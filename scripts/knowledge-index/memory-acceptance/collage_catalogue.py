"""Catalogue component photographs in oriented parent-image coordinates."""

import re
from itertools import groupby
from PIL import Image, ImageOps

from openlabel_album import bind_face, stable_id, text_value


def regular_grid(image: Image.Image) -> dict | None:
    """Accept regular full-length light gutters; tilted or irregular layouts await review."""
    im = ImageOps.exif_transpose(image).convert("L")
    width, height = im.size

    def divisions(across: bool) -> list[int] | None:
        step, length = (width, height) if across else (height, width)

        def gutter(i: int) -> bool:
            line = im.crop((i, 0, i + 1, height) if across else (0, i, width, i + 1))
            return sum(line.histogram()[238:]) >= 0.99 * length

        edges = [0]
        for light, group in groupby(range(step), key=gutter):
            indices = list(group)
            if not light or indices[0] == 0 or indices[-1] == step - 1:
                continue
            if len(indices) > 0.035 * step:
                return None
            edges.append((indices[0] + indices[-1]) // 2)
        edges.append(step)
        gaps = [b - a for a, b in zip(edges, edges[1:])]
        return edges if min(gaps) >= 24 and max(gaps) <= 1.08 * min(gaps) else None

    xs, ys = divisions(True), divisions(False)
    if not xs or not ys or (len(xs) - 1) * (len(ys) - 1) < 2:
        return None
    return {
        "panels": [
            {
                "polygon": [
                    [l / width, t / height],
                    [r / width, t / height],
                    [r / width, b / height],
                    [l / width, b / height],
                ],
                "actions": [],
            }
            for t, b in zip(ys, ys[1:])
            for l, r in zip(xs, xs[1:])
        ]
    }


def contains(polygon: list, point: tuple) -> bool:
    """Even-odd point containment, including rotated photo layouts."""
    x, y = point
    inside = False
    for i, (a, b) in enumerate(polygon):
        c, d = polygon[i - 1]
        if (b > y) != (d > y) and x < a + (y - b) * (c - a) / (d - b):
            inside = not inside
    return inside


def catalogue(scene: dict, asset: str, layout: dict, regions: dict) -> None:
    """Create OpenLABEL polygons, panel-to-face and panel-to-observation relations."""
    data = scene["openlabel"]
    w, h = (data["metadata"]["image_" + axis] for axis in ("width", "height"))
    objects = data.setdefault("objects", {})
    relations = data.setdefault("relations", {})
    actions = data.setdefault("actions", {})
    panels = layout["panels"]
    if len(panels) < 2:
        raise ValueError("A collage needs multiple photographs")
    for number, panel in enumerate(panels, 1):
        points = panel["polygon"]
        if len(points) < 3 or any(
            len(pt) != 2 or any(not 0 <= v <= 1 for v in pt) for pt in points
        ):
            raise ValueError("Invalid normalized component polygon")
        panel_id = stable_id(asset, "component", str(number))
        objects[panel_id] = {
            "name": str(number),
            "type": "component_photo",
            "object_data": {
                "poly2d": [
                    {
                        "name": "outline",
                        "mode": "MODE_POLY2D_ABSOLUTE",
                        "closed": True,
                        "val": [
                            v * scale for pt in points for v, scale in zip(pt, (w, h))
                        ],
                    }
                ]
            },
        }
        face_ids = {}
        for (ns, fid), region in regions.items():
            if ns != "immich":
                continue
            l, t, r, b = region["box"]
            center = ((l + r) / 2, (t + b) / 2)
            if not contains(points, center):
                continue
            # Near a boundary or overlapped by another panel: do not infer membership.
            inside = sum(
                contains(points, (l + (r - l) * x, t + (b - t) * y))
                for x in (0.1, 0.5, 0.9)
                for y in (0.1, 0.5, 0.9)
            )
            if sum(contains(p["polygon"], center) for p in panels) != 1 or inside < 7:
                continue
            uid = bind_face(
                asset,
                objects,
                regions,
                w,
                h,
                dict(namespace=ns, face_id=fid, person_id=region["person_id"]),
            )
            face_ids[fid] = uid

        def relate(kind, subject, target):
            relations[stable_id(panel_id, kind, subject["uid"], target["uid"])] = {
                "type": kind,
                "name": "component catalogue",
                "rdf_subjects": [subject],
                "rdf_objects": [target],
            }

        parent = {"type": "object", "uid": panel_id}
        for uid in face_ids.values():
            relate("contains_face", parent, {"type": "object", "uid": uid})
        for i, observation in enumerate(panel["actions"]):
            uid = stable_id(panel_id, "observation", str(i))
            actions[uid] = {
                "type": observation["code"],
                "name": observation["text"],
                "action_data": {"text": [text_value("source", "component review")]},
            }
            action = {"type": "action", "uid": uid}
            relate("contains_action", parent, action)
            for fid in observation["actors"]:
                if fid not in face_ids:
                    raise ValueError("Action actor outside its reviewed component")
                relate("actor", action, {"type": "object", "uid": face_ids[fid]})


def project(data: dict) -> tuple[dict, list]:
    """Separate component evidence from parent captions when rendering either view."""
    panels = {
        uid: {
            "number": int(obj["name"]),
            "polygon": obj["object_data"]["poly2d"][0]["val"],
            "faces": [],
            "actions": [],
        }
        for uid, obj in data.get("objects", {}).items()
        if obj["type"] == "component_photo"
    }
    if not panels:
        return data, []
    excluded, actors = set(), {}
    for rel in data["relations"].values():
        if rel["name"] != "component catalogue":
            continue
        src = rel["rdf_subjects"][0]["uid"]
        dst = rel["rdf_objects"][0]["uid"]
        if rel["type"] == "actor":
            actors.setdefault(src, []).append(dst)
        elif rel["type"] == "contains_face":
            panels[src]["faces"].append(dst)
        elif rel["type"] == "contains_action":
            panels[src]["actions"].append(dst)
            excluded.add(dst)
    for panel in panels.values():
        panel["faces"].sort()
        panel["actions"] = [
            {
                "text": data["actions"][uid]["name"],
                "code": data["actions"][uid]["type"],
                "actors": sorted(actors.get(uid, [])),
            }
            for uid in sorted(panel["actions"])
        ]
    parent = dict(
        data,
        objects={k: v for k, v in data["objects"].items() if k not in panels},
        actions={k: v for k, v in data["actions"].items() if k not in excluded},
        relations={
            k: v
            for k, v in data["relations"].items()
            if v["name"] != "component catalogue"
        },
    )
    return parent, sorted(panels.values(), key=lambda p: p["number"])


def filter_timeline(page: str, collages: set[str], total: int) -> str:
    """Remove only catalogue parents from the existing HTML journey, preserving its sections."""

    def keep(match):
        article = match.group()
        return (
            "" if any(f"/photos/{asset}" in article for asset in collages) else article
        )

    page = re.sub(r"<article\b[^>]*>.*?</article>", keep, page, flags=re.S)
    return re.sub(
        r"\b\d+ highlights\. Browse by recorded year\.",
        f"{total-len(collages)} highlights. Browse by recorded year.",
        page,
        count=1,
    )

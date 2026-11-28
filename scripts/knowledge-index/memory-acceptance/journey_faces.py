"""Account for every native detection in a multi-person photo using reviewed evidence."""

from openlabel_album import bind_face, fields, stable_id, text_value

VERBS = {
    "stands": "ACT.001", "sits": "ACT.003", "smiles": "ACT.005", "rests": "ACT.007",
    "looks": "ACT.008", "faces": "ACT.008", "holds": "ACT.009", "hugs": "ACT.013",
    "walks": "ACT.014", "crouches": "ACT.016", "kneels": "ACT.012", "leans": "ACT.018",
    "kisses": "ACT.025",
}
SOURCE = "individual face review"


def complete_faces(scene: dict, asset: str, regions: dict, subjects: set, reviews: dict) -> None:
    """Persist a reviewed action, alternate detection or explicit disposition for every gap."""
    native = {fid: ref for (ns, fid), ref in regions.items() if ns == "immich"}
    if len(native) < 2:
        if reviews:
            raise ValueError("Per-person review no longer matches the group photo")
        return
    data = scene["openlabel"]
    w, h = (data["metadata"]["image_" + axis] for axis in ("width", "height"))
    objects = data.setdefault("objects", {})
    missing = {fid for fid in native if stable_id(asset, "immich", fid) not in subjects}
    if reviews.keys() - missing:
        raise ValueError("Face review contains a stale or already covered detection")

    def bind(fid: str) -> str:
        ref = native[fid]
        # Immich can extend a detection past the image edge. Draw its visible portion.
        clipped = dict(ref, box=[min(1, max(0, value)) for value in ref["box"]])
        return bind_face(asset, objects, {("immich", fid): clipped}, w, h, ref)

    for fid in sorted(missing):
        review = reviews.get(fid, {})
        if review and review["box"] != native[fid]["box"]:
            raise ValueError("Reviewed face box changed")
        if local_id := review.get("same_local_face"):
            local = stable_id(asset, "photo-index", local_id)
            if local not in subjects:
                raise ValueError("Reviewed alternate face is no longer a caption subject")
            data_fields = objects[local]["object_data"]["text"]
            if any(entry["name"] == "immich_face_id" for entry in data_fields):
                raise ValueError("Multiple native detections mapped to a single subject")
            data_fields.append(text_value("immich_face_id", fid))
            continue
        actor = bind(fid)
        if "action" not in review:
            reason = review.get("reason", "Individual action has not been reviewed.")
            objects[actor]["object_data"]["text"].append(text_value("action_withheld", reason))
            continue
        verb, space, detail = review["action"].partition(" ")
        code = VERBS[verb]
        target = review.get("target")
        if detail.count("{person}") != int(bool(target)):
            raise ValueError("Participant wording differs from the reviewed face links")
        roles = {"actor": actor}
        if target:
            if target == fid or native[target]["box"] != review["target_box"]:
                raise ValueError("Reviewed action target changed")
            roles["held_person" if verb == "holds" else "participant"] = bind(target)
            if verb == "holds":
                code = "ACT.002"
        uid = stable_id(asset, "individual action", fid, code)
        data.setdefault("actions", {})[uid] = {
            "name": verb, "type": code, "action_data": {"text": [
                text_value("source", SOURCE), text_value("detail", space + detail)]}}
        for role, face in roles.items():
            data.setdefault("relations", {})[stable_id(uid, role, face)] = {
                "name": SOURCE, "type": role, "rdf_subjects": [{"type": "action", "uid": uid}],
                "rdf_objects": [{"type": "object", "uid": face}]}


def project_actions(data: dict) -> tuple[dict, list]:
    """Read the per-face action claims without mixing them into the saved primary caption."""
    actions = {uid: a for uid, a in data.get("actions", {}).items()
               if fields(a["action_data"]).get("source") == SOURCE}
    if not actions:
        return data, []
    links = {uid: {} for uid in actions}
    remaining = {}
    for key, rel in data["relations"].items():
        if rel["name"] == SOURCE:
            links[rel["rdf_subjects"][0]["uid"]][rel["type"]] = rel["rdf_objects"][0]["uid"]
        else:
            remaining[key] = rel
    claims = []
    for uid, a in sorted(actions.items()):
        roles = links[uid]
        subject = roles["actor"]
        head, marker, tail = fields(a["action_data"])["detail"].partition("{person}")
        spans = [{"face": subject}, {"text": " "},
                 {"verb": a["name"], "id": uid, "code": a["type"], "roles": roles}, {"text": head}]
        if marker:
            target, = (face for role, face in roles.items() if role != "actor")
            spans.extend([{"face": target}, {"text": tail}])
        claims.append({"subject": subject, "spans": spans})
    return dict(data, actions={k:v for k,v in data["actions"].items() if k not in actions},
                relations=remaining), claims

"""Build a private OpenLABEL review from saved, face-grounded album actions."""

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from jsonschema import Draft7Validator

from person_references import PersonRef


# Principal actions keep their original occurrence IDs across vocabulary revisions.
VERBS = {
    "stands": "ACT.001", "holds": "ACT.002", "sits": "ACT.003", "waves": "ACT.004",
    "smiles": "ACT.005", "wears": "ACT.006", "rests": "ACT.007", "looks": "ACT.008",
}


# Match complete reviewed constructions. A face placeholder can be the object of
# a preposition. A relative clause or a new subject must never inherit the actor.
FACE = "\ufffc"
COMPOUNDS = (
    (rf"rests in {FACE}[’']s arms and ", r"looks to the side", "ACT.008"),
    (r"wears (?:[a-z]+|a [a-z]+ shirt) and ", r"smiles", "ACT.005"),
    (r"wears (?:[a-z]+|a [a-z]+ shirt) and ", r"sits", "ACT.003"),
    (r"sits (?:at the front of|on) the (?:[a-z]+ )?scooter and ", r"holds the handlebar", "ACT.009"),
    (rf"sits beside {FACE} with ", r"an arm around (?:him|her|them)", "ACT.010"),
    (r"sits with ", r"both children in (?:her|his|their) arms", "ACT.011"),
)


def secondary_span(parts: list[dict]) -> tuple[int, str, str] | None:
    """Return the grounded second action's offset in the final literal chunk."""
    if "text" not in parts[-1]:
        return None
    text = "".join(part.get("text", FACE) for part in parts[1:])
    for lead, phrase, code in COMPOUNDS:
        tail = r"(?: on (?:a|the) (?:[a-z]+ )?[a-z]+)?" if code == "ACT.003" else ""
        match = re.fullmatch(r"\s*" + lead + "(?P<phrase>" + phrase + ")" + tail + r"[.!]?", text)
        if match:
            words = match["phrase"]
            offset = match.start("phrase") - (len(text) - len(parts[-1]["text"]))
            return offset, words, code
    return None


def stable_id(*key: str) -> str:
    """Identify an occurrence independently of a person's display name."""
    return str(uuid5(NAMESPACE_URL, json.dumps(key, ensure_ascii=False)))


def text_value(name: str, value: str) -> dict:
    return {"name": name, "val": value}


def fields(element_data: dict) -> dict:
    return {entry["name"]: entry["val"] for entry in element_data["text"]}


# Private span reviews name these senses. Each role identifies the marked
# person's part in the event, including when the acting person is unknown.
MARKED_SENSES = {
    **{term: (VERBS[verb], "actor") for term, verb in (
        ("stand", "stands"), ("sit", "sits"), ("wave", "waves"), ("smile", "smiles"),
        ("wear", "wears"), ("rest", "rests"), ("look", "looks"))},
    "held": ("ACT.002", "held_person"), "grasp": ("ACT.009", "actor"),
    "around": ("ACT.010", "actor"), "posture": ("ACT.012", "actor"),
    "hug": ("ACT.013", "actor"), "hugged": ("ACT.013", "recipient"),
    "walk": ("ACT.014", "actor"), "hands": ("ACT.015", "actor"),
    "crouch": ("ACT.016", "actor"), "pet": ("ACT.017", "actor"),
    "lean": ("ACT.018", "actor"), "pose": ("ACT.019", "actor"),
    "selfie": ("ACT.020", "actor"), "perform": ("ACT.021", "actor"),
    "crawl": ("ACT.022", "actor"), "comforted": ("ACT.023", "recipient"),
    "speak": ("ACT.024", "actor"), "kissed": ("ACT.025", "recipient"),
    "target": ("ACT.026", "recipient"),
}


def marked_actions(asset: str, face: str, parts: list, review: dict, bind: Callable[[dict], str]) -> tuple[dict, dict]:
    """Import an audited set of literal spans, rejecting edits or identity drift."""
    ref, *pieces = parts
    if any(ref[key] != review[key] for key in ("namespace", "face_id", "person_id")):
        raise ValueError("Marked face differs from the span review")
    if not all(isinstance(piece, str) for piece in pieces):
        raise ValueError("Marked subject review requires a single face reference")
    literal = review["literal"]
    if "".join(pieces) != review.get("source_literal", literal) or not review["spans"]:
        raise ValueError("Marked caption changed or has no reviewed spans")
    actions, relations = {}, {}
    layers = [{"face": face}]
    end = 0
    for span in review["spans"]:
        start, stop, words = span["start"], span["end"], span["words"]
        if not (end <= start < stop <= len(literal)) or literal[start:stop] != words:
            raise ValueError("Action span no longer matches its saved words")
        code, role = MARKED_SENSES[span["sense"]]
        uid = stable_id(asset, face, code, str(start))
        actions[uid] = {"name": words, "type": code, "action_data": {
            "text": [text_value("source", "marked subject")]}}
        relations[stable_id(uid, role, face)] = {
            "type": role, "name": role, "rdf_subjects": [{"type": "action", "uid": uid}],
            "rdf_objects": [{"type": "object", "uid": face}]}
        layers.extend([{"text": literal[end:start]}, {"verb": words, "id": uid}])
        end = stop
        if other := span.get("recipient"):
            left, right = other["start"], other["end"]
            if (role != "actor" or not (end <= left < right <= len(literal))
                    or literal[left:right] != other["words"]):
                raise ValueError("Invalid recipient mention in reviewed action")
            other_face = bind(other)
            if other_face == face:
                raise ValueError("Actor and recipient must have distinct faces")
            layers[-1]["recipient"] = other_face
            layers.extend([{"text": literal[end:left]}, {"face": other_face, "source_words": other["words"]}])
            relations[stable_id(uid, "recipient", other_face)] = {
                "type": "recipient", "name": "recipient",
                "rdf_subjects": [{"type": "action", "uid": uid}],
                "rdf_objects": [{"type": "object", "uid": other_face}]}
            end = right
    layers.append({"text": literal[end:]})
    first = next(iter(actions))
    actions[first]["action_data"]["text"].append(text_value("marked_caption", json.dumps(layers)))
    if "source_literal" in review:
        actions[first]["action_data"]["text"].append(text_value("source_literal", review["source_literal"]))
    return actions, relations


def bind_face(asset: str, objects: dict, regions: dict, width: int, height: int, ref: dict) -> str:
    namespace, face = ref["namespace"], ref["face_id"]
    region = regions[namespace, face]
    if region["person_id"] != ref.get("person_id"):
        raise ValueError("Face assignment changed since action review")
    left, top, right, bottom = region["box"]
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise ValueError("Invalid oriented face region")
    uid = stable_id(asset, namespace, face)
    if uid in objects and not ref.get("description"):
        return uid
    objects[uid] = {
        "type": "person", "name": uid,
        "object_data": {
            "bbox": [{"name": "face", "val": [(left+right)*width/2, (top+bottom)*height/2,
                                             (right-left)*width, (bottom-top)*height]}],
            "text": [text_value("face_namespace", namespace), text_value("face_id", face),
                     text_value("person_id", ref["person_id"] or "")],
        },
    }
    if ref.get("description"):
        objects[uid]["object_data"]["text"].append(text_value("description", ref["description"]))
    return uid


DEPICTS = "http://www.wikidata.org/entity/P180"


def link_depicted_faces(scene: dict, media: dict) -> None:
    """Import reviewed OpenLABEL depiction relations after checking both ends and the source boxes."""
    data = scene["openlabel"]
    source = media["openlabel"]
    for key in ("image_width", "image_height"):
        if source["metadata"][key] != data["metadata"][key]:
            raise ValueError("Medium geometry and oriented source dimensions differ")
    objects = data.setdefault("objects", {})
    for uid, relation in source["relations"].items():
        if relation["type"] != DEPICTS or uid in data.setdefault("relations", {}):
            raise ValueError("Expected a distinct reviewed depiction relation")
        holder, = relation["rdf_subjects"]
        subject, = relation["rdf_objects"]
        if holder["type"] != "object" or subject["type"] != "object":
            raise ValueError("Depiction must connect two objects")
        medium = source["objects"][holder["uid"]]
        face = objects[subject["uid"]]
        if face["type"] != "person" or face["object_data"]["bbox"] != source["objects"][subject["uid"]]["object_data"]["bbox"]:
            raise ValueError("Depicted face differs from the reviewed source")
        x, y, width, height = medium["object_data"]["bbox"][0]["val"]
        cx, cy, fw, fh = face["object_data"]["bbox"][0]["val"]
        if abs(cx-x) + fw/2 > width/2 or abs(cy-y) + fh/2 > height/2:
            raise ValueError("Reviewed face is outside its medium")
        if objects.setdefault(holder["uid"], medium) != medium:
            raise ValueError("Conflicting medium object")
        data["relations"][uid] = relation


def build_scene(asset: str, actions: list, regions: dict, width: int, height: int,
                marked: dict | None = None) -> dict:
    """Keep reviewed sentence fragments, source IDs and directional roles together."""
    objects, observations, relations = {}, {}, {}

    def bind(ref: dict) -> str:
        return bind_face(asset, objects, regions, width, height, ref)

    if marked and "scene" in marked:
        if actions or not marked.get("reason") or not marked["scene"]:
            raise ValueError("Scene-only evidence conflicts with saved actions")
        return {"openlabel": {"metadata": {"schema_version": "1.0.0", "vocabulary_release": "album-3",
                                          "image_width": width, "image_height": height},
                              "contexts": {"0": {"name": "Scene", "type": "scene_description",
                              "context_data": {"text": [text_value("description", marked["scene"]),
                                                        text_value("reason", marked["reason"])]}}}}}
    if marked and len(actions) != 1:
        raise ValueError("Expected exactly one saved marked subject")
    for parts in actions:
        actor = bind(parts[0])
        if marked:
            observations, relations = marked_actions(asset, actor, parts, marked, bind)
            continue
        # Saved sentences keep participant references and literal text in reading order.
        chunks = []
        for part in parts:
            if isinstance(part, dict):
                chunks.append({"face": bind(part)})
            elif chunks and "text" in chunks[-1]:
                chunks[-1]["text"] += part
            else:
                chunks.append({"text": part})
        if len(chunks) < 2 or not chunks[1].get("text", "").strip():
            raise ValueError("Reviewed action must start with the bound actor and a verb")
        first = chunks[1]["text"].lstrip()
        verb = first.split()[0]
        if verb not in VERBS:
            raise ValueError("Unmapped reviewed principal verb")
        code = VERBS[verb]
        action = stable_id(asset, actor, code)
        if action in observations:
            raise ValueError("Duplicate principal action for saved face")
        roles = {"actor": actor}
        if code == "ACT.002":
            if first.strip() != verb or len(chunks) < 3 or "face" not in chunks[2]:
                raise ValueError("Holding a person requires an explicit held face")
            roles["held_person"] = chunks[2]["face"]
            if actor == roles["held_person"]:
                raise ValueError("Holder and held person must be distinct")
        observations[action] = {
            "name": verb, "type": code, "action_data": {"text": [
                text_value("caption_parts", json.dumps(chunks, ensure_ascii=False)),
                text_value("source", "verified group action"),
            ]},
        }
        bindings = [(action, roles)]
        extra = secondary_span(chunks)
        if extra:
            offset, words, extra_code = extra
            uid = stable_id(asset, actor, extra_code)
            if uid in observations:
                raise ValueError("Duplicate action occurrence")
            observations[uid] = {
                "name": words, "type": extra_code, "action_data": {"text": [
                    text_value("sentence_action", action), text_value("offset", str(offset)),
                    text_value("source", "verified group action"),
                ]},
            }
            extra_roles = {"actor": actor}
            if extra_code == "ACT.010":
                extra_roles["recipient"] = chunks[-2]["face"]
            bindings.append((uid, extra_roles))
        for occurrence, participants in bindings:
            for role, face in participants.items():
                relations[stable_id(occurrence, role, face)] = {
                    "type": role, "name": role,
                    "rdf_subjects": [{"type": "action", "uid": occurrence}],
                    "rdf_objects": [{"type": "object", "uid": face}],
                }
    return {"openlabel": {"metadata": {"schema_version": "1.0.0", "vocabulary_release": "album-3" if marked else "album-2",
                                        "image_width": width, "image_height": height},
                          "objects": objects, "actions": observations, "relations": relations}}


def card(scene: dict, names: dict) -> dict:
    """Derive display words and click targets from the stored OpenLABEL document."""
    from collage_catalogue import project
    from journey_faces import project_actions
    data, panels = project(scene["openlabel"])
    data, individual = project_actions(data)
    details = {"width": data["metadata"]["image_width"], "height": data["metadata"]["image_height"]}
    details["individual"] = individual
    if panels:
        details["panels"] = panels
    for context in data.get("contexts", {}).values():
        if context["type"] == "reconciliation_evidence":
            details["caption_sources"] = fields(context["context_data"])
        if context["type"] == "capture_date_conflict":
            details["date_conflict"] = fields(context["context_data"])
    depictions = {}
    for rel in data.get("relations", {}).values():
        if rel["type"] == DEPICTS:
            for target in rel["rdf_objects"]:
                depictions.setdefault(target["uid"], []).extend(ref["uid"] for ref in rel["rdf_subjects"])
    faces = {}
    for uid, obj in data.get("objects", {}).items():
        if obj["type"] != "person":
            continue
        source = fields(obj["object_data"])
        local_key = source["face_namespace"] + ":" + source["face_id"]
        display = PersonRef(source["person_id"], names.get(local_key) or source.get("description", "")).name(names)
        directory_name = names.get(source["person_id"]) or names.get(local_key) or ""
        faces[uid] = {"name": display, "unnamed": not directory_name.strip(),
                      "box": obj["object_data"]["bbox"][0]["val"], **source}
        if uid in depictions:
            faces[uid]["depicted_in"] = sorted(set(depictions[uid]))
    mentions = []
    for context_id, context in sorted(data.get("contexts", {}).items()):
        if context["type"] == "caption_mention":
            mention = fields(context["context_data"])
            mention["faces"] = []
            mentions.append((context_id, mention))
    mention_map = dict(mentions)
    for relation in data.get("relations", {}).values():
        subject = relation["rdf_subjects"][0]
        if subject["type"] == "context" and subject["uid"] in mention_map:
            mention_map[subject["uid"]]["faces"].extend(r["uid"] for r in relation["rdf_objects"])
    details["mentions"] = list(mention_map.values())
    if "0" in data.get("contexts", {}) and not data.get("actions"):
        context = fields(data["contexts"]["0"]["context_data"])
        return {"faces": faces, "claims": [], "scene": context["description"], "reason": context["reason"], **details}
    role_map = {}
    for relation in data["relations"].values():
        if relation["rdf_subjects"][0]["type"] != "action" or relation["name"] == "caption participant":
            continue
        uid = relation["rdf_subjects"][0]["uid"]
        role_map.setdefault(uid, {})[relation["type"]] = relation["rdf_objects"][0]["uid"]

    claims = []
    sentences = {}
    secondary = {}
    for uid, action in sorted(data["actions"].items()):
        saved = fields(action["action_data"])
        if saved.get("source") == "marked subject":
            if "marked_caption" in saved:
                spans = json.loads(saved["marked_caption"])
                face = spans[0]["face"]
                for span in spans:
                    if "verb" in span:
                        record = data["actions"][span["id"]]
                        roles = role_map[span["id"]]
                        if "recipient" in span:
                            valid = roles == {"actor": face, "recipient": span["recipient"]}
                        else:
                            valid = len(roles) == 1 and set(roles.values()) == {face}
                        if span["verb"] != record["name"] or not valid:
                            raise ValueError("Stored marked action is inconsistent with its caption")
                        span.update(roles=roles, code=record["type"])
                claims.append({"spans": spans, "subject": face})
        elif "sentence_action" in saved:
            secondary.setdefault(saved["sentence_action"], []).append((int(saved["offset"]), uid))
        else:
            sentences[uid] = json.loads(saved["caption_parts"])
    if secondary.keys() - sentences.keys():
        raise ValueError("Secondary action missing its reviewed sentence")

    for uid, parts in sentences.items():
        action = data["actions"][uid]
        roles = role_map[uid]
        if roles["actor"] != parts[0]["face"]:
            raise ValueError("Caption and actor disagree")
        if action["type"] == "ACT.002" and roles.get("held_person") != parts[2]["face"]:
            raise ValueError("Caption and held person disagree")
        # Split the final literal first so offsets still refer to the saved text,
        # including when the primary and secondary verbs share one literal.
        spans = list(parts)
        last_literal = len(parts) - 1
        for offset, extra_id in sorted(secondary.get(uid, []), reverse=True):
            extra_action = data["actions"][extra_id]
            words = extra_action["name"]
            literal = spans[last_literal]["text"]
            if role_map[extra_id]["actor"] != roles["actor"] or literal[offset:offset+len(words)] != words:
                raise ValueError("Secondary action span or actor differs from reviewed caption")
            spans[last_literal:last_literal+1] = [
                {"text": literal[:offset]}, {"verb": words, "id": extra_id},
                {"text": literal[offset+len(words):]},
            ]
        prefix, verb, tail = spans[1]["text"].partition(action["name"])
        if not verb or prefix.strip():
            raise ValueError("Verb span differs from saved caption")
        spans[1:2] = [{"text": prefix}, {"verb": verb, "id": uid}, {"text": tail}]
        for span in spans:
            if "verb" in span:
                span["roles"] = role_map[span["id"]]
                span["code"] = data["actions"][span["id"]]["type"]
        claims.append({"spans": spans, "subject": roles["actor"], "roles": roles, "code": action["type"]})
    by_id = {span["id"]: span for claim in claims for span in claim["spans"] if "verb" in span}
    for relation in data["relations"].values():
        if relation["name"] == "caption participant":
            span = by_id[relation["rdf_subjects"][0]["uid"]]
            span.setdefault("participants", []).extend(
                {"role": relation["type"], "face": ref["uid"]} for ref in relation["rdf_objects"])
    tagged = [span["id"] for claim in claims for span in claim["spans"] if "verb" in span]
    if set(tagged) != data["actions"].keys() or len(tagged) != len(data["actions"]):
        raise ValueError("Every stored action must have exactly one clickable span")
    return {"faces": faces, "claims": claims, **details}


def validate_scenes(scenes: dict, schema: Path) -> None:
    """Validate locally against the caller's pinned OpenLABEL 1.0.0 schema."""
    definition = json.loads(schema.read_text())
    if definition["definitions"]["metadata"]["properties"]["schema_version"]["enum"] != ["1.0.0"]:
        raise ValueError("Expected ASAM OpenLABEL 1.0.0")
    validator = Draft7Validator(definition)
    for scene in scenes.values():
        validator.validate(scene)


def persist(conn, album: str, scenes: dict) -> dict:
    """Append changed revisions atomically and return the committed document contents."""
    result = {}
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (album,))
        conn.execute("""CREATE TABLE IF NOT EXISTS openlabel_album_scene (
            album uuid NOT NULL, asset uuid NOT NULL, revision integer NOT NULL,
            digest text NOT NULL, scene jsonb NOT NULL, PRIMARY KEY(album, asset, revision))""")
        for asset, scene in sorted(scenes.items()):
            payload = json.dumps(scene, sort_keys=True, ensure_ascii=False)
            digest = hashlib.sha256(payload.encode()).hexdigest()
            row = conn.execute("""SELECT revision, digest, scene FROM openlabel_album_scene
                WHERE album=%s AND asset=%s ORDER BY revision DESC LIMIT 1""", (album, asset)).fetchone()
            if row and row[1] == digest:
                result[asset] = row[2]
            else:
                result[asset] = conn.execute("""INSERT INTO openlabel_album_scene
                    VALUES (%s,%s,%s,%s,%s::jsonb) RETURNING scene""",
                    (album, asset, row[0]+1 if row else 1, digest, payload)).fetchone()[0]
    return result

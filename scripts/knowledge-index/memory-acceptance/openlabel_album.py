"""Build a private OpenLABEL review from saved, face-grounded album actions."""

import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from jsonschema import Draft7Validator

from person_references import PersonRef


# The type is stable even if the displayed wording changes. Only map the reviewed verb.
VERBS = {
    "stands": "ACT.001", "holds": "ACT.002", "sits": "ACT.003", "waves": "ACT.004",
    "smiles": "ACT.005", "wears": "ACT.006", "rests": "ACT.007", "looks": "ACT.008",
}


def stable_id(*key: str) -> str:
    """Identify an occurrence independently of a person's display name."""
    return str(uuid5(NAMESPACE_URL, json.dumps(key, ensure_ascii=False)))


def text_value(name: str, value: str) -> dict:
    return {"name": name, "val": value}


def fields(element_data: dict) -> dict:
    return {entry["name"]: entry["val"] for entry in element_data["text"]}


def build_scene(asset: str, actions: list, regions: dict, width: int, height: int) -> dict:
    """Keep reviewed sentence fragments, source IDs and directional roles together."""
    objects, observations, relations = {}, {}, {}

    def bind(ref: dict) -> str:
        namespace, face = ref["namespace"], ref["face_id"]
        region = regions[namespace, face]
        if region["person_id"] != ref.get("person_id"):
            raise ValueError("Face assignment changed since action review")
        left, top, right, bottom = region["box"]
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise ValueError("Invalid oriented face region")
        uid = stable_id(asset, namespace, face)
        objects[uid] = {
            "type": "person", "name": uid,
            "object_data": {
                "bbox": [{"name": "face", "val": [(left+right)*width/2, (top+bottom)*height/2,
                                                 (right-left)*width, (bottom-top)*height]}],
                "text": [text_value("face_namespace", namespace), text_value("face_id", face),
                         text_value("person_id", ref["person_id"] or "")],
            },
        }
        return uid

    for parts in actions:
        actor = bind(parts[0])
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
        for role, face in roles.items():
            relations[stable_id(action, role, face)] = {
                "type": role, "name": role,
                "rdf_subjects": [{"type": "action", "uid": action}],
                "rdf_objects": [{"type": "object", "uid": face}],
            }
    return {"openlabel": {"metadata": {"schema_version": "1.0.0", "vocabulary_release": "album-1",
                                        "image_width": width, "image_height": height},
                          "objects": objects, "actions": observations, "relations": relations}}


def card(scene: dict, names: dict) -> dict:
    """Derive display words and click targets from the stored OpenLABEL document."""
    data = scene["openlabel"]
    faces = {}
    for uid, obj in data["objects"].items():
        source = fields(obj["object_data"])
        local_key = source["face_namespace"] + ":" + source["face_id"]
        display = PersonRef(source["person_id"], names.get(local_key, "")).name(names)
        faces[uid] = {"name": display,
                      "box": obj["object_data"]["bbox"][0]["val"], **source}
    claims = []
    for uid, action in sorted(data["actions"].items()):
        roles = {r["type"]: r["rdf_objects"][0]["uid"] for r in data["relations"].values()
                 if r["rdf_subjects"][0]["uid"] == uid}
        parts = json.loads(fields(action["action_data"])["caption_parts"])
        if roles["actor"] != parts[0]["face"]:
            raise ValueError("Caption and actor disagree")
        if action["type"] == "ACT.002" and roles.get("held_person") != parts[2]["face"]:
            raise ValueError("Caption and held person disagree")
        prefix, verb, tail = parts[1]["text"].partition(action["name"])
        if not verb or prefix.strip():
            raise ValueError("Verb span differs from saved caption")
        spans = [parts[0], {"text": prefix}, {"verb": verb, "id": uid}, {"text": tail}, *parts[2:]]
        claims.append({"spans": spans, "roles": roles, "code": action["type"]})
    return {"faces": faces, "claims": claims, "width": data["metadata"]["image_width"],
            "height": data["metadata"]["image_height"]}


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

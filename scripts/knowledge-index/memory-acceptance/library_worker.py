"""Process a shared face-occurrence checkpoint on local Bonsai backends."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import fcntl
from io import BytesIO
import json
import os
import re
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from journey_faces import VERBS
from library_backfill import HERE, claims, connect, status

sys.path.insert(0, str(HERE.parent / "enrichers"))
from media_summary import ask_model

DEFAULT_MAC_LANES = 4
DEFAULT_RTX_LANES = 3
# The matched pass-count trial selected joint inference on RTX only.
JOINT_BACKENDS = {"rtx3070"}

STAGES = (
    "baby_toddler",
    "preschool",
    "school_age",
    "teen",
    "young_adult",
    "adult",
    "unknown",
)
AGE_PROMPT = """Classify only the person whose face is marked in yellow. The second image
is a crop of that same face. Ignore writing and recorded dates. Return JSON with stage
(one of %s) and confidence (high, medium, low). Use unknown if unclear. Do not guess
identity or precise age.""" % ", ".join(
    STAGES
)
ACTION_PROMPT = """Describe the visible action of ONLY the person with the yellow face box in
the first image. The second image is a closer view of the same subject. Follow that face
to its body. Use no names, ages, relationships, identity or intentions. If its action is
unclear or belongs to someone else, return null for both fields. Otherwise return JSON
with verb (one of %s) and action (a short English sentence fragment beginning with that
exact verb in lowercase, e.g. smiles toward the camera).""" % ", ".join(
    VERBS
)
AGE_SCHEMA = {
    "type": "object",
    "properties": {
        "stage": {"enum": list(STAGES)},
        "confidence": {"enum": ["high", "medium", "low"]},
    },
    "required": ["stage", "confidence"],
}
ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "verb": {"enum": [*VERBS, None]},
        "action": {"type": ["string", "null"]},
    },
    "required": ["verb", "action"],
}


JOINT_PROMPT = """Use the full image and crop to describe only the person whose face is
boxed in yellow. Return one JSON object with stage, confidence, verb and action.
For stage, choose one of %s. Ignore dates and writing. Use unknown when unclear.
Give stage confidence as high, medium or low. For action, follow the marked face to
its own body. Describe only what that person visibly does. Use no names, ages,
relationships or intentions in the action. Choose one verb from %s and a short English
fragment starting with the same lowercase verb, e.g. smiles toward the camera.
Return null for both verb and action if the actor or activity is unclear.""" % (
    ", ".join(STAGES),
    ", ".join(VERBS),
)
JOINT_SCHEMA = {
    "type": "object",
    "properties": {**AGE_SCHEMA["properties"], **ACTION_SCHEMA["properties"]},
    "required": [*AGE_SCHEMA["required"], *ACTION_SCHEMA["required"]],
}


def frames(row):
    url = "https://photos.app.home.panderosystems.com/api/thumbnail?" + urlencode(
        {"path": row["path"]}
    )
    with urlopen(url, timeout=40) as reply:
        data = reply.read(8_000_001)
    if len(data) > 8_000_000:
        raise ValueError("Oversize thumbnail")
    with Image.open(BytesIO(data)) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
    image.thumbnail((840, 840))
    width, height = image.size
    x, y, right, bottom = [
        round(max(0, min(1, v)) * scale) for v, scale in zip(row["box"], image.size * 2)
    ]
    dx, dy = right - x, bottom - y
    if min(dx, dy) < 12:
        return []
    target = image.crop(
        (
            max(0, x - dx),
            max(0, y - dy // 2),
            min(width, right + dx),
            min(height, bottom + 2 * dy),
        )
    )
    ImageDraw.Draw(image).rectangle((x, y, right, bottom), outline="yellow", width=3)
    pictures = []
    for pic in (image, target):
        buf = BytesIO()
        pic.save(buf, format="JPEG", quality=88)
        pictures.append(buf.getvalue())
    return pictures


def decode(answer):
    if not isinstance(answer, str):
        raise ValueError("Model returned no text")
    raw = answer.strip().removeprefix("```json").removesuffix("```").strip()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def observe(backend, endpoint, pictures, prompt, schema, *, images_first=False):
    if backend == "rtx3070":
        extra = {
            "think": False,
            "format": schema,
            "options": {"temperature": 0.1, "num_ctx": 4096, "num_predict": 160},
        }
        return decode(
            ask_model(
                endpoint,
                "bonsai-27b",
                prompt,
                pictures,
                timeout=150,
                api="ollama",
                images_first=images_first,
                extra=extra,
            )
        )
    key = (
        (Path.home() / "Library/Application Support/knowledge-index-bonsai/server.key")
        .read_text()
        .strip()
    )
    extra = {
        "max_tokens": 160,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    return decode(
        ask_model(
            endpoint,
            "bonsai-27b-metal",
            prompt,
            pictures,
            timeout=100,
            headers={"Authorization": "Bearer " + key},
            images_first=images_first,
            extra=extra,
        )
    )


def normalized_action(action):
    """Join complementary fields without changing the model’s actor, verb or object."""
    verb, text = action["verb"], action["action"]
    # Native Ollama sometimes separates the selected verb from its prepositional detail.
    if (
        verb in VERBS
        and isinstance(text, str)
        and text.split(" ", 1)[0]
        in {
            "at",
            "toward",
            "towards",
            "with",
            "in",
            "on",
            "beside",
            "near",
            "under",
            "over",
            "into",
            "from",
            "behind",
            "to",
            "down",
            "up",
        }
    ):
        text = verb + " " + text
    # Some responses put an article and a single object noun in the second field.
    # Keep longer clauses on the validation path; their subject can be ambiguous.
    if (
        verb in {"holds", "hugs", "kisses", "faces"}
        and isinstance(text, str)
        and re.fullmatch(r"(?:a|an|the) [A-Za-z]+[.]?", text)
    ):
        text = verb + " " + text
    if (verb, text) != (None, None) and (
        verb not in VERBS
        or not isinstance(text, str)
        or text.split(" ", 1)[0].rstrip(".") != verb
        or len(text) > 450
    ):
        raise ValueError("Invalid action")
    return verb, text


def normalized_stage(age: dict) -> tuple[str, str]:
    """Validate a stage reading and retain low confidence as an abstention."""
    if age.get("stage") not in STAGES or age.get("confidence") not in {
        "high",
        "medium",
        "low",
    }:
        raise ValueError("Invalid stage")
    stage = age["stage"] if age["confidence"] != "low" else "unknown"
    return stage, age["confidence"]


def infer(row, backend, endpoint, saved, checkpoint, *, joint=False, observer=None):
    model_call = observer or observe
    start = time.monotonic()
    pics = frames(row)
    if not pics:
        return "withheld", dict(saved, reason="Face too small on preview")
    combined = None
    reused_age = "stage" in saved
    if joint and "stage" not in saved and not saved.get("reviewed_action"):
        combined = model_call(backend, endpoint, pics, JOINT_PROMPT, JOINT_SCHEMA)
    if "stage" not in saved:
        age = (
            combined
            if combined is not None
            else model_call(backend, endpoint, pics, AGE_PROMPT, AGE_SCHEMA)
        )
        stage, confidence = normalized_stage(age)
        saved.update(stage=stage, confidence=confidence)
        checkpoint(saved)
    if not saved.get("reviewed_action"):
        action = (
            combined
            if combined is not None
            else model_call(backend, endpoint, pics, ACTION_PROMPT, ACTION_SCHEMA)
        )
        verb, text = normalized_action(action)
        saved.update(verb=verb, action=text, code=VERBS.get(verb))
    if combined is not None:
        mode = "joint"
    elif reused_age:
        mode = "reused_stage"
    elif saved.get("reviewed_action"):
        mode = "reused_action"
    else:
        mode = "two_pass"
    saved.update(
        inference_mode=mode,
        backend=backend,
        seconds=round(time.monotonic() - start, 3),
        source="marked face",
    )
    if saved["stage"] == "unknown" or not saved.get("action"):
        saved["reason"] = "Life stage or action unclear"
        return "withheld", saved
    saved.pop("reason", None)
    return "complete", saved


def lane(root, backend, endpoint, limit):
    with closing(connect(root)) as db:
        processed = failures = 0
        while not limit or processed < limit:
            reserve = claims.claim(db, mac_batch=0, resume=False)
            if not reserve:
                return
            face, raw = reserve
            old, attempts = db.execute(
                "SELECT outcome,attempts FROM jobs WHERE asset=?", (face,)
            ).fetchone()
            saved = json.loads(old or "{}")

            def checkpoint(value):
                with db:
                    db.execute(
                        "UPDATE jobs SET outcome=? WHERE asset=?",
                        (json.dumps(value), face),
                    )

            try:
                state, value = infer(
                    json.loads(raw),
                    backend,
                    endpoint,
                    saved,
                    checkpoint,
                    joint=backend in JOINT_BACKENDS,
                )
                failures = 0
            except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
                failures += 1
                saved["reason"] = (
                    str(error) if type(error) is ValueError else type(error).__name__
                )
                permanent = isinstance(error, UnidentifiedImageError) or (
                    isinstance(error, HTTPError)
                    and error.code in (404, 410)
                    and "/api/thumbnail?" in error.url
                )
                if (
                    permanent
                    or isinstance(error, (ValueError, KeyError, IndexError, TypeError))
                    and attempts >= 1
                ):
                    state, value = "withheld", saved
                else:
                    # Release to the next run. Other lanes continue on different faces.
                    state, value = "pending", saved
                with db:
                    db.execute(
                        "UPDATE jobs SET attempts=attempts+1 WHERE asset=?", (face,)
                    )
            claims.finish(db, face, state, json.dumps(value))
            (root / "progress").touch()
            processed += 1
            if failures >= 3:
                if limit:
                    return
                time.sleep(45)
                failures = 0


def run(root, rtx, mac_slots, rtx_slots, limit):
    with (root / "worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with closing(connect(root)) as db, db:
            db.execute("UPDATE jobs SET status='pending' WHERE status='running'")
            db.execute(
                "DELETE FROM rtx_life_stage_claims WHERE asset IN (SELECT asset FROM jobs WHERE status='pending')"
            )
            db.commit()
        with ThreadPoolExecutor(mac_slots + rtx_slots) as pool:
            tasks = [
                pool.submit(lane, root, "mac-metal", "http://127.0.0.1:19476", limit)
                for _ in range(mac_slots)
            ]
            tasks += [
                pool.submit(lane, root, "rtx3070", rtx, limit) for _ in range(rtx_slots)
            ]
            for task in tasks:
                task.result()
        with closing(connect(root)) as db:
            print(json.dumps(status(db)), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("--rtx", required=True)
    p.add_argument("--mac-slots", type=int, default=DEFAULT_MAC_LANES)
    p.add_argument("--rtx-slots", type=int, default=DEFAULT_RTX_LANES)
    p.add_argument("--limit-per-lane", type=int, default=0)
    args = p.parse_args()
    os.umask(0o077)
    run(args.root, args.rtx, args.mac_slots, args.rtx_slots, args.limit_per_lane)

"""Batch-check caption mentions against numbered Immich faces with a local vision model.

Read JSONL jobs with asset UUID, image path, captions (strings), and regions from
the owner-scoped source snapshot. Store per-asset resumable private decisions.
"""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
import json
import os
import re
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen
from uuid import UUID

from PIL import Image, ImageDraw, ImageOps

from caption_participants import PLURAL, candidate_phrases, fingerprint

PROMPT = """For each target phrase, select ONLY the numbered face(s) the phrase refers to.
For "being held by an adult", select the adult holding the subject. For "with another person",
select the companion. Exclude the main subject for both examples. Trace hands to their owners.
If the referenced person is off camera, the interaction is unclear, or a pictured bystander
is not the participant, return no boxes. A singular phrase can select at most ONE face.
Never infer friendship or family relationships. Do not cross collage panels. Use exact target
phrase strings, and return JSON {"mentions":[{"words":"target phrase","boxes":[number],"certain":true}]}.
"""


def observe(
    image: Image.Image, refs: list, captions: list, phrases: list, call, offset: int
) -> dict:
    """Translate per-pass image labels back to native face IDs before comparison."""
    marked = image.copy()
    draw = ImageDraw.Draw(marked)
    lookup = {}
    for label, ref in enumerate(refs, start=offset):
        x, y, x2, y2 = [round(v * n) for v, n in zip(ref["box"], marked.size * 2)]
        draw.rectangle((x, y, x2, y2), outline="yellow", width=2)
        top = max(0, y - 13)
        draw.rectangle((x, top, x + 24, top + 12), fill="black")
        draw.text((x, top), str(label), fill="yellow")
        lookup[label] = ref["face_id"]
    answer = call(
        marked, PROMPT + json.dumps({"captions": captions, "target_phrases": phrases})
    )
    found = {}
    for m in answer["mentions"]:
        words = m["words"]
        if words not in phrases:
            continue
        if words in found:
            found[words] = set()
            continue
        labels = m["boxes"]
        found[words] = (
            {lookup[i] for i in labels}
            if m["certain"] is True
            and (len(labels) == 1 or PLURAL.search(words))
            and all(type(i) is int and i in lookup for i in labels)
            else set()
        )
    return found


CONTACT = re.compile(
    r"\b(?:hand(?:s)?|hold(?:s|ing)?|held|embrac\w*|hug\w*|kiss\w*|arm around|comfort\w*)\b",
    re.I,
)


def infer(job: dict, call) -> dict:
    """Only link a phrase when both label orders identify the same native detections."""
    refs = sorted(
        (r for r in job["regions"] if r["namespace"] == "immich"),
        key=lambda r: r["face_id"],
    )
    phrases = job.get("phrases", candidate_phrases(job["captions"]))
    if not phrases:
        return {"caption_hash": fingerprint(job["captions"]), "mentions": []}
    with Image.open(job["image"]) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
    image.thumbnail((960, 960))
    first = observe(image, refs, job["captions"], phrases, call, 1)
    second = observe(image, refs[::-1], job["captions"], phrases, call, len(refs) + 1)
    decisions = []
    for words in phrases:
        matches = first.get(words)
        verified = bool(matches) and matches == second.get(words)
        if not PLURAL.search(words) and job.get("subject_face_id") in (
            matches or set()
        ):
            verified = False
        reason = "Face match unverified."
        if verified and any(words in c and CONTACT.search(c) for c in job["captions"]):
            # The same model can consistently choose a visible bystander while the true
            # participant is outside the frame. Require independently grounded roles.
            evidence = set(job.get("verified_roles", {}).get(words, []))
            if evidence != matches:
                verified = False
                reason = "Contact partner needs independent face and action evidence."
        decisions.append(
            {
                "words": words,
                "faces": [r for r in refs if verified and r["face_id"] in matches],
                "reason": "" if verified else reason,
            }
        )
    return {"caption_hash": fingerprint(job["captions"]), "mentions": decisions}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jobs", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--port", default=19476, type=int)
    parser.add_argument("--model", default="bonsai-27b-metal")
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=True)
    headers = {"Content-Type": "application/json"}
    if args.key_file:
        headers["Authorization"] = "Bearer " + args.key_file.read_text().strip()

    def call(image, prompt):
        jpeg = BytesIO()
        image.save(jpeg, format="JPEG", quality=90)
        url = "data:image/jpeg;base64," + base64.b64encode(jpeg.getvalue()).decode()
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": url}},
        ]
        body = {
            "model": args.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": 650,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        }
        req = Request(
            f"http://127.0.0.1:{args.port}/v1/chat/completions",
            json.dumps(body).encode(),
            headers,
        )
        with urlopen(req, timeout=120) as response:
            answer = json.load(response)["choices"][0]["message"]["content"].strip()
        if answer.startswith("```json") and answer.endswith("```"):
            answer = answer[7:-3]
        return json.loads(answer)

    def process(job):
        dest = args.output / (str(UUID(job["asset"])) + ".json")
        try:
            sig = hashlib.sha256(
                json.dumps(
                    ["participant-check-v3", PROMPT, args.model, job], sort_keys=True
                ).encode()
                + Path(job["image"]).read_bytes()
            ).hexdigest()
            if dest.exists():
                old = json.loads(dest.read_text())
                if old.get("input_hash") == sig:
                    return True
                if not old.get("input_hash"):
                    raise ValueError(
                        "Use a separate output directory for model proposals and reviewed decisions"
                    )
            result = infer(job, call)
            result["input_hash"] = sig
            with tempfile.NamedTemporaryFile(
                mode="w", dir=dest.parent, delete=False
            ) as f:
                json.dump(result, f)
            os.replace(f.name, dest)
            return True
        except Exception as error:
            print(f"{dest.stem}: {type(error).__name__}", flush=True)
            return False

    with args.jobs.open() as stream, ThreadPoolExecutor(
        max_workers=args.workers
    ) as pool:
        # Bound input memory as well as concurrent vision requests.
        from itertools import islice

        failures = 0
        while batch := list(islice(stream, max(1, args.workers) * 4)):
            failures += list(
                pool.map(process, (json.loads(line) for line in batch))
            ).count(False)
    if failures:
        raise SystemExit(f"{failures} jobs failed. Rerun to resume.")


if __name__ == "__main__":
    main()

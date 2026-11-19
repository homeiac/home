#!/usr/bin/env python3
"""Validate the live Frigate face adapter without training or changing configuration (#217)."""
import argparse
import io
import json
import logging
import os
from pathlib import Path
import shlex
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image
from photo_enrichment.faces import frigate_candidate


def load_environment() -> None:
    """Read only this tool's settings from the existing protected .env, if present."""
    env = Path(__file__).resolve().parents[2] / "proxmox/homelab/.env"
    if env.is_file():
        for line in env.read_text().splitlines():
            key, separator, value = line.removeprefix("export ").partition("=")
            if separator and key in ("PHOTO_FRIGATE_URL", "PHOTO_FRIGATE_TOKEN") and key not in os.environ:
                parts = shlex.split(value, comments=True)
                if len(parts) == 1:
                    os.environ[key] = parts[0]


def main() -> None:
    """Print only aggregate checks; never names, image paths, credentials or full config."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recognize-reference", action="store_true", help="Recognize one existing training image; never register or change it")
    parser.add_argument("--warmup-seconds", type=int, default=180, help="Bounded wait for Frigate's asynchronous reference-model build")
    args = parser.parse_args()
    load_environment()
    os.environ.setdefault("PHOTO_FRIGATE_URL", "https://frigate.app.home.panderosystems.com")
    origin = os.environ["PHOTO_FRIGATE_URL"].rstrip("/")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *unused, **kwargs):
            return None

    opener = urllib.request.build_opener(NoRedirect)

    def get(path: str) -> bytes:
        headers = {}
        if os.environ.get("PHOTO_FRIGATE_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["PHOTO_FRIGATE_TOKEN"]
        with opener.open(urllib.request.Request(origin + path, headers=headers), timeout=30) as response:
            return response.read()

    version = get("/api/version").decode().strip('"\n')
    config = json.loads(get("/api/config"))
    stats = json.loads(get("/api/stats"))
    library = json.loads(get("/api/faces"))
    references = [(name, file) for name, files in library.items() if name != "train" for file in files]
    logging.info("Runtime %s", json.dumps({"version": version,
        "detectors": {key: value.get("type") for key, value in config.get("detectors", {}).items()},
        "face_enabled": config.get("face_recognition", {}).get("enabled"),
        "face_model_size": config.get("face_recognition", {}).get("model_size"),
        "detector_ms": {key: value.get("inference_speed") for key, value in stats.get("detectors", {}).items()},
        "reference_people": sum(bool(files) for name, files in library.items() if name != "train"),
        "reference_images": len(references)}))
    if not config.get("face_recognition", {}).get("enabled"):
        raise ValueError("Face recognition is disabled")
    blank = io.BytesIO()
    Image.new("RGB", (320, 320)).save(blank, "JPEG")
    try:
        result = frigate_candidate(blank.getvalue())
        if result["name"] is not None or result["confirmed"]:
            raise ValueError("Blank image unexpectedly matched")
        logging.info("Blank-image adapter check passed")
    except urllib.error.HTTPError as exc:
        # Report the failure shape without any names or response text.
        payload = json.loads(exc.read())
        logging.error("Blank-image adapter rejected HTTP %s; response keys=%s success=%s", exc.code, sorted(payload), payload.get("success"))
        raise ValueError("Adapter must handle Frigate's negative recognition response") from None
    if args.recognize_reference:
        if not references:
            raise ValueError("No confirmed reference image available")
        # Training crops vary in quality. Probe at most five spread across the library.
        references.sort()
        samples = []
        for i in range(min(5, len(references))):
            name, file = references[i * len(references) // min(5, len(references))]
            image = get("/clips/faces/" + urllib.parse.quote(name, safe="") + "/" + urllib.parse.quote(file, safe=""))
            samples.append((name, image))
        deadline = time.monotonic() + max(0, min(args.warmup_seconds, 600))
        while True:
            passed = False
            building = False
            for i, (name, image) in enumerate(samples):
                start = time.monotonic()
                result = frigate_candidate(image)
                matched = result["name"] == name and result["confirmed"] is False
                logging.info("Reference probe %s: matched_expected=%s returned_candidate=%s reason=%s score=%s elapsed_s=%.3f", i+1, matched, result["name"] is not None, result["reason"], result["score"], time.monotonic()-start)
                passed = passed or matched
                building = building or result["reason"] == "no_match"
            if passed:
                break
            if not building or time.monotonic() >= deadline:
                raise ValueError("No sampled reference matched its expected identity")
            # Frigate 0.16 starts its reference embedding build asynchronously on first classify.
            logging.info("No classifier match yet; allowing the cold reference build to finish")
            time.sleep(min(10, max(0, deadline-time.monotonic())))
        logging.info("Live Frigate adapter validation passed (bounded reference smoke test, not an accuracy benchmark)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        main()
    except urllib.error.HTTPError as exc:
        logging.error("Validation failed: HTTP %s on %s", exc.code, urllib.parse.urlsplit(exc.url).path)
        raise SystemExit(1) from None
    except Exception as exc:
        logging.error("Validation failed (%s)", type(exc).__name__)
        raise SystemExit(1) from None

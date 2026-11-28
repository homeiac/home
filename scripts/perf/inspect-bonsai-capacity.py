#!/usr/bin/env python3
"""Read serving slots without submitting inference or exporting media/request details."""

import argparse
import json
import logging
import os
import tempfile
import time
import urllib.request
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep a runtime credential bound to the explicitly supplied endpoint."""

    def redirect_request(
        self, req: object, fp: object, code: int, msg: str, headers: object, newurl: str
    ) -> None:
        return None


def collect(endpoint: str, key_file: Path) -> dict:
    """Return aggregate readiness/slot counts; neither active prompts nor IDs persist."""
    headers = {"Authorization": "Bearer " + key_file.read_text().strip()}
    opener = urllib.request.build_opener(NoRedirect)
    results = {}
    for name in ("health", "slots"):
        request = urllib.request.Request(
            endpoint.rstrip("/") + "/" + name, headers=headers
        )
        with opener.open(request, timeout=5) as response:
            results[name] = json.load(response)
    slots = results["slots"]
    if (
        not isinstance(slots, list)
        or not slots
        or any(not isinstance(s, dict) for s in slots)
    ):
        raise ValueError("Unexpected slot inventory")
    states = [s.get("is_processing") for s in slots]
    active = sum(states) if all(type(v) is bool for v in states) else None
    status = (
        results["health"].get("status") if isinstance(results["health"], dict) else None
    )
    return {
        "observed_ns": time.time_ns(),
        "ready": status == "ok",
        "serving_contexts": len(slots),
        "processing_contexts": active,
        "idle_contexts": len(slots) - active if active is not None else None,
        "decision": "observe_only",
        "unmeasured": [
            "caller_attribution",
            "admission_delay",
            "peer_reservations",
            "cpu_memory_io_headroom",
            "useful_output_under_added_load",
        ],
    }


def main() -> None:
    """Save a private receipt while reading runtime access material only from its file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        result = collect(args.endpoint, args.key_file)
    except (OSError, ValueError, TypeError, KeyError) as error:
        # HTTP exceptions may carry private server response text or endpoints.
        parser.exit(1, "Capacity inspection failed (" + type(error).__name__ + ").\n")
    args.output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=args.output.parent, delete=False
    ) as stream:
        json.dump(result, stream, sort_keys=True)
        temporary = Path(stream.name)
    os.replace(temporary, args.output)
    logging.getLogger(__name__).info("%s", json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

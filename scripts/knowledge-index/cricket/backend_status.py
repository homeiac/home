"""Inspect numeric Mac inference counters without exposing prompts or credentials."""

import json
import urllib.request
from pathlib import Path


def main() -> None:
    """Print only aggregate endpoint status and numeric throughput counters."""
    key = (
        (Path.home() / "Library/Application Support/knowledge-index-bonsai/server.key")
        .read_text()
        .strip()
    )
    output = {}
    for route in ("/health", "/metrics"):
        try:
            request = urllib.request.Request(
                "http://127.0.0.1:19476" + route,
                headers={"Authorization": "Bearer " + key},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read().decode()
            if route == "/health":
                output["health"] = json.loads(body)
            else:
                output["metrics"] = {}
                for line in body.splitlines():
                    if line.startswith("#") or not line.strip():
                        continue
                    name, value = line.rsplit(" ", 1)
                    if any(
                        s in name for s in ("requests", "tokens", "kv_cache", "prompt")
                    ):
                        output["metrics"][name] = float(value)
        except (OSError, ValueError) as error:
            output[route] = type(error).__name__
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info("%s", json.dumps(output))


if __name__ == "__main__":
    main()

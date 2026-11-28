#!/usr/bin/env python3
"""Evaluate complete OTLP windows as a workload adapter supplies them over JSONL stdin."""
import json
import sys
from pathlib import Path

from otel_diagnosis import predict
from shared_workloads import shared_context


def main() -> None:
    """Each adapter checkpoint is a closed capture and an explicit event-time watermark."""
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            checkpoint = json.loads(line)
            result = predict(Path(checkpoint["capture"]), int(checkpoint["as_of_unix_ns"]),
                             int(checkpoint.get("window_s", 600)))
            context = shared_context(checkpoint, int(checkpoint["as_of_unix_ns"]))
            if result["scope"] and "comparison" in checkpoint and result["scope"][0] != checkpoint["comparison"]["subject"]:
                raise ValueError("comparison subject differs from the diagnosed service")
            if context["decision"] == "eligible" and result["decision"]["state"] != "trial_proposed":
                context["decision"] = "hold"
                context["reasons"].append("insufficient diagnostic evidence")
            result = {"diagnosis": result, "fleet_review": context}
        except (KeyError, TypeError, OSError, ValueError) as error:
            # One bad checkpoint must not terminate unrelated workload adapters.
            result = {"state": "invalid_checkpoint", "error": str(error)}
        print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

"""Summarize completed Luna batches from journalctl JSON-line measurements on stdin."""
from collections import Counter
import json
import math
import statistics
import sys


def latency(values):
    if not values:
        return None
    values = sorted(values)
    return dict(median=round(statistics.median(values), 3), p95=values[math.ceil(.95 * len(values)) - 1])


def summary(batches):
    items = [item for batch in batches for item in batch["results"]]
    ok = [item for item in items if item["state"] == "ok"]
    seconds = sum(batch["total_seconds"] for batch in batches)
    cost = 0
    for item in ok:
        i, c, o = (item[field] for field in ("input_tokens", "cached_tokens", "output_tokens"))
        mult = 2 if i > 272000 else 1
        cost += ((i-c)*10*mult + c*mult + o*(75 if mult == 2 else 50) + 99)//100
    return dict(batches=len(batches), seconds=round(seconds,1), saved=len(ok),
                saved_per_minute=round(60*len(ok)/max(seconds,1),2),
                media=dict(Counter(item["kind"] for item in ok)),
                unsuccessful=dict(Counter(item["failure"] or item["state"] for item in items if item["state"] != "ok")),
                prepare=latency([i["preparation_seconds"] for i in ok]),
                request=latency([i["request_seconds"] for i in ok]),
                reserve=latency([batch["reserve_seconds"] for batch in batches]),
                publish=latency([batch["publish_seconds"] for batch in batches]),
                mean_estimated_usd_per_save=round(cost/1e6/max(1,len(ok)),6))


def main():
    levels = {}
    for line in sys.stdin:
        if line.startswith("LUNA_BATCH "):
            batch = json.loads(line.removeprefix("LUNA_BATCH "))
            setting = batch["parallel"], batch.get("frame_slots",4), batch.get("batch_size",24)
            levels.setdefault(setting, {})[batch["batch"]] = batch
    print(json.dumps({f"{parallel} requests / {frames} prep / batch {size}":summary(list(batches.values()))
                      for (parallel,frames,size),batches in sorted(levels.items())}, indent=2))


if __name__ == "__main__":
    main()

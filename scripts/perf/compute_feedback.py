"""Deterministic one-increment trial controller. Workloads own sampling and dispatch."""

import json
import math
from pathlib import Path


def choose(sample: dict, policy: dict, tried: set[str]) -> str | None:
    """Choose the pool with most free increments, after reservations, for ready work."""
    if not sample["healthy"] or sample["pending"] < policy["min_pending"]:
        return None
    eligible = [
        (room, pool)
        for pool, room in sample["room"].items()
        if pool not in tried
        and sample["safe"].get(pool, False)
        and room is not None
        and math.isfinite(room)
        and room >= 1
    ]
    return min(eligible, key=lambda item: (-item[0], item[1]))[1] if eligible else None


class Controller:
    """Advance at batch boundaries. An allocation always denotes one extra lane."""

    def __init__(self, policy: dict):
        self.p = policy
        self.tried = {}
        self.phase = "baseline"
        self.pool = None
        self.start = None
        self.rate = None
        self.wins = 0

    def decision(self, action: str, reason: str) -> dict:
        return {"action": action, "pool": self.pool, "reason": reason}

    def rollback(self, reason: str) -> dict:
        result = self.decision("rollback", reason)
        self.tried[self.pool] = self.now + self.p.get("retry_after_seconds", 1800)
        self.phase, self.pool, self.start = "baseline", None, None
        self.wins = 0
        return result

    def step(self, s: dict) -> dict:
        """Consume one snapshot; thresholds are policy, observations are measurements."""
        self.now = s["time"]
        if self.start is None:
            self.start = s
            if s.get("resume") and not self.tried:
                pool, rate, at = s["resume"]
                if (
                    s["healthy"]
                    and s["pending"] >= self.p["min_pending"]
                    and s["safe"].get(pool)
                    and (s["room"].get(pool) or 0) >= 1
                    and 0 < rate
                    and 0 <= self.now - at <= self.p["promotion_ttl_seconds"]
                ):
                    self.pool, self.rate, self.phase = pool, rate, "quality"
                    return self.decision("qualify", "requalify committed increment")
        if self.phase == "baseline":
            candidate = choose(
                s,
                self.p,
                {pool for pool, until in self.tried.items() if self.now < until},
            )
            if (
                candidate is None
                or s["errors"] != self.start["errors"]
                or s["time"] < self.start["time"]
                or s["verified"] < self.start["verified"]
            ):
                self.start = s
                return self.decision("hold", "no eligible backlog and headroom")
            elapsed = s["time"] - self.start["time"]
            count = s["verified"] - self.start["verified"]
            if elapsed < self.p["window_seconds"] or count < self.p["min_verified"]:
                return self.decision("hold", "collect verified baseline")
            self.rate = count / elapsed
            self.pool, self.phase, self.start = candidate, "quality", s
            return self.decision("qualify", "matched holdout on baseline and candidate")
        if (
            self.phase == "promoted"
            and s["healthy"]
            and s["pending"] < self.p["min_verified"]
        ):
            return self.decision("idle", "queue drained, retain proven increment")
        if not s["healthy"] or s["pending"] < self.p["min_verified"]:
            return self.rollback("unhealthy baseline or insufficient remaining work")
        if not s["safe"].get(self.pool, False):
            return self.rollback("resource reserve breached or unavailable")
        elapsed = s["time"] - self.start["time"]
        if elapsed < 0 or s["verified"] < self.start["verified"]:
            return self.rollback("clock or verified counter reset")
        if self.phase in ("quality", "recheck"):
            scores = s.get("quality")
            if scores is None:
                if elapsed > self.p["quality_timeout"]:
                    return self.rollback("qualification timed out")
                return self.decision("wait", "quality benchmark running")
            n, reference, candidate = scores
            if (
                n < self.p["min_quality_cases"]
                or not 0 <= reference <= n
                or not 0 <= candidate <= n
                or candidate < reference
                or candidate / n < self.p["quality_floor"]
            ):
                return self.rollback("matched quality gate failed")
            if self.phase == "recheck":
                self.phase, self.start = "promoted", s
                return self.decision(
                    "promote", "verified fleet gain and repeat quality gate passed"
                )
            if s["room"].get(self.pool) is None or s["room"][self.pool] < 1:
                return self.rollback("headroom changed during qualification")
            self.phase, self.start = "trial", s
            return self.decision("add", "quality passed, baseline preserved")
        if s["errors"] > self.start["errors"]:
            return self.rollback("new workload error")
        if elapsed < self.p["window_seconds"]:
            return self.decision("wait", "measure verified fleet output")
        count = s["verified"] - self.start["verified"]
        attributed = s["extra_verified"] - self.start["extra_verified"]
        if count < self.p["min_verified"] or not 0 < attributed < count:
            if elapsed < self.p["max_window_seconds"]:
                return self.decision("wait", "collect verified candidate contribution")
            return self.rollback("insufficient readbacks for attribution")
        rate = count / elapsed
        if rate <= self.rate or rate < self.rate * (1 + self.p["min_gain"]):
            return self.rollback("fleet gain below floor")
        self.wins += 1
        self.start = s
        if self.wins >= self.p["windows"] and self.phase == "trial":
            self.phase = "recheck"
            return self.decision(
                "recheck", "repeat matched quality gate before promotion"
            )
        return self.decision("keep", "verified fleet gain sustained")


def replay(path: Path, policy: dict) -> list[dict]:
    """Recompute decisions from saved workload observations only."""
    controller = Controller(policy)
    results = []
    for line in path.read_text().splitlines():
        if line:
            record = json.loads(line)
            result = controller.step(record.get("observation", record))
            if "decision" in record and result != record["decision"]:
                raise ValueError(f"Replay diverged at observation {len(results) + 1}")
            results.append(result)
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Replay trial decisions from a workload snapshot JSONL."
    )
    parser.add_argument("policy", type=Path)
    parser.add_argument("snapshots", type=Path)
    args = parser.parse_args()
    for result in replay(
        args.snapshots, json.loads(args.policy.read_text())["feedback"]
    ):
        print(json.dumps(result, sort_keys=True))

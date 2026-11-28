"""Opt-in, finite CPU canary using the existing face queue and an external pool owner."""

import argparse
import hashlib
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import sqlite3
import subprocess
import time
from urllib.parse import urlsplit
from uuid import uuid4

from library_backfill import HERE, claims, connect
from library_worker import decode, infer
from media_summary import ask_model


class PoolOwnershipLost(RuntimeError):
    """The external owner no longer permits CPU submissions."""


class ReservationLost(RuntimeError):
    """A newer job generation or changed input superseded this result."""


def check_lease(name: str, holder: str) -> None:
    """Require a current, independently read-back Kubernetes owner."""
    command = ["kubectl", "--kubeconfig", os.environ.get("KUBECONFIG", str(Path.home() / "kubeconfig")),
               "--request-timeout=8s", "-n", "default", "get", "lease", name, "-o", "json"]
    lease = json.loads(subprocess.check_output(command, text=True, timeout=12))["spec"]
    renewed = datetime.fromisoformat(lease["renewTime"].replace("Z", "+00:00")).timestamp()
    age = time.time() - renewed
    if lease.get("holderIdentity") != holder or not 0 <= age < lease["leaseDurationSeconds"]:
        raise PoolOwnershipLost("CPU pool ownership is absent or expired")


def initialize(db: sqlite3.Connection) -> None:
    """Keep CPU fencing metadata separate from the existing two-column claims."""
    with db:
        claims.initialize(db)
        db.execute("""CREATE TABLE IF NOT EXISTS cpu_face_claims (
            asset TEXT PRIMARY KEY, generation TEXT NOT NULL,
            input TEXT NOT NULL, expires REAL NOT NULL)""")


def reserve(db: sqlite3.Connection, ttl: float) -> tuple | None:
    """Reserve through the existing indexed claim, atomically adding a generation."""
    generation = "cpu:" + uuid4().hex

    def owned(asset: str, raw: str) -> None:
        db.execute("UPDATE rtx_life_stage_claims SET state=? WHERE asset=?", (generation, asset))
        db.execute("""INSERT INTO cpu_face_claims VALUES(?,?,?,?)
            ON CONFLICT(asset) DO UPDATE SET generation=excluded.generation,
            input=excluded.input,expires=excluded.expires""",
                   (asset, generation, raw, time.time() + ttl))

    row = claims.claim(db, mac_batch=0, resume=False, on_claim=owned)
    return (*row, generation) if row else None


def guard(db: sqlite3.Connection, asset: str, raw: str, generation: str) -> None:
    """Reject stale generations, changed inputs and supervisor-reset reservations."""
    row = db.execute("""SELECT 1 FROM jobs j JOIN rtx_life_stage_claims r USING(asset)
        JOIN cpu_face_claims c USING(asset)
        WHERE j.asset=? AND j.status='running' AND j.input=?
        AND r.state=? AND c.generation=? AND c.input=? AND c.expires>?""",
                     (asset, raw, generation, generation, raw, time.time())).fetchone()
    if row is None:
        raise ReservationLost("CPU face reservation changed")


def checkpoint(db: sqlite3.Connection, asset: str, raw: str, generation: str, value: dict) -> None:
    """Save resumable work only while this exact face generation is owned."""
    db.execute("BEGIN IMMEDIATE")
    with db:
        guard(db, asset, raw, generation)
        db.execute("UPDATE jobs SET outcome=? WHERE asset=?", (json.dumps(value), asset))


def finish(db: sqlite3.Connection, asset: str, raw: str, generation: str,
           state: str, value: dict) -> None:
    """Reuse the production finisher with a fenced CPU reservation."""
    db.execute("BEGIN IMMEDIATE")
    try:
        guard(db, asset, raw, generation)
        claims.finish(db, asset, state, json.dumps(value), expected_state=generation)
    except BaseException:
        db.rollback()
        raise
    if state == "pending":
        with db:
            db.execute("DELETE FROM rtx_life_stage_claims WHERE asset=? AND state='released'", (asset,))


def recover(db: sqlite3.Connection) -> int:
    """Release expired CPU generations without touching a newer GPU reservation."""
    db.execute("BEGIN IMMEDIATE")
    with db:
        rows = db.execute("""SELECT c.asset,c.generation FROM cpu_face_claims c
            JOIN rtx_life_stage_claims r USING(asset) JOIN jobs j USING(asset)
            WHERE c.expires<=? AND r.state=c.generation AND j.status='running'""",
                          (time.time(),)).fetchall()
        for asset, generation in rows:
            db.execute("UPDATE jobs SET status='pending' WHERE asset=?", (asset,))
            db.execute("DELETE FROM rtx_life_stage_claims WHERE asset=? AND state=?", (asset, generation))
    return len(rows)


def cpu_observe(args: argparse.Namespace, pictures: list[bytes], prompt: str, headers: dict) -> dict:
    """Use the production HTTP client, with guest-agent transport for still-fawn."""
    if (headers.get("x-workload-name") != "library-face-observations"
            or not headers.get("x-workload-run-id") or not headers.get("traceparent")):
        raise PoolOwnershipLost("Registered caller and trace context are required")
    extra = dict(max_tokens=160, temperature=0.1, seed=42, cache_prompt=False,
                 response_format={"type": "json_object"},
                 chat_template_kwargs={"enable_thinking": False})
    if args.backend == "mac-cpu":
        return decode(ask_model(args.endpoint, args.model, prompt, pictures,
                                timeout=args.timeout, extra=extra, headers=headers))
    # Send the exact production OpenAI request through the guest agent. No VM SSH.
    import base64
    content = [{"type": "text", "text": prompt}] + [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," +
         base64.b64encode(picture).decode()}} for picture in pictures]
    body = dict(extra, model=args.model, messages=[{"role": "user", "content": content}])
    inventory = HERE.parents[2] / "proxmox/inventory.txt"
    addresses = [line.partition("#")[0].strip() for line in inventory.read_text().splitlines()
                 if line.partition("#")[2].strip() == "still-fawn"]
    if len(addresses) != 1:
        raise ValueError("Need exactly one inventoried still-fawn host")
    forwarded = [part for key, value in headers.items() for part in ("-H", key + ": " + value)]
    remote = shlex.join(["qm", "guest", "exec", "108", "--timeout", str(args.timeout + 15),
                         "--pass-stdin", "1", "--", "curl", "-fsS", "--max-time", str(args.timeout),
                         "-H", "Content-Type: application/json", "--data-binary", "@-", *forwarded,
                         args.endpoint.rstrip("/") + "/v1/chat/completions"])
    reply = json.loads(subprocess.check_output(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "root@" + addresses[0], remote],
        input=json.dumps(body), text=True, timeout=args.timeout + 30))
    if not reply.get("exited") or reply.get("exitcode") or reply.get("out-truncated"):
        raise OSError("CPU guest inference failed")
    return decode(json.loads(reply["out-data"])["choices"][0]["message"]["content"])


def run(args: argparse.Namespace, telemetry=None) -> dict:
    """Process finite unique jobs only after explicit activation and ownership."""
    if args.lanes == 0:
        return {"enabled": False, "processed": 0}
    if telemetry is None or telemetry.session.get("workload") != "library-face-observations":
        raise ValueError("A registered photo-workload telemetry provider is required")
    resource = {"mac-cpu": "mac-m5/cpu", "still-fawn-cpu": "still-fawn/cpu"}[args.backend]
    required = {"claim", "process", "infer", "checkpoint", "write"}
    if not required.issubset(telemetry.session.get("stages", [])):
        raise ValueError("Telemetry must declare claim, process, infer, checkpoint and write")
    endpoint = urlsplit(args.endpoint or "")
    if endpoint.scheme != "http" or endpoint.hostname not in {"127.0.0.1", "localhost"} or endpoint.path not in {"", "/"} or endpoint.query or endpoint.fragment:
        raise ValueError("The bounded CPU canary requires a loopback server endpoint")
    if not all((args.model, args.profile, args.lease, args.holder, args.root)):
        raise ValueError("CPU model, profile, root and external lease owner are required")
    if not (args.root / "library.sqlite3").is_file():
        raise ValueError("An existing library checkpoint is required")

    def verify_owner() -> None:
        check_lease(args.lease, args.holder)
    verify_owner()
    telemetry.bind_configuration({
        "analysis_version": args.profile,
        "allowed_assets": None,
        "backends": {args.backend: {
            "endpoint": args.endpoint, "model": args.model, "timeout": args.timeout,
            "joint": args.joint, "seed": 42, "cache_prompt": False,
            "checkpoint": str(args.root.resolve()),
            "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }},
    })
    states = Counter()
    with closing(connect(args.root)) as db:
        initialize(db)
        recover(db)
        for _ in range(args.limit):
            if args.stop_file and args.stop_file.exists():
                break
            verify_owner()
            with telemetry.stage("claim", resource):
                reserved = reserve(db, 2 * args.timeout + 300)
                parent = telemetry.headers()
            if not reserved:
                break
            asset, raw, generation = reserved
            old, attempts = db.execute("SELECT outcome,attempts FROM jobs WHERE asset=?", (asset,)).fetchone()
            saved = {}
            called = set()
            job = dict(asset=asset, fingerprint=hashlib.sha256(raw.encode()).hexdigest(),
                       version=args.profile, execution_id=generation, attempts=attempts + 1)

            def annotate(value: dict) -> None:
                value.update(cpu_execution_profile=args.profile, cpu_model=args.model)
                for part in called:
                    if part in value:
                        value[part + "_model_profile"] = args.profile

            def observe(backend: str, url: str, pictures: list[bytes], prompt: str, schema: dict) -> dict:
                from library_worker import AGE_SCHEMA, JOINT_SCHEMA
                verify_owner()
                with telemetry.stage("infer", resource, job=job):
                    answer = cpu_observe(args, pictures, prompt, telemetry.headers())
                called.update(("stage", "action") if schema is JOINT_SCHEMA else
                              ("stage",) if schema is AGE_SCHEMA else ("action",))
                return answer

            def save(value: dict) -> None:
                verify_owner()
                with telemetry.stage("checkpoint", resource, job=job):
                    annotate(value)
                    value["trace_context"] = telemetry.headers()
                    checkpoint(db, asset, raw, generation, value)

            with telemetry.stage("process", resource, parent=parent, job=job, whole_job=True):
                try:
                    saved.update(json.loads(old or "{}"))
                    if "stage" in saved:
                        saved.setdefault("stage_model_profile", saved.get("model_profile", "legacy-unspecified"))
                    if saved.get("reviewed_action"):
                        saved.setdefault("action_model_profile", "reviewed-unchanged")
                    state, value = infer(json.loads(raw), args.backend, args.endpoint, saved, save,
                                         joint=args.joint, observer=observe)
                    annotate(value)
                    verify_owner()
                    with telemetry.stage("write", resource, job=job):
                        value["trace_context"] = telemetry.headers()
                        finish(db, asset, raw, generation, state, value)
                except (OSError, ValueError, KeyError, TypeError, IndexError, RuntimeError, subprocess.SubprocessError) as error:
                    # Fencing also applies during cleanup. A newer owner must win.
                    try:
                        invalid = isinstance(error, (ValueError, KeyError, TypeError, IndexError))
                        state = "withheld" if invalid and attempts >= 1 else "pending"
                        saved["reason"] = type(error).__name__
                        db.execute("BEGIN IMMEDIATE")
                        with db:
                            guard(db, asset, raw, generation)
                            db.execute("UPDATE jobs SET attempts=attempts+? WHERE asset=?", (int(invalid), asset))
                        finish(db, asset, raw, generation, state, saved)
                    except ReservationLost:
                        db.rollback()
                        recover(db)
                        raise
                    if not invalid:
                        raise
                    states[state] += 1
                    (args.root / "progress").touch()
                    continue
                states[state] += 1
                (args.root / "progress").touch()
    return {"enabled": True, "processed": sum(states.values()), "states": dict(states)}


def main() -> None:
    """Default to no CPU claims and require finite limits for explicit canaries."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lanes", type=int, choices=(0, 1), default=0)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--backend", choices=("mac-cpu", "still-fawn-cpu"), default="mac-cpu")
    parser.add_argument("--endpoint")
    parser.add_argument("--model")
    parser.add_argument("--profile")
    parser.add_argument("--lease")
    parser.add_argument("--holder")
    parser.add_argument("--limit", type=int, choices=range(1, 101), default=1)
    parser.add_argument("--timeout", type=int, choices=range(1, 901), default=100)
    parser.add_argument("--joint", action="store_true")
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--telemetry-session", type=Path)
    args = parser.parse_args()
    if args.lanes == 0:
        print(json.dumps(run(args)))
        return
    if args.telemetry_session is None:
        parser.error("An existing --telemetry-session is required for activation")
    try:
        from cricket.telemetry import RunTelemetry
    except ImportError:
        parser.error("Install the existing shared RunTelemetry runtime before activation")
    telemetry = RunTelemetry(args.telemetry_session, workload="library-face-observations")
    try:
        result = run(args, telemetry)
    finally:
        telemetry.close_window(args.telemetry_session.parent / "closed-telemetry")
        telemetry.shutdown()
    print(json.dumps(result))


if __name__ == "__main__":
    main()

"""Submit archived video frames to Immich and retain every native face ID privately.

Uses the existing sync pod's mounted API key; no credentials leave the pod.
Uploads are content-deduplicated by Immich and checkpointed after each response.
Run again to refresh recognition/person assignments without rerunning detection.
"""

import argparse
import base64
import fcntl
import hashlib
import io
import json
import logging
import re
import struct
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from .face_context import identifier, normalize
from .ledger import Ledger
from .prepare import save_private

BRIDGE = r"""
import fs from 'node:fs/promises';
const key=(await fs.readFile('/credentials/api-key','utf8')).trim();
const base=process.env.IMMICH_URL||'http://immich-server:2283/api';
async function call(path,options={}){
 const r=await fetch(base+path,{...options,headers:{'x-api-key':key,...options.headers},signal:AbortSignal.timeout(60000)});
 if(!r.ok)throw Error('Immich HTTP '+r.status+' '+(options.method||'GET')+' '+path.split('/').slice(0,2).join('/'));
 return r.status===204?null:r.json();
}
const original=await call('/assets/'+encodeURIComponent(packet.asset));
if(original.ownerId!==packet.owner)throw Error('Source owner mismatch');
const me=await call('/users/me');
if(me.id!==packet.owner)throw Error('Upload owner mismatch');
let id=packet.frame_asset;
if(!id){
 const form=new FormData();
 form.set('assetData',new Blob([Buffer.from(packet.image,'base64')],{type:'image/jpeg'}),'cricket-frame-'+packet.key+'.jpg');
 form.set('fileCreatedAt',original.fileCreatedAt);form.set('fileModifiedAt',original.fileCreatedAt);
 form.set('visibility','archive');
 const result=await call('/assets',{method:'POST',body:form});id=result.id;
}
const info=await call('/assets/'+encodeURIComponent(id));
if(info.ownerId!==packet.owner)throw Error('Frame owner mismatch');
const faces=await call('/faces?id='+encodeURIComponent(id));
console.log(JSON.stringify({frame_asset:id,visibility:info.visibility,faces}));
"""


def kubectl(deployment: str) -> list[str]:
    """Use the shared kubeconfig and known Immich namespace, never SSH to a VM."""
    return [
        "kubectl",
        "--kubeconfig",
        str(Path.home() / "kubeconfig"),
        "-n",
        "immich-pilot",
        "exec",
        "-i",
        "deploy/" + deployment,
        "--",
    ]


def request(packet: dict) -> dict:
    """Upload/read one frame using scoped credentials already mounted inside the pod."""
    result = subprocess.run(
        kubectl("immich-sync") + ["node", "--input-type=module", "-"],
        input="const packet=" + json.dumps(packet) + ";\n" + BRIDGE,
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
    )
    if result.returncode:
        match = re.search(
            r"Error: (Immich HTTP \d+ [A-Z]+ /[a-z]+|Source owner mismatch|Upload owner mismatch|Frame owner mismatch)",
            result.stderr,
        )
        raise RuntimeError(match[1] if match else "Immich frame bridge failed")
    value = json.loads(result.stdout)
    identifier(value["frame_asset"])
    if value["visibility"] != "archive" and not packet.get("original_photo"):
        raise ValueError("Analysis frame is not archived")
    return value


def completed(asset_ids: list[str], owner: str) -> set[str]:
    """Read native detection completion; an empty result alone is not success."""
    if not asset_ids:
        return set()
    ids = ",".join("'" + identifier(value) + "'" for value in asset_ids)
    owner = identifier(owner)
    sql = f"""SELECT a.id FROM asset a JOIN asset_job_status j ON j."assetId"=a.id
WHERE a."ownerId"='{owner}' AND a.id IN ({ids}) AND j."facesRecognizedAt" IS NOT NULL AND a."deletedAt" IS NULL"""
    result = subprocess.run(
        kubectl("immich-postgres")
        + [
            "psql",
            "-XAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "immich",
            "-d",
            "immich",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return {identifier(line) for line in result.stdout.splitlines() if line}


def frame_bytes(image: str, key: str) -> str:
    """Add a deterministic JPEG provenance comment without changing any pixels.

    Makes different source/timestamp instances distinct even for identical frames;
    retries of the same frame remain byte-identical and deduplicate in Immich.
    """
    raw = base64.b64decode(image, validate=True)
    if not raw.startswith(b"\xff\xd8"):
        raise ValueError("Expected a JPEG evidence frame")
    comment = ("cricket-frame-v1:" + key).encode()
    return base64.b64encode(
        raw[:2] + b"\xff\xfe" + struct.pack(">H", len(comment) + 2) + comment + raw[2:]
    ).decode()


def frame_key(asset: dict, stamp: float | None, image: str) -> str:
    """Identify the exact prepared image and source used for a native upload."""
    return hashlib.sha256(
        json.dumps(
            [asset["owner"], asset["id"], asset["fingerprint"], stamp, image],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def synchronize(
    asset: dict, prepared: dict, folder: Path, *, max_frames: int = 0
) -> dict:
    """Checkpoint each frame independently; never assign unnamed detections to Adil."""
    path = folder / "faces" / (asset["id"] + ".json")
    value = (
        json.loads(path.read_text())
        if path.exists()
        else {
            "owner": asset["owner"],
            "asset": asset["id"],
            "fingerprint": asset["fingerprint"],
            "frames": [],
        }
    )
    if value["owner"] != asset["owner"] or value["fingerprint"] != asset["fingerprint"]:
        raise ValueError("Face registry source changed; retain old registry for review")
    prior = {r["timestamp"]: r for r in value["frames"]}
    value["identity_context"] = prepared.get("identity_context", {})
    frames = {
        stamp: image
        for w in prepared["windows"]
        for stamp, image in zip(w["positions"], w["frames"], strict=True)
    }
    for index, (stamp, image) in enumerate(sorted(frames.items())):
        if max_frames and index >= max_frames:
            break
        key = frame_key(asset, stamp, image)
        old = prior.get(stamp, {})
        if old and old.get("key") != key:
            raise ValueError("Prepared frame changed; retain prior native IDs")
        original_photo = asset["kind"] == "photo"
        packet = {
            "asset": asset["id"],
            "owner": asset["owner"],
            "key": key,
            "frame_asset": asset["id"] if original_photo else old.get("frame_asset"),
            "original_photo": original_photo,
        }
        if not packet["frame_asset"]:
            packet["image"] = frame_bytes(image, key)
        response = request(packet)
        with Image.open(io.BytesIO(base64.b64decode(image, validate=True))) as source:
            width, height = source.size
        prior[stamp] = {
            "timestamp": stamp,
            "key": key,
            "frame_asset": response["frame_asset"],
            "state": "pending",
            "faces": normalize(response["faces"]),
            "image_width": width,
            "image_height": height,
        }
        value["frames"] = list(prior.values())
        save_private(path, value)
    done = completed([r["frame_asset"] for r in value["frames"]], asset["owner"])
    # Re-read after the completion marker: the initial read may have raced detection.
    for frame in value["frames"]:
        if frame["frame_asset"] in done:
            response = request(
                {
                    "asset": asset["id"],
                    "owner": asset["owner"],
                    "frame_asset": frame["frame_asset"],
                    "original_photo": asset["kind"] == "photo",
                }
            )
            frame["faces"] = normalize(response["faces"])
            frame["state"] = "detected"
    value["expected_frames"] = len(frames)
    value["detection_complete"] = len(prior) == len(frames) and all(
        f["state"] == "detected" for f in value["frames"]
    )
    save_private(path, value)
    return {
        "frames": len(value["frames"]),
        "pending": sum(f["state"] != "detected" for f in value["frames"]),
        "faces": sum(len(f["faces"]) for f in value["frames"]),
        "complete": value["detection_complete"],
    }


def main() -> None:
    """Bound upload work independently from the existing production model workers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument(
        "--policy",
        type=Path,
        required=True,
        help='Hot-reloaded JSON: {"workers":4,"enabled":true}; bound 0..4',
    )
    parser.add_argument("--asset", help="Restrict pilot to one source asset")
    parser.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Pilot cap per asset; zero processes all prepared frames",
    )
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.max_frames < 0 or args.limit < 0:
        parser.error("Pilot limits must be nonnegative")
    args.evidence.joinpath("faces").mkdir(exist_ok=True, mode=0o700)
    fence = args.evidence.joinpath("faces", "sync.lock").open("a")
    fcntl.flock(fence, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with Ledger(args.ledger).connect() as db:
        assets = [
            dict(r)
            for r in db.execute("SELECT * FROM assets ORDER BY kind DESC,id")
            if not args.asset or r["id"] == args.asset
        ]
    if args.asset and len(assets) != 1:
        parser.error("Pilot asset not found")
    if args.limit:
        assets = assets[: args.limit]
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import time
    from concurrent.futures import FIRST_COMPLETED, wait

    waiting = iter(assets)
    running = set()
    exhausted = False
    with ThreadPoolExecutor(max_workers=4) as pool:
        while running or not exhausted:
            policy = json.loads(args.policy.read_text())
            count = policy["workers"]
            if (
                type(count) is not int
                or not 0 <= count <= 4
                or type(policy["enabled"]) is not bool
            ):
                raise ValueError("Invalid face upload policy")
            desired = count if policy["enabled"] else 0
            while not exhausted and len(running) < desired:
                asset = next(waiting, None)
                if asset is None:
                    exhausted = True
                    break
                prepared = json.loads(
                    (args.evidence / (asset["id"] + ".json")).read_text()
                )
                running.add(
                    pool.submit(
                        synchronize,
                        asset,
                        prepared,
                        args.evidence,
                        max_frames=args.max_frames,
                    )
                )
            if running:
                done, running = wait(running, timeout=2, return_when=FIRST_COMPLETED)
                for future in done:
                    logging.getLogger(__name__).info("%s", json.dumps(future.result()))
            elif not exhausted:
                time.sleep(2)


if __name__ == "__main__":
    main()

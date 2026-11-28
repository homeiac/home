"""Attach capture-date age context to private evidence without guessing from appearance."""

import argparse
import datetime as dt
import json
import logging
import subprocess
from pathlib import Path

from .evidence import fingerprint
from .importer import select_album, select_person
from .prepare import save_private


def age_context(
    asset: dict, birth_date: str | None, *, today: dt.date | None = None
) -> dict:
    """Calculate age from recorded dates; missing, contradictory or impossible dates stay unknown."""
    exif = (asset.get("exifInfo") or {}).get("dateTimeOriginal")
    raw = exif or asset.get("fileCreatedAt")
    result = {
        "recorded_date": None,
        "date_basis": "exif_original" if exif else "immich_capture_date",
        "age_years": None,
        "age_months": None,
        "status": "unavailable",
    }
    try:
        captured = dt.date.fromisoformat(raw[:10])
        born = dt.date.fromisoformat(birth_date[:10])
    except (TypeError, ValueError):
        return result
    result["recorded_date"] = captured.isoformat()
    if captured < born or captured > (today or dt.date.today()):
        return {**result, "status": "invalid_dates"}
    if exif and asset.get("fileCreatedAt"):
        try:
            alternate = dt.date.fromisoformat(asset["fileCreatedAt"][:10])
            if abs((alternate - captured).days) > 1:
                return {**result, "status": "conflicting_dates"}
        except ValueError:
            pass
    months = (
        (captured.year - born.year) * 12
        + captured.month
        - born.month
        - (captured.day < born.day)
    )
    if months > 120 * 12:
        return {**result, "status": "invalid_dates"}
    return {
        **result,
        "age_years": months // 12,
        "age_months": months % 12,
        "status": "known",
    }


def attach(prepared: dict, context: dict) -> dict:
    """Version age inputs independently; rerunning attachment is idempotent."""
    base = prepared.get("age_base_cache_key", prepared["cache_key"])
    prepared["age_base_cache_key"] = base
    prepared["identity_context"] = context
    prepared["cache_key"] = fingerprint({"base": base, "identity_context": context})
    for window in prepared["windows"]:
        window["identity_context"] = context
    return prepared


def birth_date(person: str) -> str | None:
    """Read the person's saved birthday through the existing authenticated Immich pod."""
    script = (
        "const person="
        + json.dumps(person)
        + """;
import fs from 'node:fs/promises';
const key=(await fs.readFile('/credentials/api-key','utf8')).trim();
const base=process.env.IMMICH_URL||'http://immich-server:2283/api';
const response=await fetch(base+'/people/'+encodeURIComponent(person),{headers:{'x-api-key':key},signal:AbortSignal.timeout(30000)});
if(!response.ok)throw Error('Immich HTTP '+response.status);
const p=await response.json();console.log(JSON.stringify(p.birthDate??null));
"""
    )
    result = subprocess.run(
        [
            "kubectl",
            "--kubeconfig",
            str(Path.home() / "kubeconfig"),
            "-n",
            "immich-pilot",
            "exec",
            "-i",
            "deploy/immich-sync",
            "--",
            "node",
            "--input-type=module",
            "-",
        ],
        input=script,
        text=True,
        capture_output=True,
        check=True,
        timeout=60,
    )
    return json.loads(result.stdout)


def main() -> None:
    """Refresh all prepared assets using private metadata and the saved person's birthday."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--album-name", default="All cricket videos")
    parser.add_argument("--person-name", default="Adil")
    args = parser.parse_args()
    album = select_album(json.loads(args.inventory.read_text()), args.album_name)
    person = select_person(album["people"], args.person_name)
    born = birth_date(person)
    counts = {}
    for asset in album["assets"]:
        path = args.folder / (asset["id"] + ".json")
        if not path.is_file():
            continue
        context = age_context(asset, born)
        counts[context["status"]] = counts.get(context["status"], 0) + 1
        save_private(path, attach(json.loads(path.read_text()), context))
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info("%s", json.dumps(counts))


if __name__ == "__main__":
    main()

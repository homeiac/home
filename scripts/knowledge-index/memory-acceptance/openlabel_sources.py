"""Read back current IDs and regions for an existing private album acceptance bundle."""

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from contextlib import closing
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from uuid import UUID

from review_openlabel import read


def snapshot(root: Path, pg, api_js, photo_url: str, immich_url: str, sync_journey: bool = False) -> dict:
    """Use the album's existing read-only clients to check scope and exact face bindings."""
    owner, library = (str(UUID(v)) for v in read(root/"scope.json"))
    album = str(UUID(read(root/"album-after-owner-correction.json")["id"]))
    live = api_js(f"""const me=await api('/users/me'), a=await api('/albums/{album}');
        console.log(JSON.stringify({{private: me.id==='{owner}' && a.albumUsers.some(u=>u.role==='owner' && u.user.id===me.id) &&
        !a.shared && !a.hasSharedLink && a.albumUsers.every(u=>u.role==='owner' && u.user.id===me.id),
        count:a.assetCount}}));""")
    if not live["private"]:
        raise ValueError("Live album owner or visibility changed")
    live["members"] = pg(f'''SELECT to_json("assetId") FROM album_asset WHERE "albumId"='{album}' ORDER BY "assetId"''')
    if len(live["members"]) != live["count"]:
        raise ValueError("Album changed during readback")
    frozen = set(read(root/"album-after-owner-correction.json")["members"])
    types = read(root/"album-life-stage-pilot/composite-types.json")
    collages = {asset for asset in frozen if types.get(asset, {}).get("type") == "Collage"}
    actual = set(live["members"])
    if actual - frozen or (frozen - collages) - actual:
        raise ValueError("Journey membership changed outside the reviewed collage set")
    if collages:
        ids = ",".join("'" + str(UUID(a)) + "'" for a in sorted(collages))
        authorized = pg(f"""SELECT to_json(id) FROM asset WHERE id IN ({ids}) AND "ownerId"='{owner}'
                         AND "libraryId"='{library}' AND "deletedAt" IS NULL AND NOT "isOffline" """)
        if set(authorized) != collages:
            raise ValueError("A catalogue original changed scope or availability")
    if sync_journey and (remove := sorted(actual & collages)):
        # Changes album membership only. The original assets and all face rows remain accessible.
        if any(not (root/"collage-layouts"/(asset+".json")).is_file() for asset in remove):
            raise ValueError("Catalogue the reviewed components before updating the private journey")
        api_js(f"""await api('/albums/{album}/assets','DELETE',{{ids:{json.dumps(remove)}}});
                   console.log(JSON.stringify(true));""")
        actual = set(pg(f"""SELECT to_json("assetId") FROM album_asset WHERE "albumId"='{album}'"""))
        if actual != frozen - collages:
            raise ValueError("Journey membership readback differs from the expected set")
    live.update(journey_members=sorted(actual), members=sorted(frozen), count=len(actual))
    reviewed = read(root/"album-life-stage-pilot/group-actions/verified-actions.json")
    assets = {str(UUID(row["asset"])) for row in reviewed}
    if not assets or not assets.issubset(live["members"]):
        raise ValueError("Current album no longer includes the pilot set")
    if (root / "album-reviewed-spans.json").is_file():
        assets.update(str(UUID(a)) for a in read(root/"album-reviewed-spans.json"))
        if assets != set(live["members"]) or assets != set(read(root/"album-after-owner-correction.json")["members"]):
            raise ValueError("Refresh the private album membership and span review")
    asset_list = ",".join("'" + a + "'" for a in sorted(assets))
    native = pg(f"""SELECT json_build_array(a.id, substr(a."originalPath",19), e."fileSizeInByte", f.id,
        p."personGroupId", p.name, f."boundingBoxX1"::float/f."imageWidth",
        f."boundingBoxY1"::float/f."imageHeight", f."boundingBoxX2"::float/f."imageWidth",
        f."boundingBoxY2"::float/f."imageHeight") FROM asset a JOIN asset_exif e ON e."assetId"=a.id
        JOIN asset_face f ON f."assetId"=a.id LEFT JOIN person p ON p."personGroupId"=f."personGroupId"
        AND p."ownerId"=f."ownerId" WHERE a.id IN ({asset_list}) AND a."libraryId"='{library}'
        AND a."ownerId"='{owner}' AND f."ownerId"=a."ownerId" AND a."deletedAt" IS NULL
        AND NOT a."isOffline" AND (f."personGroupId" IS NULL OR NOT p."isHidden") AND f."deletedAt" IS NULL AND f."isVisible"
        AND f."imageHeight">0 AND f."imageWidth">0""")
    names, regions = {}, defaultdict(list)
    inputs = {r["id"]: r for r in read(root/"pool.json") if r["id"] in assets}
    for asset, path, size, face, person, name, *box in native:
        if (inputs[asset]["path"], inputs[asset]["size"]) != (path, size):
            raise ValueError("Asset changed since review")
        if person:
            names[person] = name
        regions[asset].append(dict(namespace="immich", face_id=face, person_id=person, box=box))
    dbpath = root/"nikhil-life-stage-backfill/jobs.sqlite3"
    with closing(sqlite3.connect(dbpath.as_uri()+"?mode=ro", uri=True)) as db:
        for asset in sorted(assets):
            rows = db.execute("""SELECT label,face_id,action_parts FROM face_actions WHERE asset=?
                AND face_namespace='photo-index'""", (asset,)).fetchall()
            if not rows:
                continue
            url = photo_url.rstrip("/")+"/api/photo?"+urlencode({"path": inputs[asset]["path"]})
            with urlopen(url, timeout=20) as response:
                detail = json.load(response)
            if detail["size_bytes"] != inputs[asset]["size"]:
                raise ValueError("Local photo changed since review")
            faces = {str(face["id"]): face for face in detail["faces"]}
            for label, fid, raw in rows:
                face = faces[fid]
                if face["label_source"] != "user" or face["person"] != label:
                    raise ValueError("Local face no longer has its reviewed assignment")
                names["photo-index:"+fid] = face["person"]
                ref = json.loads(raw)[0]
                if ref["person_id"]:
                    pid = str(UUID(ref["person_id"]))
                    match = pg(f"""SELECT to_json(name) FROM person WHERE "ownerId"='{owner}'
                        AND "personGroupId"='{pid}' AND NOT "isHidden" """)
                    if len(match) != 1:
                        raise ValueError("Local face's referenced Immich identity changed")
                    names[pid] = match[0]
                regions[asset].append(dict(namespace="photo-index", face_id=fid,
                                           person_id=ref["person_id"], box=face["box"]))
    return dict(album=album, album_url=immich_url.rstrip("/")+"/albums/"+album,
                regions=regions, names=names, **live)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("album_directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sync-journey", action="store_true", help="Remove catalogued collages from the private Immich album")
    parser.add_argument("--photos", default="https://photos.app.home.panderosystems.com")
    parser.add_argument("--immich", default="https://immich.app.home.panderosystems.com")
    args = parser.parse_args()
    # Use the same authenticated access and scope as the private album's delivery runner.
    root = args.album_directory.resolve()
    sys.path.insert(0, str(root/"reproduction"))
    from common import pg, api_js
    os.umask(0o077)
    result = snapshot(root, pg, api_js, args.photos, args.immich, args.sync_journey)
    args.output.write_text(json.dumps(result))

"""Publish visually reviewed asset IDs to a private, owner-scoped Immich album."""

import argparse
import fcntl
import json
from pathlib import Path
import sys
from uuid import UUID


def scoped_assets(pg, owner, library, person, ids):
    """Require a current visible native face label for every reviewed image."""
    literals = ",".join(f"'{UUID(asset)}'" for asset in ids)
    return set(
        pg(
            f"""
        SELECT to_json(a.id) FROM asset a
        WHERE a.id IN ({literals}) AND a."ownerId"='{UUID(owner)}'
          AND a."libraryId"='{UUID(library)}' AND a.type='IMAGE'
          AND a.visibility='timeline' AND NOT a."isOffline" AND a."deletedAt" IS NULL
          AND EXISTS (SELECT 1 FROM asset_face f JOIN person p
             ON p."personGroupId"=f."personGroupId" AND p."ownerId"=f."ownerId"
             WHERE f."assetId"=a.id AND f."ownerId"=a."ownerId" AND f."isVisible"
               AND f."deletedAt" IS NULL AND NOT p."isHidden" AND p."personGroupId"='{UUID(person)}')
    """
        )
    )


PUBLISH = """
const me=await api('/users/me');
if(me.id!==owner) throw Error('Album owner changed');
const matches=(await api('/albums')).filter(a=>a.albumName===title);
if(matches.length>1) throw Error('Ambiguous album title');
let album=matches[0];
if(album) {
  album=await api('/albums/'+album.id);
  if(album.description!==description) throw Error('Title belongs to an existing album');
}
function checkPrivacy(a) {
  if(a.albumUsers.length!==1 || a.shared || a.hasSharedLink ||
     a.albumUsers.some(u=>u.role!=='owner'||u.user.id!==owner)) throw Error('Album is not private to owner');
}
if((album?.id??null)!==existing) throw Error('Album changed since verification');
const created=!album;
if(!album) album=await api('/albums','POST',{albumName:title,description,assetIds:ids});
album=await api('/albums/'+album.id);
checkPrivacy(album);
const missing=ids.filter(id=>!prior.includes(id));
if(!created && missing.length) await api('/albums/'+album.id+'/assets','PUT',{ids:missing});
album=await api('/albums/'+album.id);
checkPrivacy(album);
console.log(JSON.stringify({id:album.id,order:album.order,created,count:album.assetCount}));
"""


def publish(pilot: Path, selection: Path) -> dict:
    """Verify before writing, preserve prior album members and check the readback."""
    sys.path.insert(0, str(pilot / "reproduction"))
    from common import pg, api_js

    owner, library = json.loads((pilot / "scope.json").read_text())
    spec = json.loads(selection.read_text())
    ids = list(dict.fromkeys(str(UUID(i)) for i in spec["ids"]))
    if not ids or scoped_assets(pg, owner, library, spec["person"], ids) != set(ids):
        raise ValueError("Empty selection or changed face assignments")
    matches = api_js(
        "const title="
        + json.dumps(spec["title"])
        + ";console.log(JSON.stringify((await api('/albums')).filter(a=>a.albumName===title).map(a=>a.id)))"
    )
    if len(matches) > 1:
        raise ValueError("Ambiguous album title")
    existing = matches[0] if matches else None
    prior = (
        pg(
            f"""SELECT to_json("assetId") FROM album_asset WHERE "albumId"='{UUID(existing)}'"""
        )
        if existing
        else []
    )
    intent = dict(
        existing=existing,
        prior=prior,
        owner=owner,
        ids=ids,
        title=spec["title"],
        description=spec["description"],
    )
    result = api_js(
        "const {owner,ids,title,description,existing,prior}="
        + json.dumps(intent)
        + ";"
        + PUBLISH
    )
    members = pg(
        f"""SELECT to_json("assetId") FROM album_asset WHERE "albumId"='{UUID(result["id"])}'"""
    )
    expected = set(prior) | set(ids)
    if set(members) != expected or len(members) != result["count"]:
        raise ValueError("Album verification failed")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pilot", type=Path)
    ap.add_argument(
        "selection",
        type=Path,
        help="Private reviewed JSON with person, title, description and asset IDs",
    )
    args = ap.parse_args()
    with args.selection.open() as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        print(json.dumps(publish(args.pilot, args.selection)))

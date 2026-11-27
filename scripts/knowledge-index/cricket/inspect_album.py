"""Read cricket album counts through the existing authenticated Immich sync pod."""

import argparse
import json
import os
import subprocess
from pathlib import Path

SCRIPT = r"""
import fs from 'node:fs/promises';
const key=(await fs.readFile('/credentials/api-key','utf8')).trim();
const base=process.env.IMMICH_URL||'http://immich-server:2283/api';
async function api(route,body){
  const r=await fetch(base+route,{method:body?'POST':'GET',headers:{'x-api-key':key,'content-type':'application/json'},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(60000)});
  if(!r.ok)throw Error('Immich HTTP '+r.status);
  return r.json();
}
const me=await api('/users/me');
const choices=(await api('/albums')).filter(a=>a.albumName.toLowerCase().includes(config.name.toLowerCase()));
const results=[];const people=[];
if(config.inventory){for(let page=1;page<=100;page++){
  const response=await api('/people?size=1000&page='+page);
  people.push(...(response.people??[]).filter(p=>p.name).map(p=>({id:p.id,name:p.name})));
  if(!response.hasNextPage)break;
  if(page===100)throw Error('People pagination overflow');
}}
for(const choice of choices){
  const album=await api('/albums/'+encodeURIComponent(choice.id));
  const assets=[];let page=1,cursor;
  for(let iteration=0;iteration<1000;iteration++){
    const response=await api('/search/metadata',{albumIds:[album.id],withExif:true,size:1000,...(cursor?{cursor}:{page})});
    assets.push(...response.assets.items);
    if(!response.assets.nextCursor&&!response.assets.nextPage)break;
    cursor=response.assets.nextCursor;if(!cursor)page=Number(response.assets.nextPage);
    if(iteration===999)throw Error('Pagination overflow');
  }
  const owner=album.albumUsers?.find(x=>x.role==='owner')?.user?.id??album.ownerId??album.owner?.id;
  const unique=new Map(assets.map(a=>[a.id,a]));
  const counts={};for(const a of unique.values())counts[a.type]=(counts[a.type]||0)+1;
  results.push({id:album.id,name:album.albumName,owner,ownerMatches:owner===me.id,reportedCount:album.assetCount,
    total:unique.size,counts,duplicateEntries:assets.length-unique.size,
    ...(config.inventory?{assets:[...unique.values()],people}:{})});
}
console.log(JSON.stringify(results));
"""


def main() -> None:
    """Report counts and optionally save full album metadata outside the repository."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="cricket")
    parser.add_argument(
        "--inventory", type=Path, help="Private output path for album metadata"
    )
    args = parser.parse_args()
    config = {"name": args.name, "inventory": bool(args.inventory)}
    command = [
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
    ]
    result = subprocess.run(
        command,
        input="const config=" + json.dumps(config) + ";\n" + SCRIPT,
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
    albums = json.loads(result.stdout)
    if args.inventory:
        args.inventory.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.inventory, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(albums, output)
    summary = [
        {k: v for k, v in a.items() if k not in {"assets", "people", "owner", "id"}}
        for a in albums
    ]
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info("%s", json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

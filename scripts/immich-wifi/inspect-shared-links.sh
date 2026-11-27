#!/usr/bin/env bash
# Read only: discover whether an existing unexpired album link can be tested.
# Keep API keys, shared-link keys, and photo metadata inside the running pod.
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
kubectl --request-timeout=20s -n immich-pilot exec deployment/immich-sync -- node -e '
const fs=require("fs");
(async()=>{
  const key=fs.readFileSync("/credentials/api-key","utf8").trim();
  const r=await fetch("http://immich-server:2283/api/shared-links",{headers:{"x-api-key":key}});
  if(!r.ok){console.log("Shared-link inventory HTTP "+r.status);process.exitCode=1;return;}
  const links=await r.json();
  const available=links.filter(x=>(!x.expiresAt||Date.parse(x.expiresAt)>Date.now())&&!x.password&&x.album);
  console.log(JSON.stringify({existingLinks:links.length,testableAlbumLinks:available.length}));
})().catch(()=>{console.error("Shared-link inventory failed; no private data logged");process.exitCode=1;});'

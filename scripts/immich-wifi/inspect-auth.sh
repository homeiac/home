#!/usr/bin/env bash
# Read public authentication capabilities without exposing credentials or users.
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
kubectl --request-timeout=20s -n immich-pilot exec deployment/immich-sync -- node -e '
(async()=>{
  const r=await fetch("http://immich-server:2283/api/server/features");
  if(!r.ok) throw new Error("HTTP "+r.status);
  const f=await r.json();
  console.log(JSON.stringify({oauth:f.oauth,passwordLogin:f.passwordLogin,configFile:f.configFile},null,2));
})().catch(e=>{console.error(e.message);process.exitCode=1;});'

# Optionally compare the synchronization API key owner to an expected email.
# Only print match/role flags, never names, email addresses, keys, or OAuth IDs.
if [[ -n "${1:-}" ]]; then
  kubectl --request-timeout=20s -n immich-pilot exec deployment/immich-sync -- node -e '
  const fs=require("fs");
  (async()=>{
    const key=fs.readFileSync("/credentials/api-key","utf8").trim();
    const r=await fetch("http://immich-server:2283/api/users/me",{headers:{"x-api-key":key}});
    if(!r.ok) throw new Error("Account check HTTP "+r.status);
    const u=await r.json();
    console.log(JSON.stringify({expectedEmailMatches:u.email?.trim().toLowerCase()===process.argv[1].trim().toLowerCase(),isAdmin:u.isAdmin,googleOrOtherOAuthLinked:!!u.oauthId},null,2));
  })().catch(e=>{console.error(e.message);process.exitCode=1;});' "$1"
fi

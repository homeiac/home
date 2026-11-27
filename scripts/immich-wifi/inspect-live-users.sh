#!/usr/bin/env bash
# Read-only account investigation. Never select passwords, OAuth subjects,
# session tokens, or API keys. Account output is private and must not enter Git.
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
if [[ "${1:-}" == --sharing ]]; then
  kubectl --request-timeout=20s -n immich-pilot exec -i deployment/immich-postgres -- psql -X -U immich -d immich -v ON_ERROR_STOP=1 <<'SQL'
BEGIN READ ONLY;
SELECT a."albumName", u.name, u.email, au.role,
       au."createdAt" AT TIME ZONE 'America/Los_Angeles' AS shared_local
FROM album_user au JOIN album a ON a.id=au."albumId"
JOIN public."user" u ON u.id=au."userId"
WHERE a."deletedAt" IS NULL AND u."deletedAt" IS NULL
ORDER BY a."albumName", au.role, u.name;
SELECT owner.name AS shared_by, recipient.name AS shared_with,
       p."inTimeline", p."createdAt" AT TIME ZONE 'America/Los_Angeles' AS shared_local
FROM partner p JOIN public."user" owner ON owner.id=p."sharedById"
JOIN public."user" recipient ON recipient.id=p."sharedWithId";
COMMIT;
SQL
  exit
fi
kubectl --request-timeout=20s -n immich-pilot get secret immich-immich-config -o json | python3 -c '
import base64,json,sys,yaml
s=json.load(sys.stdin)
c=yaml.safe_load(base64.b64decode(s["data"]["immich-config.yaml"]))
o=c.get("oauth",{})
print(json.dumps({"oauthEnabled":o.get("enabled"),"autoRegister":o.get("autoRegister"),"issuer":o.get("issuerUrl"),"passwordLogin":c.get("passwordLogin",{}).get("enabled")},indent=2))'
kubectl --request-timeout=20s -n immich-pilot exec -i deployment/immich-postgres -- psql -X -U immich -d immich -v ON_ERROR_STOP=1 <<'SQL'
BEGIN READ ONLY;
SELECT u.email, u.name, u."isAdmin", u.status,
       COALESCE(u."oauthId", '') <> '' AS oauth_linked,
       u."createdAt" AT TIME ZONE 'America/Los_Angeles' AS created_local,
       u."updatedAt" AT TIME ZONE 'America/Los_Angeles' AS updated_local,
       count(s.id) AS sessions,
       max(s."createdAt") AT TIME ZONE 'America/Los_Angeles' AS last_session_created_local
FROM public."user" u LEFT JOIN public.session s ON s."userId"=u.id
WHERE u."deletedAt" IS NULL
GROUP BY u.id ORDER BY u."createdAt";
SELECT u.email, s."deviceType", s."deviceOS", s."appVersion",
       s."createdAt" AT TIME ZONE 'America/Los_Angeles' AS created_local,
       s."updatedAt" AT TIME ZONE 'America/Los_Angeles' AS updated_local,
       s."expiresAt" IS NULL AS no_explicit_expiry
FROM public.session s JOIN public."user" u ON u.id=s."userId"
WHERE s."createdAt" > now() - interval '24 hours'
ORDER BY s."createdAt" DESC LIMIT 20;
COMMIT;
SQL

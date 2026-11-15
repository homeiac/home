#!/bin/bash
# Explain OneDrive storage use: quota breakdown and where photos/videos live (read-only)
#
# Usage: ./cloud-backup-onedrive-quota.sh
#
# Uses the OneDrive token already in the host's rclone config (refreshed by one rclone call first)
# to ask Microsoft Graph:
#   - GET /me/drive                 quota: total, used, deleted (recycle bin), remaining
#   - GET /me/drive/root/children   size of every top-level folder (includes hidden/special ones)
#   - GET /me/drive/special/cameraroll, /photos   phone camera uploads, if any
# and compares with what the backup copied (rclone size, Personal Vault excluded).
# Nothing is changed or downloaded. Tokens are never printed.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"

cb_ssh "CONF='$CB_RCLONE_CONF' REMOTE='$CB_ONEDRIVE_REMOTE' EXCL='$CB_ONEDRIVE_EXCLUDE' bash -s" <<'EOF'
set -euo pipefail
rclone about "$REMOTE:" --config "$CONF" >/dev/null 2>&1 || true   # refreshes the access token if needed
TOKEN="$(rclone config show "$REMOTE" --config "$CONF" | sed -n 's/^token = //p')" python3 - <<'PY'
import json, os, urllib.request, urllib.error
tok = json.loads(os.environ["TOKEN"])["access_token"]
def get(path):
    req = urllib.request.Request("https://graph.microsoft.com/v1.0" + path,
                                 headers={"Authorization": "Bearer " + tok})
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        return {"error": e.code}
gb = lambda b: "%7.2f GB" % ((b or 0) / 1e9)
d = get("/me/drive")
q = d.get("quota", {})
print("== Quota (%s, %s)" % (d.get("driveType"), q.get("state")))
for k in ("total", "used", "deleted", "remaining"):
    print("  %-10s %s" % (k, gb(q.get(k))))
sp = q.get("storagePlanInformation")
if sp: print("  plan      ", sp)
print("\n== Top-level folders and files (size includes everything inside)")
items = get("/me/drive/root/children?$top=999&$select=name,size,folder,specialFolder,package")
for i in sorted(items.get("value", []), key=lambda i: -(i.get("size") or 0)):
    kind = "special:" + i["specialFolder"]["name"] if "specialFolder" in i else \
           ("package:" + i["package"].get("type", "") if "package" in i else ("folder" if "folder" in i else "file"))
    print("  %s  %-28s %s" % (gb(i.get("size")), kind, i["name"]))
print("\n== Special photo folders")
for sf in ("cameraroll", "photos"):
    r = get("/me/drive/special/" + sf)
    print("  %-10s %s" % (sf, "not present" if "error" in r else "%s  in '%s'" % (gb(r.get("size")), r.get("name"))))
PY
echo
echo "== What the backup copies (Personal Vault excluded)"
rclone size "$REMOTE:" --exclude "$EXCL" --config "$CONF" 2>&1 | grep -E "Total (objects|size)"
EOF

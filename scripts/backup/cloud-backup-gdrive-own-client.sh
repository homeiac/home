#!/bin/bash
# Switch the Google Drive remote to your OWN OAuth client (rclone's shared client_id is being retired)
#
# Usage (interactive; inside Claude Code use `! <path> <json>`):
#   ./cloud-backup-gdrive-own-client.sh ~/Downloads/client_secret_<id>.apps.googleusercontent.com.json
#
# Prerequisite (one time, Google Cloud console, see docs/plans/cloud-drive-backup-and-reclaim.md §8):
#   project with the Google Drive API enabled; OAuth consent screen External + "In production"
#   (in "Testing" Google expires refresh tokens after 7 days); OAuth client of type "Desktop app";
#   "Download JSON" of that client.
#
# What it does:
#   1. reads client_id / client_secret from the JSON (never printed) and streams the JSON to the host
#   2. runs `rclone authorize drive <id> <secret>` ON THE HOST through an SSH tunnel on 127.0.0.1:53682;
#      you open the printed URL, sign in, accept the "unverified app" warning (it is your own app)
#   3. updates $CB_GDRIVE_REMOTE on the host: client_id, client_secret, token (scope stays "drive");
#      the old config is kept as rclone.conf.bak-<time>
#   4. verifies with `rclone about` and that the "shared client_id" notice is gone
#   5. replaces only [$CB_GDRIVE_REMOTE] in the K3s VM config (cloud-backup-seed-k8s-config.sh --only)
#   6. deletes the downloaded JSON (the secret now lives only in the host and VM rclone configs)
# Re-runnable: each run re-authorizes with the given client.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"

JSON="${1:-}"
[[ -f "$JSON" ]] || { sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; echo "ERROR: give the downloaded client JSON"; exit 1; }
[[ -t 0 ]] || { echo "ERROR: needs an interactive terminal (browser sign-in)"; exit 1; }
python3 - "$JSON" <<'PY' || exit 1
import json, sys
d = json.load(open(sys.argv[1]))
c = d.get("installed") or {}
if not (c.get("client_id", "").endswith(".apps.googleusercontent.com") and c.get("client_secret")):
    sys.exit("ERROR: not a Desktop-app OAuth client JSON (expected an 'installed' client)")
print("Client:", c["client_id"].split("-")[0] + "-…apps.googleusercontent.com")
PY

readonly CDIR="$(dirname "$CB_RCLONE_CONF")"
readonly HJSON="$CDIR/.gdrive-client.json" AUTH_TMP="$CDIR/.gdrive-auth.tmp"

echo "Copying client JSON to $CB_HOST (0600, removed at the end)"
cb_ssh "umask 077; cat > '$HJSON'" < "$JSON"

echo
echo "Starting Google sign-in on $CB_HOST. Open the URL below, sign in, and continue past"
echo "'Google hasn't verified this app' (Advanced -> Go to homelab-rclone): it is your own app."
echo
ssh -t -o ExitOnForwardFailure=yes -L 53682:127.0.0.1:53682 "$CB_HOST" \
  "umask 077; ID=\$(python3 -c 'import json; print(json.load(open(\"$HJSON\"))[\"installed\"][\"client_id\"])'); \
   SECRET=\$(python3 -c 'import json; print(json.load(open(\"$HJSON\"))[\"installed\"][\"client_secret\"])'); \
   rclone authorize drive \"\$ID\" \"\$SECRET\" --auth-no-open-browser 2>&1 | tee '$AUTH_TMP' \
     | sed -u '/Paste the following/,/End paste/d'"

echo
echo "Updating remote '$CB_GDRIVE_REMOTE' on $CB_HOST"
cb_ssh "HJSON='$HJSON' AUTH_TMP='$AUTH_TMP' CONF='$CB_RCLONE_CONF' REMOTE='$CB_GDRIVE_REMOTE' bash -s" <<'EOF'
set -euo pipefail
trap 'rm -f "$HJSON" "$AUTH_TMP"' EXIT
cat > "$(dirname "$CONF")/.update.py" <<'PY'
import configparser, json, re, sys, shutil, time
conf, hjson, auth, name = sys.argv[1:5]
m = re.search(r"--->\s*(\{.*?\})\s*<---", open(auth).read(), re.S)
if not m:
    sys.exit("ERROR: no token in rclone authorize output (sign-in not completed?)")
token = m.group(1).replace("\r", "").replace("\n", "")
json.loads(token)
c = json.load(open(hjson))["installed"]
shutil.copy2(conf, conf + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
cp = configparser.RawConfigParser(); cp.optionxform = str; cp.read(conf)
if not cp.has_section(name):
    cp.add_section(name); cp.set(name, "type", "drive"); cp.set(name, "scope", "drive")
cp.set(name, "client_id", c["client_id"])
cp.set(name, "client_secret", c["client_secret"])
cp.set(name, "token", token)
with open(conf, "w") as f:
    cp.write(f)
print("updated [%s]: client_id, client_secret, token (backup kept)" % name)
PY
python3 "$(dirname "$CONF")/.update.py" "$CONF" "$HJSON" "$AUTH_TMP" "$REMOTE"
rm -f "$(dirname "$CONF")/.update.py"
chmod 600 "$CONF"
out="$(rclone about "$REMOTE:" --config "$CONF" 2>&1)"
echo "$out" | grep -v -i "client_id"
if echo "$out" | grep -qi "shared Google Drive client_id"; then echo "ERROR: still using the shared client_id"; exit 1; fi
echo "$out" | grep -q "^Total:" || { echo "ERROR: rclone about failed"; exit 1; }
echo "OK: $REMOTE uses its own client_id"
EOF

echo
"$(dirname "${BASH_SOURCE[0]}")/cloud-backup-seed-k8s-config.sh" --only "$CB_GDRIVE_REMOTE"
rm -f "$JSON"
echo "Deleted $JSON"

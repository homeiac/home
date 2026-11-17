#!/bin/bash
# Test enrichers/media_summary.py against a stub OpenAI-compatible server (local; needs python3+duckdb, ffmpeg)
#
# Usage: ./test-enricher.sh
#
# Fixture: one real photo, one 3 s video, one corrupt jpg, indexed with the Photos adapter. Asserts: summaries land in
# media_summaries with the right schema, a summarized file leaves the queue, a failed file stays queued (and is retried),
# re-running writes nothing new for finished files, --dry-run writes nothing, the GPU-memory guard refuses to start.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
W="$(mktemp -d)"; trap 'kill $(cat "$W/stub.pid" 2>/dev/null) 2>/dev/null || true; rm -rf "$W"' EXIT
LIB="$W/library"; IDX="$W/idx"; L="$LIB/Google Photos/Photos from 2023"; mkdir -p "$L" "$IDX"
ffmpeg -v error -f lavfi -i testsrc=size=320x240:rate=1 -frames:v 1 "$L/photo.jpg"
ffmpeg -v error -f lavfi -i testsrc=size=320x240:rate=10 -t 3 -pix_fmt yuv420p "$L/clip.mp4"
echo "not an image" > "$L/broken.jpg"

cat > "$W/stub.py" <<'PY'
import http.server, json, sys
log = sys.argv[1]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msg = body["messages"][0]
        n = len(msg["images"]) if self.path == "/api/chat" else sum(1 for c in msg["content"] if c["type"] == "image_url")
        open(log.replace("requests.log", "path.log"), "a").write(self.path + "\n")
        open(log.replace("requests.log", "extra.log"), "w").write(str(body.get("think")) + "\n")
        open(log, "a").write("%d\n" % n)
        reply = 'Sure!\n```json\n{"summary": "stub summary", "tags": ["a", "b"]}\n```'
        out = json.dumps({"message": {"content": reply}} if self.path == "/api/chat" else {"choices": [{"message": {"content": reply}}]}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def log_message(self, *a): pass
s = http.server.HTTPServer(("127.0.0.1", 0), H)
open(sys.argv[2], "w").write(str(s.server_port))
s.serve_forever()
PY
"$PYTHON" "$W/stub.py" "$W/requests.log" "$W/port" & echo $! > "$W/stub.pid"
for _ in $(seq 1 50); do [[ -s "$W/port" ]] && break; sleep 0.1; done
EP="http://127.0.0.1:$(cat "$W/port")"

P=0 F=0
ok()   { echo "  PASS: $1"; P=$((P+1)); }
bad()  { echo "  FAIL: $1"; F=$((F+1)); }
check() { [[ "$2" == "$3" ]] && ok "$1" || bad "$1 (got '$2', want '$3')"; }
q() { "$PYTHON" "$HERE/kidx.py" query "$IDX" "$1" | tail -n +2; }
reb() { "$PYTHON" "$HERE/kidx.py" rebuild "$IDX" >/dev/null; }
enrich() { "$PYTHON" "$HERE/enrichers/media_summary.py" run --index "$IDX" --library "$LIB" --endpoint "$EP" --model stub-model --enricher e1 --min-free-mib 0 "$@"; }

"$PYTHON" "$HERE/adapters/gphotos.py" emit u1 "$LIB" "$IDX" >/dev/null
reb
check "queue starts with 3 media files"  "$(q "SELECT count(*) FROM gphotos_to_summarize('e1')")" 3

echo "-- dry run"
enrich --dry-run --limit 3 | sed 's/^/  /'
check "dry run wrote nothing"            "$(ls "$IDX/summaries/e1" 2>/dev/null | wc -l | tr -d ' ')" 0

echo "-- real run"
: > "$W/requests.log"
enrich | sed 's/^/  /'
reb
check "2 ok rows"                        "$(q "SELECT count(*) FROM media_summaries WHERE status='ok'")" 2
check "1 error row (corrupt jpg)"        "$(q "SELECT path FROM media_summaries WHERE status='error'")" "Google Photos/Photos from 2023/broken.jpg"
check "error text recorded"              "$(q "SELECT error IS NOT NULL FROM media_summaries WHERE status='error'")" True
check "fenced JSON parsed"               "$(q "SELECT summary || '/' || array_to_string(tags, ',') FROM media_summaries WHERE path LIKE '%photo.jpg'")" "stub summary/a,b"
check "photo: 1 image, no duration"      "$(q "SELECT coalesce(frames_sampled, 0) || '/' || (duration_s IS NULL) FROM media_summaries WHERE path LIKE '%photo.jpg'")" "0/true"
check "video: 3 frames sampled"          "$(q "SELECT frames_sampled FROM media_summaries WHERE path LIKE '%clip.mp4'")" 3
check "video: duration recorded"         "$(q "SELECT round(duration_s) FROM media_summaries WHERE path LIKE '%clip.mp4'")" 3.0
check "model + prompt version stored"    "$(q "SELECT DISTINCT model || '/' || prompt_version FROM media_summaries")" "stub-model/p1"
check "size_bytes = file size"           "$(q "SELECT count(*) FROM media_summaries s JOIN gphotos_files f USING (path) WHERE s.size_bytes = f.size_bytes")" 3
check "model got 3 images for the video" "$(grep -c '^3$' "$W/requests.log")" 1
check "no .tmp left behind"              "$(find "$IDX/summaries" -name '*.tmp' | wc -l | tr -d ' ')" 0

echo "-- queue after run: failed file stays, summarized files leave"
check "only the failed file is queued"   "$(q "SELECT path FROM gphotos_to_summarize('e1')")" "Google Photos/Photos from 2023/broken.jpg"
before="$(wc -l < "$W/requests.log" | tr -d ' ')"
enrich | sed 's/^/  /'; reb
check "re-run retried only the failed file (no model call: undecodable)" "$(wc -l < "$W/requests.log" | tr -d ' ')" "$before"
check "ok rows unchanged"                "$(q "SELECT count(*) FROM media_summaries WHERE status='ok'")" 2
check "latest row per file (3 files)"    "$(q "SELECT count(*) FROM media_summaries")" 3

echo "-- a new enricher id re-queues everything; the old results stay"
check "new id: queue is full again"      "$(q "SELECT count(*) FROM gphotos_to_summarize('e2')")" 3
check "old enricher rows remain"         "$(q "SELECT count(*) FROM media_summaries WHERE enricher='e1' AND status='ok'")" 2

echo "-- extra request fields reach the model server"
: > "$W/requests.log"
"$PYTHON" "$HERE/enrichers/media_summary.py" run --index "$IDX" --library "$LIB" --endpoint "$EP" --model m --enricher e4 --min-free-mib 0 \
  --extra-json '{"think": false}' --dry-run --limit 3 >/dev/null
check "stub saw think=false"             "$(cat "$W/extra.log" 2>/dev/null | head -1)" "False"

echo "-- native Ollama API mode"
: > "$W/requests.log"; : > "$W/path.log"
"$PYTHON" "$HERE/enrichers/media_summary.py" run --index "$IDX" --library "$LIB" --endpoint "$EP" --model m --enricher e5 --min-free-mib 0 \
  --api ollama --extra-json '{"think": false}' --dry-run --limit 3 | grep -c "^ok" | sed 's/^/  ok rows: /'
check "used /api/chat"                   "$(sort -u "$W/path.log")" "/api/chat"
check "think=false sent at top level"    "$(cat "$W/extra.log")" "False"
check "video sent 3 frames natively"     "$(grep -c '^3$' "$W/requests.log")" 1

echo "-- GPU memory guard"
printf '#!/bin/sh\necho 1000\n' > "$W/fake-smi"; chmod +x "$W/fake-smi"
rc=0; "$PYTHON" "$HERE/enrichers/media_summary.py" run --index "$IDX" --library "$LIB" --endpoint "$EP" --model m --enricher e3 \
  --smi-cmd "$W/fake-smi" --min-free-mib 3000 >/dev/null 2>&1 || rc=$?
check "refuses to start below minimum (exit 3)" "$rc" 3
check "and wrote nothing"                "$(ls "$IDX/summaries/e3" 2>/dev/null | wc -l | tr -d ' ')" 0

echo "passed $P, failed $F"
exit $(( F > 0 ))

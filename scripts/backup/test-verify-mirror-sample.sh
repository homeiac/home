#!/bin/bash
# Test the sampling logic of host/verify-mirror-sample.sh on a synthetic library + mirror (no disks, no root)
# Usage: ./test-verify-mirror-sample.sh        Cases: identical -> PASS (incl. fullwidth-encoded name), 1 flipped byte, missing file,
# size change -> each FAIL with exit 1. Exercises the embedded python only (mount/lock logic needs the host).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
sed -n "/<<'PY'/,/^PY\$/p" "$HERE/host/verify-mirror-sample.sh" | sed '1d;$d' > "$W/v.py"
pass=0; fail=0
check() { if [[ "$2" == "$3" ]]; then echo "  PASS: $1"; pass=$((pass+1)); else echo "  FAIL: $1 (got $3, want $2)"; fail=$((fail+1)); fi; }
mk() { rm -rf "$W/lib" "$W/mir"; for y in 2022 2023; do for i in 1 2 3 4 5 6 7 8; do
  for r in lib mir; do d="$W/$r/Google Photos/Photos from $y"; mkdir -p "$d"; head -c $((1000+i*7)) /dev/urandom > "$d/.tmp$y$i"; done
  cp "$W/lib/Google Photos/Photos from $y/.tmp$y$i" "$W/mir/Google Photos/Photos from $y/.tmp$y$i"
  mv "$W/lib/Google Photos/Photos from $y/.tmp$y$i" "$W/lib/Google Photos/Photos from $y/IMG_$i.jpg"
  mv "$W/mir/Google Photos/Photos from $y/.tmp$y$i" "$W/mir/Google Photos/Photos from $y/IMG_$i.jpg"; done; done
  mkdir -p "$W/lib/Google Photos/Trip" "$W/mir/Google Photos/Trip"
  echo "a:b?" > "$W/lib/Google Photos/Trip/a:b?.jpg"; echo "a:b?" > "$W/mir/Google Photos/Trip/a：b？.jpg"; }   # fullwidth stand-ins on the mirror
run() { python3 "$W/v.py" "$W/mir/Google Photos/.." "$W/lib" 0.05 0.95 1 0 "$W/out.json" > "$W/log" 2>&1; echo $?; }
# the python expects <root>/Google Photos/... under the given roots: mirror and lib are the dirs that CONTAIN "Google Photos"
run() { python3 "$W/v.py" "$W/mir" "$W/lib" 0.05 0.95 1 0 "$W/out.json" > "$W/log" 2>&1; echo $?; }
# lib paths are lib/<rel>/<file> with rel = "Google Photos/Photos from Y": same shape on both sides
mk; check "identical copies (incl. fullwidth-encoded name) pass" 0 "$(run)"
grep -q "RESULT PASS" "$W/log" && check "PASS line printed" ok ok || check "PASS line printed" ok missing
mk; f="$W/mir/Google Photos/Photos from 2022/IMG_3.jpg"; printf 'X' | dd of="$f" bs=1 seek=5 conv=notrunc 2>/dev/null
check "one flipped byte fails" 1 "$(run)"
mk; rm "$W/lib/Google Photos/Photos from 2023/IMG_2.jpg"; check "file missing in library fails" 1 "$(run)"
mk; echo extra >> "$W/mir/Google Photos/Photos from 2023/IMG_5.jpg"; check "size change fails" 1 "$(run)"
echo "passed $pass, failed $fail"; [[ $fail -eq 0 ]]

#!/usr/bin/env bash
# Run inside VM 108 via qm guest exec. Cache only verified public model files.
# Temporary loopback-only process. No registration with the production queue.
set -euo pipefail
umask 077
root=/var/tmp/basic-caption-cpu-canary
mkdir -p "$root"
cd "$root"
tag=prism-b10828-a153697
model=https://huggingface.co/prism-ml/Bonsai-27B-gguf/resolve/f10afb355f104535e3e3e98cf7ab7795c72bd292
fetch() {
  local file=$1 url=$2 digest=$3
  if [[ -f "$file" ]] && echo "$digest  $file" | sha256sum -c --status; then return; fi
  curl -fsSL --retry 2 --max-time 900 -C - -o "$file.part" "$url"
  echo "$digest  $file.part" | sha256sum -c --status
  mv "$file.part" "$file"
}
archive="llama-$tag-bin-ubuntu-x64.tar.gz"
fetch "$archive" "https://github.com/PrismML-Eng/llama.cpp/releases/download/$tag/$archive" 301a6ed1b06071a5039e0f48b9b4910ce6934244f94d957474b6c60c5a070ac2
mkdir -p runtime
tar -xzf "$archive" -C runtime
server=$(find "$PWD/runtime" -type f -name llama-server -print -quit)
export LD_LIBRARY_PATH="$(dirname "$server"):$root/deps/usr/lib/x86_64-linux-gnu"
if ldd "$server" | grep -q 'libgomp.so.1 => not found'; then
  mkdir -p deps
  (cd deps && apt-get download libgomp1 && dpkg-deb -x ./libgomp1_*.deb .)
fi
"$server" --version
fetch Bonsai-27B-Q1_0.gguf "$model/Bonsai-27B-Q1_0.gguf" 17ef842e47450caeb8eaa3ebfbbab5d2f2278b62b79be107985fb69a2f819aa0
fetch Bonsai-27B-mmproj-Q8_0.gguf "$model/Bonsai-27B-mmproj-Q8_0.gguf" eb561d41a7bbeb0fcf04883c8af11078ef6cae0a66862a0b68443cfca495269d
exec "$server" -m Bonsai-27B-Q1_0.gguf --mmproj Bonsai-27B-mmproj-Q8_0.gguf --alias bonsai-27b-cpu \
  --host 127.0.0.1 --port 19479 -ngl 0 --no-mmproj-offload -np 1 -c 4096 -t 3 -tb 3 --jinja --no-webui

#!/usr/bin/env python3
"""Patch zero-filled holes in a Google Takeout .tgz by fetching only those byte ranges (host side).

Usage (on the Proxmox host, VM 105 STOPPED, archive path inside a mounted VM-105 filesystem):
  takeout-range-repair.py ARCHIVE --dry-run                 list the holes only
  takeout-range-repair.py ARCHIVE --curl-file FILE [--keep] fetch + patch + verify

FILE is the clipboard text of Chrome DevTools "Copy as cURL" for that part's download request. It holds
the signed URL and the Google session cookies, so it is a credential: it is read here, never printed,
and deleted afterwards unless --keep. Only the URL and -H / -b / --cookie options are taken from it
(parsed with shlex, never executed through a shell).
Safety: each range must answer HTTP 206 with exactly the requested length, otherwise nothing is written.
A final full gzip test must pass, or the exit code is 1.
"""
import argparse, os, shlex, subprocess, sys

def holes(path):
    size = os.path.getsize(path); fd = os.open(path, os.O_RDONLY); out = []; pos = 0
    while pos < size:
        h = os.lseek(fd, pos, os.SEEK_HOLE)
        if h >= size: break
        try: d = os.lseek(fd, h, os.SEEK_DATA)
        except OSError: d = size
        out.append((h, d - h)); pos = d
    os.close(fd); return out

def curl_args(curl_file):
    toks = shlex.split(open(curl_file).read().replace("\\\n", " "))
    url, opts, i = None, [], 1
    while i < len(toks):
        t = toks[i]
        if t in ("-H", "--header", "-b", "--cookie") and i + 1 < len(toks):
            if not (t in ("-H", "--header") and toks[i + 1].lower().split(":")[0] in ("range", "accept-encoding")):
                opts += [t, toks[i + 1]]
            i += 2; continue
        if t.startswith("http"): url = t
        i += 1
    if not url: sys.exit("no URL found in the curl file")
    return url, opts

def fetch(url, opts, start, length, dest_tmp):
    r = subprocess.run(["curl", "-sS", "-L", "-o", dest_tmp, "-w", "%{http_code} %{size_download}",
                        "-r", f"{start}-{start + length - 1}", *opts, url], capture_output=True, text=True)
    code, _, got = r.stdout.strip().partition(" ")
    if r.returncode or code != "206" or int(got or 0) != length:
        sys.exit(f"range {start}+{length}: HTTP {code or '?'}, {got or 0} bytes, curl rc {r.returncode} "
                 f"{r.stderr.strip()[:120]} - nothing written (link expired / re-auth needed / Range not supported?)")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("archive")
    ap.add_argument("--curl-file"); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(); hs = holes(a.archive)
    print(f"{os.path.basename(a.archive)}: {os.path.getsize(a.archive)} bytes, {len(hs)} hole(s): " +
          ", ".join(f"{h}+{l} ({l/1e6:.1f} MB)" for h, l in hs))
    if a.dry_run or not hs: return 0
    if not a.curl_file: sys.exit("--curl-file is required")
    url, opts = curl_args(a.curl_file); tmp = a.archive + ".range.tmp"
    size = os.path.getsize(a.archive); PAD = 65536
    for h, l in hs:
        # identity check: fetch PAD bytes of known-good data on each side of the hole as well; they must equal the local
        # file byte for byte, otherwise this link belongs to a different part and nothing is written.
        lo, hi = max(0, h - PAD), min(size, h + l + PAD)
        fetch(url, opts, lo, hi - lo, tmp)
        with open(tmp, "rb") as src, open(a.archive, "rb") as dst:
            remote = src.read(); dst.seek(lo); local = dst.read(hi - lo)
        n1, n2 = h - lo, hi - (h + l)
        if remote[:n1] != local[:n1] or (n2 and remote[len(remote) - n2:] != local[len(local) - n2:]):
            sys.exit(f"range {h}+{l}: neighbouring bytes differ from the local file - this cURL is for a different part; nothing written")
        with open(a.archive, "r+b") as dst:
            dst.seek(h); dst.write(remote[n1:n1 + l]); dst.flush(); os.fsync(dst.fileno())
        os.unlink(tmp); print(f"patched {h}+{l} (neighbours verified)")
    left = holes(a.archive)
    if left: sys.exit(f"holes remain: {left}")
    print("verifying with gzip -t (full read) ...", flush=True)
    ok = subprocess.run(["gzip", "-t", a.archive]).returncode == 0
    if not a.keep: os.unlink(a.curl_file); print("curl file (cookies) deleted")
    print("RESULT:", "archive is now valid" if ok else "gzip test FAILED - archive still bad")
    return 0 if ok else 1

sys.exit(main())

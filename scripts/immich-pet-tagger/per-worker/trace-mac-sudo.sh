#!/usr/bin/env bash
# Wait visibly for the isolated Metal diagnostic worker, then profile for 20s.
# Only profiler children are stopped. No model worker or other app is signalled.
set -euo pipefail
[[ $(id -u) == 0 && -n ${SUDO_UID:-} ]] || { echo 'Run with sudo from your normal account.'; exit 1; }
base=/private/tmp/waffles-pet-tagger-private/per-worker-20261127
trial="$base/mac-mps-traced"
[[ -d $base && ! -L $base ]] || exit 1
umask 077
echo 'START: waiting for the matched-photo Metal diagnostic worker (maximum 5 minutes).'
for ((n=0;n<300;n++)); do
  if [[ -f $trial/ready && -f $trial/pid && ! -L $trial ]]; then
    candidate=$(cat "$trial/pid")
    if [[ $candidate =~ ^[0-9]+$ ]]; then
      candidate_command=$(ps -p "$candidate" -o command= 2>/dev/null || true)
      if [[ $candidate_command == *"$base/worker.py"* && $candidate_command == *'--label mac-mps-traced'* ]]; then break; fi
    fi
  fi
  (( n % 5 != 0 )) || echo "${n}s: waiting for worker readiness..."
  sleep 1
done
[[ -f $trial/ready && ! -L $trial ]] || { echo 'Readiness deadline; no capture started.'; exit 1; }
pid=$(cat "$trial/pid")
[[ $pid =~ ^[0-9]+$ ]] || exit 1
command=$(ps -p "$pid" -o command=)
[[ $command == *"$base/worker.py"* && $command == *'--label mac-mps-traced'* ]] || { echo 'PID identity mismatch.'; exit 1; }
directory="$base/sudo-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 700 "$directory"
trace_pid= power_pid=
owned() { [[ -n $1 && $(ps -p "$1" -o ppid= 2>/dev/null | tr -d ' ') == "$$" ]]; }
cleanup() {
 trap - EXIT INT TERM
 for child in "$trace_pid" "$power_pid"; do
  if owned "$child"; then kill -KILL "$child" 2>/dev/null || true; fi
 done
 chown -R "$SUDO_UID:${SUDO_GID:-$(id -g "$SUDO_USER")}" "$directory"
 echo "FINISHED: $directory (diagnostic worker untouched)"
}
trap cleanup EXIT
trap 'exit 130' INT TERM
cat > "$directory/syscalls.d" <<EOF
#pragma D option quiet
syscall::*read*:entry,syscall::*write*:entry,syscall::*poll*:entry,syscall::*kevent*:entry,syscall::*psynch*:entry,syscall::*ulock*:entry,syscall::*semwait*:entry
/pid == $pid/ { self->start = timestamp; }
syscall::*read*:return,syscall::*write*:return,syscall::*poll*:return,syscall::*kevent*:return,syscall::*psynch*:return,syscall::*ulock*:return,syscall::*semwait*:return
/pid == $pid && self->start/ { @ns[tid,probefunc]=sum(timestamp-self->start); @calls[tid,probefunc]=count(); self->start=0; }
interval-20s { exit(0); }
EOF
echo "START CAPTURE: PID $pid; 20 seconds, 25-second hard profiler deadline."
/usr/sbin/dtrace -Z -s "$directory/syscalls.d" > "$directory/dtrace.txt" 2> "$directory/dtrace.stderr" &
trace_pid=$!
/usr/bin/powermetrics --samplers tasks,cpu_power,gpu_power,thermal --show-process-gpu --show-process-io --show-process-netstats --show-process-wait-times -i 1000 -n 20 -f plist > "$directory/powermetrics.plist" 2> "$directory/powermetrics.stderr" &
power_pid=$!
printf '%s\n' "$pid" > "$directory/worker-pid"
touch "$trial/trace-started"
for ((elapsed=0;elapsed<25;elapsed++)); do
 (( elapsed % 5 != 0 )) || echo "${elapsed}s: collecting actual worker diagnostics..."
 sleep 1
 if ! owned "$trace_pid" && ! owned "$power_pid"; then break; fi
done

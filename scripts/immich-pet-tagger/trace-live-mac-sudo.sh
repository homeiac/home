#!/usr/bin/env bash
# Bounded, visible read-only tracing of the EXISTING Metal worker. No test jobs.
set -euo pipefail
[[ $(id -u) == 0 && -n ${SUDO_UID:-} ]] || { echo 'Run with sudo from your normal account.'; exit 1; }
pid=$(pgrep -f '/immich-pet-tagger/worker.py$')
[[ $pid =~ ^[0-9]+$ ]] || { echo 'Expected exactly one existing Metal worker.'; exit 1; }
base=/private/tmp/waffles-pet-tagger-private/live-trace
[[ -d $base && ! -L $base ]] || { echo 'Private trace directory missing or is a symlink.'; exit 1; }
directory="$base/$(date -u +%Y%m%dT%H%M%SZ)-sudo-$$"
mkdir -m 700 "$directory"
umask 077
trace_pid= power_pid=
owned_child() { [[ -n $1 && $(ps -p "$1" -o ppid= 2>/dev/null | tr -d ' ') == "$$" ]]; }
cleanup() {
  trap - EXIT INT TERM
  for child in "$trace_pid" "$power_pid"; do
    if owned_child "$child"; then kill -KILL "$child" 2>/dev/null || true; fi
  done
  chown -R "$SUDO_UID:${SUDO_GID:-$(id -g "$SUDO_USER")}" "$directory"
  printf '\nFinished. Saved live-worker diagnostics: %s\n' "$directory"
  echo 'Production worker was not signalled or restarted.'
}
trap cleanup EXIT
trap 'echo "Capture interrupted; stopping profiler children only."; exit 130' INT TERM
printf 'START: tracing existing Metal worker PID %s\n' "$pid"
echo 'Collecting per-process GPU/CPU/I/O activity and syscall wait totals.'
echo 'Expected duration: 20 seconds; hard profiler deadline: 25 seconds.'
printf 'Output: %s\n' "$directory"
printf 'pid=%s\nstarted=%s\n' "$pid" "$(date -u +%FT%TZ)" > "$directory/metadata.txt"
# Native sample supplies call stacks separately. Avoid DTrace user-stack symbolication.
cat > "$directory/worker.d" <<EOF
#pragma D option quiet
syscall::*read*:entry, syscall::*write*:entry, syscall::*recv*:entry,
syscall::*send*:entry, syscall::*connect*:entry, syscall::*poll*:entry,
syscall::*kevent*:entry, syscall::*psynch*:entry, syscall::*ulock*:entry,
syscall::*sleep*:entry, syscall::*semwait*:entry
/pid == $pid/
{ self->entered = timestamp; }
syscall::*read*:return, syscall::*write*:return, syscall::*recv*:return,
syscall::*send*:return, syscall::*connect*:return, syscall::*poll*:return,
syscall::*kevent*:return, syscall::*psynch*:return, syscall::*ulock*:return,
syscall::*sleep*:return, syscall::*semwait*:return
/pid == $pid && self->entered/
{
  @syscall_nanoseconds[tid, probefunc] = sum(timestamp - self->entered);
  @syscall_calls[tid, probefunc] = count();
  self->entered = 0;
}
interval-20s { exit(0); }
EOF
/usr/bin/powermetrics --samplers tasks,cpu_power,gpu_power,thermal --show-process-gpu --show-process-io --show-process-netstats --show-process-wait-times --show-process-amp -i 1000 -n 20 -f plist > "$directory/powermetrics.plist" 2> "$directory/powermetrics.stderr" &
power_pid=$!
/usr/sbin/dtrace -Z -s "$directory/worker.d" > "$directory/dtrace.txt" 2> "$directory/dtrace.stderr" &
trace_pid=$!
printf 'Profiler PIDs: powermetrics=%s, dtrace=%s (worker=%s remains untouched)\n' "$power_pid" "$trace_pid" "$pid"
for ((elapsed=0; elapsed<25; elapsed++)); do
  if ! owned_child "$trace_pid" && ! owned_child "$power_pid"; then break; fi
  if (( elapsed % 5 == 0 )); then printf '%2ss: collecting live diagnostics...\n' "$elapsed"; fi
  sleep 1
done
for entry in "dtrace:$trace_pid" "powermetrics:$power_pid"; do
  name=${entry%%:*}; child=${entry##*:}
  if owned_child "$child"; then
    printf '25s deadline: forcibly stopping %s profiler PID %s only.\n' "$name" "$child"
    kill -KILL "$child" 2>/dev/null || true
    printf '%s_status=deadline\n' "$name" >> "$directory/metadata.txt"
  else
    set +e; wait "$child"; status=$?; set -e
    printf '%s_status=%s\n' "$name" "$status" >> "$directory/metadata.txt"
    printf '%s finished (status %s).\n' "$name" "$status"
  fi
done
printf 'finished=%s\n' "$(date -u +%FT%TZ)" >> "$directory/metadata.txt"

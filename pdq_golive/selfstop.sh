#!/usr/bin/env bash
# End this pod from inside, without the laptop. Run 5 showed why: the laptop lost its internet
# at the deadline, so its terminate call failed and the pod outlived the 3-hour limit.
#   1. terminate through the RunPod API with the pod-scoped key RunPod hands every pod
#      (RUNPOD_API_KEY, RUNPOD_POD_ID). Our account key is never on the pod.
#   2. if that is refused, stop the pod through the same API (stops the GPU charge);
#   3. last resort: end the container.
# Usage: selfstop.sh "<reason>"
set -u
LOG=/workspace_golive/boot.log
say() { echo "[selfstop] $(date -u +%FT%TZ) $*" | tee -a "$LOG"; }
say "reason: ${1:-none}"
# a shell started over SSH may not carry RunPod's variables: take them from PID 1, never print
if [ -z "${RUNPOD_API_KEY:-}" ] || [ -z "${RUNPOD_POD_ID:-}" ]; then
  while IFS= read -r -d '' kv; do
    case "$kv" in RUNPOD_API_KEY=*|RUNPOD_POD_ID=*) export "$kv";; esac
  done < /proc/1/environ 2>/dev/null
fi
sync
api() {
  curl -s -m 20 -H "Content-Type: application/json" -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
    https://api.runpod.io/graphql -d "$1" | head -c 300
}
if [ -n "${RUNPOD_API_KEY:-}" ] && [ -n "${RUNPOD_POD_ID:-}" ]; then
  for t in 1 2 3; do
    r=$(api "{\"query\":\"mutation { podTerminate(input: {podId: \\\"${RUNPOD_POD_ID}\\\"}) }\"}")
    say "terminate try $t: $(echo "$r" | tr -d '\n' | cut -c1-160)"
    echo "$r" | grep -q '"errors"' || { sleep 30; }
    sleep 10
  done
  r=$(api "{\"query\":\"mutation { podStop(input: {podId: \\\"${RUNPOD_POD_ID}\\\"}) { id desiredStatus } }\"}")
  say "stop: $(echo "$r" | tr -d '\n' | cut -c1-160)"
else
  say "no pod-scoped RunPod key in this environment"
fi
say "ending the container"
kill 1

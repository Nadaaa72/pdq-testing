#!/usr/bin/env bash
# One test session, started by boot.sh when GOLIVE_SESSION=1. Needs no laptop once the clips
# are on the pod: the laptop only uploads, writes UPLOAD_DONE, and copies results back.
#   a) wait for the index (READY) and the clips (UPLOAD_DONE)
#   b) warm the index: read the files once (RAM is smaller than the index, so this is partial)
#   c) evidence pass: every clip searched ONCE at 160 pictures, all views, 3 at a time;
#      every setting is then replayed on the laptop from these files
#   d) live timing: 50 clips one at a time, golive_g16 at nprobe 16, then the same at nprobe 32
#   e) DONE, then the pod ends itself (selfstop.sh)
# Every phase resumes if rerun and every clip has a time limit. Results: /workspace_golive/out
set -u
source /etc/profile.d/golive.sh
A=/app/pdq_golive
RUN=/workspace_golive/run; O=/workspace_golive/out; mkdir -p "$RUN" "$O"
phase() { echo "$(date -u +%FT%TZ) phase $*" >> "$O/phases.log"; sync; }
phase "session start"

# a) wait, at most 80 min from boot for both
for i in $(seq 1 160); do
  [ -f /local_index/READY ] && [ -f "$RUN/UPLOAD_DONE" ] && break
  # boot.sh writes this only after its retry has failed too
  grep -q "index copy FAILED" /workspace_golive/boot.log 2>/dev/null \
    && { phase "index FAILED"; bash $A/selfstop.sh "index copy failed"; exit 1; }
  sleep 30
done
if ! [ -f /local_index/READY ] || ! [ -f "$RUN/UPLOAD_DONE" ]; then
  phase "not ready after 80 min (READY=$(test -f /local_index/READY && echo y) UPLOAD=$(test -f $RUN/UPLOAD_DONE && echo y))"
  bash $A/selfstop.sh "not ready"; exit 1
fi
phase "ready"
(vmstat -t 5 > "$O/vmstat.log" 2>&1 &); (iostat -x 5 > "$O/iostat.log" 2>&1 &)
free -g > "$O/mem.txt"; nproc >> "$O/mem.txt"

# b) warm: 8 readers over ivf + rtmeta
t=$(date +%s)
find /local_index/ivf /local_index/rtmeta -type f \( -name '*.index' -o -name '*.bin' \) -print0 \
  | xargs -0 -n 1 -P 8 sh -c 'cat "$0" > /dev/null'
phase "warm end $(( $(date +%s) - t ))s"

# manifests: all clips for the evidence pass; 50 for timing (fixed seed, every group kept)
cd "$RUN"
python3 - <<'P'
import csv, random
rows = list(csv.DictReader(open("golive_manifest.csv", encoding="utf-8-sig")))
for r in rows:
    r["path"] = r["clip"] if "/" in r["clip"] else "clips/" + r["clip"]
f = list(rows[0].keys())
def w(n, rs):
    x = csv.DictWriter(open(n, "w", newline="", encoding="utf-8"), fieldnames=f); x.writeheader(); x.writerows(rs)
w("m_all.csv", rows)
random.seed(44); w("m_time.csv", random.sample(rows, min(50, len(rows))))
print("manifests", len(rows))
P

# c) evidence pass, 3 processes, 10 threads each (32 vCPU)
phase "evidence start"
for s in 0 1 2; do
  OMP_NUM_THREADS=10 python3 $A/evidence.py --manifest m_all.csv --out "$O" --tag golive6 \
    --shard $s/3 --timeout 180 > "$O/evidence_s$s.log" 2>&1 &
done
wait
phase "evidence end"

# d) live timing, one clip at a time, warm index
export GOLIVE_CLIP_TIMEOUT=180
phase "time16 start"
PDQ_IVF_NPROBE=16 python3 $A/run.py --manifest m_time.csv --out "$O/time16.jsonl" --profiles golive_g16 > "$O/time16.log" 2>&1
phase "time16 end rc=$?"
phase "time32 start"
PDQ_IVF_NPROBE=32 python3 $A/run.py --manifest m_time.csv --out "$O/time32.jsonl" --profiles golive_g16 > "$O/time32.log" 2>&1
phase "time32 end rc=$?"

# e) done: leave 4 minutes for the laptop's last copy, then end the pod
echo ALL_DONE >> "$O/phases.log"; sync
sleep 240
bash $A/selfstop.sh "session complete"

#!/usr/bin/env bash
# PDQ testing to go live: the whole start-up of the test pod. Nothing else runs.
#   1. a hard stop, before anything else
#   2. sshd, so the run can be driven and results copied back
#   3. the index copy (B2 read-only), then the B2 key is removed from this environment
#   4. READY, then idle until someone runs pdq_golive/run.py
# No supervisord, no app, no database, no calls out except B2 during step 3.
set -u
LOG=/workspace_golive/boot.log
mkdir -p /workspace_golive /local_index
exec > >(tee -a "$LOG") 2>&1
echo "[boot] $(date -u +%FT%TZ) image ${GOLIVE_IMAGE_SHA:-unknown}"

# 1. hard stop. GOLIVE_MAX_MIN defaults to 165 (2 h 45 min). The pod ends itself through the
#    RunPod API with the pod-scoped key RunPod hands every pod (selfstop.sh: terminate, then
#    stop, then kill 1). Run 5 showed the laptop cannot be the guard: it lost its internet at
#    the deadline. The laptop watchdog stays as the second line.
MAX_MIN="${GOLIVE_MAX_MIN:-165}"
( sleep $(( MAX_MIN * 60 )); bash /app/pdq_golive/selfstop.sh "hard stop after ${MAX_MIN} min" ) &
echo "[boot] hard stop armed: ${MAX_MIN} min"

# 2. sshd with the key RunPod hands in
if [ -n "${PUBLIC_KEY:-}" ]; then
  mkdir -p /root/.ssh && chmod 700 /root/.ssh
  echo "$PUBLIC_KEY" > /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys
fi
ssh-keygen -A >/dev/null 2>&1
# started without the B2 variables, so no login session can inherit them
mkdir -p /run/sshd && env -u B2_KEY_ID -u B2_APP_KEY -u B2_BUCKET -u B2_ENDPOINT /usr/sbin/sshd \
  && echo "[boot] sshd up"

# 3. the index, unless it is already complete on this disk
if [ ! -f /local_index/READY ]; then
  # run 5: the copy with 48 parallel requests failed; 8 with lenient checksums worked
  export AWS_RESPONSE_CHECKSUM_VALIDATION=when_required AWS_REQUEST_CHECKSUM_CALCULATION=when_required
  export AWS_MAX_ATTEMPTS=10 AWS_RETRY_MODE=adaptive
  python3 /app/pdq_golive/fetch_index.py --dest /local_index --workers 8
  rc=$?
  if [ "$rc" != "0" ]; then
    echo "[boot] index copy failed rc=$rc: fetch retry"
    python3 /app/pdq_golive/fetch_index.py --dest /local_index --workers 4
    rc=$?
  fi
  # the key is needed for nothing else: drop it from this shell and every child from now on
  unset B2_KEY_ID B2_APP_KEY B2_BUCKET B2_ENDPOINT
  if [ "$rc" != "0" ]; then
    echo "[boot] index copy FAILED rc=$rc"
  else
    date -u +%FT%TZ > /local_index/READY
    echo "[boot] READY"
  fi
else
  unset B2_KEY_ID B2_APP_KEY B2_BUCKET B2_ENDPOINT
  echo "[boot] index already present"
fi

# SSH sessions start from a clean environment with only what the runner needs.
cat > /etc/profile.d/golive.sh <<EOF
export PDQ_INDEX_DIR=/local_index
export PDQ_POD_SHARDS=/local_index/pdq_cache_flat_v2
export PDQ_POD_FILMS_CACHE=/local_index/film_list.json
export PDQ_IVF_NPROBE=${PDQ_IVF_NPROBE:-16}
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-16}
export CUDA_VISIBLE_DEVICES=""
export GOLIVE_ENGINE=/app/pdq_golive/vendor/pdq_engine_PROBEV2.py
EOF
if [ "${GOLIVE_SESSION:-0}" = "1" ]; then
  setsid nohup bash /app/pdq_golive/session.sh > /workspace_golive/session.out 2>&1 < /dev/null &
  echo "[boot] session started"
fi
echo "[boot] idle; run: python3 /app/pdq_golive/run.py --help"
sleep infinity

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

# 1. hard stop. GOLIVE_MAX_MIN defaults to 170 (2 h 50 min). The pod stops itself through the
#    RunPod API (RunPod hands every pod RUNPOD_POD_ID and a pod-scoped RUNPOD_API_KEY), and
#    the container then exits. A container exit alone could be restarted by RunPod, which is
#    why the API stop comes first; the laptop-side timer (Part 20) is the third line.
MAX_MIN="${GOLIVE_MAX_MIN:-170}"
(
  sleep $(( MAX_MIN * 60 ))
  echo "[boot] HARD STOP after ${MAX_MIN} min"
  if [ -n "${RUNPOD_POD_ID:-}" ] && [ -n "${RUNPOD_API_KEY:-}" ]; then
    curl -s -m 20 -H "Content-Type: application/json" \
      -H "Authorization: Bearer ${RUNPOD_API_KEY}" https://api.runpod.io/graphql \
      -d "{\"query\":\"mutation { podStop(input: {podId: \\\"${RUNPOD_POD_ID}\\\"}) { id desiredStatus } }\"}" \
      | head -c 300; echo
  fi
  kill 1
) &
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
  python3 /app/pdq_golive/fetch_index.py --dest /local_index
  rc=$?
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
echo "[boot] idle; run: python3 /app/pdq_golive/run.py --help"
sleep infinity

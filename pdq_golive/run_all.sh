#!/bin/bash
# Parts 23-28 on the pod, in priority order. Each phase writes JSON lines to $O and resumes if
# rerun, so a stop loses nothing that finished. Start it detached:
#   setsid nohup bash /app/pdq_golive/run_all.sh > /workspace_golive/run_all.out 2>&1 < /dev/null &
# Clips and golive_manifest.csv must be in /workspace_golive/run.
source /etc/profile.d/golive.sh
cd /workspace_golive/run || exit 1
O=/workspace_golive/out; mkdir -p $O
phase() { date -u +"%FT%TZ phase $1" >> $O/phases.log; sync; }
python3 - <<'P'
import csv, random
rows = list(csv.DictReader(open("golive_manifest.csv", encoding="utf-8-sig")))
for r in rows:
    r["path"] = r["clip"] if "/" in r["clip"] else "clips/" + r["clip"]
f = list(rows[0].keys())
def w(n, rs):
    x = csv.DictWriter(open(n, "w", newline="", encoding="utf-8"), fieldnames=f); x.writeheader(); x.writerows(rs)
random.seed(42); random.shuffle(rows)
# proof first: 20 user-confirmed SSCD clips; the main run then covers everything else
strong = [r for r in rows if r.get("group") == "sscd_in_index" and r.get("strength") == "strong"][:20]
rest = [r for r in rows if r not in strong]
w("m_proof.csv", strong); w("m_main.csv", rest)
random.seed(43); sub = random.sample(rows, 100); w("m_cmp.csv", sub); w("m_np32.csv", sub[:50])
for k in (2, 4):
    for i in range(k):
        w("m_c%d_%d.csv" % (k, i), [r for j, r in enumerate(sub) if j % k == i])
print("manifests ok", len(rows), "proof", len(strong))
P
(vmstat -t 5 > $O/vmstat.log 2>&1 &) ; (iostat -x 5 > $O/iostat.log 2>&1 &)
R="python3 /app/pdq_golive/run.py"
phase "proof start";  $R --manifest m_proof.csv --out $O/proof.jsonl --profiles golive_g16 > $O/proof.log 2>&1; phase "proof end rc=$?"
phase "main start";   $R --manifest m_main.csv --out $O/main.jsonl --profiles golive_g16 > $O/main.log 2>&1;    phase "main end rc=$?"
phase "cmp start";    $R --manifest m_cmp.csv --out $O/cmp.jsonl --profiles today,A,B,golive_g16 --rotate > $O/cmp.log 2>&1; phase "cmp end rc=$?"
phase "np32 start";   PDQ_IVF_NPROBE=32 $R --manifest m_np32.csv --out $O/np32.jsonl --profiles golive_g16 > $O/np32.log 2>&1; phase "np32 end rc=$?"
for k in 2 4; do
  phase "conc$k start"
  for i in $(seq 0 $((k-1))); do timeout 600 $R --manifest m_c${k}_$i.csv --out $O/conc${k}_$i.jsonl --profiles golive_g16 > $O/conc${k}_$i.log 2>&1 & done
  wait; phase "conc$k end"
done
echo ALL_DONE >> $O/phases.log

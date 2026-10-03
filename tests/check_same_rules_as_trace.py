# -*- coding: utf-8 -*-
"""
check_same_rules_as_trace.py - prove the engine's rules are the pod's rules.

    python tests/check_same_rules_as_trace.py

What it does: it lifts the pod's own rule code (the closures inside sharded_query_fast in
the long-named file in ../pdq/) out of that file, runs it side by side with pdq_engine on
thousands of made-up search results, and checks that both sides fill the scorecards the
same way and fire the same rule with the same reason text. Every rule that can fire is
made to fire at least once. Needs no video and no index. Takes about a minute.

If you change a rule in pdq_engine.py on purpose, this test WILL fail. That is fine:
it tells you exactly which rule now differs from the pod.
"""
from __future__ import annotations
import io
import os
import random
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import pdq_engine as E  # noqa: E402

# The pod's code: the live file when the repo's pdq/ folder is next to this one, else the
# word-for-word snapshot in tests/pod_rules_snapshot.py (so the folder works on its own).
PDQ_DIR = HERE.parent.parent / "pdq"
_live = list(PDQ_DIR.glob("pdq_query_cli_dynamic_shards_*" + "PASS2_ALWAYS" + ".py")) if PDQ_DIR.is_dir() else []
if _live:
    POD_SOURCE = "the live pod file " + _live[0].name[:40] + "..."
    L = _live[0].read_text(encoding="utf-8").splitlines()
else:
    import pod_rules_snapshot as SNAP
    POD_SOURCE = "the snapshot taken on " + SNAP.TAKEN_ON
    L = None


def find(pattern: str, start: int = 0) -> int:
    """1-based line number of the first line containing `pattern` at or after line `start`."""
    for i in range(max(0, start - 1), len(L)):
        if pattern in L[i]:
            return i + 1
    raise RuntimeError(f"not found in pod file: {pattern}")


def block(a: int, b: int) -> str:
    return textwrap.dedent("\n".join(L[a - 1:b])) + "\n"


def pod_parts() -> list:
    """The five pieces of pod code, as text, in the order they must be executed."""
    if L is None:
        return [SNAP.P9_MIN_FRAMES, SNAP.CONSTANTS, SNAP.SCORECARD, SNAP.HELPERS, SNAP.RULES]
    p9 = find("def _pdq_p9_min_frames")
    c0 = find("HAMMING_CUTOFF_EXCL = 45.0")
    m0 = find("movie_stats = defaultdict(", c0)
    h0 = find("def _best_aligned_bucket_range", m0)
    r0 = find("def _do_stats_update", h0)
    return [block(p9, find("class ShardedPDQ", p9) - 1),
            block(c0, find("PENDING_WAIT_VIDEO_S = 3.0", c0)),
            block(m0, find("pending_exit = {", m0) + 7),
            block(h0, find("def _set_pending_exit", h0) - 1),
            block(r0, find("def _stream_update_from_frame", r0) - 1)]


PARTS = pod_parts()


def lift_pod_rules():
    """Execute the pod's constants, scorecard factory, helpers and rule closures in a fresh namespace."""
    ns = {"np": np, "os": os, "defaultdict": defaultdict, "offset_bucket_s": 1.0}
    for text in PARTS:
        exec(text, ns)
    return ns


def norm(st: dict) -> dict:
    """A scorecard as plain values, so the two sides can be compared with ==."""
    out = {}
    for k, v in st.items():
        if isinstance(v, dict):
            out[k] = {kk: (dict(vv) if isinstance(vv, dict) else vv) for kk, vv in v.items()}
        elif k == "min_hamming":
            out[k] = float(v) if v not in (999.0, float("inf")) else "none"
        else:
            out[k] = v
    return out


def scenario():
    """A family of pretend clip. Each family is built to reach different rules.
    Returns (name, hamming band, offset noise, rows per batch, close neighbours per row, clip seconds per step)."""
    fam = random.choice(["loud", "slow-strong", "slow-medium", "medium-scatter", "weak", "junk",
                         "two-films", "burst", "p4", "p6a", "p4", "p6a"])
    if fam == "p4":
        return fam, (15, 20), random.choice([0.0, 0.3]), (1, 1), (1, 1), random.choice([3.5, 4.0, 6.0])
    if fam == "p6a":
        return fam, (21, 25), 0.0, (1, 1), (1, 1), 0.1
    if fam == "loud":
        return fam, (0, 12), 0.0, (4, 12), (1, 4), 0.5
    if fam == "slow-strong":
        return fam, (random.choice([3, 6, 9]), 20), random.choice([0.0, 0.3, 1.5]), (1, 2), (1, 1), random.choice([0.5, 1.5, 4.0])
    if fam == "slow-medium":
        return fam, (21, 35), random.choice([0.0, 0.3]), (1, 3), (1, 2), random.choice([0.5, 1.5, 4.0])
    if fam == "medium-scatter":
        return fam, (21, 35), 6.0, (1, 3), (1, 2), 0.5
    if fam == "weak":
        return fam, (36, 44), random.choice([0.0, 0.3, 6.0]), (1, 4), (1, 3), random.choice([0.5, 2.0])
    if fam == "junk":
        return fam, (45, 90), 6.0, (2, 6), (1, 2), 0.5
    if fam == "burst":
        return fam, (26, 35), 0.0, (8, 12), (1, 2), 0.25
    return fam, (10, 40), 0.3, (2, 6), (1, 3), 0.5


def main(trials: int = 1500) -> int:
    random.seed(7)
    np.random.seed(7)
    fired = defaultdict(int)
    n_batches = 0
    mism = 0
    for trial in range(trials):
        pod = lift_pod_rules()
        ms_pod = pod["movie_stats"]
        ms_me = defaultdict(E._new_stats)
        hist_me = defaultdict(lambda: defaultdict(int))
        fam, band, noise, rows_rng, kk_rng, dt = scenario()
        n_films = 1 if fam in ("slow-strong", "slow-medium", "weak") and random.random() < 0.6 else random.choice([1, 2, 3, 6])
        per = 4000
        meta_vid = np.repeat(np.arange(n_films, dtype="<u8"), per)
        meta_ts = np.tile(np.arange(per, dtype="<f4") / 16.0, n_films)
        true_offset = random.uniform(10, 200)
        films_used = [random.randrange(n_films)] if fam != "two-films" else list(range(min(2, n_films)))
        for step in range(random.randint(2, 40)):
            q_ts = step * dt
            rows = random.randint(*rows_rng)
            D = np.full((rows, 64), 60, dtype=np.int32) + np.random.randint(0, 40, size=(rows, 64)).astype(np.int32)
            I = np.random.randint(0, n_films * per, size=(rows, 64)).astype(np.int64)
            for r in range(rows):
                for kk in range(random.randint(*kk_rng)):
                    film = random.choice(films_used)
                    t = q_ts + true_offset + (random.gauss(0, noise) if noise else 0.0)
                    I[r, kk] = film * per + min(max(int(round(t * 16)), 0), per - 1)
                    D[r, kk] = random.randint(band[0], band[1])
            if random.random() < 0.05:
                I[0, 0] = -1
            touched_pod, touched_me = set(), set()
            pod["_do_stats_update"](D, I, 0, meta_vid, meta_ts, q_ts, touched_pod)
            E._update_stats(ms_me, touched_me, D, I, meta_vid, meta_ts, q_ts, hist_me)
            n_batches += 1
            if touched_pod != touched_me:
                mism += 1
                print("MISMATCH touched films", trial, step, touched_pod, touched_me)
                continue
            for mid in touched_me:
                a, b = norm(ms_pod[mid]), norm(ms_me[mid])
                if a != b:
                    mism += 1
                    if mism < 4:
                        for k in a:
                            if a[k] != b.get(k):
                                print("MISMATCH scorecard", trial, step, mid, k, "pod=", a[k], "engine=", b.get(k))
                ep = pod["_check_early_exit"](mid, ms_pod[mid], q_ts)
                em = E.check_early_exit(mid, ms_me[mid])
                kp = None if ep is None else (ep.get("movie_id"), ep.get("reason"), int(ep.get("priority")), bool(ep.get("immediate", True)))
                km = None if em is None else (em["movie_id"], em["reason"], int(em["priority"]), bool(em["immediate"]))
                if kp != km:
                    mism += 1
                    if mism < 6:
                        print("MISMATCH rule", trial, step, "pod=", kp, "engine=", km)
                if em:
                    fired[em["reason"].split(":")[0]] += 1
        ep = pod["_check_end_of_processing_exit"]()
        em = E.check_end_of_clip_exit(ms_me)
        kp = None if ep is None else (ep.get("movie_id"), ep.get("reason"))
        km = None if em is None else (em["movie_id"], em["reason"])
        if kp != km:
            mism += 1
            if mism < 8:
                print("MISMATCH end-of-clip rule", trial, "pod=", kp, "engine=", km)
        if em:
            fired[em["reason"].split(":")[0]] += 1
    print(f"compared against {POD_SOURCE}")
    print(f"search batches compared: {n_batches}   mismatches: {mism}")
    print("rules that fired on the engine side:", dict(sorted(fired.items())))
    expected = {"P1", "P2", "P2.5", "P3", "P4", "P5", "P5x", "P6", "P6a", "P7", "P7-strict-burst", "P8", "P9", "P9E"}
    missing = expected - set(fired)
    if missing:
        print("rules never reached by the test (the test needs work, not the engine):", sorted(missing))
    ok = mism == 0 and not missing
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

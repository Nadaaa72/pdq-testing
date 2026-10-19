# -*- coding: utf-8 -*-
"""
probe_walkthrough.py - walk one clip through the probe's three bars, showing the work.

    python probe_walkthrough.py data\clips\<clip> "Northman"

Collects exactly the evidence the probe V2 collects - through the engine's own ProbeRun,
so it cannot drift from it - then evaluates PV-A, PV-B and PV-C on the named film and
prints each bar's question, the actual numbers, and PASS or FAIL. This is the
demonstration of WHY a clip is accepted or refused, using the engine's real evidence.

It also shows WHEN: the probe samples in waves and judges after each one, so the table of
waves says how much of the clip it had to look at before the answer was settled. Unlike
the engine, this walks every wave to the end even once a bar has fired, because the point
here is to show the whole picture rather than to stop early.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("film", help="part of the film's name, e.g. Northman")
    ap.add_argument("--maxdim", type=int, default=None,
                    help="shrink each frame to this before hashing, as the engine can "
                         "(640 is the size the index was built at)")
    a = ap.parse_args()

    spec = importlib.util.spec_from_file_location("eng", HERE / "pdq_engine_PROBEV2.py")
    E = importlib.util.module_from_spec(spec)
    sys.modules["eng"] = E
    spec.loader.exec_module(E)
    index = E.load_index(str(HERE / "data" / "index"))
    w, h, dur = E.video_wh_duration(a.clip)
    qgroup = E.infer_query_group_from_wh(w, h)
    groups = [g for g in E.groups_for_clip_shape(qgroup) if g in index.index_by_group]

    # ---- collect the probe's evidence, through the engine's own ProbeRun ------------------
    # This used to be a third copy of the sampling loop, and it had already drifted: it never
    # applied maxdim, and it rebuilt the view list by hand. Going through ProbeRun means the
    # walkthrough can only ever show what the engine really does.
    run = E.ProbeRun(a.clip, index, groups, maxdim=a.maxdim)
    if not run.ok:
        print("that clip is unreadable, or 2 seconds or shorter - the probe skips it")
        return 0
    first_wave: dict = {}        # vidx -> the wave its evidence first showed up on
    wave_log = []                # [(wave, frames so far, the probe's verdict at that point)]
    try:
        for wi, idxs in enumerate(run.schedule(), 1):
            run.extend(idxs)
            for v in run.film_hits:
                first_wave.setdefault(v, wi)
            hit, _ = E.pv2_decide(run.film_hits)
            wave_log.append((wi, len(run.consumed), hit))
    finally:
        run.close()
    film_hits = run.film_hits

    target = next((v for v in film_hits if a.film.lower() in index.label(v).lower()), None)
    if target is None:
        print(f"'{a.film}' collected no evidence at all in this clip.")
        return 0

    rows = sorted(film_hits[target].values())
    print(f"clip: {Path(a.clip).name}")
    print(f"film examined: {index.label(target)}")
    print(f"\nTHE WAVES (the probe judges after each one, and stops as soon as it can):")
    print(f"  {'wave':>4}   {'frames':>6}   verdict at that point")
    for wi, nf, hit in wave_log:
        said = f"{index.label(hit['vidx'])} on {hit['tier']}" if hit else "stays quiet"
        print(f"  {wi:>4}   {nf:>6}   {said}")
    fired = next((w for w, _, h in wave_log if h), None)
    if fired:
        settled = next(nf for w, nf, h in wave_log if w == fired)
        print(f"  -> settled on wave {fired}, having looked at {settled} of "
              f"{run.n_samples} sampled frames")
    else:
        print(f"  -> never settled; all {run.n_samples} frames looked at, the rules take over")
    print(f"\nthis film's evidence first appeared on wave {first_wave.get(target, '-')}")
    print(f"\nTHE PROBE'S EVIDENCE for this film ({len(rows)} sampled frames hit it):")
    print(f"  {'clip time':>9}   {'film time':>9}   {'distance':>8}   {'offset':>9}")
    for d, ct, ft in rows:
        print(f"  {ct/60:6.2f}min   {ft/60:6.2f}min   {d:8d}   {(ft-ct)/60:6.2f}min")

    def aligned(rs):
        offs = sorted(ft - ct for _, ct, ft in rs)
        return max((sum(1 for o in offs if abs(o - o0) <= E.PV2_OFFSET_TOL_S) for o0 in offs), default=0)

    best = rows[0][0]
    a_f = [r for r in rows if r[0] < E.PV2_A_DIST]
    b_f = [r for r in rows if r[0] < E.PV2_B_DIST]
    c_f = [r for r in rows if r[0] < E.PV2_C_DIST]
    spread = E._unique_time_clusters([ct for _, ct, _ in c_f], E.PV2_SPREAD_S)

    print(f"\nTHE THREE BARS:")
    pa = best < E.PV2_A_BEST and len(a_f) >= E.PV2_A_FRAMES
    print(f"\n  PV-A  two near-identical frames?")
    print(f"        best={best:.0f} (needs <{E.PV2_A_BEST:.0f})   frames under {E.PV2_A_DIST:.0f}: {len(a_f)} (needs {E.PV2_A_FRAMES})")
    print(f"        -> {'PASS' if pa else 'FAIL'}")
    al_b = aligned(b_f)
    pb = best < E.PV2_B_BEST and len(b_f) >= E.PV2_B_FRAMES and al_b >= E.PV2_B_NEED_ALIGN
    print(f"\n  PV-B  decent frames that AGREE on film position?")
    print(f"        best={best:.0f} (needs <{E.PV2_B_BEST:.0f})   frames under {E.PV2_B_DIST:.0f}: {len(b_f)} (needs {E.PV2_B_FRAMES})")
    print(f"        hits agreeing on one offset: {al_b} (needs {E.PV2_B_NEED_ALIGN})")
    print(f"        -> {'PASS' if pb else 'FAIL'}")
    al_c = aligned(c_f)
    pc = (best < E.PV2_C_BEST and len(c_f) >= E.PV2_C_FRAMES and al_c >= E.PV2_C_NEED_ALIGN and spread >= E.PV2_C_NEED_SPREAD)
    print(f"\n  PV-C  mediocre frames, proven twice over?")
    print(f"        best={best:.0f} (needs <{E.PV2_C_BEST:.0f})   frames under {E.PV2_C_DIST:.0f}: {len(c_f)} (needs {E.PV2_C_FRAMES})")
    print(f"        agreeing: {al_c} (needs {E.PV2_C_NEED_ALIGN})   clip moments: {spread} (needs {E.PV2_C_NEED_SPREAD})")
    print(f"        -> {'PASS' if pc else 'FAIL'}")

    verdict = "ANSWER: " + index.label(target) if (pa or pb or pc) else "STAYS QUIET - the rules (or nothing) take over"
    print(f"\nVERDICT of the probe for this film: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

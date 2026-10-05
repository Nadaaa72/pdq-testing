# -*- coding: utf-8 -*-
"""
probe_walkthrough.py - walk one clip through the probe's three bars, showing the work.

    python probe_walkthrough.py data\clips\<clip> "Northman"

Collects exactly the evidence the probe V2 collects (same sampling, same views, same
per-film scorecard), then evaluates PV-A, PV-B and PV-C on the named film and prints
each bar's question, the actual numbers, and PASS or FAIL. This is the demonstration
of WHY a clip is accepted or refused, using the engine's real evidence.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("film", help="part of the film's name, e.g. Northman")
    a = ap.parse_args()

    spec = importlib.util.spec_from_file_location("eng", HERE / "pdq_engine_PROBEV2.py")
    E = importlib.util.module_from_spec(spec)
    sys.modules["eng"] = E
    spec.loader.exec_module(E)
    import cv2
    import numpy as np

    index = E.load_index(str(HERE / "data" / "index"))
    w, h, dur = E.video_wh_duration(a.clip)
    qgroup = E.infer_query_group_from_wh(w, h)
    groups = [g for g in E.groups_for_clip_shape(qgroup) if g in index.index_by_group]

    # ---- collect the probe's evidence, exactly as super_probe does -----------------------
    cap = cv2.VideoCapture(a.clip)
    samples = {g: [] for g in groups}
    for i in range(E.PV2_SAMPLES):
        t = dur * (i + 0.5) / E.PV2_SAMPLES
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, bgr = cap.read()
        if not ok or bgr is None:
            continue
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        views = [rgb]
        region = E.active_region(rgb)
        if region is not None:
            views.append(region)
        views += [np.ascontiguousarray(v[:, ::-1]) for v in list(views)]
        for vi, v in enumerate(views):
            targets = []
            if "FULL" in groups:
                targets.append(("FULL", v))
                if vi == 0:
                    sv = E.safe_trim_view(v)
                    if sv is not None:
                        targets.append(("FULL", sv))
            for c in E.CROPS:
                g = E.group_for_crop_name(c.name)
                if g in groups:
                    targets.append((g, E.center_crop_aspect(v, c.ar_w, c.ar_h, c.scale)))
            for g, img in targets:
                hb, q = E.pdq_hash(img)
                if q >= E.CLIP_QUALITY_MIN:
                    samples[g].append((i, t, hb))
    cap.release()

    film_hits: dict = defaultdict(dict)
    for g, sl in samples.items():
        if not sl:
            continue
        xq = np.frombuffer(b"".join(hb for _, _, hb in sl), dtype=np.uint8).reshape(-1, 32)
        D, I = index.index_by_group[g].search(xq, E.K_PER_HASH)
        for row in range(D.shape[0]):
            si, ct, _ = sl[row]
            for col in range(D.shape[1]):
                d = int(D[row, col]); nn = int(I[row, col])
                if nn < 0 or d >= E.MAX_HAMMING:
                    continue
                v = int(index.meta_vid[g][nn])
                cur = film_hits[v].get(si)
                if cur is None or d < cur[0]:
                    film_hits[v][si] = (d, ct, float(index.meta_ts[g][nn]))

    target = next((v for v in film_hits if a.film.lower() in index.label(v).lower()), None)
    if target is None:
        print(f"'{a.film}' collected no evidence at all in this clip.")
        return 0

    rows = sorted(film_hits[target].values())
    print(f"clip: {Path(a.clip).name}")
    print(f"film examined: {index.label(target)}")
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

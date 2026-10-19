# -*- coding: utf-8 -*-
"""
test_heldout.py - the engine on clips it was never fitted to.

    python test_heldout.py --engine pdq_engine_PROBEV2.py --probe-only
    python test_heldout.py --engine pdq_engine_PROBEV2.py --probe-only --passes

Reads data/heldout_clips.csv and the clips in data/clips_heldout/, both built by
get_heldout_clips.py. Every clip there was answered by a DIFFERENT engine and confirmed by a
user, and PDQ never answered it, so none of the probe's bars were tuned on any of them.
This is the only measurement in the repo that is not in-sample.

The two halves are scored differently, because they test opposite things:

  in-index   the film IS in data/index, so the right behaviour is to NAME it.
             right film / WRONG FILM / missed          -> recall, and whether it misleads
  out-index  the film is NOT in the index, so the right behaviour is to SAY NOTHING.
             quiet / FALSE POSITIVE                    -> the failure users actually notice

A caveat to carry into any quote of these numbers: the truth is another engine's answer plus
a user pressing "correct". Nobody re-checked the film by hand, so a careless press is
possible. It is far better evidence than the fitted suite, not perfect evidence.

Results: output/heldout_<engine>.csv (one row per clip, resumable) and two tables.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from attribute_rules import (load_engine, film_matches, stage_and_rule,  # noqa: E402
                             _scorecard_cells)
import metrics as M  # noqa: E402

OUT = HERE / "output"
CLIPS = HERE / "data" / "clips_heldout"
MANIFEST = HERE / "data" / "heldout_clips.csv"
FIELDS = ["clip", "pool", "truth_film", "truth_tmdb", "truth_engine", "answered_film",
          "verdict", "stage", "rule", "reason", "exit_kind", "query_s",
          # the hint bucket - see pv2_scorecard in the engine, and attribute_rules.FIELDS
          "hint_band", "hint_views", "hint_short", "scorecard"]


def truth_verdict(pool: str, answered: bool, label: str, job: dict) -> str:
    """What this answer means, given which half of the set the clip is in.

    The tmdb id is the truth where the engine's label carries one, because two films can
    share a title; the title match is the fallback, the same order metrics.py uses."""
    if pool == "out-index":
        # nothing in the index is this film, so ANY answer is a false positive
        return "FALSE POSITIVE" if answered else "quiet"
    if not answered:
        return "missed"
    by_id = M.tmdb_matches(label, {"answered_tmdb_id": str(job.get("truth_tmdb") or "")})
    if by_id is None:
        by_id = film_matches(label, job["truth_film"])
    return "right film" if by_id else "WRONG FILM"


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the held-out clips through one engine.")
    ap.add_argument("--engine", default="pdq_engine_PROBEV2.py")
    ap.add_argument("--probe-only", action="store_true", help="the probe V2 is the entire engine")
    ap.add_argument("--no-prescan", action="store_true")
    ap.add_argument("--passes", action="store_true",
                    help="turn on the staged two-pass probe (PDQ_PROBE_PASSES=1)")
    ap.add_argument("--tag", default="", help="suffix for the output file, to keep runs apart")
    a = ap.parse_args()

    if a.probe_only:
        os.environ["PDQ_PROBE_ONLY"] = "1"
    if a.passes:
        os.environ["PDQ_PROBE_PASSES"] = "1"

    if not MANIFEST.is_file():
        raise SystemExit("no data/heldout_clips.csv. Run get_heldout_clips.py first.")
    jobs = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))

    engine_path = HERE / a.engine
    E = load_engine(engine_path)
    index = E.load_index(str(HERE / "data" / "index"))

    tag = engine_path.stem.replace("pdq_engine_", "").replace("pdq_engine", "LIVE")
    if a.probe_only:
        tag += "_probeonly"
    if a.passes:
        tag += "_passes"
    if a.tag:
        tag += "_" + a.tag
    OUT.mkdir(exist_ok=True)
    out_csv = OUT / f"heldout_{tag}.csv"

    done = set()
    if out_csv.is_file():
        done = {r["clip"] for r in csv.DictReader(open(out_csv, encoding="utf-8"))}
        print(f"resuming: {len(done)} already done")
    new_file = not out_csv.is_file()
    fh = open(out_csv, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    if new_file:
        w.writeheader()
        fh.flush()

    # a clip whose download died is NOT a failure of the engine, so it is left out entirely
    # rather than scored as a miss, and counted separately at the end
    present, absent = [], []
    for job in jobs:
        hits = [p for p in sorted(CLIPS.glob(_safe(job["url"]) + ".*")) if p.stat().st_size > 0]
        (present if hits else absent).append((job, hits[0] if hits else None))

    print(f"engine: {engine_path.name}   held-out clips: {len(present)} of {len(jobs)} "
          f"downloaded   probe-only: {a.probe_only}   passes: {a.passes}")
    for i, (job, path) in enumerate(present, 1):
        name = path.name
        if name in done:
            continue
        t0 = time.time()
        try:
            r = E.identify_clip(str(path), index, verbose=False, prescan=not a.no_prescan)
        except Exception as e:
            w.writerow({"clip": name, "pool": job["pool"], "truth_film": job["truth_film"],
                        "truth_tmdb": job["truth_tmdb"], "truth_engine": job["truth_engine"],
                        "answered_film": "", "verdict": "ERROR", "stage": "", "rule": "",
                        "reason": str(e)[:200], "exit_kind": "",
                        "query_s": f"{time.time()-t0:.1f}"})
            fh.flush()
            print(f"[{i}/{len(present)}] {job['pool']:9} {job['truth_film'][:24]:26} ERROR {e}")
            continue
        verdict = truth_verdict(job["pool"], bool(r.early_accept), r.label or "", job)
        stage, rule = stage_and_rule(r.reason if r.early_accept else "", r.exit_kind)
        w.writerow({"clip": name, "pool": job["pool"], "truth_film": job["truth_film"],
                    "truth_tmdb": job["truth_tmdb"], "truth_engine": job["truth_engine"],
                    "answered_film": r.label or "", "verdict": verdict, "stage": stage,
                    "rule": rule, "reason": r.reason or r.exit_reason,
                    "exit_kind": r.exit_kind, "query_s": f"{r.query_seconds:.1f}",
                    **_scorecard_cells(E, index, r)})
        fh.flush()
        print(f"[{i}/{len(present)}] {job['pool']:9} {job['truth_film'][:24]:26} "
              f"{verdict:15} {rule:10} {r.query_seconds:5.1f}s")
    fh.close()

    report(out_csv, engine_path, absent, len(jobs))
    return 0


def _safe(url: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1])[:80]


def report(out_csv: Path, engine_path: Path, absent: list, n_manifest: int) -> None:
    rows = list(csv.DictReader(open(out_csv, encoding="utf-8")))
    inx = [r for r in rows if r["pool"] == "in-index"]
    out = [r for r in rows if r["pool"] == "out-index"]

    def n(sub, v):
        return sum(1 for r in sub if r["verdict"] == v)

    print()
    print("=" * 74)
    print(f"  HELD-OUT RESULT   (engine: {engine_path.name})")
    print("  Clips another engine answered and a user confirmed. None was used to fit a bar.")
    print("=" * 74)
    if absent:
        print(f"  {len(absent)} of {n_manifest} clips could not be downloaded (deleted posts);")
        print("  they are left out rather than counted as misses.")
        print()

    if inx:
        right, wrong, miss = n(inx, "right film"), n(inx, "WRONG FILM"), n(inx, "missed")
        print(f"  THE FILM IS IN THE INDEX  ({len(inx)} clips) - can it find it?")
        print(f"     named the right film     {right:4}   {100*right/len(inx):5.1f}%")
        print(f"     named the WRONG film     {wrong:4}   {100*wrong/len(inx):5.1f}%")
        print(f"     said nothing             {miss:4}   {100*miss/len(inx):5.1f}%")
        if right + wrong:
            print(f"     of the answers it gave, {100*right/(right+wrong):.1f}% were right")
        print()

    if out:
        quiet, fp = n(out, "quiet"), n(out, "FALSE POSITIVE")
        print(f"  THE FILM IS NOT IN THE INDEX  ({len(out)} clips) - does it stay quiet?")
        print(f"     stayed quiet (correct)   {quiet:4}   {100*quiet/len(out):5.1f}%")
        print(f"     answered anyway (wrong)  {fp:4}   {100*fp/len(out):5.1f}%")
        for r in out:
            if r["verdict"] == "FALSE POSITIVE":
                print(f"       {r['truth_film'][:26]:28} -> said {r['answered_film'][:34]:36} "
                      f"[{r['rule']}]")
        print()

    answered = [r for r in rows if r["verdict"] in ("right film", "WRONG FILM", "FALSE POSITIVE")]
    truly_right = n(inx, "right film")
    if answered:
        print(f"  OVERALL   it answered {len(answered)} of {len(rows)} clips; "
              f"{truly_right} of those answers were right "
              f"({100*truly_right/len(answered):.1f}% precision)")
    secs = sorted(float(r["query_s"] or 0) for r in rows)
    if secs:
        print(f"  SPEED     median {secs[len(secs)//2]:.1f}s   "
              f"p90 {secs[int(0.9*len(secs))]:.1f}s   total {sum(secs)/60:.1f} min")

    # which rules did the work, and which produced the mistakes
    for title, sub, bad in (("rules behind the right answers", inx, "right film"),
                            ("rules behind the WRONG answers", inx, "WRONG FILM"),
                            ("rules behind the FALSE POSITIVES", out, "FALSE POSITIVE")):
        tally: dict[str, int] = {}
        for r in sub:
            if r["verdict"] == bad:
                tally[r["rule"]] = tally.get(r["rule"], 0) + 1
        if tally:
            print(f"  {title}: "
                  + ", ".join(f"{k} x{v}" for k, v in sorted(tally.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    raise SystemExit(main())

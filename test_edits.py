# -*- coding: utf-8 -*-
"""
test_edits.py - how does the engine cope with edited clips?

    python test_edits.py --engine pdq_engine_ORIGINAL.py
    python test_edits.py --engine pdq_engine_PROBEV2.py --probe-only

Runs every clip in data/clips_edited/ (built by make_edited_clips.py) through the chosen
engine and answers, per KIND of edit: did the engine still name the right film, which rule
answered, and which edits break identification entirely.

Every source clip here was identified correctly before editing, so any failure is caused
by the edit and nothing else.

Results: output/edits_<engine>.csv (one row per clip, resumable) and a per-edit table.
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

from attribute_rules import load_engine, film_matches, stage_and_rule  # noqa: E402

OUT = HERE / "output"
FIELDS = ["clip", "film", "edit", "unedited_rule", "answered_film", "verdict",
          "stage", "rule", "reason", "exit_kind", "query_s"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Run every edited clip through one engine.")
    ap.add_argument("--engine", default="pdq_engine.py")
    ap.add_argument("--probe-only", action="store_true", help="the probe V2 is the entire engine")
    ap.add_argument("--no-prescan", action="store_true")
    a = ap.parse_args()

    if a.probe_only:
        os.environ["PDQ_PROBE_ONLY"] = "1"
    engine_path = HERE / a.engine
    E = load_engine(engine_path)
    index = E.load_index(str(HERE / "data" / "index"))

    manifest = HERE / "data" / "edited_clips.csv"
    if not manifest.is_file():
        raise SystemExit("no data/edited_clips.csv. Run make_edited_clips.py first.")
    jobs = list(csv.DictReader(open(manifest, encoding="utf-8")))

    tag = engine_path.stem.replace("pdq_engine_", "").replace("pdq_engine", "LIVE")
    if a.probe_only:
        tag += "_probeonly"
    if a.no_prescan:
        tag += "_noprescan"
    OUT.mkdir(exist_ok=True)
    out_csv = OUT / f"edits_{tag}.csv"

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

    print(f"engine: {engine_path.name}   edited clips: {len(jobs)}   probe-only: {a.probe_only}")
    for i, job in enumerate(jobs, 1):
        if job["file"] in done:
            continue
        path = HERE / "data" / "clips_edited" / job["file"]
        if not path.is_file():
            continue
        t0 = time.time()
        try:
            r = E.identify_clip(str(path), index, verbose=False, prescan=not a.no_prescan)
        except Exception as e:
            w.writerow({"clip": job["file"], "film": job["film"], "edit": job["edit"],
                        "unedited_rule": job["unedited_rule"], "answered_film": "", "verdict": "ERROR",
                        "stage": "", "rule": "", "reason": str(e)[:200], "exit_kind": "",
                        "query_s": f"{time.time()-t0:.1f}"})
            fh.flush()
            print(f"[{i}/{len(jobs)}] {job['edit']:10} {job['film'][:26]:28} ERROR {e}")
            continue
        if r.early_accept and film_matches(r.label, job["film"]):
            verdict = "right film"
        elif r.early_accept:
            verdict = "WRONG FILM"
        else:
            verdict = "no answer"
        stage, rule = stage_and_rule(r.reason if r.early_accept else "", r.exit_kind)
        w.writerow({"clip": job["file"], "film": job["film"], "edit": job["edit"],
                    "unedited_rule": job["unedited_rule"], "answered_film": r.label or "",
                    "verdict": verdict, "stage": stage, "rule": rule,
                    "reason": r.reason or r.exit_reason, "exit_kind": r.exit_kind,
                    "query_s": f"{r.query_seconds:.1f}"})
        fh.flush()
        print(f"[{i}/{len(jobs)}] {job['edit']:10} {job['film'][:26]:28} {verdict:11} {rule:10} {r.query_seconds:5.1f}s")
    fh.close()

    # ---- the per-edit table -------------------------------------------------------------
    rows = list(csv.DictReader(open(out_csv, encoding="utf-8")))
    edits = sorted({r["edit"] for r in rows})
    print("\n" + "=" * 70)
    print(f"  HOW EACH EDIT FARES   (engine: {engine_path.name}{', probe only' if a.probe_only else ''})")
    print("=" * 70)
    print(f"  {'edit':12} {'right film':>10} {'wrong film':>10} {'no answer':>10}   rules used")
    for e in edits:
        sub = [r for r in rows if r["edit"] == e]
        ok = sum(1 for r in sub if r["verdict"] == "right film")
        bad = sum(1 for r in sub if r["verdict"] == "WRONG FILM")
        no = sum(1 for r in sub if r["verdict"] == "no answer")
        rules = {}
        for r in sub:
            if r["verdict"] == "right film":
                rules[r["rule"]] = rules.get(r["rule"], 0) + 1
        rs = ",".join(f"{k}x{v}" for k, v in sorted(rules.items(), key=lambda x: -x[1]))
        print(f"  {e:12} {ok:>10} {bad:>10} {no:>10}   {rs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

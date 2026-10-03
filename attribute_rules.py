# -*- coding: utf-8 -*-
"""
attribute_rules.py - which rule decided each clip?

    python attribute_rules.py                                  (the live engine, both lists)
    python attribute_rules.py --engine pdq_engine_ORIGINAL.py  (the pod's rules)
    python attribute_rules.py --list wrong                     (just the wrong list)
    python attribute_rules.py --no-prescan                     (rules only, pre-scan off)

For every downloaded clip on the two lists it records WHICH PART of the engine produced
the answer: the pre-scan (SCAN), the probe (P0), a streaming rule (P1..P8), an end-of-clip
rule (P9E/P9), or nothing (reject / ran out). This is the answer to "which rule gave the
wrong answer" - every wrong answer in the output CSV comes with the rule that made it.

Results go to output/attribution_<engine>[_noprescan].csv, one row per clip, written as it
goes. A second run skips clips already in the CSV, so it can be stopped and resumed.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import os
import re
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
CLIPS = HERE / "data" / "clips"
OUT = HERE / "output"

FIELDS = ["list", "clip", "expected_film", "in_catalogue", "answered_film", "reproduced",
          "stage", "rule", "reason", "exit_kind", "frames", "avg_hamming", "wait_s",
          "duration_s", "query_s", "best_hint"]


def load_engine(path: Path):
    spec = importlib.util.spec_from_file_location("engine_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["engine_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def clip_file(url: str):
    safe = re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1])[:80]
    found = sorted(CLIPS.glob(f"{safe}.*"))
    return found[0] if found else None


def load_list(name: str, which: str):
    rows = list(csv.DictReader(open(HERE / "data" / name, encoding="utf-8")))
    out = []
    for r in rows:
        f = clip_file(r["url"])
        if f:
            out.append((which, r["answered_movie"], r.get("answered_in_catalogue", ""), f))
    return out


def film_matches(label: str | None, film: str) -> bool:
    """Same fuzzy match compare_before_after.py uses: the film name's first chunk."""
    if not label:
        return False
    key = re.split(r"[.:]", film)[0].strip()[:16].lower()
    return bool(key) and key in label.lower()


def stage_and_rule(reason: str, exit_kind: str) -> tuple[str, str]:
    """Pull the deciding stage and rule name out of the engine's reason string."""
    if not reason:
        if exit_kind == "NO_MATCH_REJECT":
            return "early-reject", "REJECT"
        return "no-answer", exit_kind
    head = re.split(r"[:(]", reason)[0].strip()
    if head.startswith("SCAN"):
        return "pre-scan", "SCAN"
    if head.startswith("PV-"):
        return "probe-v2", head
    if head == "P0":
        return "probe", "P0"
    if head in ("P9", "P9E"):
        return "end-of-clip", head
    return "streaming-rule", head


def main() -> int:
    ap = argparse.ArgumentParser(description="Record which rule decided every clip.")
    ap.add_argument("--engine", default="pdq_engine.py", help="which engine file to test")
    ap.add_argument("--list", choices=["wrong", "correct", "both"], default="both")
    ap.add_argument("--no-prescan", action="store_true", help="pre-scan off, the rules decide")
    ap.add_argument("--tag", default="", help="extra tag for the output file name")
    a = ap.parse_args()

    engine_path = HERE / a.engine
    if not engine_path.is_file():
        raise SystemExit(f"no such engine: {engine_path}")
    E = load_engine(engine_path)

    jobs = []
    if a.list in ("wrong", "both"):
        jobs += load_list("wrong_pdq_clips.csv", "wrong")
    if a.list in ("correct", "both"):
        jobs += load_list("correct_pdq_clips.csv", "correct")

    tag = engine_path.stem.replace("pdq_engine_", "").replace("pdq_engine", "LIVE")
    if a.no_prescan:
        tag += "_noprescan"
    if a.tag:
        tag += "_" + a.tag
    OUT.mkdir(exist_ok=True)
    out_csv = OUT / f"attribution_{tag}.csv"

    done = set()
    if out_csv.is_file():
        for r in csv.DictReader(open(out_csv, encoding="utf-8")):
            done.add((r["list"], r["clip"]))
        print(f"resuming: {len(done)} clips already in {out_csv.name}")

    index = E.load_index(str(HERE / "data" / "index"))
    print(f"engine: {engine_path.name}   index: {index.manifest.get('movies_count')} films, "
          f"{index.manifest.get('hashes_total'):,} fingerprints   clips: {len(jobs)}   prescan: {not a.no_prescan}")

    new_file = not out_csv.is_file()
    fh = open(out_csv, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    if new_file:
        w.writeheader()
        fh.flush()

    t_all = time.time()
    for i, (which, film, in_cat, path) in enumerate(jobs, 1):
        if (which, path.name) in done:
            continue
        t0 = time.time()
        try:
            r = E.identify_clip(str(path), index, verbose=False, prescan=not a.no_prescan)
        except Exception as e:  # a broken download must not kill the sweep
            w.writerow({"list": which, "clip": path.name, "expected_film": film, "in_catalogue": in_cat,
                        "answered_film": "", "reproduced": "", "stage": "ERROR", "rule": "ERROR",
                        "reason": str(e)[:200], "exit_kind": "", "frames": "", "avg_hamming": "",
                        "wait_s": "", "duration_s": "", "query_s": f"{time.time()-t0:.1f}", "best_hint": ""})
            fh.flush()
            print(f"[{i}/{len(jobs)}] {which:7} {film[:30]:32} ERROR {e}")
            continue
        stage, rule = stage_and_rule(r.reason if r.early_accept else "", r.exit_kind)
        st = r.movie_stats.get(r.vidx) if r.vidx is not None else None
        best_hint = ""
        if not r.early_accept and r.hints:
            v, rng, n, avg = r.hints[0]
            best_hint = f"{index.label(v)} frames={n} avg={avg:.1f}"
        w.writerow({
            "list": which, "clip": path.name, "expected_film": film, "in_catalogue": in_cat,
            "answered_film": r.label or "", "reproduced": "yes" if film_matches(r.label, film) else "no",
            "stage": stage, "rule": rule, "reason": r.reason or r.exit_reason, "exit_kind": r.exit_kind,
            "frames": (st["total_frames"] if st else ""),
            "avg_hamming": (f"{st['avg_ham']:.1f}" if st else ""),
            "wait_s": f"{r.wait_seconds:.0f}", "duration_s": f"{r.duration_s:.0f}",
            "query_s": f"{r.query_seconds:.1f}", "best_hint": best_hint,
        })
        fh.flush()
        mark = "ANSWERED" if r.early_accept else "no answer"
        print(f"[{i}/{len(jobs)}] {which:7} {film[:30]:32} {mark:10} {rule:12} {time.time()-t0:5.1f}s")
    fh.close()

    # ---- the summary: every answer attributed to its rule --------------------------------
    rows = list(csv.DictReader(open(out_csv, encoding="utf-8")))
    print(f"\nall clips done in {time.time()-t_all:.0f}s -> {out_csv}")
    print("\n" + "=" * 74)
    print("  WHICH RULE PRODUCED THE ANSWERS   (engine: " + engine_path.name + ")")
    print("=" * 74)
    for which, title in (("wrong", "WRONG answers reproduced (these rules are the problem)"),
                         ("correct", "CORRECT answers (these rules must keep working)")):
        sub = [r for r in rows if r["list"] == which and r["reproduced"] == "yes"]
        counts: dict[str, int] = {}
        for r in sub:
            counts[r["rule"]] = counts.get(r["rule"], 0) + 1
        print(f"\n  {title}: {len(sub)}")
        for rule, n in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"     {rule:10} {n}")
        if which == "wrong":
            for r in sub:
                print(f"       {r['rule']:10} {r['expected_film'][:34]:36} avg={r['avg_hamming']} frames={r['frames']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

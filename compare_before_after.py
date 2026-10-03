# -*- coding: utf-8 -*-
"""
compare_before_after.py - the measurement Jude asked for.

    python compare_before_after.py

Runs every clip you have downloaded through BOTH engines:

  pdq_engine_ORIGINAL.py    the pod's rules, untouched
  pdq_engine_MYCHANGES.py   your version

and prints the two numbers that matter:

  wrong answers removed   how many clips users said were WRONG stopped being answered
  right answers lost      how many clips users said were RIGHT stopped being answered

It only uses clips already sitting in data/clips/, so nothing is downloaded and
nothing can fail on the network. Clips you do not have are skipped and counted.

It swaps pdq_engine.py while it runs and always puts your version back at the end,
even if you press Ctrl+C.

Add --no-prescan to make the rules do the work instead of the whole-clip pre-scan.
Add --quick to run the wrong list only, which is faster while you are experimenting.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
PY = HERE / ".venv" / "Scripts" / "python.exe"
CLIPS = HERE / "data" / "clips"
LIVE = HERE / "pdq_engine.py"
ORIGINAL = HERE / "pdq_engine_ORIGINAL.py"
MINE = HERE / "pdq_engine_MYCHANGES.py"


def clip_file(url: str):
    safe = re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1])[:80]
    found = sorted(CLIPS.glob(f"{safe}.*"))
    return found[0] if found else None


def run_one(path: Path, no_prescan: bool) -> tuple[str, str]:
    """Returns (verdict line, rule line) for one clip."""
    cmd = [str(PY), "3_identify_clip.py", str(path)]
    if no_prescan:
        cmd.append("--no-prescan")
    try:
        out = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=2400).stdout or ""
    except subprocess.TimeoutExpired:
        return "TIMED OUT after 40 minutes", ""
    v = re.search(r"VERDICT:\s*(.+)", out)
    r = re.search(r"rule:\s*(.+)", out)
    return (v.group(1).strip() if v else "no verdict printed"), (r.group(1).strip() if r else "")


def answered_expected(verdict: str, film: str) -> bool:
    """Did the engine answer with the film we expected?"""
    if "no film" in verdict.lower():
        return False
    key = re.split(r"[.:]", film)[0].strip()[:16].lower()
    return bool(key) and key in verdict.lower()


def load(name: str):
    rows = list(csv.DictReader(open(HERE / "data" / name, encoding="utf-8")))
    out = []
    for r in rows:
        f = clip_file(r["url"])
        if f:
            out.append((r["answered_movie"], f))
    return out, len(rows)


def sweep(engine: Path, label: str, jobs, no_prescan: bool):
    shutil.copyfile(engine, LIVE)
    print(f"\n--- running {len(jobs)} clips with {label} " + "-" * 24)
    res = {}
    for film, path in jobs:
        verdict, rule = run_one(path, no_prescan)
        res[path.name] = (film, verdict, rule)
        mark = "answered" if not verdict.lower().startswith("no film") else "no answer"
        print(f"   {film[:34]:36} {mark:10} {rule[:44]}")
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare the original rules against your changed rules.")
    ap.add_argument("--no-prescan", action="store_true", help="skip the pre-scan so the rules decide")
    ap.add_argument("--quick", action="store_true", help="the wrong list only")
    a = ap.parse_args()

    for f in (ORIGINAL, MINE):
        if not f.is_file():
            raise SystemExit(f"missing {f.name}. Both engine versions must sit next to this script.")

    wrong_jobs, wrong_total = load("wrong_pdq_clips.csv")
    right_jobs, right_total = load("correct_pdq_clips.csv")
    if a.quick:
        right_jobs = []

    print(f"clips users said were WRONG:   {len(wrong_jobs)} of {wrong_total} downloaded")
    print(f"clips users said were CORRECT: {len(right_jobs)} of {right_total} downloaded")
    if a.no_prescan:
        print("pre-scan OFF - the rules decide")

    try:
        before_w = sweep(ORIGINAL, "the ORIGINAL rules", wrong_jobs, a.no_prescan)
        after_w = sweep(MINE, "YOUR rules", wrong_jobs, a.no_prescan)
        before_r = sweep(ORIGINAL, "the ORIGINAL rules", right_jobs, a.no_prescan) if right_jobs else {}
        after_r = sweep(MINE, "YOUR rules", right_jobs, a.no_prescan) if right_jobs else {}
    finally:
        shutil.copyfile(MINE, LIVE)
        print("\n(pdq_engine.py restored to your version)")

    removed, still_wrong = [], []
    for name, (film, v_before, rule_before) in before_w.items():
        was = answered_expected(v_before, film)
        now = answered_expected(after_w[name][1], film)
        if was and not now:
            removed.append((film, rule_before))
        elif was and now:
            still_wrong.append((film, after_w[name][2]))

    lost, kept = [], []
    for name, (film, v_before, _) in before_r.items():
        was = answered_expected(v_before, film)
        now = answered_expected(after_r[name][1], film)
        if was and not now:
            lost.append((film, after_r[name][2]))
        elif was and now:
            kept.append(film)

    print("\n" + "=" * 70)
    print("  THE TWO NUMBERS")
    print("=" * 70)
    print(f"  wrong answers removed : {len(removed)}")
    print(f"  right answers lost    : {len(lost)}")
    print("=" * 70)
    print(f"  wrong answers still there : {len(still_wrong)}")
    print(f"  right answers still fine  : {len(kept)}")

    if still_wrong:
        print("\n  still wrong, and the rule that answers each one now:")
        for f, rule in still_wrong:
            print(f"     {f[:40]:42} {rule}")
    if removed:
        print("\n  removed (good), and the rule that used to answer each one:")
        for f, rule in removed:
            print(f"     {f[:40]:42} {rule}")
    if lost:
        print("\n  LOST - these used to be right and now give no answer:")
        for f, rule in lost:
            print(f"     {f}")
        print("\n  Look at these first. Run one with:")
        print("     python 3_identify_clip.py data\\clips\\<the file> --no-prescan")
        print("  and read what the correct film's scorecard actually shows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

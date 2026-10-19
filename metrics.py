# -*- coding: utf-8 -*-
"""
metrics.py - turn an attribution CSV into the percentages.

    python metrics.py output\\attribution_PROBEV2_probeonly.csv
    python metrics.py output\\attribution_ORIGINAL.csv output\\attribution_PROBEV2_probeonly.csv
    python metrics.py --diff output\\attribution_ORIGINAL.csv output\\attribution_PROBEV2_probeonly.csv

attribute_rules.py records one row per clip: which rule answered, and whether the answer
matched what we expect. It counts, but it does not divide. This divides.

Three numbers matter and they are not the same number:

  precision   of the answers PDQ gave, how many were right. The number to protect:
              a wrong answer is worse than no answer.
  recall      of the clips that COULD be identified, how many were. The number to grow.
  candidate   was the right film anywhere in PDQ's own hints, even when it refused to
  recall      answer? The gap between this and recall is what better rules can win
              without a single extra index search.

Ground truth is a user's vote on a real Trace answer, so "correct list" means a user
confirmed the answer and "wrong list" means a user rejected it. See 4_pull_wrong_pdq_clips.py.
"""
from __future__ import annotations

import argparse
import csv
import glob
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIPS = HERE / "data" / "clips"

YES = ("1", "true", "yes", "y")


# ---- joining an attribution row back to its ground-truth row --------------------------------

def clip_stem(url: str) -> str:
    """The slug attribute_rules.clip_file builds from a url. Kept identical on purpose - if
    that slug ever changes, this must change with it or the tmdb audit goes quiet."""
    return re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1])[:80]


def load_truth() -> dict:
    """clip filename -> its ground-truth row, from the two vote lists."""
    truth = {}
    for name, which in (("wrong_pdq_clips.csv", "wrong"), ("correct_pdq_clips.csv", "correct")):
        p = HERE / "data" / name
        if not p.is_file():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            found = sorted(CLIPS.glob(clip_stem(r["url"]) + ".*")) if CLIPS.is_dir() else []
            if found:
                r["_list"] = which
                truth[found[0].name] = r
    return truth


# ---- the two ways of asking "is this the film we expected?" ---------------------------------

def fuzzy_matches(label: str, film: str) -> bool:
    """attribute_rules.film_matches, copied so this script runs on its own."""
    if not label:
        return False
    key = re.split(r"[.:]", film)[0].strip()[:16].lower()
    return bool(key) and key in label.lower()


def tmdb_of(label: str) -> str:
    """The tmdb id an index label carries: 290:The Northman (tmdb=639933) -> 639933."""
    m = re.search(r"tmdb=(\d+)", label or "")
    return m.group(1) if m else ""


def tmdb_matches(label: str, truth_row: dict | None):
    """True/False on an exact tmdb id match, or None when we cannot tell."""
    if not label or not truth_row:
        return None
    want = (truth_row.get("answered_tmdb_id") or "").strip()
    got = tmdb_of(label)
    if not want or not got:
        return None
    return want == got


# ---- reading the attribution rows -----------------------------------------------------------

HINT_RE = re.compile(r"frames=(\d+)\s+avg=([0-9.]+)")


def parse_hint(hint: str):
    m = HINT_RE.search(hint or "")
    return (int(m.group(1)), float(m.group(2))) if m else None


class Row:
    def __init__(self, d: dict, truth: dict):
        self.d = d
        self.truth = truth.get(d["clip"])
        self.lst = d["list"].strip()
        self.rule = d["rule"].strip()
        self.stage = d["stage"].strip()
        self.in_cat = (d.get("in_catalogue") or "").strip().lower() in YES
        self.answered = bool(d["answered_film"].strip())
        # Prefer the exact tmdb id over the fuzzy title match. The fuzzy test compares the
        # first 16 characters of the title against the index label, and index labels are
        # sometimes release names (Don't.Say.Good.Luck.2026.1080p...), so it reports "no"
        # for answers that are in fact right. Fall back to it only when no tmdb id is on
        # one of the two sides. The audit at the end of the report counts the disagreements.
        self.fuzzy = d["reproduced"].strip() == "yes"
        t = tmdb_matches(d["answered_film"], self.truth)
        self.by_tmdb = t is not None
        repro = t if self.by_tmdb else self.fuzzy
        # On the correct list the expected film IS the truth, so reproducing it is a right
        # answer. On the wrong list the expected film is the answer a user REJECTED, so
        # reproducing it is a wrong answer and any OTHER answer has unknown truth.
        self.right = self.answered and self.lst == "correct" and repro
        self.known_wrong = self.answered and self.lst == "wrong" and repro
        self.unknown = self.answered and not self.right and not self.known_wrong

    def hint_is_right_film(self) -> bool:
        """Was the expected film the probe's own top hint? Same tmdb-first rule as above -
        the hint carries a full index label, release names and all."""
        hint = self.d["best_hint"].strip()
        if not hint:
            return False
        t = tmdb_matches(hint, self.truth)
        return t if t is not None else fuzzy_matches(hint, self.d["expected_film"])


def pct(n: int, d: int) -> str:
    return "{:5.1f}%".format(100.0 * n / d) if d else "    - "


# ---- the report -----------------------------------------------------------------------------

def report(path: Path, truth: dict) -> dict:
    rows = [Row(d, truth) for d in csv.DictReader(open(path, encoding="utf-8"))]
    answers = [r for r in rows if r.answered]
    right = [r for r in answers if r.right]
    kwrong = [r for r in answers if r.known_wrong]
    unknown = [r for r in answers if r.unknown]

    corr_all = [r for r in rows if r.lst == "correct"]
    corr_in = [r for r in corr_all if r.in_cat]
    wrong_all = [r for r in rows if r.lst == "wrong"]
    wrong_answered = [r for r in wrong_all if r.answered]

    print("=" * 78)
    print("  " + path.name)
    print("=" * 78)
    print("  clips                        {:4d}   ({} user-confirmed, {} user-rejected)".format(
        len(rows), len(corr_all), len(wrong_all)))
    print("  answers given                {:4d}".format(len(answers)))
    print("    right                      {:4d}".format(len(right)))
    print("    known-wrong                {:4d}   (a user rejected this exact answer)".format(len(kwrong)))
    print("    truth unknown              {:4d}   (answered a film with no vote either way)".format(len(unknown)))
    print()
    print("  THE PERCENTAGES")
    print("    % of flags right           {}   {}/{}   <- precision, protect this".format(
        pct(len(right), len(answers)), len(right), len(answers)))
    print("    % ... ignoring unknowns    {}   {}/{}".format(
        pct(len(right), len(answers) - len(unknown)), len(right), len(answers) - len(unknown)))
    print("    % of identifiable found    {}   {}/{}   <- recall, of in-catalogue confirmed clips".format(
        pct(len(right), len(corr_in)), len(right), len(corr_in)))
    print("    % of all confirmed found   {}   {}/{}".format(
        pct(len(right), len(corr_all)), len(right), len(corr_all)))
    print("    % of rejected refused      {}   {}/{}   <- stayed quiet as it should".format(
        pct(len(wrong_all) - len(wrong_answered), len(wrong_all)),
        len(wrong_all) - len(wrong_answered), len(wrong_all)))

    # ---- per rule ---------------------------------------------------------------------------
    print()
    print("  WHICH RULE, AND HOW MUCH TO TRUST IT")
    print("    {:12} {:14} {:>5} {:>5} {:>5} {:>5}  precision".format(
        "rule", "stage", "fired", "right", "wrong", "unkn"))
    by_rule: dict = {}
    for r in answers:
        by_rule.setdefault((r.rule, r.stage), []).append(r)
    for (rule, stage), rs in sorted(by_rule.items(), key=lambda kv: -len(kv[1])):
        nr = sum(1 for x in rs if x.right)
        nw = sum(1 for x in rs if x.known_wrong)
        nu = sum(1 for x in rs if x.unknown)
        print("    {:12} {:14} {:5d} {:5d} {:5d} {:5d}  {}".format(
            rule, stage, len(rs), nr, nw, nu, pct(nr, len(rs))))

    # ---- candidate recall: what better rules could still win --------------------------------
    declined = [r for r in corr_in if not r.answered]
    in_hints = [r for r in declined if r.hint_is_right_film()]
    ceiling = len(right) + len(in_hints)
    print()
    print("  CANDIDATE RECALL - of the clips it refused, where was the right film?")
    print("    refused, film in catalogue  {:4d}".format(len(declined)))
    print("    right film WAS its top hint {:4d}   <- reachable by rules alone, no extra search".format(
        len(in_hints)))
    print("    right film not found at all {:4d}   <- a sampling or fingerprint limit, not a rule".format(
        len(declined) - len(in_hints)))
    print("    ceiling on recall           {}   {}/{}  (today {})".format(
        pct(ceiling, len(corr_in)), ceiling, len(corr_in), pct(len(right), len(corr_in)).strip()))
    if in_hints:
        bands = {"strong <=20": 0, "medium 20-35": 0, "weak >35": 0}
        frames = {"1 frame": 0, "2-3": 0, "4-9": 0, "10+": 0}
        for r in in_hints:
            h = parse_hint(r.d["best_hint"])
            if not h:
                continue
            n, avg = h
            bands["strong <=20" if avg <= 20 else "medium 20-35" if avg <= 35 else "weak >35"] += 1
            frames["1 frame" if n == 1 else "2-3" if n <= 3 else "4-9" if n <= 9 else "10+"] += 1
        print("      by hint distance   " + str(bands))
        print("      by frame count     " + str(frames))

    # ---- the same question on the wrong list: who is waiting at the door --------------------
    risk = [r for r in wrong_all if not r.answered and r.hint_is_right_film()]
    strong_risk = [r for r in risk if (parse_hint(r.d["best_hint"]) or (0, 99.0))[1] <= 30]
    print()
    print("  PRECISION RISK - rejected films still sitting in the hints")
    print("    rejected answer is top hint {:4d}   of {} rejected clips".format(len(risk), len(wrong_all)))
    print("    ... at distance 30 or better{:4d}   <- these return if any bar is loosened".format(
        len(strong_risk)))
    for r in sorted(strong_risk, key=lambda x: (parse_hint(x.d["best_hint"]) or (0, 99.0))[1]):
        n, avg = parse_hint(r.d["best_hint"])
        print("        {:38} frames={:<3} avg={:.1f}".format(r.d["expected_film"][:36], n, avg))

    # ---- is the fuzzy title match lying to us? ----------------------------------------------
    checked = [r for r in answers if r.by_tmdb]
    disagree = [r for r in checked if tmdb_matches(r.d["answered_film"], r.truth) != r.fuzzy]
    print()
    print("  LABEL MATCHING AUDIT - exact tmdb id (used above) vs the fuzzy title match")
    print("    answers where both can be checked {:4d} of {}".format(len(checked), len(answers)))
    print("    they disagree                     {:4d}".format(len(disagree)))
    for r in disagree:
        t = tmdb_matches(r.d["answered_film"], r.truth)
        print("        {:42} tmdb={:3} fuzzy={:3}  expected={} answered={}".format(
            r.d["clip"][:40], "yes" if t else "no", "yes" if r.fuzzy else "no",
            r.d["expected_film"][:24], r.d["answered_film"][:34]))
    if disagree:
        print("        -> the attribution CSV's own 'reproduced' column is wrong on these;"
              " the counts above are corrected")
    elif checked:
        print("        none - the counts in this file are safe to quote")
    print()
    return {"path": path, "right": len(right), "known_wrong": len(kwrong),
            "answers": len(answers), "corr_in": len(corr_in), "ceiling": ceiling}


def diff(a: Path, b: Path, truth: dict) -> None:
    ra = {r["clip"]: Row(r, truth) for r in csv.DictReader(open(a, encoding="utf-8"))}
    rb = {r["clip"]: Row(r, truth) for r in csv.DictReader(open(b, encoding="utf-8"))}
    shared = [c for c in ra if c in rb]
    print("=" * 78)
    print("  {}   ->   {}      ({} clips in both)".format(a.name, b.name, len(shared)))
    print("=" * 78)
    buckets = (
        ("right answers LOST", [c for c in shared if ra[c].right and not rb[c].right]),
        ("right answers GAINED", [c for c in shared if rb[c].right and not ra[c].right]),
        ("wrong answers REMOVED", [c for c in shared if ra[c].known_wrong and not rb[c].known_wrong]),
        ("wrong answers ADDED", [c for c in shared if rb[c].known_wrong and not ra[c].known_wrong]),
    )
    for title, cs in buckets:
        print("\n  {}: {}".format(title, len(cs)))
        for c in cs:
            x, y = ra[c], rb[c]
            print("     {:36} {:26} -> {}".format(
                x.d["expected_film"][:34], x.stage + "/" + x.rule, y.stage + "/" + y.rule))
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="Percentages from an attribution CSV.")
    ap.add_argument("csv", nargs="+", help="output/attribution_*.csv (globs allowed)")
    ap.add_argument("--diff", action="store_true", help="compare the first two files instead")
    a = ap.parse_args()

    paths = []
    for pat in a.csv:
        hits = sorted(glob.glob(pat))
        paths += [Path(h) for h in hits] if hits else [Path(pat)]
    for p in paths:
        if not p.is_file():
            raise SystemExit("no such file: " + str(p))

    truth = load_truth()
    if not truth:
        print("warning: no ground-truth lists under data/ - the tmdb audit will be empty\n")

    if a.diff:
        if len(paths) < 2:
            raise SystemExit("--diff needs two files")
        diff(paths[0], paths[1], truth)
        return 0

    summaries = [report(p, truth) for p in paths]
    if len(summaries) > 1:
        print("=" * 78)
        print("  SIDE BY SIDE")
        print("=" * 78)
        print("    {:34} {:>7} {:>6} {:>6} {:>10} {:>8} {:>8}".format(
            "engine", "answers", "right", "wrong", "precision", "recall", "ceiling"))
        for s in summaries:
            print("    {:34} {:7d} {:6d} {:6d} {:>10} {:>8} {:>8}".format(
                s["path"].stem.replace("attribution_", ""), s["answers"], s["right"],
                s["known_wrong"], pct(s["right"], s["answers"]),
                pct(s["right"], s["corr_in"]), pct(s["ceiling"], s["corr_in"])))
        print()
        print("    recall  = right answers / the 81 confirmed clips whose film is in the index")
        print("    ceiling = recall it could reach on its OWN hints, with better rules only.")
        print("              Compare ceilings between engines with care: an engine that")
        print("              early-rejects a clip records no hints for it, so its ceiling")
        print("              reads low because it stopped looking, not because nothing was there.")
        print()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())

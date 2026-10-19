# -*- coding: utf-8 -*-
"""
two_pass_lab.py - design the probe's passes against saved evidence, in a second.

    python two_pass_lab.py --tag edited --yield           which views carry the matches
    python two_pass_lab.py --tag edited --order           uncropped first or cropped first
    python two_pass_lab.py --tag edited --sizes           sweep both passes' sample sizes
    python two_pass_lab.py --tag edited --budget 1.5      the sample sizes that fit 1.5 s
    python two_pass_lab.py --tag edited --fallback        does a denser third pass help
    python two_pass_lab.py --tag cells --order            the same, on the 125 real clips
    python two_pass_lab.py --calibrate                    measure this machine's search rate

WHY THIS FILE EXISTS

A pass is a choice of three things: WHICH FRAMES it samples, WHICH PICTURES it takes from
each frame, and WHAT RULES judge the result. dump_probe_evidence.py saves one row per
(clip, film, sampled frame, group, view), so every one of those choices can be replayed
against evidence already on disk instead of re-decoding 80 or 125 videos per idea.

  group FULL  the whole frame and its safe-trimmed copy    -> the UNCROPPED pass
  any other   a centred crop of the frame                  -> the CROPPED pass
  view p      the frame as shot
  view x      its mirrored or letterbox-trimmed copy

The two passes take DIFFERENT frames. sample_order is a permutation whose every prefix is
spread over the whole clip, so pass one takes the first N1 of it and pass two the next N2 -
each spread over the whole clip, and no frame sampled twice. Pass two is also handed pass
one's frames already decoded, so it can take its own pictures from them for the price of the
hashing alone: --reuse measures whether that is worth doing.

WHAT THE COST MODEL IS

Seconds are modelled per clip from what that clip actually measured in its dump:

    seek    frames decoded     x  (its seek_s / its frames_decoded)
    hash    pictures taken     x  (its hash_s / its n_hashes)
    search  query rows, by shard, x that shard's measured seconds per row

The picture count per frame is the engine's own rule (_probe_targets), then scaled so the
whole-frame total matches the n_hashes the dump recorded - which is what keeps letterboxed
clips and the quality gate honest instead of assumed. Run --calibrate once to measure the
per-shard search rate on this machine; every report says which rates it used.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import metrics as M                                      # noqa: E402
import replay_rules as R                                 # noqa: E402
from pv2_waves import sample_order                       # noqa: E402

OUT = HERE / "output"
CALIB = OUT / "search_cost.json"

UNCROPPED = "FULL"
CROPPED = ("PORTRAIT", "SQUARE", "LANDSCAPE")
# How many centred crops each family contributes per view: 4x5 and 9x16 at two scales for
# PORTRAIT, 1x1 at two scales for SQUARE, 16x9 at two scales for LANDSCAPE.
CROPS_PER_GROUP = {"PORTRAIT": 4, "SQUARE": 2, "LANDSCAPE": 2}
# How many fingerprints each shard holds. Used as the RELATIVE weight of one query against
# one shard versus another, because a flat binary index reads every row - so a query against
# PORTRAIT costs about 3.8 times one against FULL. The absolute level never comes from here;
# it comes from the clip's own measured search_s. See the module docstring on why the
# seconds-per-row table was abandoned.
SHARD_ROWS = {"FULL": 1912233, "PORTRAIT": 7291521, "SQUARE": 3735250, "LANDSCAPE": 3805496}


def shard_rows() -> tuple:
    """Shard sizes from the index manifest when it is there, else the values above."""
    try:
        man = json.load(open(HERE / "data" / "index" / "manifest.json", encoding="utf-8"))
        got = {g: int(v.get("n", 0)) for g, v in (man.get("groups") or {}).items()}
        if got and all(got.values()):
            return got, "shard sizes from the index manifest"
    except Exception:
        pass
    return dict(SHARD_ROWS), "built-in shard sizes"


# ---- the evidence ---------------------------------------------------------------------------

class Clip:
    """One clip's per-cell evidence, plus what its dump measured it cost."""

    def __init__(self, row: dict):
        self.name = row["clip"]
        self.list = row.get("list", "")
        self.edit = row.get("edit", "")
        self.expected = row.get("expected_film", "")
        self.n_samples = int(row.get("n_samples") or 0) or 40
        self.collect_s = float(row.get("collect_s") or 0.0)
        self.seek_s = float(row.get("seek_s") or 0.0)
        self.hash_s = float(row.get("hash_s") or 0.0)
        self.search_s = float(row.get("search_s") or 0.0)
        self.n_hashes = int(row.get("n_hashes") or 0)
        self.frames_decoded = int(row.get("frames_decoded") or 0) or self.n_samples
        self.groups = [g for g in (row.get("groups") or "").split("|") if g]
        self.note = row.get("note", "")
        # A clip the probe never got to fingerprint is not a recall failure, it is a broken
        # file. Two of the 80 edited clips are unreadable - one is 0 bytes - and counting
        # them as misses quietly penalises whichever edits they happen to be.
        self.readable = self.n_hashes > 0 and not self.note.startswith("ERROR")
        self.cells: dict = {}      # (vidx, sample_i, group, view) -> (dist, clip_t, film_t, target)
        self.labels: dict = {}
        self.truth = None

    # -- cost units, from this clip's own measurement ----------------------------------------
    @property
    def seek_per_frame(self) -> float:
        return self.seek_s / max(self.frames_decoded, 1)

    @property
    def hash_per_target(self) -> float:
        return self.hash_s / max(self.n_hashes, 1)

    def nominal_rows(self, groups, views) -> dict:
        """Pictures per frame, by shard, as _probe_targets would take them."""
        out = {}
        for g in self.groups:
            if g not in groups:
                continue
            if g == UNCROPPED:
                n = (2 if "p" in views else 0) + (1 if "x" in views else 0)
            else:
                n = CROPS_PER_GROUP.get(g, 2) * (("p" in views) + ("x" in views))
            if n:
                out[g] = n
        return out

    @property
    def target_scale(self) -> float:
        """Correction so the nominal count matches the hashes the dump really recorded.

        A letterboxed clip has a third extra view, and the quality gate drops some pictures
        entirely, so the nominal rule over- or under-counts. One factor per clip keeps the
        model anchored to measurement."""
        nominal = sum(self.nominal_rows(set(self.groups), "px").values())
        if not nominal or not self.frames_decoded:
            return 1.0
        return (self.n_hashes / self.frames_decoded) / nominal

    def rows_for(self, vidx, frames=None, groups=None, views=None):
        """This film's evidence under a pass, reduced the way the engine reduces it: the best
        hit per sampled frame, taking the minimum over the cells this pass can see."""
        best = {}
        for (v, si, g, vc), cell in self.cells.items():
            if v != vidx:
                continue
            if frames is not None and si not in frames:
                continue
            if groups is not None and g not in groups:
                continue
            if views is not None and vc not in views:
                continue
            cur = best.get(si)
            if cur is None or cell[0] < cur[0]:
                best[si] = cell
        return sorted((c[0], c[1], c[2]) for c in best.values())

    def films(self, frames=None, groups=None, views=None) -> set:
        out = set()
        for (v, si, g, vc) in self.cells:
            if frames is not None and si not in frames:
                continue
            if groups is not None and g not in groups:
                continue
            if views is not None and vc not in views:
                continue
            out.add(v)
        return out


def load(tag: str) -> list:
    suffix = ("_" + tag) if tag else ""
    clips_csv = OUT / ("probe_evidence_clips%s.csv" % suffix)
    hits_csv = OUT / ("probe_evidence%s.csv" % suffix)
    if not clips_csv.is_file():
        raise SystemExit("no %s - run:  python dump_probe_evidence.py --tag %s%s"
                         % (clips_csv.name, tag, " --edited" if "edit" in tag else ""))
    clips = {}
    for r in csv.DictReader(open(clips_csv, encoding="utf-8")):
        clips[r["clip"]] = Clip(r)
    if not hits_csv.is_file():
        raise SystemExit("no %s" % hits_csv.name)
    checked = False
    for r in csv.DictReader(open(hits_csv, encoding="utf-8")):
        if not checked:
            if "group" not in r or "view" not in r:
                raise SystemExit(
                    "%s has no group/view columns, so a pass cannot be simulated from it.\n"
                    "Re-dump with the current dump_probe_evidence.py." % hits_csv.name)
            checked = True
        c = clips.get(r["clip"])
        if c is None:
            continue
        v = int(r["vidx"])
        k = (v, int(r["sample_i"]), r["group"], r["view"])
        cell = (float(r["distance"]), float(r["clip_t"]), float(r["film_t"]), r["target"])
        cur = c.cells.get(k)
        if cur is None or cell[0] < cur[0]:
            c.cells[k] = cell
        c.labels[v] = r["film_label"]
    truth = M.load_truth()
    for c in clips.values():
        c.truth = truth.get(c.name)
    out = list(clips.values())
    bad = [c for c in out if not c.readable]
    if bad:
        print("  NOTE: %d of %d clips in this dump produced no fingerprints at all and are"
              % (len(bad), len(out)))
        print("        left out of every count below - they are broken files, not misses:")
        for c in bad[:6]:
            print("          %-52s %s" % (c.name[:52], (c.note or "no hashes")[:34]))
    return [c for c in out if c.readable]


def reproduces(clip: Clip, label: str) -> bool:
    """Does this answer name the clip's EXPECTED film? Not the same as being right - see
    verdict. The edited suite judges by film name as test_edits.py does; the vote lists
    judge by tmdb id first, falling back to the title, as metrics.py does."""
    if not label:
        return False
    if clip.list == "edited":
        import attribute_rules as AR
        return AR.film_matches(label, clip.expected)
    t = M.tmdb_matches(label, clip.truth)
    return t if t is not None else M.fuzzy_matches(label, clip.expected)


def verdict(clip: Clip, label: str) -> str:
    """"right", "wrong" or "unknown".

    On the edited suite and the "correct" vote list the expected film is the truth, so
    reproducing it is a right answer. On the "wrong" list the expected film is the answer a
    user REJECTED, so reproducing it is a KNOWN-WRONG answer, and any other answer has
    unknown truth - nothing records what those clips really are. Same rule as metrics.Row
    and replay_rules.score; ignoring it makes a known-wrong answer look like a right one."""
    if not label:
        return "unknown"
    rep = reproduces(clip, label)
    if clip.list == "wrong":
        return "wrong" if rep else "unknown"
    return "right" if rep else "unknown"


def correct(clip: Clip, label: str) -> bool:
    """Shorthand for a right answer, for the callers that only care about that."""
    return verdict(clip, label) == "right"


# ---- judging, and costing, one pass ---------------------------------------------------------

def judge(clip: Clip, frames, groups, views, thresholds=None, active=None):
    """What the rulebook says about this pass's evidence, or None if it stays quiet.

    Uses replay_rules.bars_for_film, so these are the bars the engine ships and there is no
    second copy of the rulebook to drift out of step."""
    t = thresholds or R.DEFAULTS
    active = active or set(R.ADOPTED)
    seen = clip.films(frames, groups, views)
    sole = len(seen) == 1
    best = None
    for v in seen:
        rows = clip.rows_for(v, frames, groups, views)
        if not rows:
            continue
        for name, detail in R.bars_for_film(rows, t, sole):
            if name not in active:
                continue
            cl = R.offset_clusters(rows)
            key = (-R.TIER_RANK[name], len(cl[0]) if cl else 0, -rows[0][0])
            if best is None or key > best[0]:
                best = (key, v, name, detail, rows)
    if best is None:
        return None
    _, v, name, detail, rows = best
    return {"vidx": v, "rule": name, "detail": detail, "label": clip.labels.get(v, str(v)),
            "rows": rows}


def cost(clip: Clip, n_frames: int, groups, views, nrows: dict, decode: bool = True) -> dict:
    """Seconds for one pass over n_frames of this clip, scaled from ITS OWN measurements.

    No cross-clip model and no per-shard seconds table - see the note in cmd_fit_search for
    why both were abandoned. Each term is the clip's measured total times the fraction of
    that work this pass does, so a pass that takes a quarter of the pictures is charged a
    quarter of the hashing this clip really spent."""
    rows = clip.nominal_rows(groups, views)
    full = clip.nominal_rows(set(clip.groups), "px")
    targets = sum(rows.values()) * n_frames
    seek = (clip.seek_s * n_frames / max(clip.frames_decoded, 1)) if decode else 0.0
    # hash: pictures taken, as a share of the pictures the clip really hashed
    full_targets = sum(full.values()) * clip.frames_decoded
    hashing = clip.hash_s * (targets / full_targets) if full_targets else 0.0
    # search: query WORK, where one query costs in proportion to the shard it reads
    work = sum(n * n_frames * nrows.get(g, 1) for g, n in rows.items())
    full_work = sum(n * clip.frames_decoded * nrows.get(g, 1) for g, n in full.items())
    search = clip.search_s * (work / full_work) if full_work else 0.0
    return {"seek": seek, "hash": hashing, "search": search,
            "total": seek + hashing + search, "targets": targets}


def frames_of(clip: Clip, start: int, n: int) -> set:
    """n frames from the spread order, starting at position `start` - so two passes asking
    for (0, N1) and (N1, N2) get disjoint sets, each spread over the whole clip."""
    order = sample_order(clip.n_samples)
    return set(order[start:start + n])


# ---- reports --------------------------------------------------------------------------------

def cmd_yield(clips) -> None:
    """Which pictures actually carry the matches. This is the question that decides the
    pass order, and it cannot be answered from an older dump at all."""
    print("\n  WHICH PICTURES CARRY THE MATCHES   (%d clips, all %d sampled frames)"
          % (len(clips), clips[0].n_samples if clips else 0))
    print("  A clip counts for a cell group if the rulebook would ACCEPT on that group alone.\n")
    combos = [("uncropped only", {UNCROPPED}, "px"),
              ("cropped only", set(CROPPED), "px"),
              ("uncropped, plain", {UNCROPPED}, "p"),
              ("uncropped, mirrored", {UNCROPPED}, "x"),
              ("cropped, plain", set(CROPPED), "p"),
              ("cropped, mirrored", set(CROPPED), "x"),
              ("everything", {UNCROPPED} | set(CROPPED), "px")]
    print("  %-22s %8s %8s %8s   %s" % ("pictures", "accepts", "right", "wrong", "best distance seen"))
    print("  " + "-" * 78)
    for lab, groups, views in combos:
        acc = right = wrong = 0
        bests = []
        for c in clips:
            d = judge(c, None, groups, views)
            allrows = [c.rows_for(v, None, groups, views) for v in c.films(None, groups, views)]
            flat = [r[0] for rows in allrows for r in rows]
            if flat:
                bests.append(min(flat))
            if d:
                acc += 1
                v = verdict(c, d["label"])
                right += int(v == "right")
                wrong += int(v == "wrong")
        med = ("%.0f" % statistics.median(bests)) if bests else "-"
        print("  %-22s %8d %8d %8d   median %s over %d clips with any hit"
              % (lab, acc, right, wrong, med, len(bests)))

    # and per edit, if this is the edited suite
    if any(c.edit for c in clips):
        print("\n  BY EDIT - which pass would catch it (accepts on that group alone)\n")
        print("  %-12s %7s %10s %9s %9s" % ("edit", "clips", "uncropped", "cropped", "either"))
        print("  " + "-" * 54)
        by = defaultdict(list)
        for c in clips:
            by[c.edit].append(c)
        for e in sorted(by):
            cs = by[e]
            u = sum(1 for c in cs if (lambda d: bool(d) and correct(c, d["label"]))(
                judge(c, None, {UNCROPPED}, "px")))
            k = sum(1 for c in cs if (lambda d: bool(d) and correct(c, d["label"]))(
                judge(c, None, set(CROPPED), "px")))
            b = sum(1 for c in cs if (lambda d: bool(d) and correct(c, d["label"]))(
                judge(c, None, {UNCROPPED} | set(CROPPED), "px")))
            print("  %-12s %7d %10d %9d %9d" % (e, len(cs), u, k, b))


def _two_pass(clip, n1, n2, g1, v1, g2, v2, spr, reuse):
    """Run the two passes and report what each decided and cost.

    Pass two's frames are the NEXT n2 of the spread order, so the two passes never sample the
    same frame. With reuse, pass two also takes its own pictures from pass one's frames,
    which costs hashing but no seeking because those frames are already decoded."""
    f1 = frames_of(clip, 0, n1)
    d1 = judge(clip, f1, g1, v1)
    c1 = cost(clip, n1, g1, v1, spr, decode=True)
    if d1:
        return d1, 1, c1["total"], c1, None
    f2new = frames_of(clip, n1, n2)
    f2 = (f2new | f1) if reuse else f2new
    # pass two's own pictures over everything it may look at, plus pass one's groups over the
    # new frames only (pass one never saw them)
    c2 = cost(clip, len(f2new), g2, v2, spr, decode=True)
    extra = cost(clip, n1, g2, v2, spr, decode=False)["total"] if reuse else 0.0
    d2 = judge(clip, f2, set(g1) | set(g2), "".join(sorted(set(v1) | set(v2)))) if reuse \
        else judge(clip, f2, g2, v2)
    return d2, 2, c1["total"] + c2["total"] + extra, c1, c2


def cmd_order(clips, spr, label, reuse) -> None:
    print("\n  PASS ORDER   (%d clips, search rates: %s)" % (len(clips), label))
    print("  pass 1 takes the first N1 frames of the spread order, pass 2 the NEXT N2.")
    print("  %s\n" % ("pass 2 also re-uses pass 1's decoded frames for its own pictures"
                      if reuse else "the passes share no frames at all"))
    orders = [("uncropped -> cropped", {UNCROPPED}, "px", set(CROPPED), "px"),
              ("cropped -> uncropped", set(CROPPED), "px", {UNCROPPED}, "px"),
              ("plain -> mirrored", {UNCROPPED} | set(CROPPED), "p",
               {UNCROPPED} | set(CROPPED), "x")]
    print("  %-24s %6s %6s %7s %7s %9s %9s" % (
        "order", "N1", "N2", "right", "wrong", "on pass 1", "median s"))
    print("  " + "-" * 82)
    for n1, n2 in ((8, 12), (12, 12), (16, 24), (20, 20)):
        for lab, g1, v1, g2, v2 in orders:
            right = wrong = p1 = 0
            times = []
            for c in clips:
                d, which, secs, _, _ = _two_pass(c, n1, n2, g1, v1, g2, v2, spr, reuse)
                times.append(secs)
                if d:
                    v = verdict(c, d["label"])
                    if v == "right":
                        right += 1
                        if which == 1:
                            p1 += 1
                    elif v == "wrong":
                        wrong += 1
            print("  %-24s %6d %6d %7d %7d %9d %9.2f"
                  % (lab, n1, n2, right, wrong, p1, statistics.median(times)))
        print()


def cmd_sizes(clips, spr, label, reuse, order) -> None:
    g1, v1, g2, v2 = order
    print("\n  SAMPLE SIZES   (%d clips, search rates: %s)\n" % (len(clips), label))
    print("  %6s %6s %7s %7s %9s %9s %9s" % (
        "N1", "N2", "right", "wrong", "pass1 s", "both s", "median s"))
    print("  " + "-" * 66)
    for n1 in (4, 6, 8, 10, 12, 16, 20):
        for n2 in (8, 12, 16, 20, 24):
            if n1 + n2 > 40:
                continue
            right = wrong = 0
            t1, tt = [], []
            for c in clips:
                d, which, secs, c1, _ = _two_pass(c, n1, n2, g1, v1, g2, v2, spr, reuse)
                t1.append(c1["total"])
                tt.append(secs)
                if d:
                    v = verdict(c, d["label"])
                    right += int(v == "right")
                    wrong += int(v == "wrong")
            print("  %6d %6d %7d %7d %9.2f %9.2f %9.2f" % (
                n1, n2, right, wrong, statistics.median(t1),
                statistics.median(tt), statistics.median(tt)))


def _largest_fitting(clips, groups, views, nrows, budget, stat) -> tuple:
    """The most frames whose cost fits the budget, by median or by p90."""
    best = (0, 0.0)
    for n in range(1, 41):
        secs = sorted(cost(c, n, groups, views, nrows)["total"] for c in clips)
        v = statistics.median(secs) if stat == "median" else secs[int(0.9 * (len(secs) - 1))]
        if v <= budget:
            best = (n, v)
        else:
            break
    return best


def cmd_budget(clips, nrows, label, budget, order) -> None:
    """What each time threshold buys, in frames and then in recall.

    A budget is only interesting through what it can pay for, so this reports the largest
    sample size that fits and then what that sample size actually identifies. The frame
    count is what gets enforced at runtime, never the clock - so the engine's answer stays
    the same run to run, and the offline replay stays honest. p90 is the column that has to
    fit if the budget is a promise; median is the one to read if it is a target."""
    g1, v1, g2, v2 = order
    budgets = sorted({0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0, float(budget)} - {0.0})
    print()
    print("  WHAT EACH BUDGET BUYS, PER PASS   (%d clips, %s)" % (len(clips), label))
    print()
    print("  %8s  %-26s %-26s" % ("budget", "pass 1  cropped", "pass 2  uncropped"))
    print("  %8s  %12s %13s %12s %13s" % ("", "frames@med", "frames@p90", "frames@med", "frames@p90"))
    print("  " + "-" * 72)
    for b in budgets:
        n1m, _ = _largest_fitting(clips, g1, v1, nrows, b, "median")
        n1p, _ = _largest_fitting(clips, g1, v1, nrows, b, "p90")
        n2m, _ = _largest_fitting(clips, g2, v2, nrows, b, "median")
        n2p, _ = _largest_fitting(clips, g2, v2, nrows, b, "p90")
        mark = "  <-" if abs(b - budget) < 1e-9 else ""
        print("  %7.1fs  %12d %13d %12d %13d%s" % (b, n1m, n1p, n2m, n2p, mark))
    print()
    print("  and what those sample sizes identify (cropped first, frames re-used):")
    print()
    print("  %8s %7s %7s %8s %8s %10s" % (
        "budget", "N1", "N2", "right", "of", "both s"))
    print("  " + "-" * 56)
    for b in budgets:
        n1, _ = _largest_fitting(clips, g1, v1, nrows, b, "median")
        n2, _ = _largest_fitting(clips, g2, v2, nrows, b, "median")
        if not n1 or not n2:
            print("  %7.1fs %7s %7s %8s %8d %10s" % (b, "-", "-", "-", len(clips), "-"))
            continue
        n2 = min(n2, 40 - n1)
        right = wrong = 0
        secs = []
        for c in clips:
            d, _which, t, _c1, _c2 = _two_pass(c, n1, n2, g1, v1, g2, v2, nrows, True)
            secs.append(t)
            if d:
                v = verdict(c, d["label"])
                right += int(v == "right")
                wrong += int(v == "wrong")
        mark = "  <-" if abs(b - budget) < 1e-9 else ""
        print("  %7.1fs %7d %7d %8d %8d %10.2f%s" % (
            b, n1, n2, right, len(clips), statistics.median(secs), mark))
    print()
    print("  frames@med is the size that fits for a typical clip, frames@p90 the size that")
    print("  fits for nine in ten. Where frames@p90 is 0 the budget cannot be promised at")
    print("  all on this machine at clip-native resolution.")


# The fallback's rulebooks. The point is that they are NOT the probe's. The fallback only
# ever sees clips the probe already refused, so repeating the probe's bars over more frames
# mostly repeats its answer - measured, recovering 14, 13 and 14 clips at 8, 12 and 20
# frames, which is to say nothing for the extra work. These ask for different SHAPES of
# evidence instead, and those do improve with frames: "shape" goes 10, 12, 19 over the same
# three sizes, because corroboration is what more frames actually produce.
FALLBACK_BOOKS = {
    # the control: the probe's own bars, just with more frames behind them
    "same": (R.ADOPTED, {}),
    # PV-D is the scene rule - ONE offset cluster holding several hits. It is implemented in
    # replay_rules.py but deliberately not adopted by the probe, because on 8 frames a
    # cluster of four is rare. With a denser pass it stops being rare, which is exactly the
    # sort of bar that belongs in a fallback rather than in a pre-scan.
    "+PV-D": (tuple(R.ADOPTED) + ("PV-D",), {}),
    # shape only: no absolute distance bar at all, just corroboration. A fan edit or a
    # heavily re-compressed repost may have no good frame anywhere, so the probe's distance
    # bars can never fire however many frames it is given.
    "shape": (("PV-D", "PV-E"), {"D_HITS": 4, "D_BEST": 33.0,
                                 "E_CLUSTERS": 2, "E_PER_CLUSTER": 2, "E_BEST": 40.0}),
    # the probe's bars with the medium one relaxed, which more frames can afford
    "loose": (tuple(R.ADOPTED) + ("PV-D",),
              {"C_BEST": 33.0, "C_DIST": 40.0, "C_FRAMES": 6, "C_ALIGN": 4,
               "D_HITS": 5, "D_BEST": 26.0}),
}


def cmd_fallback(clips, nrows, label, order, reuse, n1: int = 8, n2: int = 12) -> None:
    """Of the clips the two passes refuse, how many does a denser THIRD pass recover?

    Its frames are the next slice of the spread order again, so all three stages sample
    different frames; the frames already decoded are re-fingerprinted under every view for
    the price of the hashing. Its rules are its own - see FALLBACK_BOOKS."""
    g1, v1, g2, v2 = order
    allg = {UNCROPPED} | set(CROPPED)
    declined, answered, wrongly = [], 0, 0
    for c in clips:
        d, _which, _secs, _c1, _c2 = _two_pass(c, n1, n2, g1, v1, g2, v2, nrows, reuse)
        v = verdict(c, d["label"]) if d else "unknown"
        if v == "right":
            answered += 1
            continue
        if v == "wrong":
            wrongly += 1
        declined.append(c)
    print()
    print("  THE FALLBACK   (%d clips, passes of %d + %d frames, %s)"
          % (len(clips), n1, n2, label))
    print("  the two passes answer %d correctly and %d wrongly, so %d of %d fall through"
          % (answered, wrongly, len(declined), len(clips)))
    if not declined:
        print("  nothing falls through - no fallback needed on this set")
        return
    print()
    print("  %-8s %7s %10s %8s %8s %10s" % (
        "rules", "frames", "recovers", "wrong", "quiet", "median s"))
    print("  " + "-" * 58)
    for book in ("same", "+PV-D", "shape", "loose"):
        active, over = FALLBACK_BOOKS[book]
        t = dict(R.DEFAULTS)
        t.update(over)
        for n3 in (8, 12, 20):
            if n1 + n2 + n3 > 40:
                continue
            rec = bad = 0
            secs = []
            for c in declined:
                seen = frames_of(c, n1 + n2, n3) | frames_of(c, 0, n1 + n2)
                d = judge(c, seen, allg, "px", t, set(active))
                k = cost(c, n3, allg, "px", nrows, decode=True)["total"]
                k += cost(c, n1 + n2, allg, "px", nrows, decode=False)["total"]
                secs.append(k)
                v = verdict(c, d["label"]) if d else "unknown"
                rec += int(v == "right")
                bad += int(v == "wrong")
            print("  %-8s %7d %10d %8d %8d %10.2f" % (
                book, n3, rec, bad, len(declined) - rec - bad, statistics.median(secs)))
        print()


def cmd_fit_search(clips) -> None:
    """Fit each shard's seconds-per-query from the dumps, instead of a synthetic loop.

    A microbenchmark of this could not be made to behave. Timed three times, the same
    120-query call against SQUARE took 0.0022, 0.0113 and 0.0023 s a query, and FULL - the
    SMALLEST shard at 1.9M rows - came out slower than PORTRAIT at 7.3M. Per-call overhead
    and faiss thread spin-up swamp the marginal cost at these batch sizes, so the table came
    out saying bigger shards search faster, which cannot be true of a flat scan.

    The dumps already hold the measurement, under real conditions and averaged over every
    clip. Each clip recorded its total search_s and its group mix is known, so

        search_s(clip) ~= sum over shards of (that shard's query rows) x (its cost per row)

    is one linear system with as many equations as there are clips. It is solved
    non-negative, so no shard can come out with a negative cost, and the fit's R2 is printed:
    a poor fit means the model is wrong and the modelled seconds elsewhere should not be
    trusted.

    Search is the small term anyway - roughly 8-10% of a clip's probe time against 75% for
    hashing - so this needs to be about right, not exact."""
    import numpy as np
    groups = sorted({g for c in clips for g in c.groups})
    rows, ys, used = [], [], []
    for c in clips:
        if c.search_s <= 0 or not c.groups or not c.frames_decoded:
            continue
        nom = c.nominal_rows(set(c.groups), "px")
        sc = c.target_scale
        rows.append([nom.get(g, 0) * c.frames_decoded * sc for g in groups])
        ys.append(c.search_s)
        used.append(c)
    if len(rows) < len(groups) + 2:
        raise SystemExit("not enough clips with a measured search_s to fit")
    A = np.array(rows, dtype=float)
    y = np.array(ys, dtype=float)
    try:
        from scipy.optimize import nnls
        x, _ = nnls(A, y)
    except Exception:
        x, *_ = np.linalg.lstsq(A, y, rcond=None)
        x = np.clip(x, 0.0, None)
    pred = A @ x
    r2 = 1.0 - ((y - pred) ** 2).sum() / max(((y - y.mean()) ** 2).sum(), 1e-12)
    sizes = {}
    try:
        man = json.load(open(HERE / "data" / "index" / "manifest.json", encoding="utf-8"))
        sizes = {g: v.get("n", 0) for g, v in (man.get("groups") or {}).items()}
    except Exception:
        pass
    print()
    print("  SEARCH COST FITTED FROM %d CLIPS' MEASURED search_s" % len(used))
    print()
    print("  %-11s %12s %14s %18s" % ("shard", "rows", "s per query", "ns per row/query"))
    print("  " + "-" * 60)
    out = {}
    for g, v in zip(groups, x):
        out[g] = round(float(v), 8)
        n = sizes.get(g, 0)
        print("  %-11s %12s %14.6f %18s" % (
            g, format(n, ",") if n else "?", v, ("%.2f" % (v / n * 1e9)) if n else "-"))
    print()
    print("  fit R2 = %.3f over %d clips" % (r2, len(used)))
    print("  The ns-per-row-per-query column is the sanity check: a flat binary scan reads")
    print("  every row, so it should come out roughly equal across shards. If it does not,")
    print("  the table is noise and the modelled seconds in the other reports are guesses.")
    OUT.mkdir(exist_ok=True)
    json.dump(out, open(CALIB, "w", encoding="utf-8"), indent=1, sort_keys=True)
    print()
    print("  wrote %s" % CALIB)


def cmd_calibrate(repeats: int = 7) -> None:
    """Measure each shard's search cost as overhead + per-query, by fitting across batch sizes.

    A single timing is useless here. Measured three times on this machine, the same 120-query
    call against SQUARE took 0.0022, 0.0113 and 0.0023 seconds a query, and FULL - the
    SMALLEST shard at 1.9M rows - came out slower than PORTRAIT at 7.3M. That is per-call
    overhead and faiss thread spin-up, not search: a flat binary index scans every row, so
    cost must rise with the shard, and a table that says otherwise is measuring the wrong
    thing.

    So each shard is warmed with a full search, then timed at several batch sizes with the
    best of `repeats` taken at each (the minimum, not the mean - the fastest run is the one
    least polluted by whatever else the machine was doing). Fitting seconds = a + b x queries
    separates the fixed cost a from the marginal cost b, and the model wants b. The fit's
    linearity is printed so a bad table announces itself rather than quietly skewing every
    later report."""
    import numpy as np
    import importlib.util as iu
    spec = iu.spec_from_file_location("ENG", HERE / "pdq_engine_PROBEV2.py")
    E = iu.module_from_spec(spec)
    sys.modules["ENG"] = E
    spec.loader.exec_module(E)
    index = E.load_index(str(HERE / "data" / "index"))
    rng = np.random.default_rng(0)
    sizes = (50, 100, 200, 400, 800)
    out, report = {}, []
    print()
    print("  SEARCH COST PER SHARD   (K=%d, best of %d at each batch size)" % (E.K_PER_HASH, repeats))
    print()
    print("  %-11s %9s  %s" % ("shard", "rows", "  ".join("%5d q" % n for n in sizes)))
    print("  " + "-" * 72)
    for g in sorted(index.index_by_group, key=lambda k: index.index_by_group[k].ntotal):
        ix = index.index_by_group[g]
        big = rng.integers(0, 256, (max(sizes), 32), dtype=np.uint8)
        ix.search(big[:16], E.K_PER_HASH)                 # page the shard in
        best = []
        for n in sizes:
            q = np.ascontiguousarray(big[:n])
            best.append(min(_time_search(ix, q, E.K_PER_HASH) for _ in range(repeats)))
        # seconds = a + b*n
        A = np.vstack([np.ones(len(sizes)), np.array(sizes, dtype=float)]).T
        (a, b), *_ = np.linalg.lstsq(A, np.array(best), rcond=None)
        pred = A @ np.array([a, b])
        ss = 1.0 - ((np.array(best) - pred) ** 2).sum() / max(
            ((np.array(best) - np.mean(best)) ** 2).sum(), 1e-12)
        out[g] = round(float(max(b, 0.0)), 8)
        report.append((g, ix.ntotal, a, b, ss))
        print("  %-11s %9d  %s" % (g, ix.ntotal, "  ".join("%6.3f" % t for t in best)))
    print()
    print("  %-11s %9s %11s %13s %8s %14s" % (
        "shard", "rows", "overhead s", "s per query", "R2", "ns per row/q"))
    print("  " + "-" * 72)
    for g, n, a, b, ss in report:
        print("  %-11s %9d %11.4f %13.6f %8.3f %14.2f" % (g, n, a, b, ss, b / n * 1e9))
    OUT.mkdir(exist_ok=True)
    json.dump(out, open(CALIB, "w", encoding="utf-8"), indent=1, sort_keys=True)
    print()
    print("  wrote %s" % CALIB)
    print("  The ns-per-row-per-query column is the sanity check: a flat binary scan should")
    print("  give roughly the same figure for every shard. If it does not, the table is")
    print("  noise and the modelled seconds in the other reports should not be trusted.")


def _time_search(ix, q, k) -> float:
    t = time.perf_counter()
    ix.search(q, k)
    return time.perf_counter() - t


def main() -> int:
    ap = argparse.ArgumentParser(description="Design the probe's passes against saved evidence.")
    ap.add_argument("--tag", default="edited", help="which probe_evidence[_tag].csv to read")
    ap.add_argument("--yield", dest="do_yield", action="store_true",
                    help="which pictures carry the matches")
    ap.add_argument("--order", action="store_true", help="which pass should go first")
    ap.add_argument("--sizes", action="store_true", help="sweep both passes' sample sizes")
    ap.add_argument("--budget", type=float, default=0.0,
                    help="report the sample sizes whose p90 fits this many seconds")
    ap.add_argument("--fallback", action="store_true", help="does a denser third pass help")
    ap.add_argument("--calibrate", action="store_true",
                    help="microbenchmark the per-shard search cost (noisy - prefer "
                         "--fit-search)")
    ap.add_argument("--fit-search", action="store_true",
                    help="fit the per-shard search cost from the dumps' measured search_s")
    ap.add_argument("--reuse", action="store_true",
                    help="pass 2 also takes its own pictures from pass 1's decoded frames")
    ap.add_argument("--cropped-first", action="store_true",
                    help="for --sizes/--budget: put the cropped pass first")
    a = ap.parse_args()

    if a.calibrate:
        cmd_calibrate()
        return 0

    spr, label = shard_rows()
    clips = load(a.tag)
    if a.fit_search:
        cmd_fit_search(clips)
        return 0
    if not clips:
        raise SystemExit("no clips in that dump")
    order = ((set(CROPPED), "px", {UNCROPPED}, "px") if a.cropped_first
             else ({UNCROPPED}, "px", set(CROPPED), "px"))

    did = False
    if a.do_yield:
        cmd_yield(clips); did = True
    if a.order:
        cmd_order(clips, spr, label, a.reuse); did = True
    if a.sizes:
        cmd_sizes(clips, spr, label, a.reuse, order); did = True
    if a.budget:
        cmd_budget(clips, spr, label, a.budget, order); did = True
    if a.fallback:
        cmd_fallback(clips, spr, label, order, a.reuse); did = True
    if not did:
        cmd_yield(clips)
    print()
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    raise SystemExit(main())

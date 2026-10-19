# -*- coding: utf-8 -*-
"""
replay_rules.py - try a rulebook against the probe's saved evidence, in under a second.

    python replay_rules.py                                   the engine's rulebook today
    python replay_rules.py --rules PV-A,PV-B,PV-C,PV-D,P1    add bars and see what moves
    python replay_rules.py --rules all --explain Soul        why one film passed or failed
    python replay_rules.py --sweep D_HITS=2:8                one bar's precision/recall curve
    python replay_rules.py --fit PV-D --max-wrong 1          grid search for the best setting
    python replay_rules.py --fit PV-D --loo                  ... and the held-out score
    python replay_rules.py --waves 8,16,24,40 --bar run      what a PROGRESSIVE probe answers
    python replay_rules.py --waves all --audit-waves --cost  ... and what it would cost

dump_probe_evidence.py paid the collection cost once. This judges that evidence, so a
threshold change costs a second instead of an hour and a half.

THE BARS. Each one asks for a different shape of evidence, and the shape matters more than
the count: a real scene matches the film at ONE constant offset (film time minus clip time),
and a look-alike scatters. That is the only thing separating the Brick clip (right) from
the Northman clip (wrong) - on count and best distance alone they are identical.

  PV-A  two near-perfect frames                           as the engine ships (mirrors P2.5)
  PV-B  the old pre-scan bar plus film-time agreement      as the engine ships (pre-scan + P4)
  PV-C  five medium frames, aligned, from two moments      as the engine ships (mirrors P6a)
  PV-D  ONE offset cluster holding several hits            new: the scene rule
  PV-E  SEVERAL clusters that each corroborate internally  new: the cut rule, for fan edits
  P1    one frame under 15 with at least 3 hits            ported from the streaming rules
  P3.5  sole candidate in the whole clip, sliding bar      ported from the streaming rules

PV-D and PV-E are the fan-edit separator. A fan edit cuts between moments of one film, so it
produces several clusters that each agree internally; a look-alike produces isolated
singletons at scattered offsets. Same scatter, opposite truth, and this is the difference.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import sys
from collections import defaultdict
from pathlib import Path

import metrics as M
from pv2_waves import sample_order as _wave_order, wave_bounds as _wave_bounds

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"

OFFSET_TOL_S = 3.0      # two hits "agree" on film time if their offsets sit within this
SPREAD_S = 3.0          # clip moments count as different if this far apart
MAX_HAMMING = 45.0      # anything worse is noise, and was never written to the evidence file

ALL_RULES = ("PV-A", "PV-B", "PV-C", "PV-D", "PV-E", "P1", "P3.5")
SHIPPED = ("PV-A", "PV-B", "PV-C")
# What the full 125-clip measurement supports adopting: the three shipped bars, P1 with
# the agreement guard, P3.5, and PV-E requiring real corroboration inside each cluster.
# 47 right / 1 wrong against the shipped 42 / 1, with precision unchanged at 97.9%.
ADOPTED = ("PV-A", "PV-B", "PV-C", "P1", "P3.5", "PV-E")

# The order a tie is broken in: the bar that asks for the strongest evidence wins.
TIER_RANK = {"PV-A": 0, "P1": 1, "PV-B": 2, "PV-D": 3, "PV-E": 4, "PV-C": 5, "P3.5": 6}


# ---- the wave schedule ----------------------------------------------------------------------
# The probe is all-or-nothing today: it pays all 40 seeks and every hash before anyone looks
# at a single result, even when sample one was a perfect match and even when the clip is not
# in the catalogue at all. These let a WAVE SCHEDULE be simulated against evidence already on
# disk, which is how the schedule below was chosen rather than guessed.
#
# The ordering itself comes from pv2_waves.py, which the engine uses too. That module
# imports nothing, so there is ONE copy of the algorithm and this file still needs no faiss -
# which is why it answers in a second where the engine needs an hour and a half.

PV2_SAMPLES = 40                  # the sample count the schedule below was tuned at
WAVES = (8, 16, 24, 40)           # cumulative sample counts
WAVE_ORDER = "vdc"                # vdc | golden | linear
# "vdc" simulates the GRID engine, where the samples sit at (i+0.5)/n and the spread comes
# from the order the ids are taken in. An ANCHORED dump (PDQ_PROBE_ANCHORED=1) puts the
# spread in the positions instead and takes its ids in order, so simulating one of those
# needs --wave-order linear. Replaying a grid dump against an anchored schedule, or the
# reverse, is meaningless rather than merely wrong: the same sample_i is a different
# moment of the clip, so the hits belong to frames the schedule never asked for.
WAVE_BAR = "run"                  # run | wave | off  (see decide_progressive)
# P3.5 is deliberately NOT allowed to accept before the last wave: it turns on being the sole
# candidate, so a film that clears it on wave one can stop being sole later, and accepting
# early would answer where the full scan refuses.
EARLY_TIERS = ("PV-A", "P1", "PV-B", "PV-D", "PV-E", "PV-C")


def pv2_sample_order(n_samples: int, mode: str = None) -> list:
    """The order the probe takes its samples in - see pv2_waves.sample_order.

    Same code the engine runs, from a module that imports nothing, so this file still needs
    no faiss and still answers in a second."""
    return _wave_order(n_samples, WAVE_ORDER if mode is None else mode)


def wave_bounds(n_samples: int, waves=None) -> list:
    """The waves as cumulative sample counts - see pv2_waves.wave_bounds."""
    return _wave_bounds(n_samples, WAVES if waves is None else waves, PV2_SAMPLES)


# ---- the thresholds, all in one place so they can be swept ----------------------------------

DEFAULTS = {
    "A_BEST": 12.0, "A_DIST": 16.0, "A_FRAMES": 2,
    "B_BEST": 20.0, "B_DIST": 28.0, "B_FRAMES": 3, "B_ALIGN": 2,
    "C_BEST": 26.0, "C_DIST": 33.0, "C_FRAMES": 5, "C_ALIGN": 3, "C_SPREAD": 2,
    "D_HITS": 4, "D_BEST": 20.0,
    "E_CLUSTERS": 2, "E_PER_CLUSTER": 2, "E_BEST": 33.0,
    "P1_BEST": 15.0, "P1_FRAMES": 3, "P1_ALIGN": 2, "P1_DIST": 28.0,
}

# What --fit is allowed to move, per rule. Deliberately coarse: a fine grid over 81 positives
# finds a setting that fits these clips by name, which is what --loo is here to expose.
GRIDS = {
    "PV-D": {"D_HITS": [3, 4, 5, 6], "D_BEST": [12.0, 16.0, 20.0, 26.0]},
    "PV-E": {"E_CLUSTERS": [2, 3], "E_PER_CLUSTER": [2, 3], "E_BEST": [12.0, 16.0, 20.0, 26.0, 33.0]},
    "P1": {"P1_BEST": [10.0, 15.0, 18.0], "P1_FRAMES": [3, 4, 5, 6],
           "P1_ALIGN": [1, 2, 3]},
    "PV-B": {"B_BEST": [16.0, 20.0], "B_DIST": [26.0, 28.0, 33.0], "B_FRAMES": [3, 4],
             "B_ALIGN": [2, 3]},
    "PV-C": {"C_FRAMES": [4, 5, 6], "C_ALIGN": [2, 3], "C_SPREAD": [1, 2]},
}


# ---- the evidence ---------------------------------------------------------------------------

class Clip:
    def __init__(self, row: dict):
        self.list = row["list"].strip()
        self.name = row["clip"]
        self.expected = row["expected_film"]
        self.in_cat = row["in_catalogue"].strip().lower() in M.YES
        self.note = row.get("note", "")
        self.films_hit = int(row["films_hit"] or 0)
        self.n_samples = int(row["n_samples"] or 0) or PV2_SAMPLES
        self.collect_s = float(row.get("collect_s") or 0.0)
        self.hits: dict = defaultdict(dict)     # vidx -> {sample_i: (distance, clip_t, film_t)}
        self.labels: dict = {}
        self.truth = None

    def rows_for(self, vidx: int, allowed=None):
        """This film's hits as [(distance, clip_t, film_t), ...], best first.

        allowed restricts the answer to a set of sampled frames, which is what makes a wave
        schedule simulable offline. The engine's _probe_search reduces strictly per query
        row - top-K per row, MAX_HAMMING per row, best per (film, sample) - so whether a
        frame hits does not depend on which other frames shared its batch. A prefix of the
        saved evidence is therefore exactly what that prefix of samples would have found."""
        rows = self.hits[vidx]
        if allowed is None:
            return sorted(rows.values())
        return sorted(r for si, r in rows.items() if si in allowed)

    def films_seen(self, allowed=None) -> int:
        """Films with at least one hit inside this prefix. P3.5 turns on being the SOLE
        candidate, so it has to be counted per prefix - counting over all 40 samples would
        judge a wave against films it had not looked at yet."""
        if allowed is None:
            return sum(1 for v in self.hits if self.hits[v])
        return sum(1 for v in self.hits if any(si in allowed for si in self.hits[v]))


def load_evidence(tag: str = "") -> list:
    suffix = ("_" + tag) if tag else ""
    clips_csv = OUT / ("probe_evidence_clips%s.csv" % suffix)
    hits_csv = OUT / ("probe_evidence%s.csv" % suffix)
    if not clips_csv.is_file():
        raise SystemExit("no %s - run:  python dump_probe_evidence.py" % clips_csv.name)
    clips = {}
    for r in csv.DictReader(open(clips_csv, encoding="utf-8")):
        clips[r["clip"]] = Clip(r)
    if hits_csv.is_file():
        for r in csv.DictReader(open(hits_csv, encoding="utf-8")):
            c = clips.get(r["clip"])
            if c is None:
                continue                         # a hit for a clip not yet in the clips file
            v = int(r["vidx"])
            si = int(r["sample_i"])
            row = (float(r["distance"]), float(r["clip_t"]), float(r["film_t"]))
            cur = c.hits[v].get(si)
            if cur is None or row[0] < cur[0]:
                # the engine's _merge_film_hits rule: one best hit per (film, sampled frame).
                # Keying by sample_i also stops a resumed dump double-counting - hit rows are
                # flushed before the clip row, so a crash between the two leaves orphan hits
                # and the clip is re-run, which an appending list would count twice.
                c.hits[v][si] = row
            c.labels[v] = r["film_label"]
    truth = M.load_truth()
    for c in clips.values():
        c.truth = truth.get(c.name)
    return list(clips.values())


# ---- the evidence shapes the bars ask about -------------------------------------------------

def aligned(rows) -> int:
    """The largest number of hits agreeing on one film-time offset."""
    offs = sorted(ft - ct for _, ct, ft in rows)
    return max((sum(1 for o in offs if abs(o - o0) <= OFFSET_TOL_S) for o0 in offs), default=0)


def spread(rows) -> int:
    """How many separate moments of the clip these hits came from."""
    secs = sorted(ct for _, ct, _ in rows)
    if not secs:
        return 0
    n = 1
    for i in range(1, len(secs)):
        if abs(secs[i] - secs[i - 1]) > SPREAD_S:
            n += 1
    return n


def offset_clusters(rows):
    """Group hits into runs that agree on film time. Each cluster spans at most OFFSET_TOL_S
    from its FIRST member, so a slow drift cannot chain into one huge cluster.

    Returns [[(offset, distance, clip_t), ...], ...], largest cluster first."""
    items = sorted((ft - ct, d, ct) for d, ct, ft in rows)
    if not items:
        return []
    out, cur = [], [items[0]]
    for it in items[1:]:
        if it[0] - cur[0][0] <= OFFSET_TOL_S:
            cur.append(it)
        else:
            out.append(cur)
            cur = [it]
    out.append(cur)
    out.sort(key=len, reverse=True)
    return out


# ---- the rulebook ---------------------------------------------------------------------------

def bars_for_film(rows, t: dict, sole_candidate: bool):
    """Every bar this film's evidence passes, as [(name, detail), ...] in rulebook order.
    rows is [(distance, clip_t, film_t), ...] sorted best first."""
    if not rows:
        return []
    best = rows[0][0]
    total = len(rows)
    avg = sum(r[0] for r in rows) / total
    out = []

    a = [r for r in rows if r[0] < t["A_DIST"]]
    if best < t["A_BEST"] and len(a) >= t["A_FRAMES"]:
        out.append(("PV-A", "best=%.0f frames_under_%.0f=%d" % (best, t["A_DIST"], len(a))))

    # P1 as the streaming rules write it asks only "one frame under 15, plus two others".
    # Ported into the probe unchanged it readmits The Northman - best distance 6 on the shared
    # footage, 6 hits, offsets scattered over 12 minutes of film - the precise wrong answer
    # the probe was built to refuse. P1_ALIGN adds the agreement check the probe's own bars
    # have (P1_ALIGN=1 is the original, unguarded rule).
    #
    # The agreement must be measured WITHIN A DISTANCE BAND, which is the trap here. Over all
    # hits, Northman does have two that agree - at distances 30 and 44, two pieces of junk
    # corroborating each other - so an unbanded aligned() >= 2 still lets it in. Restricted to
    # hits under P1_DIST its four decent hits sit at four different offsets and it is refused.
    p1 = [r for r in rows if r[0] < t["P1_DIST"]]
    if best < t["P1_BEST"] and total >= t["P1_FRAMES"] and aligned(p1) >= t["P1_ALIGN"]:
        out.append(("P1", "best=%.0f with %d frames, aligned=%d under %.0f"
                    % (best, total, aligned(p1), t["P1_DIST"])))

    b = [r for r in rows if r[0] < t["B_DIST"]]
    if best < t["B_BEST"] and len(b) >= t["B_FRAMES"] and aligned(b) >= t["B_ALIGN"]:
        out.append(("PV-B", "best=%.0f frames_under_%.0f=%d aligned=%d"
                    % (best, t["B_DIST"], len(b), aligned(b))))

    clusters = offset_clusters(rows)
    if clusters:
        big = clusters[0]
        big_best = min(d for _, d, _ in big)
        if len(big) >= t["D_HITS"] and big_best <= t["D_BEST"]:
            out.append(("PV-D", "one cluster of %d at offset %.1fmin, best=%.0f"
                        % (len(big), big[0][0] / 60.0, big_best)))
        good = [c for c in clusters
                if len(c) >= t["E_PER_CLUSTER"] and min(d for _, d, _ in c) <= t["E_BEST"]]
        if len(good) >= t["E_CLUSTERS"]:
            out.append(("PV-E", "%d corroborating clusters at %s min"
                        % (len(good), ", ".join("%.1f" % (c[0][0] / 60.0) for c in good[:4]))))

    c = [r for r in rows if r[0] < t["C_DIST"]]
    if (best < t["C_BEST"] and len(c) >= t["C_FRAMES"] and aligned(c) >= t["C_ALIGN"]
            and spread(c) >= t["C_SPREAD"]):
        out.append(("PV-C", "best=%.0f frames_under_%.0f=%d aligned=%d moments=%d"
                    % (best, t["C_DIST"], len(c), aligned(c), spread(c))))

    if sole_candidate:
        # P3.5's sliding bar: the fewer rivals, the lower the count it needs.
        for lim_avg, need in ((20.0, 4), (30.0, 7), (35.0, 12), (45.0, 20)):
            if avg <= lim_avg and total >= need:
                out.append(("P3.5", "sole candidate, %d frames at avg %.1f" % (total, avg)))
                break
    return out


def decide(clip: Clip, t: dict, active: set, allowed=None):
    """Which film the probe would answer with, and on which bar. None means it stays quiet.

    allowed restricts the judgement to a set of sampled frames - see Clip.rows_for."""
    sole = clip.films_seen(allowed) == 1
    best = None
    for v in clip.hits:
        rows = clip.rows_for(v, allowed)
        if not rows:
            continue
        for name, detail in bars_for_film(rows, t, sole):
            if name not in active:
                continue
            cl = offset_clusters(rows)
            key = (-TIER_RANK[name], len(cl[0]) if cl else 0, -rows[0][0])
            if best is None or key > best[0]:
                best = (key, v, name, detail)
    if best is None:
        return None
    _, v, name, detail = best
    return {"vidx": v, "rule": name, "detail": detail, "label": clip.labels.get(v, str(v))}


def decide_progressive(clip: Clip, t: dict, active: set, order_mode: str = None,
                       waves=None, bar: str = None, early=None) -> tuple:
    """Judge the clip the way a progressive probe would, and report what it cost.

    Wave by wave over pv2_sample_order: accept as soon as a bar fires, and give up early if
    the evidence says the clip is not in the catalogue at all. Returns
    (decision-or-None, wave_reached, samples_consumed).

    The give-up bar, measured over all 125 clips:

      "run"   stop while the WHOLE run so far has found nothing. Decision-identical to the
              full scan - 47 right, 1 wrong, the same film on all 48 answers - at 49% of the
              frame work. The default, because it costs nothing.
      "wave"  stop when one wave adds no new hit. 39% of the work, but it loses 4 correct
              answers: evidence arrives in bursts, and a quiet wave is not a verdict.
      "off"   never give up early. 81% of the work, same answers.

    A clip the probe declines still reaches the full streaming pass, so giving up here costs
    an early exit, not the answer."""
    n = clip.n_samples or PV2_SAMPLES
    order = pv2_sample_order(n, order_mode)
    bounds = wave_bounds(n, waves)
    bar = WAVE_BAR if bar is None else bar
    early = EARLY_TIERS if early is None else early
    for wi, upto in enumerate(bounds, 1):
        allowed = set(order[:upto])
        last = (wi == len(bounds))
        d = decide(clip, t, active, allowed)
        if d is not None and (last or d["rule"] in early):
            return dict(d, wave=wi, samples=upto), wi, upto
        if last:
            break
        if bar != "off":
            found = sum(1 for v in clip.hits for si in clip.hits[v] if si in allowed)
            if bar == "run" and found == 0:
                return None, wi, upto
            if bar == "wave":
                prev = set(order[:bounds[wi - 2]]) if wi > 1 else set()
                gained = sum(1 for v in clip.hits for si in clip.hits[v]
                             if si in allowed and si not in prev)
                if gained == 0:
                    return None, wi, upto
    return None, len(bounds), bounds[-1]


def progressive_decider(**kw):
    """decide_progressive as a plain decider, so score/--sweep/--fit can use one."""
    def f(clip, t, active):
        return decide_progressive(clip, t, active, **kw)[0]
    return f


# ---- scoring ---------------------------------------------------------------------------------

def is_expected_film(label: str, clip: Clip) -> bool:
    """tmdb id first, fuzzy title only as a fallback - see metrics.py for why."""
    t = M.tmdb_matches(label, clip.truth)
    return t if t is not None else M.fuzzy_matches(label, clip.expected)


def score(clips, t: dict, active: set, decider=None) -> dict:
    """decider defaults to the all-at-once judgement; pass progressive_decider(...) to score
    a wave schedule instead, so --sweep and --fit keep working under one."""
    right = wrong = unknown = answers = 0
    per_rule = defaultdict(lambda: [0, 0, 0])      # rule -> [fired, right, wrong]
    detail = []
    for c in clips:
        d = decide(c, t, active) if decider is None else decider(c, t, active)
        if d is None:
            continue
        answers += 1
        hit_expected = is_expected_film(d["label"], c)
        pr = per_rule[d["rule"]]
        pr[0] += 1
        if c.list == "correct" and hit_expected:
            right += 1
            pr[1] += 1
            detail.append(("right", c, d))
        elif c.list == "wrong" and hit_expected:
            wrong += 1
            pr[2] += 1
            detail.append(("WRONG", c, d))
        else:
            unknown += 1
            detail.append(("unknown", c, d))
    corr_in = sum(1 for c in clips if c.list == "correct" and c.in_cat)
    return {"answers": answers, "right": right, "wrong": wrong, "unknown": unknown,
            "corr_in": corr_in, "per_rule": dict(per_rule), "detail": detail}


def print_score(s: dict, active: set, title: str = "") -> None:
    if title:
        print("  " + title)
    print("    answers %3d    right %3d    known-wrong %d    unknown %d" % (
        s["answers"], s["right"], s["wrong"], s["unknown"]))
    print("    precision %s   recall %s  (%d/%d of the in-catalogue confirmed clips)" % (
        M.pct(s["right"], s["answers"]), M.pct(s["right"], s["corr_in"]),
        s["right"], s["corr_in"]))
    print("    bars:  " + "   ".join(
        "%s %d/%d%s" % (r, v[1], v[0], (" +%dwrong" % v[2]) if v[2] else "")
        for r, v in sorted(s["per_rule"].items(), key=lambda kv: TIER_RANK.get(kv[0], 9))))


def cmd_waves(clips, t: dict, active: set, order_mode: str, waves, bar: str,
              early, audit: bool) -> None:
    """What a progressive probe would answer, what it would cost, and where it differs.

    The divergence count is the number that matters. "Accept as soon as a bar fires" is only
    safe if more evidence could not have changed the answer, and pv2_decide is NOT monotone:
    offset_clusters chains each cluster from its FIRST member, so inserting a hit mid-way can
    SHRINK a cluster - offsets {1,2,3,4} are one cluster of four, but adding 0.5 splits them
    into {0.5,1,2,3} and {4} - and PV-E counts clusters by member count. So more evidence can
    flip PV-E either way. Auditing every clip turns that from a hope into a number."""
    full = {}
    for c in clips:
        full[c.name] = decide(c, t, active)

    print()
    print("  wave schedule %s, order %s, give-up bar %r" % (
        ",".join(str(b) for b in wave_bounds(PV2_SAMPLES, waves)), order_mode or WAVE_ORDER,
        bar or WAVE_BAR))
    print("  may accept before the last wave: %s" % ", ".join(
        sorted(early if early is not None else EARLY_TIERS, key=lambda r: TIER_RANK.get(r, 9))))

    prog = progressive_decider(order_mode=order_mode, waves=waves, bar=bar, early=early)
    s_prog = score(clips, t, active, prog)
    s_full = score(clips, t, active)
    print()
    print_score(s_full, active, "all at once (every sampled frame, as the probe runs today)")
    print()
    print_score(s_prog, active, "progressive waves")

    # cost, and the divergences
    frames = frames_full = 0
    secs = secs_full = 0.0
    by_wave = defaultdict(int)
    diverged, lost, gained = [], [], []
    for c in clips:
        d, wave, used = decide_progressive(c, t, active, order_mode, waves, bar, early)
        n = c.n_samples or PV2_SAMPLES
        frames += used
        frames_full += n
        # frames are the right unit: cost is dominated by hashing, measured at ~0.041 s per
        # hash and ~11.4 hash targets per sampled frame, so time scales with frames taken.
        secs += c.collect_s * used / float(n)
        secs_full += c.collect_s
        by_wave[wave if d else 0] += 1
        f = full[c.name]
        if d and f and d["vidx"] != f["vidx"]:
            diverged.append((c, d, f))
        elif d and not f:
            gained.append((c, d))
        elif f and not d:
            lost.append((c, f))

    print()
    print("  COST   %d of %d sampled frames (%.0f%%)   est %.0f s of %.0f s over the set"
          % (frames, frames_full, 100.0 * frames / max(frames_full, 1), secs, secs_full))
    print("         answered on wave: %s   never answered: %d" % (
        "  ".join("w%d %d" % (w, n) for w, n in sorted(by_wave.items()) if w),
        by_wave.get(0, 0)))
    print()
    print("  DIVERGENCE from the all-at-once answer: %d different film, %d lost, %d gained"
          % (len(diverged), len(lost), len(gained)))
    if audit:
        for c, d, f in diverged:
            print("    DIFFERENT %-40s wave %d: %s (%s)  vs full: %s (%s)" % (
                c.name[:40], d["wave"], d["label"][:24], d["rule"], f["label"][:24], f["rule"]))
        for c, f in lost:
            print("    LOST      %-40s full said %s (%s); %s list" % (
                c.name[:40], f["label"][:28], f["rule"], c.list))
        for c, d in gained:
            print("    GAINED    %-40s wave %d said %s (%s); %s list" % (
                c.name[:40], d["wave"], d["label"][:28], d["rule"], c.list))
        if not (diverged or lost or gained):
            print("    none - every clip gets the same answer as the full scan")
    print()


# ---- the commands ----------------------------------------------------------------------------

def cmd_sweep(clips, t: dict, active: set, spec: str) -> None:
    key, _, rng = spec.partition("=")
    key = key.strip()
    if key not in DEFAULTS:
        raise SystemExit("unknown threshold %r. known: %s" % (key, ", ".join(sorted(DEFAULTS))))
    parts = [float(x) for x in rng.split(":")] if rng else []
    if len(parts) < 2:
        raise SystemExit("--sweep NAME=lo:hi[:step]")
    lo, hi = parts[0], parts[1]
    step = parts[2] if len(parts) > 2 else 1.0
    isint = isinstance(DEFAULTS[key], int)
    print("\n  sweeping %s (default %s)\n" % (key, DEFAULTS[key]))
    print("    %-10s %7s %7s %7s %10s %9s" % (key, "answers", "right", "wrong", "precision", "recall"))
    v = lo
    while v <= hi + 1e-9:
        tt = dict(t)
        tt[key] = int(v) if isint else v
        s = score(clips, tt, active)
        mark = "  <- default" if tt[key] == DEFAULTS[key] else ""
        print("    %-10s %7d %7d %7d %10s %9s%s" % (
            tt[key], s["answers"], s["right"], s["wrong"],
            M.pct(s["right"], s["answers"]), M.pct(s["right"], s["corr_in"]), mark))
        v += step
    print()


def grid_outcomes(clips, t: dict, active: set, rules: list):
    """Score every grid config ONCE, keeping the per-clip outcome rather than just the totals.

    outcome per clip: +1 a right answer, -1 a known-wrong one, 0 quiet or unknown truth.

    Doing it this way is what makes --loo affordable. Refitting the whole grid for each
    held-out clip is 125 x |grid| full passes; keeping the outcome vectors makes it |grid|
    passes and turns leave-one-out into arithmetic over columns."""
    grid = {}
    for r in rules:
        grid.update(GRIDS.get(r, {}))
    if not grid:
        return [], []
    keys = sorted(grid)
    out = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        tt = dict(t)
        tt.update(dict(zip(keys, combo)))
        outcomes = []
        for c in clips:
            d = decide(c, tt, active)
            if d is None or not is_expected_film(d["label"], c):
                outcomes.append(0)
            else:
                outcomes.append(1 if c.list == "correct" else -1)
        drift = sum(0 if tt[k] == DEFAULTS[k] else 1 for k in keys)
        out.append((tt, outcomes, drift))
    return out, keys


def pick_best(cases, max_wrong: int, skip: int = -1):
    """The config with the most right answers while known-wrong stays at or under max_wrong,
    counting every clip except `skip`. Ties go to whichever moved least from the defaults,
    so a threshold only changes when the change pays for itself."""
    best = None
    for tt, outcomes, drift in cases:
        right = wrong = 0
        for i, o in enumerate(outcomes):
            if i == skip:
                continue
            if o > 0:
                right += 1
            elif o < 0:
                wrong += 1
        if wrong > max_wrong:
            continue
        key = (right, -drift)
        if best is None or key > best[0]:
            best = (key, tt, outcomes)
    return best


def fit(clips, t: dict, active: set, rules: list, max_wrong: int):
    """Grid search over all clips. Returns (thresholds, score, keys)."""
    cases, keys = grid_outcomes(clips, t, active, rules)
    if not cases:
        return t, None, []
    best = pick_best(cases, max_wrong)
    if best is None:
        return t, None, keys
    return best[1], score(clips, best[1], active), keys


def cmd_fit(clips, t: dict, active: set, rules: list, max_wrong: int, loo: bool) -> None:
    best_t, s, keys = fit(clips, t, active, rules, max_wrong)
    if s is None:
        print("\n  no setting of %s keeps known-wrong answers at or under %d\n"
              % (", ".join(rules), max_wrong))
        return
    print("\n  FITTED on all %d clips, keeping known-wrong <= %d" % (len(clips), max_wrong))
    print("    " + "  ".join("%s=%s" % (k, best_t[k]) for k in keys))
    print_score(s, active)

    if not loo:
        print("\n  Add --loo to see whether this setting survives being fitted without each clip.\n")
        return

    # Leave one out: refit without each clip, then judge that clip with the refitted bars.
    # A bar that only works with every clip in the room is a bar fitted to these clips.
    print("\n  LEAVE-ONE-OUT: refit on the other %d clips, then judge the held-out one"
          % (len(clips) - 1))
    cases, _ = grid_outcomes(clips, t, active, rules)
    right = wrong = 0
    moved = 0
    for i in range(len(clips)):
        b = pick_best(cases, max_wrong, skip=i)
        if b is None:
            continue
        if b[1] is not best_t:
            moved += 1 if b[1] != best_t else 0
        o = b[2][i]
        if o > 0:
            right += 1
        elif o < 0:
            wrong += 1
    print("    right %3d    known-wrong %d   (held-out clips only)" % (right, wrong))
    print("    recall %s   against the fitted %s" % (
        M.pct(right, s["corr_in"]), M.pct(s["right"], s["corr_in"])))
    if moved:
        print("    the fitted setting changed for %d of the %d held-out refits" % (moved, len(clips)))
    gap = s["right"] - right
    if gap > 2:
        print("    -> %d of the fitted gain does NOT survive leaving a clip out. That gain is"
              % gap)
        print("       fitted to these clips; prefer a simpler bar.")
    elif gap > 0:
        print("    -> %d answer(s) of the fitted gain is fragile; the rest holds up." % gap)
    else:
        print("    -> the gain holds up with any single clip removed.")
    print()


def cmd_explain(clips, t: dict, active: set, needle: str) -> None:
    n = needle.lower()
    shown = 0
    for c in clips:
        if n not in c.expected.lower() and n not in c.name.lower():
            continue
        shown += 1
        print("\n" + "=" * 78)
        print("  %s   (%s list, %s)" % (c.expected, c.list, c.name[:46]))
        print("=" * 78)
        if not c.hits:
            print("  the probe found no film at all - a sampling or fingerprint limit, not a rule")
            continue
        sole = c.films_seen() == 1
        ranked = sorted(c.hits, key=lambda v: (-len(c.hits[v]),
                                               min(d for d, _, _ in c.hits[v].values())))
        for v in ranked[:3]:
            rows = c.rows_for(v)
            mine = is_expected_film(c.labels.get(v, ""), c)
            print("\n  %s%s" % (c.labels.get(v, v), "   <- the expected film" if mine else ""))
            print("    %d hits, best %.0f, avg %.1f, aligned %d, moments %d" % (
                len(rows), rows[0][0], sum(r[0] for r in rows) / len(rows),
                aligned(rows), spread(rows)))
            for cl in offset_clusters(rows)[:4]:
                print("      cluster at film %7.2fmin: %d hit(s), distances %s" % (
                    cl[0][0] / 60.0, len(cl), ", ".join("%.0f" % d for _, d, _ in cl)))
            passed = bars_for_film(rows, t, sole)
            for name in ALL_RULES:
                hit = next((d for nm, d in passed if nm == name), None)
                on = "" if name in active else "  (off)"
                print("      %-5s %-4s %s%s" % (name, "PASS" if hit else "fail", hit or "", on))
        d = decide(c, t, active)
        print("\n  VERDICT: %s" % (
            "%s on %s - %s" % (d["label"], d["rule"], d["detail"]) if d else "stays quiet"))
    if not shown:
        print("  no clip matching %r" % needle)
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="Judge the probe's saved evidence.")
    ap.add_argument("--tag", default="", help="which probe_evidence[_tag].csv to read")
    ap.add_argument("--rules", default=",".join(SHIPPED),
                    help="bars to switch on: a comma list, or 'all', 'adopted' or 'shipped'")
    ap.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                    help="override one threshold, repeatable")
    ap.add_argument("--sweep", metavar="NAME=lo:hi[:step]")
    ap.add_argument("--fit", metavar="RULES", help="grid search the named bars (comma list)")
    ap.add_argument("--max-wrong", type=int, default=1, help="known-wrong answers --fit may allow")
    ap.add_argument("--loo", action="store_true", help="with --fit: the leave-one-out score")
    ap.add_argument("--explain", metavar="FILM", help="walk one clip's evidence through the bars")
    ap.add_argument("--waves", metavar="A,B,C",
                    help="cumulative sample counts, e.g. 8,16,24,40; 'all' for one wave "
                         "(the probe as it runs today)")
    ap.add_argument("--wave-order", choices=["vdc", "golden", "linear"],
                    help="which spread the waves take their frames in (default vdc)")
    ap.add_argument("--bar", choices=["off", "wave", "run"],
                    help="when the probe gives up early (default run)")
    ap.add_argument("--early-tiers", metavar="RULES",
                    help="bars allowed to accept before the last wave, or 'all'")
    ap.add_argument("--audit-waves", action="store_true",
                    help="list every clip whose wave answer differs from the full scan")
    ap.add_argument("--cost", action="store_true",
                    help="with a wave schedule: frames and seconds it would cost")
    a = ap.parse_args()

    clips = load_evidence(a.tag)
    thresholds = dict(DEFAULTS)
    for kv in a.set:
        k, _, v = kv.partition("=")
        k = k.strip()
        if k not in DEFAULTS:
            raise SystemExit("unknown threshold %r" % k)
        thresholds[k] = int(float(v)) if isinstance(DEFAULTS[k], int) else float(v)

    if a.rules == "all":
        active = set(ALL_RULES)
    elif a.rules == "shipped":
        active = set(SHIPPED)
    elif a.rules == "adopted":
        active = set(ADOPTED)
    else:
        active = {r.strip() for r in a.rules.split(",") if r.strip()}
    unknown_rules = active - set(ALL_RULES)
    if unknown_rules:
        raise SystemExit("unknown bar(s) %s. known: %s" % (
            ", ".join(sorted(unknown_rules)), ", ".join(ALL_RULES)))

    nhit = sum(1 for c in clips if c.hits)
    print("\n  %d clips of saved evidence (%d found at least one film), bars on: %s" % (
        len(clips), nhit, ", ".join(sorted(active, key=lambda r: TIER_RANK[r]))))
    if len(clips) < 125:
        print("  NOTE: dump_probe_evidence.py has not finished - this is a partial set.")

    waves = None
    if a.waves:
        waves = None if a.waves == "all" else tuple(
            int(x) for x in a.waves.replace(" ", "").split(",") if x)
        if waves == ():
            raise SystemExit("--waves wants a comma list of cumulative counts, or 'all'")
        if a.waves == "all":
            waves = (PV2_SAMPLES,)
    early = None
    if a.early_tiers:
        early = tuple(ALL_RULES) if a.early_tiers == "all" else tuple(
            r.strip() for r in a.early_tiers.split(",") if r.strip())
        bad = set(early) - set(ALL_RULES)
        if bad:
            raise SystemExit("unknown bar(s) in --early-tiers: %s" % ", ".join(sorted(bad)))
    wavey = bool(a.waves or a.wave_order or a.bar or a.early_tiers or a.audit_waves or a.cost)
    decider = progressive_decider(order_mode=a.wave_order, waves=waves, bar=a.bar,
                                  early=early) if wavey else None

    if a.explain:
        cmd_explain(clips, thresholds, active, a.explain)
        return 0
    if wavey and not (a.sweep or a.fit):
        cmd_waves(clips, thresholds, active, a.wave_order, waves, a.bar, early, a.audit_waves)
        return 0
    if a.sweep:
        cmd_sweep(clips, thresholds, active, a.sweep)
        return 0
    if a.fit:
        cmd_fit(clips, thresholds, active, [r.strip() for r in a.fit.split(",")],
                a.max_wrong, a.loo)
        return 0

    print()
    print_score(score(clips, thresholds, active), active, "THIS RULEBOOK")
    print()
    base = score(clips, thresholds, set(SHIPPED))
    if active != set(SHIPPED):
        print_score(base, set(SHIPPED), "the engine as it ships (PV-A/B/C), for comparison")
        print()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())

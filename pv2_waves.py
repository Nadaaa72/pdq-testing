# -*- coding: utf-8 -*-
"""
pv2_waves.py - the probe's sampling order and wave schedule, as pure arithmetic.

This is a leaf module ON PURPOSE. It imports nothing, so both sides of the measurement
loop can share one copy of the algorithm:

  pdq_engine_PROBEV2.py  takes the frames (and needs faiss, pdqhash, cv2, numpy)
  replay_rules.py        re-judges saved evidence, and must stay importable without any of
                         them - that is why it answers in a second instead of an hour

The alternative was a copy in each file plus something to notice when they drift. One copy
cannot drift.

The configuration does NOT live here. Each caller keeps its own constants and env vars and
passes them in, so this file has no opinion about what the schedule should be - only about
what a given schedule means.
"""
from __future__ import annotations


def radical_inverse2(i: int) -> float:
    """i's bits reflected about the binary point, giving a fraction in [0, 1)."""
    x, f = 0.0, 0.5
    while i:
        if i & 1:
            x += f
        i >>= 1
        f *= 0.5
    return x


def sample_order(n_samples: int, mode: str = "vdc") -> list:
    """A permutation of range(n_samples) whose every PREFIX is spread over the whole clip.

    That is the whole trick behind the waves: for n=40 the first 8 cover 1% to 91% of the
    clip, and each later wave interleaves into the gaps without ever re-taking a frame an
    earlier wave already had. A prefix is evenly spread AND the union stays evenly spread,
    which is what lets the probe stop early without having looked at only one end of a clip.

    Do NOT build this by bit-reversing range(2**k) and dropping values >= n. For n=40 that
    discards 24 of 64 slots unevenly, the prefixes stop being even, and it measures four
    correct answers worse (43 right instead of 47 over the 125 clips). Ranking all n indices
    by radical inverse is a true permutation for any n, which the assert keeps honest.

    Measured over the 125 clips, the ordering is load-bearing and not a matter of taste:
    vdc 47 right, golden-ratio 43, linear - the plain ascending order the probe used to
    take - 43.

    Returns INDICES, never times. The caller keeps sample i at its own t, so sample_i means
    what it always meant and evidence dumped before the waves existed stays comparable."""
    n = int(n_samples)
    if mode == "linear":
        order = list(range(n))
    elif mode == "vdc":
        order = sorted(range(n), key=lambda i: (radical_inverse2(i), i))
    elif mode == "golden":
        order = sorted(range(n), key=lambda i: ((i * 0.6180339887498949) % 1.0, i))
    else:
        raise ValueError("unknown wave order %r (vdc, golden or linear)" % mode)
    assert sorted(order) == list(range(n)), "wave order is not a permutation"
    return order


def wave_bounds(n_samples: int, waves, samples_ref: int) -> list:
    """Cumulative prefix lengths for the waves, as sample counts.

    waves is the schedule as tuned at samples_ref frames, so a run sampling some other
    number gets it scaled rather than, say, a wave of 8 out of 80. Strictly increasing, and
    the last bound is always n_samples - so passing waves=(n_samples,) gives one wave holding
    every frame, which is the all-at-once probe and how turning the schedule off costs no
    separate code path."""
    n = int(n_samples)
    out: list = []
    for c in waves:
        b = max(1, min(n, int(round(c * n / float(samples_ref)))))
        if not out or b > out[-1]:
            out.append(b)
    if not out or out[-1] != n:
        out.append(n)
    return out


def anchored_fractions(n_samples: int, lo: float = 0.02, hi: float = 0.98,
                       min_gap: float = 0.0, max_tries: int = 4096) -> list:
    """Where each sample sits in the clip, as a fraction of the duration, ANCHORED.

    The grid above puts sample i at (i + 0.5) / n. Every position is then a function of n,
    so raising the sample count does not ADD points - it relocates all of them. The 40-point
    grid and the 50-point grid share not one moment, which is why measuring 50 against 40
    compared two different 40s rather than 40 against 40-plus-10.

    Here the k-th point is lo + (hi - lo) * radical_inverse2(k), which does not mention n at
    all. So anchored_fractions(50)[:40] == anchored_fractions(40), exactly: wave one is the
    same eight moments whatever the total, raising the count is purely additive, and a
    sample id names one fixed moment of the clip instead of one slot of whichever grid was
    in force when it was recorded.

    The even spread the waves are built on is kept, because it is a property of the radical
    inverse and not of the grid: the first 2**m points land one in each 1/2**m band of
    [lo, hi), so eight points cover the window one per eighth, sixteen one per sixteenth,
    and every prefix spans the whole clip.

    lo and hi hold the samples off the very ends, where clips carry title cards, intros and
    black frames. Both are settable so that choice can be measured rather than inherited.

    min_gap, if set, refuses a candidate landing within that fraction of a point already
    taken. Check what the arithmetic allows before using it: the points lie on a dyadic
    grid, so 32 points sit (hi - lo)/32 = 3.0% apart and 64 points 1.5% apart, with nothing
    in between. A min_gap of 2% therefore takes the first 32 points and then refuses nearly
    everything after them: asking for 40 returns 33 and asking for 64 also returns 33. It
    does not thin the tail, it caps the count. This returns the short list in that case
    rather than quietly breaking its own rule, so a caller that sets min_gap must read len()
    of the result and not trust n_samples."""
    n = int(n_samples)
    lo, hi = float(lo), float(hi)
    span = hi - lo
    out: list = []
    k, tries = 0, max(int(max_tries), n)
    while len(out) < n and k < tries:
        f = lo + span * radical_inverse2(k)
        k += 1
        if min_gap > 0.0 and any(abs(f - g) < min_gap for g in out):
            continue
        out.append(f)
    return out


def nested_fractions(n_samples: int, lo: float = 0.02, hi: float = 0.98) -> list:
    """Evenly spaced positions that NEST when the count doubles.

    anchored_fractions buys a fixed position by giving up even spacing, and that spacing
    turns out to be load-bearing: measured over the 125 real clips, anchored sampling at 40
    frames answers 41 right / 2 wrong against the even grid's 46 / 1. Seven clips are lost
    and three gained. The reason is visible in show_sampling.py - 40 is not a power of two,
    so the radical inverse has subdivided eight of its 32 bands and not the other 24,
    leaving gaps of 1.5% next to gaps of 3.0% where the grid has 2.5% throughout.

    So the two properties are in tension, and this is the way to have both. The positions
    are lo + (hi - lo) * i / n, perfectly even, and DOUBLING the count keeps every one of
    them: 80 samples is the same 40 moments plus the 40 midpoints between them, because
    i/40 == 2i/80. The old (i + 0.5) / n grid cannot do this - a cell centre at one count is
    a cell boundary at twice the count, so 80 moves all 40.

    The price is that the count may only double. 50 samples cannot be the same 40 plus 10
    AND evenly spread, because 50 is not a multiple of 40 - which is the real reason the 40
    against 50 comparison measured nothing. The test to run is 40 against 80.

    Nesting needs n to be the base count times a power of two. At any other n the positions
    are still even but they no longer contain the base set, so a run like that is comparable
    on its own terms and not against another count - see nested_order."""
    n = int(n_samples)
    lo, hi = float(lo), float(hi)
    return [lo + (hi - lo) * i / n for i in range(n)]


def nested_order(n_samples: int, base: int = 40) -> list:
    """Visit order for nested_fractions: every refinement level before the next one.

    Level 0 is the base set - at n=80 and base=40 that is the even ids, which are the
    40-sample positions exactly. Level 1 is the midpoints. Taking whole levels in turn is
    what makes the WAVES additive as well as the positions: wave one is the same eight
    moments at 40 samples and at 80, the first 40 taken at n=80 are the n=40 set in the n=40
    order, and the extra 40 become later waves that only a clip which needs them ever pays
    for. Inside each level the order is the radical inverse, so every prefix is still spread
    over the whole clip.

    When n is not base x a power of two there are no levels to take in turn and this is the
    plain radical-inverse order over all n, as the grid uses. The positions are still even,
    so such a run is sound in itself; it simply does not contain the base set, so it cannot
    be read as "the base plus extras"."""
    n, b = int(n_samples), max(int(base), 1)
    out: list = []
    if n > b and n % b == 0 and (n // b) & (n // b - 1) == 0:
        step = n // b                   # the level-0 ids are the multiples of step
        while step >= 1:
            # ids first seen at this level: offset step//2 from level 0's, or all of them
            first = 0 if step == n // b else step
            ids = list(range(first, n, step if first else step))
            ids = [i for i in ids if i not in set(out)]
            out.extend(sorted(ids, key=lambda i: (radical_inverse2(ids.index(i)), i)))
            if step == 1:
                break
            step //= 2
    if len(out) != n:
        out = sample_order(n, "vdc")
    assert sorted(out) == list(range(n)), "nested order is not a permutation"
    return out

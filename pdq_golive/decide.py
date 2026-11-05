"""The go-live decision: the engine's rulebook (pv2_decide) behind two checks and fix 1.

1. Film-time check: a hit in the first GOLIVE_FILM_FIRST_S seconds of a film is ignored.
   Studio logos sit there (Paramount+ matched 63 films, its close matches 4-10 s in).
2. Quality check: a clip picture whose PDQ quality is under GOLIVE_MIN_Q is ignored.
   Plain cards score low (stoicindex 55) and look like dull pictures in hundreds of films.
3. Fix 1 (repeated still): if the winning film rests on GOLIVE_STILL_MIN or more pictures
   under GOLIVE_STILL_MAXDIST, and GOLIVE_STILL_SHARE of them are within GOLIVE_STILL_BITS of
   one picture, the answer is one image counted many times. Drop that film and decide again,
   at most GOLIVE_STILL_ROUNDS times.

Ported from output/logo_study/cards2/replay3.py (mk, guard 'both_a'). The parameters were
fixed there before any result was seen and are not tuned here.

The same function serves the offline replay (sig from the dump) and the live probe (sig from
the ProbeRun), so the laptop golden run and the pod run judge with one piece of code."""
from __future__ import annotations

import os


def _env(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


FILM_FIRST_S = _env("GOLIVE_FILM_FIRST_S", 20)
MIN_Q = _env("GOLIVE_MIN_Q", 70)
STILL_SHARE = _env("GOLIVE_STILL_SHARE", 0.6)
STILL_BITS = int(_env("GOLIVE_STILL_BITS", 10))
STILL_MIN = int(_env("GOLIVE_STILL_MIN", 3))
STILL_MAXDIST = _env("GOLIVE_STILL_MAXDIST", 33)
STILL_ROUNDS = int(_env("GOLIVE_STILL_ROUNDS", 4))


def _code(sig_row) -> int:
    return int.from_bytes(sig_row[0], "big")


def filter_hits(film_hits: dict, sig: dict, first_s: float = None, min_q: float = None):
    """film_hits without the hits the two checks ignore.

    film_hits is {vidx: {sample_i: (distance, clip_t, film_t, ...)}}; sig is
    {sample_i: (plain hash bytes, quality, clip_t)}. A picture with no sig entry is kept,
    exactly as the replay did. Returns (kept, dropped_by_time, dropped_by_quality), the
    last two as counts of (film, picture) hits."""
    first_s = FILM_FIRST_S if first_s is None else first_s
    min_q = MIN_Q if min_q is None else min_q
    kept, n_time, n_q = {}, 0, 0
    for v, hits in film_hits.items():
        g = {}
        for si, r in hits.items():
            if r[2] < first_s:
                n_time += 1
                continue
            s = sig.get(si)
            if min_q and s is not None and s[1] < min_q:
                n_q += 1
                continue
            g[si] = r
        if g:
            kept[v] = g
    return kept, n_time, n_q


def repeated_still(hits: dict, sig: dict) -> bool:
    """Does this film's evidence rest on one picture repeated? (fix 1)"""
    sis = [si for si, r in hits.items() if r[0] < STILL_MAXDIST and si in sig]
    if len(sis) < STILL_MIN:
        return False
    cs = [_code(sig[si]) for si in sis]
    best = max(sum(bin(a ^ b).count("1") <= STILL_BITS for b in cs) for a in cs)
    return best / len(cs) >= STILL_SHARE


def decide(pv2_decide, film_hits: dict, sig: dict, fix1: bool = True, checks: bool = True):
    """(hit, ranked, info). info says what the checks and fix 1 did, for the logs."""
    info = {"dropped_time": 0, "dropped_quality": 0, "still_dropped": []}
    if checks:
        f, info["dropped_time"], info["dropped_quality"] = filter_hits(film_hits, sig)
    else:
        f = film_hits
    rounds = STILL_ROUNDS if fix1 else 1
    for _ in range(rounds):
        hit, ranked = pv2_decide(f)
        if not hit or not fix1:
            return hit, ranked, info
        v = hit["vidx"]
        if repeated_still(f[v], sig):
            info["still_dropped"].append(int(v))
            f = {k: h for k, h in f.items() if k != v}
            continue
        return hit, ranked, info
    return None, [], info

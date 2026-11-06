"""Part 8: the checks, fix 1 and the profiles. Run with: python -m pytest pdq_golive/tests -q"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import decide as D      # noqa: E402
import profiles as P    # noqa: E402


def code(n: int) -> bytes:
    return n.to_bytes(32, "big")


def far(i: int) -> bytes:
    """Pictures that differ from each other in about 128 bits."""
    import random
    return random.Random(i).getrandbits(256).to_bytes(32, "big")


def fake_decide(fh):
    """Accept the film with most hits, if it has 3 or more; tier P1."""
    if not fh:
        return None, []
    v = max(fh, key=lambda k: len(fh[k]))
    if len(fh[v]) < 3:
        return None, []
    return {"vidx": v, "tier": "P1"}, [(0, 0, v, 0)]


def test_time_check_drops_only_hits_under_20s():
    fh = {1: {0: (10, 1.0, 5.0), 1: (10, 2.0, 19.9), 2: (10, 3.0, 20.0), 3: (10, 4.0, 300.0)}}
    kept, n_time, n_q = D.filter_hits(fh, {}, first_s=20, min_q=70)
    assert set(kept[1]) == {2, 3} and n_time == 2 and n_q == 0


def test_quality_check_drops_only_pictures_under_70():
    fh = {1: {0: (10, 1.0, 100.0), 1: (10, 2.0, 100.0), 2: (10, 3.0, 100.0)}}
    sig = {0: (far(0), 69, 1.0), 1: (far(1), 70, 2.0)}       # 2 has no sig: kept
    kept, n_time, n_q = D.filter_hits(fh, sig, first_s=20, min_q=70)
    assert set(kept[1]) == {1, 2} and n_q == 1


def test_fix1_drops_a_repeated_still_like_stoicindex():
    # 29 hits from one identical picture: the stoicindex case
    fh = {7: {i: (8, 14 + i * 0.1, 4531.2) for i in range(29)}}
    sig = {i: (code(12345), 90, 14 + i * 0.1) for i in range(29)}
    hit, _, info = D.decide(fake_decide, fh, sig)
    assert hit is None and info["still_dropped"] == [7]


def test_fix1_keeps_a_normal_answer_from_many_moments():
    fh = {5: {i: (12, i * 3.0, 600 + i * 3.0) for i in range(6)}}
    sig = {i: (far(i), 95, i * 3.0) for i in range(6)}
    hit, _, info = D.decide(fake_decide, fh, sig)
    assert hit["vidx"] == 5 and info["still_dropped"] == []


def test_fix1_moves_on_to_the_next_film():
    fh = {7: {i: (8, i, 900.0) for i in range(10)},                 # repeated still
          5: {20 + i: (12, 20 + i * 3.0, 600 + i * 3.0) for i in range(4)}}
    sig = {i: (code(1), 90, i) for i in range(10)}
    sig.update({20 + i: (far(i), 90, 20 + i * 3.0) for i in range(4)})
    hit, _, info = D.decide(fake_decide, fh, sig)
    assert hit["vidx"] == 5 and info["still_dropped"] == [7]


def test_logo_only_clip_is_silent():
    # every hit is the Paramount+ logo, 4-10 s into many films
    fh = {v: {i: (10, 28 + i * 0.2, 5.0 + i * 0.5) for i in range(9)} for v in (1, 2, 3)}
    sig = {i: (far(i), 100, 28 + i * 0.2) for i in range(9)}
    hit, _, info = D.decide(fake_decide, fh, sig)
    assert hit is None and info["dropped_time"] == 27


def test_checks_off_is_the_plain_rulebook():
    fh = {1: {0: (10, 1.0, 5.0), 1: (10, 2.0, 5.5), 2: (10, 3.0, 6.0)}}
    hit, _, _ = D.decide(fake_decide, fh, {}, fix1=False, checks=False)
    assert hit["vidx"] == 1


def test_profiles_set_the_engine():
    eng = types.SimpleNamespace(**{k: None for p in P.PROFILES.values() for k in p},
                                **{k: None for k in P.COMMON})
    s = P.apply(eng, "golive_g16")
    assert eng.PV2_SAMPLES == 160 and eng.PV2_GIVEUP_MIN_FRAMES == 16
    assert eng.PV2_MIRROR == "dihedral" and eng.PV2_MAXDIM == 640
    assert eng.PV2_WAVES == (8, 16, 24, 40, 80) and eng.PV2_VERIFY is False
    assert s["PV2_WAVE_BAR"] == "run"
    assert P.PROFILES["A"]["PV2_GIVEUP_MIN_FRAMES"] == 0
    assert P.PROFILES["B"]["PV2_GIVEUP_MIN_FRAMES"] == 24
    assert "golive_g16" in P.GUARDED and "A" not in P.GUARDED


def test_profile_unknown_setting_fails_loudly():
    eng = types.SimpleNamespace()
    try:
        P.apply(eng, "today")
    except AttributeError:
        return
    raise AssertionError("missing setting was not reported")


def test_placeholder_film_counts_as_no_answer():
    import loader as LD
    assert LD.is_unmapped("UNMAPPED:shard_001406")
    assert not LD.is_unmapped("43847:F1: The Movie (tmdb=911430)")

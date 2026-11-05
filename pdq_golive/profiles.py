"""Engine settings for each profile, applied to the loaded engine module before a run.

golive_g16 is the setting under test: Option A (160 nested pictures, the mirror read out of
the plain hash, frames shrunk to 640 like the index) that waits for 16 pictures before it may
give up. today, A and B are kept for comparison; they match cards2/time_settings.py.

The checks and fix 1 are not engine settings: they are the decide hook (decide.py). Only
golive_g16 turns them on by default; the comparison profiles run as the engine ships."""

COMMON = dict(PV2_WAVE_BAR="run", PV2_CARRY_FORWARD=True, PV2_TWO_STAGE=False,
              PV2_RESAMPLE=False, PV2_VERIFY=False, PV2_PASSES=False, PV2_BUDGET_S=0.0,
              PV2_ROTATE=False)

PROFILES = {
    "today": dict(PV2_SAMPLES=80, PV2_WAVES=(8, 16, 24, 40), PV2_MIRROR="pixel",
                  PV2_MAXDIM=0, PV2_GIVEUP_MIN_FRAMES=0),
    "A": dict(PV2_SAMPLES=160, PV2_WAVES=(8, 16, 24, 40, 80), PV2_MIRROR="dihedral",
              PV2_MAXDIM=640, PV2_GIVEUP_MIN_FRAMES=0),
    "B": dict(PV2_SAMPLES=160, PV2_WAVES=(8, 16, 24, 40, 80), PV2_MIRROR="dihedral",
              PV2_MAXDIM=640, PV2_GIVEUP_MIN_FRAMES=24),
    "golive_g16": dict(PV2_SAMPLES=160, PV2_WAVES=(8, 16, 24, 40, 80), PV2_MIRROR="dihedral",
                       PV2_MAXDIM=640, PV2_GIVEUP_MIN_FRAMES=16),
}

# Which profiles judge through the checks and fix 1 by default.
GUARDED = {"golive_g16"}


def apply(engine, name: str) -> dict:
    """Set the profile on the engine module; returns the settings applied."""
    s = dict(COMMON, **PROFILES[name])
    for k, v in s.items():
        if not hasattr(engine, k):
            raise AttributeError("engine has no setting %s" % k)
        setattr(engine, k, v)
    return s

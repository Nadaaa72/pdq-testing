# What the system has that the probe doesn't

*Jude's advice from the 26 September meeting: stop only moving the rule thresholds, change
the tech. Find what the full system has that the probe and the simple rules don't, give the
probe those missing pieces, and test on the clips. This is that comparison, the upgraded
probe built from it, and the measurements.*

Nada. October 2026.

## The three deciders, side by side

The engine has three ways of answering, and they are not equally equipped:

| capability | pre-scan | probe (P0) | full system (rules P1-P9) |
|---|---|---|---|
| sees the whole clip | yes, 40 sampled frames | **no, first 4 seconds only** | yes, every kept frame |
| all crop families | yes | **no, one family** | yes |
| the trimmed view (captions shaved off) | **no** | **no** | yes, first 40 frames |
| per-film scorecard (frames per band, average) | **no, just a count and a best** | **no, one best distance** | yes |
| film-time agreement (all hits give the same offset) | **no** | **no** | only P4, P5, P5x, P6a, P7, and my P8 |
| clip-time spread (hits from several moments) | **no** | **no** | only P4, P7, P9 |
| compares films against each other | picks the biggest vote | **no, takes the single best frame** | only P1.5, P3.5, P9E, P9 |
| minimum corroborating frames | 3 | **1** | 1 to 30 depending on the rule |

Two things jump out of that table.

**The probe is the thinnest decider in the engine.** One frame, under distance 30, from one
crop family, from the first four seconds. Every column that catches a coincidence is "no".
That is why the P0 change (requiring a second agreeing frame) was needed at all.

**But the pre-scan is nearly as thin, and it decides the most.** The 26 September measurement
showed the pre-scan produces about three quarters of all answers, right and wrong alike. It
has the one thing the probe lacks most - the whole-clip view - but it kept none of the
system's checking: no bands, no film-time agreement, no clip-spread. It counts hits and
takes the best. Four of the remaining wrong answers came through it, untouchable by any rule
change, because the rules never ran.

**And the one check the engine itself calls the signature of a true match is barely used.**
The engine's own notes say: *"offset = film time minus clip time. A true match gives the
same offset for every matched frame."* A real clip plays through the film, so every matched
frame lands at the same offset. A look-alike scatters. Yet the pre-scan ignores offsets, the
probe ignores them, and of the rules only the mid-tier ones check them. The strongest
structural signal in the data is unused by the parts that decide most of the traffic.

## The upgraded probe (probe V2)

`pdq_engine_PROBEV2.py` rebuilds the probe from those missing pieces. It keeps the
pre-scan's whole-clip view (40 sampled frames) and adds everything the table says was
missing:

- hashes the full frame, the **trimmed view** and **all crop families** for every sample
- keeps a **mini-scorecard per film**: distinct frames that hit it, best distance, and for
  every hit the pair (clip time, film time)
- checks **film-time agreement**: the largest group of hits that give the same offset,
  within 3 seconds
- checks **clip-time spread**: did the hits come from moments at least 3 seconds apart

Its rulebook is three tiers, each one copied from a rule the system already trusts:

| tier | fires when | mirrors |
|---|---|---|
| PV-A | 2 frames under 16, best under 12 | P2.5, two independent near-perfect frames |
| PV-B | 3 frames under 28, best under 20, **2 agreeing on film time** | the old pre-scan bar, plus P4's agreement check |
| PV-C | 5 frames under 33, best under 26, 3 agreeing, from 2 clip moments | P6a |

PV-B is the old pre-scan with one addition: the hits must agree about where in the film they
landed. A true match always passes that for free. A film that collects three unrelated
look-alike frames scattered through its running time no longer gets the answer.

With `PDQ_PROBE_ONLY=1` the probe is the entire engine: no streaming pass, no P1-P9, no
early reject. That is the test of "could we depend on the probe alone".

## Which rule gave each wrong answer

*(results from `attribute_rules.py`, filled in when the runs finish)*

## The measurement

*(same three numbers as always: wrong answers given, correct answers given, on the full
wrong + correct lists - filled in when the runs finish)*

## How to rerun any of this

```powershell
# which rule decided every clip, on any engine version:
python attribute_rules.py --engine pdq_engine_ORIGINAL.py
python attribute_rules.py --engine pdq_engine_PROBEV2.py --tag probeonly   # with PDQ_PROBE_ONLY=1 set

# results land in output/attribution_<engine>.csv, one row per clip, resumable.
```

`compare_before_after.py` now also prints, for every wrong answer that remains, the rule
that produced it, so no measurement ever reports a wrong answer without naming the rule
responsible.

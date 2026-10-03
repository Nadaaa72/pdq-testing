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

All 125 testable clips through the pod's ORIGINAL rules, pre-scan on as in production
(`output/attribution_ORIGINAL.csv`). Seven wrong answers reproduce, and every one is now
pinned to the rule that made it:

| rule | wrong answers | the clips, with the evidence they rode in on |
|---|---|---|
| SCAN (pre-scan) | 4 | Krrish 3 (best 6), The Northman (best 6), Captain America: Civil War (best 12), The In Between (best 18) |
| P0 (old probe) | 1 | Smile (avg 26.8, 5 frames) |
| P9E | 1 | Grave Encounters 2 (avg 34.0, 2 frames) |
| P8 | 1 | The Last Voyage of the Demeter (avg 41.4, 31 frames) |

The correct answers come from: SCAN 46, P0 3, P3.5 2, P1 1 - 52 in total.

What this table proves: **the majority of wrong answers (4 of 7) come from the pre-scan**,
at distances 6 to 18 - genuinely identical pictures - which is why no rule change could
ever reach them. The three that do come from rules (P0, P9E, P8) are exactly the three my
earlier changes target.

## The measurement

Same yardstick as every week: wrong answers given and correct answers given, all 125 clips.

| engine | wrong answers | correct answers |
|---|---|---|
| The pod's ORIGINAL rules | 7 | 52 |
| **Probe V2 alone** (no streaming pass at all) | **1** | 41 |

The probe alone removes six of the seven wrong answers. The one survivor is Krrish 3 at
distance 6: the clip's pictures are identical to pictures in the index, so no
picture-based check can refuse it. That one belongs with the orchestrator and the other
detectives, with its scorecard.

The cost is 11 correct answers (52 down to 41), and the pattern in them is the real
finding: **in every lost case the right film was still the probe's top hint** - it just
failed the new agreement bar. Most are montage-style clips (Soul, The Walking Dead, Bade
Miyan ...) where a true match genuinely scatters across film time because the clip cuts
between scenes. One (F1) is a sampling miss: the film occupies a small part of the clip
and 40 spread samples barely touch it.

Loosening the agreement bar to recover them would let The Northman and Civil War straight
back in - on picture evidence those wrong answers look exactly like Soul. So the answer is
not a looser probe. The two honest options:

1. **Probe V2 as the decider, streaming rules as the fallback** (the drop-in mode): clips
   the probe trusts are answered on the spot; clips it does not fall through to the full
   pass, where P1/P3/P6 catch the montages with far more evidence. Measured next.
2. Probe-only, and the 11 montage clips hand over to audio and SSCD as hints - the same
   trade as "a no answer beats a wrong one", but now it costs real correct answers, so it
   needs Jude's judgement, not mine.

In this engine version the old P0 is retired (the probe V2 replaces it - Smile came
through P0) and P9E keeps the V3 sliding floor (Grave Encounters 2).

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

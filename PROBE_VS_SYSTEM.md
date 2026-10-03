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
not a looser probe but the **drop-in mode**: probe V2 decides what it trusts, and clips it
does not fall through to the streaming rules, where P1/P3/P6 see far more evidence. In
this engine version the old P0 is retired (the probe V2 replaces it - Smile came through
P0) and P9E keeps the V3 sliding floor (Grave Encounters 2). Measured:

| engine | wrong | correct |
|---|---|---|
| The pod's ORIGINAL rules | 7 | 52 |
| Probe V2 alone | 1 | 41 |
| **Probe V2 + streaming fallback (drop-in)** | **1** | **48** |

Six of seven wrong answers gone for the price of four correct ones - and those four
(Race to Witch Mountain, Bruce Almighty, This Is Where I Leave You, The Walking Dead) are
montage clips the probe declines and the streaming pass then early-rejects before reaching
the matching segment. Recovering them means readmitting Northman and Civil War; on the
"a no answer beats a wrong one" rule I have left them out, but it is a policy choice and
I would like Jude's confirmation.

Two flags from the full tables:

- The "Misfits" wrong-list clip is answered **F1: The Movie** (P1, distance 8) by both
  the pod's ORIGINAL rules and probe V2 - the pod's live answer was The Misfits. Either
  the index has changed or the live answer came from another detective. Ground truth
  unknown; worth checking the clip.
- Krrish 3, the one wrong answer no version removes, matches at distance 6: the pictures
  are identical to pictures in the index. Not solvable by any picture-based check.

## How the system copes with edited clips

Ten edits a reposter actually makes, applied one at a time to 8 clips every engine
identifies correctly unedited, so any failure is caused by the edit alone
(`make_edited_clips.py`, tested by `test_edits.py`). Right answers out of 8 (* = /7, one
variant file was corrupt):

| edit | pod ORIGINAL | probe V2 before fixes | probe V2 after fixes |
|---|---|---|---|
| colour filter | 8 | 8 | 8 |
| black and white | 8 | 8 | 8 |
| heavy recompression | 8 | 7 | 7 |
| speed x0.8 | 8 | 8 | 8 |
| speed x1.25 | 7 | 6* | 6* |
| caption bars | 6 | 5 | 5 |
| zoom 20% | 5 | 3* | 3* |
| rotation 2 deg | 5 | 1 | 1 |
| **letterbox** | **1** | **1** | **6** |
| **mirror** | **0** | **0** | **8** |

No edit ever produced a wrong film on any engine - edits only silence the system. The two
catastrophic holes were both "what the pod-side tech has that this decider doesn't":

- **Mirror (0 of 8 everywhere)**: nothing hashed flipped frames. The probe V2 now hashes
  the mirror of every sampled view. Mirrored reposts went from never identified to 8 of 8,
  at distance 2 - PDQ sees through the flip perfectly once someone looks.
- **Letterbox (1 of 8)**: the pod's *active region crop* was the speed trick left out of
  the laptop port. The probe V2 now trims near-black bars (`active_region()`) and hashes
  the picture inside; 1 of 8 became 6 of 8. The two still missed have non-black bars after
  recompression.
- **Speed changes did NOT break the film-time agreement check** - the 3-second tolerance
  absorbs a 25% speed change over a sampled clip. The planned drift fix was not needed.
- Rotation and zoom degrade the hashes themselves (PDQ is not rotation-invariant); the
  pod only survives them through its weakest rules (P3.5, P0, P9). In drop-in mode those
  clips fall through to the same rules, so nothing is lost against the pod.

The gate for the fixes: re-running the full 125 real clips with the new views changed
**zero answers** - 1 wrong / 48 correct in drop-in mode and 1 / 41 probe-only, before and
after. The mirror and bar-trim views are purely additive.

One honest cost: the extra views make the probe about four times more search-heavy per
clip (roughly 2 minutes instead of 30 seconds on my laptop against 16.7 million
fingerprints). Irrelevant for this measurement work, but if the probe ever replaces the
pre-scan on the pod, the obvious shape is: plain views first, and the mirror and bar-trim
views only when the plain views found nothing. Ordinary clips then cost exactly what the
pre-scan costs today, and only the suspicious ones pay for the second look.

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

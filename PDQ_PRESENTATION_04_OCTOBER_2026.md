# PDQ: the week in numbers

*4 October 2026. Nada.*

| | before | after |
|---|---|---|
| wrong answers (125 clips) | 7 | **1** |
| correct answers | 52 | 48 |
| mirrored clips identified | 0 of 8 | **8 of 8** |
| letterboxed clips identified | 1 of 8 | **6 of 8** |

---

## 1. What was working before

The pod's PDQ engine, as an exact laptop copy (verified identical). Three parts can
produce an answer, and they run in this order:

1. **The pre-scan.** Before anything else: 40 frames spread across the whole clip, a
   quick vote. If one film clearly owns those pictures, it answers and nothing else runs.
2. **The probe (P0).** If the pre-scan didn't answer: after about a second of reading
   the clip, one quick look - is any single frame close to some film? If yes, answer.
3. **The rules (P1-P9).** If neither quick part answered: keep reading, build a
   scorecard per candidate film, rules watch the scorecards, first to fire wins.

It genuinely was working, mostly: **52 of 125 known clips right, 7 wrong.**

## 2. How it was working, exactly

**The pre-scan's vote**

- a sampled frame is a "hit" on a film if its closest fingerprint is under distance 28
- a film is accepted on 3 hits with the best under 20
- never asks whether the hits agree where in the film they land, or whether they came
  from different parts of the clip

**The probe's test**

- first seconds only, one crop shape, up to 64 fingerprints, one search
- any single fingerprint under distance 30 -> answer. One frame, from the "probably"
  band, not the "certain" band

**The rules**

- the scorecard counts matched frames in 3 quality bands, keeps the best distance,
  and keeps where in the film each hit lands (the offset) and which clip seconds
  produced it
- the careful rules use all of it - P4 wants 5 strong frames that agree on film
  position AND come from 2 different moments of the clip
- but the rules only ever see the clips the quick parts passed over

## 3. Where the wrong answers came from

All 125 clips run, every answer tagged with the rule that made it:

| part | wrong answers | the clips (brackets = distance) |
|---|---|---|
| pre-scan | 4 | Krrish 3 (6), The Northman (6), Civil War (12), The In Between (18) |
| probe P0 | 1 | Smile (26.8, five frames) |
| rule P9E | 1 | Grave Encounters 2 (two frames, avg 34) |
| rule P8 | 1 | Demeter (31 weak frames, avg 41) |

![attribution printout](output/shots/rules_original.png)

- Distances 6 to 18 on the pre-scan four: those pictures genuinely are in our library,
  attached to the wrong film (shared footage). The pre-scan answers before the rules
  run, so no rule change can ever touch them. The last three rules (P8, P9E, P0) are
  the ones I tightened in previous weeks.

**So the actual problem:**

- The engine knows how to check properly - it just doesn't check where it matters.
- The good checks exist: *do the matched frames point at the same place in the film?
  did they come from more than one moment of the clip?* But they are written inside
  the mid-tier rules (P4, P6a, P7), and the rules only see a clip if the pre-scan and
  probe both passed on it first. In practice they almost never pass.
- So most clips get judged by the parts that ask the fewest questions, and the parts
  that ask the right questions only see the leftovers.
- Four of the seven wrong answers came through the pre-scan, which never asked whether
  the hits agreed on film position. They didn't - and that one question would have
  caught three of them.

## 4. What I built

**1. Attribution testing** - every clip run records which part of the engine gave the
answer. Before, a wrong answer was just a number; now it has the name of the rule that
made it next to it. The table above is its output.

**2. The rebuilt probe.** It samples 40 frames across the whole clip, like the
pre-scan. For each sampled frame it fingerprints **every view**:

- A clip's frame is almost never the film frame as fingerprinted: the creator cropped
  it for a phone screen, zoomed it, TikTok drew captions over it. The film is hiding
  somewhere inside the frame.
- So each frame is fingerprinted several ways: the whole frame, the caption-trimmed
  frame, centre cut-outs in the common shapes at two zoom levels - and, after this
  week, the mirror of each and the view inside black bars.
- The old pre-scan never tried the caption-trimmed view; the old probe tried one shape
  only. They could miss a match purely because of framing. The new probe makes every
  guess.

Per film it keeps a **scorecard**: distinct frames that hit it, best distance, and for
every hit the pair (clip time, film time) so it can check the offsets. The old probe
kept no scorecard at all - it decided on one number. This gives the deciding part the
scorecard.

It answers in **three situations only**, each copied from a rule the pod already
trusts. The ladder: the worse the pictures, the more agreement demanded.

| bar | asks | copied from | impact (of its 41 answers) |
|---|---|---|---|
| PV-A | two frames basically identical to the film (under ~12-16)? One can be a fluke, two separate ones can't | P2.5 | 22 answers, e.g. mirrored Magadheera at distance 2 |
| PV-B | a few decent frames (3 under 28, best under 20 - exactly the old pre-scan bar) AND two agreeing where in the film they sit? (that agreement is P4's check) | pre-scan + P4 | 17 answers; refuses Northman, Civil War, In Between |
| PV-C | only mediocre frames (5 under 33)? then prove it twice: 3 agreeing on film position, from 2 different clip moments | P6a | 2 answers (heavily filtered clips) |

And the old probe's question - "is there one frame under 30?" - **no longer exists**.
That question is how Smile got wrongly answered; Smile now fails all three bars (best
frame 22: not identical, not under 20) and the probe stays quiet.

## 5. The probe on real clips (real printouts, rerunnable)

**A right answer - the Brick clip.** 13 frames hit Brick, best distance 8, and three
hits land at film minute 19.1 with the same offset. PV-B: decent frames, two agreeing
-> PASS. Answer: Brick.

![a right answer walked through the bars](output/shots/walk_brick.png)

**The look-alike - the Northman clip.** One frame at distance 6 (the shared footage),
others at 16-44, but the offsets scatter: minutes 37, 40, 43, 49. No two agree. PV-A:
only one near-perfect frame, fail. PV-B: decent count, agreement of one, fail. PV-C:
fail. The probe stays quiet.

![a wrong answer walked through the bars](output/shots/walk_northman.png)

**Both clips pass the old pre-scan's bar.** On "count and best" they are
indistinguishable - that is exactly how Northman got wrongly answered. The agreement
question is the only thing that separates them.

**The honest third case - the Soul clip.** Five hits, all agreeing perfectly (every
offset 32.2 minutes - a true scene's signature), but only two frames under 28 because
the film occupies just the first seconds of the clip. Thin evidence, so the probe
declines - and the fallback rules read the clip densely and name Soul via P1.
Declined is not lost.

![a true scene the probe hands to the rules](output/shots/walk_soul.png)

**The two cases that remain, and why:**

- **Krrish 3, the one wrong answer left.** Its pictures match at distance 6 AND agree
  on film position - every test we have says genuine, because those exact frames
  really are in our library under Krrish 3 (reused footage). When pictures say yes in
  every way pictures can, only a different kind of evidence can say no: audio, SSCD.
- **The four lost correct answers - fan edits.** A fan edit cuts together moments of
  one film, so its hits genuinely scatter - which is exactly what the Northman case
  looks like. Same evidence shape, opposite truth. No setting keeps the four and
  blocks the two, so it is a choice of which mistake to prefer. Per "a no answer
  beats a wrong one" I chose strict - that call is the policy question I'm bringing.

## 6. Results

| engine | wrong | correct |
|---|---|---|
| pod's rules | 7 | 52 |
| new probe alone | 1 | 41 |
| **new probe + rules backup** | **1** | **48** |

![measured](output/shots/rules_probev2.png)

**Edited clips** (10 reposter edits x 8 clips that work unedited):

![the two blinding edits](output/shots/edit_examples.png)

| edit | before | after |
|---|---|---|
| mirror | 0 of 8 | **8 of 8** (distance 2) |
| letterbox | 1 of 8 | **6 of 8** |
| filter / b&w / recompress / speeds | 6-8 of 8 | unchanged |

- No edit ever produced a wrong film, on any version. Edits silence, never fool.
- Safety gate: all 125 real clips re-run with the fixes. Zero answers changed.

**The week, before against after:**

| | before | after |
|---|---|---|
| wrong answers | 7 | **1** (Krrish 3: identical pictures, needs audio/SSCD) |
| correct answers | 52 | 48 (the 4 lost are fan edits - the policy question) |
| agreement checked where most decisions happen | no | yes |
| minimum evidence for an answer | 1 frame | 2 near-identical frames |
| mirrored clips identified | 0 of 8 | **8 of 8** |
| letterboxed clips identified | 1 of 8 | **6 of 8** |
| wrong films caused by edits | 0 | 0 |
| every answer names its rule | no | yes |
| probe cost per clip | ~30 s | ~2 min (normal-views-first restores it) |

## The asks

1. Policy call: the 4 fan-edit clips. I recommend staying strict.
2. Someone watches the Misfits clip (both engines say F1, distance 8).
3. Direction: take the probe towards the pod? Next step: normal-views-first at pod scale.
4. Still open: keep clip_query_hashes rows for voted clips. Clips are still rotting.

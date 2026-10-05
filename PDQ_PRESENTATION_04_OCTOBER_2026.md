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

- The pod's engine, as an exact laptop copy. 52 of 125 known clips right, 7 wrong.
- Three parts can answer, in order: pre-scan, probe (P0), then the rules.

| decider | evidence it needs | checks offsets? | share of answers |
|---|---|---|---|
| pre-scan | 3 frames, best under 20 | no | most |
| probe P0 | 1 frame under 30 | no | some |
| rules P1-P9 | 1 to 30 frames by rule | only the mid rules | the rest |

## 2. How it was working

- The quick parts decide most clips on counting alone. The careful checks sit in rules
  that rarely decide.
- A true match gives the same offset (film time minus clip time) for every frame.
  Nothing that decides most of the traffic checks this.
- Every answer now records the rule that made it. The seven wrong answers:

| rule | wrong answers | distance |
|---|---|---|
| pre-scan | 4 (Krrish 3, Northman, Civil War, In Between) | 6 - 18 |
| P0 probe | 1 (Smile) | 26.8 |
| P9E | 1 (Grave Encounters 2) | 34.0 |
| P8 | 1 (Demeter) | 41.4 |

![attribution printout](output/shots/rules_original.png)

- Four of seven come from the pre-scan. Rule changes can never reach them.

## 3. What I built

- **Attribution testing**: every answer tagged with the rule that produced it.
- **A rebuilt probe**: whole-clip view + the careful checks, as one decider.
- **An edits test**: 10 reposter edits x 8 clips that work unedited.
- **Two fixes**: mirrored views, and cutting black bars before fingerprinting.

## 4. How the new probe works

- Samples 40 frames across the whole clip; keeps a scorecard per film: frames, best
  distance, and every hit's (clip time, film time) pair.
- Answers only when the evidence agrees like a real scene does:

| bar | needs | copied from |
|---|---|---|
| PV-A | 2 near-identical frames | P2.5 |
| PV-B | 3 frames, best under 20, 2 agreeing on offset | pre-scan + P4 |
| PV-C | 5 medium frames agreeing, from 2 clip moments | P6a |

- The one-frame P0 is retired. The rules stay behind it as backup.

**Proof, on real clips. Both pass the OLD pre-scan bar; only the agreement question
separates them:**

![a wrong answer walked through the bars](output/shots/walk_northman.png)

![a right answer walked through the bars](output/shots/walk_brick.png)

**And the honest third case: a true scene with thin evidence. Perfect agreement
(every offset 32.2) but too few frames, so the probe declines - and the fallback
rules then name Soul via P1. Declined is not lost:**

![a true scene the probe hands to the rules](output/shots/walk_soul.png)

## 5. Results

**Real clips, all 125:**

| engine | wrong | correct |
|---|---|---|
| pod's rules | 7 | 52 |
| new probe alone | 1 | 41 |
| **new probe + rules backup** | **1** | **48** |

![measured](output/shots/rules_probev2.png)

- The 1 left: Krrish 3, distance 6, identical pictures. Needs audio / SSCD.
- The 4 lost: fan edits that jump scenes. Recovering them readmits 2 wrongs. Kept strict.

**Edited clips:**

![the two blinding edits](output/shots/edit_examples.png)

| edit | before | after |
|---|---|---|
| mirror | 0 of 8 | **8 of 8** (distance 2) |
| letterbox | 1 of 8 | **6 of 8** |
| filter / b&w / recompress / speeds | 6-8 of 8 | unchanged |

- No edit ever produced a wrong film, on any version. Edits silence, never fool.
- Safety gate: all 125 real clips re-run with the fixes. Zero answers changed.
- Cost: probe 4x slower with extra views. Pod shape: normal views first.

---

## The asks

1. Policy call: the 4 fan-edit clips. I recommend staying strict.
2. Someone watches the Misfits clip (both engines say F1, distance 8).
3. Direction: take the probe towards the pod? Next step: normal-views-first at pod scale.
4. Still open: keep clip_query_hashes rows for voted clips. Clips are still rotting.

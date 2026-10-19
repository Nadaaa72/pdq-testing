# PDQ: the first stage now reads half as much and answers the same

*11 October 2026. Nada.*

The pipeline's first stage used to fingerprint all 40 sampled frames of every clip before
looking at a single result. It now reads them in waves and stops as soon as it knows. A
typical clip went from **8.3 seconds to 3.2 seconds**, and **not one answer changed** across
205 clips.

---

## 1. What I changed

**The probe reads in waves.** 8 frames, then 16, then 24, then all 40. After each wave it
asks two questions: can I answer already, and is there anything here at all? A clip that can
be identified usually declares itself in the first 8 frames. A clip that is not in the
catalogue shows nothing in the first 8 and is abandoned there. Only genuinely difficult clips
pay for all 40.

**The frames are re-ordered so that reading fewer is safe.** The rules reward frames that
agree about where in the film they came from. Eight frames taken off the front of a clip all
come from the opening seconds and have nothing to agree about. The order is now arranged so
that any number of frames, counted from the front, is spread across the whole clip. Wave 1
lands at 1%, 11%, 21%, 41%, 51%, 61%, 81% and 91% of the way through.

**Three duplicate frame-extraction paths became one.** Seeking to a timestamp is the expensive
part of reading a clip, 15% of total runtime. The probe, the re-sampling pass and the
walkthrough tool each had their own decode loop, so the same timestamps were sought up to
three times per clip. The three had also diverged — different resolution handling, different
view sets — which meant the diagnostic tool did not reflect engine behaviour. They are now a
single component holding one open video handle, caching decoded frames and which fingerprints
have been taken from each. This is a precondition for the wave design: progressive sampling
only pays off if later waves reuse what earlier ones decoded instead of re-seeking from
scratch.

**The cost is measured for the first time.** The probe now records seeking, fingerprinting
and searching separately, which is how we know fingerprinting is 73% of the bill and
therefore the only thing worth cutting.

**Declined clips carry a scorecard.** When the probe gives up it now says how close it got:
best distance, how many frames agreed, which crop shapes saw it. This is the hand-off to the
audio and face engines.

**The sample size is now a setting.** It was hard-coded at 40 and could not be measured. It
now reads `PDQ_PROBE_SAMPLES`, so claims about sample size can be tested rather than assumed.

**Four bugs fixed on the way.** One edited test clip could never be built, because the zoom
filter produced an odd pixel width that H.264 cannot encode; it had looked like a failed
download for weeks. The re-sampling pass used a spacing fixed at 40 frames, so any other
sample count got windows of the wrong width. Saved evidence double-counted matches when a run
was interrupted and resumed. The plain-views pass still built and discarded the mirrored
copies, about 6 MB of pointless work per frame.

## 2. How I tested it

**Six complete runs, three independent sets of clips, 612 clip measurements.**

| run | clips | purpose |
|---|---|---|
| 125 real clips, old all-at-once probe | 125 | the baseline to beat |
| 125 real clips, new wave probe | 125 | same answers, less time |
| 125 real clips, staged two-pass | 125 | an idea being tested |
| 80 edited clips, wave probe | 80 | robustness to crops, mirrors, speed |
| 80 edited clips, staged two-pass | 80 | the same idea, second set |
| 77 clips never seen before | 77 | held-out accuracy |

Two more runs confirmed the whole engine's current numbers and tested a 50-frame sample size.

**Everything was replayable before it was built.** 455 clips were fully fingerprinted into
saved evidence files, recording every frame, every match and every distance. That let each
wave schedule, give-up rule and frame ordering be tested offline in about a second each,
against evidence already on disk, before the engine was touched. The schedule that shipped
was chosen that way, not guessed.

**The equivalence check is a comparison, not a judgement.** Both versions ran over the same
clips and the answers were compared one clip at a time. "Same" here means the same film named
on every clip, not similar scores.

**The held-out set is the only measurement that is not in-sample.** It is built from clips
where another engine answered and a user confirmed the film, so the truth comes from a person
and PDQ never answered them. None of its thresholds were fitted to any of those clips.

## 3. The measurements

**Speed, stage 1 only, 125 clips**

| | before | after |
|---|---|---|
| typical clip | 8.3s | **3.2s** |
| all 125 clips | 23.3 min | **11.3 min** |
| pictures fingerprinted | 100% | **49%** |
| answers that changed | — | **0 of 205** |

**Where the time goes** (measured for the first time): fingerprinting 73%, seeking 15%,
searching 12%. Cutting the number of pictures is the only lever that matters.

**Clips it had never seen, 77 clips, 68 different films**

- film in the catalogue: **15 of 40 named right, 0 named wrong**
- film not in the catalogue: **37 of 37 stayed silent, 0 false alarms**
- every answer it gave was correct, 15 of 15
- typical clip 2.9s

**Edited clips, 80 clips**: 64 identified. Mirrored clips 8 of 8, letterboxed 7 of 8, greyscale
8 of 8, low quality 8 of 8, speed changes 14 of 16. The weakest are rotation (2 of 8) and
zoom (4 of 8).

**The scorecard bands predict what happens next**, which is what makes them useful for routing:

| scorecard | clips | later identified |
|---|---|---|
| strong | 46 | 87% |
| medium | 22 | 32% |
| weak | 33 | 0% |

A clip in the weak band has never once turned out to be identifiable.

## 4. Before and after

**The whole engine, all three stages, 125 clips**

| | pre-scan (before) | probe in waves (now) |
|---|---|---|
| right answers | 52 | **51** |
| **wrong answers** | **7** | **1** |
| clips answered | 61 | 54 |
| a typical clip, whole engine | 9.7s | **5.7s** |

**Same recall and one seventh the wrong answers.** The times above are the whole engine.
Stage 1 on its own went from 8.3s to 3.2s; the old pre-scan's stage-1 time was never
measured separately, so it cannot be compared directly.

Two changes produced that, and they should be credited separately:

**The probe replacing the pre-scan (September) bought the accuracy.** The pre-scan accepted a
film on three frames being close and never asked whether those frames agreed about where in
the film they came from. The probe demands that agreement and also checks mirrored and
letterboxed versions. That is what took wrong answers from 7 to 1, and mirrored clips from 0
of 8 identified to 8 of 8.

**The waves (this week) bought the speed, and deliberately nothing else.** Identical answers
on all 205 clips. If accuracy had moved, that would have been a bug.

**What the system looks like now, end to end:** a fast front door with 6 rules — PV-A, P1,
PV-B, PV-E, PV-C and P3.5 — that answers 48 of 125 clips in about 3 seconds, backed by the
full 14-rule streaming pass that picks up 6 more when the probe declines.

## 5. Measured and turned off

Three ideas were built or tested and rejected on their own numbers. The measurements ship
next to the code so nobody repeats them.

**Cropped pictures first, in two passes.** The cropped pictures carry most of the matches, so
running them first should pay, and on edited clips it did — a third faster. On real clips it
was **27.2 minutes against 11.3**. The staged design never reaches a point where it can walk
away, so the 77 clips that are not in the catalogue plod through every stage. The wave probe
abandons those after 8 frames. The edited suite could not reveal this, because almost
everything in it matches something.

**Fingerprinting at lower resolution.** Nearly four times faster per picture, and the stored
fingerprints were built at that size anyway. It swapped one right answer for one wrong one:
precision 97.9% down to 93.9%.

**Sampling 50 frames instead of 40.** Found fewer, not more: 13 against 15 on the held-out
clips. Raising the count does not add frames, it moves them — the 50 sample moments share
none of the 40 sample moments, so it is a reshuffle rather than extra coverage.

## 6. What is not proven

Three things, stated plainly because they are the questions the room will ask.

**How much it finds is uncertain, and both test sets are biased.** On the clips the rules were
tuned on it finds 57% of in-catalogue clips; on clips it had never seen, 38%. The tuned set
was built from clips PDQ itself answered and a user confirmed, so every clip in it is one PDQ
had already proved it could identify. The held-out set was built from clips another engine
answered, so it is disproportionately clips PDQ struggles with. The true rate sits between the
two and neither test locates it. Finding it needs clips sampled at random from traffic with
the films checked by hand.

**Precision held up, and that is the stronger result.** 15 answers, 15 correct, no false alarms
in 37 chances. When it speaks, it is right.

**We are testing on 0.9% of the real catalogue.** The pod's index holds **14,653 films, 70.9
GB**. Our local index holds **134 films, 0.74 GB**. This matters in both directions. Recall
measured locally is too pessimistic, because a clip whose film we do not hold can never be
found here. Precision measured locally is probably too optimistic: the index is searched
exhaustively, so with 97 times more fingerprints the closest match to any random frame gets
closer by chance, and the distance thresholds were tuned against 134 films. **The 1 wrong
answer in 48 is a 134-film number, not a pod number.**

**The one wrong answer is disputed, not clearly wrong.** It is a clip answered as *Krrish 3*
where one user pressed "wrong" and a different user pressed "correct". The pictures match at
distance 6 out of 256, and 13 of the 40 correct answers are at distance 6 or closer, so no
threshold can reject it without rejecting those too.

## 7. What comes next

**Test it as the index grows.** `bench_scale.py` already exists for this and has never been
run. It rebuilds the index at increasing sizes, re-runs the clips at each one, and fails if any
clip answered correctly at the small size stops being answered at the large one. The full 71 GB
index cannot be built on a laptop — it needs about 88 GB of RAM — but an 8 GB index with
roughly 1,458 films is eleven times the current size and would take about two hours end to
end. If precision slips there, it will be worse on the pod, and we would know before shipping.

**Decide the time budget.** The probe finds 22 of 125 clips if capped at 1.5 seconds, 36 at 2
seconds, 43 at 3 seconds and 47 at 5 seconds, which is everything it can find at all. The
curve is steep to 3 seconds and almost flat after. That is a product decision.

**Delete the dead pre-scan.** `whole_clip_prescan` is still in the file and nothing calls it.

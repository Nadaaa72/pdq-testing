# Meeting prep: the probe speed-up

*12 October 2026. Nada. For the session with Jude. This is my own notes, not a handout.*

Every number here is one I measured, with where it came from. The questions in Part 5 are the ones I think are coming, grouped so I can find them.

---

## Part 1 — The system in four sentences

A clip arrives. **Stage 1** takes a quick look: it samples 40 frames spread across the clip, makes fingerprints of them, and searches our library to see if one film owns those frames. If stage 1 is confident it answers and nothing else runs. If not, **stage 2** decodes the clip properly and **stage 3** runs fourteen rules over the evidence as it builds up.

**Everything I changed is in stage 1.** Stages 2 and 3 I did not touch.

### Words to be able to define

**Fingerprint.** A short code describing what a picture looks like. Similar pictures get similar codes. We store one for every few frames of every film we hold: 16.7 million of them.

**Distance.** How different two fingerprints are, out of 256. Zero is identical. Under 16 is effectively the same picture. Over 40 is unrelated.

**Frame vs picture.** We sample 40 **frames**. From each we make about 11 **pictures**: the whole frame, crops for different phone shapes, and mirrored copies in case the clip was flipped. So 40 frames is about 440 fingerprints.

**Offset agreement.** If a clip really is from a film, every matching frame should point at a consistent position in that film. Frames that agree are evidence; frames matching all over the place are coincidence. The old pre-scan never checked this. It is the single biggest reason the probe is more accurate.

**Spread.** Whether the matching frames come from different moments of the *clip*, not just different moments of the film. Guards against one lucky still.

---

## Part 2 — What I changed

**1. It reads in waves and stops when it knows.** Before: all 40 frames, always, then decide. Now: 8, decide, 16, decide, 24, decide, 40. It stops either because a rule has fired and more frames cannot change the answer, or because nothing anywhere has come close and more frames will not help.

**2. The frames were re-ordered, which is what makes stopping safe.** The first 8 slots in order would all be from the opening seconds, and the rules need frames that agree about film position. The order now keeps any number of frames, counted from the front, spread across the whole clip. The first 8 land at roughly 1%, 11%, 21%, 41%, 51%, 61%, 81% and 91%.

**3. The clip is opened once instead of up to three times.** Jumping to a moment in a video file is slow, 15% of total time. Three parts of the code each opened the clip and jumped through it, and they had drifted apart, so the diagnostic tool showed something different from what the engine did. Now one piece of code opens the clip once and remembers which pictures it has already made from each frame. Without that, each wave would redo the previous wave's jumping and stopping early would save nothing.

**4. I measured where the time goes.** Fingerprinting 73%, jumping to frames 15%, searching 12%. Nobody had split this before. It is why the whole approach is "make fewer pictures".

**5. Declined clips carry a scorecard.** How close it got, how many frames agreed, which crop shapes saw it. Clips in the weak band have never once turned out to be identifiable, so it is a cheap routing signal for the audio and face engines.

**6. The frame count is adjustable.** It was fixed at 40, inherited, never justified. Now testable.

**7. Four bugs.** A test clip that could never be built, because the zoom produced an odd pixel width that video encoders reject; it had looked like a failed download for weeks. A second-look pass using windows of the wrong width. Saved results counted twice after an interrupted run. Mirrored copies built and discarded on passes that never used them.

---

## Part 3 — The six rules stage 1 can fire

If Jude asks what the probe actually decides on. It tries them in this order and takes the first that fits.

| Rule | What it wants | In plain terms |
|---|---|---|
| PV-A | 2 frames under distance 16, best under 12 | two almost perfect matches |
| P1 | best under 15, 3 frames under 28, 2 agreeing on film position | one excellent frame with support |
| PV-B | 3 frames under 28, best under 20, 2 agreeing | the old pre-scan bar, plus agreement |
| PV-E | 2 separate groups of agreeing frames, 2 each, best under 33 | corroboration from two places |
| PV-C | 5 frames under 33, best under 26, 3 agreeing, from 2 clip moments | lots of medium evidence that lines up |
| P3.5 | only one candidate film, sliding bar by frame count | nothing else is even in the running |

Stages 2 and 3 hold the full fourteen rules. The probe is a fast front door, not a replacement for them.

---

## Part 4 — How I know it did not break anything

**Both versions ran over the same clips and answers were compared one clip at a time.** Not scores, not totals. Same clip, same film named, or it counts as a difference. No differences, on 125 real clips and 80 edited ones.

**The full evidence for 455 clips is saved.** Every frame, match and distance. Any rule change can be re-tested in about a second against results on disk without touching a video. That is how the wave sizes, give-up rule and frame order were chosen before the engine was touched.

**The offline replay and the live engine agree exactly.** Replaying the saved evidence gives 48 answers and 49% of the frames. The live run gives 48 answers and 49%. If the simulation were wrong, those would not match.

**The greedier options were measured and rejected.**

| When it gives up | Frames read | Clips lost |
|---|---|---|
| Never | 83% | none |
| Only if nothing has come close anywhere yet (shipped) | 50% | none |
| If the latest batch added nothing | 41% | 2 |

| Frame order | Frames read | Clips lost |
|---|---|---|
| Spread across the clip (shipped) | 50% | none |
| A different spreading method | 48% | 4 |
| Straight through from the start | 36% | 3 |

| Wave sizes | Frames read | Clips lost |
|---|---|---|
| 8, 16, 24, 40 (shipped) | 50% | none |
| 6, 12, 24, 40 | 44% | none |
| 5, 10, 20, 40 | 44% | 1 |
| 4, 8, 16, 40 | 41% | 2 |

I shipped 8/16/24/40 rather than 6/12/24/40 even though both lose nothing, because 5/10/20/40 loses one. Six sits one step from the edge and eight gives margin. **If asked whether I left speed on the table: yes, deliberately, about 6% of frames for safety.**

---

## Part 5 — Questions I expect

### About the change

**"Is it more accurate now?"** Not from this change, and that was the goal. This month was speed with identical answers. The accuracy came last month when the probe replaced the pre-scan: 7 wrong down to 1, same number of films found.

**"Did stopping early lose clips?"** No. Zero on 205. A greedier give-up rule loses 2 and I did not ship it.

**"Why not just use fewer frames?"** Tested. Thinning 40 down to 20 drops 47 right answers to 31. The rules need frames that agree on film position, and thinning destroys the agreement. Reading fewer frames *sometimes* is safe; reading fewer frames *always* is not.

**"Why 40 frames?"** Inherited and never justified, so I made it adjustable and tried 50. It found fewer, 13 against 15 on held-out clips. The frames are evenly spaced, so changing the count moves all of them rather than adding any: at 40 you look at 0.8s, 2.2s, 3.8s; at 50 at 0.6s, 1.8s, 3.0s. None of the original moments survive.

**"What happens to very short clips?"** Anything two seconds or under skips stage 1 entirely and goes to the full read. Unchanged from before.

### About the testing

**"How many tests?"** Six full runs over three independent clip sets, 612 clip measurements, plus 455 clips fingerprinted into saved evidence. Two further runs confirmed the whole-system figures and tested the 50-frame idea.

**"Where did the 15 held-out answers come from?"** 13 different films. All six rules contributed and the newer ones did most of the work: PV-E five, P1 three, P3.5 three, PV-A two, PV-B two. The old pre-scan's bar, PV-B, found only two, which suggests the rules added since then are earning their place.

**"How do you know the held-out clips are really held out?"** They were built from clips where **another** engine answered and a user confirmed the film. If PDQ had answered them they would not be in the set. So the truth comes from outside this work and none of our thresholds were fitted to any of them.

**"Why only 77 and not 100?"** 23 of the 100 posts had been deleted from the platform. They are excluded rather than counted as misses, because a dead link is not an engine failure.

### About the numbers

**"Why 38% on unseen clips but 57% on tuned ones?"** Because both sets are picked in ways that tilt the answer, in opposite directions. The tuned set was built from clips PDQ itself answered and a user confirmed, so every clip in it is one PDQ had already proved it could find. The unseen set was built from clips another engine answered, so it leans towards clips PDQ struggles with. The true number is between. Getting it properly needs clips taken at random from live traffic with films checked by hand.

**"Is 15 of 15 just luck?"** Partly. 15 answers is a small sample. What it rules out is a precision collapse, and it is backed by 37 clips whose film we do not own where it stayed silent every time. Zero wrong in 37 means the real rate is under about 8%, not that it is zero.

**"What is the one wrong answer?"** A TikTok clip answered as *Krrish 3*. One user marked it wrong, a different user marked the same clip correct. The pictures match at distance 6 out of 256, effectively identical, and 13 of the 40 correct answers are at distance 6 or closer. No threshold rejects it without rejecting those. I would call it a disputed label, not a rule failure.

**"Why does it answer fewer clips than the old system, 54 against 61?"** Because it stays silent when the evidence is thin instead of guessing. That is the same change that took wrong answers from 7 to 1.

### About risk and shipping

**"What if it misbehaves in production?"** There is an exact escape hatch. Setting `PDQ_PROBE_PROGRESSIVE=0` and `PDQ_PROBE_WAVE_ORDER=linear` reproduces the previous behaviour precisely, no redeploy of old code needed. Every other new behaviour is also behind a switch and off by default.

**"What is the memory impact?"** Keeping frames between waves costs memory, but a clip that accepts in wave 1 only ever holds 8 frames instead of 40, so in the common case it is lower than before, not higher.

**"Has this been committed?"** Not yet. That is the first thing after this meeting.

**"Could someone else reproduce this?"** Yes. The saved evidence and the replay tool are in the repo, and the replay runs in about a second.

### About scale and the pod

**"Does this hold on the real index?"** Partly, and this is the honest weak spot. We test against 134 films; the pod holds 14,653, about 71 GB. Recall here is pessimistic, because a clip whose film we do not hold can never be found. Precision here is probably optimistic, because the index is searched exhaustively and with 97 times more fingerprints the closest match to any random frame gets closer by chance. Our thresholds were tuned against 134 films. **The one wrong answer is a 134-film number, not a pod number.**

**"Does the speed-up still help at pod scale?"** It should help more, not less. Searching grows with the size of the library, and the waves cut the number of searches by the same half they cut the pictures. At our size searching is only 12% of the time; at pod size it dominates, so halving it matters more there than here.

**"So how do we find out?"** `bench_scale.py` already exists and has never been run. It rebuilds the index at increasing sizes, re-runs the clips at each one, and fails if a clip answered correctly at the small size stops being answered at the large one. The full index cannot be built on my laptop, which needs about 88 GB of memory against 15.7 GB. An 8 GB index with roughly 1,458 films is eleven times what we have and takes about two hours. I would start with 45 minutes at 2 GB to prove the pipeline and get a real build time.

**"Shouldn't we change the index structure instead?"** Probably, eventually. It is a flat index, so every search reads everything, and cost grows in a straight line with the library. That is the real scaling limit and it is bigger than anything in stage 1. The scale test is what says when it starts to hurt.

### About what is left

**"What is unfinished?"** The scale test. The time budget, which is a product call: capped at 1.5 seconds it finds 22 of 125 clips, at 2 seconds 36, at 3 seconds 43, at 5 seconds 47, which is everything it can find. And the old pre-scan function is still in the file with nothing calling it, which should be deleted before someone assumes it still runs.

**"What did you try that failed?"** Three things, all switched off with the measurement written next to the code. Running cropped pictures first in two passes: a third faster on edited clips, two and a half times slower on real ones, because the staged design never reaches a point where it can walk away. Fingerprinting at lower resolution: four times faster per picture, but it swapped a right answer for a wrong one. Sampling 50 frames: found fewer.

**"What would you do differently?"** I would have built the saved-evidence replay first instead of partway through. Once it existed, testing an idea took a second instead of forty minutes, and I would have reached the same answers in much less time.

---

## Part 6 — If I get stuck

Better than guessing:

- "I measured that, let me pull up the number." The results are in `output/` and the replay runs in about a second.
- "I did not measure that. Here is what it would take."
- "That number comes from the clips the rules were built on, so treat it as an upper bound."

**The three claims I can defend completely:** two and a half times faster on a typical clip, zero changed answers across 205 clips, and every answer correct on the 77 clips it had never seen.

**The one thing I should raise myself rather than wait to be asked:** we are testing on 0.9% of the real catalogue, and the scale test has not been run.

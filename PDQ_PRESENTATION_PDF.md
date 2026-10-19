# PDQ: what I changed, and what it did

*11 October 2026. Nada. The first stage of the system now reads half as much and gives the same answers.*

Every clip goes through three stages. **Stage 1** takes a quick look: it samples 40 moments across the clip, makes fingerprints of them, and searches our library of films. If it is confident it answers and nothing else runs. If not, **stage 2** decodes the clip properly and **stage 3** runs the full set of rules.

Everything below is in stage 1.

## 1. What I changed

### 1. It reads in waves and stops when it knows

Before, it looked at all 40 moments of every clip and only then decided anything. Now it looks at 8, decides, then 16, then 24, then 40 if it still has to.

It stops for one of two reasons. Either a rule has already fired and more frames cannot change the answer, or nothing anywhere in the clip has come close to any film, in which case more frames will not help.

### 2. The frames were re-ordered, which is what makes stopping safe

**The 40 moments never change. What changed is the order it visits them in.**

Read in plain order, the first 8 moments would all come from the opening fifth of the clip, bunched at the start. If the clip opens with a title card, you have learnt nothing.

```
in plain order:   [########--------------------------------]
                   the only 8 moments it looked at

re-ordered:       [#---#---#-------#---#---#-------#---#---]
                   1%  11% 21%    41% 51% 61%    81% 91%
```

Same 8 frames of work, the whole clip covered. And it is not tuned for 8 in particular: stop at 4, 16 or 24 and those are spread too, which matters because the probe does not know in advance how far it will go.

### 3. The clip opens once, and it remembers what it has already read

The waves are cumulative. Wave 2 is not "8 new frames", it is "the first 16", because the rules need to weigh all the evidence together.

So without any memory of what has already been done:

```
wave 1:  jump to 8 moments           8
wave 2:  jump to 16 from scratch    16
wave 3:  jump to 24 from scratch    24
wave 4:  jump to 40 from scratch    40
                                    --
                                    88 jumps
```

The old version did 40. Reading in waves would have cost 88, so stopping early would have been **slower** than what we already had.

With one piece of code holding the clip open and remembering:

```
wave 1:  8 new moments               8
wave 2:  8 new moments               8
wave 3:  8 new moments               8
wave 4:  16 new moments             16
                                    --
                                    40 jumps
```

Same 40 if it goes all the way, far fewer if it stops early. Jumping to a moment in a video file is slow, 15% of the total time, so this is the difference between the waves saving time and costing it.

Three separate parts of the code each had their own copy of this frame-reading loop, written at different times, and they had stopped agreeing with each other. They are now one piece of code.

### 4. I measured where the time goes

The system used to report one number: this clip took 12 seconds. It now reports what those seconds went on.

| Where the time goes | Share |
|---|---|
| Making fingerprints of pictures | 73% |
| Jumping to frames | 15% |
| Searching the library | 12% |

Three quarters of it is making fingerprints, so the only lever worth pulling is making fewer pictures. It also showed that searching is cheap, which is what made the waves safe to try: reading in waves means searching four times instead of once, and if searching had been the expensive part the whole idea would have made things worse.

### 5. Declined clips carry a scorecard

When stage 1 gives up it now reports how close it got: the best match, how many frames agreed, which crop shapes saw it. It sorts clips into three bands, and the bands mean something.

| Scorecard | Clips | Later identified |
|---|---|---|
| Strong | 46 | 87% |
| Medium | 22 | 32% |
| Weak | 33 | 0% |

A clip in the weak band has never once turned out to be identifiable, so this is a cheap way to decide whether to hand a clip to the audio or face engines instead of spending more time on pictures.

### 6. The frame count is adjustable

The 40 was written into the code and carried over from the old system. Nobody had ever picked it for a reason, and testing it meant editing the file, which means comparing two different programs. It is now a setting, so both runs come from the identical program.

The waves adapt on their own:

```
at 40 frames:   8 -> 16 -> 24 -> 40
at 50 frames:   8 -> 16 -> 24 -> 40 -> 50
```

The early waves stay the same size and the extra frames become a new final wave, so a clip that answers quickly still reads only 8 either way. Turning the number up costs nothing on easy clips.

**Tested, and 50 found fewer clips than 40: 13 against 15.** The moments are spread evenly, so changing how many you take moves all of them:

```
40 moments:   0.8s   2.2s   3.8s   5.2s  ...
50 moments:   0.6s   1.8s   3.0s   4.2s  ...
```

Not one of the original moments survives. It is a different 40, not 40 plus 10, so it gained 2 clips and lost 4.

### Also: four bugs fixed

A test clip that could never be built, because the zoom produced an odd pixel width that video encoders reject; the empty file had been mistaken for a failed download for weeks. A second pass working out its search window from a number that was assumed never to change. Saved results counted twice after an interrupted run. Mirrored copies of frames built and thrown away on passes that never used them.

## 2. The six rules stage 1 can fire

It tries them in this order and takes the first that fits. Distance is how different two fingerprints are, out of 256, where 0 is identical.

| Rule | What it wants | In plain terms |
|---|---|---|
| PV-A | 2 frames under distance 16, best under 12 | two almost perfect matches |
| P1 | best under 15, 3 frames under 28, 2 agreeing on film position | one excellent frame with support |
| PV-B | 3 frames under 28, best under 20, 2 agreeing | the old bar, plus agreement |
| PV-E | 2 separate groups of agreeing frames, 2 each, best under 33 | corroboration from two places |
| PV-C | 5 frames under 33, best under 26, 3 agreeing, from 2 clip moments | lots of medium evidence that lines up |
| P3.5 | only one candidate film, sliding bar by frame count | nothing else is in the running |

"Agreeing" means the frames point at a consistent position in the film. A real match gives a consistent answer; coincidences scatter. The old system never checked this, and it is the main reason the probe is more accurate than what it replaced.

Stages 2 and 3 still hold the full fourteen rules. Stage 1 is a fast front door, not a replacement.

## 3. How I tested it

| What I ran | Clips | What it was for |
|---|---|---|
| The old version | 125 | something to compare against |
| The new version | 125 | the same clips, the same conditions |
| The new version on edited clips | 80 | cropped, mirrored, sped up, greyscale, poor quality |
| Clips it had never seen before | 77 | nobody used these to build the rules |
| An idea I was testing | 125 | turned out slower, switched off |
| The same idea on edited clips | 80 | it looked good here and bad on real clips |
| **Six runs** | **612** | |

Every answer was compared one clip at a time, not as a score. Same clip, same film named, or it counts as a difference.

I also saved the full results for 455 clips, so any change to the rules can now be re-tested in about a second without touching a video again. That is how the wave sizes, the give-up rule and the frame order were chosen before the engine was changed at all.

## 4. The summary: how the measurements moved

"A typical clip" means the middle clip: half were faster, half slower.

| | Before | After | |
|---|---|---|---|
| A typical clip, quick check | 8.3 seconds | **3.2 seconds** | 2.6 times faster |
| All 125 clips, quick check | 23.3 minutes | **11.3 minutes** | 2.1 times faster |
| Pictures it fingerprints | all of them | **about half** | this causes the rest |
| Answers that changed | | **none, out of 205** | checked one clip at a time |
| Wrong answers, whole system | 7 | **1** | from last month's change |
| Right answers, whole system | 52 | 51 | unchanged in practice |
| Clips it answered, whole system | 61 | 54 | it now stays quiet when unsure |

The top four rows are this month's work: speed, with identical answers. The bottom three cover last month as well, when the probe replaced the old first stage. **That is where the accuracy came from; this month changed no answers at all.**

### Clips it had never seen

77 clips nobody used when building the rules. Another system identified them and a person confirmed the film.

| | Result |
|---|---|
| Films we own: named the right one | **15 of 40** |
| Films we own: named the wrong one | **none** |
| Films we do not own: stayed quiet | **37 of 37** |
| A typical clip | 2.9 seconds |

Every answer it gave was right. On 37 clips where any answer would have been wrong, it gave none. It finds fewer of these than of the clips the rules were built from, 38% against 57%, and both sets are picked in ways that tilt the result, so the true figure sits between them.

### Edited clips

| Edit | Identified |
|---|---|
| Mirrored, greyscale, poor quality | 8 of 8 each |
| Letterboxed | 7 of 8 |
| Sped up or slowed down | 14 of 16 |
| Zoomed in | 4 of 8 |
| Rotated | 2 of 8 |

64 of 80 overall. Rotation is the clear weak point.

### Why it only fingerprints half

It stops as soon as it knows, so different clips cost different amounts.

| What happened | Clips | Frames read |
|---|---|---|
| Nothing came close, so it stopped early | 51 | 8 of 40 |
| The film was obvious straight away | 13 | 8 of 40 |
| It needed a little more before it was sure | 25 | 16 or 24 of 40 |
| It read everything and still found nothing | 26 | all 40 |
| It read everything, then answered | 10 | all 40 |

64 of the 125 clips finish on the first 8 frames. A fifth of the work on half the clips, full price on the rest.

## 5. How I know it did not break anything

Both versions ran over the same clips and the answers were compared one at a time. No differences, on 125 real clips and 80 edited ones.

The greedier options were measured and turned down. This is the part that shows the choice was deliberate rather than lucky.

**When to give up:**

| When it gives up | Frames read | Clips lost |
|---|---|---|
| Never | 83% | none |
| Only if nothing has come close anywhere yet (shipped) | 50% | none |
| If the latest batch added nothing | 41% | 2 |

**What order to read the frames in:**

| Frame order | Frames read | Clips lost |
|---|---|---|
| Spread across the clip (shipped) | 50% | none |
| A different spreading method | 48% | 4 |
| Straight through from the start | 36% | 3 |

**How big the waves should be:**

| Wave sizes | Frames read | Clips lost |
|---|---|---|
| 8, 16, 24, 40 (shipped) | 50% | none |
| 6, 12, 24, 40 | 44% | none |
| 5, 10, 20, 40 | 44% | 1 |
| 4, 8, 16, 40 | 41% | 2 |

Twice there was more speed on offer in exchange for lost clips, and twice I turned it down. I also shipped 8/16/24/40 rather than the slightly faster 6/12/24/40, because 5/10/20/40 loses a clip and six sits one step from that edge. That is about 6% of frames given up for margin, deliberately.

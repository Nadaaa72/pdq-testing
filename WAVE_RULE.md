# The wave rule

*Answering Jude's Part 4. Written 18 October 2026.*

## Which moments each wave takes

At 80 frames, as percentages of the whole clip. Every figure below is fixed: it does not
move when the frame count changes, which is the point of the Part 3 fix.

**Wave 1 — 8 frames**
2.0, 11.6, 21.2, 40.4, 50.0, 59.6, 78.8, 88.4

**Wave 2 — 8 more, 16 in total**
6.8, 16.4, 26.0, 30.8, 45.2, 64.4, 69.2, 83.6

**Wave 3 — 8 more, 24 in total**
4.4, 23.6, 35.6, 42.8, 54.8, 74.0, 81.2, 93.2

**Wave 4 — 16 more, 40 in total**
9.2, 14.0, 18.8, 28.4, 33.2, 38.0, 47.6, 52.4, 57.2, 62.0, 66.8, 71.6, 76.4, 86.0, 90.8,
95.6

**Wave 5 — 40 more, 80 in total**
Fills every remaining gap, ending with 80 points evenly spaced 1.2% apart.

Each wave lands in the gaps the earlier ones left, which is what Jude asked for. Nobody
chose these numbers by hand: they come out of the rule that each point sits at a fixed
fraction of the clip, and the fractions are generated so that any prefix is spread over the
whole thing.

## The 2% check

Jude asked that no new point land within about 2% of one already looked at. Measured, the
closest any new point comes to an older one:

| | Closest approach |
|---|---|
| Wave 2 | 4.8% |
| Wave 3 | 2.4% |
| Wave 4 | 2.4% |
| Wave 5 | 1.2% |

**So the rule holds for the first 40 frames and breaks at the last wave.** That is not an
oversight, it is arithmetic: wave 5 doubles the count from 40 to 80, and doubling the number
of points on a clip necessarily halves the spacing. You cannot both double the sample and
keep every new point 2% clear of the old ones.

Two ways to read that. Either 40 frames is the point at which the 2% rule stops being
satisfiable and we accept 1.2% beyond it, or 40 is the natural ceiling and going further has
diminishing value. The measurement says the former: going to 80 found 5 more films on 125
clips and 6 more on 77 held-out clips, losing none, so the closer spacing is earning its
place.

I also tried enforcing 2% as a hard rule. It does not thin the tail, it caps the count: the
points sit on a halving grid, so asking for 40 under a strict 2% rule returns 33, and asking
for 80 also returns 33. It is available as a setting but it is not useful.

## What "stops at 4" means

It meant four waves: 8, 16, 24, 40. There are now five, because of the extra wave at 80.

Jude's question was whether the probe can decide partway through a wave or only once the
whole wave is in. **Only once the whole wave is in.** It takes every frame in the wave,
makes the codes, searches, and only then applies the rules.

That is deliberate. The rules work by checking whether matching frames agree about where in
the film they came from. Judging half a wave would hand them partial evidence, and a half
wave can show agreement that the full wave would have contradicted. So the probe always
judges on complete evidence, and the cost is that it cannot stop in the middle of a batch.

One practical consequence: a limit measured in seconds cannot bind tightly, because the
clock is only read between waves and the last wave is 40 frames. That was measured and the
limit was switched off.

# Trying to stop the wrong PDQ answer

*What I changed this week and what happened when I ran the clips again.*

Nada. For the meeting with Jude, 19 September 2026.

## Where I started

Last week I got as far as finding one clean wrong answer. A Facebook video came back as
*The Last Voyage of the Demeter*. The user said it was wrong and nobody had marked the same
trace as correct, so this was the one I used to start changing the engine.

The answer came from P8, which is the weakest rule. It needs 30 frames in the 35 to 45 band.
This clip had 31, so it only got over the line by one frame. The average was 41.4, which is
very close to the point where PDQ stops counting a picture as a match at all.

| What happened before | Result |
|---|---|
| Film PDQ answered with | The Last Voyage of the Demeter |
| Rule that fired | P8 |
| Frames P8 needed | 30 |
| Frames it found | 31 |
| Average Hamming | 41.4 |
| Time | 17.5 seconds |

The other thing I noticed last week was that the notes call 40 to 45 "hint only". Those
frames can point the other detectives towards a film, but they are not meant to make PDQ
answer on their own. P8 was counting them anyway, so that was the first thing I changed.

## The first change I tried

I changed P8 so only frames from 35 to 40 count towards an answer. Anything from 40 to 45
is still kept as a hint, so the information is not thrown away. It just cannot decide the
answer by itself.

I also made the frames line up at the same part of the film. Before this, 30 similar-looking
frames from anywhere in the film could add up and fire P8. Now they have to point to the same
place, within two seconds of each other.

| Before | Now |
|---|---|
| 30 frames anywhere from 35 to 45 | 30 frames from 35 to 40 |
| The frames did not have to line up | They must point to the same part of the film |
| 40 to 45 could help make the answer | 40 to 45 is for hints only |

## That did not fix it on its own

When I ran the Demeter clip again, P8 did not fire at 25.8 seconds anymore. That part worked.
But because the engine kept going, another rule fired a few seconds later.

```text
[STREAM EARLY EXIT] @ 34.5s - P6: 15 frames in 20-35

Top result:
The Last Voyage of the Demeter
84 matched frames, average Hamming 38.5
```

This time it was P6. P6 had found the 15 medium frames it needed, but the result as a whole
was still weak. Its average was 38.5 because most of the other matches were not good ones.
So I had stopped the first route to the wrong answer, but the same film was getting through
by a second route.

## The second change

I left the P6 count at 15 frames. I added a check that the average for the whole film also
has to be 35 or better.

This means 15 genuinely useful medium matches can still make P6 fire. But 15 medium matches
cannot drag through a result that is mostly made from weak look-alikes.

| What P6 now checks | What it needs |
|---|---|
| Medium frames | At least 15 from 20 to 35 |
| Average for the whole result | 35 or better |

## What happened after both changes

I ran the whole Demeter clip again with the pre-scan off. This time it did not answer with a
film. It reached the 300-frame limit and stopped with hints instead.

```text
[QUERY EXIT SUMMARY]
  exit_kind=MAX_QUERY_FRAMES
  kept_frames=300

Top results:
- 318 frames, average 38.6 - The Last Voyage of the Demeter
-  49 frames, average 39.8 - Hokum
-  28 frames, average 42.4 - Hercules

VERDICT: no film accepted. The Last Voyage of the Demeter is a hint.
```

Demeter still shows up, which is fine. The picture matches can still help audio or SSCD look
at the same film. The difference is that PDQ no longer sends Demeter back as its answer.

| | Before | After |
|---|---|---|
| Answer | The Last Voyage of the Demeter | No film accepted |
| What PDQ sends | Wrong answer | Hints only |
| Average | 41.4 when P8 fired | 38.6 at the frame limit |
| Time on my laptop | 17.5 seconds | 15 minutes 39 seconds |

## I checked the other clip as well

I ran *The In Between* again because that was the clip the pre-scan got right last week. I
wanted to make sure I had not stopped a result that should still work.

```text
[SCAN] whole-clip pre-scan HIT: 4 frames, best Hamming 18

VERDICT: The In Between
SCAN_ACCEPT; 9.5 seconds
```

It still finds the same four frames at the same part of the film and gives the same answer.
So the wrong Demeter answer has gone, and this correct one still works.

## The small checks I ran

I made five short checks for the exact parts I changed. I tested both sides, so I was not
only checking that bad evidence was blocked. I also checked that good enough evidence could
still get through.

| Check | Result |
|---|---|
| Frames from 40 to 45 cannot fire P8 on their own | PASS |
| Frames scattered through a film cannot fire P8 | PASS |
| Frames that line up can still fire P8 | PASS |
| A weak overall average stops P6 | PASS |
| A proper medium result can still fire P6 | PASS |

## What I can say from this

For the example I was working on, the change did what I wanted. The known wrong Demeter
answer is gone, and the known correct *The In Between* answer is still there. All five of
the smaller rule checks pass as well.

| Result so far | Count |
|---|---|
| Known wrong answers removed | 1 |
| Known correct examples kept | 1 |
| Small rule checks passed | 5 out of 5 |

I cannot say yet that this fixes all 39 wrong traces. I still do not have the original video
for most of them. Some links no longer download and some now point to a different upload, so
running those again would not be a fair test of the rule change.

## The downside

The wrong answer used to come back in 17.5 seconds. The safer version took 15 minutes and 39
seconds on my laptop because it kept looking until it reached the 300-frame limit.

That is too slow, but for now I would rather have no answer than a quick wrong one. The next
thing I would look at is whether weak-only results can be stopped earlier without losing a
real match.

## What I would do next

1. Get the original traced clips or the old scorecards for the rest of the wrong list.
2. Run every wrong clip I can reproduce and every correct control I can reproduce.
3. Count how many wrong answers disappear and how many right answers I lose.
4. Try to stop weak-only results earlier so this clip does not take 15 minutes.

---

I ran this locally against my 80-film index with 9,762,635 fingerprints. I did not change
anything in the live system or write anything to the production database.

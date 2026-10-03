# Every PDQ rule, explained

*A reference for the meeting. What each rule is, what it takes to fire it, and how much I
should trust it.*

Nada. September 2026. Taken from pdq_engine.py, which is verified identical to the pod.

## How to use this

I do not need to present this. It is here so that if Jude asks about a rule I have not seen
yet, I can find it in a few seconds. The quick table at the end is the one to glance at.

## The three things every rule is built from

**Distance.** How different two pictures are. Zero means identical. The lower the number, the
better the match. The engine calls it hamming distance, and it counts how many of the 256
bits of the fingerprint differ.

**The bands.** Every matching frame gets sorted into a band by its distance.

| band | distance | what it means |
|---|---|---|
| Strong | 0 to 20 | the same picture |
| Medium | 21 to 35 | probably the same picture, maybe filtered or cropped |
| Weak | 36 to 44 | might be the same picture, might be a look-alike |
| Ignored | 45 and up | not a match, thrown away |

**The two kinds of bucket.** These are the checks that separate a real match from a
coincidence, and they answer two different questions.

*Film-time buckets* ask: do the matched frames line up in one place in the film? A real match
does. If I send twenty seconds of a film, the frames land in a twenty second stretch of that
film, in order. A look-alike scatters, a few here and a few there.

*Clip-time buckets* ask: did the matches come from more than one moment of my clip? A real
match does. A single frozen frame that happens to look like a film poster only ever produces
matches from one second of the clip.

A true match says yes to both. A wrong answer usually says no to at least one.

## The order things happen in

This matters, because an earlier step can answer before a later one gets a look in.

1. **The pre-scan** skims the whole clip first. If it is confident, it answers and nothing
   else runs.
2. **The probe** takes a quick look at the start of the clip. It can accept on rule P0, or
   trigger an early reject.
3. **The streaming rules** watch the clip go past and stop as soon as one of them fires.
   These are P1 through P8, plus P1.5 and P3.5.
4. **The end-of-clip rules** only run if the clip finished with nothing fired. These are P9E
   and P9.
5. If nothing fires at all, PDQ does not answer. It publishes hints instead, and the other
   detectives take over.

---

# Before the rules

## The pre-scan

Samples 40 frames spread evenly across the whole clip, rather than working through it in
order. A sampled frame counts as a hit on a film if its closest match is under 28.

It accepts a film when **at least 3 sampled frames hit it, and the best of those hits is
under 20**.

*In plain words:* a quick skim of the whole clip. It is looking for a few frames that are
clearly the same picture, from anywhere in the clip.

*Why it matters to me:* it is not a rule, it runs before the rules and short-circuits them.
This is why the notes say to replay with it turned off. It answered my In Between clip on 4
frames at distance 18, and when I turned it off the same clip was rejected entirely.

## P0, the probe

Runs after 0.75 seconds of clip, once it holds 15 fingerprints, and no later than 4 seconds
in. It keeps at most 64 fingerprints and takes them from one crop family only.

It accepts when **one single neighbour is under 30**.

*In plain words:* one decent frame near the start of the clip is enough.

*How much evidence:* one frame. This is the thinnest rule in the whole system. The notes list
it as a known cause of wrong answers, because one look-alike frame will do it.

## Early reject

Two ways the engine gives up and says the clip is not in the library.

After **64 fingerprints**, if the best distance seen anywhere is worse than **47**, stop.

After **96 fingerprints**, if the evidence score is under 4 and the best distance is worse
than 35, stop. The evidence score is three points per strong frame, two per medium, one per
weak.

*Why it matters to me:* this is what killed my In Between clip when I turned the pre-scan
off. It gave up after 1.6 seconds on a film that was genuinely in the index.

---

# The streaming rules

These are checked in the order below and the first one to fire wins. The rules at the top
need very little evidence because the evidence is very strong. The ones at the bottom need a
lot because each piece is weak.

## P1

**Fires when:** one frame is under distance 15, and there are at least 3 matched frames in
total.

*In plain words:* one near-perfect frame, plus two others to show it was not a fluke.

*Trust:* high. This is the most common exit on the pod by a long way.

## P2

**Fires when:** one frame is at distance 5 or under.

*In plain words:* one frame is practically identical. Nothing else needed.

*Trust:* high, but it is one frame, so a genuine look-alike would do it.

## P2.5

**Fires when:** one frame is at 8 or under, and there are at least 2 frames at 8 or under.

*In plain words:* two separate near-perfect frames.

*Trust:* high. Two independent frames is much harder to get by accident than one.

## P3

**Fires when:** at least 10 frames land in the strong band.

*In plain words:* lots of frames that are clearly the same picture.

*Trust:* high. This is the normal exit for a clean clip.

## P4

**Fires when:** at least 5 strong frames, all landing within one 2 second stretch of the
film, and coming from at least 2 moments of the clip that are 3 or more seconds apart.

*In plain words:* fewer strong frames than P3, but they line up in one spot in the film and
they came from different parts of the clip. Both checks at once.

*Trust:* high. P4 is the rule that does the most checking, and it is worth noting when I look
at P8, which does none of it.

## P5x

**Fires when:** the P4 cluster holds 8 or more strong frames, and one medium film-time bucket
holds 6 or more.

*In plain words:* the strong evidence and the medium evidence agree about where in the film
this came from.

*Trust:* high. Two kinds of evidence pointing at the same moment.

## P5

**Fires when:** at least 5 strong frames land in one 2 second stretch of the film, but
without the clip-spread check that P4 does.

*In plain words:* same as P4 but the frames might all come from one moment of the clip.

*Trust:* held back on purpose. P5 is marked pending. The engine carries on for 3 more seconds
of clip and only uses P5 if nothing better turns up.

## P6

**Fires when:** at least 15 frames land in the medium band.

*In plain words:* a lot of frames that are probably the same picture, maybe with a filter or
a crop over them.

*Trust:* medium. It is a lot of frames, but none of them are strong, and it does no
clustering check at all.

## P6a

**Fires when:** at least 10 frames land between 20 and 25, they line up within one 2 second
stretch of the film, and the best single bucket holds 10 of them.

*In plain words:* frames at the better end of medium, all pointing at the same moment.

*Trust:* medium to good. Weaker frames than P3, but the clustering check makes up for it.

## P7

**Fires when:** medium frames line up within 2 seconds of film time, and at least 3 seconds
of the clip produced matches, with at least 2 of those seconds being solid. Solid means 4
matches if there are exactly 3 such seconds, or 2 matches if there are more. Only applies
when the average is 25 or better.

*In plain words:* medium frames coming from several different moments of the clip, all
pointing at the same moment of the film.

*Trust:* medium. It checks both kinds of bucket, which is in its favour.

## P7-strict

**Fires when:** the average is worse than 25, and more than 3 clip seconds each have 4 or
more medium matches.

*In plain words:* it does not fire. That would need 16 medium frames, and P6 fires at 15
first, so P6 always gets there before it. The notes call it a dead rule.

## P7-strict-burst

**Fires when:** the average is worse than 25, and one single second of the clip has 7 or more
medium matches.

*In plain words:* a burst of matches from one moment of the clip, at a poor average.

*Trust:* low. Everything coming from one moment of the clip is exactly the pattern the notes
warn about.

## P8

**Fires when:** at least 30 frames land in the weak band.

*In plain words:* a large pile of matches, every one of them poor.

*Trust:* lowest of all. The notes say P8 is the rule most often behind a wrong answer.

**This is the rule from my Demeter clip.** It counts frames and nothing else. It does not
check whether they cluster in one part of the film, and it does not check whether they came
from more than one moment of the clip. P4 does both of those checks on much better evidence.

## P1.5

**Fires when:** after 5 seconds of clip, one film has 30 or more matched frames at an average
under 18, and at least 3 times as many frames as the runner-up.

*In plain words:* one film is miles ahead of everything else.

*Trust:* high. It is a lot of good frames and a big gap to second place.

## P3.5

**Fires when:** only one film in the entire index has matched anything at all, and it clears
one of these bars:

| average distance | frames needed |
|---|---|
| 20 or under | 4 |
| 30 or under | 7 |
| 35 or under | 12 |
| 45 or under | 20 |

*In plain words:* nothing else is in the running, so the bar drops.

*Trust:* be careful. On the pod with nine and a half thousand films this almost never happens,
because some film always picks up a stray frame. On my index of eighty films it can happen
easily. If I see P3.5 in my results I should treat it as an artefact of my small index rather
than a finding.

---

# The end-of-clip rules

These only run if the clip finished and nothing above fired.

## P9E

**Fires when:** only one film matched anything at all in the whole clip, its average is 35 or
better, and it has at least 2 frames.

*In plain words:* nothing else in sight, and what we have is decent.

*Trust:* medium. Same warning as P3.5 about small indexes.

## P9

**Fires when:** only one film matched anything, its average is in the weak band, and it has
enough weak frames. How many depends on how bad the average is.

| average | frames needed |
|---|---|
| 42 or under | 4 |
| 44 or under | 8 |
| worse than 44 | 12 |

There is a second form of P9 as well: any film with matches from 3 or more different seconds
of the clip in the weak band, as long as it also has something in the strong or medium band.

*In plain words:* nothing else in sight, but the evidence is poor, so the closer it gets to
the 45 cut-off the more frames it has to show.

*Trust:* low. This is the sliding scale I would expect P8 to have and it does not.

---

# The wait before a weak answer is sent

A weak-band answer does not go straight out. The orchestrator holds it so the audio detective
or SSCD can object. How long depends on which rule fired.

| rule | wait |
|---|---|
| P9E | 5 seconds |
| P9 | 8 seconds |
| P8 | 12 seconds |
| anything else out of the weak band | 15 seconds |

Strong-band exits do not wait at all.

On my Demeter clip the pod would have held the answer 12 seconds. Nothing objected, so it
went out and the user pressed wrong.

---

# Quick table

Rules are checked top to bottom and the first to fire wins.

| rule | needs | band | trust |
|---|---|---|---|
| pre-scan | 3 sampled frames under 28, best under 20 | strong | runs first, skips everything |
| P0 probe | 1 frame under 30 | any | one frame only |
| P1 | 1 frame under 15, plus 3 frames total | strong | high |
| P2 | 1 frame at 5 or under | strong | high |
| P2.5 | 2 frames at 8 or under | strong | high |
| P3 | 10 frames in 0-20 | strong | high |
| P4 | 5 strong, clustered in film, from 2 clip moments | strong | highest, checks both |
| P5x | 8 strong clustered, plus a medium bucket of 6 | strong | high |
| P5 | 5 strong clustered, no clip spread | strong | pending, waits 3s |
| P6 | 15 frames in 20-35 | medium | medium |
| P6a | 10 frames in 20-25, clustered | medium | medium to good |
| P7 | medium frames clustered, from 3 clip seconds | medium | medium |
| P7-strict | never fires, P6 beats it | medium | dead rule |
| P7-strict-burst | 7 medium matches in one clip second | medium | low |
| P8 | 30 frames in 35-45 | weak | lowest |
| P1.5 | 30 frames under 18, triple the runner-up | strong | high |
| P3.5 | sole candidate, sliding bar | any | suspect on a small index |
| P9E | end of clip, sole film, avg 35 or better | medium | medium |
| P9 | end of clip, sole film, weak, sliding bar | weak | low |
| reject | best worse than 47 after 64 frames | none | gives up |

## Which rules fire most

These counts come from the rules check that ships with the folder. It runs the engine over
thousands of generated searches, so it is not live traffic, but it shows which rules do the
work.

| rule | times fired |
|---|---|
| P1 | 10,130 |
| P6 | 8,564 |
| P3 | 2,954 |
| P8 | 2,183 |
| P9E | 1,149 |
| P4 | 1,108 |
| P6a | 749 |
| P9 | 219 |
| P7-strict-burst | 140 |
| P5 | 23 |
| P2 | 12 |
| P5x | 4 |
| P2.5 | 1 |
| P7 | 1 |

P1 and P6 do most of the work. P8 is fourth, which is a lot of answers coming out of the
weakest rule in the system.

---

# What I would say about all this if asked

The rules at the top of the list need almost no evidence, because what they have is
excellent. One frame at distance 5 really is the same picture. The rules at the bottom need
piles of evidence because each piece of it is nearly worthless.

The interesting gap is that the careful rules are in the middle. P4 checks that the frames
cluster in one part of the film and that they came from different moments of the clip, and it
does that on strong evidence that barely needs checking. P8 does neither check, on the worst
evidence in the system. That is back to front, and it is where I would look first.

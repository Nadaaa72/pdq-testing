# The clips PDQ got wrong

*Where I have got to, what stopped me, and what I found in the clips I could run.*

Nada. For the meeting with Jude, 13 September 2026.

## What I was asked to do

PDQ is the part of Trace that works out which film a clip came from by comparing pictures.
Sometimes it gives the wrong film and the user presses "wrong". My job is to go through
those clips, work out why it got confused, and change a rule so it stops.

The hard part is not removing the wrong answers. I could do that by making every rule
stricter. The problem is that the same change would stop the engine recognising films it
currently gets right. So I have to count two things after every change: how many wrong
answers went away, and how many right answers I broke. That is why there is a second list
of clips that users confirmed were correct. It is there to catch me breaking things.

## Setting it up

I ran the two checks that come with the folder before doing anything else.

| check | result |
|---|---|
| My rules match the pod's rules | PASS. 31,715 searches compared, no differences. |
| My fingerprints match the pod's | PASS. Frames, crops and fingerprints byte for byte. |

I wanted these passing first. Without them, if my results changed later I would not know
whether it was the rule I changed or just my laptop behaving differently.

Then I pulled the two lists out of the database and built an index with every film named in
either of them.

| | |
|---|---|
| Clips PDQ got wrong | 39 |
| Clips users confirmed (the control) | 39 |
| Films in my index | 80 |
| Fingerprints | 9,762,635 |
| Index on disk | 0.46 GB |

## Where I got stuck

To look at a wrong answer I have to replay the clip, and to replay it I have to download the
video from the link the user sent. Most of them would not download.

| | clips |
|---|---|
| On the wrong list | 39 |
| Downloaded | 20 |
| Matched any film | 3 |
| Gave back the same answer the pod gave | 2 |

Nineteen would not download at all. All 15 TikTok links failed, because the download tool
cannot get past TikTok at the moment. Four Instagram links wanted a login.

Of the 20 that did download, 17 now match nothing at all. Not a weak match or a borderline
one. Nothing. I ran all of them a second time with the pre-scan switched off in case the
first quick look was giving up too early, and it changed nothing for any of them.

I think the videos at those links are not the videos that were traced. They are social
posts, so they get edited, deleted and re-uploaded.

I also checked whether I could get the answer without the video. I cannot. The database
keeps the film that was answered, but not the scorecard and not which rule fired.

That left me two clips.

## Clip 1: The In Between

This clip was traced three times. Two users said the answer was right and one said it was
wrong, so it is not a clean example. I ran it anyway.

### Run 1, normally

```
index: C:\Users\nadaa\pdq_for_nada\data\index  (80 films, 9,762,635 fingerprints, opened in 0.01s, memory-mapped)
clip:  data\clips\www_facebook_com_share_r_14woyxuzQk7_.mp4

[ORCH][PDQ] starting query...
[ORCH][PDQ] Index ready: 1 shard(s)   (80 films, 9,762,635 fingerprints, groups searched: ['FULL', 'PORTRAIT', 'SQUARE'])
[SCAN] whole-clip pre-scan HIT in 9.4s: vidx=10 frames=4 min_hamming=18 -> early accept (skipped full pass-1)

============================================================
[QUERY EXIT SUMMARY]
  exit_kind=SCAN_ACCEPT
  reached_end=True
  reason=whole-clip pre-scan HIT
  progress=30.03s / 30.03s
  decoded_frames=0 kept_frames=0 hashes=0
============================================================

Query time: 9.63s
Top candidates:
- matched=  4  avg_hamming= 18.0  offset=    5.0s  movie=83904:The In Between (tmdb=818750)

HINTS (1 movies with avg_hamming < 45):
  1. 83904:The In Between (tmdb=818750)
     range=0-20  frames=4  avg_hamming=18.0

[EARLY EXIT] SCAN: whole-clip pre-scan min_hamming=18 frames=4

[ORCH] PDQ early accept -> movie_id=10 (SCAN: whole-clip pre-scan min_hamming=18 frames=4)

------------------------------------------------------------
VERDICT: 83904:The In Between (tmdb=818750)
         rule: SCAN: whole-clip pre-scan min_hamming=18 frames=4
         SCAN_ACCEPT; 9.6s
```

The pre-scan answered it. Four frames matched, the best of them 18 away, all pointing at
the 5 second mark of the film. Anything under 20 counts as the same picture, so those four
frames were good ones. The pre-scan needs three frames and a best distance under 20. It had
four frames at 18.

### Run 2, with the pre-scan turned off

```
index: C:\Users\nadaa\pdq_for_nada\data\index  (80 films, 9,762,635 fingerprints, opened in 0.00s, memory-mapped)
clip:  data\clips\www_facebook_com_share_r_14woyxuzQk7_.mp4

[ORCH][PDQ] starting query...
[ORCH][PDQ] Index ready: 1 shard(s)   (80 films, 9,762,635 fingerprints, groups searched: ['FULL', 'PORTRAIT', 'SQUARE'])
[PROBE] likely_match=False min_neighbor_hamming=66 closest_movie=224974:The Misfits (tmdb=581644) closest_group=PORTRAIT hashes=16 elapsed=1.12s
[REJECT] best_hamming=66>47 after 64 hashes -> no match, early reject

============================================================
[QUERY EXIT SUMMARY]
  exit_kind=NO_MATCH_REJECT
  reached_end=False
  reason=best_hamming=66>47 after 64 hashes -> no match, early reject
  progress=1.62s / 30.03s
  decoded_frames=15 kept_frames=8 hashes=64
============================================================

Query time: 3.13s

No candidates found under max_hamming (<45).
[CLOSEST-ANY TOP] None (index search returned nothing?)


------------------------------------------------------------
VERDICT: no film accepted, no hints. This clip is not in your index.
         NO_MATCH_REJECT; 3.1s
```

Same video, same index, opposite answer. With the pre-scan the film is found. Without it the
clip is thrown out as not being in the library.

The reason is where each one looks. The pre-scan skims the whole 30 seconds and finds the
part that matches. The probe takes a handful of frames from the start, lands nowhere near
the matching moment, sees a best distance of 66, and gives up after 1.6 seconds.

So this clip is only ever found by the pre-scan. If the pre-scan had missed it, the film was
in the index the whole time and the engine would still have said no.

## Clip 2: The Last Voyage of the Demeter

This is the clean one. One user pressed wrong and nobody disagreed.

### Run 3, normally

```
index: C:\Users\nadaa\pdq_for_nada\data\index  (80 films, 9,762,635 fingerprints, opened in 0.01s, memory-mapped)
clip:  data\clips\www_facebook_com_share_v_1Hao6fkTco_.mp4

[ORCH][PDQ] starting query...
[ORCH][PDQ] Index ready: 1 shard(s)   (80 films, 9,762,635 fingerprints, groups searched: ['FULL', 'PORTRAIT', 'SQUARE'])
[SCAN] no early-accept -> running full pass-1 (cropped)
[PROBE] likely_match=False min_neighbor_hamming=76 closest_movie=218386:Armour of God (tmdb=10974) closest_group=PORTRAIT hashes=16 elapsed=1.12s
[STREAM EARLY EXIT] @ q_ts=25.8s - P8: 31 frames in 35-45 (>=30)

============================================================
[QUERY EXIT SUMMARY]
  exit_kind=EARLY_ACCEPT
  reached_end=False
  reason=P8: 31 frames in 35-45 (>=30)
  progress=25.75s / 2117.43s
  decoded_frames=207 kept_frames=75 hashes=565
============================================================

Query time: 17.46s
Top candidates:
- matched= 31  avg_hamming= 41.4  offset= 4931.0s  movie=73032:The Last Voyage of the Demeter (tmdb=635910)
- matched=  1  avg_hamming= 44.0  offset= 4207.0s  movie=9495:Hercules (tmdb=184315)

HINTS (2 movies with avg_hamming < 45):
  1. 73032:The Last Voyage of the Demeter (tmdb=635910)
     range=35-45  frames=31  avg_hamming=41.4
  2. 9495:Hercules (tmdb=184315)
     range=35-45  frames=1  avg_hamming=44.0

[EARLY EXIT] P8: 31 frames in 35-45 (>=30)

[ORCH] PDQ early accept -> movie_id=22 (P8: 31 frames in 35-45 (>=30))
[ORCH] this exit is from the weak band: the pod would wait 12s for audio or SSCD to disagree before sending it

------------------------------------------------------------
VERDICT: 73032:The Last Voyage of the Demeter (tmdb=635910)
         rule: P8: 31 frames in 35-45 (>=30)
         weak band: the pod would hold this answer 12s for audio or SSCD to object
         EARLY_ACCEPT; 17.5s
```

The rule that fired is P8, which is the weakest rule in the list. The PDQ notes say it is
the one most often behind a wrong answer, so it is not a surprise to find it here.

P8 fires when 30 frames land in the weak band. It found 31. That is one frame over the line.

The distances tell the same story. Lower numbers mean a closer match, and anything over 45
is thrown away as meaningless. These 31 frames averaged 41.4, so the whole answer was built
out of matches that were nearly bad enough to be ignored.

| band | distance | what it means |
|---|---|---|
| Strong | 0 to 20 | the same picture |
| Medium | 20 to 35 | probably the same picture |
| Weak | 35 to 45 | might be the same, might be a look-alike |
| Ignored | over 45 | not a match |

There was nothing in the strong or medium bands at all. The only other film in the running
was Hercules with a single frame.

### Run 4, with the pre-scan turned off

```
index: C:\Users\nadaa\pdq_for_nada\data\index  (80 films, 9,762,635 fingerprints, opened in 0.00s, memory-mapped)
clip:  data\clips\www_facebook_com_share_v_1Hao6fkTco_.mp4

[ORCH][PDQ] starting query...
[ORCH][PDQ] Index ready: 1 shard(s)   (80 films, 9,762,635 fingerprints, groups searched: ['FULL', 'PORTRAIT', 'SQUARE'])
[PROBE] likely_match=False min_neighbor_hamming=76 closest_movie=218386:Armour of God (tmdb=10974) closest_group=PORTRAIT hashes=16 elapsed=1.12s
[STREAM EARLY EXIT] @ q_ts=25.8s - P8: 31 frames in 35-45 (>=30)

============================================================
[QUERY EXIT SUMMARY]
  exit_kind=EARLY_ACCEPT
  reached_end=False
  reason=P8: 31 frames in 35-45 (>=30)
  progress=25.75s / 2117.43s
  decoded_frames=207 kept_frames=75 hashes=565
============================================================

Query time: 6.93s
Top candidates:
- matched= 31  avg_hamming= 41.4  offset= 4931.0s  movie=73032:The Last Voyage of the Demeter (tmdb=635910)
- matched=  1  avg_hamming= 44.0  offset= 4207.0s  movie=9495:Hercules (tmdb=184315)

HINTS (2 movies with avg_hamming < 45):
  1. 73032:The Last Voyage of the Demeter (tmdb=635910)
     range=35-45  frames=31  avg_hamming=41.4
  2. 9495:Hercules (tmdb=184315)
     range=35-45  frames=1  avg_hamming=44.0

[EARLY EXIT] P8: 31 frames in 35-45 (>=30)

[ORCH] PDQ early accept -> movie_id=22 (P8: 31 frames in 35-45 (>=30))
[ORCH] this exit is from the weak band: the pod would wait 12s for audio or SSCD to disagree before sending it

------------------------------------------------------------
VERDICT: 73032:The Last Voyage of the Demeter (tmdb=635910)
         rule: P8: 31 frames in 35-45 (>=30)
         weak band: the pod would hold this answer 12s for audio or SSCD to object
         EARLY_ACCEPT; 17.5s
```

Same result. The pre-scan was not involved in this one anyway, so turning it off changed
nothing except the time it took. P8 was always the rule deciding this clip.

## What I noticed

Both clips were answered on the smallest amount of evidence the rule would take.

The Demeter clip needed 30 frames in the weak band and had 31. The In Between clip needed
three frames under 20 and had four. In both cases, one frame fewer and neither would have
answered at all.

Two clips does not prove anything. But that is the shape the PDQ notes describe for a wrong
answer, and it tells me what to look at first when I have more clips to go through.

## The bit I could not work out

The PDQ notes say that since 6 August 2026 the top of the weak band, 40 to 45, is hint only.
Frames in that range are meant to be able to point the other detectives at a film, but never
to make PDQ answer on its own.

The Demeter clip was answered by P8 on 31 frames averaging 41.4, which is inside that range.
When I read the engine, P8 counts every frame from 36 up to the 45 cut-off and does nothing
special with the 40 to 45 part.

I cannot tell from my copy whether that rule is applied somewhere else in the live system or
whether P8 skips it. If it does apply to P8, this wrong answer probably would not have
happened, which would make it worth looking at.

## What I need

I am ready to start on the engine. What I do not have is clips. Two is not enough to find a
pattern, and it is nowhere near enough to measure whether a change helps or hurts.

1. Does the pod keep a copy of the clips it traces? There is a clip_hash column in the table, so each clip was hashed at some point and the files might be stored somewhere. That would solve this outright. The hash would also tell me whether a video I download today is the same one that was traced.
2. How does the pod download from TikTok? My folder cannot, and that is 15 of my 39 clips.
3. Are the pod's [EARLY EXIT] log lines kept for old clips? The rule that fired only exists in the log. If those are still around I could read the rule for all 39 without replaying anything.

## What I will do once I have them

- Replay every wrong clip, twice each, with and without the pre-scan, and write down the rule and the scorecard.
- Work out what the wrong ones have in common.
- Change one number in the engine.
- Replay both lists and report the two counts: wrong answers removed, and right answers lost.

---

All of this was run on my laptop against a copy of the engine that is verified identical to
the live one. Nothing live was changed. The database was read only.

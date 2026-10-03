# PDQ, explained from the start

*For Nada. Written 4 Sep 2026 from the code that runs on the pod today. Every number in here is the real number the code uses.*

## 1. What PDQ does

PDQ turns a picture into a fingerprint. The fingerprint is 256 ones and zeros. Two pictures that look alike get fingerprints that are almost the same. Two pictures that look different get fingerprints that are very different.

To compare two fingerprints, you count the places where they differ. That count is called the **Hamming distance**. It goes from 0 (identical) to 256 (nothing in common). A Hamming distance of 10 means "these are the same picture". A distance of 120 means "these are different pictures".

Trace keeps a fingerprint for many frames of every film. About 95,000 fingerprints per film. When a clip arrives, Trace fingerprints the clip's frames too, and searches for the closest film fingerprints. If a lot of the clip's frames land close to frames of one film, that film is the answer.

That is the whole idea. Everything else in this document is about the word "a lot".

## 2. How a clip is turned into fingerprints

The pod does these steps, in this order, for every clip. The numbers are the real settings.

1. Pull frames from the clip at 8 frames per second.
2. Keep a frame only if it changed enough from the last kept frame. So a frozen shot does not give 50 copies of the same fingerprint.
3. Shrink each kept frame so its longest side is 640 pixels.
4. Cut each frame eight ways: square, 4:5, 9:16 and 16:9, at full size and at 85% size. TikTok creators crop films in these shapes, so the clip is compared in all of them.
5. Fingerprint each cut. Keep a fingerprint only if its quality score is 40 or more. Blank frames, fades and black screens have low quality and are thrown away.
6. Look at the clip's shape. Tall clips are searched in the film fingerprints that were made from tall crops. Wide clips in the wide ones. Square in the square ones. These are called **crop groups**: PORTRAIT, LANDSCAPE, SQUARE, and FULL (the whole frame).
7. For each clip fingerprint, ask the search file for the 64 closest film fingerprints.
8. Keep only the ones with Hamming distance 45 or less. Everything further away is ignored.

A 20-second clip gives roughly 100 to 300 fingerprints. Each one gets its 64 closest neighbours. That is the raw material. The rest is counting.

## 3. The three bands

Every matching frame is put in a band by its Hamming distance.

| band | Hamming distance | what it means |
|---|---|---|
| 0-20 | 0 to 20 | Very strong. The same picture. |
| 20-35 | 21 to 35 | Medium. Probably the same picture, maybe with a filter or a crop. |
| 35-45 | 36 to 45 | Weak. Might be the same picture. Might be a look-alike. |
| above 45 | 46 and up | Ignored. Not a match. |

Since 6 Aug 2026 the top of the weak band, 40 to 45, is **hint only**. Frames there can point the other detectives at a film. They can never make PDQ answer on their own.

## 4. What is counted, per film

While the clip is being processed, Trace keeps a small scorecard for every film that has had at least one matching frame. The scorecard holds:

| what is counted | plain meaning |
|---|---|
| matched frames | How many of the clip's frames matched this film at 45 or under. |
| min hamming | The single best match. The lowest distance seen. |
| avg hamming | The average distance over all the matched frames. |
| frames in 0-20 | How many matched frames were in the strong band. |
| frames in 20-35 | How many in the medium band. |
| frames in 35-45 | How many in the weak band. |
| offset | Where in the film the matches landed. In seconds. |

These are the numbers you see in the printout. `matched= 14  avg_hamming= 11.6  offset= 4212.0s` means fourteen matched frames, average distance eleven and a bit, and the clip lines up with the film about 70 minutes in.

## 5. Buckets

"Bucket" comes up in the rules. There are two kinds, and they answer two different questions.

**Film-time buckets.** Every matched frame says "I am at second X of the film". Trace rounds X to the nearest second and counts how many matched frames landed in each second. Those seconds are the film-time buckets. A real match lines up: if the clip is 20 seconds of a film, its matched frames land in a 20-second stretch of the film, in order. A look-alike does not line up: its matched frames scatter across the film, a few here and a few there. Rule P4 checks this with a "cluster": all the strong frames must land within one 2-second stretch of the film.

**Clip-time buckets.** Every matched frame also came from a second of the clip. Trace counts how many matched frames each second of the clip produced. A real match comes from many different seconds of the clip. A single frozen frame that happens to look like a film poster produces matches from one second only. Rules P7 and P9 count how many clip seconds produced matches. "Spread over 3 seconds" means the matches came from clip seconds at least 3 seconds apart.

So the two questions are: do the matches line up in the film (film-time buckets), and do they come from more than one moment of the clip (clip-time buckets)? A true match says yes to both. A false positive usually says no to at least one.

## 6. The early exit rules

PDQ does not wait for the whole clip. After every few new fingerprints it checks every film's scorecard against the rules below, in this order. The first rule that is true for some film fires. PDQ stops decoding and hands that film to the orchestrator, the part of Trace that runs all four detectives together.

### Before the rules: two quick looks

Two checks run before the frame-by-frame rules. They are fast, and they catch most clean clips.

| check | it fires when | in plain words |
|---|---|---|
| Pre-scan | 40 frames spread over the whole clip are hashed. One film gets at least 3 of them under hamming 28, and its best is under 20. | A quick look at the whole clip. Three good frames on one film, and PDQ stops here. |
| P0, the probe | After 0.75 seconds of clip and 15 fingerprints of one crop family, they are searched once. The best neighbour is under 30. | One frame under 30 is enough. This is the loosest rule in PDQ. |

The pre-scan prints `[SCAN] whole-clip pre-scan HIT`. The probe prints `[PROBE] P0 triggered`.

### The rules, in order

| rule | it fires when | in plain words |
|---|---|---|
| P1 | min hamming under 15, and at least 3 matched frames | One near-perfect frame plus two more. |
| P1.5 | after 5 seconds of clip, one film has 30 or more frames at avg under 18, and 3 times the runner-up | One film is far ahead of everyone. |
| P2 | min hamming 5 or under | One frame is practically identical. |
| P2.5 | min hamming 8 or under, and at least 2 frames at 8 or under | Two independent near-perfect frames. |
| P3 | at least 10 frames in 0-20 | Many strong frames. The most common exit for a clean clip. |
| P3.5 | only one film has any frames at all, and it has 4 frames at avg 20 or under, or 7 at 30, or 12 at 35, or 20 at 45 | Nothing else in sight, so the bar is lower. Rare on the pod with 9,500 films. Common on a small index. |
| P4 | at least 5 frames in 0-20, all within one 2-second stretch of the film, from clip seconds at least 3 apart | Fewer strong frames, but they line up in the film and come from different moments of the clip. |
| P5x | the P4 cluster has 8 or more frames, and one 20-35 film-time bucket has 6 or more | Strong and medium evidence agree on where in the film. |
| P5 | at least 5 frames in 0-20 in one film-time cluster, without the clip-spread check | Same as P4 but marked "pending". PDQ keeps going for 3 more seconds of clip and only uses it if nothing better comes. |
| P6 | at least 15 frames in 20-35 | Many medium frames. |
| P6a | at least 10 frames in 20-25, all in one 2-second stretch of the film, 10 in the best bucket | Medium-good frames that line up in the film. |
| P7 | in 20-35, offsets within 2 seconds, and at least 3 clip seconds with matches, 2 of them with enough (4 each if exactly 3 clip seconds, else 2 each). Only when avg is 25 or under. | Medium frames from different moments of the clip. |
| P7-strict-burst | avg over 25, and one clip second has 7 or more matches in 20-35 | A burst of medium frames from one moment, at a worse average. |
| P7-strict | avg over 25, and more than 3 clip seconds with 4 or more matches each | Never fires. That needs 16 frames in 20-35, and P6 fires at 15 first. A dead rule. |
| P8 | at least 30 frames in 35-45 | Many weak frames. The weakest rule. |
| P9E | at the end of the clip: only one film has any matched frames at all, with avg hamming 35 or under and at least 2 frames | Nothing else in sight, and it is decent. |
| P9 | at the end of the clip: only one film, avg in 35-45, with enough weak frames: 4 if avg is 42 or under, 8 if 44 or under, else 12 | Nothing else in sight, but weak. The closer to 45, the more frames it needs. |

The rules at the top need very little evidence because the evidence is very strong. The rules at the bottom need a lot of evidence because each piece is weak.

The printout shows which rule fired and why, in one line:

```
[STREAM EARLY EXIT] @ q_ts=2.5s — P3: 14 frames in 0-20 (≥10)
[EARLY EXIT] P3: 14 frames in 0-20 (≥10)
```

### Giving up early

PDQ also stops when the clip is clearly not in the library. After 64 fingerprints, if the best neighbour seen is worse than 47, it stops with no answer. After 96 fingerprints, if no film has real evidence (fewer than 4 points, where a strong frame is 3 points, a medium one 2, a weak one 1) and the best hamming is over 35, it stops too. The printout says `[REJECT]`.

## 7. What happens after an early exit

PDQ hands the film and the reason to the orchestrator. The orchestrator does not always take it straight away.

- If the audio detective has already found a strong answer, audio wins and PDQ's answer is set aside. Audio is rarely wrong when it is strong.
- If the face detective has a ranking, PDQ's film is checked against it. Agreement makes the answer stronger.
- If the exit came from the weak band (35-45), the orchestrator **waits** before accepting it. The wait gives the audio and SSCD detectives time to disagree. How long depends on the rule: P9E waits 5 seconds, P9 waits 8, P8 waits 12, anything else from 35-45 waits 15. Strong-band exits do not wait.
- Then the answer goes to the phone, and the other detectives are told to stop.

The printout line for that moment:

```
[ORCH] PDQ early accept → movie_id=3112 (P3: 14 frames in 0-20 (≥10))
```

## 8. When no rule fires: hints

Often the clip finishes and no rule fired. PDQ then does not answer. It publishes its scorecards as **hints**: every film with an average distance under 45, with its band, its matched frames and its average. The printout looks like this:

```
HINTS (3 movies with avg_hamming < 45):
  1. 2207:The Dark Knight (tmdb=155)
     range=35-45  frames=7  avg_hamming=39.2
  2. 5530:Batman Begins (tmdb=272)
     range=35-45  frames=5  avg_hamming=41.8
```

Hints are not answers. They are given to the other detectives. The audio detective can use a hint to break a tie. Gemini is told the hinted names. And the consensus rule below reads them.

## 9. Consensus

SSCD is the other picture detective. It uses a neural network, so it survives crops and filters that break PDQ. It gives each film a number of votes.

The **consensus rule** says: if SSCD's winning film is also PDQ's answer, or is in PDQ's hints, and SSCD gave it at least 4 votes, then the two picture detectives agree, and that film is very likely right. Two different methods landing on the same film is strong evidence, even when each one alone was weak.

Today the rule runs in **shadow**. It prints what it would do but does not decide, unless the switch `PDQ_SSCD_CONSENSUS` is turned on. The printout line:

```
[ORCH][CONSENSUS-SHADOW] PDQ+SSCD agree id=3112 ('Interstellar') via=hints pdq_ham=38.1 sscd_votes=6 | has_winner=False would=fire(no-winner)
```

Read it as: PDQ had Interstellar in its hints at average distance 38.1, SSCD gave it 6 votes, no other detective had an answer, and if the switch were on this would have been the answer. Watching these shadow lines is one of the best ways to see where the system is nearly right.

## 10. How PDQ gets it wrong

There are two kinds of mistake, and they pull in opposite directions.

**A false positive.** A rule fired for the wrong film. This is the mistake users notice, because a wrong name arrives on their phone. The usual causes:

- Dark scenes, fades, logo cards and blank frames look the same in every film. Since 3 Sep 2026 these are thrown away before fingerprinting, but some still get through.
- A look-alike: a scene in another film that genuinely looks like this one. Two films shot in the same location. A sequel reusing footage.
- The weak band. Thirty frames in 35-45 can come from a look-alike. P8 is the rule most often behind a wrong answer.
- One frame. The probe (P0) accepts on a single neighbour under 30, and the pre-scan on three under 28. One look-alike frame is enough for P0.
- Two copies of the same film in the library under different ids. The votes split between them.

**A missed match.** The right film was in the hints, but no rule fired, and another detective answered, or nothing did. Users notice this less, because the audio detective often saves the day. But it makes Trace slower and costs Gemini calls.

Your job is to cut the first kind without growing the second kind. Every time a rule is made stricter, some true exits stop firing. So a change has to be measured on both: the wrong answers it removes, and the right answers it loses.

## 11. How to measure

The pod's database keeps the score. For every clip a user ever sent, the table `traced_clips` records which detective answered (`match_source`), how many users pressed "wrong" (`wrong_count`), how many confirmed it (`correct_count`), and the film that was answered. The table `wrong_movie_reports` adds what the user said the film really was.

The script `4_pull_wrong_pdq_clips.py` in this folder pulls two lists from those tables: the clips where PDQ answered and a user said wrong, and the clips where PDQ answered and a user said correct. The second list is your control. A rule change that fixes the first list but breaks the second is not a fix.

The rule that fired is not in the database. It is in the pod's log, in the `[EARLY EXIT]` line. To see it for a clip, run the clip through `3_identify_clip.py` with an index that contains the wrongly answered film. The printout shows the scorecard and the rule, and you can see why it fired.

## 12. Two worked examples

**A clean clip.** A 21-second TikTok of the docking scene in Interstellar. Fourteen frames land in 0-20 with an average distance of 11.6, all within a 2-second stretch of the film at the 70-minute mark, from clip seconds 2 to 6. P3 fires at 6.4 seconds. Audio has no answer yet. The orchestrator accepts at once. Correct.

**A false positive.** A 15-second clip of a dark alley scene with heavy film grain. No frames in 0-20. Two frames in 20-35. Thirty-one frames in 35-45 for a film about a different alley, average distance 41.5, scattered across four separate minutes of that film (four film-time buckets far apart), all from clip seconds 3 to 5 (one clip-time bucket). P8 fires: thirty frames in 35-45. The orchestrator waits 12 seconds. Audio finds nothing because there is no dialogue. SSCD gives the film 1 vote, below the consensus floor of 4. The answer goes out. The user presses "wrong".

Look at what the second example had: no strong band, one clip second, four scattered film seconds, and a weak-band count just over the line. Every one of those is a sign a rule could have checked and did not. That is where the work is.

## 13. Where it is in the code

| what | file | function or place |
|---|---|---|
| Frames, crops, quality, fingerprints | `pdq/pdq_video_lookup_patched_final_updated.py` | `iter_frames_ffmpeg_fast`, `default_tiktokish_crops`, `PDQMultiCropIndex` |
| The search and the scorecards | the long-named file in `pdq/` starting `pdq_query_cli_dynamic_shards` | class `ShardedPDQ`, method `sharded_query_fast` |
| The early exit rules | same file | `_check_early_exit`, around line 5146. P9E and P9 are in `_check_end_of_processing_exit`, around line 5254. P3.5 and P1.5 are in `_stream_update_from_frame`, around line 5440 |
| The rule thresholds | same file | `MIN_HAMMING_ULTRA`, `FRAMES_ULTRA_CONFIDENT` and the others, around line 4856 |
| The pre-scan | same file | `_whole_clip_scan` |
| The probe, P0 | same file | `_maybe_finish_probe`, around line 4683 |
| Giving up early | same file | search for `PDQ_EARLY_REJECT`, around line 5629 |
| The wait before accepting a weak exit | `Max_spped_up.py` | `_wait_target_for_reason`, `_maybe_wait_for_35_45_exit` |
| What the orchestrator does with an exit | `Max_spped_up.py` | `identify_movie_with_face_and_audio`, search for "PDQ early accept" |
| The consensus rule | `Max_spped_up.py` | search for "CONSENSUS-SHADOW" |
| The hint-only band | `pdq/patches_applied/patch_pdq_ham_hintonly.py` | the whole file explains it |
| The scores from users | the database | tables `traced_clips` and `wrong_movie_reports` |
| The same steps, on your laptop | this folder | `pdq_engine.py` |

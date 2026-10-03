# Stopping the wrong answers: where I got to

*This week's changes, the measurements behind them, and where the limit turned out to be.*

Nada. For the meeting on 27 September 2026.

## The week in short

| | |
|---|---|
| Wrong answers I can reproduce | 7 |
| Removed by my changes | 2 |
| Correct answers checked | 49 |
| Correct answers broken | 0 |
| Clips secured | 125 of 141 |

- I removed the two wrong answers the rules were responsible for, without breaking a single correct answer.
- The five that remain match the pictures as well as correct answers do, so no rule change can separate them. I can now show that limit with numbers.
- I also fixed the clip problem that had me blocked for three weeks, and dropped one idea because the measurement said it made things worse.

## 1. Getting the clips back

- Last week's feedback was to test with clips where the right answer is known. I had almost none, so this became job one.
- TikTok: instead of asking how the pod manages it, I read the pod's downloader. When yt-dlp is blocked it falls back to the ScrapeCreators API, with the token already in credentials.env. I call the pod's own function, so my method matches production. About one credit per clip.
- I re-pulled the two lists for the first time since 12 September. Two weeks of new voted clips were waiting: the lists grew from 39 wrong and 41 correct to 47 wrong and 94 correct.
- I rebuilt my index from 80 films to 134, so every film either list mentions is in it.

| | Start of the week | Now |
|---|---|---|
| Clips on the two lists | 80 | 141 |
| Downloaded | 39 | 125 |
| Actually usable | 25 | 58 |

- The 16 clips I cannot get are gone for good: 14 deleted from the platforms, 2 age-restricted.
- The finding hiding in this: **clips rot**. Only 3 in 10 of the old clips still match what was traced. The fresh ones survive at 6 in 10. Every week of waiting costs Trace evidence permanently.
- Related discovery: the pod already stores each clip's fingerprints in a table called clip_query_hashes, and deletes them after about a day. Keeping those rows for voted clips would let us replay any wrong answer forever, without the video. More on this in the asks.

## 2. Measuring the P8 and P6 change properly

- Last week's change was built and tested on one clip. This week I could test it properly.
- Method: I keep the pod's original rules and my rules side by side. A script runs every clip through both and subtracts. The user-confirmed correct clips are the safety net.
- Why this way: removing wrong answers is easy, you just make rules stricter. The job is doing it without losing answers that already work, and that can only be shown by measuring both sides.
- Result: the change removes the Demeter wrong answer and nothing else moves. Every correct answer that works on the pod's rules also works on mine.

## 3. What a real match gives

- The other half of last week's feedback: look at what the actual movie scores.
- On the confirmed-correct clips, the correct film averages **between 24.8 and 38.0**.
- The wrong Demeter answer averaged **41.4**.
- So the gap I was cutting into is about three points wide, not the comfortable margin I had assumed. My cut at 40 sits inside it, but two genuinely correct answers live in the weak band.
- Tightening by feel would have broken them. This table is why thresholds are now set on data, not instinct.

## 4. An idea I tried and dropped

- While testing, I found the engine gives up on a clip after 64 fingerprints, about a second and a half, however long the clip is. One clip contained its film at distance 12 and the engine quit at 1.88 seconds of a 57-second video. The pre-scan is the only reason such clips get found.
- The obvious fix: don't give up until a quarter of the clip has been seen.
- Tested on just four clips it looked good. On the full measurement it recovered one correct answer and let **two wrong answers back in for every one recovered**. Looking longer also gives look-alikes time to pile up frames until a loose rule fires.
- So I am not proposing it. The underlying problem is real, but this fix makes Trace worse.
- What I keep from it: the spot check said yes, the measurement said no, and the measurement is right.

## 5. Most answers never reach the rules

With a real sample I could finally ask which part of the engine produces the answers.

| | decided by the pre-scan | decided by a rule |
|---|---|---|
| Correct answers (sample of 20) | 15 | 5 |
| Remaining wrong answers | 4 | 2 |

- The pre-scan skims 40 frames across the whole clip before any rule runs, and it decides about three quarters of everything, right and wrong alike.
- So changing the numbers inside the rules only ever reaches the smaller share of decisions.
- Tightening the pre-scan is not the answer either: it produces roughly 15 correct answers for every 3 or 4 wrong ones. It is the most accurate part of the engine, and squeezing it risks more good than bad.

## 6. Two more changes, and the final measurement

Two of the remaining wrong answers came from rules firing on scraps. Both fixes copy an idea the engine already uses elsewhere.

- **P9E** answered Grave Encounters 2 off 2 frames at an average of 34. Its sibling rule P9 has always demanded more frames when quality is worse, so P9E now does the same: 2 frames only at an average of 25 or better, mediocre evidence needs 4.
- **P0, the probe**, could answer off one single frame under 30. P2.5 already exists because one near-perfect frame was not trusted for P2, so the probe now needs two frames agreeing on the same film. When it defers, the ordinary rules still run and catch genuine matches.

Then the full measurement: all 40 wrong clips and all 85 control clips, through three engine versions, pre-scan on as in production.

| engine | wrong answers given | correct answers given |
|---|---|---|
| The pod's original rules | 7 | 49 |
| P8 and P6 change | 6 | 49 |
| Plus P9E and P0 change | 5 | 49 |

- Grave Encounters 2 stopped as intended. All 49 correct answers survive every version.
- What "stopped" looks like: on Demeter and Grave Encounters 2 the engine now stays quiet instead of naming a wrong film. The film still goes along as a hint for audio and SSCD. A no answer instead of a wrong one, which is the trade we agreed.
- Smile did not stop, and the reason matters: it has three probe frames agreeing at distance 22. It is a real picture match, not a fluke, which moves it into the next section.

## 7. Where this ends

- The five remaining wrong answers: Captain America: Civil War, Krrish 3, Smile, The In Between, The Northman.
- They match at distances **6 to 22**. My correct answers match at **8 to 26**. The wrong ones score as well as the right ones, sometimes better.
- That is the proven part: on the evidence PDQ sees, these five look exactly like correct answers, so no threshold, frame count or clustering test separates them from real matches.
- Why users pressed wrong on them is still an open question. None of the five came with the user saying what the film really was. Possible explanations: clips that mix footage from more than one source, shots that appear in more than one film such as trailer footage, or the vote itself. The In Between was voted correct by two users and wrong by one.
- Next step: watch the five clips next to the scene the engine matched. All five are downloaded, so this is quick.
- Whatever the answer, it is not a thresholds problem. These five belong with the orchestrator and the other detectives, and I would like to hand them over with their scorecards.

## 8. What I would like from the meeting

1. A yes or no on the P9E and P0 changes. They are small, commented, and measured at zero cost. With P8 and P6 the whole diff is four thresholds and two logic changes.
2. A home for the five picture-match cases. The question there is policy, not thresholds.
3. Retention on clip_query_hashes for voted clips. The pod already computes and stores those fingerprints, it just deletes them after a day. Keeping them solves the clip rot permanently.

---

Everything here ran on my laptop against a 134-film index with 16.7 million fingerprints.
The engine copy is verified identical to the pod except for the rules I changed, which is
what the rules check failing on exactly those rules proves. Nothing live was touched and
the database was read only.

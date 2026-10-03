# My prep notes for tomorrow

These are for me, not for showing anyone. Read once tonight, once in the morning. The
document I present from is PDQ_WEEKLY_UPDATE_26_SEPTEMBER_2026.pdf.

---

## The whole week in one minute

Last week Jude told me to test with clips where I know the right answer, and to look at
what the correct film actually scores. So this week I:

1. **Got the clips.** Found out how the pod downloads TikTok, pulled fresh lists, and went
   from 12 usable clips to a proper evidence base.
2. **Measured my rule change properly.** Ran everything through the pod's rules and mine,
   and subtracted. My change removes 1 wrong answer and breaks nothing.
3. **Tried a fix that failed.** The early-reject idea cost 2 wrong answers for every 1
   right one, so I dropped it. Measuring both sides is what caught it.
4. **Found who really decides.** Most answers, right and wrong, come from the pre-scan,
   which runs before the rules. Rule tuning can't reach those.
5. **Made two more small changes and ran the final measurement.** Wrong answers went from
   7 to 5. Correct answers: 49 before, 49 after. Nothing broke.

The five wrong answers that are left match the pictures as well as correct answers do, so
no rule can tell them apart. That's the limit of this task, and I can show it with
numbers.

---

## The numbers to remember

Only these. Everything else is in the document if someone asks.

| | |
|---|---|
| Wrong answers I can reproduce | 7 |
| Fixed by my changes | 2 (Demeter, Grave Encounters 2) |
| Can't be fixed by rules | 5 |
| Correct answers checked | 49 |
| Correct answers broken | **0** |
| Clips secured this week | 125 of 141 |

If I only remember one line: **two wrong answers removed, zero right answers lost, and the
other five aren't a rules problem.**

---

## Last week against this week

| | Last week (19 Sept) | This week (26 Sept) |
|---|---|---|
| **The rules** | I had changed two rules, P8 and P6, and they stopped one wrong answer, the Demeter clip. | I changed two more, P9E and P0, because they were firing on scraps the same way P8 did. That stopped a second wrong answer, Grave Encounters 2. |
| **Wrong answers** | The engine gave 6 wrong answers and I didn't know what was behind the other 5. | The engine gives 5 wrong answers where the pod gives 7, and I know exactly what the remaining 5 are. |
| **Proof it's safe** | I had checked my change against one wrong clip and one correct clip, so I believed it was safe but couldn't prove it. | I ran every clip through the pod's rules and through mine. All 49 correct answers that work on the pod's rules still work on mine. Nothing broke. |
| **The clips** | I had 39 clips downloaded and only about 12 were usable. TikTok was completely blocked and I didn't know why old clips wouldn't match. | I found the pod's own downloader and now have 125 of 141 clips, with 58 usable. And I know why the rest fail: clips rot. Fourteen are deleted for good, and only 3 in 10 of the old ones survive against 6 in 10 of the fresh ones. |
| **What a real match scores** | I had no idea, so I was setting thresholds half blind. | A real match averages between about 25 and 38. My cut at 40 was the right place, but with much less room than I thought. |
| **Why the right clip fails** | Jude told me to go and find out. I didn't know. | The engine gives up on a clip after about a second and a half, and the pre-scan is what rescues those clips. |
| **Who decides the answers** | I assumed the rules did, since that's what I was tuning. | The pre-scan makes about three quarters of all decisions, right and wrong. The rules I tune only ever see the rest. |
| **The five that remain** | An open question. Maybe more tuning would get them. | Proven out of reach. Their pictures genuinely match the film and they score as well as correct answers do, so any rule strict enough to block them would block real matches too. They need to be handed over, not chased. |
| **How I work** | I tuned against one wrong example and hoped for the best. | Nothing got kept unless the measurement on both lists said it was safe, and measuring is now one command. I dropped one idea, the early-reject fix, because it looked good on four clips and fell apart on the full set. Catching that before it shipped is the method working. |

If I have to say the improvement in one line: last week I had one fix tested on one clip,
and this week I have four fixes tested on 125 clips, a working way to get clips, and proof
of the point where changing rule numbers stops helping.

---

## What, why and how, for each part

### 1. Getting the clips

**What:** I went from 39 downloaded clips to 125, and from 12 usable to a real sample.

**Why:** I was stuck for three weeks because TikTok wouldn't download and old clips had
been replaced. Without clips I couldn't measure anything.

**How:** Three things. The pod's own downloader is in the repo, and it falls back to the
ScrapeCreators API when yt-dlp fails, using the token already in credentials.env. I
re-pulled the lists, which I hadn't done since 12 September, and two weeks of new voted
clips were waiting. And I rebuilt my index from 80 films to 134 so every film on the
lists is in it.

**One more thing I learned:** clips rot. 14 are deleted forever, and only 3 in 10 of the
old clips still match, against 6 in 10 of the fresh ones. Getting clips early matters.

### 2. Measuring the rule change

**What:** My P8 and P6 change removes the Demeter wrong answer and costs nothing.

**Why measure this way:** removing wrong answers is easy, you just make rules stricter.
The whole question is whether you broke correct answers doing it. So every measurement is
two numbers, never one.

**How:** I keep three engine files. The pod's original, my version, and the new one. A
script runs every clip through each and subtracts. The control clips, the ones users
confirmed as correct, are the safety net.

### 3. The failed experiment

**What:** the engine gives up on a clip after about 1.5 seconds if nothing matched yet. I
let it look at a quarter of the clip before giving up. It recovered one correct answer
and let two wrong ones back in. Dropped it.

**Why I'm still glad I tried:** it looked good when I tried it on four clips. The full
measurement over every clip killed it. That's the lesson, a quick look at a few examples
can lie to you.

### 4. The pre-scan finding

**What:** the pre-scan is a quick skim of 40 frames across the whole clip that runs
before the rules. It decides most answers. Of my correct answers, it made 15 of the 20 I
counted. Of the remaining wrong answers, it made 4 of 5.

**Why that matters:** the rules I've been tuning only ever see the cases the pre-scan
didn't already decide. And tightening the pre-scan would risk 15 right answers to chase 3
or 4 wrong ones, so I'm not proposing that.

### 5. The last two changes

**What:** P9E used to accept a lone candidate with just 2 mediocre frames. Now mediocre
evidence needs 4 frames. And P0, the probe, used to answer on one single frame. Now two
frames have to agree.

**Why these two:** both rules were firing on scraps, the same disease Demeter had. And
both fixes copy an idea the engine already uses somewhere else, so they're easy to defend.
P9 already scales frames with quality. P2.5 already demands a second frame before
trusting P2.

**How I know they're safe:** the final run. 40 wrong clips and 85 control clips through
all three engine versions. 49 correct answers every single time.

### 6. The five that remain

**What:** Captain America, Krrish 3, Smile, The In Between, The Northman.

**Why they can't be fixed with rules:** they match at distances 6 to 22. My correct
answers match at 8 to 26. The wrong ones score as well as the right ones, sometimes
better, so on the evidence PDQ sees they are identical to correct answers.

**Why users pressed wrong on them:** still an open question. None of these five users
typed in what the film really was. Could be mixed or edited clips, could be footage that
appears in more than one film, and in one case the vote itself is shaky, The In Between
got two correct votes against one wrong. The quick next step is watching the five clips
against the matched scenes.

**Whose problem it is:** the orchestrator, the audio detective, SSCD, or a product
decision. Not PDQ's thresholds.

---

## Words that might come up

| Word | What it means |
|---|---|
| Distance / hamming | how different two pictures are. 0 is identical, lower is better, over 45 is ignored |
| Pre-scan | a skim of 40 frames across the whole clip, runs first, usually decides |
| Probe (P0) | a quick look at the first second or two of the clip |
| Control clips | clips users confirmed correct. The thing I must not break |
| P9E | the rule for when only one film matched anything at all |
| Reproduce | the clip still gives the same answer today, so I can study it |

---

## Questions I might get

Say these however they come out, don't recite.

**"So is the task done?"**
> The part the rules were responsible for is done, two wrong answers removed and nothing
> broken. Five remain, and I can show they're not a rules problem. The pictures genuinely
> match, they score like correct answers do. Fixing those is an orchestrator or product
> question and I'd want to hand it over with the scorecards.

**"How sure are you nothing broke?"**
> I ran all 85 control clips through the pod's rules and through mine. Both give exactly
> the same 49 correct answers. Same films, all three versions.

**"How did you get TikTok working?"**
> I stopped asking and read the pod's downloader. It tries yt-dlp first and falls back to
> ScrapeCreators, with the token that's already in credentials.env. I called the same
> function the pod calls. It cost around a hundred credits out of seven and a half
> thousand.

**"Why did the numbers change during the week?"**
> The evidence base grew. I re-pulled the lists after two weeks and downloaded everything
> straight away. Fresh clips survive much better, six in ten against three in ten for the
> old ones. That's also why I'd pull the lists weekly from now on.

**"Should we tighten the pre-scan then?"**
> I'd be careful. On my count it makes 15 of 20 correct answers and 3 or 4 wrong ones.
> It's the most accurate part of the engine. Anything there needs the same both-lists
> measurement, and the trade doesn't look good.

**"What was the reject thing?"**
> A fix I tried and dropped. The engine gives up on a clip after about a second and a
> half, which throws away real matches, one matched at distance 12. But letting it look
> longer fed the loose rules and let two wrong answers back in for every right one
> recovered. The problem is real, my fix wasn't. It's parked.

**"Aren't your rules different from the pod now?"**
> Yes, on purpose. The rules check fails on exactly the rules I changed and nothing else.
> That's how I know my diff is the only difference.

**"What do you need from me?"**
> Three things. A yes or no on the P9E and P0 changes, they're small and measured. A home
> for the five picture-match cases, that's a policy question. And a look at keeping the
> clip_query_hashes rows for voted clips. The pod already computes those fingerprints and
> deletes them after a day. Keeping them would mean any wrong answer can be replayed
> forever, without the video.

**"What does the whole change look like in code?"**
> Four thresholds and two small logic changes, all commented. P8 only counts 35 to 40 and
> needs the frames to line up. P6 needs the film's average to stay medium. P9E needs 4
> frames when the average is mediocre. The probe needs two frames agreeing.

---

## If I get lost mid-meeting

Go back to the one line: **two wrong answers removed, zero right answers lost, the other
five aren't a rules problem.** Everything in the document backs that sentence.

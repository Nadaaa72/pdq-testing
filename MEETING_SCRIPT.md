# Script for presenting the weekly update

For me only. The document on the table is PDQ_WEEKLY_UPDATE_26_SEPTEMBER_2026.pdf.

Don't read this word for word or it will sound rehearsed. Read a section, look up, and
say it the way it comes out. The numbers are the only part to get exactly right.

About seven minutes at a normal pace.

---

## Opening

**Have the document closed. Just talk.**

> Before I open the document, here's what my week actually looked like, because it was
> really four jobs.
>
> First I went and got the clips. I found out how the pod downloads TikTok, re-pulled the
> lists, and went from 39 clips to 125, which finally gave me real evidence to test with.
>
> Second, I took last week's rule change and measured it properly against the pod's
> original rules, on every clip I have, instead of the one clip I had before.
>
> Third, I made two more rule changes, because with more clips I could see two other
> rules making the same mistake, and I measured those the same way.
>
> And fourth, I worked out which of the remaining wrong answers can be fixed with rules
> and which ones can't, so the ones that can't go to the right place instead of me
> chasing them forever.
>
> The headline is: two wrong answers stopped, zero correct answers broken, and I can
> prove both of those numbers. I'll walk through it in order.

---



## 1. Getting the clips back

**Open the document at section 1. Point at the small table with 80, 141, 39, 125.**

> The first thing I did was go and get clips, because you told me last week to test with
> clips where I know the right answer, and I only had a handful.
>
> The way I did it was by opening the pod's downloader and found it falls back to the ScrapeCreators API when yt-dlp gets blocked, using the token that's already in the credentials file. So I called the same function the pod calls. I also re-pulled the two lists from the database,  and I rebuilt my index (the library the engine searches) so every film on those lists is in it.
>
> That took me from 39 downloaded clips to 125, and from about 12 I could actually test  
> with to 58.
>
> And there's one finding in here I want to flag on its own. The clips rot. Fourteen are
> deleted from the platforms permanently, and of the older clips only three in ten still
> match what was traced. The fresh ones survive at six in ten. So every week we wait,
> Trace loses a bit more of its ability to learn from its own mistakes. I'll come back to
> that at the end because I think there's a cheap fix.

---



## 2. Measuring my change properly

**Point at section 2, then hold a finger on the words "nothing else moves".**

> Next I went back and properly tested the rule change I made last week, the P8 and P6
> one that stopped the Demeter clip.
>
> The way I test now is that I keep the pod's original rules and my rules side by side,
> and a script runs every single clip through both and compares. The clips users
> confirmed as correct are the safety net. If my version loses any of them, the change is
> no good, however many wrong answers it removes.
>
> The whole job is doing it without breaking answers that
> already work, and last week I could only check that on one clip, so I believed my
> change was safe but I couldn't prove it.
>
> Now I can. Every correct answer that works on the pod's rules also works on mine.
>
> For Trace that means the fix is real. One wrong film name that was reaching someone's
> phone doesn't any more, and nobody who was getting the right answer loses it.

---



## 3. What a real match gives

**Point at section 3, at the numbers 24.8 and 38.0, then at 41.4.**

> Quick reminder of how scoring works, because this section is about where to draw a
> line. Every match gets a score for how different the two pictures are. Zero means
> identical, so lower is better, and anything worse than 45 gets thrown away as
> meaningless.
>
> My change last week drew a line at 40. Evidence scoring worse than 40 can't decide an
> answer any more. That's what blocked Demeter, which scored 41.4.
>
> What I didn't know when I put that limit is where the correct answers score. So this week I measured it. I took the clips users confirmed as right and wrote down what the correct film scored on each one. They come in between about 25 and 38.
>
> Put those together and my line at 40 sits above every correct answer and below the wrong one, which is the only place a line works. But that is still narrow. The worst correct answer is 38 and the wrong one is 41.4, so the safe zone is about three points wide, and I picked 40 before I knew any of this. If I'd picked 37 instead, I would have blocked two correct answers and never understood why.
>
> So the lesson I'm taking is measure first, draw the line second. From here on the
> thresholds in this engine come from what real matches actually score, and that's what
> protects the answers users are already happy with.

---



## 4. The idea I tried and dropped

**Point at section 4. This one I present as a win, not an apology.**

> I also want to tell you about something that didn't work, because it's the best example
> of the method doing its job.
>
> While testing the correct clips I found the engine gives up on a clip after about a
> second and a half if nothing has matched yet, no matter how long the clip is. One clip
> had the film in it at distance 12, which is basically the same picture, and the engine
> quit at 1.88 seconds of a 57-second video. The pre-scan is the only reason clips like
> that get found.
>
> So I tried the obvious fix, which was to make it look at a quarter of the clip before
> giving up. When I first tried it on just four clips, it looked great. Then I ran the full
> measurement on both lists, and it let two wrong answers back in for every correct one
> it recovered. Looking longer helps real matches, but it also gives look-alikes time to
> pile up frames until a loose rule fires.
>
> So I dropped it. For Trace, the impact is a bad trade that never shipped. A version of
> the app that recovers one right answer but sends out two extra wrong ones is worse, and
> the only reason I know that is because I measured before keeping it.

---



## 5. Most answers never reach the rules

**Point at the two-row table in section 5.**

> Then I asked a question I couldn't ask before I had enough clips, which is: which part
> of the engine actually produces the answers?
>
> I counted it. The pre-scan, the quick skim that runs before any rule, decides about
> three quarters of everything, the right answers and the wrong ones alike. So all the
> work I've been doing, changing the numbers inside the rules, only ever affects the
> quarter of clips the pre-scan didn't already decide.
>
> That matters for where we spend effort. Four of the remaining five wrong answers come
> from the pre-scan, so changing rule numbers can never touch them. But I'm not
> proposing we tighten the pre-scan either, because on my count it produces fifteen
> correct answers for every three or four wrong ones. It's the most accurate part of the
> engine. Squeezing it would put more good answers at risk than bad ones.
>
> The useful thing is knowing the limit. We now know the most that changing these
> numbers can ever fix, so we can stop there instead of spending more weeks on changes
> that can't reach the remaining five.

---



## 6. Two more changes, and the final measurement

**Point at the three-row table in section 6. Finger down the right-hand column: 49, 49,
49.**

> With more clips I noticed two other rules doing the same thing P8 did with Demeter. They were deciding answers on far too little evidence. One of them answered Graveal Encounters 2 with just two frames, and neither of them was even a close match. The other one, the probe, was allowed to answer with one single frame.
>
> To fix i used a rule that demands more frames when the frames are lower quality, so I made the Grave Encounters rule work the same way. Two frames is enough only when they're good matches. If they're weaker, it needs four. And there's already a rule that won't accept one near-perfect frame on its own, it wants a second frame to back it up. So the probe works like that now too. It needs two frames pointing at the same film before it's allowed to decide.
>
> Then I ran the big test. I took all forty wrong clips and all eighty-five confirmed
> correct clips, and ran them through three versions of the engine. The pod's version,
> my version from last week, and my version from this week.
>
> The pod's version gives seven wrong answers. Last week's gives six. This week's gives
> five. And the correct answers stayed at forty-nine in all three versions, so I removed
> two wrong answers and didn't lose a single thing.
>
> And I want to be clear about what stopping a wrong answer actually looks like. On those
> two clips, Demeter and Grave Encounters 2, the engine doesn't name a different film
> now. It stays quiet. The film still gets passed along as a hint, so audio and SSCD can
> still look at it, but PDQ no longer sends the wrong name on its own. That's the trade
> you told me to make, a no answer instead of a wrong one.
>
> So for Trace, two wrong film names that were reaching users have stopped, and I
> checked that it cost us nothing.

---



## 7. Where this ends

**Point at section 7. Then look up, because this is the conclusion.**

> The five wrong answers that are left are the reason I can say where this work ends.
>
> I looked at each one. They match at distances between 6 and 22, and my correct answers
> match between 8 and 26. So the wrong ones score as well as the right ones, sometimes
> better. On the evidence PDQ sees, these five look exactly like correct answers. That's
> the proven part: any rule strict enough to block them would block real matches too.
>
> What I can't tell you yet is why users pressed wrong on them, because for these five
> nobody typed in what the film really was. It could be clips that mix footage from more
> than one thing. It could be shots that turn up in more than one film, like trailer
> footage. And in at least one case the vote itself is shaky, because The In Between was
> voted correct by two users and wrong by one.
>
> The obvious next step is to watch these five clips next to the scene the engine
> matched, and I have all five downloaded, so that's quick to do. But whichever way that
> comes out, it isn't a thresholds problem, and that's why I want to hand these over
> with their scorecards rather than keep chasing them with rule changes.

---



## 8. What I'd like from the meeting

**Point at the three numbered asks. Say each one, then pause and let him respond.**

> So I need three things.
>
> First, a yes or no on the two new rule changes. They're small, they're commented, and
> they're measured at zero cost. With last week's changes the whole diff is four
> thresholds and two logic changes.
>
> Second, a home for those five picture-match cases, because they're a policy question
> now, not a tuning one.
>
> And third, the one I'd push hardest. There's a table where the pod already stores every
> clip's fingerprints, and it deletes them after about a day. If we kept those rows for
> any clip a user votes on, we could replay any wrong answer forever without needing the
> video. That would end the clip rot problem permanently, and it's a retention change to
> something that already exists, not new infrastructure.

---



## Close

> That's the week. Two wrong answers gone, nothing broken, and a clear line between
> what's an engine problem and what isn't.

---



## If a question throws me

The fallback line is the same as always: two wrong answers removed, zero right answers
lost, and the other five aren't a rules problem. The longer answers are in
MEETING_PREP.md and the numbers are all in the document itself.
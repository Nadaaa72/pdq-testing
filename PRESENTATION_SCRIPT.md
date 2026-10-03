# Script for the meeting

My notes, not for handing out. The document is PDQ_FINDINGS.pdf.

Each section below is laid out the same way. The **POINT AT** line comes first, so I get the
page in front of them before I open my mouth. Then the words.

Don't read it out word for word, it'll sound read-out. Glance at the section, then say it
however it comes out. The only bits worth getting exactly right are the numbers and the
three questions at the end.

About five minutes. If I'm running short, keep sections 3, 5 and 8.

Numbers out loud as words. Forty-one point four, not 41.4.

---

## 1. Opening

**POINT AT — nothing. Document stays shut. Just talk.**

> Before I get into it, the short version is that the setup's all working, but I got stuck on
> actually getting hold of the clips, so I've only been able to look at two of them properly.
> I'll go through how I ended up there.

---



## 2. What the task was

**POINT AT — page 1, the paragraph under "What I was asked to do". Open the document here
and slide it towards him. Don't read it out, just let him see it's written down.**

> So the job was to take the clips where PDQ named the wrong film, figure out why it got
> confused, and change a rule so it stops.
>
> and you could make all the rules stricter. The problem is that would also stop it recognising films it currently gets right, so I'd be trading one kind of mistake for another. Which is why after every change I have to count both things, how many wrong answers went away and how many right answers I broke. That's what the second list is for, the clips people confirmed. It's there to catch me breaking stuff.

---



## 3. Setup

**POINT AT — the two-row table under "Setting it up". Finger on the word PASS on the first
row, then the second, as I say each one. Leave it there a second. This is the bit that says
my numbers can be trusted.**

> I ran the two checks that come with the folder before I did anything else, and they both
> pass. The first one compares my rules against the pod's and it went through about
> thirty-one thousand searches without finding a difference. The second one proves my laptop
> turns video into fingerprints the same way the pod does, byte for byte.
>
> I did this because otherwise when my results change later I'd have no idea whether it was the rule I changed or just my laptop doing something different.
>
> Then I pulled both lists and built an index with the eighty films that show up in them.

---



## 4. Where I got stuck

**POINT AT — the four-row table further down that page: 39, 20, 3, 2. Finger on each row in
turn, moving down as I say the numbers. Don't move on until he's seen the last row. This is
the most important table in the document.**

> Right, so. To look at a wrong answer I need to replay the clip, and to do that I need to
> download the video off the link the user sent. And most of them wouldn't download.
>
> I started with thirty-nine. Twenty came down. All fifteen TikTok ones failed, the tool just
> can't get past TikTok at the minute, and then four Instagram ones wanted a login.
>
> And then of the twenty I did get, seventeen of them don't match anything now. And I don't
> mean a weak match or a borderline one, I mean nothing comes back at all. I did run them all
> a second time with the pre-scan off, just in case the quick first look was bailing too
> early, but it made no difference to any of them.
>
> What I think is happening is that the video at those links isn't the video that got traced
> in the first place. They're social posts, so people edit them, delete them, put them back
> up.
>
> I did check whether I could get at the answer some other way without the video, and I
> can't. The database keeps the film that was answered but it doesn't keep the scorecard, and
> it doesn't keep which rule fired.
>
> So I was down to two clips.

---



## 5. Clip 1, The In Between

**POINT AT — turn to the "Clip 1" section. Two printouts on facing pages if it falls that
way. Find the VERDICT line at the bottom of each one before I start talking. First says
The In Between, second says no film accepted. Finger on the first when I say "run normally",
finger on the second when I say "turn the pre-scan off". That contrast is the whole point
and it's better seen than explained.**

> This one's The In Between. It's not the cleanest example because it got traced three times
> and two people said the answer was right, only one said wrong.
>
> Run normally, it finds the film. Four frames matched, best one eighteen away, and they all
> point at the same moment of the film.
>
> But then when I turn the pre-scan off, the exact same clip gets thrown out. It comes back
> saying the film isn't in the library at all.
>
> It's the same video and the same index, and I get the opposite answer. The difference is
> where each one looks. The pre-scan skims across the whole thirty seconds and finds the part
> that matches. The probe just takes a few frames off the front, lands nowhere near the right
> bit, and gives up after a second and a half.
>
> So that clip only ever gets found because of the pre-scan. The film was sat in the index the
> whole time.

---



## 6. Clip 2, The Last Voyage of the Demeter

**POINT AT — two things, in this order.**

**First: in the "Run 3" printout, the line** `[EARLY EXIT] P8: 31 frames in 35-45 (>=30)`**.
Finger on the 31, then on the 30, when I say it got over the line by one frame.**

**Then: the band table just below it. Finger on the "Weak, 35 to 45" row, then slide down to
"Ignored, over 45", while I say the bit about nearly bad enough to throw away.**

> This is the clean one. One person pressed wrong and nobody said otherwise.
>
> The rule that fired is P8, which is the weakest rule there is. The notes actually say it's
> the one behind most wrong answers, so finding it here wasn't a shock.
>
> P8 wants thirty frames in the weak band before it'll fire. It found thirty-one. So it got
> over the line by one frame.
>
> And the distances back that up. Lower is better, and anything over forty-five gets binned as
> meaningless. These thirty-one averaged forty-one point four. So basically the whole answer
> is built on matches that were nearly bad enough to throw away. There was nothing in the
> strong band and nothing in the medium band, none at all.

---



## 7. What I noticed

**POINT AT — nothing. Hands off the document. Say this looking at him.**

> The thing both of them have in common is they scraped over the line. One needed thirty
> frames and had thirty-one. The other needed three frames and had four. If either of them had
> come up one frame short, neither would have answered at all.
>
> Obviously two clips doesn't prove anything. But it does line up with what the notes say a
> wrong answer usually looks like, so at least it tells me where to start once I've got more.

---



## 8. The bit I couldn't work out

**POINT AT — turn to "The bit I could not work out" and leave the document open there.
Don't point at any one line. Then stop talking and wait. This is the one place I want an
answer before I carry on.**

> The notes say that since August the top of the weak band, so forty to forty-five, is hint
> only. Frames up there are meant to be able to point the other detectives at a film but never
> make PDQ answer on its own.
>
> But the Demeter clip got answered on frames averaging forty-one point four, which is inside
> that range. And when I went and read the engine, P8 counts everything from thirty-six up to
> the cut-off and doesn't do anything special with the forty to forty-five part.
>
> I can't tell from my copy whether that's handled somewhere else in the live system or
> whether P8 just skips it. If it does apply to P8 then this particular wrong answer probably
> wouldn't have happened, so that's the main thing I wanted to ask about.

---



## 9. What I need

**POINT AT — the numbered list under "What I need". Finger on number one, say it, pause.
Then two, pause. Then three. Don't rush these, they're the asks.**

> So I'm ready to get going on the engine, it's clips I haven't got.
>
> First one, does the pod keep a copy of the clips it traces? There's a clip hash column in
> the table so they got hashed at some point, which made me think the files might be stored
> somewhere. That would sort this out completely.
>
> Second, how does the pod download from TikTok? Mine can't, and that's fifteen of my
> thirty-nine gone.
>
> And third, are the early exit lines in the log kept for old clips? The rule that fired only
> ever exists in the log, so if those are still around I could just read off the rule for all
> thirty-nine and not replay anything.

---



## 10. Close

**POINT AT — the bullet list at the very end, "What I will do once I have them". One quick
sweep down it with a finger, then close the document.**

> Once I've got clips, the plan is to replay the lot twice each, write down the rule and the
> scorecard for every one, work out what the wrong ones have in common, change one number, and
> then come back to you with the two counts.
>
> That's about where I am.

---

---



# Questions I might get

Answers written loose on purpose. Say them how they come out.

## "Are you sure the clips changed? Could it just be that your index is too small?"

> I don't think so. Every film that got answered is in my index, I checked that before I built
> it. And two of the clips did come back right off that same index, so the index itself is
> fine. If it was an index problem I'd expect weak matches or partial ones, and what I'm
> getting is nothing.



## "Why only eighty films when the pod has nine and a half thousand?"

> Mostly size. Each film's about three meg of fingerprints, so eighty films is half a gig on
> my laptop. And the eighty I picked are every film named in either list, so whatever film got
> wrongly answered, it's definitely in there.
>
> One thing though, the small index does change something. There's a rule called P3.5 that
> fires when only one film in the whole index matched anything, and on eighty films that
> happens way more than it would on nine thousand. So if P3.5 turns up in my results I'd
> probably ignore it rather than report it.



## "Did you try updating the download tool?"

> Yeah. The version the folder pins, then the latest release, then the nightly build, and I
> tried it with the pod's TikTok cookies as well. Same error every time. So it's not a login
> thing, TikTok's changed something the tool can't get round.



## "Which rule would you change first?"

> Probably P8, though honestly two clips isn't enough to say that with a straight face.
>
> What stands out is that P8 only counts frames. It doesn't look at whether they cluster in
> one part of the film, and it doesn't look at whether they came from more than one moment of
> the clip. Other rules do check that, P4 makes the frames land inside a two second stretch of
> the film. So I'd be looking at either making P8 check the clustering the same way, or
> capping how bad the average can be, or just raising the count. But I'd want to see all
> thirty-nine before I picked.



## "What about the pre-scan, should that change?"

> I'd be careful with that one. On my first clip the pre-scan was the only reason the film got
> found at all, so it is doing something useful. And it's not really a rule, it runs before
> the rules and short-circuits them, which is why the notes tell you to replay with it off. If
> we did change it I'd want to measure that on its own, otherwise I won't know which change
> did what.



## "The In Between had two saying correct and one saying wrong. Is it actually wrong?"

> Probably not, to be honest. That's why I flagged it in the document instead of leaning on
> it. I put it in because of the pre-scan thing, which is interesting either way. Demeter's
> the one I'd actually stand behind.



## "What about the one that came back as a different film?"

> One of the twenty came back as F1: The Movie, which isn't what's on record for it. F1's in
> my index because it's on the control list. I haven't dug into that one yet, it's on my list
> to do.



## "How long once you've got the clips?"

> Replaying's about ten to twenty seconds a clip so running both lists is under an hour. The
> slow part is reading the scorecards and spotting the pattern, and then every change means
> running both lists again. A few days to something I'd be willing to show you, I'd say,
> assuming the clips are there.



## "How do you know your engine matches ours?"

> That's what the two checks are for. The rules one went through thirty-one thousand seven
> hundred searches against the pod's code and found no differences. The fingerprint one proved
> the frames and the crops and the fingerprints are byte for byte identical on both sides.
> Both pass right now.
>
> Worth saying the rules check will start failing the moment I change a rule, and that's
> expected, that's how I know my change is the only difference.



## "Which platforms actually worked?"

> The three that downloaded and matched were all Facebook links, which the database has down
> as unknown platform. Instagram mostly downloaded but then the videos didn't match anything.
> YouTube was one clip and it came down fine. TikTok was the total washout.


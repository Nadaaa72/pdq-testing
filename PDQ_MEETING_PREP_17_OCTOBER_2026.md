# Meeting prep: PDQ update

*17 October 2026. For Nada. Not for sharing.*

This is to get you ready to talk about the work. Read it once before you go in.

## First: the system, so you can explain it if asked

Someone sends us a clip. We need to say which film it came from.

1. We take some still pictures out of the clip.
2. Each picture gets turned into a short code. Similar-looking pictures get similar codes.
3. We compare those codes against the codes of every film we hold.
4. If enough of them match one film closely, we say it is that film.

That is the whole idea. Your work this week was about **step 1**: which pictures we take,
and how many.

Two words that come up:

**Distance.** How different two codes are, counted out of 256. Zero means identical. Under
about 20 means the pictures are almost certainly the same shot. Over 45 means nothing
alike.

**Agreement.** If a clip really comes from a film, every matching picture should point at a
consistent place in that film. Five matches all saying "this is around 40 minutes in" is a
real match. Five matches scattered randomly is a coincidence. Checking for that is the main
reason this system makes fewer mistakes than the old one.

## What you did, in one sentence each

**1.** Jude spotted that changing the number of pictures moved all the moments. You printed
the real timestamps and found the system was already reading the whole clip, so his
diagnosis was wrong, but something was wrong: each moment was worked out from the total, so
40 pictures and 50 pictures had no moments in common at all.

**2.** You fixed it so the moments stay fixed. Now 80 pictures is the same 40 plus 40 more,
instead of a different 80.

**3.** That let you test whether more pictures helps. It does: 46 films found went to 51,
and on a separate set 11 went to 17, with no new mistakes either time.

**4.** You also found that our test set cannot tell two approaches apart. Four sensible
choices of where to start gave results from 38 to 46 out of the same 125 clips.

## How to open

Do not start with the fix. Start with what you found. It is more interesting and it sets up
everything else.

Something like:

> "Jude asked me to look at why the timestamps moved when I changed the number of frames. He
> was right that something was broken, but it turned out to be a different thing from what
> we thought, and the knock-on effect is bigger."

Then explain the moments sliding. Then the fix. Then the numbers.

## Questions you might get, and what to say

**"So was Jude wrong?"**

He was right that it was broken and right that it mattered. His explanation was that the
percentages were being taken of the first 40 frames. They were not. They were percentages of
the whole clip all along, but each one was worked out from the total, so changing the total
moved every one. Same symptom, different cause, and the fix is different as a result.

**"How do you know it was reading the whole clip?"**

I printed the timestamps. At 40 frames they run 1% to 99% of the clip. At 50 they also run
1% to 99%. I wrote a small script that prints this for any clip, so anyone can check it.

**"Why does it matter that the moments moved?"**

Because it meant we had never actually tested whether more frames helps. Every comparison of
40 against 50 was really one set of 40 moments against a different set of 50. There was no
overlap at all. So the old result that said 50 was worse than 40 was not measuring frame
count, it was measuring which moments you happened to get.

**"Why 80 and not some other number?"**

Because the way the fix works, the moments only stay fixed if you double. 80 contains all 40
of the original moments plus 40 new ones. 50 cannot, because 50 is not a multiple of 40. So
40 against 80 is the only comparison here that can be trusted, and it is the one I ran.

**"What did it cost?"**

The whole set of 125 clips went from 11.3 minutes to 17.5. But the typical clip only went
from 3.2 seconds to 3.3, because a clip that is easy to identify still stops after the first
eight pictures. Only the hard ones pay for the rest.

**"Are you sure the 5 extra clips are not luck?"**

That is the right question, and it is why this result is different from the others. Because
the 80 moments include all 40 of the original ones, taking more can only add. It cannot take
anything away. And it held up on a second set of 77 clips that nobody had used to build the
rules, where it went from 11 to 17. Nothing was lost in either test.

**"You said our test set cannot tell approaches apart. How bad is that?"**

Four sensible places to put the first picture gave 38, 41, 41 and 46 films found out of the
same 125 clips. Nothing else changed. So anything smaller than about eight clips of
difference is noise. The reason is that a lot of clips hang on three matching frames in the
whole clip, so whether we land on one of them is close to a coin toss.

**"What would fix that?"**

More test clips. There are 2,539 in the database where a person confirmed the film and this
system was not the one that found it. That is the pool a proper test comes from. We have
been using 125.

**"Will it hold up on the real library?"**

I do not know yet, and I would expect precision to get worse, not better. Our test index
holds 16.7 million codes and the real one holds 2.29 billion. With that many more, the
closest match to any random picture gets closer by chance, and every threshold we use was
set against the small index. So our "one wrong answer in 48" is a small-index number. I am
part way through pointing the probe at the real library to find out.

**"What about the mirrored and cropped pictures, could you drop some?"**

I checked. Of 101 clips that matched anything, 91 were found by the ordinary picture and 10
only by the mirrored or letterboxed ones. So the extras do earn their place. I tried taking
them only when needed and it came out slower, because a clip that gets identified early
never reaches them anyway.

**"Why did you turn the time limit off?"**

It did not do what it claimed. 26 of 125 clips still ran past 15 seconds, one for 168,
because the system only checks the clock between batches and the last batch is 40 pictures
long. It cost three films and saved no time. I would rather switch something off than ship
something that says it does one thing and does another.

**"Did the production machine change anything?"**

Yes, and it changes what is worth working on. Making the codes is 92% of the cost there
against 73% on my laptop, because one code takes 52 milliseconds on the server and 14 on
mine. So reading fewer pictures is the weakest lever we have. Taking fewer pictures of each
frame, and making codes from smaller images, are both worth more.

**"How much did the testing cost us?"**

Nothing. The server already had 553 real clips from users on it, so I used those rather than
downloading new ones through the paid account.

## If you get stuck

Say "I would have to check that" and write it down. Nobody minds. What they will mind is a
confident number that turns out to be wrong.

Three things you can always fall back on, because you measured them yourself:

- 40 pictures and 50 pictures had **no moments in common**. Not one.
- 80 pictures found **51 films against 46**, and **17 against 11** on a separate set.
- Four starting points gave **38 to 46** out of the same clips, so the test set cannot
  separate small differences.

## One thing to say before anyone asks

Early on, I copied the test clips onto the server while 8 people were queued for the app.
The rule is to wait when anyone is waiting. It ran at the lowest priority and the queue went
from 8 down to 6 while it ran, so I do not think it slowed anyone down, but I should have
waited. Every job since checks the queue before each clip and waits by itself. You can see
that working: a later test refused to start on its own because 13 people were queued.

Saying this first is better than it coming up later.

## What you are asking for

One thing: **more test clips**. A few hundred from that pool of 2,539. That is what turns
the open questions into answers.

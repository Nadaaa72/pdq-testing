# PDQ: what I changed this week

*17 October 2026. Nada.*

The first stage of the clip identifier now finds more films than it did, and I found out
something uncomfortable about how we have been measuring it.

## What this part of the system does

When someone sends us a clip, the first thing we do is take a handful of still pictures from
it, turn each one into a short code, and look those codes up against every film we hold. If
the codes match a film closely enough, we answer straight away. If not, the clip goes on to
the slower stages.

Everything below is about that first look.

## The problem I was asked to look at

Jude noticed something odd. When I took 50 pictures from a clip instead of 40, the moments
the system looked at all moved. He said that should not happen: 11% of the way through a
clip is the same moment whatever else you do, so it looked like the system was only reading
the opening of each clip rather than the whole thing.

**He was right that something was wrong. The cause turned out to be different.**

I printed the actual moments for one clip at both settings. At 40 pictures they run from 1%
to 99% of the clip. At 50 they also run from 1% to 99%. So the system was already looking at
the whole clip, start to finish.

The real fault was this. Each moment was worked out by dividing the clip into however many
pieces you asked for. So the 16th moment out of 40 sits at 41% of the clip, and the 16th out
of 50 sits at 33%. Change the number and everything slides.

**The two settings had not one moment in common.** Not a single one.

That matters more than it sounds. It means we had never actually tested whether more
pictures helps. Every time we thought we were comparing 40 against 50, we were comparing one
set of 40 moments against a completely different set of 50. The earlier result that said 50
found fewer films than 40 was not measuring what we thought.

## What I changed

**1. The moments stay put when you ask for more.**

I changed how the moments are chosen so that each one sits at a fixed place in the clip that
does not depend on how many you take. The first eight are the same eight whether you take 40
pictures or 80.

So 80 is now genuinely 40 plus 40 more, rather than a different 80. Because the first 40 are
still there, taking more can only ever add to what you find. It cannot take anything away.

That is what made the next change testable.

**2. It takes 80 pictures instead of 40.**

With the moments pinned down, I could finally ask whether more pictures helps, and get an
answer that means something.

It does. On 125 clips it went from 46 films found to 51, with no new mistakes. On a
separate set of 77 clips that nobody had used to build any of the rules, it went from 11 to
17. Nothing was lost in either test.

**3. I found out how much of our recall number is luck.**

This is the uncomfortable one. I tried four sensible choices for where the first picture
should be taken from, changing nothing else. The results ranged from 38 films found to 46,
out of the same 125 clips.

Eight clips of difference, from nothing but shifting the moments by about 1% of the clip.

The reason is that a lot of clips hang on very little. I looked at the ones we lose, and
several of them only match the right film on three frames in the entire clip. Whether we
happen to land on one of those three is close to a coin toss.

**So our test set cannot tell two approaches apart.** Any difference smaller than about
eight clips is noise. This is the main thing I would want to fix next, and it is why the
80-picture result is worth trusting where the others are not: because the 80 contains the
40, it is the one comparison that cannot be luck.

## How I tested it

| What I ran | Clips | What it was for |
|---|---|---|
| The version before this week | 125 | something to compare against |
| The new version | 125 | the same clips, same conditions |
| Clips nobody used to build the rules | 77 | checking it was not just fitted to our own set |
| Four different starting points | 125 each | measuring how much of the result is luck |
| Two ideas that did not work | 125 each | see below |
| Real clips on the production machine | 150 | where the time actually goes |

Every answer was compared one clip at a time. Same clip, same film named, or it counts as a
difference.

## The numbers

**The first stage, on 125 clips**

| | Before | After |
|---|---|---|
| Films found | 46 | **51** |
| Wrong answers | 1 | **1** |
| Time for all 125 | 11.3 min | 17.5 min |
| A typical clip | 3.2 sec | 3.3 sec |

Five more films, no new mistakes. The total time went up by half, but the typical clip
barely moved, because a clip that is easy to identify still stops after the first eight
pictures. Only the hard ones pay for the rest.

**Clips nobody had used to build the rules, 77 of them**

| | 40 pictures | 80 pictures |
|---|---|---|
| Films we hold: named right | 11 of 40 | **17 of 40** |
| Films we hold: named wrong | none | **none** |
| Films we do not hold: stayed quiet | 37 of 37 | **37 of 37** |

Six more found, nothing lost, and still not one wrong answer. On the 37 clips where any
answer would have been a mistake, it kept quiet both times.

**How much is luck**

| Where the first picture comes from | Films found |
|---|---|
| 0.5% into the clip | 38 |
| 1.25% (what we had) | 46 |
| 2% | 41 |
| 4% | 41 |

Nothing changed but the starting point.

## Two things I tried that did not work

I am including these because the numbers are worth keeping, so nobody spends time on them
again.

**Taking the mirrored pictures only when needed.** We take about eleven pictures of every
frame: the frame itself, cropped versions, mirrored versions. I checked which ones actually
earn their place. Of 101 clips that matched anything, 91 were found by the ordinary picture
and 10 only by the mirrored or letterboxed ones. So the extras do pay for themselves and
cannot simply be cut.

I then tried taking the plain ones first and the mirrors only if the plain ones found
nothing. It came out slower, 18.3 minutes against 17.5. The saving was already being made
elsewhere: a clip that gets identified early never reaches the mirrors anyway.

**Putting a 15 second limit on each clip.** The idea was to stop the slowest clips holding
everything up. It does not work. 26 of the 125 clips still ran past 15 seconds, one of them
for 168, because the system only checks the clock between batches of pictures and the last
batch is 40 pictures long. It cost us three films and saved no time. It is switched off.

One thing that came out of that by accident is worth keeping. A limit measured in seconds
behaves differently depending on how busy the machine is. The same 15 seconds cost 13 films
on a loaded machine and 3 on a quiet one. On the production machine that would cut deepest
exactly when things are busiest.

## On the production machine

I moved the test clips onto the main server and measured where the time goes there, because
it is a different machine from my laptop and the answer is different.

| Per clip | |
|---|---|
| Making the codes from pictures | **24 seconds** |
| Getting hold of the pictures | 2.1 seconds |

Making the codes is **92%** of the cost there. On my laptop it was 73%. One code takes about
52 milliseconds on the server against 14 on my laptop.

That changes what is worth working on. Reading fewer pictures is the weakest lever. Taking
fewer pictures *of each frame*, and making the codes from smaller images, are both worth
more.

I did this without spending anything. The server already had 553 real clips from users
sitting on it, so I used those instead of downloading new ones, which would have cost money
from a paid account.

## What I have not answered yet

**We are testing against a tiny fraction of the real library.** Our test index holds 16.7
million codes. The real one holds **2.29 billion**. That is 137 times more.

This matters in a direction people do not expect. More codes means the closest match to any
random picture gets closer by chance. Every threshold in our rules was set against the small
index. **I would expect precision to get worse on the real library, not better**, and our
"one wrong answer in 48" is a small-index number that should not be quoted as if it were a
real one.

Measuring that properly is the next piece of work. I am part way through pointing the probe
at the real library.

## What would help

**A bigger set of test clips.** There are 2,539 clips in the database where a person
confirmed the film and this system was not the one that found it. That is the pool a real
test comes from. We have been using 125. With a few hundred of those, the questions above
stop being coin tosses.

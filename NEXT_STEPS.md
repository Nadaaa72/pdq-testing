# What I am actually doing, and what to do next

*Written after Jude's feedback on the 19 September update.*

---

# Part 1. What this job really is

PDQ looks at a clip and tries to name the film. It does this by turning pictures into
fingerprints and looking for films with similar pictures.

For every film it finds anything for, it fills in a **scorecard**:

- how many frames matched
- how close those matches were (the distance, where lower is better)
- whereabouts in the film they landed
- whereabouts in the clip they came from

Then a list of **rules** looks at that scorecard and decides: is this good enough to answer
with? Each rule is a different combination of "how many frames" and "how good".

My job is to move those rules so that:

- **fake matches get turned away**, and
- **real matches still get through**

Both halves matter. That second half is the part I have not done yet.

---

# Part 2. What I did last week, and what was missing

I had one clip that came back with the wrong film, The Last Voyage of the Demeter. I found
it fired on rule P8 with 31 frames where 30 were needed, at an average of 41.4.

So I tightened P8. Then the same wrong film came through on P6 instead, so I tightened P6.
Now that clip gives no answer at all. That part worked.

**The missing half:** I only ever looked at a wrong answer. I tightened the rules until it
went away. But I never looked at a clip where the answer was *right*, so I have no idea how
much room I had.

It is like setting the height barrier at a car park. I measured the one lorry that hit the
roof and lowered the barrier until it could not get in. But I never measured the ordinary
vans that need to get through. The barrier might be far too low now and I would not know.

The one "correct" clip I checked, The In Between, does not actually test my change. It is
answered by the **pre-scan**, which runs before the rules. So it never touches P6 or P8 at
all. It proved nothing about what I changed.

---

# Part 3. What Jude's feedback means

| What he said | What it means for me |
|---|---|
| Keep trying to find a sweet spot, your strategy is smart | The approach is right, carry on |
| A no answer is much better than a wrong one | My trade-off is correct, do not panic about being strict |
| Try with the clips you know, and investigate why the right clip fails. See what the actual movie gives | **The real instruction.** Use clips where I know the correct film, and look at the numbers a correct match produces |
| Do not worry about time. That's expected | The 15 minutes is fine, stop treating it as a problem |

"See what the actual movie gives" means: take a clip I know is from Southpaw, run it, and
look at what Southpaw's scorecard actually shows. How many frames? What average? Do they
line up in one part of the film?

Once I know that, I know where the floor is. **The sweet spot sits above the fakes and below
the real matches.** At the moment I only know where the fakes are.

---

# Part 4. Where the clips I know come from

`data/correct_pdq_clips.csv` is a list of 41 clips where a user pressed **correct**. Those
are clips where I know the right answer. I had never downloaded any of them.

19 of them download fine. They are now in `data/clips/`. Chaos Walking, Southpaw,
Snowpiercer, Soul, Once Upon a Time in Hollywood and others.

So I have gone from 1 known-correct clip to 19.

---

# Part 5. The exact steps

## Step 0. Before anything, know which engine is in place

There are now three engine files in the folder:

| file | what it is |
|---|---|
| `pdq_engine.py` | the one that actually runs |
| `pdq_engine_ORIGINAL.py` | the pod's rules, untouched |
| `pdq_engine_MYCHANGES.py` | my tightened version |

To put one in place, copy it over the live one:

```powershell
copy pdq_engine_MYCHANGES.py pdq_engine.py
```

## Step 1. Get the before-and-after numbers

This is the measurement Jude asked for last week and it is now one command:

```powershell
python compare_before_after.py
```

It runs every downloaded clip through the original rules and then through mine, and prints:

```
wrong answers removed : ?
right answers lost    : ?
```

Those two numbers together are the whole answer. One on its own means nothing.

It puts my engine back when it finishes, even if I stop it early.

## Step 2. Look at anything I broke

If a clip that used to give the right answer now gives no answer, that is the important
thing to investigate, and it is exactly what Jude means by "why the right clip fails".

Run that clip on its own and read the scorecard:

```powershell
python 3_identify_clip.py data\clips\<the file> --no-prescan
```

`--no-prescan` matters here. Without it the pre-scan may answer first and I learn nothing
about the rules.

Then read the "Top candidates" block and write down, for the **correct** film:

- how many frames matched
- the average distance
- whether they landed in one part of the film or were scattered
- which rule fired, or which rule *nearly* fired

## Step 3. Build up a picture of what a real match looks like

Do the same for several of the 19 known-correct clips, whether or not they broke. I am
collecting the ordinary numbers for genuine matches.

A simple table is enough:

| film | frames | average | lined up? | rule |
|---|---|---|---|---|
| Southpaw | | | | |
| Snowpiercer | | | | |
| Soul | | | | |

## Step 4. Compare that against the fake

The one fake I know well:

| | frames | average | lined up? |
|---|---|---|---|
| Demeter, the wrong answer | 31 | 41.4 | no, scattered over four minutes |

If real matches usually sit at, say, 20 to 30 average and do line up, then there is a wide
gap between them and the fake, and my rule can sit comfortably in the middle.

If some real matches also sit around 40 and scattered, then my change is too harsh and I
need a different way to tell them apart, probably the lining-up check rather than the
distance.

**The gap between those two tables is the sweet spot.**

## Step 5. Adjust, then measure again

Change one thing. Run `compare_before_after.py` again. Write down both numbers again.

Keep the change if wrong answers went down and right answers did not. Undo it if not.

## Step 6. What to report next week

- the two numbers, before and after
- the table of what real matches look like
- any clip where the right answer failed, and why

---

# Things worth remembering

**Both numbers, always.** Removing wrong answers is easy. Removing them without losing right
answers is the actual job.

**The pre-scan hides the rules.** If a clip is answered by SCAN, my rule changes did not
touch it. Use `--no-prescan` when I want to see the rules work.

**Speed does not matter.** Jude said so directly. The 15 minutes is expected.

**A no answer beats a wrong answer.** So if I am unsure, err on the strict side.

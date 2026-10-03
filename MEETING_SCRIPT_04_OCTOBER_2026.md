# Script for presenting the 4 October update

For me only. The document on the table is PDQ_WEEKLY_UPDATE_04_OCTOBER_2026.pdf.

Same rule as last time: don't read it word for word. Read a section, look up, say it the
way it comes out. The numbers are the only part to get exactly right.

About eight minutes at a normal pace.

---

## Opening

**Have the document closed. Just talk.**

> Last week you told me to stop bending the thresholds and change the actual tech. So
> this week was three jobs.
>
> First, I made the testing honest: every clip I run now records which rule gave the
> answer. So when something is wrong, I know exactly which part of the engine did it,
> not just that it happened.
>
> Second, I compared the three parts of the engine that can answer, worked out what the
> careful rules have that the pre-scan and the probe don't, and rebuilt the probe out of
> the missing pieces.
>
> Third, I built an edits test. Ten things a reposter actually does to a clip, applied
> one at a time to clips the engine gets right, so any failure is the edit's fault and
> nothing else. That found two places where the engine is completely blind, and I fixed
> both.
>
> The headline: the pod's rules give seven wrong answers on my full set. The rebuilt
> probe with the rules behind it gives one. And of the fifty-two correct answers, I keep
> forty-eight. I'll go through it.

---

## 1. Which rule gave the wrong answers

**Open at section 1. Point at the screenshot.**

> This is the printout, not a summary. All 125 clips through the pod's exact rules, and
> every answer tagged with the rule that produced it.
>
> Seven wrong answers reproduce. Four of them come from the pre-scan, and look at the
> distances: six, six, twelve, eighteen. Those pictures genuinely are in the index. The
> rules never even ran on those clips, which is why the last two weeks of rule changes
> could never have caught them. The other three are P0, P9E and P8, which are exactly
> the three my earlier changes went after.
>
> So the thing I'd been tuning could only ever reach three of the seven. That's the
> clearest argument I have for what you said last week.

---

## 2. What the system has that the deciders don't

**Section 2. The small table.**

> The engine can answer from three places. The pre-scan, the probe, and the rules.
>
> The careful rules check three things: lots of frames, the frames agreeing on where in
> the film they land, and the frames coming from more than one moment of the clip.
>
> The pre-scan and the probe, which between them decide almost everything, check none of
> that. The probe answers off one frame. And the engine's own notes say a true match
> gives the same offset for every frame. That's the strongest signal in the data and
> the two busiest parts of the engine ignore it.

---

## 3. The rebuilt probe

**Section 3. Don't linger, the next section is the point.**

> So the new probe is just: the pre-scan's whole-clip view, plus all the checks it never
> had. It samples forty frames across the clip, keeps a scorecard per film, and it only
> answers on three bars, each copied from a rule the pod already trusts. Two near-perfect
> frames. Or the old pre-scan bar plus agreement on film time. Or five medium frames that
> agree and come from two moments of the clip.
>
> The old one-frame probe is retired. This replaces it.

---

## 4. The measurement

**Section 4. Point at the three-line table, then the screenshot.**

> Same yardstick as every week, both numbers, all 125 clips.
>
> Pod's rules: seven wrong, fifty-two correct. The new probe entirely on its own: one
> wrong, forty-one. With the rules running behind it as the fallback: still one wrong,
> and forty-eight correct.
>
> The one that survives is Krrish 3, at distance six. The pictures are identical to
> pictures in the index. Nothing picture-based can refuse that; it needs audio or SSCD.
>
> The four correct answers I lose are all montage clips. The right film was the top
> candidate every single time, it just scatters across film time because the clip cuts
> between scenes. I can get them back, but the exact same loosening lets The Northman
> and Civil War back in, because on picture evidence they look the same. You told me a
> no answer beats a wrong one, so I left them out. But that's a policy call and I'd
> rather you made it than me.
>
> One more thing from the tables. The clip the pod answered as The Misfits comes back as
> F1: The Movie, at distance eight, on both the pod's rules and mine. Worth watching
> that clip. Something doesn't add up about where the live answer came from.

---

## 5. The edits test

**Section 5. The edit table screenshot, then the before-and-after one.**

> Ten edits, each applied to eight clips the engine identifies correctly unedited.
>
> First thing: no edit ever produced a wrong film. Anywhere. Edits don't fool the
> engine, they blind it. It goes quiet instead of guessing.
>
> Filters, black and white, recompression, speed changes: barely a scratch. Rotation and
> zoom hurt. And two edits blinded it completely. Mirroring: zero out of eight. And
> letterboxing: one out of eight.
>
> Both turned out to be missing tech. Nothing in the engine ever hashes a flipped frame,
> so I made the probe hash the mirror of everything it samples. Zero out of eight became
> eight out of eight, matching at distance two. And the pod has an active-region crop
> that finds the picture inside black bars, which is one of the pieces the laptop port
> left out. I built a simple version. One out of eight became six out of eight.
>
> Then the safety gate: I re-ran all 125 real clips with the new views on. Not one
> answer changed. The extra views only add, they never subtract.
>
> The honest cost is the probe is about four times slower with the extra views. On my
> laptop, irrelevant. If this goes near the pod, you'd run plain views first and only
> pay for the second look when the plain views find nothing.

---

## 6. Housekeeping

**Section 6. Quick.**

> Three small things. Everything is in a private GitHub repo now, pdq-testing, code and
> results, and I can add you to it today.
>
> Pod access works from my machine, verified read-only, nothing touched.
>
> And while setting that up, the access doc with the key in it ended up pasted into a
> chat. So if you'd rather rotate the key, now's a clean moment. Your call.

---

## 7. The asks

**Close the document. Count on fingers.**

> Four things.
>
> One, the policy call on the four montage clips. I recommend keeping the strict trade.
>
> Two, someone watches the Misfits clip.
>
> Three, a direction on the probe. If you want it taken towards the pod as the pre-scan
> and P0 replacement, I'd start with the plain-views-first version and measure it at the
> pod's index size.
>
> And four, still open from last week: keeping the clip_query_hashes rows for voted
> clips. The clips are still rotting.

---

## If he asks...

**...why not loosen the probe to get the four montages back?**
> Because I tried the numbers. The four I'd recover and the two wrong ones I'd readmit
> sit in the same evidence range. There's no bar between them. It's a trade, not a fix.

**...whether the mirror views could cause new wrong answers?**
> That was my worry too, so that was the gate. All 125 real clips, before and after,
> zero answers changed. It's in the repo if you want the diff.

**...how long the probe takes now?**
> About two minutes a clip on my laptop with every view on, against thirty seconds
> before. Plain-views-first brings ordinary clips back to today's cost.

**...whether the speed edits broke the film-time agreement?**
> I expected them to and they didn't. The three-second tolerance absorbs a 25 percent
> speed change. I had a fix designed and threw it away because the measurement said it
> wasn't needed.

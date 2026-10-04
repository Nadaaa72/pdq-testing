# Script for presenting the 4 October update

For me only. The document on the table is PDQ_WEEKLY_UPDATE_04_OCTOBER_2026.pdf.

Same rule as last time: don't read it word for word. Read a section, look up, say it the
way it comes out. The numbers are the only part to get exactly right.

About nine minutes at a normal pace.

---

## Opening

**Have the document closed. Just talk.**

> Last week you told me to change the actual tech instead of just tightening the rules.
> So this week I did three things.
>
> First, I changed how I test. Before, I could tell you a clip got the wrong film, but
> not which part of the engine made the mistake. Now, every time I run a clip, it writes
> down which rule gave the answer. So every mistake has a name next to it.
>
> Second, I went looking for what the careful parts of the engine have that the quick
> parts don't, and I rebuilt the probe out of what was missing.
>
> Third, I tested edited clips. I took clips the engine gets right, made ten edited
> copies of each, the kinds of edits people actually do when they repost, and ran those.
> If a copy fails, the edit is the reason, because the original worked. That found two
> edits where the engine is completely blind, and I fixed both.
>
> The numbers first: on my full test set, the pod's rules give seven wrong answers. My
> new version gives one. And of the fifty-two clips the pod gets right, I still get
> forty-eight. I'll go through it.

---



## 1. Which rule gave the wrong answers

**Open at section 1. Point at the screenshot.**

> This is the printout. All 125 clips through the pod's exact rules, and every answer
> tagged with the rule that produced it.
>
> Seven wrong answers show up, and four of them come from the pre-scan. The pre-scan is
> the quick skim the engine does before anything else: it grabs forty frames spread
> across the clip, and if some film clearly has those pictures, it answers on the spot
> and nothing else ever runs.
>
> Now look at the distances on those four. Distance is how different two pictures are.
> Zero means identical, and anything under about twenty is the same picture for all
> practical purposes. These four matched at six, six, twelve and eighteen. So those
> pictures genuinely are in our library, just attached to the wrong film, probably
> shared footage, things like trailers. The rules never ran on those clips at all. Which
> means two weeks of me adjusting rules could never have fixed them, whatever numbers I
> picked.
>
> The other three wrong answers did come from rules, and they're exactly the three rules
> I'd already changed. So the tuning I was doing could only ever reach three of the
> seven. That's the clearest proof of what you told me last week.

---



## 2. What the careful rules have that the quick parts don't

**Section 2. The small table.**

> The engine can answer from three places: the pre-scan, the probe, and the rules. The
> strange thing is how differently careful they are.
>
> The careful rules check three things before they answer. Did a lot of frames match.
> Do those frames all point at the same place in the film. And did they come from
> different moments of my clip, not just one frozen frame.
>
> That middle check is worth thirty seconds, because the whole week hangs on it. If my
> clip really is a scene from a film, then every frame of my clip matches the film at
> the same point. First frame matches minute forty, next frame matches minute forty plus
> one second, and so on. They all agree. A coincidence doesn't look like that. A
> coincidence picks up one stray frame from minute ten, another from minute fifty,
> scattered all over. The engine's own documentation says this is what a true match
> looks like.
>
> But the pre-scan and the probe, which between them give most of the answers, do none
> of these checks. The probe would answer off one single frame. So the parts doing most
> of the deciding do the least checking.

---



## 3. The rebuilt probe

**Section 3. Don't linger, the next section is the point.**

> The new probe is those missing pieces put together. It skims the whole clip, forty
> frames, like the pre-scan. But instead of just counting hits, it keeps a scorecard for
> every film: how many frames hit it, how good the best one is, whether they agree on
> where in the film they land, and whether they came from different parts of my clip.
>
> And it only answers in three situations, each copied from a rule the pod already
> trusts. Two near-identical frames. Or what the pre-scan used to need, plus the frames
> agreeing on film position. Or five decent frames that agree and come from two
> different moments of the clip.
>
> The old probe, the one-frame one, is switched off. This replaces it.

---



## 4. The measurement

**Section 4. Point at the three-line table, then the screenshot.**

> Both numbers, same as every week, all 125 clips.
>
> The pod's rules: seven wrong, fifty-two right. The new probe completely on its own,
> everything else switched off: one wrong, forty-one right. And the version I'd actually
> propose, the new probe with the rules kept as a backup for the clips it isn't sure
> about: one wrong, forty-eight right.
>
> The one wrong answer left is Krrish 3, matching at distance six. The pictures in that
> clip are in our library, and they are identical. No check that works on pictures can
> turn that away. That one needs the audio detective or SSCD.
>
> The four right answers I lose are all the same kind of clip: fan edits that jump
> between scenes. The right film was actually the top candidate on every one of them,
> but the frames point at many different places in the film, because the clip really
> does jump around, so my agreement check turns them away. I measured what happens if I
> loosen the check to let them back in: two of the wrong answers come back with them,
> because on pictures alone they look the same. You told me a no answer is better than a
> wrong one, so I kept it strict. But that's a choice about what Trace prefers, and I'd
> rather you made it than me.
>
> One more thing from the tables. There's a clip the pod answered as The Misfits, and a
> user voted it wrong. When I run that clip, the pod's own rules and mine both say F1,
> the Formula One film, at distance eight. Someone should watch that clip, because the
> live answer may not have come from where we think it did.

---



## 5. The edits test

**Section 5. The edit table screenshot, then the before-and-after one.**

> For the edits test I took eight clips the engine identifies correctly, and made ten
> edited copies of each. The edits are the ones reposters actually do: a colour filter,
> black and white, re-compressing, speeding up, slowing down, zooming in, tilting it a
> couple of degrees, caption bars, shrinking it inside a black frame, and flipping it
> left-to-right.
>
> First result, which surprised me: not one edit, on any version of the engine, produced
> a wrong film. When an edit beats the engine, the engine goes quiet. It doesn't guess.
>
> Most edits barely hurt. Filters, black and white, re-compression, speed changes,
> nearly everything still gets identified. Two edits made it completely blind, though.
> The flip: zero out of eight identified. And the black frame: one out of eight. The
> table in the document is from after my fixes, which is why it shows eight and six for
> those two. The before numbers are the zero and the one.
>
> The table also shows rotation at one out of eight and zoom at three, and those are a
> different kind of problem. The flip and the black frame hide a perfect picture that
> the engine never looks at. Rotation and zoom damage the fingerprint itself, so there's
> no hidden view to recover. This table is the probe on its own, with its strict bars.
> In the version with the rules as backup, those clips get a second chance from the
> rules, which is also the only way the pod itself survives them today.
>
> Both turned out to be missing machinery rather than bad thresholds. Nothing anywhere
> in the engine ever looks at the flipped picture, so a mirrored repost can't match
> anything. I made the probe also fingerprint the mirror image of each frame it samples,
> and zero out of eight became eight out of eight, matching at distance two, basically
> perfect. For the black frame, the pod has a trick called the active region crop that
> finds the picture inside the borders, and it's one of the pieces that never made it
> into my laptop copy. I built a simple version: find the black bars, cut them off,
> fingerprint what's inside. One out of eight became six out of eight. The two still
> missed have bars that aren't quite black, so my simple version doesn't see them as
> bars.
>
> Then I checked I hadn't broken anything. I re-ran all 125 real clips with the new
> views switched on, and not a single answer changed, in either direction.
>
> The cost is speed: with the extra views the probe takes about four times longer per
> clip. On my laptop that doesn't matter. If this ever goes towards the pod, the way to
> do it is to try the normal views first and only do the mirror and border checks when
> the normal ones found nothing. Then an ordinary clip costs the same as it does today.

---



## 6. Housekeeping

**Section 6. Quick.**

> Three quick things. All the code and results are in a private GitHub repo now, called
> pdq-testing. I can add you to it today.
>
> Pod access works from my machine. I tested it read-only: looked at the hostname and
> the ready status, touched nothing.
>
> And one thing I should flag. While I was setting that up, the access document with the
> key in it got pasted into a chat. If you'd rather rotate the key, this is a clean
> moment to do it. Your call.

---



## 7. The asks

**Close the document. Count on fingers.**

> Four things.
>
> One, the call on the four fan-edit clips: keep it strict, or take them back along with
> two wrong answers. I recommend keeping it strict.
>
> Two, someone watches the Misfits clip.
>
> Three, a direction on the probe. If you want it taken towards the pod, as the
> replacement for the pre-scan and the one-frame probe, my next step would be the
> normal-views-first version, measured at the pod's index size.
>
> And four, still open from last week: keeping the clip_query_hashes rows for voted
> clips. The clips are still rotting.

---



## If he asks...

**...why not loosen the probe to get the four fan edits back?**

> Because I measured it. The four I'd get back and the two wrong ones I'd let back in
> sit in the same range of evidence. There's nowhere to put the bar that separates them.
> So it's a choice between the two, not a fix.

**...whether the mirror views could cause new wrong answers?**

> That was my worry too, so that was the test I gated it on. All 125 real clips, before
> and after, zero answers changed. The diff is in the repo if you want it.

**...how long the probe takes now?**

> About two minutes a clip on my laptop with every view on, against thirty seconds
> before. Normal-views-first would bring ordinary clips back to today's cost.

**...whether the speed edits broke the film-position agreement?**

> I expected them to, and they didn't. The check has a three-second tolerance and that
> absorbs a 25 percent speed change. I had a fix designed for it and threw it away,
> because the measurement said it wasn't needed.

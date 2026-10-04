# Going in depth: the five questions, answered from the ground up

*Jude's structure for tomorrow: what was working before, how it was working, what I
built, how that works, and the results before and after. This is my study copy. Every
idea is explained from zero, so I can answer follow-ups, not just recite.*

Nada. For the meeting on 4 October 2026.

---

## 0. The foundations everything else stands on

Read this part until it feels obvious. Every answer tomorrow is built from these pieces.

**A fingerprint.** PDQ turns one picture into 256 ones and zeros, a tiny summary of
where the light and dark areas sit in the picture. Two pictures of the same thing give
nearly the same summary, even after a filter or some compression.

**Distance.** To compare two fingerprints, count how many of the 256 bits differ. That
count is the distance. Zero means identical. Under about 20, it is the same picture for
all practical purposes. 21 to 35, probably the same picture, maybe filtered or cropped.
36 to 44, might be the same, might be a look-alike. 45 and up is thrown away as noise.

**The library (the index).** Every film we protect is fingerprinted in advance, about
three frames per second of film. My laptop copy holds 134 films, 16.7 million
fingerprints. Each stored fingerprint remembers which film it came from and at what
time in the film it sits.

**A query.** When a clip comes in, the engine fingerprints its frames and asks the
library: for each clip fingerprint, which stored fingerprints are closest? Every answer
under distance 45 is one piece of evidence: "this frame of the clip looks like film X
at minute M".

**The offset.** For each piece of evidence, subtract the clip time from the film time.
If my clip really is a scene from the film, every frame matches the film at the same
offset: clip second 1 matches film minute 40:01, clip second 2 matches 40:02. Same
offset all the way. A coincidence scatters: a stray hit at minute 10, another at minute
50. The engine's own documentation calls the constant offset the signature of a true
match. Remember this one; it is the heart of the whole week.

---

## 1. What was working before

The pod's PDQ engine, which I have as an exact laptop copy (verified identical). It has
three parts that can produce an answer, and they run in this order:

1. **The pre-scan.** Before anything else, it grabs 40 frames spread across the whole
   clip and does a quick vote. If one film clearly owns those pictures, it answers right
   there and nothing else runs.
2. **The probe (rule P0).** If the pre-scan didn't answer, the engine starts reading the
   clip from the beginning, and after about a second it takes one quick look: is there
   any single frame that looks close to some film? If yes, answer on the spot.
3. **The rules (P1 to P9).** If neither quick part answered, the engine keeps reading
   the clip, builds a scorecard per candidate film, and a list of rules watches those
   scorecards. First rule to fire wins. Some rules want a few excellent frames, some
   want piles of mediocre ones, the careful ones also check the offsets.

And it genuinely was working, mostly: on my test set of 125 clips with known answers,
it identified 52 clips correctly. It also gave 7 wrong answers, the thing this whole
project is about.

---

## 2. How it was working, exactly

**The pre-scan's vote.** Each of the 40 sampled frames counts as a "hit" on a film if
its closest stored fingerprint is under distance 28. A film is accepted if it collects
at least 3 hits and the best one is under 20. That's the whole test. It never looks at
offsets, never asks whether the hits agree about where in the film they land, never
asks whether they came from different parts of the clip. Count and best, nothing else.

**The probe's test.** In the first seconds of the clip it collects up to 64
fingerprints from one crop shape, searches once, and accepts if any single fingerprint
is under distance 30. One frame. 30 is in the "probably" band, not the "certain" band.

**The rules.** The scorecard for each film counts matched frames in three quality
bands, remembers the best distance, and keeps two kinds of histogram: where in the film
the hits land (the offsets), and which seconds of the clip produced them. The careful
rules use all of it. P4, for instance, wants five strong frames that agree on film
position AND come from two different moments of the clip. But the rules only ever see
the clips the quick parts passed over.

**Where the wrong answers came from.** I ran all 125 clips and recorded which part
produced every answer. The seven wrong ones:

| part | wrong answers | the clips |
|---|---|---|
| pre-scan | 4 | Krrish 3 (6), The Northman (6), Civil War (12), The In Between (18) |
| probe P0 | 1 | Smile (26.8, five frames) |
| rule P9E | 1 | Grave Encounters 2 (two frames, avg 34) |
| rule P8 | 1 | Demeter (31 weak frames, avg 41) |

The numbers in brackets are distances. Look at the pre-scan four: distances 6 to 18.
Those pictures genuinely are in our library, attached to the wrong film, almost
certainly shared footage like trailers. And because the pre-scan answers before the
rules run, no rule change can ever touch them. The last three are the rules I'd already
tightened in previous weeks (P8 and P6, then P9E and P0 designed).

**So the structural problem:** the engine's checking and its deciding live in different
places. The parts that decide most of the traffic (pre-scan, probe) have the least
checking. The careful checks exist, in the mid-tier rules, but they rarely get to
decide anything.

---

## 3. What I built

Four things, each small on its own.

**First, attribution testing** (`attribute_rules.py`). Every clip run now records which
part of the engine gave the answer. Without this, "seven wrong answers" is a number;
with it, every wrong answer has the name of the rule that made it next to it. The table
in section 2 is its output. This is also how every later change gets judged.

**Second, the rebuilt probe** (`pdq_engine_PROBEV2.py`). One decider that has both the
quick parts' speed and the careful rules' checks:

- It samples 40 frames across the whole clip, like the pre-scan.
- For each sampled frame it fingerprints every view the full engine knows: the full
  frame, the caption-trimmed frame, and all the crop shapes. The old pre-scan and probe
  each used a subset.
- Per film it keeps a mini scorecard: how many distinct frames hit it, the best
  distance, and for every hit the pair (clip time, film time), so it can check the
  offsets.
- It answers only in three situations, each copied from a rule the pod already trusts:
  - **PV-A**: two near-identical frames (copied from P2.5)
  - **PV-B**: the old pre-scan bar, PLUS at least two hits agreeing on the offset
    (pre-scan + P4's check)
  - **PV-C**: five medium frames agreeing on offset, from two different moments of the
    clip (copied from P6a)
- The old one-frame P0 is retired; this replaces it. The streaming rules stay behind it
  as a backup for clips the probe isn't sure about.

**Third, the edits harness** (`make_edited_clips.py`, `test_edits.py`). Eight clips the
engine identifies correctly, ten edited copies of each: filter, black and white,
recompression, speed up, slow down, zoom, slight rotation, caption bars, letterbox,
mirror. Since the originals work, any failure is the edit's fault. It found the engine
completely blind to mirrored clips (0 of 8) and letterboxed clips (1 of 8).

**Fourth, the two blindness fixes**, both inside the probe:

- **Mirror**: the fingerprint describes where things sit in the picture; flip the
  picture and the fingerprint comes out completely different, and nothing in the engine
  ever looked at the flipped version. The probe now also fingerprints the mirror of
  every view it samples.
- **Letterbox**: the engine fingerprinted the whole frame, which is mostly black border
  once the clip is shrunk inside bars. The pod has an "active region crop" that finds
  the picture inside the borders; it was one of the pieces never ported to the laptop
  copy. I built a simple version: detect the near-black rows and columns, cut them off,
  fingerprint what's inside.

---

## 4. How the new probe works, on one worked example

Take a clip that really is a scene from Soul.

1. The probe grabs 40 frames spread across the clip. Frame at clip second 3 gets
   fingerprinted as the full frame, the trimmed frame, the crops, and the mirror of
   each.
2. Each fingerprint asks the library for its closest neighbours. Suppose the second-3
   frame's best answer is "Soul, film minute 41:03, distance 11".
3. The probe writes that on Soul's mini scorecard with the pair (clip 0:03, film
   41:03). Offset: 41 minutes.
4. The same happens for the other frames. Clip 0:10 matches film 41:10. Clip 0:21
   matches 41:21. Same offset, 41 minutes, every time.
5. Now the bars. Best distance 11 isn't under 12 with a second frame under 16, so not
   PV-A. But: three or more frames under 28, best under 20, and at least two agreeing
   on the offset? Yes, easily, they ALL agree. PV-B fires. Answer: Soul.

Now the same mechanics on a look-alike. A clip wrongly matching The Northman has one
frame at distance 6 (shared footage), and a few others at 16 to 28 scattered across
the film: offsets 12 minutes, 55 minutes, 80 minutes. Count and best look fine, which
is why the old pre-scan answered Northman. But no two hits agree on the offset, so
PV-B refuses, and PV-A needs two near-perfect frames and there's only one. The probe
stays quiet. That's the entire trick: real scenes agree, coincidences scatter.

The one case the trick can't solve: when the clip's pictures are identical to library
pictures at distance 6 AND agree (Krrish 3), there is nothing left for picture
evidence to say. And the one real cost: fan edits of a true film jump between scenes,
so their offsets genuinely scatter, and the strict probe declines four of those. They
look, on pictures alone, exactly like the Northman case. That's the policy question
I'm bringing.

---

## 5. Results, before and after

**On the real clips (125 with known answers):**

| | wrong answers | correct answers |
|---|---|---|
| before: the pod's rules | 7 | 52 |
| after: new probe + rules as backup | **1** | **48** |
| (new probe alone, everything else off) | 1 | 41 |

Per wrong answer: Demeter (P8), Grave Encounters 2 (P9E), Smile (P0) are stopped by
the rule changes and the probe replacing P0. Northman, Civil War, In Between are
refused by the agreement check. Krrish 3 remains, identical pictures, needs audio or
SSCD. The four correct answers lost are the fan-edit clips above.

**On the edited clips (8 per edit):**

| edit | before | after |
|---|---|---|
| mirror | 0 of 8 | **8 of 8**, at distance 2 |
| letterbox | 1 of 8 | **6 of 8** (two have bars that aren't quite black) |
| filter, b&w, recompression, speeds | 6-8 of 8 | unchanged |
| rotation, zoom | hurt the fingerprint itself | unchanged, backup rules' job |

And across every edit, on every engine version: not one edit ever produced a wrong
film. Edits silence the engine; they don't fool it.

**The safety gate.** After adding the mirror and bar-trim views I re-ran all 125 real
clips: not a single answer changed in either direction. The new views only ever helped
edited clips.

**The cost.** The extra views make the probe about four times slower per clip (about
two minutes instead of thirty seconds on my laptop). If this goes towards the pod:
normal views first, mirror and bar-trim only when the normal views find nothing, so
ordinary clips cost what they cost today.

---

## The one-breath version of each answer

- **What was working before?** The pod's engine: a quick pre-scan, a one-frame probe,
  then the rules. It got 52 of my 125 test clips right and 7 wrong.
- **How was it working?** The quick parts decide most clips on counting and best
  distance alone; the careful checks live in rules that rarely decide. Four of the
  seven wrong answers came from the pre-scan, where no rule change can reach.
- **What did I build?** Testing that names the rule behind every answer; a probe
  rebuilt with the whole-clip view plus the careful checks, especially offset
  agreement; an edits test; and fixes for the two edits that blinded the engine.
- **How does it work?** Real scenes match the film at one constant offset,
  coincidences scatter. The probe only answers when the evidence agrees the way a real
  scene does, on bars copied from rules the pod already trusts.
- **Results?** 7 wrong down to 1, keeping 48 of 52 correct. Mirror 0/8 to 8/8,
  letterbox 1/8 to 6/8, zero changes on real clips, no edit ever caused a wrong film.

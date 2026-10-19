# -*- coding: utf-8 -*-
"""show_sampling.py - which moments of a clip the probe actually looks at.

Answers the question directly rather than by reading the code: print the timestamps for one
clip at two different sample counts, and see whether they are the same moments.

    python show_sampling.py --duration 60
    python show_sampling.py data/clips/some_clip.mp4

The grid the probe has always used puts sample i at (i + 0.5) / n of the DURATION, so it has
always covered the whole clip and has never read only the first 40 frames. But every
position in that grid is a function of n, so changing the count relocates every sample
rather than adding any: the 40-sample grid and the 50-sample grid share NOT ONE moment. That
is the real reason 50 frames measured worse than 40 - it was a different 40, not 40 plus 10.

Anchored (PDQ_PROBE_ANCHORED=1), a position does not mention n at all, so 50 really is the
same 40 plus 10 more, and wave one is the same eight moments at any sample count.

Reads nothing but the clip's duration, so it is instant and needs no index.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv2_waves import anchored_fractions, sample_order, wave_bounds  # noqa: E402

SAMPLES = (40, 50)
WAVES = (8, 16, 24, 40)
LO, HI = 0.02, 0.98


def grid(n):
    """The positions and the visit order the probe uses today."""
    return [(i + 0.5) / n for i in range(n)], sample_order(n, "vdc")


def anchored(n):
    """The positions and the visit order with the samples anchored."""
    return anchored_fractions(n, LO, HI), list(range(n))


def show(name, maker, dur):
    print()
    print("=" * 78)
    print("  " + name)
    print("=" * 78)
    seen = []
    for n in SAMPLES:
        fracs, order = maker(n)
        # The grid's waves are scaled, because a wave of 8 out of 80 would cover an eighth of
        # the clip; anchored, wave one is the same eight moments at any count, so it is not.
        ref = n if maker is anchored else 40
        bounds = wave_bounds(n, WAVES, ref)
        w1 = order[:bounds[0]]
        print()
        print("  n_samples = %d        waves: %s" % (n, " -> ".join(str(b) for b in bounds)))
        print("    wave-1 ids      : %s" % w1)
        print("    their times     : %s" % ", ".join("%.2fs" % (dur * fracs[i]) for i in w1))
        print("    as %% of the clip: %s" % ", ".join("%.1f%%" % (100 * fracs[i]) for i in w1))
        s = sorted(fracs)
        gaps = [b - a for a, b in zip(s, s[1:])]
        print("    all %d samples   : %.1f%% to %.1f%% of the clip, "
              "gaps %.1f%% to %.1f%% (%.2fs to %.2fs)"
              % (len(fracs), 100 * s[0], 100 * s[-1], 100 * min(gaps), 100 * max(gaps),
                 dur * min(gaps), dur * max(gaps)))
        seen.append(set(round(f, 9) for f in fracs))
    shared = len(seen[0] & seen[1])
    print()
    print("  moments the %d-sample and %d-sample runs SHARE: %d of %d"
          % (SAMPLES[0], SAMPLES[1], shared, SAMPLES[0]))
    print("  -> raising the count %s"
          % ("ADDS samples and leaves the old ones where they were" if shared == SAMPLES[0]
             else "MOVES every sample, so the two runs are not comparable"))


def main():
    ap = argparse.ArgumentParser(description="which moments of a clip the probe looks at")
    ap.add_argument("clip", nargs="?", help="a clip, to take the real duration from")
    ap.add_argument("--duration", type=float, default=60.0,
                    help="clip length in seconds, when no clip is given (default 60)")
    a = ap.parse_args()

    dur = a.duration
    if a.clip:
        import cv2
        cap = cv2.VideoCapture(a.clip)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        cnt = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
        cap.release()
        if fps <= 0 or cnt <= 0:
            return "could not read a duration from %s" % a.clip
        dur = cnt / fps
        print("clip: %s" % a.clip)
    print("duration: %.1fs" % dur)

    show("THE GRID - sample i at (i + 0.5) / n  (the probe today)", grid, dur)
    show("ANCHORED - sample k at %.0f%% + %.0f%% x radical_inverse2(k)  (PDQ_PROBE_ANCHORED=1)"
         % (LO * 100, (HI - LO) * 100), anchored, dur)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

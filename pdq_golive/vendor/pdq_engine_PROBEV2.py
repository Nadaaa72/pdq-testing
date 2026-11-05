# -*- coding: utf-8 -*-
"""
pdq_engine.py - Trace's PDQ detective, ported step for step so it runs on a laptop.

WHAT THIS FILE IS
-----------------
Everything the pod does with PDQ, in one file, in the same order, with the same numbers:

  1. turn a film file into fingerprints           (fingerprint_video)      the "film side"
  2. read a fingerprint file that came from B2    (decode_blob)
  3. write and load an index in the pod's layout  (write_index, load_index)
  4. turn a clip into fingerprints, search, count, apply the early exit rules,
     and print what the pod prints                (identify_clip)          the "clip side"

The three scripts in this folder (1_, 2_, 3_) are thin. They call the functions here.

WHERE EACH PIECE CAME FROM
--------------------------
The film side and the crops are ported from   pdq/pdq_video_lookup_patched_final_updated.py
The clip side and the rules are ported from   the long-named file in pdq/ whose name starts
with pdq_query_cli_dynamic_shards and ends with PASS2_ALWAYS, functions sharded_query_fast, _hash_query, _check_early_exit,
_check_end_of_processing_exit, _stream_update_from_frame and _whole_clip_scan.
PDQ_BASICS.md explains the ideas. This file is the ideas as code.

WHAT IS DIFFERENT FROM THE POD (on purpose, and small)
------------------------------------------------------
- The index is the "flat" FAISS form, so it can be memory-mapped on a laptop. The pod uses
  a graph form (HNSW) at 9,500 films. Flat search is exact, so if anything this version finds
  slightly MORE neighbours than the pod, never fewer.
- No graphics card. Frames are decoded on the processor with the ffmpeg that comes with the
  imageio-ffmpeg package. Same filter, same frame timestamps.
- Two speed tricks the pod has are left out: the "active region crop" (finding the film
  inside a TikTok frame with borders) and the second cropped pass. Both change which frames
  are hashed, not how they are judged. The rules, the bands and the counting are identical.
- The pod checks the rules after every 4 new hashes. So does this file.

WORDS USED BELOW
----------------
hash / fingerprint   256 ones and zeros that describe one picture, stored as 32 bytes.
hamming              how many of the 256 differ between two fingerprints. 0 = identical.
group                which crop family a fingerprint came from: FULL, PORTRAIT, LANDSCAPE, SQUARE.
vidx                 a film's position in the index's list of films (0, 1, 2 ...). The
                     pod calls it "video index". It is NOT the database movie id.
label                the film's name as the pod prints it: "3112:Interstellar (tmdb=157336)".
offset               film time minus clip time, in seconds. A true match gives the same
                     offset for every matched frame.
"""
from __future__ import annotations

import json
import concurrent.futures as _futures
import os
import pickle
import subprocess
import sys
import time
import zlib
from array import array
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

try:
    import faiss
except ImportError as e:  # pragma: no cover
    raise SystemExit("faiss is not installed. Run: pip install -r requirements.txt") from e
try:
    import pdqhash
except ImportError as e:  # pragma: no cover
    raise SystemExit("pdqhash is not installed. Run: pip install -r requirements.txt") from e


# =============================================================================================
# 0. THE NUMBERS. These are the pod's live settings, copied from the search program.
#    Every one of them is a knob Nada may turn. The comment says what it does.
# =============================================================================================

# --- how a film is fingerprinted (the shard manifests on the pod carry these exact values) ---
FILM_FPS = 3.0            # keep up to 3 frames per second of film
FILM_DECODE_FPS = 8.0     # but look at 8 per second, and keep the ones that changed most
FILM_MAXDIM = 640         # shrink frames so the longest side is 640 pixels
FILM_QUALITY_MIN = 40     # throw away a fingerprint whose quality score is under 40
FILM_CHANGE_THRESH = 6.0  # a second is "static" if no frame changed by more than this

# --- how a clip is fingerprinted at query time (Max_spped_up.py passes these to the engine) ---
CLIP_FPS = 3.0            # same idea: keep about 3 frames per second of clip
CLIP_DECODE_FPS = 8.0     # decode 8 per second
CLIP_MAXDIM = 640
CLIP_QUALITY_MIN = 40
CLIP_CHANGE_THRESH = 6.0  # a decoded frame is kept if it changed by at least this much
CLIP_MAX_FRAMES = 300     # stop after 300 kept frames
CLIP_MAX_HASHES = 8000    # or 8000 fingerprints
K_PER_HASH = 64           # ask the index for the 64 closest film fingerprints per clip fingerprint
MAX_HAMMING = 45          # neighbours further than this are ignored
OFFSET_BUCKET_S = 1.0     # film-time buckets are 1 second wide

# --- when to run the rules while the clip is still being hashed ---
STREAM_START_HASHES = 3   # first check once 3 fingerprints exist
STREAM_BATCH_HASHES = 4   # then again every 4 new fingerprints

# --- the bands (PDQ_BASICS.md section 3) ---
RANGE_ULTRA_LOW = 5.0     # "practically identical"
RANGE_LOW = 20.0          # 0-20 is the strong band
RANGE_MID = 35.0          # 21-35 is the medium band
HAMMING_CUTOFF_EXCL = 45.0  # 36-44 is the weak band; 45 and up is ignored

# --- the rules (PDQ_BASICS.md section 6) ---
MIN_HAMMING_ULTRA = 15.0        # P1: one frame under 15 ...
MIN_HAMMING_FRAMES = 3          # ... plus at least 3 matched frames in total
FRAMES_ULTRA_CONFIDENT = 10     # P3: 10 frames in 0-20
FRAMES_LOW_CONFIDENT = 5        # P4/P5: 5 frames in 0-20 in one cluster
FRAMES_MID_CONFIDENT = 15       # P6: 15 frames in 20-35
FRAMES_HIGH_CONFIDENT = 30      # P8: 30 decision-capable weak frames in 35-40
TIMESTAMP_UNIQUE_THRESHOLD_S = 3.0   # P4: clip seconds count as "different moments" if 3 s apart
OFFSET_CLUSTER_MAX_SPAN_S = 2.0      # P4/P5/P6a/P7: matched frames "line up" if their film-time offsets sit within 2 s
FRAMES_CROSS_STRONG_0_20 = 8         # P5x: 8 strong frames in one cluster ...
FRAMES_CROSS_MED_20_35 = 6           # ... plus a medium bucket with 6
FRAMES_MIDLOW_CONFIDENT = 10         # P6a: 10 frames in 20-25 that line up
MIN_BUCKETS_FOR_DIVERSITY = 3        # P7: at least 3 clip seconds produced medium matches
MIN_UNIQUE_BUCKETS = 2               # P7: and at least 2 of them are "solid"
FRAMES_MIN_PER_BUCKET_SINGLE = 4     # P7: "solid" means 4 matches when there are exactly 3 clip seconds
FRAMES_MIN_PER_BUCKET_MULTI = 2      # P7: or 2 matches when there are more than 3
P7_STRICT_HAMMING = 25.0             # P7 gets stricter when the average is worse than 25:
P7_STRICT_FRAMES_PER_BUCKET = 4      #   then a clip second needs 4 matches to count ...
P7_STRICT_MIN_BUCKETS = 3            #   ... and more than 3 such seconds are needed ...
P7_STRICT_CONCENTRATED = 7           #   ... or one clip second with 7 matches
PENDING_WAIT_VIDEO_S = 3.0           # P5 is "pending": it fires only if 3 more seconds of clip bring nothing better
P9_HAM_LOOSE, P9_MINF_LOOSE = 42.0, 4     # P9: only film, avg <= 42 -> needs 4 weak frames
P9_HAM_TIGHT, P9_MINF_TIGHT = 44.0, 8     #     avg <= 44 -> needs 8
P9_MINF_CUTOFF = 12                       #     avg > 44  -> needs 12

# --- the whole-clip pre-scan (PDQ_BASICS.md section 6, "before the rules") ---
SCAN_SAMPLES = 40          # sample 40 frames spread over the whole clip
SCAN_ACCEPT_HAMMING = 28   # a sampled frame "hits" a film if its best neighbour is under 28
SCAN_STRONG_ANCHOR = 20    # the film's best hit must be under 20 ...
SCAN_MIN_FRAMES = 3        # ... and at least 3 sampled frames must hit it (pod default 2, live env 3)

# --- the probe, rule P0 (runs once, early in the clip) ---
PROBE_MIN_S = 0.75         # the probe fires after 0.75 s of clip ...
PROBE_MIN_HASHES = 15      # ... once it holds 15 fingerprints (or after PROBE_MAX_S no matter what)
PROBE_MAX_S = 4.0
PROBE_MAX_STORE = 64       # it keeps at most 64 fingerprints, from ONE crop family (see probe_group_for)
PROBE_ACCEPT_HAMMING = 30  # P0: one neighbour under 30 is enough to accept. One frame.
QUALITY_MIN_FLOOR = 30     # if the probe found no fingerprint at all, the quality bar drops by 15, never below 30

# --- the probe V2 (replaces the pre-scan AND rule P0 in this engine version) ---
# The old probe looked at 4 seconds of clip, one crop family, and accepted off ONE frame.
# The old pre-scan looked at the whole clip but only counted hits and took the best one.
# This probe keeps the pre-scan's whole-clip view and adds the checks the full system has
# and they never did: per-film evidence, film-time agreement (every true match gives the
# same offset), and spread across the clip. Its rulebook mirrors the trusted rules.
# How many frames to sample. Settable so the sample size can be measured rather than
# assumed: PDQ_PROBE_SAMPLES=50 reads 50 frames instead of 40. The wave schedule below
# scales with it, so the early waves stay the same size and the extra frames land in the
# last wave, where only the clips that need them ever pay for them.
# 80, not 40, since 17 Oct 2026. Measured on two independent sets: on the 125 real clips
# 51 right / 1 wrong against 40's 46 / 1, and on the 77 held-out clips 17 of 40 against 11.
# Ten clips gained and six gained, none lost either time, and no new wrong answers. The cost
# is about half again as much stage-1 time on the whole set (17.5 min against 11.3), though
# the median clip barely moves because the waves still stop it at 8 frames.
#
# This is only a fair comparison BECAUSE of the nested sampling below: the 80 moments
# contain all 40 of the 40-sample moments, so 80 can only add. Raising the count on the old
# grid relocates every sample instead, and that measures nothing - see pv2_waves.
PV2_SAMPLES = int(os.environ.get("PDQ_PROBE_SAMPLES", "80"))
PV2_OFFSET_TOL_S = 3.0      # two hits "agree" on film time if their offsets sit within 3 s
PV2_SPREAD_S = 3.0          # clip moments count as different if 3 s apart (same as P4)
PV2_A_BEST, PV2_A_DIST, PV2_A_FRAMES = 12.0, 16.0, 2   # PV-A (like P2.5): 2 near-perfect frames
PV2_B_BEST, PV2_B_DIST, PV2_B_FRAMES = 20.0, 28.0, 3   # PV-B (the old pre-scan bar) ...
PV2_B_NEED_ALIGN = 2                                   # ... but 2 hits must now agree on film time
PV2_C_BEST, PV2_C_DIST, PV2_C_FRAMES = 26.0, 33.0, 5   # PV-C (like P6a): medium frames ...
PV2_C_NEED_ALIGN, PV2_C_NEED_SPREAD = 3, 2             # ... 3 agreeing, from 2 clip moments
# Three more bars, ported into the probe and measured over all 125 real clips with
# replay_rules.py. Together they take the probe alone from 42 right / 1 wrong to
# 47 right / 1 wrong, with precision unchanged at 97.9%.
#
# P1 is the streaming rules' most common exit: one frame under 15 plus two others. Ported
# UNCHANGED it readmits The Northman - one distance-6 frame of shared footage and five
# scattered hits - which is the exact wrong answer this probe exists to refuse. So it gets
# the agreement check the probe's own bars have, and that check is measured only over hits
# under PV2_P1_DIST: unbanded, Northman's two junk hits at distances 30 and 44 corroborate
# each other and it gets back in.
PV2_P1_BEST, PV2_P1_FRAMES = 15.0, 3
PV2_P1_ALIGN, PV2_P1_DIST = 2, 28.0
# PV-E, the cut rule: a fan edit cuts between moments of one film, so it produces SEVERAL
# film-time clusters that each corroborate internally, where a look-alike produces isolated
# singletons. PV2_E_PER_CLUSTER is the whole rule - at 1 it stops meaning corroboration and
# lets The Northman in; at 2 it recovers real edits only.
PV2_E_CLUSTERS, PV2_E_PER_CLUSTER, PV2_E_BEST = 2, 2, 33.0
# P3.5: nothing else in the index matched at all, so the bar drops. Careful on a small
# index - with 134 films a sole candidate is common, with the pod's 9,500 it is rare.
PV2_P35_BARS = ((20.0, 4), (30.0, 7), (35.0, 12), (45.0, 20))
# Collect the plain views first and the mirrored / letterbox-trimmed views only if the plain
# ones did not answer. Recall-identical by construction (see super_probe), ~2x cheaper on
# every clip the probe accepts. Off by default until measured over all 125 clips.
PV2_TWO_STAGE = os.environ.get("PDQ_PROBE_TWO_STAGE") == "1"
# The second round: when nothing passes but some film is in the running, sample again densely
# around the moments that already matched, searching ONLY the shortlisted films. Measured, one
# film searches 63x faster than the whole 134-film index (0.024 s vs 1.504 s for 300 queries),
# and that cost does not grow with the catalogue. Off by default until measured end to end.
PV2_RESAMPLE = os.environ.get("PDQ_PROBE_RESAMPLE") == "1"
PV2_SHORTLIST = 20          # how many candidate films the second round may look at
# --- the verifier: a dense look at the moments that already matched, shortlist only --------
# Measured on the held-out clips (probe_lab.py, 23 Oct 2026): where the probe declines a clip
# whose film IS among its candidates, the evidence is almost always ONE matched moment of
# the clip - Spider-Man: three hits at clip 23-25 s, distances 22/26/32, one film offset -
# and every bar asks for corroboration that one moment cannot give at 80 frames spread over a
# minute. The waves can never fix that: more evenly spread frames land in that moment
# rarely. So after the waves decline, look again where the candidates matched - a short
# burst of frames either side of each hot moment - and search those frames against the
# shortlisted films ONLY, exhaustively.
#
# Searching only the shortlist is the point, twice over. It is cheap and does not grow with
# the catalogue. And it is immune to the top-K cut: at 2.55 billion codes a true match at
# distance 35 has many chance neighbours closer than it, so K_PER_HASH=64 drops it from the
# whole-index search; against five films' codes nothing crowds it out.
#
# Accepting on the burst uses the probe's own bars over the merged evidence. Off until
# measured - see probe_lab.py --verify.
PV2_VERIFY = os.environ.get("PDQ_PROBE_VERIFY") == "1"
PV2_VERIFY_FILMS = int(os.environ.get("PDQ_PROBE_VERIFY_FILMS", "5"))     # shortlist size
PV2_VERIFY_MAX_BEST = 40.0     # a film must have one hit under this to be shortlisted
PV2_VERIFY_MOMENTS = int(os.environ.get("PDQ_PROBE_VERIFY_MOMENTS", "6"))  # bursts per clip
PV2_VERIFY_SPAN_S = 1.5        # each burst covers the moment +/- this
PV2_VERIFY_FPS = 4.0           # ... at this many frames a second
# Neighbours per fingerprint in a SHORTLIST search. A few films' codes, so a deep look is
# cheap, and 64 can be filled by one film's near-duplicate frames of the same scene.
PV2_SHORTLIST_K = 256
# --- the wave schedule: stop paying for evidence the answer no longer needs ---------------
# The probe used to be all-or-nothing: all 40 seeks and every hash before anyone looked at a
# single result, even when sample one was a perfect match and even when the clip is not in the
# catalogue at all. Measured over the 125 real clips, that is a 10.9 s median, 46.6 s at p90
# and 242.5 s at worst - 40.5 minutes for the set, and not one clip under a second.
#
# So the samples are taken in WAVES instead, and the probe judges after each one. It accepts
# as soon as a bar fires, and gives up while the whole run has still found nothing. Measured
# with replay_rules.py against the saved evidence of all 125 clips, that is
# DECISION-IDENTICAL to the full scan - 47 right, 1 wrong, the same film on all 48 answers -
# at 49% of the sampled frames. Cutting frames any other way does not survive: flat
# decimation to 20 evenly spread samples drops 47 right to 31, because the bars reward hits
# that agree on a film-time offset and thinning the samples destroys the agreement.
#
# Reproduce or re-measure any of this in a second, without decoding a frame:
#   python replay_rules.py --rules adopted --waves 8,16,24,40 --bar run --audit-waves --cost
try:
    from pv2_waves import (sample_order as _wave_order, wave_bounds as _wave_bounds,
                           anchored_fractions as _anchored_fractions,
                           nested_fractions as _nested_fractions,
                           nested_order as _nested_order)
except ModuleNotFoundError:
    # Loaded by a harness that lives somewhere else, so this folder is not on the path.
    # dump_probe_evidence.py, attribute_rules.py and app.py all load this file by path, and
    # a test script can sit anywhere, so find our neighbour rather than depend on the caller.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from pv2_waves import (sample_order as _wave_order, wave_bounds as _wave_bounds,
                           anchored_fractions as _anchored_fractions,
                           nested_fractions as _nested_fractions,
                           nested_order as _nested_order)
PV2_WAVES = (8, 16, 24, 40)          # cumulative sample counts, tuned at PV2_SAMPLES=40
# Settable, e.g. PDQ_PROBE_WAVES=8,16,24,40,80 for 160 samples. The ladder is read literally
# under nested sampling and the total is always appended as the last wave, so at 160 frames
# the default would end on ONE wave of 120 frames - the shape that made the time budget unable
# to bind (see PV2_BUDGET_S). A rung at 80 keeps every wave at most half the clip's frames.
if os.environ.get("PDQ_PROBE_WAVES"):
    PV2_WAVES = tuple(int(x) for x in os.environ["PDQ_PROBE_WAVES"].split(",") if x.strip())
PV2_PROGRESSIVE = os.environ.get("PDQ_PROBE_PROGRESSIVE", "1") == "1"
PV2_WAVE_ORDER = os.environ.get("PDQ_PROBE_WAVE_ORDER", "vdc")      # vdc | golden | linear
PV2_WAVE_BAR = os.environ.get("PDQ_PROBE_WAVE_BAR", "run")          # run | wave | off
# How many frames must be looked at before "nothing comes close" may stop the clip.
# Jude's Part 6: the check belongs at the end, not the start. 0 lets it fire from the
# first wave, which is what shipped; set it to measure what that early stop costs.
# Note the schedule: at 80 samples the waves are 8, 16, 24, 40, 80 and the bar is only
# tested BETWEEN waves, so any value above 40 stops it firing at all.
PV2_GIVEUP_MIN_FRAMES = int(os.environ.get("PDQ_PROBE_GIVEUP_MIN_FRAMES", "0"))
# Does a wave judge on EVERYTHING seen so far, or only on its own frames?
#
# Carrying forward is what ships, and it is what Jude's Part 5 asks for: one frame
# matching a film in wave 1 plus one more in wave 2 is two frames, and a rule needing
# two can fire. Judging each wave alone would see one and one and never fire.
#
# This switch exists to MEASURE that rather than assert it. Setting it to 0 makes each
# wave judge on its own frames only, which is the "separate buckets" behaviour, and the
# difference between the two runs is what carrying forward actually buys.
PV2_CARRY_FORWARD = os.environ.get("PDQ_PROBE_CARRY", "1") == "1"
# How many of a frame's pictures to fingerprint at once.
#
# Making the codes is 92% of what a clip costs on the pod - 24 seconds against 2.1 for
# reaching the frames - and until now every picture was done one after another. A frame
# becomes about eleven pictures.
#
# CORRECTION, 23 Oct 2026, from reading pdqhash's own source (bindings.pyx): compute() does
# NOT let go of Python's lock. The C++ that shrinks and transforms the picture runs with the
# lock held; only the numpy colour conversion before it releases it. Measured on a laptop,
# 4 threads hash real-sized pictures 1.5x faster than 1, 8 threads 1.6-1.9x - not 4x or 8x.
# That is where the pod's 21% came from, and it is about all a thread pool can ever give.
# See PV2_MIRROR for the saving that does not depend on cores at all.
#
# 1 keeps the old behaviour exactly, and that is the default on purpose: this runs on a
# pod serving real users, where the house rule is one low-priority process and no
# contention. Turning it up is a deliberate act, not something that happens by default.
PV2_WORKERS = max(1, int(os.environ.get("PDQ_PROBE_WORKERS", "1")))
# Where the mirrored fingerprints come from.
#
#   pixel     mirror the picture, then hash it again. What has always shipped. The mirrors
#             are about half of every frame's pictures, so half the hashing.
#   dihedral  hash the picture once with pdqhash.compute_dihedral and read the mirror out of
#             the same computation (pdq_hash_dihedral). Same targets, same tags, same search;
#             the mirror hashes cost nothing. They sit a few bits from the pixel mirrors (see
#             DIH_*), so this is measured before it ships, not assumed.
PV2_MIRROR = os.environ.get("PDQ_PROBE_MIRROR", "pixel")
# Search the three rotations as well (tags "r:"), read from the same dihedral computation, so
# they cost search rows and no hashing. A sideways or upside-down repost is what these are
# for. NOT the 2-degree tilt of the edited suite's "rot2" clips - a dihedral variant is a
# quarter turn, and a 2-degree tilt is still nearest the unrotated picture.
PV2_ROTATE = os.environ.get("PDQ_PROBE_ROTATE", "0") == "1"
# Shrink each sampled frame so its longest side is this before fingerprinting it. 0 = the
# clip's own resolution, which is what ships.
#
# Why it matters: the index was built from film frames shrunk to FILM_MAXDIM=640, so a clip
# hashed at 640 is measured 3.7 bits closer to what the index holds, and the cost of a
# fingerprint stops depending on the clip. Measured on the 125 local clips, time per clip
# tracks MEGAPIXELS (correlation 0.49) and not duration (0.10): the slowest clip, 97 s, is a
# 34-second 1080x1920 one; a 35-minute clip took 36 s. At 640 every frame is at most
# 0.23 megapixels, so the tail is bounded by the frame count alone.
PV2_MAXDIM = int(os.environ.get("PDQ_PROBE_MAXDIM", "0"))
# Decode the next frame of a wave on a second thread while this one is being fingerprinted.
# Worth having where threads for HASHING are not: pdqhash holds Python's lock (see
# PV2_WORKERS), but OpenCV lets go of it while it seeks and decodes, so the two genuinely
# overlap. The frames still come back in order, so the evidence cannot change - only when it
# arrives. Off until measured end to end.
PV2_PREFETCH = os.environ.get("PDQ_PROBE_PREFETCH") == "1"
# Decode a wave's frames in ascending time. A wave's MEMBERSHIP is what the spread
# guarantees; the order within it is free, and seeking forward inside each wave keeps the
# backward jumps down to one per wave.
PV2_WAVE_DECODE_SORTED = os.environ.get("PDQ_PROBE_WAVE_UNSORTED") != "1"
# --- where the samples SIT, as against the order they are taken in -----------------------
# The probe has always sampled the whole clip: sample i is taken at (i + 0.5) / n of the
# duration, so 40 samples span 1.2% to 98.8% and the "first 40 frames" story is not what the
# code does. But every position in that grid is a function of n, so raising the count does
# not ADD samples, it MOVES all of them: the 40-sample grid and the 50-sample grid share not
# one moment. That is why 50 measured WORSE than 40 (13 right against 15) - it was not 40
# plus 10, it was a different 40, and it gained two clips and lost four.
#
# Anchored, a sample's position does not mention n at all: sample k sits at
# lo + (hi - lo) * radical_inverse2(k). So the first eight moments are the same eight at any
# sample count, 50 really is 40 plus 10, and a sample id names a moment of the clip rather
# than a slot of whichever grid was in force. See pv2_waves.anchored_fractions.
#
# Off by default until it is measured over the 125 clips, as with every other change here.
# PDQ_PROBE_ANCHORED=0 PDQ_PROBE_PROGRESSIVE=0 PDQ_PROBE_WAVE_ORDER=linear is the engine as
# it was before any of this.
#   grid     - sample i at (i + 0.5) / n. Even, and every position moves when n changes.
#   anchored - sample k at a position that never mentions n. Fixed, but NOT evenly spaced
#              at a count that is not a power of two, and the spacing turns out to matter:
#              measured over the 125 clips, 41 right / 2 wrong against the grid's 46 / 1.
#   nested   - even AND fixed, at the price that the count may only double. 80 samples is
#              the same 40 moments plus the 40 midpoints, so 40 against 80 is the
#              comparison that 40 against 50 could never be.
# "nested" since 17 Oct 2026, and it ships together with PV2_SAMPLES=80 - neither is worth
# having alone. Nested at 40 measures WORSE than the grid at 40 (41 right against 46), because
# moving every sample by about 1% of the clip is itself worth 8 clips either way on a set this
# size. Nested at 80 beats the grid at 40 and beats nested at 40 without losing a single clip,
# which is the comparison that is not luck.
#
# PDQ_PROBE_SAMPLE_MODE=grid PDQ_PROBE_SAMPLES=40 is exactly what shipped before this.
PV2_SAMPLE_MODE = os.environ.get(
    "PDQ_PROBE_SAMPLE_MODE",
    "anchored" if os.environ.get("PDQ_PROBE_ANCHORED") == "1" else "nested")
# True for either fixed-position mode: both take their ids in order, so the wave schedule
# is read literally rather than scaled, and both make sample_i mean a moment of the clip.
PV2_ANCHORED = PV2_SAMPLE_MODE != "grid"
# The count the nesting is built around: 80 and 160 contain these 40 moments, 50 cannot.
PV2_SAMPLE_BASE = int(os.environ.get("PDQ_PROBE_SAMPLE_BASE", "40"))
# Stop opening new waves once the clip has had this long. 0 disables it.
#
# Measured over the 125 real clips at 80 samples: of the 51 clips the probe can identify
# at all, 47 are identified within 15 s and the remaining 4 take up to 97 s. So the last
# 8% of the answers cost more than six times the wait, which is not a trade worth making.
# At 15 s the set takes 12.2 min for 47 right, against 17.5 min for 51 uncapped - and
# against 11.3 min for 46 at the 40 samples this replaced. Better on every count than
# where this started, worst case included.
#
# The cap is checked BETWEEN waves, never inside one, so a wave is always judged on
# complete evidence: a half-sampled wave would hand the rulebook a film-time agreement
# that the full wave might have contradicted.
#
# OFF, because measured at 15 s it does not do what it claims. The last wave is 40 of
# the 80 frames, so a clip sitting at 14 s opens a 40-frame wave and runs straight
# through the cap: 26 of the 125 clips still finished past 15 s, one of them at 168 s,
# which is worse than the 97 s worst case without any cap at all. It cost 3 right
# answers (48 against 51) and saved no time. "Overrun by one wave" is only a small
# overrun when the waves are small, and the last one is not.
#
# Worth revisiting with a finer ladder at the top end - 8, 16, 24, 40, 56, 80 - where
# the cap would have something to bind against. Measure before turning it on.
#
# One other thing the measurement showed: a time cap is LOAD-DEPENDENT. The same 15 s
# cost 13 clips on a machine running something else, against 3 on an idle one, because
# what hits a clock is slow work rather than weak evidence. On a busy pod it would cut
# deepest exactly when the system is most loaded. A cap on FRAMES has no such problem,
# and PV2_SAMPLES already is one.
PV2_BUDGET_S = float(os.environ.get("PDQ_PROBE_BUDGET_S", "0"))
# How far off each end to hold the samples, as a fraction of the clip. Clips open on title
# cards, watermarks and black, and close on credits. The grid's own first sample was half a
# step in - 1.2% at 40 samples - which was never a decision; these are settable so the
# choice can be measured.
PV2_SAMPLE_LO = float(os.environ.get("PDQ_PROBE_SAMPLE_LO", "0.02"))
PV2_SAMPLE_HI = float(os.environ.get("PDQ_PROBE_SAMPLE_HI", "0.98"))
# Refuse a sample landing within this fraction of one already taken. Read
# anchored_fractions before setting it: the positions lie on a dyadic grid, so 0.02 caps the
# usable count at 33 rather than thinning the tail, and the measured smallest gap at 40
# samples is 1.5% of the clip already.
PV2_SAMPLE_MIN_GAP = float(os.environ.get("PDQ_PROBE_SAMPLE_MIN_GAP", "0"))
# Which bars may accept before the last wave. P3.5 is deliberately absent: it turns on being
# the SOLE candidate in the index, so a film that clears it on wave one can stop being sole
# once a later wave finds a rival, and accepting early would answer where the full scan
# refuses. Deferring it to the last wave costs 1% of the frames and closes that hole.
# Measured: --early-tiers all is 48% of frames instead of 49%, with the same answers on this
# set - which is luck, not structure, so the guard stays.
PV2_WAVE_EARLY_TIERS = frozenset(("PV-A", "P1", "PV-B", "PV-E", "PV-C"))

# --- the two passes and the fallback (see the header of two_pass_lab.py) -------------------
# Three stages over three DIFFERENT slices of the spread order, so no frame is sampled twice,
# while every frame already decoded is re-fingerprinted under the later stages' views for the
# cost of the hashing alone.
#
#   1 CROPPED    the centred crops. These carry the matches - 50 of 78 edited clips and 44 of
#                125 real ones accept on them alone, against 28 and 15 for uncropped - so
#                they go first, and most clips never reach stage 2.
#   2 UNCROPPED  the whole frame and its safe-trimmed copy, over fresh frames AND over stage
#                one's, which are already in hand.
#   3 FALLBACK   more frames again, every view, judged by the same bars. Measured on the 125
#                real clips it recovers 12, 12 and 16 of the 94 fall-throughs at 8, 12 and 20
#                frames: MORE FRAMES is what pays here, not looser rules. Looser bars get 17
#                but add a second wrong answer, and shape-only bars are worse (7, 9, 12).
PV2_PASSES = os.environ.get("PDQ_PROBE_PASSES") == "1"
PV2_PASS1_FRAMES = int(os.environ.get("PDQ_PROBE_PASS1", "8"))      # cropped
PV2_PASS2_FRAMES = int(os.environ.get("PDQ_PROBE_PASS2", "12"))     # uncropped
PV2_PASS3_FRAMES = int(os.environ.get("PDQ_PROBE_PASS3", "20"))     # the fallback
# 1.5 s a pass buys about 11 cropped frames for a typical clip and 5 at the ninetieth
# percentile, measured over the 125 real clips at clip-native resolution:
#     python two_pass_lab.py --tag cells --budget 1.5
PV2_CROPPED_GROUPS = ("PORTRAIT", "SQUARE", "LANDSCAPE")
# PDQ_PROBE_PROGRESSIVE=0 with PDQ_PROBE_WAVE_ORDER=linear reproduces the all-at-once probe
# exactly - the escape hatch if any of the above is ever in doubt.

# --- early reject: give up on a clip that is clearly not in the library ---
REJECT_MIN_HASHES = 64     # after 64 fingerprints ...
REJECT_HAMMING = 47        # ... if the best neighbour seen is worse than 47, stop: no match
REJECT_NOEV_MIN_HASHES = 96   # after 96 fingerprints, if the evidence score (3*strong + 2*medium + weak)
REJECT_MIN_EVIDENCE = 4       #     is under 4 and the best hamming is worse than 35, stop: no match
REJECT_EVIDENCE_MINHAM = 35

# --- the orchestrator's wait before it trusts a weak-band exit (Max_spped_up.py) ---
WAIT_P9E_S, WAIT_P9_S, WAIT_P8_S, WAIT_OTHER_35_45_S = 5.0, 8.0, 12.0, 15.0

GROUPS = ("FULL", "PORTRAIT", "LANDSCAPE", "SQUARE")
INDEX_SCHEMA_VERSION = 12   # the pod's shard layout version; the manifest carries it


# =============================================================================================
# 1. SMALL HELPERS shared by the film side and the clip side
# =============================================================================================

def ffmpeg_exe() -> str:
    """The ffmpeg program to run. If the environment variable PDQ_FFMPEG names one, that.
    Else the one bundled with imageio-ffmpeg (nothing to install). Else 'ffmpeg' on the PATH."""
    if os.environ.get("PDQ_FFMPEG"):
        return os.environ["PDQ_FFMPEG"]
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def video_wh_duration(video_path: str) -> Tuple[int, int, float]:
    """Width, height and length in seconds of a video, read with OpenCV (no ffprobe needed)."""
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            raise RuntimeError(f"cannot open video: {video_path}")
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        n = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
        dur = (n / fps) if fps > 0 else 0.0
        return w, h, dur
    finally:
        cap.release()


def _scaled_dims(iw: int, ih: int, maxdim: int) -> Tuple[int, int]:
    """Shrink (iw, ih) so the longest side is maxdim. Even numbers only (ffmpeg likes even)."""
    if maxdim <= 0 or max(iw, ih) <= maxdim:
        ow, oh = iw, ih
    elif iw >= ih:
        ow = maxdim
        oh = int(round(ih * (maxdim / iw)))
    else:
        oh = maxdim
        ow = int(round(iw * (maxdim / ih)))
    ow -= ow % 2
    oh -= oh % 2
    return max(2, ow), max(2, oh)


@dataclass
class DecodedFrame:
    rgb: np.ndarray       # the picture, height x width x 3, red-green-blue
    timestamp: float      # seconds from the start of the video


def iter_frames(video_path: str, fps: float, maxdim: int) -> Iterable[DecodedFrame]:
    """Pull frames out of a video with ffmpeg, `fps` per second, shrunk to `maxdim`.

    This is the pod's iter_frames_ffmpeg_fast: the same ffmpeg filter ("fps=..,scale=..")
    and the same timestamps (frame i is at i / fps seconds). Frames come out one at a time
    as raw pixels, so nothing big is held in memory."""
    iw, ih, _ = video_wh_duration(video_path)
    ow, oh = _scaled_dims(iw, ih, maxdim)
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin",
           "-an", "-sn", "-dn", "-vsync", "0",
           "-i", str(video_path),
           "-vf", f"fps={fps},scale={ow}:{oh}",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-threads", str(min(8, os.cpu_count() or 8)),
           "-"]
    frame_bytes = ow * oh * 3
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=frame_bytes * 4)
    assert proc.stdout is not None
    buf = bytearray(frame_bytes)
    mv = memoryview(buf)
    i = 0
    try:
        while True:
            n = proc.stdout.readinto(mv)
            if n != frame_bytes:
                break
            rgb = np.frombuffer(mv, dtype=np.uint8).reshape((oh, ow, 3)).copy()
            yield DecodedFrame(rgb=rgb, timestamp=i / float(fps))
            i += 1
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        proc.wait(timeout=10)


def downsample_gray(frame_rgb: np.ndarray, out: int = 32) -> np.ndarray:
    """A tiny 32x32 grey copy of a frame. Used only to ask 'did the picture change?'"""
    f = frame_rgb.astype(np.float32)
    g = 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]
    h, w = g.shape
    sh, sw = h // out, w // out
    if sh < 1 or sw < 1:
        return g[:out, :out]
    g = g[: sh * out, : sw * out]
    return g.reshape(out, sh, out, sw).mean(axis=(1, 3))


def frame_change_score(prev_gray: np.ndarray, cur_gray: np.ndarray) -> float:
    """How much two tiny grey frames differ, on average. Bigger means more change."""
    return float(np.mean(np.abs(cur_gray - prev_gray)))


@dataclass(frozen=True)
class CropSpec:
    name: str     # like "9x16_s0.85"
    ar_w: int     # the shape, as width : height
    ar_h: int
    scale: float  # 1.0 = as big as fits, 0.85 = a bit tighter


def center_crop_aspect(frame: np.ndarray, ar_w: int, ar_h: int, scale: float = 1.0) -> np.ndarray:
    """Cut the biggest centred rectangle of shape ar_w:ar_h out of the frame, then shrink
    that rectangle by `scale`. This is how a TikTok creator crops a film."""
    h, w, _ = frame.shape
    w0 = max(2, int(round(w * scale)))
    h0 = max(2, int(round(h * scale)))
    r = ar_w / ar_h
    if (w0 / h0) >= r:
        crop_h = h0
        crop_w = int(round(crop_h * r))
    else:
        crop_w = w0
        crop_h = int(round(crop_w / r))
    crop_w = min(crop_w, w)
    crop_h = min(crop_h, h)
    x0 = (w - crop_w) // 2
    y0 = (h - crop_h) // 2
    return frame[y0:y0 + crop_h, x0:x0 + crop_w, :]


def default_tiktokish_crops() -> List[CropSpec]:
    """The eight crops the pod makes from every frame: four shapes at two sizes."""
    specs: List[CropSpec] = []
    for scale in (1.0, 0.85):
        specs += [
            CropSpec(f"1x1_s{scale}", 1, 1, scale),
            CropSpec(f"4x5_s{scale}", 4, 5, scale),
            CropSpec(f"9x16_s{scale}", 9, 16, scale),
            CropSpec(f"16x9_s{scale}", 16, 9, scale),
        ]
    return specs


CROPS = default_tiktokish_crops()


def group_for_crop_name(name: str) -> str:
    """Which family a crop belongs to. The index keeps one search file per family."""
    if name == "full" or name.startswith("full_dihedral"):
        return "FULL"
    if name.startswith("9x16") or name.startswith("4x5"):
        return "PORTRAIT"
    if name.startswith("16x9"):
        return "LANDSCAPE"
    if name.startswith("1x1"):
        return "SQUARE"
    return "FULL"


def infer_query_group_from_wh(w: int, h: int) -> str:
    """Tall clip, wide clip, or square clip. Decides which families are searched."""
    if h > w * 1.15:
        return "PORTRAIT"
    if w > h * 1.15:
        return "LANDSCAPE"
    return "SQUARE"


def groups_for_clip_shape(query_group: str) -> List[str]:
    """The pod searches FULL plus the family that matches the clip's shape, plus SQUARE."""
    if query_group == "PORTRAIT":
        return ["FULL", "PORTRAIT", "SQUARE"]
    if query_group == "LANDSCAPE":
        return ["FULL", "LANDSCAPE", "SQUARE"]
    return ["FULL", "SQUARE"]


def probe_group_for(query_group: str) -> str:
    """The one crop family the probe (rule P0) watches: PORTRAIT for a tall clip, SQUARE for a
    square one, FULL for a wide one."""
    return {"PORTRAIT": "PORTRAIT", "SQUARE": "SQUARE"}.get(query_group, "FULL")


def pdq_hash(img: np.ndarray) -> Tuple[bytes, int]:
    """Fingerprint one picture. Returns (32 bytes, quality score 0-100)."""
    if img.ndim == 2:
        img = np.stack([img, img, img], axis=2)
    elif img.ndim == 3 and img.shape[2] >= 4:
        img = img[:, :, :3]
    hv, q = pdqhash.compute(np.ascontiguousarray(img, dtype=np.uint8))
    arr = np.asarray(hv)
    if arr.size == 256:                       # 256 bits -> pack into 32 bytes
        hb = np.packbits(arr.astype(np.uint8), bitorder="big").tobytes()
    elif arr.size == 32:
        hb = arr.astype(np.uint8).tobytes()
    else:
        raise ValueError(f"unexpected pdqhash output size {arr.size}")
    return hb, int(q)


# The eight slots pdqhash.compute_dihedral fills, in its order. Measured on 36 real clip frames
# against hashing the transformed PIXELS with compute():
#
#     slot        is the hash of              mean / max bits apart
#     ORIG        the picture itself          0 / 0   (bit-identical to compute)
#     ROT90       np.rot90(img, 1)            3.4 / 16
#     ROT180      np.rot90(img, 2)            6.7 / 18
#     ROT270      np.rot90(img, 3)            2.7 / 16
#     MIRROR      img[:, ::-1], the repost    3.4 / 16
#                 mirror (pdqhash calls this slot FlipY)
#
# The few bits apart are the downscaling filter, which is not quite symmetric, so a dihedral
# mirror is a slightly different fingerprint of the same picture rather than a copy of the
# pixel mirror's. Whether that matters against the INDEX is measured, not assumed - see
# PV2_MIRROR.
DIH_ORIG, DIH_ROT90, DIH_ROT180, DIH_ROT270, DIH_FLIPX, DIH_MIRROR = 0, 1, 2, 3, 4, 5


def pdq_hash_dihedral(img: np.ndarray) -> Tuple[List[bytes], int]:
    """All eight dihedral fingerprints of one picture, for the price of one.

    PDQ's expensive part is shrinking the picture to 64x64. The eight rotations and
    reflections are then just sign flips and transposes of the same 16x16 DCT, so
    compute_dihedral costs what compute does - measured 18.8 ms against 18.3 ms per real clip
    frame. Returns ([32 bytes x 8] in the DIH_* order, quality)."""
    if img.ndim == 2:
        img = np.stack([img, img, img], axis=2)
    elif img.ndim == 3 and img.shape[2] >= 4:
        img = img[:, :, :3]
    hvs, q = pdqhash.compute_dihedral(np.ascontiguousarray(img, dtype=np.uint8))
    return [np.packbits(np.asarray(h).astype(np.uint8), bitorder="big").tobytes()
            for h in hvs], int(q)


def active_region(img: np.ndarray, dark: int = 26, min_keep: float = 0.94, min_px: int = 64) -> Optional[np.ndarray]:
    """The picture inside letterbox/pillarbox bars, or None when there are no bars.

    A simple version of the pod's 'active region crop', the speed trick the laptop port
    left out - and the reason letterboxed clips scored 1 of 8 in the edit test. A row or
    column counts as bars when nothing in it rises above near-black. Only returns a crop
    when the bars are real (the picture is under min_keep of the frame in some direction),
    so ordinary clips cost nothing extra."""
    g = img.max(axis=2) if img.ndim == 3 else img
    rows = np.where((g > dark).any(axis=1))[0]
    cols = np.where((g > dark).any(axis=0))[0]
    if len(rows) < min_px or len(cols) < min_px:
        return None
    y0, y1, x0, x1 = int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1
    h, w = g.shape
    if (y1 - y0) >= h * min_keep and (x1 - x0) >= w * min_keep:
        return None
    return img[y0:y1, x0:x1]


# TRIED AND REMOVED, 23 Oct 2026: a stronger band finder for the "film in a band, captions in
# the bars above and below" format. The suspicion was that caption text defeats active_region
# (it needs every pixel of a bar row near black) and that this is why 13 held-out clips whose
# film IS indexed found no candidate at all. Measured, it is not: active_region finds the band
# on 11 of the 13 anyway. The evidence that the film side is at fault: the probe's own 160
# frames, about 20 pictures each, returned nothing under 45 for these clips; and searching 16
# frames per clip EXHAUSTIVELY against only the true film's ~100k fingerprints, every view
# and mirror, gave 60-94 bits on 11 of the 13 (unrelated pictures sit around 80-100). The
# indexed copy does not hold these pictures - another source or edition, or a wrong label -
# and no view of the clip changes that. oracle_distance.py measures it per clip; the fix is
# on the film side.


def safe_trim_view(img: np.ndarray, top=0.06, bottom=0.14, side=0.03) -> Optional[np.ndarray]:
    """The frame with a thin border shaved off: 6% top, 14% bottom, 3% each side. TikTok
    puts captions and buttons there. The pod hashes this extra view for the first 40 kept
    frames of a clip."""
    h, w = img.shape[:2]
    y0, y1 = int(h * top), int(h * (1.0 - bottom))
    x0, x1 = int(w * side), int(w * (1.0 - side))
    if (y1 - y0) < 32 or (x1 - x0) < 32:
        return None
    return img[y0:y1, x0:x1]


# =============================================================================================
# 2. THE FILM SIDE: turn a film file into a fingerprint "payload" (the same dict the pod
#    stores in B2 as movie_<id>.blob), and read such a blob back.
# =============================================================================================

def fingerprint_video(video_path: str, *, fps: float = FILM_FPS, decode_fps: float = FILM_DECODE_FPS,
                      maxdim: int = FILM_MAXDIM, quality_min: int = FILM_QUALITY_MIN,
                      change_thresh: float = FILM_CHANGE_THRESH, progress=None) -> dict:
    """Fingerprint a whole film the way the pod does (PDQMultiCropIndex.add_video).

    For every second of the film: decode 8 frames, score how much each changed, keep the
    3 that changed most (or just 1 if the second was static). For each kept frame make
    the full-frame fingerprint plus the 8 crops. Keep fingerprints with quality >= 40.

    Returns the payload dict:
      {"version": 1, "video_path": ..., "crop_vocab": [names], "groups": {GROUP: {
           "hashes32": bytes (N*32), "ts_f32": bytes (N*4), "crop_id_u16": bytes (N*2)}}}
    """
    crop_vocab: List[str] = ["full"] + [c.name for c in CROPS]
    crop_id = {n: i for i, n in enumerate(crop_vocab)}
    hashes: Dict[str, bytearray] = {}
    tss: Dict[str, array] = {}
    cids: Dict[str, array] = {}
    max_keep_per_sec = max(1, int(round(fps)))

    def _add(hb: bytes, q: int, ts: float, crop_name: str):
        if q < quality_min:
            return
        g = group_for_crop_name(crop_name)
        if g not in hashes:
            hashes[g], tss[g], cids[g] = bytearray(), array("f"), array("H")
        hashes[g].extend(hb)
        tss[g].append(float(ts))
        cids[g].append(crop_id[crop_name])

    def _process_second(frames: List[Tuple[float, float, np.ndarray]]):
        """frames = [(change score, timestamp, picture), ...] for one second of film."""
        if not frames:
            return
        max_score = max(s for s, _, _ in frames)
        if max_score >= change_thresh:
            chosen = sorted(frames, key=lambda x: x[0], reverse=True)[:max_keep_per_sec]
        else:
            chosen = [max(frames, key=lambda x: x[0])]   # a static second: one frame is enough
        chosen.sort(key=lambda x: x[1])
        for _score, ts, frame in chosen:
            hb, q = pdq_hash(frame)
            _add(hb, q, ts, "full")
            for spec in CROPS:
                hb, q = pdq_hash(center_crop_aspect(frame, spec.ar_w, spec.ar_h, spec.scale))
                _add(hb, q, ts, spec.name)

    prev_small = None
    bucket: List[Tuple[float, float, np.ndarray]] = []
    cur_sec = None
    n_dec = 0
    for fr in iter_frames(video_path, fps=decode_fps, maxdim=maxdim):
        n_dec += 1
        if progress and n_dec % 80 == 0:
            progress(fr.timestamp)
        small = downsample_gray(fr.rgb, 32)
        score = 0.0 if prev_small is None else frame_change_score(prev_small, small)
        prev_small = small
        sec = int(fr.timestamp)
        if cur_sec is None:
            cur_sec = sec
        if sec != cur_sec:
            _process_second(bucket)
            bucket = []
            cur_sec = sec
        bucket.append((score, fr.timestamp, fr.rgb))
    _process_second(bucket)

    return {
        "version": 1,
        "video_path": str(video_path),
        "crop_vocab": crop_vocab,
        "groups": {g: {"hashes32": bytes(hashes[g]), "ts_f32": tss[g].tobytes(),
                       "crop_id_u16": cids[g].tobytes()} for g in hashes},
    }


def encode_blob(payload: dict) -> bytes:
    """Pack a payload the way the pod stores it: pickle, then zlib."""
    return zlib.compress(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL), 3)


_ZLIB_HEADS = {(0x78, 0x01), (0x78, 0x5E), (0x78, 0x9C), (0x78, 0xDA)}


def decode_blob(blob: bytes) -> dict:
    """Read a movie_<id>.blob from B2 (or from encode_blob) back into the payload dict."""
    if len(blob) >= 2 and (blob[0], blob[1]) in _ZLIB_HEADS:
        blob = zlib.decompress(blob)
    payload = pickle.loads(blob)
    if not isinstance(payload, dict) or "groups" not in payload:
        raise ValueError("this is not a PDQ fingerprint blob")
    return payload


def payload_arrays(payload: dict) -> Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """The payload as numpy arrays per group: (hashes uint8[N,32], ts float32[N], crop uint16[N]).
    The pod's blobs are all crop_id_u16; very old ones were u1 (one byte). Both are handled."""
    out = {}
    for g, d in payload["groups"].items():
        h = np.frombuffer(d["hashes32"], dtype=np.uint8).reshape(-1, 32)
        ts = np.frombuffer(d["ts_f32"], dtype="<f4")
        if "crop_id_u16" in d:
            cr = np.frombuffer(d["crop_id_u16"], dtype="<u2")
        else:
            cr = np.frombuffer(d.get("crop_id_u1", b""), dtype=np.uint8).astype("<u2")
        n = min(len(h), len(ts), len(cr)) if len(cr) else min(len(h), len(ts))
        out[g] = (h[:n], ts[:n], (cr[:n] if len(cr) else np.zeros(n, dtype="<u2")))
    return out


# =============================================================================================
# 3. THE INDEX: the pod's shard layout, flat form. One folder holds:
#      manifest.json                    which films, which files, the settings
#      faiss_<GROUP>.index              the fingerprints of that group (IndexBinaryFlat)
#      meta_vid_<GROUP>.bin             for each fingerprint: which film (vidx), uint64
#      meta_ts_<GROUP>.bin              for each fingerprint: film time in seconds, float32
#      meta_crop_<GROUP>.bin            for each fingerprint: which crop, uint16
#      index_contents.txt               the films, one per line, for humans
# =============================================================================================

def make_label(movie_id: int, title: str, tmdb_id) -> str:
    """The pod's label for a film: '3112:Interstellar (tmdb=157336)'."""
    return f"{int(movie_id)}:{title} (tmdb={tmdb_id})"


def write_index(index_dir: str, films: Iterable[Tuple[str, dict]], params: Optional[dict] = None) -> dict:
    """Build the index folder from films = [(label, payload), ...].

    Films are numbered in the order given; that number is the vidx stored in meta_vid.
    Returns the manifest. Everything is written to a temp folder and renamed at the end,
    so a crash half-way leaves no half-built index behind."""
    index_dir = Path(index_dir)
    tmp = index_dir.with_name(index_dir.name + ".building")
    if tmp.exists():
        import shutil
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    idx_by_group: Dict[str, "faiss.IndexBinaryFlat"] = {}
    vid_by_group: Dict[str, array] = {}
    ts_by_group: Dict[str, array] = {}
    crop_by_group: Dict[str, array] = {}
    video_paths: List[str] = []
    crop_vocab: List[str] = []
    counts: List[int] = []

    for label, payload in films:
        vidx = len(video_paths)
        video_paths.append(label)
        if not crop_vocab:
            crop_vocab = list(payload.get("crop_vocab") or [])
        n_film = 0
        for g, (h, ts, cr) in payload_arrays(payload).items():
            if len(h) == 0:
                continue
            if g not in idx_by_group:
                idx_by_group[g] = faiss.IndexBinaryFlat(256)
                vid_by_group[g], ts_by_group[g], crop_by_group[g] = array("Q"), array("f"), array("H")
            idx_by_group[g].add(np.ascontiguousarray(h))
            vid_by_group[g].extend([vidx] * len(h))
            ts_by_group[g].frombytes(np.asarray(ts, dtype="<f4").tobytes())
            crop_by_group[g].frombytes(np.asarray(cr, dtype="<u2").tobytes())
            n_film += len(h)
        counts.append(n_film)

    groups_manifest = {}
    for g, idx in idx_by_group.items():
        faiss.write_index_binary(idx, str(tmp / f"faiss_{g}.index"))
        (tmp / f"meta_vid_{g}.bin").write_bytes(vid_by_group[g].tobytes())
        (tmp / f"meta_ts_{g}.bin").write_bytes(ts_by_group[g].tobytes())
        (tmp / f"meta_crop_{g}.bin").write_bytes(crop_by_group[g].tobytes())
        groups_manifest[g] = {"faiss": f"faiss_{g}.index", "meta_vid": f"meta_vid_{g}.bin",
                              "meta_ts": f"meta_ts_{g}.bin", "meta_crop": f"meta_crop_{g}.bin",
                              "faiss_kind": "binary", "n": int(idx.ntotal)}

    manifest = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "created_at_unix": int(time.time()),
        "params": params or {"fps": FILM_FPS, "maxdim": FILM_MAXDIM, "quality_min": FILM_QUALITY_MIN,
                             "schema": INDEX_SCHEMA_VERSION, "index_form": "flat (memory-mappable)"},
        "movies_count": len(video_paths),
        "hashes_total": int(sum(counts)),
        "video_paths": video_paths,
        "crop_vocab": crop_vocab,
        "groups": groups_manifest,
    }
    (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    with open(tmp / "index_contents.txt", "w", encoding="utf-8") as f:
        f.write("# The films inside this index, one per line: vidx | label | fingerprints\n")
        for i, (lab, n) in enumerate(zip(video_paths, counts)):
            f.write(f"{i}\t{lab}\t{n}\n")

    if index_dir.exists():
        import shutil
        shutil.rmtree(index_dir)
    tmp.rename(index_dir)
    return manifest


@dataclass
class LoadedIndex:
    dir: str
    manifest: dict
    video_paths: List[str]
    index_by_group: Dict[str, "faiss.IndexBinaryFlat"]   # memory-mapped
    meta_vid: Dict[str, np.ndarray]                       # memory-mapped uint64
    meta_ts: Dict[str, np.ndarray]                        # memory-mapped float32

    def label(self, vidx: int) -> str:
        return self.video_paths[int(vidx)] if 0 <= int(vidx) < len(self.video_paths) else f"movie_{vidx}"


# --- the live pod's index, which is laid out differently ------------------------------------
# Our own index is one folder: a manifest naming four flat shards and their meta arrays, and a
# list of films that the per-row film number indexes into. The pod's is three separate things:
#
#   /local_index/ivf/ivf_<GROUP>.index    the searchable part, IVF rather than flat
#   /local_index/rtmeta/rt_meta_*_<GROUP>__<hash>.bin   row -> film number, row -> film time
#   /workspace/pdq_cache_flat_v2/shards/*/manifest.json each shard's own list of films
#
# The film list is the fiddly one. Each shard names the films it holds, a film can appear in
# several shards, and the per-row number is a position in the DEDUPLICATED list taken in shard
# order. 2,662 shards give 23,534 distinct films, and the index built on 18 Oct uses the first
# 22,997 of them - it is a snapshot, and films have been added since.
#
# Reading 2,662 small files takes about half a minute, so the list is cached. The cache lives
# where the testing folder is, never beside the live index.
PV2_POD_NPROBE = int(os.environ.get("PDQ_IVF_NPROBE", "16"))
PV2_POD_FILMS_CACHE = os.environ.get(
    "PDQ_POD_FILMS_CACHE", "/workspace/nada_pdq_testing_DO_NOT_DELETE/film_list.json")
PV2_POD_SHARDS = os.environ.get("PDQ_POD_SHARDS", "/workspace/pdq_cache_flat_v2")


def _is_pod_index(d: str) -> bool:
    """Does this folder hold the pod's index rather than one of ours?"""
    return (Path(d, "ivf").is_dir() and Path(d, "rtmeta").is_dir()
            and not Path(d, "manifest.json").is_file())


def _pod_film_list(shards_root: str = None, cache: str = None) -> List[str]:
    """Every film the pod's index knows, in the order its row numbers count in.

    Deduplicated by the film id that each label starts with, keeping first appearance, taken
    over the shards in the order the root manifest lists them. That order is what the per-row
    numbers mean, so it must not be sorted or re-grouped."""
    shards_root = shards_root or PV2_POD_SHARDS
    cache = cache or PV2_POD_FILMS_CACHE
    if cache and os.path.isfile(cache):
        try:
            films = json.loads(Path(cache).read_text(encoding="utf-8"))
            if isinstance(films, list) and films:
                return films
        except Exception:
            pass        # a damaged cache is rebuilt, never trusted

    root = json.loads(Path(shards_root, "root_manifest.json").read_text(encoding="utf-8"))
    seen, films = set(), []
    for sh in root.get("shards", []):
        mp = Path(shards_root, "shards", sh["name"], "manifest.json")
        if not mp.is_file():
            continue
        for label in (json.loads(mp.read_text(encoding="utf-8")).get("video_paths") or []):
            fid = label.split(":", 1)[0]
            if fid not in seen:
                seen.add(fid)
                films.append(label)
    if cache:
        try:
            Path(cache).parent.mkdir(parents=True, exist_ok=True)
            Path(cache).write_text(json.dumps(films), encoding="utf-8")
        except Exception:
            pass        # a cache we cannot write is a slow start, not a failure
    return films


def _load_pod_index(index_dir: str) -> LoadedIndex:
    """Open the live pod index, read-only and without copying it into memory.

    IO_FLAG_MMAP_IFC is the zero-copy map, measured: opening the 9.7 GB FULL group leaves
    this process holding 0.04 GB. The older IO_FLAG_MMAP reads a binary index into RAM, which
    on a machine serving users is exactly what not to do.

    The meta arrays are LONGER than the index they describe - 272.5 million rows against
    261.5 million for FULL - because they keep being appended to while the index is a
    snapshot. Only the first ntotal rows belong to it, so they are cut to length here. Reading
    past that would hand back a film for a row the index cannot return."""
    idx: Dict[str, object] = {}
    vid: Dict[str, np.ndarray] = {}
    ts: Dict[str, np.ndarray] = {}
    total = 0
    for path in sorted(Path(index_dir, "ivf").glob("ivf_*.index")):
        g = path.stem.replace("ivf_", "")
        flags = int(getattr(faiss, "IO_FLAG_MMAP_IFC", 0)) | int(getattr(faiss, "IO_FLAG_READ_ONLY", 0))
        shard = faiss.read_index_binary(str(path), flags)
        if hasattr(shard, "nprobe"):
            # How many clusters a lookup opens. This is the speed/thoroughness dial an IVF
            # index has and a flat one does not: our own index compares against everything.
            shard.nprobe = PV2_POD_NPROBE
        n = int(shard.ntotal)
        mv = sorted(Path(index_dir, "rtmeta").glob("rt_meta_vid_%s__*.bin" % g))
        mt = sorted(Path(index_dir, "rtmeta").glob("rt_meta_ts_%s__*.bin" % g))
        if not (n and mv and mt):
            continue
        idx[g] = shard
        vid[g] = np.memmap(str(mv[0]), dtype="<i8", mode="r")[:n]
        ts[g] = np.memmap(str(mt[0]), dtype="<f4", mode="r")[:n]
        total += n

    films = _pod_film_list()
    manifest = {"schema_version": INDEX_SCHEMA_VERSION, "movies_count": len(films),
                "hashes_total": total, "groups": {g: {} for g in idx},
                "source": "pod", "nprobe": PV2_POD_NPROBE}
    return LoadedIndex(dir=index_dir, manifest=manifest, video_paths=films,
                       index_by_group=idx, meta_vid=vid, meta_ts=ts)


def load_index(index_dir: str) -> LoadedIndex:
    """Open an index folder. Nothing big is read into memory: the search files and the
    meta arrays are memory-mapped, so the operating system pages in what a search touches
    and lets go of it again when memory is short. A 2 GB index opens in well under a
    second, and the program's own memory stays around 50 MB."""
    index_dir = os.environ.get("PDQ_INDEX_DIR") or str(index_dir)
    if _is_pod_index(index_dir):
        # The live pod index: different layout, same LoadedIndex out the other side,
        # so every harness that calls this keeps working unchanged.
        return _load_pod_index(index_dir)
    manifest = json.loads(Path(index_dir, "manifest.json").read_text(encoding="utf-8"))
    if int(manifest.get("schema_version", 0)) != INDEX_SCHEMA_VERSION:
        raise RuntimeError("index layout version does not match; rebuild it with 2_build_index.py")
    idx, vid, ts = {}, {}, {}
    for g, files in manifest["groups"].items():
        # IO_FLAG_MMAP_IFC is FAISS's zero-copy map: the file is not read into memory, the
        # operating system pages it in as the search sweeps it, and drops pages when RAM is
        # short. (The older IO_FLAG_MMAP flag silently reads a binary index into RAM.)
        idx[g] = faiss.read_index_binary(str(Path(index_dir, files["faiss"])), faiss.IO_FLAG_MMAP_IFC | faiss.IO_FLAG_READ_ONLY)
        vid[g] = np.memmap(str(Path(index_dir, files["meta_vid"])), dtype="<u8", mode="r")
        ts[g] = np.memmap(str(Path(index_dir, files["meta_ts"])), dtype="<f4", mode="r")
    return LoadedIndex(dir=index_dir, manifest=manifest, video_paths=list(manifest["video_paths"]),
                       index_by_group=idx, meta_vid=vid, meta_ts=ts)


# =============================================================================================
# 4. THE CLIP SIDE: fingerprint a clip, search, count, apply the rules, print like the pod.
# =============================================================================================

def _new_stats() -> dict:
    """One film's scorecard (PDQ_BASICS.md section 4). Filled in as neighbours arrive."""
    return {
        "total_frames": 0, "dist_sum": 0.0, "dist_cnt": 0, "avg_ham": 999.0, "min_hamming": float("inf"),
        "frames_0_8": 0, "frames_0_20": 0, "frames_20_25": 0, "frames_20_35": 0,
        "frames_35_40": 0, "frames_35_45": 0,
        "offset_buckets_0_20": defaultdict(int), "offset_buckets_20_25": defaultdict(int),
        "offset_buckets_20_35": defaultdict(int), "offset_buckets_35_40": defaultdict(int),
        "offset_buckets_35_45": defaultdict(int),
        "query_buckets_0_20": defaultdict(int), "query_buckets_20_25": defaultdict(int),
        "query_buckets_20_35": defaultdict(int), "query_buckets_35_45": defaultdict(int),
        "offset_qsecs_0_20": defaultdict(lambda: defaultdict(int)),
        "offset_qsecs_20_35": defaultdict(lambda: defaultdict(int)),
        "best_0_20_count": 0, "best_0_20_center": -1,
    }


def _update_stats(movie_stats: dict, touched: set, D: np.ndarray, I: np.ndarray,
                  meta_vid: np.ndarray, meta_ts: np.ndarray, q_ts: float, hist: dict) -> None:
    """Add one batch of search results to the scorecards. This is the pod's _do_stats_update.

    D, I come from FAISS: for each clip fingerprint, the distances and positions of its
    64 nearest film fingerprints. Every neighbour under 45 counts as one "matched frame"
    for its film (yes: one clip fingerprint can add several matches to one film if several
    of that film's frames are close to it). The offset is film time minus clip time."""
    valid = (D < HAMMING_CUTOFF_EXCL) & (I >= 0)
    if not valid.any():
        return
    d = D[valid].astype(np.float64)
    j = I[valid].astype(np.int64)
    inb = (j >= 0) & (j < len(meta_vid))
    d, j = d[inb], j[inb]
    if len(j) == 0:
        return
    mids = np.asarray(meta_vid[j]).astype(np.int64)
    offs = np.asarray(meta_ts[j]).astype(np.float64) - q_ts
    bi = np.round(offs / OFFSET_BUCKET_S).astype(np.int64)
    qsec = int(q_ts)
    for mid in np.unique(mids).tolist():
        touched.add(int(mid))
        sel = mids == mid
        ds, bis = d[sel], bi[sel]
        st = movie_stats[int(mid)]
        n = len(ds)
        st["total_frames"] += n
        st["dist_sum"] += float(ds.sum())
        st["dist_cnt"] += n
        st["avg_ham"] = st["dist_sum"] / max(st["dist_cnt"], 1)
        md = float(ds.min())
        if md < st["min_hamming"]:
            st["min_hamming"] = md
        # the histogram of offsets, used to report where in the film the clip sits
        hb = hist[int(mid)]
        for b in bis.tolist():
            hb[float(b) * OFFSET_BUCKET_S] += 1
        lo, mr, hi = ds <= RANGE_LOW, (ds > RANGE_LOW) & (ds <= RANGE_MID), (ds > RANGE_MID) & (ds < HAMMING_CUTOFF_EXCL)
        if lo.any():
            st["frames_0_20"] += int(lo.sum())
            for b in bis[lo].tolist():
                st["offset_buckets_0_20"][b] += 1
                c = st["offset_buckets_0_20"][b]
                if c > st["best_0_20_count"]:
                    st["best_0_20_count"], st["best_0_20_center"] = c, b
                st["offset_qsecs_0_20"][b][qsec] += 1
            st["query_buckets_0_20"][qsec] += int(lo.sum())
            st["frames_0_8"] += int((ds[lo] <= 8.0).sum())
        if mr.any():
            st["frames_20_35"] += int(mr.sum())
            for b in bis[mr].tolist():
                st["offset_buckets_20_35"][b] += 1
                st["offset_qsecs_20_35"][b][qsec] += 1
            st["query_buckets_20_35"][qsec] += int(mr.sum())
            lo25 = ds[mr] <= 25.0
            if lo25.any():
                st["frames_20_25"] += int(lo25.sum())
                for b in bis[mr][lo25].tolist():
                    st["offset_buckets_20_25"][b] += 1
                st["query_buckets_20_25"][qsec] += int(lo25.sum())
        if hi.any():
            st["frames_35_45"] += int(hi.sum())
            # Distances above 40 may be passed to the other detectives as hints,
            # but must not make PDQ answer on its own (policy since 6 Aug 2026).
            st["frames_35_40"] += int((ds[hi] <= 40.0).sum())
            decision_weak = hi & (ds <= 40.0)
            for b in bis[decision_weak].tolist():
                st["offset_buckets_35_40"][b] += 1
            for b in bis[hi].tolist():
                st["offset_buckets_35_45"][b] += 1
            st["query_buckets_35_45"][qsec] += int(hi.sum())


def _bucket_span_seconds(bucket_dict: dict) -> float:
    """How far apart the earliest and latest film-time buckets are, in seconds."""
    if not bucket_dict:
        return float("inf")
    keys = list(bucket_dict.keys())
    return (max(keys) - min(keys)) * OFFSET_BUCKET_S


def _offsets_clustered(bucket_dict: dict, max_span_s: float) -> bool:
    """Do all the matched frames line up in the film (within max_span_s seconds)?"""
    return _bucket_span_seconds(bucket_dict) <= max_span_s


def _unique_time_clusters(secs: list, threshold_s: float) -> int:
    """How many separate moments of the clip these seconds represent (gaps > threshold split them)."""
    if not secs:
        return 0
    secs = sorted(secs)
    clusters = 1
    for i in range(1, len(secs)):
        if abs(secs[i] - secs[i - 1]) > threshold_s:
            clusters += 1
    return clusters


def _p9_min_frames(avg_ham: float) -> int:
    """P9's floor climbs as the average gets closer to the 45 cutoff (a lone weak match near 45 is noise)."""
    if avg_ham <= P9_HAM_LOOSE:
        return P9_MINF_LOOSE
    if avg_ham <= P9_HAM_TIGHT:
        return P9_MINF_TIGHT
    return P9_MINF_CUTOFF


def check_early_exit(movie_id: int, st: dict) -> Optional[dict]:
    """THE RULEBOOK, checked for one film's scorecard. Returns the first rule that fires,
    as {"movie_id", "reason", "priority", "immediate", "avg_hamming"}, or None.

    This is the pod's _check_early_exit, rule for rule, in the pod's order. The reason
    strings are the pod's own, so the printout reads the same. PDQ_BASICS.md section 6
    explains each rule in plain words."""
    min_ham = float(st["min_hamming"])
    total = int(st["total_frames"])
    f0_8, f0_20, f20_35 = int(st["frames_0_8"]), int(st["frames_0_20"]), int(st["frames_20_35"])
    f35_40 = int(st.get("frames_35_40", 0))
    avg = float(st["avg_ham"])
    r = lambda reason, prio, immediate=True: {"movie_id": movie_id, "reason": reason, "priority": prio,
                                              "immediate": immediate, "avg_hamming": avg}

    # P1: one near-perfect frame plus two more frames
    if min_ham < MIN_HAMMING_ULTRA and total >= MIN_HAMMING_FRAMES:
        return r(f"P1: min_hamming={min_ham:.1f} < 15 with {total} frames", 1)
    # P2: one frame is practically identical
    if min_ham <= RANGE_ULTRA_LOW and total >= 1:
        return r(f"P2: min_hamming={min_ham:.1f} ≤ 5", 2)
    # P2.5: two independent near-perfect frames
    if min_ham <= 8.0 and f0_8 >= 2:
        return r(f"P2.5: min_hamming={min_ham:.1f} ≤ 8 with {f0_8} frames in 0-8", 2)
    # P3: many strong frames
    if f0_20 >= FRAMES_ULTRA_CONFIDENT:
        return r(f"P3: {f0_20} frames in 0-20 (≥{FRAMES_ULTRA_CONFIDENT})", 3)
    # P4 / P5 / P5x: fewer strong frames, but they line up in the film
    if f0_20 >= FRAMES_LOW_CONFIDENT:
        b0 = st["offset_buckets_0_20"]
        if b0:
            center = int(st["best_0_20_center"])
            if center < 0 or center not in b0:
                center = max(b0, key=b0.get)
            span = int(round(OFFSET_CLUSTER_MAX_SPAN_S / OFFSET_BUCKET_S))
            cluster_keys = [b for b in b0 if abs(int(b) - center) <= span]
            cluster_hits = int(sum(b0[b] for b in cluster_keys))
            if cluster_hits >= FRAMES_LOW_CONFIDENT:
                b1 = st["offset_buckets_20_35"]
                best1 = int(max(b1.values())) if b1 else 0
                if cluster_hits >= FRAMES_CROSS_STRONG_0_20 and best1 >= FRAMES_CROSS_MED_20_35:
                    return r(f"P5x: cross evidence 0-20_cluster={cluster_hits} + 20-35_best_bucket={best1}", 5)
                qsecs = []
                for b in cluster_keys:
                    qsecs.extend(list(st["offset_qsecs_0_20"].get(b, {}).keys()))
                if _unique_time_clusters(qsecs, TIMESTAMP_UNIQUE_THRESHOLD_S) >= 2:
                    return r(f"P4: {cluster_hits} hits in 0-20 within one alignment cluster + diverse query times", 4)
                return r(f"P5: {cluster_hits} hits in 0-20 within one alignment cluster (pending)", 5, immediate=False)
    # P6: many medium frames (the caller skips it when another film also sits in 0-35).
    # The candidate's evidence as a whole must also remain medium-quality; otherwise
    # a small number of medium neighbours can promote a much larger weak look-alike.
    if f20_35 >= FRAMES_MID_CONFIDENT and avg <= RANGE_MID:
        return r(f"P6: {f20_35} frames in 20-35 (≥{FRAMES_MID_CONFIDENT})", 6)
    # P6a: medium-good frames (20-25) that line up in the film
    if int(st["frames_20_25"]) >= FRAMES_MIDLOW_CONFIDENT:
        b25 = st["offset_buckets_20_25"]
        if b25 and _offsets_clustered(b25, OFFSET_CLUSTER_MAX_SPAN_S):
            best25 = int(max(b25.values()))
            if best25 >= FRAMES_MIDLOW_CONFIDENT:
                return r(f"P6a: 20-25 stable offset (best_bucket={best25})", 7)
    # P7: medium frames that line up in the film AND come from several moments of the clip
    if f20_35 > 0:
        b1 = st["offset_buckets_20_35"]
        if b1 and _offsets_clustered(b1, OFFSET_CLUSTER_MAX_SPAN_S):
            qb = st["query_buckets_20_35"]
            nb = len(qb)
            bk = ",".join(str(int(c)) for _, c in sorted(qb.items())[:12])
            if avg > P7_STRICT_HAMMING:
                strict_ok = sum(1 for _, c in qb.items() if int(c) >= P7_STRICT_FRAMES_PER_BUCKET)
                if strict_ok > P7_STRICT_MIN_BUCKETS:
                    return r(f"P7-strict: {strict_ok} buckets ≥ {P7_STRICT_FRAMES_PER_BUCKET} frames (avg_hamming={avg:.1f} > {P7_STRICT_HAMMING:.0f}; buckets=[{bk}])", 7)
                best_bucket = max((int(c) for _, c in qb.items()), default=0)
                if best_bucket >= P7_STRICT_CONCENTRATED:
                    return r(f"P7-strict-burst: one bucket has {best_bucket} frames (≥ {P7_STRICT_CONCENTRATED}) at avg_hamming={avg:.1f}; buckets=[{bk}]", 7)
            elif nb >= MIN_BUCKETS_FOR_DIVERSITY:
                min_per = FRAMES_MIN_PER_BUCKET_SINGLE if nb == MIN_BUCKETS_FOR_DIVERSITY else FRAMES_MIN_PER_BUCKET_MULTI
                ok = sum(1 for _, c in qb.items() if int(c) >= min_per)
                if ok >= MIN_UNIQUE_BUCKETS:
                    return r(f"P7: 20-35 has {ok} query-time buckets ≥ {min_per} (clustered offsets; buckets=[{bk}])", 7)
    # P8: many weak-but-decision-capable frames which agree on one alignment.
    # 40-45 remains available to hints and the other detectives, but can no
    # longer decide a PDQ answer. Requiring a stable offset also prevents many
    # unrelated look-alike frames scattered through a film from adding up.
    if f35_40 >= FRAMES_HIGH_CONFIDENT:
        bweak = st.get("offset_buckets_35_40", {})
        span = int(round(OFFSET_CLUSTER_MAX_SPAN_S / OFFSET_BUCKET_S))
        best_cluster = max(
            (sum(int(bweak.get(other, 0)) for other in bweak if abs(int(other) - int(center)) <= span)
             for center in bweak),
            default=0,
        )
        if best_cluster >= FRAMES_HIGH_CONFIDENT:
            return r(f"P8: {best_cluster} aligned frames in 35-40 (≥{FRAMES_HIGH_CONFIDENT}; 40-45 hint only)", 8)
    return None


def check_end_of_clip_exit(movie_stats: dict) -> Optional[dict]:
    """The rules that run only once the whole clip has been seen (the pod's
    _check_end_of_processing_exit): P9E and P9, the 'only film in sight' rules."""
    movies_any = [m for m, st in movie_stats.items() if int(st["total_frames"]) > 0]
    if not movies_any:
        return None
    uniq = sorted(set(int(m) for m in movies_any))
    if len(uniq) == 1:
        mid = uniq[0]
        st = movie_stats[mid]
        total = int(st["total_frames"])
        avg = float(st["dist_sum"]) / max(int(st["dist_cnt"]), 1)
        # P9E's sliding floor (the V3 change, kept here): two frames are only enough when
        # the evidence is good (avg ≤ 25); mediocre evidence needs four, like its sibling P9.
        p9e_minf = 2 if avg <= 25.0 else 4
        if avg <= 35.0 and total >= p9e_minf:
            return {"movie_id": mid, "reason": f"P9E: Only movie overall with avg≤35 (avg={avg:.1f}) and frames={total} (≥{p9e_minf})",
                    "priority": 9, "immediate": True, "avg_hamming": avg}
        f35 = int(st["frames_35_45"])
        minf = _p9_min_frames(avg)
        if 35.0 < avg <= 45.0 and f35 >= minf:
            return {"movie_id": mid, "reason": f"P9: Only movie overall in 35-45 with frames_35_45={f35} (≥{minf}) avg={avg:.1f}",
                    "priority": 9, "immediate": True, "avg_hamming": avg}
    for mid, st in movie_stats.items():
        if int(st["frames_35_45"]) > 0:
            qb35 = st["query_buckets_35_45"]
            if len(qb35) >= 3 and (int(st["frames_0_20"]) > 0 or int(st["frames_20_35"]) > 0):
                avg = float(st["dist_sum"]) / max(int(st["dist_cnt"]), 1)
                return {"movie_id": int(mid), "reason": f"P9: {len(qb35)} query-time buckets in 35-45 (with other-range evidence)",
                        "priority": 9, "immediate": True, "avg_hamming": avg}
    return None


def wait_seconds_for_reason(reason: str) -> float:
    """How long the orchestrator (Max_spped_up.py) waits before trusting a weak-band exit.
    0 means it does not wait."""
    rr = (reason or "").lower()
    weak = "35-45" in rr or "35,45" in rr
    if not weak:
        import re
        m = re.search(r"avg_hamming=([0-9]+\.?[0-9]*)", rr)
        weak = bool(m and 35.0 < float(m.group(1)) <= 45.0)
    if not weak:
        return 0.0
    if "p9e" in rr or "only movie overall" in rr:
        return WAIT_P9E_S
    if "p9" in rr:
        return WAIT_P9_S
    if "p8" in rr:
        return WAIT_P8_S
    return WAIT_OTHER_35_45_S


def _best_aligned_bucket_range(hist: dict, max_span_s: float = 4.0) -> Tuple[float, float]:
    """The stretch of film (up to 4 s wide) where most matched frames landed. This is the
    'offset' the pod prints for a film."""
    if not hist:
        return (0.0, 0.0)
    items = sorted(hist.items())
    buckets = [b for b, _ in items]
    counts = [c for _, c in items]
    best_i = max(range(len(items)), key=lambda i: counts[i])
    best_sum, best_l, best_r, l, cur = -1, best_i, best_i, 0, 0
    for rr in range(len(items)):
        cur += counts[rr]
        while buckets[rr] - buckets[l] > max_span_s:
            cur -= counts[l]
            l += 1
        if (rr - l + 1) >= 2 and cur > best_sum:
            best_sum, best_l, best_r = cur, l, rr
    if best_sum <= 0:
        return (float(buckets[best_i]), float(buckets[best_i]))
    return (float(buckets[best_l]), float(buckets[best_r]))


def _hamming_range_str(avg: float) -> str:
    if avg <= 20.0:
        return "0-20"
    if avg <= 35.0:
        return "20-35"
    if avg <= 45.0:
        return "35-45"
    return ">45"


@dataclass
class ClipResult:
    early_accept: bool
    vidx: Optional[int]
    label: Optional[str]
    reason: str
    exit_kind: str
    exit_reason: str
    reached_end: bool
    progress_s: float
    duration_s: float
    decoded_frames: int
    kept_frames: int
    hashes: int
    query_seconds: float
    ranked: list          # [(matched, avg_hamming, vidx, offset_s), ...] best first
    hints: list           # [(vidx, range_str, frames, avg_hamming), ...]
    movie_stats: dict     # the raw scorecards, for anyone who wants to dig
    wait_seconds: float   # what the orchestrator would wait before trusting this exit
    # The hint bucket with the shape of each candidate's evidence - see pv2_scorecard. Last
    # and defaulted so the three positional ClipResult(...) calls keep working unchanged.
    scorecard: list = None


def whole_clip_prescan(video_path: str, index: LoadedIndex, groups: List[str]) -> Optional[dict]:
    """The pod's fastest path (_whole_clip_scan). Before the frame-by-frame pass it grabs
    40 frames spread over the WHOLE clip, hashes them (full frame + crops), and asks: does
    one film get at least 3 of them under hamming 28, with its best under 20? If yes, that
    is the answer and the slow pass never runs. Returns None when there is no such film."""
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        n = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
        dur = (n / fps) if fps > 0 else 0.0
        if dur <= 2.0:
            return None
        t0 = time.time()
        hashes = {g: [] for g in groups}
        for i in range(SCAN_SAMPLES):
            t = dur * (i + 0.5) / SCAN_SAMPLES
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, bgr = cap.read()
            if not ok or bgr is None:
                continue
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            targets = [("FULL", rgb)] if "FULL" in groups else []
            for c in CROPS:
                g = group_for_crop_name(c.name)
                if g in groups:
                    targets.append((g, center_crop_aspect(rgb, c.ar_w, c.ar_h, c.scale)))
            for g, img in targets:
                hb, q = pdq_hash(img)
                if q >= CLIP_QUALITY_MIN:
                    hashes[g].append(hb)
        votes: Dict[int, list] = defaultdict(lambda: [0, 999, 0.0])   # vidx -> [frames, best hamming, film time]
        for g, hl in hashes.items():
            if not hl or g not in index.index_by_group:
                continue
            xq = np.frombuffer(b"".join(hl), dtype=np.uint8).reshape(-1, 32)
            D, I = index.index_by_group[g].search(xq, K_PER_HASH)
            for row in range(D.shape[0]):
                j = int(D[row].argmin()); md = int(D[row, j]); nn = int(I[row, j])
                if md < SCAN_ACCEPT_HAMMING and nn >= 0:
                    v = int(index.meta_vid[g][nn])
                    rec = votes[v]
                    rec[0] += 1
                    if md < rec[1]:
                        rec[1], rec[2] = md, float(index.meta_ts[g][nn])
        best = None
        for v, (cnt, mh, off) in votes.items():
            if cnt >= SCAN_MIN_FRAMES and mh < SCAN_STRONG_ANCHOR:
                key = (cnt, -mh)
                if best is None or key > best[0]:
                    best = (key, v, cnt, mh, off)
        if best is None:
            return None
        _, v, cnt, mh, off = best
        print(f"[SCAN] whole-clip pre-scan HIT in {time.time() - t0:.1f}s: vidx={v} frames={cnt} min_hamming={mh} -> early accept (skipped full pass-1)")
        return {"vidx": v, "frames": cnt, "min_hamming": mh, "offset": off,
                "reason": f"SCAN: whole-clip pre-scan min_hamming={mh} frames={cnt}"}
    finally:
        cap.release()


def pv2_sample_order(n_samples: int, mode: str | None = None) -> List[int]:
    """The order the probe takes its samples in - see pv2_waves.sample_order.

    The algorithm lives in pv2_waves.py, which imports nothing, so replay_rules.py can
    simulate a schedule using the SAME code without dragging in faiss and pdqhash. Only the
    configuration lives here."""
    if PV2_SAMPLE_MODE == "nested" and mode is None:
        return _nested_order(int(n_samples), PV2_SAMPLE_BASE)
    if PV2_ANCHORED and mode is None:
        # Anchored, the spread lives in the POSITIONS, not in the order of the ids, so the
        # ids are taken in their own order and id k is the k-th moment of the clip the probe
        # looks at. One consequence worth knowing: vdc and linear mean the same thing here,
        # so reproducing the pre-wave engine needs PDQ_PROBE_ANCHORED=0 as well.
        return list(range(int(n_samples)))
    return _wave_order(n_samples, PV2_WAVE_ORDER if mode is None else mode)


def pv2_sample_fractions(n_samples: int) -> List[float]:
    """Where each sample id sits in the clip, as a fraction of the duration.

    Anchored, this is the whole of the sampling: see pv2_waves.anchored_fractions. Its
    LENGTH is authoritative and can be shorter than asked for, because
    PDQ_PROBE_SAMPLE_MIN_GAP may refuse candidates.

    Off, it is the grid the probe has always used, which spans the whole clip just as
    evenly but re-sites every sample whenever n changes."""
    n = max(int(n_samples), 1)
    if PV2_SAMPLE_MODE == "nested":
        return _nested_fractions(n, PV2_SAMPLE_LO, PV2_SAMPLE_HI)
    if PV2_SAMPLE_MODE == "anchored":
        return _anchored_fractions(n, PV2_SAMPLE_LO, PV2_SAMPLE_HI, PV2_SAMPLE_MIN_GAP)
    if PV2_SAMPLE_MODE != "grid":
        raise ValueError("unknown PDQ_PROBE_SAMPLE_MODE %r (grid, anchored or nested)"
                         % PV2_SAMPLE_MODE)
    return [(i + 0.5) / n for i in range(n)]


def content_fractions(video_path: str, n: int, fps: float = 12.0, maxdim: int = 96,
                      cut: float = 30.0) -> List[float]:
    """Content-aware sample positions for one clip - see pv2_waves.shot_order.

    A forward decode at thumbnail size, which is the cheap way to read a clip: measured on
    ten held-out clips at 12 frames a second, 0.2 s for a 13 s clip and 2.9 s for a 125 s one,
    against a seek per frame for the grid. Only the 32x32 grey copy of each frame is kept."""
    from pv2_waves import shot_order
    times, scores, flat = [], [], []
    prev = None
    for fr in iter_frames(video_path, fps=fps, maxdim=maxdim):
        g = downsample_gray(fr.rgb, 32)
        scores.append(0.0 if prev is None else frame_change_score(prev, g))
        flat.append(float(g.std()) < 6.0)       # nearly one grey level: PDQ quality fails
        times.append(float(fr.timestamp))
        prev = g
    _, _, dur = video_wh_duration(video_path)
    return shot_order(times, scores, flat, int(n), dur or (times[-1] if times else 0.0),
                      PV2_SAMPLE_LO, PV2_SAMPLE_HI, cut=cut)


def pv2_wave_bounds(n_samples: int, waves=None) -> List[int]:
    """The waves as cumulative sample counts - see pv2_waves.wave_bounds.

    With PV2_PROGRESSIVE off this is one wave holding every frame, which is exactly the
    all-at-once probe."""
    if waves is None:
        waves = PV2_WAVES if PV2_PROGRESSIVE else (int(n_samples),)
    # Anchored, wave one is the same eight moments at any sample count, so the schedule is
    # taken literally and the extra samples become a final wave: at 50 frames that is
    # 8, 16, 24, 40, 50, and a clip that answers on wave one still pays for eight frames
    # whatever the total is set to. On the grid every position depends on n, so a wave of 8
    # out of 80 would cover a quarter of the clip rather than the whole of it, and there the
    # schedule has to be scaled instead.
    ref = int(n_samples) if PV2_ANCHORED else PV2_SAMPLES
    return _wave_bounds(n_samples, waves, max(ref, 1))


# Which view classes each views= request covers. p = the frame as shot, x = its mirror and
# letterbox-trimmed views, r = its quarter turns. "lab" is for dump_probe_evidence.py only: it
# keeps apart what production merges, so one dump can replay every variant -
#   x  pixel mirrors, hashed again (what ships)     l  the letterbox-trimmed picture
#   d  dihedral mirrors, read from the plain hash   r  quarter and half turns
_VIEW_CLASSES = {"plain": ("p",), "extra": ("x",), "all": ("p", "x"), "rot": ("r",),
                 "lab": ("p", "x", "l", "d", "r"),
                 # the lab without quarter turns, for the pod: the turns changed no answer on
                 # 266 local clips and are about 40% of a lab dump's search rows
                 "lab_norot": ("p", "x", "l", "d")}


def _classes_for(views: str) -> tuple:
    """The classes a views= request covers, with the rotations folded into "all" when
    PV2_ROTATE is on."""
    cl = _VIEW_CLASSES[views]
    if PV2_ROTATE and views == "all":
        cl = cl + ("r",)
    return cl


class ProbeRun:
    """One run of the probe over a clip, extendable A WAVE AT A TIME.

    This exists because the probe used to be all-or-nothing. It paid every seek and every
    fingerprint before anyone looked at a single result - 10.9 s on the median clip, 46.6 s
    at p90, 242.5 s at worst, and not one of the 125 real clips under a second - even when
    the first sampled frame was a perfect match, and even when the clip is not in the
    catalogue at all and no number of frames was ever going to help.

    A run holds the open video, the evidence so far, and a ledger of what has already been
    fingerprinted, so extend() can be called repeatedly and only ever pays for what is new:

      - ONE cv2.VideoCapture for the whole run. Re-opening and re-seeking a compressed video
        is the cost the old two-stage probe paid twice, which is why it came out slower on
        every clip it declined (measured: Soul 35.1 s -> 58.7 s).
      - The `hashed` ledger (sample -> which view classes are done) means re-requesting a
        sample costs nothing, and asking for the mirrored views over frames already decoded
        costs hashes but no seeks.
      - Each extend() searches ONLY its new fingerprints and merges the result. Splitting one
        batched search into per-wave searches is cost-neutral - measured on the real
        7.3M-row shard at K=64, one batch of 400 takes 1.56-1.84 s and waves of
        80/80/80/160 take 1.67-1.75 s - because faiss parallelises over the query block and
        80 rows already saturate the threads. So giving up early saves search time too.

    That makes the all-at-once probe, the progressive schedule and the two-stage view pass
    the same code path rather than three copies of one loop that drift apart.

    ok is False when the clip is unreadable or 2 s or shorter, which is what
    collect_probe_evidence returning None has always meant."""

    def __init__(self, video_path: str, index: LoadedIndex, groups: List[str],
                 n_samples: int | None = None, maxdim: int | None = None,
                 keep_frames: bool = False, frames: list | None = None):
        self.video_path = str(video_path)
        self.index = index
        self.groups = list(groups)
        self.n_samples = PV2_SAMPLES if n_samples is None else int(n_samples)
        self.maxdim = maxdim
        self.keep_frames = keep_frames
        self.film_hits: Dict[int, dict] = {}
        # (vidx, sample_i, group, view) -> (distance, clip_t, film_t, target). The overall
        # best per (film, frame) is the minimum over these, which is what film_hits holds.
        self.cells: Dict[tuple, tuple] = {}
        self.consumed: List[int] = []       # sample indices decoded, in decode order
        # sample_i -> {(group, view)} already fingerprinted. Per TARGET rather than per view
        # class, so one pass can take the cropped pictures from a frame and another the
        # uncropped ones, with neither repeating the other.
        self.hashed: Dict[int, set] = {}
        self.kept: Dict[int, tuple] = {}    # sample_i -> (clip_t, rgb)
        # Where each sample id sits, as a fraction of the duration. Empty when the frames
        # were handed in, because those carry their own times in kept.
        self._fracs: List[float] = []
        self.seek_s = self.hash_s = self.search_s = 0.0
        self.n_hashes = self.frames_decoded = self.index_searches = 0
        self.query_rows = self.waves_used = 0
        self.n_pictures = 0                 # PDQ computations actually paid for
        self.sig: Dict[int, tuple] = {}     # sample_i -> (plain full-frame hash, quality, clip_t)
        self.duration_s = 0.0
        self.decoded = frames is None
        self.ok = False
        self._cap = None
        self._seen: set = set()
        self._failed: set = set()
        self._workers = None        # the hashing pool, made on first use
        self._t0 = time.perf_counter()

        if frames is not None:
            # Handed the frames already, so never touch the video. super_probe's two-stage
            # pass comes through here, and these quirks are part of that contract: the
            # duration is the LAST sample's time rather than the clip's, and decoded is False.
            self.duration_s = frames[-1][1] if frames else 0.0
            self.n_samples = len(frames) or 1
            for i, t, rgb in frames:
                self.kept[i] = (t, rgb)
                self.consumed.append(i)
                self._seen.add(i)
            self.ok = True
            return

        import cv2
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            return
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        n = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
        dur = (n / fps) if fps > 0 else 0.0
        self.duration_s = dur
        if dur <= 2.0:
            cap.release()
            return
        self._cap = cap
        self._fracs = pv2_sample_fractions(self.n_samples)
        # The grid's length wins over the request: PDQ_PROBE_SAMPLE_MIN_GAP can refuse
        # candidates, so asking for 40 may yield 33, and the wave schedule and every
        # reported frame count are counted off n_samples.
        self.n_samples = len(self._fracs) or self.n_samples
        self.ok = True
        self._t0 = time.perf_counter()      # as before: the clock starts after the checks

    def use_fractions(self, fracs) -> None:
        """Sample at these positions instead of the grid: sample id k sits at fracs[k] of the
        clip. For dump_probe_evidence.py --order shots, which records content-aware samples
        in priority order so any prefix replays as a sample of that size."""
        self._fracs = [float(f) for f in fracs]
        self.n_samples = len(self._fracs) or 1

    # ---- the schedule ----------------------------------------------------------------------

    @property
    def bounds(self) -> List[int]:
        return pv2_wave_bounds(self.n_samples)

    @property
    def n_waves(self) -> int:
        return len(self.bounds)

    def schedule(self):
        """The waves, as lists of sample indices, in spread order.

        Each wave is evenly spread over the whole clip on its own AND the union of the waves
        so far stays evenly spread - see pv2_sample_order. With PV2_PROGRESSIVE off this
        yields one wave holding every sample, which is the old behaviour exactly."""
        order = pv2_sample_order(self.n_samples)
        prev = 0
        for b in self.bounds:
            yield order[prev:b]
            prev = b

    def time_of(self, i: int) -> float:
        """Sample id i's clip time.

        Anchored, id i is a fixed fraction of this clip that does not depend on how many
        samples the run takes, so id 3 is the same moment at 40 samples as at 50. On the
        grid it is (i + 0.5) / n, as every row already in output/probe_evidence.csv was
        recorded - which is also why those rows cannot be replayed against an anchored
        schedule: the same sample_i means a different moment.

        The second round's ids are negative and off the grid altogether, so the kept frames
        are consulted first: they carry their own time."""
        hit = self.kept.get(i)
        if hit is not None:
            return hit[0]
        if 0 <= i < len(self._fracs):
            return self.duration_s * self._fracs[i]
        return self.duration_s * (i + 0.5) / max(self.n_samples, 1)

    # ---- the work --------------------------------------------------------------------------

    def _frame(self, i: int):
        """Sample i as RGB, from the kept frames or by seeking. None if it cannot be read."""
        hit = self.kept.get(i)
        if hit is not None:
            return hit[1]
        if self._cap is None or i in self._failed:
            return None
        import cv2
        t = self.time_of(i)
        tk = time.perf_counter()
        self._cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, bgr = self._cap.read()
        rgb = None
        if ok and bgr is not None:
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            if self.maxdim:
                ow, oh = _scaled_dims(rgb.shape[1], rgb.shape[0], self.maxdim)
                if (ow, oh) != (rgb.shape[1], rgb.shape[0]):
                    rgb = cv2.resize(rgb, (ow, oh), interpolation=cv2.INTER_AREA)
            self.frames_decoded += 1
        self.seek_s += time.perf_counter() - tk
        if rgb is None:
            self._failed.add(i)
            return None
        if i not in self._seen:
            self._seen.add(i)
            self.consumed.append(i)
        if self.keep_frames:
            self.kept[i] = (t, rgb)
        return rgb

    def _prefetched(self, ids):
        """Yield (id, frame) for these ids, decoding the next frame while the caller hashes
        this one - see PV2_PREFETCH. One thread owns the capture for the whole wave, and the
        frames come back in the order asked, so the evidence is the same as decoding inline.
        With this on, seek_s and hash_s overlap and their sum can exceed the wall clock."""
        import queue
        import threading
        q = queue.Queue(maxsize=3)
        stop = threading.Event()
        done = object()

        def work():
            try:
                for i in ids:
                    if stop.is_set():
                        break
                    q.put((i, self._frame(i)))
            except BaseException as e:      # handed to the caller, never swallowed
                q.put((done, e))
                return
            q.put((done, None))

        th = threading.Thread(target=work, daemon=True)
        th.start()
        try:
            while True:
                i, rgb = q.get()
                if i is done:
                    if rgb is not None:
                        raise rgb
                    return
                yield i, rgb
        finally:
            stop.set()
            while th.is_alive():            # drain so the worker can finish and let go
                try:
                    q.get(timeout=0.05)
                except Exception:
                    pass
            th.join()

    def _pool(self):
        """This run's worker pool, made once and kept. See PV2_WORKERS."""
        if self._workers is None:
            self._workers = _futures.ThreadPoolExecutor(max_workers=PV2_WORKERS)
        return self._workers

    def _hash_into(self, samples: dict, i: int, t: float, views: str, groups=None,
                   rgb=False) -> None:
        """Fingerprint sample i, skipping any picture already taken from it.

        The ledger is per (group, view class), not per view class alone, which is what lets
        the cropped pass and the uncropped pass ask for their own pictures from the SAME
        decoded frame without either repeating the other's work.

        rgb, when given (None included), is the frame already decoded by the prefetcher."""
        want = list(groups) if groups is not None else self.groups
        if rgb is False:
            rgb = self._frame(i)
        if rgb is None:
            return
        done = self.hashed.setdefault(i, set())
        th = time.perf_counter()
        # The results are collected first and appended afterwards IN THE ORIGINAL ORDER.
        # Appending from the workers themselves would order the evidence by whichever thread
        # finished first, so the same clip would dump differently from one run to the next
        # and no two runs could be compared.
        #
        # One pool for the whole clip, not one per frame. Built per frame it was measured
        # SLOWER than doing nothing in parallel at all - 23.7 minutes against 17.5 over the
        # 125 clips - because starting and stopping eighty pools to hash eleven small
        # pictures each costs more than the hashing saves.
        mapper = self._pool().map if PV2_WORKERS > 1 else map
        rows, n_pics = _frame_hashes(rgb, want, views, done, mapper)
        self.n_pictures += n_pics
        for g, hb, q, tag in rows:
            if tag == "full" and i not in self.sig:
                self.sig[i] = (hb, q, t)    # the frame's own fingerprint, for offline study
            if q >= CLIP_QUALITY_MIN:
                samples.setdefault(g, []).append((i, t, hb, tag))
        self.hash_s += time.perf_counter() - th
        # mark every (group, view) this call covered, hit or miss, so it is not retried
        for g in want:
            for vc in _classes_for(views):
                done.add((g, vc))

    def _search_and_merge(self, samples: dict, subindex=None) -> dict:
        rows = sum(len(v) for v in samples.values())
        self.n_hashes += rows
        self.query_rows += rows
        ts = time.perf_counter()
        if subindex is None:
            delta, searches, cells = _probe_search(samples, self.index)
        else:
            delta, searches, cells = _probe_search_shortlist(samples, self.index, subindex)
        self.search_s += time.perf_counter() - ts
        self.index_searches += searches
        _merge_film_hits(self.film_hits, delta)
        # And the per-cell bests, by the same keep-the-smaller rule. These are what make a
        # pass simulable offline; film_hits above is still what the rulebook judges.
        for k, row in cells.items():
            cc = self.cells.get(k)
            if cc is None or row[0] < cc[0]:
                self.cells[k] = row
        return delta

    def extend(self, indices, views: str = "all", groups=None) -> tuple:
        """Take these samples, fingerprint whatever is new, search it, merge it.

        groups restricts which of the index's families this call looks at - {"FULL"} for the
        uncropped pass, the crop families for the cropped one. Only the shards named here are
        searched, which is most of why an uncropped pass is cheap: FULL holds 1,912,233 of
        the index's 16,744,500 fingerprints.

        Returns (evidence, delta) - the whole run's evidence so far, and just what this call
        added, so a caller can apply a give-up bar without rescanning everything."""
        if views not in _VIEW_CLASSES:
            raise ValueError("views must be all, plain or extra, not %r" % views)
        want = [int(i) for i in indices]
        if PV2_WAVE_DECODE_SORTED:
            # A wave's MEMBERSHIP is what the even spread guarantees; the order inside it is
            # free, so seek forward within a wave and keep the backward jumps to one per wave.
            # By TIME and not by id: anchored, the ids are taken in their own order and say
            # nothing about position in the clip, so sorting the ids would seek at random.
            want.sort(key=self.time_of)
        use = [g for g in (groups if groups is not None else self.groups) if g in self.groups]
        need = {(g, vc) for g in use for vc in _classes_for(views)}
        samples: Dict[str, list] = {g: [] for g in use}
        todo = [i for i in want if not need <= self.hashed.get(i, set())]
        if PV2_PREFETCH and len(todo) > 1 and self._cap is not None:
            for i, rgb in self._prefetched(todo):
                self._hash_into(samples, i, self.time_of(i), views, use, rgb=rgb)
        else:
            for i in todo:
                self._hash_into(samples, i, self.time_of(i), views, use)
        delta = self._search_and_merge(samples)
        self.waves_used += 1
        return self.evidence(), delta

    def extend_at_times(self, times, first_id: int = -1, views: str = "all",
                        shortlist=None) -> tuple:
        """Sample at arbitrary clip times rather than on the grid, for the second round.

        Ids count away from first_id (so -1, -2, -3 ...), keeping the extra samples in their
        own namespace where they cannot collide with a wave's."""
        step = -1 if first_id < 0 else 1
        samples: Dict[str, list] = {g: [] for g in self.groups}
        for k, t in enumerate(times):
            self._at_time(samples, first_id + step * k, float(t), views)
        delta = self._search_and_merge(samples, subindex=shortlist)
        return self.evidence(), delta

    def _at_time(self, samples: dict, i: int, t: float, views: str) -> None:
        """One off-grid sample: seek to t, fingerprint it under id i."""
        import cv2
        if i in self.kept:
            rgb = self.kept[i][1]
        else:
            tk = time.perf_counter()
            self._cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, bgr = self._cap.read()
            rgb = None
            if ok and bgr is not None:
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                if self.maxdim:
                    ow, oh = _scaled_dims(rgb.shape[1], rgb.shape[0], self.maxdim)
                    if (ow, oh) != (rgb.shape[1], rgb.shape[0]):
                        rgb = cv2.resize(rgb, (ow, oh), interpolation=cv2.INTER_AREA)
                self.frames_decoded += 1
            self.seek_s += time.perf_counter() - tk
            if rgb is None:
                return
            if self.keep_frames:
                self.kept[i] = (t, rgb)
        th = time.perf_counter()
        rows, n_pics = _frame_hashes(rgb, self.groups, views)
        self.n_pictures += n_pics
        for g, hb, q, tag in rows:
            if q >= CLIP_QUALITY_MIN:
                samples.setdefault(g, []).append((i, t, hb, tag))
        self.hash_s += time.perf_counter() - th

    def has_unhashed_extra(self) -> bool:
        """Is there a decoded frame whose mirrored / letterbox views were never taken?

        Fixed 23 Oct 2026: this used to test for the string "extra" in a ledger that holds
        (group, class) pairs, so it was True for every clip and the two-stage give-up check
        always ran the mirror pass. Two-stage is off by default, so nothing shipped moved."""
        return any(not any(vc == "x" for _, vc in self.hashed.get(i, ()))
                   for i in self.consumed)

    # ---- what comes out ---------------------------------------------------------------------

    def evidence(self) -> dict:
        """The dict collect_probe_evidence has always returned, plus the cost split.

        elapsed_s stays the run's wall clock, so super_probe's accumulation keeps working.
        seek_s + hash_s + search_s <= elapsed_s, the remainder being overhead; before this
        there was no way to tell the three apart, and the claim that hashing dominates rested
        on a regression across clips (R^2 0.24) rather than measurement."""
        frames = None
        if self.keep_frames:
            frames = [(i, self.kept[i][0], self.kept[i][1])
                      for i in self.consumed if i in self.kept and self.kept[i][1] is not None]
        return {"film_hits": self.film_hits, "cells": self.cells,
                "duration_s": self.duration_s,
                "elapsed_s": time.perf_counter() - self._t0,
                "n_samples": self.n_samples, "groups": list(self.groups),
                "index_searches": self.index_searches, "n_hashes": self.n_hashes,
                "frames": frames, "decoded": self.decoded,
                "seek_s": self.seek_s, "hash_s": self.hash_s, "search_s": self.search_s,
                "frames_decoded": self.frames_decoded, "query_rows": self.query_rows,
                "waves_used": self.waves_used, "n_pictures": self.n_pictures,
                "sig": self.sig}

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self._workers is not None:
            # Let the threads go with the clip. Left open, one pool per clip would
            # accumulate over a sweep of hundreds.
            self._workers.shutdown(wait=True)
            self._workers = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def collect_probe_evidence(video_path: str, index: LoadedIndex, groups: List[str],
                           n_samples: int | None = None, maxdim: int | None = None,
                           views: str = "all", frames: list | None = None,
                           keep_frames: bool = False) -> Optional[dict]:
    """GATHER the probe's evidence. No decisions here - see pv2_decide for those.

    Samples n_samples frames across the WHOLE clip (the pre-scan's trick), hashes the full
    frame, the trimmed view and the crops (the full system's views, which the old pre-scan
    and probe never used), searches the index once per group, and keeps the best hit per
    (film, sampled frame) with its clip time and film time.

    Collection and judgement are split on purpose. Collecting is the expensive half (a seek
    and ~15-30 fingerprints per sample, then one exhaustive index sweep per group); judging
    is arithmetic. Splitting them lets dump_probe_evidence.py pay the cost once and
    replay_rules.py try a thousand rulebooks against the saved result in seconds, instead of
    re-running every clip for every threshold.

    Two optional economies, both off by default so the engine's answers do not move until
    each has been measured with dump_probe_evidence.py + replay_rules.py:

      maxdim  shrink the frame before hashing. pdq_hash costs 14.3 ms on a clip-native frame
              and 8.2 ms at 640, and the INDEX was built at FILM_MAXDIM=640, so hashing at
              640 is both 1.7x cheaper and 3.7 bits closer to what the index holds. Do not
              go below 640: the drift grows to 4-10 bits at 480.

              MEASURED over all 125 clips, and it is NOT free, which is why it stays off.
              640 is 3.9x faster end to end - the whole sweep 2430 s -> 622 s, the median
              clip 10.9 s -> 4.0 s, p90 46.6 s -> 6.4 s - but the answers move:

                           answers   right   known-wrong   precision
                native          48      47             1       97.9%
                maxdim=640      49      46             2       93.9%

              It drops Race to Witch Mountain and lets a known-wrong film in through P1.
              Re-fitting P1 (P1_BEST 15 -> 10) pulls it back to 46 right / 1 wrong at 95.8%,
              but --loo then shows 3 known-wrong on held-out clips against 1 fitted, so that
              setting is partly fitting these 125 clips by name.

              So it is a real trade - 3.9x for one correct answer and two points of
              precision - not an economy. Re-measure before taking it:
                  python dump_probe_evidence.py --maxdim 640 --tag d640all
                  python replay_rules.py --rules adopted --tag d640all
      views   "all" (every view, as shipped), "plain" (the frame and its safe-trim copy
              only - about 8 targets instead of 19), or "extra" (the letterbox-trimmed and
              mirrored views only). "plain" then "extra" on demand is the two-stage search:
              a mirrored clip finds nothing on the plain views, so stage two runs for
              exactly the clips that need it.

    And one that exists only to make the two-stage search worth doing:

      frames / keep_frames
              Reading the clip is NOT cheap. Sampling 40 frames means 40 random seeks into a
              compressed video, and measured on a real clip that fixed cost is several
              seconds - comparable to all the hashing. A naive two-stage probe pays it twice
              and comes out SLOWER on every clip it declines (measured: Soul 35.1 s -> 58.7 s).
              So stage one passes keep_frames=True, gets the decoded frames back, and stage
              two is handed them through frames= and never touches the video again.

    Returns None when the clip cannot be read or is too short, otherwise a dict with
    film_hits = {vidx: {sample_i: (distance, clip_t, film_t)}} plus some cost counters.

    Every sampled frame at once, which is what this has always done. It is now one wave of
    a ProbeRun, so there is a single decode-and-fingerprint loop in this file instead of
    three that drift - see ProbeRun above, and super_probe for the progressive form."""
    run = ProbeRun(video_path, index, groups, n_samples, maxdim,
                   keep_frames=keep_frames, frames=frames)
    if not run.ok:
        return None
    try:
        want = list(run.consumed) if frames is not None else range(run.n_samples)
        return run.extend(want, views=views)[0]
    finally:
        run.close()


def _probe_targets(rgb, groups: List[str], views: str):
    """Every (group, image) this frame should be fingerprinted as, for the requested views.

    Beyond the plain frame: the picture inside any letterbox bars (edit test: letterbox
    scored 1/8 without this), and the mirror of each (the classic repost trick; mirror
    scored 0/8 without it). The safe-trim copy is taken from the plain frame only, as the
    pod does."""
    plain = [rgb]
    region = active_region(rgb)
    if region is not None:
        plain.append(region)
    if views == "plain":
        # Build the mirrors only when they are wanted. They used to be made unconditionally
        # and then thrown away, which is two full-frame copies per sampled frame - about
        # 6 MB each at 1080x1920 - bought for nothing on every plain-views pass.
        if region is not None:
            plain.pop()                     # the letterbox-trimmed view counts as "extra"
        chosen = [(0, v) for v in plain]
    else:
        extra = [np.ascontiguousarray(v[:, ::-1]) for v in plain]    # the mirrors
        if region is not None:
            extra.append(plain.pop())
        if views == "extra":
            chosen = [(1, v) for v in extra]
        else:
            chosen = [(0, v) for v in plain] + [(1, v) for v in extra]
    out = []
    for vi, v in chosen:
        pre = "" if vi == 0 else "x:"           # x: = a mirrored or letterbox-trimmed view
        if "FULL" in groups:
            out.append(("FULL", v, pre + "full"))
            if vi == 0:
                sv = safe_trim_view(v)
                if sv is not None:
                    out.append(("FULL", sv, pre + "trim"))
        for c in CROPS:
            g = group_for_crop_name(c.name)
            if g in groups:
                out.append((g, center_crop_aspect(v, c.ar_w, c.ar_h, c.scale), pre + c.name))
    return out


# The two halves of the frame's pictures, as the two passes split them. Group FULL is the
# WHOLE frame (and its safe-trimmed copy); every other group is a centred crop of it. That
# split matters for cost as much as for recall: FULL holds 1,912,233 of the index's
# 16,744,500 fingerprints - 11% - and contributes 2 pictures per view where the crops
# contribute 6, so an uncropped pass is cheap on both sides of the search.
UNCROPPED_GROUPS = ("FULL",)


def is_uncropped(group: str) -> bool:
    return group in UNCROPPED_GROUPS


def view_class(tag: str) -> str:
    """"p" for the frame as shot, "x" for its mirrored or letterbox-trimmed view.

    Worth separating from the group because the mirrors are half of each pass's cost: an
    uncropped pass is 2 pictures per frame without them and 3 with.

    The lab views (see _VIEW_CLASSES) add "l", "d" and "r"; production tags only ever carry
    "x:" or nothing, so what ships reads exactly as before."""
    pre, sep, _ = tag.partition(":")
    if not sep:
        return "p"
    return "r" if pre.startswith("r") else pre


def _view_targets(v, groups, trim: bool):
    """The pictures one view of a frame is fingerprinted as: the whole view (and, for the
    frame as shot, its safe-trimmed copy) plus a centred crop per crop family. The same list
    _probe_targets builds per view, as (group, picture, name)."""
    out = []
    if "FULL" in groups:
        out.append(("FULL", v, "full"))
        if trim:
            sv = safe_trim_view(v)
            if sv is not None:
                out.append(("FULL", sv, "trim"))
    for c in CROPS:
        g = group_for_crop_name(c.name)
        if g in groups:
            out.append((g, center_crop_aspect(v, c.ar_w, c.ar_h, c.scale), c.name))
    return out


def _rot_group(name: str, quarter: int) -> Optional[str]:
    """The family a turned picture is searched in. A half turn keeps the shape. A quarter turn
    swaps width and height, so a 9:16 crop becomes a 16:9 picture and belongs with the
    LANDSCAPE crops, and the other way round; a 4:5 crop becomes 5:4, which the index does not
    hold, so it is dropped. The whole frame and the square crops stay where they are."""
    g = group_for_crop_name(name)
    if quarter == 2 or g in ("FULL", "SQUARE"):
        return g
    if name.startswith("9x16"):
        return "LANDSCAPE"
    if name.startswith("16x9"):
        return "PORTRAIT"
    return None


_ROTATIONS = ((DIH_ROT90, 1, "r90:"), (DIH_ROT180, 2, "r180:"), (DIH_ROT270, 3, "r270:"))


def _frame_hashes(rgb, groups, views: str, done=frozenset(), mapper=map):
    """Every fingerprint one frame contributes to the requested views.

    Returns ([(search group, hash, quality, tag), ...], PDQ computations paid). A target is
    skipped when its (group, class) is already in `done`, the ProbeRun ledger.

    With PV2_MIRROR=pixel and no rotations this is exactly what has always shipped: the
    targets of _probe_targets, in its order, one compute() each. Otherwise each picture of the
    frame as shot (and of its letterbox-trimmed copy) is hashed ONCE with compute_dihedral and
    the mirror and the turns are read out of that one computation."""
    classes = set(_classes_for(views))
    lab = views in ("lab", "lab_norot")
    dihedral = lab or "r" in classes or PV2_MIRROR == "dihedral"
    if not dihedral:
        todo = [(g, img, tag) for g, img, tag in _probe_targets(rgb, groups, views)
                if (g, view_class(tag)) not in done]
        res = list(mapper(pdq_hash, [t[1] for t in todo]))
        return [(g, hb, q, tag) for (g, _img, tag), (hb, q) in zip(todo, res)], len(todo)

    # What each source picture is asked to yield. In production the mirror and the letterbox
    # copy both travel as "x"; the lab keeps them apart as d and l, and also hashes the pixel
    # mirrors the old way as x, so the two kinds of mirror can be compared frame for frame.
    mirror_cls = "d" if lab else "x"
    region_cls = "l" if lab else "x"
    want_p, want_r = "p" in classes, "r" in classes
    want_m = mirror_cls in classes
    want_reg = region_cls in classes or want_m

    def todo_for(targets, plain: bool):
        keep = []
        for g, img, name in targets:
            asks = []
            if plain:
                if want_p and (g, "p") not in done:
                    asks.append("p")
                if want_m and name != "trim" and (g, mirror_cls) not in done:
                    asks.append("m")
                if want_r and name != "trim" and (g, "r") not in done:
                    asks.append("r")
            else:
                if region_cls in classes and (g, region_cls) not in done:
                    asks.append("reg")
                if want_m and (g, mirror_cls) not in done:
                    asks.append("m")
            if asks:
                keep.append((g, img, name, asks))
        return keep

    base = todo_for(_view_targets(rgb, groups, trim=True), plain=True)
    region = active_region(rgb) if want_reg else None
    reg = todo_for(_view_targets(region, groups, trim=False), plain=False) if region is not None else []
    work = base + reg
    res = list(mapper(pdq_hash_dihedral, [w[1] for w in work]))
    out = []
    for k, ((g, _img, name, asks), (hs, q)) in enumerate(zip(work, res)):
        is_base = k < len(base)
        if "p" in asks:
            out.append((g, hs[DIH_ORIG], q, name))
        if "reg" in asks:
            out.append((g, hs[DIH_ORIG], q, region_cls + ":" + name))
        if "m" in asks:
            out.append((g, hs[DIH_MIRROR], q, mirror_cls + ":" + name))
        if "r" in asks and is_base:
            for slot, quarter, pre in _ROTATIONS:
                g2 = _rot_group(name, quarter)
                if g2 is not None:
                    out.append((g2, hs[slot], q, pre + name))
    n = len(work)
    if lab and "x" in classes:
        # the pixel mirrors, hashed again exactly as production does, for the comparison
        # Cut from the MIRRORED FRAME, as _probe_targets does: mirroring each crop instead
        # moves an odd-width crop by one pixel.
        views_m = [np.ascontiguousarray(rgb[:, ::-1])]
        if region is not None:
            views_m.append(np.ascontiguousarray(region[:, ::-1]))
        mir = [(g, img, name) for v in views_m for g, img, name in _view_targets(v, groups, trim=False)
               if (g, "x") not in done]
        mres = list(mapper(pdq_hash, [m[1] for m in mir]))
        out += [(g, hb, q, "x:" + name) for (g, _img, name), (hb, q) in zip(mir, mres)]
        n += len(mir)
    return out, n


def film_row_range(index: LoadedIndex, g: str, vidx: int):
    """Where one film's fingerprints sit in a shard, as a (lo, hi) row range.

    Every film's rows are ONE contiguous block in every shard - checked against the real
    index: all four shards hold exactly 134 blocks for 134 films, sorted by film and then by
    film time, because write_index appends film by film. That is what makes a
    candidate-restricted search trivial instead of needing a FAISS IDSelector (measured
    SLOWER than not restricting at all, since it scans everything and filters).

    Returns (0, 0) if the film has no rows in this group."""
    mv = index.meta_vid[g]
    lo = int(np.searchsorted(mv, vidx, side="left"))
    hi = int(np.searchsorted(mv, vidx, side="right"))
    if hi > lo and (int(mv[lo]) != vidx or int(mv[hi - 1]) != vidx):
        # The block assumption is broken, so a slice would silently return another film's
        # rows. Fail loudly rather than answer with the wrong evidence.
        raise RuntimeError(f"index rows for film {vidx} in {g} are not contiguous; "
                           f"rebuild the index or stop using film_row_range")
    return lo, hi


def _subindex_for_films(index: LoadedIndex, g: str, vidxs) -> tuple:
    """A throwaway flat index over just these films' rows, plus the row offsets to map
    results back to global row numbers. Measured: slicing 2.3 MB off the memory-mapped shard
    takes 0.002 s and building the sub-index 0.000 s, so this is free next to a full sweep."""
    blocks, offsets = [], []
    for v in vidxs:
        lo, hi = film_row_range(index, g, int(v))
        if hi <= lo:
            continue
        blocks.append(index.index_by_group[g].reconstruct_n(lo, hi - lo))
        offsets.append((lo, hi - lo))
    if not blocks:
        return None, []
    sub = faiss.IndexBinaryFlat(256)
    sub.add(np.concatenate(blocks, axis=0) if len(blocks) > 1 else blocks[0])
    return sub, offsets


def _global_row(offsets, local_row: int) -> int:
    """Turn a sub-index row number back into a row number in the full shard."""
    for lo, n in offsets:
        if local_row < n:
            return lo + local_row
        local_row -= n
    return -1


def resample_candidates(video_path: str, index: LoadedIndex, groups: List[str],
                        film_hits: dict, shortlist, n_extra: int = 40,
                        maxdim: int | None = None, frames: list | None = None,
                        run=None) -> dict:
    """SECOND ROUND. Sample more frames where hits already came from, and search ONLY the
    shortlisted films.

    Why this exists: of the clips the probe refuses while already holding the right film as
    its top hint, many are starved of corroboration rather than of signal - The Walking Dead
    sits at average distance 14 on two frames. No rule can fix two frames; more frames can.
    And a fan edit's cuts are only seconds long, so 40 samples spread over the whole clip
    land inside each cut at most once, which is why the cut rule finds nothing to corroborate.
    Sampling densely around the moments that already matched is what gives both of them the
    second frame they need.

    It is nearly free because the search is restricted to the shortlist: one film is ~125k of
    16.7 million fingerprints, so this round does not grow with the catalogue at all.

    Returns new film_hits (merged into the ones passed in), using negative sample indices so
    the extra samples cannot collide with the first round's."""
    if not shortlist:
        return film_hits
    # The clip moments worth looking at again: wherever a shortlisted film already hit.
    hot = sorted({round(ct, 2) for v in shortlist for _, ct, _ in film_hits.get(v, {}).values()})
    if not hot:
        return film_hits
    own = run is None
    if own:
        run = ProbeRun(video_path, index, groups, maxdim=maxdim, frames=frames)
        if not run.ok:
            return film_hits
        run.film_hits = film_hits       # merge straight into the caller's evidence
    try:
        dur = run.duration_s
        if dur <= 2.0:
            return film_hits
        # The first round's real spacing. This used to read PV2_SAMPLES directly, so a run
        # sampling any other number of frames got hot windows of the wrong width.
        step = dur / max(run.n_samples, 1)
        wanted = []
        for ct in hot:                      # four new samples inside each hot moment
            for frac in (-0.66, -0.33, 0.33, 0.66):
                t = ct + frac * step
                if 0.0 <= t <= dur:
                    wanted.append(round(t, 2))
        wanted = sorted(set(wanted))[:n_extra]
        run.extend_at_times(wanted, first_id=-1, views="all", shortlist=shortlist)
        return run.film_hits
    finally:
        if own:
            run.close()


def verify_plan(film_hits: dict, duration_s: float, n_films: int = None,
                n_moments: int = None, exclude=()) -> tuple:
    """What the verifier looks at: (shortlist of films, clip times to sample).

    The shortlist is the films with the best single hits (under PV2_VERIFY_MAX_BEST), at most
    n_films. The moments are the clip times those films matched at, merged when within 3 s
    and ranked by their best distance, at most n_moments; each becomes a burst of frames at
    PV2_VERIFY_FPS over +/- PV2_VERIFY_SPAN_S. `exclude` drops films from consideration,
    which is how the lab asks what the verifier would do with the true film absent.

    Pure arithmetic over the evidence, so probe_lab.py can plan exactly as the engine does."""
    n_films = PV2_VERIFY_FILMS if n_films is None else n_films
    n_moments = PV2_VERIFY_MOMENTS if n_moments is None else n_moments
    best = []
    for v, hits in film_hits.items():
        if v in exclude or not hits:
            continue
        b = min(r[0] for r in hits.values())
        if b < PV2_VERIFY_MAX_BEST:
            best.append((b, -len(hits), int(v)))
    best.sort()
    shortlist = [v for _, _, v in best[:n_films]]
    marks = sorted((r[0], r[1]) for v in shortlist for r in film_hits[v].values()
                   if r[0] < PV2_VERIFY_MAX_BEST)
    moments = []
    for d, ct in marks:                         # best first
        if all(abs(ct - m) > 3.0 for m in moments):
            moments.append(ct)
        if len(moments) >= n_moments:
            break
    step = 1.0 / PV2_VERIFY_FPS
    k = int(round(PV2_VERIFY_SPAN_S * PV2_VERIFY_FPS))
    times = sorted({round(min(max(m + j * step, 0.0), max(duration_s - 0.05, 0.0)), 3)
                    for m in moments for j in range(-k, k + 1) if j != 0})
    return shortlist, times


def _probe_search(samples: dict, index: LoadedIndex):
    """One batched index search per group, reduced to the best hit per (film, sampled frame).

    Returns ({vidx: {sample_i: (distance, clip_t, film_t)}}, number of searches)."""
    film_hits: Dict[int, dict] = defaultdict(dict)
    cells: Dict[tuple, tuple] = {}     # (vidx, sample_i, group, view) -> (d, ct, ft, target)
    searches = 0
    for g, sl in samples.items():
        if not sl or g not in index.index_by_group:
            continue
        xq = np.frombuffer(b"".join(r[2] for r in sl), dtype=np.uint8).reshape(-1, 32)
        D, I = index.index_by_group[g].search(xq, K_PER_HASH)
        searches += 1
        for row in range(D.shape[0]):
            si, ct, _, tag = sl[row]
            vc = view_class(tag)
            for col in range(D.shape[1]):
                d = int(D[row, col]); nn = int(I[row, col])
                if nn < 0 or d >= MAX_HAMMING:
                    continue
                v = int(index.meta_vid[g][nn])
                ft = float(index.meta_ts[g][nn])
                cur = film_hits[v].get(si)
                if cur is None or d < cur[0]:
                    film_hits[v][si] = (d, ct, ft)
                k = (v, si, g, vc)
                cc = cells.get(k)
                if cc is None or d < cc[0]:
                    cells[k] = (d, ct, ft, tag)
    return dict(film_hits), searches, cells


def _probe_search_shortlist(samples: dict, index: LoadedIndex, shortlist):
    """Like _probe_search, but over a throwaway index holding only the shortlisted films.

    Measured: one film searches 63x faster than the whole 134-film index (0.024 s vs 1.504 s
    for 300 queries), and that cost does not grow with the catalogue."""
    film_hits: Dict[int, dict] = defaultdict(dict)
    cells: Dict[tuple, tuple] = {}     # (vidx, sample_i, group, view) -> (d, ct, ft, target)
    searches = 0
    for g, sl in samples.items():
        if not sl or g not in index.index_by_group:
            continue
        sub, offsets = _subindex_for_films(index, g, shortlist)
        if sub is None:
            continue
        xq = np.frombuffer(b"".join(r[2] for r in sl), dtype=np.uint8).reshape(-1, 32)
        D, I = sub.search(xq, min(PV2_SHORTLIST_K, sub.ntotal))
        searches += 1
        for row in range(D.shape[0]):
            si, ct, _, tag = sl[row]
            vc = view_class(tag)
            for col in range(D.shape[1]):
                d = int(D[row, col]); nn = int(I[row, col])
                if nn < 0 or d >= MAX_HAMMING:
                    continue
                gr = _global_row(offsets, nn)
                if gr < 0:
                    continue
                v = int(index.meta_vid[g][gr])
                ft = float(index.meta_ts[g][gr])
                cur = film_hits[v].get(si)
                if cur is None or d < cur[0]:
                    film_hits[v][si] = (d, ct, ft)
                k = (v, si, g, vc)
                cc = cells.get(k)
                if cc is None or d < cc[0]:
                    cells[k] = (d, ct, ft, tag)
    return dict(film_hits), searches, cells


def pv2_aligned(rows) -> int:
    """The largest number of hits agreeing on one film-time offset. A real clip plays through
    the film, so every matched frame lands at the same offset; a look-alike scatters."""
    offs = sorted(ft - ct for _, ct, ft in rows)
    return max((sum(1 for o in offs if abs(o - o0) <= PV2_OFFSET_TOL_S) for o0 in offs), default=0)


def pv2_spread(rows) -> int:
    """How many separate moments of the clip these hits came from."""
    return _unique_time_clusters([ct for _, ct, _ in rows], PV2_SPREAD_S)


def pv2_offset_clusters(rows):
    """Group a film's hits into runs that agree on film time, largest first.

    Each cluster spans at most PV2_OFFSET_TOL_S from its FIRST member, so a slow drift
    cannot chain into one huge cluster. This is the shape the whole rulebook turns on: a
    real scene is one big cluster, a fan edit is several corroborating clusters, and a
    look-alike is a handful of singletons.

    Returns [[(offset, distance, clip_t), ...], ...]."""
    items = sorted((ft - ct, d, ct) for d, ct, ft in rows)
    if not items:
        return []
    out, cur = [], [items[0]]
    for it in items[1:]:
        if it[0] - cur[0][0] <= PV2_OFFSET_TOL_S:
            cur.append(it)
        else:
            out.append(cur)
            cur = [it]
    out.append(cur)
    out.sort(key=len, reverse=True)
    return out


# Checked in this order; the bar asking for the strongest evidence wins a tie.
PV2_TIER_RANK = {"PV-A": 0, "P1": 1, "PV-B": 2, "PV-E": 3, "PV-C": 4, "P3.5": 5}


def pv2_decide(film_hits: dict):
    """JUDGE the probe's evidence. The rulebook, strongest evidence first:

      PV-A  two near-perfect frames                        (mirrors P2.5)
      P1    one frame under 15, 3 hits, 2 of them agreeing (the streaming P1, plus a guard)
      PV-B  the old pre-scan bar, plus film-time agreement (mirrors pre-scan + P4's check)
      PV-E  two film-time clusters that each corroborate   (the cut rule, for fan edits)
      PV-C  five medium frames, aligned, from two moments  (mirrors P6a)
      P3.5  nothing else matched at all, so the bar drops  (the streaming P3.5)

    Returns (accept-or-None, ranked) where ranked is [(frames, avg, vidx, film_t), ...] so
    the caller can publish hints even when nothing is accepted. Pure arithmetic over the
    dict collect_probe_evidence returns - no video, no index, no I/O, which is what lets
    replay_rules.py try a rulebook over all 125 clips in under a second."""
    best_accept = None
    ranked = []
    sole_candidate = len(film_hits) == 1
    for v, hits in film_hits.items():
        rows = sorted(hits.values())             # (dist, clip_t, film_t), best first
        if not rows:
            continue
        best = float(rows[0][0])
        total = len(rows)
        avg = sum(r[0] for r in rows) / total
        ranked.append((total, float(avg), int(v), float(rows[0][2])))
        a = [r for r in rows if r[0] < PV2_A_DIST]
        b = [r for r in rows if r[0] < PV2_B_DIST]
        c = [r for r in rows if r[0] < PV2_C_DIST]
        p1 = [r for r in rows if r[0] < PV2_P1_DIST]
        clusters = pv2_offset_clusters(rows)
        corroborating = [cl for cl in clusters
                         if len(cl) >= PV2_E_PER_CLUSTER
                         and min(d for _, d, _ in cl) <= PV2_E_BEST]
        tier = None
        if best < PV2_A_BEST and len(a) >= PV2_A_FRAMES:
            tier = ("PV-A", f"best={best:.0f} frames_under_{PV2_A_DIST:.0f}={len(a)}")
        elif (best < PV2_P1_BEST and total >= PV2_P1_FRAMES
                and pv2_aligned(p1) >= PV2_P1_ALIGN):
            tier = ("P1", f"best={best:.0f} with {total} frames, "
                          f"aligned={pv2_aligned(p1)} under {PV2_P1_DIST:.0f}")
        elif best < PV2_B_BEST and len(b) >= PV2_B_FRAMES and pv2_aligned(b) >= PV2_B_NEED_ALIGN:
            tier = ("PV-B", f"best={best:.0f} frames_under_{PV2_B_DIST:.0f}={len(b)} aligned={pv2_aligned(b)}")
        elif len(corroborating) >= PV2_E_CLUSTERS:
            where = ", ".join(f"{cl[0][0] / 60.0:.1f}" for cl in corroborating[:4])
            tier = ("PV-E", f"{len(corroborating)} corroborating clusters at {where} min")
        elif (best < PV2_C_BEST and len(c) >= PV2_C_FRAMES and pv2_aligned(c) >= PV2_C_NEED_ALIGN
                and pv2_spread(c) >= PV2_C_NEED_SPREAD):
            tier = ("PV-C", f"best={best:.0f} frames_under_{PV2_C_DIST:.0f}={len(c)} "
                            f"aligned={pv2_aligned(c)} moments={pv2_spread(c)}")
        elif sole_candidate:
            for lim_avg, need in PV2_P35_BARS:
                if avg <= lim_avg and total >= need:
                    tier = ("P3.5", f"sole candidate, {total} frames at avg {avg:.1f}")
                    break
        if tier:
            key = (-PV2_TIER_RANK[tier[0]], len(clusters[0]) if clusters else 0, -best)
            if best_accept is None or key > best_accept[0]:
                best_accept = (key, int(v), tier, best, total, float(rows[0][2]))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    if best_accept is None:
        return None, ranked
    _, v, (tname, detail), best, nhits, off = best_accept
    return {"vidx": v, "frames": nhits, "min_hamming": best, "offset": off,
            "tier": tname, "detail": detail,
            "reason": f"{tname}: probe-v2 {detail}"}, ranked


PV2_BAND_RANK = {"strong": 0, "medium": 1, "weak": 2}


def pv2_shortfall(rows) -> str:
    """The bar this film came closest to passing, and what it was short of.

    A downstream system wants to know not just that the probe refused, but by how much. A
    film one frame short of PV-B is a different proposition from one whose best frame is at
    distance 44."""
    if not rows:
        return ""
    best = float(rows[0][0])
    b = [r for r in rows if r[0] < PV2_B_DIST]
    c = [r for r in rows if r[0] < PV2_C_DIST]
    a = [r for r in rows if r[0] < PV2_A_DIST]
    want = []
    if best < PV2_A_BEST:
        if len(a) < PV2_A_FRAMES:
            want.append(("PV-A", "%d more frame(s) under %.0f" % (PV2_A_FRAMES - len(a), PV2_A_DIST)))
    if best < PV2_B_BEST:
        miss = []
        if len(b) < PV2_B_FRAMES:
            miss.append("%d more under %.0f" % (PV2_B_FRAMES - len(b), PV2_B_DIST))
        if pv2_aligned(b) < PV2_B_NEED_ALIGN:
            miss.append("%d more agreeing on film time" % (PV2_B_NEED_ALIGN - pv2_aligned(b)))
        if miss:
            want.append(("PV-B", " and ".join(miss)))
    elif best < PV2_C_BEST:
        miss = []
        if len(c) < PV2_C_FRAMES:
            miss.append("%d more under %.0f" % (PV2_C_FRAMES - len(c), PV2_C_DIST))
        if pv2_aligned(c) < PV2_C_NEED_ALIGN:
            miss.append("%d more agreeing" % (PV2_C_NEED_ALIGN - pv2_aligned(c)))
        if pv2_spread(c) < PV2_C_NEED_SPREAD:
            miss.append("a second clip moment")
        if miss:
            want.append(("PV-C", " and ".join(miss)))
    if not want:
        return "best frame at %.0f, too far for any bar" % best
    name, detail = want[0]
    return "%s needs %s" % (name, detail)


def pv2_scorecard(film_hits: dict, cells: dict | None = None, top: int = 5) -> list:
    """The hint bucket: every film the probe saw, with the SHAPE of its evidence.

    The shape is what separates a real match from a look-alike, and it is the same shape the
    bars judge - how many frames matched, how well they agree on one film-time offset, how
    many separate clip moments they came from - plus which of the probe's views found them,
    which no hint has ever carried.

    band is a coarse verdict for a system that will not read the numbers:

      strong  a good frame AND corroboration: best under 20 with two hits agreeing
      medium  something real but thin: best under 33, with either agreement or 3+ frames
      weak    one stray frame, or several that agree about nothing

    The bands are MEASURED, not asserted - two_pass_lab.py --hints prints each band's
    precision over the dumped evidence of all 80 edited and 125 real clips. Treat the
    numbers as the output and the band as a convenience.

    Returns [{vidx, frames, best, avg, aligned, clusters, biggest, moments, offset_s,
              views, band, shortfall}, ...], strongest first."""
    out = []
    for v, hits in film_hits.items():
        rows = sorted(hits.values())
        if not rows:
            continue
        best = float(rows[0][0])
        n = len(rows)
        avg = sum(r[0] for r in rows) / n
        clusters = pv2_offset_clusters(rows)
        biggest = len(clusters[0]) if clusters else 0
        b = [r for r in rows if r[0] < PV2_B_DIST]
        c = [r for r in rows if r[0] < PV2_C_DIST]
        aligned = pv2_aligned(b)
        moments = pv2_spread(c)
        views = ""
        if cells:
            views = ",".join(sorted({"%s:%s" % (g, vc)
                                     for (vv, _si, g, vc) in cells if vv == v}))
        if best < PV2_B_BEST and biggest >= 2:
            band = "strong"
        elif best < PV2_C_DIST and (biggest >= 2 or n >= PV2_B_FRAMES):
            band = "medium"
        else:
            band = "weak"
        out.append({"vidx": int(v), "frames": n, "best": best, "avg": float(avg),
                    "aligned": aligned, "clusters": len(clusters), "biggest": biggest,
                    "moments": moments,
                    "offset_s": float(clusters[0][0][0]) if clusters else 0.0,
                    "views": views, "band": band, "shortfall": pv2_shortfall(rows)})
    out.sort(key=lambda d: (PV2_BAND_RANK[d["band"]], d["best"], -d["frames"]))
    return out[:top]


def pv2_scorecard_str(card: list, index: "LoadedIndex", top: int = 3) -> str:
    """The scorecard packed for one CSV cell: candidates separated by ';', fields by '~'.

    label~band~frames~best~avg~aligned~clusters~biggest~moments~views~shortfall

    Packed rather than spread over columns because the number of candidates varies, and the
    existing best_hint column stays exactly as it was so metrics.parse_hint keeps working."""
    parts = []
    for d in card[:top]:
        parts.append("~".join([
            (index.label(d["vidx"]) or str(d["vidx"])).replace("~", "-").replace(";", ","),
            d["band"], str(d["frames"]), "%.0f" % d["best"], "%.1f" % d["avg"],
            str(d["aligned"]), str(d["clusters"]), str(d["biggest"]), str(d["moments"]),
            d["views"], d["shortfall"].replace("~", "-").replace(";", ","),
        ]))
    return ";".join(parts)


def _merge_film_hits(into: dict, extra: dict) -> dict:
    """Fold a second collection pass into the first, keeping the better hit per
    (film, sampled frame) - the same rule a single pass applies."""
    for v, hits in extra.items():
        dst = into.setdefault(v, {})
        for si, row in hits.items():
            cur = dst.get(si)
            if cur is None or row[0] < cur[0]:
                dst[si] = row
    return into


def _probe_give_up(run: "ProbeRun", delta: dict, two_stage: bool) -> bool:
    """Has the probe seen enough to stop sampling this clip?

    Measured over all 125 clips with replay_rules.py, the two bars are not close:

      "run"   stop while the WHOLE run so far has found nothing under MAX_HAMMING. 49% of
              the sampled frames, and DECISION-IDENTICAL to the full scan: 47 right, 1
              wrong, the same film on all 48 answers. Clips that are not in the catalogue
              produce no hit at all on their first 8 frames - the ones that are hit at a
              median best distance of 16 - so this separates them cleanly.
      "wave"  stop when one wave adds no NEW hit. 40% of the frames but it loses 4 correct
              answers: evidence arrives in bursts, and a quiet wave is not a verdict.

    Giving up here is not the clip's verdict. identify_clip falls through to the full
    streaming pass, which has its own probe and rules, so this costs an early exit only."""
    if PV2_WAVE_BAR == "off":
        return False
    if len(run.consumed) < PV2_GIVEUP_MIN_FRAMES:
        # Jude's Part 6: a bad score on 8 frames does not mean the film is absent, it
        # means we have not seen enough of the clip yet. Hold the bar until this many
        # frames have been looked at.
        return False
    nothing = (not run.film_hits) if PV2_WAVE_BAR == "run" else (not delta)
    if not nothing:
        return False
    if two_stage and run.has_unhashed_extra():
        # A mirrored clip finds nothing AT ALL on the plain views - that is the premise of
        # the two-stage economy - so the mirror pass has to run over the frames already
        # decoded before this clip may be called hopeless. Without this the bar would
        # abandon every mirrored clip on wave one and it would never get the pass that
        # identifies it. If the mirrors do find something the next wave judges it.
        run.extend(run.consumed, views="extra")
        return not run.film_hits
    return True


def _staged_probe(run: "ProbeRun", resample: bool):
    """The two passes and the fallback. See PV2_PASSES for what each stage is and why.

    All three stages take DIFFERENT frames - consecutive slices of pv2_sample_order, so each
    slice is spread over the whole clip and no frame is ever sampled twice. What they share
    is the DECODED frames: stage two asks for the uncropped pictures of stage one's frames as
    well as its own, and the ledger inside ProbeRun means that costs the hashing and not the
    seeking. That is the whole reason the passes are cheap enough to be worth splitting.

    Returns (hit, ranked, where)."""
    order = pv2_sample_order(run.n_samples)
    n1 = max(0, min(PV2_PASS1_FRAMES, run.n_samples))
    n2 = max(0, min(PV2_PASS2_FRAMES, run.n_samples - n1))
    n3 = max(0, min(PV2_PASS3_FRAMES, run.n_samples - n1 - n2))
    cropped = [g for g in run.groups if g in PV2_CROPPED_GROUPS]
    uncropped = [g for g in run.groups if is_uncropped(g)]

    # ---- stage 1: the cropped pictures of the first slice --------------------------------
    run.extend(order[:n1], views="all", groups=cropped)
    hit, ranked = pv2_decide(run.film_hits)
    if hit is not None and hit["tier"] in PV2_WAVE_EARLY_TIERS:
        return hit, ranked, "pass 1 cropped, %d frames" % n1

    # ---- stage 2: the uncropped pictures, over the new slice AND stage one's frames -------
    if n2 or uncropped:
        run.extend(order[:n1 + n2], views="all", groups=run.groups)
        hit, ranked = pv2_decide(run.film_hits)
        if hit is not None and hit["tier"] in PV2_WAVE_EARLY_TIERS:
            return hit, ranked, "pass 2 uncropped, %d+%d frames" % (n1, n2)

    # ---- stage 3: the fallback - more frames, the same bars -------------------------------
    # Measured on the 125 real clips: with the probe's own bars this recovers 12, 12 and 16
    # of the 94 fall-throughs at 8, 12 and 20 frames, so the frames are what pay. Looser bars
    # recover 17 and add a second wrong answer; shape-only bars do worse still (7, 9, 12).
    # They looked best on the edited suite, which holds only two distinct wrong films across
    # 78 clips and so cannot punish a loose rule at all - which is why the fallback ships
    # with the probe's bars and the frames turned up instead.
    if n3:
        run.extend(order[:n1 + n2 + n3], views="all", groups=run.groups)
        hit, ranked = pv2_decide(run.film_hits)
        if hit is not None:
            return hit, ranked, "fallback, %d+%d+%d frames" % (n1, n2, n3)

    hit, ranked = pv2_decide(run.film_hits)
    return hit, ranked, "all three stages, %d frames" % (n1 + n2 + n3)


def super_probe(video_path: str, index: LoadedIndex, groups: List[str],
                two_stage: bool | None = None, maxdim: int | None = None,
                resample: bool | None = None):
    """The probe, version 2: collect the evidence IN WAVES, judging after each one.

    The samples are taken a wave at a time in pv2_sample_order, so every wave is spread over
    the whole clip and the union of the waves so far stays spread. After each wave the
    rulebook runs: a clip whose answer is already clear stops there, and a clip that has
    found nothing at all is given up on (see _probe_give_up). Measured over the 125 real
    clips this is DECISION-IDENTICAL to sampling everything - 47 right, 1 wrong, the same
    film on all 48 answers - at 49% of the sampled frames:

        python replay_rules.py --rules adopted --waves 8,16,24,40 --bar run --audit-waves

    Note what does NOT work, so nobody tries it again: taking fewer frames across the board.
    Flat decimation to 20 evenly spread samples drops 47 right to 31, because the bars reward
    hits that agree on a film-time offset and thinning the samples destroys the agreement.
    The ordering is load-bearing too - radical-inverse 47 right, golden-ratio 43, the plain
    ascending order the probe used to take 43.


    With two_stage on, the plain views are collected and judged first, and the mirrored and
    letterbox-trimmed views are only collected if the plain views did not already produce an
    answer. That is **recall-identical by construction** - an accepted clip would have been
    accepted on the plain views either way, and a declined clip still ends up judged on
    exactly the same total evidence - so it needs measuring only to size the saving, not to
    check it is safe. Measured on the Brick clip: 10.6 s instead of 22.3 s, same 13 hits at
    best distance 8.

    (A more aggressive gate - skip the extra views whenever the plain views found any film at
    all - would save more on declined clips too, but it is NOT recall-safe: a mirrored clip
    can pick up a junk candidate on its plain views and would then never get the mirror pass
    that identifies it. If that gate is ever wanted, measure it with
    `dump_probe_evidence.py --views plain` against the full dump first.)"""
    two_stage = PV2_TWO_STAGE if two_stage is None else two_stage
    resample = PV2_RESAMPLE if resample is None else resample
    first = "plain" if two_stage else "all"
    # The staged form hands each stage the frames the one before it decoded, so the frames
    # have to be kept: without this stage two would seek stage one's slice all over again,
    # which is the cost the whole split exists to avoid.
    run = ProbeRun(video_path, index, groups, maxdim=maxdim,
                   keep_frames=(two_stage or resample or PV2_PASSES))
    if not run.ok:
        return None, [], []
    try:
        if PV2_PASSES:
            # the cropped pass, then the uncropped one, then the fallback
            hit, ranked, where = _staged_probe(run, resample)
            card = pv2_scorecard(run.film_hits, run.cells)
            ev = run.evidence()
            if hit is None:
                return None, ranked, card
            print(f"[PROBE-V2] {hit['tier']} HIT in {ev['elapsed_s']:.1f}s ({where}, "
                  f"{len(run.consumed)}/{run.n_samples} frames; seek {ev['seek_s']:.1f}s "
                  f"hash {ev['hash_s']:.1f}s search {ev['search_s']:.1f}s): "
                  f"vidx={hit['vidx']} {hit['detail']} -> early accept")
            return hit, ranked, card

        hit, ranked = None, []
        wave = 0
        gave_up = out_of_time = False
        for idxs in run.schedule():
            wave += 1
            last = (wave == run.n_waves)
            _, delta = run.extend(idxs, views=first)
            # The whole run's evidence, not just this wave's - see PV2_CARRY_FORWARD.
            hit, ranked = pv2_decide(run.film_hits if PV2_CARRY_FORWARD else delta)
            if hit is not None and not (last or hit["tier"] in PV2_WAVE_EARLY_TIERS):
                # A bar fired, but not one that is trusted on partial evidence. P3.5 turns on
                # being the SOLE candidate in the index, and a later wave can find it a
                # rival, so accepting it here would answer where the full scan refuses.
                hit = None
            if hit is not None or last:
                break
            if _probe_give_up(run, delta, two_stage):
                gave_up = True
                break
            if PV2_BUDGET_S > 0 and (time.perf_counter() - run._t0) >= PV2_BUDGET_S:
                # Out of time. This is not the give-up bar - that one says the clip looks
                # unfindable, this one says only that it is slow - so the evidence gathered
                # so far still goes to the later stages exactly as it would have done.
                out_of_time = True
                break
        where = "wave %d of %d%s" % (wave, run.n_waves,
                                     ", gave up" if gave_up else
                                     ", out of time" if out_of_time else "")

        if hit is None and two_stage and run.has_unhashed_extra():
            # The frames are already in hand, so this re-reads nothing. Running the extra
            # views ONCE here rather than per wave is what keeps the two-stage economy
            # recall-identical while not charging the mirror cost to clips that accept early.
            run.extend(run.consumed, views="extra")
            hit, ranked = pv2_decide(run.film_hits)
            where += ", + mirrored views"

        if hit is None and PV2_VERIFY and run.film_hits and run._cap is not None:
            # The verifier - see PV2_VERIFY. Ids from -100000 downward, clear of the second
            # round's -1, -2, ...
            shortlist, times = verify_plan(run.film_hits, run.duration_s)
            if shortlist and times:
                try:
                    run.extend_at_times(times, first_id=-100000, views=first, shortlist=shortlist)
                    hit, ranked = pv2_decide(run.film_hits)
                    where += ", + verifier (%d films, %d frames)" % (len(shortlist), len(times))
                except (RuntimeError, AttributeError) as e:
                    # The shortlist search slices each film's rows out of a FLAT index, where
                    # they are one contiguous block. The pod's IVF index keeps no such block
                    # and cannot hand rows back without a direct map, so there the verifier
                    # needs the films' codes from the shard files instead - not built yet.
                    # Until then it steps aside rather than failing the clip.
                    where += ", verifier unavailable on this index (%s)" % str(e)[:60]

        if hit is None and resample and ranked:
            # Nothing passed, but some film is in the running. Look again, densely, around
            # the moments that already matched - and only at the shortlisted films, so the
            # round costs the same whether the catalogue holds 134 films or 14,686.
            shortlist = [int(v) for _, _, v, _ in ranked[:PV2_SHORTLIST]]
            resample_candidates(video_path, index, groups, run.film_hits, shortlist,
                                maxdim=maxdim, run=run)
            hit, ranked = pv2_decide(run.film_hits)
            where += ", + second round"

        ev = run.evidence()
        card = pv2_scorecard(run.film_hits, run.cells)
        if hit is None:
            return None, ranked, card
        print(f"[PROBE-V2] {hit['tier']} HIT in {ev['elapsed_s']:.1f}s ({where}, "
              f"{len(run.consumed)}/{run.n_samples} frames; seek {ev['seek_s']:.1f}s "
              f"hash {ev['hash_s']:.1f}s search {ev['search_s']:.1f}s): "
              f"vidx={hit['vidx']} {hit['detail']} -> early accept")
        return hit, ranked, card
    finally:
        run.close()


def identify_clip(video_path: str, index: LoadedIndex, *, verbose: bool = True, prescan: bool = True) -> ClipResult:
    """Send one clip through the index exactly as the pod does, and print what the pod prints.

    The steps, in order:
      a. the whole-clip pre-scan (40 frames spread over the clip). A hit ends it here.
      b. frame by frame: decode at 8 per second, keep frames that changed, hash the full
         frame (+ a border-trimmed copy for the first 40 frames) and the crops, quality >= 40.
      b2. the probe (rule P0): the first 15+ fingerprints of one crop family, searched once
         after 0.75 s. ONE neighbour under hamming 30 accepts the film on the spot.
      c. every 4 new hashes: search, update the scorecards, run the rules. A rule firing
         ends it here ("[STREAM EARLY EXIT]").
      d. early reject: after 64 hashes with nothing under 47, or 96 hashes with no real
         evidence, stop: this clip is not in the library.
      e. at the end of the clip: the "only film in sight" rules P9E / P9.
      f. print the summary, the top candidates and the hints, like the pod.
    """
    say = print if verbose else (lambda *a, **k: None)
    t_start = time.time()
    w, h, dur = video_wh_duration(video_path)
    qgroup = infer_query_group_from_wh(w, h)
    groups = [g for g in groups_for_clip_shape(qgroup) if g in index.index_by_group] or list(index.index_by_group)
    say("[ORCH][PDQ] starting query...")
    say(f"[ORCH][PDQ] Index ready: 1 shard(s)   ({index.manifest.get('movies_count')} films, {index.manifest.get('hashes_total'):,} fingerprints, groups searched: {groups})")

    movie_stats: Dict[int, dict] = defaultdict(_new_stats)
    hist: Dict[int, dict] = defaultdict(lambda: defaultdict(int))

    # ---- a. the probe V2 (replaces the pre-scan; set PDQ_PROBE_ONLY=1 to also skip the
    #         streaming pass, so the probe is the entire engine) -----------------------------
    if prescan:
        hit, probe_ranked, probe_card = super_probe(video_path, index, groups,
                                                     maxdim=PV2_MAXDIM or None)
        if hit:
            v = int(hit["vidx"])
            st = movie_stats[v]
            st["total_frames"], st["min_hamming"], st["avg_ham"] = hit["frames"], float(hit["min_hamming"]), float(hit["min_hamming"])
            res = ClipResult(True, v, index.label(v), hit["reason"], "SCAN_ACCEPT", "probe-v2 HIT", True,
                             dur, dur, 0, 0, 0, time.time() - t_start,
                             [(hit["frames"], float(hit["min_hamming"]), v, float(hit["offset"]))],
                             [(v, _hamming_range_str(hit["min_hamming"]), hit["frames"], float(hit["min_hamming"]))],
                             movie_stats, wait_seconds_for_reason(hit["reason"]), probe_card)
            _print_outcome(res, index, say)
            return res
        if os.environ.get("PDQ_PROBE_ONLY") == "1":
            hints = [(v, _hamming_range_str(a), n, a) for n, a, v, _ in probe_ranked if a < 45.0]
            hints.sort(key=lambda x: (-x[2], x[3]))
            res = ClipResult(False, None, None, "", "PROBE_NO_MATCH", "probe-v2 found no film it trusts", False,
                             dur, dur, 0, 0, 0, time.time() - t_start, probe_ranked, hints[:50],
                             movie_stats, 0.0, probe_card)
            _print_outcome(res, index, say)
            return res
        say("[PROBE-V2] no accept -> running full pass-1 (cropped)")

    # ---- b. + c. + d. the frame-by-frame pass with streaming checks --------------------
    keep_every = max(1, int(round(CLIP_DECODE_FPS / CLIP_FPS)))
    quality_min = CLIP_QUALITY_MIN
    q_hash: Dict[str, bytearray] = {g: bytearray() for g in groups}
    total_hashes = decoded = kept = 0
    last_kept_i = 0
    prev_small = None
    last_checked = 0
    closest_any = 999
    exit_kind, exit_reason, reached_end = "VIDEO_END", "decoded until end-of-video", True
    accept: Optional[dict] = None
    pending: Optional[dict] = None
    last_ts = 0.0
    probe = {"group": probe_group_for(qgroup), "t0": None, "done": False, "hashes": [], "lowered": False}
    if probe["group"] not in groups:
        probe["group"] = "FULL"

    for fr in iter_frames(video_path, fps=CLIP_DECODE_FPS, maxdim=CLIP_MAXDIM):
        decoded += 1
        frame, ts = fr.rgb, float(fr.timestamp)
        if kept >= CLIP_MAX_FRAMES:
            exit_kind, exit_reason, reached_end = "MAX_QUERY_FRAMES", f"kept_frames={kept} >= max_query_frames={CLIP_MAX_FRAMES}", False
            break
        # ---- early reject (the pod's PDQ_EARLY_REJECT, on by default) ----
        if total_hashes >= REJECT_MIN_HASHES:
            rej = None
            if closest_any < 999 and closest_any > REJECT_HAMMING:
                rej = f"best_hamming={closest_any}>{REJECT_HAMMING}"
            elif total_hashes >= REJECT_NOEV_MIN_HASHES:
                ev = max((3 * s["frames_0_20"] + 2 * s["frames_20_35"] + s["frames_35_45"] for s in movie_stats.values()), default=0)
                mh = min((s["min_hamming"] for s in movie_stats.values()), default=float("inf"))
                if closest_any == 999:
                    rej = "no_neighbor_within_radius+probe_negative"
                elif ev < REJECT_MIN_EVIDENCE and mh > REJECT_EVIDENCE_MINHAM:
                    rej = f"no-evidence ev={ev}<{REJECT_MIN_EVIDENCE} mh={mh:.0f}>{REJECT_EVIDENCE_MINHAM} cmin={closest_any}"
            if rej:
                exit_kind, exit_reason, reached_end = "NO_MATCH_REJECT", f"{rej} after {total_hashes} hashes -> no match, early reject", False
                say(f"[REJECT] {exit_reason}")
                break
        if total_hashes >= CLIP_MAX_HASHES:
            exit_kind, exit_reason, reached_end = "MAX_QUERY_HASHES", f"hashes={total_hashes} >= max_query_hashes={CLIP_MAX_HASHES}", False
            break
        # ---- keep this frame only if the picture changed ----
        small = downsample_gray(frame, 32)
        if prev_small is None:
            keep = True
        else:
            keep = frame_change_score(small, prev_small) >= CLIP_CHANGE_THRESH or (decoded - last_kept_i) >= keep_every
        prev_small = small
        if not keep:
            continue
        last_kept_i = decoded
        kept += 1
        last_ts = ts
        if not probe["done"] and probe["t0"] is None:
            probe["t0"] = ts
        # ---- hash the full frame, the trimmed view (first 40 frames), and the crops ----
        targets = []
        if "FULL" in groups:
            targets.append(("FULL", frame))
            if kept <= 40:
                sv = safe_trim_view(frame)
                if sv is not None:
                    targets.append(("FULL", sv))
        for c in CROPS:
            g = group_for_crop_name(c.name)
            if g in groups:
                targets.append((g, center_crop_aspect(frame, c.ar_w, c.ar_h, c.scale)))
        frame_hashes: Dict[str, list] = defaultdict(list)
        for g, img in targets:
            hb, q = pdq_hash(img)
            if q < quality_min:
                continue
            q_hash[g].extend(hb)
            frame_hashes[g].append(hb)
            total_hashes += 1
            if not probe["done"] and g == probe["group"] and len(probe["hashes"]) < PROBE_MAX_STORE:
                probe["hashes"].append(hb)
        # ---- b2. the probe (rule P0), checked before the streaming rules, as the pod does ----
        if not probe["done"] and probe["t0"] is not None:
            elapsed = ts - probe["t0"]
            n_probe = len(probe["hashes"])
            if (elapsed >= PROBE_MIN_S and n_probe >= PROBE_MIN_HASHES) or elapsed >= PROBE_MAX_S:
                if n_probe == 0 and not probe["lowered"] and quality_min > QUALITY_MIN_FLOOR:
                    quality_min = max(QUALITY_MIN_FLOOR, quality_min - 15)
                    probe["lowered"] = True
                    probe["t0"] = ts
                    say(f"[PROBE] lowered quality_min -> {quality_min} (no hashes yet)")
                else:
                    probe["done"] = True
                    # P0 is RETIRED in this engine version. The probe V2 (whole clip, with
                    # corroboration) replaces it; a single frame under 30 from the first four
                    # seconds answers nothing any more. Genuine matches that P0 used to take
                    # are caught by P1/P2 a moment later with more evidence. The old probe
                    # still runs for its other job: lowering the quality bar on clips with no
                    # hashes (the branch above).
                    #
                    # Its index search used to live here. It accepted nothing and its only
                    # consumer was the [PROBE] line below, so it was one whole exhaustive
                    # sweep of up to 64 fingerprints per clip spent on a printout. Removed.
                    # The line still reports what the old probe collected, without searching.
                    say(f"[PROBE] P0 retired; collected {n_probe} fingerprints from "
                        f"group={probe['group']} in {elapsed:.2f}s (no search, nothing accepted)")
        # ---- every 4 new hashes: search, count, run the rules ----
        if total_hashes >= STREAM_START_HASHES and (total_hashes - last_checked) >= STREAM_BATCH_HASHES and frame_hashes:
            last_checked = total_hashes
            # P5 pending: did 3 more seconds of clip pass with nothing better? (checked first, as the pod does)
            if pending and (ts - pending["trigger_ts"]) >= PENDING_WAIT_VIDEO_S:
                accept = dict(pending, reason=pending["reason"] + f" (pending satisfied after {PENDING_WAIT_VIDEO_S}s)")
            touched: set = set()
            if accept is None:
                for g, hl in frame_hashes.items():
                    xq = np.frombuffer(b"".join(hl), dtype=np.uint8).reshape(-1, 32)
                    D, I = index.index_by_group[g].search(xq, K_PER_HASH)
                    if D.size:
                        closest_any = min(closest_any, int(D.min()))
                    _update_stats(movie_stats, touched, D, I, index.meta_vid[g], index.meta_ts[g], ts, hist)
            best = None
            if accept is None:
                for mid in touched:
                    ex = check_early_exit(mid, movie_stats[mid])
                    if not ex:
                        continue
                    if not ex["immediate"]:
                        if pending is None or pending["priority"] > ex["priority"]:
                            pending = dict(ex, trigger_ts=ts)
                        continue
                    if best is None or ex["priority"] < best["priority"]:
                        best = ex
                # P3.5: only one film has any evidence at all, so lower bars are safe
                if best is None and kept >= 2:
                    with_ev = [m for m, s in movie_stats.items() if s["total_frames"] > 0]
                    if len(with_ev) == 1:
                        m = with_ev[0]; s = movie_stats[m]; tot, av = s["total_frames"], s["avg_ham"]
                        tier = None
                        if av <= 20.0 and tot >= 4: tier = "0-20"
                        elif av <= 30.0 and tot >= 7: tier = "20-30"
                        elif av <= 35.0 and tot >= 12: tier = "30-35"
                        elif av <= 45.0 and tot >= 20: tier = "35-45"
                        if tier:
                            best = {"movie_id": m, "priority": 3, "immediate": True, "avg_hamming": av,
                                    "reason": f"P3.5 (Stream-Only-Movie [{tier}]): {tot} frames @ avg_ham={av:.1f} (sole candidate after {ts:.1f}s)"}
                # P1.5: one film leads by 3x with 30+ frames at avg under 18, after 5 s of clip
                if best is None and ts >= 5.0 and touched:
                    rk = sorted(((m, movie_stats[m]["total_frames"], movie_stats[m]["avg_ham"]) for m in touched), key=lambda x: -x[1])
                    m, n1, a1 = rk[0]
                    n2 = rk[1][1] if len(rk) > 1 else 0
                    if n1 >= 30 and a1 < 18.0 and n1 >= 3 * max(n2, 1):
                        best = {"movie_id": m, "priority": 1, "immediate": True, "avg_hamming": a1,
                                "reason": f"P1.5 (Dominant Winner): {n1} frames @ avg_ham={a1:.1f}, runner-up={n2} ({n1 / max(n2, 1):.1f}x)"}
                if best:
                    accept = best
            if accept:
                say(f"[STREAM EARLY EXIT] @ q_ts={ts:.1f}s — {accept['reason']}")
                exit_kind, exit_reason, reached_end = "EARLY_ACCEPT", accept["reason"], False
                break

    # ---- e. end-of-clip rules ---------------------------------------------------------------
    if accept is None and reached_end:
        ex = check_end_of_clip_exit(movie_stats)
        if ex:
            accept = ex
            say(f"[EARLY ACCEPT] {ex['reason']}")

    # ---- f. the summary and the tables, like the pod ----------------------------------------
    query_s = time.time() - t_start
    ranked = []
    for mid, st in movie_stats.items():
        if st["total_frames"] <= 0:
            continue
        off = _best_aligned_bucket_range(hist[mid])[0]
        ranked.append((int(st["total_frames"]), float(st["avg_ham"]), int(mid), float(off)))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    hints = [(v, _hamming_range_str(a), n, a) for n, a, v, _ in ranked if a < 45.0]
    hints.sort(key=lambda x: (-x[2], x[3]))
    res = ClipResult(accept is not None, (int(accept["movie_id"]) if accept else None),
                     (index.label(accept["movie_id"]) if accept else None), (accept["reason"] if accept else ""),
                     exit_kind, exit_reason, reached_end, last_ts, dur, decoded, kept, total_hashes, query_s,
                     ranked, hints[:50], movie_stats, wait_seconds_for_reason(accept["reason"]) if accept else 0.0)
    _print_outcome(res, index, say)
    return res


def _print_outcome(res: ClipResult, index: LoadedIndex, say) -> None:
    """The pod's printout, line for line: the exit summary, the top candidates, the hints,
    and the one line the orchestrator prints when it takes PDQ's answer."""
    say("\n" + "=" * 60)
    say("[QUERY EXIT SUMMARY]")
    say(f"  exit_kind={res.exit_kind}")
    say(f"  reached_end={res.reached_end}")
    say(f"  reason={res.exit_reason}")
    if res.duration_s > 0:
        say(f"  progress={res.progress_s:.2f}s / {res.duration_s:.2f}s")
    say(f"  decoded_frames={res.decoded_frames} kept_frames={res.kept_frames} hashes={res.hashes}")
    say("=" * 60 + "\n")
    say(f"Query time: {res.query_seconds:.2f}s")
    if res.ranked:
        say("Top candidates:")
        for n, avg, v, off in res.ranked[:10]:
            say(f"- matched={n:3d}  avg_hamming={avg:5.1f}  offset={off:7.1f}s  movie={index.label(v)}")
    if res.hints:
        say(f"\nHINTS ({len(res.hints)} movies with avg_hamming < 45):")
        for i, (v, rs, n, avg) in enumerate(res.hints[:10], 1):
            say(f"  {i}. {index.label(v)}")
            say(f"     range={rs}  frames={n}  avg_hamming={avg:.1f}")
        if len(res.hints) > 10:
            say(f"  ...and {len(res.hints) - 10} more")
    if res.early_accept:
        say(f"\n[EARLY EXIT] {res.reason}\n")
        say(f"[ORCH] PDQ early accept → movie_id={res.vidx} ({res.reason})")
        if res.wait_seconds > 0:
            say(f"[ORCH] this exit is from the weak band: the pod would wait {res.wait_seconds:.0f}s for audio or SSCD to disagree before sending it")
    elif res.hints:
        say("\n⚠️ No early accept → printing HINTS (merged; no best guess).")
        say(f"Hints ({len(res.hints)} candidates) — no clear winner: {len(res.hints)} candidate movies")
        say("[ORCH][PDQ] Published hints to shared state (n=%d)" % len(res.hints))
    else:
        say("\nNo candidates found under max_hamming (<45).")
        say("[CLOSEST-ANY TOP] None (index search returned nothing?)\n")

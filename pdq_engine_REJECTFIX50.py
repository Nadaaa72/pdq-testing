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

# --- early reject: give up on a clip that is clearly not in the library ---
REJECT_MIN_CLIP_FRACTION = 0.50  # ... and only once a quarter of the clip has been looked at.
                           #     64 fingerprints is about 1.5 s, so on a 90 s clip the old rule
                           #     gave up having seen under 2% of the video.
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


def load_index(index_dir: str) -> LoadedIndex:
    """Open an index folder. Nothing big is read into memory: the search files and the
    meta arrays are memory-mapped, so the operating system pages in what a search touches
    and lets go of it again when memory is short. A 2 GB index opens in well under a
    second, and the program's own memory stays around 50 MB."""
    index_dir = str(index_dir)
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
        if avg <= 35.0 and total >= 2:
            return {"movie_id": mid, "reason": f"P9E: Only movie overall with avg≤35 (avg={avg:.1f}) and frames={total} (≥2)",
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

    # ---- a. the pre-scan -------------------------------------------------------------------
    if prescan:
        hit = whole_clip_prescan(video_path, index, groups)
        if hit:
            v = int(hit["vidx"])
            st = movie_stats[v]
            st["total_frames"], st["min_hamming"], st["avg_ham"] = hit["frames"], float(hit["min_hamming"]), float(hit["min_hamming"])
            res = ClipResult(True, v, index.label(v), hit["reason"], "SCAN_ACCEPT", "whole-clip pre-scan HIT", True,
                             dur, dur, 0, 0, 0, time.time() - t_start,
                             [(hit["frames"], float(hit["min_hamming"]), v, float(hit["offset"]))],
                             [(v, _hamming_range_str(hit["min_hamming"]), hit["frames"], float(hit["min_hamming"]))],
                             movie_stats, wait_seconds_for_reason(hit["reason"]))
            _print_outcome(res, index, say)
            return res
        say("[SCAN] no early-accept -> running full pass-1 (cropped)")

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
        seen_enough = (dur <= 0) or (ts >= dur * REJECT_MIN_CLIP_FRACTION)
        if total_hashes >= REJECT_MIN_HASHES and seen_enough:
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
                    md, best_v = None, None
                    if n_probe:
                        xq = np.frombuffer(b"".join(probe["hashes"]), dtype=np.uint8).reshape(-1, 32)
                        D, I = index.index_by_group[probe["group"]].search(xq, K_PER_HASH)
                        if D.size:
                            j = int(D.argmin()); md = int(D.flat[j]); nn = int(I.flat[j])
                            if 0 <= nn < len(index.meta_vid[probe["group"]]):
                                best_v = int(index.meta_vid[probe["group"]][nn])
                    likely = md is not None and md < PROBE_ACCEPT_HAMMING
                    say(f"[PROBE] likely_match={likely} min_neighbor_hamming={md} closest_movie={index.label(best_v) if best_v is not None else None} "
                        f"closest_group={probe['group']} hashes={n_probe} elapsed={elapsed:.2f}s")
                    if likely and best_v is not None:
                        say(f"[PROBE] P0 triggered: min_hamming={md}<{PROBE_ACCEPT_HAMMING} → early exit eligible")
                        accept = {"movie_id": best_v, "priority": 0, "immediate": True, "avg_hamming": float(md),
                                  "reason": f"P0: probe min_hamming={md} < {PROBE_ACCEPT_HAMMING}"}
                        st = movie_stats[best_v]
                        if st["total_frames"] == 0:
                            st["total_frames"], st["min_hamming"], st["avg_ham"], st["dist_sum"], st["dist_cnt"] = 1, float(md), float(md), float(md), 1
                        exit_kind, exit_reason, reached_end = "EARLY_ACCEPT", accept["reason"], False
                        break
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

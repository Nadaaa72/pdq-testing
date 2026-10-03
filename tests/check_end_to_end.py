# -*- coding: utf-8 -*-
"""
check_end_to_end.py - the whole road, on one film you have on disk.

    python tests/check_end_to_end.py  path/to/a_film.mp4  [--distractors data/index]

What it does:
  1. fingerprints five minutes of the film (from 20:00, or from the start if it is short)
  2. builds an index in data/tests/index with that slice as one film, plus every film from
     the --distractors index if you give one (your data/index from step 2 is ideal)
  3. cuts four clips with ffmpeg:
       a. 15 s from inside the slice, cropped to a phone's 9:16 shape, re-encoded
       b. 12 s from inside the slice, wide, small and low quality
       c. 15 s from a part of the film that was NOT fingerprinted
       d. 15 s of colour bars, a clip of nothing
  4. sends each through pdq_engine.identify_clip and checks:
       a and b must be accepted as the film.  d must not be accepted.
       c is reported, not judged: on a one-film index the "only film in sight" rules
       (P3.5, P9E, P9) are loose, so c can go either way. On the pod, with 9,500 films,
       it would be rejected.

It takes a few minutes. Everything it writes goes under data/tests/ (ignored by git).
"""
from __future__ import annotations
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import pdq_engine as E  # noqa: E402

OUT = HERE.parent / "data" / "tests"


def ff(*args: str) -> None:
    """Run ffmpeg quietly and stop if it fails."""
    subprocess.run([E.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args], check=True)


def films_from_index(index_dir: Path):
    """Every film of an existing flat index as (label, payload), so it can be rebuilt into another."""
    import faiss
    man = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
    per_film = {}
    for g, files in man["groups"].items():
        idx = faiss.read_index_binary(str(index_dir / files["faiss"]))
        xb = faiss.vector_to_array(idx.xb).reshape(-1, 32)
        vid = np.fromfile(str(index_dir / files["meta_vid"]), dtype="<u8")
        ts = np.fromfile(str(index_dir / files["meta_ts"]), dtype="<f4")
        cr = np.fromfile(str(index_dir / files["meta_crop"]), dtype="<u2")
        for v in np.unique(vid):
            sel = vid == v
            per_film.setdefault(int(v), {})[g] = {"hashes32": xb[sel].tobytes(), "ts_f32": ts[sel].tobytes(), "crop_id_u16": cr[sel].tobytes()}
    for v in sorted(per_film):
        yield man["video_paths"][v], {"version": 1, "video_path": man["video_paths"][v], "crop_vocab": man.get("crop_vocab", []), "groups": per_film[v]}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args or not os.path.isfile(args[0]):
        print("usage: python tests/check_end_to_end.py path/to/a_film.mp4 [--distractors data/index]")
        return 2
    film = args[0]
    distractors = None
    if "--distractors" in sys.argv:
        distractors = Path(sys.argv[sys.argv.index("--distractors") + 1])
    OUT.mkdir(parents=True, exist_ok=True)

    w, h, dur = E.video_wh_duration(film)
    start = 1200.0 if dur > 1500 else 0.0
    slice_len = min(300.0, max(60.0, dur - start - 30.0))
    print(f"film: {film}  ({w}x{h}, {dur / 60:.0f} min). slice: {start:.0f}s to {start + slice_len:.0f}s")

    # 1. the slice, and its fingerprints
    slice_mp4 = OUT / "film_slice.mp4"
    ff("-ss", str(start), "-t", str(slice_len), "-i", film, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(slice_mp4))
    t0 = time.time()
    payload = E.fingerprint_video(str(slice_mp4))
    n = sum(len(v["hashes32"]) // 32 for v in payload["groups"].values())
    print(f"1. fingerprinted the slice in {time.time() - t0:.0f}s: {n} fingerprints")

    # 2. the index
    films = [(f"999001:{Path(film).stem[:40]} slice (tmdb=0)", payload)]
    if distractors:
        films += list(films_from_index(distractors))
    man = E.write_index(str(OUT / "index"), films)
    print(f"2. index built: {man['movies_count']} films, {man['hashes_total']:,} fingerprints")
    index = E.load_index(str(OUT / "index"))

    # 3. the clips
    a = OUT / "clip_a_inside_portrait.mp4"
    b = OUT / "clip_b_inside_wide_lowq.mp4"
    c = OUT / "clip_c_unseen_part.mp4"
    d = OUT / "clip_d_nothing.mp4"
    ff("-ss", str(start + slice_len * 0.45), "-t", "15", "-i", film, "-an", "-vf", "crop=ih*9/16:ih,scale=540:960", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", str(a))
    ff("-ss", str(start + slice_len * 0.2), "-t", "12", "-i", film, "-an", "-vf", "scale=854:-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", str(b))
    far = (start + slice_len + 1500.0) if dur > start + slice_len + 1530 else max(0.0, start - 600.0)
    ff("-ss", str(far), "-t", "15", "-i", film, "-an", "-vf", "crop=ih*9/16:ih,scale=540:960", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", str(c))
    ff("-f", "lavfi", "-i", "smptebars=size=540x960:rate=25", "-t", "15", "-c:v", "libx264", "-preset", "veryfast", str(d))
    print("3. four clips cut")

    # 4. identify
    fails = 0
    results = {}
    for name, clip in (("a", a), ("b", b), ("c", c), ("d", d)):
        print("\n" + "#" * 70 + f"\n# clip {name}: {clip.name}\n" + "#" * 70)
        r = E.identify_clip(str(clip), index)
        results[name] = r
    print("\n" + "=" * 70)
    for name, must in (("a", True), ("b", True)):
        r = results[name]
        ok = r.early_accept and r.vidx == 0
        fails += not ok
        print(f"clip {name}: accepted as the film = {ok}   ({r.exit_kind}; {r.reason or r.exit_reason})")
    r = results["d"]
    ok = not r.early_accept
    fails += not ok
    print(f"clip d: not accepted = {ok}   ({r.exit_kind}; {r.reason or r.exit_reason})")
    r = results["c"]
    print(f"clip c (unseen part, reported only): accepted={r.early_accept} film={r.label}  ({r.exit_kind}; {r.reason or r.exit_reason})")
    if r.early_accept and r.vidx == 0 and man["movies_count"] == 1:
        print("   note: with one film in the index the sole-candidate rules are loose. Add --distractors to see the pod's behaviour.")
    print("RESULT:", "PASS" if fails == 0 else "FAIL")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

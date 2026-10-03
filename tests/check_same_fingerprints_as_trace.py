# -*- coding: utf-8 -*-
"""
check_same_fingerprints_as_trace.py - prove the engine makes the pod's fingerprints.

    python tests/check_same_fingerprints_as_trace.py  path/to/any_video.mp4

What it does, with the video you give it:
  1. the list of crops is the pod's list
  2. the frames ffmpeg hands over are byte-identical to the pod's frames, same timestamps
  3. every crop and every fingerprint (32 bytes + quality) is byte-identical to the pod's
  4. the change scores that pick which frames to keep are identical
  5. the film side: pdq_engine.fingerprint_video and the pod's add_video give the same
     fingerprints, timestamps and crop ids, group by group

It imports the pod's own module from ../pdq/. That module calls the programs "ffmpeg"
and "ffprobe" by name, so they must be on your PATH. If only ffmpeg is missing, this
script lends it the one bundled with imageio-ffmpeg. If ffprobe is missing, step 5 is
skipped and says so (steps 1 to 4 still run).

Use a short video (under a minute) or step 5 takes a while.
"""
from __future__ import annotations
import importlib.util
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent / "pdq"))     # the pod module imports cookie_manager from next to itself
import pdq_engine as E  # noqa: E402


def lend_ffmpeg_to_path() -> None:
    """The pod module runs plain 'ffmpeg'. If that is not on PATH, copy the bundled one
    into a temp folder under the name ffmpeg.exe and put that folder first on PATH."""
    if shutil.which("ffmpeg"):
        return
    src = E.ffmpeg_exe()
    if not os.path.isfile(src):
        return
    d = Path(tempfile.gettempdir()) / "pdq_for_nada_ffmpeg"
    d.mkdir(exist_ok=True)
    dst = d / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not dst.exists():
        shutil.copy2(src, dst)
    os.environ["PATH"] = str(d) + os.pathsep + os.environ["PATH"]
    os.environ["PDQ_FFMPEG"] = str(dst)     # and make the engine use the same binary for a fair test


def load_pod_module():
    pdq_dir = HERE.parent.parent / "pdq"
    found = list(pdq_dir.glob("pdq_video_lookup_patched_final_updated.py")) if pdq_dir.is_dir() else []
    if not found:
        print("SKIPPED: this check needs the repo's pdq/ folder next to pdq_for_nada/ (the pod's own module).")
        print("         With only this folder, run tests/check_same_rules_as_trace.py and tests/check_end_to_end.py instead.")
        sys.exit(0)
    f = found[0]
    spec = importlib.util.spec_from_file_location("trace_pdq_lookup", str(f))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> int:
    if len(sys.argv) < 2 or not os.path.isfile(sys.argv[1]):
        print("usage: python tests/check_same_fingerprints_as_trace.py path/to/video.mp4")
        return 2
    clip = sys.argv[1]
    lend_ffmpeg_to_path()
    T = load_pod_module()
    fails = 0

    # 1. the crop list
    mine = [(c.name, c.ar_w, c.ar_h, c.scale) for c in E.CROPS]
    theirs = [(c.name, c.ar_w, c.ar_h, c.scale) for c in T.default_tiktokish_crops()]
    ok = mine == theirs
    fails += not ok
    print(f"1. crop list identical: {ok}")

    # 2. frames and timestamps
    w, h, _ = E.video_wh_duration(clip)
    mine_f = list(E.iter_frames(clip, fps=8.0, maxdim=640))
    # the pod yields a VIEW of one reused buffer, so copy each frame as it comes
    theirs_f = [T.DecodedFrame(rgb=f.rgb.copy(), timestamp=f.timestamp)
                for f in T.iter_frames_ffmpeg_fast(clip, fps=8.0, maxdim=640, stream_wh=(w, h))]
    same = sum(np.array_equal(a.rgb, b.rgb) and abs(a.timestamp - b.timestamp) < 1e-9 for a, b in zip(mine_f, theirs_f))
    ok = len(mine_f) == len(theirs_f) and same == len(mine_f)
    fails += not ok
    print(f"2. frames byte-identical: {same}/{len(mine_f)} (pod gave {len(theirs_f)}), shape {mine_f[0].rgb.shape}: {ok}")

    # 3. crops and fingerprints on those frames
    import pdqhash
    n_hash = n_same = n_crop = n_crop_same = 0
    for fr in mine_f[:24]:
        for c in E.CROPS:
            a = E.center_crop_aspect(fr.rgb, c.ar_w, c.ar_h, c.scale)
            b = T.center_crop_aspect(fr.rgb, c.ar_w, c.ar_h, c.scale)
            n_crop += 1
            n_crop_same += np.array_equal(a, b)
        for img in [fr.rgb] + [E.center_crop_aspect(fr.rgb, c.ar_w, c.ar_h, c.scale) for c in E.CROPS]:
            hb, q = E.pdq_hash(img)
            hv, q2 = pdqhash.compute(img)
            n_hash += 1
            n_same += (hb == T.pdq_vector_to_bytes32(hv) and q == int(q2))
    ok = n_crop_same == n_crop and n_same == n_hash
    fails += not ok
    print(f"3. crops identical {n_crop_same}/{n_crop}; fingerprint bytes + quality identical {n_same}/{n_hash}: {ok}")

    # 4. change scores
    g1 = [E.downsample_gray(f.rgb) for f in mine_f[:10]]
    g2 = [T._downsample_gray(f.rgb) for f in mine_f[:10]]
    ok = all(np.allclose(a, b) for a, b in zip(g1, g2)) and all(
        abs(E.frame_change_score(g1[i - 1], g1[i]) - T._frame_change_score(g2[i - 1], g2[i])) < 1e-6 for i in range(1, len(g1)))
    fails += not ok
    print(f"4. change scores identical: {ok}")

    # 5. the film side, end to end
    if not shutil.which("ffprobe"):
        print("5. film side SKIPPED: the pod's add_video needs 'ffprobe' on PATH and it is not there")
    else:
        ix = T.PDQMultiCropIndex()
        ret = ix.add_video(clip, fps=3.0, maxdim=640, quality_min=40, adaptive=True, decode_fps=8.0, change_thresh=6.0,
                           add_chunk_size=4096, return_payload=True, compress_payload=True, compress_level=3)
        blob = ret[1] if isinstance(ret, tuple) else ret
        theirs_p = E.payload_arrays(E.decode_blob(blob) if isinstance(blob, (bytes, bytearray)) else blob)
        mine_p = E.payload_arrays(E.fingerprint_video(clip))
        ok = True
        for g in sorted(set(theirs_p) | set(mine_p)):
            h1, t1, c1 = theirs_p.get(g, (np.zeros((0, 32), np.uint8), np.zeros(0), np.zeros(0)))
            h2, t2, c2 = mine_p.get(g, (np.zeros((0, 32), np.uint8), np.zeros(0), np.zeros(0)))
            same = len(h1) == len(h2) and np.array_equal(h1, h2) and np.allclose(t1, t2) and np.array_equal(c1, c2)
            ok &= same
            print(f"   {g:9s} pod={len(h1):6d} engine={len(h2):6d} identical={same}")
        fails += not ok
        print(f"5. film side identical: {ok}")

    print("RESULT:", "PASS" if fails == 0 else f"FAIL ({fails} step(s) differ)")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

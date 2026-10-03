# -*- coding: utf-8 -*-
"""
3_identify_clip.py - step 3: which film is this clip from?

    python 3_identify_clip.py  path/to/clip.mp4
    python 3_identify_clip.py  https://www.tiktok.com/@someone/video/123      (downloads it first)
    python 3_identify_clip.py  clip.mp4 --no-prescan      (skip the whole-clip pre-scan, see the rules work)
    python 3_identify_clip.py  clip.mp4 --quiet           (just the one-line verdict)

The index it searches is the one named in INDEX_DIR below. Change that line to point at
another index. The clip goes through pdq_engine.identify_clip, which does exactly what the
pod does and prints exactly what the pod prints. PDQ_BASICS.md explains every line of the
printout; HOW_TO_RUN.md walks through one.

Downloads land in data/clips/ and are kept, so a second run of the same link is instant.
TikTok and Instagram links usually download without a login. YouTube often refuses (403).
If a link fails, save the clip any other way and give the file.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# ============================================================================================
# THE INDEX. Change this line to search a different one.
INDEX_DIR = HERE / "data" / "index"
# ============================================================================================

CLIPS = HERE / "data" / "clips"


def download(url: str, cookies: str | None = None) -> Path:
    """Fetch a clip from a link with yt-dlp. Returns the file. Kept in data/clips/.
    Some sites refuse yt-dlp without a login (YouTube often answers 403). If a link fails,
    save the clip with any tool you like and give this script the file instead."""
    import yt_dlp
    CLIPS.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1])[:80]
    target = CLIPS / f"{safe}.mp4"
    if target.is_file():
        print(f"already downloaded: {target}")
        return target
    opts = {"outtmpl": str(CLIPS / f"{safe}.%(ext)s"), "format": "mp4/best", "quiet": True, "no_warnings": True,
            "merge_output_format": "mp4"}
    if cookies:
        opts["cookiefile"] = cookies      # a cookies.txt exported from your browser, for sites that want a login
    print(f"downloading {url} ...")
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([url])
    found = sorted(CLIPS.glob(f"{safe}.*"), key=lambda p: p.stat().st_mtime)
    if not found:
        raise SystemExit("download failed: no file appeared in data/clips/")
    return found[-1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Step 3: identify one clip against your index.")
    ap.add_argument("clip", help="a video file, or a link (TikTok, Instagram, YouTube ...)")
    ap.add_argument("--no-prescan", action="store_true", help="skip the whole-clip pre-scan so the streaming rules decide")
    ap.add_argument("--quiet", action="store_true", help="print only the verdict")
    ap.add_argument("--index", help="use this index folder instead of INDEX_DIR at the top of the file")
    ap.add_argument("--cookies", metavar="FILE", help="a cookies.txt for yt-dlp, for links that need a login")
    a = ap.parse_args()

    import pdq_engine as E
    index_dir = Path(a.index) if a.index else INDEX_DIR
    if not (index_dir / "manifest.json").is_file():
        raise SystemExit(f"no index at {index_dir}. Run  python 2_build_index.py  first, or fix INDEX_DIR at the top of this file.")
    clip = download(a.clip, a.cookies) if re.match(r"^https?://", a.clip) else Path(a.clip)
    if not clip.is_file():
        raise SystemExit(f"no such file: {clip}")

    t0 = time.time()
    index = E.load_index(str(index_dir))
    if not a.quiet:
        print(f"index: {index_dir}  ({index.manifest.get('movies_count')} films, {index.manifest.get('hashes_total'):,} fingerprints, opened in {time.time() - t0:.2f}s, memory-mapped)")
        print(f"clip:  {clip}\n")
    r = E.identify_clip(str(clip), index, verbose=not a.quiet, prescan=not a.no_prescan)

    print("\n" + "-" * 60)
    if r.early_accept:
        print(f"VERDICT: {r.label}")
        print(f"         rule: {r.reason}")
        if r.wait_seconds:
            print(f"         weak band: the pod would hold this answer {r.wait_seconds:.0f}s for audio or SSCD to object")
    elif r.hints:
        print(f"VERDICT: no film accepted. {len(r.hints)} hint(s); best: {index.label(r.hints[0][0])} "
              f"(frames={r.hints[0][2]}, avg_hamming={r.hints[0][3]:.1f})")
    else:
        print("VERDICT: no film accepted, no hints. This clip is not in your index.")
    print(f"         {r.exit_kind}; {r.query_seconds:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

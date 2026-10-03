# -*- coding: utf-8 -*-
"""
make_edited_clips.py - build edited copies of clips the engine already identifies.

    python make_edited_clips.py              (8 source clips, all edits)
    python make_edited_clips.py --max 4      (fewer sources while experimenting)

Takes clips from the CORRECT list that the pod's rules reliably identify (read from
output/attribution_ORIGINAL.csv, so run attribute_rules.py first) and applies the kinds
of edit TikTok creators actually make: mirror, speed change, crop, zoom, filters,
captions, letterboxing, rotation, heavy re-compression.

Each edit is applied to the ORIGINAL clip separately, so when an edit breaks
identification we know exactly which edit did it.

Output: data/clips_edited/<clip>__<edit>.mp4 and data/edited_clips.csv (file, film, edit).
Existing files are kept, so it is safe to rerun.
"""
from __future__ import annotations

import argparse
import csv
import io
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
CLIPS = HERE / "data" / "clips"
OUT = HERE / "data" / "clips_edited"
ATTR = HERE / "output" / "attribution_ORIGINAL.csv"


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


# Every edit is a list of ffmpeg video-filter / option fragments. Audio is dropped (-an):
# PDQ never hears it, and it keeps the files small.
EDITS: dict[str, list[str]] = {
    # the classic repost trick: mirror the picture so copyright matching misses it
    "mirror":    ["-vf", "hflip"],
    # speed changes: common to dodge detection and fit TikTok's length limits.
    # NOTE: this changes the clip-time to film-time relationship, which is exactly
    # what the offset-agreement checks assume is fixed.
    "speed125":  ["-vf", "setpts=PTS/1.25"],
    "speed080":  ["-vf", "setpts=PTS/0.8"],
    # zoom in 20%: crops the edges away, keeps the middle
    "zoom120":   ["-vf", "crop=iw/1.2:ih/1.2,scale=iw*1.2:ih*1.2"],
    # a colour filter, like an Instagram filter over the whole clip
    "filter":    ["-vf", "eq=saturation=1.6:contrast=1.15:brightness=0.06"],
    # black and white
    "gray":      ["-vf", "hue=s=0"],
    # letterbox into a phone screen: the film floats in black bars
    "letterbox": ["-vf", "scale=iw*0.75:ih*0.75,pad=iw/0.75:ih/0.75:(ow-iw)/2:(oh-ih)/2:black"],
    # a caption bar across the top, like creators put over every clip
    "caption":   ["-vf", "drawbox=x=0:y=0:w=iw:h=ih*0.14:color=white@1.0:t=fill,"
                         "drawbox=x=iw*0.1:y=ih*0.03:w=iw*0.8:h=ih*0.03:color=black@1.0:t=fill,"
                         "drawbox=x=iw*0.15:y=ih*0.08:w=iw*0.7:h=ih*0.03:color=black@1.0:t=fill"],
    # a slight rotation, another classic de-matching trick
    "rot2":      ["-vf", "rotate=2*PI/180:fillcolor=black"],
    # heavy re-compression: a clip that has been reposted a few times
    "lowq":      ["-vf", "scale=iw/2:ih/2,scale=iw*2:ih*2", "-b:v", "250k"],
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Build edited copies of reliably-identified clips.")
    ap.add_argument("--max", type=int, default=8, help="how many source clips to edit")
    ap.add_argument("--edits", default="", help="comma list of edits to build (default: all)")
    a = ap.parse_args()

    if not ATTR.is_file():
        raise SystemExit(f"missing {ATTR}. Run attribute_rules.py --engine pdq_engine_ORIGINAL.py first.")
    sources = []
    for r in csv.DictReader(open(ATTR, encoding="utf-8")):
        if r["list"] == "correct" and r["reproduced"] == "yes":
            f = CLIPS / r["clip"]
            if f.is_file():
                sources.append((r["expected_film"], r["rule"], f))
    sources = sources[: a.max]
    if not sources:
        raise SystemExit("no reliably-identified correct clips found in the attribution CSV yet.")

    wanted = [e.strip() for e in a.edits.split(",") if e.strip()] or list(EDITS)
    OUT.mkdir(parents=True, exist_ok=True)
    fx = ffmpeg()

    manifest_path = HERE / "data" / "edited_clips.csv"
    rows = []
    if manifest_path.is_file():
        rows = list(csv.DictReader(open(manifest_path, encoding="utf-8")))
    known = {r["file"] for r in rows}

    print(f"editing {len(sources)} source clips x {len(wanted)} edits -> {OUT}")
    for film, rule, src in sources:
        for edit in wanted:
            dst = OUT / f"{src.stem}__{edit}.mp4"
            if not dst.is_file():
                cmd = [fx, "-y", "-i", str(src), *EDITS[edit], "-an", "-loglevel", "error", str(dst)]
                try:
                    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
                except subprocess.CalledProcessError as e:
                    print(f"  FAILED {dst.name}: {(e.stderr or '').strip()[:160]}")
                    continue
                except subprocess.TimeoutExpired:
                    print(f"  TIMEOUT {dst.name}")
                    continue
                print(f"  made {dst.name}")
            if dst.name not in known:
                rows.append({"file": dst.name, "film": film, "edit": edit,
                             "source": src.name, "unedited_rule": rule})
                known.add(dst.name)

    with open(manifest_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "film", "edit", "source", "unedited_rule"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nmanifest: {manifest_path}  ({len(rows)} edited clips)")
    print("next:  python test_edits.py --engine pdq_engine_ORIGINAL.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

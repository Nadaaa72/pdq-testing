# -*- coding: utf-8 -*-
"""
get_missing_clips.py - download the clips yt-dlp cannot get, the way the pod does.

    python get_missing_clips.py            download everything still missing
    python get_missing_clips.py --list     just show what is missing, download nothing

Why this exists: yt-dlp cannot get past TikTok at all any more, and Instagram answers
"empty media response" for a lot of reels. The pod solves both with the ScrapeCreators
API, using the token already in credentials.env. This script calls the pod's own
downloader so the method stays identical to production.

  TikTok    -> download_tiktok_via_scrapecreators   (the pod calls this after yt-dlp fails)
  Instagram -> download_instagram_via_scrapecreators (the pod calls this FIRST)

Each call costs about 1 ScrapeCreators credit. Run --list first if you want to know how
many that will be before spending any.

A clip that returns HTTP 404 has been deleted from the platform. Nothing can recover it.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import re
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
CLIPS = HERE / "data" / "clips"
POD = Path(r"C:\Users\nadaa\TraceAppOrig-1\TraceApp\backend\pdq\pdq_video_download_smart.py")
LISTS = [("wrong", "wrong_pdq_clips.csv"), ("control", "correct_pdq_clips.csv")]


def already_here(url: str) -> bool:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1])[:80]
    return bool(sorted(CLIPS.glob(safe + ".*")))


def target_for(url: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1])[:80]
    return CLIPS / f"{safe}.mp4"


def load_pod_downloader():
    if not POD.is_file():
        raise SystemExit(f"cannot find the pod downloader at {POD}\n"
                         "It lives in the Trace repo at TraceApp/backend/pdq/.")
    spec = importlib.util.spec_from_file_location("pod_smart", str(POD))
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(POD.parent))
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description="Download the clips yt-dlp cannot get.")
    ap.add_argument("--list", action="store_true", help="show what is missing, download nothing")
    a = ap.parse_args()

    missing = []
    for label, fn in LISTS:
        for r in csv.DictReader(open(HERE / "data" / fn, encoding="utf-8")):
            if not already_here(r["url"]):
                missing.append((label, r["platform"], r["answered_movie"], r["url"]))

    if not missing:
        print("nothing missing - every clip on both lists is already in data/clips/")
        return 0

    by_platform: dict[str, int] = {}
    for _, p, _, _ in missing:
        by_platform[p] = by_platform.get(p, 0) + 1
    print(f"{len(missing)} clips missing: " + ", ".join(f"{n} {p}" for p, n in sorted(by_platform.items())))

    if a.list:
        for label, plat, film, url in missing:
            print(f"   [{label:7}] {plat:10} {film[:36]:38} {url[:54]}")
        print(f"\nDownloading these would cost about {len(missing)} ScrapeCreators credits.")
        return 0

    CLIPS.mkdir(parents=True, exist_ok=True)
    mod = load_pod_downloader()

    from dotenv import load_dotenv
    load_dotenv(HERE / "credentials.env")

    ok = gone = failed = 0
    for label, plat, film, url in missing:
        out = target_for(url)
        fn = (mod.download_tiktok_via_scrapecreators if plat == "tiktok"
              else mod.download_instagram_via_scrapecreators if plat == "instagram"
              else None)
        if fn is None:
            print(f"  SKIP  [{label:7}] {film[:34]:36} (platform '{plat}' has no pod route)")
            continue
        try:
            res = fn(url, str(out))
        except Exception as e:
            res = None
            print(f"        error: {str(e)[:90]}")
        if res and Path(res).is_file():
            ok += 1
            print(f"  OK    [{label:7}] {film[:34]:36} {round(Path(res).stat().st_size / 1024)} KB")
        else:
            failed += 1
            print(f"  FAIL  [{label:7}] {film[:34]:36} (deleted from the platform, or refused)")
        time.sleep(0.5)

    print(f"\ndownloaded {ok}, failed {failed}")
    if failed:
        print("A failure is almost always HTTP 404, meaning the post has been taken down.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

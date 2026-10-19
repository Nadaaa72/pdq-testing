# -*- coding: utf-8 -*-
"""
get_heldout_clips.py - build a HELD-OUT test set: clips the rules were never fitted on.

    python get_heldout_clips.py --list           pick the set, write the manifest, download nothing
    python get_heldout_clips.py                  download whatever the manifest still lacks
    python get_heldout_clips.py --in-index 50 --out-index 50

Why this exists. Every accuracy figure measured so far comes from data/correct_pdq_clips.csv
and data/wrong_pdq_clips.csv - the same clips the probe's bars were tuned on. Those numbers
are an upper bound on real behaviour, not an estimate of it. This script assembles a set
that is outside every fit, from clips where:

  * a user CONFIRMED the film, so the truth comes from a human, and
  * PDQ did not answer, so nothing about PDQ was tuned on it.

Another engine (sscd, audio, gemini, face) gave the answer and a user pressed "correct".
That is good truth but not perfect: a careless press is possible, and nobody re-checked the
film by hand. Say so when quoting any number that rests on it.

The set has two halves, because they answer different questions:

  in-index    the film IS one of the 134 in data/index  -> can the probe FIND it?  (recall)
  out-index   the film is NOT in the index              -> does the probe STAY QUIET?
                                                           (false positives, which is the
                                                           failure users actually notice)

Clips land in data/clips_heldout/, never in data/clips/, so the fitted suite stays exactly
as it was and the two can never be confused.

Each download costs about one ScrapeCreators credit. Only tiktok and instagram have a pod
route, so other platforms are left out rather than spending a credit to fail.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import random
import re
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
CLIPS = HERE / "data" / "clips_heldout"
MANIFEST = HERE / "data" / "heldout_clips.csv"
INDEX_CONTENTS = HERE / "data" / "index" / "index_contents.txt"
POD = Path(r"C:\Users\nadaa\TraceAppOrig-1\TraceApp\backend\pdq\pdq_video_download_smart.py")

# the pod can only fetch these two; anything else would burn a credit for nothing
ROUTED = ("tiktok", "instagram")
FIELDS = ["pool", "url", "platform", "truth_film", "truth_tmdb", "truth_engine",
          "correct_votes", "in_catalogue"]
SEED = 20261010          # fixed, so the same 100 clips come back on a re-run


def indexed_tmdb_ids():
    ids = set()
    for line in io.open(INDEX_CONTENTS, encoding="utf-8"):
        m = re.search(r"tmdb=(\d+)", line)
        if m:
            ids.add(int(m.group(1)))
    if not ids:
        raise SystemExit("no tmdb ids found in %s" % INDEX_CONTENTS)
    return ids


def database_url():
    for line in io.open(HERE / "credentials.env", encoding="utf-8"):
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("DATABASE_URL is not in credentials.env")


def pool_from_database(n_in, n_out):
    """The two halves, drawn read-only from the pod's database and sampled with a fixed seed."""
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        raise SystemExit("psycopg2 is not installed. Run: pip install -r requirements.txt")
    ids = indexed_tmdb_ids()
    con = psycopg2.connect(database_url(), connect_timeout=25)
    con.set_session(readonly=True, autocommit=True)
    with con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT url, platform, tmdb_id, movie_name, match_source, correct_count
                 FROM traced_clips
                WHERE correct_count > 0
                  AND coalesce(wrong_count, 0) = 0
                  AND coalesce(match_source, '') <> 'pdq'
                  AND url IS NOT NULL AND tmdb_id IS NOT NULL
                  AND platform IN %s
                ORDER BY url""", (ROUTED,))
        rows = cur.fetchall()
    con.close()

    inx = [r for r in rows if int(r["tmdb_id"]) in ids]
    out = [r for r in rows if int(r["tmdb_id"]) not in ids]
    print("candidates: %d with the film in the index, %d without" % (len(inx), len(out)))

    rnd = random.Random(SEED)
    # One clip per film in the out-of-index half, so 50 clips are 50 different films rather
    # than fifty reposts of one - a repeated film would turn the false-positive rate into a
    # measurement of a single title.
    by_film = {}
    for r in out:
        by_film.setdefault(int(r["tmdb_id"]), []).append(r)
    one_each = [rnd.choice(v) for _, v in sorted(by_film.items())]
    rnd.shuffle(one_each)

    inx = sorted(inx, key=lambda r: r["url"])
    rnd.shuffle(inx)

    picked = [("in-index", r) for r in inx[:n_in]] + [("out-index", r) for r in one_each[:n_out]]
    return [{"pool": pool,
             "url": r["url"].strip(),
             "platform": r["platform"],
             "truth_film": r["movie_name"] or "",
             "truth_tmdb": r["tmdb_id"],
             "truth_engine": r["match_source"] or "",
             "correct_votes": r["correct_count"],
             "in_catalogue": "yes" if pool == "in-index" else "no"}
            for pool, r in picked]


def safe_name(url):
    return re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1])[:80]


def target_for(url):
    return CLIPS / (safe_name(url) + ".mp4")


def already_here(url):
    return bool([p for p in sorted(CLIPS.glob(safe_name(url) + ".*")) if p.stat().st_size > 0])


def load_pod_downloader():
    if not POD.is_file():
        raise SystemExit("cannot find the pod downloader at %s" % POD)
    spec = importlib.util.spec_from_file_location("pod_smart", str(POD))
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(POD.parent))
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description="Build a held-out clip set.")
    ap.add_argument("--list", action="store_true", help="pick the set and write the manifest only")
    ap.add_argument("--in-index", type=int, default=50, help="clips whose film IS indexed")
    ap.add_argument("--out-index", type=int, default=50, help="clips whose film is NOT indexed")
    ap.add_argument("--refresh", action="store_true", help="re-pick even if a manifest exists")
    a = ap.parse_args()

    if MANIFEST.is_file() and not a.refresh:
        rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))
        print("using the existing manifest: %s (%d clips)" % (MANIFEST.name, len(rows)))
    else:
        rows = pool_from_database(a.in_index, a.out_index)
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        with open(MANIFEST, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        print("wrote %s (%d clips)" % (MANIFEST, len(rows)))

    have = [r for r in rows if already_here(r["url"])]
    missing = [r for r in rows if not already_here(r["url"])]
    counts = {}
    for r in missing:
        counts[r["pool"]] = counts.get(r["pool"], 0) + 1
    print("already downloaded %d, still to fetch %d  %s"
          % (len(have), len(missing),
             ", ".join("%d %s" % (n, p) for p, n in sorted(counts.items()))))

    if a.list:
        for r in rows[:12]:
            print("   [%-9s] %-10s %-34s %s"
                  % (r["pool"], r["platform"], r["truth_film"][:32], r["url"][:50]))
        if len(rows) > 12:
            print("   ... and %d more" % (len(rows) - 12))
        print()
        print("Downloading the %d missing ones costs about %d ScrapeCreators credits."
              % (len(missing), len(missing)))
        return 0

    if not missing:
        print("nothing to do")
        return 0

    CLIPS.mkdir(parents=True, exist_ok=True)
    mod = load_pod_downloader()
    from dotenv import load_dotenv
    load_dotenv(HERE / "credentials.env")

    ok = failed = 0
    for n, r in enumerate(missing, 1):
        out = target_for(r["url"])
        fn = (mod.download_tiktok_via_scrapecreators if r["platform"] == "tiktok"
              else mod.download_instagram_via_scrapecreators if r["platform"] == "instagram"
              else None)
        if fn is None:
            print("  SKIP  [%s] %s has no pod route" % (r["pool"], r["platform"]))
            continue
        try:
            res = fn(r["url"], str(out))
        except Exception as e:
            res = None
            print("        error: %s" % str(e)[:90])
        if res and Path(res).is_file() and Path(res).stat().st_size > 0:
            ok += 1
            print("  OK   %3d/%d [%-9s] %-32s %d KB"
                  % (n, len(missing), r["pool"], r["truth_film"][:30],
                     round(Path(res).stat().st_size / 1024)))
        else:
            failed += 1
            print("  FAIL %3d/%d [%-9s] %-32s (taken down, or refused)"
                  % (n, len(missing), r["pool"], r["truth_film"][:30]))
        time.sleep(0.5)

    print()
    print("downloaded %d, failed %d" % (ok, failed))
    if failed:
        print("A failure is almost always HTTP 404 - the post has been deleted. Nothing can")
        print("recover it. Re-run with --refresh to draw replacements for the ones that died.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

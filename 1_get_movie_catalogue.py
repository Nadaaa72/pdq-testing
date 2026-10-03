# -*- coding: utf-8 -*-
"""
1_get_movie_catalogue.py - step 1: find out which films exist, and pick a starter list.

    python 1_get_movie_catalogue.py
    python 1_get_movie_catalogue.py --starter 30          (how many films go on the starter list)
    python 1_get_movie_catalogue.py --local-shards DIR    (no internet: read manifests from a folder)

What it writes, in data/:
  movies_catalogue.csv     every film the pod knows: id, title, tmdb id, sizes, whether it has
                           a fingerprint file, whether it is in the pod's live index.
  movies_to_include.txt    a starter list of films for YOUR index. Edit it: delete lines, or
                           paste lines in from the catalogue. Then run 2_build_index.py.
                           It is never overwritten once it exists (use --new-list to redo it).

Where the facts come from:
  - the pod's index pieces in B2 each carry a manifest.json that names its films, as
    "id:Title (tmdb=NNN)". Reading every manifest gives the full list of indexed films.
  - the fingerprint files in B2 are named movie_<id>.blob. Listing that folder gives the
    size of each one. The index a film makes is about 1.5 times its blob.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CATALOGUE = DATA / "movies_catalogue.csv"
LIST = DATA / "movies_to_include.txt"
WRONG_LIST = DATA / "wrong_pdq_clips.csv"      # written by 4_pull_wrong_pdq_clips.py, if you ran it

INDEX_BYTES_PER_BLOB_BYTE = 1.5    # measured on real films: the flat index is ~1.5x the blob
LABEL_RE = re.compile(r"^(\d+):(.*?)\s*\(tmdb=([^)]*)\)\s*$")


def parse_label(label: str):
    """'3112:Interstellar (tmdb=157336)' -> (3112, 'Interstellar', '157336'). Odd labels still parse."""
    m = LABEL_RE.match(label.strip())
    if m:
        return int(m.group(1)), m.group(2).strip(), m.group(3).strip()
    head, _, rest = label.partition(":")
    try:
        return int(head), rest.strip() or label, ""
    except ValueError:
        return -1, label.strip(), ""


def films_from_manifests(manifests) -> dict:
    """manifests = iterable of (shard name, manifest dict). Returns {movie_id: row}."""
    films = {}
    for shard, man in manifests:
        for label in man.get("video_paths", []):
            mid, title, tmdb = parse_label(label)
            if mid < 0:
                continue
            films.setdefault(mid, {"movie_id": mid, "title": title, "tmdb_id": tmdb, "label": label.strip(),
                                   "shard": shard, "in_pod_index": "yes", "has_blob": "no", "blob_mb": "", "index_mb": ""})
    return films


def from_b2(cfg_path_note: str = "") -> dict:
    """The real thing: read every shard manifest and list every blob in the bucket."""
    from b2_access import B2
    b2 = B2()
    shards_prefix = b2.cfg["B2_SHARDS_PREFIX"]
    blob_prefix = b2.cfg["B2_PDQ_BLOB_PREFIX"]
    print(f"listing index pieces under {shards_prefix} ...")
    keys = [k for k, _ in b2.list_keys(shards_prefix) if k.endswith("/manifest.json")]
    print(f"  {len(keys)} manifests. reading them (8 at a time) ...")

    def fetch(k):
        try:
            return k.rsplit("/", 2)[-2], json.loads(b2.get_bytes(k).decode("utf-8"))
        except Exception as e:  # one bad manifest must not stop the whole catalogue
            print(f"  could not read {k}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        manifests = [m for m in pool.map(fetch, keys) if m]
    films = films_from_manifests(manifests)
    print(f"  {len(films)} films named in the pod's index")

    print(f"listing fingerprint files under {blob_prefix} ...")
    n_blobs = 0
    for key, size in b2.list_keys(blob_prefix):
        m = re.search(r"movie_(\d+)\.blob$", key)
        if not m:
            continue
        n_blobs += 1
        mid = int(m.group(1))
        row = films.get(mid)
        if row is None:
            row = films[mid] = {"movie_id": mid, "title": "", "tmdb_id": "", "label": f"{mid}:(not in the pod index yet) (tmdb=)",
                                "shard": "", "in_pod_index": "no"}
        row["has_blob"] = "yes"
        row["blob_mb"] = f"{size / 1e6:.1f}"
        row["index_mb"] = f"{size * INDEX_BYTES_PER_BLOB_BYTE / 1e6:.1f}"
    print(f"  {n_blobs} fingerprint files")
    return films


def from_local_shards(folder: Path) -> dict:
    """No internet: manifests from a folder of shards on disk. Sizes come from the meta files."""
    import numpy as np
    manifests = []
    for man_path in sorted(folder.glob("*/manifest.json")):
        manifests.append((man_path.parent.name, json.loads(man_path.read_text(encoding="utf-8"))))
    films = films_from_manifests(manifests)
    counts = {}
    for shard, man in manifests:
        for g, f in man.get("groups", {}).items():
            p = folder / shard / f["meta_vid"]
            if not p.is_file():
                continue
            vid = np.fromfile(str(p), dtype="<u8")
            labels = man["video_paths"]
            uniq, n = np.unique(vid, return_counts=True)
            for v, c in zip(uniq.tolist(), n.tolist()):
                mid = parse_label(labels[v])[0]
                counts[mid] = counts.get(mid, 0) + c
    for mid, row in films.items():
        n = counts.get(mid, 0)
        row["has_blob"] = "yes" if n else "no"
        row["index_mb"] = f"{n * 46 / 1e6:.1f}"
        row["blob_mb"] = f"{n * 46 / INDEX_BYTES_PER_BLOB_BYTE / 1e6:.1f}"
    print(f"  {len(films)} films in {len(manifests)} local manifests")
    return films


def write_catalogue(films: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    cols = ["movie_id", "title", "tmdb_id", "has_blob", "in_pod_index", "blob_mb", "index_mb", "shard", "label"]
    with open(CATALOGUE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for mid in sorted(films):
            w.writerow({c: films[mid].get(c, "") for c in cols})
    print(f"wrote {CATALOGUE}  ({len(films)} films)")


def wrong_answer_film_ids() -> list:
    """Films that PDQ answered wrongly, if 4_pull_wrong_pdq_clips.py has run. They make the
    best starter films, because those are the ones whose rules need looking at."""
    if not WRONG_LIST.is_file():
        return []
    ids = []
    with open(WRONG_LIST, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            for col in ("answered_movie_id", "movie_id"):
                if row.get(col, "").strip().isdigit():
                    ids.append(int(row[col]))
                    break
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def write_starter_list(films: dict, n: int, seed: int) -> None:
    usable = [mid for mid, r in films.items() if r["has_blob"] == "yes" and r["in_pod_index"] == "yes"]
    if not usable:
        usable = [mid for mid, r in films.items() if r["has_blob"] == "yes"]
    chosen = [mid for mid in wrong_answer_film_ids() if mid in films and films[mid]["has_blob"] == "yes"][:n]
    rest = [mid for mid in usable if mid not in chosen]
    random.Random(seed).shuffle(rest)
    chosen += rest[: max(0, n - len(chosen))]
    total_mb = sum(float(films[m]["index_mb"] or 0) for m in chosen)
    with open(LIST, "w", encoding="utf-8") as f:
        f.write("# movies_to_include.txt - the films that go into YOUR index.\n")
        f.write("# One film per line: the id, then a | and the name. Only the id at the start matters.\n")
        f.write("# Delete lines you do not want. Paste in lines from data/movies_catalogue.csv.\n")
        f.write("# Lines starting with # are ignored. Then run: python 2_build_index.py\n")
        f.write(f"# This starter list: {len(chosen)} films, about {total_mb:.0f} MB of index.\n")
        f.write("#\n")
        for mid in chosen:
            r = films[mid]
            f.write(f"{mid} | {r['title']} (tmdb={r['tmdb_id']})  [{r['index_mb']} MB]\n")
    print(f"wrote {LIST}  ({len(chosen)} films, about {total_mb:.0f} MB of index)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Step 1: the catalogue of films and a starter list.")
    ap.add_argument("--starter", type=int, default=30, help="how many films on the starter list (default 30)")
    ap.add_argument("--seed", type=int, default=7, help="the random pick is repeatable; change this for a different pick")
    ap.add_argument("--new-list", action="store_true", help="overwrite data/movies_to_include.txt if it exists")
    ap.add_argument("--local-shards", metavar="DIR", help="read manifests from this folder instead of B2 (for testing)")
    a = ap.parse_args()

    films = from_local_shards(Path(a.local_shards)) if a.local_shards else from_b2()
    if not films:
        print("no films found. Check credentials.env and the prefixes in it.")
        return 1
    write_catalogue(films)
    if LIST.is_file() and not a.new_list:
        print(f"kept your existing {LIST.name} (use --new-list to replace it)")
    else:
        write_starter_list(films, a.starter, a.seed)
    print("\nnext: open data/movies_to_include.txt, edit it if you like, then run  python 2_build_index.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""
2_build_index.py - step 2: build YOUR index from the films on your list.

    python 2_build_index.py                         the films in data/movies_to_include.txt
    python 2_build_index.py --target-gb 2           keep the films on the list and add random ones from the
                                                    catalogue until the index is ~2 GB (the list is rewritten to match)
    python 2_build_index.py --from-video film.mp4 --title "Boyhood" --tmdb 85350
                                                    fingerprint a film file you have, add it to the list, build
    python 2_build_index.py --local-shards DIR      testing without internet

What it does:
  1. reads the ids at the start of each line of data/movies_to_include.txt
  2. for each id, uses data/blobs/movie_<id>.blob if it is there, else downloads it from B2
     (a blob is one film's fingerprints; about 3 MB; downloads are kept so a rebuild is instant)
  3. decodes every blob and writes data/index/ in the pod's layout, flat form, plus
     data/index/index_contents.txt listing what went in

Rebuilding: edit the list, run this again. The old index is replaced in one go at the end.
If you prefer, delete data/index first; it makes no difference.

Memory: the index is held in memory while it is built, so a 2 GB index needs about 2.5 GB
free while this runs. Searching it later needs almost none (it is memory-mapped).
"""
from __future__ import annotations

import argparse
import csv
import io
import random
import re
import shutil
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pdq_engine as E  # noqa: E402

DATA = HERE / "data"
BLOBS = DATA / "blobs"
INDEX = DATA / "index"
CATALOGUE = DATA / "movies_catalogue.csv"
LIST = DATA / "movies_to_include.txt"
LOCAL_ID_START = 900001      # films you fingerprint yourself get ids from here up


def read_catalogue() -> dict:
    """{movie_id: row} from data/movies_catalogue.csv, or {} if step 1 has not run."""
    if not CATALOGUE.is_file():
        return {}
    with open(CATALOGUE, encoding="utf-8", newline="") as f:
        return {int(r["movie_id"]): r for r in csv.DictReader(f) if r.get("movie_id", "").strip().lstrip("-").isdigit()}


def read_list(cat: dict | None = None) -> list:
    """The films on the list, in order. A line counts if it starts with a number (the id).
    A line that is just a title, like "Interstellar", is looked up in the catalogue by name.
    Lines nobody can make sense of are reported, never silently dropped."""
    if not LIST.is_file():
        raise SystemExit(f"{LIST} not found. Run  python 1_get_movie_catalogue.py  first.")
    by_title = {}
    for mid, r in (cat or {}).items():
        if r.get("title"):
            by_title.setdefault(r["title"].strip().lower(), mid)
    ids, seen, unknown = [], set(), []
    for raw in LIST.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"(\d+)", line)
        if m:
            mid = int(m.group(1))
        else:
            title = re.split(r"\s*[|(\[]", line, 1)[0].strip().lower()
            mid = by_title.get(title)
            if mid is None:
                unknown.append(raw)
                continue
        if mid not in seen:
            seen.add(mid)
            ids.append(mid)
    for raw in unknown:
        print(f"  NOT IN OUR LIBRARY: \"{raw.strip()}\" is not a film we have. Check the spelling in data/movies_catalogue.csv, or use the id.")
    return ids


def list_line(mid: int, title: str, tmdb: str, index_mb: str) -> str:
    return f"{mid} | {title} (tmdb={tmdb})  [{index_mb} MB]"


def write_list(lines: list, note: str) -> None:
    head = LIST.read_text(encoding="utf-8").splitlines() if LIST.is_file() else []
    comments = [ln for ln in head if ln.startswith("#") and not ln.startswith("# This ")]
    if not comments:
        comments = ["# movies_to_include.txt - the films that go into YOUR index.",
                    "# One film per line: the id, then a | and the name. Only the id at the start matters.",
                    "# Delete lines you do not want. Paste in lines from data/movies_catalogue.csv.",
                    "# Lines starting with # are ignored. Then run: python 2_build_index.py"]
    LIST.write_text("\n".join(comments + [f"# {note}", "#"] + lines) + "\n", encoding="utf-8")


def pick_for_target(cat: dict, target_gb: float, seed: int) -> list:
    """Films from the catalogue, in a repeatable random order, until their index sizes add up."""
    usable = [mid for mid, r in cat.items() if r.get("has_blob") == "yes" and r.get("in_pod_index") == "yes"]
    random.Random(seed).shuffle(usable)
    chosen, total = [], 0.0
    for mid in usable:
        mb = float(cat[mid].get("index_mb") or 0)
        if total + mb > target_gb * 1000.0 and chosen:
            continue
        chosen.append(mid)
        total += mb
        if total >= target_gb * 1000.0:
            break
    return chosen


def check_against_catalogue(ids: list, cat: dict) -> list:
    """Tell the user, per film, when we do not have it. Returns the ids that can be built."""
    if not cat:
        return ids
    ok = []
    for mid in ids:
        r = cat.get(mid)
        if mid >= LOCAL_ID_START or (BLOBS / f"movie_{mid}.blob").is_file():
            ok.append(mid)
        elif r is None:
            print(f"  NOT IN OUR LIBRARY: id {mid} is not in data/movies_catalogue.csv. We do not have this film.")
        elif r.get("has_blob") != "yes":
            print(f"  NO FINGERPRINTS YET: {mid} {r.get('title')} is known but has no fingerprint file in storage. It cannot go in.")
        else:
            ok.append(mid)
    return ok


def fetch_blobs(ids: list, cat: dict, local_shards: Path | None) -> dict:
    """Make sure data/blobs/movie_<id>.blob exists for every id. Returns {id: path}."""
    BLOBS.mkdir(parents=True, exist_ok=True)
    have = {mid: BLOBS / f"movie_{mid}.blob" for mid in ids}
    missing = [mid for mid, p in have.items() if not p.is_file()]
    if not missing:
        print(f"all {len(ids)} blobs already in {BLOBS}")
        return have
    print(f"{len(ids) - len(missing)} blobs already here, {len(missing)} to fetch")
    from tqdm import tqdm
    if local_shards:
        blobs_from_local_shards(missing, local_shards)
    else:
        from b2_access import B2
        b2 = B2()
        prefix = b2.cfg["B2_PDQ_BLOB_PREFIX"]
        failed = []
        for mid in tqdm(missing, unit="film", desc="downloading"):
            try:
                b2.download(f"{prefix}movie_{mid}.blob", str(have[mid]))
            except Exception as e:
                failed.append((mid, str(e).splitlines()[0][:120]))
        for mid, why in failed:
            if "404" in why or "Not Found" in why or "NoSuchKey" in why:
                print(f"  NO FINGERPRINTS IN STORAGE: movie_{mid}.blob does not exist. We do not have this film's fingerprints.")
            else:
                print(f"  could not fetch movie_{mid}.blob: {why}")
    return {mid: p for mid, p in have.items() if p.is_file()}


def blobs_from_local_shards(ids: list, folder: Path) -> None:
    """Testing without internet: rebuild blobs for these ids from a folder of pod shards."""
    import json
    import faiss
    import numpy as np
    want = set(ids)
    for man_path in sorted(folder.glob("*/manifest.json")):
        man = json.loads(man_path.read_text(encoding="utf-8"))
        ids_here = {int(lbl.split(":")[0]): v for v, lbl in enumerate(man["video_paths"]) if lbl.split(":")[0].isdigit()}
        hit = want & set(ids_here)
        if not hit:
            continue
        per = {mid: {} for mid in hit}
        for g, f in man["groups"].items():
            idx = faiss.read_index_binary(str(man_path.parent / f["faiss"]))
            store = faiss.downcast_IndexBinary(idx.storage) if hasattr(idx, "storage") else idx
            xb = faiss.vector_to_array(store.xb).reshape(-1, 32)
            vid = np.fromfile(str(man_path.parent / f["meta_vid"]), dtype="<u8")
            ts = np.fromfile(str(man_path.parent / f["meta_ts"]), dtype="<f4")
            cr = np.fromfile(str(man_path.parent / f["meta_crop"]), dtype="<u2")
            for mid in hit:
                sel = vid == ids_here[mid]
                if sel.any():
                    per[mid][g] = {"hashes32": xb[sel].tobytes(), "ts_f32": ts[sel].tobytes(), "crop_id_u16": cr[sel].tobytes()}
        for mid in hit:
            payload = {"version": 1, "video_path": man["video_paths"][ids_here[mid]], "crop_vocab": ["full"] + [c.name for c in E.CROPS], "groups": per[mid]}
            (BLOBS / f"movie_{mid}.blob").write_bytes(E.encode_blob(payload))


def add_video_file(video: Path, title: str, tmdb: str, movie_id: int | None) -> int:
    """Fingerprint a film file exactly as the pod does, save it as a blob, add it to the list."""
    ids = read_list({}) if LIST.is_file() else []
    if movie_id is None:
        movie_id = max([LOCAL_ID_START - 1] + [i for i in ids if i >= LOCAL_ID_START]) + 1
    BLOBS.mkdir(parents=True, exist_ok=True)
    w, h, dur = E.video_wh_duration(str(video))
    print(f"fingerprinting {video.name}  ({w}x{h}, {dur / 60:.0f} min). This takes about a tenth of the film's length.")
    t0 = time.time()
    last = [0]

    def progress(t):
        if int(t) // 60 > last[0]:
            last[0] = int(t) // 60
            print(f"  {int(t) // 60} min of film done ({time.time() - t0:.0f}s)", flush=True)

    payload = E.fingerprint_video(str(video), progress=progress)
    payload["video_path"] = f"{movie_id}:{title} (tmdb={tmdb})"
    n = sum(len(v["hashes32"]) // 32 for v in payload["groups"].values())
    (BLOBS / f"movie_{movie_id}.blob").write_bytes(E.encode_blob(payload))
    print(f"  {n:,} fingerprints in {time.time() - t0:.0f}s -> {BLOBS / f'movie_{movie_id}.blob'}")
    line = list_line(movie_id, f"{title} (your file: {video.name})", tmdb, f"{n * 46 / 1e6:.1f}")
    if movie_id not in ids:
        with open(LIST, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(f"  added to {LIST.name}: {line}")
    return movie_id


def label_for(mid: int, cat: dict, payload: dict) -> str:
    r = cat.get(mid)
    if r and r.get("title"):
        return r.get("label") or E.make_label(mid, r["title"], r.get("tmdb_id", ""))
    vp = str(payload.get("video_path") or "")
    if re.match(r"^\d+:", vp):
        return vp
    return E.make_label(mid, Path(vp).stem if vp else f"movie {mid}", "")


def build(ids: list, cat: dict, blobs: dict) -> None:
    from tqdm import tqdm
    films = []
    t0 = time.time()
    for mid in tqdm(ids, unit="film", desc="decoding"):
        p = blobs.get(mid)
        if not p:
            continue
        try:
            payload = E.decode_blob(p.read_bytes())
        except Exception as e:
            print(f"  skipping movie_{mid}.blob: not a fingerprint file ({e})")
            continue
        films.append((label_for(mid, cat, payload), payload))
    if not films:
        raise SystemExit("nothing to build: no readable blobs")
    print(f"writing {INDEX} ...")
    man = E.write_index(str(INDEX), films)
    size = sum(f.stat().st_size for f in INDEX.iterdir())
    print(f"done in {time.time() - t0:.0f}s: {man['movies_count']} films, {man['hashes_total']:,} fingerprints, {size / 1e9:.2f} GB on disk")
    print(f"the films inside: {INDEX / 'index_contents.txt'}")
    print("\nnext:  python 3_identify_clip.py path/to/clip.mp4")


def main() -> int:
    ap = argparse.ArgumentParser(description="Step 2: build your index.")
    ap.add_argument("--target-gb", type=float, help="keep the list and add random films from the catalogue until about this many GB of index; the list is rewritten to match")
    ap.add_argument("--seed", type=int, default=7, help="with --target-gb: change for a different pick")
    ap.add_argument("--from-video", metavar="FILE", help="fingerprint this film file, add it to the list, then build")
    ap.add_argument("--title", default="", help="with --from-video: the film's name")
    ap.add_argument("--tmdb", default="", help="with --from-video: the film's TMDB id, if you know it")
    ap.add_argument("--movie-id", type=int, help="with --from-video: the id to give it (default: the next free local id)")
    ap.add_argument("--no-build", action="store_true", help="with --from-video: fingerprint and add to the list, but do not build yet")
    ap.add_argument("--local-shards", metavar="DIR", help="testing without internet: make blobs from this folder of pod shards")
    a = ap.parse_args()

    cat = read_catalogue()
    local = Path(a.local_shards) if a.local_shards else None

    if a.from_video:
        video = Path(a.from_video)
        if not video.is_file():
            raise SystemExit(f"no such file: {video}")
        title = a.title or video.stem
        if not LIST.is_file():
            write_list([], "started by --from-video")
        add_video_file(video, title, a.tmdb, a.movie_id)
        if a.no_build:
            return 0

    if a.target_gb:
        if not cat:
            raise SystemExit("no catalogue yet. Run  python 1_get_movie_catalogue.py  first.")
        # the films already on the list stay (your picks, the wrongly answered ones, your own
        # files); random films from the catalogue are added around them up to the size
        keep = read_list(cat) if LIST.is_file() else []
        keep_mb = sum(float(cat[i].get("index_mb") or 0) for i in keep if i in cat)
        fill = [i for i in pick_for_target(cat, max(0.0, a.target_gb - keep_mb / 1000.0), a.seed) if i not in set(keep)]
        ids = keep + fill
        total = sum(float(cat[i].get("index_mb") or 0) for i in ids if i in cat)
        write_list([list_line(i, cat[i]["title"], cat[i]["tmdb_id"], cat[i]["index_mb"]) if i in cat else f"{i} | (your file)" for i in ids],
                   f"--target-gb {a.target_gb}: {len(keep)} films you had, plus {len(fill)} picked at random = {len(ids)} films, about {total / 1000:.2f} GB of index")
        print(f"kept your {len(keep)} films and added {len(fill)} random ones: {len(ids)} films for about {total / 1000:.2f} GB; the list now matches")
    else:
        ids = read_list(cat)
        if not ids:
            raise SystemExit(f"{LIST} has no films on it")
        print(f"{len(ids)} films on the list")

    ids = check_against_catalogue(ids, cat)
    if not ids:
        raise SystemExit("none of the films on the list can be built")
    blobs = fetch_blobs(ids, cat, local)
    build(ids, cat, blobs)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Part 11: copy the live PDQ index from B2 to this pod's disk, and rebuild the row tables.

    python3 fetch_index.py --dest /local_index

Read-only by construction: the only B2 calls are list_objects_v2, head_object and get_object
(through boto3's download_file). Nothing is put, copied or deleted. The key comes from the
environment (B2_KEY_ID, B2_APP_KEY, B2_BUCKET, B2_ENDPOINT); boot.sh unsets those once this
script returns and deletes nothing else, because nothing else ever holds them.

What is copied (paths checked against the bucket on 5 Nov 2026):
  index_gens/movie_pdq_ivf/CURRENT.json        which ivf generation is live, with sha256s
  <that generation>/ivf_<GROUP>.index|.json     the four IVF indexes (~147 GB)
  pdq_cache_flat_v2/root_manifest.json          the shard order
  pdq_cache_flat_v2/shards/<s>/manifest.json    each shard's film labels
  pdq_cache_flat_v2/shards/<s>/meta_vid_*|meta_ts_*   each shard's row -> film, film time

The row tables (rtmeta) are not stored in B2. The serving pod's are the per-shard tables laid
end to end in root-manifest order, repeats dropped, each shard's film numbers shifted by the
number of films in the shards before it - the rule study/mapping_walk.py proved against the
live pod (0 of 1,449 shards mismatched, 31 Oct). This script builds them by that rule and
writes them where pdq_engine_PROBEV2._load_pod_index looks.

Everything is logged to <dest>/fetch_log.json: bytes, seconds, MB/s per stage, sha256 results,
and the row counts against each ivf's N."""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

GROUPS = ("FULL", "LANDSCAPE", "PORTRAIT", "SQUARE")
SHARDS = "pdq_cache_flat_v2/shards/"
ROOT_MANIFEST = "pdq_cache_flat_v2/root_manifest.json"
CURRENT = "index_gens/movie_pdq_ivf/CURRENT.json"


def client():
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3", endpoint_url=os.environ["B2_ENDPOINT"],
        aws_access_key_id=os.environ["B2_KEY_ID"],
        aws_secret_access_key=os.environ["B2_APP_KEY"],
        config=Config(max_pool_connections=64, retries={"max_attempts": 8, "mode": "adaptive"}))


def listing(c, bucket, prefix):
    tok = None
    while True:
        kw = {"Bucket": bucket, "Prefix": prefix}
        if tok:
            kw["ContinuationToken"] = tok
        r = c.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            yield o["Key"], int(o["Size"])
        if not r.get("IsTruncated"):
            return
        tok = r["NextContinuationToken"]


def get(c, bucket, key, dest: Path, size: int | None = None):
    from boto3.s3.transfer import TransferConfig
    if dest.is_file() and size is not None and dest.stat().st_size == size:
        return 0                                     # resumable: already here
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    cfg = TransferConfig(multipart_threshold=64 << 20, multipart_chunksize=64 << 20,
                         max_concurrency=16, use_threads=True)
    c.download_file(bucket, key, str(tmp), Config=cfg)
    os.replace(tmp, dest)
    return dest.stat().st_size


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(16 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default="/local_index")
    ap.add_argument("--workers", type=int, default=48, help="parallel small-file downloads")
    ap.add_argument("--skip-sha", action="store_true")
    a = ap.parse_args()
    dest = Path(a.dest)
    bucket = os.environ["B2_BUCKET"]
    c = client()
    log = {"started": time.time(), "stages": {}}
    logf = dest / "fetch_log.json"
    dest.mkdir(parents=True, exist_ok=True)

    def save():
        logf.write_text(json.dumps(log, indent=1))

    def stage(name, nbytes, t0, **kw):
        s = time.time() - t0
        log["stages"][name] = dict(bytes=nbytes, seconds=round(s, 1),
                                   mb_s=round(nbytes / 1e6 / max(s, 1e-9), 1), **kw)
        save()
        print("[fetch] %-10s %.1f GB in %.0fs (%.0f MB/s)" % (name, nbytes / 1e9, s, nbytes / 1e6 / max(s, 1e-9)),
              flush=True)

    # 1. which generation is live
    cur = json.loads(c.get_object(Bucket=bucket, Key=CURRENT)["Body"].read())
    log["current"] = {"counts": cur.get("counts"),
                      "files": {k: {"key": v["key"], "bytes": v["bytes"]} for k, v in cur["files"].items()}}
    save()

    # 2. the shard tables first (many small files, the slow part per byte), in parallel with
    #    nothing else so the ivf copy below gets the full link
    t0 = time.time()
    root = json.loads(c.get_object(Bucket=bucket, Key=ROOT_MANIFEST)["Body"].read())
    shard_root = dest / "pdq_cache_flat_v2"
    (shard_root).mkdir(parents=True, exist_ok=True)
    (shard_root / "root_manifest.json").write_text(json.dumps(root))
    names, seen = [], set()
    for s in root["shards"]:
        if s["name"] not in seen:
            seen.add(s["name"])
            names.append(s["name"])
    want = []
    for key, size in listing(c, bucket, SHARDS):
        fn = key.rsplit("/", 1)[-1]
        if fn == "manifest.json" or fn.startswith("meta_vid_") or fn.startswith("meta_ts_"):
            want.append((key, size))
    nbytes = sum(s for _, s in want)
    with cf.ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(lambda ks: get(c, bucket, ks[0], dest / ks[0], ks[1]), want))
    stage("shard_meta", nbytes, t0, files=len(want), shards_in_root=len(names))

    # 3. the four ivf indexes, one after another, each with multipart concurrency
    t0 = time.time()
    ivf = dest / "ivf"
    nbytes = 0
    for fn, meta in sorted(cur["files"].items(), key=lambda kv: kv[1]["bytes"]):
        p = ivf / fn
        tf = time.time()
        get(c, bucket, meta["key"], p, meta["bytes"])
        nbytes += meta["bytes"]
        print("[fetch]   %s %.1f GB %.0fs" % (fn, meta["bytes"] / 1e9, time.time() - tf), flush=True)
    stage("ivf", nbytes, t0)

    # 4. sha256 of every ivf file against CURRENT.json, in parallel
    if not a.skip_sha:
        t0 = time.time()
        with cf.ThreadPoolExecutor(8) as ex:
            res = dict(zip(sorted(cur["files"]), ex.map(lambda fn: sha256(ivf / fn), sorted(cur["files"]))))
        bad = [fn for fn, h in res.items() if h != cur["files"][fn].get("sha256")]
        log["sha256_bad"] = bad
        stage("sha256", 0, t0, checked=len(res), bad=len(bad))
        if bad:
            print("[fetch] SHA256 MISMATCH", bad, flush=True)
            return 2

    # 5. rebuild rtmeta by the mapping-walk rule, cut to each ivf's N
    t0 = time.time()
    rt = dest / "rtmeta"
    rt.mkdir(exist_ok=True)
    # The film list is every label of every shard in that order, NOT deduplicated by film
    # id: the row numbers count every label (mapping_walk.py). pdq_engine_PROBEV2's own
    # _pod_film_list drops repeated ids, which would shift every film after the first repeat,
    # so the engine is pointed at this file through PDQ_POD_FILMS_CACHE and never builds its own.
    offs, film_list = {}, []
    for n in names:
        offs[n] = len(film_list)
        m = json.loads((shard_root / "shards" / n / "manifest.json").read_text())
        film_list += m.get("video_paths") or []
    labels = len(film_list)
    ids = [x.split(":", 1)[0] for x in film_list]
    (dest / "film_list.json").write_text(json.dumps(film_list))
    log["films_in_manifests"] = labels
    log["repeated_film_ids"] = len(ids) - len(set(ids))
    rows_info = {}
    for g in GROUPS:
        N = json.loads((ivf / ("ivf_%s.json" % g)).read_text())["N"]
        fv = open(rt / ("rt_meta_vid_%s__golive.bin" % g), "wb")
        ft = open(rt / ("rt_meta_ts_%s__golive.bin" % g), "wb")
        rows = missing = 0
        for n in names:
            d = shard_root / "shards" / n
            v = sorted(d.glob("meta_vid_%s__*.bin" % g))
            t = sorted(d.glob("meta_ts_%s__*.bin" % g))
            if not v:
                missing += 1
                continue
            sv = np.fromfile(v[0], dtype="<u8").astype(np.int64) + offs[n]
            st = np.fromfile(t[0], dtype="<f4")
            if sv.size != st.size:
                raise SystemExit("shard %s group %s: %d film rows vs %d time rows" % (n, g, sv.size, st.size))
            sv.astype("<i8").tofile(fv)
            st.astype("<f4").tofile(ft)
            rows += sv.size
        fv.close()
        ft.close()
        rows_info[g] = {"ivf_N": N, "rows_built": rows, "shards_without_group": missing,
                        "covers_ivf": rows >= N}
        print("[fetch] rtmeta %-9s N=%d rows=%d covers=%s" % (g, N, rows, rows >= N), flush=True)
    log["rtmeta"] = rows_info
    stage("rtmeta", 0, t0)
    if not all(r["covers_ivf"] for r in rows_info.values()):
        print("[fetch] RTMETA SHORTER THAN IVF", flush=True)
        return 3
    log["finished"] = time.time()
    save()
    return 0


if __name__ == "__main__":
    sys.exit(main())

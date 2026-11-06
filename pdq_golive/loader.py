"""Open the live index group by group, logging what each group costs in memory.

Run 1 (5 Nov 2026) was killed for running out of memory a minute into loading. On that pod:
  - the pod had 62 GB of RAM, not the serving pod's 125 GB, because the launch script fell back
    to a smaller machine when the 125 GB one was out of stock;
  - FULL, LANDSCAPE and SQUARE open with IO_FLAG_MMAP_IFC and leave the process at ~50 MB;
  - PORTRAIT (64 GB, 1.6 billion rows) did not: its anonymous memory climbed past 8 GB inside
    faiss.read_index_binary and kept growing until the kernel killed the run.
So this loader opens the groups smallest first, logs RssAnon after each, and refuses to go on
once anonymous memory passes GOLIVE_MAX_ANON_GB (default 100), instead of being killed with
nothing written. GOLIVE_SKIP_GROUPS (comma list) leaves groups out on purpose; a skipped or
refused group is recorded in the manifest, so every result says which groups it searched.

Everything else matches pdq_engine_PROBEV2._load_pod_index: read-only zero-copy ivf, rtmeta
memory-mapped and cut to each ivf's ntotal, film list from PDQ_POD_FILMS_CACHE."""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import numpy as np


def rss() -> dict:
    out = {}
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith(("VmRSS", "RssAnon", "RssFile")):
                    k, v = line.split(":")
                    out[k] = int(v.split()[0]) // 1024
    except OSError:
        pass
    return out


class _AnonGuard:
    """Ends the process cleanly (exit 4, message flushed) if anonymous memory passes the limit
    while a group is being read. faiss cannot be interrupted, so this is the only clean way
    out; being killed by the kernel leaves an empty log."""

    def __init__(self, limit_gb: float, group: str):
        self.limit_mb = limit_gb * 1024
        self.group = group
        self.stop = threading.Event()
        self.t = threading.Thread(target=self.watch, daemon=True)

    def watch(self):
        while not self.stop.wait(1.0):
            a = rss().get("RssAnon", 0)
            if a > self.limit_mb:
                print("[load] REFUSED: %s pushed anonymous memory to %.1f GB (limit %.0f GB). "
                      "Set GOLIVE_SKIP_GROUPS=%s or use a larger pod." % (
                          self.group, a / 1024, self.limit_mb / 1024, self.group), flush=True)
                os._exit(4)

    def __enter__(self):
        self.t.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()


def load_pod_index(E, index_dir: str):
    import faiss
    skip = {g.strip().upper() for g in os.environ.get("GOLIVE_SKIP_GROUPS", "").split(",") if g.strip()}
    limit = float(os.environ.get("GOLIVE_MAX_ANON_GB", "100"))
    flags = int(getattr(faiss, "IO_FLAG_MMAP_IFC", 0)) | int(getattr(faiss, "IO_FLAG_READ_ONLY", 0))
    paths = sorted(Path(index_dir, "ivf").glob("ivf_*.index"), key=lambda p: p.stat().st_size)
    idx, vid, ts, groups_log = {}, {}, {}, {}
    total = 0
    for path in paths:
        g = path.stem.replace("ivf_", "")
        if g in skip:
            groups_log[g] = {"status": "skipped"}
            print("[load] %-9s skipped (GOLIVE_SKIP_GROUPS)" % g, flush=True)
            continue
        mv = sorted(Path(index_dir, "rtmeta").glob("rt_meta_vid_%s__*.bin" % g))
        mt = sorted(Path(index_dir, "rtmeta").glob("rt_meta_ts_%s__*.bin" % g))
        if not (mv and mt):
            groups_log[g] = {"status": "no rtmeta"}
            continue
        t = time.perf_counter()
        before = rss()
        with _AnonGuard(limit, g):
            shard = faiss.read_index_binary(str(path), flags)
        after = rss()
        if hasattr(shard, "nprobe"):
            shard.nprobe = E.PV2_POD_NPROBE
        n = int(shard.ntotal)
        idx[g] = shard
        vid[g] = np.memmap(str(mv[0]), dtype="<i8", mode="r")[:n]
        ts[g] = np.memmap(str(mt[0]), dtype="<f4", mode="r")[:n]
        total += n
        groups_log[g] = {"status": "loaded", "ntotal": n, "seconds": round(time.perf_counter() - t, 1),
                         "file_gb": round(path.stat().st_size / 1e9, 1),
                         "anon_mb_added": after.get("RssAnon", 0) - before.get("RssAnon", 0),
                         "rss_mb": after.get("VmRSS")}
        print("[load] %-9s %s" % (g, groups_log[g]), flush=True)
    films = E._pod_film_list()
    manifest = {"schema_version": E.INDEX_SCHEMA_VERSION, "movies_count": len(films),
                "hashes_total": total, "groups": {g: {} for g in idx}, "source": "pod",
                "nprobe": E.PV2_POD_NPROBE, "load": groups_log}
    return E.LoadedIndex(dir=index_dir, manifest=manifest, video_paths=films,
                         index_by_group=idx, meta_vid=vid, meta_ts=ts)


def install(E):
    """Make the engine's load_index use this loader for the pod layout."""
    E._load_pod_index = lambda d: load_pod_index(E, d)


def is_unmapped(label: str) -> bool:
    """Rows from a shard whose film table is missing in B2 point at a placeholder film."""
    return str(label).startswith("UNMAPPED:")


if __name__ == "__main__":       # python loader.py: load once and report, nothing else
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run as R
    E, _ = R.load_engine()
    install(E)
    t = time.perf_counter()
    ix = E.load_index(os.environ.get("PDQ_INDEX_DIR", "/local_index"))
    print("[load] done %.1fs films %d groups %s rss %s" % (
        time.perf_counter() - t, len(ix.video_paths), list(ix.index_by_group), rss()), flush=True)

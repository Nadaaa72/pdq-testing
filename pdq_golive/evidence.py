"""Search each clip ONCE and save everything it matched, so every setting can be replayed later.

    python3 evidence.py --manifest m.csv --out DIR --tag golive6 [--shard 0/3]

One pass at 160 pictures with the plain, pixel-mirror, dihedral-mirror and letterbox views
(the engine's views="lab_norot"), frames shrunk to 640 like the index. That covers every
profile we compare: today (p, x), A, B and golive_g16 (p, d, l). probe_lab's replay then scores
any setting, check or fix from these files on the laptop, with no pod.

Writes the three files probe_lab.load_dump reads, with the same columns as
dump_probe_evidence.py / s30_dump.py (the format the earlier real-index dumps used):
  probe_evidence_<tag>.csv          one row per (clip, film, picture, group, view)
  probe_evidence_clips_<tag>.csv    one row per clip, including clips that matched nothing
  probe_evidence_frames_<tag>.csv   one row per picture: its own hash and quality
With --shard i/k only every k-th clip is done and the tag gets a _s<i> suffix, so k processes
can run side by side without sharing a file. Every clip is flushed and fsync'd, clips already
in the clips file are skipped (resumable), and a clip that runs past --timeout seconds is
recorded with a note and skipped."""
from __future__ import annotations

import argparse
import csv
import os
import signal
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import loader as LD          # noqa: E402
from run import load_engine, read_manifest   # noqa: E402

HIT_FIELDS = ["clip", "vidx", "film_label", "sample_i", "clip_t", "film_t", "distance",
              "offset", "group", "view", "target"]
CLIP_FIELDS = ["list", "clip", "expected_film", "in_catalogue", "duration_s", "n_samples",
               "groups", "n_hashes", "index_searches", "films_hit", "hits", "collect_s",
               "resample_s", "shortlist", "note", "edit",
               "seek_s", "hash_s", "search_s", "waves_used", "frames_decoded", "query_rows",
               "truth_tmdb", "n_pictures", "order"]
FRAME_FIELDS = ["clip", "sample_i", "clip_t", "full_hash", "quality"]


class ClipTimeout(Exception):
    pass


def _alarm(signum, frame):
    raise ClipTimeout()


def _open(path: Path, fields):
    new = not path.exists() or path.stat().st_size == 0
    f = open(path, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(f, fieldnames=fields)
    if new:
        w.writeheader()
        f.flush()
    return f, w


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--index", default=os.environ.get("PDQ_INDEX_DIR", "/local_index"))
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default="golive6")
    ap.add_argument("--shard", default="0/1", help="i/k: do every k-th clip, starting at i")
    ap.add_argument("--samples", type=int, default=160)
    ap.add_argument("--maxdim", type=int, default=640)
    ap.add_argument("--views", default="lab_norot")
    ap.add_argument("--timeout", type=int, default=180, help="seconds per clip")
    a = ap.parse_args(argv)

    si, sk = (int(x) for x in a.shard.split("/"))
    tag = a.tag + ("_s%d" % si if sk > 1 else "")
    E, epath = load_engine()
    LD.install(E)
    t = time.perf_counter()
    idx = E.load_index(a.index)
    print("engine %s  films %s  load %.1fs  shard %s" % (
        epath.name, idx.manifest.get("movies_count"), time.perf_counter() - t, a.shard), flush=True)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    hp, cp, fp = (out / ("probe_evidence_%s.csv" % tag), out / ("probe_evidence_clips_%s.csv" % tag),
                  out / ("probe_evidence_frames_%s.csv" % tag))
    done = set()
    if cp.exists():
        done = {r["clip"] for r in csv.DictReader(open(cp, encoding="utf-8"))}
    fh, wh = _open(hp, HIT_FIELDS)
    fc, wc = _open(cp, CLIP_FIELDS)
    ff, wf = _open(fp, FRAME_FIELDS)
    has_alarm = hasattr(signal, "SIGALRM")       # Linux pods; the laptop has none
    if has_alarm:
        signal.signal(signal.SIGALRM, _alarm)

    rows = read_manifest(Path(a.manifest))
    for i, r in enumerate(rows):
        if i % sk != si:
            continue
        p = Path(r["path"])
        name = p.name
        if name in done:
            continue
        row = {k: "" for k in CLIP_FIELDS}
        row.update(list="golive", clip=name, expected_film=r.get("expected_film", ""),
                   in_catalogue=r.get("in_index", ""), truth_tmdb=r.get("expected_tmdb", ""),
                   edit=r.get("group", ""), order="grid")
        t0 = time.time()
        hits, frames = [], []
        try:
            if has_alarm:
                signal.alarm(a.timeout)
            w, h, _ = E.video_wh_duration(str(p))
            groups = [g for g in E.groups_for_clip_shape(E.infer_query_group_from_wh(w, h))
                      if g in idx.index_by_group] or list(idx.index_by_group)
            ev = E.collect_probe_evidence(str(p), idx, groups, a.samples, maxdim=a.maxdim,
                                          views=a.views)
            if has_alarm:
                signal.alarm(0)
            if ev:
                labels = {}
                for (v, s, g, vc), (d, ct, ft, tgt) in sorted(ev.get("cells", {}).items()):
                    labels.setdefault(v, idx.label(v))
                    hits.append(dict(clip=name, vidx=v, film_label=labels[v], sample_i=s,
                                     clip_t="%.3f" % ct, film_t="%.3f" % ft, distance=d,
                                     offset="%.3f" % (ft - ct), group=g, view=vc, target=tgt))
                for s, (hb, q, ct) in sorted((ev.get("sig") or {}).items()):
                    frames.append(dict(clip=name, sample_i=s, clip_t="%.3f" % ct,
                                       full_hash=hb.hex(), quality=q))
                row.update(duration_s="%.1f" % ev["duration_s"], n_samples=ev["n_samples"],
                           groups="|".join(ev["groups"]), films_hit=len(ev["film_hits"]),
                           hits=len(ev.get("cells", {})), n_pictures=ev.get("n_pictures", ""),
                           **{k: ev.get(k, "") for k in ("seek_s", "hash_s", "search_s",
                                                          "frames_decoded", "query_rows",
                                                          "index_searches")})
        except ClipTimeout:
            row["note"] = "timeout %ds" % a.timeout
            hits, frames = [], []
        except Exception as e:                       # an unreadable clip must not stop the pass
            if has_alarm:
                signal.alarm(0)
            row["note"] = ("error " + str(e))[:150]
            hits, frames = [], []
        row["collect_s"] = "%.1f" % (time.time() - t0)
        for x in hits:
            wh.writerow(x)
        for x in frames:
            wf.writerow(x)
        wc.writerow(row)                             # the clip row last: it marks the clip done
        done.add(name)
        for f in (fh, ff, fc):
            f.flush()
            os.fsync(f.fileno())
        print("[%d/%d] %-44s films %-4s hits %-6s %ss %s" % (
            i + 1, len(rows), name[:44], row["films_hit"], row["hits"], row["collect_s"],
            row["note"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

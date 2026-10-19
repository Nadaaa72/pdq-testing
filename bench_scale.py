# -*- coding: utf-8 -*-
"""
bench_scale.py - how does this hold up as the index grows?

    python bench_scale.py --sizes 0.74,2,4,8        (GB targets; rebuilds the index each time)
    python bench_scale.py --sizes 0.74 --clips 20   (a quick pass on the current index)
    python bench_scale.py --no-build                (measure whatever index is on disk now)

The index is a flat FAISS binary index, which means every search is exhaustive: cost grows
LINEARLY with the number of films. Today's 134 films are 16.7 million fingerprints and
0.74 GB. The catalogue is 14,686 films, about 73 GB. Something has to change before then,
and this is the measurement that says what and when.

It writes three files:

  output/bench_scale_summary.csv   one row per index size
  output/bench_scale_clips.csv     one row per (index size, clip)
  output/bench_scale_recall.csv    one row per (index size, clip) against the baseline answer

THE GATE IS THE LAST FILE, NOT THE FIRST. A faster index that stops finding a film is not an
improvement. The smallest index is the baseline, and every larger one is a superset of it
(the film list is pinned, and 2_build_index.py keeps the existing films), so any clip that
stops being answered correctly is a regression caused by the structure, not by the contents.

Note on timing: run this with nothing else going on. Query times here move by a factor of two
under CPU contention, and the index is memory-mapped, so a warm page cache flatters a second
run. Each size is measured cold then warm and both are recorded.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import ctypes.wintypes
import importlib.util
import io
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
INDEX = HERE / "data" / "index"

CLIP_FIELDS = ["index_tag", "films", "vectors", "index_gb", "cache", "clip", "duration_s",
               "query_s", "answered_film", "stage", "rule", "exit_kind", "frames", "avg_hamming"]
SUMMARY_FIELDS = ["index_tag", "films", "vectors", "index_gb", "build_s", "open_s", "rss_mb",
                  "cache", "clips", "query_s_p50", "query_s_p90", "query_s_max",
                  "answers", "s_per_million_vectors"]
RECALL_FIELDS = ["index_tag", "clip", "baseline_answer", "answer", "agrees", "verdict"]


def rss_mb() -> float:
    """This process's working set, in MB. psutil is not installed, so ask Windows directly."""
    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.wintypes.DWORD),
                    ("PageFaultCount", ctypes.wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]
    try:
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return pmc.WorkingSetSize / 1e6
    except Exception:
        return float("nan")


def dir_gb(p: Path) -> float:
    return sum(f.stat().st_size for f in p.glob("*") if f.is_file()) / 1e9


def load_engine(name: str):
    spec = importlib.util.spec_from_file_location("engine_under_test", HERE / name)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["engine_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def measure_one(E, clips, tag: str, cache: str, wc, rc, baseline: dict) -> dict:
    """Open the index fresh, then run every clip through it."""
    t0 = time.time()
    index = E.load_index(str(INDEX))
    open_s = time.time() - t0
    films = int(index.manifest.get("movies_count") or 0)
    vectors = int(index.manifest.get("hashes_total") or 0)
    gb = dir_gb(INDEX)
    rss = rss_mb()
    rows = []
    for i, path in enumerate(clips, 1):
        t = time.time()
        try:
            r = E.identify_clip(str(path), index, verbose=False, prescan=True)
        except Exception as e:
            print("  [%d/%d] %-44s ERROR %s" % (i, len(clips), path.name[:44], e))
            continue
        q = time.time() - t
        stage, rule = ("", "")
        try:
            import attribute_rules as AR
            stage, rule = AR.stage_and_rule(r.reason if r.early_accept else "", r.exit_kind)
        except Exception:
            pass
        st = r.movie_stats.get(r.vidx) if r.vidx is not None else None
        row = {"index_tag": tag, "films": films, "vectors": vectors,
               "index_gb": "%.2f" % gb, "cache": cache, "clip": path.name,
               "duration_s": "%.0f" % r.duration_s, "query_s": "%.2f" % q,
               "answered_film": r.label or "", "stage": stage, "rule": rule,
               "exit_kind": r.exit_kind,
               "frames": (st["total_frames"] if st else ""),
               "avg_hamming": ("%.1f" % st["avg_ham"] if st else "")}
        wc.writerow(row)
        rows.append((q, r.label or ""))
        # the gate: did this index still answer what the baseline answered?
        base = baseline.get(path.name)
        if base is not None:
            agrees = (base == (r.label or ""))
            verdict = ("same" if agrees else
                       ("LOST an answer" if base and not r.label else
                        "NEW answer" if r.label and not base else "CHANGED film"))
            rc.writerow({"index_tag": tag, "clip": path.name, "baseline_answer": base,
                         "answer": r.label or "", "agrees": "yes" if agrees else "no",
                         "verdict": verdict})
        print("  [%d/%d] %-40s %6.2fs  %-10s %s" % (
            i, len(clips), path.name[:40], q, rule, (r.label or "no answer")[:36]))
    qs = [q for q, _ in rows] or [0.0]
    qs_sorted = sorted(qs)
    return {"index_tag": tag, "films": films, "vectors": vectors, "index_gb": "%.2f" % gb,
            "build_s": "", "open_s": "%.3f" % open_s, "rss_mb": "%.0f" % rss, "cache": cache,
            "clips": len(rows), "query_s_p50": "%.2f" % statistics.median(qs),
            "query_s_p90": "%.2f" % qs_sorted[min(len(qs_sorted) - 1, int(0.9 * len(qs_sorted)))],
            "query_s_max": "%.2f" % max(qs), "answers": sum(1 for _, l in rows if l),
            # the number that says whether this scales: seconds per million fingerprints
            "s_per_million_vectors": ("%.4f" % (statistics.median(qs) / (vectors / 1e6))
                                      if vectors else "")}, {n: l for (_, l), n
                                                             in zip(rows, [c.name for c in clips])}


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure how the engine scales with index size.")
    ap.add_argument("--engine", default="pdq_engine_PROBEV2.py")
    ap.add_argument("--sizes", default="",
                    help="comma list of --target-gb values to rebuild the index to, e.g. 0.74,2,4")
    ap.add_argument("--no-build", action="store_true",
                    help="measure the index already on disk and do not rebuild anything")
    ap.add_argument("--clips", type=int, default=0, help="use only the first N clips")
    ap.add_argument("--warm", action="store_true", help="also run a second, warm-cache pass")
    a = ap.parse_args()

    if not INDEX.is_dir():
        raise SystemExit("no index at %s - run 2_build_index.py first" % INDEX)
    E = load_engine(a.engine)

    import attribute_rules as AR
    jobs = AR.load_list("wrong_pdq_clips.csv", "wrong") + AR.load_list("correct_pdq_clips.csv", "correct")
    clips = [p for _, _, _, p in jobs]
    if a.clips:
        clips = clips[:a.clips]
    if not clips:
        raise SystemExit("no clips in data/clips/")

    OUT.mkdir(exist_ok=True)
    fc = open(OUT / "bench_scale_clips.csv", "w", newline="", encoding="utf-8")
    fs = open(OUT / "bench_scale_summary.csv", "w", newline="", encoding="utf-8")
    fr = open(OUT / "bench_scale_recall.csv", "w", newline="", encoding="utf-8")
    wc = csv.DictWriter(fc, fieldnames=CLIP_FIELDS); wc.writeheader()
    ws = csv.DictWriter(fs, fieldnames=SUMMARY_FIELDS); ws.writeheader()
    rc = csv.DictWriter(fr, fieldnames=RECALL_FIELDS); rc.writeheader()

    sizes = [s.strip() for s in a.sizes.split(",") if s.strip()] if a.sizes else [""]
    baseline: dict = {}
    summaries = []
    for k, size in enumerate(sizes):
        if size and not a.no_build:
            print("\n=== rebuilding the index to %s GB ===" % size)
            t0 = time.time()
            r = subprocess.run([sys.executable, str(HERE / "2_build_index.py"),
                                "--target-gb", size], cwd=str(HERE))
            if r.returncode != 0:
                print("  build failed, stopping here")
                break
            build_s = time.time() - t0
        else:
            build_s = None
        tag = ("gb%s" % size) if size else "current"
        print("\n=== measuring %s (%d clips) ===" % (tag, len(clips)))
        s, answers = measure_one(E, clips, tag, "cold", wc, rc, baseline)
        if build_s is not None:
            s["build_s"] = "%.0f" % build_s
        if k == 0:
            baseline = answers          # the smallest index is the yardstick
        ws.writerow(s); fs.flush(); fc.flush(); fr.flush()
        summaries.append(s)
        if a.warm:
            s2, _ = measure_one(E, clips, tag, "warm", wc, rc, baseline)
            ws.writerow(s2); fs.flush()
            summaries.append(s2)
    fc.close(); fs.close(); fr.close()

    print("\n" + "=" * 86)
    print("  %-10s %7s %13s %8s %6s %9s %9s %9s %8s" % (
        "index", "films", "vectors", "GB", "cache", "open_s", "query_p50", "query_p90", "s/Mvec"))
    for s in summaries:
        print("  %-10s %7s %13s %8s %6s %9s %9s %9s %8s" % (
            s["index_tag"], s["films"], format(int(s["vectors"]), ","), s["index_gb"],
            s["cache"], s["open_s"], s["query_s_p50"], s["query_s_p90"],
            s["s_per_million_vectors"]))
    print()
    print("  's/Mvec' is the number to watch. A flat index holds it CONSTANT while query time")
    print("  grows with the catalogue; a partitioned index makes it fall. If it is flat and")
    print("  query_p50 is already uncomfortable, the structure is what has to change.")
    print()
    lost = [r for r in csv.DictReader(open(OUT / "bench_scale_recall.csv", encoding="utf-8"))
            if r["agrees"] == "no"]
    print("  THE GATE: %d clip-runs disagreed with the baseline answer." % len(lost))
    for r in lost[:20]:
        print("     %-10s %-40s %s" % (r["index_tag"], r["clip"][:40], r["verdict"]))
    if not lost:
        print("     none - every index size answered exactly what the baseline answered.")
    print()
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    raise SystemExit(main())

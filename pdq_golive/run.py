"""Run PDQ alone over clips and record everything, one JSON line per (clip, profile).

    python -m pdq_golive.run --index /local_index --manifest clips.csv --out runs.jsonl \
        --profiles golive_g16                     # the main run
    python -m pdq_golive.run ... --profiles today,A,B,golive_g16 --rotate   # comparison

The engine is pdq_engine_PROBEV2.py, loaded once with the index kept open across clips. Two
module-level swaps make it the go-live engine without editing the file:
  - ProbeRun is subclassed so the hook can see the current run's picture fingerprints;
  - pv2_decide is wrapped by decide.decide, so every wave's judgement - early accepts
    included - goes through the checks and fix 1.
The hook counts its calls, so a run where it never fired shows up in the output.

Results are appended and flushed per clip, and clips already in --out are skipped, so a
stopped run resumes where it left off."""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import signal
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import decide as D          # noqa: E402
import loader as LD         # noqa: E402
import profiles as P        # noqa: E402

ENGINE_FILE = os.environ.get("GOLIVE_ENGINE", "")


def load_engine():
    """pdq_golive/vendor/pdq_engine_PROBEV2.py in the image, the repo copy on the laptop."""
    cands = [Path(ENGINE_FILE)] if ENGINE_FILE else []
    cands += [HERE / "vendor" / "pdq_engine_PROBEV2.py", HERE.parent / "pdq_engine_PROBEV2.py"]
    path = next(p for p in cands if p.is_file())
    sys.path.insert(0, str(path.parent))        # for pv2_waves next to it
    spec = importlib.util.spec_from_file_location("pdq_engine_golive", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pdq_engine_golive"] = mod
    spec.loader.exec_module(mod)
    return mod, path


class Hook:
    """The live-loop hook: the current run, whether to guard, and what each wave did."""

    def __init__(self, E):
        self.E = E
        self.orig = E.pv2_decide
        self.run = None
        self.guard = True
        self.fix1 = True
        self.reset()
        hook = self

        class Run(E.ProbeRun):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                hook.run = self

        E.ProbeRun = Run

        def hooked(film_hits):
            return hook.judge(film_hits)

        E.pv2_decide = hooked

    def reset(self):
        self.calls = 0
        self.waves = []
        self.info = {"dropped_time": 0, "dropped_quality": 0, "still_dropped": []}
        self.t0 = time.perf_counter()
        self.answer_at = None

    def judge(self, film_hits):
        self.calls += 1
        run = self.run
        sig = run.sig if run is not None else {}
        if self.guard:
            hit, ranked, info = D.decide(self.orig, film_hits, sig, fix1=self.fix1)
            self.info["dropped_time"] = info["dropped_time"]
            self.info["dropped_quality"] = info["dropped_quality"]
            for v in info["still_dropped"]:
                if v not in self.info["still_dropped"]:
                    self.info["still_dropped"].append(v)
        else:
            hit, ranked = self.orig(film_hits)
        best = min((r[0] for h in film_hits.values() for r in h.values()), default=None)
        self.waves.append({
            "t": round(time.perf_counter() - self.t0, 3),
            "pictures": len(run.consumed) if run is not None else None,
            "searches": run.index_searches if run is not None else None,
            "films": len(film_hits), "best": best,
            "tier": hit["tier"] if hit else None})
        if hit is not None and self.answer_at is None:
            self.answer_at = time.perf_counter() - self.t0
        return hit, ranked


class ClipTimeout(Exception):
    pass


def _alarm(signum, frame):
    raise ClipTimeout()


def _proc_stats() -> dict:
    out = {}
    try:
        with open("/proc/self/stat") as f:
            parts = f.read().rsplit(")", 1)[1].split()
        out["minflt"], out["majflt"] = int(parts[7]), int(parts[9])
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    out["rss_mb"] = int(line.split()[1]) // 1024
        out["load1"] = os.getloadavg()[0]
        out["threads"] = len(os.listdir("/proc/self/task"))
    except OSError:
        pass
    return out


def read_manifest(path: Path) -> list:
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    for r in rows:
        r["path"] = r.get("path") or r.get("file") or r.get("clip")
    return rows


def run_one(E, idx, hook: Hook, row: dict, profile: str, guard: bool, fix1: bool) -> dict:
    s = P.apply(E, profile)
    hook.guard, hook.fix1 = guard, fix1
    path = row["path"]
    rec = {"clip": Path(path).name, "profile": profile, "guard": guard, "fix1": fix1,
           **{k: v for k, v in row.items() if k != "path"}}
    try:
        w, h, dur = E.video_wh_duration(path)
        groups = [g for g in E.groups_for_clip_shape(E.infer_query_group_from_wh(w, h))
                  if g in idx.index_by_group] or list(idx.index_by_group)
    except Exception as e:                       # an unreadable clip must not stop the run
        rec.update(error=str(e)[:200])
        return rec
    before = _proc_stats()
    hook.reset()
    hook.run = None
    t0, c0 = time.perf_counter(), time.process_time()
    # A clip that runs past GOLIVE_CLIP_TIMEOUT seconds is recorded and skipped: run 5's
    # comparison sat on one clip for 50 minutes and never finished.
    limit = int(os.environ.get("GOLIVE_CLIP_TIMEOUT", "0") or 0)
    if limit and hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(limit)
    try:
        hit = E.super_probe(path, idx, groups, maxdim=(s["PV2_MAXDIM"] or None))[0]
    except ClipTimeout:
        rec.update(error="timeout %ds" % limit, wall_s=round(time.perf_counter() - t0, 3))
        return rec
    except Exception as e:
        if limit and hasattr(signal, "SIGALRM"):
            signal.alarm(0)
        rec.update(error=str(e)[:200], wall_s=round(time.perf_counter() - t0, 3))
        return rec
    if limit and hasattr(signal, "SIGALRM"):
        signal.alarm(0)
    wall, cpu = time.perf_counter() - t0, time.process_time() - c0
    after = _proc_stats()
    run = hook.run
    ev = run.evidence() if run is not None else {}
    n_waves = len(run.bounds) if run is not None else 0
    used = len(run.consumed) if run is not None else 0
    rec.update({
        "duration_s": round(dur or 0, 2), "groups": groups,
        # a placeholder film (rows whose shard has no film table in B2) is no answer
        "unmapped": bool(hit and LD.is_unmapped(idx.label(hit["vidx"]))),
        "raw_answer": idx.label(hit["vidx"]) if hit else "",
        "answer": idx.label(hit["vidx"]) if (hit and not LD.is_unmapped(idx.label(hit["vidx"]))) else "",
        "vidx": hit["vidx"] if hit else None,
        "tier": hit["tier"] if (hit and not LD.is_unmapped(idx.label(hit["vidx"]))) else "",
        "wall_s": round(wall, 3), "cpu_s": round(cpu, 3),
        "answer_s": round(hook.answer_at, 3) if (hit and hook.answer_at is not None) else None,
        "seek_s": round(ev.get("seek_s", 0), 3), "hash_s": round(ev.get("hash_s", 0), 3),
        "search_s": round(ev.get("search_s", 0), 3),
        "frames_decoded": ev.get("frames_decoded"), "pictures_used": used,
        "n_pictures": ev.get("n_pictures"), "query_rows": ev.get("query_rows"),
        "index_searches": ev.get("index_searches"), "waves_used": ev.get("waves_used"),
        "n_waves": n_waves,
        "gave_up": bool(hit is None and run is not None and run.waves_used < n_waves),
        "hook_calls": hook.calls, "waves": hook.waves,
        "dropped_time": hook.info["dropped_time"],
        "dropped_quality": hook.info["dropped_quality"],
        "still_dropped": hook.info["still_dropped"],
        "rss_mb": after.get("rss_mb"), "load1": after.get("load1"), "threads": after.get("threads"),
        "majflt": (after.get("majflt", 0) - before.get("majflt", 0)) if after else None,
        "minflt": (after.get("minflt", 0) - before.get("minflt", 0)) if after else None,
    })
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--index", default=os.environ.get("PDQ_INDEX_DIR", "/local_index"))
    ap.add_argument("--manifest", required=True, help="CSV with a path (or file/clip) column")
    ap.add_argument("--out", required=True)
    ap.add_argument("--profiles", default="golive_g16")
    ap.add_argument("--rotate", action="store_true", help="rotate profile order per clip")
    ap.add_argument("--no-guard", action="store_true", help="judge without the checks and fix 1")
    ap.add_argument("--no-fix1", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args(argv)

    E, epath = load_engine()
    LD.install(E)
    hook = Hook(E)
    t = time.perf_counter()
    idx = E.load_index(a.index)
    load_s = time.perf_counter() - t
    profs = [p.strip() for p in a.profiles.split(",") if p.strip()]
    rows = read_manifest(Path(a.manifest))
    if a.limit:
        rows = rows[:a.limit]
    out = Path(a.out)
    done = set()
    if out.is_file():
        for line in open(out, encoding="utf-8"):
            try:
                r = json.loads(line)
                done.add((r["clip"], r["profile"], r.get("guard")))
            except (ValueError, KeyError):
                pass
    print("engine %s  index %s films  load %.1fs  clips %d  profiles %s  done %d" % (
        epath.name, idx.manifest.get("movies_count"), load_s, len(rows), profs, len(done)),
        flush=True)
    with open(out, "a", encoding="utf-8") as f:
        for i, row in enumerate(rows):
            order = profs[i % len(profs):] + profs[:i % len(profs)] if a.rotate else profs
            for p in order:
                guard = (p in P.GUARDED) and not a.no_guard
                if (Path(row["path"]).name, p, guard) in done:
                    continue
                rec = run_one(E, idx, hook, row, p, guard, not a.no_fix1)
                rec["order"] = "|".join(order)
                rec["groups_loaded"] = sorted(idx.index_by_group)
                f.write(json.dumps(rec, default=str) + "\n")
                f.flush()
                os.fsync(f.fileno())        # a pod that stops keeps every finished clip
                print("[%d/%d] %-10s %-40s %6.2fs %s %s" % (
                    i + 1, len(rows), p, rec["clip"][:40], rec.get("wall_s") or -1,
                    rec.get("tier") or "-", (rec.get("answer") or rec.get("error") or "")[:40]),
                    flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

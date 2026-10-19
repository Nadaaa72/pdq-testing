# -*- coding: utf-8 -*-
"""
dump_probe_evidence.py - pay the probe's cost ONCE, save what it saw.

    python dump_probe_evidence.py                              (all 125 clips)
    python dump_probe_evidence.py --engine pdq_engine_PROBEV2.py
    python dump_probe_evidence.py --samples 80                 (denser sampling)
    python dump_probe_evidence.py --clips 5                    (a quick smoke test)

Trying one threshold used to cost a full sweep of every clip: about 20-45 s each, an hour
and a half for the set. That is why the bars have been tuned three clips at a time.

This script runs only the probe's COLLECTION half (collect_probe_evidence) and writes every
hit it found to output/probe_evidence.csv. replay_rules.py then evaluates any rulebook
against that file in under a second. Collect once, judge a thousand times.

Two files come out, and the second one matters as much as the first:

  output/probe_evidence.csv        one row per (clip, film, sampled frame) that hit
  output/probe_evidence_clips.csv  one row per clip, INCLUDING the clips that hit nothing

Without the second file a clip that found nothing would vanish from the set and every
recall percentage would quietly be measured against a smaller denominator.

Resumable: stop it with Ctrl-C and run it again.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"

# group and target say WHICH of the ~15 pictures taken from a sampled frame actually
# matched: group FULL is the whole frame (target "full") or its safe-trimmed copy ("trim"),
# and every other group is a centred crop ("9x16_s1.0" and so on). An "x:" prefix means the
# mirrored or letterbox-trimmed view of the frame. Without these two columns a dump cannot
# answer whether the cropped or the uncropped pictures are carrying the matches.
# One row per (clip, film, sampled frame, GROUP, VIEW) - the best hit in that cell - rather
# than one per (clip, film, frame). The overall best is the minimum over a frame's cells,
# which is the rule replay_rules.py already applies to duplicate rows, so this replays
# identically while also letting a PASS be simulated: an uncropped-only pass is the cells
# with group FULL, a plain-only pass is the cells with view p.
HIT_FIELDS = ["clip", "vidx", "film_label", "sample_i", "clip_t", "film_t", "distance",
              "offset", "group", "view", "target"]
CLIP_FIELDS = ["list", "clip", "expected_film", "in_catalogue", "duration_s", "n_samples",
               "groups", "n_hashes", "index_searches", "films_hit", "hits", "collect_s",
               "resample_s", "shortlist", "note", "edit",
               # The cost split. collect_s keeps its old meaning - wall clock around the
               # whole call - so every row already written stays comparable; these say where
               # that time went. Before them, the claim that hashing dominates rested on a
               # regression across clips (R^2 0.24) rather than on measurement. Appended at
               # the END on purpose, so a DictReader on an older file still works and old
               # rows come back with these empty rather than with their columns shifted.
               "seek_s", "hash_s", "search_s", "waves_used", "frames_decoded", "query_rows"]

COST_FIELDS = ["seek_s", "hash_s", "search_s", "waves_used", "frames_decoded", "query_rows"]


def check_header(path, fields) -> None:
    """Refuse to append rows under a header that does not match them.

    Both CSVs are opened in append mode and only get a header when the file is absent, so
    adding a column and re-running would write the new field order under the old header -
    silently misaligned data that looks fine until something reads it."""
    if not path.is_file():
        return
    with open(path, encoding="utf-8") as fh:
        head = (fh.readline() or "").strip().lstrip("\ufeff")
    want = ",".join(fields)
    if head and head != want:
        raise SystemExit(
            "%s was written with different columns, so appending to it would misalign "
            "every new row.\n  on disk: %s\n  now:     %s\nMove it aside or pass --tag "
            "to write a separate file." % (path.name, head, want))


def load_engine(path: Path):
    spec = importlib.util.spec_from_file_location("engine_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["engine_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description="Save the probe's evidence for every clip.")
    ap.add_argument("--engine", default="pdq_engine_PROBEV2.py")
    ap.add_argument("--samples", type=int, default=None,
                    help="frames sampled per clip (default: the engine's PV2_SAMPLES)")
    ap.add_argument("--clips", type=int, default=0, help="stop after this many clips")
    ap.add_argument("--maxdim", type=int, default=None,
                    help="shrink each frame to this before hashing (try 640, the size the "
                         "index was built at). Changes the hashes, so dump to a separate "
                         "--tag and compare with replay_rules.py")
    ap.add_argument("--views", default="all", choices=["all", "plain", "extra"],
                    help="all = every view as shipped; plain = the frame and its safe-trim "
                         "copy only; extra = the mirrored and letterbox-trimmed views only")
    ap.add_argument("--resample", action="store_true",
                    help="after the first round, if no bar fires, sample again densely around "
                         "the moments that already matched and search ONLY the shortlisted "
                         "films. Writes the extra hits with negative sample_i")
    ap.add_argument("--shortlist", type=int, default=20,
                    help="with --resample: how many candidate films the second round looks at")
    ap.add_argument("--tag", default="", help="extra tag for the output file names")
    ap.add_argument("--edited", action="store_true",
                    help="run the edited suite from data/edited_clips.csv instead of the "
                         "two vote lists (the clips the cropped views exist for)")
    a = ap.parse_args()

    engine_path = HERE / a.engine
    if not engine_path.is_file():
        raise SystemExit("no such engine: " + str(engine_path))
    E = load_engine(engine_path)
    if not hasattr(E, "collect_probe_evidence"):
        raise SystemExit(engine_path.name + " has no collect_probe_evidence(); it predates the "
                         "collect/judge split. Use pdq_engine_PROBEV2.py.")

    # the same two vote lists, loaded the same way, so the clip set matches the attribution CSVs
    import attribute_rules as AR
    if a.edited:
        # The edited suite from make_edited_clips.py: the same films put through the edits
        # creators really make. These are the clips the cropped views exist for, so the
        # cropped-versus-uncropped question is decided here rather than on clean reposts.
        manifest = HERE / "data" / "edited_clips.csv"
        if not manifest.is_file():
            raise SystemExit("no data/edited_clips.csv - run make_edited_clips.py first")
        jobs = []
        for r in csv.DictReader(open(manifest, encoding="utf-8")):
            path = HERE / "data" / "clips_edited" / r["file"]
            if path.is_file():
                jobs.append(("edited", r["film"], "yes", path, r.get("edit", "")))
    else:
        jobs = [(w, f, c, p, "") for w, f, c, p in
                (AR.load_list("wrong_pdq_clips.csv", "wrong")
                 + AR.load_list("correct_pdq_clips.csv", "correct"))]
    if a.clips:
        jobs = jobs[:a.clips]

    auto = []
    if a.edited:
        auto.append("edited")
    if a.samples:
        auto.append("s%d" % a.samples)
    if a.maxdim:
        auto.append("d%d" % a.maxdim)
    if a.views != "all":
        auto.append(a.views)
    if a.resample:
        auto.append("resample%d" % a.shortlist)
    tag = a.tag or "_".join(auto)
    suffix = ("_" + tag) if tag else ""
    OUT.mkdir(exist_ok=True)
    hits_csv = OUT / ("probe_evidence%s.csv" % suffix)
    clips_csv = OUT / ("probe_evidence_clips%s.csv" % suffix)

    done = set()
    if clips_csv.is_file():
        for r in csv.DictReader(open(clips_csv, encoding="utf-8")):
            done.add(r["clip"])
        print("resuming: %d clips already in %s" % (len(done), clips_csv.name))

    index = E.load_index(str(HERE / "data" / "index"))
    print("engine: %s   index: %s films, %s fingerprints   clips: %d" % (
        engine_path.name, index.manifest.get("movies_count"),
        format(index.manifest.get("hashes_total"), ","), len(jobs)))
    # The sampling mode belongs in the banner because it decides what sample_i MEANS.
    # Anchored, id 3 is a fixed moment of the clip; on the grid it is the fourth slot of
    # however many were taken. Replaying an anchored dump needs --wave-order linear, since
    # anchored runs take their ids in order and the spread is in the positions.
    print("samples: %s (%s)   views: %s   maxdim: %s   -> %s" % (
        a.samples or E.PV2_SAMPLES,
        ("anchored %.0f%%-%.0f%% of the clip" % (E.PV2_SAMPLE_LO * 100, E.PV2_SAMPLE_HI * 100))
        if E.PV2_ANCHORED else "grid, (i+0.5)/n",
        a.views, a.maxdim or "none (clip resolution)", hits_csv.name))

    check_header(hits_csv, HIT_FIELDS)
    check_header(clips_csv, CLIP_FIELDS)
    new_hits, new_clips = not hits_csv.is_file(), not clips_csv.is_file()
    fh = open(hits_csv, "a", newline="", encoding="utf-8")
    fc = open(clips_csv, "a", newline="", encoding="utf-8")
    wh = csv.DictWriter(fh, fieldnames=HIT_FIELDS)
    wc = csv.DictWriter(fc, fieldnames=CLIP_FIELDS)
    if new_hits:
        wh.writeheader()
    if new_clips:
        wc.writeheader()

    t_all = time.time()
    for i, (which, film, in_cat, path, job_edit) in enumerate(jobs, 1):
        if path.name in done:
            continue
        t0 = time.time()
        row = {"list": which, "clip": path.name, "expected_film": film, "in_catalogue": in_cat,
               "duration_s": "", "n_samples": "", "groups": "", "n_hashes": "",
               "index_searches": "", "films_hit": 0, "hits": 0,
               "collect_s": "", "resample_s": "", "shortlist": "", "note": "",
               "edit": job_edit,
               **{k: "" for k in COST_FIELDS}}
        try:
            w, h, dur = E.video_wh_duration(str(path))
            groups = [g for g in E.groups_for_clip_shape(E.infer_query_group_from_wh(w, h))
                      if g in index.index_by_group] or list(index.index_by_group)
            ev = E.collect_probe_evidence(str(path), index, groups, a.samples,
                                          maxdim=a.maxdim, views=a.views)
            if ev is not None and a.resample:
                # Only the clips no bar accepts are worth a second look - the point of the
                # round is to rescue evidence that is thin, not to pile more onto an answer
                # the probe already trusts.
                hit, ranked = E.pv2_decide(ev["film_hits"])
                if hit is None and ranked:
                    shortlist = [int(v) for _, _, v, _ in ranked[:a.shortlist]]
                    t_rs = time.time()
                    E.resample_candidates(str(path), index, groups, ev["film_hits"],
                                          shortlist, maxdim=a.maxdim)
                    ev["resample_s"] = time.time() - t_rs
                    ev["shortlist"] = len(shortlist)
        except Exception as e:                      # a broken download must not kill the sweep
            row["note"] = ("ERROR " + str(e))[:200]
            row["collect_s"] = "%.1f" % (time.time() - t0)
            wc.writerow(row); fc.flush()
            print("[%d/%d] %-7s %-32s ERROR %s" % (i, len(jobs), which, film[:30], e))
            continue

        if ev is None:
            row["note"] = "unreadable or shorter than 2s"
        else:
            n_hits = 0
            labels = {}
            for (vidx, sample_i, g, vc), (dist, clip_t, film_t, tgt) in sorted(
                    ev.get("cells", {}).items()):
                if vidx not in labels:
                    labels[vidx] = index.label(vidx)
                wh.writerow({"clip": path.name, "vidx": vidx, "film_label": labels[vidx],
                             "sample_i": sample_i, "clip_t": "%.3f" % clip_t,
                             "film_t": "%.3f" % film_t, "distance": dist,
                             "offset": "%.3f" % (film_t - clip_t),
                             "group": g, "view": vc, "target": tgt})
                n_hits += 1
            row.update({"duration_s": "%.0f" % ev["duration_s"], "n_samples": ev["n_samples"],
                        "groups": "|".join(ev["groups"]), "n_hashes": ev["n_hashes"],
                        "index_searches": ev["index_searches"],
                        "films_hit": len(ev["film_hits"]), "hits": n_hits,
                        "resample_s": ("%.1f" % ev["resample_s"]) if "resample_s" in ev else "",
                        "shortlist": ev.get("shortlist", "")})
            for k in COST_FIELDS:
                v = ev.get(k, "")
                row[k] = ("%.2f" % v) if isinstance(v, float) else v
        row["collect_s"] = "%.1f" % (time.time() - t0)
        fh.flush()
        wc.writerow(row); fc.flush()
        print("[%d/%d] %-7s %-32s %3s films %4s hits  %5.1fs %s" % (
            i, len(jobs), which, film[:30], row["films_hit"], row["hits"],
            time.time() - t0, row["note"]))
    fh.close()
    fc.close()
    print("\ndone in %.0fs -> %s  +  %s" % (time.time() - t_all, hits_csv, clips_csv))
    print("now: python replay_rules.py")
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    raise SystemExit(main())

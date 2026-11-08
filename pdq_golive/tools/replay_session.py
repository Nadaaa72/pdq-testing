"""Replay a session's evidence on the laptop: every setting, with and without the checks.

    python pdq_golive/tools/replay_session.py DIR [--manifest M.csv] [--live RUN.jsonl ...]

DIR holds the probe_evidence*_golive6[_s<i>].csv files the pod's evidence pass wrote. The shard
files are merged, then probe_lab's copy of the probe loop (the one the laptop golden run checked
against the live runner, 346 of 346) scores:
  today = base80, A = dih160, B = dih160_g24, golive = dih160_g16
each as the engine ships and through decide.decide (the 20 s check, the quality check, fix 1).
Writes DIR/replay_rows.csv (one row per clip and setting) and prints the summary tables.

--live compares the replayed golive (guarded) answers with live runner results on the same
clips, clip by clip: the proof that replay equals live on the real index.

Note: today's live profile hashes at full resolution; the evidence is hashed at 640 (the index's
size), so the replayed 'today' is today's rules on 640 pictures, not an exact replay."""
from __future__ import annotations

import argparse
import collections as C
import csv
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pdq_golive"))

SETTINGS = [("today", "base80"), ("A", "dih160"), ("B", "dih160_g24"), ("golive", "dih160_g16")]


def tmdb(label: str):
    m = re.search(r"tmdb=(\d+)", label or "")
    return m.group(1) if m else None


def merge(d: Path, tag: str) -> None:
    """Concatenate the shard files into one set under tag, header once."""
    for kind in ("probe_evidence_%s", "probe_evidence_clips_%s", "probe_evidence_frames_%s"):
        parts = sorted(d.glob((kind % (tag + "_s*")) + ".csv"))
        if not parts:
            continue
        with open(d / ((kind % tag) + ".csv"), "w", encoding="utf-8", newline="") as out:
            for i, p in enumerate(parts):
                lines = open(p, encoding="utf-8").read().splitlines(True)
                out.writelines(lines if i == 0 else lines[1:])


def outcome(expect_film: bool, exp_tmdb: str, label: str) -> str:
    got = tmdb(label) if label else None
    if expect_film:
        if not label:
            return "silent"
        return "right" if got == exp_tmdb else "wrong"
    return "right_silent" if not label else "wrong"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--tag", default="golive6")
    ap.add_argument("--manifest", default="")
    ap.add_argument("--live", nargs="*", default=[])
    a = ap.parse_args(argv)
    d = Path(a.dir)
    merge(d, a.tag)

    import probe_lab as L
    L.E = L.load_engine()
    E = L.E
    import probe_lab_variants as V
    import decide as D
    base = {v.name: v for v in V.variants(E)}
    L.OUT = d
    clips = L.load_dump(a.tag, "golive")
    man = {}
    if a.manifest:
        for r in csv.DictReader(open(a.manifest, encoding="utf-8-sig")):
            man[Path(r["clip"]).name] = r
    print("clips with evidence:", len(clips), " notes:",
          dict(C.Counter((r.get("note") or "")[:12] for r in csv.DictReader(
              open(d / ("probe_evidence_clips_%s.csv" % a.tag), encoding="utf-8")))))

    guarded = lambda fh, clip, var: D.decide(E.pv2_decide, fh, clip.sig)[:2]  # noqa: E731
    rows = []
    for name, vname in SETTINGS:
        v0 = base[vname]
        for g in (False, True):
            var = L.Variant(name, v0.views, v0.n, v0.waves, giveup=v0.giveup,
                            giveup_min=v0.giveup_min, knobs=dict(v0.knobs),
                            decide=guarded if g else None)
            res = L.evaluate(list(clips.values()), var)
            for cn, x in res.items():
                m = man.get(cn, {})
                h = x["hit"]
                label = x["clip"].labels.get(h["vidx"], "") if h else ""
                if label.startswith("UNMAPPED:"):
                    label = ""
                exp_film = (m.get("expected_answer", "film") == "film")
                rows.append({"clip": cn, "setting": name, "checks": "on" if g else "off",
                             "group": m.get("group", ""), "strength": m.get("strength", ""),
                             "expected_tmdb": m.get("expected_tmdb", ""),
                             "expected_film": m.get("expected_film", ""),
                             "answer": label, "tier": h["tier"] if h else "",
                             "pictures": x["frames"],
                             "outcome": outcome(exp_film, m.get("expected_tmdb", ""), label)})
    with open(d / "replay_rows.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print("\n== every setting, all clips (right = named the expected film; right_silent = silent "
          "on a clip that should be silent)")
    for name, _ in SETTINGS:
        for g in ("off", "on"):
            rs = [r for r in rows if r["setting"] == name and r["checks"] == g]
            c = C.Counter(r["outcome"] for r in rs)
            print("%-7s checks %-3s n=%d %s" % (name, g, len(rs), dict(sorted(c.items()))))
    print("\n== by group (checks on)")
    groups = sorted({r["group"] for r in rows})
    for name, _ in SETTINGS:
        rs = [r for r in rows if r["setting"] == name and r["checks"] == "on"]
        print(name, {gname: dict(C.Counter(r["outcome"] for r in rs if r["group"] == gname))
                     for gname in groups})
    print("\n== wrong answers (checks on)")
    for r in rows:
        if r["checks"] == "on" and r["outcome"] == "wrong":
            print("  %-7s %-18s %-40s expected %-22s got %s %s" % (
                r["setting"], r["group"][:18], r["clip"][:40], r["expected_film"][:22],
                r["answer"][:38], r["tier"]))

    if a.live:
        live = {}
        for p in a.live:
            for line in open(p, encoding="utf-8"):
                x = json.loads(line)
                if x.get("profile") == "golive_g16" and x.get("guard"):
                    live.setdefault(Path(x["clip"]).name, x)
        rep = {r["clip"]: r for r in rows if r["setting"] == "golive" and r["checks"] == "on"}
        both = sorted(set(live) & set(rep))
        diff = [(c, tmdb(live[c].get("answer")), tmdb(rep[c]["answer"]), live[c].get("tier"),
                 rep[c]["tier"]) for c in both
                if tmdb(live[c].get("answer")) != tmdb(rep[c]["answer"])]
        print("\n== replay vs live (golive, checks on): %d clips in both, %d differ" % (
            len(both), len(diff)))
        for x in diff:
            print("   %-44s live %-8s %-5s | replay %-8s %s" % (x[0][:44], x[1], x[3], x[2], x[4]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Parts 1 and 7: the laptop golden answers, and the check that the live runner matches them.

    python pdq_golive/tools/golden_laptop.py golden      # replay -> output/golive/golden_laptop.csv
    python pdq_golive/tools/golden_laptop.py manifest    # clip files for the live run
    python pdq_golive/tools/golden_laptop.py compare RUN.jsonl

golden replays the saved laptop evidence (lab160_d640 dumps) through probe_lab's copy of the
probe loop with variant dih160_g16, judged by decide.decide - the same function the live
runner hooks in. It also replays the original replay3 decide ('both_a') and stops if the two
disagree on any clip, which is the check that the port is faithful.

Scoring follows rescore_all_sets: Nada's verdicts override the vote on the 9 reviewed clips."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pdq_golive"))
OUT = ROOT / "output" / "golive"
GOLDEN = OUT / "golden_laptop.csv"
SETS = ("votes", "heldout", "heldout2", "edited")


def _lab():
    import probe_lab as L
    L.E = L.load_engine()
    import probe_lab_variants as V
    return L, L.E, {v.name: v for v in V.variants(L.E)}


def _verdicts():
    rows = list(csv.DictReader(open(ROOT / "output/logo_study/verdicts.csv", encoding="utf-8")))
    return lambda n: next((r for r in rows if r["clip_key"] in n), None)


def _replay3_decide(E):
    """replay3.py mk(20, 70, fa=1, fb=0), copied as it ran on the pod."""
    def ham(a, b):
        return bin(a ^ b).count("1")

    def dec(fh, clip, var):
        f = {}
        for v, h in fh.items():
            g = {si: r for si, r in h.items()
                 if r[2] >= 20 and not (70 and si in clip.sig and clip.sig[si][1] < 70)}
            if g:
                f[v] = g
        for _ in range(4):
            h, rk = E.pv2_decide(f)
            if not h:
                return h, rk
            v = h["vidx"]
            sis = [si for si, r in f[v].items() if r[0] < 33 and si in clip.sig]
            if len(sis) >= 3:
                cs = [int.from_bytes(clip.sig[si][0], "big") for si in sis]
                share = max(sum(ham(a, b) <= 10 for b in cs) for a in cs) / len(cs)
                if share >= .6:
                    f.pop(v)
                    continue
            return h, rk
        return None, []
    return dec


def golden():
    import decide as D
    L, E, base = _lab()
    vd = _verdicts()
    S = L.load_sets("lab160_d640")
    v0 = base["dih160_g16"]

    def variant(dec):
        return L.Variant("g16", v0.views, v0.n, v0.waves, giveup=v0.giveup,
                         giveup_min=v0.giveup_min, knobs=dict(v0.knobs), decide=dec)

    ours = variant(lambda fh, clip, var: D.decide(E.pv2_decide, fh, clip.sig)[:2])
    theirs = variant(_replay3_decide(E))
    OUT.mkdir(parents=True, exist_ok=True)
    tot, diffs = {}, []
    with open(GOLDEN, "w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo)
        w.writerow(["set", "clip", "expected", "outcome", "answer", "vidx", "tier", "frames"])
        for s in SETS:
            a, b = L.evaluate(S[s], ours), L.evaluate(S[s], theirs)
            for n, x in a.items():
                y = b[n]
                ka = (x["hit"] or {}).get("vidx"), (x["hit"] or {}).get("tier")
                kb = (y["hit"] or {}).get("vidx"), (y["hit"] or {}).get("tier")
                if ka != kb:
                    diffs.append((s, n, ka, kb))
                o, h, r = x["out"], x["hit"], vd(n)
                if r and s == "votes":
                    lab = x["clip"].labels.get(h["vidx"], "") if h else ""
                    o = "quiet" if h is None else (
                        "right" if r["category"] == "pdq_right_vote_wrong"
                        and L.fuzzy(lab, r["nada_truth"]) else "wrong")
                tot[o] = tot.get(o, 0) + 1
                w.writerow([s, n, x["clip"].expected, o,
                            x["clip"].labels.get(h["vidx"], "") if h else "",
                            h["vidx"] if h else "", h["tier"] if h else "", x["frames"]])
    print("golden", tot, "port differences vs replay3:", len(diffs))
    for d in diffs:
        print("  DIFF", d)
    return 1 if diffs else 0


def manifest():
    """Every golden clip, with its file on disk. A name found in two folders must be the
    same bytes, or the clip is reported and left out."""
    import hashlib
    files = {}
    for d in ("clips", "clips_heldout", "clips_heldout2", "clips_edited"):
        for p in (ROOT / "data" / d).rglob("*"):
            if p.is_file() and p.stat().st_size > 0:
                files.setdefault(p.name, []).append(p)
    rows, missing, clash = [], [], []
    for r in csv.DictReader(open(GOLDEN, encoding="utf-8")):
        ps = files.get(r["clip"], [])
        if not ps:
            missing.append(r["clip"])
            continue
        if len({hashlib.md5(p.read_bytes()).hexdigest() for p in ps}) > 1:
            clash.append(r["clip"])
            continue
        rows.append({"path": str(ps[0]), "set": r["set"], "expected": r["expected"]})
    with open(OUT / "laptop_manifest.csv", "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=["path", "set", "expected"])
        w.writeheader()
        w.writerows(rows)
    print("manifest rows", len(rows), "missing", len(missing), "clash", len(clash))
    for m in missing + clash:
        print("  skip", m)


def compare(run_jsonl: str):
    g = {}
    for r in csv.DictReader(open(GOLDEN, encoding="utf-8")):
        g.setdefault(r["clip"], []).append(r)
    same = differ = 0
    out = []
    for line in open(run_jsonl, encoding="utf-8"):
        rec = json.loads(line)
        if rec.get("profile") != "golive_g16":
            continue
        for r in g.get(rec["clip"], []):
            if r["set"] != rec.get("set"):
                continue
            want = (r["vidx"] or None, r["tier"] or None)
            got = (str(rec["vidx"]) if rec.get("vidx") is not None else None, rec.get("tier") or None)
            if want == got:
                same += 1
            else:
                differ += 1
                out.append((r["set"], rec["clip"], want, got, rec.get("error", "")))
    print("live vs golden: same %d, different %d" % (same, differ))
    for o in out:
        print("  DIFF", o)
    return 1 if differ else 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "golden"
    sys.exit({"golden": golden, "manifest": manifest}.get(cmd, lambda: compare(sys.argv[2]))())

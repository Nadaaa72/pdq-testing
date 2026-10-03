# -*- coding: utf-8 -*-
"""
app.py - the whole folder behind one command and one browser tab.

    python app.py

then open  http://127.0.0.1:5077  in your browser.

What it is: a small local web page (Flask) that runs the four scripts for you and shows
their printouts live. Nothing leaves your laptop. The page has five tabs:

  Home       is everything in place? credentials, catalogue, index. The next step to take.
  Films      the whole catalogue with a search box. Tick films, save the list. A film we do
             not have says so.
  Build      build the index from the list (or to a size in GB, or from your own film file).
  Identify   drop a clip in, or paste a link, and read the pod's printout.
  Wrong      pull the clips PDQ got wrong (and right), and replay any of them with one click.

Everything the page does, the scripts do too. The page just runs them:
  1_get_movie_catalogue.py, 2_build_index.py, 3_identify_clip.py, 4_pull_wrong_pdq_clips.py.
So the command line and the page always agree.
"""
from __future__ import annotations

import csv
import html
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, redirect, request

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CATALOGUE = DATA / "movies_catalogue.csv"
LIST = DATA / "movies_to_include.txt"
INDEX = DATA / "index"
CLIPS = DATA / "clips"
WRONG = DATA / "wrong_pdq_clips.csv"
CORRECT = DATA / "correct_pdq_clips.csv"
PORT = 5077

app = Flask(__name__)

# ---------------------------------------------------------------------------------------------
# One job at a time. A job is one of the scripts running in the background; its printout is
# kept here so the page can show it as it comes.
# ---------------------------------------------------------------------------------------------
JOB = {"name": "", "lines": [], "running": False, "rc": None, "started": 0.0}
JOB_LOCK = threading.Lock()


def run_job(name: str, args: list) -> bool:
    """Start a script as a background job. Returns False if another job is still running."""
    with JOB_LOCK:
        if JOB["running"]:
            return False
        JOB.update({"name": name, "lines": [], "running": True, "rc": None, "started": time.time()})

    def worker():
        cmd = [sys.executable, "-u", *args]
        proc = subprocess.Popen(cmd, cwd=str(HERE), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", bufsize=1)
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            # progress bars redraw with \r; keep only the last redraw of each
            if "\r" in line:
                line = line.split("\r")[-1]
            with JOB_LOCK:
                JOB["lines"].append(line)
        proc.wait()
        with JOB_LOCK:
            JOB["running"] = False
            JOB["rc"] = proc.returncode
            JOB["lines"].append(f"[finished with code {proc.returncode}]")

    threading.Thread(target=worker, daemon=True).start()
    return True


# ---------------------------------------------------------------------------------------------
# Small helpers to read what is on disk
# ---------------------------------------------------------------------------------------------
def read_catalogue() -> list:
    if not CATALOGUE.is_file():
        return []
    with open(CATALOGUE, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_list_ids() -> list:
    if not LIST.is_file():
        return []
    ids = []
    for line in LIST.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(\d+)", line)
        if m and not line.lstrip().startswith("#"):
            ids.append(int(m.group(1)))
    return ids


def index_summary() -> dict | None:
    man = INDEX / "manifest.json"
    if not man.is_file():
        return None
    d = json.loads(man.read_text(encoding="utf-8"))
    size = sum(f.stat().st_size for f in INDEX.iterdir() if f.is_file())
    return {"films": d.get("movies_count"), "hashes": d.get("hashes_total"), "gb": size / 1e9,
            "labels": d.get("video_paths", [])}


def credentials_ok() -> tuple:
    f = HERE / "credentials.env"
    if not f.is_file():
        return False, "credentials.env is missing. Copy the file Jude sent you into this folder."
    txt = f.read_text(encoding="utf-8", errors="replace")
    have_b2 = re.search(r"^B2_KEY_ID\s*=\s*\S+", txt, re.M) and re.search(r"^B2_APP_KEY\s*=\s*\S+", txt, re.M)
    have_db = re.search(r"^DATABASE_URL(_READONLY)?\s*=\s*\S+", txt, re.M)
    if not have_b2:
        return False, "credentials.env is there but has no B2 key in it."
    return True, "credentials.env found" + (" (with the database link)" if have_db else " (no database link: the Wrong tab will not work)")


# ---------------------------------------------------------------------------------------------
# The page. One skeleton, five tabs, plain HTML.
# ---------------------------------------------------------------------------------------------
STYLE = """
<style>
 body{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f5f7fa;color:#1f1f1f}
 header{background:#003775;color:#fff;padding:12px 24px;display:flex;gap:24px;align-items:center}
 header a{color:#fff;text-decoration:none;font-weight:600;padding:6px 10px;border-radius:6px}
 header a.on{background:#1565C0}
 main{max-width:1100px;margin:20px auto;padding:0 20px}
 .card{background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:16px 20px;margin-bottom:16px}
 pre{background:#0f172a;color:#e2e8f0;padding:12px;border-radius:6px;max-height:520px;overflow:auto;font-size:12.5px;line-height:1.45}
 table{border-collapse:collapse;width:100%;font-size:14px}
 th,td{border-bottom:1px solid #e5e7eb;padding:6px 8px;text-align:left;vertical-align:top}
 th{background:#eef2f7}
 input[type=text],input[type=number]{padding:7px 9px;border:1px solid #c9d6e5;border-radius:6px;width:100%;box-sizing:border-box}
 button,.btn{background:#1565C0;color:#fff;border:0;padding:8px 14px;border-radius:6px;cursor:pointer;font-weight:600;text-decoration:none;display:inline-block}
 button.grey{background:#6b7280}
 .ok{color:#137333;font-weight:600}.bad{color:#b3261e;font-weight:600}.muted{color:#6b6b6b}
 .row{display:flex;gap:12px;align-items:end;flex-wrap:wrap}.row>div{flex:1;min-width:180px}
 .pill{display:inline-block;padding:2px 8px;border-radius:10px;background:#e8f0fe;color:#1565C0;font-size:12px;margin-left:6px}
</style>
"""

LOG_JS = """
<script>
function poll(){fetch('/log').then(r=>r.json()).then(j=>{
  const pre=document.getElementById('log'); if(!pre) return;
  pre.textContent=(j.name?('['+j.name+']\\n'):'')+j.lines.join('\\n');
  pre.scrollTop=pre.scrollHeight;
  const s=document.getElementById('status'); if(s) s.textContent=j.running?'running...':(j.rc===null?'':'done');
  if(j.running) setTimeout(poll,1000); else setTimeout(poll,4000);
});}
poll();
</script>
"""


def page(tab: str, body: str) -> str:
    tabs = [("home", "Home"), ("films", "Films"), ("build", "Build"), ("identify", "Identify"), ("wrong", "Wrong")]
    nav = "".join(f'<a href="/{t}" class="{"on" if t == tab else ""}">{label}</a>' for t, label in tabs)
    return f"<!doctype html><html><head><meta charset='utf-8'><title>PDQ for Nada</title>{STYLE}</head><body>" \
           f"<header><b>Trace · PDQ for Nada</b>{nav}</header><main>{body}</main>{LOG_JS}</body></html>"


def log_card(title: str = "Printout") -> str:
    return f"<div class='card'><b>{title}</b> <span id='status' class='muted'></span><pre id='log'></pre></div>"


@app.route("/log")
def log():
    with JOB_LOCK:
        return Response(json.dumps({"name": JOB["name"], "lines": JOB["lines"][-2000:], "running": JOB["running"], "rc": JOB["rc"]}),
                        mimetype="application/json")


# ---- Home ------------------------------------------------------------------------------------
@app.route("/")
@app.route("/home")
def home():
    ok, msg = credentials_ok()
    cat = read_catalogue()
    ids = read_list_ids()
    idx = index_summary()
    steps = []
    steps.append(f"<li><span class='{'ok' if ok else 'bad'}'>{'✓' if ok else '✗'}</span> {html.escape(msg)}</li>")
    steps.append(f"<li><span class='{'ok' if cat else 'bad'}'>{'✓' if cat else '✗'}</span> Catalogue: "
                 + (f"{len(cat)} films known." if cat else "not fetched yet.") + " <a href='/films'>Films tab</a></li>")
    steps.append(f"<li><span class='{'ok' if ids else 'bad'}'>{'✓' if ids else '✗'}</span> Your list: "
                 + (f"{len(ids)} films." if ids else "empty.") + "</li>")
    steps.append(f"<li><span class='{'ok' if idx else 'bad'}'>{'✓' if idx else '✗'}</span> Index: "
                 + (f"{idx['films']} films, {idx['hashes']:,} fingerprints, {idx['gb']:.2f} GB." if idx else "not built.") + " <a href='/build'>Build tab</a></li>")
    nxt = ("Copy credentials.env into this folder, then reload." if not ok else
           "Go to Films and press 'Fetch the catalogue'." if not cat else
           "Tick some films on the Films tab and save the list." if not ids else
           "Go to Build and press 'Build the index'." if not idx else
           "Go to Identify and drop a clip in.")
    body = f"""
    <div class='card'><h2 style='margin-top:0'>Where things stand</h2><ul>{''.join(steps)}</ul>
      <p><b>Next:</b> {html.escape(nxt)}</p>
      <p class='muted'>Folder: {html.escape(str(HERE))}. Read <b>PDQ_BASICS.md</b> first, then <b>HOW_TO_RUN.md</b>.</p></div>
    <div class='card'><b>Check the setup</b> (no key needed, about a minute): proves the rules on this laptop are the pod's rules.
      <form method='post' action='/run/selftest' style='margin-top:8px'><button>Run the rules check</button></form></div>
    {log_card()}"""
    return page("home", body)


@app.route("/run/selftest", methods=["POST"])
def run_selftest():
    run_job("rules check", ["tests/check_same_rules_as_trace.py"])
    return redirect("/home")


# ---- Films -----------------------------------------------------------------------------------
@app.route("/films")
def films():
    cat = read_catalogue()
    chosen = set(read_list_ids())
    q = (request.args.get("q") or "").strip()
    body = """<div class='card'><div class='row'>
      <form method='post' action='/run/catalogue'><button>Fetch the catalogue</button> <span class='muted'>reads every film from storage (a minute or two)</span></form>
    </div></div>"""
    if not cat:
        body += "<div class='card'>No catalogue yet. Press <b>Fetch the catalogue</b>, watch the printout, then reload this tab.</div>"
        return page("films", body + log_card())
    rows = cat
    if q:
        ql = q.lower()
        rows = [r for r in cat if ql in (r.get("title") or "").lower() or q == r.get("movie_id") or q == r.get("tmdb_id")]
    with_blob = sum(1 for r in cat if r.get("has_blob") == "yes")
    body += f"""<div class='card'><form method='get' action='/films' class='row'>
        <div><input type='text' name='q' value='{html.escape(q)}' placeholder='search a film by name, id or tmdb id'></div>
        <div style='flex:0'><button>Search</button></div></form>
        <p class='muted'>{len(cat)} films known, {with_blob} with fingerprints. Ticked: {len(chosen)}.</p>"""
    if q and not rows:
        body += f"<p class='bad'>We do not have a film called '{html.escape(q)}'. Check the spelling, or search by its TMDB id.</p>"
    elif q and all(r.get("has_blob") != "yes" for r in rows):
        body += f"<p class='bad'>'{html.escape(q)}' is known but has no fingerprint file yet, so it cannot go in an index.</p>"
    shown = rows[:400]
    body += f"""<form method='post' action='/films/save'>
        <p><button>Save ticked films to the list</button> <button class='grey' name='clear' value='1'>Untick everything</button>
        <span class='muted'>Showing {len(shown)} of {len(rows)}. Ticks on other pages are kept.</span></p>
        <table><tr><th></th><th>id</th><th>title</th><th>tmdb</th><th>index MB</th><th>fingerprints?</th></tr>"""
    for r in shown:
        mid = r["movie_id"]
        has = r.get("has_blob") == "yes"
        chk = "checked" if int(mid) in chosen else ""
        dis = "" if has else "disabled"
        body += (f"<tr><td><input type='checkbox' name='id' value='{mid}' {chk} {dis}></td><td>{mid}</td>"
                 f"<td>{html.escape(r.get('title') or '(no title yet)')}</td><td>{html.escape(r.get('tmdb_id') or '')}</td>"
                 f"<td>{html.escape(r.get('index_mb') or '')}</td><td>{'yes' if has else '<span class=bad>no, cannot be used</span>'}</td></tr>")
    body += "</table>"
    for mid in chosen:                       # keep ticks that are not on this page
        if not any(int(r["movie_id"]) == mid for r in shown):
            body += f"<input type='hidden' name='id' value='{mid}'>"
    body += "</form></div>"
    return page("films", body + log_card())


@app.route("/films/save", methods=["POST"])
def films_save():
    cat = {r["movie_id"]: r for r in read_catalogue()}
    ids = [] if request.form.get("clear") else [i for i in request.form.getlist("id") if i in cat]
    DATA.mkdir(parents=True, exist_ok=True)
    lines = ["# movies_to_include.txt - the films that go into YOUR index.",
             "# One film per line: the id, then a | and the name. Only the id at the start matters.",
             "# Delete lines you do not want. Paste in lines from data/movies_catalogue.csv.",
             "# Lines starting with # are ignored. Then build (Build tab, or python 2_build_index.py)",
             f"# saved from the page: {len(ids)} films", "#"]
    keep_local = [ln for ln in (LIST.read_text(encoding="utf-8").splitlines() if LIST.is_file() else [])
                  if re.match(r"\s*9\d{5}\b", ln)]          # your own fingerprinted films stay on the list
    for i in ids:
        r = cat[i]
        lines.append(f"{i} | {r.get('title')} (tmdb={r.get('tmdb_id')})  [{r.get('index_mb')} MB]")
    LIST.write_text("\n".join(lines + keep_local) + "\n", encoding="utf-8")
    return redirect("/films")


@app.route("/run/catalogue", methods=["POST"])
def run_catalogue():
    run_job("catalogue", ["1_get_movie_catalogue.py", "--new-list", "--starter", "30"])
    return redirect("/films")


# ---- Build -----------------------------------------------------------------------------------
@app.route("/build")
def build():
    ids = read_list_ids()
    idx = index_summary()
    inside = ""
    if idx:
        inside = "<details><summary>What is inside now</summary><ol start='0'>" + "".join(
            f"<li>{html.escape(l)}</li>" for l in idx["labels"]) + "</ol></details>"
    body = f"""
    <div class='card'><h3 style='margin-top:0'>Build from your list</h3>
      <p>{len(ids)} films on the list (<a href='/films'>change it</a>). A film we do not have is reported in the printout, never silently skipped.</p>
      <form method='post' action='/run/build'><button>Build the index</button></form></div>
    <div class='card'><h3 style='margin-top:0'>Or build to a size</h3>
      <form method='post' action='/run/build_gb' class='row'>
        <div><label>Size in GB (2 behaves like the pod; about 430 films)</label><input type='number' step='0.1' min='0.05' name='gb' value='2'></div>
        <div style='flex:0'><button>Pick films and build</button></div></form>
      <p class='muted'>Rewrites the list to match, downloads the fingerprint files, builds. Needs about 2.5 GB of free memory for a 2 GB index.</p></div>
    <div class='card'><h3 style='margin-top:0'>Or add a film file you have</h3>
      <form method='post' action='/run/build_video' class='row'>
        <div><label>Path to the film file</label><input type='text' name='path' placeholder='D:\\films\\Boyhood.mp4'></div>
        <div><label>Title</label><input type='text' name='title' placeholder='Boyhood'></div>
        <div><label>TMDB id (optional)</label><input type='text' name='tmdb' placeholder='85350'></div>
        <div style='flex:0'><button>Fingerprint and build</button></div></form>
      <p class='muted'>Fingerprinted exactly as the pod does it. About a tenth of the film's length.</p></div>
    <div class='card'><b>Index now:</b> {(f"{idx['films']} films, {idx['hashes']:,} fingerprints, {idx['gb']:.2f} GB" if idx else "none")} {inside}</div>
    {log_card()}"""
    return page("build", body)


@app.route("/run/build", methods=["POST"])
def run_build():
    run_job("build", ["2_build_index.py"])
    return redirect("/build")


@app.route("/run/build_gb", methods=["POST"])
def run_build_gb():
    gb = request.form.get("gb") or "2"
    run_job("build to size", ["2_build_index.py", "--target-gb", gb])
    return redirect("/build")


@app.route("/run/build_video", methods=["POST"])
def run_build_video():
    args = ["2_build_index.py", "--from-video", request.form.get("path", ""), "--title", request.form.get("title", "")]
    if request.form.get("tmdb"):
        args += ["--tmdb", request.form["tmdb"]]
    run_job("fingerprint + build", args)
    return redirect("/build")


# ---- Identify --------------------------------------------------------------------------------
@app.route("/identify")
def identify():
    idx = index_summary()
    clips = sorted(CLIPS.glob("*")) if CLIPS.is_dir() else []
    recent = "".join(f"<li><a href='/run/identify?clip={html.escape(c.name)}'>replay</a> {html.escape(c.name)}</li>" for c in clips[-15:])
    body = f"""
    <div class='card'><h3 style='margin-top:0'>Identify a clip</h3>
      <p class='muted'>Index: {(f"{idx['films']} films, {idx['gb']:.2f} GB" if idx else "<span class=bad>none built yet</span>")}</p>
      <form method='post' action='/run/identify' enctype='multipart/form-data' class='row'>
        <div><label>A clip file from your laptop</label><input type='file' name='file'></div>
        <div><label>or a link</label><input type='text' name='url' placeholder='https://www.tiktok.com/@.../video/...'></div>
        <div style='flex:0'><label><input type='checkbox' name='noprescan'> skip the pre-scan (watch the rules)</label></div>
        <div style='flex:0'><button>Identify</button></div></form>
      <p class='muted'>Links go through yt-dlp. YouTube often refuses; TikTok and Instagram usually work. If a link fails, save the clip and upload the file.</p></div>
    <div class='card'><b>Clips already here</b> (data/clips)<ul>{recent or '<li class=muted>none yet</li>'}</ul></div>
    {log_card("The pod's printout")}"""
    return page("identify", body)


@app.route("/run/identify", methods=["GET", "POST"])
def run_identify():
    CLIPS.mkdir(parents=True, exist_ok=True)
    target = None
    if request.method == "GET":
        name = request.args.get("clip", "")
        if name and (CLIPS / name).is_file():
            target = str(CLIPS / name)
    else:
        f = request.files.get("file")
        if f and f.filename:
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", f.filename)[:100]
            dest = CLIPS / safe
            f.save(str(dest))
            target = str(dest)
        elif request.form.get("url", "").strip():
            target = request.form["url"].strip()
    if not target:
        return redirect("/identify")
    args = ["3_identify_clip.py", target]
    if request.form.get("noprescan") or request.args.get("noprescan"):
        args.append("--no-prescan")
    run_job("identify", args)
    return redirect("/identify")


# ---- Wrong -----------------------------------------------------------------------------------
def csv_table(path: Path, cols: list) -> str:
    if not path.is_file():
        return "<p class='muted'>not pulled yet</p>"
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    out = f"<p class='muted'>{len(rows)} clips</p><table><tr><th></th>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr>"
    for r in rows[:300]:
        url = r.get("url", "")
        out += f"<tr><td><a class='btn' style='padding:3px 8px' href='/run/identify?clip=&url={html.escape(url)}' onclick=\"return replay('{html.escape(url)}')\">replay</a></td>"
        out += "".join(f"<td>{html.escape(str(r.get(c) or ''))}</td>" for c in cols) + "</tr>"
    return out + "</table>"


@app.route("/wrong")
def wrong():
    cols = ["url", "answered_movie", "answered_movie_id", "user_said_it_was", "expected_movie_id", "wrong_count", "correct_count", "final_engine", "local_strength"]
    body = f"""
    <div class='card'><h3 style='margin-top:0'>The clips PDQ got wrong, and the ones it got right</h3>
      <form method='post' action='/run/wrong'><button>Pull from the pod's database</button></form>
      <p class='muted'>Read-only. Writes data/wrong_pdq_clips.csv and data/correct_pdq_clips.csv. Replay sends the link to the Identify tab; the answered film must be in your index to see the rule.</p></div>
    <div class='card'><h3>Wrong (the work)</h3>{csv_table(WRONG, cols)}</div>
    <div class='card'><h3>Correct (the control)</h3>{csv_table(CORRECT, cols)}</div>
    <form id='replayform' method='post' action='/run/identify'><input type='hidden' name='url' id='replayurl'><input type='hidden' name='noprescan' value='1'></form>
    <script>function replay(u){{document.getElementById('replayurl').value=u;document.getElementById('replayform').submit();return false;}}</script>
    {log_card()}"""
    return page("wrong", body)


@app.route("/run/wrong", methods=["POST"])
def run_wrong():
    run_job("pull wrong clips", ["4_pull_wrong_pdq_clips.py"])
    return redirect("/wrong")


if __name__ == "__main__":
    print(f"\n  PDQ for Nada is running. Open  http://127.0.0.1:{PORT}  in your browser. Press Ctrl+C here to stop.\n")
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)

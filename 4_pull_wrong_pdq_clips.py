# -*- coding: utf-8 -*-
"""
4_pull_wrong_pdq_clips.py - the clips PDQ got wrong, and the clips it got right.

    python 4_pull_wrong_pdq_clips.py
    python 4_pull_wrong_pdq_clips.py --show-sql      (print the queries, connect to nothing)

What it writes, in data/:
  wrong_pdq_clips.csv     clips where PDQ gave the answer and at least one user pressed "wrong".
                          With the film PDQ said, the film the user said it really was (when
                          they told us), and the clip link, so you can replay it with step 3.
  correct_pdq_clips.csv   clips where PDQ gave the answer and a user confirmed it. This is
                          the CONTROL. A rule change must keep these right. A change that
                          fixes the first file and breaks this one is not a fix.

Where it comes from: the pod's database, read-only, through DATABASE_URL_READONLY in
credentials.env. Two tables:
  traced_clips          one row per clip anyone ever sent. match_source says which detective
                        answered ('pdq' for us). wrong_count and correct_count are the votes.
  wrong_movie_reports   one row per "wrong" press, with what the user said the film really was.

What it cannot tell you: WHICH RULE fired. That is only in the pod's log. To see it, put the
answered film in your index (step 2 can take its id from this file) and replay the clip
with step 3. The printout shows the rule and the scorecard.

Two honest limits, found by pdq/tools/measure_pdq_rules_v2.py on the pod:
  - only a few dozen rows carry match_source = 'pdq' with a vote, so counts are small;
  - a clip can be traced more than once, and a later trace may have been answered by another
    detective. The row keeps the LAST answer. Read final_engine and local_strength too.
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CATALOGUE = DATA / "movies_catalogue.csv"
WRONG_OUT = DATA / "wrong_pdq_clips.csv"
CORRECT_OUT = DATA / "correct_pdq_clips.csv"

COLS = "url, platform, tmdb_id, movie_name, media_type, match_source, trace_count, wrong_count, correct_count, implicit_positive_count, final_engine, local_strength, local_suggestion, gemini_suggestion, engines_agreed"
SQL_WRONG = f"SELECT {COLS} FROM traced_clips WHERE match_source = 'pdq' AND wrong_count > 0 ORDER BY wrong_count DESC, id DESC"
SQL_CORRECT = f"SELECT {COLS} FROM traced_clips WHERE match_source = 'pdq' AND correct_count > 0 AND wrong_count = 0 ORDER BY correct_count DESC, id DESC"
SQL_REPORTS = "SELECT link, movie_name, tmdb_id, expected_movie, final_engine, created_at FROM wrong_movie_reports WHERE link IS NOT NULL ORDER BY created_at DESC"
OUT_COLS = ["url", "platform", "answered_movie", "answered_tmdb_id", "answered_movie_id", "answered_in_catalogue",
            "user_said_it_was", "expected_movie_id", "wrong_count", "correct_count", "implicit_positive_count",
            "trace_count", "final_engine", "local_strength", "engines_agreed", "local_suggestion", "gemini_suggestion", "media_type"]


def connect(url: str):
    """A read-only connection. Postgres through psycopg2 (the pod's database), or a sqlite
    file (sqlite:///path) for testing. Returns (connection, a function that runs a query)."""
    if url.startswith("sqlite:///"):
        import sqlite3
        con = sqlite3.connect(url[len("sqlite:///"):])
        con.row_factory = sqlite3.Row

        def run(sql):
            return [dict(r) for r in con.execute(sql).fetchall()]
        return con, run
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        raise SystemExit("psycopg2 is not installed. Run: pip install -r requirements.txt")
    con = psycopg2.connect(url, connect_timeout=20)
    con.set_session(readonly=True, autocommit=True)      # belt and braces: this session cannot write

    def run(sql):
        with con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]
    return con, run


def read_catalogue() -> tuple:
    """Two lookups from step 1's catalogue: by TMDB id, and by lower-cased title."""
    by_tmdb, by_title = {}, {}
    if CATALOGUE.is_file():
        with open(CATALOGUE, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("tmdb_id", "").strip().isdigit():
                    by_tmdb.setdefault(int(r["tmdb_id"]), r)
                if r.get("title", "").strip():
                    by_title.setdefault(r["title"].strip().lower(), r)
    return by_tmdb, by_title


def enrich(rows: list, reports: dict, by_tmdb: dict, by_title: dict) -> list:
    out = []
    for r in rows:
        tmdb = r.get("tmdb_id")
        cat = by_tmdb.get(int(tmdb)) if tmdb not in (None, "") else None
        rep = reports.get(r.get("url"))
        said = (rep or {}).get("expected_movie") or ""
        exp = by_title.get(said.strip().lower()) if said else None
        out.append({
            "url": r.get("url"), "platform": r.get("platform"),
            "answered_movie": r.get("movie_name"), "answered_tmdb_id": tmdb,
            "answered_movie_id": (cat or {}).get("movie_id", ""),
            "answered_in_catalogue": "yes" if cat else "no",
            "user_said_it_was": said, "expected_movie_id": (exp or {}).get("movie_id", ""),
            "wrong_count": r.get("wrong_count"), "correct_count": r.get("correct_count"),
            "implicit_positive_count": r.get("implicit_positive_count"), "trace_count": r.get("trace_count"),
            "final_engine": r.get("final_engine"), "local_strength": r.get("local_strength"),
            "engines_agreed": r.get("engines_agreed"), "local_suggestion": r.get("local_suggestion"),
            "gemini_suggestion": r.get("gemini_suggestion"), "media_type": r.get("media_type"),
        })
    return out


def write(path: Path, rows: list) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in OUT_COLS})


def main() -> int:
    ap = argparse.ArgumentParser(description="Pull the clips PDQ got wrong, and the ones it got right.")
    ap.add_argument("--show-sql", action="store_true", help="print the three queries and stop")
    ap.add_argument("--db", help="a database url to use instead of DATABASE_URL_READONLY (testing)")
    a = ap.parse_args()
    if a.show_sql:
        print(SQL_WRONG + "\n\n" + SQL_CORRECT + "\n\n" + SQL_REPORTS)
        return 0

    url = a.db
    if not url:
        from b2_access import load_credentials
        url = load_credentials().get("DATABASE_URL_READONLY", "")
        if not url:
            raise SystemExit("DATABASE_URL_READONLY is empty in credentials.env. Ask Jude for the read-only database link.")

    con, run = connect(url)
    try:
        wrong = run(SQL_WRONG)
        correct = run(SQL_CORRECT)
        reports = {}
        for r in run(SQL_REPORTS):
            reports.setdefault(r["link"], r)          # newest report per link (the query is newest first)
    finally:
        con.close()

    by_tmdb, by_title = read_catalogue()
    if not by_tmdb:
        print("note: no data/movies_catalogue.csv yet, so the film ids cannot be filled in. Run step 1 first for that.")
    wrong_rows = enrich(wrong, reports, by_tmdb, by_title)
    correct_rows = enrich(correct, reports, by_tmdb, by_title)
    write(WRONG_OUT, wrong_rows)
    write(CORRECT_OUT, correct_rows)

    print(f"wrote {WRONG_OUT}    {len(wrong_rows)} clips PDQ answered and a user said wrong")
    print(f"wrote {CORRECT_OUT}  {len(correct_rows)} clips PDQ answered and a user said correct (the control)")
    told = sum(1 for r in wrong_rows if r["user_said_it_was"])
    have = sum(1 for r in wrong_rows if r["answered_in_catalogue"] == "yes")
    print(f"of the wrong ones: {told} come with what the user said the film was; {have} answered films are in your catalogue")
    if wrong_rows:
        films = {}
        for r in wrong_rows:
            films[r["answered_movie"]] = films.get(r["answered_movie"], 0) + int(r["wrong_count"] or 0)
        print("films most often given as the wrong answer:")
        for name, n in sorted(films.items(), key=lambda x: -x[1])[:10]:
            print(f"  {n:3d}  {name}")
    print("\nnext: put the answered films in your index (step 1 will seed the list from this file), then replay each clip with step 3.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

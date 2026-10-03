# pdq_for_nada

## What this folder is

A copy of Trace's PDQ detective that runs on an ordinary Windows laptop, with no graphics
card. It is for Nada, so she can build her own small search index from the real film
fingerprints, send clips through it, and see exactly what the pod sees.

PDQ is the fast picture fingerprint. Every frame of a film becomes a code of 256 ones and
zeros. A clip's frames get the same kind of code. Codes that differ in only a few places
mean the same picture. The number of differing places is called the Hamming distance.
The rest of how it works is in `../pdq/README.md`.

This folder does the same steps as the pod, in the same order, with the same numbers. The
only difference is the index form. The pod uses a form built for 9,500 films and lots of
memory. This folder uses the "flat" form, which the laptop can memory-map: the file stays
on disk and only the parts being read come into memory.

## The one command

```
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5077 in a browser. The page has five tabs: Home, Films, Build,
Identify, Wrong. It runs the four scripts below for you and shows their printouts live. The
scripts also run on their own from a terminal. Both ways do exactly the same thing.

This folder works on its own. Copy just this folder anywhere, put `credentials.env` in it,
and everything runs. The rest of the repo is not needed.

## Read this first

`PDQ_BASICS.md` (also `PDQ_BASICS.pdf`) explains PDQ from the start. What a fingerprint is.
The three bands. Matched frames and average Hamming. The two kinds of bucket. The early
exit rules, in plain words. The wait before a weak answer. Hints. Consensus. How PDQ gets
things wrong, and how to measure it. Read it before anything else.

## The job this folder is for

PDQ sometimes answers with the wrong film. Users press "wrong" and the database records it.
The job is to make those wrong answers stop, without losing the right answers PDQ gives
today. Every change to a rule has to be measured on both lists: the wrong answers it
removes, and the right answers it keeps. `4_pull_wrong_pdq_clips.py` pulls both lists.

## The three steps

1. `1_get_movie_catalogue.py` writes a list of every film in the library and a starter list
   of films to include. You edit the list.
2. `2_build_index.py` downloads the fingerprints of the films on your list and builds the
   index. To change the index, edit the list, delete the `data/index` folder, and run this again.
3. `3_identify_clip.py` sends a clip through the index and prints what the pod would print.

`HOW_TO_RUN.md` walks through all three with the exact commands and what you will see.

## Before you start

- Install Python 3.11 or 3.12.
- Open a terminal in this folder and run `pip install -r requirements.txt`.
- Put the `credentials.env` file Jude sent you into this folder.

## The files

| file | what it is | when you use it |
|---|---|---|
| `requirements.txt` | The list of Python packages to install. Each line says what the package is for. | Once, before anything else. |
| `credentials.env.example` | A template showing what `credentials.env` holds. Jude sends you the real `credentials.env` separately. Put it in this folder. It is never committed. | Once. |
| `.gitignore` | Tells git never to save `credentials.env` or the big files in `data/`. | You never touch it. |
| `.gitattributes` | Tells git the PDF and the logo are binary files, not text. | You never touch it. |
| `app.py` | The local web page. One command, one browser tab, all four steps. | Every day. |
| `b2_access.py` | The small door to our online storage, read-only. Reads the key from `credentials.env`, lists files, downloads files. Steps 1 and 2 use it. | You never run it. |
| `pdq_engine.py` | The shared code. It decodes a fingerprint file. It pulls frames from a clip, crops them, and turns each one into a fingerprint (that step is called hashing). It searches, counts, and applies the early exit rules. Every step has a comment. The three scripts use it. | You read it when you want to know how a step works. |
| `1_get_movie_catalogue.py` | Step 1. Makes `data/movies_catalogue.csv` and `data/movies_to_include.txt`. | Once, and again if you want a fresh starter list. |
| `2_build_index.py` | Step 2. Builds `data/index/` from the films in `data/movies_to_include.txt`. | Every time you change the list. |
| `3_identify_clip.py` | Step 3. Identifies one clip against the index. The index path is a line near the top. | Every clip you test. |
| `4_pull_wrong_pdq_clips.py` | Pulls two lists from the pod's database. The clips where PDQ answered and a user said "wrong". And the clips where a user said "correct". Two spreadsheets, with the clip links, so you can replay them. | When you start work on the rules, and after every change. |
| `PDQ_BASICS.md` | The explainer. Read it first. | Your first day. |
| `PDQ_BASICS.pdf` | The same explainer as a PDF. | When you want to print it or read it on a phone. |
| `build_pdf.py` | Makes the two PDFs from the two Markdown files. Needs `pip install reportlab pillow`. | Only if you edit `PDQ_BASICS.md` or `HOW_TO_RUN.md`. |
| `trace_logo.png` | The Trace logo, for the top of the PDF. | Never touched. |
| `HOW_TO_RUN.md` | The walkthrough, with the printouts explained. | Your first day with this folder. |
| `HOW_TO_RUN.pdf` | The same walkthrough as a PDF. | When you want to print it or read it on a phone. |
| `data/` | Where the catalogue, the list, the fingerprints, the index and your clips live. Has its own note. | Always. |
| `tests/` | Three checks that prove the engine does what the pod does. Has its own note. | Once after installing. And after you change a rule. |

## The plan for building this folder

| part | what | state |
|---|---|---|
| 1 | The folder, the requirements, the credentials template. | Done 4 Sep 2026. |
| 2 | `PDQ_BASICS.md` and its PDF. Then `pdq_engine.py`, checked against Trace's own code: same fingerprints, same rules. | Done 4 Sep 2026. |
| 3 | `1_get_movie_catalogue.py`. Tested against a copy of the storage laid out like the real bucket. | Done 4 Sep 2026. |
| 3b | `app.py`, the one-command web page. Every tab driven by a test the way Nada would use it. | Done 4 Sep 2026. |
| 4 | `2_build_index.py`, with `--target-gb` and `--from-video`. Every film's counts match the pod's index exactly. | Done 4 Sep 2026. |
| 5 | `3_identify_clip.py`, checked with clips cut from a known film. | Done 4 Sep 2026. |
| 6 | `HOW_TO_RUN.md`, with the printouts explained. | Done 4 Sep 2026. |
| 7 | `4_pull_wrong_pdq_clips.py`, with the correct-answer list as the control. Tested on a test database. | Done 4 Sep 2026. |
| 8 | Final checks, a full run from an empty folder, and the hand-over note below. | Done 4 Sep 2026. |

## Before Nada starts: what Jude does

1. Send Nada the `credentials.env` file separately (not through git). She drops it into
   this folder. The pod's own `.env` works as it is: the loader reads its names.
2. Nothing in this folder writes to storage or to the database. The B2 door only lists and
   reads. The database session is opened read-only. Still, a key that can only read is
   safer than one that can write. When there is time, make one and send that instead.

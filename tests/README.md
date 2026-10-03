# tests

## What this folder is

Three checks that prove `pdq_engine.py` does what the pod does. Run them from the
`pdq_for_nada` folder. Each one prints `RESULT: PASS` or `RESULT: FAIL` at the end.

| file | what it proves | what it needs | how long |
|---|---|---|---|
| `check_same_rules_as_trace.py` | The scorecards and every early exit rule give the pod's answer. Checked on thousands of made-up search results. | Nothing. It reads the pod's code from `../pdq/`. | About a minute. |
| `check_same_fingerprints_as_trace.py` | The frames, the crops and the fingerprints are byte for byte the pod's. The film side too. | Any short video file, and the repo's `pdq/` folder next to this one. Says SKIPPED without it. | Under a minute. |
| `pod_rules_snapshot.py` | Not a test. The pod's rule code, copied word for word, so the first test runs when only this folder is present. | Never run. |
| `refresh_pod_rules_snapshot.py` | Copies the pod's rule code into the snapshot again. Needs the repo's `pdq/` folder next to this one. | When the pod's rules change. |
| `check_end_to_end.py` | A film goes in and an index comes out. Clips cut from the film are found. A clip of nothing is not. | A film file you have on disk. | A few minutes. |

```
python tests/check_same_rules_as_trace.py
python tests/check_same_fingerprints_as_trace.py  path/to/short_video.mp4
python tests/check_end_to_end.py  path/to/a_film.mp4  --distractors data/index
```

## When to run them

- After `pip install -r requirements.txt`, run all three once. If they pass, your laptop
  is set up right.
- After you change a rule in `pdq_engine.py` on purpose, `check_same_rules_as_trace.py`
  will fail on that rule. That is expected. It tells you exactly what changed. The other
  two should still pass.

## Words used

| word | meaning |
|---|---|
| distractors | Other films put in the index so the clip has something to be confused with. The real test. |
| byte for byte | Exactly the same, down to the last bit. |

# -*- coding: utf-8 -*-
"""
refresh_pod_rules_snapshot.py - copy the pod's rule code into pod_rules_snapshot.py again.

    python tests/refresh_pod_rules_snapshot.py

Run it from a checkout that has the pdq/ folder next to pdq_for_nada/. It takes the same
line ranges check_same_rules_as_trace.py reads, and writes them into the snapshot file.
"""
from __future__ import annotations

import datetime
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
POD = next((HERE.parent.parent / "pdq").glob("pdq_query_cli_dynamic_shards_*" + "PASS2_ALWAYS" + ".py"))
L = POD.read_text(encoding="utf-8").splitlines()


def find(pat: str, start: int = 0) -> int:
    for i in range(max(0, start - 1), len(L)):
        if pat in L[i]:
            return i + 1
    raise RuntimeError(f"not found: {pat}")


def block(a: int, b: int) -> str:
    return textwrap.dedent("\n".join(L[a - 1:b])) + "\n"


def main() -> None:
    p9 = find("def _pdq_p9_min_frames")
    c0 = find("HAMMING_CUTOFF_EXCL = 45.0")
    m0 = find("movie_stats = defaultdict(", c0)
    h0 = find("def _best_aligned_bucket_range", m0)
    r0 = find("def _do_stats_update", h0)
    parts = [("P9_MIN_FRAMES", block(p9, find("class ShardedPDQ", p9) - 1)),
             ("CONSTANTS", block(c0, find("PENDING_WAIT_VIDEO_S = 3.0", c0))),
             ("SCORECARD", block(m0, find("pending_exit = {", m0) + 7)),
             ("HELPERS", block(h0, find("def _set_pending_exit", h0) - 1)),
             ("RULES", block(r0, find("def _stream_update_from_frame", r0) - 1))]
    today = datetime.date.today().isoformat()
    out = ["# -*- coding: utf-8 -*-", '"""', "pod_rules_snapshot.py - the pod's rule code, copied word for word.", "",
           f"Taken on {today} from the long-named query program in the pod's pdq/ folder", f"({POD.name}),",
           "the constants, the scorecard, the helpers and the rules.",
           "check_same_rules_as_trace.py uses the live file when ../pdq is next to this folder, and this",
           "snapshot when it is not. If the pod's rules change, refresh this file: run",
           "    python tests/refresh_pod_rules_snapshot.py", "from a checkout that has the pdq/ folder.", '"""', "",
           f"SOURCE_FILE = {POD.name!r}", f"TAKEN_ON = {today!r}", ""]
    for name, text in parts:
        out.append(f"{name} = {text!r}")
        out.append("")
    (HERE / "pod_rules_snapshot.py").write_text("\n".join(out), encoding="utf-8")
    print("wrote", HERE / "pod_rules_snapshot.py", "-", sum(len(t.splitlines()) for _, t in parts), "lines of pod code")


if __name__ == "__main__":
    main()

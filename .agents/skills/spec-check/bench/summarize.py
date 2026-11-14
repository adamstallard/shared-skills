"""Tables of tokens, time and rubric score per case and version, pooled over
one or more iterations.

    python3 -I summarize.py <iteration-dir> [<iteration-dir> ...] > summary.md

Tokens are each run's total, main loop and subagents together. "main" and
"reader" are the main loop's and the subagents' tokens as the transcript
records them, which comes to a little less than the total. "rubric" counts
the expectations passed, the no-false-positive ones included, and "detect"
counts the planted defects found.

Every finished run counts in tokens, time and cost, but only graded runs count
in "rubric" and "detect"; the ungraded ones are listed after the tables.
Failed and unfinished runs count nowhere and are listed before the tables.
"""

from __future__ import annotations

import json
import pathlib
import statistics as st
import sys
from typing import Any


def load(run: pathlib.Path) -> dict[str, Any] | None:
    """A finished run's numbers; its rubric counts are zero while ungraded."""
    try:
        m = json.loads((run / "metrics.json").read_text())
    except FileNotFoundError:
        return None
    try:
        g = json.loads((run / "grading.json").read_text())
    except FileNotFoundError:
        g = None
    by: dict[str, int] = m["transcript_tokens_by_agent"]
    exps: list[dict[str, Any]] = g["expectations"] if g else []
    detect = [e for e in exps if e.get("kind") == "detect"]
    return {"tokens": m["total_tokens"], "main": by.get("main", 0),
            "reader": sum(v for k, v in by.items() if k != "main"),
            "secs": m["wall_seconds"], "cost": m["cost_usd"] or 0.0,
            "passed": sum(bool(e["passed"]) for e in exps), "total": len(exps),
            "found": sum(bool(e["passed"]) for e in detect), "planted": len(detect),
            "skill": m["skill_used"], "graded": g is not None, "run": str(run)}


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python3 -I summarize.py <iteration-dir> [...]")
    runs: dict[tuple[str, str], list[dict[str, Any]]] = {}
    failed: list[str] = []
    for it in map(pathlib.Path, sys.argv[1:]):
        for run in sorted(it.glob("eval-*/*/run-*")):
            if not (run / "metrics.json").exists():
                failed.append(str(run))
            r = load(run)
            if r is not None:
                case, version = run.parent.parent.name.removeprefix("eval-"), run.parent.name
                runs.setdefault((version, case), []).append(r)
    if failed:
        print(f"Runs that failed or did not finish, left out of every column "
              f"(rerun run_bench.py): "
              f"{', '.join(failed)}\n")
    if not runs:
        sys.exit("no finished runs found")
    versions = sorted({v for v, _ in runs}, key=lambda v: (v != "baseline", v))
    cases = sorted({c for _, c in runs})

    print("| case | " + " | ".join(versions) + " |")
    print("| --- |" + " --- |" * len(versions))
    for c in cases:
        cells: list[str] = []
        for v in versions:
            rs = runs.get((v, c), [])
            cells.append(f"{st.mean(r['tokens'] for r in rs) / 1000:.0f}k, "
                         f"{st.mean(r['secs'] for r in rs):.0f}s, "
                         f"{sum(r['passed'] for r in rs)}/{sum(r['total'] for r in rs)} "
                         f"(n={len(rs)})" if rs else "-")
        print(f"| {c} | " + " | ".join(cells) + " |")
    print()
    print("| version | runs | tokens/run | sd | main | reader | wall | cost/run | rubric | detect |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for v in versions:
        rs = [r for (vv, _), lst in runs.items() if vv == v for r in lst]
        tok = [r["tokens"] for r in rs]
        passed, total = sum(r["passed"] for r in rs), sum(r["total"] for r in rs)
        print(f"| {v} | {len(rs)} | {st.mean(tok) / 1000:.0f}k | "
              f"{(st.stdev(tok) if len(tok) > 1 else 0) / 1000:.0f}k | "
              f"{st.mean(r['main'] for r in rs) / 1000:.0f}k | "
              f"{st.mean(r['reader'] for r in rs) / 1000:.0f}k | "
              f"{st.mean(r['secs'] for r in rs):.0f}s | ${st.mean(r['cost'] for r in rs):.3f} | "
              f"{passed}/{total} ({100 * passed / total if total else 0:.0f}%) | "
              f"{sum(r['found'] for r in rs)}/{sum(r['planted'] for r in rs)} |")
    ungraded = sorted(r["run"] for lst in runs.values() for r in lst if not r["graded"])
    if ungraded:
        print(f"\nRuns not graded, counted in tokens, time and cost only: {', '.join(ungraded)}")
    missed = sorted({f"{v}/{c}" for (v, c), lst in runs.items() for r in lst if not r["skill"]})
    if missed:
        print(f"\nRuns that never loaded the skill: {', '.join(missed)}")


if __name__ == "__main__":
    main()

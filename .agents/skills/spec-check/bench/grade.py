"""Grade benchmark runs against rubrics.json with a tool-less `claude -p`.

    python3 -I grade.py --work <empty-dir> [--model claude-opus-5-5] \\
        [--parallel 7] <iteration-dir> [version ...]

Grades each finished run (one with metrics.json) and writes grading.json
beside its report.md and changes.patch, in skill-creator's schema (each
expectation with the fields text, passed and evidence, plus a summary). Each
expectation also gets a kind: "detect" for a planted defect the run must
find, and "no-false-positive" for every other item: the must-not items, and
a clean case's must items. A run already graded is skipped. A reply that
leaves an expectation unanswered prints GRADER FAILED and writes nothing, so
the next call grades that run again.
The grader runs in <empty-dir>, so it reads no project settings.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import pathlib
import subprocess
from typing import Any, cast

HERE = pathlib.Path(__file__).resolve().parent
RUBRICS: dict[str, Any] = json.loads((HERE / "rubrics.json").read_text())
PATCH_LIMIT = 60000

PROMPT = """You grade one run of an agent that was asked: "{task}"

The repository holds a staged OpenSpec change, `{change}`, built with one known defect (or none).
The known answer: {what}

The agent follows the spec-check skill, whose rules include: every SHALL/MUST requirement needs a
scenario; a decision record (openspec/specs/<capability>/decisions.md) holds only Constraint, Rejected and
Rationale entries with linked Evidence; a Rationale entry's title must equal its requirement's exact title;
a record entry whose rule a requirement or scenario already states is cut; a rejection that a requirement
guards against belongs in that requirement's Rationale; record material (a constraint, a rejected
alternative, or a reason with evidence) belongs only in the record, never repeated in design.md; an
unmeasured fact a change relies on becomes a task and an open question; conflicts with other specs are
reported with both sides quoted. Judge extra findings against these rules and the files.

Grade the run against each expectation below, using only the agent's final report and the
diff of what it changed. An expectation passes only on clear evidence in the report or diff.
A finding the agent reports beyond the known answer is not a false positive when it is a real,
defensible problem under the rules the agent cites; it is a false positive when it is wrong, or
when it claims a defect the files do not have. Quote the evidence briefly.

Expectations:
{expectations}

=== FINAL REPORT ===
{report}

=== DIFF ===
{patch}

Reply with only a JSON object, no code fence:
{{"expectations": [{{"text": "<the expectation, verbatim>", "passed": true|false, "evidence": "<one or two sentences>"}}], "extra_findings": ["<each finding beyond the known answer, marked REAL or FALSE-POSITIVE>"]}}
"""


def expectations(case: str) -> list[tuple[str, str]]:
    """(kind, text) for each expectation of the case. A clean case's "must"
    is that nothing is flagged, so it is a no-false-positive item."""
    rub = RUBRICS["cases"][case]
    must_kind = "no-false-positive" if rub.get("clean") else "detect"
    return ([(must_kind, f"MUST: {m}") for m in rub["must"]]
            + [("no-false-positive", f"MUST NOT: {m}") for m in rub["must_not"]]
            + [("no-false-positive", f"MUST NOT: {m}") for m in RUBRICS["common_must_not"]])


def ask(prompt: str, cwd: pathlib.Path, model: str) -> dict[str, Any] | None:
    """The grader's JSON reply, or None after three unreadable replies."""
    for _ in range(3):
        r = subprocess.run(["claude", "-p", prompt, "--setting-sources", "project", "--tools", "",
                            "--output-format", "json", "--no-session-persistence",
                            "--model", model], cwd=cwd, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=900)
        try:
            text = str(json.loads(r.stdout)["result"])
            reply: Any = json.loads(text[text.index("{"): text.rindex("}") + 1])
        except (ValueError, KeyError, TypeError):
            continue
        if isinstance(reply, dict) and isinstance(reply.get("expectations"), list):  # pyright: ignore[reportUnknownMemberType]
            return cast(dict[str, Any], reply)
    return None


def grade(run: pathlib.Path, case: str, cwd: pathlib.Path, model: str) -> str:
    out = run / "grading.json"
    if out.exists():
        return f"{run}: graded already"
    rub = RUBRICS["cases"][case]
    exps = expectations(case)
    prompt = PROMPT.format(task=RUBRICS["prompt"], change=rub["change"], what=rub["what"],
                           expectations="\n".join(f"- {t}" for _, t in exps),
                           report=(run / "report.md").read_text(),
                           patch=(run / "changes.patch").read_text()[:PATCH_LIMIT])
    reply = ask(prompt, cwd, model)
    if reply is None:
        return f"{run}: GRADER FAILED (no readable reply)"
    # Each answer is matched to its expectation by the text it echoes, not by
    # its position, and used once.
    answers: list[Any] = list(reply["expectations"])
    graded: list[dict[str, Any]] = []
    for kind, t in exps:
        match: Any = next((a for a in answers if isinstance(a, dict)
                      and str(a.get("text", "")).strip() == t.strip()), None)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        if match is None:
            return f"{run}: GRADER FAILED (no answer for: {t[:60]})"
        answers.remove(match)
        e = cast(dict[str, Any], match)
        graded.append({"text": t, "kind": kind, "passed": bool(e.get("passed")),
                       "evidence": str(e.get("evidence", ""))})
    passed = sum(1 for e in graded if e["passed"])
    summary: dict[str, Any] = {"passed": passed, "failed": len(graded) - passed, "total": len(graded),
               "pass_rate": round(passed / len(graded), 4)}
    out.write_text(json.dumps({"expectations": graded,
                               "extra_findings": reply.get("extra_findings", []),
                               "summary": summary}, indent=1))
    return f"{run}: {passed}/{len(graded)}"


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--work", type=pathlib.Path, required=True,
                    help="an empty directory to run the grader in")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--parallel", type=int, default=7)
    ap.add_argument("iteration", type=pathlib.Path)
    ap.add_argument("version", nargs="*", help="versions to grade; default all")
    args = ap.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    jobs: list[tuple[pathlib.Path, str]] = []
    for ev in sorted(args.iteration.glob("eval-*")):
        case = ev.name.removeprefix("eval-")
        if case not in RUBRICS["cases"]:
            continue
        for vdir in sorted(p for p in ev.iterdir() if p.is_dir()):
            if args.version and vdir.name not in args.version:
                continue
            # metrics.json marks a finished run (run_bench.py writes it last).
            jobs += [(run, case) for run in sorted(vdir.glob("run-*"))
                     if (run / "metrics.json").exists()]
    with cf.ThreadPoolExecutor(args.parallel) as ex:
        work: pathlib.Path = args.work.resolve()
        model: str = args.model
        futures = [ex.submit(grade, run, case, work, model) for run, case in jobs]
        for f in futures:
            print(f.result(), flush=True)


if __name__ == "__main__":
    main()

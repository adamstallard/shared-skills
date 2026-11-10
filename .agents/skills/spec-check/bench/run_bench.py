"""Run one version of spec-check against the benchmark cases with `claude -p`.

    python3 -I run_bench.py --cases <built-cases> --work <scratch> \\
        --iteration <iteration-dir> --version <name> --skill <skill-dir> \\
        [--reps 2] [--parallel 7] [--model claude-opus-5-5] [--timeout 3600] \\
        [case ...]

For each case and rep, copies <built-cases>/<case> (from build_cases.py) to
<scratch>/<version>/<case>/run-<k>, installs <skill-dir> there as the project
skill .claude/skills/spec-check, and runs the task prompt from rubrics.json
with only project settings, so no user skill, hook or plugin joins in. Keep
<scratch> outside ~/.claude/: Claude Code refuses edits there as a sensitive
path, and the agent could not fix anything.

Each run writes to <iteration-dir>/eval-<case>/<version>/run-<k>/:
transcript.jsonl, report.md (the final reply), changes.patch (what the agent
changed, against the case's staged tree), timing.json, and metrics.json. It
writes metrics.json last, and a run that has one is finished: the next call
skips it, so rerunning a command resumes its batch.

A run that fails writes failed.txt, saying why, and no metrics.json, and the
next call retries it. Files it wrote before failing may stay beside failed.txt.
A run fails when `claude -p` exits with an error, reports one, or passes
--timeout seconds, or when anything else in the run raises.

Each `claude -p` shares run_bench's process group, so a terminal's Ctrl-C
or hangup reaches it directly, and claude stops its own tools. On Ctrl-C,
run_bench starts no more runs from the queue and waits for the running ones
to end; they end failed, except one whose `claude -p` had already finished,
which is kept. A run already taken from the queue but still copying its
files has no `claude -p` for the Ctrl-C to reach: it starts one afterwards,
which runs at full cost. That happens in a batch's first seconds, and when a
run starts in a slot another run freed. A second Ctrl-C a few seconds later
stops it. A SIGTERM sent to run_bench's process alone stops only
run_bench, and its `claude -p` processes keep running.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import pathlib
import shutil
import subprocess
import sys
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
RUBRICS: dict[str, Any] = json.loads((HERE / "rubrics.json").read_text())
TOOLS = "Bash,Read,Edit,Write,Glob,Grep,Agent,Task,Skill"
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
              "cache_creation_input_tokens")
MODEL_USAGE_KEYS = ("inputTokens", "outputTokens", "cacheReadInputTokens",
                    "cacheCreationInputTokens")

STOP_GRACE = 30  # seconds a timed-out claude gets to stop its tools before SIGKILL


def stop(proc: subprocess.Popen[bytes]) -> None:
    """Stop a timed-out claude with SIGTERM, which makes it stop its own tools.
    A claude still running after STOP_GRACE gets SIGKILL, which reaches claude
    alone: each Bash tool runs in a process group of its own, so its tools
    keep running."""
    proc.terminate()
    try:
        proc.wait(timeout=STOP_GRACE)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def git(repo: pathlib.Path, *args: str) -> str:
    # A session of its own, so a Ctrl-C meant for the batch cannot kill the git
    # that collects a finished run's changes. A byte that is not UTF-8 in the
    # agent's edits becomes U+FFFD in changes.patch instead of failing the run.
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, encoding="utf-8", errors="replace",
                          start_new_session=True).stdout


def read_transcript(path: pathlib.Path) -> tuple[dict[str, Any], dict[str, int], int, bool]:
    """The result message, tokens per agent ("main" or the Agent call's id),
    the number of Agent calls the main loop made, and whether it loaded a
    skill. stream-json repeats an assistant message once per content block,
    so usage is counted once per message id."""
    result: dict[str, Any] = {}
    usage: dict[tuple[str, str], int] = {}
    agents = 0
    skill_used = False
    for line in path.read_text().splitlines():
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        if m.get("type") == "result":
            result = m
        if m.get("type") != "assistant":
            continue
        msg = m.get("message", {})
        who = m.get("parent_tool_use_id") or "main"
        u = msg.get("usage", {})
        usage[(who, msg.get("id", ""))] = sum(int(u.get(k) or 0) for k in USAGE_KEYS)
        for c in msg.get("content", []):
            if c.get("type") != "tool_use":
                continue
            if c.get("name") == "Skill":
                skill_used = True
            if c.get("name") in ("Agent", "Task") and who == "main":
                agents += 1
    by_agent: dict[str, int] = {}
    for (who, _), n in usage.items():
        by_agent[who] = by_agent.get(who, 0) + n
    return result, by_agent, agents, skill_used


def one(args: argparse.Namespace, case: str, k: int) -> str:
    run_dir: pathlib.Path = args.iteration / f"eval-{case}" / args.version / f"run-{k}"
    if (run_dir / "metrics.json").exists():
        return f"{run_dir}: done already"
    try:
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True)
        return attempt(args, case, k, run_dir)
    except Exception as e:  # noqa: BLE001 - any failure is recorded, so the summary lists it
        return failed(run_dir, f"{type(e).__name__}: {e}")


def attempt(args: argparse.Namespace, case: str, k: int, run_dir: pathlib.Path) -> str:
    repo: pathlib.Path = args.work / args.version / case / f"run-{k}"
    if repo.exists():
        shutil.rmtree(repo)
    shutil.copytree(args.cases / case, repo, symlinks=True)
    # bench/ stays out: rubrics.json holds the answers.
    shutil.copytree(args.skill, repo / ".claude" / "skills" / "spec-check",
                    ignore=shutil.ignore_patterns("__pycache__", "bench"))
    (run_dir / "repo-path.txt").write_text(f"{repo}\n")
    start_tree = git(repo, "write-tree").strip()
    cmd = ["claude", "-p", RUBRICS["prompt"], "--setting-sources", "project",
           "--output-format", "stream-json", "--verbose", "--no-session-persistence",
           "--model", args.model, "--permission-mode", "acceptEdits", "--allowedTools", TOOLS]
    t0 = time.time()
    timed_out = False
    with open(run_dir / "transcript.jsonl", "w") as out, open(run_dir / "stderr.txt", "w") as err:
        proc = subprocess.Popen(cmd, cwd=repo, stdout=out, stderr=err, stdin=subprocess.DEVNULL)
        try:
            rc = proc.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            stop(proc)
            rc = proc.wait()
    wall = round(time.time() - t0, 1)
    result, by_agent, agents, skill_used = read_transcript(run_dir / "transcript.jsonl")
    if timed_out or rc != 0 or not result or result.get("is_error"):
        why = (f"timed out after {args.timeout}s" if timed_out else
               f"rc={rc}, is_error={result.get('is_error')}, "
               f"result message {'present' if result else 'missing'}")
        return failed(run_dir, why)
    try:
        git(repo, "add", "-A")
        patch = git(repo, "diff", start_tree, git(repo, "write-tree").strip())
        log = git(repo, "log", "--oneline")
    except subprocess.CalledProcessError as e:
        return failed(run_dir, f"git could not read the run repository: {e.stderr.strip()}")
    (run_dir / "changes.patch").write_text(
        f"# git log --oneline\n{log}\n# diff from the case's staged tree\n{patch}")
    model_usage: dict[str, dict[str, Any]] = result.get("modelUsage", {})
    # modelUsage covers the main loop and every subagent.
    total = sum(int(v.get(k) or 0) for v in model_usage.values() for k in MODEL_USAGE_KEYS)
    metrics = {
        "rc": rc, "wall_seconds": wall, "duration_ms": result.get("duration_ms"),
        "num_turns": result.get("num_turns"), "cost_usd": result.get("total_cost_usd"),
        "total_tokens": total, "model_usage": model_usage,
        "transcript_tokens_by_agent": by_agent, "subagent_stats": result.get("subagent_stats"),
        "agent_calls": agents, "skill_used": skill_used, "is_error": result.get("is_error"),
    }
    (run_dir / "timing.json").write_text(json.dumps({
        "total_tokens": total, "duration_ms": result.get("duration_ms"),
        "total_duration_seconds": wall}, indent=1))
    (run_dir / "report.md").write_text(result.get("result", "(no result)"))
    # metrics.json goes last: it marks the run finished, for resume, grading and the summary.
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=1))
    return f"{run_dir}: rc={rc} {round(wall)}s {total} tokens agents={agents} skill={skill_used}"


def failed(run_dir: pathlib.Path, why: str) -> str:
    """Record a failed run. It gets no metrics.json, so the next call retries
    it and grade.py and summarize.py leave it out of the results."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "failed.txt").write_text(f"{why}; see stderr.txt and transcript.jsonl\n")
    return f"{run_dir}: FAILED ({why})"


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--cases", type=pathlib.Path, required=True,
                    help="the directory build_cases.py wrote")
    ap.add_argument("--work", type=pathlib.Path, required=True,
                    help="scratch directory for the run repositories, outside ~/.claude/")
    ap.add_argument("--iteration", type=pathlib.Path, required=True)
    ap.add_argument("--version", required=True, help="a name for this skill version")
    ap.add_argument("--skill", type=pathlib.Path, required=True,
                    help="the spec-check directory to test")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--parallel", type=int, default=7)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--timeout", type=int, default=3600, help="seconds allowed per run")
    ap.add_argument("case", nargs="*", help="cases to run; default every case in rubrics.json")
    args = ap.parse_args()
    for name in ("cases", "work", "iteration", "skill"):
        setattr(args, name, getattr(args, name).resolve())
    if args.work == pathlib.Path.home() / ".claude" or (pathlib.Path.home() / ".claude") in args.work.parents:
        ap.error("--work must be outside ~/.claude/, where Claude Code refuses edits")
    cases: list[str] = list(dict.fromkeys(args.case)) or sorted(RUBRICS["cases"])
    unknown = [c for c in cases if c not in RUBRICS["cases"]]
    if unknown:
        ap.error(f"no such case: {', '.join(unknown)}")
    jobs = [(c, k) for k in range(1, args.reps + 1) for c in cases]
    ex = cf.ThreadPoolExecutor(args.parallel)
    try:
        futures = [ex.submit(one, args, c, k) for c, k in jobs]
        for f in cf.as_completed(futures):
            print(f.result(), flush=True)
    except KeyboardInterrupt:
        # The same Ctrl-C reached every running claude; start no more runs.
        ex.shutdown(wait=True, cancel_futures=True)
        sys.exit("run_bench: stopped; rerun the command to retry the runs that did not finish")
    ex.shutdown()


if __name__ == "__main__":
    main()

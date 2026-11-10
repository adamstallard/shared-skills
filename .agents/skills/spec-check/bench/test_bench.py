"""Tests of the benchmark harness, with a fake `claude` on PATH.

    python3 -I test_bench.py
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

HERE = pathlib.Path(__file__).resolve().parent

# A stand-in for `claude -p`. FAKE_MODE=fail exits 1 with no output.
# FAKE_MODE=hang starts a tool process that writes LATE.txt after 2 s, in a
# session of its own, the way real Claude Code starts each Bash tool; then it
# sleeps. Like real Claude Code, it stops that process when it gets SIGTERM,
# SIGINT or SIGHUP, and SIGKILL gives it no chance to. FAKE_MODE=latin1 edits
# the repository with a byte that is not UTF-8, then finishes. As the grader
# (called with --tools) it answers every expectation in reverse order,
# passing only the "MUST:" ones. Otherwise it prints a short stream-json run.
FAKE_CLAUDE = textwrap.dedent('''\
    #!/usr/bin/env python3
    import json, os, sys
    args = sys.argv[1:]
    if os.environ.get("FAKE_MODE") == "fail":
        sys.exit(1)
    if os.environ.get("FAKE_MODE") == "hang":
        import signal, subprocess, time
        tool = subprocess.Popen(["/bin/sh", "-c", "sleep 2; echo late > LATE.txt"],
                                start_new_session=True)
        def stop(signum, frame):
            tool.kill()
            sys.exit(128 + signum)
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, stop)
        time.sleep(30)
    if os.environ.get("FAKE_MODE") == "latin1":
        open("notes.md", "wb").write(b"caf\\xe9\\n")
    if "--tools" in args:
        prompt = args[args.index("-p") + 1]
        body = prompt.split("Expectations:\\n", 1)[1].split("\\n\\n", 1)[0]
        texts = [line[2:] for line in body.splitlines() if line.startswith("- ")]
        answers = [{"text": t, "passed": t.startswith("MUST:"), "evidence": "fake"}
                   for t in reversed(texts)]
        print(json.dumps({"result": json.dumps({"expectations": answers})}))
        sys.exit(0)
    usage = {"input_tokens": 1, "output_tokens": 2, "cache_read_input_tokens": 3,
             "cache_creation_input_tokens": 4}
    print(json.dumps({"type": "assistant", "message": {"id": "m1", "usage": usage,
          "content": [{"type": "tool_use", "name": "Skill", "input": {}}]}}))
    print(json.dumps({"type": "result", "result": "fake report", "duration_ms": 5,
          "num_turns": 1, "total_cost_usd": 0.01, "is_error": False,
          "modelUsage": {"m": {"inputTokens": 1, "outputTokens": 2,
                               "cacheReadInputTokens": 3, "cacheCreationInputTokens": 4}}}))
    ''')


class Harness(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        bindir = self.tmp / "bin"
        bindir.mkdir()
        fake = bindir / "claude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(0o755)
        # A git that takes 3 s over `git add` when FAKE_GIT_SLOW is set, so a
        # signal can land while run_bench reads a finished run's repository.
        real_git = shutil.which("git")
        slow_git = bindir / "git"
        slow_git.write_text(f'#!/bin/sh\n[ -n "$FAKE_GIT_SLOW" ] && [ "$3" = add ] && sleep 3\n'
                            f'exec {real_git} "$@"\n')
        slow_git.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
        self.cases = self.tmp / "cases"
        self.iteration = self.tmp / "results" / "it"
        self.py(HERE / "build_cases.py", str(self.cases))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def py(self, script: pathlib.Path, *args: str, env: dict[str, str] | None = None) -> str:
        r = subprocess.run([sys.executable, "-I", str(script), *args], capture_output=True,
                           text=True, env=env or self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def run_bench(self, *cases: str, env: dict[str, str] | None = None,
                  timeout: str = "3600") -> str:
        return self.py(HERE / "run_bench.py", "--timeout", timeout, "--cases", str(self.cases),
                       "--work", str(self.tmp / "runs"), "--iteration", str(self.iteration),
                       "--version", "v", "--skill", str(HERE.parent), "--reps", "1", *cases,
                       env=env)

    def test_a_failed_run_is_retried_on_resume(self) -> None:
        self.run_bench("clean", env={**self.env, "FAKE_MODE": "fail"})
        run = self.iteration / "eval-clean/v/run-1"
        self.assertTrue((run / "failed.txt").exists())
        self.assertFalse((run / "report.md").exists())
        out = self.run_bench("clean")
        self.assertNotIn("done already", out)
        metrics = json.loads((self.iteration / "eval-clean/v/run-1/metrics.json").read_text())
        self.assertEqual(metrics["rc"], 0)

    def test_a_run_that_leaves_non_utf8_text_is_kept(self) -> None:
        out = self.run_bench("clean", env={**self.env, "FAKE_MODE": "latin1"})
        self.assertTrue((self.iteration / "eval-clean/v/run-1/metrics.json").exists(), out)

    def test_grades_follow_the_graders_text_not_its_order(self) -> None:
        self.run_bench("contradiction")
        self.py(HERE / "grade.py", "--work", str(self.tmp / "grader"), str(self.iteration))
        g = json.loads((self.iteration / "eval-contradiction/v/run-1/grading.json").read_text())
        detect = [e for e in g["expectations"] if e["kind"] == "detect"]
        self.assertEqual(len(detect), 1)
        self.assertTrue(detect[0]["passed"], g["expectations"])

    def test_summary_counts_runs_without_grading(self) -> None:
        self.run_bench("clean", "contradiction")
        self.py(HERE / "grade.py", "--work", str(self.tmp / "grader"), str(self.iteration))
        (self.iteration / "eval-clean/v/run-1/grading.json").unlink()
        out = self.py(HERE / "summarize.py", str(self.iteration))
        self.assertIn("| v | 2 |", out)
        self.assertIn("clean", out.split("not graded", 1)[-1] if "not graded" in out else "")

    def test_grade_skips_a_run_left_without_metrics(self) -> None:
        run = self.iteration / "eval-clean/v/run-1"
        run.mkdir(parents=True)
        (run / "report.md").write_text("partial")
        out = self.py(HERE / "grade.py", "--work", str(self.tmp / "grader"), str(self.iteration))
        self.assertFalse((run / "grading.json").exists(), out)

    def test_summary_lists_failed_runs(self) -> None:
        self.run_bench("contradiction")
        self.run_bench("clean", env={**self.env, "FAKE_MODE": "fail"})
        out = self.py(HERE / "summarize.py", str(self.iteration))
        self.assertIn("eval-clean", out.split("failed", 1)[-1] if "failed" in out else "")

    def test_a_timed_out_run_is_marked_failed_and_its_processes_stopped(self) -> None:
        self.run_bench("clean", env={**self.env, "FAKE_MODE": "hang"}, timeout="1")
        run = self.iteration / "eval-clean/v/run-1"
        self.assertTrue((run / "failed.txt").exists())
        repo = pathlib.Path((run / "repo-path.txt").read_text().strip())
        time.sleep(3)
        self.assertFalse((repo / "LATE.txt").exists())

    def test_a_run_that_cannot_start_is_marked_failed(self) -> None:
        env = {**self.env, "PATH": "/usr/bin:/bin"}  # no claude on it
        self.run_bench("clean", env=env)
        self.assertTrue((self.iteration / "eval-clean/v/run-1/failed.txt").exists())

    def signal_batch(self, sig: int, env: dict[str, str], *cases: str,
                     parallel: str = "7") -> None:
        """Start a batch of `cases`, one run each (only `clean` when none are
        named), in a session of its own, as a terminal runs a job. Then send
        its process group `sig` after 1.5 s, as the terminal does for Ctrl-C
        (SIGINT) or a closed window (SIGHUP)."""
        args = [sys.executable, "-I", str(HERE / "run_bench.py"), "--timeout", "60",
                "--cases", str(self.cases), "--work", str(self.tmp / "runs"),
                "--iteration", str(self.iteration), "--version", "v",
                "--skill", str(HERE.parent), "--reps", "1", "--parallel", parallel,
                *(cases or ("clean",))]
        p = subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        time.sleep(1.5)
        os.killpg(p.pid, sig)
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            self.fail(f"run_bench.py was still running 10 s after signal {sig}")
        finally:
            time.sleep(3)
            repo = self.tmp / "runs" / "v" / "clean" / "run-1"
            self.assertFalse((repo / "LATE.txt").exists(), "a run's process outlived run_bench")

    def test_ctrl_c_stops_the_batch_and_its_runs(self) -> None:
        self.signal_batch(signal.SIGINT, {**self.env, "FAKE_MODE": "hang"})
        self.assertTrue((self.iteration / "eval-clean/v/run-1/failed.txt").exists())

    def test_closing_the_terminal_stops_the_batch_and_its_runs(self) -> None:
        self.signal_batch(signal.SIGHUP, {**self.env, "FAKE_MODE": "hang"})
        self.run_bench("contradiction")
        out = self.py(HERE / "summarize.py", str(self.iteration))
        self.assertIn("eval-clean/v/run-1", out)

    def test_ctrl_c_keeps_a_run_whose_claude_already_finished(self) -> None:
        self.signal_batch(signal.SIGINT, {**self.env, "FAKE_GIT_SLOW": "1"})
        self.assertTrue((self.iteration / "eval-clean/v/run-1/metrics.json").exists())

    def test_a_case_named_twice_runs_once(self) -> None:
        out = self.run_bench("clean", "clean")
        self.assertEqual(out.count("eval-clean/v/run-1"), 1, out)

    def test_ctrl_c_leaves_runs_that_never_started_alone(self) -> None:
        self.run_bench("clean", "contradiction", env={**self.env, "FAKE_MODE": "fail"})
        pending = self.iteration / "eval-contradiction/v/run-1/failed.txt"
        before = pending.read_text()
        self.signal_batch(signal.SIGINT, {**self.env, "FAKE_MODE": "hang"},
                          "clean", "contradiction", parallel="1")
        self.assertEqual(pending.read_text(), before)


if __name__ == "__main__":
    unittest.main()

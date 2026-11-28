"""Tests of the answer launcher, with `claude` never run. The launcher is the
file `answer`, which has no .py to import, so the tests load it by path."""

import contextlib
import importlib.machinery
import io
import importlib.util
import json
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest import mock


def _load() -> ModuleType:
    path = Path(__file__).resolve().parent / "answer"
    loader = importlib.machinery.SourceFileLoader("answer_launcher", str(path))
    spec = importlib.util.spec_from_loader("answer_launcher", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


answer = _load()


class Launcher(unittest.TestCase):
    def launch(self, args: list[str]) -> tuple[int | None, list[Any]]:
        """Runs the launcher on `args`; returns its exit status (None when it
        handed over to claude) and the exec calls it made."""
        calls: list[Any] = []

        def fake_exec(file: str, argv: list[str], env: dict[str, str]) -> None:
            calls.append((file, argv, env))
            raise SystemExit(None)

        def fake_which(_name: str) -> str:
            return "/usr/bin/claude"

        with mock.patch.object(answer.os, "execvpe", fake_exec), mock.patch.object(answer.shutil, "which", fake_which):
            try:
                status = answer.main(args)
            except SystemExit:
                status = None
        return status, calls

    def test_starts_a_restricted_session(self) -> None:
        # @scenario answer-service: The answer launcher starts a restricted session
        for args in ([], ["--resume", "abc-123"]):
            status, calls = self.launch(args)
            self.assertIsNone(status)
            self.assertEqual(len(calls), 1)
            file, argv, env = calls[0]
            self.assertEqual(file, "claude")
            self.assertEqual(argv[:6], ["claude", "--name", "Answers", "--tools", "Read,Grep,Glob", "--strict-mcp-config"])
            self.assertEqual(argv[6:], args)
            self.assertEqual(env["INQUISITOR_ANSWER"], "1")
            self.assertEqual(env["CLAUDE_CODE_NO_FLICKER"], "1")
            # The scenario keeps every enabled plugin on, the answer mod among
            # them: the launcher adds no argument that turns plugins off.
            self.assertFalse(any(a.startswith("--settings") or "plugin" in a for a in argv))

    def test_passes_only_its_listed_arguments(self) -> None:
        # @scenario answer-service: The answer launcher passes only its listed arguments
        for args in (
            ["--resume", "abc-123"], ["-r", "abc-123"], ["--resume"], ["-r"], ["--continue"], ["-c"],
            ["--model", "opus"], ["--debug"], ["--debug=api"], ["--resume=abc-123"], ["--model=opus"],
            ["-cr", "abc-123"], ["-c", "--model", "opus", "--debug=hooks"],
        ):
            status, calls = self.launch(args)
            self.assertIsNone(status, args)
            self.assertEqual(calls[0][1][6:], args)

    def test_refuses_any_other_argument(self) -> None:
        # @scenario answer-service: The answer launcher refuses any other argument
        cases = {
            ("--name", "x"): "--name",
            ("--tools", "Bash"): "--tools",
            ("--mcp-config", "x.json"): "--mcp-config",
            ("--agents", "{}"): "--agents",
            ("--settings", "s.json"): "--settings",
            ("--plugin-dir", "d"): "--plugin-dir",
            ("-cn", "x"): "-n",
            ("a prompt",): "a prompt",
            ("-rabc",): "-rabc",
            ("--model",): "--model",
            ("-c", "x"): "x",
            ("--resume", "id", "--tools=Bash"): "--tools=Bash",
            ("--model", "--", "--tools", "Bash"): "--model",
            ("-",): "-",
            ("--continue", "--settings=s.json"): "--settings=s.json",
            ("--debug", "--plugin-dir=d"): "--plugin-dir=d",
            ("--resume", "--tools=Bash"): "--tools=Bash",
        }
        for args, named in cases.items():
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                status, calls = self.launch(list(args))
            self.assertEqual(status, 2, args)
            self.assertEqual(calls, [], args)
            self.assertIn(f"answer: {named} is not allowed", err.getvalue(), args)

    def test_without_claude_on_path_it_says_so_and_starts_nothing(self) -> None:
        # @scenario answer-service: The answer launcher starts a restricted session
        # No scenario covers a missing claude; this is the start that scenario
        # needs, failing plainly.
        calls: list[Any] = []
        err = io.StringIO()
        with mock.patch.object(answer.os, "execvpe", lambda *a: calls.append(a)), mock.patch.object(answer.shutil, "which", lambda _n: None), contextlib.redirect_stderr(err):
            status = answer.main([])
        self.assertEqual(status, 127)
        self.assertEqual(calls, [])
        self.assertIn("claude is not on PATH", err.getvalue())

class FakeCoreFixture(unittest.TestCase):
    def test_the_mod_tests_run_on_the_cores_examples(self) -> None:
        # @scenario answer-service: Running answer opens the answer service
        # The mod's tests of this scenario run against a fake core answering
        # from tests/core-examples.ts, a copy of
        # scripts/fixtures/service/examples.json; this keeps the copy current.
        here = Path(__file__).resolve().parent
        fixture = json.loads((here.parent / "scripts" / "fixtures" / "service" / "examples.json").read_text())
        text = (here / "tests" / "core-examples.ts").read_text()
        start = text.index("export const EXAMPLES = ") + len("export const EXAMPLES = ")
        end = text.rindex(" as const")
        self.assertEqual(json.loads(text[start:end]), fixture, "tests/core-examples.ts differs from examples.json: copy the fixture into it again")


if __name__ == "__main__":
    unittest.main()

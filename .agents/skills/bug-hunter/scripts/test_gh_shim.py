#!/usr/bin/env python3
"""Tests for the gh shim that mutation subagents put first on PATH.

It needs only the standard library. Run it with:

    python3 test_gh_shim.py

Each test runs the shim the way a project's test suite would reach it: as
`gh`, found on PATH ahead of any real gh.
"""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SHIM_DIR = HERE / "gh-shim"


class GhShimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="bh-gh-shim-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # A stand-in for the real gh, later on PATH than the shim. If the shim
        # ever lets a call through, this one leaves a marker file.
        self.real = self.tmp / "real-bin"
        self.real.mkdir()
        self.marker = self.tmp / "real-gh-ran"
        fake = self.real / "gh"
        fake.write_text(f"#!/bin/sh\ntouch '{self.marker}'\necho real\n")
        fake.chmod(0o755)

    def gh(self, *args, log=None):
        env = {k: v for k, v in os.environ.items() if k != "GH_SHIM_LOG"}
        env["PATH"] = f"{SHIM_DIR}{os.pathsep}{self.real}{os.pathsep}{env.get('PATH', '')}"
        if log is not None:
            env["GH_SHIM_LOG"] = str(log)
        return subprocess.run(["gh", *args], capture_output=True, text=True,
                              env=env, cwd=self.tmp)

    def test_the_shim_is_executable(self):
        self.assertTrue(os.access(SHIM_DIR / "gh", os.X_OK))

    def test_a_call_is_refused_and_never_reaches_the_real_gh(self):
        result = self.gh("api", "repos/o/r/issues", "-f", "title=x")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("gh-shim: refused: gh api repos/o/r/issues -f title=x",
                      result.stderr)
        self.assertFalse(self.marker.exists())

    def test_each_call_is_appended_to_the_log(self):
        log = self.tmp / "gh-calls.log"
        self.gh("pr", "view", "1", log=log)
        self.gh("issue", "list", log=log)
        self.assertEqual(log.read_text(), "gh pr view 1\ngh issue list\n")

    def test_a_multi_line_argument_is_still_one_log_line(self):
        # A PR or issue body is usually several lines, and a mutation
        # subagent's report counts refused calls by counting the log's lines.
        log = self.tmp / "gh-calls.log"
        self.gh("pr", "create", "--body", "Summary\n\n- one\n- two", log=log)
        self.gh("issue", "list", log=log)
        self.assertEqual(len(log.read_text().splitlines()), 2)

    def test_a_carriage_return_is_logged_as_a_space(self):
        log = self.tmp / "gh-calls.log"
        self.gh("api", "a\rb", log=log)
        self.assertEqual(log.read_bytes(), b"gh api a b\n")

    def test_a_byte_that_is_not_utf8_is_logged_with_the_rest_of_the_call(self):
        log = self.tmp / "gh-calls.log"
        env = {k: v for k, v in os.environ.items() if k != "GH_SHIM_LOG"}
        env.update(PATH=f"{SHIM_DIR}{os.pathsep}{self.real}{os.pathsep}{env.get('PATH', '')}",
                   GH_SHIM_LOG=str(log), LC_ALL="en_US.UTF-8")
        subprocess.run([b"gh", b"api", b"a\xffb\nc", b"x"], capture_output=True,
                       env=env, cwd=self.tmp)
        self.assertEqual(log.read_bytes(), b"gh api a\xffb c x\n")

    def test_without_a_log_the_call_is_still_refused(self):
        result = self.gh("auth", "status")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(list(self.tmp.glob("*.log")), [])

    def test_an_unwritable_log_still_refuses(self):
        result = self.gh("pr", "list", log=self.tmp / "missing-dir" / "gh.log")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for the caller-commits result block.

Standard library only:

    python3 test_caller_result.py

Covers bug-hunter's caller-result.sh and the shared library script it calls,
../../../lib/commit-trailer/result-block.sh, which defines the format. Each
test works in a throwaway repo in a temp directory.
"""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
WRAPPER = HERE / "caller-result.sh"
LIB = HERE.parent.parent.parent / "lib" / "commit-trailer" / "result-block.sh"
REFERENCE = HERE.parent / "reference.md"

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class ResultBlockTests(unittest.TestCase):
    """The library script: the format itself."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="bh-block-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def block(self, *args, stdin=None, shell="sh"):
        return subprocess.run([shell, str(LIB), *args], input=stdin,
                              capture_output=True, text=True, cwd=self.tmp)

    def decisions(self, text):
        path = self.tmp / "decisions.txt"
        path.write_text(text)
        return str(path)

    def test_the_block_is_exact(self):
        # Blank lines are skipped, a last line with no newline is kept, and
        # the script numbers each decision.
        path = self.decisions("refund state — 1 fix it now · 2 write it down · 3 skip\n\n  second\r\nthird")
        result = self.block("prose", "--decisions", path, "--",
                            "Prose: 1 finding fixed", "  Prose-Sig: 0123abcd4567 ")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, (
            "=== prose result ===\n"
            "Prose: 1 finding fixed\n"
            "Prose-Sig: 0123abcd4567\n"
            "=== prose open decisions: 3 ===\n"
            "① refund state — 1 fix it now · 2 write it down · 3 skip\n"
            "② second\n"
            "③ third\n"
            "=== end prose ===\n"))

    def test_zero_decisions_puts_the_end_marker_next(self):
        for args in ((), ("--decisions", self.decisions("\n\n"))):
            with self.subTest(args=args):
                result = self.block("demo", *args, "--", "Demo: done")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout,
                                 "=== demo result ===\nDemo: done\n"
                                 "=== demo open decisions: 0 ===\n=== end demo ===\n")

    def test_decisions_come_from_stdin_with_a_dash(self):
        result = self.block("demo", "--decisions", "-", "--", "Demo: done", stdin="a\nb\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("=== demo open decisions: 2 ===\n① a\n② b\n", result.stdout)

    def test_past_twenty_the_number_is_in_brackets(self):
        path = self.decisions("".join(f"d{i}\n" for i in range(1, 22)))
        result = self.block("demo", "--decisions", path, "--", "Demo: done")
        self.assertIn("⑳ d20\n(21) d21\n", result.stdout)

    def test_malformed_trailer_lines_are_refused(self):
        for line in ("Demo done", "Demo:", "Demo:   ", "2x: done", "De mo: done",
                     ": done", "Demo: a\nb", ""):
            with self.subTest(line=line):
                result = self.block("demo", "--", line)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_a_bad_skill_name_is_refused(self):
        for skill in ("", "  ", "2x", "bug hunter", "-x"):
            with self.subTest(skill=skill):
                result = self.block(skill, "--", "Demo: done")
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_a_missing_argument_is_refused_not_absorbed(self):
        # Each is a call where an unquoted empty variable vanished.
        for args in (("demo", "--"),                         # no trailer line
                     ("demo", "Demo: done"),                 # no `--`
                     ("demo", "--decisions", "--", "Demo: done"),
                     ("demo", "--decisions", "--", "--", "Demo: done"),
                     ("demo", "--decisions", "", "--", "Demo: done"),
                     ("demo", "--decisions"),
                     ("demo",)):
            with self.subTest(args=args):
                result = self.block(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
        named = self.block("demo", "--decisions", "--", "Demo: done")
        self.assertIn("--decisions is missing its file", named.stderr)

    def test_a_missing_decisions_file_is_an_error_not_zero(self):
        # Read as empty, it would tell the caller nothing is open.
        for path in (str(self.tmp / "nope.txt"), str(self.tmp)):
            with self.subTest(path=path):
                result = self.block("demo", "--decisions", path, "--", "Demo: done")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("missing or unreadable", result.stderr)

    def test_a_decision_shaped_like_a_marker_is_refused(self):
        path = self.decisions("fine\n=== end demo ===\n")
        result = self.block("demo", "--decisions", path, "--", "Demo: done")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    @unittest.skipUnless(shutil.which("dash"), "needs dash")
    def test_the_same_block_under_dash(self):
        path = self.decisions("one\ntwo")
        args = ("demo", "--decisions", path, "--", "Demo: done", "Demo-Tree: abc")
        under_sh = self.block(*args)
        under_dash = self.block(*args, shell="dash")
        self.assertEqual(under_dash.returncode, 0, under_dash.stderr)
        self.assertEqual(under_dash.stdout, under_sh.stdout)
        refused = self.block("demo", "--decisions", str(self.tmp / "nope"), "--",
                             "Demo: done", shell="dash")
        self.assertEqual((refused.returncode, refused.stdout), (1, ""))


class CallerResultTests(unittest.TestCase):
    """bug-hunter's wrapper: mints the binding, then prints the block."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="bh-caller-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def result(self, *args, script=WRAPPER, shell="sh", stdin=None, env=None):
        return subprocess.run([shell, str(script), *args], input=stdin, cwd=self.repo,
                              capture_output=True, text=True, env=env)

    def test_the_tree_line_is_git_write_tree(self):
        (self.repo / "f.py").write_text("x = 1\n")
        self.git("add", "f.py")
        result = self.result("1 iteration, 1 bug fixed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[:3], [
            "=== bug-hunter result ===",
            "Bug-hunter: 1 iteration, 1 bug fixed",
            f"Bug-hunter-Tree: {self.git('write-tree')}",
        ])

    def test_reference_md_examples_are_what_the_wrapper_prints(self):
        # A fresh repo stages the empty tree, the hash in reference.md's
        # example. Without this test, the documented block and the printed
        # one could drift apart.
        clean = self.result("2 iterations, 3 bugs fixed")
        skip = self.result("skipped at triage (docs only, no executable code)")
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertIn(f"Bug-hunter-Tree: {EMPTY_TREE}", clean.stdout)
        self.assertIn(clean.stdout + "\n" + skip.stdout, REFERENCE.read_text())

    def test_a_skip_has_no_tree_line_and_mints_nothing(self):
        # Outside a repository a mint would fail, so success shows none ran.
        outside = self.tmp / "not-a-repo"
        outside.mkdir()
        for value in ("skipped at triage (docs only)", "Skipped — tests only"):
            with self.subTest(value=value):
                result = subprocess.run(["sh", str(WRAPPER), value], cwd=outside,
                                        capture_output=True, text=True,
                                        env={**os.environ, "GIT_CEILING_DIRECTORIES": str(self.tmp)})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout,
                                 f"=== bug-hunter result ===\nBug-hunter: {value}\n"
                                 "=== bug-hunter open decisions: 0 ===\n=== end bug-hunter ===\n")

    def test_decisions_pass_through_from_a_file_or_stdin(self):
        path = self.tmp / "d.txt"
        path.write_text("refund state is rebuilt on every read — 1 fix it now · 2 write it down · 3 skip\n")
        from_file = self.result("1 iteration, 1 bug fixed", "--decisions", str(path))
        from_stdin = self.result("1 iteration, 1 bug fixed", "--decisions", "-",
                                 stdin=path.read_text())
        self.assertEqual(from_file.returncode, 0, from_file.stderr)
        self.assertEqual(from_file.stdout, from_stdin.stdout)
        self.assertTrue(from_file.stdout.endswith(
            "=== bug-hunter open decisions: 1 ===\n"
            "① refund state is rebuilt on every read — 1 fix it now · 2 write it down · 3 skip\n"
            "=== end bug-hunter ===\n"))

    def test_bad_arguments_are_refused_before_the_mint(self):
        # Each is refused with exit 2 and nothing on stdout. An unquoted
        # value that split, or vanished, is among them.
        for args in ((), ("",), ("  ",), ("a\nb",), ("1", "iteration,", "fixed"),
                     ("--decisions", "d.txt"), ("--decisions",), ("--",), ("x", "--decisions"),
                     ("x", "--other", "d.txt"), ("x", "y", "z", "w")):
            with self.subTest(args=args):
                result = self.result(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_a_failed_mint_prints_no_block(self):
        outside = self.tmp / "not-a-repo"
        outside.mkdir()
        result = subprocess.run(["sh", str(WRAPPER), "1 iteration, 0 bugs found"], cwd=outside,
                                capture_output=True, text=True,
                                env={**os.environ, "GIT_CEILING_DIRECTORIES": str(self.tmp)})
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("mint-trailer.sh failed", result.stderr)

    def copy_with_stub_mint(self, stub):
        """A copy of the skill and the library, laid out as in the clone, with
        mint-trailer.sh replaced."""
        root = self.tmp / "clone" / ".agents"
        shutil.copytree(HERE, root / "skills" / "bug-hunter" / "scripts")
        shutil.copytree(LIB.parent, root / "lib" / "commit-trailer")
        mint = root / "skills" / "bug-hunter" / "scripts" / "mint-trailer.sh"
        mint.write_text(stub)
        return root / "skills" / "bug-hunter" / "scripts" / "caller-result.sh"

    def test_a_noisy_mint_prints_no_block(self):
        # A zero exit with a second line is still refused: grep alone would
        # accept it, because one of the lines matches.
        stub = f"#!/bin/sh\necho 'trace: noise'\necho 'Bug-hunter-Tree: {EMPTY_TREE}'\n"
        for text in (stub, "#!/bin/sh\necho 'Bug-hunter-Tree: nothex'\n"):
            with self.subTest(text=text):
                shutil.rmtree(self.tmp / "clone", ignore_errors=True)
                result = self.result("1 iteration, 0 bugs found",
                                     script=self.copy_with_stub_mint(text))
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")

    def test_a_missing_library_is_reported(self):
        copied = self.tmp / "bug-hunter" / "scripts"
        shutil.copytree(HERE, copied)
        result = self.result("skipped at triage (x)", script=copied / "caller-result.sh")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("library is missing", result.stderr)

    def test_it_works_through_a_symlinked_skill_directory(self):
        installed = self.tmp / "home" / ".agents" / "skills" / "bug-hunter"
        installed.parent.mkdir(parents=True)
        installed.symlink_to(HERE.parent, target_is_directory=True)
        (self.repo / "f.py").write_text("x = 1\n")
        self.git("add", "f.py")
        result = self.result("1 iteration, 0 bugs found",
                             script=installed / "scripts" / "caller-result.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Bug-hunter-Tree: {self.git('write-tree')}\n", result.stdout)

    @unittest.skipUnless(shutil.which("dash"), "needs dash")
    def test_it_runs_under_dash(self):
        # The wrapper runs the library with `sh`; the library's own dash run
        # is in ResultBlockTests.
        result = self.result("1 iteration, 0 bugs found", shell="dash")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Bug-hunter-Tree: {EMPTY_TREE}\n", result.stdout)
        refused = self.result("", shell="dash")
        self.assertEqual((refused.returncode, refused.stdout), (2, ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)

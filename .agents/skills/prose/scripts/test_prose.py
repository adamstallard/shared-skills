#!/usr/bin/env python3
"""Tests for prose.py, its commit hook and its posting hook.

Standard library only:

    python3 test_prose.py

The trailer tests commit for real: a message has to hash the same when
`prose check` reads the text passed in and when `verify-commit` reads what git
stored, and only git can say what it stores.
"""

import contextlib
import io
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "prose.py"
COMMIT_HOOK = HERE / "check-commit-trailer.sh"
HOOK_REPORT = HERE / "hook-report.sh"
POST_HOOK = HERE / "check-post.sh"
VERIFY_STAGED = HERE / "verify-staged.sh"
LIBRARY = HERE.parent.parent.parent / "lib" / "commit-trailer"
COMMIT_SCRIPT = LIBRARY / "commit-with-trailers.sh"
BUG_HUNTER_MINT = HERE.parent.parent / "bug-hunter" / "scripts" / "mint-trailer.sh"
TRAILER = r"^Prose: ✓ [0-9a-f]{12}:[0-9a-f]{12}$"
GATE = HERE / "require-first-call.sh"

# Pass tokens and session marks go to a throwaway state directory, never the
# user's, and no test inherits the session of the agent running it.
STATE = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = STATE
os.environ.pop("CLAUDE_CODE_SESSION_ID", None)

# Compiled from source rather than imported, so a stale .pyc can never stand
# in for the code under test (see test_comment_scan.py).
prose = types.ModuleType("prose_under_test")
prose.__file__ = str(SCRIPT)
exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), prose.__dict__)


# Reader goals for every listed file, which Repo.prose adds to a check.
ALL_FILES = ["--goals-for", "**", "read it"]


def block_trailer(stdout):
    """The trailer line in the result block that ends stdout; fails unless
    stdout ends with exactly that block, holding one trailer and nothing open."""
    lines = stdout.split("\n")
    if len(lines) < 5 or lines[-1] != "" or lines[-5] != "=== prose result ===" \
            or lines[-3:-1] != ["=== prose open decisions: 0 ===", "=== end prose ==="]:
        raise AssertionError(f"stdout does not end with prose's result block:\n{stdout[-400:]}")
    return lines[-4]


def pass_token(output):
    """The token a first call printed."""
    found = re.search(r"^Pass token: ([0-9a-f]{16})\.", output, re.M)
    if not found:
        raise AssertionError(f"no pass token in:\n{output[-600:]}")
    return found.group(1)


def run(args, cwd=None, stdin=None, env=None):
    return subprocess.run(
        args, cwd=cwd, input=stdin, capture_output=True, text=True, check=False, env=env,
    )


class Repo:
    """A throwaway repository."""

    def __init__(self):
        self.path = pathlib.Path(tempfile.mkdtemp())
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "T")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args, stdin=None):
        result = run(["git"] + list(args), cwd=self.path, stdin=stdin)
        if result.returncode != 0:
            raise AssertionError(f"git {args} failed: {result.stderr}")
        return result.stdout

    def write(self, name, text):
        target = self.path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
        self.git("add", name)

    def prose(self, *args, stdin=None, file_goals=True):
        """prose.py in this repository. A check that names no per-file goals
        gets ALL_FILES, so a test about something else is not refused for a
        doc without goals; file_goals=False leaves them out."""
        args = list(args)
        if file_goals and args[:1] == ["check"] \
                and not {"--goals-for", "--goals-file"} & set(args):
            args += ALL_FILES
        return run([sys.executable, str(SCRIPT)] + args, cwd=self.path, stdin=stdin)

    def two_calls(self, *args, stdin=None, file_goals=True):
        """The pass as SKILL.md runs it: the first call, then, when it issued a
        pass token, the signing call with that token. The signing call's
        result, or the first call's when that one was refused."""
        first = self.prose(*args, stdin=stdin, file_goals=file_goals)
        if first.returncode != 4:
            return first
        return self.prose(*args, "--pass", pass_token(first.stdout), stdin=stdin,
                          file_goals=file_goals)

    def trailers(self, message, *extra):
        """The one trailer line in the result block the signing call prints
        for this message, which is all it prints."""
        (self.path / ".msg").write_bytes(message.encode("utf-8"))
        result = self.two_calls("check", "-F", ".msg", "--goals", "review it", *extra)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        trailer = block_trailer(result.stdout)
        if result.stdout.count("\n") != 4:
            raise AssertionError(f"expected only the result block, got {result.stdout!r}")
        return trailer

    def commit(self, message=None, trailers=(), m_parts=None):
        """Commit, passing each trailer with --trailer. The one place the
        tests make a commit carrying prose's trailer."""
        if isinstance(trailers, str):
            trailers = [trailers]
        args = ["commit", "-q"]
        if m_parts is not None:
            for part in m_parts:
                args += ["-m", part]
        else:
            (self.path / ".msg").write_bytes(message.encode("utf-8"))
            args += ["-F", ".msg"]
        for trailer in trailers:
            args += ["--trailer", trailer]
        self.git(*args)

    def commit_script(self, subject, body, *families):
        """Commit through the shared commit script, as SKILL.md says to."""
        args = ["sh", str(COMMIT_SCRIPT), *families, "--", subject, body]
        return run(args, cwd=self.path)

    def verify(self, sha="HEAD"):
        return self.prose("verify-commit", sha)

    def cleanup(self):
        shutil.rmtree(self.path, ignore_errors=True)


class RulesFile(unittest.TestCase):
    """read_rules parses rules.md by its headings and refuses a broken file."""

    GOOD = ("# Title\n\nPrinciple.\n\n## Scope\n\nS.\n\n## The pass\n\nP.\n\n"
            "## The rules, most important first\n\n"
            + "".join(f"### {n}. Rule {n}\nBody {n}.\n\n" for n in range(1, 9))
            + "## How agents cheat on this pass\n\n- One.\n")

    def read(self, text):
        path = pathlib.Path(tempfile.mkdtemp()) / "rules.md"
        self.addCleanup(shutil.rmtree, path.parent, True)
        path.write_text(text, encoding="utf-8")
        saved = prose.RULES
        prose.RULES = path
        try:
            return prose.read_rules()
        finally:
            prose.RULES = saved

    def test_the_real_rules_file_parses(self):
        preamble, heading, rules, cheats = prose.read_rules()
        self.assertTrue(preamble.startswith("# The prose pass"))
        self.assertIn("## The pass", preamble)
        self.assertEqual([n for n, _, _ in rules], list(range(1, len(rules) + 1)))
        self.assertGreaterEqual(len(rules), prose.RULES_IN_FULL)
        self.assertTrue(cheats.startswith("## How agents cheat"))

    def test_a_good_file_splits_into_its_parts(self):
        preamble, heading, rules, cheats = self.read(self.GOOD)
        self.assertEqual(heading, "## The rules, most important first")
        self.assertEqual([(n, t) for n, t, _ in rules], [(n, f"Rule {n}") for n in range(1, 9)])
        self.assertEqual(rules[0][2], "### 1. Rule 1\nBody 1.")

    def test_a_missing_or_misordered_section_is_refused(self):
        broken = (
            self.GOOD.replace("## Scope\n\nS.\n\n", ""),
            self.GOOD.replace("## How agents cheat on this pass\n\n- One.\n", ""),
            self.GOOD.replace("# Title\n\n", ""),
            self.GOOD.replace("## The pass", "## Passing").replace("## Scope", "## The pass"),
        )
        for text in broken:
            with self.subTest(text[:40]):
                with self.assertRaises(prose.Refused):
                    self.read(text)

    def test_misnumbered_or_too_few_rules_are_refused(self):
        for text in (self.GOOD.replace("### 3. Rule 3", "### 4. Rule 3"),
                     self.GOOD.replace("### 2. Rule 2", "### Rule 2"),
                     self.GOOD.split("### 4.")[0] + "## How agents cheat on this pass\n\n- One.\n"):
            with self.subTest(text[-60:]):
                with self.assertRaises(prose.Refused):
                    self.read(text)

    def read_bytes(self, data):
        path = pathlib.Path(tempfile.mkdtemp()) / "rules.md"
        self.addCleanup(shutil.rmtree, path.parent, True)
        path.write_bytes(data)
        saved = prose.RULES
        prose.RULES = path
        try:
            return prose.read_rules()
        finally:
            prose.RULES = saved

    def printed(self, text):
        path = pathlib.Path(tempfile.mkdtemp()) / "rules.md"
        self.addCleanup(shutil.rmtree, path.parent, True)
        path.write_text(text, encoding="utf-8")
        saved = prose.RULES
        prose.RULES = path
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                prose.print_rules()
        finally:
            prose.RULES = saved
        return out.getvalue()

    def test_a_rules_file_that_is_not_utf8_is_refused(self):
        with self.assertRaises(prose.Refused):
            self.read_bytes(self.GOOD.encode() + b"\n\xe9\n")

    def test_a_fenced_heading_is_content(self):
        text = self.GOOD.replace("- One.\n", "- One.\n\n```\n## Example heading\n# a comment\n```\n- CHEAT-TAIL\n")
        text = text.replace("Body 2.\n", "Body 2.\n```\n## not a section\n# not a heading\n```\n")
        out = self.printed(text)
        for marker in ("CHEAT-TAIL", "## Example heading", "## not a section", "# not a heading"):
            self.assertIn(marker, out)

    def test_text_the_printer_would_drop_is_printed_or_refused(self):
        for text, marker in (
            (self.GOOD.replace("## The rules, most important first\n\n",
                               "## The rules, most important first\n\nINTRO-TEXT\n\n"), "INTRO-TEXT"),
            (self.GOOD.replace("## How agents cheat", "## Extra\n\nEXTRA-SECTION\n\n## How agents cheat"), "EXTRA-SECTION"),
            (self.GOOD + "\n## After\n\nAFTER-CHEATS\n", "AFTER-CHEATS"),
        ):
            with self.subTest(marker):
                try:
                    out = self.printed(text)
                except prose.Refused:
                    continue
                self.assertIn(marker, out)

    def test_a_fenced_hash_line_is_not_a_title(self):
        with self.assertRaises(prose.Refused):
            self.read(self.GOOD.replace("# Title\n", "```\n# not a title\n```\n"))

    def test_an_empty_rule_title_is_refused(self):
        with self.assertRaises(prose.Refused):
            self.read(self.GOOD.replace("### 6. Rule 6", "### 6.  "))

    def test_a_check_with_a_broken_rules_file_prints_no_trailer(self):
        saved = prose.RULES
        path = pathlib.Path(tempfile.mkdtemp()) / "rules.md"
        self.addCleanup(shutil.rmtree, path.parent, True)
        path.write_text("# Title\n\nNo sections.\n", encoding="utf-8")
        prose.RULES = path
        try:
            with self.assertRaises(prose.Refused):
                prose.print_rules()
        finally:
            prose.RULES = saved


class RulesFileThroughTheCommand(unittest.TestCase):
    def test_the_signing_call_still_refuses_a_broken_rules_file(self):
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        (root / "scripts").mkdir()
        for name in ("prose.py", "comment_scan.py"):
            shutil.copy(HERE / name, root / "scripts" / name)
        (root / "rules.md").write_text("# Title\n\nNo sections.\n", encoding="utf-8")
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("a.txt", "a\n")
        token = prose.issue_pass(["g"], "check", "", repo.path)
        result = run([sys.executable, str(root / "scripts" / "prose.py"), "check", "-F", "-",
                      "--pass", token], cwd=repo.path, stdin="Title\n")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertNotIn("Prose:", result.stdout)
        self.assertIn("rules.md", result.stderr)


class Portability(unittest.TestCase):
    """The scripts load on the oldest Python macOS ships."""

    OLD_PYTHONS = ("/Library/Developer/CommandLineTools/usr/bin/python3", "/usr/bin/python3")

    def test_the_scripts_compile_on_an_older_python(self):
        found = [p for p in self.OLD_PYTHONS if pathlib.Path(p).exists()]
        if not found:
            self.skipTest("no older python3 on this machine")
        for script in (SCRIPT, HERE / "comment_scan.py"):
            with self.subTest(script.name):
                result = run([found[0], "-c", "import sys; compile(open(sys.argv[1]).read(), sys.argv[1], 'exec')",
                              str(script)])
                self.assertEqual(result.returncode, 0, result.stderr)


class MessageBody(unittest.TestCase):
    """Which parts of a message the signature covers."""

    def test_trailing_unicode_space_in_a_trailer_line_is_signed(self):
        self.assertNotEqual(prose.message_body("Title\n\nFixes: 1\n"),
                            prose.message_body("Title\n\nFixes: 1\u3000\u00a0\n"))

    def test_a_value_moved_across_an_added_trailer_is_signed(self):
        self.assertNotEqual(
            prose.message_body("Title\n\nFixes:\nSigned-off-by: A <a>\n  see #9\n"),
            prose.message_body("Title\n\nFixes: see #9\nSigned-off-by: A <a>\n"),
        )

    def test_the_trailer_block_is_stripped(self):
        bodies = list(prose.signed_bodies("Subj\n\nBody.\n\nProse: ✓ 0:0\nCo-Authored-By: A <a@b>\n"))
        self.assertEqual(bodies[-1], "Subj\n\nBody.")

    def test_the_title_is_never_a_trailer_block(self):
        self.assertEqual(prose.message_body("Fix: the parser\n"), "Fix: the parser")

    def test_a_wrapped_trailer_continuation_is_part_of_the_block(self):
        # Kept: git never wraps the trailers it adds, so an indented line is someone's text.
        # The search stops there, so the line it continues stays signed too.
        bodies = list(prose.signed_bodies("Subj\n\nBody.\n\nCo-Authored-By: A\n  <a@b>\nProse: checked\n"))
        self.assertEqual(bodies[-1], "Subj\n\nBody.\n\nCo-Authored-By: A\n  <a@b>")
        bodies = list(prose.signed_bodies("Subj\n\nBody.\n\nRefs: one\n  two\nProse: checked\n"))
        self.assertEqual(bodies[-1], "Subj\n\nBody.\n\nRefs: one\n  two")

    def test_whitespace_differences_do_not_change_the_body(self):
        self.assertEqual(
            prose.message_body("\n\nSubj   \n\n\n\nBody.  \r\n\n\n"),
            prose.message_body("Subj\n\nBody.\n"),
        )

    def test_any_trailer_shaped_line_is_stripped_from_the_end(self):
        bodies = list(prose.signed_bodies("Subj\n\nBody.\n\nNote: kept.\nhttps://x.example/a\nSigned-off-by: A <a@b>\n"))
        # In git's `token: value` form, which is how it stores the line.
        self.assertEqual(bodies, [
            "Subj\n\nBody.\n\nNote: kept.\nhttps: //x.example/a\nSigned-off-by: A <a@b>",
            "Subj\n\nBody.\n\nNote: kept.\nhttps: //x.example/a",
            "Subj\n\nBody.\n\nNote: kept.",
            "Subj\n\nBody.",
        ])

    def test_an_emptied_paragraph_goes_and_the_search_stops_there(self):
        bodies = list(prose.signed_bodies("Subj\n\nBody.\nCo-Authored-By: A <a@b>\n\nProse: checked\nProse-Sig: 0\n"))
        # git adds trailers to one paragraph only, so the one before is signed as written.
        self.assertEqual(bodies[-1], "Subj\n\nBody.\nCo-Authored-By: A <a@b>")
        self.assertEqual(len(bodies), 3)

    def test_the_search_never_reaches_the_title(self):
        self.assertEqual(list(prose.signed_bodies("Fix: the parser\n")), ["Fix: the parser"])

    def test_the_search_stops_at_an_indented_line(self):
        bodies = list(prose.signed_bodies("Subj\n\nBody.\n\nRefs: 1\nReviewed-by: R\n  wrapped\nProse: p\nAcked-by: A\n"))
        self.assertEqual(bodies[-1], "Subj\n\nBody.\n\nRefs: 1\nReviewed-by: R\n  wrapped")
        self.assertEqual(len(bodies), 3)

    def test_a_line_starting_with_a_hash_is_refused(self):
        with self.assertRaises(prose.Refused):
            prose.refuse_comment_lines("FEAT(x): add a thing\n\nBody.\n# not a heading\n")

    def test_the_body_text_changes_the_message_hash(self):
        self.assertNotEqual(prose.message_hash("Subj\n\nOne."), prose.message_hash("Subj\n\nTwo."))
        self.assertTrue(prose.committed_message_matches("Subj\n\nOne.\n\nProse: ✓ 0:0\n",
                                                        prose.message_hash("Subj\n\nOne.\n")))
        self.assertRegex(prose.message_hash("Subj"), r"^[0-9a-f]{12}$")


class SignatureThroughGit(unittest.TestCase):
    """The trailer holds for the commit it was made for, and only that one."""

    MESSAGES = {
        "plain": "FEAT(x): add a thing\n\nOne paragraph of body.\n",
        "trailing whitespace": "FEAT(x): add a thing   \n\nBody line.  \nSecond line.\t\n\n\n",
        "blank-line runs": "FEAT(x): add a thing\n\n\n\nPara one.\n\n\n\nPara two.\n",
        "leading blank lines": "\n\n\nFEAT(x): add a thing\n\nBody.\n",
        "existing trailers": "FEAT(x): add a thing\n\nBody.\n\nRefs: #12\nCo-Authored-By: A <a@b.c>\n",
        "a mixed last paragraph": "FEAT(x): add a thing\n\nSome prose.\nSigned-off-by: A <a@b.c>\n",
        "a url after a colon line": "FEAT(x): add a thing\n\nDetails are in the doc:\nhttps://example.com/doc\n",
        "a url paragraph": "FEAT(x): add a thing\n\nBody.\n\nhttps://example.com/doc\n",
        "crlf": "FEAT(x): add a thing\r\n\r\nBody.\r\n",
        "subject only": "FEAT(x): add a thing\n",
        "one-line trailer-shaped paragraph": "FEAT(x): add a thing\n\nBody.\n\nChecked: X. Not checked: Y.\n",
        "a --- line": "FEAT(x): add a thing\n\nBody.\n\n---\n\nMore.\n",
    }

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.counter = 0

    def stage(self):
        self.counter += 1
        self.repo.write("README.md", f"# Title\n\nRevision {self.counter}.\n")

    def assert_round_trip(self, message, cleanup=None):
        if cleanup:
            self.repo.git("config", "commit.cleanup", cleanup)
        self.stage()
        trailer = self.repo.trailers(message)
        self.assertRegex(trailer, TRAILER)
        self.repo.commit(message, trailer)
        result = self.repo.verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        if cleanup:
            self.repo.git("config", "--unset", "commit.cleanup")

    def test_every_message_shape_round_trips_through_dash_F(self):
        for name, message in self.MESSAGES.items():
            with self.subTest(name):
                self.assert_round_trip(message)

    def test_every_message_shape_round_trips_under_cleanup_strip(self):
        for name, message in self.MESSAGES.items():
            with self.subTest(name):
                self.assert_round_trip(message, cleanup="strip")

    def test_the_dash_m_form_round_trips(self):
        # What bug-hunter's commit-with-trailer.sh does: -m subject -m body.
        self.stage()
        trailers = self.repo.trailers("FEAT(x): add a thing\n\nBody text.  \n")
        self.repo.commit(trailers=trailers, m_parts=["FEAT(x): add a thing", "Body text.  "])
        self.assertEqual(self.repo.verify().returncode, 0, self.repo.verify().stdout)

    def test_a_root_commit_round_trips(self):
        self.stage()
        message = "FEAT(x): first\n"
        self.repo.commit(message, self.repo.trailers(message))
        self.assertEqual(self.repo.verify().returncode, 0)

    def test_editing_the_message_after_the_check_is_a_mismatch(self):
        self.stage()
        trailers = self.repo.trailers("FEAT(x): add a thing\n\nBody.\n")
        self.repo.commit("FEAT(x): add a thing\n\nBody, edited.\n", trailers)
        result = self.repo.verify()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("mismatch:"), result.stdout)

    def test_the_trailer_is_one_line_naming_the_tree_and_the_message(self):
        self.stage()
        message = "FEAT(x): add a thing\n\nBody.\n"
        trailer = self.repo.trailers(message)
        tree = self.repo.git("write-tree").strip()
        self.assertEqual(trailer, f"Prose: \u2713 {tree[:12]}:{prose.message_hash(message)}")
        self.repo.commit(message, trailer)
        result = self.repo.verify()
        self.assertEqual((result.returncode, result.stdout), (0, "checked\n"))

    def test_staging_a_change_after_the_check_is_a_tree_mismatch(self):
        self.stage()
        trailer = self.repo.trailers("FEAT(x): add a thing\n")
        self.repo.write("other.py", "x = 1\n")
        self.repo.commit("FEAT(x): add a thing\n", trailer)
        result = self.repo.verify()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("tree:"), result.stdout)
        self.assertIn("staged files changed", result.stdout)

    def test_a_changed_message_and_tree_is_a_message_mismatch(self):
        self.stage()
        trailer = self.repo.trailers("FEAT(x): add a thing\n")
        self.repo.write("other.py", "x = 1\n")
        self.repo.commit("FEAT(x): add another thing\n", trailer)
        self.assertTrue(self.repo.verify().stdout.startswith("mismatch:"), self.repo.verify().stdout)

    def test_a_hand_typed_well_formed_value_is_a_mismatch(self):
        self.stage()
        self.repo.commit("FEAT(x): a\n", "Prose: \u2713 0123456789ab:0123456789ab")
        self.assertTrue(self.repo.verify().stdout.startswith("mismatch:"))

    def test_a_malformed_value_is_unrecognised(self):
        self.stage()
        message = "FEAT(x): a\n"
        tree = self.repo.git("write-tree").strip()[:12]
        good = prose.message_hash(message)
        for value in (
            "checked",
            f"{tree}:{good}",
            f"v {tree}:{good}",
            f"\u2713 {tree[:11]}:{good}",
            f"\u2713 {tree}:{good}0",
            f"\u2713 {tree}",
            f"\u2713 :{good}",
            f"\u2713 ABCDEFABCDEF:{good}",
            f"\u2713 {tree}:{good} extra",
        ):
            with self.subTest(value):
                self.repo.write("README.md", f"# {value}\n")
                self.repo.git("commit", "-q", "--allow-empty", "-m", message.strip(),
                              "--trailer", f"Prose: {value}")
                result = self.repo.verify()
                self.assertEqual(result.returncode, 1)
                self.assertTrue(result.stdout.startswith("unrecognised:"), result.stdout)

    def test_no_trailer_is_missing(self):
        self.stage()
        self.repo.commit("FEAT(x): a\n")
        result = self.repo.verify()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("missing:"))

    def test_a_blank_value_is_unrecognised_not_missing(self):
        # `missing` means git sees no Prose key; a key with a blank value is
        # there, so the hook's report calls it unrecognised.
        for value in ("", " ", "\u00a0"):
            with self.subTest(repr(value)):
                self.stage()
                self.repo.commit(f"FEAT(x): a\n\nProse:{' ' if value else ''}{value}\n")
                result = self.repo.verify()
                self.assertEqual(result.returncode, 1)
                self.assertTrue(result.stdout.startswith("unrecognised:"), result.stdout)

    def test_a_commit_stored_under_another_encoding_label_is_a_mismatch(self):
        # `git -c i18n.commitEncoding=…` at commit is config `prose check`
        # never saw; with no Prose key the commit is still just missing.
        for encoding in ("ISO-8859-1", "UTF-7", "UTF-16", "EUC-TW", "SHIFT_JIS"):
            with self.subTest(encoding):
                self.stage()
                self.repo.git("-c", f"i18n.commitEncoding={encoding}", "commit", "-q", "-m", "fix typo")
                self.assertTrue(self.repo.verify().stdout.startswith("missing:"), self.repo.verify().stdout)
                self.stage()
                message = "Title\n\nFix the +AGgAaQBkAGQAZQBu- bug.\n"
                trailer = self.repo.trailers(message)
                (self.repo.path / ".msg").write_text(message)
                self.repo.git("-c", f"i18n.commitEncoding={encoding}", "commit", "-q", "-F", ".msg",
                              "--trailer", trailer)
                result = self.repo.verify()
                if result.stdout.startswith("missing:"):
                    # glibc's iconv shows a message labelled UTF-16 with no trailers.
                    self.assertIn("UTF-16", encoding)
                    continue
                self.assertEqual(result.returncode, 1)
                self.assertTrue(result.stdout.startswith("mismatch:"), result.stdout)

    def test_an_unknown_value_is_unrecognised(self):
        self.stage()
        self.repo.commit("FEAT(x): a\n", "Prose: done")
        self.assertTrue(self.repo.verify().stdout.startswith("unrecognised:"))

    def test_a_skip_value_is_unrecognised(self):
        # Every commit has a message, so every commit gets the pass: the only
        # value is the snapshot (DECISIONS: the skip is dropped).
        self.stage()
        self.repo.commit("FEAT(x): a\n", "Prose: skipped (no prose)")
        result = self.repo.verify()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("unrecognised:"), result.stdout)

    def test_amending_a_cherry_picked_commit_keeps_its_x_line_signed(self):
        # git counts the -x line as one it wrote when it places the trailers,
        # so the message keeps that paragraph as a trailer block.
        self.repo.write("f.txt", "base\n")
        self.repo.commit("base\n")
        self.repo.git("checkout", "-q", "-b", "feat")
        self.stage()
        self.repo.commit("DOCS(x): add readme\n")
        self.repo.git("checkout", "-q", "-")
        self.repo.git("cherry-pick", "-x", "feat")
        message = self.repo.git("log", "-1", "--format=%B")
        self.assertIn("(cherry picked from commit ", message)
        trailer = self.repo.trailers(message, "--amend")
        (self.repo.path / ".msg").write_text(message)
        self.repo.git("commit", "-q", "--amend", "-F", ".msg", "--trailer", trailer)
        self.assertEqual(self.repo.verify().stdout, "checked\n")
        stored = self.repo.git("log", "-1", "--format=%B")
        self.assertIn("(cherry picked from commit ", stored)
        self.assertNotEqual(prose.message_hash(message), prose.message_hash("DOCS(x): add readme\n"))

    def test_a_comment_whose_text_changed_is_prose_even_if_the_text_exists_elsewhere(self):
        self.repo.write("a.py", "a = 1  # retry three times\nb = 2  # never retry\n")
        self.repo.commit("base\n")
        self.repo.write("a.py", "a = 1  # retry three times\nb = 2  # retry three times\n")
        out = self.repo.prose("check", "-F", "-", "--goals", "g", stdin="FEAT(x): a\n").stdout
        self.assertIn("a.py:2", out)

    def test_a_commit_that_only_deletes_doc_lines_lists_the_doc(self):
        self.repo.write("README.md", "# Deploy\n\nObsolete note.\n")
        self.repo.commit("base\n")
        self.repo.write("README.md", "# Deploy\n")
        out = self.repo.prose("check", "-F", "-", "--goals", "g", stdin="DOCS(x): trim\n").stdout
        self.assertIn("README.md", out)

    def test_a_bare_carriage_return_does_not_shift_comment_lines(self):
        self.repo.write("a.py", "x = 1  # a\rb = 2\ny = 2\n# old note\nz = 3\n")
        self.repo.commit("base\n")
        self.repo.write("a.py", "x = 1  # a\rb = 2\ny = 2\n# old note\n# new note\nz = 3\n")
        out = self.repo.prose("check", "-F", "-", "--goals", "g", stdin="FEAT(x): note\n").stdout
        self.assertIn("a.py:3-4  (comment)", out)

    def test_a_log_output_encoding_config_does_not_break_verify(self):
        self.stage()
        message = "Fix the caf\u00e9 menu\n"
        self.repo.commit(message, self.repo.trailers(message))
        self.repo.git("config", "i18n.logOutputEncoding", "ISO-8859-1")
        result = self.repo.verify()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_line_starting_with_the_configured_comment_char_is_refused(self):
        self.repo.git("config", "core.commentChar", ";")
        self.stage()
        result = self.repo.prose("check", "-F", "-", "--goals", "g",
                                 stdin="Subj\n\n; note kept in the checked text\n")
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_a_doc_under_a_build_directory_is_prose(self):
        # Only vendored directories exempt docs (DECISIONS: docs are exempt only where vendored).
        self.repo.write("docs/build/README.md", "Run make.\n")
        out = self.repo.prose("check", "-F", "-", "--goals", "g", stdin="DOCS(x): a\n").stdout
        self.assertIn("docs/build/README.md", out)

    def test_a_submodule_at_a_code_looking_path_is_skipped(self):
        sub = Repo()
        self.addCleanup(sub.cleanup)
        sub.write("x.txt", "x\n")
        sub.commit("sub\n")
        head = sub.git("rev-parse", "HEAD").strip()
        self.repo.git("update-index", "--add", "--cacheinfo", f"160000,{head},external/three.js")
        message = "FEAT(x): add three.js\n"
        result = self.repo.two_calls("check", "-F", "-", "--goals", "g", stdin=message)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_an_uppercase_auto_comment_char_is_auto(self):
        self.repo.git("config", "core.commentChar", "AUTO")
        self.stage()
        result = self.repo.prose("check", "-F", "-", "--goals", "g", stdin="Title\n\nBody\n# trailing note\n")
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_a_latin1_commit_encoding_is_refused(self):
        self.repo.git("config", "i18n.commitEncoding", "ISO-8859-1")
        self.stage()
        (self.repo.path / ".msg").write_bytes("Fix the caf\u00e9 menu\n".encode("latin-1"))
        result = self.repo.prose("check", "-F", ".msg", "--goals", "g")
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_a_message_that_is_not_utf8_is_refused(self):
        self.stage()
        (self.repo.path / ".msg").write_bytes(b"Caf\xe9 change\n")
        result = self.repo.prose("check", "-F", ".msg", "--goals", "g")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.repo.git("config", "i18n.commitEncoding", "ISO-8859-1")
        result = self.repo.prose("check", "-F", "-", "--goals", "g", stdin="Plain change\n")
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_a_unicode_noncharacter_in_the_message_is_refused(self):
        self.stage()
        for char in ("\uffff", "\ufdd0", "\U0001fffe"):
            with self.subTest(hex(ord(char))):
                (self.repo.path / ".msg").write_text(f"Title\n\nBody with {char} here\n", encoding="utf-8")
                result = self.repo.prose("check", "-F", ".msg", "--goals", "g")
                self.assertEqual(result.returncode, 2, result.stdout)

    def test_a_non_default_trailer_separator_is_refused(self):
        self.repo.git("config", "trailer.separators", ":#")
        self.stage()
        result = self.repo.prose("check", "-F", "-", "--goals", "g", stdin="Title\n\nFixes #12\n")
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_trailer_key_and_command_config_is_refused(self):
        for key, value in (("trailer.ack.key", "Acked-by"), ("trailer.foo.command", "echo x")):
            with self.subTest(key):
                self.repo.git("config", key, value)
                self.stage()
                result = self.repo.prose("check", "-F", "-", "--goals", "g", stdin="Title\n\nack: yes\n")
                self.repo.git("config", "--unset", key)
                self.assertEqual(result.returncode, 2, result.stdout)

    def test_any_trailer_config_that_rewrites_the_message_is_refused(self):
        for key, value in (("trailer.bug-hunter.ifexists", "replace"), ("trailer.ifexists", "replace"),
                           ("trailer.ifexists", "doNothing"), ("trailer.where", "start")):
            with self.subTest(f"{key}={value}"):
                self.repo.git("config", key, value)
                self.stage()
                result = self.repo.prose("check", "-F", "-", "--goals", "g", stdin="Title\n\nPR: 42\n")
                self.repo.git("config", "--unset", key)
                self.assertEqual(result.returncode, 2, result.stdout)

    def test_a_line_of_only_non_ascii_whitespace_is_not_a_paragraph_break(self):
        self.stage()
        message = "Title\n\nNote:\n  folded value\n\u00a0\nSigned-off-by: A <a@a>\nRefs: x\n"
        self.repo.commit(message, self.repo.trailers(message))
        result = self.repo.verify()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_prose_indented_under_an_added_trailer_is_signed(self):
        self.stage()
        message = "Title\n\nBody.\n"
        trailers = self.repo.trailers(message)
        self.repo.commit(message + "\nCo-authored-by: X <x@x>\n  UNCHECKED PROSE\n", trailers)
        self.assertTrue(self.repo.verify().stdout.startswith("mismatch:"), self.repo.verify().stdout)

    def test_an_empty_valued_added_key_before_an_indented_line_verifies_or_is_refused(self):
        self.stage()
        message = "Title\n\nFixes: 1\nCo-authored-by:\n  Ann <a@b>\n"
        result = self.repo.two_calls("check", "-F", "-", "--goals", "g", stdin=message)
        if result.returncode == 0:
            self.repo.commit(message, block_trailer(result.stdout))
            self.assertEqual(self.repo.verify().returncode, 0, self.repo.verify().stdout)
        else:
            self.assertEqual(result.returncode, 2)

    def test_a_bare_carriage_return_in_the_message_verifies_or_is_refused(self):
        self.stage()
        message = "Title\n\nKey:\rvalue\n"
        (self.repo.path / ".msg").write_bytes(message.encode())
        result = self.repo.two_calls("check", "-F", ".msg", "--goals", "g")
        if result.returncode == 0:
            self.repo.commit(message, block_trailer(result.stdout))
            self.assertEqual(self.repo.verify().returncode, 0, self.repo.verify().stdout)
        else:
            self.assertEqual(result.returncode, 2)

    def test_a_default_separator_overriding_another_scope_is_not_refused(self):
        global_config = self.repo.path.parent / f"{self.repo.path.name}-global"
        global_config.write_text("[trailer]\n\tseparators = ;\n")
        self.repo.git("config", "trailer.separators", ":")
        self.stage()
        env = dict(os.environ, GIT_CONFIG_GLOBAL=str(global_config))
        result = run([sys.executable, str(SCRIPT), "check", "-F", "-", "--goals", "g", *ALL_FILES],
                     cwd=self.repo.path, stdin="Title\n", env=env)
        self.assertEqual(result.returncode, 4, result.stderr)

    def test_an_empty_added_key_outside_the_last_paragraph_is_not_refused(self):
        self.stage()
        message = "Title\n\nFixes: 1\nCo-authored-by:\n  foo\n\nSigned-off-by: A <a@b>\n"
        self.repo.commit(message, self.repo.trailers(message))
        self.assertEqual(self.repo.verify().returncode, 0, self.repo.verify().stdout)

    def test_a_unicode_space_is_not_git_indentation(self):
        self.stage()
        message = "Title\n\nFixes: 1\nCo-authored-by:\n  foo\n\u00a0bar\n"
        self.repo.commit(message, self.repo.trailers(message))
        self.assertEqual(self.repo.verify().returncode, 0, self.repo.verify().stdout)

    def test_a_message_ending_in_a_bare_carriage_return_is_not_refused(self):
        self.stage()
        message = "Title\n\nBody text\r"
        (self.repo.path / ".msg").write_bytes(message.encode())
        result = self.repo.two_calls("check", "-F", ".msg", "--goals", "g")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.repo.commit(message, block_trailer(result.stdout))
        self.assertEqual(self.repo.verify().returncode, 0, self.repo.verify().stdout)

    def test_a_fold_keeps_unicode_space_at_the_start_of_the_value(self):
        self.stage()
        message = "Title\n\nKey:\n   \u00a0value\n"
        self.repo.commit(message, self.repo.trailers(message))
        self.assertEqual(self.repo.verify().returncode, 0, self.repo.verify().stdout)

    def test_reindenting_a_trailer_paragraph_git_leaves_alone_is_a_prose_edit(self):
        self.assertNotEqual(
            prose.message_body("Title\n\nKey:\n  v\n\nSigned-off-by: A <a@b>\n"),
            prose.message_body("Title\n\nKey: v\n\nSigned-off-by: A <a@b>\n"),
        )

    def test_an_edit_to_a_prose_line_starting_with_an_added_key_is_a_mismatch(self):
        self.assertNotEqual(
            prose.message_body("T: x\n\nThe fix is safe.\nProse: the rollout needs no migration.\n"),
            prose.message_body("T: x\n\nThe fix is safe.\nProse: the rollout needs a manual migration.\n"),
        )

    def test_an_amend_verifies_and_lists_against_the_parent(self):
        self.repo.write("base.txt", "base\n")
        self.repo.commit("base\n")
        self.stage()
        message = "DOCS(x): add a readme\n"
        self.repo.commit(message, self.repo.trailers(message))
        self.repo.write("a.py", "x = 1\n")
        reworded = "DOCS(x): add a readme and a module\n"
        listed = self.repo.prose("check", "-F", "-", "--goals", "g", stdin=reworded).stdout
        self.assertNotIn("README.md", listed)
        listed = self.repo.prose("check", "-F", "-", "--goals", "g", "--amend", stdin=reworded).stdout
        self.assertIn("README.md", listed)
        for extra in ((), ("--amend",)):
            with self.subTest(extra):
                trailer = self.repo.trailers(reworded, *extra)
                self.repo.git("commit", "-q", "--amend", "-m", reworded.strip(), "--trailer", trailer)
                self.assertEqual(self.repo.verify().stdout, "checked\n")

    def test_a_merge_commit_is_not_checked(self):
        self.stage()
        self.repo.commit("base\n")
        self.repo.git("checkout", "-q", "-b", "side")
        self.repo.write("b.txt", "b\n")
        self.repo.commit("side\n")
        self.repo.git("checkout", "-q", "-")
        self.repo.write("c.txt", "c\n")
        self.repo.commit("main\n")
        self.repo.git("merge", "-q", "--no-edit", "side")
        result = self.repo.verify()
        self.assertEqual(result.returncode, 0)
        self.assertIn("merge", result.stdout)

    def test_a_bad_revision_cannot_be_verified(self):
        self.stage()
        self.repo.commit("a\n")
        self.assertEqual(self.repo.verify("nope").returncode, 3)


class SignatureCoverage(unittest.TestCase):
    """Every line of prose in the message is covered, trailer-shaped or not."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("README.md", "# Hi\n")

    def commit_signed_for(self, signed_text, landed_text):
        # snapshot, not check: check refuses some of these texts.
        self.repo.commit(landed_text, prose.snapshot(signed_text, str(self.repo.path)))
        return self.repo.verify()

    def test_editing_a_trailer_shaped_last_paragraph_is_a_mismatch(self):
        result = self.commit_signed_for(
            "Add readme\n\nExplains usage.\n\nNote: the --legacy flag still works.\n",
            "Add readme\n\nExplains usage.\n\nNote: the --legacy flag is removed.\n",
        )
        self.assertTrue(result.stdout.startswith("mismatch:"), result.stdout)

    def test_editing_a_line_starting_with_a_hash_is_a_mismatch(self):
        result = self.commit_signed_for(
            "Add readme\n\nWhy.\n#123 is fixed by this.\n",
            "Add readme\n\nWhy.\n#999 is fixed by this.\n",
        )
        self.assertTrue(result.stdout.startswith("mismatch:"), result.stdout)

    def test_an_empty_valued_line_before_an_indented_block_round_trips(self):
        for message in (
            "FEAT(cli): add --dry-run\n\nUsage:\n    tool --dry-run\n",
            "FEAT(cli): a\n\nFollow-ups:\n  - one\n  - two\n",
            "FEAT(cli): a\n\nExample:\n\tfoo()\n",
        ):
            with self.subTest(message):
                self.repo.write("README.md", f"# {len(message)}\n")
                self.repo.commit(message, self.repo.trailers(message))
                result = self.repo.verify()
                self.assertEqual(result.returncode, 0, result.stdout)

    def test_git_folds_only_a_paragraph_it_reads_as_trailers(self):
        # git leaves a mixed paragraph alone, folds a whole block, and folds a
        # mixed one it reads as a block because it carries a Signed-off-by.
        for message in (
            "FEAT(cli): a\n\nProse.\nExample:\n    $ cmd\n",
            "FEAT(cli): a\n\nProse.\nExample:\n    $ cmd\nSigned-off-by: A <a@b>\n",
            "FEAT(cli): a\n\nA:\n  x\nB:\n  y\n    z\n",
            "FEAT(cli): a\n\nUsage:\n    cmd\n\nCo-Authored-By: C <c@d>\n",
        ):
            with self.subTest(message):
                self.repo.write("README.md", f"# {len(message)}\n")
                self.repo.commit(message, self.repo.trailers(message))
                result = self.repo.verify()
                self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_folded_block_still_signs_its_indented_line(self):
        self.assertNotEqual(
            prose.message_body("S\n\nUsage:\n    tool --a\n"),
            prose.message_body("S\n\nUsage:\n    tool --b\n"),
        )

    def test_a_url_after_a_colon_line_is_not_refused_and_round_trips(self):
        message = "Add readme\n\nDetails are in the design doc:\nhttps://example.com/doc\n"
        self.repo.commit(message, self.repo.trailers(message))
        self.assertEqual(self.repo.verify().returncode, 0, self.repo.verify().stdout)

    def test_editing_a_bug_hunter_keyed_line_is_a_mismatch_wherever_it_is(self):
        # Once the known gap: such lines were left out of the hash.
        for signed, landed in (
            ("Add readme\n\nBug-hunter: the fix is safe\nRefs: 1\n\nMore prose.\n",
             "Add readme\n\nBug-hunter: the fix is unsafe\nRefs: 1\n\nMore prose.\n"),
            ("Add readme\n\nBody.\n\nBug-hunter: the fix is safe\n",
             "Add readme\n\nBody.\n\nBug-hunter: the fix is unsafe\n"),
        ):
            with self.subTest(signed):
                self.repo.write("README.md", f"# {len(signed)}\n")
                result = self.commit_signed_for(signed, landed)
                self.assertTrue(result.stdout.startswith("mismatch:"), result.stdout)

    def test_editing_a_non_final_line_of_the_final_trailer_block_is_a_mismatch(self):
        result = self.commit_signed_for("Add readme\n\nBody.\n\nRefs: 1\nFixes: 2\n",
                                        "Add readme\n\nBody.\n\nRefs: 9\nFixes: 2\n")
        self.assertTrue(result.stdout.startswith("mismatch:"), result.stdout)

    def test_editing_an_indented_line_in_the_final_block_is_a_mismatch(self):
        result = self.commit_signed_for("Add readme\n\nBody.\n\nNote: a\n  b\n",
                                        "Add readme\n\nBody.\n\nNote: a\n  c\n")
        self.assertTrue(result.stdout.startswith("mismatch:"), result.stdout)

    def test_a_trailer_appended_after_the_commit_verifies(self):
        # The accepted cost: any trailer-shaped line appended at the end is
        # outside the signature.
        message = "Add readme\n\nBody.\n\nNote: a\n  b\n"
        self.repo.commit(message, [self.repo.trailers(message), "Reviewed-by: R <r@r>"])
        self.assertEqual(self.repo.verify().stdout, "checked\n")
        self.repo.git("commit", "-q", "--amend", "--no-edit", "--trailer", "Acked-by: A <a@a>",
                      "--trailer", "Tested: yes")
        stored = self.repo.git("log", "-1", "--format=%B")
        self.assertTrue(stored.endswith("Reviewed-by: R <r@r>\nAcked-by: A <a@a>\nTested: yes\n\n"), stored)
        self.assertEqual(self.repo.verify().stdout, "checked\n")

    def test_git_adding_to_an_author_written_trailer_block_verifies(self):
        # The message's own last paragraph is trailers, in forms git rewrites
        # (`Refs:one`, an empty value before an indented line), ending in a
        # continuation. git adds its trailers to that paragraph.
        message = "Add readme\n\nBody.\n\nRefs:one\nKey:\n  folded\nX: a\n  cont\n"
        routes = {
            "--trailer": lambda t: self.repo.commit(message, [t, "Co-Authored-By: C <c@d>"]),
            "-s": lambda t: self.repo.git("commit", "-q", "-s", "-F", ".msg", "--trailer", t),
            "interpret-trailers": lambda t: self.repo.git(
                "commit", "-q", "-F", "-", stdin=self.repo.git(
                    "interpret-trailers", "--trailer", "Signed-off-by: S <s@s>", "--trailer", t,
                    stdin=message)),
            "commit script": lambda t: self.assertEqual(self.repo.commit_script(
                "Add readme", message.split("\n\n", 1)[1].rstrip("\n"),
                "--minted-by", str(BUG_HUNTER_MINT), "Bug-hunter", "0 bugs found",
                "--verified-value", str(VERIFY_STAGED), "Prose", t.split(": ", 1)[1],
                "--co-authored-by", "C <c@d>").returncode, 0),
        }
        for name, commit in routes.items():
            with self.subTest(name):
                self.repo.write("README.md", f"# {name}\n")
                commit(self.repo.trailers(message))
                stored = self.repo.git("log", "-1", "--format=%B")
                last = stored.rstrip("\n").split("\n\n")[-1]
                self.assertTrue(last.startswith("Refs: one\nKey: folded\nX: a\n  cont\n"), stored)
                self.assertEqual(self.repo.verify().stdout, "checked\n")


class Check(unittest.TestCase):
    """What `prose check` lists and prints."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("a.py", "x = 1\n")
        self.repo.write("gone.md", "Old.\n")
        self.repo.commit("base\n")

    def check(self, message="FEAT(x): a\n", goals="review the fix; check it is safe to merge"):
        """The first call."""
        args = ["check", "-F", "-"] + (["--goals", goals] if goals is not None else [])
        return self.repo.prose(*args, stdin=message)

    def signed(self, message="FEAT(x): a\n", goals="review the fix; check it is safe to merge"):
        """The first call, then the signing call."""
        return self.repo.two_calls("check", "-F", "-", "--goals", goals, stdin=message)

    def test_it_lists_docs_specs_comments_and_the_message(self):
        self.repo.write("README.md", "# Hi\n")
        self.repo.write("openspec/specs/x/spec.yaml", "k: v\n")
        self.repo.write("a.py", "x = 1\n# Explains y.\ny = 2\n")
        self.repo.write("b.py", "z = 3\n")
        self.repo.git("rm", "-q", "gone.md")
        out = self.check().stdout
        self.assertIn("commit message", out)
        self.assertIn("README.md", out)
        self.assertIn("openspec/specs/x/spec.yaml", out)
        self.assertIn("a.py:2  (comment)", out)
        self.assertNotIn("b.py", out)
        self.assertIn("README.md  (changed)", out)
        self.assertIn("gone.md  (changed)", out)

    def test_it_prints_the_rules_by_structure(self):
        self.repo.write("README.md", "# Hi\n")
        out = self.check().stdout
        for text in ("# The prose pass", "## Scope", "## The pass", "| Commit message |",
                     "**Never cut:**", "## How agents cheat on this pass"):
            self.assertIn(text, out)
        for number in range(1, prose.RULES_IN_FULL + 1):
            self.assertIn(f"\n### {number}. ", out)
        self.assertIn("Before: The hook reports commits landed without trailers skipped.", out)
        self.assertIn("A longer sentence that reads once beats a shorter one read twice.", out)
        self.assertIn("  [ ] 9. Say who acts", out)
        self.assertIn("  [ ] 13. Commit subject says what changed; the body says why", out)
        self.assertNotIn(f"### {prose.RULES_IN_FULL + 1}.", out)

    def listing(self, out):
        """The part of a first call's output before the rules."""
        return out.split("# The prose pass")[0]

    def check_for(self, *file_args, message="FEAT(x): a\n", goals="review the fix"):
        """A first call with these per-file goal arguments and no others."""
        return self.repo.prose("check", "-F", "-", "--goals", goals, *file_args,
                               stdin=message, file_goals=False)

    def goals_by_item(self, out):
        """{listed item: (heading, [goals])} from a first call's listing."""
        found, heading, goals = {}, None, []
        for line in self.listing(out).split("\n"):
            if line and not line.startswith(" "):
                heading, goals = line, []
            elif re.match(r"^  \d+\. ", line):
                goals.append(line.split(". ", 1)[1])
            elif line.startswith("  "):
                found[line.strip().split("  (")[0]] = (heading, goals)
        return found

    def test_the_most_specific_goals_win(self):
        for path in ("README.md", "docs/README.md", "docs/arch.md", "docs/api/ref.md",
                     "docs/api/guide.md", "docs/a.md"):
            self.repo.write(path, "# T\n")
        self.repo.git("rm", "-q", "gone.md")
        want = {"README.md": "readme", "docs/README.md": "readme", "docs/arch.md": "docs",
                "docs/api/ref.md": "api", "docs/api/guide.md": "guide",
                # An exact path beats a pattern with more literal characters.
                "docs/a.md": "exact a"}
        result = self.check_for("--goals-for", "**", "all", "--goals-for", "docs/**", "docs",
                                "--goals-for", "docs/api/**", "api",
                                "--goals-for", "docs/api/guide.md", "guide",
                                "--goals-for", "README.md", "readme",
                                "--goals-for", "docs/**/a.md", "deep a",
                                "--goals-for", "docs/a.md", "exact a")
        self.assertEqual(result.returncode, 4, result.stderr)
        found = self.goals_by_item(result.stdout)
        self.assertEqual({path: found[path][1] for path in want},
                         {path: [goal] for path, goal in want.items()})
        self.assertEqual(found["gone.md"], ("Deleted, so no reader; nothing to rewrite:", []))
        self.assertEqual(found["docs/a.md"][0], "Reader goals for its exact path (--goals-for):")
        self.assertEqual(found["docs/README.md"][0],
                         "Reader goals from the pattern 'README.md' (--goals-for):")
        self.assertEqual(found["commit message"],
                         ("The commit message, read with the goals above (--goals):", []))
        self.assertNotIn("match no listed file", result.stdout)

    def test_equally_specific_goals_that_differ_are_refused(self):
        self.repo.write("docs/a.md", "# T\n")
        result = self.check_for("--goals-for", "docs/*", "one", "--goals-for", "*/a.md", "two")
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("docs/a.md matches equally specific reader goals that differ", result.stderr)
        self.assertIn("'docs/*'", result.stderr)
        self.assertIn("'*/a.md'", result.stderr)
        same = self.check_for("--goals-for", "docs/*", "one", "--goals-for", "*/a.md", " one ")
        self.assertEqual(same.returncode, 4, same.stderr)

    def test_the_glob_patterns_match_like_gitignore(self):
        cases = {
            "*.md": (["a.md", "x/y/a.md", "a.md/b"], ["a.mdx"]),
            "docs/*.md": (["docs/a.md"], ["docs/x/a.md", "x/docs/a.md"]),
            "docs/**": (["docs/a.md", "docs/x/y.md"], ["docsx/a.md", "x/docs/a.md"]),
            "/README.md": (["README.md"], ["x/README.md"]),
            "README.md": (["README.md", "x/README.md"], ["xREADME.md"]),
            "docs/": (["docs/a.md", "x/docs/a.md"], ["docs.md"]),
            "**/api/*.md": (["api/a.md", "x/api/a.md"], ["api/x/a.md"]),
            "a/**/b.md": (["a/b.md", "a/x/y/b.md"], ["ab.md"]),
            "[ab].md": (["a.md", "x/b.md"], ["c.md"]),
            "[!a].md": (["b.md"], ["a.md"]),
            "a?.md": (["ab.md"], ["a.md", "a/.md"]),
            "**": (["a", "x/y/z.md"], []),
            "a[.md": (["a[.md"], ["a.md"]),
        }
        for pattern, (hits, misses) in cases.items():
            rule = prose.GoalRule(pattern, ("g",), "test")
            for path in hits:
                with self.subTest(pattern=pattern, path=path):
                    self.assertTrue(prose.matches(rule, path))
            for path in misses:
                with self.subTest(pattern=pattern, path=path):
                    self.assertFalse(prose.matches(rule, path))
        self.assertEqual([prose._literals(p) for p in ("**", "*.md", "docs/**", "/docs/*.md",
                                                       "[ab].md", "docs/api/**")],
                         [0, 3, 5, 8, 3, 9])

    def test_a_goals_file_is_read_like_goals_for(self):
        self.repo.write("docs/a.md", "# T\n")
        self.repo.write("README.md", "# T\n")
        goals = self.repo.path.parent / f"{self.repo.path.name}-goals.txt"
        goals.write_text("# readers\n\ndocs/**: learn it; use it\n  README.md:\tstart here\n"
                         "**: anything\n", encoding="utf-8")
        result = self.check_for("--goals-file", str(goals))
        self.assertEqual(result.returncode, 4, result.stderr)
        found = self.goals_by_item(result.stdout)
        self.assertEqual(found["docs/a.md"],
                         (f"Reader goals from the pattern 'docs/**' ({goals}:3):", ["learn it", "use it"]))
        self.assertEqual(found["README.md"],
                         (f"Reader goals for its exact path ({goals}:4):", ["start here"]))

    def test_a_bad_goals_file_or_goals_for_is_refused_naming_it(self):
        self.repo.write("docs/a.md", "# T\n")
        goals = self.repo.path.parent / f"{self.repo.path.name}-goals.txt"
        for text, said in (("# ok\ndocs/** learn it\n", f"{goals}:2: expected 'pattern: goal; goal'"),
                           ("docs/**: ; ;\n", f"{goals}:1: no reader goals for 'docs/**'"),
                           ("!docs/**: x\n", f"{goals}:1: '!docs/**' is a negation"),
                           (b"docs/**: \xff\n", "is not valid UTF-8")):
            with self.subTest(text=text):
                goals.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
                result = self.check_for("--goals-file", str(goals))
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn(said, result.stderr)
        for args, said in ((["--goals-file", str(goals) + ".missing"], "could not read the goals file"),
                           (["--goals-for", " ", "x"], "--goals-for: an empty pattern"),
                           (["--goals-for", "docs/**", ";"], "--goals-for: no reader goals")):
            with self.subTest(args=args):
                result = self.check_for(*args)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn(said, result.stderr)

    def test_a_doc_or_spec_without_goals_is_refused_with_its_kinds_default(self):
        self.repo.write("docs/arch.md", "# T\n")
        self.repo.write("README.md", "# T\n")
        self.repo.write("openspec/x/spec.md", "# T\n")
        self.repo.write("a.py", "x = 1\n# Explains y.\ny = 2\n")
        result = self.check_for("--goals-for", "docs/**", "learn it")
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("no reader goals: README.md, openspec/x/spec.md.", result.stderr)
        self.assertIn("  README.md: what it's for; how to start; what to do when it fails\n",
                      result.stderr)
        self.assertIn("  openspec/x/spec.md: what must be true; what's decided vs. open\n",
                      result.stderr)
        self.assertNotIn("docs/arch.md", result.stderr)
        self.assertNotIn("a.py", result.stderr)
        self.repo.write("docs/arch.md", "# T\n\nMore.\n")
        bare = self.check_for()
        self.assertIn("  docs/arch.md: how it works now; why it is that way\n", bare.stderr)

    def test_a_touched_comment_without_goals_gets_its_kinds_default_labelled(self):
        self.repo.write("a.py", "x = 1\n# Explains y.\ny = 2\n")
        result = self.check_for()
        self.assertEqual(result.returncode, 4, result.stderr)
        heading, goals = self.goals_by_item(result.stdout)["a.py:2"]
        self.assertEqual(heading, "Reader goals by default, from the 'Code comment' row of "
                                  "rules.md's reader table (read by someone about to change "
                                  "this code); --goals-for replaces them:")
        self.assertEqual(goals, ["what it does that the code doesn't show",
                                 "what breaks if they change it"])
        named = self.check_for("--goals-for", "*.py", "fix the parser")
        self.assertEqual(self.goals_by_item(named.stdout)["a.py:2"][1], ["fix the parser"])

    def test_a_pattern_that_matches_no_listed_file_is_a_warning(self):
        self.repo.write("docs/a.md", "# T\n")
        goals = self.repo.path.parent / f"{self.repo.path.name}-goals.txt"
        goals.write_text("dcos/**: x\n", encoding="utf-8")
        result = self.check_for("--goals-for", "docs/**", "learn it", "--goals-for", "doc/**", "x",
                                "--goals-file", str(goals))
        self.assertEqual(result.returncode, 4, result.stderr)
        listing = self.listing(result.stdout)
        warned = listing.split("match no listed file (a typo?):\n\n")[1]
        self.assertEqual(warned.split("\n")[:2], ["  'doc/**' (--goals-for)", f"  'dcos/**' ({goals}:1)"])
        self.assertNotIn("'docs/**' (--goals-for)\n", warned)

    def test_the_per_file_goals_are_bound_to_the_token(self):
        self.repo.write("docs/a.md", "# T\n")
        first = self.check_for("--goals-for", "docs/**", "learn it")
        token = pass_token(first.stdout)
        sign = lambda *extra: self.repo.prose("check", "-F", "-", "--pass", token, *extra,
                                              stdin="FEAT(x): a\n", file_goals=False)
        refused = sign("--goals-for", "docs/**", "something else")
        self.assertEqual((refused.returncode, refused.stdout), (2, ""))
        self.assertIn("per-file reader goals differ", refused.stderr)
        self.repo.write("docs/b.md", "# T\n")
        self.repo.write("README.md", "# T\n")
        uncovered = sign()
        self.assertEqual((uncovered.returncode, uncovered.stdout), (2, ""))
        self.assertIn("had no reader goals when the first call ran: README.md.", uncovered.stderr)
        self.repo.git("rm", "-q", "--cached", "README.md")
        self.assertRegex(block_trailer(sign("--goals-for", "docs/**", " learn it").stdout), TRAILER)

    def test_the_message_goals_are_the_messages_alone(self):
        self.repo.write("docs/a.md", "# T\n")
        result = self.check_for("--goals-for", "docs/**", "learn it", goals="review the fix; merge")
        out = self.listing(result.stdout)
        self.assertTrue(out.startswith("Reader goals for the commit message, most probable "
                                       "first."), out)
        self.assertEqual(out.count("review the fix"), 1)
        self.assertEqual(self.goals_by_item(result.stdout)["docs/a.md"][1], ["learn it"])
        self.assertLess(out.index("2. merge"), out.index("\n  commit message\n"))

    def test_a_pattern_naming_a_directory_covers_the_files_under_it(self):
        # gitignore matches a file when a pattern matches any directory above it.
        self.repo.write("docs/y.md", "# T\n")
        self.repo.write("docs/guide/x.md", "# T\n")
        for args in (["--goals-for", "docs", "learn it"], ["--goals-for", "docs/*", "learn it"],
                     ["--goals-for", "/docs", "learn it"], ["--goals-for", "doc[s]", "learn it"]):
            with self.subTest(args=args):
                result = self.check_for(*args)
                self.assertEqual(result.returncode, 4, result.stderr)
                found = self.goals_by_item(result.stdout)
                self.assertEqual(found["docs/guide/x.md"][1], ["learn it"])
        only_dirs = self.check_for("--goals-for", "y.md/", "x", "--goals-for", "docs/**", "learn it")
        self.assertEqual(self.goals_by_item(only_dirs.stdout)["docs/y.md"][1], ["learn it"])

    def test_a_file_named_with_glob_characters_gets_goals_by_its_path(self):
        self.repo.write("a[1].md", "# T\n")
        self.repo.write("a*.md", "# T\n")
        self.repo.write("#todo.md", "# T\n")
        refused = self.check_for()
        self.assertIn("  \\#todo.md: how it works now", refused.stderr)
        goals = self.repo.path.parent / f"{self.repo.path.name}-goals.txt"
        goals.write_text("a[1].md: one\na\\*.md: star\n\\#todo.md: todo\n", encoding="utf-8")
        result = self.check_for("--goals-file", str(goals))
        self.assertEqual(result.returncode, 4, result.stderr)
        found = self.goals_by_item(result.stdout)
        self.assertEqual({path: found[path][1] for path in ("a[1].md", "a*.md", "#todo.md")},
                         {"a[1].md": ["one"], "a*.md": ["star"], "#todo.md": ["todo"]})

    def test_a_deleted_doc_needs_no_goals(self):
        self.repo.git("rm", "-q", "gone.md")
        result = self.check_for()
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("gone.md  (changed)", result.stdout)

    def test_the_signing_call_takes_the_same_goals_in_another_order(self):
        self.repo.write("docs/a.md", "# T\n")
        self.repo.write("README.md", "# T\n")
        first = self.check_for("--goals-for", "docs/**", "one", "--goals-for", "README.md", "two")
        signed = self.repo.prose("check", "-F", "-", "--goals", "review the fix",
                                 "--goals-for", "README.md", "two", "--goals-for", "docs/**", "one",
                                 "--pass", pass_token(first.stdout), stdin="FEAT(x): a\n",
                                 file_goals=False)
        self.assertRegex(block_trailer(signed.stdout), TRAILER)

    def test_a_goals_file_may_start_with_a_byte_order_mark(self):
        self.repo.write("docs/a.md", "# T\n")
        goals = self.repo.path.parent / f"{self.repo.path.name}-goals.txt"
        for text in ("# readers\ndocs/**: learn it\n", "docs/**: learn it\n"):
            with self.subTest(text=text):
                goals.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
                result = self.check_for("--goals-file", str(goals))
                self.assertEqual(result.returncode, 4, result.stderr)
                self.assertNotIn("match no listed file", result.stdout)

    def suggested_goals_file(self, refused):
        """A goals file holding the lines a refusal suggests, as written."""
        lines = [line for line in refused.stderr.split("\n")
                 if line.startswith("  ") and not line.startswith("      (")]
        goals = self.repo.path.parent / f"{self.repo.path.name}-suggested.txt"
        goals.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return goals

    def test_a_suggested_line_reads_back_for_a_path_with_colons_or_edge_spaces(self):
        for path in ("notes: draft.md", "notes.md ", " lead.md"):
            self.repo.write(path, "# T\n")
        refused = self.check_for()
        self.assertEqual(refused.returncode, 2)
        result = self.check_for("--goals-file", str(self.suggested_goals_file(refused)))
        self.assertEqual(result.returncode, 4, result.stderr)
        found = {item.strip(): goals for item, goals in self.goals_by_item(result.stdout).items()}
        for path in ("notes: draft.md", "notes.md ", " lead.md"):
            self.assertEqual(found[path.strip()][1],
                             ["how it works now", "why it is that way"], path)
        by_flag = self.check_for("--goals-for", "notes: draft.md", "a", "--goals-for", "notes.md ", "b",
                                 "--goals-for", "\\ lead.md", "c")
        self.assertEqual(by_flag.returncode, 4, by_flag.stderr)
        escaped = self.check_for("--goals-for", "notes: draft.md", "a", "--goals-for", "notes.md\\ ", "b",
                                 "--goals-for", " lead.md", "c")
        self.assertEqual(escaped.returncode, 4, escaped.stderr)

    def test_a_deleted_doc_is_never_given_goals(self):
        self.repo.write("docs/old.md", "Old.\n")
        self.repo.commit("more\n")
        self.repo.git("rm", "-q", "docs/old.md")
        self.repo.write("docs/new.md", "# T\n")
        listed = self.check_for("--goals-for", "docs/**", "learn it")
        self.assertEqual(listed.returncode, 4, listed.stderr)
        self.assertEqual(self.goals_by_item(listed.stdout)["docs/old.md"],
                         ("Deleted, so no reader; nothing to rewrite:", []))
        self.assertNotIn("match no listed file", listed.stdout)
        tied = self.check_for("--goals-for", "docs/new.md", "a", "--goals-for", "docs/*", "a",
                              "--goals-for", "docs/**", "b")
        self.assertEqual(tied.returncode, 4, tied.stderr)

    def test_an_exact_path_with_a_blank_before_its_colon_still_wins(self):
        self.repo.write("README.md", "# T\n")
        goals = self.repo.path.parent / f"{self.repo.path.name}-goals.txt"
        goals.write_text("**/README.md: any readme\nREADME.md : this one\n", encoding="utf-8")
        result = self.check_for("--goals-file", str(goals))
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertEqual(self.goals_by_item(result.stdout)["README.md"],
                         (f"Reader goals for its exact path ({goals}:2):", ["this one"]))

    def test_a_pattern_python_cannot_compile_is_refused_not_a_crash(self):
        self.repo.write("docs/a.md", "# T\n")
        result = self.check_for("--goals-for", "docs/[z-a]*", "x", "--goals-for", "**", "y")
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("prose: --goals-for: 'docs/[z-a]*'", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_the_refusal_for_missing_goals_names_the_patterns_that_matched_nothing(self):
        self.repo.write("docs/guide.md", "# T\n")
        result = self.check_for("--goals-for", "./docs/guide.md", "x")
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("'./docs/guide.md' (--goals-for) matches no listed file", result.stderr)

    def test_every_kind_has_a_default_in_the_reader_table(self):
        for kind, path in (("comment", "a.py"), ("readme", "x/README.rst"),
                           ("spec", "openspec/x/README.md"), ("doc", "docs/CHANGELOG.md")):
            with self.subTest(kind=kind):
                self.assertEqual(prose.kind_of(path), kind)
                label, who, goals = prose.kind_default(kind)
                self.assertTrue(label.startswith(prose.KIND_ROWS[kind]) and who and goals)

    def test_the_rules_hold_a_doc_to_what_is(self):
        out = self.check().stdout
        self.assertIn("### 6. What is, not how it got here", out)
        self.assertIn("A narrow role's unused", out)
        self.assertIn("Labelling the past does not make it worth keeping", out)
        self.assertIn("Keeping context a reviewer needed in a document whose reader never will", out)

    def test_the_rules_ask_for_a_reason_instead_of_a_catchphrase(self):
        out = self.check().stdout
        self.assertIn("### 5. Plain words, and reasons instead of catchphrases", out)
        self.assertIn("A claim is stated once, with its reason", out)
        self.assertIn("grep the repository for it", out)
        self.assertIn("Repeating a phrase that sounds like a reason in place of the reason.", out)

    def test_the_signing_call_prints_only_the_result_block_holding_the_one_trailer(self):
        self.repo.write("README.md", "# Hi\n")
        result = self.signed()
        self.assertEqual(result.returncode, 0, result.stderr)
        trailer = block_trailer(result.stdout)
        self.assertRegex(trailer, TRAILER)
        self.assertEqual(result.stdout.count("\n"), 4, result.stdout)

    def test_a_code_only_commit_still_gets_checked_for_its_message(self):
        self.repo.write("a.py", "x = 2\n")
        self.assertIn("  commit message", self.check().stdout.split("\n"))
        self.assertRegex(block_trailer(self.signed().stdout), TRAILER)

    def test_an_empty_message_is_refused(self):
        self.repo.write("a.py", "x = 2\n")
        result = self.check(message="\n\n")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Prose:", result.stdout)

    def test_an_unparseable_code_file_is_listed_as_such(self):
        self.repo.write("a.py", "def f(:\n")
        self.assertIn("a.py  (did not parse)", self.check().stdout)

    def test_a_code_file_that_cannot_be_read_is_listed_not_refused(self):
        sub = Repo()
        self.addCleanup(sub.cleanup)
        sub.write("x.txt", "x\n")
        sub.commit("sub\n")
        head = sub.git("rev-parse", "HEAD").strip()
        self.repo.git("update-index", "--add", "--cacheinfo", f"160000,{head},external/three.js")
        result = self.check()
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("external/three.js  (could not be read)", result.stdout)
        self.assertRegex(block_trailer(self.signed().stdout), TRAILER)

    def test_a_pure_rename_of_a_doc_lists_nothing(self):
        self.repo.git("mv", "gone.md", "moved.md")
        self.repo.git("config", "diff.renames", "false")
        self.assertNotIn("moved.md", self.check().stdout)

    def test_history_language_in_a_touched_comment_is_flagged_without_blocking(self):
        self.repo.write("a.py", "x = 1\n# It used to be two calls.\ny = 2\n")
        result = self.check()
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("Flags (warnings, not blocking):", result.stdout)
        self.assertIn('a.py:2  "It used to" narrates what the code did before.', result.stdout)
        lines = result.stdout.rstrip("\n").split("\n")
        self.assertLess(lines.index("  a.py:2  (comment)"), lines.index("Flags (warnings, not blocking):"))
        signed = self.repo.prose("check", "-F", "-", "--pass", pass_token(result.stdout),
                                 stdin="FEAT(x): a\n")
        trailer = block_trailer(signed.stdout)
        self.assertRegex(trailer, TRAILER)
        self.repo.commit("FEAT(x): a\n", trailer)
        self.assertEqual(self.repo.verify().returncode, 0)

    def test_history_language_outside_the_change_is_not_flagged(self):
        self.repo.write("b.py", "# It used to be two calls.\ny = 2\n")
        self.repo.commit("base\n")
        self.repo.write("b.py", "# It used to be two calls.\ny = 3\n")
        out = self.check().stdout
        self.assertNotIn("Flags", out)

    def test_a_hash_line_is_refused_with_the_fix(self):
        result = self.check(message="Subj\n\nProse.\n#12 is fixed.\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("starts with `#`", result.stderr)
        self.assertIn("Reword it so it does not start with `#`", result.stderr)

    def test_no_goals_means_no_token_and_no_rules(self):
        self.repo.write("README.md", "# Hi\n")
        for goals in (None, "", " ; ;"):
            with self.subTest(goals=goals):
                result = self.check(goals=goals)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("--goals", result.stderr)

    def test_the_goals_are_echoed_first_in_order_and_kept_out_of_the_trailers(self):
        self.repo.write("README.md", "# Hi\n")
        out = self.check(goals="review the fix; check it is safe to merge").stdout
        self.assertTrue(out.startswith("Reader goals"), out)
        self.assertLess(out.index("1. review the fix"), out.index("2. check it is safe to merge"))
        self.assertLess(out.index("2. check it is safe"), out.index("\n  commit message\n"))
        self.assertNotIn("review", block_trailer(self.signed().stdout))

    def test_a_file_too_deep_to_parse_is_listed_and_does_not_block(self):
        self.repo.write("deep.py", "# Deep.\nx = " + "+".join(["1"] * 200000) + "\n")
        result = self.check()
        self.assertEqual(result.returncode, 4, result.stderr[-500:])
        self.assertIn("deep.py", result.stdout)

    def test_a_doc_git_diffs_as_binary_is_listed(self):
        (self.repo.path / "README.md").write_bytes("# Hi\n".encode("utf-16"))
        self.repo.git("add", "README.md")
        self.assertIn("README.md", self.check().stdout)

    def test_a_binary_code_file_lists_no_phantom_comments(self):
        (self.repo.path / "fixture.ts").write_bytes(b"\x00\x01G\x40// not a comment\n\xff\x00" * 50)
        self.repo.git("add", "fixture.ts")
        self.assertNotIn("fixture.ts", self.check().stdout)

    def test_vendored_files_are_not_prose(self):
        self.repo.write("node_modules/dep/README.md", "# Dep\n")
        self.assertNotIn("node_modules", self.check().stdout)


def sign_twice(text, goals):
    """`prose sign`'s first call, then its signing call with the token. Run
    in the throwaway state directory, outside any repository, so no token
    lands in the git directory of the clone running the tests."""
    first = run([sys.executable, str(SCRIPT), "sign", "--goals", goals], cwd=STATE, stdin=text)
    if first.returncode != 4:
        raise AssertionError(first.stderr)
    return run([sys.executable, str(SCRIPT), "sign", "--pass", pass_token(first.stderr)],
               cwd=STATE, stdin=text)


class PostFooter(unittest.TestCase):
    """`prose sign` and `prose verify-post`."""

    def test_a_signed_text_verifies(self):
        signed = prose.sign("A description.\n\nWith two paragraphs.\n")
        self.assertRegex(signed.rstrip("\n").split("\n")[-1], r"^prose ✓ [0-9a-f]{6}$")
        self.assertEqual(prose.verify_post(signed), (True, "signed"))

    def test_any_edit_breaks_it(self):
        signed = prose.sign("A description.\n\nWith two paragraphs.\n")
        edits = [
            signed.replace("two", "three"),
            signed.replace("A description", "A  description"),
            signed.replace("\n\nWith", "\nWith"),
            "Extra line.\n" + signed,
        ]
        for edited in edits:
            with self.subTest(edited):
                self.assertFalse(prose.verify_post(edited)[0])

    def test_editing_or_removing_the_footer_breaks_it(self):
        signed = prose.sign("Text.\n")
        body, digest = prose.split_footer(signed)
        other = "0" * 6 if digest != "0" * 6 else "1" * 6
        self.assertFalse(prose.verify_post(signed.replace(digest, other))[0])
        self.assertFalse(prose.verify_post(body)[0])
        self.assertFalse(prose.verify_post(signed + "\nP.S. one more thing\n")[0])

    def test_the_footer_must_be_exact(self):
        signed = prose.sign("Text.\n")
        self.assertFalse(prose.verify_post(signed.replace("prose ✓", "prose v"))[0])
        self.assertFalse(prose.verify_post(signed.replace("prose ✓ ", "prose ✓  "))[0])

    def test_line_endings_and_trailing_blank_lines_do_not_matter(self):
        signed = prose.sign("One.\nTwo.\n")
        self.assertTrue(prose.verify_post(signed.replace("\n", "\r\n"))[0])
        self.assertTrue(prose.verify_post(signed.rstrip("\n"))[0])
        self.assertTrue(prose.verify_post(signed + "\n\n")[0])

    def test_signing_again_replaces_the_footer(self):
        once = prose.sign("Text.\n")
        twice = prose.sign(once.replace("Text.", "Text, edited."))
        self.assertEqual(twice.count("prose ✓"), 1)
        self.assertTrue(prose.verify_post(twice)[0])

    def test_sign_refuses_without_goals_and_keeps_them_out_of_the_footer(self):
        refused = run([sys.executable, str(SCRIPT), "sign"], cwd=STATE, stdin="Text.\n")
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(refused.stdout, "")
        self.assertIn("--goals", refused.stderr)
        signed = sign_twice("Text.\n", "approve the PR")
        self.assertEqual(signed.returncode, 0)
        self.assertNotIn("approve", signed.stdout)
        self.assertIn("approve the PR", signed.stderr)

    def test_empty_text_is_refused(self):
        with self.assertRaises(prose.Refused):
            prose.sign("\n\n")

    def test_the_command_line_round_trips(self):
        signed = sign_twice("Body — with a dash.\n", "approve it")
        self.assertEqual(signed.returncode, 0)
        verified = run([sys.executable, str(SCRIPT), "verify-post"], stdin=signed.stdout)
        self.assertEqual(verified.returncode, 0, verified.stdout)
        broken = run([sys.executable, str(SCRIPT), "verify-post"], stdin=signed.stdout.replace("dash", "hyphen"))
        self.assertEqual(broken.returncode, 1)


class PostingHook(unittest.TestCase):
    """The hook before a tool call, as Claude Code sends it."""

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.good = prose.sign("A good body.\n")

    def hook(self, payload, host="claude"):
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        return run(["sh", str(POST_HOOK), "--host", host], stdin=raw)

    def mcp(self, tool, tool_input):
        return {"hook_event_name": "PreToolUse", "cwd": str(self.dir),
                "tool_name": tool, "tool_input": tool_input}

    def bash(self, command):
        return self.mcp("Bash", {"command": command})

    def test_a_prose_command_whose_goals_mention_a_gh_post_is_not_a_post(self):
        for command in (
            "python3 $S/prose.py sign --goals 'check the gh pr create flow; approve it'",
            "python3 /x/prose.py sign --pass abc < body.md > signed.md",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)
        # Anything that could run a second command is still read as a post.
        for command in (
            "python3 /x/prose.py start --goals g; gh pr create --body x",
            "python3 /x/prose.py start --goals \"$(gh pr create --body x)\"",
            "python3 /x/prose.py start --goals g && gh issue comment 3 --body x",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_an_mcp_post_with_a_valid_footer_passes(self):
        result = self.hook(self.mcp("mcp__github__create_pull_request", {"title": "t", "body": self.good}))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_an_mcp_post_without_a_footer_is_blocked(self):
        result = self.hook(self.mcp("mcp__github__add_issue_comment", {"body": "Plain text."}))
        self.assertEqual(result.returncode, 2)
        self.assertIn("prose.py", result.stderr)
        self.assertIn("sign", result.stderr)

    def test_a_nested_review_comment_is_checked_too(self):
        tool_input = {"body": self.good, "comments": [{"path": "a", "body": "Unsigned."}]}
        result = self.hook(self.mcp("mcp__github__create_pull_request_review", tool_input))
        self.assertEqual(result.returncode, 2)
        self.assertIn("comments[0].body", result.stderr)

    def test_the_block_message_gives_the_two_calls_that_sign(self):
        result = self.hook(self.bash('gh pr comment 1 --body "$(cat x)"'))
        self.assertEqual(result.returncode, 2)
        self.assertIn("sign --pass", result.stderr)
        self.assertNotRegex(result.stderr, r"sign --goals '[^']*' < ")

    def test_a_github_tool_without_a_body_field_passes(self):
        result = self.hook(self.mcp("mcp__github__get_pull_request", {"pullNumber": 3}))
        self.assertEqual(result.returncode, 0)

    def test_a_plugin_bundled_github_server_is_checked(self):
        result = self.hook(self.mcp("mcp__plugin_gh_github__add_issue_comment", {"body": "x"}))
        self.assertEqual(result.returncode, 2)

    def test_another_server_is_not_checked(self):
        result = self.hook(self.mcp("mcp__linear__save_comment", {"body": "x"}))
        self.assertEqual(result.returncode, 0)

    def test_gh_with_an_inline_body(self):
        self.assertEqual(self.hook(self.bash("gh pr comment 3 --body 'Unsigned.'")).returncode, 2)
        command = "gh pr comment 3 --body " + shlex.quote(self.good)
        self.assertEqual(self.hook(self.bash(command)).returncode, 0)

    def test_the_heredoc_idiom_is_blocked(self):
        # Not on the allow-list (DECISIONS: the posting hook reads an allow-list).
        body = self.good.rstrip("\n")
        command = f"gh pr create --title T --body \"$(cat <<'EOF'\n{body}\nEOF\n)\""
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)
        command = "gh pr create --title T --body \"$(cat <<'EOF'\nUnsigned, it's plain.\nEOF\n)\""
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_gh_with_a_body_file_relative_to_the_cwd(self):
        (self.dir / "body.md").write_text(self.good)
        self.assertEqual(self.hook(self.bash("gh pr edit 3 --body-file body.md")).returncode, 0)
        (self.dir / "bad.md").write_text("Unsigned.\n")
        self.assertEqual(self.hook(self.bash("gh issue create -t T -F bad.md")).returncode, 2)

    def test_gh_body_file_from_a_heredoc_is_not_an_accepted_form(self):
        command = f"gh pr comment 3 --body-file - <<'EOF'\n{self.good}EOF\n"
        # Not an accepted form (DECISIONS: the posting hook reads an allow-list), so blocked.
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_gh_body_from_a_pipe_cannot_be_read_and_is_blocked(self):
        result = self.hook(self.bash("cat body.md | gh pr comment 3 --body-file -"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot be checked", result.stderr)

    def test_gh_commands_that_post_no_body_pass(self):
        for command in ("gh pr view 3", "gh pr edit 3 --add-label x", "gh issue list", "ls -la"):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 0)

    def test_a_post_later_in_a_chain_is_found(self):
        command = "git push && gh pr comment 3 --body 'Unsigned.'"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_double_quoted_body_with_escapes_is_not_an_accepted_form(self):
        signed = prose.sign("Use `make test` to run it.\n\nCosts $5.\n")
        escaped = signed.rstrip("\n").replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
        command = f'gh pr comment 12 --body "{escaped}"'
        result = self.hook(self.bash(command))
        # Not an accepted form (DECISIONS: the posting hook reads an allow-list), so blocked.
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_a_body_built_by_the_shell_is_called_unreadable(self):
        (self.dir / "signed.md").write_text(self.good)
        result = self.hook(self.bash(f'gh pr create --title T --body "$(cat {self.dir}/signed.md)"'))
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot be checked", result.stderr)

    def test_a_body_file_rewritten_earlier_in_the_command_is_not_trusted(self):
        (self.dir / "pr.md").write_text(self.good)
        command = "printf 'new unsigned text\\n' > pr.md && gh pr edit 5 --body-file pr.md"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_post_inside_a_command_substitution_is_checked(self):
        for command in (
            "url=$(gh pr create --title t --body 'no footer') && echo \"$url\"",
            "PR_URL=`gh pr create --title t --body 'no footer'`",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_command_the_hook_cannot_parse_does_not_let_a_post_through(self):
        for command in (
            "gh pr comment 1 --body 'no footer' && echo $'it\\'s posted'",
            "gh pr comment 1 --body $'Don\\'t merge yet'",
            "gh pr comment 1 --body-file - <<\\EOF\nDon't merge, no footer\nEOF\n",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_backslash_heredoc_delimiter_is_not_an_accepted_form(self):
        command = f"gh pr comment 3 --body-file - <<\\EOF\n{self.good}EOF\n"
        # Not an accepted form (DECISIONS: the posting hook reads an allow-list), so blocked.
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_gh_aliases_and_attached_short_flags_are_checked(self):
        for command in (
            "gh pr new --title t --body 'no footer'",
            "gh issue new --title t --body 'no footer'",
            "gh pr comment 1 -b'no footer'",
            "gh pr comment 1 -b='no footer'",
            "gh pr comment 1 --body-file <(echo no footer)",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_post_in_a_substitution_trusts_no_file_an_earlier_command_writes(self):
        (self.dir / "pr.md").write_text(self.good)
        # Not an accepted form (DECISIONS: the posting hook reads an allow-list), so blocked.
        self.assertEqual(self.hook(self.bash("url=$(gh pr edit 5 --body-file pr.md)")).returncode, 2)
        command = "printf 'unsigned\\n' > pr.md && url=$(gh pr edit 5 --body-file pr.md)"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_signed_post_in_a_substitution_is_not_an_accepted_form(self):
        body = self.good.rstrip("\n")
        command = f"url=$(gh pr create --title T --body \"$(cat <<'EOF'\n{body}\nEOF\n)\")"
        # Not an accepted form (DECISIONS: the posting hook reads an allow-list), so blocked.
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_more_attached_flag_forms_are_read(self):
        (self.dir / "bad.md").write_text("Unsigned.\n")
        (self.dir / "good.md").write_text(self.good)
        for command, code in (
            ("gh pr comment 1 -Fbad.md", 2),
            ("gh pr comment 1 -F=bad.md", 2),
            ("gh pr comment 1 -Fgood.md", 0),
            ("gh -Rowner/repo pr comment 1 --body 'no footer'", 2),
            ("gh pr comment 1 --body " + shlex.quote(self.good), 0),
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, code)

    def test_an_unparsable_command_without_a_gh_post_passes(self):
        self.assertEqual(self.hook(self.bash("echo 'unterminated gh")).returncode, 0)
        # Mentions a gh post verb and cannot be read to the end, so whether it
        # runs one is unknown: blocked.
        command = "cat > notes.md <<'EOF'\nrun gh pr create, it's easy\nEOF\necho 'x"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_quoted_body_containing_a_heredoc_sample_passes(self):
        signed = prose.sign("Fixes the thing.\n\nRun:\n\n    cat <<EOF\n    hi\nEOF\n\nDone.\n")
        command = "gh pr comment 1 --body " + shlex.quote(signed)
        result = self.hook(self.bash(command))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_text_around_a_heredoc_substitution_is_not_ignored(self):
        body = self.good.rstrip("\n")
        command = f"gh pr create --title t --body \"Intro $(cat <<'EOF'\n{body}\nEOF\n)\""
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_close_with_a_comment_is_checked(self):
        for command in ("gh issue close 3 --comment 'unsigned text'", "gh pr close 3 -c 'unsigned text'"):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_reopen_and_revert_bodies_are_checked(self):
        for command in (
            "gh issue reopen 5 -c 'unsigned text'",
            "gh pr reopen 5 --comment 'unsigned text'",
            "gh pr revert 5 -b 'unsigned text'",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_an_unquoted_heredoc_with_backslashes_is_not_trusted(self):
        signed = prose.sign("Path is C:\\\\temp\\\\x\n").rstrip("\n")
        command = f'gh pr comment 5 -b "$(cat <<EOF\n{signed}\nEOF\n)"'
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_arithmetic_shift_is_not_a_heredoc(self):
        body = self.good.rstrip("\n")
        command = f"echo $((1<<x))\ngh pr comment 5 -b \"$(cat <<'EOF'\n{body}\nEOF\n)\""
        # Not an accepted form (DECISIONS: the posting hook reads an allow-list), so blocked.
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)
        command = "echo $((1<<EOF))\ngh pr comment 5 -b 'unsigned'\nEOF\n"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_heredoc_marker_inside_parameter_or_index_syntax_hides_nothing(self):
        for first in ("echo ${x:-<<EOF}", "echo $[1<<EOF]", "a[1<<EOF]=5"):
            command = f"{first}\ngh issue comment 1 --body 'unsigned'\nEOF\n"
            with self.subTest(first):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_later_stdin_redirect_overrides_the_heredoc(self):
        signed = self.good.rstrip("\n")
        command = f"gh issue comment 1 -F - <<'EOF' <unsigned.txt\n{signed}\nEOF\n"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_grouped_short_flags_do_not_hide_the_body(self):
        for command in (
            "gh pr close 1 -dc 'unsigned'",
            "gh pr review 1 -ab 'unsigned'",
            "gh pr create -db 'unsigned' -t t",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_shell_syntax_that_looks_like_a_heredoc_hides_no_post(self):
        for first in (
            "a=x[ # ] <<EOF",
            "echo ${x:-$'\\''} '}<<EOF' # '",
            'echo "${x:-"<<EOF"}"',
        ):
            command = f"{first}\ngh pr comment 1 --body 'unsigned'\nEOF\n"
            with self.subTest(first):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_redirection_before_the_body_flag_does_not_end_the_arguments(self):
        for command in (
            "gh pr comment 1 >/dev/null --body 'unsigned'",
            "gh pr comment 1 2>&1 --body 'unsigned'",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_heredoc_after_an_operator_run_is_counted(self):
        signed = self.good.rstrip("\n")
        command = f"true;<<A; gh pr comment 1 --body-file - <<B\n{signed}\nA\nunsigned body\nB\n"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_here_string_is_not_read_as_a_heredoc(self):
        command = "cat <<<x\ngh pr comment 1 --body 'unsigned'\nx\n"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)
        signed = self.good.rstrip("\n")
        command = f"cat <<<x; gh pr comment 1 -F - <<'EOF'\n{signed}\nEOF\n"
        # Not an accepted form (DECISIONS: the posting hook reads an allow-list), so blocked.
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_the_accepted_forms_pass_when_signed(self):
        (self.dir / "body.md").write_text(self.good)
        body = self.good.rstrip("\n")
        for command in (
            "gh pr comment 3 --body " + shlex.quote(self.good),
            'gh pr comment 3 --body "' + body + '"',
            "gh pr edit 3 --body-file body.md",
            "gh issue close 3 --comment " + shlex.quote(self.good),
            "gh -R owner/repo pr comment 3 -b " + shlex.quote(self.good),
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_signed_heredoc_body_is_blocked_and_pointed_at_body_file(self):
        # The heredoc form is not accepted (DECISIONS: the posting hook reads an allow-list).
        body = self.good.rstrip("\n")
        command = f"gh pr create --title T --body \"$(cat <<'EOF'\n{body}\nEOF\n)\""
        result = self.hook(self.bash(command))
        self.assertEqual(result.returncode, 2)
        self.assertIn("--body-file signed.md", result.stderr)

    def test_any_other_shape_of_post_is_blocked_and_told_the_forms(self):
        for command in (
            "GH_REPO=o/r gh pr comment 3 --body " + shlex.quote(self.good),
            "/usr/local/bin/gh pr comment 3 --body " + shlex.quote(self.good),
            "cd sub && gh pr comment 3 --body " + shlex.quote(self.good),
            "gh pr comment 3 --body-file missing.md",
            "gh pr comment 3 --body *.md",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 2)
                self.assertIn("gh is the whole command", result.stderr)

    def test_a_long_value_flag_does_not_hide_the_body(self):
        for command in (
            "gh pr create --title -t --body 'UNSIGNED body'",
            "gh pr edit 5 --title -t --body 'UNSIGNED body'",
            "gh pr create -d=t --body 'UNSIGNED body' --title T",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)
        command = "gh pr create --title '-bump deps' --body " + shlex.quote(self.good)
        self.assertEqual(self.hook(self.bash(command)).returncode, 0)

    def test_a_delimiter_line_inside_the_heredoc_body_ends_it(self):
        signed = prose.sign("Hello\nEOF\necho INJECTED unsigned\n").rstrip("\n")
        command = f"gh pr comment 5 --body \"$(cat <<'EOF'\n{signed}\nEOF\n)\""
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_typed_placeholder_is_never_read_as_a_heredoc(self):
        body = self.good.rstrip("\n")
        for command in (
            f"gh pr comment 5 --body \"$(cat <<'EOF'\n{body}\nEOF\n)\" --body __PROSE_HEREDOC_0__",
            "gh pr comment 5 --body __PROSE_HEREDOC_0__",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_an_unbalanced_paren_in_a_heredoc_body_is_not_trusted(self):
        signed = prose.sign('Done)"; echo INJECTED; echo "(\n').rstrip("\n")
        command = f"gh pr comment 5 --body \"$(cat <<'EOF'\n{signed}\nEOF\n)\""
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_quoted_tilde_path_is_read_literally(self):
        home = self.dir / "home"
        home.mkdir()
        (home / "body.md").write_text(self.good)
        (self.dir / "~").mkdir()
        (self.dir / "~" / "body.md").write_text("UNSIGNED\n")
        payload = self.bash("gh pr comment 5 --body-file '~/body.md'")
        env = dict(os.environ, HOME=str(home))
        result = run(["sh", str(POST_HOOK), "--host", "claude"], stdin=json.dumps(payload), env=env)
        self.assertEqual(result.returncode, 2)

    def test_flags_that_source_a_body_elsewhere_are_blocked(self):
        for command in (
            "gh pr create --fill",
            "gh pr create -f",
            "gh pr create -t x --fill-verbose",
            "gh pr create --recover state.json",
            "gh issue create -t x --recover state.json",
            "gh pr create -t x -T bug_report",
            "gh pr comment 1 -e",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)
        for command in ("gh pr close 1", "gh pr review 1 --approve"):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 0)

    def test_a_heredoc_body_bash_3_would_cut_or_join_is_not_trusted(self):
        for text in (
            "'(' x.# )\" --body 'UNSIGNED' ; : \"\nharmless words\n",
            "# x \\\n(\nmore\n",
            "Run:\n    make build \\\n      FLAGS=1\n",
        ):
            signed = prose.sign(text).rstrip("\n")
            command = f"gh pr comment 1 --body \"$(cat <<'EOF'\n{signed}\nEOF\n)\""
            with self.subTest(text):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_word_zsh_would_expand_is_not_read(self):
        (self.dir / "=notes").write_text(self.good)
        self.assertEqual(self.hook(self.bash("gh pr comment 1 --body-file =notes")).returncode, 2)

    def test_a_heredoc_body_with_ansi_c_or_locale_quoting_is_not_trusted(self):
        for text in ("Split on tabs with IFS=$'\\t' here.\n", 'Say $"hello" here.\n'):
            signed = prose.sign(text).rstrip("\n")
            command = f"gh pr comment 1 --body \"$(cat <<'EOF'\n{signed}\nEOF\n)\""
            with self.subTest(text):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_an_empty_quoted_prefix_does_not_hide_a_zsh_equals_word(self):
        (self.dir / "=post").write_text(self.good)
        self.assertEqual(self.hook(self.bash("gh pr comment 1 --body-file ''=post")).returncode, 2)

    def test_an_unreadable_payload_fails_open(self):
        self.assertEqual(self.hook("not json gh").returncode, 0)

    def test_cursor_gets_json_either_way(self):
        allow = self.hook({"command": "ls", "cwd": str(self.dir)}, host="cursor")
        self.assertEqual(json.loads(allow.stdout), {"permission": "allow"})
        deny = self.hook({"tool_name": "add_issue_comment", "mcp_server_name": "github",
                          "tool_input": json.dumps({"body": "x"})}, host="cursor")
        self.assertEqual(deny.returncode, 0)
        self.assertEqual(json.loads(deny.stdout)["permission"], "deny")
        passing = self.hook({"command": "gh pr view 3", "cwd": str(self.dir)}, host="cursor")
        self.assertEqual(json.loads(passing.stdout), {"permission": "allow"})

    def test_a_command_that_only_mentions_a_gh_post_passes(self):
        for command in (
            # A script whose text names a gh post, as data, in a quoted heredoc.
            "python3 - <<'EOF'\n# then run gh issue edit 5 --add-label x\n"
            "open('notes.md', 'w').write('Claim it with `gh issue edit 5 --add-label claimed`.')\nEOF\n",
            "cat > notes.md <<'EOF'\nrun gh pr create, it's easy\nEOF",
            "cat > notes.md <<-EOF\n\tgh pr comment 1 --body 'x'\n\tEOF\necho done",
            'grep -rn "gh pr create" .',
            "git commit -m 'docs: explain gh issue comment' && git push",
            "ls # later: gh pr create --fill",
            "python3 /x/prose.py sign --goals 'gh pr create' && echo ok",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_gh_command_that_posts_no_prose_passes_in_a_compound_command(self):
        for command in (
            "cd /tmp && gh issue edit 12 --add-label claimed",
            "gh issue edit 12 --add-label claimed 2>&1",
            "gh issue edit 12 --add-label claimed --remove-label ready && gh issue view 12",
            "gh pr ready 3 && gh pr edit 3 --add-reviewer x --milestone v1 >/dev/null",
            "gh issue close 3; gh issue reopen 4",
            "(cd sub && gh pr edit 3 --add-assignee @me)",
            "git push -u origin HEAD\ngh pr edit 3 --remove-label wip",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_post_in_a_compound_command_is_still_blocked(self):
        (self.dir / "body.md").write_text(self.good)
        for command in (
            "cd /tmp && gh issue edit 12 --add-label x --body 'unsigned'",
            "gh issue edit 12 --add-label x && gh issue comment 12 --body 'unsigned'",
            "gh issue comment 1 --body 'unsigned' 2>&1",
            "cd sub && gh pr comment 3 --body-file body.md",
            "gh issue edit 12 --add-label x < body.md",
            "cat body.md | gh issue edit 12 --add-label x",
            "cat > a.md <<'EOF'\ngh pr create\nEOF\ngh pr comment 1 --body 'unsigned'",
            "python3 - <<'EOF' && gh pr comment 1 --body 'unsigned'\nprint(1)\nEOF\n",
            "gh --verbose pr comment 1 --body 'unsigned' && true",
            "GH_REPO=o/r gh issue edit 1 --add-label x; true",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_text_a_shell_would_run_is_not_read_as_data(self):
        for command in (
            "bash <<'EOF'\ngh pr comment 1 --body 'unsigned'\nEOF",
            "sh -c 'gh pr comment 1 --body unsigned'",
            "echo 'gh issue comment 1 --body x' | /bin/bash",
            "eval 'gh pr create --body x'",
            "ssh host 'gh pr comment 1 --body x'",
            "xargs -n1 gh pr comment --body x < list",
            "env gh pr comment 1 --body x",
            "cat <<EOF\n$(gh pr comment 1 --body x)\nEOF",
            "cat <<EOF\n`gh pr comment 1 --body x`\nEOF",
            "cat <<EOF\nend \\\nEOF\ngh pr comment 1 --body x\nEOF",
            "# it's\ngh pr comment 1 --body x\n# '",
            "echo x # ; gh pr comment 1 --body x",
            "cat <<'EOF'\ngh pr comment 1 --body x\n",
            "(cat <<'EOF'\ngh pr create\nEOF\n); gh pr comment 1 --body x",
            "[ -f x ] || gh pr comment 1 --body x",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_text_another_command_may_run_is_not_read_as_data(self):
        for command in (
            "xargs gh <<< 'pr comment 1 --body hi'",
            "xargs gh pr <<'EOF'\ncomment 1 --body hi\nEOF",
            "echo comment 1 --body hi | xargs gh pr # then gh pr comment",
            "trap 'gh pr comment 1 --body hi' EXIT",
            "env -S 'gh pr comment 1 --body hi'",
            "echo 'gh pr comment 1 --body hi' | xargs env -S",
            "echo 'gh pr comment 1 --body hi' |\nsh",
            "echo 'gh pr comment 1 --body hi' | # run it\nsh",
            "echo 'gh pr comment 1 --body hi' | (true; sh)",
            "(sh) <<< 'gh pr comment 1 --body hi'",
            "(sh) <<'EOF'\ngh pr comment 1 --body hi\nEOF",
            'cat <<"E\\OF"\nx\nE\\OF\ngh pr comment 1 --body hi\nEOF',
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_heredoc_body_after_an_open_substitution_is_not_skipped(self):
        # bash and zsh run the $( … ) first and read the heredoc body after
        # its closing line, so the lines below the operator are code.
        for command in (
            "cat <<echo $(\ngh pr comment 1 -b hello\necho\n)\necho",
            'cat <<true >/dev/null "$x" $(\ngh pr comment 1 -b hello\ntrue\n)\ntrue',
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_only_a_single_ascii_digit_before_a_redirection_is_a_descriptor(self):
        # zsh reads `12>` as the argument 12 and a redirection; neither shell
        # reads a non-ASCII digit as a descriptor. Either way gh gets the word.
        for command in (
            "gh pr comment 1 -F 12>/dev/stderr",
            "cd . && gh pr comment 1 -b 12>/dev/stderr",
            "gh pr comment 1 -b ١>/dev/stderr",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_gh_post_split_by_quotes_in_a_longer_command_is_read(self):
        for command in (
            "echo 'gh pr comment' ; gh p''r comment 1 -b hello",
            "gh pr edit 5 --add-label x && gh p''r comment 5 -b hello",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_body_file_path_with_a_nul_byte_is_blocked(self):
        result = self.hook(self.bash("cd /tmp && gh pr comment 5 --body-file 'a\x00b'"))
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_a_command_after_a_reserved_word_is_read_as_that_command(self):
        for command in (
            'if grep -q "gh pr create" README.md; then echo yes; fi',
            "! grep -q 'gh pr create' README.md",
            "time grep -rn 'gh pr create' .",
            "while false; do grep -n 'gh pr create' a.md; done",
            "{ echo 'gh pr create'; echo x; } > notes.md",
            'if [ -n "$x" ]; then gh issue edit 3 --add-label claimed; fi',
            "if gh pr view 3 >/dev/null 2>&1; then gh pr ready 3; "
            "else gh issue edit 3 --add-label blocked; fi",
            "for n in 3 4; do gh issue edit 3 --add-label x; done",
            "{ gh issue edit 3 --add-label x; }",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)
        for command in (
            "if true; then gh pr comment 1 --body x; fi",
            "{ gh pr comment 1 --body x; }",
            "! time gh issue comment 1 --body x",
            "if sh -c 'gh pr comment 1 --body x'; then true; fi",
            # A reserved word alone on a line leaves no command to read.
            "if true\nthen\ngh pr comment 1 --body x\nfi",
            "{\ngh pr comment 1 --body x\n}",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_word_that_only_contains_gh_does_not_name_it(self):
        for command in (
            "make gh-pages && gh issue edit 3 --add-label deployed",
            "npm run deploy:gh-pages && gh issue edit 3 --add-label deployed",
            "chmod +x scripts/gh-post.sh && gh issue edit 3 --add-label x",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_line_continuation_is_not_a_word(self):
        for command in (
            "cd repo && \\\n  grep -rn 'gh pr create' .",
            "cd repo && \\\n  gh issue edit 3 --add-label x",
            "cd repo && gh issue edit 3 \\\n  --add-label a \\\n  --add-label b",
            "git push && gh pr edit 3 \\\n  --add-reviewer alice",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)
        for command in (
            "cd repo && \\\n  gh pr comment 3 --body x",
            "cd repo && gh pr comment 3 \\\n  --body x",
            "cd repo && \\\ngh pr comment 3 --body x",
            # The shell removes the continuation first, so the delimiter is
            # unquoted and the body's $( … ) runs.
            "cat <<\\\nEOF\n$(gh pr comment 3 --body x)\nEOF\n",
            "cat <<E\\\nOF\n$(gh pr comment 3 --body x)\nEOF\n",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_closing_reserved_word_is_no_command_beside_a_pipe(self):
        for command in (
            "if git log --oneline | grep -q 'gh pr create'; then echo found; fi",
            "{ echo '# Notes'; echo 'Run gh pr create'; } | tee notes.md",
            "if grep -q 'gh pr create' a.md < /dev/null; then echo yes; fi",
            "while false; do echo 'gh pr create'; done | cat",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)
        for command in (
            "echo 'gh pr comment 1 --body x' | { sh; }",
            "echo 'gh pr comment 1 --body x' | if true; then sh; fi",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_gh_read_command_naming_a_post_verb_passes_in_a_longer_command(self):
        for command in (
            "cd repo && gh pr list --search 'review-requested:@me'",
            "cd repo && gh issue list --label new",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)
        for command in (
            "cd repo && gh pr -R o/r comment 1 --body x",
            "cd repo && gh pr --repo=o/r comment 1 --body x",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_printf_and_test_may_run_a_subscript_so_their_text_is_not_data(self):
        # bash 4+ evaluates an array subscript in `printf -v` and `test -v`,
        # command substitution included, so the quoted text can run gh.
        for command in (
            "printf -v 'a[$(gh pr comment 1 --body hi)]' x",
            "test -v 'a[$(gh pr comment 1 --body hi)]'",
            "[ -v 'a[$(gh pr comment 1 --body hi)]' ]",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)


class CommitHookBase(unittest.TestCase):
    """A repository with one commit, and the hook's cursor set past it."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("a.py", "x = 1\n")
        self.repo.commit("base\n")
        self.hook()  # sets the cursor, so later runs judge only new commits

    def hook(self, script=COMMIT_HOOK, env=None):
        payload = json.dumps({"cwd": str(self.repo.path)})
        full = dict(os.environ, TMPDIR=tempfile.gettempdir(), **(env or {}))
        return run(["sh", str(script), "--host", "claude"], stdin=payload, env=full)

    def callback(self, sha="HEAD"):
        """commit_trailer_verify, as the library calls it."""
        env = dict(os.environ, PROSE_SCRIPTS=str(HERE))
        return run(["sh", "-c", '. "$0" && commit_trailer_verify "$1" ignored', str(HOOK_REPORT), sha],
                   cwd=self.repo.path, env=env)


class CommitHook(CommitHookBase):
    """prose's commit hook: the shared library's report, and the callback
    prose gives it, called directly by sourcing hook-report.sh. The library
    calling it is tested in CommitHookThroughTheLibrary."""

    def test_a_checked_commit_passes_the_callback(self):
        self.repo.write("README.md", "# Hi\n")
        message = "DOCS(x): add a readme\n"
        self.repo.commit(message, self.repo.trailers(message))
        result = self.callback()
        self.assertEqual((result.returncode, result.stdout), (0, "checked\n"))

    def test_a_commit_without_the_trailer_is_reported(self):
        self.repo.write("README.md", "# Hi\n")
        self.repo.commit("DOCS(x): add a readme\n")
        result = self.hook()
        self.assertEqual(result.returncode, 2)
        self.assertIn("without a Prose: trailer", result.stderr)
        self.assertIn("Prose: ✓ <tree>:<message>", result.stderr)

    def test_an_edited_message_fails_the_callback(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n")
        self.repo.commit("DOCS(x): add a readme, edited\n", trailer)
        result = self.callback()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("mismatch:"), result.stdout)

    def test_a_change_staged_after_the_check_fails_the_callback(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n")
        self.repo.write("b.py", "y = 2\n")
        self.repo.commit("DOCS(x): add a readme\n", trailer)
        result = self.callback()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("tree:"), result.stdout)

    def test_a_skip_value_fails_the_callback(self):
        self.repo.write("README.md", "# Hi\n")
        self.repo.commit("DOCS(x): add a readme\n", "Prose: skipped (no prose)")
        result = self.callback()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("unrecognised:"), result.stdout)

    def test_a_commit_the_callback_cannot_read_exits_3(self):
        self.assertEqual(self.callback("nope").returncode, 3)

    def test_a_cherry_pick_carrying_a_valid_trailer_is_not_reported(self):
        self.repo.git("checkout", "-q", "-b", "side")
        self.repo.write("README.md", "# Hi\n")
        message = "DOCS(x): add a readme\n"
        self.repo.commit(message, self.repo.trailers(message))
        self.repo.git("checkout", "-q", "-")
        self.repo.write("b.py", "y = 2\n")
        self.repo.commit("other\n", self.repo.trailers("other\n"))
        self.hook()
        self.repo.git("cherry-pick", "side")
        result = self.hook()
        self.assertEqual((result.returncode, result.stderr), (0, ""))
class HookReportText(unittest.TestCase):
    def test_the_rejected_trailer_report_names_both_calls(self):
        result = run(["sh", "-c", f'. "{HOOK_REPORT}"; rejected="abc123 mismatch"; '
                                  'commit_trailer_report; printf "%s\\n" "$REPORT"'])
        self.assertIn("--pass", result.stdout)


class CommitHookThroughTheLibrary(CommitHookBase):
    """The hook end to end: the shared library finds each new commit and calls
    prose's commit_trailer_verify, and reports what it returns."""

    def test_a_commit_made_through_the_commit_script_is_quiet(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n")
        made = self.repo.commit_script("DOCS(x): add a readme", "", "--verified-value",
                                       str(VERIFY_STAGED), "Prose", trailer[len("Prose: "):])
        self.assertEqual(made.returncode, 0, made.stderr)
        result = self.hook()
        self.assertEqual((result.returncode, result.stderr), (0, ""))

    def test_an_edited_message_is_reported(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n")
        self.repo.commit("DOCS(x): add a readme, edited\n", trailer)
        result = self.hook()
        self.assertEqual(result.returncode, 2)
        self.assertIn("carry a Prose: trailer that does not hold", result.stderr)
        self.assertIn("DOCS(x): add a readme, edited -- mismatch:", result.stderr)

    def test_a_change_staged_after_the_check_is_reported(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n")
        self.repo.write("b.py", "y = 2\n")
        self.repo.commit("DOCS(x): add a readme\n", trailer)
        result = self.hook()
        self.assertEqual(result.returncode, 2)
        self.assertIn("DOCS(x): add a readme -- tree:", result.stderr)

    def test_a_skip_note_passed_to_the_commit_script_is_reported(self):
        # The commit script runs no verifier for a value starting "skipped";
        # prose has no skip value, so the hook reports the commit.
        self.repo.write("README.md", "# Hi\n")
        made = self.repo.commit_script("DOCS(x): add a readme", "", "--verified-value",
                                       str(VERIFY_STAGED), "Prose", "skipped (no prose)")
        self.assertEqual(made.returncode, 0, made.stderr)
        result = self.hook()
        self.assertEqual(result.returncode, 2)
        self.assertIn("-- unrecognised: Prose: skipped (no prose)", result.stderr)
class CommitScript(unittest.TestCase):
    """The commit path SKILL.md gives: the shared commit script, with prose's
    --verified-value option, alone or beside bug-hunter's."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("a.py", "x = 1\n")
        self.repo.commit("base\n")
        self.base = self.head()

    def head(self):
        return self.repo.git("rev-parse", "HEAD").strip()

    def prose_family(self, trailer):
        return ["--verified-value", str(VERIFY_STAGED), "Prose", trailer[len("Prose: "):]]

    def test_a_checked_commit_lands_and_verifies(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n\nWhy it is needed.\n")
        made = self.repo.commit_script("DOCS(x): add a readme", "Why it is needed.",
                                       *self.prose_family(trailer),
                                       "--co-authored-by", "A <a@example.com>")
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual(self.repo.git("log", "-1", "--format=%(trailers:key=Prose,valueonly)").strip(),
                         trailer[len("Prose: "):])
        verified = self.repo.verify()
        self.assertEqual((verified.returncode, verified.stdout), (0, "checked\n"))

    def test_a_message_signed_from_a_file_commits_from_that_file(self):
        self.repo.write("README.md", "# Hi\n")
        message = "DOCS(x): add a readme\n\nWhy it's needed: \"quotes\", $HOME and `ticks`.\n"
        trailer = self.repo.trailers(message)  # signs the file .msg
        made = run(["sh", str(COMMIT_SCRIPT), *self.prose_family(trailer),
                    "--message-file", ".msg", "--"], cwd=self.repo.path)
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual(self.repo.git("log", "-1", "--format=%s").strip(), "DOCS(x): add a readme")
        verified = self.repo.verify()
        self.assertEqual((verified.returncode, verified.stdout), (0, "checked\n"))

    def test_an_edited_message_is_refused_before_the_commit(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n")
        made = self.repo.commit_script("DOCS(x): add a readme, edited", "", *self.prose_family(trailer))
        self.assertEqual(made.returncode, 1)
        self.assertIn("mismatch:", made.stderr)
        self.assertEqual(self.head(), self.base)

    def test_a_change_staged_after_the_check_is_refused_before_the_commit(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n")
        self.repo.write("b.py", "y = 2\n")
        made = self.repo.commit_script("DOCS(x): add a readme", "", *self.prose_family(trailer))
        self.assertEqual(made.returncode, 1)
        self.assertIn("tree:", made.stderr)
        self.assertEqual(self.head(), self.base)

    def test_it_composes_with_bug_hunter_in_one_commit(self):
        self.repo.write("b.py", "y = 2\n")
        trailer = self.repo.trailers("FIX(x): set y\n")
        made = self.repo.commit_script(
            "FIX(x): set y", "",
            "--minted-by", str(BUG_HUNTER_MINT), "Bug-hunter", "1 iteration, 1 bug fixed",
            *self.prose_family(trailer))
        self.assertEqual(made.returncode, 0, made.stderr)
        trailers = self.repo.git("log", "-1", "--format=%(trailers:only,unfold)").split("\n")
        tree = self.repo.git("rev-parse", "HEAD^{tree}").strip()
        self.assertEqual([t for t in trailers if t], [
            "Bug-hunter: 1 iteration, 1 bug fixed", f"Bug-hunter-Tree: {tree}", trailer])
        self.assertEqual(self.repo.verify().returncode, 0, self.repo.verify().stdout)

    def test_check_with_amend_says_how_to_amend(self):
        self.repo.write("README.md", "# Hi\n")
        self.repo.commit("DOCS(x): add a readme\n")
        self.repo.write("README.md", "# Hello\n")
        result = self.repo.prose("check", "-F", "-", "--goals", "g", "--amend",
                                 stdin="DOCS(x): add a readme\n")
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertNotIn("Commit through the commit script", result.stdout)
        self.assertIn("git commit --amend", result.stdout)

    def test_the_amend_instruction_names_the_file_that_was_checked(self):
        self.repo.write("README.md", "# Hi\n")
        self.repo.commit("DOCS(x): add a readme\n")
        self.repo.write("README.md", "# Hello\n")
        (self.repo.path / "final msg.txt").write_text("DOCS(x): add a readme\n")
        result = self.repo.prose("check", "-F", "final msg.txt", "--goals", "g", "--amend")
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("git commit --amend -F 'final msg.txt' --trailer", result.stdout)
        from_stdin = self.repo.prose("check", "-F", "-", "--goals", "g", "--amend",
                                     stdin="DOCS(x): add a readme\n")
        self.assertNotIn("msg.txt", from_stdin.stdout)
        self.assertIn("-F <a file holding exactly the text checked>", from_stdin.stdout)

    def test_verify_staged_refuses_a_line_that_is_not_a_prose_trailer(self):
        result = run([str(VERIFY_STAGED), "Prose: checked"], cwd=self.repo.path, stdin="Title")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("unrecognised:"), result.stdout)
class PreCommitHook(unittest.TestCase):
    """`prose check` runs the repository's pre-commit hook before it lists or
    signs, through the shared library's run-pre-commit.sh."""

    MESSAGE = "DOCS(x): add a readme\n\nWhy it is needed.\n"

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("a.py", "x = 1\n")
        self.repo.commit("base\n")
        self.base = self.repo.git("rev-parse", "HEAD").strip()
        self.runs = self.repo.path.parent / f"{self.repo.path.name}-hook-runs"
        self.addCleanup(lambda: self.runs.unlink(missing_ok=True))

    def install_hook(self, body):
        """A pre-commit hook that counts its runs, then runs body."""
        hook = self.repo.path / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text(f'#!/bin/sh\necho run >>"{self.runs}"\n{body}')
        hook.chmod(0o755)

    def install_formatter(self):
        """Deletes the spaces in each staged Markdown file and restages it, as
        prettier under lint-staged restages what it rewrites."""
        self.install_hook(
            "for f in $(git diff --cached --name-only --diff-filter=ACM -- '*.md'); do\n"
            '  tr -d " " <"$f" >"$f.tmp" && mv "$f.tmp" "$f" && git add "$f"\n'
            "done\n")

    def hook_runs(self):
        return len(self.runs.read_text().splitlines()) if self.runs.exists() else 0

    def first_call(self, *extra):
        (self.repo.path / ".msg").write_text(self.MESSAGE)
        return self.repo.prose("check", "-F", ".msg", "--goals", "review it", *extra)

    def signing_call(self, first, *extra):
        return self.repo.prose("check", "-F", ".msg", "--pass", pass_token(first.stdout), *extra)

    def commit(self, trailer):
        return self.repo.commit_script(
            "DOCS(x): add a readme", "Why it is needed.",
            "--verified-value", str(VERIFY_STAGED), "Prose", trailer[len("Prose: "):])

    def test_a_restaging_formatter_runs_once_and_the_formatted_tree_lands(self):
        self.install_formatter()
        self.repo.write("README.md", "# Hi there\n")
        first = self.first_call()
        self.assertEqual(first.returncode, 4, first.stderr)
        self.assertIn("the prose below is read from the files as it left them", first.stderr)
        self.assertEqual(self.repo.git("show", ":README.md"), "#Hithere\n")
        signed = self.signing_call(first)
        self.assertEqual(signed.returncode, 0, signed.stderr)
        trailer = block_trailer(signed.stdout)
        self.assertEqual(signed.stdout.count("\n"), 4, signed.stdout)
        made = self.commit(trailer)
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual(self.repo.git("show", "HEAD:README.md"), "#Hithere\n")
        verified = self.repo.verify()
        self.assertEqual((verified.returncode, verified.stdout), (0, "checked\n"))
        self.assertEqual(self.hook_runs(), 1)

    def test_an_edit_between_the_calls_runs_the_hook_again_before_signing(self):
        # The pass rewrites the doc and restages it: the signing call formats
        # and signs the rewrite, and the commit script does not run the hook.
        self.install_formatter()
        self.repo.write("README.md", "# Hi there\n")
        first = self.first_call()
        self.assertEqual(first.returncode, 4, first.stderr)
        self.repo.write("README.md", "# Hello there\n")
        signed = self.signing_call(first)
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.assertIn("the trailer signs the files as it left them", signed.stderr)
        made = self.commit(block_trailer(signed.stdout))
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual(self.repo.git("show", "HEAD:README.md"), "#Hellothere\n")
        self.assertEqual(self.repo.verify().returncode, 0, self.repo.verify().stdout)
        self.assertEqual(self.hook_runs(), 2)

    def test_a_failing_hook_stops_the_first_call_before_any_token(self):
        self.install_hook('echo "lint: README.md is wrong" >&2\nexit 1\n')
        self.repo.write("README.md", "# Hi\n")
        first = self.first_call()
        self.assertEqual(first.returncode, 2, first.stderr)
        self.assertIn("lint: README.md is wrong", first.stderr)
        self.assertIn("run-pre-commit.sh refused", first.stderr)
        self.assertEqual(first.stdout, "")

    def test_a_failing_hook_stops_the_signing_call_with_no_trailer(self):
        self.install_hook("")
        self.repo.write("README.md", "# Hi\n")
        first = self.first_call()
        self.assertEqual(first.returncode, 4, first.stderr)
        # Editing the hook invalidates the recorded pass, so it runs again.
        self.install_hook('echo "lint: README.md is wrong" >&2\nexit 1\n')
        signed = self.signing_call(first)
        self.assertEqual(signed.returncode, 2, signed.stderr)
        self.assertIn("lint: README.md is wrong", signed.stderr)
        self.assertIn("nothing was signed", signed.stderr)
        self.assertEqual(signed.stdout, "")
        # The token is not spent: after the fix, the same token signs.
        self.install_hook("")
        again = self.signing_call(first)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertRegex(block_trailer(again.stdout), TRAILER)

    def test_with_no_hook_nothing_is_run_or_printed(self):
        self.repo.write("README.md", "# Hi there\n")
        first = self.first_call()
        self.assertEqual((first.returncode, first.stderr), (4, ""))
        signed = self.signing_call(first)
        self.assertEqual((signed.returncode, signed.stderr), (0, ""))
        self.assertEqual(signed.stdout.count("\n"), 4, signed.stdout)
        record = self.repo.git("rev-parse", "--git-path", "commit-trailer").strip()
        self.assertFalse((self.repo.path / record).exists())

    def test_with_amend_the_hook_runs_and_the_amend_keeps_the_signature(self):
        # `git commit --amend` runs the hook again; a formatter that already
        # ran changes nothing the second time.
        self.install_formatter()
        self.repo.write("README.md", "# Hi\n")
        self.repo.commit(self.MESSAGE)
        self.repo.write("README.md", "# Hi there\n")
        first = self.first_call("--amend")
        self.assertEqual(first.returncode, 4, first.stderr)
        signed = self.signing_call(first, "--amend")
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.repo.git("commit", "-q", "--amend", "-F", ".msg",
                      "--trailer", block_trailer(signed.stdout))
        self.assertEqual(self.repo.git("show", "HEAD:README.md"), "#Hithere\n")
        self.assertEqual(self.repo.verify().returncode, 0, self.repo.verify().stdout)


class PassToken(unittest.TestCase):
    """The first call prints the rules and a pass token; the signing call
    spends the token (DECISIONS: The rules are on screen before a signature)."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("README.md", "# Hi\n")

    def first(self, message="DOCS(x): add a readme\n", goals="review it"):
        return self.repo.prose("check", "-F", "-", "--goals", goals, stdin=message)

    def signing(self, token, message="DOCS(x): add a readme\n", *extra):
        return self.repo.prose("check", "-F", "-", "--pass", token, *extra, stdin=message)

    def test_the_first_call_prints_goals_listing_rules_and_a_token_but_no_trailer(self):
        result = self.first()
        self.assertEqual(result.returncode, 4, result.stderr)
        out = result.stdout
        self.assertNotRegex(out, "(?m)^Prose: ")
        self.assertNotIn("=== prose result ===", out)
        token = pass_token(out)
        order = [out.index(text) for text in ("Reader goals", "README.md  (changed)",
                                              "## The pass", "### 5. ", "## How agents cheat",
                                              "Pass token:", f"--pass {token}")]
        self.assertEqual(order, sorted(order))

    def test_the_signing_call_signs_a_commit_that_verifies(self):
        token = pass_token(self.first().stdout)
        result = self.signing(token)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("## The pass", result.stdout)
        self.repo.commit("DOCS(x): add a readme\n", block_trailer(result.stdout))
        self.assertEqual(self.repo.verify().stdout, "checked\n")

    def test_the_text_may_change_between_the_calls(self):
        token = pass_token(self.first(message="DOCS(x): draft\n").stdout)
        self.repo.write("README.md", "# Hello, rewritten\n")
        result = self.signing(token, "DOCS(x): add a readme\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_token_signs_once(self):
        token = pass_token(self.first().stdout)
        self.assertEqual(self.signing(token).returncode, 0)
        again = self.signing(token)
        self.assertEqual((again.returncode, again.stdout), (2, ""))
        self.assertIn("already used", again.stderr)
        self.assertIn("--goals in place of --pass", again.stderr)

    def test_an_unknown_or_malformed_token_is_refused(self):
        for token in ("0123456789abcdef", "../../../etc/pas", "", "ABC"):
            with self.subTest(token=token):
                result = self.signing(token) if token else self.repo.prose(
                    "check", "-F", "-", "--pass", "", stdin="DOCS(x): a\n")
                self.assertEqual((result.returncode, result.stdout), (2, ""))

    def test_an_expired_token_is_refused_and_deleted(self):
        token = prose.issue_pass(["review it"], "check", "", self.repo.path)
        path = prose.pass_dir(self.repo.path) / token
        path.write_text(json.dumps({"goals": ["review it"], "kind": "check",
                                    "issued": prose.time.time() - prose.PASS_LIFETIME - 1}))
        result = self.signing(token)
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("expired", result.stderr)
        self.assertFalse(path.exists())

    def test_other_goals_are_refused_and_the_token_survives(self):
        token = pass_token(self.first(goals="review it").stdout)
        refused = self.signing(token, "DOCS(x): add a readme\n", "--goals", "something else")
        self.assertEqual((refused.returncode, refused.stdout), (2, ""))
        self.assertIn("differ", refused.stderr)
        same = self.signing(token, "DOCS(x): add a readme\n", "--goals", " review it ")
        self.assertEqual(same.returncode, 0, same.stderr)

    def test_a_refused_signing_call_keeps_the_token(self):
        token = pass_token(self.first().stdout)
        refused = self.signing(token, "Subj\n\n#12 is fixed.\n")
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(self.signing(token).returncode, 0)

    def test_sign_first_call_prints_to_stderr_and_signs_nothing(self):
        first = run([sys.executable, str(SCRIPT), "sign", "--goals", "approve it"],
                    cwd=self.repo.path, stdin="Text.\n")
        self.assertEqual((first.returncode, first.stdout), (4, ""))
        self.assertIn("## The pass", first.stderr)
        token = pass_token(first.stderr)
        self.assertIn(f"sign --pass {token} < body.md > signed.md", first.stderr)
        signed = run([sys.executable, str(SCRIPT), "sign", "--pass", token],
                     cwd=self.repo.path, stdin="Text.\n")
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.assertNotIn("## The pass", signed.stderr)
        self.assertEqual(prose.verify_post(signed.stdout), (True, "signed"))

    def test_start_needs_goals_prints_the_rules_and_issues_no_token(self):
        refused = self.repo.prose("start")
        self.assertEqual((refused.returncode, refused.stdout), (2, ""))
        started = self.repo.prose("start", "--goals", "review it")
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertIn("## The pass", started.stdout)
        self.assertNotIn("Pass token", started.stdout)
        self.assertIn("check -F msg.txt --goals", started.stdout)
        self.assertFalse((self.repo.path / ".git" / "prose").exists())

    def test_start_refuses_a_pass_token(self):
        # start redeems nothing, so a token given to it is a mistake to report.
        result = self.repo.prose("start", "--goals", "review it", "--pass", "abc")
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("--pass", result.stderr)

    def test_a_commit_token_cannot_sign_a_post_nor_a_post_token_a_commit(self):
        commit_token = pass_token(self.first().stdout)
        post = self.repo.prose("sign", "--pass", commit_token, stdin="Text.\n")
        self.assertEqual((post.returncode, post.stdout), (2, ""))
        self.assertIn("issued for a commit, not a post", post.stderr)
        self.assertEqual(self.signing(commit_token).returncode, 0)
        post_token = pass_token(self.repo.prose("sign", "--goals", "approve it", stdin="").stderr)
        commit = self.signing(post_token)
        self.assertEqual((commit.returncode, commit.stdout), (2, ""))
        self.assertIn("issued for a post, not a commit", commit.stderr)

    def test_two_texts_in_one_session_each_need_their_own_first_call(self):
        token = pass_token(self.first().stdout)
        self.assertEqual(self.signing(token).returncode, 0)
        self.repo.commit("DOCS(x): add a readme\n")
        self.repo.write("README.md", "# Hello\n")
        second = self.signing(token, "DOCS(x): reword the readme\n")
        self.assertEqual((second.returncode, second.stdout), (2, ""))
        own = pass_token(self.first(message="DOCS(x): reword the readme\n", goals="see the new title").stdout)
        self.assertEqual(self.signing(own, "DOCS(x): reword the readme\n").returncode, 0)

    def test_the_token_lives_in_the_git_directory_and_never_shows_in_status(self):
        token = pass_token(self.first().stdout)
        self.assertTrue((self.repo.path / ".git" / "prose" / "passes" / token).is_file())
        self.assertNotIn("prose", self.repo.git("status", "--porcelain", "--ignored"))

    def test_outside_a_repository_the_token_lives_in_the_state_home(self):
        outside = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        state = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, state, True)
        env = dict(os.environ, XDG_STATE_HOME=str(state), GIT_CEILING_DIRECTORIES=str(outside.parent))
        first = run([sys.executable, str(SCRIPT), "sign", "--goals", "g"], cwd=outside, stdin="", env=env)
        token = pass_token(first.stderr)
        self.assertTrue((state / "prose" / "passes" / token).is_file())
        signed = run([sys.executable, str(SCRIPT), "sign", "--pass", token], cwd=outside,
                     stdin="Text.\n", env=env)
        self.assertEqual(signed.returncode, 0, signed.stderr)

    def test_concurrent_first_calls_each_get_a_token_that_signs(self):
        # sign, not check: concurrent checks already collide on git's index
        # lock (write-tree), before any token is issued.
        calls = [subprocess.Popen([sys.executable, str(SCRIPT), "sign", "--goals", "g"],
                                  cwd=self.repo.path, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
                 for _ in range(8)]
        tokens = [pass_token(call.communicate()[1]) for call in calls]
        self.assertEqual(len(set(tokens)), 8)
        for token in tokens:
            self.assertTrue((self.repo.path / ".git" / "prose" / "passes" / token).is_file())
            signed = self.repo.prose("sign", "--pass", token, stdin="Text.\n")
            self.assertEqual(signed.returncode, 0, signed.stderr)

    def test_the_first_call_marks_its_session(self):
        state = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, state, True)
        env = dict(os.environ, XDG_STATE_HOME=str(state), CLAUDE_CODE_SESSION_ID="from-env")
        run([sys.executable, str(SCRIPT), "start", "--goals", "g"], cwd=self.repo.path, env=env)
        run([sys.executable, str(SCRIPT), "start", "--goals", "g", "--session", "from-flag"],
            cwd=self.repo.path, env=env)
        self.assertEqual(sorted(p.name for p in (state / "prose" / "sessions").iterdir()),
                         ["from-env", "from-flag"])


class Gate(unittest.TestCase):
    """The hook that blocks a session's first file write or post until a first call ran."""

    def setUp(self):
        self.state = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state, True)
        self.env = dict(os.environ, XDG_STATE_HOME=str(self.state / "missing" / "state"))

    def gate(self, tool, tool_input, session="s-1", env=None, cwd=None):
        payload = {"session_id": session, "hook_event_name": "PreToolUse", "cwd": str(cwd or self.state),
                   "tool_name": tool, "tool_input": tool_input}
        return run(["/bin/sh", str(GATE), "--host", "claude"], stdin=json.dumps(payload),
                   env=env or self.env)

    def start(self, *extra, env=None):
        result = run([sys.executable, str(SCRIPT), "start", "--goals", "g", *extra],
                     cwd=self.state, env=env or self.env)
        self.assertEqual(result.returncode, 0, result.stderr)

    def assertBlocked(self, result, what):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(what, result.stderr)
        self.assertIn("start --goals", result.stderr)

    def assertAllowed(self, result):
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_a_write_without_a_path_key_still_reaches_the_gate(self):
        # The wrapper skips only Bash commands that name no gh; every other
        # matched tool goes to prose.py, whatever its input's keys are called.
        for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            with self.subTest(tool):
                self.assertBlocked(self.gate(tool, {"path": "/w/a.md", "content": "x"}), f"this {tool}")
        self.assertAllowed(self.gate("Bash", {"command": "ls"}))

    def test_it_blocks_the_first_file_edit_until_a_first_call_then_stays_silent(self):
        edit = {"file_path": "/w/docs/guide.md", "old_string": "a", "new_string": "b"}
        blocked = self.gate("Edit", edit)
        self.assertBlocked(blocked, "this Edit of /w/docs/guide.md")
        self.assertIn("--session s-1", blocked.stderr)
        self.start("--session", "s-1")
        self.assertAllowed(self.gate("Edit", edit))
        self.assertAllowed(self.gate("Write", {"file_path": "/w/README", "content": "x"}))
        self.assertBlocked(self.gate("Edit", edit, session="s-2"), "guide.md")

    def test_the_session_id_from_the_environment_opens_it(self):
        self.start(env=dict(self.env, CLAUDE_CODE_SESSION_ID="s-1"))
        self.assertAllowed(self.gate("Write", {"file_path": "/w/openspec/x/spec.yaml", "content": "k: v"}))

    def test_an_edit_that_is_neither_a_doc_nor_a_comment_is_blocked(self):
        self.assertBlocked(self.gate("Edit", {"file_path": "/w/a.py", "old_string": "x = 1",
                                              "new_string": "x = 2"}), "this Edit of /w/a.py")

    def test_a_write_to_any_path_is_blocked(self):
        for tool, tool_input in (
                ("Write", {"file_path": "/w/data.json", "content": "{}"}),
                ("Write", {"file_path": "/w/node_modules/d/README.md", "content": "x"}),
                ("Write", {"file_path": "/w/build/out/a.py", "content": "x = 1\n"}),
                ("Write", {"file_path": "rel/Dockerfile", "content": "FROM alpine\n"}),
                ("MultiEdit", {"file_path": "/w/a.ts", "edits": [{"old_string": "a", "new_string": "b"}]}),
                ("NotebookEdit", {"notebook_path": "/w/n.ipynb", "cell_type": "code", "new_source": "x = 1"}),
                ("NotebookEdit", {"notebook_path": "/w/n.ipynb", "edit_mode": "delete", "cell_id": "c1"})):
            with self.subTest(tool=tool, path=tool_input.get("file_path") or tool_input.get("notebook_path")):
                path = tool_input.get("file_path") or tool_input.get("notebook_path")
                self.assertBlocked(self.gate(tool, tool_input), f"this {tool} of {path}")

    def test_after_start_every_call_passes(self):
        self.start("--session", "s-1")
        for tool, tool_input in (
                ("Write", {"file_path": "/w/data.json", "content": "{}"}),
                ("Edit", {"file_path": "/w/a.py", "old_string": "x", "new_string": "# why\nx"}),
                ("MultiEdit", {"file_path": "/w/a.ts", "edits": [{"old_string": "a", "new_string": "b"}]}),
                ("NotebookEdit", {"notebook_path": "/w/n.ipynb", "cell_type": "markdown", "new_source": "# N"}),
                ("Bash", {"command": "gh pr create --body-file signed.md"}),
                ("mcp__github__add_issue_comment", {"body": "Hi."})):
            with self.subTest(tool):
                self.assertAllowed(self.gate(tool, tool_input))

    def test_tools_that_write_nothing_pass(self):
        self.assertAllowed(self.gate("Read", {"file_path": "/w/README.md"}))
        self.assertAllowed(self.gate("Grep", {"pattern": "x", "path": "/w"}))

    def test_it_blocks_a_gh_post_but_not_other_commands(self):
        self.assertBlocked(self.gate("Bash", {"command": "gh pr create --body-file signed.md"}),
                           "this gh post")
        self.assertBlocked(self.gate("mcp__github__add_issue_comment", {"body": "Hi."}), "mcp__github__")
        for command in ("ls", "gh pr view 3", "git commit -m x",
                        "cd /tmp && gh issue edit 1 --add-label y",
                        "cat > a.md <<'EOF'\nrun gh pr create\nEOF"):
            with self.subTest(command):
                self.assertAllowed(self.gate("Bash", {"command": command}))
        self.assertAllowed(self.gate("mcp__github__get_pull_request", {"pullNumber": 3}))

    def test_it_does_not_block_its_own_start_command(self):
        command = "python3 /x/prose.py start --goals 'review the gh pr create flow' --session s"
        self.assertAllowed(self.gate("Bash", {"command": command}))
        self.assertBlocked(self.gate("Bash", {"command": "python3 /x/prose.py start --goals g | gh pr create --body x"}),
                           "this gh post")

    def test_the_block_message_does_not_promise_a_token_from_start(self):
        blocked = self.gate("Write", {"file_path": "/w/README.md", "content": "x"})
        self.assertNotIn("pass token", blocked.stderr)

    def test_a_marked_session_does_not_read_the_file(self):
        self.start("--session", "s-1")
        fifo = self.state / "big.py"
        os.mkfifo(fifo)
        payload = {"session_id": "s-1", "cwd": str(self.state), "tool_name": "Edit",
                   "tool_input": {"file_path": str(fifo), "old_string": "a", "new_string": "# b"}}
        try:
            # Reading a FIFO with no writer blocks, so a gate that reads the
            # file before checking the session times out here.
            result = subprocess.run([sys.executable, str(SCRIPT), "hook-gate"], input=json.dumps(payload),
                                    capture_output=True, text=True, env=self.env, timeout=10)
        except subprocess.TimeoutExpired:
            self.fail("the gate read the file in a session whose first call already ran")
        self.assertEqual(result.returncode, 0, result.stderr)


    def test_it_fails_open(self):
        edit = {"file_path": "/w/README.md", "old_string": "a", "new_string": "b"}
        not_a_dir = self.state / "file"
        not_a_dir.write_text("")
        self.assertAllowed(self.gate("Edit", edit, env=dict(self.env, XDG_STATE_HOME=str(not_a_dir))))
        bin_dir = self.state / "bin"
        bin_dir.mkdir()
        for tool in ("cat", "dirname"):
            os.symlink(shutil.which(tool), bin_dir / tool)
        self.assertAllowed(self.gate("Edit", edit, env=dict(self.env, PATH=str(bin_dir))))
        for raw in ("not json", "[]", json.dumps({"tool_name": "Edit", "tool_input": edit})):
            with self.subTest(raw):
                self.assertAllowed(run(["/bin/sh", str(GATE)], stdin=raw, env=self.env))

    def test_it_fails_open_on_an_unreadable_state_directory(self):
        if os.geteuid() == 0:
            self.skipTest("root reads any directory")
        sessions = self.state / "home" / "prose" / "sessions"
        sessions.mkdir(parents=True)
        sessions.chmod(0)
        self.addCleanup(sessions.chmod, 0o700)
        env = dict(self.env, XDG_STATE_HOME=str(self.state / "home"))
        self.assertAllowed(self.gate("Edit", {"file_path": "/w/README.md", "old_string": "a",
                                              "new_string": "b"}, env=env))


class ResultBlock(unittest.TestCase):
    def test_a_missing_library_stops_the_check_before_any_output(self):
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        scripts = root / "skills" / "prose" / "scripts"
        scripts.mkdir(parents=True)
        for name in ("prose.py", "comment_scan.py"):
            shutil.copy(HERE / name, scripts / name)
        shutil.copy(HERE.parent / "rules.md", scripts.parent / "rules.md")
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("a.py", "x = 1\n")
        for extra in (["--goals", "g"], ["--pass", prose.issue_pass(["g"], "check", "", repo.path)]):
            with self.subTest(extra=extra):
                result = run([sys.executable, str(scripts / "prose.py"), "check", "-F", "-",
                              *extra], cwd=repo.path, stdin="Title\n")
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("commit-trailer library is missing", result.stderr)
    def test_a_failing_result_block_leaves_the_token_unspent(self):
        # Only a printed trailer spends the token: if the result block cannot
        # be printed, the same signing call can run again.
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        scripts = root / "skills" / "prose" / "scripts"
        scripts.mkdir(parents=True)
        for name in ("prose.py", "comment_scan.py"):
            shutil.copy(HERE / name, scripts / name)
        shutil.copy(HERE.parent / "rules.md", scripts.parent / "rules.md")
        lib = root / "lib" / "commit-trailer"
        shutil.copytree(HERE.parent.parent.parent / "lib" / "commit-trailer", lib)
        (lib / "result-block.sh").write_text("#!/bin/sh\necho 'result block failed' >&2\nexit 1\n")
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("a.py", "x = 1\n")
        token = prose.issue_pass(["g"], "check", "", repo.path)
        result = run([sys.executable, str(scripts / "prose.py"), "check", "-F", "-", "--pass", token],
                     cwd=repo.path, stdin="Title\n")
        self.assertEqual((result.returncode, result.stdout), (2, ""), result.stderr)
        self.assertIn("result block failed", result.stderr)
        self.assertTrue((prose.pass_dir(repo.path) / token).exists(), "the token was spent")


if __name__ == "__main__":
    unittest.main(verbosity=2)

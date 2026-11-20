#!/usr/bin/env python3
"""Tests for prose.py's check and sign: the rules file, what `prose check`
lists and prints, the signature a commit trailer or a post footer carries,
the pass token, and the repository's own pre-commit hook, which
`prose check` runs first.

Standard library only:

    python3 test_check.py

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
import shutil
import subprocess
import sys
import tempfile
import unittest

from prose_test_support import (
    ALL_FILES,
    BUG_HUNTER_MINT,
    HERE,
    Repo,
    SCRIPT,
    STATE,
    TRAILER,
    VERIFY_STAGED,
    block_trailer,
    cold_read,
    pass_token,
    prose,
    run,
    straight_report,
)


class RulesFile(unittest.TestCase):
    """read_rules parses rules.md by its headings and refuses a broken file."""

    GOOD = ("# Title\n\nPrinciple.\n\n## Scope\n\nS.\n\n## The pass\n\nP.\n\n"
            "## The rules, most important first\n\n"
            + "".join(f"### {n}. Rule {n}\nBody {n}.\n\n" for n in range(1, 10))
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
        self.assertEqual([(n, t) for n, t, _ in rules], [(n, f"Rule {n}") for n in range(1, 10)])
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
        # The staged doc was read cold, with nothing found.
        self.assertEqual(trailer, f"Prose: \u2713 {tree[:12]}:{prose.message_hash(message)}"
                                  "; cold read: no findings; understood: 1 item, 0 fixed, 0 kept")
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
        # valid value is the `✓ <tree>:<message>` snapshot.
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
        # Only vendored directories exempt docs.
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
        self.assertIn("a sentence lengthened to read once beats a shorter one read twice", out)
        self.assertIn("  [ ] 10. Say who acts", out)
        self.assertIn("  [ ] 14. Commit subject says what changed; the body says why", out)
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

    def test_a_yaml_files_prose_strings_are_listed_beside_its_comments(self):
        self.repo.write("rules.yaml", "# How to merge.\nrules:\n  proposal:\n"
                        "    - Read the decision record before proposing an approach.\n"
                        "name: ci\n")
        result = self.check_for()
        self.assertEqual(result.returncode, 4, result.stderr)
        listing = self.listing(result.stdout)
        self.assertIn("rules.yaml:1  (comment)", listing)
        self.assertIn("rules.yaml:3-4  (prose strings)", listing)
        heading, goals = self.goals_by_item(result.stdout)["rules.yaml:3-4"]
        self.assertIn("from the 'YAML prose string' row of rules.md's reader table", heading)
        self.assertEqual(goals, ["what to do", "when it applies"])

    def test_a_yaml_change_outside_any_prose_string_lists_none(self):
        self.repo.write("ci.yml", "name: ci\nrun: npm ci\n")
        self.repo.commit("base 2\n")
        self.repo.write("ci.yml", "name: ci\nrun: npm ci --silent\nnote: Runs the suite on "
                        "every push to main.\n")
        self.repo.commit("base 3\n")
        self.repo.write("ci.yml", "name: ci\nrun: npm test\nnote: Runs the suite on "
                        "every push to main.\n")
        self.assertNotIn("ci.yml", self.listing(self.check_for().stdout))

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
        sign = lambda *extra: cold_read(lambda *cold: self.repo.prose(
            "check", "-F", "-", "--pass", token, *cold, *extra, stdin="FEAT(x): a\n",
            file_goals=False))
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
        signed = cold_read(lambda *cold: self.repo.prose(
            "check", "-F", "-", "--goals", "review the fix", "--goals-for", "README.md", "two",
            "--goals-for", "docs/**", "one", "--pass", pass_token(first.stdout), *cold,
            stdin="FEAT(x): a\n", file_goals=False))
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
        self.assertIn("### 8. What is, not how it got here", out)
        self.assertIn("A narrow role's unused", out)
        self.assertIn("Labelling the past does not make it worth keeping", out)
        self.assertIn("Keeping context a reviewer needed in a document whose reader never will", out)

    def test_the_rules_print_a_hypothetical_in_full(self):
        out = self.check().stdout
        self.assertIn("### 4. A hypothetical reads as one", out)
        self.assertIn("### 5. Say when, and whether", out)
        self.assertIn("**Put its consequences in \"would\" or \"might\".**", out)
        self.assertIn("adding \"if\" and leaving its consequences in the plain present", out)
        self.assertIn("Answering `matches` to an understood line", out)

    def test_the_rules_ask_for_a_reason_instead_of_a_catchphrase(self):
        out = self.check().stdout
        self.assertIn("### 7. Plain words, and reasons instead of catchphrases", out)
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
        token = pass_token(result.stdout)
        signed = cold_read(lambda *cold: self.repo.prose("check", "-F", "-", "--pass", token,
                                                         *cold, stdin="FEAT(x): a\n"))
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
    token = pass_token(first.stderr)
    return cold_read(lambda *cold: run([sys.executable, str(SCRIPT), "sign", "--pass", token,
                                        *cold], cwd=STATE, stdin=text))


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
        token = pass_token(first.stdout)
        return cold_read(lambda *cold: self.repo.prose("check", "-F", ".msg", "--pass", token,
                                                       *cold, *extra))

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
        # The signing call's first run asks for a cold read; the hook runs on
        # that run, and the run with the report finds the tree it passed.
        token = pass_token(first.stdout)
        needed = self.repo.prose("check", "-F", ".msg", "--pass", token)
        self.assertEqual(needed.returncode, prose.COLD_READ_NEEDED, needed.stderr)
        self.assertIn("the trailer signs the files as it left them", needed.stderr)
        signed = self.repo.prose("check", "-F", ".msg", "--pass", token,
                                 *straight_report(needed.stdout))
        self.assertEqual(signed.returncode, 0, signed.stderr)
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
    spends the token."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("README.md", "# Hi\n")

    def first(self, message="DOCS(x): add a readme\n", goals="review it"):
        return self.repo.prose("check", "-F", "-", "--goals", goals, stdin=message)

    def signing(self, token, message="DOCS(x): add a readme\n", *extra):
        return cold_read(lambda *cold: self.repo.prose("check", "-F", "-", "--pass", token,
                                                       *cold, *extra, stdin=message))

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
        signed = cold_read(lambda *cold: run([sys.executable, str(SCRIPT), "sign", "--pass", token,
                                              *cold], cwd=self.repo.path, stdin="Text.\n"))
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.assertNotIn("## The pass", signed.stderr)
        self.assertEqual(prose.verify_post(signed.stdout), (True, "signed"))

    def goals_file(self, text):
        """A goals file holding text, beside the repository rather than in it,
        so that it never becomes part of the change prose lists."""
        path = self.repo.path.parent / f"{self.repo.path.name}-goals.txt"
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
        return str(path)

    def test_sign_takes_its_goals_from_a_file(self):
        goals = self.goals_file("# the reviewer\n\napprove it; check it's safe\n  see what's left\n")
        first = self.repo.prose("sign", "--goals-file", goals)
        self.assertEqual((first.returncode, first.stdout), (4, ""), first.stderr)
        self.assertIn("1. approve it\n  2. check it's safe\n  3. see what's left\n", first.stderr)
        token = pass_token(first.stderr)
        record = json.loads((prose.pass_dir(self.repo.path) / token).read_text())
        self.assertEqual(record["goals"], ["approve it", "check it's safe", "see what's left"])
        signed = cold_read(lambda *cold: self.repo.prose("sign", "--pass", token, "--goals-file",
                                                         goals, *cold, stdin="Text.\n"))
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.assertEqual(prose.verify_post(signed.stdout), (True, "signed"))

    def test_a_goals_file_names_the_same_goals_as_goals_does(self):
        # The token is bound to the goals, not to where they came from.
        token = pass_token(self.repo.prose("sign", "--goals", "approve it; check it").stderr)
        same = cold_read(lambda *cold: self.repo.prose(
            "sign", "--pass", token, "--goals-file", self.goals_file("approve it\ncheck it\n"),
            *cold, stdin="Text.\n"))
        self.assertEqual(same.returncode, 0, same.stderr)

    def test_the_signing_call_refuses_a_goals_file_with_other_goals(self):
        token = pass_token(self.repo.prose("sign", "--goals-file",
                                           self.goals_file("approve it\n")).stderr)
        refused = self.repo.prose("sign", "--pass", token, "--goals-file",
                                  self.goals_file("something else\n"), stdin="Text.\n")
        self.assertEqual((refused.returncode, refused.stdout), (2, ""))
        self.assertIn("differ", refused.stderr)

    def test_start_takes_its_goals_from_a_file(self):
        started = self.repo.prose("start", "--goals-file", self.goals_file("review it\n"))
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertIn("1. review it", started.stdout)
        self.assertIn("## The pass", started.stdout)

    def test_a_goals_file_for_one_text_is_refused_when_unusable(self):
        cases = (("# only a comment\n\n", "holds no reader goals"),
                 (" ; ;\n", "holds no reader goals"),
                 (b"approve it \xff\n", "is not valid UTF-8"),
                 (None, "could not read the goals file"))
        for text, said in cases:
            for command in ("start", "sign"):
                with self.subTest(text=text, command=command):
                    path = self.goals_file(text) if text is not None else str(
                        self.repo.path.parent / f"{self.repo.path.name}-missing.txt")
                    result = self.repo.prose(command, "--goals-file", path)
                    self.assertEqual((result.returncode, result.stdout), (2, ""))
                    self.assertIn(said, result.stderr)
                    self.assertFalse((self.repo.path / ".git" / "prose").exists())

    def test_goals_given_twice_are_refused(self):
        # Goals are ordered, so --goals and a file cannot be joined.
        for command in ("start", "sign"):
            with self.subTest(command=command):
                result = self.repo.prose(command, "--goals", "approve it",
                                         "--goals-file", self.goals_file("check it\n"))
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("given twice", result.stderr)

    def test_check_takes_the_message_goals_from_a_file(self):
        goals = self.goals_file("# the reviewer\n\nreview it; merge it\n  see what's left\n")
        first = self.repo.prose("check", "-F", "-", "--message-goals-file", goals,
                                stdin="DOCS(x): add a readme\n")
        self.assertEqual(first.returncode, 4, first.stderr)
        self.assertIn("1. review it\n  2. merge it\n  3. see what's left\n", first.stdout)
        self.assertIn("The commit message, read with the goals above (--message-goals-file):",
                      first.stdout)
        token = pass_token(first.stdout)
        record = json.loads((prose.pass_dir(self.repo.path) / token).read_text())
        self.assertEqual(record["goals"], ["review it", "merge it", "see what's left"])
        result = self.signing(token, "DOCS(x): add a readme\n", "--message-goals-file", goals)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.repo.commit("DOCS(x): add a readme\n", block_trailer(result.stdout))
        self.assertEqual(self.repo.verify().stdout, "checked\n")

    def test_a_message_goals_file_names_the_same_goals_as_goals_does(self):
        token = pass_token(self.first(goals="review it; merge it").stdout)
        same = self.signing(token, "DOCS(x): add a readme\n", "--message-goals-file",
                            self.goals_file("review it\nmerge it\n"))
        self.assertEqual(same.returncode, 0, same.stderr)

    def test_the_signing_check_refuses_a_message_goals_file_with_other_goals(self):
        token = pass_token(self.first(goals="review it").stdout)
        refused = self.signing(token, "DOCS(x): add a readme\n", "--message-goals-file",
                               self.goals_file("something else\n"))
        self.assertEqual((refused.returncode, refused.stdout), (2, ""))
        self.assertIn("differ", refused.stderr)
        self.assertEqual(self.signing(token).returncode, 0)

    def test_a_message_goals_file_is_refused_when_unusable_or_given_with_goals(self):
        # Each case writes the file inside the loop: goals_file always writes the
        # same path, so files written before the loop would all hold the last text.
        cases = (("# only a comment\n\n", (), "holds no reader goals"),
                 (" ; ;\n", (), "holds no reader goals"),
                 (b"review it \xff\n", (), "is not valid UTF-8"),
                 (None, (), "could not read the goals file"),
                 ("merge it\n", ("--goals", "review it"),
                  "given twice, with --goals and --message-goals-file"))
        for text, extra, said in cases:
            with self.subTest(text=text, extra=extra):
                path = self.goals_file(text) if text is not None else str(
                    self.repo.path.parent / f"{self.repo.path.name}-missing.txt")
                result = self.repo.prose("check", "-F", "-", *extra, "--message-goals-file",
                                         path, stdin="DOCS(x): a\n")
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn(said, result.stderr)
                passes = prose.pass_dir(self.repo.path)
                self.assertFalse(passes.exists() and any(passes.iterdir()))

    def test_check_goals_file_still_holds_only_per_file_goals(self):
        # check's --goals-file gives per-file goals only: without --goals or
        # --message-goals-file the message has none, and the first call is refused.
        result = self.repo.prose("check", "-F", "-", "--goals-file",
                                 self.goals_file("README.md: learn it\n"), stdin="DOCS(x): a\n")
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("no reader goals, so no pass token", result.stderr)

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
        signed = cold_read(lambda *cold: run([sys.executable, str(SCRIPT), "sign", "--pass", token,
                                              *cold], cwd=outside, stdin="Text.\n", env=env))
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
            signed = cold_read(lambda *cold: self.repo.prose("sign", "--pass", token, *cold,
                                                             stdin="Text.\n"))
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

    def test_the_next_commands_name_the_path_prose_was_run_by(self):
        # A skill loaded through a link, such as a pinned plugin directory,
        # is run by the link's path; a caller granted that path by permission
        # is denied the clone's. So the printed commands keep the link.
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        link = root / "pinned" / "skills" / "prose"
        link.parent.mkdir(parents=True)
        link.symlink_to(HERE.parent)
        env = dict(os.environ, XDG_STATE_HOME=str(root / "state"))
        script = link / "scripts" / "prose.py"
        started = run([sys.executable, str(script), "start", "--goals", "g"], cwd=self.repo.path, env=env)
        self.assertIn(f"python3 {script} check", started.stdout + started.stderr)
        self.repo.write("a.py", "x = 1\n")
        first = run([sys.executable, str(script), "check", "-F", "-", "--goals", "g",
                     "--goals-for", "README.md", "g"], cwd=self.repo.path, env=env, stdin="Title\n")
        self.assertIn(f"python3 {script} check -F", first.stdout + first.stderr)
        self.assertNotIn(str(SCRIPT), first.stdout + first.stderr)


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
    def test_without_the_shared_reader_a_gh_post_is_blocked_with_the_fix(self):
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        scripts = root / "skills" / "prose" / "scripts"
        scripts.mkdir(parents=True)
        for name in ("prose.py", "comment_scan.py"):
            shutil.copy(HERE / name, scripts / name)
        payload = json.dumps({"tool_name": "Bash", "cwd": str(root),
                              "tool_input": {"command": "gh pr comment 5 --body 'hi'"}})
        result = run([sys.executable, str(scripts / "prose.py"), "hook-post", "--host", "claude"],
                     cwd=root, stdin=payload)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("shared command reader is missing", result.stderr)
        quiet = json.dumps({"tool_name": "Bash", "cwd": str(root),
                            "tool_input": {"command": "ls"}})
        self.assertEqual(run([sys.executable, str(scripts / "prose.py"), "hook-post", "--host",
                              "claude"], cwd=root, stdin=quiet).returncode, 0)

    def test_a_failing_result_block_leaves_the_token_unspent(self):
        # Only a printed trailer spends the token: if the result block cannot
        # be printed, the same signing call can run again.
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        scripts = root / "skills" / "prose" / "scripts"
        scripts.mkdir(parents=True)
        for name in ("prose.py", "comment_scan.py", "compact.py", "reading_cost.py"):
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


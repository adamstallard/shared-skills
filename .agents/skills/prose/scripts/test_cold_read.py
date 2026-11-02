#!/usr/bin/env python3
"""Tests for prose.py's cold read: the brief, the reader's report and its
findings, and signing again on the same tree. Also the saved cold-read
brief: prose.py's brief_files picks the lines each item needs, and
compact.py's print_brief prints and saves the brief.

Standard library only:

    python3 test_cold_read.py
"""

import io
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import unittest

from prose_test_support import (
    BUG_HUNTER_HOOK,
    BUG_HUNTER_MINT,
    COMMIT_HOOK,
    REPORTS,
    Repo,
    SCRIPT,
    TRAILER,
    VERIFY_STAGED,
    block_trailer,
    cold_flags,
    cold_report,
    compact,
    matching,
    pass_token,
    prose,
    run,
    understood_lines,
)


class ColdRead(unittest.TestCase):
    """A commit that changes a comment or a doc passage, and every post, is
    signed only with a cold reader's report for its token; without one, the
    signing call prints the brief, signs nothing and keeps the token. The
    commit message is never read cold."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("a.py", "x = 1\n")
        self.repo.commit("base\n")

    def first(self, message, file_goals=True):
        result = self.repo.prose("check", "-F", "-", "--goals", "review it", stdin=message,
                                 file_goals=file_goals)
        self.assertEqual(result.returncode, 4, result.stderr)
        return pass_token(result.stdout)

    def signing(self, token, message, *extra):
        return self.repo.prose("check", "-F", "-", "--pass", token, *extra, stdin=message,
                               file_goals=False)

    def brief(self, output):
        start = output.index("=== cold-read brief ===\n") + len("=== cold-read brief ===\n")
        return output[start:output.index("=== end cold-read brief ===")]

    def test_a_changed_comment_needs_a_report_and_the_token_is_kept(self):
        self.repo.write("a.py", "x = 1\n# One.\n# Two.\ny = 2\n")
        token = self.first("FEAT(x): a\n", file_goals=False)
        needed = self.signing(token, "FEAT(x): a\n")
        self.assertEqual(needed.returncode, prose.COLD_READ_NEEDED, needed.stderr)
        self.assertNotIn("=== prose result ===", needed.stdout)
        brief = self.brief(needed.stdout)
        self.assertIn(f"  cold-read {token}\n", brief)
        self.assertIn(f"The files named below are in {self.repo.path.resolve()}.", brief)
        self.assertIn("1. A code comment: a.py, lines 2-3, and the code it sits on.", brief)
        self.assertIn("   - what it does that the code doesn't show", brief)
        self.assertIn(f"--pass {token} --cold-read cold-read.txt", needed.stdout)
        signed = self.signing(token, "FEAT(x): a\n", *cold_flags(token))
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.repo.commit("FEAT(x): a\n", block_trailer(signed.stdout))
        self.assertEqual(self.repo.verify().stdout, "checked\n")

    def test_a_one_line_comment_is_read_cold_too(self):
        self.repo.write("a.py", "x = 1  # One.\n")
        token = self.first("FEAT(x): a\n")
        brief = self.brief(self.signing(token, "FEAT(x): a\n").stdout)
        self.assertIn("1. A code comment: a.py, line 1, and the code it sits on.", brief)

    def test_the_brief_is_cold_read_md_unchanged(self):
        self.repo.write("a.py", "x = 1\n# One.\n")
        token = self.first("FEAT(x): a\n")
        brief = self.brief(self.signing(token, "FEAT(x): a\n").stdout)
        self.assertTrue(brief.startswith(prose.COLD_READ.read_text(encoding="utf-8").strip("\n")))

    def test_a_commit_with_no_changed_comment_or_doc_signs_without_a_report(self):
        self.repo.write("a.py", "x = 2\n")
        message = "FEAT(x): a\n\nA body of\nseveral lines\nthat is never read cold.\n"
        token = self.first(message)
        result = self.signing(token, message)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # No cold read: the value is the one prose minted before it had one.
        self.assertRegex(block_trailer(result.stdout), r"^Prose: ✓ [0-9a-f]{12}:[0-9a-f]{12}$")

    def test_one_changed_line_in_a_comment_brings_the_whole_block(self):
        self.repo.write("a.py", "# One.\n# Two.\n# Three.\nx = 1\n")
        self.repo.commit("base 2\n")
        self.repo.write("a.py", "# One.\n# Two, changed.\n# Three.\nx = 1\n")
        token = self.first("FEAT(x): a\n")
        brief = self.brief(self.signing(token, "FEAT(x): a\n").stdout)
        self.assertIn("A code comment: a.py, lines 1-3,", brief)

    def test_the_brief_lists_comments_and_doc_passages_but_never_the_message(self):
        self.repo.write("a.py", "x = 1\n# One.\n")
        self.repo.write("docs/guide.md", "# Guide\n\nOne.\n")
        message = "FEAT(x): a\n\nWhy one.\nWhy two.\n"
        token = self.first(message)
        brief = self.brief(self.signing(token, message).stdout)
        self.assertIn("A code comment: a.py, line 2,", brief)
        self.assertIn("A doc passage: docs/guide.md, the changed lines 1-3, each read in its "
                      "section.", brief)
        self.assertIn("   - read it", brief)
        self.assertNotIn("Why one.", brief)
        self.assertNotIn("commit message", brief)

    def test_a_doc_git_diffs_as_binary_is_skipped(self):
        self.repo.write(".gitattributes", "*.md -diff\n")
        self.repo.write("guide.md", "# Guide\n\nOne.\nTwo.\nThree.\n")
        token = self.first("DOCS(x): guide\n")
        result = self.signing(token, "DOCS(x): guide\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_symlink_at_a_doc_path_needs_no_cold_read(self):
        self.repo.write("AGENTS.md", "# Agents\n\nLong text.\n")
        self.repo.commit("base 2\n")
        os.symlink("AGENTS.md", self.repo.path / "CLAUDE.md")
        self.repo.git("add", "CLAUDE.md")
        token = self.first("FEAT(x): link\n")
        result = self.signing(token, "FEAT(x): link\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_submodule_at_a_doc_path_needs_no_cold_read(self):
        self.repo.git("update-index", "--add", "--cacheinfo",
                      "160000,1111111111111111111111111111111111111111,openspec/specs/lib")
        token = self.first("FEAT(x): add lib\n")
        result = self.signing(token, "FEAT(x): add lib\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_submodule_bump_needs_no_cold_read_when_config_ignores_submodules(self):
        self.repo.git("update-index", "--add", "--cacheinfo",
                      "160000,1111111111111111111111111111111111111111,openspec/sub")
        self.repo.commit("base 2\n")
        self.repo.git("config", "diff.ignoreSubmodules", "all")
        self.repo.git("update-index", "--cacheinfo",
                      "160000,2222222222222222222222222222222222222222,openspec/sub")
        token = self.first("FEAT(x): bump\n")
        result = self.signing(token, "FEAT(x): bump\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_doc_made_a_symlink_to_its_own_text_needs_no_cold_read(self):
        (self.repo.path / "README.md").write_bytes(b"../shared/README.md")
        self.repo.git("add", "README.md")
        self.repo.commit("base 2\n")
        (self.repo.path / "README.md").unlink()
        os.symlink("../shared/README.md", self.repo.path / "README.md")
        self.repo.git("add", "README.md")
        token = self.first("DOCS(x): link\n")
        result = self.signing(token, "DOCS(x): link\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_deleted_doc_needs_no_cold_read(self):
        self.repo.write("old.md", "One.\nTwo.\nThree.\n")
        self.repo.commit("base 2\n")
        self.repo.git("rm", "-q", "old.md")
        token = self.first("DOCS(x): drop old\n")
        self.assertEqual(self.signing(token, "DOCS(x): drop old\n").returncode, 0)

    def test_a_bad_report_is_refused_and_keeps_the_token(self):
        self.repo.write("a.py", "x = 1\n# One.\n")
        message = "FEAT(x): a\n"
        token = self.first(message)
        other = self.first(message)
        self.assertEqual(self.signing(token, message).returncode, prose.COLD_READ_NEEDED)
        bad = REPORTS / "bad.txt"
        for text in ("Item 1: read straight through.\n", f"cold-read {token}\n\n",
                     f"cold-read {other}\nItem 1: read straight through.\n"
                     + understood_lines(1)):
            bad.write_text(text, encoding="utf-8")
            refused = self.signing(token, message, "--cold-read", str(bad))
            self.assertEqual(refused.returncode, 2, text)
            self.assertIn("token is kept", refused.stderr)
        missing = self.signing(token, message, "--cold-read", str(REPORTS / "none.txt"))
        self.assertEqual(missing.returncode, 2)
        self.assertIn("cannot read the cold-read report", missing.stderr)
        signed = self.signing(token, message, *cold_flags(token))
        self.assertEqual(signed.returncode, 0, signed.stderr)

    def test_a_report_starting_with_a_byte_order_mark_is_accepted(self):
        self.repo.write("a.py", "x = 1\n# One.\n")
        token = self.first("FEAT(x): a\n")
        report = REPORTS / "bom.txt"
        self.assertEqual(self.signing(token, "FEAT(x): a\n").returncode, prose.COLD_READ_NEEDED)
        report.write_bytes(f"\ufeffcold-read {token}\nItem 1: read straight through.\n"
                           f"{understood_lines(1)}".encode("utf-8"))
        signed = self.signing(token, "FEAT(x): a\n", "--cold-read", str(report),
                              "--dispositions", matching(token))
        self.assertEqual(signed.returncode, 0, signed.stderr)

    def test_a_cold_read_without_a_pass_is_refused(self):
        result = self.repo.prose("check", "-F", "-", "--goals", "review it",
                                 "--cold-read", cold_report("0" * 16), stdin="FEAT(x): a\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--cold-read goes with --pass", result.stderr)

    def sign(self, *args, stdin):
        return run([sys.executable, str(SCRIPT), "sign"] + list(args), cwd=self.repo.path,
                   stdin=stdin)

    def test_a_post_of_any_length_needs_a_report_and_prints_only_to_stderr(self):
        first = self.sign("--goals", "approve it", stdin="")
        token = pass_token(first.stderr)
        self.assertIn("cold-read brief", first.stderr)
        post = "One line.\n\nprose \u2713 000000\n"
        needed = self.sign("--pass", token, stdin=post)
        self.assertEqual((needed.returncode, needed.stdout), (prose.COLD_READ_NEEDED, ""))
        brief = self.brief(needed.stderr)
        self.assertIn("1. The post below.", brief)
        self.assertIn("   - approve it", brief)
        self.assertIn("   One line.\n   ----", brief)
        self.assertIn(f"sign --pass {token} --cold-read cold-read.txt --dispositions "
                      "dispositions.txt < body.md", needed.stderr)
        signed = self.sign("--pass", token, *cold_flags(token), stdin=post)
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.assertEqual(prose.verify_post(signed.stdout), (True, "signed"))

    def test_an_empty_post_is_refused_before_any_brief(self):
        token = pass_token(self.sign("--goals", "approve it", stdin="").stderr)
        refused = self.sign("--pass", token, stdin="\n")
        self.assertEqual(refused.returncode, 2)
        self.assertNotIn("cold-read brief", refused.stderr)


class ResignSameTree(unittest.TestCase):
    """A signing call on the very tree an earlier signing call signed after a
    cold read, listed with the same items and goals, signs with that read's
    result and prints no brief: re-signing for a new message reads nothing
    cold. Any other tree, and any read no signing call accepted, gets the
    full brief."""

    COMMENT = "x = 1\n# One.\n# Two.\ny = 2\n"

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("a.py", "x = 1\n")
        self.repo.commit("base\n")
        self.repo.write("a.py", self.COMMENT)

    def first(self, message, *extra):
        result = self.repo.prose("check", "-F", "-", "--goals", "review it", *extra,
                                 stdin=message)
        self.assertEqual(result.returncode, 4, result.stderr)
        return pass_token(result.stdout)

    def signing(self, token, message, *extra):
        return self.repo.prose("check", "-F", "-", "--pass", token, *extra, stdin=message,
                               file_goals=False)

    def full_brief(self, token, message, *extra):
        """Asserts the signing call prints a brief naming the comment."""
        result = self.signing(token, message, *extra)
        self.assertEqual(result.returncode, prose.COLD_READ_NEEDED, result.stdout + result.stderr)
        self.assertIn("1. A code comment: a.py, lines 2-3", result.stdout)

    def signed(self, message, *extra):
        """Runs both calls and a full cold read for message, and returns the
        trailer."""
        token = self.first(message, *extra)
        self.full_brief(token, message, *extra)
        done = self.signing(token, message, *extra, *cold_flags(token))
        self.assertEqual(done.returncode, 0, done.stderr)
        return block_trailer(done.stdout)

    def test_a_message_only_resign_reuses_the_cold_read(self):
        first = self.signed("FEAT(x): a\n\nThree tests.\n")
        message = "FEAT(x): a\n\nFour tests.\n"
        token = self.first(message)
        done = self.signing(token, message)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("cold-read brief", done.stdout)
        trailer = block_trailer(done.stdout)
        # The value's tree half and its counts are the first signing's; only
        # the message half differs.
        tree_half = re.compile(r"✓ ([0-9a-f]{12}):")
        self.assertEqual(tree_half.search(trailer).group(1), tree_half.search(first).group(1))
        self.assertEqual(trailer.split(";", 1)[1], first.split(";", 1)[1])
        self.assertTrue(trailer.endswith("; cold read: no findings; understood: 1 item, "
                                         "0 fixed, 0 kept"), trailer)
        self.assertNotEqual(trailer, first)
        self.repo.commit(message, trailer)
        self.assertEqual(self.repo.verify().stdout, "checked\n")

    def test_a_reused_read_keeps_its_counts(self):
        token = self.first("FEAT(x): a\n")
        self.full_brief(token, "FEAT(x): a\n")
        report = cold_report(token, "Finding 1, item 1, guessed: «One» What?\n", name="kept")
        answers = REPORTS / "kept-dispositions.txt"
        answers.write_text(f"dispositions {token}\n1. kept (asked): it is clear\n"
                           "Item 1: matches\n", encoding="utf-8")
        done = self.signing(token, "FEAT(x): a\n", "--cold-read", report, "--dispositions",
                            str(answers))
        self.assertEqual(done.returncode, 0, done.stderr)
        other = self.first("FEAT(x): b\n")
        again = self.signing(other, "FEAT(x): b\n")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertTrue(block_trailer(again.stdout).endswith(
            "; cold read: 1 finding, 0 fixed, 1 kept; understood: 1 item, 0 fixed, 0 kept"))

    def test_any_staged_change_forces_a_full_cold_read(self):
        self.signed("FEAT(x): a\n")
        for name, text in (("a.py", self.COMMENT + "z = 3\n"), ("b.txt", "data\n")):
            with self.subTest(name=name):
                self.repo.write(name, text)
                self.full_brief(self.first("FEAT(x): b\n"), "FEAT(x): b\n")

    def test_a_cold_read_never_signed_is_not_reused(self):
        token = self.first("FEAT(x): a\n")
        self.full_brief(token, "FEAT(x): a\n")
        # The brief was printed, but no signing call accepted the tree.
        self.full_brief(self.first("FEAT(x): b\n"), "FEAT(x): b\n")

    def test_a_refused_signing_call_records_nothing(self):
        token = self.first("FEAT(x): a\n")
        self.full_brief(token, "FEAT(x): a\n")
        bad = self.signing(token, "FEAT(x): a\n", "--cold-read", cold_report(token, name="bad"))
        self.assertEqual(bad.returncode, 2, bad.stderr)
        self.full_brief(self.first("FEAT(x): b\n"), "FEAT(x): b\n")

    def test_a_signing_call_with_nothing_left_to_read_records_nothing(self):
        token = self.first("FEAT(x): a\n")
        self.full_brief(token, "FEAT(x): a\n")
        self.repo.write("a.py", "x = 2\n")
        done = self.signing(token, "FEAT(x): a\n", *cold_flags(token))
        self.assertEqual(done.returncode, 0, done.stderr)
        results = prose.cold_results_dir(str(self.repo.path))
        self.assertEqual(list(results.iterdir()) if results.exists() else [], [])

    def test_a_stale_or_unreadable_earlier_result_forces_a_full_cold_read(self):
        self.signed("FEAT(x): a\n")
        results = prose.cold_results_dir(str(self.repo.path))
        (record,) = list(results.iterdir())
        # An earlier tree's result: the staged tree is not the one it signed.
        stale = json.loads(record.read_text(encoding="utf-8"))
        stale["tree"] = "0" * 40
        for text in ("{not json", json.dumps(stale), json.dumps({"tree": record.name})):
            with self.subTest(text=text):
                record.write_text(text, encoding="utf-8")
                self.full_brief(self.first("FEAT(x): b\n"), "FEAT(x): b\n")
        record.unlink()
        self.full_brief(self.first("FEAT(x): b\n"), "FEAT(x): b\n")

    def test_other_reader_goals_force_a_full_cold_read(self):
        self.signed("FEAT(x): a\n")
        token = self.first("FEAT(x): b\n", "--goals-for", "a.py", "see what it guards")
        self.full_brief(token, "FEAT(x): b\n")

    def test_an_amend_of_the_signed_tree_reuses_the_read(self):
        self.signed("FEAT(x): a\n")
        self.repo.commit("FEAT(x): a\n")
        # The same tree, listed against HEAD's parent: the same items.
        token = self.first("FEAT(x): b\n", "--amend")
        done = self.signing(token, "FEAT(x): b\n", "--amend")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_a_report_passed_anyway_is_checked_as_usual(self):
        self.signed("FEAT(x): a\n")
        token = self.first("FEAT(x): b\n")
        refused = self.signing(token, "FEAT(x): b\n", *cold_flags(token))
        self.assertEqual(refused.returncode, 2, refused.stdout)
        self.assertIn("no cold-read brief was printed", refused.stderr)


class ColdReadFindings(unittest.TestCase):
    """Every finding in a cold reader's report is answered before signing:
    fixed, checked by its item having changed, or kept with a reason. The
    answers are bound to the report's token."""

    COMMENT = "x = 1\n# The worker takes a command\n# off the token. It runs there.\ny = 2\n"
    MESSAGE = "FEAT(x): a\n"

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("a.py", "x = 1\n")
        self.repo.commit("base\n")
        self.repo.write("a.py", self.COMMENT)
        first = self.repo.prose("check", "-F", "-", "--goals", "review it", stdin=self.MESSAGE)
        self.token = pass_token(first.stdout)
        needed = self.signing()
        self.assertEqual(needed.returncode, prose.COLD_READ_NEEDED, needed.stderr)
        self.assertIn(f"--cold-read cold-read.txt --dispositions dispositions.txt",
                      needed.stdout)
        self.assertIn(f"'dispositions {self.token}'", needed.stdout)

    def signing(self, *extra):
        return self.repo.prose("check", "-F", "-", "--pass", self.token, *extra,
                               stdin=self.MESSAGE, file_goals=False)

    def report(self, *findings):
        """A report holding these findings, each (item, quote), and an
        understood line for item 1."""
        return cold_report(self.token, "".join(
            f"Finding {n}, item {item}, guessed: «{quote}» It was not clear.\n"
            for n, (item, quote) in enumerate(findings, start=1)), name="findings")

    def answers(self, *lines, token=None, understood=("Item 1: matches",)):
        """A dispositions file holding lines, then the answers to the
        understood lines, which the understood argument gives."""
        path = REPORTS / "dispositions.txt"
        header = [] if token == "" else [f"dispositions {token or self.token}"]
        path.write_text("\n".join(header + list(lines) + list(understood)) + "\n",
                        encoding="utf-8")
        return str(path)

    def refused(self, result, *words):
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("token is kept", result.stderr)
        for word in words:
            self.assertIn(word, result.stderr)

    def fix(self, text):
        self.repo.write("a.py", text)

    def test_findings_without_dispositions_are_refused(self):
        self.refused(self.signing("--cold-read", self.report((1, "takes a command"))),
                     "pass --dispositions", f"'dispositions {self.token}'")

    def test_dispositions_must_carry_the_report_token(self):
        report = self.report((1, "takes a command"))
        self.fix("x = 1\n# The worker runs the command.\ny = 2\n")
        self.refused(self.signing("--cold-read", report, "--dispositions",
                                  self.answers("1. fixed", token="")),
                     f"does not start with 'dispositions {self.token}'")
        self.refused(self.signing("--cold-read", report, "--dispositions",
                                  self.answers("1. fixed", token="0" * 16)),
                     f"does not start with 'dispositions {self.token}'")
        signed = self.signing("--cold-read", report, "--dispositions", self.answers("1. fixed"))
        self.assertEqual(signed.returncode, 0, signed.stderr)

    def test_every_finding_is_answered_once(self):
        report = self.report((1, "takes a command"), (1, "It runs there."))
        self.fix("x = 1\n# The worker runs the command.\ny = 2\n")
        self.refused(self.signing("--cold-read", report, "--dispositions",
                                  self.answers("1. fixed")), "does not answer finding 2")
        self.refused(self.signing("--cold-read", report, "--dispositions",
                                  self.answers("1. fixed", "2. fixed", "1. fixed")),
                     "answers finding 1 twice")
        self.refused(self.signing("--cold-read", report, "--dispositions",
                                  self.answers("1. fixed", "2. fixed", "3. fixed")),
                     "answers finding 3, which the report does not have")
        self.refused(self.signing("--cold-read", report, "--dispositions",
                                  self.answers("1. fixed", "2: fixed")),
                     "a line prose cannot read: '2: fixed'")
        signed = self.signing("--cold-read", report, "--dispositions",
                              self.answers("2. fixed", "1. fixed"))
        self.assertEqual(signed.returncode, 0, signed.stderr)

    def test_fixed_is_refused_while_its_item_is_unchanged(self):
        report = self.report((1, "It runs there."))
        answers = self.answers("1. fixed")
        unchanged = ("finding 1 is marked fixed, but item 1, in a.py, has not changed since the "
                     "brief was printed")
        self.refused(self.signing("--cold-read", report, "--dispositions", answers), unchanged)
        # Code added below the item, one line clear of it, is not a change to it.
        self.fix(self.COMMENT + "z = 3\n")
        self.refused(self.signing("--cold-read", report, "--dispositions", answers), unchanged)
        self.fix(self.COMMENT.replace("It runs there.", "It runs in the clone."))
        signed = self.signing("--cold-read", report, "--dispositions", answers)
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.repo.commit(self.MESSAGE, block_trailer(signed.stdout))

    def test_an_edit_to_another_part_of_the_item_counts(self):
        # The accepted cost of comparing items, not quotes (DECISIONS: Every
        # cold-read finding is answered before signing).
        report = self.report((1, "It runs there."))
        self.fix(self.COMMENT.replace("worker", "builder"))
        signed = self.signing("--cold-read", report, "--dispositions", self.answers("1. fixed"))
        self.assertEqual(signed.returncode, 0, signed.stderr)

    def test_a_deleted_file_counts_as_changed(self):
        report = self.report((1, "It runs there."))
        self.repo.git("rm", "-q", "-f", "a.py")
        signed = self.signing("--cold-read", report, "--dispositions", self.answers("1. fixed"))
        self.assertEqual(signed.returncode, 0, signed.stderr)

    def test_kept_needs_a_reason(self):
        report = self.report((1, "It runs there."))
        for line in ("1. kept (asked):", "1. kept (asked):   ", "1. kept:"):
            self.refused(self.signing("--cold-read", report, "--dispositions",
                                      self.answers(line)), "keeps finding 1 without a reason")
        signed = self.signing("--cold-read", report, "--dispositions",
                              self.answers("1. kept (asked): the line above names the clone"))
        self.assertEqual(signed.returncode, 0, signed.stderr)

    def test_a_kept_finding_no_person_was_asked_about_is_refused_and_handed_back(self):
        report = self.report((1, "takes a command"), (1, "It runs there."))
        self.fix("x = 1\n# The worker runs the command.\n# It runs there.\ny = 2\n")
        answers = self.answers("1. fixed", "2. kept: the line above says where")
        refused = self.signing("--cold-read", report, "--dispositions", answers)
        self.refused(refused, "1 finding(s) are kept, and no person was asked about them",
                     f"the token is kept: {self.token}, unspent, lasts 2 hours",
                     "Finding 2, in a.py: «It runs there.»\n"
                     "  The cold reader: It was not clear.\n"
                     "  Kept, because: the line above says where\n",
                     '"Keep as is" makes its line \'<n>. kept (asked): <reason>\'',
                     '"Fix it" means rewrite the passage (and restage it, for a commit)',
                     "If you cannot ask (a subagent, a background job, no picker), don't sign",
                     f"the report {pathlib.Path(report).resolve()}",
                     f"the dispositions file {pathlib.Path(answers).resolve()}")
        self.assertNotIn("Finding 1, in", refused.stderr)
        self.assertEqual(refused.stdout, "")
        for line in ("2. kept (asked) : x", "2. kept(asked): x", "2. kept (Asked): x"):
            self.refused(self.signing("--cold-read", report, "--dispositions",
                                      self.answers("1. fixed", line)), "a line prose cannot read")
        signed = self.signing("--cold-read", report, "--dispositions",
                              self.answers("1. fixed", "2. kept (asked): the line above says where"))
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.assertNotIn("Finding 2", signed.stderr)

    def test_a_quote_is_not_checked_against_the_text(self):
        # A paraphrase, a change of case, curly quotes and an ellipsis.
        report = self.report((1, "It runs here."), (1, "it runs there."),
                             (1, "\u201cIt runs\u201d \u2026"))
        signed = self.signing("--cold-read", report, "--dispositions",
                              self.answers("1. kept (asked): fine", "2. kept (asked): fine",
                                           "3. kept (asked): fine"))
        self.assertEqual(signed.returncode, 0, signed.stderr)

    def test_a_report_prose_cannot_read_is_refused_with_its_form(self):
        for body, problem in (
                ("It was fine.\n", "a line prose cannot read: 'It was fine.'"),
                ("", "holds only its first line"),
                ("Finding 1, item 1, stopped: \"It runs there.\" No place.\n",
                 "a line prose cannot read"),
                ("Finding 2, item 1, stopped: «It runs there.» No place.\n",
                 "numbers finding 1 as 2"),
                ("Finding 1, item 2, stopped: «It runs there.» No place.\n",
                 "puts finding 1 in item 2, but the brief has items 1 to 1"),
                ("Finding 1, item 1, stopped: «It runs there.»\n",
                 "does not say, in finding 1, what was guessed or missing"),
                ("Finding 1, item 1, stopped: «  » No words.\n", "quotes no words in finding 1"),
                ("Item 1: read straight through.\nItem 1: read straight through.\n",
                 "item 1 was read straight through twice"),
                ("Item 1: read straight through.\nFinding 1, item 1, reread: «It runs there.» "
                 "Where?\n", "and also reports findings in it"),
                ("Item 2: read straight through.\n", "says nothing about item 1"),
                ("Item 1: read straight through.\nItem 2: read straight through.\n",
                 "names item 2, but the brief has items 1 to 1"),
        ):
            result = self.signing("--cold-read", cold_report(self.token, body, name="bad",
                                                             understood=0))
            self.refused(result, problem)
            if problem != "holds only its first line":
                self.assertIn("'Item <item>: read straight through.'", result.stderr)

    def test_a_finding_may_go_on_over_indented_lines(self):
        report = cold_report(self.token, "Finding 1, item 1, guessed: «It runs there.»\n"
                                         "   What runs, and where?\n", name="wrapped")
        signed = self.signing("--cold-read", report, "--dispositions",
                              self.answers("1. kept (asked): a test"))
        self.assertEqual(signed.returncode, 0, signed.stderr)

    def test_a_report_with_no_findings_still_answers_its_understood_lines(self):
        report = cold_report(self.token, "Item 1: read straight through.\n", name="clean")
        self.refused(self.signing("--cold-read", report),
                     "0 finding(s) and 1 understood line(s), and each needs an answer: pass "
                     "--dispositions", f"'dispositions {self.token}'")
        signed = self.signing("--cold-read", report, "--dispositions", self.answers())
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.assertTrue(block_trailer(signed.stdout).endswith(
            ":" + prose.message_hash(self.MESSAGE)
            + "; cold read: no findings; understood: 1 item, 0 fixed, 0 kept"))

    def hook(self, script):
        payload = json.dumps({"cwd": str(self.repo.path)})
        return run(["sh", str(script), "--host", "claude"], stdin=payload,
                   env=dict(os.environ, TMPDIR=tempfile.gettempdir()))

    def test_the_trailer_counts_the_findings(self):
        for script in (COMMIT_HOOK, BUG_HUNTER_HOOK):
            self.hook(script)  # sets each hook's cursor before the commit
        report = self.report((1, "takes a command"), (1, "It runs there."))
        self.fix("x = 1\n# The worker runs the command.\n# It runs there.\ny = 2\n")
        signed = self.signing("--cold-read", report, "--dispositions",
                              self.answers("1. fixed",
                                           "2. kept (asked): the line above says where"))
        self.assertEqual(signed.returncode, 0, signed.stderr)
        trailer = block_trailer(signed.stdout)
        self.assertRegex(trailer, TRAILER)
        self.assertTrue(trailer.endswith("; cold read: 2 findings, 1 fixed, 1 kept"
                                         "; understood: 1 item, 0 fixed, 0 kept"), trailer)
        self.assertEqual(signed.stdout.count("\n"), 4, signed.stdout)
        made = self.repo.commit_script(
            "FEAT(x): a", "", "--minted-by", str(BUG_HUNTER_MINT), "Bug-hunter", "0 bugs found",
            "--verified-value", str(VERIFY_STAGED), "Prose", trailer[len("Prose: "):])
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual(self.repo.git("log", "-1", "--format=%(trailers:key=Prose,valueonly)")
                         .strip(), trailer[len("Prose: "):])
        self.assertEqual(self.repo.verify().stdout, "checked\n")
        for script in (COMMIT_HOOK, BUG_HUNTER_HOOK):
            result = self.hook(script)
            self.assertEqual(result.returncode, 0, f"{script}: {result.stderr}")

    def test_all_fixed_counts_none_kept(self):
        report = self.report((1, "It runs there."))
        self.fix("x = 1\n# The worker runs the command in the clone.\ny = 2\n")
        signed = self.signing("--cold-read", report, "--dispositions", self.answers("1. fixed"))
        self.assertTrue(block_trailer(signed.stdout).endswith(
            "; cold read: 1 finding, 1 fixed, 0 kept; understood: 1 item, 0 fixed, 0 kept"))

    def test_a_report_missing_an_understood_line_is_refused(self):
        for body, understood, problem in (
                ("Finding 1, item 1, guessed: «It runs there.» Where?\n", 0,
                 "does not say what it understood of item 1: every item gets one 'Item 1, "
                 "understood: <what the item says>' line"),
                ("Item 1: read straight through.\n", 0, "does not say what it understood of item 1"),
                ("Item 1: read straight through.\nItem 1, understood: Once.\n", 1,
                 "says what it understood of item 1 twice"),
                ("Item 1: read straight through.\nItem 2, understood: Once.\n", 1,
                 "names item 2, but the brief has items 1 to 1"),
                ("Item 1: read straight through.\nItem 1, understood:\n", 0,
                 "a line prose cannot read: 'Item 1, understood:'"),
        ):
            result = self.signing("--cold-read", cold_report(self.token, body, name="bad",
                                                             understood=understood),
                                  "--dispositions", self.answers())
            self.refused(result, problem)
            self.assertIn("'Item <item>, understood: <what the item says>'", result.stderr)

    def test_an_understood_line_may_go_on_over_indented_lines(self):
        report = cold_report(self.token, "Item 1: read straight through.\n"
                                         "Item 1, understood: The worker takes a command\n"
                                         "   and runs it, always.\n", name="wrapped",
                             understood=0)
        signed = self.signing("--cold-read", report, "--dispositions", self.answers())
        self.assertEqual(signed.returncode, 0, signed.stderr)

    def test_every_understood_line_is_answered_once(self):
        report = self.report((1, "It runs there."))
        for understood, problem in (
                ((), "does not answer the understood line of item 1; every item's understood "
                     "line is answered once"),
                (("Item 1: matches", "Item 1: matches"),
                 "answers the understood line of item 1 twice"),
                (("Item 1: matches", "Item 2: matches"),
                 "answers the understood line of item 2, which the report does not have"),
                (("Item 1: match",), "a line prose cannot read: 'Item 1: match'"),
                (("Item 1: kept (asked):",), "keeps the understood line of item 1 without a "
                                             "reason"),
        ):
            self.refused(self.signing("--cold-read", report, "--dispositions",
                                      self.answers("1. kept (asked): fine",
                                                   understood=understood)), problem)
        signed = self.signing("--cold-read", report, "--dispositions",
                              self.answers("1. kept (asked): fine"))
        self.assertEqual(signed.returncode, 0, signed.stderr)

    def test_an_understood_line_marked_fixed_needs_its_item_changed(self):
        report = cold_report(self.token, "Item 1: read straight through.\n", name="clean")
        answers = self.answers(understood=("Item 1: fixed",))
        self.refused(self.signing("--cold-read", report, "--dispositions", answers),
                     "the understood line of item 1 is marked fixed, but item 1, in a.py, has "
                     "not changed since the brief was printed")
        self.fix(self.COMMENT.replace("It runs there.", "A person may run it there."))
        signed = self.signing("--cold-read", report, "--dispositions", answers)
        self.assertEqual(signed.returncode, 0, signed.stderr)
        trailer = block_trailer(signed.stdout)
        self.assertTrue(trailer.endswith("; cold read: no findings; understood: 1 item, 1 fixed, "
                                         "0 kept"), trailer)
        self.repo.commit(self.MESSAGE, trailer)
        self.assertEqual(self.repo.verify().stdout, "checked\n")

    def test_a_kept_understood_line_needs_a_person_asked(self):
        report = cold_report(self.token, "Item 1: read straight through.\n", name="clean")
        refused = self.signing("--cold-read", report, "--dispositions",
                               self.answers(understood=("Item 1: kept: close enough",)))
        self.refused(refused, "1 understood line(s) are kept, and no person was asked",
                     "Item 1, in a.py, understood: The code does this, always.\n"
                     "  Kept, because: close enough\n",
                     "(for an understood line, 'Item <n>: kept (asked): <reason>')")
        self.assertNotIn("finding(s)", refused.stderr.split("\n")[0])
        signed = self.signing("--cold-read", report, "--dispositions",
                              self.answers(understood=("Item 1: kept (asked): close enough",)))
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.assertTrue(block_trailer(signed.stdout).endswith(
            "; understood: 1 item, 0 fixed, 1 kept"))

    def test_understood_counts_in_any_other_form_are_unrecognised(self):
        good = f"Prose: ✓ {'0' * 12}:{prose.message_hash(self.MESSAGE)}; cold read: no findings"
        for counts in ("0 items, 0 fixed, 0 kept", "1 items, 0 fixed, 0 kept",
                       "2 item, 0 fixed, 0 kept", "1 item, 1 fixed, 1 kept", "1 item, 1 fixed",
                       "01 items, 0 fixed, 0 kept", "", "2 items, 0 fixed, 0 kept; x"):
            ok, reason = prose.verify_staged(f"{good}; understood: {counts}", self.MESSAGE,
                                             self.repo.path)
            self.assertEqual((ok, reason.split(":")[0]), (False, "unrecognised"), counts)
        # A value from before the understood lines, and each new form, is
        # recognised: each fails only on its tree, a zero hash here.
        for value in (good, f"{good}; understood: 1 item, 0 fixed, 0 kept",
                      f"{good}; understood: 41 items, 2 fixed, 1 kept"):
            ok, reason = prose.verify_staged(value, self.MESSAGE, self.repo.path)
            self.assertTrue(reason.startswith("tree:"), (value, reason))
        ok, reason = prose.verify_staged(f"Prose: ✓ {'0' * 12}:{prose.message_hash(self.MESSAGE)}"
                                         "; understood: 1 item, 0 fixed, 0 kept", self.MESSAGE,
                                         self.repo.path)
        self.assertEqual((ok, reason.split(":")[0]), (False, "unrecognised"))

    def test_a_commit_signed_before_the_understood_lines_still_verifies(self):
        report = cold_report(self.token, "Item 1: read straight through.\n", name="clean")
        trailer = block_trailer(self.signing("--cold-read", report, "--dispositions",
                                             self.answers()).stdout)
        self.assertTrue(trailer.endswith("; understood: 1 item, 0 fixed, 0 kept"), trailer)
        self.repo.commit(self.MESSAGE, trailer[:-len("; understood: 1 item, 0 fixed, 0 kept")])
        self.assertEqual(self.repo.verify().stdout, "checked\n")

    def test_counts_in_any_other_form_are_unrecognised(self):
        good = f"Prose: ✓ {'0' * 12}:{prose.message_hash(self.MESSAGE)}"
        for counts in ("2 findings, 1 fixed, 2 kept", "1 findings, 1 fixed, 0 kept",
                       "0 findings, 0 fixed, 0 kept", "2 findings, 01 fixed, 1 kept",
                       "3 findings", "No findings", "", "1 finding, 1 fixed, 0 kept; x"):
            ok, reason = prose.verify_staged(f"{good}; cold read: {counts}", self.MESSAGE,
                                             self.repo.path)
            self.assertEqual((ok, reason.split(":")[0]), (False, "unrecognised"), counts)
        for counts in ("no findings", "1 finding, 0 fixed, 1 kept", "12 findings, 7 fixed, 5 kept"):
            ok, reason = prose.verify_staged(f"{good}; cold read: {counts}", self.MESSAGE,
                                             self.repo.path)
            self.assertTrue(reason.startswith("tree:"), (counts, reason))

    def test_a_committed_value_with_counts_in_another_form_is_unrecognised(self):
        report = cold_report(self.token, "Item 1: read straight through.\n", name="clean")
        trailer = block_trailer(self.signing("--cold-read", report, "--dispositions",
                                             self.answers()).stdout)
        self.repo.commit(self.MESSAGE, trailer.replace("no findings", "0 findings, 0 fixed, 0 kept"))
        result = self.repo.verify()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("unrecognised:"), result.stdout)

    def test_dispositions_without_a_report_are_refused(self):
        result = self.signing("--dispositions", self.answers("1. fixed"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("--dispositions goes with --cold-read", result.stderr)

    def test_a_file_staged_after_the_brief_needs_a_new_brief(self):
        self.repo.write("b.py", "# It does the thing with the stuff.\nz = 3\n")
        report = cold_report(self.token, "Item 1: read straight through.\n", name="clean")
        result = self.signing("--cold-read", report)
        self.refused(result, "b.py")
        self.assertNotIn("=== prose result ===", result.stdout)

    def test_a_report_with_no_brief_printed_is_refused(self):
        first = self.repo.prose("check", "-F", "-", "--goals", "review it", stdin=self.MESSAGE)
        token = pass_token(first.stdout)
        result = self.repo.prose("check", "-F", "-", "--pass", token, "--cold-read",
                                 cold_report(token), stdin=self.MESSAGE, file_goals=False)
        self.refused(result, f"no cold-read brief was printed for pass token {token}")

    def test_a_post_fixed_means_the_post_changed(self):
        sign = lambda *args, stdin: run([sys.executable, str(SCRIPT), "sign"] + list(args),
                                        cwd=self.repo.path, stdin=stdin)
        token = pass_token(sign("--goals", "approve it", stdin="").stderr)
        post = "The fix lands there.\nIt is safe.\n"
        self.assertEqual(sign("--pass", token, stdin=post).returncode, prose.COLD_READ_NEEDED)
        report = cold_report(token, "Finding 1, item 1, guessed: «lands there» Where?\n",
                             name="post")
        answers = self.answers("1. fixed", token=token)
        # A footer added or removed is not a change to the post.
        for same in (post, post + "\nprose \u2713 000000\n"):
            self.refused(sign("--pass", token, "--cold-read", report, "--dispositions", answers,
                              stdin=same), "item 1, in the post, has not changed")
        # Any change to the post counts, even one far from the quote.
        fixed = "The fix lands there.\nIt is safe to merge.\n"
        signed = sign("--pass", token, "--cold-read", report, "--dispositions", answers,
                      stdin=fixed)
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.assertEqual(prose.verify_post(signed.stdout), (True, "signed"))

    def test_a_post_keeps_a_finding_only_once_a_person_was_asked(self):
        sign = lambda *args, stdin: run([sys.executable, str(SCRIPT), "sign"] + list(args),
                                        cwd=self.repo.path, stdin=stdin)
        token = pass_token(sign("--goals", "approve it", stdin="").stderr)
        post = "The fix lands there.\n"
        sign("--pass", token, stdin=post)
        report = cold_report(token, "Finding 1, item 1, guessed: «lands there» Where?\n",
                             name="post-kept")
        refused = sign("--pass", token, "--cold-read", report, "--dispositions",
                       self.answers("1. kept: the title names the branch", token=token),
                       stdin=post)
        self.refused(refused, "Finding 1, in the post: «lands there»\n  The cold reader: Where?\n"
                              "  Kept, because: the title names the branch\n")
        self.assertEqual(refused.stdout, "")
        signed = sign("--pass", token, "--cold-read", report, "--dispositions",
                      self.answers("1. kept (asked): the title names the branch", token=token),
                      stdin=post)
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.assertEqual(signed.stdout, prose.sign(post))


class FixedItemChanged(unittest.TestCase):
    """A finding marked fixed counts only when the item it is in changed
    since the brief: not another item in the same file, and not the item's
    lines moved by an edit above it."""

    TWO = "# First block,\n# two lines.\nx = 1\n\ny = 2\n# Second block.\nz = 3\n"

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("a.py", "x = 1\n")
        self.repo.commit("base\n")

    def signed_after_fix(self, files, fixes, item=1, items=1, deleted=()):
        """The signing call after a brief over files, {path: text}, a report
        with one finding in item, marked fixed, and fixes staged."""
        for path, text in files.items():
            self.repo.write(path, text)
        first = self.repo.prose("check", "-F", "-", "--goals", "review it", stdin="FEAT(x): a\n")
        token = pass_token(first.stdout)
        sign = lambda *extra: self.repo.prose("check", "-F", "-", "--pass", token, *extra,
                                              stdin="FEAT(x): a\n")
        needed = sign()
        self.assertEqual(needed.returncode, prose.COLD_READ_NEEDED, needed.stderr)
        lines = [f"Finding 1, item {item}, guessed: «x» Which call?"] + [
            f"Item {n}: read straight through." for n in range(1, items + 1) if n != item]
        report = cold_report(token, "\n".join(lines) + "\n", name="item-changed",
                             understood=items)
        answers = matching(token, items, "1. fixed", name="item-changed")
        for path, text in fixes.items():
            self.repo.write(path, text)
        for path in deleted:
            self.repo.git("rm", "-q", "-f", path)
        return sign("--cold-read", report, "--dispositions", str(answers))

    def assert_refused(self, result, item):
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(f"item {item}, in ", result.stderr)
        self.assertIn("has not changed since the brief was printed", result.stderr)

    def test_an_edit_to_another_item_does_not_count(self):
        fixed = self.TWO.replace("Second block.", "Second block, reworded.")
        self.assert_refused(self.signed_after_fix({"a.py": self.TWO}, {"a.py": fixed}, items=2), 1)
        self.assertEqual(self.signed_after_fix({"a.py": self.TWO}, {"a.py": fixed}, item=2,
                                               items=2).returncode, 0)

    def test_lines_moved_by_an_edit_above_are_not_a_change(self):
        moved = "import os\nimport re\n\n" + self.TWO
        self.assert_refused(self.signed_after_fix({"a.py": self.TWO}, {"a.py": moved}, item=2,
                                                  items=2), 2)
        reworded = moved.replace("Second block.", "Second block, reworded.")
        self.assertEqual(self.signed_after_fix({"a.py": self.TWO}, {"a.py": reworded}, item=2,
                                               items=2).returncode, 0)

    def test_an_edit_in_another_file_does_not_count(self):
        files = {"a.py": "# One.\nx = 1\n", "b.py": "# Two.\ny = 2\n"}
        result = self.signed_after_fix(files, {"b.py": "# Two, reworded.\ny = 2\n"}, items=2)
        self.assert_refused(result, 1)

    def test_a_line_added_inside_or_at_the_edge_of_a_doc_passage_counts(self):
        doc = "# Guide\n\nOld text.\n"
        self.repo.write("guide.md", doc)
        self.repo.commit("base 2\n")
        before = doc + "\nNew passage.\n"
        for after in (before + "Its reason.\n", before.replace("\nNew", "\nFirst.\nNew")):
            result = self.signed_after_fix({"guide.md": before}, {"guide.md": after})
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_refused(self.signed_after_fix(
            {"guide.md": before}, {"guide.md": before.replace("Old text.", "Old.")}), 1)

    def test_a_removed_passage_or_a_deleted_file_counts(self):
        doc = "# Guide\n\nOld text.\n"
        self.repo.write("guide.md", doc)
        self.repo.commit("base 2\n")
        added = doc + "\nNew passage.\n"
        result = self.signed_after_fix({"guide.md": added}, {"guide.md": doc, "a.py": "x = 2\n"})
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.signed_after_fix({"guide.md": added}, {}, deleted=["guide.md"])
        self.assertEqual(result.returncode, 0, result.stderr)


class ItemChanged(unittest.TestCase):
    """item_changed, on line spans of the text the brief recorded."""

    OLD = "a\nb\nc\nd\ne\n"

    def changed(self, new, spans=((3, 3),)):
        return prose.item_changed(self.OLD, new, spans)

    def test_a_line_of_the_item_changed_or_removed(self):
        self.assertTrue(self.changed("a\nb\nC\nd\ne\n"))
        self.assertTrue(self.changed("a\nb\nd\ne\n"))

    def test_a_line_added_inside_or_directly_beside_the_item(self):
        self.assertTrue(self.changed("a\nb\nX\nc\nd\ne\n"))
        self.assertTrue(self.changed("a\nb\nc\nX\nd\ne\n"))
        self.assertTrue(prose.item_changed(self.OLD, "a\nb\nX\nc\nd\ne\n", ((2, 3),)))

    def test_changes_beside_or_away_from_the_item_do_not_count(self):
        self.assertFalse(self.changed(self.OLD))
        self.assertFalse(self.changed("X\nY\na\nb\nc\nd\ne\n"))
        self.assertFalse(self.changed("a\nB\nc\nD\ne\n"))
        self.assertFalse(self.changed("a\nc\nd\n"))
        self.assertFalse(self.changed("a\nb\nc\nd\ne\nf\n"))

    def test_any_of_several_spans(self):
        self.assertTrue(prose.item_changed(self.OLD, "a\nb\nc\nd\nE\n", ((1, 1), (5, 5))))
        self.assertFalse(prose.item_changed(self.OLD, "a\nb\nC\nd\ne\n", ((1, 1), (5, 5))))

    def test_blank_lines_in_a_long_doc_are_not_reported_changed(self):
        old = "".join(f"Line {n}.\n\n" for n in range(300))
        new = old.replace("Line 10.", "Line ten.")
        self.assertFalse(prose.item_changed(old, new, ((400, 420),)))
        self.assertTrue(prose.item_changed(old, new, ((19, 21),)))

    def test_with_no_spans_the_whole_text_is_the_item(self):
        self.assertFalse(prose.item_changed("a b\n", "a b\n", ()))
        self.assertTrue(prose.item_changed("a b\n", "a  b\n", ()))
        self.assertTrue(prose.item_changed("a\n", "", ((1, 1),)))


class ColdReadBriefFiles(unittest.TestCase):
    """The saved cold-read brief goes on with the staged lines its items
    need, so the reader needs nothing but the brief; the printed brief ends
    with a note instead (DECISIONS: The cold reader runs on the brief
    alone)."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("README.md", "# Base\n")
        self.repo.commit("base\n")
        (self.repo.path / ".msg").write_text("FEAT(x): a\n")

    def needed(self):
        first = self.repo.prose("check", "-F", ".msg", "--goals", "review it")
        token = pass_token(first.stdout)
        result = self.repo.prose("check", "-F", ".msg", "--goals", "review it", "--pass", token)
        self.assertEqual(result.returncode, prose.COLD_READ_NEEDED, result.stdout + result.stderr)
        printed = result.stdout[result.stdout.index("=== cold-read brief ===\n"):
                                result.stdout.index("=== end cold-read brief ===")]
        path = pathlib.Path(re.search(r"^Brief file: (.+)$", result.stdout, re.M).group(1))
        return printed, path.read_text(encoding="utf-8")

    def test_the_saved_brief_holds_each_named_file_with_line_numbers(self):
        self.repo.write("a.py", "x = 1\n# One.\ny = 2\n")
        printed, saved = self.needed()
        self.assertIn("--- a.py ---\n1  x = 1\n2  # One.\n3  y = 2\n--- end a.py ---", saved)
        self.assertTrue(printed.rstrip("\n").endswith(prose.BRIEF_FILES_NOTE))
        self.assertNotIn("--- a.py ---", printed)

    def test_the_staged_text_is_copied_not_the_working_tree(self):
        self.repo.write("a.py", "x = 1\n# Staged.\n")
        (self.repo.path / "a.py").write_text("x = 1\n# Unstaged edit.\n")
        _, saved = self.needed()
        self.assertIn("2  # Staged.", saved)
        self.assertNotIn("Unstaged edit", saved)

    def test_a_file_two_items_name_is_copied_once(self):
        self.repo.write("a.py", "# One.\nx = 1\n\n\ny = 2\n# Two.\n")
        _, saved = self.needed()
        self.assertEqual(saved.count("--- a.py ---"), 1)
        self.assertIn("A code comment: a.py, line 1,", saved)
        self.assertIn("A code comment: a.py, line 6,", saved)

    def test_a_doc_and_a_comment_are_both_copied(self):
        self.repo.write("a.py", "x = 1  # One.\n")
        self.repo.write("docs/guide.md", "# Guide\n\nOne.\n")
        _, saved = self.needed()
        self.assertIn("--- a.py ---", saved)
        self.assertIn("--- docs/guide.md ---\n1  # Guide\n2\n3  One.\n", saved)

    def test_a_post_brief_has_no_files_and_no_note(self):
        sign = lambda *args, stdin: run([sys.executable, str(SCRIPT), "sign"] + list(args),
                                        cwd=self.repo.path, stdin=stdin)
        token = pass_token(sign("--goals", "approve it", stdin="").stderr)
        needed = sign("--pass", token, stdin="The fix lands.\n")
        self.assertEqual(needed.returncode, prose.COLD_READ_NEEDED, needed.stderr)
        self.assertNotIn(prose.BRIEF_FILES_NOTE, needed.stderr)
        self.assertNotIn("The named files", needed.stderr)


def fill(tag, count):
    """count numbered lines of filler, tag0 to tag<count - 1>."""
    return "".join(f"{tag}{n}\n" for n in range(count))


class BriefFilesText(unittest.TestCase):
    """brief_files on its own: numbering, odd bytes, and the window each
    item gets."""

    def item(self, path="a.py"):
        return prose.ColdItem("A code comment.", ("g",), path, spans=((1, 1),))

    def test_a_bare_cr_does_not_shift_the_numbers(self):
        out = prose.brief_files([self.item()], {"a.py": "a\rb\nc\n"})
        self.assertIn("1  ab\n2  c\n", out)

    def test_a_last_line_with_no_newline_is_kept(self):
        out = prose.brief_files([self.item()], {"a.py": "# One.\nx = 1"})
        self.assertIn("1  # One.\n2  x = 1\n--- end a.py ---", out)

    def test_bytes_that_are_not_utf8_are_replaced(self):
        text = b"x = '\xff'\n".decode("utf-8", prose.TEXT_ERRORS)
        out = prose.brief_files([self.item()], {"a.py": text})
        self.assertIn("1  x = '\ufffd'", out)
        out.encode("utf-8")

    def doc(self, spans, path="guide.md"):
        return prose.ColdItem("A doc passage.", ("g",), path, spans=spans)

    def test_a_doc_passage_gets_its_section_up_to_a_heading_as_high(self):
        text = ("# A\n" + fill("a", 50) + "## B\n" + fill("b", 50) + "### B1\n" + fill("c", 50) +
                "## C\n" + fill("d", 60))
        out = prose.brief_files([self.doc(((100, 100),))], {"guide.md": text})
        self.assertIn("(lines 1-51 left out)\n 52  ## B\n", out)
        self.assertIn("103  ### B1\n", out)
        self.assertIn("(lines 154-214 left out)", out)

    def test_a_hash_line_in_a_fence_is_not_a_heading(self):
        text = "## A\n```sh\n# a shell comment\n```\n" + fill("a", 100) + "## B\n" + fill("b", 60)
        out = prose.brief_files([self.doc(((60, 60),))], {"guide.md": text})
        self.assertIn("--- guide.md ---\n  1  ## A\n", out)
        self.assertIn("(lines 105-165 left out)", out)

    def test_a_passage_before_any_heading_starts_at_line_one(self):
        text = fill("p", 60) + "# Later\n" + fill("f", 60)
        out = prose.brief_files([self.doc(((10, 10),))], {"guide.md": text})
        self.assertIn("--- guide.md ---\n  1  p0\n", out)
        self.assertIn("(lines 61-121 left out)", out)

    def test_a_long_section_is_cut_but_keeps_its_heading(self):
        reach = prose.BRIEF_SECTION_REACH
        text = "# Top\n" + "".join(f"line {n}\n" for n in range(2, 2 * reach + 400))
        middle = reach + 200
        out = prose.brief_files([self.doc(((middle, middle),))], {"guide.md": text})
        self.assertIn("--- guide.md ---\n  1  # Top\n(lines 2-", out)
        self.assertIn(f"(lines 2-{middle - reach - 1} left out)", out)
        self.assertIn(f"{middle + reach}  line {middle + reach}\n(lines {middle + reach + 1}-", out)

    def test_a_readme_and_a_spec_get_their_sections(self):
        text = "# P\n" + fill("p", 10) + "## Install\n" + fill("s", 100) + "## Usage\n" + fill("u", 60)
        for path in ("README.md", "openspec/specs/x/spec.md"):
            out = prose.brief_files([self.doc(((60, 60),), path)], {path: text})
            self.assertIn("(lines 1-11 left out)\n 12  ## Install\n", out, path)
            self.assertIn("(lines 113-173 left out)", out, path)

    def test_a_setext_underline_is_not_taken_for_a_heading(self):
        text = "Usage\n===\n" + "".join(f"para {n}\n" for n in range(3, 200))
        out = prose.brief_files([self.doc(((180, 180),))], {"guide.md": text})
        self.assertNotIn("  2  ===\n(lines", out)

    def test_a_hash_line_in_an_rst_code_block_is_not_a_heading(self):
        text = ("Install\n=======\n\nRun these:\n\n.. code-block:: bash\n\n"
                "   # fetch the deps\n   make deps\n\nThen\nrun it.\n")
        out = prose.brief_files([self.doc(((12, 12),), "install.rst")], {"install.rst": text})
        self.assertIn(" 1  Install\n", out)

    def test_a_comment_gets_the_lines_after_it_and_lines_either_side(self):
        reach = prose.BRIEF_CODE_LINES + prose.BRIEF_CONTEXT_LINES
        text = "".join(f"line {n}\n" for n in range(1, 101))
        out = prose.brief_files([self.item("a.py")._replace(spans=((20, 21),))], {"a.py": text})
        self.assertIn("(lines 1-14 left out)\n 15  line 15\n", out)
        self.assertIn(f"{21 + reach}  line {21 + reach}\n(lines {22 + reach}-100 left out)", out)

    def test_a_comment_near_the_end_stops_at_the_last_line(self):
        out = prose.brief_files([self.item("a.py")._replace(spans=((3, 3),))],
                                {"a.py": "a\nb\n# c\nd\n"})
        self.assertIn("1  a\n2  b\n3  # c\n4  d\n--- end a.py ---", out)
        self.assertNotIn("left out", out)

    def test_two_items_close_together_share_one_window(self):
        text = "".join(f"line {n}\n" for n in range(1, 201))
        items = [self.item("a.py")._replace(spans=((10, 10),)),
                 self.item("a.py")._replace(spans=((30, 30),))]
        out = prose.brief_files(items, {"a.py": text})
        self.assertEqual(out.count("left out"), 2)
        self.assertIn("(lines 1-4 left out)", out)
        self.assertIn(f"(lines {31 + prose.BRIEF_CODE_LINES + prose.BRIEF_CONTEXT_LINES}-200 "
                      "left out)", out)

    def test_an_asciidoc_passage_gets_its_section(self):
        text = "= Doc\n" + fill("d", 5) + "== A\n" + fill("a", 100) + "== B\n" + fill("b", 60)
        out = prose.brief_files([self.doc(((60, 60),), "guide.adoc")], {"guide.adoc": text})
        self.assertIn("(lines 1-6 left out)\n  7  == A\n", out)
        self.assertIn("(lines 108-168 left out)", out)

    def test_a_fence_line_with_an_info_string_does_not_close_a_fence(self):
        text = ("# Guide\n" + fill("g", 50) + "## Writing fences\n```\nOpen with:\n```python\n"
                "print(1)\n```\n## Usage\n" + fill("u", 100) + "## Last\n" + fill("l", 60))
        out = prose.brief_files([self.doc(((110, 110),))], {"guide.md": text})
        self.assertIn("(lines 1-57 left out)\n 58  ## Usage\n", out)
        self.assertIn("(lines 159-219 left out)", out)

    def test_a_yaml_comment_is_not_a_heading(self):
        text = "".join(f"k{n}: {n}\n" for n in range(60)) + "# Added at review.\nk60: 60\n"
        out = prose.brief_files([self.doc(((62, 62),), "openspec/config.yaml")],
                                {"openspec/config.yaml": text})
        self.assertIn("--- openspec/config.yaml ---\n 1  k0: 0\n", out)

    def test_a_heading_in_an_html_comment_leaves_the_section_whole(self):
        text = ("# Install\nRun the installer.\n<!--\nold notes\n# Old install steps\n-->\n" +
                fill("x", 100) + "# Use\n" + fill("u", 60))
        out = prose.brief_files([self.doc(((2, 2),), "README.md")], {"README.md": text})
        self.assertIn("106  x99\n(lines 107-167 left out)", out)

    def test_a_comment_in_front_matter_leaves_the_title_in(self):
        text = "---\ntitle: Page\n# draft: true\n---\n" + fill("x", 60)
        out = prose.brief_files([self.doc(((60, 60),), "docs/page.mdx")], {"docs/page.mdx": text})
        self.assertIn(" 2  title: Page\n", out)

    def test_a_heading_in_an_asciidoc_listing_leaves_the_section_whole(self):
        text = ("== Writing\nChanged passage.\n----\n= Example title\n----\n" + fill("m", 100) +
                "== Next\n" + fill("n", 60))
        out = prose.brief_files([self.doc(((2, 2),), "guide.adoc")], {"guide.adoc": text})
        self.assertIn("105  m99\n(lines 106-166 left out)", out)

    def test_an_upper_case_suffix_still_finds_headings(self):
        text = "# A\n" + fill("a", 100) + "# B\n" + fill("b", 60)
        out = prose.brief_files([self.doc(((50, 50),), "README.MD")], {"README.MD": text})
        self.assertIn("(lines 102-162 left out)", out)

    def test_a_misread_heading_hides_nothing_within_the_floor(self):
        cases = {
            "README.md": ("# Project\n\n## Install\n\nSteps follow.\n\n<pre>\n# Clone it\n"
                          "git clone x\n</pre>\n\nThen run make.\n", 12),
            "guide.adoc": ("= Guide\n\n== Nesting\n\nTo nest:\n\n====\n[source,asciidoc]\n----\n"
                           "====\n== Not a section\n----\n====\n\nIt keeps its delimiters.\n", 15),
            "post.md": ("+++\ntitle = 'Post'\n# draft until review\ndraft = true\n+++\n\n"
                        "Intro paragraph.\n\n## Details\n", 7),
            "bom.md": ("\ufeff---\ntitle: Post\n# yaml-language-server: x\n---\n\nIntro.\n\n"
                       "## Details\n", 6),
        }
        for path, (text, line) in cases.items():
            out = prose.brief_files([self.doc(((line, line),), path)], {path: text})
            self.assertNotIn("left out", out, path)

    def test_a_long_html_comment_hides_its_headings(self):
        text = ("# Install\nRun.\n<!--\none\ntwo\n# Hidden\n-->\n" + fill("x", 100) + "# Use\n" +
                fill("u", 60))
        out = prose.brief_files([self.doc(((2, 2),), "README.md")], {"README.md": text})
        self.assertIn("107  x99\n(lines 108-168 left out)", out)

    def test_a_heading_after_a_closed_block_ends_the_section(self):
        text = "---\ntitle: P\n---\n# A\n" + fill("a", 100) + "# B\n" + fill("b", 60)
        out = prose.brief_files([self.doc(((50, 50),))], {"guide.md": text})
        self.assertIn("(lines 105-165 left out)", out)
        text = "== A\n----\ncode\n----\n" + fill("a", 100) + "== B\n" + fill("b", 60)
        out = prose.brief_files([self.doc(((50, 50),), "g.adoc")], {"g.adoc": text})
        self.assertIn("(lines 105-165 left out)", out)

    def test_a_passage_starting_on_a_heading_starts_its_section_there(self):
        text = "# A\n" + fill("a", 100) + "# B\n" + fill("b", 100)
        out = prose.brief_files([self.doc(((102, 103),))], {"guide.md": text})
        self.assertIn("(lines 1-61 left out)", out)

    def test_a_passage_ending_on_a_heading_runs_to_the_next(self):
        text = "# A\n" + fill("a", 100) + "# B\n" + fill("b", 100) + "# C\n" + fill("c", 60)
        out = prose.brief_files([self.doc(((50, 102),))], {"guide.md": text})
        self.assertIn("202  b99\n(lines 203-263 left out)", out)

    def test_a_section_ends_at_the_first_later_sibling(self):
        text = "# A\n" + fill("a", 100) + "# B\n" + fill("b", 100) + "# C\n" + fill("c", 60)
        out = prose.brief_files([self.doc(((50, 50),))], {"guide.md": text})
        self.assertIn("(lines 102-263 left out)", out)

    def test_one_files_items_do_not_widen_anothers(self):
        text = fill("x", 200)
        items = [self.item("a.py")._replace(spans=((10, 10),)),
                 self.item("b.py")._replace(spans=((150, 150),))]
        out = prose.brief_files(items, {"a.py": text, "b.py": text})
        self.assertIn("(lines 56-200 left out)\n--- end a.py ---", out)

    def test_a_passage_gets_the_floor_across_a_near_heading(self):
        text = "# A\n" + fill("a", 100) + "# B\n" + fill("b", 100)
        out = prose.brief_files([self.doc(((95, 95),))], {"guide.md": text})
        self.assertIn("102  # B\n", out)
        self.assertIn("135  b32\n(lines 136-202 left out)", out)

    def test_a_thematic_break_in_markdown_opens_no_block(self):
        text = "# A\n" + fill("a", 50) + "----\n" + fill("b", 50) + "# B\n" + fill("c", 60)
        out = prose.brief_files([self.doc(((50, 50),))], {"guide.md": text})
        self.assertIn("(lines 103-163 left out)", out)

    def test_a_one_line_html_comment_closes_on_its_line(self):
        text = "# A\n" + fill("a", 50) + "<!-- note -->\n" + fill("b", 50) + "# B\n" + fill("c", 60)
        out = prose.brief_files([self.doc(((50, 50),))], {"guide.md": text})
        self.assertIn("(lines 103-163 left out)", out)

    def test_a_post_alone_has_no_files(self):
        self.assertEqual(prose.brief_files([prose.ColdItem("The post below.", ("g",))], {}), "")

    def test_a_brief_that_cannot_be_saved_is_printed_whole(self):
        blocked = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, blocked)
        (blocked / "briefs").write_text("a file, not a directory")
        out = io.StringIO()
        compact.print_brief("cold-read brief", "short", blocked / "briefs", "cold-read", out,
                            "short\nand the files")
        self.assertIn("short\nand the files\n=== end cold-read brief ===", out.getvalue())
        self.assertIn("Brief file: not saved", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)


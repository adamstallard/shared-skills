#!/usr/bin/env python3
"""Tests for verbatim text: files declared `prose-verbatim` in .gitattributes
and marked blocks in a doc are not listed for the pass and get no cold read, the cold reader
never sees them, and the trailer counts what was skipped.

Standard library only, besides the sibling prose_test_support.py:

    python3 test_verbatim.py
"""

import pathlib
import re
import shutil
import sys
import tempfile
import unittest

from prose_test_support import (
    SCRIPT,
    Repo,
    block_trailer,
    compact,
    pass_token,
    prose,
    run,
)

BEGIN, END = "<!-- prose:verbatim begin -->", "<!-- prose:verbatim end -->"


class Verbatim(unittest.TestCase):

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("a.py", "x = 1\n")
        self.repo.commit("base\n")

    def first(self, message="DOCS(x): a\n"):
        return self.repo.prose("check", "-F", "-", "--goals", "review it", stdin=message,
                               file_goals=True)

    def signing(self, token, message="DOCS(x): a\n"):
        return self.repo.prose("check", "-F", "-", "--pass", token, stdin=message,
                               file_goals=False)

    def sign(self, message="DOCS(x): a\n"):
        token = pass_token(self.first(message).stdout)
        return self.signing(token, message)

    def test_a_declared_file_is_skipped_and_counted(self):
        self.repo.write(".gitattributes", "chats/** prose-verbatim\n")
        self.repo.write("chats/one.md", "# Chat\n\nme: hi there\n")
        self.repo.write("chats/two.md", "# Chat two\n\nme: bye\n")
        first = self.first()
        self.assertIn("chats/one.md  (file)", first.stdout)
        self.assertNotIn("chats/one.md  (changed)", first.stdout)
        signed = self.signing(pass_token(first.stdout), "DOCS(x): a\n")
        self.assertEqual(signed.returncode, 0, signed.stderr + signed.stdout)
        self.assertIn("; verbatim: 2 files", signed.stdout)
        self.repo.commit("DOCS(x): a\n", block_trailer(signed.stdout))
        self.assertEqual(self.repo.verify().stdout, "checked\n")

    def test_an_unset_attribute_leaves_a_file_in_the_pass(self):
        self.repo.write(".gitattributes", "*.md prose-verbatim\nkeep.md -prose-verbatim\n")
        self.repo.write("keep.md", "# Keep\n\nOne.\n")
        first = self.first()
        self.assertEqual(first.returncode, 4, first.stderr)
        self.assertNotIn("(file)", first.stdout)

    def test_a_block_is_skipped_and_the_rest_of_the_doc_is_read(self):
        text = f"# Log\n\nWritten now.\n\n{BEGIN}\nme: SENT TEXT\n{END}\n"
        self.repo.write("log.md", text)
        token = pass_token(self.first().stdout)
        needed = self.signing(token)
        self.assertEqual(needed.returncode, prose.COLD_READ_NEEDED, needed.stderr)
        self.assertNotIn("SENT TEXT", needed.stdout)
        self.assertNotIn("SENT TEXT", needed.stderr)

    def test_a_doc_changed_only_inside_a_block_signs_with_no_cold_read(self):
        self.repo.write("log.md", f"# Log\n\n{BEGIN}\nme: one\n{END}\n")
        self.repo.commit("base 2\n")
        self.repo.write("log.md", f"# Log\n\n{BEGIN}\nme: one\nme: two\n{END}\n")
        signed = self.sign()
        self.assertEqual(signed.returncode, 0, signed.stderr + signed.stdout)
        self.assertIn("; verbatim: 1 block", signed.stdout)

    def test_a_block_the_change_does_not_touch_is_not_counted(self):
        self.repo.write("log.md", f"# Log\n\n{BEGIN}\nme: one\n{END}\n\nTail.\n")
        self.repo.commit("base 2\n")
        self.repo.write("log.md", f"# Log\n\n{BEGIN}\nme: one\n{END}\n\nTail, longer.\n")
        token = pass_token(self.first().stdout)
        needed = self.signing(token)
        self.assertEqual(needed.returncode, prose.COLD_READ_NEEDED, needed.stderr)

    def test_a_marker_in_a_code_fence_is_text(self):
        self.repo.write("guide.md", f"# Guide\n\n```\n{BEGIN}\n```\n\nMore.\n")
        needed = self.signing(pass_token(self.first().stdout))
        self.assertEqual(needed.returncode, prose.COLD_READ_NEEDED, needed.stderr)
        self.assertNotIn("; verbatim", needed.stdout)

    def test_a_marker_in_a_sentence_is_text(self):
        self.repo.write("guide.md", "# Guide\n\nWrite `prose:verbatim begin` to start.\n")
        needed = self.signing(pass_token(self.first().stdout))
        self.assertEqual(needed.returncode, prose.COLD_READ_NEEDED, needed.stderr)

    def test_markers_work_in_other_comment_styles(self):
        for begin, end in (("# prose:verbatim begin", "# prose:verbatim end"),
                           (".. prose:verbatim begin", ".. prose:verbatim end"),
                           ("[//]: # (prose:verbatim begin)", "[//]: # (prose:verbatim end)")):
            self.assertEqual(prose.verbatim_blocks("a.md", f"x\n{begin}\ny\n{end}\n"), [(2, 4)])

    def test_unbalanced_markers_are_refused(self):
        for text, reason in ((f"{BEGIN}\nx\n", "no end"),
                             (f"x\n{END}\n", "no begin"),
                             (f"{BEGIN}\n{BEGIN}\n{END}\n", "nest")):
            with self.assertRaises(prose.Refused, msg=reason):
                prose.verbatim_blocks("a.md", text)

    def test_the_cold_reader_never_sees_a_block_in_a_sections_context(self):
        masked = prose.mask_verbatim("log.md", f"# Log\n{BEGIN}\nSECRET\n{END}\nTail.\n")
        self.assertNotIn("SECRET", masked)
        self.assertEqual(masked.count("\n"), 5)

    def test_a_hand_typed_verbatim_part_must_be_in_the_one_form(self):
        for good in ("1 file", "2 files", "1 block", "3 blocks", "2 files, 1 block"):
            self.assertTrue(prose.verbatim_valid(good), good)
        for bad in ("", "0 files", "1 files", "2 file", "1 block, 2 files", "files",
                    "1 file, 0 blocks", "x"):
            self.assertFalse(prose.verbatim_valid(bad), bad)

    def test_a_declared_file_is_never_compacted(self):
        self.repo.write(".gitattributes", "notes.md prose-verbatim\n")
        found = prose.compactor().settings(["notes.md"], str(self.repo.path))
        self.assertTrue(found["notes.md"].binary)

    # The trailer's verbatim counts are recomputed from git, not only
    # checked for form.

    def signed_block_change(self):
        """A change only inside a block, staged and signed; (trailer line, message)."""
        self.repo.write("log.md", f"# Log\n\n{BEGIN}\nme: one\n{END}\n")
        self.repo.commit("base 2\n")
        self.repo.write("log.md", f"# Log\n\n{BEGIN}\nme: one\nme: two\n{END}\n")
        signed = self.sign()
        self.assertEqual(signed.returncode, 0, signed.stderr + signed.stdout)
        return block_trailer(signed.stdout), "DOCS(x): a\n"

    def verify_staged(self, line, message="DOCS(x): a\n"):
        return self.repo.prose("verify-staged", line, stdin=message)

    def test_verify_staged_accepts_the_counts_the_signing_call_printed(self):
        line, message = self.signed_block_change()
        result = self.verify_staged(line, message)
        self.assertEqual((result.returncode, result.stdout), (0, "checked\n"), result.stderr)

    def test_verify_staged_refuses_a_count_the_index_does_not_give(self):
        line, message = self.signed_block_change()
        for forged in (line.replace("; verbatim: 1 block", "; verbatim: 2 blocks"),
                       line.replace("; verbatim: 1 block", "; verbatim: 1 file, 1 block"),
                       line.replace("; verbatim: 1 block", "")):
            result = self.verify_staged(forged, message)
            self.assertEqual(result.returncode, 1, forged)
            self.assertTrue(result.stdout.startswith("tree:"), result.stdout)

    def test_verify_staged_refuses_a_verbatim_part_when_nothing_was_skipped(self):
        self.repo.write("plain.md", "# Plain\n\nOne.\n")
        line = prose.snapshot("DOCS(x): a\n", str(self.repo.path)) + "; verbatim: 1 file"
        result = self.verify_staged(line)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertTrue(result.stdout.startswith("tree:"), result.stdout)

    def test_verify_commit_refuses_a_hand_typed_count(self):
        line, message = self.signed_block_change()
        self.repo.commit(message, line.replace("1 block", "3 blocks"))
        result = self.repo.verify()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertTrue(result.stdout.startswith("tree:"), result.stdout)

    def test_verify_commit_refuses_a_verbatim_part_dropped_by_hand(self):
        line, message = self.signed_block_change()
        self.repo.commit(message, line.replace("; verbatim: 1 block", ""))
        result = self.repo.verify()
        self.assertTrue(result.stdout.startswith("tree:"), result.stdout)

    def test_verify_commit_accepts_the_counts_the_signing_call_printed(self):
        line, message = self.signed_block_change()
        self.repo.commit(message, line)
        self.assertEqual(self.repo.verify().stdout, "checked\n")

    def test_verify_commit_reads_gitattributes_as_of_the_commit(self):
        self.repo.write(".gitattributes", "chats/** prose-verbatim\n")
        self.repo.write("chats/one.md", "# Chat\n\nme: hi there\n")
        signed = self.sign()
        self.assertEqual(signed.returncode, 0, signed.stderr + signed.stdout)
        self.repo.commit("DOCS(x): a\n", block_trailer(signed.stdout))
        sha = self.repo.git("rev-parse", "HEAD").strip()
        # A later commit takes the declaration back; the first commit is
        # still checked against the .gitattributes it holds.
        self.repo.write(".gitattributes", "")
        self.repo.commit("undeclare\n")
        self.assertEqual(self.repo.verify(sha).stdout, "checked\n")
        # A working-tree .gitattributes does not count either.
        (self.repo.path / ".gitattributes").write_text("*.md prose-verbatim\nchats/** -prose-verbatim\n")
        self.assertEqual(self.repo.verify(sha).stdout, "checked\n")

    def test_the_cold_read_brief_shows_a_placeholder_for_a_block(self):
        text = f"# Log\n\nWritten now.\n\n{BEGIN}\nme: SENT\nme: MORE\n{END}\n\nTail line.\n"
        self.repo.write("log.md", text)
        needed = self.signing(pass_token(self.first().stdout))
        self.assertEqual(needed.returncode, prose.COLD_READ_NEEDED, needed.stderr)
        brief = pathlib.Path(re.search(r"^Brief file: (.+)$", needed.stdout, re.M).group(1))
        saved = brief.read_text(encoding="utf-8")
        self.assertNotIn("SENT", saved)
        self.assertIn("5-8  [verbatim block: 4 lines not shown]", saved)
        # Lines around the block keep their own numbers.
        self.assertIn(" 3  Written now.", saved)
        self.assertIn("10  Tail line.", saved)
        for number in (6, 7, 8):
            self.assertIsNone(re.search(rf"^ ?{number}\s*$", saved, re.M), saved)

    # Compaction keeps each verbatim block byte for byte.

    BLOCK = f"{BEGIN}\nme: Previously we said this, and SENT stays.\n{END}\n"

    def compacted(self, after_block):
        before = f"# Doc\n\nRule one holds. Rule two holds too, as said.\n\n{self.BLOCK}\nEnd.\n"
        after = f"# Doc\n\nRule one holds.\n\n{after_block}\nEnd.\n"
        return compact.check_result(before, after, "SKILL.md", None)

    def test_compaction_that_keeps_a_block_passes_its_check(self):
        report = self.compacted(self.BLOCK)
        self.assertEqual(report.failures, [])

    def test_compaction_that_changes_moves_or_drops_a_block_fails(self):
        for after in (self.BLOCK.replace("SENT stays", "SENT"),
                      self.BLOCK.replace(f"{END}\n", "") + f"{END}\n".replace(END, "") + END + "\n",
                      self.BLOCK.replace("me: Previously we said this, and SENT stays.\n", "")
                      + "me: Previously we said this, and SENT stays.\n",
                      self.BLOCK.replace(f"{BEGIN}\n", "").replace(f"{END}\n", ""),
                      ""):
            report = self.compacted(after)
            self.assertTrue(any("verbatim" in failure for failure in report.failures),
                            (after, report.failures))

    def test_compaction_brief_flags_nothing_inside_a_block(self):
        text = (f"# Doc\n\n{BEGIN}\nPreviously, as of 2025-01-01, we used to do X. "
                f"This was later superseded.\n{END}\n")
        self.assertEqual(compact.passages(text, "SKILL.md"), [])

    def test_compaction_brief_says_blocks_are_kept_as_is(self):
        self.assertIn("verbatim", compact.BRIEF.read_text(encoding="utf-8"))


    def test_a_declared_file_counts_the_same_from_a_subdirectory(self):
        self.repo.write(".gitattributes", "docs/*.md prose-verbatim\n")
        self.repo.commit("attrs\n")
        self.repo.write("docs/one.md", "# Chat\n\nme: hi\n")
        signed = self.sign()
        self.assertEqual(signed.returncode, 0, signed.stderr + signed.stdout)
        line = block_trailer(signed.stdout)
        self.assertIn("; verbatim: 1 file", line)
        docs = self.repo.path / "docs"
        staged = run([sys.executable, str(SCRIPT), "verify-staged", line], cwd=docs,
                     stdin="DOCS(x): a\n")
        self.assertEqual(staged.stdout, "checked\n", staged.stderr)
        self.repo.commit("DOCS(x): a\n", line)
        landed = run([sys.executable, str(SCRIPT), "verify-commit", "HEAD"], cwd=docs)
        self.assertEqual(landed.stdout, "checked\n", landed.stderr)

    def test_an_uncommitted_attributes_file_declares_nothing(self):
        info = self.repo.path / ".git" / "info"
        info.mkdir(exist_ok=True)
        (info / "attributes").write_text("*.md prose-verbatim\n")
        self.repo.write("guide.md", "# Guide\n\nProse nobody reviewed.\n")
        first = self.first()
        self.assertNotIn("guide.md  (file)", first.stdout)

    def test_markers_in_an_indented_or_longer_fence_are_text(self):
        for text in ("# Guide\n\n1. Open a block with this line:\n\n   ```\n"
                     f"   {BEGIN}\n   ```\n\n2. Close it later.\n",
                     f"# Guide\n\n````markdown\n```\n{BEGIN}\n```\n````\n\nSome prose.\n"):
            self.assertEqual(prose.verbatim_blocks("guide.md", text), [], text)

    def test_compaction_flags_a_sentence_right_after_a_block(self):
        text = (f"# T\n\n{BEGIN}\nme: hi\n{END}\nWe used to call this the old flow, which "
                f"was previously replaced in 2024 and is no longer used.\n")
        found = compact.passages(text, "SKILL.md")
        self.assertTrue(any(p.start == 6 for p in found), found)
        self.assertFalse(any(p.start <= 5 for p in found), found)

    def test_the_placeholder_counts_a_block_that_ends_the_file(self):
        text = f"# H\n\ntext 3\n{BEGIN}\nSECRET\n{END}"
        item = prose.ColdItem("x", ("g",), "d.md", spans=((3, 3),))
        out = prose.brief_files([item], {"d.md": prose.mask_verbatim("d.md", text)},
                                {"d.md": prose.verbatim_blocks("d.md", text)})
        self.assertIn("4-6  [verbatim block: 3 lines not shown]", out)


    def brief_of(self, text, span):
        item = prose.ColdItem("x", ("g",), "d.md", spans=(span,))
        return prose.brief_files([item], {"d.md": prose.mask_verbatim("d.md", text)},
                                 {"d.md": prose.verbatim_blocks("d.md", text)})

    def long_doc(self, blocks, size=400):
        lines = [f"line {n}" for n in range(1, size + 1)]
        for first, last in blocks:
            lines[first - 1], lines[last - 1] = BEGIN, END
        return "\n".join(lines) + "\n"

    def test_a_block_outside_the_window_does_not_widen_it(self):
        out = self.brief_of(self.long_doc([(10, 12)]), (200, 200))
        self.assertIn("(lines 1-49 left out)", out)
        self.assertNotIn("verbatim block", out)

    def test_nothing_is_shown_after_a_block_that_ends_the_window(self):
        out = self.brief_of(self.long_doc([(348, 350)]), (200, 200))
        self.assertIn("348-350  [verbatim block: 3 lines not shown]", out)
        self.assertNotIn("line 351", out)
        self.assertIn("(lines 351-400 left out)", out)

    def test_a_two_line_block_that_ends_the_file_gets_its_placeholder(self):
        out = self.brief_of(f"# H\n\ntext 3\n{BEGIN}\n{END}", (3, 3))
        self.assertIn("4-5  [verbatim block: 2 lines not shown]", out)

    def test_compaction_that_changes_only_a_begin_marker_fails(self):
        after = self.BLOCK.replace(BEGIN, ".. prose:verbatim begin")
        report = self.compacted(after)
        self.assertTrue(any("verbatim" in failure for failure in report.failures),
                        report.failures)

    def test_a_declared_doc_git_diffs_as_binary_is_counted(self):
        self.repo.write(".gitattributes", "notes.md prose-verbatim -diff\n")
        self.repo.write("notes.md", "# Notes\n\nme: hi\n")
        signed = self.sign()
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.assertIn("; verbatim: 1 file", block_trailer(signed.stdout))

    def test_a_change_to_a_begin_marker_alone_counts_its_block(self):
        self.repo.write("log.md", f"# Log\n\n{BEGIN}\nme: one\n{END}\n")
        self.repo.commit("base 2\n")
        self.repo.write("log.md", f"# Log\n\n.. prose:verbatim begin\nme: one\n{END}\n")
        signed = self.sign()
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.assertIn("; verbatim: 1 block", block_trailer(signed.stdout))

    def test_a_doc_changed_only_inside_a_block_needs_no_goals(self):
        self.repo.write("log.md", f"# Log\n\n{BEGIN}\nme: one\n{END}\n")
        self.repo.commit("base 2\n")
        self.repo.write("log.md", f"# Log\n\n{BEGIN}\nme: one\nme: two\n{END}\n")
        first = self.repo.prose("check", "-F", "-", "--goals", "review it",
                                stdin="DOCS(x): a\n", file_goals=False)
        self.assertEqual(first.returncode, 4, first.stderr)
        self.assertNotIn("log.md  (changed)", first.stdout)

    def test_an_edit_to_a_declared_doc_git_diffs_as_binary_is_counted(self):
        self.repo.write(".gitattributes", "notes.md prose-verbatim -diff\n")
        self.repo.write("notes.md", "# Notes\n\nme: hi\n")
        self.repo.commit("base 2\n")
        self.repo.write("notes.md", "# Notes\n\nme: hi\nme: bye\n")
        signed = self.sign()
        self.assertEqual(signed.returncode, 0, signed.stderr)
        line = block_trailer(signed.stdout)
        self.assertIn("; verbatim: 1 file", line)
        self.repo.commit("DOCS(x): a\n", line)
        self.assertEqual(self.repo.verify().stdout, "checked\n")

    def test_verify_commit_ignores_what_is_staged_since(self):
        self.repo.write(".gitattributes", "chats/** prose-verbatim\n")
        self.repo.write("chats/one.md", "# Chat\n\nme: hi\n")
        self.repo.commit("base 2\n")
        self.repo.git("rm", "-q", "chats/one.md")
        signed = self.sign()
        self.repo.commit("DOCS(x): a\n", block_trailer(signed.stdout))
        self.repo.write("chats/two.md", "# Chat two\n\nme: bye\n")
        self.assertEqual(self.repo.verify().stdout, "checked\n")

    def test_a_malformed_part_is_unrecognised_not_recounted(self):
        line, message = self.signed_block_change()
        for forged in (line.replace("1 block", "1 blocks"),
                       line.replace("; verbatim: 1 block", "; cold read: 3 findings, 9 fixed, 0 kept")):
            staged = self.verify_staged(forged, message)
            self.assertTrue(staged.stdout.startswith("unrecognised"), (forged, staged.stdout))
        self.repo.commit(message, line.replace("; verbatim: 1 block",
                                               "; cold read: 3 findings, 9 fixed, 0 kept"))
        self.assertTrue(self.repo.verify().stdout.startswith("unrecognised"))


    def test_markers_after_a_fence_count_in_a_crlf_doc(self):
        text = f"x\r\n```\r\ncode\r\n```\r\n{BEGIN}\r\ny\r\n{END}\r\n"
        self.assertEqual(prose.verbatim_blocks("a.md", text), [(5, 7)])

    def test_a_macro_applied_in_info_attributes_declares_nothing(self):
        self.repo.write(".gitattributes", "[attr]keep prose-verbatim\n")
        self.repo.commit("attrs\n")
        info = self.repo.path / ".git" / "info"
        info.mkdir(exist_ok=True)
        (info / "attributes").write_text("notes.md keep\n")
        self.repo.write("notes.md", "# Notes\n\nProse nobody reviewed.\n")
        first = self.first()
        self.assertNotIn("notes.md  (file)", first.stdout)
        self.assertIn("info/attributes sets attributes", first.stderr)

    def test_attribute_patterns_match_case_whatever_core_ignorecase_says(self):
        self.repo.git("config", "core.ignorecase", "true")
        self.repo.write(".gitattributes", "Chats/** prose-verbatim\n")
        self.repo.write("chats/one.md", "# Chat\n\nme: hi\n")
        self.assertNotIn("chats/one.md  (file)", self.first().stdout)

    def test_compact_refused_for_unbalanced_markers_starts_nothing(self):
        self.repo.write("SKILL.md", f"# Skill\n\nDo the thing.\n\n{BEGIN}\nme: hi\n\nMore.\n")
        self.repo.commit("base 2\n")
        refused = self.repo.prose("compact", "SKILL.md")
        self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
        self.repo.write("SKILL.md", f"# Skill\n\nDo the thing.\n\n{BEGIN}\nme: hi\n{END}\n\nMore.\n")
        signed = self.sign("DOCS(x): close the block\n")
        self.assertNotIn("compacted but not verified", signed.stderr)
        self.assertEqual(signed.returncode, 0, signed.stderr)


    def test_compact_refuses_a_declared_file(self):
        self.repo.write(".gitattributes", "chats/** prose-verbatim\n")
        self.repo.write("chats/one.md", "# Chat\n\nme: previously we did it by hand.\n")
        self.repo.commit("base 2\n")
        refused = self.repo.prose("compact", "chats/one.md", "--")
        self.assertEqual(refused.returncode, 2, refused.stdout[-400:] + refused.stderr)
        self.assertIn("verbatim", refused.stderr)

    def test_a_change_that_only_deletes_a_marker_is_refused(self):
        self.repo.write("log.md", f"# Log\n{BEGIN}\nme: one\n{END}\n\nTail.\n")
        self.repo.commit("base 2\n")
        self.repo.write("log.md", f"# Log\n{BEGIN}\nme: one\n\nTail.\n")
        first = self.first()
        self.assertEqual(first.returncode, 2, first.stdout[-400:])
        self.assertIn("log.md:2: a prose:verbatim begin with no end", first.stderr)

    # A change that only deletes lines in a block, or on its markers, touches it.

    def deleted_from(self, before, after):
        self.repo.write("log.md", before)
        self.repo.commit("base 2\n")
        self.repo.write("log.md", after)

    def test_deleting_two_markers_that_merge_blocks_counts_the_block(self):
        self.deleted_from(f"# Log\n\n{BEGIN}\nme: one\n{END}\n\nWe now ship weekly.\n\n"
                          f"{BEGIN}\nme: two\n{END}\n",
                          f"# Log\n\n{BEGIN}\nme: one\n\nWe now ship weekly.\n\n"
                          f"me: two\n{END}\n")
        signed = self.sign()
        self.assertEqual(signed.returncode, 0, signed.stderr)
        line = block_trailer(signed.stdout)
        self.assertIn("; verbatim: 1 block", line)
        self.repo.commit("DOCS(x): a\n", line)
        self.assertEqual(self.repo.verify().stdout, "checked\n")

    def test_deleting_a_line_inside_a_block_counts_it_and_lists_nothing(self):
        self.deleted_from(f"# Log\n\n{BEGIN}\nme: one\nme: two\n{END}\n",
                          f"# Log\n\n{BEGIN}\nme: one\n{END}\n")
        first = self.repo.prose("check", "-F", "-", "--goals", "review it",
                                stdin="DOCS(x): a\n", file_goals=False)
        self.assertEqual(first.returncode, 4, first.stderr)
        self.assertNotIn("log.md  (changed)", first.stdout)
        signed = self.signing(pass_token(first.stdout))
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.assertIn("; verbatim: 1 block", block_trailer(signed.stdout))

    def test_deleting_a_whole_block_counts_it(self):
        self.deleted_from(f"# Log\n\nKept.\n\n{BEGIN}\nme: one\n{END}\n",
                          "# Log\n\nKept.\n\n")
        signed = self.sign()
        self.assertEqual(signed.returncode, 0, signed.stderr)
        line = block_trailer(signed.stdout)
        self.assertIn("; verbatim: 1 block", line)
        self.repo.commit("DOCS(x): a\n", line)
        self.assertEqual(self.repo.verify().stdout, "checked\n")

    def test_replacing_a_whole_block_with_prose_counts_it(self):
        self.deleted_from(f"# Log\n\n{BEGIN}\nme: secret\nme: two\n{END}\n\nTail.\n",
                          "# Log\n\nNew prose line.\n\nTail.\n")
        token = pass_token(self.first().stdout)
        needed = self.signing(token)
        self.assertEqual(needed.returncode, prose.COLD_READ_NEEDED, needed.stderr)
        self.assertIn("log.md, the changed lines 3,", needed.stdout)
        verbatim = prose.Verbatim()
        prose.prose_in(str(self.repo.path), prose.commit_parents(str(self.repo.path)),
                       lambda path: prose.read_staged(path, str(self.repo.path)), verbatim,
                       comments=False)
        self.assertEqual(verbatim.trailer(), "; verbatim: 1 block")

    def test_deleting_only_the_markers_reads_the_text_they_held(self):
        self.deleted_from(f"# Log\n\n{BEGIN}\nme: secret\nme: two\n{END}\n\nTail.\n",
                          "# Log\n\nme: secret\nme: two\n\nTail.\n")
        token = pass_token(self.first().stdout)
        needed = self.signing(token)
        self.assertEqual(needed.returncode, prose.COLD_READ_NEEDED, needed.stderr)
        self.assertIn("log.md, the changed lines 3-4,", needed.stdout)

    def block_count(self):
        return self.read_cold()[1]

    def read_cold(self):
        """(the runs of lines each listed doc is read cold for, the block labels)."""
        verbatim = prose.Verbatim()
        root = str(self.repo.path)
        items, _ = prose.prose_in(root, prose.commit_parents(root),
                                  lambda path: prose.read_staged(path, root), verbatim,
                                  comments=False)
        return {item.path: item.spans for item in items if item.path}, verbatim.blocks


    def test_unmarking_a_block_and_adding_one_counts_both_however_git_pairs_lines(self):
        self.deleted_from(f"# L\n{BEGIN}\na\nc\n{END}\nrest\n",
                          "# L\na\n.. prose:verbatim begin\nx\n.. prose:verbatim end\nc\nrest\n")
        self.assertEqual(self.read_cold(),
                         ({"log.md": ((2, 2), (6, 6))}, ["log.md:3-5", "log.md:2-5 (removed)"]))

    def test_splitting_a_block_reads_the_text_between_the_halves(self):
        self.deleted_from(f"# L\n\n{BEGIN}\nq1\nq2\nfreed one\nfreed two\nq3\n{END}\n",
                          f"# L\n\n{BEGIN}\nq1\nq2\n{END}\nfreed one\nfreed two\n{BEGIN}\nq3\n{END}\n")
        self.assertEqual(self.read_cold(),
                         ({"log.md": ((7, 8),)}, ["log.md:3-6", "log.md:9-11"]))

    def test_splitting_a_block_beside_another_change_reads_both(self):
        self.deleted_from(f"# L\n\nold tail\n{BEGIN}\nq1\nfreed\nq3\n{END}\n",
                          f"# L\n\n{BEGIN}\nq1\n{END}\nfreed\n{BEGIN}\nq3\n{END}\n")
        self.assertEqual(self.read_cold()[0], {"log.md": ((6, 6),)})

    # Markers in a doc git diffs as binary are refused: no hunks show which
    # block a change touched.

    def test_markers_in_a_doc_marked_minus_diff_are_refused(self):
        self.repo.write(".gitattributes", "*.md -diff\n")
        self.repo.write("log.md", f"p1\n{BEGIN}\nv1\n{END}\np2\n")
        self.repo.commit("base 2\n")
        self.repo.write("log.md", f"p1\n{BEGIN}\nv2 changed\n{END}\np2\n")
        first = self.first()
        self.assertEqual(first.returncode, 2, first.stdout[-400:])
        self.assertIn("log.md: git diffs this doc as binary", first.stderr)
        self.assertIn("prose-verbatim", first.stderr)

    def test_markers_in_a_doc_holding_a_nul_byte_are_refused(self):
        self.repo.write("log.md", f"p1\n{BEGIN}\nv1\n{END}\np2\n")
        self.repo.commit("base 2\n")
        self.repo.write("log.md", f"p1\x00\n{BEGIN}\nv1\n{END}\np2\n")
        first = self.first()
        self.assertEqual(first.returncode, 2, first.stdout[-400:])
        self.assertIn("log.md: git diffs this doc as binary", first.stderr)

    def test_a_commit_with_markers_in_a_binary_doc_is_refused_by_verify_commit(self):
        self.repo.write(".gitattributes", "*.md -diff\n")
        self.repo.write("log.md", f"p1\n{BEGIN}\nv1\n{END}\np2\n")
        self.repo.commit("base 2\n")
        self.repo.write("log.md", f"p1\n{BEGIN}\nv2\n{END}\np2\n")
        self.repo.commit("DOCS(x): a\n", "Prose: ✓ 000000000000:000000000000")
        root = str(self.repo.path)
        sha = self.repo.git("rev-parse", "HEAD").strip()
        with self.assertRaises(prose.Refused) as caught:
            prose.prose_in(root, [sha + "~1"], lambda path: self.repo.git("show", f"{sha}:{path}"),
                           prose.Verbatim(), source=sha, comments=False)
        self.assertIn("log.md: git diffs this doc as binary", str(caught.exception))

    def test_a_binary_doc_with_no_markers_is_still_listed(self):
        self.repo.write(".gitattributes", "*.md -diff\n")
        self.repo.write("log.md", "p1\np2\n")
        self.repo.commit("base 2\n")
        self.repo.write("log.md", "p1\np3\n")
        self.assertEqual(self.read_cold(), ({"log.md": ()}, []))

    # A file that stops being declared verbatim gets the pass on its whole text.

    def declared_then(self):
        self.repo.write(".gitattributes", "chats/** prose-verbatim\n")
        self.repo.write("chats/a.md", "# Chat\n\nme: hello\n")
        self.repo.commit("base 2\n")

    def test_a_file_renamed_out_of_a_verbatim_pattern_is_read_whole(self):
        self.declared_then()
        self.repo.git("mv", "chats/a.md", "notes.md")
        self.assertEqual(self.read_cold(), ({"notes.md": ((1, 3),)}, []))

    def test_a_file_renamed_out_and_edited_is_read_whole(self):
        self.declared_then()
        self.repo.git("mv", "chats/a.md", "notes.md")
        self.repo.write("notes.md", "# Chat\n\nme: hello\nme: bye\n")
        self.assertEqual(self.read_cold(), ({"notes.md": ((1, 4),)}, []))

    def test_a_removed_declaration_reads_the_file_whole(self):
        self.declared_then()
        self.repo.write(".gitattributes", "*.bin binary\n")
        self.assertEqual(self.read_cold(), ({"chats/a.md": ((1, 3),)}, []))

    def test_a_file_renamed_within_a_verbatim_pattern_stays_skipped(self):
        self.declared_then()
        self.repo.git("mv", "chats/a.md", "chats/b.md")
        self.assertEqual(self.read_cold(), ({}, []))

    def test_an_undeclared_file_s_blocks_stay_skipped(self):
        self.repo.write(".gitattributes", "chats/** prose-verbatim\n")
        self.repo.write("chats/a.md", f"# Chat\n{BEGIN}\nkeep\n{END}\nme: hello\n")
        self.repo.commit("base 2\n")
        self.repo.write(".gitattributes", "*.bin binary\n")
        self.assertEqual(self.read_cold(), ({"chats/a.md": ((1, 1), (5, 5))}, ["chats/a.md:2-4"]))

    def test_info_attributes_does_not_refuse_a_change_that_ends_no_declaration(self):
        self.declared_then()
        info = self.repo.path / ".git" / "info"
        info.mkdir(exist_ok=True)
        (info / "attributes").write_text("*.bin binary\n")
        self.repo.write("other.md", "# Other\n\nA line.\n")
        self.repo.commit("other\n")
        self.repo.git("mv", "other.md", "moved.md")
        self.repo.write("notes.md", "# Notes\n\nNew.\n")
        self.assertEqual(self.read_cold(), ({"notes.md": ((1, 3),)}, []))

    def test_working_tree_attributes_do_not_decide_binary_for_a_commit(self):
        self.repo.write("notes.md", f"p1\n{BEGIN}\nv1\n{END}\np2\n")
        self.repo.commit("base 2\n")
        self.repo.write("notes.md", f"p1\n{BEGIN}\nv2\n{END}\np2\n")
        self.repo.commit("DOCS(x): a\n")
        sha = self.repo.git("rev-parse", "HEAD").strip()
        (self.repo.path / ".gitattributes").write_text("*.md -diff\n")
        verbatim = prose.Verbatim()
        prose.prose_in(str(self.repo.path), [sha + "~1"],
                       lambda path: self.repo.git("show", f"{sha}:{path}"),
                       verbatim, source=sha, comments=False)
        self.assertEqual(verbatim.blocks, ["notes.md:2-4"])

    def test_an_untracked_minus_diff_does_not_refuse_staged_markers(self):
        self.repo.write("notes.md", f"p1\n{BEGIN}\nv1\n{END}\np2\n")
        (self.repo.path / ".gitattributes").write_text("*.md -diff\n")
        first = self.first()
        self.assertEqual(first.returncode, 4, first.stderr[-400:])

    def test_a_staged_minus_diff_missing_from_the_working_tree_refuses(self):
        self.repo.write(".gitattributes", "*.md -diff\n")
        (self.repo.path / ".gitattributes").unlink()
        self.repo.write("notes.md", f"p1\n{BEGIN}\nv1\n{END}\np2\n")
        first = self.first()
        self.assertEqual(first.returncode, 2, first.stdout[-400:])
        self.assertIn("notes.md: git diffs this doc as binary", first.stderr)

    def test_markers_in_a_utf16_doc_are_refused(self):
        path = self.repo.path / "notes.md"
        path.write_bytes(f"p1\n{BEGIN}\nv1\n{END}\np2\n".encode("utf-16"))
        self.repo.git("add", "notes.md")
        first = self.first()
        self.assertEqual(first.returncode, 2, first.stdout[-400:])
        self.assertIn("notes.md: git diffs this doc as binary", first.stderr)

    def test_an_nfd_directory_does_not_hide_an_undeclared_file(self):
        self.repo.git("config", "core.precomposeUnicode", "false")
        self.repo.write("zone/.gitattributes", "x.md prose-verbatim\n")
        self.repo.write("zone/x.md", "# X\n\nme: hi\n")
        self.repo.write("cafe\u0301/.gitattributes", "*.png binary\n")
        self.repo.commit("base 2\n")
        self.repo.git("config", "core.precomposeUnicode", "true")
        self.repo.git("mv", "zone/x.md", "x.md")
        self.assertEqual(self.read_cold(), ({"x.md": ((1, 3),)}, []))

    def test_info_attributes_does_not_refuse_an_unrelated_gitattributes_edit(self):
        self.declared_then()
        info = self.repo.path / ".git" / "info"
        info.mkdir(exist_ok=True)
        (info / "attributes").write_text("*.bin -diff\n")
        self.repo.write(".gitattributes", "chats/** prose-verbatim\n*.png binary\n")
        self.assertEqual(self.read_cold(), ({}, []))

    def test_a_symlink_renamed_out_of_a_pattern_has_no_passage(self):
        self.repo.write(".gitattributes", "keep/** prose-verbatim\n")
        (self.repo.path / "keep").mkdir()
        (self.repo.path / "keep" / "link.md").symlink_to("../README.md")
        self.repo.git("add", "keep/link.md")
        self.repo.commit("base 2\n")
        self.repo.git("mv", "keep/link.md", "link2.md")
        self.assertEqual(self.read_cold(), ({"link2.md": ()}, []))

    def test_working_tree_attributes_do_not_decide_a_declared_code_file_s_count(self):
        self.repo.write(".gitattributes", "gen.py prose-verbatim\n")
        self.repo.write("gen.py", "# a comment here\nx = 1\n")
        (self.repo.path / ".gitattributes").write_text("gen.py prose-verbatim -diff\n")
        verbatim = prose.Verbatim()
        root = str(self.repo.path)
        prose.prose_in(root, prose.commit_parents(root),
                       lambda path: prose.read_staged(path, root), verbatim, comments=False)
        self.assertEqual(verbatim.files, ["gen.py"])

    def test_markers_in_a_utf16_doc_named_like_a_stage_are_refused(self):
        path = self.repo.path / "1:notes.md"
        path.write_bytes(f"p1\n{BEGIN}\nv1\n{END}\np2\n".encode("utf-16-le"))
        self.repo.git("add", "1:notes.md")
        first = self.first()
        self.assertEqual(first.returncode, 2, first.stdout[-400:])
        self.assertIn("1:notes.md: git diffs this doc as binary", first.stderr)

    def test_markers_in_a_utf32_doc_are_refused(self):
        for encoding in ("utf-32-le", "utf-32-be"):
            path = self.repo.path / "notes.md"
            path.write_bytes(f"p1\n{BEGIN}\nv1\n{END}\np2\n".encode(encoding))
            self.repo.git("add", "notes.md")
            first = self.first()
            self.assertEqual(first.returncode, 2, encoding + first.stdout[-400:])

    def test_working_tree_attributes_do_not_decide_rename_pairing_for_a_commit(self):
        self.repo.write(".gitattributes", "legacy/** prose-verbatim\n")
        prose_lines = "".join(f"prose line {n} with some words\r\n" for n in range(12))
        self.repo.write("legacy/a.md", prose_lines + f"{BEGIN}\nkept\n{END}\n")
        self.repo.commit("base 2\n")
        (self.repo.path / "docs").mkdir()
        self.repo.git("mv", "legacy/a.md", "docs/b.md")
        self.repo.write("docs/b.md", prose_lines.replace("\r\n", "\n") + f"{BEGIN}\nkept\n{END}\n")
        self.repo.commit("DOCS(x): a\n")
        sha = self.repo.git("rev-parse", "HEAD").strip()

        def blocks():
            verbatim = prose.Verbatim()
            prose.prose_in(str(self.repo.path), [sha + "~1"],
                           lambda path: self.repo.git("show", f"{sha}:{path}"),
                           verbatim, source=sha, comments=False)
            return verbatim.blocks
        before = blocks()
        (self.repo.path / ".gitattributes").write_text("legacy/** prose-verbatim -diff\n")
        self.assertEqual(blocks(), before)
        self.assertEqual(before, ["docs/b.md:13-15"])

    def test_a_utf16_doc_that_only_mentions_the_marker_is_not_refused(self):
        path = self.repo.path / "notes.md"
        path.write_bytes("# Notes\n\nWrap it in `prose:verbatim begin` and `prose:verbatim end` "
                         "lines.\n".encode("utf-16"))
        self.repo.git("add", "notes.md")
        first = self.first()
        self.assertEqual(first.returncode, 4, first.stderr[-400:])

    def test_a_removed_declaration_reads_an_edited_file_whole(self):
        self.declared_then()
        self.repo.write(".gitattributes", "*.bin binary\n")
        self.repo.write("chats/a.md", "# Chat\n\nme: hello\nme: bye\n")
        self.assertEqual(self.read_cold(), ({"chats/a.md": ((1, 4),)}, []))

    def test_deleting_a_declared_file_while_editing_gitattributes_is_not_an_error(self):
        self.declared_then()
        self.repo.git("rm", "-q", "chats/a.md")
        self.repo.write(".gitattributes", "chats/** prose-verbatim\n*.bin binary\n")
        self.assertEqual(self.read_cold(), ({}, []))

    def test_a_rename_within_a_verbatim_pattern_counts_no_file(self):
        self.declared_then()
        self.repo.git("mv", "chats/a.md", "chats/b.md")
        verbatim = prose.Verbatim()
        root = str(self.repo.path)
        prose.prose_in(root, prose.commit_parents(root),
                       lambda path: prose.read_staged(path, root), verbatim, comments=False)
        self.assertEqual(verbatim.files, [])

    def test_a_binary_doc_that_shows_a_marker_in_a_fence_is_not_refused(self):
        self.repo.write(".gitattributes", "*.md -diff\n")
        self.repo.write("notes.md", f"# Notes\n\n```\n{BEGIN}\n```\n")
        first = self.first()
        self.assertEqual(first.returncode, 4, first.stderr[-400:])

    def merge_editing_a_block(self, attributes=None):
        if attributes:
            self.repo.write(".gitattributes", attributes)
        self.repo.write("doc.md", f"# T\n\nIntro.\n\n{BEGIN}\nKeep.\n{END}\n\nOutro.\n")
        self.repo.commit("base 2\n")
        self.repo.git("checkout", "-q", "-b", "side")
        self.repo.write("doc.md", f"# T\n\nIntro two.\n\n{BEGIN}\nKeep.\n{END}\n\nOutro.\n")
        self.repo.commit("side\n")
        self.repo.git("checkout", "-q", "-")
        self.repo.write("doc.md", f"# T\n\nIntro.\n\n{BEGIN}\nKeep.\n{END}\n\nOutro two.\n")
        self.repo.commit("main\n")
        self.repo.git("merge", "-q", "--no-commit", "--no-ff", "side")
        self.repo.write("doc.md",
                        f"# T\n\nIntro two.\n\n{BEGIN}\nKeep evil.\n{END}\n\nOutro two.\n")

    def test_working_tree_attributes_do_not_decide_a_merge_s_counts(self):
        self.merge_editing_a_block()
        before = self.block_count()
        (self.repo.path / ".gitattributes").write_text("*.md -diff\n")
        self.assertEqual(self.block_count(), before)
        self.assertEqual(before, ["doc.md:5-7"])

    def test_markers_in_a_binary_doc_are_refused_in_a_merge(self):
        self.merge_editing_a_block("*.md -diff\n")
        with self.assertRaises(prose.Refused) as caught:
            self.block_count()
        self.assertIn("doc.md: git diffs this doc as binary", str(caught.exception))

    def test_markers_in_a_utf16_doc_diffed_as_text_are_refused(self):
        self.repo.write(".gitattributes", "*.md diff\n")
        self.repo.commit("attrs\n")
        path = self.repo.path / "notes.md"
        path.write_bytes(f"p1\n{BEGIN}\nv1\n{END}\np2\n".encode("utf-16"))
        self.repo.git("add", "notes.md")
        first = self.first()
        self.assertEqual(first.returncode, 2, first.stdout[-400:])
        self.assertIn("notes.md: git diffs this doc as binary", first.stderr)

    def test_a_merge_doc_a_binary_diff_driver_marks_is_refused(self):
        self.repo.git("config", "diff.foo.binary", "true")
        self.merge_editing_a_block("*.md diff=foo\n")
        with self.assertRaises(prose.Refused) as caught:
            self.block_count()
        self.assertIn("doc.md: git diffs this doc as binary", str(caught.exception))

    def test_a_merge_taking_one_side_s_binary_doc_with_the_other_s_mode_is_not_refused(self):
        for attributes in ("*.md -diff\n", "*.md diff=foo\n"):
            with self.subTest(attributes=attributes):
                self.setUp()
                self.repo.git("config", "diff.foo.binary", "true")
                self.repo.write(".gitattributes", attributes)
                self.repo.write("doc.md", f"# T\n\nIntro.\n\n{BEGIN}\nKeep.\n{END}\n")
                self.repo.commit("base 2\n")
                self.repo.git("checkout", "-q", "-b", "side")
                self.repo.write("doc.md", f"# T\n\nIntro A.\n\n{BEGIN}\nKeep.\n{END}\n")
                self.repo.commit("side\n")
                self.repo.git("checkout", "-q", "-")
                (self.repo.path / "doc.md").chmod(0o755)
                self.repo.git("add", "doc.md")
                self.repo.commit("mode\n")
                self.repo.git("merge", "-q", "--no-commit", "--no-ff", "side")
                self.assertEqual(self.block_count(), [])

    def test_an_undeclared_file_is_read_whole_in_a_commit_too(self):
        self.declared_then()
        self.repo.git("mv", "chats/a.md", "notes.md")
        staged = self.read_cold()
        self.repo.commit("DOCS(x): a\n")
        root = str(self.repo.path)
        sha = self.repo.git("rev-parse", "HEAD").strip()
        items, _ = prose.prose_in(root, [sha + "~1"],
                                  lambda path: self.repo.git("show", f"{sha}:{path}"),
                                  prose.Verbatim(), source=sha, comments=False)
        self.assertEqual(({item.path: item.spans for item in items if item.path}, []), staged)

    def test_merging_two_blocks_lists_no_doc(self):
        self.deleted_from(f"# L\n{BEGIN}\na\n{END}\n{BEGIN}\nb\n{END}\n",
                          f"# L\n{BEGIN}\na\nb\n{END}\n")
        self.assertEqual(self.read_cold(), ({}, ["log.md:2-5"]))

    def test_moving_a_begin_marker_down_reads_the_lines_it_left(self):
        self.deleted_from(f"# L\n{BEGIN}\nx\nx2\n{END}\n",
                          f"# L\nx\nx2\n{BEGIN}\n{END}\n")
        self.assertEqual(self.read_cold(), ({"log.md": ((2, 3),)}, ["log.md:4-5"]))

    def test_a_block_inserted_after_an_unmarked_line_reads_that_line(self):
        self.deleted_from(f"# L\n{BEGIN}\na\nb\nc\nd\n{END}\n",
                          f"# L\na\nb\n{BEGIN}\nx\n{END}\nc\nd\n")
        self.assertEqual(self.read_cold(), ({"log.md": ((2, 3), (7, 8))},
                                           ["log.md:4-6", "log.md:2-7 (removed)"]))

    def test_unmarking_a_block_beside_a_new_one_counts_both(self):
        self.deleted_from(f"# L\n{BEGIN}\na\n{END}\nrest\n",
                          "# L\na\n.. prose:verbatim begin\nx\n.. prose:verbatim end\nrest\n")
        self.assertEqual(self.read_cold(),
                         ({"log.md": ((2, 2),)}, ["log.md:3-5", "log.md:2-4 (removed)"]))

    def test_deleting_a_block_s_last_line_and_adding_one_counts_it_once(self):
        self.deleted_from(f"# L\n{BEGIN}\na\nb\nc\nd\n{END}\n",
                          f"# L\n{BEGIN}\na\nNEW\nb\nc\n{END}\n")
        self.assertEqual(self.block_count(), ["log.md:2-7"])

    def test_deleting_a_block_s_first_line_and_adding_one_counts_it_once(self):
        self.deleted_from(f"# L\n{BEGIN}\na\nb\nc\nd\n{END}\n",
                          f"# L\n{BEGIN}\nb\nc\nNEW\nd\n{END}\n")
        self.assertEqual(self.block_count(), ["log.md:2-7"])

    def test_an_added_line_shown_as_a_header_does_not_hide_a_later_hunk(self):
        self.deleted_from(f"# L\n\nx\n\n{BEGIN}\na\nb\n{END}\n",
                          f"# L\n\n++ new\n\n{BEGIN}\na\n{END}\n")
        self.assertEqual(self.block_count(), ["log.md:5-7"])

    def test_compact_outside_a_repository_ignores_the_working_directory(self):
        self.repo.write(".gitattributes", "notes.md prose-verbatim\n")
        self.repo.commit("attrs\n")
        outside = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        (outside / "notes.md").write_text("# Notes\n\nSome rules hold.\n")
        brief = run([sys.executable, str(SCRIPT), "compact", str(outside / "notes.md"), "--"],
                    cwd=self.repo.path)
        self.assertEqual(brief.returncode, 4, brief.stderr)

    def test_compact_refuses_a_declared_file_while_info_attributes_sets_any(self):
        self.repo.write(".gitattributes", "notes.md prose-verbatim\n")
        self.repo.write("notes.md", "# Notes\n\nSome rules hold.\n")
        self.repo.commit("base 2\n")
        info = self.repo.path / ".git" / "info"
        info.mkdir(exist_ok=True)
        (info / "attributes").write_text("*.bin binary\n")
        refused = self.repo.prose("compact", "notes.md")
        self.assertEqual(refused.returncode, 2, refused.stdout[-300:])
        self.assertIn("info/attributes sets attributes", refused.stderr)

    def test_deleting_a_line_outside_blocks_still_lists_the_doc(self):
        self.deleted_from(f"# Log\n\n{BEGIN}\nme: one\n{END}\n\nTail.\n",
                          f"# Log\n\n{BEGIN}\nme: one\n{END}\n")
        first = self.repo.prose("check", "-F", "-", "--goals", "review it",
                                stdin="DOCS(x): a\n", file_goals=False)
        self.assertEqual(first.returncode, 2, first.stdout[-300:])
        self.assertIn("log.md", first.stderr)

    def test_compaction_settings_read_verbatim_as_prose_does(self):
        self.repo.write(".gitattributes", "notes.md prose-verbatim\nChats/** prose-verbatim\n")
        self.repo.git("config", "core.ignorecase", "true")
        found = compact.settings(["notes.md", "chats/one.md"], str(self.repo.path))
        self.assertTrue(found["notes.md"].verbatim)
        self.assertFalse(found["chats/one.md"].verbatim)


if __name__ == "__main__":
    unittest.main()

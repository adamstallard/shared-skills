#!/usr/bin/env python3
"""Tests for verbatim text: files declared `prose-verbatim` in .gitattributes
and marked blocks in a doc are not listed for the pass and get no cold read, the cold reader
never sees them, and the trailer counts what was skipped.

Standard library only, besides the sibling prose_test_support.py:

    python3 test_verbatim.py
"""

import unittest

from prose_test_support import (
    Repo,
    block_trailer,
    pass_token,
    prose,
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


if __name__ == "__main__":
    unittest.main()

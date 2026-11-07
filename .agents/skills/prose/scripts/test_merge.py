#!/usr/bin/env python3
"""Tests for what `prose check` lists for a merge commit: only the text
where the staged result differs from every parent, as git's combined diff
(`git diff --cc`) shows it. Covers a merge in progress, `--amend` of a
merge commit and an octopus merge, and checks that a commit with one parent
lists what it always has.

Standard library only:

    python3 test_merge.py
"""

import random
import unittest

from prose_test_support import (
    Repo,
    cold_read,
    pass_token,
    prose,
    repeated,
)

LINES = [f"Line {n} says one thing." for n in range(12)]


def doc(lines):
    return "".join(f"{line}\n" for line in lines)


def changed(lines, edits):
    """lines with each {index: text} of edits put in."""
    out = list(lines)
    for index, text in edits.items():
        out[index] = text
    return out


class MergeRepo(Repo):
    """A repository with a base commit, and helpers that build two or more
    branches from it and start merging them into the first."""

    def __init__(self):
        super().__init__()
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        self.write("README.md", doc(LINES))
        self.write("a.py", "# The first comment.\nx = 1\n\n\n\n\n# The second comment.\ny = 2\n")
        self.commit("base\n")

    def branch(self, name, files):
        """Commit files ({path: text}) on a new branch name from main's
        base commit."""
        self.git("checkout", "-q", "-b", name, "main")
        for path, text in files.items():
            self.write(path, text)
        self.commit(f"{name}\n")
        self.git("checkout", "-q", "main")

    def on_main(self, files):
        for path, text in files.items():
            self.write(path, text)
        self.commit("main side\n")

    def start_merge(self, *branches, result=None):
        """Merge branches into main without committing. With result
        ({path: text}), the merge keeps main's tree (`-s ours`) and stages
        result over it, so a test can stage any outcome."""
        if result is None:
            run = ["merge", "-q", "--no-commit", "--no-ff", *branches]
        else:
            run = ["merge", "-q", "--no-commit", "--no-ff", "-s", "ours", *branches]
        self.git(*run)
        for path, text in (result or {}).items():
            self.write(path, text)

    def listed(self, amend=False):
        """{path: listed line numbers} for every item but the message, from
        prose_in on the commit's parents."""
        root = str(self.path)
        items, _ = prose.prose_in(root, prose.commit_parents(root, amend),
                                  lambda path: prose.git(["show", f":0:{path}"], root))
        return {item.path: {n for first, last in item.spans for n in range(first, last + 1)}
                for item in items if item.path is not None}

    def first_call(self, *extra):
        return self.prose("check", "-F", "-", "--goals", "review it", *extra, stdin="Merge\n")


class MergeListing(unittest.TestCase):
    """A merge lists only what it changed itself."""

    def setUp(self):
        self.repo = MergeRepo()
        self.addCleanup(self.repo.cleanup)

    def test_a_merge_without_conflicts_lists_nothing_from_either_side(self):
        self.repo.branch("side", {"README.md": doc(changed(LINES, {9: "Side wrote this."})),
                                  "side.md": "# Side\n\nA new doc.\n",
                                  "a.py": "# The first comment.\nx = 1\n\n\n\n\n"
                                          "# Side rewrote the second comment.\ny = 2\n"})
        self.repo.on_main({"README.md": doc(changed(LINES, {1: "Main wrote this."})),
                           "a.py": "# Main rewrote the first comment.\nx = 1\n\n\n\n\n"
                                   "# The second comment.\ny = 2\n"})
        self.repo.start_merge("side")
        self.assertEqual(self.repo.listed(), {})
        out = self.repo.first_call().stdout
        self.assertIn("  commit message\n", out)
        for path in ("README.md", "side.md", "a.py"):
            self.assertNotIn(f"  {path}", out)

    def test_a_conflict_resolution_is_listed_and_the_rest_is_not(self):
        self.repo.branch("side", {"README.md": doc(changed(LINES, {2: "Side says two.",
                                                                    9: "Side wrote nine."}))})
        self.repo.on_main({"README.md": doc(changed(LINES, {2: "Main says two."}))})
        with self.assertRaises(AssertionError):
            self.repo.start_merge("side")
        self.repo.write("README.md", doc(changed(LINES, {2: "Both say two.",
                                                          9: "Side wrote nine."})))
        self.assertEqual(self.repo.listed(), {"README.md": {3}})

    def test_a_resolution_that_takes_one_side_lists_nothing(self):
        self.repo.branch("side", {"README.md": doc(changed(LINES, {2: "Side says two."}))})
        self.repo.on_main({"README.md": doc(changed(LINES, {2: "Main says two."}))})
        with self.assertRaises(AssertionError):
            self.repo.start_merge("side")
        self.repo.write("README.md", doc(changed(LINES, {2: "Side says two."})))
        self.assertEqual(self.repo.listed(), {})

    def test_a_resolution_mixing_lines_from_both_sides_is_listed(self):
        # Each line is one side's, but the passage is neither side's.
        self.repo.branch("side", {"README.md": doc(changed(LINES, {2: "Side two.", 3: "Side three."}))})
        self.repo.on_main({"README.md": doc(changed(LINES, {2: "Main two.", 3: "Main three."}))})
        with self.assertRaises(AssertionError):
            self.repo.start_merge("side")
        self.repo.write("README.md", doc(changed(LINES, {2: "Main two.", 3: "Side three."})))
        self.assertEqual(self.repo.listed(), {"README.md": {3, 4}})

    def test_a_resolution_taking_each_side_a_line_apart_is_listed(self):
        # Ours on line 2, theirs on line 4: each line is one side's, but
        # `git show` prints the passage as one hunk matching neither.
        self.repo.branch("side", {"README.md": doc(changed(LINES, {1: "Side two.", 3: "Side four."}))})
        self.repo.on_main({"README.md": doc(changed(LINES, {1: "Main two.", 3: "Main four."}))})
        with self.assertRaises(AssertionError):
            self.repo.start_merge("side")
        self.repo.write("README.md", doc(changed(LINES, {1: "Main two.", 3: "Side four."})))
        self.assertEqual(self.repo.listed(), {"README.md": {2, 4}})

    def test_a_clean_line_beside_the_merges_own_edit_is_listed_as_git_show_prints_it(self):
        # The accepted cost of context: a line the merged-in branch changed
        # cleanly, within three lines of the merge's own edit, is in its hunk.
        self.repo.branch("side", {"README.md": doc(changed(LINES, {5: "Side wrote six."}))})
        self.repo.on_main({"a.py": "# Main's comment.\nx = 1\n\n\n\n\n# The second comment.\ny = 2\n"})
        self.repo.start_merge("side")
        self.repo.write("README.md", doc(changed(LINES, {5: "Side wrote six.", 7: "The merge's eight."})))
        self.assertEqual(self.repo.listed(), {"README.md": {6, 8}})

    def test_an_evil_merge_edit_is_listed(self):
        self.repo.branch("side", {"README.md": doc(changed(LINES, {9: "Side wrote nine."}))})
        self.repo.on_main({"README.md": doc(changed(LINES, {1: "Main wrote one."}))})
        self.repo.start_merge("side")
        self.repo.write("README.md", doc(changed(LINES, {1: "Main wrote one.", 5: "The merge wrote five.",
                                                          9: "Side wrote nine."})))
        self.repo.write("a.py", "# The first comment.\nx = 1\n\n\n\n\n# The merge's own comment.\ny = 2\n")
        self.repo.write("new.md", "Only the merge has this.\n")
        self.assertEqual(self.repo.listed(), {"README.md": {6}, "a.py": {7}, "new.md": {1}})

    def test_a_passage_only_the_second_parent_changed_is_not_listed(self):
        self.repo.branch("side", {"README.md": doc(changed(LINES, {4: "Side wrote four.",
                                                                    5: "And five."}))})
        self.repo.on_main({"a.py": "# Main's comment.\nx = 1\n\n\n\n\n# The second comment.\ny = 2\n"})
        self.repo.start_merge("side")
        self.assertEqual(self.repo.listed(), {})

    def test_the_cold_read_brief_holds_only_the_merges_own_passage(self):
        self.repo.branch("side", {"README.md": doc(changed(LINES, {2: "Side says two.",
                                                                    9: "Side wrote nine."}))})
        self.repo.on_main({"README.md": doc(changed(LINES, {2: "Main says two."}))})
        with self.assertRaises(AssertionError):
            self.repo.start_merge("side")
        self.repo.write("README.md", doc(changed(LINES, {2: "Both say two.",
                                                          9: "Side wrote nine."})))
        first = self.repo.first_call()
        self.assertEqual(first.returncode, 4, first.stderr)
        self.assertIn("  README.md  (changed)\n", first.stdout)
        token = pass_token(first.stdout)
        brief = self.repo.prose("check", "-F", "-", "--pass", token, stdin="Merge\n")
        self.assertEqual(brief.returncode, prose.COLD_READ_NEEDED, brief.stderr)
        self.assertIn("1. A doc passage: README.md, the changed lines 3, each read", brief.stdout)
        signed = cold_read(lambda *cold: self.repo.prose("check", "-F", "-", "--pass", token,
                                                         *cold, stdin="Merge\n"))
        self.assertEqual(signed.returncode, 0, signed.stderr)
        self.assertIn("understood: 1 item, 0 fixed, 0 kept", signed.stdout)

    def test_only_docs_the_merge_changed_need_goals(self):
        self.repo.branch("side", {"docs/side.md": "# Side\n"})
        self.repo.start_merge("side")
        self.repo.write("docs/own.md", "# The merge's\n")
        result = self.repo.prose("check", "-F", "-", "--goals", "review it",
                                 "--goals-for", "docs/own.md", "read it", stdin="Merge\n",
                                 file_goals=False)
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertNotIn("docs/side.md", result.stdout)

    def test_a_doc_the_merge_deleted_is_listed_and_one_a_side_deleted_is_not(self):
        self.repo.write("gone.md", "# Gone\n")
        self.repo.write("kept.md", "# Kept\n")
        self.repo.commit("docs\n")
        self.repo.git("checkout", "-q", "-b", "side")
        self.repo.git("rm", "-q", "gone.md")
        self.repo.commit("side drops gone.md\n")
        self.repo.git("checkout", "-q", "main")
        self.repo.on_main({"a.py": "# Main's comment.\nx = 1\n\n\n\n\n# The second comment.\ny = 2\n"})
        self.repo.start_merge("side")
        self.repo.git("rm", "-q", "kept.md")
        out = self.repo.first_call().stdout
        self.assertIn("  kept.md  (changed)\n", out)
        self.assertNotIn("gone.md", out)

    def test_rename_and_diff_config_change_nothing(self):
        # A rename the merged branch made arrives as that branch's file, and
        # diff settings cannot shift which lines are the merge's own.
        for key, value in (("diff.renames", "copies"), ("diff.algorithm", "histogram"),
                           ("diff.indentHeuristic", "false")):
            self.repo.git("config", key, value)
        self.repo.write("old.md", doc(LINES))
        self.repo.commit("old.md\n")
        self.repo.git("checkout", "-q", "-b", "side")
        self.repo.git("mv", "old.md", "renamed.md")
        self.repo.write("README.md", doc(changed(LINES, {2: "Side says two."})))
        self.repo.commit("side renames\n")
        self.repo.git("checkout", "-q", "main")
        self.repo.on_main({"README.md": doc(changed(LINES, {2: "Main says two."}))})
        with self.assertRaises(AssertionError):
            self.repo.start_merge("side")
        self.repo.write("README.md", doc(changed(LINES, {2: "Both say two."})[1:]))
        self.assertEqual(self.repo.listed(), {"README.md": {2}})

    def test_a_doc_one_side_renamed_and_the_other_edited_lists_nothing(self):
        # git pairs the rename when it merges, and so does `git show` of the
        # merge, which prints nothing here.
        self.repo.write("old.md", doc(LINES))
        self.repo.commit("old.md\n")
        self.repo.git("checkout", "-q", "-b", "side")
        self.repo.git("mv", "old.md", "new.md")
        self.repo.commit("side renames\n")
        self.repo.git("checkout", "-q", "main")
        self.repo.on_main({"old.md": doc(changed(LINES, {2: "Main says three."}))})
        self.repo.start_merge("side")
        self.assertEqual(self.repo.listed(), {})
        self.repo.write("new.md", doc(changed(LINES, {2: "Main says three.",
                                                       7: "The merge wrote eight."})))
        self.assertEqual(self.repo.listed(), {"new.md": {8}})

    def items(self):
        root = str(self.repo.path)
        items, _ = prose.prose_in(root, prose.commit_parents(root),
                                  lambda path: prose.git(["show", f":0:{path}"], root))
        return {item.path: item for item in items if item.path is not None}

    def test_the_merges_own_binary_deleted_symlinked_and_blank_lines_are_listed(self):
        self.repo.write("del.md", "# Deleted by the merge\n")
        self.repo.write("ln.md", "README.md")
        self.repo.commit("more docs\n")
        self.repo.branch("side", {"README.md": doc(changed(LINES, {2: "Side says two."}))})
        self.repo.on_main({"README.md": doc(changed(LINES, {2: "Main says two."}))})
        with self.assertRaises(AssertionError):
            self.repo.start_merge("side")
        # A resolution of three lines, the middle one blank.
        self.repo.write("README.md", doc(LINES[:2] + ["Both say two.", "", "And more."] + LINES[3:]))
        (self.repo.path / "bin.md").write_bytes(b"\x00binary\x00")
        self.repo.git("add", "bin.md")
        self.repo.git("rm", "-q", "del.md")
        # The same blob as before, now a symlink.
        (self.repo.path / "ln.md").unlink()
        (self.repo.path / "ln.md").symlink_to("README.md")
        self.repo.git("add", "ln.md")
        items = self.items()
        self.assertEqual(set(items), {"README.md", "bin.md", "del.md", "ln.md"})
        self.assertEqual(items["README.md"].spans, ((3, 5),))
        self.assertEqual((items["bin.md"].deleted, items["bin.md"].spans), (False, ()))
        self.assertEqual((items["del.md"].deleted, items["del.md"].spans), (True, ()))
        self.assertEqual((items["ln.md"].deleted, items["ln.md"].spans), (False, ()))

    def test_a_merge_head_naming_no_commit_is_refused(self):
        self.repo.branch("side", {"side.md": "# Side\n"})
        self.repo.start_merge("side")
        merge_head = self.repo.path / ".git" / "MERGE_HEAD"
        merge_head.write_text("0" * 40 + "\n")
        result = self.repo.first_call()
        self.assertEqual(result.returncode, 2)
        self.assertIn("MERGE_HEAD names a commit git cannot find", result.stderr)

    def test_hunks_slide_as_git_show_slides_them(self):
        # git's default indent heuristic slides these hunks; prose must slide
        # them the same way to list what `git show` prints.
        base = "f() {\n\n\n  y\n\n}\n}\n  x\n  y\n  x\ng() {\n}\n  x\n}\n  y\nf() {\n\nf() {\nf() {\n  x\n  x\n  y\n"
        side = "f() {\n\n\n  y\n\n}\n}\n  x\n  y\n  x\ng() {\n}\n  x\n}\nf() {\n\nf() {\nf() {\n  x\n  x\n  y\n  x\n"
        main = "f() {\n\n\n  y\n}\n}\n  x\n  y\n  x\ng() {\n}\n}r5\n}\n  y\nf() {\nf() {\nf() {\n  x\n  x\n  y\n"
        result = "f() {\n\n\n  y\n\n}\n}\n  x\n  y\n  x\ng() {\n}\n  x\n}\nf() {\n\nf() {\nf() {\n  x\n  y\n  x"
        self.repo.write("doc.md", base)
        self.repo.commit("doc\n")
        self.repo.branch("side", {"doc.md": side})
        self.repo.on_main({"doc.md": main})
        self.repo.start_merge("side", result={"doc.md": result})
        self.assertEqual(self.repo.listed(), {"doc.md": {13, 16, 21}})

    def test_a_textconv_driver_does_not_shift_the_lines(self):
        self.repo.git("config", "diff.twice.textconv", "sed p")
        (self.repo.path / ".git" / "info").mkdir(exist_ok=True)
        (self.repo.path / ".git" / "info" / "attributes").write_text("*.md diff=twice\n")
        self.repo.branch("side", {"README.md": doc(changed(LINES, {9: "Side wrote nine."}))})
        self.repo.on_main({"README.md": doc(changed(LINES, {1: "Main wrote one."}))})
        self.repo.start_merge("side")
        self.repo.write("README.md", doc(changed(LINES, {1: "Main wrote one.", 5: "The merge wrote five.",
                                                          9: "Side wrote nine."})))
        self.assertEqual(self.repo.listed(), {"README.md": {6}})

    def test_renames_are_paired_with_rename_detection_off_in_config(self):
        self.repo.write("old.md", doc(LINES))
        self.repo.commit("old.md\n")
        self.repo.git("checkout", "-q", "-b", "side")
        self.repo.git("mv", "old.md", "new.md")
        self.repo.commit("side renames\n")
        self.repo.git("checkout", "-q", "main")
        self.repo.on_main({"old.md": doc(changed(LINES, {2: "Main says three."}))})
        self.repo.start_merge("side")
        # Set after the merge, which reads the same setting to find renames.
        self.repo.git("config", "diff.renames", "false")
        self.assertEqual(self.repo.listed(), {})

    def test_renames_are_paired_with_a_low_rename_limit_in_config(self):
        self.repo.write("a.md", doc(LINES))
        self.repo.write("b.md", doc(line.replace("Line", "Row") for line in LINES))
        self.repo.commit("two docs\n")
        self.repo.git("checkout", "-q", "-b", "side")
        self.repo.git("mv", "a.md", "a2.md")
        self.repo.git("mv", "b.md", "b2.md")
        self.repo.write("a2.md", doc(LINES + ["Side's extra."]))
        self.repo.write("b2.md", doc([line.replace("Line", "Row") for line in LINES] + ["Extra."]))
        self.repo.commit("side renames and edits\n")
        self.repo.git("checkout", "-q", "main")
        self.repo.on_main({"a.md": doc(changed(LINES, {2: "Main says three."}))})
        self.repo.start_merge("side")
        self.repo.write("a2.md", doc(changed(LINES, {2: "Main says three.", 9: "The merge's ten."})
                                     + ["Side's extra."]))
        # Set after the merge, so it reaches only prose's diff, not the
        # merge's own rename detection.
        self.repo.git("config", "diff.renameLimit", "1")
        # Side's added line 13 is within the context of the merge's line 10,
        # so `git show` prints both in one hunk.
        self.assertEqual(self.repo.listed(), {"a2.md": {10, 13}})
        self.repo.git("config", "--unset", "diff.renameLimit")
        self.repo.git("commit", "-q", "--no-verify", "-m", "merge")
        # No pathspec: one would stop git pairing the rename.
        shown = self.repo.git("show", "--format=", "--cc", "HEAD")
        self.assertEqual([line[2:] for line in shown.split("\n") if line.startswith(("++", " +", "+ "))
                          and not line.startswith("+++")],
                         ["The merge's ten.", "Side's extra."])

    def test_a_mode_change_the_merge_made_lists_nothing(self):
        self.repo.branch("side", {"side.md": "# Side\n"})
        self.repo.start_merge("side")
        self.repo.git("update-index", "--chmod=+x", "README.md")
        self.assertEqual(self.repo.listed(), {})

    def test_an_octopus_merge_lists_only_its_own_text(self):
        self.repo.branch("one", {"README.md": doc(changed(LINES, {2: "One wrote two."}))})
        self.repo.branch("two", {"README.md": doc(changed(LINES, {9: "Two wrote nine."}))})
        self.repo.on_main({"a.py": "# Main's comment.\nx = 1\n\n\n\n\n# The second comment.\ny = 2\n"})
        self.repo.start_merge("one", "two")
        self.assertEqual(len(prose.commit_parents(str(self.repo.path))), 3)
        self.assertEqual(self.repo.listed(), {})
        self.repo.write("README.md", doc(changed(LINES, {2: "One wrote two.", 5: "The merge's five.",
                                                          9: "Two wrote nine."})))
        # One's line 3 is within the context of the merge's line 6, so it is
        # in the same hunk; Two's line 10 is not.
        self.assertEqual(self.repo.listed(), {"README.md": {3, 6}})


class AmendMerge(unittest.TestCase):
    """`--amend` of a merge commit reads it against the merge's parents."""

    def setUp(self):
        self.repo = MergeRepo()
        self.addCleanup(self.repo.cleanup)
        self.repo.branch("side", {"README.md": doc(changed(LINES, {9: "Side wrote nine."}))})
        self.repo.on_main({"README.md": doc(changed(LINES, {1: "Main wrote one."}))})
        self.repo.start_merge("side")
        self.repo.write("README.md", doc(changed(LINES, {1: "Main wrote one.", 5: "The merge wrote five.",
                                                          9: "Side wrote nine."})))
        self.repo.git("commit", "-q", "--no-edit")

    def test_amend_lists_what_the_merge_changed_against_all_its_parents(self):
        self.assertEqual(len(prose.commit_parents(str(self.repo.path), amend=True)), 2)
        self.assertEqual(self.repo.listed(amend=True), {"README.md": {6}})
        self.repo.write("README.md", doc(changed(LINES, {1: "Main wrote one.", 5: "The merge wrote five.",
                                                          7: "An amend wrote seven.",
                                                          9: "Side wrote nine."})))
        # Side's line 10 is within the context of the amend's line 8, so
        # `git show` prints it in the same hunk.
        self.assertEqual(self.repo.listed(amend=True), {"README.md": {6, 8, 10}})

    def test_amend_signs_and_the_merge_commit_keeps_both_parents(self):
        first = self.repo.first_call("--amend")
        self.assertEqual(first.returncode, 4, first.stderr)
        token = pass_token(first.stdout)
        signed = cold_read(lambda *cold: self.repo.prose("check", "-F", "-", "--amend", "--pass",
                                                         token, *cold, stdin="Merge\n"))
        self.assertEqual(signed.returncode, 0, signed.stderr)
        trailer = signed.stdout.split("\n")[1]
        self.repo.git("commit", "-q", "--amend", "-m", "Merge", "--trailer", trailer)
        self.assertEqual(len(self.repo.git("log", "-1", "--format=%P").split()), 2)

    def test_amend_during_a_merge_is_refused(self):
        self.repo.branch("other", {"other.md": "# Other\n"})
        self.repo.start_merge("other")
        result = self.repo.first_call("--amend")
        self.assertEqual(result.returncode, 2)
        self.assertIn("a merge is in progress", result.stderr)


class MergeCompaction(unittest.TestCase):
    """The compaction trigger advises on the docs a merge changed, not on
    those it brought in."""

    def setUp(self):
        self.repo = MergeRepo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write(".gitattributes", "* prose-compact-flagged=50\n")
        self.repo.commit("attributes\n")

    def test_a_due_doc_the_merged_branch_brought_is_not_advised(self):
        self.repo.branch("side", {"skills/a/SKILL.md": repeated()})
        self.repo.on_main({"a.py": "# Main's comment.\nx = 1\n\n\n\n\n# The second comment.\ny = 2\n"})
        self.repo.start_merge("side")
        self.assertNotIn("compaction due", self.repo.first_call().stdout)

    def test_a_due_doc_one_side_renamed_and_the_other_edited_is_not_advised(self):
        self.repo.write("skills/x/SKILL.md", repeated())
        self.repo.commit("a due doc\n")
        self.repo.git("checkout", "-q", "-b", "side")
        (self.repo.path / "skills/y").mkdir(parents=True)
        self.repo.git("mv", "skills/x/SKILL.md", "skills/y/SKILL.md")
        self.repo.commit("side renames\n")
        self.repo.git("checkout", "-q", "main")
        self.repo.on_main({"skills/x/SKILL.md": repeated().replace("# Doc", "# Main's doc")})
        self.repo.start_merge("side")
        self.assertNotIn("compaction due", self.repo.first_call().stdout)

    def test_a_due_doc_the_merge_wrote_is_advised(self):
        self.repo.branch("side", {"README.md": doc(changed(LINES, {9: "Side wrote nine."}))})
        self.repo.start_merge("side")
        self.repo.write("skills/a/SKILL.md", repeated())
        self.assertIn("compaction due for skills/a/SKILL.md", self.repo.first_call().stdout)


class PlainCompaction(unittest.TestCase):
    """A commit with one parent is advised against HEAD, or with --amend
    against HEAD's parent."""

    def setUp(self):
        self.repo = MergeRepo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write(".gitattributes", "* prose-compact-flagged=50\n")
        self.repo.write("skills/a/SKILL.md", repeated())
        self.repo.commit("a due doc\n")
        self.repo.write("a.py", "# Another comment.\nx = 1\n")

    def test_a_due_doc_only_head_changed_is_not_advised(self):
        self.assertNotIn("compaction due", self.repo.first_call().stdout)

    def test_amend_is_advised_on_the_due_doc_the_amended_commit_changed(self):
        self.assertIn("compaction due for skills/a/SKILL.md",
                      self.repo.first_call("--amend").stdout)


class Properties(unittest.TestCase):
    """Random merges of one doc, each line taken from a parent or written
    anew, checked against what the rule promises."""

    CASES = 30

    def random_merge(self, rng):
        repo = MergeRepo()
        self.addCleanup(repo.cleanup)
        ours = changed(LINES, {i: f"Main's line {i}." for i in rng.sample(range(12), rng.randint(1, 5))})
        theirs = changed(LINES, {i: f"Side's line {i}." for i in rng.sample(range(12), rng.randint(1, 5))})
        choices = [rng.choice(("ours", "theirs", "new")) for _ in LINES]
        result = [ours[i] if pick == "ours" else theirs[i] if pick == "theirs"
                  else f"The merge's line {i}." for i, pick in enumerate(choices)]
        repo.branch("side", {"README.md": doc(theirs)})
        repo.on_main({"README.md": doc(ours)})
        repo.start_merge("side", result={"README.md": doc(result)})
        return repo, ours, theirs, result

    def test_lines_differing_from_every_parent_are_listed_and_shared_lines_are_not(self):
        rng = random.Random(59)
        for case in range(self.CASES):
            repo, ours, theirs, result = self.random_merge(rng)
            listed = repo.listed().get("README.md", set())
            with self.subTest(case=case, ours=ours, theirs=theirs, result=result):
                for i, line in enumerate(result):
                    if line != ours[i] and line != theirs[i]:
                        self.assertIn(i + 1, listed)
                    if line == ours[i] == theirs[i]:
                        self.assertNotIn(i + 1, listed)

    def test_the_listing_holds_the_lines_git_show_prints_as_added(self):
        # Compared as text, so the check does not share the listing's line
        # counting: commit the merge and read `git show` of it.
        rng = random.Random(4059)
        for case in range(self.CASES):
            repo, ours, theirs, result = self.random_merge(rng)
            listed = repo.listed().get("README.md", set())
            repo.git("commit", "-q", "--no-verify", "-m", "merge")
            shown = repo.git("-c", "diff.context=3", "show", "--format=", "--cc", "HEAD",
                             "--", "README.md")
            added = sorted(line[2:] for line in shown.split("\n")
                           if line[:2] != "++" and "+" in line[:2] and "-" not in line[:2]
                           or line.startswith("++") and not line.startswith("+++"))
            with self.subTest(case=case, ours=ours, theirs=theirs, result=result):
                self.assertEqual(sorted(result[n - 1] for n in listed), added)

    def test_a_result_equal_to_one_parent_lists_nothing(self):
        rng = random.Random(5959)
        for case in range(self.CASES // 2):
            repo = MergeRepo()
            self.addCleanup(repo.cleanup)
            ours = changed(LINES, {i: f"Main's line {i}." for i in rng.sample(range(12), rng.randint(1, 6))})
            theirs = changed(LINES, {i: f"Side's line {i}." for i in rng.sample(range(12), rng.randint(1, 6))})
            repo.branch("side", {"README.md": doc(theirs)})
            repo.on_main({"README.md": doc(ours)})
            repo.start_merge("side", result={"README.md": doc(rng.choice((ours, theirs)))})
            with self.subTest(case=case):
                self.assertEqual(repo.listed(), {})

    def test_a_merge_of_identical_parents_lists_what_a_plain_commit_does(self):
        # With every parent the same commit, "differs from every parent" is
        # "differs from HEAD": the combined path must agree with the plain
        # one on any edit, insertions and deletions included.
        rng = random.Random(1959)
        for case in range(self.CASES):
            repo = MergeRepo()
            self.addCleanup(repo.cleanup)
            lines = list(LINES)
            for _ in range(rng.randint(1, 4)):
                at = rng.randrange(len(lines) + 1)
                kind = rng.choice(("insert", "delete", "replace"))
                if kind == "insert" or not lines or at == len(lines):
                    lines.insert(at, f"Inserted {case}-{at}-{rng.random():.6f}.")
                elif kind == "delete":
                    del lines[at]
                else:
                    lines[at] = f"Replaced {case}-{at}-{rng.random():.6f}."
            repo.write("README.md", doc(lines))
            repo.write("a.py", "# The first comment.\nx = 1\n\n\n\n\n"
                               f"# A comment {case} rewrote.\ny = 2\n")
            root = str(repo.path)
            head = prose.commit_parents(root)
            read = lambda path, root=root: prose.git(["show", f":0:{path}"], root)
            plain, _ = prose.prose_in(root, head, read)
            merged, _ = prose.prose_in(root, head * 2, read)
            with self.subTest(case=case, lines=lines):
                self.assertEqual(plain, merged)


class PlainCommits(unittest.TestCase):
    """A commit with one parent, or none, lists as it always has."""

    def test_a_plain_commits_parents_are_head_alone(self):
        repo = MergeRepo()
        self.addCleanup(repo.cleanup)
        head = repo.git("rev-parse", "HEAD").strip()
        self.assertEqual(prose.commit_parents(str(repo.path)), [head])
        repo.write("README.md", doc(changed(LINES, {3: "Changed."})))
        self.assertEqual(repo.listed(), {"README.md": {4}})

    def test_amend_of_a_plain_commit_reads_against_its_parent(self):
        repo = MergeRepo()
        self.addCleanup(repo.cleanup)
        base = repo.git("rev-parse", "HEAD").strip()
        repo.write("README.md", doc(changed(LINES, {3: "Changed."})))
        repo.commit("change\n")
        self.assertEqual(prose.commit_parents(str(repo.path), amend=True), [base])
        self.assertEqual(repo.listed(amend=True), {"README.md": {4}})

    def test_amend_with_no_commit_is_refused(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("README.md", "# Hi\n")
        result = repo.prose("check", "-F", "-", "--goals", "review it", "--amend", stdin="T\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--amend, but there is no commit to amend", result.stderr)

    def test_the_first_commit_and_an_amended_root_read_against_nothing(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        self.assertEqual(prose.commit_parents(str(repo.path)), [])
        repo.write("README.md", "# Hi\n")
        repo.commit("root\n")
        self.assertEqual(prose.commit_parents(str(repo.path), amend=True), [])


if __name__ == "__main__":
    unittest.main()

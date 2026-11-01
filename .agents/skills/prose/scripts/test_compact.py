#!/usr/bin/env python3
"""Tests for compaction, in compact.py and prose.py: `prose compact <file>`,
the answers the compacting agent gives for each flagged passage, --verify,
the gate that refuses to sign an unverified compaction, and the file each
brief prose prints is also saved to.

Standard library only:

    python3 test_compact.py
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
import time
import unittest

from prose_test_support import (
    REPEAT,
    Repo,
    SCRIPT,
    answers_file,
    compact,
    mock_attr,
    paragraphs,
    pass_token,
    prose,
    run,
    straight_report,
)


class PassageAnswers(unittest.TestCase):
    """The compactor answers for every flagged passage, and --verify checks
    each answer against the new file."""

    DOC = ("# D\n\n## The token expires after two hours\n\nIt expires. We tried a lock first.\n\n"
           + REPEAT + "Note: the hook reads it.\n\n" + REPEAT)

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("DECISIONS.md", self.DOC)
        self.repo.commit("base\n")
        result = self.repo.prose("compact", "DECISIONS.md")
        self.assertEqual(result.returncode, 4, result.stderr)
        self.brief = result.stdout
        self.answers = answers_file(self.brief)

    def verify(self, after, answers):
        self.repo.write("DECISIONS.md", after)
        if answers is not None:
            self.answers.write_text(answers)
        return self.repo.prose("compact", "DECISIONS.md", "--verify")

    GOOD = "# D\n\n## The token expires after two hours\n\nIt expires.\n\n" + REPEAT

    def test_the_brief_lists_each_passage_with_its_lines_kind_and_text(self):
        self.assertIn("Flagged passages (3).", self.brief)
        self.assertIn("Passage 1, lines 5-5, narrative:\n    We tried a lock first.", self.brief)
        self.assertIn("Passage 2, lines 9-9, filler:\n    Note: the hook reads it.", self.brief)
        self.assertIn("Passage 3, lines 11-11, repetition; same as line 7:\n    The token",
                      self.brief)

    def test_each_passage_answered_and_gone_passes(self):
        result = self.verify(self.GOOD, "Passage 1: removed\nPassage 2: removed\n"
                                        "Passage 3: removed\n")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Flagged passages: 3; answered 0 rewritten, 3 removed, 0 kept.",
                      result.stdout)

    def test_no_answers_file_fails(self):
        result = self.verify(self.GOOD, None)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("no answers for the 3 flagged passages", result.stdout)

    def test_a_passage_with_no_answer_fails(self):
        result = self.verify(self.GOOD, "Passage 1: removed\nPassage 3: removed\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no answer for passage 2", result.stdout)

    def test_a_verbatim_copy_answered_rewritten_fails(self):
        after = self.GOOD.replace("It expires.", "It expires. We tried a lock first.")
        result = self.verify(after, "Passage 1: rewritten\nPassage 2: removed\n"
                                    "Passage 3: removed\n")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("passage 1 (lines 5-5, narrative) is answered rewritten but is still in the "
                      "file word for word", result.stdout)

    def test_a_verbatim_copy_kept_with_a_reason_passes(self):
        after = self.GOOD.replace("It expires.", "It expires. We tried a lock first.")
        result = self.verify(after, "Passage 1: kept: the lock is the live alternative\n"
                                    "Passage 2: removed\nPassage 3: removed\n")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_both_copies_of_a_repetition_left_fails(self):
        result = self.verify(self.GOOD + REPEAT, "Passage 1: removed\nPassage 2: removed\n"
                                                 "Passage 3: removed\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("passage 3", result.stdout)

    def test_two_passages_with_the_same_text_need_both_copies_gone(self):
        sentence = ("Note: the pass token expires after two hours, so run the first call "
                    "again before signing.")
        before = f"# Doc\n\n{sentence}\n\nMiddle paragraph.\n\n{sentence}\n"
        after = f"# Doc\n\nMiddle paragraph.\n\n{sentence}\n"
        found = compact.passages(before)
        self.assertEqual(len(found), 2)
        _, failures = compact.check_passages(before, after, found,
                                             ["Passage 1: removed", "Passage 2: removed"])
        self.assertTrue(failures)
        _, failures = compact.check_passages(before, after, found,
                                             ["Passage 1: removed", "Passage 2: kept: once"])
        self.assertEqual(failures, [])

    def test_history_kept_with_a_reason_passes_and_new_history_fails(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("DECISIONS.md", "# D\n\n**Revised 2026-09-30.** The token expires.\n\n"
                                   "Gone paragraph here.\n")
        repo.commit("base\n")
        answers = answers_file(repo.prose("compact", "DECISIONS.md").stdout)
        repo.write("DECISIONS.md", "# D\n\n**Revised 2026-09-30.** The token expires.\n")
        answers.write_text("Passage 1: kept: the date is the decision's own\n")
        result = repo.prose("compact", "DECISIONS.md", "--verify")
        self.assertEqual(result.returncode, 0, result.stdout)
        repo.write("DECISIONS.md", "# D\n\n**Revised 2026-09-30.** The token expires.\n\n"
                                   "Update: it was changed to two hours.\n")
        result = repo.prose("compact", "DECISIONS.md", "--verify")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("history marker left at line 5", result.stdout)
        self.assertNotIn("history marker left at line 3", result.stdout)

    def test_a_kept_passage_exempts_only_its_own_text_from_the_history_check(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("notes.md", "# N\n\nPreviously the tool used Python for parsing. Basically it "
                               "now uses Go for every parser.\n\nGone paragraph.\n")
        repo.commit("base\n")
        answers = answers_file(repo.prose("compact", "notes.md").stdout)
        repo.write("notes.md", "# N\n\nPreviously it parsed with Python. Basically it now uses Go "
                               "for every parser.\n")
        answers.write_text("Passage 1: rewritten\nPassage 2: kept: the claim must stay\n")
        result = repo.prose("compact", "notes.md", "--verify")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("history marker left at line 3", result.stdout)

    def stored_copy_repo(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("notes.md", "# N\n\nPreviously the tool used Python for parsing.\n\n"
                               "Gone paragraph.\n")
        repo.commit("base\n")
        answers = answers_file(repo.prose("compact", "notes.md").stdout)
        repo.write("notes.md", "# N\n\nPreviously the tool used Python for parsing.\n")
        answers.write_text("Passage 1: kept: reason x\n")
        self.assertEqual(repo.prose("compact", "notes.md", "--verify").returncode, 0)
        return repo, answers

    def changes_file(self, review):
        return pathlib.Path(re.search(r"^The changes: (.*)$", review.stdout, re.M).group(1)) \
            .read_text(encoding="utf-8")

    def test_an_edit_to_the_answers_after_verify_is_ignored_until_verify_runs_again(self):
        repo, answers = self.stored_copy_repo()
        answers.write_text("Passage 1: kept: reason y\n")
        review = repo.prose("compact", "notes.md", "--review")
        self.assertIn("Reason given: reason x", self.changes_file(review))
        self.assertEqual(repo.prose("compact", "notes.md", "--verify").returncode, 0)
        review = repo.prose("compact", "notes.md", "--review")
        self.assertIn("Reason given: reason y", self.changes_file(review))

    def test_the_gate_refuses_answers_verified_after_their_review(self):
        repo, answers = self.stored_copy_repo()
        review = repo.prose("compact", "notes.md", "--review")
        count = int(re.search(r"Changes: ([0-9]+)", review.stdout).group(1))
        (repo.path / ".reply").write_text("".join(f"Change {n}: superseded\n"
                                                  for n in range(1, count + 1))
                                          + "Passage 1: justified\nTotals: 0 lost, 0 false\n")
        done = repo.prose("compact", "notes.md", "--reviewed", str(repo.path / ".reply"))
        self.assertEqual(done.returncode, 0, done.stderr)

        def pending():
            here = os.getcwd()
            os.chdir(repo.path)
            try:
                return compact.unverified(str(repo.path), False,
                                          repo.path / ".git/prose/passes")
            finally:
                os.chdir(here)

        self.assertEqual(pending(), [])
        answers.write_text("Passage 1: kept: reason y\n")
        # The edited answers are not verified, so the gate still reads the
        # stored copy the review judged.
        self.assertEqual(pending(), [])
        self.assertEqual(repo.prose("compact", "notes.md", "--verify").returncode, 0)
        self.assertEqual(len(pending()), 1)
        self.assertIn("its review was not completed", pending()[0])

    def test_a_blob_verified_with_a_kept_passage_needs_that_passage_judged(self):
        repo, answers = self.stored_copy_repo()
        verified = (repo.path / "notes.md").read_text()
        repo.write("notes.md", verified + "More text that grows the file well past its size.\n")
        self.assertEqual(repo.prose("compact", "notes.md", "--verify").returncode, 1)
        repo.write("notes.md", verified)
        review = repo.prose("compact", "notes.md", "--review")
        count = int(re.search(r"Changes: ([0-9]+)", review.stdout).group(1)) \
            if review.returncode == 4 else 0
        (repo.path / ".reply").write_text("".join(f"Change {n}: superseded\n"
                                                  for n in range(1, count + 1))
                                          + "Totals: 0 lost, 0 false\n")
        repo.prose("compact", "notes.md", "--reviewed", str(repo.path / ".reply"))
        here = os.getcwd()
        os.chdir(repo.path)
        try:
            pending = compact.unverified(str(repo.path), False, repo.path / ".git/prose/passes")
        finally:
            os.chdir(here)
        self.assertTrue(pending, "the kept passage was never judged")

    def test_a_line_not_in_the_form_fails(self):
        result = self.verify(self.GOOD, "Passage 1: gone\nPassage 2: removed\n"
                                        "Passage 3: removed\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not 'Passage <n>: rewritten'", result.stdout)

    def test_a_new_first_step_discards_old_answers(self):
        self.answers.write_text("Passage 1: removed\n")
        self.repo.prose("compact", "DECISIONS.md")
        self.assertFalse(self.answers.exists())

    def test_abandon_deletes_the_answers(self):
        self.answers.write_text("Passage 1: removed\n")
        self.assertEqual(self.repo.prose("compact", "--abandon", "DECISIONS.md").returncode, 0)
        self.assertFalse(self.answers.exists())

    def test_the_answers_file_is_outside_the_git_directory(self):
        # A subagent writes the answers file, and a harness may refuse its
        # writes into the shared git directory. Outside the work tree too,
        # so nothing can stage it.
        git_dir = (self.repo.path / ".git").resolve()
        where = self.answers.resolve()
        self.assertFalse(where == git_dir or git_dir in where.parents, where)
        self.assertFalse(self.repo.path.resolve() in where.parents, where)

    def test_verify_reads_the_answers_file_given_with_answers(self):
        elsewhere = self.repo.path.parent / f"{self.repo.path.name}-answers.txt"
        self.addCleanup(lambda: elsewhere.unlink() if elsewhere.exists() else None)
        elsewhere.write_text("Passage 1: removed\nPassage 2: removed\nPassage 3: removed\n")
        self.repo.write("DECISIONS.md", self.GOOD)
        self.assertFalse(self.answers.exists())
        result = self.repo.prose("compact", "DECISIONS.md", "--verify", "--answers", str(elsewhere))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("answered 0 rewritten, 3 removed, 0 kept.", result.stdout)

    def test_a_missing_answers_file_given_with_answers_is_refused(self):
        self.repo.write("DECISIONS.md", self.GOOD)
        result = self.repo.prose("compact", "DECISIONS.md", "--verify", "--answers",
                                 str(self.repo.path.parent / "no-such-answers.txt"))
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("no-such-answers.txt: no such file, given with --answers", result.stderr)

    def test_answers_goes_only_with_verify(self):
        for step in ([], ["--review"], ["--abandon"]):
            with self.subTest(step=step):
                result = self.repo.prose("compact", "DECISIONS.md", *step, "--answers", "a.txt")
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("--answers goes with --verify", result.stderr)


class CitedShortHeadings(unittest.TestCase):
    """A heading shorter than MIN_HEADING counts as cited where its words,
    case kept and markup ignored, are on the same line, or in the same
    sentence, as a name for the
    doc: its path, its file name, or its skill's name as "<skill>'s" or
    "the <skill> skill"."""

    DOC = ("# Prose\n\n## Compaction\n\nA.\n\n## The cold read\n\nB.\n\n## Committing\n\nC.\n\n"
           "## Never\n\nD.\n\n## Keep\n\nE.\n")
    AFTER = "# Prose\n\n## Keep\n\nE.\n"
    NAME = "skills/prose/SKILL.md"
    # The first three entries cite a short heading in the shapes other files
    # use: bug-hunter's SKILL.md, compact.py's messages and prose's rules.md.
    # other.md uses the headings' words without naming the doc, so it cites
    # nothing.
    CITING = {
        "skills/bug-hunter/SKILL.md": "cold-read brief. Follow prose's SKILL.md, *The cold read*, "
                                      "which gives the\nSKILL.md, *Committing*, which covers an "
                                      "amend.\n",
        "skills/prose/scripts/compact.py": '    f"were making first (SKILL.md, *Compaction*), then '
                                           'run the first "\n',
        "skills/prose/rules.md": "- SKILL.md's *The cold read* says how to run it.\n",
        "other.md": "Compaction keeps docs short. Never skip it, and keep Committing small.\n",
    }

    def repo_with(self, files):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        for name, text in files.items():
            repo.write(name, text)
        repo.commit("base\n")
        return repo

    def verify_after(self, repo, new_text):
        brief = repo.prose("compact", self.NAME)
        self.assertEqual(brief.returncode, 4, brief.stderr)
        (repo.path / self.NAME).write_text(new_text)
        repo.git("add", "--", self.NAME)
        return brief, repo.prose("compact", self.NAME, "--verify")

    def test_the_brief_and_verify_protect_short_headings_cited_by_name(self):
        repo = self.repo_with({self.NAME: self.DOC, **self.CITING})
        brief, result = self.verify_after(repo, self.AFTER)
        self.assertIn("  The cold read  (in skills/bug-hunter/SKILL.md, skills/prose/rules.md)",
                      brief.stdout)
        self.assertIn("  Committing  (in skills/bug-hunter/SKILL.md)", brief.stdout)
        self.assertIn("  Compaction  (in skills/prose/scripts/compact.py)", brief.stdout)
        self.assertNotIn("  Never  (", brief.stdout)
        self.assertEqual(result.returncode, 1, result.stdout)
        for line in ("skills/bug-hunter/SKILL.md:1 names 'The cold read'",
                     "skills/bug-hunter/SKILL.md:2 names 'Committing'",
                     "skills/prose/scripts/compact.py:1 names 'Compaction'",
                     "skills/prose/rules.md:1 names 'The cold read'"):
            self.assertIn(line, result.stdout)
        self.assertNotIn("other.md", result.stdout)

    def test_each_name_for_the_doc_counts(self):
        for text in ("See skills/prose/SKILL.md, under Never.", "SKILL.md: Never",
                     "prose's Never list", "prose’s Never list", "the prose skill's Never list",
                     "The Prose skill keeps a Never list.",
                     "Read SKILL.md and its\nNever list.", "# Read SKILL.md and its\n# Never list.",
                     # The file name on the line makes a heading word in
                     # another clause count too: no clause is parsed.
                     "SKILL.md is long; Never mind.", "Read SKILL.md.  Never mind."):
            with self.subTest(text=text):
                repo = self.repo_with({self.NAME: self.DOC, "n.md": text + "\n"})
                _, result = self.verify_after(repo, self.AFTER)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("names 'Never'", result.stdout)

    def test_no_name_beside_it_does_not_count(self):
        for text in ("the compaction runs, and Compaction is a word.", "Never.",
                     "Read SKILL.md.\nNever mind.",
                     "SKILL.md\n\nNever", "SKILL.md: never", "SKILL.md: Nevermore",
                     "bug-hunter's Never list", "proses Never list", "README.md: Never",
                     "SKILL.mdx: Never", "the prose-check skill: Never"):
            with self.subTest(text=text):
                repo = self.repo_with({self.NAME: self.DOC, "n.md": text + "\n"})
                _, result = self.verify_after(repo, self.AFTER)
                self.assertEqual(result.returncode, 0, result.stdout)

    def test_the_files_own_citation_does_not_block(self):
        repo = self.repo_with({self.NAME: self.DOC})
        _, result = self.verify_after(repo, self.AFTER + "\nSee SKILL.md, Never.\n")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_skill_name_in_backticks_counts(self):
        for text in ("Readability is the `prose` skill's Never job.", "`prose`'s Never list"):
            with self.subTest(text=text):
                repo = self.repo_with({self.NAME: self.DOC, "n.md": text + "\n"})
                _, result = self.verify_after(repo, self.AFTER)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("n.md:1 names 'Never'", result.stdout)

    def test_an_abbreviation_does_not_end_the_sentence(self):
        repo = self.repo_with({self.NAME: self.DOC,
                               "n.md": "For the rule see the prose skill, e.g.\nNever.\n"})
        _, result = self.verify_after(repo, self.AFTER)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("n.md:2 names 'Never'", result.stdout)

    def test_underscore_emphasis_counts(self):
        for text in ("See _SKILL.md_, _Never_, for the reason.", "See SKILL.md, _Never_.",
                     "See _SKILL.md_, *Never*."):
            with self.subTest(text=text):
                repo = self.repo_with({self.NAME: self.DOC, "n.md": text + "\n"})
                _, result = self.verify_after(repo, self.AFTER)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("n.md:1 names 'Never'", result.stdout)

    def test_a_numbered_list_continues_the_sentence(self):
        repo = self.repo_with({self.NAME: self.DOC,
                               "n.md": "SKILL.md lists these sections:\n1. Keep\n2. Never\n"})
        _, result = self.verify_after(repo, self.AFTER)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("n.md:3 names 'Never'", result.stdout)

    def test_a_skill_name_counts_outside_a_repository(self):
        folder = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        skill = folder / "skills" / "prose"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(self.DOC)
        (folder / "skills" / "other.md").write_text("See the prose skill, Never, for why.\n")
        brief = run([sys.executable, str(SCRIPT), "compact", "SKILL.md", "--", "../other.md"],
                    cwd=skill)
        self.addCleanup(run, [sys.executable, str(SCRIPT), "compact", "--abandon", "SKILL.md"],
                        cwd=skill)
        self.assertEqual(brief.returncode, 4, brief.stderr)
        self.assertIn("  Never  (in ../other.md)", brief.stdout)
        (skill / "SKILL.md").write_text(self.AFTER)
        result = run([sys.executable, str(SCRIPT), "compact", "SKILL.md", "--verify", "--",
                      "../other.md"], cwd=skill)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("names 'Never'", result.stdout)

    def test_a_short_heading_with_markup_is_found_as_rendered(self):
        doc = "# Prose\n\n## Using `rg`\n\nA.\n\n## Keep\n\nE.\n"
        repo = self.repo_with({self.NAME: doc, "n.md": "See the prose skill, *Using rg*.\n"})
        _, result = self.verify_after(repo, self.AFTER)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("n.md:1 names 'Using `rg`'", result.stdout)

    def test_a_heading_inside_the_docs_own_name_is_not_cited(self):
        repo = self.repo_with({"docs/FAQ.md": "# Doc\n\n## FAQ\n\nA.\n\n## Keep\n\nB.\n",
                               "other.md": "Questions go to docs/FAQ.md.\n"})
        self.assertEqual(repo.prose("compact", "docs/FAQ.md").returncode, 4)
        (repo.path / "docs/FAQ.md").write_text("# Doc\n\n## Keep\n\nB.\n")
        repo.git("add", "--", "docs/FAQ.md")
        result = repo.prose("compact", "docs/FAQ.md", "--verify")
        self.assertEqual(result.returncode, 0, result.stdout)


class AnswersDirectory(unittest.TestCase):
    """The private directory for compactors' answers files."""

    def test_windows_permission_bits_do_not_refuse_it(self):
        # Windows reports a directory's mode as 0o777 or 0o555, whoever owns
        # it, so the private-mode check cannot apply there. The test removes
        # os.getuid, which Windows lacks, and fakes a 0o777 directory.
        fake = os.stat_result((0o040777, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        getuid = getattr(os, "getuid", None)
        if getuid is not None:
            del os.getuid
        try:
            with mock_attr(compact.os, "lstat", lambda path: fake):
                self.assertTrue(compact.answers_dir().name.startswith("prose-answers-"))
        finally:
            if getuid is not None:
                os.getuid = getuid


class ManualRequest(unittest.TestCase):
    """`prose compact <file>` on a file no trigger would name still lists
    and enforces every flagged passage."""

    def test_a_file_not_due_gets_every_passage(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("README.md", "# R\n\nIt runs. Note: it runs twice.\n")
        repo.commit("base\n")
        self.assertEqual(compact.due(["README.md"], str(repo.path)), [])
        brief = repo.prose("compact", "README.md")
        self.assertIn("Passage 1, lines 3-3, filler:\n    Note: it runs twice.", brief.stdout)
        repo.write("README.md", "# R\n\nIt runs. Note: it runs twice.\n")
        repo.write("README.md", "# R\n\nIt runs twice. Note: it runs twice.\n")
        answers_file(brief.stdout).write_text("Passage 1: rewritten\n")
        result = repo.prose("compact", "README.md", "--verify")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("still in the file word for word", result.stdout)


class Attribution(unittest.TestCase):
    """Credits are kept unless the file's attribute drops them."""

    def brief(self, attributes):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        if attributes:
            repo.write(".gitattributes", attributes)
        repo.write("skills/a/DECISIONS.md", "# D\n\nIt holds (Adam, 2026-10-24).\n")
        repo.commit("base\n")
        return repo.prose("compact", "skills/a/DECISIONS.md").stdout

    def test_credits_are_kept_by_default(self):
        self.assertIn("Credits: keep each \"who decided\" credit", self.brief(""))

    def test_the_attribute_drops_them(self):
        out = self.brief("skills/*/DECISIONS.md prose-compact-attribution=drop\n")
        self.assertIn("Credits: drop each \"who decided\" credit", out)
        self.assertIn("prose-compact-attribution=drop says so", out)


class KeptPassageReview(unittest.TestCase):
    """The reviewer judges each kept passage's reason."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("DECISIONS.md", "# D\n\nIt holds. We tried a lock first.\n\nGone.\n")
        self.repo.commit("base\n")
        answers = answers_file(self.repo.prose("compact", "DECISIONS.md").stdout)
        self.repo.write("DECISIONS.md", "# D\n\nIt holds. We tried a lock first.\n")
        answers.write_text("Passage 1: kept: the lock is still the alternative\n")
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--verify").returncode, 0)
        self.review = self.repo.prose("compact", "DECISIONS.md", "--review")

    def reviewed(self, reply, dispositions=None):
        (self.repo.path / ".reply").write_text(reply)
        extra = []
        if dispositions is not None:
            (self.repo.path / ".disp").write_text(dispositions)
            extra = ["--dispositions", str(self.repo.path / ".disp")]
        return self.repo.prose("compact", "DECISIONS.md", "--reviewed",
                               str(self.repo.path / ".reply"), *extra)

    def test_the_changes_file_lists_each_kept_passage_and_its_reason(self):
        self.assertIn("Flagged passages kept: 1.", self.review.stdout)
        changes = pathlib.Path(re.search(r"^The changes: (.*)$", self.review.stdout, re.M).group(1))
        text = changes.read_text(encoding="utf-8")
        self.assertIn("### Passage 1, lines 3-3, narrative\n\nReason given: the lock is still the "
                      "alternative\n\n    We tried a lock first.", text)

    def test_a_kept_passage_needs_a_verdict(self):
        result = self.reviewed("Change 1: superseded\nTotals: 0 lost, 0 false\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no verdict for kept passage 1", result.stderr)
        result = self.reviewed("Change 1: superseded\nPassage 1: justified\n"
                               "Totals: 0 lost, 0 false\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_passage_kept_after_the_review_needs_a_review_of_it(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("CLAUDE.md", "# C\n\nIt writes YAML. Note that it basically writes YAML.\n\n"
                                "Gone line here.\n")
        repo.commit("base\n")
        answers = answers_file(repo.prose("compact", "CLAUDE.md").stdout)
        repo.write("CLAUDE.md", "# C\n\nIt writes YAML.\n")
        answers.write_text("Passage 1: removed\n")
        self.assertEqual(repo.prose("compact", "CLAUDE.md", "--verify").returncode, 0)
        review = repo.prose("compact", "CLAUDE.md", "--review")
        count = int(re.search(r"Changes: ([0-9]+)", review.stdout).group(1))
        repo.write("CLAUDE.md", "# C\n\nIt writes YAML. Note that it basically writes YAML.\n")
        answers.write_text("Passage 1: kept: the reviewer wanted it back\n")
        self.assertEqual(repo.prose("compact", "CLAUDE.md", "--verify").returncode, 0)
        (repo.path / ".reply").write_text("Change 1: lost: it writes YAML\n" + "".join(
            f"Change {n}: superseded\n" for n in range(2, count + 1)) + "Totals: 1 lost, 0 false\n")
        (repo.path / ".disp").write_text("Change 1: fixed\n")
        result = repo.prose("compact", "CLAUDE.md", "--reviewed", str(repo.path / ".reply"),
                            "--dispositions", str(repo.path / ".disp"))
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("passage 1", result.stderr)

    def test_an_unjustified_kept_passage_can_be_fixed_and_recorded(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("notes.md", "# N\n\nPreviously the tool used Python for parsing.\n\n"
                               "Gone paragraph here.\n")
        repo.commit("base\n")
        answers = answers_file(repo.prose("compact", "notes.md").stdout)
        repo.write("notes.md", "# N\n\nPreviously the tool used Python for parsing.\n")
        answers.write_text("Passage 1: kept: x\n")
        self.assertEqual(repo.prose("compact", "notes.md", "--verify").returncode, 0)
        review = repo.prose("compact", "notes.md", "--review")
        count = int(re.search(r"Changes: ([0-9]+)", review.stdout).group(1))
        repo.write("notes.md", "# N\n\nThe tool uses Python for parsing.\n")
        answers.write_text("Passage 1: rewritten\n")
        self.assertEqual(repo.prose("compact", "notes.md", "--verify").returncode, 0)
        (repo.path / ".reply").write_text("".join(f"Change {n}: superseded\n"
                                                  for n in range(1, count + 1))
                                          + "Passage 1: unjustified: drop it\n"
                                          + "Totals: 0 lost, 0 false\n")
        (repo.path / ".disp").write_text("Passage 1: fixed\n")
        result = repo.prose("compact", "notes.md", "--reviewed", str(repo.path / ".reply"),
                            "--dispositions", str(repo.path / ".disp"))
        self.assertEqual(result.returncode, 0, result.stderr)

    def fixed_flow(self, repo, rewrite=True):
        """Compact notes.md keeping passage 1, have it found unjustified,
        then fix it (or, with rewrite False, only touch another line)."""
        repo.write("notes.md", "# N\n\nPreviously the tool used Python for parsing.\n\n"
                               "Gone paragraph here.\n\nOther line.\n")
        repo.commit("base\n")
        answers = answers_file(repo.prose("compact", "notes.md").stdout)
        repo.write("notes.md", "# N\n\nPreviously the tool used Python for parsing.\n\n"
                               "Other line.\n")
        answers.write_text("Passage 1: kept: x\n")
        self.assertEqual(repo.prose("compact", "notes.md", "--verify").returncode, 0)
        review = repo.prose("compact", "notes.md", "--review")
        count = int(re.search(r"Changes: ([0-9]+)", review.stdout).group(1))
        if rewrite:
            repo.write("notes.md", "# N\n\nThe tool uses Python for parsing.\n\nOther line.\n")
            answers.write_text("Passage 1: rewritten\n")
        else:
            repo.write("notes.md", "# N\n\nPreviously the tool used Python for parsing.\n\n"
                                   "Other.\n")
        self.assertEqual(repo.prose("compact", "notes.md", "--verify").returncode, 0)
        (repo.path / ".reply").write_text("".join(f"Change {n}: superseded\n"
                                                  for n in range(1, count + 1))
                                          + "Passage 1: unjustified: drop it\n"
                                          + "Totals: 0 lost, 0 false\n")
        (repo.path / ".disp").write_text("Passage 1: fixed\n")
        return repo.prose("compact", "notes.md", "--reviewed", str(repo.path / ".reply"),
                          "--dispositions", str(repo.path / ".disp"))

    def test_a_passage_marked_fixed_and_still_kept_after_verify_is_refused_by_the_gate(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("doc.md", "# D\n\nPreviously we used a lock.\n\nNote: the other thing is also "
                             "true and stays.\n\nGone.\n")
        repo.commit("base\n")
        answers = answers_file(repo.prose("compact", "doc.md").stdout)
        repo.write("doc.md", "# D\n\nNote: the other thing is also true and stays.\n\nKept.\n")
        answers.write_text("Passage 1: removed\nPassage 2: kept: needed\n")
        self.assertEqual(repo.prose("compact", "doc.md", "--verify").returncode, 0)
        review = repo.prose("compact", "doc.md", "--review")
        count = int(re.search(r"Changes: ([0-9]+)", review.stdout).group(1))
        repo.write("doc.md", "# D\n\nNote: the other thing is also true and stays.\n\nKept it.\n")
        (repo.path / ".reply").write_text("".join(f"Change {n}: superseded\n"
                                                  for n in range(1, count + 1))
                                          + "Passage 2: unjustified: drop it\n"
                                          + "Totals: 0 lost, 0 false\n")
        (repo.path / ".disp").write_text("Passage 2: fixed\n")
        repo.prose("compact", "doc.md", "--reviewed", str(repo.path / ".reply"),
                   "--dispositions", str(repo.path / ".disp"))
        repo.prose("compact", "doc.md", "--verify")
        here = os.getcwd()
        os.chdir(repo.path)
        try:
            pending = compact.unverified(str(repo.path), False, repo.path / ".git/prose/passes")
        finally:
            os.chdir(here)
        self.assertTrue(pending, "passage 2 was marked fixed but is still kept")

    def test_a_passage_still_kept_is_not_fixed(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        result = self.fixed_flow(repo, rewrite=False)
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_verify_again_after_a_fixed_review_keeps_the_review(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        self.assertEqual(self.fixed_flow(repo).returncode, 0)
        self.assertEqual(repo.prose("compact", "notes.md", "--verify").returncode, 0)
        here = os.getcwd()
        os.chdir(repo.path)
        try:
            pending = compact.unverified(str(repo.path), False, repo.path / ".git/prose/passes")
        finally:
            os.chdir(here)
        self.assertEqual(pending, [])

    def test_an_unjustified_reason_needs_an_answer(self):
        reply = ("Change 1: superseded\nPassage 1: unjustified: it is history\n"
                 "Totals: 0 lost, 0 false\n")
        result = self.reviewed(reply)
        self.assertEqual(result.returncode, 2)
        self.assertIn("an unjustified reason for kept passage 1", result.stderr)
        result = self.reviewed(reply, "Passage 1: kept: a person asked to keep it\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 kept passage judged, 1 unjustified", result.stdout)


class Anchors(unittest.TestCase):
    def test_github_slugs_with_duplicates_numbered(self):
        text = "# `prose check` runs it\n\n## Why?\n\n## Why?\n\n```\n# in a code block\n```\n"
        # A heading-shaped line in a code block counts: --verify errs toward blocking.
        self.assertEqual(compact.anchors(text),
                         {"prose-check-runs-it", "why", "why-1", "in-a-code-block"})


class GoneTermsAndChanges(unittest.TestCase):
    """What the script hands the reviewer, at no model cost."""

    def test_gone_terms_finds_each_kind_once(self):
        before = ("# Doc\n\n## Kept\n\n## Dropped heading\n\nRun `prose check` with --goals-file;\n"
                  "RULES_IN_FULL is 9. See lib/commit-trailer/DECISIONS.md and rules.md.\n"
                  "Again `prose check`.\n")
        after = "# Doc\n\n## Kept\n\nRun prose check.\n"
        self.assertEqual(compact.gone_terms(before, after),
                         [("heading", "Dropped heading"), ("flag", "--goals-file"),
                          ("constant", "RULES_IN_FULL"), ("path", "lib/commit-trailer/DECISIONS.md"),
                          ("path", "rules.md")])

    def test_a_wrapped_code_span_or_a_heading_with_code_is_not_gone(self):
        before = "# Doc\n\n## `prose check` runs it\n\nUse `git worktree\nremove` here.\n"
        after = "# Doc\n\n## `prose check` runs it\n\nUse `git worktree remove`.\n"
        self.assertEqual(compact.gone_terms(before, after), [])

    def test_changes_ignore_rewrapping(self):
        before = "# T\n\nOne two\nthree.\n\nGone.\n"
        after = "# T\n\nOne two three.\n"
        self.assertEqual([(c.kind, c.old, c.new) for c in compact.changes(before, after)],
                         [("removed", ["Gone."], [])])


class CompactCommand(unittest.TestCase):
    """`prose compact <file>`: the brief, then --verify."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.doc = ("# Decisions\n\n## The token expires after two hours\n\nIt expires.\n\n"
                    "**Revised 2026-09-30.** It used to expire after one hour.\n\n"
                    "## Old section\n\nGone soon.\n")
        self.repo.write("DECISIONS.md", self.doc)
        self.repo.write("README.md", "See [why](DECISIONS.md#the-token-expires-after-two-hours).\n")
        self.repo.write("tool.py", "# DECISIONS: The token expires after two hours\n")
        self.repo.commit("base\n")

    def compact(self, *extra):
        # Stage, then verify or review: the staged file is what is checked.
        if extra[:1] in (("--verify",), ("--review",)):
            self.repo.git("add", "DECISIONS.md")
        return self.repo.prose("compact", "DECISIONS.md", *extra)

    def test_the_brief(self):
        result = self.compact()
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("=== compaction brief ===\n# Compact a document\n", result.stdout)
        self.assertIn(f"The file: {(self.repo.path / 'DECISIONS.md').resolve()}", result.stdout)
        self.assertIn("line 7: «Revised 2026-09-30»", result.stdout)
        self.assertIn("  #the-token-expires-after-two-hours  (in README.md)", result.stdout)
        self.assertIn("  The token expires after two hours  (in tool.py)", result.stdout)
        self.assertIn("compact DECISIONS.md --verify", result.stdout)

    def test_a_good_compaction_verifies(self):
        answers = answers_file(self.compact().stdout)
        (self.repo.path / "DECISIONS.md").write_text(
            "# Decisions\n\n## The token expires after two hours\n\nIt expires.\n")
        answers.write_text("Passage 1: removed\n")
        result = self.compact("--verify")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("References to removed headings: 0.", result.stdout)
        self.assertIn("Headings removed or renamed (1): Old section", result.stdout)

    def test_a_broken_link_a_named_heading_and_a_marker_fail(self):
        self.compact()
        (self.repo.path / "DECISIONS.md").write_text(
            "# Decisions\n\n## Expiry\n\nTwo hours. **Revised 2026-09-30.**\n")
        result = self.compact("--verify")
        self.assertEqual(result.returncode, 1)
        self.assertIn("README.md:1 links to #the-token-expires-after-two-hours", result.stdout)
        self.assertIn("tool.py:1 names 'The token expires after two hours'", result.stdout)
        self.assertIn("history marker left at line 5: «Revised 2026-09-30»", result.stdout)

    def test_a_file_that_grew_or_emptied_fails(self):
        for text, failure in ((self.doc + "More.\n", "the file grew"), ("\n", "the file is empty")):
            with self.subTest(failure=failure):
                self.compact()
                (self.repo.path / "DECISIONS.md").write_text(text)
                self.assertIn(failure, self.compact("--verify").stdout)

    def test_verify_without_a_snapshot_is_refused(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("SKILL.md", "# S\n")
        result = repo.prose("compact", "SKILL.md", "--verify")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no snapshot of SKILL.md", result.stderr)

    def test_a_missing_file_is_refused(self):
        result = self.repo.prose("compact", "nope.md")
        self.assertEqual(result.returncode, 2)
        self.assertIn("nope.md: no such file", result.stderr)

    def test_outside_a_repository_it_checks_the_files_own_links(self):
        folder = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        doc = folder / "DOC.md"
        doc.write_text("# A\n\nSee [b](#b).\n\n## B\n\nText here, at length.\n")
        self.assertEqual(run([sys.executable, str(SCRIPT), "compact", str(doc)]).returncode, 4)
        doc.write_text("# A\n\nSee [b](#b).\n")
        result = run([sys.executable, str(SCRIPT), "compact", str(doc), "--verify"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("Not in a git repository", result.stdout)
        self.assertIn("DOC.md:3 links to #b, a heading the compaction removed", result.stdout)

    def test_the_review_brief_names_a_file_of_every_change(self):
        self.compact()
        (self.repo.path / "DECISIONS.md").write_text(
            "# Decisions\n\n## The token expires after two hours\n\nIt expires, always.\n")
        result = self.compact("--review")
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("=== compaction review brief ===\n# Review a compaction\n", result.stdout)
        self.assertIn(f"The repository: {self.repo.path.resolve()}", result.stdout)
        self.assertIn("Changes: 1. Names gone: 1.", result.stdout)
        changes = pathlib.Path(re.search(r"^The changes: (.*)$", result.stdout, re.M).group(1))
        text = changes.read_text(encoding="utf-8")
        self.assertIn("- heading: Old section", text)
        self.assertIn('## Change 1: rewritten, under "The token expires after two hours"\n\n'
                      "### Before\n\nIt expires.\n\n**Revised 2026-09-30.** It used to expire "
                      "after one hour.\n\n## Old section\n\nGone soon.\n\n"
                      "### After\n\nIt expires, always.\n", text)

    def test_a_change_inside_code_is_a_change_but_rewrapping_prose_is_not(self):
        code = "```yaml\nroot:\n    child:\n        enabled: false\n```"
        self.assertEqual(len(compact.changes(f"# D\n\n{code}\n",
                                             "# D\n\n" + code.replace("    ", "") + "\n")), 1)
        self.assertEqual(len(compact.changes("# D\n\n    indented code\n",
                                             "# D\n\nindented code\n")), 1)
        self.assertEqual(compact.changes("# D\n\nOne long\nsentence here.\n",
                                         "# D\n\nOne long sentence\nhere.\n"), [])

    def test_a_fence_line_with_an_info_string_inside_a_block_keeps_changes_apart(self):
        doc = ("# T\n\n```\n```python\nx = 1\n```\n\n## Section B\n\nThe hook reads the file.\n\n"
               "## Section C\n\nOther text.\n")
        after = doc.replace("The hook reads the file.\n\n", "")
        self.assertEqual([(c.kind, c.heading, c.old) for c in compact.changes(doc, after)],
                         [("removed", "Section B", ["The hook reads the file."])])

    def test_a_fence_inside_a_quote_is_compared_exactly(self):
        self.assertEqual(len(compact.changes("> ```\n> a  b\n> ```\n", "> ```\n> a b\n> ```\n")), 1)

    def test_a_fence_opened_on_a_list_item_line_is_compared_exactly(self):
        before = "Intro.\n\n- ```yaml\n  a: 1\n  b: 2\n\n  c: 3\n  ```\n"
        self.assertEqual(len(compact.changes(before, before.replace("  b: 2", "   b: 2"))), 1)

    def test_verify_and_review_are_separate_steps(self):
        self.compact()
        result = self.compact("--verify", "--review")
        self.assertEqual(result.returncode, 2)
        self.assertIn("separate steps", result.stderr)

    def test_verify_suggests_no_budget(self):
        report = compact.check_result("x" * 100_000, "x" * 95_000, "DECISIONS.md", None)
        self.assertNotIn("budget", " ".join(report.lines))


class ConservativeVerify(unittest.TestCase):
    """--verify's rule: a removed heading or anchor that is still referenced,
    by its normalised text or its `#slug`, anywhere else, blocks the
    compaction."""

    def repo_with(self, files):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        for name, text in files.items():
            repo.write(name, text)
        repo.commit("base\n")
        return repo

    def verify_after(self, repo, new_text, name="DECISIONS.md"):
        self.assertEqual(repo.prose("compact", name).returncode, 4)
        (repo.path / name).write_text(new_text)
        repo.git("add", "--", name)
        return repo.prose("compact", name, "--verify")

    DOC = "# D\n\n## Snapshot lifetime policy\n\nA long paragraph about it.\n\n## Keep\n\nB.\n"
    AFTER = "# D\n\n## Keep\n\nB.\n"

    def test_an_unreferenced_heading_may_be_removed(self):
        repo = self.repo_with({"DECISIONS.md": self.DOC, "README.md": "Nothing to see.\n"})
        result = self.verify_after(repo, self.AFTER)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("References to removed headings: 0.", result.stdout)

    def test_an_incidental_mention_blocks(self):
        repo = self.repo_with({"DECISIONS.md": self.DOC,
                               "notes.txt": "We talked about a snapshot lifetime policy... "
                                            "the Snapshot lifetime policy, that is.\n"})
        result = self.verify_after(repo, self.AFTER)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("notes.txt:1 names 'Snapshot lifetime policy'", result.stdout)

    def test_an_anchor_substring_blocks(self):
        for text in ("See DECISIONS.md#snapshot-lifetime-policy.\n",
                     "# docs/x/DECISIONS.md#snapshot-lifetime-policy-and-more\n",
                     "https://example.com/other#snapshot-lifetime-policy\n"):
            with self.subTest(text=text):
                repo = self.repo_with({"DECISIONS.md": self.DOC, "code.py": text})
                result = self.verify_after(repo, self.AFTER)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("code.py:1 links to #snapshot-lifetime-policy", result.stdout)

    def test_the_files_own_anchor_blocks(self):
        repo = self.repo_with({"DECISIONS.md": self.DOC})
        result = self.verify_after(repo, self.AFTER + "\nSee [x](#snapshot-lifetime-policy).\n")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("DECISIONS.md:7 links to #snapshot-lifetime-policy", result.stdout)

    def test_the_heading_text_in_the_file_itself_does_not_block(self):
        repo = self.repo_with({"DECISIONS.md": self.DOC})
        result = self.verify_after(repo, self.AFTER + "\nThe Snapshot lifetime policy is gone.\n")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_short_headings_text_is_not_searched_but_its_anchor_is(self):
        doc = "# D\n\n## Why\n\nA long paragraph about why.\n\n## Keep\n\nB.\n"
        repo = self.repo_with({"DECISIONS.md": doc, "README.md": "Why not.\n"})
        self.assertEqual(self.verify_after(repo, self.AFTER).returncode, 0)
        repo = self.repo_with({"DECISIONS.md": doc, "README.md": "[w](DECISIONS.md#why)\n"})
        self.assertEqual(self.verify_after(repo, self.AFTER).returncode, 1)

    def test_a_reference_broken_before_does_not_count(self):
        repo = self.repo_with({"DECISIONS.md": self.DOC, "README.md": "[x](DECISIONS.md#never-was)\n"})
        self.assertEqual(self.verify_after(repo, self.AFTER).returncode, 0)

    def test_a_shared_heading_blocks(self):
        shared = "## Environment credentials belong to one identity"
        repo = self.repo_with({"a/DECISIONS.md": f"# A\n\n{shared}\n\nA long paragraph.\n\n## Keep\n\nB.\n",
                               "b/DECISIONS.md": f"# B\n\n{shared}\n\nC.\n"})
        result = self.verify_after(repo, "# A\n\n## Keep\n\nB.\n", "a/DECISIONS.md")
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_a_citation_is_matched_normalised(self):
        # Case, backticks, `*`, `_`, whitespace, and line breaks with the
        # comment or quote markers that start the next line, are ignored.
        doc = ("# D\n\n## `prose check` runs the *pre-commit* hook\n\nA long paragraph.\n\n"
               "## Keep\n\nB.\n")
        for text, line in (("x = 1\n# See Prose check\n# runs the pre-commit\n#   hook first.\n", 2),
                           ("// DECISIONS: prose check runs\n// the PRE-COMMIT hook\n", 1),
                           ("> quoted: `prose check` runs\n> the pre-commit    hook\n", 1),
                           ("/*\n * prose check runs the\n * pre-commit hook\n */\n", 2)):
            with self.subTest(text=text):
                repo = self.repo_with({"DECISIONS.md": doc, "code.c": text})
                result = self.verify_after(repo, self.AFTER)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(f"code.c:{line} names '`prose check` runs the *pre-commit* hook'",
                              result.stdout)

    def test_removing_one_of_two_same_headings_searches_both_anchors(self):
        doc = "# D\n\n## Notes\n\nfirst notes, about caching\n\n## Notes\n\nsecond notes\n"
        repo = self.repo_with({"DECISIONS.md": doc, "other.md": "Caching: see DECISIONS.md#notes\n"})
        result = self.verify_after(repo, "# D\n\n## Notes\n\nsecond notes\n")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("other.md:1 links to #notes,", result.stdout)
        self.assertIn("Headings removed or renamed (1): Notes", result.stdout)

    def test_bare_carriage_returns_break_lines(self):
        repo = self.repo_with({"DECISIONS.md": self.DOC})
        (repo.path / "notes.txt").write_bytes(b"# see the Snapshot\r# lifetime policy section\r")
        repo.git("add", "notes.txt")
        self.assertEqual(self.verify_after(repo, self.AFTER).returncode, 1)

    def test_case_is_folded_not_lowered(self):
        doc = "# D\n\n## Gr\u00f6\u00dfe der Stra\u00dfe handling\n\nA long paragraph.\n\n## Keep\n\nB.\n"
        repo = self.repo_with({"DECISIONS.md": doc, "notes.txt": "See GR\u00d6SSE DER STRASSE HANDLING.\n"})
        self.assertEqual(self.verify_after(repo, self.AFTER).returncode, 1)

    def test_a_heading_needle_is_normalised_as_the_files_are(self):
        texts = {compact.normalised([(0, "Snapshot lifetime\r# policy rules")])[0]: "h"}
        self.assertEqual(len(compact._find("r.md", [(1, "Snapshot lifetime\r# policy rules")],
                                           [], texts)), 1)

    def test_a_bom_or_bare_cr_line_ends_do_not_hide_headings(self):
        self.assertEqual(compact.heading_texts("\ufeff# Title here\n\n## Next\n"), ["Title here", "Next"])
        self.assertEqual(compact.heading_texts("# Doc\r\rIntro.\r\r## Snapshot lifetime policy\r"),
                         ["Doc", "Snapshot lifetime policy"])

    def test_normalising_keeps_other_punctuation(self):
        self.assertEqual(compact.normalise_line("  # // > **The `C#` heading**,  here "),
                         "the c# heading, here")
        repo = self.repo_with({"DECISIONS.md": self.DOC, "a.md": "Snapshot-lifetime policy\n"})
        self.assertEqual(self.verify_after(repo, self.AFTER).returncode, 0)

    def test_grep_config_does_not_hide_or_break_references(self):
        for key, value in (("grep.column", "true"), ("color.ui", "always"), ("color.grep", "always")):
            with self.subTest(key=key):
                repo = self.repo_with({"DECISIONS.md": self.DOC,
                                       "other.md": "See DECISIONS.md#snapshot-lifetime-policy.\n"})
                repo.git("config", key, value)
                result = self.verify_after(repo, self.AFTER)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("other.md:1 links to #snapshot-lifetime-policy", result.stdout)

    def test_a_removed_headings_own_anchor_is_searched_when_a_survivor_takes_it(self):
        doc = ("# D\n\n## Retry policy: backoff\n\nA long paragraph.\n\n"
               "## Retry policy backoff\n\nB.\n")
        repo = self.repo_with({"DECISIONS.md": doc, "other.md": "DECISIONS.md#retry-policy-backoff\n"})
        result = self.verify_after(repo, "# D\n\n## Retry policy backoff\n\nB.\n")
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_a_heading_in_a_code_block_counts(self):
        doc = "# D\n\n```\n## Snapshot lifetime policy\n```\n\nA long example.\n\n## Keep\n\nB.\n"
        repo = self.repo_with({"DECISIONS.md": doc, "other.md": "DECISIONS.md#snapshot-lifetime-policy\n"})
        self.assertEqual(self.verify_after(repo, self.AFTER).returncode, 1)

    def test_crlf_line_ends_read_as_lf(self):
        repo = self.repo_with({"DECISIONS.md": self.DOC.replace("\n", "\r\n"),
                               "other.md": "DECISIONS.md#snapshot-lifetime-policy\n"})
        result = self.verify_after(repo, self.AFTER.replace("\n", "\r\n"))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("other.md:1 links to #snapshot-lifetime-policy", result.stdout)
        self.assertEqual([m.line for m in compact.history_markers(
            "# R\r\n\r\n```bash\r\nx\r\n```\r\n\r\nWe previously used tabs.\r\n")], [7])

    def test_a_kept_heading_sharing_a_removed_headings_anchor_blocks(self):
        # Accepted over-blocking: a rename that keeps the anchor blocks too.
        for before, after in (("## Foo bar\n\nA.\n\n## foo bar\n\nB, at length.\n", "## Foo bar\n\nA.\n"),
                              ("## Setup and usage\n\nA, at length.\n", "## Setup and Usage\n\nA.\n")):
            with self.subTest(after=after):
                repo = self.repo_with({"DECISIONS.md": "# D\n\n" + before,
                                       "other.md": f"DECISIONS.md#{compact.slug(after.split(chr(10))[0][3:])}\n"})
                self.assertEqual(self.verify_after(repo, "# D\n\n" + after).returncode, 1)

    def test_only_a_tracked_path_spelt_as_git_lists_it_is_accepted(self):
        repo = self.repo_with({"Doc.md": self.DOC})
        (repo.path / "new.md").write_text(self.DOC)
        for name in ("new.md",) + (("doc.md",) if (repo.path / "doc.md").exists() else ()):
            with self.subTest(name=name):
                result = repo.prose("compact", name)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("not a tracked file", result.stderr)

    def test_outside_a_repository_the_files_own_anchors_are_checked(self):
        folder = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        doc = folder / "DECISIONS.md"
        doc.write_text(self.DOC)
        self.assertEqual(run([sys.executable, str(SCRIPT), "compact", str(doc)]).returncode, 4)
        doc.write_text(self.AFTER + "\nSee [x](#snapshot-lifetime-policy).\n")
        result = run([sys.executable, str(SCRIPT), "compact", str(doc), "--verify"])
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Not in a git repository", result.stdout)

    def test_git_rev_parse_failing_means_outside_whatever_it_says(self):
        # A repository git refuses for its owner, a broken .git link and a
        # filesystem boundary all fail rev-parse: each is outside a
        # repository, and the report says other files were not checked.
        repo = self.repo_with({"DECISIONS.md": self.DOC, "a.txt": "Snapshot lifetime policy\n"})
        env = dict(os.environ, GIT_TEST_ASSUME_DIFFERENT_OWNER="1")
        result = run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md"], cwd=repo.path, env=env)
        self.assertEqual(result.returncode, 4, result.stderr)
        (repo.path / "DECISIONS.md").write_text(self.AFTER)
        result = run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md", "--verify"],
                     cwd=repo.path, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("references from other files were not checked", result.stdout)
        folder = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / ".git").write_text("gitdir: /nonexistent/repo/.git\n")
        (folder / "DECISIONS.md").write_text(self.DOC)
        result = run([sys.executable, str(SCRIPT), "compact", str(folder / "DECISIONS.md")])
        self.assertEqual(result.returncode, 4, result.stderr)

    def test_grep_writing_an_error_fails_even_when_it_exits_0(self):
        if os.geteuid() == 0:
            self.skipTest("root reads every file")
        repo = self.repo_with({"DECISIONS.md": self.DOC, "other.md": "Nothing.\n"})
        self.assertEqual(repo.prose("compact", "DECISIONS.md").returncode, 4)
        repo.write("DECISIONS.md", self.AFTER)
        # The index's old copy of other.md still matches, so git grep exits 0.
        (repo.path / "other.md").write_text("See Snapshot lifetime policy.\n")
        os.chmod(repo.path / "other.md", 0)
        self.addCleanup(os.chmod, repo.path / "other.md", 0o644)
        result = repo.prose("compact", "DECISIONS.md", "--verify")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("git grep failed", result.stderr)

    def test_submodules_are_not_searched_whatever_the_config(self):
        sub = self.repo_with({"n.txt": "Snapshot lifetime policy\n"})
        repo = self.repo_with({"DECISIONS.md": self.DOC})
        repo.git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub.path), "sub")
        repo.commit("sub\n")
        repo.git("config", "submodule.recurse", "true")
        self.assertEqual(self.verify_after(repo, self.AFTER).returncode, 0)

    BINARY = b"see DECISIONS.md#snapshot-lifetime-policy, the Snapshot lifetime policy\0\n"

    def binary_repo(self, attributes):
        repo = self.repo_with({".gitattributes": attributes, "DECISIONS.md": self.DOC,
                               "plain.md": "Nothing here.\n"})
        (repo.path / "blob.dat").write_bytes(self.BINARY)
        repo.git("add", "blob.dat")
        repo.commit("blob\n")
        return repo

    def test_a_file_git_treats_as_binary_is_not_searched(self):
        for attributes in ("", "notes.md -diff\n", "notes.md binary\n"):
            with self.subTest(attributes=attributes):
                repo = self.binary_repo(attributes)
                repo.write("notes.md", "see DECISIONS.md#snapshot-lifetime-policy\n")
                repo.commit("notes\n")
                result = self.verify_after(repo, self.AFTER)
                self.assertNotIn("blob.dat", result.stdout)
                if attributes:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertNotIn("notes.md", result.stdout)
                else:
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("notes.md:1 links to", result.stdout)
                self.assertIn("skipping files git treats as binary", result.stdout)

    def test_a_diff_attribute_brings_a_binary_file_back_into_the_search(self):
        repo = self.binary_repo("blob.dat diff\n")
        result = self.verify_after(repo, self.AFTER)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("blob.dat:1 links to #snapshot-lifetime-policy", result.stdout)
        self.assertIn("blob.dat:1 names 'Snapshot lifetime policy'", result.stdout)

    def test_a_binary_file_staged_only_is_skipped_and_its_diff_attribute_honoured(self):
        # blob.dat's work-tree copy is plain text and its staged copy binary,
        # so only the index run can find it, and it skips the staged copy as
        # binary unless the diff attribute is set.
        for attributes, code in (("", 0), ("blob.dat diff\n", 1)):
            with self.subTest(attributes=attributes):
                repo = self.binary_repo(attributes)
                self.assertEqual(repo.prose("compact", "DECISIONS.md").returncode, 4)
                (repo.path / "blob.dat").write_text("Nothing here.\n")
                repo.write("DECISIONS.md", self.AFTER)
                repo.git("add", "DECISIONS.md")
                result = repo.prose("compact", "DECISIONS.md", "--verify")
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)

    def test_a_diff_attribute_outside_a_sparse_index_cone_is_honoured(self):
        for flag, attributes in (("--no-sparse-index", "far/.gitattributes"),
                                 ("--sparse-index", "far/.gitattributes"),
                                 ("--sparse-index", ".gitattributes")):
            with self.subTest(flag=flag, attributes=attributes):
                line = "blob.dat diff\n" if attributes.startswith("far/") else "far/blob.dat diff\n"
                repo = self.repo_with({"DECISIONS.md": self.DOC, attributes: line, "near/x.md": "x\n",
                                       "far/other.md": "x\n"})
                (repo.path / "far" / "blob.dat").write_bytes(self.BINARY)
                repo.git("add", "far/blob.dat")
                repo.commit("blob\n")
                repo.git("sparse-checkout", "init", "--cone", flag)
                repo.git("sparse-checkout", "set", "near")
                result = self.verify_after(repo, self.AFTER)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("far/blob.dat:1 links to", result.stdout)

    def test_a_binary_file_named_as_a_referrer_is_searched(self):
        repo = self.binary_repo("")
        result = self.verify_after(repo, self.AFTER)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = repo.prose("compact", "DECISIONS.md", "--verify", "--", "blob.dat")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("blob.dat:1 links to", result.stdout)

    def test_a_hash_ending_a_headings_text_is_kept(self):
        self.assertEqual(compact.heading_texts("## Building with C#\n## Closed ##\n"),
                         ["Building with C#", "Closed"])

    def test_a_tracked_symlink_is_refused(self):
        repo = self.repo_with({"README.md": "x\n"})
        (repo.path / "untracked.md").write_text(self.DOC)
        os.symlink("untracked.md", repo.path / "link.md")
        repo.git("add", "link.md")
        repo.commit("link\n")
        # A symlink's blob is its target's name, not prose.
        result = repo.prose("compact", "link.md")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("a symlink holds no prose", result.stderr)

    def test_an_unreadable_tracked_file_is_an_error(self):
        if os.geteuid() == 0:
            self.skipTest("root reads every file")
        repo = self.repo_with({"DECISIONS.md": self.DOC, "ref.md": "Snapshot lifetime policy\n"})
        self.assertEqual(repo.prose("compact", "DECISIONS.md").returncode, 4)
        (repo.path / "DECISIONS.md").write_text(self.AFTER)
        os.chmod(repo.path / "ref.md", 0)
        self.addCleanup(os.chmod, repo.path / "ref.md", 0o644)
        self.assertEqual(repo.prose("compact", "DECISIONS.md", "--verify").returncode, 2)

    def test_a_tracked_file_outside_the_work_tree_is_still_searched(self):
        repo = self.repo_with({"DECISIONS.md": self.DOC, "ref.md": "Snapshot lifetime policy\n"})
        repo.git("sparse-checkout", "set", "--no-cone", "/DECISIONS.md")
        self.assertEqual(self.verify_after(repo, self.AFTER).returncode, 1)

    def test_a_root_whose_name_ends_in_a_space_works(self):
        parent = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, parent, True)
        root = parent / "sp "
        root.mkdir()
        run(["git", "init", "-q"], cwd=root)
        (root / "DECISIONS.md").write_text(self.DOC)
        run(["git", "add", "DECISIONS.md"], cwd=root)
        run(["git", "-c", "user.name=T", "-c", "user.email=t@e", "commit", "-qm", "base"], cwd=root)
        self.assertEqual(run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md"], cwd=root).returncode, 4)

    def test_extra_spaces_after_the_hashes_are_not_part_of_the_heading(self):
        self.assertEqual(compact.heading_texts("##  Configuration of the widget\n"),
                         ["Configuration of the widget"])

    def test_a_path_with_a_space_is_quoted_in_the_next_command(self):
        repo = self.repo_with({"my skill/SKILL.md": "# S\n\n## Size budget\n\nA.\n"})
        self.assertIn("compact 'my skill/SKILL.md' --verify",
                      repo.prose("compact", "my skill/SKILL.md").stdout)

    def test_a_file_once_emptied_is_measured_without_dividing_by_zero(self):
        repo = self.repo_with({"SKILL.md": "x" * 100})
        repo.write("SKILL.md", "")
        repo.commit("empty\n")
        repo.write("SKILL.md", "y " * 25000)
        found = compact.due(["SKILL.md"], str(repo.path))
        self.assertEqual(len(found), 1, found)

    def test_a_compaction_inside_a_merged_branch_is_found(self):
        repo = self.repo_with({".gitattributes": "* prose-compact-budget=1000\n",
                               "DECISIONS.md": paragraphs(30)})
        repo.git("checkout", "-q", "-b", "pr")
        repo.write("DECISIONS.md", paragraphs(36))
        repo.commit("grow\n")
        repo.write("DECISIONS.md", paragraphs(31))
        repo.commit("compact\n")
        repo.git("checkout", "-q", "-")
        repo.git("merge", "-q", "--no-ff", "-m", "merge", "pr")
        repo.write("DECISIONS.md", paragraphs(32))
        self.assertEqual(compact.due(["DECISIONS.md"], str(repo.path)), [])

    def test_tracked_symlinks_are_not_counted_as_searched(self):
        repo = self.repo_with({"DECISIONS.md": self.DOC})
        os.symlink("DECISIONS.md#snapshot-lifetime-policy", repo.path / "link.md")
        repo.git("add", "link.md")
        repo.commit("link\n")
        result = self.verify_after(repo, self.AFTER)
        self.assertIn("the repository's 1 tracked file,", result.stdout)

    def test_a_sparse_index_hint_is_not_an_error(self):
        repo = self.repo_with({"DECISIONS.md": self.DOC, "far/ref.md": "x\n"})
        repo.git("sparse-checkout", "init", "--cone", "--sparse-index")
        repo.git("sparse-checkout", "set", "near")
        (repo.path / "far").mkdir(exist_ok=True)
        (repo.path / "far" / "ref.md").write_text("Snapshot lifetime policy\n")
        result = self.verify_after(repo, self.AFTER)
        self.assertNotIn("git grep failed", result.stderr)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_indented_and_tab_separated_headings_are_headings(self):
        self.assertEqual(compact.heading_texts("   ## Indented heading here\n##\tTabbed heading here\n"
                                               "    ## Code, not a heading\n"),
                         ["Indented heading here", "Tabbed heading here"])

    def test_a_tracked_file_whose_name_holds_a_newline_is_attributed_rightly(self):
        repo = self.repo_with({"DECISIONS.md": self.DOC,
                               "x\nDECISIONS.md": "See DECISIONS.md#snapshot-lifetime-policy\n"})
        result = self.verify_after(repo, self.AFTER)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("x\nDECISIONS.md:1 links to", result.stdout)

    def test_the_tracked_count_leaves_out_submodules_and_says_so(self):
        sub = self.repo_with({"n.txt": "x\n"})
        repo = self.repo_with({"DECISIONS.md": self.DOC})
        repo.git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub.path), "sub")
        repo.commit("sub\n")
        result = self.verify_after(repo, self.AFTER)
        self.assertIn("the repository's 2 tracked files, in the work tree and the index, "
                      "not its 1 submodule", result.stdout)

    def test_a_marker_wrapped_across_a_line_is_found(self):
        self.assertEqual(
            [m.line for m in compact.history_markers("The limit was changed\nto 5.\n\n**Revised\n2026-09-30.** X.\n")],
            [1, 4])



class GivenReferrers(unittest.TestCase):
    """The files --verify searches beside the tracked ones: paths after `--`,
    and lists from --paths-from."""

    DOC = ConservativeVerify.DOC
    AFTER = ConservativeVerify.AFTER
    LINK = "See [it](DECISIONS.md#snapshot-lifetime-policy).\n"

    def folder(self, files):
        folder = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        for name, text in files.items():
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            (folder / name).write_text(text) if isinstance(text, str) else (folder / name).write_bytes(text)
        return folder

    def outside(self, files, *extra, stdin=None):
        folder = self.folder(dict({"DECISIONS.md": self.DOC}, **files))
        self.assertEqual(run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md"],
                             cwd=folder).returncode, 4)
        (folder / "DECISIONS.md").write_text(self.AFTER)
        return run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md", "--verify", *extra],
                   cwd=folder, stdin=stdin)

    def test_outside_with_no_paths_says_other_files_were_not_checked(self):
        result = self.outside({"notes/a.md": self.LINK})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Searched for references: the file's own links. Not in a git repository and "
                      "no paths given, so references from other files were not checked", result.stdout)

    def test_files_after_the_dashes(self):
        result = self.outside({"notes/a.md": self.LINK, "b.txt": "Snapshot lifetime policy\n"},
                              "--", "b.txt", "notes/a.md", "notes/a.md")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("notes/a.md:1 links to #snapshot-lifetime-policy", result.stdout)
        self.assertIn("b.txt:1 names 'Snapshot lifetime policy'", result.stdout)
        self.assertEqual(result.stdout.count("notes/a.md:1 links to"), 1, result.stdout)

    def test_a_directory_is_refused_with_how_to_list_its_files(self):
        result = self.outside({"notes/a.md": self.LINK}, "--", "notes")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("notes: a directory; name the files in it", result.stderr)
        self.assertIn("rg -l <name> notes | prose compact --verify <file> --paths-from -",
                      result.stderr)
        self.assertIn("-print0", result.stderr)

    def test_a_dangling_symlink_is_an_error(self):
        folder = self.folder({"DECISIONS.md": self.DOC})
        os.symlink("nowhere.md", folder / "dangling.md")
        result = run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md", "--",
                      "dangling.md"], cwd=folder)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("dangling.md: no such file", result.stderr)

    def test_a_file_named_after_the_dashes_is_read_whatever_its_suffix(self):
        result = self.outside({"a.py": self.LINK}, "--", "a.py")
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_paths_from_a_file_and_from_stdin(self):
        result = self.outside({"n/a.md": self.LINK, "list.txt": "n/a.md\r\n\n"},
                              "--paths-from", "list.txt")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("n/a.md:1 links to", result.stdout)
        result = self.outside({"n/a.md": self.LINK}, "--paths-from", "-", stdin="n/a.md\n")
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_nul_separated_paths_keep_spaces_and_newlines(self):
        result = self.outside({"n/a b\nc.md": self.LINK}, "--paths-from", "-", "-0",
                              stdin="n/a b\nc.md\0")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("1 given file from the list on stdin.", result.stdout)

    def test_a_nul_separated_list_without_the_flag_says_add_it(self):
        result = self.outside({"n/a.md": self.LINK}, "--paths-from", "-", stdin="n/a.md\0")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("holds NUL bytes", result.stderr)
        self.assertIn("add -0", result.stderr)

    def test_paths_after_the_dashes_follow_any_option(self):
        result = self.outside({"n/a.md": self.LINK, "list.txt": "n/b.md\n", "n/b.md": "x\n"},
                              "--paths-from", "list.txt", "--", "n/a.md")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("2 given files", result.stdout)

    def test_a_file_named_after_the_dashes_alone_is_the_doc(self):
        folder = self.folder({"-notes.md": self.DOC, "r.md": self.LINK})
        result = run([sys.executable, str(SCRIPT), "compact", "--", "-notes.md"], cwd=folder)
        self.assertEqual(result.returncode, 4, result.stderr)
        result = run([sys.executable, str(SCRIPT), "compact", "--verify", "--", "-notes.md",
                      "r.md"], cwd=folder)
        self.assertNotIn("arguments are required", result.stderr)
        self.assertIn("1 given file from r.md", result.stdout)

    def test_the_commands_printed_for_a_dash_named_file_run(self):
        folder = self.folder({"-notes.md": self.DOC})
        result = run([sys.executable, str(SCRIPT), "compact", "--", "-notes.md"], cwd=folder)
        self.assertIn("compact ./-notes.md --verify", result.stdout)
        self.assertEqual(compact.command_path("-x.md"), "./-x.md")
        self.assertEqual(compact.command_path("a b.md"), "'a b.md'")

    def test_a_closed_stdin_does_not_crash(self):
        folder = self.folder({"DECISIONS.md": self.DOC})
        result = subprocess.run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md"], cwd=folder,
                                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                close_fds=True, preexec_fn=lambda: os.close(0))
        self.assertEqual(result.returncode, 4, result.stderr)

    def test_a_referrer_without_the_dashes_and_an_abbreviation_are_errors(self):
        folder = self.folder({"DECISIONS.md": self.DOC, "r.md": self.LINK, "l.txt": "r.md\n"})
        for extra in (["r.md"], ["--verify", "r.md"], ["--paths", "l.txt"]):
            with self.subTest(extra=extra):
                result = run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md", *extra],
                             cwd=folder)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("unrecognized arguments", result.stderr)

    def test_printed_fixes_use_the_callers_spelling(self):
        folder = self.folder({"DECISIONS.md": self.DOC, "-docs/a.md": self.LINK})
        result = run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md", "--", "-docs"],
                     cwd=folder)
        self.assertIn("rg -l <name> ./-docs", result.stderr)
        repo = ConservativeVerify.repo_with(self, {"sub/DECISIONS.md": self.DOC})
        self.assertEqual(run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md"],
                             cwd=repo.path / "sub").returncode, 4)
        (repo.path / "sub/DECISIONS.md").write_text(self.AFTER)
        result = run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md", "--verify"],
                     cwd=repo.path / "sub")
        self.assertIn("(git add DECISIONS.md)", result.stderr)

    def test_abandon_outside_a_repository(self):
        folder = self.folder({"DECISIONS.md": self.DOC})
        env = dict(os.environ, XDG_STATE_HOME=str(folder / "state"))
        abandon = [sys.executable, str(SCRIPT), "compact", "DECISIONS.md", "--abandon"]
        self.assertEqual(run(abandon, cwd=folder, env=env).returncode, 2)
        run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md"], cwd=folder, env=env)
        self.assertEqual(run(abandon, cwd=folder, env=env).returncode, 0)
        result = run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md", "--verify"],
                     cwd=folder, env=env)
        self.assertIn("no snapshot of DECISIONS.md", result.stderr)

    def test_an_empty_list_is_reported_as_empty(self):
        result = self.outside({}, "--paths-from", "-", stdin="")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("0 given files (the list was empty)", result.stdout)

    def test_a_missing_path_and_a_misused_flag_are_refused(self):
        self.assertIn("nope: no such file", self.outside({}, "--", "nope").stderr)
        self.assertIn("-0 goes with --paths-from", self.outside({}, "-0").stderr)
        folder = self.folder({"DECISIONS.md": self.DOC})
        run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md"], cwd=folder)
        result = run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md", "--review", "--",
                      "DECISIONS.md"],
                     cwd=folder)
        self.assertEqual(result.returncode, 2)

    def test_the_report_names_where_each_list_came_from(self):
        result = self.outside({"n/a.md": self.LINK, "list.txt": "n/a.md\n"},
                              "--paths-from", "list.txt", "--", "n/a.md")
        self.assertIn("2 given files from the list in list.txt, n/a.md.", result.stdout)
        result = self.outside({"n/a.md": self.LINK}, "--paths-from", "-", stdin="n/a.md\n")
        self.assertIn("1 given file from the list on stdin.", result.stdout)

    def test_an_unreadable_referrer_fails_even_when_nothing_was_removed(self):
        if os.geteuid() == 0:
            self.skipTest("root reads every file")
        folder = self.folder({"DECISIONS.md": self.DOC + "\nWe previously did it.\n", "ref.md": "x\n"})
        run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md"], cwd=folder)
        (folder / "DECISIONS.md").write_text(self.DOC)
        os.chmod(folder / "ref.md", 0)
        self.addCleanup(os.chmod, folder / "ref.md", 0o644)
        result = run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md", "--verify", "--",
                      "ref.md"], cwd=folder)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("ref.md: could not read it", result.stderr)

    def test_a_snapshot_of_any_age_is_still_used(self):
        folder = self.folder({"DECISIONS.md": self.DOC, "r.md": self.LINK})
        env = dict(os.environ, XDG_STATE_HOME=str(folder / "state"))
        run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md"], cwd=folder, env=env)
        for snapshot in (folder / "state/prose/compact").iterdir():
            if snapshot.name.startswith("."):
                continue
            fields = json.loads(snapshot.read_text())
            fields["saved"] -= 30 * 24 * 60 * 60
            snapshot.write_text(json.dumps(fields))
            old = fields["saved"]
            os.utime(snapshot, (old, old))
        (folder / "DECISIONS.md").write_text(self.AFTER)
        result = run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md", "--verify", "--",
                      "r.md"], cwd=folder, env=env)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("r.md:1 links to", result.stdout)

    def test_the_doc_named_in_another_case_or_by_a_hard_link_is_not_a_referrer(self):
        folder = self.folder({"DECISIONS.md": self.DOC})
        os.link(folder / "DECISIONS.md", folder / "alias.md")
        names = ["alias.md"] + (["decisions.md"] if (folder / "decisions.md").exists() else [])
        files = compact.referrer_files([str(folder / n) for n in names], folder / "DECISIONS.md")
        self.assertEqual(files.files, [])

    def test_a_referrer_that_exists_but_cannot_be_read_says_so(self):
        if os.geteuid() == 0:
            self.skipTest("root reads every file")
        folder = self.folder({"DECISIONS.md": self.DOC, "locked/ref.md": "x\n"})
        os.mkfifo(folder / "fifo")
        os.chmod(folder / "locked", 0)
        self.addCleanup(os.chmod, folder / "locked", 0o755)
        with self.assertRaisesRegex(ValueError, "not a regular file"):
            compact.referrer_files([str(folder / "fifo")], folder / "DECISIONS.md")
        with self.assertRaisesRegex(ValueError, "could not read it"):
            compact.referrer_files([str(folder / "locked/ref.md")], folder / "DECISIONS.md")

    def test_the_doc_itself_is_not_a_referrer(self):
        result = self.outside({}, "--", "DECISIONS.md", "./DECISIONS.md")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("0 given files", result.stdout)

    def test_inside_a_repository_given_paths_add_to_the_tracked_files(self):
        repo = ConservativeVerify.repo_with(self, {"DECISIONS.md": self.DOC})
        (repo.path / "untracked.md").write_text(self.LINK)
        elsewhere = self.folder({"x.md": self.LINK})
        self.assertEqual(repo.prose("compact", "DECISIONS.md").returncode, 4)
        repo.write("DECISIONS.md", self.AFTER)
        result = repo.prose("compact", "DECISIONS.md", "--verify")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("the repository's 1 tracked file, in the work tree and the index, skipping "
                      "files git treats as binary.", result.stdout)
        result = repo.prose("compact", "DECISIONS.md", "--verify", "--", "untracked.md",
                            str(elsewhere / "x.md"))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("untracked.md:1 links to", result.stdout)
        self.assertIn(f"{elsewhere}/x.md:1 links to", result.stdout)

    def test_the_brief_names_headings_a_given_file_references_and_the_command(self):
        folder = self.folder({"DECISIONS.md": self.DOC, "n/a.md": self.LINK})
        result = run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md", "--", "n/a.md"],
                     cwd=folder)
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("  #snapshot-lifetime-policy  (in n/a.md)", result.stdout)
        self.assertIn("compact DECISIONS.md --verify -- n/a.md\n", result.stdout)
        self.assertNotIn("checks only its own links", result.stdout)

    def test_the_brief_outside_a_repository_points_at_how_to_find_referrers(self):
        folder = self.folder({"DECISIONS.md": self.DOC})
        result = run([sys.executable, str(SCRIPT), "compact", "DECISIONS.md"], cwd=folder)
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("checks only its own links", result.stdout)
        self.assertIn(f"({compact.STEPS}, *Which files refer to the doc*)",
                      " ".join(result.stdout.split()))


class CompactionGate(unittest.TestCase):
    """`prose check` refuses to sign a compaction unless --verify passed on
    the staged blob and its review was completed."""

    DOC = ConservativeVerify.DOC + "".join(f"\nParagraph {n}, at some length.\n" for n in range(20))
    AFTER = ConservativeVerify.AFTER
    PASSES = ".git/prose/passes"

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("DECISIONS.md", self.DOC)
        self.repo.commit("base\n")

    def sign(self):
        (self.repo.path / ".msg").write_text("DOCS(x): compact\n")
        return self.repo.two_calls("check", "-F", ".msg", "--goals", "review it")

    def pending(self):
        # From the repository, as prose check runs, so printed paths are
        # relative to it.
        here = os.getcwd()
        os.chdir(self.repo.path)
        try:
            return compact.unverified(str(self.repo.path), False, self.repo.path / self.PASSES)
        finally:
            os.chdir(here)

    def write(self, name, text):
        path = self.repo.path / name
        path.write_text(text)
        return str(path)

    CLEAN = "Change 1: superseded\nChange 2: superseded\nTotals: 0 lost, 0 false\n"

    def compaction(self, after=None, reply=CLEAN):
        """The steps compaction.md gives, without step 4's cold read:
        snapshot, compact and stage (Repo.write stages), verify, review,
        record the review."""
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        self.repo.write("DECISIONS.md", self.AFTER if after is None else after)
        verified = self.repo.prose("compact", "DECISIONS.md", "--verify")
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--review").returncode, 4)
        return self.repo.prose("compact", "DECISIONS.md", "--reviewed", self.write(".reply", reply))

    def test_an_unverified_unreviewed_compaction_is_refused_naming_both_steps(self):
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        self.repo.write("DECISIONS.md", self.AFTER)
        first = self.repo.prose("check", "-F", "-", "--goals", "g", stdin="DOCS(x): c\n")
        self.assertIn("DECISIONS.md was compacted but not verified", first.stdout)
        result = self.sign()
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("DECISIONS.md was compacted but not verified; run "
                      "`prose compact --verify DECISIONS.md`", result.stderr)
        self.assertIn("DECISIONS.md was compacted but its review was not completed", result.stderr)
        # Both the first call's listing and the refusal name the steps' file.
        self.assertIn(f"The steps are in {compact.STEPS}.", first.stdout)
        self.assertIn(f"; the steps are in {compact.STEPS}", result.stderr)

    def test_the_cold_read_brief_comes_before_the_review_and_signing_waits_for_it(self):
        # compaction.md: the cold read of a compacted file runs before its reviews,
        # so the reviews check the cold read's fixes.
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        # A rewritten line, so the compacted file has a passage to read cold.
        self.repo.write("DECISIONS.md", self.AFTER.replace("B.", "B, now clearer."))
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--verify").returncode, 0)
        (self.repo.path / ".msg").write_text("DOCS(x): compact\n")
        first = self.repo.prose("check", "-F", ".msg", "--goals", "review it")
        token = pass_token(first.stdout)
        sign = lambda *extra: self.repo.prose("check", "-F", ".msg", "--goals", "review it",
                                              "--pass", token, *extra)
        needed = sign()
        self.assertEqual(needed.returncode, prose.COLD_READ_NEEDED, needed.stderr)
        self.assertIn("=== cold-read brief ===", needed.stdout)
        self.assertIn("DECISIONS.md was compacted but its review was not completed",
                      needed.stdout)
        self.assertIn(f"The steps are in {compact.STEPS}.", needed.stdout)
        flags = straight_report(needed.stdout)
        refused = sign(*flags)
        self.assertEqual(refused.returncode, 2, refused.stdout)
        self.assertIn("its review was not completed", refused.stderr)
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--review").returncode, 4)
        done = self.repo.prose("compact", "DECISIONS.md", "--reviewed",
                               self.write(".reply", self.CLEAN))
        self.assertEqual(done.returncode, 0, done.stderr)
        signed = sign(*flags)
        self.assertEqual(signed.returncode, 0, signed.stderr)

    def test_a_compaction_with_nothing_to_read_cold_promises_no_brief(self):
        # Only lines removed: no passage to read cold, so the first call must
        # not say the signing call can print a brief.
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        self.repo.write("DECISIONS.md", self.AFTER)
        first = self.repo.prose("check", "-F", "-", "--goals", "g", stdin="DOCS(x): c\n")
        self.assertEqual(first.returncode, 4, first.stderr)
        self.assertIn("DECISIONS.md was compacted but not verified", first.stdout)
        self.assertNotIn("cold-read brief now", first.stdout)

    def test_a_verified_and_reviewed_compaction_signs(self):
        done = self.compaction()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.pending(), [])
        result = self.sign()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_verified_but_not_reviewed_names_the_review(self):
        self.repo.prose("compact", "DECISIONS.md")
        self.repo.write("DECISIONS.md", self.AFTER)
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--verify").returncode, 0)
        found = self.pending()
        self.assertEqual(len(found), 1, found)
        self.assertIn("its review was not completed", found[0])

    def test_verify_and_review_refuse_an_unstaged_file(self):
        self.repo.prose("compact", "DECISIONS.md")
        (self.repo.path / "DECISIONS.md").write_text(self.AFTER)
        for step in ("--verify", "--review"):
            result = self.repo.prose("compact", "DECISIONS.md", step)
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("has changes that are not staged", result.stderr)

    def test_a_change_after_the_records_is_refused_again(self):
        self.compaction()
        self.repo.write("DECISIONS.md", self.AFTER + "\nMore.\n")
        self.assertEqual(len(self.pending()), 2)

    def test_the_first_call_refuses_a_file_that_differs_from_head(self):
        self.repo.prose("compact", "DECISIONS.md")
        self.repo.write("DECISIONS.md", self.AFTER)
        # Run again on the compacted copy: refused, so no snapshot can start
        # from anything but the committed file.
        result = self.repo.prose("compact", "DECISIONS.md")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("differs from HEAD's; commit the change you were making first", result.stderr)
        self.assertIn(f"first ({compact.STEPS})", result.stderr)

    def test_a_failed_verify_removes_its_record(self):
        self.compaction()
        (self.repo.path / "ref.md").write_text("DECISIONS.md#snapshot-lifetime-policy\n")
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--verify", "--",
                                         "ref.md").returncode, 1)
        self.assertEqual([line for line in self.pending() if "not verified" in line],
                         ["DECISIONS.md was compacted but not verified; run "
                          "`prose compact --verify DECISIONS.md`; or, to drop this compaction, "
                          "`prose compact --abandon DECISIONS.md`"])

    def test_the_reply_must_answer_every_change_and_total_its_findings(self):
        self.repo.prose("compact", "DECISIONS.md")
        self.repo.write("DECISIONS.md", self.AFTER)
        self.repo.prose("compact", "DECISIONS.md", "--review")
        both = "Change 1: holds\nChange 2: superseded\n"
        for reply, error in (("Totals: 0 lost, 0 false\n", "no verdict for changes 1, 2"),
                             ("Change 1: superseded\nTotals: 0 lost, 0 false\n",
                              "no verdict for change 2"),
                             (both, "needs one line 'Totals: 0 lost, 0 false'"),
                             (both + "Change 1: lost: x\nTotals: 0 lost, 0 false\n",
                              "Totals: 1 lost"),
                             (both + "Change 3: holds\nTotals: 0 lost, 0 false\n",
                              "change 3 is not one of"),
                             (both + "Change 1 - lost\nTotals: 0 lost, 0 false\n",
                              "does not allow")):
            with self.subTest(reply=reply):
                result = self.repo.prose("compact", "DECISIONS.md", "--reviewed",
                                         self.write(".reply", reply))
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn(error, result.stderr)

    def test_findings_need_answers_and_a_fix_needs_a_changed_file(self):
        reply = "Change 1: lost: the snapshot policy\nChange 2: superseded\nTotals: 1 lost, 0 false\n"
        self.repo.prose("compact", "DECISIONS.md")
        self.repo.write("DECISIONS.md", self.AFTER)
        self.repo.prose("compact", "DECISIONS.md", "--review")
        reviewed = lambda *extra: self.repo.prose("compact", "DECISIONS.md", "--reviewed",
                                                  self.write(".reply", reply), *extra)
        self.assertIn("pass it with --dispositions", reviewed().stderr)
        fixed = ["--dispositions", self.write(".answers", "Change 1: fixed\n")]
        self.assertIn("is the file the reviewer read", reviewed(*fixed).stderr)
        self.assertIn("not 'Change <n>: fixed'",
                      reviewed("--dispositions", self.write(".answers", "Change 1: kept\n")).stderr)
        kept = reviewed("--dispositions", self.write(".answers", "Change 1: kept: still true\n"))
        self.assertEqual(kept.returncode, 0, kept.stderr)
        self.repo.write("DECISIONS.md", self.AFTER + "\nThe snapshot policy, restored.\n")
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--verify").returncode, 0)
        # The kept call above rewrote .answers; the fix is answered afresh.
        fixed = ["--dispositions", self.write(".answers", "Change 1: fixed\n")]
        self.assertEqual(reviewed(*fixed).returncode, 0)
        self.assertEqual(self.pending(), [])

    def test_a_review_that_did_not_see_the_staged_file_is_refused(self):
        self.repo.prose("compact", "DECISIONS.md")
        # Reviewed before the compaction: no changes to answer.
        self.repo.prose("compact", "DECISIONS.md", "--review")
        self.repo.write("DECISIONS.md", self.AFTER)
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--verify").returncode, 0)
        result = self.repo.prose("compact", "DECISIONS.md", "--reviewed",
                                 self.write(".reply", "Totals: 0 lost, 0 false\n"))
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("not the file the reviewer read", result.stderr)

    def test_an_assume_unchanged_or_skip_worktree_file_is_refused(self):
        for flag in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(flag=flag):
                self.repo.git("update-index", flag, "DECISIONS.md")
                self.addCleanup(self.repo.git, "update-index", flag.replace("--", "--no-"),
                                "DECISIONS.md")
                result = self.repo.prose("compact", "DECISIONS.md")
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("marked", result.stderr)
                self.repo.git("update-index", flag.replace("--", "--no-"), "DECISIONS.md")

    def test_a_verified_compaction_under_an_eol_conversion_signs(self):
        self.repo.write(".gitattributes", "*.md text eol=crlf\n")
        self.repo.commit("eol\n")
        (self.repo.path / "DECISIONS.md").unlink()
        self.repo.git("checkout", "--", "DECISIONS.md")
        self.assertIn(b"\r\n", (self.repo.path / "DECISIONS.md").read_bytes())
        self.assertEqual(self.compaction(self.AFTER.replace("\n", "\r\n")).returncode, 0)
        self.assertEqual(self.pending(), [])

    def test_odd_paths_are_read_by_their_listed_ids(self):
        for name in ("0:DECISIONS.md", "a\nb/DECISIONS.md", "DECISIONS.md\r"):
            with self.subTest(name=repr(name)):
                self.repo.write(name, self.DOC)
                self.repo.commit("odd\n")
                started = self.repo.prose("compact", name)
                self.assertEqual(started.returncode, 4, started.stderr)
                self.repo.write(name, self.AFTER)
                self.assertEqual(len(self.pending()), 2, name)

    def test_a_doc_made_a_symlink_is_not_gated(self):
        self.repo.write("README.md", "hi\n")
        self.repo.commit("readme\n")
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        (self.repo.path / "DECISIONS.md").unlink()
        os.symlink("README.md", self.repo.path / "DECISIONS.md")
        self.repo.git("add", "DECISIONS.md")
        self.assertEqual(self.pending(), [])

    def test_only_a_started_compaction_is_gated(self):
        # A shrink by hand, a merge or a deletion of text that prose compact
        # was never started on is not gated, however much it cut.
        self.repo.write("DECISIONS.md", self.AFTER)
        self.assertEqual(self.pending(), [])
        self.assertEqual(self.sign().returncode, 0)

    def test_any_file_compact_was_started_on_is_gated_whatever_it_changed(self):
        self.repo.write("runbook.txt", self.DOC)
        self.repo.commit("runbook\n")
        self.assertEqual(self.repo.prose("compact", "runbook.txt").returncode, 4)
        self.assertEqual(self.pending(), [])
        # A small edit, far under a tenth, of a file prose does not read as a doc.
        self.repo.write("runbook.txt", self.DOC.replace("\nParagraph 19, at some length.\n", ""))
        self.assertEqual(len(self.pending()), 2, self.pending())
        result = self.repo.prose("compact", "runbook.txt", "--verify")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.repo.prose("compact", "runbook.txt", "--review").returncode, 4)
        done = self.repo.prose("compact", "runbook.txt", "--reviewed",
                               self.write(".reply", "Change 1: holds\nTotals: 0 lost, 0 false\n"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.pending(), [])

    def test_a_snapshot_from_another_work_tree_does_not_gate_this_one(self):
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        directory = self.repo.path / ".git/prose/compact"
        for snapshot in directory.iterdir():
            if not snapshot.suffix and not snapshot.name.startswith("."):
                fields = json.loads(snapshot.read_text())
                fields["root"] = "/elsewhere"
                snapshot.write_text(json.dumps(fields))
        self.repo.write("DECISIONS.md", self.DOC + "x\n")
        self.assertEqual(self.pending(), [])

    def test_a_declaration_makes_any_text_file_current_state_but_not_a_binary(self):
        self.repo.write(".gitattributes",
                        "*.txt prose-compact prose-compact-flagged=1\nblob.txt binary\n")
        self.repo.write("runbook.txt", "a\n")
        self.repo.write("blob.txt", "a\n")
        self.repo.write("nul.txt", "a\n")
        self.repo.commit("attrs\n")
        for name in ("runbook.txt", "blob.txt"):
            self.repo.write(name, "We previously did it.\n")
        self.repo.write("nul.txt", "We previously did it.\0\n")
        first = self.repo.prose("check", "-F", "-", "--goals", "g", stdin="DOCS(x): c\n")
        self.assertIn("compaction due for runbook.txt: read often (declared prose-compact in "
                      ".gitattributes)", first.stdout)
        self.assertNotIn("compaction due for blob.txt", first.stdout)
        self.assertNotIn("compaction due for nul.txt", first.stdout)

    def test_core_ignore_stat_is_named_in_the_refusal(self):
        self.repo.git("config", "core.ignoreStat", "true")
        self.repo.write("DECISIONS.md", self.DOC + "x\n")
        result = self.repo.prose("compact", "DECISIONS.md")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("core.ignoreStat is true", result.stderr)

    def test_an_unreadable_snapshot_refuses(self):
        if os.geteuid() == 0:
            self.skipTest("root reads every file")
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        self.repo.write("DECISIONS.md", self.DOC + "x\n")
        for snapshot in (self.repo.path / ".git/prose/compact").iterdir():
            os.chmod(snapshot, 0)
            self.addCleanup(os.chmod, snapshot, 0o644)
        found = self.pending()
        self.assertEqual(len(found), 1, found)
        self.assertIn("could not tell which staged files were compacted", found[0])

    def test_a_partial_clone_offline_is_not_refused(self):
        source = Repo()
        self.addCleanup(source.cleanup)
        source.write("a/DECISIONS.md", self.DOC)
        source.write("b/other.md", "x\n")
        source.commit("base\n")
        source.git("config", "uploadpack.allowFilter", "true")
        parent = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, parent, True)
        clone = parent / "clone"
        result = run(["git", "clone", "-q", "--filter=blob:none", "--sparse", "--no-local",
                      f"file://{source.path}", str(clone)])
        if result.returncode != 0:
            self.skipTest(f"git cannot make a partial clone here: {result.stderr}")
        run(["git", "sparse-checkout", "set", "a"], cwd=clone)
        shutil.move(str(source.path), str(source.path) + ".gone")
        self.addCleanup(shutil.move, str(source.path) + ".gone", str(source.path))
        (clone / "a/DECISIONS.md").write_text(self.DOC + "x\n")
        run(["git", "add", "a/DECISIONS.md"], cwd=clone)
        self.assertEqual(compact.unverified(str(clone), False, clone / self.PASSES), [])

    def test_a_textconv_driver_does_not_hide_unstaged_changes(self):
        (self.repo.path / ".git/info/attributes").write_text("DECISIONS.md diff=strip\n")
        self.repo.git("config", "diff.strip.textconv", "sh -c 'tr -d \"[:space:]\" < \"$0\"'")
        (self.repo.path / "DECISIONS.md").write_text(self.DOC + "\n\n\n")
        result = self.repo.prose("compact", "DECISIONS.md")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("has changes that are not staged", result.stderr)

    def test_a_snapshot_older_than_seven_days_still_gates(self):
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        month = 30 * 24 * 60 * 60
        for snapshot in (self.repo.path / ".git/prose/compact").iterdir():
            if snapshot.name.startswith("."):
                continue
            fields = json.loads(snapshot.read_text())
            fields["saved"] -= month
            snapshot.write_text(json.dumps(fields))
            os.utime(snapshot, (fields["saved"], fields["saved"]))
        self.repo.write("DECISIONS.md", self.AFTER)
        self.assertEqual(len(self.pending()), 2)
        # Starting a compaction of another file deletes no old snapshot,
        # however old.
        self.repo.write("SKILL.md", "# S\n\n## Another section entirely\n\nA long paragraph.\n")
        self.repo.git("commit", "-q", "-m", "skill", "--", "SKILL.md")
        self.assertEqual(self.repo.prose("compact", "SKILL.md").returncode, 4)
        self.assertEqual(len(self.pending()), 2)
        # The later steps accept the month-old snapshot of DECISIONS.md,
        # and finishing it clears the gate.
        reply = self.write(".reply", self.CLEAN)
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--verify").returncode, 0)
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--review").returncode, 4)
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--reviewed", reply).returncode, 0)
        self.assertEqual(self.pending(), [])

    def test_a_committed_compaction_stops_gating(self):
        # The check after the commit retires the compaction, so a later
        # revert or a switch to a branch without it finds an ordinary file.
        for way in ("revert", "branch"):
            with self.subTest(way=way):
                self.setUp()
                self.repo.git("branch", "-M", "main")
                self.repo.git("checkout", "-q", "-b", "feature")
                self.repo.write("OTHER.md", "x\n")
                self.repo.commit("other\n")
                self.assertEqual(self.compaction().returncode, 0)
                self.repo.git("commit", "-q", "-m", "compact")
                self.assertEqual(self.pending(), [])
                if way == "branch":
                    self.repo.git("checkout", "-q", "main")
                else:
                    self.repo.git("revert", "--no-edit", "HEAD")
                self.repo.write("DECISIONS.md", self.DOC + "\nA new decision.\n")
                self.assertEqual(self.pending(), [])

    def test_a_snapshot_deleted_while_the_gate_lists_them_is_skipped(self):
        # Another file's compaction is abandoned, or retired by another check
        # in this work tree, between the gate's listing and its read.
        self.repo.write("OTHER.md", "# O\n\nSome text here.\n")
        self.repo.commit("other\n")
        self.assertEqual(self.repo.prose("compact", "OTHER.md").returncode, 4)
        real, done = pathlib.Path.read_bytes, []

        def racing(path):
            if not done and path.parent.name == "compact" and not path.name.startswith("."):
                done.append(path)
                path.unlink()
            return real(path)

        pathlib.Path.read_bytes = racing
        self.addCleanup(setattr, pathlib.Path, "read_bytes", real)
        found = self.pending()
        pathlib.Path.read_bytes = real
        self.assertTrue(done)
        self.assertEqual(found, [])

    def test_a_committed_finished_compaction_retires_its_snapshot(self):
        self.assertEqual(self.compaction().returncode, 0)
        snapshots = lambda: [e for e in (self.repo.path / ".git/prose/compact").iterdir()
                             if not e.name.startswith(".")]
        self.assertTrue(snapshots())
        self.repo.git("commit", "-q", "-m", "compact")
        self.assertEqual(self.pending(), [])
        self.assertEqual(snapshots(), [])
        # Reverted, the file is an ordinary one: nothing re-arms the gate.
        self.repo.git("revert", "--no-edit", "HEAD")
        self.repo.write("DECISIONS.md", self.AFTER + "\nAn edit.\n")
        self.assertEqual(self.pending(), [])

    def test_another_compactions_records_do_not_retire_this_one(self):
        # A compaction finished on another branch from the same start must
        # not retire this snapshot when the base comes to hold its result.
        self.repo.git("branch", "-M", "main")
        self.repo.git("checkout", "-q", "-b", "b1")
        self.assertEqual(self.compaction().returncode, 0)
        self.repo.git("commit", "-q", "-m", "compact")
        b1 = self.repo.git("rev-parse", "HEAD").strip()
        self.repo.git("checkout", "-q", "main")
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        self.repo.write("DECISIONS.md", self.AFTER + "\nUnchecked.\n")
        self.assertEqual(len(self.pending()), 2)
        self.repo.git("reset", "-q", "--soft", b1)
        self.assertEqual(len(self.pending()), 2)

    def test_a_stale_load_does_not_drop_another_steps_list(self):
        # A step that loaded the snapshot before another step wrote to it
        # changes only its own list.
        self.repo.prose("compact", "DECISIONS.md")
        state = self.repo.path / ".git/prose/compact"
        here = os.getcwd()
        os.chdir(self.repo.path)
        try:
            where = compact.target("DECISIONS.md")
            stale = compact._load_snapshot(where, "DECISIONS.md", None)
            fresh = compact._load_snapshot(where, "DECISIONS.md", None)
            compact._note_in_snapshot(where, None, fresh, "reviewed", "a" * 40, True)
            compact._note_in_snapshot(where, None, stale, "verified", "a" * 40, True)
            saved = compact._load_snapshot(where, "DECISIONS.md", None)
        finally:
            os.chdir(here)
        self.assertEqual((saved["verified"], saved["reviewed"]), (["a" * 40], ["a" * 40]))
        self.assertTrue(state.exists())

    def test_retirement_leaves_a_snapshot_a_new_step_1_wrote_meanwhile(self):
        # A new step 1 lands between the unlocked read and the lock taken
        # to retire: the new compaction keeps gating.
        self.assertEqual(self.compaction().returncode, 0)
        self.repo.git("commit", "-q", "-m", "compact")
        real, calls = compact._snapshot_lock, []

        def interleaved(directory):
            if not calls:
                calls.append(1)
                self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
            return real(directory)

        compact._snapshot_lock = interleaved
        self.addCleanup(setattr, compact, "_snapshot_lock", real)
        self.pending()
        compact._snapshot_lock = real
        self.repo.write("DECISIONS.md", self.AFTER + "\nUnchecked edit.\n")
        self.assertEqual(len(self.pending()), 2)

    def test_abandon_is_not_undone_by_a_step_writing_at_the_same_time(self):
        # --abandon runs while a step is between reading the snapshot and
        # writing it back; the abandon must win.
        self.repo.prose("compact", "DECISIONS.md")
        self.repo.write("DECISIONS.md", self.AFTER)
        here = os.getcwd()
        os.chdir(self.repo.path)
        self.addCleanup(os.chdir, here)
        where = compact.target("DECISIONS.md")
        loaded = compact._load_snapshot(where, "DECISIONS.md", None)
        real, started = compact._write_snapshot, []

        def interleaved(path, fields):
            started.append(subprocess.Popen(
                [sys.executable, str(SCRIPT), "compact", "DECISIONS.md", "--abandon"],
                cwd=self.repo.path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            time.sleep(1)
            real(path, fields)

        compact._write_snapshot = interleaved
        self.addCleanup(setattr, compact, "_write_snapshot", real)
        compact._note_in_snapshot(where, None, loaded, "verified", "a" * 40, True)
        compact._write_snapshot = real
        self.assertEqual(started[0].wait(timeout=30), 0)
        os.chdir(here)
        self.assertEqual(self.pending(), [])

    def test_a_late_review_of_an_older_compaction_leaves_the_new_one_alone(self):
        self.repo.prose("compact", "DECISIONS.md")
        self.repo.write("DECISIONS.md", self.AFTER)
        here = os.getcwd()
        os.chdir(self.repo.path)
        self.addCleanup(os.chdir, here)
        real = compact.changes

        def late(before, after):
            found = real(before, after)
            # A new compaction starts and is reviewed meanwhile.
            compact.changes = real
            self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--abandon").returncode, 0)
            self.repo.write("DECISIONS.md", self.DOC)
            self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
            self.repo.write("DECISIONS.md", self.AFTER + "\nNewer.\n")
            self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--review").returncode, 4)
            return found

        newer = None
        compact.changes = late
        self.addCleanup(setattr, compact, "changes", real)
        self.repo.write("DECISIONS.md", self.AFTER)
        with self.assertRaisesRegex(ValueError, "changed while --review ran"):
            with contextlib.redirect_stdout(io.StringIO()):
                compact.review("DECISIONS.md", None)
        for review in (self.repo.path / ".git/prose/compact").glob("*.review.md"):
            newer = review.read_text()
        self.assertIn("Newer.", newer)
        self.assertEqual(list((self.repo.path / ".git/prose/compact").glob(".*.review.md.*")), [])

    def test_drafts_left_by_a_killed_step_are_cleared(self):
        # Drafts exist only while the lock is held, so any found under it
        # are deleted, whatever their process id; nothing probes processes.
        self.repo.prose("compact", "DECISIONS.md")
        directory = self.repo.path / ".git/prose/compact"
        key = next(e.name for e in directory.iterdir()
                   if not e.suffix and not e.name.startswith("."))
        drafts = [directory / f".{key}.review.md.{os.getpid()}",
                  directory / f".{key}.{os.getppid()}"]
        for draft in drafts:
            draft.write_text("left\n")
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--abandon").returncode, 0)
        self.assertEqual([d for d in drafts if d.exists()], [])

    def test_review_writes_its_draft_only_under_the_lock(self):
        self.repo.prose("compact", "DECISIONS.md")
        self.repo.write("DECISIONS.md", self.AFTER)
        directory = self.repo.path / ".git/prose/compact"
        here = os.getcwd()
        os.chdir(self.repo.path)
        self.addCleanup(os.chdir, here)
        real, seen = compact._snapshot_lock, []

        @contextlib.contextmanager
        def watched(where):
            seen.append(sorted(e.name for e in where.glob(".*.review.md.*")))
            with real(where):
                yield

        compact._snapshot_lock = watched
        self.addCleanup(setattr, compact, "_snapshot_lock", real)
        with contextlib.redirect_stdout(io.StringIO()):
            compact.review("DECISIONS.md", None)
        compact._snapshot_lock = real
        self.assertTrue(seen)
        self.assertEqual([names for names in seen if names], [])
        self.assertEqual(list(directory.glob(".*.review.md.*")), [])

    def test_verify_fails_when_its_snapshot_was_replaced_meanwhile(self):
        self.repo.prose("compact", "DECISIONS.md")
        self.repo.write("DECISIONS.md", self.AFTER)
        real = compact._note_in_snapshot
        compact._note_in_snapshot = lambda *args: False
        self.addCleanup(setattr, compact, "_note_in_snapshot", real)
        here = os.getcwd()
        os.chdir(self.repo.path)
        self.addCleanup(os.chdir, here)
        with self.assertRaisesRegex(ValueError, "changed while --verify ran"):
            with contextlib.redirect_stdout(io.StringIO()):
                compact.verify("DECISIONS.md", None, prose.pass_dir)

    def test_a_list_of_another_shape_counts_as_empty(self):
        self.repo.prose("compact", "DECISIONS.md")
        for snapshot in (self.repo.path / ".git/prose/compact").iterdir():
            if not snapshot.suffix and not snapshot.name.startswith("."):
                fields = json.loads(snapshot.read_text())
                fields["verified"] = None
                snapshot.write_text(json.dumps(fields))
        self.repo.write("DECISIONS.md", self.AFTER)
        result = self.repo.prose("compact", "DECISIONS.md", "--verify")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_compaction_committed_without_its_records_keeps_gating(self):
        self.repo.prose("compact", "DECISIONS.md")
        self.repo.write("DECISIONS.md", self.AFTER)
        self.repo.git("commit", "-q", "-m", "by hand")
        self.repo.write("DECISIONS.md", self.AFTER + "\nAn edit.\n")
        found = self.pending()
        self.assertEqual(len(found), 2, found)
        self.assertIn("--abandon", found[0])
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--abandon").returncode, 0)
        self.assertEqual(self.pending(), [])

    def test_a_commit_of_other_files_keeps_the_compaction_gated(self):
        self.repo.prose("compact", "DECISIONS.md")
        self.repo.write("OTHER.md", "x\n")
        self.repo.git("commit", "-q", "-m", "other", "--", "OTHER.md")
        self.repo.write("DECISIONS.md", self.AFTER)
        self.assertEqual(len(self.pending()), 2)

    def test_amending_a_committed_compaction_with_new_edits_is_gated(self):
        self.assertEqual(self.compaction().returncode, 0)
        self.repo.git("commit", "-q", "-m", "compact")
        self.repo.write("DECISIONS.md", self.AFTER + "\nUnreviewed edit.\n")
        here = os.getcwd()
        os.chdir(self.repo.path)
        try:
            found = compact.unverified(str(self.repo.path), True, self.repo.path / self.PASSES)
        finally:
            os.chdir(here)
        self.assertEqual(len(found), 2, found)

    def test_a_new_compaction_after_one_landed_elsewhere_is_gated(self):
        self.repo.git("branch", "-M", "main")
        self.repo.git("checkout", "-q", "-b", "feature")
        self.assertEqual(self.compaction().returncode, 0)
        self.repo.git("commit", "-q", "-m", "compact")
        self.repo.git("checkout", "-q", "main")
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        self.repo.write("DECISIONS.md", self.AFTER + "\nA different result.\n")
        self.assertEqual(len(self.pending()), 2)

    def test_a_stashed_finished_compaction_edited_again_is_gated(self):
        self.assertEqual(self.compaction().returncode, 0)
        self.repo.git("stash", "-q")
        self.repo.git("stash", "apply", "-q", "--index")
        self.repo.write("DECISIONS.md", self.AFTER + "\nEdited after the review.\n")
        self.assertEqual(len(self.pending()), 2)

    def test_abandon_clears_the_block(self):
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        self.repo.write("DECISIONS.md", self.AFTER)
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--verify").returncode, 0)
        found = self.pending()
        self.assertEqual(len(found), 1, found)
        self.assertIn("`prose compact --abandon DECISIONS.md`", found[0])
        result = self.repo.prose("compact", "DECISIONS.md", "--abandon")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Abandoned the compaction of DECISIONS.md: removed its snapshot and "
                      "1 record.", result.stdout)
        self.assertEqual(self.pending(), [])
        self.assertEqual(list((self.repo.path / self.PASSES / "compacted").iterdir()), [])
        self.assertEqual(self.sign().returncode, 0)

    def test_abandon_with_nothing_started_is_refused(self):
        result = self.repo.prose("compact", "DECISIONS.md", "--abandon")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("DECISIONS.md: no compaction was started on it, so there is nothing to "
                      "abandon", result.stderr)

    def test_abandon_leaves_other_files_compactions_alone(self):
        skill = "# S\n\n## Another section entirely\n\nA long paragraph.\n\n## Stays\n\nC.\n"
        self.repo.write("SKILL.md", skill)
        self.repo.commit("skill\n")
        for name, after in (("DECISIONS.md", self.AFTER), ("SKILL.md", "# S\n\n## Stays\n\nC.\n")):
            self.assertEqual(self.repo.prose("compact", name).returncode, 4)
            self.repo.write(name, after)
            verified = self.repo.prose("compact", name, "--verify")
            self.assertEqual(verified.returncode, 0, verified.stdout)
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--abandon").returncode, 0)
        found = self.pending()
        self.assertEqual(len(found), 1, found)
        self.assertTrue(found[0].startswith("SKILL.md was compacted but its review"), found)
        self.assertEqual(len(list((self.repo.path / self.PASSES / "compacted").iterdir())), 1)

    def test_abandon_keeps_records_another_compaction_still_needs(self):
        # Two files with the same content compacted alike share their
        # records, by blob id; abandoning one must not undo the other.
        doc = "# S\n\n## Stays\n\nA long paragraph that goes.\n\nC.\n"
        after = "# S\n\n## Stays\n\nC.\n"
        self.repo.write("A.md", doc)
        self.repo.write("B.md", doc)
        self.repo.commit("twins\n")
        reply = self.write(".reply", "Change 1: superseded\nTotals: 0 lost, 0 false\n")
        for name in ("B.md", "A.md"):
            self.assertEqual(self.repo.prose("compact", name).returncode, 4)
            self.repo.write(name, after)
            self.assertEqual(self.repo.prose("compact", name, "--verify").returncode, 0)
            self.assertEqual(self.repo.prose("compact", name, "--review").returncode, 4)
            self.assertEqual(self.repo.prose("compact", name, "--reviewed", reply).returncode, 0)
        self.assertEqual(self.pending(), [])
        self.assertEqual(self.repo.prose("compact", "A.md", "--abandon").returncode, 0)
        self.assertEqual(self.pending(), [])

    def test_abandon_leaves_another_work_trees_compaction_of_the_same_file(self):
        other = pathlib.Path(tempfile.mkdtemp()) / "wt"
        self.addCleanup(shutil.rmtree, other.parent, True)
        self.repo.git("worktree", "add", "-q", "-b", "other", str(other))
        reply = self.write(".reply", "Change 1: superseded\nChange 2: superseded\n"
                                     "Totals: 0 lost, 0 false\n")
        for where, after in ((other, self.AFTER + "\nOther.\n"), (self.repo.path, self.AFTER)):
            prose = lambda *args: run([sys.executable, str(SCRIPT), *args], cwd=where)
            self.assertEqual(prose("compact", "DECISIONS.md").returncode, 4)
            (where / "DECISIONS.md").write_text(after)
            run(["git", "add", "DECISIONS.md"], cwd=where)
            self.assertEqual(prose("compact", "DECISIONS.md", "--verify").returncode, 0)
            self.assertEqual(prose("compact", "DECISIONS.md", "--review").returncode, 4)
            done = prose("compact", "DECISIONS.md", "--reviewed", reply)
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--abandon").returncode, 0)
        self.assertEqual(compact.unverified(str(other), False, self.repo.path / self.PASSES), [])

    def test_abandon_works_on_a_file_deleted_from_the_work_tree(self):
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        self.repo.write("DECISIONS.md", self.AFTER)
        (self.repo.path / "DECISIONS.md").unlink()
        self.assertEqual(len(self.pending()), 2)
        result = self.repo.prose("compact", "DECISIONS.md", "--abandon")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.pending(), [])

    def test_abandon_works_when_the_files_directory_is_gone_too(self):
        self.repo.write("docs/sub/D.md", self.DOC)
        self.repo.commit("doc\n")
        self.assertEqual(self.repo.prose("compact", "docs/sub/D.md").returncode, 4)
        self.repo.write("docs/sub/D.md", self.AFTER)
        shutil.rmtree(self.repo.path / "docs")
        result = self.repo.prose("compact", "docs/sub/D.md", "--abandon")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.pending(), [])

    def test_a_snapshot_of_an_odd_shape_keeps_every_record(self):
        self.repo.write("SKILL.md", "# S\n\n## Another section entirely\n\nA long paragraph.\n")
        self.repo.commit("skill\n")
        self.assertEqual(self.repo.prose("compact", "SKILL.md").returncode, 4)
        for snapshot in (self.repo.path / ".git/prose/compact").iterdir():
            if not snapshot.suffix and not snapshot.name.startswith("."):
                fields = json.loads(snapshot.read_text())
                fields["before"] = [fields["before"]]
                snapshot.write_text(json.dumps(fields))
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        self.repo.write("DECISIONS.md", self.AFTER)
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--verify").returncode, 0)
        result = self.repo.prose("compact", "DECISIONS.md", "--abandon")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("record", result.stdout)
        self.assertEqual(self.pending(), [])

    def test_the_unmerged_refusal_names_abandon_too(self):
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        # A conflict, made in the index: stages 1 to 3 for the file.
        base = self.repo.git("rev-parse", "HEAD:DECISIONS.md").strip()
        other = self.repo.git("hash-object", "-w", "--stdin", stdin=self.AFTER).strip()
        self.repo.git("rm", "-q", "--cached", "DECISIONS.md")
        self.repo.git("update-index", "--index-info",
                      stdin="".join(f"100644 {oid} {stage}\tDECISIONS.md\n"
                                    for oid, stage in ((base, 1), (other, 2), (base, 3))))
        found = self.pending()
        self.assertEqual(len(found), 1, found)
        self.assertIn("is unmerged", found[0])
        self.assertIn("`prose compact --abandon DECISIONS.md`", found[0])

    def test_abandon_then_start_again(self):
        self.repo.prose("compact", "DECISIONS.md")
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--abandon").returncode, 0)
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md", "--abandon").returncode, 2)
        self.assertEqual(self.compaction().returncode, 0)
        self.assertEqual(self.pending(), [])

    def test_a_rename_with_a_shrink_is_not_gated(self):
        # The known gap DECISIONS.md records: the new path has no base.
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        (self.repo.path / "docs").mkdir()
        self.repo.git("mv", "DECISIONS.md", "docs/DECISIONS.md")
        self.repo.write("docs/DECISIONS.md", self.AFTER)
        self.assertEqual(self.pending(), [])


class BriefFiles(unittest.TestCase):
    """Each brief prose prints for a subagent is also saved to a file, whose
    path it prints, so the agent hands over the path instead of retyping
    the text."""

    DOC = CompactionGate.DOC
    AFTER = CompactionGate.AFTER.replace("B.", "B, now clearer.")

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("DECISIONS.md", self.DOC)
        self.repo.commit("base\n")

    def saved(self, output, marker):
        """Check that output holds the brief between marker's lines and a
        `Brief file:` line naming a file with the same text; return its path.
        A cold-read brief's file goes on after the printed text, with the
        lines its items need (ColdReadBriefFiles)."""
        found = re.search(rf"^=== {marker} ===\n(.*?)\n=== end {marker} ===$", output,
                          re.M | re.S)
        self.assertIsNotNone(found, output)
        path = re.search(r"^Brief file: (.+)$", output, re.M)
        self.assertIsNotNone(path, output)
        path = pathlib.Path(path.group(1))
        printed = found.group(1)
        if printed.endswith("\n\n" + prose.BRIEF_FILES_NOTE):
            printed = printed[:-len("\n\n" + prose.BRIEF_FILES_NOTE)]
            self.assertTrue(path.read_text(encoding="utf-8").startswith(printed + "\n"))
        else:
            self.assertEqual(path.read_text(encoding="utf-8"), printed + "\n")
        git_dir = (self.repo.path / ".git").resolve()
        self.assertEqual(path.parent, git_dir / "prose" / "briefs")
        return path

    def test_the_compaction_and_review_briefs_are_saved(self):
        first = self.repo.prose("compact", "DECISIONS.md")
        self.assertEqual(first.returncode, 4, first.stderr)
        self.saved(first.stdout, "compaction brief")
        self.repo.write("DECISIONS.md", self.AFTER)
        review = self.repo.prose("compact", "DECISIONS.md", "--review")
        self.assertEqual(review.returncode, 4, review.stderr)
        self.saved(review.stdout, "compaction review brief")

    def test_the_cold_read_brief_of_a_commit_is_saved(self):
        self.repo.write("DECISIONS.md", self.AFTER)
        (self.repo.path / ".msg").write_text("DOCS(x): edit\n")
        first = self.repo.prose("check", "-F", ".msg", "--goals", "review it")
        token = pass_token(first.stdout)
        needed = self.repo.prose("check", "-F", ".msg", "--goals", "review it", "--pass", token)
        self.assertEqual(needed.returncode, prose.COLD_READ_NEEDED, needed.stderr)
        self.assertIn(token, self.saved(needed.stdout, "cold-read brief").read_text())

    def test_the_cold_read_brief_of_a_post_is_saved(self):
        sign = lambda *args, stdin: run([sys.executable, str(SCRIPT), "sign"] + list(args),
                                        cwd=self.repo.path, stdin=stdin)
        token = pass_token(sign("--goals", "approve it", stdin="").stderr)
        needed = sign("--pass", token, stdin="The fix lands.\n")
        self.assertEqual(needed.returncode, prose.COLD_READ_NEEDED, needed.stderr)
        self.assertEqual(needed.stdout, "")
        self.assertIn("The fix lands.", self.saved(needed.stderr, "cold-read brief").read_text())

    def test_old_briefs_are_deleted_as_old_tokens_are(self):
        briefs = (self.repo.path / ".git" / "prose" / "briefs")
        briefs.mkdir(parents=True)
        old, recent = briefs / "old.md", briefs / "recent.md"
        for path in (old, recent):
            path.write_text("x")
        past = time.time() - compact.BRIEF_LIFETIME - 60
        os.utime(old, (past, past))
        self.assertEqual(self.repo.prose("compact", "DECISIONS.md").returncode, 4)
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)


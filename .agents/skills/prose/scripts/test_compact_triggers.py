#!/usr/bin/env python3
"""Tests for compact.py's triggers: which docs are due for compaction, the
bloat detectors, and the doc reads each kind of commit implies, which count
toward how often a doc is read. prose.py's first call reports the docs
that are due.

Standard library only:

    python3 test_compact_triggers.py
"""

import contextlib
import io
import os
import pathlib
import re
import shutil
import tempfile
import time
import unittest

from prose_test_support import (
    ALL_FILES,
    REPEAT,
    Repo,
    answers_file,
    compact,
    mock_attr,
    paragraphs,
    prose,
    repeated,
    run,
)


class HistoryMarkers(unittest.TestCase):
    """The history-marker trigger, which makes a current-state doc due at any size."""

    def names(self, text):
        return [marker.name for marker in compact.history_markers(text)]

    def test_it_finds_revision_notes_and_narrative(self):
        for text in ("**Revised 2026-09-30.** The goals open the call.",
                     "(Revised 2026-09-26: the skip value is dropped.)",
                     "### Superseded 2026-09-30: the gate that looked for prose",
                     "That was dropped on 2026-09-28 in favour of a line.",
                     "Checking by the quote was replaced on 2026-10-13.",
                     "History: from 2026-09-26 the engine signed lines.",
                     "**Update:** the hook now blocks.",
                     "It previously read every comment.",
                     "The gate was originally a comment scan.",
                     "The limit was changed to 30 seconds."):
            with self.subTest(text=text):
                self.assertEqual(len(self.names(text)), 1)

    def test_it_leaves_attribution_measurements_and_quoted_markers(self):
        for text in ("**Decision (Adam, 2026-10-24).** Compaction lives in prose.",
                     "Measured 2026-09-27 against one seat.",
                     "It refuses a previously issued token.",
                     "No `previously` or \"revised\" in a current doc, and no «superseded».",
                     "```\nRevised 2026-09-30: an example inside a fence.\n```",
                     "## Update the config",
                     "Dropping one is a decision, not an\nedit: the compactor names it.",
                     "The commit is refused if the tree no longer matches.",
                     "**Rejected: a length budget per kind.** It reads as a target."):
            with self.subTest(text=text):
                self.assertEqual(self.names(text), [])

    def test_a_quotation_wrapped_onto_the_next_line_is_still_quoted(self):
        text = 'Markers: "History:", "a previously\nissued", "originally".\nIt previously ran.\n'
        self.assertEqual([(m.line, m.name) for m in compact.history_markers(text)],
                         [(3, "previously")])

    def test_it_reports_one_marker_per_line_with_its_line_number(self):
        found = compact.history_markers("# T\n\nIt previously was, originally.\nFine.\n")
        self.assertEqual([(m.line, m.name) for m in found], [(3, "previously")])


class CurrentStateDocs(unittest.TestCase):
    """Which docs the triggers measure when no attribute says."""

    def test_the_defaults(self):
        for path, expected in (("DECISIONS.md", True),
                               (".agents/skills/prose/SKILL.md", True),
                               ("AGENTS.md", True), ("sub/CLAUDE.md", True),
                               ("docs/architecture.md", True), ("ARCHITECTURE.md", True),
                               ("openspec/specs/seat/spec.md", True),
                               ("openspec/changes/fix-x/proposal.md", True),
                               ("openspec/changes/fix-x/design.md", True),
                               ("openspec/changes/fix-x/specs/seat/spec.md", True),
                               ("openspec/changes/archive/2026-10-01-x/design.md", False),
                               ("openspec/changes/archive/2026-10-01-x/specs/seat/spec.md",
                                False),
                               ("openspec/changes/fix-x/specs/seat/notes.md", False),
                               ("openspec/changes/fix-x/tasks.md", False),
                               ("README.md", False), ("CHANGELOG.md", False),
                               ("docs/guide.md", False)):
            with self.subTest(path=path):
                self.assertEqual(compact.default_current(path), expected)

    def test_gitattributes_declare_exempt_and_set_numbers(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write(".gitattributes", "* prose-compact-flagged=500\n"
                                     "docs/runbook.md prose-compact prose-compact-growth=20 "
                                     "prose-compact-reads=3\n"
                                     "DECISIONS.md -prose-compact\n"
                                     "**/DECISIONS.md prose-compact-attribution=drop\n")
        found = compact.settings(["docs/runbook.md", "DECISIONS.md", "SKILL.md", "README.md",
                                  "a/DECISIONS.md"], str(repo.path))
        self.assertEqual(found["docs/runbook.md"],
                         compact.Settings(True, 20, False, True, 500, 3, False, False))
        repo.write(".gitattributes", "SKILL.md prose-compact-growth-bytes=750\n")
        self.assertEqual(compact.settings(["SKILL.md", "a.md"], str(repo.path))["SKILL.md"]
                         .growth_bytes, 750)
        self.assertEqual(compact.settings(["a.md"], str(repo.path))["a.md"].growth_bytes,
                         compact.DEFAULT_GROWTH_BYTES)
        self.assertEqual(found["DECISIONS.md"].current, False)
        self.assertEqual(found["DECISIONS.md"].exempt, True)
        self.assertEqual(found["DECISIONS.md"].drop_attribution, True)
        self.assertEqual(found["a/DECISIONS.md"].drop_attribution, True)
        self.assertEqual(found["SKILL.md"],
                         compact.Settings(True, compact.DEFAULT_GROWTH, flagged=500))
        self.assertEqual(found["README.md"].current, False)

    def test_the_budget_setting_is_gone(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write(".gitattributes", "* prose-compact-budget=500\n")
        self.assertFalse(hasattr(compact, "DEFAULT_BUDGET"))
        self.assertEqual(compact.settings(["SKILL.md"], str(repo.path))["SKILL.md"],
                         compact.Settings(True, compact.DEFAULT_GROWTH))

    def test_outside_a_repository_every_path_gets_the_defaults(self):
        found = compact.settings(["SKILL.md"], None)
        self.assertEqual(found["SKILL.md"], compact.Settings(True, compact.DEFAULT_GROWTH))
        self.assertEqual((found["SKILL.md"].flagged, found["SKILL.md"].reads),
                         (compact.DEFAULT_FLAGGED, compact.DEFAULT_READS))


class CompactionDue(unittest.TestCase):
    """The triggers, as `prose check`'s first call prints them: a doc read
    often is due when its flagged text passes the threshold, or when it has
    grown by both the growth share and the growth bytes since its last
    compaction."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write(".gitattributes", "* prose-compact-flagged=50\n")
        self.repo.write("a.py", "x = 1\n")
        self.repo.commit("base\n")

    def check(self):
        return self.repo.prose("check", "-F", "-", "--goals", "review it", stdin="T\n")

    def test_a_read_often_doc_with_flagged_text_is_due(self):
        self.repo.write("skills/a/SKILL.md", repeated())
        result = self.check()
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertRegex(result.stdout, r"compaction due for skills/a/SKILL\.md: read often \(every "
                                        r"SKILL\.md is read before work\); 64 bytes \([0-9]+%\) in 1 "
                                        r"flagged passage \(1 repetition\); due at 10% of the "
                                        r"file and 50 bytes more than at its last compaction")

    def test_flagged_text_under_the_threshold_is_not_due(self):
        self.repo.write(".gitattributes", "* prose-compact-flagged=65\n")
        self.repo.write("skills/a/SKILL.md", repeated())
        self.assertNotIn("compaction due", self.check().stdout)

    def test_a_doc_not_read_often_is_not_due_whatever_it_holds(self):
        self.repo.write("DECISIONS.md", repeated(5, "**Revised 2026-09-30.** It holds.\n\n"))
        self.repo.write("README.md", repeated(5))
        self.assertNotIn("compaction due", self.check().stdout)

    def test_a_file_a_skill_links_to_be_read_first_is_read_often(self):
        self.repo.write("skills/a/SKILL.md", "# A\n\n- [The rules](rules.md). Read them first.\n"
                                             "- [Why](DECISIONS.md). Read it before changing this "
                                             "file.\n")
        self.repo.commit("skill\n")
        self.repo.write("skills/a/rules.md", repeated())
        self.repo.write("skills/a/DECISIONS.md", repeated())
        out = self.check().stdout
        self.assertIn("compaction due for skills/a/rules.md: read often (skills/a/SKILL.md links "
                      "it to be read first)", out)
        # Read before changing the skill is a read only when the skill changes.
        self.assertNotIn("compaction due for skills/a/DECISIONS.md", out)

    def test_an_open_changes_proposal_is_read_often(self):
        self.repo.write("openspec/changes/x/proposal.md", repeated())
        self.repo.write("openspec/changes/archive/2026-01-01-y/proposal.md", repeated())
        out = self.check().stdout
        self.assertIn("compaction due for openspec/changes/x/proposal.md: read often (an open "
                      "OpenSpec change's proposal)", out)
        self.assertNotIn("compaction due for openspec/changes/archive", out)

    def test_an_open_changes_delta_spec_is_read_often(self):
        # A consistency read opens every open change's delta specs, as it
        # does its proposal and design.
        self.repo.write("openspec/changes/x/specs/seat/spec.md", repeated())
        self.repo.write("openspec/changes/archive/2026-01-01-y/specs/seat/spec.md", repeated())
        out = self.check().stdout
        self.assertIn("compaction due for openspec/changes/x/specs/seat/spec.md: read often (an "
                      "open OpenSpec change's delta spec)", out)
        self.assertNotIn("compaction due for openspec/changes/archive", out)

    def test_a_main_spec_is_read_often_once_commits_imply_enough_reads(self):
        self.repo.write(".gitattributes", "* prose-compact-flagged=50 prose-compact-reads=3\n")
        self.repo.write("openspec/specs/x/spec.md", "# X\n")
        self.repo.commit("spec\n\nSpec-check: ✓ 1\n")
        self.repo.write("a.py", "x = 2\n")
        self.repo.commit("code\n\nSpec-check: ✓ 2\n")
        self.repo.write("openspec/specs/x/spec.md", repeated())
        self.assertNotIn("compaction due", self.check().stdout)
        self.repo.git("checkout", "HEAD", "--", "openspec/specs/x/spec.md")
        self.repo.write("a.py", "x = 3\n")
        self.repo.commit("more\n\nSpec-check: ✓ 3\n")
        self.repo.write("openspec/specs/x/spec.md", repeated())
        self.assertIn("compaction due for openspec/specs/x/spec.md: read often (3 reads implied by "
                      "commits since it was added; 3 make it read often)", self.check().stdout)

    def test_a_doc_never_compacted_is_not_due_by_growth(self):
        # The removed prose-compact-budget attribute is ignored.
        self.repo.write(".gitattributes", "* prose-compact-flagged=50 prose-compact-budget=1000\n")
        self.repo.write("SKILL.md", paragraphs(5))
        self.repo.commit("add\n")
        self.repo.write("SKILL.md", paragraphs(30))
        self.assertNotIn("compaction due", self.check().stdout)

    def test_after_a_compaction_growth_past_the_share_makes_it_due(self):
        self.repo.write(".gitattributes", "* prose-compact-flagged=50 prose-compact-growth-bytes=100\n")
        self.repo.write("SKILL.md", paragraphs(40))
        self.repo.commit("grow\n")
        self.repo.write("SKILL.md", paragraphs(30))
        self.repo.commit("compact\n")
        self.repo.write("SKILL.md", paragraphs(40))
        self.assertNotIn("compaction due", self.check().stdout)
        self.repo.write("SKILL.md", paragraphs(46))
        self.assertRegex(self.check().stdout, r"compaction due for SKILL\.md: read often .*; "
                                              r"[0-9,]+ bytes, grown [0-9]+% \([0-9,]+ bytes\) "
                                              r"since its last compaction \([0-9a-f]{12}, [0-9,]+ "
                                              r"bytes\); 50% and 100 bytes are allowed")

    def test_growth_under_the_byte_floor_is_not_due(self):
        self.repo.write("SKILL.md", paragraphs(40))
        self.repo.commit("grow\n")
        self.repo.write("SKILL.md", paragraphs(30))
        self.repo.commit("compact\n")
        # Grown by more than half, but by under 2,000 bytes.
        self.repo.write("SKILL.md", paragraphs(46))
        self.assertNotIn("compaction due", self.check().stdout)
        self.repo.write("SKILL.md", paragraphs(30 + 2000 // 40))
        self.assertIn("2,000 bytes are allowed", self.check().stdout)

    def test_passages_its_last_compaction_kept_do_not_make_it_due_again(self):
        self.repo.write("SKILL.md", repeated(3) + paragraphs(20))
        self.repo.commit("grow\n")
        self.repo.write("SKILL.md", repeated(3))
        self.repo.commit("compact, keeping two repetitions\n")
        self.repo.write("SKILL.md", repeated(3) + "One more line.\n")
        self.assertNotIn("compaction due", self.check().stdout)
        self.repo.write("SKILL.md", repeated(4) + "One more line.\n")
        out = self.check().stdout
        self.assertIn("compaction due for SKILL.md: read often (every SKILL.md is read before "
                      "work); 192 bytes", out)
        self.assertIn("128 of them at its last compaction", out)
        # The advice names the file holding the steps, and that file exists.
        self.assertIn(f"following {compact.STEPS}):", out)
        self.assertTrue(compact.STEPS.is_file(), compact.STEPS)

    def test_a_compaction_that_kept_its_flags_and_cut_little_is_not_due_again(self):
        notes = "".join(f"Note that rule {n} holds for every commit here.\n\n" for n in range(25))
        plain = "".join(f"Plain line {n} states a fact.\n" for n in range(150))
        self.repo.write(".gitattributes", "* prose-compact-flagged=1000\n")
        self.repo.write("SKILL.md", notes + plain)
        self.repo.commit("add\n")
        brief = self.repo.prose("compact", "SKILL.md")
        self.assertEqual(brief.returncode, 4, brief.stderr)
        self.repo.write("SKILL.md", notes + plain[:len(plain) * 9 // 10])
        answers_file(brief.stdout).write_text(
            "".join(f"Passage {n}: kept: a false flag\n" for n in range(1, 26)))
        verified = self.repo.prose("compact", "SKILL.md", "--verify")
        self.assertEqual(verified.returncode, 0, verified.stdout)
        review = self.repo.prose("compact", "SKILL.md", "--review")
        kept = len(re.findall(r"^### Passage ", pathlib.Path(re.search(
            r"^The changes: (.*)$", review.stdout, re.M).group(1)).read_text(), re.M))
        reply = "".join(f"Change {n}: superseded\n" for n in range(1, 2)) + "".join(
            f"Passage {n}: justified\n" for n in range(1, kept + 1)) + "Totals: 0 lost, 0 false\n"
        (self.repo.path / ".reply").write_text(reply)
        done = self.repo.prose("compact", "SKILL.md", "--reviewed", str(self.repo.path / ".reply"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.repo.commit("compact, keeping every flagged passage\n")
        self.repo.write("SKILL.md", notes + plain[:len(plain) * 9 // 10] + "One more line.\n")
        self.assertNotIn("compaction due", self.check().stdout)

    def test_a_doc_never_compacted_counts_all_its_flagged_text(self):
        # Flagged text it held from the start counts: no compaction kept it.
        self.repo.write("SKILL.md", repeated(2))
        self.repo.commit("add, with one repetition\n")
        self.repo.write("SKILL.md", repeated(2) + "One more line.\n")
        self.assertIn("compaction due for SKILL.md", self.check().stdout)

    def test_a_doc_deleted_and_added_again_is_not_due_by_the_old_ones_growth(self):
        self.repo.write("SKILL.md", paragraphs(100))
        self.repo.commit("add\n")
        self.repo.write("SKILL.md", paragraphs(10))
        self.repo.commit("shrink\n")
        self.repo.git("rm", "-q", "SKILL.md")
        self.repo.commit("remove\n")
        self.repo.write("SKILL.md", paragraphs(150))
        self.repo.commit("add again\n")
        self.repo.write("SKILL.md", paragraphs(151))
        self.assertNotIn("grown", self.check().stdout)

    def test_a_doc_deleted_in_head_and_added_again_is_not_due_by_growth(self):
        self.repo.write("SKILL.md", paragraphs(100))
        self.repo.commit("add\n")
        self.repo.write("SKILL.md", paragraphs(30))
        self.repo.commit("shrink\n")
        self.repo.git("rm", "-q", "SKILL.md")
        self.repo.commit("remove\n")
        self.repo.write("SKILL.md", paragraphs(100))
        self.assertNotIn("grown", self.check().stdout)

    def test_a_compaction_with_an_earlier_commit_date_than_the_add_is_found(self):
        root = str(self.repo.path)

        def commit_at(message, when):
            env = dict(os.environ, GIT_COMMITTER_DATE=when, GIT_AUTHOR_DATE=when)
            result = run(["git", "commit", "-q", "-m", message], cwd=root, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)

        self.repo.write("SKILL.md", paragraphs(90))
        commit_at("add", "2026-10-01T12:00:00")
        self.repo.git("checkout", "-q", "-b", "side")
        self.repo.write("SKILL.md", paragraphs(60))
        commit_at("compact", "2026-10-01T11:55:00")
        self.repo.git("checkout", "-q", "-")
        self.repo.write("SKILL.md", paragraphs(90).replace("# Doc", "# The doc", 1))
        commit_at("edit the title", "2026-10-01T12:10:00")
        env = dict(os.environ, GIT_COMMITTER_DATE="2026-10-01T12:11:00",
                   GIT_AUTHOR_DATE="2026-10-01T12:11:00")
        run(["git", "merge", "-q", "--no-ff", "side", "-m", "merge"], cwd=root, env=env)
        self.assertIsNotNone(compact.size_history("SKILL.md", root).last)

    def test_a_change_that_compacts_the_doc_is_not_due(self):
        self.repo.write("SKILL.md", repeated(9))
        self.repo.commit("grow\n")
        self.repo.write("SKILL.md", repeated(7))
        self.assertNotIn("compaction due", self.check().stdout)

    def test_an_exempt_doc_is_never_due_and_a_declared_one_is_read_often(self):
        self.repo.write(".gitattributes", "* prose-compact-flagged=50\nSKILL.md -prose-compact\n"
                                          "notes.md prose-compact\n")
        self.repo.write("SKILL.md", repeated())
        self.repo.write("notes.md", repeated())
        out = self.check().stdout
        self.assertNotIn("compaction due for SKILL.md", out)
        self.assertIn("compaction due for notes.md: read often (declared prose-compact in "
                      ".gitattributes)", out)

    def test_growth_and_flagged_settings_apply_per_file(self):
        self.repo.write(".gitattributes", "* prose-compact-flagged=50\n"
                                          "SKILL.md prose-compact-growth=10 "
                                          "prose-compact-flagged=100000 "
                                          "prose-compact-growth-bytes=10\n")
        self.repo.write("SKILL.md", paragraphs(40))
        self.repo.commit("grow\n")
        self.repo.write("SKILL.md", paragraphs(30))
        self.repo.commit("compact\n")
        self.repo.write("SKILL.md", paragraphs(34) + REPEAT + REPEAT)
        self.assertIn("10% and 10 bytes are allowed", self.check().stdout)

    def test_a_large_doc_under_the_flagged_share_is_not_due(self):
        # 64 flagged bytes, past the 50-byte floor, in about 5,000 bytes.
        self.repo.write("SKILL.md", repeated(2, paragraphs(90)))
        self.assertNotIn("compaction due", self.check().stdout)
        self.repo.write(".gitattributes", "* prose-compact-flagged=50 "
                                          "prose-compact-flagged-share=1\n")
        self.assertIn("compaction due for SKILL.md: read often (every SKILL.md is read before "
                      "work); 64 bytes (1%) in 1 flagged passage (1 repetition); due at 1% of "
                      "the file and 50 bytes", self.check().stdout)

    def test_the_defaults_need_a_tenth_of_the_file_and_1000_bytes(self):
        self.repo.write(".gitattributes", "")
        # 17 repetitions, 1,088 bytes, about 60% of the file.
        self.repo.write("SKILL.md", repeated(18))
        self.assertIn("compaction due for SKILL.md", self.check().stdout)
        # A small doc: a high share, but under the 1,000-byte floor.
        self.repo.write("SKILL.md", repeated(10))
        self.assertNotIn("compaction due", self.check().stdout)

    def test_after_a_compaction_the_flagged_text_added_is_measured_against_the_file(self):
        self.repo.write("SKILL.md", repeated(12, paragraphs(40)))
        self.repo.commit("grow\n")
        # The compaction keeps 11 repetitions, 704 bytes, over 40% of it.
        self.repo.write("SKILL.md", repeated(12, paragraphs(10)))
        self.repo.commit("compact, keeping the repetitions\n")
        # 64 bytes added: past setUp's 50-byte floor, under a tenth of the file.
        self.repo.write("SKILL.md", repeated(13, paragraphs(10)))
        self.assertNotIn("compaction due", self.check().stdout)
        # 320 bytes added, over a tenth.
        self.repo.write("SKILL.md", repeated(17, paragraphs(10)))
        self.assertRegex(self.check().stdout, r"compaction due for SKILL\.md: .*, 704 of them at "
                                              r"its last compaction; 320 bytes \(1[0-9]%\) added "
                                              r"since; due at 10% of the file")

    def test_the_flagged_share_setting_is_read(self):
        self.repo.write(".gitattributes", "SKILL.md prose-compact-flagged-share=25\n")
        found = compact.settings(["SKILL.md", "a.md"], str(self.repo.path))
        self.assertEqual(found["SKILL.md"].flagged_share, 25)
        self.assertEqual(found["a.md"].flagged_share, compact.DEFAULT_FLAGGED_SHARE)

    def test_a_deleted_doc_is_not_due(self):
        self.repo.write("SKILL.md", repeated(5))
        self.repo.commit("add\n")
        self.repo.git("rm", "-q", "SKILL.md")
        self.assertNotIn("compaction due", self.check().stdout)


class ImpliedReads(unittest.TestCase):
    """The declared map from commits to the reads they imply."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("skills/a/SKILL.md", "# A\n\n[Ref](ref.md): read it first.\n")
        self.repo.write("skills/a/ref.md", "# Ref\n")
        self.repo.write("skills/a/DECISIONS.md", "# D\n")
        self.repo.write("skills/bug-hunter/SKILL.md", "# B\n")
        self.repo.write("openspec/specs/x/spec.md", "# X\n")
        self.repo.write("openspec/changes/y/proposal.md", "# Y\n")
        self.repo.write("README.md", "r\n")
        self.repo.commit("base\n")

    def reads(self, stops):
        root = str(self.repo.path)
        index = compact.index_entries(root)
        return compact.implied_reads(root, index, compact.read_first_links(root, index), stops)

    def change(self, name, message):
        self.repo.write(name, (self.repo.path / name).read_text() + "x\n")
        self.repo.commit(message)
        return self.repo.git("rev-parse", "HEAD").strip()

    def test_each_kind_of_commit_implies_its_reads(self):
        docs = ["skills/a/SKILL.md", "skills/a/ref.md", "skills/a/DECISIONS.md",
                "skills/bug-hunter/SKILL.md", "openspec/specs/x/spec.md",
                "openspec/changes/y/proposal.md"]
        before = self.reads(dict.fromkeys(docs))
        self.change("skills/a/DECISIONS.md", "touch a\n")
        self.change("README.md", "readme\n\nBug-hunter: 0 bugs found\n")
        self.change("README.md", "readme\n\nSpec-check: ✓ abc\n")
        after = self.reads(dict.fromkeys(docs))
        self.assertEqual({doc: after[doc] - before[doc] for doc in docs},
                         {"skills/a/SKILL.md": 1, "skills/a/ref.md": 1,
                          "skills/a/DECISIONS.md": 0, "skills/bug-hunter/SKILL.md": 1,
                          "openspec/specs/x/spec.md": 1, "openspec/changes/y/proposal.md": 1})

    def test_reads_are_counted_only_since_the_last_compaction(self):
        self.change("skills/a/ref.md", "one\n")
        stop = self.change("skills/a/ref.md", "the compaction\n")
        self.change("skills/a/ref.md", "three\n")
        self.assertEqual(self.reads({"skills/a/ref.md": stop[:7]}), {"skills/a/ref.md": 1})

    def test_commits_before_the_doc_was_added_imply_no_reads(self):
        root = str(self.repo.path)
        self.change("README.md", "readme\n\nSpec-check: ✓ a\n")
        self.change("README.md", "readme\n\nSpec-check: ✓ b\n")
        self.repo.write("openspec/specs/new/spec.md", "# New\n")
        index = compact.index_entries(root)
        reads = compact.implied_reads(root, index, compact.read_first_links(root, index),
                                      {"openspec/specs/new/spec.md": None})
        self.assertEqual(reads, {"openspec/specs/new/spec.md": 0})

    def test_a_doc_deleted_and_added_again_starts_a_new_history(self):
        root = str(self.repo.path)
        self.repo.write("openspec/specs/a/spec.md", "# A\n")
        self.repo.commit("add\n")
        self.repo.git("rm", "-q", "openspec/specs/a/spec.md")
        self.repo.commit("remove\n")
        self.change("README.md", "readme\n\nSpec-check: ✓ a\n")
        self.repo.write("openspec/specs/a/spec.md", "# A again\n")
        self.repo.commit("add again\n")
        index = compact.index_entries(root)
        reads = compact.implied_reads(root, index, compact.read_first_links(root, index),
                                      {"openspec/specs/a/spec.md": None})
        self.assertEqual(reads, {"openspec/specs/a/spec.md": 0})

    def test_a_subject_naming_a_skill_is_not_a_trailer(self):
        root = str(self.repo.path)
        self.repo.write("openspec/specs/s/spec.md", "# S\n")
        self.repo.commit("add\n")
        self.change("README.md", "spec-check: tweak the script\n")
        index = compact.index_entries(root)
        reads = compact.implied_reads(root, index, compact.read_first_links(root, index),
                                      {"openspec/specs/s/spec.md": None})
        self.assertEqual(reads, {"openspec/specs/s/spec.md": 0})

    def test_a_merge_titled_like_a_trailer_implies_no_read(self):
        root = str(self.repo.path)
        self.repo.write("openspec/specs/m/spec.md", "# M\n")
        self.repo.commit("add\n")
        for n in range(2):
            self.repo.git("checkout", "-q", "-b", f"side{n}")
            self.repo.write(f"side{n}.txt", "x\n")
            self.repo.commit(f"side {n}\n")
            self.repo.git("checkout", "-q", "-")
            self.repo.git("merge", "-q", "--no-ff", f"side{n}", "-m", f"Merge pull request #{n}",
                          "-m", f"spec-check: tweak {n}")
        index = compact.index_entries(root)
        reads = compact.implied_reads(root, index, compact.read_first_links(root, index),
                                      {"openspec/specs/m/spec.md": None})
        self.assertEqual(reads, {"openspec/specs/m/spec.md": 0})

    def test_the_log_is_capped(self):
        for n in range(4):
            self.change("skills/a/ref.md", f"c{n}\n")
        with mock_attr(compact, "READS_DEPTH", 2):
            self.assertEqual(self.reads({"skills/a/ref.md": None}), {"skills/a/ref.md": 2})


class BloatDetectors(unittest.TestCase):
    """Each detector, on the file alone."""

    def kinds(self, text, root=None, path="DOC.md"):
        return [(p.start, p.end, p.kinds) for p in compact.passages(text, path, root)]

    def test_history(self):
        self.assertEqual(self.kinds("# D\n\n**Revised 2026-09-30.** It signs twice.\n"),
                         [(3, 3, ("history",))])

    def test_repetition_of_a_sentence_and_of_a_long_overlap(self):
        found = compact.passages("# D\n\n" + REPEAT + "Other.\n\n" + REPEAT)
        self.assertEqual([(p.start, p.kinds, p.note) for p in found],
                         [(7, ("repetition",), "same as line 3")])
        found = compact.passages("Agents read some docs before every single task, always.\n\n"
                                 "Then: agents read some docs before every single task, so they "
                                 "cost.\n")
        self.assertEqual([(p.start, p.note) for p in found], [(3, "overlaps line 1")])
        self.assertEqual(compact.passages("Agents read some docs.\n\nAgents read some docs.\n"),
                         [])

    def test_amendment_notes(self):
        for text in ("*Amended by decision 12: the hook vets every post.*",
                     "Superseded by decision 3, it stays.", "The rule, as first written, held.",
                     "Item 4 was withdrawn."):
            with self.subTest(text=text):
                self.assertEqual([k for _, _, k in self.kinds(text)], [("amendment",)])

    def test_long_rejected_alternatives(self):
        self.assertEqual(self.kinds("**Rejected: a lock.** It deadlocks. It is slow.\n"),
                         [(1, 1, ("rejected",))])
        self.assertEqual(self.kinds("**Rejected: a lock.** It deadlocks.\n"), [])
        text = ("**Rejected.**\n- **A lock.** It deadlocks. It is slow.\n"
                "- **A queue.** It reorders.\n\nAfter.\n")
        self.assertEqual(self.kinds(text), [(2, 2, ("rejected",))])
        text = "## Rejected: a GitHub Action\n\nIt needs CI.\n\nNo repository has it.\n\n## Next\n"
        self.assertEqual(self.kinds(text), [(3, 5, ("rejected",))])

    def test_stale_references(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("scripts/tool.py", "p.add_argument('--keep')\ndef run(x):\n    pass\n")
        repo.write("DOC.md", "x\n")
        text = ("Use `--keep`.\n\nUse `--gone`.\n\nCall `run()`.\n\nCall `vanish()`.\n\n"
                "See `scripts/tool.py`.\n\nSee `scripts/gone.py`.\n\n"
                "In the target repository, `openspec/specs/` holds them.\n")
        found = compact.passages(text, "DOC.md", str(repo.path))
        self.assertEqual([(p.start, p.kinds) for p in found],
                         [(3, ("stale reference",)), (7, ("stale reference",)),
                          (11, ("stale reference",))])
        # Outside a repository there is nothing to check against.
        self.assertEqual(compact.passages(text, "DOC.md", None), [])

    def test_narrative_words(self):
        for text in ("We tried a lock.", "At first it was slow.", "It turned out to be fine.",
                     "Initially, it signed once.", "It originally ran twice."):
            with self.subTest(text=text):
                self.assertIn("narrative", self.kinds(text)[0][2])
        self.assertEqual(self.kinds("It refuses a previously issued token."), [])

    def test_filler(self):
        for text in ("Note: the token expires.", "It is worth noting that it expires.",
                     "As mentioned above, it expires.", "It expires. In other words, it ends."):
            with self.subTest(text=text):
                self.assertIn("filler", self.kinds(text)[-1][2])
        self.assertEqual(self.kinds("Say it again in other words."), [])

    def test_fenced_and_quoted_text_is_skipped(self):
        text = ('# D\n\n```\nRevised 2026-09-30: an example.\nWe tried a lock.\n```\n\n'
                'Markers such as "previously" and `Note:` are quoted.\n\n> fine\n')
        self.assertEqual(self.kinds(text), [])

    def test_one_sentence_flagged_twice_is_one_passage_with_both_kinds(self):
        found = compact.passages("We tried it, Revised 2026-09-30, and kept it.\n")
        self.assertEqual([p.kinds for p in found], [("history", "narrative")])

    def test_a_passage_spans_the_lines_its_sentence_wraps_over(self):
        found = compact.passages("# D\n\nIt holds. We tried a lock\nfor a day. It holds.\n")
        self.assertEqual([(p.start, p.end, p.text) for p in found],
                         [(3, 4, "We tried a lock\nfor a day.")])


@contextlib.contextmanager
def mock_env(**values):
    old = {name: os.environ.get(name) for name in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class DetectorEdgeCases(unittest.TestCase):
    """Inputs the detectors and the trigger meet in real repositories."""

    def test_a_doc_that_is_not_utf8_does_not_crash_the_trigger(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write(".gitattributes", "* prose-compact-flagged=10\n")
        repo.commit("base\n")
        (repo.path / "SKILL.md").write_bytes(
            b"# S\n\nThe caf\xe9 previously opened at nine in the morning.\n")
        repo.git("add", "SKILL.md")
        found = compact.due(["SKILL.md"], str(repo.path))
        self.assertEqual([item.path for item in found], ["SKILL.md"])

    def test_a_history_label_flags_its_own_sentence(self):
        text = ("# Doc\n\nThe limit is ten requests per second for each client. Update: the "
                "cache now lives in Redis on its own host.\n")
        self.assertEqual([p.text for p in compact.passages(text)],
                         ["Update: the cache now lives in Redis on its own host."])

    def test_a_fence_opened_in_a_list_item_or_a_quote_is_skipped(self):
        text = ("# Doc\n\n- ```text\n  We tried a lock.\n  ```\n\nIt was previously a "
                "different thing.\n\n> ```sh\n> # Note: we tried it twice\n> ```\n")
        self.assertEqual([(p.start, p.kinds) for p in compact.passages(text)],
                         [(7, ("history", "narrative"))])

    def test_the_trigger_fetches_no_blob_in_a_partial_clone(self):
        source = Repo()
        self.addCleanup(source.cleanup)
        for n in range(5):
            source.write("SKILL.md", "# S\n\n" + "Line.\n" * (n + 1) * 20)
            source.commit(f"c{n}\n")
        source.git("config", "uploadpack.allowFilter", "true")
        parent = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, parent, True)
        clone = parent / "clone"
        result = run(["git", "clone", "-q", "--filter=blob:none", "--no-local",
                      f"file://{source.path}", str(clone)])
        if result.returncode != 0:
            self.skipTest(f"git cannot make a partial clone here: {result.stderr}")
        (clone / "SKILL.md").write_text("# S\n\n" + "Line.\n" * 101)
        run(["git", "add", "SKILL.md"], cwd=clone)
        trace = parent / "trace"
        with mock_env(GIT_TRACE=str(trace)):
            compact.due(["SKILL.md"], str(clone))
        fetches = re.findall(r"built-in: git fetch\b.*", trace.read_text() if trace.exists() else "")
        self.assertEqual(fetches, [])


class DetectorEdgeCasesTwo(unittest.TestCase):
    """More inputs the detectors and the trigger meet in real repositories."""

    def repo(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        return repo

    def test_the_users_grep_settings_do_not_make_references_stale(self):
        repo = self.repo()
        repo.write("scripts/tool.py", "p.add_argument('--verify')\ndef build_it():\n    pass\n")
        repo.git("config", "grep.lineNumber", "true")
        repo.git("config", "grep.column", "true")
        text = "# Doc\n\nRun `--verify`, then call `build_it()`.\n"
        self.assertEqual(compact.passages(text, "DOC.md", str(repo.path)), [])

    def test_a_path_holding_glob_characters_reads_only_its_own_history(self):
        repo = self.repo()
        repo.write("d[x]/DECISIONS.md", "a" * 10000)
        repo.write("dx/DECISIONS.md", "b" * 10000)
        repo.commit("add\n")
        repo.write("d[x]/DECISIONS.md", "a" * 5000)
        repo.commit("compact d[x]\n")
        repo.write("dx/DECISIONS.md", "b" * 500)
        repo.commit("compact dx\n")
        self.assertEqual(compact.size_history("d[x]/DECISIONS.md", str(repo.path)).last[1], 5000)

    def test_read_first_links_written_inside_the_sentence_count(self):
        for text in ("Read [x](x.md) first.", "Read [the design](design.md) before you start."):
            with self.subTest(text=text):
                self.assertTrue(compact.READ_FIRST.search(text))
        self.assertFalse(compact.READ_FIRST.search("Read [x](x.md) before changing this file."))

    def test_a_stale_reference_alone_on_its_line_is_its_own_passage(self):
        repo = self.repo()
        repo.write("scripts/tool.py", "x = 1\n")
        text = "# Doc\n\nThe build runs nightly.\n\n`scripts/old.py`\n"
        found = compact.passages(text, "DOC.md", str(repo.path))
        self.assertEqual([(p.start, p.text) for p in found], [(5, "`scripts/old.py`")])

    def test_a_sentence_starting_with_code_or_a_quote_is_its_own(self):
        for text in ("The gate is strict. `prose check` previously ran nightly.",
                     'The gate is strict. "Sign" previously ran nightly.'):
            with self.subTest(text=text):
                self.assertEqual([p.text[:20] for p in compact.passages(text)], [text[20:40]])

    def test_inline_code_of_triple_backticks_opens_no_fence(self):
        text = ("- ```a `` b``` is how a span holding two backticks is written.\n\n"
                "Previously the gate ran nightly.\n")
        self.assertEqual([p.start for p in compact.passages(text)], [3])

    def test_stale_paths_are_checked_quickly_in_a_large_repository(self):
        tracked = {f"src/module{n}/file{n}.py" for n in range(200_000)}
        spans = [(n, f"src/gone{n}.py") for n in range(300)]
        started = time.time()
        found = compact._stale(spans, "DOC.md", "/nonexistent", tracked)
        self.assertEqual(len(found), 300)
        self.assertLess(time.time() - started, 1.5)


class DetectorEdgeCasesThree(unittest.TestCase):
    """More inputs the detectors and the trigger meet in real repositories."""

    def test_a_horizontal_rule_on_the_first_line_is_not_front_matter(self):
        text = "---\n\n# Title\n\nWe previously used X here.\n"
        self.assertEqual([p.start for p in compact.passages(text)], [5])

    def test_inline_code_wrapped_over_a_line_break_is_skipped(self):
        self.assertEqual(compact.passages("Run the command `prose check --note-that\n"
                                          "basically` to see it.\n"), [])

    def test_every_history_marker_verify_reads_is_a_flagged_passage(self):
        for text in ("# T\n\nThe flag is set by `--mode\npreviously-set` in the config file.\n",
                     "# T\n\nWrite ``a`b`` in the shell.\nPreviously the tool used `make` to "
                     "build.\n",
                     "---\nname: x\ndescription: Formerly the build skill. Use it to build.\n---"
                     "\n\n# X\n\nBody text.\n"):
            with self.subTest(text=text):
                flagged = {line for p in compact.passages(text) if "history" in p.kinds
                           for line in range(p.start, p.end + 1)}
                self.assertLessEqual({m.line for m in compact.history_markers(text)}, flagged)
                if "Previously the tool" in text:
                    self.assertIn(4, flagged)

    def test_a_quote_inside_code_hides_no_stale_reference(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("scripts/real.py", "x = 1\n")
        text = 'Split on `"` first, then read `scripts/gone.py` for it. He said "fine".\n'
        self.assertEqual([p.kinds for p in compact.passages(text, "DOC.md", str(repo.path))],
                         [("stale reference",)])

    def test_a_read_first_link_with_a_title_counts(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("s/SKILL.md", '# S\n\nRead [the guide](guide.md "The guide") first.\n')
        repo.write("s/guide.md", "g\n")
        root = str(repo.path)
        self.assertEqual(compact.read_first_links(root, compact.index_entries(root)),
                         {"s/guide.md": "s/SKILL.md"})

    def test_a_shallow_clone_that_misses_the_compaction_is_not_due(self):
        source = Repo()
        self.addCleanup(source.cleanup)
        flagged = "".join(f"Note that rule {n} was previously used here.\n\n" for n in range(40))
        source.write(".gitattributes", "* prose-compact-flagged=1000\n")
        source.write("CLAUDE.md", flagged + "Plain text line.\n" * 200)
        source.commit("add\n")
        source.write("CLAUDE.md", flagged + "Plain text line.\n" * 20)
        source.commit("compact, keeping the flagged text\n")
        for n in range(3):
            source.write("a.txt", f"{n}\n")
            source.commit(f"other {n}\n")
        parent = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, parent, True)
        clone = parent / "clone"
        result = run(["git", "clone", "-q", "--depth=2", f"file://{source.path}", str(clone)])
        if result.returncode != 0:
            self.skipTest(f"git cannot make a shallow clone here: {result.stderr}")
        (clone / "CLAUDE.md").write_text(flagged + "Plain text line.\n" * 20 + "More.\n")
        run(["git", "add", "CLAUDE.md"], cwd=clone)
        self.assertEqual(compact.due(["CLAUDE.md"], str(clone)), [])

    def test_repetition_inside_code_or_quotes_is_not_flagged(self):
        code = "`prose.py compact --verify my-file.md --paths-from list.txt -0 --extra one`"
        quote = '"commit this, commit my changes, let us commit, wrap this up and commit"'
        for shared in (code, quote):
            with self.subTest(shared=shared):
                text = (f"Run {shared} to start.\n\nLater, {shared} finishes the job.\n")
                self.assertEqual(compact.passages(text), [])

    def test_a_new_doc_in_a_repository_with_no_commits_is_judged(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write(".gitattributes", "* prose-compact-flagged=50\n")
        repo.write("CLAUDE.md", repeated(3))
        self.assertEqual([d.path for d in compact.due(["CLAUDE.md"], str(repo.path))],
                         ["CLAUDE.md"])

    def test_a_new_doc_in_a_shallow_clone_is_judged(self):
        source = Repo()
        self.addCleanup(source.cleanup)
        for n in range(3):
            source.write("a.txt", f"{n}\n")
            source.commit(f"c{n}\n")
        parent = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, parent, True)
        clone = parent / "clone"
        result = run(["git", "clone", "-q", "--depth=1", f"file://{source.path}", str(clone)])
        if result.returncode != 0:
            self.skipTest(f"git cannot make a shallow clone here: {result.stderr}")
        (clone / ".gitattributes").write_text("* prose-compact-flagged=50\n")
        (clone / "CLAUDE.md").write_text(repeated(3))
        run(["git", "add", ".gitattributes", "CLAUDE.md"], cwd=clone)
        self.assertEqual([d.path for d in compact.due(["CLAUDE.md"], str(clone))],
                         ["CLAUDE.md"])

    def test_a_fence_with_an_info_string_does_not_close_an_open_fence(self):
        text = ("# Doc\n\n```\n```python\nNote: this is code, basically.\n```\n\n"
                "Previously the real prose ran here.\n")
        self.assertEqual([p.start for p in compact.passages(text)], [8])

    def test_an_indented_fence_inside_a_block_does_not_close_it(self):
        text = ('# D\n\nIntro.\n\n```python\ndef f():\n    """Example:\n\n    ```\n'
                '    # we initially tried a lock, note that this is code\n    ```\n    """\n```\n\n'
                'End.\n')
        self.assertEqual(compact.passages(text), [])

    def test_a_quoted_fence_in_a_list_item_hides_nothing_after_it(self):
        text = ("# Doc\n\n- > ```sh\n  > run it\n  > ```\n\nWe tried a lock and it turned "
                "out slow.\n")
        self.assertEqual([p.start for p in compact.passages(text)], [7])

    def test_the_stale_lookup_is_built_once_for_many_docs(self):
        tracked = {f"a{n % 50}/b{n % 7}/c{n}/d/e/f{n}.py" for n in range(300_000)}
        started = time.time()
        for _ in range(10):
            compact._stale([(0, "a1/b1/x.py")], "docs/x.md", "/nonexistent", tracked)
        self.assertLess(time.time() - started, 3)

    def test_an_unreadable_baseline_in_a_partial_clone_is_not_zero(self):
        source = Repo()
        self.addCleanup(source.cleanup)
        flagged = "".join(f"Note that rule {n} was previously used here.\n\n" for n in range(40))
        source.write(".gitattributes", "* prose-compact-flagged=1000\n")
        source.write("CLAUDE.md", flagged + "Plain text line.\n" * 200)
        source.commit("add\n")
        source.write("CLAUDE.md", flagged + "Plain text line.\n" * 20)
        source.commit("compact, keeping the flagged text\n")
        source.write("CLAUDE.md", flagged + "Plain text line.\n" * 20 + "Later.\n")
        source.commit("a later line\n")
        source.git("config", "uploadpack.allowFilter", "true")
        parent = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, parent, True)
        clone = parent / "clone"
        result = run(["git", "clone", "-q", "--filter=blob:none", "--no-local",
                      f"file://{source.path}", str(clone)])
        if result.returncode != 0:
            self.skipTest(f"git cannot make a partial clone here: {result.stderr}")
        (clone / "CLAUDE.md").write_text(flagged + "Plain text line.\n" * 20 + "Later.\nMore.\n")
        run(["git", "add", "CLAUDE.md"], cwd=clone)
        self.assertEqual(compact.due(["CLAUDE.md"], str(clone)), [])


class TriggerFailure(unittest.TestCase):
    """The trigger only advises: an error in it never stops the first call."""

    def test_a_trigger_error_warns_and_the_first_call_goes_on(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("SKILL.md", "# S\n")
        (repo.path / ".msg").write_text("DOCS(x): c\n")
        real = prose.compactor()

        def broken(*args, **kwargs):
            raise RuntimeError("the trigger broke")

        out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        err = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        here = os.getcwd()
        os.chdir(repo.path)
        try:
            with mock_attr(real, "due", broken), contextlib.redirect_stdout(out), \
                    contextlib.redirect_stderr(err):
                code = prose.main(["check", "-F", ".msg", "--goals", "g"] + ALL_FILES)
        finally:
            os.chdir(here)
        out.flush()
        err.flush()
        printed, warned = (stream.buffer.getvalue().decode("utf-8") for stream in (out, err))
        self.assertEqual(code, 4, warned)
        self.assertIn("the trigger broke", warned)
        self.assertIn("compaction", warned)
        self.assertRegex(printed, r"[0-9a-f]{16}")


class CompactedTrailer(unittest.TestCase):
    """A committed compaction is named in the Prose: trailer, so every
    clone's trigger sees it, whatever it cut."""

    NOTES = "".join(f"Note that rule {n} holds for every commit here.\n\n" for n in range(25))
    PLAIN = "".join(f"Plain line {n} states a fact.\n" for n in range(150))

    def compact_little(self, repo):
        """Compact SKILL.md, keeping every flagged passage and cutting under
        a tenth, through every step; returns the signing call's result."""
        repo.write(".gitattributes", "* prose-compact-flagged=1000\n")
        repo.write("SKILL.md", self.NOTES + self.PLAIN)
        repo.commit("add\n")
        brief = repo.prose("compact", "SKILL.md")
        repo.write("SKILL.md", self.NOTES + self.PLAIN[:len(self.PLAIN) * 95 // 100])
        answers_file(brief.stdout).write_text(
            "".join(f"Passage {n}: kept: a false flag\n" for n in range(1, 26)))
        self.assertEqual(repo.prose("compact", "SKILL.md", "--verify").returncode, 0)
        review = repo.prose("compact", "SKILL.md", "--review")
        count = int(re.search(r"Changes: ([0-9]+)", review.stdout).group(1))
        (repo.path / ".reply").write_text(
            "".join(f"Change {n}: superseded\n" for n in range(1, count + 1))
            + "".join(f"Passage {n}: justified\n" for n in range(1, 26))
            + "Totals: 0 lost, 0 false\n")
        done = repo.prose("compact", "SKILL.md", "--reviewed", str(repo.path / ".reply"))
        self.assertEqual(done.returncode, 0, done.stderr)
        return repo.trailers("DOCS(x): compact SKILL.md\n")

    def test_a_fresh_clone_sees_a_small_compaction_through_the_trailer(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        trailer = self.compact_little(repo)
        self.assertTrue(trailer.endswith("; compacted: SKILL.md"), trailer)
        repo.commit("DOCS(x): compact SKILL.md\n", trailers=[trailer])
        self.assertEqual(repo.verify().returncode, 0, repo.verify().stdout)
        parent = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, parent, True)
        clone = parent / "clone"
        run(["git", "clone", "-q", str(repo.path), str(clone)])
        self.assertFalse((clone / ".git/prose").exists())
        (clone / "SKILL.md").write_text((clone / "SKILL.md").read_text() + "One more line.\n")
        run(["git", "add", "SKILL.md"], cwd=clone)
        self.assertEqual(compact.due(["SKILL.md"], str(clone)), [])

    def test_an_amend_after_a_plain_check_still_lists_the_compaction(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        trailer = self.compact_little(repo)
        repo.commit("DOCS(x): compact SKILL.md\n", trailers=[trailer])
        repo.write("other.txt", "x\n")
        repo.trailers("DOCS(x): compact SKILL.md\n")
        amended = repo.trailers("DOCS(x): compact SKILL.md\n", "--amend")
        self.assertTrue(amended.endswith("; compacted: SKILL.md"), amended)

    def test_the_users_trailer_separators_do_not_hide_the_record(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("doc.md", "a\n" * 100)
        repo.commit("add\n")
        repo.write("doc.md", "a\n" * 99)
        repo.commit("compact\n\nProse: ✓ 0123456789ab:0123456789ab; compacted: doc.md\n")
        repo.git("config", "trailer.separators", "#")
        self.assertIsNotNone(compact.size_history("doc.md", str(repo.path)).last)

    def test_a_hand_added_compacted_list_is_refused(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        repo.write("README.md", "# R\n")
        repo.commit("base\n")
        repo.write("README.md", "# R\n\nMore.\n")
        message = "DOCS(x): more\n"
        trailer = repo.trailers(message) + "; compacted: README.md"
        staged = repo.prose("verify-staged", trailer, stdin=message)
        self.assertEqual(staged.returncode, 1, staged.stdout)
        self.assertIn("compacted", staged.stdout)
        repo.commit(message, trailers=[trailer.replace("README.md", "NOT-CHANGED.md")])
        committed = repo.verify()
        self.assertNotEqual(committed.returncode, 0, committed.stdout)
        self.assertIn("compacted", committed.stdout + committed.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)


#!/usr/bin/env python3
"""Tests for the reading cost: the sections a compaction brief lists to
consider moving out, the skill descriptions `prose check` measures, the
reads each commit implies of an AGENTS.md or CLAUDE.md, and `prose cost`.

Standard library only:

    python3 test_reading_cost.py
"""

import os
import random
import re
import unittest

from prose_test_support import Repo, compact, mock_attr

reading_cost = compact.reading_cost


def sections(text, minimum=0):
    return reading_cost.conditional_sections(text, compact.code_lines(text), minimum)


def body(words=200):
    """A paragraph of about words words that states no condition."""
    return " ".join(f"word{n}" for n in range(words)) + ".\n"


class ConditionalSections(unittest.TestCase):
    """Which sections the detector proposes, and where each ends."""

    def titles(self, text, minimum=0):
        return [(found.kind, found.title) for found in sections(text, minimum)]

    def test_a_heading_that_states_a_condition_is_a_section_to_its_next_peer(self):
        text = ("# Skill\n\nIntro.\n\n## When the caller commits\n\nStage it.\n\n"
                "### Its block\n\nPrint it.\n\n## Never\n\nGuess.\n")
        found = sections(text)
        self.assertEqual([(f.kind, f.title, f.start, f.end) for f in found],
                         [("heading", "When the caller commits", 5, 11)])
        lines = text.split("\n")
        self.assertEqual(found[0].size, sum(len(line) + 1 for line in lines[4:11]))

    def test_each_kind_of_condition_counts(self):
        for title in ("When the caller commits", "Whenever a hook fires", "If you are a subagent",
                      "Unless the repository opted out", "Only when asked", "Without subagents",
                      "With bug-hunter installed", "Called by another skill", "Setup",
                      "First-time setup", "Installing", "Troubleshooting", "Upgrading",
                      "Migrating from v1", "On Windows", "In case the token expires"):
            with self.subTest(title=title):
                self.assertEqual(self.titles(f"# T\n\n## {title}\n\n{body()}"),
                                 [("heading", title)])

    def test_steps_every_reader_runs_and_the_skills_trigger_are_no_condition(self):
        for title in ("Before a commit", "After the last fix", "Once it passes",
                      "While it runs", "When", "When to use one", "When to write a TLA+ model",
                      "If you are an agent about to commit", "`uninstall` removes its hook",
                      "With care", "Settings"):
            with self.subTest(title=title):
                self.assertEqual(self.titles(f"# T\n\n## {title}\n\n{body()}"), [])

    def test_a_section_every_reader_meets_is_not_reopened_by_its_first_sentence(self):
        text = f"# T\n\n## If you are an agent about to commit\n\nIf another skill commits, wait.\n\n{body()}"
        self.assertEqual(self.titles(text), [])

    def test_a_first_paragraph_that_opens_with_a_condition_introduces_the_section(self):
        text = f"# T\n\n## Remind and block modes\n\nWhen the user asks which mode is on, run it.\n\n{body()}"
        self.assertEqual(self.titles(text), [("first sentence", "Remind and block modes")])
        found = sections(text)[0]
        self.assertEqual(found.condition, "When the user asks which mode is on, run it.")

    def test_only_a_plain_first_paragraph_introduces_a_section(self):
        for first in ("- When a list item", "| When | a table |", "> When quoted",
                      "**When bold** leads it.", "```\nWhen in code\n```"):
            with self.subTest(first=first):
                found = self.titles(f"# T\n\n## Modes\n\n{first}\n\n{body()}")
                self.assertNotIn("first sentence", [kind for kind, _ in found])

    def test_a_lead_in_takes_the_lists_and_code_after_it_up_to_the_next_paragraph(self):
        text = ("# T\n\nIntro.\n\n**When it is due.** It prints this:\n- one\n- two\n\n"
                "```sh\nrun it\n```\n\n| a | b |\n\nA plain paragraph.\n")
        found = sections(text)
        self.assertEqual([(f.kind, f.title, f.start, f.end) for f in found],
                         [("lead-in", "When it is due.", 5, 13)])

    def test_a_list_items_lead_in_takes_only_its_own_lines(self):
        text = ("# T\n\n- **If an agent spawned it**, its report is yours.\n"
                "  It goes on here.\n\n  And here.\n- **Plain item.** Not part of it.\n")
        found = sections(text)
        self.assertEqual([(f.kind, f.start, f.end) for f in found], [("lead-in", 3, 6)])

    def test_a_list_items_lead_in_stops_at_the_sibling_on_the_next_line(self):
        text = "# T\n\n- **If an item** leads.\n- sibling\n- another\n"
        self.assertEqual([(f.start, f.end) for f in sections(text)], [(3, 3)])

    def test_only_a_level_1_heading_that_comes_first_is_the_title(self):
        text = f"## When it fails first\n\n{body(5)}\n# T\n\n{body(5)}\n# When it fails later\n\n{body(5)}"
        self.assertEqual(self.titles(text), [("heading", "When it fails first"),
                                             ("heading", "When it fails later")])

    def test_a_lead_in_inside_a_list_items_continuation_stays_inside_the_item(self):
        text = ("# T\n\n- **If you run on CI.** One.\n\n  **When the caller commits.** Two.\n\n"
                "- Plain next item.\n  more of it\n\nClosing paragraph.\n")
        found = sections(text)
        for first, second in zip(found, found[1:]):
            self.assertLess(first.end, second.start)
        self.assertEqual([(f.start, f.end) for f in found], [(3, 5)])

    def test_a_lead_in_straight_under_a_heading_opens_its_block(self):
        for above in ("## Modes", "```\ncode\n```"):
            with self.subTest(above=above):
                text = f"# T\n\n{above}\n**If you run on CI.** {body(5)}"
                self.assertEqual([f.kind for f in sections(text)], ["lead-in"])

    def test_a_lead_in_must_open_its_block(self):
        text = "# T\n\nA line.\n**When joined** to it, it leads nothing.\n"
        self.assertEqual(sections(text), [])

    def test_a_section_inside_another_is_proposed_once(self):
        text = (f"# T\n\n## Setup\n\n**If you are offline**, wait.\n\n### When it fails\n\n"
                f"{body()}\n## Next\n\nText.\n")
        self.assertEqual(self.titles(text), [("heading", "Setup")])

    def test_headings_in_code_and_the_title_are_never_sections(self):
        self.assertEqual(self.titles(f"# When the title says so\n\n{body()}"), [])
        self.assertEqual(self.titles(f"# T\n\n```md\n## When in code\n```\n\n{body()}"), [])

    def test_small_sections_are_not_proposed(self):
        small = "# T\n\n## When it fails\n\nRetry.\n"
        self.assertEqual(sections(small, reading_cost.MOVE_MIN_BYTES), [])
        large = f"# T\n\n## When it fails\n\n{body()}"
        self.assertEqual(len(sections(large, reading_cost.MOVE_MIN_BYTES)), 1)

    def test_code_must_mark_every_line(self):
        with self.assertRaises(ValueError):
            reading_cost.conditional_sections("a\nb\n", [False])

    def test_heading_matches_the_same_lines_as_compacts(self):
        for line in ("## Two", "   ### Indented", "#\tTab", "#### Closed ##", "#NoSpace",
                     "    #### Four spaces", "####### Seven", "## "):
            with self.subTest(line=line):
                self.assertEqual(bool(reading_cost.HEADING.match(line)),
                                 bool(compact.HEADING.match(line)))


class ConditionalSectionsProperties(unittest.TestCase):
    """Invariants over random docs built from the shapes the detector reads."""

    PIECES = ("## When it fails\n", "## Setup\n", "### If offline\n", "## Plain heading\n",
              "# Another top\n", "When the user asks, run it.\n", "A plain sentence.\n",
              "**When bold** leads.\n", "- **If an item** leads.\n", "  continued.\n",
              "- plain item\n", "```\n## When in code\n```\n", "| a | b |\n", "> quoted\n",
              "\n", "\n")

    def docs(self, count=300):
        rng = random.Random(36)
        for _ in range(count):
            parts = ["# Title\n\n"] + [rng.choice(self.PIECES) for _ in range(rng.randint(0, 40))]
            yield "".join(parts)

    def test_sections_are_ordered_disjoint_measured_and_never_open_on_code(self):
        for text in self.docs():
            with self.subTest(text=text):
                lines = text.split("\n")
                code = compact.code_lines(text)
                found = reading_cost.conditional_sections(text, code, 0)
                # Each line is proposed at most once.
                for first, second in zip(found, found[1:]):
                    self.assertLess(first.end, second.start)
                for one in found:
                    self.assertLessEqual(one.start, one.end)
                    self.assertLessEqual(one.end, len(lines))
                    self.assertFalse(code[one.start - 1])
                    self.assertEqual(one.size, sum(len(line.encode()) + 1
                                                   for line in lines[one.start - 1:one.end]))
                    self.assertFalse([other for other in found if other is not one
                                      and other.start <= one.start and one.end <= other.end])

    def test_a_higher_minimum_only_filters(self):
        for text in self.docs(150):
            code = compact.code_lines(text)
            every = reading_cost.conditional_sections(text, code, 0)
            for minimum in (1, 40, 200):
                with self.subTest(text=text, minimum=minimum):
                    self.assertEqual(reading_cost.conditional_sections(text, code, minimum),
                                     [one for one in every if one.size >= minimum])


class Descriptions(unittest.TestCase):
    """skill_description reads a description as a YAML reader loads it."""

    def test_the_shapes_skills_use(self):
        cases = {
            "---\nname: a\ndescription: >-\n  Folded over\n  two lines.\n---\n": "Folded over two lines.",
            "---\ndescription: >\n  Folded, clipped.\n\n  New paragraph.\nname: a\n---\n":
                "Folded, clipped.\nNew paragraph.",
            "---\ndescription: |-\n  Literal\n  lines.\n---\n": "Literal\nlines.",
            "---\ndescription: Plain on one line # a comment\n---\n": "Plain on one line",
            "---\ndescription: Plain\n  continued.\nname: a\n---\n": "Plain continued.",
            "---\ndescription: \"Double \\\"quoted\\\"\"\n---\n": "Double \"quoted\"",
            "---\ndescription: 'It''s single'\n---\n": "It's single",
            "---\r\ndescription: CRLF\r\n---\r\n": "CRLF",
        }
        for text, value in cases.items():
            with self.subTest(text=text):
                self.assertEqual(reading_cost.skill_description(text), value)

    def test_a_value_on_the_line_after_the_key(self):
        cases = {
            "---\ndescription:\n  \"Use when it's a \\\"quoted\\\" case,\n  and more.\"\n---\n":
                "Use when it's a \"quoted\" case, and more.",
            "---\ndescription:\n  Use when a,\n  and b.\nname: a\n---\n": "Use when a, and b.",
        }
        for text, value in cases.items():
            with self.subTest(text=text):
                self.assertEqual(reading_cost.skill_description(text), value)

    def test_a_comment_before_the_value_is_not_part_of_it(self):
        for text in ("---\ndescription: # note\n  Use when a.\n---\n",
                     "---\ndescription:\n  # note\n  Use when a.\n---\n",
                     "---\ndescription:\n# note at the margin\n  Use when a.\n---\n"):
            with self.subTest(text=text):
                self.assertEqual(reading_cost.skill_description(text), "Use when a.")

    def test_a_line_at_the_left_margin_ends_the_value(self):
        for after in ("# owner: team-x", "license: MIT", "..."):
            with self.subTest(after=after):
                text = f"---\ndescription: >\n  Use when a.\n{after}\nname: a\n---\n"
                self.assertEqual(reading_cost.skill_description(text), "Use when a.")

    def test_no_front_matter_or_no_description_is_none(self):
        for text in ("# Skill\n", "---\nname: a\n---\n", "---\ndescription: unclosed\n",
                     "text\n---\ndescription: late\n---\n", "---\ndescription:\nname: a\n---\n"):
            with self.subTest(text=text):
                self.assertIsNone(reading_cost.skill_description(text))

    def test_a_folded_value_reads_back_at_any_wrap_width(self):
        rng = random.Random(1024)
        words = ["Rewrite", "any", "text", "—", "READMEs,", "\"quoted\"", "it's", "a:b",
                 "`code`", "#tag", "é"]
        for _ in range(300):
            value = " ".join(rng.choice(words) for _ in range(rng.randint(1, 60)))
            width = rng.randint(10, 90)
            lines, line = [], ""
            for word in value.split(" "):
                if line and len(line) + 1 + len(word) > width:
                    lines.append(line)
                    line = word
                else:
                    line = f"{line} {word}" if line else word
            lines.append(line)
            text = "---\nname: x\ndescription: >-\n" + "".join(f"  {l}\n" for l in lines) + "---\n"
            with self.subTest(text=text):
                self.assertEqual(reading_cost.skill_description(text), value)

    def test_the_limit_counts_characters_not_bytes(self):
        at = reading_cost.measure("a", "é" * reading_cost.DESCRIPTION_LIMIT)
        self.assertEqual(at.size, 2 * reading_cost.DESCRIPTION_LIMIT)
        self.assertFalse(reading_cost.over_limit(at))
        self.assertTrue(reading_cost.over_limit(
            reading_cost.measure("a", "e" * (reading_cost.DESCRIPTION_LIMIT + 1))))


def skill(description):
    return f"---\nname: a\ndescription: >-\n  {description}\n---\n\n# A\n"


class CheckMeasuresDescriptions(unittest.TestCase):
    """prose check's first call measures each description the change sets."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("skills/a/SKILL.md", skill("Use when a."))
        self.repo.write("skills/b/SKILL.md", skill("Use when b, a longer one."))
        self.repo.commit("base\n")

    def first_call(self):
        (self.repo.path / ".msg").write_text("Change it\n", encoding="utf-8")
        result = self.repo.prose("check", "-F", ".msg", "--goals", "review it")
        self.assertEqual(result.returncode, 4, result.stderr)
        return result.stdout

    def test_a_changed_description_is_measured_beside_what_it_was_and_the_total(self):
        self.repo.write("skills/a/SKILL.md", skill("Use when a, now longer."))
        out = self.first_call()
        self.assertIn("Skill descriptions (a host loads each one in every session", out)
        self.assertIn("  skills/a/SKILL.md: 23 bytes (23 characters), was 11 bytes\n", out)
        self.assertIn("All 2 descriptions here: 48 bytes, about 12 tokens", out)
        self.assertNotIn("skills/b/SKILL.md:", out)

    def test_a_new_skill_is_measured(self):
        self.repo.write("skills/c/SKILL.md", skill("New."))
        self.assertIn("skills/c/SKILL.md: 4 bytes (4 characters), a new skill", self.first_call())

    def test_a_long_description_is_flagged(self):
        self.repo.write("skills/a/SKILL.md", skill("x" * (reading_cost.DESCRIPTION_LIMIT + 1)))
        self.assertIn("over the 1,024 characters the Agent Skills specification allows",
                      self.first_call())

    def test_a_skill_edited_elsewhere_prints_nothing(self):
        self.repo.write("skills/a/SKILL.md", skill("Use when a.") + "\nMore.\n")
        self.assertNotIn("Skill descriptions", self.first_call())

    def test_an_amend_compares_with_the_parent(self):
        self.repo.write("skills/a/SKILL.md", skill("Use when a, amended."))
        self.repo.commit("amend me\n")
        (self.repo.path / ".msg").write_text("Change it\n", encoding="utf-8")
        result = self.repo.prose("check", "-F", ".msg", "--goals", "review it", "--amend")
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("skills/a/SKILL.md: 20 bytes (20 characters), was 11 bytes", result.stdout)


class NoLazyFetch(unittest.TestCase):
    """The reads the brief and the description measure make never fetch a
    blob a partial clone lacks, as the trigger's never do."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("skills/a/SKILL.md", skill("Use a.") + f"\n## When it fails\n\n{body()}")
        self.repo.commit("add\n")
        self.seen = []
        real = compact._git

        def spy(args, root, stdin=None):
            self.seen.append(os.environ.get("GIT_NO_LAZY_FETCH"))
            return real(args, root, stdin)
        patch = mock_attr(compact, "_git", spy)
        patch.__enter__()
        self.addCleanup(patch.__exit__, None, None, None)

    def test_brief_moves_reads_with_no_lazy_fetch(self):
        root = str(self.repo.path)
        where = compact.Target(self.repo.path / "skills/a/SKILL.md", root, "skills/a/SKILL.md")
        text = (self.repo.path / "skills/a/SKILL.md").read_text()
        compact.brief_moves(where, text, compact.settings([where.rel], root)[where.rel])
        self.assertTrue(self.seen)
        self.assertEqual(set(self.seen), {"1"})

    def test_changed_descriptions_reads_with_no_lazy_fetch(self):
        self.repo.write("skills/a/SKILL.md", skill("Use a, changed."))
        compact.changed_descriptions(["skills/a/SKILL.md"], str(self.repo.path), False)
        self.assertTrue(self.seen)
        self.assertEqual(set(self.seen), {"1"})


class GuideReads(unittest.TestCase):
    """Each commit reads every AGENTS.md and CLAUDE.md above the files it
    changes, and the files an AGENTS.md links as read first."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("AGENTS.md", "# Repo\n\nRead [the guide](guide.md) first.\n")
        self.repo.write("guide.md", "# Guide\n")
        self.repo.write("CLAUDE.md", "# Claude\n")
        self.repo.write("app/AGENTS.md", "# App\n")
        self.repo.write("app/main.go", "package main\n")
        self.repo.write("docs/x.md", "x\n")
        self.repo.commit("base\n")

    def reads(self):
        root = str(self.repo.path)
        index = compact.index_entries(root)
        docs = ["AGENTS.md", "guide.md", "CLAUDE.md", "app/AGENTS.md"]
        return compact.implied_reads(root, index, compact.read_first_links(root, index),
                                     dict.fromkeys(docs))

    def test_a_file_a_skill_also_links_read_first_still_gets_the_guides_reads(self):
        # read_first_links keeps the first source in path order, so a skill
        # under `.agents/`, which sorts before AGENTS.md, takes guide.md from it.
        self.repo.write(".agents/skills/a/SKILL.md",
                        "# A\n\nRead [the guide](../../../guide.md) first.\n")
        self.repo.commit("skill\n")
        root = str(self.repo.path)
        index = compact.index_entries(root)
        links = compact.read_first_links(root, index)
        before = compact.implied_reads(root, index, links, {"guide.md": None})["guide.md"]
        self.repo.write("docs/x.md", "y\n")
        self.repo.commit("docs\n")
        after = compact.implied_reads(root, index, links, {"guide.md": None})["guide.md"]
        self.assertEqual(after - before, 1)

    def test_each_commit_reads_the_guides_above_its_files(self):
        before = self.reads()
        self.repo.write("docs/x.md", "y\n")
        self.repo.commit("docs\n")
        self.repo.write("app/main.go", "package main // two\n")
        self.repo.commit("app\n")
        after = self.reads()
        self.assertEqual({doc: after[doc] - before[doc] for doc in after},
                         {"AGENTS.md": 2, "guide.md": 2, "CLAUDE.md": 2, "app/AGENTS.md": 1})


class Moves(unittest.TestCase):
    """The compaction brief lists the sections to consider moving out, and
    prose cost ranks them across the repository."""

    CONDITIONAL = f"## When the caller commits\n\n{body()}\n"

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def brief(self, path):
        result = self.repo.prose("compact", path)
        self.assertEqual(result.returncode, 4, result.stderr)
        return re.search(r"=== compaction brief ===\n(.*)=== end compaction brief ===",
                         result.stdout, re.S).group(1)

    def test_a_skill_brief_lists_each_section_with_its_cost(self):
        self.repo.write("skills/a/SKILL.md", f"# A\n\nIntro.\n\n{self.CONDITIONAL}")
        self.repo.commit("add a\n")
        self.repo.write("skills/a/x.py", "x = 1\n")
        self.repo.commit("touch a\n")
        out = self.brief("skills/a/SKILL.md")
        size = len(self.CONDITIONAL.rstrip("\n").encode()) + 1
        self.assertIn("Sections to consider moving out (1), by reading cost: each section's "
                      "bytes times this doc's 2 estimated reads", out)
        self.assertIn(f"  Section 1, lines 5-7, {size:,} bytes, cost {2 * size:,}: headed "
                      "«When the caller commits»", out)

    def test_a_doc_not_loaded_before_work_lists_none(self):
        for path in ("skills/a/DECISIONS.md", "openspec/specs/x/spec.md"):
            with self.subTest(path=path):
                self.repo.write(path, f"# D\n\n{self.CONDITIONAL}")
                self.repo.commit(f"add {path}\n")
                self.assertIn("Sections to consider moving out: none; agents do not load this "
                              "doc before every task.", self.brief(path))
                self.assertEqual(self.repo.prose("compact", "--abandon", path).returncode, 0)

    def test_a_declared_doc_gets_a_list(self):
        self.repo.write(".gitattributes", "docs/runbook.md prose-compact\n")
        self.repo.write("docs/runbook.md", f"# R\n\n{self.CONDITIONAL}")
        self.repo.commit("add\n")
        self.assertIn("Sections to consider moving out (1)", self.brief("docs/runbook.md"))

    def test_a_declared_decisions_md_lists_none(self):
        self.repo.write(".gitattributes", "*.md prose-compact\n")
        self.repo.write("skills/a/DECISIONS.md", f"# D\n\n{self.CONDITIONAL}")
        self.repo.commit("add\n")
        self.assertIn("Sections to consider moving out: none; agents do not load this "
                      "doc before every task.", self.brief("skills/a/DECISIONS.md"))

    def test_a_skill_with_no_section_lists_none(self):
        self.repo.write("skills/a/SKILL.md", "# A\n\nAll of it, always.\n")
        self.repo.commit("add\n")
        self.assertIn("Sections to consider moving out: none.\n", self.brief("skills/a/SKILL.md"))

    def test_prose_cost_ranks_sections_by_bytes_times_reads(self):
        small = f"## If offline\n\n{body(170)}\n"
        self.repo.write("skills/a/SKILL.md", f"---\ndescription: >-\n  Use a.\n---\n\n# A\n\n{small}")
        self.repo.write("skills/b/SKILL.md", f"# B\n\n{self.CONDITIONAL}")
        self.repo.commit("add\n")
        for n in range(3):
            self.repo.write("skills/a/x.py", f"x = {n}\n")
            self.repo.commit(f"touch a {n}\n")
        result = self.repo.prose("cost")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Skill descriptions: 6 bytes in 1", result.stdout)
        self.assertEqual(re.findall(r"^ +[0-9,]+ bytes +[0-9,]+ characters  (\S+)", result.stdout,
                                    re.M), ["skills/a/SKILL.md"])
        ranked = re.findall(r"bytes x +(\d+) reads  (\S+):", result.stdout)
        self.assertEqual(ranked, [("4", "skills/a/SKILL.md"), ("1", "skills/b/SKILL.md")])

    def test_prose_cost_lists_descriptions_largest_first(self):
        for name, text in (("a", "Short."), ("b", "A longer description."), ("c", "Mid size.")):
            self.repo.write(f"skills/{name}/SKILL.md", skill(text))
        self.repo.commit("add\n")
        result = self.repo.prose("cost")
        self.assertEqual(re.findall(r"^ +[0-9,]+ bytes +[0-9,]+ characters  (\S+)", result.stdout,
                                    re.M),
                         ["skills/b/SKILL.md", "skills/c/SKILL.md", "skills/a/SKILL.md"])

    def test_prose_cost_with_nothing_to_move(self):
        self.repo.write("README.md", "# R\n")
        self.repo.commit("add\n")
        result = self.repo.prose("cost")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Skill descriptions: 0 bytes in 0", result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith("none"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

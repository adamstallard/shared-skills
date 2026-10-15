#!/usr/bin/env python3
"""Tests for spec_trace.py. Standard library only; each test builds a scratch repository.

Run from the root of the shared-skills clone:  python3 .agents/skills/spec-trace/scripts/test_spec_trace.py
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spec_trace as st  # noqa: E402

CLAIMING = """\
# work-claiming Specification

## Requirements
### Requirement: An Igor claims before it starts

Every pickup SHALL take a claim.

#### Scenario: Claim precedes work

- **WHEN** triage returns proceed
- **THEN** a claim is taken first

#### Scenario: Unclaimed work refused

- **WHEN** a claim cannot be taken
- **THEN** no work is performed
"""

# The tag word is split so this file holds no tag of its own: the default
# globs match test_*.py, so a literal tag here would be read as a real one.
AT = "@" + "scenario"


class Repo(unittest.TestCase):
    """A scratch repository with one capability, work-claiming, and its two scenarios."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.write("openspec/specs/work-claiming/spec.md", CLAIMING)

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(text))

    def read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def run_cmd(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = st.main(["--root", self.root, *args])
        self.err = err.getvalue()
        return code, out.getvalue()

    def tag_both(self):
        self.write("test/claim.test.ts", f"""\
            // {AT} work-claiming: Claim precedes work
            it("claims first", () => {{}});
            // {AT} work-claiming: Unclaimed work refused
            it("refuses", () => {{}});
            """)


class Check(Repo):
    def test_every_scenario_tagged_passes(self):
        self.tag_both()
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)
        self.assertIn("2 of 2 scenarios are tagged", out)

    def test_untagged_scenario_not_in_baseline_fails_with_the_tag_to_add(self):
        self.write("test/claim.test.ts", f"// {AT} work-claiming: Claim precedes work\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("openspec/specs/work-claiming/spec.md:13: no test tags scenario "
                      "'work-claiming: Unclaimed work refused'", out)
        self.assertIn(f"{AT} work-claiming: Unclaimed work refused", out)

    def test_untagged_scenario_in_baseline_passes(self):
        self.write("test/claim.test.ts", f"// {AT} work-claiming: Claim precedes work\n")
        self.write(st.DEFAULT_BASELINE, "work-claiming: Unclaimed work refused\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_baseline_line_now_tagged_fails_and_says_remove_it(self):
        self.tag_both()
        self.write(st.DEFAULT_BASELINE, "# header\nwork-claiming: Unclaimed work refused\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("openspec/spec-trace-baseline.txt:2: 'work-claiming: Unclaimed work refused' "
                      "is now tagged by test/claim.test.ts:3. Remove this line", out)

    def test_baseline_line_naming_no_scenario_fails(self):
        self.tag_both()
        self.write(st.DEFAULT_BASELINE, "work-claiming: Gone\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("'work-claiming: Gone' names no scenario", out)

    def test_orphan_tag_fails_with_file_line_and_a_suggestion(self):
        self.tag_both()
        self.write("test/old.test.ts", f"\n\n// {AT} work-claiming: Claim precedes all work\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("test/old.test.ts:3: tag '@scenario work-claiming: Claim precedes all work' "
                      "names no scenario", out)
        self.assertIn("Did you mean 'Claim precedes work'?", out)

    def test_tag_naming_an_unknown_capability_fails(self):
        self.tag_both()
        self.write("test/x.test.ts", f"// {AT} work-claim: Claim precedes work\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("names no capability", out)
        self.assertIn("Did you mean 'work-claiming'?", out)

    def test_whitespace_differences_still_match(self):
        self.write("openspec/specs/work-claiming/spec.md",
                   CLAIMING.replace("Scenario: Claim precedes work", "Scenario:   Claim  precedes\twork  "))
        self.write("test/claim.test.ts", f"""\
            //   {AT}   work-claiming :  Claim precedes   work
            # {AT} work-claiming: Unclaimed  work refused
            """)
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_several_tags_on_one_test(self):
        self.write("test/claim.test.ts", f"""\
            // {AT} work-claiming: Claim precedes work
            // {AT} work-claiming: Unclaimed work refused
            it("claims", () => {{}});
            """)
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_two_tags_on_one_line(self):
        self.write("test/claim.test.ts",
                   f"// {AT} work-claiming: Claim precedes work {AT} work-claiming: Unclaimed work refused\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_tag_in_a_test_name_ends_at_the_quote(self):
        self.write("test/claim.test.ts", f"""\
            it("claims first {AT} work-claiming: Claim precedes work", () => {{}});
            def test_refuses():  # {AT} work-claiming: Unclaimed work refused
            """)
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_tag_in_a_block_comment_ends_at_the_closer(self):
        self.write("test/claim.test.ts", f"""\
            /* {AT} work-claiming: Claim precedes work */
            <!-- {AT} work-claiming: Unclaimed work refused -->
            """)
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_a_name_with_an_apostrophe_matches_whole(self):
        self.tag_both()
        self.write("openspec/specs/kill/spec.md", "### Requirement: R\n#### Scenario: The worker's tree dies\n")
        self.write("test/kill.test.ts", f"it('kills', () => {{}}); // {AT} kill: The worker's tree dies\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_a_longer_name_is_not_taken_for_a_shorter_one(self):
        # "Claim precedes work" must not match a tag for "Claim precedes work twice".
        self.tag_both()
        self.write("test/x.test.ts", f"// {AT} work-claiming: Claim precedes work twice\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("'@scenario work-claiming: Claim precedes work twice' names no scenario", out)

    def test_a_scenario_covered_by_several_tests_lists_them_all(self):
        self.tag_both()
        self.write("tests/test_more.py", f"# {AT} work-claiming: Claim precedes work\n")
        self.write(st.DEFAULT_BASELINE, "work-claiming: Claim precedes work\n")
        code, out = self.run_cmd("check")
        self.assertIn("is now tagged by test/claim.test.ts:1, tests/test_more.py:1", out)

    def test_scenarios_in_open_changes_are_ignored(self):
        self.tag_both()
        self.write("openspec/changes/add-x/specs/work-claiming/spec.md", """\
            ## ADDED Requirements
            ### Requirement: New
            #### Scenario: Not built yet
            """)
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_a_scenario_in_a_code_fence_is_not_a_scenario(self):
        self.tag_both()
        self.write("openspec/specs/work-claiming/spec.md",
                   CLAIMING + "\n```\n#### Scenario: An example in a fence\n```\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_tags_outside_test_files_are_not_read(self):
        self.tag_both()
        self.write("src/claim.ts", f"// {AT} work-claiming: No such scenario\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_test_globs_can_be_replaced(self):
        self.write("checks/claim.ts", f"""\
            // {AT} work-claiming: Claim precedes work
            // {AT} work-claiming: Unclaimed work refused
            """)
        self.assertEqual(self.run_cmd("check")[0], 1)
        code, out = self.run_cmd("--tests", "checks/**", "check")
        self.assertEqual(code, 0, out)

    def test_node_modules_and_nested_repositories_are_skipped(self):
        self.tag_both()
        self.write("node_modules/pkg/test/x.test.js", f"// {AT} work-claiming: Nope\n")
        self.write(".claude/worktrees/other/.git", "gitdir: elsewhere\n")
        self.write(".claude/worktrees/other/test/x.test.ts", f"// {AT} work-claiming: Nope\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_in_a_git_repository_ignored_files_are_skipped(self):
        self.tag_both()
        self.write(".gitignore", "build/\n")
        self.write("build/test/x.test.js", f"// {AT} work-claiming: Nope\n")
        subprocess.run(["git", "init", "-q", self.root], check=True)
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_no_openspec_specs_is_an_error(self):
        shutil.rmtree(os.path.join(self.root, "openspec"))
        with self.assertRaises(SystemExit) as raised:
            self.run_cmd("check")
        self.assertIn("no openspec/specs", str(raised.exception))


class FoundByTheHunt(Repo):
    """Regression tests for bugs bug-hunter found before spec-trace's first commit."""

    def test_an_escaped_apostrophe_in_a_single_quoted_name_matches(self):
        self.tag_both()
        self.write("openspec/specs/cmd/spec.md", "### Requirement: R\n#### Scenario: A person's command is unchanged\n")
        self.write("test/a.test.ts", f"it('{AT} cmd: A person\\'s command is unchanged', () => {{}});\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_a_bare_repeated_name_in_a_single_quoted_name_is_ambiguous(self):
        self.tag_both()
        self.write("openspec/specs/run/spec.md",
                   "### Requirement: A\n#### Scenario: Ordinary\n### Requirement: B\n#### Scenario: Ordinary\n")
        self.write(st.DEFAULT_BASELINE, "run: A / Ordinary\nrun: B / Ordinary\n")
        self.write("test/a.test.ts", f"it('{AT} run: Ordinary', async () => {{\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("test/a.test.ts:1: tag '@scenario run: Ordinary' is ambiguous", out)

    def test_brace_and_bracket_globs_match(self):
        self.tag_both()
        self.assertEqual(self.run_cmd("--tests", "test/*.{test,spec}.[jt]s", "check")[0], 0)

    def test_globs_that_match_no_file_fail(self):
        self.tag_both()
        code, out = self.run_cmd("--tests", "nowhere/**", "baseline")
        self.assertEqual(code, 2, out)
        self.assertIn("no test files", out)
        self.assertFalse(os.path.exists(os.path.join(self.root, st.DEFAULT_BASELINE)))

    def test_a_repository_with_no_tests_yet_can_still_adopt(self):
        code, out = self.run_cmd("baseline")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_cmd("check")[0], 0)

    def test_a_tag_ending_a_sentence_with_a_period_matches(self):
        self.write("test/claim.test.ts", f"""\
            // Checks this. {AT} work-claiming: Claim precedes work.
            // {AT} work-claiming: Unclaimed work refused
            """)
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_an_empty_section_heading_in_a_change_does_not_crash(self):
        self.write("openspec/changes/ch/specs/work-claiming/spec.md",
                   "## ADDED Requirements\n### Requirement: New\n#### Scenario: Fresh\n\n## \n")
        code, out = self.run_cmd("report", "--include-changes")
        self.assertEqual(code, 0)
        self.assertIn("| Fresh (change: ch) | none |", out)

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_a_file_in_a_merge_conflict_is_read_once(self):
        git = ["git", "-C", self.root, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q", "-b", "main", self.root], check=True)
        self.write("test/a.test.ts", f"// {AT} work-claiming: Claim precedes work\n")
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-qm", "a"], check=True)
        subprocess.run(git + ["checkout", "-qb", "other"], check=True)
        self.write("test/a.test.ts", f"// {AT} work-claiming: Claim precedes work\n// other\n")
        subprocess.run(git + ["commit", "-qam", "b"], check=True)
        subprocess.run(git + ["checkout", "-q", "main"], check=True)
        self.write("test/a.test.ts", f"// {AT} work-claiming: Claim precedes work\n// main\n")
        subprocess.run(git + ["commit", "-qam", "c"], check=True)
        subprocess.run(git + ["merge", "-q", "other"], capture_output=True)
        out = self.run_cmd("report")[1]
        self.assertIn("| Claim precedes work | test/a.test.ts:1 |", out)


class FoundByTheSecondHunt(Repo):
    """Regression tests for bugs found in the fixes from the first hunt."""

    def test_a_bare_repeated_name_is_ambiguous_even_when_a_shorter_name_exists(self):
        self.tag_both()
        self.write("openspec/specs/disc/spec.md",
                   "### Requirement: A\n#### Scenario: Item assigned, on Linear\n"
                   "### Requirement: B\n#### Scenario: Item assigned, on Linear\n"
                   "#### Scenario: Item assigned\n")
        self.write(st.DEFAULT_BASELINE, "disc: A / Item assigned, on Linear\ndisc: B / Item assigned, on Linear\n"
                   "disc: Item assigned\n")
        self.write("test/d.test.ts", f"it('skips {AT} disc: Item assigned, on Linear', () => {{}});\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        self.assertIn("tag '@scenario disc: Item assigned, on Linear' is ambiguous", out)

    def test_a_period_before_a_closing_quote_ends_the_tag(self):
        self.write("tests/test_claim.py", f'''\
            """Taken first. {AT} work-claiming: Claim precedes work."""
            # {AT} work-claiming: Unclaimed work refused
            ''')
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_a_change_that_renames_a_requirement_reports_its_scenario_once(self):
        self.tag_both()
        self.write("openspec/changes/rename-r/specs/work-claiming/spec.md", """\
            ## RENAMED Requirements
            - FROM: `### Requirement: An Igor claims before it starts`
            - TO: `### Requirement: An Igor claims before any work`

            ## MODIFIED Requirements
            ### Requirement: An Igor claims before any work
            #### Scenario: Claim precedes work
            #### Scenario: Unclaimed work refused
            """)
        out = self.run_cmd("report", "--include-changes")[1]
        self.assertIn("2 of 2 scenarios are tagged", out)
        self.assertNotIn("### Problems", out)

    def test_an_unclosed_brace_in_a_glob_is_a_usage_error(self):
        self.tag_both()
        code, out = self.run_cmd("--tests", "test/{a", "check")
        self.assertEqual(code, 2, out)

    def test_an_orphan_in_a_single_quoted_name_is_shown_without_the_rest_of_the_line(self):
        self.tag_both()
        self.write("test/c.test.ts", f"it('claims {AT} work-claiming: Claim precedes all work', async () => {{\n")
        out = self.run_cmd("check")[1]
        self.assertIn("tag '@scenario work-claiming: Claim precedes all work' names no scenario", out)


class FoundByTheThirdHunt(Repo):
    """Regression tests for bugs found in the fixes from the second hunt."""

    def test_a_tag_for_a_scenario_in_an_open_change_is_accepted(self):
        # The implementation lands before the archive, so its tests are tagged first.
        self.tag_both()
        self.write("openspec/changes/add-new/specs/work-claiming/spec.md",
                   "## ADDED Requirements\n### Requirement: N\n#### Scenario: New\n")
        self.write("openspec/changes/add-new/specs/newcap/spec.md",
                   "## ADDED Requirements\n### Requirement: M\n#### Scenario: Fresh\n")
        self.write("test/a.test.ts", f"// {AT} work-claiming: New\n// {AT} newcap: Fresh\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_each_explicit_glob_must_match_a_file(self):
        self.tag_both()
        code, out = self.run_cmd("--tests", "test/**", "--tests", "ee2/**", "baseline")
        self.assertEqual(code, 2, out)
        self.assertIn("ee2/**", out)

    def test_a_fenced_example_in_a_delta_changes_nothing(self):
        self.tag_both()
        fence = "`" * 3
        self.write("openspec/changes/ex/specs/work-claiming/spec.md",
                   "## ADDED Requirements\n### Requirement: Examples are shown\n"
                   f"{fence}markdown\n## REMOVED Requirements\n### Requirement: An Igor claims before it starts\n{fence}\n"
                   "#### Scenario: An example renders\n")
        out = self.run_cmd("report", "--include-changes")[1]
        self.assertIn("| Claim precedes work | test/claim.test.ts:1 |", out)

    def test_an_escaped_double_quote_is_shown_as_written(self):
        self.tag_both()
        self.write("test/b.test.ts", f'it("{AT} work-claiming: Prints \\"done\\" twice", () => {{}});\n')
        out = self.run_cmd("check")[1]
        self.assertIn("""tag '@scenario work-claiming: Prints "done" twice' names no scenario""", out)


class FoundByTheScopedHunt(Repo):
    """Regression tests: tags for open changes' scenarios, ambiguity there, fences, displayed tags."""

    def test_a_tag_for_a_longer_pending_name_is_not_counted_for_a_shorter_main_one(self):
        self.tag_both()
        self.write("openspec/changes/sharpen/specs/work-claiming/spec.md",
                   "## MODIFIED Requirements\n### Requirement: An Igor claims before it starts\n"
                   "#### Scenario: Claim precedes work\n#### Scenario: Claim precedes work, always\n"
                   "#### Scenario: Unclaimed work refused\n")
        self.write("test/b.test.ts", f"// {AT} work-claiming: Claim precedes work, always\n")
        out = self.run_cmd("report")[1]
        self.assertIn("| Claim precedes work | test/claim.test.ts:1 |", out)

    def test_a_bare_name_repeated_in_an_open_change_is_ambiguous(self):
        self.tag_both()
        self.write("openspec/changes/add-two/specs/roles/spec.md",
                   "## ADDED Requirements\n### Requirement: Role names\n#### Scenario: Malformed input rejected\n"
                   "### Requirement: Role permissions\n#### Scenario: Malformed input rejected\n")
        self.write("test/r.test.ts", f"// {AT} roles: Malformed input rejected\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        self.assertIn("is ambiguous", out)

    def test_a_fence_closes_only_with_its_own_character(self):
        self.tag_both()
        tick, tilde = "`" * 3, "~" * 3
        self.write("openspec/changes/doc/specs/work-claiming/spec.md",
                   "## ADDED Requirements\n### Requirement: Examples\n"
                   f"{tilde}markdown\n{tick}python\n## REMOVED Requirements\n"
                   f"### Requirement: An Igor claims before it starts\n{tilde}\n"
                   "#### Scenario: Example shown\n")
        out = self.run_cmd("report", "--include-changes")[1]
        self.assertIn("| Claim precedes work | test/claim.test.ts:1 |", out)
        self.assertIn("| Example shown (change: doc) | none |", out)

    def test_an_unescaped_double_quote_in_a_comment_tag_is_shown(self):
        self.tag_both()
        self.write("test/q.test.ts", f'// {AT} work-claiming: The "quiet" flag hides progress\n')
        out = self.run_cmd("check")[1]
        self.assertIn("""tag '@scenario work-claiming: The "quiet" flag hides progress' names no scenario""", out)

    def test_a_tag_may_use_a_requirement_name_an_open_change_renames_to(self):
        self.tag_both()
        self.write("openspec/changes/ren/specs/work-claiming/spec.md",
                   "## RENAMED Requirements\n- FROM: `### Requirement: An Igor claims before it starts`\n"
                   "- TO: `### Requirement: An Igor claims first`\n")
        self.write("test/n.test.ts", f"// {AT} work-claiming: An Igor claims first / Claim precedes work\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)


class FoundInTheScopedRunsSecondPass(Repo):
    def test_an_orphan_in_a_quoted_name_followed_by_code_is_shown_alone(self):
        self.tag_both()
        self.write("tests/a.rb", f'it "{AT} work-claiming: Clam precedes work" do\n')
        self.write("tests/b.kt", f"fun `{AT} work-claiming: Clam precedes work`() {{\n")
        out = self.run_cmd("check")[1]
        self.assertIn("tests/a.rb:1: tag '@scenario work-claiming: Clam precedes work' names", out)
        self.assertIn("tests/b.kt:1: tag '@scenario work-claiming: Clam precedes work' names", out)


class RepeatedNames(Repo):
    """A scenario name that repeats within a capability is named with its requirement."""

    def setUp(self):
        super().setUp()
        self.write("openspec/specs/task-execution/spec.md", """\
            ### Requirement: Names are text
            #### Scenario: An ordinary run is unaffected
            ### Requirement: No removal is lost
            #### Scenario: An ordinary run is unaffected
            """)
        self.tag_both()

    def test_the_qualified_tags_cover_each(self):
        self.write("test/run.test.ts", f"""\
            // {AT} task-execution: Names are text / An ordinary run is unaffected
            // {AT} task-execution: No removal is lost / An ordinary run is unaffected
            """)
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_a_bare_tag_is_ambiguous_and_lists_the_choices(self):
        self.write("test/run.test.ts", f"// {AT} task-execution: An ordinary run is unaffected\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("test/run.test.ts:1: tag '@scenario task-execution: An ordinary run is unaffected' "
                      "is ambiguous", out)
        self.assertIn(f"{AT} task-execution: No removal is lost / An ordinary run is unaffected", out)

    def test_the_baseline_names_each_by_its_requirement(self):
        code, out = self.run_cmd("baseline")
        self.assertEqual(code, 0, out)
        self.assertIn("task-execution: Names are text / An ordinary run is unaffected\n",
                      self.read(st.DEFAULT_BASELINE))
        self.assertEqual(self.run_cmd("check")[0], 0)

    def test_a_qualified_tag_works_for_a_unique_name_too(self):
        self.write("test/claim.test.ts", f"""\
            // {AT} work-claiming: An Igor claims before it starts / Claim precedes work
            // {AT} work-claiming: Unclaimed work refused
            """)
        self.write("test/run.test.ts", f"""\
            // {AT} task-execution: Names are text / An ordinary run is unaffected
            // {AT} task-execution: No removal is lost / An ordinary run is unaffected
            """)
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_the_same_name_under_the_same_requirement_fails(self):
        self.write("openspec/specs/task-execution/spec.md", """\
            ### Requirement: Names are text
            #### Scenario: Twice
            #### Scenario: Twice
            """)
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("no tag can tell them apart. Rename one of them", out)


class Baseline(Repo):
    def test_writes_untagged_scenarios_sorted_and_check_then_passes(self):
        self.write("openspec/specs/alpha/spec.md", "### Requirement: R\n#### Scenario: Zed\n#### Scenario: Ay\n")
        self.write("test/claim.test.ts", f"// {AT} work-claiming: Claim precedes work\n")
        code, out = self.run_cmd("baseline")
        self.assertEqual(code, 0, out)
        lines = [l for l in self.read(st.DEFAULT_BASELINE).splitlines() if not l.startswith("#")]
        self.assertEqual(lines, ["alpha: Ay", "alpha: Zed", "work-claiming: Unclaimed work refused"])
        self.assertIn("wrote 3 untagged scenario(s) of 4", out)
        self.assertEqual(self.run_cmd("check")[0], 0)

    def test_baseline_path_is_configurable(self):
        code, _ = self.run_cmd("--baseline", "trace.txt", "baseline")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "trace.txt")))
        self.assertEqual(self.run_cmd("--baseline", "trace.txt", "check")[0], 0)


class Report(Repo):
    def test_a_table_per_capability_with_file_and_line(self):
        self.write("test/claim.test.ts", f"\n// {AT} work-claiming: Claim precedes work\n")
        code, out = self.run_cmd("report")
        self.assertEqual(code, 0)
        self.assertIn("1 of 2 scenarios are tagged by a test.", out)
        self.assertIn("### work-claiming (1 of 2 tagged)", out)
        self.assertIn("| Scenario | Tests |", out)
        self.assertIn("| Claim precedes work | test/claim.test.ts:2 |", out)
        self.assertIn("| Unclaimed work refused | none |", out)

    def test_open_changes_are_listed_only_when_asked(self):
        self.write("openspec/changes/add-x/specs/work-claiming/spec.md", """\
            ## ADDED Requirements
            ### Requirement: New
            #### Scenario: Not built yet
            ## REMOVED Requirements
            ### Requirement: Old
            #### Scenario: Going away
            """)
        self.write("openspec/changes/archive/old/specs/work-claiming/spec.md",
                   "### Requirement: A\n#### Scenario: Archived\n")
        self.assertNotIn("Not built yet", self.run_cmd("report")[1])
        out = self.run_cmd("report", "--include-changes")[1]
        self.assertIn("| Not built yet (change: add-x) | none |", out)
        self.assertNotIn("Going away", out)
        self.assertNotIn("Archived", out)

    def test_problems_are_listed_after_the_tables(self):
        self.write("test/x.test.ts", f"// {AT} work-claiming: Nope\n")
        out = self.run_cmd("report")[1]
        self.assertIn("### Problems", out)
        self.assertIn("- test/x.test.ts:1: tag", out)


class Detection(Repo):
    """Test globs come from the repository's test runner configuration when --tests is not given."""

    def files(self):
        found = st.detect_tests(self.root)
        self.troubles = found.troubles
        return found.sources, st.detected_files(self.root, found)

    def test_vitest_include(self):
        self.write("vitest.config.ts", """\
            export default defineConfig({
              test: {
                include: ['checks/**/*.check.ts'],  // where the tests live
                coverage: { include: ['src/**'] },
              },
            })
            """)
        self.write("checks/a.check.ts", "")
        self.write("test/b.test.ts", "")
        sources, files = self.files()
        self.assertEqual(sources, ["vitest.config.ts (test.include)"])
        self.assertEqual(files, ["checks/a.check.ts"])

    def test_vitest_default_include_and_its_exclude(self):
        self.write("vitest.config.ts", "export default defineConfig({ test: { exclude: ['old/**'] } })\n")
        for f in ("test/a.test.ts", "src/b.spec.mjs", "old/c.test.ts", "test/helpers.ts"):
            self.write(f, "")
        sources, files = self.files()
        self.assertEqual(sources, ["vitest.config.ts (Vitest's default include)"])
        self.assertEqual(files, ["src/b.spec.mjs", "test/a.test.ts"])

    def test_a_computed_vitest_include_falls_back_to_the_defaults(self):
        self.write("vitest.config.ts", "export default defineConfig({ test: { include: dirs.map(d => d + '/**') } })\n")
        sources, _ = self.files()
        self.assertEqual(sources, ["the defaults"])
        self.assertIn("vitest.config.ts: could not read test.include", self.troubles[0])

    def test_a_vite_config_without_test_settings_says_nothing(self):
        self.write("vite.config.js", "export default { build: { outDir: 'dist' } }\n")
        self.assertEqual(self.files()[0], ["the defaults, since no test runner configuration was found"])
        self.assertEqual(self.troubles, [])

    def test_jest_test_match_in_a_config_file(self):
        self.write("jest.config.js", "module.exports = { testMatch: ['<rootDir>/spec/**/*.js'] }\n")
        self.write("spec/a.js", "")
        self.write("test/b.test.js", "")
        sources, files = self.files()
        self.assertEqual(sources, ["jest.config.js (testMatch)"])
        self.assertEqual(files, ["spec/a.js"])

    def test_jest_default_test_match_from_package_json(self):
        self.write("package.json", '{"name": "x", "jest": {"verbose": true}}\n')
        for f in ("src/__tests__/a.js", "src/b.test.tsx", "src/c.js"):
            self.write(f, "")
        sources, files = self.files()
        self.assertEqual(sources, ["package.json (Jest's default testMatch)"])
        self.assertEqual(files, ["src/__tests__/a.js", "src/b.test.tsx"])

    def test_jest_test_regex(self):
        self.write("package.json", '{"jest": {"testRegex": "/specs/.*\\\\.js$"}}\n')
        self.write("specs/a.js", "")
        self.write("test/b.test.js", "")
        self.assertEqual(self.files()[1], ["specs/a.js"])

    def test_jest_test_regex_string_in_a_config_file(self):
        self.write("jest.config.js", "module.exports = {\n  'testRegex': '/specs/.*\\\\.js$',\n}\n")
        self.write("specs/a.js", "")
        self.write("test/b.test.js", "")
        self.assertEqual(self.files(), (["jest.config.js (testRegex)"], ["specs/a.js"]))

    def test_pytest_ini(self):
        self.write("pytest.ini", "[pytest]\ntestpaths = checks\npython_files = check_*.py\n")
        self.write("checks/check_a.py", "")
        self.write("tests/test_b.py", "")
        sources, files = self.files()
        self.assertEqual(sources, ["pytest.ini (pytest testpaths and python_files)"])
        self.assertEqual(files, ["checks/check_a.py"])

    def test_pytest_in_pyproject_and_setup_cfg(self):
        self.write("pyproject.toml", '[tool.pytest.ini_options]\ntestpaths = ["suite"]\n')
        self.write("suite/test_a.py", "")
        self.write("suite/deep/b_test.py", "")
        self.write("other/test_c.py", "")
        self.assertEqual(self.files()[1], ["suite/deep/b_test.py", "suite/test_a.py"])
        os.remove(os.path.join(self.root, "pyproject.toml"))
        self.write("setup.cfg", "[tool:pytest]\npython_files = check_*.py\n")
        self.write("x/check_d.py", "")
        self.assertEqual(self.files()[1], ["x/check_d.py"])

    def test_go(self):
        self.write("go.mod", "module x\n")
        self.write("pkg/a_test.go", "")
        self.write("pkg/a.go", "")
        self.assertEqual(self.files(), (["go.mod (Go's *_test.go)"], ["pkg/a_test.go"]))

    def test_rust(self):
        self.write("Cargo.toml", "[package]\n")
        self.write("src/lib.rs", "")
        self.write("tests/it.rs", "")
        self.write("build.rs", "")
        self.assertEqual(self.files()[1], ["src/lib.rs", "tests/it.rs"])

    def test_no_runner_configuration_falls_back_to_the_defaults(self):
        self.tag_both()
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)
        self.assertIn("test files from the defaults, since no test runner configuration was found", self.err)

    def test_the_source_is_printed_and_tests_overrides_detection(self):
        self.write("go.mod", "module x\n")
        self.write("checks/claim.ts", f"// {AT} work-claiming: Claim precedes work\n// {AT} work-claiming: Unclaimed work refused\n")
        self.assertEqual(self.run_cmd("check")[0], 1)
        self.assertIn("test files from go.mod (Go's *_test.go)", self.err)
        code, out = self.run_cmd("--tests", "checks/**", "check")
        self.assertEqual(code, 0, out)
        self.assertIn("test files from --tests", self.err)


class Trouble(Repo):
    """A config spec-trace cannot read with confidence is reported, and never guessed at silently."""

    def trouble(self, *args):
        code, out = self.run_cmd(*args)
        return code, out, self.err

    def test_a_regex_literal_makes_the_vitest_config_unreadable_and_pytest_still_counts(self):
        self.write("vite.config.ts", "export default { server: { proxy: { '/api': { rewrite: (p) => "
                   "p.replace(/^\\/api\\//, '/') } } }, test: { include: ['src/**/*.unit.ts'] } }\n")
        self.write("pytest.ini", "[pytest]\ntestpaths = checks\n")
        self.write("checks/test_claim.py", f"# {AT} work-claiming: Claim precedes work\n"
                   f"# {AT} work-claiming: Unclaimed work refused\n")
        code, out, err = self.trouble("check")
        self.assertEqual(code, 0, out + err)
        self.assertIn("vite.config.ts: could not read", err)
        self.assertIn("checks/**/test_*.py", err)
        self.assertIn("openspec/spec-trace-tests.txt", err)

    def test_a_comment_with_an_apostrophe_inside_the_include_list_is_read(self):
        self.write("vitest.config.ts", "export default {\n  test: {\n    include: [\n"
                   "      'src/**/*.unit.ts', // don't add e2e here\n    ],\n  },\n}\n")
        self.write("src/a.unit.ts", "")
        self.assertEqual(Detection.files(self), (["vitest.config.ts (test.include)"], ["src/a.unit.ts"]))
        self.assertEqual(self.troubles, [])

    def test_a_shorthand_include_is_trouble(self):
        self.write("vitest.config.ts", "const include = ['src/**']\nexport default { test: { include } }\n")
        Detection.files(self)
        self.assertIn("vitest.config.ts: could not read test.include", self.troubles[0])

    def test_vitest_projects_are_trouble(self):
        self.write("vitest.config.ts", "export default { test: { projects: [{ test: { include: ['a/**'] } }] } }\n")
        Detection.files(self)
        self.assertIn("vitest.config.ts: could not read test.projects", self.troubles[0])

    def test_a_negated_jest_test_match_entry_is_trouble(self):
        self.write("jest.config.js", "module.exports = { testMatch: ['**/src/**/*.check.js', '!**/fixtures/**'] }\n")
        Detection.files(self)
        self.assertIn("jest.config.js: could not read testMatch", self.troubles[0])

    def test_pyproject_without_tomllib_is_trouble(self):
        self.write("pyproject.toml", '[tool.pytest.ini_options]\npython_files = "check_*.py test_*.py"\n')
        with mock.patch.dict(sys.modules, {"tomllib": None}):
            Detection.files(self)
        self.assertIn("pyproject.toml: could not read", self.troubles[0])

    def test_pytest_reads_its_config_files_in_pytests_order(self):
        self.write(".pytest.ini", "[pytest]\npython_files = dot_*.py\n")
        self.write("pyproject.toml", '[tool.pytest.ini_options]\npython_files = ["py_*.py"]\n')
        self.write("tox.ini", "[pytest]\npython_files = tox_*.py\n")
        self.assertEqual(Detection.files(self)[0], [".pytest.ini (pytest testpaths and python_files)"])
        os.remove(os.path.join(self.root, ".pytest.ini"))
        self.assertEqual(Detection.files(self)[0], ["pyproject.toml (pytest testpaths and python_files)"])

    def test_baseline_refuses_to_write_while_detection_reports_trouble(self):
        self.write("vitest.config.ts", "export default { test: { include: dirs } }\n")
        code, out, err = self.trouble("baseline")
        self.assertEqual(code, 2, out + err)
        self.assertIn("vitest.config.ts: could not read test.include", out)
        self.assertFalse(os.path.exists(os.path.join(self.root, st.DEFAULT_BASELINE)))
        self.tag_both()
        self.write(st.TESTS_FILE, "test/**\n")
        self.assertEqual(self.trouble("baseline")[0], 0)

    def test_a_bad_detected_glob_does_not_crash(self):
        self.tag_both()
        self.write("vitest.config.ts", "export default { test: { include: ['src/**/!(*.e2e).test.ts'] } }\n")
        code, out, err = self.trouble("check")
        self.assertEqual(code, 0, out + err)
        self.assertIn("vitest.config.ts: could not read test.include", err)

    def test_a_name_ending_in_a_parenthesis_is_shown_whole(self):
        self.tag_both()
        self.write("test/r.test.ts", f"it('{AT} work-claiming: Run (fast)', () => {{}})\n")
        self.assertIn("tag '@scenario work-claiming: Run (fast)' names no scenario", self.run_cmd("check")[1])


class FoundByTheDetectionHunt(Repo):
    """Regression tests: detection must never silently miss a tagged test, nor crash."""

    def setUp(self):
        super().setUp()
        self.write("openspec/specs/work-claiming/spec.md", "### Requirement: R\n#### Scenario: Claim precedes work\n")

    def baseline_must_not_exempt(self, tagged):
        self.write(tagged, f"// {AT} work-claiming: Claim precedes work\n")
        code, out = self.run_cmd("baseline")
        written = os.path.exists(os.path.join(self.root, st.DEFAULT_BASELINE)) and \
            "work-claiming: Claim precedes work" in self.read(st.DEFAULT_BASELINE)
        self.assertFalse(written, out + self.err)

    def test_a_runner_config_below_the_root_is_reported(self):
        self.write("pyproject.toml", '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
        self.write("web/vitest.config.ts", "export default { test: { include: ['src/**/*.test.ts'] } }\n")
        self.baseline_must_not_exempt("web/src/a.test.ts")

    def test_a_go_module_below_the_root_is_read(self):
        self.write("svc/go.mod", "module x\n")
        self.write("svc/a_test.go", f"// {AT} work-claiming: Claim precedes work\n")
        self.assertEqual(self.run_cmd("check")[0], 0, self.err)

    def test_one_runners_exclude_does_not_hide_another_runners_tests(self):
        self.write("vitest.config.ts", "export default { test: { exclude: ['backend/**'] } }\n")
        self.write("pytest.ini", "[pytest]\ntestpaths = backend/tests\n")
        self.baseline_must_not_exempt("backend/tests/test_a.py")

    def test_a_test_setting_that_is_not_an_object_literal_is_reported(self):
        self.write("vitest.config.ts", "const test = { include: ['src/**/*.check.ts'] }\n"
                   "export default defineConfig({ plugins: [react()], test })\n")
        self.baseline_must_not_exempt("src/a.check.ts")
        os.remove(os.path.join(self.root, "vitest.config.ts"))
        self.write("vitest.config.ts", "export default { test: ci ? { include: ['a/**'] } : { include: ['src/**/*.check.ts'] } }\n")
        self.baseline_must_not_exempt("src/a.check.ts")

    def test_vitest_in_source_tests_are_reported(self):
        self.write("vitest.config.ts", "export default { test: { includeSource: ['src/**/*.ts'] } }\n")
        self.baseline_must_not_exempt("src/add.ts")

    def test_jest_projects_are_reported(self):
        self.write("jest.config.js", "module.exports = { projects: [{ testMatch: ['<rootDir>/src/**/*.unit.js'] }] }\n")
        self.baseline_must_not_exempt("src/a.unit.js")

    def test_a_base_directory_is_reported(self):
        self.write("vitest.config.ts", "export default { root: 'app', test: { include: ['tests/**/*.ts'] } }\n")
        self.baseline_must_not_exempt("app/tests/a.ts")

    def test_pytest_testpaths_with_a_leading_dot(self):
        self.write("pytest.ini", "[pytest]\ntestpaths = ./tests\n")
        self.write("tests/test_a.py", f"# {AT} work-claiming: Claim precedes work\n")
        self.assertEqual(self.run_cmd("check")[0], 0, self.err)

    def test_pytest_toml_and_the_native_pytest_table_are_reported(self):
        self.write("pytest.toml", '[pytest]\ntestpaths = ["checks"]\n')
        self.write("pyproject.toml", '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
        self.baseline_must_not_exempt("checks/check_a.py")
        os.remove(os.path.join(self.root, "pytest.toml"))
        self.write("pyproject.toml", '[tool.pytest]\npython_files = ["check_*.py"]\n')
        self.write("go.mod", "module x\n")
        self.baseline_must_not_exempt("src/pkg/check_a.py")

    def test_jest_30_default_test_match_takes_mjs(self):
        self.write("package.json", '{"jest": {"testEnvironment": "node"}}\n')
        self.write("src/a.test.mjs", f"// {AT} work-claiming: Claim precedes work\n")
        self.assertEqual(self.run_cmd("check")[0], 0, self.err)

    def test_broken_configs_never_crash(self):
        cases = [
            ("vitest.config.ts", "export default { test: { include: ['src/**/*.[t-j]s'] } }\n".encode()),
            ("pytest.ini", b"[pytest]\npython_files = test_[z-a]*.py\n"),
            ("setup.cfg", "[metadata]\nauthor = J\u00fcrgen\n".encode("latin-1")),
            ("pyproject.toml", "[project]\nname = 'J\u00fcrgen'\n".encode("latin-1")),
            ("jest.config.json", b"[]\n"),
            (st.TESTS_FILE, "# caf\u00e9\ntest/**\n".encode("latin-1")),
        ]
        self.write("test/a.test.ts", f"// {AT} work-claiming: Claim precedes work\n")
        for name, data in cases:
            path = os.path.join(self.root, name)
            with open(path, "wb") as f:
                f.write(data)
            for command in ("check", "report", "baseline"):
                code, out = self.run_cmd(command)
                self.assertIn(code, (0, 1, 2), f"{name} {command}: {out}{self.err}")
            os.remove(path)


class TestsFile(Repo):
    """openspec/spec-trace-tests.txt sets the test globs by hand, in place of detection."""

    def test_it_replaces_detection_and_tests_wins_over_it(self):
        self.write("go.mod", "module x\n")
        self.write("checks/claim.ts", f"// {AT} work-claiming: Claim precedes work\n// {AT} work-claiming: Unclaimed work refused\n")
        self.write("checks/fixtures/old.ts", f"// {AT} work-claiming: Gone\n")
        self.write(st.TESTS_FILE, "# where the tests live\nchecks/**\n!checks/fixtures/**\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)
        self.assertIn(f"test files from {st.TESTS_FILE}", self.err)
        code, out = self.run_cmd("--tests", "test/**", "check")
        self.assertEqual(code, 2)
        self.assertIn("test files from --tests", self.err)

    def test_a_glob_in_it_that_matches_nothing_stops_the_command(self):
        self.tag_both()
        self.write(st.TESTS_FILE, "test/**\nee2/**\n")
        code, out = self.run_cmd("baseline")
        self.assertEqual(code, 2)
        self.assertIn("ee2/**", out)


class Globs(unittest.TestCase):
    def test_defaults_match_common_layouts(self):
        patterns = [st.glob_to_regex(g) for g in st.DEFAULT_TESTS]
        hit = lambda p: any(r.match(p) for r in patterns)  # noqa: E731
        for path in ["test/a.ts", "pkg/tests/b.py", "src/__tests__/c.js", "x_test.go",
                     "src/a.test.ts", "src/a.spec.js", "test_x.py", "deep/test_y.py"]:
            self.assertTrue(hit(path), path)
        for path in ["src/a.ts", "openspec/specs/x/spec.md", "contest/a.ts", "latest.py"]:
            self.assertFalse(hit(path), path)

    def test_extglobs(self):
        r = st.glob_to_regex("**/?(*.)+(spec|test).[jt]s?(x)")
        for path in ["a.test.js", "src/a.spec.tsx", "src/test.ts"]:
            self.assertTrue(r.match(path), path)
        for path in ["src/a.js", "src/a.test.jsxx"]:
            self.assertFalse(r.match(path), path)
        with self.assertRaises(ValueError):
            st.glob_to_regex("!(a)")



HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "scenario_hook.py")
CLONE = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
CONFIG_TEXT = "schema: spec-driven\n\n# Project context (optional)\n#   context: |\n"


class GitRepo(Repo):
    """A Repo that is a git repository and has an openspec/config.yaml."""

    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q", self.root], check=True)
        self.write("openspec/config.yaml", CONFIG_TEXT)


class AdoptionState(GitRepo):
    def state(self):
        return st.adoption_state(self.root)

    def test_no_openspec_directory_is_none(self):
        shutil.rmtree(os.path.join(self.root, "openspec"))
        self.assertIsNone(self.state())
        self.assertEqual(self.run_cmd("state"), (0, "n/a\n"))

    def test_neither_baseline_nor_marker_is_undecided(self):
        self.assertEqual(self.state(), st.UNDECIDED)
        self.assertEqual(self.run_cmd("state"), (0, "undecided\n"))

    def test_no_config_is_undecided(self):
        os.remove(os.path.join(self.root, "openspec/config.yaml"))
        self.assertEqual(self.state(), st.UNDECIDED)

    def test_the_baseline_file_is_adopted(self):
        self.write("openspec/spec-trace-baseline.txt", "# none\n")
        self.assertEqual(self.state(), st.ADOPTED)

    def test_a_moved_baseline_is_adopted(self):
        self.write("ci/baseline.txt", "")
        self.assertEqual(self.run_cmd("--baseline", "ci/baseline.txt", "state"), (0, "adopted\n"))

    def test_a_workflow_that_runs_the_checker_is_adopted_without_a_baseline(self):
        self.write(".github/workflows/trace.yml", "run: python3 spec_trace.py check\n")
        self.assertEqual(self.state(), st.ADOPTED)

    def test_a_workflow_that_does_not_run_it_is_not(self):
        self.write(".github/workflows/ci.yml", "run: npm test\n")
        self.write(".github/workflows/notes.txt", "spec_trace.py\n")
        self.assertEqual(self.state(), st.UNDECIDED)

    def test_the_hand_set_globs_file_is_adopted(self):
        self.write(st.TESTS_FILE, "test/**\n")
        self.assertEqual(self.state(), st.ADOPTED)

    def test_the_marker_is_declined(self):
        self.write("openspec/config.yaml", CONFIG_TEXT + "  # spec-trace: declined  \n")
        self.assertEqual(self.state(), st.DECLINED)

    def test_the_marker_inside_a_line_is_not_declined(self):
        self.write("openspec/config.yaml", CONFIG_TEXT + "# not # spec-trace: declined\n"
                   "# spec-trace: declined, maybe\n# spec-check: decisions first declined\n")
        self.assertEqual(self.state(), st.UNDECIDED)

    def test_adoption_wins_over_a_marker_left_behind(self):
        self.write("openspec/config.yaml", CONFIG_TEXT + st.DECLINE_MARKER + "\n")
        self.write("openspec/spec-trace-baseline.txt", "")
        self.assertEqual(self.state(), st.ADOPTED)


class Decline(GitRepo):
    def test_appends_the_marker_and_keeps_every_other_line(self):
        code, out = self.run_cmd("decline")
        self.assertEqual(code, 0)
        self.assertIn("Commit it", out)
        self.assertEqual(self.read("openspec/config.yaml"), CONFIG_TEXT + "# spec-trace: declined\n")
        self.assertEqual(st.adoption_state(self.root), st.DECLINED)

    def test_is_idempotent(self):
        self.run_cmd("decline")
        code, out = self.run_cmd("decline")
        self.assertEqual(code, 0)
        self.assertIn("already declines", out)
        self.assertEqual(self.read("openspec/config.yaml").count(st.DECLINE_MARKER), 1)

    def test_dry_run_prints_the_new_config_and_changes_nothing(self):
        code, out = self.run_cmd("decline", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(out, CONFIG_TEXT + "# spec-trace: declined\n")
        self.assertEqual(self.read("openspec/config.yaml"), CONFIG_TEXT)

    def binary(self, data):
        path = os.path.join(self.root, "openspec/config.yaml")
        with open(path, "wb") as f:
            f.write(data)
        self.run_cmd("decline")
        with open(path, "rb") as f:
            return f.read()

    def test_keeps_crlf_line_endings_and_uses_them(self):
        self.assertEqual(self.binary(b"schema: spec-driven\r\n# note\r\n"),
                         b"schema: spec-driven\r\n# note\r\n# spec-trace: declined\r\n")

    def test_ends_an_unterminated_last_line_first(self):
        self.assertEqual(self.binary(b"schema: spec-driven\n# last"),
                         b"schema: spec-driven\n# last\n# spec-trace: declined\n")

    def test_missing_config_is_refused_and_not_created(self):
        os.remove(os.path.join(self.root, "openspec/config.yaml"))
        code, out = self.run_cmd("decline")
        self.assertEqual(code, 2)
        self.assertIn("openspec init", out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "openspec/config.yaml")))

    def test_an_adopted_repository_is_refused(self):
        self.write("openspec/spec-trace-baseline.txt", "")
        code, out = self.run_cmd("decline")
        self.assertEqual(code, 1)
        self.assertIn("nothing was declined", out)
        self.assertEqual(self.read("openspec/config.yaml"), CONFIG_TEXT)

    def test_no_openspec_directory_is_refused(self):
        shutil.rmtree(os.path.join(self.root, "openspec"))
        self.assertEqual(self.run_cmd("decline")[0], 2)

    def test_a_config_that_is_not_utf8_keeps_its_bytes(self):
        self.assertEqual(self.binary(b"schema: spec-driven\n# caf\xe9 notes\n"),
                         b"schema: spec-driven\n# caf\xe9 notes\n# spec-trace: declined\n")

    def test_runs_without_reading_test_configuration(self):
        self.write("vitest.config.ts", "export default { test: { include: [x] } }\n")
        code, _ = self.run_cmd("decline")
        self.assertEqual(code, 0)
        self.assertEqual(self.err, "")


class NestedOpenSpec(GitRepo):
    """openspec/ only below the top of the repository, as in a monorepo. The
    repository is its git top level, which has no openspec/, so the hook says nothing."""

    def setUp(self):
        super().setUp()
        os.rename(os.path.join(self.root, "openspec"), os.path.join(self.root, "pkg-openspec"))
        os.makedirs(os.path.join(self.root, "pkg"))
        os.rename(os.path.join(self.root, "pkg-openspec"), os.path.join(self.root, "pkg/openspec"))

    def test_a_spec_below_the_top_of_the_repository_is_silent(self):
        spec = os.path.join(self.root, "pkg/openspec/specs/work-claiming/spec.md")
        out = subprocess.run([sys.executable, HOOK, "--host", "claude"], capture_output=True,
                             text=True, timeout=30,
                             input=json.dumps({"tool_input": {"file_path": spec}})).stdout
        self.assertEqual(out, "")


class WhichOpenSpecCounts(GitRepo):
    """The repository is its git top level. An openspec/ folder below the top is
    not asked about, and a workflow counts only for its own root and only when
    it runs spec_trace.py itself."""

    def hook(self, rel):
        payload = {"cwd": self.root, "tool_input": {"file_path": rel}}
        return subprocess.run([sys.executable, HOOK, "--host", "claude"], capture_output=True,
                              text=True, timeout=30, input=json.dumps(payload)).stdout

    def test_a_declined_repository_is_not_asked_about_a_fixture_spec(self):
        self.run_cmd("decline")
        self.write("test/fixtures/openspec/specs/y/spec.md", CLAIMING)
        self.assertEqual(self.hook("test/fixtures/openspec/specs/y/spec.md"), "")

    def test_a_workflow_for_one_project_does_not_adopt_another(self):
        self.write(".github/workflows/ci.yml", "run: python3 tools/spec_trace.py --root a check\n")
        self.write("b/openspec/config.yaml", CONFIG_TEXT)
        self.assertEqual(self.run_cmd("--root", os.path.join(self.root, "b"), "state")[1], "undecided\n")

    def test_running_the_checker_s_own_tests_is_not_adoption(self):
        self.write(".github/workflows/skills.yml",
                   "run: python3 .agents/skills/spec-trace/scripts/test_spec_trace.py\n")
        self.assertEqual(st.adoption_state(self.root), st.UNDECIDED)


class HookPaths(unittest.TestCase):
    """The spec's path names the top's own openspec/, however the path is spelled."""

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base)

    def repo(self, name, openspec="openspec"):
        root = os.path.join(self.base, name)
        os.makedirs(os.path.join(root, openspec, "specs/cap"))
        with open(os.path.join(root, openspec, "config.yaml"), "w", encoding="utf-8") as f:
            f.write(CONFIG_TEXT)
        subprocess.run(["git", "init", "-q", root], check=True)
        return root

    def asks(self, path):
        out = subprocess.run([sys.executable, HOOK, "--host", "claude"], capture_output=True,
                             text=True, timeout=30,
                             input=json.dumps({"tool_input": {"file_path": path}})).stdout
        return "hasn't decided on spec-trace" in out

    def test_an_openspec_folder_that_is_a_link_is_the_top_s_own(self):
        root = self.repo("sym", openspec="docs/openspec")
        os.symlink("docs/openspec", os.path.join(root, "openspec"))
        self.assertTrue(self.asks(os.path.join(root, "openspec/specs/cap/spec.md")))

    def test_a_top_whose_name_ends_in_a_space(self):
        root = self.repo("sp ")
        self.assertTrue(self.asks(os.path.join(root, "openspec/specs/cap/spec.md")))


class Hook(GitRepo):
    def hook(self, payload, host="claude"):
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        result = subprocess.run([sys.executable, HOOK, "--host", host], input=raw,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def spec(self, rel="openspec/specs/work-claiming/spec.md"):
        return os.path.join(self.root, rel)

    def test_claude_gets_context_for_a_main_spec_in_an_undecided_repository(self):
        out = self.hook({"tool_name": "Write", "tool_input": {"file_path": self.spec()}})
        context = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(context["hookEventName"], "PostToolUse")
        self.assertIn("hasn't decided on spec-trace", context["additionalContext"])
        self.assertIn(f"spec_trace.py --root {self.root} decline", context["additionalContext"])

    def test_cursor_gets_context_for_a_spec_in_an_open_change(self):
        path = self.spec("openspec/changes/add-x/specs/work-claiming/spec.md")
        for payload in ({"tool_name": "Write", "tool_input": {"file_path": path}},
                        {"tool_name": "Write", "tool_input": {"path": path}},
                        {"file_path": path, "edits": []},
                        {"tool_input": {"path": "openspec/changes/add-x/specs/a/b/spec.md"},
                         "cwd": self.root}):
            out = self.hook(payload, host="cursor")
            self.assertIn("hasn't decided on spec-trace", json.loads(out)["additional_context"], payload)

    def test_adopted_and_declined_repositories_are_silent(self):
        payload = {"tool_input": {"file_path": self.spec()}}
        self.write("openspec/spec-trace-baseline.txt", "")
        self.assertEqual(self.hook(payload), "")
        os.remove(os.path.join(self.root, "openspec/spec-trace-baseline.txt"))
        self.run_cmd("decline")
        self.assertEqual(self.hook(payload), "")
        self.assertEqual(self.hook(payload, host="cursor"), "")

    def test_other_files_are_silent(self):
        for rel in ("openspec/changes/add-x/proposal.md", "openspec/specs/spec.md",
                    "openspec/changes/archive/2025-01-01-x/specs/work-claiming/spec.md",
                    "docs/specs/a/spec.md", "openspec/specs/a/spec.md.bak"):
            self.assertEqual(self.hook({"tool_input": {"file_path": self.spec(rel)}}), "", rel)

    def test_a_directory_that_is_not_a_git_repository_is_silent(self):
        shutil.rmtree(os.path.join(self.root, ".git"))
        self.assertEqual(self.hook({"tool_input": {"file_path": self.spec()}}), "")

    def test_bad_payloads_are_silent(self):
        for raw in ("", "not json spec.md", "[\"spec.md\"]", "{\"tool_input\": \"spec.md\"}",
                    json.dumps({"tool_input": {"file_path": 7}, "x": "spec.md"}),
                    json.dumps({"tool_input": {"file_path": "openspec/specs/a/spec.md"}})):
            self.assertEqual(self.hook(raw), "", raw)

    def test_an_unknown_host_gets_the_message_on_stderr(self):
        result = subprocess.run([sys.executable, HOOK], capture_output=True, text=True, timeout=30,
                                input=json.dumps({"tool_input": {"file_path": self.spec()}}))
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        self.assertIn("hasn't decided on spec-trace", result.stderr)


class HookWiring(unittest.TestCase):
    """manage-skills wires hook.json, in a sandbox that never touches real configs."""

    def test_install_wires_the_hook_for_both_hosts(self):
        sandbox = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, sandbox)
        home = os.path.join(sandbox, "home")
        env = dict(os.environ, SHARED_SKILLS_REPO=CLONE,
                   SHARED_SKILLS_TARGET=os.path.join(sandbox, "skills"),
                   SHARED_SKILLS_CONFIG=os.path.join(sandbox, "config.json"),
                   SHARED_SKILLS_HOOK_HOME=home)
        manager = os.path.join(CLONE, ".agents/skills/manage-skills/scripts/skills.py")
        result = subprocess.run([sys.executable, manager, "install", "spec-trace"], env=env,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with open(os.path.join(home, ".claude/settings.json"), encoding="utf-8") as f:
            claude = json.loads(f.read())["hooks"]["PostToolUse"]
        with open(os.path.join(home, ".cursor/hooks.json"), encoding="utf-8") as f:
            cursor = json.loads(f.read())["hooks"]["postToolUse"]
        script = os.path.realpath(HOOK)
        self.assertEqual([(e["matcher"], h["command"]) for e in claude for h in e["hooks"]],
                         [("^(Write|Edit|MultiEdit)$", f"{script} --host claude")])
        self.assertEqual([(e.get("matcher"), e["command"]) for e in cursor],
                         [("Write", f"{script} --host cursor")])


if __name__ == "__main__":
    unittest.main()

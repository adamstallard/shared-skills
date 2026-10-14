#!/usr/bin/env python3
"""Tests for spec_trace.py. Standard library only; each test builds a scratch repository.

Run from the root of the shared-skills clone:  python3 .agents/skills/spec-trace/scripts/test_spec_trace.py
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
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
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = st.main(["--root", self.root, *args])
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


class Globs(unittest.TestCase):
    def test_defaults_match_common_layouts(self):
        patterns = [st.glob_to_regex(g) for g in st.DEFAULT_TESTS]
        hit = lambda p: any(r.match(p) for r in patterns)  # noqa: E731
        for path in ["test/a.ts", "pkg/tests/b.py", "src/__tests__/c.js", "x_test.go",
                     "src/a.test.ts", "src/a.spec.js", "test_x.py", "deep/test_y.py"]:
            self.assertTrue(hit(path), path)
        for path in ["src/a.ts", "openspec/specs/x/spec.md", "contest/a.ts", "latest.py"]:
            self.assertFalse(hit(path), path)


if __name__ == "__main__":
    unittest.main()

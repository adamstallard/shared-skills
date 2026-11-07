#!/usr/bin/env python3
"""Tests for spec_trace.py. Standard library only; each test builds a scratch git repository.

Every git command here runs with the user's and the system's git config shut out
(setUpModule), so settings such as a global excludes file or hooks change nothing.

Run from the root of the shared-skills clone:  python3 .agents/skills/spec-trace/scripts/test_spec_trace.py
"""

import io
import json
import os
import re
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

## Purpose

Work is claimed before it starts.

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

# The fixtures build the tag word from parts, so their text in this file is not
# a tag. This file still holds tag-shaped text in the messages it expects, so a
# repository that vendors spec-trace's scripts folder must list this file in its
# openspec/spec-trace-ignore.txt, or check fails on those messages as tags.
AT = "@" + "scenario"


def openspec_version():
    """The OpenSpec CLI's version on PATH, as a tuple, or None."""
    exe = shutil.which("openspec")
    if exe is None:
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", subprocess.run([exe, "--version"], capture_output=True,
                                                         text=True).stdout)
    return tuple(map(int, m.groups())) if m else None


# check, report and baseline read scenarios only through OpenSpec 1.15.0 or later.
HAS_OPENSPEC = (openspec_version() or (0,)) >= (1, 15, 0)
READS_SPECS = ("check", "report", "baseline")


def skip_without_openspec(test, args):
    """Skip test when args run a command that reads specs and OpenSpec 1.15.0 or later is
    not on PATH."""
    if not HAS_OPENSPEC and any(a in READS_SPECS for a in args):
        test.skipTest("needs OpenSpec 1.15.0 or later on PATH")


def spec(body):
    """A main spec holding body, its requirements. OpenSpec reads a main spec only when it
    has a Purpose section with text and a Requirements section, and a scenario only when
    text follows its heading, so each fixture's scenario has a `- THEN` line."""
    return "# Spec\n\n## Purpose\n\nTests.\n\n## Requirements\n\n" + textwrap.dedent(body)


def setUpModule():
    """Shut out the user's and the system's git config for every git this module runs."""
    scratch = tempfile.mkdtemp()
    empty = os.path.join(scratch, "gitconfig")
    open(empty, "w").close()
    patcher = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": empty, "GIT_CONFIG_NOSYSTEM": "1"})
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)
    unittest.addModuleCleanup(shutil.rmtree, scratch)


def git(root, *args):
    subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


class Repo(unittest.TestCase):
    """A scratch git repository with one capability, work-claiming, and its two scenarios.

    Files are left untracked unless a test adds them: spec-trace searches both.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        subprocess.run(["git", "init", "-q", "-b", "main", self.root], check=True)
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
        skip_without_openspec(self, args)
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
        self.assertIn("openspec/specs/work-claiming/spec.md:17: no test tags scenario "
                      "'work-claiming: Unclaimed work refused'", out)
        self.assertIn(f"with `{AT}` followed by this line, or write that test:\n"
                      "      work-claiming: Unclaimed work refused", out)

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
                      "is now tagged by test/claim.test.ts:3. Run `baseline --prune` to remove this line", out)

    def test_baseline_line_naming_no_scenario_fails(self):
        self.tag_both()
        self.write(st.DEFAULT_BASELINE, "work-claiming: Gone\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("'work-claiming: Gone' names no scenario in openspec/specs. "
                      "Run `baseline --prune` to remove this line", out)

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
        self.write("openspec/specs/kill/spec.md", spec("### Requirement: R\n#### Scenario: The worker's tree dies\n- THEN it holds\n"))
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
            - THEN it holds
            """)
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_a_scenario_in_a_code_fence_is_not_a_scenario(self):
        self.tag_both()
        self.write("openspec/specs/work-claiming/spec.md",
                   CLAIMING + "\n```\n#### Scenario: An example in a fence\n- THEN it holds\n```\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_no_openspec_directory_is_an_error(self):
        shutil.rmtree(os.path.join(self.root, "openspec"))
        with self.assertRaises(SystemExit) as raised:
            self.run_cmd("check")
        self.assertEqual(f"spec-trace: no openspec/ under {self.root}", str(raised.exception))


class NoSpecsYet(Repo):
    """A repository that has just adopted OpenSpec: openspec/ holds an open change, and
    there is no openspec/specs/ until the change is archived."""

    def setUp(self):
        super().setUp()
        shutil.rmtree(os.path.join(self.root, "openspec", "specs"))
        self.write("openspec/changes/add-x/specs/work-claiming/spec.md", """\
            ## ADDED Requirements
            ### Requirement: New
            #### Scenario: Not built yet
            - THEN it holds
            """)

    def test_check_passes_with_no_scenarios(self):
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)
        self.assertIn("spec-trace: ok. 0 of 0 scenarios are tagged", out)

    def test_a_tag_naming_the_change_s_scenario_is_accepted(self):
        self.write("test/x.test.ts", f"// {AT} work-claiming: Not built yet\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_a_tag_naming_nothing_fails(self):
        self.write("test/x.test.ts", f"// {AT} work-claiming: Nothing\n// {AT} nope: Nothing\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        self.assertIn("test/x.test.ts:1: tag '@scenario work-claiming: Nothing' names no capability "
                      "under openspec/specs. It holds no scenario yet", out)
        self.assertIn("test/x.test.ts:2: tag '@scenario nope: Nothing' names no capability", out)
        self.assertIn("2 problem(s)", out)

    def test_baseline_writes_only_its_header(self):
        code, out = self.run_cmd("baseline")
        self.assertEqual(code, 0, out)
        self.assertIn("wrote 0 untagged scenario(s) of 0", out)
        text = self.read(st.DEFAULT_BASELINE)
        self.assertTrue(text)
        self.assertTrue(all(l.startswith("#") for l in text.splitlines()), text)
        self.assertEqual(self.run_cmd("check")[0], 0)

    def test_report_runs_and_lists_the_change_when_asked(self):
        self.write("test/x.test.ts", f"// {AT} work-claiming: Not built yet\n")
        code, out = self.run_cmd("report")
        self.assertEqual(code, 0, out)
        self.assertIn("0 of 0 scenarios are tagged by a test.", out)
        code, out = self.run_cmd("report", "--include-changes")
        self.assertEqual(code, 0, out)
        self.assertIn("| Not built yet (change: add-x) | test/x.test.ts:1 |", out)

    def test_a_capability_only_a_change_adds_counts_only_when_report_includes_changes(self):
        self.write("test/x.test.ts", f"// {AT} work-claiming: Nope\n")
        out = self.run_cmd("report")[1]
        self.assertIn("tag '@scenario work-claiming: Nope' names no capability under openspec/specs", out)
        out = self.run_cmd("report", "--include-changes")[1]
        self.assertIn("tag '@scenario work-claiming: Nope' names no scenario in "
                      "openspec/specs/work-claiming/spec.md.", out)
        self.assertNotIn("names no capability", out)


class Search(Repo):
    """Tags are found with git grep over every file git tracks or would track under the root."""

    def test_tags_in_tracked_and_untracked_files_count(self):
        self.write("test/a.test.ts", f"// {AT} work-claiming: Claim precedes work\n")
        git(self.root, "add", "test/a.test.ts")
        self.write("src/b.go", f"// {AT} work-claiming: Unclaimed work refused\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)
        out = self.run_cmd("report")[1]
        self.assertIn("| Claim precedes work | test/a.test.ts:1 |", out)
        self.assertIn("| Unclaimed work refused | src/b.go:1 |", out)

    def test_a_tag_outside_a_test_counts_when_it_names_a_scenario_and_fails_when_not(self):
        self.tag_both()
        self.write("src/claim.ts", f"// {AT} work-claiming: No such scenario\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("src/claim.ts:1: tag '@scenario work-claiming: No such scenario' names no scenario", out)

    def test_ignored_files_are_skipped(self):
        self.tag_both()
        self.write(".gitignore", "build/\n*.log\n")
        self.write("build/test/x.test.js", f"// {AT} work-claiming: Nope\n")
        self.write("run.log", f"{AT} work-claiming: Nope\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_a_tracked_file_that_gitignore_matches_is_not_searched(self):
        # Deliberately unsupported: DECISIONS.md, "A test whose path .gitignore matches is not supported".
        self.tag_both()
        self.write(".gitignore", "build/\n*.log\n")
        self.write("build/x.test.js", f"// {AT} work-claiming: Nope\n")
        self.write("x.log", f"{AT} work-claiming: Nope\n")
        git(self.root, "add", "-f", "build/x.test.js", "x.log")
        self.assertEqual(self.run_cmd("check")[0], 0)

    def test_each_default_exclusion_is_skipped(self):
        self.tag_both()
        for rel in ("README.md", "docs/deep/guide.md", "docs/a.mdx", "docs/b.rst", "docs/c.adoc",
                    "notes.txt", "openspec/changes/x/proposal.md", "openspec/notes.yaml"):
            self.write(rel, f"{AT} work-claiming: Nope\n")
            code, out = self.run_cmd("check")
            self.assertEqual(code, 0, f"{rel}: {out}")

    def test_binary_files_are_skipped(self):
        self.tag_both()
        # Without -I, git prints "Binary file ... matches" for this file, a line with no NUL.
        # The parser fails on it only when it ends the output. Named to sort last, the file
        # makes this test fail if -I is ever dropped.
        with open(os.path.join(self.root, "zz.bin"), "wb") as f:
            f.write(b"\0\0" + f"{AT} work-claiming: Nope\n".encode())
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_a_nested_repository_is_skipped(self):
        self.tag_both()
        nested = os.path.join(self.root, ".claude/worktrees/other")
        os.makedirs(nested)
        subprocess.run(["git", "init", "-q", nested], check=True)
        self.write(".claude/worktrees/other/test/x.test.ts", f"// {AT} work-claiming: Nope\n")
        self.assertEqual(self.run_cmd("check")[0], 0)

    def test_a_path_with_a_colon_and_a_crlf_line_is_read(self):
        self.write("test/a:b.test.ts", f"// {AT} work-claiming: Claim precedes work\r\n"
                                        f"// {AT} work-claiming: Unclaimed work refused\r\n")
        out = self.run_cmd("report")[1]
        self.assertIn("| Claim precedes work | test/a:b.test.ts:1 |", out)
        self.assertIn("| Unclaimed work refused | test/a:b.test.ts:2 |", out)

    def test_git_settings_that_change_its_output_are_undone(self):
        self.tag_both()
        settings = {"grep.fullName": "true", "grep.column": "true", "color.grep": "always",
                    "color.ui": "always", "grep.patternType": "perl", "grep.lineNumber": "false"}
        env = {"GIT_CONFIG_COUNT": str(len(settings))}
        for i, (key, value) in enumerate(settings.items()):
            env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"] = key, value
        with mock.patch.dict(os.environ, env):
            out = self.run_cmd("report")[1]
        self.assertIn("| Claim precedes work | test/claim.test.ts:1 |", out)

    def test_submodule_recurse_in_git_config_does_not_stop_the_search(self):
        self.tag_both()
        with mock.patch.dict(os.environ, {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "submodule.recurse",
                                          "GIT_CONFIG_VALUE_0": "true"}):
            code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_literal_pathspecs_in_the_environment_keep_the_exclusions(self):
        self.tag_both()
        self.write("NOTES.md", f"{AT} work-claiming: Gone\n")
        with mock.patch.dict(os.environ, {"GIT_LITERAL_PATHSPECS": "1"}):
            code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_the_grep_command(self):
        self.assertEqual(st.grep_command("/r", ["vendor/**"]), [
            "git", "--no-literal-pathspecs", "-C", "/r", "grep", "--untracked",
            "--no-recurse-submodules", "-I", "-n", "-z", "--no-color", "--no-column", "--no-full-name",
            "-F", "-e", "@scenario", "--", ".",
            ":(exclude,glob)**/*.md", ":(exclude,glob)**/*.mdx", ":(exclude,glob)**/*.rst",
            ":(exclude,glob)**/*.adoc", ":(exclude,glob)**/*.txt", ":(exclude,glob)openspec/**",
            ":(exclude,glob)vendor/**"])

    def test_a_name_ending_in_a_parenthesis_is_shown_whole(self):
        self.tag_both()
        self.write("test/r.test.ts", f"it('{AT} work-claiming: Run (fast)', () => {{}})\n")
        self.assertIn("tag '@scenario work-claiming: Run (fast)' names no scenario", self.run_cmd("check")[1])


class IgnoreFile(Repo):
    """openspec/spec-trace-ignore.txt: one git glob pattern per line, each an extra exclude."""

    def setUp(self):
        super().setUp()
        self.tag_both()
        self.write("docs/tags.html", f"<!-- {AT} work-claiming: Some scenario -->\n")
        self.write("vendor/tool/x.js", f"// {AT} other: Not ours\n")

    def test_its_patterns_silence_tags_that_are_not_tests(self):
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("docs/tags.html:1: tag '@scenario work-claiming: Some scenario' names no scenario", out)
        self.assertIn("vendor/tool/x.js:1: tag '@scenario other: Not ours' names no capability", out)
        self.assertEqual(out.count(f"If the file is not a test, add a pattern for its path to {st.IGNORE_FILE}."), 2)
        self.write(st.IGNORE_FILE, "# Not tests\n\ndocs/*.html\n  vendor/  \n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_a_pattern_leaves_other_files_alone(self):
        self.write(st.IGNORE_FILE, "docs/*.html\nvendor/**\n")
        self.write("docs/sub/more.html", f"{AT} work-claiming: Nope\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("docs/sub/more.html:1:", out)
        self.assertNotIn("docs/tags.html", out)

    def test_a_byte_order_mark_does_not_spoil_the_first_pattern(self):
        with open(os.path.join(self.root, st.IGNORE_FILE), "wb") as f:
            f.write(b"\xef\xbb\xbfdocs/**\r\nvendor/**\r\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_a_bad_pattern_stops_every_command_with_gits_error(self):
        self.write(st.IGNORE_FILE, "vendor/**\n/elsewhere/x\n")
        self.write(st.DEFAULT_BASELINE, "work-claiming: Claim precedes work\n")
        for command in (["check"], ["report"], ["report", "--include-changes"], ["baseline", "--prune"]):
            code, out = self.run_cmd(*command)
            self.assertEqual(code, 2, f"{command}: {out}")
            self.assertIn("spec-trace: git grep failed: fatal:", out)
            self.assertIn("/elsewhere", out)
            self.assertIn(f"Check the patterns in {st.IGNORE_FILE}.", out)
        self.assertEqual(self.read(st.DEFAULT_BASELINE), "work-claiming: Claim precedes work\n")
        os.remove(os.path.join(self.root, st.DEFAULT_BASELINE))
        self.assertEqual(self.run_cmd("baseline")[0], 2)
        self.assertFalse(os.path.exists(os.path.join(self.root, st.DEFAULT_BASELINE)))

    def test_one_that_is_not_a_regular_file_or_too_long_stops_the_command(self):
        os.makedirs(os.path.join(self.root, st.IGNORE_FILE))
        code, out = self.run_cmd("check")
        self.assertEqual(code, 2)
        self.assertIn(f"{st.IGNORE_FILE} cannot be read", out)
        os.rmdir(os.path.join(self.root, st.IGNORE_FILE))
        self.write(st.IGNORE_FILE, "# x\n" * (st.IGNORE_FILE_LIMIT // 4 + 1))
        code, out = self.run_cmd("check")
        self.assertEqual(code, 2)
        self.assertIn(f"is longer than {st.IGNORE_FILE_LIMIT} characters", out)


class SubdirectoryRoot(unittest.TestCase):
    """--root below the top of the repository: the search, the exclusions and the
    ignore file's patterns all start at the root."""

    def setUp(self):
        self.top = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.top)
        subprocess.run(["git", "init", "-q", self.top], check=True)
        self.pkg = os.path.join(self.top, "packages/api")
        for rel, text in (
                ("packages/api/openspec/specs/work-claiming/spec.md", CLAIMING),
                ("packages/api/test/claim.test.ts", f"// {AT} work-claiming: Claim precedes work\n"),
                ("packages/api/README.md", f"{AT} work-claiming: Nope\n"),
                ("packages/api/vendor/x.js", f"{AT} work-claiming: Nope\n"),
                ("packages/api/openspec/spec-trace-ignore.txt", "vendor/**\n"),
                ("e2e/claim.test.ts", f"// {AT} work-claiming: Unclaimed work refused\n"),
                ("openspec/x.js", f"{AT} work-claiming: Nope\n")):
            path = os.path.join(self.top, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

    def run_cmd(self, *args):
        skip_without_openspec(self, args)
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = st.main(["--root", self.pkg, *args])
        return code, out.getvalue()

    def test_only_files_under_the_root_are_searched(self):
        code, out = self.run_cmd("report")
        self.assertEqual(code, 0)
        self.assertIn("| Claim precedes work | test/claim.test.ts:1 |", out)
        # A test outside the package can't tag its scenarios.
        self.assertIn("| Unclaimed work refused | none |", out)
        self.assertNotIn("### Problems", out)

    def test_git_settings_that_change_its_output_are_undone_below_the_top(self):
        settings = {"grep.fullName": "true", "grep.column": "true"}
        env = {"GIT_CONFIG_COUNT": str(len(settings))}
        for i, (key, value) in enumerate(settings.items()):
            env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"] = key, value
        with mock.patch.dict(os.environ, env):
            out = self.run_cmd("report")[1]
        self.assertIn("| Claim precedes work | test/claim.test.ts:1 |", out)

    def test_an_inherited_git_dir_does_not_hide_the_top_level_gitignore(self):
        # git exports GIT_DIR, without GIT_WORK_TREE, to hooks in a linked worktree
        # and to `git rebase -x`; git -C <root> would then take the root for the top.
        with open(os.path.join(self.top, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("build/\n")
        os.makedirs(os.path.join(self.pkg, "build"))
        with open(os.path.join(self.pkg, "build/out.js"), "w", encoding="utf-8") as f:
            f.write(f"// {AT} work-claiming: Generated\n")
        with mock.patch.dict(os.environ, {"GIT_DIR": os.path.join(self.top, ".git")}):
            out = self.run_cmd("report")[1]
        self.assertNotIn("build/out.js", out)
        self.assertIn("| Claim precedes work | test/claim.test.ts:1 |", out)

    def ignored_build(self):
        with open(os.path.join(self.top, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("build/\n")
        os.makedirs(os.path.join(self.pkg, "build"))
        with open(os.path.join(self.pkg, "build/out.js"), "w", encoding="utf-8") as f:
            f.write(f"// {AT} work-claiming: Generated\n")

    def test_a_relative_inherited_git_dir_is_read_from_the_root(self):
        # git reads a relative GIT_DIR after -C, so from the root.
        self.ignored_build()
        with mock.patch.dict(os.environ, {"GIT_DIR": "../../.git"}):
            out = self.run_cmd("report")[1]
        self.assertNotIn("build/out.js", out)
        self.assertIn("| Claim precedes work | test/claim.test.ts:1 |", out)

    def test_a_git_dir_set_on_purpose_is_kept(self):
        # A work tree whose git directory lives elsewhere, as in a dotfiles setup:
        # git finds no repository from the root without GIT_DIR.
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base)
        tree, gitdir = os.path.join(base, "tree"), os.path.join(base, "store.git")
        shutil.copytree(self.pkg, tree)
        subprocess.run(["git", "init", "-q", "--separate-git-dir", gitdir, tree], check=True)
        os.remove(os.path.join(tree, ".git"))
        skip_without_openspec(self, ["report"])
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"GIT_DIR": gitdir, "GIT_CEILING_DIRECTORIES": base}), \
                redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = st.main(["--root", tree, "report"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("| Claim precedes work | test/claim.test.ts:1 |", out.getvalue())

    def test_saved_check_output_is_not_read_as_tags(self):
        self.write_pkg("trace.log", self.run_cmd("check")[1])
        self.assertEqual(self.run_cmd("check")[0], 1)

    def write_pkg(self, rel, text):
        with open(os.path.join(self.pkg, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def test_baseline_and_check(self):
        self.assertEqual(self.run_cmd("baseline")[0], 0)
        with open(os.path.join(self.pkg, st.DEFAULT_BASELINE), encoding="utf-8") as f:
            self.assertIn("work-claiming: Unclaimed work refused\n", f.read())
        self.assertEqual(self.run_cmd("check")[0], 0)


class NoGit(unittest.TestCase):
    """The commands that read tags need git and a git work tree; state and decline do not."""

    def setUp(self):
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base)
        self.root = os.path.join(base, "repo")
        os.makedirs(os.path.join(self.root, "openspec/specs/work-claiming"))
        with open(os.path.join(self.root, "openspec/specs/work-claiming/spec.md"), "w", encoding="utf-8") as f:
            f.write(CLAIMING)
        with open(os.path.join(self.root, "claim.test.ts"), "w", encoding="utf-8") as f:
            f.write(f"// {AT} work-claiming: Claim precedes work\n")
        # git must not find a repository above the scratch folder.
        patcher = mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": base})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cmd(self, *args):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = st.main(["--root", self.root, *args])
        return code, out.getvalue()

    def refused(self, says):
        for command in (["check"], ["report"], ["report", "--include-changes"], ["baseline"],
                        ["baseline", "--prune"]):
            code, out = self.run_cmd(*command)
            self.assertEqual(code, 2, f"{command}: {out}")
            self.assertIn(says, out)
            self.assertIn("state and decline do not", out)
        self.assertFalse(os.path.exists(os.path.join(self.root, st.DEFAULT_BASELINE)))

    def test_outside_a_git_work_tree_tag_commands_are_refused(self):
        self.refused(f"spec-trace: {self.root} is not inside a git work tree")

    def test_without_git_tag_commands_are_refused(self):
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty)
        with mock.patch.dict(os.environ, {"PATH": empty}):
            self.refused("spec-trace: git could not be run")

    def test_state_and_decline_work_without_git(self):
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty)
        with mock.patch.dict(os.environ, {"PATH": empty}):
            self.assertEqual(self.run_cmd("state"), (0, "undecided\n"))
            self.assertEqual(self.run_cmd("decline")[0], 0)
            self.assertEqual(self.run_cmd("state"), (0, "declined\n"))


class FoundByTheHunt(Repo):
    """Regression tests for bugs bug-hunter found before spec-trace's first commit."""

    def test_an_escaped_apostrophe_in_a_single_quoted_name_matches(self):
        self.tag_both()
        self.write("openspec/specs/cmd/spec.md", spec("### Requirement: R\n#### Scenario: A person's command is unchanged\n- THEN it holds\n"))
        self.write("test/a.test.ts", f"it('{AT} cmd: A person\\'s command is unchanged', () => {{}});\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_a_bare_repeated_name_in_a_single_quoted_name_is_ambiguous(self):
        self.tag_both()
        self.write("openspec/specs/run/spec.md", spec("### Requirement: A\n#### Scenario: Ordinary\n- THEN it holds\n### Requirement: B\n#### Scenario: Ordinary\n- THEN it holds\n"))
        self.write(st.DEFAULT_BASELINE, "run: A / Ordinary\nrun: B / Ordinary\n")
        self.write("test/a.test.ts", f"it('{AT} run: Ordinary', async () => {{\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("test/a.test.ts:1: tag '@scenario run: Ordinary' is ambiguous", out)

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
                   "## ADDED Requirements\n### Requirement: New\n#### Scenario: Fresh\n- THEN it holds\n\n## \n")
        code, out = self.run_cmd("report", "--include-changes")
        self.assertEqual(code, 0)
        self.assertIn("| Fresh (change: ch) | none |", out)

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_a_file_in_a_merge_conflict_is_read_once(self):
        git = ["git", "-C", self.root, "-c", "user.name=t", "-c", "user.email=t@t"]
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
        self.write("openspec/specs/disc/spec.md", spec("### Requirement: A\n#### Scenario: Item assigned, on Linear\n- THEN it holds\n"
                   "### Requirement: B\n#### Scenario: Item assigned, on Linear\n- THEN it holds\n"
                   "#### Scenario: Item assigned\n- THEN it holds\n"))
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
            - THEN it holds
            #### Scenario: Unclaimed work refused
            - THEN it holds
            """)
        out = self.run_cmd("report", "--include-changes")[1]
        self.assertIn("2 of 2 scenarios are tagged", out)
        self.assertNotIn("### Problems", out)

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
                   "## ADDED Requirements\n### Requirement: N\n#### Scenario: New\n- THEN it holds\n")
        self.write("openspec/changes/add-new/specs/newcap/spec.md",
                   "## ADDED Requirements\n### Requirement: M\n#### Scenario: Fresh\n- THEN it holds\n")
        self.write("test/a.test.ts", f"// {AT} work-claiming: New\n// {AT} newcap: Fresh\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)

    def test_a_fenced_example_in_a_delta_changes_nothing(self):
        self.tag_both()
        fence = "`" * 3
        self.write("openspec/changes/ex/specs/work-claiming/spec.md",
                   "## ADDED Requirements\n### Requirement: Examples are shown\n"
                   f"{fence}markdown\n## REMOVED Requirements\n### Requirement: An Igor claims before it starts\n{fence}\n"
                   "#### Scenario: An example renders\n- THEN it holds\n")
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
                   "#### Scenario: Claim precedes work\n- THEN it holds\n#### Scenario: Claim precedes work, always\n- THEN it holds\n"
                   "#### Scenario: Unclaimed work refused\n- THEN it holds\n")
        self.write("test/b.test.ts", f"// {AT} work-claiming: Claim precedes work, always\n")
        out = self.run_cmd("report")[1]
        self.assertIn("| Claim precedes work | test/claim.test.ts:1 |", out)

    def test_a_bare_name_repeated_in_an_open_change_is_ambiguous(self):
        self.tag_both()
        self.write("openspec/changes/add-two/specs/roles/spec.md",
                   "## ADDED Requirements\n### Requirement: Role names\n#### Scenario: Malformed input rejected\n- THEN it holds\n"
                   "### Requirement: Role permissions\n#### Scenario: Malformed input rejected\n- THEN it holds\n")
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
                   "#### Scenario: Example shown\n- THEN it holds\n")
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
        self.write("openspec/specs/task-execution/spec.md", spec("""\
            ### Requirement: Names are text
            #### Scenario: An ordinary run is unaffected
            - THEN it holds
            ### Requirement: No removal is lost
            #### Scenario: An ordinary run is unaffected
            - THEN it holds
            """))
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
        self.assertIn(f"write `{AT}` followed by one of these lines:", out)
        self.assertIn("\n      task-execution: No removal is lost / An ordinary run is unaffected", out)

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
        self.write("openspec/specs/task-execution/spec.md", spec("""\
            ### Requirement: Names are text
            #### Scenario: Twice
            - THEN it holds
            #### Scenario: Twice
            - THEN it holds
            """))
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("no tag can tell them apart. Rename one of them", out)
        self.assertIn("openspec/specs/task-execution/spec.md:12: scenario 'Twice' repeats under requirement "
                      "'Names are text' (openspec/specs/task-execution/spec.md:10)", out)


class ReadByOpenSpec(Repo):
    """Scenarios are what `openspec show` reads, and only that."""

    def test_a_section_title_openspec_ignores_restates_nothing(self):
        # OpenSpec reads no section titled "MODIFIED Requirements:", so it changes nothing.
        self.tag_both()
        self.write("openspec/changes/sharpen/specs/work-claiming/spec.md", """\
            ## MODIFIED Requirements:
            ### Requirement: An Igor claims before it starts
            #### Scenario: Claim is logged
            - THEN it holds
            """)
        self.write("test/log.test.ts", f"// {AT} work-claiming: Claim is logged\n")
        out = self.run_cmd("report", "--include-changes")[1]
        self.assertIn("| Claim precedes work | test/claim.test.ts:1 |", out)
        self.assertNotIn("(change: sharpen)", out)
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        self.assertIn("tag '@scenario work-claiming: Claim is logged' names no scenario", out)

    def test_a_heading_s_closing_hashes_are_not_part_of_the_name(self):
        self.write("openspec/specs/work-claiming/spec.md",
                   CLAIMING.replace("Scenario: Unclaimed work refused", "Scenario: Unclaimed work refused ##"))
        self.write("test/claim.test.ts", f"// {AT} work-claiming: Claim precedes work\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        self.assertIn("openspec/specs/work-claiming/spec.md:17: no test tags scenario "
                      "'work-claiming: Unclaimed work refused'.", out)
        self.tag_both()
        self.assertEqual(self.run_cmd("check")[0], 0)

    def test_a_scenario_heading_with_no_text_under_it_is_not_a_scenario(self):
        self.tag_both()
        self.write("openspec/specs/work-claiming/spec.md", CLAIMING + "\n#### Scenario: Empty\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 0, out)
        self.assertIn("2 of 2 scenarios are tagged", out)

    def test_a_spec_openspec_cannot_read_fails_check_and_baseline(self):
        self.tag_both()
        self.write("openspec/specs/bad/spec.md", "### Requirement: R\n#### Scenario: S\n- THEN it holds\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        self.assertIn("openspec/specs/bad/spec.md: `openspec show` cannot read this spec (Spec must have "
                      "a Purpose section), so none of its scenarios, and no tag or baseline line naming them, "
                      "were checked.", out)
        code, out = self.run_cmd("baseline")
        self.assertEqual(code, 1, out)
        self.assertFalse(os.path.exists(os.path.join(self.root, st.DEFAULT_BASELINE)))

    def test_tags_and_baseline_lines_for_an_unreadable_spec_are_not_called_wrong(self):
        self.tag_both()
        self.write("openspec/specs/auth/spec.md",
                   "## Requirements\n### Requirement: Login\n#### Scenario: Good password\n- THEN in\n"
                   "#### Scenario: Bad password\n- THEN out\n")
        self.write("test/a.test.js", f"// {AT} auth: Good password\n")
        self.write(st.DEFAULT_BASELINE, "auth: Bad password\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        self.assertIn("openspec/specs/auth/spec.md: `openspec show` cannot read this spec", out)
        self.assertNotIn("names no capability", out)
        self.assertNotIn("'auth: Bad password' names no scenario", out)
        self.assertIn("1 problem(s)", out)

    def test_while_a_spec_is_unreadable_check_does_not_send_the_author_to_prune(self):
        # `baseline --prune` refuses while a spec cannot be read.
        self.tag_both()
        self.write("openspec/specs/auth/spec.md", "## Requirements\n### Requirement: R\n#### Scenario: S\n- THEN it holds\n")
        self.write(st.DEFAULT_BASELINE, "work-claiming: Claim precedes work\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        self.assertIn("'work-claiming: Claim precedes work' is now tagged by test/claim.test.ts:1.", out)
        self.assertNotIn("Run `baseline --prune`", out)
        self.assertEqual(self.run_cmd("baseline", "--prune")[0], 1)

    def test_a_tag_failure_names_a_delta_spec_openspec_reads_as_empty(self):
        # "## ADDED Requirement", singular, is not a section OpenSpec reads, so the delta is empty.
        self.tag_both()
        for cap in ("work-claiming", "newcap"):
            self.write(f"openspec/changes/add-x/specs/{cap}/spec.md",
                       "## ADDED Requirement\n### Requirement: New\n#### Scenario: Fresh\n- THEN it holds\n")
        self.write("test/x.test.ts", f"// {AT} work-claiming: Fresh\n// {AT} newcap: Fresh\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        for cap in ("work-claiming", "newcap"):
            self.assertIn(f"`openspec show` reads no requirement in openspec/changes/add-x/specs/{cap}/spec.md. "
                          "If this tag names a scenario there, run `openspec validate add-x --type change` "
                          "to see why.", out)
        self.assertEqual(out.count("reads no requirement"), 2, out)
        out = self.run_cmd("report", "--include-changes")[1]
        self.assertIn("reads no requirement in openspec/changes/add-x/specs/newcap/spec.md", out)

    def test_an_empty_delta_adds_nothing_to_a_tag_that_fails_elsewhere(self):
        self.tag_both()
        self.write("openspec/changes/add-x/specs/newcap/spec.md", "## ADDED Requirement\n")
        self.write("test/x.test.ts", f"// {AT} work-claiming: Nothing\n")
        out = self.run_cmd("check")[1]
        self.assertIn("names no scenario", out)
        self.assertNotIn("reads no requirement", out)

    def test_a_tag_failure_names_a_restated_requirement_with_no_scenario(self):
        # A scenario heading with no text under it is not a scenario to OpenSpec, so the
        # requirement above it is read with none. add-x covers a requirement a delta adds,
        # and mod-y one it modifies.
        self.tag_both()
        self.write("openspec/changes/add-x/specs/work-claiming/spec.md",
                   "## ADDED Requirements\n### Requirement: New\nIt SHALL hold.\n\n#### Scenario: Fresh\n")
        self.write("openspec/changes/mod-y/specs/work-claiming/spec.md",
                   "## MODIFIED Requirements\n### Requirement: An Igor claims before it starts\n"
                   "Every pickup SHALL take a claim.\n\n#### Scenario: Claim precedes work\n")
        self.write("test/x.test.ts", f"// {AT} work-claiming: Fresh\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        self.assertIn("`openspec show` reads no scenario under requirement 'New' in "
                      "openspec/changes/add-x/specs/work-claiming/spec.md. If this tag names a scenario "
                      "there, run `openspec validate add-x --type change` to see why.", out)
        self.assertIn("`openspec show` reads no scenario under requirement 'An Igor claims before it starts' in "
                      "openspec/changes/mod-y/specs/work-claiming/spec.md.", out)
        self.assertNotIn("reads no requirement", out)

    def test_a_capability_whose_only_requirement_a_change_removes_still_exists(self):
        self.tag_both()
        self.write("openspec/changes/drop/specs/work-claiming/spec.md",
                   "## REMOVED Requirements\n### Requirement: An Igor claims before it starts\n")
        out = self.run_cmd("report", "--include-changes")[1]
        self.assertIn("test/claim.test.ts:1: tag '@scenario work-claiming: Claim precedes work' names no "
                      "scenario in openspec/specs/work-claiming/spec.md.", out)
        self.assertNotIn("names no capability", out)

    def test_a_capability_left_with_no_scenario_by_a_misread_modification_still_exists(self):
        self.tag_both()
        self.write("openspec/changes/mod-y/specs/work-claiming/spec.md",
                   "## MODIFIED Requirements\n### Requirement: An Igor claims before it starts\n"
                   "Every pickup SHALL take a claim.\n\n#### Scenario: Claim precedes work\n")
        out = self.run_cmd("report", "--include-changes")[1]
        self.assertIn("test/claim.test.ts:1: tag '@scenario work-claiming: Claim precedes work' names no "
                      "scenario in openspec/specs/work-claiming/spec.md.", out)
        self.assertIn("`openspec show` reads no scenario under requirement 'An Igor claims before it starts' "
                      "in openspec/changes/mod-y/specs/work-claiming/spec.md.", out)
        self.assertNotIn("names no capability", out)

    def test_a_main_spec_with_no_scenario_is_still_a_capability(self):
        self.tag_both()
        self.write("openspec/specs/bare/spec.md", spec("### Requirement: R\nIt SHALL hold.\n"))
        self.write("test/b.test.ts", f"// {AT} bare: Something\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        self.assertIn("tag '@scenario bare: Something' names no scenario in openspec/specs/bare/spec.md.", out)
        self.assertNotIn("names no capability", out)

    def test_a_delta_that_only_removes_or_renames_brings_no_note(self):
        self.tag_both()
        self.write("openspec/changes/drop/specs/work-claiming/spec.md",
                   "## REMOVED Requirements\n### Requirement: An Igor claims before it starts\n")
        self.write("openspec/changes/ren/specs/work-claiming/spec.md",
                   "## RENAMED Requirements\n- FROM: `### Requirement: An Igor claims before it starts`\n"
                   "- TO: `### Requirement: An Igor claims first`\n")
        self.write("test/x.test.ts", f"// {AT} work-claiming: Nothing\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        self.assertIn("names no scenario", out)
        self.assertNotIn("reads no", out)

    def test_a_delta_openspec_reads_brings_no_note(self):
        self.tag_both()
        self.write("openspec/changes/add-x/specs/work-claiming/spec.md",
                   "## ADDED Requirements\n### Requirement: New\n#### Scenario: Fresh\n- THEN it holds\n")
        self.write("openspec/changes/add-x/specs/newcap/spec.md", "## ADDED Requirement\n")
        self.write("test/x.test.ts", f"// {AT} work-claiming: Nothing\n// {AT} newcap: Nothing\n")
        out = self.run_cmd("check")[1]
        self.assertEqual(out.count("reads no requirement"), 1, out)
        self.assertNotIn("reads no requirement in openspec/changes/add-x/specs/work-claiming/spec.md", out)

    def test_a_fenced_example_of_a_scenario_does_not_take_its_line(self):
        fence = "`" * 3
        self.write("openspec/specs/work-claiming/spec.md", CLAIMING.replace(
            "Every pickup SHALL take a claim.\n",
            f"Every pickup SHALL take a claim.\n\n{fence}\n#### Scenario: Unclaimed work refused\n{fence}\n"))
        self.write("test/claim.test.ts", f"// {AT} work-claiming: Claim precedes work\n")
        out = self.run_cmd("check")[1]
        self.assertIn("openspec/specs/work-claiming/spec.md:21: no test tags scenario "
                      "'work-claiming: Unclaimed work refused'", out)

    def test_two_requirements_with_one_name_keep_their_own_lines(self):
        self.write("openspec/specs/dup/spec.md", spec(
            "### Requirement: R\n#### Scenario: X\n- THEN a\n### Requirement: R\n#### Scenario: Y\n- THEN b\n"))
        self.tag_both()
        self.write("test/x.test.ts", f"// {AT} dup: X\n")
        out = self.run_cmd("check")[1]
        self.assertIn("openspec/specs/dup/spec.md:13: no test tags scenario 'dup: Y'", out)

    def test_a_removed_requirement_s_scenarios_leave_the_report(self):
        self.tag_both()
        self.write("openspec/changes/drop/specs/work-claiming/spec.md",
                   "## REMOVED Requirements\n### Requirement: An Igor claims before it starts\n")
        out = self.run_cmd("report", "--include-changes")[1]
        self.assertIn("0 of 0 scenarios are tagged", out)
        self.assertNotIn("Claim precedes work |", out)

    def test_a_spec_edited_between_two_runs_in_one_process_is_read_again(self):
        self.tag_both()
        self.assertEqual(self.run_cmd("check")[0], 0)
        self.write("openspec/specs/work-claiming/spec.md",
                   CLAIMING + "\n#### Scenario: Claim is logged\n- THEN it holds\n")
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        self.assertIn("no test tags scenario 'work-claiming: Claim is logged'", out)

    def test_report_lists_a_change_openspec_cannot_read(self):
        self.write("openspec/changes/add-x/specs/work-claiming/spec.md",
                   "## ADDED Requirements\n### Requirement: New\n#### Scenario: Fresh\n- THEN it holds\n")
        real = st.run_show

        def refuse_changes(kind, name, files):
            return (None, "no can do") if kind == "change" else real(kind, name, files)

        with mock.patch.object(st, "run_show", side_effect=refuse_changes), \
                mock.patch.dict(st._shown, clear=True):
            out = self.run_cmd("report")[1]
        self.assertIn("### Problems", out)
        self.assertIn("- openspec/changes/add-x: `openspec show` cannot read its delta specs (no can do)", out)

    def test_a_change_openspec_cannot_read_fails_check(self):
        self.tag_both()
        self.write("openspec/changes/add-x/specs/work-claiming/spec.md",
                   "## ADDED Requirements\n### Requirement: New\n#### Scenario: Fresh\n- THEN it holds\n")
        real = st.run_show

        def refuse_changes(kind, name, files):
            return (None, "no can do") if kind == "change" else real(kind, name, files)

        with mock.patch.object(st, "run_show", side_effect=refuse_changes), \
                mock.patch.dict(st._shown, clear=True):
            code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        self.assertIn("openspec/changes/add-x: `openspec show` cannot read its delta specs (no can do)", out)

    def test_each_file_is_read_once_per_run(self):
        self.tag_both()
        self.write("openspec/changes/add-x/specs/work-claiming/spec.md",
                   "## ADDED Requirements\n### Requirement: New\n#### Scenario: Fresh\n- THEN it holds\n")
        with mock.patch.object(st, "run_show", wraps=st.run_show) as shown, \
                mock.patch.dict(st._shown, clear=True):
            self.assertEqual(self.run_cmd("check")[0], 0)
            self.assertEqual(shown.call_count, 2)
            self.run_cmd("report", "--include-changes")
            self.assertEqual(shown.call_count, 2)  # same content, so read from the cache


class WithoutOpenSpec(unittest.TestCase):
    """Below OpenSpec 1.15.0, or without its CLI, the commands that read specs refuse;
    state and decline still work."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        subprocess.run(["git", "init", "-q", self.root], check=True)
        os.makedirs(os.path.join(self.root, "openspec/specs/work-claiming"))
        with open(os.path.join(self.root, "openspec/specs/work-claiming/spec.md"), "w", encoding="utf-8") as f:
            f.write(CLAIMING)
        # A PATH holding git and, when a test writes one, a fake openspec.
        self.bin = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.bin)
        os.symlink(shutil.which("git"), os.path.join(self.bin, "git"))
        patcher = mock.patch.dict(os.environ, {"PATH": self.bin})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cmd(self, *args):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = st.main(["--root", self.root, *args])
        return code, out.getvalue()

    def refused(self, says):
        baseline = os.path.join(self.root, st.DEFAULT_BASELINE)
        for command in (["check"], ["report"], ["report", "--include-changes"], ["baseline"],
                        ["baseline", "--prune"]):
            if command == ["baseline", "--prune"]:
                with open(baseline, "w", encoding="utf-8") as f:
                    f.write("work-claiming: Gone\n")
            code, out = self.run_cmd(*command)
            self.assertEqual(code, 2, f"{command}: {out}")
            self.assertIn(f"spec-trace: not run: install OpenSpec 1.15.0 or later ({says})", out)
            self.assertIn("state and decline do not", out)
            if command == ["baseline"]:
                self.assertFalse(os.path.exists(baseline))
        with open(baseline, encoding="utf-8") as f:
            self.assertEqual(f.read(), "work-claiming: Gone\n")

    def test_without_the_cli_spec_commands_are_refused(self):
        self.refused("the openspec CLI is not on PATH")

    def test_an_older_cli_is_refused(self):
        fake = os.path.join(self.bin, "openspec")
        with open(fake, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\necho 1.14.0\n")
        os.chmod(fake, 0o755)
        self.refused("this one is 1.14.0")

    def fake_cli(self, show_output, exit_code):
        fake = os.path.join(self.bin, "openspec")
        with open(fake, "w", encoding="utf-8") as f:
            f.write(f"#!/bin/sh\nif [ \"$1\" = --version ]; then echo 1.15.0; exit 0; fi\n"
                    f"echo '{show_output}'\nexit {exit_code}\n")
        os.chmod(fake, 0o755)
        # Readings are kept by content, so one the real CLI made would answer for the fake.
        patcher = mock.patch.dict(st._shown, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_delta_naming_a_capability_it_was_not_given_is_ignored(self):
        # The CLI's output is data from outside; a delta for another capability is skipped.
        os.makedirs(os.path.join(self.root, "openspec/changes/ch/specs/work-claiming"))
        with open(os.path.join(self.root, "openspec/changes/ch/specs/work-claiming/spec.md"), "w",
                  encoding="utf-8") as f:
            f.write("## ADDED Requirements\n")
        self.fake_cli('{"requirements": [], "deltas": [{"spec": "other", "operation": "ADDED", '
                      '"requirement": {"name": "N", "scenarios": [{"name": "S"}]}}]}', 0)
        code, out = self.run_cmd("report", "--include-changes")
        self.assertEqual(code, 0, out)
        self.assertIn("0 of 0 scenarios are tagged", out)

    def test_a_failing_show_is_unread_even_when_it_prints_a_list(self):
        self.fake_cli('{"requirements": []}', 1)
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        self.assertIn("`openspec show` cannot read this spec", out)

    def test_a_show_that_prints_no_json_is_unread(self):
        self.fake_cli("garbage", 0)
        code, out = self.run_cmd("check")
        self.assertEqual(code, 1, out)
        self.assertIn("`openspec show` cannot read this spec (garbage)", out)

    def test_state_and_decline_need_no_cli(self):
        self.assertEqual(self.run_cmd("state"), (0, "undecided\n"))
        self.assertEqual(self.run_cmd("decline")[0], 0)


class Baseline(Repo):
    def test_writes_untagged_scenarios_sorted_and_check_then_passes(self):
        self.write("openspec/specs/alpha/spec.md", spec("### Requirement: R\n#### Scenario: Zed\n- THEN it holds\n#### Scenario: Ay\n- THEN it holds\n"))
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

    def test_an_existing_baseline_is_refused_and_left_untouched(self):
        self.write(st.DEFAULT_BASELINE, "# kept\nwork-claiming: Claim precedes work\n")
        code, out = self.run_cmd("baseline")
        self.assertEqual(code, 2, out)
        self.assertIn(f"{st.DEFAULT_BASELINE} already exists, so baseline wrote nothing. "
                      "Run `baseline --prune`", out)
        self.assertIn("or delete the file first to write it from scratch", out)
        self.assertEqual(self.read(st.DEFAULT_BASELINE), "# kept\nwork-claiming: Claim precedes work\n")
        os.remove(os.path.join(self.root, st.DEFAULT_BASELINE))
        self.assertEqual(self.run_cmd("baseline")[0], 0)
        self.assertIn("work-claiming: Unclaimed work refused\n", self.read(st.DEFAULT_BASELINE))

    def test_an_existing_baseline_at_another_path_is_refused(self):
        self.write("trace.txt", "")
        code, out = self.run_cmd("--baseline", "trace.txt", "baseline")
        self.assertEqual(code, 2, out)
        self.assertEqual(self.read("trace.txt"), "")


class Prune(Repo):
    """`baseline --prune` removes the lines `check` fails on, and never adds one."""

    HEADER = "# Scenarios no test tagged at adoption.\n\n"

    def setUp(self):
        super().setUp()
        self.write("openspec/specs/alpha/spec.md", spec("### Requirement: R\n#### Scenario: Zed\n- THEN it holds\n#### Scenario: Ay\n- THEN it holds\n#### Scenario: Bee\n- THEN it holds\n"))

    def test_removes_a_now_tagged_line_and_one_naming_no_scenario(self):
        self.write("test/claim.test.ts", f"// {AT} work-claiming: Claim precedes work\n")
        self.write(st.DEFAULT_BASELINE, self.HEADER + "alpha: Zed\nwork-claiming: Claim precedes work\n"
                   "alpha: Gone\nalpha: Ay\nalpha: Bee\nwork-claiming: Unclaimed work refused\n")
        code, out = self.run_cmd("baseline", "--prune")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.read(st.DEFAULT_BASELINE), self.HEADER + "alpha: Zed\nalpha: Ay\nalpha: Bee\n"
                         "work-claiming: Unclaimed work refused\n")
        self.assertIn(f"{st.DEFAULT_BASELINE}:4: removed 'work-claiming: Claim precedes work': "
                      "now tagged by test/claim.test.ts:1.", out)
        self.assertIn(f"{st.DEFAULT_BASELINE}:5: removed 'alpha: Gone': names no scenario in openspec/specs.", out)
        self.assertIn(f"pruned 2 line(s) from {st.DEFAULT_BASELINE}; 4 scenario line(s) remain.", out)
        self.assertEqual(self.run_cmd("check")[0], 0)

    def test_never_adds_an_untagged_scenario_missing_from_the_file(self):
        self.write("test/claim.test.ts", f"// {AT} work-claiming: Claim precedes work\n")
        self.write(st.DEFAULT_BASELINE, "alpha: Zed\nwork-claiming: Claim precedes work\n")
        code, out = self.run_cmd("baseline", "--prune")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.read(st.DEFAULT_BASELINE), "alpha: Zed\n")
        self.assertEqual(self.run_cmd("check")[0], 1)

    def test_nothing_to_prune_leaves_the_file_untouched(self):
        text = self.HEADER + "alpha: Bee\r\n  alpha :  Zed  \nalpha: Ay"
        path = os.path.join(self.root, st.DEFAULT_BASELINE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        before = os.stat(path).st_mtime_ns
        code, out = self.run_cmd("baseline", "--prune")
        self.assertEqual(code, 0, out)
        self.assertIn(f"nothing to prune; {st.DEFAULT_BASELINE} is unchanged, with 3 scenario line(s).", out)
        with open(path, encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), text)
        self.assertEqual(os.stat(path).st_mtime_ns, before)

    def test_kept_lines_keep_their_text_and_line_endings(self):
        self.write("test/a.test.ts", f"// {AT} alpha: Ay\n")
        path = os.path.join(self.root, st.DEFAULT_BASELINE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("# h\r\nalpha: Ay\r\n  alpha :  Zed  \r\n")
        self.assertEqual(self.run_cmd("baseline", "--prune")[0], 0)
        with open(path, encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), "# h\r\n  alpha :  Zed  \r\n")

    def test_with_no_baseline_it_is_refused(self):
        code, out = self.run_cmd("baseline", "--prune")
        self.assertEqual(code, 2, out)
        self.assertIn(f"there is no baseline file at {st.DEFAULT_BASELINE}, so there is nothing to prune", out)
        self.assertFalse(os.path.exists(os.path.join(self.root, st.DEFAULT_BASELINE)))

    def test_a_byte_order_mark_does_not_hide_the_first_line(self):
        self.write("test/a.test.ts", f"// {AT} alpha: Bee\n")
        path = os.path.join(self.root, st.DEFAULT_BASELINE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write("alpha: Zed\nalpha: Bee\n")
        code, out = self.run_cmd("baseline", "--prune")
        self.assertEqual(code, 0, out)
        self.assertNotIn("Zed", out)
        with open(path, encoding="utf-8-sig") as f:
            self.assertEqual(f.read(), "alpha: Zed\n")

    def test_the_file_stays_with_its_header_when_no_scenario_line_is_left(self):
        self.write("test/a.test.ts", f"// {AT} alpha: Ay\n// {AT} alpha: Zed\n")
        self.write(st.DEFAULT_BASELINE, self.HEADER + "alpha: Ay\nalpha: Zed\nalpha: Gone\n")
        code, out = self.run_cmd("baseline", "--prune")
        self.assertEqual(code, 0, out)
        self.assertIn("0 scenario line(s) remain. Keep the file: it records that this repository "
                      "adopted spec-trace.", out)
        self.assertEqual(self.read(st.DEFAULT_BASELINE), self.HEADER)
        self.assertEqual(st.adoption_state(self.root), st.ADOPTED)

    def test_respects_the_baseline_option(self):
        self.write("test/claim.test.ts", f"// {AT} work-claiming: Claim precedes work\n")
        self.write("ci/trace.txt", "work-claiming: Claim precedes work\nalpha: Ay\n")
        self.write(st.DEFAULT_BASELINE, "work-claiming: Claim precedes work\n")
        code, out = self.run_cmd("--baseline", "ci/trace.txt", "baseline", "--prune")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.read("ci/trace.txt"), "alpha: Ay\n")
        self.assertIn("ci/trace.txt:1: removed 'work-claiming: Claim precedes work'", out)
        self.assertEqual(self.read(st.DEFAULT_BASELINE), "work-claiming: Claim precedes work\n")


class Report(Repo):
    def test_with_no_spec_files_at_all_report_says_so(self):
        shutil.rmtree(os.path.join(self.root, "openspec", "specs"))
        self.write("test/x.test.ts", f"// {AT} zzz: Nothing\n")
        out = self.run_cmd("report", "--include-changes")[1]
        self.assertIn("tag '@scenario zzz: Nothing' names no capability in openspec/specs or an open "
                      "change. There is no spec file in either yet.", out)

    def test_an_unknown_capability_s_message_names_where_report_looked(self):
        self.write("openspec/changes/add-y/specs/billing/spec.md",
                   "## ADDED Requirements\n### Requirement: B\nIt SHALL bill.\n\n#### Scenario: Bills\n- THEN it bills\n")
        self.write("test/x.test.ts", f"// {AT} zzz: Nothing\n")
        out = self.run_cmd("report")[1]
        self.assertIn("tag '@scenario zzz: Nothing' names no capability under openspec/specs. "
                      "Capabilities: work-claiming.", out)
        out = self.run_cmd("report", "--include-changes")[1]
        self.assertIn("tag '@scenario zzz: Nothing' names no capability in openspec/specs or an open "
                      "change. Capabilities: billing, work-claiming.", out)
        out = self.run_cmd("check")[1]
        self.assertIn("tag '@scenario zzz: Nothing' names no capability under openspec/specs. "
                      "Capabilities: work-claiming.", out)

    def test_a_misspelled_capability_gets_a_suggestion(self):
        self.write("test/x.test.ts", f"// {AT} work-claim: Claim precedes work\n")
        out = self.run_cmd("report")[1]
        self.assertIn("tag '@scenario work-claim: Claim precedes work' names no capability under "
                      "openspec/specs. Did you mean 'work-claiming'?", out)

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
            - THEN it holds
            ## REMOVED Requirements
            ### Requirement: Old
            #### Scenario: Going away
            - THEN it holds
            """)
        self.write("openspec/changes/archive/old/specs/work-claiming/spec.md",
                   "### Requirement: A\n#### Scenario: Archived\n- THEN it holds\n")
        self.assertNotIn("Not built yet", self.run_cmd("report")[1])
        out = self.run_cmd("report", "--include-changes")[1]
        self.assertIn("| Not built yet (change: add-x) | none |", out)
        self.assertNotIn("Going away", out)
        self.assertNotIn("Archived", out)

    def test_include_changes_finds_tags_for_a_change_s_scenarios(self):
        self.tag_both()
        self.write("openspec/changes/add-x/specs/work-claiming/spec.md",
                   "## ADDED Requirements\n### Requirement: New\n#### Scenario: Fresh\n- THEN it holds\n#### Scenario: Stale\n- THEN it holds\n")
        self.write("src/fresh_test.go", f"// {AT} work-claiming: Fresh\n")
        code, out = self.run_cmd("report", "--include-changes")
        self.assertEqual(code, 0)
        self.assertIn("3 of 4 scenarios are tagged by a test.", out)
        self.assertIn("| Fresh (change: add-x) | src/fresh_test.go:1 |", out)
        self.assertIn("| Stale (change: add-x) | none |", out)

    def test_where_tags_were_found_lists_each_directory_sorted(self):
        self.tag_both()
        self.write("src/b/pay.go", f"// {AT} work-claiming: Claim precedes work\n")
        self.write("src/a/x.py", f"# {AT} work-claiming: Nope\n")
        self.write("src/a/y.py", f"# {AT} work-claiming: Gone {AT} work-claiming: Also gone\n")
        self.write("top.js", f"// {AT} work-claiming: Claim precedes work\n")
        self.write("src/a/untagged.py", "print('no tag here')\n")
        out = self.run_cmd("report")[1]
        section = out[out.index("### Where tags were found"):out.index("### Problems")]
        self.assertEqual(section, "### Where tags were found\n\n"
                         "| Directory | Files | Tags |\n| --- | --- | --- |\n"
                         "| . | 1 | 1 |\n| src/a | 2 | 3 |\n| src/b | 1 | 1 |\n| test | 1 | 2 |\n\n"
                         f"{st.RUNNER_EXCLUDES_HINT}\n\n")
        self.assertIn("ask your agent to add it to openspec/spec-trace-ignore.txt.", section)

    def test_where_tags_were_found_counts_tags_for_an_open_change(self):
        self.tag_both()
        self.write("openspec/changes/add-x/specs/work-claiming/spec.md",
                   "## ADDED Requirements\n### Requirement: New\n#### Scenario: Fresh\n- THEN it holds\n")
        self.write("pending/a.test.ts", f"// {AT} work-claiming: Fresh\n")
        for args in (["report"], ["report", "--include-changes"]):
            out = self.run_cmd(*args)[1]
            self.assertIn("| pending | 1 | 1 |", out, args)

    def test_where_tags_were_found_skips_a_line_that_only_mentions_the_word(self):
        self.tag_both()
        self.write("src/notes.js", "// the @scenario tag goes above a test\n")
        self.assertNotIn("| src |", self.run_cmd("report")[1])

    def test_where_tags_were_found_with_no_tags(self):
        out = self.run_cmd("report")[1]
        self.assertIn("### Where tags were found\n\nNo tags were found.\n", out)
        self.assertNotIn(st.RUNNER_EXCLUDES_HINT, out)

    def test_check_and_baseline_do_not_list_directories(self):
        self.tag_both()
        self.assertNotIn("Where tags were found", self.run_cmd("check")[1])
        self.assertNotIn("Where tags were found", self.run_cmd("baseline")[1])

    def test_problems_are_listed_after_the_tables(self):
        self.write("test/x.test.ts", f"// {AT} work-claiming: Nope\n")
        out = self.run_cmd("report")[1]
        self.assertIn("### Problems", out)
        self.assertIn("- test/x.test.ts:1: tag", out)


HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "scenario_hook.py")
CLONE = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
CONFIG_TEXT = "schema: spec-driven\n\n# Project context (optional)\n#   context: |\n"


class GitRepo(Repo):
    """A Repo that has an openspec/config.yaml."""

    def setUp(self):
        super().setUp()
        self.write("openspec/config.yaml", CONFIG_TEXT)


class AdoptionState(GitRepo):
    def state(self):
        return st.adoption_state(self.root)

    def test_no_openspec_directory_is_none(self):
        shutil.rmtree(os.path.join(self.root, "openspec"))
        self.assertIsNone(self.state())
        self.assertEqual(self.run_cmd("state"), (0, "n/a\n"))

    def test_neither_baseline_nor_decision_file_is_undecided(self):
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

    def test_the_ignore_file_is_not_adoption(self):
        self.write(st.IGNORE_FILE, "vendor/**\n")
        self.assertEqual(self.state(), st.UNDECIDED)

    def test_the_old_tests_file_is_not_read(self):
        self.write("openspec/spec-trace-tests.txt", "test/**\n")
        self.assertEqual(self.state(), st.UNDECIDED)

    def test_the_decision_file_is_declined(self):
        self.write(st.DECISION_FILE, "# why we declined\n\nadoption :  declined \n")
        self.assertEqual(self.state(), st.DECLINED)
        self.assertEqual(self.run_cmd("state"), (0, "declined\n"))

    def test_a_decision_file_with_a_byte_order_mark_is_declined(self):
        with open(os.path.join(self.root, st.DECISION_FILE), "wb") as f:
            f.write(b"\xef\xbb\xbfadoption: declined\n")
        self.assertEqual(self.state(), st.DECLINED)

    def test_an_unreadable_decision_file_is_reported_as_unreadable(self):
        os.makedirs(os.path.join(self.root, st.DECISION_FILE))
        self.assertEqual(self.state(), st.UNKNOWN)
        code, out = self.run_cmd("decline")
        self.assertEqual(code, 1)
        self.assertIn("cannot be read", out)
        self.assertNotIn("holds something other", out)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs a FIFO")
    def test_a_decision_file_that_is_a_fifo_is_unreadable_and_never_hangs(self):
        os.mkfifo(os.path.join(self.root, st.DECISION_FILE))
        script = os.path.join(HERE, "spec_trace.py")
        try:
            result = subprocess.run([sys.executable, script, "--root", self.root, "state"],
                                    capture_output=True, text=True, timeout=10)
        except subprocess.TimeoutExpired:
            self.fail("state hung reading a FIFO")
        self.assertEqual(result.stdout, "unknown\n")
        self.assertIn("cannot be read", result.stderr)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs a FIFO")
    def test_a_workflow_that_is_a_fifo_is_skipped_and_never_hangs(self):
        os.makedirs(os.path.join(self.root, ".github/workflows"))
        os.mkfifo(os.path.join(self.root, ".github/workflows/ci.yml"))
        script = os.path.join(HERE, "spec_trace.py")
        try:
            result = subprocess.run([sys.executable, script, "--root", self.root, "state"],
                                    capture_output=True, text=True, timeout=10)
        except subprocess.TimeoutExpired:
            self.fail("state hung reading a FIFO workflow")
        self.assertEqual(result.stdout, "undecided\n")

    def test_a_decision_file_saying_anything_else_is_unknown(self):
        for text in ("adoption: adopted\n", "", "adoption: declined\nother: 1\n",
                     "adoption declined\n"):
            self.write(st.DECISION_FILE, text)
            self.assertEqual(self.state(), st.UNKNOWN, text)
        code, out = self.run_cmd("state")
        self.assertEqual((code, out), (0, "unknown\n"))
        self.assertIn(st.DECISION_FILE, self.err)

    def test_the_old_marker_in_config_yaml_is_not_a_decision(self):
        self.write("openspec/config.yaml", CONFIG_TEXT + "# spec-trace: declined\n")
        self.assertEqual(self.state(), st.UNDECIDED)

    def test_adoption_wins_over_a_decision_file_left_behind(self):
        self.write(st.DECISION_FILE, "adoption: declined\n")
        self.write("openspec/spec-trace-baseline.txt", "")
        self.assertEqual(self.state(), st.ADOPTED)


class Decline(GitRepo):
    def test_writes_the_decision_file_and_leaves_config_yaml_alone(self):
        code, out = self.run_cmd("decline")
        self.assertEqual(code, 0)
        self.assertIn("Commit it", out)
        self.assertEqual(self.read(st.DECISION_FILE), "adoption: declined\n")
        self.assertEqual(self.read("openspec/config.yaml"), CONFIG_TEXT)
        self.assertEqual(st.adoption_state(self.root), st.DECLINED)

    def test_works_without_config_yaml(self):
        os.remove(os.path.join(self.root, "openspec/config.yaml"))
        self.assertEqual(self.run_cmd("decline")[0], 0)
        self.assertEqual(st.adoption_state(self.root), st.DECLINED)
        self.assertFalse(os.path.exists(os.path.join(self.root, "openspec/config.yaml")))

    def test_is_idempotent(self):
        self.write(st.DECISION_FILE, "# reason\nadoption: declined\n")
        code, out = self.run_cmd("decline")
        self.assertEqual(code, 0)
        self.assertIn("already declines", out)
        self.assertEqual(self.read(st.DECISION_FILE), "# reason\nadoption: declined\n")

    def test_dry_run_changes_nothing(self):
        code, out = self.run_cmd("decline", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("adoption: declined", out)
        self.assertFalse(os.path.exists(os.path.join(self.root, st.DECISION_FILE)))

    def test_a_decision_file_saying_anything_else_is_refused(self):
        self.write(st.DECISION_FILE, "adoption: maybe\n")
        code, out = self.run_cmd("decline")
        self.assertEqual(code, 1)
        self.assertIn("nothing was declined", out)
        self.assertEqual(self.read(st.DECISION_FILE), "adoption: maybe\n")

    def test_an_adopted_repository_is_refused(self):
        self.write("openspec/spec-trace-baseline.txt", "")
        code, out = self.run_cmd("decline")
        self.assertEqual(code, 1)
        self.assertIn("nothing was declined", out)
        self.assertFalse(os.path.exists(os.path.join(self.root, st.DECISION_FILE)))

    def test_no_openspec_directory_is_refused(self):
        shutil.rmtree(os.path.join(self.root, "openspec"))
        self.assertEqual(self.run_cmd("decline")[0], 2)

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

    def test_adopted_declined_and_unknown_repositories_are_silent(self):
        payload = {"tool_input": {"file_path": self.spec()}}
        self.write("openspec/spec-trace-baseline.txt", "")
        self.assertEqual(self.hook(payload), "")
        os.remove(os.path.join(self.root, "openspec/spec-trace-baseline.txt"))
        self.run_cmd("decline")
        self.assertEqual(self.hook(payload), "")
        self.assertEqual(self.hook(payload, host="cursor"), "")
        self.write(st.DECISION_FILE, "adoption: maybe\n")
        self.assertEqual(self.hook(payload), "")

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

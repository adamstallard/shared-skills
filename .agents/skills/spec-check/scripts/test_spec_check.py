#!/usr/bin/env python3
"""Tests for spec_check.py and spec-check's commit hook.

Standard library only:

    python3 test_spec_check.py

Each test builds a throwaway git repository in a temp directory, so nothing
here touches a real repository. Tests that need the OpenSpec CLI skip
unless OpenSpec 1.15.0 or later is on PATH.
"""

import json
import os
import pathlib
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "spec_check.py"
HOOK = HERE / "check-commit-trailer.sh"
SKILLS_PY = HERE.parent.parent / "manage-skills" / "scripts" / "skills.py"
VERIFY = HERE / "verify-staged.sh"
SKILLS = HERE.parent.parent
LIB = SKILLS.parent / "lib" / "commit-trailer" / "commit-with-trailers.sh"
BUG_HUNTER = SKILLS / "bug-hunter" / "scripts" / "commit-with-trailer.sh"
BUG_HUNTER_HOOK = SKILLS / "bug-hunter" / "scripts" / "check-commit-trailer.sh"

sys.path.insert(0, str(HERE))
import spec_check  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="t@example.com",
           OPENSPEC_TELEMETRY="0", DO_NOT_TRACK="1",
           # No test reaches GitHub. By default gh names a file nobody creates;
           # a test that needs gh points SPEC_CHECK_GH at its fake.
           SPEC_CHECK_GH=str(pathlib.Path(tempfile.gettempdir()) / "spec-check-no-gh"))


def openspec_version():
    """The OpenSpec CLI's version on PATH, as a tuple, or None."""
    exe = shutil.which("openspec")
    if exe is None:
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", subprocess.run([exe, "--version"], capture_output=True,
                                                         text=True).stdout)
    return tuple(map(int, m.groups())) if m else None


# spec-check reads requirements only through OpenSpec 1.15.0 or later.
OPENSPEC_VERSION = openspec_version()
HAS_OPENSPEC = OPENSPEC_VERSION is not None and OPENSPEC_VERSION >= (1, 15, 0)

MAIN_SPEC = """# cap Specification

## Purpose

What cap does.

## Requirements

### Requirement: Records are kept

The store SHALL keep every record it is given for at least thirty days after the last read.

#### Scenario: A record survives

- **WHEN** a record is written
- **THEN** it can be read for thirty days
"""

GOOD_PROPOSAL = """## Why

Records pile up (`src/app.py:5`).

## What Changes

- Records expire.

## Capabilities

### Modified Capabilities
- `cap`: records expire

## Impact

`src/app.py`.
"""

GOOD_DELTA = """## ADDED Requirements

### Requirement: Records expire

The store SHALL delete a record ninety days after its last read.

#### Scenario: An old record goes

- **WHEN** a record has not been read for ninety days
- **THEN** it is deleted
"""

TASKS = "## 1. Build\n\n- [ ] 1.1 Expire records\n"


class Repo:
    """A throwaway repository with one main spec and a ten-line source file."""

    def __init__(self, test):
        self.path = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-test-")).resolve()
        test.addCleanup(shutil.rmtree, self.path, ignore_errors=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "commit.gpgsign", "false")
        self.write("openspec/config.yaml", "schema: spec-driven\n")
        self.write("openspec/specs/cap/spec.md", MAIN_SPEC)
        self.write("src/app.py", "".join(f"line{i}\n" for i in range(1, 11)))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")

    def git(self, *args, check=True):
        r = subprocess.run(["git", *args], cwd=self.path, capture_output=True, text=True, env=ENV)
        if check and r.returncode != 0:
            raise AssertionError(r.stdout + r.stderr)
        return r.stdout.strip()

    def write(self, rel, text):
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def change(self, name, proposal=GOOD_PROPOSAL, delta=GOOD_DELTA, cap="cap"):
        self.write(f"openspec/changes/{name}/proposal.md", proposal)
        self.write(f"openspec/changes/{name}/specs/{cap}/spec.md", delta)
        self.write(f"openspec/changes/{name}/tasks.md", TASKS)

    def run(self, *args, cwd=None, stdin=None, env=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.path,
                              capture_output=True, text=True, env=env or ENV, input=stdin)

    def check(self, *args, env=None):
        return self.run("check", "--base", "main", "--no-validate", *args, env=env)


def kinds(result):
    return [line.split("[", 1)[1].split("]", 1)[0]
            for line in result.stdout.splitlines() if ": error [" in line or ": check [" in line]


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)

    def test_a_clean_change_passes(self):
        self.repo.change("good")
        r = self.repo.check("good")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(kinds(r), [])
        self.assertIn("0 error(s), 0 check(s) in good", r.stdout)

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_a_requirement_without_a_scenario_fails(self):
        self.repo.change("x", delta="## ADDED Requirements\n\n### Requirement: Bare\n\n"
                                    "The store SHALL do a thing.\n")
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(kinds(r), ["no-scenario"])
        self.assertIn("openspec/changes/x/specs/cap/spec.md:3: error [no-scenario]", r.stdout)

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_a_scenario_without_then_fails(self):
        self.repo.change("x", delta=GOOD_DELTA.replace("- **THEN** it is deleted\n", ""))
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(kinds(r), ["scenario-incomplete"])
        self.assertIn("has no THEN", r.stdout)

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_a_scenario_without_when_or_then_names_both(self):
        self.repo.change("x", delta=GOOD_DELTA.replace("- **WHEN** a record has not been read for ninety days\n", "")
                         .replace("- **THEN** it is deleted\n", "- it goes\n"))
        r = self.repo.check("x")
        self.assertIn("has no WHEN or THEN", r.stdout)

    def test_a_removed_requirement_needs_no_scenario(self):
        self.repo.change("x", delta=GOOD_DELTA + "\n## REMOVED Requirements\n\n### Requirement: Records are kept\n\n"
                                                 "**Reason**: gone. The store MUST NOT do it.\n")
        self.assertEqual(kinds(self.repo.check("x")), [])

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_a_rule_stated_in_two_places_fails(self):
        dup = ("The store SHALL keep every record it is given for at least thirty days "
               "after the last read.")
        self.repo.change("x", delta=GOOD_DELTA.replace(
            "The store SHALL delete a record ninety days after its last read.",
            "The store SHALL delete a record ninety days after its last read. " + dup))
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(kinds(r), ["duplicate"])
        self.assertIn('also stated in "Records are kept" at openspec/specs/cap/spec.md:11', r.stdout)

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_a_rule_copied_into_two_changes_is_reported_in_each(self):
        rule = ("Every command SHALL be redacted of each credential the process knows "
                "before it is written anywhere.")
        for name, req in (("a", "Log redacts"), ("b", "Table redacts")):
            self.repo.change(name, delta=f"## ADDED Requirements\n\n### Requirement: {req}\n\n{rule}\n\n"
                                         "#### Scenario: s\n\n- **WHEN** w\n- **THEN** t\n")
        r = self.repo.check()
        self.assertEqual(kinds(r), ["duplicate", "duplicate"])

    def test_a_modified_requirement_may_restate_the_one_it_modifies(self):
        self.repo.change("x", delta=MAIN_SPEC.split("## Requirements\n", 1)[1]
                         .replace("Records are kept", "Records are kept")
                         .join(["## MODIFIED Requirements\n", ""]))
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_citation_to_a_missing_file_fails(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "src/gone.py:5"))
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(kinds(r), ["citation"])
        self.assertIn("src/gone.py does not exist on main", r.stdout)

    def test_a_citation_past_the_end_of_the_file_fails(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "src/app.py:8-14"))
        r = self.repo.check("x")
        self.assertEqual(kinds(r), ["citation"])
        self.assertIn("src/app.py has 10 lines on main", r.stdout)

    def test_citations_are_checked_against_the_base_not_the_working_tree(self):
        self.repo.write("src/app.py", "".join(f"line{i}\n" for i in range(1, 40)))
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "src/app.py:30"))
        self.assertEqual(kinds(self.repo.check("x")), ["citation"])

    def test_a_bare_file_name_resolves_when_one_file_has_it(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "app.py:5"))
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_url_with_a_port_is_not_a_citation(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL + "\nSee http://example.com:8080 and example.com:443.\n")
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_branch_is_checked_without_checking_it_out(self):
        self.repo.git("checkout", "-q", "-b", "spec/x")
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "src/gone.py:5"))
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "spec")
        self.repo.git("checkout", "-q", "main")
        self.assertFalse((self.repo.path / "openspec/changes/x").exists())
        r = self.repo.check("--ref", "spec/x", "x")
        self.assertEqual(kinds(r), ["citation"])
        self.assertIn("read from spec/x", r.stdout)

    def test_an_unknown_change_cannot_run(self):
        r = self.repo.check("nope")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no open change named 'nope'", r.stderr)

    def test_the_main_specs_can_be_checked(self):
        r = self.repo.check("specs")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("in openspec/specs", r.stdout)

    def test_json_output(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "src/gone.py:5"))
        data = json.loads(self.repo.check("x", "--json").stdout)
        self.assertEqual(data["errors"], 1)
        self.assertEqual(data["findings"][0]["kind"], "citation")

    def test_validate_says_not_run_without_the_cli(self):
        self.repo.change("good")
        bin_dir = self.repo.path.parent / f"{self.repo.path.name}-bin"
        bin_dir.mkdir()
        self.addCleanup(shutil.rmtree, bin_dir, ignore_errors=True)
        (bin_dir / "git").symlink_to(shutil.which("git"))
        env = dict(ENV, PATH=str(bin_dir))
        r = subprocess.run([sys.executable, str(SCRIPT), "check", "--base", "main", "good"],
                           cwd=self.repo.path, capture_output=True, text=True, env=env)
        self.assertIn("openspec validate --strict (good): not run: install OpenSpec 1.15.0 or later "
                      "(the openspec CLI is not on PATH)", r.stdout, r.stderr)

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_validate_runs_and_its_issues_are_findings(self):
        self.repo.change("good")
        self.repo.change("bad", delta=GOOD_DELTA.replace("SHALL", "will"))
        r = self.repo.run("check", "--base", "main", "good", "bad")
        self.assertIn("openspec validate --strict (good): passed", r.stdout)
        self.assertIn("openspec-validate", r.stdout)
        self.assertIn("should contain SHALL or MUST", r.stdout)
        self.assertEqual(r.returncode, 1)


def added_req(name, body, cap_scenario="s"):
    return (f"## ADDED Requirements\n\n### Requirement: {name}\n\n{body}\n\n"
            f"#### Scenario: {cap_scenario}\n\n- **WHEN** w\n- **THEN** t\n")


MAIN_RULE = "The store SHALL keep every record it is given for at least thirty days after the last read."


class ArchiveRefusalTests(unittest.TestCase):
    """A change with no `Builds on:` line is archived alone, by the real
    `openspec archive`, into a scratch copy of the tree's specs, and each
    refusal is an archive error (issue #37, item 4)."""

    DELTA = "openspec/changes/x/specs/cap/spec.md"

    def setUp(self):
        if not HAS_OPENSPEC:
            self.skipTest("needs OpenSpec 1.15.0 or later")
        self.repo = Repo(self)

    def refused(self, r, name, quote):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        hits = [l for l in errors(r) if "[archive]" in l]
        self.assertEqual(len(hits), 1, r.stdout)
        self.assertTrue(hits[0].startswith(self.DELTA + ":"), hits[0])
        self.assertIn(f'"{name}" in cap', hits[0])
        self.assertIn(quote, hits[0])
        self.assertIn("openspec archive (x): refused", r.stdout)
        return hits[0]

    def test_an_added_name_main_already_has_is_an_error(self):
        self.repo.change("x", delta=added_req("Records are kept", "The store SHALL keep records for a year."))
        line = self.refused(self.repo.check("x"), "Records are kept", "already exists")
        self.assertTrue(line.startswith(self.DELTA + ":3:"), line)  # the ADDED header

    def test_a_rename_onto_a_taken_name_is_an_error(self):
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n### Requirement: Records expire\n\n"
                        "The store SHALL delete a record ninety days after its last read.\n\n"
                        "#### Scenario: An old record goes\n\n- **WHEN** w\n- **THEN** t\n")
        self.repo.change("x", delta="## RENAMED Requirements\n\n- FROM: `### Requirement: Records are kept`\n"
                                    "- TO: `### Requirement: Records expire`\n")
        self.refused(self.repo.check("x"), "Records expire", "target already exists")

    def test_a_modification_that_drops_a_scenario_is_an_error(self):
        self.repo.change("x", delta="## MODIFIED Requirements\n\n### Requirement: Records are kept\n\n"
                                    "The store SHALL keep every record for a year.\n\n"
                                    "#### Scenario: A year passes\n\n- **WHEN** a year passes\n"
                                    "- **THEN** the record is still there\n")
        self.refused(self.repo.check("x"), "Records are kept",
                     "current spec contains scenario(s) not present in the modified block")

    def test_a_change_that_fits_passes_and_says_so(self):
        self.repo.change("x")
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("openspec archive (x): passed", r.stdout)
        self.assertEqual(json.loads(self.repo.check("x", "--json").stdout)["openspec_archive"],
                         {"x": "passed"})

    def test_each_change_is_archived_alone(self):
        # Two open changes add the same name. Either fits main alone; together
        # they would not, but only the checked change is archived.
        self.repo.change("x", delta=added_req("Audit trail", "Every change SHALL be written to the audit log."))
        self.repo.change("y", delta=added_req("Audit trail", "Every read SHALL be written to the access log."))
        r = self.repo.check()
        self.assertNotIn("[archive]", r.stdout)
        self.assertIn("openspec archive (x): passed", r.stdout)
        self.assertIn("openspec archive (y): passed", r.stdout)

    def test_the_tree_is_left_alone(self):
        self.repo.change("x")
        self.repo.check("x")
        self.assertEqual(self.repo.git("status", "--porcelain"),
                         "?? openspec/changes/")
        self.assertEqual((self.repo.path / "openspec/specs/cap/spec.md").read_text(), MAIN_SPEC)


PURPOSE = "Keeps the audit log every reviewer reads when a record changes owner."


def purposed(purpose, delta=GOOD_DELTA):
    """delta with `purpose` written under a `## Purpose` above it."""
    return f"## Purpose\n\n{purpose}\n\n" + delta


class NewCapabilityPurposeTests(unittest.TestCase):
    """A delta that creates a capability carries the new spec's Purpose:
    `openspec archive` seeds it from the delta's `## Purpose`, and writes a
    placeholder nobody replaces when there is none. Archive ignores a delta
    Purpose for a capability that exists, so that is a check, unless it
    matches the spec's Purpose."""

    DELTA = "openspec/changes/x/specs/audit/spec.md"

    def setUp(self):
        if not HAS_OPENSPEC:
            self.skipTest("needs OpenSpec 1.15.0 or later")
        self.repo = Repo(self)

    def purpose(self, delta, cap="audit"):
        """The one purpose finding for change x, and the result."""
        self.repo.change("x", delta=delta, cap=cap)
        r = self.repo.check("x")
        hits = [l for l in r.stdout.splitlines() if "[purpose]" in l]
        self.assertEqual(len(hits), 1, r.stdout + r.stderr)
        self.assertIn("openspec archive (x): passed", r.stdout)
        return hits[0], r

    def error(self, delta, line, why):
        hit, r = self.purpose(delta)
        self.assertEqual(r.returncode, 1, r.stdout)
        where = f"{self.DELTA}:{line}:" if line else f"{self.DELTA}:"
        self.assertTrue(hit.startswith(where + " error [purpose] x creates audit, and "), hit)
        self.assertIn(why, hit)
        self.assertIn("Write what audit is for under `## Purpose` in this delta, in 50 characters or more", hit)
        return hit

    def test_no_purpose_is_an_error(self):
        hit = self.error(GOOD_DELTA, 0, "its delta has no `## Purpose`")
        self.assertIn('"TBD - created by archiving change x. Update Purpose after archive."', hit)

    def test_an_empty_purpose_is_an_error_at_its_header(self):
        self.error("## Purpose\n\n" + GOOD_DELTA, 1, "its `## Purpose` is empty")

    def test_a_purpose_that_is_only_a_comment_is_empty(self):
        self.error(purposed("<!-- say what audit is for, at some length, before review -->"), 1,
                   "its `## Purpose` is empty")

    def test_a_purpose_only_in_a_fence_is_missing(self):
        self.error("```\n## Purpose\n\n" + PURPOSE + "\n```\n\n" + GOOD_DELTA, 0,
                   "its delta has no `## Purpose`")

    def test_a_tbd_marker_is_an_error(self):
        self.error(purposed("TBD - write this once we know what the audit capability covers."), 1,
                   "is a placeholder")

    def test_a_lowercase_todo_with_punctuation_is_an_error(self):
        self.error(purposed("todo: write this once we know what the audit capability covers."), 1,
                   "is a placeholder")

    def test_the_placeholder_sentence_copied_in_is_an_error(self):
        self.error(purposed("TBD - created by archiving change y. Update Purpose after archive."), 1,
                   "is a placeholder")

    def test_a_purpose_under_fifty_characters_is_an_error(self):
        self.error(purposed("Keeps the audit log."), 1, "under 50 characters")

    def test_a_purpose_archive_would_not_carry_is_an_error(self):
        hit = self.error(purposed(PURPOSE + " <!-- reviewed -->"), 1, "would leave that spec unreadable")
        self.assertIn('"TBD - created by archiving change x. Update Purpose after archive."', hit)

    def test_a_real_purpose_passes(self):
        self.repo.change("x", delta=purposed(PURPOSE), cap="audit")
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(kinds(r), [])

    def test_a_spanish_sentence_starting_todo_passes(self):
        self.repo.change("x", delta=purposed("Todo el registro de auditoría que lee quien revisa un cambio."),
                         cap="audit")
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_purpose_for_an_existing_capability_is_a_check(self):
        hit, r = self.purpose(purposed(PURPOSE), cap="cap")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(hit.startswith("openspec/changes/x/specs/cap/spec.md:1: check [purpose] "
                                       "cap already exists, so `openspec archive` will ignore this "
                                       "`## Purpose`"), hit)
        self.assertIn("edit openspec/specs/cap/spec.md directly", hit)

    def test_an_existing_capability_needs_no_purpose(self):
        self.repo.change("x")
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(kinds(r), [])

    def test_each_new_capability_is_judged_on_its_own(self):
        self.repo.change("x", delta=purposed(PURPOSE), cap="audit")
        self.repo.write("openspec/changes/x/specs/search/spec.md", GOOD_DELTA)
        r = self.repo.check("x")
        hits = [l for l in r.stdout.splitlines() if "[purpose]" in l]
        self.assertEqual(len(hits), 1, r.stdout)
        self.assertTrue(hits[0].startswith("openspec/changes/x/specs/search/spec.md: error [purpose] "
                                           "x creates search"), hits[0])

    def test_a_refused_delta_does_not_hide_another_capability(self):
        self.repo.change("x", delta=GOOD_DELTA, cap="audit")
        self.repo.write("openspec/changes/x/specs/search/spec.md", modified("Records are kept", SEARCH))
        r = self.repo.check("x")
        self.assertEqual(kinds(r), ["archive", "purpose"], r.stdout)
        self.assertIn("openspec/changes/x/specs/search/spec.md:3: error [archive]", r.stdout)
        self.assertIn(f"{self.DELTA}: error [purpose] x creates audit, and its delta has no", r.stdout)
        self.assertNotIn("x creates search", r.stdout)

    def test_a_purpose_header_behind_a_byte_order_mark_is_not_read(self):
        # OpenSpec matches `## Purpose` on the raw first line, so a byte-order
        # mark hides it and archive writes the placeholder.
        hit = self.error("\ufeff" + purposed(PURPOSE), 0, "its delta has no `## Purpose` that `openspec archive` reads")
        self.assertNotIn("is a placeholder", hit)

    def test_a_purpose_that_repeats_the_existing_one_is_not_reported(self):
        self.repo.change("x", delta=purposed("What cap does."), cap="cap")
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(kinds(r), [])

    def test_a_repeated_purpose_with_a_fence_in_a_list_is_not_reported(self):
        # OpenSpec closes a fence at any indentation, so the column-0 fence
        # below ends the block, and both Purposes end at the next `##`. A
        # CommonMark reader would keep the fence open to the end of the file,
        # run each Purpose on into its requirements, and report a check for
        # two equal Purposes.
        purpose = (f"{PURPOSE}\n\n- An example record:\n  ```json\n  {{\"id\": 1}}\n```")
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace("What cap does.", purpose))
        self.repo.git("commit", "-qam", "purpose")
        self.repo.change("x", delta=purposed(purpose), cap="cap")
        r = self.repo.check("x")
        self.assertEqual(kinds(r), [], r.stdout + r.stderr)

    def test_a_repeated_purpose_archive_reads_as_equal_is_not_reported(self):
        # Archive trims a byte-order mark off the Purpose before comparing.
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace("What cap does.", "\ufeff" + PURPOSE))
        self.repo.git("commit", "-qam", "purpose")
        self.repo.change("x", delta=purposed(PURPOSE), cap="cap")
        r = self.repo.check("x")
        self.assertEqual(kinds(r), [], r.stdout + r.stderr)

    def test_a_fence_opener_ending_in_a_line_separator_hides_the_purpose(self):
        # A backtick in a fence's info string makes the line inline code, not
        # a fence. JavaScript's `.` stops at U+2028, so OpenSpec never sees the
        # backtick after it, reads the line as a fence, and finds no prose.
        self.error(purposed("```\u2028`\n" + PURPOSE + "\n```"), 1, "its `## Purpose` is empty")

    def test_purposes_that_differ_after_a_fenced_heading_are_reported(self):
        fence = f"{PURPOSE}\n\n```\n## example\n```\n\n"
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace("What cap does.", fence + "Old tail."))
        self.repo.git("commit", "-qam", "purpose")
        hit, _ = self.purpose(purposed(fence + "New tail."), cap="cap")
        self.assertIn("check [purpose] cap already exists", hit)

    def test_purposes_that_differ_only_in_a_comment_are_reported(self):
        self.repo.write("openspec/specs/cap/spec.md",
                        MAIN_SPEC.replace("What cap does.", PURPOSE + " <!-- owner: a -->"))
        self.repo.git("commit", "-qam", "purpose")
        hit, _ = self.purpose(purposed(PURPOSE + " <!-- owner: b -->"), cap="cap")
        self.assertIn("check [purpose] cap already exists", hit)

    def test_purpose_headers_match_openspec_s_pattern(self):
        # Repo's main spec (MAIN_SPEC) gives the existing capability `cap` the
        # Purpose "What cap does.". OpenSpec's `openspec archive` warns that a
        # delta's Purpose is ignored when the capability exists and the delta
        # has a `## Purpose` with prose that differs from the existing one.
        # spec-check should print a `[purpose]` line in exactly those cases.
        # OpenSpec is JavaScript, so its whitespace rules are JavaScript's,
        # where Python's strip() would get the last two cases backwards.
        cases = [
            # No space after `##`: OpenSpec does not see a header.
            ("##Purpose\n\nOther.\n\n", False),
            # Words after `Purpose`: OpenSpec does not see a header.
            ("## Purpose of this\n\nOther.\n\n", False),
            # `###` does not end the section, so `### Note` and "More." stay in
            # the body, which then differs from "What cap does.".
            ("## Purpose\n\nWhat cap does.\n\n### Note\n\nMore.\n\n", True),
            # JavaScript's trim() removes U+FEFF, so the section has no prose.
            ("## Purpose\n\n\ufeff\n\n", False),
            # JavaScript's trim() keeps U+0085, so the section has prose.
            ("## Purpose\n\n\x85\n\n", True),
        ]
        for block, reported in cases:
            with self.subTest(block=block):
                self.repo.change("x", delta=block + GOOD_DELTA, cap="cap")
                r = self.repo.check("x")
                self.assertEqual("[purpose]" in r.stdout, reported, r.stdout + r.stderr)

    def test_a_spec_path_that_is_a_directory_gets_only_the_archive_error(self):
        self.repo.write("openspec/specs/audit/spec.md/notes.md", "notes\n")
        self.repo.change("x", delta=purposed(PURPOSE), cap="audit")
        r = self.repo.check("x")
        self.assertEqual(kinds(r), ["archive"], r.stdout)

    def test_a_purpose_closed_by_the_other_comment_terminator_is_empty(self):
        self.error(purposed("<!-- say what audit is for --!>"), 1, "its `## Purpose` is empty")

    def test_a_purpose_that_is_only_a_code_block_is_empty(self):
        self.error(purposed("```\nAudit records everything a reviewer changes, by seat.\n```"), 1,
                   "its `## Purpose` is empty")

    def test_prose_after_the_first_comment_terminator_counts(self):
        hit, r = self.purpose(purposed("<!-- a --> Lets reviewers search the audit log by seat --!>"),
                              cap="cap")
        self.assertIn("check [purpose] cap already exists", hit)

    def test_an_unclosed_comment_hides_the_purpose_below_it(self):
        self.repo.change("x", delta="<!-- draft\n\n" + purposed(PURPOSE), cap="cap")
        self.assertNotIn("[purpose]", self.repo.check("x").stdout)

    def test_without_the_cli_it_is_not_run(self):
        self.repo.change("x", delta=GOOD_DELTA, cap="audit")
        r = self.repo.check("x", env=dict(ENV, PATH=git_only_path(self)))
        self.assertNotIn("[purpose]", r.stdout)
        self.assertIn("openspec archive (x): not run", r.stdout)


class SameNameDuplicateTests(unittest.TestCase):
    """A same-name pair may share sentences only when one of the two is a
    MODIFIED requirement in the other's capability (issue #37, item 4)."""

    def setUp(self):
        self.repo = Repo(self)

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_an_added_requirement_repeating_main_under_its_name_is_a_duplicate(self):
        self.repo.change("x", delta=added_req("Records are kept", MAIN_RULE))
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("duplicate", kinds(r))
        self.assertIn('also stated in "Records are kept" at openspec/specs/cap/spec.md:11', r.stdout)

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_the_same_name_in_another_capability_is_a_duplicate(self):
        self.repo.change("x", delta=purposed(PURPOSE, added_req("Records are kept", MAIN_RULE)),
                         cap="archive-store")
        r = self.repo.check("x")
        self.assertEqual(kinds(r), ["duplicate"], r.stdout)

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_a_modification_in_another_capability_is_a_duplicate(self):
        self.repo.change("x", delta=MAIN_SPEC.split("## Requirements\n", 1)[1]
                         .join(["## MODIFIED Requirements\n", ""]), cap="archive-store")
        self.assertIn("duplicate", kinds(self.repo.check("x")))

    def test_two_changes_modifying_one_requirement_are_not_duplicates(self):
        for name in ("x", "y"):
            self.repo.change(name, delta=MAIN_SPEC.split("## Requirements\n", 1)[1]
                             .join(["## MODIFIED Requirements\n", ""]))
        self.assertEqual(kinds(self.repo.check()), [])

    def test_the_main_spec_is_not_a_duplicate_of_an_open_modification(self):
        self.repo.change("x", delta=MAIN_SPEC.split("## Requirements\n", 1)[1]
                         .join(["## MODIFIED Requirements\n", ""]))
        self.assertEqual(kinds(self.repo.check("specs")), [])


class FoundByBugHunterGapTests(unittest.TestCase):
    """Regressions found by bug-hunter's run over the issue #37 changes."""

    def setUp(self):
        self.repo = Repo(self)

    def test_a_moved_requirement_quoted_in_its_removal_is_not_a_duplicate(self):
        self.repo.change("x", delta="## REMOVED Requirements\n\n### Requirement: Records are kept\n\n"
                                    "**Reason**: moved to retention.\n\n" + MAIN_RULE + "\n")
        self.repo.write("openspec/changes/x/specs/retention/spec.md",
                        added_req("Records are kept", MAIN_RULE))
        self.assertNotIn("duplicate", kinds(self.repo.check("x")))

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_lines_after_a_stray_heading_are_read_as_openspec_show_reads_them(self):
        # `openspec show` ends the scenario at the stray heading, so the THEN
        # line under it is in no scenario.
        self.repo.change("x", delta="## ADDED Requirements\n\n### Requirement: Records expire\n\n"
                                    "The store SHALL delete a record ninety days after its last read.\n\n"
                                    "#### Scenario: An old record goes\n\n- **WHEN** a record has not been read\n\n"
                                    "### Notes\n\n- **THEN** it is deleted\n")
        self.assertEqual(kinds(self.repo.check("x")), ["scenario-incomplete"])


def fake_openspec(test, version, delegate):
    """A PATH directory holding git, node and an `openspec` that reports
    version. With delegate it runs the real CLI for anything else; without,
    it fails as a CLI too old for --json does."""
    d = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-bin-"))
    test.addCleanup(shutil.rmtree, d, ignore_errors=True)
    (d / "git").symlink_to(shutil.which("git"))
    if shutil.which("node"):
        (d / "node").symlink_to(shutil.which("node"))
    rest = (f'exec "{shutil.which("openspec")}" "$@"\n' if delegate
            else "echo \"error: unknown option '--json'\" >&2\nexit 1\n")
    f = d / "openspec"
    f.write_text(f'#!/bin/sh\n[ "$1" = --version ] && {{ echo {version}; exit 0; }}\n' + rest)
    f.chmod(0o755)
    return d


def git_only_path(test):
    """A PATH directory holding git and nothing else."""
    d = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-path-"))
    test.addCleanup(shutil.rmtree, d, ignore_errors=True)
    (d / "git").symlink_to(shutil.which("git"))
    return d


NO_SCENARIO = ("## ADDED Requirements\n\n### Requirement: Invoices are kept\n\n"
               "The store SHALL keep invoices for a year.\n")


class CliMinimumTests(unittest.TestCase):
    """spec-check reads requirements only through OpenSpec 1.15.0 or later.
    Without it, every check that needs a requirement is reported as not run
    (Adam, 2026-10-31)."""

    NEEDS = "not run: install OpenSpec 1.15.0 or later"

    def setUp(self):
        self.repo = Repo(self)
        self.repo.change("x", delta=NO_SCENARIO)

    def test_without_the_cli_the_requirement_checks_are_not_run(self):
        r = self.repo.run("check", "--base", "main", "x",
                          env=dict(ENV, PATH=str(git_only_path(self))))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("[no-scenario]", r.stdout)
        why = f"{self.NEEDS} (the openspec CLI is not on PATH)"
        self.assertIn(f"requirement checks (openspec show): {why}", r.stdout)
        self.assertIn(f"openspec archive (x): {why}", r.stdout)
        self.assertIn(f"openspec validate --strict (x): {why}", r.stdout)

    def test_the_json_report_says_the_requirement_checks_were_not_run(self):
        r = self.repo.check("x", "--json", env=dict(ENV, PATH=str(git_only_path(self))))
        self.assertTrue(json.loads(r.stdout)["openspec_show"].startswith(self.NEEDS), r.stdout)

    def test_a_cli_older_than_1_15_0_is_not_used(self):
        r = self.repo.run("check", "--base", "main", "x",
                          env=dict(ENV, PATH=str(fake_openspec(self, "1.14.3", delegate=False))))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"requirement checks (openspec show): {self.NEEDS} (this one is 1.14.3)", r.stdout)
        self.assertIn(f"openspec archive (x): {self.NEEDS}", r.stdout)
        self.assertNotIn("unknown option", r.stdout)

    def test_a_cli_whose_version_cannot_be_read_is_not_used(self):
        r = self.repo.check("x", env=dict(ENV, PATH=str(fake_openspec(self, "unknown", delegate=False))))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("`openspec --version` printed no version", r.stdout)

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_a_cli_at_exactly_1_15_0_is_used(self):
        r = self.repo.check("x", env=dict(ENV, PATH=str(fake_openspec(self, "1.15.0", delegate=True))))
        self.assertIn("[no-scenario]", r.stdout, r.stdout + r.stderr)
        self.assertIn("openspec archive (x): passed", r.stdout)
        self.assertNotIn("requirement checks", r.stdout)

    def stacked(self):
        s = Stack(self, openspec=False)
        s.dependency(171, "a-change", modified("Records are kept", KEPT, SEAT))
        s.stacked(SEARCH_REQ, "a-change (acme/widgets#171)")
        return s

    def test_a_stacked_change_without_the_cli_is_a_stack_error(self):
        s = self.stacked()
        out = s.repo.check("lore-search", env=dict(s.env(), PATH=str(git_only_path(self))))
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        line = [l for l in out.stdout.splitlines() if "error [stack]" in l]
        self.assertEqual(len(line), 1, out.stdout)
        self.assertIn(f"{self.NEEDS} (the openspec CLI is not on PATH)", line[0])
        self.assertIn("duplicate and drift checks did not run", line[0])

    def test_a_stacked_change_with_an_old_cli_is_a_stack_error(self):
        s = self.stacked()
        d = fake_openspec(self, "1.14.0", delegate=False)
        out = s.repo.check("lore-search", env=dict(s.env(), PATH=str(d)))
        self.assertEqual(out.returncode, 1, out.stdout)
        line = [l for l in out.stdout.splitlines() if "error [stack]" in l]
        self.assertEqual(len(line), 1, out.stdout)
        self.assertIn(f"{self.NEEDS} (this one is 1.14.0)", line[0])
        self.assertIn(f"openspec archive (lore-search): {self.NEEDS}", out.stdout)


class RelayedFromValidateTests(unittest.TestCase):
    """What a delta drops or misfiles is reported by `openspec validate
    --strict`, with OpenSpec's own line and message; spec-check adds advice
    only to a stray heading (Adam, 2026-10-31)."""

    MODIFY = ("\n### Requirement: Records are kept\n\n"
              "The store SHALL keep every record for a year.\n\n"
              "#### Scenario: A record survives\n\n- **WHEN** w\n- **THEN** t\n")
    STRAY = ("## ADDED Requirements\n\n### Requirement: Records expire\n\n"
             "The store SHALL delete a record ninety days after its last read.\n\n"
             "### Retention details\n\nNinety days, counted from the last read.\n\n"
             "#### Scenario: An old record goes\n\n- **WHEN** a record has not been read\n"
             "- **THEN** it is deleted\n")
    STRAY_IN_MODIFIED = ("## MODIFIED Requirements\n\n### Requirement: Records are kept\n\n"
                         "The store SHALL keep every record for a year.\n\n"
                         "#### Scenario: A record survives\n\n- **WHEN** w\n- **THEN** t\n\n"
                         "### Records are audited\n\nThe store SHALL log each read.\n\n"
                         "#### Scenario: A read is logged\n\n- **WHEN** w\n- **THEN** t\n")
    AUDITED = ("\n### Requirement: Records are audited\n\nThe store SHALL log each write.\n\n"
               "#### Scenario: A write is logged\n\n- **WHEN** w\n- **THEN** t\n")

    def setUp(self):
        if not HAS_OPENSPEC:
            self.skipTest("needs OpenSpec 1.15.0 or later")
        self.repo = Repo(self)

    def validated(self, delta):
        self.repo.change("x", delta=delta)
        return self.repo.run("check", "--base", "main", "x")

    def relayed(self, r):
        return [l for l in r.stdout.splitlines() if "[openspec-validate]" in l]

    def test_a_misspelt_section_title_is_reported_at_its_lines(self):
        r = self.validated(GOOD_DELTA + "\n## MODIFIED Requirements:\n" + self.MODIFY)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(set(kinds(r)), {"openspec-validate"}, r.stdout)
        self.assertIn('spec.md:12: error [openspec-validate] Section "## MODIFIED Requirements:" is not '
                      "carried into the main spec by archive", r.stdout)
        self.assertIn('spec.md:14: error [openspec-validate] Requirement "Records are kept" is under '
                      '"## MODIFIED Requirements:"', r.stdout)

    def test_a_section_of_plain_text_is_reported(self):
        r = self.validated(GOOD_DELTA + "\n## Notes\n\nPlain words here.\n")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('spec.md:12: error [openspec-validate] Section "## Notes"', r.stdout)

    def test_text_above_the_first_section_is_reported(self):
        r = self.validated("Intro line.\n\n" + GOOD_DELTA)
        self.assertIn('spec.md:1: error [openspec-validate] Text above the first "## " section', r.stdout)

    def test_a_requirement_above_the_first_section_is_reported_and_not_read(self):
        r = self.validated(NO_SCENARIO.split("\n", 2)[2] + "\n" + GOOD_DELTA)
        self.assertIn('spec.md:1: error [openspec-validate] Requirement "Invoices are kept" is above '
                      'the first "## " section', r.stdout)
        self.assertNotIn("[no-scenario]", r.stdout)

    def test_a_stray_heading_in_an_addition_is_relayed_with_advice(self):
        r = self.validated(self.STRAY)
        line = self.relayed(r)[0]
        self.assertTrue(line.startswith("openspec/changes/x/specs/cap/spec.md:7: check [openspec-validate] "
                                        'Header "### Retention details" in ADDED Requirements'), line)
        self.assertIn('move it to "## ADDED Requirements" as "### Requirement: Retention details"', line)

    def test_a_stray_heading_naming_a_requirement_main_lacks_says_to_add_it(self):
        line = self.relayed(self.validated(self.STRAY_IN_MODIFIED))[0]
        self.assertIn('move it to "## ADDED Requirements" as "### Requirement: Records are audited"', line)

    def test_a_stray_heading_naming_a_requirement_main_has_says_to_modify_it(self):
        # Added under its own name, it would be refused: main already has it.
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + self.AUDITED)
        self.repo.git("commit", "-qam", "audited")
        line = self.relayed(self.validated(self.STRAY_IN_MODIFIED))[0]
        self.assertNotIn("ADDED Requirements as", line)
        self.assertIn('restate it as "### Requirement: Records are audited" under '
                      '"## MODIFIED Requirements"', line)

    def test_a_stray_heading_ending_in_a_hash_keeps_its_name(self):
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n" + '### Requirement: Builds with C#\n\nThe tool SHALL build with C#.\n\n#### Scenario: Builds\n\n- **WHEN** w\n- **THEN** t\n')
        self.repo.git("commit", "-qam", "c sharp")
        line = self.relayed(self.validated('## MODIFIED Requirements\n\n### Requirement: Records are kept\n\nThe store SHALL keep every record for a year.\n\n#### Scenario: A record survives\n\n- **WHEN** w\n- **THEN** t\n\n### Builds with C#\n\nThe tool SHALL build with C# 12.\n\n#### Scenario: Builds\n\n- **WHEN** w\n- **THEN** t\n'))[0]
        self.assertIn('"### Requirement: Builds with C#" under "## MODIFIED Requirements"', line)

    def test_a_stray_heading_in_a_complete_stack_is_advised_from_the_stack(self):
        s = Stack(self)
        s.dependency(171, "a-change", "## ADDED Requirements\n\n### Requirement: Records are audited\n\n"
                     "The store SHALL log each read.\n\n#### Scenario: A read is logged\n\n"
                     "- **WHEN** w\n- **THEN** t\n")
        s.stacked("## MODIFIED Requirements\n\n### Requirement: Records are kept\n\n" + KEPT +
                  "\n\n#### Scenario: A record survives\n\n- **WHEN** a record is written\n"
                  "- **THEN** it can be read for thirty days\n\n### Records are audited\n\n"
                  "The store SHALL log each read and write.\n", "a-change (acme/widgets#171)")
        out = s.repo.run("check", "--base", "main", "lore-search", env=s.env())
        line = self.relayed(out)[0]
        self.assertIn('restate it as "### Requirement: Records are audited" under '
                      '"## MODIFIED Requirements"; otherwise', line)
        self.assertNotIn("if the specs already have", line)

    def test_a_stray_heading_in_a_main_spec_leaves_its_requirement_without_a_scenario(self):
        # `openspec show` ends the requirement at the heading, so the
        # scenario after it belongs to no requirement.
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace(
            "#### Scenario: A record survives", "### Retention details\n\nThirty days.\n\n"
            "#### Scenario: A record survives"))
        r = self.repo.run("check", "--base", "main", "specs")
        self.assertIn("openspec/specs/cap/spec.md:9: error [no-scenario]", r.stdout)
        self.assertIn("[openspec-validate]", r.stdout)

    def test_a_bare_section_marker_before_a_scenario_leaves_no_scenario(self):
        r = self.validated('## ADDED Requirements\n\n### Requirement: Records are audited\n\nThe store SHALL log each read.\n\n## \n\n#### Scenario: A read is logged\n\n- **WHEN** w\n- **THEN** t\n')
        self.assertIn('error [no-scenario] requirement "Records are audited"', r.stdout)
        self.assertIn('"Records are audited" must include at least one scenario', r.stdout)


class OpenSpecReadingTests(unittest.TestCase):
    """spec-check reads a delta as `openspec show` reads it, and finds lines
    by searching for what it names (Adam, 2026-10-31)."""

    def setUp(self):
        if not HAS_OPENSPEC:
            self.skipTest("needs OpenSpec 1.15.0 or later")
        self.repo = Repo(self)

    def check_delta(self, delta, *args):
        self.repo.change("x", delta=delta)
        return self.repo.check("x", *args)

    def test_a_fenced_section_line_inside_a_requirement_is_its_text(self):
        self.repo.change("x", delta='## ADDED Requirements\n\n### Requirement: Records are exported\n\nThe store SHALL export records as markdown like this:\n\n```markdown\n## Export\n```\n\n#### Scenario: An export is written\n\n- **WHEN** w\n- **THEN** t\n\n### Requirement: Records are audited\n\nThe store SHALL log each read.\n\n#### Scenario: A read is logged\n\n- **WHEN** w\n- **THEN** t\n')
        r = self.repo.run("check", "--base", "main", "x")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(kinds(r), [])

    def test_a_fenced_delta_title_inside_a_requirement_is_its_text(self):
        r = self.check_delta('## MODIFIED Requirements\n\n### Requirement: Records are kept\n\nThe store SHALL keep every record for a year. A delta adds rules like this:\n\n```markdown\n## ADDED Requirements\n```\n\n#### Scenario: A record survives\n\n- **WHEN** w\n- **THEN** t\n\n## ADDED Requirements\n\n### Requirement: Records are audited\n\nThe store SHALL log each read.\n\n#### Scenario: A read is logged\n\n- **WHEN** w\n- **THEN** t\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_both_sections_with_one_title_are_read(self):
        r = self.check_delta(NO_SCENARIO + "\n" + NO_SCENARIO.replace("Invoices", "Receipts").replace(
            "invoices", "receipts"))
        self.assertEqual(kinds(r), ["no-scenario", "no-scenario"], r.stdout)
        self.assertIn("spec.md:3: error [no-scenario]", r.stdout)
        self.assertIn("spec.md:9: error [no-scenario]", r.stdout)

    def test_a_title_in_another_case_is_read(self):
        r = self.check_delta(GOOD_DELTA + "\n## added requirements\n\n" + NO_SCENARIO.split("\n", 2)[2])
        self.assertIn("spec.md:14: error [no-scenario]", r.stdout)

    def test_a_scenario_is_found_at_its_line(self):
        r = self.check_delta(GOOD_DELTA.replace("- **THEN** it is deleted\n", ""))
        self.assertIn('spec.md:7: error [scenario-incomplete] scenario "An old record goes" has no THEN',
                      r.stdout)

    def test_a_line_separator_in_the_text_keeps_the_lines_found(self):
        r = self.check_delta("## ADDED Requirements\n\nIntro line. Second.\n\n"
                             + NO_SCENARIO.split("\n", 2)[2])
        self.assertIn("spec.md:5: error [no-scenario]", r.stdout)

    def test_a_delta_outside_a_capability_directory_is_not_read(self):
        # OpenSpec reads a delta only at specs/<capability>/spec.md, never
        # directly under specs/.
        self.repo.change("x", delta=NO_SCENARIO)
        os.rename(self.repo.path / "openspec/changes/x/specs/cap/spec.md",
                  self.repo.path / "openspec/changes/x/specs/spec.md")
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_change_with_an_unreadable_proposal_still_has_its_deltas_read(self):
        # `openspec show` refuses a change whose proposal lacks "What
        # Changes", so the deltas are read beside spec-check's stub proposal.
        self.repo.change("x", proposal="# x\n", delta=NO_SCENARIO)
        self.assertIn("[no-scenario]", self.repo.check("x").stdout)


class RenamedBlockTests(unittest.TestCase):
    """Under "## RENAMED Requirements" OpenSpec reads only FROM and TO lines,
    so the archive drops a requirement written out there, and neither
    `openspec show` nor `openspec validate` says so. A line scan reports it
    (Adam, 2026-10-31)."""

    RENAME_WITH_BLOCK = ("## RENAMED Requirements\n\n- FROM: `### Requirement: Records are kept`\n"
                         "- TO: `### Requirement: Records are retained`\n\n"
                         "### Requirement: Records are retained\n\n"
                         "The store SHALL keep every record for a year.\n\n### Notes\n\n"
                         "#### Scenario: s\n\n- **WHEN** w\n")

    def setUp(self):
        self.repo = Repo(self)

    def check_delta(self, delta, env=None):
        self.repo.change("x", delta=delta)
        return self.repo.check("x", env=env)

    def test_a_requirement_written_out_under_renamed_is_an_error(self):
        r = self.check_delta(self.RENAME_WITH_BLOCK)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('openspec/changes/x/specs/cap/spec.md:6: error [renamed-block] '
                      '"### Requirement: Records are retained"', r.stdout)
        self.assertIn('"## MODIFIED Requirements"', r.stdout)

    def test_the_scan_runs_without_the_cli(self):
        r = self.check_delta(self.RENAME_WITH_BLOCK, env=dict(ENV, PATH=str(git_only_path(self))))
        self.assertIn("spec.md:6: error [renamed-block]", r.stdout)

    def test_each_heading_with_text_under_it_is_named(self):
        self.assertIn("spec.md:10: error [renamed-block] \"### Notes\"",
                      self.check_delta(self.RENAME_WITH_BLOCK).stdout)

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_a_requirement_under_renamed_gets_no_requirement_findings(self):
        r = self.check_delta(self.RENAME_WITH_BLOCK)
        for kind in ("no-scenario", "scenario-incomplete", "duplicate"):
            self.assertNotIn(f"[{kind}]", r.stdout)

    def test_a_header_over_from_and_to_lines_is_a_rename(self):
        # The archive renames it and drops nothing.
        r = self.check_delta('## RENAMED Requirements\n\n### Requirement: Records are kept\n- FROM: `### Requirement: Records are kept`\n- TO: `### Requirement: Records are retained`\n')
        self.assertNotIn("[renamed-block]", r.stdout)

    def test_a_fenced_block_under_a_heading_is_text_and_ends_no_section(self):
        r = self.check_delta("## RENAMED Requirements\n\n- FROM: `### Requirement: Records are kept`\n"
                             "- TO: `### Requirement: Records are retained`\n\n"
                             "### Requirement: Records are retained\n\n```markdown\n## Example\n```\n\n"
                             "### Later\n\nMore.\n")
        self.assertIn("spec.md:6: error [renamed-block]", r.stdout)
        self.assertIn("spec.md:12: error [renamed-block]", r.stdout)

    def test_a_heading_under_another_section_is_not_scanned(self):
        r = self.check_delta(GOOD_DELTA + "\n## Notes\n\n### Background\n\nWhy.\n")
        self.assertNotIn("[renamed-block]", r.stdout)

    def test_a_section_title_in_another_case_is_scanned(self):
        r = self.check_delta(self.RENAME_WITH_BLOCK.replace("RENAMED Requirements", "renamed requirements"))
        self.assertIn("spec.md:6: error [renamed-block]", r.stdout)


class FoundByBugHunterRun7Tests(unittest.TestCase):
    """Regressions found by bug-hunter's seventh run over this skill: the
    line locator and the stray-heading advice."""

    def setUp(self):
        if not HAS_OPENSPEC:
            self.skipTest("needs OpenSpec 1.15.0 or later")
        self.repo = Repo(self)

    def check_delta(self, delta, *args):
        self.repo.change("x", delta=delta)
        return self.repo.check("x", *args)

    def test_a_name_ending_in_a_backtick_is_found_at_its_line(self):
        r = self.check_delta("## ADDED Requirements\n\n### Requirement: Plain\n\nThe tool SHALL be plain.\n\n"
                             "#### Scenario: Happy\n\n- **WHEN** a\n- **THEN** b\n\n"
                             "### Requirement: Run `x`\n\nThe tool SHALL run x.\n\n"
                             "#### Scenario: Happy\n\n- **WHEN** a write\n\n"
                             "### Requirement: Bare `y`\n\nThe tool SHALL be bare.\n")
        self.assertIn('spec.md:16: error [scenario-incomplete] scenario "Happy" has no THEN', r.stdout)
        self.assertIn('spec.md:20: error [no-scenario] requirement "Bare `y`"', r.stdout)

    def test_a_scenario_header_with_closing_hashes_is_found_at_its_line(self):
        r = self.check_delta("## ADDED Requirements\n\n### Requirement: Alpha\n\nThe tool SHALL alpha.\n\n"
                             "#### Scenario: Works ##\n\n- **WHEN** a\n\n"
                             "### Requirement: Beta\n\nThe tool SHALL beta.\n\n"
                             "#### Scenario: Works\n\n- **WHEN** a\n- **THEN** b\n")
        self.assertIn('spec.md:7: error [scenario-incomplete] scenario "Works" has no THEN', r.stdout)

    def test_a_stray_heading_with_no_requirement_above_it_is_not_said_to_be_kept(self):
        self.repo.change("x", delta="## ADDED Requirements\n\n### Logging\n\nThe tool SHALL log every write.\n\n"
                         + GOOD_DELTA.split("\n", 2)[2])
        r = self.repo.run("check", "--base", "main", "x")
        line = next(l for l in r.stdout.splitlines() if 'Header "### Logging"' in l)
        self.assertNotIn("keeps it inside the requirement above it", line)
        self.assertNotIn('move it to "## ADDED Requirements"', line)


class FoundByBugHunterRun7Iteration2Tests(unittest.TestCase):
    """Regressions found by the second iteration of bug-hunter's seventh
    run: the line locator against OpenSpec 1.15's header grammar."""

    def setUp(self):
        if not HAS_OPENSPEC:
            self.skipTest("needs OpenSpec 1.15.0 or later")
        self.repo = Repo(self)

    def check_delta(self, delta, validate=False):
        self.repo.change("x", delta=delta)
        if validate:
            return self.repo.run("check", "--base", "main", "x")
        return self.repo.check("x")

    def test_a_scenario_header_without_its_prefix_is_found_at_its_line(self):
        r = self.check_delta('## ADDED Requirements\n\n### Requirement: Alpha\n\nThe tool SHALL alpha.\n\n#### Scenario: Fine\n\n- **WHEN** a\n- **THEN** b\n\n#### Edge case\n\n- **WHEN** a\n')
        self.assertIn('spec.md:12: error [scenario-incomplete] scenario "Edge case" has no THEN', r.stdout)

    def test_a_rename_line_with_a_plus_bullet_is_found_at_its_line(self):
        r = self.check_delta('## RENAMED Requirements\n\n+ FROM: `### Requirement: Nope`\n+ TO: `### Requirement: Yes`\n')
        self.assertIn('spec.md:3: error [archive] "Nope" in cap', r.stdout)

    def test_a_bare_rename_line_ending_in_a_backtick_is_found_at_its_line(self):
        r = self.check_delta('## RENAMED Requirements\n\n- FROM: ### Requirement: Run `x`\n- TO: ### Requirement: Yes\n')
        self.assertIn("spec.md:3: error [archive]", r.stdout)

    def test_a_bare_hash_line_does_not_end_the_requirement_above(self):
        r = self.check_delta('## ADDED Requirements\n\n### Requirement: Alpha\n\nThe tool SHALL alpha.\n\n#### Scenario: Fine\n\n- **WHEN** a\n- **THEN** b\n\n##\n\n### Logging\n\nThe tool SHALL log.\n', validate=True)
        line = next(l for l in r.stdout.splitlines() if 'Header "### Logging"' in l)
        self.assertIn("keeps it inside the requirement above it", line)

    def test_two_scenarios_of_one_name_are_found_at_their_own_lines(self):
        r = self.check_delta('## ADDED Requirements\n\n### Requirement: Alpha\n\nThe tool SHALL alpha.\n\n#### Scenario: Same\n\n- **WHEN** a\n- **THEN** b\n\n#### Scenario: Same\n\n- **WHEN** c\n')
        self.assertIn('spec.md:12: error [scenario-incomplete] scenario "Same" has no THEN', r.stdout)


class FoundByBugHunterRun7Iteration3Tests(unittest.TestCase):
    """Regressions found by the third iteration of bug-hunter's seventh run."""

    def setUp(self):
        if not HAS_OPENSPEC:
            self.skipTest("needs OpenSpec 1.15.0 or later")
        self.repo = Repo(self)

    WIDGET = ("## ADDED Requirements\n\n### Requirement: Intro\n\nThe tool SHALL format a header like this:\n\n"
              "{example}\n\n#### Scenario: Shown\n\n- **WHEN** a\n- **THEN** b\n\n"
              "### Requirement: Widget\n\nThe tool SHALL widget.\n\n#### Scenario: Half\n\n- **WHEN** a\n")

    def test_a_line_openspec_does_not_read_as_a_header_is_not_taken_for_one(self):
        for example in ("    ### Requirement: Widget", "`### Requirement: Widget`"):
            with self.subTest(example=example):
                self.repo.change("x", delta=self.WIDGET.format(example=example))
                r = self.repo.check("x")
                self.assertIn('spec.md:18: error [scenario-incomplete] scenario "Half" has no THEN',
                              r.stdout)

    def test_a_header_with_no_name_is_not_a_requirement_above_a_stray_heading(self):
        self.repo.change("x", delta=GOOD_DELTA + "\n## ADDED Requirements\n\n### Requirement:\n\n"
                         "### Logging\n\nThe tool SHALL log.\n\n#### Scenario: L\n\n- **WHEN** a\n- **THEN** b\n")
        r = self.repo.run("check", "--base", "main", "x")
        line = next(l for l in r.stdout.splitlines() if 'Header "### Logging"' in l)
        self.assertNotIn("keeps it inside the requirement above it", line)

    def test_a_byte_order_mark_does_not_hide_a_renamed_section(self):
        self.repo.change("x", delta="\ufeff## RENAMED Requirements\n\n### Requirement: Records are kept\n\n"
                         "The store SHALL keep records for sixty days.\n\n"
                         "- FROM: `### Requirement: Records are kept`\n- TO: `### Requirement: Records are held`\n")
        self.assertIn("spec.md:3: error [renamed-block]", self.repo.check("x").stdout)


class FoundByBugHunterRun8Tests(unittest.TestCase):
    """Regressions found by the first iteration of bug-hunter's eighth run."""

    def setUp(self):
        if not HAS_OPENSPEC:
            self.skipTest("needs OpenSpec 1.15.0 or later")
        self.repo = Repo(self)

    def relayed(self, r):
        return [l for l in r.stdout.splitlines() if "[openspec-validate]" in l]

    def test_a_rename_written_with_star_or_plus_bullets_is_a_rename(self):
        # OpenSpec reads a FROM or TO line with any of - * + as its bullet, and a
        # blank line under the heading is not text.
        for bullet in "-*+":
            with self.subTest(bullet=bullet):
                self.repo.change("x", delta=f"## RENAMED Requirements\n\n### Requirement: Records are kept\n\n"
                                 f"{bullet} FROM: `### Requirement: Records are kept`\n"
                                 f"{bullet} TO: `### Requirement: Records are held`\n")
                r = self.repo.check("x")
                self.assertNotIn("[renamed-block]", r.stdout)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_stray_heading_under_a_section_title_in_another_case_gets_advice(self):
        self.repo.change("x", delta=RelayedFromValidateTests.STRAY.replace("## ADDED", "## Added"))
        line = next(l for l in self.relayed(self.repo.run("check", "--base", "main", "x"))
                    if 'Header "### Retention details"' in l)
        self.assertIn('as "### Requirement: Retention details"', line)

    def test_a_delta_in_a_nested_capability_is_archived(self):
        self.repo.change("x", cap="area/cap", delta=modified("Records are kept", KEPT))
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("openspec/changes/x/specs/area/cap/spec.md:3: error [archive]", r.stdout)

    def test_a_nested_capability_is_read(self):
        self.repo.write("openspec/specs/area/cap/spec.md", MAIN_SPEC)
        self.repo.change("x", cap="area/cap", delta=modified("Records are kept", KEPT)
                         + "\n## ADDED Requirements\n\n### Requirement: Nested\n\nThe store SHALL nest.\n")
        r = self.repo.check("x")
        self.assertIn("openspec/changes/x/specs/area/cap/spec.md:14: error [no-scenario]", r.stdout)
        self.assertNotIn("[archive]", r.stdout)

    def test_a_name_holding_the_word_requirement_and_a_colon_keeps_its_lines(self):
        self.repo.change("x", delta="## ADDED Requirements\n\n### Requirement: Each requirement: has an owner\n\n"
                         "The tool SHALL name an owner.\n\n#### Scenario: Owned\n\n- **WHEN** a\n")
        self.assertIn('spec.md:7: error [scenario-incomplete] scenario "Owned" has no THEN',
                      self.repo.check("x").stdout)

    def test_a_duplicate_on_the_last_line_of_the_file_is_reported_there(self):
        self.repo.change("x", delta=f"## ADDED Requirements\n\n### Requirement: Twice\n\n{KEPT}\n")
        self.assertIn("openspec/changes/x/specs/cap/spec.md:5: error [duplicate]", self.repo.check("x").stdout)

    def test_a_sentence_wrapped_over_two_lines_is_one_sentence(self):
        wrapped = KEPT.replace(" for at least", "\nfor at least")
        self.repo.change("x", delta=f"## ADDED Requirements\n\n### Requirement: Twice\n\n{wrapped}\n\n"
                         "#### Scenario: S\n\n- **WHEN** a\n- **THEN** b\n")
        self.assertIn("openspec/changes/x/specs/cap/spec.md:5: error [duplicate]", self.repo.check("x").stdout)

    def test_a_stray_heading_naming_a_requirement_mid_line_is_not_one_above_itself(self):
        self.repo.change("x", delta="## ADDED Requirements\n\n### Old Requirement: Gone\n\nThe store SHALL do more.\n\n"
                         "### Requirement: Fresh\n\nThe store SHALL do fresh things.\n\n"
                         "#### Scenario: F\n\n- **WHEN** a\n- **THEN** b\n")
        line = next(l for l in self.relayed(self.repo.run("check", "--base", "main", "x"))
                    if 'Header "### Old Requirement: Gone"' in l)
        self.assertIn("No requirement is above it in its section, so `openspec archive` drops it", line)
        self.assertIn('write it as "### Requirement: Old Requirement: Gone"', line)

    def test_the_advice_drops_a_stray_headings_closing_hashes(self):
        self.repo.change("x", delta=GOOD_DELTA + "\n### Also fresh ##\n\nThe store SHALL do more.\n")
        line = next(l for l in self.relayed(self.repo.run("check", "--base", "main", "x"))
                    if 'Header "### Also fresh ##"' in l)
        self.assertIn('as "### Requirement: Also fresh"; otherwise', line)

    def test_an_issue_inside_a_spec_names_its_place(self):
        self.repo.write("openspec/specs/cap/spec.md", "# cap\n\n## Purpose\n\nshort\n\n## Requirements\n\n"
                        "### Requirement: Old\n\nThe store SHALL keep things.\n")
        r = self.repo.run("check", "--base", "main", "specs")
        self.assertIn("openspec/specs/cap/spec.md: error [openspec-validate] Purpose section is too brief "
                      "(less than 50 characters) (at overview)", r.stdout)

    def test_a_stray_heading_below_one_that_only_mentions_a_requirement_has_none_above(self):
        # OpenSpec's header pattern does not match "### Old Requirement: Gone",
        # so the archive drops both stray headings and their text.
        self.repo.change("x", delta="## ADDED Requirements\n\n### Old Requirement: Gone\n\nAlpha text here.\n\n"
                         "### Also stray\n\nBravo text SHALL stay.\n\n### Requirement: Fresh\n\n"
                         "The store SHALL be fresh.\n\n#### Scenario: S\n\n- **WHEN** w\n- **THEN** t\n")
        line = next(l for l in self.relayed(self.repo.run("check", "--base", "main", "x"))
                    if 'Header "### Also stray"' in l)
        self.assertIn("No requirement is above it in its section, so `openspec archive` drops it", line)

    def test_a_heading_left_open_in_a_renamed_section_is_reported_once(self):
        self.repo.change("x", delta="## RENAMED Requirements\n\n### Requirement: Records are kept\n"
                         "- FROM: `### Requirement: Records are kept`\n- TO: `### Requirement: Records are held`\n"
                         "The store SHALL keep things longer.\n\n## ADDED Requirements\n\n### Requirement: Z\n\n"
                         "The store SHALL zip.\n\n#### Scenario: S\n\n- **WHEN** w\n- **THEN** t\n")
        self.assertEqual(self.repo.check("x").stdout.count("[renamed-block]"), 1)

    def test_a_fenced_heading_in_a_renamed_section_is_not_a_heading(self):
        self.repo.change("x", delta="## RENAMED Requirements\n\n- FROM: `### Requirement: Records are kept`\n"
                         "- TO: `### Requirement: Records are held`\n\n```markdown\n### Requirement: Records are kept\n```\n")
        self.assertNotIn("[renamed-block]", self.repo.check("x").stdout)

    def test_a_refusal_for_a_missing_spec_is_placed_at_the_first_rename(self):
        # The archive applies renames first, whatever order the file has.
        self.repo.change("x", cap="cap2", delta="## MODIFIED Requirements\n\n### Requirement: A\n\nThe store SHALL a.\n\n"
                         "#### Scenario: S\n\n- **WHEN** w\n- **THEN** t\n\n## RENAMED Requirements\n\n"
                         "- FROM: `### Requirement: B`\n- TO: `### Requirement: C`\n")
        self.assertIn('openspec/changes/x/specs/cap2/spec.md:14: error [archive] "B" in cap2', self.repo.check("x").stdout)

    def test_a_cli_that_fails_to_read_the_deltas_is_an_error_not_a_crash(self):
        bin_dir = fake_openspec(self, "1.15.0", delegate=True)
        f = bin_dir / "openspec"
        f.write_text(f.read_text().replace("exec ", 'case "$*" in *"--type change"*) echo "boom" >&2; exit 1;; esac\nexec ', 1))
        self.repo.change("x")
        r = self.repo.check("x", env=dict(ENV, PATH=f"{bin_dir}:{ENV['PATH']}"))
        self.assertIn("error [openspec-show] `openspec show` cannot read this change's deltas: boom", r.stdout)
        self.assertNotIn("Traceback", r.stderr)


class FoundByBugHunterTests(unittest.TestCase):
    """Regressions found by bug-hunter's first pass over this skill."""

    def setUp(self):
        self.repo = Repo(self)

    def test_an_address_with_a_port_is_not_a_citation(self):
        self.repo.change("x", delta=GOOD_DELTA.replace(
            "its last read.", "its last read, served on 0.0.0.0:8080 and "
            "host.docker.internal:5432 and `127.0.0.1:8080`."))
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_renamed_requirement_is_not_a_duplicate_of_its_old_name(self):
        restated = MAIN_SPEC.split("## Requirements\n", 1)[1].replace(
            "Records are kept", "Records are retained")
        self.repo.change("x", delta="## RENAMED Requirements\n\n- FROM: `### Requirement: Records are kept`\n"
                                    "- TO: `### Requirement: Records are retained`\n\n"
                                    "## MODIFIED Requirements\n" + restated)
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_replaced_requirement_is_not_a_duplicate_of_the_one_it_removes(self):
        restated = MAIN_SPEC.split("## Requirements\n", 1)[1].replace(
            "Records are kept", "Records are retained")
        self.repo.change("x", delta="## ADDED Requirements\n" + restated +
                         "\n## REMOVED Requirements\n\n### Requirement: Records are kept\n\n"
                         "**Reason**: replaced.\n")
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_repository_with_no_commits_can_be_checked_and_signed(self):
        fresh = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-test-")).resolve()
        self.addCleanup(shutil.rmtree, fresh, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=fresh, check=True, env=ENV)
        (fresh / "openspec/specs/cap").mkdir(parents=True)
        (fresh / "openspec/specs/cap/spec.md").write_text(MAIN_SPEC)
        subprocess.run(["git", "add", "-A"], cwd=fresh, check=True, env=ENV)
        r = subprocess.run([sys.executable, str(SCRIPT), "sign", "--read", "self", "--no-validate"],
                           cwd=fresh, capture_output=True, text=True, env=ENV)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Spec-check: \u2713", r.stdout)

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_a_failed_strict_validation_is_an_error(self):
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace("What cap does.", "Short."))
        r = self.repo.run("check", "--base", "main", "specs")
        self.assertIn("failed", r.stdout)
        self.assertEqual(r.returncode, 1, r.stdout)

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_a_spec_validation_finding_names_the_spec_file(self):
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace("SHALL", "will"))
        r = self.repo.run("check", "--base", "main", "specs")
        self.assertIn("openspec/specs/cap/spec.md: error [openspec-validate]", r.stdout)

    def test_sign_a_commit_that_deletes_openspec(self):
        self.repo.git("rm", "-rq", "openspec")
        r = self.repo.run("sign", "--read", "self", "--base", "main", "--no-validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Spec-check: \u2713", r.stdout)


class FoundByBugHunterIteration2Tests(unittest.TestCase):
    """Regressions found by bug-hunter's second pass, mostly in the first pass's fixes."""

    def setUp(self):
        self.repo = Repo(self)

    def test_a_stale_origin_head_falls_back_to_a_base_that_resolves(self):
        self.repo.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.repo.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/master")
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "src/app.py:99"))
        r = self.repo.run("check", "--no-validate", "x")
        self.assertEqual(kinds(r), ["citation"])
        self.assertIn("src/app.py has 10 lines on origin/main", r.stdout)

    def test_a_requirement_moved_to_another_capability_is_not_a_duplicate(self):
        self.repo.change("x", delta="## REMOVED Requirements\n\n### Requirement: Records are kept\n\n"
                                    "**Reason**: moved to retention.\n")
        self.repo.write("openspec/changes/x/specs/retention/spec.md",
                        purposed(PURPOSE, "## ADDED Requirements\n" + MAIN_SPEC.split("## Requirements\n", 1)[1]
                                 .replace("Records are kept", "Records are retained")))
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_check_on_a_ref_without_openspec_cannot_run(self):
        self.repo.git("checkout", "-q", "-b", "nospec")
        self.repo.git("rm", "-rq", "openspec")
        self.repo.git("commit", "-q", "-m", "drop")
        self.repo.git("checkout", "-q", "main")
        r = self.repo.check("--ref", "nospec")
        self.assertEqual(r.returncode, 2, r.stdout)

    def test_a_bare_name_with_an_uncommon_extension_is_still_a_citation(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "schema.prisma:40"))
        self.assertEqual(kinds(self.repo.check("x")), ["citation"])

    def test_a_host_with_a_port_is_still_not_a_citation(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL + "\nIt calls api.example.com:443 and example.com:80.\n")
        self.assertEqual(kinds(self.repo.check("x")), [])

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_an_info_note_stays_a_check_and_keeps_its_line(self):
        self.repo.change("x", delta="## ADDED Requirements\n\n### Documentation Requirements\n\n"
                                    "### Requirement: Plain\n\nThe store keeps things.\n\n"
                                    "#### Scenario: s\n\n- **WHEN** w\n- **THEN** t\n")
        r = self.repo.run("check", "--base", "main", "x")
        info = [l for l in r.stdout.splitlines() if "is ignored" in l]
        self.assertTrue(info, r.stdout)
        self.assertIn("spec.md:3: check [openspec-validate]", info[0])


class FoundByBugHunterIteration3Tests(unittest.TestCase):
    """Regressions found by bug-hunter's third pass."""

    def setUp(self):
        self.repo = Repo(self)

    def test_a_service_address_is_not_an_error(self):
        self.repo.change("x", delta=GOOD_DELTA.replace(
            "its last read.", "its last read, cached at `redis.cache:6379` and postgres.default:5432."))
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 0, r.stdout)

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_sign_a_commit_that_deletes_openspec_runs_no_validation(self):
        self.repo.git("rm", "-rq", "openspec")
        r = self.repo.run("sign", "--read", "self", "--base", "main")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no open change or spec staged", r.stdout)


class FoundByScopedRunTests(unittest.TestCase):
    """Fences inside a list, quoted stack traces and image names, and
    citations of files the change adds. bug-hunter found each of these."""

    def setUp(self):
        self.repo = Repo(self)

    def proposal(self, items):
        return GOOD_PROPOSAL.replace("- Records expire.\n", items)

    def test_a_fence_in_a_list_does_not_end_it(self):
        self.repo.change("x", proposal=self.proposal(
            "1. **Purge nightly.** *Rejected:* purging on read. The job:\n\n"
            "```sh\n# nightly purge\npurge --older-than 90d\n```\n\n"
            "2. **Purged records are deleted** (`src/purge.py:3`).\n"))
        self.assertEqual(kinds(self.repo.check("x")), ["citation"])

    def test_a_quoted_stack_trace_is_not_a_citation(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("## What Changes", (
            "```\n    at Layer.handle (node_modules/express/lib/router/layer.js:95:5)\n```\n\n"
            "It runs ghcr.io/acme/web.api:2.\n\n## What Changes")))
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_citation_of_a_file_the_change_adds_is_not_an_error(self):
        self.repo.write("src/expire.py", "a\nb\nc\nd\n")
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "src/expire.py:3"))
        self.repo.git("add", "-A")
        r = self.repo.run("sign", "--read", "self", "--base", "main", "--no-validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("check [citation]", r.stdout)


class FoundByScopedRunIteration2Tests(unittest.TestCase):
    """Citations of files or lines the change adds, nested and tilde fences,
    and dot directories, such as `.ai/`, read as hosts.
    bug-hunter found each of these."""

    def setUp(self):
        self.repo = Repo(self)

    def sign(self):
        self.repo.git("add", "-A")
        return self.repo.run("sign", "--read", "self", "--base", "main", "--no-validate")

    def test_a_bare_name_of_an_added_file_is_not_an_error(self):
        self.repo.write("src/expire.py", "a\nb\nc\nd\n")
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "expire.py:3"))
        r = self.sign()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_line_the_change_adds_to_an_existing_file_is_not_an_error(self):
        self.repo.write("src/app.py", "".join(f"line{i}\n" for i in range(1, 15)))
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "src/app.py:13"))
        r = self.sign()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("check [citation]", r.stdout)

    def test_a_fence_inside_a_longer_fence_does_not_end_the_list(self):
        for outer in ("~~~", "````"):
            with self.subTest(outer=outer):
                self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
                    "- Records expire.\n",
                    "1. **Ship the snippet.** *Rejected:* linking out.\n\n"
                    f"{outer}markdown\nRun it:\n```\n# build everything\nmake\n```\n{outer}\n\n"
                    "2. **Snippets are tested** (`src/snippets.py:3`).\n"))
                self.assertEqual(kinds(self.repo.check("x")), ["citation"])

    def test_a_dot_directory_is_not_a_host(self):
        self.repo.write(".ai/rules.md", "one\ntwo\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "rules")
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", ".ai/rules.md:40"))
        self.assertEqual(kinds(self.repo.check("x")), ["citation"])


class CitationRuleTests(unittest.TestCase):
    """A citation is an error only when it has a `/` and its line is in neither
    the base nor the change; every other citation finding is a check."""

    def setUp(self):
        self.repo = Repo(self)

    def sign(self):
        self.repo.git("add", "-A")
        return self.repo.run("sign", "--read", "self", "--base", "main", "--no-validate")

    def test_a_fence_in_a_nested_list_item_is_a_fence(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
            "- Records expire.\n",
            "1. **Records expire.** *Rejected:* keeping them forever. Today:\n\n"
            "    - The trace we see:\n\n"
            "        ```\n"
            "        at Layer.handle (node_modules/express/lib/router/layer.js:95:5)\n"
            "        ```\n"))
        r = self.sign()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("layer.js", r.stdout)

    def test_a_bare_name_shared_with_a_base_file_does_not_block_sign(self):
        self.repo.write("pkg/config.py", "a\nb\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "pkg")
        self.repo.write("src/config.py", "".join(f"x{i}\n" for i in range(60)))
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "config.py:50"))
        r = self.sign()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("check [citation]", r.stdout)

    def test_a_missing_bare_name_is_never_an_error(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "gone.py:5"))
        r = self.repo.check("x")
        self.assertEqual((r.returncode, kinds(r)), (0, ["citation"]), r.stdout)

    def test_a_path_missing_from_both_trees_is_an_error(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "src/gone.py:5"))
        r = self.sign()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("error [citation] src/gone.py:5", r.stdout)


class EvolutionTextTests(unittest.TestCase):
    """Text recording how a change got to its shape is an error, which only
    a person's override through the change's kept file clears. The examples are
    taken from real changes the patterns were measured on (DECISIONS.md,
    "Document-evolution text is an error")."""

    HISTORY = [
        "Amended by Adam's decision 298: no decline can be reopened.",
        "This rule amends decision 4.",
        "It reverses the earlier decision to keep records.",
        "That paragraph is superseded by decision 12.",
        "104. **A release deletes the files** (Adam, 2026-10-21, amending decision 79).",
        "Its scope was narrowed by decision 9.",
        "and Adam narrowed it on 2026-10-20.",
        "The store keeps records (Adam, 2026-10-21).",
        "A fetch authenticates as the App (Adam,",
        "Adam decided that a seat's reserve is a line.",
        "Issue #212, decided by Adam and recorded in igor.",
        "Approved by Adam (2026-10-20), as written.",
        "- decisions 21 and 22 on 2026-10-20, answering two questions.",
        "Recorded 2026-09-28. This changes no requirement.",
        "The rule previously said thirty days.",
        "Previously, records were kept forever.",
        "This change originally assumed a weaker signal.",
        "An earlier draft defined a role file here.",
        "The earlier wording kept records forever.",
        "This rule was changed to ninety days.",
        "It was reworded after the read.",
        "This requirement was narrowed to one store.",
        "Fixed in this push.",
        "Found this round.",
        "## Since review: the reserve becomes a line",
        "Findings for this change's next revision.",
        "Hitherto it said thirty days.",
        "Then this was amended.",
        "It moves to the next version of this spec.",
        "Questions this change's second to fourth consistency reads raised.",
    ]

    BEHAVIOUR = [
        "A newer file supersedes an older one.",
        "The item is no longer claimed.",
        "The derived length supersedes the built-in one.",
        "The new session replaces the lock and holds it.",
        "Every action is cheap to reverse.",
        "A candidate previously rejected is not proposed again.",
        "New evidence may raise a previously rejected rule.",
        "#### Scenario: Claim confirmed",
        "No link is kept, since the review is planned and has no spec.",
        "Its accepted cost is that Igor sees its spend late.",
        "An added seat file has no earlier version in the first parent.",
        "The agent decided it on its own.",
        "- **WHEN** on 2026-10-20 the agent logs the question",
        "The record names who asked and what they said.",
        "A comment that was changed by a later commit is not counted.",
        "Each field that was changed is listed.",
        "The decision is recorded where the question was asked.",
        "One previously held claim is released.",
        "Adam's previously held claim is released.",
        "A claim previously shown is hidden.",
        "A previously held claim is released.",
    ]

    def test_each_kind_of_history_is_flagged(self):
        for line in self.HISTORY:
            with self.subTest(line=line):
                self.assertEqual(len(spec_check.evolution_hits(line + "\n")), 1)

    def test_behaviour_using_the_same_words_is_not_flagged(self):
        for line in self.BEHAVIOUR:
            with self.subTest(line=line):
                self.assertEqual(spec_check.evolution_hits(line + "\n"), [])

    def test_code_fences_and_quoted_examples_are_not_flagged(self):
        text = ("A checker flags `amended by` and \"this round\" in a change.\n\n"
                "```\nAmended by decision 3 (Adam, 2026-10-21)\n```\n")
        self.assertEqual(spec_check.evolution_hits(text), [])

    def test_property_a_history_line_is_found_at_its_own_line_number(self):
        # Seeded, so a failure reproduces: any mix of behaviour lines and blank
        # lines, with history lines dropped in at random places, reports each
        # history line once, at its own number, quoting it, and nothing else.
        rng = random.Random(20261102)
        for trial in range(200):
            lines, expected = [], []
            for _ in range(rng.randint(1, 12)):
                kind = rng.random()
                if kind < 0.3:
                    lines.append(rng.choice(self.HISTORY))
                    expected.append((len(lines), lines[-1]))
                elif kind < 0.8:
                    lines.append(rng.choice(self.BEHAVIOUR))
                else:
                    lines.append("")
            with self.subTest(trial=trial):
                hits = spec_check.evolution_hits("\n".join(lines) + "\n")
                self.assertEqual([(n, quote) for n, _, _, quote in hits], expected)
                for _, phrase, _, quote in hits:
                    self.assertIn(phrase.lower(), quote.lower())

    def test_a_word_opening_a_sentence_is_not_taken_for_a_name(self):
        # A word in EVOLUTION_NOT_NAMES before a decision verb is not a name.
        # The first line is from a real design.md that the check flagged as
        # crediting a person named "Also". Each line of the second loop is a
        # real credit and gives one error, from whichever pattern fires first:
        # plain names, names ending in -ly ("Anatoly"), a name after a listed
        # word ("Then Alice"), an @ handle, and an "(Adam, <date>)" credit.
        for line in ["Also ruled out by scenarios:",
                     "This settled the order.", "Then approved by the reviewer.",
                     "Later agreed in the session.", "And chose the second path.",
                     "Once accepted, a claim holds.", "Finally settled by a test.",
                     "- Eventually adopted by every store.", "So confirmed: the claim holds."]:
            with self.subTest(line=line):
                self.assertEqual(spec_check.evolution_hits(line + "\n"), [])
        for line in ["Adam ruled out the second store.", "Alice decided the order.",
                     "Also, Adam ruled out the second store.", "Then Alice decided it.",
                     "Beverly decided the order.", "Emily approved it.",
                     "Anatoly decided the order.", "Then Anatoly decided it.",
                     "@Adam decided the order.",
                     "(Adam, 2026-11-04) decided the order."]:
            with self.subTest(line=line):
                self.assertEqual(len(spec_check.evolution_hits(line + "\n")), 1)

    def test_function_words_are_not_names(self):
        for line in ["The agreed order holds.", "We decided to keep one store.",
                     "However settled the rule is, it holds.", "Today approved stores sync hourly.",
                     "They agreed on one store.", "A settled rule stays.", "An approved list is final.",
                     "When accepted, a claim holds.", "Newly accepted claims are held for a day.",
                     "Typically accepted claims stay.", "Ultimately chose one store.",
                     "Clearly settled by a test."]:
            with self.subTest(line=line):
                self.assertEqual(spec_check.evolution_hits(line + "\n"), [])

    def test_property_quoting_a_history_line_silences_it(self):
        for line in self.HISTORY:
            with self.subTest(line=line):
                self.assertEqual(spec_check.evolution_hits(f"`{line}`\n"), [])

    def test_a_quoted_word_does_not_make_the_text_before_it_a_determiner(self):
        # A mask of spaces would put "The" right before "previously" in the
        # first line, and right before "Adam" in the second, so the
        # determiner veto would silence both.
        # The mask is neither space nor word. Found by bug-hunter.
        self.assertEqual(len(spec_check.evolution_hits("The `claim` previously held for an hour.\n")), 1)
        self.assertEqual(len(spec_check.evolution_hits("The \"Claim\" Adam decided on.\n")), 1)

    def test_a_code_span_holding_a_backtick_is_skipped_whole(self):
        # A ``double-backtick`` span may hold a single backtick. Found by
        # bug-hunter.
        self.assertEqual(spec_check.evolution_hits("``Adam decided ` x``\n"), [])

    def test_a_long_line_of_vetoed_hits_is_read_in_linear_time(self):
        # A veto that reads all the text before each hit takes 11 s on the
        # first line. Found by bug-hunter.
        start = time.monotonic()
        spec_check.evolution_hits("a previously " * 8000 + "\n")
        spec_check.evolution_hits("the " + "previously rejected " * 5000 + "\n")
        self.assertLess(time.monotonic() - start, 2.0)

    def test_a_backtick_run_opens_a_span_only_as_a_whole_run(self):
        # ``x ... ` is no code span in CommonMark: two backticks never close on
        # one. Found by bug-hunter, iteration 2.
        self.assertEqual(len(spec_check.evolution_hits("A ``x Adam decided it` y.\n")), 1)
        self.assertEqual(spec_check.evolution_hits("A ``x Adam decided it`` y.\n"), [])

    def test_the_phrase_is_the_line_as_written(self):
        # The phrase carried the invisible mask character where a quote sat.
        # Found by bug-hunter, iteration 2.
        hit = spec_check.evolution_hits("Adam decided `the scope` on 2026-01-01.\n")
        self.assertEqual(hit[0][1], "decided `the scope` on 2026-01-01")
        self.assertEqual(spec_check.evolution_hits("(Adam,   \n")[0][1], "(Adam,")

    def test_a_veto_reads_past_a_run_of_spaces_and_late_in_a_long_line(self):
        self.assertEqual(spec_check.evolution_hits("every      previously held claim\n"), [])
        self.assertEqual(spec_check.evolution_hits("x " * 60 + "the previously held claim\n"), [])
        self.assertEqual(spec_check.evolution_hits("The previously held claim stays. " + "x " * 60 + "\n"),
                         [])

    def test_an_escaped_backtick_opens_no_code_span(self):
        # A backslash makes the backtick after it literal, so it opens no code
        # span and the text after it is still read. Found by bug-hunter,
        # iteration 3.
        self.assertEqual(len(spec_check.evolution_hits("The rule \\`previously` held.\n")), 1)
        self.assertEqual(spec_check.evolution_hits("Write \\`x` previously `y` here.\n"), [])

    def test_a_change_with_history_fails_with_an_error_naming_the_line(self):
        repo = Repo(self)
        repo.change("x")
        repo.write("openspec/changes/x/design.md",
                   "## Decisions\n\nRecords expire after ninety days (Adam, 2026-10-21).\n")
        r = repo.check("x")
        self.assertEqual((r.returncode, kinds(r)), (1, ["evolution"]), r.stdout + r.stderr)
        self.assertIn("openspec/changes/x/design.md:3: error [evolution] \"(Adam, 2026-10-21\"",
                      r.stdout)
        self.assertIn("to git: Records expire after ninety days (Adam, 2026-10-21).", r.stdout)

    def test_history_blocks_sign(self):
        repo = Repo(self)
        repo.change("x", proposal=GOOD_PROPOSAL.replace("- Records expire.",
                                                        "- Records expire. An earlier draft kept them."))
        repo.git("add", "-A")
        r = repo.run("sign", "--read", "self", "--base", "main", "--no-validate")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("error [evolution]", r.stdout)
        self.assertNotIn("Spec-check: ✓", r.stdout)

    def test_main_specs_are_not_scanned(self):
        repo = Repo(self)
        repo.write("openspec/specs/cap/spec.md",
                   MAIN_SPEC.replace("What cap does.", "What cap does (Adam, 2026-10-21)."))
        repo.change("x")
        r = repo.check("x", "specs")
        self.assertNotIn("evolution", kinds(r), r.stdout)

    def test_the_finding_says_what_the_phrase_does_and_quotes_the_line_stripped(self):
        hit = spec_check.evolution_hits("  - The rule previously said thirty days.\n")
        self.assertEqual(hit, [(1, "previously", "narrates an earlier state of the document",
                                "- The rule previously said thirty days.")])

    def test_a_line_of_exactly_the_limit_is_quoted_whole(self):
        corpus = mock.Mock(texts={})
        for length, quote in ((160, None), (161, 159)):
            line = "Adam decided " + "x" * (length - len("Adam decided "))
            corpus.texts["d.md"] = line + "\n"
            out = []
            spec_check.check_evolution(["d.md"], corpus, out)
            with self.subTest(length=length):
                tail = out[0].message.split("to git: ", 1)[1]
                self.assertEqual(tail, line if quote is None else line[:quote] + "…")

    def test_a_long_line_is_quoted_cut_short(self):
        repo = Repo(self)
        repo.change("x")
        repo.write("openspec/changes/x/design.md", "Adam decided " + "x" * 300 + "\n")
        r = repo.check("x")
        line = next(l for l in r.stdout.splitlines() if "[evolution]" in l)
        self.assertTrue(line.endswith("…"), line)


class KeptEvolutionTests(unittest.TestCase):
    """A person overrules a false evolution error through the change's
    committed kept file, which check and sign both read; the spec text stays
    as written and the trailer counts the errors it cleared."""

    DESIGN = "openspec/changes/x/design.md"
    KEPT = "openspec/changes/x/.spec-check-kept"
    NARROWS = "The spec narrows the decision."
    DATED = "Records expire (Adam, 2026-10-21)."

    def setUp(self):
        self.repo = Repo(self)
        self.repo.change("x")
        self.design(self.NARROWS, self.DATED)

    def design(self, *lines):
        self.repo.write(self.DESIGN, "## Decisions\n\n" + "".join(l + "\n" for l in lines))
        self.repo.git("add", "-A")

    def kept(self, text):
        self.repo.write(self.KEPT, text)
        self.repo.git("add", "-A")

    def sign(self, kept=None):
        if kept is not None:
            self.kept(kept)
        return self.repo.run("sign", "--read", "self", "--base", "main", "--no-validate")

    def both(self, how1="kept (asked)", how2="kept (asked)"):
        return (f"design.md: «{self.NARROWS}» {how1}: compares a spec with a decision\n"
                f"design.md: «{self.DATED}» {how2}: the date is part of the rule\n")

    def test_kept_entries_sign_and_the_trailer_counts_them(self):
        r = self.sign(self.both())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("error [evolution]", r.stdout)
        self.assertIn(f"{self.DESIGN}:3: kept (asked) [evolution] compares a spec with a decision",
                      r.stdout)
        trailer = r.stdout.strip().splitlines()[-1]
        self.assertRegex(trailer, r"^Spec-check: ✓ [0-9a-f]{12} 0 errors, 0 checks, "
                                  r"2 evolution kept; ")
        self.assertIn(self.NARROWS, (self.repo.path / self.DESIGN).read_text())

    def test_check_reads_the_committed_file_so_a_reviewer_sees_no_error(self):
        self.kept(self.both())
        self.repo.git("commit", "-q", "-m", "x")
        for args in ((), ("--ref", "HEAD")):
            with self.subTest(args=args):
                r = self.repo.check("x", *args)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn(f"{self.DESIGN}:4: kept (asked) [evolution] the date is part",
                              r.stdout)
                self.assertIn("0 error(s), 0 check(s), 2 evolution kept in x", r.stdout)

    def test_blank_lines_between_entries_are_skipped(self):
        first, second = self.both().splitlines()
        r = self.sign(f"{first}\n\n   \n{second}\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 checks, 2 evolution kept; ", r.stdout)

    def test_json_and_text_reports_list_the_kept_errors(self):
        self.kept(self.both())
        kept = [f"{self.DESIGN}:3: kept (asked) [evolution] compares a spec with a decision",
                f"{self.DESIGN}:4: kept (asked) [evolution] the date is part of the rule"]
        data = json.loads(self.repo.check("x", "--json").stdout)
        self.assertEqual((data["evolution_kept"], data["kept"], data["errors"]), (2, kept, 0))
        # When the kept file clears every finding, a blank line still
        # follows the kept lines, before the summary.
        self.assertEqual(self.repo.check("x").stdout.splitlines()[:3], kept + [""])

    def test_without_entries_the_trailer_has_no_count(self):
        self.design("Records expire.")
        r = self.sign()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("kept", r.stdout.strip().splitlines()[-1])

    def test_a_finding_not_kept_still_blocks_sign(self):
        r = self.sign(self.both().splitlines()[0] + "\n")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"{self.DESIGN}:4: error [evolution]", r.stdout)
        self.assertNotIn("Spec-check: ✓", r.stdout)

    def test_an_entry_survives_lines_inserted_above_and_other_spacing(self):
        self.design("A new first line.", "", "Another.", "   " + self.NARROWS.replace(" ", "  "),
                    self.DATED)
        r = self.sign(self.both())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"{self.DESIGN}:6: kept (asked) [evolution] compares", r.stdout)

    def test_one_entry_keeps_every_line_with_its_text(self):
        self.design(self.DATED, "Records last.", self.DATED)
        r = self.sign(f"design.md: «{self.DATED}» kept (asked): the date is part of the rule\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 checks, 2 evolution kept; ", r.stdout)

    def test_an_entry_whose_text_changed_is_a_check_asking_for_its_removal(self):
        self.kept(self.both())
        self.design(self.NARROWS, "Records expire (Adam, 2026-10-22).")
        r = self.sign()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"{self.DESIGN}:4: error [evolution]", r.stdout)
        self.assertIn(f"{self.KEPT}:2: check [kept] «{self.DATED}» matches no evolution error in "
                      f"design.md: the line changed or is gone, so remove the entry", r.stdout)
        self.design(self.NARROWS, "Records expire after a year.")
        r = self.sign()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout.strip().splitlines()[-1], r" 0 errors, 1 checks, 1 evolution kept; ")

    def test_an_entry_quoting_a_line_of_another_kind_of_error_is_stale(self):
        self.repo.change("x", delta=GOOD_DELTA.split("#### Scenario")[0])
        self.repo.git("add", "-A")
        r = self.sign(self.both() + "specs/cap/spec.md: «The store SHALL keep records.» "
                                    "kept (asked): not history\n")
        self.assertIn("error [no-scenario]", r.stdout)
        self.assertIn(f"{self.KEPT}:3: check [kept]", r.stdout)

    def test_an_entry_without_asked_is_refused_and_named_for_hand_back(self):
        r = self.sign(self.both(how2="kept"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"{self.KEPT}:2: error [kept] the entry has no `(asked)`", r.stdout)
        handback = r.stdout.split("no person approved:", 1)[1]
        self.assertIn(f"{self.KEPT}:2: design.md: «{self.DATED}»", handback)
        self.assertIn(f"{self.DESIGN}:4: \"(Adam, 2026-10-21\"", handback)
        self.assertIn("reason: the date is part of the rule", handback)
        self.assertIn("Do not commit.", handback)
        self.assertNotIn(f"{self.DESIGN}:3:", handback)
        self.assertNotIn("Spec-check: ✓", r.stdout)

    def test_an_entry_without_a_reason_or_twice_or_malformed_is_refused(self):
        for extra, why in ((f"design.md: «{self.DATED}» kept (asked):   \n",
                            "the entry quotes the same line of design.md as line 2"),
                           (f"design.md:4 kept (asked): the date\n",
                            "the entry is not `<file>: «<line text>» kept (asked): <reason>`"),
                           ("whatever\n", "the entry is not")):
            with self.subTest(why=why):
                r = self.sign(self.both() + extra)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn(f"{self.KEPT}:3: error [kept] {why}", r.stdout)
        r = self.sign(self.both().replace("the date is part of the rule", ""))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"{self.KEPT}:2: error [kept] the entry gives no reason", r.stdout)

    def test_an_unreadable_kept_file_is_an_error(self):
        (self.repo.path / self.KEPT).write_bytes(b"\xff\xfe\n")
        self.repo.git("add", "-A")
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"{self.KEPT}: error [kept] cannot read the kept file", r.stdout)

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_the_file_passes_validate_and_archives_with_its_change(self):
        self.kept(self.both())
        exe = shutil.which("openspec")
        v = subprocess.run([exe, "validate", "x", "--strict"], cwd=self.repo.path,
                           capture_output=True, text=True, env=ENV)
        self.assertEqual(v.returncode, 0, v.stdout + v.stderr)
        a = subprocess.run([exe, "archive", "x", "-y"], cwd=self.repo.path,
                           capture_output=True, text=True, env=ENV)
        self.assertEqual(a.returncode, 0, a.stdout + a.stderr)
        archived = list((self.repo.path / "openspec/changes/archive").glob("*-x/.spec-check-kept"))
        self.assertEqual([p.read_text() for p in archived], [self.both()])
        self.assertFalse((self.repo.path / self.KEPT).exists())

    def test_property_entries_clear_exactly_the_findings_whose_text_they_quote(self):
        # Seeded: entries for any subset of the flagged texts clear exactly the
        # findings with those texts and count them; they still do with plain
        # lines inserted anywhere. Editing one quoted line so that it is still
        # flagged, with another text, gives it an error the entry no longer
        # clears, and makes the entry a stale check.
        rng = random.Random(20261103)
        pool = EvolutionTextTests.HISTORY[:8] + ["Plain line %d." % i for i in range(8)]
        prefix = "openspec/changes/x/"
        for trial in range(150):
            lines = [rng.choice(pool) for _ in range(rng.randint(1, 12))]
            with self.subTest(trial=trial), tempfile.TemporaryDirectory() as tmp:
                corpus = mock.Mock(root=tmp, texts={})

                def run(lines, entries):
                    corpus.texts[prefix + "design.md"] = "".join(l + "\n" for l in lines)
                    p = pathlib.Path(tmp, prefix, ".spec-check-kept")
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text("".join(f"design.md: «{t}» kept (asked): r\n" for t in entries))
                    own = []
                    spec_check.check_evolution([prefix + "design.md"], corpus, own)
                    before = list(own)
                    kept = spec_check.apply_kept("x", corpus, own)
                    return before, own, kept

                flagged = sorted({l for l in lines if spec_check.evolution_hits(l + "\n")})
                chosen = rng.sample(flagged, rng.randint(0, len(flagged)))
                before, left, kept = run(lines, chosen)
                cleared = [f for f in before if f.quote in chosen]
                self.assertEqual(left, [f for f in before if f not in cleared])
                self.assertEqual(len(kept), len(cleared))
                moved = list(lines)
                for _ in range(rng.randint(1, 4)):
                    moved.insert(rng.randint(0, len(moved)), "Inserted plain line.")
                _, left, kept = run(moved, chosen)
                self.assertEqual((len(kept), [f.kind for f in left]),
                                 (len(cleared), ["evolution"] * (len(before) - len(cleared))))
                if chosen:
                    gone = rng.choice(chosen)
                    edited = [l[:-1] + " (Adam, 2026-01-01)." if l == gone else l for l in moved]
                    _, left, kept = run(edited, chosen)
                    stale = [f for f in left if f.kind == "kept"]
                    self.assertEqual([(f.severity, f.line) for f in stale],
                                     [("check", chosen.index(gone) + 1)])
                    self.assertEqual(len(kept), len(cleared) - lines.count(gone))
                    self.assertEqual(sum(1 for f in left if f.kind == "evolution"),
                                     len(before) - len(cleared) + lines.count(gone))


class FoundByBugHunterKeptTests(unittest.TestCase):
    """Kept-file cases found by the first pass of a bug-hunter run on the
    kept file."""

    DESIGN = "openspec/changes/x/design.md"
    KEPT = "openspec/changes/x/.spec-check-kept"

    def setUp(self):
        self.repo = Repo(self)
        self.repo.change("x")

    def test_a_byte_order_mark_does_not_hide_the_first_entry(self):
        self.repo.write(self.DESIGN, "## Decisions\n\nRecords expire (Adam, 2026-10-21).\n")
        self.repo.write(self.KEPT, "\ufeffdesign.md: «Records expire (Adam, 2026-10-21).» "
                                   "kept (asked): the date is the rule\n")
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 evolution kept", r.stdout)

    def test_entries_split_only_at_newlines_as_the_markdown_does(self):
        for sep in ("\u2028", "\x0c"):
            with self.subTest(sep=repr(sep)):
                line = f"Records expire (Adam, 2026-10-21).{sep}See the table."
                self.repo.write(self.DESIGN, f"## Decisions\n\n{line}\n")
                self.repo.write(self.KEPT, f"design.md: «{line}» kept (asked): the date is the rule\n")
                r = self.repo.check("x")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("1 evolution kept", r.stdout)

    def test_an_unasked_entry_that_keeps_nothing_is_stale_not_handed_back(self):
        self.repo.write(self.DESIGN, "## Decisions\n\nRecords expire (Adam, 2026-10-21).\n")
        self.repo.write(self.KEPT, "design.md: «Records expire (Adam, 2026-10-20).» kept: the date\n")
        self.repo.git("add", "-A")
        r = self.repo.run("sign", "--read", "self", "--base", "main", "--no-validate")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"{self.KEPT}:1: check [kept]", r.stdout)
        self.assertNotIn("no person approved", r.stdout)


class FencesAndLinksTests(unittest.TestCase):
    """Regressions found by the bug-hunter run over the citation rule."""

    def setUp(self):
        self.repo = Repo(self)

    def why(self, text):
        return GOOD_PROPOSAL.replace("## What Changes", text + "\n\n## What Changes")

    def test_a_fence_straight_after_a_list_item_is_a_fence(self):
        self.repo.change("x", proposal=self.why(
            "To reproduce:\n- run `npm test`; it prints:\n```text\nTypeError\n"
            "    at src/app/handler.ts:812:5\n```\nafter"))
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_fences_straight_after_list_items_hide_nothing(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
            "- Records expire.\n",
            "1. Store the policy as YAML. *Rejected:* JSON. The file reads:\n"
            "```yaml\n- name: web\n  retries: 1\n```\n"
            "2. Install the hook with a script. *Rejected:* manual steps.\n"
            "```bash\n# install the hook\n./setup.sh\n```\n"
            "3. Use Postgres for the retry log (`src/retry.py:3`).\n"))
        r = self.repo.check("x")
        self.assertEqual(kinds(r), ["citation"])
        self.assertIn("Use Postgres", self.repo.path.joinpath(
            "openspec/changes/x/proposal.md").read_text().splitlines()[
                int(r.stdout.split("proposal.md:")[1].split(":")[0]) - 1])

    def test_a_fence_opened_on_the_list_marker_line_is_a_fence(self):
        self.repo.change("x", proposal=self.why(
            "- ```text\n  TypeError\n      at src/app/handler.ts:812:5\n  ```\n"
            "- ```text\n  RangeError\n      at src/app/queue.ts:40:1\n  ```"))
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_fence_in_a_blockquote_is_a_fence(self):
        self.repo.change("x", proposal=self.why(
            "> ```text\n> TypeError\n>     at app/missing.ts:812:5\n> ```"))
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_citation_through_a_symlink_holds_in_sign(self):
        self.repo.write("real/handler.ts", "".join(f"l{i}\n" for i in range(30)))
        os.symlink("real", self.repo.path / "src2")
        os.symlink("handler.ts", self.repo.path / "real/link.ts")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "links")
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
            "src/app.py:5", "src2/handler.ts:20 and real/link.ts:20"))
        self.repo.git("add", "-A")
        r = self.repo.run("sign", "--read", "self", "--base", "main", "--no-validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("[citation]", r.stdout)

    def test_a_path_with_a_non_ascii_name_holds_in_sign(self):
        self.repo.write("docs/café.md", "a\nb\nc\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "cafe")
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "docs/café.md:2"))
        self.repo.git("add", "-A")
        r = self.repo.run("sign", "--read", "self", "--base", "main", "--no-validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class QuotesAndSubmodulesTests(unittest.TestCase):
    """Regressions found by the second pass of the run over the citation rule."""

    def setUp(self):
        self.repo = Repo(self)

    def test_a_prompt_line_inside_a_list_item_fence_stays_in_the_fence(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
            "- Records expire.\n",
            "1. Parse dates with `parseDate`. *Rejected:* a regular expression. In the REPL:\n"
            "   ```\n   > parseDate(\"2024-02-29\")\n   Uncaught RangeError\n"
            "       at parseDate (app/dates.js:212:5)\n   ```\n"
            "2. Log every retry (`src/retry.py:3`).\n"))
        r = self.repo.check("x")
        self.assertEqual(kinds(r), ["citation"])
        self.assertNotIn("dates.js", r.stdout)

    def test_a_citation_into_a_submodule_does_not_block_sign(self):
        sub = self.repo.path.parent / f"{self.repo.path.name}-sub"
        sub.mkdir()
        self.addCleanup(shutil.rmtree, sub, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=sub, check=True, env=ENV)
        (sub / "x.c").write_text("".join(f"l{i}\n" for i in range(50)))
        subprocess.run(["git", "add", "-A"], cwd=sub, check=True, env=ENV)
        subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=sub, check=True, env=ENV)
        self.repo.git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "vendor/lib")
        self.repo.git("commit", "-q", "-m", "sub")
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("src/app.py:5", "vendor/lib/x.c:30"))
        self.repo.git("add", "-A")
        r = self.repo.run("sign", "--read", "self", "--base", "main", "--no-validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("this change adds it", r.stdout)



class TrailerTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        # Run the hook once so its cursor moves past the base commit, and the
        # runs in each test report only that test's own commits.
        self.hook()

    def hook(self, script=HOOK):
        return subprocess.run(["sh", str(script), "--host", "claude"],
                              input=json.dumps({"cwd": str(self.repo.path)}),
                              capture_output=True, text=True, cwd=self.repo.path, env=ENV)

    def stage_change(self, **kw):
        self.repo.change("good", **kw)
        self.repo.git("add", "-A")

    def sign(self, *extra):
        return self.repo.run("sign", "--read", "subagent", "--base", "main", "--no-validate", *extra)

    def value(self):
        r = self.sign("--amended", "2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        line = r.stdout.strip().splitlines()[-1]
        self.assertTrue(line.startswith("Spec-check: ✓ "), line)
        return line[len("Spec-check: "):]

    def commit_with(self, *families, message="Add a spec"):
        (self.repo.path / "msg.txt").write_text(message + "\n")
        return subprocess.run(["sh", str(LIB), *families, "--message-file", "msg.txt", "--"],
                              cwd=self.repo.path, capture_output=True, text=True, env=ENV)

    def test_an_openspec_commit_without_the_trailer_is_reported(self):
        self.stage_change()
        self.repo.git("commit", "-q", "-m", "Add a spec")
        r = self.hook()
        self.assertEqual(r.returncode, 2)
        self.assertIn("1 new commit(s) changed openspec/ without a Spec-check: trailer", r.stderr)
        self.assertIn("Add a spec", r.stderr)
        self.assertIn("Ask before rewriting a pushed commit.", r.stderr)
        self.assertIn("Fix it with the spec-check skill's *Commit* steps.", r.stderr)
        self.assertIn("A person who does not want this check can turn it off:", r.stderr)
        self.assertIn("skills.py disable-hook spec-check", r.stderr)
        self.assertNotIn("spec_check.py sign", r.stderr)
        self.assertNotIn("set up spec-check", r.stderr)

    def test_both_kinds_in_one_report_name_the_repository_and_are_separate_paragraphs(self):
        # One batch can hold a commit with no trailer and another whose
        # trailer fails verification. Each block names the repository and
        # keeps its own header after a blank line.
        self.stage_change()
        self.repo.git("commit", "-q", "-m", "Add a spec")
        self.repo.write("openspec/changes/good/design.md", "## Context\n\nMore.\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "Add a design", "--trailer",
                      "Spec-check: ✓ 0123456789ab 0 errors")
        r = self.hook()
        self.assertEqual(r.returncode, 2)
        top = self.repo.git("rev-parse", "--show-toplevel")
        self.assertIn(f"changed openspec/ without a Spec-check: trailer in {top}.", r.stderr)
        self.assertRegex(r.stderr, r"Add a spec\n\nspec-check: 1 commit\(s\) carry a Spec-check: "
                                   r"trailer that does not hold in " + re.escape(top) + r"\.")

    def test_a_spec_check_line_git_does_not_read_is_reported_as_such(self):
        self.stage_change()
        self.repo.git("commit", "-q", "-m", "Add a spec\n\nSpec-check: ✓ 0123 0 errors\n\nmore body")
        r = self.hook()
        self.assertEqual(r.returncode, 2)
        self.assertIn("There is a Spec-check: line in there, but git does not read it as a trailer.",
                      r.stderr)

    def test_a_config_only_commit_gets_its_trailer_from_sign(self):
        self.repo.write("openspec/config.yaml", "schema: spec-driven\ncontext: Records.\n")
        self.repo.git("add", "openspec/")
        r = self.sign()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        value = r.stdout.strip().splitlines()[-1][len("Spec-check: "):]
        self.assertIn("no open change or spec staged", value)
        r = self.commit_with("--verified-value", str(VERIFY), "Spec-check", value,
                             message="Give OpenSpec context")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.hook().returncode, 0)

    def test_a_commit_outside_openspec_is_never_reported(self):
        self.repo.write("src/other.py", "x\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "Code only")
        r = self.hook()
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def stage_openspec_symlink(self):
        """Stages a symlink named openspec at the root as the commit's only
        change, after a commit that removes the openspec/ folder."""
        self.repo.git("rm", "-q", "-r", "openspec")
        self.repo.git("commit", "-q", "-m", "Drop the folder")
        # The hook reports each commit once: this run reports the removal, so
        # the test's next run reports only the symlink commit.
        self.hook()
        (self.repo.path / "specs-elsewhere").mkdir()
        (self.repo.path / "openspec").symlink_to("specs-elsewhere")
        self.repo.git("add", "openspec")

    def test_a_commit_that_only_adds_an_openspec_symlink_is_reported(self):
        self.stage_openspec_symlink()
        self.repo.git("commit", "-q", "-m", "Link the specs")
        r = self.hook()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("1 new commit(s) changed openspec/ without a Spec-check: trailer", r.stderr)
        self.assertIn("Link the specs", r.stderr)

    def test_staged_targets_lists_a_staged_openspec_symlink(self):
        self.stage_openspec_symlink()
        self.assertEqual(spec_check.staged_targets(str(self.repo.path)), (["openspec"], [], False))

    def test_staged_targets_takes_a_file_named_changes_as_no_change(self):
        self.repo.write("openspec/changes", "x\n")
        self.repo.git("add", "-A")
        self.assertEqual(spec_check.staged_targets(str(self.repo.path)),
                         (["openspec/changes"], [], False))

    def test_a_path_that_only_starts_with_openspec_is_never_reported(self):
        self.repo.write("openspec-notes/a.md", "x\n")
        self.repo.write("openspecx", "x\n")
        self.repo.git("add", "-A")
        self.assertEqual(spec_check.staged_targets(str(self.repo.path)), ([], [], False))
        self.repo.git("commit", "-q", "-m", "Notes only")
        r = self.hook()
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_a_signed_commit_is_quiet(self):
        self.stage_change()
        r = self.commit_with("--verified-value", str(VERIFY), "Spec-check", self.value())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.hook().returncode, 0)
        body = self.repo.git("log", "-1", "--format=%B")
        self.assertIn("read by a fresh subagent: good; 2 amended, 0 open", body)

    def test_a_skip_note_is_quiet(self):
        self.stage_change()
        r = self.commit_with("--verified-value", str(VERIFY), "Spec-check", "skipped (work in progress)")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.hook().returncode, 0)

    def test_staging_after_signing_refuses_the_commit(self):
        self.stage_change()
        value = self.value()
        self.repo.write("openspec/changes/good/design.md", "## Context\n\nMore.\n")
        self.repo.git("add", "-A")
        r = self.commit_with("--verified-value", str(VERIFY), "Spec-check", value)
        self.assertEqual(r.returncode, 1)
        self.assertIn("something was staged after signing", r.stderr)
        self.assertEqual(self.repo.git("rev-list", "--count", "HEAD"), "1")

    def test_a_hand_typed_value_is_reported(self):
        self.stage_change()
        self.repo.git("commit", "-q", "-m", "Add a spec", "--trailer",
                      "Spec-check: ✓ 0123456789ab 0 errors")
        r = self.hook()
        self.assertEqual(r.returncode, 2)
        self.assertIn("carry a Spec-check: trailer that does not hold", r.stderr)
        self.assertIn("Fix it with the spec-check skill's *Commit* steps.", r.stderr)

    def test_sign_refuses_a_change_with_errors(self):
        self.stage_change(proposal=GOOD_PROPOSAL.replace("src/app.py:5", "src/gone.py:5"))
        r = self.sign()
        self.assertEqual(r.returncode, 1)
        self.assertIn("[citation]", r.stdout)
        self.assertIn("not signed", r.stderr)
        self.assertNotIn("Spec-check:", r.stdout)

    def test_sign_with_nothing_staged_under_openspec(self):
        self.repo.write("src/other.py", "x\n")
        self.repo.git("add", "-A")
        r = self.sign()
        self.assertEqual(r.returncode, 1)
        self.assertIn("needs no Spec-check trailer", r.stderr)

    def test_sign_records_a_self_review(self):
        self.stage_change()
        r = self.repo.run("sign", "--read", "self", "--base", "main", "--no-validate")
        self.assertIn("read by its author, no subagent", r.stdout)
        self.assertIn("validate not run", r.stdout)

    def test_sign_without_the_cli_names_everything_not_run(self):
        # Adam, 2026-10-31: the trailer names show, validate and archive,
        # with the install hint, not just "validate not run".
        self.stage_change()
        for path in (git_only_path(self), fake_openspec(self, "1.14.3", delegate=False)):
            with self.subTest(path=path):
                r = self.repo.run("sign", "--read", "self", "--base", "main",
                                  env=dict(ENV, PATH=str(path)))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                line = next(l for l in r.stdout.splitlines() if l.startswith("Spec-check:"))
                self.assertIn("; show, validate and archive not run (install OpenSpec 1.15.0 or "
                              "later); read by", line)
                self.assertNotIn("; validate not run;", line)

    def test_a_read_that_amends_nothing_lands_on_an_empty_commit(self):
        """With every edit committed, the read is recorded on an empty commit,
        its trailer still bound to the tree."""
        self.hook(BUG_HUNTER_HOOK)
        self.repo.git("checkout", "-q", "-b", "spec")
        self.stage_change()
        signed_commit(self, self.repo, read="deferred")
        r = self.repo.run("sign", "--read", "subagent", "--base", "main", "--no-validate")
        self.assertEqual(r.returncode, 0, r.stderr)
        value = r.stdout.strip().splitlines()[-1][len("Spec-check: "):]
        self.assertIn("read by a fresh subagent: good;", value)
        (self.repo.path / "msg.txt").write_text("Record the consistency read\n")
        before = self.repo.git("rev-parse", "HEAD^{tree}")
        r = subprocess.run(
            ["sh", str(BUG_HUNTER), "--allow-empty",
             "--verified-value", str(VERIFY), "Spec-check", value, "--",
             "-F", "msg.txt", "skipped at triage (no change)"],
            cwd=self.repo.path, capture_output=True, text=True, env=ENV)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.repo.git("rev-parse", "HEAD^{tree}"), before)
        self.assertEqual(self.hook().returncode, 0)
        self.assertIn("no change waits for its consistency read",
                      self.repo.run("sign", "--read", "subagent", "--base", "main",
                                    "--no-validate").stderr)

    def test_bug_hunter_prose_and_spec_check_land_on_one_commit(self):
        """bug-hunter's commit script carries the other two as families."""
        self.hook(BUG_HUNTER_HOOK)  # settle bug-hunter's cursor past the base commit
        self.stage_change()
        prose_ok = self.repo.path.parent / f"{self.repo.path.name}-prose-ok.sh"
        prose_ok.write_text("#!/bin/sh\ncat >/dev/null\nexit 0\n")
        prose_ok.chmod(0o755)
        self.addCleanup(prose_ok.unlink)
        (self.repo.path / "msg.txt").write_text("Add a spec\n\nThe body.\n")
        r = subprocess.run(
            ["sh", str(BUG_HUNTER),
             "--verified-value", str(prose_ok), "Prose", "✓ 4d593e935186:9138830a72a2",
             "--verified-value", str(VERIFY), "Spec-check", self.value(), "--",
             "-F", "msg.txt", "skipped at triage (spec only, no code)", "Test <t@example.com>"],
            cwd=self.repo.path, capture_output=True, text=True, env=ENV)
        self.assertEqual(r.returncode, 0, r.stderr)
        trailers = self.repo.git("log", "-1", "--format=%(trailers:only,unfold)").splitlines()
        self.assertEqual([t.split(":", 1)[0] for t in trailers],
                         ["Bug-hunter", "Prose", "Spec-check", "Co-Authored-By"])
        self.assertEqual(self.hook().returncode, 0)
        self.assertEqual(self.hook(BUG_HUNTER_HOOK).returncode, 0)


class ManifestTests(unittest.TestCase):
    def test_hook_json_names_executable_scripts(self):
        manifest = json.loads((HERE.parent / "hook.json").read_text())
        self.assertEqual(manifest["default"], "enabled")
        commands = [h["command"] for h in manifest["hooks"]]
        self.assertEqual(commands, ["scripts/check-commit-trailer.sh"]
                         + ["scripts/check-handback.sh"] * 5)
        for command in commands:
            self.assertTrue(os.access(HERE.parent / command, os.X_OK), command)

    def test_a_sandboxed_install_wires_the_hook_on_both_hosts(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-install-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        env = dict(ENV, SHARED_SKILLS_TARGET=str(tmp / "skills"),
                   SHARED_SKILLS_HOOK_HOME=str(tmp / "home"),
                   SHARED_SKILLS_CONFIG=str(tmp / "config"),
                   SHARED_SKILLS_REPO=str(SKILLS.parent.parent))
        (tmp / "skills").mkdir()
        r = subprocess.run([sys.executable, str(SKILLS_PY), "install", "spec-check"],
                           capture_output=True, text=True, env=env, cwd=tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        claude = json.loads((tmp / "home/.claude/settings.json").read_text())["hooks"]
        wired = {(g["matcher"], h["command"].split("/")[-1].split(" ")[0])
                 for g in claude["PostToolUse"] for h in g["hooks"]}
        self.assertIn(("Bash", "check-commit-trailer.sh"), wired)
        cursor = json.loads((tmp / "home/.cursor/hooks.json").read_text())["hooks"]
        self.assertTrue(any("check-commit-trailer.sh --host cursor" in h["command"]
                            for h in cursor["postToolUse"]))
        before = {(g["matcher"], h["command"].split("/")[-1].split(" ")[0])
                  for g in claude["PreToolUse"] for h in g["hooks"]}
        self.assertIn(("^(Bash|mcp__github__.*|mcp__plugin_.*_github__.*)$", "check-handback.sh"),
                      before)
        self.assertIn(("^(Bash|mcp__github__.*|mcp__plugin_.*_github__.*)$", "check-handback.sh"),
                      wired)
        for event in ("beforeShellExecution", "beforeMCPExecution", "postToolUse",
                      "afterMCPExecution"):
            self.assertTrue(any("check-handback.sh --host cursor" in h["command"]
                                for h in cursor[event]), event)
        r = subprocess.run([sys.executable, str(SKILLS_PY), "doctor"],
                           capture_output=True, text=True, env=env, cwd=tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("No problems found in any target.", r.stdout)


# -- stacked changes -----------------------------------------------------------

# A stand-in for the GitHub CLI. It answers from the JSON file named by
# $FAKE_GH, logs each call to $FAKE_GH.log, and reads file contents for
# `gh api .../contents/...` from the fixture's bare remote.
FAKE_GH = """\
import json, os, subprocess, sys, urllib.parse
data = json.load(open(os.environ["FAKE_GH"]))
a = sys.argv[1:]
with open(os.environ["FAKE_GH"] + ".log", "a") as fh:
    fh.write(json.dumps(a) + "\\n")
def fields():
    return a[a.index("--json") + 1].split(",")
if a[:2] == ["repo", "view"]:
    print(json.dumps({"nameWithOwner": data["repo"]}))
elif a[:2] == ["pr", "view"]:
    pr = data.get("prs", {}).get(a[2])
    if pr is None or a[a.index("--repo") + 1] != data["repo"]:
        sys.exit("GraphQL: Could not resolve to a PullRequest with the number of %s." % a[2])
    print(json.dumps({k: pr[k] for k in fields() if k in pr}))
elif a[:2] == ["pr", "list"]:
    if data.get("list") is None:
        sys.exit("error connecting to api.github.com")
    print(json.dumps(data["list"]))
elif a[:1] == ["api"] and "/pulls/" in a[-3] and a[-3].split("?")[0].endswith("/files"):
    pr = data.get("prs", {}).get(a[-3].split("?")[0].split("/")[-2])
    if pr is None or pr.get("all_files") is None:
        sys.exit("gh: Not Found (HTTP 404)")
    print("".join(f + "\\n" for f in pr["all_files"]), end="")
elif a[:1] == ["api"]:
    path, ref = a[-1].split("/contents/", 1)[1].split("?ref=")
    r = subprocess.run(["git", "-C", data["git"], "show", "%s:%s" % (ref, urllib.parse.unquote(path))],
                       capture_output=True)
    if r.returncode:
        sys.exit("gh: Not Found (HTTP 404)")
    sys.stdout.buffer.write(r.stdout)
else:
    sys.exit("fake gh: unexpected call %r" % a)
"""

KEPT = "The store SHALL keep every record it is given for at least thirty days after the last read."
SEAT = "Each record SHALL name the seat that wrote it, as the seat file recorded it at the time."
SEAT_REWORDED = "Each record SHALL carry the seat that wrote it, taken from its seat file when it was written."
AUDIT = "Every change to a record SHALL be written to the audit log with the seat that made it."
SEARCH = "A search SHALL return the records whose text matches the query, newest first, at most fifty."


def modified(name, *sentences):
    return (f"## MODIFIED Requirements\n\n### Requirement: {name}\n\n{' '.join(sentences)}\n\n"
            "#### Scenario: A record survives\n\n- **WHEN** a record is written\n"
            "- **THEN** it can be read for thirty days\n")


def renamed(old, new):
    return (f"## RENAMED Requirements\n\n- FROM: `### Requirement: {old}`\n"
            f"- TO: `### Requirement: {new}`\n\n")


# seat-files renames "Records are kept" and rewrites it, keeping one sentence.
SEAT_FILES = renamed("Records are kept", "Records are retained") + modified("Records are retained", KEPT, SEAT)


def stacked_proposal(*deps):
    lines = "".join(f"Builds on: {d}\n" for d in deps)
    return f"# Lore search\n\n{lines}\n" + GOOD_PROPOSAL


class Stack:
    """A repository with a bare remote at <tmp>/acme/widgets.git, a colleague's
    clone that pushes dependency branches to it, and a fake gh that knows
    those branches as pull requests. The repository under test never has the
    dependencies' commits until spec-check fetches them."""

    SLUG = "acme/widgets"

    def __init__(self, test, openspec=True):
        # A stacked change is checked by archiving its dependencies with the
        # OpenSpec CLI, so a test that gets that far needs it.
        if openspec and not HAS_OPENSPEC:
            test.skipTest("needs OpenSpec 1.15.0 or later")
        self.test = test
        self.repo = Repo(test)
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-stack-")).resolve()
        test.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.bare = tmp / "acme" / "widgets.git"
        self.bare.parent.mkdir()
        self.sh("git", "init", "-q", "--bare", "-b", "main", str(self.bare))
        self.repo.git("remote", "add", "origin", str(self.bare))
        self.repo.git("push", "-q", "origin", "main")
        self.repo.git("fetch", "-q", "origin")
        self.other = tmp / "other"
        self.sh("git", "clone", "-q", str(self.bare), str(self.other))
        self.sh("git", "-C", str(self.other), "config", "commit.gpgsign", "false")
        self.data_path = tmp / "gh.json"
        self.data = {"repo": self.SLUG, "prs": {}, "list": [], "git": str(self.bare)}
        self.gh = tmp / "gh"
        self.gh.write_text(f"#!{sys.executable}\n" + FAKE_GH)
        self.gh.chmod(0o755)

    def sh(self, *args):
        r = subprocess.run(args, capture_output=True, text=True, env=ENV)
        if r.returncode:
            raise AssertionError(r.stdout + r.stderr)
        return r.stdout.strip()

    def dependency(self, number, change, delta, base="origin/main", proposal=None, cap="cap",
                   state="OPEN", branch=None):
        """Pushes a branch adding `change`, and registers it as pull request
        `number`. Returns the branch name."""
        branch = branch or change
        o = str(self.other)
        self.sh("git", "-C", o, "fetch", "-q", "origin")
        self.sh("git", "-C", o, "checkout", "-q", "-B", branch, base)
        self.put(f"openspec/changes/{change}/proposal.md", proposal or GOOD_PROPOSAL)
        self.put(f"openspec/changes/{change}/specs/{cap}/spec.md", delta)
        self.put(f"openspec/changes/{change}/tasks.md", TASKS)
        self.push(branch, f"add {change}")
        self.register(number, branch, state)
        return branch

    def put(self, rel, text):
        p = self.other / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def push(self, branch, message):
        o = str(self.other)
        self.sh("git", "-C", o, "add", "-A")
        self.sh("git", "-C", o, "commit", "-q", "-m", message)
        self.sh("git", "-C", o, "push", "-q", "-f", "origin", branch)

    def register(self, number, branch, state="OPEN"):
        oid = self.sh("git", "-C", str(self.bare), "rev-parse", f"refs/heads/{branch}")
        files = self.sh("git", "-C", str(self.bare), "diff", "--name-only", "main", oid).splitlines()
        self.data["prs"][str(number)] = {"state": state, "headRefName": branch, "headRefOid": oid,
                                         "isCrossRepository": False,
                                         "files": [{"path": f} for f in files],
                                         "all_files": files}  # what the files API lists
        self.data["list"] = [p for p in self.data["list"] if p["number"] != number]
        if state == "OPEN":
            self.data["list"].append({"number": number, "headRefOid": oid,
                                      "files": [{"path": f} for f in files]})

    def merge(self, number, oid=None):
        """Marks pull request number merged. spec-check reads no merge
        commit, so oid is unused; a caller passes it only to show the reader
        which commit the test treats as the merge."""
        self.data["prs"][str(number)]["state"] = "MERGED"

    def env(self, gh=True):
        self.data_path.write_text(json.dumps(self.data))
        return dict(ENV, SPEC_CHECK_GH=str(self.gh), FAKE_GH=str(self.data_path)) if gh else ENV

    def calls(self):
        log = pathlib.Path(str(self.data_path) + ".log")
        return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []

    def stacked(self, delta, *deps, name="lore-search"):
        self.repo.change(name, proposal=stacked_proposal(*deps), delta=delta)

    def check(self, *args, gh=True):
        return self.repo.check(*args, env=self.env(gh))


def merged_then_archiving(stack, number, change, delta, proposal=GOOD_PROPOSAL, date="2026-10-01"):
    """Commits change, still open under openspec/changes/, as the merge
    commit of pull request number, then stages the move of change into the
    archive, as `openspec archive` would. The caller writes the archived
    specs and commits; that commit is the archive."""
    r = stack.repo
    r.change(change, proposal=proposal, delta=delta)
    r.git("add", "-A")
    r.git("commit", "-q", "-m", f"merge #{number}")
    stack.merge(number, r.git("rev-parse", "HEAD"))
    (r.path / "openspec/changes/archive").mkdir(parents=True, exist_ok=True)
    r.git("mv", f"openspec/changes/{change}", f"openspec/changes/archive/{date}-{change}")


def errors(result):
    return [l for l in result.stdout.splitlines() if ": error [" in l]


class StackedChangeTests(unittest.TestCase):
    """lore-search builds on seat-files (PR 171), as igor PR #216 builds on igor
    PR #171: seat-files renames and rewrites a requirement, and the rewritten
    text shares sentences with the old one, which only seat-files removes."""

    def setUp(self):
        self.s = Stack(self)
        self.s.dependency(171, "seat-files", SEAT_FILES)
        self.lore = modified("Records are retained", KEPT, SEAT, SEARCH)

    def test_without_the_declaration_the_shared_sentence_is_a_duplicate(self):
        self.s.repo.change("lore-search", delta=self.lore)
        r = self.s.check("lore-search", gh=False)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(kinds(r), ["duplicate", "archive"])
        self.assertIn('also stated in "Records are kept"', r.stdout)
        # On main alone, there is no "Records are retained" to modify.
        self.assertIn('error [archive] "Records are retained" in cap: `openspec archive` would refuse', r.stdout)
        self.assertNotIn("Builds on", r.stdout)  # no gh, so no hint

    def test_with_the_declaration_it_checks_against_main_plus_the_dependency(self):
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(kinds(r), [])
        self.assertIn("lore-search builds on seat-files (acme/widgets#171", r.stdout)
        self.assertIn("; checked against main plus it\n", r.stdout)

    def test_both_changes_in_one_tree_need_the_declaration_too(self):
        self.s.repo.change("seat-files", delta=SEAT_FILES)
        self.s.repo.change("lore-search", delta=self.lore)
        self.assertEqual(kinds(self.s.check("lore-search", gh=False)), ["duplicate", "archive"])
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(kinds(r), [], r.stdout + r.stderr)

    def test_the_dependency_is_read_without_checking_anything_out(self):
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        before = (self.s.repo.git("rev-parse", "--abbrev-ref", "HEAD"), self.s.repo.git("status", "--porcelain"))
        self.s.check("lore-search")
        self.assertEqual(before, (self.s.repo.git("rev-parse", "--abbrev-ref", "HEAD"),
                                  self.s.repo.git("status", "--porcelain")))
        self.assertEqual(self.s.repo.git("branch", "--list", "seat-files"), "")

    def test_a_duplicate_of_what_the_dependency_adds_is_still_reported(self):
        self.s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH)
                       + "\n## ADDED Requirements\n\n### Requirement: Seats are shown\n\n" + SEAT
                       + "\n\n#### Scenario: s\n\n- **WHEN** w\n- **THEN** t\n",
                       "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(set(kinds(r)), {"duplicate"})  # its MODIFIED and ADDED requirements share SEAT too
        self.assertIn("openspec/changes/seat-files/specs/cap/spec.md", r.stdout)
        self.assertIn("in acme/widgets#171", r.stdout)

    def test_the_hint_names_the_line_to_add(self):
        self.s.repo.change("lore-search", delta=self.lore)
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(kinds(r), ["duplicate", "archive"])
        self.assertIn("Builds on: seat-files (acme/widgets#171)", r.stdout)

    def test_no_hint_when_no_open_pull_request_retires_the_requirement(self):
        self.s.data["list"] = []
        self.s.repo.change("lore-search", delta=self.lore)
        r = self.s.check("lore-search")
        self.assertEqual(kinds(r), ["duplicate", "archive"])
        self.assertNotIn("Builds on", r.stdout)

    def test_no_hint_when_gh_cannot_list_pull_requests(self):
        self.s.data["list"] = None
        self.s.repo.change("lore-search", delta=self.lore)
        r = self.s.check("lore-search")
        self.assertEqual(kinds(r), ["duplicate", "archive"])
        self.assertNotIn("Builds on", r.stdout)

    def test_the_hint_lookup_is_bounded_and_made_once(self):
        for n in range(300, 330):  # thirty more open PRs that each touch cap
            self.s.dependency(n, f"other-{n}", GOOD_DELTA.replace("Records expire", f"Thing {n}"))
        self.s.repo.change("lore-search", delta=self.lore)
        self.s.repo.change("lore-two", delta=self.lore)
        self.s.check()
        calls = self.s.calls()
        self.assertEqual(sum(1 for c in calls if c[:2] == ["pr", "list"]), 1)
        self.assertLessEqual(sum(1 for c in calls if c[:1] == ["api"]), 20)

    def test_drift_when_the_dependency_renamed_the_requirement_again(self):
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        self.s.put("openspec/changes/seat-files/specs/cap/spec.md",
                   renamed("Records are kept", "Records are held") + modified("Records are held", KEPT, SEAT))
        self.s.push("seat-files", "rename again")
        self.s.register(171, "seat-files")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 1)
        self.assertIn("drift", kinds(r))
        drift = [l for l in errors(r) if "[drift]" in l][0]
        self.assertIn('"Records are retained"', drift)
        self.assertIn("seat-files (acme/widgets#171)", drift)

    def test_drift_when_the_dependency_reworded_a_sentence(self):
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        self.s.put("openspec/changes/seat-files/specs/cap/spec.md",
                   renamed("Records are kept", "Records are retained")
                   + modified("Records are retained", KEPT, SEAT_REWORDED))
        self.s.push("seat-files", "reword")
        self.s.register(171, "seat-files")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 0, r.stdout)  # a check shows both texts; it never fails
        self.assertEqual(kinds(r), ["drift"])
        self.assertIn('"Records are retained"', r.stdout)
        self.assertIn("seat-files (acme/widgets#171)", r.stdout)
        self.assertIn(": check [drift]", r.stdout)
        self.assertIn(SEAT, r.stdout)
        self.assertIn(SEAT_REWORDED, r.stdout)

    def test_a_sentence_of_the_stacked_change_own_is_not_drift(self):
        self.s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH, AUDIT), "seat-files (acme/widgets#171)")
        self.assertEqual(kinds(self.s.check("lore-search")), [])

    def test_drift_when_a_removed_requirement_is_gone(self):
        self.s.stacked(GOOD_DELTA + "\n## REMOVED Requirements\n\n### Requirement: Records are kept\n\n"
                       "**Reason**: replaced.\n", "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(kinds(r), ["drift"])
        self.assertIn('removes "Records are kept" in cap, which seat-files (acme/widgets#171) renames to '
                      '"Records are retained"', r.stdout)

    def test_modifying_a_requirement_nobody_defines_is_an_error(self):
        self.s.stacked(modified("Records are lost", KEPT), "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertIn("drift", kinds(r))
        self.assertIn('modifies "Records are lost" in cap, which neither main nor its dependencies define',
                      r.stdout)

    def test_an_unknown_pull_request_is_an_error_not_a_pass(self):
        self.s.stacked(self.lore, "seat-files (acme/widgets#999)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(kinds(r), ["stack"])
        self.assertIn("seat-files (acme/widgets#999)", r.stdout)
        self.assertIn("duplicate and drift checks did not run", r.stdout)

    def test_no_gh_is_an_error_not_a_pass(self):
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search", gh=False)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(kinds(r), ["stack"])
        self.assertIn("seat-files (acme/widgets#171)", r.stdout)

    def test_a_closed_pull_request_is_an_error(self):
        self.s.data["prs"]["171"]["state"] = "CLOSED"
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(kinds(r), ["stack"])
        self.assertIn("closed", r.stdout)

    def test_a_branch_without_the_change_is_an_error(self):
        self.s.stacked(self.lore, "seat-tables (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(kinds(r), ["stack"])
        self.assertIn("#171 holds no change seat-tables", r.stdout)

    def test_an_unreachable_branch_is_an_error(self):
        self.s.data["prs"]["171"]["headRefOid"] = "0" * 40
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(kinds(r), ["stack"])
        self.assertIn("seat-files (acme/widgets#171)", r.stdout)

    def test_a_repository_with_no_remote_here_is_an_error(self):
        self.s.data["repo"] = "acme/gadgets"
        self.s.data["prs"]["5"] = self.s.data["prs"]["171"]
        self.s.stacked(self.lore, "seat-files (acme/gadgets#5)")
        r = self.s.check("lore-search")
        self.assertEqual(kinds(r), ["stack"])
        self.assertIn("acme/gadgets", r.stdout)

    def test_a_malformed_declaration_is_an_error(self):
        for line in ("**Builds on:** seat-files (acme/widgets#171)", "Builds on: seat-files (#171)",
                     "Builds on: seat-files", "- Builds on: seat-files (acme/widgets#171)"):
            with self.subTest(line=line):
                self.s.repo.change("lore-search", delta=self.lore,
                                   proposal="# Lore search\n\n" + line + "\n\n" + GOOD_PROPOSAL)
                r = self.s.check("lore-search")
                self.assertIn("stack", kinds(r))
                self.assertIn("Builds on: <change> (<owner>/<repo>#<number>)", r.stdout)

    def test_a_declaration_in_a_code_fence_is_quoted_text(self):
        self.s.repo.change("x", proposal=GOOD_PROPOSAL + "\n```\nBuilds on: seat-files (#171)\n```\n")
        self.assertEqual(kinds(self.s.check("x")), [])
        self.assertEqual(self.s.calls(), [])

    def test_an_archived_dependency_says_to_remove_the_line(self):
        # seat-files has been archived into main: main's spec holds its result.
        merged_then_archiving(self.s, 171, "seat-files", SEAT_FILES)
        main_spec = MAIN_SPEC.replace("### Requirement: Records are kept\n\n" + KEPT,
                                      "### Requirement: Records are retained\n\n" + KEPT + " " + SEAT)
        self.s.repo.write("openspec/specs/cap/spec.md", main_spec)
        self.s.repo.write("openspec/changes/archive/2026-10-01-seat-files/proposal.md", GOOD_PROPOSAL)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "archive seat-files")
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 0, r.stdout)  # a check, never an error
        self.assertEqual(kinds(r), ["stack"])
        self.assertIn(": check [stack]", r.stdout)
        self.assertIn("already in the tree", r.stdout)
        self.assertIn("remove the `Builds on: seat-files (acme/widgets#171)` line", r.stdout)

    def test_a_dependency_archived_on_the_base_but_not_in_this_tree(self):
        self.s.repo.git("checkout", "-q", "-b", "stale")
        self.s.repo.git("checkout", "-q", "main")
        self.s.repo.write("openspec/changes/archive/2026-10-01-seat-files/proposal.md", GOOD_PROPOSAL)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "archive seat-files")
        self.s.repo.git("checkout", "-q", "stale")
        self.s.merge(171, self.s.repo.git("rev-parse", "main"))  # merged into main, not into stale
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        # #171 has merged, but this tree lacks the requirements it set: a blocking error.
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("seat-files (acme/widgets#171): #171 has merged, but this branch does not hold its result", r.stdout)

    def test_a_merged_pull_request_whose_branch_is_gone_is_still_read_and_judged(self):
        self.s.merge(171, "f" * 40)  # merged by a commit this repository does not have
        self.s.sh("git", "-C", str(self.s.bare), "update-ref", "refs/pull/171/head",
                  self.s.data["prs"]["171"]["headRefOid"])
        self.s.sh("git", "-C", str(self.s.bare), "update-ref", "-d", "refs/heads/seat-files")
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        # #171 has merged, but this tree lacks the requirements it set: a blocking error.
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("seat-files (acme/widgets#171): #171 has merged, but this branch does not hold its result", r.stdout)

    def test_sign_checks_the_stack_too(self):
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        self.s.repo.git("add", "-A")
        r = self.s.repo.run("sign", "--read", "self", "--base", "main", "--no-validate", env=self.s.env())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.s.repo.run("sign", "--read", "self", "--base", "main", "--no-validate", env=self.s.env(gh=False))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("[stack]", r.stdout)

    def test_a_branch_is_checked_with_its_stack(self):
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        self.s.repo.git("checkout", "-q", "-b", "lore")
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "lore")
        self.s.repo.git("checkout", "-q", "main")
        r = self.s.check("--ref", "lore", "lore-search")
        self.assertEqual(kinds(r), [], r.stdout + r.stderr)


class StackedNewCapabilityTests(unittest.TestCase):
    """A capability a dependency creates already exists for the change built
    on it: its Purpose came from the dependency's delta."""

    def setUp(self):
        self.s = Stack(self)
        self.s.dependency(171, "audit-log", purposed(PURPOSE, added_req("Audit trail", AUDIT)), cap="audit")
        self.later = added_req("Audit search", SEARCH)

    def stacked(self, delta):
        self.s.repo.change("lore-search", proposal=stacked_proposal("audit-log (acme/widgets#171)"),
                           delta=delta, cap="audit")
        return self.s.check("lore-search")

    def test_no_purpose_is_needed(self):
        r = self.stacked(self.later)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(kinds(r), [])

    def test_a_purpose_is_a_check_that_it_is_ignored(self):
        r = self.stacked(purposed("Lets a reviewer search the audit log by seat and by record.", self.later))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(kinds(r), ["purpose"])
        self.assertIn("openspec/changes/lore-search/specs/audit/spec.md:1: check [purpose] audit already "
                      "exists", r.stdout)
        self.assertIn("edit it in the change this one builds on that creates it", r.stdout)

    def test_without_the_declaration_it_is_new(self):
        self.s.repo.change("lore-search", delta=self.later, cap="audit")
        r = self.s.check("lore-search", gh=False)
        self.assertIn("lore-search creates audit, and its delta has no `## Purpose`", r.stdout)


class StackedChainTests(unittest.TestCase):
    """lore-search builds on seat-audit, which builds on seat-files."""

    def setUp(self):
        self.s = Stack(self)
        self.s.dependency(171, "seat-files", SEAT_FILES)
        self.s.dependency(172, "seat-audit", modified("Records are retained", KEPT, SEAT, AUDIT),
                          base="seat-files",
                          proposal=stacked_proposal("seat-files (acme/widgets#171)"))
        self.lore = modified("Records are retained", KEPT, SEAT, AUDIT, SEARCH)

    def test_a_chain_listed_in_order_passes(self):
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)", "seat-audit (acme/widgets#172)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(kinds(r), [])

    def test_a_missing_link_names_the_line_to_add_first(self):
        self.s.stacked(self.lore, "seat-audit (acme/widgets#172)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 1)
        self.assertIn("stack", kinds(r))
        self.assertIn("seat-audit (acme/widgets#172) builds on seat-files (acme/widgets#171)", r.stdout)
        self.assertNotIn("duplicate", kinds(r))

    def test_a_chain_listed_out_of_order_is_an_error(self):
        self.s.stacked(self.lore, "seat-audit (acme/widgets#172)", "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 1)
        self.assertIn("stack", kinds(r))
        self.assertIn("before", r.stdout)

    def test_the_same_dependency_twice_is_an_error(self):
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)", "seat-files (acme/widgets#171)",
                       "seat-audit (acme/widgets#172)")
        self.assertIn("stack", kinds(self.s.check("lore-search")))



class FoundByBugHunterStackTests(unittest.TestCase):
    """Regressions found by bug-hunter's first pass over stacked changes."""

    def setUp(self):
        self.s = Stack(self)
        self.s.dependency(171, "seat-files", SEAT_FILES)
        self.lore = modified("Records are retained", KEPT, SEAT, SEARCH)

    def test_a_stacked_change_may_rename_and_modify_under_the_new_name(self):
        self.s.stacked(renamed("Records are retained", "Records are searchable")
                       + modified("Records are searchable", KEPT, SEAT, SEARCH),
                       "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_sentence_the_dependency_dropped_is_not_drift(self):
        # The stack was made by moving the search rule out of seat-files.
        self.s.dependency(171, "seat-files", renamed("Records are kept", "Records are retained")
                          + modified("Records are retained", KEPT, SEAT, SEARCH))
        self.s.put("openspec/changes/seat-files/specs/cap/spec.md", SEAT_FILES)
        self.s.push("seat-files", "move search out")
        self.s.register(171, "seat-files")
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_an_older_archived_change_of_the_same_name_is_not_the_dependency(self):
        self.s.repo.write("openspec/changes/archive/2025-01-01-seat-files/proposal.md",
                          GOOD_PROPOSAL.replace("Records expire.", "An older change of the same name."))
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "an old seat-files")
        self.s.repo.git("push", "-q", "origin", "main")
        self.s.dependency(171, "seat-files", SEAT_FILES)
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_change_cannot_build_on_itself(self):
        delta = GOOD_DELTA.replace("Records expire", "Lore is kept").replace(
            "The store SHALL delete a record ninety days after its last read.", KEPT)
        self.s.dependency(216, "lore-search", delta)
        self.s.stacked(delta, "lore-search (acme/widgets#216)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("stack", kinds(r))

    def test_only_an_archived_dependency_prints_no_empty_stack_line(self):
        self.s.repo.write("openspec/changes/archive/2026-10-01-seat-files/proposal.md", GOOD_PROPOSAL)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "archive seat-files")
        self.s.merge(171)
        self.s.stacked(GOOD_DELTA, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertNotIn("builds on ;", r.stdout)


class FoundByBugHunterStackIteration2Tests(unittest.TestCase):
    """Regressions found by bug-hunter's second pass over stacked changes."""

    def setUp(self):
        self.s = Stack(self)
        self.s.dependency(171, "seat-files", SEAT_FILES)

    def test_a_merged_dependency_not_yet_archived_beside_an_older_archive_of_its_name(self):
        self.s.repo.write("openspec/changes/archive/2025-01-01-seat-files/proposal.md",
                          GOOD_PROPOSAL.replace("Records expire.", "An older change of the same name."))
        self.s.repo.change("seat-files", delta=SEAT_FILES)  # merged, not archived
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "merge seat-files")
        self.s.merge(171)
        self.s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH), "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_dependency_delta_that_is_not_utf8_is_not_a_crash(self):
        path = self.s.other / "openspec/changes/seat-files/specs/cap/spec.md"
        path.write_bytes(SEAT_FILES.replace("seat file", "s\u00e9at file").encode("latin-1"))
        self.s.push("seat-files", "latin-1")
        self.s.register(171, "seat-files")
        self.s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH), "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("spec-check:", r.stdout)


class FoundByBugHunterStackIteration3Tests(unittest.TestCase):
    """Regressions found by bug-hunter's third pass over stacked changes."""

    def setUp(self):
        self.s = Stack(self)
        self.s.dependency(171, "seat-files", SEAT_FILES)

    def test_a_hint_read_that_is_not_utf8_is_not_a_crash(self):
        path = self.s.other / "openspec/changes/seat-files/specs/cap/spec.md"
        path.write_bytes(SEAT_FILES.replace("seat file", "s\u00e9at file").encode("latin-1"))
        self.s.push("seat-files", "latin-1")
        self.s.register(171, "seat-files")
        self.s.repo.change("lore-search", delta=modified("Records are retained", KEPT, SEAT, SEARCH))
        r = self.s.check("lore-search")
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(kinds(r), ["duplicate", "archive"])

    def test_a_branch_from_before_the_merge_beside_an_older_archive_of_its_name(self):
        old = GOOD_PROPOSAL.replace("Records expire.", "An older change of the same name.")
        self.s.repo.write("openspec/changes/archive/2025-01-01-seat-files/proposal.md", old)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "an older seat-files")
        self.s.repo.git("checkout", "-q", "-b", "lore")
        self.s.repo.git("checkout", "-q", "main")
        self.s.repo.change("seat-files", delta=SEAT_FILES)  # #171 merges, not archived
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "merge seat-files")
        self.s.repo.git("checkout", "-q", "lore")
        self.s.merge(171, self.s.repo.git("rev-parse", "main"))  # merged into main, not into lore
        self.s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH), "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        # #171 has merged, but this tree lacks the requirements it set: a blocking error.
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("seat-files (acme/widgets#171): #171 has merged, but this branch does not hold its result", r.stdout)

class FoundByBugHunterRun8StackTests(unittest.TestCase):
    """Stack regressions found by the first iteration of bug-hunter's eighth run."""

    def test_a_dependency_changing_only_a_fenced_example_is_not_already_in_the_tree(self):
        # `openspec show` leaves fenced code out of a requirement's text, and
        # `openspec archive` writes it.
        s = Stack(self)
        fence = "for at least thirty days after the last read.\n\n```json\n{json}\n```\n"
        main = MAIN_SPEC.replace("for at least thirty days after the last read.\n",
                                 fence.replace("{json}", '{"days": 30}'))
        s.repo.write("openspec/specs/cap/spec.md", main)
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "a fenced example")
        s.repo.git("push", "-q", "origin", "main")
        s.dependency(171, "json-shape", modified("Records are kept", KEPT).replace(
            KEPT + "\n", KEPT + '\n\n```json\n{"days": 30, "unit": "day"}\n```\n'))
        s.stacked(GOOD_DELTA, "json-shape (acme/widgets#171)")
        r = s.check("lore-search")
        self.assertNotIn("already in the tree", r.stdout)
        self.assertIn("lore-search builds on json-shape (acme/widgets#171", r.stdout)

    SC = "#### Scenario: S\n\n- **WHEN** w\n- **THEN** t\n"
    SEAT_RULE = "Every record SHALL carry the seat that wrote it, taken from its seat file."
    AUDITED = ("### Requirement: Records are audited\n\nThe store SHALL log each read.\n\n"
               "#### Scenario: A read is logged\n\n- **WHEN** a record is read\n- **THEN** the read is logged\n")
    FRESH = ("### Requirement: Fresh\n\nThe store SHALL be fresh.\n\n" + SC + "\n### Notes\n\n" + SEAT_RULE + "\n")
    SEATS = "## ADDED Requirements\n\n### Requirement: Seats\n\n" + SEAT_RULE + "\n\n" + SC

    def audited_on_main(self, s):
        s.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n" + self.AUDITED)
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "audited")
        s.repo.git("push", "-q", "origin", "main")

    def test_a_dependency_is_archived_as_written_with_its_stray_text(self):
        # The archive keeps "### Notes" and its sentence inside "Fresh". In a
        # main spec, `openspec show` takes any `###` heading for a
        # requirement, so it reads "Notes" as one, which the stacked change
        # repeats.
        s = Stack(self)
        s.dependency(171, "fresh", "## ADDED Requirements\n\n" + self.FRESH)
        s.stacked(self.SEATS, "fresh (acme/widgets#171)")
        self.assertIn('error [duplicate] this rule is also stated in "Notes"', s.check("lore-search").stdout)

    def test_a_dependency_partly_in_the_tree_keeps_its_stray_text(self):
        s = Stack(self)
        self.audited_on_main(s)
        s.dependency(171, "fresh", "## ADDED Requirements\n\n" + self.AUDITED + "\n" + self.FRESH)
        s.stacked(self.SEATS, "fresh (acme/widgets#171)")
        self.assertIn('error [duplicate] this rule is also stated in "Notes"', s.check("lore-search").stdout)

    def test_a_removal_kept_from_a_dependency_partly_in_the_tree_is_applied(self):
        s = Stack(self)
        self.audited_on_main(s)
        s.dependency(171, "drop-kept", "## REMOVED Requirements\n\n### Requirement: Records are kept\n\n"
                     "**Reason**: moved\n\n## ADDED Requirements\n\n" + self.AUDITED)
        s.stacked("## ADDED Requirements\n\n### Requirement: Records are kept\n\n"
                  "The store SHALL keep records a year.\n\n" + self.SC, "drop-kept (acme/widgets#171)")
        r = s.check("lore-search")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('the rest were applied (removes "Records are kept" from cap)', r.stdout)

    def fenced_dependency(self, main_after, dep_after):
        """main's "Records are kept" and json-shape's MODIFIED version of it,
        each ending with main_after and dep_after."""
        s = Stack(self)
        s.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + main_after)
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "a fenced example")
        s.repo.git("push", "-q", "origin", "main")
        s.dependency(171, "json-shape", modified("Records are kept", KEPT) + dep_after)
        s.stacked(GOOD_DELTA, "json-shape (acme/widgets#171)")
        return s.check("lore-search")

    def test_a_fenced_example_ending_the_file_is_compared(self):
        # With no scenario after it, the fence is the last thing in the file.
        s = Stack(self)
        kept = f"### Requirement: Records are kept\n\n{KEPT}\n\n```json\n{{json}}\n```\n"
        s.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.split("### Requirement")[0]
                     + kept.replace("{json}", '{"days": 30}'))
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "a fenced example")
        s.repo.git("push", "-q", "origin", "main")
        s.dependency(171, "json-shape", "## MODIFIED Requirements\n\n"
                     + kept.replace("{json}", '{"days": 30, "unit": "day"}'))
        s.stacked(GOOD_DELTA, "json-shape (acme/widgets#171)")
        self.assertNotIn("already in the tree", s.check("lore-search").stdout)

    def test_a_fenced_example_under_a_stray_heading_is_compared(self):
        r = self.fenced_dependency('\n### Notes\n\n```json\n{"days": 30}\n```\n',
                                   '\n### Notes\n\n```json\n{"days": 30, "unit": "day"}\n```\n')
        self.assertNotIn("already in the tree", r.stdout)

    def test_a_nested_capability_gets_the_hint(self):
        s = Stack(self)
        s.repo.write("openspec/specs/area/cap/spec.md", MAIN_SPEC)
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "nested")
        s.repo.git("push", "-q", "origin", "main")
        s.dependency(171, "seat-files", SEAT_FILES, cap="area/cap")
        s.repo.change("lore-search", cap="area/cap", delta=f"## ADDED Requirements\n\n### Requirement: Twice\n\n"
                      f"{KEPT}\n\n#### Scenario: S\n\n- **WHEN** w\n- **THEN** t\n")
        self.assertIn("Builds on: seat-files (acme/widgets#171)", s.check("lore-search").stdout)

class FoundByBugHunterRun8Iteration2Tests(unittest.TestCase):
    """Regressions found by the second iteration of bug-hunter's eighth run."""

    def test_names_that_differ_only_by_backticks_keep_their_own_blocks(self):
        # OpenSpec reads them as two names. `openspec show` lists the ADDED
        # one before the MODIFIED one, the reverse of the file, so a search
        # matching names loosely would give each the other's header line.
        s = Stack(self)
        s.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n" + FoundByBugHunterRun8StackTests.AUDITED)
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "audited")
        s.repo.git("push", "-q", "origin", "main")
        s.dependency(171, "twin", modified("Records are kept", "The store SHALL keep every record for a year.")
                     + "\n## ADDED Requirements\n\n### Requirement: Records are `kept`\n\n"
                     "The store SHALL mark each kept record.\n\n#### Scenario: S\n\n- **WHEN** w\n- **THEN** t\n\n"
                     + FoundByBugHunterRun8StackTests.AUDITED)
        s.stacked(GOOD_DELTA, "twin (acme/widgets#171)")
        r = s.check("lore-search")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("the rest were applied", r.stdout)


class FoundByBugHunterRun2Tests(unittest.TestCase):
    """Regressions found by a bug-hunter run over an earlier rule, which
    recognised a dependency's archive by matching its proposal, and over the
    check severities (Adam, 2026-10-24)."""

    def setUp(self):
        self.s = Stack(self)
        self.s.dependency(171, "seat-files", SEAT_FILES)
        self.s.put("openspec/changes/seat-files/specs/cap/spec.md",
                   renamed("Records are kept", "Records are retained")
                   + modified("Records are retained", KEPT, SEAT_REWORDED))
        self.s.push("seat-files", "reword")
        self.s.register(171, "seat-files")
        self.lore = modified("Records are retained", KEPT, SEAT, SEARCH)

    def archive_on_its_branch_and_merge(self):
        s, o = self.s, str(self.s.other)
        (s.other / "openspec/changes/archive").mkdir(parents=True)
        s.sh("git", "-C", o, "mv", "openspec/changes/seat-files", "openspec/changes/archive/2026-10-01-seat-files")
        s.sh("git", "-C", o, "commit", "-q", "-m", "archive")
        s.sh("git", "-C", o, "push", "-q", "origin", "seat-files")
        s.register(171, "seat-files")
        s.sh("git", "-C", o, "checkout", "-q", "main")
        s.sh("git", "-C", o, "merge", "-q", "--no-ff", "-m", "merge 171", "seat-files")
        s.sh("git", "-C", o, "push", "-q", "origin", "main")
        s.merge(171, s.sh("git", "-C", str(s.bare), "rev-parse", "main"))  # not fetched here

    def test_a_dependency_archived_in_the_tree_still_gets_sentence_drift(self):
        merged_then_archiving(self.s, 171, "seat-files", SEAT_FILES)
        main_spec = MAIN_SPEC.replace("### Requirement: Records are kept\n\n" + KEPT,
                                      "### Requirement: Records are retained\n\n" + KEPT + " " + SEAT_REWORDED)
        self.s.repo.write("openspec/specs/cap/spec.md", main_spec)
        self.s.repo.write("openspec/changes/archive/2026-10-01-seat-files/proposal.md", GOOD_PROPOSAL)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "archive seat-files")
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertIn(": check [drift]", r.stdout)
        self.assertIn(SEAT_REWORDED, r.stdout)

    def test_a_merged_dependency_archived_on_its_branch_with_a_stale_base(self):
        self.archive_on_its_branch_and_merge()  # origin/main here is not fetched
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.repo.run("check", "--no-validate", "lore-search", env=self.s.env())
        # #171 has merged, but this tree lacks the requirements it set: a blocking error.
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("seat-files (acme/widgets#171): #171 has merged, but this branch does not hold its result", r.stdout)

    def test_an_archive_the_branch_inherited_from_main_is_not_the_dependency(self):
        old = GOOD_PROPOSAL.replace("Records expire.", "An older change of the same name.")
        self.s.repo.write("openspec/changes/archive/2025-01-01-seat-files/proposal.md", old)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "an older seat-files")
        self.s.repo.git("push", "-q", "origin", "main")
        self.s.dependency(172, "seat-files-v2", SEAT_FILES, branch="seat-files-v2")
        self.s.stacked(self.lore, "seat-files (acme/widgets#172)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 1)
        self.assertIn("#172 holds no change seat-files", r.stdout)
        self.assertNotIn("2025-01-01-seat-files", r.stdout)


class FoundByBugHunterRun2Iteration2Tests(unittest.TestCase):
    """Regressions found by the second iteration of that run."""

    def setUp(self):
        self.s = Stack(self)

    def archive_on_its_branch_and_merge(self):
        s, o = self.s, str(self.s.other)
        (s.other / "openspec/changes/archive").mkdir(parents=True)
        s.sh("git", "-C", o, "mv", "openspec/changes/seat-files", "openspec/changes/archive/2026-10-01-seat-files")
        s.sh("git", "-C", o, "commit", "-q", "-m", "archive")
        s.sh("git", "-C", o, "push", "-q", "origin", "seat-files")
        s.register(171, "seat-files")
        s.sh("git", "-C", o, "checkout", "-q", "main")
        s.sh("git", "-C", o, "merge", "-q", "--no-ff", "-m", "merge 171", "seat-files")
        s.sh("git", "-C", o, "push", "-q", "origin", "main")
        s.merge(171, s.sh("git", "-C", str(s.bare), "rev-parse", "main"))  # not fetched here

    def test_an_archive_whose_proposal_was_edited_on_main_is_still_recognised(self):
        prop = "# Seat files\n\nBuilds on: z-base (acme/widgets#160)\n\n" + GOOD_PROPOSAL
        self.s.dependency(160, "z-base", "")  # seat-files builds on it, and it changes no spec
        self.s.dependency(171, "seat-files", SEAT_FILES, proposal=prop)
        merged_then_archiving(self.s, 171, "seat-files", SEAT_FILES, proposal=prop)
        main_spec = MAIN_SPEC.replace("### Requirement: Records are kept\n\n" + KEPT,
                                      "### Requirement: Records are retained\n\n" + KEPT + " " + SEAT)
        self.s.repo.write("openspec/specs/cap/spec.md", main_spec)
        self.s.repo.write("openspec/changes/archive/2026-10-01-seat-files/proposal.md",
                          "# Seat files\n\n" + GOOD_PROPOSAL)  # the line was removed on main
        self.s.repo.write("openspec/changes/archive/2026-01-01-z-base/proposal.md", GOOD_PROPOSAL)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "archive seat-files")
        self.s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH), "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertIn("already in the tree", r.stdout)
        self.assertNotIn("does not apply", r.stdout)

    def test_a_dependency_read_from_its_archive_is_cited_at_the_archive(self):
        self.s.dependency(171, "seat-files", SEAT_FILES)
        self.archive_on_its_branch_and_merge()
        self.s.data["prs"]["171"]["state"] = "OPEN"  # archived on its branch, not merged yet
        delta = GOOD_DELTA.replace("Records expire", "Lore names seat").replace(
            "The store SHALL delete a record ninety days after its last read.", SEAT)
        self.s.stacked(delta, "seat-files (acme/widgets#171)")
        r = self.s.repo.run("check", "--no-validate", "lore-search", env=self.s.env())
        self.assertIn("openspec/changes/archive/2026-10-01-seat-files/specs/cap/spec.md", r.stdout)

    def test_an_inherited_archive_with_a_stale_base_is_not_called_the_branchs_own(self):
        o = str(self.s.other)
        self.s.sh("git", "-C", o, "checkout", "-q", "main")
        self.s.put("openspec/changes/archive/2025-01-01-seat-files/proposal.md",
                   GOOD_PROPOSAL.replace("Records expire.", "An older change of the same name."))
        self.s.push("main", "older seat-files archive")  # not fetched here
        self.s.dependency(172, "seat-files-v2", SEAT_FILES, branch="seat-files-v2")
        self.s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH), "seat-files (acme/widgets#172)")
        r = self.s.repo.run("check", "--no-validate", "lore-search", env=self.s.env())
        self.assertIn("#172 holds no change seat-files", r.stdout)
        self.assertNotIn("once #172 merges", r.stdout)

    def test_a_requirement_an_archived_dependency_renamed_says_so(self):
        self.s.dependency(171, "seat-files", SEAT_FILES)
        merged_then_archiving(self.s, 171, "seat-files", SEAT_FILES)
        main_spec = MAIN_SPEC.replace("### Requirement: Records are kept\n\n" + KEPT,
                                      "### Requirement: Records are retained\n\n" + KEPT + " " + SEAT)
        self.s.repo.write("openspec/specs/cap/spec.md", main_spec)
        self.s.repo.write("openspec/changes/archive/2026-10-01-seat-files/proposal.md", GOOD_PROPOSAL)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "archive seat-files")
        self.s.stacked(modified("Records are kept", KEPT, SEARCH), "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertIn('renames to "Records are retained"', r.stdout)

    def test_a_merged_change_still_open_here_that_does_not_apply_stays_an_error(self):
        # An older archive under the same name does not count as this
        # dependency while its change is still open in the tree.
        broken = modified("Nobody defines this", KEPT, SEAT)
        self.s.dependency(171, "seat-files", broken)
        self.s.repo.write("openspec/changes/archive/2025-01-01-seat-files/proposal.md",
                          GOOD_PROPOSAL.replace("Records expire.", "An older change of the same name."))
        self.s.repo.change("seat-files", delta=broken)  # merged, not archived
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "merge seat-files")
        self.s.merge(171)
        self.s.stacked(modified("Records are kept", KEPT, SEARCH), "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("do not fit the tree", r.stdout)


class FoundByBugHunterRun2Iteration3Tests(unittest.TestCase):
    """Regressions found by the third iteration of that run."""

    def test_a_merged_modified_only_dependency_with_an_edited_archive_hides_no_duplicate(self):
        s = Stack(self)
        prop = "# Seat files\n\nBuilds on: z-base (acme/widgets#160)\n\n" + GOOD_PROPOSAL
        s.dependency(160, "z-base", "")  # seat-files builds on it, and it changes no spec
        s.dependency(171, "seat-files", modified("Records are kept", KEPT, SEAT), proposal=prop)
        merged_then_archiving(s, 171, "seat-files", modified("Records are kept", KEPT, SEAT), proposal=prop)
        # main archived seat-files with its proposal edited, then a later change reworded the rule
        s.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace(KEPT, KEPT + " " + AUDIT))
        s.repo.write("openspec/changes/archive/2026-10-01-seat-files/proposal.md",
                     "# Seat files\n\n" + GOOD_PROPOSAL)
        s.repo.write("openspec/changes/archive/2026-01-01-z-base/proposal.md", GOOD_PROPOSAL)
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "archive seat-files, then reword")
        s.stacked("## ADDED Requirements\n\n### Requirement: Audit trail\n\n" + AUDIT +
                  "\n\n#### Scenario: s\n\n- **WHEN** w\n- **THEN** t\n", "seat-files (acme/widgets#171)")
        r = s.check("lore-search")
        # Merged, and the tree holds "Records are kept" by name, reworded since:
        # the line is stale, and the duplicate of main's text is reported.
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("error [duplicate]", r.stdout)
        self.assertIn("remove the `Builds on: seat-files (acme/widgets#171)` line", r.stdout)

    def test_a_merged_pull_request_without_the_change_does_not_take_an_inherited_archive(self):
        s = Stack(self)
        old = GOOD_PROPOSAL.replace("Records expire.", "An older change of the same name.")
        s.repo.write("openspec/changes/archive/2025-01-01-seat-files/proposal.md", old)
        s.repo.write("openspec/changes/archive/2025-01-01-seat-files/specs/cap/spec.md",
                     renamed("Old thing", "Records are kept"))
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "an older seat-files")
        s.repo.git("push", "-q", "origin", "main")
        s.dependency(172, "seat-files-v2", SEAT_FILES, branch="seat-files-v2")
        s.merge(172)
        s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH), "seat-files (acme/widgets#172)")
        r = s.check("lore-search")
        self.assertIn("error [stack]", r.stdout)
        self.assertIn("#172 holds no change seat-files", r.stdout)


MERGED_SPEC = MAIN_SPEC.replace("### Requirement: Records are kept\n\n" + KEPT,
                                "### Requirement: Records are retained\n\n" + KEPT + " " + SEAT)


class FoundByBugHunterRun3Tests(unittest.TestCase):
    """Regressions found by bug-hunter's run over the git-history archive rule."""

    def setUp(self):
        self.s = Stack(self)
        self.s.dependency(171, "seat-files", SEAT_FILES)
        self.lore = modified("Records are retained", KEPT, SEAT, SEARCH)

    def test_a_merge_of_main_in_progress_counts_main_as_merged(self):
        r = self.s.repo
        r.git("checkout", "-q", "-b", "lore")
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "lore")
        r.git("checkout", "-q", "main")
        merged_then_archiving(self.s, 171, "seat-files", SEAT_FILES)
        r.write("openspec/specs/cap/spec.md", MERGED_SPEC)
        r.write("openspec/changes/archive/2026-10-01-seat-files/proposal.md", GOOD_PROPOSAL)
        r.write("openspec/changes/archive/2026-10-01-seat-files/specs/cap/spec.md", SEAT_FILES)
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "archive #171")
        r.git("checkout", "-q", "lore")
        r.git("merge", "--no-commit", "--no-ff", "main", check=False)
        out = self.s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(": check [stack]", out.stdout)

    def test_a_change_name_reused_after_the_dependency_was_archived(self):
        r = self.s.repo
        r.change("seat-files", delta=SEAT_FILES)
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "merge #171")
        self.s.merge(171, r.git("rev-parse", "HEAD"))
        (r.path / "openspec/changes/archive").mkdir(parents=True, exist_ok=True)
        r.git("mv", "openspec/changes/seat-files", "openspec/changes/archive/2026-10-01-seat-files")
        r.write("openspec/specs/cap/spec.md", MERGED_SPEC)
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "archive seat-files")
        r.change("seat-files", delta="## REMOVED Requirements\n\n### Requirement: Records are retained\n\n"
                                     "**Reason**: x\n**Migration**: y\n")  # a later change reuses the name
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "a new seat-files")
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        out = self.s.check("lore-search")
        self.assertNotIn("seat-files (acme/widgets#171) removes", out.stdout)
        self.assertIn(": check [stack]", out.stdout)

    def test_a_large_pull_request_that_archives_its_change_on_its_branch(self):
        s, o = self.s, str(self.s.other)
        (s.other / "openspec/changes/archive").mkdir(parents=True, exist_ok=True)
        s.sh("git", "-C", o, "mv", "openspec/changes/seat-files", "openspec/changes/archive/2026-10-20-seat-files")
        for i in range(110):
            s.put(f"app/gen/f{i:03}.py", f"x = {i}\n")
        s.push("seat-files", "implement and archive")
        s.register(171, "seat-files")
        s.data["prs"]["171"]["files"] = s.data["prs"]["171"]["files"][:100]  # gh lists at most 100
        s.stacked(self.lore, "seat-files (acme/widgets#171)")
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_a_large_pull_request_whose_full_file_list_cannot_be_read_is_an_error(self):
        s = self.s
        for i in range(110):
            s.put(f"app/gen/f{i:03}.py", f"x = {i}\n")
        s.push("seat-files", "implement")
        s.register(171, "seat-files")
        s.data["prs"]["171"]["files"] = s.data["prs"]["171"]["files"][:100]
        s.data["prs"]["171"]["all_files"] = None  # the files API fails
        s.stacked(self.lore, "seat-files (acme/widgets#171)")
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("full list cannot be read", out.stdout)

    def test_a_squash_merged_dependency_keeps_the_sentence_drift_check(self):
        s = self.s
        reworded = renamed("Records are kept", "Records are retained") + modified("Records are retained", KEPT, SEAT_REWORDED)
        s.put("openspec/changes/seat-files/specs/cap/spec.md", reworded)
        s.push("seat-files", "reword")
        s.register(171, "seat-files")
        s.repo.change("seat-files", delta=reworded)  # squash-merged into main, not archived
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "seat-files (#171)")
        s.merge(171, s.repo.git("rev-parse", "HEAD"))
        s.stacked(self.lore, "seat-files (acme/widgets#171)")
        out = s.check("lore-search")
        self.assertIn(": check [drift]", out.stdout)


class FoundByBugHunterRun3Iteration2Tests(unittest.TestCase):
    """Regressions found by the second iteration of that run."""

    def test_a_reverted_modification_still_shows_by_name(self):
        s, r = Stack(self), None
        seat_only = modified("Records are kept", KEPT, SEAT)
        s.dependency(171, "seat-files", seat_only)
        r = s.repo
        r.change("seat-files", delta=seat_only)
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "merge #171")
        merge = r.git("rev-parse", "HEAD")
        s.merge(171, merge)
        r.git("revert", "--no-edit", merge)
        s.stacked(modified("Records are kept", KEPT, SEAT, SEARCH), "seat-files (acme/widgets#171)")
        out = s.check("lore-search")
        # A merged modification shows by name, whatever the text: the line is stale.
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("remove the `Builds on: seat-files (acme/widgets#171)` line", out.stdout)

    def test_an_archive_that_was_reverted_leaves_the_change_open(self):
        s = Stack(self)
        s.dependency(171, "seat-files", GOOD_DELTA)  # adds "Records expire"
        r = s.repo
        r.change("seat-files", delta=GOOD_DELTA)
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "merge #171")
        s.merge(171, r.git("rev-parse", "HEAD"))
        (r.path / "openspec/changes/archive").mkdir(parents=True, exist_ok=True)
        r.git("mv", "openspec/changes/seat-files", "openspec/changes/archive/2026-10-01-seat-files")
        r.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n" + GOOD_DELTA.split("\n", 2)[2])
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "archive seat-files")
        r.git("revert", "--no-edit", "HEAD")
        s.stacked(GOOD_DELTA.replace("ADDED", "MODIFIED").replace("its last read.", "its last read, and log it."),
                  "seat-files (acme/widgets#171)")
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_a_pull_request_at_githubs_file_cap_that_lists_the_change(self):
        s = Stack(self)
        s.dependency(171, "seat-files", SEAT_FILES)
        files = [f"app/gen/f{i:04}.py" for i in range(2997)] + [
            "openspec/changes/seat-files/proposal.md", "openspec/changes/seat-files/specs/cap/spec.md",
            "openspec/changes/seat-files/tasks.md"]
        s.data["prs"]["171"]["files"] = [{"path": f} for f in files[:100]]
        s.data["prs"]["171"]["all_files"] = files
        s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH), "seat-files (acme/widgets#171)")
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_an_archive_not_yet_committed_counts_as_archived(self):
        s = Stack(self)
        s.dependency(171, "seat-files", SEAT_FILES)
        merged_then_archiving(s, 171, "seat-files", SEAT_FILES)  # staged, not committed
        s.repo.write("openspec/specs/cap/spec.md", MERGED_SPEC)
        s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH), "seat-files (acme/widgets#171)")
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("check [stack]", out.stdout)

class FoundByBugHunterRun3Iteration3Tests(unittest.TestCase):
    """Regressions found by the third iteration of that run."""

    def test_a_reverted_merge_of_a_pull_request_that_archived_itself_says_to_merge_main(self):
        s = Stack(self)
        s.dependency(171, "seat-files", GOOD_DELTA)
        o = str(s.other)
        (s.other / "openspec/changes/archive").mkdir(parents=True, exist_ok=True)
        s.sh("git", "-C", o, "mv", "openspec/changes/seat-files", "openspec/changes/archive/2026-10-20-seat-files")
        s.push("seat-files", "archive")
        s.register(171, "seat-files")
        r = s.repo
        r.write("openspec/changes/archive/2026-10-20-seat-files/proposal.md", GOOD_PROPOSAL)
        r.write("openspec/changes/archive/2026-10-20-seat-files/specs/cap/spec.md", GOOD_DELTA)
        r.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n" + GOOD_DELTA.split("\n", 2)[2])
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "seat-files (#171)")
        merge = r.git("rev-parse", "HEAD")
        s.merge(171, merge)
        r.git("revert", "--no-edit", merge)
        s.stacked(GOOD_DELTA.replace("Records expire", "Lore expires").replace("record", "lore entry"),
                  "seat-files (acme/widgets#171)")
        out = s.check("lore-search")
        self.assertNotIn("already in the tree", out.stdout)
        # The revert left its addition out, and a merged dependency is never applied.
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn('does not hold its result ("Records expire" in cap)', out.stdout)

    def test_a_squash_merge_of_main_in_progress_counts_main_as_merged(self):
        s = Stack(self)
        s.dependency(171, "seat-files", SEAT_FILES)
        r = s.repo
        r.git("checkout", "-q", "-b", "lore")
        s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH), "seat-files (acme/widgets#171)")
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "lore")
        r.git("checkout", "-q", "main")
        merged_then_archiving(s, 171, "seat-files", SEAT_FILES)
        r.write("openspec/specs/cap/spec.md", MERGED_SPEC)
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "archive #171")
        r.git("checkout", "-q", "lore")
        r.git("merge", "--squash", "main", check=False)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_a_pull_request_that_archives_an_open_change_and_rewrites_a_file(self):
        s = Stack(self)
        o = str(s.other)
        s.dependency(171, "seat-files", SEAT_FILES)
        s.sh("git", "-C", o, "checkout", "-q", "main")
        s.sh("git", "-C", o, "merge", "-q", "--ff-only", "seat-files")
        s.sh("git", "-C", o, "push", "-q", "origin", "main")
        s.sh("git", "-C", o, "checkout", "-q", "-b", "impl")
        (s.other / "openspec/changes/archive").mkdir(parents=True, exist_ok=True)
        s.sh("git", "-C", o, "mv", "openspec/changes/seat-files", "openspec/changes/archive/2026-10-20-seat-files")
        s.put("openspec/changes/archive/2026-10-20-seat-files/tasks.md",
              "## 1. Build\n\n- [x] 1.1 Write the seat into each record\n- [x] 1.2 Read seat files\n- [x] 1.3 Migrate\n")
        s.put("openspec/specs/cap/spec.md", MERGED_SPEC)
        s.push("impl", "implement and archive")
        s.register(180, "impl")
        s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH), "seat-files (acme/widgets#180)")
        out = s.check("lore-search")
        self.assertNotIn("is not at openspec/changes/seat-files/", out.stdout)


class ContentCheckTests(unittest.TestCase):
    """Whether the tree holds a dependency is read from its content
    (Adam, 2026-10-24)."""

    def setUp(self):
        self.s = Stack(self)

    def test_a_partial_match_names_what_is_there_and_what_is_not(self):
        both = GOOD_DELTA + "\n### Requirement: Records are tagged\n\nThe store SHALL tag every record it keeps with the day it arrived.\n\n#### Scenario: t\n\n- **WHEN** w\n- **THEN** t\n"
        self.s.dependency(171, "seat-files", both)
        self.s.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n" + GOOD_DELTA.split("\n", 2)[2])
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "one of the two added by hand")
        self.s.stacked(modified("Records are kept", KEPT, SEARCH), "seat-files (acme/widgets#171)")
        out = self.s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("some of its deltas are already in the tree", out.stdout)
        self.assertIn('adds "Records expire"', out.stdout)
        self.assertIn('adds "Records are tagged"', out.stdout)

    def test_an_open_dependency_over_a_reworded_requirement_is_quiet(self):
        self.s.dependency(171, "seat-files", modified("Records are kept", KEPT, SEAT))
        later = MAIN_SPEC.replace(KEPT, KEPT + " " + AUDIT)  # changed since, by another change
        self.s.repo.write("openspec/specs/cap/spec.md", later)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "a later change")
        self.s.stacked(modified("Records are kept", KEPT, AUDIT, SEARCH), "seat-files (acme/widgets#171)")
        out = self.s.check("lore-search")
        # The dependency's pull request is open, so its text is used quietly
        # (DECISIONS.md, "A modified requirement is decided by its pull
        # request's state").
        self.assertNotIn("error [stack]", out.stdout)
        self.assertNotIn("check [drift]", out.stdout)
        self.assertNotIn("remove the `Builds on:", out.stdout)

    def test_a_rename_that_matches_neither_state_is_an_error(self):
        self.s.dependency(171, "seat-files", SEAT_FILES)
        both = MAIN_SPEC + "\n### Requirement: Records are retained\n\nThe store SHALL do another thing entirely, every day.\n\n#### Scenario: s\n\n- **WHEN** w\n- **THEN** t\n"
        self.s.repo.write("openspec/specs/cap/spec.md", both)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "both names")
        self.s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH), "seat-files (acme/widgets#171)")
        out = self.s.check("lore-search")
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn("target already exists", out.stdout)  # `openspec archive`'s words


ADDED_SEAT = ("## ADDED Requirements\n\n### Requirement: Seat shown\n\n" + SEAT +
              "\n\n#### Scenario: s\n\n- **WHEN** w\n- **THEN** t\n")
ADDED_AUDIT = ("## ADDED Requirements\n\n### Requirement: Audit trail\n\n" + AUDIT +
               "\n\n#### Scenario: s\n\n- **WHEN** w\n- **THEN** t\n")


class FoundByBugHunterRun4Tests(unittest.TestCase):
    """Regressions found by bug-hunter's run over the content rule."""

    def setUp(self):
        self.s = Stack(self)

    def test_a_dependency_built_on_one_already_merged_is_still_applied(self):
        s = self.s
        s.dependency(171, "seat-files", modified("Records are kept", KEPT, SEAT))
        s.dependency(172, "audit-log", modified("Records are kept", KEPT, SEAT, AUDIT), base="origin/seat-files",
                     proposal=stacked_proposal("seat-files (acme/widgets#171)"))
        s.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace(KEPT, KEPT + " " + SEAT))
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "#171 merged and archived")
        s.stacked(ADDED_AUDIT, "audit-log (acme/widgets#172)")
        out = s.check("lore-search")
        self.assertIn("duplicate", kinds(out))
        self.assertNotIn("already in the tree", out.stdout)

    def test_a_dependency_that_edits_its_archive_after_archiving(self):
        s, o = self.s, str(self.s.other)
        s.dependency(171, "seat-files", modified("Records are kept", KEPT, SEAT))
        (s.other / "openspec/changes/archive").mkdir(parents=True, exist_ok=True)
        s.sh("git", "-C", o, "mv", "openspec/changes/seat-files", "openspec/changes/archive/2026-10-01-seat-files")
        s.put("openspec/specs/cap/spec.md", MAIN_SPEC.replace(KEPT, KEPT + " " + SEAT))
        s.push("seat-files", "archive seat-files")
        s.put("openspec/changes/archive/2026-10-01-seat-files/tasks.md", TASKS + "- [x] 1.2 Done\n")
        s.push("seat-files", "tick a task in the archived change")
        s.register(171, "seat-files")
        s.stacked(ADDED_SEAT, "seat-files (acme/widgets#171)")
        out = s.check("lore-search")
        self.assertIn("duplicate", kinds(out))

    def test_a_rename_that_only_changes_capitalisation(self):
        self.s.dependency(171, "seat-files", renamed("Records are kept", "Records Are Kept")
                          + modified("Records Are Kept", KEPT, SEAT))
        self.s.stacked(GOOD_DELTA.replace("Records expire", "Lore"), "seat-files (acme/widgets#171)")
        out = self.s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_two_independent_dependencies_modifying_one_requirement_are_not_silent(self):
        s = self.s
        s.dependency(171, "seat-files", modified("Records are kept", KEPT, SEAT))
        s.dependency(172, "audit-log", modified("Records are kept", KEPT, AUDIT))
        s.stacked(ADDED_SEAT, "seat-files (acme/widgets#171)", "audit-log (acme/widgets#172)")
        out = s.check("lore-search")
        self.assertNotEqual(kinds(out), [])

    def test_an_unlisted_dependency_of_a_dependency_is_not_silently_left_out(self):
        s = self.s
        s.dependency(171, "seat-files", ADDED_SEAT.replace("Seat shown", "Seats are recorded"))
        s.dependency(172, "audit-log", modified("Records are kept", KEPT, AUDIT), base="origin/seat-files",
                     proposal=stacked_proposal("seat-files (acme/widgets#171)"))
        s.stacked(ADDED_SEAT, "audit-log (acme/widgets#172)")
        out = s.check("lore-search")
        self.assertNotEqual(out.returncode, 0, out.stdout)

    def test_a_dependency_stacked_by_its_line_alone_is_applied(self):
        # audit-log's branch is cut from main; it builds on seat-files only by its line
        s = self.s
        s.dependency(171, "seat-files", modified("Records are kept", KEPT, SEAT))
        s.dependency(172, "audit-log", modified("Records are kept", KEPT, SEAT, AUDIT),
                     proposal=stacked_proposal("seat-files (acme/widgets#171)"))
        s.stacked(ADDED_AUDIT, "seat-files (acme/widgets#171)", "audit-log (acme/widgets#172)")
        out = s.check("lore-search")
        self.assertIn("duplicate", kinds(out))
        self.assertNotIn(": check [drift]", out.stdout)

    def test_an_unlisted_dependency_of_a_dependency_that_cannot_be_read_is_an_error(self):
        s = self.s
        s.dependency(172, "audit-log", modified("Records are kept", KEPT, AUDIT),
                     proposal=stacked_proposal("seat-files (acme/widgets#171)"))  # no PR 171
        s.stacked(GOOD_DELTA.replace("Records expire", "Lore"), "audit-log (acme/widgets#172)")
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn("builds on seat-files (acme/widgets#171), which this change does not list", out.stdout)

    def test_an_open_dependency_over_a_reworded_requirement_is_not_a_stale_line(self):
        s = self.s
        s.dependency(171, "seat-files", modified("Records are kept", KEPT, SEAT))
        s.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace(KEPT, KEPT + " " + AUDIT))
        s.repo.git("commit", "-qam", "another change on main")
        s.stacked(GOOD_DELTA.replace("Records expire", "Lore"), "seat-files (acme/widgets#171)")
        out = s.check("lore-search")
        # The dependency's pull request is open, so its text is used quietly
        # (DECISIONS.md, "A modified requirement is decided by its pull
        # request's state").
        self.assertNotIn("error [stack]", out.stdout)
        self.assertNotIn("check [drift]", out.stdout)
        self.assertNotIn("remove the `Builds on:", out.stdout)

class FoundByBugHunterRun4Iteration2Tests(unittest.TestCase):
    """Regressions found by the second iteration of that run."""

    def setUp(self):
        self.s = Stack(self)

    def test_an_open_dependency_over_another_changes_text_is_quiet(self):
        s, r = self.s, self.s.repo
        r.change("x-change", delta=modified("Records are kept", KEPT, SEAT))
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "merge X open")
        r.git("push", "-q", "origin", "main")
        s.dependency(172, "audit-log", modified("Records are kept", KEPT, AUDIT))
        r.git("rm", "-rq", "openspec/changes/x-change")
        r.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace(KEPT, KEPT + " " + SEAT))
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "archive X")
        s.stacked(ADDED_SEAT, "audit-log (acme/widgets#172)")
        out = s.check("lore-search")
        # The dependency's pull request is open, so its text is used quietly
        # (DECISIONS.md, "A modified requirement is decided by its pull
        # request's state").
        self.assertNotIn("error [stack]", out.stdout)
        self.assertNotIn("check [drift]", out.stdout)
        self.assertNotIn("remove the `Builds on:", out.stdout)

    def test_a_dependency_built_on_a_rename_only_dependency_is_applied(self):
        s = self.s
        s.dependency(171, "seat-files", renamed("Records are kept", "Records are retained"))
        s.dependency(172, "audit-log", modified("Records are retained", KEPT, AUDIT), base="origin/seat-files",
                     proposal=stacked_proposal("seat-files (acme/widgets#171)"))
        s.stacked(ADDED_SEAT, "seat-files (acme/widgets#171)", "audit-log (acme/widgets#172)")
        out = s.check("lore-search")
        self.assertNotIn("check [drift]", out.stdout)
        self.assertIn("then audit-log", out.stdout)

    def test_the_tree_holding_the_merged_version_of_a_dependencys_dependency(self):
        s, o = self.s, str(self.s.other)
        s.dependency(171, "seat-files", ADDED_SEAT)
        s.dependency(172, "audit-log", ADDED_AUDIT, base="origin/seat-files",
                     proposal=stacked_proposal("seat-files (acme/widgets#171)"))
        s.sh("git", "-C", o, "checkout", "-q", "seat-files")
        v2 = ADDED_SEAT.replace("as the seat file recorded it at the time", "as recorded when written")
        s.put("openspec/changes/seat-files/specs/cap/spec.md", v2)
        s.push("seat-files", "review")
        s.register(171, "seat-files")
        s.merge(171)
        s.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n" + v2.split("\n", 2)[2])
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "#171 merged and archived")
        s.stacked(GOOD_DELTA.replace("Records expire", "Lore"), "audit-log (acme/widgets#172)")
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_a_dependencys_dependency_with_no_deltas_yet_at_the_branch_point(self):
        s, o = self.s, str(self.s.other)
        s.sh("git", "-C", o, "checkout", "-q", "-B", "seat-files", "origin/main")
        s.put("openspec/changes/seat-files/proposal.md", GOOD_PROPOSAL)
        s.push("seat-files", "proposal first")
        s.dependency(172, "audit-log", ADDED_AUDIT, base="origin/seat-files",
                     proposal=stacked_proposal("seat-files (acme/widgets#171)"))
        s.sh("git", "-C", o, "checkout", "-q", "seat-files")
        s.put("openspec/changes/seat-files/specs/cap/spec.md", ADDED_SEAT)
        s.push("seat-files", "specs")
        s.register(171, "seat-files")
        s.stacked(GOOD_DELTA.replace("Records expire", "Lore"), "audit-log (acme/widgets#172)")
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 1, out.stdout)


def spec_with(*sentences):
    return MAIN_SPEC.replace(KEPT, " ".join(sentences))


class FoundByBugHunterRun4Iteration3Tests(unittest.TestCase):
    """Regressions found by the third iteration of that run."""

    def setUp(self):
        self.s = Stack(self)

    def remote_main_commit(self, files, msg):
        s, o = self.s, str(self.s.other)
        s.sh("git", "-C", o, "fetch", "-q", "origin")
        s.sh("git", "-C", o, "checkout", "-q", "-B", "main", "origin/main")
        for k, v in files.items():
            s.put(k, v)
        s.sh("git", "-C", o, "add", "-A")
        s.sh("git", "-C", o, "commit", "-q", "-m", msg)
        s.sh("git", "-C", o, "push", "-q", "origin", "main")

    def test_an_open_dependency_built_on_an_archived_one_is_quiet(self):
        s = self.s
        s.dependency(171, "a-change", modified("Records are kept", KEPT, SEAT))
        s.merge(171)
        self.remote_main_commit({
            "openspec/changes/archive/2026-10-01-a-change/proposal.md": GOOD_PROPOSAL,
            "openspec/changes/archive/2026-10-01-a-change/specs/cap/spec.md": modified("Records are kept", KEPT, SEAT),
            "openspec/specs/cap/spec.md": spec_with(KEPT, SEAT)}, "A merged and archived")
        self.remote_main_commit({"openspec/specs/cap/spec.md": spec_with(KEPT, SEAT_REWORDED)}, "D rewords")
        s.dependency(172, "b-change", modified("Records are kept", KEPT, SEAT_REWORDED, AUDIT),
                     proposal=stacked_proposal("a-change (acme/widgets#171)"))
        s.repo.write("openspec/specs/cap/spec.md", spec_with(KEPT, SEAT))
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "A in tree")
        s.stacked(modified("Records are kept", KEPT, SEAT_REWORDED, AUDIT, SEARCH), "b-change (acme/widgets#172)")
        out = s.check("lore-search")
        # The dependency's pull request is open, so its text is used quietly
        # (DECISIONS.md, "A modified requirement is decided by its pull
        # request's state").
        self.assertNotIn("error [stack]", out.stdout)
        self.assertNotIn("check [drift]", out.stdout)
        self.assertNotIn("remove the `Builds on:", out.stdout)

    def test_a_merged_chain_listing_only_its_last_dependency(self):
        s = self.s
        s.dependency(171, "a-change", modified("Records are kept", KEPT, SEAT))
        s.dependency(172, "b-change", modified("Records are kept", KEPT, SEAT, AUDIT), base="origin/a-change",
                     proposal=stacked_proposal("a-change (acme/widgets#171)"))
        s.merge(171)
        s.merge(172)
        s.repo.write("openspec/specs/cap/spec.md", spec_with(KEPT, SEAT, AUDIT))
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "A and B merged and archived")
        s.stacked(modified("Records are kept", KEPT, SEAT, AUDIT, SEARCH), "b-change (acme/widgets#172)")
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_an_older_archive_of_the_name_is_not_an_unreadable_dependencys_dependency(self):
        s = self.s
        s.repo.write("openspec/changes/archive/2025-01-01-a-change/proposal.md", GOOD_PROPOSAL)
        s.repo.write("openspec/changes/archive/2025-01-01-a-change/specs/cap/spec.md", GOOD_DELTA)
        s.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n" + GOOD_DELTA.split("\n", 2)[2])
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "an older a-change archived")
        s.repo.git("push", "-q", "origin", "main")
        s.dependency(172, "b-change", modified("Records are kept", KEPT, SEAT, AUDIT),
                     proposal=stacked_proposal("a-change (acme/widgets#999)"))
        s.stacked(modified("Records are kept", KEPT, SEAT, AUDIT, SEARCH).replace("A record survives", "Lore"),
                  "b-change (acme/widgets#172)")
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 1, out.stdout)

    def test_a_dependency_stacked_by_its_line_on_a_merged_dependency(self):
        s = self.s
        s.dependency(171, "a-change", modified("Records are kept", KEPT, SEAT))
        s.merge(171)
        s.dependency(172, "b-change", modified("Records are kept", KEPT, SEAT, AUDIT),
                     proposal=stacked_proposal("a-change (acme/widgets#171)"))
        s.repo.write("openspec/specs/cap/spec.md", spec_with(KEPT, SEAT))
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "A in tree")
        s.stacked(modified("Records are kept", KEPT, SEAT, AUDIT, SEARCH), "b-change (acme/widgets#172)")
        out = s.check("lore-search")
        self.assertNotIn("check [drift]", out.stdout)


class PullRequestStateTests(unittest.TestCase):
    """A modified requirement is decided by its pull request's state
    (Adam, 2026-10-24)."""

    def setUp(self):
        self.s = Stack(self)
        self.s.dependency(171, "seat-files", modified("Records are kept", KEPT, SEAT))

    def test_an_open_pull_request_whose_text_differs_is_applied_quietly(self):
        self.s.stacked(ADDED_SEAT, "seat-files (acme/widgets#171)")
        out = self.s.check("lore-search")
        self.assertEqual(kinds(out), ["duplicate"])  # its text is in the checked state

    def test_a_merged_pull_request_whose_text_main_holds_passes(self):
        self.s.merge(171)
        self.s.repo.write("openspec/specs/cap/spec.md", spec_with(KEPT, SEAT))
        self.s.repo.git("commit", "-qam", "merged and archived")
        self.s.stacked(GOOD_DELTA, "seat-files (acme/widgets#171)")
        out = self.s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn(": error [", out.stdout)

    def test_a_merged_pull_request_whose_text_main_reworded_is_a_stale_line(self):
        self.s.merge(171)
        self.s.repo.write("openspec/specs/cap/spec.md", spec_with(KEPT, AUDIT))
        self.s.repo.git("commit", "-qam", "main reworded it")
        self.s.stacked(GOOD_DELTA, "seat-files (acme/widgets#171)")
        out = self.s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("remove the `Builds on: seat-files (acme/widgets#171)` line", out.stdout)

    def test_a_merged_pull_request_not_yet_archived_here_is_applied(self):
        self.s.merge(171)
        self.s.repo.change("seat-files", delta=modified("Records are kept", KEPT, SEAT))
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "merged, archive still to come")
        self.s.stacked(ADDED_SEAT, "seat-files (acme/widgets#171)")
        out = self.s.check("lore-search")
        self.assertNotIn("does not hold its result", out.stdout)
        self.assertIn("duplicate", kinds(out))

    def test_the_pull_request_state_is_read_with_gh(self):
        self.s.stacked(GOOD_DELTA, "seat-files (acme/widgets#171)")
        self.s.check("lore-search")
        views = [c for c in self.s.calls() if c[:2] == ["pr", "view"]]
        self.assertEqual(len(views), 1)
        self.assertIn("state", views[0][views[0].index("--json") + 1].split(","))


def removed_delta(name):
    return f"## REMOVED Requirements\n\n### Requirement: {name}\n\n**Reason**: gone.\n**Migration**: none.\n\n"


def spec_named(name, *sentences):
    return MAIN_SPEC.replace("Records are kept", name).replace(KEPT, " ".join(sentences))


class FoundByBugHunterRun5Tests(unittest.TestCase):
    """Regressions found by bug-hunter's run over the pull-request-state rule."""

    def setUp(self):
        self.s = Stack(self)

    def tree(self, text):
        self.s.repo.write("openspec/specs/cap/spec.md", text)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "merged and archived")

    def test_a_merged_rename_chain_listed_in_full_passes(self):
        s = self.s
        s.dependency(171, "a-change", renamed("Records are kept", "Records are retained"))
        s.dependency(172, "b-change", renamed("Records are retained", "Records are held"), base="origin/a-change",
                     proposal=stacked_proposal("a-change (acme/widgets#171)"))
        s.merge(171)
        s.merge(172)
        self.tree(spec_named("Records are held", KEPT))
        for deps in (["a-change (acme/widgets#171)", "b-change (acme/widgets#172)"], ["b-change (acme/widgets#172)"]):
            with self.subTest(deps=deps):
                s.stacked(modified("Records are held", KEPT, SEARCH), *deps)
                out = s.check("lore-search")
                self.assertEqual(out.returncode, 0, out.stdout)

    def test_a_modification_a_later_dependency_removes_is_skipped(self):
        s = self.s
        s.dependency(171, "a-change", modified("Records are kept", KEPT, SEAT))
        s.dependency(172, "b-change", removed_delta("Records are kept") + ADDED_AUDIT, base="origin/a-change",
                     proposal=stacked_proposal("a-change (acme/widgets#171)"))
        s.merge(171)
        s.merge(172)
        self.tree("# cap Specification\n\n## Purpose\n\nWhat cap does.\n\n## Requirements\n\n"
                  + ADDED_AUDIT.split("\n", 2)[2])
        s.stacked(ADDED_SEAT.replace("Seat shown", "Search works").replace(SEAT, SEARCH),
                  "a-change (acme/widgets#171)", "b-change (acme/widgets#172)")
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_a_merged_dependencys_dependency_reworded_on_main_does_not_advise_merging_main(self):
        s = self.s
        s.dependency(171, "a-change", modified("Records are kept", KEPT, SEAT))
        s.merge(171)
        self.tree(spec_named("Records are kept", KEPT, SEAT_REWORDED))
        s.repo.git("push", "-q", "origin", "main")
        s.dependency(172, "b-change", ADDED_AUDIT, proposal=stacked_proposal("a-change (acme/widgets#171)"))
        s.stacked(ADDED_SEAT.replace("Seat shown", "Search works").replace(SEAT, SEARCH), "b-change (acme/widgets#172)")
        out = s.check("lore-search")
        self.assertNotIn("merge main into your branch", out.stdout)

    def test_a_superseded_open_dependency_is_not_called_stale(self):
        s = self.s
        s.dependency(171, "a-change", modified("Records are kept", KEPT, SEAT))
        s.dependency(172, "b-change", modified("Records are kept", KEPT, SEAT, AUDIT), base="origin/a-change",
                     proposal=stacked_proposal("a-change (acme/widgets#171)"))
        s.stacked(modified("Records are kept", KEPT, SEAT, AUDIT, SEARCH),
                  "a-change (acme/widgets#171)", "b-change (acme/widgets#172)")
        out = s.check("lore-search")
        self.assertNotIn("already in the tree", out.stdout)


class FoundByBugHunterRun5Iteration2Tests(unittest.TestCase):
    """Regressions found by the second iteration of that run."""

    def setUp(self):
        self.s = Stack(self)

    def test_a_later_rename_does_not_drop_an_earlier_modification(self):
        s = self.s
        s.dependency(171, "a-change", modified("Records are kept", KEPT, SEAT))
        s.dependency(172, "b-change", renamed("Records are kept", "Records are retained"), base="origin/a-change",
                     proposal=stacked_proposal("a-change (acme/widgets#171)"))
        for deps, expect in ((["b-change (acme/widgets#172)"], "error [stack]"),
                             (["a-change (acme/widgets#171)", "b-change (acme/widgets#172)"], "error [duplicate]")):
            with self.subTest(deps=deps):
                s.stacked(ADDED_SEAT, *deps)
                out = s.check("lore-search")
                self.assertIn(expect, out.stdout)

    def test_a_merged_dependencys_dependency_is_judged_against_the_tree_not_the_stack(self):
        s = self.s
        s.dependency(171, "a-change", modified("Records are kept", KEPT, SEAT))
        s.merge(171)
        s.repo.write("openspec/specs/cap/spec.md", spec_named("Records are kept", KEPT, SEAT))
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "archive A")
        s.dependency(173, "l-change", modified("Records are kept", KEPT, SEAT, AUDIT))
        s.dependency(172, "b-change", ADDED_SEAT.replace("Seat shown", "Search works").replace(SEAT, SEARCH),
                     proposal=stacked_proposal("a-change (acme/widgets#171)"))
        s.stacked(GOOD_DELTA, "l-change (acme/widgets#173)", "b-change (acme/widgets#172)")
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)


SEARCH_REQ = ADDED_SEAT.replace("Seat shown", "Search works").replace(SEAT, SEARCH)


class RenamedSupersessionTests(unittest.TestCase):
    """A later dependency that renames a requirement and sets it again under
    the new name replaces an earlier one's version of it. When both
    dependencies have merged, the tree holds both results and the check
    passes. When the later one is still open, a check says the earlier
    version is left out (found by bug-hunter, 2026-10-24)."""

    A, B = "a-change (acme/widgets#171)", "b-change (acme/widgets#172)"

    def setUp(self):
        self.s = Stack(self)

    def tree(self, text):
        self.s.repo.write("openspec/specs/cap/spec.md", text)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "merged and archived")

    def test_an_addition_a_later_dependency_only_renames_both_merged(self):
        s = self.s
        s.dependency(171, "a-change", ADDED_AUDIT)
        s.dependency(172, "b-change", renamed("Audit trail", "Audit kept"), base="origin/a-change",
                     proposal=stacked_proposal(self.A))
        s.merge(171)
        s.merge(172)
        self.tree(MAIN_SPEC + "\n" + ADDED_AUDIT.split("\n", 2)[2].replace("Audit trail", "Audit kept"))
        s.stacked(SEARCH_REQ, self.A, self.B)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_a_dependency_renamed_and_reworded_by_the_next_both_merged(self):
        s = self.s
        s.dependency(171, "a-change", modified("Records are kept", KEPT, SEAT))
        s.dependency(172, "b-change", renamed("Records are kept", "Records are retained")
                     + modified("Records are retained", KEPT, SEAT, AUDIT),
                     base="origin/a-change", proposal=stacked_proposal(self.A))
        s.merge(171)
        s.merge(172)
        self.tree(spec_named("Records are retained", KEPT, SEAT, AUDIT))
        for deps in ([self.A, self.B], [self.B]):
            with self.subTest(deps=deps):
                s.stacked(SEARCH_REQ, *deps)
                out = s.check("lore-search")
                self.assertEqual(out.returncode, 0, out.stdout)

    def test_an_addition_renamed_and_reworded_by_the_next_both_merged(self):
        s = self.s
        kept = modified("Audit kept", AUDIT, SEAT)
        s.dependency(171, "a-change", ADDED_AUDIT)
        s.dependency(172, "b-change", renamed("Audit trail", "Audit kept") + kept,
                     base="origin/a-change", proposal=stacked_proposal(self.A))
        s.merge(171)
        s.merge(172)
        self.tree(MAIN_SPEC + "\n" + kept.split("\n", 2)[2])
        for deps in ([self.A, self.B], [self.B]):
            with self.subTest(deps=deps):
                s.stacked(SEARCH_REQ, *deps)
                out = s.check("lore-search")
                self.assertEqual(out.returncode, 0, out.stdout)

    def independent(self):
        s = self.s
        s.dependency(171, "a-change", modified("Records are kept", KEPT, SEAT))
        s.dependency(172, "b-change", renamed("Records are kept", "Records are retained")
                     + modified("Records are retained", KEPT, AUDIT))

    def test_an_independent_rename_and_rewording_says_the_earlier_version_is_left_out(self):
        self.independent()
        self.s.stacked(SEARCH_REQ, self.A, self.B)
        out = self.s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("left out", out.stdout)

    def test_an_independent_rename_and_rewording_once_both_merged(self):
        self.independent()
        self.s.merge(171)
        self.s.merge(172)
        self.tree(spec_named("Records are retained", KEPT, AUDIT))
        self.s.stacked(SEARCH_REQ, self.A, self.B)
        out = self.s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_an_independent_rename_and_rewording_merged_while_the_earlier_is_open(self):
        # Merged b-change renamed the requirement that open a-change modifies,
        # so a-change does not apply to main: `openspec archive` refuses it.
        self.independent()
        self.s.merge(172)
        self.tree(spec_named("Records are retained", KEPT, AUDIT))
        self.s.stacked(SEARCH_REQ, self.A, self.B)
        out = self.s.check("lore-search")
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn("error [stack] a-change (acme/widgets#171): its deltas do not fit the tree", out.stdout)
        self.assertIn('"### Requirement: Records are kept" - not found', out.stdout)

    def test_a_change_modifying_what_seat_files_renames_and_rewords(self):
        # The shape of igor #216 stacked on #171: seat-files renames "Records
        # are kept" and rewords it, and another change listed before it
        # modifies the requirement under its old name.
        s = self.s
        s.dependency(170, "other-change", modified("Records are kept", KEPT, AUDIT))
        s.dependency(171, "seat-files", SEAT_FILES)
        s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH),
                  "other-change (acme/widgets#170)", "seat-files (acme/widgets#171)")
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("left out", out.stdout)


class LaterOrderTests(unittest.TestCase):
    """Whether a later dependency sets a requirement again depends on the
    order of the later dependencies' renames and removals (found by
    bug-hunter, 2026-10-24)."""

    A, B, C = "a-change (acme/widgets#171)", "b-change (acme/widgets#172)", "c-change (acme/widgets#173)"

    def setUp(self):
        self.s = Stack(self)

    def test_a_removal_before_a_rename_onto_its_name_does_not_supersede(self):
        s = self.s
        old_w = "Old records SHALL be moved to cold storage after ninety days without a read."
        s.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n### Requirement: Records are retained\n\n"
                     + old_w + "\n\n#### Scenario: cold\n\n- **WHEN** w\n- **THEN** t\n")
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "main with W")
        s.dependency(171, "a-change", modified("Records are kept", KEPT, SEAT))
        s.dependency(172, "b-change", removed_delta("Records are retained"), base="origin/a-change",
                     proposal=stacked_proposal(self.A))
        s.dependency(173, "c-change", renamed("Records are kept", "Records are retained"),
                     base="origin/b-change", proposal=stacked_proposal(self.A, self.B))
        s.stacked(ADDED_SEAT, self.A, self.B, self.C)
        out = s.check("lore-search")
        self.assertIn("error [duplicate]", out.stdout)

    def test_a_case_only_rename_then_a_real_rename_still_supersedes(self):
        s = self.s
        s.dependency(171, "a-change", modified("Records are kept", KEPT, SEAT))
        s.dependency(172, "b-change", renamed("Records are kept", "RECORDS ARE KEPT"))
        s.dependency(173, "c-change", renamed("RECORDS ARE KEPT", "Records are retained")
                     + modified("Records are retained", KEPT, AUDIT), base="origin/b-change",
                     proposal=stacked_proposal(self.B))
        s.stacked(SEARCH_REQ, self.A, self.B, self.C)
        out = s.check("lore-search")
        self.assertIn("left out", out.stdout)

    def test_a_rename_onto_a_name_an_earlier_dependency_adds_is_not_silent(self):
        s = self.s
        s.dependency(171, "a-change", ADDED_AUDIT.replace("Audit trail", "Records are retained"))
        s.dependency(172, "b-change", renamed("Records are kept", "Records are retained")
                     + modified("Records are retained", KEPT, SEAT), base="origin/a-change",
                     proposal=stacked_proposal(self.A))
        s.stacked(SEARCH_REQ, self.A, self.B)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 1, out.stdout)


def chain_renames(*names):
    pairs = "".join(f"- FROM: `### Requirement: {a}`\n- TO: `### Requirement: {b}`\n\n"
                    for a, b in zip(names, names[1:]))
    return "## RENAMED Requirements\n\n" + pairs


def req_block(name, text):
    return f"\n### Requirement: {name}\n\n{text}\n\n#### Scenario: s\n\n- **WHEN** w\n- **THEN** t\n"


class RenameChainTests(unittest.TestCase):
    """Renames within one delta apply one after another, as `openspec
    archive` applies them; a removal is undone by a later dependency that
    puts the name back (found by bug-hunter, 2026-10-24)."""

    A, B = "a-change (acme/widgets#171)", "b-change (acme/widgets#172)"
    X, Y, Z = "Records are kept", "Records are retained", "Records are stored"

    def setUp(self):
        self.s = Stack(self)

    def tree(self, text):
        self.s.repo.write("openspec/specs/cap/spec.md", text)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "tree")

    def test_a_chained_rename_in_one_later_dependency_still_says_left_out(self):
        s = self.s
        s.dependency(171, "a-change", modified(self.X, KEPT, SEAT))
        s.dependency(172, "b-change", chain_renames(self.X, self.Y, self.Z) + modified(self.Z, KEPT, AUDIT))
        s.stacked(SEARCH_REQ, self.A, self.B)
        out = s.check("lore-search")
        self.assertIn("left out", out.stdout)

    def test_a_chained_rename_once_both_merged(self):
        s = self.s
        s.dependency(171, "a-change", modified(self.X, KEPT, SEAT))
        s.dependency(172, "b-change", chain_renames(self.X, self.Y, self.Z), base="origin/a-change",
                     proposal=stacked_proposal(self.A))
        s.merge(171)
        s.merge(172)
        self.tree(spec_named(self.Z, KEPT, SEAT))
        for deps in ([self.A, self.B], [self.B]):
            with self.subTest(deps=deps):
                s.stacked(SEARCH_REQ, *deps)
                out = s.check("lore-search")
                self.assertEqual(out.returncode, 0, out.stdout)

    def test_a_removed_name_a_later_dependency_renames_another_onto(self):
        s = self.s
        cold = "Old records SHALL be moved to cold storage after ninety days without a read."
        self.tree(MAIN_SPEC + req_block("Cold storage", cold))
        s.repo.git("push", "-q", "origin", "main")
        s.dependency(171, "a-change", removed_delta(self.X))
        s.dependency(172, "b-change", renamed("Cold storage", self.X), base="origin/a-change",
                     proposal=stacked_proposal(self.A))
        s.merge(171)
        s.merge(172)
        self.tree(MAIN_SPEC.split("### Requirement:")[0] + req_block(self.X, cold).lstrip("\n"))
        for deps in ([self.A, self.B], [self.B]):
            with self.subTest(deps=deps):
                s.stacked(SEARCH_REQ, *deps)
                out = s.check("lore-search")
                self.assertEqual(out.returncode, 0, out.stdout)

    def test_a_removed_name_a_later_dependency_adds_again(self):
        s = self.s
        cold = "Old records SHALL be moved to cold storage after ninety days without a read."
        s.dependency(171, "a-change", removed_delta(self.X))
        s.dependency(172, "b-change", "## ADDED Requirements\n" + req_block(self.X, cold), base="origin/a-change",
                     proposal=stacked_proposal(self.A))
        s.merge(171)
        s.merge(172)
        self.tree(MAIN_SPEC.split("### Requirement:")[0] + req_block(self.X, cold).lstrip("\n"))
        for deps in ([self.A, self.B], [self.B]):
            with self.subTest(deps=deps):
                s.stacked(SEARCH_REQ, *deps)
                out = s.check("lore-search")
                self.assertEqual(out.returncode, 0, out.stdout)
                self.assertIn("remove the `Builds on:", out.stdout)



class RealArchiveTests(unittest.TestCase):
    """Sequences of removals, renames and re-adds across dependencies that
    the base must come out right for. The base is built with `openspec
    archive` itself. Found by bug-hunter's third iteration (2026-10-24)."""

    A, B = "a-change (acme/widgets#171)", "b-change (acme/widgets#172)"
    X, Y, Z, Q = "Records are kept", "Records are retained", "Records are stored", "Records are archived"
    COLD = "Old records SHALL be moved to cold storage after ninety days without a read."
    COLD_SIXTY = "Old records SHALL be moved to cold storage after sixty days without a read."

    def setUp(self):
        self.s = Stack(self)

    def tree(self, text):
        self.s.repo.write("openspec/specs/cap/spec.md", text)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "tree")

    def restating(self, text):
        return SEARCH_REQ.replace("Search works", "Cold again").replace(SEARCH, text)

    def test_a_rename_onto_a_name_the_earlier_dependency_removed(self):
        # A removes X and adds W ("Cold storage"); B, on A, renames W onto X. All open.
        s = self.s
        s.dependency(171, "a-change", removed_delta(self.X) + "## ADDED Requirements\n"
                     + req_block("Cold storage", self.COLD))
        s.dependency(172, "b-change", renamed("Cold storage", self.X), base="origin/a-change",
                     proposal=stacked_proposal(self.A))
        s.stacked(SEARCH_REQ, self.A, self.B)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertEqual(kinds(out), [], out.stdout)  # no drift, no stale line for open b-change
        # X now holds W's text, and main's text of X is gone.
        s.stacked(self.restating(self.COLD), self.A, self.B)
        out = s.check("lore-search")
        self.assertIn("error [duplicate]", out.stdout)
        self.assertIn('also stated in "Records are kept"', out.stdout)
        s.stacked(self.restating(KEPT), self.A, self.B)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertNotIn("[duplicate]", out.stdout)

    def test_a_chain_in_one_delta_then_a_later_rename_both_merged(self):
        s = self.s
        s.dependency(171, "a-change", chain_renames(self.X, self.Y, self.Z))
        s.dependency(172, "b-change", renamed(self.Z, self.Q), base="origin/a-change",
                     proposal=stacked_proposal(self.A))
        s.merge(171)
        s.merge(172)
        self.tree(spec_named(self.Q, KEPT))
        for deps in ([self.A, self.B], [self.B]):
            with self.subTest(deps=deps):
                s.stacked(SEARCH_REQ, *deps)
                out = s.check("lore-search")
                self.assertEqual(out.returncode, 0, out.stdout)
                self.assertIn("remove the `Builds on: b-change (acme/widgets#172)` line", out.stdout)

    def test_a_merged_shift_rename_in_one_delta(self):
        # Y -> Z, then X -> Y, in one delta.
        s = self.s
        self.tree(MAIN_SPEC + req_block(self.Y, self.COLD))
        s.repo.git("push", "-q", "origin", "main")
        s.dependency(171, "a-change", "## RENAMED Requirements\n\n"
                     f"- FROM: `### Requirement: {self.Y}`\n- TO: `### Requirement: {self.Z}`\n\n"
                     f"- FROM: `### Requirement: {self.X}`\n- TO: `### Requirement: {self.Y}`\n")
        s.merge(171)
        self.tree(MAIN_SPEC.replace(self.X, self.Y) + req_block(self.Z, self.COLD))
        s.stacked(SEARCH_REQ, self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertNotIn("both names", out.stdout)
        self.assertIn("remove the `Builds on: a-change (acme/widgets#171)` line", out.stdout)

    def test_a_removal_undone_by_a_re_add_then_reworded_on_main(self):
        # A removes X, B re-adds it; both merged; main has since reworded X.
        s = self.s
        s.dependency(171, "a-change", removed_delta(self.X))
        s.dependency(172, "b-change", "## ADDED Requirements\n" + req_block(self.X, self.COLD),
                     base="origin/a-change", proposal=stacked_proposal(self.A))
        s.merge(171)
        s.merge(172)
        self.tree(MAIN_SPEC.split("### Requirement:")[0] + req_block(self.X, self.COLD_SIXTY).lstrip("\n"))
        for deps in ([self.A, self.B], [self.B]):
            with self.subTest(deps=deps, restates="main's text"):
                s.stacked(self.restating(self.COLD_SIXTY), *deps)
                out = s.check("lore-search")
                self.assertIn("error [duplicate]", out.stdout)  # the tree's text is the base
            with self.subTest(deps=deps, restates="b-change's text"):
                s.stacked(self.restating(self.COLD), *deps)
                out = s.check("lore-search")
                self.assertEqual(out.returncode, 0, out.stdout)
                self.assertIn("remove the `Builds on: b-change (acme/widgets#172)` line", out.stdout)


class MergedNotReplayedTests(unittest.TestCase):
    """A merged dependency is judged by the requirement names the tree
    holds; its delta is never archived onto the base. Each open dependency
    is archived once, with the real `openspec` CLI. Renames apply in order.
    A requirement block's header is read whatever its case (Adam,
    2026-10-24). Found by bug-hunter."""

    A, B, C = "a-change (acme/widgets#171)", "b-change (acme/widgets#172)", "c-change (acme/widgets#173)"
    X, Y, Z, T = "Records are kept", "Records are retained", "Records are stored", "Records are swapping"
    COLD = "Old records SHALL be moved to cold storage after ninety days without a read."
    CHECKSUM = "Every record SHALL be checksummed when written."

    def setUp(self):
        self.s = Stack(self)

    def tree(self, text):
        self.s.repo.write("openspec/specs/cap/spec.md", text)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "tree")

    def shim(self):
        """A PATH whose openspec logs each run to the returned log file,
        then runs the real CLI."""
        bindir = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-shim-"))
        self.addCleanup(shutil.rmtree, bindir, ignore_errors=True)
        log = bindir / "log"
        shim = bindir / "openspec"
        shim.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexec "{shutil.which("openspec")}" "$@"\n')
        shim.chmod(0o755)
        return dict(self.s.env(), PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}"), log

    def runs(self, log):
        return [l.split()[1] for l in log.read_text().splitlines()
                if l.startswith("archive ")] if log.exists() else []

    def test_a_swap_through_a_temporary_name_is_applied(self):
        # X -> T, Y -> X, T -> Y in one open delta swaps X and Y.
        s = self.s
        self.tree(MAIN_SPEC + req_block(self.Y, self.COLD))
        s.repo.git("push", "-q", "origin", "main")
        s.dependency(171, "a-change", "## RENAMED Requirements\n\n"
                     f"- FROM: `### Requirement: {self.X}`\n- TO: `### Requirement: {self.T}`\n\n"
                     f"- FROM: `### Requirement: {self.Y}`\n- TO: `### Requirement: {self.X}`\n\n"
                     f"- FROM: `### Requirement: {self.T}`\n- TO: `### Requirement: {self.Y}`\n")
        s.stacked(SEARCH_REQ.replace("Search works", "Cold again").replace(SEARCH, self.COLD), self.A)
        out = s.check("lore-search")
        self.assertIn('also stated in "Records are kept"', out.stdout)  # the swap applied
        self.assertNotIn("already in the tree", out.stdout)

    def test_lowercase_requirement_headers_are_read(self):
        # OpenSpec reads `### requirement:` as a requirement header.
        s = self.s
        s.dependency(171, "a-change", ADDED_AUDIT.replace("### Requirement:", "### requirement:"))
        s.stacked(SEARCH_REQ.replace(SEARCH, AUDIT), self.A)
        out = s.check("lore-search")
        self.assertIn("error [duplicate]", out.stdout)
        self.assertIn("in acme/widgets#171", out.stdout)

    def test_a_lowercase_modified_header_is_applied(self):
        s = self.s
        s.dependency(171, "a-change", modified(self.X, KEPT, SEAT).replace("### Requirement:", "### requirement:"))
        s.stacked(ADDED_SEAT, self.A)
        out = s.check("lore-search")
        self.assertIn("error [duplicate]", out.stdout)  # a-change's text is in the base
        self.assertIn("lore-search builds on a-change", out.stdout)

    def test_a_merged_modification_then_removal_listed_in_any_subset(self):
        # A modifies X; B, on A, removes X; both merged.
        s = self.s
        s.dependency(171, "a-change", modified(self.X, KEPT, SEAT))
        s.dependency(172, "b-change", removed_delta(self.X), base="origin/a-change",
                     proposal=stacked_proposal(self.A))
        s.merge(171)
        s.merge(172)
        self.tree(MAIN_SPEC.split("### Requirement:")[0])
        for deps in ([self.A, self.B], [self.B]):
            with self.subTest(deps=deps):
                s.stacked(SEARCH_REQ, *deps)
                out = s.check("lore-search")
                self.assertEqual(out.returncode, 0, out.stdout)
                for d in deps:
                    self.assertIn(f"remove the `Builds on: {d}` line", out.stdout)

    def test_a_merged_chain_of_three_ending_in_a_removal(self):
        # A and B modify X; C, on both, removes it; all merged.
        s = self.s
        s.dependency(171, "a-change", modified(self.X, KEPT, SEAT))
        s.dependency(172, "b-change", modified(self.X, KEPT, self.CHECKSUM), base="origin/a-change",
                     proposal=stacked_proposal(self.A))
        s.dependency(173, "c-change", removed_delta(self.X), base="origin/b-change",
                     proposal=stacked_proposal(self.A, self.B))
        for n in (171, 172, 173):
            s.merge(n)
        self.tree(MAIN_SPEC.split("### Requirement:")[0])
        s.stacked(SEARCH_REQ, self.A, self.B, self.C)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_a_merged_chain_of_three_ending_in_a_rename(self):
        # A and B modify X; C, on both, renames it to Y; all merged.
        s = self.s
        s.dependency(171, "a-change", modified(self.X, KEPT, SEAT))
        s.dependency(172, "b-change", modified(self.X, KEPT, self.CHECKSUM), base="origin/a-change",
                     proposal=stacked_proposal(self.A))
        s.dependency(173, "c-change", renamed(self.X, self.Y), base="origin/b-change",
                     proposal=stacked_proposal(self.A, self.B))
        for n in (171, 172, 173):
            s.merge(n)
        self.tree(spec_named(self.Y, KEPT, self.CHECKSUM))
        for deps in ([self.C], [self.B, self.C]):
            with self.subTest(deps=deps):
                s.stacked(SEARCH_REQ, *deps)
                out = s.check("lore-search")
                self.assertEqual(out.returncode, 0, out.stdout)

    def test_an_identical_addition_by_two_dependencies_once_the_later_merges(self):
        # A and B both add "Audit trail" with the same text; only B has
        # merged, so the tree holds it once and A's copy is not a duplicate.
        s = self.s
        s.dependency(171, "a-change", ADDED_AUDIT)
        s.dependency(172, "b-change", ADDED_AUDIT + "\n" + SEARCH_REQ.replace("## ADDED Requirements\n", ""))
        s.merge(172)
        self.tree(MAIN_SPEC + req_block("Audit trail", AUDIT) + req_block("Search works", SEARCH))
        s.stacked(ADDED_SEAT, self.A, self.B)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertNotIn("error [", out.stdout)

    def test_archive_runs_once_per_open_dependency_and_the_stacked_change_never_for_a_merged_one(self):
        # A and B have merged and C is open: only C and the stacked change
        # are archived, each once.
        s = self.s
        s.dependency(171, "a-change", modified(self.X, KEPT, SEAT))
        s.dependency(172, "b-change", modified(self.X, KEPT, SEAT, AUDIT), base="origin/a-change",
                     proposal=stacked_proposal(self.A))
        s.dependency(173, "c-change", modified(self.X, KEPT, SEAT, AUDIT, self.CHECKSUM), base="origin/b-change",
                     proposal=stacked_proposal(self.A, self.B))
        s.merge(171)
        s.merge(172)
        self.tree(spec_with(KEPT, SEAT, AUDIT))
        s.stacked(SEARCH_REQ, self.A, self.B, self.C)
        env, log = self.shim()
        out = s.repo.check("lore-search", env=env)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(self.runs(log), ["c-change", "lore-search"])  # then the stacked change itself

    def test_each_merged_dependency_that_shows_gets_the_stale_line_check(self):
        # B, which builds on A, rewords A's version of X.
        s = self.s
        s.dependency(171, "a-change", modified(self.X, KEPT, SEAT))
        s.dependency(172, "b-change", modified(self.X, KEPT, SEAT, AUDIT), base="origin/a-change",
                     proposal=stacked_proposal(self.A))
        s.merge(171)
        s.merge(172)
        self.tree(spec_with(KEPT, SEAT, AUDIT))
        s.stacked(SEARCH_REQ, self.A, self.B)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)
        for d in (self.A, self.B):
            self.assertIn(f"remove the `Builds on: {d}` line", out.stdout)

    def test_a_merged_dependency_whose_result_the_branch_lacks_says_to_merge_main(self):
        s = self.s
        s.dependency(171, "a-change", renamed(self.X, self.Y) + "## ADDED Requirements\n" + req_block(self.Z, self.COLD))
        s.merge(171)
        s.stacked(SEARCH_REQ, self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn("has merged, but this branch does not hold its result", out.stdout)
        self.assertIn("Merge main into your branch", out.stdout)
        self.assertIn(f'"{self.Z}"', out.stdout)

    def test_sentence_drift_survives_a_later_rename(self):
        # A rewords X; B, on A, renames X to Y.
        s = self.s
        s.dependency(171, "a-change", modified(self.X, KEPT, SEAT))
        s.put("openspec/changes/a-change/specs/cap/spec.md", modified(self.X, KEPT, SEAT_REWORDED))
        s.push("a-change", "reword")
        s.register(171, "a-change")
        s.dependency(172, "b-change", renamed(self.X, self.Y), base="origin/a-change",
                     proposal=stacked_proposal(self.A))
        s.stacked(modified(self.Y, KEPT, SEAT, SEARCH), self.A, self.B)
        out = s.check("lore-search")
        self.assertIn("check [drift]", out.stdout)
        self.assertIn(SEAT_REWORDED, out.stdout)


class OpenSpecGrammarTests(unittest.TestCase):
    """A dependency's delta is read as `openspec show` reads it. Each delta
    here passes `openspec validate --strict`. Regressions found by a
    bug-hunter run."""

    A = "a-change (acme/widgets#171)"
    X, CS = "Records are kept", "Records in C#"
    AUDIT_REQ = ("\n### Requirement: Audit trail\n\n" + AUDIT +
                 "\n\n#### Scenario: s\n\n- **WHEN** w\n- **THEN** t\n")
    # MODIFY_AUDIT keeps the requirement's scenario: `openspec archive` refuses
    # a MODIFIED block that drops one (StackedChangeArchiveTests).
    MODIFY_AUDIT = "## MODIFIED Requirements\n" + req_block("Audit trail", AUDIT + " The log SHALL be kept for a year.")

    def setUp(self):
        self.s = Stack(self)

    def tree(self, text):
        self.s.repo.write("openspec/specs/cap/spec.md", text)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "tree")
        self.s.repo.git("push", "-q", "origin", "main")

    # (1) OpenSpec keeps a trailing "#" in a requirement name.

    def test_a_merged_rename_onto_a_name_ending_in_a_hash_shows(self):
        s = self.s
        s.dependency(171, "a-change", renamed(self.X, self.CS))
        s.merge(171)
        self.tree(spec_named(self.CS, KEPT))
        s.stacked(SEARCH_REQ, self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn(f"remove the `Builds on: {self.A}` line", out.stdout)

    def test_an_open_rename_onto_a_name_ending_in_a_hash_already_done_is_dropped(self):
        s = self.s
        self.tree(spec_named(self.CS, KEPT))
        s.dependency(171, "a-change", renamed(self.X, self.CS) + ADDED_AUDIT)
        s.stacked(SEARCH_REQ, self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("already in the tree and were skipped", out.stdout)

    def test_the_stacked_change_renames_a_name_ending_in_a_hash(self):
        s = self.s
        self.tree(spec_named(self.CS, KEPT))
        s.dependency(171, "a-change", ADDED_AUDIT)
        s.stacked(renamed(self.CS, "Records stay"), self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)

    # (2) OpenSpec reads a REMOVED entry written as a bullet.

    BULLET = "\n## REMOVED Requirements\n\n- `### Requirement: Audit trail`\n"

    def test_a_bullet_removal_is_applied(self):
        s = self.s
        self.tree(MAIN_SPEC + self.AUDIT_REQ)
        s.dependency(171, "a-change", SEARCH_REQ + self.BULLET)
        s.stacked(self.MODIFY_AUDIT, self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn('modifies "Audit trail" in cap, which a-change (acme/widgets#171) removes', out.stdout)

    def test_a_delta_of_only_a_bullet_removal_is_readable(self):
        s = self.s
        self.tree(MAIN_SPEC + self.AUDIT_REQ)
        s.dependency(171, "a-change", self.BULLET.lstrip("\n"))
        s.stacked(ADDED_SEAT.replace("Seat shown", "Audit moved").replace(SEAT, AUDIT), self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertNotIn("holds no requirement header", out.stdout)

    def test_a_merged_bullet_removal_the_branch_lacks_says_to_merge_main(self):
        s = self.s
        self.tree(MAIN_SPEC + self.AUDIT_REQ)
        s.dependency(171, "a-change", "## MODIFIED Requirements\n" +
                     req_block(self.X, KEPT).replace("#### Scenario: s\n\n- **WHEN** w\n- **THEN** t\n",
                                                     "#### Scenario: A record survives\n\n- **WHEN** a record is written\n"
                                                     "- **THEN** it can be read for thirty days\n") + self.BULLET)
        s.merge(171)
        s.stacked(SEARCH_REQ, self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn("Merge main into your branch", out.stdout)
        self.assertIn('its removal of "Audit trail" from cap', out.stdout)

    # (3) OpenSpec reads `###Requirement:` with no space as a header.

    def test_a_removal_without_a_space_after_the_hashes_is_applied(self):
        s = self.s
        self.tree(MAIN_SPEC + self.AUDIT_REQ)
        s.dependency(171, "a-change", SEARCH_REQ + "\n## REMOVED Requirements\n\n###Requirement: Audit trail\n")
        s.stacked(self.MODIFY_AUDIT, self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn('modifies "Audit trail" in cap, which a-change (acme/widgets#171) removes', out.stdout)

    # (4) What OpenSpec does not read is not applied.

    def test_lowercase_from_and_to_lines_are_not_a_rename(self):
        s = self.s
        self.tree(MAIN_SPEC + self.AUDIT_REQ)
        s.dependency(171, "a-change", SEARCH_REQ + "\n## RENAMED Requirements\n\n"
                     "- FROM: `### requirement: Audit trail`\n- TO: `### requirement: Audit log`\n")
        s.stacked(self.MODIFY_AUDIT, self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_a_section_title_with_more_words_is_ignored(self):
        s = self.s
        self.tree(MAIN_SPEC + self.AUDIT_REQ)
        s.dependency(171, "a-change", SEARCH_REQ +
                     "\n## REMOVED Requirements (cleanup)\n\n### Requirement: Audit trail\n")
        s.stacked(self.MODIFY_AUDIT, self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_both_sections_with_one_title_are_applied(self):
        s = self.s
        s.dependency(171, "a-change", SEARCH_REQ + "\n" + ADDED_AUDIT)
        s.stacked(modified("Search works", SEARCH, "The search SHALL time out after a second.")
                  .replace("A record survives", "s"), self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)


class ExactComparisonTests(unittest.TestCase):
    """A requirement is compared by its text and scenarios as `openspec
    show` reads them, with their case, by its fenced code, and by its name
    exactly (found by bug-hunter,
    2026-10-24)."""

    A = "a-change (acme/widgets#171)"
    STALE = "every delta it holds is already in the tree"

    def setUp(self):
        self.s = Stack(self)

    def tree(self, text):
        self.s.repo.write("openspec/specs/cap/spec.md", text)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "tree")
        self.s.repo.git("push", "-q", "origin", "main")

    # (1) A dependency's modification is present only when its text, with
    # its case, is.

    def test_a_modification_only_in_case_is_applied(self):
        s = self.s
        self.tree(MAIN_SPEC.replace(KEPT, KEPT + " Each read must reset the clock."))
        s.dependency(171, "a-change", modified("Records are kept", KEPT, "Each read MUST reset the clock."))
        s.stacked(ADDED_AUDIT, self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertNotIn(self.STALE, out.stdout)

    # (2) The stacked change's names match the base exactly, as `openspec
    # archive` matches them: "records are kept" is not "Records are kept".

    def test_a_name_differing_only_in_case_is_a_drift_error(self):
        cases = {"modifies": modified("records are kept", KEPT, "Records SHALL be kept on two disks."),
                 "removes": removed_delta("records are kept") + ADDED_AUDIT,
                 "renames": renamed("records are kept", "Records are retained")}
        for verb, delta in cases.items():
            with self.subTest(verb=verb):
                s = self.s
                s.dependency(171, "a-change", SEARCH_REQ)
                s.stacked(delta, self.A)
                out = s.check("lore-search")
                self.assertEqual(out.returncode, 1, out.stdout)
                self.assertIn(f'error [drift] {verb} "records are kept" in cap', out.stdout)

    def test_a_removal_in_another_case_does_not_excuse_a_duplicate(self):
        s = self.s
        s.repo.change("plain", delta=removed_delta("records are kept") + "## ADDED Requirements\n\n"
                      "### Requirement: Records are held\n\n" + KEPT +
                      "\n\n#### Scenario: s\n\n- **WHEN** w\n- **THEN** t\n")
        out = s.check("plain")
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn("[duplicate]", out.stdout)


class StackedChangeArchiveTests(unittest.TestCase):
    """The stacked change itself is archived by `openspec archive`, after its
    open dependencies, into a copy of the scratch specs (DECISIONS.md,
    "The stacked change itself is archived too"). Each refusal is a drift error naming its delta file
    and requirement and quoting the CLI."""

    A = "a-change (acme/widgets#171)"
    DELTA = "openspec/changes/lore-search/specs/cap/spec.md"

    def setUp(self):
        self.s = Stack(self)

    def refused(self, out, name, quote):
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        hits = [l for l in errors(out) if "[archive]" in l and quote in l]
        self.assertEqual(len(hits), 1, out.stdout)
        self.assertTrue(hits[0].startswith(self.DELTA + ":"), hits[0])
        self.assertIn(f'"{name}"', hits[0])
        self.assertIn("openspec archive (lore-search): refused", out.stdout)
        return hits[0]

    def test_adding_a_requirement_its_dependency_adds_is_an_error(self):
        self.s.dependency(171, "a-change", ADDED_AUDIT)
        self.s.stacked(ADDED_AUDIT.replace(AUDIT, AUDIT + " The log SHALL be kept for a year."), self.A)
        line = self.refused(self.s.check("lore-search"), "Audit trail", "already exists")
        self.assertIn(f"{self.DELTA}:3:", line)  # the ADDED header

    def test_renaming_onto_a_name_its_dependency_adds_is_an_error(self):
        self.s.dependency(171, "a-change", ADDED_AUDIT)
        self.s.stacked(renamed("Records are kept", "Audit trail"), self.A)
        self.refused(self.s.check("lore-search"), "Audit trail", "target already exists")

    def test_a_modification_dropping_a_scenario_its_dependency_added_is_an_error(self):
        two = (modified("Records are kept", KEPT) +
               "\n#### Scenario: Two\n\n- **WHEN** a record is read\n- **THEN** its clock resets\n")
        self.s.dependency(171, "a-change", two)
        self.s.stacked(modified("Records are kept", KEPT, "Records SHALL be kept on two disks."), self.A)
        self.refused(self.s.check("lore-search"), "Records are kept",
                     "current spec contains scenario(s) not present in the modified block")

    def test_a_change_that_fits_what_it_builds_on_still_passes(self):
        two = (modified("Records are kept", KEPT) +
               "\n#### Scenario: Two\n\n- **WHEN** a record is read\n- **THEN** its clock resets\n")
        self.s.dependency(171, "a-change", two)
        self.s.stacked(modified("Records are kept", KEPT, "Records SHALL be kept on two disks.") +
                       "\n#### Scenario: Two\n\n- **WHEN** a record is read\n- **THEN** its clock resets\n"
                       + "\n" + ADDED_AUDIT, self.A)
        out = self.s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(kinds(out), [], out.stdout)

    def test_the_archive_leaves_the_base_of_the_other_checks_alone(self):
        # The stacked change renames a requirement its dependency adds. Had
        # its archive reached the base, the drift check would not find
        # "Audit trail" there to modify.
        self.s.dependency(171, "a-change", ADDED_AUDIT)
        self.s.stacked(renamed("Audit trail", "Audit log") + "## MODIFIED Requirements\n\n"
                       "### Requirement: Audit log\n\n" + AUDIT + " The log SHALL be kept for a year."
                       "\n\n#### Scenario: s\n\n- **WHEN** w\n- **THEN** t\n", self.A)
        out = self.s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(kinds(out), [], out.stdout)

    def test_a_refusal_about_a_capability_with_no_spec_is_not_pinned_on_another_file(self):
        # The CLI's "target spec does not exist" refusal names no requirement.
        # It is reported once, on the delta file of the missing capability,
        # never again at line 0 of whichever delta file sorts first. Found by
        # bug-hunter run 9, iteration 1.
        self.s.dependency(171, "seat-files", SEAT_FILES)
        self.s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH), "seat-files (acme/widgets#171)")
        self.s.repo.write("openspec/changes/lore-search/specs/zeta/spec.md", modified("Zeta rule", AUDIT))
        out = self.s.check("lore-search")
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        errs = errors(out)
        self.assertEqual(len(errs), 1, out.stdout)
        self.assertTrue(errs[0].startswith("openspec/changes/lore-search/specs/zeta/spec.md:3:"), errs[0])

    def test_an_added_name_already_present_is_reported_beside_a_missing_scenario(self):
        # The refusal is the only sign of the name collision, so it is
        # reported even when a no-scenario error sits on the same line.
        # Found by bug-hunter run 9, iteration 1.
        self.s.dependency(171, "seat-files", SEAT_FILES)
        self.s.stacked("## ADDED Requirements\n\n### Requirement: Records are retained\n\n" + SEARCH + "\n",
                       "seat-files (acme/widgets#171)")
        out = self.s.check("lore-search")
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("no-scenario", kinds(out), out.stdout)
        self.refused(out, "Records are retained", "already exists")

    @staticmethod
    def added(name, body):
        return (f"## ADDED Requirements\n\n### Requirement: {name}\n\n{body}\n\n"
                "#### Scenario: s\n\n- **WHEN** w\n- **THEN** t\n")

    def test_a_refusal_naming_a_requirement_with_a_quote_and_dash_lands_on_its_line(self):
        # The requirement name is read whole from the refusal, past any `" -`
        # inside it, so the error lands on that requirement's line. Found by
        # bug-hunter run 9, iteration 2.
        name = 'Button "Save" - disabled state'
        self.s.dependency(171, "a-change", self.added(name, AUDIT))
        self.s.stacked(self.added(name, SEARCH), self.A)
        line = self.refused(self.s.check("lore-search"), name, "already exists")
        self.assertIn(f"{self.DELTA}:3:", line)

    def test_a_file_beside_the_delta_ending_in_spec_md_is_not_archived(self):
        # OpenSpec archives only <cap>/spec.md. A sibling such as v2-spec.md
        # is left out of the archive, so it cannot take the delta's place and
        # hide the delta's refusal. Found by bug-hunter run 9, iteration 3.
        self.s.dependency(171, "a-change", ADDED_AUDIT)
        self.s.stacked(ADDED_AUDIT.replace(AUDIT, AUDIT + " The log SHALL be kept for a year."), self.A)
        self.s.repo.write("openspec/changes/lore-search/specs/cap/v2-spec.md", self.added("Search", SEARCH))
        line = self.refused(self.s.check("lore-search"), "Audit trail", "already exists")
        self.assertIn(f"{self.DELTA}:3:", line)


def signed_commit(test, repo, read="subagent", message="Change the spec", extra=()):
    """Signs the staged tree with sign --read <read> and commits it with that
    trailer; returns the trailer's value."""
    r = repo.run("sign", "--read", read, "--base", "main", "--no-validate", *extra)
    test.assertEqual(r.returncode, 0, r.stdout + r.stderr)
    value = r.stdout.strip().splitlines()[-1][len("Spec-check: "):]
    repo.git("commit", "-q", "-m", message, "--trailer", f"Spec-check: {value}")
    return value


class RoundTests(unittest.TestCase):
    """One consistency read per round: the trailer records where it ran
    (DECISIONS.md, "One consistency read per round")."""

    def setUp(self):
        self.repo = Repo(self)
        self.repo.git("checkout", "-q", "-b", "spec")

    def sign(self, read, *extra):
        return self.repo.run("sign", "--read", read, "--base", "main", "--no-validate", *extra)

    def value(self, r):
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout.strip().splitlines()[-1]

    def test_a_deferred_read_says_so(self):
        self.repo.change("good")
        self.repo.git("add", "-A")
        r = self.sign("deferred")
        line = self.value(r)
        self.assertTrue(line.endswith("; read deferred to the round's end"), line)

    def test_a_deferred_read_takes_no_counts(self):
        self.repo.change("good")
        self.repo.git("add", "-A")
        r = self.sign("deferred", "--amended", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("a deferred read has none", r.stderr)

    def test_a_read_names_the_changes_it_read(self):
        self.repo.change("good")
        self.repo.change("other", delta=GOOD_DELTA.replace("Records expire", "Records are counted")
                         .replace("delete a record ninety", "count a record each"))
        self.repo.git("add", "-A")
        line = self.value(self.sign("subagent", "--amended", "2", "--open", "1"))
        self.assertTrue(line.endswith("; read by a fresh subagent: good, other; 2 amended, 1 open"), line)

    def test_after_a_read_an_unchanged_change_is_not_due(self):
        self.repo.change("good")
        self.repo.git("add", "-A")
        signed_commit(self, self.repo)
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n")
        self.repo.git("add", "-A")
        line = self.value(self.sign("subagent"))
        self.assertTrue(line.endswith("; no read due"), line)

    def test_a_change_edited_after_its_read_is_due_again(self):
        self.repo.change("good")
        self.repo.git("add", "-A")
        signed_commit(self, self.repo)
        self.repo.write("openspec/changes/good/design.md", "## Context\n\nMore.\n")
        self.repo.git("add", "-A")
        line = self.value(self.sign("subagent"))
        self.assertIn("read by a fresh subagent: good;", line)

    def test_a_deferred_commit_does_not_count_as_a_read(self):
        self.repo.change("good")
        self.repo.git("add", "-A")
        signed_commit(self, self.repo, read="deferred")
        self.repo.write("src/app.py", "changed\n")
        self.repo.git("add", "-A")
        # Nothing under openspec/ is staged, but the change still waits for
        # its read, so a code commit can carry it.
        line = self.value(self.sign("subagent"))
        self.assertIn("read by a fresh subagent: good;", line)

    def test_a_code_commit_needs_no_trailer_when_no_read_waits(self):
        self.repo.change("good")
        self.repo.git("add", "-A")
        signed_commit(self, self.repo)
        self.repo.write("src/app.py", "changed\n")
        self.repo.git("add", "-A")
        r = self.sign("subagent")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no change waits for its consistency read", r.stderr)

    def test_a_value_from_before_rounds_read_the_changes_its_commit_touched(self):
        self.repo.change("good")
        self.repo.git("add", "-A")
        tree = self.repo.git("write-tree")
        self.repo.git("commit", "-q", "-m", "Old style", "--trailer",
                      f"Spec-check: ✓ {tree[:12]} 0 errors, 0 checks; validate passed; "
                      "read by a fresh subagent; 3 amended, 0 open")
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n")
        self.repo.git("add", "-A")
        self.assertTrue(self.value(self.sign("subagent")).endswith("; no read due"))

    def test_a_read_whose_tree_is_not_its_commits_records_nothing(self):
        self.repo.change("good")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "Copied trailer", "--trailer",
                      "Spec-check: ✓ 0123456789ab 0 errors, 0 checks; validate passed; "
                      "read by a fresh subagent: good; 0 amended, 0 open")
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n")
        self.repo.git("add", "-A")
        self.assertIn("read by a fresh subagent: good;", self.value(self.sign("subagent")))

class KeptInRoundsTests(unittest.TestCase):
    """Kept lines inside a review round: evolution errors fail every commit,
    deferred or not; the kept count sits beside the checks on each kind of
    value; and a value carrying it still records the round's read for sign,
    unread_at and ci."""

    DESIGN = "openspec/changes/x/design.md"
    KEPT = "openspec/changes/x/.spec-check-kept"
    ENTRY = "design.md: «The spec narrows the decision.» kept (asked): compares a spec with a decision\n"

    def setUp(self):
        self.repo = Repo(self)
        self.repo.git("checkout", "-q", "-b", "spec")
        self.repo.change("x")
        self.repo.write(self.DESIGN, "## Decisions\n\nThe spec narrows the decision.\n")

    def keep(self, text=ENTRY):
        self.repo.write(self.KEPT, text)
        self.repo.git("add", "-A")

    def sign(self, read):
        return self.repo.run("sign", "--read", read, "--base", "main", "--no-validate")

    def test_a_deferred_commit_refuses_an_evolution_error_nobody_kept(self):
        self.repo.git("add", "-A")
        r = self.sign("deferred")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("error [evolution]", r.stdout)

    def test_a_deferred_commit_counts_kept_lines_and_records_no_read(self):
        self.keep()
        value = signed_commit(self, self.repo, read="deferred")
        self.assertRegex(value, r"^✓ [0-9a-f]{12} 0 errors, 0 checks, 1 evolution kept; "
                                r"validate not run; read deferred to the round's end$")
        self.assertEqual(spec_check.unread_at(str(self.repo.path), "HEAD", "main"), ["x"])

    def test_a_read_carrying_kept_counts_is_the_changes_last_read(self):
        self.keep()
        value = signed_commit(self, self.repo)
        self.assertRegex(value, r"^✓ [0-9a-f]{12} 0 errors, 0 checks, 1 evolution kept; "
                                r"validate not run; read by a fresh subagent: x; 0 amended, 0 open$")
        self.assertEqual(spec_check.unread_at(str(self.repo.path), "HEAD", "main"), [])
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n")
        self.repo.git("add", "-A")
        r = self.sign("subagent")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.strip().endswith("; no read due"), r.stdout)

    def test_editing_only_the_kept_file_makes_the_change_due(self):
        self.keep()
        signed_commit(self, self.repo)
        self.keep(self.ENTRY + "\n")
        signed_commit(self, self.repo, read="deferred")
        self.assertEqual(spec_check.unread_at(str(self.repo.path), "HEAD", "main"), ["x"])

    def test_ci_passes_a_head_whose_read_carries_kept_counts(self):
        self.keep()
        signed_commit(self, self.repo)
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-ci-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        event = tmp / "event.json"
        event.write_text(json.dumps({"action": "ready_for_review", "pull_request": {
            "html_url": "https://github.com/o/r/pull/7", "draft": False,
            "head": {"sha": self.repo.git("rev-parse", "HEAD")}, "base": {"ref": "main"}}}))
        r = self.repo.run("ci", "--event", str(event))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no OpenSpec change is unread", r.stdout)


class RoundStartTests(unittest.TestCase):
    """Which commit a never-read change's edits are counted from (the merge
    base, or HEAD on the base branch), and which changes count as open (DECISIONS.md, "One consistency read per round")."""

    def setUp(self):
        self.repo = Repo(self)

    def value(self, *args):
        r = self.repo.run("sign", *args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout.strip().splitlines()[-1]

    def test_a_change_on_the_base_that_the_branch_leaves_alone_is_not_due(self):
        self.repo.change("onmain")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "A change on main")
        self.repo.git("checkout", "-q", "-b", "spec")
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n")
        self.repo.git("add", "-A")
        self.assertTrue(self.value("--read", "subagent", "--base", "main", "--no-validate")
                        .endswith("; no read due"))

    def test_with_the_base_at_head_an_unread_change_is_due(self):
        self.repo.git("checkout", "-q", "-b", "spec")
        self.repo.change("good")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "Unread")
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n")
        self.repo.git("add", "-A")
        self.assertIn("read by a fresh subagent: good;",
                      self.value("--read", "subagent", "--base", "HEAD", "--no-validate"))

    def test_a_change_with_no_deltas_is_open_and_its_read_is_recorded(self):
        self.repo.git("checkout", "-q", "-b", "spec")
        self.repo.write("openspec/changes/bare/proposal.md", GOOD_PROPOSAL)
        self.repo.git("add", "-A")
        self.assertIn("read by a fresh subagent: bare;",
                      self.value("--read", "subagent", "--base", "main", "--no-validate"))

    def test_a_value_from_before_rounds_covers_a_commit_of_top_level_files(self):
        self.repo.git("checkout", "-q", "-b", "spec")
        self.repo.change("good")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "Unread")
        self.repo.write("openspec/changes/good/tasks.md", TASKS + "- [ ] 1.2 More\n")
        self.repo.git("add", "-A")
        tree = self.repo.git("write-tree")
        self.repo.git("commit", "-q", "-m", "Old style", "--trailer",
                      f"Spec-check: ✓ {tree[:12]} 0 errors, 0 checks; validate passed; "
                      "read by a fresh subagent; 0 amended, 0 open")
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC + "\n")
        self.repo.git("add", "-A")
        self.assertTrue(self.value("--read", "subagent", "--base", "main", "--no-validate")
                        .endswith("; no read due"))

    @unittest.skipUnless(HAS_OPENSPEC, "needs OpenSpec 1.15.0 or later")
    def test_a_change_that_validates_says_validate_passed(self):
        self.repo.git("checkout", "-q", "-b", "spec")
        self.repo.change("good")
        self.repo.git("add", "-A")
        self.assertIn("; validate passed;", self.value("--read", "subagent", "--base", "main"))


class FoundByBugHunterRoundsIteration2Tests(unittest.TestCase):
    """Bug-hunter's second iteration over rounds."""

    def setUp(self):
        self.repo = Repo(self)
        up = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-up-")).resolve()
        self.addCleanup(shutil.rmtree, up, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "--bare", str(up)], check=True, env=ENV)
        self.repo.git("remote", "add", "origin", str(up))
        self.repo.git("push", "-q", "origin", "main")

    def test_a_merged_change_with_an_edit_after_its_read_is_not_due_on_another_branch(self):
        r = self.repo
        r.git("checkout", "-q", "-b", "pr1")
        r.change("x")
        r.git("add", "-A")
        signed_commit(self, r)
        r.write("openspec/changes/x/tasks.md", TASKS + "- [ ] 1.2 Suggested\n")
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "Apply suggestion from code review")
        r.git("checkout", "-q", "main")
        r.git("merge", "-q", "--no-ff", "pr1", "-m", "Merge PR 1")
        r.git("push", "-q", "origin", "main")
        r.git("checkout", "-q", "-b", "pr2", "origin/main")
        r.change("y", delta=GOOD_DELTA.replace("Records expire", "Logs rotate").replace(
            "delete a record ninety days after its last read", "rotate a log file weekly"))
        r.git("add", "-A")
        out = r.run("sign", "--read", "subagent", "--base", "origin/main", "--no-validate")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("read by a fresh subagent: y;", out.stdout)

class FoundByBugHunterWholeReadTests(unittest.TestCase):
    """Bug-hunter's run over whole-change rounds."""

    def setUp(self):
        self.repo = Repo(self)

    def origin(self):
        up = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-up-")).resolve()
        self.addCleanup(shutil.rmtree, up, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "--bare", str(up)], check=True, env=ENV)
        self.repo.git("remote", "add", "origin", str(up))
        self.repo.git("push", "-q", "origin", "main")

    def test_a_round_committed_on_the_base_branch_keeps_its_read_due(self):
        r = self.repo
        r.change("good")
        r.git("add", "-A")
        signed_commit(self, r, read="deferred")
        r.write("src/app.py", "x = 1\n")
        r.git("add", "-A")
        out = r.run("sign", "--read", "subagent", "--no-validate")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("read by a fresh subagent: good;", out.stdout)

    def test_a_tag_named_like_the_branch_does_not_hide_the_base_branch(self):
        r = self.repo
        self.origin()
        r.git("tag", "main")
        r.change("good")
        r.git("add", "-A")
        signed_commit(self, r, read="deferred")
        r.git("push", "-q", "origin", "refs/heads/main:refs/heads/main")
        r.write("src/app.py", "x = 1\n")
        r.git("add", "-A")
        out = r.run("sign", "--read", "subagent", "--base", "origin/main", "--no-validate")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("read by a fresh subagent: good;", out.stdout)



class TouchedChangesTests(unittest.TestCase):
    """Which open changes a commit touches, for a read recorded before
    reads named their changes (tests from bug-hunter's mutation pass)."""

    def setUp(self):
        self.repo = Repo(self)

    def test_a_commit_adding_only_under_archive_touches_no_open_change(self):
        r = self.repo
        r.write("openspec/changes/archive/2026-01-01-y/tasks.md", TASKS)
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "Archive y")
        self.assertEqual(spec_check.touched_changes(str(r.path), r.git("rev-parse", "HEAD")), set())

    def test_a_root_commit_touches_the_changes_it_adds(self):
        r = self.repo
        r.git("checkout", "-q", "--orphan", "fresh")
        r.change("x")
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "A history that starts with a change")
        self.assertEqual(spec_check.touched_changes(str(r.path), r.git("rev-parse", "HEAD")), {"x"})

HANDBACK = HERE / "check-handback.sh"
# A gh that answers `gh pr view <selector>` from $FAKE_PRS, a JSON object
# keyed by selector or URL, or else with the JSON in $FAKE_PR (failing when
# neither is set or the selector is not a key), succeeds at `gh pr ready --undo` and `gh pr edit` unless
# $FAKE_UNDO_FAIL is set, and logs every call to $FAKE_PR_LOG.
FAKE_PR_GH = """\
import json, os, sys
a = sys.argv[1:]
if os.environ.get("FAKE_PR_LOG"):
    with open(os.environ["FAKE_PR_LOG"], "a") as fh:
        fh.write(json.dumps(a) + "\\n")
if a[:2] == ["pr", "view"] and os.environ.get("FAKE_PRS") is not None:
    prs = json.loads(os.environ["FAKE_PRS"])
    key = a[2] if len(a) > 2 and not a[2].startswith("-") else ""
    if key not in prs:
        sys.exit("gh: no pull request " + key)
    print(json.dumps(prs[key]))
elif a[:2] == ["pr", "view"] and os.environ.get("FAKE_PR") is not None:
    print(os.environ["FAKE_PR"])
elif a[:2] in (["pr", "ready"], ["pr", "edit"]) and not os.environ.get("FAKE_UNDO_FAIL"):
    pass
else:
    sys.exit("gh: not this time")
"""


class HandbackBase(unittest.TestCase):
    """A repository on branch spec, pushed to an origin that stands in for
    GitHub, and the hand-back hook run against it."""

    def setUp(self):
        self.repo = Repo(self)
        self.repo.git("checkout", "-q", "-b", "spec")
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-hb-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.tmp, self.up, self.cache = tmp, tmp / "origin", tmp / "cache"
        subprocess.run(["git", "init", "-q", "--bare", str(self.up)], check=True, env=ENV)
        self.repo.git("remote", "add", "origin", str(self.up))
        self.repo.git("push", "-q", "origin", "main")
        self.gh = tmp / "gh"
        self.gh.write_text(f"#!{sys.executable}\n" + FAKE_PR_GH)
        self.gh.chmod(0o755)
        self.log = tmp / "gh.log"

    def pr(self, number=7, draft=False):
        """Pushes branch spec as pull request <number> and returns gh's view."""
        self.repo.git("push", "-q", "-f", "origin", f"spec:spec",
                      f"spec:refs/pull/{number}/head")
        return {"number": number, "url": f"{self.up}/pull/{number}",
                "headRefOid": self.repo.git("rev-parse", "spec"), "baseRefName": "main",
                "isDraft": draft}

    def run_hook(self, payload, host="claude", pr=None, extra_env=None):
        env = dict(ENV, SPEC_CHECK_GH=str(self.gh), SPEC_CHECK_CACHE=str(self.cache),
                   FAKE_PR_LOG=str(self.log))
        if pr is not None:
            env["FAKE_PR"] = json.dumps(pr)
        env.update(extra_env or {})
        return subprocess.run([str(HANDBACK), "--host", host], input=json.dumps(payload),
                              capture_output=True, text=True, env=env, cwd=self.repo.path)

    def hook(self, command, pr=None, output=None, host="claude", cwd=None, extra_env=None):
        """The hook before a Bash call, or after it when output is given."""
        payload = {"tool_name": "Bash", "tool_input": {"command": command},
                   "cwd": str(cwd or self.repo.path), "hook_event_name": "PreToolUse"}
        if output is not None:
            payload.update(hook_event_name="PostToolUse",
                           tool_response={"stdout": output, "stderr": ""})
        if host == "cursor":
            payload = {"command": command, "cwd": str(cwd or self.repo.path),
                       "hook_event_name": "beforeShellExecution"}
            if output is not None:
                payload = {"tool_name": "Shell", "tool_input": {"command": command},
                           "tool_output": output, "cwd": str(cwd or self.repo.path),
                           "hook_event_name": "postToolUse"}
        return self.run_hook(payload, host, pr, extra_env)

    def calls(self):
        """Every gh call the hook made, as argument lists."""
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def undos(self):
        return [c for c in self.calls() if c[:2] in (["pr", "ready"], ["pr", "edit"])]

    def blocked(self, r, *names):
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("spec-check: blocked this hand-back", r.stderr)
        for name in names:
            self.assertIn(name, r.stderr)

    def taken_back(self, r, *names):
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("spec-check: took back a hand-back", r.stderr)
        for name in names:
            self.assertIn(name, r.stderr)

    def allowed(self, r):
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stderr, "")

    def noted(self, r, reason, host="claude"):
        """Not judged: nothing blocked or undone, and the agent told why."""
        self.allowed(r)
        out = json.loads(r.stdout)
        note = out["additional_context"] if host == "cursor" else \
            out["hookSpecificOutput"]["additionalContext"]
        for part in ("did not check this hand-back", reason,
                     "git, cd, echo, printf, true or sleep",
                     "no $, backticks, globs, braces or leading ~",
                     "run `gh pr ...` on its own", "GitHub workflow, it still checks"):
            self.assertIn(part, note)
        self.assertEqual(self.undos(), [])
        return out

    def deferred(self):
        self.repo.change("good")
        self.repo.git("add", "-A")
        signed_commit(self, self.repo, read="deferred")

    def read(self):
        self.repo.write("openspec/changes/good/tasks.md", TASKS + "- [ ] 1.2 More\n")
        self.repo.git("add", "-A")
        signed_commit(self, self.repo)


class HandbackBeforeTests(HandbackBase):
    """Before the call: a hand-back whose pull request can be found without
    knowing the directory gh runs in (DECISIONS.md, "One consistency read per
    round")."""

    def test_a_named_hand_back_with_an_unread_change_is_blocked(self):
        self.deferred()
        pr = self.pr()
        for command in ("gh pr ready 7 -R o/r", "gh -R o/r pr ready 7",
                        "gh pr --repo=o/r ready 7", "GH_REPO=o/r gh pr ready 7",
                        f"gh pr ready {pr['url']}", "gh pr edit 7 -R o/r --add-reviewer=adam",
                        "git push && gh pr ready 7 -R o/r"):
            with self.subTest(command=command):
                self.blocked(self.hook(command, pr=pr), "good", pr["url"])

    def test_after_the_read_the_hand_back_goes_ahead(self):
        self.deferred()
        self.read()
        self.repo.write("src/app.py", "code after the read\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "Code")
        self.allowed(self.hook("gh pr ready 7 -R o/r", pr=self.pr()))

    def test_the_pull_request_s_head_is_judged_not_the_local_branch(self):
        self.deferred()
        pr = self.pr()
        self.read()  # read locally, not pushed
        self.blocked(self.hook("gh pr ready 7 -R o/r", pr=pr), "good")

    def test_an_edit_after_the_read_is_unread_again(self):
        self.repo.change("good")
        self.repo.git("add", "-A")
        signed_commit(self, self.repo)
        self.repo.write("openspec/changes/good/tasks.md", TASKS + "- [ ] 1.2 More\n")
        self.repo.git("add", "-A")
        signed_commit(self, self.repo, read="deferred")
        self.blocked(self.hook("gh pr ready 7 -R o/r", pr=self.pr()), "good")

    def test_a_change_the_branch_leaves_alone_is_not_unread(self):
        self.repo.git("checkout", "-q", "main")
        self.repo.change("onmain")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "A change on main, read in its own pull request")
        self.repo.git("push", "-q", "origin", "main")
        self.repo.git("checkout", "-q", "-B", "spec")
        self.repo.write("src/app.py", "x\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "Code only")
        self.allowed(self.hook("gh pr ready 7 -R o/r", pr=self.pr()))

    def test_a_hand_back_found_only_through_a_directory_is_not_judged_before(self):
        self.deferred()
        pr = self.pr()
        for command in ("gh pr ready 7", "gh pr ready spec", "gh pr ready",
                        "gh pr create --title x", "gh pr edit --add-reviewer adam"):
            self.allowed(self.hook(command, pr=pr))
        self.assertEqual(self.calls(), [])

    def test_what_is_not_a_hand_back_is_not_judged(self):
        self.deferred()
        pr = self.pr()
        for command in ("gh pr create --draft --title x -R o/r", "gh pr create -dt x",
                        "gh pr create --dry-run", "gh pr ready 7 -R o/r --undo",
                        "gh pr edit 7 -R o/r --title 'New title'",
                        "sed -i '' 's/gh pr create/gh pr create --draft/' notes.md",
                        "printf '%s\\n' 'then run gh pr ready 7 -R o/r'"):
            self.allowed(self.hook(command, pr=pr))
        self.assertEqual(self.calls(), [])

    def test_a_pull_request_gh_cannot_show_or_fetch_is_let_through(self):
        self.deferred()
        self.allowed(self.hook("gh pr ready 7 -R o/r"))
        pr = self.pr()
        pr["url"] = f"{self.tmp}/nowhere/pull/7"
        self.allowed(self.hook("gh pr ready 7 -R o/r", pr=pr))
        pr["url"] = str(self.up)
        self.allowed(self.hook("gh pr ready 7 -R o/r", pr=pr))

    def test_a_head_github_has_no_pull_ref_for_yet_is_still_judged(self):
        self.deferred()
        pr = self.pr()
        subprocess.run(["git", "-C", str(self.up), "update-ref", "-d", "refs/pull/7/head"],
                       check=True, env=ENV)
        self.blocked(self.hook("gh pr ready 7 -R o/r", pr=pr), "good")

    def test_a_pull_request_without_openspec_is_never_blocked(self):
        self.repo.write("src/app.py", "x\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "Code")
        self.allowed(self.hook("gh pr ready 7 -R o/r", pr=self.pr()))

    def test_a_github_mcp_update_is_judged(self):
        self.deferred()
        pr = self.pr()
        for tool in ("mcp__github__update_pull_request",
                     "mcp__plugin_gh_github__update_pull_request"):
            update = {"tool_name": tool, "cwd": str(self.repo.path),
                      "hook_event_name": "PreToolUse",
                      "tool_input": {"owner": "o", "repo": "r", "pullNumber": 7, "draft": False}}
            self.blocked(self.run_hook(update, pr=pr), "MCP update_pull_request")
        update["tool_input"] = {"owner": "o", "repo": "r", "pullNumber": 7, "title": "y"}
        self.allowed(self.run_hook(update, pr=pr))

    def test_cursor_gets_a_permission(self):
        self.deferred()
        pr = self.pr()
        r = self.hook("gh pr ready 7 -R o/r", pr=pr, host="cursor")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["permission"], "deny")
        r = self.hook("gh pr ready 7 -R o/r --undo", pr=pr, host="cursor")
        self.assertEqual(json.loads(r.stdout), {"permission": "allow"})

    def test_the_fetched_pull_requests_are_kept_in_one_cache_per_repository(self):
        self.deferred()
        pr = self.pr()
        self.hook("gh pr ready 7 -R o/r", pr=pr)
        self.hook("gh pr ready 7 -R o/r", pr=pr)
        self.assertEqual(len(list((self.cache / "pulls").iterdir())), 1)


class HandbackAfterTests(HandbackBase):
    """After the call: a command holding exactly one gh call, a hand-back,
    judged at the pull request it printed, and taken back."""

    READY_7 = '✓ Pull request o/r#7 is marked as "ready for review"\n'

    def prs(self, *prs):
        found = {}
        for pr in prs:
            found.update({str(pr["number"]): pr, pr["url"]: pr})
        return {"FAKE_PRS": json.dumps(found)}

    def test_a_pull_request_created_ready_with_an_unread_change_is_made_a_draft(self):
        self.deferred()
        pr = self.pr()
        r = self.hook("gh pr create --title x", pr=pr, output=pr["url"] + "\n")
        self.taken_back(r, pr["url"], "good", "it is a draft again")
        self.assertEqual(self.undos(), [["pr", "ready", pr["url"], "--undo"]])

    def test_the_reviewers_the_call_requested_are_removed(self):
        self.deferred()
        pr = self.pr()
        self.hook("gh pr create -t x -r adam,bo --reviewer cy", pr=pr, output=pr["url"])
        ready, edit = self.undos()
        self.assertEqual(ready, ["pr", "ready", pr["url"], "--undo"])
        self.assertEqual(edit[:4], ["pr", "edit", pr["url"], "--remove-reviewer"])
        self.assertEqual(sorted(edit[4].split(",")), ["adam", "bo", "cy"])

    def test_a_review_request_is_withdrawn_without_making_a_draft(self):
        self.deferred()
        pr = self.pr()
        r = self.hook("gh pr edit --add-reviewer adam", pr=pr, output=pr["url"] + "\n")
        self.taken_back(r, "the review request to adam is withdrawn")
        self.assertEqual(self.undos(), [["pr", "edit", pr["url"], "--remove-reviewer", "adam"]])

    def test_a_draft_that_requested_a_reviewer_loses_only_the_request(self):
        self.deferred()
        pr = self.pr(draft=True)
        self.hook("gh pr create -d -r adam -t x", pr=pr, output=pr["url"])
        self.assertEqual(self.undos(), [["pr", "edit", pr["url"], "--remove-reviewer", "adam"]])

    def test_gh_s_ready_line_names_the_pull_request(self):
        self.deferred()
        pr = self.pr()
        for command in ("gh pr ready", "gh pr ready 7", f"git push && gh pr ready {pr['url']}"):
            with self.subTest(command=command):
                self.taken_back(self.hook(command, output=self.READY_7, extra_env=self.prs(pr)),
                                "good")
        self.assertIn(["pr", "view", "7", "--json", "number,url,headRefOid,baseRefName,isDraft",
                       "-R", "o/r"], self.calls())

    def test_gh_s_lines_are_found_on_stderr_and_after_other_lines(self):
        self.deferred()
        pr = self.pr()
        payload = {"tool_name": "Bash", "tool_input": {"command": "git push && gh pr ready"},
                   "cwd": str(self.repo.path), "hook_event_name": "PostToolUse",
                   "tool_response": {"stdout": "", "stderr": self.READY_7}}
        self.taken_back(self.run_hook(payload, pr=pr), "good")
        self.taken_back(self.hook("git push && gh pr create -t x", pr=pr,
                                  output=f"\nCreating pull request for spec into main\n\n"
                                         f"{pr['url']}\n"), "good")

    def test_after_the_read_nothing_is_taken_back(self):
        self.deferred()
        self.read()
        pr = self.pr()
        self.allowed(self.hook("gh pr create --title x", pr=pr, output=pr["url"]))
        self.assertEqual(self.undos(), [])

    def test_a_command_with_any_gh_the_reader_cannot_see_is_not_judged(self):
        self.deferred()
        pr = self.pr()
        for command in ("gh pr checks 7 && gh pr ready",
                        "gh pr view 8 --json url -q .url; gh pr ready 7",
                        "timeout 60 gh pr ready 7", "stdbuf -oL gh pr create -t x",
                        "op run -- gh pr create -t x", "bash -c 'gh pr create -t x'",
                        "xargs gh pr ready < prs.txt", "awk 'BEGIN{system(\"gh pr ready 7\")}'",
                        "git -c alias.r='!gh pr ready 7' r",
                        'gh pr ready "$(git branch --show-current)"',
                        "bash <<EOF\ngh pr create --title x\nEOF",
                        "gh pr create -t x; bash <<EOF\ngh pr ready 8\nEOF",
                        "echo 'gh pr ready 8' | bash; gh pr create -t x"):
            with self.subTest(command=command):
                self.allowed(self.hook(command, output=self.READY_7 + pr["url"] + "\n",
                                       extra_env=self.prs(pr)))
        self.assertEqual(self.calls(), [])

    def test_a_hand_back_that_printed_no_one_pull_request_is_not_judged(self):
        self.deferred()
        seven, eight = self.pr(7), self.pr(8)
        env = self.prs(seven, eight)
        self.allowed(self.hook("gh pr create -t x > /dev/null", output="", extra_env=env))
        self.allowed(self.hook("gh pr create -t x", output=f"{seven['url']}\n{eight['url']}\n",
                               extra_env=env))
        self.assertEqual(self.calls(), [])

    def test_without_the_shared_reader_nothing_is_judged(self):
        self.deferred()
        pr = self.pr()
        sys.path.insert(0, str(HERE))
        import handback
        payload = {"tool_name": "Bash", "tool_input": {"command": "gh pr create -t x"},
                   "cwd": str(self.repo.path), "hook_event_name": "PostToolUse",
                   "tool_response": {"stdout": pr["url"], "stderr": ""}}
        with mock.patch.object(handback, "load_reader", return_value=None), \
                mock.patch.object(handback.sc, "GH", str(self.gh)), \
                mock.patch.dict(os.environ, {"SPEC_CHECK_CACHE": str(self.cache),
                                             "FAKE_PR": json.dumps(pr),
                                             "FAKE_PR_LOG": str(self.log)}):
            self.assertEqual(handback.hook(json.dumps(payload), "claude"), (0, "", ""))

    def test_a_draft_made_with_nobody_requested_is_left_alone(self):
        self.deferred()
        pr = self.pr(draft=True)
        self.allowed(self.hook("gh pr create --title x", pr=pr, output=pr["url"]))
        self.assertEqual(self.undos(), [])

    def test_a_hand_back_in_a_command_that_fails_is_still_taken_back(self):
        self.deferred()
        pr = self.pr()
        payload = {"tool_name": "Bash", "tool_input": {"command": "git push && gh pr create -t x"},
                   "cwd": str(self.repo.path), "hook_event_name": "PostToolUseFailure",
                   "error": f"{pr['url']}\nExit code 1"}
        self.taken_back(self.run_hook(payload, pr=pr), "good")

    def test_a_create_that_fails_because_the_pull_request_exists_takes_nothing_back(self):
        self.deferred()
        pr = self.pr()
        payload = {"tool_name": "Bash",
                   "tool_input": {"command": "gh pr create -t x -r adam --draft"},
                   "cwd": str(self.repo.path), "hook_event_name": "PostToolUseFailure",
                   "error": 'a pull request for branch "spec" into branch "main" already '
                            f'exists:\n{pr["url"]}\n'}
        self.allowed(self.run_hook(payload, pr=pr))
        self.assertEqual(self.undos(), [])

    def test_a_failed_undo_says_what_to_run(self):
        self.deferred()
        pr = self.pr()
        r = self.hook("gh pr create --title x", pr=pr, output=pr["url"],
                      extra_env={"FAKE_UNDO_FAIL": "1"})
        self.taken_back(r, f"gh pr ready {pr['url']} --undo")

    def test_a_payload_with_output_and_no_event_name_is_after_the_call(self):
        self.deferred()
        pr = self.pr()
        payload = {"tool_name": "Bash", "tool_input": {"command": "gh pr create -t x"},
                   "cwd": str(self.repo.path), "tool_response": {"stdout": pr["url"]}}
        self.taken_back(self.run_hook(payload, pr=pr), "good")

    def test_a_github_mcp_call_is_judged_from_its_result(self):
        self.deferred()
        pr = self.pr()
        payload = {"tool_name": "mcp__github__create_pull_request", "cwd": str(self.repo.path),
                   "hook_event_name": "PostToolUse",
                   "tool_input": {"owner": "o", "repo": "r", "head": "spec", "base": "main",
                                  "title": "x", "body": "Alternative to o/r/pull/51"},
                   "tool_response": [{"type": "text", "text": json.dumps(
                       {"number": 7, "html_url": pr["url"],
                        "body": "Alternative to https://github.com/o/r/pull/51"})}]}
        self.taken_back(self.run_hook(payload, pr=pr), pr["url"])
        self.assertEqual(self.undos(), [["pr", "ready", pr["url"], "--undo"]])
        payload["tool_input"]["draft"] = True
        self.log.unlink()
        self.allowed(self.run_hook(payload, pr=pr))
        update = {"tool_name": "mcp__github__update_pull_request", "cwd": str(self.repo.path),
                  "hook_event_name": "PostToolUse", "tool_response": "ok",
                  "tool_input": {"owner": "o", "repo": "r", "pullNumber": 7,
                                 "reviewers": ["adam"]}}
        self.taken_back(self.run_hook(update, pr=pr), "adam")

    def test_cursor_is_told_through_additional_context(self):
        self.deferred()
        pr = self.pr()
        r = self.hook("gh pr create --title x", pr=pr, output=pr["url"], host="cursor")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("took back", json.loads(r.stdout)["additional_context"])
        payload = {"tool_name": "Shell", "tool_input": {"command": "git push && gh pr create"},
                   "tool_output": json.dumps({"exitCode": 0, "stdout": pr["url"] + "\n"}),
                   "cwd": str(self.repo.path), "hook_event_name": "postToolUse"}
        r = self.run_hook(payload, host="cursor", pr=pr)
        self.assertIn("took back", json.loads(r.stdout)["additional_context"])
        self.read()
        pr = self.pr()
        r = self.hook("gh pr create -t x", pr=pr, output=pr["url"], host="cursor")
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)


class CiTests(unittest.TestCase):
    """The GitHub workflow's check (spec_check.py ci) and setup-ci."""

    def setUp(self):
        self.repo = Repo(self)
        self.repo.git("checkout", "-q", "-b", "spec")
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-ci-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.tmp = tmp
        self.gh = tmp / "gh"
        self.gh.write_text(f"#!{sys.executable}\n" + FAKE_PR_GH)
        self.gh.chmod(0o755)
        self.log = tmp / "gh.log"

    def deferred(self):
        self.repo.change("good")
        self.repo.git("add", "-A")
        signed_commit(self, self.repo, read="deferred")

    def ci(self, action, draft=False, **extra):
        event = {"action": action, "pull_request": {
            "html_url": "https://github.com/o/r/pull/7", "draft": draft,
            "head": {"sha": self.repo.git("rev-parse", "HEAD")}, "base": {"ref": "main"}}}
        event.update(extra)
        path = self.tmp / "event.json"
        path.write_text(json.dumps(event))
        return self.repo.run("ci", "--event", str(path),
                             env=dict(ENV, SPEC_CHECK_GH=str(self.gh), FAKE_PR_LOG=str(self.log)))

    def calls(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()] \
            if self.log.exists() else []

    def test_a_hand_back_with_an_unread_change_fails_and_is_made_a_draft(self):
        self.deferred()
        for action in ("opened", "ready_for_review"):
            r = self.ci(action)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("::error::spec-check: good", r.stdout)
        self.assertEqual(self.calls(), [["pr", "ready", "https://github.com/o/r/pull/7",
                                         "--undo"]] * 2)

    def test_a_review_request_is_withdrawn(self):
        self.deferred()
        self.assertEqual(self.ci("review_requested", draft=True,
                                 requested_reviewer={"login": "adam"}).returncode, 1)
        self.assertEqual(self.ci("review_requested", requested_team={"slug": "core"},
                                 repository={"owner": {"login": "o"}}).returncode, 1)
        self.assertEqual(self.calls(), [
            ["pr", "edit", "https://github.com/o/r/pull/7", "--remove-reviewer", "adam"],
            ["pr", "ready", "https://github.com/o/r/pull/7", "--undo"],
            ["pr", "edit", "https://github.com/o/r/pull/7", "--remove-reviewer", "o/core"]])

    def test_a_push_only_fails_the_check(self):
        self.deferred()
        r = self.ci("synchronize")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.calls(), [])

    def test_a_draft_or_a_read_change_passes(self):
        self.deferred()
        self.assertEqual(self.ci("opened", draft=True).returncode, 0)
        self.assertEqual(self.ci("synchronize", draft=True).returncode, 0)
        self.repo.write("openspec/changes/good/tasks.md", TASKS + "- [ ] 1.2 More\n")
        self.repo.git("add", "-A")
        signed_commit(self, self.repo)
        r = self.ci("ready_for_review")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls(), [])

    def test_a_failed_undo_still_fails_the_check(self):
        self.deferred()
        event = self.tmp / "event.json"
        r = self.ci("ready_for_review")
        self.assertEqual(r.returncode, 1)
        env = dict(ENV, SPEC_CHECK_GH=str(self.gh), FAKE_UNDO_FAIL="1")
        r = self.repo.run("ci", "--event", str(event), env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("::warning::", r.stdout)

    def test_a_clone_without_the_base_cannot_run(self):
        self.deferred()
        self.repo.git("branch", "-m", "main", "trunk")
        r = self.ci("opened")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("fetch-depth: 0", r.stderr)

    def test_setup_ci_pins_a_commit_and_keeps_an_existing_workflow(self):
        sha = "a" * 40
        r = self.repo.run("setup-ci", "--sha", sha)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (self.repo.path / ".github/workflows/spec-check.yml").read_text()
        self.assertIn(f"SPEC_CHECK_SHA: {sha}", text)
        self.assertNotIn("<SPEC_CHECK_SHA>", text)
        self.assertIn("spec_check.py\" ci", text)
        self.assertEqual(self.repo.run("setup-ci", "--sha", "b" * 40).returncode, 1)
        self.assertEqual(self.repo.run("setup-ci", "--sha", "main", "--force").returncode, 1)
        self.assertEqual(self.repo.run("setup-ci", "--sha", "b" * 40, "--force").returncode, 0)

    def test_setup_ci_refuses_a_short_sha(self):
        r = self.repo.run("setup-ci", "--sha", "abc1234")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertFalse((self.repo.path / ".github").exists())


class FoundByBugHunterHandbackRun4Tests(HandbackAfterTests):
    """Bug-hunter's first iteration over the one-gh-call hand-back hook."""

    READY_8 = '✓ Pull request o/r#8 is marked as "ready for review"\n'

    def test_gh_hidden_from_the_reader_is_not_taken_for_the_one_it_sees(self):
        self.deferred()
        seven, eight = self.pr(7), self.pr(8)
        env = self.prs(seven, eight)
        edit = "gh pr edit 7 --add-reviewer adam >/dev/null; "
        for hidden in ("bash -o pipefail <<'EOF'\ngh pr ready 8\nEOF",
                       "bash -s x <<'EOF'\ngh pr ready 8\nEOF",
                       "env bash <<'EOF'\ngh pr ready 8\nEOF",
                       "bash /dev/stdin <<'EOF'\ngh pr ready 8\nEOF",
                       "bash -o pipefail <<< 'gh pr ready 8'",
                       "c='gh pr ready 8'; eval \"$c\"",
                       "G=gh; $G pr ready 8",
                       "python3 - <<'EOF'\nimport subprocess\nEOF",
                       "./make-pr.sh"):
            with self.subTest(hidden=hidden):
                self.allowed(self.hook(edit + hidden, output=self.READY_8, extra_env=env))
        self.assertEqual(self.calls(), [])

    def test_a_printed_pull_request_other_than_the_one_named_is_not_judged(self):
        self.deferred()
        seven, eight = self.pr(7), self.pr(8)
        self.allowed(self.hook("gh pr edit 7 --add-reviewer adam", output=eight["url"],
                               extra_env=self.prs(seven, eight)))
        self.assertEqual(self.calls(), [])

    def test_a_hand_back_with_words_only_the_shell_reads_is_judged(self):
        self.deferred()
        pr = self.pr()
        for command in ("gh pr create --title x --body-file ~/pr.md",
                        'gh pr create --title x --body "line one\\nline two"',
                        "gh pr create --title café"):
            with self.subTest(command=command):
                self.taken_back(self.hook(command, pr=pr, output=pr["url"]), "good")


class HandbackRun4MutationTests(HandbackAfterTests):
    """What the one-gh-call hook's mutants showed no test checked."""

    def mcp(self, tool, tool_input, response):
        return {"tool_name": f"mcp__github__{tool}", "cwd": str(self.repo.path),
                "hook_event_name": "PostToolUse", "tool_input": tool_input,
                "tool_response": response}

    def test_an_mcp_draft_that_requests_a_review_loses_the_request(self):
        self.deferred()
        pr = self.pr(draft=True)
        self.taken_back(self.run_hook(self.mcp(
            "create_pull_request", {"owner": "o", "repo": "r", "head": "spec", "base": "main",
                                    "title": "x", "draft": True, "reviewers": ["adam"]},
            json.dumps({"html_url": pr["url"]})), pr=pr), "adam")

    def test_an_mcp_update_marking_ready_makes_a_draft_again(self):
        self.deferred()
        pr = self.pr()
        self.taken_back(self.run_hook(self.mcp(
            "update_pull_request", {"owner": "o", "repo": "r", "pullNumber": 7, "draft": False},
            json.dumps({"html_url": pr["url"]})), pr=pr), "it is a draft again")

    def test_a_result_with_an_html_url_and_an_api_url_is_one_pull_request(self):
        self.deferred()
        pr = self.pr()
        self.taken_back(self.run_hook(self.mcp(
            "create_pull_request", {"owner": "o", "repo": "r", "head": "spec", "base": "main",
                                    "title": "x"},
            json.dumps({"html_url": pr["url"],
                        "url": "https://api.github.com/repos/o/r/pull/77"})), pr=pr), "good")

    def test_gh_s_already_exists_message_without_a_colon_names_no_hand_back(self):
        self.deferred()
        pr = self.pr()
        payload = {"tool_name": "Bash", "tool_input": {"command": "gh pr create -t x"},
                   "cwd": str(self.repo.path), "hook_event_name": "PostToolUseFailure",
                   "error": f'a pull request for branch "spec" already exists\n{pr["url"]}\n'}
        self.allowed(self.run_hook(payload, pr=pr))


class FoundByBugHunterHandbackRun4Iteration2Tests(FoundByBugHunterHandbackRun4Tests):
    """Bug-hunter's second iteration over the one-gh-call hand-back hook."""

    def test_a_hand_back_after_an_assignment_or_reserved_word_is_judged(self):
        self.deferred()
        pr = self.pr()
        for command in ("GH_REPO=o/r gh pr create -t x", "time gh pr create -t x",
                        "! gh pr create -t x"):
            with self.subTest(command=command):
                self.taken_back(self.hook(command, pr=pr, output=pr["url"]), "good")

    def test_a_shell_s_name_as_an_ordinary_argument_hides_nothing(self):
        self.deferred()
        pr = self.pr()
        for command in ("git add . && git commit -qm x && git push && gh pr create -t x",
                        "gh pr create -t x -r node", "gh pr create -t x -H source"):
            with self.subTest(command=command):
                self.taken_back(self.hook(command, pr=pr, output=pr["url"]), "good")

    def test_words_the_shell_expands_are_not_read_as_written(self):
        self.deferred()
        pr = self.pr()
        for command in ("gh pr edit 7 --add-reviewer={adam,bob}",
                        "gh pr edit 7 --add-reviewer adam,bo?"):
            with self.subTest(command=command):
                self.allowed(self.hook(command, pr=pr, output=pr["url"]))
        self.assertEqual(self.undos(), [])

    def test_gh_spelled_with_quotes_inside_another_program_is_hidden(self):
        self.deferred()
        seven, eight = self.pr(7), self.pr(8)
        env = self.prs(seven, eight)
        for hidden in ("timeout 60 g\\h pr ready 8", "timeout 60 g''h pr ready 8",
                       "echo 'pr ready 8' | xargs g\\h", "=bash <<'EOF'\ngh pr ready 8\nEOF",
                       "python3.12 - <<'EOF'\nimport os\nEOF"):
            with self.subTest(hidden=hidden):
                self.allowed(self.hook("gh pr create -t x >/dev/null; " + hidden,
                                       output=self.READY_8, extra_env=env))
        self.assertEqual(self.calls(), [])

    def test_a_number_or_url_gh_reads_as_the_same_pull_request_matches(self):
        self.deferred()
        pr = self.pr()
        self.taken_back(self.hook("gh pr ready 007", output=self.READY_7,
                                  extra_env=self.prs(pr)), "good")
        self.blocked(self.hook(f"gh pr ready {pr['url']}/files",
                               extra_env={"FAKE_PRS": json.dumps({pr["url"] + "/files": pr})}),
                     "good")


class FoundByBugHunterHandbackRun4Iteration3Tests(FoundByBugHunterHandbackRun4Tests):
    """Bug-hunter's third iteration over the one-gh-call hand-back hook."""

    def test_quoted_text_that_looks_like_a_glob_does_not_stop_the_judgement(self):
        self.deferred()
        pr = self.pr()
        for command in ('gh pr create -t x --body "## Summary\\n- a\\n\\n## Test plan\\n- [ ] run"',
                        'gh pr create -t "x [WIP]" -b y -F ~/b.md',
                        'gh pr create -t "retries = 3?" --body "a\\nb"'):
            with self.subTest(command=command):
                self.taken_back(self.hook(command, pr=pr, output=pr["url"]), "good")

    def test_a_file_sourced_through_builtin_or_command_is_hidden(self):
        self.deferred()
        seven, eight = self.pr(7), self.pr(8)
        for hidden in ("builtin source ./x.sh", "command . ./x.sh", "exec . ./x.sh",
                       ". x.sh", "source x.sh", "my-gh foo"):
            with self.subTest(hidden=hidden):
                self.allowed(self.hook("gh pr create -t x >/dev/null; " + hidden,
                                       output=self.READY_8, extra_env=self.prs(seven, eight)))
        self.assertEqual(self.calls(), [])

    def test_a_selector_of_digits_outside_ascii_does_not_crash(self):
        self.deferred()
        pr = self.pr()
        r = self.hook("gh pr ready ²", output=self.READY_7, extra_env=self.prs(pr))
        self.assertIn(r.returncode, (0, 2), r.stderr)
        self.assertNotIn("Traceback", r.stderr)


class FoundByBugHunterHandbackRun5Tests(FoundByBugHunterHandbackRun4Tests):
    """Bug-hunter's fifth run, over plain_words' shlex fallback and the check
    for a command that sources a file."""

    def test_a_file_sourced_after_a_prefix_s_option_or_by_trap_is_not_judged(self):
        self.deferred()
        seven, eight = self.pr(7), self.pr(8)
        for hidden in ("command -p . ./x.sh", "builtin -- . ./x.sh", "time -p . ./x.sh",
                       "command -- . ./x.sh", "- . ./x.sh", "exec -a x . ./x.sh",
                       "trap '. ./x.sh' EXIT"):
            with self.subTest(hidden=hidden):
                self.noted(self.hook("gh pr edit --add-reviewer adam >/dev/null; " + hidden,
                                       output=self.READY_8, extra_env=self.prs(seven, eight)), "because")
        self.assertEqual(self.calls(), [])

    def test_a_carriage_return_is_part_of_a_word(self):
        self.deferred()
        pr = self.pr()
        self.allowed(self.hook("gh pr edit 7 --title x\r--add-reviewer\radam", pr=pr,
                               output=pr["url"]))
        self.assertEqual(self.undos(), [])

    def test_the_fallback_refuses_what_the_shell_reads_otherwise(self):
        sys.path.insert(0, str(HERE))
        import handback
        for source in ('gh pr ready "fix\\$x"', 'gh pr ready "fix\\`x"',
                       'gh pr ready 7 -R "o/r\\$"', "gh pr edit 7 --add-reviewer ~adam",
                       "gh pr ready ~+", "gh pr ready ~", "gh pr create -t x -b y\r--draft"):
            with self.subTest(source=source):
                self.assertIsNone(handback.plain_words(source))
        self.assertEqual(handback.plain_words("gh pr create -F ~/b.md")[-1][0], "~/b.md")


class FoundByBugHunterHandbackRun5Iteration2Tests(FoundByBugHunterHandbackRun4Tests):
    """Bug-hunter's fifth run, second iteration."""

    def test_space_shlex_keeps_in_a_word_does_not_stop_the_fallback(self):
        sys.path.insert(0, str(HERE))
        import handback
        for space in (" ", "\f", "\v", " ", " "):
            with self.subTest(space=repr(space)):
                words = handback.plain_words(f'gh pr edit 5 --body "say \\"hi\\"{space}there"')
                self.assertEqual(words[-1][0], f'say "hi"{space}there')
        self.assertEqual(handback.plain_words('gh pr edit 5 --body "a\rb\\"c"')[-1][0], 'a\rb"c')

    def test_a_prefix_spelled_with_zsh_s_equals_is_not_judged(self):
        self.deferred()
        seven, eight = self.pr(7), self.pr(8)
        for hidden in ("=command . ./x.sh", "=builtin source ./x.sh"):
            with self.subTest(hidden=hidden):
                self.noted(self.hook("gh pr edit --add-reviewer adam >/dev/null; " + hidden,
                                       output=self.READY_8, extra_env=self.prs(seven, eight)), "because")
        self.assertEqual(self.calls(), [])

    def test_a_shell_named_inside_a_word_env_splits_is_not_judged(self):
        self.deferred()
        seven, eight = self.pr(7), self.pr(8)
        self.noted(self.hook('gh pr edit --add-reviewer adam >/dev/null; env -S "bash ./x.sh"',
                               output=self.READY_8, extra_env=self.prs(seven, eight)), "because")
        self.assertEqual(self.calls(), [])

    def test_a_tilde_after_an_equals_sign_is_refused(self):
        sys.path.insert(0, str(HERE))
        import handback
        self.assertIsNone(handback.plain_words('gh pr edit 5 x=~root --body "a\\"b"'))


class FoundByBugHunterHandbackRun5Iteration3Tests(FoundByBugHunterHandbackRun4Tests):
    """Bug-hunter's fifth run, third iteration."""

    def test_env_splitting_a_string_or_running_a_variable_is_not_judged(self):
        self.deferred()
        seven, eight = self.pr(7), self.pr(8)
        for hidden in ("env -S'bash ./x.sh'", 'env -S"bash ./x.sh"', "env -iS'bash ./x.sh'",
                       "env -S'bash\\_./x.sh'", "env --split-string='bash ./x.sh'",
                       'env "$X"', 'env -S"$X"'):
            with self.subTest(hidden=hidden):
                self.noted(self.hook("gh pr edit --add-reviewer adam >/dev/null; " + hidden,
                                       output=self.READY_8, extra_env=self.prs(seven, eight)), "because")
        self.assertEqual(self.calls(), [])

    def test_a_tilde_after_a_colon_is_refused(self):
        sys.path.insert(0, str(HERE))
        import handback
        self.assertIsNone(handback.plain_words('gh pr edit 5 --title "é" --add-reviewer x=a:~root'))




class HandbackAllowlistTests(HandbackBase):
    """After the call, only the forms on the allowlist are judged; a hand-back
    in any other form is given a note and left to the workflow."""

    def test_a_hand_back_beside_only_listed_programs_is_judged(self):
        self.deferred()
        pr = self.pr()
        for command in ("git push && gh pr create -t x", "cd repo && gh pr ready {n}",
                        "git push; sleep 1; gh pr ready {n} && echo done",
                        "printf x; true && gh pr ready {n}",
                        "cd ~/repo && gh pr ready {n}"):
            command = command.format(n=pr["number"])
            with self.subTest(command=command):
                self.taken_back(self.hook(command, pr=pr, output=pr["url"]), "good")

    def test_a_program_not_listed_is_named_in_the_note(self):
        self.deferred()
        pr = self.pr()
        for command, program in (("timeout 60 gh pr ready 7", "timeout"),
                                 ("gh pr create -t x | tee log", "tee"),
                                 ("gh pr create -t x; false", "false"),
                                 ("if gh pr create -t x; then echo ok; fi", "fi"),
                                                                  ("bash -c 'gh pr create -t x'", "bash"),
                                 ("npm test && gh pr create -t x", "npm")):
            with self.subTest(command=command):
                self.noted(self.hook(command, pr=pr, output=pr["url"]),
                           f"`{program}` is not one of the programs listed")

    def test_an_expanding_word_is_quoted_in_the_note(self):
        self.deferred()
        pr = self.pr()
        for command, word in (("gh pr create -t \"$TITLE\"", '"$TITLE"'),
                              ("gh pr edit 7 --add-reviewer={adam,bob}",
                               "--add-reviewer={adam,bob}"),
                              ("gh pr create -t *.md", "*.md")):
            with self.subTest(command=command):
                self.noted(self.hook(command, pr=pr, output=pr["url"]),
                           f"the word `{word}` expands")

    def test_a_brace_group_is_not_judged(self):
        self.deferred()
        pr = self.pr()
        self.noted(self.hook("{ gh pr create -t x; }", pr=pr, output=pr["url"]),
                   "the word `}` expands")

    def test_an_assignment_or_a_second_gh_call_is_named_in_the_note(self):
        self.deferred()
        pr = self.pr()
        for command, reason in (("FOO=1 git push && gh pr create -t x",
                                 "`FOO=1` assigns a variable"),
                                ("gh pr checks 7 && gh pr ready 7",
                                 "the command runs 2 gh calls")):
            with self.subTest(command=command):
                self.noted(self.hook(command, pr=pr, output=pr["url"]), reason)

    def test_a_command_the_reader_cannot_read_still_gets_the_note(self):
        self.deferred()
        pr = self.pr()
        self.noted(self.hook("echo $(gh pr create -t x)", pr=pr, output=pr["url"]),
                   "expands")

    def test_cursor_gets_the_note_as_additional_context(self):
        self.deferred()
        pr = self.pr()
        self.noted(self.hook("timeout 60 gh pr ready 7", pr=pr, output=pr["url"],
                             host="cursor"), "`timeout`", host="cursor")

    def test_the_note_names_the_event_it_answers(self):
        self.deferred()
        pr = self.pr()
        payload = {"tool_name": "Bash", "tool_input": {"command": "timeout 9 gh pr ready 7"},
                   "cwd": str(self.repo.path), "hook_event_name": "PostToolUseFailure",
                   "error": "Exit code 1"}
        out = self.noted(self.run_hook(payload, pr=pr), "`timeout`")
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUseFailure")

    def test_no_note_without_a_hand_back(self):
        self.deferred()
        pr = self.pr()
        for command in ("timeout 60 gh pr view 7", "npm test | tee log",
                        "FOO=1 make $TARGET", "gh pr checks 7 && gh pr view 7",
                        "gh pr create -t x --draft | tee log",
                        "git commit -m 'gh pr create later' && npm test",
                        "echo $(gh pr view 7)"):
            with self.subTest(command=command):
                r = self.hook(command, pr=pr, output=pr["url"])
                self.allowed(r)
                self.assertEqual(r.stdout, "")

    def test_no_note_before_the_call(self):
        self.deferred()
        pr = self.pr()
        r = self.hook("timeout 60 gh pr ready 7", pr=pr)
        self.allowed(r)
        self.assertEqual(r.stdout, "")



class FoundByBugHunterHandbackRun6Tests(HandbackBase):
    """Bug-hunter's sixth run, over the post-call allowlist and its note."""

    READY = '\u2713 Pull request o/r#{n} is marked as "ready for review"\n'

    def other(self, pr):
        """The same pull request number in a second repository."""
        other = self.tmp / "other"
        subprocess.run(["git", "init", "-q", "--bare", str(other)], check=True, env=ENV)
        self.repo.git("push", "-q", str(other), "main", "spec:spec",
                      f"spec:refs/pull/{pr['number']}/head")
        return dict(pr, url=f"{other}/pull/{pr['number']}")

    def env(self, *prs):
        found = {}
        for pr in prs:
            found.setdefault(str(pr["number"]), pr)
            found[pr["url"]] = pr
        return {"FAKE_PRS": json.dumps(found)}

    def test_another_repository_s_pull_request_with_the_same_number_is_not_taken_back(self):
        self.deferred()
        seven = self.pr(7)
        other = self.other(seven)
        r = self.hook(f"echo {other['url']}; gh pr ready 7 -R o/r",
                      output=other["url"] + "\n" + self.READY.format(n=7),
                      extra_env=self.env(seven, other))
        self.assertNotIn(other["url"], json.dumps(self.undos()))
        self.assertNotEqual(r.returncode, 2, r.stderr)

    def test_a_url_echo_prints_is_not_taken_for_the_hand_back_s(self):
        self.deferred()
        seven = self.pr(7)
        other = self.other(seven)
        payload = {"tool_name": "Bash",
                   "tool_input": {"command": f"echo {other['url']} && git push; gh pr create -t x"},
                   "cwd": str(self.repo.path), "hook_event_name": "PostToolUseFailure",
                   "error": other["url"] + "\nmust first push the current branch\n"}
        r = self.run_hook(payload, extra_env=self.env(seven, other))
        self.assertEqual(self.undos(), [])
        self.assertNotEqual(r.returncode, 2, r.stderr)

    def test_an_indented_url_or_state_line_is_not_gh_s(self):
        self.deferred()
        seven = self.pr(7)
        other = self.other(seven)
        for printed in ("    " + other["url"] + "\n",
                        "    fix: " + self.READY.format(n=7)):
            with self.subTest(printed=printed):
                r = self.hook("git log -1 && gh pr create -t x", output=printed,
                              extra_env=self.env(seven, other))
                self.assertEqual(self.undos(), [])
                self.assertNotEqual(r.returncode, 2, r.stderr)

    def test_printf_assigning_a_variable_is_not_judged(self):
        self.deferred()
        seven = self.pr(7)
        r = self.hook("printf -v 'a[$(gh pr ready 9 >&2)]' x; gh pr create -t x",
                      output=seven["url"] + "\n", extra_env=self.env(seven))
        self.assertEqual(self.undos(), [])
        self.assertIn("printf -v", r.stdout)

    def test_gh_run_by_its_path_gets_the_note(self):
        self.deferred()
        seven = self.pr(7)
        r = self.hook("/opt/homebrew/bin/gh pr ready 7", output=self.READY.format(n=7),
                      extra_env=self.env(seven))
        self.assertEqual(self.undos(), [])
        self.assertIn("did not check this hand-back", r.stdout)
        self.assertIn("/opt/homebrew/bin/gh", r.stdout)

    def test_a_count_flag_is_not_a_shell_command(self):
        self.deferred()
        seven = self.pr(7)
        for command in ("grep -c 'gh pr ready 7' notes.txt", "rg -c 'gh pr create' ."):
            with self.subTest(command=command):
                r = self.hook(command, output="3\n", extra_env=self.env(seven))
                self.assertEqual(r.stdout, "")
        r = self.hook("bash -c 'gh pr create -t x'", output=seven["url"] + "\n",
                      extra_env=self.env(seven))
        self.assertIn("did not check this hand-back", r.stdout)

    def test_a_single_quoted_dollar_is_not_named_as_expanding(self):
        self.deferred()
        seven = self.pr(7)
        r = self.hook("echo 'a $b' <(true); gh pr create -t x", output=seven["url"] + "\n",
                      extra_env=self.env(seven))
        self.assertNotIn("`a $b` expands", r.stdout)



class FoundByBugHunterHandbackRun6Iteration2Tests(FoundByBugHunterHandbackRun6Tests):
    """Bug-hunter's sixth run, second iteration."""

    def test_an_echo_naming_no_pull_request_beside_the_hand_back_is_judged(self):
        self.deferred()
        seven = self.pr(7)
        for command, printed in (
                ("gh pr edit 7 --add-reviewer adam && echo 'Pull request created'",
                 seven["url"] + "\nPull request created\n"),
                ("gh pr ready 7 && echo 'Pull request is ready for review'",
                 self.READY.format(n=7) + "Pull request is ready for review\n")):
            with self.subTest(command=command):
                self.taken_back(self.hook(command, output=printed, extra_env=self.env(seven)),
                                "good")

    def test_an_unquoted_state_line_echo_prints_is_not_judged(self):
        self.deferred()
        seven = self.pr(7)
        r = self.hook("echo Pull request o/r#7 is ready; gh pr create -t x",
                      output="Pull request o/r#7 is ready\n", extra_env=self.env(seven))
        self.assertEqual(self.undos(), [])
        self.assertIn("did not check this hand-back", r.stdout)

    def test_a_command_shlex_cannot_split_still_gets_the_note(self):
        self.deferred()
        seven = self.pr(7)
        r = self.hook("gh pr ready 7 && echo 'oops", output=self.READY.format(n=7),
                      extra_env=self.env(seven))
        self.assertEqual(self.undos(), [])
        self.assertIn("did not check this hand-back", r.stdout)

    def test_gh_s_coloured_ready_line_is_read(self):
        self.deferred()
        seven = self.pr(7)
        for line in ('\x1b[0;32m\u2713\x1b[0m Pull request o/r#7 is marked as "ready for review"\n',
                     '\x1b[0;33m!\x1b[0m Pull request o/r#7 is already "ready for review"\n'):
            with self.subTest(line=line):
                self.taken_back(self.hook("gh pr ready 7", output=line,
                                          extra_env=self.env(seven)), "good")

    def test_the_existing_pull_request_in_crlf_output_is_not_taken_back(self):
        self.deferred()
        seven = self.pr(7)
        payload = {"tool_name": "Bash", "tool_input": {"command": "gh pr create -t x"},
                   "cwd": str(self.repo.path), "hook_event_name": "PostToolUseFailure",
                   "error": 'a pull request for branch "spec" into branch "main" already '
                            f'exists:\r\n{seven["url"]}\r\n'}
        self.allowed(self.run_hook(payload, extra_env=self.env(seven)))
        self.assertEqual(self.undos(), [])



class HandbackUnnamedTests(FoundByBugHunterHandbackRun6Tests):
    """Beside a hand-back that names no pull request, only git push, git add,
    git commit, cd, true and sleep may stand."""

    def test_an_unnamed_hand_back_beside_the_narrow_list_is_judged(self):
        self.deferred()
        seven = self.pr(7)
        for command in ("git push && gh pr create -t x",
                        "git add -A && git commit -qm x && git push -u origin spec && "
                        "gh pr create -t x",
                        "cd repo && sleep 1 && true && gh pr create -t x",
                        "git push && gh pr ready",
                        "git push && gh pr edit --add-reviewer adam"):
            with self.subTest(command=command):
                self.taken_back(self.hook(command, output=seven["url"] + "\n",
                                          extra_env=self.env(seven)), "good")

    def test_an_unnamed_hand_back_beside_anything_else_gets_the_narrow_note(self):
        self.deferred()
        seven = self.pr(7)
        for command, beside in (("echo 'Opening' && gh pr create -t x", "echo 'Opening'"),
                                ("printf x && gh pr create -t x", "printf x"),
                                ("git show -s --format=%b && gh pr create -t x",
                                 "git show -s --format=%b"),
                                ("git -c alias.x=y x && gh pr create -t x",
                                 "git -c alias.x=y x"),
                                ("git rebase -x true HEAD~1; gh pr ready spec",
                                 "git rebase -x true HEAD~1"),
                                ("git && gh pr create -t x", "git")):
            with self.subTest(command=command):
                r = self.hook(command, output=seven["url"] + "\n", extra_env=self.env(seven))
                self.noted(r, f"`{beside}` stands beside a hand-back that names no pull request")
                self.assertIn("only git push, git add, git commit, cd, true or sleep", r.stdout)

    def test_a_hand_back_naming_its_number_or_url_keeps_the_wide_list(self):
        self.deferred()
        seven = self.pr(7)
        for command in ("echo 'Opening' && gh pr ready 7",
                        "git log -1 && gh pr edit 7 --add-reviewer adam",
                        f"printf x && gh pr ready {seven['url']}"):
            with self.subTest(command=command):
                self.taken_back(self.hook(command, output=self.READY.format(n=7),
                                          extra_env=self.env(seven)), "good")

    def test_a_wide_list_break_gets_the_wide_note(self):
        self.deferred()
        seven = self.pr(7)
        r = self.hook("npm test && gh pr create -t x", output=seven["url"] + "\n",
                      extra_env=self.env(seven))
        self.noted(r, "`npm` is not one of the programs listed")
        self.assertNotIn("only git push, git add", r.stdout)



class FoundByBugHunterHandbackRun7Tests(FoundByBugHunterHandbackRun6Tests):
    """Bug-hunter's seventh run, over the narrower list beside an unnamed
    hand-back."""

    def test_a_git_option_that_prints_a_diff_or_runs_a_command_is_off_the_narrow_list(self):
        self.deferred()
        seven = self.pr(7)
        for command in ("git add -p; gh pr edit feature --add-reviewer bob",
                        "git commit --dry-run -v; gh pr ready feature",
                        "git commit -v -m x && gh pr create -t x -r bob",
                        "git push --receive-pack=x ../b.git HEAD:x; gh pr ready",
                        "git push --exec=x origin; gh pr ready"):
            with self.subTest(command=command):
                r = self.hook(command, output="+Pull request o/r#7 is ready\n",
                              extra_env=self.env(seven))
                self.assertEqual(self.undos(), [])
                self.assertIn("names no pull request", r.stdout)

    def test_a_value_in_a_short_cluster_is_read_as_git_reads_it(self):
        sys.path.insert(0, str(HERE))
        import handback
        self.assertTrue(handback.on_unnamed_list(["git", "commit", "-am", "--bogus"]))
        self.assertFalse(handback.on_unnamed_list(["git", "commit", "-mx", "--bogus"]))

    def test_commit_takes_no_bare_double_dash_beside_an_unnamed_hand_back(self):
        sys.path.insert(0, str(HERE))
        import handback
        self.assertFalse(handback.on_unnamed_list(["git", "commit", "--", "path"]))
        self.assertTrue(handback.on_unnamed_list(["git", "add", "--", "path"]))

    def test_plain_git_options_beside_an_unnamed_hand_back_are_judged(self):
        self.deferred()
        seven = self.pr(7)
        for command in ("git add -A && git commit -qm 'fix: x' && git push -u origin spec && "
                        "gh pr create -t x",
                        "git add . && git commit -am x -s && git push --force-with-lease && "
                        "gh pr ready",
                        "git commit --amend --no-edit && git push -f origin spec && "
                        "gh pr create -t x",
                        "git commit -m '-x' -F msg.txt && git push && gh pr create -t x"):
            with self.subTest(command=command):
                self.taken_back(self.hook(command, output=seven["url"] + "\n",
                                          extra_env=self.env(seven)), "good")


class PassDueTests(unittest.TestCase):
    """The commit hook prints `current-state pass due for: ...` for a commit
    that adds a src/ file on a branch with an open change (gate two), and for
    one that archives a change (SKILL.md, *Current-state passes*)."""

    def setUp(self):
        self.repo = Repo(self)
        self.hook()  # settles the cursor past the base commit

    def hook(self):
        return subprocess.run(["sh", str(HOOK), "--host", "claude"],
                              input=json.dumps({"cwd": str(self.repo.path)}),
                              capture_output=True, text=True, cwd=self.repo.path, env=ENV)

    def commit(self, message, *paths):
        for rel in paths:
            self.repo.write(rel, "x\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", message, "--trailer", "Spec-check: skipped (test)")

    def spec_branch(self):
        self.repo.git("checkout", "-q", "-b", "spec")
        self.repo.change("good")
        self.repo.write("openspec/changes/good/design.md", "## Decisions\n\nNone.\n")
        self.commit("Add the spec")
        self.hook()

    def pass_due(self, sha="HEAD"):
        return self.repo.run("pass-due", sha, "--base", "main")

    def test_new_src_files_on_a_spec_branch_start_a_pass(self):
        self.spec_branch()
        self.commit("Build it", "src/store.py", "packages/web/src/view.ts")
        r = self.hook()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("current-state pass due for: openspec/changes/good/proposal.md, "
                      "openspec/changes/good/design.md, and the pull request's body and title. "
                      "The implementation is on the branch of the open change good "
                      "(packages/web/src/view.ts, src/store.py added)", r.stderr)
        self.assertNotIn("without a Spec-check: trailer", r.stderr)

    def test_an_edited_src_file_or_a_branch_without_its_own_change_starts_none(self):
        self.spec_branch()
        self.repo.write("src/app.py", "changed\n")
        self.commit("Edit only")
        self.assertEqual(self.pass_due().stdout, "")
        # A change already on main is not this branch's.
        self.repo.git("checkout", "-q", "main")
        self.repo.git("merge", "-q", "--ff-only", "spec")
        self.repo.git("checkout", "-q", "-b", "impl")
        self.commit("Build elsewhere", "src/new.py")
        self.assertEqual(self.pass_due().stdout, "")
        # On main itself, every open change counts, as spec_check.py sign
        # counts them.
        self.repo.git("checkout", "-q", "main")
        self.commit("Build on main", "src/main.py")
        self.assertIn("open change good", self.pass_due().stdout)

    def test_no_open_change_means_no_pass(self):
        self.repo.git("checkout", "-q", "-b", "code")
        self.commit("Build", "src/new.py")
        self.assertEqual(self.pass_due().stdout, "")
        self.assertEqual(self.hook().returncode, 0)

    def test_an_archive_commit_starts_the_decisions_fold(self):
        self.spec_branch()
        (self.repo.path / "openspec/changes/archive").mkdir()
        self.repo.git("mv", "openspec/changes/good", "openspec/changes/archive/2026-11-06-good")
        self.repo.git("commit", "-q", "-m", "Archive good", "--trailer",
                      "Spec-check: skipped (test)")
        r = self.hook()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("current-state pass due for: the DECISIONS.md of each skill the change "
                      "good affects. It is archived as openspec/changes/archive/2026-11-06-good: "
                      "fold its reasoning into those files, rewriting older reasoning rather "
                      "than appending to it, then run prose check on each and compact any it "
                      "reports as due.", r.stderr)

    def test_an_amended_commit_says_its_pass_once(self):
        self.spec_branch()
        self.commit("Build it", "src/store.py")
        self.repo.git("commit", "-q", "--amend", "-m", "Build it again", "--trailer",
                      "Spec-check: skipped (test)")
        r = self.hook()
        self.assertEqual(r.stderr.count("current-state pass due for:"), 1, r.stderr)

    def test_a_commit_then_a_checkout_of_main_judges_the_commits_branch(self):
        # Found by bug-hunter: with HEAD back on main, every open change on
        # main counted as the branch's own.
        self.repo.change("other")
        self.commit("An open change on main")
        self.hook()
        self.repo.git("checkout", "-q", "-b", "feature")
        self.commit("Build", "src/a.py")
        self.repo.git("checkout", "-q", "main")
        r = self.hook()
        self.assertNotIn("current-state pass due for:", r.stderr)

    def test_amending_the_pass_into_the_commit_asks_for_it_no_more(self):
        # Found by bug-hunter: the amend still adds src/ against its parent,
        # so the pass just done was asked for again.
        self.spec_branch()
        self.commit("Build it", "src/store.py")
        self.assertIn("current-state pass due for:", self.hook().stderr)
        self.repo.write("openspec/changes/good/proposal.md", "## Why\n\nBuilt.\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "--amend", "--no-edit")
        self.assertNotIn("current-state pass due for:", self.hook().stderr)
        # An amend that adds another src/ file builds more: asked again.
        self.repo.write("src/more.py", "x\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "--amend", "--no-edit")
        self.assertIn("(src/more.py, src/store.py added)", self.hook().stderr)

    def test_a_change_with_no_specs_folder_is_archived_too(self):
        self.repo.git("checkout", "-q", "-b", "spec")
        self.commit("A proposal-only change", "openspec/changes/lone/proposal.md",
                    "openspec/changes/lone/tasks.md")
        (self.repo.path / "openspec/changes/archive").mkdir()
        self.repo.git("mv", "openspec/changes/lone", "openspec/changes/archive/2026-11-06-lone")
        self.commit("Archive lone")
        self.assertIn("the change lone affects", self.pass_due().stdout)

    def test_a_deep_src_path_is_not_read_as_an_archive(self):
        self.spec_branch()
        self.commit("Build deep", "packages/web/src/ui/view.ts")
        out = self.pass_due().stdout
        self.assertIn("(packages/web/src/ui/view.ts added)", out)
        self.assertNotIn("is archived as", out)

    def test_more_than_three_src_files_are_counted_not_listed(self):
        self.spec_branch()
        self.commit("Build three", "src/a.py", "src/b.py", "src/c.py")
        self.assertIn("(src/a.py, src/b.py, src/c.py added)", self.pass_due().stdout)
        self.commit("Build four", "src/d.py", "src/e.py", "src/f.py", "src/g.py")
        self.assertIn("(src/d.py, src/e.py, src/f.py and 1 more added)", self.pass_due().stdout)

    def test_amending_the_decisions_fold_into_an_archive_asks_no_more(self):
        # Found by bug-hunter: the amend still adds the archive folder.
        self.spec_branch()
        (self.repo.path / "openspec/changes/archive").mkdir()
        self.repo.git("mv", "openspec/changes/good", "openspec/changes/archive/2026-11-06-good")
        self.commit("Archive good")
        self.assertIn("the change good affects", self.hook().stderr)
        self.repo.write("DECISIONS.md", "Folded.\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "--amend", "--no-edit")
        self.assertNotIn("current-state pass due for:", self.hook().stderr)

    def test_a_commit_pushed_to_main_from_another_branch_counts_as_main(self):
        # Found by bug-hunter: the push moved origin/main to the commit
        # while local main lagged, so the commit looked like nobody's.
        self.repo.change("good")
        self.commit("An open change on main")
        remote = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-remote-")).resolve()
        self.addCleanup(shutil.rmtree, remote, ignore_errors=True)
        self.repo.git("init", "-q", "--bare", str(remote))
        self.repo.git("remote", "add", "origin", str(remote))
        self.repo.git("push", "-q", "origin", "main")
        self.repo.git("fetch", "-q", "origin")
        self.repo.git("checkout", "-q", "-b", "direct", "origin/main")
        self.commit("Build on main", "src/a.py")
        self.repo.git("push", "-q", "origin", "HEAD:main")
        self.repo.git("fetch", "-q", "origin")
        r = self.repo.run("pass-due", "HEAD", "--base", "origin/main")
        self.assertIn("open change good", r.stdout)

    def test_amending_the_change_into_a_code_commit_starts_the_pass(self):
        # Found by bug-hunter: the amend filter dropped src/ files the replaced
        # commit held, though that commit, made before the branch had an open
        # change, started no pass.
        self.repo.git("checkout", "-q", "-b", "feat")
        self.commit("Build first", "src/a.py")
        self.assertNotIn("current-state pass due for:", self.hook().stderr)
        self.repo.change("good")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "--amend", "--no-edit")
        self.assertIn("open change good", self.hook().stderr)

    def test_an_amend_that_drops_a_src_file_asks_no_more(self):
        # Found by bug-hunter: the shown file list changed, so the whole pass
        # was asked for again.
        self.spec_branch()
        self.commit("Build it", "src/a.py", "src/b.py")
        self.assertIn("current-state pass due for:", self.hook().stderr)
        self.repo.git("rm", "-q", "src/b.py")
        self.repo.git("commit", "-q", "--amend", "--no-edit")
        self.assertNotIn("current-state pass due for:", self.hook().stderr)

    def test_an_amend_after_landing_on_main_still_asks_for_mains_changes(self):
        # Found by bug-hunter: the replaced commit was judged as on main, so
        # main's other open change looked asked for, though its own hook,
        # on the branch, never printed it.
        self.repo.change("other")
        self.commit("An open change on main")
        self.spec_branch()
        self.commit("Build it", "src/a.py")
        self.assertNotIn("open change other", self.hook().stderr)
        self.repo.git("checkout", "-q", "main")
        self.repo.git("merge", "-q", "--ff-only", "spec")
        self.repo.write("openspec/changes/good/proposal.md", "## Why\n\nBuilt.\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "--amend", "--no-edit")
        self.assertIn("open change other", self.hook().stderr)

    def test_an_amend_with_nothing_older_in_the_reflog_is_judged_alone(self):
        self.spec_branch()
        self.commit("Build it", "src/a.py")
        self.repo.git("reflog", "expire", "--expire=now", "--all")
        self.repo.git("commit", "-q", "--amend", "-m", "Build it again")
        self.assertIn("open change good", self.pass_due().stdout)

    def test_a_short_id_or_head_reads_the_amend_as_the_full_id_does(self):
        # Found by bug-hunter: the reflog names commits in full, so `HEAD`
        # or a short id never matched an amend.
        self.spec_branch()
        self.commit("Build it", "src/a.py")
        self.repo.git("rm", "-q", "--cached", "src/a.py")
        self.repo.git("add", "-A")
        self.repo.write("openspec/changes/good/proposal.md", "## Why\n\nBuilt.\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "--amend", "--no-edit")
        short = self.repo.git("rev-parse", "--short", "HEAD")
        for ref in ("HEAD", short):
            with self.subTest(ref=ref):
                self.assertEqual(self.pass_due(ref).stdout, "")

    def test_amending_a_commit_made_on_main_asks_no_more(self):
        # Found by bug-hunter: the replaced commit was judged as on a branch,
        # so main's open changes looked unasked and were asked again.
        self.repo.change("good")
        self.commit("An open change on main")
        self.hook()
        self.commit("Build on main", "src/a.py")
        self.assertIn("open change good", self.hook().stderr)
        self.repo.write("src/a.py", "more\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "--amend", "--no-edit")
        self.assertNotIn("current-state pass due for:", self.hook().stderr)

    def test_moving_an_existing_archive_folder_starts_no_pass(self):
        # Archiving deletes the change's folder; moving archive folders that
        # already exist deletes none, so it is not archiving.
        # docs/old/old ends in "old", the name in archive/2026-01-01-old, but
        # it is no change folder: only a deletion under openspec/changes/
        # pairs with an archive.
        self.repo.write("docs/old/old/proposal.md", GOOD_PROPOSAL)
        self.repo.write("openspec/changes/archive/2026-01-02-archive/proposal.md",
                        GOOD_PROPOSAL)
        self.commit("Keep old archives")
        self.hook()
        self.repo.git("mv", "docs/old/old",
                      "openspec/changes/archive/2026-01-01-old")
        self.repo.git("mv", "openspec/changes/archive/2026-01-02-archive",
                      "openspec/changes/archive/2026-01-03-archive")
        self.commit("Move the archives")
        self.assertNotIn("is archived as", self.hook().stderr)
        self.assertEqual(self.pass_due().stdout, "")

    def test_a_change_named_with_a_date_is_archived_under_its_own_name(self):
        # Found by bug-hunter: `openspec archive` adds no second date to a
        # name that starts with one. Stripping the date from the archive
        # folder left "dated", which matched no deleted change folder.
        self.repo.change("2026-01-01-dated")
        self.commit("Add the change")
        self.hook()
        (self.repo.path / "openspec/changes/archive").mkdir()
        self.repo.git("mv", "openspec/changes/2026-01-01-dated",
                      "openspec/changes/archive/2026-01-01-dated")
        self.commit("Archive it")
        self.assertIn("the change 2026-01-01-dated affects. It is archived as "
                      "openspec/changes/archive/2026-01-01-dated:", self.hook().stderr)

    def test_deleting_a_change_archives_nothing_outside_the_archive(self):
        # Only a folder under openspec/changes/archive/ pairs with a deleted
        # change. Both added paths below have "ui" as their fourth part, the
        # position the archive folder's name is read from, but neither is
        # under archive/: one is deep in packages/, one inside change new.
        self.repo.change("ui")
        self.commit("Add ui")
        self.hook()
        self.repo.git("rm", "-rq", "openspec/changes/ui")
        self.repo.change("new")
        self.commit("Drop ui", "packages/web/src/ui/view.ts",
                    "openspec/changes/new/ui/notes.md")
        self.assertNotIn("is archived as", self.pass_due().stdout)

    def test_a_handed_back_pull_request_gets_the_notice_in_ci(self):
        self.spec_branch()
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-ci-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        def ci(action):
            event = tmp / "event.json"
            event.write_text(json.dumps({"action": action, "pull_request": {
                "html_url": "https://github.com/o/r/pull/7", "draft": False,
                "head": {"sha": self.repo.git("rev-parse", "HEAD")},
                "base": {"ref": "main"}}}))
            return self.repo.run("ci", "--event", str(event))
        # The change is unread: the hand-back is taken back, so no pass yet.
        self.assertNotIn("current-state pass due for:", ci("ready_for_review").stdout)
        self.repo.write("openspec/changes/good/tasks.md", TASKS + "- [ ] 1.2 More\n")
        self.repo.git("add", "-A")
        signed_commit(self, self.repo)
        r = ci("ready_for_review")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("::notice::current-state pass due for: each doc the pull request "
                      "changes, and its body and title.", r.stdout)
        self.assertNotIn("current-state pass due for:", ci("synchronize").stdout)


if __name__ == "__main__":
    unittest.main()

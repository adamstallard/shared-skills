#!/usr/bin/env python3
"""Tests for spec_check.py and spec-check's commit hook.

Standard library only:

    python3 test_spec_check.py

Each test builds a throwaway git repository in a temp directory, so nothing
here touches a real repository. Tests that need the OpenSpec CLI skip when it
is not on PATH.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "spec_check.py"
HOOK = HERE / "check-commit-trailer.sh"
PROPOSAL_HOOK = HERE / "proposal-hook.sh"
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
HAS_OPENSPEC = shutil.which("openspec") is not None

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

GOOD_PROPOSAL = """## Decisions

1. **Records expire.** *Rejected:* keeping them forever.

**Still open:** nothing.

## Why

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
    """A throwaway repository with one main spec and a ten-line source file.
    It enforces the decisions-first rule unless the test passes another
    decision, or None for a repository that has not decided."""

    def __init__(self, test, decision="enforce"):
        self.path = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-test-")).resolve()
        test.addCleanup(shutil.rmtree, self.path, ignore_errors=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "commit.gpgsign", "false")
        self.write("openspec/config.yaml", "schema: spec-driven\n")
        if decision is not None:
            self.write("openspec/spec-check.yaml", f"decisions-first: {decision}\n")
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

    def test_a_requirement_without_a_scenario_fails(self):
        self.repo.change("x", delta="## ADDED Requirements\n\n### Requirement: Bare\n\n"
                                    "The store SHALL do a thing.\n")
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(kinds(r), ["no-scenario"])
        self.assertIn("openspec/changes/x/specs/cap/spec.md:3: error [no-scenario]", r.stdout)

    def test_a_scenario_without_then_fails(self):
        self.repo.change("x", delta=GOOD_DELTA.replace("- **THEN** it is deleted\n", ""))
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(kinds(r), ["scenario-incomplete"])
        self.assertIn("has no THEN", r.stdout)

    def test_a_scenario_without_when_or_then_names_both(self):
        self.repo.change("x", delta=GOOD_DELTA.replace("- **WHEN** a record has not been read for ninety days\n", "")
                         .replace("- **THEN** it is deleted\n", "- it goes\n"))
        r = self.repo.check("x")
        self.assertIn("has no WHEN or THEN", r.stdout)

    def test_a_removed_requirement_needs_no_scenario(self):
        self.repo.change("x", delta=GOOD_DELTA + "\n## REMOVED Requirements\n\n### Requirement: Old\n\n"
                                                 "**Reason**: gone. The store MUST NOT do it.\n")
        self.assertEqual(kinds(self.repo.check("x")), [])

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

    def test_a_proposal_without_a_decisions_section_fails(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.split("## Why", 1)[1].join(["## Why", ""]))
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(kinds(r), ["decisions-first"])
        self.assertIn('opens with "Why"', r.stdout)

    def test_a_decision_with_no_rejected_alternative_passes(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
            "1. **Records expire.** *Rejected:* keeping them forever.",
            "1. **Expiry runs nightly.**\n   Once a day is enough."))
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(kinds(r), [])

    def test_a_still_open_list_passes(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
            "**Still open:** nothing.", "**Still open:**\n\n- Whether ninety days is right."))
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_decisions_section_with_no_decisions_fails(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
            "1. **Records expire.** *Rejected:* keeping them forever.\n", "None yet.\n"))
        self.assertEqual(kinds(self.repo.check("x")), ["decisions-first"])

    def test_the_decisions_heading_is_configurable(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("## Decisions", "## Choices for you"))
        self.assertEqual(kinds(self.repo.check("x")), ["decisions-first"])
        r = self.repo.check("x", "--decisions-heading", "Choices")
        self.assertEqual(kinds(r), [])

    def test_a_longer_decisions_heading_matches(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("## Decisions", "## Decisions for the reviewer"))
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_branch_is_checked_without_checking_it_out(self):
        self.repo.git("checkout", "-q", "-b", "spec/x")
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("## Decisions", "## Why not"))
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "spec")
        self.repo.git("checkout", "-q", "main")
        self.assertFalse((self.repo.path / "openspec/changes/x").exists())
        r = self.repo.check("--ref", "spec/x", "x")
        self.assertEqual(kinds(r), ["decisions-first"])
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
        self.assertIn("openspec validate --strict (good): not run: the openspec CLI is not on PATH",
                      r.stdout, r.stderr)

    @unittest.skipUnless(HAS_OPENSPEC, "openspec CLI not on PATH")
    def test_validate_runs_and_its_issues_are_findings(self):
        self.repo.change("good")
        self.repo.change("bad", delta=GOOD_DELTA.replace("SHALL", "will"))
        r = self.repo.run("check", "--base", "main", "good", "bad")
        self.assertIn("openspec validate --strict (good): passed", r.stdout)
        self.assertIn("openspec-validate", r.stdout)
        self.assertIn("must contain SHALL or MUST", r.stdout)
        self.assertEqual(r.returncode, 1)


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

    def test_a_decision_starting_with_open_is_a_decision(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
            "1. **Records expire.** *Rejected:* keeping them forever.",
            "- **Open registration to everyone.** *Rejected:* invite-only."))
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

    @unittest.skipUnless(HAS_OPENSPEC, "openspec CLI not on PATH")
    def test_a_failed_strict_validation_is_an_error(self):
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace("What cap does.", "Short."))
        r = self.repo.run("check", "--base", "main", "specs")
        self.assertIn("failed", r.stdout)
        self.assertEqual(r.returncode, 1, r.stdout)

    @unittest.skipUnless(HAS_OPENSPEC, "openspec CLI not on PATH")
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
                        "## ADDED Requirements\n" + MAIN_SPEC.split("## Requirements\n", 1)[1]
                        .replace("Records are kept", "Records are retained"))
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_still_open_list_item_ends_the_decisions(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
            "1. **Records expire.** *Rejected:* keeping them forever.\n\n**Still open:** nothing.\n", "- **Still open:** whether archived records expire too.\n"))
        self.assertEqual(kinds(self.repo.check("x")), ["decisions-first"])

    def test_open_items_end_the_decisions(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
            "1. **Records expire.** *Rejected:* keeping them forever.\n\n**Still open:** nothing.\n", "**Open items:**\n\n- Whether archived records expire too.\n"))
        self.assertEqual(kinds(self.repo.check("x")), ["decisions-first"])

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

    @unittest.skipUnless(HAS_OPENSPEC, "openspec CLI not on PATH")
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

    def test_a_decision_about_open_issues_is_a_decision(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
            "1. **Records expire.** *Rejected:* keeping them forever.",
            "1. **Open issues close after ninety days.** *Rejected:* never closing them."))
        self.assertEqual(kinds(self.repo.check("x")), [])

    @unittest.skipUnless(HAS_OPENSPEC, "openspec CLI not on PATH")
    def test_sign_a_commit_that_deletes_openspec_runs_no_validation(self):
        self.repo.git("rm", "-rq", "openspec")
        r = self.repo.run("sign", "--read", "self", "--base", "main")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no open change or spec staged", r.stdout)


class FoundByScopedRunTests(unittest.TestCase):
    """Fences inside the decisions section, the "still open" label's styles,
    quoted stack traces and image names, and citations of files the change
    adds. bug-hunter found each of these."""

    def setUp(self):
        self.repo = Repo(self)

    def proposal(self, decisions):
        return GOOD_PROPOSAL.replace(
            "1. **Records expire.** *Rejected:* keeping them forever.\n\n**Still open:** nothing.\n",
            decisions)

    def test_a_fence_in_the_decisions_does_not_end_them(self):
        self.repo.change("x", proposal=self.proposal(
            "1. **Purge nightly.** *Rejected:* purging on read. The job:\n\n"
            "```sh\n# nightly purge\npurge --older-than 90d\n```\n\n"
            "2. **Purged records are deleted** (`src/purge.py:3`).\n"))
        self.assertEqual(kinds(self.repo.check("x")), ["citation"])

    def test_a_list_item_in_a_fence_is_not_a_decision(self):
        self.repo.change("x", proposal=self.proposal(
            "The config, for reference:\n\n"
            "```yaml\n- name: primary\n  pool: 10\n```\n"))
        self.assertEqual(kinds(self.repo.check("x")), ["decisions-first"])

    def test_still_open_labels_in_other_styles_end_the_decisions(self):
        for label in ("*Still open:*", "_Still open:_", "### *Still open*",
                      "**Open questions?**", "Still open."):
            with self.subTest(label=label):
                self.repo.change("x", proposal=self.proposal(
                    f"{label}\n\n- Whether archived records expire too.\n"))
                self.assertEqual(kinds(self.repo.check("x")), ["decisions-first"])

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
    underscore-wrapped labels, and dot directories read as hosts.
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

    def test_a_fence_inside_a_longer_fence_does_not_end_the_decisions(self):
        for outer in ("~~~", "````"):
            with self.subTest(outer=outer):
                self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
                    "1. **Records expire.** *Rejected:* keeping them forever.\n",
                    "1. **Ship the snippet.** *Rejected:* linking out.\n\n"
                    f"{outer}markdown\nRun it:\n```\n# build everything\nmake\n```\n{outer}\n\n"
                    "2. **Snippets are tested** (`src/snippets.py:3`).\n"))
                self.assertEqual(kinds(self.repo.check("x")), ["citation"])

    def test_an_underscore_wrapped_label_ends_the_decisions(self):
        for label in ("__Still open__", "_Open questions_", "### _Still open_"):
            with self.subTest(label=label):
                self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
                    "1. **Records expire.** *Rejected:* keeping them forever.\n\n**Still open:** nothing.\n", f"{label}\n\n- Whether archived records expire too.\n"))
                self.assertEqual(kinds(self.repo.check("x")), ["decisions-first"])

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
            "1. **Records expire.** *Rejected:* keeping them forever.\n",
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

    def test_fences_straight_after_decisions_hide_nothing(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
            "1. **Records expire.** *Rejected:* keeping them forever.\n",
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
            "1. **Records expire.** *Rejected:* keeping them forever.\n",
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

    def test_an_undecided_repository_gets_one_more_line(self):
        self.stage_change()
        self.repo.git("commit", "-q", "-m", "Add a spec")
        self.assertNotIn("ask your agent to set up spec-check", self.hook().stderr)
        self.repo.git("rm", "-q", "openspec/spec-check.yaml")
        self.repo.git("commit", "-q", "-m", "Undecide")
        r = self.hook()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stderr.count("ask your agent to set up spec-check in this repository"), 1)

    def test_a_commit_removing_openspec_does_not_ask_for_setup(self):
        self.repo.git("rm", "-rq", "openspec")
        self.repo.git("commit", "-q", "-m", "Drop OpenSpec")
        r = self.hook()
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("ask your agent to set up spec-check", r.stderr)

    def test_a_decision_only_commit_gets_its_trailer_from_sign(self):
        for args in (("setup",), ("setup", "--decline")):
            with self.subTest(args=args):
                self.repo = Repo(self, None)
                self.hook()
                r = self.repo.run(*args)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.repo.git("add", "openspec/")
                r = self.sign()
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                value = r.stdout.strip().splitlines()[-1][len("Spec-check: "):]
                self.assertIn("no open change or spec staged", value)
                r = self.commit_with("--verified-value", str(VERIFY), "Spec-check", value,
                                     message="Settle the decisions-first rule")
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("openspec/spec-check.yaml",
                              self.repo.git("diff", "--name-only", "HEAD~1", "HEAD"))
                self.assertEqual(self.hook().returncode, 0)

    def test_a_commit_outside_openspec_is_never_reported(self):
        self.repo.write("src/other.py", "x\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "Code only")
        r = self.hook()
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_a_signed_commit_is_quiet(self):
        self.stage_change()
        r = self.commit_with("--verified-value", str(VERIFY), "Spec-check", self.value())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.hook().returncode, 0)
        body = self.repo.git("log", "-1", "--format=%B")
        self.assertIn("read by a fresh subagent; 2 amended, 0 open", body)

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

    def test_sign_refuses_a_change_with_errors(self):
        self.stage_change(proposal=GOOD_PROPOSAL.replace("## Decisions", "## Why first"))
        r = self.sign()
        self.assertEqual(r.returncode, 1)
        self.assertIn("decisions-first", r.stdout)
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
        self.assertEqual(commands, ["scripts/check-commit-trailer.sh", "scripts/proposal-hook.sh"])
        for command in commands:
            self.assertTrue(os.access(HERE.parent / command, os.X_OK), command)

    def test_a_sandboxed_install_wires_both_hooks_on_both_hosts(self):
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
        self.assertIn(("^(Write|Edit|MultiEdit)$", "proposal-hook.sh"), wired)
        cursor = json.loads((tmp / "home/.cursor/hooks.json").read_text())["hooks"]
        self.assertTrue(any("check-commit-trailer.sh --host cursor" in h["command"]
                            for h in cursor["postToolUse"]))
        self.assertTrue(any("proposal-hook.sh --host cursor" in h["command"]
                            for h in cursor["postToolUse"] if h.get("matcher") == "Write"))
        r = subprocess.run([sys.executable, str(SKILLS_PY), "doctor"],
                           capture_output=True, text=True, env=env, cwd=tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("No problems found in any target.", r.stdout)
        # The command as wired runs, and speaks in an undecided repository.
        command = next(h["command"] for g in claude["PostToolUse"] for h in g["hooks"]
                       if "proposal-hook.sh" in h["command"])
        repo = Repo(self, None)
        repo.change("x")
        payload = {"tool_name": "Write", "cwd": str(repo.path),
                   "tool_input": {"file_path": str(repo.path / "openspec/changes/x/proposal.md")}}
        r = subprocess.run(command, shell=True, input=json.dumps(payload),
                           capture_output=True, text=True, env=ENV)
        self.assertIn("has not decided", json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])


class DecisionFileTests(unittest.TestCase):
    """openspec/spec-check.yaml: what it says, and what check does with it."""

    BAD = GOOD_PROPOSAL.replace("## Decisions", "## Why first")

    def test_the_states_on_disk(self):
        for text, want in ((None, "undecided"), ("decisions-first: enforce\n", "enforce"),
                           ("decisions-first: off\n", "off"),
                           ("\r\ndecisions-first:   off  \r\n\r\n", "off"),
                           ("decisions-first: on\n", "invalid"), ("", "invalid"),
                           ("decisions-first: enforce\nother: x\n", "invalid"),
                           ("# comment\ndecisions-first: enforce\n", "invalid")):
            with self.subTest(text=text):
                repo = Repo(self, None)
                if text is not None:
                    repo.write("openspec/spec-check.yaml", text)
                self.assertEqual(repo.run("state").stdout.strip(), want)

    def test_no_openspec_is_undecided(self):
        repo = Repo(self, None)
        shutil.rmtree(repo.path / "openspec")
        self.assertEqual(repo.run("state").stdout.strip(), "undecided")

    def test_enforce_makes_it_an_error(self):
        repo = Repo(self, "enforce")
        repo.change("x", proposal=self.BAD)
        r = repo.check("x")
        self.assertEqual((r.returncode, kinds(r)), (1, ["decisions-first"]))

    def test_off_is_not_checked(self):
        repo = Repo(self, "off")
        repo.change("x", proposal=self.BAD)
        r = repo.check("x")
        self.assertEqual((r.returncode, kinds(r)), (0, []), r.stdout)
        self.assertEqual(json.loads(repo.check("x", "--json").stdout)["decisions_first"], "off")

    def test_undecided_gives_one_note_and_no_errors(self):
        repo = Repo(self, None)
        repo.change("x", proposal=self.BAD)
        repo.change("y", proposal="## Why\n\nNo decisions.\n")
        r = repo.check()
        self.assertEqual((r.returncode, kinds(r)), (0, ["decisions-first"]), r.stdout)
        self.assertIn("openspec/spec-check.yaml: check [decisions-first] this repository "
                      "has not decided", r.stdout)
        self.assertIn("setup --decline", r.stdout)
        data = json.loads(repo.check("x", "--json").stdout)
        self.assertEqual((data["decisions_first"], data["errors"], data["checks"]),
                         ("undecided", 0, 1))

    def test_only_specs_get_no_note(self):
        self.assertEqual(kinds(Repo(self, None).check("specs")), [])

    def test_an_invalid_file_gives_one_note_without_setup_advice(self):
        repo = Repo(self, None)
        repo.write("openspec/spec-check.yaml", "decisions-first: yes\n")
        repo.change("x", proposal=self.BAD)
        r = repo.check("x")
        self.assertEqual((r.returncode, kinds(r)), (0, ["decisions-first"]), r.stdout)
        self.assertIn("must hold one line", r.stdout)
        self.assertNotIn("setup", r.stdout)
        self.assertEqual(json.loads(repo.check("x", "--json").stdout)["decisions_first"], "invalid")

    def test_a_link_is_not_followed_on_disk_or_in_a_tree(self):
        repo = Repo(self, None)
        repo.write("shared/sc.yaml", "decisions-first: enforce\n")
        (repo.path / "openspec/spec-check.yaml").symlink_to("../shared/sc.yaml")
        repo.change("x", proposal=self.BAD)
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "linked")
        self.assertEqual(repo.run("state").stdout.strip(), "invalid")
        for args in (("x",), ("--ref", "HEAD", "x")):
            with self.subTest(args=args):
                r = repo.check(*args)
                self.assertEqual((r.returncode, kinds(r)), (0, ["decisions-first"]), r.stdout)
                self.assertIn("is a symlink, not a plain file", r.stdout)

    def test_a_submodule_or_directory_in_a_tree_is_reported(self):
        repo = Repo(self, None)
        repo.write("openspec/spec-check.yaml/x", "y\n")
        repo.change("x", proposal=self.BAD)
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "dir")
        r = repo.check("--ref", "HEAD", "x")
        self.assertIn("is a directory, not a plain file", r.stdout)
        sub = repo.path.parent / f"{repo.path.name}-sub"
        sub.mkdir()
        self.addCleanup(shutil.rmtree, sub, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=sub, check=True, env=ENV)
        (sub / "f").write_text("decisions-first: enforce\n")
        subprocess.run(["git", "add", "-A"], cwd=sub, check=True, env=ENV)
        subprocess.run(["git", "commit", "-q", "-m", "s"], cwd=sub, check=True, env=ENV)
        repo.git("rm", "-rq", "openspec/spec-check.yaml")
        repo.git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub),
                 "openspec/spec-check.yaml")
        repo.git("commit", "-q", "-m", "sub")
        r = repo.check("--ref", "HEAD", "x")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("is a submodule, not a plain file", r.stdout)

    def test_a_branch_is_judged_by_its_own_file(self):
        repo = Repo(self, None)
        repo.git("checkout", "-q", "-b", "spec/x")
        repo.change("x", proposal=self.BAD)
        repo.write("openspec/spec-check.yaml", "decisions-first: enforce\n")
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "x")
        repo.git("checkout", "-q", "main")
        r = repo.check("--ref", "spec/x", "x")
        self.assertEqual((r.returncode, kinds(r)), (1, ["decisions-first"]))

    def test_sign_reads_the_staged_file(self):
        repo = Repo(self, None)
        repo.change("x", proposal=self.BAD)
        repo.git("add", "-A")
        r = repo.run("sign", "--read", "subagent", "--base", "main", "--no-validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 errors, 1 checks", r.stdout)
        repo.write("openspec/spec-check.yaml", "decisions-first: enforce\n")
        r = repo.run("sign", "--read", "subagent", "--base", "main", "--no-validate")
        self.assertEqual(r.returncode, 0, "unstaged, so the staged tree is still undecided")
        repo.git("add", "-A")
        r = repo.run("sign", "--read", "subagent", "--base", "main", "--no-validate")
        self.assertEqual(r.returncode, 1, r.stdout)


class FoundByBugHunterDecisionTests(unittest.TestCase):
    """Regressions found by bug-hunter over the decision file."""

    def setUp(self):
        self.repo = Repo(self, None)
        self.openspec = self.repo.path / "openspec"

    def test_a_link_at_the_temporary_name_is_not_written_through(self):
        outside = self.repo.path.parent / f"{self.repo.path.name}-victim.txt"
        outside.write_text("keep\n")
        self.addCleanup(outside.unlink)
        (self.openspec / "spec-check.yaml.tmp").symlink_to(outside)
        r = self.repo.run("setup")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(outside.read_text(), "keep\n")
        self.assertFalse((self.openspec / "spec-check.yaml").is_symlink())
        self.assertEqual(self.repo.run("state").stdout.strip(), "enforce")

    def test_a_decision_file_linked_out_of_the_repository_is_reported_from_a_tree(self):
        outside = self.repo.path.parent / f"{self.repo.path.name}-out.yaml"
        outside.write_text("decisions-first: enforce\n")
        self.addCleanup(outside.unlink)
        (self.openspec / "spec-check.yaml").symlink_to(f"../../{outside.name}")
        self.repo.change("x")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "linked")
        r = self.repo.check("--ref", "HEAD", "x")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("is a symlink, not a plain file", r.stdout)


class FoundByBugHunterDecisionIteration2Tests(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self, None)
        self.openspec = self.repo.path / "openspec"

    def test_a_ref_whose_openspec_holds_only_the_decision_file(self):
        (self.openspec / "config.yaml").unlink()
        shutil.rmtree(self.openspec / "specs")
        self.repo.write("openspec/spec-check.yaml", "decisions-first: off\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "only the decision")
        r = self.repo.check("--ref", "HEAD")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

class SetupDecisionTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self, None)
        self.decision = self.repo.path / "openspec" / "spec-check.yaml"
        self.config = self.repo.path / "openspec" / "config.yaml"

    def test_setup_writes_enforce_and_never_touches_the_config(self):
        before = self.config.read_bytes()
        r = self.repo.run("setup")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.decision.read_text(), "decisions-first: enforce\n")
        self.assertEqual(self.config.read_bytes(), before)
        self.assertIn("SKILL.md", r.stdout)
        self.assertEqual(self.repo.run("state").stdout.strip(), "enforce")

    def test_decline_writes_off_and_never_touches_the_config(self):
        before = self.config.read_bytes()
        r = self.repo.run("setup", "--decline")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.decision.read_text(), "decisions-first: off\n")
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(self.repo.run("state").stdout.strip(), "off")

    def test_setup_needs_no_config_at_all(self):
        self.config.unlink()
        for args, want in ((("setup",), "enforce"), (("setup", "--decline"), "off")):
            with self.subTest(args=args):
                r = self.repo.run(*args)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(self.decision.read_text(), f"decisions-first: {want}\n")
        self.assertFalse(self.config.exists())

    def test_each_is_idempotent_and_one_switches_the_other(self):
        for args, want in ((("setup",), "enforce"), (("setup",), "enforce"),
                           (("setup", "--decline"), "off"), (("setup", "--decline"), "off"),
                           (("setup",), "enforce")):
            with self.subTest(args=args):
                r = self.repo.run(*args)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(self.decision.read_text(), f"decisions-first: {want}\n")
        self.assertIn("already says", self.repo.run("setup").stdout)

    def test_dry_runs_write_nothing(self):
        for args in (("setup", "--dry-run"), ("setup", "--decline", "--dry-run")):
            with self.subTest(args=args):
                r = self.repo.run(*args)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("--- openspec/spec-check.yaml\ndecisions-first:", r.stdout)
                self.assertFalse(self.decision.exists())

    def test_a_linked_decision_file_is_replaced_by_a_plain_file(self):
        self.repo.write("shared/sc.yaml", "decisions-first: off\n")
        self.decision.symlink_to("../shared/sc.yaml")
        r = self.repo.run("setup")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.decision.is_symlink())
        self.assertEqual(self.decision.read_text(), "decisions-first: enforce\n")
        self.assertEqual((self.repo.path / "shared/sc.yaml").read_text(), "decisions-first: off\n")

    def test_repo_naming_a_subdirectory_writes_the_tops_decision(self):
        nested = self.repo.path / "pkg"
        (nested / "openspec").mkdir(parents=True)
        r = self.repo.run("setup", "--decline", "--repo", str(nested))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.decision.read_text(), "decisions-first: off\n")
        self.assertFalse((nested / "openspec/spec-check.yaml").exists())
        self.assertEqual(self.repo.run("state", "--repo", str(nested)).stdout.strip(), "off")

    def test_no_openspec_refuses(self):
        shutil.rmtree(self.repo.path / "openspec")
        r = self.repo.run("setup")
        self.assertEqual(r.returncode, 2)
        self.assertIn("openspec init", r.stderr)


class ProposalHookTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self, None)
        self.proposal = self.repo.path / "openspec/changes/x/proposal.md"
        self.repo.change("x")

    def run_hook(self, host, payload):
        data = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run(["sh", str(PROPOSAL_HOOK), "--host", host], input=data,
                              capture_output=True, text=True, env=ENV, cwd=tempfile.gettempdir())

    def claude(self, path, tool="Write"):
        return {"hook_event_name": "PostToolUse", "tool_name": tool, "cwd": str(self.repo.path),
                "tool_input": {"file_path": str(path), "content": "x"}}

    def cursor(self, path):
        return {"hook_event_name": "postToolUse", "tool_name": "Write",
                "tool_input": {"file_path": str(path), "contents": "x"},
                "tool_output": "{}", "cwd": str(self.repo.path)}

    def context(self, r, host):
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        if not r.stdout:
            return None
        data = json.loads(r.stdout)
        if host == "claude":
            self.assertEqual(data["hookSpecificOutput"]["hookEventName"], "PostToolUse")
            return data["hookSpecificOutput"]["additionalContext"]
        return data["additional_context"]

    def test_a_proposal_in_an_undecided_repository_adds_context(self):
        for host, payload in (("claude", self.claude(self.proposal)),
                              ("claude", self.claude(self.proposal, "Edit")),
                              ("claude", self.claude(self.proposal, "MultiEdit")),
                              ("cursor", self.cursor(self.proposal))):
            with self.subTest(host=host, payload=payload):
                text = self.context(self.run_hook(host, payload), host)
                self.assertIn("has not decided", text)
                self.assertIn(f"{SCRIPT} setup --repo {self.repo.path}`", text)
                self.assertIn(f"{SCRIPT} setup --repo {self.repo.path} --decline`", text)
                self.assertIn("Before finishing this proposal", text)

    def test_cursor_write_input_may_name_the_path_by_any_known_key(self):
        for key in ("path", "target_file"):
            with self.subTest(key=key):
                payload = self.cursor(self.proposal)
                payload["tool_input"] = {key: str(self.proposal)}
                self.assertIn("has not decided", self.context(self.run_hook("cursor", payload), "cursor"))

    def test_a_relative_path_is_read_from_the_payloads_cwd(self):
        payload = self.claude("openspec/changes/x/proposal.md")
        self.assertIsNotNone(self.context(self.run_hook("claude", payload), "claude"))

    def test_git_is_asked_about_the_directory_holding_openspec(self):
        cases = (("/openspec/changes/x/proposal.md", "/", ["/"]),
                 ("openspec/changes/x/proposal.md", "/", ["/"]),
                 ("/r/openspec/changes/x/proposal.md", "/", ["/r"]),
                 ("openspec/changes/x/proposal.md", "/r", ["/r"]),
                 ("/r/myopenspec/changes/x/proposal.md", "/", []),
                 ("myopenspec/changes/x/proposal.md", "/r", []),
                 ("/r/openspec/changes/archive/2026-01-01-x/proposal.md", "/", []))
        for path, cwd, want in cases:
            asked = []

            def fake_run(cmd, **_):
                asked.append(cmd[2])
                return subprocess.CompletedProcess(cmd, 1, "", "")
            with self.subTest(path=path, cwd=cwd), \
                    mock.patch.object(spec_check.subprocess, "run", fake_run):
                payload = {"cwd": cwd, "tool_input": {"file_path": path}}
                self.assertIsNone(spec_check.proposal_hook_message(payload))
                self.assertEqual(asked, want)

    def test_a_nested_proposal_asks_about_the_repository_top(self):
        nested = self.repo.path / "pkg/openspec/changes/y/proposal.md"
        nested.parent.mkdir(parents=True)
        nested.write_text(GOOD_PROPOSAL)
        text = self.context(self.run_hook("claude", self.claude(nested)), "claude")
        self.assertIn(f"--repo {self.repo.path}`", text)
        self.assertNotIn(f"--repo {self.repo.path / 'pkg'}", text)

    def test_a_nested_proposal_with_no_openspec_at_the_top_is_silent(self):
        shutil.rmtree(self.repo.path / "openspec")
        nested = self.repo.path / "pkg/openspec/changes/y/proposal.md"
        nested.parent.mkdir(parents=True)
        nested.write_text(GOOD_PROPOSAL)
        self.assertIsNone(self.context(self.run_hook("claude", self.claude(nested)), "claude"))

    def test_a_nested_openspec_in_a_decided_repository_is_silent(self):
        self.repo.write("openspec/spec-check.yaml", "decisions-first: enforce\n")
        nested = self.repo.path / "examples/demo/openspec/changes/b/proposal.md"
        nested.parent.mkdir(parents=True)
        nested.write_text(GOOD_PROPOSAL)
        self.assertIsNone(self.context(self.run_hook("claude", self.claude(nested)), "claude"))

    def test_a_decided_repository_is_silent(self):
        for config in ("decisions-first: enforce\n", "decisions-first: off\n", "nonsense\n"):
            self.repo.write("openspec/spec-check.yaml", config)
            for host, payload in (("claude", self.claude(self.proposal)),
                                  ("cursor", self.cursor(self.proposal))):
                with self.subTest(config=config, host=host):
                    self.assertIsNone(self.context(self.run_hook(host, payload), host))

    def test_other_paths_are_silent(self):
        others = [self.repo.path / "openspec/changes/x/design.md",
                  self.repo.path / "openspec/changes/archive/2026-01-01-x/proposal.md",
                  self.repo.path / "openspec/specs/cap/proposal.md",
                  self.repo.path / "docs/proposal.md",
                  self.repo.path / "openspec/changes/x/proposal.md.bak"]
        for path in others:
            for host, payload in (("claude", self.claude(path)), ("cursor", self.cursor(path))):
                with self.subTest(path=path, host=host):
                    self.assertIsNone(self.context(self.run_hook(host, payload), host))

    def test_outside_a_git_repository_is_silent(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-nogit-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = tmp / "openspec/changes/x/proposal.md"
        path.parent.mkdir(parents=True)
        path.write_text(GOOD_PROPOSAL)
        self.assertIsNone(self.context(self.run_hook("claude", self.claude(path)), "claude"))

    def test_a_bad_payload_is_silent(self):
        for payload in ("", "not json", "[]", "null", '{"tool_input": "openspec/changes/x/proposal.md"}',
                        json.dumps({"tool_input": {"file_path": 7}, "file_path": "proposal.md"}),
                        json.dumps({"tool_input": {"file_path": "openspec/changes/x/proposal.md"}})):
            for host in ("claude", "cursor"):
                with self.subTest(payload=payload, host=host):
                    self.assertIsNone(self.context(self.run_hook(host, payload), host))

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
            test.skipTest("openspec CLI not on PATH")
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
        self.assertEqual(kinds(r), ["duplicate"])
        self.assertIn('also stated in "Records are kept"', r.stdout)
        self.assertNotIn("Builds on", r.stdout)  # no gh, so no hint

    def test_with_the_declaration_it_checks_against_main_plus_the_dependency(self):
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(kinds(r), [])
        self.assertIn("lore-search builds on seat-files (acme/widgets#171", r.stdout)

    def test_both_changes_in_one_tree_need_the_declaration_too(self):
        self.s.repo.change("seat-files", delta=SEAT_FILES)
        self.s.repo.change("lore-search", delta=self.lore)
        self.assertEqual(kinds(self.s.check("lore-search", gh=False)), ["duplicate"])
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
        self.assertEqual(kinds(r), ["duplicate"])
        self.assertIn("Builds on: seat-files (acme/widgets#171)", r.stdout)

    def test_no_hint_when_no_open_pull_request_retires_the_requirement(self):
        self.s.data["list"] = []
        self.s.repo.change("lore-search", delta=self.lore)
        r = self.s.check("lore-search")
        self.assertEqual(kinds(r), ["duplicate"])
        self.assertNotIn("Builds on", r.stdout)

    def test_no_hint_when_gh_cannot_list_pull_requests(self):
        self.s.data["list"] = None
        self.s.repo.change("lore-search", delta=self.lore)
        r = self.s.check("lore-search")
        self.assertEqual(kinds(r), ["duplicate"])
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
        self.assertEqual(kinds(r), ["duplicate"])

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


class NoOpenSpecTests(unittest.TestCase):
    """The OpenSpec CLI is required for a stacked change (Adam, 2026-10-24)."""

    def test_without_the_openspec_cli_a_stacked_change_is_an_error(self):
        s = Stack(self, openspec=False)
        s.dependency(171, "a-change", modified("Records are kept", KEPT, SEAT))
        s.stacked(SEARCH_REQ, "a-change (acme/widgets#171)")
        bindir = pathlib.Path(tempfile.mkdtemp(prefix="spec-check-path-"))
        self.addCleanup(shutil.rmtree, bindir, ignore_errors=True)
        (bindir / "git").symlink_to(shutil.which("git"))  # PATH holds git and nothing else
        env = dict(s.env(), PATH=str(bindir))
        out = s.repo.check("lore-search", env=env)
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("error [stack]", out.stdout)
        self.assertIn("the openspec CLI is not on PATH", out.stdout)



class OpenSpecGrammarTests(unittest.TestCase):
    """A dependency's delta is read as OpenSpec's delta reader reads it
    (openspec 1.6, core/parsers/requirement-blocks.js). Each delta here
    passes `openspec validate --strict`. Regressions found by a bug-hunter
    run."""

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

    def test_an_addition_without_a_space_after_the_hashes_is_applied(self):
        s = self.s
        s.dependency(171, "a-change", SEARCH_REQ + "\n###Requirement: Seat shown\n\n" + SEAT +
                     "\n\n#### Scenario: s\n\n- **WHEN** w\n- **THEN** t\n")
        s.stacked("## MODIFIED Requirements\n" + req_block("Seat shown", SEAT + " The seat SHALL be shown in bold."),
                  self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertNotIn("neither main nor its dependencies define", out.stdout)

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

    def test_of_two_sections_with_one_title_the_last_wins(self):
        s = self.s
        s.dependency(171, "a-change", SEARCH_REQ + "\n" + ADDED_AUDIT)
        s.stacked(modified("Search works", SEARCH, "The search SHALL time out after a second."), self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn('modifies "Search works" in cap', out.stdout)


class ExactComparisonTests(unittest.TestCase):
    """A requirement is compared as OpenSpec compares it: its whole block,
    with its case, and its name exactly (found by bug-hunter, 2026-10-24)."""

    A = "a-change (acme/widgets#171)"
    DETAILS = MAIN_SPEC.replace("#### Scenario: A record survives",
                                "### Details\n\nReads are counted daily.\n\n#### Scenario: A record survives")
    STALE = "every delta it holds is already in the tree"

    def setUp(self):
        self.s = Stack(self)

    def tree(self, text):
        self.s.repo.write("openspec/specs/cap/spec.md", text)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "tree")
        self.s.repo.git("push", "-q", "origin", "main")

    # (1) A dependency's modification is present only when its whole block,
    # with its case, is.

    def test_a_modification_under_a_subheading_is_applied(self):
        s = self.s
        self.tree(self.DETAILS)
        s.dependency(171, "a-change", "## MODIFIED Requirements\n\n" + self.DETAILS.split("## Requirements\n\n")[1]
                     .replace("Reads are counted daily.", "Reads are counted hourly, and the count is kept for a year."))
        s.stacked(ADDED_AUDIT, self.A)
        out = s.check("lore-search")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertNotIn(self.STALE, out.stdout)

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
        hits = [l for l in errors(out) if "[drift]" in l and quote in l]
        self.assertEqual(len(hits), 1, out.stdout)
        self.assertTrue(hits[0].startswith(self.DELTA + ":"), hits[0])
        self.assertIn(f'"{name}"', hits[0])
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


if __name__ == "__main__":
    unittest.main()

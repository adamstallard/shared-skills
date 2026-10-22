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

    def __init__(self, test):
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
                                         "isCrossRepository": False}
        self.data["list"] = [p for p in self.data["list"] if p["number"] != number]
        if state == "OPEN":
            self.data["list"].append({"number": number, "headRefOid": oid,
                                      "files": [{"path": f} for f in files]})

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
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(kinds(r), ["drift"])
        self.assertIn('"Records are retained"', r.stdout)
        self.assertIn("seat-files (acme/widgets#171)", r.stdout)
        self.assertIn("Each record SHALL name the seat", r.stdout)

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
        self.assertIn("no open change seat-tables", r.stdout)

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
        main_spec = MAIN_SPEC.replace("### Requirement: Records are kept\n\n" + KEPT,
                                      "### Requirement: Records are retained\n\n" + KEPT + " " + SEAT)
        self.s.repo.write("openspec/specs/cap/spec.md", main_spec)
        self.s.repo.write("openspec/changes/archive/2026-10-01-seat-files/proposal.md", GOOD_PROPOSAL)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "archive seat-files")
        self.s.data["prs"]["171"]["state"] = "MERGED"
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(kinds(r), ["stack"])
        self.assertIn("archived", r.stdout)
        self.assertIn("remove the `Builds on: seat-files (acme/widgets#171)` line", r.stdout)

    def test_a_dependency_archived_on_the_base_but_not_in_this_tree(self):
        self.s.repo.git("checkout", "-q", "-b", "stale")
        self.s.repo.git("checkout", "-q", "main")
        self.s.repo.write("openspec/changes/archive/2026-10-01-seat-files/proposal.md", GOOD_PROPOSAL)
        self.s.repo.git("add", "-A")
        self.s.repo.git("commit", "-q", "-m", "archive seat-files")
        self.s.repo.git("checkout", "-q", "stale")
        self.s.data["prs"]["171"]["state"] = "MERGED"
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(kinds(r), ["stack"])
        self.assertIn("archived", r.stdout)
        self.assertIn("rebase", r.stdout)

    def test_a_merged_pull_request_whose_branch_is_gone_is_still_read(self):
        self.s.data["prs"]["171"]["state"] = "MERGED"
        self.s.sh("git", "-C", str(self.s.bare), "update-ref", "refs/pull/171/head",
                  self.s.data["prs"]["171"]["headRefOid"])
        self.s.sh("git", "-C", str(self.s.bare), "update-ref", "-d", "refs/heads/seat-files")
        self.s.stacked(self.lore, "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(kinds(r), [], r.stdout + r.stderr)

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
        self.s.data["prs"]["171"]["state"] = "MERGED"
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
        self.s.data["prs"]["171"]["state"] = "MERGED"
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
        self.s.data["prs"]["171"]["state"] = "MERGED"
        self.s.stacked(modified("Records are retained", KEPT, SEAT, SEARCH), "seat-files (acme/widgets#171)")
        r = self.s.check("lore-search")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()

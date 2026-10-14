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

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "spec_check.py"
HOOK = HERE / "check-commit-trailer.sh"
VERIFY = HERE / "verify-staged.sh"
SKILLS = HERE.parent.parent
LIB = SKILLS.parent / "lib" / "commit-trailer" / "commit-with-trailers.sh"
BUG_HUNTER = SKILLS / "bug-hunter" / "scripts" / "commit-with-trailer.sh"
BUG_HUNTER_HOOK = SKILLS / "bug-hunter" / "scripts" / "check-commit-trailer.sh"

sys.path.insert(0, str(HERE))
import spec_check  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="t@example.com",
           OPENSPEC_TELEMETRY="0", DO_NOT_TRACK="1")
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

    def run(self, *args, cwd=None, stdin=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.path,
                              capture_output=True, text=True, env=ENV, input=stdin)

    def check(self, *args):
        return self.run("check", "--base", "main", "--no-validate", *args)


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

    def test_an_undefined_term_is_a_check_not_a_failure(self):
        self.repo.change("x", delta=GOOD_DELTA.replace(
            "its last read.", "its last read, by the record's `tier`."))
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(kinds(r), ["undefined-term"])
        self.assertIn('check [undefined-term] "tier"', r.stdout)

    def test_code_like_literals_are_not_terms(self):
        literals = "`ghp_`, `xoxb-`, `sk-ant-`, `PASSWORD`, `AKIA`, `GITHUB_TOKEN`, " \
                   "`NotebookEdit`, `prBody`, `max_retries`, `v2api`"
        self.repo.change("x", delta=GOOD_DELTA.replace(
            "its last read.", f"its last read, and SHALL redact {literals}."))
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_plain_word_in_backticks_is_still_a_term(self):
        self.repo.change("x", delta=GOOD_DELTA.replace(
            "its last read.", "its last read, by the record's `tier` and `no-output` state."))
        self.assertEqual(kinds(self.repo.check("x")), ["undefined-term", "undefined-term"])

    def test_a_term_the_proposal_names_is_defined(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL + "\nA `tier` is how long a record lives.\n",
                         delta=GOOD_DELTA.replace("its last read.", "its last read, by its `tier`."))
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

    def test_a_decision_without_a_rejected_alternative_fails(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
            "1. **Records expire.** *Rejected:* keeping them forever.",
            "1. **Records expire.** *Rejected:* keeping them forever.\n"
            "2. **Expiry runs nightly.**\n   Once a day is enough."))
        r = self.repo.check("x")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(kinds(r), ["decision-alternative"])
        self.assertIn("proposal.md:4: error [decision-alternative]", r.stdout)

    def test_what_is_still_open_needs_no_alternative(self):
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
            "- **Open registration to everyone.** *Rejected:* invite-only.\n"
            "- **Records expire.** Nothing else."))
        r = self.repo.check("x")
        self.assertEqual(kinds(r), ["decision-alternative"])

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

    def test_setup_keeps_crlf_line_endings(self):
        config = self.repo.path / "openspec/config.yaml"
        config.write_bytes(b"schema: spec-driven\r\nrules:\r\n  proposal:\r\n    - Keep it short\r\n")
        self.repo.run("setup")
        data = config.read_bytes()
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
        self.assertIn(spec_check.RULE_TEXT.encode(), data)

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
            "**Still open:** nothing.", "- **Still open:** whether archived records expire too."))
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_open_items_end_the_decisions(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
            "**Still open:** nothing.", "**Open items:**\n\n- Whether archived records expire too."))
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_check_on_a_ref_without_openspec_cannot_run(self):
        self.repo.git("checkout", "-q", "-b", "nospec")
        self.repo.git("rm", "-rq", "openspec")
        self.repo.git("commit", "-q", "-m", "drop")
        self.repo.git("checkout", "-q", "main")
        r = self.repo.check("--ref", "nospec")
        self.assertEqual(r.returncode, 2, r.stdout)

    def test_setup_keeps_each_lines_own_ending(self):
        config = self.repo.path / "openspec/config.yaml"
        config.write_bytes(b"schema: spec-driven\nrules:\n  proposal:\n    - Keep it short\r\n"
                           b"  tasks:\n    - Small\n")
        self.repo.run("setup")
        data = config.read_bytes()
        self.assertTrue(data.startswith(b"schema: spec-driven\nrules:\n  proposal:\n"), data)
        self.assertTrue(data.endswith(b"  tasks:\n    - Small\n"), data)
        self.assertIn(spec_check.RULE_TEXT.encode(), data)

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

    def test_a_wrapped_decision_line_starting_open_issues_is_not_the_open_part(self):
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
            "1. **Records expire.** *Rejected:* keeping them forever.",
            "1. **Stale issues close after ninety days.** The bot closes\n"
            "   open issues that have had no activity for ninety days.\n"
            "   *Rejected:* never closing them.\n"
            "2. **The bot comments first.** *Rejected:* closing silently."))
        self.assertEqual(kinds(self.repo.check("x")), [])

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
            "2. **Purged records are deleted.**\n"))
        self.assertEqual(kinds(self.repo.check("x")), ["decision-alternative"])

    def test_a_list_item_in_a_fence_is_not_a_decision(self):
        self.repo.change("x", proposal=self.proposal(
            "1. **Validate config at load.** *Rejected:* validating lazily. Example:\n\n"
            "```yaml\n- name: primary\n  pool: 10\n```\n"))
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_still_open_labels_in_other_styles_end_the_decisions(self):
        for label in ("*Still open:*", "_Still open:_", "### *Still open*",
                      "**Open questions?**", "Still open."):
            with self.subTest(label=label):
                self.repo.change("x", proposal=self.proposal(
                    "1. **Records expire.** *Rejected:* keeping them forever.\n\n"
                    f"{label}\n\n- Whether archived records expire too.\n"))
                self.assertEqual(kinds(self.repo.check("x")), [])

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
                    "2. **Snippets are tested.**\n"))
                self.assertEqual(kinds(self.repo.check("x")), ["decision-alternative"])

    def test_an_underscore_wrapped_label_ends_the_decisions(self):
        for label in ("__Still open__", "_Open questions_", "### _Still open_"):
            with self.subTest(label=label):
                self.repo.change("x", proposal=GOOD_PROPOSAL.replace(
                    "**Still open:** nothing.", f"{label}\n\n- Whether archived records expire too."))
                self.assertEqual(kinds(self.repo.check("x")), [])

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
            "3. Use Postgres for the retry log.\n"))
        r = self.repo.check("x")
        self.assertEqual(kinds(r), ["decision-alternative"])
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
            "2. Log every retry.\n"))
        r = self.repo.check("x")
        self.assertEqual(kinds(r), ["decision-alternative"])
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


IGOR_STYLE = """schema: spec-driven

# Project context (optional)
# This is shown to AI when creating artifacts.

# Per-artifact rules (optional)
# Example:
#   rules:
#     proposal:
#       - Keep proposals under 500 words
"""


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.config = self.repo.path / "openspec" / "config.yaml"

    def setup_with(self, text):
        self.config.write_text(text)
        r = self.repo.run("setup")
        self.assertEqual(r.returncode, 0, r.stderr)
        return self.config.read_text()

    def assert_only_added(self, before, after):
        """Every original line survives, in order."""
        it = iter(after.splitlines())
        for line in before.splitlines():
            self.assertIn(line, it, f"lost or reordered: {line!r}")

    def test_a_config_with_only_comments_gets_a_rules_block(self):
        after = self.setup_with(IGOR_STYLE)
        self.assert_only_added(IGOR_STYLE, after)
        self.assertTrue(after.endswith(f'rules:\n  proposal:\n    {spec_check.RULE_MARKER}\n'
                                       f'    - "{spec_check.RULE_TEXT}"\n'))

    def test_a_second_run_changes_nothing(self):
        once = self.setup_with(IGOR_STYLE)
        r = self.repo.run("setup")
        self.assertIn("already", r.stdout)
        self.assertEqual(self.config.read_text(), once)

    def test_an_edited_rule_under_the_marker_is_left_alone(self):
        once = self.setup_with(IGOR_STYLE).replace("then everything else.", "then the rest.")
        self.config.write_text(once)
        self.repo.run("setup")
        self.assertEqual(self.config.read_text(), once)

    def test_rules_without_proposal_get_a_proposal_list(self):
        before = ("schema: spec-driven\nrules:  # ours\n    tasks:\n      - Small tasks\n"
                  "# trailing note\ncontext: |\n  Stack\n")
        after = self.setup_with(before)
        self.assert_only_added(before, after)
        self.assertIn("rules:  # ours\n    proposal:\n        # spec-check", after)
        self.assertIn("    tasks:\n      - Small tasks\n# trailing note\ncontext: |\n", after)

    def test_an_existing_proposal_list_gets_the_rule_last(self):
        before = ("rules:\n  proposal:\n    # keep it short\n    - Under 500 words\n"
                  "    - Name non-goals,\n      always\n  tasks:\n    - Small\ncontext: x\n")
        after = self.setup_with(before)
        self.assert_only_added(before, after)
        self.assertIn("      always\n    # spec-check: decisions first\n    - \"Open with", after)
        self.assertIn("\n  tasks:\n    - Small\ncontext: x\n", after)

    def test_a_list_at_the_keys_own_indent_is_extended_at_that_indent(self):
        before = "rules:\n  proposal:\n  - Under 500 words\n  tasks:\n  - Small\n"
        after = self.setup_with(before)
        self.assertIn("  - Under 500 words\n  # spec-check: decisions first\n  - \"Open", after)
        self.assertTrue(after.endswith("  tasks:\n  - Small\n"))

    def test_flow_style_is_refused_and_the_file_is_untouched(self):
        for before in ("rules:\n  proposal: [a, b]\n", "rules: {}\n"):
            self.config.write_text(before)
            r = self.repo.run("setup")
            self.assertEqual(r.returncode, 2)
            self.assertIn("by hand", r.stderr)
            self.assertEqual(self.config.read_text(), before)

    def test_dry_run_writes_nothing(self):
        self.config.write_text(IGOR_STYLE)
        r = self.repo.run("setup", "--dry-run")
        self.assertIn(spec_check.RULE_TEXT, r.stdout)
        self.assertEqual(self.config.read_text(), IGOR_STYLE)

    @unittest.skipUnless(HAS_OPENSPEC, "openspec CLI not on PATH")
    def test_openspec_shows_the_rule_to_the_agent(self):
        for before in (IGOR_STYLE, "rules:\n  proposal:\n    - Under 500 words\n"):
            self.config.write_text("schema: spec-driven\n" + before.replace("schema: spec-driven\n", ""))
            self.repo.run("setup")
            self.repo.change("probe")
            r = subprocess.run(["openspec", "instructions", "proposal", "--change", "probe"],
                               cwd=self.repo.path, capture_output=True, text=True, env=ENV)
            rules = r.stdout.split("<rules>", 1)[1].split("</rules>", 1)[0]
            self.assertIn(spec_check.RULE_TEXT, rules)


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
    def test_hook_json_names_an_executable_script(self):
        manifest = json.loads((HERE.parent / "hook.json").read_text())
        self.assertEqual(manifest["default"], "enabled")
        self.assertTrue(os.access(HERE.parent / manifest["command"], os.X_OK))


if __name__ == "__main__":
    unittest.main()

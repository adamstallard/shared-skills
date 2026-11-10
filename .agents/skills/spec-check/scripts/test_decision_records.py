#!/usr/bin/env python3
"""Tests for spec-check's decision records: the configured location, the
format checks, the rationale check, the checks on a branch's record edits,
the reader's list, and the OpenSpec behaviour the records rely on.

Standard library only:

    python3 test_decision_records.py

Each test builds a throwaway git repository, as test_spec_check.py does,
and the tests that need the OpenSpec CLI skip unless 1.16.0 or later is on
PATH.
"""

import json
import os
import pathlib
import random
import re
import shutil
import subprocess
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import spec_check  # noqa: E402
from test_spec_check import (ENV, GOOD_DELTA, GOOD_PROPOSAL, HAS_OPENSPEC, MAIN_SPEC,  # noqa: E402
                             Repo, kinds, signed_commit)
from test_spec_check import TASKS  # noqa: E402
from test_spec_check import Stack as StackRepo  # noqa: E402

NEEDS = "needs OpenSpec 1.16.0 or later"

CONSTRAINT = """- **Constraint: The store keeps no credentials.**
  Because: a leaked store leaks every seat.
  Evidence: two seats leaked in one incident, #12
  Holds while: seats are shared between roles.
  Paths: src/app.py
"""

REJECTED = """- **Rejected: A retrieval tool the worker calls.**
  Facing: workers missing lessons they did not know to ask for.
  Lost because: workers never call it, https://example.com/run/7.
  Instead: lessons are injected into the prompt.
  Paths: src/
"""


RATIONALE = """- **Rationale: Records are kept.**
  Thirty days covers the longest audit window any customer has asked for.
  A shorter window lost a disputed record twice.
  Evidence: the second loss, #31
  Evidence: the audit terms, https://example.com/terms
"""


def record(cap="cap", constraints=(CONSTRAINT,), rejected=(REJECTED,), rationale=()):
    text = f"# {cap}: constraints, rejected alternatives and rationale\n"
    for heading, entries in (("Constraints", constraints), ("Rejected", rejected),
                             ("Rationale", rationale)):
        if entries:
            text += f"\n## {heading}\n" + "\n".join(entries)
    return text


def findings(text, pending=False, names=("src/app.py", "src/lib/x.py"), requirements=None,
             gone=None):
    """[(severity, line, message)] of check_record on text, against a tree
    holding names, and with requirements, the titles a Rationale entry may
    name (None: not checked), and gone, {title: why} for the titles an open
    change removes or renames away. pending: an open change touches the
    capability, so its implementation may add a missing path."""
    class FakeBase:
        def change_names(self):
            return list(names)
    out = []
    spec_check.check_record("r.md", text, FakeBase(), out, cap="cap",
                            requirements=requirements, gone=gone, pending=pending)
    return [(f.severity, f.line, f.message) for f in out]


class ConfigTests(unittest.TestCase):
    def test_no_file_means_the_default(self):
        self.assertEqual(spec_check.parse_config(""), (spec_check.DEFAULT_RECORD, []))

    def test_a_template_is_read_with_quotes_and_comments(self):
        for text in ("decision-records: openspec/decisions/<capability>/decisions.md\n",
                     "# where records live\ndecision-records: 'openspec/decisions/<capability>/decisions.md'\n",
                     'decision-records: "openspec/decisions/<capability>/decisions.md"  # beside nothing\n',
                     "decision-records: openspec/decisions/<capability>/decisions.md # note\n"):
            with self.subTest(text=text):
                self.assertEqual(spec_check.parse_config(text),
                                 ("openspec/decisions/<capability>/decisions.md", []))

    def test_an_unknown_key_or_line_is_an_error(self):
        # Each case gives the record location parse_config must return. A
        # bad line never sets it: neither an unknown key's value, nor a
        # malformed line, nor a second decision-records line, which leaves
        # the first in place.
        default = spec_check.DEFAULT_RECORD
        for text, what, location in (
                ("decision-record: openspec/x/<capability>/d.md\n",
                 "reads no key 'decision-record'; delete this line (the only key is "
                 "decision-records)", default),
                ("decisions-first: enforce\n",
                 "reads no key 'decisions-first'; delete this line", default),
                ("- a list\n", "not a `key: value` line", default),
                ("decision-records: 'unclosed\n", "not one quoted string", default),
                ("decision-records: openspec/a/<capability>/d.md\n"
                 "decision-records: openspec/b/<capability>/d.md\n", "set twice",
                 "openspec/a/<capability>/d.md")):
            with self.subTest(text=text):
                template, problems = spec_check.parse_config(text)
                self.assertEqual([sev for _, sev, _ in problems], ["error"])
                self.assertIn(what, problems[0][2])
                self.assertEqual(template, location)

    def test_an_unusable_template_is_an_error_and_the_default_is_used(self):
        for value in ("", "openspec/decisions.md", "openspec/<capability>/<capability>.md",
                      "docs/<capability>.md", "openspec/changes/<capability>.md",
                      "/openspec/<capability>.md", "openspec/../<capability>.md",
                      "openspec/specs/<capability>/spec.md", "openspec/<capability>.txt",
                      "openspec//<capability>.md", "openspec/decisions/<capability>.md",
                      "openspec/specs/<capability>.md", "openspec/<capability>.md",
                      "openspec/x-<capability>/decisions.md", "openspec/<capability>-x/decisions.md"):
            with self.subTest(value=value):
                template, problems = spec_check.parse_config(f"decision-records: {value}\n")
                self.assertEqual(template, spec_check.DEFAULT_RECORD)
                self.assertEqual([sev for _, sev, _ in problems], ["error"], problems)

    def test_property_a_record_path_maps_back_to_its_capability(self):
        rng = random.Random(20261106)
        word = lambda: "".join(rng.choice("abcdefgh-") for _ in range(rng.randint(1, 6))).strip("-") or "a"
        for _ in range(300):
            head = "/".join(["openspec"] + [word() for _ in range(rng.randint(0, 2))])
            template = rng.choice([f"{head}/<capability>/decisions.md", f"{head}/<capability>/d.md",
                                   f"{head}/<capability>/{word()}/r.md"])
            self.assertIsNone(spec_check.template_problem(template), template)
            cap = "/".join(word() for _ in range(rng.randint(1, 3)))
            rel = spec_check.record_path(template, cap)
            self.assertEqual(spec_check.record_cap(template, rel), cap, (template, rel))

    def test_a_bad_config_fails_check(self):
        repo = Repo(self)
        repo.write("openspec/spec-check.yaml", "decision-records: docs/<capability>.md\n")
        repo.change("x")
        r = repo.check("x")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("openspec/spec-check.yaml:1: error [config]", r.stdout)


class RecordFormatTests(unittest.TestCase):
    def test_a_record_in_the_form_passes(self):
        self.assertEqual(findings(record()), [])

    def test_one_section_alone_passes(self):
        self.assertEqual(findings(record(rejected=())), [])
        self.assertEqual(findings(record(constraints=())), [])

    def test_each_missing_part_is_an_error(self):
        for label in ("Because", "Evidence", "Holds while", "Paths"):
            with self.subTest(label=label):
                text = record(constraints=(re.sub(rf"  {label}:.*\n", "", CONSTRAINT),))
                errors = [m for sev, _, m in findings(text) if sev == "error"]
                self.assertEqual(errors, [f"the Constraint entry has no {label}: line"])
        for label in ("Facing", "Lost because", "Instead"):
            with self.subTest(label=label):
                text = record(rejected=(re.sub(rf"  {label}:.*\n", "", REJECTED),))
                self.assertEqual([m for sev, _, m in findings(text) if sev == "error"],
                                 [f"the Rejected entry has no {label}: line"])

    def test_an_empty_part_is_an_error(self):
        text = record(constraints=(CONSTRAINT.replace("Because: a leaked store leaks every seat.",
                                                      "Because:"),))
        self.assertIn(("error", 5, "Because: is empty"), findings(text))

    def test_a_wrapped_part_is_one_part(self):
        text = record(constraints=(CONSTRAINT.replace(
            "  Holds while: seats are shared between roles.\n",
            "  Holds while: seats are shared\n    between roles.\n"),))
        self.assertEqual(findings(text), [])

    def test_a_part_of_the_other_kind_is_an_error(self):
        text = record(constraints=(CONSTRAINT.replace("  Paths:", "  Instead: nothing.\n  Paths:"),))
        msgs = [m for sev, _, m in findings(text) if sev == "error"]
        self.assertEqual(len(msgs), 1)
        self.assertIn("a Constraint entry has no part 'Instead'", msgs[0])

    def test_an_entry_under_the_wrong_section_is_an_error(self):
        text = record(constraints=(REJECTED,), rejected=())
        self.assertIn("goes under `## Rejected`", " ".join(m for _, _, m in findings(text)))

    def test_the_title_names_all_three_kinds_of_entry(self):
        old = record().replace("constraints, rejected alternatives and rationale",
                               "constraints and rejected alternatives")
        self.assertIn("`# <capability>: constraints, rejected alternatives and rationale`",
                      " ".join(m for _, _, m in findings(old)))
        self.assertEqual(findings(record()), [])
        title = "# cap: constraints, rejected alternatives and rationale"
        self.assertEqual(findings(record().replace(
            title, "# cap: Constraints, Rejected Alternatives And Rationale")), [])
        for bad in ("# cap:constraints, rejected alternatives and rationale",
                    "#cap: constraints, rejected alternatives and rationale"):
            self.assertTrue(any("the first line must be" in m for _, _, m in
                                findings(record().replace(title, bad))), bad)

    def test_the_title_must_name_the_capability_in_the_form(self):
        self.assertIn("the first line must be",
                      " ".join(m for _, _, m in findings(record().replace("constraints, rejected", "rules, rejected"))))
        self.assertIn("the title names 'other'",
                      " ".join(m for _, _, m in findings(record(cap="other"))))

    def test_anything_outside_the_form_is_an_error(self):
        for extra, what in (("\n## Notes\n- x\n", "has no section '## Notes'"),
                            ("\nSome prose about the record.\n", "not part of an entry"),
                            ("\n```\ncode\n```\n", "a code fence"),
                            ("\n## Retired\n- **Rejected: x.**\n", "has no section '## Retired'")):
            with self.subTest(extra=extra):
                msgs = [m for sev, _, m in findings(record() + extra) if sev == "error"]
                self.assertTrue(any(what in m for m in msgs), msgs)

    def test_a_repeated_entry_or_section_is_an_error(self):
        self.assertIn("the same Constraint entry as line 4",
                      " ".join(m for _, _, m in findings(record(constraints=(CONSTRAINT, CONSTRAINT.replace(
                          "credentials.", "credentials")),))))
        self.assertIn("appears twice",
                      " ".join(m for _, _, m in findings(record() + "\n## Rejected\n" + REJECTED)))

    def test_evidence_and_lost_because_without_a_link_are_checks(self):
        text = record(constraints=(CONSTRAINT.replace(", #12", ""),),
                      rejected=(REJECTED.replace(", https://example.com/run/7", ""),))
        self.assertEqual([(sev, n) for sev, n, _ in findings(text)], [("check", 6), ("check", 13)])
        for link in ("#12", "owner/repo#12", "[run](https://x.y)", "commit 4d593e93"):
            with self.subTest(link=link):
                text = record(constraints=(CONSTRAINT.replace("#12", link),))
                self.assertEqual(findings(text), [])

    def test_a_link_check_names_what_evidence_is(self):
        text = record(constraints=(CONSTRAINT.replace(", #12", ""),),
                      rejected=(REJECTED.replace(", https://example.com/run/7", ""),),
                      rationale=(RATIONALE.replace("#31", "the incident").replace(
                          ", https://example.com/terms", " terms"),))
        messages = [m for _, _, m in findings(text) if "links nothing" in m]
        self.assertEqual(len(messages), 4, messages)
        for m in messages:
            self.assertIn("the failure, measurement or outside fact", m)
            self.assertNotIn("test", m)

    def test_a_because_of_two_sentences_is_a_check(self):
        text = record(constraints=(CONSTRAINT.replace("every seat.", "every seat. It did once."),))
        self.assertEqual([(sev, n) for sev, n, _ in findings(text)], [("check", 5)])

    def test_a_missing_path_is_an_error_unless_an_open_change_touches_the_capability(self):
        text = record(constraints=(CONSTRAINT.replace("src/app.py", "src/gone.py"),))
        self.assertEqual([sev for sev, _, _ in findings(text)], ["error"])
        self.assertEqual([sev for sev, _, _ in findings(text, pending=True)], ["check"])

    def test_paths_name_files_directories_and_globs(self):
        for paths in ("src/app.py", "src", "src/", "`src/lib/`", "src/*.py", "src/**/x.py",
                      "**/*.py", "src/app.py, src/lib"):
            with self.subTest(paths=paths):
                text = record(constraints=(CONSTRAINT.replace("Paths: src/app.py", f"Paths: {paths}"),))
                self.assertEqual(findings(text), [])
        text = record(constraints=(CONSTRAINT.replace("Paths: src/app.py", "Paths: src/*.txt, sr"),))
        self.assertEqual(len(findings(text)), 2)

    def test_property_path_matching(self):
        rng = random.Random(4096)
        name = lambda: rng.choice(["a", "b", "cc", "d.py", "e.md"])
        for _ in range(500):
            parts = [name() for _ in range(rng.randint(1, 4))]
            path = "/".join(parts)
            self.assertTrue(spec_check.path_matches(path, path))
            for i in range(1, len(parts)):
                prefix = "/".join(parts[:i])
                self.assertTrue(spec_check.path_matches(prefix, path), (prefix, path))
                self.assertTrue(spec_check.path_matches(prefix + "/", path))
                self.assertTrue(spec_check.path_matches(prefix + "/**", path))
                # A directory never matches a longer name that starts like it.
                self.assertFalse(spec_check.path_matches(prefix + "x", path))
            self.assertTrue(spec_check.path_matches("**/" + parts[-1], path))
            if len(parts) > 1:
                # `*` stays within one name, and names what is under it.
                self.assertTrue(spec_check.path_matches("*", path))
                self.assertTrue(spec_check.path_matches("*/" * (len(parts) - 1) + "*", path))
                self.assertFalse(spec_check.path_matches("*/" * len(parts) + "*", path))

class RationaleTests(unittest.TestCase):
    def extra(self, body):
        return spec_check.rationale_sentences(body)

    def test_a_statement_and_one_because_sentence_pass(self):
        self.assertEqual(len(self.extra("The store SHALL keep records. Records are evidence.")), 1)
        self.assertEqual(self.extra("The store SHALL keep records, because they are evidence."), [])

    def test_more_than_one_sentence_beside_the_statement_is_counted(self):
        self.assertEqual(self.extra("The store SHALL keep records. They are evidence. "
                                    "Auditors ask for them."),
                         ["They are evidence.", "Auditors ask for them."])

    def test_every_rfc_2119_keyword_states_the_rule(self):
        self.assertEqual(self.extra("The store SHALL keep records. A reader MAY copy them. "
                                    "A writer SHOULD sign them. One MUST NOT edit them."), [])

    def test_a_list_continues_its_statement(self):
        body = ("The config SHALL carry:\n\n- `git rm`, the only way to delete\n"
                "- `git mv`, the only way to rename. It stages both sides.\n")
        self.assertEqual(self.extra(body), ["It stages both sides."])

    def test_linked_evidence_and_abbreviations_are_not_rationale(self):
        self.assertEqual(self.extra("The store SHALL keep records, e.g. logs. See #12. "
                                    "Evidence: the audit, https://x.y/z. "
                                    "[The incident](https://x.y/i)."), [])

    def test_check_flags_a_change_requirement_with_long_rationale(self):
        repo = Repo(self)
        repo.change("x", delta=GOOD_DELTA.replace(
            "ninety days after its last read.",
            "ninety days after its last read. Disks fill. Auditors agree. Nobody reads old ones."))
        r = repo.check("x")
        self.assertEqual(r.returncode, 0, r.stdout)
        if HAS_OPENSPEC:
            self.assertEqual(kinds(r), ["rationale"])
            self.assertIn("holds 3 sentences beside its SHALL statement", r.stdout)
            self.assertIn("move reasoning with evidence to a Rationale entry in "
                          "openspec/specs/cap/decisions.md, and the rest to design.md", r.stdout)

    def test_main_specs_are_not_given_the_rationale_check(self):
        repo = Repo(self)
        repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace(
            "after the last read.", "after the last read. Disks fill. Auditors agree."))
        self.assertNotIn("rationale", kinds(repo.check("specs")))


class SignTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.repo.git("checkout", "-q", "-b", "spec")

    def sign(self, read="deferred"):
        return self.repo.run("sign", "--read", read, "--base", "main", "--no-validate")

    def test_a_staged_main_record_is_checked(self):
        self.repo.write("openspec/specs/cap/decisions.md", record().replace("  Facing:", "  Facin:"))
        self.repo.git("add", "-A")
        r = self.sign()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("error [record]", r.stdout)

    def test_a_staged_record_at_a_configured_location_is_checked(self):
        self.repo.write("openspec/spec-check.yaml", "decision-records: openspec/decisions/<capability>/decisions.md\n")
        self.repo.write("openspec/decisions/cap/decisions.md", record().replace("  Facing:", "  Facin:"))
        self.repo.git("add", "-A")
        r = self.sign()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("openspec/decisions/cap/decisions.md", r.stdout)

    def test_a_staged_bad_config_alone_is_refused(self):
        self.repo.git("rm", "-q", "-r", "openspec/specs")
        self.repo.git("commit", "-q", "-m", "no specs")
        self.repo.write("openspec/spec-check.yaml", "decision-recs: x\n")
        self.repo.git("add", "-A")
        r = self.sign()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("error [config]", r.stdout)

    def test_editing_a_record_makes_the_change_touching_its_capability_due(self):
        self.repo.change("good")
        self.repo.git("add", "-A")
        signed_commit(self, self.repo)
        self.repo.write("openspec/specs/cap/decisions.md", record())
        self.repo.git("add", "-A")
        r = self.sign("subagent")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("read by a fresh subagent: good;", r.stdout.strip().splitlines()[-1])
        self.assertNotIn("decisions.md", r.stdout.strip().splitlines()[-1])

    def test_a_record_edit_no_open_change_touches_is_due_on_its_own(self):
        self.repo.write("openspec/specs/cap/decisions.md", record())
        self.repo.git("add", "-A")
        r = self.sign("subagent")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("read by a fresh subagent: openspec/specs/cap/decisions.md;",
                      r.stdout.strip().splitlines()[-1])
        self.repo.git("commit", "-q", "-m", "record", "--trailer",
                      "Spec-check: " + r.stdout.strip().splitlines()[-1][len("Spec-check: "):])
        self.repo.write("README.md", "unrelated\n")
        self.repo.git("add", "-A")
        r = self.sign("subagent")
        self.assertIn("nothing waits for its consistency read", r.stderr)

    def test_a_record_edit_beside_a_change_to_another_capability_is_due_on_its_own(self):
        self.repo.change("good")
        self.repo.git("add", "-A")
        signed_commit(self, self.repo)
        self.repo.write("openspec/specs/other/decisions.md", record(cap="other"))
        self.repo.git("add", "-A")
        r = self.sign("subagent")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("read by a fresh subagent: openspec/specs/other/decisions.md;",
                      r.stdout.strip().splitlines()[-1])

class RecordsForTheReaderTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.repo.write("openspec/specs/cap/decisions.md", record())
        self.repo.write("openspec/specs/other/spec.md", MAIN_SPEC.replace("cap", "other")
                        .replace("Records are kept", "Others are kept"))
        self.repo.write("openspec/specs/other/decisions.md", record(cap="other", rejected=(
            REJECTED.replace("Paths: src/", "Paths: lib/**/*.go"),), constraints=()))
        self.repo.write("openspec/specs/third/decisions.md", record(cap="third", constraints=(), rejected=(
            REJECTED.replace("Paths: src/", "Paths: docs/"),)))
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "records")
        self.repo.git("checkout", "-q", "-b", "spec")

    def records(self, *extra):
        r = self.repo.run("records", "--base", "main", *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout.splitlines()

    def test_the_touched_capabilitys_record_is_given(self):
        self.repo.change("x")
        self.assertEqual(self.records("x"),
                         ["openspec/specs/cap/decisions.md  (the change touches cap)"])

    def test_a_record_whose_paths_match_a_changed_file_is_given(self):
        self.repo.change("x")
        self.repo.write("lib/a/b.go", "package b\n")  # untracked
        self.assertEqual(self.records("x")[1:],
                         ["openspec/specs/other/decisions.md  (its Paths lib/**/*.go matches lib/a/b.go)"])

    def test_a_branch_ref_is_read_without_a_checkout(self):
        self.repo.change("x")
        self.repo.write("docs/guide.md", "x\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "x")
        self.repo.git("checkout", "-q", "main")
        self.assertEqual(self.records("x", "--ref", "spec"),
                         ["openspec/specs/cap/decisions.md  (the change touches cap)",
                          "openspec/specs/third/decisions.md  (its Paths docs/ matches docs/guide.md)"])

    def test_a_record_the_branch_edits_says_to_read_its_diff(self):
        self.repo.change("y")
        self.repo.write("openspec/specs/cap/decisions.md", record(rejected=()))
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "edit the record")
        self.assertEqual(self.records("y"),
                         ["openspec/specs/cap/decisions.md  (the change touches cap; the branch "
                          "edits it: read its diff against the merge base)"])

    def test_no_record_prints_none(self):
        self.repo.change("y", cap="newcap", delta=GOOD_DELTA)
        self.assertEqual(self.records("y"), ["none"])


@unittest.skipUnless(HAS_OPENSPEC, NEEDS)
class OpenSpecIgnoresDecisionRecordsTests(unittest.TestCase):
    """Pins what OpenSpec does with a decisions.md, as measured on 1.16.0
    for issue #56. A release that starts reading one fails here, and the
    reliance on plain `openspec archive` leaving a main record untouched,
    with a change holding no record of its own, must then be reconsidered."""

    def setUp(self):
        self.repo = Repo(self)
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace(
            "What cap does.", "What cap does: it keeps the records it is given, and reads them back."))
        # A record holding a requirement and a scenario, so a release that
        # read it as a spec would count one more.
        self.main_record = record() + "\n### Requirement: Not a rule\n\nIt SHALL be ignored.\n\n" \
                                      "#### Scenario: s\n\n- **WHEN** w\n- **THEN** t\n"
        self.repo.write("openspec/specs/cap/decisions.md", self.main_record)
        self.repo.write("openspec/decisions/cap.md", self.main_record)
        self.repo.write("openspec/specs/lonely/decisions.md", record(cap="lonely"))
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("Records pile up",
                                                             "Records pile up, and the disk fills"))
        self.repo.write("openspec/changes/x/specs/cap/decisions.md", self.main_record)
        self.repo.write("openspec/changes/x/specs/newcap/decisions.md", record(cap="newcap"))

    def openspec(self, *args):
        r = subprocess.run([shutil.which("openspec"), *args], cwd=self.repo.path,
                           capture_output=True, text=True, env=ENV)
        return r

    def json(self, *args):
        import json
        r = self.openspec(*args, "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_validate_list_and_show_ignore_records(self):
        data = self.json("validate", "--all", "--strict", "--no-interactive")
        self.assertEqual(sorted((i["id"], i["type"], i["valid"]) for i in data["items"]),
                         [("cap", "spec", True), ("x", "change", True)])
        self.assertEqual([s["id"] for s in self.json("list", "--specs")["specs"]], ["cap"])
        self.assertEqual([s["requirementCount"] for s in self.json("list", "--specs")["specs"]], [1])
        shown = self.json("show", "cap", "--type", "spec")
        self.assertEqual([r["text"] for r in shown["requirements"]],
                         ["The store SHALL keep every record it is given for at least thirty days "
                          "after the last read."])
        deltas = self.json("show", "x", "--type", "change", "--deltas-only")["deltas"]
        self.assertEqual(sorted((d["spec"], d["operation"]) for d in deltas), [("cap", "ADDED")])

    def test_archive_leaves_the_main_record_and_the_changes_record_behind(self):
        r = self.openspec("archive", "x", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.repo.path / "openspec/specs/cap/decisions.md").read_text(), self.main_record)
        self.assertFalse((self.repo.path / "openspec/specs/newcap").exists())
        archived = [p for p in (self.repo.path / "openspec/changes/archive").iterdir()]
        self.assertEqual(len(archived), 1)
        self.assertEqual((archived[0] / "specs/cap/decisions.md").read_text(), self.main_record)
        self.assertTrue((archived[0] / "specs/newcap/decisions.md").exists())


class FoundByBugHunterTests(unittest.TestCase):
    def test_a_config_value_with_text_after_its_quote_is_an_error(self):
        _, problems = spec_check.parse_config('decision-records: "openspec/d/<capability>/d.md" junk\n')
        self.assertEqual([sev for _, sev, _ in problems], ["error"])

    def test_a_config_file_starting_with_a_byte_order_mark_reads_cleanly(self):
        self.assertEqual(spec_check.parse_config("\ufeffdecision-records: openspec/d/<capability>/d.md\n"),
                         ("openspec/d/<capability>/d.md", []))

    def test_a_backslash_inside_a_template_is_refused(self):
        self.assertIn("not a plain path", spec_check.template_problem("openspec/a\\b/<capability>/d.md"))

    def test_a_capability_with_an_empty_segment_is_not_one(self):
        self.assertIsNone(spec_check.record_cap("openspec/decisions/<capability>/d.md",
                                                "openspec/decisions/a//d.md"))

    def test_a_repeated_part_or_an_empty_title_is_an_error(self):
        text = record(constraints=(CONSTRAINT.replace("  Evidence:", "  Because: again.\n  Evidence:"),))
        self.assertIn("Because appears twice in this entry", " ".join(m for _, _, m in findings(text)))
        text = record(constraints=(CONSTRAINT.replace("The store keeps no credentials.", "."),))
        self.assertIn("the entry names nothing after its label", " ".join(m for _, _, m in findings(text)))

    def test_an_abbreviation_does_not_end_a_sentence_or_drop_the_next(self):
        self.assertEqual(spec_check.sentences("Stores leak, e.g. Redis dumps. The fold runs."),
                         ["Stores leak, e.g. Redis dumps.", "The fold runs."])

    def test_a_record_listed_for_its_capability_is_not_listed_again_for_its_paths(self):
        repo = Repo(self)
        repo.write("openspec/specs/cap/decisions.md", record())
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "record")
        repo.git("checkout", "-q", "-b", "spec")
        repo.change("x")
        repo.write("src/app.py", "changed\n")
        r = repo.run("records", "x", "--base", "main")
        self.assertEqual(r.stdout.splitlines(), ["openspec/specs/cap/decisions.md  (the change touches cap)"])


class FoundByBugHunterIteration3Tests(unittest.TestCase):
    def test_a_malformed_record_for_a_capability_with_no_spec_is_still_checked(self):
        repo = Repo(self)
        repo.write("openspec/specs/gone/decisions.md",
                   record(cap="gone").replace("# gone: constraints", "# gone - constraints"))
        r = repo.check("specs")
        self.assertIn("openspec/specs/gone/decisions.md:1: error [record] the first line must be", r.stdout)
        self.assertEqual(r.returncode, 1)


class FoundByBugHunterRun2Tests(unittest.TestCase):
    def test_a_readme_beside_records_in_their_own_folder_is_not_a_record(self):
        repo = Repo(self)
        repo.write("openspec/spec-check.yaml", "decision-records: openspec/decisions/<capability>/decisions.md\n")
        repo.write("openspec/decisions/README.md", "# Decision records\n\nOne file per capability.\n")
        repo.write("openspec/decisions/cap/decisions.md", record())
        r = repo.check("specs")
        self.assertNotIn("README.md", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)


class FoundByBugHunterRun2Iteration2Tests(unittest.TestCase):
    NEWCAP = GOOD_DELTA.replace("## ADDED Requirements", "## Purpose\n\nWhat newcap does: it keeps "
                                "the records it is given.\n\n## ADDED Requirements")

    def test_a_change_holding_its_own_record_is_refused(self):
        repo = Repo(self)
        repo.change("x")
        repo.write("openspec/changes/x/specs/cap/decisions.md", record())
        r = repo.check("x")
        self.assertIn("a change holds no decision record of its own: edit the main record "
                      "directly, at openspec/specs/cap/decisions.md", r.stdout)
        self.assertEqual(r.returncode, 1)

    def test_a_path_under_openspec_changes_is_never_a_main_record(self):
        self.assertIsNone(spec_check.record_cap("openspec/<capability>/decisions.md",
                                                "openspec/changes/x/specs/cap/decisions.md"))


class ConfiguredLocationRecordTests(unittest.TestCase):
    """Every file the configured location matches is a record."""

    def test_a_record_with_no_spec_is_checked_even_after_a_byte_order_mark(self):
        for lead in ("", "\ufeff", "\n\n"):
            with self.subTest(lead=repr(lead)):
                repo = Repo(self)
                repo.write("openspec/spec-check.yaml",
                           "decision-records: openspec/decisions/<capability>/decisions.md\n")
                repo.write("openspec/decisions/gone/decisions.md", lead + record(cap="gone").replace(
                    "Paths: src/app.py", "Paths: src/nonexistent.py"))
                r = repo.check("specs")
                self.assertIn("src/nonexistent.py matches nothing", r.stdout)

class FoundByBugHunterRun2Iteration3Tests(unittest.TestCase):
    def test_a_change_record_whose_capability_has_no_record_path_names_none(self):
        repo = Repo(self)
        repo.write("openspec/spec-check.yaml", "decision-records: openspec/<capability>/decisions.md\n")
        repo.change("x", cap="changes", delta=GOOD_DELTA.replace(
            "## ADDED Requirements", "## Purpose\n\nWhat changes does: it keeps the records it is given.\n\n"
            "## ADDED Requirements"))
        repo.write("openspec/changes/x/specs/changes/decisions.md", record(cap="changes"))
        r = repo.check("x")
        self.assertIn("a change holds no decision record of its own", r.stdout)
        self.assertNotIn("at openspec/changes/decisions.md", r.stdout)
        self.assertEqual(r.returncode, 1)


LORE = GOOD_DELTA.replace("Records expire", "Records are searched").replace(
    "delete a record ninety days after its last read", "index each record for search").replace(
    "An old record goes", "A record is found")


def rejected_first(cap="cap"):
    return f"# {cap}: constraints, rejected alternatives and rationale\n\n## Rejected\n{REJECTED}\n## Constraints\n{CONSTRAINT}"


class FoundByBugHunterRun4Tests(unittest.TestCase):
    def test_a_path_with_non_ascii_letters_matches_its_file(self):
        repo = Repo(self)
        repo.write("src/café.py", "x\n")
        repo.write("openspec/specs/cap/decisions.md",
                   record(constraints=(CONSTRAINT.replace("src/app.py", "src/café.py"),), rejected=()))
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "c")
        r = repo.check("specs")
        self.assertNotIn("matches nothing", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_records_lists_a_record_whose_paths_name_a_non_ascii_file(self):
        repo = Repo(self)
        repo.write("src/café.py", "x\n")
        repo.write("openspec/specs/other/decisions.md",
                   record(cap="other", constraints=(CONSTRAINT.replace("src/app.py", "src/café.py"),),
                          rejected=()))
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "c")
        repo.git("checkout", "-q", "-b", "spec")
        repo.change("x")
        repo.write("src/café.py", "y\n")
        r = repo.run("records", "--base", "main", "x")
        self.assertIn("openspec/specs/other/decisions.md", r.stdout)

    def test_a_file_name_that_is_not_utf8_does_not_crash_check_or_records(self):
        repo = Repo(self)
        repo.write("openspec/specs/cap/decisions.md", record(rejected=()))
        repo.git("add", "-A")
        blob = subprocess.run(["git", "-C", str(repo.path), "hash-object", "-w", "--stdin"],
                              input=b"x\n", capture_output=True, check=True).stdout.strip()
        subprocess.run(["git", "-C", str(repo.path), "update-index", "--index-info"],
                       input=b"100644 " + blob + b"\tdocs/caf\xe9.txt\n", check=True)
        repo.git("commit", "-q", "-m", "c")
        r = repo.check("specs")
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        repo.git("checkout", "-q", "-b", "spec")
        repo.change("x")
        r = repo.run("records", "--base", "main", "x")
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_name_that_is_not_utf8_is_printed_without_a_crash(self):
        repo = Repo(self)
        repo.write("openspec/specs/other/decisions.md", record(
            cap="other", constraints=(CONSTRAINT.replace("src/app.py", "lib/"),), rejected=()))
        repo.write("lib/a.c", "x\n")
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "c")
        repo.git("checkout", "-q", "-b", "feat")
        blob = subprocess.run(["git", "-C", str(repo.path), "hash-object", "-w", "--stdin"],
                              input=b"x\n", capture_output=True, check=True).stdout.strip()
        subprocess.run(["git", "-C", str(repo.path), "update-index", "--index-info"],
                       input=b"100644 " + blob + b"\tlib/caf\xe9.c\n", check=True)
        repo.change("x")
        repo.git("add", "openspec")
        repo.git("commit", "-q", "-m", "feat")
        # Strict UTF-8 on stdout, as Python before 3.15 has under an ordinary locale.
        env = dict(ENV, PYTHONUTF8="0", PYTHONIOENCODING="utf-8:strict")
        r = repo.run("records", "--ref", "feat", "--base", "main", "x", env=env)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("openspec/specs/other/decisions.md", r.stdout)

class FoundByBugHunterRun5Tests(unittest.TestCase):
    def test_a_template_naming_spec_md_or_changes_in_another_case_is_refused(self):
        for t in ("openspec/specs/<capability>/Spec.md", "openspec/Changes/<capability>/decisions.md"):
            with self.subTest(t=t):
                self.assertIsNotNone(spec_check.template_problem(t))
        self.assertIsNone(spec_check.record_cap("openspec/<capability>/decisions.md",
                                                "openspec/Changes/x/decisions.md"))

    def test_records_given_specs_says_it_takes_a_change(self):
        repo = Repo(self)
        repo.change("x")
        for target in ("specs", "openspec/specs", "specs/", "openspec/specs/"):
            with self.subTest(target=target):
                r = repo.run("records", target, "--base", "main")
                self.assertNotIn("Traceback", r.stderr)
                self.assertIn("records takes a change's name", r.stderr)
                self.assertEqual(r.returncode, 2)

class MutationGapRun5Tests(unittest.TestCase):
    def test_check_rationale_passes_one_sentence_and_flags_two(self):
        import types
        corpus = types.SimpleNamespace(template=spec_check.DEFAULT_RECORD)
        for body, flagged in (("The store SHALL keep records. Records are evidence.", False),
                              ("The store SHALL keep records. They are evidence. Auditors ask.", True)):
            req = types.SimpleNamespace(body=body, path="openspec/specs/cap/spec.md", line=3, name="R")
            out = []
            spec_check.check_rationale([req], corpus, out)
            self.assertEqual(bool(out), flagged, body)

    def test_a_stream_that_already_writes_raw_bytes_is_left_alone(self):
        repo = Repo(self)
        repo.write("openspec/specs/other/decisions.md", record(
            cap="other", constraints=(CONSTRAINT.replace("src/app.py", "lib/"),), rejected=()))
        repo.write("lib/a.c", "x\n")
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "c")
        repo.git("checkout", "-q", "-b", "feat")
        blob = subprocess.run(["git", "-C", str(repo.path), "hash-object", "-w", "--stdin"],
                              input=b"x\n", capture_output=True, check=True).stdout.strip()
        subprocess.run(["git", "-C", str(repo.path), "update-index", "--index-info"],
                       input=b"100644 " + blob + b"\tlib/caf\xe9.c\n", check=True)
        repo.change("x")
        repo.git("add", "openspec")
        repo.git("commit", "-q", "-m", "feat")
        env = dict(ENV, PYTHONIOENCODING="utf-8:surrogateescape")
        r = subprocess.run([sys.executable, str(spec_check.__file__), "records", "--ref", "feat",
                            "--base", "main", "x"], cwd=repo.path, capture_output=True, env=env)
        self.assertIn(b"lib/caf\xe9.c", r.stdout)


class FoundByBugHunterRun7Tests(unittest.TestCase):
    def test_a_glob_ending_in_a_slash_names_what_is_under_it(self):
        for pattern in ("src/*/", "src/**/", "src/l*/", "src/?ib/"):
            with self.subTest(pattern=pattern):
                self.assertTrue(spec_check.path_matches(pattern, "src/lib/x.py"))

class SymlinkGateTests(unittest.TestCase):
    """spec-check refuses every symlink under openspec/, openspec itself
    included, in the tree being judged: the checkout or staged tree for
    check, sign, records and archive; the head for ci and the hand-back
    hook. A symlink only at the merge base is not refused."""

    GATE = "spec-check doesn't support symlinks under openspec/: "

    def link_openspec(self, repo):
        os.makedirs(repo.path / "docs", exist_ok=True)
        os.rename(repo.path / "openspec", repo.path / "docs/openspec")
        os.symlink("docs/openspec", repo.path / "openspec")
        repo.git("add", "-A")

    def ci(self, repo):
        event = {"action": "ready_for_review", "pull_request": {
            "html_url": "https://github.com/o/r/pull/7", "draft": False,
            "head": {"sha": repo.git("rev-parse", "HEAD")}, "base": {"ref": "main"}}}
        path = repo.path.parent / "event.json"
        path.write_text(json.dumps(event))
        return repo.run("ci", "--event", str(path))

    def refused(self, r, *links):
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(self.GATE + ", ".join(links) + "; replace each with a real folder or file",
                      r.stderr)

    def test_check_names_every_symlink_under_openspec_wherever_it_is(self):
        repo = Repo(self)
        repo.change("x")
        repo.write("shared/notes.md", "notes\n")
        os.symlink("../../../shared/notes.md", repo.path / "openspec/changes/x/notes.md")
        os.symlink("../../../shared/notes.md", repo.path / "openspec/specs/cap/decisions.md")
        os.symlink("../../nowhere", repo.path / "openspec/specs/gone")
        os.symlink("/usr", repo.path / "openspec/abs")
        links = ["openspec/abs", "openspec/changes/x/notes.md", "openspec/specs/cap/decisions.md",
                 "openspec/specs/gone"]
        self.refused(repo.check("x"), *links)
        self.refused(repo.check("specs"), *links)
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "links")
        self.refused(repo.check("--ref", "HEAD", "x"), *links)

    def test_a_linked_openspec_or_changes_folder_is_refused(self):
        repo = Repo(self)
        repo.change("x")
        self.link_openspec(repo)
        self.refused(repo.check(), "openspec")
        os.remove(repo.path / "openspec")
        os.rename(repo.path / "docs/openspec", repo.path / "openspec")
        os.rename(repo.path / "openspec/changes", repo.path / "docs/changes")
        os.symlink("../docs/changes", repo.path / "openspec/changes")
        self.refused(repo.check(), "openspec/changes")
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "linked changes")
        self.refused(repo.check("--ref", "HEAD"), "openspec/changes")

    def test_sign_and_records_refuse_a_symlink(self):
        repo = Repo(self)
        repo.git("checkout", "-q", "-b", "spec")
        repo.change("x")
        repo.write("shared/notes.md", "notes\n")
        os.symlink("../../../shared/notes.md", repo.path / "openspec/changes/x/notes.md")
        repo.git("add", "-A")
        self.refused(repo.run("sign", "--read", "deferred", "--base", "main", "--no-validate"),
                     "openspec/changes/x/notes.md")
        self.refused(repo.run("records", "x"), "openspec/changes/x/notes.md")

    def test_ci_takes_back_a_hand_back_whose_head_holds_a_symlink(self):
        repo = Repo(self)
        repo.git("checkout", "-q", "-b", "spec")
        repo.change("x")
        self.link_openspec(repo)
        repo.git("commit", "-q", "-m", "link")
        r = self.ci(repo)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("::error::" + self.GATE + "openspec; replace each with a real folder or file "
                      f"(head {repo.git('rev-parse', 'HEAD')[:12]}); push, and hand back again.",
                      r.stdout)
        self.assertIn("could not take the hand-back back", r.stdout)
        with self.assertRaises(spec_check.Fatal):
            spec_check.unread_at(str(repo.path), "HEAD", "main")

    def test_the_hand_back_hook_blocks_and_takes_back_a_head_holding_a_symlink(self):
        from test_spec_check import HandbackBase

        class Case(HandbackBase):
            def runTest(self):
                pass
        case = Case()
        case.setUp()
        self.addCleanup(case.doCleanups)
        repo = case.repo
        repo.change("x")
        repo.write("shared/notes.md", "notes\n")
        os.symlink("../../../shared/notes.md", repo.path / "openspec/changes/x/notes.md")
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "link")
        pr = case.pr()
        why = self.GATE + "openspec/changes/x/notes.md; replace each with a real folder or file"
        r = case.hook("gh pr ready 7 -R o/r", pr=pr)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("spec-check: blocked this hand-back", r.stderr)
        self.assertIn(f"gh pr ready: in {pr['url']} (head {pr['headRefOid'][:12]}), {why}.", r.stderr)
        r = case.hook("gh pr create --title x", pr=pr, output=pr["url"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("spec-check: took back a hand-back", r.stderr)
        self.assertIn(f"{pr['url']} (head {pr['headRefOid'][:12]}) was handed back, but {why};",
                      r.stderr)

    def test_a_symlink_only_at_the_merge_base_is_not_refused(self):
        repo = Repo(self)
        repo.change("old")
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "old change")
        self.link_openspec(repo)
        repo.git("commit", "-q", "-m", "link on main")
        repo.git("checkout", "-q", "-b", "spec")
        os.remove(repo.path / "openspec")
        os.rename(repo.path / "docs/openspec", repo.path / "openspec")
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "real folder, unread")
        r = self.ci(repo)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("old changed after its last consistency read", r.stdout)
        repo.change("old", delta=LORE)
        repo.git("add", "-A")
        signed_commit(self, repo)
        r = self.ci(repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no OpenSpec change is unread", r.stdout)


class FoundByBugHunterGateRunTests(unittest.TestCase):
    """Found by bug-hunter in the symlink gate's run: markdown and records
    are read only from regular files, so a FIFO cannot make check hang."""

    def test_a_fifo_named_like_markdown_or_a_record_is_not_read(self):
        for name in ("notes.md", "decisions.md"):
            with self.subTest(name=name):
                repo = Repo(self)
                os.mkfifo(repo.path / "openspec/specs/cap" / name)
                try:
                    r = subprocess.run([sys.executable, spec_check.__file__, "check", "--base",
                                        "main", "--no-validate", "specs"], cwd=repo.path,
                                       capture_output=True, text=True, env=ENV, timeout=60)
                except subprocess.TimeoutExpired:
                    self.fail(f"check hung reading a FIFO named {name}")
                self.assertIn("spec-check:", r.stdout + r.stderr)
                self.assertNotIn("Traceback", r.stderr)


class RationaleFormTests(unittest.TestCase):
    """The form of a `## Rationale` entry: a bold title naming its
    requirement, the reasoning, then one or more Evidence lines. The script
    checks the form; whether the linked evidence holds up (a test link
    alone does not) is the consistency read's to judge."""

    def test_a_rationale_entry_in_the_form_passes(self):
        text = record(rationale=(RATIONALE,))
        self.assertEqual(findings(text, requirements={"Records are kept"}), [])
        rec = spec_check.parse_record(text)
        (e,) = [e for e in rec.entries if e.kind == "Rationale"]
        self.assertEqual(e.title, "Records are kept.")
        self.assertEqual(e.section, "rationale")
        self.assertEqual(e.reasoning, "Thirty days covers the longest audit window any customer "
                                      "has asked for. A shorter window lost a disputed record twice.")
        self.assertEqual([v for _, v in e.evidence],
                         ["the second loss, #31", "the audit terms, https://example.com/terms"])

    def test_evidence_and_reasoning_are_both_required(self):
        bare = "- **Rationale: Records are kept.**\n  Thirty days covers every audit window.\n"
        self.assertEqual([(sev, n) for sev, n, m in findings(record(rationale=(bare,)))
                          if "no Evidence" in m], [("error", 18)])
        test = bare + "  Evidence: the regression test for the lost-record bug, [test_audit](tests/test_audit.py)\n"
        self.assertEqual(findings(record(rationale=(test,))), [])
        empty = "- **Rationale: Records are kept.**\n  Evidence: the audit terms, #4\n"
        problems = findings(record(rationale=(empty,)))
        self.assertTrue(any(sev == "error" and "no reasoning" in m for sev, _, m in problems), problems)

    def test_reasoning_after_evidence_is_an_error(self):
        late = ("- **Rationale: Records are kept.**\n  Evidence: the audit terms, #4\n"
                "\n  Thirty days covers every audit window.\n")
        problems = findings(record(rationale=(late,)))
        self.assertTrue(any(sev == "error" for sev, _, _ in problems), problems)

    def test_evidence_that_links_nothing_is_a_check(self):
        text = record(rationale=(RATIONALE.replace("#31", "the incident"),))
        self.assertEqual([(sev, m.split(":")[0]) for sev, _, m in findings(text)],
                         [("check", "Evidence")])

    def test_entries_go_under_their_own_section(self):
        misplaced = record(rejected=(REJECTED, RATIONALE))
        self.assertTrue(any("goes under `## Rationale`" in m for _, _, m in findings(misplaced)))
        wrong = record(rationale=(RATIONALE, CONSTRAINT))
        self.assertTrue(any("goes under `## Constraints`" in m for _, _, m in findings(wrong)))

    def test_a_rationale_must_name_a_requirement(self):
        text = record(rationale=(RATIONALE.replace("Records are kept", "Records are shredded"),))
        problems = findings(text, requirements={"Records are kept"})
        self.assertEqual([(sev, line) for sev, line, _ in problems], [("error", 18)])
        self.assertIn('"Records are shredded" names no requirement of cap', problems[0][2])
        self.assertEqual(findings(record(rationale=(RATIONALE.replace(
            "Records are kept.", "Records are kept"),)), requirements={"Records are kept"}), [])
        # Titles match exactly; a loose match only suggests the exact title.
        ((_, _, message),) = findings(record(rationale=(RATIONALE.replace(
            "Records are kept.", "records ARE `kept`"),)), requirements={"Records are kept"})
        self.assertIn('"records ARE `kept`" names no requirement of cap', message)
        self.assertTrue(message.endswith('by its exact title; did you mean "Records are kept"?'), message)
        ((_, _, message),) = findings(record(rationale=(RATIONALE.replace(
            "Records are kept.", "records are kept"),)), requirements={"Records are kept", "Records are Kept"})
        self.assertTrue(message.endswith("by its exact title"), message)

    def test_a_title_ending_in_a_period_is_written_with_two(self):
        two = RATIONALE.replace("Records are kept.", "Records are kept..")
        self.assertEqual(findings(record(rationale=(two,)), requirements={"Records are kept."}), [])
        self.assertEqual(len(findings(record(rationale=(RATIONALE,)), requirements={"Records are kept."})), 1)

    def test_a_hint_for_a_title_ending_in_a_period_gives_the_title_to_write(self):
        ((_, _, message),) = findings(record(rationale=(RATIONALE.replace(
            "Records are kept.", "records are kept."),)), requirements={"Records are kept."})
        self.assertTrue(message.endswith('did you mean "Records are kept.."?'), message)

    def test_an_entry_title_is_trimmed_as_javascript_trims(self):
        (entry,) = spec_check.parse_record(record(constraints=(), rejected=(), rationale=(RATIONALE.replace(
            "Records are kept.", "Records are kept\x1f"),))).entries
        self.assertEqual(entry.key, ("Rationale", "Records are kept\x1f"))

    def test_space_before_the_closing_period_is_trimmed(self):
        (entry,) = spec_check.parse_record(record(constraints=(), rejected=(), rationale=(RATIONALE.replace(
            "Records are kept.", "Records are kept ."),))).entries
        self.assertEqual(entry.key, ("Rationale", "Records are kept"))

    def test_a_title_of_periods_is_written_with_one_more(self):
        two = RATIONALE.replace("Records are kept.", "..")
        self.assertEqual(findings(record(rationale=(two,)), requirements={"."}), [])
        ((_, _, message),) = findings(record(rationale=(RATIONALE.replace("Records are kept.", "."),)),
                                      requirements={"."})
        self.assertIn("names nothing after its label", message)

    def test_a_rationale_naming_a_requirement_going_away_is_an_error(self):
        text = record(constraints=(), rejected=(), rationale=(RATIONALE,))
        why = "the open change x removes"
        ((sev, line, message),) = findings(text, requirements={"Records are kept"},
                                           gone={"Records are kept": why})
        self.assertEqual((sev, line), ("error", 4))
        self.assertIn(f'"Records are kept" names a requirement that {why}', message)
        self.assertIn("delete the entry, or retitle it", message)
        self.assertEqual(findings(text, requirements={"Records are kept"}, gone={"Other": why}), [])

class RationaleCheckTests(unittest.TestCase):
    """check holds a Rationale entry's title to the requirements in force,
    or in the change."""

    def setUp(self):
        self.repo = Repo(self)

    def record_errors(self, *args):
        r = self.repo.check(*args)
        return [line for line in r.stdout.splitlines() if "error [record]" in line]

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_a_record_may_name_a_requirement_in_force_or_in_an_open_change(self):
        self.repo.change("x")
        why = "- **Rationale: {}.**\n  The reasoning, at more length than one sentence holds.\n  Evidence: the incident, #9\n"
        self.repo.write("openspec/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(why.format("Records are kept"),
                                                    why.format("Records expire"))))
        self.assertEqual(self.record_errors("specs"), [])
        self.repo.write("openspec/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(why.format("Records are shredded"),)))
        (error,) = self.record_errors("specs")
        self.assertIn('"Records are shredded" names no requirement of cap', error)

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_a_record_may_name_a_requirement_only_another_open_change_adds(self):
        self.repo.change("x")
        self.repo.change("y", delta=GOOD_DELTA.replace("Records expire", "Records are indexed"))
        why = "- **Rationale: {}.**\n  The reasoning, at more length than one sentence holds.\n  Evidence: the incident, #9\n"
        self.repo.write("openspec/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(why.format("Records are indexed"),)))
        self.assertEqual(self.record_errors("specs"), [])
        shutil.rmtree(self.repo.path / "openspec/changes/y")
        (error,) = self.record_errors("specs")
        self.assertIn('"Records are indexed" names no requirement of cap', error)

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_a_record_may_not_name_a_requirement_an_open_change_removes(self):
        self.repo.change("x", delta="## REMOVED Requirements\n\n### Requirement: Records are kept\n\n"
                                    "**Reason**: no longer needed.\n\n**Migration**: none.\n")
        self.repo.write("openspec/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(RATIONALE,)))
        (at_record,) = self.record_errors("specs")
        self.assertIn('openspec/specs/cap/decisions.md:4: error [record] Rationale: "Records are kept" '
                      "names a requirement that the open change x removes", at_record)
        # The change's own check reports it at both places.
        at_delta, at_record_too = self.record_errors("x")
        self.assertEqual(at_record_too, at_record)
        self.assertIn('openspec/changes/x/specs/cap/spec.md:3: error [record] removes "Records are '
                      'kept", which openspec/specs/cap/decisions.md gives a Rationale entry; delete '
                      "that entry from the record", at_delta)
        self.repo.write("openspec/specs/cap/decisions.md", record())
        self.assertEqual(self.record_errors("specs") + self.record_errors("x"), [])

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_a_main_record_must_name_a_main_requirement(self):
        self.repo.write("openspec/specs/cap/decisions.md", record(rationale=(
            RATIONALE, RATIONALE.replace("Records are kept", "Records are shredded"))))
        (error,) = self.record_errors("specs")
        self.assertIn("openspec/specs/cap/decisions.md:", error)
        self.assertIn('"Records are shredded" names no requirement of cap', error)

    def test_records_says_when_a_rationale_covers_a_requirement_the_change_changes(self):
        self.repo.write("openspec/specs/cap/decisions.md", record(rationale=(RATIONALE,)))
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "record")
        self.repo.git("checkout", "-q", "-b", "spec")
        self.repo.change("x", delta=MAIN_SPEC.split("## Requirements\n", 1)[1].replace(
            "### Requirement", "## MODIFIED Requirements\n\n### Requirement").replace(
            "thirty days", "sixty days"))
        r = self.repo.run("records", "--base", "main", "x")
        self.assertEqual(r.stdout.splitlines(), [
            'openspec/specs/cap/decisions.md  (the change touches cap; its Rationale for '
            '"Records are kept" covers a requirement the change changes)'])


class FoundByBugHunterRationaleRunTests(unittest.TestCase):
    """Found by bug-hunter in its run over the Rationale work."""

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_a_main_spec_openspec_cannot_read_leaves_rationale_titles_unchecked(self):
        repo = Repo(self)
        repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace("## Purpose\n\nWhat cap does.\n\n", ""))
        repo.write("openspec/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(RATIONALE,)))
        repo.change("x")
        r = repo.check("x")
        self.assertNotIn("error [record]", r.stdout)
        self.assertIn("openspec-show", r.stdout)

    def test_reasoning_may_start_with_a_word_another_kind_uses_as_a_label(self):
        text = record(rationale=("- **Rationale: Records are kept.**\n  Thirty days was chosen over\n"
                                 "  Instead: of ninety, which the auditors refused.\n  Evidence: the refusal, #7\n",))
        self.assertEqual(findings(text), [])
        (e,) = [e for e in spec_check.parse_record(text).entries if e.kind == "Rationale"]
        self.assertIn("Instead: of ninety", e.reasoning)

    def test_a_blank_line_inside_an_entry_says_so(self):
        text = record(rationale=("- **Rationale: Records are kept.**\n  Thirty days.\n\n  More.\n",))
        self.assertTrue(any("a blank line ends" in m for _, _, m in findings(text)), findings(text))

    def test_the_blank_line_hint_needs_a_blank_line(self):
        unlabelled = CONSTRAINT.replace("  Because:", "  plain text first\n  Because:")
        problems = findings(record(constraints=(unlabelled,)))
        self.assertTrue(problems)
        self.assertFalse(any("blank line" in m for _, _, m in problems), problems)

    def test_a_rationale_error_says_which_titles_it_may_name(self):
        text = record(rationale=(RATIONALE.replace("Records are kept", "Records are shredded"),))
        (problem,) = findings(text, requirements={"Records are kept"})
        self.assertIn('"Records are shredded" names no requirement of cap', problem[2])
        self.assertIn("one an open change adds, modifies or renames to", problem[2])

class MutationGapRationaleRunTests(unittest.TestCase):
    """Mutants that survived the mutation testing of bug-hunter's run over
    the Rationale work, each killed by a test here."""

    RENAME = ("## RENAMED Requirements\n\n- FROM: `### Requirement: Records are kept`\n"
              "- TO: `### Requirement: Records are retained`\n")

    def test_a_wrapped_evidence_value_joins_its_line(self):
        wrapped = "- **Rationale: Records are kept.**\n  Thirty days.\n  Evidence:\n    the terms, #4\n"
        text = record(rationale=(wrapped,))
        self.assertEqual(findings(text), [])
        (e,) = [e for e in spec_check.parse_record(text).entries if e.kind == "Rationale"]
        self.assertEqual([v for _, v in e.evidence], ["the terms, #4"])

    def test_a_wrapped_line_under_a_wrong_label_is_one_error(self):
        text = record(rationale=("- **Rationale: Records are kept.**\n  Thirty days.\n"
                                 "  Evidence: the terms, #4\n  Because: of audits.\n    and more.\n",))
        problems = findings(text)
        self.assertEqual([m.split(";")[0] for _, _, m in problems],
                         ["a Rationale entry has no part 'Because'"])
        (e,) = [e for e in spec_check.parse_record(text).entries if e.kind == "Rationale"]
        self.assertEqual([v for _, v in e.evidence], ["the terms, #4"])

    def test_open_titles_are_read_from_the_delta_text(self):
        repo = Repo(self)
        repo.change("x", delta=GOOD_DELTA + "\n## REMOVED Requirements\n\n### Requirement: Records are kept\n\n"
                                            "**Reason**: no longer needed.\n\n**Migration**: none.\n")
        repo.change("y", cap="other")
        corpus = spec_check.Corpus(str(repo.path), requirements=False)
        self.assertEqual(spec_check.open_titles(corpus, "cap"),
                         ({"Records expire"}, {"Records are kept": "the open change x removes"}))
        self.assertEqual(spec_check.open_titles(corpus, "third"), (set(), {}))
        repo.change("x", delta="## RENAMED Requirements\n\n- FROM: `### Requirement: Records are kept`\n"
                               "- TO: `### Requirement: Records are kept`\n")
        corpus = spec_check.Corpus(str(repo.path), requirements=False)
        self.assertEqual(spec_check.open_titles(corpus, "cap"), ({"Records are kept"}, {}))

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_a_change_renaming_a_requirement_moves_its_rationale_title(self):
        repo = Repo(self)
        repo.change("x", delta=self.RENAME)
        why = "- **Rationale: {}.**\n  The reasoning, at more length than one sentence holds.\n  Evidence: the incident, #9\n"
        repo.write("openspec/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(why.format("Records are retained"),)))
        self.assertNotIn("error [record]", repo.check("x").stdout)
        repo.write("openspec/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(why.format("Records are kept"),)))
        self.assertIn('"Records are kept" names a requirement that the open change x renames to '
                      '"Records are retained"', repo.check("specs").stdout)
        out = repo.check("x").stdout
        self.assertIn('renames "Records are kept" to "Records are retained", which '
                      "openspec/specs/cap/decisions.md gives a Rationale entry", out)

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_a_main_spec_openspec_cannot_read_leaves_main_rationale_unchecked(self):
        repo = Repo(self)
        repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace("## Purpose\n\nWhat cap does.\n\n", ""))
        repo.write("openspec/specs/cap/decisions.md", record(rationale=(
            RATIONALE.replace("Records are kept", "Records are shredded"),)))
        self.assertNotIn("error [record]", repo.check("specs").stdout)

    def test_records_names_a_rationale_on_either_side_of_a_rename(self):
        for title in ("Records are kept", "Records are retained"):
            with self.subTest(title=title):
                repo = Repo(self)
                repo.write("openspec/specs/cap/decisions.md", record(rationale=(
                    RATIONALE.replace("Records are kept", title),)))
                repo.git("add", "-A")
                repo.git("commit", "-q", "-m", "record")
                repo.change("x", delta=self.RENAME)
                r = repo.run("records", "--base", "main", "x")
                self.assertIn(f'its Rationale for "{title}" covers a requirement the change changes',
                              r.stdout)


REMOVE_KEPT = ("## REMOVED Requirements\n\n### Requirement: Records are kept\n\n"
               "**Reason**: superseded.\n\n**Migration**: none.\n")
RENAME_KEPT = ("## RENAMED Requirements\n\n- FROM: `### Requirement: Records are kept`\n"
               "- TO: `### Requirement: Records are retained`\n")

class TitleReuseTests(unittest.TestCase):
    """A change may not add or rename to a title it also renames or removes
    away; `check` and `sign` refuse it, and plain renames and removals
    still pass."""

    def reuse(self, delta):
        out = []
        spec_check.check_title_reuse("d.md", delta, out)
        return [(f.line, f.severity, f.kind, f.message) for f in out]

    def test_renaming_away_and_adding_the_same_title_is_refused(self):
        delta = (RENAME_KEPT + "\n## ADDED Requirements\n\n### Requirement: Records are kept\n\n"
                 "The store SHALL checksum each record.\n")
        ((line, severity, category, message),) = self.reuse(delta)
        self.assertEqual((line, severity, category), (8, "error", "title-reuse"))
        self.assertEqual(message, 'this change renames or removes "Records are kept" and also adds '
                         'or renames to "Records are kept"; spec-check doesn\'t support reusing a '
                         "title within one change. Split it into two changes, the second with a "
                         "`Builds on:` line for the first (both can sit in one pull request), or "
                         "choose another title")

    def test_a_swap_is_refused(self):
        delta = ("## RENAMED Requirements\n\n- FROM: `### Requirement: A`\n- TO: `### Requirement: B`\n"
                 "- FROM: `### Requirement: C`\n- TO: `### Requirement: A`\n")
        self.assertEqual([(line, category) for line, _, category, _ in self.reuse(delta)],
                         [(5, "title-reuse")])

    def test_removing_and_renaming_to_the_same_title_is_refused(self):
        delta = (REMOVE_KEPT + "\n## RENAMED Requirements\n\n- FROM: `### Requirement: Old`\n"
                 "- TO: `### Requirement: Records are kept`\n")
        self.assertEqual(len(self.reuse(delta)), 1)

    def test_a_title_reused_twice_is_one_finding_at_the_first_leaving(self):
        # Added at lines 3 and 7, removed at 13, the FROM of a rename at 21: one
        # finding, at the later of the first arrival and the first leaving.
        delta = ("## ADDED Requirements\n\n### Requirement: Records are kept\n\nThe store SHALL x.\n\n"
                 "### Requirement: Records are kept\n\nThe store SHALL y.\n\n"
                 + REMOVE_KEPT + "\n## RENAMED Requirements\n\n- FROM: `### Requirement: Records are kept`\n"
                 "- TO: `### Requirement: Other`\n")
        self.assertEqual([(line, kind) for line, _, kind, _ in self.reuse(delta)], [(13, "title-reuse")])

    def test_plain_renames_and_removals_pass(self):
        for delta in (RENAME_KEPT, REMOVE_KEPT, RENAME_KEPT + "\n" + REMOVE_KEPT.replace("kept", "read"),
                      "## RENAMED Requirements\n\n- FROM: `### Requirement: Records are kept`\n"
                      "- TO: `### Requirement: Records are Kept`\n"):
            with self.subTest(delta=delta):
                self.assertEqual(self.reuse(delta), [])


class FoundByBugHunterTitleReuseIteration2Tests(unittest.TestCase):
    """Iteration 2 of the title-reuse run: a delta read with OpenSpec's
    normalization, a leading byte-order mark dropped, `\\r` read as a line
    end and U+FEFF read as space."""

    REUSE = (RENAME_KEPT + "\n## ADDED Requirements\n\n### Requirement: Records are kept\n\n"
             "The store SHALL x.\n")

    def test_a_leading_byte_order_mark_hides_nothing(self):
        out = []
        spec_check.check_title_reuse("d.md", "\ufeff" + self.REUSE, out)
        self.assertEqual([f.kind for f in out], ["title-reuse"])
        self.assertEqual(spec_check.delta_changes("\ufeff" + RENAME_KEPT)[1],
                         [(3, "Records are kept", "Records are retained")])

    def test_a_carriage_return_alone_ends_a_line(self):
        self.assertEqual(spec_check.delta_changes(RENAME_KEPT.replace("\n", "\r"))[1],
                         [(3, "Records are kept", "Records are retained")])

    def test_a_zero_width_no_break_space_is_space(self):
        text = ("## REMOVED Requirements\ufeff\n\n###\ufeffRequirement: Records are kept\ufeff\n\n"
                "- \ufeff`### Requirement: Records are read`\n")
        self.assertEqual([t for _, t in spec_check.delta_changes(text)[0]],
                         ["Records are kept", "Records are read"])


class DeltaLineSeparatorTests(unittest.TestCase):
    """A delta's lines read with JavaScript's `.`, as OpenSpec 1.16.0's
    parseDeltaSpec reads them."""

    LS, PS = "\u2028", "\u2029"

    def test_a_line_separator_ends_no_match_as_openspec_reads_it(self):
        # Each case as OpenSpec 1.16.0's parseDeltaSpec reads it.
        ls, ps = self.LS, self.PS
        cases = [
            # A title ending in a closing run and a line separator: OpenSpec
            # reads "Foo", which the change also removes.
            (f"## ADDED Requirements\n### Requirement: Foo ##{ls}\n\n## REMOVED Requirements\n"
             "### Requirement: Foo\n", ["Foo"], [("Foo",)], []),
            # A separator inside an ADDED title: that title is no requirement.
            (f"## ADDED Requirements\n### Requirement: Foo{ls}bar\n\n## REMOVED Requirements\n"
             "### Requirement: Foo bar\n", [], [("Foo bar",)], []),
            # A separator inside a heading: no new section.
            (f"## ADDED Requirements\n### Requirement: A\n\n## Notes{ps}x\n### Requirement: Foo\n",
             ["A", "Foo"], [], []),
            # A separator inside a FROM line: no rename.
            (f"## RENAMED Requirements\n- FROM: `### Requirement: Old{ls}x`\n"
             "- TO: `### Requirement: New`\n", [], [], []),
            (f"## REMOVED Requirements\n- `### Requirement: Gone{ps}x`\n", [], [], []),
        ]
        for text, added, removed, renames in cases:
            with self.subTest(text=text):
                _, got_removed, got_renames, got_added = spec_check.delta_requirements(text)
                self.assertEqual([t for _, t in got_added], added)
                self.assertEqual([(t,) for _, t in got_removed], removed)
                self.assertEqual(got_renames, renames)
        out = []
        spec_check.check_title_reuse("d.md", cases[0][0], out)
        self.assertEqual(len(out), 1)
        out = []
        spec_check.check_title_reuse("d.md", cases[1][0], out)
        self.assertEqual(out, [])


class RationaleInARecordWithNoSpecTests(unittest.TestCase):
    def test_a_main_record_with_no_spec_gets_only_the_no_spec_finding(self):
        if not HAS_OPENSPEC:
            self.skipTest(NEEDS)
        repo = Repo(self)
        repo.write("openspec/specs/gone/decisions.md", record(cap="gone", rationale=(RATIONALE,)))
        found = [line for line in repo.check("specs").stdout.splitlines()
                 if "openspec/specs/gone/decisions.md" in line]
        self.assertEqual(len(found), 1, found)
        self.assertIn("no spec in openspec/specs/ is 'gone'", found[0])


class ConsistencyReadChecklistTests(unittest.TestCase):
    """consistency-read.md's checklist asks the reader to flag a record
    entry that repeats a requirement."""

    def test_item_16_flags_a_record_entry_a_requirement_already_states(self):
        text = (pathlib.Path(spec_check.__file__).parent.parent / "consistency-read.md").read_text()
        items = re.findall(r"^(\d+)\. ", text.split("Then go through the checklist", 1)[1], re.M)
        self.assertEqual(items, [str(n) for n in range(1, 18)])
        item = re.search(r"^16\. (.*?)(?=^\S|\Z)", text, re.M | re.S).group(1)
        for words in ("Constraint or Rejected", "requirement or scenario already states",
                      "*because* sentence", "Rationale entry"):
            self.assertIn(words, " ".join(item.split()))
        both_sides = re.search(r"\(items ([\d, ]+)\), quote both sides", text).group(1)
        self.assertIn("16", both_sides.replace(" ", "").split(","))

    def test_item_17_flags_ungrounded_reasoning_in_the_round_it_appears(self):
        text = (pathlib.Path(spec_check.__file__).parent.parent / "consistency-read.md").read_text()
        item = " ".join(re.search(r"^17\. (.*?)(?=^\S|\Z)", text, re.M | re.S).group(1).split())
        for words in ("names a person as its reason", "who decided or amended a decision, or when",
                      "reversed by <name> on <date>", "decided on <date>", "states a preference",
                      "claims a fact without Evidence", "only restates its requirement",
                      "its requirement's own test as its only Evidence",
                      "a requirement guards against", "move a rejection",
                      "in this round", "ask the person who decided for the evidence",
                      "reopen the decision", "strike the entry"):
            self.assertIn(words, item)


class MutationGapRun9Tests(unittest.TestCase):
    """Mutants that survived bug-hunter's ninth run on this change, each
    killed by a test here."""

    def test_a_file_directly_in_the_changes_folder_is_not_a_change(self):
        repo = Repo(self)
        repo.git("checkout", "-q", "-b", "spec")
        repo.write("openspec/changes/README.md", "Open changes live here.\n")
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "readme")
        self.assertEqual(spec_check.open_changes(str(repo.path), "HEAD"), set())
        self.assertEqual(spec_check.unread_at(str(repo.path), "HEAD", "main"), [])


class MutationGapRun8Tests(unittest.TestCase):
    def test_a_title_out_of_form_is_one_error(self):
        problems = findings(record().replace("constraints, rejected", "rules, rejected"))
        self.assertEqual([m for _, line, m in problems if line == 1],
                         [m for _, line, m in problems if line == 1 and "the first line must be" in m])
        self.assertEqual(len([1 for _, line, _ in problems if line == 1]), 1, problems)

    def test_a_star_stays_within_one_name(self):
        self.assertTrue(spec_check.path_matches("src/*.py", "src/x.py"))
        self.assertFalse(spec_check.path_matches("src/*.py", "src/lib/x.py"))


class OpsxRulesTests(unittest.TestCase):
    """opsx-rules.yaml is merged into openspec/config.yaml by hand; OpenSpec
    must read it with no warning and show each artifact its rules."""

    RULES = pathlib.Path(spec_check.__file__).parent.parent / "opsx-rules.yaml"

    def rules(self):
        """{artifact: [rule]} read from the file's plain two-level layout."""
        out, artifact = {}, None
        for line in self.RULES.read_text().splitlines():
            if m := re.match(r"^  (\w+):$", line):
                artifact = m.group(1)
                out[artifact] = []
            elif m := re.match(r"^    - (.+)$", line):
                out[artifact].append(m.group(1))
        return out

    def test_the_rules_name_spec_driven_artifacts(self):
        self.assertTrue(set(self.rules()) <= {"proposal", "specs", "design", "tasks"}, self.rules())
        self.assertTrue(all(self.rules().values()))

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_openspec_shows_each_artifact_its_rules(self):
        repo = Repo(self)
        repo.write("openspec/config.yaml", "schema: spec-driven\n" + self.RULES.read_text())
        repo.change("x")
        for artifact, rules in self.rules().items():
            with self.subTest(artifact=artifact):
                r = subprocess.run(["openspec", "instructions", artifact, "--change", "x"],
                                   cwd=repo.path, capture_output=True, text=True, env=ENV)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertNotIn("Unknown artifact ID", r.stdout + r.stderr)
                self.assertNotIn("must be an array", r.stdout + r.stderr)
                for rule in rules:
                    self.assertIn(rule, r.stdout)

class RecordDiffEvolutionTests(unittest.TestCase):
    """The evolution check reads the lines a branch changes in a main
    record, against the merge base, skipping the credit rules."""

    def setUp(self):
        self.repo = Repo(self)

    def evolution(self):
        r = self.repo.check("specs")
        return [line for line in r.stdout.splitlines() if "error [evolution]" in line]

    def test_a_history_line_the_branch_adds_to_a_record_is_an_error(self):
        self.repo.git("checkout", "-q", "-b", "spec")
        self.repo.write("openspec/specs/cap/decisions.md", record(constraints=(CONSTRAINT.replace(
            "a leaked store leaks every seat.", "a leaked store leaks every seat, previously one."),)))
        (error,) = self.evolution()
        self.assertTrue(error.startswith("openspec/specs/cap/decisions.md:5: error [evolution]"), error)

    def test_a_history_line_already_on_the_base_is_not_read(self):
        self.repo.write("openspec/specs/cap/decisions.md", record(constraints=(CONSTRAINT.replace(
            "a leaked store leaks every seat.", "a leaked store leaks every seat, previously one."),)))
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "old record")
        self.repo.git("checkout", "-q", "-b", "spec")
        self.assertEqual(self.evolution(), [])
        text = (self.repo.path / "openspec/specs/cap/decisions.md").read_text()
        self.repo.write("openspec/specs/cap/decisions.md",
                        text.replace("Paths: src/app.py", "Paths: src/"))
        self.assertEqual(self.evolution(), [])

    def test_a_credit_the_branch_adds_to_a_record_is_skipped(self):
        self.repo.git("checkout", "-q", "-b", "spec")
        self.repo.write("openspec/specs/cap/decisions.md", record(constraints=(CONSTRAINT.replace(
            "two seats leaked in one incident, #12", "two seats leaked (Linux, 2024-05-01), #12"),)))
        self.assertEqual(self.evolution(), [])

    def test_changed_lines_are_those_that_differ_from_the_old_text(self):
        self.assertEqual(spec_check.changed_lines(None, "a\nb"), {1, 2})
        self.assertEqual(spec_check.changed_lines("a\nb\nc\n", "a\nB\nc\nd\n"), {2, 4})
        self.assertEqual(spec_check.changed_lines("a\nb\n", "b\n"), set())


from test_spec_check import HandbackBase  # noqa: E402


class FoundByBugHunterNoFoldHandbackTests(HandbackBase):
    def test_a_hand_back_editing_only_a_record_with_no_change_folder_is_blocked(self):
        self.repo.write("openspec/specs/cap/decisions.md", record())
        self.repo.git("add", "-A")
        signed_commit(self, self.repo, read="deferred")
        self.blocked(self.hook("gh pr ready 7 -R o/r", pr=self.pr()),
                     "openspec/specs/cap/decisions.md")

    def test_the_judgement_fetches_what_it_reads_with_gh_s_token(self):
        """read_units reads the decision-records configuration, a file's
        contents the partial clone lacks, so git fetches it while judging:
        that fetch carries gh's credential helper and never prompts."""
        sys.path.insert(0, str(HERE))
        import handback
        seen = {}

        def unread_at(repo, head, base_ref):
            seen.update({k: v for k, v in os.environ.items()
                         if k.startswith("GIT_CONFIG_") or k == "GIT_TERMINAL_PROMPT"})
            return []
        self.repo.write("openspec/specs/cap/decisions.md", record())
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "record")
        with mock.patch.object(handback.sc, "unread_at", unread_at), \
                mock.patch.object(handback.sc, "GH", str(self.gh)), \
                mock.patch.dict(os.environ, {"SPEC_CHECK_CACHE": str(self.cache)}):
            self.assertEqual(handback.unread(self.pr()), "")
        self.assertEqual(seen.get("GIT_TERMINAL_PROMPT"), "0")
        helpers = [seen[k.replace("KEY", "VALUE")] for k in seen
                   if k.startswith("GIT_CONFIG_KEY_") and seen[k] == "credential.helper"]
        self.assertEqual(helpers[0], "")
        self.assertIn("auth git-credential", helpers[-1])
        self.assertNotIn("GIT_TERMINAL_PROMPT", {k for k in os.environ if k == "GIT_TERMINAL_PROMPT"
                                                  and os.environ[k] == "0" and k not in ENV})


class FoundByBugHunterNoFoldRunTests(unittest.TestCase):
    def test_check_with_ref_reads_the_record_diff_against_the_refs_merge_base(self):
        repo = Repo(self)
        old = record(constraints=(CONSTRAINT.replace(
            "a leaked store leaks every seat.", "a leaked store leaks every seat, previously one."),))
        repo.write("openspec/specs/cap/decisions.md", old)
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "record")
        repo.git("checkout", "-q", "-b", "feat")
        repo.write("openspec/specs/cap/decisions.md", old.replace("Paths: src/app.py", "Paths: src/"))
        repo.git("commit", "-qam", "feat edits another line")
        repo.git("checkout", "-q", "main")
        repo.write("openspec/specs/cap/decisions.md", record())
        repo.git("commit", "-qam", "main drops the history line")
        r = repo.check("--ref", "feat", "specs")
        self.assertNotIn("error [evolution]", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_changed_lines_number_lines_as_the_evolution_check_does(self):
        old = "a\u2028b\nc\nd\n"
        self.assertEqual(spec_check.changed_lines(old, "a\u2028b\nc\nD\n"), {3})
        self.assertEqual(spec_check.changed_lines(None, "a\fb\nc"), {1, 2})

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_a_record_naming_a_removed_requirement_errors_though_another_change_is_unreadable(self):
        repo = Repo(self)
        repo.change("x", delta="## REMOVED Requirements\n\n### Requirement: Records are kept\n\n"
                               "**Reason**: no longer needed.\n\n**Migration**: none.\n")
        repo.change("y", cap="other", delta=GOOD_DELTA.replace("Records expire", "Unreadable"))
        repo.write("openspec/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(RATIONALE,)))
        real_show = spec_check.show

        def show(kind, name, files):
            if any("Unreadable" in text for text in files.values()):
                return None, "broken"
            return real_show(kind, name, files)
        with mock.patch.object(spec_check, "show", show):
            corpus = spec_check.Corpus(str(repo.path))
            self.assertIn("y", corpus.unread)
            _, _, found, *_ = spec_check.run_checks(str(repo.path), str(repo.path), "main",
                                                    ["x", "specs"], False)
        messages = [f.message for f in found if f.severity == "error"]
        self.assertIn('removes "Records are kept", which openspec/specs/cap/decisions.md gives '
                      "a Rationale entry; delete that entry from the record", messages)
        self.assertIn('Rationale: "Records are kept" names a requirement that the open change x '
                      "removes; delete the entry, or retitle it to the requirement it explains",
                      messages)

    def test_a_record_naming_a_removed_requirement_errors_without_openspec(self):
        repo = Repo(self)
        repo.change("x", delta="## REMOVED Requirements\n\n### Requirement: Records are kept\n\n"
                               "**Reason**: no longer needed.\n\n**Migration**: none.\n")
        repo.write("openspec/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(RATIONALE,)))
        env = dict(ENV, PATH=os.pathsep.join(p for p in ENV["PATH"].split(os.pathsep)
                                             if not (pathlib.Path(p) / "openspec").exists()))
        r = repo.check("x", "specs", env=env)
        self.assertIn('"Records are kept" names a requirement that the open change x removes',
                      r.stdout)
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_the_opsx_rules_point_rationale_at_the_main_record(self):
        text = (HERE.parent / "opsx-rules.yaml").read_text()
        self.assertNotIn("change's decisions.md", text)


class RecordKeptFileTests(unittest.TestCase):
    """A kept file beside a decision record keeps the evolution errors a
    person chose to keep in that record's lines, whether or not an open
    change touches the capability."""

    LINE = "Because: a leaked store leaks every seat, previously one."

    def setUp(self):
        self.repo = Repo(self)
        self.repo.git("checkout", "-q", "-b", "spec")

    def write(self, where="openspec/specs/cap", asked=True):
        self.repo.write(f"{where}/decisions.md", record(constraints=(CONSTRAINT.replace(
            "Because: a leaked store leaks every seat.", self.LINE),)))
        self.repo.write(f"{where}/.spec-check-kept",
                        f"decisions.md: «{self.LINE}» kept{' (asked)' if asked else ''}: "
                        "the line quotes the incident report\n")

    def test_a_kept_record_line_is_not_an_error(self):
        self.write()
        r = self.repo.check("specs")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("openspec/specs/cap/decisions.md:5: kept (asked) [evolution] the line "
                      "quotes the incident report", r.stdout)
        self.assertNotIn("error [evolution]", r.stdout)

    def test_an_unasked_entry_keeps_nothing(self):
        self.write(asked=False)
        r = self.repo.check("specs")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("error [kept]", r.stdout)
        self.assertIn("error [evolution]", r.stdout)

    def test_a_kept_file_covers_its_record_while_a_change_touches_the_capability(self):
        self.repo.change("good")
        self.write()
        r = self.repo.check("specs", "good")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("kept (asked) [evolution]", r.stdout)

    def test_a_kept_file_beside_a_configured_record(self):
        self.repo.write("openspec/spec-check.yaml",
                        "decision-records: openspec/decisions/<capability>/decisions.md\n")
        self.write("openspec/decisions/cap")
        r = self.repo.check("specs")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("openspec/decisions/cap/decisions.md:5: kept (asked)", r.stdout)

    def test_sign_counts_a_kept_record_line_and_a_kept_file_edit_is_due(self):
        self.write()
        self.repo.git("add", "-A")
        value = signed_commit(self, self.repo)
        self.assertIn("1 evolution kept", value)
        self.assertIn("read by a fresh subagent: openspec/specs/cap/decisions.md;", value)
        kept = self.repo.path / "openspec/specs/cap/.spec-check-kept"
        kept.write_text(kept.read_text().replace("incident report", "incident report, #12"))
        self.repo.git("add", "-A")
        r = self.repo.run("sign", "--read", "subagent", "--base", "main", "--no-validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("read by a fresh subagent: openspec/specs/cap/decisions.md;",
                      r.stdout.strip().splitlines()[-1])


class FoundByBugHunterNoFoldIteration2Tests(unittest.TestCase):
    LINE = RecordKeptFileTests.LINE

    def setUp(self):
        self.repo = Repo(self)
        self.repo.git("checkout", "-q", "-b", "spec")

    def test_staging_only_a_configured_records_kept_file_checks_the_record(self):
        self.repo.write("openspec/spec-check.yaml",
                        "decision-records: openspec/decisions/<capability>/decisions.md\n")
        self.repo.write("openspec/decisions/cap/decisions.md", record(constraints=(CONSTRAINT.replace(
            "Because: a leaked store leaks every seat.", self.LINE),)))
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "wip", "--trailer", "Spec-check: skipped (wip)")
        self.repo.write("openspec/decisions/cap/.spec-check-kept",
                        f"decisions.md: «{self.LINE}» kept: no person asked\n")
        self.repo.git("add", "-A")
        r = self.repo.run("sign", "--read", "deferred", "--base", "main", "--no-validate")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("the entry has no `(asked)`", r.stdout)

    def test_a_kept_entry_for_a_record_line_that_merged_is_not_called_gone(self):
        self.repo.write("openspec/specs/cap/decisions.md", record(constraints=(CONSTRAINT.replace(
            "Because: a leaked store leaks every seat.", self.LINE),)))
        self.repo.write("openspec/specs/cap/.spec-check-kept",
                        f"decisions.md: «{self.LINE}» kept (asked): quotes the report\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "record")
        self.repo.git("checkout", "-q", "main")
        self.repo.git("merge", "-q", "--ff-only", "spec")
        self.repo.git("checkout", "-q", "-b", "next")
        r = self.repo.check("specs")
        self.assertNotIn("matches no evolution error", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)
        text = (self.repo.path / "openspec/specs/cap/decisions.md").read_text()
        self.repo.write("openspec/specs/cap/decisions.md", text.replace(self.LINE, "Because: gone."))
        self.assertIn("matches no evolution error", self.repo.check("specs").stdout)

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_a_record_of_a_capability_an_open_change_creates_is_held_to_its_titles(self):
        self.repo.change("newc", cap="newcap", delta=GOOD_DELTA.replace(
            "## ADDED Requirements", "## Purpose\n\nWhat newcap does: it keeps the records it is given.\n\n"
            "## ADDED Requirements"))
        why = "- **Rationale: {}.**\n  The reasoning, at more length than one sentence holds.\n  Evidence: the incident, #9\n"
        self.repo.write("openspec/specs/newcap/decisions.md", record(
            cap="newcap", constraints=(), rejected=(),
            rationale=(why.format("Records expire"), why.format("Typo title nobody has"))))
        r = self.repo.check("specs")
        self.assertIn('"Typo title nobody has" names no requirement of newcap', r.stdout)
        self.assertNotIn('"Records expire" names', r.stdout)
        self.assertNotIn("no spec in openspec/specs/ is 'newcap'", r.stdout)


    def test_present_lines_reads_a_record_as_markdown_lines_do(self):
        class FakeCorpus:
            records = {"r.md": "\ufeffFirst  line\r\nsecond\n"}
        self.assertEqual(spec_check.present_lines(FakeCorpus(), "r.md"), {"First line", "second", ""})
        self.assertEqual(spec_check.present_lines(FakeCorpus(), "gone.md"), set())


OTHER_SPEC = MAIN_SPEC.replace("# cap Specification", "# other Specification").replace(
    "What cap does.", "What other does.").replace("Records are kept", "Logs are kept")


class ChangeChecksItsRecordsTests(unittest.TestCase):
    """`check <change>` checks the main decision records the change bears
    on: the record of each capability it touches, each record whose own
    Paths match a file the branch changes, and each record the branch edits
    or whose kept file it edits. Any other record is left to `check
    specs`."""

    BARE = "- **Rationale: Records are kept.**\n  Thirty days covers every audit window.\n"
    WHY = ("- **Rationale: {}.**\n  The reasoning, at more length than one sentence holds.\n"
           "  Evidence: the incident, #9\n")

    def setUp(self):
        self.repo = Repo(self)
        self.repo.write("openspec/specs/other/spec.md", OTHER_SPEC)
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "other")

    def record_errors(self, *args):
        r = self.repo.check(*args)
        return r, [line for line in r.stdout.splitlines() if "error [record]" in line]

    def commit_and_branch(self):
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "--allow-empty", "-m", "records")
        self.repo.git("checkout", "-q", "-b", "spec")

    def test_a_rationale_with_no_evidence_fails_check_of_the_change(self):
        self.repo.write("openspec/specs/cap/decisions.md", record(rationale=(self.BARE,)))
        self.repo.change("x")
        r, (error,) = self.record_errors("x")
        self.assertIn("openspec/specs/cap/decisions.md:", error)
        self.assertIn("the Rationale entry has no Evidence", error)
        self.assertEqual(r.returncode, 1, r.stdout)

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_a_rationale_title_that_is_not_exact_fails_check_of_the_change(self):
        self.repo.write("openspec/specs/cap/decisions.md", record(rationale=(
            self.WHY.format("Records are Kept"),)))
        self.repo.change("x")
        r, (error,) = self.record_errors("x")
        self.assertIn('"Records are Kept" names no requirement of cap', error)
        self.assertIn("Records are kept", error.split("names no requirement", 1)[1])
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_a_record_the_branch_edits_is_checked_with_any_change(self):
        self.commit_and_branch()
        self.repo.change("x")
        self.repo.write("openspec/specs/other/decisions.md", record(
            cap="other", rationale=(self.BARE.replace("Records", "Logs"),)))
        _, (error,) = self.record_errors("x")
        self.assertIn("openspec/specs/other/decisions.md:", error)
        self.assertIn("no Evidence", error)
        # Staged, or committed on the branch, it is still the branch's edit.
        self.repo.git("add", "-A")
        self.assertEqual(len(self.record_errors("x")[1]), 1)
        self.repo.git("commit", "-q", "-m", "edit")
        self.assertEqual(len(self.record_errors("x")[1]), 1)

    def test_editing_only_a_records_kept_file_checks_the_record(self):
        self.repo.write("openspec/specs/other/decisions.md", record(
            cap="other", rationale=(self.BARE.replace("Records", "Logs"),)))
        self.commit_and_branch()
        self.repo.change("x")
        self.assertEqual(self.record_errors("x")[1], [])
        self.repo.write("openspec/specs/other/.spec-check-kept", "")
        self.assertEqual(len(self.record_errors("x")[1]), 1)

    def test_a_record_whose_paths_name_a_file_the_branch_deletes_is_checked(self):
        self.repo.write("openspec/specs/other/decisions.md", record(cap="other"))
        self.commit_and_branch()
        self.repo.change("x")
        self.assertEqual(self.record_errors("x")[1], [])
        self.repo.git("rm", "-q", "src/app.py")
        _, errors = self.record_errors("x")
        # record() holds CONSTRAINT (Paths: src/app.py) and REJECTED
        # (Paths: src/). src/app.py was the only file under src/, so both
        # paths now match nothing.
        self.assertEqual([e.split("error [record] ", 1)[1].split(" matches")[0] for e in errors],
                         ["Paths: src/app.py", "Paths: src/"])

    def test_a_record_the_change_does_not_bear_on_is_left_to_check_specs(self):
        self.repo.write("openspec/specs/other/decisions.md", record(
            cap="other", constraints=(), rejected=(), rationale=(self.BARE.replace("Records", "Logs"),)))
        self.commit_and_branch()
        self.repo.change("x")
        r, errors = self.record_errors("x")
        self.assertEqual((errors, r.returncode), ([], 0), r.stdout)
        self.assertEqual(len(self.record_errors("specs")[1]), 1)

    def test_a_record_is_reported_once_whatever_the_targets(self):
        # x reaches cap's record; only y reaches other's. Changes are checked
        # in sorted order, so code that read only the first change's records
        # would miss other's.
        self.repo.write("openspec/specs/cap/decisions.md", record(rationale=(self.BARE,)))
        self.repo.write("openspec/specs/other/decisions.md", record(
            cap="other", rationale=(self.BARE.replace("Records", "Logs"),)))
        self.repo.change("x")
        self.repo.change("y", cap="other", delta=GOOD_DELTA.replace("Records", "Logs"))
        for targets in (("x", "y"), (), ("x", "specs")):
            with self.subTest(targets=targets):
                errors = self.record_errors(*targets)[1]
                self.assertEqual(sorted(e.split(":", 1)[0] for e in errors),
                                 ["openspec/specs/cap/decisions.md",
                                  "openspec/specs/other/decisions.md"], errors)

    def test_a_branch_ref_checks_the_records_it_edits(self):
        self.commit_and_branch()
        self.repo.change("x")
        self.repo.write("openspec/specs/other/decisions.md", record(
            cap="other", rationale=(self.BARE.replace("Records", "Logs"),)))
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "edit")
        self.repo.git("checkout", "-q", "main")
        r = self.repo.check("--ref", "spec", "x")
        self.assertEqual(len([l for l in r.stdout.splitlines() if "error [record]" in l]), 1,
                         r.stdout)

    def test_with_no_merge_base_the_touched_capabilitys_record_is_still_checked(self):
        self.repo.write("openspec/specs/cap/decisions.md", record(rationale=(self.BARE,)))
        self.repo.git("checkout", "-q", "--orphan", "unrelated")
        self.repo.git("commit", "-q", "--allow-empty", "-m", "unrelated")
        self.repo.git("checkout", "-q", "main")
        self.repo.change("x")
        r = self.repo.run("check", "--base", "unrelated", "--no-validate", "x")
        self.assertNotIn("Traceback", r.stderr)
        (error,) = [l for l in r.stdout.splitlines() if "error [record]" in l]
        self.assertIn("no Evidence", error)

    def test_sign_refuses_over_a_record_the_staged_change_bears_on(self):
        self.repo.write("openspec/specs/cap/decisions.md", record(rationale=(self.BARE,)))
        self.commit_and_branch()
        self.repo.change("x")
        self.repo.git("add", "-A")
        r = self.repo.run("sign", "--read", "deferred", "--base", "main", "--no-validate")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("openspec/specs/cap/decisions.md:", r.stdout)
        self.assertIn("no Evidence", r.stdout)

    def test_with_no_merge_base_an_unchanged_history_line_is_not_flagged(self):
        self.repo.write("openspec/specs/cap/decisions.md", record(constraints=(CONSTRAINT.replace(
            "a leaked store leaks every seat.", "a leaked store leaks every seat, previously one."),)))
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "old record")
        self.repo.git("checkout", "-q", "--orphan", "unrelated")
        self.repo.git("commit", "-q", "--allow-empty", "-m", "unrelated")
        self.repo.git("checkout", "-q", "main")
        self.repo.change("x")
        for targets in (("x",), ("specs",)):
            with self.subTest(targets=targets):
                r = self.repo.run("check", "--base", "unrelated", "--no-validate", *targets)
                self.assertNotIn("error [evolution]", r.stdout)
                self.assertIn("openspec/specs/cap/decisions.md: check [evolution] no merge base "
                              "with unrelated", r.stdout)


    def test_with_no_head_commit_every_record_line_is_new(self):
        # An orphan branch has no commit yet, so nothing is old: a history
        # line in the staged record is the branch's own.
        self.repo.git("checkout", "-q", "--orphan", "fresh")
        self.repo.write("openspec/specs/cap/decisions.md", record(constraints=(CONSTRAINT.replace(
            "a leaked store leaks every seat.", "a leaked store leaks every seat, previously one."),)))
        self.repo.git("add", "-A")
        r = self.repo.run("sign", "--read", "deferred", "--base", "main", "--no-validate")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("openspec/specs/cap/decisions.md:5: error [evolution]", r.stdout)
        self.assertNotIn("no merge base", r.stdout)

    def test_with_no_head_commit_check_reads_every_record_the_branch_adds(self):
        # On a branch with no commit yet, every file is the branch's own, as
        # sign reads it; check must agree.
        self.repo.git("checkout", "-q", "--orphan", "fresh")
        self.repo.write("openspec/specs/other/decisions.md", record(cap="other", constraints=(
            CONSTRAINT.replace("a leaked store leaks every seat.",
                               "a leaked store leaks every seat, previously one."),)))
        self.repo.change("x")
        r = self.repo.check("x")
        self.assertIn("openspec/specs/other/decisions.md:5: error [evolution]", r.stdout)

    def test_with_no_head_commit_records_says_to_read_the_record_whole(self):
        self.repo.write("openspec/specs/other/decisions.md", record(cap="other"))
        self.commit_and_branch()
        self.repo.git("checkout", "-q", "--orphan", "fresh")
        self.repo.change("x")
        r = self.repo.run("records", "--base", "main", "x")
        self.assertIn("openspec/specs/other/decisions.md", r.stdout)
        self.assertNotIn("merge base", r.stdout + r.stderr)
        self.assertIn("read it whole", r.stdout)

if __name__ == "__main__":
    unittest.main()

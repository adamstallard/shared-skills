#!/usr/bin/env python3
"""Tests for spec-check's decision records: the configured location, the
format checks, the rationale check, the reader's list, the fold at archive,
and the OpenSpec behaviour the records rely on.

Standard library only:

    python3 test_decision_records.py

Each test builds a throwaway git repository, as test_spec_check.py does,
and the tests that need the OpenSpec CLI skip unless 1.15.0 or later is on
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

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import spec_check  # noqa: E402
from test_spec_check import (ENV, GOOD_DELTA, GOOD_PROPOSAL, HAS_OPENSPEC, MAIN_SPEC,  # noqa: E402
                             Repo, kinds, signed_commit)
from test_spec_check import TASKS  # noqa: E402
from test_spec_check import Stack as StackRepo  # noqa: E402

NEEDS = "needs OpenSpec 1.15.0 or later"

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


def record(cap="cap", constraints=(CONSTRAINT,), rejected=(REJECTED,), retired=(), rationale=()):
    text = f"# {cap}: constraints and rejected alternatives\n"
    for heading, entries in (("Constraints", constraints), ("Rejected", rejected),
                             ("Rationale", rationale), ("Retired", retired)):
        if entries:
            text += f"\n## {heading}\n" + "\n".join(entries)
    return text


def findings(text, change=False, names=("src/app.py", "src/lib/x.py"), requirements=None):
    """[(severity, line, message)] of check_record on text, against a tree
    holding names, and with requirements, the titles a Rationale entry may
    name (None: not checked)."""
    class FakeBase:
        def change_names(self):
            return list(names)
    out = []
    spec_check.check_record("r.md", text, FakeBase(), out, change=change, cap="cap",
                            requirements=requirements)
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

    def test_the_retired_decisions_first_key_is_a_check(self):
        template, problems = spec_check.parse_config("decisions-first: enforce\n")
        self.assertEqual(template, spec_check.DEFAULT_RECORD)
        self.assertEqual([(n, sev) for n, sev, _ in problems], [(1, "check")])
        self.assertIn("no longer reads decisions-first", problems[0][2])

    def test_an_unknown_key_or_line_is_an_error(self):
        for text, what in (("decision-record: openspec/x/<capability>/d.md\n", "reads no key"),
                           ("- a list\n", "not a `key: value` line"),
                           ("decision-records: 'unclosed\n", "not one quoted string"),
                           ("decision-records: openspec/a/<capability>/d.md\n"
                            "decision-records: openspec/b/<capability>/d.md\n", "set twice")):
            with self.subTest(text=text):
                _, problems = spec_check.parse_config(text)
                self.assertEqual([sev for _, sev, _ in problems], ["error"])
                self.assertIn(what, problems[0][2])

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

    def test_the_title_must_name_the_capability_in_the_form(self):
        self.assertIn("the first line must be",
                      " ".join(m for _, _, m in findings(record().replace("constraints and", "rules and"))))
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
                          "credentials.", "Credentials")),))))
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

    def test_a_because_of_two_sentences_is_a_check(self):
        text = record(constraints=(CONSTRAINT.replace("every seat.", "every seat. It did once."),))
        self.assertEqual([(sev, n) for sev, n, _ in findings(text)], [("check", 5)])

    def test_a_missing_path_is_an_error_in_a_main_record_and_a_check_in_a_change(self):
        text = record(constraints=(CONSTRAINT.replace("src/app.py", "src/gone.py"),))
        self.assertEqual([sev for sev, _, _ in findings(text)], ["error"])
        self.assertEqual([sev for sev, _, _ in findings(text, change=True)], ["check"])

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

    def test_property_a_record_survives_a_fold_of_nothing(self):
        """Folding an empty change record into a record rewrites it with the
        same entries, parts and order."""
        rng = random.Random(77)
        for _ in range(100):
            cons = [CONSTRAINT.replace("credentials", f"credentials {i}") for i in range(rng.randint(0, 3))]
            rejs = [REJECTED.replace("calls", f"calls {i}") for i in range(rng.randint(0, 3))]
            if not cons and not rejs:
                continue
            text = record(constraints=cons, rejected=rejs)
            folded, problems = spec_check.fold_record("cap", text, record(constraints=(), rejected=()))
            self.assertEqual(problems, [])
            self.assertEqual(folded, text)


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
            self.assertIn("move the rest to openspec/changes/x/specs/cap/decisions.md", r.stdout)

    def test_main_specs_are_not_given_the_rationale_check(self):
        repo = Repo(self)
        repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace(
            "after the last read.", "after the last read. Disks fill. Auditors agree."))
        self.assertNotIn("rationale", kinds(repo.check("specs")))


class ChangeRecordTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.repo.write("openspec/specs/cap/decisions.md", record())
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "record")

    def test_a_change_record_in_the_form_passes(self):
        self.repo.change("x")
        self.repo.write("openspec/changes/x/specs/cap/decisions.md", record(
            constraints=(CONSTRAINT.replace("credentials", "tokens"),), rejected=()))
        r = self.repo.check("x")
        self.assertEqual(kinds(r), [], r.stdout)

    def test_retiring_an_entry_the_main_record_lacks_is_an_error(self):
        self.repo.change("x")
        self.repo.write("openspec/changes/x/specs/cap/decisions.md", record(
            constraints=(), rejected=(), retired=("- **Rejected: A retrieval tool the worker calls.**\n",
                                                  "- **Constraint: Nothing like this.**\n")))
        r = self.repo.check("x")
        self.assertEqual(kinds(r), ["record"], r.stdout)
        self.assertIn("retires a Constraint entry 'Nothing like this.'", r.stdout)

    def test_a_change_record_is_checked_for_history(self):
        self.repo.change("x")
        self.repo.write("openspec/changes/x/specs/cap/decisions.md", record(
            constraints=(CONSTRAINT.replace("seats are shared between roles.",
                                            "seats are shared (Adam, 2026-10-21)."),), rejected=()))
        r = self.repo.check("x")
        self.assertEqual(kinds(r), ["evolution"], r.stdout)
        self.repo.write("openspec/changes/x/.spec-check-kept",
                        "specs/cap/decisions.md: «Holds while: seats are shared (Adam, 2026-10-21).» "
                        "kept (asked): the date is when the seats were split\n")
        self.assertEqual(kinds(self.repo.check("x")), [])

    def test_a_main_record_is_checked_with_the_specs(self):
        self.repo.write("openspec/specs/cap/decisions.md", record().replace("Paths: src/\n", "Paths: lib/\n"))
        r = self.repo.check("specs")
        self.assertEqual(kinds(r), ["record"], r.stdout)
        self.assertIn("openspec/specs/cap/decisions.md:", r.stdout)

    def test_a_record_at_a_configured_location_is_checked(self):
        self.repo.write("openspec/spec-check.yaml", "decision-records: openspec/decisions/<capability>/decisions.md\n")
        self.repo.write("openspec/decisions/cap/decisions.md", record().replace("Instead:", "Instead"))
        r = self.repo.check("specs")
        self.assertIn("openspec/decisions/cap/decisions.md", r.stdout)
        self.assertEqual(r.returncode, 1)
        # The default location is no longer a record.
        self.assertNotIn("openspec/specs/cap/decisions.md:", r.stdout)

    def test_a_record_for_a_capability_with_no_spec_is_a_check(self):
        self.repo.write("openspec/specs/gone/decisions.md", record(cap="gone"))
        r = self.repo.check("specs")
        self.assertIn("openspec/specs/gone/decisions.md: check [record] no spec", r.stdout)


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

    def test_editing_a_change_record_makes_the_change_due(self):
        self.repo.change("good")
        self.repo.git("add", "-A")
        signed_commit(self, self.repo)
        self.repo.write("openspec/changes/good/specs/cap/decisions.md", record(rejected=()))
        self.repo.git("add", "-A")
        r = self.sign("subagent")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("read by a fresh subagent: good;", r.stdout.strip().splitlines()[-1])

    def test_a_main_record_edit_makes_no_change_due(self):
        self.repo.change("good")
        self.repo.git("add", "-A")
        signed_commit(self, self.repo)
        self.repo.write("openspec/specs/cap/decisions.md", record())
        self.repo.git("add", "-A")
        r = self.sign("subagent")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.strip().endswith("; no read due"), r.stdout)


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

    def test_no_record_prints_none(self):
        self.repo.change("y", cap="newcap", delta=GOOD_DELTA)
        self.assertEqual(self.records("y"), ["none"])


@unittest.skipUnless(HAS_OPENSPEC, NEEDS)
class FoldAtArchiveTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        # A Purpose long enough for OpenSpec's own checks at archive.
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace(
            "What cap does.", "What cap does: it keeps the records it is given, and reads them back."))
        self.repo.write("openspec/specs/cap/decisions.md", record())
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "record")
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("Records pile up",
                                                             "Records pile up, and the disk fills"))

    def archive(self, change="x"):
        return self.repo.run("archive", change, "--", "--yes")

    def main(self, rel="openspec/specs/cap/decisions.md"):
        p = self.repo.path / rel
        return p.read_text() if p.exists() else None

    def test_a_new_entry_is_added_and_one_with_the_same_title_replaced_in_place(self):
        new = CONSTRAINT.replace("credentials", "tokens")
        changed = REJECTED.replace("lessons are injected into the prompt", "lessons are injected")
        self.repo.write("openspec/changes/x/specs/cap/decisions.md",
                        record(constraints=(new,), rejected=(changed,)))
        r = self.archive()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.main(), record(constraints=(CONSTRAINT, new), rejected=(changed,)))
        self.assertFalse((self.repo.path / "openspec/changes/x").exists())

    def test_a_retired_entry_is_removed_and_an_empty_record_deleted(self):
        self.repo.write("openspec/changes/x/specs/cap/decisions.md", record(
            constraints=(), rejected=(), retired=("- **Constraint: The store keeps no credentials.**\n",)))
        self.assertEqual(self.archive().returncode, 0)
        self.assertEqual(self.main(), record(constraints=()))
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "archived")
        self.repo.change("y", proposal=GOOD_PROPOSAL.replace("Records pile up", "Records pile up again"),
                         delta=GOOD_DELTA.replace("Records expire", "Records shrink"))
        self.repo.write("openspec/changes/y/specs/cap/decisions.md", record(
            constraints=(), rejected=(), retired=("- **Rejected: a retrieval tool the worker calls**\n",)))
        r = self.archive("y")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIsNone(self.main())
        self.assertIn("has no entry left; removed it", r.stdout)

    def test_a_record_is_created_at_the_configured_location(self):
        self.repo.write("openspec/spec-check.yaml", "decision-records: openspec/decisions/<capability>/decisions.md\n")
        self.repo.write("openspec/changes/x/specs/cap/decisions.md", record(rejected=()))
        self.assertEqual(self.archive().returncode, 0)
        self.assertEqual(self.main("openspec/decisions/cap/decisions.md"), record(rejected=()))
        # The file at the default location is no longer a record, and is left alone.
        self.assertEqual(self.main(), record())

    def test_nothing_is_archived_when_a_record_cannot_be_folded(self):
        self.repo.write("openspec/changes/x/specs/cap/decisions.md", record(
            constraints=(), rejected=(), retired=("- **Constraint: Not there.**\n",)))
        r = self.archive()
        self.assertEqual(r.returncode, 1)
        self.assertIn("nothing archived", r.stderr)
        self.assertIn("retires a Constraint entry 'Not there.'", r.stdout)
        self.assertTrue((self.repo.path / "openspec/changes/x").exists())
        self.assertEqual(self.main(), record())

    def test_a_malformed_main_record_stops_the_fold(self):
        self.repo.write("openspec/specs/cap/decisions.md", record() + "\nA stray line.\n")
        self.repo.write("openspec/changes/x/specs/cap/decisions.md", record(rejected=()))
        r = self.archive()
        self.assertEqual(r.returncode, 1)
        self.assertIn("the main record, line", r.stdout)

    def test_folding_twice_is_folding_once(self):
        main = record()
        ours = record(constraints=(CONSTRAINT.replace("credentials", "tokens"),), rejected=(REJECTED,))
        once, _ = spec_check.fold_record("cap", main, ours)
        twice, _ = spec_check.fold_record("cap", once, ours)
        self.assertEqual(once, twice)


@unittest.skipUnless(HAS_OPENSPEC, NEEDS)
class OpenSpecIgnoresDecisionRecordsTests(unittest.TestCase):
    """Pins what OpenSpec does with a decisions.md, as measured on 1.16.0
    for issue #56. A release that starts reading one fails here, and spec-
    check's fold at archive, which exists because OpenSpec leaves a change's
    record behind, must then be reconsidered (DECISIONS.md, "Decision
    records per capability")."""

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
        text = record(constraints=(CONSTRAINT.replace("The store keeps no credentials.", "..."),))
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

    def test_check_reports_a_malformed_main_record_the_fold_would_refuse(self):
        repo = Repo(self)
        repo.write("openspec/specs/cap/decisions.md", record() + "\nA stray line.\n")
        repo.change("x")
        repo.write("openspec/changes/x/specs/cap/decisions.md", record(rejected=()))
        r = repo.check("x")
        self.assertIn("cannot fold into openspec/specs/cap/decisions.md", r.stdout)
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

    def test_an_empty_change_record_with_no_main_record_folds_to_nothing(self):
        repo = Repo(self)
        repo.change("x")
        repo.write("openspec/changes/x/specs/cap/decisions.md", record(constraints=(), rejected=()))
        corpus = spec_check.Corpus(str(repo.path), requirements=False)
        self.assertEqual(spec_check.fold_change("x", corpus), ({}, []))


class FoundByBugHunterRun2Iteration3Tests(unittest.TestCase):
    def test_a_malformed_change_record_still_shows_a_malformed_main_record(self):
        repo = Repo(self)
        repo.write("openspec/specs/cap/decisions.md", record() + "\nA stray line.\n")
        repo.change("x")
        repo.write("openspec/changes/x/specs/cap/decisions.md",
                   record(rejected=()).replace("  Holds while: seats are shared between roles.\n", ""))
        r = repo.check("x")
        self.assertIn("the main record, line", r.stdout)
        self.assertIn("has no Holds while: line", r.stdout)
        self.assertEqual(r.stdout.count("has no Holds while: line"), 1, r.stdout)

    def test_a_record_the_template_puts_under_openspec_changes_is_refused(self):
        repo = Repo(self)
        repo.write("openspec/spec-check.yaml", "decision-records: openspec/<capability>/decisions.md\n")
        repo.change("x", cap="changes", delta=GOOD_DELTA.replace(
            "## ADDED Requirements", "## Purpose\n\nWhat changes does: it keeps the records it is given.\n\n"
            "## ADDED Requirements"))
        repo.write("openspec/changes/x/specs/changes/decisions.md", record(cap="changes"))
        r = repo.check("x")
        self.assertIn("cannot fold into openspec/changes/decisions.md", r.stdout)
        self.assertEqual(r.returncode, 1)
        folded, out = spec_check.fold_change("x", spec_check.Corpus(str(repo.path), requirements=False))
        self.assertEqual(folded, {})
        self.assertEqual(len(out), 1, [f.text() for f in out])


class StackedRecordTests(unittest.TestCase):
    """A stacked change's records are folded onto main's with each
    dependency's own record folded in first."""

    def setUp(self):
        self.repo = Repo(self)
        self.repo.write("openspec/specs/cap/decisions.md", record(rejected=()))
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "record")

    def dep(self, records):
        d = spec_check.Dep("seat-files", "acme/widgets", "171", 1)
        d.records = records
        return d

    def corpus(self, retired):
        self.repo.change("x", proposal="Builds on: seat-files (acme/widgets#171)\n\n" + GOOD_PROPOSAL)
        self.repo.write("openspec/changes/x/specs/cap/decisions.md", record(
            constraints=(), rejected=(), retired=(retired,)))
        return spec_check.Corpus(str(self.repo.path), requirements=False)

    def test_retiring_an_entry_a_dependency_adds_is_no_error(self):
        corpus = self.corpus("- **Rejected: A retrieval tool the worker calls.**\n")
        dep = self.dep({"cap": record(constraints=())})
        self.assertEqual(spec_check.fold_change("x", corpus)[1][0].kind, "record")  # main alone lacks it
        folded, problems = spec_check.fold_change("x", corpus, [dep])
        self.assertEqual(problems, [])
        self.assertEqual(folded, {"openspec/specs/cap/decisions.md": record(rejected=())})

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_check_passes_a_stacked_change_retiring_what_its_dependency_adds(self):
        s = StackRepo(self)
        s.put("openspec/changes/seat-files/specs/cap/decisions.md", record(rejected=()))
        s.dependency(171, "seat-files", GOOD_DELTA)
        s.stacked(GOOD_DELTA.replace("Records expire", "Records are searched").replace(
            "delete a record ninety days after its last read", "index each record for search").replace(
            "An old record goes", "A record is found"), "seat-files (acme/widgets#171)")
        s.repo.write("openspec/changes/lore-search/specs/cap/decisions.md", record(
            constraints=(), rejected=(), retired=("- **Constraint: The store keeps no credentials.**\n",)))
        r = s.check("lore-search")
        self.assertNotIn("[record]", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_retiring_an_entry_no_dependency_adds_is_still_an_error(self):
        corpus = self.corpus("- **Rejected: Nothing like this.**\n")
        _, problems = spec_check.fold_change("x", corpus, [self.dep({"cap": record(constraints=())})])
        self.assertIn("retires a Rejected entry 'Nothing like this.'", problems[0].message)

    def test_a_dependency_whose_record_cannot_fold_is_named(self):
        corpus = self.corpus("- **Constraint: The store keeps no credentials.**\n")
        bad = self.dep({"cap": record(constraints=(), rejected=(), retired=("- **Rejected: Gone.**\n",))})
        _, problems = spec_check.fold_change("x", corpus, [bad])
        self.assertIn("cannot fold seat-files (acme/widgets#171)'s record", problems[0].message)

    def test_a_merged_dependency_is_left_out_and_an_unbuilt_stack_checks_only_the_form(self):
        open_dep, merged, pending = (self.dep({}) for _ in range(3))
        open_dep.state, merged.state, pending.state, pending.pending = "OPEN", "MERGED", "MERGED", True
        class S:
            loaded = [open_dep, merged, pending]
        self.assertEqual(spec_check.stack_records(S, True), [open_dep, pending])
        self.assertIsNone(spec_check.stack_records(S, False))
        self.assertEqual(spec_check.stack_records(None, True), ())

    def test_records_lists_a_dependencys_own_record(self):
        corpus = self.corpus("- **Rejected: A retrieval tool the worker calls.**\n")
        dep = self.dep({"cap": record(constraints=())})
        dep.deltas = {"other": "x"}
        self.assertIn(("openspec/changes/seat-files/specs/cap/decisions.md in acme/widgets#171",
                       "the record of seat-files (acme/widgets#171), which this change builds on"),
                      spec_check.records_for("x", corpus, [], [dep]))


LORE = GOOD_DELTA.replace("Records expire", "Records are searched").replace(
    "delete a record ninety days after its last read", "index each record for search").replace(
    "An old record goes", "A record is found")
RETIRE_TOOL = record(constraints=(), rejected=(),
                     retired=("- **Rejected: A retrieval tool the worker calls.**\n",))


@unittest.skipUnless(HAS_OPENSPEC, NEEDS)
class FoundByBugHunterRun3Tests(unittest.TestCase):
    def stack(self):
        s = StackRepo(self)
        s.repo.write("openspec/specs/cap/decisions.md", record(rejected=()))
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "rec")
        s.repo.git("push", "-q", "origin", "main")
        return s

    def test_check_reports_a_dependencys_record_that_cannot_fold(self):
        for own in (None, record(constraints=(CONSTRAINT.replace("credentials", "tokens"),), rejected=())):
            with self.subTest(own=own is not None):
                s = self.stack()
                s.put("openspec/changes/seat-files/specs/cap/decisions.md", record(
                    constraints=(), rejected=(), retired=("- **Rejected: Gone.**\n",)))
                s.dependency(171, "seat-files", GOOD_DELTA)
                s.stacked(LORE, "seat-files (acme/widgets#171)")
                if own:
                    s.repo.write("openspec/changes/lore-search/specs/cap/decisions.md", own)
                r = s.check("lore-search")
                self.assertIn("cannot fold seat-files (acme/widgets#171)'s record", r.stdout)
                self.assertEqual(r.returncode, 1)

    def merged_dependency(self, with_delta):
        s = self.stack()
        rec = record(constraints=(), rejected=(REJECTED,))
        s.put("openspec/changes/seat-files/specs/cap/decisions.md", rec)
        if with_delta:
            s.dependency(171, "seat-files", GOOD_DELTA, state="MERGED")
            s.repo.change("seat-files", delta=GOOD_DELTA)
        else:
            o = str(s.other)
            s.sh("git", "-C", o, "fetch", "-q", "origin")
            s.sh("git", "-C", o, "checkout", "-q", "-B", "seat-files", "origin/main")
            s.put("openspec/changes/seat-files/proposal.md", GOOD_PROPOSAL)
            s.put("openspec/changes/seat-files/tasks.md", TASKS)
            s.push("seat-files", "add")
            s.register(171, "seat-files", "MERGED")
            s.repo.write("openspec/changes/seat-files/proposal.md", GOOD_PROPOSAL)
            s.repo.write("openspec/changes/seat-files/tasks.md", TASKS)
        s.repo.write("openspec/changes/seat-files/specs/cap/decisions.md", rec)
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "merge #171")
        s.repo.git("checkout", "-q", "-b", "spec")
        s.stacked(LORE, "seat-files (acme/widgets#171)")
        s.repo.write("openspec/changes/lore-search/specs/cap/decisions.md", RETIRE_TOOL)
        return s

    def test_records_lists_a_merged_dependency_the_tree_still_holds_open(self):
        s = self.merged_dependency(with_delta=True)
        r = s.repo.run("records", "--base", "main", "lore-search", env=s.env())
        self.assertIn("openspec/changes/seat-files/specs/cap/decisions.md in acme/widgets#171", r.stdout)

    def test_a_merged_dependency_holding_only_a_record_is_folded_while_open(self):
        s = self.merged_dependency(with_delta=False)
        r = s.check("lore-search")
        self.assertNotIn("[record]", r.stdout)
        self.assertNotIn("already in the tree", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_archive_refuses_while_a_dependency_is_open_in_the_tree(self):
        repo = Repo(self)
        repo.change("seat-files")
        repo.change("lore-search", delta=LORE,
                    proposal="Builds on: seat-files (acme/widgets#171)\n\n" + GOOD_PROPOSAL)
        r = repo.run("archive", "lore-search", "--", "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("archive seat-files first", r.stdout + r.stderr)
        self.assertTrue((repo.path / "openspec/changes/lore-search").exists())


RETIRE_STORE = record(constraints=(), rejected=(),
                      retired=("- **Constraint: The store keeps no credentials.**\n",))


def dep_with(records):
    d = spec_check.Dep("seat-files", "acme/widgets", "171", 1)
    d.records = records
    return d


class FoundByBugHunterRun3Iteration2Tests(unittest.TestCase):
    def repo_with_retiring_change(self, text):
        repo = Repo(self)
        repo.write("openspec/specs/cap/decisions.md", record(rejected=()))
        repo.change("x", proposal="Builds on: seat-files (acme/widgets#171)\n\n" + GOOD_PROPOSAL)
        repo.write("openspec/changes/x/specs/cap/decisions.md", text)
        return spec_check.Corpus(str(repo.path), requirements=False)

    def test_a_dependency_record_that_cannot_fold_brings_no_second_error(self):
        corpus = self.repo_with_retiring_change(RETIRE_TOOL)
        broken = REJECTED.replace("  Paths: src/\n", "")
        dep = dep_with({"cap": record(constraints=(), rejected=(broken,))})
        _, out = spec_check.fold_change("x", corpus, [dep])
        self.assertEqual([f.path for f in out], ["openspec/changes/x/proposal.md"], [f.text() for f in out])

    def test_a_dependency_retiring_the_last_entry_deletes_the_record_first(self):
        corpus = self.repo_with_retiring_change(RETIRE_STORE)
        _, out = spec_check.fold_change("x", corpus, [dep_with({"cap": RETIRE_STORE})])
        self.assertEqual(len(out), 1, [f.text() for f in out])
        self.assertIn("does not hold", out[0].message)
        self.assertEqual(out[0].path, "openspec/changes/x/specs/cap/decisions.md")

    def test_a_dependency_record_that_cannot_fold_brings_no_error_on_a_later_one(self):
        corpus = self.repo_with_retiring_change(record(constraints=(CONSTRAINT,), rejected=()))
        broken = REJECTED.replace("  Paths: src/\n", "")
        d1 = dep_with({"cap": record(constraints=(), rejected=(broken,))})
        d2 = spec_check.Dep("d2", "acme/widgets", "172", 2)
        d2.records = {"cap": RETIRE_TOOL}
        _, out = spec_check.fold_change("x", corpus, [d1, d2])
        self.assertEqual(len(out), 1, [f.text() for f in out])
        self.assertIn("seat-files", out[0].message)

    def test_archive_refuses_a_change_that_builds_on_itself(self):
        repo = Repo(self)
        repo.change("lore-search", delta=LORE,
                    proposal="Builds on: lore-search (acme/widgets#9)\n\n" + GOOD_PROPOSAL)
        r = repo.run("archive", "lore-search", "--", "--yes")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("cannot build on itself", r.stderr)
        self.assertTrue((repo.path / "openspec/changes/lore-search").exists())

    def test_records_lists_no_main_record_a_dependency_touches_that_does_not_exist(self):
        repo = Repo(self)
        repo.change("x", proposal="Builds on: seat-files (acme/widgets#171)\n\n" + GOOD_PROPOSAL)
        corpus = spec_check.Corpus(str(repo.path), requirements=False)
        d = dep_with({"other": record(cap="other")})
        d.dir, d.slug = "openspec/changes/seat-files", "acme/widgets"
        listed = [rel for rel, _ in spec_check.records_for("x", corpus, [], [d])]
        self.assertEqual(listed, ["openspec/changes/seat-files/specs/other/decisions.md in acme/widgets#171"])

    def test_a_template_with_a_parent_segment_is_refused(self):
        self.assertIsNotNone(spec_check.template_problem("openspec/../x/<capability>/decisions.md"))

    def test_a_sibling_of_a_record_in_its_capability_folder_is_not_one(self):
        t = "openspec/decisions/<capability>/decisions.md"
        self.assertIsNone(spec_check.record_cap(t, "openspec/decisions/cap/notes-on-the-capability.md"))
        self.assertEqual(spec_check.record_cap(t, "openspec/decisions/cap/decisions.md"), "cap")

    def test_archive_refuses_a_change_whose_builds_on_line_is_malformed(self):
        repo = Repo(self)
        repo.change("seat-files")
        repo.change("lore-search", delta=LORE,
                    proposal="Builds on: seat-files, see #171\n\n" + GOOD_PROPOSAL)
        r = repo.run("archive", "lore-search", "--", "--yes")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("Builds on:", r.stderr)
        self.assertTrue((repo.path / "openspec/changes/lore-search").exists())


@unittest.skipUnless(HAS_OPENSPEC, NEEDS)
class FoundByBugHunterRun3Iteration2StackTests(FoundByBugHunterRun3Tests):
    def records_only_dependency(self, state, text, in_tree):
        s = self.stack()
        o = str(s.other)
        s.sh("git", "-C", o, "fetch", "-q", "origin")
        s.sh("git", "-C", o, "checkout", "-q", "-B", "seat-files", "origin/main")
        p = s.other / "openspec/changes/seat-files/specs/cap/decisions.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode())
        s.put("openspec/changes/seat-files/proposal.md", GOOD_PROPOSAL)
        s.put("openspec/changes/seat-files/tasks.md", TASKS)
        s.push("seat-files", "add")
        s.register(171, "seat-files", state)
        if in_tree:
            s.repo.write("openspec/changes/seat-files/proposal.md", GOOD_PROPOSAL)
            s.repo.write("openspec/changes/seat-files/tasks.md", TASKS)
            q = s.repo.path / "openspec/changes/seat-files/specs/cap/decisions.md"
            q.parent.mkdir(parents=True, exist_ok=True)
            q.write_bytes(text.encode())
            s.repo.git("add", "-A")
            s.repo.git("commit", "-q", "-m", "merge #171")
        s.repo.git("checkout", "-q", "-b", "spec")
        return s

    def test_a_records_only_dependency_with_crlf_lines_is_pending_while_open(self):
        rec = record(constraints=(), rejected=(REJECTED,)).replace("\n", "\r\n")
        s = self.records_only_dependency("MERGED", rec, in_tree=True)
        s.stacked(LORE, "seat-files (acme/widgets#171)")
        s.repo.write("openspec/changes/lore-search/specs/cap/decisions.md", RETIRE_TOOL)
        r = s.check("lore-search")
        self.assertNotIn("[record]", r.stdout)
        self.assertNotIn("already in the tree", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_a_merged_records_only_dependency_the_branch_lacks_says_merge_main(self):
        s = self.records_only_dependency("MERGED", record(constraints=(), rejected=(REJECTED,)),
                                         in_tree=False)
        s.stacked(LORE, "seat-files (acme/widgets#171)")
        r = s.check("lore-search")
        self.assertIn("Merge main into your branch", r.stdout)
        self.assertNotIn("already in the tree", r.stdout)
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_an_unlisted_dependency_whose_records_a_listed_one_holds_passes(self):
        from test_spec_check import stacked_proposal
        s = self.stack()
        held = record(constraints=(), rejected=(REJECTED,))
        o = str(s.other)
        for num, name in ((169, "a-rec"), (170, "c-rec")):
            s.sh("git", "-C", o, "fetch", "-q", "origin")
            s.sh("git", "-C", o, "checkout", "-q", "-B", name, "origin/main")
            s.put(f"openspec/changes/{name}/specs/cap/decisions.md", held)
            s.put(f"openspec/changes/{name}/proposal.md", GOOD_PROPOSAL)
            s.put(f"openspec/changes/{name}/tasks.md", TASKS)
            s.push(name, "add " + name)
            s.register(num, name, "OPEN")
        s.put("openspec/changes/seat-files/specs/cap/decisions.md", RETIRE_TOOL)
        s.dependency(171, "seat-files", GOOD_DELTA, base="c-rec",
                     proposal=stacked_proposal("c-rec (acme/widgets#170)"))
        s.stacked(LORE, "a-rec (acme/widgets#169)", "seat-files (acme/widgets#171)")
        r = s.check("lore-search")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_an_unlisted_records_only_dependency_of_a_dependency_is_named(self):
        from test_spec_check import stacked_proposal
        s = self.stack()
        o = str(s.other)
        s.sh("git", "-C", o, "fetch", "-q", "origin")
        s.sh("git", "-C", o, "checkout", "-q", "-B", "c-rec", "origin/main")
        s.put("openspec/changes/c-rec/specs/cap/decisions.md", record(constraints=(), rejected=(REJECTED,)))
        s.put("openspec/changes/c-rec/proposal.md", GOOD_PROPOSAL)
        s.put("openspec/changes/c-rec/tasks.md", TASKS)
        s.push("c-rec", "add c")
        s.register(170, "c-rec", "OPEN")
        s.put("openspec/changes/seat-files/specs/cap/decisions.md", RETIRE_TOOL)
        s.dependency(171, "seat-files", GOOD_DELTA, base="c-rec",
                     proposal=stacked_proposal("c-rec (acme/widgets#170)"))
        s.stacked(LORE, "seat-files (acme/widgets#171)")
        r = s.check("lore-search")
        self.assertIn("which this change does not list before it", r.stdout)
        self.assertNotIn("cannot fold", r.stdout)



@unittest.skipUnless(HAS_OPENSPEC, NEEDS)
class StackedRecordsJudgedLikeDeltasTests(FoundByBugHunterRun3Iteration2StackTests):
    """An open dependency's records are held, meaning the tree already has
    what they add, only when folding them onto main plus the listed
    dependencies' records changes nothing."""

    def test_an_open_dependency_whose_deltas_main_holds_but_not_its_records_is_kept(self):
        s = self.stack()
        spec = s.repo.path / "openspec/specs/cap/spec.md"
        s.repo.write("openspec/specs/cap/spec.md", spec.read_text() + "\n" + GOOD_DELTA.split("\n", 2)[2])
        s.repo.git("add", "-A")
        s.repo.git("commit", "-q", "-m", "x")
        s.repo.git("push", "-q", "origin", "main")
        s.put("openspec/changes/seat-files/specs/cap/decisions.md", record(constraints=(), rejected=(REJECTED,)))
        s.dependency(171, "seat-files", GOOD_DELTA)
        s.stacked(LORE, "seat-files (acme/widgets#171)")
        s.repo.write("openspec/changes/lore-search/specs/cap/decisions.md", RETIRE_TOOL)
        r = s.check("lore-search")
        self.assertNotIn("remove the `Builds on", r.stdout)
        self.assertIn("its decision records are not, and are folded in", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_an_unlisted_dependency_rewording_an_entry_must_be_listed(self):
        from test_spec_check import stacked_proposal
        reworded = CONSTRAINT.replace("seats are shared between roles", "seats are shared between any two roles")
        s = self.stack()
        o = str(s.other)
        s.sh("git", "-C", o, "fetch", "-q", "origin")
        s.sh("git", "-C", o, "checkout", "-q", "-B", "c-rec", "origin/main")
        s.put("openspec/changes/c-rec/specs/cap/decisions.md", record(constraints=(reworded,), rejected=()))
        s.put("openspec/changes/c-rec/proposal.md", GOOD_PROPOSAL)
        s.put("openspec/changes/c-rec/tasks.md", TASKS)
        s.push("c-rec", "add c")
        s.register(170, "c-rec", "OPEN")
        s.dependency(171, "seat-files", GOOD_DELTA, base="c-rec",
                     proposal=stacked_proposal("c-rec (acme/widgets#170)"))
        s.stacked(LORE, "seat-files (acme/widgets#171)")
        r = s.check("lore-search")
        self.assertIn("which this change does not list before it", r.stdout)
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_an_open_records_only_dependency_main_already_holds_is_stale(self):
        s = self.records_only_dependency("OPEN", record(rejected=()), in_tree=False)
        s.stacked(LORE, "seat-files (acme/widgets#171)")
        r = s.check("lore-search")
        self.assertIn("every decision record it holds is already in the tree", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_merge_main_names_a_plain_openspec_archive(self):
        s = self.records_only_dependency("MERGED", record(constraints=(), rejected=(REJECTED,)),
                                         in_tree=False)
        s.stacked(LORE, "seat-files (acme/widgets#171)")
        r = s.check("lore-search")
        self.assertIn("Merge main into your branch", r.stdout)
        self.assertIn("plain `openspec archive`", r.stdout)
        self.assertEqual(r.returncode, 1, r.stdout)



def rejected_first(cap="cap"):
    return f"# {cap}: constraints and rejected alternatives\n\n## Rejected\n{REJECTED}\n## Constraints\n{CONSTRAINT}"


class FoundByBugHunterRun4Tests(unittest.TestCase):
    def test_records_held_ignores_the_order_of_the_sections(self):
        repo = Repo(self)
        repo.write("openspec/specs/cap/decisions.md", rejected_first())
        corpus = spec_check.Corpus(str(repo.path), requirements=False)
        self.assertTrue(spec_check.records_held(dep_with({"cap": rejected_first()}), corpus, corpus.records))
        self.assertFalse(spec_check.records_held(dep_with({"cap": record(rejected=())}), corpus, {}))

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

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_archive_passes_yes_so_openspec_never_prompts(self):
        for extra in ((), ("--", "-y"), ("--", "--yes")):
            with self.subTest(extra=extra):
                repo = Repo(self)
                repo.write("openspec/specs/cap/decisions.md", record(rejected=()))
                repo.change("x")
                repo.write("openspec/changes/x/specs/cap/decisions.md",
                           record(constraints=(), rejected=(REJECTED,)))
                repo.git("add", "-A")
                repo.git("commit", "-q", "-m", "c")
                r = repo.run("archive", "x", *extra, stdin="n\nn\nn\n")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("Records expire", (repo.path / "openspec/specs/cap/spec.md").read_text())
                self.assertIn("Rejected: A retrieval tool",
                              (repo.path / "openspec/specs/cap/decisions.md").read_text())

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_archive_with_skip_specs_leaves_the_records_alone(self):
        repo = Repo(self)
        repo.write("openspec/specs/cap/decisions.md", record(rejected=()))
        repo.change("x")
        repo.write("openspec/changes/x/specs/cap/decisions.md", record(constraints=(), rejected=(REJECTED,)))
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "c")
        r = repo.run("archive", "x", "--", "--yes", "--skip-specs")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((repo.path / "openspec/specs/cap/decisions.md").read_text(), record(rejected=()))



class RecordsNotShownTests(unittest.TestCase):
    def corpus(self, main):
        repo = Repo(self)
        repo.write("openspec/specs/cap/decisions.md", main)
        return spec_check.Corpus(str(repo.path), requirements=False)

    def test_an_entry_a_later_merged_dependency_retires_need_not_be_there(self):
        corpus = self.corpus(record(rejected=()))
        adds = dep_with({"cap": record(constraints=(), rejected=(REJECTED,))})
        later = dep_with({"cap": RETIRE_TOOL})
        self.assertEqual(spec_check.records_not_shown(adds, corpus, [later]), [])
        self.assertEqual(len(spec_check.records_not_shown(adds, corpus)), 1)

    def test_an_entry_a_later_merged_dependency_adds_back_need_not_be_gone(self):
        corpus = self.corpus(record(rejected=()))
        retires = dep_with({"cap": RETIRE_STORE})
        later = dep_with({"cap": record(rejected=())})
        self.assertEqual(spec_check.records_not_shown(retires, corpus, [later]), [])
        self.assertEqual(len(spec_check.records_not_shown(retires, corpus)), 1)

    def test_fold_deps_leaves_the_corpus_records_alone(self):
        corpus = self.corpus(record(rejected=()))
        before = dict(corpus.records)
        spec_check.fold_deps(corpus, [dep_with({"cap": RETIRE_STORE})], "p.md")
        self.assertEqual(corpus.records, before)


@unittest.skipUnless(HAS_OPENSPEC, NEEDS)
class MergedDependencyOfADependencyTests(FoundByBugHunterRun3Iteration2StackTests):
    def test_an_unlisted_merged_dependency_whose_records_the_branch_lacks_says_merge_main(self):
        from test_spec_check import stacked_proposal
        s = self.stack()
        o = str(s.other)
        s.sh("git", "-C", o, "fetch", "-q", "origin")
        s.sh("git", "-C", o, "checkout", "-q", "-B", "c-rec", "origin/main")
        s.put("openspec/changes/c-rec/specs/cap/decisions.md", record(constraints=(), rejected=(REJECTED,)))
        s.put("openspec/changes/c-rec/proposal.md", GOOD_PROPOSAL)
        s.put("openspec/changes/c-rec/tasks.md", TASKS)
        s.push("c-rec", "add c")
        s.register(170, "c-rec", "MERGED")
        s.dependency(171, "seat-files", GOOD_DELTA, base="c-rec",
                     proposal=stacked_proposal("c-rec (acme/widgets#170)"))
        s.stacked(LORE, "seat-files (acme/widgets#171)")
        r = s.check("lore-search")
        self.assertIn("builds on c-rec (acme/widgets#170), which has merged", r.stdout)
        self.assertIn("plain `openspec archive`", r.stdout)
        self.assertEqual(r.returncode, 1, r.stdout)



class FoundByBugHunterRun5Tests(unittest.TestCase):
    def test_a_template_naming_spec_md_or_changes_in_another_case_is_refused(self):
        for t in ("openspec/specs/<capability>/Spec.md", "openspec/Changes/<capability>/decisions.md"):
            with self.subTest(t=t):
                self.assertIsNotNone(spec_check.template_problem(t))
        self.assertIsNone(spec_check.record_cap("openspec/<capability>/decisions.md",
                                                "openspec/Changes/x/decisions.md"))

    def test_a_file_at_the_record_path_that_is_not_read_as_a_record_stops_the_fold(self):
        repo = Repo(self)
        repo.write("openspec/spec-check.yaml", "decision-records: openspec/Specs/<capability>/decisions.md\n")
        repo.write("openspec/specs/cap/decisions.md", record(rejected=()))
        repo.change("x")
        repo.write("openspec/changes/x/specs/cap/decisions.md", record(constraints=(), rejected=(REJECTED,)))
        corpus = spec_check.Corpus(str(repo.path), requirements=False)
        main = repo.path / "openspec/Specs/cap/decisions.md"
        if not main.exists():
            self.skipTest("needs a filesystem that ignores case")
        folded, out = spec_check.fold_change("x", corpus)
        self.assertEqual(folded, {})
        self.assertEqual(len(out), 1, [f.text() for f in out])
        self.assertIn("not read as a record", out[0].message)

    def test_records_given_specs_says_it_takes_a_change(self):
        repo = Repo(self)
        repo.change("x")
        for cmd in ("records", "archive"):
            for target in ("specs", "openspec/specs", "specs/", "openspec/specs/"):
                with self.subTest(cmd=cmd, target=target):
                    r = repo.run(cmd, target, *(("--base", "main") if cmd == "records" else ()))
                    self.assertNotIn("Traceback", r.stderr)
                    self.assertIn(f"{cmd} takes a change's name", r.stderr)
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

    def test_a_title_only_main_record_holds_a_dependency_record_with_no_entry(self):
        repo = Repo(self)
        title = "# cap: constraints and rejected alternatives\n"
        repo.write("openspec/specs/cap/decisions.md", title)
        corpus = spec_check.Corpus(str(repo.path), requirements=False)
        self.assertTrue(spec_check.records_held(dep_with({"cap": title}), corpus, corpus.records))

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
    def test_a_change_record_keeping_and_retiring_one_entry_is_an_error(self):
        kept = CONSTRAINT.replace("a leaked store leaks every seat", "a leak exposes every seat")
        retired = "- **Constraint: The store keeps no credentials.**\n"
        for text in (record(constraints=(kept,), rejected=(), retired=(retired,)),
                     "# cap: constraints and rejected alternatives\n\n## Retired\n" + retired +
                     "\n## Constraints\n" + kept):
            with self.subTest(order=text.index("Retired") < text.index("Because")):
                problems = spec_check.parse_record(text, change=True).problems
                self.assertEqual(len(problems), 1, problems)
                self.assertIn("keeps and retires the same Constraint entry", problems[0][1])

    def test_a_glob_ending_in_a_slash_names_what_is_under_it(self):
        for pattern in ("src/*/", "src/**/", "src/l*/", "src/?ib/"):
            with self.subTest(pattern=pattern):
                self.assertTrue(spec_check.path_matches(pattern, "src/lib/x.py"))

class MutationGapRun7Tests(unittest.TestCase):
    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_skip_specs_says_the_records_were_left_alone_only_when_there_were_some(self):
        for has_record in (True, False):
            with self.subTest(has_record=has_record):
                repo = Repo(self)
                repo.write("openspec/specs/cap/decisions.md", record(rejected=()))
                repo.change("x")
                if has_record:
                    repo.write("openspec/changes/x/specs/cap/decisions.md",
                               record(constraints=(), rejected=(REJECTED,)))
                repo.git("add", "-A")
                repo.git("commit", "-q", "-m", "c")
                r = repo.run("archive", "x", "--", "--skip-specs")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual("records were not folded either" in r.stdout, has_record)



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

    def test_sign_records_and_archive_refuse_a_symlink(self):
        repo = Repo(self)
        repo.git("checkout", "-q", "-b", "spec")
        repo.change("x")
        repo.write("shared/notes.md", "notes\n")
        os.symlink("../../../shared/notes.md", repo.path / "openspec/changes/x/notes.md")
        repo.git("add", "-A")
        self.refused(repo.run("sign", "--read", "deferred", "--base", "main", "--no-validate"),
                     "openspec/changes/x/notes.md")
        self.refused(repo.run("records", "x"), "openspec/changes/x/notes.md")
        self.refused(repo.run("archive", "x"), "openspec/changes/x/notes.md")
        self.assertTrue((repo.path / "openspec/changes/x").is_dir())

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
    """`## Rationale` holds reasoning longer than a requirement's one
    *because* sentence, one entry per requirement, named by its title."""

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

    def test_evidence_is_optional_and_reasoning_is_not(self):
        bare = "- **Rationale: Records are kept.**\n  Thirty days covers every audit window.\n"
        self.assertEqual(findings(record(rationale=(bare,))), [])
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
            "Records are kept.", "records ARE `kept`"),)), requirements={"Records are kept"}), [])

    def test_a_rationale_is_retired_under_retired(self):
        text = record(constraints=(), rejected=(), retired=("- **Rationale: Records are kept.**\n",))
        self.assertEqual(findings(text, change=True, requirements=set()), [])

    def test_the_fold_keys_rationale_by_requirement_title(self):
        main = record(rationale=(RATIONALE,))
        new = RATIONALE.replace("A shorter window", "A seven-day window")
        other = "- **Rationale: Records expire.**\n  Ninety days bounds what a leak exposes.\n"
        folded, problems = spec_check.fold_record(
            "cap", main, record(constraints=(), rejected=(), rationale=(new, other)))
        self.assertEqual(problems, [])
        self.assertEqual(folded, record(rationale=(new, other)))
        retired, problems = spec_check.fold_record("cap", main, record(
            constraints=(), rejected=(), retired=("- **Rationale: records are kept**\n",)))
        self.assertEqual((retired, problems), (record(), []))

    def test_the_fold_writes_rationale_after_constraints_and_rejected(self):
        folded, _ = spec_check.fold_record("cap", None, record(rationale=(RATIONALE,)))
        self.assertLess(folded.index("## Rejected"), folded.index("## Rationale"))


class RationaleCheckTests(unittest.TestCase):
    """check holds a Rationale entry's title to the requirements in force,
    or in the change."""

    def setUp(self):
        self.repo = Repo(self)

    def record_errors(self, *args):
        r = self.repo.check(*args)
        return [line for line in r.stdout.splitlines() if "error [record]" in line]

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_a_change_record_may_name_a_requirement_in_force_or_in_the_change(self):
        self.repo.change("x")
        why = "- **Rationale: {}.**\n  The reasoning, at more length than one sentence holds.\n"
        self.repo.write("openspec/changes/x/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(why.format("Records are kept"),
                                                    why.format("Records expire"))))
        self.assertEqual(self.record_errors("x"), [])
        self.repo.write("openspec/changes/x/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(why.format("Records are shredded"),)))
        (error,) = self.record_errors("x")
        self.assertIn('"Records are shredded" names no requirement of cap', error)

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_a_change_record_may_not_name_a_requirement_the_change_removes(self):
        self.repo.change("x", delta="## REMOVED Requirements\n\n### Requirement: Records are kept\n\n"
                                    "**Reason**: no longer needed.\n\n**Migration**: none.\n")
        self.repo.write("openspec/changes/x/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(RATIONALE,)))
        (error,) = self.record_errors("x")
        self.assertIn('"Records are kept" names no requirement of cap', error)

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_a_main_record_must_name_a_main_requirement(self):
        self.repo.write("openspec/specs/cap/decisions.md", record(rationale=(
            RATIONALE, RATIONALE.replace("Records are kept", "Records are shredded"))))
        (error,) = self.record_errors("specs")
        self.assertIn("openspec/specs/cap/decisions.md:", error)
        self.assertIn('"Records are shredded" names no requirement of cap', error)

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_archive_folds_a_rationale_entry(self):
        self.repo.write("openspec/specs/cap/spec.md", MAIN_SPEC.replace(
            "What cap does.", "What cap does: it keeps the records it is given, and reads them back."))
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "purpose")
        self.repo.change("x", proposal=GOOD_PROPOSAL.replace("Records pile up",
                                                             "Records pile up, and the disk fills"))
        self.repo.write("openspec/changes/x/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(RATIONALE,)))
        r = self.repo.run("archive", "x")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.repo.path / "openspec/specs/cap/decisions.md").read_text(),
                         record(constraints=(), rejected=(), rationale=(RATIONALE,)))

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
        repo.change("x")
        repo.write("openspec/changes/x/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(RATIONALE,)))
        r = repo.check("x")
        self.assertNotIn("error [record]", r.stdout)
        self.assertIn("openspec-show", r.stdout)

    def test_reasoning_may_start_with_a_word_another_kind_uses_as_a_label(self):
        text = record(rationale=("- **Rationale: Records are kept.**\n  Thirty days was chosen over\n"
                                 "  Instead: of ninety, which the auditors refused.\n",))
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
        retired = record(constraints=(), rejected=(), retired=(
            "- **Rationale: Records are kept.**\n  old reasoning\n",))
        problems = findings(retired, change=True)
        self.assertEqual([m for _, _, m in problems],
                         ["an entry under `## Retired` is its bold line alone"])

    def test_a_main_records_rationale_error_names_main_requirements_only(self):
        text = record(rationale=(RATIONALE.replace("Records are kept", "Records are shredded"),))
        (problem,) = findings(text, requirements={"Records are kept"})
        self.assertNotIn("this change", problem[2])
        (problem,) = findings(text, change=True, requirements={"Records are kept"})
        self.assertIn("this change adds or modifies", problem[2])


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

    def test_requirements_that_cannot_be_told_leave_titles_unchecked(self):
        class FakeCorpus:
            missing, unread, items = None, {}, {}
        self.assertIsNone(spec_check.change_requirements("x", FakeCorpus(), None, "cap"))
        FakeCorpus.missing = "openspec is not installed"
        self.assertIsNone(spec_check.change_requirements("x", FakeCorpus(), {("cap", "A")}, "cap"))

    @unittest.skipUnless(HAS_OPENSPEC, NEEDS)
    def test_a_change_renaming_a_requirement_moves_its_rationale_title(self):
        repo = Repo(self)
        repo.change("x", delta=self.RENAME)
        why = "- **Rationale: {}.**\n  The reasoning, at more length than one sentence holds.\n"
        repo.write("openspec/changes/x/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(why.format("Records are retained"),)))
        self.assertNotIn("error [record]", repo.check("x").stdout)
        repo.write("openspec/changes/x/specs/cap/decisions.md", record(
            constraints=(), rejected=(), rationale=(why.format("Records are kept"),)))
        self.assertIn('"Records are kept" names no requirement of cap', repo.check("x").stdout)

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


class ConsistencyReadChecklistTests(unittest.TestCase):
    """consistency-read.md's checklist asks the reader to flag a record
    entry that repeats a requirement."""

    def test_item_16_flags_a_record_entry_a_requirement_already_states(self):
        text = (pathlib.Path(spec_check.__file__).parent.parent / "consistency-read.md").read_text()
        items = re.findall(r"^(\d+)\. ", text.split("Then go through the checklist", 1)[1], re.M)
        self.assertEqual(items, [str(n) for n in range(1, 17)])
        item = re.search(r"^16\. (.*?)(?=^\S|\Z)", text, re.M | re.S).group(1)
        for words in ("Constraint or Rejected", "requirement or scenario already states",
                      "*because* sentence", "Rationale entry"):
            self.assertIn(words, " ".join(item.split()))
        both_sides = re.search(r"\(items ([\d, ]+)\), quote both sides", text).group(1)
        self.assertIn("16", both_sides.replace(" ", "").split(","))


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
        problems = findings(record().replace("constraints and", "rules and"))
        self.assertEqual([m for _, line, m in problems if line == 1],
                         [m for _, line, m in problems if line == 1 and "the first line must be" in m])
        self.assertEqual(len([1 for _, line, _ in problems if line == 1]), 1, problems)

    def test_a_star_stays_within_one_name(self):
        self.assertTrue(spec_check.path_matches("src/*.py", "src/x.py"))
        self.assertFalse(spec_check.path_matches("src/*.py", "src/lib/x.py"))



if __name__ == "__main__":
    unittest.main()

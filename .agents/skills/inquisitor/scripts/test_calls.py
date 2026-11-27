"""Tests for calls: the two calls of `vet` and the verdict records."""

import contextlib
import io
import json
import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, cast
from unittest import mock

import calls
import config
from common import Refused, verdicts_dir
from contracts import QuestionIn, SearchResult
from qtext import Question, question_hash, question_text

TOKEN = "ghp_" + "a" * 36


def empty_search(question: QuestionIn, service: bool) -> SearchResult:
    return {"version": 1, "hits": [], "not_searched": [], "clones": [], "left_out": 0}


def picker(text: str, options: list[str], **extra: Any) -> dict[str, Any]:
    return {"kind": "picker", "question": text, "options": options,
            "concerns": {"repository": "o/api"}, **extra}


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        os.chmod(self.dir, 0o700)
        self.state = self.dir / "state"
        ranks = ["private", "internal", "public"]

        def same(configured: str | None) -> str | None:
            return configured

        def more_visible(a: str | None, b: str | None) -> bool:
            return ranks.index(a or "public") > ranks.index(b or "private")

        patches: list[Any] = [
            mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.state)}),
            mock.patch("search.filter1", side_effect=empty_search),
            mock.patch("calls._working_repository", return_value="o/api"),
            mock.patch("config.load", return_value=config.Config(login="alice")),
            mock.patch("github.session_login", side_effect=same),
            mock.patch("github.write_access", return_value=True),
            mock.patch("github.visibility", return_value="private"),
            mock.patch("github.more_visible", side_effect=more_visible),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.n = 0

    def tearDown(self) -> None:
        subprocess.run(["rm", "-rf", str(self.dir)], check=True)

    def file(self, content: str, mode: int = 0o600) -> str:
        self.n += 1
        path = self.dir / f"in{self.n}.json"
        path.write_text(content, encoding="utf-8")
        os.chmod(path, mode)
        return str(path)

    def run_vet(self, args: calls.VetArgs, stdin: str = "") -> tuple[str, list[Any]]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("sys.stdin", io.StringIO(stdin)):
            calls.run(args)
        text = out.getvalue()
        objs = [json.loads(line) for line in text.splitlines() if line.startswith("{")]
        return text, objs

    def first(self, questions: list[dict[str, Any]], stdin: bool = False) -> tuple[str, dict[str, Any]]:
        body = json.dumps({"version": 1, "questions": questions})
        if stdin:
            text, objs = self.run_vet(calls.VetArgs(questions="-"), body)
        else:
            text, objs = self.run_vet(calls.VetArgs(questions=self.file(body)))
        return text, objs[-1]

    def second(self, token: str, verdicts: list[dict[str, Any]], stdin: bool = False) -> dict[str, Any]:
        body = json.dumps({"version": 1, "verdicts": verdicts})
        if stdin:
            _, objs = self.run_vet(calls.VetArgs(pass_token=token, verdicts="-"), body)
        else:
            _, objs = self.run_vet(calls.VetArgs(pass_token=token, verdicts=self.file(body)))
        return objs[-1]

    def records(self) -> list[Path]:
        d = verdicts_dir()
        return sorted(d.iterdir()) if d.exists() else []


class FirstCall(Base):
    def test_prints_filters_and_records_nothing(self) -> None:
        # @scenario inquisitor: The first call prints the filters and records no verdict
        text, out = self.first([picker("Should retries back off?", ["Yes", "No"])])
        self.assertIn("Already answered", text)
        self.assertIn("Cheap to reverse", text)
        self.assertIn("Filter 1 found nothing.", text)
        self.assertRegex(out["token"], r"^[0-9a-f]{32}$")
        digest = question_hash("Should retries back off?\nYes\nNo")
        self.assertEqual(out["questions"][0]["hash"], digest)
        self.assertEqual(self.records(), [])
        token_file = self.state / "inquisitor" / "tokens" / f"{out['token']}.json"
        self.assertEqual(stat.S_IMODE(token_file.stat().st_mode), 0o600)
        self.assertNotIn("retries", token_file.read_text())

    def test_readable_questions_file_refused(self) -> None:
        # @scenario inquisitor: A questions file others can read is refused
        body = json.dumps({"version": 1, "questions": [picker("Q?", ["A", "B"])]})
        with self.assertRaises(Refused) as cm:
            calls.run(calls.VetArgs(questions=self.file(body, 0o644)))
        self.assertIn("mktemp -d", str(cm.exception))
        self.assertFalse((self.state / "inquisitor" / "tokens").exists())

    def test_category_only_on_stdin(self) -> None:
        # @scenario inquisitor: A question with a category given in a file is refused
        q = picker("Can this path traversal be exploited?", ["Yes", "No"], category="secret")
        with self.assertRaises(Refused) as cm:
            self.first([q])
        self.assertIn("standard input", str(cm.exception))
        self.assertIn("every other question", str(cm.exception))
        self.assertFalse((self.state / "inquisitor" / "tokens").exists())

    def test_unknown_category_refused(self) -> None:
        # @scenario inquisitor: An unknown category is refused
        with self.assertRaises(Refused):
            self.first([picker("Q?", ["A", "B"], category="private")], stdin=True)
        self.assertFalse((self.state / "inquisitor" / "tokens").exists())

    def test_category_keeps_only_the_hash(self) -> None:
        # @scenario inquisitor: The three categories and their records
        # (neither the token nor the record holds the question's text)
        for category in ("vulnerability", "secret", "personal"):
            text, out = self.first([picker("Is the key in the vault?", ["Yes", "No"],
                                           category=category)], stdin=True)
            self.assertNotIn("vault", text)
            token_file = self.state / "inquisitor" / "tokens" / f"{out['token']}.json"
            self.assertNotIn("vault", token_file.read_text())
            self.second(out["token"], [{"question": 1, "verdict": "deferred",
                                        "field": {"where": "my report"}}], stdin=True)
            record = json.loads((verdicts_dir() / f"{out['questions'][0]['hash']}.json").read_text())
            self.assertEqual(record["category"], category)
            self.assertNotIn("vault", json.dumps(record))

    def test_post_question_holding_a_token_refused(self) -> None:
        # @scenario inquisitor: A question holding a secret is refused in a post
        post = self.file(f"Intro.\n\nShould we rotate {TOKEN} today?\n")
        with self.assertRaises(Refused) as cm:
            calls.run(calls.VetArgs(post=post))
        self.assertIn("question 1", str(cm.exception))
        self.assertNotIn(TOKEN, str(cm.exception))

    def test_token_in_link_target_refused(self) -> None:
        # @scenario inquisitor: A token in a link target is refused
        post = self.file(f"Should we use [the docs](https://x/?token={TOKEN})?\n")
        with self.assertRaises(Refused):
            calls.run(calls.VetArgs(post=post))

    def test_post_questions_and_concerns(self) -> None:
        # @scenario inquisitor: A question about another repository names it
        post = self.file("## Open questions\n\n- Should retries back off?\n  Concerns: o/web\n"
                         "- Cap them?\n\nAnything else?\n")
        _, objs = self.run_vet(calls.VetArgs(post=post, repository="o/api"))
        out = objs[-1]
        self.assertEqual([q["item"] for q in out["questions"]], [1, 2, None])
        self.assertEqual(out["questions"][0]["hash"], question_hash("Should retries back off?"))
        token = json.loads((self.state / "inquisitor" / "tokens" / f"{out['token']}.json").read_text())
        self.assertEqual(token["questions"][0]["concerns"], {"repository": "o/web", "asked_from": "o/api"})
        self.assertEqual(token["questions"][1]["concerns"], {"repository": "o/api", "asked_from": "o/api"})


class SecondCall(Base):
    def test_each_verdict_with_its_field_recorded(self) -> None:
        # @scenario inquisitor: Each verdict carries its field
        # @scenario inquisitor: The related decision is named at the second call
        # @scenario inquisitor: The records have mode 0600
        questions = [picker(f"Question {i}?", ["A", "B"], files=["src/x.py"]) for i in range(4)]
        _, out = self.first(questions)
        verdicts = [
            {"question": 1, "verdict": "answered", "field": {"citation": "docs/x.md#retries"}},
            {"question": 2, "verdict": "deferred", "field": {"where": "this PR's description"}},
            {"question": 3, "verdict": "decided", "field": {"where": "docs/x.md"}},
            {"question": 4, "verdict": "ask", "field": {"recommended": "A", "changes": "B: slower."},
             "related": "https://github.com/o/api/pull/3"},
        ]
        result = self.second(out["token"], verdicts)
        self.assertEqual([line["question"] for line in result["lines"]], [4])
        records = calls.read_records({q["hash"] for q in out["questions"]})
        assert records is not None
        by_q = [cast(dict[str, Any], records[q["hash"]]) for q in out["questions"]]
        self.assertEqual(by_q[0]["field"], {"citation": "docs/x.md#retries"})
        self.assertEqual(by_q[1]["verdict"], "deferred")
        self.assertEqual(by_q[3]["related"], "https://github.com/o/api/pull/3")
        self.assertEqual(by_q[3]["files"], ["src/x.py"])
        self.assertEqual(by_q[3]["concerns"], {"repository": "o/api", "asked_from": "o/api"})
        self.assertEqual(stat.S_IMODE(verdicts_dir().stat().st_mode), 0o700)
        self.assertEqual(verdicts_dir(), self.state / "inquisitor" / "verdicts")
        for path in self.records():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_records_default_to_home_state(self) -> None:
        # @scenario inquisitor: The records have mode 0600
        # (with XDG_STATE_HOME unset, records land under HOME at mode 0600)
        with mock.patch.dict(os.environ, {"HOME": str(self.dir)}):
            os.environ.pop("XDG_STATE_HOME")
            home = self.dir / ".local" / "state" / "inquisitor" / "verdicts"
            self.assertEqual(verdicts_dir(), home)
            _, out = self.first([picker("Q?", ["A", "B"])])
            self.second(out["token"], [{"question": 1, "verdict": "decided", "field": {"where": "x"}}])
            self.assertEqual(stat.S_IMODE(home.stat().st_mode), 0o700)
            for path in home.iterdir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_record_holds_no_option_label(self) -> None:
        # @scenario inquisitor: A record holds no option's label
        _, out = self.first([picker("Which backoff?", ["Exponential", "Linear"])])
        self.second(out["token"], [{"question": 1, "verdict": "ask",
                                    "field": {"recommended": "Exponential", "changes": "Slower recovery."}}])
        raw = self.records()[0].read_text()
        self.assertNotIn("Exponential", raw)
        self.assertNotIn("Linear", raw)
        self.assertIn("Slower recovery.", raw)

    def assert_refused_and_kept(self, token: str, verdicts: list[dict[str, Any]], stdin: bool = False) -> str:
        with self.assertRaises(Refused) as cm:
            self.second(token, verdicts, stdin)
        self.assertEqual(self.records(), [])
        self.assertTrue((self.state / "inquisitor" / "tokens" / f"{token}.json").exists())
        return str(cm.exception)

    def test_missing_field_refused(self) -> None:
        # @scenario inquisitor: A verdict without its field is refused
        _, out = self.first([picker("Q?", ["A", "B"])])
        self.assert_refused_and_kept(out["token"], [{"question": 1, "verdict": "answered", "field": {}}])
        self.assert_refused_and_kept(out["token"], [{"question": 1, "verdict": "answered"}])

    def test_secret_in_field_refused(self) -> None:
        # @scenario inquisitor: A verdict field holding a secret is refused
        _, out = self.first([picker("Q?", ["A", "B"])])
        self.assert_refused_and_kept(out["token"], [{"question": 1, "verdict": "deferred",
                                                     "field": {"where": f"see {TOKEN}"}}])

    def test_stale_and_spent_tokens_refused(self) -> None:
        # @scenario inquisitor: A stale token is refused
        _, out = self.first([picker("Q?", ["A", "B"])])
        verdict = [{"question": 1, "verdict": "decided", "field": {"where": "docs/x.md"}}]
        self.second(out["token"], verdict)
        before = self.records()[0].read_text()
        with self.assertRaises(Refused) as cm:
            self.second(out["token"], verdict)
        self.assertIn("spent", str(cm.exception))
        self.assertEqual(self.records()[0].read_text(), before)

        _, out = self.first([picker("Other?", ["A", "B"])])
        path = self.state / "inquisitor" / "tokens" / f"{out['token']}.json"
        data = json.loads(path.read_text())
        data["issued"] = time.time() - 2 * 60 * 60 - 5
        path.write_text(json.dumps(data))
        with self.assertRaises(Refused) as cm:
            self.second(out["token"], verdict)
        self.assertIn("run the first call again", str(cm.exception))
        self.assertEqual(len(self.records()), 1)

    def test_question_left_without_verdict_refused(self) -> None:
        # @scenario inquisitor: A question left without a verdict is refused
        _, out = self.first([picker("One?", ["A", "B"]), picker("Two?", ["A", "B"])])
        decided = {"verdict": "decided", "field": {"where": "docs/x.md"}}
        self.assert_refused_and_kept(out["token"], [{"question": 1, **decided}])
        self.assert_refused_and_kept(out["token"], [{"question": 1, **decided},
                                                    {"question": 2, **decided},
                                                    {"question": 3, **decided}])

    def test_verdicts_in_readable_file_refused(self) -> None:
        # @scenario inquisitor: A questions file others can read is refused
        # (its AND: the second call refuses verdicts in such a file)
        _, out = self.first([picker("Q?", ["A", "B"])])
        body = json.dumps({"version": 1, "verdicts": [
            {"question": 1, "verdict": "decided", "field": {"where": "x"}}]})
        with self.assertRaises(Refused):
            calls.run(calls.VetArgs(pass_token=out["token"], verdicts=self.file(body, 0o644)))
        self.assertEqual(self.records(), [])

    def test_recommended_must_be_first(self) -> None:
        # @scenario inquisitor: The recommended answer comes first
        _, out = self.first([picker("Which?", ["Linear", "Exponential"])])
        message = self.assert_refused_and_kept(out["token"], [{"question": 1, "verdict": "ask", "field": {
            "recommended": "Exponential", "changes": "x"}}])
        self.assertIn("first option", message)
        self.assertIn("run the first call again", message)

    def test_skill_name_syntax(self) -> None:
        # @scenario inquisitor: A skill name off the syntax is refused
        # @scenario inquisitor: A question spec-trace requires is posted with its line
        _, out = self.first([picker("Adopt spec-trace?", ["Yes", "No"])])
        ask = {"question": 1, "verdict": "ask", "field": {"recommended": "Yes", "changes": "No: untraced."}}
        self.assert_refused_and_kept(out["token"], [{**ask, "requires": "Spec Trace"}])
        result = self.second(out["token"], [{**ask, "requires": "spec-trace"}])
        self.assertEqual(result["lines"][0]["person_required_line"],
                         "Inquisitor: a person must decide this (required by spec-trace).")
        records = calls.read_records({out["questions"][0]["hash"]})
        assert records is not None
        self.assertEqual(records[out["questions"][0]["hash"]].get("requires"), "spec-trace")

    def test_category_recorded_by_hash_only(self) -> None:
        # @scenario inquisitor: A question holding a secret is recorded by hash only
        # @scenario inquisitor: A question with a category given in a file is refused
        # (its AND: verdicts for such a question in a file are refused)
        q = picker("Is the key in the vault?", ["Yes", "No"], category="secret")
        _, out = self.first([q], stdin=True)
        ask = [{"question": 1, "verdict": "ask", "field": {"recommended": "Yes", "changes": "No: rotate."}}]
        message = self.assert_refused_and_kept(out["token"], ask)
        self.assertIn("standard input", message)
        self.second(out["token"], ask, stdin=True)
        record = json.loads(self.records()[0].read_text())
        self.assertEqual(set(record), {"version", "hash", "verdict", "time", "category"})
        self.assertEqual(record["category"], "secret")
        self.assertEqual(record["hash"], question_hash(question_text(
            Question("picker", "Is the key in the vault?", ("Yes", "No")))))


class RecordLine(Base):
    def line_for(self, q: dict[str, Any], stdin: bool = False) -> str:
        _, out = self.first([q], stdin)
        result = self.second(out["token"], [{"question": 1, "verdict": "ask", "field": {
            "recommended": "Yes", "changes": "No: x."}}], stdin)
        return result["lines"][0]["record_line"]

    def test_picker_shows_where_recorded(self) -> None:
        # @scenario inquisitor: The picker shows where the answer will be recorded
        self.assertEqual(self.line_for(picker("Retry?", ["Yes", "No"])),
                         "Recorded: o/api questions branch (private)")

    def test_wider_record_names_source(self) -> None:
        # @scenario inquisitor: A wider record names its source before the person answers
        lore = config.Config(login="alice", lore=(config.LoreRepo(path="/l", owners=("o",),
                                                                  repository="o/lore"),))
        vis = {"o/lore": "public", "o/api": "private"}
        with mock.patch("config.load", return_value=lore), \
                mock.patch("github.visibility", side_effect=vis.__getitem__):
            line = self.line_for({"kind": "picker", "question": "Name releases how?",
                                  "options": ["Yes", "No"], "concerns": {"lore": "o/lore"}})
        self.assertEqual(line, "Recorded: o/lore questions branch (public), more visible than "
                         "o/api (private), where this was asked")

    def test_not_recorded_reasons(self) -> None:
        # @scenario inquisitor: Not recorded gives a listed reason
        q = picker("Retry?", ["Yes", "No"])
        self.assertEqual(self.line_for({**q, "concerns": {}}), "Not recorded: about your way of working")
        self.assertEqual(self.line_for({**q, "category": "vulnerability"}, stdin=True),
                         "Not recorded: only a security advisory may hold it")
        self.assertEqual(self.line_for({**q, "category": "personal"}, stdin=True),
                         "Not recorded: it has a category")
        with mock.patch("github.write_access", return_value=None):
            self.assertEqual(self.line_for(q), "Not recorded: no push access to its questions branch")
        self.assertEqual(self.line_for({**q, "concerns": {"lore": "o/lore"}}),
                         "Not recorded: no team's lore repository serves it")
        with mock.patch("github.session_login", return_value=None):
            self.assertEqual(self.line_for(q), "Not recorded: no GitHub login configured")

    def test_post_question_gets_no_record_line(self) -> None:
        # @scenario inquisitor: The picker shows where the answer will be recorded
        # (only a picker question gets a record line)
        _, out = self.first([{"kind": "post", "question": "Retry?", "concerns": {"repository": "o/api"}}])
        result = self.second(out["token"], [{"question": 1, "verdict": "ask", "field": {
            "recommended": "Back off.", "changes": "No: hammering."}}])
        self.assertNotIn("record_line", result["lines"][0])


class ReadRecords(Base):
    def test_old_records_deleted(self) -> None:
        # @scenario inquisitor: An old record is deleted
        d = verdicts_dir()
        d.mkdir(parents=True, mode=0o700)
        old, new = "a" * 64, "b" * 64
        (d / f"{old}.json").write_text(json.dumps({"version": 1, "hash": old, "verdict": "deferred",
                                                   "time": time.time() - 7300, "category": "vulnerability"}))
        (d / f"{new}.json").write_text(json.dumps({"version": 1, "hash": new, "verdict": "ask",
                                                   "time": time.time()}))
        (d / "notes.txt").write_text("keep")
        self.assertEqual(set(calls.read_records({new}) or {}), {new})
        self.assertFalse((d / f"{old}.json").exists())
        self.assertTrue((d / "notes.txt").exists())

    def test_unreadable_records(self) -> None:
        # @scenario inquisitor: A post is blocked when the verdict records cannot be read
        # (read_records gives None, which the post hook blocks on)
        self.assertEqual(calls.read_records({"a" * 64}), {})
        d = verdicts_dir()
        d.mkdir(parents=True, mode=0o700)
        (d / f"{'c' * 64}.json").write_text("not json")
        self.assertIsNone(calls.read_records({"c" * 64}))
        self.assertEqual(calls.read_records({"d" * 64}), {})


class AllOrNone(Base):
    def test_failed_record_write_records_nothing(self) -> None:
        # @scenario inquisitor: A verdict without its field is refused
        # (as there, a failed second call records nothing and keeps the token)
        _, out = self.first([picker("One?", ["A", "B"]), picker("Two?", ["A", "B"])])
        real = calls.write_private
        writes: list[Path] = []

        def failing(path: Path, text: str) -> None:
            if path.parent == verdicts_dir():
                writes.append(path)
                if len(writes) == 2:
                    raise OSError(28, "No space left on device")
            real(path, text)

        decided = {"verdict": "decided", "field": {"where": "docs/x.md"}}
        with mock.patch("calls.write_private", side_effect=failing), self.assertRaises(OSError):
            self.second(out["token"], [{"question": 1, **decided}, {"question": 2, **decided}])
        self.assertEqual([p.name for p in self.records() if not p.name.startswith(".")], [])
        self.assertTrue((self.state / "inquisitor" / "tokens" / f"{out['token']}.json").exists())

    def test_conflicting_verdicts_for_one_text_refused(self) -> None:
        # @scenario inquisitor: A question left without a verdict is refused
        # (one text keeps one record, so two verdicts for it cannot both be kept)
        post = self.file("Should we retry?\n\nNot done:\n\n- Should we retry?\n")
        _, objs = self.run_vet(calls.VetArgs(post=post, repository="o/api"))
        out = objs[-1]
        self.assertEqual(out["questions"][0]["hash"], out["questions"][1]["hash"])
        with self.assertRaises(Refused):
            self.second(out["token"], [
                {"question": 1, "verdict": "ask", "field": {"recommended": "Yes.", "changes": "No: x."}},
                {"question": 2, "verdict": "deferred", "field": {"where": "this PR's description"}}])
        self.assertEqual(self.records(), [])
        deferred = {"verdict": "deferred", "field": {"where": "this PR's description"}}
        self.second(out["token"], [{"question": 1, **deferred}, {"question": 2, **deferred}])
        self.assertEqual(len(self.records()), 1)


class Edges(Base):
    def test_boolean_question_number_refused(self) -> None:
        # @scenario inquisitor: A question left without a verdict is refused
        # (`true` names no question the first call took)
        _, out = self.first([picker("Q?", ["A", "B"])])
        with self.assertRaises(Refused):
            self.second(out["token"], [{"question": True, "verdict": "decided", "field": {"where": "x"}}])
        self.assertEqual(self.records(), [])

    def line(self, q: dict[str, Any]) -> str:
        _, out = self.first([q])
        result = self.second(out["token"], [{"question": 1, "verdict": "ask", "field": {
            "recommended": "Yes", "changes": "No: x."}}])
        return result["lines"][0]["record_line"]

    def test_record_line_without_asked_from(self) -> None:
        # @scenario inquisitor: The picker shows where the answer will be recorded
        with mock.patch("calls._working_repository", return_value=None), \
                mock.patch("github.visibility", side_effect={"o/api": "public"}.get):
            self.assertEqual(self.line(picker("Retry?", ["Yes", "No"])),
                             "Recorded: o/api questions branch (public)")

    def test_no_login_before_access_check(self) -> None:
        # @scenario inquisitor: Not recorded gives a listed reason
        with mock.patch("github.session_login", return_value=None), \
                mock.patch("github.write_access", return_value=None):
            self.assertEqual(self.line(picker("Retry?", ["Yes", "No"])),
                             "Not recorded: no GitHub login configured")

    def test_named_repository_beats_owner(self) -> None:
        # @scenario inquisitor: A lore repository naming the repository beats one naming its owner
        lore = config.Config(login="alice", lore=(
            config.LoreRepo(path="/a", owners=("o",), repository="o/lore-org"),
            config.LoreRepo(path="/b", repos=("o/api",), repository="o/lore-api"),
            config.LoreRepo(path="/c", owners=("o",), repository="o/lore-later")))
        q = {"kind": "picker", "question": "Name releases?", "options": ["Yes", "No"],
             "concerns": {"lore": "o/lore-api"}}
        with mock.patch("config.load", return_value=lore):
            self.assertTrue(self.line(q).startswith("Recorded: o/lore-api questions branch"))
            with mock.patch("calls._working_repository", return_value="o/web"):
                self.assertTrue(self.line(q).startswith("Recorded: o/lore-org questions branch"))
            with mock.patch("calls._working_repository", return_value="x/web"):
                self.assertEqual(self.line(q), "Not recorded: no team's lore repository serves it")

    def test_unknown_visibilities_count_against_sharing(self) -> None:
        # @scenario inquisitor: A wider record names its source before the person answers
        q = picker("Retry?", ["Yes", "No"], concerns={"repository": "o/web", "asked_from": "o/api"})
        with mock.patch("github.visibility", return_value=None):
            self.assertEqual(self.line(q), "Recorded: o/web questions branch (public), more visible "
                             "than o/api (private), where this was asked")


class OneTextOneRecord(Base):
    def test_same_text_about_two_repositories_refused(self) -> None:
        # @scenario inquisitor: A question left without a verdict is refused
        # (one text keeps one record, so the two concerns cannot both be kept)
        post = self.file("Should we bump the version?\nConcerns: o/api\n\n"
                         "Should we bump the version?\nConcerns: o/web\n")
        _, objs = self.run_vet(calls.VetArgs(post=post))
        ask = {"verdict": "ask", "field": {"recommended": "Yes.", "changes": "No: x."}}
        with self.assertRaises(Refused):
            self.second(objs[-1]["token"], [{"question": 1, **ask}, {"question": 2, **ask}])
        self.assertEqual(self.records(), [])

    def test_same_text_with_and_without_category_refused(self) -> None:
        # @scenario inquisitor: A question holding a secret is recorded by hash only
        # (the same text without its category would leave a full record)
        q = picker("Rotate the key?", ["Yes", "No"])
        _, out = self.first([{**q, "category": "secret"}, q], stdin=True)
        ask = {"verdict": "ask", "field": {"recommended": "Yes", "changes": "No: x."}}
        with self.assertRaises(Refused):
            self.second(out["token"], [{"question": 1, **ask}, {"question": 2, **ask}], stdin=True)
        self.assertEqual(self.records(), [])


if __name__ == "__main__":
    unittest.main()

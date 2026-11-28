"""Tests for log_command: the `log` and `misses` commands, with the questions
branch, GitHub and the configuration replaced by fakes."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Literal
from unittest import mock

import branches
import config
import github
import log_command
from common import Refused
from formats import (HashOnlyMiss, LogFile, MissFile, Unreadable, miss_hash, parse, render)
from log_command import LogArgs, MissesArgs

Q1 = "2026-10-20-should-retries-back-off-3f9a1c.md"
Q2 = "2026-10-20-should-retries-back-off-4b0b0b.md"
VIS: dict[str, github.Visibility | None] = {
    "o/api": "private", "o/web": "public", "o/lore": "public", "o/private-item": "private",
    "o/public-item": "public", "o/internal-lore": "internal", "o/unknown": None,
}


def question_file(name: str, repository: str | None, asked_from: str,
                  answered: bool = False) -> str:
    text = render(LogFile(name=name, asked="2026-10-20", question="Should retries back off?",
                          repository=repository, asked_from=asked_from))
    if answered:
        text = text.replace("---\n## Question", 'answered_by: "alice"\nauthority: "input"\n'
                            f'recorded_in: "questions/{name}"\n---\n## Question') + "## Answer\n> yes\n"
    return text


class Fakes(unittest.TestCase):
    """A questions branch per repository, a comment store, GitHub's faked
    replies, and a private directory for input files."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        os.chmod(self.tmp, 0o700)
        self.branch: dict[str, list[branches.BranchFile]] = {}
        self.pushed: list[dict[str, Any]] = []
        self.push_result = branches.PushResult(pushed=True)
        self.comments: dict[str, github.Comment] = {}
        self.write: set[tuple[str, str]] = {("o/api", "alice"), ("o/lore", "alice"),
                                           ("o/web", "alice")}
        self.cfg = config.Config(login="alice", lore=(
            config.LoreRepo(path=str(self.tmp / "lore"), owners=("o",), repository="o/lore"),
            config.LoreRepo(path=str(self.tmp / "ilore"), owners=("o",),
                            repository="o/internal-lore")))
        self.here: str | None = "o/api"
        self.gh_calls: list[str] = []
        self.vis = dict(VIS)
        self.unreadable: set[str] = set()
        patches = [
            mock.patch.object(branches, "list_files", self.list_files),
            mock.patch.object(branches, "push_file", self.push_file),
            mock.patch.object(github, "visibility", self.visibility),
            mock.patch.object(github, "comment", self.comment),
            mock.patch.object(github, "session_login", self.session_login),
            mock.patch.object(github, "write_access", self.write_access),
            mock.patch.object(config, "load", self.load),
            mock.patch.object(log_command, "current_repository", self.current),
            mock.patch.object(log_command, "today", self.today),
            mock.patch.object(log_command, "random_hex", self.random_hex),
            mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.tmp / "state")}),
        ]
        os.environ.pop("IGOR_RUN", None)
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    # -- fakes

    def session_login(self, configured: str | None) -> str | None:
        return configured if configured == "alice" else None

    def write_access(self, repository: str, login: str) -> bool | None:
        return (repository, login) in self.write

    def load(self) -> config.Config:
        return self.cfg

    def current(self) -> str | None:
        return self.here

    def today(self) -> str:
        return "2026-10-21"

    def random_hex(self) -> str:
        return "a1b2c3"

    def list_files(self, repository: str) -> list[branches.BranchFile] | None:
        if repository in self.unreadable:
            return None
        return list(self.branch.get(repository, []))

    def push_file(self, repository: str, path: str, content: str,
                  as_inquisitor: bool, service: bool) -> branches.PushResult:
        self.pushed.append({"repository": repository, "path": path, "content": content,
                            "message": f"inquisitor: log {path}", "as_inquisitor": as_inquisitor,
                            "service": service})
        return self.push_result

    def visibility(self, repository: str) -> github.Visibility | None:
        self.gh_calls.append(f"visibility {repository}")
        return self.vis.get(repository)

    def comment(self, url: str) -> github.Comment | None:
        self.gh_calls.append(f"comment {url}")
        return self.comments.get(url)

    def add(self, repository: str, path: str, content: str) -> None:
        self.branch.setdefault(repository, []).append(
            branches.BranchFile(path=path, content=content, added_by="c" * 40))

    # -- running the command

    def input(self, data: dict[str, Any], mode: int = 0o600) -> str:
        path = self.tmp / "in.json"
        path.write_text(json.dumps({"version": 1, **data}), encoding="utf-8")
        os.chmod(path, mode)
        return str(path)

    def log(self, data: dict[str, Any], **flags: Any) -> dict[str, Any]:
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(log_command.run(LogArgs(input=self.input(data), **flags)), 0)
        return json.loads(out.getvalue())

    def refused(self, data: dict[str, Any], says: str, **flags: Any) -> None:
        with self.assertRaises(Refused) as caught:
            log_command.run(LogArgs(input=self.input(data), **flags))
        self.assertIn(says, str(caught.exception))
        self.assertEqual(self.pushed, [])

    def written(self, index: int = -1) -> LogFile | MissFile | HashOnlyMiss:
        push = self.pushed[index]
        parsed = parse(push["path"], push["content"], push["repository"] in ("o/lore",
                                                                              "o/internal-lore"))
        assert not isinstance(parsed, Unreadable), parsed
        assert isinstance(parsed, (LogFile, MissFile, HashOnlyMiss))
        return parsed


POST = "https://github.com/o/api/issues/7#issuecomment-1001"
REPLY = "https://github.com/o/api/issues/7#issuecomment-1002"
DISCORD = "https://discord.com/channels/1/2/3"


def question(**extra: Any) -> dict[str, Any]:
    return {"kind": "question", "branch": {"repository": "o/api"},
            "question": "Should retries back off?\nConcerns: o/api\n@alice",
            "asked_in": POST, **extra}


def answer(answer_in: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"kind": "answer", "branch": {"repository": "o/api"},
            "question": "Should retries back off?", "answer": answer_in, **extra}


class Questions(Fakes):
    def test_question_goes_to_its_repository_branch(self) -> None:
        # @scenario inquisitor: A question about a repository goes to its questions branch
        # @scenario inquisitor: A question waiting for its answer is already logged
        # @scenario inquisitor: A question logged and asked in a post links the post
        self.here = "o/api"
        result = self.log(question())
        path = "questions/2026-10-21-should-retries-back-off-a1b2c3.md"
        self.assertEqual(result, {"version": 1, "status": "pushed", "path": path})
        f = self.written()
        assert isinstance(f, LogFile)
        self.assertEqual((f.repository, f.asked_from, f.asked_in, f.answer),
                         ("o/api", "o/api", POST, None))
        self.assertIn("@alice", f.question)
        self.assertEqual(self.pushed[0]["repository"], "o/api")

    def test_commit_message_carries_no_trailer(self) -> None:
        # @scenario inquisitor: A log or miss file's commit carries no trailer
        self.log(question())
        push = self.pushed[0]
        self.assertEqual(push["message"], f"inquisitor: log {push['path']}")
        self.assertFalse(push["as_inquisitor"])

    def test_organization_file_names_where_asked_from(self) -> None:
        # @scenario inquisitor: An organization's file names where it was asked from
        # @scenario inquisitor: An organization's question goes to its lore repository
        self.here = "o/web"
        self.log(question(branch={"lore": "o/lore"}, asked_in=
                          "https://github.com/o/web/issues/7#issuecomment-1001"))
        f = self.written()
        assert isinstance(f, LogFile)
        self.assertEqual((f.repository, f.asked_from), (None, "o/web"))
        self.assertEqual(self.pushed[0]["repository"], "o/lore")

    def test_unconfigured_lore_repository_logs_nothing(self) -> None:
        # @scenario inquisitor: A collective's question no lore repository serves logs nothing
        # A collective's question is about an organization or other group, logged on its lore
        # repository.
        self.refused(question(branch={"lore": "o/other-lore"}), "no configured lore repository")

    def test_input_others_can_read_is_refused(self) -> None:
        # @scenario inquisitor: A log command input others can read is refused
        with self.assertRaises(Refused):
            log_command.run(LogArgs(input=self.input(question(), mode=0o644)))
        self.assertEqual(self.pushed, [])

    def test_closing_heading_in_question_is_refused(self) -> None:
        # @scenario inquisitor: A question holding a closing section's heading is refused
        self.refused(question(question="Should we?\n## Discussion\nmore"),
                     "would be read as a closing section")

    def test_malformed_links_are_refused(self) -> None:
        # @scenario inquisitor: The log command refuses an answer_link of no given form
        self.refused(question(asked_in="https://example.com/t/5"), "asked_in")
        self.refused(answer({"answered_by": "alice", "authority": "input",
                             "answer_link": "https://example.com/a/5"}), "answer_link")
        self.assertEqual([c for c in self.gh_calls if c.startswith("comment")], [])

    def test_secret_is_not_written(self) -> None:
        # @scenario inquisitor: A log file holding a secret is not written
        self.refused(question(question="Is ghp_abcdefghijklmnop the token?"),
                     "credential patterns")
        self.refused(question(question="Should we use [x](https://x/?t=ghp_abc)?"),
                     "credential patterns")

    def test_secret_after_an_escaped_line_break_is_not_written(self) -> None:
        # @scenario inquisitor: A log file holding a secret is not written
        for said in ("see config\nghp_" + "A" * 36, "x\tAKIA" + "B" * 16):
            self.refused({"kind": "miss", "branch": {"repository": "o/api"}, "question": "Q?",
                          "miss": {"filter": "1", "said": said, "said_by": "alice",
                                   "name": {"kind": "message", "value": POST}}},
                         "credential patterns")

    def test_private_thread_stays_off_public_branch(self) -> None:
        # @scenario inquisitor: A question asked in a private thread stays off a public questions branch
        self.here = "o/web"
        self.refused(question(branch={"repository": "o/web"}, repository="o/web"),
                     "more visible than " + POST)

    def test_private_organization_question_not_logged_when_asked(self) -> None:
        # @scenario inquisitor: A private repository's organization question is not logged when asked
        # @scenario inquisitor: A private repository's question stays out of an internal lore repository
        self.here = "o/api"
        self.refused(question(branch={"lore": "o/lore"}), "more visible than o/api")
        self.refused(question(branch={"lore": "o/internal-lore"}), "more visible than o/api")
        self.refused(question(branch={"lore": "o/lore"}), "more visible", confirm_visible=True)
        self.assertFalse((self.tmp / "state" / "inquisitor" / "pending").exists())

    def test_question_not_asked_in_a_post_waits_for_its_answer(self) -> None:
        # @scenario inquisitor: A picker question is pushed once it is answered
        # A picker question, asked in Claude Code's question tool rather than a post, is logged only
        # once answered.
        data = question()
        del data["asked_in"]
        self.refused(data, "logged unanswered only when asked in a GitHub post")
        self.refused(question(asked_in=DISCORD), "logged unanswered only when asked in a GitHub post")
        self.refused(question(answer={"answered_by": "alice", "authority": "input", "text": "x"}),
                     "another kind's")

    def test_outside_any_repository_there_is_no_asked_from(self) -> None:
        # @scenario inquisitor: Where a file goes and how its slug is made
        self.here = None
        self.refused(question(), "no asked_from")
        self.here = "o/api"
        self.log(question(question="../ --- a: b?"))
        self.assertEqual(self.pushed[0]["path"], "questions/2026-10-21-a-b-a1b2c3.md")


class Answers(Fakes):
    def test_whole_comment_text_and_author(self) -> None:
        # @scenario inquisitor: A comment's whole text is recorded as the answer
        # @scenario inquisitor: The answer's answered_by is the linked comment's author
        # @scenario inquisitor: A whole comment fits as the answer
        self.comments[REPLY] = github.Comment(url=REPLY, text="Yes.\n\n## Answer: quoted",
                                              login="mallory", author_type="User", node_id="N")
        self.log(answer({"answered_by": "alice", "authority": "decision", "answer_link": REPLY,
                         "text": "something else"}))
        f = self.written()
        assert isinstance(f, LogFile) and f.answer is not None
        self.assertEqual((f.answer.answered_by, f.answer.text, f.answer.answer_link,
                          f.answer.recorded_in, f.answer.authority),
                         ("mallory", "Yes.\n\n## Answer: quoted", REPLY, REPLY, "input"))

    def test_bot_author_is_input(self) -> None:
        # @scenario inquisitor: The answer's answered_by is the linked comment's author
        # @scenario inquisitor: A User says comment with no answer file is input
        # `User says: ` is how a relay bot's comment starts.
        self.comments[REPLY] = github.Comment(url=REPLY, text="User says: yes", login="x[bot]",
                                              author_type="Bot", node_id="N")
        self.write.add(("o/api", "x[bot]"))
        self.log(answer({"answered_by": "alice", "authority": "decision", "answer_link": REPLY}))
        f = self.written()
        assert isinstance(f, LogFile) and f.answer is not None
        self.assertEqual((f.answer.answered_by, f.answer.authority), ("x[bot]", "input"))

    def test_linked_comment_with_write_access_is_a_decision(self) -> None:
        # @scenario inquisitor: The answer's answered_by is the linked comment's author
        self.comments[REPLY] = github.Comment(url=REPLY, text="Yes.", login="alice",
                                              author_type="User", node_id="N")
        self.log(answer({"answered_by": "bob", "authority": "decision", "answer_link": REPLY}))
        f = self.written()
        assert isinstance(f, LogFile) and f.answer is not None
        self.assertEqual((f.answer.answered_by, f.answer.authority), ("alice", "decision"))

    def test_unreadable_comment_is_not_logged(self) -> None:
        # @scenario inquisitor: A linked comment the script cannot read is not logged
        self.refused(answer({"answered_by": "alice", "authority": "input",
                             "answer_link": REPLY}), "does not return the comment")

    def test_unlinked_answer_by_someone_else_is_input(self) -> None:
        # @scenario inquisitor: An unlinked answer by someone other than the session's person is input
        self.write.add(("o/api", "bob"))
        self.log(answer({"answered_by": "bob", "authority": "decision", "text": "Back off."}))
        f = self.written()
        assert isinstance(f, LogFile) and f.answer is not None
        self.assertEqual((f.answer.answered_by, f.answer.authority, f.answer.text),
                         ("bob", "input", "Back off."))
        self.assertEqual(f.answer.recorded_in, "questions/" + f.name)

    def test_picker_answer_authority_follows_write_access(self) -> None:
        # @scenario inquisitor: A picker answer from a person with write access is a decision
        # @scenario inquisitor: A picker answer from a person without write access is input
        # @scenario inquisitor: A picker answer is logged in the person's words
        self.log(answer({"answered_by": "alice", "authority": "decision",
                         "text": "back off but cap it at a minute"}))
        self.write.clear()
        self.log(answer({"answered_by": "alice", "authority": "decision", "text": "Back off."}))
        first, second = self.written(0), self.written(1)
        assert isinstance(first, LogFile) and first.answer is not None
        assert isinstance(second, LogFile) and second.answer is not None
        self.assertEqual(first.answer.authority, "decision")
        self.assertEqual(first.answer.text, "back off but cap it at a minute")
        self.assertEqual(second.answer.authority, "input")

    def test_answers_must_name_unanswered_files_on_the_branch(self) -> None:
        # @scenario inquisitor: An answers key naming no file on the branch is refused
        # @scenario inquisitor: An answers key naming an answered file is refused
        self.refused(answer({"answered_by": "alice", "authority": "input", "text": "x",
                             "answers": [Q1]}), "is not on the questions branch")
        self.add("o/api", "questions/" + Q1, question_file(Q1, "o/api", "o/api", answered=True))
        self.refused(answer({"answered_by": "alice", "authority": "input", "text": "x",
                             "answers": [Q1]}), "already holds an answer")

    def test_answer_file_names_both_files(self) -> None:
        # @scenario inquisitor: An answer file names the file it answers
        # @scenario inquisitor: One answer file names both files holding a question
        # @scenario inquisitor: A later answer on the questions branch is a new file
        self.add("o/api", "questions/" + Q1, question_file(Q1, "o/api", "o/api"))
        self.add("o/api", "questions/" + Q2, question_file(Q2, "o/api", "o/api"))
        self.log(answer({"answered_by": "alice", "authority": "input", "text": "x",
                         "answers": [Q1, Q2]}))
        f = self.written()
        assert isinstance(f, LogFile) and f.answer is not None
        self.assertEqual(f.answer.answers, (Q1, Q2))
        self.assertNotIn(self.pushed[0]["path"], ("questions/" + Q1, "questions/" + Q2))

    def test_answer_file_copies_most_private_asked_from(self) -> None:
        # @scenario inquisitor: An answer file copies the most private asked_from
        # @scenario inquisitor: An answer file with no answers key takes a question file's asked_from
        self.add("o/lore", "questions/" + Q1, question_file(Q1, None, "o/public-item"))
        self.add("o/lore", "questions/" + Q2, question_file(Q2, None, "o/private-item"))
        base = {"branch": {"lore": "o/lore"}}
        self.here = "o/lore"
        self.vis["o/lore"] = "private"
        self.log(answer({"answered_by": "alice", "authority": "input", "text": "x",
                         "answers": [Q1, Q2]}, **base))
        f = self.written()
        assert isinstance(f, LogFile)
        self.assertEqual(f.asked_from, "o/private-item")
        self.log(answer({"answered_by": "alice", "authority": "input", "text": "x"}, **base))
        f = self.written()
        assert isinstance(f, LogFile)
        self.assertEqual(f.asked_from, "o/lore")

    def test_different_repository_keys_get_a_file_each(self) -> None:
        # @scenario inquisitor: Files with different repository keys get an answer file each
        self.here = "o/lore"
        self.add("o/lore", "questions/" + Q1, question_file(Q1, "o/web", "o/web"))
        self.add("o/lore", "questions/" + Q2, question_file(Q2, None, "o/web"))
        self.refused(answer({"answered_by": "alice", "authority": "input", "text": "x",
                             "answers": [Q1, Q2]}, branch={"lore": "o/lore"}),
                     "get one answer file each")
        self.log(answer({"answered_by": "alice", "authority": "input", "text": "x",
                         "answers": [Q2]}, branch={"lore": "o/lore"}))
        self.log(answer({"answered_by": "alice", "authority": "input", "text": "x",
                         "answers": [Q1]}, branch={"lore": "o/lore"}, repository="o/web"))
        self.assertEqual(len(self.pushed), 2)

    def test_picker_question_from_private_work_needs_confirmation(self) -> None:
        # @scenario inquisitor: A picker question from private work reaches a public questions branch only once confirmed
        # @scenario inquisitor: Without the confirmation the record stays as private as its source
        data = answer({"answered_by": "alice", "authority": "decision", "text": "Yes."},
                      branch={"repository": "o/web"}, repository="o/web")
        self.refused(data, "more visible than o/api")
        self.log(data, confirm_visible=True)
        f = self.written()
        assert isinstance(f, LogFile)
        self.assertEqual(f.asked_from, "o/web")

    def test_confirmed_record_drops_links_and_re_line(self) -> None:
        # @scenario inquisitor: A confirmed answer drops the relay post's Re line
        # @scenario inquisitor: A GitHub link into a more private repository is left out
        # @scenario inquisitor: The question is found in its thread and logged once confirmed
        self.here = "o/web"
        relay = "https://github.com/o/api/issues/7#issuecomment-1003"
        self.comments[relay] = github.Comment(
            url=relay, text="User says: yes\nRe: https://github.com/o/api/issues/7",
            login="relay", author_type="Bot", node_id="N")
        self.log(answer({"answered_by": "alice", "authority": "decision", "answer_link": relay},
                        branch={"lore": "o/lore"}, asked_in=POST),
                 service=True, asked_from="o/api", confirm_visible=True)
        f = self.written()
        assert isinstance(f, LogFile) and f.answer is not None
        self.assertEqual((f.asked_in, f.answer.answer_link, f.asked_from, f.answer.text,
                          f.answer.answers), (None, None, "o/lore", "User says: yes", ()))
        self.assertEqual(f.answer.recorded_in, "questions/" + f.name)


class Service(Fakes):
    def test_service_only_inputs_are_refused_without_it(self) -> None:
        # @scenario inquisitor: The log command refuses a handled key without its service option
        # @scenario inquisitor: The log command refuses a hash-only miss file without its service option
        # @scenario inquisitor: The log command refuses a reply-id miss without its service option
        # @scenario inquisitor: A Discord answer link without the service option is refused
        # @scenario inquisitor: An asking agent writes no handled file
        self.add("o/api", "questions/" + Q1, question_file(Q1, "o/api", "o/api"))
        self.refused({"kind": "handled", "branch": {"repository": "o/api"}, "closes": Q1},
                     "answer service's option")
        self.refused(question(closes=Q1), "answer service's option")
        miss = {"kind": "miss", "branch": {"repository": "o/api"},
                "miss": {"filter": "4", "said": "x", "name": {"kind": "github", "value": "N1"}}}
        self.refused(miss, "answer service's option", hash_only=True)
        self.refused({**miss, "question": "Q?"}, "reply's id")
        self.refused(answer({"answered_by": "alice", "authority": "input", "text": "x",
                             "answer_link": DISCORD}), "Linear or Discord answer_link")

    def test_more_service_only_inputs_are_refused_without_it(self) -> None:
        # @scenario inquisitor: The log command refuses a handled key without its service option
        # @scenario inquisitor: The log command refuses a hash-only miss file without its service option
        self.refused(answer({"answered_by": "alice", "authority": "input", "text": "x"},
                            handled="2026-10-20"), "answer service's option")
        self.refused({"kind": "miss", "branch": {"repository": "o/api"},
                      "miss": {"filter": "4", "said": "x",
                               "name": {"kind": "message", "value": POST}}},
                     "hash-only", hash_only=True)

    def test_discord_link_recorded_and_never_fetched(self) -> None:
        # @scenario inquisitor: A Discord answer link is recorded and never fetched
        self.log(answer({"answered_by": "bob", "authority": "decision",
                         "answer_link": DISCORD, "text": "User says: back off."}),
                 service=True, asked_from="o/api")
        f = self.written()
        assert isinstance(f, LogFile) and f.answer is not None
        self.assertEqual((f.answer.answer_link, f.answer.text, f.answer.answered_by,
                          f.answer.recorded_in), (DISCORD, "User says: back off.", "alice",
                                                  DISCORD))
        self.assertEqual([c for c in self.gh_calls if c.startswith("comment")], [])
        self.assertTrue(self.pushed[0]["service"])

    def test_service_answered_by_is_session_person(self) -> None:
        # @scenario inquisitor: With its service option, answered_by is the session's person
        # @scenario answer-service: A GitHub relay's answer is read from the comment
        self.comments[REPLY] = github.Comment(url=REPLY, text="User says: yes", login="relay",
                                              author_type="Bot", node_id="N")
        self.log(answer({"answered_by": "bob", "authority": "decision", "answer_link": REPLY,
                         "rephrased": "Should every  service back off?",
                         "discussion": "It keeps\nqueues short."}),
                 service=True, asked_from="o/api")
        f = self.written()
        assert isinstance(f, LogFile) and f.answer is not None
        self.assertEqual((f.answer.answered_by, f.answer.authority, f.answer.text),
                         ("alice", "decision", "User says: yes"))
        self.assertEqual(f.answer.rephrased, "Should every service back off?")

    def test_withheld_relay_url_is_not_recorded_in(self) -> None:
        # @scenario inquisitor: A withheld relay URL is not kept as recorded_in
        # @scenario inquisitor: A confirmed answer from a Discord thread is recorded on a public branch
        self.log(answer({"answered_by": "alice", "authority": "input", "answer_link": DISCORD,
                         "text": "User says: yes"}, branch={"repository": "o/web"},
                        repository="o/web", asked_in="https://discord.com/channels/1/2/9"),
                 service=True, asked_from="o/web", confirm_visible=True)
        f = self.written()
        assert isinstance(f, LogFile) and f.answer is not None
        self.assertEqual((f.answer.answer_link, f.asked_in, f.asked_from), (None, None, "o/web"))
        self.assertEqual(f.answer.recorded_in, "questions/" + f.name)

    def test_handled_file(self) -> None:
        # @scenario inquisitor: A handled file's keys
        # @scenario inquisitor: A handled file may go to a more visible questions branch
        self.add("o/web", "questions/" + Q1, question_file(Q1, "o/web", "o/api"))
        result = self.log({"kind": "handled", "branch": {"repository": "o/web"}, "closes": Q1,
                           "handled": "2026-10-20"}, service=True)
        self.assertEqual(result["path"], "questions/2026-10-21-handled-a1b2c3.md")
        self.assertEqual(self.pushed[0]["content"],
                         f'---\nhandled: "2026-10-20"\ncloses: "{Q1}"\n---\n')

    def test_failed_service_push_keeps_nothing(self) -> None:
        # @scenario inquisitor: A file the answer service cannot push leaves no pending copy
        self.push_result = branches.PushResult(pushed=False, why="no write access")
        result = self.log(answer({"answered_by": "alice", "authority": "input", "text": "x"}),
                          service=True, asked_from="o/api")
        self.assertEqual(result, {"version": 1, "status": "failed", "path": None,
                                  "why": "no write access"})
        self.assertTrue(self.pushed[0]["service"])

    def test_pending_push_is_reported(self) -> None:
        # @scenario inquisitor: A file an agent cannot push is kept pending and reported
        self.push_result = branches.PushResult(pushed=False, pending=True, why="no write access")
        result = self.log(question())
        self.assertEqual((result["status"], result["why"]), ("pending", "no write access"))
        self.assertFalse(self.pushed[0]["service"])


class Misses(Fakes):
    def test_file_miss_is_named_by_its_question_file(self) -> None:
        # @scenario inquisitor: A miss with no reply hashes its question's file path
        # @scenario inquisitor: A miss file's keys
        # @scenario inquisitor: A miss goes to the questions branch its question's file is on
        self.add("o/api", "questions/" + Q1, question_file(Q1, "o/api", "o/api"))
        result = self.log({"kind": "miss", "branch": {"repository": "o/api"},
                           "question": "Should retries back off?", "asked": "2026-10-25",
                           "miss": {"filter": "3", "said": "It had one sensible answer.",
                                    "said_by": "alice", "asked_by": "web-bot[bot]",
                                    "name": {"kind": "file", "value": "questions/" + Q1}}})
        digest = miss_hash("file", "questions/" + Q1)
        self.assertEqual(result["path"], f"misses/{digest}.md")
        f = self.written()
        assert isinstance(f, MissFile)
        self.assertEqual((f.filter, f.said_by, f.asked_by, f.repository, f.asked_from, f.asked),
                         ("3", "alice", "web-bot[bot]", "o/api", "o/api", "2026-10-20"))

    def test_message_miss_counts_its_thread_as_source(self) -> None:
        # @scenario inquisitor: A question asked in a private thread stays off a public questions branch
        # @scenario inquisitor: A miss file's keys
        self.here = "o/web"
        linear = "https://linear.app/o/issue/ENG-1"
        for url in (linear, POST):
            self.refused({"kind": "miss", "branch": {"repository": "o/web"}, "question": "Q?",
                          "miss": {"filter": "3", "said": "obvious", "said_by": "alice",
                                   "name": {"kind": "message", "value": url}}}, "more visible")
        self.here = "o/api"
        self.log({"kind": "miss", "branch": {"repository": "o/api"}, "question": "Q?",
                  "miss": {"filter": "3", "said": "obvious", "said_by": "alice",
                           "name": {"kind": "message", "value": linear}}})
        f = self.written()
        assert isinstance(f, MissFile)
        self.assertEqual(f.asked_in, linear)

    def test_confirmed_miss_drops_asked_by(self) -> None:
        # @scenario inquisitor: A miss file's keys
        # A confirmed miss drops asked_by, as *The answerer's confirmation can send a record
        # somewhere more visible* requires.
        self.here = "o/api"
        self.log({"kind": "miss", "branch": {"lore": "o/lore"}, "question": "Q?",
                  "miss": {"filter": "3", "said": "obvious", "said_by": "alice",
                           "asked_by": "bob", "name": {"kind": "message", "value": POST}}},
                 confirm_visible=True)
        f = self.written()
        assert isinstance(f, MissFile)
        self.assertEqual((f.asked_by, f.asked_from), (None, "o/lore"))

    def test_taken_miss_name_pushes_nothing(self) -> None:
        # @scenario inquisitor: A retried push of a miss already on the branch pushes nothing
        digest = miss_hash("message", POST)
        self.add("o/api", f"misses/{digest}.md", "---\n---\n")
        result = self.log({"kind": "miss", "branch": {"repository": "o/api"},
                           "question": "Q?", "miss": {"filter": "1", "said": "x",
                                                      "name": {"kind": "message", "value": POST}}})
        self.assertEqual(result["status"], "taken")
        self.assertEqual(self.pushed, [])

    def test_hash_only_miss(self) -> None:
        # @scenario inquisitor: A hash-only miss file holds nothing
        # @scenario inquisitor: A miss file is named by its reply's id
        result = self.log({"kind": "miss", "branch": {"repository": "o/web"},
                           "miss": {"filter": "4", "said": "x",
                                    "name": {"kind": "discord", "value": "123"}}},
                          service=True, hash_only=True)
        self.assertEqual(result["path"], f"misses/{miss_hash('discord', '123')}.md")
        self.assertEqual(self.pushed[0]["content"], "---\n---\n")
        self.assertTrue(self.pushed[0]["as_inquisitor"])

    def test_unreadable_branch_is_refused_or_reported(self) -> None:
        # @scenario inquisitor: An answers key naming no file on the branch is refused
        self.unreadable.add("o/api")
        self.refused(answer({"answered_by": "alice", "authority": "input", "text": "x",
                             "answers": [Q1]}), "cannot read the questions branch of o/api")
        out = io.StringIO()
        with redirect_stdout(out):
            log_command.run_misses(MissesArgs(repository="o/api"))
        self.assertEqual(json.loads(out.getvalue())["not_read"], ["o/api"])

    def test_misses_lists_by_filter(self) -> None:
        # @scenario inquisitor: A hash-only miss file holds nothing
        self.add("o/api", "misses/" + "a" * 64 + ".md", "---\n---\n")
        misses: list[tuple[str, Literal["1", "2", "3", "4"]]] = [("b" * 64, "1"), ("c" * 64, "3")]
        for digest, flt in misses:
            self.add("o/api", f"misses/{digest}.md", render(MissFile(
                hash=digest, asked="2026-10-20", filter=flt, said="x", question="Q?",
                repository="o/api", asked_from="o/api")))
        self.add("o/api", "misses/see-o-api-issue-4.md", "x")
        out = io.StringIO()
        with redirect_stdout(out):
            log_command.run_misses(MissesArgs(repository="o/api", filter="3"))
        listed = json.loads(out.getvalue())
        self.assertEqual([m["path"] for m in listed["misses"]], [f"misses/{'c' * 64}.md"])
        self.assertEqual(listed["hash_only"], {"o/api": 1})
        self.assertEqual(listed["unreadable"], ["o/api:misses/see-o-api-issue-4.md"])


if __name__ == "__main__":
    unittest.main()

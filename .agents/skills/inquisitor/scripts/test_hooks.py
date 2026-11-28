"""Tests for hooks: the picker hook and the post hook, called as Python and
through their shell scripts."""

import contextlib
import io
import json
import os
import re
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import hooks
from common import verdicts_dir
from qtext import (PERSON_REQUIRED_FORMAT, UNTAGGED_LINE, Question, find_questions, question_hash,
                   question_text)

HERE = Path(__file__).resolve().parent
TOKEN = "ghp_" + "a" * 36
SPEC_TRACE_LINE = PERSON_REQUIRED_FORMAT.format(skill="spec-trace")


def post_hash(text: str) -> str:
    return question_hash(question_text(Question("post", text)))


def picker_hash(text: str, labels: list[str]) -> str:
    return question_hash(question_text(Question("picker", text, tuple(labels))))


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        os.chmod(self.dir, 0o700)
        self.state = self.dir / "state"
        patch = mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.state)})
        patch.start()
        self.addCleanup(patch.stop)

    def tearDown(self) -> None:
        subprocess.run(["chmod", "-R", "u+rwx", str(self.dir)], check=True)
        subprocess.run(["rm", "-rf", str(self.dir)], check=True)

    def record(self, digest: str, verdict: str, age: float = 0, **extra: Any) -> None:
        """Write a verdict record as vet's second call writes one, with a
        default field for the verdict when none is given."""
        directory = verdicts_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{digest}.json"
        data: dict[str, Any] = {"version": 1, "hash": digest, "verdict": verdict,
                                "time": time.time() - age, **extra}
        if verdict != "not asked" and "category" not in extra and "field" not in extra:
            data["field"] = ({"recommended": "yes", "changes": "none"} if verdict == "ask"
                             else {"citation": "lore#1"} if verdict == "answered"
                             else {"where": "the report"})
        path.write_text(json.dumps(data), encoding="utf-8")
        os.chmod(path, 0o600)

    def write(self, name: str, text: str) -> str:
        (self.dir / name).write_text(text, encoding="utf-8")
        return name

    def call(self, run: Any, payload: Any) -> tuple[int, str]:
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = run(raw)
        return code, err.getvalue()


# -- the picker hook -----------------------------------------------------------

def picker_payload(*questions: tuple[str, list[str]]) -> dict[str, Any]:
    return {"tool_name": "AskUserQuestion", "tool_input": {"questions": [
        {"question": q, "header": "h", "multiSelect": False,
         "options": [{"label": label, "description": "d"} for label in labels]}
        for q, labels in questions]}}


class Picker(Base):
    Q = "Should retries back off?"
    OPTIONS = ["Yes", "No"]

    def ask(self, *questions: tuple[str, list[str]]) -> tuple[int, str]:
        return self.call(hooks.run_ask, picker_payload(*questions))

    # @scenario inquisitor: An unvetted question is blocked
    def test_unvetted(self) -> None:
        code, err = self.ask((self.Q, self.OPTIONS))
        self.assertEqual(code, 2)
        self.assertIn("Should retries back off?", err)
        self.assertIn("vet --questions", err)

    def test_vetted_passes(self) -> None:
        self.record(picker_hash("Should retries  back\noff?", self.OPTIONS), "ask")
        self.assertEqual(self.ask(("Should retries back off?", self.OPTIONS))[0], 0)

    # @scenario inquisitor: Adding the related-decision line needs no second vetting
    # @scenario inquisitor: A trimmed related-decision line is left out of a picker question
    def test_related_line_added(self) -> None:
        self.record(picker_hash(self.Q, self.OPTIONS), "ask")
        code, _ = self.ask((self.Q + "\n  Related: https://github.com/o/r/pull/3 ", self.OPTIONS))
        self.assertEqual(code, 0)

    # @scenario inquisitor: A related-decision line holding a secret is blocked
    def test_related_line_with_a_secret(self) -> None:
        text = f"{self.Q}\nRelated: https://github.com/o/r/pull/3?t={TOKEN}"
        self.record(picker_hash(text, self.OPTIONS), "ask")
        code, err = self.ask((text, self.OPTIONS))
        self.assertEqual(code, 2)
        self.assertIn("credential", err)

    # @scenario inquisitor: A related-decision line holding a secret is blocked
    def test_secret_names_only_the_secret(self) -> None:
        text = f"{self.Q}\nRelated: https://github.com/o/r/pull/3?t={TOKEN}"
        code, err = self.ask((text, self.OPTIONS))
        self.assertEqual(code, 2)
        self.assertIn("credential", err)
        self.assertNotIn("no verdict", err)

    # @scenario inquisitor: A question edited after vetting is blocked
    def test_edited(self) -> None:
        self.record(picker_hash(self.Q, self.OPTIONS), "ask")
        self.assertEqual(self.ask(("Should  retries\nback off?", self.OPTIONS))[0], 0)
        self.assertEqual(self.ask(("Should retries back off quickly?", self.OPTIONS))[0], 2)
        self.assertEqual(self.ask((self.Q, ["Yes", "Never"]))[0], 2)

    # The filters stopped it: its latest verdict is not ask.
    # @scenario inquisitor: A question the filters stopped is blocked
    def test_stopped(self) -> None:
        digest = picker_hash(self.Q, self.OPTIONS)
        for verdict in ("answered", "deferred", "decided", "not asked"):
            with self.subTest(verdict=verdict):
                self.record(digest, "ask", age=60)
                self.record(digest, verdict)
                code, err = self.ask((self.Q, self.OPTIONS))
                self.assertEqual(code, 2)
                self.assertIn(f"latest verdict is {verdict}", err)
        self.record(digest, "answered", field={"citation": "lore#7"})
        self.assertIn("citation: lore#7", self.ask((self.Q, self.OPTIONS))[1])

    def test_stale(self) -> None:
        self.record(picker_hash(self.Q, self.OPTIONS), "ask", age=2 * 3600 + 5)
        self.assertEqual(self.ask((self.Q, self.OPTIONS))[0], 2)

    # @scenario inquisitor: The picker hook fails open
    def test_fails_open(self) -> None:
        self.assertEqual(self.call(hooks.run_ask, "not json")[0], 0)
        self.assertEqual(self.call(hooks.run_ask, {"tool_input": {"questions": "x"}})[0], 0)
        verdicts_dir().mkdir(parents=True)
        (verdicts_dir() / f"{picker_hash(self.Q, self.OPTIONS)}.json").write_text("{bad")
        self.assertEqual(self.ask((self.Q, self.OPTIONS))[0], 0)
        os.chmod(verdicts_dir(), 0)
        self.assertEqual(self.ask((self.Q, self.OPTIONS))[0], 0)
        with mock.patch("hooks.read_records", side_effect=RuntimeError("boom")):
            self.assertEqual(self.ask((self.Q, self.OPTIONS))[0], 0)

    # A question with a category is recorded by its hash, verdict, time and
    # category only.
    # @scenario inquisitor: The hook lets through a question recorded by hash only
    def test_hash_only(self) -> None:
        self.record(picker_hash(self.Q, self.OPTIONS), "ask", category="personal")
        self.assertEqual(self.ask((self.Q, self.OPTIONS))[0], 0)

    def test_every_failed_question_is_named(self) -> None:
        self.record(picker_hash(self.Q, self.OPTIONS), "ask")
        code, err = self.ask((self.Q, self.OPTIONS), ("Cap at a minute?", self.OPTIONS))
        self.assertEqual(code, 2)
        self.assertIn("question 2", err)
        self.assertNotIn("question 1", err)


# -- the post hook -------------------------------------------------------------

class Post(Base):
    def bash(self, command: str) -> dict[str, Any]:
        return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.dir)}

    def post(self, body: str, command: str = "gh issue comment 7 --body-file body.md"
             ) -> tuple[int, str]:
        self.write("body.md", body)
        return self.call(hooks.run_post, self.bash(command))

    def tool(self, tool: str, /, **tool_input: Any) -> tuple[int, str]:
        return self.call(hooks.run_post, {"tool_name": tool, "tool_input": tool_input,
                                          "cwd": str(self.dir)})

    # @scenario inquisitor: A post with an unvetted question is blocked
    def test_unvetted(self) -> None:
        code, err = self.post("We could retry. Should retries back off?\n",
                              "gh pr create --title Retries --body-file body.md")
        self.assertEqual(code, 2)
        self.assertIn("Should retries back off?", err)
        self.assertIn("vet --post", err)
        self.record(post_hash("Should retries back off?"), "ask")
        self.assertEqual(self.post("We could retry. Should retries back off?\n",
                                   "gh pr create --title Retries --body-file body.md")[0], 0)

    # The filters stopped it: its latest verdict is answered or decided.
    # @scenario inquisitor: A post with a question the filters stopped is blocked
    def test_stopped(self) -> None:
        digest = post_hash("Should retries back off?")
        for verdict, field in (("answered", "citation: lore#1"), ("decided", "where: the report")):
            with self.subTest(verdict=verdict):
                self.record(digest, "ask", age=60)
                self.record(digest, verdict)
                code, err = self.post("Should retries back off?\n")
                self.assertEqual(code, 2)
                self.assertIn(f"latest verdict is {verdict}", err)
                self.assertIn(field, err)

    # @scenario inquisitor: A post is blocked when the verdict records cannot be read
    def test_records_unreadable(self) -> None:
        verdicts_dir().mkdir(parents=True)
        (verdicts_dir() / f"{post_hash('Should retries back off?')}.json").write_text("{bad")
        code, err = self.post("Should retries back off?\n")
        self.assertEqual(code, 2)
        self.assertIn("verdict records cannot be read", err)
        self.assertEqual(self.post("No question here.\n")[0], 0)

    # @scenario inquisitor: A post is blocked when the verdict records cannot be read
    def test_records_unlistable_and_no_question(self) -> None:
        verdicts_dir().mkdir(parents=True)
        os.chmod(verdicts_dir(), 0)
        self.assertEqual(self.post("No question here.\n")[0], 0)
        self.assertEqual(self.post("Should retries back off?\n")[0], 2)

    # The scenario lets a title holding no question through; a reserved prefix
    # applies to bodies, not titles.
    # @scenario inquisitor: A question in a title is refused on every surface
    def test_title_with_a_reserved_prefix_passes(self) -> None:
        self.assertEqual(self.post("No question.\n", "gh pr create --title 'User says: retries' "
                                   "--body-file body.md")[0], 0)

    # Asked in running text, outside any deferral label.
    # @scenario inquisitor: A deferred question asked outside an open-questions section is blocked
    def test_deferred_in_running_text(self) -> None:
        self.record(post_hash("Should retries back off?"), "deferred")
        for command in ("gh issue comment 7 --body-file body.md",
                        "gh issue create --title Retries --body-file body.md"):
            with self.subTest(command=command):
                code, err = self.post("Should retries back off?\n", command)
                self.assertEqual(code, 2)
                self.assertIn("needs an ask verdict", err)

    # @scenario inquisitor: A deferred question may be listed in a post
    def test_deferred_listed(self) -> None:
        self.record(post_hash("Should retries back off?"), "deferred")
        self.assertEqual(self.post("Not in this change:\n\n- Should retries back off?\n")[0], 0)

    # @scenario inquisitor: A deferred question may be listed in a post
    def test_deferred_listed_with_the_untagged_line(self) -> None:
        self.record(post_hash("Should retries back off?"), "deferred")
        body = f"Not in this change:\n\n- Should retries back off?\n  {UNTAGGED_LINE}\n"
        self.assertEqual(self.post(body)[0], 0)

    # @scenario inquisitor: A deferred question that tags a person is blocked
    def test_deferred_mention_in_underscore_emphasis(self) -> None:
        self.record(post_hash("Should retries back off?\n_cc @alice_"), "deferred")
        self.assertEqual(self.post("Not in this change:\n\n- Should retries back off?\n"
                                   "  _cc @alice_\n")[0], 2)
        self.record(post_hash("Should retries back off?\n[option A](if @alice agrees)"), "deferred")
        self.assertEqual(self.post("Not in this change:\n\n- Should retries back off?\n"
                                   "  [option A](if @alice agrees)\n")[0], 2)

    def deferred_item(self, item: str, command: str = "gh issue comment 7 --body-file body.md"
                      ) -> int:
        """Post `item` as the only item under a deferral label, its found
        question recorded deferred; the hook's exit code."""
        body = f"Not in this change:\n\n- {item}\n"
        for found in find_questions(body, in_code=True):
            self.record(question_hash(question_text(found.question)), "deferred")
        if command.startswith("python3"):
            self.write("m.md", body)
            return self.call(hooks.run_post, self.bash(command))[0]
        return self.post(body, command)[0]

    # @scenario inquisitor: A deferred question that tags a person is blocked
    def test_deferred_mention_beside_backticks_that_open_no_span(self) -> None:
        self.assertEqual(self.deferred_item("Is \\` the separator @alice wants, or `|`?"), 2)
        self.assertEqual(self.deferred_item("Is ``` the fence @alice wants, or `~~~`?"), 2)

    # @scenario inquisitor: A deferred question that tags a person is blocked
    def test_deferred_mention_after_a_span_over_two_lines(self) -> None:
        self.assertEqual(self.deferred_item(
            "Should we rename `retry\n  policy` for @alice or keep `old`?"), 2)

    # @scenario inquisitor: A deferred question that tags a person is blocked
    def test_deferred_discord_mention_in_either_form(self) -> None:
        command = "python3 /abs/discord_bot.py post --channel 1 --message-file m.md"
        for mention in ("<@123456789>", "<@!123456789>"):
            with self.subTest(mention=mention):
                self.assertEqual(self.deferred_item(f"Should retries back off? {mention}",
                                                    command), 2)

    # @scenario inquisitor: A deferred question may be listed in a post
    def test_deferred_naming_a_team_or_a_commented_login(self) -> None:
        for question in ("Should @o/devs own the retry policy?",
                         "Should retries back off? <!-- @alice -->"):
            with self.subTest(question=question):
                self.record(post_hash(question), "deferred")
                self.assertEqual(self.post(f"Not in this change:\n\n- {question}\n")[0], 0)

    # @scenario inquisitor: A deferred question that tags a person is blocked
    def test_deferred_mentioning_a_person_in_its_text(self) -> None:
        question = "Should @alice decide whether retries back off?"
        self.record(post_hash(question), "deferred")
        code, err = self.post(f"Not in this change:\n\n- {question}\n")
        self.assertEqual(code, 2)
        self.assertIn("needs an ask verdict", err)

    # @scenario inquisitor: A deferred question that tags a person is blocked
    def test_deferred_tagged(self) -> None:
        self.record(post_hash("Should retries back off?"), "deferred")
        code, err = self.post("Not in this change:\n\n- Should retries back off?\n  @alice\n")
        self.assertEqual(code, 2)
        self.assertIn("needs an ask verdict", err)

    # @scenario inquisitor: A post with a stale verdict is blocked
    def test_stale(self) -> None:
        digest = post_hash("Should retries back off?")
        self.record(digest, "ask", age=2 * 3600 + 5)
        code, err = self.post("Should retries back off?\n")
        self.assertEqual(code, 2)
        self.assertIn("Should retries back off?", err)
        self.record(digest, "deferred", age=2 * 3600 + 5)
        self.assertEqual(self.post("Not in this change:\n\n- Should retries back off?\n")[0], 2)

    # @scenario inquisitor: A question with an ask verdict listed as deferred is blocked
    def test_ask_listed_as_deferred(self) -> None:
        self.record(post_hash("Should retries back off?"), "ask")
        code, err = self.post("Not done:\n\n- Should retries back off?\n")
        self.assertEqual(code, 2)
        self.assertIn("Open questions", err)
        self.assertEqual(self.post("Open questions:\n\n- Should retries back off?\n")[0], 0)

    # @scenario inquisitor: A call that sends no post passes the post hook
    def test_no_post(self) -> None:
        self.assertEqual(self.call(hooks.run_post, self.bash("gh pr view 7"))[0], 0)
        self.assertEqual(self.tool("mcp__linear__get_issue", id="X-1")[0], 0)
        self.assertEqual(self.call(hooks.run_post, {"tool_name": "Read",
                                                    "tool_input": {"file_path": "x"}})[0], 0)

    # A JSON value other than an object passes too.
    # @scenario inquisitor: A hook payload that is not JSON passes the post hook
    def test_not_json(self) -> None:
        self.assertEqual(self.call(hooks.run_post, "not json")[0], 0)
        self.assertEqual(self.call(hooks.run_post, "[1]")[0], 0)

    # @scenario inquisitor: A GitHub MCP post is checked
    def test_github_mcp(self) -> None:
        for name in ("mcp__github__add_issue_comment", "mcp__claude_ai_GitHub__add_issue_comment"):
            with self.subTest(name=name):
                code, err = self.tool(name, owner="o", repo="r", issue_number=7,
                                      body="Should retries back off?")
                self.assertEqual(code, 2)
                self.assertIn("Should retries back off?", err)

    # @scenario inquisitor: A post whose body cannot be read is blocked
    def test_unreadable(self) -> None:
        code, err = self.call(hooks.run_post,
                              self.bash('gh pr comment 5 --body "$(cat body.md)"'))
        self.assertEqual(code, 2)
        self.assertIn("gh pr comment <number> --body-file <file>", err)

    # @scenario inquisitor: A tool-call post with a reserved prefix is blocked
    def test_reserved_prefix(self) -> None:
        code, err = self.call(hooks.run_post,
                              self.bash("gh issue comment 7 --body 'User says: yes'"))
        self.assertEqual(code, 2)
        self.assertIn("User says:", err)
        review = {"body": "Looks fine.", "event": "COMMENT",
                  "comments": [{"path": "a.py", "line": 1, "body": "User says: yes"}]}
        self.write("review.json", json.dumps(review))
        self.assertEqual(self.call(hooks.run_post, self.bash(
            "gh api repos/o/r/pulls/5/reviews -X POST --input review.json"))[0], 2)
        self.assertEqual(self.call(hooks.run_post,
                                   self.bash("gh issue comment 7 --body 'Says: yes'"))[0], 0)

    # @scenario inquisitor: A reserved prefix in markup is blocked too
    def test_reserved_prefix_in_markup(self) -> None:
        for body in ("'**User says:** yes'", "' User says: yes'"):
            with self.subTest(body=body):
                self.assertEqual(self.call(hooks.run_post, self.bash(
                    f"gh issue comment 7 --body {body}"))[0], 2)

    # @scenario inquisitor: A question in a title is refused on every surface
    def test_title(self) -> None:
        self.record(post_hash("Retry with backoff?"), "ask")
        self.record(post_hash("Retries?"), "ask")
        self.record(post_hash("Ship it?"), "ask")
        code, err = self.post("No question.\n", "gh pr create --title 'Retry with backoff?' "
                              "--body-file body.md")
        self.assertEqual(code, 2)
        self.assertIn("ask it in the post's body", err)
        code, err = self.tool("mcp__linear__save_project", name="Retries?")
        self.assertEqual(code, 2)
        self.assertIn("issue's description or a comment", err)
        code, err = self.call(hooks.run_post, self.bash(
            "python3 /abs/discord_bot.py thread --message-id 9 --name 'Ship it?'"))
        self.assertEqual(code, 2)
        self.assertIn("ask it in the post's body", err)
        self.assertEqual(self.post("No question.\n", "gh pr create --title 'Retry with backoff' "
                                   "--body-file body.md")[0], 0)

    # @scenario inquisitor: A question in a Linear project's summary is refused
    def test_linear_summary(self) -> None:
        self.record(post_hash("Should retries back off?"), "ask")
        code, err = self.tool("mcp__linear__save_project", id="p", summary="Should retries back off?")
        self.assertEqual(code, 2)
        self.assertIn("issue's description or a comment", err)
        self.assertEqual(self.tool("mcp__linear__save_project", id="p",
                                   summary="Backoff:\n\n```\nretry?\n```\n")[0], 0)
        self.assertEqual(self.tool("mcp__linear__save_project", id="p",
                                   summary="User says: go")[0], 2)

    # @scenario inquisitor: A Discord message through discord-bot is vetted
    def test_discord(self) -> None:
        command = "python3 /abs/discord_bot.py post --message-file m.md"
        self.write("m.md", "Should retries back off?")
        code, err = self.call(hooks.run_post, self.bash(command))
        self.assertEqual(code, 2)
        self.assertIn("Should retries back off?", err)
        self.write("m.md", "User says: yes")
        self.assertEqual(self.call(hooks.run_post, self.bash(command))[0], 2)

    # @scenario inquisitor: A Linear comment or description through the Linear MCP is vetted
    def test_linear(self) -> None:
        self.assertEqual(self.tool("mcp__linear__save_comment", issueId="X-1",
                                   body="User says: yes")[0], 2)
        question = "Should this repository adopt spec-trace?"
        self.record(post_hash(question), "ask", requires="spec-trace")
        code, err = self.tool("mcp__linear__save_issue", id="X-1", description=question)
        self.assertEqual(code, 2)
        self.assertIn("person-required line", err)
        self.assertEqual(self.tool("mcp__linear__save_issue", id="X-1",
                                   description=f"{question}\n{SPEC_TRACE_LINE}")[0], 0)
        self.write("m.md", question)
        self.assertEqual(self.call(hooks.run_post, self.bash(
            "python3 /abs/discord_bot.py post --message-file m.md"))[0], 2)

    # @scenario inquisitor: A missing or misplaced person-required line is blocked
    # @scenario inquisitor: A question spec-trace requires is posted with its line
    def test_person_required(self) -> None:
        question = "Should this repository adopt spec-trace?"
        self.record(post_hash(question), "ask", requires="spec-trace")
        self.assertEqual(self.post(f"{question}\n{SPEC_TRACE_LINE}\n")[0], 0)
        for body in (f"{question}\n",
                     f"{question}\n{PERSON_REQUIRED_FORMAT.format(skill='prose')}\n"):
            with self.subTest(body=body):
                code, err = self.post(body)
                self.assertEqual(code, 2)
                self.assertIn(question, err)
        other = "Should retries back off?"
        self.record(post_hash(other), "ask")
        code, err = self.post(f"{other}\n{SPEC_TRACE_LINE}\n")
        self.assertEqual(code, 2)
        self.assertIn(other, err)

    # @scenario inquisitor: A tag made for an App's post blocks a plain gh post
    def test_app_identity(self) -> None:
        question = "Should retries back off?"
        self.record(post_hash(question), "ask", identity="bot")
        body = f"{question}\n@alice\n"
        code, err = self.post(body, "gh pr comment 5 --body-file body.md")
        self.assertEqual(code, 2)
        self.assertIn("--identity bot", err)
        self.assertEqual(self.post(body, "python3 /abs/github_app.py --identity bot gh pr comment 5 "
                                   "--body-file body.md")[0], 0)

    # @scenario inquisitor: A post holding a question with a category is blocked
    def test_category(self) -> None:
        self.record(post_hash("Can the path traversal be exploited?"), "ask",
                    category="vulnerability")
        code, err = self.post("Can the path traversal be exploited?\n")
        self.assertEqual(code, 2)
        self.assertIn("security advisory", err)

    # @scenario inquisitor: A question in a code block is not asked
    # The plain reading reads code as text; the hiding reading skips it.
    # @scenario inquisitor: A question in code is found by the plain reading alone
    def test_not_asked_in_code(self) -> None:
        body = "Run this:\n\n```\nretry --why?\n```\n"
        self.assertEqual(self.post(body)[0], 2)
        self.record(post_hash("retry --why?"), "not asked")
        self.assertEqual(self.post(body)[0], 0)

    # @scenario inquisitor: A not asked question posted in running text is blocked
    def test_not_asked_in_running_text(self) -> None:
        self.record(post_hash("retry --why?"), "not asked")
        code, err = self.post("Should we run retry --why?\n\nretry --why?\n")
        self.assertEqual(code, 2)
        self.assertIn("needs an ask verdict", err)

    # @scenario inquisitor: A token added to a link target after vetting is blocked
    def test_token_in_link_target(self) -> None:
        self.record(post_hash("Should we use [the docs](https://x/)?"), "ask")
        self.assertEqual(self.post("Should we use [the docs](https://x/)?\n")[0], 0)
        code, err = self.post(f"Should we use [the docs](https://x/?token={TOKEN})?\n")
        self.assertEqual(code, 2)
        self.assertIn("credential", err)

    # @scenario inquisitor: A Related or tag line after a line ending no question is scanned
    def test_related_after_no_question(self) -> None:
        for line in (f"Related: https://x/?t={TOKEN}", f"@alice {TOKEN}"):
            with self.subTest(line=line):
                self.assertEqual(self.post(f"We retry.\n{line}\n")[0], 2)

    # @scenario inquisitor: Adding the tag line keeps the vetted hash
    def test_tag_line_added(self) -> None:
        self.record(post_hash("Should retries back off?"), "ask")
        for tag in ("@alice", UNTAGGED_LINE):
            with self.subTest(tag=tag):
                body = ("Open questions:\n\n- Should retries back off?\n"
                        f"  Related: https://github.com/o/r/pull/3\n  {tag}\n")
                self.assertEqual(self.post(body)[0], 0)

    # @scenario inquisitor: Signing after vetting keeps the post vetted
    def test_signed(self) -> None:
        self.record(post_hash("Should retries back off?"), "ask")
        self.assertEqual(self.post("Should retries back off?\n\nprose ✓ 3f2a91\n")[0], 0)

    def test_fails_closed(self) -> None:
        with mock.patch("hooks.post_reader.read_posts", side_effect=RuntimeError("boom")):
            code, err = self.call(hooks.run_post, self.bash("gh pr view 7"))
        self.assertEqual(code, 2)
        self.assertIn("boom", err)


# -- the scripts and hook.json ---------------------------------------------------

class Scripts(Base):
    def script(self, name: str, payload: str, env: dict[str, str] | None = None
               ) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(HERE / name)], input=payload, capture_output=True, text=True,
                              env={**os.environ, "XDG_STATE_HOME": str(self.state), **(env or {})},
                              check=False)

    # Spend no record: neither hook writes, deletes or uses up a verdict
    # record.
    # @scenario inquisitor: The hooks are on once installed, and spend no record
    def test_on_and_spend_no_record(self) -> None:
        manifest = json.loads((HERE.parent / "hook.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["default"], "enabled")
        commands = {h["command"]: h["events"]["claude"] for h in manifest["hooks"]}
        self.assertEqual(commands["scripts/check-ask.sh"],
                         {"event": "PreToolUse", "matcher": "^AskUserQuestion$"})
        self.assertEqual(commands["scripts/check-post.sh"]["event"], "PreToolUse")
        self.record(picker_hash("Should retries back off?", ["Yes", "No"]), "ask")
        self.record(post_hash("Should we cap at a minute?"), "ask")
        (self.dir / "c.md").write_text("Should we cap at a minute?\n", encoding="utf-8")
        picker = json.dumps(picker_payload(("Should retries back off?", ["Yes", "No"])))
        post = json.dumps({"tool_name": "Bash", "cwd": str(self.dir), "tool_input": {
            "command": "gh pr comment 5 --body-file c.md"}})
        for _ in range(2):
            self.assertEqual(self.script("check-ask.sh", picker).returncode, 0)
            self.assertEqual(self.script("check-post.sh", post).returncode, 0)
        self.assertEqual(len(list(verdicts_dir().iterdir())), 2)

    # @scenario inquisitor: The picker hook fails open
    def test_ask_script_fails_open(self) -> None:
        broken = {"PATH": str(self.dir)}
        (self.dir / "python3").write_text("#!/bin/sh\nexit 1\n")
        os.chmod(self.dir / "python3", 0o755)
        self.assertEqual(self.script("check-ask.sh", "{}", broken).returncode, 0)
        result = self.script("check-ask.sh", json.dumps(picker_payload(("Retry?", ["Yes"]))))
        self.assertEqual(result.returncode, 2)

    # @scenario inquisitor: A verdict recorded in another repository counts
    def test_another_repository(self) -> None:
        self.record(picker_hash("Should retries back off?", ["Yes", "No"]), "ask")
        other = self.dir / "other-clone"
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        result = subprocess.run(
            [str(HERE / "check-ask.sh")], cwd=other, capture_output=True, text=True, check=False,
            input=json.dumps(picker_payload(("Should retries back off?", ["Yes", "No"]))),
            env={**os.environ, "XDG_STATE_HOME": str(self.state)})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_post_script_fails_closed(self) -> None:
        (self.dir / "python3").write_text("#!/bin/sh\nexit 1\n")
        os.chmod(self.dir / "python3", 0o755)
        result = self.script("check-post.sh", "{}", {"PATH": f"{self.dir}:/usr/bin:/bin"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("post hook failed", result.stderr)
        self.assertEqual(self.script("check-post.sh", "not json").returncode, 0)

    # @scenario inquisitor: A GitHub MCP post is checked
    def test_matchers(self) -> None:
        manifest = json.loads((HERE.parent / "hook.json").read_text(encoding="utf-8"))
        matcher = next(h["events"]["claude"]["matcher"] for h in manifest["hooks"]
                       if h["command"] == "scripts/check-post.sh")
        for name in ("Bash", "mcp__github__create_issue", "mcp__plugin_x_github__create_issue",
                     "mcp__claude_ai_GitHub__create_issue", "mcp__linear__save_project",
                     "mcp__plugin_x_linear__save_comment", "mcp__claude_ai_Linear__save_issue"):
            self.assertIsNotNone(re.fullmatch(matcher, name), name)
        self.assertIsNone(re.fullmatch(matcher, "Read"))


if __name__ == "__main__":
    unittest.main()

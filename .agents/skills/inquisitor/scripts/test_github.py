"""Tests for github: lookups through gh, with gh replaced by canned
answers, so no test reaches GitHub."""

import json
import os
import unittest
from typing import Any
from unittest import mock

import github


class FakeGh:
    """Stands in for github.run_gh: answers by the joined args' prefix, and
    records every call."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []

    def __call__(self, args: list[str], env: dict[str, str] | None = None) -> tuple[int, str, str]:
        self.calls.append(args)
        self.envs.append(env)
        joined = " ".join(args)
        for prefix, answer in self.answers.items():
            if joined.startswith(prefix):
                if isinstance(answer, tuple):
                    return answer  # type: ignore[return-value]
                return 0, json.dumps(answer), ""
        return 1, "", "HTTP 404: Not Found"


def fake(answers: dict[str, Any]) -> FakeGh:
    return FakeGh(answers)


class Logins(unittest.TestCase):
    def test_configured_login_counts_when_gh_is_it(self) -> None:
        # @scenario inquisitor: A configured login counts when gh is logged in as it
        gh = fake({"api user": {"login": "alice"}})
        with mock.patch.object(github, "run_gh", gh):
            self.assertEqual(github.session_login("alice"), "alice")
            self.assertEqual(github.session_login("Alice"), "Alice")
            self.assertIsNone(github.session_login("bob"))
            self.assertIsNone(github.session_login(None))
        with mock.patch.object(github, "run_gh", fake({})):
            self.assertIsNone(github.session_login("alice"))

    def test_app_token_in_environment_is_ignored(self) -> None:
        # @scenario inquisitor: An agent posting as a GitHub App keeps the configured login
        gh = fake({"api user": {"login": "alice"}})
        with mock.patch.dict(os.environ, {"GH_TOKEN": "x", "GITHUB_TOKEN": "y"}), \
                mock.patch.object(github, "run_gh", gh):
            self.assertEqual(github.session_login("alice"), "alice")
        env = gh.envs[0]
        assert env is not None
        self.assertNotIn("GH_TOKEN", env)
        self.assertNotIn("GITHUB_TOKEN", env)


class WriteAccess(unittest.TestCase):
    def test_unreadable_permission_is_none(self) -> None:
        # @scenario inquisitor: A permission that cannot be read is no write access
        # @scenario inquisitor: Without push access, no answer counts by write access
        denied = (1, "", "gh: Must have push access to view collaborator permission. (HTTP 403)")
        gh = fake({"api repos/o/api/collaborators/alice/permission": denied})
        with mock.patch.object(github, "run_gh", gh):
            self.assertIsNone(github.write_access("o/api", "alice"))
        yes = fake({"api repos/o/api/collaborators/alice/permission":
                    {"permission": "write", "user": {"permissions": {"push": True}}},
                    "api repos/o/api/collaborators/bob/permission":
                    {"permission": "read", "user": {"permissions": {"push": False}}}})
        with mock.patch.object(github, "run_gh", yes):
            self.assertIs(github.write_access("o/api", "alice"), True)
            self.assertIs(github.write_access("o/api", "bob"), False)

    def test_malformed_login_makes_no_call(self) -> None:
        # @scenario inquisitor: A malformed login is skipped
        # @scenario inquisitor: An answer whose author's login is malformed is input
        gh = fake({})
        with mock.patch.object(github, "run_gh", gh):
            self.assertIsNone(github.write_access("o/api", "../orgs/x"))
            self.assertIsNone(github.write_access("o/api", "alice/../admin"))
            self.assertIsNone(github.write_access("o/api", "x[bot]"))
            self.assertIsNone(github.write_access("o/../../user", "alice"))
            self.assertIsNone(github.visibility("o/../../user"))
            self.assertIsNone(github.last_commit_author("o/../x", "README.md"))
        self.assertEqual(gh.calls, [])


class Visibility(unittest.TestCase):
    def test_visibility_and_ranking(self) -> None:
        # @scenario inquisitor: An unreadable visibility of where a post goes counts as public
        # @scenario inquisitor: A private repository's question goes to no internal or public place
        gh = fake({"repo view o/api": {"visibility": "PRIVATE"},
                   "repo view o/web": {"visibility": "PUBLIC"},
                   "repo view o/corp": {"visibility": "INTERNAL"}})
        with mock.patch.object(github, "run_gh", gh):
            api, web, corp = github.visibility("o/api"), github.visibility("o/web"), github.visibility("o/corp")
            self.assertEqual((api, web, corp), ("private", "public", "internal"))
            self.assertIsNone(github.visibility("o/gone"))
        self.assertTrue(github.more_visible(web, api))
        self.assertTrue(github.more_visible(corp, api))
        self.assertFalse(github.more_visible(api, web))
        self.assertFalse(github.more_visible(api, api))
        self.assertTrue(github.more_visible(None, None))
        self.assertTrue(github.more_visible(None, "internal"))
        self.assertTrue(github.more_visible("internal", None))
        self.assertFalse(github.more_visible("private", None))

    def test_unreadable_source_counts_as_private(self) -> None:
        # @scenario inquisitor: A well-formed asked_from whose visibility can't be read is private
        self.assertTrue(github.more_visible("public", None))
        self.assertFalse(github.more_visible(None, "public"))


class Comments(unittest.TestCase):
    def test_comment_text_and_author(self) -> None:
        # @scenario inquisitor: A comment's whole text is recorded as the answer
        # @scenario inquisitor: The answer's answered_by is the linked comment's author
        url = "https://github.com/o/api/pull/12#issuecomment-1002"
        gh = fake({"api repos/o/api/issues/comments/1002": {
            "html_url": url, "body": "Yes, back off.\nCap it at a minute, as the question suggests.",
            "user": {"login": "mallory", "type": "User"}, "node_id": "IC_kw1"}})
        with mock.patch.object(github, "run_gh", gh):
            c = github.comment(url)
        self.assertEqual(c, github.Comment(url=url, login="mallory", author_type="User", node_id="IC_kw1",
                                           text="Yes, back off.\nCap it at a minute, as the question suggests."))
        bot = fake({"api repos/o/api/pulls/12/reviews/7": {
            "html_url": "https://github.com/o/api/pull/12#pullrequestreview-7", "body": None,
            "user": {"login": "x[bot]", "type": "Bot"}, "node_id": "PRR_1"}})
        with mock.patch.object(github, "run_gh", bot):
            r = github.comment("https://github.com/o/api/pull/12#pullrequestreview-7")
        assert r is not None
        self.assertEqual((r.login, r.author_type, r.text), ("x[bot]", "Bot", ""))

    def test_unreadable_comment_is_none(self) -> None:
        # @scenario inquisitor: A linked comment the script cannot read is not logged
        gh = fake({"api repos/o/api/pulls/comments/55": {
            "html_url": "https://github.com/o/api/pull/99#discussion_r55", "body": "x",
            "user": {"login": "a", "type": "User"}, "node_id": "n"}})
        with mock.patch.object(github, "run_gh", gh):
            self.assertIsNone(github.comment("https://github.com/o/api/pull/12#discussion_r55"))
            self.assertIsNone(github.comment("https://github.com/o/api/pull/12#issuecomment-1"))
            self.assertIsNone(github.comment("https://discord.com/channels/1/2/3"))
            self.assertIsNone(github.comment("https://github.com/o/r/pull/3?x=../"))
        self.assertEqual(len(gh.calls), 2)
        for user in (None, {"type": "User"}):
            ghost = fake({"api repos/o/api/issues/comments/1": {
                "html_url": "https://github.com/o/api/pull/12#issuecomment-1", "body": "x",
                "user": user, "node_id": "n"}})
            with mock.patch.object(github, "run_gh", ghost):
                self.assertIsNone(github.comment("https://github.com/o/api/pull/12#issuecomment-1"))


class Candidates(unittest.TestCase):
    def test_last_commit_author(self) -> None:
        # @scenario inquisitor: The last commit's author is tagged last
        gh = fake({"api repos/o/api/commits?path=docs/a%20b.md&per_page=1":
                   [{"author": {"login": "carol", "type": "User"}}],
                   "api repos/o/api/commits?path=x.md&per_page=1": [{"author": None}],
                   "api repos/o/api/commits?path=new.md&per_page=1": [],
                   "api repos/o/api/commits?path=odd.md&per_page=1": {"message": "x"}})
        with mock.patch.object(github, "run_gh", gh):
            self.assertEqual(github.last_commit_author("o/api", "docs/a b.md"), "carol")
            self.assertIsNone(github.last_commit_author("o/api", "x.md"))
            self.assertIsNone(github.last_commit_author("o/api", "new.md"))
            self.assertIsNone(github.last_commit_author("o/api", "odd.md"))

    def test_approver_of_pull_request(self) -> None:
        # @scenario inquisitor: The approver of the earlier decision is tagged
        reviews = {"data": {"repository": {"pullRequest": {"reviews": {"nodes": [
            {"author": {"__typename": "User", "login": "dana"}}]}}}}}
        gh = fake({"api graphql": reviews})
        with mock.patch.object(github, "run_gh", gh):
            self.assertEqual(github.decision_approver("o/api", "https://github.com/o/api/pull/3"), "dana")
        call = gh.calls[0]
        self.assertEqual(call[call.index("number=3") - 1], "-F")
        self.assertEqual(call[call.index("owner=o") - 1], "-f")

    def test_blame_approver(self) -> None:
        # @scenario inquisitor: The approver of the earlier decision is tagged
        def commit(date: str, merged: bool, login: str | None) -> dict[str, Any]:
            nodes = [{"author": {"__typename": "User", "login": login}}] if login else []
            return {"committedDate": date, "associatedPullRequests": {"nodes": [
                {"merged": merged, "reviews": {"nodes": nodes}}]}}
        ranges = [{"startingLine": 1, "endingLine": 5, "commit": commit("2026-01-01T00:00:00Z", True, "old")},
                  {"startingLine": 6, "endingLine": 9, "commit": commit("2026-03-01T00:00:00Z", True, "new")},
                  {"startingLine": 2, "endingLine": None, "commit": commit("2026-05-01T00:00:00Z", True, "odd")}]
        data = {"data": {"repository": {"object": {"blame": {"ranges": ranges}}}}}
        url = "https://github.com/o/api/blob/main/openspec/specs/retry/spec.md"
        with mock.patch.object(github, "run_gh", fake({"api graphql": data})):
            self.assertEqual(github.decision_approver("o/api", url + "#L2-L4"), "old")
            self.assertEqual(github.decision_approver("o/api", url + "#L7"), "new")
            self.assertEqual(github.decision_approver("o/api", url + "#L5"), "old")
            self.assertEqual(github.decision_approver("o/api", url), "new")

    def test_no_known_approver_is_skipped(self) -> None:
        # @scenario inquisitor: A decision with no known approver is skipped
        gh = fake({"api graphql": {"data": {"repository": {"pullRequest": {"reviews": {"nodes": []}}}}}})
        with mock.patch.object(github, "run_gh", gh):
            self.assertIsNone(github.decision_approver("o/api", "https://github.com/o/api/pull/3"))
            self.assertIsNone(github.decision_approver("o/api", "https://github.com/o/api/issues/4"))
        self.assertEqual(len(gh.calls), 1)
        bot = fake({"api graphql": {"data": {"repository": {"pullRequest": {"reviews": {"nodes": [
            {"author": {"__typename": "Bot", "login": "igor-x"}}]}}}}}})
        with mock.patch.object(github, "run_gh", bot):
            self.assertEqual(github.decision_approver("o/api", "https://github.com/o/api/pull/3"), "igor-x[bot]")


if __name__ == "__main__":
    unittest.main()


class MarkdownLineLinks(unittest.TestCase):
    def test_plain_view_line_link(self) -> None:
        # @scenario inquisitor: The approver of the earlier decision is tagged
        ranges = [{"startingLine": 1, "endingLine": 30, "commit": {
            "committedDate": "2026-01-01T00:00:00Z", "associatedPullRequests": {"nodes": [
                {"merged": True, "reviews": {"nodes": [{"author": {"__typename": "User", "login": "alice"}}]}}]}}}]
        data = {"data": {"repository": {"object": {"blame": {"ranges": ranges}}}}}
        with mock.patch.object(github, "run_gh", fake({"api graphql": data})):
            self.assertEqual(github.decision_approver(
                "o/api", "https://github.com/o/api/blob/abc/docs/design.md?plain=1#L10-L20"), "alice")

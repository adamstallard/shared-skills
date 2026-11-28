"""Tests for tagging: whom a posted question tags."""

import contextlib
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import config
import tagging
from common import Refused, verdicts_dir
from contracts import TagResult, VerdictRecord
from qtext import UNTAGGED_LINE

HASH = "e" * 64


class Tag(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        os.chmod(self.dir, 0o700)
        self.access: dict[tuple[str, str], bool | None] = {}
        self.reviewers: dict[str, list[str]] = {}
        self.approver: str | None = None
        self.authors: dict[str, str | None] = {}
        self.called: list[str] = []
        self.configured: str | None = "alice"
        self.gh_user = "alice"

        def write_access(repository: str, login: str) -> bool | None:
            self.called.append(login)
            return self.access.get((repository, login))

        def approver(repository: str, decision: str) -> str | None:
            return self.approver

        def author(repository: str, path: str) -> str | None:
            return self.authors.get(path)

        def session_login(configured: str | None) -> str | None:
            return configured if configured == self.gh_user else None

        def load() -> config.Config:
            return config.Config(login=self.configured)

        def reviewers(repository: str) -> list[str] | None:
            return self.reviewers.get(repository)

        patches: list[Any] = [
            mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.dir / "state"),
                                         "CLAUDE_CODE_SESSION_ATTENDED": "1"}),
            mock.patch("github.write_access", side_effect=write_access),
            mock.patch("github.decision_approver", side_effect=approver),
            mock.patch("github.last_commit_author", side_effect=author),
            mock.patch("github.session_login", side_effect=session_login),
            mock.patch("config.load", side_effect=load),
            mock.patch("tagging.reviewers", side_effect=reviewers),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self) -> None:
        subprocess.run(["rm", "-rf", str(self.dir)], check=True)

    def record(self, **extra: Any) -> None:
        rec: dict[str, Any] = {"version": 1, "hash": HASH, "verdict": "ask", "time": time.time(),
                               "kind": "post", "field": {"recommended": "a", "changes": "b"},
                               "concerns": {"repository": "o/api"}, **extra}
        verdicts_dir().mkdir(parents=True, mode=0o700, exist_ok=True)
        (verdicts_dir() / f"{HASH}.json").write_text(json.dumps(rec))

    def tag(self, identity: str | None = None) -> TagResult:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(tagging.run(tagging.TagArgs(hash=HASH, identity=identity)), 0)
        return json.loads(out.getvalue())

    def test_approver_tagged(self) -> None:
        # @scenario inquisitor: The approver of the earlier decision is tagged
        self.record(related="https://github.com/o/api/pull/3")
        self.approver = "carol"
        self.access[("o/api", "carol")] = True
        self.reviewers["o/api"] = ["dave"]
        self.access[("o/api", "dave")] = True
        self.assertEqual(self.tag(), {"version": 1, "action": "tag", "line": "@carol"})

    def test_reviewer_next(self) -> None:
        # @scenario inquisitor: A listed reviewer is tagged next
        # @scenario inquisitor: A decision with no known approver is skipped
        self.record(related="https://github.com/o/api/issues/4")
        self.reviewers["o/api"] = ["erin", "dave"]
        self.access[("o/api", "dave")] = True
        self.assertEqual(self.tag()["line"], "@dave")
        self.assertEqual(self.called[:2], ["erin", "dave"])

    def test_collective_reads_lore_reviewers(self) -> None:
        # @scenario inquisitor: An organization's question tags a reviewer from lore
        self.record(concerns={"lore": "o/lore", "asked_from": "o/api"})
        self.reviewers["o/api"] = ["dave"]
        self.access[("o/api", "dave")] = True
        self.reviewers["o/lore"] = ["lena"]
        self.access[("o/lore", "lena")] = True
        self.assertEqual(self.tag()["line"], "@lena")

    def test_last_commit_author_last(self) -> None:
        # @scenario inquisitor: The last commit's author is tagged last
        self.record(files=["src/retry.py"])
        self.authors["src/retry.py"] = "frank"
        self.access[("o/api", "frank")] = True
        self.assertEqual(self.tag()["line"], "@frank")

    def test_malformed_login_skipped(self) -> None:
        # @scenario inquisitor: A malformed login is skipped
        self.record()
        self.reviewers["o/api"] = ["../orgs/x", "dave"]
        self.access[("o/api", "dave")] = True
        self.assertEqual(self.tag()["line"], "@dave")
        self.assertNotIn("../orgs/x", self.called)

    def test_configured_login_tagged_through_app(self) -> None:
        # @scenario inquisitor: The configured login is tagged when no candidate can decide
        # @scenario inquisitor: A post through github-app's gh tags the configured login
        self.record()
        self.access[("o/api", "alice")] = True
        self.assertEqual(self.tag(identity="bot"), {"version": 1, "action": "tag", "line": "@alice"})
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ATTENDED": "0"}):
            self.assertEqual(self.tag(identity="bot")["line"], "@alice")

    def test_tag_for_an_app_post_records_the_identity(self) -> None:
        # @scenario inquisitor: A tag made for an App's post blocks a plain gh post
        # The record holds the identity only while the configured login is tagged for an App's
        # post. A later run of `tag` that tags a reviewer with write access instead, or one with
        # no --identity (here ending in the picker), removes it from the record.
        self.record()
        path = verdicts_dir() / f"{HASH}.json"

        def recorded() -> VerdictRecord:
            return json.loads(path.read_text())

        self.access[("o/api", "alice")] = True
        self.tag(identity="bot")
        self.assertEqual(recorded().get("identity"), "bot")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual({k: v for k, v in recorded().items() if k != "identity"}["verdict"], "ask")
        self.assertEqual(self.tag()["action"], "picker")
        self.assertNotIn("identity", recorded())
        self.tag(identity="bot")
        self.reviewers["o/api"] = ["dave"]
        self.access[("o/api", "dave")] = True
        self.assertEqual(self.tag(identity="bot")["line"], "@dave")
        self.assertNotIn("identity", recorded())

    def test_post_as_login_asks_through_picker(self) -> None:
        # @scenario inquisitor: A post by the configured login asks through the picker
        # @scenario inquisitor: github-app's environment alone does not make a post an App's
        self.record()
        self.access[("o/api", "alice")] = True
        with mock.patch.dict(os.environ, {"GITHUB_APP_ACT_AS": "bot", "GIT_AUTHOR_NAME": "x[bot]"}):
            self.assertEqual(self.tag(), {"version": 1, "action": "picker", "line": None})

    def test_no_configured_login_asks_through_picker(self) -> None:
        # @scenario inquisitor: No configured login means asking through the picker
        self.record()
        self.configured = None
        self.assertEqual(self.tag(identity="bot")["action"], "picker")
        self.configured, self.gh_user = "maintainer", "contributor"
        self.assertEqual(self.tag(identity="bot")["action"], "picker")

    def test_headless_does_not_tag_own_login(self) -> None:
        # @scenario inquisitor: A headless session does not tag its own login
        self.record()
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ATTENDED": "0"}):
            self.configured = None
            self.assertEqual(self.tag(identity="bot"), {"version": 1, "action": "untagged",
                                                        "line": UNTAGGED_LINE})
            self.configured = "alice"
            self.access[("o/api", "alice")] = True
            self.assertEqual(self.tag()["action"], "untagged")

    def test_no_one_can_decide(self) -> None:
        # @scenario inquisitor: A question no one can decide is posted untagged
        self.record()
        self.access[("o/api", "alice")] = False
        for attended in ("1", "0"):
            with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ATTENDED": attended}):
                self.assertEqual(self.tag(identity="bot"), {"version": 1, "action": "untagged",
                                                            "line": UNTAGGED_LINE})

    def test_refusals(self) -> None:
        # @scenario inquisitor: A post holding a question with a category is blocked
        # (tag refuses such a question, saying to ask directly or in the advisory)
        with self.assertRaises(Refused):
            self.tag()
        self.record(verdict="deferred")
        with self.assertRaises(Refused):
            self.tag()
        cat: VerdictRecord = {"version": 1, "hash": HASH, "verdict": "ask", "time": time.time(),
                              "category": "vulnerability"}
        (verdicts_dir() / f"{HASH}.json").write_text(json.dumps(cat))
        with self.assertRaises(Refused) as cm:
            self.tag()
        self.assertIn("security advisory", str(cm.exception))
        with self.assertRaises(Refused):
            tagging.run(tagging.TagArgs(hash="nothex"))
        self.record()
        with self.assertRaises(Refused):
            tagging.run(tagging.TagArgs(hash=HASH, identity="../bot"))

    def test_damaged_record_is_named(self) -> None:
        # The refusal names the record file that is not JSON, for whoever reads it to remove:
        # read_records never deletes such a file, since its age cannot be read.
        verdicts_dir().mkdir(parents=True, mode=0o700, exist_ok=True)
        path = verdicts_dir() / f"{HASH}.json"
        path.write_text("{trunc")
        with self.assertRaises(Refused) as cm:
            self.tag()
        self.assertIn(str(path), str(cm.exception))


if __name__ == "__main__":
    unittest.main()

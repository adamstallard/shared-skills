"""Tests for cite: the `cite` command, with the questions branch faked."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest import mock

import branches
import cite
import github
import log_command
from common import Refused
from formats import CitationFile, parse


def fetched(clone: Path, repository: str) -> bool:
    return True


class Cite(unittest.TestCase):
    def setUp(self) -> None:
        self.pushed: list[dict[str, Any]] = []
        self.result = branches.PushResult(pushed=True)
        self.visibility_calls: list[str] = []
        patches = [
            mock.patch.object(branches, "fetch", fetched),
            mock.patch.object(branches, "push_file", self.push_file),
            mock.patch.object(github, "visibility", self.visibility),
            mock.patch.object(log_command, "today", lambda: "2026-10-20"),
            mock.patch.object(log_command, "random_hex", lambda: "3f9a1c"),
            mock.patch.dict(os.environ, {"XDG_STATE_HOME": tempfile.mkdtemp()}),
        ]
        os.environ.pop("IGOR_RUN", None)
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def push_file(self, clone: Path, repository: str, path: str, content: str, message: str,
                  as_inquisitor: bool, service: bool) -> branches.PushResult:
        self.pushed.append({"repository": repository, "path": path, "content": content,
                            "message": message, "as_inquisitor": as_inquisitor,
                            "service": service})
        return self.result

    def visibility(self, repository: str) -> github.Visibility | None:
        self.visibility_calls.append(repository)
        return "public"

    def cite(self, **args: bool) -> dict[str, Any]:
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cite.run(cite.CiteArgs(lore="o/lore", entry="retry-backoff",
                                                    **args)), 0)
        return json.loads(out.getvalue())

    def test_citation_file_and_commit(self) -> None:
        # @scenario inquisitor: Only the citation file names the lore entry
        # @scenario inquisitor: A citation from a session outside an Igor's run holds no run id
        # @scenario inquisitor: A citation's commit names no person
        # @scenario inquisitor: A question about a private repository cites a public lore entry
        result = self.cite()
        self.assertEqual(result, {"version": 1, "status": "pushed",
                                  "path": "citations/2026-10-20-3f9a1c"})
        push = self.pushed[0]
        self.assertEqual(push["repository"], "o/lore")
        self.assertEqual(push["content"], 'entry: "retry-backoff"\ndate: "2026-10-20"\n')
        self.assertEqual(push["message"], "inquisitor: log citations/2026-10-20-3f9a1c")
        self.assertTrue(push["as_inquisitor"])
        self.assertEqual(parse(push["path"], push["content"], True),
                         CitationFile(name="2026-10-20-3f9a1c", entry="retry-backoff",
                                      date="2026-10-20"))
        self.assertEqual(self.visibility_calls, [])

    def test_igor_run_pushes_nothing(self) -> None:
        # @scenario inquisitor: An agent pushes no citation during an Igor's run
        with mock.patch.dict(os.environ, {"IGOR_RUN": "worker"}):
            result = self.cite()
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(self.pushed, [])

    def test_service_push_failure_keeps_nothing(self) -> None:
        # @scenario inquisitor: A file the answer service cannot push leaves no pending copy
        self.result = branches.PushResult(pushed=False, why="no network")
        result = self.cite(service=True)
        self.assertEqual(result, {"version": 1, "status": "failed", "path": None,
                                  "why": "no network"})
        self.assertTrue(self.pushed[0]["service"])

    def test_malformed_arguments_are_refused(self) -> None:
        # @scenario inquisitor: Only the citation file names the lore entry
        # --entry is the id the citation names; one off igor's id rule is never written.
        for lore, entry in (("o/../x", "retry-backoff"), ("o/lore", "Bad_Id")):
            with self.assertRaises(Refused):
                cite.run(cite.CiteArgs(lore=lore, entry=entry))
        self.assertEqual(self.pushed, [])


if __name__ == "__main__":
    unittest.main()

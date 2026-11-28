"""Tests for lore: the `lore` command against a fake GitHub (run_gh), and the
entry rules checked against igor's lore store at lore.IGOR_COMMIT."""

import base64
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest import mock

import branches
import config
import github
import lore
from common import Refused
from formats import LogFile, MissFile, render

# The rules of igor's src/entry.ts at lore.IGOR_COMMIT, as written there.
# igor PRs #216 and #202, open on 2026-11-27, change neither src/entry.ts nor
# the lore-store spec, so the pin is the head of igor's main on that day.
IGOR_ENTRY_TS = r"""
export const STATUSES = ['provisional', 'active', 'deprecated'] as const
export const DERIVED_FIELDS = ['support'] as const
const SCOPE_PATTERN = /^(global|role:[a-z0-9][a-z0-9-]*|project:[a-z0-9][a-z0-9-]*)$/
const ID_PATTERN = /^[a-z0-9][a-z0-9-]*$/
"""
# igor's lore-store spec, *Frontmatter conforms to a validated schema*, and
# *Entry files are markdown with frontmatter, named by id*.
IGOR_REQUIRED = "`id`, `claim`, `scope`, `status`, `conditions`, `provenance`, and `supersedes`"
IGOR_PATH = "<destination>/entries/"

FRONTMATTER: dict[str, Any] = {
    "claim": "Retries back off exponentially, capped at a minute.",
    "scope": "global",
    "conditions": {"prose": "a client retries a failed request"},
    "provenance": [{"author": "alice", "at": "2026-10-21"}],
}


class PinnedToIgor(unittest.TestCase):
    def test_rules_match_igor_commit(self) -> None:
        # @scenario inquisitor: A proposed entry goes in entries/
        # @scenario inquisitor: An id outside igor's id rule is refused
        self.assertEqual(lore.IGOR_COMMIT, "7d969cd6ab7820e143c2802a9ead44b3a91332b0")
        m = re.search(r"const ID_PATTERN = /(.+)/\n", IGOR_ENTRY_TS)
        assert m
        self.assertEqual(lore.ID_PATTERN, m.group(1))
        m = re.search(r"const SCOPE_PATTERN = /(.+)/\n", IGOR_ENTRY_TS)
        assert m
        self.assertEqual(lore.SCOPE_PATTERN, m.group(1))
        m = re.search(r"STATUSES = \[(.+)\]", IGOR_ENTRY_TS)
        assert m
        self.assertEqual(lore.STATUSES, tuple(re.findall(r"'([a-z]+)'", m.group(1))))
        m = re.search(r"DERIVED_FIELDS = \[(.+)\]", IGOR_ENTRY_TS)
        assert m
        self.assertEqual(lore.DERIVED_FIELDS, tuple(re.findall(r"'([a-z]+)'", m.group(1))))
        self.assertEqual(lore.REQUIRED_FIELDS, tuple(re.findall(r"`([a-z]+)`", IGOR_REQUIRED)))
        self.assertTrue(IGOR_PATH.endswith(lore.ENTRIES_DIR + "/"))

    def test_schema_errors(self) -> None:
        # @scenario inquisitor: A proposed entry goes in entries/
        good: dict[str, Any] = {**FRONTMATTER, "id": "x", "status": "provisional", "supersedes": []}
        self.assertEqual(lore.entry_errors(good), [])
        self.assertIn("reviewed: is required when status is active",
                      lore.entry_errors({**good, "status": "active"}))
        self.assertIn("scope: must be global, role:<name>, or project:<name>",
                      lore.entry_errors({**good, "scope": "team:frontend"}))
        self.assertIn("provenance: must be a non-empty array",
                      lore.entry_errors({**good, "provenance": []}))
        self.assertEqual(lore.entry_errors(
            {**good, "conditions": {"prose": "p", "paths": ["src/"]}}), [])
        for paths in ([], [""]):
            self.assertIn("conditions.paths: must be a non-empty array of non-empty strings",
                          lore.entry_errors({**good, "conditions": {"prose": "p", "paths": paths}}))
        self.assertEqual(lore.entry_errors({**good, "reviewed": {"by": "b", "at": "2026-01-01"}}), [])
        self.assertIn("reviewed.by: is required",
                      lore.entry_errors({**good, "reviewed": {"by": "", "at": "2026-01-01"}}))
        self.assertIn("reviewed.at: must be an ISO date (YYYY-MM-DD)",
                      lore.entry_errors({**good, "reviewed": {"by": "b", "at": "x"}}))
        self.assertIn("support: is derived from provenance and must not be stored",
                      lore.entry_errors({**good, "support": 3}))


class Command(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        os.chmod(self.tmp, 0o700)
        # A fake GitHub: the lore repository's default branch holds these.
        self.on_main = {"entries/taken.md", "rejected/old-idea.md"}
        self.refs: set[str] = set()
        self.commits: dict[str, str] = {}
        self.writes: list[list[str]] = []
        self.failing: set[str] = set()
        self.open_pulls: list[dict[str, str]] = []
        self.gh: list[list[str]] = []
        self.cfg = config.Config(login="alice", lore=(
            config.LoreRepo(path=str(self.tmp / "lore"), owners=("o",), repository="o/lore"),))
        self.vis: dict[str, github.Visibility | None] = {
            "o/api": "private", "o/web": "public", "o/lore": "public"}
        self.branch: dict[str, list[branches.BranchFile]] = {}
        patches = [
            mock.patch.object(config, "load", self.load),
            mock.patch.object(github, "visibility", self.visibility),
            mock.patch.object(branches, "list_files", self.list_files),
            mock.patch.object(lore, "run_gh", self.run_gh),
        ]
        os.environ.pop("IGOR_RUN", None)
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def load(self) -> config.Config:
        return self.cfg

    def visibility(self, repository: str) -> github.Visibility | None:
        return self.vis.get(repository)

    def list_files(self, repository: str) -> list[branches.BranchFile]:
        return self.branch.get(repository, [])

    def run_gh(self, args: list[str]) -> tuple[int, str, str]:
        self.gh.append(args)
        sent: dict[str, str] = {}
        if "--input" in args:
            sent = json.loads(Path(args[args.index("--input") + 1]).read_text(encoding="utf-8"))
        method = args[args.index("-X") + 1] if "-X" in args else "GET"
        path = next(a for a in args[1:] if a.startswith("repos/"))
        if method != "GET":
            self.writes.append(args)
        if f"{method} {path}" in self.failing:
            return 1, "", "gh: Server Error (HTTP 502)"
        if path == "repos/o/lore":
            return 0, json.dumps({"default_branch": "main"}), ""
        if path == "repos/o/lore/git/ref/heads/main":
            return 0, json.dumps({"object": {"sha": "b" * 40}}), ""
        if path.startswith("repos/o/lore/contents/") and method == "GET":
            wanted = path.removeprefix("repos/o/lore/contents/").split("?")[0]
            return (0, "{}", "") if wanted in self.on_main else (1, "", "gh: Not Found (HTTP 404)")
        if path.startswith("repos/o/lore/pulls?"):
            return 0, json.dumps(self.open_pulls), ""
        if path.startswith("repos/o/lore/git/refs/heads/") and method == "PATCH":
            self.reset = sent
            return 0, "{}", ""
        if path == "repos/o/lore/git/refs":
            if sent["ref"] in self.refs:
                return 1, "", "gh: Reference already exists (HTTP 422)"
            self.refs.add(sent["ref"])
            return 0, "{}", ""
        if path.startswith("repos/o/lore/contents/"):
            entry = path.removeprefix("repos/o/lore/contents/")
            self.commits[f"{sent['branch']}:{entry}"] = base64.b64decode(sent["content"]).decode()
            return 0, "{}", ""
        if path == "repos/o/lore/pulls":
            self.pull = sent
            return 0, json.dumps({"html_url": "https://github.com/o/lore/pull/9"}), ""
        return 1, "", "unexpected call"

    def input(self, **data: Any) -> str:
        full = {"version": 1, "kind": "new", "lore": "o/lore", "id": "retry-backoff",
                "frontmatter": FRONTMATTER, "body": "Back off on 503 and 429.",
                "source": {"repository": "o/web"}, **data}
        path = self.tmp / "in.json"
        path.write_text(json.dumps(full), encoding="utf-8")
        os.chmod(path, 0o600)
        return str(path)

    def propose(self, confirm: bool = False, **data: Any) -> dict[str, Any]:
        out = io.StringIO()
        with redirect_stdout(out):
            lore.run(lore.LoreArgs(input=self.input(**data), confirm_visible=confirm))
        return json.loads(out.getvalue())

    def refused(self, says: str, confirm: bool = False, **data: Any) -> None:
        with self.assertRaises(Refused) as caught:
            lore.run(lore.LoreArgs(input=self.input(**data), confirm_visible=confirm))
        self.assertIn(says, str(caught.exception))
        self.assertEqual(self.writes, [])

    def pushed_entry(self) -> str:
        return self.commits["inquisitor/lore-retry-backoff:entries/retry-backoff.md"]

    def test_new_entry_opens_pull_request(self) -> None:
        # @scenario inquisitor: A general answer becomes a lore pull request
        # @scenario inquisitor: A proposed entry goes in entries/
        result = self.propose()
        self.assertEqual(result, {"version": 1, "url": "https://github.com/o/lore/pull/9",
                                  "path": "entries/retry-backoff.md"})
        entry = self.pushed_entry()
        self.assertTrue(entry.startswith('---\nid: "retry-backoff"\nclaim: "Retries back off'))
        self.assertIn('status: "provisional"\n', entry)
        self.assertIn("supersedes: []\n", entry)
        self.assertIn('provenance: [{"author": "alice", "at": "2026-10-21"}]\n', entry)
        self.assertIn('conditions: {"prose": "a client retries a failed request"}\n', entry)
        self.assertTrue(entry.endswith("---\nBack off on 503 and 429.\n"))
        self.assertEqual((self.pull["head"], self.pull["base"]),
                         ("inquisitor/lore-retry-backoff", "main"))
        self.assertTrue(self.pull["title"].startswith("LORE: Retries back off"))
        self.assertEqual(self.refs, {"refs/heads/inquisitor/lore-retry-backoff"})

    def test_secret_in_the_entry_is_refused(self) -> None:
        # @scenario inquisitor: A log file holding a secret is not written
        # The spec's credential rule names log files; lore applies the same scan to an entry.
        self.refused("credential patterns",
                     frontmatter={**FRONTMATTER, "claim": "Use the token\nghp_" + "A" * 36})

    def test_text_utf8_cannot_encode_is_refused(self) -> None:
        # @scenario inquisitor: A proposed entry goes in entries/
        # igor reads entries as UTF-8 text, so one that cannot be written in it never goes in entries/.
        self.refused("UTF-8", frontmatter={**FRONTMATTER, "claim": "a\ud800b"})

    def test_frontmatter_cannot_smuggle_keys_or_raw_controls(self) -> None:
        # @scenario inquisitor: A proposed entry goes in entries/
        # An entry goes in entries/ only with frontmatter igor reads: no smuggled key, no raw
        # control character.
        self.refused("frontmatter key", frontmatter={**FRONTMATTER, "note: x\nstatus": "active"})
        self.refused("frontmatter key", frontmatter={**FRONTMATTER, "extra": {"True": 1}})
        self.refused("number JSON cannot write", frontmatter={**FRONTMATTER, "extra": float("nan")})
        self.propose(frontmatter={**FRONTMATTER, "claim": "Retries\u0085 back\x7f off\x9b."})
        entry = self.pushed_entry()
        self.assertFalse(any(c in entry for c in "\x7f\x85\x9b"))
        self.assertIn('claim: "Retries\\u0085 back\\u007f off\\u009b."', entry)

    def test_control_character_in_claim_is_refused_before_any_push(self) -> None:
        # @scenario inquisitor: A general answer becomes a lore pull request
        # The pull request is opened only for an entry with no NUL, refused before any branch exists.
        self.refused("control character", frontmatter={**FRONTMATTER, "claim": "Back off\u0000now"})
        self.assertEqual(self.refs, set())

    def test_null_optional_fields_are_refused_as_igor_does(self) -> None:
        # @scenario inquisitor: A proposed entry goes in entries/
        # igor refuses a null reviewed or paths, so such an entry never goes in entries/.
        self.refused("reviewed: must be an object", frontmatter={**FRONTMATTER, "reviewed": None})
        self.refused("conditions.paths", frontmatter={
            **FRONTMATTER, "conditions": {"prose": "p", "paths": None}})

    def test_a_failed_proposal_can_be_retried(self) -> None:
        # @scenario inquisitor: A general answer becomes a lore pull request
        # A failed attempt must not stop the answer becoming a pull request on the next try.
        self.failing.add("PUT repos/o/lore/contents/entries/retry-backoff.md")
        with self.assertRaises(Refused):
            lore.run(lore.LoreArgs(input=self.input()))
        self.failing.clear()
        self.assertEqual(self.propose()["url"], "https://github.com/o/lore/pull/9")
        self.open_pulls = [{"html_url": "https://github.com/o/lore/pull/9"}]
        with self.assertRaises(Refused) as caught:
            lore.run(lore.LoreArgs(input=self.input()))
        self.assertIn("pull/9", str(caught.exception))

    def test_body_line_ends_are_lf(self) -> None:
        # @scenario inquisitor: A proposed entry goes in entries/
        # The entry in entries/ has LF line ends, whatever the body was given with.
        self.propose(body="Back off.\r\nOn 503.\rAnd 429.")
        self.assertTrue(self.pushed_entry().endswith("---\nBack off.\nOn 503.\nAnd 429.\n"))

    def test_unconfigured_lore_repository_is_told_not_proposed(self) -> None:
        # @scenario inquisitor: No lore repository is configured
        self.cfg = config.Config(login="alice")
        self.refused("no configured lore repository")

    def test_failed_github_steps_refuse(self) -> None:
        # @scenario inquisitor: A general answer becomes a lore pull request
        # When GitHub refuses a step, no half-made pull request is opened.
        for step in ("GET repos/o/lore", "POST repos/o/lore/git/refs"):
            self.failing = {step}
            with self.assertRaises(Refused):
                lore.run(lore.LoreArgs(input=self.input()))
            self.assertFalse(any("repos/o/lore/pulls" in a for w in self.writes for a in w))

    def test_a_key_igor_cannot_parse_is_refused(self) -> None:
        # @scenario inquisitor: A proposed entry goes in entries/
        # igor's yaml refuses a key over 1024 characters, so such an entry never goes in entries/.
        self.refused("frontmatter key", frontmatter={**FRONTMATTER, "k" * 1100: 1})

    def test_id_outside_igor_rule_is_refused(self) -> None:
        # @scenario inquisitor: An id outside igor's id rule is refused
        self.refused("igor's id rule", id="Retry_Policy")
        self.refused("igor's id rule", id="../x")

    def test_taken_and_rejected_ids(self) -> None:
        # @scenario inquisitor: An id an entry already holds is not reused
        # @scenario inquisitor: A rejected candidate is not proposed again
        self.refused("an entry there holds it", id="taken")
        self.refused("rejected candidate", id="old-idea")

    def test_unknown_lore_visibility_counts_as_public(self) -> None:
        # @scenario inquisitor: A lore repository of unknown visibility counts as public
        # @scenario inquisitor: With no person in the session, a private answer never reaches a public lore repository
        # No confirmation option is what a session with no person in it gives.
        self.vis["o/lore"] = None
        self.refused("more visible than o/api", source={"repository": "o/api"})

    def test_confirmed_entry_holds_no_link_into_source(self) -> None:
        # @scenario inquisitor: A confirmed entry is proposed with generalized text
        fm = {**FRONTMATTER, "provenance": [{"author": "alice", "at": "2026-10-21",
                                             "url": "https://github.com/o/api/issues/7"}]}
        self.refused("no provenance link", confirm=True, source={"repository": "o/api"},
                     frontmatter=fm)
        self.propose(confirm=True, source={"repository": "o/api"})
        self.assertIn("retry-backoff", self.pushed_entry())

    def test_promotion_of_more_private_file_needs_confirmation(self) -> None:
        # @scenario inquisitor: An unconfirmed promotion of a more private file opens nothing
        # @scenario inquisitor: A logged answer is promoted to lore
        name = "2026-10-21-should-retries-back-off-a1b2c3.md"
        text = render(LogFile(name=name, asked="2026-10-21", question="Should retries back off?",
                              repository="o/web", asked_from="o/api"))
        text = text.replace("---\n## Question", 'answered_by: "alice"\nauthority: "decision"\n'
                            f'recorded_in: "questions/{name}"\n---\n## Question') + "## Answer\n> Yes\n"
        self.branch["o/web"] = [branches.BranchFile(path="questions/" + name, content=text,
                                                    added_by="c" * 40)]
        source = {"file": {"repository": "o/web", "path": "questions/" + name}}
        self.refused("more visible than o/web:questions/" + name, kind="promotion", source=source)
        self.propose(confirm=True, kind="promotion", source=source)
        self.assertEqual(len(self.refs), 1)

    def test_lesson_from_private_misses_needs_confirmation(self) -> None:
        # @scenario inquisitor: A team lesson from a private repository's misses reaches a public lore repository only once confirmed
        # @scenario inquisitor: A team lesson goes to its lore repository by pull request
        digest = "d" * 64
        miss = render(MissFile(hash=digest, asked="2026-10-20", filter="3", said="x",
                               question="Q?", repository="o/api", asked_from="o/api"))
        self.branch["o/api"] = [branches.BranchFile(path=f"misses/{digest}.md", content=miss,
                                                    added_by="c" * 40)]
        source = {"misses": [{"repository": "o/api", "path": f"misses/{digest}.md"}]}
        self.refused("more visible", kind="lesson", source=source)
        public = "e" * 64
        self.branch["o/web"] = [branches.BranchFile(path=f"misses/{public}.md", added_by="c" * 40,
                                                    content=miss.replace("o/api", "o/web"))]
        self.vis["o/lore"] = "internal"
        both = {"misses": [{"repository": "o/web", "path": f"misses/{public}.md"},
                           *source["misses"]]}
        self.refused("more visible than o/api", kind="lesson", source=both)
        self.vis["o/lore"] = "private"
        self.propose(kind="lesson", source=source)
        self.assertEqual(len(self.refs), 1)


if __name__ == "__main__":
    unittest.main()

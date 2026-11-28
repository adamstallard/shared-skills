"""Tests for branches: reading and pushing a questions branch through
GitHub's API, against FakeGitHub, which answers gh's calls from an
in-memory repository in the shapes GitHub gives (measured 2026-11-27 with
read-only calls: the GraphQL head, history and blob shapes, a missing
repository's NOT_FOUND error, a missing ref's 404; the write refusals are
GitHub's documented messages)."""

import base64
import datetime
import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, cast
from unittest import mock

import branch_search
import branches
from formats import CitationFile, HashOnlyMiss, LogFile, render

QUESTION = LogFile(name="2026-10-20-should-retries-back-off-3f9a1c.md", asked="2026-10-20",
                   question="Should retries back off?", repository="o/api", asked_from="o/api")
PATH = "questions/" + QUESTION.name
MISS_PATH = "misses/" + "a" * 64 + ".md"
CITATION = CitationFile(name="2026-10-20-3f9a1c", entry="retry-backoff", date="2026-10-20")
OTHER = replace(QUESTION, name="2026-10-20-other-000001.md")

NOT_FOUND = '{"message":"Not Found","documentation_url":"https://docs.github.com/rest","status":"404"}'
NOT_FAST_FORWARD = ('{"message":"Update is not a fast forward","documentation_url":'
                    '"https://docs.github.com/rest/git/refs#update-a-reference","status":"422"}')


@dataclass
class Commit:
    tree: dict[str, str]
    parents: list[str]
    message: str
    author: dict[str, str]
    committer: dict[str, str]


@dataclass
class FakeGitHub:
    """One repository per name: blobs, flat trees (path to blob id),
    commits and branch heads. calls records every gh call; fail maps a
    REST method and endpoint prefix to the error gh prints; before_ref runs
    once before the next ref change, standing in for another pusher."""

    page: int = 100
    blobs: dict[str, bytes] = field(default_factory=lambda: {})
    trees: dict[str, dict[str, str]] = field(default_factory=lambda: {})
    commits: dict[str, Commit] = field(default_factory=lambda: {})
    heads: dict[tuple[str, str], str] = field(default_factory=lambda: {})
    repos: set[str] = field(default_factory=lambda: {"o/api", "o/lore"})
    empty: set[str] = field(default_factory=lambda: set())
    calls: list[list[str]] = field(default_factory=lambda: [])
    fail: dict[str, str] = field(default_factory=lambda: {})
    before_ref: Callable[[], object] | None = None

    # -- the in-memory repository

    def _id(self, kind: str, data: str) -> str:
        return hashlib.sha1(f"{kind}\0{data}".encode()).hexdigest()

    def blob(self, content: bytes) -> str:
        sha = self._id("blob", content.decode("latin-1"))
        self.blobs[sha] = content
        return sha

    def tree(self, files: dict[str, str]) -> str:
        sha = self._id("tree", json.dumps(files, sort_keys=True))
        self.trees[sha] = dict(files)
        return sha

    def commit(self, tree: dict[str, str], parents: list[str], message: str = "m",
               author: dict[str, str] | None = None, committer: dict[str, str] | None = None) -> str:
        who = {"name": "Alice", "email": "alice@example.com", "date": "2026-10-20T12:34:56Z"}
        c = Commit(dict(tree), parents, message, author or who, committer or author or who)
        sha = self._id("commit", json.dumps([c.tree, c.parents, c.message, c.author, len(self.commits)]))
        self.commits[sha] = c
        self.tree(tree)
        return sha

    def add(self, repository: str, path: str, content: str | bytes | None) -> str:
        """Commit straight onto the questions branch, as another pusher:
        content None deletes path."""
        head = self.heads.get((repository, "questions"))
        files = dict(self.commits[head].tree) if head else {}
        if content is None:
            files.pop(path)
        else:
            files[path] = self.blob(content if isinstance(content, bytes) else content.encode())
        sha = self.commit(files, [head] if head else [], f"add {path}")
        self.heads[(repository, "questions")] = sha
        return sha

    def history(self, head: str, path: str | None) -> list[str]:
        """Commits from head, newest first; with path, only those that
        touched it."""
        out: list[str] = []
        sha: str | None = head
        while sha:
            c = self.commits[sha]
            parent = self.commits[c.parents[0]].tree if c.parents else {}
            if path is None or c.tree.get(path) != parent.get(path):
                out.append(sha)
            sha = c.parents[0] if c.parents else None
        return out

    def files_of(self, repository: str) -> dict[str, bytes]:
        head = self.heads[(repository, "questions")]
        return {p: self.blobs[b] for p, b in self.commits[head].tree.items()}

    def last(self, repository: str) -> Commit:
        return self.commits[self.heads[(repository, "questions")]]

    # -- gh

    def run_gh(self, args: list[str], stdin: str | None = None) -> tuple[int, str, str]:
        self.calls.append(args)
        assert args[0] == "api", args
        if args[1] == "graphql":
            assert args[2:] == ["--input", "-"] and stdin is not None
            sent = json.loads(stdin)
            return self.graphql(sent["query"], sent["variables"])
        method, rest = ("GET", args[1:]) if args[1] != "-X" else (args[2], args[3:])
        endpoint = rest[0]
        body = cast(dict[str, Any], json.loads(stdin)) if stdin else {}
        for key, err in self.fail.items():
            if f"{method} {endpoint}".startswith(key):
                return 1, NOT_FOUND, err
        return self.rest(method, endpoint, body)

    def _page(self, oids: list[str], first: int, after: str | None) -> dict[str, Any]:
        start = int(after.split(" ")[1]) + 1 if after else 0
        shown = oids[start:start + min(first, self.page)]
        end = start + len(shown) - 1
        return {"totalCount": len(oids),
                "pageInfo": {"hasNextPage": start + len(shown) < len(oids),
                             "endCursor": f"{oids[0] if oids else ''} {end}" if shown else None},
                "nodes": [{"oid": o} for o in shown]}

    def graphql(self, query: str, v: dict[str, str]) -> tuple[int, str, str]:
        repository = f"{v['owner']}/{v['name']}"
        if repository not in self.repos:
            msg = f"Could not resolve to a Repository with the name '{repository}'."
            return 1, json.dumps({"data": {"repository": None}, "errors": [
                {"type": "NOT_FOUND", "path": ["repository"], "message": msg}]}), f"gh: {msg}\n"
        repo: dict[str, Any]
        if "ref(qualifiedName" in query:
            head = self.heads.get((repository, v["ref"].removeprefix("refs/heads/")))
            if head is None:
                repo = {"isEmpty": repository in self.empty, "ref": None}
            else:
                h = self.history(head, None)
                tree = self.tree(self.commits[head].tree)
                repo = {"ref": {"target": {"oid": head, "tree": {"oid": tree},
                                           "history": self._page(h, 100, None)}}}
        elif "$path" in query:
            repo = {"object": {"history": self._page(self.history(v["head"], v["path"]), 100,
                                                     v["after"])}}
        elif "$after" in query:
            repo = {"object": {"history": self._page(self.history(v["head"], None), 100,
                                                     v["after"])}}
        else:
            repo = {"object": {}}
            i = 0
            while f"p{i}" in v:
                repo["object"][f"h{i}"] = self._page(self.history(v["head"], v[f"p{i}"]), 100, None)
                data = self.blobs[v[f"b{i}"]]
                try:
                    repo[f"b{i}"] = {"text": data.decode("utf-8"), "isTruncated": False}
                except UnicodeDecodeError:
                    repo[f"b{i}"] = {"text": None, "isTruncated": False}
                i += 1
        return 0, json.dumps({"data": {"repository": repo}}), ""

    def rest(self, method: str, endpoint: str, body: dict[str, Any]) -> tuple[int, str, str]:
        parts = endpoint.split("?")[0].split("/")
        repository = "/".join(parts[1:3])
        if repository not in self.repos:
            return 1, NOT_FOUND, "gh: Not Found (HTTP 404)\n"
        what = "/".join(parts[3:])
        if method == "GET" and what.startswith("git/trees/"):
            files = self.trees[parts[5]]
            entries = [{"path": p, "mode": "100644", "type": "blob", "sha": b} for p, b in files.items()]
            dirs = sorted({p.rsplit("/", 1)[0] for p in files if "/" in p})
            entries += [{"path": d, "mode": "040000", "type": "tree", "sha": "0" * 40} for d in dirs]
            return 0, json.dumps({"sha": parts[5], "tree": entries, "truncated": False}), ""
        if method == "GET" and what.startswith("git/blobs/"):
            data = self.blobs[parts[5]]
            return 0, json.dumps({"content": base64.b64encode(data).decode(), "encoding": "base64"}), ""
        if repository in self.empty and method == "POST":
            return 1, '{"message":"Git Repository is empty.","status":"409"}', \
                "gh: Git Repository is empty. (HTTP 409)\n"
        if method == "POST" and what == "git/trees":
            files = dict(self.trees[body["base_tree"]]) if "base_tree" in body else {}
            for e in body["tree"]:
                files[e["path"]] = self.blob(e["content"].encode())
            return 0, json.dumps({"sha": self.tree(files)}), ""
        if method == "POST" and what == "git/commits":
            sha = self.commit(self.trees[body["tree"]], body["parents"], body["message"],
                              body.get("author"), body.get("committer"))
            return 0, json.dumps({"sha": sha}), ""
        if what.startswith("git/refs"):
            if self.before_ref is not None:
                hook, self.before_ref = self.before_ref, None
                hook()
            if method == "POST":
                name = body["ref"].removeprefix("refs/heads/")
                if (repository, name) in self.heads:
                    return 1, '{"message":"Reference already exists"}', \
                        "gh: Reference already exists (HTTP 422)\n"
                self.heads[(repository, name)] = body["sha"]
                return 0, json.dumps({"ref": body["ref"]}), ""
            name = what.removeprefix("git/refs/heads/")
            old = self.heads.get((repository, name))
            if old is None:
                return 1, '{"message":"Reference does not exist"}', \
                    "gh: Reference does not exist (HTTP 422)\n"
            if not body["force"] and old not in self.history(body["sha"], None):
                return 1, NOT_FAST_FORWARD, "gh: Update is not a fast forward (HTTP 422)\n"
            self.heads[(repository, name)] = body["sha"]
            return 0, json.dumps({"ref": f"refs/heads/{name}"}), ""
        raise AssertionError(f"unexpected call {method} {endpoint}")


class Fake(unittest.TestCase):
    def setUp(self) -> None:
        self.gh = FakeGitHub()
        self.state = Path(tempfile.mkdtemp())
        for p in (mock.patch.object(branches, "run_gh", self.gh.run_gh),
                  mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.state)})):
            p.start()
            self.addCleanup(p.stop)

    def push(self, path: str, content: str, as_inquisitor: bool = False,
             service: bool = False, repository: str = "o/api") -> branches.PushResult:
        return branches.push_file(repository, path, content, as_inquisitor, service)


class Push(Fake):
    def test_first_question_creates_orphan_branch(self) -> None:
        # @scenario inquisitor: The first question creates the questions branch
        # @scenario inquisitor: A questions-branch commit moves no HEAD
        # (nothing but gh's API is called, so no checkout, HEAD or hook is involved)
        self.gh.heads[("o/api", "main")] = self.gh.commit({"README.md": self.gh.blob(b"hi\n")}, [])
        main = self.gh.heads[("o/api", "main")]
        self.assertEqual(self.push(PATH, render(QUESTION)), branches.PushResult(pushed=True))
        self.assertEqual(self.gh.files_of("o/api"), {PATH: render(QUESTION).encode()})
        self.assertEqual(self.gh.last("o/api").parents, [])
        self.assertEqual(self.gh.heads[("o/api", "main")], main)
        self.assertTrue(all(c[0] == "api" for c in self.gh.calls))

    def test_commit_message_has_no_trailer(self) -> None:
        # @scenario inquisitor: A log or miss file's commit carries no trailer
        self.push(PATH, render(QUESTION))
        miss = render(HashOnlyMiss(hash="a" * 64))
        self.push(MISS_PATH, miss, as_inquisitor=True, service=True)
        commits = [self.gh.commits[c] for c in self.gh.history(self.gh.heads[("o/api", "questions")], None)]
        self.assertEqual([c.message for c in commits], [f"inquisitor: log {MISS_PATH}",
                                                        f"inquisitor: log {PATH}"])
        self.assertEqual(commits[1].author["name"], "Alice")  # no author sent: GitHub records gh's login, the fake Alice

    def test_citation_commit_names_no_person(self) -> None:
        # @scenario inquisitor: A citation's commit names no person
        path = "citations/" + CITATION.name
        self.assertTrue(self.push(path, render(CITATION), as_inquisitor=True,
                                  repository="o/lore").pushed)
        c = self.gh.last("o/lore")
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        who = {"name": "inquisitor", "email": "noreply", "date": f"{today}T00:00:00Z"}
        self.assertEqual((c.author, c.committer, c.message), (who, who, f"inquisitor: log {path}"))

    def test_hash_only_miss_commit(self) -> None:
        # @scenario inquisitor: A hash-only miss file holds nothing
        # (its commit's identity; test_formats checks its empty body)
        self.assertTrue(self.push(MISS_PATH, render(HashOnlyMiss(hash="a" * 64)),
                                  as_inquisitor=True, service=True).pushed)
        self.assertEqual(self.gh.last("o/api").author["name"], "inquisitor")
        self.assertEqual(self.gh.last("o/api").committer["email"], "noreply")

    def test_taken_path_adds_nothing(self) -> None:
        # @scenario inquisitor: A retried push of a miss already on the branch pushes nothing
        # @scenario inquisitor: A file whose name the branch holds is not added
        self.gh.add("o/api", PATH, "first")
        before = self.gh.heads[("o/api", "questions")]
        self.assertEqual(self.push(PATH, render(QUESTION)),
                         branches.PushResult(pushed=False, taken=True))
        content = render(HashOnlyMiss(hash="a" * 64))
        self.push(MISS_PATH, content, as_inquisitor=True, service=True)
        middle = self.gh.heads[("o/api", "questions")]
        self.assertEqual(self.push(MISS_PATH, content, as_inquisitor=True, service=True),
                         branches.PushResult(pushed=False, taken=True))
        self.assertEqual(self.gh.heads[("o/api", "questions")], middle)
        self.assertEqual(self.gh.commits[middle].parents, [before])
        self.assertEqual(self.gh.files_of("o/api")[PATH], b"first")
        self.assertFalse(branches.pending_dir("o/api").exists())

    def test_taken_miss_pushes_nothing_even_with_pending(self) -> None:
        # @scenario inquisitor: A retried push of a miss already on the branch pushes nothing
        content = render(HashOnlyMiss(hash="a" * 64))
        self.push(MISS_PATH, content, as_inquisitor=True, service=True)
        branches._keep_pending("o/api", PATH, render(QUESTION))  # pyright: ignore[reportPrivateUsage]
        before = self.gh.heads[("o/api", "questions")]
        self.assertEqual(self.push(MISS_PATH, content, as_inquisitor=True),
                         branches.PushResult(pushed=False, taken=True))
        self.assertEqual(self.gh.heads[("o/api", "questions")], before)

    def test_moved_branch_is_retried(self) -> None:
        # @scenario inquisitor: A rejected push to the questions branch is retried
        self.push("questions/" + OTHER.name, render(OTHER))
        self.gh.before_ref = lambda: self.gh.add("o/api", "questions/2026-10-20-third-000002.md", "x")
        self.assertEqual(self.push(PATH, render(QUESTION)), branches.PushResult(pushed=True))
        self.assertEqual(sorted(self.gh.files_of("o/api")),
                         sorted(["questions/" + OTHER.name, "questions/2026-10-20-third-000002.md", PATH]))
        self.assertEqual(self.gh.last("o/api").message, f"inquisitor: log {PATH}")

    def test_branch_created_meanwhile_is_retried(self) -> None:
        # @scenario inquisitor: A rejected push to the questions branch is retried
        self.gh.before_ref = lambda: self.gh.add("o/api", "questions/" + OTHER.name, render(OTHER))
        self.assertTrue(self.push(PATH, render(QUESTION)).pushed)
        self.assertEqual(sorted(self.gh.files_of("o/api")), ["questions/" + OTHER.name, PATH])

    def test_deleted_branch_is_created_again_as_an_orphan(self) -> None:
        # @scenario inquisitor: A rejected push to the questions branch is retried
        self.push("questions/" + OTHER.name, render(OTHER))
        self.gh.before_ref = lambda: self.gh.heads.pop(("o/api", "questions"))
        self.assertEqual(self.push(PATH, render(QUESTION)), branches.PushResult(pushed=True))
        self.assertEqual(sorted(self.gh.files_of("o/api")), [PATH])
        self.assertEqual(self.gh.last("o/api").parents, [])

    def test_repository_with_no_commits_keeps_the_file_pending(self) -> None:
        # @scenario inquisitor: A repository with no commits keeps the file pending
        # (an agent's push, without the service option; the next test is the service's)
        self.gh.repos.add("o/new")
        self.gh.empty.add("o/new")
        why = "o/new has no commits: it needs a first commit before its questions can be logged"
        self.assertEqual(self.push(PATH, render(QUESTION), repository="o/new"),
                         branches.PushResult(pushed=False, pending=True, why=why))
        self.assertTrue((branches.pending_dir("o/new") / PATH).exists())
        self.assertEqual(branches.list_files("o/new"), [])

    def test_service_push_to_a_repository_with_no_commits_keeps_nothing(self) -> None:
        # @scenario inquisitor: A file the answer service cannot push leaves no pending copy
        self.gh.repos.add("o/new")
        self.gh.empty.add("o/new")
        why = "o/new has no commits: it needs a first commit before its questions can be logged"
        self.assertEqual(self.push(PATH, render(QUESTION), repository="o/new", service=True),
                         branches.PushResult(pushed=False, why=why))
        self.assertFalse(branches.pending_dir("o/new").exists())

    def test_same_path_pushed_meanwhile_is_taken(self) -> None:
        # @scenario inquisitor: A file whose name the branch holds is not added
        self.push("questions/" + OTHER.name, render(OTHER))
        self.gh.before_ref = lambda: self.gh.add("o/api", PATH, "theirs")
        self.assertEqual(self.push(PATH, render(QUESTION)),
                         branches.PushResult(pushed=False, taken=True))
        self.assertEqual(self.gh.files_of("o/api")[PATH], b"theirs")

    def test_branch_that_keeps_moving_fails(self) -> None:
        # @scenario inquisitor: A rejected push to the questions branch is retried
        self.push("questions/" + OTHER.name, render(OTHER))
        n = [0]

        def move() -> None:
            n[0] += 1
            self.gh.add("o/api", f"questions/2026-10-20-x-{n[0]:06d}.md", "x")
            self.gh.before_ref = move

        self.gh.before_ref = move
        result = self.push(PATH, render(QUESTION), service=True)
        self.assertFalse(result.pushed)
        self.assertIn("not a fast forward", result.why or "")
        self.assertEqual(n[0], branches.ATTEMPTS)

    def test_unpushable_file_kept_pending_then_pushed(self) -> None:
        # @scenario inquisitor: A file an agent cannot push is kept pending and reported
        self.gh.fail["POST repos/o/api/git/trees"] = "gh: Not Found (HTTP 404)\n"
        result = self.push(PATH, render(QUESTION))
        self.assertEqual(result, branches.PushResult(pushed=False, pending=True,
                                                     why="gh: Not Found (HTTP 404)"))
        kept = branches.pending_dir("o/api") / PATH
        self.assertEqual(kept.read_text(), render(QUESTION))
        self.assertEqual(kept.stat().st_mode & 0o777, 0o600)
        self.gh.fail.clear()
        self.assertTrue(self.push("questions/" + OTHER.name, render(OTHER)).pushed)
        commits = [self.gh.commits[c].message
                   for c in self.gh.history(self.gh.heads[("o/api", "questions")], None)]
        self.assertEqual(commits, [f"inquisitor: log questions/{OTHER.name}", f"inquisitor: log {PATH}"])
        self.assertFalse(kept.exists())

    def test_pending_citation_commits_as_inquisitor(self) -> None:
        # @scenario inquisitor: A citation's commit names no person
        cpath = "citations/" + CITATION.name
        self.gh.fail["POST repos/o/api/git/trees"] = "gh: Not Found (HTTP 404)\n"
        self.assertTrue(self.push(cpath, render(CITATION), as_inquisitor=True).pending)
        self.gh.fail.clear()
        self.assertTrue(self.push(PATH, render(QUESTION)).pushed)
        first = self.gh.commits[self.gh.last("o/api").parents[0]]
        self.assertEqual((first.message, first.author["name"]), (f"inquisitor: log {cpath}", "inquisitor"))
        self.assertEqual(self.gh.last("o/api").author["name"], "Alice")

    def test_unpushable_miss_kept_pending_unless_known_taken(self) -> None:
        # @scenario inquisitor: A file an agent cannot push is kept pending and reported
        content = render(HashOnlyMiss(hash="a" * 64))
        self.gh.fail["POST repos/o/api/git/trees"] = "gh: Not Found (HTTP 404)\n"
        self.assertTrue(self.push(MISS_PATH, content, as_inquisitor=True).pending)
        self.assertTrue((branches.pending_dir("o/api") / MISS_PATH).exists())

    def test_service_keeps_nothing_pending(self) -> None:
        # @scenario inquisitor: A file the answer service cannot push leaves no pending copy
        self.gh.fail["POST repos/o/api/git/trees"] = "gh: Not Found (HTTP 404)\n"
        result = self.push(PATH, render(QUESTION), service=True)
        self.assertEqual(result, branches.PushResult(pushed=False, why="gh: Not Found (HTTP 404)"))
        self.assertFalse(branches.pending_dir("o/api").exists())

    def test_unreadable_branch_keeps_the_file_pending(self) -> None:
        # @scenario inquisitor: A file an agent cannot push is kept pending and reported
        result = self.push(PATH, render(QUESTION), repository="o/gone")
        self.assertTrue(result.pending)
        self.assertEqual(result.why, "cannot read the questions branch of o/gone")
        self.assertFalse(any(c[1] == "-X" for c in self.gh.calls))

    def test_refuses_bad_input(self) -> None:
        # @scenario inquisitor: A malformed repository key is never sent to GitHub
        # (nothing is pushed or kept for a malformed repository or an unreadable file)
        self.assertFalse(self.push(PATH, render(QUESTION), repository="o/../x").pushed)
        self.assertFalse(self.push(PATH, "not a log file").pushed)
        self.assertEqual(self.gh.calls, [])
        self.assertFalse(branches.pending_dir("o/api").exists())

    def test_pending_ignores_a_vanishing_temp_file(self) -> None:
        # @scenario inquisitor: A file an agent cannot push is kept pending and reported
        root = branches.pending_dir("o/api") / "questions"
        root.mkdir(parents=True)
        (root / "2026-10-20-q-000001.md").write_text("x")
        real_stat = Path.stat
        (root / ".tmp-gone").write_text("y")

        def stat(p: Path, *a: object, **k: object) -> os.stat_result:
            if p.name.startswith(".tmp-"):
                raise FileNotFoundError(str(p))
            return real_stat(p)

        with mock.patch.object(Path, "stat", stat):
            found = branches._pending("o/api")  # pyright: ignore[reportPrivateUsage]
        self.assertEqual(found, [("questions/2026-10-20-q-000001.md", "x")])


class Read(Fake):
    def test_list_files_in_commit_order(self) -> None:
        # @scenario inquisitor: A file name holding a Re line is only unreadable input
        # (list_files passes the name through as data; test_formats checks parse finds it unreadable)
        hostile = "questions/2026-10-20-x-3f9a1c.md\nRe: o api issue 9"
        first = self.gh.add("o/api", "questions/z.md", render(QUESTION))
        second = self.gh.add("o/api", hostile, "x")
        third = self.gh.add("o/api", "questions/a.md", "a")
        self.assertEqual(branches.list_files("o/api"),
                         [branches.BranchFile("questions/z.md", render(QUESTION), first, False),
                          branches.BranchFile(hostile, "x", second, False),
                          branches.BranchFile("questions/a.md", "a", third, False)])

    def test_missing_branch_has_no_files(self) -> None:
        # @scenario inquisitor: A branch the command cannot read is reported, not empty
        # (no branch lists as empty; an unreadable repository or a malformed name fails)
        self.assertEqual(branches.list_files("o/api"), [])
        self.assertIsNone(branches.list_files("o/gone"))
        self.assertIsNone(branches.list_files("o/../x"))

    def test_empty_branch_has_no_files(self) -> None:
        # @scenario inquisitor: A branch the command cannot read is reported, not empty
        self.gh.heads[("o/api", "questions")] = self.gh.commit({}, [])
        self.assertEqual(branches.list_files("o/api"), [])

    def test_failed_call_lists_none(self) -> None:
        # @scenario inquisitor: A branch the command cannot read is reported, not empty
        self.gh.add("o/api", PATH, render(QUESTION))
        self.gh.fail["GET repos/o/api/git/trees"] = "gh: Server Error (HTTP 502)\n"
        self.assertIsNone(branches.list_files("o/api"))
        real = self.gh.graphql

        def broken(query: str, v: dict[str, str]) -> tuple[int, str, str]:
            return (1, "", "gh: timeout\n") if "$p0" in query else real(query, v)

        self.gh.fail.clear()
        with mock.patch.object(self.gh, "graphql", broken):
            self.assertIsNone(branches.list_files("o/api"))

    def test_truncated_tree_lists_none(self) -> None:
        # @scenario inquisitor: A branch the command cannot read is reported, not empty
        self.gh.add("o/api", PATH, render(QUESTION))
        real = self.gh.rest

        def truncated(method: str, endpoint: str, body: dict[str, Any]) -> tuple[int, str, str]:
            code, out, err = real(method, endpoint, body)
            if "git/trees/" in endpoint:
                out = json.dumps({**json.loads(out), "truncated": True})
            return code, out, err

        with mock.patch.object(self.gh, "rest", truncated):
            self.assertIsNone(branches.list_files("o/api"))

    def test_changed_file_is_marked(self) -> None:
        # @scenario inquisitor: A questions-branch decision changed after it was added is input
        # (list_files marks the change; test_branch_search checks the label)
        a = self.gh.add("o/api", "questions/a.md", "a")
        b = self.gh.add("o/api", "questions/b.md", "b")
        self.gh.add("o/api", "questions/a.md", "a2")
        c = self.gh.add("o/api", "questions/c.md", "c")
        self.gh.add("o/api", "questions/c.md", None)
        self.gh.add("o/api", "questions/c.md", "c")
        files = branches.list_files("o/api")
        assert files is not None
        self.assertEqual([(f.path, f.content, f.added_by, f.changed) for f in files],
                         [("questions/a.md", "a2", a, True), ("questions/b.md", "b", b, False),
                          ("questions/c.md", "c", c, True)])

    def test_paging_and_batches(self) -> None:
        # @scenario inquisitor: The repository's questions branch is searched
        # (a long branch reads every commit and file, in a bounded number of calls)
        self.gh.page = 3
        added = [self.gh.add("o/api", f"questions/{i:03d}.md", str(i)) for i in range(branches.BATCH + 5)]
        for n in range(4):
            self.gh.add("o/api", "questions/000.md", f"again {n}")
        files = branches.list_files("o/api")
        assert files is not None
        self.assertEqual([f.added_by for f in files], added)
        self.assertTrue(files[0].changed)
        self.assertEqual(files[0].content, "again 3")
        self.assertFalse(any(f.changed for f in files[1:]))
        graphql = [c for c in self.gh.calls if c[1] == "graphql"]
        commits = branches.BATCH + 9
        # head + further history pages + two file batches + path pages for the changed file
        self.assertEqual(len(graphql), 1 + (commits - 1) // 3 + 2 + 1)
        self.assertEqual(sum(c[1].startswith("repos/") for c in self.gh.calls), 1)

    def test_long_branch_keeps_commit_order(self) -> None:
        # @scenario inquisitor: The repository's questions branch is searched
        # (files added out of path order on a branch longer than one history page keep commit order)
        self.gh.page = 2
        added = [self.gh.add("o/api", f"questions/{i:03d}.md", str(i)) for i in range(6, -1, -1)]
        files = branches.list_files("o/api")
        assert files is not None
        self.assertEqual([f.added_by for f in files], added)

    def test_failed_blob_fallback_lists_none(self) -> None:
        # @scenario inquisitor: A branch the command cannot read is reported, not empty
        self.gh.add("o/api", PATH, b"---\n\xff\n")
        self.gh.fail["GET repos/o/api/git/blobs"] = "gh: API rate limit exceeded (HTTP 403)\n"
        self.assertIsNone(branches.list_files("o/api"))

    def test_malformed_answers_list_none(self) -> None:
        # @scenario inquisitor: A branch the command cannot read is reported, not empty
        # (an answer missing a field the read needs fails the read, never a partial listing)
        self.gh.add("o/api", PATH, b"---\n\xff\n")
        self.gh.add("o/api", "questions/" + OTHER.name, render(OTHER))
        real_graphql, real_rest = self.gh.graphql, self.gh.rest

        def drop(path: list[str]) -> Callable[[str, dict[str, str]], tuple[int, str, str]]:
            def answer(query: str, v: dict[str, str]) -> tuple[int, str, str]:
                code, out, err = real_graphql(query, v)
                data = json.loads(out)
                node: Any = data["data"]["repository"]
                try:  # only the query whose answer holds the key path is changed
                    for k in path[:-1]:
                        node = node[k]
                    if isinstance(node, list):
                        node = cast(list[Any], node)[0]
                    del node[path[-1]]
                except (KeyError, TypeError, IndexError):
                    pass
                return code, json.dumps(data), err
            return answer

        for path in (["ref", "target", "tree"], ["ref", "target", "history", "nodes", "oid"],
                     ["object", "h0", "totalCount"]):
            with mock.patch.object(self.gh, "graphql", drop(path)):
                self.assertIsNone(branches.list_files("o/api"), path)

        def no_content(method: str, endpoint: str, body: dict[str, Any]) -> tuple[int, str, str]:
            code, out, err = real_rest(method, endpoint, body)
            return (0, json.dumps({"encoding": "base64"}), "") if "git/blobs/" in endpoint else (code, out, err)

        with mock.patch.object(self.gh, "rest", no_content):
            self.assertIsNone(branches.list_files("o/api"))

    def test_non_utf8_content_is_read_through_rest(self) -> None:
        # @scenario inquisitor: A file name holding a Re line is only unreadable input
        # (content that is not UTF-8 reads as replacement characters, so parse() reads the file as
        # unreadable input, as it does a name holding a Re line)
        self.gh.add("o/api", PATH, b"---\n\xff\n")
        files = branches.list_files("o/api")
        assert files is not None
        self.assertEqual(files[0].content, "---\n�\n")

    def test_branch_search_reads_through_the_api_outside_a_checkout(self) -> None:
        # @scenario inquisitor: A branch search reads the branch through the API
        # @scenario inquisitor: The repository's questions branch is searched
        self.gh.add("o/api", PATH, render(QUESTION))
        here = Path(tempfile.mkdtemp())
        cwd = os.getcwd()
        os.chdir(here)
        self.addCleanup(os.chdir, cwd)
        out = io.StringIO()
        with mock.patch.object(branch_search, "gh_json", return_value=None), \
                mock.patch.object(branch_search, "_configured_lore", return_value=set()), \
                mock.patch("sys.stdin", io.StringIO("Should retries back off?")), \
                redirect_stdout(out):
            self.assertEqual(branch_search.run_branch_search(
                branch_search.BranchSearchArgs(repository="o/api")), 0)
        hits = cast(list[dict[str, Any]], json.loads(out.getvalue())["hits"])
        self.assertEqual([h["path"] for h in hits], [PATH])
        self.assertEqual(list(here.iterdir()), [])
        self.assertEqual(list(self.state.iterdir()), [])
        self.assertTrue(all(c[0] == "api" for c in self.gh.calls))


if __name__ == "__main__":
    unittest.main()

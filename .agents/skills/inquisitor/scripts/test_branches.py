"""Tests for branches: reading and pushing a questions branch with git's
plumbing, against a local bare repository standing in for GitHub."""

import os
import stat
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Callable
from unittest import mock

import branches
from formats import CitationFile, HashOnlyMiss, LogFile, render

QUESTION = LogFile(name="2026-10-20-should-retries-back-off-3f9a1c.md", asked="2026-10-20",
                   question="Should retries back off?", repository="o/api", asked_from="o/api")
PATH = "questions/" + QUESTION.name
MISS_PATH = "misses/" + "a" * 64 + ".md"
CITATION = CitationFile(name="2026-10-20-3f9a1c", entry="retry-backoff", date="2026-10-20")


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                          text=True).stdout


class BranchSetup(unittest.TestCase):
    """A local bare repository standing in for GitHub, and a clone."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.remote = self.root / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], check=True)
        self.clone = self.root / "clone"
        subprocess.run(["git", "init", "-q", "-b", "work", str(self.clone)], check=True)
        for c in (self.clone,):
            git(c, "config", "user.name", "Alice")
            git(c, "config", "user.email", "alice@example.com")
            git(c, "config", "commit.gpgsign", "false")
        (self.clone / "README.md").write_text("hi\n")
        git(self.clone, "add", "README.md")
        git(self.clone, "commit", "-qm", "init")
        git(self.clone, "remote", "add", "origin", str(self.remote))
        git(self.clone, "push", "-q", "origin", "work:main")
        self.env = mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.root / "state")})
        self.env.start()
        self.url = mock.patch.object(branches, "remote_url", self.at(self.remote))
        self.url.start()

    @staticmethod
    def at(remote: Path) -> Callable[[Path, str], str]:
        return lambda clone, repository: str(remote)

    def tearDown(self) -> None:
        self.url.stop()
        self.env.stop()
        subprocess.run(["rm", "-rf", str(self.root)], check=True)

    def remote_files(self) -> list[str]:
        return git(self.remote, "ls-tree", "-r", "--name-only", "questions").split()



class Branch(BranchSetup):
    def test_first_question_creates_orphan_branch(self) -> None:
        # @scenario inquisitor: The first question creates the questions branch
        # @scenario inquisitor: A questions-branch commit moves no HEAD
        head = git(self.clone, "rev-parse", "HEAD")
        reflog = git(self.clone, "reflog")
        (self.clone / "dirty.txt").write_text("x")
        result = branches.push_file(self.clone, "o/api", PATH, render(QUESTION),
                                    f"inquisitor: log {PATH}", False, False)
        self.assertEqual(result, branches.PushResult(pushed=True))
        self.assertEqual(self.remote_files(), [PATH])
        self.assertEqual(git(self.remote, "rev-list", "--count", "questions").strip(), "1")
        self.assertEqual(git(self.remote, "ls-tree", "-r", "--name-only", "main").split(), ["README.md"])
        self.assertEqual(git(self.clone, "rev-parse", "HEAD"), head)
        self.assertEqual(git(self.clone, "reflog"), reflog)
        self.assertEqual(git(self.clone, "status", "--porcelain"), "?? dirty.txt\n")
        self.assertEqual(git(self.clone, "branch", "--list"), "* work\n")

    def test_commit_message_has_no_trailer(self) -> None:
        # @scenario inquisitor: A log or miss file's commit carries no trailer
        branches.push_file(self.clone, "o/api", PATH, render(QUESTION), f"inquisitor: log {PATH}",
                           False, False)
        self.assertEqual(git(self.remote, "log", "-1", "--format=%B", "questions").strip(),
                         f"inquisitor: log {PATH}")
        self.assertEqual(git(self.remote, "log", "-1", "--format=%an", "questions").strip(), "Alice")

    def test_citation_commit_names_no_person(self) -> None:
        # @scenario inquisitor: A citation's commit names no person
        path = "citations/" + CITATION.name
        result = branches.push_file(self.clone, "o/lore", path, render(CITATION),
                                    f"inquisitor: log {path}", True, False)
        self.assertTrue(result.pushed)
        out = git(self.remote, "log", "-1", "--format=%an|%ae|%cn|%ce|%B|%at|%ct", "questions")
        an, ae, cn, ce, body, at, ct = out.split("|")
        self.assertEqual((an, ae, cn, ce), ("inquisitor", "noreply", "inquisitor", "noreply"))
        self.assertEqual(body.strip(), f"inquisitor: log {path}")
        self.assertEqual(int(at) % 86400, 0)
        self.assertEqual(at, ct.strip())

    def test_hash_only_miss_commit(self) -> None:
        # @scenario inquisitor: A hash-only miss file holds nothing
        # (its commit's identity; test_formats checks its empty body)
        result = branches.push_file(self.clone, "o/api", MISS_PATH, render(HashOnlyMiss(hash="a" * 64)),
                                    f"inquisitor: log {MISS_PATH}", True, True)
        self.assertTrue(result.pushed)
        self.assertEqual(git(self.remote, "log", "-1", "--format=%an %ce", "questions").strip(),
                         "inquisitor noreply")

    def test_taken_miss_pushes_nothing(self) -> None:
        # @scenario inquisitor: A retried push of a miss already on the branch pushes nothing
        content = render(HashOnlyMiss(hash="a" * 64))
        branches.push_file(self.clone, "o/api", MISS_PATH, content, "inquisitor: log x", True, True)
        before = git(self.remote, "rev-parse", "questions")
        result = branches.push_file(self.clone, "o/api", MISS_PATH, content, "inquisitor: log x",
                                    True, True)
        self.assertEqual(result, branches.PushResult(pushed=False, taken=True))
        self.assertEqual(git(self.remote, "rev-parse", "questions"), before)

    def test_moved_branch_is_retried(self) -> None:
        # @scenario inquisitor: A rejected push to the questions branch is retried
        other = replace(QUESTION, name="2026-10-20-other-000001.md")
        branches.push_file(self.clone, "o/api", "questions/" + other.name, render(other), "m", False, False)
        real_fetch = branches._fetch_tip  # pyright: ignore[reportPrivateUsage]
        calls: list[int] = []

        def stale_once(clone: Path, repository: str) -> "tuple[branches._Tip, str | None]":  # pyright: ignore[reportPrivateUsage]
            calls.append(1)
            if len(calls) == 1:
                # The first fetch reports the branch missing, as if another
                # writer created it just after; the orphan push is then
                # rejected, since the branch exists, and the retry fetches
                # the real tip.
                return "missing", None
            return real_fetch(clone, repository)

        with mock.patch.object(branches, "_fetch_tip", stale_once):
            result = branches.push_file(self.clone, "o/api", PATH, render(QUESTION), "m", False, False)
        self.assertTrue(result.pushed)
        self.assertEqual(len(calls), 2)
        self.assertEqual(sorted(self.remote_files()), sorted(["questions/" + other.name, PATH]))

    def test_unpushable_file_kept_pending_then_pushed(self) -> None:
        # @scenario inquisitor: A file an agent cannot push is kept pending and reported
        with mock.patch.object(branches, "remote_url", self.at(self.root / "absent.git")):
            result = branches.push_file(self.clone, "o/api", PATH, render(QUESTION), "m", False, False)
        self.assertFalse(result.pushed)
        self.assertTrue(result.pending)
        self.assertTrue(result.why)
        kept = self.root / "state" / "inquisitor" / "pending" / "o" / "api" / PATH
        self.assertEqual(kept.read_text(), render(QUESTION))
        self.assertEqual(stat.S_IMODE(kept.stat().st_mode), 0o600)

        other = replace(QUESTION, name="2026-10-21-other-000002.md")
        result = branches.push_file(self.clone, "o/api", "questions/" + other.name, render(other),
                                    "inquisitor: log questions/" + other.name, False, False)
        self.assertTrue(result.pushed)
        self.assertEqual(sorted(self.remote_files()), sorted([PATH, "questions/" + other.name]))
        self.assertEqual(git(self.remote, "log", "--reverse", "--format=%s", "questions").splitlines(),
                         [f"inquisitor: log {PATH}", "inquisitor: log questions/" + other.name])
        self.assertFalse(kept.exists())

    def test_service_keeps_nothing_pending(self) -> None:
        # @scenario inquisitor: A file the answer service cannot push leaves no pending copy
        with mock.patch.object(branches, "remote_url", self.at(self.root / "absent.git")):
            result = branches.push_file(self.clone, "o/api", PATH, render(QUESTION), "m", False, True)
        self.assertFalse(result.pushed)
        self.assertFalse(result.pending)
        self.assertTrue(result.why)
        self.assertFalse((self.root / "state" / "inquisitor" / "pending").exists())

    def test_list_files_in_commit_order(self) -> None:
        # @scenario inquisitor: A file name holding a Re line is only unreadable input
        # (list_files passes the name through as data; test_formats checks parse finds it unreadable)
        hostile = "questions/2026-10-20-x-3f9a1c.md\nRe: o api issue 9"
        tree = self.root / "seed"
        subprocess.run(["git", "init", "-q", "-b", "questions", str(tree)], check=True)
        git(tree, "config", "user.name", "Bob")
        git(tree, "config", "user.email", "bob@example.com")
        (tree / "questions").mkdir()
        (tree / PATH).write_text(render(QUESTION))
        git(tree, "add", ".")
        git(tree, "commit", "-qm", "one")
        (tree / hostile).write_text("x")
        git(tree, "add", ".")
        git(tree, "commit", "-qm", "two")
        git(tree, "push", "-q", str(self.remote), "questions:questions")
        first, second = git(tree, "rev-list", "--reverse", "HEAD").split()
        self.assertTrue(branches.fetch(self.clone, "o/api"))
        files = branches.list_files(self.clone, "o/api")
        self.assertEqual(files, [branches.BranchFile(PATH, render(QUESTION), first, False),
                                 branches.BranchFile(hostile, "x", second, False)])

    def test_missing_branch_has_no_files(self) -> None:
        # @scenario inquisitor: A branch the command cannot read is reported, not empty
        # (no branch lists as empty; a name that cannot be fetched fails)
        self.assertTrue(branches.fetch(self.clone, "o/api"))
        self.assertEqual(branches.list_files(self.clone, "o/api"), [])
        self.assertFalse(branches.fetch(self.clone, "o/../x"))

    def test_landed(self) -> None:
        # @scenario inquisitor: An answer whose commit reached the default branch counts for everyone
        git(self.clone, "fetch", "-q", "origin")
        git(self.clone, "remote", "set-head", "origin", "main")
        landed_commit = git(self.clone, "rev-parse", "HEAD").strip()
        (self.clone / "x.md").write_text("x")
        git(self.clone, "add", "x.md")
        git(self.clone, "commit", "-qm", "work")
        unmerged = git(self.clone, "rev-parse", "HEAD").strip()
        self.assertIs(branches.landed(self.clone, landed_commit), True)
        self.assertIs(branches.landed(self.clone, unmerged), False)
        self.assertIsNone(branches.landed(self.clone, "f" * 40))


class Hostile(BranchSetup):
    def seed(self, commits: list[tuple[str, str]], sign: bool = False) -> list[str]:
        tree = self.root / "seed"
        subprocess.run(["git", "init", "-q", "-b", "questions", str(tree)], check=True)
        git(tree, "config", "user.name", "Bob")
        git(tree, "config", "user.email", "bob@example.com")
        if sign:
            key = self.root / "key"
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
            git(tree, "config", "gpg.format", "ssh")
            git(tree, "config", "user.signingkey", str(key))
        (tree / "questions").mkdir()
        for path, content in commits:
            (tree / path).write_text(content)
            git(tree, "add", ".")
            git(tree, "commit", "-qm", path, *(["-S"] if sign else []))
        git(tree, "push", "-q", str(self.remote), "questions:questions")
        return git(tree, "rev-list", "--reverse", "HEAD").split()

    def test_root_commit_listed_whatever_the_log_config(self) -> None:
        # @scenario inquisitor: The repository's questions branch is searched
        # (every file, the root commit's included, whatever the person's git config)
        ids = self.seed([("questions/a.md", "a"), ("questions/b.md", "b"), ("questions/c.md", "c")],
                        sign=True)
        cfg = self.root / "gitconfig"
        cfg.write_text("[log]\n\tshowRoot = false\n\tshowSignature = true\n")
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(cfg)}):
            self.assertTrue(branches.fetch(self.clone, "o/api"))
            files = branches.list_files(self.clone, "o/api")
        assert files is not None
        self.assertEqual([(f.path, f.added_by) for f in files],
                         [("questions/a.md", ids[0]), ("questions/b.md", ids[1]),
                          ("questions/c.md", ids[2])])

    def test_pending_ignores_a_vanishing_temp_file(self) -> None:
        # @scenario inquisitor: A file an agent cannot push is kept pending and reported
        root = branches.pending_dir("o/api") / "questions"
        root.mkdir(parents=True)
        (root / "2026-10-20-q-000001.md").write_text("x")
        real_stat = Path.stat
        tmp = root / ".tmp-gone"
        tmp.write_text("y")

        def stat(p: Path, *a: object, **k: object) -> os.stat_result:
            if p.name.startswith(".tmp-"):
                raise FileNotFoundError(str(p))
            return real_stat(p)

        with mock.patch.object(Path, "stat", stat):
            found = branches._pending("o/api")  # pyright: ignore[reportPrivateUsage]
        self.assertEqual(found, [("questions/2026-10-20-q-000001.md", "x")])

    def test_taken_miss_pushes_nothing_even_with_pending(self) -> None:
        # @scenario inquisitor: A retried push of a miss already on the branch pushes nothing
        content = render(HashOnlyMiss(hash="a" * 64))
        branches.push_file(self.clone, "o/api", MISS_PATH, content, "m", True, True)
        branches._keep_pending("o/api", PATH, render(QUESTION))  # pyright: ignore[reportPrivateUsage]
        before = git(self.remote, "rev-parse", "questions")
        result = branches.push_file(self.clone, "o/api", MISS_PATH, content, "m", True, False)
        self.assertEqual(result, branches.PushResult(pushed=False, taken=True))
        self.assertEqual(git(self.remote, "rev-parse", "questions"), before)

    def test_changed_file_is_marked(self) -> None:
        # @scenario inquisitor: A questions-branch decision changed after it was added is input
        ids = self.seed([("questions/a.md", "a"), ("questions/b.md", "b"),
                         ("questions/a.md", "a2"), ("questions/c.md", "c")])
        tree = self.root / "seed"
        git(tree, "rm", "-q", "questions/c.md")
        git(tree, "commit", "-qm", "drop c")
        (tree / "questions" / "c.md").write_text("c")
        git(tree, "add", ".")
        git(tree, "commit", "-qm", "c again")
        git(tree, "push", "-q", str(self.remote), "questions:questions")
        self.assertTrue(branches.fetch(self.clone, "o/api"))
        files = branches.list_files(self.clone, "o/api")
        assert files is not None
        self.assertEqual([(f.path, f.content, f.added_by, f.changed) for f in files],
                         [("questions/a.md", "a2", ids[0], True),
                          ("questions/b.md", "b", ids[1], False),
                          ("questions/c.md", "c", ids[3], True)])

    def test_fetch_creates_the_cache(self) -> None:
        # @scenario inquisitor: The repository's questions branch is searched
        # (from no checkout, through the cache fetch creates)
        self.seed([("questions/a.md", "a")])
        cache = branches.cache_dir("o/api")
        self.assertEqual(cache, self.root / "state" / "inquisitor" / "branches" / "o" / "api")
        self.assertTrue(branches.fetch(cache, "o/api"))
        self.assertEqual(git(cache, "rev-parse", "--is-bare-repository").strip(), "true")
        files = branches.list_files(cache, "o/api")
        assert files is not None
        self.assertEqual([f.path for f in files], ["questions/a.md"])
        self.assertTrue(branches.fetch(cache, "o/api"))

    def test_remote_url_follows_origin(self) -> None:
        # @scenario inquisitor: The repository's questions branch is searched
        # (each fetch reaches the repository by SSH or HTTPS, as the clone's origin does)
        self.url.stop()
        try:
            for origin, want in (("git@github.com:o/x.git", "git@github.com:o/api.git"),
                                 ("ssh://git@github.com/o/x.git", "git@github.com:o/api.git"),
                                 ("https://github.com/o/x.git", "https://github.com/o/api.git")):
                git(self.clone, "remote", "set-url", "origin", origin)
                self.assertEqual(branches.remote_url(self.clone, "o/api"), want)
        finally:
            self.url.start()

    def test_unreadable_log_lists_none(self) -> None:
        # @scenario inquisitor: A branch the command cannot read is reported, not empty
        # (a log git cannot read gives None, not an empty listing)
        self.seed([("questions/a.md", "a")])
        self.assertTrue(branches.fetch(self.clone, "o/api"))
        real = branches._git  # pyright: ignore[reportPrivateUsage]

        def failing(cwd: Path, *args: str) -> "subprocess.CompletedProcess[bytes]":
            if args[0] == "log":
                return subprocess.CompletedProcess(args, 128, b"", b"bad")
            return real(cwd, *args)

        with mock.patch.object(branches, "_git", failing):
            self.assertIsNone(branches.list_files(self.clone, "o/api"))

    def test_pending_citation_commits_as_inquisitor(self) -> None:
        # @scenario inquisitor: A citation's commit names no person
        cpath = "citations/" + CITATION.name
        with mock.patch.object(branches, "remote_url", self.at(self.root / "absent.git")):
            kept = branches.push_file(self.clone, "o/api", cpath, render(CITATION), "m", True, False)
        self.assertTrue(kept.pending)
        result = branches.push_file(self.clone, "o/api", PATH, render(QUESTION), "m", False, False)
        self.assertTrue(result.pushed)
        authors = [line.split() for line in git(
            self.remote, "log", "--reverse", "--format=%an %ad", "--date=raw", "questions").splitlines()]
        self.assertEqual(authors[0][0], "inquisitor")
        self.assertEqual(int(authors[0][1]) % 86400, 0)
        self.assertEqual(authors[1][0], "Alice")

    def test_unpushable_miss_kept_pending_unless_known_taken(self) -> None:
        # @scenario inquisitor: A file an agent cannot push is kept pending and reported
        content = render(HashOnlyMiss(hash="a" * 64))
        with mock.patch.object(branches, "remote_url", self.at(self.root / "absent.git")):
            kept = branches.push_file(self.clone, "o/api", MISS_PATH, content, "m", True, False)
        self.assertTrue(kept.pending)
        (branches.pending_dir("o/api") / MISS_PATH).unlink()
        branches.push_file(self.clone, "o/api", MISS_PATH, content, "m", True, True)
        self.assertTrue(branches.fetch(self.clone, "o/api"))
        with mock.patch.object(branches, "remote_url", self.at(self.root / "absent.git")):
            again = branches.push_file(self.clone, "o/api", MISS_PATH, content, "m", True, False)
        self.assertFalse(again.pending)
        self.assertFalse((branches.pending_dir("o/api") / MISS_PATH).exists())

    def test_landed_needs_a_commit_id(self) -> None:
        # @scenario inquisitor: An answer whose commit reached the default branch counts for everyone
        git(self.clone, "fetch", "-q", "origin")
        git(self.clone, "remote", "set-head", "origin", "main")
        self.assertIsNone(branches.landed(self.clone, "HEAD"))
        self.assertIsNone(branches.landed(self.clone, "main~0"))

    def test_deleted_branch_lists_nothing(self) -> None:
        # @scenario inquisitor: A branch the command cannot read is reported, not empty
        # (a branch deleted on GitHub lists as empty, not as the old files)
        self.seed([("questions/a.md", "a")])
        self.assertTrue(branches.fetch(self.clone, "o/api"))
        git(self.remote, "update-ref", "-d", "refs/heads/questions")
        self.assertTrue(branches.fetch(self.clone, "o/api"))
        self.assertEqual(branches.list_files(self.clone, "o/api"), [])

    def test_odd_paths_do_not_mislead_the_listing(self) -> None:
        # @scenario inquisitor: A questions-branch decision is taken at its word
        # (an odd path a pusher adds cannot mark an unchanged decision changed)
        mark = "\x01inquisitor-commit:" + "0" * 40
        ids = self.seed([("nl.md", "y")])
        tree = self.root / "seed"
        # git puts a newline before the first name after a commit's mark,
        # so each odd path comes after another path in its commit, in git's
        # byte order: only there would the parser see the path's own
        # leading character.
        for names, msg in ((["\tz", "\nnl.md"], "newline"),
                           (["\tz", "\nnl.md"], "edit newline"),
                           (["\x01a", mark, "zz.md"], "mark")):
            for n in names:
                (tree / n).write_text(msg)
            git(tree, "add", ".")
            git(tree, "commit", "-qm", msg)
        ids = git(tree, "rev-list", "--reverse", "HEAD").split()
        git(tree, "push", "-q", str(self.remote), "questions:questions")
        cfg = self.root / "gitconfig"
        cfg.write_text("[diff]\n\trelative = true\n")
        (self.clone / "sub").mkdir()
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(cfg)}):
            self.assertTrue(branches.fetch(self.clone, "o/api"))
            files = branches.list_files(self.clone / "sub", "o/api")
        assert files is not None
        got = {f.path: (f.added_by, f.changed) for f in files}
        self.assertEqual(got["nl.md"], (ids[0], False))
        self.assertEqual(got["\nnl.md"], (ids[1], True))
        self.assertEqual(got["zz.md"], (ids[3], False))
        self.assertEqual(got[mark], (ids[3], False))

    def test_cache_is_sha1_whatever_the_config(self) -> None:
        # @scenario inquisitor: The repository's questions branch is searched
        # (through a cache, whatever the person's init config)
        self.seed([("questions/a.md", "a")])
        cfg = self.root / "gitconfig"
        cfg.write_text("[init]\n\tdefaultObjectFormat = sha256\n")
        cache = branches.cache_dir("o/api")
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(cfg)}):
            self.assertTrue(branches.fetch(cache, "o/api"))
            files = branches.list_files(cache, "o/api")
        assert files is not None
        self.assertEqual([f.path for f in files], ["questions/a.md"])

    def test_listing_ignores_log_encoding(self) -> None:
        # @scenario inquisitor: A questions-branch decision changed after it was added is input
        ids = self.seed([("questions/a.md", "a"), ("questions/a.md", "a2"), ("questions/b.md", "b")])
        self.assertTrue(branches.fetch(self.clone, "o/api"))
        for enc in ("UTF-16LE", "UTF-7"):
            with mock.patch.dict(os.environ, {"GIT_CONFIG_COUNT": "1",
                                              "GIT_CONFIG_KEY_0": "i18n.logOutputEncoding",
                                              "GIT_CONFIG_VALUE_0": enc}):
                files = branches.list_files(self.clone, "o/api")
            assert files is not None
            self.assertEqual([(f.path, f.added_by, f.changed) for f in files],
                             [("questions/a.md", ids[0], True), ("questions/b.md", ids[2], False)])

    def test_cache_works_under_hardened_and_inherited_git(self) -> None:
        # @scenario inquisitor: The repository's questions branch is searched
        # (through a cache, under safe.bareRepository=explicit and an inherited GIT_DIR)
        self.seed([("questions/a.md", "a")])
        cache = branches.cache_dir("o/api")
        other = self.root / "other"
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        hardened = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.bareRepository",
                    "GIT_CONFIG_VALUE_0": "explicit"}
        with mock.patch.dict(os.environ, hardened):
            self.assertTrue(branches.fetch(cache, "o/api"))
            files = branches.list_files(cache, "o/api")
        assert files is not None
        self.assertEqual([f.path for f in files], ["questions/a.md"])
        with mock.patch.dict(os.environ, {**hardened, "GIT_DIR": str(other / ".git")}):
            self.assertTrue(branches.fetch(cache, "o/api"))
            files = branches.list_files(cache, "o/api")
            self.assertTrue(branches.fetch(self.clone, "o/api"))
            in_clone = branches.list_files(self.clone, "o/api")
        assert files is not None and in_clone is not None
        self.assertEqual([f.path for f in files], ["questions/a.md"])
        self.assertEqual([f.path for f in in_clone], ["questions/a.md"])
        self.assertEqual(git(other, "for-each-ref").strip(), "")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Regression tests for check-commit-trailer.sh.

Standard library only:

    python3 test_hook.py

Each test builds a throwaway git repo in a temp directory, so nothing here can
touch a real repository. The contract under test: a commit that lands without a
`Bug-hunter:` trailer gets reported exactly once, and nothing else does.
"""

import contextlib
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import time
import unittest

HOOK = pathlib.Path(__file__).resolve().parent / "check-commit-trailer.sh"
MINT = pathlib.Path(__file__).resolve().parent / "mint-trailer.sh"
WRAPPER = pathlib.Path(__file__).resolve().parent / "commit-with-trailer.sh"

REPORTED = 2
QUIET = 0

TRAILER = "Bug-hunter: 1 iteration, 0 bugs found"

# Every fixture below that carries a real Bug-hunter: trailer is meant to
# represent a commit that was genuinely checked — which, under the mint
# scheme, means it needs a matching Bug-hunter-Tree binding too, or these
# fixtures would themselves be testing against the exact fabrication shape
# this file exists to catch. Rather than hand-computing a tree hash at each
# of the ~50 call sites that build a message containing TRAILER (across this
# file's own repo, submodules, clones, and other throwaway repos), one choke
# point does it for all of them: every `git commit -m <message>` this test
# file runs, however it gets there — self.git(), a local closure, a bare
# subprocess.run() — passes through here first. A message whose Bug-hunter:
# trailer is not a skip, and that does not already carry a Bug-hunter-Tree
# line, gets one appended, computed with a real `git write-tree` against
# whatever the *targeted* repo (the call's own `cwd`) has staged at that
# exact moment — which every call site already stages before constructing
# the message, by construction of when Python evaluates the argument.
#
# A test that wants to exercise the fabricated-trailer case itself — no
# binding, or a stale one — either builds the message by hand and wraps the
# call in `with self.no_auto_mint():`, or (for a deliberately stale binding)
# already embeds a `Bug-hunter-Tree:` line itself, which this leaves alone.
_REAL_SUBPROCESS_RUN = subprocess.run
_AUTO_MINT_SUPPRESSED = False


def _run_with_auto_mint(cmd, *args, **kwargs):
    if (
        not _AUTO_MINT_SUPPRESSED
        and isinstance(cmd, list)
        and "commit" in cmd
        and "-m" in cmd
    ):
        i = cmd.index("-m")
        message = cmd[i + 1]
        m = re.search(r"(?im)^Bug-hunter:[ \t]*(.*)$", message)
        if (
            m
            and not m.group(1).strip().lower().startswith("skipped")
            and "Bug-hunter-Tree:" not in message
        ):
            tree = _REAL_SUBPROCESS_RUN(
                ["git", "write-tree"], cwd=kwargs.get("cwd", "."),
                capture_output=True, text=True,
            )
            if tree.returncode == 0:
                cmd = list(cmd)
                cmd[i + 1] = f"{message}\nBug-hunter-Tree: {tree.stdout.strip()}"
    return _REAL_SUBPROCESS_RUN(cmd, *args, **kwargs)


subprocess.run = _run_with_auto_mint


class CommitTrailerTests(unittest.TestCase):
    def setUp(self):
        self.repo = pathlib.Path(tempfile.mkdtemp(prefix="bug-hunter-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        self.git("init", "-q", "-b", "main")

    # -- helpers ----------------------------------------------------------

    def git(self, *args):
        result = subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=self.repo,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def commit(self, message, filename="f.txt", content="x"):
        (self.repo / filename).write_text(content)
        self.git("add", filename)
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def commit_at(self, message, when, filename="old.txt", content="x"):
        """A commit whose committer date is `when` — i.e. not this session."""
        (self.repo / filename).write_text(content)
        self.git("add", filename)
        result = subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m", message,
             "--date", when],
            cwd=self.repo, capture_output=True, text=True,
            env={**os.environ, "GIT_COMMITTER_DATE": when},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.git("rev-parse", "HEAD")

    def run_hook(self, *args, cwd=None):
        payload = json.dumps({"cwd": str(cwd or self.repo), "tool_name": "Bash"})
        return subprocess.run(
            ["sh", str(HOOK), *args],
            input=payload,
            capture_output=True,
            text=True,
            cwd=self.repo,
        )

    @property
    def state_file(self):
        return self.repo / ".git" / "bug-hunter-head"

    def settle(self):
        """Run once so the current HEAD is recorded as already-judged."""
        self.commit("initial")
        self.run_hook("--host", "claude")

    def mint(self):
        """What scripts/mint-trailer.sh prints for whatever is staged right
        now — a Bug-hunter-Tree trailer bound to that exact tree."""
        result = subprocess.run(
            ["sh", str(MINT)], cwd=self.repo, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    @contextlib.contextmanager
    def no_auto_mint(self):
        """Suppresses the module-wide auto-mint wrapper for the commits made
        inside this block — for a test that means to exercise the fabricated
        case itself: a real Bug-hunter: trailer, claiming real work, with
        nothing behind it."""
        global _AUTO_MINT_SUPPRESSED
        _AUTO_MINT_SUPPRESSED = True
        try:
            yield
        finally:
            _AUTO_MINT_SUPPRESSED = False

    def commit_bound(self, subject, bug_hunter_line, filename="bound.txt", content="x",
                      tree_override=None):
        """Stage `filename`, mint a real Bug-hunter-Tree from the resulting
        index, and commit with both trailers — what an honest run of this
        skill's own committing step produces. `tree_override` simulates
        minting against one tree and then landing another (staging more, or
        an unrelated amend, after the mint ran)."""
        (self.repo / filename).write_text(content)
        self.git("add", filename)
        tree_line = tree_override if tree_override is not None else self.mint()
        message = f"{subject}\n\n{bug_hunter_line}\n{tree_line}"
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    # -- the thing it is for ----------------------------------------------

    def test_a_commit_without_the_trailer_is_reported(self):
        self.settle()
        sha = self.commit("FEAT: add a thing", filename="g.txt")
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("bug-hunter", result.stderr)
        self.assertIn(sha[:7], result.stderr)
        self.assertIn("1 new commit", result.stderr)

    def test_a_commit_with_the_trailer_is_ignored(self):
        self.settle()
        self.commit(f"FEAT: add a thing\n\n{TRAILER}", filename="g.txt")
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, QUIET)
        self.assertEqual(result.stderr, "")

    def test_a_skipped_at_triage_trailer_counts_as_checked(self):
        self.settle()
        self.commit(
            "REFACTOR(rename): move things\n\nBug-hunter: skipped at triage (rename)",
            filename="g.txt",
        )
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_the_report_carries_the_facts_and_no_commands(self):
        # The report states which commits and which repository, and stops. It
        # does not construct git commands: doing so meant computing them from
        # the reader's context, which this script cannot see and the reader has.
        self.settle()
        sha = self.commit("FEAT: x", filename="g.txt")[:7]
        stderr = self.run_hook("--host", "claude").stderr
        self.assertIn(sha, stderr)
        self.assertIn(str(self.repo), stderr)
        self.assertIn("disable-hook bug-hunter", stderr)
        self.assertNotIn("git -C", stderr)
        self.assertNotIn("reset --soft", stderr)

    def test_the_report_keeps_the_context_free_trailer_guidance(self):
        # The rule is not "no imperatives" — it is nothing computed from a frame
        # the reader does not occupy. Where a trailer goes in a message is true
        # wherever they stand, and it is the one thing here they cannot cheaply
        # work out; a remedy is not. Deleting this paragraph, or putting an
        # --amend prescription back, left every other test in the file green.
        self.settle()
        self.commit("FEAT: x", filename="g.txt")
        stderr = self.run_hook("--host", "claude").stderr
        self.assertIn("A trailer belongs in the last paragraph", stderr)
        self.assertNotIn("--amend", stderr)

    def test_a_commit_is_reported_once_and_not_again(self):
        # Otherwise every later command in the repo repeats the same complaint.
        self.settle()
        self.commit("FEAT: x", filename="g.txt")
        self.assertEqual(self.run_hook("--host", "claude").returncode, REPORTED)
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_several_new_commits_are_counted_and_the_checked_ones_excluded(self):
        self.settle()
        self.commit("FEAT: a", filename="a.txt")
        self.commit(f"FEAT: b\n\n{TRAILER}", filename="b.txt")
        self.commit("FEAT: c", filename="c.txt")
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("2 new commit", result.stderr)
        self.assertIn("FEAT: a", result.stderr)
        self.assertIn("FEAT: c", result.stderr)
        self.assertNotIn("FEAT: b", result.stderr)

    # -- the trailer is a trailer, not a substring -------------------------

    def test_a_message_that_merely_mentions_the_trailer_is_still_reported(self):
        # `--grep` would call this checked. git's trailer parser does not, and
        # this exact message is one anyone working on this skill would write.
        self.settle()
        self.commit(
            "FEAT: teach the hook to read the Bug-hunter: trailer", filename="g.txt"
        )
        self.assertEqual(self.run_hook("--host", "claude").returncode, REPORTED)

    def test_a_trailer_in_the_body_prose_is_still_reported(self):
        self.settle()
        self.commit(
            "FIX: parser\n\nWe used to look for a Bug-hunter: line here.",
            filename="g.txt",
        )
        self.assertEqual(self.run_hook("--host", "claude").returncode, REPORTED)

    def test_a_trailer_beside_other_trailers_counts(self):
        # The shape every real commit has once a Co-Authored-By is involved.
        self.settle()
        self.commit(
            "FEAT: d\n\nBody.\n\n"
            f"{TRAILER}\nCo-Authored-By: Someone <someone@example.com>",
            filename="g.txt",
        )
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_a_trailer_split_off_by_a_blank_line_is_reported_and_explained(self):
        # git does not read this as a trailer, and the hook caught exactly this
        # on its own shipping commit. Reporting it without saying why would look
        # like the hook was simply broken.
        self.settle()
        self.commit(
            "FEAT: d\n\nBody.\n\n"
            f"{TRAILER}\n\nCo-Authored-By: Someone <someone@example.com>",
            filename="g.txt",
        )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("does not read it as a trailer", result.stderr)
        self.assertIn("last paragraph", result.stderr)

    def test_a_lowercase_trailer_counts(self):
        # git matches trailer keys case-insensitively, and the report the agent
        # reads opens with a lowercase "bug-hunter:". Reporting work that *was*
        # checked is the false alarm that gets a hook switched off.
        self.settle()
        self.commit(
            "FEAT: d\n\nbug-hunter: 1 iteration, 0 bugs found", filename="g.txt"
        )
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    # -- the ways HEAD moves that are not new work ------------------------

    def test_with_no_baseline_existing_history_is_not_judged(self):
        # Replaces two earlier rules — "judge nothing the first time", which hid
        # a fresh worktree's only commit, and "judge just the newest entry",
        # which reported one of N. The rule now is recency: work from this
        # session counts, history the hook had no part in does not.
        old = "2026-08-01T10:00:00"
        self.commit_at("FEAT: one, no trailer", old, filename="a.txt")
        self.commit_at("FEAT: two, no trailer", old, filename="b.txt")
        self.commit_at("FEAT: three, no trailer", old, filename="c.txt")
        self.git("checkout", "-q", "-b", "elsewhere")

        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, QUIET, result.stderr)
        self.assertTrue(self.state_file.is_file())

    def test_checking_out_an_older_commit_is_not_a_new_commit(self):
        self.settle()
        first = self.git("rev-parse", "HEAD")
        self.commit(f"FEAT: b\n\n{TRAILER}", filename="b.txt")
        self.run_hook("--host", "claude")
        self.git("checkout", "-q", first)
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_a_reset_backwards_is_not_a_new_commit(self):
        self.settle()
        self.commit(f"FEAT: b\n\n{TRAILER}", filename="b.txt")
        self.run_hook("--host", "claude")
        self.git("reset", "-q", "--hard", "HEAD~1")
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_switching_back_to_a_branch_does_not_re_report_it(self):
        # The most common agent branch flow there is. Reporting on every switch
        # is unbounded nagging, and nagging gets the hook turned off.
        self.settle()
        self.git("checkout", "-q", "-b", "feature")
        self.commit("FEAT: work, no trailer", filename="b.txt")
        self.assertEqual(self.run_hook("--host", "claude").returncode, REPORTED)

        for _ in range(3):
            self.git("checkout", "-q", "main")
            self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)
            self.git("checkout", "-q", "feature")
            self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_a_fast_forward_merge_does_not_re_report(self):
        self.settle()
        self.git("checkout", "-q", "-b", "feature")
        self.commit("FEAT: work, no trailer", filename="b.txt")
        self.run_hook("--host", "claude")
        self.git("checkout", "-q", "main")
        self.run_hook("--host", "claude")
        self.git("merge", "--ff-only", "-q", "feature")
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_pulling_someone_elses_commits_is_not_your_work(self):
        # Reporting a teammate's commits would be bad enough; the report also
        # recommends `git reset --soft HEAD~1` for them.
        origin = pathlib.Path(tempfile.mkdtemp(prefix="origin-")).resolve()
        self.addCleanup(shutil.rmtree, origin, ignore_errors=True)
        self.settle()
        self.git("clone", "-q", str(self.repo), str(origin / "clone"))

        clone = origin / "clone"
        self.commit("FEAT: theirs, no trailer", filename="t.txt")
        self.commit("FIX: theirs too, no trailer", filename="u.txt")

        first = subprocess.run(
            ["sh", str(HOOK), "--host", "claude"],
            input=json.dumps({"cwd": str(clone)}),
            capture_output=True,
            text=True,
        )
        self.assertEqual(first.returncode, QUIET)  # baseline in the clone

        subprocess.run(["git", "pull", "-q", "--ff-only"], cwd=clone, check=True)
        result = subprocess.run(
            ["sh", str(HOOK), "--host", "claude"],
            input=json.dumps({"cwd": str(clone)}),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, QUIET, result.stderr)

    def test_a_clean_rebase_replaying_old_commits_is_not_reported(self):
        self.settle()
        (self.repo / "shared").write_text("base\n")
        self.git("add", "shared")
        self.git("commit", "-q", "-m", f"FEAT: shared\n\n{TRAILER}")
        self.git("checkout", "-q", "-b", "feature")
        self.commit("FEAT: old work, no trailer", filename="shared", content="theirs\n")
        self.git("checkout", "-q", "main")
        self.commit("FEAT: main moved", filename="shared", content="ours\n")
        self.git("checkout", "-q", "feature")
        self.run_hook("--host", "claude")

        # A clean replay moves HEAD onto content that already existed, and
        # stays silent. A rebase finished by hand does not — see
        # test_a_conflicted_rebase_is_reported, which supersedes the earlier
        # rule that treated every rebase as replay.
        subprocess.run(["git", "rebase", "main"], cwd=self.repo, capture_output=True)
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    # -- rewriting a reported commit is still unchecked work ---------------

    def test_re_committing_after_the_suggested_reset_is_checked_again(self):
        # The report tells the agent to reset and re-commit. If that replacement
        # slipped through, the remedy would be a bypass.
        self.settle()
        self.commit("FEAT: b, no trailer", filename="b.txt")
        self.assertEqual(self.run_hook("--host", "claude").returncode, REPORTED)

        self.git("reset", "-q", "--soft", "HEAD~1")
        self.commit("FEAT: b redone, still no trailer", filename="b.txt", content="b2")
        self.assertEqual(self.run_hook("--host", "claude").returncode, REPORTED)

    def test_amending_in_new_code_is_reported(self):
        self.settle()
        self.commit(f"FEAT: b\n\n{TRAILER}", filename="b.txt")
        self.run_hook("--host", "claude")
        (self.repo / "big-new.py").write_text("unchecked code\n")
        self.git("add", "big-new.py")
        self.git("commit", "-q", "--amend", "-m", "FEAT: b plus big-new.py")
        self.assertEqual(self.run_hook("--host", "claude").returncode, REPORTED)

    # -- worktrees ---------------------------------------------------------

    def test_the_first_commit_in_a_new_worktree_is_checked(self):
        # Agents run a worktree per task, and a task is often one commit — so the
        # first one is the only one that matters.
        self.settle()
        tree = self.repo.parent / f"{self.repo.name}-wt"
        self.addCleanup(shutil.rmtree, tree, ignore_errors=True)
        self.git("worktree", "add", "-q", "-b", "feature", str(tree))

        (tree / "w.txt").write_text("w")
        subprocess.run(["git", "add", "w.txt"], cwd=tree, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m", "FEAT: in a worktree"],
            cwd=tree,
            check=True,
        )
        result = subprocess.run(
            ["sh", str(HOOK), "--host", "claude"],
            input=json.dumps({"cwd": str(tree)}),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, REPORTED, result.stderr)

    def test_a_merge_commit_is_not_reported(self):
        self.settle()
        self.git("checkout", "-q", "-b", "side")
        self.commit(f"FEAT: side\n\n{TRAILER}", filename="s.txt")
        self.git("checkout", "-q", "main")
        self.commit(f"FEAT: main\n\n{TRAILER}", filename="m.txt")
        self.run_hook("--host", "claude")
        self.git("merge", "--no-ff", "-q", "-m", "Merge branch 'side'", "side")
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_a_command_that_changes_nothing_is_silent(self):
        self.settle()
        for _ in range(3):
            self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    # -- environments it should stay out of -------------------------------

    def test_a_directory_that_is_not_a_repo_is_ignored(self):
        outside = pathlib.Path(tempfile.mkdtemp(prefix="not-a-repo-")).resolve()
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        result = self.run_hook("--host", "claude", cwd=outside)
        self.assertEqual(result.returncode, QUIET)

    def test_a_repo_with_no_commits_is_ignored(self):
        empty = pathlib.Path(tempfile.mkdtemp(prefix="empty-repo-")).resolve()
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=empty, check=True)
        self.assertEqual(self.run_hook("--host", "claude", cwd=empty).returncode, QUIET)

    def test_the_reported_repo_is_the_one_the_command_ran_in(self):
        # The hook's own cwd is not necessarily where the agent was working.
        other = pathlib.Path(tempfile.mkdtemp(prefix="other-repo-")).resolve()
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        self.settle()
        result = self.run_hook("--host", "claude", cwd=other)
        self.assertEqual(result.returncode, QUIET)

    # -- host protocols ---------------------------------------------------

    def test_cursor_gets_follow_up_context_as_json(self):
        self.settle()
        self.commit("FEAT: x", filename="g.txt")
        result = self.run_hook("--host", "cursor")
        self.assertEqual(result.returncode, QUIET)  # cursor reads stdout, not the code
        context = json.loads(result.stdout)["additional_context"]
        self.assertIn("bug-hunter", context)
        self.assertIn("without being checked", context)

    def test_an_unknown_host_still_reports_on_stderr(self):
        self.settle()
        self.commit("FEAT: x", filename="g.txt")
        result = self.run_hook("--host", "antigravity")
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("bug-hunter", result.stderr)

    def test_a_host_flag_with_no_value_does_not_hang(self):
        self.settle()
        self.commit("FEAT: x", filename="g.txt")
        try:
            result = subprocess.run(
                ["sh", str(HOOK), "--host"],
                input=json.dumps({"cwd": str(self.repo)}),
                capture_output=True,
                text=True,
                cwd=self.repo,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            self.fail("the hook hung instead of deciding")
        self.assertIn(result.returncode, (QUIET, REPORTED))

    # -- ① the cursor is a position, not a sha ----------------------------

    def test_a_commit_that_also_moves_head_back_is_still_reported(self):
        # The most common agent chain there is, and the whole purpose of this
        # hook failing on it: matching the baseline *sha* stops the walk early,
        # because that sha appears in the reflog many times.
        self.settle()
        self.git("checkout", "-q", "-b", "fix")
        self.commit("FIX: core, never checked", filename="core.py")
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--ff-only", "fix")

        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr)
        self.assertIn("FIX: core, never checked", result.stderr)

    def test_a_fabricated_trailer_survives_a_ff_merge_back_onto_main(self):
        # The same chain, with a trailer this time: a fast-forward merge gives
        # the fix commit a `merge:` reflog entry newer than the `commit:`
        # entry that actually created it. Taking only the newest entry for a
        # sha reads `merge:`, never matches `commit:`/`commit (amend):`, and
        # would skip the mint check entirely — a silent miss on exactly the
        # chain the test above calls "the most common agent chain there is."
        self.settle()
        self.git("checkout", "-q", "-b", "fix")
        with self.no_auto_mint():
            self.commit(
                "FIX: core\n\nBug-hunter: 1 iteration, 1 bug fixed",
                filename="core.py",
            )
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--ff-only", "fix")

        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")
        self.assertIn("Bug-hunter-Tree", result.stderr)

    def test_it_never_forgets_a_commit_it_has_not_reported(self):
        self.settle()
        self.git("checkout", "-q", "-b", "fix")
        self.commit("FIX: core, never checked", filename="core.py")
        self.git("checkout", "-q", "main")
        self.run_hook("--host", "claude")          # reports it
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_more_commits_than_the_reflog_window_are_all_counted(self):
        self.settle()
        for i in range(60):
            self.commit(f"REFACTOR: file {i}", filename=f"f{i}.py")
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("60 new commit", result.stderr)
        self.assertIn("REFACTOR: file 0", result.stderr)

    def test_a_fresh_worktree_reports_every_commit_of_its_first_command(self):
        self.settle()
        tree = self.repo.parent / f"{self.repo.name}-wt2"
        self.addCleanup(shutil.rmtree, tree, ignore_errors=True)
        self.git("worktree", "add", "-q", "-b", "wt2", str(tree))
        for i in range(3):
            (tree / f"p{i}.py").write_text(str(i))
            subprocess.run(["git", "add", f"p{i}.py"], cwd=tree, check=True)
            subprocess.run(
                ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
                 "-c", "commit.gpgsign=false", "commit", "-q", "-m", f"FEAT: part {i}"],
                cwd=tree, check=True,
            )
        result = subprocess.run(
            ["sh", str(HOOK), "--host", "claude"],
            input=json.dumps({"cwd": str(tree)}), capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, REPORTED, result.stderr)
        self.assertIn("3 new commit", result.stderr)

    def test_a_first_run_does_not_judge_an_old_commit(self):
        # The hook was just installed. The newest thing that happened was a
        # commit from two weeks ago, already pushed. Advising `reset --soft` on
        # it would be destructive, and it is not this session's work.
        self.commit_at(
            "FEAT: shipped weeks ago", "2026-08-01T10:00:00", filename="old.py"
        )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, QUIET, result.stderr)

    # -- ② which reflog actions author code -------------------------------

    def test_a_revert_is_new_code_and_is_reported(self):
        self.settle()
        self.git("revert", "--no-edit", "HEAD")
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr)

    def test_a_cherry_pick_is_reported(self):
        self.settle()
        self.git("checkout", "-q", "-b", "side")
        self.commit(f"FEAT: side\n\n{TRAILER}", filename="s.py")
        picked = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        self.run_hook("--host", "claude")
        self.git("cherry-pick", picked)
        # The cherry-picked copy keeps the trailer, so use one without.
        self.git("checkout", "-q", "-b", "side2")
        self.commit("FEAT: unchecked side work", filename="s2.py")
        target = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        self.run_hook("--host", "claude")
        self.git("cherry-pick", target)
        self.assertEqual(self.run_hook("--host", "claude").returncode, REPORTED)

    def test_resolving_a_merge_conflict_is_not_reported(self):
        # A clean merge is silent; a conflicted one finishes with
        # `commit (merge):`. Reporting only the conflicted case is backwards,
        # and `reset --soft` on a merge commit drops the second parent.
        self.settle()
        self.git("checkout", "-q", "-b", "side")
        self.commit(f"FEAT: theirs\n\n{TRAILER}", filename="shared", content="theirs\n")
        self.git("checkout", "-q", "main")
        self.commit(f"FEAT: ours\n\n{TRAILER}", filename="shared", content="ours\n")
        self.run_hook("--host", "claude")
        subprocess.run(["git", "merge", "side"], cwd=self.repo, capture_output=True)
        (self.repo / "shared").write_text("resolved\n")
        self.git("add", "shared")
        subprocess.run(
            ["git", "-c", "core.editor=true", "-c", "user.name=T",
             "-c", "user.email=t@e.com", "commit", "-q", "--no-edit"],
            cwd=self.repo, capture_output=True,
        )
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    # -- ③ failures that must not look like "all clear" -------------------

    def test_a_git_that_cannot_read_trailers_says_so(self):
        # git prints an unsupported %(...) placeholder verbatim instead of
        # failing, so every commit would look checked and the hook would be
        # silent forever — indistinguishable from working.
        stub_dir = self.repo.parent / "stubbin"
        stub_dir.mkdir(exist_ok=True)
        self.addCleanup(shutil.rmtree, stub_dir, ignore_errors=True)
        real = shutil.which("git")
        stub = stub_dir / "git"
        stub.write_text(
            "#!/bin/sh\n"
            'case "$*" in *"trailers:key"*) echo \'%(trailers:key=Bug-hunter)\'; exit 0;; esac\n'
            f'exec {real} "$@"\n'
        )
        stub.chmod(0o755)

        self.settle()
        self.commit("FEAT: x", filename="g.py")
        result = subprocess.run(
            ["sh", str(HOOK), "--host", "claude"],
            input=json.dumps({"cwd": str(self.repo)}),
            capture_output=True,
            text=True,
            env={**os.environ, "PATH": f"{stub_dir}:{os.environ['PATH']}"},
        )
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("trailer", result.stderr.lower())

    def test_an_abandoned_lock_does_not_disable_the_hook_forever(self):
        # SIGKILL skips the EXIT trap. Without an age check the hook is
        # silently dead from then on, with no way to notice.
        self.settle()
        self.commit("FEAT: x", filename="g.py")
        lock = self.repo / ".git" / "bug-hunter.lock"
        lock.mkdir()
        old = time.time() - 3600
        os.utime(lock, (old, old))
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr)

    def test_an_empty_trailer_value_does_not_count_as_checked(self):
        self.settle()
        self.commit("FEAT: x\n\nBug-hunter:", filename="g.py")
        self.assertEqual(self.run_hook("--host", "claude").returncode, REPORTED)

    def test_the_first_cwd_in_the_payload_wins(self):
        self.settle()
        self.commit("FEAT: x", filename="g.py")
        payload = (
            '{"cwd":"%s","tool_input":{"command":"x","cwd":"/nowhere/at/all"}}'
            % self.repo
        )
        result = subprocess.run(
            ["sh", str(HOOK), "--host", "claude"],
            input=payload, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, REPORTED, result.stderr)

    # -- iteration 2: what iteration 1's fixes broke or missed -------------

    def test_a_conflicted_cherry_pick_is_reported(self):
        # A clean pick copies an existing commit and IS reported; a conflicted
        # one contains hand-written resolution and was not. Backwards, and for
        # the same reason `commit (merge)` is excluded.
        self.settle()
        self.git("checkout", "-q", "-b", "side")
        # No trailer on the source: a cherry-pick copies the message, so a
        # trailered source would produce a trailered copy and prove nothing.
        self.commit("side change, unchecked", filename="f.txt", content="theirs\n")
        picked = self.git("rev-parse", "HEAD")
        self.run_hook("--host", "claude")   # report it here, not later
        self.git("checkout", "-q", "main")
        self.commit(f"main change\n\n{TRAILER}", filename="f.txt", content="ours\n")
        self.run_hook("--host", "claude")

        subprocess.run(["git", "cherry-pick", picked], cwd=self.repo, capture_output=True)
        (self.repo / "f.txt").write_text("hand written resolution nobody checked\n")
        self.git("add", "f.txt")
        subprocess.run(
            ["git", "-c", "core.editor=true", "-c", "user.name=T",
             "-c", "user.email=t@e.com", "cherry-pick", "--continue"],
            cwd=self.repo, capture_output=True,
        )
        self.assertEqual(self.run_hook("--host", "claude").returncode, REPORTED)

    def test_a_trailer_value_mentioning_the_placeholder_does_not_trip_the_probe(self):
        # The probe read HEAD's trailer VALUE, so a commit describing the probe
        # made the hook claim git cannot read trailers — and swallowed the real
        # findings in that same window, permanently.
        self.settle()
        self.commit("FEAT: UNCHECKED CODE nobody reviewed", filename="danger.py")
        self.commit(
            "FIX(hook): probe wording\n\n"
            "Bug-hunter: 2 iterations, fixed the %(trailers:key=) probe",
            filename="check.sh",
        )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED)
        self.assertNotIn("cannot read commit trailers", result.stderr)
        self.assertIn("UNCHECKED CODE", result.stderr)



    def test_the_too_old_git_warning_reaches_cursor(self):
        # The one message deliberately made loud was the only one ignoring the
        # host protocol, so Cursor users got nothing.
        stub_dir = self.repo.parent / "stubbin2"
        stub_dir.mkdir(exist_ok=True)
        self.addCleanup(shutil.rmtree, stub_dir, ignore_errors=True)
        stub = stub_dir / "git"
        stub.write_text(
            "#!/bin/sh\n"
            'case "$*" in *"trailers:key"*) echo \'%(trailers:key=Bug-hunter)\'; exit 0;; esac\n'
            f'exec {shutil.which("git")} "$@"\n'
        )
        stub.chmod(0o755)
        self.settle()
        self.commit("FEAT: x", filename="g.txt")
        result = subprocess.run(
            ["sh", str(HOOK), "--host", "cursor"],
            input=json.dumps({"cwd": str(self.repo)}),
            capture_output=True, text=True,
            env={**os.environ, "PATH": f"{stub_dir}:{os.environ['PATH']}"},
        )
        self.assertEqual(result.returncode, QUIET)
        self.assertIn("additional_context", json.loads(result.stdout))

    def test_a_cwd_containing_json_punctuation_is_read_correctly(self):
        # Splitting the payload on , and { split the path value too, so the
        # hook fell back to its own cwd and reported a different repository.
        odd = self.repo.parent / f"{self.repo.name}-svc,api"
        self.addCleanup(shutil.rmtree, odd, ignore_errors=True)
        odd.mkdir()
        for cmd in (["init", "-q", "-b", "main"],):
            subprocess.run(["git", *cmd], cwd=odd, check=True)
        (odd / "b.txt").write_text("b")
        subprocess.run(["git", "add", "b.txt"], cwd=odd, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m", "FEAT: the actual work"],
            cwd=odd, check=True,
        )
        self.settle()   # self.repo has its own commits and a baseline

        result = subprocess.run(
            ["sh", str(HOOK), "--host", "claude"],
            input=json.dumps({"cwd": str(odd)}),
            capture_output=True, text=True, cwd=self.repo,
        )
        self.assertTrue((odd / ".git" / "bug-hunter-head").is_file(), result.stderr)


    def test_a_commit_after_the_reflog_shrinks_is_still_reported(self):
        self.settle()
        self.commit(f"FEAT: a\n\n{TRAILER}", filename="a.txt")
        self.run_hook("--host", "claude")
        subprocess.run(
            ["git", "reflog", "expire", "--expire=now",
             "--expire-unreachable=now", "HEAD"],
            cwd=self.repo, capture_output=True,
        )
        self.commit("FEAT: brand new unchecked after gc", filename="z.py")
        self.assertEqual(self.run_hook("--host", "claude").returncode, REPORTED)


    # -- iteration 3: what the environment does to it ---------------------

    def test_signed_commits_with_log_showsignature_do_not_blind_it(self):
        # log.showSignature prepends verification text to `git log --format`
        # output, so every commit reads as trailered and the hook goes silent
        # forever — and the same contamination disarms the too-old-git probe.
        key = self.repo / "key"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-f", str(key), "-N", "", "-C", "t@e.com"],
            check=True, capture_output=True,
        )
        (self.repo / "allowed").write_text(f"t@e.com {(key.with_suffix('.pub')).read_text()}")
        for k, v in (
            ("gpg.format", "ssh"),
            ("user.signingkey", str(key.with_suffix(".pub"))),
            ("commit.gpgsign", "true"),
            ("log.showSignature", "true"),
            ("gpg.ssh.allowedSignersFile", str(self.repo / "allowed")),
        ):
            self.git("config", k, v)

        # NOT self.commit(): that helper forces commit.gpgsign=false, so
        # nothing would be signed and the contamination would never appear.
        def signed(message, filename):
            (self.repo / filename).write_text("x")
            subprocess.run(["git", "add", filename], cwd=self.repo, check=True)
            r = subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=t@e.com",
                 "commit", "-q", "-m", message],
                cwd=self.repo, capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        signed(f"base\n\n{TRAILER}", "base.txt")
        self.run_hook("--host", "claude")
        signed("FEAT: charge customers, unchecked", "payments.py")
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")
        self.assertIn("charge customers", result.stderr)

    def test_a_nondefault_trailer_separators_config_does_not_blind_it(self):
        # The hook reads trailers with `%(trailers:key=...)`, which honours
        # the reader's own trailer.separators config — a repo configured
        # without ":" in that set would stop git recognizing "Bug-hunter: ..."
        # as a trailer at all, and a real, correctly-bound commit would read
        # as unchecked. Same failure shape as log.showSignature above: the
        # hook goes blind to its own signal, this time on the read side.
        self.settle()
        self.git("config", "trailer.separators", "=")
        try:
            self.commit_bound("FIX: real bug", "Bug-hunter: 1 iteration, 1 bug fixed")
            self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)
        finally:
            self.git("config", "--unset", "trailer.separators")

    def test_a_conflicted_rebase_is_reported(self):
        # Content that exists in no earlier commit, written by hand during
        # conflict resolution. The same case as the conflicted cherry-pick, and
        # far more common.
        self.settle()
        (self.repo / "auth.py").write_text("def check(t): return t == 'ok'\n")
        self.git("add", "auth.py")
        self.git("commit", "-q", "-m", f"base auth\n\n{TRAILER}")
        self.git("checkout", "-q", "-b", "feature")
        self.commit("FEAT: feature side, unchecked",
                    filename="auth.py", content="def check(t): return verify(t)\n")
        self.git("checkout", "-q", "main")
        self.commit(f"FEAT: main side\n\n{TRAILER}",
                    filename="auth.py", content="def check(t): return t in ALLOW\n")
        self.git("checkout", "-q", "feature")
        self.run_hook("--host", "claude")

        subprocess.run(["git", "rebase", "main"], cwd=self.repo, capture_output=True)
        (self.repo / "auth.py").write_text("def check(t): return NEVER_REVIEWED(t)\n")
        self.git("add", "auth.py")
        subprocess.run(
            ["git", "-c", "core.editor=true", "-c", "user.name=T",
             "-c", "user.email=t@e.com", "rebase", "--continue"],
            cwd=self.repo, capture_output=True,
        )
        self.assertEqual(self.run_hook("--host", "claude").returncode, REPORTED)

    def test_a_pretty_printed_payload_still_reads_the_first_cwd(self):
        # awk match() runs per line, so a multi-line payload with a nested cwd
        # printed both, the path became two lines, and the hook fell back to its
        # own cwd — the silent-wrong-repo failure again.
        other = pathlib.Path(tempfile.mkdtemp(prefix="other-")).resolve()
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=other, check=True)
        self.settle()
        self.commit("FEAT: unchecked here", filename="g.txt")

        payload = (
            '{\n  "cwd": "%s",\n  "tool_input": {\n    "cwd": "%s"\n  }\n}\n'
            % (self.repo, other)
        )
        result = subprocess.run(
            ["sh", str(HOOK), "--host", "claude"],
            input=payload, capture_output=True, text=True, cwd=other,
        )
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")

    def test_the_wrapped_trailer_note_explains_indenting(self):
        # An unindented continuation line also stops git reading a trailer, and
        # the diagnostic only mentioned blank lines — which led one agent to
        # conclude the trailer must never be wrapped at all.
        self.settle()
        self.commit(
            "FEAT: d\n\nBug-hunter: skipped at triage (docs only, no\nexecutable code)",
            filename="g.txt",
        )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("indent", result.stderr.lower())

    # -- verification pass: what inverting the list cost -------------------

    def test_a_rebase_that_preserves_merges_is_silent(self):
        # `git rebase -r` writes `rebase (merge):` and `rebase (reset):`, which
        # the inverted list did not exclude — so it named two recreated merge
        # commits (never reported by design) plus an already-reported tip of
        # main, listed twice.
        self.settle()
        self.commit(f"FEAT: base\n\n{TRAILER}", filename="base.txt")
        self.git("checkout", "-q", "-b", "topic")
        self.git("checkout", "-q", "-b", "f1")
        self.commit(f"FEAT: f1\n\n{TRAILER}", filename="f1.txt")
        self.git("checkout", "-q", "topic")
        self.git("merge", "--no-ff", "-q", "-m", "Merge f1", "f1")
        self.git("checkout", "-q", "main")
        self.commit(f"FEAT: main moved\n\n{TRAILER}", filename="m.txt")
        self.run_hook("--host", "claude")

        self.git("checkout", "-q", "topic")
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "rebase", "-r", "main"],
            cwd=self.repo, capture_output=True,
        )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, QUIET, result.stderr)



    def test_a_commit_then_leaving_the_branch_is_still_reported(self):
        # The case the cursor design was built for, and the one a reachability
        # filter silently swallows: the new commit is not reachable from the
        # final HEAD, and it is still exactly what this hook is for.
        self.settle()
        self.git("checkout", "-q", "-b", "side")
        self.commit("FEAT: unchecked work", filename="s.py")
        self.git("checkout", "-q", "main")
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")
        self.assertIn("unchecked work", result.stderr)

    def test_the_report_prescribes_nothing_when_the_commit_is_not_head(self):
        # The report names commits that are not HEAD — that is the case above,
        # and the central one. Any instruction to amend or re-commit acts on the
        # reader's HEAD instead, putting a trailer on an unrelated commit while
        # the reported one keeps none and, the cursor having advanced, is never
        # reported again. The report states facts; prose is a command too.
        self.settle()
        self.git("checkout", "-q", "-b", "side")
        self.commit("FEAT: unchecked work", filename="s.py")
        self.git("checkout", "-q", "main")
        stderr = self.run_hook("--host", "claude").stderr
        self.assertIn("unchecked work", stderr)
        for prescription in ("amend a trailer in", "re-commit with one",
                             "Put these right where they are"):
            self.assertNotIn(prescription, stderr)

    def test_a_commit_then_rebasing_it_away_is_still_reported(self):
        # Same shape via `git commit && git rebase main`: the original sha is
        # gone and its replayed twin arrives as `rebase (pick):`, so filtering
        # on reachability made this completely silent.
        self.settle()
        self.commit(f"FEAT: main moves\n\n{TRAILER}", filename="m.py")
        self.git("checkout", "-q", "-b", "side", "HEAD~1")
        self.commit("FEAT: unchecked side work", filename="s.py")
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "rebase", "main"],
            cwd=self.repo, capture_output=True,
        )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")

    def test_an_amend_elsewhere_does_not_swallow_an_unrelated_commit(self):
        # The amend-adjacency rule assumed "the entry before an amend is the
        # commit it amended". Excluded entries sit between them all the time, so
        # it landed on an unrelated commit and dropped it — silently.
        self.settle()
        for name in ("a", "b", "c", "d"):
            self.commit(f"FEAT: {name}\n\n{TRAILER}", filename=f"{name}.txt")
        self.run_hook("--host", "claude")

        (self.repo / "new.py").write_text("x")
        self.git("add", "new.py")
        self.git("commit", "-q", "-m", "FEAT: UNCHECKED brand new work")
        seq = self.repo / "seq.sh"
        seq.write_text('#!/bin/sh\nsed "2s/^pick/edit/" "$1" > "$1.n" && mv "$1.n" "$1"\n')
        seq.chmod(0o755)
        env = {**os.environ, "GIT_SEQUENCE_EDITOR": str(seq), "GIT_EDITOR": "true"}
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "rebase", "-i", "HEAD~3"],
            cwd=self.repo, capture_output=True, env=env,
        )
        (self.repo / "b.txt").write_text("tweak")
        self.git("add", "b.txt")
        self.git("commit", "-q", "--amend", "--no-edit")
        subprocess.run(
            ["git", "-c", "core.editor=true", "-c", "user.name=T",
             "-c", "user.email=t@e.com", "rebase", "--continue"],
            cwd=self.repo, capture_output=True, env=env,
        )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")
        self.assertIn("UNCHECKED brand new work", result.stderr)

    def test_an_interactive_rebase_does_not_re_report_replayed_commits(self):
        # `rebase (edit):` is a pure replay — git applies the commit unchanged
        # and stops — but it was not excluded, so already-reported commits came
        # back under new shas, with reset --soft advice fired mid-rebase on a
        # detached HEAD where following it corrupts the sequence.
        self.settle()
        for name in ("a", "b", "c", "d"):
            self.commit(f"FEAT: {name}", filename=f"{name}.txt")
        self.run_hook("--host", "claude")          # reported once, here

        seq = self.repo / "seq.sh"
        seq.write_text('#!/bin/sh\nsed "1,2s/^pick/edit/" "$1" > "$1.n" && mv "$1.n" "$1"\n')
        seq.chmod(0o755)
        env = {**os.environ, "GIT_SEQUENCE_EDITOR": str(seq), "GIT_EDITOR": "true"}
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "rebase", "-i", "HEAD~3"],
            cwd=self.repo, capture_output=True, env=env,
        )
        (self.repo / "b.txt").write_text("fix")
        self.git("add", "b.txt")
        self.git("commit", "-q", "--amend", "--no-edit")
        subprocess.run(
            ["git", "-c", "core.editor=true", "-c", "user.name=T",
             "-c", "user.email=t@e.com", "rebase", "--continue"],
            cwd=self.repo, capture_output=True, env=env,
        )
        subprocess.run(
            ["git", "-c", "core.editor=true", "-c", "user.name=T",
             "-c", "user.email=t@e.com", "rebase", "--continue"],
            cwd=self.repo, capture_output=True, env=env,
        )
        stderr = self.run_hook("--host", "claude").stderr
        self.assertNotIn("FEAT: c", stderr)
        self.assertNotIn("FEAT: d", stderr)

    def test_amending_a_merge_commit_is_not_reported(self):
        # A merge is never reported — reset --soft on one drops the second
        # parent. Tidying its message must not change that.
        self.settle()
        self.git("checkout", "-q", "-b", "side")
        self.commit(f"FEAT: side\n\n{TRAILER}", filename="s.txt")
        self.git("checkout", "-q", "main")
        self.commit(f"FEAT: main\n\n{TRAILER}", filename="m.txt")
        self.git("merge", "--no-ff", "-q", "-m", "Merge branch 'side'", "side")
        self.run_hook("--host", "claude")
        self.git("commit", "-q", "--amend", "-m", "Merge branch 'side' into main")
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, QUIET, result.stderr)

    def test_a_repo_with_no_reflog_says_so_once(self):
        # Silent-and-broken must not look like silent-and-fine. The fix is one
        # config command, so the user can be told rather than left guessing —
        # but only once, or it becomes the nagging that gets hooks uninstalled.
        self.settle()
        self.git("config", "core.logAllRefUpdates", "false")
        # The config alone is not enough: git keeps appending to a reflog file
        # that already exists, so the logs have to go too — which is the state a
        # bare repo, or one configured this way from the start, is actually in.
        shutil.rmtree(self.repo / ".git" / "logs", ignore_errors=True)
        self.commit("FEAT: unchecked", filename="g.py")

        first = self.run_hook("--host", "claude")
        self.assertEqual(first.returncode, REPORTED, first.stderr or "(silent)")
        self.assertIn("reflog", first.stderr.lower())
        self.assertIn("core.logAllRefUpdates", first.stderr)

        for _ in range(3):
            self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_the_no_reflog_notice_is_valid_json_for_cursor(self):
        self.settle()
        self.git("config", "core.logAllRefUpdates", "false")
        # The config alone is not enough: git keeps appending to a reflog file
        # that already exists, so the logs have to go too — which is the state a
        # bare repo, or one configured this way from the start, is actually in.
        shutil.rmtree(self.repo / ".git" / "logs", ignore_errors=True)
        self.commit("FEAT: unchecked", filename="g.py")
        result = self.run_hook("--host", "cursor")
        self.assertEqual(result.returncode, QUIET)
        self.assertIn("reflog", json.loads(result.stdout)["additional_context"])

    def test_a_commit_inside_a_submodule_is_reported(self):
        # A submodule is its own repository with its own HEAD, so a commit in
        # one moves a reflog the parent run never looks at.
        sub = pathlib.Path(tempfile.mkdtemp(prefix="submod-")).resolve()
        self.addCleanup(shutil.rmtree, sub, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=sub, check=True)
        (sub / "lib.py").write_text("x")
        subprocess.run(["git", "add", "lib.py"], cwd=sub, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m", f"seed\n\n{TRAILER}"],
            cwd=sub, check=True,
        )
        self.settle()
        self.git("-c", "protocol.file.allow=always", "submodule", "add", "-q",
                 str(sub), "vendor/lib")
        self.git("commit", "-q", "-m", f"CHORE: add submodule\n\n{TRAILER}")
        self.run_hook("--host", "claude")   # settle both repos

        inner = self.repo / "vendor" / "lib"
        (inner / "lib.py").write_text("unchecked change")
        subprocess.run(["git", "add", "lib.py"], cwd=inner, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m",
             "FEAT: unchecked work in the submodule"],
            cwd=inner, check=True,
        )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")
        self.assertIn("unchecked work in the submodule", result.stderr)

    def test_an_uninitialised_submodule_is_skipped_quietly(self):
        self.settle()
        (self.repo / ".gitmodules").write_text(
            '[submodule "vendor/lib"]\n\tpath = vendor/lib\n\turl = ../nowhere\n'
        )
        self.git("add", ".gitmodules")
        self.git("commit", "-q", "-m", f"CHORE: gitmodules\n\n{TRAILER}")
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    # -- the submodule walk, reviewed ------------------------------------

    def _submodule_repo(self, path="vendor/lib"):
        """A settled parent with an initialised submodule at `path`."""
        sub = pathlib.Path(tempfile.mkdtemp(prefix="submod-")).resolve()
        self.addCleanup(shutil.rmtree, sub, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=sub, check=True)
        (sub / "lib.py").write_text("x")
        subprocess.run(["git", "add", "lib.py"], cwd=sub, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m", f"seed\n\n{TRAILER}"],
            cwd=sub, check=True,
        )
        self.settle()
        self.git("-c", "protocol.file.allow=always", "submodule", "add", "-q",
                 str(sub), path)
        self.git("commit", "-q", "-m", f"CHORE: add submodule\n\n{TRAILER}")
        self.run_hook("--host", "claude")
        return self.repo / path

    def _submodule_gitdir(self, repo):
        """A submodule's .git is a file pointing at the real gitdir."""
        dot = repo / ".git"
        if dot.is_dir():
            return dot
        target = dot.read_text().split(":", 1)[1].strip()
        return (repo / target).resolve() if not target.startswith("/") else pathlib.Path(target)

    def _commit_in(self, repo, message, filename="lib.py", content="changed"):
        (repo / filename).write_text(content)
        subprocess.run(["git", "add", filename], cwd=repo, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m", message],
            cwd=repo, check=True,
        )

    def test_cursor_gets_exactly_one_json_object(self):
        # Cursor parses stdout as a single document. Two reporting repos meant
        # two objects, an unparseable payload, and the user seeing nothing — in
        # the case with the most to report.
        inner = self._submodule_repo()
        self._commit_in(inner, "FEAT: unchecked in submodule")
        self.commit("FEAT: unchecked in parent", filename="p.py")
        result = self.run_hook("--host", "cursor")
        json.loads(result.stdout)   # raises on the second object

    def test_a_submodule_path_with_a_space_is_checked(self):
        inner = self._submodule_repo(path="vendor/my lib")
        self._commit_in(inner, "FEAT: unchecked in the spaced submodule")
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")
        self.assertIn("spaced submodule", result.stderr)

    def test_a_gitmodules_path_escaping_the_repo_is_ignored(self):
        # .gitmodules is an ordinary tracked file in any repo you clone. A path
        # of `..` made the walk run the full check on the parent directory's
        # repository — writing state into it and printing its commit subjects.
        outer = pathlib.Path(tempfile.mkdtemp(prefix="outer-")).resolve()
        self.addCleanup(shutil.rmtree, outer, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=outer, check=True)
        (outer / "o.txt").write_text("secret")
        subprocess.run(["git", "add", "o.txt"], cwd=outer, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m",
             "OUTER work with no trailer"],
            cwd=outer, check=True,
        )
        inner = outer / "inner"
        inner.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=inner, check=True)
        (inner / ".gitmodules").write_text(
            '[submodule "up"]\n\tpath = ..\n\turl = ./\n'
        )
        subprocess.run(["git", "add", "."], cwd=inner, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m", f"inner\n\n{TRAILER}"],
            cwd=inner, check=True,
        )
        result = subprocess.run(
            ["sh", str(HOOK), "--host", "claude"],
            input=json.dumps({"cwd": str(inner)}), capture_output=True, text=True,
        )
        self.assertNotIn("OUTER work", result.stderr)
        self.assertFalse((outer / ".git" / "bug-hunter-head").exists())

    def test_the_walk_skips_submodules_that_have_not_moved(self):
        # The walk spawns a process per submodule on every command, not just on
        # commits. Skipping the ones whose reflog has not moved since their own
        # cursor makes the steady state nearly free.
        inner = self._submodule_repo()
        self.run_hook("--host", "claude")          # both settled

        # Timing would prove nothing here — the un-gated version is fast too.
        # The gate is observable directly: with an unchecked commit present but
        # the submodule's reflog older than its own cursor, the gate skips the
        # spawn and the run is silent. That is the mechanism, and its cost.
        gitdir = self._submodule_gitdir(inner)
        self._commit_in(inner, "FEAT: unchecked but the reflog looks old")
        old = time.time() - 3600
        os.utime(gitdir / "logs" / "HEAD", (old, old))
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

        # And the moment the reflog is genuinely newer, it reports again — the
        # gate is a skip decision, never a second source of truth.
        now = time.time()
        os.utime(gitdir / "logs" / "HEAD", (now, now))
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")
        self.assertIn("reflog looks old", result.stderr)

    def test_a_submodule_commit_is_reported_when_the_parent_never_moves(self):
        # The obvious gate — skip the walk unless the PARENT's reflog moved — is
        # wrong: committing inside a submodule does not move the parent's HEAD,
        # which is precisely the case the walk exists for.
        inner = self._submodule_repo()
        self.run_hook("--host", "claude")
        parent_head_before = self.git("rev-parse", "HEAD")

        self._commit_in(inner, "FEAT: submodule only, parent untouched")
        self.assertEqual(self.git("rev-parse", "HEAD"), parent_head_before)

        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")
        self.assertIn("parent untouched", result.stderr)

    def test_a_nested_submodule_is_reached_when_its_parent_has_not_moved(self):
        # The gate decides whether to spawn for A by looking at A — but that
        # spawn is the only thing that ever walks A's own submodules. The gate's
        # own comment says gating on a parent's reflog is wrong for exactly this
        # reason; this is that mistake, one level down.
        grand = pathlib.Path(tempfile.mkdtemp(prefix="grand-")).resolve()
        self.addCleanup(shutil.rmtree, grand, ignore_errors=True)
        mid = pathlib.Path(tempfile.mkdtemp(prefix="mid-")).resolve()
        self.addCleanup(shutil.rmtree, mid, ignore_errors=True)

        def seed(repo, name):
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            (repo / f"{name}.py").write_text("x")
            subprocess.run(["git", "add", f"{name}.py"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
                 "-c", "commit.gpgsign=false", "commit", "-q", "-m", f"seed\n\n{TRAILER}"],
                cwd=repo, check=True,
            )

        def gitc(repo, *a):
            r = subprocess.run(
                ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
                 "-c", "commit.gpgsign=false", "-c", "protocol.file.allow=always", *a],
                cwd=repo, capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        seed(grand, "g")
        seed(mid, "m")
        gitc(mid, "submodule", "add", "-q", str(grand), "inner")
        gitc(mid, "commit", "-q", "-m", f"CHORE: nest\n\n{TRAILER}")

        self.settle()
        gitc(self.repo, "submodule", "add", "-q", str(mid), "vendor/a")
        gitc(self.repo, "commit", "-q", "-m", f"CHORE: vendor\n\n{TRAILER}")
        gitc(self.repo, "submodule", "update", "--init", "--recursive")
        self.run_hook("--host", "claude")
        self.run_hook("--host", "claude")   # settle every level

        inner = self.repo / "vendor" / "a" / "inner"
        (inner / "g.py").write_text("code nobody reviewed")
        gitc(inner, "add", "g.py")
        gitc(inner, "commit", "-q", "-m", "FEAT: UNCHECKED in the nested submodule")

        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")
        self.assertIn("nested submodule", result.stderr)

    def test_an_unusable_tmpdir_stays_silent_and_quiet(self):
        # A vanished TMPDIR is routine on macOS: /var/folders/…/T is purged
        # while an exported TMPDIR in a running session still points at it.
        self.settle()
        self.commit("FEAT: unchecked", filename="g.py")
        result = subprocess.run(
            ["sh", str(HOOK), "--host", "claude"],
            input=json.dumps({"cwd": str(self.repo)}),
            capture_output=True, text=True,
            env={**os.environ, "TMPDIR": "/var/folders/zz/definitely-gone-12345/T"},
        )
        self.assertNotIn("No such file", result.stderr)
        # Nothing could be delivered, so nothing should be blocked on.
        self.assertEqual(result.returncode, QUIET, result.stderr)

    def test_a_tab_in_a_subject_keeps_the_cursor_payload_valid(self):
        self.settle()
        (self.repo / "g.py").write_text("x")
        self.git("add", "g.py")
        self.git("commit", "-q", "-m", "FEAT:\tadd\ttabbed thing")
        result = self.run_hook("--host", "cursor")
        json.loads(result.stdout)   # invalid control character otherwise

    def test_it_never_removes_dev_null(self):
        # A tracked but empty .gitmodules is what `git rm` of the last submodule
        # leaves behind. A sentinel of subs_file=/dev/null then reached
        # `rm -f /dev/null` — harmless as a normal user on macOS, and as root on
        # Linux (routine in agent containers) it unlinks /dev/null, after which
        # every 2>/dev/null in every process creates a regular file.
        self.settle()
        (self.repo / ".gitmodules").write_text("")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"CHORE: empty gitmodules\n\n{TRAILER}")
        trace = subprocess.run(
            ["sh", "-x", str(HOOK), "--host", "claude"],
            input=json.dumps({"cwd": str(self.repo)}),
            capture_output=True, text=True,
        )
        self.assertNotIn("rm -f /dev/null", trace.stderr)
        self.assertNotIn("subs_file=/dev/null", trace.stderr)

    def test_an_unusable_buffer_does_not_advance_the_cursor(self):
        # The cursor is written before the report is emitted, so a dead buffer
        # would mark the commits seen and lose the report permanently. With
        # nothing able to speak, the run must do nothing at all.
        self.settle()
        self.commit("FEAT: unchecked", filename="g.py")
        before = self.state_file.read_text()
        subprocess.run(
            ["sh", str(HOOK), "--host", "claude"],
            input=json.dumps({"cwd": str(self.repo)}),
            capture_output=True, text=True,
            env={**os.environ, "TMPDIR": "/var/folders/zz/definitely-gone-99999/T"},
        )
        self.assertEqual(self.state_file.read_text(), before, "cursor advanced")
        # And with a working TMPDIR the report is still there to be made.
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")

    def test_an_unusable_tmpdir_is_quiet_under_dash(self):
        # `:` is a POSIX *special built-in*: a redirection failure on one aborts
        # a non-interactive shell outright, `||` and all. Under dash — /bin/sh on
        # Debian and Ubuntu, so most Linux agent sandboxes — that killed the
        # script before the guard written for this case could run, leaving a
        # blocking exit 2 with zero bytes on every command.
        dash = shutil.which("dash")
        if not dash:
            self.skipTest("dash not installed")
        self.settle()
        self.commit("FEAT: unchecked", filename="g.py")
        result = subprocess.run(
            [dash, str(HOOK), "--host", "claude"],
            input=json.dumps({"cwd": str(self.repo)}),
            capture_output=True, text=True,
            env={**os.environ, "TMPDIR": "/var/tmp/definitely-gone-54321"},
        )
        self.assertEqual(result.returncode, QUIET,
                         f"rc={result.returncode} err={result.stderr!r}")
        self.assertEqual(result.stderr, "")

    def test_a_non_utf8_subject_does_not_swallow_the_report(self):
        # .git/logs/HEAD holds the message bytes raw, and macOS awk treats an
        # invalid byte as fatal under a UTF-8 locale — truncating the reflog
        # list at that record while the cursor has already advanced, so the
        # commit is never revisited.
        self.settle()
        msg = self.repo / "m.txt"
        msg.write_bytes(b"FEAT: g\xe8re les paiements NEVER CHECKED\n")
        (self.repo / "pay.py").write_text("x")
        self.git("add", "pay.py")
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-F", str(msg)],
            cwd=self.repo, capture_output=True,
        )
        result = subprocess.run(
            ["sh", str(HOOK), "--host", "claude"],
            input=json.dumps({"cwd": str(self.repo)}),
            capture_output=True, text=True, errors="replace",
            env={**os.environ, "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"},
        )
        self.assertNotIn("multibyte", result.stderr)
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")

    def test_a_gitmodules_listing_nothing_live_does_not_force_a_spawn(self):
        # `git submodule update --init` without --recursive is the default flow
        # and leaves a .gitmodules listing a path that was never initialised.
        # Exempting on the file's mere presence meant a process per command
        # forever, which could never find anything.
        inner = self._submodule_repo()
        # A .gitmodules inside the submodule naming something uninitialised.
        (inner / ".gitmodules").write_text(
            '[submodule "nested"]\n\tpath = nested\n\turl = ../nowhere\n'
        )
        subprocess.run(["git", "add", ".gitmodules"], cwd=inner, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m",
             f"CHORE: gitmodules\n\n{TRAILER}"],
            cwd=inner, check=True,
        )
        self.run_hook("--host", "claude")
        self.run_hook("--host", "claude")   # settle every level

        trace = subprocess.run(
            ["sh", "-x", str(HOOK), "--host", "claude"],
            input=json.dumps({"cwd": str(self.repo)}),
            capture_output=True, text=True,
        )
        spawns = trace.stderr.count("BUG_HUNTER_DEPTH=1")
        self.assertEqual(spawns, 0, f"spawned {spawns}x for an empty tree")

    def test_a_live_nested_submodule_still_forces_a_spawn(self):
        # The exemption must survive for the case it was added for: a real
        # nested submodule, whose commits are only reachable through its parent.
        inner = self._submodule_repo()
        grand = pathlib.Path(tempfile.mkdtemp(prefix="grand2-")).resolve()
        self.addCleanup(shutil.rmtree, grand, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=grand, check=True)
        (grand / "g.py").write_text("x")
        subprocess.run(["git", "add", "g.py"], cwd=grand, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m", f"seed\n\n{TRAILER}"],
            cwd=grand, check=True,
        )
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "-c", "protocol.file.allow=always",
             "submodule", "add", "-q", str(grand), "nested"],
            cwd=inner, check=True,
        )
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m",
             f"CHORE: nest\n\n{TRAILER}"],
            cwd=inner, check=True,
        )
        self.run_hook("--host", "claude")
        self.run_hook("--host", "claude")

        deep = inner / "nested"
        (deep / "g.py").write_text("unchecked")
        subprocess.run(["git", "add", "g.py"], cwd=deep, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m",
             "FEAT: UNCHECKED deep in the tree"],
            cwd=deep, check=True,
        )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")
        self.assertIn("deep in the tree", result.stderr)



    def test_a_nested_submodule_path_with_a_space_counts_as_live(self):
        # The liveness check word-split .gitmodules paths, unlike the parent
        # walk seventy lines above it, so a nested submodule at `deep dir` read
        # as not live — and the parent spawn was skipped when only that nested
        # repo had moved.
        inner = self._submodule_repo()
        grand = pathlib.Path(tempfile.mkdtemp(prefix="grand3-")).resolve()
        self.addCleanup(shutil.rmtree, grand, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=grand, check=True)
        (grand / "g.py").write_text("x")
        subprocess.run(["git", "add", "g.py"], cwd=grand, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m", f"seed\n\n{TRAILER}"],
            cwd=grand, check=True,
        )
        for args in (["submodule", "add", "-q", str(grand), "deep dir"],
                     ["commit", "-q", "-m", f"CHORE: nest\n\n{TRAILER}"]):
            r = subprocess.run(
                ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
                 "-c", "commit.gpgsign=false", "-c", "protocol.file.allow=always", *args],
                cwd=inner, capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.run_hook("--host", "claude")
        self.run_hook("--host", "claude")

        deep = inner / "deep dir"
        (deep / "g.py").write_text("unchecked")
        subprocess.run(["git", "add", "g.py"], cwd=deep, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m",
             "FEAT: UNCHECKED in the spaced nested submodule"],
            cwd=deep, check=True,
        )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")
        self.assertIn("spaced nested submodule", result.stderr)


    def test_a_submodule_commit_names_its_repository(self):
        inner = self._submodule_repo()
        self._commit_in(inner, "FEAT: submodule work, no trailer")
        stderr = self.run_hook("--host", "claude").stderr
        self.assertIn("vendor/lib", stderr, "report does not say which repo")


    def test_a_submodule_named_with_a_path_token_is_still_checked(self):
        # `${line#*.path }` strips to the FIRST `.path `, so a submodule whose
        # NAME contains it yields a mangled path and is never checked.
        src = pathlib.Path(tempfile.mkdtemp(prefix="oddname-")).resolve()
        self.addCleanup(shutil.rmtree, src, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=src, check=True)
        (src / "s.py").write_text("x")
        subprocess.run(["git", "add", "s.py"], cwd=src, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m", f"seed\n\n{TRAILER}"],
            cwd=src, check=True,
        )
        self.settle()
        self.git("-c", "protocol.file.allow=always", "submodule", "add", "-q",
                 "--name", "v2.path lib", str(src), "vendor/lib")
        self.git("commit", "-q", "-m", f"CHORE: add\n\n{TRAILER}")
        self.run_hook("--host", "claude")

        inner = self.repo / "vendor" / "lib"
        self._commit_in(inner, "SUB: unchecked work", filename="s.py")
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")
        self.assertIn("SUB: unchecked work", result.stderr)

    def test_a_nested_submodule_named_with_a_path_token_is_reached(self):
        # Covers the liveness check's own parse, which the parent-walk test does
        # not touch: reverting that parse alone broke no test at all.
        def seed(repo, name):
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            (repo / f"{name}.py").write_text("x")
            subprocess.run(["git", "add", f"{name}.py"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
                 "-c", "commit.gpgsign=false", "commit", "-q", "-m", f"seed\n\n{TRAILER}"],
                cwd=repo, check=True,
            )

        def gitc(repo, *a):
            r = subprocess.run(
                ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
                 "-c", "commit.gpgsign=false", "-c", "protocol.file.allow=always", *a],
                cwd=repo, capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        grand = pathlib.Path(tempfile.mkdtemp(prefix="deepname-")).resolve()
        mid = pathlib.Path(tempfile.mkdtemp(prefix="midname-")).resolve()
        for d in (grand, mid):
            self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        seed(grand, "g")
        seed(mid, "m")
        # The awkward name is on the NESTED submodule, inside `mid`.
        gitc(mid, "submodule", "add", "-q", "--name", "weird.path name",
             str(grand), "inner")
        gitc(mid, "commit", "-q", "-m", f"CHORE: nest\n\n{TRAILER}")

        self.settle()
        gitc(self.repo, "submodule", "add", "-q", str(mid), "vendor/a")
        gitc(self.repo, "commit", "-q", "-m", f"CHORE: vendor\n\n{TRAILER}")
        gitc(self.repo, "submodule", "update", "--init", "--recursive")
        self.run_hook("--host", "claude")
        self.run_hook("--host", "claude")

        deep = self.repo / "vendor" / "a" / "inner"
        (deep / "g.py").write_text("unchecked")
        gitc(deep, "add", "g.py")
        gitc(deep, "commit", "-q", "-m", "FEAT: UNCHECKED in the oddly named nest")

        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")
        self.assertIn("oddly named nest", result.stderr)


    def test_a_valueless_gitmodules_key_does_not_hide_later_submodules(self):
        # `git config -z` emits `key\0` for a valueless key — one line, not two —
        # which desynchronises a strict pair read for every entry after it.
        inner = self._submodule_repo()
        gm = self.repo / ".gitmodules"
        gm.write_text('[submodule "ghost"]\n\tpath\n' + gm.read_text())
        self.git("add", ".gitmodules")
        self.git("commit", "-q", "-m", f"CHORE: ghost\n\n{TRAILER}")
        self.run_hook("--host", "claude")

        self._commit_in(inner, "FEAT: unchecked behind the ghost")
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")
        self.assertIn("behind the ghost", result.stderr)

    def test_a_root_commit_is_not_told_to_reset_to_a_parent(self):
        # The first commit in a repo has no HEAD~1.
        (self.repo / "first.py").write_text("x")
        self.git("add", "first.py")
        self.git("commit", "-q", "-m", "FEAT: first ever commit")
        self.run_hook("--host", "claude")   # baseline
        (self.repo / "second.py").write_text("x")
        self.git("add", "second.py")
        self.git("commit", "-q", "-m", "FEAT: second")
        self.git("reset", "-q", "--hard", "HEAD~1")   # back to the root commit
        subprocess.run(["git", "reflog", "expire", "--expire=now", "--all"],
                       cwd=self.repo, capture_output=True)
        shutil.rmtree(self.repo / ".git" / "bug-hunter-head", ignore_errors=True)
        (self.repo / ".git" / "bug-hunter-head").unlink(missing_ok=True)
        result = self.run_hook("--host", "claude")
        if result.returncode == REPORTED:
            self.assertNotIn("reset --soft HEAD~1", result.stderr)


    def test_the_misplaced_trailer_note_survives_the_cursor_channel(self):
        self.settle()
        self.commit(
            "FEAT: d\n\nBug-hunter: 1 iteration\n\nmore body", filename="g.py")
        result = self.run_hook("--host", "cursor")
        ctx = json.loads(result.stdout)["additional_context"]
        if "git commit" in ctx:
            self.assertNotIn('-m  ', ctx, "double quotes stripped out of the example")
        # The cursor channel replaces every `"` and `\` with a space, so the
        # example command has to be quoted and laid out so that it survives.
        self.assertIn("commit-with-trailer.sh -F msg.txt '1 iteration, 1 bug fixed'", ctx)

    def test_the_misplaced_trailer_note_points_at_the_commit_script(self):
        # The note used to show a hand-typed `git commit -m ... --trailer ...`
        # as the way to do it — the same assembly step that produced the
        # misplaced line, so an agent acting on the report did it again by
        # hand. The report names the script that does the assembly instead,
        # and shows no hand-built git commit at all.
        self.settle()
        self.commit("FEAT: d\n\nBug-hunter: 1 iteration\n\nmore body", filename="g.py")
        stderr = self.run_hook("--host", "claude").stderr
        self.assertIn("commit-with-trailer.sh", stderr)
        self.assertNotIn("git commit -m", stderr)

    def test_every_report_names_the_commit_script_under_both_install_targets(self):
        # A commit with no trailer at all is the other way to arrive here, and
        # the closing guidance is the one paragraph every report carries. Both
        # install targets are named because a real install may populate only
        # one (../DECISIONS.md, the two-target fallback entry).
        self.settle()
        self.commit("FEAT: x", filename="g.txt")
        stderr = self.run_hook("--host", "claude").stderr
        self.assertIn("commit-with-trailer.sh", stderr)
        self.assertIn("~/.agents/skills/bug-hunter/scripts/", stderr)
        self.assertIn("~/.claude/skills/bug-hunter/scripts/", stderr)



    def test_a_key_shaped_directory_is_not_walked_as_a_submodule(self):
        # submodule "a"'s own path value, "submodule.b.path", is shaped like a
        # config key. The rejected disambiguation tested such a line by asking
        # whether it resolves to a real directory with a .git — which this one
        # does, so a repo living at exactly that path got walked and reported.
        # Do not "fix" this by renaming the directory: the value the parser
        # actually emits here is "submodule.b.path" (see get-regexp above), so
        # that is the one name this test can discriminate on. A stray
        # directory named after a *different* submodule's key (e.g.
        # "submodule.c.path", from a submodule with no path key at all) never
        # reaches the disambiguation branch — it isn't emitted by
        # --get-regexp in the first place, and the test would pass against
        # either implementation without exercising anything.
        self.settle()
        (self.repo / ".gitmodules").write_text(
            '[submodule "a"]\n\tpath = submodule.b.path\n'
            '[submodule "c"]\n\turl = ../x\n')
        stray = self.repo / "submodule.b.path"
        stray.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=stray, check=True)
        (stray / "n.py").write_text("x")
        subprocess.run(["git", "add", "n.py"], cwd=stray, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m", "NESTED-NOT-A-SUBMODULE"],
            cwd=stray, check=True)
        self.git("add", ".gitmodules")
        self.git("commit", "-q", "-m", f"CHORE: gm\n\n{TRAILER}")
        result = self.run_hook("--host", "claude")
        self.assertNotIn("NESTED-NOT-A-SUBMODULE", result.stderr)




    def test_every_report_names_the_repository_and_the_shas(self):
        # Whatever else is dropped, the facts stay.
        self.settle()
        self.git("checkout", "-q", "-b", "side")
        sha = self.commit("FEAT: elsewhere", filename="s.py")[:7]
        self.git("checkout", "-q", "main")
        stderr = self.run_hook("--host", "claude").stderr
        self.assertIn(sha, stderr)
        self.assertIn(str(self.repo), stderr)

    def test_a_symlinked_submodule_pointing_outside_is_ignored(self):
        # The string guard catches `..` and absolute paths but cannot see
        # through a symlink, and a tracked symlink plus a matching .gitmodules
        # is ordinary content in any repo you clone.
        victim = pathlib.Path(tempfile.mkdtemp(prefix="victim-")).resolve()
        self.addCleanup(shutil.rmtree, victim, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=victim, check=True)
        (victim / "s.txt").write_text("s")
        subprocess.run(["git", "add", "s.txt"], cwd=victim, check=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
             "-c", "commit.gpgsign=false", "commit", "-q", "-m",
             "SECRET: internal victim repo commit subject"],
            cwd=victim, check=True,
        )
        self.settle()
        (self.repo / "vendor").mkdir()
        (self.repo / "vendor" / "lib").symlink_to(victim)
        (self.repo / ".gitmodules").write_text(
            '[submodule "lib"]\n\tpath = vendor/lib\n\turl = ./x\n'
        )
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"CHORE: vendor\n\n{TRAILER}")

        result = self.run_hook("--host", "claude")
        self.assertNotIn("SECRET", result.stderr)
        self.assertFalse((victim / ".git" / "bug-hunter-head").exists())

    def test_a_relative_script_path_does_not_leak_a_shell_error(self):
        inner = self._submodule_repo()
        self._commit_in(inner, "FEAT: unchecked in submodule")
        result = subprocess.run(
            ["sh", HOOK.name, "--host", "claude"],
            input=json.dumps({"cwd": str(self.repo)}),
            capture_output=True, text=True, cwd=str(HOOK.parent),
        )
        self.assertNotIn("No such file", result.stderr)

    def test_a_junk_depth_variable_is_treated_as_zero(self):
        inner = self._submodule_repo()
        self._commit_in(inner, "FEAT: unchecked in submodule")
        result = subprocess.run(
            ["sh", str(HOOK), "--host", "claude"],
            input=json.dumps({"cwd": str(self.repo)}),
            capture_output=True, text=True,
            env={**os.environ, "BUG_HUNTER_DEPTH": "abc"},
        )
        self.assertNotIn("integer expression", result.stderr)
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")

    def test_expiring_a_reflog_does_not_trigger_the_no_reflog_notice(self):
        # `git reflog expire` empties the reflog of a repo whose reflogs are
        # enabled. The notice then advises turning on something already on —
        # and burns the once-per-repository marker, so the genuine case would
        # later go silent with no notice at all.
        self.settle()
        subprocess.run(
            ["git", "reflog", "expire", "--expire=now",
             "--expire-unreachable=now", "--all"],
            cwd=self.repo, capture_output=True,
        )
        result = self.run_hook("--host", "claude")
        self.assertNotIn("keeps no reflog", result.stderr)
        self.assertFalse((self.repo / ".git" / "bug-hunter-noreflog").exists())

    def test_a_commit_after_an_expiry_that_restores_the_count_is_reported(self):
        # The cursor is a count, and `count == last` short-circuits before the
        # shrink fallback. An expiry that drops as many entries as were added
        # lands back on the stored value with real work in between.
        self.settle()
        subprocess.run(
            ["git", "reflog", "expire", "--expire=now",
             "--expire-unreachable=now", "--all"],
            cwd=self.repo, capture_output=True,
        )
        self.commit("FEAT: charge customers, NEVER CHECKED", filename="pay.py")
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED, result.stderr or "(silent)")
        self.assertIn("NEVER CHECKED", result.stderr)

    # -- degrading quietly -------------------------------------------------

    def test_a_state_file_it_cannot_write_stays_silent(self):
        # Without a memory it cannot report once, and repeating the same
        # complaint on every command for the rest of the session is worse than
        # missing it. It must also not leak a raw shell error.
        self.settle()
        self.commit("FEAT: x", filename="g.txt")
        self.state_file.chmod(0o444)
        self.state_file.parent.chmod(0o555)
        self.addCleanup(self.state_file.parent.chmod, 0o755)

        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, QUIET)
        self.assertNotIn("Permission denied", result.stderr)

    def test_concurrent_invocations_report_once(self):
        self.settle()
        self.commit("FEAT: x", filename="g.txt")
        payload = json.dumps({"cwd": str(self.repo)})
        procs = [
            subprocess.Popen(
                ["sh", str(HOOK), "--host", "claude"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(4)
        ]
        reported = sum(1 for p in procs if p.communicate(payload) and p.returncode == REPORTED)
        self.assertEqual(reported, 1)

    def test_the_script_is_executable(self):
        self.assertTrue(HOOK.stat().st_mode & 0o111, f"{HOOK} lost its exec bit")

    # -- ④ a non-skip trailer must be minted, not recalled -----------------
    #
    # The gap this closes: an honest fix, with a real red-then-green test,
    # made entirely outside this skill, then given a trailer that pattern-
    # matches the shape this file documents. The trailer parses; the words
    # are right; nothing was ever delegated. Scoped to every trailer except
    # a skip — not only ones claiming a fix — because the first draft of
    # this scoped to "N bugs fixed" and left a one-word bypass: write
    # "0 bugs found" instead and the same fabrication sails through. See
    # ../../../lib/commit-trailer/DECISIONS.md#the-trailer-is-minted-from-the-tree-not-recalled-by-the-agent.

    def test_the_mint_script_is_executable(self):
        self.assertTrue(MINT.stat().st_mode & 0o111, f"{MINT} lost its exec bit")

    def test_mint_trailer_matches_write_tree(self):
        (self.repo / "a.txt").write_text("x")
        self.git("add", "a.txt")
        expected = f"Bug-hunter-Tree: {self.git('write-tree')}"
        self.assertEqual(self.mint(), expected)

    def test_mint_trailer_fails_outside_a_git_repo(self):
        outside = pathlib.Path(tempfile.mkdtemp(prefix="not-a-repo-")).resolve()
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        result = subprocess.run(
            ["sh", str(MINT)], cwd=outside, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_mint_trailer_does_not_leak_stderr_into_a_successful_binding(self):
        # git write-tree was captured with 2>&1, so anything git prints on
        # stderr while still exiting 0 — GIT_TRACE=1, a stale core.fsmonitor
        # hook — landed ahead of the hash in the minted value. Proven against
        # a git shim that is noisy on write-tree and still succeeds, since
        # nothing here reliably makes the real git noisy on demand.
        (self.repo / "a.txt").write_text("x")
        self.git("add", "a.txt")
        expected_hash = self.git("write-tree")
        shim = pathlib.Path(tempfile.mkdtemp(prefix="bh-git-shim-")).resolve()
        self.addCleanup(shutil.rmtree, shim, ignore_errors=True)
        real_git = shutil.which("git")
        (shim / "git").write_text(
            "#!/bin/sh\n"
            'case " $* " in *" write-tree "*) '
            'echo "hint: use --reflog to find unreachable objects" >&2 ;; esac\n'
            f'exec "{real_git}" "$@"\n')
        (shim / "git").chmod(0o755)
        result = subprocess.run(
            ["sh", str(MINT)], cwd=self.repo, capture_output=True, text=True,
            env={**os.environ, "PATH": f"{shim}:{os.environ['PATH']}"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"Bug-hunter-Tree: {expected_hash}\n")

    def test_a_fix_trailer_with_a_matching_binding_is_checked(self):
        self.settle()
        self.commit_bound("FIX: real bug", "Bug-hunter: 1 iteration, 1 bug fixed")
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_a_fix_trailer_with_no_binding_at_all_is_reported(self):
        # The exact shape of the real incident: the wording is right, the
        # trailer is a real git trailer, and nothing backs it. Suppressing
        # the test file's own auto-mint is the point here — this is the one
        # case meant to reproduce the fabrication, not to avoid it.
        self.settle()
        with self.no_auto_mint():
            self.commit(
                "FIX: real bug\n\nBug-hunter: 1 iteration, 1 bug fixed",
                filename="g.txt",
            )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("Bug-hunter-Tree", result.stderr)
        self.assertIn("mint-trailer.sh", result.stderr)
        # ...and the thing that runs it, which is what to reach for.
        self.assertIn("commit-with-trailer.sh", result.stderr)
        # Distinguishable from "no trailer at all" — a different problem with
        # a different fix.
        self.assertNotIn("landed without being checked", result.stderr)

    def test_a_fix_trailer_with_a_stale_binding_is_reported(self):
        # Minted against one tree, then more was staged before the commit —
        # or the trailer was copied from an earlier, different run.
        self.settle()
        stale = self.mint()
        self.commit_bound(
            "FIX: real bug", "Bug-hunter: 1 iteration, 1 bug fixed",
            tree_override=stale,
        )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("Bug-hunter-Tree", result.stderr)

    def test_a_zero_bugs_found_trailer_with_no_binding_is_reported(self):
        # The loophole the first draft of this feature left open: scoping the
        # requirement to trailers that claim a fix meant an agent that never
        # ran anything could stay silent just by writing "0 bugs found"
        # instead of "1 bug fixed" — a smaller lie for a bigger bypass. A
        # trailer that says the loop ran over this tree needs the same
        # binding regardless of what it says it found.
        self.settle()
        with self.no_auto_mint():
            self.commit(f"FEAT: x\n\n{TRAILER}", filename="g.txt")
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("Bug-hunter-Tree", result.stderr)

    def test_a_zero_bugs_found_trailer_with_a_matching_binding_is_checked(self):
        self.settle()
        self.commit(f"FEAT: x\n\n{TRAILER}", filename="g.txt")
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_a_skipped_trailer_needs_no_binding_even_if_worded_like_a_fix(self):
        # Triage stopped before any loop ran, so there is no tree for a
        # binding to attest to — the one shape genuinely exempt.
        self.settle()
        with self.no_auto_mint():
            self.commit(
                "FEAT: x\n\nBug-hunter: skipped at triage (1 bug fixed "
                "manually earlier, nothing to review here)",
                filename="g.txt",
            )
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_an_aborted_trailer_with_no_binding_is_reported(self):
        # An aborted run still means the loop ran over this tree three times
        # — that is a claim about this tree, same as "0 bugs found" is.
        self.settle()
        with self.no_auto_mint():
            self.commit(
                "FEAT: x\n\nBug-hunter: 3 iterations, aborted — see report",
                filename="g.txt",
            )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("Bug-hunter-Tree", result.stderr)

    def test_an_aborted_trailer_with_a_matching_binding_is_checked(self):
        self.settle()
        self.commit(
            "FEAT: x\n\nBug-hunter: 3 iterations, aborted — see report",
            filename="g.txt",
        )
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_a_cherry_picked_fix_trailer_is_not_required_to_rebind(self):
        # A clean cherry-pick copies the message — trailer and stale binding
        # both — onto a different tree. That is a legitimate, already-tested
        # shape (test_a_cherry_pick_is_reported); the mint check must not turn
        # it into a new false alarm. Confirmed empirically that a clean
        # cherry-pick's reflog action is `cherry-pick:`, never `commit:`.
        self.settle()
        self.git("checkout", "-q", "-b", "side")
        self.commit_bound(
            "FIX: on the side", "Bug-hunter: 1 iteration, 1 bug fixed",
            filename="s.txt",
        )
        picked = self.git("rev-parse", "HEAD")
        self.run_hook("--host", "claude")
        self.git("checkout", "-q", "main")
        self.run_hook("--host", "claude")

        self.git("cherry-pick", picked)
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, QUIET, result.stderr or "(silent)")

    def test_amending_the_message_only_keeps_a_valid_binding(self):
        # Repairing trailer placement, or adding a Co-Authored-By, touches no
        # file — the tree is unchanged and the binding still matches.
        self.settle()
        self.commit_bound("FIX: real bug", "Bug-hunter: 1 iteration, 1 bug fixed")
        self.git("commit", "--amend", "-q", "--no-edit",
                  "--trailer", "Co-Authored-By: Someone <someone@example.com>")
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_amending_in_a_new_file_after_minting_is_reported(self):
        # The binding was good for the tree it was minted against; amending in
        # more content afterward changes the tree without changing the
        # trailer, and that drift is exactly what this is for.
        self.settle()
        self.commit_bound("FIX: real bug", "Bug-hunter: 1 iteration, 1 bug fixed")
        (self.repo / "extra.py").write_text("unreviewed\n")
        self.git("add", "extra.py")
        self.git("commit", "--amend", "-q", "--no-edit")
        self.assertEqual(self.run_hook("--host", "claude").returncode, REPORTED)

    def test_a_root_commit_with_a_fabricated_trailer_is_reported(self):
        # `commit (initial):` is a root commit's own reflog action, distinct
        # from `commit:` — confirmed against a real repro, not inferred. It
        # was missing from the action list entirely: a repository's very
        # first commit could carry a fabricated trailer and stay silent
        # forever, until some unrelated later amend of it suddenly reported
        # the byte-identical trailer that had been silent all along.
        with self.no_auto_mint():
            self.commit(f"FEAT: entire project\n\n{TRAILER}", filename="app.py")
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("Bug-hunter-Tree", result.stderr)

    def test_amending_a_cherry_picked_commits_message_still_needs_no_rebind(self):
        # Amending only the message of a cherry-picked commit rewrites its
        # reflog action to `commit (amend):`, even though the tree — and so
        # the binding it carries — never changed. By the time that amend
        # happens the hook has typically already run once on the pick itself
        # (correctly silent) and moved the cursor past it, so recognising
        # this case has to search the whole reflog, not just the current
        # window — confirmed against a real repro: a window-scoped version of
        # this same check still reported this exact honest sequence.
        self.settle()
        self.git("checkout", "-q", "-b", "side")
        self.commit_bound(
            "FIX: on the side", "Bug-hunter: 1 iteration, 1 bug fixed",
            filename="s.txt",
        )
        picked = self.git("rev-parse", "HEAD")
        self.run_hook("--host", "claude")
        self.git("checkout", "-q", "main")
        self.commit("unrelated on main", filename="other.txt")
        self.run_hook("--host", "claude")

        self.git("cherry-pick", picked)
        self.run_hook("--host", "claude")  # exempt via cherry-pick:, moves the cursor past it

        message = self.git("log", "-1", "--format=%B").replace(
            "on the side", "on the side!!!", 1
        )
        self.git("commit", "--amend", "-q", "-m", message)
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, QUIET, result.stderr or "(silent)")

    def test_multiple_bug_hunter_tree_trailers_take_the_last_one(self):
        # `--trailer`'s default (addIfDifferentNeighbor) appends rather than
        # replaces, so repairing a wrong binding by minting again and passing
        # --trailer a second time produces two Bug-hunter-Tree lines, not
        # one. Concatenating both, as an earlier version did, produced an
        # 80-hex-character string that could never equal a real tree — the
        # amend-based repair README.md itself documents was a no-op. Taking
        # the last logical value instead matches what a second --trailer
        # actually means here: a correction.
        self.settle()
        self.commit_bound(
            "FIX: thing", "Bug-hunter: 1 iteration, 1 bug fixed",
            tree_override="Bug-hunter-Tree: " + "0" * 40,
        )
        self.assertEqual(self.run_hook("--host", "claude").returncode, REPORTED)

        correct_tree = self.git("write-tree")
        self.git("commit", "--amend", "-q", "--trailer", f"Bug-hunter-Tree: {correct_tree}")
        self.assertEqual(
            self.git("log", "-1", "--format=%B").count("Bug-hunter-Tree:"), 2
        )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, QUIET, result.stderr or "(silent)")

    def test_a_correct_binding_followed_by_a_bad_one_is_still_reported(self):
        # Last-wins cuts both ways: a real mint followed by an unrelated,
        # hand-typed second Bug-hunter-Tree line must not be shadowed by the
        # good one that happened to come first.
        self.settle()
        (self.repo / "g.txt").write_text("x")
        self.git("add", "g.txt")
        good = self.mint()
        message = f"FIX: thing\n\nBug-hunter: 1 iteration, 1 bug fixed\n{good}"
        self.git("commit", "-q", "-m", message)
        self.git("commit", "--amend", "-q", "--trailer", "Bug-hunter-Tree: " + "0" * 40)
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED)

    def test_a_skip_note_before_a_real_fix_claim_does_not_exempt_it(self):
        # The exemption test used to run against the concatenation of every
        # Bug-hunter: value on the commit, so a skip note listed first
        # exempted a genuine fix-claim trailer sitting right beside it from
        # ever needing a binding. Closed by testing only the last logical
        # trailer, which is also the one a human reading the commit would
        # take as authoritative.
        self.settle()
        with self.no_auto_mint():
            self.commit(
                "FEAT(app): big new feature\n\n"
                "Bug-hunter: skipped at triage (docs only)\n"
                "Bug-hunter: 1 iteration, 1 bug fixed",
                filename="app.py",
            )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("Bug-hunter-Tree", result.stderr)

    def test_a_skip_note_after_a_stale_fix_claim_is_exempt(self):
        # The reverse order is a legitimate correction, not a bypass: the
        # last Bug-hunter: trailer on the commit is the one that applies.
        self.settle()
        with self.no_auto_mint():
            self.commit(
                "docs: readme tweak\n\n"
                "Bug-hunter: 1 iteration, 1 bug fixed\n"
                "Bug-hunter: skipped at triage (docs only)",
                filename="README.md",
            )
        result = self.run_hook("--host", "claude")
        self.assertEqual(result.returncode, QUIET, result.stderr or "(silent)")

    # -- ⑤ the commit is assembled by the script, not by hand ---------------
    #
    # commit-with-trailer.sh is the one command SKILL.md's commit step names
    # and the one the hook's own report points at. These pin the contract the
    # docs make for it: every trailer is a real git trailer, a skip is never
    # minted, anything else is minted against the tree that lands, the
    # Co-Authored-By footer cannot fall out of the trailer block, and the
    # hook is quiet on what it produces. See
    # ../DECISIONS.md#the-commit-is-assembled-by-a-script-not-by-hand.

    def wrapper_commit(self, *args):
        """Stage nothing; run the wrapper with `args` in the test repo, as an
        agent would from the project directory. Identity and signing are set
        on the repo, since the wrapper runs plain `git commit`."""
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "commit.gpgsign", "false")
        return subprocess.run(
            ["sh", str(WRAPPER), *args], cwd=self.repo, capture_output=True, text=True,
        )

    def trailer(self, key):
        return self.git("log", "-1", f"--format=%(trailers:key={key},valueonly)")

    def wrapper_with_its_library(self):
        """A copy of the commit script in the clone's layout, with the shared
        library but without the real mint, so a test can put a stub
        mint-trailer.sh in the returned scripts directory."""
        root = pathlib.Path(tempfile.mkdtemp(prefix="bh-scripts-")).resolve()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        scripts = root / ".agents" / "skills" / "bug-hunter" / "scripts"
        scripts.mkdir(parents=True)
        shutil.copy(WRAPPER, scripts / "commit-with-trailer.sh")
        shutil.copytree(WRAPPER.parent.parent.parent.parent / "lib" / "commit-trailer",
                        root / ".agents" / "lib" / "commit-trailer")
        return scripts

    def test_the_commit_script_is_executable(self):
        self.assertTrue(WRAPPER.stat().st_mode & 0o111, f"{WRAPPER} lost its exec bit")

    def test_a_skip_through_the_script_is_a_real_trailer_and_is_not_minted(self):
        # The "quick docs commit" — the case that kept getting hand-typed.
        # An empty body is legal and produces no empty paragraph.
        self.settle()
        (self.repo / "README.md").write_text("docs")
        self.git("add", "README.md")
        result = self.wrapper_commit(
            "DOCS(Readme): fix typo", "", "skipped at triage (docs only)")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.trailer("Bug-hunter"), "skipped at triage (docs only)")
        self.assertEqual(self.trailer("Bug-hunter-Tree"), "")
        self.assertEqual(
            self.git("log", "-1", "--format=%B"),
            "DOCS(Readme): fix typo\n\nBug-hunter: skipped at triage (docs only)")
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_a_fix_through_the_script_is_minted_against_the_landed_tree(self):
        self.settle()
        (self.repo / "fix.py").write_text("x = 1")
        self.git("add", "fix.py")
        result = self.wrapper_commit(
            "FIX(Parser): handle empty input", "Body text here.", "1 iteration, 1 bug fixed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.trailer("Bug-hunter"), "1 iteration, 1 bug fixed")
        self.assertEqual(self.trailer("Bug-hunter-Tree"), self.git("rev-parse", "HEAD^{tree}"))
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_the_co_author_lands_in_the_same_trailer_block(self):
        # The Co-Authored-By footer is the shape that actually loses a
        # hand-typed trailer (reference.md, "Trailer placement"): appended
        # last, a blank line below, it starts a new paragraph and the
        # Bug-hunter: line above it stops being a trailer. As the fourth
        # argument it is a trailer too, so there is no paragraph to fall into.
        self.settle()
        (self.repo / "fix.py").write_text("x = 1")
        self.git("add", "fix.py")
        result = self.wrapper_commit(
            "FIX(Parser): handle empty input", "Body text here.",
            "1 iteration, 1 bug fixed", "Someone <someone@example.com>")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.trailer("Co-Authored-By"), "Someone <someone@example.com>")
        self.assertEqual(self.trailer("Bug-hunter"), "1 iteration, 1 bug fixed")
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_the_script_refuses_the_wrong_number_of_arguments_and_commits_nothing(self):
        self.settle()
        (self.repo / "fix.py").write_text("x = 1")
        self.git("add", "fix.py")
        before = self.git("rev-parse", "HEAD")
        result = self.wrapper_commit("FIX: x", "body")
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def test_an_empty_bug_hunter_value_is_refused_and_commits_nothing(self):
        # `""` is legal for the body and SKILL.md says so, which is exactly how
        # a transposed argument list arrives here. An empty value passed the
        # count check, was minted, and landed as `Bug-hunter:` with nothing
        # after it — which git reads as no trailer, so the hook reported the
        # commit the wrapper had just exited 0 on.
        self.settle()
        (self.repo / "fix.py").write_text("x = 1")
        self.git("add", "fix.py")
        for value in ("", "   "):   # the hook strips whitespace before judging
            with self.subTest(value=value):
                (self.repo / "fix.py").write_text(f"x = {value!r}")
                self.git("add", "fix.py")
                before = self.git("rev-parse", "HEAD")
                result = self.wrapper_commit("FIX: x", "body", value)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotEqual(result.stderr, "")
                self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def test_a_multi_line_bug_hunter_value_is_refused_and_commits_nothing(self):
        # git does not fold a --trailer value: the second line lands
        # unindented, the trailer block ends there, and nothing after it —
        # the freshly minted Bug-hunter-Tree included — parses as a trailer.
        # The wrapper exited 0 and the hook reported the commit as unchecked.
        # The fourth argument has the same failure, and takes every trailer
        # above it down too.
        self.settle()
        for args in (("aborted after iteration 1 (reason\nsecond line)",),
                     ("1 iteration, 1 bug fixed", "A <a@x>\nB <b@x>")):
            with self.subTest(args=args):
                (self.repo / "fix.py").write_text(f"x = {args!r}")
                self.git("add", "fix.py")
                before = self.git("rev-parse", "HEAD")
                result = self.wrapper_commit("FIX: x", "body", *args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(self.git("rev-parse", "HEAD"), before)
        # A trailing newline — a heredoc-built value — is not an embedded one;
        # git trims it, so the wrapper must not refuse it.
        (self.repo / "fix.py").write_text("x = 'trailing newline'")
        self.git("add", "fix.py")
        result = self.wrapper_commit(
            "FIX: x", "body", "1 iteration, 1 bug fixed\n", "A <a@x>\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.trailer("Bug-hunter"), "1 iteration, 1 bug fixed")
        self.assertEqual(self.trailer("Co-Authored-By"), "A <a@x>")
        self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)

    def test_a_failed_mint_never_reaches_git_commit(self):
        # `set -- "$@" --trailer "$("$mint")"` does not trip `set -e` when the
        # substitution fails — `set` itself returns 0 — so the wrapper went on
        # to `git commit ... --trailer ""`. git 2.54 happens to refuse an empty
        # --trailer; every earlier git that has --trailer at all handed it to
        # interpret-trailers, which emitted a blank line and landed the commit
        # with its binding missing or its block split, wrapper exit 0. So the
        # check is not "did the commit fail" — it is "was git commit invoked".
        self.settle()
        scripts = self.wrapper_with_its_library()
        stub = scripts / "mint-trailer.sh"
        stub.write_text("#!/bin/sh\necho 'mint-trailer: simulated failure' >&2\nexit 1\n")
        stub.chmod(0o755)
        shim = pathlib.Path(tempfile.mkdtemp(prefix="bh-git-shim-")).resolve()
        self.addCleanup(shutil.rmtree, shim, ignore_errors=True)
        marker = shim / "commit-was-invoked"
        real_git = shutil.which("git")
        (shim / "git").write_text(
            "#!/bin/sh\n"
            f'case " $* " in *" commit "*) : >"{marker}"; exit 0 ;; esac\n'
            f'exec "{real_git}" "$@"\n')
        (shim / "git").chmod(0o755)
        (self.repo / "fix.py").write_text("x = 1")
        self.git("add", "fix.py")
        result = subprocess.run(
            ["sh", str(scripts / "commit-with-trailer.sh"),
             "FIX: x", "body", "1 iteration, 1 bug fixed"],
            cwd=self.repo, capture_output=True, text=True,
            env={**os.environ, "PATH": f"{shim}:{os.environ['PATH']}"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("simulated failure", result.stderr)
        self.assertFalse(marker.exists(), "git commit was invoked after the mint failed")

    def test_a_users_trailer_config_cannot_drop_or_mangle_the_trailers(self):
        # git compares trailer tokens by prefix, so `Bug-hunter-Tree` counts as
        # already existing whenever `Bug-hunter` does. The default
        # addIfDifferentNeighbor keeps both; a user's `trailer.ifexists=replace`
        # made the mint replace the Bug-hunter trailer, `doNothing` dropped the
        # mint, and `trailer.ifmissing=doNothing` dropped all three. The
        # wrapper exited 0 every time and the hook reported every commit —
        # then told the agent to use the wrapper. (`trailer.separators` is
        # not here: it also breaks the hook's own *reading* of trailers, the
        # `log.showSignature` problem again — fixed on the hook's own read
        # side, tested separately, not reachable from the wrapper.)
        self.settle()
        for key, value in (("trailer.ifexists", "replace"),
                           ("trailer.ifexists", "doNothing"),
                           ("trailer.ifmissing", "doNothing")):
            with self.subTest(**{key: value}):
                self.git("config", key, value)
                try:
                    (self.repo / "fix.py").write_text(f"x = '{key}={value}'")
                    self.git("add", "fix.py")
                    result = self.wrapper_commit("FIX: x", "body", "0 bugs found", "A <a@x>")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.trailer("Bug-hunter"), "0 bugs found")
                    self.assertEqual(self.trailer("Bug-hunter-Tree"), self.git("rev-parse", "HEAD^{tree}"))
                    self.assertEqual(self.trailer("Co-Authored-By"), "A <a@x>")
                    self.assertEqual(self.run_hook("--host", "claude").returncode, QUIET)
                finally:
                    self.git("config", "--unset", key)

    def test_a_noisy_mint_never_lands_a_multi_line_binding(self):
        # mint-trailer.sh captures `git write-tree 2>&1`, so anything git says
        # on stderr while succeeding — GIT_TRACE=1, a core.fsmonitor hook that
        # is not on this machine — arrives ahead of the hash in the minted
        # value. The wrapper validated the two values it was given for line
        # breaks and trusted the one it generated: git wrote the hash as an
        # unindented second line, the whole block stopped parsing, and the
        # hook reported the commit as unchecked. Wrapper exit 0.
        #
        # The noisy mint is injected rather than provoked with GIT_TRACE=1,
        # so this stays a test of the wrapper's own contract — refuse a value
        # it would not accept from an argument — independent of
        # test_mint_trailer_does_not_leak_stderr_into_a_successful_binding,
        # which covers the real script no longer merging stderr in.
        self.settle()
        scripts = self.wrapper_with_its_library()
        noisy = scripts / "mint-trailer.sh"
        noisy.write_text(
            "#!/bin/sh\n"
            "printf 'Bug-hunter-Tree: fatal: cannot exec /nonexistent/fsmonitor\\n%s\\n' "
            "\"$(git write-tree)\"\n")
        noisy.chmod(0o755)
        (self.repo / "fix.py").write_text("x = 1")
        self.git("add", "fix.py")
        before = self.git("rev-parse", "HEAD")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "commit.gpgsign", "false")
        result = subprocess.run(
            ["sh", str(scripts / "commit-with-trailer.sh"),
             "FIX: x", "body", "1 iteration, 1 bug fixed"],
            cwd=self.repo, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def test_an_empty_subject_is_refused_and_commits_nothing(self):
        # `-m ""` contributes nothing and an empty body adds no `-m`, so the
        # message was only the trailer lines — which git reads as the title
        # paragraph, never as trailers. The commit landed with the Bug-hunter
        # line as its subject and the hook reported it. This is the documented
        # quick-docs shape (`<subject> "" "skipped — <reason>"`) with the
        # subject coming out of an empty variable.
        self.settle()
        for subject in ("", "  "):
            with self.subTest(subject=subject):
                (self.repo / "README.md").write_text(f"docs {subject!r}")
                self.git("add", "README.md")
                before = self.git("rev-parse", "HEAD")
                result = self.wrapper_commit(subject, "", "skipped at triage (docs only)")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(self.git("rev-parse", "HEAD"), before)


class SharedLibraryTests(unittest.TestCase):
    """bug-hunter's scripts are wrappers over .agents/lib/commit-trailer/.

    Every other test runs them by their real path in the clone. Installs reach
    them through a symlinked skill directory instead, so this runs all three
    that way, end to end.
    """

    GIT = ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
           "-c", "commit.gpgsign=false"]

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="bh-lib-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.repo, check=True)
        subprocess.run(self.GIT + ["commit", "-q", "--allow-empty", "-m", "seed",
                                   "--trailer", "Bug-hunter: skipped at triage (seed)"],
                       cwd=self.repo, check=True)

    def hook(self, script, host="claude", shell="sh"):
        return subprocess.run(
            [shell, str(script), "--host", host],
            input=json.dumps({"cwd": str(self.repo)}),
            capture_output=True, text=True, cwd=self.repo,
        )

    def test_it_works_through_a_symlinked_skill_directory(self):
        installed = self.tmp / "home" / ".agents" / "skills" / "bug-hunter"
        installed.parent.mkdir(parents=True)
        installed.symlink_to(HOOK.parent.parent, target_is_directory=True)
        scripts = installed / "scripts"

        self.assertEqual(self.hook(scripts / "check-commit-trailer.sh").returncode, QUIET)
        (self.repo / "f.py").write_text("x")
        subprocess.run(["git", "add", "f.py"], cwd=self.repo, check=True)

        minted = subprocess.run(["sh", str(scripts / "mint-trailer.sh")],
                                cwd=self.repo, capture_output=True, text=True)
        tree = subprocess.run(["git", "write-tree"], cwd=self.repo,
                              capture_output=True, text=True).stdout.strip()
        self.assertEqual(minted.stdout.strip(), f"Bug-hunter-Tree: {tree}", minted.stderr)

        committed = subprocess.run(
            ["sh", str(scripts / "commit-with-trailer.sh"), "FEAT: f", "",
             "1 iteration, 0 bugs found"],
            cwd=self.repo, capture_output=True, text=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@e.com",
                 "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@e.com"},
        )
        self.assertEqual(committed.returncode, 0, committed.stderr)
        result = self.hook(scripts / "check-commit-trailer.sh")
        self.assertEqual(result.returncode, QUIET, result.stderr)

    def test_a_missing_library_is_reported_not_silent(self):
        # A copy of the skill without the clone around it has no library. A
        # hook that then exits 0 is broken and looks like it is working.
        copied = self.tmp / "bug-hunter" / "scripts"
        shutil.copytree(HOOK.parent, copied)

        result = self.hook(copied / "check-commit-trailer.sh")
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("library is missing", result.stderr)

        cursor = self.hook(copied / "check-commit-trailer.sh", host="cursor")
        self.assertEqual(cursor.returncode, 0)
        self.assertIn("library is missing", json.loads(cursor.stdout)["additional_context"])

        mint = subprocess.run(["sh", str(copied / "mint-trailer.sh")],
                              cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(mint.returncode, 1)
        self.assertIn("library is missing", mint.stderr)

    def second_skill(self, skill, key, host="claude", shell="sh",
                     report_text='commit_trailer_report() { REPORT="custom report"; }\n'):
        """A wrapper for another skill, configured as the library documents."""
        lib = HOOK.parent.parent.parent.parent / "lib" / "commit-trailer" / "check-commit-trailer.sh"
        report = self.tmp / "report.sh"
        report.write_text(report_text)
        wrapper = self.tmp / "second.sh"
        wrapper.write_text(
            f"COMMIT_TRAILER_SKILL='{skill}'\nCOMMIT_TRAILER_KEY='{key}'\n"
            f"COMMIT_TRAILER_REPORT='{report}'\n. '{lib}'\n"
        )
        return self.hook(wrapper, host=host, shell=shell)

    @unittest.skipUnless(shutil.which("dash"), "needs dash, where `.` on a broken file aborts")
    def test_a_broken_report_file_still_reports_under_dash(self):
        # Under dash a syntax error in a sourced file aborts the whole shell.
        # The cursor has already advanced by then, so the commits it was about
        # to name are never reported again.
        subprocess.run(self.GIT + ["commit", "-q", "--allow-empty", "-m", "FEAT: unreported"],
                       cwd=self.repo, check=True)
        broken = 'commit_trailer_report() {\n  REPORT="x"\n'
        result = self.second_skill("demo", "Demo", shell="dash", report_text=broken)
        self.assertEqual(result.returncode, REPORTED, result.stderr)
        self.assertIn("could not be loaded", result.stderr)
        self.assertIn("unreported", result.stderr)

    def test_a_missing_skill_name_or_key_is_refused(self):
        # With no key, no commit can ever carry the trailer, so every commit
        # would be reported after every command, forever.
        for skill, key in (("prose", ""), ("", "Prose")):
            with self.subTest(skill=skill, key=key):
                result = self.second_skill(skill, key)
                self.assertEqual(result.returncode, REPORTED)
                self.assertIn("must be set", result.stderr)
                self.assertNotIn("custom report", result.stderr)
                self.assertFalse((self.repo / ".git" / "-head").exists())

    def test_a_skill_name_starting_with_a_digit_is_refused(self):
        # The name becomes a shell variable prefix, which cannot start with a
        # digit: accepting it crashed the hook on every command.
        result = self.second_skill("2x", "Prose")
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("must be set", result.stderr)
        self.assertNotIn("bad substitution", result.stderr)

    def test_a_misconfigured_skill_still_answers_cursor_in_json(self):
        result = self.second_skill("", "Prose", host="cursor")
        self.assertEqual(result.returncode, 0)
        self.assertIn("must be set", json.loads(result.stdout)["additional_context"])


class CommitFamiliesTests(unittest.TestCase):
    """Commits carrying several skills' trailer families, made by the
    library's commit-with-trailers.sh. Most tests pair bug-hunter's minted
    family (Bug-hunter, Bug-hunter-Tree) with a stand-in for prose's family:
    one `Prose` line whose value is a signature minted beforehand and checked
    by its own verifier (--verified-value).
    See ../../../lib/commit-trailer/DECISIONS.md#one-commit-several-families.
    """

    LIB = HOOK.parent.parent.parent.parent / "lib" / "commit-trailer" / "commit-with-trailers.sh"

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="bh-families-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        for key, value in (("user.name", "T"), ("user.email", "t@e.com"),
                           ("commit.gpgsign", "false")):
            self.git("config", key, value)
        self.git("commit", "-q", "--allow-empty", "-m", "seed",
                 "--trailer", "Bug-hunter: skipped at triage (seed)")
        self.demo = self.value_demo()
        self.verified_marker = self.tmp / "verifier-ran"
        self.commit_marker = self.tmp / "commit-was-invoked"
        shim = self.tmp / "shim"
        shim.mkdir()
        (shim / "git").write_text(
            "#!/bin/sh\n"
            f'if [ -n "${{SHIM_COMMIT:-}}" ]; then case " $* " in *" commit "*) : >"{self.commit_marker}"; exit 0 ;; esac; fi\n'
            f'exec "{shutil.which("git")}" "$@"\n')
        (shim / "git").chmod(0o755)
        self.env = {**os.environ, "PATH": f"{shim}:{os.environ['PATH']}",
                    "DEMO_MARKER": str(self.verified_marker)}
        self.run_hook()  # record the seed commit as already judged

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def run_hook(self):
        return subprocess.run(
            ["sh", str(HOOK), "--host", "claude"],
            input=json.dumps({"cwd": str(self.repo)}),
            capture_output=True, text=True, cwd=self.repo,
        )

    def stage(self, name="f.py", content="x = 1"):
        (self.repo / name).write_text(content)
        self.git("add", name)

    def demo_value(self, subject, body):
        """What the prose stand-in signs for this message, over what is staged now."""
        return self.prose_value(self.demo, subject, body)

    def commit(self, *args, shim=False):
        env = {**self.env, **({"SHIM_COMMIT": "1"} if shim else {})}
        return subprocess.run(["sh", str(self.LIB), *args], cwd=self.repo,
                              capture_output=True, text=True, env=env)

    def trailer(self, key):
        return self.git("log", "-1", f"--format=%(trailers:key={key},valueonly)")

    def trailer_block(self):
        message = self.git("log", "-1", "--format=%B")
        return subprocess.run(["git", "interpret-trailers", "--parse"], input=message,
                              capture_output=True, text=True).stdout.strip().splitlines()

    def assert_both_families_landed(self, value):
        tree = self.git("rev-parse", "HEAD^{tree}")
        self.assertEqual(self.trailer_block(), [
            "Bug-hunter: 1 iteration, 0 bugs found",
            f"Bug-hunter-Tree: {tree}",
            f"Prose: {value}",
            "Co-Authored-By: A <a@x>",
        ])
        self.assertEqual(self.trailer("Bug-hunter"), "1 iteration, 0 bugs found")
        self.assertEqual(self.trailer("Bug-hunter-Tree"), tree)
        self.assertEqual(self.trailer("Prose"), value)
        result = self.run_hook()
        self.assertEqual(result.returncode, QUIET, result.stderr)

    def two_families(self, value, minter=None, subject="FEAT: x", body="body"):
        bug_hunter = (["--minted-by", str(minter)] if minter else ["--minted"])
        return [*bug_hunter, "Bug-hunter", "1 iteration, 0 bugs found",
                "--verified-value", str(self.demo), "Prose", value,
                "--co-authored-by", "A <a@x>", "--", subject, body]

    def test_the_script_is_executable(self):
        self.assertTrue(self.LIB.stat().st_mode & 0o111, f"{self.LIB} lost its exec bit")

    def test_two_families_land_in_one_trailer_block_with_matching_bindings(self):
        for minter in (None, MINT):   # --minted, then --minted-by bug-hunter's mint
            with self.subTest(minter=minter):
                self.stage(content=f"x = {minter!r}")
                value = self.demo_value("FEAT: x", "body")
                result = self.commit(*self.two_families(value, minter))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(self.verified_marker.exists(), "the verifier never ran")
                self.verified_marker.unlink()
                self.assert_both_families_landed(value)

    def test_an_empty_body_reaches_the_verifier_as_the_subject_alone(self):
        self.stage()
        value = self.demo_value("FEAT: x", "")
        result = self.commit(*self.two_families(value, body=""))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "FEAT: x")

    def test_a_stale_binding_is_refused_before_any_commit(self):
        # Each case mints the binding, then changes the staged tree or the
        # message before committing. git commit must never be invoked.
        cases = {
            "tree changed after minting": ("FEAT: x", "body", True),
            "subject changed after minting": ("FEAT: y", "body", False),
            "body changed after minting": ("FEAT: x", "other body", False),
        }
        for name, (subject, body, restage) in cases.items():
            with self.subTest(name):
                self.stage(content=f"x = {name!r}")
                value = self.demo_value("FEAT: x", "body")
                if restage:
                    self.stage("g.py", "y = 2")
                before = self.git("rev-parse", "HEAD")
                result = self.commit(*self.two_families(value, subject=subject, body=body),
                                     shim=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("no longer matches", result.stderr)
                self.assertFalse(self.commit_marker.exists(), "git commit was invoked")
                self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def test_the_prefix_matching_trap_holds_for_both_families(self):
        # git matches trailer keys by prefix, so it treats `Bug-hunter-Tree` as
        # a repeat of `Bug-hunter`. Without the library's pinned settings, each
        # of these user settings would drop or overwrite a binding, or reverse
        # the trailer order.
        for key, value in (("trailer.ifexists", "replace"),
                           ("trailer.ifexists", "doNothing"),
                           ("trailer.ifmissing", "doNothing"),
                           ("trailer.where", "start")):
            with self.subTest(**{key: value}):
                self.git("config", key, value)
                try:
                    self.stage(content=f"x = '{key}={value}'")
                    signature = self.demo_value("FEAT: x", "body")
                    result = self.commit(*self.two_families(signature, MINT))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assert_both_families_landed(signature)
                finally:
                    self.git("config", "--unset", key)

    def test_skip_notes_bind_nothing_in_either_family(self):
        self.stage("README.md", "docs")
        result = self.commit("--minted-by", str(MINT), "Bug-hunter", "skipped at triage (docs only)",
                             "--verified-value", str(self.demo), "Prose", "Skipped (not prose)",
                             "--", "DOCS: x", "")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.verified_marker.exists(), "a skip note was verified")
        self.assertEqual(self.trailer_block(), [
            "Bug-hunter: skipped at triage (docs only)", "Prose: Skipped (not prose)"])
        self.assertEqual(self.run_hook().returncode, QUIET)

    def test_a_bad_family_is_refused_before_anything_runs(self):
        # Each case must exit 2 before any verifier, mint or git commit runs.
        self.stage()
        mint_marker = self.tmp / "mint-ran"
        minter = self.tmp / "minter"
        minter.write_text(f'#!/bin/sh\n: >"{mint_marker}"\nexec sh "{MINT}"\n')
        minter.chmod(0o755)
        bh = ["--minted-by", str(minter), "Bug-hunter", "0 bugs found"]
        demo = ["--verified-value", str(self.demo)]
        tail = ["--", "FEAT: x", "body"]
        cases = {
            "multi-line value in the second family": [*bh, *demo, "Prose", "a\nb", *tail],
            "empty value in the second family": [*bh, *demo, "Prose", "  ", *tail],
            "the same key twice": [*bh, *bh, *tail],
            "a key inside another family's namespace": [*bh, "--minted", "Bug-hunter-Tree",
                                                        "x", *tail],
            "a key that is a prefix of another": [*bh, "--minted", "Bug", "x", *tail],
            "a key starting with a digit": [*bh, "--minted", "2x", "x", *tail],
            "a key with a space": [*bh, "--minted", "Demo Sig", "x", *tail],
            "no family at all": [*tail],
            "an empty subject": [*bh, "--", "  ", ""],
            "a multi-line co-author": [*bh, "--co-authored-by", "A <a@x>\nB <b@x>", *tail],
            "a missing body": [*bh, "--", "FEAT: x"],
            "an unknown option": [*bh, "--tree", "Demo", "x", *tail],
        }
        for name, args in cases.items():
            with self.subTest(name):
                result = self.commit(*args, shim=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertNotEqual(result.stderr, "")
                for marker in (self.verified_marker, mint_marker, self.commit_marker):
                    self.assertFalse(marker.exists(), f"{marker.name} after a bad argument")

    def test_a_missing_tool_is_refused_before_anything_runs(self):
        self.stage()
        value = self.demo_value("FEAT: x", "body")
        text = self.tmp / "not-executable"
        text.write_text("#!/bin/sh\nexit 0\n")
        for tool in (self.tmp / "absent", text, self.tmp):
            with self.subTest(tool=tool.name):
                result = self.commit("--minted", "Bug-hunter", "0 bugs found",
                                     "--verified-value", str(tool), "Prose", value,
                                     "--", "FEAT: x", "body", shim=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("not an executable file", result.stderr)
                self.assertFalse(self.commit_marker.exists())

    def test_a_failed_or_noisy_minter_never_reaches_git_commit(self):
        # The library's version of bug-hunter's two minter tests. A minter that
        # fails, or that succeeds but prints more than the binding, must stop
        # the commit. The test checks whether git commit was invoked, not
        # whether HEAD moved.
        self.stage()
        value = self.demo_value("FEAT: x", "body")
        stubs = {
            "failing": ("echo 'mint: simulated failure' >&2\nexit 1\n", "simulated failure"),
            "noisy": ("printf 'Bug-hunter-Tree: fatal: cannot exec fsmonitor\\n%s\\n' "
                      "\"$(git write-tree)\"\n", "more than one line"),
            "wrong key": ('printf \'Demo-Tree: %s\\n\' "$(git write-tree)"\n', "other than"),
            "junk": ("echo 'Bug-hunter-Tree: not-a-hash'\n", "other than"),
        }
        for name, (body, expected) in stubs.items():
            with self.subTest(name):
                stub = self.tmp / f"mint-{name.replace(' ', '-')}"
                stub.write_text("#!/bin/sh\n" + body)
                stub.chmod(0o755)
                result = self.commit(*self.two_families(value, stub), shim=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(expected, result.stderr)
                self.assertFalse(self.commit_marker.exists(), "git commit was invoked")

    def test_keys_sharing_a_plain_prefix_are_refused(self):
        # git treats two keys as one when either is a prefix of the other, with
        # or without a dash. Without this refusal, under git's default
        # ifexists (addIfDifferentNeighbor), the second of two identical skip
        # notes would be dropped and the commit would still exit 0.
        self.stage()
        for first, second in (("Pro", "Prose"), ("Demo", "Demonstration"), ("Prose", "pro")):
            with self.subTest(first=first, second=second):
                result = self.commit("--minted", first, "skipped (n/a)",
                                     "--minted", second, "skipped (n/a)",
                                     "--", "S", "", shim=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("collides", result.stderr)
                self.assertFalse(self.commit_marker.exists(), "git commit was invoked")

    def test_a_tool_named_without_a_path_is_refused(self):
        # A bare name would be checked in the current directory but run from
        # PATH. Without this refusal, a verifier beside the caller would pass
        # the check, then fail as "command not found", reported as a stale
        # binding.
        self.stage()
        value = self.demo_value("FEAT: x", "body")
        shutil.copy(self.demo, self.repo / "prose-sig")
        for family in (["--verified-value", "prose-sig", "Prose", value],
                       ["--minted-by", "prose-sig", "Prose", "checked"]):
            with self.subTest(kind=family[0]):
                result = self.commit(*family, "--", "FEAT: x", "body", shim=True)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("no longer matches", result.stderr)
                self.assertNotIn("not found", result.stderr)
                self.assertFalse(self.commit_marker.exists(), "git commit was invoked")

    def test_the_removed_verified_family_is_refused_as_an_unknown_option(self):
        # --verified (a family with a separate binding line) is not an option.
        # A caller still passing it must commit nothing.
        self.stage()
        result = self.commit("--verified", str(self.demo), "Prose", "checked",
                             "Prose-Sig: 0123abcd4567", "--", "FEAT: x", "body", shim=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("unknown option --verified", result.stderr)
        self.assertFalse(self.verified_marker.exists(), "a verifier ran")
        self.assertFalse(self.commit_marker.exists(), "git commit was invoked")

    def test_verifiers_run_before_any_mint(self):
        # A stale binding in the last family must stop the commit before the
        # first family's mint writes anything.
        self.stage()
        value = self.demo_value("FEAT: x", "body")
        self.stage("g.py", "y = 2")
        mint_marker = self.tmp / "mint-ran"
        minter = self.tmp / "minter"
        minter.write_text(f'#!/bin/sh\n: >"{mint_marker}"\nexec sh "{MINT}"\n')
        minter.chmod(0o755)
        result = self.commit(*self.two_families(value, minter), shim=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("no longer matches", result.stderr)
        self.assertFalse(mint_marker.exists(), "a mint ran before the verifier refused")
        self.assertFalse(self.commit_marker.exists(), "git commit was invoked")

    def test_a_missing_value_does_not_swallow_the_separator(self):
        # Models `--minted Bug-hunter $v --` with $v empty and unquoted.
        # Without the check in takes(), the parser would take `--` as the value
        # and commit `Bug-hunter: --` with a valid binding.
        self.stage()
        for args in (["--minted", "Bug-hunter", "--"],
                     ["--minted-by", str(MINT), "Bug-hunter", "--"],
                     ["--minted", "Bug-hunter", "0 bugs found", "--co-authored-by", "--"],
                     # two values missing in a row: the next option's name would become a value
                     ["--minted", "Bug-hunter", "--co-authored-by", "--"],
                     ["--minted", "Bug-hunter", "0 bugs found",
                      "--co-authored-by", "--co-authored-by", "--"],
                     # the same without the separator
                     ["--minted", "Bug-hunter", "--co-authored-by"]):
            with self.subTest(args=args):
                result = self.commit(*args, "FEAT: x", "body", shim=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse(self.commit_marker.exists(), "git commit was invoked")

    def test_a_vanished_value_is_refused_when_splitting_restores_the_count(self):
        # An unquoted empty value and an unquoted two-word subject, with no
        # `--`. Without the required `--`, the subject's first word would
        # become the value and its second word the subject; the argument count
        # comes out right, so the commit would land, bound.
        self.stage()
        for option in (["--minted", "Bug-hunter"], ["--minted", "Bug-hunter", "0 bugs found",
                                                    "--co-authored-by"]):
            with self.subTest(option=option):
                result = self.commit(*option, "FEAT:", "x", "body", shim=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse(self.commit_marker.exists(), "git commit was invoked")

    def test_a_value_with_quotes_and_dollars_lands_verbatim(self):
        # The library replays families through `eval set --`; the shell must
        # not interpret anything in a value on the way.
        self.stage()
        value = "1 iteration, 0 bugs found ('it''s' \"$HOME\" `id` \\ $(id))"
        subject = "FEAT: it's \"$HOME\" `id`"
        result = self.commit("--minted", "Bug-hunter", value, "--", subject, "b'o\"dy $x")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.trailer("Bug-hunter"), value)
        self.assertEqual(self.git("log", "-1", "--format=%s"), subject)
        self.assertEqual(self.run_hook().returncode, QUIET)

    # -- a family whose value is its own binding (--verified-value) ---------
    #
    # prose's trailer is `Prose: ✓ <12 hex tree>:<12 hex message>`: the value
    # is the signature, so there is no separate binding line.

    VALUE_DEMO = (
        "#!/bin/sh\n"
        "set -eu\n"
        '[ -n "${DEMO_MARKER:-}" ] && [ "$#" -gt 0 ] && : >"$DEMO_MARKER"\n'
        "tree=$(git write-tree | cut -c1-12)\n"
        "msg=$(git hash-object --stdin | cut -c1-12)\n"
        'if [ "$#" -eq 0 ]; then printf \'\\342\\234\\223 %s:%s\\n\' "$tree" "$msg"; exit 0; fi\n'
        '[ "$1" = "Prose: $(printf \'\\342\\234\\223\') $tree:$msg" ]\n'
    )

    def value_demo(self):
        script = self.tmp / "prose-sig"
        script.write_text(self.VALUE_DEMO)
        script.chmod(0o755)
        return script

    def prose_value(self, script, subject, body):
        message = subject + (f"\n\n{body}" if body else "")
        result = subprocess.run([str(script)], input=message, cwd=self.repo,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_a_value_verified_family_composes_with_a_minted_one(self):
        self.stage()
        prose = self.value_demo()
        value = self.prose_value(prose, "FEAT: x", "body")
        self.assertRegex(value, r"^\u2713 [0-9a-f]{12}:[0-9a-f]{12}$")
        result = self.commit("--minted", "Bug-hunter", "1 iteration, 0 bugs found",
                             "--verified-value", str(prose), "Prose", value,
                             "--co-authored-by", "A <a@x>", "--", "FEAT: x", "body")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.verified_marker.exists(), "the verifier never ran")
        self.assertEqual(self.trailer_block(), [
            "Bug-hunter: 1 iteration, 0 bugs found",
            f"Bug-hunter-Tree: {self.git('rev-parse', 'HEAD^{tree}')}",
            f"Prose: {value}",
            "Co-Authored-By: A <a@x>",
        ])
        self.assertEqual(self.run_hook().returncode, QUIET)

    def test_a_stale_value_is_refused_before_any_mint_or_commit(self):
        prose = self.value_demo()
        mint_marker = self.tmp / "mint-ran"
        minter = self.tmp / "minter"
        minter.write_text(f'#!/bin/sh\n: >"{mint_marker}"\nexec sh "{MINT}"\n')
        minter.chmod(0o755)
        cases = {
            "tree changed after signing": ("FEAT: x", "body", True),
            "message changed after signing": ("FEAT: y", "body", False),
        }
        for name, (subject, body, restage) in cases.items():
            with self.subTest(name):
                self.stage(content=f"x = {name!r}")
                value = self.prose_value(prose, "FEAT: x", "body")
                if restage:
                    self.stage("g.py", "y = 2")
                result = self.commit("--minted-by", str(minter), "Bug-hunter", "0 bugs found",
                                     "--verified-value", str(prose), "Prose", value,
                                     "--", subject, body, shim=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("no longer matches", result.stderr)
                self.assertFalse(mint_marker.exists(), "a mint ran before the verifier refused")
                self.assertFalse(self.commit_marker.exists(), "git commit was invoked")

    def test_a_value_verified_skip_note_is_not_verified(self):
        self.stage("README.md", "docs")
        prose = self.value_demo()
        result = self.commit("--verified-value", str(prose), "Prose", "skipped (no prose)",
                             "--", "DOCS: x", "")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.verified_marker.exists(), "a skip note was verified")
        self.assertEqual(self.trailer_block(), ["Prose: skipped (no prose)"])

    def test_a_bad_value_verified_family_is_refused_before_anything_runs(self):
        self.stage()
        prose = self.value_demo()
        good = self.prose_value(prose, "FEAT: x", "body")
        shutil.copy(prose, self.repo / "prose-sig")
        tail = ["--", "FEAT: x", "body"]
        cases = {
            "bare tool name": ["--verified-value", "prose-sig", "Prose", good, *tail],
            "empty value": ["--verified-value", str(prose), "Prose", " ", *tail],
            "multi-line value": ["--verified-value", str(prose), "Prose", good + "\nx", *tail],
            "key colliding with another family": ["--minted", "Pro", "0 bugs found",
                                                  "--verified-value", str(prose), "Prose", good, *tail],
            "the option taken as a vanished value": ["--minted", "Bug-hunter",
                                                     "--verified-value", str(prose), "Prose", good, *tail],
            "too few words": ["--verified-value", str(prose), "Prose"],
        }
        for name, args in cases.items():
            with self.subTest(name):
                result = self.commit(*args, shim=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse(self.verified_marker.exists(), "verifier ran after a bad argument")
                self.assertFalse(self.commit_marker.exists(), "git commit was invoked")

    # -- the repository's pre-commit hook runs before anything is bound ------
    #
    # See ../../../lib/commit-trailer/DECISIONS.md
    # #the-pre-commit-hook-runs-before-anything-is-bound.

    # A lint-staged-style formatter: rewrites each staged .py file (drops its
    # spaces) and stages the result. Idempotent, so git commit's own run of it
    # changes nothing more.
    FORMATTER = (
        "#!/bin/sh\n"
        'echo run >>"$HOOK_RUNS"\n'
        "for f in $(git diff --cached --name-only --diff-filter=ACM -- '*.py'); do\n"
        '  tr -d " " <"$f" >"$f.tmp" && mv "$f.tmp" "$f" && git add "$f"\n'
        "done\n"
    )

    def install_hook(self, text, where=None):
        hooks = where or self.repo / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        hook = hooks / "pre-commit"
        hook.write_text(text)
        hook.chmod(0o755)
        return hook

    def hook_runs(self):
        runs = self.tmp / "hook-runs"
        return len(runs.read_text().splitlines()) if runs.exists() else 0

    def commit_with_env(self, *args, shim=False):
        self.env["HOOK_RUNS"] = str(self.tmp / "hook-runs")
        return self.commit(*args, shim=shim)

    def minting_stub(self):
        marker = self.tmp / "mint-ran"
        minter = self.tmp / "minter"
        minter.write_text(f'#!/bin/sh\n: >"{marker}"\nexec sh "{MINT}"\n')
        minter.chmod(0o755)
        return minter, marker

    def test_a_restaging_formatter_runs_before_the_mint(self):
        # Without the early run, the mint binds the unformatted tree, git
        # commit's own hook run then formats it, and the landed tree differs:
        # an honest commit the hook reports as unminted.
        self.install_hook(self.FORMATTER)
        for minter in (None, MINT):
            with self.subTest(minter=minter):
                self.stage(content=f"x = {len(str(minter))}")
                value = "1 iteration, 0 bugs found"
                bh = ["--minted-by", str(minter)] if minter else ["--minted"]
                result = self.commit_with_env(*bh, "Bug-hunter", value, "--", "FEAT: x", "body")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("changed the staged files", result.stderr)
                self.assertEqual(self.git("show", "HEAD:f.py"), f"x={len(str(minter))}")
                self.assertEqual(self.trailer("Bug-hunter-Tree"),
                                 self.git("rev-parse", "HEAD^{tree}"))
                self.assertEqual(self.run_hook().returncode, QUIET)

    def test_a_restaging_formatter_through_bug_hunters_script(self):
        self.install_hook(self.FORMATTER)
        self.stage(content="y = 2")
        env = {**os.environ, "HOOK_RUNS": str(self.tmp / "hook-runs")}
        result = subprocess.run(["sh", str(WRAPPER), "FEAT: x", "body", "1 iteration, 0 bugs found"],
                                cwd=self.repo, capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("show", "HEAD:f.py"), "y=2")
        self.assertEqual(self.trailer("Bug-hunter-Tree"), self.git("rev-parse", "HEAD^{tree}"))
        self.assertEqual(self.run_hook().returncode, QUIET)

    def test_a_failing_hook_is_refused_before_anything_is_minted(self):
        # Two shapes: a check that fails outright, and the pre-commit
        # framework's formatter, which rewrites the file, leaves the change
        # unstaged and fails.
        minter, mint_marker = self.minting_stub()
        hooks = {
            "fails outright": "echo 'lint: f.py: line too long'\nexit 1\n",
            "modifies without restaging": (
                "tr -d ' ' <f.py >f.tmp && mv f.tmp f.py\n"
                "echo 'Failed - hook id: fmt - files were modified by this hook'\nexit 1\n"),
        }
        for name, text in hooks.items():
            with self.subTest(name):
                self.install_hook("#!/bin/sh\n" + text)
                self.stage(content="x = 1")
                staged = self.git("write-tree")
                result = self.commit_with_env(
                    "--minted-by", str(minter), "Bug-hunter", "0 bugs found",
                    "--", "FEAT: x", "body", shim=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("pre-commit hook failed (exit 1)", result.stderr)
                self.assertIn("nothing committed", result.stderr)
                self.assertIn("lint: f.py" if name == "fails outright" else "files were modified",
                              result.stderr)
                self.assertFalse(mint_marker.exists(), "a mint ran after the hook failed")
                self.assertFalse(self.commit_marker.exists(), "git commit was invoked")
                self.assertEqual(self.git("write-tree"), staged)

    def test_with_no_hook_nothing_is_said_about_one(self):
        self.stage()
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FEAT: x", "body")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("pre-commit", result.stderr)
        self.assertEqual(self.trailer("Bug-hunter-Tree"), self.git("rev-parse", "HEAD^{tree}"))

    def test_core_hooks_path_is_honoured(self):
        # The default hooks directory holds a hook that would refuse; the
        # configured one holds the formatter.
        self.install_hook("#!/bin/sh\necho 'wrong hook'\nexit 1\n")
        self.install_hook(self.FORMATTER, where=self.repo / "my-hooks")
        self.git("config", "core.hooksPath", "my-hooks")
        self.stage(content="z = 3")
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FEAT: x", "body")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("wrong hook", result.stderr)
        self.assertEqual(self.git("show", "HEAD:f.py"), "z=3")
        self.assertEqual(self.trailer("Bug-hunter-Tree"), self.git("rev-parse", "HEAD^{tree}"))

    def test_a_signature_the_hook_invalidates_is_refused_and_says_why(self):
        # The value was signed before the commit script ran the hook, so a hook
        # that reformats makes it stale. The refusal must name the hook, or the
        # agent re-signs, runs again, and is refused again with no idea why.
        minter, mint_marker = self.minting_stub()
        self.install_hook(self.FORMATTER)
        self.stage(content="x = 1")
        value = self.demo_value("FEAT: x", "body")
        result = self.commit_with_env(*self.two_families(value, minter), shim=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("no longer matches", result.stderr)
        self.assertIn("the pre-commit hook changed the staged files after the value was made",
                      result.stderr)
        self.assertFalse(mint_marker.exists(), "a mint ran after the verifier refused")
        self.assertFalse(self.commit_marker.exists(), "git commit was invoked")

    def test_a_signature_made_after_the_hook_ran_lands(self):
        # What prose's `prose check` will do: run the hook, then sign.
        self.install_hook(self.FORMATTER)
        self.stage(content="x = 1")
        self.env["HOOK_RUNS"] = str(self.tmp / "hook-runs")
        early = subprocess.run(["sh", str(self.LIB.parent / "run-pre-commit.sh")], cwd=self.repo,
                               capture_output=True, text=True, env=self.env)
        self.assertEqual((early.returncode, early.stdout), (0, "changed\n"), early.stderr)
        value = self.demo_value("FEAT: x", "body")
        result = self.commit_with_env(*self.two_families(value))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_both_families_landed(value)

    def test_a_hook_that_only_touches_the_work_tree_binds_the_index(self):
        # Exits 0 and leaves its change unstaged: nothing unstaged is
        # committed, so the binding is still the landed tree.
        self.install_hook("#!/bin/sh\necho touched >notes.txt\n")
        self.stage(content="x = 1")
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FEAT: x", "body")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("changed the staged files", result.stderr)
        self.assertTrue((self.repo / "notes.txt").exists())
        self.assertEqual(self.git("ls-tree", "--name-only", "HEAD", "notes.txt"), "")
        self.assertEqual(self.trailer("Bug-hunter-Tree"), self.git("rev-parse", "HEAD^{tree}"))

    def test_skip_notes_only_leave_the_hook_to_git_commit(self):
        # Nothing is bound, so the script leaves the hook to git commit. With
        # a bound value the script runs it, and git commit does not.
        self.install_hook(self.FORMATTER)
        cases = {"skip notes only": ("skipped at triage (docs)", 1),
                 "a bound value": ("0 bugs found", 1)}
        for name, (value, runs) in cases.items():
            with self.subTest(name):
                (self.tmp / "hook-runs").unlink(missing_ok=True)
                self.stage(content=name)
                result = self.commit_with_env("--minted", "Bug-hunter", value,
                                              "--", "FEAT: x", "body")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.hook_runs(), runs)

    def test_a_refusal_that_ran_no_hook_does_not_blame_one(self):
        # run-pre-commit.sh also refuses when the staged tree cannot be read
        # (an unmerged index), with no hook installed at all. The last line
        # must not send the agent looking for a hook failure.
        blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], input="a", cwd=self.repo,
                              capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "update-index", "--index-info"], cwd=self.repo, text=True,
                       input=f"100644 {blob} 1\tc.py\n100644 {blob} 2\tc.py\n", check=True)
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FEAT: x", "body", shim=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("write-tree failed", result.stderr)
        self.assertNotIn("the pre-commit hook did not pass", result.stderr)
        self.assertFalse(self.commit_marker.exists(), "git commit was invoked")

    def test_a_git_without_git_hook_refuses_only_when_there_is_a_hook(self):
        # git before 2.36 has no `git hook run`. With a hook to run, the
        # binding cannot be made after it, so the commit is refused; with none,
        # nothing changes.
        old = self.tmp / "old-git"
        old.mkdir()
        (old / "git").write_text(
            "#!/bin/sh\n"
            'case $1 in version) echo "git version 2.34.1"; exit 0 ;;\n'
            "  hook) echo \"git: 'hook' is not a git command.\" >&2; exit 1 ;; esac\n"
            f'exec "{shutil.which("git")}" "$@"\n')
        (old / "git").chmod(0o755)
        self.env["PATH"] = f"{old}:{self.env['PATH']}"
        self.stage(content="x = 1")
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FEAT: x", "body")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.trailer("Bug-hunter-Tree"), self.git("rev-parse", "HEAD^{tree}"))
        self.install_hook(self.FORMATTER)
        self.stage(content="x = 2")
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FEAT: x", "body", shim=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("git (2.34.1) cannot run the pre-commit hook", result.stderr)
        self.assertIn("2.36", result.stderr)
        self.assertNotIn("the pre-commit hook did not pass", result.stderr)
        self.assertFalse(self.commit_marker.exists(), "git commit was invoked")
        self.assertEqual(self.hook_runs(), 0)


    # -- each hook runs once per commit ---------------------------------------
    #
    # See ../../../lib/commit-trailer/DECISIONS.md
    # #the-pre-commit-hook-runs-once-per-commit.

    def counting_hook(self, name, extra="", where=None):
        """A hook that logs its name to $HOOK_RUNS, then runs <extra>."""
        hooks = where or self.repo / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        hook = hooks / name
        hook.write_text(f'#!/bin/sh\necho {name} >>"$HOOK_RUNS"\n{extra}')
        hook.chmod(0o755)
        return hook

    def runs_of(self, name):
        runs = self.tmp / "hook-runs"
        return runs.read_text().splitlines().count(name) if runs.exists() else 0

    def test_each_hook_runs_once_in_a_two_family_commit(self):
        seen = self.tmp / "commit-msg-saw"
        self.counting_hook("pre-commit")
        self.counting_hook("prepare-commit-msg")
        self.counting_hook("commit-msg", f'cp "$1" "{seen}"\n')
        self.counting_hook("post-commit")
        self.stage(content="x = 1")
        value = self.demo_value("FEAT: x", "body")
        result = self.commit_with_env(*self.two_families(value))
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("pre-commit", "prepare-commit-msg", "commit-msg", "post-commit"):
            self.assertEqual(self.runs_of(name), 1, name)
        self.assert_both_families_landed(value)
        # commit-msg saw the message that landed, trailers included.
        self.assertEqual(seen.read_text().strip(), self.git("log", "-1", "--format=%B"))

    def test_pre_commit_is_not_run_again_on_a_state_it_passed_in(self):
        # The first attempt runs the hook, then is refused for another reason
        # (a stale signature). The second runs it again only if something it
        # could depend on changed.
        cases = {
            "nothing changed": (lambda hook: None, 1),
            "another file staged": (lambda hook: self.stage("g.py", "y = 2"), 2),
            "the hook edited": (lambda hook: hook.write_text(hook.read_text() + "# edited\n"), 2),
            "an unstaged change": (lambda hook: (self.repo / "f.py").write_text("x = 9"), 2),
        }
        for name, (change, runs) in cases.items():
            with self.subTest(name):
                (self.tmp / "hook-runs").unlink(missing_ok=True)
                hook = self.counting_hook("pre-commit")
                self.stage(content=f"x = {name!r}")
                result = self.commit_with_env(*self.two_families("\u2713 000000000000:000000000000"))
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("no longer matches", result.stderr)
                self.assertEqual(self.runs_of("pre-commit"), 1)
                change(hook)
                value = self.demo_value("FEAT: x", "body")
                result = self.commit_with_env(*self.two_families(value))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.runs_of("pre-commit"), runs)
                if runs == 1:
                    self.assertIn("already passed", result.stderr)
                self.assert_both_families_landed(value)

    def test_a_check_that_ran_the_hook_leaves_the_commit_nothing_to_run(self):
        # prose's flow: `prose check` runs run-pre-commit.sh, then signs, then
        # commits through the script. The hook runs once in all.
        self.install_hook(self.FORMATTER)
        self.stage(content="x = 1")
        self.env["HOOK_RUNS"] = str(self.tmp / "hook-runs")
        early = subprocess.run(["sh", str(self.LIB.parent / "run-pre-commit.sh")], cwd=self.repo,
                               capture_output=True, text=True, env=self.env)
        self.assertEqual((early.returncode, early.stdout), (0, "changed\n"), early.stderr)
        value = self.demo_value("FEAT: x", "body")
        result = self.commit_with_env(*self.two_families(value))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.hook_runs(), 1)
        self.assert_both_families_landed(value)

    def test_a_commit_msg_hook_that_edits_the_message(self):
        # A signature over the old message is refused; a minted binding, which
        # covers only the tree, still lands.
        self.counting_hook("commit-msg", 'sed "1s/^FEAT/feat/" "$1" >"$1.tmp" && mv "$1.tmp" "$1"\n')
        self.stage(content="x = 1")
        before = self.git("rev-parse", "HEAD")
        value = self.demo_value("FEAT: x", "body")
        result = self.commit_with_env(*self.two_families(value))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("the commit-msg hook changed the message after the value was made",
                      result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FEAT: x", "body")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "feat: x")
        self.assertEqual(self.trailer("Bug-hunter-Tree"), self.git("rev-parse", "HEAD^{tree}"))
        self.assertEqual(self.run_hook().returncode, QUIET)

    def test_a_verifier_sees_the_message_commit_msg_left_minus_the_added_trailers(self):
        # A Signed-off-by appended by the hook is part of the changed message.
        got = self.tmp / "verifier-got"
        verifier = self.tmp / "verifier"
        verifier.write_text(f'#!/bin/sh\ncat >>"{got}"; echo ===>>"{got}"\n')
        verifier.chmod(0o755)
        self.counting_hook("commit-msg", 'echo "Signed-off-by: S <s@x>" >>"$1"\n')
        self.stage(content="x = 1")
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--verified-value", str(verifier), "Prose", "v",
                                      "--co-authored-by", "A <a@x>", "--", "FEAT: x", "body")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(got.read_text(), "FEAT: x\n\nbody===\n"
                                          "FEAT: x\n\nbody\n\nSigned-off-by: S <s@x>===\n")
        self.assertEqual(self.trailer("Signed-off-by"), "S <s@x>")
        self.assertEqual(self.trailer("Bug-hunter-Tree"), self.git("rev-parse", "HEAD^{tree}"))

    def test_a_commit_msg_hook_that_drops_an_added_trailer_is_refused(self):
        self.counting_hook("commit-msg", 'grep -v "^Bug-hunter-Tree:" "$1" >"$1.tmp"; mv "$1.tmp" "$1"\n')
        self.stage(content="x = 1")
        before = self.git("rev-parse", "HEAD")
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FEAT: x", "body")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("removed or changed a trailer line this script added: Bug-hunter-Tree:",
                      result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def test_a_commit_msg_hook_that_rejects_commits_nothing(self):
        self.counting_hook("commit-msg", "echo 'subject must be lower case'\nexit 1\n")
        self.stage(content="x = 1")
        before = self.git("rev-parse", "HEAD")
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FEAT: x", "body")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("subject must be lower case", result.stderr)
        self.assertIn("the commit-msg hook rejected the message (exit 1)", result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.runs_of("commit-msg"), 1)

    # husky v9's generated files, as `husky` writes them into .husky/_ (minus
    # its ~/.config init file, which a test must not read).
    HUSKY_H = (
        "#!/usr/bin/env sh\n"
        '[ "$HUSKY" = "2" ] && set -x\n'
        'n=$(basename "$0")\n'
        's=$(dirname "$(dirname "$0")")/$n\n'
        '[ ! -f "$s" ] && exit 0\n'
        '[ "${HUSKY-}" = "0" ] && exit 0\n'
        'export PATH="node_modules/.bin:$PATH"\n'
        'sh -e "$s" "$@"\n'
        "c=$?\n"
        '[ $c != 0 ] && echo "husky - $n script failed (code $c)"\n'
        "exit $c\n"
    )
    HUSKY_WRAPPER = '#!/usr/bin/env sh\n. "$(dirname "$0")/h"\n'

    def test_husky_hooks_run_once_and_are_honoured(self):
        husky = self.repo / ".husky"
        generated = husky / "_"
        generated.mkdir(parents=True)
        (generated / ".gitignore").write_text("*\n")
        (generated / "h").write_text(self.HUSKY_H)
        for name in ("pre-commit", "commit-msg"):
            (generated / name).write_text(self.HUSKY_WRAPPER)
            (generated / name).chmod(0o755)
        # husky's own scripts are tracked and not executable.
        (husky / "pre-commit").write_text(self.FORMATTER.split("\n", 1)[1])
        (husky / "commit-msg").write_text('echo commit-msg >>"$HOOK_RUNS"\n')
        self.git("add", ".husky")
        self.git("commit", "-q", "-m", "husky", "--trailer", "Bug-hunter: skipped at triage (seed)")
        self.run_hook()
        self.git("config", "core.hooksPath", ".husky/_")
        self.stage(content="x = 1")
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FEAT: x", "body")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.hook_runs(), 2)   # pre-commit's "run", and commit-msg
        self.assertEqual(self.runs_of("commit-msg"), 1)
        self.assertEqual(self.git("show", "HEAD:f.py"), "x=1")
        self.assertEqual(self.trailer("Bug-hunter-Tree"), self.git("rev-parse", "HEAD^{tree}"))
        # An unstaged edit to husky's script runs the hook again.
        (self.tmp / "hook-runs").unlink()
        self.stage(content="x = 2")
        once = subprocess.run(["sh", str(self.LIB.parent / "run-pre-commit.sh")], cwd=self.repo,
                              capture_output=True, text=True, env=self.env)
        self.assertEqual(once.returncode, 0, once.stderr)
        (husky / "pre-commit").write_text((husky / "pre-commit").read_text() + "# edited\n")
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FEAT: x", "body")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.runs_of("run"), 2)

    def test_an_appending_commit_msg_hook_and_a_body_ending_in_a_hash_line(self):
        # interpret-trailers puts the trailers before a trailing `#` line, so
        # they are not in the message's last paragraph.
        self.counting_hook("commit-msg",
                           'git interpret-trailers --in-place --trailer "Signed-off-by: S <s@x>" "$1"\n')
        self.stage(content="x = 1")
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FIX: y", "Fix the thing.\n\n#42")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.trailer("Bug-hunter-Tree"), self.git("rev-parse", "HEAD^{tree}"))
        self.assertEqual(self.git("log", "-1", "--format=%B").splitlines()[-1], "#42")

    def test_commit_cleanup_verbatim_keeps_the_message_as_passed(self):
        self.git("config", "commit.cleanup", "verbatim")
        self.stage(content="x = 1")
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FIX: y", "text  ")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("log", "-1", "--format=%B").split("\n")[2], "text  ")

    def test_a_check_run_from_the_top_spares_a_commit_from_a_subdirectory(self):
        self.counting_hook("pre-commit")
        (self.repo / "sub").mkdir()
        self.stage(content="x = 1")
        self.env["HOOK_RUNS"] = str(self.tmp / "hook-runs")
        early = subprocess.run(["sh", str(self.LIB.parent / "run-pre-commit.sh")], cwd=self.repo,
                               capture_output=True, text=True, env=self.env)
        self.assertEqual(early.returncode, 0, early.stderr)
        result = subprocess.run(["sh", str(self.LIB), "--minted", "Bug-hunter", "0 bugs found",
                                 "--", "FIX: y", "body"], cwd=self.repo / "sub",
                                capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.runs_of("pre-commit"), 1)

    def test_a_verified_family_before_a_minted_one_gets_the_message(self):
        self.stage(content="x = 1")
        value = self.demo_value("FEAT: x", "body")
        result = self.commit_with_env("--verified-value", str(self.demo), "Prose", value,
                                      "--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FEAT: x", "body")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.trailer("Prose"), value)

    def test_commit_cleanup_verbatim_adds_no_newline_to_a_body_that_ends_in_one(self):
        self.git("config", "commit.cleanup", "verbatim")
        self.stage(content="x = 1")
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FIX: y", "body\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        stored = subprocess.run(["git", "cat-file", "commit", "HEAD"], cwd=self.repo,
                                capture_output=True, text=True).stdout
        self.assertFalse(stored.endswith("\n\n"), repr(stored[-80:]))

    def test_a_config_change_the_hook_reads_runs_it_again(self):
        # git's own pre-commit.sample reads hooks.allownonascii.
        self.counting_hook("pre-commit",
                           '[ "$(git config --bool hooks.allownonascii)" = true ] || exit 1\n')
        self.git("config", "hooks.allownonascii", "true")
        self.stage(content="x = 1")
        self.env["HOOK_RUNS"] = str(self.tmp / "hook-runs")
        early = subprocess.run(["sh", str(self.LIB.parent / "run-pre-commit.sh")], cwd=self.repo,
                               capture_output=True, text=True, env=self.env)
        self.assertEqual(early.returncode, 0, early.stderr)
        self.git("config", "hooks.allownonascii", "false")
        before = self.git("rev-parse", "HEAD")
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FIX: y", "body")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def run_pre_commit(self):
        self.env["HOOK_RUNS"] = str(self.tmp / "hook-runs")
        return subprocess.run(["sh", str(self.LIB.parent / "run-pre-commit.sh")], cwd=self.repo,
                              capture_output=True, text=True, env=self.env)

    def assert_a_failing_hook_refuses_the_commit(self):
        before = self.git("rev-parse", "HEAD")
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FIX: y", "body")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def test_without_hooks_the_commit_is_a_plain_git_commit(self):
        # The hook path (commit-with-hooks.sh) runs only when there is a hook
        # to run; otherwise the script commits as it did before it existed.
        log = self.tmp / "git-commits"
        shim = self.tmp / "logshim"
        shim.mkdir()
        (shim / "git").write_text(
            "#!/bin/sh\n"
            f'case " $* " in *" commit "*) printf "%s\\n" "$*" >>"{log}" ;; esac\n'
            f'exec "{shutil.which("git")}" "$@"\n')
        (shim / "git").chmod(0o755)
        self.env["PATH"] = f"{shim}:{self.env['PATH']}"
        self.stage(content="x = 1")
        result = self.commit_with_env("--minted", "Bug-hunter", "0 bugs found",
                                      "--", "FIX: y", "body")
        self.assertEqual(result.returncode, 0, result.stderr)
        commits = log.read_text().splitlines()
        self.assertEqual(len(commits), 1, commits)
        self.assertIn(" commit -m FIX: y -m body --trailer Bug-hunter: 0 bugs found", commits[0])
        self.assertNotIn("--no-verify", commits[0])
        self.assertFalse((self.repo / ".git" / "commit-trailer").exists())
        self.assertEqual(self.trailer("Bug-hunter-Tree"), self.git("rev-parse", "HEAD^{tree}"))

    def test_a_config_hook_is_recorded_like_a_hook_file(self):
        # git 2.54's hook.<name>.command. All config is in the recorded state,
        # so changing the command reruns the hook; its script's own content is
        # not (a recorded limitation, like a gitignored file a hook loads).
        counter = self.tmp / "runs"
        script = self.tmp / "lint"
        script.write_text(f"#!/bin/sh\necho run >> {counter}\nexit 0\n")
        script.chmod(0o755)
        self.git("config", "hook.lint.event", "pre-commit")
        self.git("config", "hook.lint.command", str(script))
        if subprocess.run(["git", "hook", "run", "pre-commit"], cwd=self.repo,
                          capture_output=True).returncode != 0:
            self.skipTest("this git does not run hooks defined in config")
        counter.unlink(missing_ok=True)
        self.stage(content="x = 1")
        for _ in range(2):
            result = self.run_pre_commit()
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(counter.read_text().count("run"), 1,
                         "a passed config hook ran again on the same state")
        self.git("config", "hook.lint.command", f"{script} --strict")
        result = self.run_pre_commit()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(counter.read_text().count("run"), 2,
                         "changing the config hook's command did not rerun it")

    def test_an_edit_inside_a_dirty_submodule_runs_the_hook_again(self):
        # git diff shows a dirty submodule as one "-dirty" line, whatever the
        # edits inside it are.
        sub = self.tmp / "sub-origin"
        sub.mkdir()
        for args in (("init", "-q", "-b", "main"), ("add", "."),
                     ("-c", "user.name=T", "-c", "user.email=t@e.com", "-c",
                      "commit.gpgsign=false", "commit", "-q", "-m", "seed")):
            if args[0] == "add":
                (sub / "f").write_text("ok\n")
            subprocess.run(["git", *args], cwd=sub, check=True)
        self.git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "lib")
        self.git("commit", "-q", "-m", "sub", "--trailer", "Bug-hunter: skipped at triage (seed)")
        self.counting_hook("pre-commit", "! grep -q BAD lib/f\n")
        (self.repo / "lib" / "f").write_text("ok2\n")
        self.stage(content="x = 1")
        early = self.run_pre_commit()
        self.assertEqual(early.returncode, 0, early.stderr)
        (self.repo / "lib" / "f").write_text("BAD\n")
        self.assert_a_failing_hook_refuses_the_commit()

    # -- bug-hunter's commit script forwards other skills' families ---------
    #
    # Its commit step carries every installed skill's trailer on one commit
    # (../../../lib/commit-trailer/DECISIONS.md#every-installed-skills-trailer-on-one-commit),
    # so it passes --verified-value families through to the library and
    # refuses every other option.

    def wrap(self, *args, shim=False):
        env = {**self.env, **({"SHIM_COMMIT": "1"} if shim else {})}
        return subprocess.run(["sh", str(WRAPPER), *args], cwd=self.repo,
                              capture_output=True, text=True, env=env)

    def other_demo(self):
        script = self.tmp / "other-sig"
        script.write_text(self.VALUE_DEMO.replace("Prose:", "Other:"))
        script.chmod(0o755)
        return script

    def test_the_wrapper_lands_its_family_and_two_forwarded_ones_on_one_commit(self):
        self.stage()
        other = self.other_demo()
        prose = self.prose_value(self.demo, "FEAT: x", "body")
        mine = self.prose_value(other, "FEAT: x", "body")
        result = self.wrap("--verified-value", str(self.demo), "Prose", prose,
                           "--verified-value", str(other), "Other", mine, "--",
                           "FEAT: x", "body", "1 iteration, 0 bugs found", "A <a@x>")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.verified_marker.exists(), "the verifier never ran")
        self.assertEqual(self.trailer_block(), [
            "Bug-hunter: 1 iteration, 0 bugs found",
            f"Bug-hunter-Tree: {self.git('rev-parse', 'HEAD^{tree}')}",
            f"Prose: {prose}",
            f"Other: {mine}",
            "Co-Authored-By: A <a@x>",
        ])
        self.assertEqual(self.git("log", "-1", "--format=%s"), "FEAT: x")
        self.assertEqual(self.run_hook().returncode, QUIET)

    def test_the_wrapper_without_families_takes_an_optional_separator(self):
        self.stage()
        result = self.wrap("--", "FEAT: x", "", "0 bugs found")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.trailer("Bug-hunter"), "0 bugs found")
        self.assertEqual(self.git("log", "-1", "--format=%s"), "FEAT: x")

    def test_the_wrapper_refuses_a_malformed_family_before_anything_runs(self):
        self.stage()
        good = self.prose_value(self.demo, "FEAT: x", "body")
        shutil.copy(self.demo, self.repo / "prose-sig")
        fam = ["--verified-value", str(self.demo), "Prose"]
        tail = ["FEAT: x", "body", "0 bugs found"]
        cases = {
            "no -- after the family": [*fam, good, *tail],
            "the value vanished": [*fam, "--", *tail],
            "the key and value vanished": ["--verified-value", str(self.demo), "--", *tail],
            "too few words": [*fam],
            "bare tool name": ["--verified-value", "prose-sig", "Prose", good, "--", *tail],
            "empty value": [*fam, " ", "--", *tail],
            "multi-line value": [*fam, good + "\nx", "--", *tail],
            "the Bug-hunter key": ["--verified-value", str(self.demo), "Bug-hunter", good, "--", *tail],
            "a key inside Bug-hunter's": ["--verified-value", str(self.demo), "Bug-hunter-Tree", good, "--", *tail],
            "no subject left": [*fam, good, "--", "FEAT: x", "body"],
        }
        for name, args in cases.items():
            with self.subTest(name):
                result = self.wrap(*args, shim=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse(self.verified_marker.exists(), "verifier ran after a bad argument")
                self.assertFalse(self.commit_marker.exists(), "git commit was invoked")

    def test_the_wrapper_refuses_a_stale_forwarded_value_and_commits_nothing(self):
        self.stage()
        value = self.prose_value(self.demo, "FEAT: x", "body")
        before = self.git("rev-parse", "HEAD")
        result = self.wrap("--verified-value", str(self.demo), "Prose", value, "--",
                           "FEAT: edited after signing", "body", "0 bugs found")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("no longer matches", result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def test_the_wrapper_still_refuses_every_other_option(self):
        # The wrapper adds the Bug-hunter family and Co-Authored-By itself.
        # Anything else in front of the subject would be read as the subject,
        # or would add a family the wrapper does not vouch for.
        self.stage()
        good = self.prose_value(self.demo, "FEAT: x", "body")
        fam = ["--verified-value", str(self.demo), "Prose", good]
        tail = ["FEAT: x", "body", "0 bugs found"]
        cases = {
            "--minted in front": ["--minted", "Other", "x", "--", *tail],
            "--minted-by in front": ["--minted-by", str(MINT), "Other", "x", "--", *tail],
            "--co-authored-by in front": ["--co-authored-by", "A <a@x>", "--", *tail],
            "--minted after a family": [*fam, "--minted", "Other", "x", "--", *tail],
            "--minted as the subject after --": [*fam, "--", "--minted", "body", "0 bugs found"],
            "-- as the subject": ["--", "--", "body", "0 bugs found"],
            "an option name as the Bug-hunter value": [*fam, "--", "FEAT: x", "body", "--verified-value"],
            "an option name as the co-author": [*fam, "--", *tail, "--co-authored-by"],
        }
        for name, args in cases.items():
            with self.subTest(name):
                result = self.wrap(*args, shim=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse(self.verified_marker.exists(), "verifier ran after a bad argument")
                self.assertFalse(self.commit_marker.exists(), "git commit was invoked")

    # --message-file: the message from a file, never quoted on a command line.
    # See ../../../lib/commit-trailer/DECISIONS.md#the-message-comes-from-a-file.

    def message_file(self, text, name="msg.txt"):
        path = self.tmp / name
        path.write_text(text)
        return path

    def test_a_message_file_gives_the_subject_body_and_both_families(self):
        self.stage()
        subject, body = "FEAT: it's \"quoted\" $HOME `id`", "First line.\n\nSecond paragraph, it's fine."
        value = self.demo_value(subject, body)
        path = self.message_file(f"{subject}\n\n{body}\n")
        families = self.two_families(value)[:-3]  # every family, without '--' <subject> <body>
        result = self.commit(*families, "--message-file", str(path), "--")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("log", "-1", "--format=%s"), subject)
        self.assertTrue(self.git("log", "-1", "--format=%b").startswith(body), self.git("log", "-1", "--format=%b"))
        self.assert_both_families_landed(value)

    def test_a_message_file_with_only_a_subject_commits(self):
        self.stage()
        value = self.demo_value("FEAT: x", "")
        families = self.two_families(value)[:-3]
        result = self.commit(*families, "--message-file", str(self.message_file("FEAT: x\n")), "--")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "FEAT: x")
        self.assert_both_families_landed(value)

    def test_a_bad_message_file_is_refused_and_nothing_is_committed(self):
        self.stage()
        head = self.git("rev-parse", "HEAD")
        families = self.two_families("✓ 0123abcd4567:89abcdef0123")[:-3]
        cases = {
            "missing": (["--message-file", str(self.tmp / "nope.txt"), "--"], "cannot read"),
            "empty subject": (["--message-file", str(self.message_file("\n  \n\n", "e.txt")), "--"],
                              "subject is empty"),
            "no blank second line": (["--message-file", str(self.message_file("FEAT: x\nmore\n", "s.txt")), "--"],
                                     "second line is not blank"),
            "a file and words": (["--message-file", str(self.message_file("FEAT: x\n", "b.txt")), "--",
                                  "FEAT: x", "body"], "not both"),
            "no '--' after it": (["--message-file", str(self.message_file("FEAT: x\n", "d.txt"))], "usage:"),
            "given twice": (["--message-file", str(self.message_file("FEAT: x\n", "t.txt")),
                             "--message-file", str(self.message_file("FEAT: x\n", "t2.txt")), "--"], "twice"),
            "a vanished path": (["--message-file", "--"], "missing an argument"),
        }
        for name, (tail, expected) in cases.items():
            with self.subTest(name):
                result = self.commit(*families, *tail)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(expected, result.stderr)
                self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_a_message_file_starting_with_a_blank_line_commits_like_git_would(self):
        self.stage()
        value = self.demo_value("FEAT: x", "body")
        families = self.two_families(value)[:-3]
        result = self.commit(*families, "--message-file", str(self.message_file("\nFEAT: x\n\nbody\n")), "--")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "FEAT: x")

    def test_the_message_file_option_after_the_dashes_is_refused(self):
        self.stage()
        head = self.git("rev-parse", "HEAD")
        families = self.two_families("✓ 0123abcd4567:89abcdef0123")[:-3]
        path = str(self.message_file("FEAT: x\n"))
        for words in (["--message-file", path], ["-F", path]):
            with self.subTest(words[0]):
                result = self.commit(*families, "--", *words)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("before", result.stderr)
                self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_bug_hunters_script_refuses_other_spellings_of_the_file_option(self):
        self.stage()
        head = self.git("rev-parse", "HEAD")
        path = str(self.message_file("FEAT: x\n\nbody\n"))
        for first in ("-F" + path, "--message-file=" + path, "--file"):
            with self.subTest(first):
                result = subprocess.run(["sh", str(WRAPPER), first, "1 iteration, 0 bugs found", "A <a@x>"],
                                        cwd=self.repo, capture_output=True, text=True, env=self.env)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("-F <file>", result.stderr)
                self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_a_line_git_keeps_is_never_dropped_from_a_message_file(self):
        # git and prose count only space, tab and CR as blank; a form feed or a
        # no-break space is text, so dropping that line would change the message.
        for name, text in (("form feed first", "\f\nFEAT: x\n\nbody\n"),
                           ("no-break space between", "FEAT: x\n \nbody\n")):
            with self.subTest(name):
                self.stage(content=name)
                result = self.commit("--minted", "Bug-hunter", "1 iteration, 0 bugs found",
                                     "--message-file", str(self.message_file(text)), "--")
                committed = self.git("log", "-1", "--format=%B")
                self.assertFalse(result.returncode == 0 and "\f" not in committed and " " not in committed,
                                 f"a line git keeps was dropped: {committed!r}")

    def test_a_positional_subject_starting_with_dash_f_still_commits(self):
        self.stage()
        result = self.commit("--minted", "Bug-hunter", "1 iteration, 0 bugs found", "--", "-Fix typo", "body")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "-Fix typo")

    def test_bug_hunters_script_takes_a_message_file(self):
        self.stage()
        path = self.message_file("FEAT: x\n\nbody\n")
        result = subprocess.run(["sh", str(WRAPPER), "-F", str(path), "1 iteration, 0 bugs found", "A <a@x>"],
                                cwd=self.repo, capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "FEAT: x")
        self.assertEqual(self.trailer("Bug-hunter-Tree"), self.git("rev-parse", "HEAD^{tree}"))
        self.assertEqual(self.trailer("Co-Authored-By"), "A <a@x>")

    def test_bug_hunters_script_takes_a_message_file_beside_another_family(self):
        self.stage()
        value = self.demo_value("FEAT: x", "body")
        path = self.message_file("FEAT: x\n\nbody\n")
        result = subprocess.run(["sh", str(WRAPPER), "--verified-value", str(self.demo), "Prose", value, "--",
                                 "-F", str(path), "1 iteration, 0 bugs found", "A <a@x>"],
                                cwd=self.repo, capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_both_families_landed(value)


class SkillVerifyTests(unittest.TestCase):
    """A skill's report file may define commit_trailer_verify, which the hook
    calls instead of the <Key>-Tree check. A demo skill, `demo` / `Demo:`,
    whose valid value is `ok <12 hex tree of the commit>`. See
    ../../../lib/commit-trailer/DECISIONS.md#a-skill-may-verify-its-own-trailer.
    """

    GIT = ["git", "-c", "user.name=T", "-c", "user.email=t@e.com",
           "-c", "commit.gpgsign=false"]
    LIB = HOOK.parent.parent.parent.parent / "lib" / "commit-trailer" / "check-commit-trailer.sh"
    REPORT = (
        'commit_trailer_report() {\n'
        '  REPORT="demo report\n'
        'unchecked: $unchecked\n'
        'unminted: $unminted\n'
        'rejected: $rejected"\n'
        '}\n'
    )
    VERIFY = (
        'commit_trailer_verify() {\n'
        '  case $2 in skipped*) return 0 ;; esac  # skip notes reach the skill too\n'
        '  [ "$2" = broken ] && { echo "no verifier here"; return 3; }\n'
        '  t=$(git rev-parse --short=12 "$1^{tree}")\n'
        '  [ "$2" = "ok $t" ] && return 0\n'
        '  echo "tree $t is not what $2 names"; return 1\n'
        '}\n'
    )

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="bh-verify-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.repo, check=True)
        self.commit("seed", "Demo: skipped (seed)", allow_empty=True)
        self.use_report(self.REPORT + self.VERIFY)
        self.assertEqual(self.hook().returncode, QUIET)  # settles the cursor

    def use_report(self, text):
        report = self.tmp / "report.sh"
        report.write_text(text)
        self.wrapper = self.tmp / "demo-hook.sh"
        self.wrapper.write_text(
            f"COMMIT_TRAILER_SKILL=demo\nCOMMIT_TRAILER_KEY=Demo\n"
            f"COMMIT_TRAILER_REPORT='{report}'\n. '{self.LIB}'\n")

    def hook(self, shell="sh"):
        return subprocess.run(
            [shell, str(self.wrapper), "--host", "claude"],
            input=json.dumps({"cwd": str(self.repo)}),
            capture_output=True, text=True, cwd=self.repo)

    def git(self, *args):
        result = subprocess.run(self.GIT + list(args), cwd=self.repo,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def commit(self, subject, trailer, allow_empty=False, name="f.py", content="x"):
        if not allow_empty:
            (self.repo / name).write_text(content)
            self.git("add", name)
        self.git("commit", "-q", *(["--allow-empty"] if allow_empty else []),
                 "-m", subject, "--trailer", trailer)

    def tree12(self):
        return self.git("write-tree")[:12]

    def test_a_value_the_skill_accepts_is_quiet(self):
        # A commit per shell: the first run moves the cursor past its commit.
        for shell in ("sh",) + (("dash",) if shutil.which("dash") else ()):
            with self.subTest(shell=shell):
                self.commit(f"FEAT: valid ({shell})",
                            f"Demo: ok {self.tree12_after('f.py', shell)}", content=shell)
                result = self.hook(shell)
                self.assertEqual(result.returncode, QUIET, result.stderr)
                # and the same shell does report a forgery, so the quiet is earned
                self.commit(f"FEAT: forged ({shell})", "Demo: ok 000000000000",
                            content=shell + "!")
                self.assertEqual(self.hook(shell).returncode, REPORTED)

    def test_the_callback_does_not_inherit_the_hooks_set_u(self):
        # The hook runs under `set -u`. A callback that reads an unset
        # variable aborted before returning: "rejected" under bash, "could not
        # be verified" under dash, for a commit the callback accepts.
        self.use_report(self.REPORT + self.VERIFY.replace(
            'commit_trailer_verify() {\n',
            'commit_trailer_verify() {\n  [ "$2" = lenient ] && [ -z "$OPTIONAL_SETTING" ] && return 0\n'))
        for shell in ("sh",) + (("dash",) if shutil.which("dash") else ()):
            with self.subTest(shell=shell):
                self.commit(f"FEAT: lenient ({shell})", "Demo: lenient", content=shell)
                result = self.hook(shell)
                self.assertEqual(result.returncode, QUIET, result.stderr)

    def test_an_amended_replay_is_not_asked_either(self):
        # A message-only amend of a cherry-pick is still a tree some replay
        # landed: out of scope, whatever the skill would have answered.
        self.git("checkout", "-q", "-b", "side")
        self.commit("FEAT: side", "Demo: broken", name="side.py", content="side")
        self.assertEqual(self.hook().returncode, REPORTED)
        self.git("checkout", "-q", "main")
        self.git("cherry-pick", "side")
        self.assertEqual(self.hook().returncode, QUIET)
        self.git("commit", "-q", "--amend", "-m", "FEAT: side, reworded", "-m", "Demo: broken")
        result = self.hook()
        self.assertEqual(result.returncode, QUIET, result.stderr)

    def test_a_value_the_skill_rejects_is_reported_with_its_reason(self):
        self.commit("FEAT: forged", "Demo: ok 000000000000")
        result = self.hook()
        self.assertEqual(result.returncode, REPORTED, result.stderr)
        self.assertIn("rejected:", result.stderr)
        self.assertIn("FEAT: forged -- tree", result.stderr)
        self.assertIn("is not what ok 000000000000 names", result.stderr)
        self.assertNotIn("unminted: " + "FEAT", result.stderr)

    def test_a_verifier_that_cannot_decide_is_said_out_loud(self):
        self.commit("FEAT: unknown", "Demo: broken")
        result = self.hook()
        self.assertEqual(result.returncode, REPORTED, result.stderr)
        self.assertIn("could not be verified (exit 3): no verifier here", result.stderr)

    def test_a_replay_is_not_asked(self):
        # A cherry-pick carries a valid value onto another tree; a message-only
        # amend of it rewrites the reflog action to `commit (amend):`.
        self.git("checkout", "-q", "-b", "side")
        self.commit("FEAT: side", f"Demo: ok {self.tree12_after('side.py', 'side')}",
                    name="side.py", content="side")
        self.assertEqual(self.hook().returncode, QUIET)
        self.git("checkout", "-q", "main")
        self.commit("FEAT: main moves", f"Demo: ok {self.tree12_after('m.py', 'm')}",
                    name="m.py", content="m")
        self.assertEqual(self.hook().returncode, QUIET)
        self.git("cherry-pick", "side")
        self.assertEqual(self.hook().returncode, QUIET)
        self.git("commit", "-q", "--amend", "-m", "FEAT: side, reworded",
                 "-m", f"Demo: ok {self.git('log', '-1', '--format=%(trailers:key=Demo,valueonly)').split()[-1]}")
        result = self.hook()
        self.assertEqual(result.returncode, QUIET, result.stderr)

    def test_a_replay_is_not_asked_even_when_the_skill_cannot_decide(self):
        # Scoped to plain commits and amends: the replay is never handed to
        # the skill, so its answer cannot matter.
        self.git("checkout", "-q", "-b", "side")
        self.commit("FEAT: side", "Demo: broken", name="side.py", content="side")
        self.assertEqual(self.hook().returncode, REPORTED)  # the original is judged
        self.git("checkout", "-q", "main")
        self.git("cherry-pick", "side")
        result = self.hook()
        self.assertEqual(result.returncode, QUIET, result.stderr)

    def hook_cursor(self):
        return subprocess.run(
            ["sh", str(self.wrapper), "--host", "cursor"],
            input=json.dumps({"cwd": str(self.repo)}),
            capture_output=True, text=True, cwd=self.repo)

    def test_a_report_file_printing_at_load_keeps_cursors_json_whole(self):
        # Cursor reads stdout as one JSON document. Output from the report
        # file's top level reached it from the callback check, and landed in
        # the callback's reason too.
        for verify in ("", self.VERIFY):
            with self.subTest(callback=bool(verify)):
                self.use_report('echo "loaded at top level"\n' + self.REPORT + verify)
                self.commit(f"FEAT: forged {bool(verify)}", "Demo: ok 000000000000",
                            content=str(bool(verify)))
                result = self.hook_cursor()
                self.assertEqual(result.returncode, 0, result.stderr)
                context = json.loads(result.stdout)["additional_context"]
                self.assertNotIn("-- loaded at top level", context)

    def test_the_callback_check_and_the_report_do_not_inherit_set_u(self):
        # An unset read at the report file's top level made the callback check
        # fail silently, falling back to the tree check; one inside the report
        # function lost the skill's report.
        self.use_report(': "$OPTIONAL_SETTING"\n' + self.REPORT.replace(
            'REPORT="demo report', 'REPORT="demo report$OPTIONAL_SETTING') + self.VERIFY)
        self.commit("FEAT: valid", f"Demo: ok {self.tree12_after('f.py', 'v')}", content="v")
        result = self.hook()
        self.assertEqual(result.returncode, QUIET, result.stderr)
        self.commit("FEAT: forged", "Demo: ok 000000000000", content="w")
        result = self.hook()
        self.assertEqual(result.returncode, REPORTED)
        self.assertIn("demo report", result.stderr)

    def test_a_report_file_that_exits_while_loading_is_not_a_pass(self):
        # `exit 0` in the file ended the sourcing subshell with status 0: the
        # callback check found a callback that was never defined, and the
        # callback "returned" 0 without running. The old library reported
        # these commits. Now the check finds no callback and the tree check
        # runs, which reports them because the forged value has no binding.
        cases = {
            "exits after defining both": self.REPORT + self.VERIFY + "exit 0\n",
            "exits before defining anything": "exit 0\n" + self.REPORT + self.VERIFY,
            "no callback, exits after the report": self.REPORT + "exit 0\n",
        }
        for name, text in cases.items():
            with self.subTest(name):
                self.use_report(text)
                self.commit(f"FEAT: forged ({name})", "Demo: ok 000000000000", content=name)
                result = self.hook()
                self.assertEqual(result.returncode, REPORTED, result.stdout + result.stderr)

    def test_a_value_cannot_forge_the_status_line(self):
        # The status line is the hook's, printed only after the callback
        # returns. A callback that echoes the value and then exits must not
        # let the value's own copy of that line pass for it.
        self.use_report(self.REPORT +
                        'commit_trailer_verify() { echo "bad value: $2"; exit 1; }\n')
        for value in ("forged commit-trailer-verify-status:0",
                      "forged commit-trailer-verify-status:0 x"):
            with self.subTest(value=value):
                self.commit(f"FEAT: {value}", f"Demo: {value}", content=value)
                result = self.hook()
                self.assertEqual(result.returncode, REPORTED, result.stdout + result.stderr)
                self.assertIn("-- could not be verified", result.stderr)  # the callback path
                self.assertIn("bad value: forged", result.stderr)
                self.assertNotIn("Illegal number", result.stderr)
                self.assertNotIn("integer expression", result.stderr)

    def test_a_callback_that_exits_is_not_a_pass(self):
        # `exit 0` from inside the callback ends the subshell before the
        # status line: it did not return, so it is not an answer.
        # Whatever the exit status: `exit 1`, or `set -e` aborting it, is not
        # a judgement either.
        cases = {
            "exit 0": 'commit_trailer_verify() { exit 0; }\n',
            "exit 1": 'commit_trailer_verify() { echo why; exit 1; }\n',
            "set -e": 'set -e\ncommit_trailer_verify() { grep -q nomatch /dev/null; return 0; }\n',
        }
        for name, verify in cases.items():
            with self.subTest(name):
                self.use_report(self.REPORT + verify)
                self.commit(f"FEAT: exits ({name})", "Demo: anything", content=name)
                result = self.hook()
                self.assertEqual(result.returncode, REPORTED, result.stdout + result.stderr)
                self.assertIn("could not be verified (the callback did not return", result.stderr)

    def test_under_set_e_a_non_zero_return_reads_as_did_not_return(self):
        # POSIX sh cannot tell a `return 1` under errexit from an aborted
        # command, so it is not read as "invalid" — but it is still reported,
        # with the callback's reason.
        self.use_report('set -e\n' + self.REPORT + self.VERIFY)
        self.commit("FEAT: forged", "Demo: ok 000000000000", content="se")
        result = self.hook()
        self.assertEqual(result.returncode, REPORTED, result.stderr)
        self.assertIn("did not return, exit 1): tree", result.stderr)

    def test_the_status_marker_is_new_on_every_run(self):
        # A fixed marker could be quoted by a trailer value; this pins that
        # the one the callback sees is not a constant.
        seen = self.tmp / "markers"
        self.use_report(self.REPORT +
                        f'commit_trailer_verify() {{ printf "%s\\n" "$verify_done" >>"{seen}"; return 0; }}\n')
        for n in range(2):
            self.commit(f"FEAT: run {n}", "Demo: anything", content=str(n))
            self.assertEqual(self.hook().returncode, QUIET)
        markers = seen.read_text().split()
        self.assertEqual(len(markers), 2)
        self.assertNotEqual(markers[0], markers[1])
        self.assertNotIn("commit-trailer-verify-status:", markers)

    def tree12_after(self, name, content):
        (self.repo / name).write_text(content)
        self.git("add", name)
        return self.tree12()

    def test_without_the_callback_the_tree_check_is_unchanged(self):
        self.use_report(self.REPORT)
        self.commit("FEAT: unbound", "Demo: 1 iteration, 0 bugs found")
        result = self.hook()
        self.assertEqual(result.returncode, REPORTED, result.stderr)
        self.assertIn("unminted: ", result.stderr)
        self.assertIn("FEAT: unbound", result.stderr.split("unminted: ", 1)[1].split("rejected:")[0])
        self.assertIn("rejected: ", result.stderr)
        self.assertNotIn("-- ", result.stderr.split("rejected:", 1)[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)

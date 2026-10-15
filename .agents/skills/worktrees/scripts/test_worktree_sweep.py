#!/usr/bin/env python3
"""Regression tests for worktree-sweep.py.

Standard library only:

    python3 test_worktree_sweep.py

Each test builds a throwaway repo with a bare origin in a temp directory and
runs the hook as a subprocess, with HOME and the mode config pointed into that
directory, so nothing here can touch a real repository or setting.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HOOK = pathlib.Path(__file__).resolve().parent / "worktree-sweep.py"


class SweepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="worktrees-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
            "HOME": str(self.tmp / "home"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
            "WORKTREES_CONFIG": str(self.tmp / "worktrees.json"),
        }
        (self.tmp / "home").mkdir()
        self.origin = self.tmp / "origin.git"
        self.repo = self.tmp / "repo"
        self.elsewhere = self.tmp / "not-a-repo"
        self.elsewhere.mkdir()
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.git(self.tmp, "clone", "-q", str(self.origin), str(self.repo))
        self.commit(self.repo, "first")
        self.git(self.repo, "push", "-q", "origin", "HEAD:main")
        self.git(self.repo, "fetch", "-q", "origin")

    # -- helpers ----------------------------------------------------------

    def git(self, cwd, *args):
        r = subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=cwd,
                           env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout.strip()

    def commit(self, cwd, name):
        (pathlib.Path(cwd) / f"{name}.txt").write_text(name)
        self.git(cwd, "add", ".")
        self.git(cwd, "commit", "-q", "-m", name)

    def worktree(self, name, start="origin/main"):
        path = self.repo / ".claude" / "worktrees" / name
        self.git(self.repo, "worktree", "add", "-q", "-b", name, str(path), start)
        return path

    def landed(self, name="feature"):
        """A worktree with one commit, pushed to its own branch."""
        path = self.worktree(name)
        self.commit(path, name)
        self.git(path, "push", "-q", "origin", f"HEAD:{name}")
        return path

    def git_dirs(self):
        """Every worktree's own git directory, in every repo the test made."""
        return list(self.tmp.glob("*/.git/worktrees/*"))

    def age(self, git_dir, hours):
        """Makes everything in a git directory look last changed `hours` ago,
        including the entries of its HEAD reflogs (its own and its
        submodules'), whose timestamps the hook reads."""
        then = time.time() - hours * 3600
        for log in git_dir.rglob("logs/HEAD"):
            lines = []
            for line in log.read_text().splitlines():
                head, tab, message = line.partition("\t")
                fields = head.split(" ")
                fields[-2] = str(int(then))
                lines.append(" ".join(fields) + tab + message)
            log.write_text("".join(f"{line}\n" for line in lines))
        for p in (git_dir, *git_dir.rglob("*")):
            os.utime(p, (then, then), follow_symlinks=False)

    def age_pushes(self, repo=None, seconds=7200):
        """Makes every push recorded in a repo's remote-tracking reflogs look
        `seconds` old: by default two hours, so the next push check sees no
        push."""
        then = int(time.time()) - seconds
        logs = (repo or self.repo) / ".git" / "logs" / "refs" / "remotes"
        for log in logs.rglob("*"):
            if log.is_file():
                lines = []
                for line in log.read_text().splitlines():
                    head, tab, message = line.partition("\t")
                    fields = head.split(" ")
                    fields[-2] = str(then)
                    lines.append(" ".join(fields) + tab + message)
                log.write_text("\n".join(lines) + "\n")
                os.utime(log, (then, then))

    def run_hook(self, payload, host="claude", mode=None, raw=None, cwd=None, aged=True):
        """Runs the hook. Unless aged is False, every worktree first looks
        last used two hours ago, past the hook's recency guard."""
        if aged:
            for d in self.git_dirs():
                self.age(d, 2)
        env = dict(self.env)
        if mode:
            env["WORKTREES_MODE"] = mode
        stdin = raw if raw is not None else json.dumps(payload)
        r = subprocess.run([sys.executable, str(HOOK), "--host", host], input=stdin,
                           cwd=cwd or self.elsewhere, env=env, capture_output=True, text=True,
                           timeout=60)
        return r

    def stop(self, **extra):
        return {"hook_event_name": "Stop", "cwd": str(self.repo), **extra}

    def push(self, command, cwd=None):
        """A push check's payload. Its cwd defaults to the feature worktree, so
        the hook takes that worktree as the session's own. The push it finds
        is the one landed() already made."""
        cwd = cwd or self.repo / ".claude" / "worktrees" / "feature"
        return {"hook_event_name": "PostToolUse", "cwd": str(cwd),
                "tool_name": "Bash", "tool_input": {"command": command}}

    def listed(self, r):
        return r.stdout + r.stderr

    # -- which worktrees are listed ---------------------------------------

    def test_lists_a_worktree_pushed_to_its_own_branch(self):
        path = self.landed()
        r = self.run_hook(self.stop())
        self.assertIn(str(path), self.listed(r))
        self.assertIn("on origin/feature", self.listed(r))

    def test_lists_a_worktree_pushed_straight_to_main(self):
        path = self.worktree("direct")
        self.commit(path, "direct")
        self.git(path, "push", "-q", "origin", "HEAD:main")
        r = self.run_hook(self.stop())
        self.assertIn(str(path), self.listed(r))
        self.assertIn("on origin/main", self.listed(r))

    def test_skips_a_fresh_checkout_made_for_review(self):
        self.git(self.repo, "push", "-q", "origin", "HEAD:review-me")
        self.git(self.repo, "fetch", "-q", "origin")
        path = self.worktree("review-me", "origin/review-me")
        r = self.run_hook(self.stop())
        self.assertNotIn(str(path), self.listed(r))
        self.assertEqual(r.returncode, 0)

    def test_skips_an_unpushed_commit(self):
        path = self.worktree("local")
        self.commit(path, "local")
        r = self.run_hook(self.stop())
        self.assertNotIn(str(path), self.listed(r))

    def test_skips_a_modified_tracked_file(self):
        path = self.landed()
        (path / "feature.txt").write_text("changed")
        self.assertNotIn(str(path), self.listed(self.run_hook(self.stop())))

    def test_skips_an_untracked_file(self):
        path = self.landed()
        (path / "scratch.txt").write_text("new")
        self.assertNotIn(str(path), self.listed(self.run_hook(self.stop())))

    def test_skips_an_untracked_file_when_status_hides_untracked_files(self):
        path = self.landed()
        self.git(self.repo, "config", "status.showUntrackedFiles", "no")
        (path / "notes.txt").write_text("precious")
        self.assertNotIn(str(path), self.listed(self.run_hook(self.stop())))

    def test_skips_a_review_checkout_updated_by_cherry_pick_ff(self):
        self.git(self.repo, "push", "-q", "origin", "HEAD:pr")
        self.git(self.repo, "fetch", "-q", "origin")
        review = self.worktree("pr", "origin/pr")
        author = self.tmp / "author"
        self.git(self.tmp, "clone", "-q", "-b", "pr", str(self.origin), str(author))
        self.commit(author, "more")
        self.git(author, "push", "-q", "origin", "pr")
        self.git(review, "fetch", "-q", "origin")
        self.git(review, "cherry-pick", "--ff", "origin/pr")
        self.assertNotIn(str(review), self.listed(self.run_hook(self.stop())))

    def test_skips_a_detached_head(self):
        path = self.landed()
        self.git(path, "checkout", "-q", "--detach")
        self.assertNotIn(str(path), self.listed(self.run_hook(self.stop())))

    def test_skips_a_worktree_a_process_is_running_in(self):
        path = self.landed()
        proc = subprocess.Popen(["sleep", "30"], cwd=path)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        time.sleep(0.2)
        self.assertNotIn(str(path), self.listed(self.run_hook(self.stop())))

    def test_never_lists_the_main_checkout(self):
        self.commit(self.repo, "main-work")
        self.git(self.repo, "push", "-q", "origin", "HEAD:main")
        r = self.run_hook(self.stop())
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_names_the_command_that_removes_it(self):
        path = self.landed()
        r = self.run_hook(self.stop())
        self.assertIn(f"git -C {self.repo} worktree remove {path}", self.listed(r))

    def test_skips_a_worktree_a_process_shares_with_the_session(self):
        path = self.landed()
        proc = subprocess.Popen(["sleep", "30"], cwd=path)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        time.sleep(0.2)
        r = self.run_hook({"hook_event_name": "Stop", "cwd": str(path)})
        self.assertNotIn(str(path), self.listed(r))

    def test_does_not_count_its_own_process_as_busy(self):
        path = self.landed()
        r = self.run_hook({"hook_event_name": "stop", "status": "completed", "loop_count": 0,
                           "workspace_roots": [str(path)]}, host="cursor", mode="block",
                          cwd=path)
        self.assertIn(str(path), json.loads(r.stdout)["followup_message"])

    @unittest.skipUnless(sys.platform == "darwin", "needs a case-insensitive file system")
    def test_skips_a_busy_worktree_registered_under_other_letter_case(self):
        upper = self.tmp / "Upper"
        self.git(self.tmp, "clone", "-q", str(self.origin), str(upper))
        typed = str(self.tmp / "upper" / ".claude" / "worktrees" / "cased")
        self.git(upper, "worktree", "add", "-q", "-b", "cased", typed, "origin/main")
        real = upper / ".claude" / "worktrees" / "cased"
        self.commit(real, "cased")
        self.git(real, "push", "-q", "origin", "HEAD:cased")
        proc = subprocess.Popen(["sleep", "30"], cwd=real)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        time.sleep(0.2)
        r = self.run_hook({"hook_event_name": "Stop", "cwd": str(upper)})
        self.assertNotIn("cased", self.listed(r))

    def test_skips_a_worktree_that_holds_another_worktree(self):
        outer = self.landed("outer")
        (outer / ".gitignore").write_text(".claude/worktrees/\n")
        self.git(outer, "add", ".gitignore")
        self.git(outer, "commit", "-q", "-m", "ignore")
        self.git(outer, "push", "-q", "origin", "HEAD:outer")
        self.git(outer, "worktree", "add", "-q", "-b", "inner",
                 str(outer / ".claude" / "worktrees" / "inner"), "origin/main")
        r = self.run_hook(self.stop())
        self.assertNotIn(f"{outer}  (", self.listed(r))

    def test_skips_a_review_checkout_of_a_branch_committed_in_an_earlier_worktree(self):
        path = self.landed()
        self.git(self.repo, "worktree", "remove", str(path))
        review = self.repo / ".claude" / "worktrees" / "review"
        self.git(self.repo, "worktree", "add", "-q", str(review), "feature")
        self.assertNotIn(str(review), self.listed(self.run_hook(self.stop())))

    def test_skips_a_worktree_switched_to_another_branch_after_its_work_landed(self):
        path = self.landed()
        self.git(self.repo, "push", "-q", "origin", "HEAD:other")
        self.git(path, "fetch", "-q", "origin")
        self.git(path, "switch", "-q", "-c", "other", "origin/other")
        self.assertNotIn(str(path), self.listed(self.run_hook(self.stop())))

    def test_skips_a_worktree_a_rebase_switched_to_another_branch(self):
        path = self.landed()
        self.git(self.repo, "push", "-q", "origin", "HEAD:other")
        self.git(path, "fetch", "-q", "origin")
        self.git(path, "branch", "-q", "other", "origin/other")
        self.git(path, "rebase", "-q", "origin/main", "other")
        self.assertNotIn(str(path), self.listed(self.run_hook(self.stop())))

    def test_lists_a_landed_worktree_after_checking_out_its_own_branch_again(self):
        path = self.landed()
        self.git(path, "checkout", "-q", "feature")
        self.assertIn(str(path), self.listed(self.run_hook(self.stop())))

    def test_skips_a_review_checkout_fast_forwarded_to_a_new_push(self):
        self.git(self.repo, "push", "-q", "origin", "HEAD:pr")
        self.git(self.repo, "fetch", "-q", "origin")
        review = self.worktree("pr", "origin/pr")
        author = self.tmp / "author"
        self.git(self.tmp, "clone", "-q", "-b", "pr", str(self.origin), str(author))
        self.commit(author, "more")
        self.git(author, "push", "-q", "origin", "pr")
        self.git(review, "fetch", "-q", "origin")
        self.git(review, "merge", "-q", "--ff-only", "origin/pr")
        self.assertNotIn(str(review), self.listed(self.run_hook(self.stop())))

    # -- locks, recency and whose worktree it is --------------------------

    def lock(self, path, reason="agent A working: task"):
        self.git(self.repo, "worktree", "lock", "--reason", reason, str(path))

    def test_skips_a_locked_worktree_whose_work_has_landed(self):
        path = self.landed()
        self.lock(path)
        for mode in ("remind", "block"):
            r = self.run_hook(self.stop(), mode=mode)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""), mode)

    # -- idle worktrees, shown to the user --------------------------------

    def idle(self, name="idle", hours=25, lock=None, start="origin/main"):
        """A worktree last used `hours` ago, locked with `lock` if given."""
        path = self.worktree(name, start)
        if lock:
            self.lock(path, lock)
        self.age(self.git_dir(name), hours)
        return path

    def git_dir(self, name):
        return next(d for d in self.git_dirs() if d.name == name)

    def settle(self, tree, hours=30):
        """Makes every directory in a worktree look last changed `hours` ago,
        as in a tree no one has touched."""
        for d in (tree, *(p for p in tree.rglob("*") if p.is_dir())):
            self.touch(d, hours)

    def touch(self, path, hours):
        then = time.time() - hours * 3600
        os.utime(path, (then, then))

    def message(self, r):
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        return json.loads(r.stdout)["systemMessage"]

    def test_shows_an_idle_worktree_to_the_user_and_tells_the_agent_nothing(self):
        path = self.idle()
        for mode in ("remind", "block"):
            for extra in ({}, {"stop_hook_active": True}):
                message = self.message(self.run_hook(self.stop(**extra), mode=mode, aged=False))
                self.assertIn(f"  {path}  (branch idle)\n"
                              f"    clean; no commit removal would lose\n"
                              f"    git -C {self.repo} worktree remove {path}", message)
                self.assertNotIn("unlock", message)

    def test_shows_an_idle_locked_worktree_with_its_reason_and_unlock_command(self):
        path = self.landed()
        self.lock(path, "agent B working: the parser")
        self.age(self.git_dir("feature"), 25)
        message = self.message(self.run_hook(self.stop(), mode="block", aged=False))
        self.assertIn(f"  {path}  (branch feature)\n"
                      f"    locked: agent B working: the parser\n"
                      f"    clean; no commit removal would lose\n"
                      f"    git -C {self.repo} worktree unlock {path} && "
                      f"git -C {self.repo} worktree remove {path}", message)

    def test_shows_an_idle_detached_worktree(self):
        path = self.repo / ".claude" / "worktrees" / "det"
        self.git(self.repo, "worktree", "add", "-q", "--detach", str(path), "origin/main")
        self.age(self.git_dir("det"), 25)
        message = self.message(self.run_hook(self.stop(), aged=False))
        self.assertIn(f"  {path}  (detached HEAD)\n    clean; no commit removal would lose\n"
                      f"    git -C {self.repo} worktree remove {path}", message)

    def test_skips_a_worktree_with_git_activity_in_the_last_day(self):
        self.idle(hours=23)
        self.idle("held", hours=23, lock="agent C working")
        r = self.run_hook(self.stop(), aged=False)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_skips_a_worktree_whose_changed_file_was_edited_in_the_last_day(self):
        path = self.idle()
        (path / "first.txt").write_text("edited by a tool, with no git command")
        (path / "new" / "deep").mkdir(parents=True)
        (path / "new" / "deep" / "draft.txt").write_text("draft")
        self.settle(path)
        self.touch(path / "first.txt", 30)
        r = self.run_hook(self.stop(), aged=False)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.touch(path / "new" / "deep" / "draft.txt", 30)
        message = self.message(self.run_hook(self.stop(), aged=False))
        self.assertIn(f"  {path}  (branch idle)\n"
                      "    uncommitted changes; no commit removal would lose", message)
        self.assertNotIn(f"remove {path}", message)

    def test_reads_the_first_changed_file_of_an_unstaged_edit(self):
        path = self.idle()
        (path / "a").write_text("a")
        self.git(path, "add", "a")
        self.git(path, "commit", "-q", "-m", "a")
        self.git(path, "push", "-q", "origin", "HEAD:idle")
        (path / "a").write_text("edited, with no git command")
        self.settle(path)
        self.age(self.git_dir("idle"), 25)
        r = self.run_hook(self.stop(), aged=False)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.touch(path / "a", 30)
        message = self.message(self.run_hook(self.stop(), aged=False))
        self.assertIn(f"  {path}  (branch idle)\n"
                      "    uncommitted changes; no commit removal would lose", message)
        self.assertNotIn(f"remove {path}", message)

    def test_offers_no_command_for_edits_status_hides(self):
        path = self.idle()
        self.git(path, "update-index", "--skip-worktree", "first.txt")
        (path / "first.txt").write_text("local only")
        self.settle(path)
        self.touch(path / "first.txt", 30)
        self.age(self.git_dir("idle"), 25)
        message = self.message(self.run_hook(self.stop(), aged=False))
        self.assertIn(f"  {path}  (branch idle)", message)
        self.assertNotIn(f"remove {path}", message)

    def test_reads_the_files_inside_an_untracked_repository(self):
        path = self.idle()
        nested = path / "sub"
        self.git(self.tmp, "init", "-q", str(nested))
        (nested / "f").write_text("edited just now")
        self.touch(nested, 30)
        r = self.run_hook(self.stop(), aged=False)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_offers_a_command_when_a_skip_worktree_file_is_unchanged(self):
        path = self.idle()
        self.git(path, "update-index", "--skip-worktree", "first.txt")
        self.age(self.git_dir("idle"), 25)
        message = self.message(self.run_hook(self.stop(), aged=False))
        self.assertIn(f"git -C {self.repo} worktree remove {path}", message)

    def test_reads_a_hidden_edit_in_a_file_whose_name_starts_with_a_quote(self):
        path = self.landed()
        (path / '"a"').write_text("original")
        (path / "a").write_text("original")
        self.git(path, "add", ".")
        self.git(path, "commit", "-q", "-m", "quoted")
        self.git(path, "push", "-q", "origin", "HEAD:feature")
        self.git(path, "update-index", "--skip-worktree", '"a"')
        (path / '"a"').write_text("edited, the only copy")
        r = self.run_hook(self.stop(), mode="block")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_judges_a_flagged_symlink_by_its_link_text(self):
        path = self.landed()
        (path / "link").symlink_to("feature.txt")
        (path / "gone").symlink_to("nowhere")
        self.git(path, "add", ".")
        self.git(path, "commit", "-q", "-m", "links")
        self.git(path, "push", "-q", "origin", "HEAD:feature")
        self.git(path, "update-index", "--skip-worktree", "link")
        self.git(path, "update-index", "--assume-unchanged", "gone")
        r = self.run_hook(self.stop(), mode="block")
        self.assertEqual(r.returncode, 2)
        self.assertIn(f"git -C {self.repo} worktree remove {path}", r.stderr)

    def test_shows_an_idle_tree_with_work_beside_a_dangling_flagged_symlink(self):
        path = self.idle()
        (path / "gone").symlink_to("nowhere")
        self.git(path, "add", "gone")
        self.git(path, "commit", "-q", "-m", "gone")
        self.git(path, "update-index", "--assume-unchanged", "gone")
        (path / "precious.txt").write_text("only copy")
        self.settle(path)
        self.touch(path / "precious.txt", 30)
        self.age(self.git_dir("idle"), 25)
        message = self.message(self.run_hook(self.stop(), aged=False))
        self.assertIn(f"  {path}  (branch idle)\n    uncommitted changes; no commit removal would lose",
                      message)

    @unittest.skipUnless(sys.platform.startswith("linux"), "needs a file system that allows non-UTF-8 names")
    def test_reads_a_hidden_edit_in_a_file_whose_name_is_not_utf8(self):
        path = self.landed()
        name = os.fsencode(path) + b"/n\xff.txt"
        with open(name, "wb") as f:
            f.write(b"original")
        self.git(path, "add", ".")
        self.git(path, "commit", "-q", "-m", "odd name")
        self.git(path, "push", "-q", "origin", "HEAD:feature")
        subprocess.run([b"git", b"update-index", b"--skip-worktree", b"n\xff.txt"], cwd=path,
                       env=self.env, check=True)
        with open(name, "wb") as f:
            f.write(b"edited, the only copy")
        r = self.run_hook(self.stop(), mode="block")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_offers_a_command_for_an_idle_worktree_on_an_unborn_branch(self):
        path = self.repo / ".claude" / "worktrees" / "o"
        self.git(self.repo, "worktree", "add", "-q", "--orphan", "-b", "o", str(path))
        self.age(self.git_dir("o"), 25)
        self.settle(path)
        message = self.message(self.run_hook(self.stop(), aged=False))
        self.assertIn(f"  {path}  (branch o)\n    clean; no commit removal would lose\n"
                      f"    git -C {self.repo} worktree remove {path}", message)

    def test_offers_no_command_for_an_unborn_branch_whose_reflog_holds_a_commit(self):
        path = self.repo / ".claude" / "worktrees" / "o3"
        self.git(self.repo, "worktree", "add", "-q", "--detach", str(path), "origin/main")
        self.commit(path, "only in the reflog")
        self.git(path, "checkout", "-q", "--orphan", "o3")
        self.git(path, "rm", "-q", "-r", "-f", ".")
        self.age(self.git_dir("o3"), 25)
        self.settle(path)
        message = self.message(self.run_hook(self.stop(), aged=False))
        self.assertIn(f"  {path}  (branch o3)\n    clean; commits removal would lose: unknown",
                      message)
        self.assertNotIn(f"remove {path}", message)

    @unittest.skipUnless(sys.platform.startswith("linux"), "needs a file system that allows non-UTF-8 names")
    def test_reads_the_time_of_a_changed_file_whose_name_is_not_utf8(self):
        path = self.idle()
        self.settle(path)
        with open(os.fsencode(path) + b"/caf\xe9.txt", "wb") as f:
            f.write(b"written just now")
        self.touch(path, 30)
        self.age(self.git_dir("idle"), 25)
        r = self.run_hook(self.stop(), aged=False)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_never_shows_a_worktree_that_holds_another_as_idle(self):
        (self.repo / ".gitignore").write_text(".claude/\n")
        self.git(self.repo, "add", ".gitignore")
        self.git(self.repo, "commit", "-q", "-m", "ignore")
        self.git(self.repo, "push", "-q", "origin", "HEAD:main")
        self.git(self.repo, "fetch", "-q", "origin")
        outer = self.worktree("outer")
        inner = outer / ".claude" / "worktrees" / "inner"
        self.git(outer, "worktree", "add", "-q", "-b", "inner", str(inner), "origin/main")
        self.commit(inner, "just now")
        self.age(self.git_dir("outer"), 25)
        self.settle(outer)
        r = self.run_hook(self.stop(), aged=False)
        self.assertNotIn(f"{outer}  (", self.listed(r))

    # -- the check command ---------------------------------------------------

    def check(self, path):
        return subprocess.run([sys.executable, str(HOOK), "check", str(path)], env=self.env,
                              cwd=self.elsewhere, capture_output=True, text=True, timeout=60)

    def test_check_says_safe_or_names_the_commit_removal_would_lose(self):
        safe = self.landed()
        r = self.check(safe)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertIn("Safe to remove", r.stdout)
        risky = self.worktree("feat")
        self.git(risky, "checkout", "-q", "--detach")
        self.commit(risky, "left behind")
        self.git(risky, "checkout", "-q", "feat")
        r = self.check(risky)
        self.assertEqual(r.returncode, 1)
        self.assertIn("1 commit(s) removal would lose", r.stdout)

    def test_check_refuses_a_worktree_that_holds_another(self):
        outer = self.worktree("outer")
        self.git(outer, "worktree", "add", "-q", "-b", "inner",
                 str(outer / ".claude" / "worktrees" / "inner"), "origin/main")
        (outer / ".gitignore").write_text(".claude/\n")
        self.git(outer, "add", ".gitignore")
        self.git(outer, "commit", "-q", "-m", "ignore")
        self.git(outer, "push", "-q", "origin", "HEAD:outer")
        r = self.check(outer)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("worktree inside it", r.stdout)

    def test_check_cannot_tell_for_a_worktree_without_its_git_file(self):
        (self.repo / ".gitignore").write_text(".claude/\n")
        self.git(self.repo, "add", ".gitignore")
        self.git(self.repo, "commit", "-q", "-m", "ignore")
        path = self.worktree("x")
        (path / ".git").unlink()
        r = self.check(path)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    # -- the landed listing uses the same judgement as the idle list and check

    def test_does_not_list_a_landed_worktree_whose_reflog_alone_holds_a_commit(self):
        path = self.landed()
        self.git(path, "checkout", "-q", "--detach")
        self.commit(path, "left behind")
        self.git(path, "checkout", "-q", "feature")
        for mode in ("remind", "block"):
            r = self.run_hook(self.stop(), mode=mode)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""), mode)

    def test_lists_a_landed_worktree_whose_commit_was_amended_before_the_push(self):
        path = self.worktree("feature")
        self.commit(path, "first try")
        self.git(path, "commit", "-q", "--amend", "-m", "amended")
        self.git(path, "push", "-q", "origin", "HEAD:feature")
        r = self.run_hook(self.stop(), mode="block")
        self.assertEqual(r.returncode, 2)
        self.assertIn(f"git -C {self.repo} worktree remove {path}", r.stderr)

    def test_lists_a_landed_worktree_rebased_and_force_pushed(self):
        path = self.landed()
        self.commit(self.repo, "main moves")
        self.git(self.repo, "push", "-q", "origin", "HEAD:main")
        self.git(path, "fetch", "-q", "origin")
        self.git(path, "rebase", "-q", "origin/main")
        self.git(path, "push", "-q", "-f", "origin", "HEAD:feature")
        r = self.run_hook(self.stop(), mode="block")
        self.assertEqual(r.returncode, 2)
        self.assertIn(f"git -C {self.repo} worktree remove {path}", r.stderr)

    def test_lists_a_landed_worktree_whose_reset_away_commit_its_branch_log_keeps(self):
        path = self.landed()
        self.commit(path, "abandoned")
        self.git(path, "reset", "-q", "--hard", "origin/feature")
        r = self.run_hook(self.stop(), mode="block")
        self.assertEqual(r.returncode, 2)
        self.assertIn(str(path), r.stderr)

    def test_does_not_list_a_landed_worktree_with_a_hidden_edit(self):
        path = self.landed()
        self.git(path, "update-index", "--skip-worktree", "feature.txt")
        (path / "feature.txt").write_text("local only")
        r = self.run_hook(self.stop(), mode="block")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_does_not_list_a_landed_worktree_with_a_submodule(self):
        self.submodule_in_main()
        path = self.worktree("feature")
        self.git(path, "-c", "protocol.file.allow=always", "submodule", "update", "-q", "--init")
        self.commit(path, "feature")
        self.git(path, "push", "-q", "origin", "HEAD:feature")
        r = self.run_hook(self.stop(), mode="block")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_does_not_list_a_landed_worktree_with_files_in_an_uninitialised_submodule(self):
        self.submodule_in_main()
        path = self.worktree("feature")
        (path / "sub" / "notes.txt").write_text("only copy")
        self.commit(path, "feature")
        self.git(path, "push", "-q", "origin", "HEAD:feature")
        r = self.run_hook(self.stop(), mode="block")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        r = self.check(path)
        self.assertEqual(r.returncode, 1, r.stdout)

    @unittest.skipIf(os.geteuid() == 0, "root reads any directory")
    def test_an_unreadable_submodule_directory_does_not_hide_the_others(self):
        self.submodule_in_main()
        odd = self.worktree("odd")
        (odd / "sub" / "notes.txt").write_text("only copy")
        done = self.landed("done")
        self.age(self.git_dir("odd"), 25)
        self.age(self.git_dir("done"), 2)
        self.settle(odd)
        (odd / "sub").chmod(0)
        self.addCleanup((odd / "sub").chmod, 0o755)
        r = self.run_hook(self.stop(stop_hook_active=True), mode="block", aged=False)
        self.assertEqual(r.returncode, 0)
        message = json.loads(r.stdout)["systemMessage"]
        self.assertIn(str(done), message)
        self.assertIn(f"  {odd}  (branch odd)\n    uncommitted changes", message)
        r = self.check(odd)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def submodule_in_main(self):
        """Adds a submodule `sub` to main and pushes it."""
        lib = self.tmp / "lib.git"
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", str(lib))
        seed = self.tmp / "seed"
        self.git(self.tmp, "clone", "-q", str(lib), str(seed))
        self.commit(seed, "lib")
        self.git(seed, "push", "-q", "origin", "HEAD:main")
        self.git(self.repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q",
                 str(lib), "sub")
        self.git(self.repo, "commit", "-q", "-m", "sub")
        self.git(self.repo, "push", "-q", "origin", "HEAD:main")
        self.git(self.repo, "fetch", "-q", "origin")

    def test_reads_a_submodule_and_offers_no_command_for_it(self):
        self.submodule_in_main()
        path = self.worktree("withsub")
        self.git(path, "-c", "protocol.file.allow=always", "submodule", "update", "-q", "--init")
        self.age(self.git_dir("withsub"), 25)
        message = self.message(self.run_hook(self.stop(), aged=False))
        self.assertIn(f"  {path}  (branch withsub)\n    clean; no commit removal would lose\n"
                      "    has submodules, which git worktree remove refuses", message)
        self.assertNotIn(f"remove {path}", message)
        (path / "sub" / "lib.txt").write_text("edited just now")
        self.git(path / "sub", "commit", "-q", "-am", "wip")
        self.age(self.git_dir("withsub"), 25)
        r = self.run_hook(self.stop(), aged=False)
        self.assertNotIn(str(path), self.listed(r))

    def test_skips_a_worktree_whose_files_were_just_moved_or_deleted(self):
        path = self.idle()
        self.touch(path / "first.txt", 30)
        (path / "lib").mkdir()
        (path / "first.txt").rename(path / "lib" / "moved.txt")
        r = self.run_hook(self.stop(), aged=False)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_shows_a_worktree_with_a_deleted_file(self):
        path = self.idle()
        (path / "first.txt").unlink()
        self.touch(path, 30)
        message = self.message(self.run_hook(self.stop(), aged=False))
        self.assertIn("    uncommitted changes; no commit removal would lose", message)
        self.assertNotIn(f"remove {path}", message)

    def test_skips_the_sessions_own_worktree_and_a_busy_one(self):
        own = self.idle("own")
        busy = self.idle("busy")
        proc = subprocess.Popen(["sleep", "30"], cwd=busy)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        time.sleep(0.2)
        r = self.run_hook({"hook_event_name": "Stop", "cwd": str(own)}, aged=False, cwd=own)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_offers_a_command_when_its_branch_keeps_an_unpushed_commit(self):
        path = self.worktree("ahead")
        self.commit(path, "ahead")
        self.age(self.git_dir("ahead"), 25)
        self.settle(path)
        message = self.message(self.run_hook(self.stop(), aged=False))
        self.assertIn(f"  {path}  (branch ahead)\n    clean; no commit removal would lose\n"
                      f"    git -C {self.repo} worktree remove {path}", message)

    def test_idle_activity_survives_git_gc(self):
        path = self.idle()
        self.settle(path)
        self.git(self.repo, "gc", "-q")
        self.git(self.repo, "reflog", "expire", "--all")
        message = self.message(self.run_hook(self.stop(), aged=False))
        self.assertIn(f"  {path}  (branch idle)", message)

    def test_reads_activity_in_a_submodule(self):
        self.submodule_in_main()
        path = self.worktree("withsub2")
        self.git(path, "-c", "protocol.file.allow=always", "submodule", "update", "-q", "--init")
        self.age(self.git_dir("withsub2"), 25)
        self.settle(path)
        self.assertIn(str(path), self.listed(self.run_hook(self.stop(), aged=False)))
        self.git(path / "sub", "commit", "-q", "--allow-empty", "-m", "now")
        self.touch(path / "sub", 30)
        r = self.run_hook(self.stop(), aged=False)
        self.assertNotIn(str(path), self.listed(r))

    def test_counts_a_commit_only_the_reflog_holds(self):
        path = self.worktree("feat")
        self.git(path, "checkout", "-q", "--detach")
        self.commit(path, "left behind")
        self.git(path, "checkout", "-q", "feat")
        self.age(self.git_dir("feat"), 25)
        message = self.message(self.run_hook(self.stop(), aged=False))
        self.assertIn(f"  {path}  (branch feat)\n    clean; 1 commit removal would lose", message)
        self.assertNotIn(f"remove {path}", message)

    def test_offers_a_command_for_an_empty_reflog_with_head_on_a_remote(self):
        path = self.idle("bare")
        (self.git_dir("bare") / "logs" / "HEAD").unlink()
        self.age(self.git_dir("bare"), 25)
        message = self.message(self.run_hook(self.stop(), aged=False))
        self.assertIn(f"  {path}  (branch bare)\n    clean; no commit removal would lose\n"
                      f"    git -C {self.repo} worktree remove {path}", message)

    def test_idle_worktrees_never_block_beside_landed_ones(self):
        idle = self.idle()
        landed = self.landed()
        self.age(self.git_dir("feature"), 25)
        r = self.run_hook(self.stop(), mode="block", aged=False)
        self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertIn(str(landed), r.stderr)
        self.assertNotIn(str(idle), r.stderr)
        message = self.message(self.run_hook(self.stop(stop_hook_active=True), mode="block",
                                             aged=False))
        self.assertIn(f"  {idle}  (branch idle)", message)
        self.assertEqual(message.count(str(landed) + "  "), 1)

    def test_a_worktree_with_a_huge_reflog_does_not_hide_the_others(self):
        done = self.landed("done")
        big = self.worktree("big")
        # 30000 distinct commits in big's HEAD reflog: more than fit in one
        # command line.
        n = 30000
        stream = "".join(f"commit refs/heads/scratch\nmark :{i}\n"
                         f"committer T <t@e> {1700000000 + i} +0000\ndata 1\n{i % 10}\n\n"
                         for i in range(1, n + 1))
        marks = self.tmp / "marks"
        subprocess.run(["git", "fast-import", "--quiet", f"--export-marks={marks}"],
                       cwd=self.repo, env=self.env, input=stream, text=True, check=True)
        shas = [line.split()[1] for line in marks.read_text().splitlines()]
        log = self.git_dir("big") / "logs" / "HEAD"
        with open(log, "a") as f:
            for old, new in zip(shas, shas[1:]):
                f.write(f"{old} {new} T <t@e> 1700000000 +0000\treset: moving to {new}\n")
        for d in self.git_dirs():
            self.age(d, 25)
        r = self.run_hook(self.stop(), mode="block", aged=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn(str(done), r.stderr)
        message = self.message(self.run_hook(self.stop(stop_hook_active=True), mode="block",
                                             aged=False))
        self.assertIn(f"  {big}  (branch big)\n    clean; no commit removal would lose\n"
                      f"    git -C {self.repo} worktree remove {big}", message)

    def test_never_shows_the_main_checkout_as_idle(self):
        clone = self.tmp / "clone"
        self.git(self.tmp, "clone", "-q", str(self.origin), str(clone))
        self.age(clone / ".git", 25)
        r = self.run_hook({"hook_event_name": "Stop", "cwd": str(clone)}, aged=False)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_cursor_shows_nothing_for_an_idle_worktree(self):
        self.idle()
        for mode in ("remind", "block"):
            r = self.run_hook({"hook_event_name": "stop", "status": "completed", "loop_count": 0,
                               "workspace_roots": [str(self.repo)]}, host="cursor", mode=mode,
                              aged=False)
            self.assertEqual((r.returncode, json.loads(r.stdout), r.stderr), (0, {}, ""), mode)

    def test_push_never_mentions_an_idle_worktree(self):
        idle = self.idle()
        own = self.landed()
        self.age(self.git_dir("idle"), 25)
        r = self.run_hook(self.push("git push", cwd=own), mode="block", aged=False)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn(str(idle), self.listed(r))

    def test_skips_a_sibling_used_in_the_last_hour(self):
        path = self.landed()
        r = self.run_hook(self.stop(), aged=False)
        self.assertNotIn(str(path), self.listed(r))

    def test_lists_a_sibling_unused_for_over_an_hour(self):
        path = self.landed()
        self.assertIn(str(path), self.listed(self.run_hook(self.stop())))

    def test_lists_the_sessions_own_worktree_however_recently_used(self):
        path = self.landed()
        r = self.run_hook({"hook_event_name": "Stop", "cwd": str(path)}, aged=False)
        self.assertIn(str(path), self.listed(r))
        r = self.run_hook(self.push("git push", cwd=path), aged=False)
        self.assertIn(str(path), self.listed(r))

    def test_its_own_git_status_leaves_the_index_untouched(self):
        path = self.landed()
        # A newer mtime than the index records: a plain `git status` would
        # refresh the index and write it.
        (path / "feature.txt").touch()
        git_dir = next(d for d in self.git_dirs() if d.name == "feature")
        self.age(git_dir, 2)
        before = (git_dir / "index").stat().st_mtime
        self.run_hook(self.stop(), aged=False)
        self.assertEqual((git_dir / "index").stat().st_mtime, before)

    # -- the push check -----------------------------------------------------

    def test_push_is_read_from_git_whatever_the_command_text(self):
        path = self.landed()
        for cmd in ("bash -c 'git push'", 'out=$(git push 2>&1); echo "$out"',
                    "make release"):
            payload = {**self.push(cmd, cwd=path), "duration_ms": 30000}
            r = self.run_hook(payload, mode="block")
            self.assertEqual(r.returncode, 2, cmd)
            self.assertIn(str(path), r.stderr, cmd)

    def test_push_check_is_silent_without_a_recent_push(self):
        self.landed()
        self.age_pushes()
        for cmd in ("git push", "git stash push -m wip"):
            r = self.run_hook(self.push(cmd), mode="block")
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""), cmd)

    def test_push_check_ignores_a_push_made_before_the_command_started(self):
        sibling = self.landed("sibling")
        self.lock(sibling, "agent B working")
        own = self.landed("feature")
        self.age_pushes(seconds=20)
        for cwd in (sibling, own):
            payload = {**self.push("git log -1", cwd=cwd), "duration_ms": 30}
            r = self.run_hook(payload, mode="block")
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""), cwd)

    def test_push_check_without_a_duration_needs_push_in_the_command(self):
        self.landed()
        r = self.run_hook(self.push("ls"), mode="block")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertEqual(self.run_hook(self.push("git push"), mode="block").returncode, 2)

    def test_push_lists_only_the_worktree_it_came_from(self):
        sibling = self.landed("sibling")
        own = self.landed("feature")
        self.age_pushes()
        self.commit(own, "more")
        self.git(own, "push", "-q", "origin", "HEAD:feature")
        r = self.run_hook(self.push("git push", cwd=own))
        self.assertIn(str(own), self.listed(r))
        self.assertNotIn(str(sibling), self.listed(r))

    def test_push_from_the_main_checkout_lists_nothing(self):
        self.landed()
        self.age_pushes()
        self.commit(self.repo, "on-main")
        self.git(self.repo, "push", "-q", "origin", "HEAD:main")
        r = self.run_hook(self.push("git push", cwd=self.repo), mode="block")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_push_never_lists_a_worktree_the_session_is_not_in(self):
        path = self.landed()
        for cwd in (self.repo, self.elsewhere):
            r = self.run_hook(self.push(f"git -C {path} log -1", cwd=cwd), mode="block")
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""), cwd)

    def test_push_lists_its_own_locked_worktree_with_the_unlock_command(self):
        path = self.landed()
        self.lock(path)
        r = self.run_hook(self.push("git push", cwd=path), mode="block")
        self.assertEqual(r.returncode, 2)
        self.assertIn(f"git -C {self.repo} worktree unlock {path} && "
                      f"git -C {self.repo} worktree remove {path}", r.stderr)

    def test_push_check_survives_a_worktree_whose_directory_was_deleted(self):
        gone = self.worktree("gone")
        shutil.rmtree(gone)
        path = self.landed()
        r = self.run_hook({**self.push("git push", cwd=path), "duration_ms": 800}, mode="block")
        self.assertEqual(r.returncode, 2)
        self.assertIn(str(path), r.stderr)

    def test_push_shows_the_lock_reason_and_says_to_unlock_only_its_own_lock(self):
        path = self.landed()
        self.lock(path, "agent B working: build feature X")
        r = self.run_hook(self.push("git push", cwd=path), mode="block")
        self.assertIn("locked: agent B working: build feature X", r.stderr)
        self.assertIn("only if you locked it", r.stderr)

    def test_push_shows_a_lock_reason_as_it_was_written(self):
        path = self.landed()
        self.lock(path, "Zoë's agent:\tbuild")
        r = self.run_hook(self.push("git push", cwd=path), mode="block")
        self.assertIn("locked: Zoë's agent: build\n", r.stderr)

    def test_push_keeps_a_lock_reason_on_one_line(self):
        path = self.landed()
        fake = f"\n  {self.repo}  (branch main, on origin/main)\n    git -C {self.repo} worktree remove {self.repo}"
        self.lock(path, "agent 7 reviewing" + fake + "\x1b[31m")
        r = self.run_hook(self.push("git push", cwd=path), mode="block")
        self.assertNotIn(f"\n  {self.repo}  (branch main", r.stderr)
        self.assertNotIn("\x1b", r.stderr)
        self.assertIn("locked: agent 7 reviewing ", r.stderr)

    def test_lists_worktrees_when_git_prints_bytes_that_are_not_utf8(self):
        path = self.landed()
        other = self.landed("other")
        self.git(self.repo, "config", "core.quotePath", "false")
        self.lock(other, "bad")
        locked = next(d for d in self.git_dirs() if d.name == "other") / "locked"
        locked.write_bytes(b"bad\xff\xfe reason")
        r = self.run_hook(self.push("git push", cwd=path), mode="block")
        self.assertEqual(r.returncode, 2)
        self.assertIn(str(path), r.stderr)

    def test_never_lists_a_locked_worktree_whose_branch_holds_a_line_separator(self):
        name = "L\u2028\u2028z"
        path = self.repo / ".claude" / "worktrees" / "wa"
        self.git(self.repo, "worktree", "add", "-q", "-b", name, str(path), "origin/main")
        self.commit(path, "wa")
        self.git(path, "push", "-q", "origin", f"HEAD:{name}")
        self.lock(path, "do not touch")
        r = self.run_hook({"hook_event_name": "Stop", "cwd": str(path)})
        self.assertNotIn(str(path), self.listed(r))

    def test_a_lock_reason_cannot_forge_an_unlocked_entry(self):
        path = self.landed("wb")
        self.git(self.repo, "config", "core.quotePath", "false")
        forged = f"keep\u2028\u2028worktree {os.path.realpath(path)}\u2028branch refs/heads/wb"
        self.lock(path, forged)
        r = self.run_hook(self.stop())
        self.assertNotIn(str(path), self.listed(r))

    def test_a_lock_reason_shown_to_the_user_holds_no_line_separator(self):
        path = self.landed()
        self.lock(path, "x\u2028  /fake  (branch f, on origin/f)\u2029end")
        self.age(next(d for d in self.git_dirs() if d.name == "feature"), 25)
        r = self.run_hook(self.stop(), aged=False)
        message = json.loads(r.stdout)["systemMessage"]
        self.assertIn(str(path), message)
        self.assertNotIn("\u2028", message)
        self.assertNotIn("\u2029", message)

    def test_skips_a_busy_worktree_whose_path_holds_a_tab(self):
        path = self.repo / ".claude" / "worktrees" / "w\tt"
        self.git(self.repo, "worktree", "add", "-q", "-b", "wt", str(path), "origin/main")
        self.commit(path, "wt")
        self.git(path, "push", "-q", "origin", "HEAD:wt")
        proc = subprocess.Popen(["sleep", "30"], cwd=path)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        time.sleep(0.2)
        self.assertNotIn("(branch wt", self.listed(self.run_hook(self.stop())))

    @unittest.skipUnless(sys.platform.startswith("linux"), "needs a file system that allows non-UTF-8 names")
    def test_skips_a_worktree_holding_a_nested_worktree_with_a_non_utf8_name(self):
        outer = self.landed("outer")
        (outer / ".gitignore").write_text(".claude/worktrees/\n")
        self.git(outer, "add", ".gitignore")
        self.git(outer, "commit", "-q", "-m", "ignore")
        self.git(outer, "push", "-q", "origin", "HEAD:outer")
        inner = os.fsencode(outer / ".claude" / "worktrees") + b"/n\xff"
        subprocess.run([b"git", b"worktree", b"add", b"-q", b"-b", b"inner", inner, b"origin/main"],
                       cwd=outer, env=self.env, check=True, capture_output=True)
        r = self.run_hook(self.stop())
        self.assertNotIn(f"{outer}  (", self.listed(r))

    def test_reads_worktrees_from_a_git_without_the_z_flag(self):
        path = self.landed()
        self.lock(path, "Zoë's agent")
        self.age(next(d for d in self.git_dirs() if d.name == "feature"), 25)
        self.old_git()
        r = self.run_hook(self.stop(), aged=False)
        message = json.loads(r.stdout)["systemMessage"]
        self.assertIn(str(path), message)
        self.assertIn("locked: Zoë's agent", message)

    def old_git(self):
        """Puts a git on PATH whose `worktree list` refuses -z, as git before
        2.36 does. Other commands, such as `status -z`, take it."""
        bin_dir = self.tmp / "old-git"
        bin_dir.mkdir(exist_ok=True)
        wrapper = bin_dir / "git"
        wrapper.write_text("#!/bin/sh\n"
                           'case " $* " in *" worktree list "*) for a in "$@"; do '
                           '[ "$a" = -z ] && exit 129; done;; esac\n'
                           f'exec {shutil.which("git")} "$@"\n')
        wrapper.chmod(0o755)
        self.env["PATH"] = f"{bin_dir}:{self.env['PATH']}"

    def test_a_path_cannot_forge_an_unlocked_entry_on_a_git_without_z(self):
        locked = self.landed("b")
        self.lock(locked, "someone else's")
        evil = f"{self.repo}/.claude/worktrees/x\n\nworktree {os.path.realpath(locked)}"
        self.git(self.repo, "worktree", "add", "-q", "-b", "evil", evil, "origin/b")
        self.old_git()
        r = self.run_hook({"hook_event_name": "Stop", "cwd": str(locked)})
        self.assertNotIn(os.path.realpath(locked), self.listed(r))

    def test_a_process_in_a_non_ascii_directory_does_not_silence_the_hook(self):
        path = self.landed()
        elsewhere = self.tmp / "Développement"
        elsewhere.mkdir()
        proc = subprocess.Popen(["sleep", "30"], cwd=elsewhere)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        time.sleep(0.2)
        self.env["LC_ALL"] = "C"
        self.assertIn(str(path), self.listed(self.run_hook(self.stop())))

    def test_never_lists_a_locked_worktree_whose_git_file_is_missing(self):
        (self.repo / ".gitignore").write_text(".claude/\n")
        self.git(self.repo, "add", ".gitignore")
        self.git(self.repo, "commit", "-q", "-m", "ignore")
        self.git(self.repo, "push", "-q", "origin", "HEAD:main")
        path = self.landed()
        self.lock(path, "agent X busy")
        (path / ".git").rename(self.tmp / "moved-git-file")
        r = self.run_hook({"hook_event_name": "Stop", "cwd": str(path)})
        self.assertNotIn(str(path), self.listed(r))

    def test_a_forged_entry_for_a_subdirectory_of_a_locked_worktree_is_not_listed(self):
        locked = self.landed("b")
        (locked / "sub").mkdir()
        self.lock(locked, "someone else's")
        real = os.path.realpath(locked)
        evil = f"{self.repo}/.claude/worktrees/x\n\nworktree {real}/sub\nbranch refs/heads/b"
        self.git(self.repo, "worktree", "add", "-q", "-b", "evil", evil, "origin/b")
        self.old_git()
        r = self.run_hook({"hook_event_name": "Stop", "cwd": f"{real}/sub"})
        self.assertNotIn(f"{real}/sub", self.listed(r))

    def test_push_never_lists_a_locked_sibling(self):
        sibling = self.landed("sibling")
        self.lock(sibling)
        r = self.run_hook(self.push("git push", cwd=self.repo), mode="block")
        self.assertNotIn(str(sibling), self.listed(r))

    # -- finding the repo -------------------------------------------------

    def test_stop_finds_the_repo_through_the_transcript(self):
        path = self.landed()
        transcript = self.tmp / "transcript.jsonl"
        transcript.write_text(json.dumps({"text": f"cd {path}/src && make"}) + "\n")
        r = self.run_hook({"hook_event_name": "Stop", "cwd": str(self.elsewhere),
                           "transcript_path": str(transcript)})
        self.assertIn(str(path), self.listed(r))

    def test_stop_reads_a_path_after_an_escaped_newline_in_the_transcript(self):
        path = self.landed()
        transcript = self.tmp / "transcript.jsonl"
        transcript.write_text(json.dumps({"text": f"/tmp/foo\n{path}\n"}) + "\n")
        r = self.run_hook({"hook_event_name": "Stop", "cwd": str(self.elsewhere),
                           "transcript_path": str(transcript)})
        self.assertIn(str(path), self.listed(r))

    def test_stop_reads_a_transcript_holding_an_image_quickly(self):
        path = self.landed()
        transcript = self.tmp / "transcript.jsonl"
        image = "iVBORw0KGgo/" * 60000
        transcript.write_text(json.dumps({"image": image, "text": f"cd {path}"}) + "\n")
        started = time.monotonic()
        r = self.run_hook({"hook_event_name": "Stop", "cwd": str(self.elsewhere),
                           "transcript_path": str(transcript)})
        self.assertLess(time.monotonic() - started, 5)
        self.assertIn(str(path), self.listed(r))

    def test_stop_from_a_non_repo_cwd_with_no_transcript_is_silent(self):
        self.landed()
        r = self.run_hook({"hook_event_name": "Stop", "cwd": str(self.elsewhere)})
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_cursor_finds_the_repo_through_workspace_roots(self):
        path = self.landed()
        r = self.run_hook({"hook_event_name": "stop", "status": "completed", "loop_count": 0,
                           "workspace_roots": [str(self.repo)]}, host="cursor", mode="block")
        self.assertIn(str(path), json.loads(r.stdout)["followup_message"])

    # -- failing open -----------------------------------------------------

    def test_malformed_stdin_exits_0(self):
        for raw in ("", "not json", "[1, 2]", '{"cwd": 5, "tool_input": "x"}'):
            r = self.run_hook(None, raw=raw, mode="block")
            self.assertEqual(r.returncode, 0, raw)

    # -- what each host, event and mode reports ---------------------------

    def test_claude_push_in_remind_mode_adds_context_without_blocking(self):
        path = self.landed()
        r = self.run_hook(self.push("git push"))
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PostToolUse")
        self.assertIn(str(path), out["additionalContext"])
        self.assertIn("ask the user", out["additionalContext"])

    def test_claude_push_in_block_mode_exits_2_with_the_list(self):
        path = self.landed()
        r = self.run_hook(self.push("git push"), mode="block")
        self.assertEqual(r.returncode, 2)
        self.assertIn(str(path), r.stderr)
        self.assertIn("Remove them now", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_claude_stop_in_remind_mode_tells_the_user_without_blocking(self):
        path = self.landed()
        r = self.run_hook(self.stop())
        self.assertEqual(r.returncode, 0)
        self.assertIn(str(path), json.loads(r.stdout)["systemMessage"])

    def test_claude_stop_in_block_mode_blocks(self):
        path = self.landed()
        r = self.run_hook(self.stop(stop_hook_active=False), mode="block")
        self.assertEqual(r.returncode, 2)
        self.assertIn(str(path), r.stderr)
        self.assertIn("ask the user", r.stderr)

    def test_second_stop_in_block_mode_tells_the_user_instead_of_blocking(self):
        path = self.landed()
        r = self.run_hook(self.stop(stop_hook_active=True), mode="block")
        self.assertEqual(r.returncode, 0)
        self.assertIn(str(path), json.loads(r.stdout)["systemMessage"])

    def test_mode_is_read_from_the_config_file(self):
        self.landed()
        (self.tmp / "worktrees.json").write_text('{"mode": "block"}')
        self.assertEqual(self.run_hook(self.stop()).returncode, 2)

    def test_the_environment_overrides_the_config_file(self):
        self.landed()
        (self.tmp / "worktrees.json").write_text('{"mode": "block"}')
        self.assertEqual(self.run_hook(self.stop(), mode="remind").returncode, 0)

    def test_an_unknown_or_unreadable_mode_means_remind(self):
        self.landed()
        (self.tmp / "worktrees.json").write_text("[not json")
        self.assertEqual(self.run_hook(self.stop()).returncode, 0)
        self.assertEqual(self.run_hook(self.stop(), mode="blocking").returncode, 0)

    def test_cursor_push_adds_context_in_either_mode(self):
        path = self.landed()
        payload = {"hook_event_name": "postToolUse", "cwd": str(path),
                   "tool_name": "Shell", "tool_input": {"command": "git push"}}
        for mode in ("remind", "block"):
            r = self.run_hook(payload, host="cursor", mode=mode)
            self.assertEqual(r.returncode, 0, mode)
            self.assertIn(str(path), json.loads(r.stdout)["additional_context"], mode)

    def test_cursor_stop_in_block_mode_sends_a_follow_up_once(self):
        path = self.landed()
        payload = {"hook_event_name": "stop", "status": "completed",
                   "workspace_roots": [str(self.repo)]}
        r = self.run_hook({**payload, "loop_count": 0}, host="cursor", mode="block")
        self.assertEqual(r.returncode, 0)
        self.assertIn(str(path), json.loads(r.stdout)["followup_message"])
        r = self.run_hook({**payload, "loop_count": 1}, host="cursor", mode="block")
        self.assertEqual((r.returncode, json.loads(r.stdout)), (0, {}))

    def test_cursor_stop_sends_nothing_in_remind_mode_or_after_an_abort(self):
        self.landed()
        payload = {"hook_event_name": "stop", "status": "completed", "loop_count": 0,
                   "workspace_roots": [str(self.repo)]}
        r = self.run_hook(payload, host="cursor")
        self.assertEqual((r.returncode, json.loads(r.stdout)), (0, {}))
        r = self.run_hook({**payload, "status": "aborted"}, host="cursor", mode="block")
        self.assertEqual((r.returncode, json.loads(r.stdout)), (0, {}))

    def test_cursor_prints_empty_json_when_nothing_is_listed(self):
        r = self.run_hook({"hook_event_name": "stop", "workspace_roots": [str(self.repo)]},
                          host="cursor")
        self.assertEqual((r.returncode, json.loads(r.stdout)), (0, {}))

    def test_messages_name_no_one(self):
        self.landed()
        for mode in ("remind", "block"):
            r = self.run_hook(self.push("git push"), mode=mode)
            self.assertNotIn("Adam", self.listed(r))

    def test_the_hook_uses_the_mode_the_mode_command_wrote(self):
        self.landed()
        run_mode(self.env, "block")
        self.assertEqual(self.run_hook(self.stop()).returncode, 2)
        run_mode(self.env, "remind")
        r = self.run_hook(self.stop())
        self.assertEqual(r.returncode, 0)
        self.assertIn("systemMessage", json.loads(r.stdout))

    def test_a_hook_run_never_takes_the_mode_command(self):
        self.landed()
        for argv in (["--host", "claude"], ["--host", "claude", "mode"],
                     ["--host", "claude", "--event", "stop", "mode", "block"]):
            for d in self.git_dirs():
                self.age(d, 2)
            r = subprocess.run([sys.executable, str(HOOK), *argv], input=json.dumps(self.stop()),
                               cwd=self.elsewhere, env=self.env, capture_output=True, text=True,
                               timeout=60)
            self.assertEqual(r.returncode, 0, argv)
            self.assertIn("systemMessage", json.loads(r.stdout), argv)
            self.assertFalse((self.tmp / "worktrees.json").exists(), argv)


def run_mode(env, *args, extra=None):
    return subprocess.run([sys.executable, str(HOOK), "mode", *args],
                          env={**env, **(extra or {})}, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=30)


class ModeCommandTests(unittest.TestCase):
    """`worktree-sweep.py mode [block|remind]`, with the config file in a temp
    directory."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="worktrees-mode-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "home").mkdir()
        self.config = self.tmp / "conf" / "worktrees.json"
        self.env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "HOME": str(self.tmp / "home"), "WORKTREES_CONFIG": str(self.config)}

    def mode(self, *args, **extra):
        return run_mode(self.env, *args, extra=extra)

    def write(self, text):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(text)

    def test_reports_the_default_when_there_is_no_file(self):
        r = self.mode()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, f"Worktrees mode: remind, the default: {self.config} "
                                   "does not exist.\n")

    def test_reports_the_mode_in_the_file(self):
        self.write('{"mode": "block"}')
        self.assertEqual(self.mode().stdout, f"Worktrees mode: block, from {self.config}.\n")

    def test_reports_the_environment_over_the_file(self):
        self.write('{"mode": "block"}')
        r = self.mode(WORKTREES_MODE="remind")
        self.assertEqual(r.stdout, "Worktrees mode: remind, from the WORKTREES_MODE "
                                   "environment variable.\n")

    def test_reports_a_file_it_cannot_use_and_that_the_hook_then_reminds(self):
        for text, why in (("[not json", "is not valid JSON"),
                          ('["block"]', "holds JSON that is not an object"),
                          ('"block"', "holds JSON that is not an object")):
            self.write(text)
            r = self.mode()
            self.assertEqual(r.returncode, 0, text)
            self.assertIn(f"Worktrees mode: remind, because {self.config} {why}", r.stdout, text)
            self.assertIn("the hook uses remind", r.stdout, text)

    def test_reports_an_unknown_value_as_remind(self):
        self.write('{"mode": "blocking"}')
        self.assertIn('remind, from', self.mode().stdout)
        self.assertIn('"blocking" isn\'t block or remind', self.mode().stdout)
        self.assertIn('"Block!" isn\'t block or remind', self.mode(WORKTREES_MODE="Block!").stdout)

    def test_reports_what_the_hook_would_use(self):
        """For many file contents and WORKTREES_MODE values, the command names
        the mode the hook's own mode() returns."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("sweep", HOOK)
        sweep = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sweep)
        cases = [None, '{"mode": "block"}', '{"mode": " BLOCK "}', '{"mode": "remind"}',
                 '{"mode": null}', '{"mode": true}', "{}", "[1]", "nope", ""]
        for text in cases:
            for env_mode in (None, "block", "remind", "  ", "x"):
                if text is None:
                    self.config.unlink(missing_ok=True)
                else:
                    self.write(text)
                extra = {"WORKTREES_MODE": env_mode} if env_mode is not None else {}
                saved = dict(os.environ)
                try:
                    os.environ.clear()
                    os.environ.update({**self.env, **extra})
                    want = sweep.mode()
                finally:
                    os.environ.clear()
                    os.environ.update(saved)
                got = self.mode(**extra).stdout
                self.assertTrue(got.startswith(f"Worktrees mode: {want},"), (text, env_mode, got))

    def test_sets_block_and_remind(self):
        for want in ("block", "remind", "BLOCK"):
            r = self.mode(want)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(self.config.read_text()), {"mode": want.lower()})
            self.assertEqual(r.stdout, f"Wrote mode {want.lower()} to {self.config}.\n"
                                       f"Worktrees mode: {want.lower()}, from {self.config}.\n")

    def test_creates_the_directory(self):
        self.config = self.tmp / "a" / "b" / "worktrees.json"
        self.env["WORKTREES_CONFIG"] = str(self.config)
        self.assertEqual(self.mode("block").returncode, 0)
        self.assertEqual(json.loads(self.config.read_text()), {"mode": "block"})

    def test_keeps_other_keys(self):
        self.write('{"other": [1, {"x": "\\u00e9"}], "mode": "remind", "z": null}')
        self.assertEqual(self.mode("block").returncode, 0)
        self.assertEqual(json.loads(self.config.read_text()),
                         {"other": [1, {"x": "\u00e9"}], "mode": "block", "z": None})

    def test_refuses_another_value(self):
        self.write('{"mode": "remind"}')
        for args in (["blocking"], [""], ["block", "remind"], ["--help"]):
            r = self.mode(*args)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn("Usage: worktree-sweep.py mode [block|remind]", r.stderr, args)
            self.assertEqual(self.config.read_text(), '{"mode": "remind"}', args)

    def test_refuses_a_file_that_is_not_a_json_object_and_leaves_it(self):
        for text, why in (("[not json", "is not valid JSON"), ("", "is not valid JSON"),
                          ('["mode"]', "holds JSON that is not an object"),
                          ("42", "holds JSON that is not an object")):
            self.write(text)
            r = self.mode("block")
            self.assertEqual(r.returncode, 1, text)
            self.assertIn(f"{self.config} {why}, so it was left as it is", r.stderr, text)
            self.assertEqual(r.stdout, "", text)
            self.assertEqual(self.config.read_text(), text, text)
            self.assertEqual(os.listdir(self.config.parent), ["worktrees.json"], text)

    def test_refuses_a_file_that_is_not_utf8_and_leaves_it(self):
        self.config.parent.mkdir(parents=True)
        self.config.write_bytes(b'{"note": "caf\xe9", "mode": "block"}')
        self.assertIn("is not valid JSON", self.mode().stdout)
        r = self.mode("remind")
        self.assertEqual(r.returncode, 1)
        self.assertIn(f"{self.config} is not valid JSON, so it was left as it is", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(self.config.read_bytes(), b'{"note": "caf\xe9", "mode": "block"}')

    def test_warns_when_the_environment_overrides_the_new_value(self):
        r = self.mode("block", WORKTREES_MODE="remind")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(self.config.read_text()), {"mode": "block"})
        self.assertIn("Worktrees mode: remind, from the WORKTREES_MODE environment variable.",
                      r.stdout)
        self.assertIn('WORKTREES_MODE is set to "remind" and overrides the file', r.stdout)
        self.assertIn("unset WORKTREES_MODE in the environment the agent is started from",
                      r.stdout)
        self.assertNotIn("overrides", self.mode("block").stdout)

    def test_uses_the_default_path_without_worktrees_config(self):
        del self.env["WORKTREES_CONFIG"]
        default = self.tmp / "home" / ".config" / "shared-skills" / "worktrees.json"
        r = self.mode("block")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(default.read_text()), {"mode": "block"})
        self.assertEqual(self.mode().stdout, f"Worktrees mode: block, from {default}.\n")

    def test_writes_through_a_link_and_keeps_it(self):
        real = self.tmp / "dotfiles" / "worktrees.json"
        real.parent.mkdir()
        real.write_text('{"mode": "remind"}')
        self.config.parent.mkdir()
        self.config.symlink_to(real)
        self.assertEqual(self.mode("block").returncode, 0)
        self.assertTrue(self.config.is_symlink())
        self.assertEqual(json.loads(real.read_text()), {"mode": "block"})

    def test_keeps_the_files_permissions(self):
        self.write('{"mode": "remind"}')
        self.config.chmod(0o600)
        self.assertEqual(self.mode("block").returncode, 0)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main(verbosity=2)

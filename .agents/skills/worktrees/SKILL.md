---
name: worktrees
description: >-
  When and how an agent uses git worktrees, and when it removes them. Use
  before starting work on a branch, before working in parallel with other
  agents or a human, before checking out a branch to review it, and when
  finishing work done in a worktree: after pushing, opening a pull request or
  landing a commit on the default branch, or when stopping with nothing
  committed in it. Also use when `git worktree list`
  shows entries, when a hook lists worktrees whose work has landed, and when
  writing a brief that tells another agent to create a worktree.
---

# Worktrees

**A worktree keeps the human's checkout untouched, its detached HEAD
leaves the branch free for anyone to check out, its lock says who is working
in it, and it goes the moment its work has landed.**

## When to use one

- Any work on a branch other than the one the human's checkout is on.
- Any parallel or background agent work, even on the same branch.

The human's working copy is never switched to another branch or left dirty by
you. A read-only question needs no worktree.

## Create it locked, on the branch you will work on, in one step

```bash
git fetch origin
# a branch on origin, such as a pull request's
git worktree add --lock --reason "<agent or person> working: <task>" \
  --detach .claude/worktrees/<name> origin/<branch>
# a new branch
git worktree add --lock --reason "<agent or person> working: <task>" \
  --detach .claude/worktrees/<name> origin/<branch-to-start-from>
```

**The worktree holds no branch, so anyone can check the branch out while
you work.** git lets a branch be checked out in one place only. While a
worktree holds a pull request's branch, `gh pr checkout`, an IDE's "check out
pull request", the person's own `git checkout` and another agent's worktree
for that branch all fail with `fatal: '<branch>' is already checked out at
…`. Never create a local branch for the work.

Commit on the detached HEAD, and push after every commit:

```bash
git push origin HEAD:refs/heads/<branch>
```

The first push of a new branch creates it on origin; open the pull request
from it. Write the full `refs/heads/<branch>`: from a detached HEAD, git
refuses a short name that doesn't exist on origin yet. To take in commits
someone else pushed, run `git fetch origin` and
`git merge --ff-only origin/<branch>`. If someone pushed while a commit of
yours was still unpushed, `--ff-only` refuses: run `git merge origin/<branch>`
instead, and push. Never force-push.

**A commit on a detached HEAD is on no branch.** Only the worktree's own
HEAD reflog holds it, and removing the worktree deletes that reflog. Pushing
after every commit puts it on origin, and the removal steps below check that
HEAD is there.

`--reason` with `add` needs git 2.33 or later. On an older git, add the
worktree with `--lock` alone and run
`git worktree lock --reason "<who> working: <task>" <path>` straight after.

**The lock is how other agents know the worktree is in use.** Between
commands an agent has no process in its worktree, so nothing else can tell
that it is still working there. Nobody removes a locked worktree but its
owner.

Never create it from `origin/main` and then check out another branch. Git
deletes and restores every file the two branches differ by, and editors index
that churn and report it as mass deletions.

## Keep it inside the project

Put it under `.claude/worktrees/<name>` of the main checkout, and add
`.claude/worktrees/` to `.gitignore` if it is not there. Run `git worktree
add` from the main checkout, or give it an absolute path. Run from inside
another worktree, a relative path nests the new tree inside that one, and
removing the outer tree then deletes it. Inside the project, your permissions
and tooling already cover it. Don't put it outside the repository.

## Remove it the moment its work has landed

Its work has landed when a pull request is open for the branch it pushes
to, or when its commits are pushed to the default branch. Remove the worktree
then, in the same turn, before you report done:

1. Nothing is running in it, and your own shell is not inside it.
2. It is safe to remove: every check in *Safe to remove* below passes.
3. HEAD is pushed: after `git -C <worktree> fetch origin`,
   `git -C <worktree> branch -r --contains HEAD` lists `origin/<branch>`, the
   branch you pushed to.
4. If you locked it: `git -C <main checkout> worktree unlock <worktree>`
5. `git -C <main checkout> worktree remove <worktree>`

Never discard uncommitted work to get there: if step 2 or 3 fails, ask the
user. Recreating a worktree takes seconds. None of these is a reason to keep
one:

- "Review might want changes." Recreate it when they do.
- "I might want to verify the result." `git show origin/<branch>:<path>`
  reads exactly what was pushed.
- "Another agent can reuse it." Its lock names you, not that agent, and a
  fresh worktree takes that agent seconds.

### Safe to remove

Removing a worktree deletes its files, its own HEAD reflog and its own
refs. Check it with the skill's command, which applies the same judgement as
the hook (`<base directory>` is explained under *Remind and block modes*):

```bash
python3 "<base directory>/scripts/worktree-sweep.py" check <worktree>
```

It prints "Safe to remove" and exits 0, or names what is wrong and exits 1
(2 when it can't tell). It is safe only when all of these hold:

- **Clean:** `git -C <worktree> status --porcelain --untracked-files=all`
  prints nothing. The flag counts untracked files even where a config
  hides them.
- **No hidden edits:** `git -C <worktree> ls-files -v` shows no `S` or
  lowercase tag. If some files carry one, the `check` command finds whether
  each of them still matches git's copy. Skip-worktree and assume-unchanged
  files can hold edits `git status` doesn't show.
- **No commit lost:** every commit in its HEAD, its HEAD reflog and the refs
  only this worktree has (under `refs/worktree`, `refs/bisect` and
  `refs/rewritten`) is reachable from something removal keeps: a branch, tag or remote
  ref, any branch's reflog, or another worktree's or the main checkout's
  HEAD and reflog. A commit on a detached HEAD is kept only once it is
  pushed, by the remote ref.
- **No submodules:** `"$(git -C <worktree> rev-parse --absolute-git-dir)/modules"`
  does not exist, and no path that `git -C <worktree> ls-files -s` lists with
  mode `160000` holds a `.git`. `git worktree remove` refuses a tree with
  submodules, after an unlock has already dropped the lock.
- **No worktree inside it:** no other entry of `git worktree list` lies
  inside it. Removing it would delete that one too.

## Remove it when you stop without work

When your task ends with nothing committed in the worktree, because you gave
up, found no change was needed, or handed the work off, remove it in the
same turn, before you report:

1. Nothing is running in it, and your own shell is not inside it.
2. It is safe to remove: every check in *Safe to remove* passes.
3. If you locked it: `git -C <main checkout> worktree unlock <worktree>`
4. `git -C <main checkout> worktree remove <worktree>`

If step 2 fails, ask the user; never discard work. The hook never lists
such a worktree for you: it looks the same as one an agent is about to use,
so only you know it is finished.

## Sweep whenever you list them

Whenever `git worktree list` runs, check every entry, not only the one you
came for. Remove any whose work has landed and whose tree is clean,
including ones you did not create, by the steps for landed work, with these
four exceptions:

- **Never remove a locked worktree you did not lock**, whoever created it,
  however finished it looks. `git worktree list` shows `locked` beside it. If
  one looks abandoned, tell the user and show its lock reason
  (`git worktree list --porcelain`).
- Never unlock a worktree to remove it unless you locked it.
- Leave an unlocked worktree that someone else used in the last hour: its
  owner may simply not have locked it. You can tell it was used: its
  `index` or `HEAD` in `<main checkout>/.git/worktrees/<name>/` changed in
  that hour, or its newest `git -C <worktree> reflog` entry is from that
  hour.
- Leave a worktree someone else made that has no commits of its own: one
  whose `git -C <worktree> reflog` shows no commit, merge, rebase,
  cherry-pick or revert since its current HEAD was checked out there.
  Fast-forwards don't count, nor do a rebase's entries that make no commit:
  `start`, `finish`, `abort`, and `reset`, which `--rebase-merges` logs. Its HEAD being on origin, for example on
  `origin/main` because it was just created from there, doesn't mean work
  has landed: it may be a review checkout, or a tree an agent is about to
  work in. If one looks abandoned, tell the user.

Run `git worktree prune` for an entry whose directory no longer exists.

## Briefing other agents

A brief that tells an agent to create a worktree tells it to create it
locked and detached, with a reason naming the agent and the task, and to
push each commit with `git push origin HEAD:refs/heads/<branch>`. It also
tells the agent, as its last step once the work has landed, to remove that
worktree by the steps in *Remove it the moment its work has landed*. An agent not told this keeps it, and an agent that doesn't lock one can
have it removed by another agent's sweep.

## The hook

This skill ships a hook that lists worktrees whose work has landed, for you
to remove:

- **After a push:** only the worktree you pushed from, even if it is locked.
  A locked one comes with its lock reason and the command to unlock it and
  then remove it. Unlock it only if the lock is yours; otherwise ask the user.
- **When you stop:** every worktree in the repository, except locked ones and
  other worktrees used in the last hour.

A listed worktree passes every check in *Safe to remove*. It also has
commits made in it and a HEAD on origin, nothing is running in it, and no
rebase, merge, cherry-pick, revert, bisect or notes merge is paused in it.
Remove each one with the command it prints, or ask the user if one must stay.
The hook never removes anything itself.

A locked worktree you didn't just push from is never listed for you. A
worktree that has been idle for a day, locked or not, is shown to the user
instead and never to you: no git activity there, and no file that
`git status` lists as changed was modified in that time. The user sees its
lock reason, whether it is clean, how many commits removing it would lose,
and a remove command when removing it loses nothing.

In Cursor, the hook adds the list to the agent's context after a push and,
at a stop, only when the user has turned on block mode. A Cursor stop hook can't
show the user anything, so Cursor users never see the idle worktrees.

## Remind and block modes

When the user asks which worktrees mode is on, or asks to switch to block or
remind mode, run:

```bash
python3 "<base directory>/scripts/worktree-sweep.py" mode           # which mode is on
python3 "<base directory>/scripts/worktree-sweep.py" mode block      # or: mode remind
```

`<base directory>` is this skill's base directory: the directory that holds
this SKILL.md, which Claude Code names on the "Base directory for this skill:"
line above it. Write the path out in full.

Tell the user the result in a sentence: the mode the hook uses and where it
comes from. Don't edit the config file yourself: the command keeps the
file's other keys and won't overwrite a file it can't parse. If it refuses,
show the user its message. If it says `WORKTREES_MODE` overrides the file,
tell the user the variable decides, and that the file counts only once the
variable is unset in the environment the agent is started from and the agent
restarted. A switch through the file takes effect at the hook's next run,
with no restart, since the hook reads the file every time it runs.

In remind mode, the default, the hook never stops you: you get the list as
context after a push, and the user sees it when you stop. In block mode you
are told to remove the listed worktrees right after a push, and when you stop
you are sent back to remove them, once.

# worktrees

Teaches your agent to do its work in git worktrees, so your own checkout is
never switched to another branch or left dirty. The agent locks each
worktree while it works there and removes it as soon as its work has landed.
A worktree left behind holds its branch: git refuses to check that branch out
anywhere else, so you can't open it to review until the worktree is gone.

Ask your agent to "install the worktrees skill". [SKILL.md](SKILL.md) holds
the rules it follows: when to use a worktree, how to create one locked on the
right branch, where to put it, and when to remove it. The lock is what tells
other agents a worktree is in use: never remove a locked worktree you did not
lock.

An agent that stops without committing anything in its worktree, because it
gave up, found nothing to change, or handed the work off, removes the
worktree before it reports. It first checks, with the skill's own
`worktree-sweep.py check`, that removing it loses nothing, and asks you if not. It also deletes the
branch it made for the worktree, once every commit on that branch and in its
reflog is on a remote.

## The hook

Installing the skill also turns on a hook, in Claude Code and in Cursor. It
tells the agent which worktrees to remove:

- **After a command that pushed**, only the worktree the push came from: the
  one the agent is working in, whose commit was just pushed. The hook reads
  the push from git, so any command that pushes counts. A push from your main
  checkout lists nothing.
- **When the agent stops**, every worktree in the repository, except locked
  ones and any other worktree used in the last hour. The agent's own worktree
  is listed however recently it was used.

A worktree is listed only when all of these hold:

- it has a branch checked out, not a detached HEAD;
- it is safe to remove: `git status` is clean, untracked files included;
  no skip-worktree or assume-unchanged file holds an edit; removing it loses
  no commit, such as one made earlier on a detached HEAD and left behind;
  and it has no submodules,
  which git refuses to remove;
- someone committed, merged, rebased, cherry-picked or reverted in that
  worktree; fast-forwards don't count. So a worktree made only to review a
  branch, or for an agent about to start, is never listed, even after it is
  updated to the author's latest push;
- its HEAD is on origin, on its own branch or on another, such as main;
- no other worktree sits inside it, since removing it would delete that one
  too;
- no program is running inside it, apart from the agent that ran the hook.

**It never deletes anything.** It tells the agent which worktrees to remove,
with the command for each, and the agent removes them or asks you.

**Locked worktrees are yours to judge.** The agent is never told to remove a
locked worktree, except the one it just pushed from. That one is listed with
its lock reason, and the agent is told to unlock it only if it locked it
itself, and otherwise to ask you.

**Idle worktrees are shown to you.** When the agent stops, Claude Code also
shows you every other worktree that has been idle for a day: no git
activity in it, and no file that `git status` lists as changed was modified
in that time. That catches a worktree whose agent gave up, died, or forgot
to remove it, locked or not. The hook doesn't judge whether work was done
in it; you get the facts and decide. "N commits removal would lose" counts
the commits that removing the worktree would lose:

```text
Worktrees idle for over a day: no git activity, and no changed file edited. Whoever was using one may be gone. A remove command is shown only where removing it loses nothing:
  /src/app/.claude/worktrees/fix-login  (branch fix-login)
    locked: agent B working: fix the login bug
    clean; no commit removal would lose
    git -C /src/app worktree unlock /src/app/.claude/worktrees/fix-login && git -C /src/app worktree remove /src/app/.claude/worktrees/fix-login
  /src/app/.claude/worktrees/spike  (branch spike)
    uncommitted changes; 2 commits removal would lose
```

The remove command appears only when the tree is safe to remove, by the
same test the agent's list uses. The tree is clean, and no skip-worktree or
assume-unchanged file holds an edit. Removing it loses no commit: a commit
on a branch stays with the branch, but one left behind on a detached HEAD
would be lost. It has no submodules, which git refuses to remove. Otherwise
you see what it holds and decide.

The agent is never told about idle worktrees, and they never block a stop.
The agent's own worktree is not shown, nor is one with a program running in
it or another worktree inside it. Cursor can't show you this list.

### Remind and block

The hook has two modes. **Remind**, the default, never stops the agent:

| | Remind (default) | Block |
|---|---|---|
| After a push, Claude Code | the agent gets the list as context | the agent is told to remove them now |
| When the agent stops, Claude Code | you see the list | the agent can't stop until it removes them or asks you; a second stop goes through and shows you the list |
| After a push, Cursor | the agent gets the list as context | the agent gets the list as context, worded as an instruction |
| When the agent stops, Cursor | nothing | the list is sent to the agent as a follow-up message, once |

Cursor gets less than Claude Code because its stop hook can't show you a
message, and its hook after a command can't block. The Cursor wiring follows
Cursor's hook documentation and has not been tried in a real Cursor.

**To see which mode is on**, ask your agent "which worktrees mode is on?". It
tells you the mode and where it comes from: the environment, the config file,
or the default.

**To switch**, ask your agent to "switch worktrees to block mode", or to
remind mode. The change applies to both hosts, from the hook's next run, with
no restart. Without an agent, run the same command it does:

```bash
python3 ~/.agents/skills/worktrees/scripts/worktree-sweep.py mode          # which mode is on
python3 ~/.agents/skills/worktrees/scripts/worktree-sweep.py mode block    # or: mode remind
```

It writes `~/.config/shared-skills/worktrees.json`, or the file named by
`WORKTREES_CONFIG`, and keeps any other keys in it. A `WORKTREES_MODE`
environment variable set to `block` or `remind`, in the environment the agent
was started from, overrides the file; the command says so when it is set.

**To turn the hook off**, ask your agent to "turn off the worktrees hook", or:

```bash
python3 ~/.agents/skills/manage-skills/scripts/skills.py disable-hook worktrees
```

The choice sticks: installing skills again later won't turn it back on. The
skill's rules still apply with the hook off.

## Troubleshooting

**It listed a worktree that should stay.** Tell the agent to keep it. To see
why it was listed, run the hook by hand against the repository:

```bash
echo '{"cwd": "/path/to/repo"}' | ~/.agents/skills/worktrees/scripts/worktree-sweep.py --host claude --event stop
```

It prints what a stop in that repository would show. Then check that worktree
against the conditions above:
`git -C <worktree> status --porcelain --untracked-files=all`,
`git -C <worktree> reflog`, and `git -C <worktree> branch -r --contains HEAD`,
or run `worktree-sweep.py check <worktree>`, which says what makes it unsafe.

**It didn't list a worktree whose work has landed.** One of the conditions
failed. The usual ones are:

- an untracked file in the worktree;
- a commit left behind on a detached HEAD, which only its reflog holds;
- a submodule;
- a terminal, dev server or other program whose working directory is
  inside it;
- work that was committed somewhere else and only checked out in the
  unlisted worktree, so its reflog shows no commit.

A locked worktree is also skipped, and so is one someone used in the last
hour, unless it is the agent's own. So is a
worktree whose name holds a control or invisible character, such as a
zero-width joiner, and a worktree whose branch was pushed from a
single-branch or shallow clone, which has no `origin/<branch>` to compare
with. The hook lists nothing when it can't tell
which programs are running: on macOS it needs `lsof`.

A worktree left off the list this way is shown to you once it has been idle
for a day, unless a program is running in it or another worktree sits
inside it.

**It doesn't see a repository.** The hook looks in the agent's working
directory and the workspace folders, and, when the agent stops, any
`.claude/worktrees/` path in the conversation. A worktree outside all of
those isn't checked. A push the agent made with `git -C` from outside the
worktree gets no reminder, since the hook can't tell that worktree is the
agent's own. The agent's own steps from SKILL.md still remove it.

## Tests

From the root of your shared-skills clone:

```bash
python3 .agents/skills/worktrees/scripts/test_worktree_sweep.py
```

Why the hook works the way it does: [DECISIONS.md](DECISIONS.md).

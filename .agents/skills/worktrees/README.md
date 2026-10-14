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
- `git status` is clean, untracked files included;
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
itself, and otherwise to ask you. When a locked worktree has landed and has
seen no git activity for a day, Claude Code shows it to you when the agent
stops, with its lock reason, in case the agent that locked it is gone. Cursor
can't show it to you.

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

**To turn block mode on**, for both hosts:

```bash
mkdir -p ~/.config/shared-skills
echo '{"mode": "block"}' > ~/.config/shared-skills/worktrees.json
```

Delete that file, or set `"mode"` to `"remind"`, to go back. A
`WORKTREES_MODE` environment variable set to `block` or `remind`, in the
environment the agent was started from, overrides the file.

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
against the conditions above: `git -C <worktree> status --porcelain`,
`git -C <worktree> reflog`, and `git -C <worktree> branch -r --contains HEAD`.

**It didn't list a worktree whose work has landed.** One of the conditions
failed. The usual ones are an untracked file in the worktree, a terminal, dev
server or other program whose working directory is inside it, or work that
was committed somewhere else and only checked out there, so that worktree's
reflog shows no commit. A worktree that is locked, or that someone used in
the last hour, is also skipped unless it is the agent's own. So is a
worktree whose name holds a control or invisible character, such as a
zero-width joiner, and a worktree whose branch was pushed from a
single-branch or shallow clone, which has no `origin/<branch>` to compare
with. The hook lists nothing when it can't tell
which programs are running: on macOS it needs `lsof`.

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

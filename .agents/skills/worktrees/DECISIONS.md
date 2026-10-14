# worktrees — decisions

Read this before changing `scripts/worktree-sweep.py` or `hook.json`. Each
entry is a decision, why it was made, and what was rejected.

---

## A locked worktree is listed only to the agent that just pushed from it

**Decision.** SKILL.md has every agent create its worktree locked, with a
reason naming the agent and the task, and unlock it only as the last step
before removing it. The hook lists a locked worktree for the agent in one
case only: after a push from that worktree by this session, with the command
to unlock and then remove it. At Stop, and for any other worktree, a locked
worktree is never listed for the agent. When a locked worktree has landed
and its git directory has not changed for 24 hours, the hook shows it to the
user at Stop, with its lock reason, and tells the agent nothing.

**Why.** In a run with several agents working in parallel, agents sweeping
"landed" worktrees removed other agents' worktrees while those agents were
still working in them, one of them twice and one in the middle of a build.
An agent's shell keeps no process in its directory between commands, so the
busy check (see *Busy is decided from every process's working directory*)
sees nothing. Only the owner knows it is still working,
and a lock is how it says so.

**Why the push's own worktree is the exception (the maintainer's decision).** Every worktree made
as SKILL.md says is locked, so without it the hook would never remind an
agent about the worktree it just finished. The push identifies that worktree
by the session's own directory and a commit pushed during the command.

git cannot say who locked a worktree, so this can still name another agent's
locked tree. One case is a session that pushed from inside that agent's
worktree on its behalf. Another is a session standing in that agent's
worktree while the agent pushed the worktree's HEAD: both conditions then
hold, the session's directory and a commit pushed during its command. The listing therefore shows the
lock reason and tells the agent to unlock only a worktree it locked, and
otherwise to ask the user.

**24 hours** is far longer than an agent holds a finished worktree before
removing it, and short enough that a crashed agent's tree is noticed the next
day. Only the user decides a lock is abandoned: an agent cannot tell a dead
owner from a slow one.

## The push check lists only the worktree the push came from

**Decision.** After a push, the hook looks only at a worktree that holds the
session's cwd or a workspace root and whose HEAD is a commit just pushed.
The sweep of every worktree runs only at Stop, where locks and the recency
guard protect other agents' trees.

**Why.** A push tells the hook which worktree's work just landed and nothing
about any other. Listing siblings there is what had agents removing each
other's worktrees mid-task. The session's directory is required, not just a
matching commit, because the reflogs that record pushes are shared by every
worktree of a repo: another agent's push, made a few seconds before this
session's command, matches that agent's worktree.

## Another session's worktree used in the last hour is skipped

**Decision.** At Stop, a worktree that is not the session's own is skipped
when its per-worktree git directory (`.git/worktrees/<name>`: the directory,
`index`, `HEAD`, `logs/HEAD`) changed in the last 60 minutes. Those times are
read before the hook runs any git command in the worktree, and every git
command runs with `GIT_OPTIONAL_LOCKS=0`, because `git status` otherwise
rewrites the index and every worktree would look just used. The session's
own worktree is exempt and is listed the moment its work lands.

**Why.** Not every agent locks its worktree. An agent can go many minutes
between git commands while it signs prose, waits on a reviewer or opens a
pull request, so a short window would catch it mid-task. The sweep is a
backstop, since each owner removes its own, so waiting an hour costs little.
The session's own worktree needs no guard: the session knows it is done.

## A worktree is listed only if its own reflog shows local work

**Decision.** The worktree's own HEAD reflog must hold a `commit`, `merge`,
`rebase`, `cherry-pick` or `revert` entry that is not a fast-forward and is
newer than the checkout that brought the current branch into the tree. A
worktree whose reflog since then shows only its creation or a fast-forward
is never listed, however clean and pushed it is.

**Why.** Two kinds of worktree are clean, on a branch and already on origin
without holding any landed work: one checked out to review a pushed branch,
and one an agent has just created and not yet committed in. Without this
condition the hook lists both. Several sessions often share one repository, so
one session's hook would then tell its agent to remove a tree another agent
is about to work in, or one the human is reviewing. A commit or merge made
in the tree is the cheapest signal that its work was done there and has now
landed.

**Rejected: the branch's reflog.** It outlives the worktree. A branch
committed in one worktree, which was then removed, and later checked out
fresh in another for review, still shows those commits, so the review tree
was listed. A fast-forward is excluded so that a review tree stays unlisted
too: a reviewer who runs `git merge --ff-only` to pick up the author's latest push has done no
work in the tree. **Rejected: the whole HEAD reflog.** A tree whose branch
landed and that was then switched to another branch, to review it or to start
new work, still shows the first branch's commits.

**Rejected: skipping worktrees created recently, or keeping a list of the
trees this session made.** A creation time says nothing about whether a
review or a task is still going on. A list is lost when the session ends, and
SKILL.md's sweep covers every landed tree, including those another session
made.

**Known gaps.** Work committed elsewhere and only checked out or pulled
here shows no local work, so that worktree is never listed. A review tree
brought up to date with `git rebase` instead of a fast-forward logs a
`rebase` entry and counts as local work. The README names the first case.

## Remind is the default

**Decision.** Without configuration, the hook never blocks: after a push the
agent gets the list as context, and at Stop the user sees it. Block mode is
opt-in, through `~/.config/shared-skills/worktrees.json` or `WORKTREES_MODE`.

**Why.** Three organizations install from this repository, and the hook runs
in every session of everyone who installs the skill. A Stop hook that blocks
takes over the end of every turn, and a false listing then costs a whole
extra turn. People who did not choose this rule should see it working before
it can stop their agent. Block mode is for someone who has already decided
that a landed worktree must go before the turn ends.

**Rejected: an argument in `hook.json`.** manage-skills wires the hook's
script by path with only `--host` appended, so a manifest has no per-user
argument. An environment variable alone would not reach Cursor when it is
started from the Dock, since it then doesn't read the user's shell profile. A
config file reaches both hosts, so the file is the documented switch and the
variable only overrides it.

## The agent switches modes with a command, not by editing the file

**Decision.** `worktree-sweep.py mode` prints the mode and where it comes
from, and `mode block` or `mode remind` writes it. SKILL.md has the agent run
it and not edit the config file itself.

**Why.** The command reports through the hook's own `mode()`, so what it
prints is what the hook uses, including when `WORKTREES_MODE` overrides the
file, or when a malformed file makes the hook fall back to remind. An agent
editing the file by hand could report a mode the hook doesn't use. The command
also keeps the file's other keys, writes atomically, and refuses a file it
can't parse instead of overwriting it.

**Known gap.** The command sees the environment of the agent's shell, and the
hook sees the host's. The two differ when the agent's shell loads the user's
shell profile and the host, started from the Dock, did not. A
`WORKTREES_MODE` set only in that profile then reaches the command but not
the hook: the command reports the variable while the hook uses the file.

## The hook never deletes

**Decision.** The hook lists worktrees and the command to remove each one. It
never runs that command.

**Why.** Every condition is a heuristic over state that can change between
the check and the removal: a file written a second later, an editor opened
inside the tree, a commit the reflog reads differently than expected.
`git worktree remove` refuses a dirty tree, but not a tree whose clean state
is someone's half-finished review. The agent can see what the conversation
was about and can ask the user; the hook can't. A wrong listing costs a
sentence of the agent's attention, and a wrong deletion costs someone's
working directory.

## A second Stop does not block again

**Decision.** In block mode, a Stop that is already continuing because of a
stop hook (`stop_hook_active` in Claude Code, `loop_count` above 0 in
Cursor) does not block. Claude Code shows the user the list instead; Cursor
has no channel to the user at Stop, so it shows nothing.

**Why.** Some worktrees can't be removed by the agent: a terminal is open in
one, or the user wants it kept. Blocking again would loop until the host's
own cap ends the turn (eight continuations in Claude Code, five follow-ups
in Cursor), spending a turn each time on the same list. One block gives the
agent the chance to act; after that the user decides.

## Busy is decided from every process's working directory

**Decision.** A worktree is skipped when any process has its working
directory inside it, except the hook itself and the processes that started
it, found by walking parent process ids from `ps`. On Linux the hook reads
`/proc/<pid>/cwd`; elsewhere it runs `lsof`. When neither can run, the hook
lists nothing. "Inside" is decided by device and inode, walking up from each
process's directory, not by comparing path strings.

**Why.** Removing a tree that a test run, a build or another agent is using
breaks that process. The agent that ran the hook is exempt because it often
sits in the worktree it just pushed from, and the message tells it to leave
first. Listing nothing when processes can't be read keeps the guarantee that
a busy tree is never listed, at the cost of silence.

**Rejected: exempting every process whose directory equals the session's
working directory.** A dev server or test run the agent started in the
background shares that directory, so its tree was listed as idle. **Rejected:
comparing path strings.** git records a worktree's path as it was typed, so
on a case-insensitive disk a path in other letter case, or reached through a
symlink, never matched the path `lsof` reports.

**Escaped paths.** lsof prints some characters in a path escaped. When the
path lsof prints for a process doesn't exist on disk and holds a backslash, a
caret or U+FFFD, the process's real directory is unknown. Everything under its nearest existing ancestor then
counts as busy. lsof runs with `LC_ALL` removed and `LC_CTYPE=UTF-8`: in the
C locale it escapes every non-ASCII byte, and a single process in a directory
such as `~/Développement` made all of the home directory look busy.

**Known gap.** An editor with the worktree open does not usually have its
working directory there, so it does not make the tree busy.

## A worktree with another worktree inside it is not listed

**Decision.** A worktree is skipped when another registered worktree's
directory lies inside it.

**Why.** An agent standing in a worktree that runs
`git worktree add .claude/worktrees/<name>` creates the new tree inside the
current one, where `.gitignore` hides it from `git status`. `git worktree
remove` on the outer tree then deletes the inner one, uncommitted files
included, without a warning.

**Known gap.** Other ignored files, such as a `.env`, are also invisible to
`git status`, and `git worktree remove` deletes them. Counting ignored files
as dirty would stop nearly every worktree being listed, since build output
and installed dependencies are ignored too.

## A push is read from git, not from the command

**Decision.** The push check runs after every command, and finds a push in
the reflogs of `refs/remotes/origin/*`: git writes an `update by push` entry
there whenever a push moves a remote-tracking ref. An entry counts only when
it is no older than the command's start, from the duration the host reports,
less five seconds for rounding. When the host reports no duration, it counts
within the last minute, and only for a command whose text contains "push".
The reflog files are read directly, because a git command per ref on every
command the agent runs would cost too much. Remote-tracking reflogs are on by
default: `core.logAllRefUpdates` defaults to true in a repository with a
working tree, and a non-bare clone sets it.

**Why.** Reading the command text kept missing pushes. A push inside
`bash -c '...'`, inside `$(...)`, behind `sudo -u`, after a comment line, or
after a heredoc whose body held an apostrophe was missed, and a heredoc body
mentioning `git push` was taken for one. Three rounds of fixes to a shell
parser each found more cases. git records the push itself, whatever command
made it.

**Rejected: a fixed window of a minute after any command.** The reflogs are
shared by every worktree of a repo. A session standing in another agent's
locked worktree, to review it, was told to unlock and remove it when it ran
`git log` a few seconds after that agent pushed. In block mode, every command
in the minute after a push also exited 2.

**Known gaps.** A repository using the reftable ref store has no reflog
files, so the push check finds nothing there. Neither does a bare clone used
as the home of worktrees, which keeps no remote-tracking refs. A single-branch
or shallow clone creates no tracking ref for a newly pushed branch, so neither
the push check nor Stop lists that worktree. A push made with `git -C` from
outside the worktree is not tied to the session's directory, so it gets no
reminder after the push. At Stop that worktree is not the session's own, so
it is listed only once it has gone an hour unused and only if it is not
locked. Either way the agent's own removal step, from SKILL.md, is what
removes it.

## Names from git are read as bytes and printed only when safe

**Decision.** `git worktree list --porcelain -z` is read as bytes and split
on NUL; on a git older than 2.36, which lacks `-z`, it is split on "\n"
alone. Paths are decoded with `os.fsdecode`, so they name the same files. A
path listed twice is dropped, and a worktree's lock is read from the
`locked` file in its own git directory, not from this output. A directory
without a `.git` file of its own that names an existing git directory is
never listed: every git command run there would answer for the repository above
it, and its lock could not be read. A worktree whose path, branch or main
checkout holds a control or format character, a line or paragraph separator,
or bytes that aren't UTF-8 is never listed. A lock reason has those
characters turned into spaces.

**Why.** Python's `splitlines()` also splits on U+2028, U+0085 and others,
which a branch name or a lock reason can hold. A branch name split that way
ended its entry early and dropped the `locked` line, so a locked worktree was
listed for removal; a lock reason could forge a whole entry. Decoding paths
with replacement characters made a nested worktree's path nonexistent, so the
nesting check missed it. Without `-z`, git prints a path raw, so a directory
named with newlines forged an entry, without its lock, for a locked worktree
(seen with git 2.34, which Ubuntu 22.04 ships). Printing such text could also
add lines to what the agent or the user reads.

**Known issue.** On Linux, a worktree whose `.git` file holds bytes that
aren't UTF-8, because its path does, makes the hook fail while reading that
file. The hook then exits 0 having listed nothing, for any repository. macOS
refuses such file names, so it can't happen there.

**Known limitation.** A name holding a zero-width joiner or non-joiner (U+200D,
U+200C) is never listed, since those are format characters. That hides, for
example, a worktree whose name is a Persian word written with ZWNJ, or an emoji
sequence, even after the session's own push.

## Cursor gets the push check and, in block mode, one follow-up

**Decision.** In Cursor the hook runs on `postToolUse` for the `Shell` tool
and on `stop`. After a push it returns `additional_context` in both modes. At
`stop` it returns `followup_message` in block mode only, when `status` is
`completed` and `loop_count` is 0; otherwise it returns `{}`.

**Why.** Cursor's `postToolUse` can add context but cannot block, and its
`stop` hook can only submit a message to the agent as the next prompt; it has
no field shown to the user. A follow-up after an aborted or failed run would
restart work the user just stopped. This is wired from Cursor's hook
documentation and has not been run in a real Cursor.

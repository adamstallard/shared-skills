#!/usr/bin/env python3
"""Tells the agent which git worktrees to remove because their work has landed.

A worktree holding a branch stops anyone checking that branch out elsewhere,
so it should go as soon as its work is pushed. This hook never removes
anything itself. Read ../DECISIONS.md before changing it.

When it looks, and at what:
  - After a command that pushed (PostToolUse, or Cursor's postToolUse): only
    the worktree the push came from. That is a linked worktree that holds the
    payload's cwd or a workspace root, and whose HEAD was pushed during the
    command. The push is read from git, as an "update by push" entry in a
    refs/remotes/origin/* reflog no older than the command's start, from the
    duration the host reports. Without a duration, an entry from the last
    PUSH_FALLBACK_SECONDS counts, and only for a command whose text contains
    "push". Every worktree of a repo shares those reflogs, so requiring the
    session's own directory is what keeps another agent's just-pushed
    worktree off the list. This one worktree is listed even when locked, with
    its lock reason and an unlock command.
  - At Stop: every worktree of every repo it finds, except locked ones and,
    unless it is the session's own, any whose git directory
    (.git/worktrees/<name>: the directory, index, HEAD, logs/HEAD) changed in
    the last RECENT_SECONDS. Those times are read before git runs in the
    worktree, and git runs with GIT_OPTIONAL_LOCKS=0, so `git status` does not
    rewrite the index.

A worktree is listed only when all of these hold:
  - it is a linked worktree with a `.git` file of its own and a branch
    checked out
  - `git status --porcelain` is empty, untracked files included
  - its own HEAD reflog shows a commit, merge, rebase, cherry-pick or revert
    since its branch was checked out there, fast-forwards aside, so a
    checkout made for review or for an agent about to start is never listed
  - HEAD is reachable from a refs/remotes/origin/* ref
  - no other worktree sits inside it, since removing it would delete that one
  - no process has its working directory inside it, apart from this hook and
    the processes that started it; when processes can't be read, nothing is
    listed
  - its path, its branch and the main checkout's path hold no control,
    format or line-separator character and no undecodable byte, so printing
    them can't add a line to the listing

"Inside" compares device and inode, so another spelling of a path still counts.

At Stop, a locked worktree that meets every other condition and whose git
directory has not changed for STALE_SECONDS is shown to the user, with its
lock reason, as possibly abandoned. The agent is not told.

Usage: worktree-sweep.py --host <claude|cursor> [--event push|stop], with the
host's payload on stdin. The event comes from hook_event_name; --event
overrides it.

Mode: WORKTREES_MODE, else "mode" in ~/.config/shared-skills/worktrees.json
(WORKTREES_CONFIG names another file). Anything but "block" means remind.
  remind  never blocks. After a push the agent gets the list as context. At
          Stop, Claude Code shows the user the list, and Cursor shows nothing.
  block   after a push the agent is told to remove them now, and Stop is
          blocked until it has. A Stop that already continues an earlier block
          (stop_hook_active, or Cursor's loop_count above 0) is not blocked
          again: Claude Code shows the user the list, and Cursor shows nothing.
At every Stop the hook does not block, Claude Code also shows the user the
possibly abandoned locked worktrees.

Repos are found from the payload's cwd and workspace_roots and, at Stop, from
any `.../.claude/worktrees/...` path in the transcript, so a session started
outside a repo still sees the worktrees it worked in.

Any crash exits 0, so a broken hook never blocks a session.

To see why a worktree is or is not listed, run it by hand:
  echo '{"cwd": "<repo>"}' | worktree-sweep.py --host claude --event stop
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
import unicodedata

# A worktree another agent used this recently may still be its working tree:
# an agent can go many minutes between git commands while it waits on a
# reviewer or writes a pull request.
RECENT_SECONDS = 60 * 60
# A locked worktree untouched this long may have lost the agent that locked it.
STALE_SECONDS = 24 * 60 * 60
# A push counts as the command's own when its reflog entry is no older than
# the command's start, by the duration the host reports, less this margin for
# clock rounding. Reflogs are shared by every worktree of a repo, so a wider
# window would pick up another agent's push.
PUSH_SLACK_SECONDS = 5
# When the host reports no duration: how far back a push counts, and only for
# a command whose text mentions "push".
PUSH_FALLBACK_SECONDS = 60

LOCAL_WORK = re.compile(r"^(commit|merge|rebase|cherry-pick|revert)\b")
WORKTREE_TAIL = re.compile(r"/\.claude/worktrees/[^\s\"'`/:\\]+")
# Characters that end a path in a transcript. A backslash is one: in JSON it
# starts an escape such as \n.
PATH_END = set(" \t\r\n\"'`:\\")
# Unicode categories never printed into a listing: control and format
# characters, unpaired surrogates (undecodable bytes), and line and paragraph
# separators. Any of them could add a line, or a terminal escape, to what the
# agent or the user reads.
UNSAFE = {"Cc", "Cf", "Cs", "Zl", "Zp"}
SWITCH = re.compile(r"^checkout: moving from (.*) to (.*)$")
CONFIG = os.path.join("~", ".config", "shared-skills", "worktrees.json")


def git(*args, cwd=None):
    # GIT_OPTIONAL_LOCKS=0 keeps `git status` from rewriting a worktree's
    # index, which would make it look recently used.
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    # errors="replace": a path or ref name in git's output can hold bytes that
    # aren't UTF-8, and one of them must not stop the whole hook.
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True,
                       errors="replace", timeout=20)
    return r.returncode, r.stdout.strip()


def mode():
    value = os.environ.get("WORKTREES_MODE", "").strip()
    if not value:
        path = os.path.expanduser(os.environ.get("WORKTREES_CONFIG") or CONFIG)
        try:
            with open(path) as f:
                value = str(json.load(f).get("mode", ""))
        except (OSError, ValueError, AttributeError):
            value = ""
    return "block" if value.strip().lower() == "block" else "remind"


def common_dir(path):
    if not path or not os.path.isdir(path):
        return None
    code, out = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=path)
    return os.path.realpath(out) if code == 0 and out else None


def worktrees(common):
    """(main checkout's path, [linked worktree entries]) from `git worktree list`.

    Read as bytes, split on NUL (`-z`, git 2.36 and later) or else on "\n"
    alone, with paths decoded by os.fsdecode so they name the same files.
    Splitting decoded text on line breaks would also split on characters
    such as U+2028, which a branch name can hold, and end an entry early.

    Without -z, git prints a path raw, so a path holding newlines can forge
    an entry for another worktree. A forged entry repeats a real worktree's
    path, so every path listed twice is dropped, the real entry with the
    forgery. A worktree's lock is read from its own git directory, not from
    this output.
    """
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    for flags, sep in ((["-z"], b"\0"), ([], b"\n")):
        r = subprocess.run(["git", "--git-dir", common, "worktree", "list", "--porcelain",
                            *flags], env=env, capture_output=True, timeout=20)
        if r.returncode == 0:
            break
    else:
        return None, []
    entries, cur = [], {}
    for field in r.stdout.split(sep) + [b""]:
        if not field:
            if cur:
                entries.append(cur)
            cur = {}
        elif field.startswith(b"worktree "):
            cur["path"] = os.fsdecode(field[len(b"worktree "):])
        elif field.startswith(b"branch refs/heads/"):
            cur["branch"] = os.fsdecode(field[len(b"branch refs/heads/"):])
        elif field.split(b" ")[0] in (b"bare", b"detached", b"prunable"):
            cur[field.split(b" ")[0].decode()] = True
    if not entries:
        return None, []
    paths = [e.get("path") for e in entries]
    linked = [e for e in entries[1:] if paths.count(e.get("path")) == 1]
    for e in linked:
        reason = lock_reason(e.get("path"))
        if reason is not None:
            e["locked"] = reason
    return entries[0].get("path"), linked  # the first entry is the main checkout


def lock_reason(worktree):
    """The worktree's lock reason, on one line, or None when it isn't locked.
    git keeps it in the worktree's git directory, in a file named `locked`."""
    gitdir = git_dir_of(worktree) if worktree else None
    if not gitdir:
        return None
    try:
        with open(os.path.join(gitdir, "locked"), "rb") as f:
            text = f.read().decode("utf-8", "replace")
    except FileNotFoundError:
        return None
    except OSError:
        return "unreadable lock"
    return clean(text) or "no reason given"


def printable(text):
    return all(unicodedata.category(ch) not in UNSAFE for ch in text)


def clean(text):
    """Text on one line, with every UNSAFE character made a space."""
    return " ".join("".join(" " if unicodedata.category(ch) in UNSAFE else ch
                            for ch in text).split())


def git_dir_of(worktree):
    """A linked worktree's own git directory, read from its .git file."""
    try:
        with open(os.path.join(worktree, ".git")) as f:
            line = f.readline().strip()
    except OSError:
        return None
    if not line.startswith("gitdir: "):
        return None
    return os.path.join(worktree, line[len("gitdir: "):])


def has_own_git(path):
    """Is path a worktree whose `.git` file names a git directory that exists?
    Without one, every git command run there answers for the repository
    above it, and its lock can't be read."""
    gitdir = git_dir_of(path) if path and os.path.isdir(path) else None
    return bool(gitdir) and os.path.isdir(gitdir)


def last_used(worktree):
    """When the worktree's git directory last changed, or None if unknown."""
    gitdir = git_dir_of(worktree)
    if not gitdir:
        return None
    times = []
    for name in ("", "index", "HEAD", os.path.join("logs", "HEAD")):
        try:
            times.append(os.stat(os.path.join(gitdir, name)).st_mtime)
        except OSError:
            pass
    return max(times) if times else None


def identity(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_dev, st.st_ino


def identities_up_from(path):
    """The (device, inode) of path and of every directory above it."""
    ids, path = set(), os.path.abspath(path)
    while True:
        i = identity(path)
        if i:
            ids.add(i)
        parent = os.path.dirname(path)
        if parent == path:
            return ids
        path = parent


def run(*cmd, env=None):
    # cwd="/": a child started in the hook's own directory, which may be a
    # worktree, would itself count as a process inside it.
    return subprocess.run(list(cmd), capture_output=True, text=True, errors="replace",
                          timeout=10, cwd="/", env=env)


def own_lineage():
    """This process and every process above it: the agent that ran the hook."""
    parents = {}
    try:
        for line in run("ps", "-A", "-o", "pid=,ppid=").stdout.splitlines():
            pid, ppid = line.split()
            parents[int(pid)] = int(ppid)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    lineage, pid = set(), os.getpid()
    while pid and pid not in lineage:
        lineage.add(pid)
        pid = parents.get(pid)
    return lineage


def process_cwds():
    """{pid: working directory} of every running process, or None when they
    cannot be read.

    lsof exits non-zero whenever it cannot read some process, such as another
    user's, so its exit code is ignored and only a failure to run counts.
    """
    if os.path.isdir("/proc/self/cwd"):
        cwds = {}
        for pid in os.listdir("/proc"):
            if pid.isdigit():
                try:
                    cwds[int(pid)] = os.readlink(f"/proc/{pid}/cwd")
                except OSError:
                    pass
        return cwds
    # In a locale that isn't UTF-8, such as LC_ALL=C, lsof prints every
    # non-ASCII byte escaped, and each such directory would make a whole
    # tree look busy. Where the UTF-8 locale is missing, lsof uses C, as it
    # would without this setting.
    env = {k: v for k, v in os.environ.items() if k != "LC_ALL"}
    env["LC_CTYPE"] = "UTF-8"
    try:
        out = run("lsof", "-a", "-d", "cwd", "-F", "pn", env=env).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    cwds, pid = {}, None
    for line in out.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("n/") and pid is not None:
            cwds[pid] = line[1:]
    return cwds


def busy_identities():
    """(directories some other process is inside, directories whose whole
    tree counts as busy), each by (device, inode), or None when processes
    cannot be read.

    A process directory that does not exist and holds a backslash, a caret or
    U+FFFD is one lsof printed escaped, or whose bytes were not UTF-8, so its
    real path is unknown. Everything under its nearest existing ancestor then
    counts as busy.
    """
    cwds = process_cwds()
    if cwds is None:
        return None
    mine = own_lineage()
    inside, trees = set(), set()
    for pid, cwd in cwds.items():
        if pid in mine:
            continue
        inside |= identities_up_from(cwd)
        if not os.path.exists(cwd) and any(ch in cwd for ch in "\\^\ufffd"):
            parent = os.path.dirname(cwd)
            while parent and not os.path.exists(parent) and parent != os.path.dirname(parent):
                parent = os.path.dirname(parent)
            if identity(parent):
                trees.add(identity(parent))
    return inside, trees


def describe_if_landed(wt, main, others, busy):
    """The listing line for a worktree whose work has landed, or None. Locks
    are the caller's to judge."""
    path, branch = wt.get("path"), wt.get("branch")
    if not branch or wt.get("prunable") or not has_own_git(path):
        return None
    # A name that can't be printed safely can't be listed, and is skipped.
    if not (printable(path) and printable(branch) and printable(main)):
        return None
    me = identity(path)
    inside, trees = busy
    if me is None or me in inside or identities_up_from(path) & trees:
        return None
    if any(me in identities_up_from(o) for o in others if o != path and os.path.exists(o)):
        return None
    # Spelled out, so a config that hides untracked files can't hide them here.
    code, status = git("status", "--porcelain", "--untracked-files=normal", cwd=path)
    if code != 0 or status:
        return None
    code, log = git("reflog", "show", "--format=%gs", "HEAD", cwd=path)
    if code != 0 or not local_work(log.split("\n")):
        return None
    code, out = git("for-each-ref", "--contains", "HEAD", "--format=%(refname:short)",
                    "refs/remotes/origin", cwd=path)
    refs = [r for r in out.split("\n") if r not in ("", "origin", "origin/HEAD")]
    if code != 0 or not refs:
        return None
    on = f"origin/{branch}" if f"origin/{branch}" in refs else clean(refs[0])
    git_c = f"git -C {shlex.quote(main)} worktree"
    unlock = f"{git_c} unlock {shlex.quote(path)} && " if wt.get("locked") else ""
    return (f"  {path}  (branch {branch}, on {on})\n"
            f"    {unlock}{git_c} remove {shlex.quote(path)}")


def local_work(reflog):
    """Does this HEAD reflog, newest first, show work done on the branch now
    checked out? Entries before the checkout that brought that branch here
    belong to another branch, and fast-forwards are not work. `git rebase
    <upstream> <branch>` switches branches too, logging `rebase: checkout`."""
    for entry in reflog:
        switch = SWITCH.match(entry)
        if (switch and switch.group(1) != switch.group(2)) or entry.startswith("rebase: checkout "):
            return False
        if LOCAL_WORK.match(entry) and not entry.lower().endswith("fast-forward"):
            return True
    return False


def transcript_paths(text):
    """Every absolute `.../.claude/worktrees/<name>` path in the text.

    It finds the fixed `/.claude/worktrees/` part first and walks back from
    there to where the path starts. A pattern that searched for the start of
    the path instead takes time growing with the square of the length of a
    base64 image in the transcript: a minute for one screenshot.
    """
    paths = []
    for m in WORKTREE_TAIL.finditer(text):
        start = m.start()
        i, floor = start, max(0, start - 4096)
        while i > floor and text[i - 1] not in PATH_END:
            i -= 1
        head = text[i:start]
        slash = head.find("/")
        if slash >= 0 and len(head) - slash > 1:
            paths.append(head[slash:] + m.group(0))
    return paths


def session_dirs(payload):
    """The directories this session works in: the payload's cwd and workspace
    roots."""
    roots = payload.get("workspace_roots")
    dirs = [payload.get("cwd"), *(roots if isinstance(roots, list) else [])]
    return [os.path.expanduser(d) for d in dirs if isinstance(d, str) and d]


def pushed_commits(common, since):
    """The commits pushed since `since` (a unix time), read from the reflogs of
    refs/remotes/origin/*: git writes "update by push" there when a push
    moves a remote-tracking ref. Reflog files are read directly, since a git
    command per ref would cost too much on every command the agent runs."""
    pushed = set()
    for root, _, files in os.walk(os.path.join(common, "logs", "refs", "remotes", "origin")):
        for name in files:
            log = os.path.join(root, name)
            try:
                if os.stat(log).st_mtime < since:
                    continue
                with open(log, "rb") as f:
                    f.seek(max(0, os.stat(log).st_size - 8192))
                    lines = f.read().decode("utf-8", "replace").split("\n")
            except OSError:
                continue
            for line in reversed(lines):
                head, _, message = line.partition("\t")
                fields = head.split()
                try:
                    when = int(fields[-2])
                except (IndexError, ValueError):
                    continue
                if when < since:
                    break
                if message.strip() == "update by push":
                    pushed.add(fields[1])
    return pushed


def candidate_dirs(payload, event):
    dirs = session_dirs(payload)
    if event != "push":
        tp = payload.get("transcript_path")
        if isinstance(tp, str) and os.path.isfile(tp):
            with open(tp, errors="replace") as f:
                dirs += transcript_paths(f.read())
    return [os.path.expanduser(d.strip("'\"")) for d in dirs if isinstance(d, str) and d]


def event_of(payload):
    if "--event" in sys.argv:
        return sys.argv[sys.argv.index("--event") + 1]
    name = str(payload.get("hook_event_name", "")).lower()
    return {"posttooluse": "push", "stop": "stop"}.get(name)


def host_of():
    for i, arg in enumerate(sys.argv):
        if arg == "--host" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if arg.startswith("--host="):
            return arg[len("--host="):]
    return "claude"


def repos(payload, event):
    commons = []
    for d in candidate_dirs(payload, event):
        c = common_dir(d)
        if c and c not in commons:
            commons.append(c)
    return commons


def push_window_start(payload):
    """The earliest time a push can have been made by this command, or None
    when the command cannot have pushed."""
    for key in ("duration_ms", "duration"):
        value = payload.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            return time.time() - value / 1000 - PUSH_SLACK_SECONDS
    tool_input = payload.get("tool_input")
    text = tool_input.get("command") if isinstance(tool_input, dict) else None
    if isinstance(text, str) and "push" in text:
        return time.time() - PUSH_FALLBACK_SECONDS
    return None


def find_pushed(payload):
    """The listing for the worktree a push in this command came from, if its
    work has landed."""
    since = push_window_start(payload)
    if since is None:
        return []
    pushes = {c: p for c in repos(payload, "push") if (p := pushed_commits(c, since))}
    if not pushes:
        return []
    busy = busy_identities()
    if busy is None:
        return []
    mine = set()
    for d in session_dirs(payload):
        mine |= identities_up_from(d)
    found = []
    for c, shas in pushes.items():
        main, linked = worktrees(c)
        pushed_from = []
        for wt in linked:
            path = wt.get("path")
            if not path or wt.get("prunable") or not has_own_git(path):
                continue
            code, head = git("rev-parse", "HEAD", cwd=path)
            if code == 0 and head in shas:
                pushed_from.append(wt)
        others = [wt["path"] for wt in linked if wt.get("path")]
        for wt in pushed_from:
            if identity(wt["path"]) in mine and (
                    hit := describe_if_landed(wt, main or c, others, busy)):
                # git can't say who locked it, so the agent is shown the reason.
                found.append(f"{hit}\n    locked: {wt['locked']}" if wt.get("locked") else hit)
    return found


def find_landed(payload):
    """At Stop: (worktrees for the agent to remove, locked ones to show the
    user)."""
    commons = repos(payload, "stop")
    if not commons:
        return [], []
    busy = busy_identities()
    if busy is None:
        return [], []
    own = set()
    for d in session_dirs(payload):
        own |= identities_up_from(d)
    now = time.time()
    found, stale = [], []
    for c in commons:
        main, linked = worktrees(c)
        others = [wt["path"] for wt in linked if wt.get("path")]
        for wt in linked:
            path = wt.get("path") or ""
            # Read before any git command runs in the worktree.
            used = last_used(path)
            idle = now - used if used is not None else None
            if wt.get("locked"):
                if (idle is not None and idle > STALE_SECONDS
                        and (hit := describe_if_landed(wt, main or c, others, busy))):
                    stale.append(f"{hit}\n    locked: {wt['locked']}")
                continue
            if identity(path) not in own and (idle is None or idle < RECENT_SECONDS):
                continue
            if hit := describe_if_landed(wt, main or c, others, busy):
                found.append(hit)
    return found, stale


def agent_message(listing, mode_, host):
    leave = "ExitWorktree, or cd out" if host == "claude" else "cd out"
    head = ("These worktrees hold work that has already landed: clean tree, branch pushed "
            "to origin, nothing running in them.")
    tail = f"If this session is inside one, leave it first ({leave}). "
    if "\n    locked: " in listing:
        tail += ("A locked one is listed because this push came from it. Unlock it only if "
                 "you locked it; if someone else did, ask the user before touching it. ")
    if mode_ == "block":
        return (f"{head} Remove them now, before reporting done:\n{listing}\n"
                f"{tail}If one must stay, ask the user instead of skipping it.\n")
    return (f"{head} A worktree holding a branch stops anyone else checking that branch "
            f"out, so remove each one once you are done with it:\n{listing}\n"
            f"{tail}If one should stay, ask the user.\n")


def user_message(found, stale):
    parts = []
    if found:
        parts.append("Worktrees whose work has landed are still present:\n" + "\n".join(found))
    if stale:
        parts.append(
            "Locked worktrees whose work has landed, with no git activity for over a day. "
            "The agent that locked one may be gone; if so, unlock it "
            "(git worktree unlock <path>) and remove it:\n" + "\n".join(stale))
    return "\n\n".join(parts)


def report(found, stale, event, mode_, host, payload):
    """(stdout, stderr, exit code) for this host, event and mode."""
    listing = "\n".join(found)
    if host == "cursor":
        if not found:
            return "{}", "", 0
        if event == "push":
            return json.dumps({"additional_context": agent_message(listing, mode_, host)}), "", 0
        # Cursor's stop hook has no channel to the user, only a follow-up message
        # that it submits to the agent as the next prompt.
        if (mode_ == "block" and payload.get("status", "completed") == "completed"
                and not payload.get("loop_count")):
            return json.dumps({"followup_message": agent_message(listing, mode_, host)}), "", 0
        return "{}", "", 0

    if event == "push":
        if not found:
            return "", "", 0
        if mode_ == "block":
            return "", agent_message(listing, mode_, host), 2
        return json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": agent_message(listing, mode_, host)}}), "", 0
    if found and mode_ == "block" and not payload.get("stop_hook_active"):
        return "", agent_message(listing, mode_, host), 2
    if found or stale:
        return json.dumps({"systemMessage": user_message(found, stale)}), "", 0
    return "", "", 0


def main():
    host = host_of()
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        return 0
    event = event_of(payload) or "stop"
    if event == "push":
        found, stale = find_pushed(payload), []
    else:
        found, stale = find_landed(payload)
    out, err, code = report(found, stale, event, mode(), host, payload)
    if out:
        print(out)
    if err:
        sys.stderr.write(err)
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)

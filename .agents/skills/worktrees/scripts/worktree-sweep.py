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
    refs/remotes/origin/* reflog no older than the command's start: now, less
    the duration the host reports. Without a duration, an entry from the last
    PUSH_FALLBACK_SECONDS counts, and only for a command whose text contains
    "push". Every worktree of a repo shares those reflogs, so requiring the
    session's own directory is what keeps another agent's just-pushed
    worktree off the list. This one worktree is listed even when locked, with
    its lock reason and an unlock command.
  - At Stop: every worktree of every repo it finds, except two kinds. Locked
    ones are skipped. A worktree that isn't the session's own is also skipped
    when git did something in it during the last RECENT_SECONDS, by
    last_used. Those times are read before git runs in the
    worktree, and git runs with GIT_OPTIONAL_LOCKS=0, so `git status` does not
    rewrite the index.

A worktree is listed only when all of these hold:
  - it is a linked worktree with a `.git` file of its own and a branch
    checked out
  - it is safe to remove (judge and safe): `git status` is clean, untracked
    files included; no skip-worktree or assume-unchanged file differs on
    disk; removing it loses no commit (lost_commits); it has no submodule,
    which `git worktree remove` refuses; and no other worktree sits inside
    it, since removing it would delete that one
  - its own HEAD reflog shows a commit, merge, rebase, cherry-pick or revert
    since its branch was checked out there, fast-forwards aside, so a
    checkout made for review or for an agent about to start is never listed
  - HEAD is reachable from a refs/remotes/origin/* ref
  - no process has its working directory inside it, apart from this hook and
    the processes that started it; when processes can't be read, nothing is
    listed
  - its path, its branch and the main checkout's path hold no control,
    format or line-separator character and no undecodable byte, so printing
    them can't add a line to the listing

"Inside" compares device and inode, so another spelling of a path still counts.

At Stop, every idle linked worktree not in the agent's list is shown to the
user, locked or not, whatever its state. Idle means git has done nothing
there for IDLE_SECONDS, by last_used, and no file that `git status` lists as
changed was modified in that time. That counts every file inside an
untracked nested repository or a changed submodule, a moved or deleted file
by its directory's time, and the skip-worktree and assume-unchanged files
that differ on disk. The session's own worktree, a busy one (a process has
its working directory inside it), and one whose names can't be printed
safely or that holds another worktree are not shown. Each comes with its
branch, lock reason, whether it is clean, how many commits removing it would
lose, and whether it has submodules. A remove command is shown only when it
is safe to remove, by the same judgement as the list above. The agent is not
told.

Usage: worktree-sweep.py --host <claude|cursor> [--event push|stop], with the
host's payload on stdin. The event comes from hook_event_name; --event
overrides it.

       worktree-sweep.py check <worktree>
Says whether removing a linked worktree is safe, by the same judgement as
"it is safe to remove" in the list above, and if not, why. Exits 0 when
safe, 1 when not, 2 when it can't tell.

       worktree-sweep.py mode [block|remind]
With no value, prints the mode the hook would use and where it comes from.
With one, writes it to the config file, keeping the file's other keys, and
then prints the mode the hook would use.

Mode: WORKTREES_MODE, else "mode" in ~/.config/shared-skills/worktrees.json
(WORKTREES_CONFIG names another file). Anything but "block" means remind.
  remind  never blocks. After a push the agent gets the list as context. At
          Stop, Claude Code shows the user the list, and Cursor shows nothing.
  block   after a push the agent is told to remove them now, and Stop is
          blocked until it has. A Stop that already continues an earlier block
          (stop_hook_active, or Cursor's loop_count above 0) is not blocked
          again: Claude Code shows the user the list, and Cursor shows nothing.
At every Stop at which the hook does not block, Claude Code also shows the
user the idle worktrees. They never make block mode block.

Repos are found from the payload's cwd and workspace_roots and, at Stop, from
any `.../.claude/worktrees/...` path in the transcript, so a session started
outside a repo still sees the worktrees it worked in.

Any crash exits 0, so a broken hook never blocks a session.

To see why a worktree is or is not listed, run it by hand:
  echo '{"cwd": "<repo>"}' | worktree-sweep.py --host claude --event stop
"""
import collections
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata

# A worktree another agent used this recently may still be its working tree:
# an agent can go many minutes between git commands while it waits on a
# reviewer or writes a pull request.
RECENT_SECONDS = 60 * 60
# A worktree with no git activity and no changed file modified this long is
# idle, and is shown to the user.
IDLE_SECONDS = 24 * 60 * 60
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


def git(*args, cwd=None, input=None, raw=False):
    # GIT_OPTIONAL_LOCKS=0 keeps `git status` from rewriting a worktree's
    # index, which would make it look recently used.
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    if raw:
        # Bytes, as git printed them: a path decoded or stripped could name
        # a different file, or none.
        r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, timeout=20)
        return r.returncode, r.stdout
    # errors="replace": a path or ref name in git's output can hold bytes that
    # aren't UTF-8, and one of them must not stop the whole hook.
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True,
                       errors="replace", timeout=20, input=input)
    return r.returncode, r.stdout.strip()


def config_path():
    return os.path.expanduser(os.environ.get("WORKTREES_CONFIG") or CONFIG)


def as_mode(value):
    return "block" if value.strip().lower() == "block" else "remind"


def mode():
    return mode_and_source()[0]


def mode_and_source():
    """(mode, where it comes from, in words). The hook's mode() is the first
    value, so the `mode` command reports exactly what the hook uses."""
    value = os.environ.get("WORKTREES_MODE", "").strip()
    if value:
        return as_mode(value), "from the WORKTREES_MODE environment variable" + unknown(value)
    path = config_path()
    data, problem = read_config(path)
    if problem == "missing":
        return "remind", f"the default: {path} does not exist"
    if problem:
        return "remind", (f"because {path} {problem}, and the hook uses remind when it can't "
                          f"use the file. Fix or delete it")
    value = str(data.get("mode", ""))
    if not value.strip():
        return "remind", f"the default: {path} sets no mode"
    return as_mode(value), f"from {path}" + unknown(value)


def read_config(path):
    """(the file's JSON object, None), or (None, the problem). The problem is
    "missing", or a phrase that follows the path in a message, such as "is not
    valid JSON". The hook and the `mode` command both read the file through
    this, so they can't judge it differently."""
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        return None, "missing"
    except OSError as e:
        return None, f"can't be read ({e.strerror})"
    except ValueError:  # UnicodeDecodeError included
        return None, "is not valid JSON"
    if not isinstance(data, dict):
        return None, "holds JSON that is not an object"
    return data, None


def unknown(value):
    if value.strip().lower() in ("block", "remind"):
        return ""
    return f", whose value {json.dumps(value)} isn't block or remind, so the hook uses remind"


def mode_command(args):
    """`worktree-sweep.py mode [block|remind]`: prints the mode, or sets it."""
    if not args:
        print_mode()
        return 0
    want = args[0].strip().lower()
    if len(args) > 1 or want not in ("block", "remind"):
        sys.stderr.write("Usage: worktree-sweep.py mode [block|remind]\n")
        return 2
    path = config_path()
    # When the config path is a symlink, write the file it points to:
    # os.replace on the link itself would turn it into a regular file.
    target = os.path.realpath(path)
    data, problem = read_config(target)
    if problem == "missing":
        data, perms = {}, None
    elif problem:
        return refuse(path, problem)
    else:
        try:
            perms = stat.S_IMODE(os.stat(target).st_mode)
        except OSError as e:
            return refuse(path, f"can't be read ({e.strerror})")
    data["mode"] = want
    if perms is None:
        umask = os.umask(0)
        os.umask(umask)
        perms = 0o666 & ~umask
    tmp = None
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target),
                                   prefix=f".{os.path.basename(target)}.")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, perms)
        os.replace(tmp, target)
    except OSError as e:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
        sys.stderr.write(f"Could not write {path}: {e.strerror or e}\n")
        return 1
    print(f"Wrote mode {want} to {path}.")
    active = print_mode()
    env = os.environ.get("WORKTREES_MODE", "").strip()
    if env:
        print(f"WORKTREES_MODE is set to {json.dumps(env)} and overrides the file, so the hook "
              f"uses {active}. For the file to count, unset WORKTREES_MODE in the environment "
              f"the agent is started from, then restart the agent.")
    return 0


def check_command(args):
    """`worktree-sweep.py check <worktree>`: says whether removing a linked
    worktree is safe, by the same judgement the hook uses, and if not, why.
    Exits 0 when safe, 1 when not, 2 when it can't tell. It doesn't look for
    running processes."""
    if len(args) != 1:
        sys.stderr.write("Usage: worktree-sweep.py check <worktree>\n")
        return 2
    path = os.path.abspath(args[0])
    common = common_dir(path)
    main, linked = worktrees(common) if common else (None, [])
    me = identity(path)
    wt = next((w for w in linked if me and identity(w.get("path") or "") == me), None)
    if wt is None:
        sys.stderr.write(f"{path} is not a linked worktree.\n")
        return 2
    if wt.get("prunable") or not has_own_git(wt["path"]):
        print("Can't tell: the worktree has no git directory of its own.")
        return 2
    others = [w["path"] for w in linked if w.get("path")]
    j = judge(wt["path"], peers_of(wt["path"], main or common, others))
    if j is None:
        print("Can't tell: git couldn't read the worktree.")
        return 2
    reasons = []
    if j.changed:
        reasons.append(f"{len(j.changed)} changed or untracked file(s)")
    if j.hidden:
        reasons.append(f"{len(j.hidden)} skip-worktree or assume-unchanged file(s) that "
                       f"differ: {', '.join(j.hidden)}")
    if j.lost is None:
        reasons.append("can't tell which commits removal would lose")
    elif j.lost:
        reasons.append(f"{j.lost} commit(s) removal would lose")
    if j.submodules:
        reasons.append("submodules, which git worktree remove refuses")
    if j.nested:
        reasons.append("another worktree inside it, which removal would delete")
    if reasons:
        print("Not safe to remove: " + "; ".join(reasons) + ".")
        return 1
    print("Safe to remove: clean, no hidden edits, no commit only it holds, no submodules, "
          "no worktree inside it.")
    return 0


def print_mode():
    active, source = mode_and_source()
    print(f"Worktrees mode: {active}, {source}.")
    return active


def refuse(path, why):
    sys.stderr.write(f"{path} {why}, so it was left as it is. Fix or delete it, then run "
                     f"this again.\n")
    return 1


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
    """When git last did something in the worktree, or None if unknown: the
    newest of its HEAD's and index's times and of the newest entry in its
    HEAD reflog, and the same for each of its submodules' repositories.
    `git gc` rewrites every reflog file and its directory, but leaves those
    times and each entry's own timestamp as they were."""
    gitdir = git_dir_of(worktree)
    if not gitdir:
        return None
    times = []
    for root, dirs, files in os.walk(gitdir):
        if "HEAD" not in files:
            # Not a repository but a directory on the way to one, such as
            # modules/a above modules/a/b, the repository of a submodule at
            # a/b. Its subdirectories are walked to reach that repository.
            continue
        # Into submodules' repositories only, not objects or refs.
        dirs[:] = [d for d in dirs if d == "modules"]
        for name in ("HEAD", "index"):
            try:
                times.append(os.stat(os.path.join(root, name)).st_mtime)
            except OSError:
                pass
        newest = newest_reflog_entry(os.path.join(root, "logs", "HEAD"))
        if newest is not None:
            times.append(newest)
    return max(times) if times else None


def newest_reflog_entry(log):
    """The timestamp written in the last entry of a reflog file, or None."""
    try:
        with open(log, "rb") as f:
            f.seek(max(0, os.stat(log).st_size - 8192))
            lines = f.read().split(b"\n")
    except OSError:
        return None
    for line in reversed(lines):
        fields = line.partition(b"\t")[0].split()
        try:
            return int(fields[-2])
        except (IndexError, ValueError):
            continue
    return None


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


def safe_to_show(wt, main, others, busy):
    """May this worktree be shown at all? It needs a git directory of its
    own, names that print safely, no process inside it and no other worktree
    inside it. The inner worktree's activity is in its own git directory, so
    the outer one would look idle while the inner one is in use."""
    path, branch = wt.get("path"), wt.get("branch") or ""
    if wt.get("prunable") or not has_own_git(path):
        return False
    # A name that can't be printed safely can't be listed, and is skipped.
    if not (printable(path) and printable(branch) and printable(main)):
        return False
    me = identity(path)
    inside, trees = busy
    if me is None or me in inside or identities_up_from(path) & trees:
        return False
    return not any(me in identities_up_from(o) for o in others
                   if o != path and os.path.exists(o))


def describe_if_landed(wt, main, others, busy):
    """The listing line for a worktree whose work has landed and that is safe
    to remove, or None. Locks are the caller's to judge."""
    path, branch = wt.get("path"), wt.get("branch")
    if not branch or not safe_to_show(wt, main, others, busy):
        return None
    code, log = git("reflog", "show", "--format=%gs", "HEAD", cwd=path)
    if code != 0 or not local_work(log.split("\n")):
        return None
    code, out = git("for-each-ref", "--contains", "HEAD", "--format=%(refname:short)",
                    "refs/remotes/origin", cwd=path)
    refs = [r for r in out.split("\n") if r not in ("", "origin", "origin/HEAD")]
    if code != 0 or not refs or not safe(judge(path, peers_of(path, main, others))):
        return None
    on = f"origin/{branch}" if f"origin/{branch}" in refs else clean(refs[0])
    return f"  {path}  (branch {branch}, on {on})\n    {remove_command(wt, main)}"


def describe_if_idle(wt, main, others, busy, since):
    """The listing for a worktree with no changed file modified after `since`,
    or None. It gives the facts a person needs to decide whether to remove
    it, and the command to remove it only when it is safe to."""
    path, branch = wt.get("path"), wt.get("branch")
    if not safe_to_show(wt, main, others, busy):
        return None
    j = judge(path, peers_of(path, main, others))
    for name in (j.changed + j.hidden) if j else []:
        full = os.path.join(path, name)
        # A directory here is a nested repository or a changed submodule.
        if is_real_dir(full) and modified_under(full, since):
            return None
        # A move or a delete leaves the file's own time unchanged or gone, but
        # changes its directory's.
        for p in (full, nearest_dir(full, path)):
            try:
                if os.lstat(p).st_mtime > since:
                    return None
            except OSError:
                pass  # deleted: no time to read
    lines = [f"  {path}  ({f'branch {branch}' if branch else 'detached HEAD'})"]
    if wt.get("locked"):
        lines.append(f"    locked: {wt['locked']}")
    if j is None:
        lines.append("    state unknown: git couldn't read it")
        return "\n".join(lines)
    if j.lost is None:
        commits = "commits removal would lose: unknown"
    elif j.lost:
        commits = f"{j.lost} commit{'s' if j.lost > 1 else ''} removal would lose"
    else:
        commits = "no commit removal would lose"
    if j.hidden:
        files = f"{len(j.hidden)} file{'s' if len(j.hidden) > 1 else ''}"
        state = (f"uncommitted changes, and {files} git status doesn't check differ"
                 if j.changed else f"clean by git status, but {files} it doesn't check differ")
    else:
        state = "uncommitted changes" if j.changed else "clean"
    lines.append(f"    {state}; {commits}")
    if j.submodules:
        lines.append("    has submodules, which git worktree remove refuses")
    if safe(j):
        lines.append(f"    {remove_command(wt, main)}")
    return "\n".join(lines)


def remove_command(wt, main):
    """The command that removes the worktree, unlocking it first if locked."""
    path = wt.get("path")
    git_c = f"git -C {shlex.quote(main)} worktree"
    unlock = f"{git_c} unlock {shlex.quote(path)} && " if wt.get("locked") else ""
    return f"{unlock}{git_c} remove {shlex.quote(path)}"


Judgement = collections.namedtuple("Judgement", "changed hidden lost submodules nested")


def peers_of(path, main, others):
    """The repository's worktrees other than path, the main checkout first."""
    return [main] + [o for o in others if o != path]


def judge(path, peers):
    """What decides whether removing the worktree is safe, or None when git
    can't say: the files `git status` lists as changed, untracked included;
    the skip-worktree and assume-unchanged files that differ on disk, which
    `git status` doesn't show; how many commits removing it would lose; and
    whether it has submodules, which `git worktree remove` refuses. Peers
    are the repository's other worktrees, the main checkout among them; one
    inside this worktree would be deleted with it."""
    if not has_own_git(path):
        return None  # git would answer for the repository above it
    # -uall lists each untracked file rather than its directory, except in a
    # nested repository, which it lists as one directory ending in "/".
    code, out = git("status", "--porcelain", "-z", "--untracked-files=all", cwd=path,
                    raw=True)
    if code != 0:
        return None
    # Read as bytes, so a name that isn't UTF-8 still names its file.
    code, index = git("ls-files", "-v", "-s", "-z", cwd=path, raw=True)
    if code != 0:
        return None
    hidden, gitlinks = [], []
    for field in index.split(b"\0"):
        meta, _, name = field.partition(b"\t")
        parts = meta.decode("ascii", "replace").split(" ")
        if len(parts) != 4 or not name:
            continue
        tag, mode, sha = parts[0], parts[1], parts[2]
        full = os.path.join(os.fsencode(path), name)
        if mode == "160000":
            gitlinks.append((full, name))
        elif ((tag == "S" or tag.islower()) and os.path.lexists(full)
              and blob_id(full, len(sha)) != sha):
            hidden.append(os.fsdecode(name))
    # The test `git worktree remove` makes: a `modules` directory in the
    # worktree's own git directory, or a gitlink whose submodule is checked out.
    submodules = (os.path.isdir(os.path.join(git_dir_of(path), "modules"))
                  or any(os.path.lexists(os.path.join(g, b".git")) for g, _ in gitlinks))
    # git status never looks inside a gitlink's directory, so files put in an
    # uninitialised submodule's directory are changes it doesn't show.
    changed = changed_files(out) + [os.fsdecode(n) for g, n in gitlinks
                                    if not os.path.lexists(os.path.join(g, b".git"))
                                    and os.path.isdir(g) and holds_anything(g)]
    me = identity(path)
    nested = any(me in identities_up_from(p) for p in peers if p != path and os.path.exists(p))
    return Judgement(changed, hidden, lost_commits(path, peers), submodules, nested)


def holds_anything(directory):
    """Does this directory hold anything? One that can't be read counts as
    holding something, since what is in it is unknown."""
    try:
        return bool(os.listdir(directory))
    except OSError:
        return True


def blob_id(full, length):
    """The id git would give this file's content as a blob, hashed here
    rather than by `git hash-object --stdin-paths`, which unquotes a name
    starting with `"` as if git had quoted it, and so hashes another file.
    A symlink's content is its link text. A file git would convert,
    such as by its line endings, hashes differently and so counts as changed.
    None when the file can't be read."""
    try:
        if os.path.islink(full):
            data = os.readlink(full)
        else:
            with open(full, "rb") as f:
                data = f.read()
    except OSError:
        return None
    h = hashlib.sha256() if length == 64 else hashlib.sha1()
    h.update(b"blob %d\0" % len(data) + data)
    return h.hexdigest()


def safe(j):
    """Is removing the worktree safe: nothing lost, no other worktree deleted
    with it, and nothing that makes git refuse?"""
    return (j is not None and not j.changed and not j.hidden and j.lost == 0
            and not j.submodules and not j.nested)


def changed_files(status):
    """The paths `git status --porcelain -z`, read as bytes, lists as changed,
    untracked included, decoded so they name the same files. A rename or
    copy, staged or not, is followed by its old path, which is skipped."""
    names, fields, i = [], status.split(b"\0"), 0
    while i < len(fields):
        field = fields[i]
        i += 1
        if len(field) < 4:
            continue
        names.append(os.fsdecode(field[3:]))
        if b"R" in field[:2] or b"C" in field[:2]:
            i += 1
    return names


def nearest_dir(path, root):
    """The closest existing directory holding path, no higher than root."""
    parent = os.path.dirname(path)
    while len(parent) > len(root) and not os.path.isdir(parent):
        parent = os.path.dirname(parent)
    return parent if len(parent) >= len(root) else root


def is_real_dir(path):
    """Is path a directory, and not a symlink to one?"""
    try:
        return stat.S_ISDIR(os.lstat(path).st_mode)
    except OSError:
        return False


def modified_under(directory, since):
    """Was anything under this directory modified after `since`?"""
    for root, dirs, files in os.walk(directory):
        for name in dirs + files:
            try:
                if os.lstat(os.path.join(root, name)).st_mtime > since:
                    return True
            except OSError:
                pass
    return False


def lost_commits(path, peers):
    """How many commits removing the worktree would lose, or None when git
    can't say. Removal deletes only the worktree's HEAD reflog and its own
    refs (refs/worktree, refs/bisect, refs/rewritten). A commit there is
    lost unless something that stays reaches it: any branch, tag or remote
    ref, any branch's reflog, the main checkout's HEAD and its reflog, or
    another worktree's HEAD and its reflog. So an amended or rebased commit
    is kept by its branch's reflog, and a commit left behind on a detached
    HEAD is lost."""
    code, common = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=path)
    if code != 0:
        return None
    code, head = git("rev-parse", "-q", "--verify", "HEAD", cwd=path)
    if code == 0:
        code, out = git("reflog", "show", "--format=%H", "HEAD", cwd=path)
        if code != 0:
            return None
        lines = [head, *out.split("\n")]
    elif git("reflog", "exists", "HEAD", cwd=path)[0] == 0:
        # HEAD is on an unborn branch, as after `git switch --orphan`, but
        # its reflog can hold commits made before; git won't list a reflog
        # whose HEAD doesn't resolve, so what removal would lose is unknown.
        return None
    else:
        lines = []  # a branch no one has committed on
    code, own = git("for-each-ref", "--format=%(objectname)", "refs/worktree/",
                    "refs/bisect/", "refs/rewritten/", cwd=path)
    if code != 0:
        return None
    lines += own.split("\n")
    lines += [f"^{sha}" for peer in peers for sha in peer_commits(peer)]
    # Run as the main checkout, whose --single-worktree view holds every ref
    # and every shared reflog but no linked worktree's HEAD reflog; the
    # other worktrees' are given as ^ lines. On stdin, since reflogs can hold
    # more commits than fit in argv.
    code, count = git("--git-dir", common, "rev-list", "--count", "--stdin", "--not",
                      "--single-worktree", "--all", "--reflog",
                      input="\n".join(x for x in lines if x) + "\n")
    return int(count) if code == 0 and count.isdigit() else None


PEER_COMMITS = {}


def peer_commits(peer):
    """The commits another worktree's HEAD and HEAD reflog hold, read once
    per run. None of them is lost when a different worktree is removed."""
    if peer not in PEER_COMMITS and not os.path.isdir(peer):
        PEER_COMMITS[peer] = []  # its directory is gone; count as keeping nothing
    if peer not in PEER_COMMITS:
        code, out = git("reflog", "show", "--format=%H", "HEAD", cwd=peer)
        _, head = git("rev-parse", "-q", "--verify", "HEAD", cwd=peer)
        PEER_COMMITS[peer] = [s for s in (out.split("\n") if code == 0 else []) + [head] if s]
    return PEER_COMMITS[peer]


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
    """At Stop: (worktrees for the agent to remove, idle ones to show the
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
    found, idle_ones = [], []
    for c in commons:
        main, linked = worktrees(c)
        others = [wt["path"] for wt in linked if wt.get("path")]
        for wt in linked:
            path = wt.get("path") or ""
            # Read before any git command runs in the worktree.
            used = last_used(path)
            idle = now - used if used is not None else None
            mine = identity(path) in own
            if (not wt.get("locked") and (mine or (idle is not None and idle >= RECENT_SECONDS))
                    and (hit := describe_if_landed(wt, main or c, others, busy))):
                found.append(hit)
                continue
            # An idle tree is shown to the user only, never to the agent, which
            # can't tell an abandoned tree from one someone is about to use.
            # The session's own tree is in use, so it is never shown.
            if (not mine and idle is not None and idle > IDLE_SECONDS
                    and (hit := describe_if_idle(wt, main or c, others, busy,
                                                 now - IDLE_SECONDS))):
                idle_ones.append(hit)
    return found, idle_ones


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


def user_message(found, idle):
    parts = []
    if found:
        parts.append("Worktrees whose work has landed are still present:\n" + "\n".join(found))
    if idle:
        parts.append(
            "Worktrees idle for over a day: no git activity, and no changed file edited. "
            "Whoever was using one may be gone. A remove command is shown only where "
            "removing it loses nothing:\n" + "\n".join(idle))
    return "\n\n".join(parts)


def report(found, idle, event, mode_, host, payload):
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
    if found or idle:
        return json.dumps({"systemMessage": user_message(found, idle)}), "", 0
    return "", "", 0


def main():
    host = host_of()
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        return 0
    event = event_of(payload) or "stop"
    if event == "push":
        found, idle = find_pushed(payload), []
    else:
        found, idle = find_landed(payload)
    out, err, code = report(found, idle, event, mode(), host, payload)
    if out:
        print(out)
    if err:
        sys.stderr.write(err)
    return code


if __name__ == "__main__":
    # manage-skills wires the hook as `<script> --host <host>`, so a hook run
    # never takes this branch.
    if sys.argv[1:2] == ["mode"]:
        sys.exit(mode_command(sys.argv[2:]))
    if sys.argv[1:2] == ["check"]:
        sys.exit(check_command(sys.argv[2:]))
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)

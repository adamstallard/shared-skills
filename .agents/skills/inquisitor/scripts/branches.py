"""Reading and writing a repository's `questions` branch with git's plumbing,
never a checkout, so no HEAD moves; and keeping pending the files the script
could not push (inquisitor spec: *A question is pushed to the questions
branch of what it concerns*; *A file the script cannot push stays
pending*).

Owned by P2. Standard library only.
"""

import datetime
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from common import state_home
from config import origin_repository
from formats import Unreadable, is_repository, parse
from private_files import write_private

BRANCH = "questions"


@dataclass(frozen=True)
class BranchFile:
    """A file on a questions branch: its path, its text, the commit that
    added it, and whether a later commit changed it (modified it, or
    deleted and added it again). list_files gives them oldest first."""

    path: str
    content: str
    added_by: str
    changed: bool = False


@dataclass(frozen=True)
class PushResult:
    """pushed: the commit landed. pending: kept to push with the next file
    for that branch; never set when the service option was given. taken: a miss file's
    name was on the branch, so nothing was pushed. why: the failure, when
    neither pushed nor taken."""

    pushed: bool
    pending: bool = False
    taken: bool = False
    why: str | None = None


_REPOSITORY_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE")


def _clean_env() -> dict[str, str]:
    """The environment without the variables that point git at a
    repository. git sets them while it runs a hook or a `rebase -x`
    command; a script started from one would otherwise act on the
    repository git is running in, not on the clone it was given."""
    return {k: v for k, v in os.environ.items() if k not in _REPOSITORY_VARS}


def _git(clone: Path, *args: str, env: dict[str, str] | None = None,
         stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    """Run git in clone, with no pager or prompt, and none of the
    caller's repository variables. When clone is a bare repository (no
    .git, but objects/ and HEAD), as the cache is, GIT_DIR names it: a
    person's safe.bareRepository=explicit refuses `git -C` into one."""
    full_env = {**_clean_env(), "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", **(env or {})}
    if not (clone / ".git").exists() and (clone / "objects").is_dir() and (clone / "HEAD").is_file():
        full_env["GIT_DIR"] = str(clone)
    try:
        return subprocess.run(["git", "-C", str(clone), *args], input=stdin, capture_output=True,
                              env=full_env, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(["git", *args], 127, b"", str(e).encode())


def _ref(repository: str) -> str:
    """Where the clone keeps the fetched questions branch of repository: a
    ref of the script's own, so no branch, HEAD or working tree moves."""
    return f"refs/inquisitor/{repository}/{BRANCH}"


def remote_url(clone: Path, repository: str) -> str:
    """The URL to reach repository by: SSH when the clone's origin is SSH,
    else HTTPS, so the person's existing git credentials serve."""
    origin = _git(clone, "remote", "get-url", "origin").stdout.decode(errors="replace").strip()
    if origin.startswith("git@github.com:") or origin.startswith("ssh://git@github.com/"):
        return f"git@github.com:{repository}.git"
    return f"https://github.com/{repository}.git"


_Tip = Literal["ok", "missing", "failed"]


def _fetch_tip(clone: Path, repository: str) -> tuple[_Tip, str | None]:
    """Fetch the questions branch into _ref(repository): ("ok", its
    commit), ("missing", None) when the repository has no such branch (the
    local ref is then removed), or ("failed", None)."""
    if not is_repository(repository):
        return "failed", None
    url = remote_url(clone, repository)
    listed = _git(clone, "ls-remote", "--heads", url, f"refs/heads/{BRANCH}")
    if listed.returncode != 0:
        return "failed", None
    line = listed.stdout.decode(errors="replace").split("\n")[0].split("\t")
    if len(line) < 2 or not re.fullmatch(r"[0-9a-f]{40}", line[0]):
        _git(clone, "update-ref", "-d", _ref(repository))
        return "missing", None
    done = _git(clone, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", url,
                f"+refs/heads/{BRANCH}:{_ref(repository)}")
    if done.returncode != 0:
        return "failed", None
    return "ok", _git(clone, "rev-parse", _ref(repository)).stdout.decode().strip()


def cache_dir(repository: str) -> Path:
    """The path of the bare repository that holds repository's questions
    branch for a command run from no checkout of that repository:
    state_home()/inquisitor/branches/<owner>/<repo>. fetch creates it."""
    return state_home() / "inquisitor" / "branches" / repository


def fetch(clone: Path, repository: str) -> bool:
    """Fetch the repository's questions branch into clone, under a ref of
    the script's own; False when it cannot. Where clone does not exist,
    as for the path cache_dir gives, fetch first creates it as a bare
    repository. When the repository has no questions branch, fetch
    succeeds and list_files then finds no files."""
    if not is_repository(repository):
        return False
    if not clone.exists():
        clone.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        made = subprocess.run(["git", "init", "--quiet", "--bare", "--object-format=sha1",
                               str(clone)],
                              capture_output=True, check=False, env=_clean_env())
        if made.returncode != 0:
            return False
    return _fetch_tip(clone, repository)[0] != "failed"


def _tree(clone: Path, ref: str) -> dict[str, str] | None:
    """Every file at ref, path to blob id; None when ref cannot be read."""
    done = _git(clone, "ls-tree", "-r", "-z", "--full-tree", ref)
    if done.returncode != 0:
        return None
    files: dict[str, str] = {}
    for entry in done.stdout.split(b"\0"):
        if not entry:
            continue
        meta, _, path = entry.partition(b"\t")
        parts = meta.split(b" ")
        if len(parts) == 3 and parts[1] == b"blob":
            files[path.decode("utf-8", errors="surrogateescape")] = parts[2].decode()
    return files


def _blobs(clone: Path, ids: list[str]) -> list[bytes] | None:
    """The contents of the blobs, in order, read with one cat-file."""
    if not ids:
        return []
    done = _git(clone, "cat-file", "--batch", stdin=("\n".join(ids) + "\n").encode())
    if done.returncode != 0:
        return None
    out, pos, found = done.stdout, 0, list[bytes]()
    for _ in ids:
        end = out.index(b"\n", pos)
        header = out[pos:end].split(b" ")
        if len(header) != 3:
            return None
        size = int(header[2])
        found.append(out[end + 1:end + 1 + size])
        pos = end + 1 + size + 1
    return found


_MARK = "\x01inquisitor-commit:"


def list_files(clone: Path, repository: str | None = None) -> list[BranchFile] | None:
    """Every file on the fetched questions branch of repository (the
    clone's origin when None), read from git's objects, in the order of the
    commits that added them, or None when the branch cannot be read. A
    repository with no questions branch has no files. Content that is not
    UTF-8 is decoded with replacement characters; no questions-branch
    format allows them, so parse() reads such a file as Unreadable."""
    repository = repository or origin_repository(clone)
    if repository is None or not is_repository(repository):
        return None
    ref = _ref(repository)
    if _git(clone, "rev-parse", "--verify", "--quiet", ref).returncode != 0:
        return []
    files = _tree(clone, ref)
    log = _git(clone, "log", "--root", "--no-show-signature", "--reverse",
               f"--format={_MARK}%H", "--name-status", "-z", "--no-renames",
               "--no-relative", "--encoding=UTF-8", "--first-parent", ref)
    if files is None or log.returncode != 0:
        return None
    added: dict[str, str] = {}
    changed: set[str] = set()
    commit, status = "", None
    for token in log.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        if status is None:
            # A status, or the next commit's mark; git puts a newline
            # between a commit's mark and its first status.
            token = token.removeprefix("\n")
            if token.startswith(_MARK) and re.fullmatch(r"[0-9a-f]{40}", token[len(_MARK):]):
                commit = token[len(_MARK):]
            elif token:
                status = token
        else:
            if token in added:
                changed.add(token)
            elif status == "A" and token in files:
                added[token] = commit
            status = None
    contents = _blobs(clone, [files[p] for p in added])
    if contents is None:
        return None
    return [BranchFile(path=p, content=c.decode("utf-8", errors="replace"), added_by=commit,
                       changed=p in changed)
            for (p, commit), c in zip(added.items(), contents)]


# -- pending files ------------------------------------------------------------

def pending_dir(repository: str) -> Path:
    """Where files waiting to be pushed to repository's questions branch are
    kept, each at its path on the branch (inquisitor spec: *A file the
    script cannot push stays pending*)."""
    return state_home() / "inquisitor" / "pending" / repository


def _pending(repository: str) -> list[tuple[str, str]]:
    root = pending_dir(repository)
    if not root.is_dir():
        return []
    found: list[tuple[float, str, str]] = []
    for f in root.rglob("*"):
        if f.name.startswith(".tmp-"):
            continue
        try:  # another process may push and drop the file meanwhile
            if f.is_file():
                found.append((f.stat().st_mtime, f.relative_to(root).as_posix(),
                              f.read_text(encoding="utf-8")))
        except FileNotFoundError:
            continue
    return [(path, content) for _, path, content in sorted(found)]


def _keep_pending(repository: str, path: str, content: str) -> None:
    write_private(pending_dir(repository) / path, content)


def _drop_pending(repository: str, path: str) -> None:
    (pending_dir(repository) / path).unlink(missing_ok=True)


# -- pushing -------------------------------------------------------------------

def _inquisitor_env(now: datetime.datetime) -> dict[str, str]:
    midnight = datetime.datetime(now.year, now.month, now.day, tzinfo=datetime.timezone.utc)
    stamp = f"{int(midnight.timestamp())} +0000"
    return {"GIT_AUTHOR_NAME": "inquisitor", "GIT_AUTHOR_EMAIL": "noreply",
            "GIT_COMMITTER_NAME": "inquisitor", "GIT_COMMITTER_EMAIL": "noreply",
            "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}


def _commit(clone: Path, parent: str | None, base: dict[str, str], path: str, content: str,
            message: str, as_inquisitor: bool, index: Path) -> tuple[str, dict[str, str]] | None:
    """One commit adding path on top of parent, built in a private index
    file: its id and its tree's files, or None on failure."""
    blob = _git(clone, "hash-object", "-w", "--stdin", stdin=content.encode("utf-8"))
    if blob.returncode != 0:
        return None
    blob_id = blob.stdout.decode().strip()
    env = {"GIT_INDEX_FILE": str(index)}
    if parent is None:
        reset = _git(clone, "read-tree", "--empty", env=env)
    else:
        reset = _git(clone, "read-tree", parent, env=env)
    if reset.returncode != 0:
        return None
    entry = f"100644 {blob_id}\t{path}\0".encode("utf-8")
    added = _git(clone, "update-index", "--add", "-z", "--index-info", env=env, stdin=entry)
    tree = _git(clone, "write-tree", env=env)
    if added.returncode != 0 or tree.returncode != 0:
        return None
    args = ["commit-tree", tree.stdout.decode().strip(), "-m", message]
    if parent is not None:
        args += ["-p", parent]
    commit_env = dict(env)
    if as_inquisitor:
        args.append("--no-gpg-sign")
        commit_env.update(_inquisitor_env(datetime.datetime.now(datetime.timezone.utc)))
    made = _git(clone, *args, env=commit_env)
    if made.returncode != 0:
        return None
    return made.stdout.decode().strip(), {**base, path: blob_id}


def _as_inquisitor(path: str, content: str) -> bool:
    """Whether a pending file is committed as `inquisitor <noreply>`: a
    citation, or a hash-only miss file."""
    return path.startswith("citations/") or (path.startswith("misses/") and content == "---\n---\n")


_REJECTED_MOVED = ("non-fast-forward", "fetch first", "[rejected]", "stale info")
ATTEMPTS = 5


def push_file(clone: Path, repository: str, path: str, content: str,
              message: str, as_inquisitor: bool, service: bool) -> PushResult:
    """Commit one file onto the branch with hash-object, a private index
    and commit-tree, and push it by commit id, fetching and retrying when
    the branch moved. as_inquisitor commits as `inquisitor <noreply>`
    dated midnight UTC of the day it pushes, so the commit shows no time of
    day (citations and hash-only miss files). A file that parse() reads
    as unreadable is never pushed or kept. When the file's name is already
    on the branch, nothing is pushed, not even pending files.

    Without service, files kept pending for that branch are committed
    first, each with the message `inquisitor: log <path>`, and leave
    pending once pushed. When the push fails, the new file is kept pending
    beside them, unless it is a miss file whose name the last fetch saw on
    the branch. With service, nothing is kept pending. No branch, HEAD,
    index or working tree of the clone moves, and no hook runs."""
    if not is_repository(repository):
        return PushResult(pushed=False, why=f"{repository!r} is not in the form owner/repo")
    if isinstance(parse(path, content, True), Unreadable):
        return PushResult(pushed=False, why=f"{path!r} does not read as a questions-branch file")
    queue = [] if service else [(p, c, f"inquisitor: log {p}", _as_inquisitor(p, c))
                                for p, c in _pending(repository) if p != path]
    queue.append((path, content, message, as_inquisitor))
    why = "the branch kept moving"
    with tempfile.TemporaryDirectory() as tmp:
        index = Path(tmp) / "index"
        for _ in range(ATTEMPTS):
            state, tip = _fetch_tip(clone, repository)
            if state == "failed":
                why = f"cannot fetch the {BRANCH} branch of {repository}"
                break
            base = _tree(clone, _ref(repository)) if tip else {}
            if base is None:
                why = f"cannot read the {BRANCH} branch of {repository}"
                break
            if path in base:
                return PushResult(pushed=False, taken=True)
            head, done_paths, failed = tip, list[str](), False
            for p, c, msg, quiet in queue:
                if p in base:
                    done_paths.append(p)
                    continue
                made = _commit(clone, head, base, p, c, msg, quiet, index)
                if made is None:
                    failed = True
                    break
                head, base = made
                done_paths.append(p)
            if failed:
                why = "git could not build the commit"
                break
            assert head is not None  # path was not in base, so it was committed
            pushed = _git(clone, "push", "--quiet", "--no-verify", remote_url(clone, repository),
                          f"{head}:refs/heads/{BRANCH}")
            if pushed.returncode == 0:
                for p in done_paths:
                    _drop_pending(repository, p)
                return PushResult(pushed=True)
            err = pushed.stderr.decode(errors="replace")
            if not any(sign in err for sign in _REJECTED_MOVED):
                why = err.strip().splitlines()[-1] if err.strip() else "git push failed"
                break
    if not service and not (path.startswith("misses/") and _known_taken(clone, repository, path)):
        _keep_pending(repository, path, content)
        return PushResult(pushed=False, pending=True, why=why)
    return PushResult(pushed=False, why=why)


def _known_taken(clone: Path, repository: str, path: str) -> bool:
    files = _tree(clone, _ref(repository))
    return files is not None and path in files


def landed(clone: Path, commit: str) -> bool | None:
    """Whether commit is on the clone's remote-tracking default branch
    (`origin/HEAD`), None when it cannot tell, as when the commit is not in
    the clone or origin/HEAD is unset."""
    head = _git(clone, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    if head.returncode != 0 or not re.fullmatch(r"[0-9a-fA-F]{4,40}", commit):
        return None
    if _git(clone, "cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
        return None
    done = _git(clone, "merge-base", "--is-ancestor", commit, head.stdout.decode().strip())
    if done.returncode == 0:
        return True
    if done.returncode == 1:
        return False
    return None

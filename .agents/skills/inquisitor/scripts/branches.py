"""Reading and writing a repository's `questions` branch through GitHub's
API with gh's authentication, keeping no clone or copy of it; and keeping
pending the files the inquisitor's commands could not push (inquisitor spec: *A questions
branch is read through GitHub's API*; *A question is pushed to the
questions branch of what it concerns*; *A file the script cannot push stays
pending*).

A read takes one GraphQL call for the branch's head and its commits, one
REST call for its tree, and one GraphQL call per 50 files for their
contents and each file's commits. It takes more calls only for a branch
of over 100 commits (one per further 100), a file touched by over 100
commits, or a blob GraphQL gives no text (one REST call each).

Owned by build part P2 of the implementation plan. Standard library only.
"""

import base64
import datetime
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from common import state_home
from formats import Unreadable, is_repository, parse
from private_files import write_private

BRANCH = "questions"
BATCH = 50
ATTEMPTS = 5


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
    for that branch; never set when the service option was given. taken: the
    file's path was on the branch, so nothing was pushed. why: the failure,
    when neither pushed nor taken."""

    pushed: bool
    pending: bool = False
    taken: bool = False
    why: str | None = None


# -- gh ------------------------------------------------------------------------

def run_gh(args: list[str], stdin: str | None = None) -> tuple[int, str, str]:
    """Run `gh` with args and stdin; its exit code, stdout and stderr. A gh
    that cannot start, or runs over 60 seconds, gives exit 127. Tests replace this function."""
    try:
        done = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True,
                              timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return 127, "", str(e)
    return done.returncode, done.stdout, done.stderr


def _api(args: list[str], payload: dict[str, Any] | None = None) -> tuple[Any, str]:
    """`gh api <args>`, sending payload as the JSON body: the parsed answer
    and "", or None and gh's error. A GraphQL answer holding `errors` fails
    through gh's exit code, which gh sets non-zero for it; the body is not
    checked."""
    if payload is not None:
        args = [*args, "--input", "-"]
    code, out, err = run_gh(["api", *args], json.dumps(payload) if payload is not None else None)
    if code != 0:
        return None, err.strip() or f"gh exited {code}"
    try:
        return json.loads(out), ""
    except json.JSONDecodeError:
        return None, "gh's answer is not JSON"


def _get(obj: Any, *keys: str) -> Any:
    """obj[keys[0]][keys[1]]..., or None where a level is not an object."""
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = cast(dict[str, Any], obj).get(key)
    return obj


def _graphql(repository: str, query: str, variables: dict[str, str]) -> Any:
    """The `repository` object in the answer to a GraphQL query about
    repository, or None when the query fails or the repository cannot be
    read."""
    owner, name = repository.split("/")
    data, _ = _api(["graphql"], {"query": query,
                                 "variables": {"owner": owner, "name": name, **variables}})
    return _get(data, "data", "repository")


# -- reading ---------------------------------------------------------------------

_HISTORY = "history(first: 100{after}) {{ pageInfo {{ hasNextPage endCursor }} nodes {{ oid }} }}"

_HEAD_QUERY = ("query($owner: String!, $name: String!, $ref: String!) {"
               " repository(owner: $owner, name: $name) { ref(qualifiedName: $ref) {"
               " target { ... on Commit { oid tree { oid } "
               + _HISTORY.format(after="") + " } } } } }")

_MORE_QUERY = ("query($owner: String!, $name: String!, $head: GitObjectID!, $after: String!) {"
               " repository(owner: $owner, name: $name) { object(oid: $head) { ... on Commit { "
               + _HISTORY.format(after=", after: $after") + " } } } }")


@dataclass(frozen=True)
class _Head:
    """The branch's head commit, its tree, and its commits, newest first."""

    commit: str
    tree: str
    commits: list[str]


_State = Literal["ok", "missing", "failed"]


def _nodes(history: Any) -> list[str] | None:
    nodes = _get(history, "nodes")
    if not isinstance(nodes, list):
        return None
    oids = [_get(n, "oid") for n in cast(list[Any], nodes)]
    return [o for o in oids if isinstance(o, str)] if all(isinstance(o, str) for o in oids) else None


def _head(repository: str, all_commits: bool) -> tuple[_State, _Head | None]:
    """The branch's head: ("ok", head), ("missing", None) when the
    repository has no questions branch, or ("failed", None). all_commits:
    read every commit, not only the newest 100."""
    found = _graphql(repository, _HEAD_QUERY, {"ref": f"refs/heads/{BRANCH}"})
    if not isinstance(found, dict):
        return "failed", None
    ref = _get(found, "ref")
    if ref is None:
        return "missing", None
    target = _get(ref, "target")
    commit, tree = _get(target, "oid"), _get(target, "tree", "oid")
    history = _get(target, "history")
    commits = _nodes(history)
    if not isinstance(commit, str) or not isinstance(tree, str) or commits is None:
        return "failed", None
    while all_commits and _get(history, "pageInfo", "hasNextPage") is True:
        after = _get(history, "pageInfo", "endCursor")
        if not isinstance(after, str):
            return "failed", None
        more = _graphql(repository, _MORE_QUERY, {"head": commit, "after": after})
        history = _get(more, "object", "history")
        page = _nodes(history)
        if page is None:
            return "failed", None
        commits += page
    return "ok", _Head(commit, tree, commits)


def _tree(repository: str, tree: str) -> dict[str, str] | None:
    """Every file in tree, path to blob id; None when it cannot be read
    whole."""
    found, _ = _api([f"repos/{repository}/git/trees/{tree}?recursive=1"])
    entries = _get(found, "tree")
    if not isinstance(entries, list) or _get(found, "truncated") is not False:
        return None
    files: dict[str, str] = {}
    for e in cast(list[Any], entries):
        path, kind, sha = _get(e, "path"), _get(e, "type"), _get(e, "sha")
        if kind == "blob" and isinstance(path, str) and isinstance(sha, str):
            files[path] = sha
    return files


def _files_query(count: int) -> str:
    params = "".join(f", $p{i}: String!, $b{i}: GitObjectID!" for i in range(count))
    history = " ".join(f"h{i}: history(path: $p{i}, first: 100) {{ totalCount"
                       f" pageInfo {{ hasNextPage endCursor }} nodes {{ oid }} }}"
                       for i in range(count))
    blobs = " ".join(f"b{i}: object(oid: $b{i}) {{ ... on Blob {{ text isTruncated }} }}"
                     for i in range(count))
    return (f"query($owner: String!, $name: String!, $head: GitObjectID!{params}) {{"
            f" repository(owner: $owner, name: $name) {{"
            f" object(oid: $head) {{ ... on Commit {{ {history} }} }} {blobs} }} }}")


_PATH_QUERY = ("query($owner: String!, $name: String!, $head: GitObjectID!, $path: String!,"
               " $after: String!) { repository(owner: $owner, name: $name) {"
               " object(oid: $head) { ... on Commit { history(path: $path, first: 100,"
               " after: $after) { pageInfo { hasNextPage endCursor } nodes { oid } } } } } }")


def _first_commit(repository: str, head: str, path: str, history: Any) -> str | None:
    """The oldest commit touching path. history is the first page of the
    path's commits; later pages are read until the last. None when a page
    cannot be read."""
    oldest = None
    while True:
        page = _nodes(history)
        if page is None:
            return None
        if not page:
            return oldest
        oldest = page[-1]
        if _get(history, "pageInfo", "hasNextPage") is not True:
            return oldest
        after = _get(history, "pageInfo", "endCursor")
        if not isinstance(after, str):
            return None
        found = _graphql(repository, _PATH_QUERY, {"head": head, "path": path, "after": after})
        history = _get(found, "object", "history")


def _blob(repository: str, sha: str) -> str | None:
    """A blob's text read through REST, used when GraphQL gives the blob no
    text because it is not UTF-8 or too large; None when the answer holds
    no base64 content. Bytes that are not UTF-8 decode as replacement
    characters, which no questions-branch format allows, so parse() reads
    such a file as Unreadable."""
    found, _ = _api([f"repos/{repository}/git/blobs/{sha}"])
    content = _get(found, "content")
    if not isinstance(content, str) or _get(found, "encoding") != "base64":
        return None
    try:
        return base64.b64decode(content).decode("utf-8", errors="replace")
    except ValueError:
        return None


def _read(repository: str, head: _Head, files: dict[str, str]) -> list[BranchFile] | None:
    """Each file's text, the commit that added it and whether a later one
    changed it, oldest first by the commit that added it and by path within
    one commit; None when any call fails or an answer lacks a field."""
    position = {c: i for i, c in enumerate(reversed(head.commits))}
    paths = sorted(files)
    out: list[tuple[int, str, BranchFile]] = []
    for start in range(0, len(paths), BATCH):
        batch = paths[start:start + BATCH]
        variables = {"head": head.commit}
        for i, p in enumerate(batch):
            variables[f"p{i}"], variables[f"b{i}"] = p, files[p]
        found = _graphql(repository, _files_query(len(batch)), variables)
        if not isinstance(found, dict):
            return None
        for i, p in enumerate(batch):
            history = _get(found, "object", f"h{i}")
            commits, total = _nodes(history), _get(history, "totalCount")
            if not commits or not isinstance(total, int):
                return None
            added = _first_commit(repository, head.commit, p, history)
            text = _get(found, f"b{i}", "text")
            if not isinstance(text, str) or _get(found, f"b{i}", "isTruncated") is not False:
                text = _blob(repository, files[p])
            if added is None or text is None:
                return None
            out.append((position.get(added, len(position)), p,
                        BranchFile(path=p, content=text, added_by=added, changed=total > 1)))
    return [f for _, _, f in sorted(out, key=lambda t: (t[0], t[1]))]


def list_files(repository: str) -> list[BranchFile] | None:
    """Every file on repository's questions branch, read through GitHub's
    API, oldest first by the commit that added each (by path within one
    commit), or None when the branch cannot be read. A repository with no
    questions branch has no files."""
    if not is_repository(repository):
        return None
    state, head = _head(repository, all_commits=True)
    if state != "ok" or head is None:
        return [] if state == "missing" else None
    files = _tree(repository, head.tree)
    return None if files is None else _read(repository, head, files)


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

def _as_inquisitor(path: str, content: str) -> bool:
    """Whether a pending file is committed as `inquisitor <noreply>`: a
    citation, or a hash-only miss file."""
    return path.startswith("citations/") or (path.startswith("misses/") and content == "---\n---\n")


def _commit(repository: str, parent: str | None, tree: str | None, path: str, content: str,
            as_inquisitor: bool) -> tuple[str, str] | tuple[None, str]:
    """One commit adding path on top of parent (whose tree is tree): its id
    and its tree's id, or None and why it failed."""
    entry = {"path": path, "mode": "100644", "type": "blob", "content": content}
    made, err = _api(["-X", "POST", f"repos/{repository}/git/trees"],
                     {"tree": [entry], **({"base_tree": tree} if tree else {})})
    new_tree = _get(made, "sha")
    if not isinstance(new_tree, str):
        return None, err or "GitHub gave no tree"
    body: dict[str, Any] = {"message": f"inquisitor: log {path}", "tree": new_tree,
                            "parents": [parent] if parent else []}
    if as_inquisitor:
        midnight = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
        body["author"] = body["committer"] = {"name": "inquisitor", "email": "noreply",
                                              "date": midnight}
    made, err = _api(["-X", "POST", f"repos/{repository}/git/commits"], body)
    commit = _get(made, "sha")
    if not isinstance(commit, str):
        return None, err or "GitHub gave no commit"
    return commit, new_tree


# GitHub's refusals of a ref change because the branch moved: an update
# that is no fast-forward, a create where the branch now exists, and an
# update where it was deleted meanwhile.
_MOVED = ("not a fast forward", "Reference already exists", "Reference does not exist")


def push_file(repository: str, path: str, content: str, as_inquisitor: bool,
              service: bool) -> PushResult:
    """Commit one file onto the questions branch through GitHub's Git
    database API, with the message `inquisitor: log <path>`: a tree on the
    branch's head, a commit, then the branch moved forward without force,
    or created as an orphan when missing. When GitHub refuses the move
    because the branch moved, the commit is made again on the new head, up
    to ATTEMPTS times in all. as_inquisitor commits the file as
    `inquisitor <noreply>` dated midnight UTC of the day it pushes, so the
    commit shows no time of day; callers set it for citations and hash-only
    miss files. Other commits are by gh's login. A file that parse() reads
    as unreadable is never pushed or kept.

    When the file's path is already on the branch, nothing is pushed, not
    even pending files. No commit ever adds a path the branch holds.

    Without service, files kept pending for that branch are committed
    first, one commit each, as `inquisitor <noreply>` when the path shows a
    citation or hash-only miss file. A pending file already on the branch
    is skipped. Each leaves pending once the push lands. When the push
    fails, the new file is kept pending beside them. With service, pending
    files are neither pushed nor added to."""
    if not is_repository(repository):
        return PushResult(pushed=False, why=f"{repository!r} is not in the form owner/repo")
    if isinstance(parse(path, content, True), Unreadable):
        return PushResult(pushed=False, why=f"{path!r} does not read as a questions-branch file")
    queue = [] if service else [(p, c, _as_inquisitor(p, c))
                                for p, c in _pending(repository) if p != path]
    queue.append((path, content, as_inquisitor))
    why = "the branch kept moving"
    for _ in range(ATTEMPTS):
        state, head = _head(repository, all_commits=False)
        if state == "failed":
            why = f"cannot read the {BRANCH} branch of {repository}"
            break
        held = _tree(repository, head.tree) if head else {}
        if held is None:
            why = f"cannot read the {BRANCH} branch of {repository}"
            break
        seen = set(held)
        if path in seen:
            return PushResult(pushed=False, taken=True)
        parent, tree = (head.commit, head.tree) if head else (None, None)
        done: list[str] = []
        failed: str | None = None
        for p, c, quiet in queue:
            if p not in seen:
                commit, made = _commit(repository, parent, tree, p, c, quiet)
                if commit is None:
                    failed = made
                    break
                parent, tree = commit, made
            done.append(p)
        if failed is not None:
            why = failed
            break
        if head is None:
            _, err = _api(["-X", "POST", f"repos/{repository}/git/refs"],
                          {"ref": f"refs/heads/{BRANCH}", "sha": parent})
        else:
            _, err = _api(["-X", "PATCH", f"repos/{repository}/git/refs/heads/{BRANCH}"],
                          {"sha": parent, "force": False})
        if not err:
            for p in done:
                _drop_pending(repository, p)
            return PushResult(pushed=True)
        why = err
        if not any(sign in err for sign in _MOVED):
            break
    if not service:
        _keep_pending(repository, path, content)
        return PushResult(pushed=False, pending=True, why=why)
    return PushResult(pushed=False, why=why)

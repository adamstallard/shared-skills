"""Reading and writing a repository's `questions` branch with git's plumbing,
never a checkout, so no HEAD moves; and keeping pending the files the script
could not push (inquisitor spec: *A question is pushed to the questions
branch of what it concerns*; *A file the script cannot push stays
pending*).

Owned by P2. Standard library only.
"""

from dataclasses import dataclass
from pathlib import Path

from common import NotBuilt

BRANCH = "questions"


@dataclass(frozen=True)
class BranchFile:
    """A file on a questions branch: its path, its text, and the commit that
    added it. list_files gives them oldest first."""

    path: str
    content: str
    added_by: str


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


def fetch(clone: Path, repository: str) -> bool:
    """Fetch the repository's questions branch into clone; False when it
    cannot. TODO(P2): build it."""
    raise NotBuilt("P2", "branches.fetch")


def list_files(clone: Path) -> list[BranchFile] | None:
    """Every file on the fetched branch, read with `git show`, in the order
    of the commits that added them, or None when the branch cannot be read.
    TODO(P2): build it."""
    raise NotBuilt("P2", "branches.list_files")


def push_file(clone: Path, repository: str, path: str, content: str,
              message: str, as_inquisitor: bool, service: bool) -> PushResult:
    """Commit one file onto the branch with hash-object, mktree and
    commit-tree, and push it by commit id, fetching and retrying when the
    branch moved. as_inquisitor commits as `inquisitor <noreply>` dated
    midnight UTC of the day it pushes, so the commit shows no time of day
    (citations and hash-only miss files). Pushes nothing where
    a miss file's name is taken, and with service set keeps nothing
    pending. TODO(P2): build it."""
    raise NotBuilt("P2", "branches.push_file")


def landed(clone: Path, commit: str) -> bool | None:
    """Whether commit is on the repository's default branch, None when it
    cannot tell. TODO(P2): build it."""
    raise NotBuilt("P2", "branches.landed")

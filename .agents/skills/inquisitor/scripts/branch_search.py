"""The questions-branch commands an Igor, an AI teammate of the igor
project, runs for the worker it started on an item: `branch-search`,
`miss-check` and `file-answer`. Their JSON is a contract with igor (tasks
2.3b to 2.3d): a test compares each command's output field for field with
its stored copy in fixtures/json/.

Owned by P4. Standard library only.
"""

from dataclasses import dataclass
from typing import Literal

from common import NotBuilt


@dataclass(frozen=True)
class BranchSearchArgs:
    """repository: the questions branch's repository. item: the repository
    of the item an Igor's run works on; given, the search applies that run's
    rules. linear: the item is a Linear issue, so it counts as private. The
    question comes on standard input."""

    repository: str
    item: str | None = None
    linear: bool = False


@dataclass(frozen=True)
class MissCheckArgs:
    repository: str
    surface: Literal["github", "linear", "discord"]
    id: str


@dataclass(frozen=True)
class FileAnswerArgs:
    """date and suffix: a questions-branch file name's `yyyy-mm-dd` and 6
    lowercase hex digits."""

    repository: str
    date: str
    suffix: str


def run_branch_search(args: BranchSearchArgs) -> int:
    """Print a contracts.BranchSearchResult; print nothing and exit 1 when
    the branch cannot be fetched.

    TODO(P4): build it (task 2.3b)."""
    raise NotBuilt("P4", "branch-search")


def run_miss_check(args: MissCheckArgs) -> int:
    """Print a contracts.MissCheckResult without asking GitHub anyone's
    permission (github.write_access), since only someone with write access
    could have pushed a file to the branch.

    TODO(P4): build it (task 2.3c)."""
    raise NotBuilt("P4", "miss-check")


def run_file_answer(args: FileAnswerArgs) -> int:
    """Print a contracts.FileAnswerResult.

    TODO(P4): build it (task 2.3d)."""
    raise NotBuilt("P4", "file-answer")

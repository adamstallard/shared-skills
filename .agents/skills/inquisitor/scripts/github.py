"""GitHub lookups through `gh`, each returning a value or None when it
cannot tell.

None never means "no": each caller applies its requirement's rule for an
unknown, such as *An unreadable visibility counts against sharing* or *A
permission that cannot be read is no write access* (inquisitor spec). No
function here passes a login or repository to GitHub before checking its
syntax with formats.is_login or formats.is_repository; one off the syntax
gives None with no call made.

Owned by P2. tasks.md's task 0.4 measured that a caller without push access
gets 403 `Must have push access to view collaborator permission.`, which
write_access gives as None, and that an App's `<slug>[bot]` always reads
`none`. Standard library only.
"""

from dataclasses import dataclass
from typing import Literal

from common import NotBuilt

Visibility = Literal["private", "internal", "public"]


@dataclass(frozen=True)
class Comment:
    """A GitHub comment's or review's own text and author. login ends
    `[bot]` for an App's comment (task 0.11); author_type is GitHub's
    `User` or `Bot`."""

    url: str
    text: str
    login: str
    author_type: str
    node_id: str


def gh_login() -> str | None:
    """The login `gh api user` gives, or None when gh cannot tell.

    TODO(P2): build it."""
    raise NotBuilt("P2", "gh_login")


def session_login(configured: str | None) -> str | None:
    """The configured login when gh is logged in as it, else None
    (inquisitor spec: *A configured login counts only when gh is logged in
    as it*).

    TODO(P2): build it."""
    raise NotBuilt("P2", "session_login")


def write_access(repository: str, login: str) -> bool | None:
    """Whether login can push to repository, from
    `gh api repos/<owner>/<repo>/collaborators/<login>/permission`'s
    `user.permissions.push`; None when it cannot tell.

    TODO(P2): build it."""
    raise NotBuilt("P2", "write_access")


def visibility(repository: str) -> Visibility | None:
    """The repository's visibility from `gh repo view --json visibility`,
    or None when unreadable.

    TODO(P2): build it."""
    raise NotBuilt("P2", "visibility")


def more_visible(a: Visibility | None, b: Visibility | None) -> bool:
    """Whether a place of visibility a is more visible than one of
    visibility b. An unknown a counts as public and an unknown b as private
    (inquisitor spec: *An unreadable visibility counts against sharing*).

    TODO(P2): build it."""
    raise NotBuilt("P2", "more_visible")


def comment(url: str) -> Comment | None:
    """The comment or review a github.com answer_link names, read with the
    gh login the script runs under, or None when GitHub does not return it.

    TODO(P2): build it."""
    raise NotBuilt("P2", "comment")


def last_commit_author(repository: str, path: str) -> str | None:
    """The `author.login` of the newest commit to path (task 0.5), or None
    for a commit naming no GitHub account.

    TODO(P2): build it."""
    raise NotBuilt("P2", "last_commit_author")


def decision_approver(repository: str, decision: str) -> str | None:
    """The approver of the pull request that added a related earlier
    decision, or None when it cannot be found (task 0.8 measures how).

    TODO(P2): build it."""
    raise NotBuilt("P2", "decision_approver")

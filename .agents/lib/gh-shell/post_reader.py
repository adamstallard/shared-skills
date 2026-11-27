"""The shared post reader tells a hook, for a tool call, the posts it sends
on a GitHub issue or pull request, or that it sends none, or that a post's
body cannot be read (gh-post spec: *The shared post reader reads a post's
body from an allow-list*). prose's posting hook and the inquisitor's post
hook read posts only through read_posts.

TODO(P1): move prose's body reader (posts_in and its helpers in
.agents/skills/prose/scripts/prose.py) here, as tasks.md's tasks 1.1 to
1.3 say. Standard library only.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Post:
    """One body the call sends. The field `where` labels that body in the
    hooks' block messages, such as `gh pr comment --body-file` or
    `comments[0].body` of a review."""

    where: str
    body: str


@dataclass(frozen=True)
class NoPost:
    """The call sends no post."""


@dataclass(frozen=True)
class Unreadable:
    """The call may send a post whose body the reader cannot read, and why.
    The inquisitor's post hook and prose's posting hook both block such a
    call."""

    why: str


def read_posts(payload: dict[str, Any], host: str) -> list[Post] | NoPost | Unreadable:
    """What the hook payload's tool call posts. host is "claude" or
    "cursor", as prose's hook names it, since the two hosts send different
    payload shapes. A call that posts several bodies,
    such as a review with comments, gives one Post per body.

    TODO(P1): build it."""
    raise NotImplementedError("read_posts is not built (owned by P1)")

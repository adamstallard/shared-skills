"""`tag`: whom a posted question tags (inquisitor spec: *A question in a post
tags one person who can decide, if there is one*; *A question no candidate
can decide turns to the session's login*; *A candidate or login that cannot
be checked is skipped*).

Owned by P3 (task 2.6). Standard library only.
"""

from dataclasses import dataclass

from common import NotBuilt


@dataclass(frozen=True)
class TagArgs:
    """hash: the vetted question's hash, whose verdict record gives its
    related earlier decision, what it concerns and its files. posting_as:
    the login the post goes out as, or None when unknown, which counts as
    the configured login (task 0.7 decides how the agent learns it)."""

    hash: str
    posting_as: str | None = None


def run(args: TagArgs) -> int:
    """Print a contracts.TagResult.

    TODO(P3): build it."""
    raise NotBuilt("P3", "tag")

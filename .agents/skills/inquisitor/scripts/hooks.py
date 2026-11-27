"""The picker hook and the post hook, run by scripts/check-ask.sh and
scripts/check-post.sh with the host's hook payload on standard input
(inquisitor spec: *A hook blocks a picker question that was not vetted*;
*Questions in posts pass the same filters*; *The post hook vets what the
shared post reader returns*).

Owned by P6 (tasks 3.1 to 3.3). Standard library only.
"""

from common import NotBuilt


def run_ask(payload: str) -> int:
    """0 to let the call through, 2 to block it with the message on stderr.
    Fails open.

    TODO(P6): build it."""
    raise NotBuilt("P6", "hook-ask")


def run_post(payload: str) -> int:
    """0 to let the post through, 2 to block it. Reads posts only through
    the shared post reader (.agents/lib/gh-shell/post_reader.py) and fails
    closed.

    TODO(P6): build it."""
    raise NotBuilt("P6", "hook-post")

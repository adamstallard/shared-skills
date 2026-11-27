"""The two calls that prove the four filters ran (`vet`), and the verdict
records the picker hook and the post hook read (inquisitor spec: *Two calls prove the filters ran*; *The
second call records all its verdicts or none*; *The two calls' files and
records stay private*; *Some questions are recorded by hash only*).

Owned by P3 (tasks 2.1, 2.2). Standard library only.
"""

from dataclasses import dataclass

from common import NotBuilt
from contracts import VerdictRecord


@dataclass(frozen=True)
class VetArgs:
    """The first call takes questions (a QuestionsInput file, or `-` for
    standard input) or post (a post's body, a markdown file), with
    repository or lore naming what the post's questions concern. The second
    call takes pass_token and verdicts (a VerdictsInput file, or `-`)."""

    questions: str | None = None
    post: str | None = None
    repository: str | None = None
    lore: str | None = None
    pass_token: str | None = None
    verdicts: str | None = None


def run(args: VetArgs) -> int:
    """First call: print the four filters' instructions and filter 1's
    results for each question, issue a token, record nothing. Second call:
    check and record every verdict or none, printing, for each `ask`
    verdict, its record line and person-required line
    (contracts.SecondCallLine).

    TODO(P3): build it."""
    raise NotBuilt("P3", "vet")


def read_records(hashes: set[str]) -> dict[str, VerdictRecord] | None:
    """The latest record for each hash asked for. It deletes each record
    over 2 hours old, the life of a verdict, and no other; None when the records cannot be read. Both
    hooks and `tag` call this.

    TODO(P3): build it."""
    raise NotBuilt("P3", "read_records")

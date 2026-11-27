"""`log`, which writes and pushes every log and miss file but those an Igor
writes itself, and `misses`, which lists misses for a review (inquisitor
spec: *A log file and a miss file have one format* and the `log` command's
requirements).

Owned by P5 (tasks 2.4, 2.9). Standard library only.
"""

from dataclasses import dataclass

from common import NotBuilt


@dataclass(frozen=True)
class LogArgs:
    """input: a private contracts.LogInput file. service: the option only
    the answer service passes; it allows handled files, hash-only miss
    files, reply-id miss names and Linear or Discord answer links, and keeps
    nothing pending. asked_from: the answer service's `asked_from`
    (service only). hash_only: write a hash-only miss file (service only).
    confirm_visible: the person confirmed sending the record somewhere more
    visible than its source."""

    input: str
    service: bool = False
    asked_from: str | None = None
    hash_only: bool = False
    confirm_visible: bool = False


@dataclass(frozen=True)
class MissesArgs:
    """repository or lore: whose questions branch to list; filter: only
    misses against that filter."""

    repository: str | None = None
    lore: str | None = None
    filter: str | None = None


def run(args: LogArgs) -> int:
    """Write one file and push it, printing a contracts.LogResult.

    TODO(P5): build it."""
    raise NotBuilt("P5", "log")


def run_misses(args: MissesArgs) -> int:
    """List the misses by filter.

    TODO(P5): build it."""
    raise NotBuilt("P5", "misses")

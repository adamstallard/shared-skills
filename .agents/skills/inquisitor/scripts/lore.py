"""`lore`: open a lore pull request adding a new entry, a promotion from a
questions branch, or a lesson from misses (inquisitor spec: *An answer that
generalizes is proposed as lore* through *A proposed lore entry's path,
fields and id follow igor's rules*).

Owned by P5 (tasks 2.7, 2.8). Standard library only.
"""

from dataclasses import dataclass

from common import NotBuilt

# igor's id rule (`ID_PATTERN` in igor's src/entry.ts).
ID_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


@dataclass(frozen=True)
class LoreArgs:
    """input: a private contracts.LoreInput file. confirm_visible: the
    person confirmed the entry for a lore repository more visible than its
    source."""

    input: str
    confirm_visible: bool = False


def run(args: LoreArgs) -> int:
    """Open the pull request, or during an Igor's run write the entry into
    the run's report.

    TODO(P5): build it."""
    raise NotBuilt("P5", "lore")

"""`cite`: push a citation file to the questions branch of the lore
repository holding a cited entry (inquisitor spec: *A lore entry that stops
a question gets a citation file*; *A citation file has one format*).

Owned by P5 (task 2.4b). Standard library only.
"""

from dataclasses import dataclass

from common import NotBuilt


@dataclass(frozen=True)
class CiteArgs:
    """lore: the lore repository as owner/repo; entry: the cited entry's
    id; service: the answer service's option, which keeps nothing
    pending."""

    lore: str
    entry: str
    service: bool = False


def run(args: CiteArgs) -> int:
    """Push the citation. During an Igor's run (common.igor_run()), push
    nothing: the Igor publishes the citations its worker reports.

    TODO(P5): build it."""
    raise NotBuilt("P5", "cite")

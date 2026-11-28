"""`cite`: push a citation file to the questions branch of the lore
repository holding a cited entry (inquisitor spec: *A lore entry that stops
a question gets a citation file*; *A citation file has one format*).

Its callers decide whether a citation is owed: never for a question with a
category (`vulnerability`, `secret` or `personal`), which the spec records
by hash only, nor for an entry out of scope or not `active`. This command does
not check those, nor any visibility, since a citation names only the entry
and the day.

Owned by build part P5 of the implementation plan (task 2.4b). Standard library only.
"""

import re
from dataclasses import dataclass

from common import VERSION, Refused, igor_run, print_json
from contracts import CiteResult
from formats import CitationFile
import log_command
from log_command import check_repository, push
from lore import ID_PATTERN


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
    nothing: the worker reports the citation to its Igor, which publishes
    it under igor PR #216's rules."""
    lore = check_repository(args.lore, "--lore")
    if re.fullmatch(ID_PATTERN, args.entry) is None:
        raise Refused(f"--entry {args.entry!r} is no lore entry id")
    if igor_run() is not None:
        skipped: CiteResult = {"version": VERSION, "status": "skipped", "path": None,
                               "why": "an Igor's run pushes no citation; the Igor publishes "
                                      "those its worker reports"}
        print_json(skipped)
        return 0
    date = log_command.today()
    citation = CitationFile(name=f"{date}-{log_command.random_hex()}", entry=args.entry, date=date)
    path = f"citations/{citation.name}"
    result = push(lore, path, citation, True, args.service)
    print_json(result)
    return 0

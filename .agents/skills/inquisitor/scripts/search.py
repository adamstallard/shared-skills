"""Filter 1's search, used by the first call, and the `search` command that
runs it alone for the answer service (inquisitor spec: *Filter 1 searches
every place an answer is recorded* through *Only an answer with authority
stops a question* and its authority rules; *The search command runs filter
1 alone for the answer service*).

Owned by P4 (tasks 2.3, 2.3e). Standard library only.
"""

from dataclasses import dataclass

from common import NotBuilt
from contracts import QuestionIn, SearchResult


@dataclass(frozen=True)
class SearchArgs:
    """input: a SearchInput file, or `-` for standard input, the only way a
    question with a category may come."""

    input: str


def filter1(question: QuestionIn, service: bool) -> SearchResult:
    """Filter 1's results for one question. service: read only the answer
    service's clones as last fetched, and reading issues only of repositories
    those clones hold, fetching nothing. Outside an Igor's run it reads the configured
    lore clones; in one (common.igor_run()) it searches lore only through
    `igor lore-search`.

    TODO(P4): build it."""
    raise NotBuilt("P4", "filter1")


def run(args: SearchArgs) -> int:
    """Print filter1(question, service=True) as JSON: no token, no record,
    no file, no fetch.

    TODO(P4): build it."""
    raise NotBuilt("P4", "search")

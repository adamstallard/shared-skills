"""The formats of questions-branch files: log files (question, answer and
handled files), miss files (readable and hash-only) and citation files.

Every writer and reader goes through this module, so a file has one format
wherever it is written (inquisitor spec: *A log file and a miss file have
one format*; *A citation file has one format*). The golden files under
fixtures/formats/ are the format as the specs give it: each is a file's
path on a questions branch with `.golden` added, so that prose and other
tools that check .md docs leave it as it is. render() of each dataclass below must equal its golden file byte for
byte, and parse() of the golden file, read at its path without `.golden`,
must give the dataclass back.

Owned by P2. Standard library only.
"""

from dataclasses import dataclass
from typing import Literal

from common import NotBuilt

Surface = Literal["github", "linear", "discord"]
Authority = Literal["decision", "input"]


@dataclass(frozen=True)
class Answer:
    """The answer part of an answer file. text is the answer's lines without
    their quote marks. rephrased and discussion are set together, when
    the person answered a rephrased version of the question in the answer
    service."""

    answered_by: str
    authority: Authority
    recorded_in: str
    text: str
    answer_link: str | None = None
    answers: tuple[str, ...] = ()
    rephrased: str | None = None
    discussion: str | None = None


@dataclass(frozen=True)
class LogFile:
    """A question or answer file, `questions/<date>-<slug>-<hex>.md`.

    question holds the question's lines as logged, its tag, related-decision,
    person-required and concerns lines included. repository is None on a
    collective's file; asked_from is None only in a file written during an
    Igor's run, before the Igor sets it.
    """

    name: str
    asked: str
    question: str
    repository: str | None = None
    asked_from: str | None = None
    asked_in: str | None = None
    answer: Answer | None = None


@dataclass(frozen=True)
class HandledFile:
    """A handled file: only `handled` (yyyy-mm-dd, UTC) and `closes` (the
    closed file's name without its directory), and no body."""

    name: str
    handled: str
    closes: str


@dataclass(frozen=True)
class MissFile:
    """A readable miss file, `misses/<hash>.md`. filter is "1" to "4".
    said_by is None in a miss reported by an Igor's worker or by
    the Igor's own inquisitor run; asked_by
    is None for a question with no thread, and in a worker's miss."""

    hash: str
    asked: str
    filter: Literal["1", "2", "3", "4"]
    said: str
    question: str
    said_by: str | None = None
    asked_by: str | None = None
    repository: str | None = None
    asked_from: str | None = None
    asked_in: str | None = None


@dataclass(frozen=True)
class HashOnlyMiss:
    """A hash-only miss file: empty frontmatter, no body (inquisitor spec: *A
    hash-only miss file shows nothing but that it exists*)."""

    hash: str


@dataclass(frozen=True)
class CitationFile:
    """`citations/<date>-<hex>` on a lore repository's questions branch.
    run is set only when an Igor pushes it from a run."""

    name: str
    entry: str
    date: str
    run: str | None = None


@dataclass(frozen=True)
class Unreadable:
    """A questions-branch file that does not read as its format says.
    Callers show it only as input labelled unreadable, and post nothing from
    it, its name included."""

    path: str
    why: str


QuestionsBranchFile = LogFile | HandledFile | MissFile | HashOnlyMiss | CitationFile


# -- names ------------------------------------------------------------------

def slug(question_text: str) -> str:
    """The slug of a log file's name: lowercase, each run of characters
    other than a-z and 0-9 made one `-`, at most 40 characters, no `-` at
    either end, or `question` when nothing is left.

    TODO(P2): build it."""
    raise NotBuilt("P2", "slug")


def log_name(date: str, slug_text: str, suffix: str) -> str:
    """`<date>-<slug>-<suffix>.md`; a handled file's slug is `handled`.

    TODO(P2): build it."""
    raise NotBuilt("P2", "log_name")


def miss_hash(kind: Literal["github", "linear", "discord", "file", "message"], value: str) -> str:
    """The hash naming `misses/<hash>.md`: SHA-256 of kind, LF, value
    (inquisitor spec: *Every miss file is named by one hash*). For a reply,
    kind is its surface and value the reply's id (a GitHub reply's
    node_id); else `file` and the log file's path, or `message` and the
    asking message's URL.

    TODO(P2): build it."""
    raise NotBuilt("P2", "miss_hash")


# -- the forms keys must take ------------------------------------------------

def is_login(value: str) -> bool:
    """GitHub's login syntax, checked before a login reaches any API call
    (inquisitor spec: *A candidate or login that cannot be checked is
    skipped*). TODO(P2): build it."""
    raise NotBuilt("P2", "is_login")


def is_repository(value: str) -> bool:
    """`<owner>/<repo>`, as the spec's scenario *The forms a repository key
    and an answer_link must take* sets it. TODO(P2): build it."""
    raise NotBuilt("P2", "is_repository")


def is_answer_link(value: str) -> bool:
    """A github.com comment or review URL, or a relayed Linear or Discord
    URL, in the forms the spec gives. TODO(P2): build it."""
    raise NotBuilt("P2", "is_answer_link")


def is_asked_in(value: str) -> bool:
    """An `asked_in` in the forms *Where an asked_in may be written* gives.
    TODO(P2): build it."""
    raise NotBuilt("P2", "is_asked_in")


def is_recorded_in(value: str) -> bool:
    """A `recorded_in`: an answer_link form, or a path from the repository's
    root, optionally `@<40 hex>`. TODO(P2): build it."""
    raise NotBuilt("P2", "is_recorded_in")


# -- reading and writing -----------------------------------------------------

def render(file: QuestionsBranchFile) -> str:
    """The file's content: UTF-8 text with LF line ends, frontmatter values
    double-quoted. TODO(P2): build it."""
    raise NotBuilt("P2", "render")


def parse(path: str, content: str, lore_branch: bool) -> QuestionsBranchFile | Unreadable:
    """Read a questions-branch file by its path (`questions/…`,
    `misses/…` or `citations/…`). lore_branch says whether the branch is a
    lore repository's, where a log file may lack `repository`. Anything off
    the format is Unreadable (inquisitor spec: *A log file is read by its
    frontmatter and its body's end*; *A questions-branch file named outside
    the format is unreadable*; *A log file's repository keys and links are
    checked before use*). TODO(P2): build it."""
    raise NotBuilt("P2", "parse")

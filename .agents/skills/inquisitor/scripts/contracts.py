"""The JSON every command reads or prints, as TypedDicts.

These shapes are the interfaces between the build parts: a part changing
one changes it here, and the golden copies under fixtures/json/, in the
same commit. branch-search, miss-check and file-answer outputs are also a
contract with igor (tasks 2.3b to 2.3d), checked field for field against
their stored copies.

Terms such as filter, miss, category, place, relay, the two calls and
an Igor's run are the inquisitor and answer-service specs' terms
(openspec/changes/inquisitor/specs/, or openspec/specs/ once archived).

Owned by P0. Standard library only.
"""

from typing import Literal, NotRequired, TypedDict

Category = Literal["vulnerability", "secret", "personal"]
VerdictName = Literal["answered", "deferred", "decided", "ask"]
QuestionKind = Literal["picker", "post", "text"]


# -- what a question concerns ------------------------------------------------

class Concerns(TypedDict):
    """What a question concerns. repository: the repository the question
    concerns, as owner/repo. lore: for a question about a team rather than
    one repository, the team's lore repository, as owner/repo. With neither
    key, the question is about one person's way of working. asked_from: the
    repository holding the current work, which limits what a team's
    question may draw on; the script fills it from the working tree when
    absent."""

    repository: NotRequired[str]
    lore: NotRequired[str]
    asked_from: NotRequired[str]


# -- the first call (vet --questions) and search ------------------------------

class QuestionIn(TypedDict):
    """One question as the person would see it. For kind "picker", question
    is the `question` field and options its labels; "post" is a list item
    or sentence; "text" any other text, whole. files: the files the
    question concerns. category is given only on standard input, so a
    question with a category never sits in a file."""

    kind: QuestionKind
    question: str
    options: NotRequired[list[str]]
    concerns: Concerns
    files: NotRequired[list[str]]
    category: NotRequired[Category]


class QuestionsInput(TypedDict):
    """`vet --questions <file|->`: the first call's questions."""

    version: int
    questions: list[QuestionIn]


class SearchInput(TypedDict):
    """`search --input <file|->`: one question for filter 1 alone."""

    version: int
    question: QuestionIn


# -- the second call (vet --pass --verdicts) ----------------------------------

class AnsweredField(TypedDict):
    citation: str


class WhereField(TypedDict):
    """`deferred`: where the question will be listed. `decided`: where the
    choice is recorded."""

    where: str


class AskField(TypedDict):
    """recommended: the recommended answer, a picker option's label or, for
    a post question, a sentence. changes: what changes under each other
    answer."""

    recommended: str
    changes: str


class VerdictIn(TypedDict):
    """One verdict. question: the question's number as the first call
    printed it, from 1. related: the URL of a related earlier decision from
    the question's filter 1 hits (ask only). requires: the skill requiring a
    person to decide it (ask only), lowercase letters, digits and `-`."""

    question: int
    verdict: VerdictName
    field: AnsweredField | WhereField | AskField
    related: NotRequired[str]
    requires: NotRequired[str]


class VerdictsInput(TypedDict):
    version: int
    verdicts: list[VerdictIn]


class SecondCallLine(TypedDict):
    """What the second call prints for one `ask`, as JSON after its text:
    the lines the agent copies exactly into the question. record_line only for a question
    asked in the session (picker or reply); person_required_line only when
    the ask names a requiring skill."""

    question: int
    hash: str
    record_line: NotRequired[str]
    person_required_line: NotRequired[str]


class VerdictRecord(TypedDict):
    """One verdict record, a file of mode 0600 under common.verdicts_dir(),
    read by the inquisitor's picker and post hooks and by `tag`. time is
    seconds since the epoch, UTC. kind, field, related, requires, concerns
    and files come from the second call's input for the question. A
    question with a category keeps only version, hash, verdict, time and
    category. For an `ask` verdict of kind "picker", the field (an
    AskField) drops `recommended`, which is then an option's label, and a
    record holds no option's label (inquisitor spec: *The two calls' files
    and records stay private*). identity: the
    github-app identity for which `tag` made the tag line (inquisitor spec:
    *A tag made for an App's post goes out only through github-app*)."""

    version: int
    hash: str
    verdict: VerdictName
    time: float
    category: NotRequired[Category]
    kind: NotRequired[QuestionKind]
    field: NotRequired[AnsweredField | WhereField | AskField | dict[str, str]]
    related: NotRequired[str]
    requires: NotRequired[str]
    concerns: NotRequired[Concerns]
    files: NotRequired[list[str]]
    identity: NotRequired[str]


# -- tag ----------------------------------------------------------------------

class TagResult(TypedDict):
    """`tag`: action "tag" puts line (`@login`) on the question's tag line;
    "untagged" puts line (qtext.UNTAGGED_LINE) there; "picker" asks the
    question through the picker instead, with line null."""

    version: int
    action: Literal["tag", "untagged", "picker"]
    line: str | None


# -- filter 1's hits ------------------------------------------------------------

InputReason = Literal["unconfirmed", "unanswered", "miss", "superseded", "unreadable", "input"]


class BranchHit(TypedDict):
    """A questions-branch hit, as branch-search prints it (inquisitor spec:
    *The script searches a questions branch and prints labelled hits as
    JSON*). answer is null for a file with no answer. reason only on an
    input hit. landed: true, false, or null when the file's own
    `recorded_in` pins no commit. filter and said only on a miss file's hit."""

    path: str
    question: str
    answer: str | None
    label: Literal["decision", "input"]
    reason: NotRequired[InputReason]
    landed: bool | None
    filter: NotRequired[str]
    said: NotRequired[str]


class BranchSearchResult(TypedDict):
    version: int
    repository: str
    hits: list[BranchHit]


class MissCheckResult(TypedDict):
    version: int
    backed: bool


class FileAnswerResult(TypedDict):
    version: int
    answer: str | None


HitSource = Literal["decision-document", "issue", "questions-branch", "lore-entry",
                    "decision-record", "igor-lore-search"]


class SearchHit(TypedDict):
    """One of filter 1's hits. where: a path from the repository's root, or a URL. A
    questions-branch hit also holds every BranchHit field (source
    "questions-branch"). why: an input hit's label, such as `not accepted`
    or `unconfirmed`, as the first call prints it."""

    source: HitSource
    label: Literal["decision", "input"]
    repository: str | None
    where: str
    quote: str
    terms: int
    why: NotRequired[str]
    path: NotRequired[str]
    question: NotRequired[str]
    answer: NotRequired[str | None]
    reason: NotRequired[InputReason]
    landed: NotRequired[bool | None]
    filter: NotRequired[str]
    said: NotRequired[str]


class CloneFreshness(TypedDict):
    """A lore clone or subscribed clone, and when a fetch last updated its
    remote-tracking default branch (ISO 8601, UTC), or null when unknown."""

    path: str
    repository: str | None
    fetched: str | None


class SearchResult(TypedDict):
    """`search`: filter 1's results for one question. hits lists answers
    before input, each group by terms matched. left_out: how many hits the
    cap of 20 left out."""

    version: int
    hits: list[SearchHit]
    not_searched: list[str]
    clones: list[CloneFreshness]
    left_out: int


# -- log ------------------------------------------------------------------------

class Branch(TypedDict):
    """Which questions branch a file goes to: the repository's, or, for a
    collective's question, the lore repository's."""

    repository: NotRequired[str]
    lore: NotRequired[str]


class AnswerIn(TypedDict):
    """An answer. With a github.com answer_link the script reads text from
    the comment; otherwise text is the person's words as given. answers:
    names of the files on the branch it answers, without directory."""

    answered_by: str
    authority: Literal["decision", "input"]
    recorded_in: NotRequired[str]
    text: NotRequired[str]
    answer_link: NotRequired[str]
    answers: NotRequired[list[str]]
    rephrased: NotRequired[str]
    discussion: NotRequired[str]


class MissName(TypedDict):
    """What names a miss file: a reply's surface and id (service option
    only), else `file` and the log file's path, else `message` and the
    asking message's URL."""

    kind: Literal["github", "linear", "discord", "file", "message"]
    value: str


class MissIn(TypedDict):
    filter: Literal["1", "2", "3", "4"]
    said: str
    said_by: NotRequired[str]
    asked_by: NotRequired[str]
    name: MissName


class LogInput(TypedDict):
    """`log --input <file>`: one file to write and push. kind "handled"
    and a hash-only miss (`log --hash-only`) need `--service`, the option
    the skill reserves for the answer service. question is every line of the question
    as asked; absent only on a handled or hash-only file. handled: for kind
    "handled", the date written into the file, YYYY-MM-DD in UTC; when
    absent, the date of writing. repository, asked, asked_in and closes are the log file's keys
    of those names (inquisitor spec: *A log file and a miss file have one
    format*)."""

    version: int
    kind: Literal["question", "answer", "miss", "handled"]
    branch: Branch
    question: NotRequired[str]
    repository: NotRequired[str]
    asked: NotRequired[str]
    asked_in: NotRequired[str]
    answer: NotRequired[AnswerIn]
    miss: NotRequired[MissIn]
    handled: NotRequired[str]
    closes: NotRequired[str]


class LogResult(TypedDict):
    """What `log` prints. status "pushed", "pending" (kept, never with
    --service), "taken" (a miss file's name was on the branch) or "failed"
    (only with --service, which keeps nothing pending; `why` says why)."""

    version: int
    status: Literal["pushed", "pending", "taken", "failed"]
    path: str | None
    why: NotRequired[str]


class MissOut(TypedDict):
    """One miss file `misses` could parse: its branch and path, and every
    other field the miss file's key of the same name (inquisitor spec: *A
    log file and a miss file have one format*)."""

    branch: str
    path: str
    filter: str
    said: str
    asked: str
    question: str
    said_by: NotRequired[str]
    asked_by: NotRequired[str]
    repository: NotRequired[str]
    asked_from: NotRequired[str]
    asked_in: NotRequired[str]


class MissesResult(TypedDict):
    """What `misses` prints: each readable miss file, oldest first by the
    commit that added it; how
    many hash-only miss files each branch holds; the paths of unreadable
    ones; and the branches it could not read."""

    version: int
    misses: list[MissOut]
    hash_only: dict[str, int]
    unreadable: list[str]
    not_read: list[str]


class CiteResult(TypedDict):
    """What `cite` prints: a LogResult's fields. During an Igor's run,
    which common.igor_run() detects, `cite` pushes nothing and reports status "skipped"."""

    version: int
    status: Literal["pushed", "pending", "taken", "failed", "skipped"]
    path: str | None
    why: NotRequired[str]


# -- lore -----------------------------------------------------------------------

class LoreSource(TypedDict):
    """The entry's source; the script refuses a lore repository more
    visible than it: repository for a new entry; file for a promotion
    ({repository, path} of a questions-branch file); misses for a lesson
    from misses (each {repository, path})."""

    repository: NotRequired[str]
    file: NotRequired[dict[str, str]]
    misses: NotRequired[list[dict[str, str]]]


class LoreInput(TypedDict):
    """`lore --input <file> [--confirm-visible]`: the entry to propose.
    frontmatter holds every field igor's lore store requires (task 2.8)."""

    version: int
    kind: Literal["new", "promotion", "lesson"]
    lore: str
    id: str
    frontmatter: dict[str, object]
    body: str
    source: LoreSource

"""The JSON commands between the answer mod and the answer service's Python
core.

The mod (TypeScript) does the UI, the timers, its tools, the answer marker
(the environment variable the `answer` launcher sets) and stripping other
plugins' tools from the session; the core does polling, state, records and pushes,
reusing the script's hash and file-format code. The mod runs
`python3 -I <skill>/scripts/inquisitor.py service` once per command, with one Request on
standard input, and reads one Response from standard output. The core
keeps no process between commands: its state is the state folder.

answer-mod/hooks/core-protocol.ts mirrors these types; fixtures/service/
holds one example of each request and response, which both sides' tests
read. Change all three together.

Owned by P0. Standard library only.
"""

from typing import Literal, NotRequired, TypedDict

Surface = Literal["github", "linear", "discord"]
Filter = Literal[1, 2, 3, 4]


# -- shared shapes ---------------------------------------------------------------

class LockInfo(TypedDict):
    """The state folder's `lock`: the holding session's id, name and start
    (ISO 8601, UTC), and its last refresh."""

    session_id: str
    session_name: str
    started: str
    refreshed: str


class Notice(TypedDict):
    """Something the mod shows: a failed check, a channel turned off, the
    rate-limit wait, discord-bot's warnings, why no miss was logged. kind
    is a closed list the mod renders; text is shown as is."""

    kind: Literal["check-failed", "channel-off", "rate-limit", "relay-warning",
                  "no-miss", "push-failed", "login", "lock-lost"]
    text: str


class Reply(TypedDict):
    """A message in a question's thread after it."""

    author: str
    text: str
    at: str
    url: str


class RecordedAnswer(TypedDict):
    """Filter 1's recorded answer shown beside a question: where it is
    recorded, and the hit's quote."""

    recorded_in: str
    quote: str


class QuestionView(TypedDict):
    """A question as the mod shows it. id is the core's own key for it,
    stable across polls. asker: "person" (including a relayed question),
    "agent", "item" (an Igor handback's item question) or
    "questions-branch". text is null when the core has no readable copy:
    a question with a category, whose text is never written to disk. item: its number in an
    open-questions section. new: found by the poll that returned it."""

    id: str
    surface: Surface
    asker: Literal["person", "agent", "item", "questions-branch"]
    asked_by: str
    asked_at: str
    url: str
    text: str | None
    item: NotRequired[int]
    concerns: NotRequired[str]
    related: NotRequired[str]
    recorded: NotRequired[RecordedAnswer]
    replies: list[Reply]
    has_category: bool
    new: bool


class PendingView(TypedDict):
    """An answer the person gave that is not yet posted in its thread, and
    why."""

    question: str
    text: str
    why: str


class JudgeRequest(TypedDict):
    """A message the code puts before the model for record_verdict. turn 1
    asks for question, category, and place or place_sure when the message
    needs them; turn 2 for filter and hit, with search's hits. places: the
    places turn 1 may give (each subscribed and lore repository). defaults:
    those of places the channel's `repos` names."""

    message: str
    turn: Literal[1, 2]
    text: str
    needs_place: bool
    needs_place_sure: bool
    places: list[str]
    defaults: list[str]
    hits: NotRequired[list[dict[str, object]]]
    person_question: bool


class VerdictFields(TypedDict, total=False):
    """record_verdict's fields, a closed list (answer-service spec:
    *record_verdict's fields are a closed list*). Values arrive as the
    model sent them; the core refuses one outside its set."""

    question: str
    category: str
    filter: str
    hit: int
    place: str
    place_sure: str


class PreviewRecord(TypedDict):
    """Where an answer will be recorded: the place, its visibility, and the
    thread's or source's place when the record is more visible."""

    place: str | None
    visibility: Literal["private", "internal", "public"] | None
    more_visible_than: NotRequired[str]
    not_recorded: NotRequired[str]


# -- requests ----------------------------------------------------------------------

class OpenRequest(TypedDict):
    command: Literal["open"]
    session_id: str
    session_name: str
    takeover: bool


class SessionRequest(TypedDict):
    """refresh, close, poll, pending.list and setup.status take only the
    session's id, which the core checks against the lock first."""

    command: Literal["refresh", "close", "poll", "pending.list", "setup.status"]
    session_id: str


class SetupSaveRequest(TypedDict):
    """Save setup's answers. config is the answer_service section;
    linear_key, when given, goes to the keychain, never the file."""

    command: Literal["setup.save"]
    session_id: str
    login: NotRequired[str]
    config: dict[str, object]
    linear_key: NotRequired[str]


class SetupGuessRequest(TypedDict):
    command: Literal["setup.guess-repos"]
    session_id: str
    surface: Literal["linear", "discord"]
    channel: str


class SetupCreateLoreRequest(TypedDict):
    command: Literal["setup.create-lore"]
    session_id: str
    repository: str
    path: str
    serves: list[str]


class VerdictRequest(TypedDict):
    """A record_verdict call. agent_id: the call's agentId, if any; the
    core refuses a call that carries one, since only the main conversation
    may judge."""

    command: Literal["judge.verdict"]
    session_id: str
    message: str
    turn: Literal[1, 2]
    fields: VerdictFields
    agent_id: NotRequired[str]


class TurnEndRequest(TypedDict):
    """The model's reply in a judging turn ended; the core acts on the
    turn's accepted fields."""

    command: Literal["judge.turn-end"]
    session_id: str
    message: str
    turn: Literal[1, 2]


class DiscussionRequest(TypedDict):
    """Append to a question's discussion record (nothing for a question with
    a category)."""

    command: Literal["discussion.append"]
    session_id: str
    question: str
    role: Literal["person", "model"]
    text: str


class ContextRequest(TypedDict):
    """The quoted-data context for a discussion message."""

    command: Literal["context"]
    session_id: str
    question: str


class ScreenRequest(TypedDict):
    command: Literal["screen.set"]
    session_id: str
    question: str | None


class PreviewRequest(TypedDict):
    """Build the exact post and record before anything goes out. action:
    "answer" (a `User says: ` post), "ask" (a `User asks: ` post), "decline" (reason 1 or 2, with
    filter for reason 2), "agree" (a shown recorded answer), "edit" (a
    relay post's new text). place: the person's pick of another place.
    recorded_in: the URL a filter 1 decline's post links. note: the
    person's note for a miss."""

    command: Literal["preview"]
    session_id: str
    question: str
    action: Literal["answer", "ask", "decline", "agree", "edit"]
    text: NotRequired[str]
    place: NotRequired[str]
    reason: NotRequired[Literal[1, 2]]
    filter: NotRequired[Filter]
    recorded_in: NotRequired[str]
    note: NotRequired[str]


class PostRequest(TypedDict):
    """Send what a preview showed, unchanged: preview is PreviewResponse's
    id."""

    command: Literal["post"]
    session_id: str
    preview: str


class ReopenRequest(TypedDict):
    command: Literal["reopen"]
    session_id: str
    question: str


Request = (OpenRequest | SessionRequest | SetupSaveRequest | SetupGuessRequest
           | SetupCreateLoreRequest | VerdictRequest | TurnEndRequest | DiscussionRequest
           | ContextRequest | ScreenRequest | PreviewRequest | PostRequest | ReopenRequest)


# -- responses ---------------------------------------------------------------------

class ErrorResponse(TypedDict):
    """Any command the core refuses or fails: lock_lost means the lock names
    another session, and the mod closes the answer service."""

    version: int
    ok: Literal[False]
    error: str
    lock_lost: NotRequired[bool]


class OpenResponse(TypedDict):
    """status "opened": the lock is held; "locked": another session holds a
    fresh lock, named in lock; "setup": the configuration is incomplete, so
    setup opens. screen: the question last on screen, if it still shows."""

    version: int
    ok: Literal[True]
    status: Literal["opened", "locked", "setup"]
    lock: NotRequired[LockInfo]
    screen: NotRequired[str | None]
    notices: list[Notice]


class RefreshResponse(TypedDict):
    version: int
    ok: Literal[True]
    held: bool


class PollResponse(TypedDict):
    version: int
    ok: Literal[True]
    questions: list[QuestionView]
    judge: list[JudgeRequest]
    notices: list[Notice]
    rate_limited_until: str | None


class SetupCheck(TypedDict):
    surface: Surface | Literal["login", "lore"]
    channel: NotRequired[str]
    name: str
    ok: bool | None
    fix: NotRequired[str]


class SetupStatusResponse(TypedDict):
    version: int
    ok: Literal[True]
    complete: bool
    config: dict[str, object]
    checks: list[SetupCheck]


class GuessResponse(TypedDict):
    version: int
    ok: Literal[True]
    repos: list[str]


class VerdictResponse(TypedDict):
    version: int
    ok: Literal[True]
    accepted: bool
    why: NotRequired[str]


class TurnEndResponse(TypedDict):
    """next: the turn 2 request after turn 1, else null. posted: URLs of
    automatic posts the core made."""

    version: int
    ok: Literal[True]
    next: JudgeRequest | None
    posted: list[str]
    notices: list[Notice]


class ContextResponse(TypedDict):
    version: int
    ok: Literal[True]
    context: str


class PreviewResponse(TypedDict):
    """post is the exact text, or null when nothing is posted (a decline
    with no thread or with a category). reaches_run: the line saying the
    answer also reaches the run of an Igor working on a more visible item. reword: why the text
    must be reworded (an answer whose last line starts `Re: `)."""

    version: int
    ok: Literal[True]
    id: str
    post: str | None
    record: PreviewRecord
    warnings: list[str]
    reaches_run: NotRequired[str]
    reword: NotRequired[str]


class PostResponse(TypedDict):
    """status "posted", "pending" (kept to relay once its channel works),
    "held" (a reply arrived since the preview) or "failed"."""

    version: int
    ok: Literal[True]
    status: Literal["posted", "pending", "held", "failed"]
    url: NotRequired[str]
    warnings: list[str]
    why: NotRequired[str]


class PendingResponse(TypedDict):
    version: int
    ok: Literal[True]
    answers: list[PendingView]


class DoneResponse(TypedDict):
    """close, discussion.append, screen.set, reopen and setup.create-lore."""

    version: int
    ok: Literal[True]


Response = (ErrorResponse | OpenResponse | RefreshResponse | PollResponse | SetupStatusResponse
            | GuessResponse | VerdictResponse | TurnEndResponse | ContextResponse
            | PreviewResponse | PostResponse | PendingResponse | DoneResponse)

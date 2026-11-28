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

Terms such as filter, miss, category, place, relay, the two calls and
an Igor's run are the inquisitor and answer-service specs' terms
(openspec/changes/inquisitor/specs/, or openspec/specs/ once archived).

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


class Suggestion(TypedDict):
    """The suggestion the model makes when it judges an agent's question
    by filters 2 to 4 (answer-service spec: *Filters 2 to 4 only suggest a
    verdict on other questions*). filter is the filter the model judged the
    question fails; why is the model's reason, in its words. The mod shows
    both."""

    filter: Literal[2, 3, 4]
    why: str


class Option(TypedDict):
    """One answer a question offers. label is the answer's text as shown;
    effect is what choosing it would change, "" for an option given as a
    label only."""

    label: str
    effect: str


class Revision(TypedDict):
    """A question as rephrased after a discussion and accepted by the
    person. text is the rephrased question; summary, the discussion in one
    sentence; options, for a question with options, its options as
    rephrased. An answer's post carries text and summary on its
    `Rephrased question: ` and `Discussion: ` lines."""

    text: str
    summary: str
    options: NotRequired[list[Option]]


class QuestionView(TypedDict):
    """A question as the mod shows it. id is the core's own key for it,
    stable across polls. asker: "person" (including a relayed question),
    "agent", "item" (an Igor handback's item question) or
    "questions-branch". text is null only for a question with a category,
    whose text is never written to disk. item: its number in the Igor
    handback's open-questions section. concerns: the place it concerns.
    related: an earlier decision it names. recorded: filter 1's recorded
    answer. replies: its thread's messages after it. new: found by the poll
    that returned it. state: "open"; "set-aside", set aside for later by
    the person and queued after the open ones in the mod's list; or "pending", answered,
    the answer not yet posted in its thread; absent means "open".
    suggested: filters 2 to 4's Suggestion, never on a person's question.
    relay: the bot account that posts the person's answers on the
    question's surface, such as `answers[bot]`; absent for a
    questions-branch question, since nothing is posted for one. revision:
    the rephrasing the person last accepted (discussion.revise)."""

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
    state: NotRequired[Literal["open", "set-aside", "pending"]]
    suggested: NotRequired[Suggestion]
    relay: NotRequired[str]
    revision: NotRequired[Revision]


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
    """Save setup's answers. config is inquisitor.json's answer_service
    section; login, the person's GitHub login, goes to inquisitor.json's
    top-level `login`. The
    person's Linear key never passes through this protocol: the person
    stores it in the keychain with the command setup.status gives, and the
    core reads it from there."""

    command: Literal["setup.save"]
    session_id: str
    login: NotRequired[str]
    config: dict[str, object]


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


class ReviseRequest(TypedDict):
    """The core keeps the rephrasing the person accepted after a discussion,
    in the question's discussion record, or in memory only for a question
    with a category, since such a question has no discussion record. When
    the question's next "answer" preview builds its post, that post
    includes it."""

    command: Literal["discussion.revise"]
    session_id: str
    question: str
    revision: Revision


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
    """Build the exact post and the questions-branch record before anything
    goes out. action: "answer" (a `User says: ` post), "ask" (a `User asks:
    ` post), "decline" (reason 1, won't answer, or reason 2, the inquisitor
    should have stopped the question, with the filter that should have
    stopped it: answer-service spec, *The person can decline to answer*),
    "agree" (a shown recorded answer), "edit" (a relay post's new text).
    text: the answer, the question asked back or the edited post's text,
    for "answer", "ask" and "edit". place: the person's pick of a place
    other than the one the question concerns, for the question's record.
    recorded_in: for a reason 2, filter 1 decline, the URL its post links
    to. note: the person's note for the miss a reason 2 decline logs.
    unasked: with reason 2 and filter 3 on an agent's question, filter 3's
    "the agent shouldn't have asked": the core posts nothing and logs a
    filter 3 miss against the asking agent; it refuses unasked with any
    other reason or filter."""

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
    unasked: NotRequired[bool]


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
           | ReviseRequest | ContextRequest | ScreenRequest | PreviewRequest | PostRequest
           | ReopenRequest)


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
    """rate_limited_until concerns GitHub alone: while GitHub refuses
    requests for its rate limit, it holds the reset time GitHub gave (ISO
    8601, UTC), else null. The core sends GitHub no request until then and
    keeps polling Linear and Discord, and it adds a "rate-limit" notice to
    the first poll of each such wait only, so the person is told once per
    wait."""

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


class Candidate(TypedDict):
    """A channel that setup offers: a GitHub owner or repository, a Linear
    team or a Discord channel that the relay (the bot account that posts
    the person's answers) or the person can read. id is the value that
    inquisitor.json's answer_service section lists under `subscriptions`
    once the person subscribes; name is shown beside it; subscribed says
    whether it is listed there already."""

    surface: Surface
    id: str
    name: str
    subscribed: bool


class SetupStatusResponse(TypedDict):
    """candidates: the channels setup offers. linear_key_command: present
    only when Linear is configured as a surface and the keychain holds no
    key for it; the
    command the person runs in their own terminal to store their Linear
    API key."""

    version: int
    ok: Literal[True]
    complete: bool
    config: dict[str, object]
    checks: list[SetupCheck]
    candidates: NotRequired[list[Candidate]]
    linear_key_command: NotRequired[str]


class GuessResponse(TypedDict):
    version: int
    ok: Literal[True]
    repos: list[str]


class VerdictResponse(TypedDict):
    version: int
    ok: Literal[True]
    accepted: bool
    why: NotRequired[str]


class PostedItem(TypedDict):
    """An automatic post the core made (answer-service spec: *An automatic
    post's text is fixed by the answer service*). question is the id of
    the question it answers; url, the post's URL; text, its exact text; and
    kind, "recorded" for a `Recorded answer: ` post or "inquisitor" for an
    `Inquisitor: ` post."""

    question: str
    url: str
    text: str
    kind: Literal["recorded", "inquisitor"]


class TurnEndResponse(TypedDict):
    """next: after turn 1, the turn 2 request, or null when the message
    needs no turn 2; after turn 2, null. posted: the automatic posts the
    core made."""

    version: int
    ok: Literal[True]
    next: JudgeRequest | None
    posted: list[PostedItem]
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
    """The response to close, discussion.append, discussion.revise,
    screen.set, reopen and setup.create-lore."""

    version: int
    ok: Literal[True]


Response = (ErrorResponse | OpenResponse | RefreshResponse | PollResponse | SetupStatusResponse
            | GuessResponse | VerdictResponse | TurnEndResponse | ContextResponse
            | PreviewResponse | PostResponse | PendingResponse | DoneResponse)

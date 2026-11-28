/**
 * The JSON commands between the answer mod and the answer service's Python
 * core, mirroring scripts/service/protocol.py field for field. The mod runs
 * `python3 -I <skill>/scripts/inquisitor.py service` once per command, with
 * one Request on standard input, and reads one Response from standard
 * output. scripts/fixtures/service/ holds an example of each, which both
 * sides' tests read. Change this file, protocol.py and those fixtures together.
 *
 * Terms such as filter, miss, category, place, relay, the two calls and
 * an Igor's run are the inquisitor and answer-service specs' terms
 * (openspec/changes/inquisitor/specs/, or openspec/specs/ once archived).
 *
 * Owned by P0.
 */

export type Surface = 'github' | 'linear' | 'discord'
export type Filter = 1 | 2 | 3 | 4
export type Visibility = 'private' | 'internal' | 'public'

export type LockInfo = {
  session_id: string
  session_name: string
  started: string
  refreshed: string
}

export type Notice = {
  kind:
    | 'check-failed'
    | 'channel-off'
    | 'rate-limit'
    | 'relay-warning'
    | 'no-miss'
    | 'push-failed'
    | 'login'
    | 'lock-lost'
  text: string
}

export type Reply = { author: string; text: string; at: string; url: string }

export type RecordedAnswer = { recorded_in: string; quote: string }

/** The model's suggestion when it judges an agent's question by filters 2 to 4: `filter` is the filter it judged the question fails; `why` is the model's reason. */
export type Suggestion = { filter: 2 | 3 | 4; why: string }

/** One answer a question offers: `label` is the answer's text as shown; `effect` is what choosing it would change, '' for a label-only option. */
export type Option = { label: string; effect: string }

/** A question rephrased after a discussion and accepted by the person: `text` is the rephrased question; `summary`, the discussion in one sentence; `options`, for a question with options, its options as rephrased. */
export type Revision = { text: string; summary: string; options?: Option[] }

/**
 * state: 'open', or absent, for an open question. 'set-aside': the person
 * set it aside for later, and the mod lists it after the open ones.
 * 'pending': the person confirmed an answer that is not yet posted in the
 * question's thread. relay: the bot account that posts the person's
 * answers on the question's surface; absent for a questions-branch
 * question, since nothing is posted for one. revision: the rephrasing
 * carried by the answer the person confirmed for this question, whether
 * posted or kept pending.
 */
export type QuestionView = {
  id: string
  surface: Surface
  asker: 'person' | 'agent' | 'item' | 'questions-branch'
  asked_by: string
  asked_at: string
  url: string
  text: string | null
  item?: number
  concerns?: string
  related?: string
  recorded?: RecordedAnswer
  replies: Reply[]
  has_category: boolean
  new: boolean
  state?: 'open' | 'set-aside' | 'pending'
  suggested?: Suggestion
  relay?: string
  revision?: Revision
}

export type PendingView = { question: string; text: string; why: string }

export type JudgeRequest = {
  message: string
  turn: 1 | 2
  text: string
  needs_place: boolean
  needs_place_sure: boolean
  places: string[]
  defaults: string[]
  hits?: Record<string, unknown>[]
  person_question: boolean
}

/** The fields of record_verdict, the tool the model calls to judge a message, as the model sent them; the core checks each. */
export type VerdictFields = {
  question?: string
  category?: string
  filter?: string
  hit?: number
  place?: string
  place_sure?: string
}

export type PreviewRecord = {
  place: string | null
  visibility: Visibility | null
  more_visible_than?: string
  not_recorded?: string
}

// -- requests ------------------------------------------------------------------

export type OpenRequest = {
  command: 'open'
  session_id: string
  session_name: string
  takeover: boolean
}
export type SessionRequest = {
  command: 'refresh' | 'close' | 'poll' | 'pending.list' | 'setup.status'
  session_id: string
}
export type SetupSaveRequest = {
  command: 'setup.save'
  session_id: string
  login?: string
  config: Record<string, unknown>
}
export type SetupGuessRequest = {
  command: 'setup.guess-repos'
  session_id: string
  surface: 'linear' | 'discord'
  channel: string
}
export type SetupCreateLoreRequest = {
  command: 'setup.create-lore'
  session_id: string
  repository: string
  path: string
  serves: string[]
}
export type VerdictRequest = {
  command: 'judge.verdict'
  session_id: string
  message: string
  turn: 1 | 2
  fields: VerdictFields
  agent_id?: string
}
export type TurnEndRequest = {
  command: 'judge.turn-end'
  session_id: string
  message: string
  turn: 1 | 2
}
export type DiscussionRequest = {
  command: 'discussion.append'
  session_id: string
  question: string
  role: 'person' | 'model'
  text: string
}
/** The mod sends this request when the person sets a question aside for later. The core keeps the question set aside, and each later poll's QuestionView gives it the state 'set-aside', until a post request answering or declining it is sent, whether the post goes out or is kept pending. Nothing else, a reopen included, ends the set-aside. */
export type SetAsideRequest = { command: 'set-aside'; session_id: string; question: string }
export type ContextRequest = { command: 'context'; session_id: string; question: string }
export type ScreenRequest = { command: 'screen.set'; session_id: string; question: string | null }
export type PreviewRequest = {
  command: 'preview'
  session_id: string
  question: string
  action: 'answer' | 'ask' | 'decline' | 'agree' | 'edit'
  text?: string
  place?: string
  reason?: 1 | 2
  filter?: Filter
  recorded_in?: string
  note?: string
  /** With reason 2 and filter 3: "the agent shouldn't have asked"; the core posts nothing and logs a filter 3 miss against the asking agent, and refuses it with any other reason or filter. */
  unasked?: boolean
  /** The rephrasing the person accepted, with action 'answer' only; the core refuses it with any other action. The post carries its `Rephrased question: ` and `Discussion: ` lines. The core keeps the revision, with the answer, only once a post request names this preview, whether the post goes out then or is kept pending; the rephrasing reaches the core no other way. */
  revision?: Revision
}
export type PostRequest = { command: 'post'; session_id: string; preview: string }
export type ReopenRequest = { command: 'reopen'; session_id: string; question: string }

export type Request =
  | OpenRequest
  | SessionRequest
  | SetupSaveRequest
  | SetupGuessRequest
  | SetupCreateLoreRequest
  | VerdictRequest
  | TurnEndRequest
  | DiscussionRequest
  | SetAsideRequest
  | ContextRequest
  | ScreenRequest
  | PreviewRequest
  | PostRequest
  | ReopenRequest

// -- responses -----------------------------------------------------------------

export type ErrorResponse = { version: number; ok: false; error: string; lock_lost?: boolean }
type Ok = { version: number; ok: true }

export type OpenResponse = Ok & {
  status: 'opened' | 'locked' | 'setup'
  lock?: LockInfo
  screen?: string | null
  notices: Notice[]
}
export type RefreshResponse = Ok & { held: boolean }
/**
 * rate_limited_until concerns GitHub alone: while GitHub refuses requests
 * for its rate limit, it holds GitHub's reset time (ISO 8601, UTC), else
 * null. The core skips GitHub until then, keeps polling Linear and Discord,
 * and adds a 'rate-limit' notice to the first poll of each such wait only.
 */
export type PollResponse = Ok & {
  questions: QuestionView[]
  judge: JudgeRequest[]
  notices: Notice[]
  rate_limited_until: string | null
}
export type SetupCheck = {
  surface: Surface | 'login' | 'lore'
  channel?: string
  name: string
  ok: boolean | null
  fix?: string
}
/** A channel that setup offers: `id` is the value inquisitor.json's answer_service section lists under `subscriptions` once subscribed; `name` is shown beside it; `subscribed` says whether it is listed already. */
export type Candidate = { surface: Surface; id: string; name: string; subscribed: boolean }
/** linear_key_command: present only when Linear is configured as a surface and the keychain holds no key for it; the command the person runs in their own terminal to store their Linear key there. */
export type SetupStatusResponse = Ok & {
  complete: boolean
  config: Record<string, unknown>
  checks: SetupCheck[]
  candidates?: Candidate[]
  linear_key_command?: string
}
export type GuessResponse = Ok & { repos: string[] }
export type VerdictResponse = Ok & { accepted: boolean; why?: string }
/** An automatic post the core made: `question` is the id of the question it answers; `url`, the post's URL; `text`, its exact text; `kind`, 'recorded' for a `Recorded answer: ` post or 'inquisitor' for an `Inquisitor: ` post. */
export type PostedItem = { question: string; url: string; text: string; kind: 'recorded' | 'inquisitor' }
export type TurnEndResponse = Ok & {
  next: JudgeRequest | null
  posted: PostedItem[]
  notices: Notice[]
}
export type ContextResponse = Ok & { context: string }
export type PreviewResponse = Ok & {
  id: string
  post: string | null
  record: PreviewRecord
  warnings: string[]
  reaches_run?: string
  reword?: string
}
export type PostResponse = Ok & {
  status: 'posted' | 'pending' | 'held' | 'failed'
  url?: string
  warnings: string[]
  why?: string
}
export type PendingResponse = Ok & { answers: PendingView[] }
export type DoneResponse = Ok

/** The response the core sends for each command, besides ErrorResponse. */
export type ResponseFor = {
  open: OpenResponse
  refresh: RefreshResponse
  close: DoneResponse
  poll: PollResponse
  'pending.list': PendingResponse
  'setup.status': SetupStatusResponse
  'setup.save': SetupStatusResponse
  'setup.guess-repos': GuessResponse
  'setup.create-lore': DoneResponse
  'judge.verdict': VerdictResponse
  'judge.turn-end': TurnEndResponse
  'discussion.append': DoneResponse
  'set-aside': DoneResponse
  context: ContextResponse
  'screen.set': DoneResponse
  preview: PreviewResponse
  post: PostResponse
  reopen: DoneResponse
}

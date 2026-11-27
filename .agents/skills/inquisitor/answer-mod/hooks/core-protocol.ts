/**
 * The JSON commands between the answer mod and the answer service's Python
 * core, mirroring scripts/service/protocol.py field for field. The mod runs
 * `python3 -I <skill>/scripts/inquisitor.py service` once per command, with
 * one Request on standard input, and reads one Response from standard
 * output. scripts/fixtures/service/ holds an example of each, which both
 * sides' tests read. Change this file, protocol.py and those fixtures together.
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
  linear_key?: string
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
export type SetupStatusResponse = Ok & {
  complete: boolean
  config: Record<string, unknown>
  checks: SetupCheck[]
}
export type GuessResponse = Ok & { repos: string[] }
export type VerdictResponse = Ok & { accepted: boolean; why?: string }
export type TurnEndResponse = Ok & {
  next: JudgeRequest | null
  posted: string[]
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
  context: ContextResponse
  'screen.set': DoneResponse
  preview: PreviewResponse
  post: PostResponse
  reopen: DoneResponse
}

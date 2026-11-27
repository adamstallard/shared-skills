// The core's shapes this file, the mod's state contract, stores, as hooks/core-protocol.ts defines
// them. A contract holds no import, so they are written out here; every write
// of a value from the core to `$.state` type-checks against them.

export type Surface = 'github' | 'linear' | 'discord'
export type Visibility = 'private' | 'internal' | 'public'
export type LockInfo = { session_id: string; session_name: string; started: string; refreshed: string }
export type CoreReply = { author: string; text: string; at: string; url: string }
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
  replies: CoreReply[]
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
export type PreviewRecord = { place: string | null; visibility: Visibility | null; more_visible_than?: string; not_recorded?: string }
export type PreviewResponse = {
  version: number
  ok: true
  id: string
  post: string | null
  record: PreviewRecord
  warnings: string[]
  reaches_run?: string
  reword?: string
}
export type SetupCheck = { surface: Surface | 'login' | 'lore'; channel?: string; name: string; ok: boolean | null; fix?: string }
export type SetupStatusResponse = { version: number; ok: true; complete: boolean; config: Record<string, unknown>; checks: SetupCheck[] }

/** The inquisitor's filters: 1 already answered, 2 can wait, 3 only one option has merit, 4 cheap to reverse. */
export type Filter = 1 | 2 | 3 | 4

/**
 * Why the person declines a question: 1, nothing to answer (the
 * conversation is over, or it isn't a question); 2, the inquisitor should
 * have handled it, on an agent's question only.
 */
export type DeclineReason = 1 | 2

/**
 * The question the person is declining, and where they are in it: `reason`
 * while they pick why; for reason 2, `filter` while they pick the filter
 * that should have stopped it, `place` while they give where filter 1's
 * answer is recorded, and `post` while the reply is previewed. Nothing is
 * recorded or posted until the last Enter.
 */
export type Declining =
  | { id: string; stage: 'reason' }
  | { id: string; stage: 'filter' }
  | { id: string; stage: 'place' }
  | { id: string; stage: 'post'; filter: Filter; place?: string }

/** What was done with a question here, by the person or, for `recorded` with `auto`, by the service itself. */
export type Answer = {
  /**
   * What the person gave, without a prefix: the answer, for `wait` the
   * question sent back, for `handled` the note for the miss; empty for a
   * deferral, a decline and an automatic post.
   */
  text: string
  /**
   * `answer` is relayed or logged; `defer` keeps it open, behind the new
   * ones; `wait` asked the asker; `wont` declined with nothing posted;
   * `handled` declined for the inquisitor, the chosen filter's reply posted;
   * `recorded` the recorded answer agreed to, or, with `auto`, posted by the
   * service by itself.
   */
  kind: 'answer' | 'defer' | 'wait' | 'wont' | 'recorded' | 'handled'
  /** True once the person edited the post. */
  edited?: true
  /** For `wont`: why. */
  reason?: DeclineReason
  /** For `handled`: the filter picked. */
  filter?: Filter
  /** For `recorded`: the service posted it by itself, with no word of the person's. */
  auto?: true
  /** What the core says was posted, prefix and `Re: ` line included; absent when nothing posted. */
  post?: string
  /** Where the post is. */
  url?: string
  /** Why the answer waits as pending instead of posted (its channel is off or refused it). */
  pending?: string
}

/** One message in a question's discussion: the person's, the model's reply, or what failed. */
export type Turn = { who: 'you' | 'model' | 'error'; text: string }

/** A question rewritten after a discussion. */
export type Revision = {
  text: string
  context: string
  options?: { label: string; effect: string }[]
  /** One line saying what the discussion settled. */
  summary: string
}

/** One row placed in the transcript for something done with a question. */
export type PlacedRow = {
  id: string
  verb: 'answered' | 'logged' | 'asked' | 'wont' | 'recorded' | 'inquisitor' | 'edited' | 'pending'
  /** What was posted or logged; for `wont`, the reason in words. */
  text: string
  posts: boolean
  /** The post's URL, once it landed. */
  url?: string
}

/**
 * Where the answer service stands in this session: not opened (no marker,
 * or before the opening), `setup` in place of the queue, `locked` by
 * another session, `tools` kept closed by a tool outside its set, `open`,
 * `lost` when another session took it over, `closed` by the person.
 */
export type ServiceState =
  | { status: 'none' }
  | { status: 'opening' }
  | { status: 'setup'; setup: SetupStatusResponse | null; back: boolean; login?: string }
  | { status: 'locked'; lock: LockInfo | null }
  | { status: 'tools'; tools: string[] }
  | { status: 'open' }
  | { status: 'lost' }
  | { status: 'closed' }

/** A preview the core made, and the request it answers, as a key. */
export type Previewed = { key: string; res: PreviewResponse }

/** What the person has been shown of a question's replies: how many, and from which on they are new. */
export type Seen = { shown: number; fresh?: number }

/** The judging turn under way: the message, its turn, and the turn id once it started. */
export type Judging = { req: JudgeRequest; text: string; turnId?: string }

declare module 'claude-code' {
  interface PluginState {
    'inquisitor-answer-mod': {
      /** True in a session the answer launcher started: its environment holds the answer marker. */
      marker: boolean
      /** The answer service's state in this session. */
      service: ServiceState
      /** The questions the polls show, by id. */
      questions: Record<string, QuestionView>
      /** Question ids in queue order, oldest asked first. */
      order: string[]
      /** Index of the question on screen in `order`; its length is the summary. */
      cursor: number
      /** What was done here with each question, by id. */
      answers: Record<string, Answer>
      /** The prompt box's text while the band is open, so the band can preview what Enter would do. */
      prompt: string
      /** The last thing done, or a notice; null once acted past. */
      flash: string | null
      /** The question whose discussion is open, or null. */
      talking: string | null
      /** Each question's discussion, by id. */
      talks: Record<string, Turn[]>
      /** Work under way, by question id. */
      thinking: Record<string, 'reply' | 'rephrase' | 'draft'>
      /** Questions rephrased after a discussion, by id. */
      rephrased: Record<string, Revision>
      /** True for a rephrased question while its original is shown instead. */
      original: Record<string, boolean>
      /** Discussion messages whose turn has not started, oldest first. */
      awaiting: { id: string; text: string }[]
      /** The question each running discussion turn answers, by turn id. */
      replyTurns: Record<string, string>
      /** The post being edited in the prompt box, by question id. */
      editing: Record<string, true>
      /** Questions whose clarifying question to the asker is being written. */
      asking: Record<string, true>
      /** The question being declined, and the stage; null when none. */
      declining: Declining | null
      /** What the person has been shown of each question's replies, by id. */
      seen: Record<string, Seen>
      /** The question whose replies and record are shown in full, and the page; null otherwise. */
      viewing: { id: string; page: number } | null
      /** Rows placed in the transcript, by row id. */
      rows: Record<string, PlacedRow>
      /** Placed rows whose post has not landed yet, by row id. */
      posting: Record<string, true>
      /** Questions that arrived while the band was open and have not been shown since, by id. */
      marked: Record<string, true>
      /** The latest preview the core made. */
      previewed: Previewed | null
      /** The question a poll took from under the cursor, until the person next moves or presses Enter. */
      displaced: string | null
      /** The place the person picked for each question's record, by id. */
      places: Record<string, string>
      /** True while the person picks another place for the record of the question on screen. */
      picking: boolean
      /** Every place the code has listed for a record: the subscribed and lore repositories. */
      knownPlaces: string[]
      /** Answers kept pending, from the core. */
      pending: PendingView[]
      /** Messages waiting for the model's judgement, oldest first. */
      judgeQueue: JudgeRequest[]
      /** The judging turn under way, or null. */
      judging: Judging | null
      /** The main conversation's running turn, so a tool joining can abort it. */
      turn: string | null
      /** Each surface's relay identity, as the configuration names it. */
      relays: Record<string, string>
      /** When the core polls GitHub again after its rate-limit refusal, or null; the other channels go on meanwhile. */
      rateLimitedUntil: string | null
    }
  }
}

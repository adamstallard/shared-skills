/**
 * Why Adam won't answer a question: 1, the conversation is over; 2, not a
 * question (picked up by mistake); 3, the inquisitor should have handled it,
 * and he answers for it.
 */
export type WontReason = 1 | 2 | 3

/** The inquisitor's filters: 1 already answered, 2 can wait, 3 only one option has merit, 4 cheap to reverse. */
export type Filter = 1 | 2 | 3 | 4

/**
 * The question Adam is declining to answer, and where he is in it: `reason`
 * while he picks why; for reason 3, `filter` while he picks which filter
 * should have stopped it, `place` while he gives where filter 1's answer is
 * recorded, and `post` while the reply he is posting for the inquisitor is
 * previewed (with the place, for filter 1). Nothing is recorded or posted
 * until the last Enter; going back steps back, and from the first two
 * stages keeps the question open.
 */
export type Declining =
  | { id: string; stage: 'reason' }
  | { id: string; stage: 'filter' }
  | { id: string; stage: 'place' }
  | { id: string; stage: 'post'; filter: Filter; place?: string }

/** What was done with a question, by Adam or, for `recorded` and `handled`, by the session itself. */
export type Answer = {
  /**
   * The posted text, without its prefix: the answer, for `wait` the
   * clarifying question sent back, for `recorded` the citation, for
   * `handled` the filter's action; empty for a deferral and a won't-answer.
   */
  text: string
  /**
   * `answer` is relayed; `defer` keeps it open, behind the new ones; `wait`
   * sent the asker a clarifying question, and it returns when they reply;
   * `wont` posts nothing and closes it, with a reason. The session's own:
   * `recorded`, answered for Adam from a recorded answer with authority
   * (filter 1), posted as "Recorded answer: "; `handled`, an agent's
   * question that clearly fails filter 2, 3 or 4, replied to with that
   * filter's action, posted as "Inquisitor: ". `handled` with `chosen` is
   * Adam's won't-answer reason 3: he answered for the inquisitor with the
   * filter he chose (filter 1 as "Recorded answer: " and where it is
   * recorded), and the question is closed.
   */
  kind: 'answer' | 'defer' | 'wait' | 'wont' | 'recorded' | 'handled'
  /** True once the post was edited after it went out; an edited post is Adam's, prefixed "User says: ". */
  edited?: true
  /** For `wont`: why. (Reason 3 posts, so it ends as `handled` with `chosen`.) */
  reason?: 1 | 2
  /** For `handled`: the filter whose reply was posted. */
  filter?: Filter
  /**
   * For `handled`: true when Adam chose it (won't-answer reason 3) rather than
   * the session. For `recorded`: Adam relayed filter 1's recorded answer,
   * shown to him rather than posted by itself.
   */
  chosen?: true
  /** For a `handled` Adam chose: the note he typed with it, the miss's "what was said". */
  said?: string
  /** For an answer Adam relayed over the session's own post: that post, prefix included. */
  over?: string
  /**
   * For `answer`: read from the thread, not posted here. The relay's own
   * reply was there already, posted from another machine.
   */
  elsewhere?: true
}

/**
 * What the session knows of a question's thread from its last read. Prototype
 * only: the replies are the question's made-up ones; reading reveals them.
 */
export type ThreadSeen = {
  /** Clock time of the last read. A question on screen is read again once this is about a minute old. */
  readAt: number
  /** How many replies the person has been shown. A post finds more since: it stops, and shows them. */
  shown: number
  /** Replies from this index on were found by the read before a post: marked new. */
  fresh?: number
  /** Prototype only: the made-up late reply has landed in the thread. */
  late?: true
}

/**
 * Where the replies since the question and filter 1's recorded answer go:
 * `beside` the choices, in the right column, or `under` the question, in the
 * left. Prototype only: two designs to compare, switched with /answer layout.
 */
export type Layout = 'beside' | 'under'

/** One message in a question's discussion. */
export type Turn = {
  /** `you` is the person; `model` the reply its turn ended with; `error` what failed: a turn with no reply, a rephrasing or a draft. */
  who: 'you' | 'model' | 'error'
  text: string
}

/** A question rewritten after a discussion, or by its asker after a clarifying question. */
export type Revision = {
  text: string
  /** One or two sentences of background; empty when none is needed. */
  context: string
  /** For an agent's question: revised options, the recommended first. */
  options?: { label: string; effect: string }[]
  /** One line saying what the discussion settled, logged with the answer. */
  summary: string
}

/** The asker's reply to a clarifying question, and what it changed. */
export type Returned = {
  /** The clarifying question that was sent. */
  asked: string
  /** What the asker replied. */
  reply: string
  /** For an agent's question, its revised question and options. */
  revised?: Revision
}

declare module 'claude-code' {
  interface PluginState {
    'answer-session': {
      /** Index of the question on screen, in queue order. */
      cursor: number
      /** Answers, deferrals and questions sent back, by question id. */
      answers: Record<string, Answer>
      /**
       * The prompt box's text while the session is open, kept so the band can
       * preview what Enter would do with it.
       */
      prompt: string
      /** The last relay, confirmed on the next screen; null once acted past. */
      flash: string | null
      /** The question whose discussion is open, or null on the question view. */
      talking: string | null
      /**
       * Each question's discussion: the messages Adam sent the session's model
       * and the replies its turns ended with, read by a rephrasing and a draft.
       */
      talks: Record<string, Turn[]>
      /**
       * Work under way, by question id: `reply`, a discussion message's turn
       * in the session; `rephrase` and `draft`, a model call of the band's own.
       */
      thinking: Record<string, 'reply' | 'rephrase' | 'draft'>
      /** Questions rephrased after a discussion, by id. */
      rephrased: Record<string, Revision>
      /** True for a changed question while its original is shown instead. */
      original: Record<string, boolean>
      /**
       * Discussion messages that reached the model and whose turn has not
       * started, oldest first: the question each is about, and its text.
       */
      awaiting: { id: string; text: string }[]
      /** The question each running discussion turn answers, by turn id. */
      replyTurns: Record<string, string>
      /** The relayed answer or question to the asker being edited in the prompt box, by question id. */
      editing: Record<string, true>
      /** Questions whose clarifying question to the asker is being written in the prompt box. */
      asking: Record<string, true>
      /** The question Adam is declining to answer, and the stage he is at; null when none. */
      declining: Declining | null
      /** Askers' replies to clarifying questions, by question id. */
      returned: Record<string, Returned>
      /** Each question's thread as last read, by question id. */
      threads: Record<string, ThreadSeen>
      /** Questions whose thread is being read, by id. */
      reading: Record<string, true>
      /** The question whose replies and record are shown in full, and the page; null on the question view. */
      viewing: { id: string; page: number } | null
      /** Where replies and the recorded answer go. */
      layout: Layout
      /**
       * True while the answer session is open: the band above the prompt
       * shows it, and Enter in the prompt box acts in it (only a discussion
       * message reaches the model, its question attached). /answer, q and the
       * band's close button flip it.
       */
      isOpen: boolean
    }
  }
}

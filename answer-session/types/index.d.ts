/** What was done with a question. */
export type Answer = {
  /**
   * The relayed text, without the "User says: " prefix: the answer, or for
   * `wait` the clarifying question sent back; empty for a deferral.
   */
  text: string
  /**
   * `answer` is relayed; `defer` keeps it open, behind the new ones; `wait`
   * sent the asker a clarifying question, and it returns when they reply.
   */
  kind: 'answer' | 'defer' | 'wait'
}

/** One message in a question's discussion. */
export type Turn = {
  /** `you` is the person; `model` the session's model; `error` a call that gave no reply. */
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
       * The prompt box's text while the pane is open, kept so the pane can
       * preview what Enter would do with it.
       */
      prompt: string
      /** The last relay, confirmed on the next screen; null once acted past. */
      flash: string | null
      /** The question whose discussion is open, or null on the question view. */
      talking: string | null
      /** Each question's discussion, kept so reopening it continues it. */
      talks: Record<string, Turn[]>
      /** A model call under way, by question id: a reply, a rephrasing, a draft. */
      thinking: Record<string, 'reply' | 'rephrase' | 'draft'>
      /** Questions rephrased after a discussion, by id. */
      rephrased: Record<string, Revision>
      /** True for a changed question while its original is shown instead. */
      original: Record<string, boolean>
      /** How many lines the discussion is scrolled up from its newest. */
      talkScroll: number
      /** Questions whose clarifying question to the asker is being written in the prompt box. */
      asking: Record<string, true>
      /** Askers' replies to clarifying questions, by question id. */
      returned: Record<string, Returned>
      /**
       * True from an open of the pane until its close: the conversation and
       * the prompt's chrome draw nothing while it is up, so the pane is all
       * there is to see. Checked against the open panes before hiding.
       */
      immersive: boolean
      /** True while a launch-time open waits for room and the status line says so. */
      placing: boolean
    }
  }
}

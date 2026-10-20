import { atom, read, update } from 'claude-code'
import type { EngineInterface, ModelCompleteResult, Register } from 'claude-code'

import type { Answer, Returned, Revision, Staged, Turn } from '../types'

// Prototype only: the questions are fixed examples, and an answer is kept in
// the session's state instead of being posted by the relay account.

type Surface = 'github' | 'linear' | 'discord'

type Option = { label: string; effect: string }

type Question = {
  id: string
  surface: Surface
  /** Where it was asked, as a reader names the place. */
  where: string
  link: string
  asker: { name: string; kind: 'agent' | 'human'; via?: string; replyTo?: string }
  age: string
  text: string
  /** Background the asker gave; for a reply, the message it answers. */
  context?: string
  /** Agent questions only: the recommended answer first. */
  options?: Option[]
  /** An earlier decision the question touches. */
  related?: string
  /** A decision that may already answer it, and a reply citing it. */
  answered?: { decision: string; cite: string }
  relayAs: string
}

const QUESTIONS: Question[] = [
  {
    id: 'igor-216-scope',
    surface: 'github',
    where: 'adamstallard/igor #216',
    link: 'https://github.com/adamstallard/igor/pull/216',
    asker: { name: 'claude', kind: 'agent', via: 'the inquisitor' },
    age: '12m',
    text:
      "During a run, should the inquisitor's first filter hide questions-branch files about projects the role doesn't work on, as it hides lore entries outside the role's scope?",
    context:
      "The scope filter covers lore entries only. Question files on the lore repository's questions branch can be about any project.",
    options: [
      { label: "Yes, filter them by the role's scope", effect: "A worker never sees another project's questions." },
      { label: 'No, show them as input', effect: "Workers may read other projects' questions." },
    ],
    related: '#216 decision 3: scope is a hard filter',
    relayAs: 'adam-relay[bot]',
  },
  {
    id: 'eng-412',
    surface: 'linear',
    where: 'ENG-412 · Onboarding flag',
    link: 'https://linear.app/example/issue/ENG-412',
    asker: { name: 'Maya Ortiz', kind: 'human' },
    age: '22m',
    text: 'Can we ship the onboarding flag to 10% on Friday, or should we wait for the metrics review on Monday?',
    context: 'QA signed off this morning. Waiting for the review adds three days.',
    relayAs: 'adam-relay (Linear app)',
  },
  {
    id: 'igor-216-visibility',
    surface: 'github',
    where: 'adamstallard/igor #216',
    link: 'https://github.com/adamstallard/igor/pull/216',
    asker: { name: 'claude', kind: 'agent', via: 'the inquisitor' },
    age: '14m',
    text:
      "igor's publicStore setting can't tell an internal lore repository from a private one. How should the Igor learn its visibility?",
    options: [
      { label: 'Ask GitHub at startup', effect: "One API call, exact visibility, used by #212's startup check." },
      {
        label: 'Treat publicStore: false as internal',
        effect: "No API call; private items' citations are never pushed to a non-public lore repository.",
      },
    ],
    related: '#212: lore is no more visible than the repositories it serves',
    relayAs: 'adam-relay[bot]',
  },
  {
    id: 'lore-backoff',
    surface: 'discord',
    where: '#igor-dev',
    link: 'https://discord.com/channels/example/igor-dev',
    asker: { name: 'Igor (scribe)', kind: 'agent', via: 'its inquisitor role' },
    age: '1h',
    text: 'Two lore entries disagree on retry backoff. Keep "exponential, capped at 30s" and retire "fixed 5s"?',
    context:
      'retry-backoff-exponential (active, 4 supports) and retry-fixed-5s (active, 1 support) both fire on HTTP client changes.',
    options: [
      { label: 'Keep exponential, retire fixed', effect: 'retry-fixed-5s is deprecated in one lore pull request.' },
      { label: 'Keep both, narrow the fixed one', effect: 'retry-fixed-5s fires only for the payments client.' },
      { label: 'Retire both', effect: 'Workers get no retry guidance.' },
    ],
    relayAs: 'adam-relay#4127',
  },
  {
    id: 'igor-216-jlee',
    surface: 'github',
    where: 'adamstallard/igor #216',
    link: 'https://github.com/adamstallard/igor/pull/216',
    asker: { name: 'jlee', kind: 'human' },
    age: '2h',
    text: 'Why does a citation carry an opaque run id rather than the item number?',
    context: 'Review comment on openspec/changes/lore-search/specs/lore-firing/spec.md',
    answered: {
      decision: "#216 decision 10: the run id links to the run's ledger row",
      cite: "See decision 10 in #216: the run id links to the run's ledger row, which an item number cannot.",
    },
    relayAs: 'adam-relay[bot]',
  },
  {
    id: 'igor-216-citation-time',
    surface: 'github',
    where: 'adamstallard/igor #216',
    link: 'https://github.com/adamstallard/igor/pull/216',
    asker: { name: 'claude', kind: 'agent', via: 'the inquisitor' },
    age: '15m',
    text: 'Should a citation be checked against the lore store as the run read it, or at push time?',
    context: '#208 lets an entry be deprecated mid-run.',
    options: [
      { label: 'As the run read it', effect: 'The citation records what the run actually used.' },
      { label: 'At push time', effect: 'An entry deprecated mid-run gets no citation.' },
    ],
    relayAs: 'adam-relay[bot]',
  },
  {
    id: 'ops-staging',
    surface: 'discord',
    where: '#ops',
    link: 'https://discord.com/channels/example/ops',
    asker: { name: 'Sam K', kind: 'human', replyTo: 'adam-relay#4127' },
    age: '3h',
    text: 'Thanks. Does that also apply to the staging cluster?',
    context: 'User says: freeze deploys to prod until the migration finishes.',
    relayAs: 'adam-relay#4127',
  },
  {
    id: 'igor-216-sensitive',
    surface: 'github',
    where: 'adamstallard/igor #216',
    link: 'https://github.com/adamstallard/igor/pull/216',
    asker: { name: 'claude', kind: 'agent', via: 'the inquisitor' },
    age: '16m',
    text:
      "Is it acceptable that a refused run that met a sensitive question keeps only the limit and reset time, losing the provider's text?",
    context:
      "Decision 13 withholds free text from such runs. The provider's reply would help learn where it puts its reset time.",
    options: [
      { label: 'Yes, accept the loss', effect: 'Sensitive runs stay free of text.' },
      { label: "Keep the provider's text, secret-scanned", effect: 'More data, and some risk.' },
    ],
    relayAs: 'adam-relay[bot]',
  },
]

// Prototype only: what each asker replies to a clarifying question, after
// SIM_REPLY_MS. The real skill hears the reply on the question's own thread.
const SIM_REPLY_MS = 25_000
const SIM_REPLIES: Record<string, { reply: string; revised?: Omit<Revision, 'summary'> }> = {
  'igor-216-scope': {
    reply:
      "Each file on the questions branch has a project field in its front matter, so the same scope check that drops lore entries can drop them. They stay on the branch; a worker's search just never returns them.",
    revised: {
      text: "Should the first filter drop questions-branch files whose project field is outside the role's scope, as it drops out-of-scope lore entries?",
      context: 'The files stay on the branch either way; only what a worker sees changes.',
      options: [
        { label: 'Yes, apply the same scope check', effect: "Workers see only their own projects' questions." },
        { label: 'No, return them marked out of scope', effect: "Workers can read them, flagged as another project's." },
      ],
    },
  },
  'igor-216-visibility': {
    reply:
      "GitHub's repository API reports internal and private exactly, and the Igor's token can already read repository metadata. The cost is one call at startup and a failure mode if GitHub is down then.",
    revised: {
      text: "Should the Igor read its lore repository's visibility from GitHub at startup, or treat publicStore: false as internal?",
      context: 'Reading it needs no new permission. Startup would fail if GitHub is unreachable.',
      options: [
        { label: 'Read it from GitHub at startup', effect: "Exact visibility; startup depends on GitHub's API." },
        { label: 'Treat publicStore: false as internal', effect: 'No API call; citations of private items stay out of non-public stores.' },
      ],
    },
  },
  'igor-216-citation-time': {
    reply:
      'Deprecation mid-run happens about once a week. A citation checked at push time would silently drop the entry the run actually relied on.',
    revised: {
      text: 'Should a citation name the lore entry the run read, even if that entry was deprecated before the push?',
      context: '',
      options: [
        { label: 'Yes, cite what the run read', effect: 'Citations stay true to the run; some name deprecated entries.' },
        { label: 'No, cite only entries live at push time', effect: 'Citations of entries deprecated mid-run are dropped.' },
      ],
    },
  },
  'igor-216-sensitive': {
    reply:
      "The provider's text is usually one line: the limit name and a reset time in its own format. Secret-scanning it would catch tokens but not a pasted prompt fragment.",
  },
  'lore-backoff': {
    reply:
      'The fixed 5s entry came from the payments client, whose upstream rejects bursts. Nothing else depends on it.',
    revised: {
      text: 'Retire the general "fixed 5s" lore entry, keeping fixed backoff only for the payments client?',
      context: 'The exponential entry would apply everywhere else.',
      options: [
        { label: 'Yes, narrow it to payments', effect: 'One entry for payments, exponential everywhere else.' },
        { label: 'Retire it entirely', effect: 'The payments client falls back to exponential.' },
      ],
    },
  },
  'eng-412': {
    reply:
      "Friday's 10% is new sign-ups only, and we can switch it off in minutes. The Monday review is about the conversion metric, not safety.",
  },
  'igor-216-jlee': {
    reply: "I meant the queue's item number, like #14. I hadn't seen decision 10. Is the ledger row public?",
  },
  'ops-staging': {
    reply: "Staging has its own migration tomorrow. I'm asking whether we can deploy there today.",
  },
}

const SURFACE_NAME: Record<Surface, string> = { github: 'GitHub', linear: 'Linear', discord: 'Discord' }

// One accent; the rest is weight, dimness and space. Theme keys, so the
// palette follows the person's theme.
const ACCENT = 'suggestion'
const DONE = 'success'
const LATER = 'warning'
const RULE = 'subtle'

const PANE = 'answer-session'
const PREFIX = 'User says: '
const SPEAKER = 9
const cursorAtom = atom({ plugin: 'answer-session', key: 'cursor' } as const, 0)
const answersAtom = atom({ plugin: 'answer-session', key: 'answers' } as const, {} as Record<string, Answer>)
const stagedAtom = atom({ plugin: 'answer-session', key: 'staged' } as const, {} as Record<string, Staged>)
const draftsAtom = atom({ plugin: 'answer-session', key: 'drafts' } as const, {} as Record<string, string>)
const seedsAtom = atom({ plugin: 'answer-session', key: 'seeds' } as const, {} as Record<string, string>)
const flashAtom = atom({ plugin: 'answer-session', key: 'flash' } as const, null as string | null)
const talkingAtom = atom({ plugin: 'answer-session', key: 'talking' } as const, null as string | null)
const talksAtom = atom({ plugin: 'answer-session', key: 'talks' } as const, {} as Record<string, Turn[]>)
const thinkingAtom = atom(
  { plugin: 'answer-session', key: 'thinking' } as const,
  {} as Record<string, 'reply' | 'rephrase' | 'draft'>,
)
const rephrasedAtom = atom({ plugin: 'answer-session', key: 'rephrased' } as const, {} as Record<string, Revision>)
const originalAtom = atom({ plugin: 'answer-session', key: 'original' } as const, {} as Record<string, boolean>)
const talkScrollAtom = atom({ plugin: 'answer-session', key: 'talkScroll' } as const, 0)
const askingAtom = atom(
  { plugin: 'answer-session', key: 'asking' } as const,
  {} as Record<string, { seed: string; text: string }>,
)
const returnedAtom = atom({ plugin: 'answer-session', key: 'returned' } as const, {} as Record<string, Returned>)
const immersiveAtom = atom({ plugin: 'answer-session', key: 'immersive' } as const, false)
const placingAtom = atom({ plugin: 'answer-session', key: 'placing' } as const, false)

/** Breaks `text` into lines of at most `width` cells, at spaces where it can. */
function wrap(text: string, width: number): string[] {
  const lines: string[] = []
  let line = ''
  for (const word of text.split(/\s+/).filter(Boolean)) {
    let rest = word
    while (rest.length > width) {
      if (line) lines.push(line)
      lines.push(rest.slice(0, width))
      rest = rest.slice(width)
      line = ''
    }
    if (!line) line = rest
    else if (line.length + 1 + rest.length <= width) line += ' ' + rest
    else {
      lines.push(line)
      line = rest
    }
  }
  if (line || lines.length === 0) lines.push(line)
  return lines
}

/** Wraps a message paragraph by paragraph; a "- " item hangs under its dash. */
function wrapMessage(text: string, width: number): string[] {
  const out: string[] = []
  let wasItem = false
  for (const para of text.split(/\n+/).map(p => p.trim()).filter(Boolean)) {
    const item = /^[-*•] /.test(para)
    // A blank line between paragraphs; a list's items stay together.
    if (out.length && !(item && wasItem)) out.push('')
    wasItem = item
    const lines = wrap(item ? para.slice(2) : para, item ? width - 2 : width)
    out.push(...lines.map((line, i) => (item ? (i === 0 ? '- ' : '  ') + line : line)))
  }
  return out.length ? out : ['']
}

/** A question as it now stands: rephrased after a discussion, revised by its asker, or as asked. */
function view(base: Question, rephrased?: Revision, returned?: Returned, showOriginal?: boolean): Question {
  const revision = rephrased ?? returned?.revised
  if (!revision || showOriginal) return base
  return {
    ...base,
    text: revision.text,
    context: revision.context || base.context,
    options: base.options && revision.options?.length ? revision.options : base.options,
  }
}

/** The text the relay posts for a staged answer, without its prefix. */
function stagedText(q: Question, staged: Staged | undefined, draft: string): string | undefined {
  if (!staged) return undefined
  if (staged.kind === 'option') return q.options?.[staged.index]?.label
  return draft.trim() || undefined
}

/** The first question after `from` with nothing done to it, or the summary's index. */
function nextFresh(from: number, answers: Record<string, Answer>): number {
  for (let step = 1; step <= QUESTIONS.length; step++) {
    const i = (from + step) % QUESTIONS.length
    if (!answers[QUESTIONS[i]!.id]) return i
  }
  return QUESTIONS.length
}

/** The key the focus ring starts on for a question: the recommendation, or the reply field. */
function landingKey(q: Question): string {
  return q.options ? `opt:${q.id}:0` : `field:${q.id}`
}

/** Everything the model is told about the question it helps with. */
function systemPrompt(q: Question, returned?: Returned): string {
  const who =
    q.asker.kind === 'agent'
      ? `${q.asker.name}, an agent asking through ${q.asker.via ?? 'the inquisitor'}`
      : `${q.asker.name}, a person`
  const lines = [
    "You are helping Adam think through one question that was relayed to him in his answer session. He will answer it himself. Your job is to help him understand it and work out what he wants, not to answer it for him.",
    '',
    `The question, asked on ${SURFACE_NAME[q.surface]} in ${q.where} by ${who}, ${q.age} ago:`,
    `"${q.text}"`,
  ]
  if (q.context) lines.push(`Context the asker gave: ${q.context}`)
  if (q.asker.replyTo) lines.push(`It replies to a message Adam's relay account (${q.asker.replyTo}) posted earlier.`)
  if (q.options) {
    lines.push('', "The answers offered, the asker's recommendation first, each with what it would change:")
    q.options.forEach((o, i) => lines.push(`${i + 1}. ${o.label}${i === 0 ? ' (recommended)' : ''}: ${o.effect}`))
  } else {
    lines.push('', 'It is a free-form question from a person: Adam will write the reply himself.')
  }
  if (q.related) lines.push(`Related earlier decision: ${q.related}`)
  if (q.answered) lines.push(`Possibly answered already by: ${q.answered.decision}`)
  if (returned) lines.push('', `Adam asked the asker: "${returned.asked}"`, `They replied: "${returned.reply}"`)
  lines.push(
    '',
    'How to help:',
    '- Explain what is being asked and why it matters, in plain words.',
    '- Lay out the trade-offs and what each answer would change.',
    '- When what Adam wants is unclear, ask him one short question back.',
    '- Do not choose for him. If he asks which you would pick, say which way the trade-offs lean and why, and leave the choice to him.',
    "- Say when you do not know something (the code, the asker's intent) rather than guess.",
    'Write plain text for a terminal: short paragraphs, under about 120 words, no headings, no bold or italics. A simple "- " list is fine.',
  )
  return lines.join('\n')
}

/** The discussion so far, as the one user message a completion takes. */
function transcript(turns: Turn[]): string {
  return turns
    .filter(t => t.who !== 'error')
    .map(t => `${t.who === 'you' ? 'Adam' : 'You'}: ${t.text}`)
    .join('\n\n')
}

/** Reads the rephrasing the model returned as JSON, or undefined when it is not usable. */
function parseRevision(text: string, hasOptions: boolean): Revision | undefined {
  const start = text.indexOf('{')
  const end = text.lastIndexOf('}')
  if (start < 0 || end <= start) return undefined
  let raw: unknown
  try {
    raw = JSON.parse(text.slice(start, end + 1))
  } catch {
    return undefined
  }
  if (typeof raw !== 'object' || raw === null) return undefined
  const r = raw as Record<string, unknown>
  if (typeof r.question !== 'string' || !r.question.trim()) return undefined
  const options = Array.isArray(r.options)
    ? r.options
        .filter((o): o is { label: string; effect: string } => {
          const one = o as Record<string, unknown>
          return typeof one?.label === 'string' && typeof one?.effect === 'string'
        })
        .slice(0, 4)
    : []
  if (hasOptions && options.length < 2) return undefined
  return {
    text: r.question.trim(),
    context: typeof r.context === 'string' ? r.context.trim() : '',
    options: hasOptions ? options : undefined,
    summary: typeof r.summary === 'string' ? r.summary.trim() : '',
  }
}

/** Why a completion gave no text, in a few words. */
function why(r: ModelCompleteResult): string {
  if (r.isAnswered) return ''
  if (r.reason === 'api-error') return `the API answered ${r.status ?? 'with an error'}`
  if (r.reason === 'aborted') return 'the call timed out'
  return 'the reply was empty'
}

/** A record without one key. */
function without<T>(record: Record<string, T>, id: string): Record<string, T> {
  const { [id]: _gone, ...rest } = record
  return rest
}

/** Prototype only: the asker's simulated reply arrives; the question is new again. */
async function deliverReply($: EngineInterface, id: string): Promise<void> {
  const one = QUESTIONS.find(x => x.id === id)
  if (!one) return
  let asked = ''
  await update($, answersAtom, a => {
    const was = a[id]
    if (was?.kind !== 'wait') return a
    asked = was.text
    return without(a, id)
  })
  if (!asked) return
  const sim = SIM_REPLIES[id]
  const returned: Returned = {
    asked,
    reply: sim?.reply ?? 'Thanks for asking. My question stands as written.',
    revised: one.options && sim?.revised ? { ...sim.revised, summary: '' } : undefined,
  }
  await update($, returnedAtom, x => ({ ...x, [id]: returned }))
  await update($, rephrasedAtom, x => without(x, id))
  await update($, originalAtom, x => without(x, id))
  $.ui.toast(`${one.asker.name} replied: their question is back in the queue.`)
}

// `/tui fullscreen` restarts the process and resumes the session. `$.state`
// lives in the process, so what the answer session needs to come back as it
// was goes to `$.store`, which persists, under one key read at the next start.
const RESUME_KEY = 'reopen-after-restart'
// A record older than this is from a restart that never happened: dropped.
const RESUME_WINDOW_MS = 120_000

type ResumeRecord = {
  sessionId: string
  cwd: string
  at: number
  cursor: number
  answers: Record<string, Answer>
  talks: Record<string, Turn[]>
  rephrased: Record<string, Revision>
  original: Record<string, boolean>
  returned: Record<string, Returned>
}

/** Keeps the open answer session for the process the restart starts. */
async function saveForRestart($: EngineInterface): Promise<void> {
  const record: ResumeRecord = {
    sessionId: await $.session.id(),
    cwd: await $.session.cwd(),
    at: await $.clock.now(),
    cursor: await read($, cursorAtom),
    answers: await read($, answersAtom),
    talks: await read($, talksAtom),
    rephrased: await read($, rephrasedAtom),
    original: await read($, originalAtom),
    returned: await read($, returnedAtom),
  }
  await $.store.set(RESUME_KEY, record)
}

/**
 * At a session's start: the record a restart left, if it is this session's
 * (the same id, or the same directory within the window), restored; always
 * removed, so it reopens nothing twice and nothing in another session.
 */
async function takeRestart($: EngineInterface, cwd: string): Promise<ResumeRecord | undefined> {
  const raw = await $.store.get(RESUME_KEY)
  if (raw === undefined) return undefined
  await $.store.delete(RESUME_KEY)
  if (typeof raw !== 'object' || raw === null) return undefined
  const record = raw as ResumeRecord
  const isSame = record.sessionId === (await $.session.id())
  const isFresh = (await $.clock.now()) - record.at <= RESUME_WINDOW_MS && record.cwd === cwd
  if (!isSame && !isFresh) return undefined
  await update($, cursorAtom, () => record.cursor ?? 0)
  await update($, answersAtom, () => record.answers ?? {})
  await update($, talksAtom, () => record.talks ?? {})
  await update($, rephrasedAtom, () => record.rephrased ?? {})
  await update($, originalAtom, () => record.original ?? {})
  await update($, returnedAtom, () => record.returned ?? {})
  return record
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    // Immediate: /answer opens the pane at once, even mid-turn. Its hook only
    // opens or focuses the pane, which needs nothing of the turn.
    await $.command.register({
      name: 'answer',
      description: 'Open the answer session (prototype, example questions)',
      immediate: true,
    })
    const started = await next(e)
    // Back from `/tui fullscreen`: the answer session reopens as it was. The
    // switch is the person's own act (the f in the notice, or /tui typed), so
    // the pane counts as asked for.
    const restored = e.isInteractive ? await takeRestart($, e.cwd).catch(() => undefined) : undefined
    if (restored) {
      await update($, flashAtom, () => 'Back after the restart, where you left off.')
      for (const [id, answer] of Object.entries(restored.answers ?? {})) {
        // Prototype only: a reply still owed comes after the usual wait.
        if (answer.kind === 'wait') $.clock.after(SIM_REPLY_MS, () => void deliverReply($, id))
      }
    }
    // A session launched as an answer session opens it by itself:
    //   CLAUDE_CODE_NO_FLICKER=1 INQUISITOR_ANSWER_SESSION=1 claude
    const flag = await $.env.get('INQUISITOR_ANSWER_SESSION')
    const isAnswerSession = !!flag && flag !== '0' && flag !== 'false'
    if (e.isInteractive && (isAnswerSession || restored)) {
      // The answer session is the whole screen: the pane asks for every row
      // and column, and the conversation beside it draws nothing.
      void update($, immersiveAtom, () => true)
      void $.ui.open({ id: PANE, title: 'Answer session', focus: true, rows: 500, columns: 500 }).then(opened => {
        // Unasked, the engine seats a pane only on a wide terminal (144
        // columns, or 110 once the person has opened this id). Otherwise it
        // waits, seating itself if the terminal widens, and /answer seats it.
        if (opened.isPlaced) return
        $.ui.status(`Answer session waiting for room (${opened.reason}). Run /answer to open it.`)
        void update($, placingAtom, () => true)
      })
    }
    return started
  })

  on('command.run', { command: 'answer' }, async $ => {
    // An answer session is the whole session: ask for every row and column the
    // screen can give (inline above the prompt, or docked floor to ceiling in
    // fullscreen). The engine caps both at what the layout spares.
    // Under the fullscreen layout the pane docks beside the transcript, floor
    // to ceiling, as wide as the engine allows (the terminal less the 24
    // columns it keeps for the transcript); on the main screen it sits inline
    // above the prompt, as tall as the layout spares.
    await update($, immersiveAtom, () => true)
    await $.ui.open({ id: PANE, title: 'Answer session', focus: true, rows: 500, columns: 500 })
    if (await read($, placingAtom)) {
      $.ui.status(undefined)
      await update($, placingAtom, () => false)
    }
    return { text: 'Answer session opened.' }
  })

  // Closing the pane, by the engine's close mark, ctrl+x x or an unload, brings
  // the conversation back.
  on('ui.close', { id: PANE }, async ($, e, next) => {
    const closed = await next(e)
    await update($, immersiveAtom, () => false)
    // Closed by hand, it must not come back after a restart. An unload (the
    // restart itself) leaves the record for the next start.
    if (e.origin.kind !== 'unload') await $.store.delete(RESUME_KEY)
    return closed
  })

  // `/tui fullscreen`, run from the notice or typed by the person, restarts
  // the session: while the pane is open, keep it for the restarted process.
  on('command.run', { command: 'tui' }, async ($, e, next) => {
    if (/\bfullscreen\b/.test(e.args) && (await $.ui.panes()).some(pane => pane.id === PANE)) await saveForRestart($)
    return next(e)
  })

  // While the pane is up, everything else the engine draws in the transcript
  // and around the prompt draws nothing: the pane is all there is to see. The
  // flag says when to look; the open panes say whether it really is up, so a
  // closed pane never leaves the conversation hidden. Only under the
  // fullscreen layout, which draws the transcript again when it changes: the
  // main screen prints finished rows into the terminal's scrollback once, so a
  // row hidden there would stay blank after the pane closed.
  on(
    'ui.render',
    {
      component: [
        'UserMessage',
        'AssistantMessage',
        'ToolUse',
        'ToolResult',
        'ToolGroup',
        'ToolProgress',
        'CommandOutput',
        'Spinner',
        'TurnDuration',
        'InfoNotice',
        'SessionMode',
        'AbovePrompt',
      ],
    },
    async ($, e, next) => {
      if (e.viewport?.isFullscreen !== true || !(await read($, immersiveAtom))) return next(e)
      const panes = await $.ui.panes()
      if (!panes.some(pane => pane.id === PANE && pane.isShown && pane.isPlaced)) return next(e)
      const { Box } = $.ui.resolve(e)
      return <Box />
    },
  )

  // The prompt box itself stays (no hook draws it); its hint line says the
  // two things worth knowing there: what typing does, and how to get back.
  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    if (!(await read($, immersiveAtom))) return next(e)
    const panes = await $.ui.panes()
    if (!panes.some(pane => pane.id === PANE && pane.isShown && pane.isPlaced)) return next(e)
    const { Text } = $.ui.resolve(e)
    return <Text dimColor>answer session · only /commands go to Claude · ctrl+x tab returns to it</Text>
  })

  // While the pane is open nothing typed in the prompt box reaches the model:
  // slash commands run, and prompts the engine sends itself pass. A failure
  // here drops the prompt rather than letting it through.
  on('prompt.submit', async ($, e, next) => {
    if (e.command || e.isMeta || !(await read($, immersiveAtom))) return next(e)
    const panes = await $.ui.panes()
    if (!panes.some(pane => pane.id === PANE && pane.isPlaced)) return next(e)
    return { drop: 'The answer session is open, so this was not sent to Claude. Close the pane to chat.' }
  }).catch(($, e, next) => (next.called ? next(e) : { drop: 'The answer session could not check this prompt, so it was not sent.' }))

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const ui = $.ui.resolve(e)
    const { Box, Text, Button, Link } = ui
    // Input is on the terminal and desktop surfaces only.
    const Input = 'Input' in ui ? ui.Input : undefined
    // Drawn at last after a launch-time open waited: the hint has done its job.
    // (A drawing never writes state; /answer clears the flag.)
    if (await read($, placingAtom)) $.ui.status(undefined)
    const cursor = await read($, cursorAtom)
    const answers = await read($, answersAtom)
    const stagedAll = await read($, stagedAtom)
    const drafts = await read($, draftsAtom)
    const flash = await read($, flashAtom)
    const seeds = await read($, seedsAtom)
    const talking = await read($, talkingAtom)
    const talks = await read($, talksAtom)
    const thinking = await read($, thinkingAtom)
    const rephrasedAll = await read($, rephrasedAtom)
    const originals = await read($, originalAtom)
    const talkScroll = await read($, talkScrollAtom)
    const askingAll = await read($, askingAtom)
    const returnedAll = await read($, returnedAtom)

    // The pane's own body, not the terminal: what the screen fills.
    const cols = e.props.bodyColumns
    const rows = Math.max(16, e.props.scroll.bodyRows)
    const padX = cols >= 100 ? 3 : cols >= 70 ? 2 : 1
    const inner = cols - 2 * padX
    // A reading measure: long lines are hard to read, however wide the dock.
    const measure = Math.min(inner, 88)
    // Vertical rhythm: the summary's gaps grow with the pane; a question's
    // are fitted to it below, once its lines are counted.
    const gap = rows >= 40 ? 2 : 1
    const focused = e.props.isFocused

    const N = QUESTIONS.length
    const at = Math.min(Math.max(cursor, 0), N)
    const base = at < N ? QUESTIONS[at] : undefined
    const count = (kind: Answer['kind']) => QUESTIONS.filter(one => answers[one.id]?.kind === kind).length
    const relayed = count('answer')
    const deferred = count('defer')
    const waiting = count('wait')
    const fresh = N - relayed - deferred - waiting

    // ── actions ──────────────────────────────────────────────────────────

    const drop = <T,>(record: Record<string, T>, id: string) => {
      const { [id]: _gone, ...rest } = record
      return rest
    }
    const focus = (key: string) => {
      if (focused) void $.ui.focus({ requestId: PANE, key })
    }
    // Moves to question `i` (N is the summary) and lands the focus ring there.
    const go = (i: number) => {
      void (async () => {
        const target = QUESTIONS[i]
        await update($, cursorAtom, () => i)
        await update($, flashAtom, () => null)
        if (target) focus(landingKey(target))
      })()
    }
    const step = (by: number) => () => go((at + by + N + 1) % (N + 1))
    const leaving = (one: Question) => {
      // An unsent draft is not kept past the question: it would be text the
      // field no longer shows.
      void update($, draftsAtom, d => ({ ...d, [one.id]: '' }))
      void update($, seedsAtom, d => ({ ...d, [one.id]: '' }))
      void update($, stagedAtom, s => (s[one.id]?.kind === 'text' ? drop(s, one.id) : s))
    }
    const stage = (one: Question, staged: Staged) => {
      void (async () => {
        await update($, stagedAtom, s => ({ ...s, [one.id]: staged }))
        await update($, flashAtom, () => null)
        // Choosing is not sending: the ring moves to Relay, so Enter sends
        // exactly the message the preview shows.
        if (staged.kind === 'option') focus(`send:${one.id}`)
      })()
    }
    // Records what was done with a question and moves to the next new one.
    const settle = (one: Question, answer: Answer, note: string) => {
      void (async () => {
        let after: Record<string, Answer> = {}
        await update($, answersAtom, a => (after = { ...a, [one.id]: answer }))
        await update($, stagedAtom, s => drop(s, one.id))
        await update($, draftsAtom, d => ({ ...d, [one.id]: '' }))
        await update($, seedsAtom, d => ({ ...d, [one.id]: '' }))
        await update($, talkingAtom, () => null)
        const target = nextFresh(QUESTIONS.findIndex(x => x.id === one.id), after)
        await update($, cursorAtom, () => target)
        await update($, flashAtom, () => note)
        const next = QUESTIONS[target]
        if (next) focus(landingKey(next))
      })()
    }
    // One completion on the session's own model; an error in words, never a throw.
    const complete = async (
      system: string,
      prompt: string,
      maxTokens: number,
    ): Promise<{ ok: true; text: string } | { ok: false; error: string }> => {
      try {
        const model = await $.session.model()
        const r = await $.model.complete({ model, system, prompt, maxTokens, timeoutMs: 120_000 })
        return r.isAnswered ? { ok: true, text: r.text.trim() } : { ok: false, error: why(r) }
      } catch (err) {
        return { ok: false, error: err instanceof Error ? err.message : String(err) }
      }
    }
    const think = (id: string, kind: 'reply' | 'rephrase' | 'draft' | undefined) =>
      update($, thinkingAtom, t => (kind ? { ...t, [id]: kind } : drop(t, id)))
    const addTurn = (id: string, turn: Turn) => update($, talksAtom, t => ({ ...t, [id]: [...(t[id] ?? []), turn] }))

    const openTalk = (one: Question) => {
      void (async () => {
        leaving(one)
        await update($, talkScrollAtom, () => 0)
        await update($, flashAtom, () => null)
        await update($, talkingAtom, () => one.id)
        focus(`talk:${one.id}:${(talks[one.id] ?? []).length}`)
      })()
    }
    const backToQuestion = (one: Question) => {
      void (async () => {
        await update($, askingAtom, a => drop(a, one.id))
        await update($, talkingAtom, () => null)
        focus(landingKey(one))
      })()
    }
    // Adam's message, then the model's reply, both kept with the question.
    const say = (one: Question, text: string) => {
      if (!text.trim() || thinking[one.id]) return
      void (async () => {
        let turns: Turn[] = []
        await update($, talksAtom, t => {
          turns = [...(t[one.id] ?? []), { who: 'you', text: text.trim() }]
          return { ...t, [one.id]: turns }
        })
        await update($, talkScrollAtom, () => 0)
        focus(`talk:${one.id}:${turns.length}`)
        await think(one.id, 'reply')
        const r = await complete(systemPrompt(one, returnedAll[one.id]), `${transcript(turns)}\n\nReply to Adam's last message.`, 1024)
        await addTurn(one.id, r.ok ? { who: 'model', text: r.text } : { who: 'error', text: `No reply: ${r.error}. Send again to retry.` })
        await think(one.id, undefined)
      })()
    }
    // The question rewritten in light of the discussion, then asked again.
    const rephrase = (one: Question) => {
      if (thinking[one.id]) return
      void (async () => {
        await think(one.id, 'rephrase')
        const shape = one.options
          ? '{"question": string, "context": string (one or two sentences, or ""), "options": [{"label": string, "effect": string}] (2 to 4 answers, the recommended one first: the asker\'s recommendation unless the discussion showed it no longer fits; each effect says what that answer would change), "summary": string (one line: what the discussion settled)}'
          : '{"question": string (what the person is asking, restated clearly), "context": string (one or two sentences, or ""), "options": [], "summary": string (one line: what the discussion settled)}'
        const r = await complete(
          systemPrompt(one, returnedAll[one.id]),
          `${transcript(talks[one.id] ?? [])}\n\nThe discussion is over. Rewrite the question in light of it, so that Adam can answer it at once: keep what the asker needs to know, use the words the discussion made clear, and drop what confused him. Answer with JSON only, in this shape:\n${shape}`,
          1500,
        )
        const revision = r.ok ? parseRevision(r.text, !!one.options) : undefined
        await think(one.id, undefined)
        if (!revision) {
          await addTurn(one.id, {
            who: 'error',
            text: !r.ok ? `Could not rephrase: ${r.error}. Press r to try again.` : 'The rephrasing came back unreadable. Press r to try again.',
          })
          return
        }
        await update($, rephrasedAtom, x => ({ ...x, [one.id]: revision }))
        await update($, originalAtom, o => drop(o, one.id))
        await update($, stagedAtom, s => drop(s, one.id))
        await update($, talkingAtom, () => null)
        await update($, flashAtom, () => 'Rephrased after your discussion. Asked again below.')
        focus(landingKey(one))
      })()
    }
    // A clarifying question for the asker, drafted by the model; Adam edits it.
    const draftAsk = (one: Question) => {
      if (thinking[one.id]) return
      void (async () => {
        await update($, askingAtom, a => ({ ...a, [one.id]: a[one.id] ?? { seed: '', text: '' } }))
        focus(`ask:${one.id}`)
        await think(one.id, 'draft')
        const r = await complete(
          systemPrompt(one, returnedAll[one.id]),
          `${transcript(talks[one.id] ?? [])}\n\nDraft the one clarifying question Adam should send back to ${one.asker.name} in the thread, about what the discussion shows is unclear. Write it as Adam would: one or two plain sentences addressed to them, no greeting, no sign-off, no quotation marks.`,
          300,
        )
        await think(one.id, undefined)
        if (r.ok) {
          const text = r.text.replace(/^["“]|["”]$/g, '').trim()
          await update($, askingAtom, a => ({ ...a, [one.id]: { seed: text, text } }))
        } else {
          await addTurn(one.id, { who: 'error', text: `Could not draft a question: ${r.error}. Write your own below.` })
        }
      })()
    }
    const sendAsk = (one: Question, text: string) => {
      if (!text.trim()) return
      settle(one, { kind: 'wait', text: text.trim() }, `Asked ${one.asker.name} on ${SURFACE_NAME[one.surface]}. Their question waits for the reply; nothing else does.`)
      void update($, askingAtom, a => drop(a, one.id))
      // Prototype only: the asker "replies" after a while.
      $.clock.after(SIM_REPLY_MS, () => void deliverReply($, one.id))
    }

    // ── pieces ────────────────────────────────────────────────────────────

    const rule = <Text color={RULE}>{'─'.repeat(inner)}</Text>
    // A section's label: small capitals, dim; a name in it keeps its case.
    const label = (words: string, name?: string) => (
      <Text>
        <Text dimColor>{words.toUpperCase()}</Text>
        {name ? <Text> {name}</Text> : ''}
      </Text>
    )
    // Key hints read as the Buttons beside them draw: the key in the accent,
    // a colon, the words.
    const hint = ([key, what]: [string, string]) => (
      <Text>
        <Text color={ACCENT}>{key}</Text>
        <Text dimColor>: {what}</Text>
      </Text>
    )
    const isTalking = !!base && talking === base.id

    const dots = (
      <Text>
        {QUESTIONS.map((one, i) => {
          const a = answers[one.id]
          const glyph = !a ? '○' : a.kind === 'answer' ? '●' : a.kind === 'defer' ? '◐' : '◌'
          const color = i === at ? ACCENT : !a ? RULE : a.kind === 'answer' ? DONE : a.kind === 'defer' ? LATER : ACCENT
          return (
            <Text color={color} bold={i === at} dimColor={a?.kind === 'wait' && i !== at}>
              {i > 0 ? ' ' : ''}
              {i === at && !a ? (isTalking ? '◇' : '◉') : glyph}
            </Text>
          )
        })}
      </Text>
    )
    const tally = [`${fresh} new`, `${relayed} relayed`, `${deferred} deferred`, ...(waiting ? [`${waiting} waiting`] : [])].join(' · ')
    const bar = (
      <Box gap={3}>
        <Text bold wrap="truncate-end">
          Answer session
        </Text>
        {dots}
        <Text dimColor wrap="truncate-end">
          {base ? `${at + 1} of ${N}` : 'summary'}
          {isTalking ? '  ·  talking it through' : inner >= 100 ? `  ·  ${tally}` : ''}
        </Text>
      </Box>
    )
    // On the main screen the pane takes the terminal's height at any width.
    // Fullscreen under 110 columns seats it above the prompt too, but caps it
    // at half the rows: say so, where the relay confirmation goes.
    const isSqueezed = e.props.placement === 'inline' && e.viewport?.isFullscreen === true
    const flashLine = flash ? (
      <Text color={DONE} wrap="truncate-end">✓ {flash}</Text>
    ) : isSqueezed ? (
      <Text color={LATER} wrap="truncate-end">
        Half the screen: fullscreen needs 110 columns. Widen the terminal, or start Claude Code with CLAUDE_CODE_NO_FLICKER=0.
      </Text>
    ) : (
      <Text> </Text>
    )

    // The screen: the session bar on top, the body on a reading measure in
    // the space between (two fifths of the slack above it, three below), and
    // the keys pinned to the bottom row: hints, then the Buttons they name.
    const frame = (body: ReturnType<typeof Box>, keys: [string, string][], buttons: ReturnType<typeof Button>[]) => (
      <Box flexDirection="column" width={cols} minHeight={rows} paddingX={padX}>
        {bar}
        {rule}
        {flashLine}
        <Box flexDirection="column" flexGrow={1} alignItems="center">
          <Box flexGrow={2} />
          <Box flexDirection="column" width={measure}>
            {body}
          </Box>
          <Box flexGrow={3} minHeight={1} />
        </Box>
        {rule}
        <Box columnGap={4} flexWrap="wrap">
          {keys.map(hint)}
          {buttons}
        </Box>
      </Box>
    )
    const navButtons = (one?: Question) => [
      <Button key="prev" hotkey="p" plain dimColor onPress={() => {
        if (one) leaving(one)
        step(-1)()
      }}>
        previous
      </Button>,
      <Button key="next" hotkey="n" plain dimColor onPress={() => {
        if (one) leaving(one)
        step(1)()
      }}>
        next
      </Button>,
    ]

    // ── the summary: every question handled, or the end of the queue ──────

    if (!base) {
      const done = QUESTIONS.filter(one => answers[one.id]?.kind === 'answer')
      const later = QUESTIONS.findIndex(one => answers[one.id]?.kind === 'defer')
      const settled = fresh === 0 && deferred === 0 && waiting === 0
      const head =
        fresh > 0
          ? `${fresh} question${fresh === 1 ? '' : 's'} still new`
          : deferred > 0
            ? `Nothing new. ${deferred} deferred.`
            : waiting > 0
              ? `Nothing new. ${waiting} waiting for a reply.`
              : 'All caught up.'
      return frame(
        <Box flexDirection="column" gap={gap}>
          <Box flexDirection="column" alignItems="center">
            <Text bold color={settled ? DONE : undefined}>
              {settled ? '✓  ' : ''}
              {head}
            </Text>
            <Text dimColor>
              {relayed} of {N} relayed this session{waiting ? ` · ${waiting} back with their askers` : ''}
            </Text>
          </Box>
          {done.length > 0 && (
            <Box flexDirection="column">
              {label('Relayed')}
              <Box height={1} />
              {done.map(one => (
                <Box gap={2}>
                  <Box width={Math.min(34, Math.floor(measure / 3))} flexShrink={0}>
                    <Text wrap="truncate-end">
                      <Text bold>{one.asker.name}</Text>
                      <Text dimColor> {one.where}</Text>
                    </Text>
                  </Box>
                  <Box flexGrow={1} flexShrink={1}>
                    <Text wrap="truncate-end">
                      <Text color={DONE}>│ </Text>
                      <Text dimColor>{PREFIX}</Text>
                      {answers[one.id]!.text}
                    </Text>
                  </Box>
                </Box>
              ))}
            </Box>
          )}
          {later >= 0 && (
            <Button key="review" hotkey="r" plain onPress={() => go(later)}>
              {`review the ${deferred === 1 ? 'deferred question' : `${deferred} deferred questions`}`}
            </Button>
          )}
        </Box>,
        [],
        navButtons(),
      )
    }

    // ── one question, as it now stands ───────────────────────────────────

    const returned = returnedAll[base.id]
    const rephrased = rephrasedAll[base.id]
    const showOriginal = !!originals[base.id]
    const q = view(base, rephrased, returned, showOriginal)
    const changed = rephrased ?? returned?.revised
    const answer = answers[base.id]
    const isRelayed = answer?.kind === 'answer'
    const isWaiting = answer?.kind === 'wait'
    const staged = stagedAll[q.id]
    const draft = drafts[q.id] ?? ''
    const message = stagedText(q, staged, draft)
    const isHuman = !q.options
    const turns = talks[q.id] ?? []
    const busy = thinking[q.id]
    const postsAs = `on ${SURFACE_NAME[q.surface]} as`

    const asked =
      q.asker.replyTo !== undefined
        ? `replied to ${q.asker.replyTo}`
        : q.asker.kind === 'agent'
          ? `asks, an agent via ${q.asker.via ?? 'the inquisitor'}`
          : 'asks'
    const provenance = (
      <Box flexDirection="column">
        <Box justifyContent="space-between">
          <Box gap={2}>
            <Text bold>{SURFACE_NAME[q.surface]}</Text>
            <Link href={q.link}>{q.where}</Link>
          </Box>
          <Text dimColor>
            {answer?.kind === 'defer' ? <Text color={LATER}>deferred · </Text> : ''}
            {isWaiting ? <Text color={ACCENT}>waiting for {q.asker.name} · </Text> : ''}
            {q.age} ago
          </Text>
        </Box>
        <Text>
          <Text color={ACCENT} bold>
            {q.asker.name}
          </Text>
          <Text dimColor> {asked}</Text>
        </Text>
      </Box>
    )
    const questionLines = wrap(q.text, measure).map(line => <Text bold>{line}</Text>)

    // What the relay account posts, exactly: "User says: …" behind a bar.
    const bubbleWidth = Math.max(20, measure - 2)
    const bubble = (text: string | undefined, color: string) => (
      <Box flexDirection="column">
        {wrap(PREFIX + (text ?? '…'), bubbleWidth).map((line, i) => (
          <Text>
            <Text color={color}>│ </Text>
            {i === 0 ? (
              <Text>
                <Text dimColor>{PREFIX}</Text>
                <Text dimColor={!text}>{line.slice(PREFIX.length)}</Text>
              </Text>
            ) : (
              <Text>{line}</Text>
            )}
          </Text>
        ))}
      </Box>
    )

    // ── talking it through: this question only, the queue waits ──────────

    if (isTalking) {
      const asking = askingAll[q.id]
      const composing = !!asking
      const hasReply = turns.some(t => t.who === 'model')
      const textWidth = Math.max(20, measure - SPEAKER)

      // The exchange as lines: a speaker column, then the words; newest last.
      type Line = { who?: Turn['who'] | 'thinking'; text: string }
      const all: Line[] = []
      turns.forEach((turn, i) => {
        if (i > 0) all.push({ text: '' })
        wrapMessage(turn.text, textWidth).forEach((text, j) => all.push({ who: j === 0 ? turn.who : undefined, text }))
      })
      if (busy) {
        if (all.length) all.push({ text: '' })
        all.push({
          who: 'thinking',
          text: busy === 'rephrase' ? 'rephrasing the question…' : busy === 'draft' ? `drafting a question for ${q.asker.name}…` : 'thinking…',
        })
      }
      if (!all.length) {
        for (const text of wrap(
          `Ask anything about this question: what it means, what each answer would change, what you are unsure of. The rest of the queue waits where it was. When it is clear, r rephrases the question and asks it again, or a asks ${q.asker.name} a question of your own, through the relay.`,
          textWidth,
        ))
          all.push({ text })
      }

      const optionLines = q.options?.length ?? 0
      const head = 5 + 2 + 1 + wrap(q.text, measure).length + (optionLines ? 1 + optionLines : 0) + 1 + 2
      const askText = asking?.text ?? ''
      const lower = composing ? 1 + 1 + 5 + 1 + 1 + wrap(PREFIX + (askText || '…'), bubbleWidth).length + 2 : 1 + 4
      const window = Math.max(3, rows - head - lower - 1) // less the spacer under the body
      const scroll = Math.min(talkScroll, Math.max(0, all.length - window))
      let shown = all.slice(Math.max(0, all.length - window - scroll), all.length - scroll)
      const hiddenAbove = all.length - scroll - shown.length
      if (hiddenAbove > 0) shown = shown.slice(1)
      if (scroll > 0) shown = shown.slice(0, -1)
      const speaker = (who: Line['who']) =>
        who === 'you' ? (
          <Text color={ACCENT} bold>
            you
          </Text>
        ) : who === 'model' || who === 'thinking' ? (
          <Text dimColor bold>
            claude
          </Text>
        ) : who === 'error' ? (
          <Text color={LATER} bold>
            claude
          </Text>
        ) : (
          <Text> </Text>
        )
      const lineOf = (line: Line, kind: Line['who']) => (
        <Box>
          <Box width={SPEAKER} flexShrink={0}>
            {speaker(line.who)}
          </Box>
          <Text dimColor={kind === 'thinking' || kind === undefined} italic={kind === 'thinking'} color={kind === 'error' ? LATER : undefined}>
            {line.text || ' '}
          </Text>
        </Box>
      )
      // A wrapped line keeps the style of the message it belongs to.
      let current: Line['who'] = undefined
      const kinds = all.map(line => {
        if (line.who) current = line.who
        return turns.length || busy ? current : undefined
      })
      const firstShown = Math.max(0, all.length - scroll - shown.length)

      const exchange = (
        <Box flexDirection="column" height={window} justifyContent="flex-end">
          {hiddenAbove > 0 && (
            <Text dimColor>
              {' '.repeat(SPEAKER)}↑ {hiddenAbove} earlier line{hiddenAbove === 1 ? '' : 's'}
            </Text>
          )}
          {shown.map((line, i) => lineOf(line, kinds[firstShown + i]))}
          {scroll > 0 && (
            <Text dimColor>
              {' '.repeat(SPEAKER)}↓ {scroll} newer line{scroll === 1 ? '' : 's'}
            </Text>
          )}
        </Box>
      )

      const talkField = Input ? (
        <Box paddingLeft={SPEAKER}>
          <Input
            // A new key per message sent: the field starts empty again.
            key={`talk:${q.id}:${turns.length}`}
            placeholder={busy ? 'Claude is replying…' : turns.length ? 'Reply, or ask more…' : 'Ask about this question…'}
            submitLabel="send"
            rows={2}
            autoFocus={composing ? undefined : true}
            onSubmit={(text: string) => say(q, text)}
          />
        </Box>
      ) : (
        <Text dimColor>Talking a question through needs a keyboard: this surface has no text field.</Text>
      )

      const compose = composing ? (
        <Box flexDirection="column">
          {label(`Ask ${q.asker.name}, in the thread`)}
          {Input ? (
            <Input
              key={`ask:${q.id}`}
              // The model's draft seeds the field; Adam's edits are his own.
              value={asking.seed}
              placeholder={busy === 'draft' ? 'Drafting…' : `Your question for ${q.asker.name}…`}
              submitLabel="send"
              rows={3}
              autoFocus
              onInput={(text: string) => void update($, askingAtom, a => ({ ...a, [q.id]: { seed: a[q.id]?.seed ?? '', text } }))}
              onSubmit={(text: string) => sendAsk(q, text)}
            />
          ) : null}
          <Box height={1} />
          {label(askText.trim() ? `Will post ${postsAs}` : `Posts ${postsAs}`, `${q.relayAs}, replying in ${q.where}`)}
          {bubble(askText.trim() || undefined, askText.trim() ? ACCENT : RULE)}
          <Box marginTop={1} gap={2}>
            {askText.trim() ? (
              <Button key={`ask-send:${q.id}`} hotkey="s" variant="primary" onPress={() => sendAsk(q, askText)}>
                Send
              </Button>
            ) : (
              <Text> </Text>
            )}
            {askText.trim() ? <Text dimColor>The question waits for their reply; the queue moves on.</Text> : ''}
          </Box>
        </Box>
      ) : null

      return frame(
        <Box flexDirection="column">
          {provenance}
          <Box height={1} />
          {questionLines}
          {q.options && (
            <Box flexDirection="column" marginTop={1}>
              {q.options.map((o, i) => (
                <Text dimColor wrap="truncate-end">
                  {i + 1}  {o.label}
                  {i === 0 ? '  ★' : ''}
                </Text>
              ))}
            </Box>
          )}
          <Box height={1} />
          <Text>
            <Text color={ACCENT}>◇ </Text>
            {label('Talking it through', '')}
            <Text dimColor> · this question only</Text>
          </Text>
          <Box height={1} />
          {exchange}
          <Box height={1} />
          {composing ? compose : talkField}
        </Box>,
        composing
          ? [
              ['Enter', `send to ${q.asker.name}`],
              ['Tab', 'leave the field'],
            ]
          : [
              ['Enter', 'send'],
              ['Tab', 'leave the field'],
            ],
        [
          ...(!composing && hasReply
            ? [
                <Button key={`rephrase:${q.id}`} hotkey="r" plain onPress={() => rephrase(q)}>
                  rephrase and ask again
                </Button>,
              ]
            : []),
          ...(!composing
            ? [
                <Button key={`ask:${q.id}:open`} hotkey="a" plain onPress={() => draftAsk(q)}>
                  ask the asker
                </Button>,
              ]
            : []),
          ...(hiddenAbove > 0
            ? [
                <Button key="earlier" hotkey="k" plain dimColor onPress={() => void update($, talkScrollAtom, s => s + Math.max(1, window - 2))}>
                  earlier
                </Button>,
              ]
            : []),
          ...(scroll > 0
            ? [
                <Button key="later" hotkey="j" plain dimColor onPress={() => void update($, talkScrollAtom, s => Math.max(0, s - Math.max(1, window - 2)))}>
                  later
                </Button>,
              ]
            : []),
          composing ? (
            <Button key={`back:${q.id}`} hotkey="b" plain dimColor onPress={() => {
              void update($, askingAtom, a => drop(a, q.id))
              focus(`talk:${q.id}:${turns.length}`)
            }}>
              back to the discussion
            </Button>
          ) : (
            <Button key={`back:${q.id}`} hotkey="b" plain dimColor onPress={() => backToQuestion(q)}>
              back without changes
            </Button>
          ),
        ],
      )
    }

    // ── the question view ────────────────────────────────────────────────

    const contextBlock = q.context ? (
      q.asker.replyTo !== undefined ? (
        <Box flexDirection="column">
          <Text dimColor>Their reply is to:</Text>
          {wrap(q.context, measure - 2).map(line => (
            <Text dimColor>│ {line}</Text>
          ))}
        </Box>
      ) : (
        <Box flexDirection="column">
          {wrap(q.context, measure).map(line => (
            <Text>{line}</Text>
          ))}
        </Box>
      )
    ) : null

    // The asker's reply to a clarifying question, quoted and attributed.
    const replyBlock = returned ? (
      <Box flexDirection="column">
        <Text>
          <Text color={ACCENT}>↩ </Text>
          <Text bold>{q.asker.name}</Text>
          <Text dimColor> replied to your question</Text>
        </Text>
        {wrap(`You asked: ${returned.asked}`, measure - 2).map(line => (
          <Text dimColor>{'  '}{line}</Text>
        ))}
        {wrap(returned.reply, measure - 2).map(line => (
          <Text>
            <Text dimColor>│ </Text>
            {line}
          </Text>
        ))}
      </Box>
    ) : null

    const changeMark = changed ? (
      <Box gap={3}>
        <Text dimColor>
          {showOriginal
            ? 'The original question, as asked'
            : rephrased
              ? '↻ Rephrased after your discussion'
              : `↻ Revised by ${q.asker.name} after your question`}
        </Text>
        <Button key={`orig:${q.id}`} hotkey="o" plain dimColor onPress={() => {
          void update($, originalAtom, o => ({ ...o, [q.id]: !o[q.id] }))
          void update($, stagedAtom, s => (s[q.id]?.kind === 'option' ? drop(s, q.id) : s))
        }}>
          {showOriginal ? 'show it as asked now' : 'show the original'}
        </Button>
      </Box>
    ) : null

    const relatedBlock =
      q.related || q.answered ? (
        <Box flexDirection="column">
          {q.related && (
            <Text>
              <Text dimColor>Related </Text>
              {q.related}
            </Text>
          )}
          {q.answered && (
            <Box flexDirection="column">
              <Text>
                <Text color={LATER}>Possibly answered already </Text>
                {q.answered.decision}
              </Text>
              {!isRelayed && !isWaiting && Input && (
                <Button
                  key={`cite:${q.id}`}
                  hotkey="c"
                  plain
                  dimColor
                  onPress={() => {
                    void (async () => {
                      await update($, seedsAtom, d => ({ ...d, [q.id]: q.answered!.cite }))
                      await update($, draftsAtom, d => ({ ...d, [q.id]: q.answered!.cite }))
                      await update($, stagedAtom, s => ({ ...s, [q.id]: { kind: 'text' as const } }))
                      focus(`send:${q.id}`)
                    })()
                  }}
                >
                  reply by citing it
                </Button>
              )}
            </Box>
          )}
        </Box>
      ) : null

    // Each option: a gutter that marks the chosen one, the number key and the
    // label on the first row, what changes beneath it, dim and indented.
    const effectWidth = Math.max(20, measure - 7)
    const optionRows = (q.options ?? []).map((o, i) => {
      const isChosen = staged?.kind === 'option' && staged.index === i
      const effect = wrap(o.effect, effectWidth - 2).map((line, j) => (j === 0 ? '→ ' : '  ') + line)
      const mark = isChosen ? '▌' : ' '
      return (
        <Box flexDirection="row">
          <Box flexDirection="column" width={2}>
            {[0, ...effect.map((_, j) => j + 1)].map(() => (
              <Text color={ACCENT}>{mark}</Text>
            ))}
          </Box>
          <Box flexDirection="column" flexGrow={1}>
            <Box gap={3}>
              <Button
                key={`opt:${q.id}:${i}`}
                hotkey={String(i + 1)}
                plain
                autoFocus={i === 0 && !staged ? true : undefined}
                onPress={() => stage(q, { kind: 'option', index: i })}
              >
                <Text bold color={isChosen ? ACCENT : undefined}>
                  {o.label}
                </Text>
              </Button>
              {i === 0 && <Text color={ACCENT}>★ recommended</Text>}
            </Box>
            {effect.map(line => (
              <Text dimColor>
                {'   '}
                {line}
              </Text>
            ))}
          </Box>
        </Box>
      )
    })

    // What the real skill logs beside an answer to a changed question.
    const logNote =
      changed && !showOriginal && (isRelayed || message) ? (
        <Box flexDirection="column" marginTop={1}>
          {wrap(
            `Logged with the answer in the real skill, not posted: the question as ${rephrased ? 'rephrased' : 'revised'}${
              rephrased?.summary ? `, and the discussion in a line: “${rephrased.summary.replace(/[.\s]+$/, '')}.”` : '.'
            }`,
            measure - 2,
          ).map(line => (
            <Text dimColor>{'  '}{line}</Text>
          ))}
        </Box>
      ) : null
    const logLines = logNote ? 1 + wrap(`Logged with the answer in the real skill, not posted: the question as rephrased, and the discussion in a line: “${rephrased?.summary ?? ''}”.`, measure - 2).length : 0

    // Count the screen's lines, then give what is left to the three gaps
    // (where it came from | the question | the answers | what will post), a
    // field a little taller when there is room, and the rest above and below.
    const lines = (text: string, width: number) => wrap(text, width).length
    const sent = isRelayed || isWaiting ? answer.text : message
    const open = !isRelayed && !isWaiting
    type Trim = { label: boolean; reserve: boolean; context: 'full' | 'line' | 'none'; related: boolean }
    const contextLines = (t: Trim) =>
      !q.context || t.context === 'none'
        ? 0
        : 1 +
          (t.context === 'line'
            ? 1 + (q.asker.replyTo !== undefined ? 1 : 0)
            : q.asker.replyTo !== undefined
              ? 1 + lines(q.context, measure - 2)
              : lines(q.context, measure))
    const measureWith = (t: Trim) =>
      6 + // session bar, its rule, the line under it; the spacer, the keys' rule and row
      2 + // where and who
      (changed ? 1 : 0) +
      lines(q.text, measure) +
      contextLines(t) +
      (returned ? 2 + lines(`You asked: ${returned.asked}`, measure - 2) + lines(returned.reply, measure - 2) : 0) +
      (t.related && (q.related || q.answered)
        ? 1 + (q.related ? lines(`Related ${q.related}`, measure) : 0) + (q.answered ? 2 : 0)
        : 0) +
      (open
        ? (isHuman || !t.label ? 0 : 2) + // the label and its gap
          (q.options ?? []).reduce((sum, o) => sum + 2 + lines(o.effect, effectWidth - 2), 0) +
          (isHuman ? 2 : 1) + 2 // the own-words row and the field's frame
        : 0) +
      1 + lines(PREFIX + (sent ?? '…'), bubbleWidth) + (open && t.reserve ? 2 : 0) + logLines
    const gaps = open ? 3 : 2
    const minField = isHuman ? 3 : 1
    // In order: the options' label, then the empty Relay row, each before a
    // gap closes; then the gaps; then the context, cut to a line, then dropped.
    const steps: [Trim, number][] = [
      [{ label: true, reserve: true, context: 'full', related: true }, gaps],
      [{ label: false, reserve: true, context: 'full', related: true }, gaps],
      [{ label: false, reserve: !!message, context: 'full', related: true }, gaps],
      [{ label: false, reserve: !!message, context: 'full', related: true }, 0],
      [{ label: false, reserve: !!message, context: 'line', related: true }, 0],
      [{ label: false, reserve: !!message, context: 'line', related: false }, 0],
      [{ label: false, reserve: !!message, context: 'none', related: false }, 0],
    ]
    const trim = (steps.find(([t, room]) => measureWith(t) + minField + room <= rows) ?? steps[steps.length - 1]!)[0]
    const counted = measureWith(trim)
    const roomy = rows - counted >= 3 * (gaps + 1) + 3
    const fieldRows = isHuman ? (roomy ? 5 : 3) : roomy ? 2 : 1
    const free = rows - counted - fieldRows
    const fit = Math.min(3, Math.max(0, Math.floor(free / (gaps + 1))))
    // Too short for a row in every gap: what rows there are go first above the
    // answers, then above the preview, then under where it came from.
    const gapAt = (place: 'top' | 'answers' | 'preview') =>
      fit > 0 ? fit : Math.max(0, Math.min(1, free - (place === 'answers' ? 0 : place === 'preview' ? 1 : 2)))
    const shortContext =
      q.context && trim.context === 'line' ? (
        q.asker.replyTo !== undefined ? (
          <Box flexDirection="column">
            <Text dimColor>Their reply is to:</Text>
            <Text dimColor wrap="truncate-end">│ {q.context}</Text>
          </Box>
        ) : (
          <Text wrap="truncate-end">{q.context}</Text>
        )
      ) : null

    const field = Input ? (
      <Input
        key={`field:${q.id}`}
        // A seed is text the mod puts in the field (a citation); typing never
        // changes it, so a redraw never takes back what was typed since.
        value={seeds[q.id]}
        placeholder={isHuman ? 'Write your reply…' : 'Type an answer instead…'}
        submitLabel="relay"
        rows={fieldRows}
        autoFocus={isHuman ? true : undefined}
        onInput={(text: string) => {
          void update($, draftsAtom, d => ({ ...d, [q.id]: text }))
          void update($, stagedAtom, s => (text.trim() ? { ...s, [q.id]: { kind: 'text' as const } } : s[q.id]?.kind === 'text' ? drop(s, q.id) : s))
          void update($, flashAtom, () => null)
        }}
        onSubmit={(text: string) => {
          // The preview showed this text as it was typed: Enter sends it.
          if (text.trim()) settle(q, { kind: 'answer', text: text.trim() }, `Relayed to ${SURFACE_NAME[q.surface]} ${q.where} as ${q.relayAs}`)
        }}
      />
    ) : null
    const isWriting = staged?.kind === 'text'
    const ownWords = field ? (
      <Box flexDirection="row">
        <Box flexDirection="column" width={2}>
          <Text color={ACCENT}>{isWriting ? '▌' : ' '}</Text>
        </Box>
        <Box flexDirection="column" flexGrow={1}>
          <Button key={`write:${q.id}`} hotkey="w" plain onPress={() => focus(`field:${q.id}`)}>
            <Text bold={isWriting} color={isWriting ? ACCENT : undefined}>
              {isHuman ? `Reply to ${q.asker.name}` : 'Or answer in your own words'}
            </Text>
          </Button>
          <Box paddingLeft={3} marginTop={isHuman ? 1 : 0}>
            {field}
          </Box>
        </Box>
      </Box>
    ) : null

    const preview = isRelayed ? (
      <Box flexDirection="column">
        <Text>
          <Text color={DONE}>✓ </Text>
          {label(`Relayed ${postsAs}`, q.relayAs)}
        </Text>
        {bubble(answer.text, DONE)}
        {logNote}
      </Box>
    ) : isWaiting ? (
      <Box flexDirection="column">
        <Text>
          <Text color={ACCENT}>◌ </Text>
          {label(`Waiting for ${q.asker.name}. Asked ${postsAs}`, q.relayAs)}
        </Text>
        {bubble(answer.text, ACCENT)}
      </Box>
    ) : (
      <Box flexDirection="column">
        {label(message ? `Will post ${postsAs}` : `Posts ${postsAs}`, q.relayAs)}
        {bubble(message, message ? ACCENT : RULE)}
        {logNote}
        {/* The Relay row is held even while empty, so choosing moves nothing,
            unless the pane is too short to spare it. */}
        <Box marginTop={1} gap={2} display={message || trim.reserve ? 'flex' : 'none'}>
          {message ? (
            <Button
              key={`send:${q.id}`}
              hotkey="s"
              variant="primary"
              onPress={() => settle(q, { kind: 'answer', text: message }, `Relayed to ${SURFACE_NAME[q.surface]} ${q.where} as ${q.relayAs}`)}
            >
              Relay
            </Button>
          ) : (
            <Text> </Text>
          )}
          {message ? <Text dimColor>Enter or s sends exactly this</Text> : ''}
        </Box>
      </Box>
    )

    const options = q.options ?? []
    const keys: [string, string][] = !open
      ? []
      : isHuman
        ? [
            ['Enter', 'relay'],
            ['Tab', 'leave the field'],
            ...(q.answered ? ([['c', 'cite the decision']] as [string, string][]) : []),
          ]
        : [
            [`1–${options.length}`, 'choose'],
            ...(message ? ([['Enter', 'relay']] as [string, string][]) : []),
            ['w', 'own words'],
          ]

    return frame(
      <Box flexDirection="column">
        {provenance}
        <Box height={gapAt('top')} />
        {changeMark}
        {questionLines}
        {contextBlock && trim.context === 'full' && <Box marginTop={1}>{contextBlock}</Box>}
        {shortContext && <Box marginTop={1}>{shortContext}</Box>}
        {replyBlock && <Box marginTop={1}>{replyBlock}</Box>}
        {relatedBlock && trim.related && <Box marginTop={1}>{relatedBlock}</Box>}
        <Box height={gapAt('answers')} />
        {open && (
          <Box flexDirection="column" gap={1}>
            {!isHuman && trim.label && label('Choose an answer')}
            {optionRows}
            {ownWords}
          </Box>
        )}
        {open && <Box height={gapAt('preview')} />}
        {preview}
      </Box>,
      keys,
      [
        ...(open
          ? [
              <Button key={`talk:${q.id}:open`} hotkey="t" plain onPress={() => openTalk(q)}>
                {turns.length ? 'continue the discussion' : 'talk it through'}
              </Button>,
              <Button key={`defer:${q.id}`} hotkey="d" plain dimColor onPress={() => settle(q, { kind: 'defer', text: '' }, `Deferred: ${q.asker.name}'s question waits until the new ones are done`)}>
                defer
              </Button>,
            ]
          : []),
        ...navButtons(q),
      ],
    )
  })
}

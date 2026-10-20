import { atom, read, update } from 'claude-code'
import type { EngineInterface, ModelCompleteResult, Register, RenderElement } from 'claude-code'

import type { Answer, Returned, Revision, Turn } from '../types'

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

// Prototype only: shown in the top bar, so a tester can tell which build is
// loaded. v0.1-N, N the number of commits in the prototype repository once
// this build is committed.
const BUILD = 'v0.1-14'
const PREFIX = 'User says: '
const SPEAKER = 8
const cursorAtom = atom({ plugin: 'answer-session', key: 'cursor' } as const, 0)
const answersAtom = atom({ plugin: 'answer-session', key: 'answers' } as const, {} as Record<string, Answer>)
const promptAtom = atom({ plugin: 'answer-session', key: 'prompt' } as const, '')
const flashAtom = atom({ plugin: 'answer-session', key: 'flash' } as const, null as string | null)
const talkingAtom = atom({ plugin: 'answer-session', key: 'talking' } as const, null as string | null)
const talksAtom = atom({ plugin: 'answer-session', key: 'talks' } as const, {} as Record<string, Turn[]>)
const thinkingAtom = atom(
  { plugin: 'answer-session', key: 'thinking' } as const,
  {} as Record<string, 'reply' | 'rephrase' | 'draft'>,
)
const rephrasedAtom = atom({ plugin: 'answer-session', key: 'rephrased' } as const, {} as Record<string, Revision>)
const originalAtom = atom({ plugin: 'answer-session', key: 'original' } as const, {} as Record<string, boolean>)
const awaitingAtom = atom({ plugin: 'answer-session', key: 'awaiting' } as const, [] as { id: string; text: string }[])
const replyTurnsAtom = atom({ plugin: 'answer-session', key: 'replyTurns' } as const, {} as Record<string, string>)
const askingAtom = atom({ plugin: 'answer-session', key: 'asking' } as const, {} as Record<string, true>)
const returnedAtom = atom({ plugin: 'answer-session', key: 'returned' } as const, {} as Record<string, Returned>)
const openAtom = atom({ plugin: 'answer-session', key: 'isOpen' } as const, false)

/** `text` cut to `width` cells, an ellipsis marking the cut. */
function cut(text: string, width: number): string {
  if (text.length <= width) return text
  return width <= 1 ? '…' : `${text.slice(0, width - 1).trimEnd()}…`
}

/**
 * What a view of the band may give up to fit its height, one step at a time
 * in `TRIMS`' order: space first, then labels and repetition, then detail.
 * The question itself, the options' labels and the post's first line stay.
 */
type Trim = {
  /** Blank rows between a column's groups. */
  gap: number
  /** The "Choose an answer" label. */
  label: boolean
  /** A blank row between options. */
  optionGap: boolean
  /** What the real skill logs beside an answer to a changed question. */
  logNote: boolean
  /** Each option's effect: all of it, one line, or none. */
  effects: 'full' | 'line' | 'none'
  /** The asker's context: all of it, one line, or none. */
  context: 'full' | 'line' | 'none'
  /** The "Or type your own answer" row (the hint line under the prompt says it too). */
  ownWords: boolean
  /** The related decision, and the cite button under "possibly answered". */
  related: boolean
  /** Where and who: two rows, one, or none (the question alone, on the smallest band). */
  provenance: 0 | 1 | 2
  /** The asker's reply to a clarifying question: with what was asked, or the reply alone. */
  reply: 'full' | 'short'
  /** Most lines of the post's preview. */
  bubble: number
  /** The preview under its label, or the post alone in one row. */
  preview: 'full' | 'line'
}
const TRIMS: Trim[] = (() => {
  let t: Trim = {
    gap: 2,
    label: true,
    optionGap: true,
    logNote: true,
    effects: 'full',
    context: 'full',
    ownWords: true,
    related: true,
    provenance: 2,
    reply: 'full',
    bubble: 6,
    preview: 'full',
  }
  const steps: Partial<Trim>[] = [
    {},
    { gap: 1 },
    { label: false },
    { optionGap: false },
    { gap: 0 },
    { logNote: false },
    { effects: 'line' },
    { context: 'line' },
    { ownWords: false },
    { related: false },
    { provenance: 1 },
    { reply: 'short' },
    { bubble: 2 },
    { effects: 'none' },
    { context: 'none' },
    { bubble: 1 },
    { preview: 'line' },
    { provenance: 0 },
  ]
  return steps.map(step => (t = { ...t, ...step }))
})()

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

/** The first question after `from` with nothing done to it, or the summary's index. */
function nextFresh(from: number, answers: Record<string, Answer>): number {
  for (let step = 1; step <= QUESTIONS.length; step++) {
    const i = (from + step) % QUESTIONS.length
    if (!answers[QUESTIONS[i]!.id]) return i
  }
  return QUESTIONS.length
}

/** Everything the model is told about the question it helps with: the system prompt of a rephrasing or a draft. */
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
    'Write plain text for a terminal: short paragraphs, under about 120 words unless he asks for more, no headings, no bold or italics. A simple "- " list is fine.',
  )
  return lines.join('\n')
}

/**
 * What rides beside each discussion message, unseen by Adam: the question and
 * how to help. The message goes to the session's own model, which may read
 * the thread, the code and the specs with its tools before it answers.
 */
function discussionContext(q: Question, returned?: Returned): string {
  return [
    `[Answer session] Adam's message is about a question relayed to him (${q.link}). He is talking it through before he answers it.`,
    '',
    systemPrompt(q, returned),
    '- You may read the thread, the code and the specs with your tools to check a fact; say what you checked.',
    '- Do not post, comment, push or change anything: Adam answers through his answer session, not through you.',
  ].join('\n')
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

// ── what Enter does ─────────────────────────────────────────────────────
//
// The keyboard stays in the prompt box for the whole session. What the box
// holds is read against the screen on show: a digit chooses an option, one
// letter names a command, anything longer is an answer (or, in a
// discussion, a message to the model). The band previews it as it is typed;
// Enter does it. Only a discussion message reaches the model; everything
// else Enter does is dropped once done.

/** The answer session's state, as the screen and Enter both read it. */
type Ctx = {
  at: number
  base?: Question
  /** The question as it now stands (rephrased, revised, or as asked). */
  q?: Question
  answer?: Answer
  open: boolean
  talking: boolean
  composing: boolean
  busy?: 'reply' | 'rephrase' | 'draft'
  hasReply: boolean
  changed: boolean
  deferredAt: number
}

async function snapshot($: EngineInterface): Promise<Ctx> {
  const N = QUESTIONS.length
  const at = Math.min(Math.max(await read($, cursorAtom), 0), N)
  const answers = await read($, answersAtom)
  const deferredAt = QUESTIONS.findIndex(one => answers[one.id]?.kind === 'defer')
  const base = QUESTIONS[at]
  if (!base) return { at, open: false, talking: false, composing: false, hasReply: false, changed: false, deferredAt }
  const rephrased = (await read($, rephrasedAtom))[base.id]
  const returned = (await read($, returnedAtom))[base.id]
  const q = view(base, rephrased, returned, !!(await read($, originalAtom))[base.id])
  const answer = answers[base.id]
  const talking = (await read($, talkingAtom)) === base.id
  return {
    at,
    base,
    q,
    answer,
    open: answer?.kind !== 'answer' && answer?.kind !== 'wait',
    talking,
    composing: talking && !!(await read($, askingAtom))[base.id],
    busy: (await read($, thinkingAtom))[base.id],
    hasReply: ((await read($, talksAtom))[base.id] ?? []).some(t => t.who === 'model'),
    changed: !!(rephrased ?? returned?.revised),
    deferredAt,
  }
}

/** A one-letter command: its key and what it does (`runCommand` does it). */
type Command = { key: string; what: string }

/** The commands the screen offers now, in the order the key row shows them. */
function commands(c: Ctx): Command[] {
  const q = c.q
  const close: Command = { key: 'q', what: 'close' }
  const nav: Command[] = [
    { key: 'p', what: 'previous' },
    { key: 'n', what: 'next' },
  ]
  if (!q) return [...(c.deferredAt >= 0 ? [{ key: 'r', what: 'back to those for later' }] : []), ...nav, close]
  if (c.composing) return [{ key: 'b', what: 'back to the discussion' }, close]
  if (c.talking) {
    return [
      ...(c.hasReply && !c.busy ? [{ key: 'r', what: 'rephrase and ask again' }] : []),
      ...(!c.busy ? [{ key: 'a', what: `ask ${q.asker.name}` }] : []),
      { key: 'b', what: 'back without changes' },
      close,
    ]
  }
  return [
    ...(c.open
      ? [
          { key: 't', what: 'talk it through' },
          ...(q.answered ? [{ key: 'c', what: 'cite the decision' }] : []),
          { key: 'l', what: 'later' },
        ]
      : []),
    ...(c.changed ? [{ key: 'o', what: 'original' }] : []),
    ...nav,
    close,
  ]
}

/** Does command `key` on the screen `c` describes, and says what it did. */
async function runCommand($: EngineInterface, c: Ctx, key: string): Promise<string> {
  const q = c.q
  if (key === 'q') return closeSession($)
  if (key === 'p') return stepBy($, c.at, -1)
  if (key === 'n') return stepBy($, c.at, 1)
  if (!q) return key === 'r' ? go($, c.deferredAt, 'Back to a deferred question') : ''
  if (c.composing) return key === 'b' ? backToTalk($, q) : ''
  if (c.talking) {
    switch (key) {
      case 'r':
        return rephrase($, q)
      case 'a':
        return draftAsk($, q)
      case 'b':
        return backToQuestion($, q)
    }
    return ''
  }
  switch (key) {
    case 't':
      return openTalk($, q)
    case 'c':
      return cite($, q)
    case 'l':
      return settle($, q, { kind: 'defer', text: '' }, `Later: ${q.asker.name}'s question comes back after the new ones`)
    case 'o':
      return toggleOriginal($, q)
  }
  return ''
}

/** What Enter would do with the prompt box's text. */
type Intent =
  | { kind: 'none' }
  | { kind: 'option'; index: number; text: string }
  | { kind: 'relay'; text: string }
  | { kind: 'command'; command: Command }
  | { kind: 'say'; text: string }
  | { kind: 'ask'; text: string }
  | { kind: 'refused'; why: string }

function intent(c: Ctx, draft: string): Intent {
  const text = draft.trim()
  if (!text) return { kind: 'none' }
  const command = text.length === 1 ? commands(c).find(one => one.key === text.toLowerCase()) : undefined
  if (command) return { kind: 'command', command }
  const q = c.q
  if (!q) return { kind: 'refused', why: 'Nothing to answer here: p or n moves to a question.' }
  if (c.composing) return { kind: 'ask', text }
  if (c.talking) {
    // A digit chooses, as on the question; one character is never a message.
    if (/^[1-9]$/.test(text)) {
      const option = q.options?.[Number(text) - 1]
      if (option && c.open) return { kind: 'option', index: Number(text) - 1, text: option.label }
      return { kind: 'refused', why: q.options ? `There is no answer ${text}.` : 'A digit chooses an answer: this question has none to choose.' }
    }
    if (text.length === 1) return { kind: 'refused', why: `${text} is not a command here: the key row lists them.` }
    return c.busy ? { kind: 'refused', why: 'Claude is still answering above: wait for it, or Esc to stop it.' } : { kind: 'say', text }
  }
  if (!c.open) {
    return { kind: 'refused', why: c.answer?.kind === 'wait' ? `This question waits for ${q.asker.name}'s reply.` : 'This question is already relayed.' }
  }
  if (q.options && /^[1-9]$/.test(text)) {
    const index = Number(text) - 1
    const option = q.options[index]
    return option ? { kind: 'option', index, text: option.label } : { kind: 'refused', why: `There is no answer ${text}.` }
  }
  return { kind: 'relay', text }
}

/** What Enter would do, in a few words for the hint line; undefined when nothing. */
function enterHint(c: Ctx, it: Intent): string | undefined {
  const q = c.q
  switch (it.kind) {
    case 'option':
    case 'relay':
      return q ? `⏎ relay to ${SURFACE_NAME[q.surface]}` : undefined
    case 'command':
      return it.command.key === 'l' ? '⏎ ask me later, after the new ones' : `⏎ ${it.command.what}`
    case 'say':
      return '⏎ to Claude, with the question'
    case 'ask':
      return q ? `⏎ send to ${q.asker.name}` : undefined
    case 'refused':
      return it.why
    case 'none':
      return undefined
  }
}

/**
 * Does what Enter does on the screen `c` describes, and says what it did: all
 * but a discussion message, which the submit hook sends on to the model.
 */
async function enter($: EngineInterface, c: Ctx, it: Exclude<Intent, { kind: 'say' }>): Promise<string> {
  const q = c.q
  switch (it.kind) {
    case 'none':
      return 'Nothing to send.'
    case 'refused':
      return it.why
    case 'command':
      return runCommand($, c, it.command.key)
    case 'option':
    case 'relay':
      return q ? relay($, q, it.text) : ''
    case 'ask':
      return q ? sendAsk($, q, it.text) : ''
  }
}

// ── the prompt box ──────────────────────────────────────────────────────
//
// After Enter, the engine puts the dropped prompt back in the box (a
// prompt.change with origin `engine`). What the box should hold instead
// (nothing, or a citation Enter put there) waits here until that put-back
// arrives, or PUT_BACK_MS passes without one.
let afterDrop: { dropped: string; text: string } | undefined
const PUT_BACK_MS = 500
// True while a survey holds the band (the band's drawing says so): Enter then
// answers nothing, since no question is on screen.
let surveyUp = false

/** Puts `text` in the prompt box, after any put-back still due. */
async function putInBox($: EngineInterface, text: string): Promise<void> {
  if (afterDrop) {
    afterDrop.text = text
    return
  }
  await $.prompt.fill({ text, mode: 'replace' })
  // The mod's own fill skips its own prompt.change hook: keep the copy here.
  await update($, promptAtom, () => text)
}

/** Applies what the box should hold after a drop; `isPutBack` when the engine just put the prompt back. */
async function settleBox($: EngineInterface, isPutBack: boolean): Promise<void> {
  const due = afterDrop
  if (!due) return
  afterDrop = undefined
  // With no put-back, an empty box needs nothing, and filling it could wipe
  // what the person has started typing.
  if (!isPutBack && !due.text) return
  await $.prompt.fill({ text: due.text, mode: 'replace' })
  await update($, promptAtom, () => due.text)
}

// ── actions ─────────────────────────────────────────────────────────────

/** Moves to question `i` (the queue's length is the summary). */
async function go($: EngineInterface, i: number, note: string): Promise<string> {
  await update($, cursorAtom, () => i)
  await update($, flashAtom, () => null)
  return note
}

/** Moves to question `i`, or the summary past the last, and says where. */
function goTo($: EngineInterface, i: number): Promise<string> {
  const N = QUESTIONS.length
  return go($, i, i === N ? 'The summary' : `Question ${i + 1} of ${N}`)
}

function stepBy($: EngineInterface, at: number, by: number): Promise<string> {
  const N = QUESTIONS.length
  return goTo($, (at + by + N + 1) % (N + 1))
}

/** A command pressed in the band: done on the screen as it is now, as typing its key and Enter would. */
async function pressKey($: EngineInterface, key: string): Promise<string> {
  return runCommand($, await snapshot($), key)
}

/** Closes the band; the queue and everything done stay for the next /answer. */
async function closeSession($: EngineInterface): Promise<string> {
  await update($, openAtom, () => false)
  await update($, flashAtom, () => null)
  return 'Answer session closed. /answer opens it again where you left off.'
}

/** Records what was done with a question and moves to the next new one. */
async function settle($: EngineInterface, one: Question, answer: Answer, note: string): Promise<string> {
  let after: Record<string, Answer> = {}
  await update($, answersAtom, a => (after = { ...a, [one.id]: answer }))
  await update($, talkingAtom, () => null)
  await update($, cursorAtom, () => nextFresh(QUESTIONS.findIndex(x => x.id === one.id), after))
  await update($, flashAtom, () => note)
  return note
}

function relay($: EngineInterface, one: Question, text: string): Promise<string> {
  return settle($, one, { kind: 'answer', text }, `Relayed to ${SURFACE_NAME[one.surface]} ${one.where} as ${one.relayAs}`)
}

/** One completion on the session's own model; an error in words, never a throw. */
async function complete(
  $: EngineInterface,
  system: string,
  prompt: string,
  maxTokens: number,
): Promise<{ ok: true; text: string } | { ok: false; error: string }> {
  try {
    const model = await $.session.model()
    const r = await $.model.complete({ model, system, prompt, maxTokens, timeoutMs: 120_000 })
    return r.isAnswered ? { ok: true, text: r.text.trim() } : { ok: false, error: why(r) }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) }
  }
}

const think = ($: EngineInterface, id: string, kind: 'reply' | 'rephrase' | 'draft' | undefined) =>
  update($, thinkingAtom, t => (kind ? { ...t, [id]: kind } : without(t, id)))
const addTurn = ($: EngineInterface, id: string, turn: Turn) =>
  update($, talksAtom, t => ({ ...t, [id]: [...(t[id] ?? []), turn] }))

async function openTalk($: EngineInterface, one: Question): Promise<string> {
  await update($, flashAtom, () => null)
  await update($, talkingAtom, () => one.id)
  return 'Talking it through'
}

async function backToQuestion($: EngineInterface, one: Question): Promise<string> {
  await update($, askingAtom, a => without(a, one.id))
  await update($, talkingAtom, () => null)
  return 'Back to the question'
}

async function backToTalk($: EngineInterface, one: Question): Promise<string> {
  await update($, askingAtom, a => without(a, one.id))
  return 'Back to the discussion'
}

async function toggleOriginal($: EngineInterface, one: Question): Promise<string> {
  let isOriginal = false
  await update($, originalAtom, o => ({ ...o, [one.id]: (isOriginal = !o[one.id]) }))
  return isOriginal ? 'The original question' : 'The question as asked now'
}

/** Puts the reply citing the earlier decision in the prompt box, to edit or send. */
async function cite($: EngineInterface, one: Question): Promise<string> {
  if (one.answered) await putInBox($, one.answered.cite)
  return 'The citing reply is in the prompt box: Enter relays it'
}

/**
 * Adam's message, kept with the question, as it goes to the session's model.
 * Its reply is kept when the turn that answers it ends (the turn hooks).
 */
async function recordSay($: EngineInterface, one: Question, text: string): Promise<void> {
  await addTurn($, one.id, { who: 'you', text })
  await think($, one.id, 'reply')
  await update($, awaitingAtom, w => [...w, { id: one.id, text: text.trim() }])
}

/** The question rewritten in light of the discussion, then asked again. */
async function rephrase($: EngineInterface, one: Question): Promise<string> {
  void (async () => {
    await think($, one.id, 'rephrase')
    const shape = one.options
      ? '{"question": string, "context": string (one or two sentences, or ""), "options": [{"label": string, "effect": string}] (2 to 4 answers, the recommended one first: the asker\'s recommendation unless the discussion showed it no longer fits; each effect says what that answer would change), "summary": string (one line: what the discussion settled)}'
      : '{"question": string (what the person is asking, restated clearly), "context": string (one or two sentences, or ""), "options": [], "summary": string (one line: what the discussion settled)}'
    const returned = (await read($, returnedAtom))[one.id]
    const talks = (await read($, talksAtom))[one.id] ?? []
    const r = await complete(
      $,
      systemPrompt(one, returned),
      `${transcript(talks)}\n\nThe discussion is over. Rewrite the question in light of it, so that Adam can answer it at once: keep what the asker needs to know, use the words the discussion made clear, and drop what confused him. Answer with JSON only, in this shape:\n${shape}`,
      1500,
    )
    const revision = r.ok ? parseRevision(r.text, !!one.options) : undefined
    await think($, one.id, undefined)
    if (!revision) {
      await addTurn($, one.id, {
        who: 'error',
        text: !r.ok ? `Could not rephrase: ${r.error}. r and Enter try again.` : 'The rephrasing came back unreadable. r and Enter try again.',
      })
      return
    }
    await update($, rephrasedAtom, x => ({ ...x, [one.id]: revision }))
    await update($, originalAtom, o => without(o, one.id))
    await update($, talkingAtom, () => null)
    await update($, flashAtom, () => 'Rephrased after your discussion. Asked again below.')
  })()
  return 'Rephrasing the question'
}

/** A clarifying question for the asker, drafted by the model into the prompt box. */
async function draftAsk($: EngineInterface, one: Question): Promise<string> {
  await update($, askingAtom, a => ({ ...a, [one.id]: true as const }))
  void (async () => {
    await think($, one.id, 'draft')
    const returned = (await read($, returnedAtom))[one.id]
    const talks = (await read($, talksAtom))[one.id] ?? []
    const r = await complete(
      $,
      systemPrompt(one, returned),
      `${transcript(talks)}\n\nDraft the one clarifying question Adam should send back to ${one.asker.name} in the thread, about what the discussion shows is unclear. Write it as Adam would: one or two plain sentences addressed to them, no greeting, no sign-off, no quotation marks.`,
      300,
    )
    await think($, one.id, undefined)
    if (!r.ok) {
      await addTurn($, one.id, { who: 'error', text: `Could not draft a question: ${r.error}. Write your own in the prompt box.` })
      return
    }
    // The draft lands only in an empty box: what Adam started typing is his.
    const still = (await read($, askingAtom))[one.id]
    if (still && !(await $.prompt.read()).text.trim()) {
      await putInBox($, r.text.replace(/^["“]|["”]$/g, '').trim())
    }
  })()
  return `Drafting a question for ${one.asker.name}`
}

/** The Relay button: relays what the prompt box holds, then empties the box, as Enter would. */
async function relayPressed($: EngineInterface, one: Question, text: string): Promise<string> {
  const note = await relay($, one, text)
  await putInBox($, '')
  return note
}

/** The Send button under a question for the asker: sends it, then empties the box, as Enter would. */
async function askPressed($: EngineInterface, one: Question, text: string): Promise<string> {
  const note = await sendAsk($, one, text)
  await putInBox($, '')
  return note
}

async function sendAsk($: EngineInterface, one: Question, text: string): Promise<string> {
  await update($, askingAtom, a => without(a, one.id))
  const note = await settle($, one, { kind: 'wait', text }, `Asked ${one.asker.name} on ${SURFACE_NAME[one.surface]}. Their question waits for the reply; nothing else does.`)
  // Prototype only: the asker "replies" after a while.
  $.clock.after(SIM_REPLY_MS, () => void deliverReply($, one.id))
  return note
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    // Immediate: /answer opens or closes the band at once, even mid-turn. Its
    // hook only flips a value, which needs nothing of the turn.
    await $.command.register({
      name: 'answer',
      description: 'Open or close the answer session (prototype, example questions)',
      immediate: true,
    })
    const started = await next(e)
    // Back from `/tui fullscreen`: the answer session reopens as it was. The
    // switch is the person's own act, so the session counts as asked for.
    const restored = e.isInteractive ? await takeRestart($, e.cwd).catch(() => undefined) : undefined
    if (restored) {
      await update($, flashAtom, () => 'Back after the restart, where you left off.')
      for (const [id, answer] of Object.entries(restored.answers ?? {})) {
        // Prototype only: a reply still owed comes after the usual wait.
        if (answer.kind === 'wait') $.clock.after(SIM_REPLY_MS, () => void deliverReply($, id))
      }
    }
    // An answer session opens by /answer: typed, or given as the session's
    // first prompt (`claude '/answer'`). Only a restart reopens it unasked.
    if (e.isInteractive && restored) await update($, openAtom, () => true)
    return started
  })

  // /answer opens the band, or closes it when it is open. The band needs no
  // room of its own: it is the strip above the prompt, as wide as the
  // terminal, in both layouts.
  on('command.run', { command: 'answer' }, async $ => {
    let isOpen = false
    await update($, openAtom, v => (isOpen = !v))
    if (!isOpen) return { text: 'Answer session closed. /answer opens it again where you left off.' }
    // The preview reads a copy of the prompt box: start it from what is there.
    const box = await $.prompt.read().catch(() => ({ text: '' }))
    await update($, promptAtom, () => box.text)
    return { text: 'Answer session open: type in the prompt box, Enter answers.' }
  })

  // `/tui fullscreen` restarts the session: while the band is open, keep the
  // answer session for the restarted process.
  on('command.run', { command: 'tui' }, async ($, e, next) => {
    if (/\bfullscreen\b/.test(e.args) && (await read($, openAtom))) await saveForRestart($)
    return next(e)
  })

  // The permission mode's labels mean nothing while every prompt is an
  // answer: they draw nothing while the band is open.
  on('ui.render', { component: 'SessionMode' }, async ($, e, next) => {
    if (!(await read($, openAtom))) return next(e)
    const { Box } = $.ui.resolve(e)
    return <Box />
  })

  // The hint line under the prompt says what Enter would do with what is
  // typed, where the eyes are while typing. It rewrites only the line's
  // text: another plugin's `tail` (usage-hint's figures) still draws after it.
  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    if (surveyUp || !(await read($, openAtom))) return next(e)
    const c = await snapshot($)
    const idle = c.composing
      ? `your question for ${c.q?.asker.name ?? 'the asker'}, then ⏎`
      : c.talking
        ? 'a message to Claude or a key, then ⏎'
        : c.q?.options && c.open
          ? 'a number, a key or your answer, then ⏎'
          : 'a key or your answer, then ⏎'
    const hint = enterHint(c, intent(c, await read($, promptAtom))) ?? idle
    // Added after the engine's own line, never in place of it: a rewritten
    // `hint` drops every plugin's `tail`, usage-hint's figures among them.
    return next({ ...e, props: { ...e.props, tail: hint + (e.props.tail ? `  ·  ${e.props.tail}` : '') } })
  })

  // The band previews what Enter would do with the prompt box's text, so it
  // keeps a copy: every edit, and every change no edit carried (a fill, a
  // recalled history entry, a clear).
  on('prompt.edit', async ($, e, next) => {
    const box = await next(e)
    if (await read($, openAtom)) await update($, promptAtom, () => box.text)
    return box
  })
  on('prompt.change', async ($, e, next) => {
    const changed = await next(e)
    if (afterDrop && e.origin.kind === 'engine' && e.text === afterDrop.dropped) await settleBox($, true)
    else if (await read($, openAtom)) await update($, promptAtom, () => e.text)
    return changed
  })

  // While the band is open, Enter in the prompt box answers or acts in the
  // answer session, and the prompt never reaches the model: slash commands
  // run, and prompts the engine sends itself pass. The drop's reason is what
  // the person sees (a row in the transcript), so it says what was done. A
  // failure here drops the prompt rather than letting it through.
  on('prompt.submit', async ($, e, next) => {
    if (e.command || e.isMeta || e.origin.kind !== 'composer' || !(await read($, openAtom))) return next(e)
    // A survey holds the band: nothing typed answers a question not on screen.
    if (surveyUp) return { drop: 'A survey is above the prompt: answer it first, and the answer session is back.' }
    const c = await snapshot($)
    const it = intent(c, e.text)
    // In a discussion a message goes on to the session's own model, as any
    // prompt does, with the question beside it: the model can read the thread
    // and the code before it answers, and the reply shows in the conversation
    // above the band. The message and the reply are kept with the question.
    if (it.kind === 'say') {
      if (!c.q) return { drop: 'Nothing to discuss here.' }
      await recordSay($, c.q, it.text)
      await update($, promptAtom, () => '')
      const returned = (await read($, returnedAtom))[c.q.id]
      return next({ ...e, context: [...(e.context ?? []), discussionContext(c.q, returned)] })
    }
    afterDrop = { dropped: e.text, text: '' }
    const done = await enter($, c, it)
    await update($, promptAtom, () => '')
    $.clock.after(PUT_BACK_MS, () => void settleBox($, false))
    return { drop: done }
  }).catch(($, e, next) => (next.called ? next(e) : { drop: 'The answer session could not check this prompt, so it was not sent.' }))

  // A discussion message's turn: the turn that starts with its text answers
  // it. (Should the text not match, as when the engine expands it, the oldest
  // message still waiting takes the turn, so a reply is never lost.)
  on('turn.start', async ($, e, next) => {
    const waiting = e.agentId ? [] : await read($, awaitingAtom)
    if (waiting.length && e.text.trim()) {
      const exact = waiting.findIndex(w => w.text === e.text.trim())
      const i = exact >= 0 ? exact : 0
      const id = waiting[i]!.id
      await update($, awaitingAtom, w => w.filter((_, j) => j !== i))
      await update($, replyTurnsAtom, m => ({ ...m, [e.turnId]: id }))
    }
    return next(e)
  }).catch(($, e, next) => next(e))

  // The turn's final text is the reply, kept with its question so a
  // rephrasing or a question for the asker reads the whole discussion.
  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    const id = e.agentId ? undefined : (await read($, replyTurnsAtom))[e.turnId]
    if (id) {
      await update($, replyTurnsAtom, m => without(m, e.turnId))
      const text = e.answer.trim()
      await addTurn(
        $,
        id,
        e.reason === 'answer' && text
          ? { who: 'model', text }
          : { who: 'error', text: e.reason === 'aborted' ? 'Stopped before it answered.' : `No answer (${e.reason}). Send again to retry.` },
      )
      await think($, id, undefined)
    }
    return done
  }).catch(($, e, next) => next(e))

  // The answer session is the band above the prompt: as wide as the terminal,
  // as tall as the engine lets it be (in fullscreen, what half the screen
  // leaves above the prompt; on the main screen, the screen less the prompt).
  // Every row is fitted to that height, so nothing scrolls out of sight.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    // A drawing never writes state; the module's own flag is not state, and
    // Enter and the hint line read it.
    surveyUp = e.props.hasSurvey
    if (e.props.hasSurvey || !(await read($, openAtom))) return next(e)
    const { Box, Text, Button, Link } = $.ui.resolve(e)
    const cursor = await read($, cursorAtom)
    const answers = await read($, answersAtom)
    const draft = await read($, promptAtom)
    const flash = await read($, flashAtom)
    const talking = await read($, talkingAtom)
    const talks = await read($, talksAtom)
    const thinking = await read($, thinkingAtom)
    const rephrasedAll = await read($, rephrasedAtom)
    const originals = await read($, originalAtom)
    const askingAll = await read($, askingAtom)
    const returnedAll = await read($, returnedAtom)

    // ── the room ─────────────────────────────────────────────────────────
    //
    // Fullscreen hands the band what half the screen leaves above the prompt.
    // The main screen hands it the terminal's height, which would push the
    // band's top off the screen: there it takes the screen less the prompt
    // box, its rules and the footer.
    const cols = Math.max(30, e.props.bodyColumns)
    const vp = e.viewport
    const isFullscreen = vp?.isFullscreen === true
    const promptRows = vp ? wrap(draft, Math.max(10, vp.columns - 4)).length : 1
    const H = Math.max(5, isFullscreen || !vp ? e.props.maxRows : Math.min(e.props.maxRows, vp.rows - 5 - promptRows))
    // Two columns on a wide strip: the question on the left stays put, the
    // right is where the work happens (the answers, the discussion, the
    // question for the asker). One column on a narrow one.
    const isWide = cols >= 100
    const GUTTER = 3
    const LW = isWide ? Math.min(96, Math.floor((cols - GUTTER) * 0.47)) : cols
    const RW = isWide ? Math.min(110, cols - GUTTER - LW) : cols
    const hasRule = H >= 14
    // Rows for the body: the bar on top, the keys at the bottom.
    const B = H - 2 - (hasRule ? 1 : 0)

    const N = QUESTIONS.length
    const at = Math.min(Math.max(cursor, 0), N)
    const base = at < N ? QUESTIONS[at] : undefined
    const count = (kind: Answer['kind']) => QUESTIONS.filter(one => answers[one.id]?.kind === kind).length
    const relayed = count('answer')
    const deferred = count('defer')
    const waiting = count('wait')
    const fresh = N - relayed - deferred - waiting

    // What Enter would do with the prompt box's text, and the commands on
    // screen; a click on one does what typing its key and Enter does.
    const c = await snapshot($)
    const it = intent(c, draft)
    const cmds = commands(c)
    const run = (doing: Promise<unknown>) => void doing.catch(() => undefined)
    const isTalking = !!base && talking === base.id

    // ── rows ─────────────────────────────────────────────────────────────
    //
    // Everything below the bar is built as rows, each exactly one terminal
    // row tall, so a view can count what it draws and give things up, in a
    // fixed order, until it fits.
    type Row = RenderElement
    const blank = (): Row => <Text> </Text>
    const plain = (text: string, style: { dim?: boolean; bold?: boolean; color?: string } = {}): Row => (
      <Text wrap="truncate-end" dimColor={style.dim} bold={style.bold} color={style.color}>
        {text || ' '}
      </Text>
    )
    // A section's label: small capitals, dim; a name after it keeps its case.
    const label = (words: string, name?: string): Row => (
      <Text wrap="truncate-end">
        <Text dimColor>{words.toUpperCase()}</Text>
        {name ? <Text> {name}</Text> : ''}
      </Text>
    )
    /** Groups of rows, `gaps[i]` blank rows before group i + 1 (one number: everywhere); an empty group vanishes with its gap. */
    const stack = (groups: Row[][], gaps: number | number[]): Row[] => {
      const out: Row[] = []
      groups.forEach((group, i) => {
        if (!group.length) return
        const g = typeof gaps === 'number' ? gaps : (gaps[Math.min(i - 1, gaps.length - 1)] ?? 0)
        if (out.length) for (let k = 0; k < g; k++) out.push(blank())
        out.push(...group)
      })
      return out
    }
    /** The first trim whose rows fit `budget`; the last, cut to it, when none does. */
    const fit = (build: (t: Trim) => Row[], budget: number): Row[] => {
      for (const t of TRIMS) {
        const rows = build(t)
        if (rows.length <= budget) return rows
      }
      const rows = build(TRIMS[TRIMS.length - 1]!)
      return [...rows.slice(0, Math.max(0, budget - 1)), plain('⋯', { dim: true })]
    }
    // What the relay account posts, exactly: "User says: …" behind a bar, at
    // most `max` lines, the last cut with an ellipsis.
    const bubble = (text: string | undefined, color: string, width: number, max: number): Row[] => {
      let lines = wrap(PREFIX + (text ?? '…'), Math.max(10, width - 2))
      if (lines.length > max) lines = [...lines.slice(0, Math.max(1, max) - 1), cut(lines.slice(Math.max(1, max) - 1).join(' '), width - 3)]
      return lines.map((line, i) => (
        <Text wrap="truncate-end">
          <Text color={color}>│ </Text>
          {i === 0 ? <Text dimColor>{PREFIX}</Text> : ''}
          <Text dimColor={!text}>{i === 0 ? line.slice(PREFIX.length) : line}</Text>
        </Text>
      ))
    }

    // ── the bar: the session, the queue as dots, where this is ──────────

    const dots = QUESTIONS.map((one, i) => {
      const a = answers[one.id]
      const glyph = i === at && !a ? (isTalking ? '◇' : '◉') : !a ? '○' : a.kind === 'answer' ? '●' : a.kind === 'defer' ? '◐' : '◌'
      const color = i === at ? ACCENT : !a ? RULE : a.kind === 'answer' ? DONE : a.kind === 'defer' ? LATER : ACCENT
      // A click on a dot opens that question.
      return (
        <Button key={`dot:${i}`} plain onPress={() => run(goTo($, i))}>
          <Text color={color} bold={i === at} dimColor={a?.kind === 'wait' && i !== at}>
            {glyph}
          </Text>
        </Button>
      )
    })
    const toSummary = (
      <Button key="dot:summary" plain onPress={() => run(goTo($, N))}>
        <Text color={at === N ? ACCENT : undefined} bold={at === N} dimColor={at !== N}>
          summary
        </Text>
      </Button>
    )
    const tally = [`${fresh} new`, `${relayed} relayed`, `${deferred} for later`, ...(waiting ? [`${waiting} waiting`] : [])].join(' · ')
    const where = [...(base ? [`${at + 1} of ${N}`] : []), ...(isTalking ? (cols >= 120 ? ['talking it through'] : []) : cols >= 120 || !base ? [tally] : [])].join(' · ')
    const bar = (
      <Box height={1} overflow="hidden" justifyContent="space-between" width={cols} gap={2}>
        <Box gap={2} flexShrink={0}>
          <Text bold>Answer session</Text>
          <Box gap={1}>{dots}</Box>
          {toSummary}
          <Text dimColor>{where}</Text>
        </Box>
        <Text dimColor wrap="truncate-end">
          {BUILD}
        </Text>
      </Box>
    )

    // ── the keys: what one letter and Enter does, each a click away ──────

    const keyText = (key: string, what: string) => (
      <Text>
        <Text color={ACCENT}>{key}</Text>
        <Text dimColor>: {what}</Text>
      </Text>
    )
    const keyButton = (cmd: Command) => (
      <Button key={`cmd:${cmd.key}`} plain onPress={() => run(pressKey($, cmd.key))}>
        {keyText(cmd.key, cmd.what)}
      </Button>
    )
    // The last thing done, or why Enter would refuse what is typed.
    const status =
      it.kind === 'refused' ? (
        <Text color={LATER} wrap="truncate-end">
          {it.why}
        </Text>
      ) : flash ? (
        <Text color={DONE} wrap="truncate-end">
          ✓ {flash}
        </Text>
      ) : null
    const keys = (hints: [string, string][], shown: Command[]) => (
      <Box height={1} overflow="hidden" justifyContent="space-between" width={cols} gap={3}>
        <Box columnGap={3} flexShrink={0}>
          {hints.map(([key, what]) => keyText(key, what))}
          {shown.filter(cmd => cmd.key !== 'q').map(keyButton)}
        </Box>
        <Box gap={3} flexShrink={1} justifyContent="flex-end">
          {status}
          {keyButton({ key: 'q', what: 'close' })}
        </Box>
      </Box>
    )

    // The band at its full height; a body of fewer `rows` makes it shorter
    // and gives the conversation above the rest. The rule on top parts the
    // band from the conversation, and is the first row a short band gives up.
    const frame = (body: Row, hints: [string, string][], shown: Command[], rows = B) => (
      <Box flexDirection="column" width={cols} height={rows === B ? H : rows + 2 + (hasRule ? 1 : 0)}>
        {hasRule && <Text color={RULE}>{'─'.repeat(cols)}</Text>}
        {bar}
        <Box flexDirection="column" height={rows} overflow="hidden">
          {body}
        </Box>
        {keys(hints, shown)}
      </Box>
    )
    const column = (rows: Row[], width: number) => (
      <Box flexDirection="column" width={width} flexShrink={0}>
        {rows}
      </Box>
    )
    // Rows left over sit two fifths above the content, three below, so a
    // tall band (the main screen's) holds it near the middle, not at the top.
    const lift = (rows: number) => Array.from({ length: Math.floor((B - Math.min(B, rows)) * 0.4) }, blank)
    // Wide: the question, a thin rule, the work beside it, tops aligned.
    const columns = (left: Row[], right: Row[], LW: number, RW: number, centred = true, rows = B) => {
      const pad = centred ? lift(Math.max(left.length, right.length)) : []
      return (
      <Box flexDirection="row" height={rows}>
        {column([...pad, ...left], LW)}
        <Box flexDirection="column" width={GUTTER} flexShrink={0} alignItems="center">
          {Array.from({ length: rows }, () => (
            <Text color={RULE}>│</Text>
          ))}
        </Box>
        {column([...(centred ? lift(Math.max(left.length, right.length)) : []), ...right], RW)}
      </Box>
      )
    }

    // ── the summary: every question handled, or the end of the queue ──────

    if (!base) {
      const settled = fresh === 0 && deferred === 0 && waiting === 0
      const head =
        fresh > 0
          ? `${fresh} question${fresh === 1 ? '' : 's'} still new`
          : deferred > 0
            ? `Nothing new. ${deferred} for later.`
            : waiting > 0
              ? `Nothing new. ${waiting} waiting for a reply.`
              : 'All caught up.'
      // Each handled question, in queue order; a click opens it.
      const handled = QUESTIONS.map((one, i) => ({ one, i, a: answers[one.id] })).filter(x => x.a)
      const W = Math.min(cols, 160)
      // Who and where in columns of their own, so the answers line up.
      const whoWidth = Math.min(20, Math.max(...handled.map(x => x.one.asker.name.length), 0) + 2)
      const placeWidth = Math.min(36, Math.max(...handled.map(x => x.one.where.length), 0) + 2)
      const itemRow = ({ one, i, a }: (typeof handled)[number]): Row => {
        const glyph = a!.kind === 'answer' ? '●' : a!.kind === 'defer' ? '◐' : '◌'
        const color = a!.kind === 'answer' ? DONE : a!.kind === 'defer' ? LATER : ACCENT
        const who = cut(one.asker.name, whoWidth - 2).padEnd(whoWidth)
        const place = cut(one.where, placeWidth - 2).padEnd(placeWidth)
        const what = a!.kind === 'answer' ? `│ ${PREFIX}${a!.text}` : a!.kind === 'defer' ? '│ for later' : `│ asked: ${a!.text}`
        const room = Math.max(0, W - 2 - who.length - place.length)
        return (
          <Box height={1} overflow="hidden">
            <Button key={`sum:${one.id}`} plain onPress={() => run(goTo($, i))}>
              <Text color={color}>{glyph} </Text>
              <Text bold>{who}</Text>
              <Text dimColor>{place}</Text>
              <Text>{cut(what, room)}</Text>
            </Button>
          </Box>
        )
      }
      const top: Row[] = [
        plain(`${settled ? '✓  ' : ''}${head}`, { bold: true, color: settled ? DONE : undefined }),
        plain(`${relayed} of ${N} relayed this session${waiting ? ` · ${waiting} back with their askers` : ''}`, { dim: true }),
      ]
      const room = Math.max(0, B - top.length - 1)
      const list: Row[] =
        handled.length > room
          ? [...handled.slice(0, Math.max(0, room - 1)).map(itemRow), plain(`and ${handled.length - Math.max(0, room - 1)} more: the dots above open each`, { dim: true })]
          : handled.map(itemRow)
      return frame(<Box flexDirection="column">{stack([top, list], 1)}</Box>, [], cmds)
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
    const open = !isRelayed && !isWaiting
    const message = it.kind === 'option' || it.kind === 'relay' ? it.text : undefined
    const isHuman = !q.options
    const turns = talks[q.id] ?? []
    const busy = thinking[q.id]
    const postsAs = `on ${SURFACE_NAME[q.surface]} as`

    // Where it was asked (a link to it) and by whom: two rows, or one.
    const asked =
      q.asker.replyTo !== undefined
        ? `replied to ${q.asker.replyTo}`
        : q.asker.kind === 'agent'
          ? `asks, an agent via ${q.asker.via ?? 'the inquisitor'}`
          : 'asks'
    const state =
      answer?.kind === 'defer' ? <Text color={LATER}>for later · </Text> : isWaiting ? <Text color={ACCENT}>waiting for {q.asker.name} · </Text> : ''
    const provenance = (lines: 0 | 1 | 2): Row[] => {
      if (lines === 0) return []
      const source = (
        <Box gap={2} flexShrink={0}>
          <Text bold>{SURFACE_NAME[q.surface]}</Text>
          <Link href={q.link}>{q.where}</Link>
        </Box>
      )
      if (lines === 2) {
        return [
          <Box height={1} overflow="hidden" gap={2}>
            {source}
            <Text dimColor wrap="truncate-end">
              {state}
              {q.age} ago
            </Text>
          </Box>,
          <Text wrap="truncate-end">
            <Text color={ACCENT} bold>
              {q.asker.name}
            </Text>
            <Text dimColor> {asked}</Text>
          </Text>,
        ]
      }
      return [
        <Box height={1} overflow="hidden" gap={2}>
          {source}
          <Text wrap="truncate-end">
            <Text color={ACCENT} bold>
              {q.asker.name}
            </Text>
            <Text dimColor>
              {' '}
              · {state}
              {q.age} ago
            </Text>
          </Text>
        </Box>,
      ]
    }
    const questionRows = (width: number): Row[] => wrap(q.text, width).map(line => plain(line, { bold: true }))
    const changeMark: Row[] = changed
      ? [
          <Box height={1} overflow="hidden" gap={3}>
            <Text dimColor wrap="truncate-end">
              {showOriginal
                ? 'The original question, as asked'
                : rephrased
                  ? '↻ Rephrased after your discussion'
                  : `↻ Revised by ${q.asker.name} after your question`}
            </Text>
            <Button key="original" plain dimColor onPress={() => run(pressKey($, 'o'))}>
              {showOriginal ? 'o: show it as asked now' : 'o: show the original'}
            </Button>
          </Box>,
        ]
      : []

    // ── the question view ────────────────────────────────────────────────

    // The left column: where it came from, the question, what it rests on.
    const questionColumn = (t: Trim, width: number): Row[] => {
      // Beside an asker's reply the context matters less than the reply: it
      // gives way a step sooner, and the reply is never cut.
      const contextFit = returned ? (t.context === 'full' ? 'line' : 'none') : t.context
      const context: Row[] =
        !q.context || contextFit === 'none'
          ? []
          : q.asker.replyTo !== undefined
            ? contextFit === 'line'
              ? [plain(`Their reply is to: ${q.context}`, { dim: true })]
              : [plain('Their reply is to:', { dim: true }), ...wrap(q.context, width - 2).map(line => plain(`│ ${line}`, { dim: true }))]
            : contextFit === 'line'
              ? [plain(q.context)]
              : wrap(q.context, width).map(line => plain(line))
      // The asker's reply to a clarifying question, quoted and attributed.
      const reply: Row[] = returned
        ? [
            <Text wrap="truncate-end">
              <Text color={ACCENT}>↩ </Text>
              <Text bold>{q.asker.name}</Text>
              <Text dimColor> replied to your question</Text>
            </Text>,
            ...(t.reply === 'full' ? wrap(`You asked: ${returned.asked}`, width - 2).map(line => plain(`  ${line}`, { dim: true })) : []),
            ...wrap(returned.reply, width - 2).map(line => (
              <Text wrap="truncate-end">
                <Text dimColor>│ </Text>
                {line}
              </Text>
            )),
          ]
        : []
      const related: Row[] = [
        ...(q.related && t.related
          ? [
              <Text wrap="truncate-end">
                <Text dimColor>Related </Text>
                {q.related}
              </Text>,
            ]
          : []),
        ...(q.answered
          ? [
              <Text wrap="truncate-end">
                <Text color={LATER}>Possibly answered already </Text>
                {q.answered.decision}
              </Text>,
              ...(open && t.related
                ? [
                    <Box height={1} overflow="hidden">
                      <Button key="cite" plain dimColor onPress={() => run(pressKey($, 'c'))}>
                        c: reply by citing it
                      </Button>
                    </Box>,
                  ]
                : []),
            ]
          : []),
      ]
      const near = Math.min(1, t.gap)
      return stack([provenance(t.provenance), [...changeMark, ...questionRows(width)], context, reply, related], [t.gap, near, near, near])
    }

    // The right column: the answers to choose from, then what will post.
    const answerColumn = (t: Trim, width: number): Row[] => {
      if (isRelayed || isWaiting) {
        const head: Row = isRelayed ? (
          <Text wrap="truncate-end">
            <Text color={DONE}>✓ </Text>
            <Text dimColor>{`Relayed ${postsAs}`.toUpperCase()}</Text> {q.relayAs}
          </Text>
        ) : (
          <Text wrap="truncate-end">
            <Text color={ACCENT}>◌ </Text>
            <Text dimColor>{`Waiting for ${q.asker.name}. Asked ${postsAs}`.toUpperCase()}</Text> {q.relayAs}
          </Text>
        )
        return [head, ...bubble(answer.text, isRelayed ? DONE : ACCENT, width, t.bubble), ...(isRelayed && t.logNote ? logNote(width) : [])]
      }
      // Each option: a gutter that marks the chosen one, the number and the
      // label (a click puts the number in the prompt box, as typing it
      // would), what it changes beneath, dim.
      const options: Row[] = (q.options ?? []).flatMap((o, i) => {
        const isChosen = it.kind === 'option' && it.index === i
        const mark = <Text color={ACCENT}>{isChosen ? '▌ ' : '  '}</Text>
        const head = (
          <Box height={1} overflow="hidden">
            {mark}
            <Button key={`opt:${q.id}:${i}`} plain onPress={() => run(putInBox($, String(i + 1)))}>
              <Text color={ACCENT}>{i + 1}</Text>
              <Text dimColor>: </Text>
              <Text bold color={isChosen ? ACCENT : undefined}>
                {cut(o.label, width - 5 - (i === 0 ? 15 : 0))}
              </Text>
            </Button>
            {i === 0 ? <Text color={ACCENT}>{'  ★ recommended'}</Text> : null}
          </Box>
        )
        const effect =
          t.effects === 'none' ? [] : t.effects === 'line' ? [cut(`→ ${o.effect}`, width - 5)] : wrap(o.effect, width - 7).map((line, j) => (j ? '  ' : '→ ') + line)
        return [
          ...(i > 0 && t.optionGap ? [blank()] : []),
          head,
          ...effect.map(line => (
            <Text wrap="truncate-end">
              {mark}
              <Text dimColor>
                {'   '}
                {line}
              </Text>
            </Text>
          )),
        ]
      })
      // Typing in the prompt box is the own words: this row says so, and marks
      // it chosen while the box holds an answer.
      const isWriting = it.kind === 'relay'
      const ownWords = (
        <Text wrap="truncate-end">
          <Text color={ACCENT}>{isWriting ? '▌ ' : '  '}</Text>
          <Text bold={isWriting} color={isWriting ? ACCENT : undefined} dimColor={!isWriting}>
            {isHuman ? `Reply to ${q.asker.name}: type it in the prompt box` : 'Or type your own answer in the prompt box'}
          </Text>
        </Text>
      )
      const choose: Row[] = isHuman
        ? [ownWords]
        : [...options, ...(t.ownWords || isWriting ? [...(t.optionGap ? [blank()] : []), ownWords] : [])]
      // What will post, exactly, and the Relay button once there is something to relay.
      const relayButton = message ? (
        <Button key={`send:${q.id}`} variant="primary" onPress={() => run(relayPressed($, q, message))}>
          Relay
        </Button>
      ) : null
      const preview: Row[] =
        t.preview === 'line'
          ? [
              <Box height={1} overflow="hidden" gap={2}>
                <Box flexShrink={1}>{bubble(message, message ? ACCENT : RULE, width - 12, 1)}</Box>
                {relayButton}
              </Box>,
            ]
          : [
        <Box height={1} overflow="hidden" gap={2}>
          <Box flexShrink={1}>{label(message ? `Will post ${postsAs}` : `Posts ${postsAs}`, q.relayAs)}</Box>
          {relayButton}
        </Box>,
        ...bubble(message, message ? ACCENT : RULE, width, t.bubble),
        ...(message && t.logNote ? logNote(width) : []),
      ]
      return stack([t.label && !isHuman ? [label('Choose an answer')] : [], choose, preview], [0, t.gap])
    }
    // What the real skill logs beside an answer to a changed question.
    function logNote(width: number): Row[] {
      if (!changed || showOriginal) return []
      const summary = rephrased?.summary ? `, and the discussion in a line: “${rephrased.summary.replace(/[.\s]+$/, '')}.”` : '.'
      return wrap(`Logged with the answer in the real skill, not posted: the question as ${rephrased ? 'rephrased' : 'revised'}${summary}`, width - 2).map(line =>
        plain(`  ${line}`, { dim: true }),
      )
    }

    if (!isTalking) {
      const options = q.options ?? []
      const hints: [string, string][] = !open || isHuman ? [] : [[`1–${options.length}`, 'choose']]
      const one = isWide ? [] : fit(t => stack([questionColumn(t, cols), answerColumn(t, cols)], Math.min(1, t.gap)), B)
      const body = isWide ? (
        columns(fit(t => questionColumn(t, LW), B), fit(t => answerColumn(t, RW), B), LW, RW)
      ) : (
        <Box flexDirection="column">{[...lift(one.length), ...one]}</Box>
      )
      return frame(body, hints, cmds)
    }

    // ── talking it through: this question only, the queue waits ──────────
    //
    // The discussion is the conversation above the band: each message goes to
    // the session's model with the question attached, and the reply shows
    // there, the model free to read the thread and the code first. The band
    // keeps the question in view and says what Enter will do, and shrinks to
    // that, so the conversation gets the rest of the screen.

    const composing = !!askingAll[q.id]
    const askText = it.kind === 'ask' ? it.text : ''
    // The question stays in view, close packed so the band stays short:
    // where, the question, its options in a line each.
    const pinned = (width: number, budget: number): Row[] => {
      const optionRows = (q.options ?? []).map((o, i) => plain(`${i + 1}  ${o.label}${i === 0 ? '  ★' : ''}`, { dim: true }))
      const tight = stack([provenance(1), questionRows(width), optionRows], 0)
      if (tight.length <= budget) return tight
      const lines = wrap(q.text, width)
      const room = Math.max(1, budget - 1)
      return [...provenance(1), ...lines.slice(0, room - 1).map(line => plain(line, { bold: true })), plain(cut(lines.slice(room - 1).join(' '), width), { bold: true })]
    }
    // The question for the asker, previewed as it will post in their thread.
    const compose = (width: number): Row[] => [
      <Box height={1} overflow="hidden" gap={2}>
        <Box flexShrink={1}>{label(`Ask ${q.asker.name}, in the thread`)}</Box>
        {askText && !busy ? (
          <Button key={`ask:${q.id}`} variant="primary" onPress={() => run(askPressed($, q, askText))}>
            Send
          </Button>
        ) : null}
      </Box>,
      ...bubble(askText || undefined, askText ? ACCENT : RULE, width, Math.max(2, B - 5)),
      ...wrap(
        busy === 'draft'
          ? 'Drafting a question into the prompt box…'
          : askText
            ? `Will post ${postsAs} ${q.relayAs}. Enter sends exactly this; the question waits for the reply, the queue moves on.`
            : `Type your question for ${q.asker.name} in the prompt box.`,
        width,
      ).map(line => plain(line, { dim: true })),
    ]
    // Where the discussion stands, and what Enter would do with the box.
    const talkState = (width: number): Row[] => {
      const head: Row = (
        <Text wrap="truncate-end">
          <Text color={ACCENT}>◇ </Text>
          <Text dimColor>TALKING IT THROUGH</Text>
          <Text dimColor> · in the conversation above</Text>
        </Text>
      )
      if (composing) return [head, ...compose(width)]
      // A number chooses an answer here too: what it would post, and Relay.
      if (it.kind === 'option') {
        return [
          head,
          <Box height={1} overflow="hidden" gap={2}>
            <Box flexShrink={1}>{label(`Will post ${postsAs}`, q.relayAs)}</Box>
            <Button key={`send:${q.id}`} variant="primary" onPress={() => run(relayPressed($, q, it.text))}>
              Relay
            </Button>
          </Box>,
          ...bubble(it.text, ACCENT, width, 2),
        ]
      }
      const said = turns.filter(turn => turn.who === 'you').length
      const last = turns[turns.length - 1]
      const state: Row[] =
        busy === 'reply'
          ? [plain('◌ Claude is answering above…', { color: ACCENT })]
          : busy === 'rephrase'
            ? [plain('◌ Rephrasing the question from your discussion…', { color: ACCENT })]
            : last?.who === 'error'
              ? wrap(last.text, width).map(line => plain(line, { color: LATER }))
              : said
                ? wrap(
                    `${said} message${said === 1 ? '' : 's'} so far. Ask more, or: r rephrases the question and asks it again; a asks ${q.asker.name} in the thread${q.options ? '; a number chooses an answer' : ''}.`,
                    width,
                  ).map(line => plain(line, { dim: true }))
                : wrap(
                    `Type what you want to understand. Claude gets the question with it and may read the thread and the code before it answers; the reply shows above. The rest of the queue waits.`,
                    width,
                  ).map(line => plain(line, { dim: true }))
      const pending: Row[] =
        it.kind === 'say'
          ? [
              <Text wrap="truncate-end">
                <Text color={ACCENT} bold>
                  {'you'.padEnd(SPEAKER)}
                </Text>
                <Text dimColor>{it.text} ⏎</Text>
              </Text>,
            ]
          : []
      return [head, ...state, ...pending]
    }

    if (isWide) {
      const right = talkState(RW)
      const left = pinned(LW, Math.max(B, right.length))
      const rows = Math.min(B, Math.max(left.length, right.length))
      return frame(columns(left.slice(0, rows), right.slice(0, rows), LW, RW, false, rows), [], cmds, rows)
    }
    // One column: the question cut to two lines, where the discussion stands under it.
    const rows1 = [...pinned(cols, 3), ...talkState(cols)].slice(0, B)
    return frame(<Box flexDirection="column">{rows1}</Box>, [], cmds, rows1.length)
  })
}

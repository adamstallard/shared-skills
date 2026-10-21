import { atom, read, update } from 'claude-code'
import type { EngineInterface, ModelCompleteResult, Register, RenderElement } from 'claude-code'

import type { Answer, Declining, Filter, Returned, Revision, Turn, WontReason } from '../types'

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
  /** Where that decision is; prototype URLs past the thread's own are made up. */
  relatedLink?: string
  /**
   * A decision that may already answer it, and a reply citing it. With
   * `hasAuthority` it is a recorded answer with authority: the inquisitor's
   * filter 1 answers the question by itself, posting the citation.
   */
  answered?: { decision: string; cite: string; link?: string; hasAuthority?: true }
  /**
   * An agent's question that clearly fails filter 2, 3 or 4: the session
   * replied by itself with that filter's action when it arrived.
   */
  handled?: { filter: 2 | 3 | 4 }
  /**
   * A person's question that looks as though it fails filter 2, 3 or 4:
   * the verdict is only suggested, with the reply agreeing would post.
   */
  verdict?: { filter: 2 | 3 | 4; why: string; reply: string }
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
    relatedLink: 'https://github.com/adamstallard/igor/pull/216#decision-3',
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
    context: 'QA signed off this morning, and the flag switches off in minutes. Waiting for the review adds three days.',
    verdict: {
      filter: 4,
      why: 'The flag switches off in minutes, so either choice is easy to undo.',
      reply: "Your call: either way is cheap to switch, since the flag turns off in minutes.",
    },
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
    relatedLink: 'https://github.com/adamstallard/igor/issues/212',
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
      link: 'https://github.com/adamstallard/igor/pull/216#decision-10',
      decision: "#216 decision 10: the run id links to the run's ledger row",
      cite: "See decision 10 in #216: the run id links to the run's ledger row, which an item number cannot.",
      hasAuthority: true,
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
    answered: {
      link: 'https://discord.com/channels/example/ops/runbook',
      decision: '#ops runbook: staging follows prod freezes',
      cite: 'The runbook has staging follow prod freezes, so yes: hold staging deploys until the migration finishes.',
    },
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
  {
    id: 'sync-log-level',
    surface: 'discord',
    where: '#igor-dev',
    link: 'https://discord.com/channels/example/igor-dev',
    asker: { name: 'Igor (worker)', kind: 'agent', via: 'its inquisitor role' },
    age: '5m',
    text: 'Should the questions-branch sync log each file it skips at debug or at info level?',
    context: 'One line in sync.go sets it, and any later release can change it.',
    options: [
      { label: 'Debug', effect: 'Quiet logs; skips show with --debug.' },
      { label: 'Info', effect: 'Every skip in the normal log.' },
    ],
    handled: { filter: 4 },
    relayAs: 'adam-relay#4127',
  },
]

/** The inquisitor's filters, as the answer session names them and acts on them. */
const FILTERS: Record<Filter, { name: string; action: string; verdict: string }> = {
  1: { name: 'already answered', action: 'here is the recorded answer', verdict: 'looks already answered' },
  2: { name: 'can wait', action: 'carry on without it, and list it as not done', verdict: 'looks like it can wait' },
  3: { name: 'only one option has merit', action: 'take the option that has merit', verdict: 'looks like only one option has merit' },
  4: { name: 'cheap to reverse', action: "pick one, it's cheap to switch", verdict: 'looks cheap to reverse' },
}

/**
 * Why Adam won't answer, as he chooses it, and what follows (`will`, shown
 * while choosing). Prototype only: nothing is written or posted.
 */
const REASONS: Record<WontReason, { label: string; will: string }> = {
  1: {
    label: 'The conversation is over',
    will: 'The real skill ends the thread: later replies there stop counting as questions.',
  },
  2: {
    label: 'Not a question',
    will: 'It was picked up by mistake. The real skill writes a lesson candidate against how the question was found.',
  },
  3: {
    label: 'The inquisitor should have handled it',
    will: "Choose the filter that should have stopped it, and the session answers for the inquisitor with that filter's reply. The real skill logs a miss against that filter.",
  },
}

/**
 * Reasons 1 and 2 close the question with nothing posted: what the real
 * skill logged (`did`), and what reopening withdraws (`undo`). Reason 3
 * posts instead, so it closes as handled (`answerForInquisitor`).
 */
const CLOSED: Record<1 | 2, { did: string; undo: string }> = {
  1: {
    did: 'In the real skill the thread is ended: later replies there no longer count as questions.',
    undo: 'replies in its thread count as questions again',
  },
  2: {
    did: 'In the real skill a lesson candidate is written against how the question was found.',
    undo: 'the real skill withdraws the lesson candidate',
  },
}

// The two prefixes the session posts with by itself, and only these: a
// recorded answer with authority (filter 1), and a filter's action on an
// agent's question (filters 2 to 4). Adam's reply for the inquisitor
// (won't-answer reason 3) carries them too, on his Enter. Everything else
// posts on Adam's Enter, as "User says: ".
const RECORDED = 'Recorded answer: '
const INQUISITOR = 'Inquisitor: '

/**
 * What a filter's reply says after its prefix: for filter 1, where the
 * answer is recorded; for 2 to 4, the filter and its action, fixed.
 */
function filterReply(n: Filter, place = ''): string {
  return n === 1 ? place : `Filter ${n} (${FILTERS[n].name}): ${FILTERS[n].action}.`
}

/** What the session did by itself as the questions arrived: filter 1's answers and the handled agents' questions. */
const ARRIVED: Record<string, Answer> = Object.fromEntries(
  QUESTIONS.flatMap((one): [string, Answer][] =>
    one.answered?.hasAuthority
      ? [[one.id, { kind: 'recorded', text: one.answered.cite }]]
      : one.handled
        ? [[one.id, { kind: 'handled', filter: one.handled.filter, text: filterReply(one.handled.filter) }]]
        : [],
  ),
)

/**
 * The prefix a post carries: the session's own two, until Adam edits it
 * (a filter-1 reply he posted for the inquisitor is a recorded answer); his,
 * "User says: ".
 */
function prefixOf(a: Answer): string {
  if (a.edited) return PREFIX
  return a.kind === 'recorded' || (a.kind === 'handled' && a.filter === 1) ? RECORDED : a.kind === 'handled' ? INQUISITOR : PREFIX
}

/** Whether a question has a post in its thread that Adam can edit. */
const isPosted = (a?: Answer) => a?.kind === 'answer' || a?.kind === 'wait' || a?.kind === 'recorded' || a?.kind === 'handled'

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
/** Each state's dot, in the bar and the summary: ○ new, ◉ on screen and ◇ in a conversation are drawn beside these. */
const GLYPH: Record<Answer['kind'], string> = { answer: '●', defer: '◐', wait: '◌', wont: '⊘', recorded: '◎', handled: '◈' }
const TONE: Record<Answer['kind'], string> = { answer: DONE, defer: LATER, wait: ACCENT, wont: RULE, recorded: DONE, handled: DONE }

// Prototype only: shown in the top bar, so a tester can tell which build is
// loaded. v0.1-N, N the number of commits in the prototype repository once
// this build is committed.
const BUILD = 'v0.1-29'
const PREFIX = 'User says: '
// The tool the session's model calls to put a drafted reply in the prompt box.
const PROPOSE_TOOL = 'mcp__answer-session__propose_reply'
// The key row's right end: the same place on every screen.
const AT_RIGHT = ['b', 'n', 'q']
const SPEAKER = 8
const cursorAtom = atom({ plugin: 'answer-session', key: 'cursor' } as const, 0)
const answersAtom = atom({ plugin: 'answer-session', key: 'answers' } as const, ARRIVED as Record<string, Answer>)
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
const editingAtom = atom({ plugin: 'answer-session', key: 'editing' } as const, {} as Record<string, true>)
const returnedAtom = atom({ plugin: 'answer-session', key: 'returned' } as const, {} as Record<string, Returned>)
const openAtom = atom({ plugin: 'answer-session', key: 'isOpen' } as const, false)
const decliningAtom = atom({ plugin: 'answer-session', key: 'declining' } as const, null as Declining | null)

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
/**
 * The blank rows a view can hold, the longest kept first (Adam's order):
 * above the question, above its explanation, above the choices; then above
 * the post, an asker's reply and the related decision.
 */
type Gap = 'question' | 'context' | 'choices' | 'preview' | 'reply' | 'related'
const GAP_ORDER: Gap[] = ['question', 'context', 'choices', 'preview', 'reply', 'related']

type Trim = {
  /** How many of GAP_ORDER's gaps get a blank row before rows left over fill the rest. */
  gaps: number
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
    gaps: GAP_ORDER.length,
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
    { gaps: 3 },
    { label: false },
    { optionGap: false },
    { logNote: false },
    // Adam's three gaps (question, context, choices) outlast the row the
    // hint line repeats, the context's second line and the related decision.
    { ownWords: false },
    { effects: 'line' },
    { context: 'line' },
    { related: false },
    { gaps: 2 },
    { gaps: 1 },
    { gaps: 0 },
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
  return [
    "You are helping Adam think through one question that was relayed to him in his answer session. The answer is his to decide. Your job is to help him understand it and work out what he wants, and, when he asks, to draft the reply he describes.",
    '',
    questionBlock(q, returned),
    '',
    'How to help:',
    '- Explain what is being asked and why it matters, in plain words.',
    '- Lay out the trade-offs and what each answer would change.',
    '- When what Adam wants is unclear, ask him one short question back.',
    '- Do not choose for him. If he asks which you would pick, say which way the trade-offs lean and why, and leave the choice to him.',
    "- Say when you do not know something (the code, the asker's intent) rather than guess.",
    'Write plain text for a terminal: short paragraphs, under about 120 words unless he asks for more, no headings, no bold or italics. A simple "- " list is fine.',
  ].join('\n')
}

/** The question itself, where and by whom, its options and what it rests on, for the model. */
function questionBlock(q: Question, returned?: Returned): string {
  const who =
    q.asker.kind === 'agent'
      ? `${q.asker.name}, an agent asking through ${q.asker.via ?? 'the inquisitor'}`
      : `${q.asker.name}, a person`
  const lines = [
    `The question, asked on ${SURFACE_NAME[q.surface]} in ${q.where} by ${who}, ${q.age} ago:`,
    `"${q.text}"`,
  ]
  if (q.context) lines.push(`Context the asker gave: ${q.context}`)
  if (q.asker.replyTo) lines.push(`It replies to a message Adam's relay account (${q.asker.replyTo}) posted earlier.`)
  if (q.options) {
    lines.push('', "The answers offered, the asker's recommendation first, each with what it would change:")
    q.options.forEach((o, i) => lines.push(`${i + 1}. ${o.label}${i === 0 ? ' (recommended)' : ''}: ${o.effect}`))
  } else {
    lines.push('', 'It is a free-form question from a person: Adam writes the reply, or asks you to draft it.')
  }
  if (q.related) lines.push(`Related earlier decision: ${q.related}`)
  if (q.answered) lines.push(`${q.answered.hasAuthority ? 'Answered from a recorded answer with authority' : 'Possibly answered already by'}: ${q.answered.decision}`)
  if (q.verdict) lines.push(`The answer session suggests it ${FILTERS[q.verdict.filter].verdict} (the inquisitor's filter ${q.verdict.filter}): ${q.verdict.why}`)
  if (returned) lines.push('', `Adam asked the asker: "${returned.asked}"`, `They replied: "${returned.reply}"`)
  return lines.join('\n')
}

/**
 * What rides beside a message to Claude while Adam gives where filter 1's
 * answer is recorded: he is answering for the inquisitor, and Claude helps
 * him find the place, which it may fill in with the draft tool.
 */
function placeContext(q: Question, returned?: Returned): string {
  return [
    `[Answer session] Adam's message is about a question relayed to him (${q.link}). He won't answer it himself: the inquisitor's filter 1 (already answered) should have stopped it, so he is answering for the inquisitor with a post that says "${RECORDED}" and where the answer is recorded. He is talking to you to find that place.`,
    '',
    questionBlock(q, returned),
    '',
    'How to help:',
    '- Help him find where the answer is recorded: a decision, a spec, a doc, an earlier thread. You may read the thread, the code and the specs with your tools; say what you checked.',
    '- Say when you cannot find it, rather than guess.',
    `- If he asks you to fill the place in, call ${PROPOSE_TOOL} with exactly the text that follows "${RECORDED.trim()}" in the post: the place (a link, or the decision and what it says), short. It puts it in his prompt box for him to check; it posts nothing.`,
    '- Do not post, comment, push or change anything.',
    'Plain text for a terminal: under about 120 words, no headings, no bold or italics.',
  ].join('\n')
}

/**
 * What rides beside each discussion message, unseen by Adam: the question and
 * how to help. The message goes to the session's own model, which may read
 * the thread, the code and the specs with its tools before it answers.
 */
function discussionContext(q: Question, returned?: Returned, editing?: string): string {
  return [
    editing === undefined
      ? `[Answer session] Adam's message is about a question relayed to him (${q.link}). He is talking to you about it before he answers: to understand it, to have you draft his reply, or both.`
      : `[Answer session] Adam's message is about a question relayed to him (${q.link}). He already posted in its thread and is editing that post, which now says: "${editing}". If he asks you to draft the new version, call the tool with the full replacement text.`,
    '',
    systemPrompt(q, returned),
    '- You may read the thread, the code and the specs with your tools to check a fact; say what you checked.',
    '- Do not post, comment, push or change anything: Adam answers through his answer session, not through you.',
    `- If Adam asks you to write or draft his reply, call ${PROPOSE_TOOL} with exactly the text to post (no "User says:"). It puts the draft in his prompt box on the question, for him to confirm or edit; it posts nothing.`,
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
  /** It can be answered: new, for later, or handled for Adam (he can still answer it himself). */
  open: boolean
  /** It has a post in its thread: relayed, waiting for the asker, or answered or handled for Adam. */
  posted: boolean
  /** A post is being edited in the prompt box. */
  editing: boolean
  talking: boolean
  composing: boolean
  /** Adam is declining to answer it: choosing why, or, for reason 3, answering for the inquisitor. */
  declining?: Declining
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
  if (!base) return { at, open: false, posted: false, editing: false, talking: false, composing: false, hasReply: false, changed: false, deferredAt }
  const rephrased = (await read($, rephrasedAtom))[base.id]
  const returned = (await read($, returnedAtom))[base.id]
  const q = view(base, rephrased, returned, !!(await read($, originalAtom))[base.id])
  const answer = answers[base.id]
  const talking = (await read($, talkingAtom)) === base.id
  const posted = isPosted(answer)
  const declining = await read($, decliningAtom)
  return {
    at,
    base,
    q,
    answer,
    // Handled by the session, he can still answer it; handled by his choice, it is closed.
    open: !answer || answer.kind === 'defer' || (answer.kind === 'handled' && !answer.chosen),
    posted,
    editing: posted && !!(await read($, editingAtom))[base.id],
    talking,
    composing: talking && !!(await read($, askingAtom))[base.id],
    declining: declining?.id === base.id ? declining : undefined,
    busy: (await read($, thinkingAtom))[base.id],
    hasReply: ((await read($, talksAtom))[base.id] ?? []).some(t => t.who === 'model'),
    changed: !!(rephrased ?? returned?.revised),
    deferredAt,
  }
}

/**
 * A one-letter command: its key and what it does (`runCommand` does it).
 * One that `posts` is typed into the prompt box by a click, never done by
 * it: only Enter posts.
 */
type Command = { key: string; what: string; posts?: true }

/** The commands the screen offers now, in the order the key row shows them. */
function commands(c: Ctx): Command[] {
  const q = c.q
  const close: Command = { key: 'q', what: '(q)uit' }
  const nav: Command[] = [
    { key: 'b', what: '(b)ack' },
    { key: 'n', what: '(n)ext' },
  ]
  if (!q) return [...(c.deferredAt >= 0 ? [{ key: 'r', what: '(r)eview those for later' }] : []), ...nav, close]
  if (c.composing) return [{ key: 'b', what: 'go (b)ack to the discussion' }, close]
  // In a discussion the key sits inside the words, as Adam wrote them.
  if (c.talking) {
    // Rewording and asking the asker come before an answer: not during an
    // edit, nor while finding where an answer is recorded.
    const asking = c.open && !c.editing && !c.declining && !c.busy
    return [
      { key: 't', what: 'keep (t)alking' },
      ...(asking && c.hasReply ? [{ key: 'r', what: '(r)eword the question' }] : []),
      ...(asking ? [{ key: 'a', what: '(a)sk the asker' }] : []),
      { key: 'b', what: 'go (b)ack' },
      close,
    ]
  }
  // One conversation with Claude either way: to understand the question, to
  // have a reply drafted, or both. Named for what a question without
  // suggested answers needs most.
  const talk: Command = q.options ? { key: 't', what: '(t)alk to Claude' } : { key: 'h', what: '(h)elp me answer' }
  // Declining: going back steps back, and from the first two stages keeps
  // the question open. Claude can help find where filter 1's answer is
  // recorded; `p` posts the reply for the inquisitor without a note.
  if (c.declining) {
    const stage = c.declining.stage
    return [
      ...(stage === 'place' ? [talk] : []),
      ...(stage === 'post' ? [{ key: 'p', what: '(p)ost it', posts: true as const }] : []),
      { key: 'b', what: 'go (b)ack' },
      close,
    ]
  }
  const kind = c.answer?.kind
  const own: Command[] = c.editing
    ? [
        { key: 'h', what: '(h)elp me edit' },
        { key: 'k', what: '(k)eep it as posted' },
      ]
    : kind === 'wont'
      ? [{ key: 'r', what: '(r)eopen' }]
      : kind === 'handled'
        ? [...(c.open ? [talk] : []), { key: 'e', what: '(e)dit the reply' }]
        : c.open
          ? [
              talk,
              ...(q.verdict ? [{ key: 'a', what: '(a)gree', posts: true as const }] : []),
              ...(q.answered && !q.answered.hasAuthority ? [{ key: 'c', what: '(c)ite the decision' }] : []),
              { key: 'w', what: "(w)on't answer" },
              { key: 'l', what: '(l)ater' },
            ]
          : [{ key: 'e', what: kind === 'recorded' ? '(e)dit the post' : '(e)dit your post' }]
  return [...own, ...(c.changed ? [{ key: 'o', what: '(o)riginal' }] : []), ...nav, close]
}

/** Does command `key` on the screen `c` describes, and says what it did. */
async function runCommand($: EngineInterface, c: Ctx, key: string): Promise<string> {
  const q = c.q
  if (key === 'q') return closeSession($)
  // b and n sit side by side: back and next through the queue. In a
  // discussion, or while declining, b means back a step, so the queue's
  // keys act only outside them.
  const inside = c.talking || c.composing || !!c.declining
  if (!inside && key === 'b') return stepBy($, c.at, -1)
  if (!inside && key === 'n') return stepBy($, c.at, 1)
  if (!q) return key === 'r' ? go($, c.deferredAt, 'Back to a deferred question') : ''
  if (c.composing) return key === 'b' ? backToTalk($, q) : ''
  if (c.talking) {
    switch (key) {
      case 't':
        return 'Keep typing: Claude answers above.'
      case 'r':
        return rephrase($, q)
      case 'a':
        return draftAsk($, q)
      case 'b':
        return c.declining ? backToPlace($) : backToQuestion($, q)
    }
    return ''
  }
  if (c.declining) {
    const d = c.declining
    switch (key) {
      case 'b':
        return backDecline($, q, d)
      case 't':
      case 'h':
        return d.stage === 'place' ? openTalk($, q) : ''
      case 'p':
        return d.stage === 'post' ? answerForInquisitor($, q, d, '') : ''
    }
    return ''
  }
  switch (key) {
    case 't':
    case 'h':
      return openTalk($, q)
    case 'a':
      return q.verdict ? relay($, q, q.verdict.reply) : ''
    case 'c':
      return cite($, q)
    case 'w':
      return startDecline($, q)
    case 'r':
      return reopen($, q)
    case 'l':
      return settle($, q, { kind: 'defer', text: '' }, `Later: ${q.asker.name}'s question comes back after the new ones`)
    case 'e':
      return startEdit($, q, c.answer?.text ?? '', c.answer?.kind !== 'recorded' && c.answer?.kind !== 'handled')
    case 'k':
      return stopEdit($, q)
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
  | { kind: 'edit'; text: string }
  | { kind: 'reason'; reason: WontReason }
  /** Reason 3: the filter that should have stopped it. */
  | { kind: 'filter'; filter: Filter }
  /** Filter 1: where the answer is recorded. */
  | { kind: 'place'; text: string }
  /** The note posted with the reply for the inquisitor: the miss's "what was said". */
  | { kind: 'note'; text: string }
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
    // The choices are on the question, not here: go back to answer.
    if (/^[1-9]$/.test(text)) return { kind: 'refused', why: c.declining ? 'Go (b)ack, then ⏎ on where it is recorded.' : 'To answer, go (b)ack to the question and choose there.' }
    if (text.length === 1) return { kind: 'refused', why: `${text} is not a command here: the key row lists them.` }
    return c.busy ? { kind: 'refused', why: 'Claude is still answering above: wait for it, or Esc to stop it.' } : { kind: 'say', text }
  }
  const stage = c.declining?.stage
  if (stage === 'reason') {
    return /^[1-3]$/.test(text)
      ? { kind: 'reason', reason: Number(text) as WontReason }
      : { kind: 'refused', why: 'Choose why, 1 to 3, or go (b)ack to keep it open.' }
  }
  if (stage === 'filter') {
    return /^[1-4]$/.test(text)
      ? { kind: 'filter', filter: Number(text) as Filter }
      : { kind: 'refused', why: 'Choose the filter that should have stopped it, 1 to 4, or go (b)ack to keep it open.' }
  }
  if (stage === 'place' || stage === 'post') {
    if (text.length === 1) return { kind: 'refused', why: `${text} is not a command here: the key row lists them.` }
    return stage === 'place' ? { kind: 'place', text } : { kind: 'note', text }
  }
  if (c.editing) return text === c.answer?.text.trim() ? { kind: 'refused', why: 'That is what it says now: change it, or (k)eep it as posted.' } : { kind: 'edit', text }
  if (!c.open) {
    const kind = c.answer?.kind
    return {
      kind: 'refused',
      why:
        kind === 'wait'
          ? `This question waits for ${q.asker.name}'s reply: (e)dit your post to change it.`
          : kind === 'wont'
            ? "You won't answer this question: (r)eopen it to answer."
            : kind === 'recorded'
              ? 'This question was answered for you: (e)dit the post to change it.'
              : kind === 'handled'
                ? 'You answered this for the inquisitor: (e)dit the reply to change it.'
                : 'This question is already relayed: (e)dit your post to change it.',
    }
  }
  if (q.options && /^[1-9]$/.test(text)) {
    const index = Number(text) - 1
    const option = q.options[index]
    return option ? { kind: 'option', index, text: option.label } : { kind: 'refused', why: `There is no answer ${text}.` }
  }
  // One letter is never an answer: it is a command, or a slip.
  if (text.length === 1) return { kind: 'refused', why: `${text} is not a command here: the key row lists them.` }
  return { kind: 'relay', text }
}

/** What Enter would do, in a few words for the hint line; undefined when nothing. */
function enterHint(c: Ctx, it: Intent): string | undefined {
  const q = c.q
  const surface = q ? SURFACE_NAME[q.surface] : ''
  switch (it.kind) {
    case 'option':
    case 'relay':
      return q ? `⏎ relay to ${surface}` : undefined
    case 'command':
      if (it.command.key === 'a' && q?.verdict) return `⏎ relay to ${surface}: ${FILTERS[q.verdict.filter].action}`
      if (it.command.key === 'p' && c.declining?.stage === 'post') return `⏎ post on ${surface} for the inquisitor, with no note`
      if (it.command.key === 'w') return "⏎ choose why you won't answer"
      return it.command.key === 'l' ? '⏎ ask me later, after the new ones' : `⏎ ${it.command.what.replace(/[()]/g, '')}`
    case 'say':
      return '⏎ to Claude, with the question'
    case 'ask':
      return q ? `⏎ send to ${q.asker.name}` : undefined
    case 'edit':
      return q ? `⏎ update the post on ${surface}` : undefined
    case 'reason':
      return it.reason === 3
        ? '⏎ choose which filter should have stopped it; nothing is posted yet'
        : `⏎ won't answer: ${REASONS[it.reason].label.toLowerCase()}; nothing is posted`
    case 'filter':
      return it.filter === 1 ? '⏎ filter 1: then give where the answer is recorded' : `⏎ filter ${it.filter}: then check the reply; nothing is posted yet`
    case 'place':
      return '⏎ use this place, then check the reply; nothing is posted yet'
    case 'note':
      return `⏎ post on ${surface} for the inquisitor; the note goes in the miss`
    case 'refused':
      return it.why
    case 'none':
      return undefined
  }
}

/** What Enter sends on to the session's model rather than doing in the band: a message to Claude. */
type ToModel = { kind: 'say'; text: string }
const isToModel = (it: Intent): it is ToModel => it.kind === 'say'

/**
 * Does what Enter does on the screen `c` describes, and says what it did: all
 * but what goes on to the model, which the submit hook sends.
 */
async function enter($: EngineInterface, c: Ctx, it: Exclude<Intent, ToModel>): Promise<string> {
  const q = c.q
  const d = c.declining
  switch (it.kind) {
    case 'none':
      return d?.stage === 'place' ? "Type or paste where the answer is recorded: without it, it can't post as filter 1." : 'Nothing to send.'
    case 'refused':
      return it.why
    case 'command':
      return runCommand($, c, it.command.key)
    case 'option':
    case 'relay':
      return q ? relay($, q, it.text) : ''
    case 'ask':
      return q ? sendAsk($, q, it.text) : ''
    case 'edit':
      return q ? editPost($, q, it.text) : ''
    case 'reason':
      return !q ? '' : it.reason === 3 ? startFilter($, q) : decline($, q, it.reason)
    case 'filter':
      return q ? chooseFilter($, q, it.filter) : ''
    case 'place':
      return q ? setPlace($, q, it.text) : ''
    case 'note':
      return q && d?.stage === 'post' ? answerForInquisitor($, q, d, it.text) : ''
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
  // An edit not sent is dropped with the question it was on, and so is a
  // won't-answer whose reason is not yet recorded.
  await update($, editingAtom, () => ({}))
  await update($, decliningAtom, () => null)
  await update($, cursorAtom, () => i)
  await update($, flashAtom, () => null)
  return note
}

/**
 * Puts what was posted (the answer, or the question to the asker) back in
 * the prompt box to change; Enter then updates the post where it is. The
 * real skill edits the relay's own comment or message on the surface.
 */
async function startEdit($: EngineInterface, one: Question, posted: string, isOwn: boolean): Promise<string> {
  await update($, editingAtom, () => ({ [one.id]: true as const }))
  await putInBox($, posted)
  return `${isOwn ? 'Your post' : "The session's post"} is in the prompt box: change it, then ⏎`
}

async function stopEdit($: EngineInterface, one: Question): Promise<string> {
  await update($, editingAtom, e => without(e, one.id))
  await putInBox($, '')
  return 'Kept as posted'
}

async function editPost($: EngineInterface, one: Question, text: string): Promise<string> {
  let was: Answer | undefined
  await update($, answersAtom, a => {
    was = a[one.id]
    return was ? { ...a, [one.id]: { ...was, text, edited: true as const } } : a
  })
  await update($, editingAtom, e => without(e, one.id))
  // The session's own post, once Adam edits it, is his: it says "User says: ".
  const whose = was?.kind === 'recorded' || was?.kind === 'handled' ? 'the post' : 'your post'
  const note = `Edited ${whose} on ${SURFACE_NAME[one.surface]} ${one.where}`
  await update($, flashAtom, () => note)
  return note
}

/**
 * The model's draft of Adam's reply, from its propose_reply tool: back to
 * the question view with the draft in the prompt box, where the band
 * previews the post and Enter relays it, after any edit. Posts nothing.
 */
async function proposeReply($: EngineInterface, draft: string): Promise<string> {
  if (!(await read($, openAtom))) return 'The answer session is closed, so nothing was drafted.'
  const c = await snapshot($)
  // Where filter 1's answer is recorded: the place goes in the box, for Adam
  // to check; Enter takes it, and Enter again posts the reply.
  if (c.declining?.stage === 'place' && c.q) {
    const place = draft.replace(new RegExp(`^\\s*${RECORDED.trim()}\\s*`, 'i'), '').trim()
    if (!place) return 'The place was empty, so nothing was put in the prompt box.'
    await update($, talkingAtom, () => null)
    await update($, flashAtom, () => 'Claude filled in where it is recorded: check it in the prompt box, then ⏎')
    await putInBox($, place)
    return `The place is in Adam's prompt box on the question "${cut(c.q.text, 80)}". He checks it; the reply posts as "${RECORDED}${cut(place, 60)}" only when he presses Enter. Do not post it yourself.`
  }
  if (c.declining) return "Adam is choosing why he won't answer this question, so nothing was drafted."
  const text = draft.replace(new RegExp(`^\\s*${PREFIX.trim()}\\s*`, 'i'), '').trim()
  const q = c.q
  if (!q || !(c.open || c.editing)) return 'No open question or post being edited is on screen in the answer session, so nothing was drafted.'
  if (!text) return 'The draft was empty, so nothing was put in the prompt box.'
  await update($, askingAtom, a => without(a, q.id))
  await update($, talkingAtom, () => null)
  // While editing, the draft is the new version of the post: the edit stays on.
  await update($, flashAtom, () =>
    c.editing ? 'Claude drafted the edit: change it in the prompt box if you like, then ⏎ updates your post' : 'Claude drafted a reply: edit it in the prompt box if you like, then ⏎ relays it',
  )
  await putInBox($, text)
  return `The draft is in Adam's prompt box on the question "${cut(q.text, 80)}". He confirms or edits it; it posts only when he presses Enter. Do not post it yourself.`
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
  await update($, decliningAtom, () => null)
  await update($, cursorAtom, () => nextFresh(QUESTIONS.findIndex(x => x.id === one.id), after))
  await update($, flashAtom, () => note)
  return note
}

async function relay($: EngineInterface, one: Question, text: string): Promise<string> {
  // Answering a question the session handled posts a reply of Adam's after
  // the session's own, which stays in the thread.
  const was = (await read($, answersAtom))[one.id]
  const over = was?.kind === 'handled' ? prefixOf(was) + was.text : undefined
  return settle($, one, { kind: 'answer', text, ...(over ? { over } : {}) }, `Relayed to ${SURFACE_NAME[one.surface]} ${one.where} as ${one.relayAs}`)
}

/** Won't answer: the band offers the reasons; nothing is recorded until one is chosen. */
async function startDecline($: EngineInterface, one: Question): Promise<string> {
  await update($, decliningAtom, () => ({ id: one.id, stage: 'reason' as const }))
  await update($, flashAtom, () => null)
  return `Won't answer ${one.asker.name}'s question: choose why.`
}

/**
 * Back a step while declining: from the reply's preview to where filter 1's
 * answer is recorded (the place back in the box) or to the filters; from
 * there to the filters; from the filters or the reasons, the question stays
 * open with nothing recorded.
 */
async function backDecline($: EngineInterface, one: Question, d: Declining): Promise<string> {
  if (d.stage === 'post' && d.filter === 1) {
    await update($, decliningAtom, () => ({ id: one.id, stage: 'place' as const }))
    if (d.place) await putInBox($, d.place)
    return 'Back to where the answer is recorded'
  }
  if (d.stage === 'post' || d.stage === 'place') {
    await update($, decliningAtom, () => ({ id: one.id, stage: 'filter' as const }))
    return 'Back to the filters'
  }
  await update($, decliningAtom, () => null)
  return `Kept ${one.asker.name}'s question open: nothing recorded`
}

/** Records a won't-answer for reason 1 or 2 and moves on. Prototype only: nothing is written. */
function decline($: EngineInterface, one: Question, reason: 1 | 2): Promise<string> {
  return settle($, one, { kind: 'wont', text: '', reason }, `Won't answer ${one.asker.name}'s question: ${REASONS[reason].label.toLowerCase()}. Nothing posted.`)
}

/** Reason 3: the inquisitor should have handled it. The band asks which filter should have stopped it. */
async function startFilter($: EngineInterface, one: Question): Promise<string> {
  await update($, decliningAtom, () => ({ id: one.id, stage: 'filter' as const }))
  await update($, flashAtom, () => null)
  return `The inquisitor should have handled ${one.asker.name}'s question: choose the filter that should have stopped it. Nothing is posted yet.`
}

/** The filter chosen: filter 1 asks where the answer is recorded; 2 to 4 preview their fixed reply. */
async function chooseFilter($: EngineInterface, one: Question, n: Filter): Promise<string> {
  await update($, flashAtom, () => null)
  if (n === 1) {
    await update($, decliningAtom, () => ({ id: one.id, stage: 'place' as const }))
    return 'Filter 1, already answered: give where the answer is recorded'
  }
  await update($, decliningAtom, () => ({ id: one.id, stage: 'post' as const, filter: n }))
  return `Filter ${n}, ${FILTERS[n].name}: check the reply, then ⏎ posts it`
}

/** Filter 1's place given: the reply that names it is previewed, to post. */
async function setPlace($: EngineInterface, one: Question, place: string): Promise<string> {
  // What filled the place in (Claude's draft) is past: the reply is on screen now.
  await update($, flashAtom, () => null)
  await update($, decliningAtom, () => ({ id: one.id, stage: 'post' as const, filter: 1 as const, place }))
  return `Filter 1, already answered: ${RECORDED}${place}. Check the reply, then ⏎ posts it`
}

/**
 * Posts the chosen filter's reply for the inquisitor, with the session's own
 * prefix, closes the question as handled by Adam's choice and moves on; the
 * note is the miss's "what was said". Prototype only: nothing is posted or logged.
 */
async function answerForInquisitor($: EngineInterface, one: Question, d: Extract<Declining, { stage: 'post' }>, note: string): Promise<string> {
  if (d.filter === 1 && !d.place) return "There is no place for the recorded answer: without it, it can't post as filter 1."
  const said = note.trim()
  const answer: Answer = { kind: 'handled', filter: d.filter, chosen: true, text: filterReply(d.filter, d.place), ...(said ? { said } : {}) }
  return settle(
    $,
    one,
    answer,
    `Answered ${one.asker.name}'s question for the inquisitor on ${SURFACE_NAME[one.surface]} ${one.where} as ${one.relayAs}. The real skill logs a miss against filter ${d.filter}${said ? `, with your note: ${said}` : '.'}`,
  )
}

/** Reopens a won't-answer: the question is open again, as if new. */
async function reopen($: EngineInterface, one: Question): Promise<string> {
  let was: Answer | undefined
  await update($, answersAtom, a => {
    was = a[one.id]
    return was?.kind === 'wont' ? without(a, one.id) : a
  })
  if (was?.kind !== 'wont') return ''
  const note = `Reopened ${one.asker.name}'s question: ${CLOSED[was.reason ?? 1].undo}`
  await update($, flashAtom, () => note)
  return note
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
  return 'Talking to Claude'
}

async function backToQuestion($: EngineInterface, one: Question): Promise<string> {
  await update($, askingAtom, a => without(a, one.id))
  await update($, talkingAtom, () => null)
  return 'Back to the question'
}

/** Out of the talk about where filter 1's answer is recorded, back to giving it. */
async function backToPlace($: EngineInterface): Promise<string> {
  await update($, talkingAtom, () => null)
  return 'Back to where the answer is recorded'
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
    // In the tool list from the start, so the model reaches for it when Adam
    // asks it to write his reply.
    await $.tool
      .register({
        name: 'propose_reply',
        description:
          "Puts a drafted reply in the person's prompt box in their answer session, on the question they are discussing, for them to confirm or edit before it posts. Use it when they ask you to write or draft their reply. It posts nothing.",
        inputSchema: {
          type: 'object',
          properties: { text: { type: 'string', description: 'Exactly the reply to post, without a "User says:" prefix.' } },
          required: ['text'],
        },
        isDeferred: false,
      })
      .catch(() => undefined)
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
    // What the session did by itself, said once on opening: it is in the
    // dots and the summary from then on.
    const answers = await read($, answersAtom)
    const byKind = (kind: Answer['kind']) => QUESTIONS.filter(one => answers[one.id]?.kind === kind).length
    const recorded = byKind('recorded')
    const handled = byKind('handled')
    const done =
      recorded && handled
        ? `${recorded} answered and ${handled} handled for you`
        : recorded
          ? `${recorded} answered for you`
          : handled
            ? `${handled} handled for you`
            : ''
    if (done && !(await read($, flashAtom))) await update($, flashAtom, () => `${done}: see the summary`)
    return { text: `Answer session open: type in the prompt box, Enter answers.${done ? ` ${done[0]!.toUpperCase()}${done.slice(1)}: see the summary.` : ''}` }
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
    const stage = c.declining?.stage
    const idle = c.composing
      ? `your question for ${c.q?.asker.name ?? 'the asker'}, then ⏎`
      : c.talking
        ? 'a message to Claude or a key, then ⏎'
        : stage === 'reason'
          ? '1, 2 or 3 for why, then ⏎'
          : stage === 'filter'
            ? '1 to 4 for the filter, then ⏎'
            : stage === 'place'
              ? 'where the answer is recorded, then ⏎'
              : stage === 'post'
                ? 'a note for the miss, or p to post it as it is, then ⏎'
                : c.q?.options && c.open && !c.editing
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
  // Only the session's own conversation drafts into the prompt box: a call
  // from any other loop (a subagent, or one of the engine's forks, such as
  // the one that guesses the next prompt) is refused.
  on('tool.call', { tool: PROPOSE_TOOL }, async ($, e) =>
    e.agentId
      ? { deny: 'Only the main conversation can draft a reply into the answer session.' }
      : { result: await proposeReply($, typeof e.text === 'string' ? e.text : '') },
  )

  // While the session is open the prompt box takes answers: the engine's
  // guess at the next prompt is not one, and Tab and Enter would relay it.
  on('prompt.suggest', async ($, e, next) =>
    e.origin.kind === 'suggestion' && (await read($, openAtom)) ? { isShown: false } : next(e),
  )

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
    if (isToModel(it)) {
      const q = c.q
      if (!q) return { drop: 'Nothing to discuss here.' }
      const returned = (await read($, returnedAtom))[q.id]
      await update($, promptAtom, () => '')
      await recordSay($, q, it.text)
      // Finding where filter 1's answer is recorded, or talking it through.
      const context = c.declining?.stage === 'place' ? placeContext(q, returned) : discussionContext(q, returned, c.editing ? c.answer?.text : undefined)
      return next({ ...e, context: [...(e.context ?? []), context] })
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
    const wont = count('wont')
    const recorded = count('recorded')
    // Handled by the session, or by Adam for the inquisitor (won't-answer reason 3).
    const mine = QUESTIONS.filter(one => answers[one.id]?.kind === 'handled' && answers[one.id]?.chosen).length
    const handledCount = count('handled') - mine
    const fresh = N - relayed - deferred - waiting - wont - recorded - handledCount - mine

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
    /**
     * The first trim whose rows fit `budget`, with the gaps it keeps; rows
     * left over then go to the other gaps in GAP_ORDER, a row each, then a
     * second each, so spare height spaces the view out instead of pooling at
     * its foot. The last trim, cut to `budget`, when none fits.
     */
    const fit = (build: (t: Trim, g: (gap: Gap) => number) => Row[], budget: number): Row[] => {
      for (const t of TRIMS) {
        const given = new Map<Gap, number>(GAP_ORDER.slice(0, t.gaps).map(gap => [gap, 1]))
        let rows = build(t, gap => given.get(gap) ?? 0)
        if (rows.length > budget) continue
        for (const round of [1, 2]) {
          for (const gap of GAP_ORDER) {
            if ((given.get(gap) ?? 0) >= round) continue
            const more = new Map(given).set(gap, round)
            const tried = build(t, g => more.get(g) ?? 0)
            if (tried.length <= budget && tried.length > rows.length) {
              given.set(gap, round)
              rows = tried
            }
          }
        }
        return rows
      }
      const rows = build(TRIMS[TRIMS.length - 1]!, () => 0)
      return [...rows.slice(0, Math.max(0, budget - 1)), plain('⋯', { dim: true })]
    }
    // What the relay account posts, exactly: "User says: …" behind a bar, at
    // most `max` lines, the last cut with an ellipsis.
    const bubble = (text: string | undefined, color: string, width: number, max: number, prefix = PREFIX): Row[] => {
      let lines = wrap(prefix + (text ?? '…'), Math.max(10, width - 2))
      if (lines.length > max) lines = [...lines.slice(0, Math.max(1, max) - 1), cut(lines.slice(Math.max(1, max) - 1).join(' '), width - 3)]
      // The prefix is dim, unless it is one of the session's own: those say
      // who posted, and stand out.
      const own = prefix !== PREFIX
      return lines.map((line, i) => (
        <Text wrap="truncate-end">
          <Text color={color}>│ </Text>
          {i === 0 && line.startsWith(prefix) ? (
            <Text dimColor={!own} bold={own}>
              {prefix}
            </Text>
          ) : (
            ''
          )}
          <Text dimColor={!text}>{i === 0 && line.startsWith(prefix) ? line.slice(prefix.length) : line}</Text>
        </Text>
      ))
    }

    // ── the bar: the session, the queue as dots, where this is ──────────

    const dots = QUESTIONS.map((one, i) => {
      const a = answers[one.id]
      const glyph = i === at && (!a || isTalking) ? (isTalking ? '◇' : '◉') : !a ? '○' : GLYPH[a.kind]
      const color = i === at ? ACCENT : !a ? RULE : TONE[a.kind]
      // A click on a dot opens that question.
      return (
        <Button key={`dot:${i}`} plain onPress={() => run(goTo($, i))}>
          <Text color={color} bold={i === at} dimColor={(a?.kind === 'wait' || a?.kind === 'wont') && i !== at}>
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
    // Narrower than 120 columns only the counts that are not zero, so the bar keeps its build at the right.
    const tally = (
      [
        [fresh, 'new', true],
        [relayed, 'relayed', cols >= 120],
        [deferred, 'for later', cols >= 120],
        [waiting, 'waiting', false],
        [wont, "won't answer", false],
        [recorded + handledCount, 'done for you', false],
        [mine, 'for the inquisitor', false],
      ] as const
    )
      .filter(([n, , always]) => n > 0 || always)
      .map(([n, words]) => `${n} ${words}`)
      .join(' · ')
    const where = [...(base ? [`${at + 1} of ${N}`] : []), ...(isTalking ? (cols >= 120 ? ['talking to Claude'] : []) : cols >= 120 || !base ? [tally] : [])].join(' · ')
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

    // `t: talk it through`, or, where the words hold the key, `keep (t)alking`.
    const keyText = (key: string, what: string) => {
      const at = what.indexOf(`(${key})`)
      return at < 0 ? (
        <Text>
          <Text color={ACCENT}>{key}</Text>
          <Text dimColor>: {what}</Text>
        </Text>
      ) : (
        <Text>
          <Text dimColor>{what.slice(0, at)}</Text>
          <Text color={ACCENT}>({key})</Text>
          <Text dimColor>{what.slice(at + 3)}</Text>
        </Text>
      )
    }
    // A click does what the letter and Enter do, except a command that posts:
    // its letter goes into the prompt box, and Enter posts.
    const keyButton = (cmd: Command) => (
      <Button key={`cmd:${cmd.key}`} plain onPress={() => run(cmd.posts ? putInBox($, cmd.key) : pressKey($, cmd.key))}>
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
    // Narrower than 100 columns the commands sit closer, so the row holds them all.
    const keyGap = cols >= 100 ? 3 : 2
    const keys = (hints: [string, string][], shown: Command[]) => (
      <Box height={1} overflow="hidden" justifyContent="space-between" width={cols} gap={keyGap}>
        <Box columnGap={keyGap} flexShrink={0}>
          {hints.map(([key, what]) => keyText(key, what))}
          {shown.filter(cmd => !AT_RIGHT.includes(cmd.key)).map(keyButton)}
        </Box>
        {/* Back, next and quit always in the same place, at the right, for
            quick back and forth by click. */}
        <Box gap={keyGap} flexShrink={1} justifyContent="flex-end">
          {/* The status gives way to the commands, never the other way round. */}
          {status ? <Box flexShrink={1}>{status}</Box> : null}
          <Box gap={keyGap} flexShrink={0}>
            {AT_RIGHT.flatMap(key => shown.filter(cmd => cmd.key === key)).map(keyButton)}
          </Box>
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
        const glyph = GLYPH[a!.kind]
        const color = TONE[a!.kind]
        const who = cut(one.asker.name, whoWidth - 2).padEnd(whoWidth)
        const place = cut(one.where, placeWidth - 2).padEnd(placeWidth)
        // What was posted, exactly, with its prefix: the session's own two say it was done for Adam.
        const what =
          a!.kind === 'defer'
            ? '│ for later'
            : a!.kind === 'wait'
              ? `│ asked: ${a!.text}`
              : a!.kind === 'wont'
                ? `│ won't answer: ${REASONS[a!.reason ?? 1].label.toLowerCase()}`
                : `│ ${a!.kind === 'handled' && a!.chosen ? 'you chose · ' : ''}${prefixOf(a!)}${a!.text}`
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
        plain(
          [
            `${relayed} of ${N} relayed this session`,
            ...(recorded ? [`${recorded} answered for you`] : []),
            ...(handledCount ? [`${handledCount} handled for you`] : []),
            ...(mine ? [`${mine} you answered for the inquisitor`] : []),
            ...(wont ? [`${wont} you won't answer`] : []),
            ...(waiting ? [`${waiting} back with their askers`] : []),
          ].join(' · '),
          { dim: true },
        ),
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
    const open = c.open
    // `a` and Enter agree with a suggested verdict: the preview shows what it posts.
    const verdictChosen = it.kind === 'command' && it.command.key === 'a' && !!q.verdict
    const message = it.kind === 'option' || it.kind === 'relay' ? it.text : verdictChosen ? q.verdict?.reply : undefined
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
    const STATE: Partial<Record<Answer['kind'], string>> = {
      defer: 'for later · ',
      wait: `waiting for ${q.asker.name} · `,
      wont: "won't answer · ",
      recorded: 'answered for you · ',
      handled: 'handled for you · ',
    }
    const stateText = answer?.kind === 'handled' && answer.chosen ? 'handled by your choice · ' : answer ? STATE[answer.kind] : undefined
    const state = stateText ? <Text color={answer ? TONE[answer.kind] : undefined}>{stateText}</Text> : ''
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
              {showOriginal ? 'show it as asked n(o)w' : 'show the (o)riginal'}
            </Button>
          </Box>,
        ]
      : []

    // ── the question view ────────────────────────────────────────────────

    // The left column: where it came from, the question, what it rests on.
    // The post in one run, wrapping when long: where and as whom, then
    // exactly what it says, at most `max` lines.
    const postRows = (text: string, width: number, max: number, verb = 'Post', prefix = PREFIX): Row[] => {
      const where = `${verb} ${postsAs}`.toUpperCase()
      const head = `${where} ${q.relayAs}: `
      let lines = wrap(head + prefix + text, Math.max(10, width))
      if (lines.length > max) lines = [...lines.slice(0, Math.max(1, max) - 1), cut(lines.slice(Math.max(1, max) - 1).join(' '), width)]
      return lines.map((line, i) =>
        i === 0 && line.startsWith(head) ? (
          <Text wrap="truncate-end">
            <Text dimColor>{where}</Text>
            {` ${q.relayAs}: `}
            {/* The session's own prefixes say who posted, and stand out. */}
            <Text dimColor={prefix === PREFIX} bold={prefix !== PREFIX}>
              {prefix}
            </Text>
            {line.slice(head.length + prefix.length)}
          </Text>
        ) : (
          plain(line)
        ),
      )
    }
    const questionColumn = (t: Trim, width: number, g: (gap: Gap) => number): Row[] => {
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
              <Text dimColor> replied to your question </Text>
              <Link href={q.link}>view</Link>
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
                {q.relatedLink ? <Link href={q.relatedLink}>{q.related}</Link> : q.related}
              </Text>,
            ]
          : []),
        ...(q.answered
          ? [
              <Text wrap="truncate-end">
                {q.answered.hasAuthority ? <Text color={DONE}>Recorded answer </Text> : <Text color={LATER}>Possibly answered already </Text>}
                {q.answered.link ? <Link href={q.answered.link}>{q.answered.decision}</Link> : q.answered.decision}
              </Text>,
              ...(open && t.related && !q.answered.hasAuthority
                ? [
                    <Box height={1} overflow="hidden">
                      <Button key="cite" plain dimColor onPress={() => run(pressKey($, 'c'))}>
                        (c)ite it in a reply
                      </Button>
                    </Box>,
                  ]
                : []),
            ]
          : []),
      ]
      return stack([provenance(t.provenance), [...changeMark, ...questionRows(width)], context, reply, related], [g('question'), g('context'), g('reply'), g('related')])
    }

    // The right column: the answers to choose from, then what will post; or
    // the reasons not to answer; or what was done.
    const answerColumn = (t: Trim, width: number, g: (gap: Gap) => number): Row[] => {
      const d = c.declining
      if (d?.stage === 'reason') return reasonsColumn(t, width)
      if (d?.stage === 'filter') return filtersColumn(t, width)
      if (d) return inquisitorColumn(d, t, width, g)
      if (answer?.kind === 'wont') return wontColumn(answer, t, width)
      if (answer && c.posted && (c.editing || answer.kind !== 'handled' || answer.chosen)) return postColumn(answer, t, width)
      const choose = chooseColumn(t, width, g)
      // Handled for Adam: the session's reply, and he can still answer it himself.
      if (answer?.kind === 'handled') return stack([postColumn(answer, t, width), choose], [g('related')])
      return stack([q.verdict ? verdictRows(q.verdict, t, width) : [], choose], [g('related')])
    }

    // A post in the thread: Adam's relay, his question to the asker, or one
    // of the session's own; while it is edited, the new version under it.
    const postColumn = (a: Answer, t: Trim, width: number): Row[] => {
      const HEAD: Record<'answer' | 'wait' | 'recorded' | 'handled', [string, string]> = {
        answer: ['✓', `Relayed ${postsAs}`],
        wait: ['◌', `Waiting for ${q.asker.name}. Asked ${postsAs}`],
        recorded: [GLYPH.recorded, `Answered for you ${postsAs}`],
        handled: [GLYPH.handled, a.chosen ? `Handled by your choice ${postsAs}` : `Handled for you ${postsAs}`],
      }
      const [glyph, words] = HEAD[a.kind as keyof typeof HEAD] ?? HEAD.answer
      // The post itself, a click away (prototype: the thread; the real
      // skill links the relay's own comment or message).
      const headRow: Row = (
        <Box height={1} overflow="hidden" gap={2}>
          <Box flexShrink={1}>
            <Text wrap="truncate-end">
              <Text color={TONE[a.kind]}>{glyph} </Text>
              <Text dimColor>{words.toUpperCase()}</Text> {q.relayAs}
            </Text>
          </Box>
          <Link href={q.link}>{a.edited ? 'edited · view' : 'view'}</Link>
        </Box>
      )
      const posted = bubble(a.text, c.editing ? RULE : TONE[a.kind], width, t.bubble, prefixOf(a))
      if (c.editing) {
        return [
          headRow,
          ...posted,
          ...(it.kind === 'edit'
            ? postRows(it.text, width, t.bubble, 'Edit')
            : [plain('Editing: change it in the prompt box, then ⏎ updates the post.', { dim: true })]),
        ]
      }
      // Why the session posted by itself, until Adam edits it into his own;
      // for one he answered for the inquisitor, the miss the real skill logs.
      const n = a.filter ?? 4
      const why =
        a.kind === 'handled' && a.chosen
          ? `The real skill logs a miss against filter ${n} (${FILTERS[n].name})${a.said ? ', with what you said:' : '.'}`
          : a.edited
            ? ''
            : a.kind === 'recorded'
              ? 'Filter 1 found a recorded answer with authority, so the session posted it for you.'
              : a.kind === 'handled'
                ? "It should have been stopped before it was asked: the session replied with the filter's action, and the real skill logs a miss."
                : a.over
                  ? `After the session's own reply: ${a.over}`
                  : ''
      const whyRows = !why || t.effects === 'none' ? [] : t.effects === 'line' ? [plain(why, { dim: true })] : wrap(why, width).map(line => plain(line, { dim: true }))
      const said = a.kind === 'handled' && a.chosen && a.said && t.effects !== 'none' ? wrap(a.said, width - 2).slice(0, Math.max(1, t.bubble)).map(line => plain(`│ ${line}`)) : []
      return [headRow, ...posted, ...whyRows, ...said, ...(isRelayed && t.logNote ? logNote(width) : [])]
    }

    // The suggested verdict on a person's question: only a suggestion, and
    // agreeing is one key and Enter, which posts the filter's action as Adam's.
    const verdictRows = (v: NonNullable<Question['verdict']>, t: Trim, width: number): Row[] => {
      const mark = <Text color={ACCENT}>{verdictChosen ? '▌ ' : '  '}</Text>
      return [
        <Text wrap="truncate-end">
          <Text dimColor>SUGGESTED </Text>
          <Text bold color={LATER}>
            {FILTERS[v.filter].verdict.replace(/^./, x => x.toUpperCase())}
          </Text>
          <Text dimColor> · the inquisitor's filter {v.filter}</Text>
        </Text>,
        ...(t.effects === 'none' ? [] : t.effects === 'line' ? [plain(v.why)] : wrap(v.why, width).map(line => plain(line))),
        <Box height={1} overflow="hidden">
          {mark}
          <Button key="verdict" plain onPress={() => run(putInBox($, 'a'))}>
            <Text color={ACCENT}>(a)</Text>
            <Text bold={verdictChosen} color={verdictChosen ? ACCENT : undefined} dimColor={!verdictChosen}>
              gree: {FILTERS[v.filter].action}
            </Text>
          </Button>
        </Box>,
      ]
    }

    // Won't answer: the three reasons, chosen by number in the prompt box
    // (a click puts the number there), each with what the real skill logs.
    const reasonsColumn = (t: Trim, width: number): Row[] => {
      const chosen = it.kind === 'reason' ? it.reason : undefined
      const reasons = ([1, 2, 3] as const).flatMap(r => {
        const isChosen = chosen === r
        const mark = <Text color={ACCENT}>{isChosen ? '▌ ' : '  '}</Text>
        const effect =
          t.effects === 'none' ? [] : t.effects === 'line' ? [cut(`→ ${REASONS[r].will}`, width - 5)] : wrap(REASONS[r].will, width - 7).map((line, j) => (j ? '  ' : '→ ') + line)
        return [
          ...(r > 1 && t.optionGap ? [blank()] : []),
          <Box height={1} overflow="hidden">
            {mark}
            <Button key={`why:${r}`} plain onPress={() => run(putInBox($, String(r)))}>
              <Text color={ACCENT}>{r}</Text>
              <Text dimColor>: </Text>
              <Text bold color={isChosen ? ACCENT : undefined}>
                {REASONS[r].label}
              </Text>
            </Button>
          </Box>,
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
      return [
        <Text wrap="truncate-end">
          <Text color={ACCENT}>{GLYPH.wont} </Text>
          <Text dimColor>{"WON'T ANSWER · CHOOSE WHY"}</Text>
        </Text>,
        ...reasons,
      ]
    }

    // A won't-answer, with its reason and what the real skill logged for it.
    const wontColumn = (a: Answer, t: Trim, width: number): Row[] => {
      const r = a.reason ?? 1
      const did = t.effects === 'none' ? [] : t.effects === 'line' ? [plain(CLOSED[r].did, { dim: true })] : wrap(CLOSED[r].did, width).map(line => plain(line, { dim: true }))
      return [
        <Text wrap="truncate-end">
          <Text color={TONE.wont}>{GLYPH.wont} </Text>
          <Text dimColor>{"WON'T ANSWER · "}</Text>
          <Text bold>{REASONS[r].label}</Text>
          <Text dimColor> · nothing was posted</Text>
        </Text>,
        ...did,
      ]
    }

    // Reason 3: the filter that should have stopped it, chosen by number in
    // the prompt box (a click puts the number there), each with what the
    // reply for the inquisitor will say.
    const filtersColumn = (t: Trim, width: number): Row[] => {
      const chosen = it.kind === 'filter' ? it.filter : undefined
      const filters = ([1, 2, 3, 4] as const).flatMap(n => {
        const isChosen = chosen === n
        const mark = <Text color={ACCENT}>{isChosen ? '▌ ' : '  '}</Text>
        const says = n === 1 ? 'replies with where the answer is recorded, which you give' : `replies: ${FILTERS[n].action}`
        const effect = t.effects === 'none' ? [] : [cut(`→ ${says}`, width - 5)]
        return [
          ...(n > 1 && t.optionGap ? [blank()] : []),
          <Box height={1} overflow="hidden">
            {mark}
            <Button key={`filter:${n}`} plain onPress={() => run(putInBox($, String(n)))}>
              <Text color={ACCENT}>{n}</Text>
              <Text dimColor>: </Text>
              <Text bold color={isChosen ? ACCENT : undefined}>
                {FILTERS[n].name.replace(/^./, x => x.toUpperCase())}
              </Text>
            </Button>
          </Box>,
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
      return [
        <Text wrap="truncate-end">
          <Text color={ACCENT}>{GLYPH.handled} </Text>
          <Text dimColor>{'WHICH FILTER SHOULD HAVE STOPPED IT? · NOTHING IS POSTED YET'}</Text>
        </Text>,
        ...filters,
      ]
    }

    // Answering for the inquisitor: for filter 1, where the answer is
    // recorded, typed in the prompt box (or found with Claude's help); then
    // exactly what will post, with an optional note for the miss. Enter posts.
    const inquisitorColumn = (d: Extract<Declining, { stage: 'place' | 'post' }>, t: Trim, width: number, g: (gap: Gap) => number): Row[] => {
      const n: Filter = d.stage === 'place' ? 1 : d.filter
      const dim = (text: string) => wrap(text, width).map(line => plain(line, { dim: true }))
      const head: Row = (
        <Text wrap="truncate-end">
          <Text color={ACCENT}>{GLYPH.handled} </Text>
          <Text dimColor>{'ANSWER FOR THE INQUISITOR · '}</Text>
          <Text bold>
            Filter {n}, {FILTERS[n].name}
          </Text>
        </Text>
      )
      if (d.stage === 'place') {
        const place = it.kind === 'place' ? it.text : ''
        const talkKey = q.options ? '(t)alk to Claude' : '(h)elp me answer'
        return stack(
          [
            [head, ...dim(`Where is the answer recorded? Type or paste it in the prompt box: a link, or the decision and what it says. Or ${talkKey}: Claude can find it and fill it in.`)],
            place
              ? postRows(place, width, t.bubble, 'Post', RECORDED)
              : [...postRows('…', width, 1, 'Post', RECORDED), ...dim("Without a place it can't post as filter 1.")],
          ],
          [g('choices')],
        )
      }
      const note: Row[] =
        it.kind === 'note'
          ? wrap(`NOTE FOR THE MISS, NOT POSTED: ${it.text}`, width).map((line, i) =>
              i === 0 ? (
                <Text wrap="truncate-end">
                  <Text dimColor>NOTE FOR THE MISS, NOT POSTED: </Text>
                  {line.slice('NOTE FOR THE MISS, NOT POSTED: '.length)}
                </Text>
              ) : (
                plain(line)
              ),
            )
          : dim('A note for the miss, if you like: type it in the prompt box. Or (p)ost it as it is. ⏎ posts.')
      const after = [
        ...(t.effects === 'full' ? dim(`The real skill logs a miss against filter ${n}, with your note as what was said.`) : []),
        // Said once, here: it posts on people's questions as well as agents'.
        ...(t.effects === 'none' ? [] : dim(`Posts on a person's question too, as you chose. You can still answer on ${SURFACE_NAME[q.surface]} by hand.`)),
      ]
      return stack([[head], postRows(filterReply(n, d.place), width, t.bubble, 'Post', n === 1 ? RECORDED : INQUISITOR), note, after], [g('choices'), g('preview'), g('related')])
    }

    // The answers to choose from, then what will post.
    const chooseColumn = (t: Trim, width: number, g: (gap: Gap) => number): Row[] => {
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
      // What will post, exactly, once there is something to post.
      const preview: Row[] = message ? [...postRows(message, width, t.preview === 'line' ? 1 : t.bubble), ...(t.logNote ? logNote(width) : [])] : []
      // Under the session's own reply the label parts the two, so it stays as long as the related decision does.
      const heading = answer?.kind === 'handled' ? (t.related ? [label('Or answer it yourself')] : []) : t.label && !isHuman ? [label('Choose an answer')] : []
      return stack([heading, choose, preview], [0, g('preview')])
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
      const hints: [string, string][] =
        c.declining?.stage === 'reason'
          ? [['1–3', 'choose why']]
          : c.declining?.stage === 'filter'
            ? [['1–4', 'choose the filter']]
            : c.declining || !open || c.editing || isHuman
              ? []
              : [[`1–${options.length}`, 'choose']]
      const one = isWide ? [] : fit((t, g) => stack([questionColumn(t, cols, g), answerColumn(t, cols, g)], g('choices')), B)
      const body = isWide ? (
        columns(fit((t, g) => questionColumn(t, LW, g), B), fit((t, g) => answerColumn(t, RW, g), B), LW, RW)
      ) : (
        <Box flexDirection="column">{[...lift(one.length), ...one]}</Box>
      )
      return frame(body, hints, cmds)
    }

    // ── talking to Claude: this question only, the queue waits ───────────
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
      // The choices stay on the question: going back is how to answer.
      const tight = stack([provenance(1), questionRows(width)], 0)
      if (tight.length <= budget) return tight
      const lines = wrap(q.text, width)
      const room = Math.max(1, budget - 1)
      return [...provenance(1), ...lines.slice(0, room - 1).map(line => plain(line, { bold: true })), plain(cut(lines.slice(room - 1).join(' '), width), { bold: true })]
    }
    // The question for the asker, previewed as it will post in their thread.
    const compose = (width: number): Row[] => [
      label(`Ask ${q.asker.name}, in the thread`),
      ...bubble(askText || undefined, askText ? ACCENT : RULE, width, Math.max(2, B - 5)),
      ...wrap(
        busy === 'draft'
          ? 'Drafting a question into the prompt box…'
          : askText
            ? `Posts ${postsAs} ${q.relayAs}. Enter sends exactly this; the question waits for the reply, the queue moves on.`
            : `Type your question for ${q.asker.name} in the prompt box.`,
        width,
      ).map(line => plain(line, { dim: true })),
    ]
    // Where the discussion stands, and what Enter would do with the box.
    const talkState = (width: number): Row[] => {
      const head: Row = (
        <Text wrap="truncate-end">
          <Text color={ACCENT}>◇ </Text>
          <Text dimColor>TALKING TO CLAUDE</Text>
          <Text dimColor>
            {c.editing
              ? ' · for your edit, in the conversation above'
              : c.declining
                ? ' · about where the answer is recorded, in the conversation above'
                : ' · in the conversation above'}
          </Text>
        </Text>
      )
      // The conversation above is where the discussion happens, so the band
      // can spare the rows: a blank row each side of the head, and one above
      // the key row.
      const spaced = (rows: Row[]): Row[] => [blank(), head, blank(), ...rows, blank()]
      if (composing) return spaced(compose(width))
      const said = turns.some(turn => turn.who === 'you')
      const last = turns[turns.length - 1]
      const state: Row[] =
        busy === 'reply'
          ? [plain('◌ Claude is answering above…', { color: ACCENT })]
          : busy === 'rephrase'
            ? [plain('◌ Rephrasing the question from your discussion…', { color: ACCENT })]
            : last?.who === 'error'
              ? wrap(last.text, width).map(line => plain(line, { color: LATER }))
              : said
                ? []
                : wrap(
                    c.declining
                      ? `Ask Claude where the answer is recorded, or to find it and fill it in for you to check. It gets the question with your message and may read the thread and the code first. Nothing posts until you ⏎ on the reply.`
                      : `Ask anything about the question, or tell Claude what to say and it drafts your reply for you to check. It gets the question with your message and may read the thread and the code first; its reply shows above. The rest of the queue waits.`,
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
      return spaced([...state, ...pending])
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

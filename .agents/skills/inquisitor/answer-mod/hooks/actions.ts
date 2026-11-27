// What the person does in the band: the state Enter acts on, the commands,
// and each act, which the core previews and posts.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, ModelCompleteResult, Timer } from 'claude-code'

import type { Answer, Declining, Filter, PlacedRow } from '../types'
import { ask } from './service-core'
import { pollNow } from './service'
import type { PostResponse, PreviewRequest, PreviewResponse } from './core-protocol'
import {
  CLOSED,
  FILTERS,
  INQUISITOR,
  PREFIX,
  RECORDED,
  REASONS,
  RESERVED,
  SURFACE_NAME,
  cut,
  others,
  questionOf,
  view,
} from './questions'
import type { Question, Reply } from './questions'
import { INITIAL, without } from './state'

const answersAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'answers' } as const, INITIAL.answers)
const askingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'asking' } as const, INITIAL.asking)
const awaitingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'awaiting' } as const, INITIAL.awaiting)
const cursorAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'cursor' } as const, INITIAL.cursor)
const decliningAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'declining' } as const, INITIAL.declining)
const editingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'editing' } as const, INITIAL.editing)
const flashAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'flash' } as const, INITIAL.flash)
const knownPlacesAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'knownPlaces' } as const, INITIAL.knownPlaces)
const markedAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'marked' } as const, INITIAL.marked)
const orderAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'order' } as const, INITIAL.order)
const originalAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'original' } as const, INITIAL.original)
const pickingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'picking' } as const, INITIAL.picking)
const placesAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'places' } as const, INITIAL.places)
const postingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'posting' } as const, INITIAL.posting)
const previewedAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'previewed' } as const, INITIAL.previewed)
const displacedAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'displaced' } as const, INITIAL.displaced)
const promptAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'prompt' } as const, INITIAL.prompt)
const questionsAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'questions' } as const, INITIAL.questions)
const rephrasedAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'rephrased' } as const, INITIAL.rephrased)
const rowsAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'rows' } as const, INITIAL.rows)
const seenAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'seen' } as const, INITIAL.seen)
const serviceAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'service' } as const, INITIAL.service)
const talkingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'talking' } as const, INITIAL.talking)
const talksAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'talks' } as const, INITIAL.talks)
const thinkingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'thinking' } as const, INITIAL.thinking)
const viewingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'viewing' } as const, INITIAL.viewing)

/** The commands that sit at the key row's right end on every screen. */
export const AT_RIGHT = ['b', 'n']
/** Starts the notice of a stopped post. The band and boxChanged find that notice by this prefix, to draw it in the warning colour, not as done. */
export const NOT_POSTED = 'Not posted: '

// ── the queue ───────────────────────────────────────────────────────────

/** The questions in queue order, as the band shows them now. */
export async function queueOf($: EngineInterface): Promise<Question[]> {
  const all = await read($, questionsAtom)
  const now = await $.clock.now()
  return (await read($, orderAtom)).flatMap(id => (all[id] ? [questionOf(all[id], now)] : []))
}

/** The first question with nothing done to it, searching from just after `from` and wrapping around; the summary's index when there is none. */
export function nextFresh(from: number, answers: Record<string, Answer>, queue: Question[]): number {
  for (let step = 1; step <= queue.length; step++) {
    const i = (from + step) % queue.length
    if (!answers[queue[i]!.id]) return i
  }
  return queue.length
}

/** Whether an answer left a post in its thread that the person can edit: one made for them, not an automatic or pending one. */
export const isPosted = (a?: Answer) => !!a && !a.auto && !a.pending && (a.kind === 'answer' || a.kind === 'wait' || a.kind === 'recorded' || a.kind === 'handled') && a.post !== undefined

/** A post's own words: without its reserved prefix and without the `Re: ` line the relay adds. */
export function bodyOf(post: string): string {
  const prefix = RESERVED.find(p => post.startsWith(p)) ?? ''
  return post.slice(prefix.length).replace(/\n+Re: \S+\s*$/, '').trim()
}

// ── what Enter does ─────────────────────────────────────────────────────
//
// The keyboard stays in the prompt box. What the box holds is read against
// the screen: a digit chooses an option, one letter names a command, anything
// longer is an answer (or, in a discussion, a message to the model). The
// band previews it as it is typed; Enter does it.

/** The band's state, as the screen and Enter both read it. */
export type Ctx = {
  at: number
  base?: Question
  /** The question as it now stands (rephrased, or as asked). */
  q?: Question
  answer?: Answer
  /** It can be answered: nothing done to it, or for later. */
  open: boolean
  /** It has a post of the person's in its thread. */
  posted: boolean
  editing: boolean
  talking: boolean
  composing: boolean
  declining?: Declining
  busy?: 'reply' | 'rephrase' | 'draft'
  hasReply: boolean
  changed: boolean
  deferredAt: number
  /** The thread's replies since the question, as the last poll found them. */
  replies: Reply[]
  /** Replies from this index on came after the person last saw the thread: new to them. */
  fresh?: number
  viewing?: number
  /** Picking another place where the answer will be recorded. */
  picking: boolean
  /** The place picked for the record, if any. */
  place?: string
  pending: number
}

export async function snapshot($: EngineInterface): Promise<Ctx> {
  const queue = await queueOf($)
  const N = queue.length
  const at = Math.min(Math.max(await read($, cursorAtom), 0), N)
  const answers = await read($, answersAtom)
  const deferredAt = queue.findIndex(one => answers[one.id]?.kind === 'defer')
  const pending = Object.values(answers).filter(a => a.pending).length
  const base = queue[at]
  const empty: Ctx = { at, open: false, posted: false, editing: false, talking: false, composing: false, hasReply: false, changed: false, deferredAt, replies: [], picking: false, pending }
  if (!base) return empty
  const seen = (await read($, seenAtom))[base.id]
  const viewing = await read($, viewingAtom)
  const rephrased = (await read($, rephrasedAtom))[base.id]
  const q = view(base, rephrased, !!(await read($, originalAtom))[base.id])
  const answer = answers[base.id]
  const talking = (await read($, talkingAtom)) === base.id
  const posted = isPosted(answer)
  const declining = await read($, decliningAtom)
  const busy = (await read($, thinkingAtom))[base.id]
  const place = (await read($, placesAtom))[base.id]
  return {
    at,
    base,
    q,
    ...(answer ? { answer } : {}),
    open: !answer || answer.kind === 'defer',
    posted,
    editing: posted && !!(await read($, editingAtom))[base.id],
    talking,
    composing: talking && !!(await read($, askingAtom))[base.id],
    ...(declining?.id === base.id ? { declining } : {}),
    ...(busy ? { busy } : {}),
    hasReply: ((await read($, talksAtom))[base.id] ?? []).some(t => t.who === 'model'),
    changed: !!rephrased,
    deferredAt,
    replies: base.replies,
    ...(seen?.fresh !== undefined ? { fresh: seen.fresh } : {}),
    ...(viewing?.id === base.id ? { viewing: viewing.page } : {}),
    picking: await read($, pickingAtom),
    ...(place ? { place } : {}),
    pending,
  }
}

/**
 * A one-letter command: its key and what it does. A click on a command that
 * `posts` only types it into the prompt box; only Enter posts.
 */
export type Command = {
  key: string
  what: string
  posts?: true
  /** Not in the key row: its button sits beside what it opens. */
  aside?: true
  /** Left out of the key row, to save the row's room: typed only. */
  unlisted?: true
}

/** Whether a question is an agent's, which alone can be declined for the inquisitor. */
const isAgents = (q: Question) => q.asker.kind === 'agent'

/** The commands the screen offers now, in the order the key row shows them. */
export function commands(c: Ctx): Command[] {
  const q = c.q
  const close: Command = { key: 'q', what: '(q)uit', unlisted: true }
  const nav: Command[] = [
    { key: 'b', what: '(b)ack' },
    { key: 'n', what: '(n)ext' },
  ]
  if (!q) return [...(c.deferredAt >= 0 ? [{ key: 'r', what: '(r)eview those for later' }] : []), ...nav, close]
  if (c.composing) return [{ key: 'b', what: 'go (b)ack to the discussion' }, close]
  if (c.viewing !== undefined) return [{ key: 'm', what: '(m)ore' }, { key: 'b', what: 'go (b)ack' }, close]
  if (c.picking) return [{ key: 'b', what: 'go (b)ack' }, close]
  if (c.talking) {
    const asking = c.open && !c.editing && !c.declining && !c.busy && !q.branch
    return [
      ...(asking && c.hasReply ? [{ key: 'r', what: '(r)eword the question' }] : []),
      ...(asking ? [{ key: 'a', what: '(a)sk the asker' }] : []),
      { key: 'b', what: 'go (b)ack' },
      close,
    ]
  }
  const talk: Command = q.options ? { key: 't', what: '(t)alk to Claude' } : { key: 'h', what: '(h)elp me answer' }
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
  const viewAll: Command[] = others(c.replies).length || q.record ? [{ key: 'v', what: '(v)iew all', aside: true }] : []
  // Another place where the answer will be recorded: offered on an open question that is not a questions-branch file.
  const elsewhere: Command[] = c.open && !q.branch ? [{ key: 's', what: 'record (s)omewhere else', aside: true }] : []
  const own: Command[] = c.editing
    ? [
        { key: 'h', what: '(h)elp me edit' },
        { key: 'k', what: '(k)eep it as posted' },
      ]
    : kind === 'wont'
      ? q.branch
        ? []
        : [{ key: 'r', what: '(r)eopen' }]
      : c.open
        ? [
            talk,
            ...(q.record ? [{ key: 'a', what: '(a)gree', posts: true as const }] : []),
            { key: 'w', what: "(w)on't answer" },
            { key: 'l', what: '(l)ater' },
          ]
        : c.posted && !q.branch
          ? [{ key: 'e', what: kind === 'answer' || kind === 'wait' ? '(e)dit your post' : kind === 'handled' ? '(e)dit the reply' : '(e)dit the post' }]
          : []
  return [...own, ...(c.changed ? [{ key: 'o', what: '(o)riginal' }] : []), ...viewAll, ...elsewhere, ...nav, close]
}

/** Does command `key` on the screen `c` describes, and says what it did. */
export async function runCommand($: EngineInterface, c: Ctx, key: string): Promise<string> {
  const q = c.q
  if (key === 'q') return quitSession($)
  const inside = c.talking || c.composing || !!c.declining || c.viewing !== undefined || c.picking
  if (!inside && key === 'b') return stepBy($, c.at, -1)
  if (!inside && key === 'n') return stepBy($, c.at, 1)
  if (!q) return key === 'r' ? go($, c.deferredAt, 'Back to a deferred question') : ''
  if (c.viewing !== undefined) return key === 'b' ? closeView($) : key === 'm' ? morePages($) : ''
  if (c.picking) return key === 'b' ? stopPicking($) : ''
  if (c.composing) return key === 'b' ? backToTalk($, q) : ''
  if (c.talking) {
    switch (key) {
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
        return d.stage === 'post' ? answerForInquisitor($, c, q, d, '') : ''
    }
    return ''
  }
  switch (key) {
    case 't':
    case 'h':
      return openTalk($, q)
    case 'a':
      return q.record ? agree($, c, q) : ''
    case 'v':
      return viewAll($, q)
    case 's':
      return startPicking($)
    case 'w':
      return startDecline($, q)
    case 'r':
      return reopen($, q)
    case 'l':
      return settle($, q, { kind: 'defer', text: '' }, `Later: ${q.asker.name}'s question comes back after the unanswered ones`)
    case 'e':
      return startEdit($, q, c.answer)
    case 'k':
      return stopEdit($, q)
    case 'o':
      return toggleOriginal($, q)
  }
  return ''
}

/** What Enter would do with the prompt box's text. */
export type Intent =
  | { kind: 'none' }
  | { kind: 'option'; index: number; text: string }
  | { kind: 'relay'; text: string }
  | { kind: 'command'; command: Command }
  | { kind: 'say'; text: string }
  | { kind: 'ask'; text: string }
  | { kind: 'edit'; text: string }
  | { kind: 'reason'; reason: 1 | 2 }
  | { kind: 'filter'; filter: Filter }
  | { kind: 'place'; text: string }
  | { kind: 'note'; text: string }
  | { kind: 'pick'; place: string }
  | { kind: 'refused'; why: string }

/** A place for a record: a repository's `owner/name`. */
const isRepo = (text: string) => /^[A-Za-z0-9][\w.-]*\/[\w.-]+$/.test(text)

export function intent(c: Ctx, draft: string, places: string[] = []): Intent {
  const text = draft.trim()
  if (!text) return { kind: 'none' }
  const command = text.length === 1 ? commands(c).find(one => one.key === text.toLowerCase()) : undefined
  if (command) return { kind: 'command', command }
  const q = c.q
  if (!q) return { kind: 'refused', why: 'Nothing to answer here: b or n moves to a question.' }
  if (c.viewing !== undefined) return { kind: 'refused', why: 'Go (b)ack to answer: this shows the replies and the record in full.' }
  if (c.picking) {
    if (/^[1-9]\d*$/.test(text)) {
      const place = places[Number(text) - 1]
      return place ? { kind: 'pick', place } : { kind: 'refused', why: `There is no place ${text}.` }
    }
    return isRepo(text) ? { kind: 'pick', place: text } : { kind: 'refused', why: 'Choose a place by number, or type a repository as owner/name.' }
  }
  if (c.composing) return { kind: 'ask', text }
  if (c.talking) {
    if (/^[1-9]$/.test(text)) return { kind: 'refused', why: c.declining ? 'Go (b)ack, then ⏎ on where it is recorded.' : 'To answer, go (b)ack to the question and choose there.' }
    if (text.length === 1) return { kind: 'refused', why: `${text} is not a command here: the key row lists them.` }
    return c.busy ? { kind: 'refused', why: 'Claude is still answering above: wait for it, or Esc to stop it.' } : { kind: 'say', text }
  }
  const stage = c.declining?.stage
  if (stage === 'reason') {
    if (text === '2' && !isAgents(q)) return { kind: 'refused', why: "Reason 2 is for an agent's question only: only an agent has an inquisitor to learn from a miss." }
    return /^[12]$/.test(text) ? { kind: 'reason', reason: Number(text) as 1 | 2 } : { kind: 'refused', why: 'Choose why, 1 or 2, or go (b)ack to keep it open.' }
  }
  if (stage === 'filter') {
    return /^[1-4]$/.test(text)
      ? { kind: 'filter', filter: Number(text) as Filter }
      : { kind: 'refused', why: 'Choose the filter that should have stopped it, 1 to 4, or go (b)ack to keep it open.' }
  }
  if (stage === 'place' || stage === 'post') {
    if (text.length === 1) return { kind: 'refused', why: `${text} is not a command here: the key row lists them.` }
    if (stage === 'place' && /\s/.test(text)) return { kind: 'refused', why: "Where it is recorded is one URL, with no space or line break: the post's Recorded in: line holds it." }
    return stage === 'place' ? { kind: 'place', text } : { kind: 'note', text }
  }
  if (c.editing) {
    const now = c.answer?.post ? bodyOf(c.answer.post) : ''
    return text === now ? { kind: 'refused', why: 'That is what it says now: change it, or (k)eep it as posted.' } : { kind: 'edit', text }
  }
  if (!c.open) {
    const kind = c.answer?.kind
    return {
      kind: 'refused',
      why:
        c.answer?.pending
          ? `Your answer waits to be relayed: ${c.answer.pending}`
          : q.branch && (kind === 'answer' || kind === 'recorded')
            ? 'This question is answered, in a log file on the questions branch, which takes no edits.'
            : c.answer?.auto
              ? 'This question was answered for you.'
              : kind === 'wait'
                ? `This question waits for ${q.asker.name}'s reply: (e)dit your post to change it.`
                : kind === 'wont'
                  ? q.branch
                    ? "You declined this question: its handled file closes it everywhere."
                    : "You declined this question: (r)eopen it to answer."
                  : kind === 'recorded'
                    ? 'You posted the recorded answer: (e)dit the post to change it.'
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
  if (text.length === 1) return { kind: 'refused', why: `${text} is not a command here: the key row lists them.` }
  return { kind: 'relay', text }
}

/** What Enter would do, in a few words for the hint line; undefined when nothing. */
export function enterHint(c: Ctx, it: Intent): string | undefined {
  const q = c.q
  const surface = q ? SURFACE_NAME[q.surface] : ''
  switch (it.kind) {
    case 'option':
    case 'relay':
      return !q ? undefined : q.branch ? '⏎ log it on the questions branch; nothing posts' : `⏎ relay to ${surface}`
    case 'command':
      if (it.command.key === 'a' && q?.record) return q.branch ? '⏎ log the recorded answer on the questions branch; nothing posts' : `⏎ post the recorded answer on ${surface}`
      if (it.command.key === 'p' && c.declining?.stage === 'post') return `⏎ post on ${surface} for the inquisitor, with no note`
      if (it.command.key === 'w') return "⏎ choose why you won't answer"
      return it.command.key === 'l' ? '⏎ ask me later, after the unanswered ones' : `⏎ ${it.command.what.replace(/[()]/g, '')}`
    case 'say':
      return '⏎ to Claude, with the question'
    case 'ask':
      return q ? `⏎ send to ${q.asker.name}` : undefined
    case 'edit':
      return q ? `⏎ update the post on ${surface}` : undefined
    case 'reason':
      return it.reason === 2 ? '⏎ choose which filter should have stopped it; nothing is posted yet' : "⏎ won't answer: nothing to answer; nothing is posted"
    case 'filter':
      return it.filter === 1 ? '⏎ filter 1: then give where the answer is recorded' : `⏎ filter ${it.filter}: then check the reply; nothing is posted yet`
    case 'place':
      return '⏎ use this place, then check the reply; nothing is posted yet'
    case 'note':
      return `⏎ post on ${surface} for the inquisitor; the note goes in the miss`
    case 'pick':
      return `⏎ record it in ${it.place}`
    case 'refused':
      return it.why
    case 'none':
      return undefined
  }
}

/** What Enter sends on to the session's model rather than doing in the band. */
export type ToModel = { kind: 'say'; text: string }
export const isToModel = (it: Intent): it is ToModel => it.kind === 'say'

/** Does what Enter does on the screen `c` describes, and says what it did. */
export async function enter($: EngineInterface, c: Ctx, it: Exclude<Intent, ToModel>): Promise<string> {
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
      return q ? relay($, c, q, it.text) : ''
    case 'ask':
      return q ? sendAsk($, c, q, it.text) : ''
    case 'edit':
      return q ? editPost($, c, q, it.text) : ''
    case 'reason':
      return !q ? '' : it.reason === 2 ? startFilter($, q) : decline($, c, q)
    case 'filter':
      return q ? chooseFilter($, q, it.filter) : ''
    case 'place':
      return q ? setPlace($, q, it.text) : ''
    case 'note':
      return q && d?.stage === 'post' ? answerForInquisitor($, c, q, d, it.text) : ''
    case 'pick':
      return q ? pickPlace($, q, it.place) : ''
  }
}

// ── the prompt box ──────────────────────────────────────────────────────
//
// After Enter, the engine puts the dropped prompt back in the box (a
// prompt.change with origin `engine`). What the box should hold instead
// waits here until that put-back arrives, or PUT_BACK_MS passes.
let afterDrop: { dropped: string; text: string } | undefined
export const PUT_BACK_MS = 500

export function dropped(text: string): void {
  afterDrop = { dropped: text, text: '' }
}
export const isPutBack = (text: string) => afterDrop !== undefined && text === afterDrop.dropped

/** What was typed stays in the box after a drop, for a second Enter. */
function keepTyped(): void {
  if (afterDrop) afterDrop.text = afterDrop.dropped
  stoppedWith = afterDrop?.dropped.trim()
}

/** Puts `text` in the prompt box, after any put-back still due. */
export async function putInBox($: EngineInterface, text: string): Promise<void> {
  if (afterDrop) {
    afterDrop.text = text
    return
  }
  await $.prompt.fill({ text, mode: 'replace' })
  // The mod's own fill raises no prompt.change for this mod, so promptAtom's copy of the box is set here.
  await update($, promptAtom, () => text)
  await boxChanged($, text)
  schedulePreview($)
}

// The core's preview of what Enter would do, asked for once the box has been
// still a moment, so the band shows the core's exact words before Enter.
let previewTimer: Timer | undefined
const PREVIEW_MS = 400

export function schedulePreview($: EngineInterface): void {
  previewTimer?.cancel()
  previewTimer = $.clock.after(PREVIEW_MS, () => void previewNow($).catch(() => undefined))
}

async function previewNow($: EngineInterface): Promise<void> {
  if ((await read($, serviceAtom)).status !== 'open') return
  const c = await snapshot($)
  const a = actOf(c, intent(c, await read($, promptAtom), await read($, knownPlacesAtom)))
  if (!a || (await read($, previewedAtom))?.key === actKey(a)) return
  await previewOf($, a)
}

/** Applies what the box should hold after a drop; `putBack` when the engine just put the prompt back. */
export async function settleBox($: EngineInterface, putBack: boolean): Promise<void> {
  const due = afterDrop
  if (!due) return
  afterDrop = undefined
  if (!putBack && !due.text) return
  await $.prompt.fill({ text: due.text, mode: 'replace' })
  await update($, promptAtom, () => due.text)
}

/** What the box held when a post was stopped; once it holds something else, the stop's notice goes. */
let stoppedWith: string | undefined

/** The box changed to `text`: a stop's notice goes once it holds something else. */
export async function boxChanged($: EngineInterface, text: string): Promise<void> {
  if (stoppedWith === undefined || !text.trim() || text.trim() === stoppedWith) return
  stoppedWith = undefined
  await update($, flashAtom, f => (f?.startsWith(NOT_POSTED) ? null : f))
}

/** Shorter forms of a stopped post's notice, longest first, for the key row to take the longest that fits. */
export function noticeForms(note: string): string[] {
  const replied = /^Not posted: (.+?) replied since/.exec(note)
  if (replied) {
    const who = replied[1]!
    const first = who.includes(' and ') ? undefined : who.split(' ')[0]
    return [
      note,
      `${NOT_POSTED}${who} replied. Read it, then ⏎ again.`,
      `${NOT_POSTED}${who} replied. ⏎ again to post.`,
      `${NOT_POSTED}${who} replied`,
      ...(first && first !== who ? [`${NOT_POSTED}${first} replied`] : []),
      `${NOT_POSTED}a new reply`,
    ]
  }
  return [note]
}

// ── moving through the queue ────────────────────────────────────────────

/** Moves to question `i` (the queue's length is the summary). */
export async function go($: EngineInterface, i: number, note: string): Promise<string> {
  await update($, editingAtom, () => ({}))
  await update($, decliningAtom, () => null)
  await update($, viewingAtom, () => null)
  await update($, pickingAtom, () => false)
  await update($, previewedAtom, () => null)
  await update($, cursorAtom, () => i)
  await update($, flashAtom, () => null)
  await arrive($, i)
  return note
}

/**
 * Question `i` came on screen: its replies count as seen, its mark in the
 * bar goes, and the core keeps it as the question on screen.
 */
export async function arrive($: EngineInterface, i: number): Promise<void> {
  const one = (await queueOf($))[i]
  await update($, displacedAtom, () => null)
  if (one && (await read($, markedAtom))[one.id]) await update($, markedAtom, m => without(m, one.id))
  if (one) await update($, seenAtom, s => ({ ...s, [one.id]: { shown: one.replies.length } }))
  const service = await read($, serviceAtom)
  if (service.status === 'open') void ask($, { command: 'screen.set', session_id: await $.session.id(), question: one?.id ?? null })
}

export async function goTo($: EngineInterface, i: number): Promise<string> {
  const N = (await read($, orderAtom)).length
  return go($, i, i === N ? 'The summary' : `Question ${i + 1} of ${N}`)
}

export async function stepBy($: EngineInterface, at: number, by: number): Promise<string> {
  const N = (await read($, orderAtom)).length
  return goTo($, (at + by + N + 1) % (N + 1))
}

/** A command pressed in the band: done on the screen as it is now, as typing its key and Enter would. */
export async function pressKey($: EngineInterface, key: string): Promise<string> {
  return runCommand($, await snapshot($), key)
}

/** A click on a transcript row's view or a link to a question in the queue: that question. */
export async function openQuestion($: EngineInterface, id: string): Promise<string> {
  const i = (await read($, orderAtom)).indexOf(id)
  return i < 0 ? '' : goTo($, i)
}

/** The links in a post that lead to a question in the queue: a click on one opens it here. */
export function queueLinks(text: string, queue: Question[]): string[] {
  const hrefs = [...text.matchAll(/\[[^\]]*\]\(([^)\s]+)\)/g)].map(m => m[1]!)
  return [...new Set(hrefs.filter(href => queue.some(one => one.link === href)))]
}

/** A click on a link to a question in the queue: where several share the thread, the first with nothing done to it. */
export async function openLinked($: EngineInterface, href: string): Promise<string> {
  const queue = await queueOf($)
  const answers = await read($, answersAtom)
  const linked = queue.map((one, i) => ({ one, i })).filter(x => x.one.link === href)
  const to = linked.find(x => !answers[x.one.id]) ?? linked[0]
  return to ? goTo($, to.i) : ''
}

/**
 * q: leaves Claude Code, closing the answer service as any exit does, since
 * a session the answer command starts exists only for answering. `/exit`
 * runs from a timer, once the hook handling q has returned.
 */
export async function quitSession($: EngineInterface): Promise<string> {
  await update($, flashAtom, () => null)
  $.clock.after(0, () => {
    $.command.run({ command: 'exit' }).catch(() => $.ui.toast('Type /exit to leave Claude Code.'))
  })
  return 'Leaving Claude Code.'
}

// ── the thread and the replies ──────────────────────────────────────────

async function viewAll($: EngineInterface, one: Question): Promise<string> {
  await update($, viewingAtom, () => ({ id: one.id, page: 0 }))
  await update($, flashAtom, () => null)
  return 'Everything since the question, in full'
}

async function closeView($: EngineInterface): Promise<string> {
  await update($, viewingAtom, () => null)
  return 'Back to the question'
}

async function morePages($: EngineInterface): Promise<string> {
  await update($, viewingAtom, v => (v ? { ...v, page: v.page + 1 } : v))
  return 'The next page'
}

// ── the core's preview, then the post ───────────────────────────────────
//
// Every act goes to the core as a preview, which says exactly what will
// post and where the answer will be recorded, then as a post of that
// preview. The band asks for the preview while the person types, so it
// shows the core's words. Enter stops, and the next Enter posts, when the
// preview carries a warning the band has not drawn, or when a poll took
// the question being answered from under the cursor.

/** An act as the core's preview takes it, less the session. */
export type Act = Omit<PreviewRequest, 'command' | 'session_id'>

export const actKey = (a: Act) => JSON.stringify(a)

/** Whether a preview carries anything the person must see before it posts. */
export const mustSee = (pv: PreviewResponse) => pv.warnings.length > 0 || !!pv.record.more_visible_than || !!pv.reaches_run

/** The act Enter would do on screen `c` with intent `it`; undefined for one the core does not preview. */
export function actOf(c: Ctx, it: Intent): Act | undefined {
  const q = c.q
  if (!q) return undefined
  const place = c.place ? { place: c.place } : {}
  const d = c.declining
  switch (it.kind) {
    case 'option':
    case 'relay':
      return { question: q.id, action: 'answer', text: it.text, ...place }
    case 'ask':
      return { question: q.id, action: 'ask', text: it.text }
    case 'edit':
      return { question: q.id, action: 'edit', text: it.text }
    case 'reason':
      return it.reason === 1 ? { question: q.id, action: 'decline', reason: 1 } : undefined
    case 'note':
      return d?.stage === 'post' ? declineAct(q, d, it.text) : undefined
    case 'command':
      if (it.command.key === 'a' && q.record && c.open) return { question: q.id, action: 'agree', ...place }
      if (it.command.key === 'p' && d?.stage === 'post') return declineAct(q, d, '')
      return undefined
    case 'none':
      return d?.stage === 'post' ? declineAct(q, d, '') : undefined
  }
  return undefined
}

function declineAct(q: Question, d: Extract<Declining, { stage: 'post' }>, note: string): Act {
  return {
    question: q.id,
    action: 'decline',
    reason: 2,
    filter: d.filter,
    ...(d.filter === 1 && d.place ? { recorded_in: d.place } : {}),
    ...(note.trim() ? { note: note.trim() } : {}),
  }
}

/** The core's preview of `a`, kept for the band to draw; an error's words otherwise. */
export async function previewOf($: EngineInterface, a: Act): Promise<PreviewResponse | string> {
  const res = await ask($, { command: 'preview', session_id: await $.session.id(), ...a })
  if (!res.ok) return res.error
  await update($, previewedAtom, () => ({ key: actKey(a), res }))
  return res
}

/** The caller's step once the core posted the act, or kept it pending: records the outcome and returns the note. */
type Done = (post: PostResponse & { status: 'posted' | 'pending' }, pv: PreviewResponse) => Promise<string>

/**
 * Previews `a` (or takes the preview the band already drew of it) and posts
 * it. Stops, keeping what was typed for a second Enter, when the preview
 * has a warning the person has not seen, asks for rewording, or when the
 * core holds the post because the thread has a reply the person has not
 * seen. Nothing posts without this, and this runs only on the person's Enter.
 */
async function send($: EngineInterface, one: Question, a: Act, verb: PlacedRow['verb'], done: Done): Promise<string> {
  const key = actKey(a)
  const cached = await read($, previewedAtom)
  const seen = cached?.key === key ? cached.res : undefined
  const got = seen ?? (await previewOf($, a))
  if (typeof got === 'string') return stop($, `${NOT_POSTED}${got}`)
  const pv = got
  if (pv.reword) return stop($, `${NOT_POSTED}${pv.reword}`)
  // A poll took the question being answered from under the cursor: what
  // was typed for it must not post unseen to the question now on screen.
  // A preview the band drew since, for that question, does not count as
  // seen: the band previews on its own timer, while the person may still
  // be typing.
  const moved = (await read($, displacedAtom)) !== null
  if (moved) await update($, displacedAtom, () => null)
  if (moved || (!seen && mustSee(pv))) return stop($, `${NOT_POSTED}check the preview first, then ⏎ again.`)
  const rowId = pv.post !== null ? await placeRow($, one, verb, pv.post, true) : undefined
  const res = await ask($, { command: 'post', session_id: await $.session.id(), preview: pv.id })
  await update($, previewedAtom, () => null)
  if (!res.ok || res.status === 'held' || res.status === 'failed') {
    if (rowId) await dropRow($, rowId)
    if (!res.ok) return stop($, `${NOT_POSTED}${res.error}`)
    if (res.status === 'failed') return stop($, `${NOT_POSTED}${res.why ?? 'the surface refused it.'}`)
    return held($, one, res.why)
  }
  if (rowId) await landRow($, rowId, res.status === 'pending', res.url)
  else if (res.status === 'posted') await placeRow($, one, verb, a.text ?? '', false)
  for (const w of res.warnings) $.ui.toast(w)
  return done(res as PostResponse & { status: 'posted' | 'pending' }, pv)
}

/** A post stopped: the notice, in the warning's colour, and what was typed kept for a second Enter. */
async function stop($: EngineInterface, note: string): Promise<string> {
  keepTyped()
  await update($, flashAtom, () => note)
  return note
}

/**
 * The core held the post: someone replied since the person last saw the
 * thread. A poll brings the replies, which are shown marked new.
 */
async function held($: EngineInterface, one: Question, why?: string): Promise<string> {
  const before = (await read($, seenAtom))[one.id]?.shown ?? one.replies.length
  await pollNow($, false)
  const now = (await queueOf($)).find(x => x.id === one.id)
  const fresh = others((now?.replies ?? []).slice(before))
  if (now) await update($, seenAtom, s => ({ ...s, [one.id]: { shown: now.replies.length, fresh: before } }))
  const names = [...new Set(fresh.map(r => r.who))].join(' and ')
  return stop($, names ? `${NOT_POSTED}${names} replied since you last read the thread. Read it, then ⏎ again.` : `${NOT_POSTED}${why ?? 'a reply arrived in the thread.'} Read it, then ⏎ again.`)
}


/** Records what was done with a question and moves to the next unanswered one. */
export async function settle($: EngineInterface, one: Question, answer: Answer, note: string): Promise<string> {
  let after: Record<string, Answer> = {}
  await update($, answersAtom, a => (after = { ...a, [one.id]: answer }))
  await update($, talkingAtom, () => null)
  await update($, decliningAtom, () => null)
  await update($, viewingAtom, () => null)
  await update($, pickingAtom, () => false)
  await update($, previewedAtom, () => null)
  const queue = await queueOf($)
  const next = nextFresh(queue.findIndex(x => x.id === one.id), after, queue)
  await update($, cursorAtom, () => next)
  await update($, flashAtom, () => note)
  await arrive($, next)
  return note
}

/** The note for a done act: the caller's `posted` note, or that the core kept it pending, and why. */
function landed(res: PostResponse & { status: 'posted' | 'pending' }, posted: string): string {
  return res.status === 'pending' ? `Kept pending: ${res.why ?? 'its channel is off'}. It is relayed once the channel works again.` : posted
}

const fields = (res: PostResponse & { status: 'posted' | 'pending' }, pv: PreviewResponse): Partial<Answer> => ({
  ...(pv.post !== null ? { post: pv.post } : {}),
  ...(res.url ? { url: res.url } : {}),
  ...(res.status === 'pending' ? { pending: res.why ?? 'its channel is off' } : {}),
})

async function relay($: EngineInterface, c: Ctx, one: Question, text: string): Promise<string> {
  return send($, one, { question: one.id, action: 'answer', text, ...(c.place ? { place: c.place } : {}) }, one.branch ? 'logged' : 'answered', (res, pv) =>
    settle(
      $,
      one,
      { kind: 'answer', text, ...fields(res, pv) },
      landed(res, one.branch ? `Logged your answer on ${one.branch.repo}'s questions branch, in a new file; nothing posted` : `Relayed to ${SURFACE_NAME[one.surface]} ${one.where}`),
    ),
  )
}

/** Agrees to filter 1's recorded answer shown beside the question. */
async function agree($: EngineInterface, c: Ctx, one: Question): Promise<string> {
  return send($, one, { question: one.id, action: 'agree', ...(c.place ? { place: c.place } : {}) }, 'recorded', (res, pv) =>
    settle(
      $,
      one,
      { kind: 'recorded', text: '', ...fields(res, pv) },
      landed(res, pv.post === null ? 'Agreed to the recorded answer; nothing posted' : `Posted the recorded answer on ${SURFACE_NAME[one.surface]} ${one.where}`),
    ),
  )
}

async function sendAsk($: EngineInterface, _c: Ctx, one: Question, text: string): Promise<string> {
  return send($, one, { question: one.id, action: 'ask', text }, 'asked', async (res, pv) => {
    await update($, askingAtom, a => without(a, one.id))
    return settle($, one, { kind: 'wait', text, ...fields(res, pv) }, landed(res, `Asked ${one.asker.name} on ${SURFACE_NAME[one.surface]}. Their question waits for the reply; nothing else does.`))
  })
}

/** Puts what was posted back in the prompt box to change; Enter then updates the post where it is. */
async function startEdit($: EngineInterface, one: Question, a?: Answer): Promise<string> {
  if (!a?.post) return ''
  await update($, editingAtom, () => ({ [one.id]: true as const }))
  await putInBox($, bodyOf(a.post))
  return 'Your post is in the prompt box: change it, then ⏎'
}

async function stopEdit($: EngineInterface, one: Question): Promise<string> {
  await update($, editingAtom, e => without(e, one.id))
  await putInBox($, '')
  return 'Kept as posted'
}

async function editPost($: EngineInterface, _c: Ctx, one: Question, text: string): Promise<string> {
  return send($, one, { question: one.id, action: 'edit', text }, 'edited', async (_res, pv) => {
    await update($, answersAtom, a => {
      const was = a[one.id]
      return was ? { ...a, [one.id]: { ...was, text, edited: true as const, ...(pv.post !== null ? { post: pv.post } : {}) } } : a
    })
    await update($, editingAtom, e => without(e, one.id))
    const note = `Edited your post on ${SURFACE_NAME[one.surface]} ${one.where}`
    await update($, flashAtom, () => note)
    return note
  })
}

/**
 * The model's draft of the person's reply, from propose_reply: back to the
 * question view with the draft in the prompt box, where the band previews
 * the post and Enter acts on it as on anything typed, after any edit. In a
 * filter 1 decline it fills only the record's URL. Posts nothing.
 */
export async function proposeReply($: EngineInterface, draft: string): Promise<{ ok: boolean; text: string }> {
  if (draft.startsWith('/') || draft.trimStart().startsWith('/')) {
    return { ok: false, text: 'Refused: a draft starting with / would run as a command in the prompt box. Write it without the leading /.' }
  }
  if ((await read($, serviceAtom)).status !== 'open') return { ok: false, text: 'The answer service is not open, so nothing was drafted.' }
  const c = await snapshot($)
  if (c.declining?.stage === 'place' && c.q) {
    const place = draft.replace(new RegExp(`^\\s*${RECORDED.trim()}\\s*`, 'i'), '').replace(/^see the record below\.\s*/i, '').replace(/^Recorded in:\s*/i, '').trim()
    if (!place) return { ok: false, text: 'The place was empty, so nothing was put in the prompt box.' }
    if (/\s/.test(place)) return { ok: false, text: "Refused: here the draft fills only the record's URL, one link with no space or line break." }
    if (place.startsWith('/')) return { ok: false, text: 'Refused: a place starting with / would run as a command in the prompt box.' }
    await update($, talkingAtom, () => null)
    await update($, flashAtom, () => 'Claude filled in where it is recorded: check it in the prompt box, then ⏎')
    await putInBox($, place)
    return { ok: true, text: `The record's URL is in the person's prompt box on the question "${cut(c.q.text, 80)}". They check it; the reply posts only when they press Enter. Do not post it yourself.` }
  }
  if (c.declining) return { ok: false, text: "The person is choosing why they won't answer this question, so nothing was drafted." }
  const text = draft.replace(new RegExp(`^\\s*${PREFIX.trim()}\\s*`, 'i'), '').trim()
  const q = c.q
  if (!q || !(c.open || c.editing)) return { ok: false, text: 'No open question or post being edited is on screen in the answer service, so nothing was drafted.' }
  if (!text) return { ok: false, text: 'The draft was empty, so nothing was put in the prompt box.' }
  if (text.startsWith('/')) return { ok: false, text: 'Refused: a draft starting with / would run as a command in the prompt box.' }
  await update($, askingAtom, a => without(a, q.id))
  await update($, talkingAtom, () => null)
  await update($, flashAtom, () =>
    c.editing ? 'Claude drafted the edit: change it in the prompt box if you like, then ⏎ updates your post' : 'Claude drafted a reply: edit it in the prompt box if you like, then ⏎ relays it',
  )
  await putInBox($, text)
  return { ok: true, text: `The draft is in the person's prompt box on the question "${cut(q.text, 80)}". They confirm or edit it; it posts only when they press Enter. Do not post it yourself.` }
}

// ── another place for the record ────────────────────────────────────────

async function startPicking($: EngineInterface): Promise<string> {
  await update($, pickingAtom, () => true)
  await update($, flashAtom, () => null)
  return 'Choose where the answer is recorded'
}

async function stopPicking($: EngineInterface): Promise<string> {
  await update($, pickingAtom, () => false)
  return 'Back to the question'
}

async function pickPlace($: EngineInterface, one: Question, place: string): Promise<string> {
  await update($, placesAtom, p => ({ ...p, [one.id]: place }))
  await update($, knownPlacesAtom, k => (k.includes(place) ? k : [...k, place]))
  await update($, pickingAtom, () => false)
  await update($, previewedAtom, () => null)
  const note = `The answer will be recorded in ${place}`
  await update($, flashAtom, () => note)
  return note
}

// ── declining ───────────────────────────────────────────────────────────

async function startDecline($: EngineInterface, one: Question): Promise<string> {
  await update($, decliningAtom, () => ({ id: one.id, stage: 'reason' as const }))
  await update($, flashAtom, () => null)
  return `Won't answer ${one.asker.name}'s question: choose why.`
}

async function backDecline($: EngineInterface, one: Question, d: Declining): Promise<string> {
  await update($, previewedAtom, () => null)
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

/** Reason 1: nothing to answer. The core records it on this machine; nothing posts. */
async function decline($: EngineInterface, _c: Ctx, one: Question): Promise<string> {
  return send($, one, { question: one.id, action: 'decline', reason: 1 }, 'wont', (_res, pv) =>
    settle($, one, { kind: 'wont', text: '', reason: 1, ...(pv.post !== null ? { post: pv.post } : {}) }, `Won't answer ${one.asker.name}'s question: nothing to answer. Nothing posted.`),
  )
}

async function startFilter($: EngineInterface, one: Question): Promise<string> {
  await update($, decliningAtom, () => ({ id: one.id, stage: 'filter' as const }))
  await update($, flashAtom, () => null)
  return `The inquisitor should have handled ${one.asker.name}'s question: choose the filter that should have stopped it. Nothing is posted yet.`
}

async function chooseFilter($: EngineInterface, one: Question, n: Filter): Promise<string> {
  await update($, flashAtom, () => null)
  if (n === 1) {
    await update($, decliningAtom, () => ({ id: one.id, stage: 'place' as const }))
    return 'Filter 1, already answered: give where the answer is recorded'
  }
  await update($, decliningAtom, () => ({ id: one.id, stage: 'post' as const, filter: n }))
  return `Filter ${n}, ${FILTERS[n].name}: check the reply, then ⏎ posts it`
}

async function setPlace($: EngineInterface, one: Question, place: string): Promise<string> {
  await update($, flashAtom, () => null)
  await update($, decliningAtom, () => ({ id: one.id, stage: 'post' as const, filter: 1 as const, place }))
  return `Filter 1, already answered: ${RECORDED}see the record below. Check the reply, then ⏎ posts it`
}

/** Posts the chosen filter's reply for the inquisitor, and closes the question; `note` becomes what the logged miss says. */
async function answerForInquisitor($: EngineInterface, _c: Ctx, one: Question, d: Extract<Declining, { stage: 'post' }>, note: string): Promise<string> {
  if (d.filter === 1 && !d.place) return "There is no place for the recorded answer: without it, it can't post as filter 1."
  return send($, one, declineAct(one, d, note), 'inquisitor', (res, pv) =>
    settle(
      $,
      one,
      { kind: 'handled', filter: d.filter, text: note.trim(), ...fields(res, pv) },
      landed(
        res,
        `${pv.post === null ? 'Declined' : `Answered ${one.asker.name}'s question for the inquisitor on ${SURFACE_NAME[one.surface]} ${one.where}`}. A miss is logged against filter ${d.filter}${note.trim() ? `, with your note: ${note.trim()}` : '.'}`,
      ),
    ),
  )
}

/** Reopens a question declined here with nothing posted: it is back in the queue. */
async function reopen($: EngineInterface, one: Question): Promise<string> {
  const was = (await read($, answersAtom))[one.id]
  if (was?.kind !== 'wont' || one.branch) return ''
  const res = await ask($, { command: 'reopen', session_id: await $.session.id(), question: one.id })
  if (!res.ok) return stop($, `Not reopened: ${res.error}`)
  await update($, answersAtom, a => without(a, one.id))
  const note = `Reopened ${one.asker.name}'s question: ${CLOSED.undo}`
  await update($, flashAtom, () => note)
  return note
}

// ── talking to Claude ───────────────────────────────────────────────────

/** Why a completion gave no text, in a few words. */
function why(r: ModelCompleteResult): string {
  if (r.isAnswered) return ''
  if (r.reason === 'api-error') return `the API answered ${r.status ?? 'with an error'}`
  if (r.reason === 'aborted') return 'the call timed out'
  return 'the reply was empty'
}

/** One completion on the session's own model; an error in words, never a throw. */
async function complete($: EngineInterface, system: string, prompt: string, maxTokens: number): Promise<{ ok: true; text: string } | { ok: false; error: string }> {
  try {
    const model = await $.session.model()
    const r = await $.model.complete({ model, system, prompt, maxTokens, timeoutMs: 120_000 })
    return r.isAnswered ? { ok: true, text: r.text.trim() } : { ok: false, error: why(r) }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) }
  }
}

export async function think($: EngineInterface, id: string, kind: 'reply' | 'rephrase' | 'draft' | undefined): Promise<void> {
  await update($, thinkingAtom, t => (kind ? { ...t, [id]: kind } : without(t, id)))
}
export async function addTurn($: EngineInterface, id: string, turn: { who: 'you' | 'model' | 'error'; text: string }): Promise<void> {
  await update($, talksAtom, t => ({ ...t, [id]: [...(t[id] ?? []), turn] }))
}

async function openTalk($: EngineInterface, _one: Question): Promise<string> {
  await update($, flashAtom, () => null)
  await update($, talkingAtom, () => _one.id)
  return 'Talking to Claude'
}

async function backToQuestion($: EngineInterface, one: Question): Promise<string> {
  await update($, askingAtom, a => without(a, one.id))
  await update($, talkingAtom, () => null)
  return 'Back to the question'
}

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

/** The core's context for a question: the question and its thread as quoted data, and the session's instructions. */
export async function contextOf($: EngineInterface, id: string): Promise<string | undefined> {
  const res = await ask($, { command: 'context', session_id: await $.session.id(), question: id })
  return res.ok ? res.context : undefined
}

/**
 * The person's message, kept with the question in the band and in the
 * core's discussion record, as it goes to the session's model.
 */
export async function recordSay($: EngineInterface, one: Question, text: string): Promise<void> {
  await addTurn($, one.id, { who: 'you', text })
  await think($, one.id, 'reply')
  await update($, awaitingAtom, w => [...w, { id: one.id, text: text.trim() }])
  void ask($, { command: 'discussion.append', session_id: await $.session.id(), question: one.id, role: 'person', text })
}

/** The discussion so far, as the one user message a completion takes. */
function transcript(turns: { who: string; text: string }[]): string {
  return turns
    .filter(t => t.who !== 'error')
    .map(t => `${t.who === 'you' ? 'The person' : 'You'}: ${t.text}`)
    .join('\n\n')
}

/** Reads the rephrasing the model returned as JSON, or undefined when it is not usable. */
export function parseRevision(text: string, hasOptions: boolean): { text: string; context: string; options?: { label: string; effect: string }[]; summary: string } | undefined {
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
  const question = r['question']
  if (typeof question !== 'string' || !question.trim()) return undefined
  const list = r['options']
  const options = Array.isArray(list)
    ? list
        .filter((o): o is { label: string; effect: string } => {
          const one = o as Record<string, unknown> | null
          return typeof one?.['label'] === 'string' && typeof one['effect'] === 'string'
        })
        .slice(0, 4)
    : []
  if (hasOptions && options.length < 2) return undefined
  const context = r['context']
  const summary = r['summary']
  return {
    text: question.trim(),
    context: typeof context === 'string' ? context.trim() : '',
    ...(hasOptions ? { options } : {}),
    summary: typeof summary === 'string' ? summary.trim() : '',
  }
}

/** The question rewritten in light of the discussion, then asked again. */
async function rephrase($: EngineInterface, one: Question): Promise<string> {
  void (async () => {
    await think($, one.id, 'rephrase')
    const shape = one.options
      ? '{"question": string, "context": string (one or two sentences, or ""), "options": [{"label": string, "effect": string}] (2 to 4 answers, the recommended one first), "summary": string (one sentence: what the discussion settled)}'
      : '{"question": string (what is being asked, restated clearly), "context": string (one or two sentences, or ""), "options": [], "summary": string (one sentence: what the discussion settled)}'
    const talks = (await read($, talksAtom))[one.id] ?? []
    const r = await complete(
      $,
      (await contextOf($, one.id)) ?? '',
      `${transcript(talks)}\n\nThe discussion is over. Rewrite the question in light of it, so that the person can answer it at once: keep what the asker needs to know, use the words the discussion made clear, and drop what confused them. Answer with JSON only, in this shape:\n${shape}`,
      1500,
    )
    const revision = r.ok ? parseRevision(r.text, !!one.options) : undefined
    await think($, one.id, undefined)
    if (!revision) {
      await addTurn($, one.id, { who: 'error', text: !r.ok ? `Could not rephrase: ${r.error}. r and Enter try again.` : 'The rephrasing came back unreadable. r and Enter try again.' })
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
    const talks = (await read($, talksAtom))[one.id] ?? []
    const r = await complete(
      $,
      (await contextOf($, one.id)) ?? '',
      `${transcript(talks)}\n\nDraft the one clarifying question the person should send back to ${one.asker.name} in the thread, about what the discussion shows is unclear. Write it as the person would: one or two plain sentences addressed to them, no greeting, no sign-off, no quotation marks.`,
      300,
    )
    await think($, one.id, undefined)
    if (!r.ok) {
      await addTurn($, one.id, { who: 'error', text: `Could not draft a question: ${r.error}. Write your own in the prompt box.` })
      return
    }
    const still = (await read($, askingAtom))[one.id]
    const draft = r.text.replace(/^["“]|["”]$/g, '').trim()
    if (still && !draft.startsWith('/') && !(await $.prompt.read()).text.trim()) await putInBox($, draft)
  })()
  return `Drafting a question for ${one.asker.name}`
}

// ── rows in the transcript ──────────────────────────────────────────────
//
// Each question answered, declined or edited leaves a row at the
// transcript's end, drawn by the Placed hook. The row says what was done
// and what was posted; it shows "posting" until the post lands, then a
// link to it.

/** The word a transcript row opens with, saying what was done. */
export const DONE_WORD: Record<PlacedRow['verb'], string> = {
  answered: 'Relayed.',
  logged: 'Logged.',
  asked: 'Asked.',
  wont: "Won't answer.",
  recorded: 'Posted.',
  inquisitor: 'Posted.',
  edited: 'Edited.',
  pending: 'Kept pending.',
}

async function placeRow($: EngineInterface, one: Question, verb: PlacedRow['verb'], text: string, posts: boolean): Promise<string | undefined> {
  const rows = await read($, rowsAtom)
  const id = `${one.id}_${Object.keys(rows).length + 1}`.replace(/[^\w-]/g, '_')
  const shown = verb === 'wont' ? REASONS[1].label.toLowerCase() : text
  await update($, rowsAtom, r => ({ ...r, [id]: { id: one.id, verb, text: shown, posts } }))
  if (posts) await update($, postingAtom, p => ({ ...p, [id]: true as const }))
  const placed = await $.ui.place({ id }).catch(() => undefined)
  if (!placed?.isPlaced) {
    await dropRow($, id)
    return undefined
  }
  return id
}

async function dropRow($: EngineInterface, id: string): Promise<void> {
  await update($, rowsAtom, r => without(r, id))
  await update($, postingAtom, p => without(p, id))
}

/** A placed row's post landed, or was kept pending. */
async function landRow($: EngineInterface, id: string, pending: boolean, url?: string): Promise<void> {
  await update($, postingAtom, p => without(p, id))
  await update($, rowsAtom, r => {
    const row = r[id]
    if (!row) return r
    return { ...r, [id]: { ...row, ...(pending ? { verb: 'pending' as const, posts: false } : {}), ...(url ? { url } : {}) } }
  })
}

/** The service's own prefixes, which the band draws bold. */
export const OWN_PREFIXES = [RECORDED, INQUISITOR]

// What the mod's tests stand in for: the engine's side of a session, and a
// fake core answering each command with the core's worked example
// (core-examples.ts, a copy of scripts/fixtures/service/examples.json) or
// with what a test gives it.
import { mock } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

import { EXAMPLES } from './core-examples'

/** The band above the prompt in a fullscreen terminal of 140 × 40. */
export const BAND = {
  plugin: 'inquisitor-answer-mod',
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isCollapsed: false,
    isWorking: false,
    maxRows: 15,
    bodyColumns: 135,
    scroll: { offset: 0, bodyRows: 14 },
    view: {},
  },
  viewport: { columns: 140, rows: 40, isFullscreen: true },
} as const

export const TYPED = { origin: { kind: 'composer' }, wait: false } as const

/** A request the mod sent the core. */
export type Req = { command: string } & Record<string, unknown>
type Answerer = (req: Req) => unknown | Promise<unknown>

export const OPENED = { version: 1, ok: true, status: 'opened', screen: null, notices: [] }
export const DONE = { version: 1, ok: true }

/** The poll example's question, with another id and the fields a test changes. */
export function question(id: string, over: Record<string, unknown> = {}): Record<string, unknown> {
  return { ...EXAMPLES.poll.response.questions[0], replies: [], new: false, id, ...over }
}

/** A poll's response showing `questions`. */
export function polled(questions: unknown[], extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { version: 1, ok: true, questions, judge: [], notices: [], rate_limited_until: null, ...extra }
}

/** A preview of `post`, recorded in o/api, private, unless `extra` gives another record. */
export function previewOf(post: string | null, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { version: 1, ok: true, id: 'pv-1', post, record: { place: 'o/api', visibility: 'private' }, warnings: [], ...extra }
}

export const POSTED = { version: 1, ok: true, status: 'posted', url: 'https://github.com/o/api/pull/12#issuecomment-1003', warnings: [] }

type Options = {
  /** False for a session the answer launcher did not start. */
  marker?: boolean
  /** The fake core's answer per command, over the examples. */
  core?: Record<string, Answerer>
  /** The session's tool list, as the engine built it. */
  tools?: string[]
  /** Why the engine drops a prompt the mod submits, such as a settings hook's refusal. */
  drop?: (text: string) => string | undefined
}

/**
 * A session with the engine stood in for. `calls` is every request the mod
 * sent the core; `of(command)` those of one command. Call it before the
 * test's first `$` call: like every test hook, the engine hooks it adds
 * must come first.
 */
export function session(on: On, opts: Options = {}) {
  const calls: Req[] = []
  const core: Record<string, Answerer> = {
    open: () => OPENED,
    poll: () => polled([]),
    'pending.list': () => ({ version: 1, ok: true, answers: [] }),
    'setup.status': () => ({ version: 1, ok: true, complete: true, config: { github: { relay: 'answers', subscriptions: ['o'] } }, checks: [] }),
    'screen.set': () => DONE,
    'discussion.append': () => DONE,
    close: () => DONE,
    ...opts.core,
  }
  on('process.run', async (_, e) => {
    const req = JSON.parse(e.init?.stdin ?? '{}') as Req
    calls.push(req)
    const answer = core[req.command]
    const example = (EXAMPLES as Record<string, { response: unknown }>)[req.command]
    const res = answer ? await answer(req) : example ? example.response : { version: 1, ok: false, error: `no answer for ${req.command}` }
    return { value: { exitCode: 0, stdout: `${JSON.stringify(res)}\n`, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  mock.env(on, opts.marker === false ? {} : { INQUISITOR_ANSWER: '1' })
  const clock = mock.clock(on, { now: Date.parse('2026-10-20T10:05:00Z') })
  on('session.id', () => ({ value: 'sess-1' }))
  on('tool.list', () => ({ value: (opts.tools ?? []).map(name => ({ name, description: name, mcp: name.startsWith('mcp__') })) }))
  const registered: string[] = []
  on('tool.register', (_, e) => {
    registered.push(e.name)
    return { value: { tool: `mcp__inquisitor-answer-mod__${e.name}` } }
  })
  const commands: string[] = []
  on('command.register', (_, e) => {
    commands.push(e.name)
    return { value: { command: e.name } }
  })
  const filled: string[] = []
  on('prompt.fill', (_, e) => {
    filled.push(e.text)
    return { isFilled: true }
  })
  on('prompt.read', () => ({ value: { text: '', cursor: 0 } }))
  on('prompt.change', (_, e) => ({ text: e.text }))
  const sent: string[] = []
  const contexts: (readonly string[] | undefined)[] = []
  on('prompt.submit', async (_, e) => {
    await self.onSubmit?.()
    const dropped = opts.drop?.(e.text)
    if (dropped !== undefined) return { drop: dropped }
    sent.push(e.text)
    contexts.push(e.context)
    return { text: e.text, ...(e.context ? { context: e.context } : {}) }
  })
  on('tool.offer', () => ({ isOffered: true }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', (_, e) => ({ text: e.answer }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.end', (_, e) => ({ sessionId: e.sessionId }))
  on('ui.render', { component: 'AbovePrompt' }, ($, e) => {
    const { Box } = $.ui.resolve(e)
    return <Box key="engine" />
  })
  const toasts: string[] = []
  on('ui.toast', (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.notify', () => ({ value: { isSent: true, channel: 'client' as const } }))
  on('audio.play', () => ({ value: undefined }))
  on('ui.place', (_, e) => ({ value: { isPlaced: true as const, requestId: e.id } }))
  const exits: string[] = []
  on('command.run', { command: 'exit' }, () => {
    exits.push('exit')
    return { text: '' }
  })
  const aborts: string[] = []
  on('turn.abort', (_, e) => {
    aborts.push(e.turnId)
    return { value: undefined }
  })
  let turns = 0
  const self = {
    /** Called after Enter's prompt is dropped, before the engine puts it back. */
    onDrop: undefined as undefined | (() => Promise<unknown>),
    /** Called as a prompt reaches the engine beneath the mod, before it enters or is dropped. */
    onSubmit: undefined as undefined | (() => Promise<unknown>),
    calls,
    of: (command: string) => calls.filter(c => c.command === command),
    clock,
    registered,
    commands,
    filled,
    sent,
    contexts,
    toasts,
    exits,
    aborts,
    start: async ($: Engine) => {
      await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
      await clock.settle()
    },
    /** Enter on `text`; a drop is put back in the box, as the engine does, as `back` (a long paste shows collapsed). */
    enter: async ($: Engine, text: string, back = text) => {
      const res = await $.prompt.submit({ ...TYPED, text })
      if (res.drop !== undefined) await self.onDrop?.()
      if (res.drop !== undefined) await ($.prompt as unknown as { change(e: unknown): Promise<unknown> }).change({ text: back, cursor: back.length, origin: { kind: 'engine' } })
      await clock.settle()
      return res.drop
    },
    slash: ($: Engine, command: string, args = '') => $.command.run({ command, args, origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 140 } }),
    /** A turn of the main conversation for the last prompt, ended with `answer`. */
    reply: async ($: Engine, answer: string, text?: string) => {
      const turnId = `turn-${++turns}`
      await $.turn.start({ text: text ?? sent[sent.length - 1] ?? '', turnId })
      await $.turn.complete({ answer, durationMs: 1, isAborted: false, turnId, reason: 'answer' })
      await clock.settle()
      return turnId
    },
  }
  return self
}

/**
 * Types `text` into the prompt box, as a `prompt.change` the band answers
 * with its debounced preview. The test engine raises it, though its type
 * lists no such call.
 */
export function typeInBox($: Engine, text: string): Promise<unknown> {
  return ($.prompt as unknown as { change(e: unknown): Promise<unknown> }).change({ text, cursor: text.length, origin: { kind: 'app' } })
}

/**
 * Enter as the engine raises it: the box emptied first (a prompt.change of
 * origin `clear`), then the prompt.submit, as Claude Code 2.1.332 orders them.
 */
export async function enterAsTyped($: Engine, s: { enter: ($: Engine, text: string, back?: string) => Promise<string | undefined> }, text: string, back = text): Promise<string | undefined> {
  await ($.prompt as unknown as { change(e: unknown): Promise<unknown> }).change({ text: '', cursor: 0, origin: { kind: 'clear' } })
  return s.enter($, text, back)
}

type Drawn = {
  redraw(): Promise<unknown>
  find(query: { type?: string; text?: RegExp; key?: string }): Promise<unknown>
}

/** Text on screen, drawn as a Text, or as Markdown for a post's words. */
export async function shown(ui: Pick<Drawn, 'find'>, text: RegExp): Promise<unknown> {
  for (const type of ['Text', 'Markdown']) {
    const found = await ui.find({ type, text })
    if (found) return found
  }
  return undefined
}

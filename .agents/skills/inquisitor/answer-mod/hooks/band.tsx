// The band above the prompt: the answer service, as wide as the terminal and
// as tall as the engine lets it be, every row fitted to that height.
import { atom, read } from 'claude-code'
import type { EngineInterface, RenderElement } from 'claude-code'

import type { Answer, Declining, Filter, PlacedRow } from '../types'
import {
  AT_RIGHT,
  NOT_POSTED,
  actKey,
  actOf,
  commands,
  intent,
  noticeForms,
  openLinked,
  openQuestion,
  pressKey,
  putInBox,
  queueLinks,
  snapshot,
  goTo,
  queueOf,
} from './actions'
import type { Command } from './actions'
import type { PreviewResponse } from './core-protocol'
import {
  CLOSED,
  FILTERS,
  INQUISITOR,
  PREFIX,
  RECORDED,
  REASONS,
  RESERVED,
  SURFACE_NAME,
  ago,
  cut,
  emphasised,
  filterReply,
  others,
  unmark,
  wrap,
  wrapLines,
} from './questions'
import type { Question, Reply } from './questions'
import { SETUP_HELP, channelsOf, checkOf, surfaceOf, SURFACES } from './setup'
import { serviceKey } from './screens'
import { toolsMessage } from './service'
import { INITIAL } from './state'

const answersAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'answers' } as const, INITIAL.answers)
const askingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'asking' } as const, INITIAL.asking)
const cursorAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'cursor' } as const, INITIAL.cursor)
const flashAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'flash' } as const, INITIAL.flash)
const knownPlacesAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'knownPlaces' } as const, INITIAL.knownPlaces)
const markedAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'marked' } as const, INITIAL.marked)
const originalAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'original' } as const, INITIAL.original)
const pendingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'pending' } as const, INITIAL.pending)
const postingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'posting' } as const, INITIAL.posting)
const previewedAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'previewed' } as const, INITIAL.previewed)
const promptAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'prompt' } as const, INITIAL.prompt)
const rephrasedAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'rephrased' } as const, INITIAL.rephrased)
const relaysAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'relays' } as const, INITIAL.relays)
const rowsAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'rows' } as const, INITIAL.rows)
const serviceAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'service' } as const, INITIAL.service)
const talkingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'talking' } as const, INITIAL.talking)
const talksAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'talks' } as const, INITIAL.talks)
const thinkingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'thinking' } as const, INITIAL.thinking)

// One accent colour, plus a tone each for success, warning and subtle
// text; the rest is weight, dimness and space. Theme keys, so the palette
// follows the person's theme.
export const ACCENT = 'suggestion'
export const DONE = 'success'
export const LATER = 'warning'
export const RULE = 'subtle'
/** Each state's dot, in the bar and the summary: ○ unanswered, ◉ on screen and ◇ in a conversation are drawn beside these. */
export const GLYPH: Record<Answer['kind'], string> = { answer: '●', defer: '◐', wait: '◌', wont: '⊘', recorded: '◎', handled: '◈' }
const glyphOf = (a: Answer) => (a.pending ? '◌' : a.kind === 'recorded' && !a.auto ? GLYPH.answer : GLYPH[a.kind])
const TONE: Record<Answer['kind'], string> = { answer: DONE, defer: LATER, wait: ACCENT, wont: RULE, recorded: DONE, handled: DONE }
const toneOf = (a: Answer) => (a.pending ? LATER : TONE[a.kind])

/** What the bar shows at its right end: nothing, so that end stays free. */
const RIGHT = ''

/**
 * The parts of a view, which the trims below shrink to fit its height, one
 * step at a time in TRIMS' order: space first, then labels and repetition,
 * then detail. The question itself, the options' labels and the post's
 * first line stay.
 */
type Gap = 'question' | 'context' | 'choices' | 'preview' | 'reply' | 'related' | 'thread'
const GAP_ORDER: Gap[] = ['question', 'context', 'choices', 'preview', 'reply', 'related', 'thread']

type Trim = {
  gaps: number
  label: boolean
  optionGap: boolean
  effects: 'full' | 'line' | 'none'
  ownWords: boolean
  related: boolean
  provenance: 0 | 1 | 2
  bubble: number
  preview: 'full' | 'line'
  replies: 'full' | 'latest' | 'lines' | 'count'
  record: 'full' | 'short' | 'line' | 'head'
}
const TRIMS: Trim[] = (() => {
  let t: Trim = {
    gaps: GAP_ORDER.length,
    label: true,
    optionGap: true,
    effects: 'full',
    ownWords: true,
    related: true,
    provenance: 2,
    bubble: 6,
    preview: 'full',
    replies: 'full',
    record: 'full',
  }
  const steps: Partial<Trim>[] = [
    {},
    { gaps: 3 },
    { label: false },
    { optionGap: false },
    { replies: 'latest' },
    { ownWords: false },
    { effects: 'line' },
    { record: 'short' },
    { replies: 'lines' },
    { related: false },
    { gaps: 2 },
    { gaps: 1 },
    { gaps: 0 },
    { provenance: 1 },
    { record: 'line' },
    { replies: 'count' },
    { bubble: 2 },
    { effects: 'none' },
    { bubble: 1 },
    { preview: 'line' },
    { record: 'head' },
    { provenance: 0 },
  ]
  return steps.map(step => (t = { ...t, ...step }))
})()

/** A post's reserved prefix and the rest, so the band can style the prefix. */
function splitPost(post: string): [string, string] {
  const prefix = RESERVED.find(p => post.startsWith(p)) ?? ''
  return [prefix, post.slice(prefix.length)]
}

type BandEvent = {
  surface: 'terminal' | 'desktop' | 'vscode' | 'mobile'
  props: { maxRows: number; bodyColumns: number; hasSurvey: boolean }
  viewport?: { columns: number; rows: number; isFullscreen?: boolean } | undefined
}

export async function band($: EngineInterface, e: BandEvent, ui: ReturnType<EngineInterface['ui']['resolve']>): Promise<RenderElement | undefined> {
  const { Box, Text, Button, Link, Markdown } = ui
  const service = await read($, serviceAtom)
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
  const relays = await read($, relaysAtom)
  const previewed = await read($, previewedAtom)
  const knownPlaces = await read($, knownPlacesAtom)

  // ── the room ─────────────────────────────────────────────────────────
  const cols = Math.max(30, e.props.bodyColumns)
  const vp = e.viewport
  const isFullscreen = vp?.isFullscreen === true
  const promptRows = vp ? wrap(draft, Math.max(10, vp.columns - 4)).length : 1
  const H = Math.max(5, isFullscreen || !vp ? e.props.maxRows : Math.min(e.props.maxRows, vp.rows - 5 - promptRows))
  const isWide = cols >= 100
  const GUTTER = 3
  const LW = isWide ? Math.min(96, Math.floor((cols - GUTTER) * 0.47)) : cols
  const RW = isWide ? Math.min(110, cols - GUTTER - LW) : cols
  const hasRule = H >= 14
  const B = H - 2 - (hasRule ? 1 : 0)

  const queue = await queueOf($)
  const N = queue.length
  const at = Math.min(Math.max(cursor, 0), N)
  const base = at < N ? queue[at] : undefined
  const kinds = queue.map(one => answers[one.id])
  const count = (test: (a: Answer) => boolean) => kinds.filter((a): a is Answer => !!a && test(a)).length
  const pendingCount = count(a => !!a.pending)
  const relayed = count(a => !a.pending && (a.kind === 'answer' || (a.kind === 'recorded' && !a.auto)))
  const deferred = count(a => a.kind === 'defer')
  const waiting = count(a => !a.pending && a.kind === 'wait')
  const wont = count(a => a.kind === 'wont')
  const recorded = count(a => a.kind === 'recorded' && !!a.auto)
  const handledForYou = count(a => a.kind === 'handled' && !!a.auto)
  const mine = count(a => !a.pending && a.kind === 'handled' && !a.auto)
  const fresh = N - kinds.filter(Boolean).length
  const marked = await read($, markedAtom)
  const markedAt = queue.flatMap((one, i) => (marked[one.id] ? [i] : []))

  const c = await snapshot($)
  const it = intent(c, draft, knownPlaces)
  const cmds = commands(c)
  const run = (doing: Promise<unknown>) => void doing.catch(() => undefined)
  const isTalking = !!base && talking === base.id
  const relayOf = (q: Question) => q.relay ?? relays[q.surface] ?? 'your relay'

  // ── rows ─────────────────────────────────────────────────────────────
  type Row = RenderElement
  const blanks = new WeakSet<object>()
  const blank = (): Row => {
    const row = <Text> </Text>
    if (typeof row === 'object' && row !== null) blanks.add(row)
    return row
  }
  const heads = new WeakMap<object, { k: number; inner: Row }>()
  const cuts = new WeakSet<object>()
  const cutRow = <R extends Row>(row: R): R => {
    if (typeof row === 'object' && row !== null) cuts.add(row)
    return row
  }
  const hasCut = (rows: Row[]) => rows.some(row => typeof row === 'object' && row !== null && cuts.has(row))
  const tall = (inner: Row, k: number): Row[] => {
    const n = Math.max(1, k)
    const head = (
      <Box height={n} flexShrink={0} overflow="hidden" flexDirection="column">
        {inner}
      </Box>
    )
    if (typeof head === 'object' && head !== null) heads.set(head, { k: n, inner })
    return [head, ...Array.from({ length: n - 1 }, () => <Box height={0} />)]
  }
  const take = (rows: Row[], n: number): Row[] => {
    const kept = rows.slice(0, Math.max(0, n))
    return kept.map((row, i) => {
      const block = typeof row === 'object' && row !== null ? heads.get(row) : undefined
      return block && i + block.k > kept.length ? cutRow(tall(block.inner, kept.length - i)[0]!) : row
    })
  }
  const md = (text: string, width: number, key: string, style: { bold?: boolean; dim?: boolean } = {}): Row[] => {
    const links = queueLinks(text, queue)
    const shown = style.bold ? emphasised(text) : text
    return tall(
      <Box width={width} flexDirection="column">
        {links.length ? (
          <Markdown key={key} text={shown} dimColor={!!style.dim} pressableLinks={links} onLinkPress={link => run(openLinked($, link.href))} />
        ) : (
          <Markdown text={shown} dimColor={!!style.dim} />
        )}
      </Box>,
      wrapLines(unmark(text), width).length,
    )
  }
  const quoted = (inner: Row, k: number, width: number, color?: string): Row[] =>
    tall(
      <Box flexDirection="row">
        <Box flexDirection="column" width={2} flexShrink={0}>
          {Array.from({ length: k }, () => (
            <Text {...(color ? { color } : {})} dimColor={!color}>
              │
            </Text>
          ))}
        </Box>
        <Box flexDirection="column" width={Math.max(8, width - 2)}>
          {inner}
        </Box>
      </Box>,
      k,
    )
  const plain = (text: string, style: { dim?: boolean; bold?: boolean; color?: string } = {}): Row => (
    <Text wrap="truncate-end" dimColor={!!style.dim} bold={!!style.bold} {...(style.color ? { color: style.color } : {})}>
      {text || ' '}
    </Text>
  )
  const dimLines = (text: string, width: number) => wrap(text, width).map(line => plain(line, { dim: true }))
  const label = (words: string, name?: string): Row => (
    <Text wrap="truncate-end">
      <Text dimColor>{words.toUpperCase()}</Text>
      {name ? <Text> {name}</Text> : ''}
    </Text>
  )
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
    return [...take(rows, budget - 1), cutRow(plain('⋯', { dim: true }))]
  }
  // A post exactly as it goes out, behind a bar, at most `max` rows; its
  // reserved prefix dim for `User says: `, bold for every other.
  const bubble = (post: string | undefined, color: string, width: number, max: number): Row[] => {
    const [prefix, rest] = splitPost(post ?? `${PREFIX}…`)
    const k = Math.min(Math.max(1, max), wrapLines(prefix + rest, Math.max(10, width - 2)).length)
    const own = prefix !== PREFIX
    return quoted(
      <Text maxLines={k}>
        <Text dimColor={!own} bold={own}>
          {prefix}
        </Text>
        <Text dimColor={!post}>{rest}</Text>
      </Text>,
      k,
      width,
      color,
    )
  }

  // ── the bar ──────────────────────────────────────────────────────────
  const dots = queue.map((one, i) => {
    const a = answers[one.id]
    const isMarked = !!marked[one.id]
    const glyph = i === at && (!a || isTalking) ? (isTalking ? '◇' : '◉') : isMarked ? '▣' : !a ? '○' : glyphOf(a)
    const color = i === at || isMarked ? ACCENT : !a ? RULE : toneOf(a)
    return (
      <Button key={`dot:${i}`} plain onPress={() => run(goTo($, i))}>
        <Text color={color} bold={i === at || isMarked} dimColor={(a?.kind === 'wait' || a?.kind === 'wont') && i !== at}>
          {glyph}
        </Text>
      </Button>
    )
  })
  const toSummary = (
    <Button key="dot:summary" plain onPress={() => run(goTo($, N))}>
      <Text {...(at === N ? { color: ACCENT } : {})} bold={at === N} dimColor={at !== N}>
        summary
      </Text>
    </Button>
  )
  const newLabel = markedAt.length ? `${markedAt.length} new` : ''
  const counts = (
    [
      [fresh, 'unanswered'],
      [relayed, 'relayed'],
      [deferred, 'for later'],
      [waiting, 'waiting'],
      [pendingCount, 'pending'],
      [wont, "won't answer"],
      [recorded, 'done for you'],
      [handledForYou, 'handled for you'],
      [mine, 'for the inquisitor'],
    ] as const
  )
    .filter(([n]) => n > 0)
    .map(([n, words]) => `${n} ${words}`)
  const pos = base ? [`${at + 1} of ${N}`] : []
  const kept = [...pos, newLabel].filter(Boolean)
  const rest = isTalking ? ['talking to Claude'] : counts
  const fixed = 2 * N - 1 + 2 + 'summary'.length
  const room = cols - fixed - 2 - RIGHT.length
  let parts = kept
  for (let n = rest.length; n > 0; n--) {
    const ps = [...kept, ...rest.slice(0, n)]
    if (2 + ps.join(' · ').length <= room) {
      parts = ps
      break
    }
  }
  const tally = parts.length ? (
    <Box key="tally">
      {parts.map((part, i) => {
        const sep = i ? ' · ' : ''
        return part === newLabel ? (
          <Box key="new">
            {sep ? <Text dimColor>{sep}</Text> : null}
            <Button key="dot:new" plain onPress={() => run(goTo($, markedAt[0]!))}>
              <Text color={ACCENT} bold>
                {newLabel}
              </Text>
            </Button>
          </Box>
        ) : (
          <Text key={part} dimColor>
            {sep}
            {part}
          </Text>
        )
      })}
    </Box>
  ) : null
  const bar = (
    <Box height={1} overflow="hidden" justifyContent="space-between" width={cols} gap={2}>
      <Box gap={2} flexShrink={0}>
        <Box gap={1}>{dots}</Box>
        {toSummary}
        {tally}
      </Box>
      <Text dimColor wrap="truncate-end">
        {RIGHT}
      </Text>
    </Box>
  )

  // ── the keys ─────────────────────────────────────────────────────────
  const keyText = (key: string, what: string) => {
    const i = what.indexOf(`(${key})`)
    return i < 0 ? (
      <Text>
        <Text color={ACCENT}>{key}</Text>
        <Text dimColor>: {what}</Text>
      </Text>
    ) : (
      <Text>
        <Text dimColor>{what.slice(0, i)}</Text>
        <Text color={ACCENT}>({key})</Text>
        <Text dimColor>{what.slice(i + 3)}</Text>
      </Text>
    )
  }
  const keyButton = (cmd: Command, press: (key: string) => Promise<unknown> = k => pressKey($, k)) => (
    <Button key={`cmd:${cmd.key}`} plain onPress={() => run(cmd.posts ? putInBox($, cmd.key) : press(cmd.key))}>
      {keyText(cmd.key, cmd.what)}
    </Button>
  )
  const status = (room: number, refused?: string) =>
    refused ? (
      <Text color={LATER} wrap="truncate-end">
        {refused}
      </Text>
    ) : flash?.startsWith(NOT_POSTED) || flash?.startsWith('Notice: ') ? (
      <Text color={LATER} wrap="truncate-end">
        {noticeForms(flash).find(form => form.length <= room) ?? flash}
      </Text>
    ) : flash ? (
      <Text color={DONE} wrap="truncate-end">
        ✓ {flash}
      </Text>
    ) : null
  const keyGap = cols >= 100 ? 3 : 2
  const keys = (allHints: [string, string][], offered: Command[], press?: (key: string) => Promise<unknown>, refused?: string) => {
    const shown = offered.filter(cmd => !cmd.unlisted)
    const length = [...allHints.map(([key, what]) => `${key}: ${what}`), ...shown.filter(cmd => !cmd.aside).map(cmd => cmd.what)].reduce((n, w) => n + w.length + keyGap, 0)
    const hints = length > cols ? [] : allHints
    const left = [...hints.map(([key, what]) => `${key}: ${what}`), ...shown.filter(cmd => !AT_RIGHT.includes(cmd.key) && !cmd.aside).map(cmd => cmd.what)]
    const right = AT_RIGHT.flatMap(key => shown.filter(cmd => cmd.key === key)).map(cmd => cmd.what)
    const used = [...left, ...right].reduce((n, w) => n + w.length, 0) + keyGap * (left.length - 1 + right.length - 1 + 2)
    const said = status(Math.max(0, cols - used), refused)
    return (
      <Box height={1} overflow="hidden" justifyContent="space-between" width={cols} gap={keyGap}>
        <Box columnGap={keyGap} flexShrink={0}>
          {hints.map(([key, what]) => keyText(key, what))}
          {shown.filter(cmd => !AT_RIGHT.includes(cmd.key) && !cmd.aside).map(cmd => keyButton(cmd, press))}
        </Box>
        <Box gap={keyGap} flexShrink={1} justifyContent="flex-end">
          {said ? <Box flexShrink={1}>{said}</Box> : null}
          <Box gap={keyGap} flexShrink={0}>
            {AT_RIGHT.flatMap(key => shown.filter(cmd => cmd.key === key)).map(cmd => keyButton(cmd, press))}
          </Box>
        </Box>
      </Box>
    )
  }
  const frame = (body: Row, hints: [string, string][], shown: Command[], rows = B, top: Row = bar, press?: (key: string) => Promise<unknown>, refused?: string) => (
    <Box flexDirection="column" width={cols} height={rows === B ? H : rows + 2 + (hasRule ? 1 : 0)}>
      {hasRule && (
        <Text color={RULE} wrap="clip">
          {'─'.repeat(cols)}
        </Text>
      )}
      {top}
      <Box flexDirection="column" height={rows} overflow="hidden">
        {body}
      </Box>
      {keys(hints, shown, press, refused)}
    </Box>
  )
  const column = (rows: Row[], width: number) => (
    <Box flexDirection="column" width={width} flexShrink={0}>
      {rows}
    </Box>
  )
  const lift = (rows: number) => Array.from({ length: Math.floor((B - Math.min(B, rows)) * 0.4) }, blank)
  const columns = (left: Row[], right: Row[], lw: number, rw: number, centred = true, rows = B) => {
    const pad = centred ? lift(Math.max(left.length, right.length)) : []
    return (
      <Box flexDirection="row" height={rows}>
        {column([...pad, ...left], lw)}
        <Box flexDirection="column" width={GUTTER} flexShrink={0} alignItems="center">
          {Array.from({ length: rows }, () => (
            <Text color={RULE}>│</Text>
          ))}
        </Box>
        {column([...pad, ...right], rw)}
      </Box>
    )
  }

  // ── the screens a closed or unopened service shows ───────────────────
  //
  // Each in the question view's pattern: a dim head, what it means, and the
  // key row; the bar carries no dots while there is no queue.
  const quitOnly: Command[] = [{ key: 'q', what: '(q)uit' }]
  const emptyBar = <Box height={1} />
  const notice = (head: string, glyph: string, color: string, lines: string[], offered: Command[]) =>
    frame(
      <Box flexDirection="column">
        {[
          ...lift(lines.length + 1),
          <Text wrap="truncate-end">
            <Text color={color}>{glyph} </Text>
            <Text dimColor>{head.toUpperCase()}</Text>
          </Text>,
          ...lines.flatMap(line => (line ? wrap(line, Math.min(cols, 110)).map(l => plain(l)) : [blank()])),
        ]}
      </Box>,
      [],
      offered,
      B,
      emptyBar,
      key => serviceKey($, key),
    )
  if (service.status === 'opening') return notice('Opening the answer service', '◌', ACCENT, ['Reading the lock and the configuration…'], quitOnly)
  if (service.status === 'locked') {
    const lock = service.lock
    return notice(
      'Another session holds the answer service',
      '◌',
      LATER,
      [
        lock ? `${lock.session_name} · session ${lock.session_id} · started ${lock.started} · last refreshed ${lock.refreshed}` : 'The lock names another session.',
        '',
        'One answer service runs on each machine. (t)ake over: this session takes the lock, and the other closes its answer service before its next refresh, poll, post or push.',
      ],
      [{ key: 't', what: '(t)ake over' }, ...quitOnly],
    )
  }
  if (service.status === 'tools') {
    return notice('The answer service did not open', '⊘', LATER, [toolsMessage(service.tools), '', 'Its model may have only its own two tools and Read, Grep and Glob. Turn the mod or server off, then run answer again.'], quitOnly)
  }
  if (service.status === 'lost') return notice('The answer service closed', '⊘', RULE, ['Another session took it over. Nothing here polls, posts or pushes any more; your answers there carry on.'], quitOnly)
  if (service.status === 'closed') return notice('The answer service is closed', '⊘', RULE, [flash ?? 'Nothing polls while it is closed.', '', '/answer opens it again.'], quitOnly)
  if (service.status === 'setup') {
    const s = service.setup
    const setupCmds: Command[] = [{ key: 's', what: '(s)ave' }, { key: 'r', what: '(r)echeck' }, ...(service.back ? [{ key: 'b', what: 'go (b)ack' }] : []), { key: 'q', what: '(q)uit', unlisted: true }]
    if (!s) return notice('Setup', '⚙', ACCENT, [flash ?? 'Setup could not read the configuration.', '', '(r)echeck reads it again.'], setupCmds)
    const loginCheck = s.checks.find(k => k.surface === 'login')
    const mark = (ok: boolean | null | undefined) => (ok === true ? <Text color={DONE}>✓</Text> : ok === false ? <Text color={LATER}>✗</Text> : <Text dimColor>?</Text>)
    const channels = channelsOf(s.config)
    const W = Math.min(cols, 140)
    const rowsOut: Row[] = [
      <Text wrap="truncate-end">
        <Text color={ACCENT}>⚙ </Text>
        <Text dimColor>SETUP · THE ANSWER SERVICE · {s.complete ? 'COMPLETE' : 'NOT COMPLETE YET'}</Text>
      </Text>,
      <Text wrap="truncate-end">
        <Text dimColor>GitHub login </Text>
        <Text bold>{service.login ?? (loginCheck ? loginCheck.name : 'not set')}</Text>
        {loginCheck ? <Text> {mark(loginCheck.ok)}</Text> : ''}
        {!service.login && !loginCheck ? <Text color={LATER}> · needed: every answer file, and every miss file but a hash-only one, names you by it</Text> : ''}
      </Text>,
    ]
    for (const surface of SURFACES) {
      const entry = surfaceOf(s.config, surface)
      const mine = channels.map((ch, i) => ({ ch, i })).filter(x => x.ch.surface === surface)
      const relay = typeof entry['relay'] === 'string' ? entry['relay'] : '—'
      const user = surface === 'discord' && typeof entry['user'] === 'string' ? ` · user ${entry['user']}` : ''
      rowsOut.push(blank(), label(`${SURFACE_NAME[surface]} · relay ${relay}${user}`))
      if (surface === 'linear' && s.linear_key_command) {
        rowsOut.push(
          <Box height={1} width={W} overflowX="scroll">
            <Text>
              <Text color={LATER}>  Your Linear key goes in the keychain: run in your own terminal, never here, then (r)echeck: </Text>
              <Text bold>{s.linear_key_command}</Text>
            </Text>
          </Box>,
        )
      }
      const offered = (s.candidates ?? []).filter(k => k.surface === surface && !k.subscribed)
      if (!mine.length && !offered.length) rowsOut.push(plain('  no channels', { dim: true }))
      for (const { ch, i } of mine) {
        const k = checkOf(s.checks, ch)
        const repos = ch.surface === 'github' ? '' : ch.repos === undefined ? '  repos not set' : `  repos ${ch.repos.length ? ch.repos.join(', ') : 'none'}`
        rowsOut.push(
          <Box height={1} width={W} overflowX="scroll">
            <Text>
              <Text color={ACCENT}>{`${i + 1}`.padStart(3)} </Text>
              <Text bold>{ch.id}</Text>
              <Text dimColor>{repos}</Text>
              <Text> </Text>
              {k ? mark(k.ok) : <Text dimColor>·</Text>}
              <Text dimColor>{k ? ` ${k.name}${k.ok === null ? ': not checked' : ''}${k.fix ? ` · ${k.fix}` : ''}` : ''}</Text>
            </Text>
          </Box>,
        )
      }
      for (const k of offered) {
        rowsOut.push(
          <Box height={1} width={W} overflowX="scroll">
            <Button key={`cand:${k.surface}:${k.id}`} plain onPress={() => run(putInBox($, `add ${k.surface} ${k.id}`))}>
              <Text>
                <Text dimColor>{'    + '}</Text>
                <Text color={ACCENT}>add {k.surface} {k.id}</Text>
                <Text dimColor>{k.name && k.name !== k.id ? `  ${k.name}` : ''}</Text>
              </Text>
            </Button>
          </Box>,
        )
      }
    }
    const other = s.checks.filter(k => k.surface !== 'login' && !k.channel)
    if (other.length) {
      rowsOut.push(blank(), label('Checks'))
      for (const k of other) {
        rowsOut.push(
          <Box height={1} width={W} overflowX="scroll">
            <Text>
              {'  '}
              {mark(k.ok)}
              <Text> {k.name}</Text>
              <Text dimColor>{k.ok === null ? ': not checked' : ''}{k.fix ? ` · ${k.fix}` : ''}</Text>
            </Text>
          </Box>,
        )
      }
    }
    rowsOut.push(blank(), ...dimLines(SETUP_HELP, Math.min(cols, 140)))
    const body = take(rowsOut, B)
    return frame(<Box flexDirection="column">{body}</Box>, [], setupCmds, B, emptyBar, key => serviceKey($, key))
  }
  if (service.status !== 'open') return undefined

  // ── the summary ──────────────────────────────────────────────────────
  const pending = await read($, pendingAtom)
  if (!base) {
    const settled = fresh === 0 && deferred === 0 && waiting === 0
    const head =
      fresh > 0
        ? `${fresh} question${fresh === 1 ? '' : 's'} still unanswered`
        : deferred > 0
          ? `None unanswered. ${deferred} for later.`
          : waiting > 0
            ? `None unanswered. ${waiting} waiting for a reply.`
            : N === 0
              ? 'No questions yet. The next poll runs about a minute after the last.'
              : 'All caught up.'
    const handled = queue.map((one, i) => ({ one, i, a: answers[one.id] })).filter((x): x is { one: Question; i: number; a: Answer } => !!x.a)
    const W = Math.min(cols, 160)
    const whoWidth = Math.min(20, Math.max(...handled.map(x => x.one.asker.name.length), 0) + 2)
    const placeWidth = Math.min(36, Math.max(...handled.map(x => x.one.where.length), 0) + 2)
    const itemRow = ({ one, i, a }: { one: Question; i: number; a: Answer }): Row => {
      const who = cut(one.asker.name, whoWidth - 2).padEnd(whoWidth)
      const place = cut(one.where, placeWidth - 2).padEnd(placeWidth)
      const what =
        a.kind === 'defer'
          ? '│ for later'
          : a.pending
            ? `│ pending · ${a.pending} · ${a.text.replace(/\n/g, ' ')}`
            : a.kind === 'wont'
              ? `│ won't answer: nothing to answer`
              : a.auto
                ? a.kind === 'handled'
                  ? '│ handled for you'
                  : '│ answered for you'
                : `│ ${a.kind === 'handled' ? 'you chose · ' : ''}${one.branch && a.kind === 'answer' ? `logged · ${a.text}` : (a.post ?? a.text).replace(/\n/g, ' ')}`
      return (
        <Box height={1} width={W} overflowX="scroll">
          <Button key={`sum:${one.id}`} plain onPress={() => run(goTo($, i))}>
            <Text color={toneOf(a)}>{glyphOf(a)} </Text>
            <Text bold>{who}</Text>
            <Text dimColor>{place}</Text>
          </Button>
          <Text>{what}</Text>
        </Box>
      )
    }
    // Answers not yet relayed, from the core's pending list, each saying why it waits.
    const pendingRows: Row[] = pending.length
      ? [
          label(`${pending.length} ${pending.length === 1 ? 'answer' : 'answers'} not yet relayed`),
          ...pending.map(p => {
            const one = queue.find(x => x.id === p.question)
            return (
              <Box height={1} width={W} overflowX="scroll">
                <Button key={`pend:${p.question}`} plain onPress={() => run(one ? openQuestion($, one.id) : Promise.resolve(''))}>
                  <Text color={LATER}>◌ </Text>
                  <Text bold>{cut(one?.asker.name ?? p.question, whoWidth - 2).padEnd(whoWidth)}</Text>
                  <Text dimColor>{cut(one?.where ?? '', placeWidth - 2).padEnd(placeWidth)}</Text>
                </Button>
                <Text>
                  │ {p.text.replace(/\n/g, ' ')} <Text dimColor>· {p.why}</Text>
                </Text>
              </Box>
            )
          }),
        ]
      : []
    const top: Row[] = [
      plain(`${settled ? '✓  ' : ''}${head}`, { bold: true, ...(settled ? { color: DONE } : {}) }),
      plain(
        [
          `${relayed} of ${N} relayed this session`,
          ...(recorded ? [`${recorded} answered for you`] : []),
          ...(handledForYou ? [`${handledForYou} handled for you`] : []),
          ...(mine ? [`${mine} you answered for the inquisitor`] : []),
          ...(wont ? [`${wont} you won't answer`] : []),
          ...(waiting ? [`${waiting} back with their askers`] : []),
          ...(pendingCount ? [`${pendingCount} pending`] : []),
        ].join(' · '),
        { dim: true },
      ),
    ]
    const room2 = Math.max(0, B - top.length - 1 - (pendingRows.length ? pendingRows.length + 1 : 0))
    const list: Row[] =
      handled.length > room2
        ? [...handled.slice(0, Math.max(0, room2 - 1)).map(itemRow), plain(`and ${handled.length - Math.max(0, room2 - 1)} more: the dots above open each`, { dim: true })]
        : handled.map(itemRow)
    return frame(<Box flexDirection="column">{take(stack([top, list, pendingRows], 1), B)}</Box>, [], cmds)
  }

  // ── one question, as it now stands ───────────────────────────────────
  const rephrased = rephrasedAll[base.id]
  const showOriginal = !!originals[base.id]
  const q = c.q ?? base
  const answer = answers[base.id]
  const open = c.open
  const recordChosen = it.kind === 'command' && it.command.key === 'a' && !!q.record
  const isHuman = !q.options
  const turns = talks[q.id] ?? []
  const busy = thinking[q.id]
  const postsAs = q.branch ? 'on the questions branch as' : `on ${SURFACE_NAME[q.surface]} as`
  // The core's preview of what Enter would do now, when it is back for exactly this.
  const act = actOf(c, it)
  const pv: PreviewResponse | undefined = act && previewed?.key === actKey(act) ? previewed.res : undefined

  const STATE: Partial<Record<Answer['kind'], string>> = {
    defer: 'for later · ',
    wait: `waiting for ${q.asker.name} · `,
    wont: "won't answer · ",
    handled: 'handled by your choice · ',
  }
  const stateText = answer?.pending
    ? 'pending · '
    : answer?.kind === 'handled' && answer.auto
      ? 'handled for you · '
      : answer?.kind === 'recorded'
      ? answer.auto
        ? 'answered for you · '
        : q.branch
          ? 'logged · '
          : 'record posted · '
      : answer
        ? STATE[answer.kind]
        : undefined
  const state = stateText ? <Text {...(answer ? { color: toneOf(answer) } : {})}>{stateText}</Text> : ''
  const heard = others(c.replies).length
  const threadNote = q.branch ? '' : heard ? ` · ${heard} ${heard === 1 ? 'reply' : 'replies'}` : ' · no replies'
  const asked = q.asker.kind === 'agent' ? 'asks, an agent' : 'asks'
  const provenance = (lines: 0 | 1 | 2): Row[] => {
    if (lines === 0) return []
    const source = (
      <Box gap={2} flexShrink={0}>
        <Text bold>{q.branch ? 'Questions branch' : SURFACE_NAME[q.surface]}</Text>
        <Link href={q.link}>{q.where}</Link>
      </Box>
    )
    if (lines === 2) {
      return [
        <Box height={1} overflow="hidden" gap={2}>
          {source}
          <Text dimColor wrap="truncate-end">
            {state}
            {ago(q.age)}
            {threadNote}
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
            {ago(q.age)}
            {threadNote}
          </Text>
        </Text>
      </Box>,
    ]
  }
  const questionRows = (width: number): Row[] => md(q.text, width, `md:${q.id}`, { bold: true, dim: q.hasCategory && q.text !== base.text ? false : q.hasCategory })
  const changeMark: Row[] = rephrased
    ? [
        <Box height={1} overflow="hidden" gap={3}>
          <Text dimColor wrap="truncate-end">
            {showOriginal ? 'The original question, as asked' : '↻ Rephrased after your discussion'}
          </Text>
          <Button key="original" plain dimColor onPress={() => run(pressKey($, 'o'))}>
            {showOriginal ? 'show it as asked n(o)w' : 'show the (o)riginal'}
          </Button>
        </Box>,
      ]
    : []

  // The post in one run: where and as whom, then exactly what it says.
  const postRows = (post: string, width: number, max: number, verb = 'Post'): Row[] => {
    const where = `${verb} ${postsAs}`.toUpperCase()
    const head = `${where} ${relayOf(q)}: `
    const [prefix, body] = splitPost(post)
    const k = Math.min(Math.max(1, max), wrapLines(head + post, Math.max(10, width)).length)
    return tall(
      <Text maxLines={k}>
        <Text dimColor>{where}</Text>
        {` ${relayOf(q)}: `}
        <Text dimColor={prefix === PREFIX} bold={prefix !== PREFIX && prefix !== ''}>
          {prefix}
        </Text>
        {body}
      </Text>,
      k,
    )
  }
  // Where the answer will be recorded, from the core's preview, with the
  // warnings the person sees before Enter posts.
  const recordLines = (p: PreviewResponse | undefined, width: number): Row[] => {
    if (!p) return []
    const r = p.record
    const rows: Row[] = []
    if (r.place) {
      rows.push(
        <Box height={1} overflow="hidden" gap={3}>
          <Box flexShrink={1}>
            <Text wrap="truncate-end">
              <Text dimColor>RECORDED IN </Text>
              <Text bold>{r.place}</Text>
              <Text dimColor>{r.visibility ? ` · ${r.visibility}` : ''}</Text>
            </Text>
          </Box>
          {open && !q.branch ? (
            <Button key="elsewhere" plain dimColor onPress={() => run(pressKey($, 's'))}>
              record (s)omewhere else
            </Button>
          ) : null}
        </Box>,
      )
    } else if (r.not_recorded) rows.push(plain(`Not recorded: ${r.not_recorded}`, { dim: true }))
    if (r.more_visible_than) rows.push(...wrap(`⚠ ${r.place ?? 'The record'} is more visible than the thread (${r.more_visible_than}): recording it there shows the answer to more readers.`, width).map(l => plain(l, { color: LATER })))
    if (p.reaches_run) rows.push(...wrap(p.reaches_run, width).map(l => plain(l, { color: LATER })))
    for (const w of p.warnings) rows.push(...wrap(`⚠ ${w}`, width).map(l => plain(l, { color: LATER })))
    if (p.reword) rows.push(...wrap(p.reword, width).map(l => plain(l, { color: LATER })))
    return rows
  }

  // ── the replies since the question, and filter 1's record ─────────────
  const isNew = (r: Reply) => c.fresh !== undefined && c.replies.indexOf(r) >= c.fresh
  const viewButton = (key: string) => (
    <Button key={key} plain dimColor onPress={() => run(pressKey($, 'v'))}>
      (v)iew all
    </Button>
  )
  const replyHead = (r: Reply): Row => (
    <Text wrap="truncate-end">
      <Text bold {...(isNew(r) ? { color: ACCENT } : {})}>
        {r.who}
      </Text>
      <Text dimColor>
        {r.role === 'asker' ? ' · the asker' : ''} · {ago(r.age)}
      </Text>
      {isNew(r) ? <Text color={ACCENT}> · new</Text> : ''}
    </Text>
  )
  const replyBody = (r: Pick<Reply, 'text'>, width: number, max: number, key: string): Row[] => {
    const k = wrapLines(unmark(r.text), Math.max(10, width - 2)).length
    if (max >= 99 && k > B - 2) {
      return wrapLines(unmark(r.text), Math.max(10, width - 2)).map(line => (
        <Text wrap="truncate-end">
          <Text dimColor>│ </Text>
          {line}
        </Text>
      ))
    }
    if (k <= max) return quoted(md(r.text, Math.max(10, width - 2), key)[0]!, k, width)
    const [head, ...more] = quoted(<Text maxLines={Math.max(1, max)}>{unmark(r.text)}</Text>, Math.max(1, max), width)
    return [cutRow(head!), ...more]
  }
  const replyLine = (r: Reply, width: number): Row => {
    const row = (
      <Text wrap="truncate-end">
        <Text bold {...(isNew(r) ? { color: ACCENT } : {})}>
          {r.who}
        </Text>
        <Text dimColor>{r.role === 'asker' ? ' (the asker)' : ''}: </Text>
        {unmark(r.text)}
      </Text>
    )
    const said = `${r.who}${r.role === 'asker' ? ' (the asker)' : ''}: ${unmark(r.text)}`
    return said.length > width || said.includes('\n') ? cutRow(row) : row
  }
  const threadRows = (t: Trim, width: number): Row[] => {
    const list = others(c.replies)
    const n = list.length
    if (!n) return []
    const freshN = list.filter(isNew).length
    const words = `${n} ${n === 1 ? 'REPLY' : 'REPLIES'} SINCE IT WAS ASKED`
    const head = (more = ''): Row => (
      <Box height={1} overflow="hidden" gap={3}>
        <Box flexShrink={1}>
          <Text wrap="truncate-end">
            <Text color={ACCENT}>↩ </Text>
            <Text dimColor>{words}</Text>
            {freshN ? (
              <Text color={ACCENT} bold>
                {` · ${freshN} NEW`}
              </Text>
            ) : (
              ''
            )}
            <Text dimColor>{more}</Text>
          </Text>
        </Box>
        {viewButton('view')}
      </Box>
    )
    if (t.replies === 'count') return [cutRow(head(` · latest ${list[n - 1]!.who}`))]
    const last = list[n - 1]!
    if (t.replies === 'lines') {
      const shown = list.slice(-3)
      return [head(), ...(n > shown.length ? [cutRow(plain(`▸ ${n - shown.length} earlier`, { dim: true }))] : []), ...shown.map(r => replyLine(r, width))]
    }
    if (t.replies === 'latest') return [head(), ...list.slice(0, -1).map(r => replyLine(r, width)), replyHead(last), ...replyBody(last, width, 3, `md:${q.id}:reply:${c.replies.indexOf(last)}`)]
    return [head(), ...list.flatMap((r, i) => [...(i > 0 && t.optionGap ? [blank()] : []), replyHead(r), ...replyBody(r, width, 6, `md:${q.id}:reply:${c.replies.indexOf(r)}`)])]
  }
  const recordRows = (t: Trim, width: number, part: 'all' | 'record' | 'act'): Row[] => {
    const r = q.record
    if (!r) return []
    const head = (
      <Box height={1} overflow="hidden" gap={3}>
        <Box flexShrink={1}>
          <Text wrap="truncate-end">
            <Text color={DONE}>{GLYPH.recorded} </Text>
            <Text dimColor>{part === 'act' ? 'RECORDED ANSWER · FILTER 1 · SHOWN WITH THE QUESTION' : 'RECORDED ANSWER · FILTER 1'}</Text>
          </Text>
        </Box>
        {part === 'act' ? null : viewButton('view:record')}
      </Box>
    )
    if (part !== 'act' && (t.record === 'head' || t.record === 'line')) cutRow(head)
    const record: Row[] =
      t.record === 'head'
        ? []
        : [
            <Text wrap="truncate-end">
              <Link href={r.url}>{r.title}</Link>
            </Text>,
            ...(t.record === 'line' ? [] : replyBody({ text: r.excerpt }, width, t.record === 'full' ? 3 : 1, `md:${q.id}:record`)),
          ]
    const why =
      r.why === 'private'
        ? 'Not posted by itself: the record is more private than this thread. (a)gree posts its link, which shows the record exists.'
        : 'Not posted by itself: a questions-branch file has no thread. (a)gree records it as the answer, and nothing posts.'
    const whyRows = t.record === 'head' ? [] : t.record === 'line' ? [plain(why, { dim: true })] : dimLines(why, width)
    const agree: Row[] =
      open && answer?.kind !== 'recorded'
        ? [
            <Box height={1} overflow="hidden">
              <Text color={ACCENT}>{recordChosen ? '▌ ' : '  '}</Text>
              <Button key="record" plain onPress={() => run(putInBox($, 'a'))}>
                <Text color={ACCENT}>(a)</Text>
                <Text bold={recordChosen} {...(recordChosen ? { color: ACCENT } : {})} dimColor={!recordChosen}>
                  gree: {q.branch ? 'record the recorded answer' : 'post the recorded answer'}
                </Text>
              </Button>
            </Box>,
          ]
        : []
    if (t.record === 'head' && part !== 'record' && agree.length) {
      return [
        cutRow(
          <Box height={1} overflow="hidden" gap={2}>
            <Text color={DONE}>{GLYPH.recorded}</Text>
            <Text dimColor>RECORDED ANSWER</Text>
            <Button key="record" plain onPress={() => run(putInBox($, 'a'))}>
              <Text color={ACCENT}>(a)</Text>
              <Text bold={recordChosen} {...(recordChosen ? { color: ACCENT } : {})} dimColor={!recordChosen}>
                gree: {q.branch ? 'record it' : 'post it'}
              </Text>
            </Button>
            {viewButton('view:record')}
          </Box>,
        ),
      ]
    }
    if (part === 'record') return [head, ...record]
    if (part === 'act') return [head, ...whyRows, ...agree]
    return [head, ...record, ...whyRows, ...agree]
  }
  const evidence = (t: Trim, width: number, g: (gap: Gap) => number, side: 'left' | 'right'): Row[] => {
    const isOpen = open && !c.posted
    if (side === 'left') return recordRows(t, width, isWide || !isOpen ? 'record' : 'all')
    return stack([isWide && isOpen ? recordRows(t, width, 'act') : [], threadRows(t, width)], [g('thread')])
  }

  const questionColumn = (t: Trim, width: number, g: (gap: Gap) => number): Row[] => {
    const related: Row[] =
      q.related && t.related
        ? [
            <Text wrap="truncate-end">
              <Text dimColor>Related </Text>
              <Link href={q.related}>{q.related}</Link>
            </Text>,
          ]
        : []
    const concerns: Row[] = [
      ...(q.concerns && t.related && !q.branch ? [plain(`Concerns ${q.concerns}`, { dim: true })] : []),
      ...(q.suggested && q.asker.kind === 'agent' && c.open ? [plain(`Claude suggests filter ${q.suggested.filter}, ${FILTERS[q.suggested.filter].name}: ${q.suggested.why}`, { dim: true })] : []),
    ]
    return stack([provenance(t.provenance), [...changeMark, ...questionRows(width)], evidence(t, width, g, 'left'), [...concerns, ...related]], [g('question'), g('thread'), g('related')])
  }

  const answerColumn = (t: Trim, width: number, g: (gap: Gap) => number): Row[] => {
    const d = c.declining
    if (c.picking) return pickColumn(t, width)
    if (d?.stage === 'reason') return reasonsColumn(t, width)
    if (d?.stage === 'filter') return filtersColumn(t, width)
    if (d) return inquisitorColumn(d, t, width, g)
    const seen = evidence(t, width, g, 'right')
    if (answer?.kind === 'wont') return stack([seen, wontColumn(t, width)], [g('thread')])
    if (answer && answer.kind !== 'defer') return stack([seen, postColumn(answer, t, width)], [g('thread')])
    return stack([seen, chooseColumn(t, width, g)], [g('thread'), g('related')])
  }

  // A post in the thread: the person's, or the service's own; while it is edited, the new version under it.
  const postColumn = (a: Answer, t: Trim, width: number): Row[] => {
    const words = a.pending
      ? `Pending ${postsAs}`
      : a.auto
        ? `${a.kind === 'handled' ? 'Handled' : 'Answered'} for you ${postsAs}`
        : a.kind === 'wait'
          ? `Waiting for ${q.asker.name}. Asked ${postsAs}`
          : a.kind === 'handled'
            ? `Handled by your choice ${postsAs}`
            : a.kind === 'recorded'
              ? `${q.branch ? 'Recorded' : 'Posted'} the recorded answer ${postsAs}`
              : q.branch
                ? `Logged ${postsAs}`
                : `Relayed ${postsAs}`
    const headRow: Row = (
      <Box height={1} overflow="hidden" gap={2}>
        <Box flexShrink={1}>
          <Text wrap="truncate-end">
            <Text color={toneOf(a)}>{a.kind === 'answer' && !a.pending ? '✓' : glyphOf(a)} </Text>
            <Text dimColor>{words.toUpperCase()}</Text> {relayOf(q)}
          </Text>
        </Box>
        {a.url ? <Link href={a.url}>{a.edited ? 'edited · view' : 'view'}</Link> : null}
      </Box>
    )
    const posted = a.post !== undefined ? bubble(a.post, c.editing ? RULE : toneOf(a), width, t.bubble) : a.text ? quoted(plain(a.text), 1, width, toneOf(a)) : []
    if (c.editing) {
      return [
        headRow,
        ...posted,
        ...(it.kind === 'edit' ? [...postRows(pv?.post ?? `${splitPost(a.post ?? '')[0]}${it.text}`, width, t.bubble, 'Edit'), ...recordLines(pv, width)] : [plain('Editing: change it in the prompt box, then ⏎ updates the post.', { dim: true })]),
      ]
    }
    const why =
      a.pending
        ? `Not relayed yet: ${a.pending}. It is relayed once its channel works again.`
        : a.auto
          ? 'The service posted it by itself: filter 1 found a recorded answer with authority, or the inquisitor should have stopped it.'
          : a.kind === 'handled'
            ? `A miss is logged against filter ${a.filter ?? 1} (${FILTERS[a.filter ?? 1].name})${a.text ? ', with what you said:' : '.'}`
            : a.kind === 'recorded' && q.branch
              ? 'Nothing was posted: a new log file on the questions branch holds it as the answer.'
              : q.branch && a.kind === 'answer'
                ? 'Nothing was posted: a new log file on the questions branch holds your answer, as you wrote it.'
                : ''
    const whyRows = !why || t.effects === 'none' ? [] : t.effects === 'line' ? [plain(why, { dim: true })] : dimLines(why, width)
    const said = a.kind === 'handled' && a.text && t.effects !== 'none' ? wrap(a.text, width - 2).slice(0, Math.max(1, t.bubble)).map(line => plain(`│ ${line}`)) : []
    return [headRow, ...posted, ...whyRows, ...said]
  }

  // Another place for the record: the places the code lists, by number, or one typed.
  const pickColumn = (t: Trim, width: number): Row[] => {
    const chosen = it.kind === 'pick' ? it.place : c.place
    const rows = knownPlaces.flatMap((p, i) => {
      const isChosen = chosen === p
      return [
        ...(i > 0 && t.optionGap && knownPlaces.length < 6 ? [blank()] : []),
        <Box height={1} overflow="hidden">
          <Text color={ACCENT}>{isChosen ? '▌ ' : '  '}</Text>
          <Button key={`place:${i}`} plain onPress={() => run(putInBox($, String(i + 1)))}>
            <Text color={ACCENT}>{i + 1}</Text>
            <Text dimColor>: </Text>
            <Text bold {...(isChosen ? { color: ACCENT } : {})}>
              {p}
            </Text>
          </Button>
        </Box>,
      ]
    })
    return [
      <Text wrap="truncate-end">
        <Text color={ACCENT}>◎ </Text>
        <Text dimColor>WHERE SHOULD THE ANSWER BE RECORDED?</Text>
      </Text>,
      ...rows,
      ...dimLines('Or type a repository as owner/name. The next preview shows the record there, and warns if it is more visible than the thread.', width),
    ]
  }

  // Declining: the reasons, chosen by number in the prompt box; reason 2 only on an agent's question.
  const reasonsColumn = (t: Trim, width: number): Row[] => {
    const chosen = it.kind === 'reason' ? it.reason : undefined
    const offered = isHuman || q.asker.kind !== 'agent' ? ([1] as const) : ([1, 2] as const)
    const reasons = offered.flatMap(r => {
      const isChosen = chosen === r
      const mark = <Text color={ACCENT}>{isChosen ? '▌ ' : '  '}</Text>
      const effect = t.effects === 'none' ? [] : t.effects === 'line' ? [cut(`→ ${REASONS[r].will}`, width - 5)] : wrap(REASONS[r].will, width - 7).map((line, j) => (j ? '  ' : '→ ') + line)
      return [
        ...(r > 1 && t.optionGap ? [blank()] : []),
        <Box height={1} overflow="hidden">
          {mark}
          <Button key={`why:${r}`} plain onPress={() => run(putInBox($, String(r)))}>
            <Text color={ACCENT}>{r}</Text>
            <Text dimColor>: </Text>
            <Text bold {...(isChosen ? { color: ACCENT } : {})}>
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
  const wontColumn = (t: Trim, width: number): Row[] => {
    const did = t.effects === 'none' ? [] : t.effects === 'line' ? [plain(CLOSED.did, { dim: true })] : dimLines(CLOSED.did, width)
    return [
      <Text wrap="truncate-end">
        <Text color={TONE.wont}>{GLYPH.wont} </Text>
        <Text dimColor>{"WON'T ANSWER · "}</Text>
        <Text bold>Nothing to answer</Text>
        <Text dimColor> · nothing was posted</Text>
      </Text>,
      ...did,
    ]
  }
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
            <Text bold {...(isChosen ? { color: ACCENT } : {})}>
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
    const hint = q.suggested
      ? [
          <Text wrap="truncate-end">
            <Text dimColor>Claude suggests </Text>
            <Text color={ACCENT}>{q.suggested.filter}</Text>
            <Text dimColor>: {cut(q.suggested.why, Math.max(10, width - 20))}</Text>
          </Text>,
        ]
      : []
    return [
      <Text wrap="truncate-end">
        <Text color={ACCENT}>{GLYPH.handled} </Text>
        <Text dimColor>{'WHICH FILTER SHOULD HAVE STOPPED IT? · NOTHING IS POSTED YET'}</Text>
      </Text>,
      ...hint,
      ...filters,
    ]
  }
  const inquisitorColumn = (d: Extract<Declining, { stage: 'place' | 'post' }>, t: Trim, width: number, g: (gap: Gap) => number): Row[] => {
    const n: Filter = d.stage === 'place' ? 1 : d.filter
    const head: Row = (
      <Text wrap="truncate-end">
        <Text color={ACCENT}>{GLYPH.handled} </Text>
        <Text dimColor>{'ANSWER FOR THE INQUISITOR · '}</Text>
        <Text bold>
          Filter {n}, {FILTERS[n].name}
        </Text>
      </Text>
    )
    const prefixOf = (f: Filter) => (f === 1 ? RECORDED : INQUISITOR)
    if (d.stage === 'place') {
      const place = it.kind === 'place' ? it.text : ''
      const talkKey = q.options ? '(t)alk to Claude' : '(h)elp me answer'
      return stack(
        [
          [head, ...dimLines(`Where is the answer recorded? Type or paste its URL in the prompt box. Or ${talkKey}: Claude can find it and fill it in.`, width)],
          place ? postRows(prefixOf(1) + filterReply(1, place), width, t.bubble) : [...postRows(`${RECORDED}…`, width, 1), ...dimLines("Without a place it can't post as filter 1.", width)],
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
        : dimLines('A note for the miss, if you like: type it in the prompt box. Or (p)ost it as it is. ⏎ posts.', width)
    const post = pv ? pv.post : prefixOf(n) + filterReply(n, d.place)
    const after = t.effects === 'full' ? dimLines(`A miss is logged against filter ${n}, with your note as what was said.`, width) : []
    return stack([[head], post === null ? dimLines('Nothing posts: this question has no thread, or its text holds a category.', width) : postRows(post, width, t.bubble), recordLines(pv, width), note, after], [g('choices'), 0, g('preview'), g('related')])
  }

  const chooseColumn = (t: Trim, width: number, g: (gap: Gap) => number): Row[] => {
    const options: Row[] = (q.options ?? []).flatMap((o, i) => {
      const isChosen = it.kind === 'option' && it.index === i
      const mark = <Text color={ACCENT}>{isChosen ? '▌ ' : '  '}</Text>
      const head = (
        <Box height={1} overflow="hidden">
          {mark}
          <Button key={`opt:${q.id}:${i}`} plain onPress={() => run(putInBox($, String(i + 1)))}>
            <Text color={ACCENT}>{i + 1}</Text>
            <Text dimColor>: </Text>
            <Text bold {...(isChosen ? { color: ACCENT } : {})}>
              {cut(o.label, width - 5 - (i === 0 ? 15 : 0))}
            </Text>
          </Button>
          {i === 0 ? <Text color={ACCENT}>{'  ★ recommended'}</Text> : null}
        </Box>
      )
      const effect = !o.effect || t.effects === 'none' ? [] : t.effects === 'line' ? [cut(`→ ${o.effect}`, width - 5)] : wrap(o.effect, width - 7).map((line, j) => (j ? '  ' : '→ ') + line)
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
    const isWriting = it.kind === 'relay'
    const ownWords = (
      <Text wrap="truncate-end">
        <Text color={ACCENT}>{isWriting ? '▌ ' : '  '}</Text>
        <Text bold={isWriting} {...(isWriting ? { color: ACCENT } : {})} dimColor={!isWriting}>
          {isHuman ? `Reply to ${q.asker.name}: type it in the prompt box` : 'Or type your own answer in the prompt box'}
        </Text>
      </Text>
    )
    const choose: Row[] = isHuman ? [ownWords] : [...options, ...(t.ownWords || isWriting ? [...(t.optionGap ? [blank()] : []), ownWords] : [])]
    // What will post, exactly: the core's preview once it is back, else the band's own reading of it.
    const message = it.kind === 'option' || it.kind === 'relay' ? it.text : undefined
    const local = message !== undefined ? (q.branch ? message : PREFIX + message) : recordChosen && q.record ? `${RECORDED}see the record below.\nRecorded in: ${q.record.url}` : undefined
    const shown = pv ? pv.post : local
    const preview: Row[] =
      shown === undefined
        ? []
        : shown === null
          ? [...dimLines(q.branch ? 'Nothing posts: a new log file on the questions branch records it.' : 'Nothing posts.', width), ...recordLines(pv, width)]
          : [...postRows(shown, width, t.preview === 'line' ? 1 : t.bubble, q.branch ? 'Log' : 'Post'), ...recordLines(pv, width)]
    const heading = q.record ? (t.related ? [label('Or answer it yourself')] : []) : t.label && !isHuman ? [label('Choose an answer')] : []
    return stack([heading, choose, preview], [0, g('preview')])
  }

  // ── everything since the question, in full ───────────────────────────
  if (c.viewing !== undefined && !isTalking) {
    const width = isWide ? Math.min(LW, RW) : cols
    const r = q.record
    const list = others(c.replies)
    const rows: Row[] = [
      ...questionRows(width),
      ...(r
        ? [
            blank(),
            <Text wrap="truncate-end">
              <Text color={DONE}>{GLYPH.recorded} </Text>
              <Text dimColor>RECORDED ANSWER · THE INQUISITOR'S FILTER 1</Text>
            </Text>,
            <Text wrap="truncate-end">
              <Link href={r.url}>{r.title}</Link>
            </Text>,
            ...replyBody({ text: r.excerpt }, width, 99, `md:${q.id}:record`),
          ]
        : []),
      ...(list.length
        ? [
            blank(),
            <Text wrap="truncate-end">
              <Text color={ACCENT}>↩ </Text>
              <Text dimColor>{`${list.length} ${list.length === 1 ? 'REPLY' : 'REPLIES'} SINCE IT WAS ASKED, OLDEST FIRST`}</Text>
            </Text>,
            ...list.flatMap((one, i) => [...(i > 0 ? [blank()] : []), replyHead(one), ...replyBody(one, width, 99, `md:${q.id}:reply:${c.replies.indexOf(one)}`)]),
          ]
        : []),
    ]
    const size = B - 1
    const chunks: Row[][] = []
    let chunk: Row[] = []
    const isBlank = (row: Row | undefined) => typeof row === 'object' && row !== null && blanks.has(row)
    for (let i = 0; i < rows.length; ) {
      const row = rows[i]!
      if (!chunk.length && isBlank(row)) {
        i++
        continue
      }
      const k = (typeof row === 'object' && row !== null ? heads.get(row)?.k : undefined) ?? 1
      if (chunk.length && chunk.length + k > size) {
        chunks.push(chunk)
        chunk = []
        continue
      }
      chunk.push(...take(rows.slice(i, i + k), size - chunk.length))
      i += k
      if (chunk.length >= size) {
        chunks.push(chunk)
        chunk = []
      }
    }
    if (chunk.length) chunks.push(chunk)
    const per = isWide ? 2 : 1
    const pages = Math.max(1, Math.ceil(chunks.length / per))
    const page = c.viewing % pages
    const head: Row = (
      <Text wrap="truncate-end">
        <Text dimColor>{`${pages > 1 && !isWide ? `PAGE ${page + 1} OF ${pages} · ` : ''}EVERYTHING SINCE THE QUESTION · `}</Text>
        <Link href={q.link}>{q.where}</Link>
        <Text dimColor>
          {' '}
          · {q.asker.name} asked {ago(q.age)}
        </Text>
      </Text>
    )
    const left = [head, ...(chunks[page * per] ?? [])]
    const right = [pages > 1 ? plain(`page ${page + 1} of ${pages} · (m)ore`, { dim: true }) : blank(), ...(chunks[page * per + 1] ?? [])]
    const shownCmds = cmds.filter(cmd => cmd.key !== 'm' || pages > 1)
    const body = isWide ? columns(left, right, LW, RW, false) : <Box flexDirection="column">{left}</Box>
    return frame(body, [], shownCmds, B, bar, undefined, it.kind === 'refused' ? it.why : undefined)
  }

  if (!isTalking) {
    const options = q.options ?? []
    const hints: [string, string][] =
      c.declining?.stage === 'reason'
        ? q.asker.kind === 'agent'
          ? [['1–2', 'choose why']]
          : [['1', 'nothing to answer']]
        : c.declining?.stage === 'filter'
          ? [['1–4', 'choose the filter']]
          : c.picking
            ? knownPlaces.length
              ? [[`1–${knownPlaces.length}`, 'choose the place']]
              : []
            : c.declining || !open || c.editing || isHuman
              ? []
              : [[`1–${options.length}`, 'choose']]
    const one = isWide ? [] : fit((t, g) => stack([questionColumn(t, cols, g), answerColumn(t, cols, g)], g('choices')), B)
    const left = isWide ? fit((t, g) => questionColumn(t, LW, g), B) : []
    const right = isWide ? fit((t, g) => answerColumn(t, RW, g), B) : []
    const body = isWide ? columns(left, right, LW, RW) : <Box flexDirection="column">{[...lift(one.length), ...one]}</Box>
    const isCut = hasCut([...one, ...left, ...right])
    return frame(
      body,
      hints,
      cmds.map(cmd => (cmd.key === 'v' && isCut ? { key: cmd.key, what: cmd.what } : cmd)),
      B,
      bar,
      undefined,
      it.kind === 'refused' ? it.why : undefined,
    )
  }

  // ── talking to Claude: this question only, the queue waits ───────────
  const composing = !!askingAll[q.id]
  const askText = it.kind === 'ask' ? it.text : ''
  const pinned = (width: number, budget: number): Row[] => {
    const tight = stack([provenance(1), questionRows(width)], 0)
    if (tight.length <= budget) return tight
    const roomRows = Math.max(1, budget - 1)
    return [
      ...provenance(1),
      ...tall(
        <Text bold maxLines={roomRows}>
          {unmark(q.text)}
        </Text>,
        roomRows,
      ),
    ]
  }
  const compose = (width: number): Row[] => [
    label(`Ask ${q.asker.name}, in the thread`),
    ...bubble(askText ? (pv?.post ?? `User asks: ${askText}`) : undefined, askText ? ACCENT : RULE, width, Math.max(2, B - 5)),
    ...dimLines(
      busy === 'draft'
        ? 'Drafting a question into the prompt box…'
        : askText
          ? `Posts ${postsAs} ${relayOf(q)}. Enter sends exactly this; the question waits for the reply, the queue moves on.`
          : `Type your question for ${q.asker.name} in the prompt box.`,
      width,
    ),
  ]
  const talkState = (width: number): Row[] => {
    const head: Row = (
      <Text wrap="truncate-end">
        <Text color={ACCENT}>◇ </Text>
        <Text dimColor>TALKING TO CLAUDE</Text>
        <Text dimColor>
          {c.editing ? ' · for your edit, in the conversation above' : c.declining ? ' · about where the answer is recorded, in the conversation above' : ' · in the conversation above'}
        </Text>
      </Text>
    )
    const spaced = (rows: Row[]): Row[] => [blank(), head, blank(), ...rows, blank()]
    if (composing) return spaced(compose(width))
    const said = turns.some(turn => turn.who === 'you')
    const last = turns[turns.length - 1]
    const stateRows: Row[] =
      busy === 'reply'
        ? [plain('◌ Claude is answering above…', { color: ACCENT })]
        : busy === 'rephrase'
          ? [plain('◌ Rephrasing the question from your discussion…', { color: ACCENT })]
          : last?.who === 'error'
            ? wrap(last.text, width).map(line => plain(line, { color: LATER }))
            : said
              ? []
              : dimLines(
                  c.declining
                    ? 'Ask Claude where the answer is recorded, or to find it and fill in its URL for you to check. It gets the question with your message and may read files first. Nothing posts until you ⏎ on the reply.'
                    : 'Ask anything about the question, or tell Claude what to say and it drafts your reply for you to check. It gets the question with your message and may read and search files first; its reply shows above. The rest of the queue waits.',
                  width,
                )
    return spaced(stateRows)
  }
  if (isWide) {
    const right = talkState(RW)
    const left = pinned(LW, Math.max(B, right.length))
    const rows = Math.min(B, Math.max(left.length, right.length))
    return frame(columns(take(left, rows), take(right, rows), LW, RW, false, rows), [], cmds, rows, bar, undefined, it.kind === 'refused' ? it.why : undefined)
  }
  const rows1 = take([...pinned(cols, 3), ...talkState(cols)], B)
  return frame(<Box flexDirection="column">{rows1}</Box>, [], cmds, rows1.length, bar, undefined, it.kind === 'refused' ? it.why : undefined)
}

/** A row the service placed in the transcript: what was done, and what was posted. */
export async function placed($: EngineInterface, rowId: string, ui: ReturnType<EngineInterface['ui']['resolve']>): Promise<RenderElement | undefined> {
  const row = (await read($, rowsAtom))[rowId]
  const one = row && (await queueOf($)).find(x => x.id === row.id)
  if (!row || !one) return undefined
  const isPosting = !!(await read($, postingAtom))[rowId]
  const { Box, Text, Link, Button } = ui
  const surface = SURFACE_NAME[one.surface]
  const HEAD: Record<PlacedRow['verb'], [string, string, string]> = {
    answered: [GLYPH.answer, DONE, `Answered ${one.where}`],
    logged: [GLYPH.answer, DONE, `Logged on ${one.branch?.repo ?? one.where}'s questions branch`],
    asked: [GLYPH.wait, ACCENT, `Asked ${one.asker.name} on ${one.where}`],
    wont: [GLYPH.wont, RULE, `Won't answer ${one.where}`],
    recorded: [GLYPH.recorded, DONE, one.branch ? `Recorded the recorded answer for ${one.where}` : `Posted the recorded answer on ${one.where}`],
    inquisitor: [GLYPH.handled, DONE, `Answered for the inquisitor on ${one.where}`],
    edited: ['✎', DONE, `Edited your post on ${one.where}`],
    pending: ['◌', LATER, `Kept your answer to ${one.where} pending`],
  }
  const [glyph, color, did] = HEAD[row.verb]
  const whose = `(${one.asker.name}'s question: ${cut(unmark(one.text), 36)})`
  const said = row.verb === 'wont' ? 'nothing posted' : row.text.replace(/\n/g, ' ')
  return (
    <Box flexDirection="row" gap={2}>
      <Box flexShrink={1}>
        <Text wrap="truncate-end">
          <Text color={isPosting ? RULE : color}>{isPosting ? '◌' : glyph} </Text>
          <Text bold>{did}</Text>
          <Text dimColor> {whose}</Text>
          {said ? <Text> — {said}</Text> : ''}
        </Text>
      </Box>
      {row.posts ? (
        isPosting ? (
          <Box flexShrink={0}>
            <Text dimColor>posting to {surface}…</Text>
          </Box>
        ) : (
          <Box flexShrink={0} gap={2}>
            <Button key={`view:${rowId}`} plain onPress={() => void openQuestion($, one.id).catch(() => undefined)}>
              <Text color={ACCENT}>view</Text>
            </Button>
            {row.url ? <Link href={row.url}>{`on ${surface}`}</Link> : null}
          </Box>
        )
      ) : null}
    </Box>
  )
}

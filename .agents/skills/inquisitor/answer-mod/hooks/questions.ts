// A question as the band shows it, read from the core's QuestionView, and the
// fixed words the band uses. Pure functions only: no `$`.
import type { Filter, Revision } from '../types'
import type { QuestionView, Reply as CoreReply, Surface } from './core-protocol'

export type Option = { label: string; effect: string }

/** A reply in a question's thread since the question: someone's, the asker's, or a relay post. */
export type Reply = { who: string; role?: 'asker' | 'relay'; age: string; text: string; url: string }

/** Filter 1's recorded answer, shown beside the question rather than posted by itself. */
export type Record_ = {
  /** `branch`: the question is a questions-branch file, with no thread; `private`: the record is more private than the thread. */
  why: 'private' | 'branch'
  url: string
  /** The record's place, as a reader names it: the file the URL names. */
  title: string
  /** What it says, as filter 1's hit quotes it. */
  excerpt: string
}

export type Question = {
  id: string
  surface: Surface
  /** Where it was asked, as a reader names the place. */
  where: string
  link: string
  asker: { name: string; kind: 'agent' | 'human' }
  age: string
  /** The question's words, or a placeholder when the core gives none because the question has a category. */
  text: string
  hasCategory: boolean
  /** An agent's question: the answers its numbered list offers, the recommended one first. */
  options?: Option[]
  related?: string
  record?: Record_
  /** A questions-branch file: it has no thread; its answer is a new log file there. */
  branch?: { repo: string }
  /** The repository an agent's concerns line names. */
  concerns?: string
  replies: Reply[]
  /** The bot account that posts the person's answers here; absent for a questions-branch file. */
  relay?: string
  /** The model's judgement of an agent's question: the filter, 2 to 4, that should have stopped it, and why. */
  suggested?: { filter: 2 | 3 | 4; why: string }
}

/** The tool the session's model calls to put a drafted reply in the prompt box. */
export const PROPOSE_TOOL = 'mcp__inquisitor-answer-mod__propose_reply'
/** The tool the model judges a message with. */
export const VERDICT_TOOL = 'mcp__inquisitor-answer-mod__record_verdict'

export const SURFACE_NAME: Record<Surface, string> = { github: 'GitHub', linear: 'Linear', discord: 'Discord' }

/** The four prefixes only the answer service's posts start with. */
export const PREFIX = 'User says: '
export const ASKS = 'User asks: '
export const RECORDED = 'Recorded answer: '
export const INQUISITOR = 'Inquisitor: '
export const RESERVED = [PREFIX, ASKS, RECORDED, INQUISITOR]

/** The inquisitor's filters, as the band names them. */
export const FILTERS: Record<Filter, { name: string; action: string }> = {
  1: { name: 'already answered', action: 'here is the recorded answer' },
  2: { name: 'can wait', action: 'carry on without it, and list it as not done' },
  3: { name: 'only one option has merit', action: 'take the option that has merit' },
  4: { name: 'cheap to reverse', action: "pick one, it's cheap to switch" },
}

/** Why the person declines, as they choose it, and what follows. */
export const REASONS: Record<1 | 2, { label: string; will: string }> = {
  1: {
    label: "Nothing to answer: the conversation is over, or it isn't a question",
    will: 'Nothing is posted and no miss logged. Only this question closes; later messages in its thread are new questions.',
  },
  2: {
    label: 'The inquisitor should have handled it',
    will: "Choose the filter that should have stopped it, and the reply that filter would have given is posted for the inquisitor. A miss is logged against that filter.",
  },
}

/** A decline with nothing posted: what happened, and what reopening does. */
export const CLOSED = {
  did: 'Recorded on this machine: the question is closed here, and later messages in its thread are new questions.',
  undo: 'it is back in your queue',
}

/** The line the person's filter 2 to 4 reply ends with. */
export const CHOSE = 'The person chose this filter.'

/** What a filter's reply says after its prefix, as the band shows it before the core's preview is back. */
export function filterReply(n: Filter, place = ''): string {
  return n === 1 ? `see the record below.\nRecorded in: ${place}` : `Filter ${n} (${FILTERS[n].name}): ${FILTERS[n].action}.\n${CHOSE}`
}

/** `text` cut to `width` cells, an ellipsis marking the cut. */
export function cut(text: string, width: number): string {
  if (text.length <= width) return text
  return width <= 1 ? '…' : `${text.slice(0, width - 1).trimEnd()}…`
}

/** Breaks `text` into lines of at most `width` cells, at spaces where it can. */
export function wrap(text: string, width: number): string[] {
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

/** `wrap`, keeping the text's own line breaks. */
export const wrapLines = (text: string, width: number): string[] => text.split('\n').flatMap(line => wrap(line, width))

/** Markdown as the terminal shows it, near enough to count its rows. */
export const unmark = (text: string): string => text.replace(/!?\[([^\]]*)\]\([^)\s]*\)/g, '$1').replace(/\*\*|__|`/g, '')

/** A question in bold, as the band draws it: each plain paragraph wrapped in bold marks. */
export const emphasised = (text: string): string =>
  text
    .split(/\n{2,}/)
    .map(para => (/\*\*|__|^\s*([-*>#]|\d+\.)\s/.test(para) ? para : `**${para.trim()}**`))
    .join('\n\n')

/** "12m ago", or "just now". */
export const ago = (age: string) => (age === 'just now' ? age : `${age} ago`)

/** How long ago `iso` was, from `now`, in the band's short words. */
export function ageOf(iso: string, now: number): string {
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return 'a while'
  const s = Math.max(0, Math.floor((now - then) / 1000))
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86_400) return `${Math.floor(s / 3600)}h`
  return `${Math.floor(s / 86_400)}d`
}

/** The place a URL names, as a reader names it: `o/r #12`, `ENG-442`, a Discord channel. */
export function whereOf(url: string, surface: Surface): string {
  let u: URL
  try {
    u = new URL(url)
  } catch {
    return url
  }
  const parts = u.pathname.split('/').filter(Boolean)
  if (surface === 'github') {
    const [owner, repo, kind, num] = parts
    if (owner && repo && (kind === 'pull' || kind === 'issues' || kind === 'discussions') && num) return `${owner}/${repo} #${num}`
    if (owner && repo && kind === 'blob') return `${owner}/${repo} ${parts.slice(4).join('/')}`
    if (owner && repo) return `${owner}/${repo}`
  }
  if (surface === 'linear') {
    const i = parts.indexOf('issue')
    const key = i >= 0 ? parts[i + 1] : undefined
    if (key) return key
  }
  if (surface === 'discord' && parts[0] === 'channels' && parts[2]) return `channel ${parts[2]}`
  return u.host + u.pathname
}

/** The file a record's URL names, for its heading. */
function titleOf(url: string): string {
  try {
    const parts = new URL(url).pathname.split('/').filter(Boolean)
    return parts.length > 4 && parts[2] === 'blob' ? `${parts[0]}/${parts[1]} ${parts.slice(4).join('/')}` : url
  } catch {
    return url
  }
}

/**
 * The answers an agent's question offers: a numbered list of two or more
 * items, `1.` to `n.`, each `label: effect` or `label — effect`. A question
 * without one has no options, and is answered in the person's own words.
 */
export function optionsOf(text: string): Option[] | undefined {
  const items: Option[] = []
  for (const line of text.split('\n')) {
    const m = /^\s*(\d+)[.)]\s+(.+?)\s*$/.exec(line)
    if (!m) continue
    if (Number(m[1]) !== items.length + 1) return undefined
    const body = m[2]!
    const split = /\s+[—–]\s+|:\s+/.exec(body)
    items.push(split ? { label: body.slice(0, split.index).trim(), effect: body.slice(split.index + split[0].length).trim() } : { label: body, effect: '' })
  }
  return items.length >= 2 ? items : undefined
}

/** Whether a reply is a relay post: it starts with a reserved prefix. */
export const isRelayPost = (text: string) => RESERVED.some(p => text.startsWith(p))

/** The band's question, read from the core's view at time `now`. */
export function questionOf(v: QuestionView, now: number): Question {
  const isAgent = v.asker !== 'person'
  const text = v.text ?? `The question's words are not shown: its text holds a secret, a vulnerability or something personal. Read it where it was asked.`
  const reply = (r: CoreReply): Reply => ({
    who: r.author,
    ...(isRelayPost(r.text) ? { role: 'relay' as const } : r.author === v.asked_by ? { role: 'asker' as const } : {}),
    age: ageOf(r.at, now),
    text: r.text,
    url: r.url,
  })
  const options = isAgent && v.text ? optionsOf(v.text) : undefined
  const branch = v.asker === 'questions-branch' ? { repo: v.concerns ?? whereOf(v.url, 'github').split(' ')[0]! } : undefined
  return {
    id: v.id,
    surface: v.surface,
    where: whereOf(v.url, v.surface),
    link: v.url,
    asker: { name: v.asked_by, kind: isAgent ? 'agent' : 'human' },
    age: ageOf(v.asked_at, now),
    text,
    hasCategory: v.has_category,
    ...(options ? { options } : {}),
    ...(v.related ? { related: v.related } : {}),
    ...(v.recorded
      ? { record: { why: branch ? ('branch' as const) : ('private' as const), url: v.recorded.recorded_in, title: titleOf(v.recorded.recorded_in), excerpt: v.recorded.quote } }
      : {}),
    ...(branch ? { branch } : {}),
    ...(v.concerns ? { concerns: v.concerns } : {}),
    replies: v.replies.map(reply),
    ...(v.relay ? { relay: v.relay } : {}),
    ...(v.suggested ? { suggested: v.suggested } : {}),
  }
}

/** A question as it now stands: rephrased after a discussion, or as asked. */
export function view(base: Question, rephrased?: Revision, showOriginal?: boolean): Question {
  if (!rephrased || showOriginal) return base
  const options = base.options && rephrased.options?.length ? rephrased.options : base.options
  return { ...base, text: rephrased.text, ...(options ? { options } : {}) }
}

/** The replies the person judges: all but relay posts. */
export const others = (replies: Reply[]) => replies.filter(r => r.role !== 'relay')

/**
 * Where a tool named `mcp__<name>__<tool>` comes from: `<name>`, the mod or
 * MCP server that adds it.
 */
export function sourceOf(tool: string): string | undefined {
  const m = /^mcp__(.+?)__/.exec(tool)
  return m ? m[1] : undefined
}

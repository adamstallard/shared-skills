import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, Timer } from 'claude-code'

import type { UsageLimit } from '../types'

// Appends this session's subscription usage to the hint line under the
// prompt: `5h 31% ⇡ 3p · 7d 18% Fri 9a`. The figures are the ones the engine
// already keeps from its own responses, so this sends no request; they update
// as this session's calls report a window moving a whole point. The text is
// built when the line draws, and a once-a-minute redraw keeps the pace marker
// following the clock while the session is idle and the figures hold still.

const limits = atom({ plugin: 'usage-hint', key: 'limits' } as const, [])

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const HOUR = 3600_000
const WINDOWS: Record<string, { label: string; ms: number }> = {
  five_hour: { label: '5h', ms: 5 * HOUR },
  seven_day: { label: '7d', ms: 7 * 24 * HOUR },
}
// Points either side of an even pace that draw no marker, so it doesn't flip
// back and forth while usage sits near the line.
const PACE_SLACK = 5
// The line only redraws when its props or state change, so a timer redraws it
// for the clock. Pace moves a fifth of a point a minute at most (5h window).
const REDRAW_MS = 60_000
let redraws: Timer | undefined

// Started by the first reading; a reload cancels the timer and clears this.
function followClock($: EngineInterface): void {
  redraws ??= $.clock.every(REDRAW_MS, () => $.ui.invalidate('ui.render'))
}

// `3p`, `3:07p`; another day than `now` adds its weekday: `Fri 9a`.
// Every reset is under a week away, so the weekday is unambiguous.
export function compactTime(ms: number, now: number): string {
  const d = new Date(ms)
  const hour = d.getHours() % 12 || 12
  const min = d.getMinutes() ? `:${String(d.getMinutes()).padStart(2, '0')}` : ''
  const time = `${hour}${min}${d.getHours() < 12 ? 'a' : 'p'}`
  return d.toDateString() === new Date(now).toDateString() ? time : `${DAYS[d.getDay()]} ${time}`
}

// `⇡` when the window is being used faster than an even pace (the share of the
// window already gone by), `⇣` when slower, '' when within PACE_SLACK points or
// when the window's length or reset is unknown.
export function paceMarker(percentUsed: number, resetsAt: number, windowMs: number, now: number): string {
  const elapsed = 100 * (1 - (resetsAt - now) / windowMs)
  if (!Number.isFinite(elapsed) || elapsed < 0 || elapsed > 100) return ''
  const ahead = percentUsed - elapsed
  return ahead > PACE_SLACK ? '⇡' : ahead < -PACE_SLACK ? '⇣' : ''
}

// Undefined off a subscription and before the session's first response.
export function usageText(windows: readonly UsageLimit[], now: number): string | undefined {
  if (windows.length === 0) return undefined
  return windows
    .map(w => {
      const known = WINDOWS[w.kind]
      const resetsAt = w.resetsAt ? Date.parse(w.resetsAt) : NaN
      const pace = known && !Number.isNaN(resetsAt) ? paceMarker(w.percentUsed, resetsAt, known.ms, now) : ''
      const reset = Number.isNaN(resetsAt) ? '' : ' ' + compactTime(resetsAt, now)
      return `${known?.label ?? w.kind} ${Math.round(w.percentUsed)}%${pace ? ' ' + pace : ''}${reset}`
    })
    .join(' · ')
}

function plain(rateLimits: readonly UsageLimit[]): UsageLimit[] {
  return rateLimits.map(({ kind, percentUsed, resetsAt }) => (resetsAt ? { kind, percentUsed, resetsAt } : { kind, percentUsed }))
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    const { rateLimits } = await $.session.usage()
    await update($, limits, () => plain(rateLimits))
    followClock($)
    return started
  })

  on('session.measure', async ($, e, next) => {
    if (e.changed.includes('rateLimits')) {
      await update($, limits, () => plain(e.rateLimits))
      followClock($)
    }
    return next(e)
  })

  // The engine keeps its own line and draws `tail` dim at its end, cut where
  // the row ends, so the usage takes no row of its own.
  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    const text = usageText(await read($, limits), await $.clock.now())
    if (!text) return next(e)
    const before = e.props.tail ? e.props.tail + '  ·  ' : ''
    return next({ ...e, props: { ...e.props, tail: before + text } })
  })
}

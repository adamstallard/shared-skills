import { atom, read, update } from 'claude-code'
import type { Register, SessionRateLimit } from 'claude-code'

// Appends this session's subscription usage to the hint line under the
// prompt: `5h 31% 3p · 7d 18% Fri 9a`. The figures are the ones the engine
// already keeps from its own responses, so this sends no request; they update
// as this session's calls report a window moving a whole point, and stay put
// while it is idle.

const tail = atom({ plugin: 'usage-hint', key: 'tail' } as const, null)

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const KIND: Record<string, string> = { five_hour: '5h', seven_day: '7d' }

// `3p`, `3:07p`; another day than `now` adds its weekday: `Fri 9a`.
// Every reset is under a week away, so the weekday is unambiguous.
export function compactTime(ms: number, now: number): string {
  const d = new Date(ms)
  const hour = d.getHours() % 12 || 12
  const min = d.getMinutes() ? `:${String(d.getMinutes()).padStart(2, '0')}` : ''
  const time = `${hour}${min}${d.getHours() < 12 ? 'a' : 'p'}`
  return d.toDateString() === new Date(now).toDateString() ? time : `${DAYS[d.getDay()]} ${time}`
}

// Undefined off a subscription and before the session's first response.
export function usageText(limits: readonly SessionRateLimit[], now: number): string | undefined {
  if (limits.length === 0) return undefined
  return limits
    .map(l => {
      const reset = l.resetsAt ? ' ' + compactTime(Date.parse(l.resetsAt), now) : ''
      return `${KIND[l.kind] ?? l.kind} ${Math.round(l.percentUsed)}%${reset}`
    })
    .join(' · ')
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    const text = usageText((await $.session.usage()).rateLimits, await $.clock.now())
    await update($, tail, () => text ?? null)
    return started
  })

  on('session.measure', async ($, e, next) => {
    if (e.changed.includes('rateLimits')) {
      const text = usageText(e.rateLimits, await $.clock.now())
      await update($, tail, () => text ?? null)
    }
    return next(e)
  })

  // The engine keeps its own line and draws `tail` dim at its end, cut where
  // the row ends, so the usage takes no row of its own.
  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    const text = await read($, tail)
    if (!text) return next(e)
    const before = e.props.tail ? e.props.tail + '  ·  ' : ''
    return next({ ...e, props: { ...e.props, tail: before + text } })
  })
}

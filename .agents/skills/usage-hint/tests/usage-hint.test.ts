import { expect, test } from 'claude-code/testing'

import { compactTime, paceMarker, usageText } from '../hooks/register'

const MON_9AM = new Date(2026, 9, 5, 9, 0).getTime()
const HOUR = 3600_000

test('reset time is compact: time today, weekday otherwise', async () => {
  expect(compactTime(new Date(2026, 9, 5, 15, 0).getTime(), MON_9AM)).toBe('3p')
  expect(compactTime(new Date(2026, 9, 5, 15, 7).getTime(), MON_9AM)).toBe('3:07p')
  expect(compactTime(new Date(2026, 9, 9, 9, 0).getTime(), MON_9AM)).toBe('Fri 9a')
})

test('pace marker compares usage with the share of the window gone by', async () => {
  // 2 of 5 hours gone (40%), resetting in 3 hours.
  const resetsAt = MON_9AM + 3 * HOUR
  expect(paceMarker(60, resetsAt, 5 * HOUR, MON_9AM)).toBe('⇡')
  expect(paceMarker(20, resetsAt, 5 * HOUR, MON_9AM)).toBe('⇣')
  expect(paceMarker(43, resetsAt, 5 * HOUR, MON_9AM)).toBe('')
  // A reset further away than the window is long: no marker rather than a guess.
  expect(paceMarker(50, MON_9AM + 6 * HOUR, 5 * HOUR, MON_9AM)).toBe('')
})

test('usage reads 5h and 7d with pace and resets; nothing off a subscription', async () => {
  const limits = [
    // 5h: 2 of 5 hours gone (40%), 60% used: ahead.
    { kind: 'five_hour', percentUsed: 60, resetsAt: new Date(MON_9AM + 3 * HOUR).toISOString() },
    // 7d: resets Fri 9a, so 3 of 7 days gone (43%), 18% used: behind.
    { kind: 'seven_day', percentUsed: 18, resetsAt: new Date(2026, 9, 9, 9, 0).toISOString() },
  ]
  expect(usageText(limits, MON_9AM)).toBe('5h 60% ⇡ 12p · 7d 18% ⇣ Fri 9a')
  expect(usageText([{ kind: 'spend_limit', percentUsed: 50 }], MON_9AM)).toBe('spend_limit 50%')
  expect(usageText([], MON_9AM)).toBeUndefined()
})

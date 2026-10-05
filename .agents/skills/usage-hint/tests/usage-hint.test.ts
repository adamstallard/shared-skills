import { expect, test } from 'claude-code/testing'

import { compactTime, usageText } from '../hooks/register'

const MON_9AM = new Date(2026, 9, 5, 9, 0).getTime()

test('reset time is compact: time today, weekday otherwise', async () => {
  expect(compactTime(new Date(2026, 9, 5, 15, 0).getTime(), MON_9AM)).toBe('3p')
  expect(compactTime(new Date(2026, 9, 5, 15, 7).getTime(), MON_9AM)).toBe('3:07p')
  expect(compactTime(new Date(2026, 9, 9, 9, 0).getTime(), MON_9AM)).toBe('Fri 9a')
})

test('usage reads 5h and 7d with resets; nothing off a subscription', async () => {
  const limits = [
    { kind: 'five_hour', percentUsed: 31.4, resetsAt: new Date(2026, 9, 5, 15, 0).toISOString() },
    { kind: 'seven_day', percentUsed: 18, resetsAt: new Date(2026, 9, 9, 9, 0).toISOString() },
  ]
  expect(usageText(limits, MON_9AM)).toBe('5h 31% 3p · 7d 18% Fri 9a')
  expect(usageText([{ kind: 'spend_limit', percentUsed: 50 }], MON_9AM)).toBe('spend_limit 50%')
  expect(usageText([], MON_9AM)).toBeUndefined()
})

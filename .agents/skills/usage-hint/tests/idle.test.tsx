import { expect, mock, test } from 'claude-code/testing'

const HOUR = 3600_000
const T0 = new Date(2026, 9, 5, 9, 0).getTime()

test('the pace marker follows the clock while the session is idle', async ($, on) => {
  const clock = mock.clock(on, { now: T0 })
  const tails: (string | undefined)[] = []
  on('ui.render', { component: 'PromptHint' }, ($, e) => {
    tails.push(e.props.tail)
    const { Text } = $.ui.resolve(e)
    return <Text>{String(e.props.tail)}</Text>
  })
  on('session.measure', ($, e) => ({ changed: e.changed }))
  // 2 of 5 hours gone (40%) with 60% used: ahead.
  await $.session.measure({
    context: { contextWindow: 200_000 } as never,
    rateLimits: [{ kind: 'five_hour', percentUsed: 60, resetsAt: new Date(T0 + 3 * HOUR).toISOString() }],
    changed: ['rateLimits'],
  })
  const ui = await $.ui.mount({
    plugin: 'usage-hint',
    surface: 'terminal',
    component: 'PromptHint',
    props: { isDraft: false, isWorking: false, hint: '? for shortcuts' },
  })
  expect(tails.at(-1)).toBe('5h 60% ⇡ 12p')
  // Two idle hours: 80% of the window gone with 60% used is behind.
  await clock.advance(2 * HOUR)
  await clock.settle()
  expect(tails.at(-1)).toBe('5h 60% ⇣ 12p')
  await ui.unmount()
})

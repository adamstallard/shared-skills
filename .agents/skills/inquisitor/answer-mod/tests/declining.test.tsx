// Declining a question: its two reasons, the filters, reopening.
import { expect, test } from 'claude-code/testing'

import { BAND, DONE, POSTED, previewOf, question, polled, session, shown } from './harness'

function open(on: Parameters<typeof session>[0], questions: unknown[], core: Record<string, (req: Record<string, unknown>) => unknown> = {}) {
  return session(on, {
    core: {
      poll: () => polled(questions),
      preview: req =>
        req['reason'] === 1
          ? previewOf(null, { record: { place: null, visibility: null, not_recorded: 'a decline with nothing to answer records nothing' } })
          : req['filter'] === 1
            ? previewOf(`Recorded answer: see the record below.\nRecorded in: ${String(req['recorded_in'])}`)
            : previewOf(`Inquisitor: Filter ${String(req['filter'])} (cheap to reverse): pick one, it's cheap to switch.\nThe person chose this filter.`),
      post: () => POSTED,
      reopen: () => DONE,
      ...core,
    },
  })
}

const T1 = '2026-10-20T09:00:00Z'
const T2 = '2026-10-20T09:30:00Z'

test('declining with nothing to answer posts nothing and closes only that question; it can be reopened here', async ($, on) => {
  // @scenario answer-service: Declining with nothing to answer posts nothing
  // @scenario answer-service: A thread copy declined with nothing posted is reopened
  const s = open(on, [question('q1', { text: 'Done?', asked_at: T1 }), question('q2', { text: 'And this?', asked_at: T2 })])
  await s.start($)
  await s.enter($, 'w')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /WON'T ANSWER · CHOOSE WHY/)).toBeDefined()
  expect(await shown(ui, /Nothing to answer: the conversation is over, or it isn't a question/)).toBeDefined()
  expect(await s.enter($, '1')).toBe("Won't answer.")
  expect(s.of('preview').at(-1)).toMatchObject({ question: 'q1', action: 'decline', reason: 1 })
  expect(s.of('post').length).toBe(1)
  await ui.redraw()
  // The other question in the thread stays, and comes next.
  expect(await shown(ui, /And this\?/)).toBeDefined()
  await s.enter($, 'b')
  expect(await s.enter($, 'r')).toContain('just come on screen')
  expect(await s.enter($, 'r')).toContain('back in your queue')
  expect(s.of('reopen')).toEqual([expect.objectContaining({ question: 'q1' })])
})

test("reason 2 is offered on an agent's question only", async ($, on) => {
  // @scenario answer-service: A message picked up by mistake logs no miss
  const s = open(on, [question('q1', { text: 'Can you look?', asker: 'person', asked_by: 'maya' })])
  await s.start($)
  await s.enter($, 'w')
  expect(await s.enter($, '2')).toContain("for an agent's question only")
  expect(s.of('preview')).toEqual([])
})

test('reason 2 with filter 3 and a note shows the exact post, and posts it once confirmed', async ($, on) => {
  // @scenario answer-service: The inquisitor's reply is posted once the person confirms it
  // @scenario answer-service: The person's filter 3 reply ends with the chosen line
  // The person picks filter 3, whose reply ends with `The person chose this filter.`
  const s = open(on, [question('q1', { text: 'Flag or env var?' })])
  await s.start($)
  await s.enter($, 'w')
  await s.enter($, '2')
  await s.enter($, '3')
  await s.clock.advance(500)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /The person chose this filter\./)).toBeDefined()
  expect(s.of('post')).toEqual([])
  expect(await s.enter($, 'a config flag, easy to flip')).toContain('check the preview first')
  expect(await s.enter($, 'a config flag, easy to flip')).toBe('Posted.')
  expect(s.of('preview').at(-1)).toMatchObject({ action: 'decline', reason: 2, filter: 3, note: 'a config flag, easy to flip' })
  expect(s.of('post').length).toBe(1)
})

test('filter 1 takes one URL as the place: one with a space is refused, one without is previewed and posted', async ($, on) => {
  // @scenario answer-service: A filter 1 reply whose URL holds a line break or a space is refused
  // @scenario answer-service: A filter 1 reply names the place the person gave
  const s = open(on, [question('q1', { text: 'Back off?' })])
  await s.start($)
  await s.enter($, 'w')
  await s.enter($, '2')
  await s.enter($, '1')
  expect(await s.enter($, 'the retry spec')).toContain('no space or line break')
  const url = 'https://github.com/o/api/blob/main/openspec/specs/retry/spec.md'
  await s.enter($, url)
  expect(await s.enter($, 'p')).toContain('check the preview first')
  expect(await s.enter($, 'p')).toBe('Posted.')
  expect(s.of('preview').at(-1)).toMatchObject({ action: 'decline', reason: 2, filter: 1, recorded_in: url })
})

test('a declined questions-branch file is not offered for reopening', async ($, on) => {
  // @scenario answer-service: A declined questions-branch file is not offered for reopening
  const s = open(on, [question('q1', { text: 'Which cap?', asker: 'questions-branch', url: 'https://github.com/o/lore/blob/questions/q.md' })])
  await s.start($)
  await s.enter($, 'w')
  await s.enter($, '1')
  await s.enter($, 'b')
  expect(await s.enter($, 'r')).toContain('closes it everywhere')
  expect(s.of('reopen')).toEqual([])
})

test("filter 3 also offers that the agent shouldn't have asked, which posts nothing", async ($, on) => {
  // @scenario answer-service: The agent shouldn't have asked posts nothing
  const s = open(on, [question('q1', { text: 'Thanks, all done here?' })], {
    preview: req => (req['unasked'] ? previewOf(null, { record: { place: 'o/api', visibility: 'private' } }) : previewOf('Inquisitor: Filter 3 (only one option has merit): take the option that has merit.\nThe person chose this filter.')),
    post: () => ({ version: 1, ok: true, status: 'posted', warnings: [] }),
  })
  await s.start($)
  await s.enter($, 'w')
  await s.enter($, '2')
  await s.enter($, '3')
  await s.clock.advance(1_000)
  // The band's preview of the plain filter 3 reply, which p would post, carries no unasked.
  expect(s.of('preview').at(-1)).toMatchObject({ action: 'decline', reason: 2, filter: 3 })
  expect(s.of('preview').at(-1)).not.toHaveProperty('unasked')
  await s.enter($, 'u')
  expect(s.of('preview').at(-1)).toMatchObject({ action: 'decline', reason: 2, filter: 3, unasked: true })
  expect(s.of('post').length).toBe(1)
})

test('a decline with a note posts on the next Enter even when the engine puts nothing back', async ($, on) => {
  // @scenario answer-service: The inquisitor's reply is posted once the person confirms it
  const s = open(on, [question('q1', { text: 'Thanks, all done here?' })], {
    preview: req => previewOf(`Inquisitor: Filter 3 (only one option has merit): ${String(req['note'] ?? '')}`),
    post: () => ({ version: 1, ok: true, status: 'posted', warnings: [] }),
  })
  await s.start($)
  await s.enter($, 'w')
  await s.enter($, '2')
  await s.enter($, '3')
  await s.clock.advance(1_000)
  expect(await s.enter($, 'a config flag')).toContain('check the preview first')
  await s.clock.advance(1_000)
  expect(await s.enter($, 'a config flag')).toBe('Posted.')
})

test('a decline with a note is shown before it goes, even when it posts in no thread', async ($, on) => {
  // @scenario answer-service: The inquisitor's reply is posted once the person confirms it
  const s = open(on, [question('q1', { text: 'Thanks, all done here?' })], {
    preview: () => previewOf(null, { record: { place: 'o/api', visibility: 'private' } }),
    post: () => ({ version: 1, ok: true, status: 'posted', warnings: [] }),
  })
  await s.start($)
  await s.enter($, 'w')
  await s.enter($, '2')
  await s.enter($, '3')
  await s.clock.advance(1_000)
  expect(await s.enter($, 'my private note about this agent')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
})

test('agreeing to the suggested verdict declines with that filter, and the reply is shown before it posts', async ($, on) => {
  // @scenario answer-service: Agreeing to a suggested verdict declines with that filter
  const s = open(on, [question('q1', { text: 'Flag or env var?', suggested: { filter: 4, why: 'either is a one-line change' } })])
  await s.start($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /Claude suggests filter 4, cheap to reverse: either is a one-line change/)).toBeDefined()
  await s.enter($, 'g')
  await s.clock.advance(500)
  expect(s.of('post')).toEqual([])
  expect(await s.enter($, 'p')).toContain('check the preview first')
  expect(await s.enter($, 'p')).toBe('Posted.')
  expect(s.of('preview').at(-1)).toMatchObject({ action: 'decline', reason: 2, filter: 4 })
})

test("a person's question offers no suggested verdict to agree to", async ($, on) => {
  // @scenario answer-service: A person's question gets no suggested verdict and no filter to decline with
  const s = open(on, [question('q1', { text: 'Flag or env var?', asker: 'person', asked_by: 'maya', suggested: { filter: 4, why: 'x' } })])
  await s.start($)
  expect(await s.enter($, 'g')).toContain('not a command')
})

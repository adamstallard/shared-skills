// Answering in the band: the core's preview, the post and what it says back,
// editing, asking the asker, and the replies since the question.
import { expect, test } from 'claude-code/testing'

import { questionOf } from '../hooks/questions'
import { BAND, POSTED, previewOf, question, polled, session, shown, typeInBox } from './harness'

const AGENT_Q = 'Should retries back off?\n\n1. Yes, exponentially: calls spread out under load\n2. No, retry at once: simpler'

/** A session open on one agent's question with options, and the core answering previews and posts as given. */
function open(on: Parameters<typeof session>[0], core: Record<string, (req: Record<string, unknown>) => unknown> = {}, questions = [question('q1', { text: AGENT_Q })]) {
  return session(on, {
    core: {
      poll: () => polled(questions, { judge: [{ message: 'm9', turn: 1, text: 'x', needs_place: true, needs_place_sure: false, places: ['o/api', 'o/web'], defaults: [], person_question: false }] }),
      preview: req => previewOf(`User says: ${String(req['text'] ?? '')}\n\nRe: https://github.com/o/api/pull/12#issuecomment-1001`),
      post: () => POSTED,
      ...core,
    },
  })
}

test('a click on an option types its number; the core previews the post and where it is recorded, and Enter posts it', async ($, on) => {
  // @scenario answer-service: The preview names the branch and its visibility
  // The record's place is o/api's questions branch, which is private.
  const s = open(on)
  await s.start($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /Yes, exponentially/)).toBeDefined()
  await ui.press({ key: 'opt:q1:0' })
  expect(s.filled).toEqual(['1'])
  await s.clock.advance(500)
  expect(s.of('preview')[0]).toMatchObject({ question: 'q1', action: 'answer', text: 'Yes, exponentially' })
  await ui.redraw()
  expect(await shown(ui, /RECORDED IN o\/api · private/)).toBeDefined()
  expect(await shown(ui, /Re: https:\/\/github.com\/o\/api\/pull\/12/)).toBeDefined()
  expect(await s.enter($, '1')).toBe('Relayed.')
  expect(s.of('post')).toEqual([expect.objectContaining({ preview: 'pv-1' })])
  // The preview drawn was the one posted: no second preview.
  expect(s.of('preview').length).toBe(1)
  await ui.redraw()
  expect(await shown(ui, /1 relayed/)).toBeDefined()
})

test('nothing posts before Enter, and one letter that is no command is refused', async ($, on) => {
  // @scenario answer-service: A draft lands in the prompt box
  // A click types the option into the box, as a draft does: nothing posts before Enter.
  const s = open(on)
  await s.start($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'opt:q1:1' })
  await s.clock.advance(500)
  expect(s.of('post')).toEqual([])
  expect(await s.enter($, 'z')).toContain('not a command')
  expect(s.of('post')).toEqual([])
})

test('a preview warning a more visible record is shown first; the next Enter posts it', async ($, on) => {
  // @scenario answer-service: The preview warns before a record more visible than its thread
  const s = open(on, { preview: () => previewOf('User says: Yes, back off.', { record: { place: 'o/web', visibility: 'public', more_visible_than: 'the Discord thread' } }) })
  await s.start($)
  expect(await s.enter($, 'Yes, back off.')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
  // What was typed comes back in the box, and the band shows the core's preview of it.
  await s.clock.advance(500)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /RECORDED IN o\/web · public/)).toBeDefined()
  expect(await shown(ui, /more visible than/)).toBeDefined()
  expect(await s.enter($, 'Yes, back off.')).toBe('Relayed.')
  expect(s.of('post').length).toBe(1)
})

test('the preview says when an answer also reaches a more visible item’s run, and when nothing is recorded', async ($, on) => {
  // @scenario answer-service: The preview says an answer also reaches a more visible item's run
  // @scenario answer-service: The preview says when nothing will be recorded
  const s = open(on, {
    preview: () =>
      previewOf(null, {
        record: { place: null, visibility: null, not_recorded: 'the question has a category, and the asker will not receive the answer' },
        reaches_run: "The answer is also passed to the Igor's run on o/web #4, which must not quote it there.",
      }),
  })
  await s.start($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'opt:q1:0' })
  await s.clock.advance(500)
  await ui.redraw()
  expect(await shown(ui, /Not recorded: the question has a category/)).toBeDefined()
  expect(await shown(ui, /also passed to the Igor's run on o\/web #4/)).toBeDefined()
})

test('the person picks another place for the record, and the next preview records it there', async ($, on) => {
  // @scenario answer-service: The person moves a question to another place
  const s = open(on)
  await s.start($)
  await s.enter($, 's')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /WHERE SHOULD THE ANSWER BE RECORDED\?/)).toBeDefined()
  expect(await shown(ui, /o\/web/)).toBeDefined()
  expect(await s.enter($, '2')).toContain('recorded in o/web')
  await s.enter($, 'Yes, back off.')
  expect(s.of('preview').at(-1)).toMatchObject({ action: 'answer', place: 'o/web' })
})

test('an answer the core asks to reword is not posted', async ($, on) => {
  // @scenario answer-service: An answer ending in its own Re line is sent back for rewording
  const s = open(on, { preview: () => previewOf(null, { reword: "Its last line starts with Re: , which a reader takes for the post's own: reword it." }) })
  await s.start($)
  expect(await s.enter($, 'Yes.\nRe: https://github.com/o/api/issues/7#issuecomment-1')).toContain('reword it')
  expect(s.of('post')).toEqual([])
})

test('a post the core holds for a reply the person has not seen shows the reply, marked new', async ($, on) => {
  // @scenario answer-service: A new reply stops the post
  let polls = 0
  const reply = { author: 'api-bot[bot]', text: 'Actually, only on 429s.', at: '2026-10-20T10:04:00Z', url: 'https://github.com/o/api/pull/12#issuecomment-1002' }
  const s = session(on, {
    core: {
      poll: () => polled([question('q1', { text: AGENT_Q, replies: ++polls > 1 ? [reply] : [] })]),
      preview: () => previewOf('User says: Yes.'),
      post: () => ({ version: 1, ok: true, status: 'held', warnings: [], why: 'a reply arrived' }),
    },
  })
  await s.start($)
  expect(await s.enter($, 'Yes, back off.')).toBe('Not posted: api-bot[bot] replied since you last read the thread. Read it, then ⏎ again.')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /1 REPLY SINCE IT WAS ASKED · 1 NEW/)).toBeDefined()
  expect(await shown(ui, /only on 429s/)).toBeDefined()
})

test('a failed question to the asker says why, and leaves the question unanswered', async ($, on) => {
  // @scenario answer-service: A failed question to the asker or automatic post leaves its question unanswered
  const s = open(on, { post: () => ({ version: 1, ok: true, status: 'failed', warnings: [], why: 'GitHub answered 403: the App cannot comment here' }) })
  await s.start($)
  await s.enter($, 't')
  await s.enter($, 'a')
  expect(await s.enter($, 'Which calls do you mean?')).toContain('GitHub answered 403')
  expect(s.of('preview').at(-1)).toMatchObject({ action: 'ask', text: 'Which calls do you mean?' })
  await s.enter($, 'b')
  await s.enter($, 'b')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /waiting for/)).toBeUndefined()
  expect(await shown(ui, /1 unanswered/)).toBeDefined()
})

test('a clarifying question goes to the asker through the preview and post, and the question waits', async ($, on) => {
  // @scenario answer-service: A clarifying question goes to the asker's thread
  const s = open(on, { preview: req => previewOf(`User asks: ${String(req['text'])}`) })
  await s.start($)
  await s.enter($, 't')
  await s.enter($, 'a')
  expect(await s.enter($, 'Which calls do you mean?')).toBe('Asked.')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /1 waiting/)).toBeDefined()
})

test('an answer the core keeps pending is listed with why, on the summary', async ($, on) => {
  // @scenario answer-service: A refused answer is kept pending
  const s = open(on, {
    post: () => ({ version: 1, ok: true, status: 'pending', warnings: [], why: 'Discord refused the post: missing permission' }),
    'pending.list': () => ({ version: 1, ok: true, answers: [{ question: 'q1', text: 'Yes, back off.', why: 'Discord refused the post: missing permission' }] }),
  })
  await s.start($)
  expect(await s.enter($, 'Yes, back off.')).toBe('Kept pending.')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /1 ANSWER NOT YET RELAYED/)).toBeDefined()
  expect(await shown(ui, /Discord refused the post: missing permission/)).toBeDefined()
})

test('a relayed answer is edited in place: e puts the post in the box, Enter previews and posts the edit', async ($, on) => {
  // @scenario answer-service: An answer is edited in place
  const s = open(on)
  await s.start($)
  await s.enter($, 'Yes, back off.')
  await s.enter($, 'b')
  await s.enter($, 'e')
  await s.clock.advance(500)
  expect(s.filled.at(-1)).toBe('Yes, back off.')
  expect(await s.enter($, 'Yes, back off, capped at a minute.')).toBe('Edited.')
  expect(s.of('preview').at(-1)).toMatchObject({ action: 'edit', text: 'Yes, back off, capped at a minute.' })
  expect(s.of('post').length).toBe(2)
})

test('the replies since the question are shown with it, the relay’s own posts left out', async ($, on) => {
  // @scenario answer-service: Replies since the question are shown
  const replies = [
    { author: 'maya', text: 'I would say yes.', at: '2026-10-20T10:01:00Z', url: 'u1' },
    { author: 'tom', text: 'Agreed, with a cap.', at: '2026-10-20T10:02:00Z', url: 'u2' },
    { author: 'answers[bot]', text: 'Inquisitor: Filter 4 (cheap to reverse): pick one.', at: '2026-10-20T10:03:00Z', url: 'u3' },
  ]
  const s = open(on, {}, [question('q1', { text: AGENT_Q, replies })])
  await s.start($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /2 REPLIES SINCE IT WAS ASKED/)).toBeDefined()
  expect(await shown(ui, /Agreed, with a cap/)).toBeDefined()
})

test('a recorded answer shown beside the question is agreed to by a and Enter, through the preview', async ($, on) => {
  // @scenario answer-service: A filter 1 reply with a more private record is posted only after a warning
  const s = open(
    on,
    { preview: () => previewOf('Recorded answer: see the record below.\nRecorded in: https://github.com/o/priv/blob/main/d.md', { warnings: ['Posting it shows the private record exists.'] }) },
    [question('q1', { text: AGENT_Q, recorded: { recorded_in: 'https://github.com/o/priv/blob/main/d.md', quote: 'Back off exponentially.' } })],
  )
  await s.start($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /RECORDED ANSWER · FILTER 1/)).toBeDefined()
  expect(await s.enter($, 'a')).toContain('check the preview first')
  expect(s.of('preview').at(-1)).toMatchObject({ action: 'agree' })
  expect(await s.enter($, 'a')).toBe('Posted.')
})

test('a question that leaves the queue while an answer is typed takes the answer with it', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  // An answer typed for q1 never posts unseen to the question that took q1's place.
  let polls = 0
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const s = open(on, { poll: () => polled(++polls === 1 ? [q1, q2] : [q2]) })
  on('prompt.change', (_, e) => ({ text: e.text }))
  await s.start($)
  await typeInBox($, 'Answer meant for the first')
  await s.clock.advance(500)
  expect(s.of('preview').at(-1)).toMatchObject({ question: 'q1' })
  await s.clock.advance(70_000)
  expect(await s.enter($, 'Answer meant for the first')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
  expect(s.of('preview').at(-1)).toMatchObject({ question: 'q2' })
  // Having seen q2's preview, the person may still post it there.
  expect(await s.enter($, 'Answer meant for the first')).toBe('Relayed.')
})

test('a held post whose question then leaves the queue posts nothing to the next question on the next Enter', async ($, on) => {
  // @scenario answer-service: A new reply stops the post
  let polls = 0
  let posts = 0
  const s = open(on, {
    poll: () => polled(++polls > 1 ? [question('q2', { text: 'Other question?' })] : [question('q1', { text: AGENT_Q }), question('q2', { text: 'Other question?', asked_at: '2026-10-20T10:04:30Z' })]),
    post: () => (++posts === 1 ? { version: 1, ok: true, status: 'held', warnings: [], why: 'a reply arrived' } : POSTED),
  })
  await s.start($)
  expect(await s.enter($, 'Yes, back off.')).toContain('Not posted')
  expect(await s.enter($, 'Yes, back off.')).toContain('check the preview first')
  expect(s.of('post').length).toBe(1)
})

test('a reply from the asker is marked as the asker\'s, and no one else\'s is', async () => {
  // @scenario answer-service: Replies since the question are shown
  const view = question('q1', {
    asked_by: 'maya',
    replies: [
      { author: 'maya', text: 'Only on 429s.', at: '2026-10-20T10:01:00Z', url: 'u1' },
      { author: 'tom', text: 'Agreed.', at: '2026-10-20T10:02:00Z', url: 'u2' },
    ],
  })
  const q = questionOf(view as never, Date.parse('2026-10-20T10:05:00Z'))
  expect(q.replies.map(r => r.role)).toEqual(['asker', undefined])
})

test('settling the last of three questions moves to the first one still unanswered', async ($, on) => {
  // @scenario answer-service: The question asked first comes first
  // After an answer, the band goes to the earliest-asked question still unanswered.
  const qs = [
    question('q1', { text: 'Alpha one?', asked_at: '2026-10-20T09:00:00Z' }),
    question('q2', { text: 'Beta two?', asked_at: '2026-10-20T09:10:00Z' }),
    question('q3', { text: 'Gamma three?', asked_at: '2026-10-20T09:20:00Z' }),
  ]
  const s = open(on, {}, qs)
  await s.start($)
  await s.enter($, 'n')
  await s.enter($, 'n')
  expect(await s.enter($, 'Answer to gamma.')).toBe('Relayed.')
  expect(s.of('preview').at(-1)).toMatchObject({ question: 'q3' })
  expect(s.of('screen.set').at(-1)).toMatchObject({ question: 'q1' })
})

test('typing on after a poll takes the question away still stops the first Enter', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  let polls = 0
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const s = open(on, { poll: () => polled(++polls === 1 ? [q1, q2] : [q2]) })
  on('prompt.change', (_, e) => ({ text: e.text }))
  await s.start($)
  await typeInBox($, 'Answer meant for the first')
  await s.clock.advance(500)
  await s.clock.advance(70_000)
  await typeInBox($, 'Answer meant for the first.')
  await s.clock.advance(500)
  expect(await s.enter($, 'Answer meant for the first.')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
})

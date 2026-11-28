// Answering in the band: the core's preview, the post and what it says back,
// editing, asking the asker, and the replies since the question.
import { expect, test } from 'claude-code/testing'

import { dropped, leaveBox, putBackOf } from '../hooks/actions'
import { questionOf } from '../hooks/questions'
import { BAND, POSTED, enterAsTyped, previewOf, question, polled, session, shown, typeInBox } from './harness'

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
  expect(await s.enter($, '1')).toContain('check the preview first')
  expect(await s.enter($, '1')).toBe('Relayed.')
  // Each Enter asks the core for its own preview, besides the one the band drew.
  expect(s.of('preview').length).toBe(3)
  expect(s.of('post')).toEqual([expect.objectContaining({ preview: 'pv-1' })])
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
  expect(await s.enter($, 'Yes, back off.')).toContain('check the preview first')
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
  expect(await s.enter($, 'Which calls do you mean?')).toContain('check the preview first')
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
  expect(await s.enter($, 'Which calls do you mean?')).toContain('check the preview first')
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
  expect(await s.enter($, 'Yes, back off.')).toContain('check the preview first')
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
  await s.enter($, 'Yes, back off.')
  await s.enter($, 'b')
  await s.enter($, 'e')
  expect(s.filled.at(-1)).toBe('Yes, back off.')
  expect(await s.enter($, 'Yes, back off, capped at a minute.')).toContain('check the preview first')
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
  expect(await s.enter($, 'Yes, back off.')).toContain('check the preview first')
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
  expect(await s.enter($, 'Answer to gamma.')).toContain('check the preview first')
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
  await s.start($)
  await typeInBox($, 'Answer meant for the first')
  await s.clock.advance(500)
  await s.clock.advance(70_000)
  await typeInBox($, 'Answer meant for the first.')
  await s.clock.advance(500)
  expect(await s.enter($, 'Answer meant for the first.')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
})

test('after discussing the question that took the place of one a poll took away, the draft posts once its preview is shown', async ($, on) => {
  // @scenario answer-service: A draft lands in the prompt box
  // Nothing was typed for q1: the person saw q2, discussed it and took a draft for it.
  let polls = 0
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const s = open(on, { poll: () => polled(++polls === 1 ? [q1, q2] : [q2]), context: () => ({ version: 1, ok: true, context: 'the question' }) })
  await s.start($)
  await s.clock.advance(70_000)
  await s.enter($, 'h')
  await s.enter($, 'Help me answer the second question')
  await s.reply($, 'Say yes.')
  await $.tool.call({ tool: 'mcp__inquisitor-answer-mod__propose_reply', text: 'Answer for the second.' })
  await s.clock.advance(500)
  expect(await s.enter($, 'Answer for the second.')).toContain('check the preview first')
  expect(await s.enter($, 'Answer for the second.')).toBe('Relayed.')
  expect(s.of('post').length).toBe(1)
})

test('a preview the core cannot make stops the post and says why', async ($, on) => {
  // With no preview to show, nothing posts.
  const s = open(on, { preview: () => ({ version: 1, ok: false, error: 'core down' }) })
  await s.start($)
  expect(await s.enter($, 'Yes, back off.')).toBe('Not posted: core down')
  expect(s.of('post')).toEqual([])
})

test('after a question to the asker the surface refused, the next Enter previews again and posts the new preview', async ($, on) => {
  // @scenario answer-service: A failed question to the asker or automatic post leaves its question unanswered
  let previews = 0
  let posts = 0
  const s = open(on, {
    preview: () => previewOf('User asks: Which calls?', { id: `pv-${++previews}` }),
    post: () => (++posts === 1 ? { version: 1, ok: true, status: 'failed', warnings: [], why: 'GitHub answered 502.' } : POSTED),
  })
  await s.start($)
  await s.enter($, 't')
  await s.enter($, 'a')
  expect(await s.enter($, 'Which calls?')).toContain('check the preview first')
  expect(await s.enter($, 'Which calls?')).toBe('Not posted: GitHub answered 502.')
  expect(await s.enter($, 'Which calls?')).toContain('check the preview first')
  expect(await s.enter($, 'Which calls?')).toBe('Asked.')
  // Each post is of the preview its own Enter asked for.
  expect(s.of('post').map(p => p['preview'])).toEqual(['pv-2', 'pv-4'])
})

test('a draft from a discussion still running when a poll took its question away is dropped', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  // The turn began on q1; its draft never lands on q2, which took q1's place.
  let polls = 0
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const s = open(on, { poll: () => polled(++polls === 1 ? [q1, q2] : [q2]), context: () => ({ version: 1, ok: true, context: 'the question' }) })
  await s.start($)
  await s.enter($, 'h')
  await s.enter($, 'Help me answer the first question')
  await $.turn.start({ text: s.sent.at(-1) ?? '', turnId: 'turn-q1' })
  await s.clock.advance(70_000)
  await s.enter($, 'h')
  const r = await $.tool.call({ tool: 'mcp__inquisitor-answer-mod__propose_reply', text: 'Answer for the first.' })
  expect(r.deny).toContain('dropped')
  expect(s.filled).not.toContain('Answer for the first.')
  await s.clock.advance(500)
  expect(s.of('post')).toEqual([])
})

test('a judging turn running when the person opens a discussion on the question now on screen does not drop its draft', async ($, on) => {
  // @scenario answer-service: A draft lands in the prompt box
  // A judging turn drafts nothing: once the person discusses q2 and takes a draft for it, the draft posts after the Enter that shows its preview.
  let polls = 0
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const judge = { message: 'm9', turn: 1, text: 'x', needs_place: false, needs_place_sure: false, places: [], defaults: [], person_question: false }
  const s = session(on, {
    core: {
      poll: () => (++polls === 1 ? polled([q1, q2]) : polled([q2], { judge: [judge] })),
      preview: req => previewOf(`User says: ${String(req['text'] ?? '')}`),
      post: () => POSTED,
      context: () => ({ version: 1, ok: true, context: 'the question' }),
      'judge.turn-end': () => ({ version: 1, ok: true, next: null, posted: [], notices: [] }),
    },
  })
  await s.start($)
  await s.clock.advance(70_000)
  await $.turn.start({ text: s.sent.at(-1) ?? '', turnId: 'judge-1' })
  expect(await s.enter($, 'h')).toBe('Talking to Claude')
  await $.turn.complete({ answer: 'judged.', durationMs: 1, isAborted: false, turnId: 'judge-1', reason: 'answer' })
  await s.clock.settle()
  await s.enter($, 'Help me answer the second question')
  await s.reply($, 'Say yes.')
  await $.tool.call({ tool: 'mcp__inquisitor-answer-mod__propose_reply', text: 'Answer for the second.' })
  await s.clock.advance(500)
  expect(await s.enter($, 'Answer for the second.')).toContain('check the preview first')
  expect(await s.enter($, 'Answer for the second.')).toBe('Relayed.')
})

test('opening a discussion clears the notice the band was showing', async ($, on) => {
  // @scenario answer-service: A discussion message carries its question
  const s = open(on)
  await s.start($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /Answer service open/)).toBeDefined()
  expect(await s.enter($, 't')).toBe('Talking to Claude')
  await ui.redraw()
  expect(await shown(ui, /Answer service open/)).toBeUndefined()
})

test('a discussion message sent while Claude is still answering is not sent, so no draft lands on the wrong question', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const s = open(on, { poll: () => polled([q1, q2]), context: () => ({ version: 1, ok: true, context: 'the question' }) })
  await s.start($)
  await s.enter($, 'h')
  await s.enter($, 'Help me answer the first question')
  await $.turn.start({ text: s.sent.at(-1) ?? '', turnId: 'turn-q1' })
  await s.enter($, 'b')
  await s.enter($, 'n')
  await s.enter($, 'h')
  const sent = s.sent.length
  expect(await s.enter($, 'Help me answer the second question')).toContain('still answering')
  expect(s.sent.length).toBe(sent)
  await $.turn.complete({ answer: 'ok', durationMs: 1, isAborted: false, turnId: 'turn-q1', reason: 'answer' })
  await s.clock.settle()
  // Once that turn is over, the message goes to Claude.
  expect(await s.enter($, 'Help me answer the second question')).toBeUndefined()
  expect(s.sent.length).toBe(sent + 1)
})

test('a discussion message dropped beneath the mod leaves the discussion open and judging going', async ($, on) => {
  // @scenario answer-service: The discussion record keeps both sides
  let block = true
  let polls = 0
  const judge = { message: 'm1', turn: 1, text: 'x', needs_place: false, needs_place_sure: false, places: [], defaults: [], person_question: false }
  const s = session(on, {
    core: {
      poll: () => polled([question('q1', { text: 'First question?' })], ++polls > 1 ? { judge: [judge] } : {}),
      context: () => ({ version: 1, ok: true, context: 'the question' }),
      preview: req => previewOf(`User says: ${String(req['text'] ?? '')}`),
      post: () => POSTED,
    },
    drop: text => (block && text.includes('What breaks') ? 'blocked by a UserPromptSubmit hook' : undefined),
  })
  const asked: string[] = []
  on('model.complete', (_, e) => {
    asked.push(JSON.stringify(e))
    return { value: { isAnswered: true, text: '{"question": "Retry?", "context": "", "options": [], "summary": "s"}' } } as never
  })
  on('session.model', () => ({ value: 'claude-opus-5-5' }) as never)
  await s.start($)
  await s.enter($, 'h')
  expect(await s.enter($, 'What breaks if we do not?')).toContain('blocked by a UserPromptSubmit hook')
  // The core's discussion record keeps only what reached Claude, and the band says it was not sent.
  expect(s.of('discussion.append').map(c => c['text'])).toEqual([])
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /Not sent: blocked by a UserPromptSubmit hook/)).toBeDefined()
  block = false
  expect(await s.enter($, 'And what if we do?')).toBeUndefined()
  await s.reply($, 'Then it retries.')
  // A rephrasing reads the discussion as Claude had it, without the message that never reached it.
  await s.enter($, 'r')
  await s.clock.advance(1_000)
  expect(asked.some(t => t.includes('And what if we do?'))).toBe(true)
  expect(asked.some(t => t.includes('What breaks'))).toBe(false)
  await s.clock.advance(600_000)
  expect(s.sent.some(t => t.includes('Judge message m1'))).toBe(true)
})

test('a judge message listed while a discussion message is on its way goes before Claude at the next poll once that message is dropped', async ($, on) => {
  // @scenario answer-service: A judging prompt that never reaches the model is put before it again
  let judging = false
  const judge = { message: 'm1', turn: 1, text: 'x', needs_place: false, needs_place_sure: false, places: [], defaults: [], person_question: false }
  const s = session(on, {
    core: {
      poll: () => polled([question('q1', { text: 'First question?' })], judging ? { judge: [judge] } : {}),
      context: () => ({ version: 1, ok: true, context: 'the question' }),
    },
    drop: text => (text.includes('What breaks') ? 'blocked by a UserPromptSubmit hook' : undefined),
  })
  await s.start($)
  await s.enter($, 'h')
  judging = true
  // A poll lands while the hook beneath decides on the message.
  s.onSubmit = async () => {
    s.onSubmit = undefined
    await s.clock.advance(70_000)
    await s.clock.settle()
  }
  await s.enter($, 'What breaks if we do not?')
  expect(s.sent.some(t => t.includes('Judge message m1'))).toBe(false)
  await s.clock.advance(70_000)
  expect(s.sent.some(t => t.includes('Judge message m1'))).toBe(true)
})

test('a draft from a discussion on a question a poll took away is dropped, even after an Enter that stopped', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  // Claude's draft is for q1, still being discussed; it never lands on q2, which took q1's place.
  let polls = 0
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const s = open(on, { poll: () => polled(++polls === 1 ? [q1, q2] : [q2]), context: () => ({ version: 1, ok: true, context: 'the question' }) })
  await s.start($)
  await s.enter($, 'h')
  await s.enter($, 'Help me answer the first question')
  await $.turn.start({ text: s.sent.at(-1) ?? '', turnId: 'turn-q1' })
  await s.clock.advance(70_000)
  expect(await s.enter($, 'No.')).toContain('check the preview first')
  const r = await $.tool.call({ tool: 'mcp__inquisitor-answer-mod__propose_reply', text: 'Answer for the first.' })
  expect(r.deny).toContain('dropped')
  expect(s.filled).not.toContain('Answer for the first.')
  await s.clock.advance(500)
  expect(s.of('post')).toEqual([])
})

test('a draft from a discussion on a question a poll took away is dropped, even after moving away and back', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  // Claude's draft is for q1, still being discussed; it never lands on q2, which took q1's place.
  let polls = 0
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const s = open(on, { poll: () => polled(++polls === 1 ? [q1, q2] : [q2]), context: () => ({ version: 1, ok: true, context: 'the question' }) })
  await s.start($)
  await s.enter($, 'h')
  await s.enter($, 'Help me answer the first question')
  await $.turn.start({ text: s.sent.at(-1) ?? '', turnId: 'turn-q1' })
  await s.clock.advance(70_000)
  await s.enter($, 'n')
  await s.enter($, 'b')
  const r = await $.tool.call({ tool: 'mcp__inquisitor-answer-mod__propose_reply', text: 'Answer for the first.' })
  expect(r.deny).toContain('dropped')
  expect(s.filled).not.toContain('Answer for the first.')
  await s.clock.advance(500)
  expect(s.of('post')).toEqual([])
})

test('an image pasted alone is not posted', async ($, on) => {
  const s = open(on)
  await s.start($)
  expect(await s.enter($, '\n[Image #1]')).toContain('An image cannot be posted')
  expect(s.of('preview')).toEqual([])
  expect(s.of('post')).toEqual([])
})

test('what the core keeps of a question shows: set aside, kept pending, rephrased, and the relay that posts there', async ($, on) => {
  // @scenario answer-service: A question set aside comes after the new ones
  // @scenario answer-service: A refused answer is kept pending
  const s = open(on, {
    'pending.list': () => ({ version: 1, ok: true, answers: [{ question: 'q2', text: 'Yes, exponentially.', why: 'its channel is off' }] }),
  }, [
    question('q1', { text: 'First?', asked_at: '2026-10-20T09:00:00Z', state: 'set-aside' }),
    question('q2', { text: 'Second?', asked_at: '2026-10-20T09:10:00Z', state: 'pending' }),
    question('q3', { text: 'Third?', asked_at: '2026-10-20T09:20:00Z', relay: 'answers-bot', revision: { text: 'Third, rephrased?', summary: 'settled' } }),
  ])
  await s.start($)
  await s.enter($, 'n')
  await s.enter($, 'n')
  await s.enter($, 'n')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /for later/)).toBeDefined()
  expect(await shown(ui, /pending · its channel is off/)).toBeDefined()
  await s.enter($, 'b')
  await ui.redraw()
  expect(await shown(ui, /Third, rephrased\?/)).toBeDefined()
  // An answer to the question as shown carries its rephrasing.
  expect(await s.enter($, 'Yes.')).toContain('check the preview first')
  expect(s.of('preview').at(-1)).toMatchObject({ question: 'q3', revision: { text: 'Third, rephrased?', summary: 'settled' } })
})

test('text typed on the summary does not post to a question clicked to: the first Enter shows the preview', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  const s = open(on, {}, [question('q1', { text: 'First question?' })])
  await s.start($)
  await s.enter($, 'n')
  await typeInBox($, 'An answer')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:0' })
  await typeInBox($, 'An answer.')
  expect(await enterAsTyped($, s, 'An answer.')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
})

test('with the box emptied before Enter reaches the band, as the engine does, an answer still stays with its question', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  // Typed for q1, then a click on q2: the first Enter stops; the second, the person having seen q2, posts there.
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const s = open(on, {}, [q1, q2])
  await s.start($)
  await typeInBox($, 'Answer meant for the first')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:1' })
  expect(await enterAsTyped($, s, 'Answer meant for the first')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
  expect(await enterAsTyped($, s, 'Answer meant for the first')).toBe('Relayed.')
  expect(s.of('preview').at(-1)).toMatchObject({ question: 'q2' })
})

test('with the box emptied before Enter, a poll that takes the question away still stops the first Enter, and the next posts', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  let polls = 0
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const s = open(on, { poll: () => polled(++polls === 1 ? [q1, q2] : [q2]) })
  await s.start($)
  await typeInBox($, 'Answer meant for the first')
  await s.clock.advance(70_000)
  expect(await enterAsTyped($, s, 'Answer meant for the first')).toContain('check the preview first')
  expect(await enterAsTyped($, s, 'Answer meant for the first')).toBe('Relayed.')
})

test('a long answer pasted for one question, shown collapsed in the box, does not post unseen to another after a click', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  // The box shows the paste collapsed; Enter sends it expanded.
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const s = open(on, {}, [q1, q2])
  await s.start($)
  await typeInBox($, '[Pasted text #1 +2 lines]')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:1' })
  expect(await enterAsTyped($, s, 'Line one of a long answer\nline two\nline three')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
})

function change($: Parameters<typeof typeInBox>[0], text: string, kind: string): Promise<unknown> {
  return ($.prompt as unknown as { change(e: unknown): Promise<unknown> }).change({ text, cursor: text.length, origin: { kind } })
}

function twoQuestions(on: Parameters<typeof open>[0]) {
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const s = open(on, {}, [q1, q2])
  return s
}

test('an answer a survey refused, put back after a click, does not post unseen to the question on screen', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  const s = twoQuestions(on)
  await s.start($)
  await typeInBox($, 'Answer meant for the first')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:1' })
  await $.ui.mount({ ...BAND, props: { ...BAND.props, hasSurvey: true }, surface: 'terminal' })
  expect(await enterAsTyped($, s, 'Answer meant for the first')).toContain('survey')
  await change($, 'Answer meant for the first', 'engine')
  await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await enterAsTyped($, s, 'Answer meant for the first')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
})

test('an answer stashed, then restored after a click, stays with the question it was typed for', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  const s = twoQuestions(on)
  await s.start($)
  await typeInBox($, 'Answer meant for the first')
  await change($, '', 'clear')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:1' })
  await change($, 'Answer meant for the first', 'engine')
  expect(await enterAsTyped($, s, 'Answer meant for the first')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
})

test('an answer deleted, then brought back by undo after a click, stays with the question it was typed for', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  const s = twoQuestions(on)
  await s.start($)
  await typeInBox($, 'Answer meant for the first')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:1' })
  await typeInBox($, '')
  await change($, 'Answer meant for the first', 'undo')
  expect(await enterAsTyped($, s, 'Answer meant for the first')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
})

test('a long paste posted, put back collapsed by the engine, is cleared and not posted again to the next question', async ($, on) => {
  const s = twoQuestions(on)
  await s.start($)
  const long = 'Line one of a long answer\nline two\nline three'
  await typeInBox($, '[Pasted text #1 +2 lines]')
  expect(await enterAsTyped($, s, long, '[Pasted text #1 +2 lines]')).toContain('check the preview first')
  expect(await enterAsTyped($, s, long, '[Pasted text #1 +2 lines]')).toBe('Relayed.')
  expect(s.of('post')).toHaveLength(1)
  expect(s.filled.at(-1)).toBe('')
})

test('an answer deleted a key at a time, then brought back whole by one undo after a click, stays with the question it was typed for', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  const s = twoQuestions(on)
  await s.start($)
  await typeInBox($, 'Answer meant for the first')
  await typeInBox($, 'A')
  await typeInBox($, '')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:1' })
  await change($, 'Answer meant for the first', 'undo')
  expect(await enterAsTyped($, s, 'Answer meant for the first')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
})

test('the preview the band draws while the person types does not post: the first Enter shows it, the second posts', async ($, on) => {
  // @scenario answer-service: A preview for another question posts nothing
  const s = open(on)
  await s.start($)
  await typeInBox($, 'Yes, back off.')
  await s.clock.advance(600)
  expect(s.of('preview')).toHaveLength(1)
  expect(await s.enter($, 'Yes, back off.')).toContain('check the preview first: it answers')
  expect(s.of('post')).toEqual([])
  expect(await s.enter($, 'Yes, back off.')).toBe('Relayed.')
})

test('after moving to another question and back, the first Enter only shows it, and the next posts the unchanged preview', async ($, on) => {
  // @scenario answer-service: A preview for another question posts nothing
  const s = twoQuestions(on)
  await s.start($)
  expect(await s.enter($, 'Answer meant for the first')).toContain('check the preview first')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:1' })
  await ui.press({ key: 'dot:0' })
  expect(await s.enter($, 'Answer meant for the first')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
  expect(await s.enter($, 'Answer meant for the first')).toBe('Relayed.')
  expect(s.of('post')).toHaveLength(1)
})

test('a poll that takes away the question whose preview an Enter showed voids it, so the next Enter previews the new one', async ($, on) => {
  // @scenario answer-service: A preview for another question posts nothing
  let polls = 0
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const s = open(on, { poll: () => polled(++polls === 1 ? [q1, q2] : [q2]) })
  await s.start($)
  expect(await s.enter($, 'Answer meant for the first')).toContain('check the preview first')
  await s.clock.advance(70_000)
  expect(await s.enter($, 'Answer meant for the first')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
  expect(s.of('preview').at(-1)).toMatchObject({ question: 'q2' })
})

test('a poll that keeps the question on screen keeps the preview an Enter showed: the next Enter posts', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  const s = open(on)
  await s.start($)
  expect(await s.enter($, 'Yes, back off.')).toContain('check the preview first')
  await s.clock.advance(70_000)
  expect(await s.enter($, 'Yes, back off.')).toBe('Relayed.')
})

test("a stop's notice stays while a click fills the box with what was stopped, and goes once it fills something else", async ($, on) => {
  const s = open(on, { preview: () => ({ version: 1, ok: false, error: 'core down' }) })
  await s.start($)
  expect(await s.enter($, '1')).toBe('Not posted: core down')
  await s.clock.advance(600)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'opt:q1:0' })
  await ui.redraw()
  expect(await shown(ui, /core down/)).toBeDefined()
  await ui.press({ key: 'opt:q1:1' })
  await ui.redraw()
  expect(await shown(ui, /core down/)).toBeUndefined()
})

test('a clarifying question Claude drafts lands in the box while its question is on screen, and is dropped once another is', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  const release: (() => void)[] = []
  const s = twoQuestions(on)
  on('session.model', () => ({ value: 'claude-opus-5-5' }) as never)
  on('model.complete', () => new Promise(r => release.push(() => r({ value: { isAnswered: true, text: 'Which calls do you mean?' } }))) as never)
  await s.start($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await s.enter($, 'h')
  await s.clock.advance(600)
  await s.enter($, 'a')
  await s.clock.advance(600)
  for (let i = 0; i < 50 && !release.length; i++) await s.clock.advance(10)
  release.shift()!()
  await s.clock.advance(10)
  expect(s.filled.at(-1)).toBe('Which calls do you mean?')
  await s.enter($, 'b')
  await s.enter($, 'b')
  await s.enter($, 'h')
  await s.clock.advance(600)
  await s.enter($, 'a')
  await s.clock.advance(600)
  await ui.press({ key: 'dot:1' })
  const before = s.filled.length
  for (let i = 0; i < 50 && !release.length; i++) await s.clock.advance(10)
  release.shift()!()
  await s.clock.advance(10)
  expect(s.filled.slice(before)).not.toContain('Which calls do you mean?')
})

test('a long paste the engine puts back collapsed posts on the next Enter, its notice kept meanwhile', async ($, on) => {
  const s = twoQuestions(on)
  await s.start($)
  const long = 'Line one of a long answer\nline two\nline three'
  await typeInBox($, '[Pasted text #1 +2 lines]')
  expect(await enterAsTyped($, s, long, '[Pasted text #1 +2 lines]')).toContain('check the preview first')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /check the preview first/)).toBeDefined()
  expect(await enterAsTyped($, s, long, '[Pasted text #1 +2 lines]')).toBe('Relayed.')
})

test("a stop's notice goes once the person types something else after the put-back", async ($, on) => {
  const s = twoQuestions(on)
  on('prompt.edit', (_, e) => ({ text: `${e.text.slice(0, e.start)}${e.inputText}${e.text.slice(e.end)}`, cursor: e.start + e.inputText.length }) as never)
  await s.start($)
  expect(await s.enter($, 'Answer A')).toContain('check the preview first')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /check the preview first/)).toBeDefined()
  await ($.prompt as unknown as { edit(e: unknown): Promise<unknown> }).edit({ origin: { kind: 'composer' }, text: 'Answer A', cursor: 8, start: 8, end: 8, inputText: ' and more' })
  await ui.redraw()
  expect(await shown(ui, /check the preview first/)).toBeUndefined()
})

test('an Enter on the closed answer service clears the box as the put-back lands', async ($, on) => {
  const s = twoQuestions(on)
  await s.start($)
  await s.slash($, 'answer')
  await s.clock.settle()
  const fills = s.filled.length
  await s.enter($, 'hello')
  expect(s.filled.slice(fills)).toEqual([''])
})

test('a poll that edits the question on screen voids the preview an Enter showed', async ($, on) => {
  // @scenario answer-service: A preview for another question posts nothing
  let polls = 0
  const s = open(on, { poll: () => polled([question('q1', { text: ++polls === 1 ? AGENT_Q : `${AGENT_Q}\n3. Retry twice` })]) })
  await s.start($)
  expect(await s.enter($, 'Yes, back off.')).toContain('check the preview first')
  const previews = s.of('preview').length
  await s.clock.advance(70_000)
  expect(await s.enter($, 'Yes, back off.')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
  // The core makes a new preview for the question as it now reads.
  expect(s.of('preview').length).toBeGreaterThan(previews)
})

test('setting a question aside tells the core, on the Enter after the one that showed it', async ($, on) => {
  // @scenario answer-service: A question set aside comes after the new ones
  const s = twoQuestions(on)
  await s.start($)
  expect(await s.enter($, 'l')).toContain('just come on screen')
  expect(s.of('set-aside')).toEqual([])
  await s.enter($, 'l')
  expect(s.of('set-aside')).toEqual([expect.objectContaining({ question: 'q1' })])
})

test('a preview that changed since the Enter that showed it is shown again, not posted', async ($, on) => {
  // @scenario answer-service: A preview for another question posts nothing
  let n = 0
  const s = open(on, { preview: req => previewOf(`User says: ${String(req['text'])}`, { record: { place: ++n === 1 ? 'o/api' : 'o/web', visibility: 'private' } }) })
  await s.start($)
  expect(await s.enter($, 'Yes, back off.')).toContain('check the preview first')
  expect(await s.enter($, 'Yes, back off.')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
  expect(await s.enter($, 'Yes, back off.')).toBe('Relayed.')
})

test('an answer that posts in no thread but reaches a run, or a more visible record, is still shown before it goes', async ($, on) => {
  // @scenario answer-service: The preview warns before a record more visible than its thread
  const views = [
    previewOf(null, { record: { place: null, visibility: null, not_recorded: 'category' }, reaches_run: "The answer is also passed to the Igor's run on o/web #4." }),
    previewOf(null, { record: { place: 'o/web', visibility: 'public', more_visible_than: 'the file it came from' }, warnings: ['the record is public'] }),
  ]
  let at = 0
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const s = open(on, { preview: () => views[at]! }, [q1, q2])
  await s.start($)
  expect(await s.enter($, 'Use the flag.')).toContain('check the preview first')
  expect(await s.enter($, 'Use the flag.')).toBe('Relayed.')
  // Settled, the queue has moved on to q2.
  at = 1
  await s.clock.advance(1_000)
  expect(await s.enter($, 'Use the flag.')).toContain('check the preview first')
  expect(s.of('post')).toHaveLength(1)
})

test('an agree that posts nothing goes on one Enter, unless its preview has a warning, a run it reaches or a more visible record', async ($, on) => {
  // @scenario answer-service: A filter 1 reply with a more private record is posted only after a warning
  const recorded = { recorded_in: 'https://github.com/o/priv/blob/main/d.md', quote: 'Back off exponentially.' }
  const views = [
    previewOf(null),
    previewOf(null, { warnings: ['Posting it shows the private record exists.'] }),
    previewOf(null, { reaches_run: "The answer is also passed to the Igor's run on o/web #4." }),
    previewOf(null, { record: { place: 'o/web', visibility: 'public', more_visible_than: 'the file it came from' } }),
  ]
  let at = 0
  const s = open(on, { preview: () => views[at]! }, ['q1', 'q2', 'q3', 'q4'].map((id, i) => question(id, { text: AGENT_Q, asked_at: `2026-10-20T09:0${i}:00Z`, recorded })))
  await s.start($)
  expect(await s.enter($, 'a')).toContain('just come on screen')
  expect(await s.enter($, 'a')).toBe('Posted.')
  for (at = 1; at < views.length; at++) {
    // Each settles onto the next question, so its first Enter only shows that question, with the preview.
    expect(await s.enter($, 'a')).toContain('check the preview first')
    expect(await s.enter($, 'a')).toBe('Posted.')
  }
})

test('the put-back of a set-aside is cleared as it lands, leaving nothing for a second Enter', async ($, on) => {
  // @scenario answer-service: A question set aside comes after the new ones
  const s = twoQuestions(on)
  await s.start($)
  await s.enter($, 'l')
  const fills = s.filled.length
  await s.enter($, 'l')
  expect(s.filled.slice(fills)).toEqual([''])
  expect(s.of('set-aside')).toHaveLength(1)
})

test('an agree on a question a poll has just put on screen only shows it on the first Enter', async ($, on) => {
  // @scenario answer-service: A preview for another question posts nothing
  let polls = 0
  const recorded = { recorded_in: 'https://github.com/o/priv/blob/main/d.md', quote: 'Back off exponentially.' }
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: AGENT_Q, asked_at: '2026-10-20T09:30:00Z', recorded })
  const s = open(on, { poll: () => polled(++polls === 1 ? [q1, q2] : [q2]), preview: () => previewOf(null) })
  await s.start($)
  await s.enter($, 'n')
  await s.enter($, 'b')
  await s.clock.advance(70_000)
  expect(await s.enter($, 'a')).toContain('just come on screen')
  expect(s.of('post')).toEqual([])
  expect(await s.enter($, 'a')).toBe('Posted.')
})

test('a key typed before the put-back lands stays: the put-back fills nothing over it', async ($, on) => {
  const s = twoQuestions(on)
  on('prompt.edit', (_, e) => ({ text: `${e.text.slice(0, e.start)}${e.inputText}${e.text.slice(e.end)}`, cursor: e.start + e.inputText.length }) as never)
  await s.start($)
  const fills = s.filled.length
  s.onDrop = () => ($.prompt as unknown as { edit(e: unknown): Promise<unknown> }).edit({ origin: { kind: 'composer' }, text: '', cursor: 0, start: 0, end: 0, inputText: 'H' })
  await s.enter($, 'n')
  expect(s.filled.slice(fills)).toEqual([])
})

test("a click that fills the box before the put-back lands goes in as it lands, and the stop's notice goes", async ($, on) => {
  const s = open(on)
  await s.start($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  s.onDrop = () => ui.press({ key: 'opt:q1:1' })
  expect(await s.enter($, 'Yes, back off.')).toContain('check the preview first')
  expect(s.filled.at(-1)).toBe('2')
  await ui.redraw()
  expect(await shown(ui, /check the preview first/)).toBeUndefined()
})

test('a long paste after typed words, put back collapsed, is cleared once posted', async ($, on) => {
  const s = twoQuestions(on)
  await s.start($)
  const long = 'See: Line one of a long answer\nline two\nline three'
  expect(await enterAsTyped($, s, long, 'See: [Pasted text #1 +2 lines]')).toContain('check the preview first')
  expect(await enterAsTyped($, s, long, 'See: [Pasted text #1 +2 lines]')).toBe('Relayed.')
  expect(s.filled.at(-1)).toBe('')
})

test('a click on later for a question a poll has just put on screen only shows it', async ($, on) => {
  // @scenario answer-service: A question set aside comes after the new ones
  let polls = 0
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const s = open(on, { poll: () => polled(++polls === 1 ? [q1, q2] : [q2]) })
  await s.start($)
  // An answer whose preview the Enter shows: that Enter has had its look on q1.
  expect(await s.enter($, 'Answer A')).toContain('check the preview first')
  await s.clock.advance(70_000)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'cmd:l' })
  expect(s.of('set-aside')).toEqual([])
  await ui.press({ key: 'cmd:l' })
  expect(s.of('set-aside')).toEqual([expect.objectContaining({ question: 'q2' })])
})

test('after an Enter that did not act, a click on later acts at once', async ($, on) => {
  // @scenario answer-service: A question set aside comes after the new ones
  const s = twoQuestions(on)
  await s.start($)
  expect(await s.enter($, 'z')).toContain('not a command')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'cmd:l' })
  expect(s.of('set-aside')).toEqual([expect.objectContaining({ question: 'q1' })])
})

test('an engine write is taken for the put-back only when its paste markers stand for text in what Enter sent', async () => {
  const isPutBack = (sent: string, back: string) => {
    dropped(sent)
    const due = putBackOf('engine', back)
    leaveBox()
    return due !== undefined
  }
  expect(isPutBack('see abcdefgh', 'see [Pasted text #1 +3 lines]')).toBe(true)
  expect(isPutBack('A1xyz2B', 'A[Pasted text #1]xyz[Pasted text #2]B')).toBe(true)
  // Matching what was sent on one side only.
  expect(isPutBack('see abcdefgh', 'see [Pasted text #1] zz')).toBe(false)
  // No marker: only the very text sent is the put-back.
  expect(isPutBack('hello there, hello', 'hello')).toBe(false)
  // Each marker needs text of its own, in order.
  expect(isPutBack('A1xyzB', 'A[Pasted text #1]xyz[Pasted text #2]B')).toBe(false)
  expect(isPutBack('see ', 'see [Pasted text #1]')).toBe(false)
})

test('a write with several paste markers that is not the put-back is judged at once, however long what Enter sent', async ($, on) => {
  const s = twoQuestions(on)
  await s.start($)
  const long = 'word '.repeat(2_000)
  s.onDrop = () => change($, '[Pasted text #1 +9 lines] [Pasted text #2 +9 lines] [Pasted text #3 +9 lines] X', 'engine')
  const started = Date.now()
  await s.enter($, long)
  expect(Date.now() - started).toBeLessThan(1_000)
})

test('a dictation that mentions a pasted text, landing before the put-back, is not taken for it', async ($, on) => {
  const s = twoQuestions(on)
  await s.start($)
  const fills = s.filled.length
  s.onDrop = () => change($, 'see [Pasted text #3 +4 lines] earlier', 'engine')
  await s.enter($, 'n')
  expect(s.filled.slice(fills)).toEqual([])
})

test('a dictation landing before the put-back stays in the box, and the put-back after it fills nothing', async ($, on) => {
  const s = twoQuestions(on)
  await s.start($)
  const fills = s.filled.length
  // The engine's dictation lands while Enter is handled, before the put-back.
  s.onDrop = () => change($, 'hello', 'engine')
  await s.enter($, 'l')
  expect(s.filled.slice(fills)).toEqual([])
})

test("a recall or a clear after Enter is the person's: nothing fills over it", async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  const s = twoQuestions(on)
  await s.start($)
  expect(await s.enter($, 'Answer A')).toContain('check the preview first')
  await change($, 'an earlier prompt', 'history')
  const fills = s.filled.length
  await s.clock.advance(1_000)
  expect(s.filled.slice(fills)).toEqual([])
  await s.clock.advance(1_000)
  expect(await s.enter($, 'Answer B')).toContain('check the preview first')
  await change($, '', 'clear')
  const fills2 = s.filled.length
  await s.clock.advance(1_000)
  expect(s.filled.slice(fills2)).toEqual([])
})

test('a message to judge that the poll after a held post brings goes before Claude', async ($, on) => {
  // @scenario answer-service: A judging prompt that never reaches the model is put before it again
  let held = false
  const judge = { message: 'm1', turn: 1, text: 'x', needs_place: false, needs_place_sure: false, places: [], defaults: [], person_question: false }
  const s = session(on, {
    core: {
      poll: () => polled([question('q1', { text: 'First question?' })], held ? { judge: [judge] } : {}),
      preview: req => previewOf(`User says: ${String(req['text'] ?? '')}`),
      post: () => ((held = true), { version: 1, ok: true, status: 'held', warnings: [], why: 'a reply arrived' }),
    },
  })
  await s.start($)
  expect(await s.enter($, 'Yes.')).toContain('check the preview first')
  expect(await s.enter($, 'Yes.')).toContain('Read it, then')
  expect(s.sent.some(t => t.includes('Judge message m1'))).toBe(true)
})

test('after a post the core held for a reply, the next Enter posts the same preview', async ($, on) => {
  // @scenario answer-service: A preview for another question posts nothing
  let posts = 0
  const s = open(on, { post: () => (++posts === 1 ? { version: 1, ok: true, status: 'held', warnings: [], why: 'a reply arrived' } : POSTED) })
  await s.start($)
  expect(await s.enter($, 'Yes, back off.')).toContain('check the preview first')
  expect(await s.enter($, 'Yes, back off.')).toContain('Read it, then ⏎ again')
  expect(await s.enter($, 'Yes, back off.')).toBe('Relayed.')
})

test('a click on the question already on screen does not make the next Enter only show it', async ($, on) => {
  // @scenario answer-service: A question set aside comes after the new ones
  const s = twoQuestions(on)
  await s.start($)
  expect(await s.enter($, 'z')).toContain('not a command')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:0' })
  await s.enter($, 'l')
  expect(s.of('set-aside')).toEqual([expect.objectContaining({ question: 'q1' })])
})

test('a key typed as Enter takes the box does not move what was sent to the question on screen', async ($, on) => {
  // @scenario answer-service: An answer stays in its thread
  const q1 = question('q1', { text: 'First question?', asked_at: '2026-10-20T09:00:00Z' })
  const q2 = question('q2', { text: 'Second question?', asked_at: '2026-10-20T09:30:00Z' })
  const s = open(on, {}, [q1, q2])
  await s.start($)
  await typeInBox($, 'Answer meant for the first')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:1' })
  await ($.prompt as unknown as { change(e: unknown): Promise<unknown> }).change({ text: 'x', cursor: 1, origin: { kind: 'clear' } })
  expect(await s.enter($, 'Answer meant for the first')).toContain('check the preview first')
  expect(s.of('post')).toEqual([])
})

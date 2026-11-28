// The judging pump against races: polls, turn-ends, hot reloads and the
// person's Enter overlapping. A fake core reply can be held back while
// other events run.
import { expect, test } from 'claude-code/testing'

import { TYPED, polled, question, session } from './harness'

const A = { message: 'A', turn: 1, text: 'Should retries back off?', needs_place: false, needs_place_sure: false, places: [], defaults: [], person_question: false }
const J1 = { message: 'M', turn: 1, text: 'Should retries back off?', needs_place: false, needs_place_sure: false, places: [], defaults: [], person_question: false }
const J2 = { ...J1, turn: 2, hits: [] }
const ofTurn = (sent: string[], turn: number) => sent.filter(t => t.includes(`Judge message M, turn ${turn}.`))

const Q1 = () => question('q1', { asker: 'person', asked_by: 'maya' })
const ENDED = (next: unknown) => ({ version: 1, ok: true, next, posted: [], notices: [], refused: false })

test('a poll the core answered before turn 1 ended does not put turn 1 before Claude again', async ($, on) => {
  // @scenario answer-service: A judging prompt that never reaches the model is put before it again
  let ended = false
  let release: () => void = () => undefined
  const gate = new Promise<void>(r => (release = r))
  const s = session(on, {
    core: {
      // Until the core takes turn 1's turn-end, its polls still list turn 1.
      poll: () => polled([question('q1', { asker: 'person', asked_by: 'maya' })], { judge: [ended ? J2 : J1] }),
      'judge.turn-end': async req => {
        if (req['turn'] === 1 && !ended) await gate
        if (req['turn'] === 1) ended = true
        return { version: 1, ok: true, next: req['turn'] === 1 ? J2 : null, posted: [], notices: [] }
      },
    },
  })
  await s.start($)
  await $.turn.start({ text: s.sent.at(-1) ?? '', turnId: 'j1' })
  const done = $.turn.complete({ answer: 'judged.', durationMs: 1, isAborted: false, turnId: 'j1', reason: 'answer' })
  // The minute's poll lands while turn 1's turn-end is still with the core.
  await s.clock.advance(60_000)
  release()
  await done
  await s.clock.settle()
  expect(ofTurn(s.sent, 1)).toHaveLength(1)
  expect(ofTurn(s.sent, 2)).toHaveLength(1)
})

test('a hot reload after a judging prompt was submitted, before its turn starts, does not submit it again', async ($, on) => {
  // @scenario answer-service: A judging prompt that never reaches the model is put before it again
  let ended = false
  const s = session(on, {
    core: {
      poll: () => polled([question('q1', { asker: 'person', asked_by: 'maya' })], { judge: ended ? [] : [J1] }),
      'judge.turn-end': req => {
        if (req['turn'] === 1) ended = true
        return { version: 1, ok: true, next: null, posted: [], notices: [] }
      },
    },
  })
  await s.start($)
  expect(ofTurn(s.sent, 1)).toHaveLength(1)
  // The prompt is with the engine and its turn has not started; the reload raises session.start again.
  await s.start($)
  expect(ofTurn(s.sent, 1)).toHaveLength(1)
  // Were a second prompt sent, its turn would be taken for Claude's reply to any discussion message waiting then.
  await $.turn.start({ text: s.sent[0] ?? '', turnId: 'j1' })
  await $.turn.complete({ answer: 'judged.', durationMs: 1, isAborted: false, turnId: 'j1', reason: 'answer' })
  await s.clock.settle()
  expect(s.of('discussion.append').filter(c => c['role'] === 'model' && c['text'] === 'judged.')).toEqual([])
})

test('turn 2, given by the turn-end and listed by a poll as well, goes before Claude once', async ($, on) => {
  // @scenario answer-service: A judging prompt that never reaches the model is put before it again
  let ended = false
  let release: () => void = () => undefined
  const gate = new Promise<void>(r => (release = r))
  const s = session(on, {
    core: {
      poll: () => polled([question('q1', { asker: 'person', asked_by: 'maya' })], { judge: [ended ? J2 : J1] }),
      'judge.turn-end': async req => {
        if (req['turn'] === 1) ended = true
        // The core has taken the turn-end; its reply is slow to reach the mod.
        if (req['turn'] === 1) await gate
        return { version: 1, ok: true, next: req['turn'] === 1 ? J2 : null, posted: [], notices: [] }
      },
    },
  })
  await s.start($)
  await $.turn.start({ text: s.sent.at(-1) ?? '', turnId: 'j1' })
  const done = $.turn.complete({ answer: 'judged.', durationMs: 1, isAborted: false, turnId: 'j1', reason: 'answer' })
  await s.clock.advance(60_000)
  release()
  await done
  await s.clock.settle()
  expect(ofTurn(s.sent, 2)).toHaveLength(1)
})

test('a discussion message is dropped when a poll starts judging while its context is read', async ($, on) => {
  let polls = 0
  let gated = false
  let release: () => void = () => undefined
  const s = session(on, {
    core: {
      poll: () => polled([question('q1', { asker: 'person', asked_by: 'maya' })], { judge: polls++ === 0 ? [] : [J1] }),
      context: async () => {
        if (gated) await new Promise<void>(r => (release = r))
        return { version: 1, ok: true, context: 'the question' }
      },
    },
  })
  await s.start($)
  await s.enter($, 'h')
  gated = true
  const entering = $.prompt.submit({ ...TYPED, text: 'Is this about the API client?' })
  // While the core reads the question's context, the minute's poll puts a message to judge before Claude, whose turn starts.
  await s.clock.advance(60_000)
  expect(ofTurn(s.sent, 1)).toHaveLength(1)
  await $.turn.start({ text: s.sent.at(-1) ?? '', turnId: 'j1' })
  release()
  const r = await entering
  expect(r.drop).toContain('Claude is judging')
  expect(s.sent).not.toContain('Is this about the API client?')
})

test('a judging prompt whose 0 ms timer died at a hot reload is put before Claude once the service restarts', async ($, on) => {
  // @scenario answer-service: A judging prompt that never reaches the model is put before it again
  // The old copy's first 0 ms wait never resolves, as opening.test.tsx models the old copy's timers.
  let first = true
  on('clock.after', { ms: 0 }, async (_, e, next) => {
    if (first) {
      first = false
      return new Promise<never>(() => undefined)
    }
    return next(e)
  })
  const s = session(on, { core: { poll: () => polled([question('q1', { asker: 'person', asked_by: 'maya' })], { judge: [A] }) } })
  await s.start($)
  expect(s.sent).toHaveLength(0)
  await s.start($)
  expect(s.sent.filter(t => t.includes('Judge message A, turn 1.'))).toHaveLength(1)
})

test('a judging turn running across a hot reload still ends with its turn-end', async ($, on) => {
  // @scenario answer-service: A judging prompt that never reaches the model is put before it again
  // A running judging turn keeps its `judging` through the reload.
  const s = session(on, { core: { poll: () => polled([], { judge: [A] }), 'judge.turn-end': () => ({ version: 1, ok: true, next: null, posted: [], notices: [] }) } })
  await s.start($)
  await $.turn.start({ text: s.sent.at(-1) ?? '', turnId: 'j1' })
  await s.start($)
  await $.turn.complete({ answer: 'judged.', durationMs: 1, isAborted: false, turnId: 'j1', reason: 'answer' })
  await s.clock.settle()
  expect(s.of('judge.turn-end')).toHaveLength(1)
  expect(s.sent.filter(t => t.includes('Judge message A, turn 1.'))).toHaveLength(1)
})

test("an old copy's 0 ms timer firing after a hot reload submits nothing more", async ($, on) => {
  // @scenario answer-service: A judging prompt that never reaches the model is put before it again
  // The engine's types say an old copy's `after` runs on until it unloads.
  let held: (() => void) | undefined
  let n = 0
  on('clock.after', { ms: 0 }, async (_, e, next) => {
    if (n++ === 0) await new Promise<void>(r => (held = r))
    return next(e)
  })
  const s = session(on, { core: { poll: () => polled([], { judge: [A] }) } })
  await s.start($)
  await s.start($)
  held?.()
  await s.clock.settle()
  expect(s.sent.filter(t => t.includes('Judge message A, turn 1.'))).toHaveLength(1)
})

test('a poll still running when turn 1 and turn 2 have both ended does not put turn 1 before Claude again', async ($, on) => {
  // @scenario answer-service: A judging prompt that never reaches the model is put before it again
  let ended = 0
  let polls = 0
  let release: () => void = () => undefined
  let began: () => void = () => undefined
  const begun = new Promise<void>(r => (began = r))
  const s = session(on, {
    core: {
      poll: async () => {
        // The core reads its list when the poll starts; the minute's poll is slow to answer.
        const judge = ended === 0 ? [J1] : ended === 1 ? [J2] : []
        if (polls++ === 1) {
          began()
          await new Promise<void>(r => (release = r))
        }
        return polled([Q1()], { judge })
      },
      'judge.turn-end': req => {
        if (ended === 2) return { version: 1, ok: false, error: 'turn 1 of M has ended' }
        ended = req['turn'] === 1 ? 1 : 2
        return ENDED(req['turn'] === 1 ? J2 : null)
      },
    },
  })
  await s.start($)
  const minute = s.clock.advance(60_000)
  await begun
  await s.reply($, 'judged.')
  await s.reply($, 'judged.')
  expect(ofTurn(s.sent, 2)).toHaveLength(1)
  release()
  await minute
  await s.clock.settle()
  expect(ofTurn(s.sent, 1)).toHaveLength(1)
})

test('a judging prompt waiting behind a long turn is not put before Claude a second time', async ($, on) => {
  // @scenario answer-service: A judging prompt that never reaches the model is put before it again
  const s = session(on, { core: { poll: () => polled([Q1()], { judge: [J1] }) } })
  // A turn the person started with a slash command waits on a permission prompt while they are away.
  await $.turn.start({ text: 'Summarise the repository', turnId: 'long' })
  await s.start($)
  for (let i = 0; i < 12; i++) await s.clock.advance(60_000)
  expect(ofTurn(s.sent, 1)).toHaveLength(1)
})

test('a poll during a running discussion turn puts no message before Claude until that turn ends', async ($, on) => {
  // @scenario answer-service: A judging prompt that never reaches the model is put before it again
  let polls = 0
  const s = session(on, {
    core: {
      poll: () => polled([Q1()], { judge: polls++ === 0 ? [] : [J1] }),
      context: () => ({ version: 1, ok: true, context: 'the question' }),
    },
  })
  await s.start($)
  await s.enter($, 'h')
  await $.prompt.submit({ ...TYPED, text: 'Is this about the API client?' })
  await $.turn.start({ text: 'Is this about the API client?', turnId: 'd1' })
  await s.clock.advance(60_000)
  expect(ofTurn(s.sent, 1)).toHaveLength(0)
  await $.turn.complete({ answer: 'It is.', durationMs: 1, isAborted: false, turnId: 'd1', reason: 'answer' })
  await s.clock.advance(60_000)
  expect(ofTurn(s.sent, 1)).toHaveLength(1)
})

test('a discussion message sent while Claude judges is dropped before the question is read', async ($, on) => {
  // @scenario answer-service: A judging prompt that never reaches the model is put before it again
  const s = session(on, {
    core: {
      poll: () => polled([Q1()], { judge: [J1] }),
      context: () => ({ version: 1, ok: false, error: 'the thread could not be read' }),
    },
  })
  await s.start($)
  expect(ofTurn(s.sent, 1)).toHaveLength(1)
  await s.enter($, 'h')
  const r = await $.prompt.submit({ ...TYPED, text: 'Is this about the API client?' })
  expect(r.drop).toContain('Claude is judging')
  expect(s.of('context')).toHaveLength(0)
})

test('a judging prompt whose turn never starts frees Claude after ten minutes, and is put before it again', async ($, on) => {
  // @scenario answer-service: A judging prompt that never reaches the model is put before it again
  const s = session(on, { core: { poll: () => polled([Q1()], { judge: [J1] }) } })
  // The first prompt's result went with an old copy of the mod: it never settles, and its turn never starts.
  let first = true
  s.onSubmit = () => (first ? ((first = false), new Promise<never>(() => undefined)) : Promise.resolve())
  await s.start($)
  for (let i = 0; i < 9; i++) await s.clock.advance(60_000)
  expect(ofTurn(s.sent, 1)).toHaveLength(0)
  for (let i = 0; i < 3; i++) await s.clock.advance(60_000)
  expect(ofTurn(s.sent, 1)).toHaveLength(1)
})

test('a poll still listing a turn the core has since taken does not put it before Claude again', async ($, on) => {
  // @scenario answer-service: A judging prompt that never reaches the model is put before it again
  let ended = false
  let polls = 0
  let release: () => void = () => undefined
  let began: () => void = () => undefined
  const begun = new Promise<void>(r => (began = r))
  const s = session(on, {
    core: {
      poll: async () => {
        const judge = ended ? [] : [J2]
        if (polls++ === 1) {
          began()
          await new Promise<void>(r => (release = r))
        }
        return polled([Q1()], { judge })
      },
      'judge.turn-end': () => {
        ended = true
        return ENDED(null)
      },
    },
  })
  await s.start($)
  const minute = s.clock.advance(60_000)
  await begun
  await s.reply($, 'judged.')
  release()
  await minute
  await s.clock.settle()
  expect(ofTurn(s.sent, 2)).toHaveLength(1)
})

test("a judging prompt's turn starting after its judging was let go is not taken for Claude's reply to a waiting message", async ($, on) => {
  // @scenario answer-service: A judging prompt that never reaches the model is put before it again
  let ended = false
  const s = session(on, {
    core: {
      poll: () => polled([Q1()], { judge: ended ? [] : [J1] }),
      context: () => ({ version: 1, ok: true, context: 'the question' }),
      'judge.turn-end': () => {
        ended = true
        return ENDED(null)
      },
    },
  })
  // The first prompt is slow to reach the model, so after ten minutes the same message is put before it again.
  let first = true
  s.onSubmit = () => (first ? ((first = false), new Promise<never>(() => undefined)) : Promise.resolve())
  await s.start($)
  for (let i = 0; i < 12; i++) await s.clock.advance(60_000)
  const prompt = s.sent.at(-1) ?? ''
  expect(prompt).toContain('Judge message M, turn 1.')
  // The first prompt's turn takes the judging; then the person sends a discussion message.
  await s.reply($, 'judged.', prompt)
  await s.enter($, 'h')
  const said = await $.prompt.submit({ ...TYPED, text: 'Is this about the API client?' })
  expect(said.drop).toBeUndefined()
  // The second prompt's turn starts, its judging already let go.
  await $.turn.start({ text: prompt, turnId: 'stale' })
  await $.turn.complete({ answer: 'judged.', durationMs: 1, isAborted: false, turnId: 'stale', reason: 'answer' })
  await s.clock.settle()
  expect(s.of('discussion.append').filter(c => c['role'] === 'model')).toEqual([])
})

import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

/** A store the test can read back: $.store answered from a Map. */
function memoryStore(on: On, entries: Record<string, unknown> = {}): Map<string, unknown> {
  const map = new Map(Object.entries(entries))
  on('store.get', (_, e) => ({ value: map.get(e.key) }))
  on('store.set', (_, e) => {
    map.set(e.key, JSON.parse(JSON.stringify(e.value)))
    return { value: undefined }
  })
  on('store.delete', (_, e) => {
    map.delete(e.key)
    return { value: undefined }
  })
  on('store.keys', () => ({ value: [...map.keys()] }))
  return map
}

const PANE = {
  plugin: 'answer-session',
  component: 'Pane',
  requestId: 'answer-session',
  props: {
    title: 'Answer session',
    isFocused: false,
    bodyColumns: 120,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 },
    view: {},
  },
} as const

const SURFACES = ['terminal', 'desktop'] as const

const TYPED = { origin: { kind: 'composer' }, wait: false } as const

/**
 * An answer session as `/answer` opens it, with the engine's side stood in
 * for: `open` starts it, `enter` presses Enter on text in the prompt box and
 * returns what the session said it did, `filled` is every text the session put
 * in the box, `sent` every prompt that reached the model, and `clock` the
 * session's mock clock. Like every test
 * hook, these are added before the test's first `$` call.
 */
function answerSession(on: On) {
  let isUp = false
  const filled: string[] = []
  const sent: string[] = []
  const clock = mock.clock(on)
  mock.env(on, {})
  on('command.register', () => ({ value: { command: 'answer' } }))
  on('ui.open', () => {
    isUp = true
    return { value: { isPlaced: true } }
  })
  on('ui.panes', () => ({ value: isUp ? SHOWN : [] }))
  on('prompt.fill', (_, e) => {
    filled.push(e.text)
    return { isFilled: true }
  })
  on('prompt.read', () => ({ value: { text: '', cursor: 0 } }))
  on('prompt.submit', (_, e) => {
    sent.push(e.text)
    return { text: e.text }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  return {
    filled,
    sent,
    clock,
    open: async ($: Engine) => {
      await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
      await $.command.run({ command: 'answer', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } })
    },
    enter: async ($: Engine, text: string) => (await $.prompt.submit({ ...TYPED, text })).drop,
  }
}

type Drawn = { redraw(): Promise<unknown>; find(query: { type?: string; text?: RegExp; key?: string }): Promise<unknown> }

/** Redraws until `query` is on screen: a model call runs on after Enter returns. */
async function waitFor(ui: Drawn, query: { type?: string; text?: RegExp; key?: string }): Promise<unknown> {
  for (let i = 0; i < 50; i++) {
    await ui.redraw()
    const found = await ui.find(query)
    if (found) return found
  }
  return undefined
}

for (const surface of SURFACES) {
  test(`an option's number and Enter relay it and move on (${surface})`, async ($, on) => {
    const s = answerSession(on)
    await s.open($)
    const ui = await $.ui.mount({ ...PANE, surface })
    expect(await ui.find({ type: 'Text', text: /During a run/ })).toBeDefined()
    // A click on an option types its number, as the person would.
    await ui.press({ key: 'opt:igor-216-scope:1' })
    expect(s.filled).toEqual(['2'])

    expect(await s.enter($, '2')).toContain('Relayed to GitHub')
    await ui.redraw()
    // The next new question is Maya's, a person's: a reply, no options.
    expect(await ui.find({ type: 'Text', text: /onboarding flag/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Reply to Maya Ortiz/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Relayed to GitHub/ })).toBeDefined()

    // Back to the first: it now shows what was relayed.
    expect(await s.enter($, 'p')).toBe('Question 1 of 8')
    await ui.redraw()
    expect(await ui.find({ type: 'Text', text: /RELAYED ON GITHUB AS/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /No, show them as input/ })).toBeDefined()
    expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeUndefined()
    expect(s.sent).toEqual([])
    await ui.unmount()
  })
}

test("a person's question is answered by typing; Enter relays the text", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await s.enter($, 'n')
  expect(await s.enter($, 'Ship Friday')).toContain('Relayed to Linear')
  await s.enter($, 'p')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Ship Friday/ })).toBeDefined()
  await ui.unmount()
})

test('deferring and relaying everything ends on the summary', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await s.enter($, 'd')).toContain('Deferred')
  // The rest in queue order: a person's gets words, an agent's its first option.
  for (const text of ['ok', '1', '1', 'ok', '1', 'ok', '1']) expect(await s.enter($, text)).toContain('Relayed')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Nothing new\. 1 deferred\./ })).toBeDefined()
  await s.enter($, 'r')
  await ui.redraw()
  expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeDefined()
  await ui.unmount()
})

test("after Enter the box is left to the engine's put-back, and a citation lands once it is due", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  await s.enter($, 'd')
  await s.clock.advance(1_000)
  // No put-back came: an empty box is left alone.
  expect(s.filled).toEqual([])
  // Walk to jlee's question, which a decision may already answer; c cites it.
  for (let i = 0; i < 8 && !((await s.enter($, 'n')) ?? '').startsWith('Question 5'); i++);
  expect(await s.enter($, 'c')).toContain('citing reply')
  expect(s.filled).toEqual([])
  await s.clock.advance(1_000)
  expect(s.filled).toEqual(["See decision 10 in #216: the run id links to the run's ledger row, which an item number cannot."])
})

test('Enter refuses what the screen cannot take, and sends nothing', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  expect(await s.enter($, '3')).toBe('There is no answer 3.')
  await s.enter($, '1')
  await s.enter($, 'p')
  expect(await s.enter($, 'Changed my mind')).toBe('This question is already relayed.')
  expect(s.sent).toEqual([])
})

test('the pane has no close control of its own: the engine draws one', async ($, on) => {
  memoryStore(on)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ key: 'close' })).toBeUndefined()
  await ui.unmount()
})

test('a session launched with INQUISITOR_ANSWER_SESSION=1 opens the pane by itself', async ($, on) => {
  mock.env(on, { INQUISITOR_ANSWER_SESSION: '1' })
  memoryStore(on)
  const opened: string[] = []
  on('command.register', () => ({ value: { command: 'answer' } }))
  on('ui.open', (_, e) => {
    opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(opened).toEqual(['answer-session'])
})

test('without the variable, the session opens nothing until /answer', async ($, on) => {
  mock.env(on, {})
  memoryStore(on)
  const opened: string[] = []
  on('command.register', () => ({ value: { command: 'answer' } }))
  on('ui.open', (_, e) => {
    opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(opened).toEqual([])
})

const USAGE = { input_tokens: 1, output_tokens: 1, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }
const REPHRASED = {
  question: "Should a worker's search leave out questions-branch files about other projects?",
  context: 'The files stay on the branch.',
  options: [
    { label: 'Yes, leave them out', effect: "Workers see only their own projects' questions." },
    { label: 'No, include them', effect: "Workers also see other projects' questions." },
  ],
  summary: 'Adam wants isolation between projects.',
}

test('talking a question through, then rephrasing it, keeps the queue where it was', async ($, on) => {
  const s = answerSession(on)
  const prompts: string[] = []
  on('session.model', () => ({ value: 'test-model' }))
  on('model.complete', (_, e) => {
    prompts.push(e.prompt)
    const text = /JSON only/.test(e.prompt) ? JSON.stringify(REPHRASED) : 'It asks whether out-of-scope question files are hidden.'
    return { value: { isAnswered: true, text, usage: USAGE } }
  })
  await s.open($)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await s.enter($, 't')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /TALKING IT THROUGH/ })).toBeDefined()
  // The question stays in view above the discussion.
  expect(await ui.find({ type: 'Text', text: /During a run/ })).toBeDefined()

  expect(await s.enter($, 'What is the questions branch?')).toBe('Sent to Claude')
  expect(await waitFor(ui, { type: 'Text', text: /out-of-scope question files are hidden/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /What is the questions branch\?/ })).toBeDefined()
  expect(prompts[0]).toContain('What is the questions branch?')

  await s.enter($, 'r')
  expect(await waitFor(ui, { type: 'Text', text: /Rephrased after your discussion/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /leave out questions-branch files/ })).toBeDefined()
  expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeDefined()
  // Same place in the queue: 1 of 8.
  expect(await ui.find({ type: 'Text', text: /1 of 8/ })).toBeDefined()

  await s.enter($, 'o')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /During a run/ })).toBeDefined()
  await s.enter($, 'o')

  expect(await s.enter($, '1')).toContain('Relayed')
  await s.enter($, 'p')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Logged with the answer in the real skill/ })).toBeDefined()
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test('back without changes keeps the question and its discussion', async ($, on) => {
  const s = answerSession(on)
  on('session.model', () => ({ value: 'test-model' }))
  on('model.complete', () => ({ value: { isAnswered: true, text: 'A reply.', usage: USAGE } }))
  await s.open($)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await s.enter($, 't')
  await s.enter($, 'Why now?')
  expect(await waitFor(ui, { type: 'Text', text: /A reply\./ })).toBeDefined()
  await s.enter($, 'b')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /During a run/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /TALKING IT THROUGH/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /Rephrased/ })).toBeUndefined()
  // Reopening continues where it was.
  await s.enter($, 't')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Why now\?/ })).toBeDefined()
  await ui.unmount()
})

test("a failed model call is shown in place and the discussion stays usable", async ($, on) => {
  const s = answerSession(on)
  on('session.model', () => ({ value: 'test-model' }))
  on('model.complete', () => ({ value: { isAnswered: false, reason: 'empty-reply', usage: USAGE } }))
  await s.open($)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await s.enter($, 't')
  await s.enter($, 'Hello?')
  expect(await waitFor(ui, { type: 'Text', text: /No reply: the reply was empty/ })).toBeDefined()
  expect(await s.enter($, 'Hello again?')).toBe('Sent to Claude')
  await ui.unmount()
})

test('asking the asker: send, wait, the reply arrives, back in the queue', async ($, on) => {
  const s = answerSession(on)
  const clock = s.clock
  const toasts: string[] = []
  on('session.model', () => ({ value: 'test-model' }))
  on('model.complete', () => ({
    value: { isAnswered: true, text: 'Do hidden files stay on the branch?', usage: USAGE },
  }))
  on('ui.toast', (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  await s.open($)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await s.enter($, 't')
  await s.enter($, 'a')
  expect(await waitFor(ui, { type: 'Text', text: /ASK CLAUDE, IN THE THREAD/ })).toBeDefined()
  // The model's draft goes into the empty prompt box, to edit or send, once
  // the engine's put-back of the "a" is due.
  await clock.advance(1_000)
  for (let i = 0; i < 50 && !s.filled.length; i++) await ui.redraw()
  expect(s.filled).toEqual(['Do hidden files stay on the branch?'])
  expect(await s.enter($, 'Do hidden files stay on the branch, or are they removed?')).toContain('Asked claude on GitHub')

  // Nothing blocks: the next new question is up, the first waits.
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Reply to Maya Ortiz/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /1 waiting/ })).toBeDefined()

  await clock.advance(30_000)
  expect(toasts).toEqual(['claude replied: their question is back in the queue.'])
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /1 waiting/ })).toBeUndefined()
  await s.enter($, 'p')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /replied to your question/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /or are they removed\?/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Revised by claude after your question/ })).toBeDefined()
  expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeDefined()
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test('while the pane is up the conversation draws nothing', async ($, on) => {
  memoryStore(on)
  let isUp = false
  on('command.register', () => ({ value: { command: 'answer' } }))
  on('ui.open', () => {
    isUp = true
    return { value: { isPlaced: true } }
  })
  on('ui.close', () => {
    isUp = false
    return { value: undefined }
  })
  on('ui.panes', () => ({
    value: isUp ? [{ id: 'answer-session', title: 'Answer session', isShown: true, isFocused: true, isPlaced: true }] : [],
  }))
  // Stands for the engine's own drawing of each component.
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine</Text>
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

  const NOTICE = {
    plugin: 'answer-session',
    component: 'InfoNotice',
    requestId: 'notice-1',
    props: { text: 'Model: opus', command: null },
    viewport: { columns: 200, rows: 50, isFullscreen: true },
  } as const
  const TURN = {
    plugin: 'answer-session',
    component: 'TurnDuration',
    requestId: 'turn-1',
    props: { word: 'Baked', durationMs: 3000 },
    viewport: { columns: 200, rows: 50, isFullscreen: true },
  } as const

  // Pane closed: the engine draws as usual.
  let notice = await $.ui.mount({ ...NOTICE, surface: 'terminal' })
  expect(await notice.find({ type: 'Text', text: /engine/ })).toBeDefined()
  await notice.unmount()

  await $.command.run({
    command: 'answer',
    args: '',
    origin: { kind: 'composer' },
    presentation: { isFullscreen: true, columns: 200 },
  })
  notice = await $.ui.mount({ ...NOTICE, surface: 'terminal' })
  const turn = await $.ui.mount({ ...TURN, surface: 'terminal' })
  expect(await notice.find({ type: 'Text', text: /engine/ })).toBeUndefined()
  expect(await turn.find({ type: 'Text', text: /engine/ })).toBeUndefined()

  // On the main screen nothing is hidden: its scrollback could not be redrawn.
  const mainScreen = await $.ui.mount({ ...NOTICE, requestId: 'notice-2', viewport: { columns: 200, rows: 50, isFullscreen: false }, surface: 'terminal' })
  expect(await mainScreen.find({ type: 'Text', text: /engine/ })).toBeDefined()
  await mainScreen.unmount()

  await notice.unmount()
  await turn.unmount()
})

test('while the pane is open, Enter acts in the session and nothing reaches the model; slash commands run', async ($, on) => {
  memoryStore(on)
  const s = answerSession(on)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect((await $.prompt.submit({ ...TYPED, text: 'before' })).drop).toBeUndefined()
  await $.command.run({ command: 'answer', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 90 } })
  expect(await s.enter($, 'An answer in my own words')).toContain('Relayed to GitHub')
  expect((await $.prompt.submit({ ...TYPED, text: '/model', command: { name: 'model', args: '' } })).drop).toBeUndefined()
  expect(s.sent).toEqual(['before', '/model'])
})

const INLINE = { ...PANE, props: { ...PANE.props, placement: 'inline' } } as const
const SHOWN = [{ id: 'answer-session', title: 'Answer session', isShown: true, isFocused: true, isPlaced: true }]

test('on the main screen the pane shows no notice and offers no switch', async $ => {
  const ui = await $.ui.mount({ ...INLINE, viewport: { columns: 90, rows: 40, isFullscreen: false }, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /Half the screen/ })).toBeUndefined()
  expect(await ui.find({ key: 'fullscreen' })).toBeUndefined()
  await ui.unmount()
})

test('fullscreen under 110 columns says the pane has half the screen', async $ => {
  const ui = await $.ui.mount({ ...INLINE, viewport: { columns: 90, rows: 40, isFullscreen: true }, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /Half the screen/ })).toBeDefined()
  await ui.unmount()
  const docked = await $.ui.mount({ ...PANE, viewport: { columns: 200, rows: 50, isFullscreen: true }, surface: 'terminal' })
  expect(await docked.find({ type: 'Text', text: /Half the screen/ })).toBeUndefined()
  await docked.unmount()
})

test('after the restart the pane reopens by itself where it was', async ($, on) => {
  mock.clock(on, { now: 1_060_000 })
  mock.env(on, {})
  const store = memoryStore(on, {
    'reopen-after-restart': {
      sessionId: 'S1',
      cwd: '/work',
      at: 1_000_000,
      cursor: 2,
      answers: { 'igor-216-scope': { kind: 'answer', text: 'Yes' } },
      talks: {},
      rephrased: {},
      original: {},
      returned: {},
    },
  })
  const opened: string[] = []
  on('session.id', () => ({ value: 'S1' }))
  on('command.register', () => ({ value: { command: 'answer' } }))
  on('ui.open', (_, e) => {
    opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  await $.session.start({ cwd: '/work', surface: 'terminal', isInteractive: true })
  expect(opened).toEqual(['answer-session'])
  expect(store.has('reopen-after-restart')).toBe(false)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /3 of 8/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /1 relayed/ })).toBeDefined()
  await ui.unmount()
})

test("another session never reopens the pane from a stale record", async ($, on) => {
  mock.clock(on, { now: 9_000_000 })
  mock.env(on, {})
  const store = memoryStore(on, {
    'reopen-after-restart': { sessionId: 'S1', cwd: '/work', at: 1_000_000, cursor: 2, answers: {}, talks: {}, rephrased: {}, original: {}, returned: {} },
  })
  const opened: string[] = []
  on('session.id', () => ({ value: 'S2' }))
  on('command.register', () => ({ value: { command: 'answer' } }))
  on('ui.open', (_, e) => {
    opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  await $.session.start({ cwd: '/work', surface: 'terminal', isInteractive: true })
  expect(opened).toEqual([])
  expect(store.has('reopen-after-restart')).toBe(false)
})

test('typing /tui fullscreen with the pane open keeps the session too; with it closed, nothing', async ($, on) => {
  const store = memoryStore(on)
  mock.clock(on, { now: 5_000 })
  let panes = SHOWN
  on('ui.panes', () => ({ value: panes }))
  on('session.id', () => ({ value: 'S1' }))
  on('session.cwd', () => ({ value: '/work' }))
  on('command.run', { command: 'tui' }, () => ({ text: '' }))
  const typed = {
    command: 'tui',
    args: 'fullscreen',
    origin: { kind: 'composer' },
    presentation: { isFullscreen: false, columns: 160 },
  } as const
  await $.command.run(typed)
  expect((store.get('reopen-after-restart') as { sessionId: string }).sessionId).toBe('S1')
  store.clear()
  panes = []
  await $.command.run(typed)
  expect(store.has('reopen-after-restart')).toBe(false)
})

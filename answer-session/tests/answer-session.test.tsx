import { expect, mock, test } from 'claude-code/testing'
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

for (const surface of SURFACES) {
  test(`choosing an option previews the exact message; relaying it moves on (${surface})`, async $ => {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect(await ui.find({ type: 'Text', text: /During a run/ })).toBeDefined()
    expect(await ui.find({ key: 'send:igor-216-scope' })).toBeUndefined()

    await ui.press({ key: 'opt:igor-216-scope:1' })
    expect(await ui.find({ type: 'Text', text: /No, show them as input/ })).toBeDefined()
    expect(await ui.find({ key: 'send:igor-216-scope' })).toBeDefined()

    await ui.press({ key: 'send:igor-216-scope' })
    // The next new question is Maya's, a person's: a reply field, no options.
    expect(await ui.find({ type: 'Text', text: /onboarding flag/ })).toBeDefined()
    expect(await ui.find({ type: 'Input', key: 'field:eng-412' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Relayed to GitHub/ })).toBeDefined()

    // Back to the first: it now shows what was relayed.
    await ui.press({ key: 'prev' })
    expect(await ui.find({ type: 'Text', text: /Relayed on GitHub as|RELAYED ON GITHUB AS/ })).toBeDefined()
    expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeUndefined()
    await ui.unmount()
  })
}

test("a person's question is answered by typing; Enter relays the text", async $ => {
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'next' })
  await ui.input({ key: 'field:eng-412', text: 'Ship Friday', kind: 'change' })
  expect(await ui.find({ type: 'Text', text: /Ship Friday/ })).toBeDefined()
  expect(await ui.find({ key: 'send:eng-412' })).toBeDefined()
  await ui.input({ key: 'field:eng-412', text: 'Ship Friday' })
  expect(await ui.find({ type: 'Text', text: /Relayed to Linear/ })).toBeDefined()
  await ui.unmount()
})

test('deferring and relaying everything ends on the summary', async $ => {
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'defer:igor-216-scope' })
  expect(await ui.find({ type: 'Text', text: /Deferred/ })).toBeDefined()
  for (const id of ['eng-412', 'igor-216-jlee', 'ops-staging']) {
    // walk to it and answer in words
    for (let i = 0; i < 8 && !(await ui.find({ key: `field:${id}` })); i++) await ui.press({ key: 'next' })
    await ui.input({ key: `field:${id}`, text: 'ok' })
  }
  for (const id of ['igor-216-visibility', 'lore-backoff', 'igor-216-citation-time', 'igor-216-sensitive']) {
    for (let i = 0; i < 9 && !(await ui.find({ key: `opt:${id}:0` })); i++) await ui.press({ key: 'next' })
    await ui.press({ key: `opt:${id}:0` })
    await ui.press({ key: `send:${id}` })
  }
  expect(await ui.find({ type: 'Text', text: /Nothing new\. 1 deferred\./ })).toBeDefined()
  await ui.press({ key: 'review' })
  expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeDefined()
  await ui.unmount()
})

test('x closes the pane (test builds only)', async ($, on) => {
  memoryStore(on)
  const closed: string[] = []
  on('ui.close', (_, e) => {
    closed.push(e.id)
    return { value: undefined }
  })
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'close' })
  expect(closed).toEqual(['answer-session'])
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
  const prompts: string[] = []
  on('session.model', () => ({ value: 'test-model' }))
  on('model.complete', (_, e) => {
    prompts.push(e.prompt)
    const text = /JSON only/.test(e.prompt) ? JSON.stringify(REPHRASED) : 'It asks whether out-of-scope question files are hidden.'
    return { value: { isAnswered: true, text, usage: USAGE } }
  })
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'next' })
  await ui.press({ key: 'prev' })
  await ui.press({ key: 'talk:igor-216-scope:open' })
  expect(await ui.find({ type: 'Text', text: /TALKING IT THROUGH/ })).toBeDefined()
  // The question stays in view above the discussion.
  expect(await ui.find({ type: 'Text', text: /During a run/ })).toBeDefined()

  await ui.input({ key: 'talk:igor-216-scope:0', text: 'What is the questions branch?' })
  expect(await ui.find({ type: 'Text', text: /What is the questions branch\?/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /out-of-scope question files are hidden/ })).toBeDefined()
  expect(prompts[0]).toContain('What is the questions branch?')

  await ui.press({ key: 'rephrase:igor-216-scope' })
  expect(await ui.find({ type: 'Text', text: /Rephrased after your discussion/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /leave out questions-branch files/ })).toBeDefined()
  expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeDefined()
  // Same place in the queue: 1 of 8.
  expect(await ui.find({ type: 'Text', text: /1 of 8/ })).toBeDefined()

  await ui.press({ key: 'orig:igor-216-scope' })
  expect(await ui.find({ type: 'Text', text: /During a run/ })).toBeDefined()
  await ui.press({ key: 'orig:igor-216-scope' })

  await ui.press({ key: 'opt:igor-216-scope:0' })
  expect(await ui.find({ type: 'Text', text: /Logged with the answer in the real skill/ })).toBeDefined()
  await ui.press({ key: 'send:igor-216-scope' })
  expect(await ui.find({ type: 'Input', key: 'field:eng-412' })).toBeDefined()
  await ui.unmount()
})

test('back without changes keeps the question and its discussion', async ($, on) => {
  on('session.model', () => ({ value: 'test-model' }))
  on('model.complete', () => ({ value: { isAnswered: true, text: 'A reply.', usage: USAGE } }))
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'talk:igor-216-scope:open' })
  await ui.input({ key: 'talk:igor-216-scope:0', text: 'Why now?' })
  await ui.press({ key: 'back:igor-216-scope' })
  expect(await ui.find({ type: 'Text', text: /During a run/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Rephrased/ })).toBeUndefined()
  // Reopening continues where it was.
  await ui.press({ key: 'talk:igor-216-scope:open' })
  expect(await ui.find({ type: 'Text', text: /Why now\?/ })).toBeDefined()
  expect(await ui.find({ type: 'Input', key: 'talk:igor-216-scope:2' })).toBeDefined()
  await ui.unmount()
})

test("a failed model call is shown in place and the discussion stays usable", async ($, on) => {
  on('session.model', () => ({ value: 'test-model' }))
  on('model.complete', () => ({ value: { isAnswered: false, reason: 'empty-reply', usage: USAGE } }))
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'talk:igor-216-scope:open' })
  await ui.input({ key: 'talk:igor-216-scope:0', text: 'Hello?' })
  expect(await ui.find({ type: 'Text', text: /No reply: the reply was empty/ })).toBeDefined()
  expect(await ui.find({ type: 'Input', key: 'talk:igor-216-scope:2' })).toBeDefined()
  await ui.unmount()
})

test('asking the asker: send, wait, the reply arrives, back in the queue', async ($, on) => {
  const clock = mock.clock(on)
  const toasts: string[] = []
  on('session.model', () => ({ value: 'test-model' }))
  on('model.complete', () => ({
    value: { isAnswered: true, text: 'Do hidden files stay on the branch?', usage: USAGE },
  }))
  on('ui.toast', (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'talk:igor-216-scope:open' })
  await ui.press({ key: 'ask:igor-216-scope:open' })
  // The model's draft, exactly as it would post.
  expect(await ui.find({ type: 'Text', text: /WILL POST ON GITHUB AS/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Do hidden files stay on the branch\?/ })).toBeDefined()
  await ui.input({ key: 'ask:igor-216-scope', text: 'Do hidden files stay on the branch, or are they removed?', kind: 'change' })
  await ui.press({ key: 'ask-send:igor-216-scope' })

  // Nothing blocks: the next new question is up, the first waits.
  expect(await ui.find({ type: 'Input', key: 'field:eng-412' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /1 waiting/ })).toBeDefined()

  await clock.advance(30_000)
  expect(toasts).toEqual(['claude replied: their question is back in the queue.'])
  expect(await ui.find({ type: 'Text', text: /1 waiting/ })).toBeUndefined()
  await ui.press({ key: 'prev' })
  expect(await ui.find({ type: 'Text', text: /replied to your question/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /or are they removed\?/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Revised by claude after your question/ })).toBeDefined()
  expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeDefined()
  await ui.unmount()
})

test('while the pane is up the conversation draws nothing; after x it draws again', async ($, on) => {
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

  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await pane.press({ key: 'close' })
  await notice.redraw()
  await turn.redraw()
  expect(await notice.find({ type: 'Text', text: /engine/ })).toBeDefined()
  expect(await turn.find({ type: 'Text', text: /engine/ })).toBeDefined()
  await pane.unmount()
  await notice.unmount()
  await turn.unmount()
})

test('the pane says when the layout is not fullscreen', async $ => {
  const ui = await $.ui.mount({ ...PANE, props: { ...PANE.props, placement: 'inline' }, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /Not fullscreen/ })).toBeDefined()
  await ui.unmount()
  const docked = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await docked.find({ type: 'Text', text: /Not fullscreen/ })).toBeUndefined()
  await docked.unmount()
})

const INLINE = { ...PANE, props: { ...PANE.props, placement: 'inline' } } as const
const SHOWN = [{ id: 'answer-session', title: 'Answer session', isShown: true, isFocused: true, isPlaced: true }]

test('f on the main screen runs /tui fullscreen and keeps the session for the restart', async ($, on) => {
  const store = memoryStore(on)
  mock.clock(on, { now: 1_000_000 })
  const ran: string[] = []
  on('command.list', () => ({ value: [{ name: 'tui', description: 'Switch the TUI', source: 'builtin' }] }))
  on('command.run', { command: 'tui' }, (_, e) => {
    ran.push(e.args)
    return { text: '' }
  })
  on('ui.panes', () => ({ value: SHOWN }))
  on('session.id', () => ({ value: 'S1' }))
  on('session.cwd', () => ({ value: '/work' }))
  const ui = await $.ui.mount({ ...INLINE, surface: 'terminal' })
  await ui.press({ key: 'next' })
  await ui.press({ key: 'next' })
  await ui.press({ key: 'fullscreen' })
  expect(ran).toEqual(['fullscreen'])
  const kept = store.get('reopen-after-restart') as { sessionId: string; cwd: string; cursor: number }
  expect(kept.sessionId).toBe('S1')
  expect(kept.cwd).toBe('/work')
  expect(kept.cursor).toBe(2)
  await ui.unmount()
})

test('without a /tui command, f says what to type instead', async ($, on) => {
  memoryStore(on)
  const toasts: string[] = []
  on('command.list', () => ({ value: [] }))
  on('ui.toast', (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  const ui = await $.ui.mount({ ...INLINE, surface: 'terminal' })
  await ui.press({ key: 'fullscreen' })
  expect(toasts[0]).toContain('type /tui fullscreen')
  await ui.unmount()
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

test('closing the pane with x drops the record, so nothing reopens', async ($, on) => {
  const store = memoryStore(on, { 'reopen-after-restart': { sessionId: 'S1' } })
  on('ui.close', () => ({ value: undefined }))
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'close' })
  expect(store.has('reopen-after-restart')).toBe(false)
  await ui.unmount()
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

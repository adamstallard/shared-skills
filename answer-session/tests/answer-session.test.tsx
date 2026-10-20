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

/** The band above the prompt in a fullscreen terminal of 140 × 40, as Claude Code 2.1.305 sizes it. */
const BAND = {
  plugin: 'answer-session',
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isWorking: false,
    maxRows: 15,
    bodyColumns: 135,
    scroll: { offset: 0, bodyRows: 14 },
    view: {},
  },
  viewport: { columns: 140, rows: 40, isFullscreen: true },
} as const

const SURFACES = ['terminal', 'desktop'] as const

const TYPED = { origin: { kind: 'composer' }, wait: false } as const

/** Stands for the engine's own band, which draws nothing here: what the band shows when the session yields it. */
function engineBand(on: On) {
  on('ui.render', { component: 'AbovePrompt' }, ($, e) => {
    const { Box } = $.ui.resolve(e)
    return <Box />
  })
}

/**
 * An answer session as `/answer` opens it, with the engine's side stood in
 * for: `open` starts it, `enter` presses Enter on text in the prompt box and
 * returns what the session said it did (undefined when the prompt went on to
 * the model), `reply` ends the model's turn for the last prompt with an
 * answer, `filled` is every text the session put in the box, `sent` every
 * prompt that reached the model and `contexts` what rode beside each, and
 * `clock` the session's mock clock. Like every test hook, these are added
 * before the test's first `$` call.
 */
function answerSession(on: On) {
  engineBand(on)
  const filled: string[] = []
  const sent: string[] = []
  const contexts: (readonly string[] | undefined)[] = []
  let turns = 0
  const clock = mock.clock(on)
  on('command.register', () => ({ value: { command: 'answer' } }))
  on('prompt.fill', (_, e) => {
    filled.push(e.text)
    return { isFilled: true }
  })
  on('prompt.read', () => ({ value: { text: '', cursor: 0 } }))
  on('prompt.submit', (_, e) => {
    sent.push(e.text)
    contexts.push(e.context)
    return { text: e.text, context: e.context }
  })
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', (_, e) => ({ text: e.answer }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  return {
    filled,
    sent,
    contexts,
    clock,
    reply: async ($: Engine, answer: string, reason: 'answer' | 'aborted' | 'error' = 'answer') => {
      const turnId = `turn-${++turns}`
      await $.turn.start({ text: sent[sent.length - 1] ?? '', turnId })
      await $.turn.complete({ answer, durationMs: 1, isAborted: reason === 'aborted', turnId, reason })
    },
    open: async ($: Engine) => {
      await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
      await slash($, 'answer')
    },
    enter: async ($: Engine, text: string) => (await $.prompt.submit({ ...TYPED, text })).drop,
  }
}

/** Runs a slash command as the person typing it would. */
function slash($: Engine, command: string, args = '') {
  return $.command.run({ command, args, origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 140 } })
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
    const ui = await $.ui.mount({ ...BAND, surface })
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
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
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
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
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

/** Whether the band shows the answer session now. */
async function isShown($: Engine): Promise<boolean> {
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const found = await ui.find({ type: 'Text', text: /^Answer session$/ })
  await ui.unmount()
  return found !== undefined
}

test('a new session shows nothing until /answer', async ($, on) => {
  engineBand(on)
  memoryStore(on)
  on('command.register', () => ({ value: { command: 'answer' } }))
  on('prompt.read', () => ({ value: { text: '', cursor: 0 } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(await isShown($)).toBe(false)
  await slash($, 'answer')
  expect(await isShown($)).toBe(true)
})

test('q, the close button and /answer close the band; /answer opens it again where it was', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  expect(await s.enter($, 'n')).toBe('Question 2 of 8')
  expect(await s.enter($, 'q')).toContain('Answer session closed')
  expect(await isShown($)).toBe(false)
  // Closed, a prompt reaches the model again.
  expect((await $.prompt.submit({ ...TYPED, text: 'hello' })).drop).toBeUndefined()
  expect(s.sent).toEqual(['hello'])

  await slash($, 'answer')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /2 of 8/ })).toBeDefined()
  await ui.press({ key: 'cmd:q' })
  await ui.unmount()
  expect(await isShown($)).toBe(false)
  await slash($, 'answer')
  expect(await isShown($)).toBe(true)
  await slash($, 'answer')
  expect(await isShown($)).toBe(false)
})

test('a click on a dot opens that question; on summary, the summary; a summary row, its question', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:3' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Two lore entries disagree/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /4 of 8/ })).toBeDefined()
  // Enter acts on the question the dot opened.
  expect(await s.enter($, '2')).toContain('Relayed to Discord')
  await ui.press({ key: 'dot:summary' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /7 questions still new/ })).toBeDefined()
  await ui.press({ key: 'sum:lore-backoff' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /RELAYED ON DISCORD AS/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Keep both, narrow the fixed one/ })).toBeDefined()
  await ui.unmount()
})

test('a click on a key-row command does what its letter and Enter do', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'cmd:t' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /TALKING IT THROUGH/ })).toBeDefined()
  await ui.press({ key: 'cmd:b' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /TALKING IT THROUGH/ })).toBeUndefined()
  await ui.press({ key: 'cmd:d' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Reply to Maya Ortiz/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /1 deferred/ })).toBeDefined()
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test('a click on an option puts its number in the box; the Relay button relays it', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ key: 'send:igor-216-scope' })).toBeUndefined()
  await ui.press({ key: 'opt:igor-216-scope:0' })
  expect(s.filled).toEqual(['1'])
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /WILL POST ON GITHUB AS/ })).toBeDefined()
  await ui.press({ key: 'send:igor-216-scope' })
  // Relayed, the number leaves the box, as after Enter.
  expect(s.filled).toEqual(['1', ''])
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Reply to Maya Ortiz/ })).toBeDefined()
  expect(await s.enter($, 'p')).toBe('Question 1 of 8')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Yes, filter them by the role's scope/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /RELAYED ON GITHUB AS/ })).toBeDefined()
  await ui.unmount()
})

test('the source is a link to where the question was asked', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const link = (await ui.find({ type: 'Link' })) as { props?: { href?: string } } | undefined
  expect(link?.props?.href).toBe('https://github.com/adamstallard/igor/pull/216')
  await ui.unmount()
})

test('a short band keeps the question and its options and gives up the detail; a taller one shows it', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  // Fullscreen at 90 × 24: one column, eight rows.
  const short = await $.ui.mount({
    ...BAND,
    props: { ...BAND.props, maxRows: 7, bodyColumns: 85, scroll: { offset: 0, bodyRows: 6 } },
    viewport: { columns: 90, rows: 24, isFullscreen: true },
    surface: 'terminal',
  })
  expect(await short.find({ type: 'Text', text: /During a run/ })).toBeDefined()
  expect(await short.find({ key: 'opt:igor-216-scope:1' })).toBeDefined()
  expect(await short.find({ type: 'Text', text: /A worker never sees/ })).toBeUndefined()
  await short.unmount()
  const tall = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await tall.find({ type: 'Text', text: /A worker never sees/ })).toBeDefined()
  expect(await tall.find({ type: 'Text', text: /The scope filter covers lore entries only/ })).toBeDefined()
  await tall.unmount()
})

test('a survey takes the band, and Enter answers nothing while it is up', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const survey = await $.ui.mount({ ...BAND, props: { ...BAND.props, hasSurvey: true }, surface: 'terminal' })
  expect(await survey.find({ type: 'Text', text: /^Answer session$/ })).toBeUndefined()
  expect(await s.enter($, '1')).toContain('A survey is above the prompt')
  await survey.unmount()
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /1 of 8/ })).toBeDefined()
  expect(await s.enter($, '1')).toContain('Relayed to GitHub')
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test('the conversation above the band is drawn as usual while the session is open', async ($, on) => {
  const s = answerSession(on)
  // Stands for the engine's own drawing of each component.
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine</Text>
  })
  await s.open($)
  const notice = await $.ui.mount({
    plugin: 'answer-session',
    component: 'InfoNotice',
    props: { text: 'Model: opus', command: null },
    viewport: { columns: 140, rows: 40, isFullscreen: true },
    surface: 'terminal',
  })
  expect(await notice.find({ type: 'Text', text: /engine/ })).toBeDefined()
  await notice.unmount()
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

test('a discussion message reaches the model with the question attached; its reply is kept with the question', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await s.enter($, 't')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /TALKING IT THROUGH/ })).toBeDefined()
  // The question stays in view in the band.
  expect(await ui.find({ type: 'Text', text: /During a run/ })).toBeDefined()

  // Not dropped: it goes on to the session's model as a prompt.
  expect(await s.enter($, 'What is the questions branch?')).toBeUndefined()
  expect(s.sent).toEqual(['What is the questions branch?'])
  const context = s.contexts[0]?.join('\n') ?? ''
  expect(context).toContain("During a run, should the inquisitor's first filter hide questions-branch files")
  expect(context).toContain('adamstallard/igor #216')
  expect(context).toContain("1. Yes, filter them by the role's scope (recommended): A worker never sees another project's questions.")
  expect(context).toContain('Related earlier decision: #216 decision 3')
  expect(context).toContain('Do not choose for him')
  expect(context).toContain('Do not post, comment, push or change anything')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Claude is answering above/ })).toBeDefined()
  // Another message waits for the reply.
  expect(await s.enter($, 'And then?')).toContain('Claude is still answering above')

  await s.reply($, 'It is a branch of question files about any project.')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /1 message so far/ })).toBeDefined()
  expect(s.sent).toEqual(['What is the questions branch?'])
  await ui.unmount()
})

test('in a discussion, commands and digits act in the session and never reach the model', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  await s.enter($, 't')
  expect(await s.enter($, 'x')).toContain('x is not a command here')
  expect(await s.enter($, '3')).toBe('There is no answer 3.')
  expect(await s.enter($, 'b')).toBe('Back to the question')
  await s.enter($, 't')
  // A digit chooses that answer and relays it, as on the question.
  expect(await s.enter($, '2')).toContain('Relayed to GitHub')
  // On a person's question a digit chooses nothing.
  await s.enter($, 't')
  expect(await s.enter($, '1')).toContain('this question has none to choose')
  expect(await s.enter($, 'q')).toContain('Answer session closed')
  expect(s.sent).toEqual([])
})

test('rephrasing reads the discussion as it happened in the session, and keeps the queue where it was', async ($, on) => {
  const s = answerSession(on)
  const prompts: string[] = []
  on('session.model', () => ({ value: 'test-model' }))
  on('model.complete', (_, e) => {
    prompts.push(e.prompt)
    return { value: { isAnswered: true, text: JSON.stringify(REPHRASED), usage: USAGE } }
  })
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await s.enter($, 't')
  await s.enter($, 'What is the questions branch?')
  await s.reply($, 'It asks whether out-of-scope question files are hidden.')

  await s.enter($, 'r')
  expect(await waitFor(ui, { type: 'Text', text: /Rephrased after your discussion/ })).toBeDefined()
  expect(prompts[0]).toContain('Adam: What is the questions branch?')
  expect(prompts[0]).toContain('You: It asks whether out-of-scope question files are hidden.')
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
  expect(s.sent).toEqual(['What is the questions branch?'])
  await ui.unmount()
})

test('back without changes keeps the question and its discussion', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await s.enter($, 't')
  await s.enter($, 'Why now?')
  await s.reply($, 'A reply.')
  await s.enter($, 'b')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /During a run/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /TALKING IT THROUGH/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /Rephrased/ })).toBeUndefined()
  // Reopening continues where it was.
  await s.enter($, 't')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /1 message so far/ })).toBeDefined()
  await ui.unmount()
})

test('a turn that ends without a reply is shown in the band and the discussion stays usable', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await s.enter($, 't')
  await s.enter($, 'Hello?')
  await s.reply($, '', 'error')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /No answer \(error\)\. Send again to retry\./ })).toBeDefined()
  expect(await s.enter($, 'Hello again?')).toBeUndefined()
  await s.reply($, '', 'aborted')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Stopped before it answered/ })).toBeDefined()
  expect(s.sent).toEqual(['Hello?', 'Hello again?'])
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
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
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
  expect(await ui.find({ type: 'Text', text: /You asked: Do hidden files stay on the branch/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Revised by claude after your question/ })).toBeDefined()
  expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeDefined()
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test('while the session is open, Enter acts in it and nothing reaches the model; slash commands run', async ($, on) => {
  memoryStore(on)
  const s = answerSession(on)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect((await $.prompt.submit({ ...TYPED, text: 'before' })).drop).toBeUndefined()
  await slash($, 'answer')
  expect(await s.enter($, 'An answer in my own words')).toContain('Relayed to GitHub')
  expect((await $.prompt.submit({ ...TYPED, text: '/model', command: { name: 'model', args: '' } })).drop).toBeUndefined()
  expect(s.sent).toEqual(['before', '/model'])
})

test('after the restart the band reopens by itself where it was', async ($, on) => {
  mock.clock(on, { now: 1_060_000 })
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
  on('session.id', () => ({ value: 'S1' }))
  on('command.register', () => ({ value: { command: 'answer' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  await $.session.start({ cwd: '/work', surface: 'terminal', isInteractive: true })
  expect(store.has('reopen-after-restart')).toBe(false)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /3 of 8/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /1 relayed/ })).toBeDefined()
  await ui.unmount()
})

test("another session never reopens the band from a stale record", async ($, on) => {
  engineBand(on)
  mock.clock(on, { now: 9_000_000 })
  const store = memoryStore(on, {
    'reopen-after-restart': { sessionId: 'S1', cwd: '/work', at: 1_000_000, cursor: 2, answers: {}, talks: {}, rephrased: {}, original: {}, returned: {} },
  })
  on('session.id', () => ({ value: 'S2' }))
  on('command.register', () => ({ value: { command: 'answer' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  await $.session.start({ cwd: '/work', surface: 'terminal', isInteractive: true })
  expect(await isShown($)).toBe(false)
  expect(store.has('reopen-after-restart')).toBe(false)
})

test('typing /tui fullscreen with the session open keeps it too; with it closed, nothing', async ($, on) => {
  const store = memoryStore(on)
  mock.clock(on, { now: 5_000 })
  on('prompt.read', () => ({ value: { text: '', cursor: 0 } }))
  on('session.id', () => ({ value: 'S1' }))
  on('session.cwd', () => ({ value: '/work' }))
  on('command.run', { command: 'tui' }, () => ({ text: '' }))
  const typed = {
    command: 'tui',
    args: 'fullscreen',
    origin: { kind: 'composer' },
    presentation: { isFullscreen: false, columns: 160 },
  } as const
  await slash($, 'answer')
  await $.command.run(typed)
  expect((store.get('reopen-after-restart') as { sessionId: string }).sessionId).toBe('S1')
  store.clear()
  await slash($, 'answer')
  await $.command.run(typed)
  expect(store.has('reopen-after-restart')).toBe(false)
})

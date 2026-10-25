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
    expect(await s.enter($, 'b')).toBe('Question 1 of 17')
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
  await s.enter($, 'b')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Ship Friday/ })).toBeDefined()
  await ui.unmount()
})

test('putting one off for later and relaying the rest ends on the summary', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await s.enter($, 'l')).toContain('comes back after the new ones')
  // The rest in queue order: a person's gets words, an agent's its first
  // option. jlee's was answered for Adam and the last handled for him: the
  // queue passes them by.
  for (const text of ['ok', '1', '1', '1', 'ok', '1']) expect(await s.enter($, text)).toContain('Relayed')
  // Then the ones whose threads hold replies, each read as it comes on
  // screen: a teammate's answer, several replies, a withdrawal, a long reply.
  for (const text of ['1', 'ok', 'ok', 'ok']) {
    await s.clock.advance(1_000)
    expect(await s.enter($, text)).toContain('Relayed')
  }
  // Ben's was answered from another machine: the read marks it, so n moves on.
  await s.clock.advance(1_000)
  expect(await s.enter($, 'ok')).toBe('This question is already relayed: (e)dit your post to change it.')
  await s.enter($, 'n')
  await s.clock.advance(1_000)
  // Sara replies the moment a post is first tried: it stops, and the second Enter relays.
  expect(await s.enter($, 'ok')).toContain('Not posted: Sara Lind replied')
  expect(await s.enter($, 'ok')).toContain('Relayed')
  // The recorded answers shown, not posted: answered in Adam's own words.
  await s.clock.advance(1_000)
  expect(await s.enter($, '2')).toContain('Relayed')
  expect(await s.enter($, '1')).toContain("Logged your answer on adamstallard/lore's questions branch")
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Nothing new\. 1 for later\./ })).toBeDefined()
  await s.enter($, 'r')
  await ui.redraw()
  expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeDefined()
  await ui.unmount()
})

test("after Enter the box is left to the engine's put-back, and a citation lands once it is due", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  await s.enter($, 'l')
  await s.clock.advance(1_000)
  // No put-back came: an empty box is left alone.
  expect(s.filled).toEqual([])
  // Walk to Sam's question, which the runbook may already answer; c cites it.
  for (let i = 0; i < 9 && !((await s.enter($, 'n')) ?? '').startsWith('Question 7'); i++);
  expect(await s.enter($, 'c')).toContain('citing reply')
  expect(s.filled).toEqual([])
  await s.clock.advance(1_000)
  expect(s.filled).toEqual(['The runbook has staging follow prod freezes, so yes: hold staging deploys until the migration finishes.'])
})

test('a relayed answer can be edited: e puts it in the box, Enter updates the post, k keeps it', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await s.enter($, '1')
  await s.enter($, 'b')
  expect(await s.enter($, 'e')).toContain('Your post is in the prompt box')
  await s.clock.advance(1_000)
  expect(s.filled).toEqual(["Yes, filter them by the role's scope"])
  expect(await s.enter($, "Yes, filter them by the role's scope")).toContain('That is what it says now')
  expect(await s.enter($, 'Yes, and the same for miss files')).toBe('Edited your post on GitHub adamstallard/igor #216')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /the same for miss files/ })).toBeDefined()
  expect(await ui.find({ type: 'Link', text: /edited · view/ })).toBeDefined()
  // Keeping it as posted leaves the post alone.
  await s.enter($, 'e')
  expect(await s.enter($, 'k')).toBe('Kept as posted')
  expect(await s.enter($, 'Something else')).toContain('already relayed')
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test("asked to draft the reply, the model's draft lands in the prompt box on the question, and Enter relays it", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await s.enter($, 'n')
  // Maya's question has no suggested answers: help me answer.
  expect(await s.enter($, 't')).toContain('t is not a command here')
  expect(await s.enter($, 'h')).toBe('Talking to Claude')
  await s.enter($, 'Write my reply: yes to Friday, 10% of new sign-ups only')
  expect(s.contexts[0]?.join('\n')).toContain('mcp__answer-session__propose_reply')
  const called = await $.tool.call({ tool: 'mcp__answer-session__propose_reply', text: 'Yes, ship Friday to 10% of new sign-ups.' })
  expect(JSON.stringify(called)).toContain("The draft is in Adam's prompt box")
  await s.clock.advance(1_000)
  expect(s.filled).toContain('Yes, ship Friday to 10% of new sign-ups.')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /TALKING TO CLAUDE/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /Claude drafted a reply/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /POST ON LINEAR AS/ })).toBeDefined()
  // Nothing posts until Enter; Enter relays what the box holds, edited or not.
  expect(await s.enter($, 'Yes, ship Friday to 10% of new sign-ups.')).toContain('Relayed to Linear')
  await ui.unmount()
})

test('while editing a post, Claude can draft the new version; Enter updates the post', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await s.enter($, '1')
  await s.enter($, 'b')
  await s.enter($, 'e')
  await s.clock.advance(1_000)
  expect(await s.enter($, 'h')).toBe('Talking to Claude')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /for your edit/ })).toBeDefined()
  // Rewording and asking the asker belong before an answer, not during an edit.
  expect(await ui.find({ key: 'cmd:r' })).toBeUndefined()
  expect(await ui.find({ key: 'cmd:a' })).toBeUndefined()
  await s.enter($, 'Draft a version that covers miss files too')
  expect(s.contexts[0]?.join('\n')).toContain("is editing that post, which now says: \"Yes, filter them by the role's scope\"")
  await $.tool.call({ tool: 'mcp__answer-session__propose_reply', text: 'Yes: filter question and miss files by the role scope.' })
  await s.clock.advance(1_000)
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Claude drafted the edit/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /EDIT ON GITHUB AS/ })).toBeDefined()
  expect(await s.enter($, 'Yes: filter question and miss files by the role scope.')).toBe('Edited your post on GitHub adamstallard/igor #216')
  expect(s.sent).toEqual(['Draft a version that covers miss files too'])
  await ui.unmount()
})

test('Enter refuses what the screen cannot take, and sends nothing', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  expect(await s.enter($, '3')).toBe('There is no answer 3.')
  await s.enter($, '1')
  await s.enter($, 'b')
  expect(await s.enter($, 'Changed my mind')).toBe('This question is already relayed: (e)dit your post to change it.')
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
  expect(await s.enter($, 'n')).toBe('Question 2 of 17')
  expect(await s.enter($, 'q')).toContain('Answer session closed')
  expect(await isShown($)).toBe(false)
  // Closed, a prompt reaches the model again.
  expect((await $.prompt.submit({ ...TYPED, text: 'hello' })).drop).toBeUndefined()
  expect(s.sent).toEqual(['hello'])

  await slash($, 'answer')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /2 of 17/ })).toBeDefined()
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
  expect(await ui.find({ type: 'Text', text: /4 of 17/ })).toBeDefined()
  // Enter acts on the question the dot opened.
  expect(await s.enter($, '2')).toContain('Relayed to Discord')
  await ui.press({ key: 'dot:summary' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /14 questions still new/ })).toBeDefined()
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
  expect(await ui.find({ type: 'Text', text: /TALKING TO CLAUDE/ })).toBeDefined()
  await ui.press({ key: 'cmd:b' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /TALKING TO CLAUDE/ })).toBeUndefined()
  await ui.press({ key: 'cmd:l' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Reply to Maya Ortiz/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /1 for later/ })).toBeDefined()
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test('a click on an option puts its number in the box; Enter relays it', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ key: 'send:igor-216-scope' })).toBeUndefined()
  await ui.press({ key: 'opt:igor-216-scope:0' })
  expect(s.filled).toEqual(['1'])
  await ui.redraw()
  // The number is in the box: the post previews on one line; no Relay button, Enter relays.
  expect(await ui.find({ type: 'Text', text: /POST ON GITHUB AS/ })).toBeDefined()
  expect(await ui.find({ key: 'send:igor-216-scope' })).toBeUndefined()
  expect(await s.enter($, '1')).toContain('Relayed to GitHub')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Reply to Maya Ortiz/ })).toBeDefined()
  expect(await s.enter($, 'b')).toBe('Question 1 of 17')
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
  expect(await ui.find({ type: 'Text', text: /1 of 17/ })).toBeDefined()
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
  expect(await ui.find({ type: 'Text', text: /TALKING TO CLAUDE/ })).toBeDefined()
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
  // With a reply in, the question can be reworded from the talk.
  expect(await ui.find({ key: 'cmd:r' })).toBeDefined()
  expect(s.sent).toEqual(['What is the questions branch?'])
  await ui.unmount()
})

test('in a discussion, commands act in the session, digits send you back, and nothing reaches the model', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  await s.enter($, 't')
  expect(await s.enter($, 'x')).toContain('x is not a command here')
  // The choices are on the question: a digit here says to go back.
  expect(await s.enter($, '2')).toContain('go (b)ack to the question')
  // Typing keeps the conversation going: no key for it.
  expect(await s.enter($, 't')).toContain('t is not a command here')
  expect(await s.enter($, 'b')).toBe('Back to the question')
  expect(await s.enter($, '2')).toContain('Relayed to GitHub')
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
  // Same place in the queue: 1 of 17.
  expect(await ui.find({ type: 'Text', text: /1 of 17/ })).toBeDefined()

  await s.enter($, 'o')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /During a run/ })).toBeDefined()
  await s.enter($, 'o')

  expect(await s.enter($, '1')).toContain('Relayed')
  await s.enter($, 'b')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Logged with the answer in the real skill/ })).toBeDefined()
  expect(s.sent).toEqual(['What is the questions branch?'])
  await ui.unmount()
})

test('back to the question keeps the question and its discussion', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await s.enter($, 't')
  await s.enter($, 'Why now?')
  await s.reply($, 'A reply.')
  await s.enter($, 'b')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /During a run/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /TALKING TO CLAUDE/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /Rephrased/ })).toBeUndefined()
  // Reopening continues where it was.
  await s.enter($, 't')
  await ui.redraw()
  expect(await ui.find({ key: 'cmd:r' })).toBeDefined()
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
  await s.enter($, 'b')
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
  expect(await ui.find({ type: 'Text', text: /3 of 17/ })).toBeDefined()
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

test("(w)on't answer offers three reasons; going back cancels; reason 1 records it, posts nothing and moves on", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await s.enter($, 'w')).toContain('choose why')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /WON'T ANSWER · CHOOSE WHY/ })).toBeDefined()
  for (const why of [/The conversation is over/, /^Not a question$/, /The inquisitor should have handled it/]) expect(await ui.find({ type: 'Text', text: why })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Not a real question/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /The real skill ends the thread: later replies there stop/ })).toBeDefined()
  // Before a reason is chosen, nothing is recorded: going back keeps it open.
  expect(await s.enter($, 'b')).toBe("Kept claude's question open: nothing recorded")
  await ui.redraw()
  expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /1 of 17/ })).toBeDefined()

  await s.enter($, 'w')
  await s.clock.advance(1_000)
  await ui.redraw()
  // A click on a reason types its number, as an option's does.
  await ui.press({ key: 'why:1' })
  expect(s.filled).toEqual(['1'])
  expect(await s.enter($, '4')).toContain('Choose why, 1 to 3')
  expect(await s.enter($, '1')).toBe("Won't answer claude's question: the conversation is over. Nothing posted.")
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Reply to Maya Ortiz/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /1 won't answer/ })).toBeDefined()
  expect(await s.enter($, 'b')).toBe('Question 1 of 17')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /the thread is ended/ })).toBeDefined()
  expect(await ui.find({ key: 'cmd:r' })).toBeDefined()
  expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeUndefined()
  expect(await s.enter($, 'An answer after all')).toContain("You won't answer this question")
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test('reason 2, not a question, notes a lesson candidate against how it was found; (r)eopen makes it answerable again', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await s.enter($, 'w')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /picked up by mistake/ })).toBeDefined()
  expect(await s.enter($, '2')).toBe("Won't answer claude's question: not a question. Nothing posted.")
  await s.enter($, 'b')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /^Not a question$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /a lesson candidate is written against how the/ })).toBeDefined()
  await ui.press({ key: 'dot:summary' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /│ won't answer: not a question/ })).toBeDefined()
  await ui.press({ key: 'dot:0' })
  expect(await s.enter($, 'r')).toBe("Reopened claude's question: the real skill withdraws the lesson candidate")
  await ui.redraw()
  expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeDefined()
  expect(await ui.find({ key: 'cmd:w' })).toBeDefined()
  expect(await s.enter($, '1')).toContain('Relayed to GitHub')
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test('reason 3 asks which filter should have stopped it; filter 4 previews the fixed reply, a note goes in the miss, Enter posts and closes it as handled', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await s.enter($, 'w')
  expect(await s.enter($, '3')).toContain('choose the filter that should have stopped it')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /WHICH FILTER SHOULD HAVE STOPPED IT/ })).toBeDefined()
  for (const name of [/^Already answered$/, /^Can wait$/, /^Only one option has merit$/, /^Cheap to reverse$/]) expect(await ui.find({ type: 'Text', text: name })).toBeDefined()
  expect(await ui.find({ key: 'cmd:b' })).toBeDefined()
  // Nothing went to the model: the band asks, not Claude.
  expect(s.sent).toEqual([])
  await s.clock.advance(1_000)
  await ui.press({ key: 'filter:4' })
  expect(s.filled).toEqual(['4'])
  expect(await s.enter($, '5')).toContain('1 to 4')
  expect(await s.enter($, '4')).toBe("Filter 4, cheap to reverse: check the reply, then ⏎ posts it")
  await ui.redraw()
  // Exactly what will post: the handled-for-you path's fixed text for filter 4.
  expect(await ui.find({ type: 'Text', text: /ANSWER FOR THE INQUISITOR/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^POST ON GITHUB AS$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Inquisitor: $/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Inquisitor: Filter 4 \(cheap to$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /logs a miss against filter 4/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /You can still/ })).toBeDefined()
  expect(await ui.find({ key: 'cmd:p' })).toBeDefined()

  const said = 'Isolation is decision 3, so either was cheap to switch'
  expect(await s.enter($, said)).toBe(
    "Answered claude's question for the inquisitor on GitHub adamstallard/igor #216 as adam-relay[bot]. The real skill logs a miss against filter 4, with your note: " + said,
  )
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Reply to Maya Ortiz/ })).toBeDefined()
  expect(await s.enter($, 'b')).toBe('Question 1 of 17')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /HANDLED BY YOUR CHOICE ON GITHUB AS/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /handled by your choice/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^The real skill logs a miss against filter 4 \(cheap to reverse\), with/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /│ Isolation is decision 3/ })).toBeDefined()
  // Closed: no options, no won't answer; the reply can be edited.
  expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeUndefined()
  expect(await ui.find({ key: 'cmd:w' })).toBeUndefined()
  expect(await ui.find({ key: 'cmd:e' })).toBeDefined()
  expect(await s.enter($, 'An answer after all')).toBe('You answered this for the inquisitor: (e)dit the reply to change it.')
  await ui.press({ key: 'dot:summary' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /1 you answered for the inquisitor/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /│ you chose · Inquisitor: Filter 4 \(cheap to reverse\)/ })).toBeDefined()
  expect(s.sent).toEqual([])
  await ui.unmount()
})

const FILTER_NAMES = { 2: 'can wait', 3: 'only one option has merit' } as const
// Filter 2 on Maya's question (a person's), filter 3 on the first (an agent's).
for (const [filter, at] of [
  [2, 1],
  [3, 0],
] as const) {
  test(`reason 3 with filter ${filter} posts its fixed Inquisitor reply, on a person's question as on an agent's; (p)ost needs no note`, async ($, on) => {
    const s = answerSession(on)
    await s.open($)
    const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
    if (at) await ui.press({ key: `dot:${at}` })
    await s.enter($, 'w')
    await s.enter($, '3')
    await s.enter($, String(filter))
    // A click on (p)ost only types it.
    await s.clock.advance(1_000)
    await ui.press({ key: 'cmd:p' })
    expect(s.filled).toEqual(['p'])
    expect(await s.enter($, 'p')).toContain(`a miss against filter ${filter}.`)
    await ui.press({ key: 'dot:summary' })
    await ui.redraw()
    expect(await ui.find({ type: 'Text', text: new RegExp(`│ you chose · Inquisitor: Filter ${filter} \\(${FILTER_NAMES[filter]}\\)`) })).toBeDefined()
    await ui.press({ key: `dot:${at}` })
    await ui.redraw()
    expect(await ui.find({ type: 'Text', text: /HANDLED BY YOUR CHOICE ON/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: new RegExp(`^The real skill logs a miss against filter ${filter} \\(`) })).toBeDefined()
    expect(s.sent).toEqual([])
    await ui.unmount()
  })
}

test("filter 1 without a place can't post; with one it previews a Recorded answer naming it, and back steps through the stages", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await s.enter($, 'w')
  await s.enter($, '3')
  expect(await s.enter($, '1')).toBe('Filter 1, already answered: give where the answer is recorded')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Where is the answer recorded\?/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Recorded answer: $/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Without a place it can't post as filter 1/ })).toBeDefined()
  expect(await ui.find({ key: 'cmd:t' })).toBeDefined()
  // Nothing typed: nothing can post, and (p)ost is not offered here.
  expect(await ui.find({ key: 'cmd:p' })).toBeUndefined()
  expect(await s.enter($, 'p')).toContain('p is not a command here')
  expect(await s.enter($, '')).toBe("Type or paste where the answer is recorded: without it, it can't post as filter 1.")
  // Back steps back: to the filters, then the question stays open.
  expect(await s.enter($, 'b')).toBe('Back to the filters')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /WHICH FILTER SHOULD HAVE STOPPED IT/ })).toBeDefined()
  expect(await s.enter($, 'b')).toBe("Kept claude's question open: nothing recorded")
  await ui.redraw()
  expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeDefined()

  await s.enter($, 'w')
  await s.enter($, '3')
  await s.enter($, '1')
  const place = '#216 decision 3: scope is a hard filter'
  expect(await s.enter($, place)).toContain(`Recorded answer: ${place}`)
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /^Recorded answer: $/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /#216 decision 3/ })).toBeDefined()
  // Back from the preview puts the place in the box again, to change.
  await s.clock.advance(1_000)
  expect(await s.enter($, 'b')).toBe('Back to where the answer is recorded')
  await s.clock.advance(1_000)
  expect(s.filled).toContain(place)
  await s.enter($, place)
  expect(await s.enter($, 'p')).toContain('a miss against filter 1.')
  await ui.press({ key: 'dot:0' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /HANDLED BY YOUR CHOICE ON GITHUB AS/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Recorded answer: $/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^The real skill logs a miss against filter 1 \(already answered\)\.$/ })).toBeDefined()
  await ui.press({ key: 'dot:summary' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /│ you chose · Recorded answer: #216 decision 3/ })).toBeDefined()
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test("for filter 1, Claude can help find where it is recorded and fill the place in; it posts only on Adam's Enter", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  // Maya's question has no options: help me answer.
  await s.enter($, 'n')
  await s.enter($, 'w')
  await s.enter($, '3')
  await s.enter($, '1')
  expect(await s.enter($, 'h')).toBe('Talking to Claude')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /about where the answer is recorded/ })).toBeDefined()
  // Rewording and asking the asker are not offered here.
  expect(await ui.find({ key: 'cmd:r' })).toBeUndefined()
  expect(await ui.find({ key: 'cmd:a' })).toBeUndefined()
  expect(await s.enter($, 'Where did we decide this?')).toBeUndefined()
  expect(s.sent).toEqual(['Where did we decide this?'])
  const context = s.contexts[0]?.join('\n') ?? ''
  expect(context).toContain("filter 1 (already answered) should have stopped it")
  expect(context).toContain('mcp__answer-session__propose_reply')
  expect(context).toContain('Can we ship the onboarding flag')
  await s.reply($, 'The rollout runbook says flags under 25% need no review.')
  const called = await $.tool.call({ tool: 'mcp__answer-session__propose_reply', text: 'Recorded answer: the rollout runbook, flags under 25% need no review' })
  expect(JSON.stringify(called)).toContain("The place is in Adam's prompt box")
  await s.clock.advance(1_000)
  expect(s.filled).toContain('the rollout runbook, flags under 25% need no review')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /TALKING TO CLAUDE/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /Claude filled in where it is recorded/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Where is the answer recorded\?/ })).toBeDefined()
  // Nothing was posted yet; Enter takes the place, Enter again posts.
  expect(await ui.find({ type: 'Text', text: /2 of 17/ })).toBeDefined()
  await s.enter($, 'the rollout runbook, flags under 25% need no review')
  expect(await s.enter($, 'p')).toContain("Answered Maya Ortiz's question for the inquisitor on Linear")
  expect(s.sent).toEqual(['Where did we decide this?'])
  await ui.unmount()
})

test('answering for the inquisitor posts nothing before Enter: clicks only type, and going back at any stage records nothing', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const unchanged = async () => {
    await ui.press({ key: 'dot:summary' })
    await ui.redraw()
    const same = await ui.find({ type: 'Text', text: /0 of 17 relayed this session · 1 answered for you · 1 handled for you$/ })
    await ui.press({ key: 'dot:0' })
    return same
  }
  await s.enter($, 'w')
  await ui.press({ key: 'why:3' })
  await s.enter($, '3')
  for (const n of [1, 2, 3, 4]) await ui.press({ key: `filter:${n}` })
  await s.enter($, '2')
  await s.clock.advance(1_000)
  await ui.press({ key: 'cmd:p' })
  await ui.redraw()
  // Still previewing: a click on (p)ost put p in the box, and Enter did not come.
  expect(await ui.find({ type: 'Text', text: /ANSWER FOR THE INQUISITOR/ })).toBeDefined()
  expect(s.filled.slice(-1)).toEqual(['p'])
  // Back from the preview: to the filters, then the question stays open.
  expect(await s.enter($, 'b')).toBe('Back to the filters')
  expect(await s.enter($, 'b')).toBe("Kept claude's question open: nothing recorded")
  expect(await unchanged()).toBeDefined()
  // Moving to another question drops it too.
  await s.enter($, 'w')
  await s.enter($, '3')
  await s.enter($, '4')
  await ui.press({ key: 'dot:2' })
  await ui.press({ key: 'dot:0' })
  await ui.redraw()
  expect(await ui.find({ key: 'opt:igor-216-scope:0' })).toBeDefined()
  expect(await unchanged()).toBeDefined()
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test("jlee's question arrives answered for Adam from the record; it is listed, and e edits it into his own post", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /1 answered and 1 handled for you: see the summary/ })).toBeDefined()
  await ui.press({ key: 'dot:4' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /ANSWERED FOR YOU ON GITHUB AS/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Recorded answer: $/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Filter 1 found a recorded answer with authority/ })).toBeDefined()
  expect(await ui.find({ key: 'cmd:w' })).toBeUndefined()
  expect(await s.enter($, 'Another answer')).toBe('This question was answered for you: (e)dit the post to change it.')

  expect(await s.enter($, 'e')).toBe("The session's post is in the prompt box: change it, then ⏎")
  await s.clock.advance(1_000)
  expect(s.filled).toEqual(["See decision 10 in #216: the run id links to the run's ledger row, which an item number cannot."])
  expect(await s.enter($, 'See decision 10 in #216; the ledger row is public.')).toBe('Edited the post on GitHub adamstallard/igor #216')
  await ui.redraw()
  // Edited, it is Adam's: "User says: ".
  expect(await ui.find({ type: 'Link', text: /edited · view/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^User says: $/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Filter 1 found/ })).toBeUndefined()

  await ui.press({ key: 'dot:summary' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /1 answered for you · 1 handled for you/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /│ User says: See decision 10 in #216; the ledger row is public\./ })).toBeDefined()
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test("an agent's question that clearly fails filter 4 is handled for Adam; he can edit the reply or still answer it himself", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:8' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /HANDLED FOR YOU ON DISCORD AS/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Inquisitor: $/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Filter 4 \(cheap to reverse\): pick one, it's cheap to/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /the real skill logs a miss/ })).toBeDefined()
  expect(await ui.find({ key: 'cmd:e' })).toBeDefined()

  // Edit the session's reply.
  expect(await s.enter($, 'e')).toBe("The session's post is in the prompt box: change it, then ⏎")
  expect(await s.enter($, 'Debug, please.')).toBe('Edited the post on Discord #igor-dev')
  // Or answer it properly: Adam's own post follows the session's.
  await ui.redraw()
  expect(await ui.find({ key: 'opt:sync-log-level:1' })).toBeDefined()
  expect(await s.enter($, '2')).toContain('Relayed to Discord')
  await ui.press({ key: 'dot:8' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /RELAYED ON DISCORD AS/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /After the session's own reply: User says: Debug, please\./ })).toBeDefined()
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test("a person's question only shows a suggested verdict; agreeing is a key and Enter, and a click only types it", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await s.enter($, 'n')
  // The engine's put-back of the n is due first.
  await s.clock.advance(1_000)
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /Looks cheap to reverse/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /HANDLED FOR YOU/ })).toBeUndefined()
  // A click on (a)gree, in the key row or beside the verdict, puts a in the box and posts nothing.
  await ui.press({ key: 'cmd:a' })
  await ui.press({ key: 'verdict' })
  expect(s.filled).toEqual(['a', 'a'])
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /2 of 17/ })).toBeDefined()
  expect(await s.enter($, 'a')).toBe('Relayed to Linear ENG-412 · Onboarding flag as adam-relay (Linear app)')
  await s.enter($, 'b')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /^User says: $/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Your call: either way is cheap to switch/ })).toBeDefined()
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test("nothing posts or reaches the model without Enter, but the session's own two prefixes", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ids = ['igor-216-scope', 'eng-412', 'igor-216-visibility', 'lore-backoff', 'igor-216-jlee', 'igor-216-citation-time', 'ops-staging', 'igor-216-sensitive', 'sync-log-level']
  // Every click on every question: the dots, the options, the verdict, the
  // citation, won't-answer and its reasons, then back.
  for (const [i, id] of ids.entries()) {
    for (const key of [`dot:${i}`, `opt:${id}:0`, 'verdict', 'cmd:a', 'cite', 'cmd:c', 'cmd:w', 'why:1', 'why:2', 'why:3', 'filter:1', 'filter:4', 'cmd:p', 'cmd:b']) {
      await ui.redraw()
      if (await ui.find({ key })) await ui.press({ key })
    }
  }
  await ui.press({ key: 'dot:summary' })
  await ui.redraw()
  // Posted: only what the session did itself, under its own two prefixes.
  expect(await ui.find({ type: 'Text', text: /0 of 17 relayed this session · 1 answered for you · 1 handled for you$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /│ Recorded answer: See decision 10 in #216/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /│ Inquisitor: Filter 4 \(cheap to reverse\)/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /User says:/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /15 questions still new/ })).toBeDefined()
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test("while the session is open the engine's prompt guesses stay out of the box, and only the main loop can draft", async ($, on) => {
  const s = answerSession(on)
  on('prompt.suggest', () => ({ isShown: true }))
  expect((await $.prompt.suggest({ text: 'next question', origin: { kind: 'suggestion' } })).isShown).toBe(true)
  await s.open($)
  expect((await $.prompt.suggest({ text: 'next question', origin: { kind: 'suggestion' } })).isShown).toBe(false)
  await s.enter($, 'n')
  await s.enter($, 'h')
  const forked = await $.tool.call({ tool: 'mcp__answer-session__propose_reply', text: 'next question', agentId: 'fork-1' })
  expect(JSON.stringify(forked)).toContain('Only the main conversation')
  await s.clock.advance(1_000)
  expect(s.filled).not.toContain('next question')
  expect(s.sent).toEqual([])
})

test("a question's thread is read as it comes on screen: every reply since is shown, and the relay's own marks it answered", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  // Priya answered in the thread: shown with the question, which stays open.
  await ui.press({ key: 'dot:9' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /reading the thread/ })).toBeDefined()
  await s.clock.advance(1_000)
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /1 REPLY SINCE IT WAS ASKED/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /We settled this in #198/ })).toBeDefined()
  expect(await ui.find({ key: 'opt:igor-220-retry:0' })).toBeDefined()
  // Read in the last minute: coming back reads nothing.
  await ui.press({ key: 'dot:0' })
  await ui.press({ key: 'dot:9' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /reading the thread/ })).toBeUndefined()
  // Ben's thread holds the relay's own answer, from another machine: answered.
  await ui.press({ key: 'dot:13' })
  await s.clock.advance(1_000)
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /RELAYED FROM ANOTHER MACHINE ON GITHUB AS/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Answered already: adam-relay\[bot\] posted your answer from another machine/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Bumping this/ })).toBeDefined()
  expect(await s.enter($, 'From main')).toBe('This question is already relayed: (e)dit your post to change it.')
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test('many replies are trimmed to fit, and (v)iew all shows every one in full', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const short = await $.ui.mount({
    ...BAND,
    props: { ...BAND.props, maxRows: 7, bodyColumns: 85, scroll: { offset: 0, bodyRows: 6 } },
    viewport: { columns: 90, rows: 24, isFullscreen: true },
    surface: 'terminal',
  })
  await short.press({ key: 'dot:10' })
  await s.clock.advance(1_000)
  await short.redraw()
  expect(await short.find({ type: 'Text', text: /4 REPLIES SINCE IT WAS ASKED/ })).toBeDefined()
  expect(await short.find({ type: 'Text', text: /Finance is the main user/ })).toBeUndefined()
  await short.unmount()
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'view' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /EVERYTHING SINCE THE QUESTION/ })).toBeDefined()
  for (const words of [/Finance is the main user/, /Parquet is a tenth the size/, /Could we ship both/, /Adam, your call on the/]) {
    expect(await ui.find({ type: 'Text', text: words })).toBeDefined()
  }
  expect(await s.enter($, 'CSV')).toBe('Go (b)ack to answer: this shows the replies and the record in full.')
  expect(await s.enter($, 'b')).toBe('Back to the question')
  expect(await s.enter($, 'CSV by default, Parquet behind a flag.')).toContain('Relayed to Linear')
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test('a reply that lands while Adam writes stops the post until he has seen it; Enter again relays', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:14' })
  await s.clock.advance(1_000)
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /no replies/ })).toBeDefined()
  expect(await s.enter($, 'Yes, keep the banner up.')).toBe('Not posted: Sara Lind replied since you last read the thread. Read it, then ⏎ again.')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /back to normal as of 10:40/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: / · 1 NEW/ })).toBeDefined()
  // What was typed goes back in the box, for the second Enter.
  await s.clock.advance(1_000)
  expect(s.filled.slice(-1)).toEqual(['Yes, keep the banner up.'])
  expect(await s.enter($, 'No banner, then.')).toBe('Relayed to Linear ENG-437 · Status page as adam-relay (Linear app)')
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test("a record more private than the thread is shown, not posted; (a)gree posts the recorded answer's fixed text and its link", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:15' })
  await s.clock.advance(1_000)
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /RECORDED ANSWER · FILTER 1/ })).toBeDefined()
  expect(await ui.find({ type: 'Link', text: /D-41: Installation tokens are scoped to one repository/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /the record is private and this thread public/ })).toBeDefined()
  // Nothing posted by itself; a click on (a)gree only types it.
  await ui.press({ key: 'record' })
  expect(s.filled.slice(-1)).toEqual(['a'])
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /^POST ON GITHUB AS$/ })).toBeDefined()
  expect(await s.enter($, 'a')).toBe('Posted the recorded answer on GitHub adamstallard/shared-skills #34 as adam-relay[bot]')
  await ui.press({ key: 'dot:15' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /POSTED THE RECORDED ANSWER ON GITHUB AS/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Recorded answer: $/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Recorded in:/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /https:\/\/github\.com\/adamstallard\/igor-ops\/blob\/main\/DECISIONS\.md#d-41/ })).toBeDefined()
  await ui.press({ key: 'dot:summary' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /^1 of 17 relayed this session/ })).toBeDefined()
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test('a questions-branch question shows its recorded answer; agreeing or answering logs it there, with no asking back and no edit', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:16' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /a questions-branch file has no thread/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /reading the thread/ })).toBeUndefined()
  // Talking to Claude offers no asking back: there is no thread to ask in.
  await s.enter($, 't')
  await ui.redraw()
  expect(await ui.find({ key: 'cmd:a' })).toBeUndefined()
  await s.enter($, 'b')
  expect(await s.enter($, 'a')).toBe("Logged the recorded answer on adamstallard/lore's questions branch, in a new file; nothing posted")
  await ui.press({ key: 'dot:16' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /LOGGED THE RECORDED ANSWER ON THE QUESTIONS BRANCH AS/ })).toBeDefined()
  expect(await ui.find({ key: 'cmd:e' })).toBeUndefined()
  expect(await s.enter($, 'e')).toBe('This question is answered, in a log file on the questions branch, which takes no edits.')
  expect(s.sent).toEqual([])
  await ui.unmount()
})

test("a post tried before the thread's first read comes back reads it itself; the late read changes nothing", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:14' })
  expect(await s.enter($, 'Yes, keep the banner up.')).toContain('Not posted: Sara Lind replied')
  await s.clock.advance(1_000)
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: / · 1 NEW/ })).toBeDefined()
  expect(await s.enter($, 'No banner, then.')).toContain('Relayed to Linear')
  await ui.unmount()
})

test("a stopped post's notice fits the key row in whole words, and goes once the post goes through or Adam moves on", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const at = (columns: number) => ({
    ...BAND,
    props: { ...BAND.props, bodyColumns: columns - 5 },
    viewport: { columns, rows: 40, isFullscreen: true },
    surface: 'terminal' as const,
  })
  const notice = /^Not posted: /
  const stop = async () => {
    await s.enter($, 'n')
    expect(await s.enter($, 'Yes, keep the banner up.')).toBe('Not posted: Sara Lind replied since you last read the thread. Read it, then ⏎ again.')
  }
  // Sara's question, dot 15: the first post is stopped.
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'dot:13' })
  await stop()
  for (const [columns, words] of [
    [140, 'Not posted: Sara Lind replied. Read it, then ⏎ again.'],
    [120, 'Not posted: Sara Lind replied'],
    [95, 'Not posted: a new reply'],
  ] as const) {
    const band = await $.ui.mount(at(columns))
    expect(((await band.find({ type: 'Text', text: notice })) as { text?: string } | undefined)?.text).toBe(words)
    await band.unmount()
  }
  // The second Enter posts: the notice is gone, here and back on her question.
  expect(await s.enter($, 'No banner, then.')).toContain('Relayed to Linear')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: notice })).toBeUndefined()
  await ui.press({ key: 'dot:14' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: notice })).toBeUndefined()
  // Her reply is no longer marked new either.
  expect(await ui.find({ type: 'Text', text: / · 1 NEW/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /back to normal as of 10:40/ })).toBeDefined()
  await ui.unmount()
})

test("a stopped post's notice goes with (l)ater, and with moving to another question", async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const notice = /^Not posted: /
  await ui.press({ key: 'dot:14' })
  expect(await s.enter($, 'Yes, keep the banner up.')).toContain('Not posted')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: notice })).toBeDefined()
  await ui.press({ key: 'dot:13' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: notice })).toBeUndefined()
  // Back on Sara's question, her reply already shown: it posts, so stop the next one another way.
  await ui.press({ key: 'dot:14' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: notice })).toBeUndefined()
  expect(await s.enter($, 'l')).toContain('Later')
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: notice })).toBeUndefined()
  await ui.unmount()
})

test('replies sit beside the choices and the recorded answer under the question, with why and (a)gree beside it', async ($, on) => {
  const s = answerSession(on)
  await s.open($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  // Under the question: the record's own heading; beside the choices: why it was not posted, and (a)gree.
  await ui.press({ key: 'dot:16' })
  await ui.redraw()
  expect(await ui.find({ type: 'Text', text: /^RECORDED ANSWER · FILTER 1$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^RECORDED ANSWER · FILTER 1 · SHOWN WITH THE QUESTION$/ })).toBeDefined()
  expect(await ui.find({ key: 'record' })).toBeDefined()
  expect(await ui.find({ key: 'view:record' })).toBeDefined()
  // No switch is left: /answer toggles the session, as before.
  expect(await ui.find({ key: 'layout' })).toBeUndefined()
  expect((await slash($, 'answer', 'layout')).text).toBe('Answer session closed. /answer opens it again where you left off.')
  expect(s.sent).toEqual([])
  await ui.unmount()
})

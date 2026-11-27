// Opening the answer service: the marker, the lock, setup, and the tools it
// opens beside.
import { expect, test } from 'claude-code/testing'

import { blocked, strip, stripListed, toolsMessage } from '../hooks/service'
import { applySetup, channelsOf, setupIntent } from '../hooks/setup'
import { BAND, OPENED, question, polled, session, shown } from './harness'

const OWN = ['mcp__inquisitor-answer-mod__propose_reply', 'mcp__inquisitor-answer-mod__record_verdict']
const OTHER = { plugin: 'other', tier: 'user' } as const
const info = (name: string) => ({ name, description: name, mcp: name.startsWith('mcp__') })

test('running answer opens the answer service with no prompt typed, named Answers', async ($, on) => {
  // @scenario answer-service: Running answer opens the answer service
  const s = session(on, { tools: ['Read', 'Grep', 'Glob'], core: { poll: () => polled([question('q1', { text: 'Should retries back off?' })]) } })
  await s.start($)
  const open = s.of('open')
  expect(open.length).toBe(1)
  expect(open[0]).toMatchObject({ session_id: 'sess-1', session_name: 'Answers', takeover: false })
  expect(s.of('poll').length).toBe(1)
  expect(s.registered).toEqual(['propose_reply', 'record_verdict'])
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /Should retries back off\?/)).toBeDefined()
  expect(await shown(ui, /Ctrl\+C twice to leave/)).toBeDefined()
})

test('a resumed session the launcher started opens the answer service again', async ($, on) => {
  // @scenario answer-service: Resuming the session reopens the answer service
  const s = session(on)
  await s.start($)
  // A resume raises session.start again, the marker still set by answer.
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await s.clock.settle()
  expect(s.of('open').length).toBeGreaterThanOrEqual(1)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /No questions yet/)).toBeDefined()
})

for (const how of ['resumed with claude --resume', 'started some other way'] as const) {
  test(`a session without the marker opens no answer service (${how})`, async ($, on) => {
    // @scenario answer-service: Resuming it without answer opens no answer service
    // @scenario answer-service: Another session opens no answer service
    const s = session(on, { marker: false })
    await s.start($)
    expect(s.calls).toEqual([])
    expect(s.registered).toEqual([])
    expect(s.commands).toEqual([])
    const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
    expect(await ui.find({ key: 'engine' })).toBeDefined()
    // Typed prompts reach the model as usual.
    expect(await s.enter($, 'hello')).toBeUndefined()
    expect(s.sent).toEqual(['hello'])
  })
}

test('the strip keeps only the mod’s own tools and Read, Grep and Glob', async () => {
  // @scenario answer-service: Another mod's tool is stripped at start
  // @scenario answer-service: A session without the launcher's restriction loses Bash
  const listed = ['Bash', 'Read', 'Grep', 'Glob', 'WebFetch', 'mcp__other__post_anything', ...OWN].map(info)
  expect(strip(listed).map(t => t.name)).toEqual(['Read', 'Grep', 'Glob', ...OWN])
  // @scenario answer-service: A tool registered later is stripped
  expect(strip([...listed, info('mcp__other__late_post')]).map(t => t.name)).toEqual(['Read', 'Grep', 'Glob', ...OWN])
  // @scenario answer-service: Only its own tools let it open
  expect(blocked(['Read', 'Grep', 'Glob', ...OWN])).toEqual([])
  expect(blocked(['Read', 'mcp__other__sneak'])).toEqual(['mcp__other__sneak'])
})

test('a session holding the marker opens beside its own tools, other mods on, their tools gone', async ($, on) => {
  // @scenario answer-service: Another mod's tool is stripped at start
  const s = session(on, { tools: ['Read', 'Grep', 'Glob', 'Bash', 'mcp__other__post_anything'] })
  await s.start($)
  expect(s.of('open').length).toBe(1)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /did not open/i)).toBeUndefined()
})

test('a tool another mod adds back keeps the answer service closed, naming the tool and where it comes from', async ($, on) => {
  // @scenario answer-service: A tool another mod adds back keeps the answer service closed
  const s = session(on)
  // The engine offers the model a tool the strip removed: another mod's
  // hook, running after this mod's, put it back.
  const offered = await $.tool.offer({ tool: 'mcp__other__sneak', provider: OTHER, for: 'list' })
  expect(offered.isOffered).toBe(false)
  await s.start($)
  expect(s.of('open')).toEqual([])
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /DID NOT OPEN/)).toBeDefined()
  expect(await shown(ui, /mcp__other__sneak comes from the mod or MCP server `other`, which must be turned off first/)).toBeDefined()
  expect(toolsMessage(['mcp__other__sneak'])).toContain('`other`')
})

test('a tool joining an open answer service aborts the turn, says which tool, and ends the session', async ($, on) => {
  // @scenario answer-service: A tool added back later ends the session
  const s = session(on)
  await s.start($)
  await $.turn.start({ text: 'what does it do?', turnId: 't-9' })
  await $.tool.offer({ tool: 'mcp__other__sneak', provider: OTHER, for: 'list' })
  await s.clock.settle()
  expect(s.aborts).toEqual(['t-9'])
  expect(s.of('close').length).toBe(1)
  expect(s.toasts.some(t => /mcp__other__sneak joined/.test(t) && /`other`/.test(t))).toBe(true)
  expect(s.exits).toEqual(['exit'])
})

test('a tool offered to a subagent, or in a session without the marker, changes nothing', async ($, on) => {
  // @scenario answer-service: A session without the marker keeps every tool
  session(on, { marker: false })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const offered = await $.tool.offer({ tool: 'mcp__other__post_anything', provider: OTHER, for: 'list' })
  expect(offered.isOffered).toBe(true)
})

test('another session’s fresh lock is shown with its name, id and start, and (t)ake over opens it here', async ($, on) => {
  // @scenario answer-service: A second session is offered the choice
  let takeover = false
  const s = session(on, {
    core: {
      open: req => {
        takeover = req['takeover'] === true
        return takeover ? OPENED : { version: 1, ok: true, status: 'locked', lock: { session_id: 'sess-0', session_name: 'Answers', started: '2026-10-20T09:00:00Z', refreshed: '2026-10-20T09:30:00Z' }, notices: [] }
      },
    },
  })
  await s.start($)
  expect(s.of('poll')).toEqual([])
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /ANOTHER SESSION HOLDS THE ANSWER SERVICE/)).toBeDefined()
  expect(await shown(ui, /Answers · session sess-0 · started 2026-10-20T09:00:00Z/)).toBeDefined()
  await s.enter($, 't')
  expect(takeover).toBe(true)
  expect(s.of('poll').length).toBe(1)
})

test('a lock lost to another session closes this one: it refreshes and polls nothing more', async ($, on) => {
  // @scenario answer-service: Taking over stops the old session
  let held = true
  const s = session(on, { core: { refresh: () => ({ version: 1, ok: true, held }) } })
  await s.start($)
  await s.clock.advance(30_000)
  expect(s.of('refresh').length).toBe(1)
  held = false
  await s.clock.advance(30_000)
  const polls = s.of('poll').length
  const refreshes = s.of('refresh').length
  await s.clock.advance(300_000)
  expect(s.of('poll').length).toBe(polls)
  expect(s.of('refresh').length).toBe(refreshes)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /Another session took it over/)).toBeDefined()
})

test('a core error saying the lock is lost closes the answer service too', async ($, on) => {
  // @scenario answer-service: Taking over stops the old session
  const s = session(on, { core: { poll: () => ({ version: 1, ok: false, error: 'another session holds the lock', lock_lost: true }) } })
  await s.start($)
  await s.clock.advance(120_000)
  expect(s.of('poll').length).toBe(1)
  expect(s.toasts.some(t => /took over the answer service/.test(t))).toBe(true)
})

test('reopening lands on the question last on screen', async ($, on) => {
  // @scenario answer-service: Reopening lands on the same question unless it was answered or has a category
  const s = session(on, {
    core: {
      open: () => ({ ...OPENED, screen: 'q2' }),
      poll: () => polled([question('q1', { text: 'First?', asked_at: '2026-10-20T09:00:00Z' }), question('q2', { text: 'Second?', asked_at: '2026-10-20T09:30:00Z' })]),
    },
  })
  await s.start($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /Second\?/)).toBeDefined()
  expect(await shown(ui, /2 of 2/)).toBeDefined()
  expect(s.of('screen.set').at(-1)).toMatchObject({ question: 'q2' })
})

test('setup runs in place of the queue on an incomplete configuration, and says why the login is needed', async ($, on) => {
  // @scenario answer-service: Setup opens in place of the queue on an incomplete configuration
  // @scenario answer-service: Setup asks for the GitHub login of a Discord-only person
  const s = session(on, {
    core: {
      open: () => ({ version: 1, ok: true, status: 'setup', notices: [] }),
      'setup.status': () => ({ version: 1, ok: true, complete: false, config: { discord: { relay: 'bot', subscriptions: [{ id: '123' }] } }, checks: [] }),
      'setup.save': req => ({ version: 1, ok: true, complete: false, config: req['config'], checks: [] }),
    },
  })
  await s.start($)
  expect(s.of('poll')).toEqual([])
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /SETUP · THE ANSWER SERVICE · NOT COMPLETE YET/)).toBeDefined()
  expect(await shown(ui, /every answer file, and every miss file but a hash-only one, names you by it/)).toBeDefined()
  expect(await s.enter($, 's')).toContain('needs your GitHub login')
})

test('setup saves the person’s channels and guesses a Linear team’s repositories, then opens the service', async ($, on) => {
  // @scenario answer-service: Setup offers the person's channels
  let complete = false
  const s = session(on, {
    core: {
      open: () => (complete ? OPENED : { version: 1, ok: true, status: 'setup', notices: [] }),
      'setup.status': () => ({ version: 1, ok: true, complete: false, config: { keep: 1 }, checks: [] }),
      'setup.guess-repos': () => ({ version: 1, ok: true, repos: ['o/api'] }),
      'setup.save': req => {
        complete = true
        return { version: 1, ok: true, complete: true, config: req['config'], checks: [] }
      },
    },
  })
  await s.start($)
  await s.enter($, 'login alice')
  await s.enter($, 'relay github answers')
  await s.enter($, 'add github o/api')
  await s.enter($, 'relay linear eng-relay')
  expect(await s.enter($, 'add linear ENG')).toContain('names o/api')
  await s.enter($, 's')
  const saved = s.of('setup.save')[0]!
  expect(saved['login']).toBe('alice')
  expect(saved['config']).toEqual({
    keep: 1,
    github: { relay: 'answers', subscriptions: ['o/api'] },
    linear: { relay: 'eng-relay', subscriptions: [{ id: 'ENG', repos: ['o/api'] }] },
  })
  expect(s.of('open').length).toBe(2)
  expect(s.of('poll').length).toBe(1)
})

test('setup runs again on request, showing the saved subscriptions', async ($, on) => {
  // @scenario answer-service: Setup runs again on request
  const s = session(on)
  await s.start($)
  await s.slash($, 'answer', 'setup')
  await s.clock.settle()
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /GITHUB · RELAY ANSWERS/)).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^o$/ })).toBeDefined()
})

test('setup asked for over an open service keeps the lock refreshed, and leaving releases it', async ($, on) => {
  // @scenario answer-service: A second session is offered the choice
  // Another session meets a live lock, never one left by a session that exited.
  const s = session(on)
  await s.start($)
  await s.slash($, 'answer', 'setup')
  await s.clock.advance(60_000)
  expect(s.of('refresh').length).toBeGreaterThan(0)
  await $.session.end({ sessionId: 'sess-1', reason: 'prompt_input_exit' } as never)
  await s.clock.settle()
  expect(s.of('close').length).toBe(1)
})

test('the tool list the model gets is stripped only in a session holding the marker', async () => {
  // @scenario answer-service: Another mod's tool is stripped at start
  // @scenario answer-service: A session without the marker keeps every tool
  const listed = { value: ['Bash', 'Read', ...OWN].map(info) }
  expect(stripListed(listed, true).value?.map(t => t.name)).toEqual(['Read', ...OWN])
  expect(stripListed(listed, false).value?.map(t => t.name)).toEqual(['Bash', 'Read', ...OWN])
})

test('setup refuses a channel added twice, sets a team\'s repositories, and removes a channel by its number', async () => {
  // @scenario answer-service: Setup runs again on request
  let config: Record<string, unknown> = {}
  const line = (text: string) => {
    const it = setupIntent(text, channelsOf(config), false)
    if (it.kind === 'refused') return it.why
    config = applySetup(config, it, channelsOf(config))
    return it.kind
  }
  expect(line('add github o/api')).toBe('add')
  expect(line('add github o/api')).toContain('already a channel')
  expect(line('add github o/web')).toBe('add')
  expect(line('add linear ENG')).toBe('add')
  expect(line('repos ENG o/web')).toBe('repos')
  expect(line('repos o/api o/web')).toContain('not a Linear team or Discord channel')
  expect(line('1')).toBe('remove')
  expect(config).toEqual({ github: { subscriptions: ['o/web'] }, linear: { subscriptions: [{ id: 'ENG', repos: ['o/web'] }] } })
})

test('reopening lands on the oldest question when it was last on screen', async ($, on) => {
  // @scenario answer-service: Reopening lands on the same question unless it was answered or has a category
  const qs = [question('q1', { text: 'First?', asked_at: '2026-10-20T09:00:00Z' }), question('q2', { text: 'Second?', asked_at: '2026-10-20T09:30:00Z' })]
  let screen = 'q2'
  const s = session(on, { core: { open: () => ({ ...OPENED, screen }), poll: () => polled(qs) } })
  await s.start($)
  await s.slash($, 'answer')
  await s.clock.settle()
  screen = 'q1'
  await s.slash($, 'answer')
  await s.clock.settle()
  expect(s.of('screen.set').at(-1)).toMatchObject({ question: 'q1' })
})

test('a tool another mod adds back while the lock is shown names the tool at once', async ($, on) => {
  // @scenario answer-service: A tool another mod adds back keeps the answer service closed
  const s = session(on, { core: { open: () => ({ version: 1, ok: true, status: 'locked', lock: { session_id: 'sess-0', session_name: 'Answers', started: '2026-10-20T09:00:00Z', refreshed: '2026-10-20T09:30:00Z' }, notices: [] }) } })
  await s.start($)
  await $.tool.offer({ tool: 'mcp__other__sneak', provider: OTHER, for: 'list' })
  await s.clock.settle()
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shown(ui, /DID NOT OPEN/)).toBeDefined()
  expect(await shown(ui, /mcp__other__sneak comes from the mod or MCP server `other`/)).toBeDefined()
})

test('setup asked for twice over an open service keeps the lock, and b goes back to the questions', async ($, on) => {
  // @scenario answer-service: Setup runs again on request
  const s = session(on)
  await s.start($)
  await s.slash($, 'answer', 'setup')
  await s.clock.settle()
  await s.slash($, 'answer', 'setup')
  await s.clock.settle()
  await s.clock.advance(60_000)
  expect(s.of('refresh').length).toBeGreaterThan(0)
  expect(await s.enter($, 'b')).toContain('Back to the questions')
})

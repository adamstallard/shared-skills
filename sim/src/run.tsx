import './globals'
import React from 'react'
import { render, Box as IBox, Text as IText } from 'ink'
import { register } from '../../answer-session/hooks/register.tsx'
import { __store } from './shim'
import { EventEmitter } from 'node:events'

const hooks: Record<string, any> = {}
register(((ev: string, a: any, b?: any) => { hooks[ev + (typeof a === 'function' ? '' : ':' + JSON.stringify(a))] = b ?? a; return { catch() {} } }) as any, {} as any)
const renderHook = Object.entries(hooks).find(([k]) => k.startsWith('ui.render') && k.includes('"Pane"'))![1]
const submitHook = hooks['prompt.submit']
// The pane is open and placed, as after /answer; the prompt box is the store's copy.
__store.set('immersive', true)

const mk = (type: string) => (props: any) => ({ type, props })
const comps = { Box: mk('Box'), Text: mk('Text'), Button: mk('Button'), Input: mk('Input'), Link: mk('Link'), Select: mk('Select') }
const log: string[] = []
const timers: (() => void)[] = []
const REPLIES = [
  "It asks whether the scope filter, which already hides lore entries outside the role's projects, should also hide files on the questions branch. Those files are questions agents asked about any project, so today a worker on igor can read a question about a payments project.\n\nThe trade-off:\n- Filtering keeps workers focused and leaks nothing across projects.\n- Showing them lets a worker learn from a similar question elsewhere.\n\nWhich matters more to you here: isolation between projects, or reuse of answers?",
  "Then the first answer fits what you described: hide them, the same way lore is hidden. One thing to settle first: the question doesn't say whether hidden files stay on the branch. If you're unsure, asking claude is cheap.",
]
let replyN = 0
const $: any = {
  session: { model: async () => 'claude-opus-5-5' },
  model: {
    complete: async (r: any) => {
      log.push('model.complete'); if (process.env.SLOW && replyN >= Number(process.env.SLOW)) return new Promise(() => {})
      if (process.env.MODEL_FAIL) return { isAnswered: false, reason: 'api-error', status: 529 }
      if (/JSON only/.test(r.prompt)) return { isAnswered: true, text: JSON.stringify({ question: "Should a worker's search leave out questions-branch files about projects outside the role's scope, the way it leaves out lore entries?", context: 'The files stay on the branch; only what a worker sees changes.', options: [ { label: 'Yes, leave them out', effect: "Workers see only their own projects' questions." }, { label: 'No, include them', effect: "Workers also see other projects' questions." } ], summary: 'Adam wants isolation between projects; hidden files stay on the branch.' }) }
      if (/clarifying question/.test(r.prompt)) return { isAnswered: true, text: 'When the filter hides a question file, does it stay on the branch for other roles, or is it removed?' }
      return { isAnswered: true, text: REPLIES[replyN++ % REPLIES.length] }
    },
  },
  clock: { after: (_ms: number, fn: () => void) => { timers.push(fn); return { cancel() {} } } },
  prompt: {
    read: async () => ({ text: (__store.get('prompt') as string) ?? '', cursor: 0 }),
    fill: async (a: any) => { __store.set('prompt', a.text); log.push('fill ' + a.text); return { isFilled: true } },
  },
  ui: { panes: async () => [{ id: 'answer-session', isShown: true, isPlaced: true }], toast: (t: string) => log.push('toast ' + t), resolve: () => comps, status: (t: any) => log.push('status ' + t), focus: async (a: any) => { log.push('focus ' + a.key); return {} }, close: async () => log.push('close') },
}
let buttons: Record<string, any> = {}
let inputs: Record<string, any> = {}
const strip = (p: any) => { const { children, key, hover, ...rest } = p; return rest }
const toInk = (n: any, i = 0): any => {
  if (n == null || n === false || n === true) return null
  if (typeof n === 'string' || typeof n === 'number') return String(n)
  const kids = (n.props.children ?? []).map((c: any, j: number) => toInk(c, j))
  switch (n.type) {
    case 'Box': return React.createElement(IBox, { key: i, ...strip(n.props) }, ...kids)
    case 'Text': {
      const { dimColor, color, bold, inverse, wrap, italic } = n.props
      return React.createElement(IText, { key: i, dimColor, bold, inverse, wrap, italic }, ...kids)
    }
    case 'Link': return React.createElement(IText, { key: i, underline: true }, ...kids)
    case 'Button': {
      buttons[n.props.key ?? n.props.label] = n.props
      const prefix = n.props.plain ? (n.props.hotkey ? n.props.hotkey + ': ' : '') : '[ '
      const suffix = n.props.plain ? '' : ' ]'
      return React.createElement(IText, { key: i }, prefix, ...(n.props.label ? [n.props.label] : kids), suffix)
    }
    case 'Input': {
      inputs[n.props.key] = n.props
      const rows = n.props.rows ?? 1
      const lines = [React.createElement(IText, { key: 0, dimColor: true }, '› ' + (n.props.value || n.props.placeholder || ''))]
      for (let r = 1; r < rows; r++) lines.push(React.createElement(IText, { key: r }, ' '))
      return React.createElement(IBox, { key: i, flexDirection: 'column', borderStyle: 'single', borderDimColor: true, paddingX: 1, flexGrow: 1 } as any, ...lines)
    }
  }
  return React.createElement(IText, { key: i }, `<${n.type}>`)
}

async function frame(cols: number, rows: number) {
  buttons = {}; inputs = {}
  const tree = await renderHook($, { props: { bodyColumns: cols, scroll: { bodyRows: rows, offset: 0 }, isFocused: false, placement: process.env.PLACEMENT ?? 'dock' } })
  const out: any = new EventEmitter(); out.columns = cols; out.rows = rows + 5
  let last = ''; out.write = (s: string) => { last = s }
  const inst = render(toInk(tree), { stdout: out, debug: true, patchConsole: false, exitOnCtrlC: false } as any)
  inst.unmount()
  return last.replace(/\x1b\[[0-9;]*m/g, '').split('\n').map(l => l.replace(/\s+$/, '')).join('\n')
}
const settle = () => new Promise(r => setTimeout(r, 60))

const [cols, rows] = (process.argv[2] ?? '120x40').split('x').map(Number) as [number, number]
const script = (process.argv[3] ?? '').split('|').filter(Boolean)
;(async () => {
  await frame(cols!, rows!)
  for (const act of script) {
    if (act === 'tick') { for (const fn of timers.splice(0)) fn() }
    else if (act.startsWith('say@')) { const [pre, ...rest] = act.slice(4).split(':'); const k = Object.keys(inputs).find(x => x.startsWith(pre!))!; inputs[k].onSubmit(rest.join(':')) }
    else if (act.startsWith('edit@')) { const [pre, ...rest] = act.slice(5).split(':'); const k = Object.keys(inputs).find(x => x.startsWith(pre!))!; inputs[k].onInput(rest.join(':')) }
    // type:<text> puts text in the prompt box; enter:<text>, or bare text, presses Enter on it.
    else if (act.startsWith('type:')) { __store.set('prompt', act.slice(5)) }
    else {
      const text = act.startsWith('enter:') ? act.slice(6) : act
      const r = await submitHook($, { text, origin: { kind: 'composer' } }, async () => ({ text }))
      log.push('⏎ ' + (r?.drop ?? 'REACHED THE MODEL'))
      __store.set('prompt', '')
    }
    await settle(); await frame(cols!, rows!)
  }
  const f = await frame(cols!, rows!)
  const lines = f.split('\n')
  console.log('┌' + '─'.repeat(cols!) + '┐')
  for (const l of lines) console.log('│' + l.padEnd(cols!) + '│')
  console.log('└' + '─'.repeat(cols!) + '┘')
  console.log('> ' + ((__store.get('prompt') as string) || ''))
  console.log(lines.length, 'rows;', log.join(' | '))
})()

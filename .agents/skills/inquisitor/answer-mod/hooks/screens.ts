// The keys and lines of the screens a closed or unopened service shows:
// setup, the lock, the tools that keep it closed.
import { atom, read, update } from 'claude-code'
import type { EngineInterface } from 'claude-code'

import { quitSession } from './actions'
import { OPENING_LINE, openService } from './service'
import { enterSetup } from './setup'
import { INITIAL } from './state'

const flashAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'flash' } as const, INITIAL.flash)
const serviceAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'service' } as const, INITIAL.service)

/** A key on a screen outside the queue: setup, the lock, a closed service. */
export async function serviceKey($: EngineInterface, key: string): Promise<string> {
  const s = await read($, serviceAtom)
  if (key === 'q') return quitSession($)
  if (s.status === 'locked' && key === 't') {
    await openService($, true)
    return 'Took over the answer service'
  }
  if (s.status === 'setup') return enterSetup($, key, () => openService($, false), () => quitSession($))
  return ''
}

/** What a line typed on a screen outside the queue does. */
export async function serviceEnter($: EngineInterface, text: string): Promise<string> {
  const s = await read($, serviceAtom)
  const key = text.trim().toLowerCase()
  if (s.status === 'setup') return enterSetup($, text, () => openService($, false), () => quitSession($))
  if (key === 'q') return quitSession($)
  if (s.status === 'locked' && key === 't') return serviceKey($, 't')
  const why = s.status === 'locked' ? '(t)ake over, or (q)uit.' : s.status === 'opening' ? OPENING_LINE : '/answer opens the answer service again; q leaves.'
  await update($, flashAtom, () => why)
  return why
}


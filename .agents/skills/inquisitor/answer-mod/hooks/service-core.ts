// Every call the band makes to the core goes through `ask`, which closes the
// answer service the moment the core says another session holds the lock.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Timer } from 'claude-code'

import { callCore } from './core'
import type { Reply } from './core'
import type { Request } from './core-protocol'
import type { ServiceState } from '../types'
import { INITIAL } from './state'

const judgingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'judging' } as const, INITIAL.judging)
const serviceAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'service' } as const, INITIAL.service)

/**
 * The service's timers. They live in the module: a hot reload stops them,
 * and the session.start that follows opens the service again.
 */
export const timers: { poll?: Timer; refresh?: Timer } = {}

/**
 * Whether this session holds the lock: the service is open, or setup was
 * asked for over the open service. Refreshing and closing go by this, so
 * the lock is kept while setup is on screen and goes with the session.
 */
export function holdsLock(s: ServiceState): boolean {
  return s.status === 'open' || (s.status === 'setup' && s.back)
}

export function stopTimers(): void {
  timers.poll?.cancel()
  timers.refresh?.cancel()
  delete timers.poll
  delete timers.refresh
}

/**
 * Another session took the lock: this one closes its answer service and
 * refreshes, polls, posts and pushes nothing more.
 */
export async function lost($: EngineInterface): Promise<void> {
  if ((await read($, serviceAtom)).status === 'lost') return
  stopTimers()
  await update($, serviceAtom, () => ({ status: 'lost' as const }))
  await update($, judgingAtom, () => null)
  $.ui.toast('Another session took over the answer service: this one has closed it.')
}

export async function ask<R extends Request>($: EngineInterface, request: R): Promise<Reply<R['command']>> {
  const reply = await callCore($, request)
  if (!reply.ok && reply.lock_lost) await lost($)
  return reply
}

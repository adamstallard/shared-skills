// Setup, in the band in place of the queue: the configuration as the core
// reads it, changed by lines typed in the prompt box, saved by the core.
import { atom, read, update } from 'claude-code'
import type { EngineInterface } from 'claude-code'

import type { SetupCheck, SetupStatusResponse, Surface } from './core-protocol'
import { ask } from './service-core'
import { INITIAL } from './state'

const flashAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'flash' } as const, INITIAL.flash)
const serviceAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'service' } as const, INITIAL.service)

export const SURFACES: readonly Surface[] = ['github', 'linear', 'discord']

/** One subscription, numbered across the surfaces as setup lists them. */
export type Channel = { surface: Surface; id: string; repos?: string[] }

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

/** A surface's object in the answer_service section, or an empty one. */
export function surfaceOf(config: Record<string, unknown>, surface: Surface): Record<string, unknown> {
  const entry = config[surface]
  return isRecord(entry) ? entry : {}
}

/** Every subscription in the configuration, in setup's order. */
export function channelsOf(config: Record<string, unknown>): Channel[] {
  return SURFACES.flatMap(surface => {
    const subs = surfaceOf(config, surface)['subscriptions']
    if (!Array.isArray(subs)) return []
    return subs.flatMap((s): Channel[] => {
      if (typeof s === 'string') return [{ surface, id: s }]
      if (isRecord(s) && typeof s['id'] === 'string') {
        const repos = Array.isArray(s['repos']) ? s['repos'].filter((r): r is string => typeof r === 'string') : undefined
        return [{ surface, id: s['id'], ...(repos ? { repos } : {}) }]
      }
      return []
    })
  })
}

/** The configuration with one surface's object changed by `fn`, every other key kept. */
function withSurface(config: Record<string, unknown>, surface: Surface, fn: (entry: Record<string, unknown>) => Record<string, unknown>): Record<string, unknown> {
  return { ...config, [surface]: fn(surfaceOf(config, surface)) }
}

function subsOf(entry: Record<string, unknown>): unknown[] {
  return Array.isArray(entry['subscriptions']) ? entry['subscriptions'] : []
}

/** The check setup shows beside a channel, if any. */
export const checkOf = (checks: readonly SetupCheck[], c: Channel) => checks.find(k => k.surface === c.surface && k.channel === c.id)

/** What a line typed in setup does. */
export type SetupIntent =
  | { kind: 'login'; login: string }
  | { kind: 'relay'; surface: Surface; name: string }
  | { kind: 'add'; surface: Surface; id: string }
  | { kind: 'remove'; index: number }
  | { kind: 'repos'; id: string; repos: string[] }
  | { kind: 'user'; id: string }
  | { kind: 'key' }
  | { kind: 'lore'; repository: string; path: string; serves: string[] }
  | { kind: 'save' }
  | { kind: 'recheck' }
  | { kind: 'back' }
  | { kind: 'quit' }
  | { kind: 'refused'; why: string }
  | { kind: 'none' }

const REPO = /^[A-Za-z0-9][\w.-]*(\/[\w.-]+)?$/

export const SETUP_HELP =
  'Type a line, then ⏎: login <your GitHub login> · relay github|linear|discord <identity> · add github <owner or owner/repo> · add linear <team key> · add discord <channel id> · user <your Discord user id> · repos <team or channel> <owner/repo …|none> · linear-key <key> · lore <owner/repo> <clone path> <owner …> · a number removes that channel.'

export function setupIntent(draft: string, channels: readonly Channel[], back: boolean): SetupIntent {
  const text = draft.trim()
  if (!text) return { kind: 'none' }
  const lower = text.toLowerCase()
  if (lower === 's') return { kind: 'save' }
  if (lower === 'r') return { kind: 'recheck' }
  if (lower === 'q') return { kind: 'quit' }
  if (lower === 'b' && back) return { kind: 'back' }
  if (/^\d+$/.test(text)) {
    const index = Number(text) - 1
    return channels[index] ? { kind: 'remove', index } : { kind: 'refused', why: `There is no channel ${text}.` }
  }
  const [word = '', ...rest] = text.split(/\s+/)
  const surface = (s: string | undefined): Surface | undefined => SURFACES.find(x => x === s?.toLowerCase())
  switch (word.toLowerCase()) {
    case 'login':
      return rest.length === 1 && /^[A-Za-z0-9-]+$/.test(rest[0]!) ? { kind: 'login', login: rest[0]! } : { kind: 'refused', why: 'login takes your GitHub login, one word.' }
    case 'relay': {
      const s = surface(rest[0])
      return s && rest.length === 2 ? { kind: 'relay', surface: s, name: rest[1]! } : { kind: 'refused', why: 'relay takes a surface, github, linear or discord, and the identity its skill posts as.' }
    }
    case 'add': {
      const s = surface(rest[0])
      const id = rest[1]
      if (!s || rest.length !== 2 || !id) return { kind: 'refused', why: 'add takes a surface and one channel: add github o/api, add linear ENG, add discord 1234.' }
      if (s === 'github' && !REPO.test(id)) return { kind: 'refused', why: 'A GitHub channel is an owner, or owner/repo.' }
      if (channels.some(c => c.surface === s && c.id === id)) return { kind: 'refused', why: `${id} is already a channel.` }
      return { kind: 'add', surface: s, id }
    }
    case 'repos': {
      const [id, ...repos] = rest
      if (!id || !repos.length) return { kind: 'refused', why: 'repos takes a team or channel, then its repositories, or none.' }
      if (!channels.some(c => c.surface !== 'github' && c.id === id)) return { kind: 'refused', why: `${id} is not a Linear team or Discord channel here.` }
      if (repos.length === 1 && repos[0]!.toLowerCase() === 'none') return { kind: 'repos', id, repos: [] }
      return repos.every(r => /^[\w.-]+\/[\w.-]+$/.test(r)) ? { kind: 'repos', id, repos } : { kind: 'refused', why: 'Each repository is owner/repo.' }
    }
    case 'user':
      return rest.length === 1 && /^\d+$/.test(rest[0]!) ? { kind: 'user', id: rest[0]! } : { kind: 'refused', why: 'user takes your Discord user id, a number.' }
    case 'linear-key':
      return rest.length === 1 ? { kind: 'key' } : { kind: 'refused', why: 'linear-key takes the key, one word.' }
    case 'lore': {
      const [repository, path, ...serves] = rest
      if (!repository || !/^[\w.-]+\/[\w.-]+$/.test(repository) || !path || !serves.length) return { kind: 'refused', why: 'lore takes the repository to create, owner/repo, its clone path, and the owners or repositories it serves.' }
      return { kind: 'lore', repository, path, serves }
    }
  }
  return { kind: 'refused', why: `${word} is not a setup line: ${SETUP_HELP}` }
}

/** The configuration a setup line leaves. */
export function applySetup(config: Record<string, unknown>, it: SetupIntent, channels: readonly Channel[]): Record<string, unknown> {
  switch (it.kind) {
    case 'relay':
      return withSurface(config, it.surface, e => ({ ...e, relay: it.name }))
    case 'add':
      return withSurface(config, it.surface, e => ({ ...e, subscriptions: [...subsOf(e), it.surface === 'github' ? it.id : { id: it.id }] }))
    case 'remove': {
      const c = channels[it.index]
      if (!c) return config
      return withSurface(config, c.surface, e => ({
        ...e,
        subscriptions: subsOf(e).filter(s => (typeof s === 'string' ? s : isRecord(s) ? s['id'] : undefined) !== c.id),
      }))
    }
    case 'repos': {
      const c = channels.find(x => x.surface !== 'github' && x.id === it.id)
      if (!c) return config
      return withSurface(config, c.surface, e => ({
        ...e,
        subscriptions: subsOf(e).map(s => (isRecord(s) && s['id'] === it.id ? { ...s, repos: it.repos } : s)),
      }))
    }
    case 'user':
      return withSurface(config, 'discord', e => ({ ...e, user: it.id }))
  }
  return config
}

// The Linear key typed in setup: held here until the save hands it to the
// core, which keeps it in the keychain. Never in `$.state` or the config.
let linearKey: string | undefined

/** The setup on screen, or undefined. */
async function current($: EngineInterface): Promise<{ setup: SetupStatusResponse; back: boolean; login?: string } | undefined> {
  const s = await read($, serviceAtom)
  return s.status === 'setup' && s.setup ? { setup: s.setup, back: s.back, ...(s.login ? { login: s.login } : {}) } : undefined
}

async function put($: EngineInterface, setup: SetupStatusResponse, extra: { login?: string } = {}): Promise<void> {
  await update($, serviceAtom, s => (s.status === 'setup' ? { ...s, setup, ...extra } : s))
}

/** Does a setup line; returns what it did. `reopen` opens the service once setup is complete. */
export async function enterSetup($: EngineInterface, draft: string, reopen: () => Promise<void>, quit: () => Promise<string>): Promise<string> {
  const now = await current($)
  if (!now) return 'Setup could not read the configuration: r and Enter read it again.'
  const channels = channelsOf(now.setup.config)
  const it = setupIntent(draft, channels, now.back)
  const say = async (note: string) => {
    await update($, flashAtom, () => note)
    return note
  }
  switch (it.kind) {
    case 'none':
      return say(SETUP_HELP)
    case 'refused':
      return say(it.why)
    case 'quit':
      return quit()
    case 'back':
      await reopen()
      return 'Back to the questions'
    case 'login':
      await put($, now.setup, { login: it.login })
      return say(`Your GitHub login: ${it.login}. (s)ave keeps it.`)
    case 'key':
      linearKey = draft.trim().split(/\s+/)[1]
      return say('The Linear key goes to the keychain when you (s)ave; it is never written to the configuration.')
    case 'recheck': {
      const res = await ask($, { command: 'setup.status', session_id: await $.session.id() })
      if (!res.ok) return say(`Setup could not read the configuration: ${res.error}`)
      await put($, res)
      return say('Checked again.')
    }
    case 'lore': {
      const res = await ask($, { command: 'setup.create-lore', session_id: await $.session.id(), repository: it.repository, path: it.path, serves: it.serves })
      return say(res.ok ? `Created ${it.repository}, cloned it to ${it.path}, and added it to your lore repositories.` : `Not created: ${res.error}`)
    }
    case 'save': {
      const res = await ask($, {
        command: 'setup.save',
        session_id: await $.session.id(),
        config: now.setup.config,
        ...(now.login ? { login: now.login } : {}),
        ...(linearKey ? { linear_key: linearKey } : {}),
      })
      if (!res.ok) return say(`Not saved: ${res.error}`)
      linearKey = undefined
      await put($, res)
      if (!res.complete) return say('Saved. Setup is not complete yet: it needs your GitHub login and a surface with both a relay and a channel.')
      await reopen()
      return 'Saved. The answer service opens.'
    }
    case 'add': {
      let config = applySetup(now.setup.config, it, channels)
      let note = `Added ${it.id} on ${it.surface}. (s)ave keeps it.`
      if (it.surface !== 'github') {
        const guess = await ask($, { command: 'setup.guess-repos', session_id: await $.session.id(), surface: it.surface, channel: it.id })
        if (guess.ok && guess.repos.length) {
          config = applySetup(config, { kind: 'repos', id: it.id, repos: guess.repos }, channelsOf(config))
          note = `Added ${it.id}: its history names ${guess.repos.join(', ')}, so its questions are placed there. (s)ave keeps it.`
        } else {
          note = `Added ${it.id}: its history names no subscribed repository. Which does it concern? Type repos ${it.id} owner/repo …, or repos ${it.id} none.`
        }
      }
      await put($, { ...now.setup, config })
      return say(note)
    }
    case 'remove':
    case 'relay':
    case 'repos':
    case 'user': {
      await put($, { ...now.setup, config: applySetup(now.setup.config, it, channels) })
      return say('Changed. (s)ave keeps it.')
    }
  }
}

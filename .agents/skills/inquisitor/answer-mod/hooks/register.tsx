// The inquisitor's answer mod: the answer service's band, its tools and its
// timers. The service's logic is the Python core (scripts/service/), which
// the mod calls over the JSON commands in core-protocol.ts.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import {
  DONE_WORD,
  PUT_BACK_MS,
  addTurn,
  boxChanged,
  contextOf,
  dropped,
  enter,
  enterHint,
  intent,
  isPutBack,
  isToModel,
  proposeReply,
  recordSay,
  schedulePreview,
  settleBox,
  snapshot,
  think,
} from './actions'
import { band, placed } from './band'
import { PROPOSE_TOOL } from './questions'
import { serviceEnter } from './screens'
import {
  VERDICT_TOOL,
  closeService,
  hasMarker,
  judgeTurnEnded,
  judgeTurnStarted,
  loadSetup,
  openService,
  pumpJudge,
  recordVerdict,
  strip,
  stripListed,
  toolJoined,
} from './service'
import { ask, holdsLock } from './service-core'
import { INITIAL, without } from './state'

const awaitingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'awaiting' } as const, INITIAL.awaiting)
const flashAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'flash' } as const, INITIAL.flash)
const judgingAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'judging' } as const, INITIAL.judging)
const knownPlacesAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'knownPlaces' } as const, INITIAL.knownPlaces)
const markerAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'marker' } as const, INITIAL.marker)
const promptAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'prompt' } as const, INITIAL.prompt)
const replyTurnsAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'replyTurns' } as const, INITIAL.replyTurns)
const rowsAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'rows' } as const, INITIAL.rows)
const serviceAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'service' } as const, INITIAL.service)
const turnAtom = atom({ plugin: 'inquisitor-answer-mod', key: 'turn' } as const, INITIAL.turn)

/** The band shows while the service is anything but unopened. */
async function isShown($: EngineInterface): Promise<boolean> {
  return (await read($, markerAtom)) && (await read($, serviceAtom)).status !== 'none'
}

async function isOpen($: EngineInterface): Promise<boolean> {
  return (await read($, serviceAtom)).status === 'open'
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const marker = await hasMarker($)
    await update($, markerAtom, () => marker)
    if (marker) {
      await $.command.register({ name: 'answer', description: 'Close or open the answer service; /answer setup runs setup', immediate: true })
      await $.tool
        .register({
          name: 'propose_reply',
          description:
            "Puts a drafted reply in the person's prompt box, on the question they are discussing in the answer service, for them to confirm or edit before it posts. Use it when they ask you to write or draft their reply, or the new text of a post they are editing. It posts nothing.",
          inputSchema: {
            type: 'object',
            properties: { text: { type: 'string', description: 'Exactly the reply to post, without a "User says:" prefix.' } },
            required: ['text'],
          },
          isDeferred: false,
        })
        .catch(() => undefined)
      await $.tool
        .register({
          name: 'record_verdict',
          description:
            'Records your judgement of a message the answer service put before you to judge. It posts, writes and runs nothing: its fields choose among fixed actions. Set only the fields that turn asks for.',
          inputSchema: {
            type: 'object',
            properties: {
              message: { type: 'string', description: 'The message id the judging prompt names.' },
              question: { type: 'string', enum: ['yes', 'no', 'unclear'] },
              category: { type: 'string', enum: ['secret', 'vulnerability', 'personal', 'none'] },
              filter: { type: 'string', enum: ['1', '2', '3', '4', 'none'] },
              hit: { type: 'integer', minimum: 1 },
              place: { type: 'string' },
              place_sure: { type: 'string', enum: ['yes', 'no'] },
            },
            required: ['message'],
          },
          isDeferred: false,
        })
        .catch(() => undefined)
    }
    const started = await next(e)
    // Only a session the answer launcher started opens the answer service,
    // by itself, with no prompt typed: started, resumed or reloaded alike.
    if (marker && e.isInteractive) await openService($, false)
    return started
  })

  // Any exit closes the answer service: the lock goes with the session.
  on('session.end', async ($, e, next) => {
    if (holdsLock(await read($, serviceAtom))) await closeService($).catch(() => undefined)
    return next(e)
  })

  // /answer closes the answer service, or opens it again; /answer setup runs setup.
  on('command.run', { command: 'answer' }, async ($, e) => {
    if (!(await read($, markerAtom))) return { text: 'The answer service opens only in a session the answer command starts.' }
    if (/\bsetup\b/.test(e.args)) {
      await loadSetup($, holdsLock(await read($, serviceAtom)))
      return { text: 'Setup: type a line in the prompt box, then Enter.' }
    }
    if (await isOpen($)) {
      await closeService($)
      await update($, flashAtom, () => null)
      return { text: 'Answer service closed: nothing polls. /answer opens it again where you left off.' }
    }
    await openService($, false)
    return { text: 'Answer service open: type in the prompt box, Enter answers. Ctrl+C twice to leave.' }
  })

  // In a session holding the marker, the model keeps only the mod's own two
  // tools and Read, Grep and Glob; other plugins stay on without their tools.
  on('tool.list', async ($, e, next) => {
    const listed = await next(e)
    return stripListed(listed, await hasMarker($))
  }).catch(async ($, e, next) => {
    // Fails closed: in a session holding the marker, a strip that failed still strips.
    return stripListed(await next(e), await read($, markerAtom))
  })

  // A tool the strip did not keep out, offered to the main conversation's
  // model: a closed service stays closed, and an open one ends the session.
  on('tool.offer', async ($, e, next) => {
    if (e.agentId !== undefined || !(await hasMarker($)) || strip([{ name: e.tool, description: '', mcp: false }]).length) return next(e)
    await toolJoined($, e.tool)
    return { isOffered: false }
  }).catch(async ($, e, next) => ((await read($, markerAtom)) && !strip([{ name: e.tool, description: '', mcp: false }]).length ? { isOffered: false } : next(e)))

  // Only the main conversation drafts into the prompt box: a call from a
  // subagent or one of the engine's forks carries an agentId and is refused.
  on('tool.call', { tool: PROPOSE_TOOL }, async ($, e) => {
    if (e.agentId !== undefined) return { deny: 'Only the main conversation can draft a reply into the answer service.' }
    const raw = (e as unknown as { text?: unknown }).text
    const text = typeof raw === 'string' ? raw : ''
    const r = await proposeReply($, text)
    return r.ok ? { result: r.text } : { deny: r.text }
  }).catch(() => ({ deny: 'The answer service could not take the draft, so nothing was put in the prompt box.' }))

  on('tool.call', { tool: VERDICT_TOOL }, async ($, e) => ({
    result: await recordVerdict($, e as unknown as Record<string, unknown>, e.agentId),
  })).catch(() => ({ result: 'Refused: the answer service could not take the verdict.' }))

  // While the service is open the prompt box takes answers: the engine's
  // guess at the next prompt is not one.
  on('prompt.suggest', async ($, e, next) => (e.origin.kind === 'suggestion' && (await isShown($)) ? { isShown: false } : next(e)))

  // The band previews what Enter would do with the box's text, so it keeps a copy.
  on('prompt.edit', async ($, e, next) => {
    const box = await next(e)
    if (await isShown($)) {
      await update($, promptAtom, () => box.text)
      await boxChanged($, box.text)
      schedulePreview($)
    }
    return box
  })
  on('prompt.change', async ($, e, next) => {
    const changed = await next(e)
    if (e.origin.kind === 'engine' && isPutBack(e.text)) await settleBox($, true)
    else if (await isShown($)) {
      await update($, promptAtom, () => e.text)
      await boxChanged($, e.text)
      schedulePreview($)
    }
    return changed
  })

  // While the band shows, Enter acts in it and the prompt reaches the model
  // only as a discussion message, with the question attached as quoted
  // data. Slash commands run. A failure drops the prompt.
  let surveyUp = false
  on('prompt.submit', async ($, e, next) => {
    if (e.command || e.isMeta || e.origin.kind !== 'composer' || !(await isShown($))) return next(e)
    if (surveyUp) return { drop: 'A survey is above the prompt: answer it first, and the answer service is back.' }
    if (!(await isOpen($))) {
      dropped(e.text)
      const done = await serviceEnter($, e.text)
      await update($, promptAtom, () => '')
      $.clock.after(PUT_BACK_MS, () => void settleBox($, false))
      return { drop: done }
    }
    const c = await snapshot($)
    const it = intent(c, e.text, await read($, knownPlacesAtom))
    if (isToModel(it)) {
      const q = c.q
      if (!q) return { drop: 'Nothing to discuss here.' }
      if (await read($, judgingAtom)) return { drop: 'Claude is judging a new message: send it again in a moment.' }
      const context = await contextOf($, q.id)
      if (context === undefined) return { drop: 'The answer service could not read the question for Claude, so the message was not sent.' }
      await update($, promptAtom, () => '')
      await recordSay($, q, it.text)
      const mode =
        c.declining?.stage === 'place'
          ? `[Answer service] The person is declining this question for the inquisitor under filter 1, and asks you to help find where the answer is recorded. If they ask you to fill it in, call ${PROPOSE_TOOL} with only the record's URL.`
          : c.editing && c.answer?.post
            ? `[Answer service] The person is editing their post in this thread, which now says, as quoted data: ${JSON.stringify(c.answer.post)}. If they ask for a new version, call ${PROPOSE_TOOL} with the full replacement text.`
            : `[Answer service] If the person asks you to write or draft their reply, call ${PROPOSE_TOOL} with exactly the text to post.`
      return next({ ...e, context: [...(e.context ?? []), context, mode] })
    }
    dropped(e.text)
    const rowsBefore = Object.keys(await read($, rowsAtom)).length
    const done = await enter($, c, it)
    await update($, promptAtom, () => '')
    $.clock.after(PUT_BACK_MS, () => void settleBox($, false))
    schedulePreview($)
    const rows = Object.values(await read($, rowsAtom))
    const row = rows.length > rowsBefore ? rows[rows.length - 1] : undefined
    return { drop: row ? DONE_WORD[row.verb] : done }
  }).catch((_$, e, next) => (next.called ? next(e) : { drop: 'The answer service could not check this prompt, so it was not sent.' }))

  // The main conversation's turns: a judging turn is bound to its message,
  // a discussion turn to its question.
  on('turn.start', async ($, e, next) => {
    if (e.agentId === undefined) {
      await update($, turnAtom, () => e.turnId)
      if (!(await judgeTurnStarted($, e.turnId, e.text))) {
        const waiting = await read($, awaitingAtom)
        if (waiting.length && e.text.trim()) {
          const exact = waiting.findIndex(w => e.text.includes(w.text))
          const i = exact >= 0 ? exact : 0
          const id = waiting[i]!.id
          await update($, awaitingAtom, w => w.filter((_, j) => j !== i))
          await update($, replyTurnsAtom, m => ({ ...m, [e.turnId]: id }))
        }
      }
    }
    return next(e)
  }).catch((_$, e, next) => next(e))

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    if (e.agentId !== undefined) return done
    await update($, turnAtom, t => (t === e.turnId ? null : t))
    await judgeTurnEnded($, e.turnId)
    const id = (await read($, replyTurnsAtom))[e.turnId]
    if (id) {
      await update($, replyTurnsAtom, m => without(m, e.turnId))
      const text = e.answer.trim()
      if (e.reason === 'answer' && text) {
        await addTurn($, id, { who: 'model', text })
        void ask($, { command: 'discussion.append', session_id: await $.session.id(), question: id, role: 'model', text })
      } else {
        await addTurn($, id, { who: 'error', text: e.reason === 'aborted' ? 'Stopped before it answered.' : `No answer (${e.reason}). Send again to retry.` })
      }
      await think($, id, undefined)
    }
    await pumpJudge($)
    return done
  }).catch((_$, e, next) => next(e))

  // The permission mode's labels mean nothing while every prompt is an answer.
  on('ui.render', { component: 'SessionMode' }, async ($, e, next) => {
    if (!(await isShown($))) return next(e)
    const { Box } = $.ui.resolve(e)
    return <Box />
  })

  // The hint line under the prompt says what Enter would do with what is typed.
  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    if (surveyUp || !(await isOpen($))) return next(e)
    const c = await snapshot($)
    const stage = c.declining?.stage
    const idle = c.composing
      ? `your question for ${c.q?.asker.name ?? 'the asker'}, then ⏎`
      : c.talking
        ? 'a message to Claude or a key, then ⏎'
        : c.picking
          ? 'a number or owner/name for where it is recorded, then ⏎'
          : stage === 'reason'
            ? c.q?.asker.kind === 'agent'
              ? '1 or 2 for why, then ⏎'
              : '1, then ⏎'
            : stage === 'filter'
              ? '1 to 4 for the filter, then ⏎'
              : stage === 'place'
                ? 'the URL where the answer is recorded, then ⏎'
                : stage === 'post'
                  ? 'a note for the miss, or p to post it as it is, then ⏎'
                  : c.q?.options && c.open && !c.editing
                    ? 'a number, a key or your answer, then ⏎'
                    : 'a key or your answer, then ⏎'
    const hint = enterHint(c, intent(c, await read($, promptAtom), await read($, knownPlacesAtom))) ?? idle
    return next({ ...e, props: { ...e.props, tail: hint + (e.props.tail ? `  ·  ${e.props.tail}` : '') } })
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    surveyUp = e.props.hasSurvey
    if (e.props.hasSurvey || !(await isShown($))) return next(e)
    return (await band($, e, $.ui.resolve(e))) ?? next(e)
  })

  on('ui.render', { component: 'Placed' }, async ($, e, next) => {
    if (e.props.plugin !== 'inquisitor-answer-mod' || e.surface !== 'terminal') return next(e)
    return (await placed($, e.props.id, $.ui.resolve(e))) ?? next(e)
  })
}

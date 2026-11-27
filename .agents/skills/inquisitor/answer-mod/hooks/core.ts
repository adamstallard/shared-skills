// Calls the answer service's Python core: one `inquisitor.py service` run per
// command, the request on standard input, the response on standard output.
import type { EngineInterface } from 'claude-code'

import type { ErrorResponse, Request, ResponseFor } from './core-protocol'

/** A poll fetches every subscribed questions branch; everything else is quick. */
const POLL_TIMEOUT_MS = 300_000
const TIMEOUT_MS = 120_000

export type Reply<C extends Request['command']> = ResponseFor[C] | ErrorResponse

const failure = (error: string): ErrorResponse => ({ version: 1, ok: false, error })

/**
 * The core's response to `request`, or an ErrorResponse saying why there is
 * none: the script did not run, printed no JSON, or printed something that
 * is not a response. Never throws.
 *
 * The script is found beside the mod's folder: `answer-mod/../scripts`. The
 * system resolves a linked plugin folder before its `..`, so the path holds
 * when the mod is loaded through `install-mod`'s link.
 */
export async function callCore<R extends Request>($: EngineInterface, request: R): Promise<Reply<R['command']>> {
  const script = `${$.plugin.root}/../scripts/inquisitor.py`
  let out: { exitCode: number; stdout: string; stderr: string }
  try {
    out = await $.process.run(['python3', '-I', script, 'service'], {
      stdin: JSON.stringify(request),
      timeoutMs: request.command === 'poll' ? POLL_TIMEOUT_MS : TIMEOUT_MS,
    })
  } catch (err) {
    return failure(`the answer service's script did not run: ${err instanceof Error ? err.message : String(err)}`)
  }
  const line = out.stdout.trim().split('\n').pop() ?? ''
  let parsed: unknown
  try {
    parsed = JSON.parse(line)
  } catch {
    const said = out.stderr.trim().split('\n').pop() ?? ''
    return failure(`the answer service's script printed no response (exit ${out.exitCode}${said ? `: ${said}` : ''})`)
  }
  if (typeof parsed !== 'object' || parsed === null || typeof (parsed as { ok?: unknown }).ok !== 'boolean') {
    return failure("the answer service's script printed something that is not a response")
  }
  const response = parsed as { ok: boolean; version?: unknown; error?: unknown }
  if (response.version !== 1) return failure(`the answer service's script answered version ${String(response.version)}, not 1`)
  if (!response.ok && typeof response.error !== 'string') return failure("the answer service's script failed without saying why")
  return parsed as Reply<R['command']>
}

/** Narrows a reply to its success. */
export const isOk = <C extends Request['command']>(reply: Reply<C>): reply is ResponseFor[C] => reply.ok

import type { ChatErrorCode, ChatSource, ChatTurn } from '../api/types'
import { isChatResponse } from './chat-response'

/** Browser deadline: above the route's own 30 s deadline. */
export const CLIENT_TIMEOUT_MS = 35_000

const CODES: readonly ChatErrorCode[] = [
  'invalid_request', 'busy', 'timeout', 'upstream_failure', 'unavailable', 'internal_error',
]

export type SendTurnResult =
  | { ok: true; answer: string; sources: ChatSource[] }
  | { ok: false; code: ChatErrorCode }

export interface SendTurnParams {
  question: string
  history: ChatTurn[]
  signal?: AbortSignal
}

/** One turn: a same-origin POST to the route, a client deadline, and the response mapped to a
 *  result. Never throws, never retries. */
export async function sendTurn({ question, history, signal }: SendTurnParams): Promise<SendTurnResult> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), CLIENT_TIMEOUT_MS)
  const onOuterAbort = () => controller.abort()
  signal?.addEventListener('abort', onOuterAbort)
  if (signal?.aborted) controller.abort()
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ question, history }),
      signal: controller.signal,
    })
    let body: unknown
    try {
      body = await res.json()
    } catch {
      return { ok: false, code: res.ok ? 'upstream_failure' : 'internal_error' }
    }
    if (res.ok) {
      if (!isChatResponse(body)) return { ok: false, code: 'upstream_failure' }
      return { ok: true, answer: body.answer, sources: body.sources }
    }
    const code = (body as { error?: unknown } | null)?.error
    const known = CODES.find((c) => c === code)
    return { ok: false, code: known ?? 'internal_error' }
  } catch (error) {
    const aborted = (error as { name?: unknown } | null)?.name === 'AbortError'
    return { ok: false, code: aborted ? 'timeout' : 'upstream_failure' }
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onOuterAbort)
  }
}

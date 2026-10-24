import { AwsClient } from 'aws4fetch'
import { isChatResponse } from '../lib/chat-response'
import type { BackendOutcome, ChatResponse, ChatTurn } from './types'

/** Default deadline for the one backend call: above the backend's 22 s read timeout. */
export const DEFAULT_TIMEOUT_MS = 30_000

export interface CallChatBackendParams {
  baseUrl: string
  accessKeyId: string
  secretAccessKey: string
  question: string
  history: ChatTurn[]
  timeoutMs?: number
}

export type CallChatBackendResult =
  | { ok: true; data: ChatResponse }
  | { ok: false; outcome: BackendOutcome }

const STATUS_OUTCOME: Record<number, BackendOutcome> = {
  400: 'invalid_request',
  429: 'busy',
  504: 'timeout',
  502: 'upstream_failure',
  403: 'backend_forbidden',
}

/** Signs one SigV4 request and makes exactly one fetch: no retry at any layer, because a
 *  retried POST would run the agent twice. Uses AwsClient.sign() (never AwsClient.fetch). */
export async function callChatBackend(params: CallChatBackendParams): Promise<CallChatBackendResult> {
  const { baseUrl, accessKeyId, secretAccessKey, question, history, timeoutMs = DEFAULT_TIMEOUT_MS } = params
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const client = new AwsClient({
      accessKeyId,
      secretAccessKey,
      service: 'execute-api',
      region: 'us-east-1',
      retries: 0,
    })
    const signed = await client.sign(`${baseUrl}/v1/chat`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ question, history }),
    })
    const res = await fetch(signed, { signal: controller.signal })
    if (!res.ok) return { ok: false, outcome: STATUS_OUTCOME[res.status] ?? 'backend_error' }
    let body: unknown
    try {
      body = await res.json()
    } catch {
      return { ok: false, outcome: 'upstream_failure' }
    }
    if (!isChatResponse(body)) return { ok: false, outcome: 'upstream_failure' }
    return { ok: true, data: { answer: body.answer, sources: body.sources } }
  } catch (error) {
    const aborted = (error as { name?: unknown } | null)?.name === 'AbortError'
    return { ok: false, outcome: aborted ? 'timeout' : 'upstream_failure' }
  } finally {
    clearTimeout(timer)
  }
}

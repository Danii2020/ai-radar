import { isValidHistory, trimHistory } from '../lib/history'
import { BODY_MAX_BYTES, QUESTION_MAX_CHARS } from '../lib/limits'
import { callChatBackend } from './backend'
import type { ChatErrorCode } from './types'

type Outcome =
  | 'ok'
  | 'invalid_request'
  | 'busy'
  | 'timeout'
  | 'upstream_failure'
  | 'backend_forbidden'
  | 'backend_error'
  | 'missing_config'
  | 'internal_error'

const REPLY: Record<Exclude<Outcome, 'ok'>, [number, ChatErrorCode]> = {
  invalid_request: [400, 'invalid_request'],
  busy: [429, 'busy'],
  timeout: [504, 'timeout'],
  upstream_failure: [502, 'upstream_failure'],
  backend_forbidden: [503, 'unavailable'],
  backend_error: [503, 'unavailable'],
  missing_config: [503, 'unavailable'],
  internal_error: [500, 'internal_error'],
}

const HEADERS = { 'content-type': 'application/json', 'cache-control': 'no-store' }

function failure(outcome: Exclude<Outcome, 'ok'>): Response {
  const [status, error] = REPLY[outcome]
  return new Response(JSON.stringify({ error }), { status, headers: HEADERS })
}

/** One text-free line: outcome and duration only (never question, history, answer, credentials). */
function log(outcome: Outcome, start: number): void {
  const line = JSON.stringify({ event: 'chat_request', outcome, duration_ms: Math.round(performance.now() - start) })
  if (outcome === 'ok') console.info(line)
  else console.error(line)
}

function envValue(name: string): string | null {
  const value = process.env[name]?.trim()
  return value ? value : null
}

async function handle(request: Request): Promise<Response | Exclude<Outcome, 'ok'>> {
  const declared = Number(request.headers.get('content-length'))
  if (Number.isFinite(declared) && declared > BODY_MAX_BYTES) return 'invalid_request'
  const raw = await request.text()
  if (new TextEncoder().encode(raw).length > BODY_MAX_BYTES) return 'invalid_request'

  let body: unknown
  try {
    body = JSON.parse(raw)
  } catch {
    return 'invalid_request'
  }
  if (typeof body !== 'object' || body === null || Array.isArray(body)) return 'invalid_request'
  const { question, history = [] } = body as Record<string, unknown>
  if (typeof question !== 'string' || question.trim() === '' || question.length > QUESTION_MAX_CHARS) {
    return 'invalid_request'
  }
  if (!isValidHistory(history)) return 'invalid_request'

  const baseUrl = envValue('CHAT_API_BASE_URL')
  const accessKeyId = envValue('CHAT_API_ACCESS_KEY_ID')
  const secretAccessKey = envValue('CHAT_API_SECRET_ACCESS_KEY')
  if (!baseUrl || !accessKeyId || !secretAccessKey) return 'missing_config'

  const result = await callChatBackend({
    baseUrl: baseUrl.replace(/\/+$/, ''),
    accessKeyId,
    secretAccessKey,
    question,
    history: trimHistory(history),
  })
  if (!result.ok) return result.outcome
  return new Response(JSON.stringify({ answer: result.data.answer, sources: result.data.sources }), {
    status: 200,
    headers: HEADERS,
  })
}

/** The whole logic of `POST /api/chat`: size check, parse, validate, trim, read env, one
 *  backend call, map to a fixed error code, log one line. Never throws. */
export async function handleChatRequest(request: Request): Promise<Response> {
  const start = performance.now()
  let outcome: Outcome
  let response: Response
  try {
    const result = await handle(request)
    if (typeof result === 'string') {
      outcome = result
      response = failure(result)
    } else {
      outcome = 'ok'
      response = result
    }
  } catch {
    outcome = 'internal_error'
    response = failure('internal_error')
  }
  log(outcome, start)
  return response
}

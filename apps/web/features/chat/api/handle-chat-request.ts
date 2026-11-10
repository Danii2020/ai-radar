import { isValidHistory, trimHistory } from '../lib/history'
import { BODY_MAX_BYTES, QUESTION_MAX_CHARS } from '../lib/limits'
import { callChatBackend } from './backend'
import { checkRateLimit } from './rate-limit'
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
  | 'rate_limited'
  | 'limiter_unavailable'
  | 'limiter_config_invalid'
  | 'internal_error'

const REPLY: Record<Exclude<Outcome, 'ok'>, [number, ChatErrorCode]> = {
  invalid_request: [400, 'invalid_request'],
  busy: [429, 'busy'],
  timeout: [504, 'timeout'],
  upstream_failure: [502, 'upstream_failure'],
  backend_forbidden: [503, 'unavailable'],
  backend_error: [503, 'unavailable'],
  missing_config: [503, 'unavailable'],
  rate_limited: [429, 'rate_limited'],
  limiter_unavailable: [503, 'unavailable'],
  limiter_config_invalid: [503, 'unavailable'],
  internal_error: [500, 'internal_error'],
}

const HEADERS = { 'content-type': 'application/json', 'cache-control': 'no-store' }

function failure(outcome: Exclude<Outcome, 'ok'>, retryAfterS?: number): Response {
  const [status, error] = REPLY[outcome]
  const headers: Record<string, string> = retryAfterS === undefined ? HEADERS : { ...HEADERS, 'retry-after': String(retryAfterS) }
  return new Response(JSON.stringify({ error }), { status, headers })
}

/** Extra fields on the log line: which limit fired, or which variable is invalid (never a value). */
interface LogExtra {
  limit?: string
  variable?: string
  retryAfterS?: number
}

/** One text-free line: outcome and duration only (never question, history, answer, credentials). */
function log(outcome: Outcome, start: number, extra: LogExtra): void {
  const line = JSON.stringify({
    event: 'chat_request',
    outcome,
    duration_ms: Math.round(performance.now() - start),
    ...(extra.limit ? { limit: extra.limit } : {}),
    ...(extra.variable ? { variable: extra.variable } : {}),
  })
  if (outcome === 'ok') console.info(line)
  else console.error(line)
}

function envValue(name: string): string | null {
  const value = process.env[name]?.trim()
  return value ? value : null
}

async function handle(request: Request, extra: LogExtra): Promise<Response | Exclude<Outcome, 'ok'>> {
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

  const verdict = await checkRateLimit(request.headers)
  if (verdict.kind === 'config_invalid') {
    extra.variable = verdict.variable
    return 'limiter_config_invalid'
  }
  if (verdict.kind === 'unavailable') return 'limiter_unavailable'
  if (verdict.kind === 'limited') {
    extra.limit = verdict.limit
    extra.retryAfterS = verdict.retryAfterS
    return 'rate_limited'
  }

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
 *  limiter check, one
 *  backend call, map to a fixed error code, log one line. Never throws. */
export async function handleChatRequest(request: Request): Promise<Response> {
  const start = performance.now()
  let outcome: Outcome
  let response: Response
  const extra: LogExtra = {}
  try {
    const result = await handle(request, extra)
    if (typeof result === 'string') {
      outcome = result
      response = failure(result, extra.retryAfterS)
    } else {
      outcome = 'ok'
      response = result
    }
  } catch {
    outcome = 'internal_error'
    response = failure('internal_error')
  }
  log(outcome, start, extra)
  return response
}

import { createHmac } from 'node:crypto'
import { isChatResponse } from '../lib/chat-response'
import type { RateLimitConfig } from './rate-limit-config'
import { saltFor } from './rate-limit'
import type { ChatResponse } from './types'

const VARIABLE = 'CHAT_CACHE_TTL_S'
const DEFAULT_TTL_S = 21_600
const MIN_TTL_S = 60
const MAX_TTL_S = 86_400
const STORE_TIMEOUT_MS = 1000
const KEY_PREFIX = 'chat-cache:{v1}:'

export type CacheSettings =
  | { kind: 'off' }
  | { kind: 'on'; ttlS: number }
  | { kind: 'invalid'; variable: string }

/** Reads `CHAT_CACHE_TTL_S` per request: unset is six hours, `0` is off, otherwise 60 to 86400. */
export function readCacheSettings(): CacheSettings {
  const raw = process.env[VARIABLE]?.trim()
  if (!raw) return { kind: 'on', ttlS: DEFAULT_TTL_S }
  if (!/^[0-9]+$/.test(raw)) return { kind: 'invalid', variable: VARIABLE }
  const n = Number(raw)
  if (n === 0) return { kind: 'off' }
  return n >= MIN_TTL_S && n <= MAX_TTL_S ? { kind: 'on', ttlS: n } : { kind: 'invalid', variable: VARIABLE }
}

/** Trim, collapse whitespace runs to one space, lower-case. Nothing else is changed. */
export function normalizeQuestion(question: string): string {
  return question.trim().replace(/\s+/g, ' ').toLowerCase()
}

/** The store key: a keyed one-way digest of the normalized question under its own prefix. The
 *  digest input carries a domain tag so it can never equal a limiter digest of the same text. */
export function cacheKey(question: string, config: RateLimitConfig): string {
  const digest = createHmac('sha256', saltFor(config)).update(`cache\0${normalizeQuestion(question)}`).digest('hex')
  return `${KEY_PREFIX}${digest}`
}

export type CacheRead = { kind: 'hit'; data: ChatResponse } | { kind: 'miss' } | { kind: 'error' }

const memory = new Map<string, { value: string; expiresAt: number }>()

function parseStored(value: unknown): CacheRead {
  if (typeof value !== 'string') return { kind: 'error' }
  try {
    const data: unknown = JSON.parse(value)
    return isChatResponse(data) ? { kind: 'hit', data: { answer: data.answer, sources: data.sources } } : { kind: 'error' }
  } catch {
    return { kind: 'error' }
  }
}

/** One REST command with a 1 s abort; returns the reply's `result`, or `undefined` on any failure. */
async function command(config: RateLimitConfig, args: string[]): Promise<{ result: unknown } | undefined> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), STORE_TIMEOUT_MS)
  try {
    const res = await fetch(config.restUrl as string, {
      method: 'POST',
      headers: { authorization: `Bearer ${config.restToken as string}`, 'content-type': 'application/json' },
      body: JSON.stringify(args),
      signal: controller.signal,
    })
    if (!res.ok) return undefined
    const body = (await res.json()) as { result?: unknown; error?: unknown } | null
    if (body === null || typeof body !== 'object' || body.error !== undefined) return undefined
    return { result: body.result }
  } catch {
    return undefined
  } finally {
    clearTimeout(timer)
  }
}

/** Never throws: every failure is `{ kind: 'error' }`, which the caller treats as a miss. */
export async function readCache(key: string, config: RateLimitConfig): Promise<CacheRead> {
  if (config.store === 'memory') {
    const entry = memory.get(key)
    if (!entry) return { kind: 'miss' }
    if (entry.expiresAt <= Date.now()) {
      memory.delete(key)
      return { kind: 'miss' }
    }
    return parseStored(entry.value)
  }
  const reply = await command(config, ['GET', key])
  if (reply === undefined) return { kind: 'error' }
  if (reply.result === null) return { kind: 'miss' }
  return parseStored(reply.result)
}

/** One write with its expiry. Never throws; `false` means it was not stored. */
export async function writeCache(key: string, data: ChatResponse, ttlS: number, config: RateLimitConfig): Promise<boolean> {
  const value = JSON.stringify({ answer: data.answer, sources: data.sources })
  if (config.store === 'memory') {
    const now = Date.now()
    for (const [k, entry] of memory) if (entry.expiresAt <= now) memory.delete(k)
    memory.set(key, { value, expiresAt: now + ttlS * 1000 })
    return true
  }
  const reply = await command(config, ['SET', key, value, 'EX', String(ttlS)])
  return reply !== undefined && reply.result === 'OK'
}

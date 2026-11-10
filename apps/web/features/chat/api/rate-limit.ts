import { createHmac, randomBytes } from 'node:crypto'
import { readRateLimitConfig } from './rate-limit-config'
import { visitorKey } from './visitor'

export type LimitName = 'burst' | 'daily' | 'global'

export type RateLimitResult =
  | { kind: 'admitted' }
  | { kind: 'limited'; limit: LimitName; retryAfterS: number }
  | { kind: 'unavailable' }
  | { kind: 'config_invalid'; variable: string }

const STORE_TIMEOUT_MS = 1000
const DAY_MS = 86_400_000
const DAY_EXPIRY_S = 172_800
const BURST = 1
const DAILY = 2
const GLOBAL = 4

/** Reads the three counters; if any is at its limit returns the bitmask and counts nothing,
 *  otherwise increments all three (expiry set when the key is created) and returns 0. */
const SCRIPT = `
local mask = 0
if (tonumber(redis.call('GET', KEYS[1])) or 0) >= tonumber(ARGV[1]) then mask = mask + 1 end
if (tonumber(redis.call('GET', KEYS[2])) or 0) >= tonumber(ARGV[2]) then mask = mask + 2 end
if (tonumber(redis.call('GET', KEYS[3])) or 0) >= tonumber(ARGV[3]) then mask = mask + 4 end
if mask > 0 then return mask end
if redis.call('INCR', KEYS[1]) == 1 then redis.call('EXPIRE', KEYS[1], ARGV[4]) end
if redis.call('INCR', KEYS[2]) == 1 then redis.call('EXPIRE', KEYS[2], ARGV[5]) end
if redis.call('INCR', KEYS[3]) == 1 then redis.call('EXPIRE', KEYS[3], ARGV[5]) end
return 0
`

interface Request {
  keys: [string, string, string]
  limits: [number, number, number]
  burstExpiryS: number
  now: number
}

const memory = new Map<string, { count: number; expiresAt: number }>()
let processSalt: string | null = null

function memoryCheck({ keys, limits, burstExpiryS, now }: Request): number {
  for (const [key, entry] of memory) if (entry.expiresAt <= now) memory.delete(key)
  let mask = 0
  keys.forEach((key, i) => {
    if ((memory.get(key)?.count ?? 0) >= limits[i]) mask += 1 << i
  })
  if (mask > 0) return mask
  keys.forEach((key, i) => {
    const entry = memory.get(key)
    if (entry) entry.count += 1
    else memory.set(key, { count: 1, expiresAt: now + (i === 0 ? burstExpiryS : DAY_EXPIRY_S) * 1000 })
  })
  return 0
}

async function upstashCheck(
  { keys, limits, burstExpiryS }: Request,
  url: string,
  token: string,
): Promise<number | null> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), STORE_TIMEOUT_MS)
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
      body: JSON.stringify([
        'EVAL', SCRIPT, 3, ...keys, ...limits.map(String), String(burstExpiryS), String(DAY_EXPIRY_S),
      ]),
      signal: controller.signal,
    })
    if (!res.ok) return null
    const body = (await res.json()) as { result?: unknown; error?: unknown } | null
    if (body === null || typeof body !== 'object' || body.error !== undefined) return null
    const r = body.result
    return typeof r === 'number' && Number.isInteger(r) && r >= 0 && r <= 7 ? r : null
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}

/** One limit decision for a validated request: config, visitor digest, one atomic store check. */
export async function checkRateLimit(headers: Headers): Promise<RateLimitResult> {
  const cfg = readRateLimitConfig()
  if (!cfg.ok) return { kind: 'config_invalid', variable: cfg.variable }
  const c = cfg.config

  let salt = c.salt
  if (salt === null) salt = processSalt ??= randomBytes(32).toString('hex')
  const digest = createHmac('sha256', salt).update(visitorKey(headers)).digest('hex')

  const now = Date.now()
  const nowS = Math.floor(now / 1000)
  const windowStartS = Math.floor(nowS / c.burstWindowS) * c.burstWindowS
  const day = new Date(now).toISOString().slice(0, 10).replaceAll('-', '')
  const request: Request = {
    keys: [`chat-rl:{v1}:b:${digest}:${windowStartS}`, `chat-rl:{v1}:d:${digest}:${day}`, `chat-rl:{v1}:g:${day}`],
    limits: [c.burst, c.daily, c.globalDaily],
    burstExpiryS: 2 * c.burstWindowS,
    now,
  }

  const mask =
    c.store === 'memory'
      ? memoryCheck(request)
      : await upstashCheck(request, c.restUrl as string, c.restToken as string)
  if (mask === null) return { kind: 'unavailable' }
  if (mask === 0) return { kind: 'admitted' }

  const dayEnd = (Math.floor(now / DAY_MS) + 1) * DAY_MS
  const burstEnd = (windowStartS + c.burstWindowS) * 1000
  const resets = [(mask & BURST) !== 0 ? burstEnd : 0, (mask & DAILY) !== 0 ? dayEnd : 0, (mask & GLOBAL) !== 0 ? dayEnd : 0]
  const retryAfterS = Math.max(1, Math.ceil((Math.max(...resets) - now) / 1000))
  const limit: LimitName = (mask & GLOBAL) !== 0 ? 'global' : (mask & DAILY) !== 0 ? 'daily' : 'burst'
  return { kind: 'limited', limit, retryAfterS }
}

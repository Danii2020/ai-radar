export interface RateLimitConfig {
  burst: number
  burstWindowS: number
  daily: number
  globalDaily: number
  store: 'memory' | 'upstash'
  salt: string | null
  restUrl: string | null
  restToken: string | null
}

export type ConfigResult = { ok: true; config: RateLimitConfig } | { ok: false; variable: string }

const MIN_SALT_CHARS = 32

function envValue(name: string): string | null {
  const value = process.env[name]?.trim()
  return value ? value : null
}

function whole(name: string, fallback: number, max: number): number | null {
  const value = envValue(name)
  if (value === null) return fallback
  if (!/^[0-9]+$/.test(value)) return null
  const n = Number(value)
  return n >= 1 && n <= max ? n : null
}

/** Reads and validates the limiter settings; names the first invalid variable, never its value. */
export function readRateLimitConfig(): ConfigResult {
  const bad = (variable: string): ConfigResult => ({ ok: false, variable })
  const burst = whole('CHAT_RATE_LIMIT_BURST', 5, 1_000_000)
  if (burst === null) return bad('CHAT_RATE_LIMIT_BURST')
  const burstWindowS = whole('CHAT_RATE_LIMIT_BURST_WINDOW_S', 60, 86_400)
  if (burstWindowS === null) return bad('CHAT_RATE_LIMIT_BURST_WINDOW_S')
  const daily = whole('CHAT_RATE_LIMIT_DAILY', 20, 1_000_000)
  if (daily === null) return bad('CHAT_RATE_LIMIT_DAILY')
  const globalDaily = whole('CHAT_RATE_LIMIT_GLOBAL_DAILY', 50, 1_000_000)
  if (globalDaily === null) return bad('CHAT_RATE_LIMIT_GLOBAL_DAILY')

  const onVercel = envValue('VERCEL') !== null
  const urlName = envValue('KV_REST_API_URL') !== null ? 'KV_REST_API_URL' : 'UPSTASH_REDIS_REST_URL'
  const tokenName = envValue('KV_REST_API_TOKEN') !== null ? 'KV_REST_API_TOKEN' : 'UPSTASH_REDIS_REST_TOKEN'
  const restUrl = envValue(urlName)
  const restToken = envValue(tokenName)

  // Table order: a short salt is named before the store and REST variables.
  const salt = envValue('CHAT_RATE_LIMIT_SALT')
  if (salt !== null && salt.length < MIN_SALT_CHARS) return bad('CHAT_RATE_LIMIT_SALT')

  const chosen = envValue('CHAT_RATE_LIMIT_STORE')
  if (chosen !== null && chosen !== 'memory' && chosen !== 'upstash') return bad('CHAT_RATE_LIMIT_STORE')
  const store = chosen ?? (onVercel || restUrl !== null ? 'upstash' : 'memory')
  if (store === 'memory' && onVercel) return bad('CHAT_RATE_LIMIT_STORE')

  if (store === 'upstash') {
    if (salt === null) return bad('CHAT_RATE_LIMIT_SALT')
    if (restUrl === null) return bad('KV_REST_API_URL')
    try {
      const protocol = new URL(restUrl).protocol
      if (protocol !== 'http:' && protocol !== 'https:') return bad('KV_REST_API_URL')
    } catch {
      return bad('KV_REST_API_URL')
    }
    if (restToken === null) return bad('KV_REST_API_TOKEN')
  }

  return { ok: true, config: { burst, burstWindowS, daily, globalDaily, store, salt, restUrl, restToken } }
}

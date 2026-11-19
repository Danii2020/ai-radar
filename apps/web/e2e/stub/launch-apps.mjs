// Builds the app once, then starts `next start` instances from that build
// (populated :3100, empty :3101, tight chat limits :3102, response cache :3103), each pointed explicitly at the local stub.
// FEED_API_BASE_URL and CHAT_API_BASE_URL are always set here, so .env.local's real URLs are
// never used; the chat credentials are obvious fakes (the stub only checks the SigV4 scope).
// Server stderr is redirected to e2e/.tmp/ for the stderr baseline.
import { spawn, spawnSync } from 'node:child_process'
import { mkdirSync, openSync, rmSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../..', import.meta.url))
const tmp = fileURLToPath(new URL('../.tmp/', import.meta.url))
mkdirSync(tmp, { recursive: true })
rmSync(`${root}.next/cache/fetch-cache`, { recursive: true, force: true })

const next = `${root}node_modules/next/dist/bin/next`
const baseEnv = { ...process.env, NEXT_TELEMETRY_DISABLED: '1' }
const chatEnv = (name) => ({
  CHAT_API_BASE_URL: `http://127.0.0.1:4010/${name}`,
  CHAT_API_ACCESS_KEY_ID: 'FAKE-E2E-KEY-ID-0001',
  CHAT_API_SECRET_ACCESS_KEY: 'fake-e2e-secret-do-not-use-0001',
})
// The chat visitor limiter (in-process store off Vercel, no service needed). The suites on 3100 and
// 3101 send many turns from the one loopback visitor, so their limits are out of reach; 3102 is the
// tight instance for e2e/chat-rate-limit.e2e.ts: 2 turns per visitor, in a window of one UTC day
// (aligned to the epoch, so it cannot roll over mid-run except at 00:00 UTC).
// The response cache is off on these three (CHAT_CACHE_TTL_S=0): their suites resend identical questions and
// expect a fresh stub answer each time. The fifth instance (3103, `cache`) has it on.
const HIGH_LIMITS = {
  CHAT_CACHE_TTL_S: '0',
  CHAT_RATE_LIMIT_BURST: '1000000',
  CHAT_RATE_LIMIT_DAILY: '1000000',
  CHAT_RATE_LIMIT_GLOBAL_DAILY: '1000000',
}
// 3103: cache on for an hour, a global ceiling of 1 live turn per UTC day, per-visitor limits out of reach.
const CACHE_LIMITS = {
  CHAT_CACHE_TTL_S: '3600',
  CHAT_RATE_LIMIT_BURST: '1000000',
  CHAT_RATE_LIMIT_DAILY: '1000000',
  CHAT_RATE_LIMIT_GLOBAL_DAILY: '1',
}
const TIGHT_LIMITS = {
  CHAT_CACHE_TTL_S: '0',
  CHAT_RATE_LIMIT_BURST: '2',
  CHAT_RATE_LIMIT_BURST_WINDOW_S: '86400',
  CHAT_RATE_LIMIT_DAILY: '1000',
  CHAT_RATE_LIMIT_GLOBAL_DAILY: '1000',
}
const build = spawnSync(process.execPath, [next, 'build'], {
  cwd: root,
  stdio: 'inherit',
  env: { ...baseEnv, FEED_API_BASE_URL: 'http://127.0.0.1:4010/populated', ...chatEnv('populated') },
})
if (build.status !== 0) process.exit(build.status ?? 1)
rmSync(`${root}.next/cache/fetch-cache`, { recursive: true, force: true })

const children = []
// empty and tight first: the populated port (3100) is the readiness signal for all three.
// [name, port, feed prefix, limits, chat prefix]: the cache instance has its own chat prefix, so the stub's
// per-prefix request count belongs to it alone.
for (const [name, port, feed, limits, chat = feed] of [
  ['empty', 3101, 'empty', HIGH_LIMITS],
  ['tight', 3102, 'populated', TIGHT_LIMITS],
  ['cache', 3103, 'populated', CACHE_LIMITS, 'cache'],
  ['populated', 3100, 'populated', HIGH_LIMITS],
]) {
  rmSync(`${tmp}app-${name}.stderr.log`, { force: true })
  children.push(
    spawn(process.execPath, [next, 'start', '-p', String(port), '-H', '127.0.0.1'], {
      cwd: root,
      stdio: ['ignore', 'inherit', openSync(`${tmp}app-${name}.stderr.log`, 'a')],
      env: { ...baseEnv, ...limits, FEED_API_BASE_URL: `http://127.0.0.1:4010/${feed}`, ...chatEnv(chat) },
    }),
  )
}
const stop = () => children.forEach((c) => c.kill('SIGTERM'))
process.on('SIGTERM', () => { stop(); process.exit(0) })
process.on('SIGINT', () => { stop(); process.exit(0) })
setInterval(() => {}, 1 << 30)

// Builds the app once, then starts two `next start` instances from that build
// (populated :3100, empty :3101), each pointed explicitly at the local stub.
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
const build = spawnSync(process.execPath, [next, 'build'], {
  cwd: root,
  stdio: 'inherit',
  env: { ...baseEnv, FEED_API_BASE_URL: 'http://127.0.0.1:4010/populated', ...chatEnv('populated') },
})
if (build.status !== 0) process.exit(build.status ?? 1)
rmSync(`${root}.next/cache/fetch-cache`, { recursive: true, force: true })

const children = []
// empty first: the populated port (3100) is the readiness signal for both.
for (const [name, port] of [['empty', 3101], ['populated', 3100]]) {
  rmSync(`${tmp}app-${name}.stderr.log`, { force: true })
  children.push(
    spawn(process.execPath, [next, 'start', '-p', String(port), '-H', '127.0.0.1'], {
      cwd: root,
      stdio: ['ignore', 'inherit', openSync(`${tmp}app-${name}.stderr.log`, 'a')],
      env: { ...baseEnv, FEED_API_BASE_URL: `http://127.0.0.1:4010/${name}`, ...chatEnv(name) },
    }),
  )
}
const stop = () => children.forEach((c) => c.kill('SIGTERM'))
process.on('SIGTERM', () => { stop(); process.exit(0) })
process.on('SIGINT', () => { stop(); process.exit(0) })
setInterval(() => {}, 1 << 30)

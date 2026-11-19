/**
 * Spec: web-chat-response-cache, O7 (AC1, AC3, AC5, AC10, AC11). The chat response cache against the cache
 * instance (port 3103: cache on for 3600 s, a global ceiling of ONE live turn per UTC day, per-visitor limits
 * out of reach) started by e2e/stub/launch-apps.mjs, with the in-process store and the chat stub. The stub's
 * per-prefix request counter proves a cached answer made no backend call. Offline, fake credentials, no
 * snapshots. The tests share one cache and one ceiling, so they run in order.
 */
import { expect, test, type APIRequestContext } from '@playwright/test'

test.use({ baseURL: 'http://127.0.0.1:3103' })
test.describe.configure({ mode: 'serial' })

const QUESTION = 'What is new in agent frameworks?'
const COUNT_URL = 'http://127.0.0.1:4010/_count/cache'

type Playwright = { request: { newContext: (options: object) => Promise<APIRequestContext> } }
const visitor = (playwright: Playwright, ip: string) =>
  playwright.request.newContext({ baseURL: 'http://127.0.0.1:3103', extraHTTPHeaders: { 'x-forwarded-for': ip } })
const backendCount = async (request: APIRequestContext) =>
  ((await (await request.get(COUNT_URL)).json()) as { count: number }).count
const turn = (who: APIRequestContext, question: string, history: unknown[] = []) =>
  who.post('/api/chat', { data: { question, history } })

test('a repeated first-turn question is answered from the cache with an identical response and no backend call (AC1, AC10)', async ({ playwright }) => {
  const a = await visitor(playwright, '198.51.100.101')
  const b = await visitor(playwright, '198.51.100.102')

  const live = await turn(a, QUESTION)
  expect(live.status()).toBe(200)
  expect(await backendCount(a)).toBe(1)

  const cached = await turn(b, `  ${QUESTION.toUpperCase()}  `)
  expect(cached.status()).toBe(200)
  expect(await cached.text()).toBe(await live.text())
  expect(cached.headers()['content-type']).toBe(live.headers()['content-type'])
  expect(cached.headers()['cache-control']).toBe('no-store')
  expect(await backendCount(a)).toBe(1)

  await a.dispose()
  await b.dispose()
})

test('a hit does not use the global ceiling, a new question does (AC5)', async ({ playwright }) => {
  const c = await visitor(playwright, '198.51.100.103')

  expect((await turn(c, QUESTION)).status()).toBe(200) // still a hit after the ceiling was used up
  const limited = await turn(c, 'And what about evaluation tooling?')
  expect(limited.status()).toBe(429)
  expect(await limited.text()).toBe('{"error":"rate_limited"}')
  expect(await backendCount(c)).toBe(1)

  await c.dispose()
})

test('a turn with a history is never served from the cache (AC3)', async ({ playwright }) => {
  const d = await visitor(playwright, '198.51.100.104')
  const history = [
    { role: 'user', text: 'hello' },
    { role: 'assistant', text: 'hi' },
  ]
  // The same question as the cached one, but with a history: it needs a live turn, and the ceiling is used up.
  expect((await turn(d, QUESTION, history)).status()).toBe(429)
  expect(await backendCount(d)).toBe(1)
  await d.dispose()
})

/**
 * Spec: web-chat-visitor-rate-limit, O7 (AC1, AC4, AC6, AC12, AC13). The chat route's visitor limit
 * against the tight-limit instance (port 3102: 2 turns per visitor in a window of one UTC day, other
 * limits out of reach) started by e2e/stub/launch-apps.mjs, using the in-process store and the
 * existing chat stub. Fully offline, fake credentials, no snapshots.
 *
 * Visitors are told apart by `x-forwarded-for`: `next start` only sets that header when the client
 * sent none (`??=` in node_modules/next/dist/server/base-server.js), so a client-supplied value is
 * kept. Each test uses its own address because the counters live for the whole run. If a future
 * Next.js stops keeping the header, the two-visitor test fails loudly.
 */
import { expect, test } from '@playwright/test'

test.use({ baseURL: 'http://127.0.0.1:3102' })

const LIMIT_COPY = "You've reached the chat limit for now. Please try again later."
const QUESTION = 'What is new in agent frameworks?'

const forwardedFor = (ip: string) => ({ extraHTTPHeaders: { 'x-forwarded-for': ip } })

test.describe('burst limit and response contract (AC1, AC6)', () => {
  test.use(forwardedFor('198.51.100.1'))

  test('one visitor gets two answers, then 429 rate_limited with the contract headers', async ({ request }) => {
    const turn = () => request.post('/api/chat', { data: { question: QUESTION, history: [] } })
    expect((await turn()).status()).toBe(200)
    expect((await turn()).status()).toBe(200)

    const limited = await turn()
    expect(limited.status()).toBe(429)
    expect(await limited.text()).toBe('{"error":"rate_limited"}')
    expect(limited.headers()['content-type']).toBe('application/json')
    expect(limited.headers()['cache-control']).toBe('no-store')
    expect(limited.headers()['retry-after']).toMatch(/^[1-9][0-9]*$/)
    expect(Number(limited.headers()['retry-after'])).toBeLessThanOrEqual(86_400)
  })
})

test.describe('one visitor does not block another (AC4)', () => {
  test('A is limited, then B is still answered', async ({ playwright }) => {
    const visitor = (ip: string) =>
      playwright.request.newContext({ baseURL: 'http://127.0.0.1:3102', extraHTTPHeaders: { 'x-forwarded-for': ip } })
    const a = await visitor('198.51.100.10')
    const b = await visitor('198.51.100.20')
    const turn = (who: typeof a) => who.post('/api/chat', { data: { question: QUESTION, history: [] } })

    expect((await turn(a)).status()).toBe(200)
    expect((await turn(a)).status()).toBe(200)
    expect((await turn(a)).status()).toBe(429)
    expect((await turn(b)).status()).toBe(200)

    await a.dispose()
    await b.dispose()
  })
})

test.describe('the limited state in the UI (AC12)', () => {
  test('two answers, then the limit copy; no code, status or URL; the question stays; Retry is offered', async ({ browser }) => {
    const context = await browser.newContext({ baseURL: 'http://127.0.0.1:3102', ...forwardedFor('198.51.100.30') })
    const page = await context.newPage()
    await page.goto('/')
    await page.getByTestId('chat-launcher').click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    const ask = async (question: string) => {
      await dialog.getByRole('textbox').fill(question)
      await dialog.getByRole('button', { name: /send/i }).click()
    }
    await ask(QUESTION)
    await expect(dialog.getByText(/agent frameworks keep converging/)).toHaveCount(1)
    await ask('And what about evaluation tooling?')
    await expect(dialog.getByText(/agent frameworks keep converging/)).toHaveCount(2)
    await expect(dialog.getByRole('alert')).toHaveCount(0)

    await ask('A third question')
    const alert = dialog.getByRole('alert')
    await expect(alert).toContainText(LIMIT_COPY)
    await expect(alert).not.toContainText(/429|http|rate_limited|retry-after|limiter|redis|upstash/i)
    await expect(dialog.getByRole('textbox')).toHaveValue('A third question')
    await expect(alert.getByRole('button', { name: /retry|try again/i })).toBeVisible()

    await context.close()
  })
})

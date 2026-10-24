/**
 * Spec: web-chat-ui, O8 (AC1, AC2, AC4, AC5, AC6, AC7, AC8, AC9). The chat widget against the
 * local stub of the chat API (e2e/stub/feed-api-stub.mjs, `POST /populated/v1/chat`). Fully
 * offline, fake credentials only. The stub answers 403 to anything that is not SigV4-signed
 * for us-east-1/execute-api, so a good answer here also proves the route signed its request.
 * No snapshots: nothing here touches e2e/__baseline__.
 */
import { expect, test, type Page } from '@playwright/test'
import { atBottom, expectInView, scrollArea, scrollTop, scrollUp, settledScrollTop } from './chat-scroll'

const QUESTION = 'What is new in agent frameworks?'

const toggle = (page: Page) => page.getByTestId('chat-launcher')
const dialog = (page: Page) => page.getByRole('dialog')

async function openChat(page: Page) {
  await page.goto('/')
  await toggle(page).click()
  await expect(dialog(page)).toBeVisible()
}

async function ask(page: Page, question: string) {
  await dialog(page).getByRole('textbox').fill(question)
  await dialog(page).getByRole('button', { name: /send/i }).click()
}

test.describe('chat widget (AC1)', () => {
  test('the button is visible and the panel is closed on first load; the button toggles it', async ({ page }) => {
    await page.goto('/')
    await expect(toggle(page)).toBeVisible()
    await expect(toggle(page)).toHaveAttribute('aria-expanded', 'false')
    await expect(dialog(page)).toHaveCount(0)

    await toggle(page).click()
    await expect(dialog(page)).toBeVisible()
    await expect(dialog(page).getByRole('textbox')).toBeVisible()
    await expect(dialog(page).getByRole('button', { name: /send/i })).toBeVisible()

    await toggle(page).click()
    await expect(dialog(page)).toHaveCount(0)
  })

  test('Escape closes the panel', async ({ page }) => {
    await openChat(page)
    await page.keyboard.press('Escape')
    await expect(dialog(page)).toHaveCount(0)
  })
})

test.describe('ask and answer (AC2, AC6, AC7)', () => {
  test('shows the stubbed answer with 3 numbered source links; one same-origin POST; clean console', async ({ page }) => {
    const consoleOutput: string[] = []
    page.on('console', (message) => consoleOutput.push(`${message.type()}: ${message.text()}`))
    page.on('pageerror', (error) => consoleOutput.push(`pageerror: ${error.message}`))
    const requests: string[] = []
    page.on('request', (request) => {
      if (request.method() === 'POST') requests.push(request.url())
    })

    await openChat(page)
    await ask(page, QUESTION)

    await expect(dialog(page).getByText(/agent frameworks keep converging/)).toBeVisible()
    await expect(dialog(page).getByText(QUESTION)).toBeVisible()
    await dialog(page).getByRole('button', { name: /sources \(3\)/i }).click()
    const links = dialog(page).getByRole('link')
    await expect(links).toHaveCount(3)
    for (const n of [1, 2, 3]) {
      const link = links.nth(n - 1)
      await expect(link).toHaveAttribute('href', `https://example.test/source-${n}`)
      await expect(link).toContainText(`[${n}]`)
      await expect(link).toContainText(`Stub source ${n}`)
      await expect(link).toContainText(`Stub Wire ${n}`)
    }

    expect(requests).toEqual(['http://127.0.0.1:3100/api/chat'])
    expect(consoleOutput).toEqual([])
  })

  test('the widget sits outside the FeedView root', async ({ page }) => {
    await openChat(page)
    const feedRoot = page.locator('[class*="-module__"][class*="__feedPage"]')
    await expect(feedRoot.getByTestId('chat-launcher')).toHaveCount(0)
    await expect(feedRoot.getByRole('dialog')).toHaveCount(0)
  })
})

test.describe('question limits (AC4)', () => {
  test('an over-long question shows an inline message and sends no request', async ({ page }) => {
    const chatRequests: string[] = []
    page.on('request', (request) => {
      if (request.url().includes('/api/chat')) chatRequests.push(request.url())
    })
    await openChat(page)
    await ask(page, 'q'.repeat(1001))

    await expect(dialog(page).getByRole('alert')).toBeVisible()
    expect(chatRequests).toEqual([])
  })
})

test.describe('failure states (AC5, AC9)', () => {
  test('429 shows the busy state, keeps the question, and retry sends it again', async ({ page }) => {
    await openChat(page)
    await ask(page, 'please throttle me')

    const alert = dialog(page).getByRole('alert')
    await expect(alert).toContainText(/busy/i)
    await expect(alert).not.toContainText(/429|execute-api|http/i)
    await expect(dialog(page).getByRole('textbox')).toHaveValue('please throttle me')

    const second = page.waitForRequest((request) => request.url().includes('/api/chat'))
    await alert.getByRole('button', { name: /retry|try again/i }).click()
    await second
    await expect(dialog(page).getByRole('alert')).toBeVisible()
  })

  test('504 shows its own timeout state, different from the busy copy', async ({ page }) => {
    await openChat(page)
    await ask(page, 'please throttle me')
    const busy = await dialog(page).getByRole('alert').innerText()

    await ask(page, 'this will timeout')
    await expect.poll(async () => dialog(page).getByRole('alert').innerText()).not.toBe(busy)
    await expect(dialog(page).getByRole('alert')).not.toContainText(/504|execute-api|http/i)
  })
})

test.describe('theme (AC8)', () => {
  for (const scheme of ['light', 'dark'] as const) {
    test(`the panel background is the --surface-card token in ${scheme} mode`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await openChat(page)
      const { panel, token } = await page.evaluate(() => {
        const probe = document.createElement('div')
        probe.style.backgroundColor = 'var(--surface-card)'
        document.body.appendChild(probe)
        const token = getComputedStyle(probe).backgroundColor
        probe.remove()
        const panel = getComputedStyle(document.querySelector('[role="dialog"]') as Element).backgroundColor
        return { panel, token }
      })
      expect(panel).toBe(token)
    })
  }
})

test.describe('desktop panel (1280 x 800, AC5)', () => {
  test.use({ viewport: { width: 1280, height: 800 } })

  test('desktop: the panel is 448 to 480 px wide and at most 640 px tall, with an AI RADAR header', async ({ page }) => {
    await openChat(page)
    const box = (await dialog(page).boundingBox())!
    expect(box.width).toBeGreaterThanOrEqual(448)
    expect(box.width).toBeLessThanOrEqual(480)
    expect(box.height).toBeLessThanOrEqual(640)
    expect(box.y).toBeGreaterThanOrEqual(0)
    await expect(dialog(page)).toContainText('AI RADAR')
  })

  test('desktop: the header Close button closes the panel and focuses the launcher', async ({ page }) => {
    await openChat(page)
    await dialog(page).getByRole('button', { name: 'Close chat' }).click()
    await expect(dialog(page)).toHaveCount(0)
    await expect(toggle(page)).toBeFocused()
  })

  test('desktop: launcher, Send and Close hit areas are at least 44 x 44', async ({ page }) => {
    await openChat(page)
    for (const target of [
      toggle(page),
      dialog(page).getByRole('button', { name: /send/i }),
      dialog(page).getByRole('button', { name: 'Close chat' }),
    ]) {
      const box = (await target.boundingBox())!
      expect(box.width).toBeGreaterThanOrEqual(44)
      expect(box.height).toBeGreaterThanOrEqual(44)
    }
  })

  for (const scheme of ['light', 'dark'] as const) {
    test(`desktop: Send uses the --link accent in ${scheme} mode`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await openChat(page)
      const { send, token } = await page.evaluate(() => {
        const probe = document.createElement('div')
        probe.style.backgroundColor = 'var(--link)'
        document.body.appendChild(probe)
        const token = getComputedStyle(probe).backgroundColor
        probe.remove()
        const button = document.querySelector('[role="dialog"] button[aria-label="Send"]') as Element
        return { send: getComputedStyle(button).backgroundColor, token }
      })
      expect(send).toBe(token)
    })
  }

  test('desktop latest: a reader who scrolled up is not moved; Jump to latest returns to the answer', async ({ page }) => {
    await openChat(page)
    await ask(page, 'tall one')
    await expect(dialog(page).getByText(/Paragraph 6\./)).toBeVisible()
    await ask(page, 'slow one')
    await expect(dialog(page).getByRole('status')).toBeVisible()
    await scrollUp(page)
    const before = await settledScrollTop(page)
    await expect(dialog(page).getByText(/Paragraph 6\./)).toHaveCount(2)
    expect(Math.abs((await scrollTop(page)) - before)).toBeLessThanOrEqual(2)
    const jump = dialog(page).getByRole('button', { name: 'Jump to latest' })
    await expect(jump).toBeVisible()
    await jump.click()
    await expect(jump).toHaveCount(0)
    await expect.poll(() => atBottom(page)).toBe(true)
    expect(await scrollArea(page).evaluate((el) => el.scrollHeight)).toBeGreaterThan(0)
  })

  test('desktop latest: each turn brings the question, then the loader, then the answer into view', async ({ page }) => {
    await openChat(page)
    for (const n of [1, 2, 3]) {
      await ask(page, `slow question ${n}`)
      await expectInView(page, dialog(page).getByText(`slow question ${n}`))
      await expect(dialog(page).getByRole('status')).toBeVisible()
      await expectInView(page, dialog(page).getByRole('status'))
      await expect(dialog(page).getByText(/Paragraph 6\./)).toHaveCount(n)
      await expectInView(page, dialog(page).getByText(/Paragraph 6\./).nth(n - 1))
    }
  })
})

test.describe('loader (AC7)', () => {
  test('loader: three animated dots while pending; no animation with reduced motion', async ({ page }) => {
    await openChat(page)
    await ask(page, 'slow please')
    const status = dialog(page).getByRole('status')
    await expect(status).toContainText('Thinking')
    const names = () => status.locator('span[aria-hidden="true"] > span').evaluateAll((dots) => dots.map((d) => getComputedStyle(d).animationName))
    const animated = await names()
    expect(animated).toHaveLength(3)
    for (const name of animated) expect(name).not.toBe('none')
    await expect(status).toHaveCount(0)
  })

  test('loader: reduced motion stops the dots animating', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await openChat(page)
    await ask(page, 'slow please')
    const status = dialog(page).getByRole('status')
    await expect(status).toBeVisible()
    const names = await status.locator('span[aria-hidden="true"] > span').evaluateAll((dots) => dots.map((d) => getComputedStyle(d).animationName))
    expect(names).toEqual(['none', 'none', 'none'])
  })
})

test.describe('composer (AC8)', () => {
  test('composer: Shift+Enter inserts a newline and sends nothing; Enter alone sends', async ({ page }) => {
    const chatRequests: string[] = []
    page.on('request', (request) => {
      if (request.url().includes('/api/chat')) chatRequests.push(request.url())
    })
    await openChat(page)
    const box = dialog(page).getByRole('textbox', { name: 'Your question' })
    await box.fill('a')
    await box.press('Shift+Enter')
    await box.pressSequentially('b')
    await expect(box).toHaveValue('a\nb')
    expect(chatRequests).toEqual([])
    await box.press('Enter')
    await expect(dialog(page).getByText(/agent frameworks keep converging/)).toBeVisible()
    expect(chatRequests).toHaveLength(1)
  })
})

test.describe('markdown (AC1, AC2)', () => {
  test('markdown: bold, lists and a code block render as elements inside the dialog', async ({ page }) => {
    await openChat(page)
    await ask(page, 'markdown please')
    await expect(dialog(page).locator('strong')).toHaveText('Agents')
    await expect(dialog(page).locator('ol li')).toHaveCount(2)
    await expect(dialog(page).locator('ul li')).toHaveCount(2)
    await expect(dialog(page).locator('code:not(pre code)')).toHaveText('code')
    await expect(dialog(page).locator('pre')).toContainText('const agent = build()')
    expect(await dialog(page).innerText()).not.toContain('**')
  })

  test('unsafe: nothing runs and no element or non-http(s) link comes from the answer', async ({ page }) => {
    const jsDialogs: string[] = []
    page.on('dialog', (d) => {
      jsDialogs.push(d.message())
      void d.dismiss()
    })
    await openChat(page)
    await ask(page, 'unsafe please')
    await expect(dialog(page).getByRole('link', { name: 'ok' })).toBeVisible()
    await expect(dialog(page).locator('script, img')).toHaveCount(0)
    const hrefs = await dialog(page).locator('a[href]').evaluateAll((links) => links.map((l) => l.getAttribute('href') ?? ''))
    expect(hrefs.length).toBeGreaterThan(0)
    for (const href of hrefs) expect(href).toMatch(/^https?:/)
    expect(jsDialogs).toEqual([])
  })
})

test.describe('suggestions (AC9)', () => {
  test('suggestion: pressing one sends it and the stub answer follows', async ({ page }) => {
    await openChat(page)
    await dialog(page).getByRole('button', { name: /latest research on AI agents/ }).click()
    await expect(dialog(page).getByText('What is the latest research on AI agents?')).toBeVisible()
    await expect(dialog(page).getByText(/agent frameworks keep converging/)).toBeVisible()
  })
})

/**
 * Spec: web-chat-ui-polish, O3 / O8 (AC3, AC4, AC10). Layout checks that need a real layout engine
 * (jsdom has none): the phone sheet stays on screen, nothing overflows horizontally, and a long
 * feed URL wraps. Phone viewport 375 by 667. Offline against the local stub; no snapshots.
 */
import { expect, test, type Page } from '@playwright/test'
import { expectInView, atBottom, scrollTop, scrollUp, settledScrollTop } from './chat-scroll'
// Must match LONG_URL in e2e/stub/feed-api-stub.mjs (not imported: the stub uses import.meta).
const LONG_URL = `https://example.invalid/${'a'.repeat(300 - 'https://example.invalid/'.length)}`
const PHONE = { width: 375, height: 667 }

const dialog = (page: Page) => page.getByRole('dialog')

async function openChat(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: 'Open chat' }).click()
  await expect(dialog(page)).toBeVisible()
}

async function ask(page: Page, question: string) {
  await dialog(page).getByRole('textbox').fill(question)
  await dialog(page).getByRole('button', { name: /send/i }).click()
}

async function expectBoxOnScreen(page: Page) {
  const box = await dialog(page).boundingBox()
  expect(box).not.toBeNull()
  const { x, y, width, height } = box!
  console.log(`dialog box: x=${x} y=${y} width=${width} height=${height}`)
  expect(x).toBeGreaterThanOrEqual(0)
  expect(x + width).toBeLessThanOrEqual(PHONE.width)
  expect(y).toBeGreaterThanOrEqual(0)
  expect(y + height).toBeLessThanOrEqual(PHONE.height)
}

async function expectNoHorizontalOverflow(page: Page) {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth)
}

test.describe('phone layout (375 x 667)', () => {
  test.use({ viewport: PHONE })

  test('the open panel is a sheet that stays on screen, with header and composer visible', async ({ page }) => {
    await openChat(page)
    await expectBoxOnScreen(page)
    await expect(dialog(page).getByText(/AI RADAR/i).first()).toBeVisible()
    await expect(dialog(page).getByRole('textbox')).toBeVisible()
    await expect(dialog(page).getByRole('button', { name: /send/i })).toBeVisible()
    await expectNoHorizontalOverflow(page)
  })

  test('a very long URL in a link, a source and a code block wraps inside the sheet', async ({ page }) => {
    await openChat(page)
    await ask(page, 'longurl please')
    await expect(dialog(page).getByText(/the long link/)).toBeVisible()
    await dialog(page).getByRole('button', { name: /sources \(1\)/i }).click()
    await expect(dialog(page).getByRole('link', { name: /Long source/ })).toBeVisible()

    await expectBoxOnScreen(page)
    await expectNoHorizontalOverflow(page)
    const dialogBox = (await dialog(page).boundingBox())!
    const pre = (await dialog(page).locator('pre').boundingBox())!
    expect(pre.x + pre.width).toBeLessThanOrEqual(dialogBox.x + dialogBox.width + 1)
    expect(await dialog(page).locator('pre').evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true)
    for (const link of await dialog(page).getByRole('link').all()) {
      const box = (await link.boundingBox())!
      expect(box.x + box.width).toBeLessThanOrEqual(dialogBox.x + dialogBox.width + 1)
    }
  })
})

test.describe('feed card on a phone (AC10)', () => {
  test.use({ viewport: PHONE })

  test('a 300-character URL wraps inside the card with no horizontal overflow', async ({ page }) => {
    await page.goto('/?tag=long-url')
    const link = page.locator('a[class*="urlLine"]')
    await expect(link).toHaveText(LONG_URL)
    const metrics = await link.evaluate((el) => {
      const box = el.getBoundingClientRect()
      const card = (el.closest('article') ?? el.parentElement!).getBoundingClientRect()
      return {
        height: box.height,
        lineHeight: parseFloat(getComputedStyle(el).lineHeight) || parseFloat(getComputedStyle(el).fontSize) * 1.2,
        cardRight: card.right,
      }
    })
    console.log(`urlLine: ${JSON.stringify(metrics)}`)
    expect(metrics.height).toBeGreaterThan(metrics.lineHeight * 2)
    expect(metrics.cardRight).toBeLessThanOrEqual(PHONE.width)
    await expectNoHorizontalOverflow(page)
  })
})

test.describe('latest message stays in view (phone, AC3)', () => {
  test.use({ viewport: PHONE })

  test('latest: three tall turns each end with the question and the answer inside the message area', async ({ page }) => {
    await openChat(page)
    for (const n of [1, 2, 3]) {
      await ask(page, `tall question ${n}`)
      await expect(dialog(page).getByText(/Paragraph 6\./)).toHaveCount(n)
      await expectInView(page, dialog(page).getByText(/Paragraph 6\./).nth(n - 1))
    }
  })

  test('latest: a reader who scrolled up is not moved, sees Jump to latest, and the button returns to the answer', async ({ page }) => {
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
  })
})

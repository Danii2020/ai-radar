/**
 * Spec: web-chat-swipe-handle, O1 to O5 (AC1 to AC7, AC9). The phone edge tab and its threshold swipes,
 * with trusted CDP touch input, against the local stub. Offline, fake credentials only; every
 * request must stay on 127.0.0.1 and the console must stay empty. No snapshots.
 */
import { expect, test as base, type Page } from '@playwright/test'
import { scrollArea } from './chat-scroll'
import { swipe } from './touch'

const PHONE = { width: 375, height: 667 }
const DESKTOP = { width: 1280, height: 800 }

const test = base.extend<{ monitor: void }>({
  monitor: [
    async ({ page }, use) => {
      const consoleOutput: string[] = []
      const urls: string[] = []
      page.on('console', (m) => consoleOutput.push(`${m.type()}: ${m.text()}`))
      page.on('pageerror', (e) => consoleOutput.push(`pageerror: ${e.message}`))
      page.on('request', (r) => urls.push(r.url()))
      await use()
      expect(consoleOutput).toEqual([])
      expect(urls.filter((u) => !u.startsWith('http://127.0.0.1') && !u.startsWith('data:'))).toEqual([])
    },
    { auto: true },
  ],
})

const launcher = (page: Page) => page.getByTestId('chat-launcher')
const dialog = (page: Page) => page.getByRole('dialog')

async function ask(page: Page, question: string) {
  await dialog(page).getByRole('textbox').fill(question)
  await dialog(page).getByRole('button', { name: /send/i }).click()
}

test.describe('phone (375 x 667)', () => {
  test.use({ viewport: PHONE, hasTouch: true })

  test('edge tab: flush right, slim, in the lower third, icon only, no overflow, visible focus ring', async ({ page }) => {
    await page.goto('/')
    const tab = launcher(page)
    await expect(tab).toHaveAttribute('aria-expanded', 'false')
    await expect(tab).toHaveAccessibleName('Open chat')
    await expect(tab).toHaveAttribute('aria-controls', /.+/)
    const box = (await tab.boundingBox())!
    expect(box.x + box.width).toBeGreaterThanOrEqual(PHONE.width - 1)
    expect(box.x + box.width).toBeLessThanOrEqual(PHONE.width)
    expect(box.width).toBeGreaterThanOrEqual(20)
    expect(box.width).toBeLessThanOrEqual(24)
    expect(box.height).toBeGreaterThanOrEqual(44)
    expect(box.y).toBeGreaterThanOrEqual((2 / 3) * PHONE.height - 1)
    expect(box.y + box.height).toBeLessThanOrEqual(PHONE.height)
    expect(await tab.evaluate((el) => (el as HTMLElement).innerText)).not.toMatch(/chat/i)
    await expect(tab.locator('svg[aria-hidden="true"]')).toBeVisible()
    const overflow = await page.evaluate(() => ({
      s: document.documentElement.scrollWidth,
      c: document.documentElement.clientWidth,
    }))
    expect(overflow.s).toBeLessThanOrEqual(overflow.c)

    await tab.focus()
    expect(await tab.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe('none')
    const focused = (await tab.boundingBox())!
    expect(focused.x + focused.width).toBeLessThanOrEqual(PHONE.width)
  })

  test('tap and keyboard: open by tap and Enter, every close returns focus to the tab', async ({ page }) => {
    await page.goto('/')
    await launcher(page).tap()
    await expect(dialog(page)).toBeVisible()
    await expect(dialog(page).getByRole('textbox')).toBeFocused()
    await expect(launcher(page)).toHaveAttribute('aria-expanded', 'true')
    await expect(launcher(page)).toBeHidden()

    await page.keyboard.press('Escape')
    await expect(dialog(page)).toHaveCount(0)
    await expect(launcher(page)).toBeFocused()

    await page.keyboard.press('Enter')
    await expect(dialog(page)).toBeVisible()
    await dialog(page).getByRole('button', { name: /close/i }).first().click()
    await expect(dialog(page)).toHaveCount(0)
    await expect(launcher(page)).toBeFocused()
  })

  test('swipe left opens the sheet and it stays open after the trailing click', async ({ page }) => {
    await page.goto('/')
    await swipe(page, launcher(page), -60, 8)
    await expect(dialog(page)).toBeVisible()
    await expect(dialog(page).getByRole('textbox')).toBeFocused()
    await page.waitForTimeout(300)
    await expect(dialog(page)).toBeVisible()
  })

  test('does not open: short, rightward and mostly vertical gestures, and the page still scrolls', async ({ page }) => {
    await page.goto('/')
    expect(await launcher(page).evaluate((el) => getComputedStyle(el).touchAction)).toBe('pan-y')
    await swipe(page, launcher(page), -30, 0)
    await swipe(page, launcher(page), 60, 0)
    await expect(dialog(page)).toHaveCount(0)

    expect(await page.evaluate(() => window.scrollY)).toBe(0)
    await swipe(page, launcher(page), -20, -200)
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0)
    await expect(dialog(page)).toHaveCount(0)
  })

  test('swipe right on the sheet closes it, keeps the conversation, and ignores code blocks', async ({ page }) => {
    await page.goto('/')
    await launcher(page).tap()
    await ask(page, 'longurl please')
    await expect(dialog(page).getByText(/the long link/)).toBeVisible()

    const pre = dialog(page).locator('pre')
    expect(await pre.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true)
    await swipe(page, pre, 80, 0)
    await expect(dialog(page)).toBeVisible()

    await swipe(page, scrollArea(page), 80, 10)
    await expect(dialog(page)).toHaveCount(0)
    await expect(launcher(page)).toBeFocused()

    await launcher(page).tap()
    await expect(dialog(page).getByText(/the long link/)).toBeVisible()
  })

  test('reduced motion: nothing animates, and swipe left still opens', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto('/')
    const motion = (sel: () => ReturnType<typeof launcher>) =>
      sel().evaluate((el) => {
        const s = getComputedStyle(el)
        return { t: s.transitionDuration.split(',').map((v) => v.trim()), a: s.animationName }
      })
    const tab = await motion(() => launcher(page))
    expect(tab.t.every((v) => v === '0s')).toBe(true)
    expect(tab.a).toBe('none')
    await swipe(page, launcher(page), -60, 0)
    await expect(dialog(page)).toBeVisible()
    const sheet = await motion(() => dialog(page) as unknown as ReturnType<typeof launcher>)
    expect(sheet.t.every((v) => v === '0s')).toBe(true)
    expect(sheet.a).toBe('none')
  })
})

test.describe('desktop (1280 x 800) is unchanged', () => {
  test.use({ viewport: DESKTOP, hasTouch: true })

  test('desktop: the pill shows "Chat", no icon, bottom right, 44 x 44 at least; touch drags do nothing', async ({ page }) => {
    await page.goto('/')
    const tab = launcher(page)
    expect(await tab.evaluate((el) => (el as HTMLElement).innerText)).toMatch(/chat/i)
    await expect(tab.locator('svg')).toBeHidden()
    const box = (await tab.boundingBox())!
    expect(box.width).toBeGreaterThanOrEqual(44)
    expect(box.height).toBeGreaterThanOrEqual(44)
    expect(box.x + box.width).toBeGreaterThan(DESKTOP.width / 2)
    expect(box.y + box.height).toBeGreaterThan(DESKTOP.height / 2)

    await swipe(page, tab, -60, 0)
    await expect(dialog(page)).toHaveCount(0)

    await tab.click()
    await expect(dialog(page)).toBeVisible()
    await swipe(page, dialog(page), 80, 0)
    await expect(dialog(page)).toBeVisible()
  })
})

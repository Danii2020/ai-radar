import { expect, type Locator, type Page } from '@playwright/test'

const dialog = (page: Page) => page.getByRole('dialog')

/** True when the element is inside the scroll area; false (never throws) while it is missing or detached. */
export async function isInView(page: Page, target: Locator) {
  try {
    const box = await target.boundingBox({ timeout: 500 })
    const area = await scrollArea(page).boundingBox({ timeout: 500 })
    if (!box || !area) return false
    return box.y >= area.y - 1 && box.y + box.height <= area.y + area.height + 1
  } catch {
    return false
  }
}

export async function expectInView(page: Page, target: Locator) {
  // The view follows with a smooth animation, and the pending question's node is replaced when the
  // answer lands, so re-resolve and poll until the element is present and inside the scroll area.
  await expect.poll(() => isInView(page, target)).toBe(true)
}

/** Resolves once scrollTop has stopped changing (wheel scrolling is animated). */
export async function settledScrollTop(page: Page) {
  let last = -1
  await expect
    .poll(async () => {
      const now = await scrollTop(page)
      const stable = now === last
      last = now
      return stable
    })
    .toBe(true)
  return last
}

export const scrollArea = (page: Page) => dialog(page).locator('[aria-live="polite"]').locator('xpath=..')
export const scrollTop = (page: Page) => scrollArea(page).evaluate((el) => el.scrollTop)
export const atBottom = (page: Page) =>
  scrollArea(page).evaluate((el) => el.scrollTop + el.clientHeight >= el.scrollHeight - 2)
export async function scrollUp(page: Page) {
  const box = (await scrollArea(page).boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.wheel(0, -600)
  await expect.poll(() => atBottom(page)).toBe(false)
}

/**
 * Trusted touch input for Chromium: `Input.dispatchTouchEvent` through a CDP session, so
 * `touch-action` and pointer capture apply as on a real phone. Playwright has no swipe API.
 */
import type { Locator, Page } from '@playwright/test'

/** Touch down at (x, y), move in a few steps by (dx, dy), lift. */
export async function swipeFrom(page: Page, x: number, y: number, dx: number, dy: number, steps = 5) {
  const cdp = await page.context().newCDPSession(page)
  try {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] })
    for (let i = 1; i <= steps; i++) {
      await cdp.send('Input.dispatchTouchEvent', {
        type: 'touchMove',
        touchPoints: [{ x: x + (dx * i) / steps, y: y + (dy * i) / steps }],
      })
    }
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  } finally {
    await cdp.detach()
  }
}

/** Swipe starting at the centre of `target`. */
export async function swipe(page: Page, target: Locator, dx: number, dy: number) {
  const box = await target.boundingBox()
  if (!box) throw new Error('swipe target has no box')
  await swipeFrom(page, box.x + box.width / 2, box.y + box.height / 2, dx, dy)
}

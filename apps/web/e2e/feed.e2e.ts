/**
 * Spec: feed-structure-refactor (AC7, AC10) -- characterization suite.
 * Captured against the pre-refactor tree into e2e/__baseline__/, then compared
 * unchanged after the refactor. Never run with --update-snapshots afterwards.
 *
 * Compared per scenario: normalized FeedView DOM, computed styles of a fixed
 * selector set, browser console output (must hold no errors/warnings), and
 * the server-side `feed_fetch_failed` stderr lines for error scenarios.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test, type Page } from '@playwright/test'
import fixtures from './fixtures/populated.json'

const POPULATED = 'http://127.0.0.1:3100'
const EMPTY = 'http://127.0.0.1:3101'
const NEXT_CURSOR: string = fixtures.next_cursor
// Playwright runs from apps/web.
const STDERR_LOG = join(process.cwd(), 'e2e/.tmp/app-populated.stderr.log')

// Locals whose computed style is recorded (CSS-module class "<file>-module__<hash>__<local>").
const STYLE_LOCALS = [
  'feedPage', 'masthead', 'wordmark', 'tagline', 'feedList', 'card', 'cardTitle',
  'cardTitleLink', 'urlLine', 'summary', 'takeaways', 'cardTags', 'chip', 'chipActive',
  'chipRow', 'chipNote', 'clearLink', 'cardFoot', 'badge', 'meta', 'metaSep', 'pagerBar',
  'pagerLink', 'state', 'stateError', 'stateHeading', 'stateBody', 'stateActions',
]
const STYLE_PROPS = [
  'color', 'backgroundColor', 'borderTopWidth', 'borderTopStyle', 'borderTopColor',
  'borderLeftWidth', 'borderLeftColor', 'borderBottomWidth', 'borderRadius',
  'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
  'marginTop', 'marginRight', 'marginBottom', 'marginLeft',
  'fontSize', 'fontWeight', 'fontFamily', 'lineHeight', 'letterSpacing', 'textTransform',
  'textDecorationLine', 'display', 'gap', 'justifyContent', 'alignItems', 'flexDirection',
  'width', 'maxWidth',
]

async function captureRoot(page: Page) {
  return page.evaluate(
    ({ locals, props }) => {
      // The FeedView root: the element carrying the `feedPage` module class.
      const root = document.querySelector('[class*="-module__"][class*="__feedPage"]') as HTMLElement
      // "<file>-module__<hash>__<local>" -> "<file>-module__<local>"; nothing else is rewritten.
      const classRe = /([\w-]+-module)__[A-Za-z0-9-]+?__([A-Za-z0-9-]+)/g
      const dom = root.outerHTML.replace(classRe, '$1__$2')

      const localsOf = (el: Element) =>
        Array.from(el.classList)
          .map((c) => /^[\w-]+-module__[A-Za-z0-9-]+?__([A-Za-z0-9-]+)$/.exec(c)?.[1])
          .filter((c): c is string => c !== undefined)
      const styles: Record<string, Record<string, string>> = {}
      const record = (key: string, el: Element) => {
        if (styles[key]) return
        const cs = getComputedStyle(el) as unknown as Record<string, string>
        const out: Record<string, string> = {}
        for (const p of props) out[p] = cs[p]
        out['--accent'] = getComputedStyle(el).getPropertyValue('--accent').trim()
        styles[key] = out
      }
      for (const el of [root, ...Array.from(root.querySelectorAll('*'))]) {
        for (const local of localsOf(el)) {
          if (!locals.includes(local)) continue
          const type = el.getAttribute('data-type')
          record(type ? `${local}[${type}]` : local, el)
        }
      }
      const ordered = Object.fromEntries(Object.keys(styles).sort().map((k) => [k, styles[k]]))
      return { dom, styles: JSON.stringify(ordered, null, 2) + '\n' }
    },
    { locals: STYLE_LOCALS, props: STYLE_PROPS },
  )
}

interface Scenario { name: string; origin: string; path: string; errorTag?: string }

const SCENARIOS: Scenario[] = [
  { name: 'ok-first-page', origin: POPULATED, path: '/' },
  { name: 'ok-last-page', origin: POPULATED, path: `/?cursor=${encodeURIComponent(NEXT_CURSOR)}` },
  { name: 'tag-promoted', origin: POPULATED, path: '/?tag=agents' },
  { name: 'tag-not-promoted', origin: POPULATED, path: '/?tag=rare-x' },
  { name: 'tag-untrimmed', origin: POPULATED, path: '/?tag=%20agents%20' },
  { name: 'empty-first-page', origin: EMPTY, path: '/' },
  { name: 'filtered-empty-no-cards-tagged', origin: POPULATED, path: '/?tag=no-such-tag' },
  { name: 'filtered-empty-drained', origin: POPULATED, path: '/?tag=drain' },
  { name: 'drain-finds-late-page', origin: POPULATED, path: '/?tag=late' },
  { name: 'error-http', origin: POPULATED, path: '/?tag=http-500', errorTag: 'http-500' },
  { name: 'error-http-with-cursor', origin: POPULATED, path: '/?tag=http-500&cursor=a%2Bb%2Fc%3D', errorTag: 'http-500' },
  { name: 'error-malformed', origin: POPULATED, path: '/?tag=malformed', errorTag: 'malformed' },
  { name: 'error-network', origin: POPULATED, path: '/?tag=network', errorTag: 'network' },
  { name: 'error-network-with-cursor', origin: POPULATED, path: '/?tag=network&cursor=abc', errorTag: 'network' },
  { name: 'edge-whitespace-tag', origin: POPULATED, path: '/?tag=%20%20%20' },
  { name: 'edge-repeated-tag', origin: POPULATED, path: '/?tag=agents&tag=llm' },
  { name: 'edge-empty-cursor', origin: POPULATED, path: '/?cursor=' },
]

test.beforeAll(async ({ request }) => {
  // The empty instance starts just before the populated one; wait for it.
  await expect
    .poll(async () => (await request.get(EMPTY).catch(() => undefined))?.status(), { timeout: 60_000 })
    .toBe(200)
})

/** Distinct `feed_fetch_failed` server lines for one tag (deduped: Next may
 *  re-render the same URL, e.g. on prefetch), per cursor presence. */
function stderrLinesFor(tag: string, hasCursor: boolean): string[] {
  const lines = readFileSync(STDERR_LOG, 'utf-8')
    .split('\n')
    .filter((l) => l.includes('"event":"feed_fetch_failed"') && l.includes(`"tag":"${tag}"`) && l.includes(`"has_cursor":${hasCursor}`))
  return [...new Set(lines)].sort()
}

test.describe('rendered output matches the pre-refactor baseline', () => {
  for (const scenario of SCENARIOS) {
    test(scenario.name, async ({ page }) => {
      const messages: string[] = []
      page.on('console', (m) => messages.push(`${m.type()}: ${m.text()}`))
      page.on('pageerror', (e) => messages.push(`pageerror: ${e.message}`))

      await page.goto(scenario.origin + scenario.path)
      await page.waitForLoadState('networkidle')

      const { dom, styles } = await captureRoot(page)
      expect(dom).toMatchSnapshot(['dom', `${scenario.name}.html`])
      expect(styles).toMatchSnapshot(['styles', `${scenario.name}.json`])

      expect(messages.filter((m) => /^(error|warning|pageerror)/.test(m))).toEqual([])
      expect(JSON.stringify(messages, null, 2) + '\n').toMatchSnapshot([
        'console',
        `${scenario.name}.json`,
      ])

      if (scenario.errorTag) {
        const tag = scenario.errorTag
        const hasCursor = scenario.path.includes('cursor=')
        await expect.poll(() => stderrLinesFor(tag, hasCursor).length, { timeout: 5_000 }).toBeGreaterThan(0)
        expect(stderrLinesFor(tag, hasCursor).join('\n') + '\n').toMatchSnapshot(['stderr', `${scenario.name}.txt`])
      }
    })
  }
})

test.describe('content comes from the stub, never from AWS', () => {
  test('first page renders the stub fixture titles', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: 'E2E fixture card 1', exact: true })).toBeVisible()
  })
})

test.describe('navigation', () => {
  test('a promoted chip leads to ?tag= and shows only tagged cards', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('link', { name: 'Filter by tag agents' }).click()
    await expect(page).toHaveURL(`${POPULATED}/?tag=agents`)
    await expect(page.getByTestId('feed-list')).toBeVisible()
  })

  test("a card's inline tag filters, even when the tag is not a promoted chip", async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: 'Filter by tag rare-x' })).toHaveCount(0)
    await page.locator('article').first().getByRole('link', { name: 'rare-x', exact: true }).click()
    await expect(page).toHaveURL(`${POPULATED}/?tag=rare-x`)
    await expect(page.getByRole('link', { name: 'Filter by tag rare-x' })).toBeVisible()
  })

  test('the active-tag chip stays on the filter and "All cards" clears it', async ({ page }) => {
    await page.goto('/?tag=agents')
    await page.getByRole('link', { name: 'Filter by tag agents' }).click()
    await expect(page).toHaveURL(`${POPULATED}/?tag=agents`)
    await page.getByRole('link', { name: 'All cards' }).click()
    await expect(page).toHaveURL(`${POPULATED}/`)
  })

  test('Next page carries next_cursor byte-identical; First page and Back work', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('link', { name: 'Next page →' }).click()
    await expect(page).toHaveURL(/cursor=/)
    expect(new URL(page.url()).searchParams.get('cursor')).toBe(NEXT_CURSOR)
    await expect(page.getByRole('link', { name: 'E2E fixture card 16', exact: true })).toBeVisible()

    await page.goBack()
    await expect(page).toHaveURL(`${POPULATED}/`)
    await expect(page.getByRole('link', { name: 'E2E fixture card 1', exact: true })).toBeVisible()

    await page.getByRole('link', { name: 'Next page →' }).click()
    await page.getByRole('link', { name: '← First page' }).click()
    await expect(page).toHaveURL(`${POPULATED}/`)
  })

  test('error page: "Back to the first page" appears for http with a cursor', async ({ page }) => {
    await page.goto('/?tag=http-500&cursor=abc')
    await page.getByRole('link', { name: 'Back to the first page' }).click()
    await expect(page).toHaveURL(`${POPULATED}/?tag=http-500`)
  })
})

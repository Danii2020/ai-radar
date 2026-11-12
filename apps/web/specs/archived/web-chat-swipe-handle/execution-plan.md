# Execution Plan: Web Chat Swipe Handle

## Guidance consulted
- `apps/web/AGENTS.md` (WEB-1 to WEB-9, barrel-only imports, the dependency rule, `high-value-tests`, Playwright
  e2e tier) and the repo-root `CLAUDE.md` (two harness roots, monotonic ADR numbers).
- `harny-sync` lookup: `specs/current/_index.md`, `specs/current/web-chat.md` (WEBCHAT-1, -5, -10, -11, -12,
  invariants 1 to 4, WEBCHAT-R9) and `specs/current/web-feed.md` (WEB-9 scope: only `globals.css` and
  `feed.module.css` are byte-verbatim copies; chat CSS is token-only under WEBCHAT-10).
- Code read: `features/chat/components/chat-widget.tsx`, `chat-panel.tsx`, `chat.module.css`,
  `chat-widget.test.tsx`, `chat-css.test.ts`, `features/chat/conventions.test.ts`, `app/page.tsx`,
  `features/feed/components/feed.module.css` (the page gutter is `--space-5`, 24 px, on every width, so a
  24 px tab sits in the gutter and covers no card), `app/globals.css` tokens.
- Tests read: `e2e/chat.e2e.ts`, `e2e/layout.e2e.ts`, `e2e/chat-rate-limit.e2e.ts`, `e2e/chat-scroll.ts`,
  `e2e/feed.e2e.ts` (the baseline captures only the feed root at the default desktop viewport, so it is not
  affected), `playwright.config.ts` (Chromium only), `vitest.config.ts` (jsdom; jsdom ships `PointerEvent`).
- Playwright 1.64.1 docs (Context7 `/microsoft/playwright/v1.64.1`): there is no built-in touch-swipe API;
  `hasTouch` enables `locator.tap()`; touch gestures are emulated by dispatching events. This plan uses a Chromium
  CDP session (`Input.dispatchTouchEvent`) so the touch input is trusted and `touch-action` applies.
- Platform note (web search): Android gesture navigation and iOS Safari reserve edge swipes; pages cannot opt out
  (intent Q1).

## Ownership
- `apps/web/features/chat/components/` (`chat-widget.tsx`, `chat-panel.tsx` if the close gesture is attached
  there, `chat.module.css`, `chat-widget.test.tsx`), optionally one new pure module in `features/chat/lib/`, a new
  e2e file and helper under `apps/web/e2e/`, and the chat line in `apps/web/AGENTS.md`.
- Affected `specs/current` capabilities: `web-chat` (WEBCHAT-1 amended on phones; new phone gesture requirement;
  WEBCHAT-12 widened to cover gestures).

## Binding constraints
- One launcher element at every width; keep `data-testid="chat-launcher"`, `aria-expanded`, `aria-controls`, the
  accessible names "Open chat" / "Close chat", and the existing focus-return effect (source: WEBCHAT-1; consumers
  `chat.e2e.ts`, `layout.e2e.ts`, `chat-rate-limit.e2e.ts`, `chat-widget.test.tsx`).
- The phone breakpoint is the existing `@media (max-width: 640px)`; the gesture code uses the same query string,
  so CSS and JS cannot disagree (source: intent AC1, AC7).
- Gestures are recognized only for `pointerType` `touch` or `pen` and only while the phone query matches (source:
  intent AC4, AC7).
- A recognized swipe is not followed by a toggle from the browser's trailing `click` (source: intent AC3).
- Colours, padding, margin, gap and radius only from tokens; no new token; `globals.css` and `feed.module.css`
  untouched (source: WEBCHAT-10, WEB-9, `chat-css.test.ts`).
- No new dependency (source: AGENTS.md dependency rule).
- No change to `features/chat/api/`, `features/chat/index.ts`, existing `features/chat/lib/` files,
  `app/api/chat/route.ts`, `app/page.tsx` or the backend (source: web-chat invariants 3 and 4, intent Scope).
- Anything this feature animates is off under `prefers-reduced-motion: reduce` (source: intent AC6).
- The e2e tier stays offline with fake credentials (source: WEBCHAT-12).
- The Stop hook (eslint and tsc) and `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`,
  `npm run test:e2e` stay green (source: AGENTS.md § Validation).

## Proposed approach
Revisable by the executor if it records why.
- Decision: restyle the existing `<button>` at the phone breakpoint rather than render a second element —
  rationale: every consumer (selectors, `aria-*`, focus return) keeps working untouched; rejected: a separate
  phone-only tab element, which would duplicate the testid or force selector migration in three e2e files and
  split focus-return logic.
- Decision: the button holds both the existing visible text and an `aria-hidden` inline SVG icon; CSS shows the
  text on desktop and the icon on a phone. The accessible name stays on `aria-label` — rationale: no markup fork
  per width; rejected: changing the label text per width (screen readers would hear two names).
- Decision: phone tab geometry, suggested values: `position: fixed`, `right: 0`, 24 px wide, about 64 px tall,
  vertically placed in the lower third (for example `bottom` around 20 to 25 % of `100dvh` with a `vh` fallback,
  plus `env(safe-area-inset-bottom)`), background `var(--link)`, icon `var(--surface-card)`, left corners
  `var(--radius-md)` and right corners 0, `var(--shadow-hover)`. Focus ring drawn inside the box (negative
  `outline-offset`) so the right edge does not clip it — rationale: meets AC1 with tokens only; rejected: an
  invisible 44 px hit area, which would overlap 20 px of card content past the 24 px gutter.
- Decision: gesture rule as a small pure function (suggested `features/chat/lib/swipe.ts`, exporting the two
  threshold constants and a classifier from `(dx, dy)` to left, right or none) plus pointer handling in the
  component — rationale: the rule is unit-testable in isolation and tunable in one place; `lib/` is where pure
  helpers live (AGENTS.md); adding a file does not edit the stable shell. Rejected: putting the math inline in
  the component (harder to test at the boundaries).
- Decision: pointer handling with `onPointerDown`, `onPointerMove`/`onPointerUp`, and `onPointerCancel` (reset).
  Record the start point on down; classify on up. Do not call `preventDefault` on down, so a tap still produces a
  click. Rely on implicit pointer capture for touch (guard `setPointerCapture`, which jsdom lacks) — rationale:
  threshold-based, no follow-finger state; rejected: Touch Events only (no pen, more code) and a gesture library
  (new dependency).
- Decision: `touch-action: pan-y` on the tab and on the sheet's swipe surface — rationale: the browser keeps
  vertical panning (page scroll, conversation scroll) and hands horizontal moves to the pointer handlers instead
  of cancelling them; a horizontally scrollable `pre` is its own scroll container, so its own panning still works.
  Rejected: `touch-action: none` (would block page scroll from the tab, breaking AC4).
- Decision: suppress the trailing click with a short-lived "just swiped" ref that the toggle's `onClick` checks
  and clears — rationale: a swipe-open followed by a click would otherwise run `toggle()` and close the sheet.
  Rejected: `preventDefault` on `pointerdown` (also kills taps and focus).
- Decision: the close gesture sits on the dialog root (in `ChatPanel` via an optional handler prop, or on the
  widget wrapper filtered to targets inside the dialog). It ignores gestures whose target is inside the textarea
  or inside an element that scrolls horizontally (`scrollWidth > clientWidth` with `overflow-x` `auto` or
  `scroll`), and it calls the existing `close()` so focus returns to the tab. Rejected: a header-only zone as the
  default (it is open question Q3).
- Decision: read the phone query through `window.matchMedia('(max-width: 640px)')` at gesture time (not at render)
  — rationale: no hydration mismatch and no resize listener; rejected: a render-time media hook (server and client
  output would differ).
- Decision: no sheet animation (the sheet keeps mounting and unmounting), and if the tab gets a press feedback
  transition it is disabled inside a `prefers-reduced-motion: reduce` block next to the existing `.dot` one —
  rationale: an exit animation would need a delayed unmount and would fight the focus-return effect; intent Q4.
- Decision: one ADR candidate, **0056** (next free number per the repo-root index): "On phones the chat launcher
  is an edge tab with threshold touch/pen swipes; amends WEBCHAT-1's 44 px hit area at 640 px and narrower". The
  documenter writes it through `harny-adr`; the architect does not.

## Consumers and migration
- `features/chat/components/chat-widget.test.tsx`: existing tests use `fireEvent.click` on the launcher and keep
  passing without edits. New gesture tests are added in a new `describe` block that stubs `window.matchMedia`
  (jsdom has none) and restores it after each test.
- `e2e/chat.e2e.ts` (default desktop viewport, `getByTestId('chat-launcher')`, the 44 by 44 hit-area test at 1280
  by 800): no change expected.
- `e2e/layout.e2e.ts` (phone, `getByRole('button', { name: 'Open chat' }).click()`): no change expected; the tab
  is fully on screen, so Playwright's click lands on it. If Playwright reports the tab as outside the viewport, fix
  the CSS, not the test.
- `e2e/chat-rate-limit.e2e.ts` (default viewport, `getByTestId('chat-launcher')`): no change expected.
- `e2e/feed.e2e.ts` baseline: captures only the feed root at desktop width; no snapshot update allowed.
- `features/chat/components/chat-css.test.ts`: unchanged; it checks the new CSS.
- `features/chat/conventions.test.ts`: unchanged; a new `lib/` module must not import `api/` except with
  `import type` and must not be `"use client"` unless needed.
- Docs: `apps/web/AGENTS.md` components block (chat-widget line, and the new `lib/` module if added). The
  `web-chat` capability doc is updated by `harny-sync` at archive time, not by the executor.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Android gesture navigation or iOS Safari takes the swipe from the right edge (Back or Forward) | High on Android gesture nav | Med (the visitor leaves the page or nothing happens) | Tap always works (AC2); record a reservation; human real-device check (tasks O8); intent Q1 offers an inset as the alternative |
| A swipe opens the sheet and the trailing click closes it again | Med | High (the gesture looks broken) | Binding click-suppression rule; unit and e2e tests assert the dialog is still open after the full sequence |
| Swipe-right closes the sheet while the visitor selects text or scrolls a code block | Med | Med | Exclude textarea and horizontally scrollable targets; mouse never triggers; tests for both exclusions |
| CDP touch events in headless Chromium behave differently from a real phone (`touch-action`, implicit capture) | Med | Low (tests green but real behavior off) | e2e uses trusted CDP touch; the real-device human check covers the rest |
| Vertical-scroll e2e assertion is flaky (page too short or scroll settles late) | Med | Low | Use the populated stub at 375 by 667 (taller than the viewport); poll `scrollY`; also assert computed `touch-action` is `pan-y` |
| jsdom lacks `setPointerCapture` or `matchMedia` | High | Low | Guard the capture call; stub `matchMedia` in tests |
| The 24 px tab is below the 44 px rule in WEBCHAT-1 | Certain | Low (accepted by the human's decision) | Stated in intent Constraints, ADR 0056 candidate; Q2 |
| Tab overlaps a fixed or sticky feed element in the lower third | Low | Low | The feed has no fixed elements; e2e checks no horizontal overflow and the tab box |

## Validation
One row per AC. All commands run from `apps/web`. E2E rows share one new file, `e2e/chat-swipe.e2e.ts`, at a
375 by 667 viewport with `hasTouch: true`, and a small helper (suggested `e2e/touch.ts`) that sends
`Input.dispatchTouchEvent` `touchStart`, a few `touchMove` steps and `touchEnd` through
`page.context().newCDPSession(page)`.

| AC | Demonstrated by | Tests to write | Tier | Framework | Setup | Focused command | Broader command | Cwd |
|---|---|---|---|---|---|---|---|---|
| AC1 | Tab geometry, icon, no visible text, no overflow, focus ring inside the viewport | `chat-swipe.e2e.ts` "edge tab": launcher box flush right (`x + width` in `[374, 375]`), width in `[20, 24]`, height `>= 44`, `y >= 2/3 * 667`, `y + height <= 667`; `innerText` has no "Chat"; an `svg[aria-hidden="true"]` inside; `scrollWidth <= clientWidth`; after `focus()` the computed outline is drawn (outline-style not `none`) and the box is inside the viewport. `chat-css.test.ts` (existing) catches non-token values | e2e; unit (existing) | Playwright; vitest | `hasTouch: true`, phone viewport | `npx playwright test e2e/chat-swipe.e2e.ts -g "edge tab"` | `npm run test:e2e` | `apps/web` |
| AC2 | Tap and keyboard open; all closes return focus | `chat-swipe.e2e.ts` "tap and keyboard": `launcher.tap()` -> dialog visible, input focused, `aria-expanded="true"`, launcher hidden; focus launcher, `Enter` -> open; `Escape` -> closed, launcher focused; Close button -> launcher focused. Existing unit tests for click and focus return keep passing | e2e; unit (existing) | Playwright; vitest + Testing Library | as AC1 | `npx playwright test e2e/chat-swipe.e2e.ts -g "tap and keyboard"` | `npm run test:e2e`; `npm test` | `apps/web` |
| AC3 | Swipe left on the tab opens, and stays open after the trailing click | Unit: `features/chat/lib/swipe.test.ts` (if the module is added) `it.each` over the classifier: `(-60, 8)` left, `(-40, 20)` left (boundary), `(-39, 0)` none, `(-60, 31)` none (ratio), `(60, 0)` right. Widget: new `describe("phone gestures")` in `chat-widget.test.tsx` with `matchMedia` stubbed to match: `pointerDown`/`pointerMove`/`pointerUp` with `pointerType: "touch"` and `(-60, 8)` on the launcher, then `fireEvent.click` on it -> dialog present, `aria-expanded="true"`, input focused. E2E: CDP swipe `(-60, 8)` from the tab centre -> dialog visible and still visible after 300 ms | unit; e2e | vitest + Testing Library; Playwright | stub `window.matchMedia`; CDP session | `npx vitest run features/chat/lib/swipe.test.ts features/chat/components/chat-widget.test.tsx` and `npx playwright test e2e/chat-swipe.e2e.ts -g "swipe left"` | `npm test`; `npm run test:e2e` | `apps/web` |
| AC4 | Non-swipes do not open; page still scrolls; mouse never triggers | Widget unit: touch `(-20, 200)`, `(-30, 0)`, `(60, 0)`, and a down-move-`pointercancel` sequence -> no dialog; a mouse `pointerType` `(-60, 0)` sequence without a click -> no dialog. E2E: CDP vertical drag from the tab `(-20, -200)` (finger up, page scrolls down) -> no dialog and `window.scrollY` increases (polled); the tab's computed `touch-action` is `pan-y` | unit; e2e | vitest + Testing Library; Playwright | as AC3; populated stub page taller than 667 px | `npx vitest run features/chat/components/chat-widget.test.tsx -t "phone gestures"` and `npx playwright test e2e/chat-swipe.e2e.ts -g "does not open"` | `npm test`; `npm run test:e2e` | `apps/web` |
| AC5 | Swipe right closes, keeps the conversation, exclusions hold | Widget unit: open, touch `(80, 10)` on the dialog's message area -> no dialog, launcher focused; reopen -> earlier message present; touch `(80, 0)` starting on the textarea -> still open; touch `(-80, 0)` and `(10, 120)` -> still open. E2E: ask one stub question, CDP swipe `(80, 10)` on the message area -> dialog gone, launcher focused; reopen by tap -> answer still shown; ask `longurl please` (its stub code block overflows horizontally at 375 px, as `layout.e2e.ts` already asserts) and swipe `(80, 0)` starting inside `pre` -> still open; Close and Escape still close (covered by AC2 row) | unit; e2e | vitest + Testing Library; Playwright | as AC3; existing stub answers | `npx vitest run features/chat/components/chat-widget.test.tsx -t "phone gestures"` and `npx playwright test e2e/chat-swipe.e2e.ts -g "swipe right"` | `npm test`; `npm run test:e2e` | `apps/web` |
| AC6 | Reduced motion turns off this feature's motion; gestures still work | E2E with `page.emulateMedia({ reducedMotion: 'reduce' })`: launcher computed `transition-duration` is `0s` (every listed value) and `animation-name` `none`; after opening, the dialog's `animation-name` is `none` and `transition-duration` `0s`; CDP swipe left still opens | e2e | Playwright | as AC1 | `npx playwright test e2e/chat-swipe.e2e.ts -g "reduced motion"` | `npm run test:e2e` | `apps/web` |
| AC7 | Desktop unchanged | Existing `chat.e2e.ts` desktop tests (44 by 44 hit area, Close focuses launcher, size) pass unedited. New in `chat-swipe.e2e.ts` at 1280 by 800 with `hasTouch`: launcher shows "Chat" text and no visible icon, box at the bottom right and at least 44 by 44; CDP swipe `(-60, 0)` on the launcher -> no dialog; open by click, CDP swipe `(80, 0)` on the panel -> still open. Widget unit: `matchMedia` not matching, touch `(-60, 0)` on the launcher -> no dialog | e2e; unit | Playwright; vitest + Testing Library | desktop viewport in its own `describe` | `npx playwright test e2e/chat-swipe.e2e.ts -g "desktop"` and `npx playwright test e2e/chat.e2e.ts` | `npm run test:e2e`; `npm test` | `apps/web` |
| AC8 | Nothing else regressed | Existing suites unedited: `e2e/chat.e2e.ts`, `e2e/layout.e2e.ts`, `e2e/chat-rate-limit.e2e.ts`, `e2e/feed.e2e.ts` (17 baselines, no `--update-snapshots`), `chat-css.test.ts`, `conventions.test.ts`; `git diff --stat` shows no change under `features/chat/api/`, `features/chat/index.ts`, existing `features/chat/lib/*.ts`, `app/`, `package.json`, `package-lock.json`, `app/globals.css`, `features/feed/`; new e2e tests collect console output and expect it empty | unit; e2e; static | vitest; Playwright; git | none | `npx playwright test e2e/layout.e2e.ts e2e/chat.e2e.ts` | `npm run lint && npm run typecheck && npm test && npm run build && npm run test:e2e` | `apps/web` |
| AC9 | Offline coverage | The rows above run with no `.env.local` against `e2e/stub/feed-api-stub.mjs`; the new e2e file makes no request to a non-local host (assert every request URL starts with `http://127.0.0.1`) | e2e | Playwright | none | `npx playwright test e2e/chat-swipe.e2e.ts` | `npm run test:e2e` | `apps/web` |

## Revision log
- Revision 1 (2026-11-11): first plan.

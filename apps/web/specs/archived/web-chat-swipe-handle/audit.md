# Audit: Web Chat Swipe Handle

Round 1, 2026-11-11. Branch `feat/web-chat-swipe-handle`, base `846a1c1`, working tree uncommitted.
Reviewed: `features/chat/components/chat-widget.tsx`, `chat.module.css`, `chat-widget.test.tsx` (additions
only), new `features/chat/lib/swipe.ts`, `swipe.test.ts`, `e2e/chat-swipe.e2e.ts`, `e2e/touch.ts`, and the
`AGENTS.md` components lines. Every changed line was read; the only consumer of the changed component is
`features/chat/index.ts` (unchanged) and through it `app/page.tsx` (unchanged).

Commands rerun by the auditor from `apps/web` (Node v24.16.0):

| Command | Result | Label |
|---|---|---|
| `npm run lint` | exit 0; 0 errors, 1 warning: `features/feed/api/types.generated.ts 1:1 Unused eslint-disable directive` | rerun |
| `npm run typecheck` | exit 0 | rerun |
| `npm test` | 21 files, 433/433 passed | rerun |
| `npm run build` | exit 0, compiled successfully | rerun |
| `npm run test:e2e` | 61/61 passed, including all 7 tests in `e2e/chat-swipe.e2e.ts` | rerun |
| Red check: base-commit code (`git archive 846a1c1`, copied to the scratchpad) plus the new `swipe.test.ts` and `chat-widget.test.tsx` | `swipe.test.ts` fails to resolve `./swipe`; 4 positive gesture tests fail (swipe-left opens, pen opens, swipe-right on message area closes, swipe-right on dialog closes); guards pass, as expected for "does nothing" tests | rerun |
| Mutation checks on a scratch copy of the green widget | removing click suppression fails 1 test; removing the textarea/code-block exclusion fails 2; allowing mouse fails 2; dropping the phone query fails 2 (desktop gestures); not resetting on `pointercancel` fails 1 | rerun |

Lint and type-check were rerun at the caller's request, because the executor ran neither `harny-standards` nor
`harny-feedback` as steps and no hook evidence for this change survives (see F3). The lint warning is in a
generated file this change does not touch (`git status` shows nothing under `features/feed/`, and the eslint
config is unchanged), so it predates the change and is a note, not a finding.

Red tests not edited: the test files (`chat-swipe.e2e.ts`, `touch.ts`, `swipe.test.ts` at 21:14:34,
`chat-widget.test.tsx` at 21:14:44) were last modified before any implementation file (`swipe.ts` and
`chat-widget.tsx` at 21:19:04, `chat.module.css` at 21:20:31), and the `chat-widget.test.tsx` diff is purely
additive (existing tests unedited). No record of the red-phase content exists to diff against, so this rests on
modification times plus the red rerun above.

## AC results
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | e2e "edge tab" passed: box flush right, width in [20, 24] (CSS 24 px), height >= 44 (64 px), top >= 2/3 of 667 (`bottom: calc(15dvh + env(safe-area-inset-bottom))` puts the top near 503 px), no "chat" in `innerText`, `svg[aria-hidden]` visible, no horizontal overflow, outline drawn and inside the viewport (`outline-offset: -4px`). `chat-css.test.ts` token checker passed in `npm test` (rerun) |
| AC2 | PASS | e2e "tap and keyboard" passed: tap opens with input focused, `aria-expanded="true"`, tab hidden; Escape and Close return focus to the tab; Enter opens (rerun). Swipe-right focus return covered by the unit test (rerun) |
| AC3 | PASS | `classifySwipe` boundary table passed; unit "swipe left on the tab opens ... trailing click does not close it" passed and fails without the suppression ref (mutation M1); e2e trusted-CDP swipe `(-60, 8)` opens and stays open after 300 ms (rerun) |
| AC4 | PASS | unit: vertical, short, rightward, ratio-not-met, cancelled and mouse gestures do not open; mouse click still toggles (rerun). e2e: `touch-action: pan-y` on the tab, `(-30,0)` and `(60,0)` do not open, `(-20,-200)` scrolls the page (`scrollY > 0`) with no dialog (rerun) |
| AC5 | PASS | unit: swipe right on message area closes, focuses the tab, conversation kept; textarea and horizontally scrolling `pre` excluded; leftward, vertical, short and mouse gestures do not close (rerun). e2e: `longurl please` code block overflows, swipe in `pre` keeps the sheet open, swipe `(80,10)` on the message area closes and focuses the tab, reopen shows the answer (rerun) |
| AC6 | PASS | e2e "reduced motion" passed: tab and dialog `transition-duration` all `0s`, `animation-name` `none`, swipe left still opens (rerun). The feature adds no transition or animation (diff of `chat.module.css`), so nothing needs disabling |
| AC7 | PASS | e2e "desktop" passed: "Chat" text, icon hidden, bottom right, >= 44 by 44, touch swipes on launcher and panel do nothing; `chat.e2e.ts` passed unedited; unit "desktop gestures (AC7)" passed and fails without the phone query (mutation M4) (rerun) |
| AC8 | PASS | `layout.e2e.ts`, `chat.e2e.ts`, `chat-rate-limit.e2e.ts`, `feed.e2e.ts` (17 baselines, `e2e/__baseline__` unchanged) passed; `git status` shows no change under `features/chat/api/`, `features/chat/index.ts`, existing `features/chat/lib/*.ts`, `app/`, `features/feed/`, `package.json`, `package-lock.json`, configs; the new e2e monitor asserts empty console output (rerun) |
| AC9 | PASS | `chat-swipe.e2e.ts` monitor asserts every request is `http://127.0.0.1` (or `data:`); `launch-apps.mjs` overrides `.env.local` with stub URLs and fake keys (rerun) |

## Binding-constraint compliance
| Constraint | Status | Evidence |
|---|---|---|
| One launcher element; testid, `aria-expanded`, `aria-controls`, names, focus return kept | PASS | Same `<button>`; text moved into a `span.toggleText`, accessible name still on `aria-label`; all four consumer suites pass unedited |
| Phone breakpoint is `(max-width: 640px)` in CSS and JS | PASS | `PHONE_QUERY = '(max-width: 640px)'`; CSS rules sit in the existing `@media (max-width: 640px)` block |
| Gestures only for touch or pen and only while the phone query matches | PASS | `onPointerDown` returns on `mouse` or `!isPhone()`; pointer type must match on up; mutations M3 and M4 |
| A recognized swipe is not followed by a toggle from the trailing click | PASS | `suppressClickUntil` (500 ms) checked in `onToggleClick`; mutation M1 |
| Tokens only; no new token; `globals.css`, `feed.module.css` untouched | PASS | Colours and radius from tokens; px values are layout sizes; `chat-css.test.ts` passed; neither protected file changed |
| No new dependency | PASS | `package.json` and `package-lock.json` unchanged |
| No change to `api/`, `index.ts`, existing `lib/` files, route, `app/page.tsx`, backend | PASS | Only new `lib/swipe.ts` added (allowed by intent Constraints) |
| Motion off under reduced motion | PASS | No motion added; e2e asserts `0s` / `none` |
| e2e offline, fake credentials | PASS | See AC9 |
| Stop hook and the five commands stay green | PASS | All five rerun green (table above); hook firing itself is unverified (F3) |

Plan deviations assessed:
- **`touch-action: pan-y` on `.scroll` as well as `.panel` and the tab.** The plan names "the tab and the sheet's
  swipe surface"; `.scroll` is part of that surface. Effective `touch-action` is intersected only up to the
  nearest scroll container, so `.scroll` (the conversation's own scroll container) needs the value itself for
  horizontal moves on the message area to reach the pointer handlers instead of being cancelled. The rule lives
  only in the phone block, so desktop is unaffected, and the horizontally scrolling `pre` remains its own scroll
  container, so code still pans (e2e confirms). Compliant alternative, not a defect.
- **Handlers on the widget wrapper**, filtered by "not on the tab" rather than "inside the dialog": on a phone with
  the sheet open the wrapper holds only the dialog and the hidden tab, so the two are equivalent. The plan allows
  the wrapper option.
- **`HTMLInputElement` added to the excluded targets** beside the textarea: stricter than required, harmless.

## Test coverage
| AC | Test | Status |
|---|---|---|
| AC1 | `e2e/chat-swipe.e2e.ts` "edge tab"; `features/chat/components/chat-css.test.ts` (existing) | PASS |
| AC2 | `e2e/chat-swipe.e2e.ts` "tap and keyboard"; existing click/focus tests in `chat-widget.test.tsx` | PASS |
| AC3 | `features/chat/lib/swipe.test.ts`; `chat-widget.test.tsx` "phone gestures" (swipe left, pen); `e2e/chat-swipe.e2e.ts` "swipe left" | PASS (red shown at base, rerun) |
| AC4 | `chat-widget.test.tsx` "phone gestures" (it.each non-swipes, cancelled, mouse); `e2e/chat-swipe.e2e.ts` "does not open" | PASS (guards; removal shown red by mutations M3, M5) |
| AC5 | `chat-widget.test.tsx` "with the sheet open"; `e2e/chat-swipe.e2e.ts` "swipe right" | PASS (red shown at base and by mutation M2, rerun) |
| AC6 | `e2e/chat-swipe.e2e.ts` "reduced motion" | PASS |
| AC7 | `e2e/chat-swipe.e2e.ts` "desktop"; `e2e/chat.e2e.ts` (unedited); `chat-widget.test.tsx` "desktop gestures (AC7)" | PASS (mutation M4) |
| AC8 | existing suites unedited; e2e console monitor; auditor `git status` | PASS |
| AC9 | `e2e/chat-swipe.e2e.ts` request monitor | PASS |

E2E red evidence is `unavailable`: the auditor did not rebuild the base app against the new e2e file; the unit
red rerun and the mutation checks cover the same behaviors.

### Tier Results
| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit (vitest + Testing Library) | `swipe.test.ts` (12 cases), `chat-widget.test.tsx` "phone gestures" and "desktop gestures (AC7)", existing `chat-css.test.ts`, `conventions.test.ts` | AC1 (tokens), AC2 (existing), AC3, AC4, AC5, AC7, AC8 | Yes: `matchMedia` stubbed with `vi.stubGlobal`; no new config or dependency | rerun, 433/433 | PASS | none |
| e2e (Playwright, Chromium) | `e2e/chat-swipe.e2e.ts` (7 tests) with helper `e2e/touch.ts` (CDP `Input.dispatchTouchEvent`); existing suites | AC1 to AC9 | Yes: 375 by 667 and 1280 by 800 with `hasTouch`, CDP session, populated stub; `playwright.config.ts` unchanged | rerun, 61/61 | PASS | none |
| static (git) | auditor `git status` / `git diff` over the protected paths | AC8 | Yes | rerun | PASS | none |
| real device (human, O8) | none (not an executor tier) | intent Q1 | n/a | not run: human step on Android gesture navigation and iOS Safari | N/A | R1 |

## Findings
| Id | Severity | Cites | Finding | Closure condition | Status |
|---|---|---|---|---|---|
| F1 | MEDIUM | tasks Baseline; binding constraint "five commands stay green" | No baseline was recorded before the first edit; tasks.md § Baseline still says "not yet recorded". The auditor showed the one lint warning predates the change (untouched generated file), so no regression is hidden, but the record is missing | tasks.md § Baseline records the pre-change state (for example the green `harny feedback (apps/web)` run on `846a1c1`, 2026-11-11, plus the pre-existing lint warning) | Open |
| F2 | MEDIUM | tasks O1 to O5 | The checked outcomes O1 to O5 have empty `Red:` and `Green:` lines; the only evidence is one aggregate note. The auditor's red rerun and mutations supply unit evidence, but the outcome record does not carry it | Each of O1 to O5 records its red evidence (failing test and reason) and green command and result | Open |
| F3 | MEDIUM | binding constraint "Stop hook ... stay green"; harny-feedback | `harny-standards` and `harny-feedback` were not run as steps. No hook-firing evidence for this change survives (`.sdd/feedback/.turns/` holds only older turns), and `harny-feedback-apps-web.yml` has no run on this change (uncommitted; latest run is on `846a1c1`, green). The auditor's lint and typecheck rerun is green, so no defect is known | `harny-feedback-apps-web.yml` runs green on this branch's PR and its log shows `N of M command(s) ran` with N > 0 | Open |
| F4 | MEDIUM | intent Constraints (WEBCHAT-1 amendment); plan ADR 0056 | `specs/current/web-chat.md` WEBCHAT-1 still says the launcher has a 44 px hit area and is "a floating chat button"; the phone tab is 24 by 64 (meets WCAG 2.2 AA 24 px, not 44 by 44). The amendment is approved in the intent but not yet recorded. 0056 is confirmed free (repo-root `specs/current/_index.md` names it next unclaimed; no ADR file uses it) | Documenter writes ADR 0056 via `harny-adr`, and `harny-sync` amends WEBCHAT-1 (phones: edge tab, 24 px wide, at least 44 px tall; desktop unchanged) and widens WEBCHAT-12 at archive | Open (owner: documenter, not the executor) |
| F5 | LOW | AC5 | `ownsHorizontalGesture` reads `(el as HTMLElement).style?.overflowX` before `getComputedStyle(el).overflowX`. The inline branch is redundant: the unit suite passes with it removed (mutation M6), and computed style already reflects inline style | Drop the inline-style branch, or keep it and record why | Open |
| F6 | LOW | tasks.md | tasks.md § Working state ("Outcome: none started", "Phase: spec drafted") and § Checkpoint ("no code has been changed") are stale | Working state and Checkpoint reflect the implemented state | Open |

Reservations (accepted, not defects):
- **R1 (O8, intent Q1).** Android gesture navigation and iOS Safari may take a swipe that starts on a tab flush with
  the right edge (Back or Forward). Chromium CDP touch cannot show this. Tap remains the guaranteed path (AC2,
  verified). O8 stays open and is recorded as unavailable, not a pass, until the human checks a real Android phone
  with gesture navigation and an iPhone in Safari.
- **R2 (WEBCHAT-1 on phones).** The tab is below the 44 by 44 target that WEBCHAT-1 sets, by the human's decision
  (intent Constraints, Q2 default 24 px). It meets WCAG 2.2 AA 2.5.8 (24 by 24). Tracked in F4 until ADR 0056 lands.

Notes (not findings): the lint warning in `features/feed/api/types.generated.ts` predates the change. If no
trailing click arrives after a swipe-open, a tap on the tab within 500 ms of a swipe-close is swallowed once;
negligible. `touch-action: pan-y` on the tab and sheet also disables pinch-zoom when a gesture starts there
(page zoom elsewhere and browser zoom still work); `pan-y pinch-zoom` would keep it, worth considering.

## Audit log
| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-11-11 | APPROVED WITH RESERVATIONS | All ACs and binding constraints pass on rerun (lint, typecheck, 433 unit, build, 61 e2e). Process findings F1 to F3 and F6 on tasks.md and feedback evidence; F4 is the documenter's ADR 0056 and WEBCHAT-1 amendment; F5 is redundant code. R1 (O8 real device) open for the human |

## Final verdict

APPROVED WITH RESERVATIONS

**Summary**: The edge tab and threshold swipes meet AC1 to AC9 with tests that fail when the behavior is removed,
and every validation command is green on rerun with no regression. The open items are record-keeping (baseline,
red/green evidence, feedback evidence), the pending ADR 0056 / WEBCHAT-1 amendment, and the human real-device check
(O8).

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- F1: record the pre-change baseline in tasks.md.
- F2: fill the Red and Green lines for O1 to O5.
- F3: get a green `harny-feedback-apps-web.yml` run on the PR with N > 0 commands ran.
- F4: documenter writes ADR 0056 and the WEBCHAT-1 amendment is synced at archive.
- R1: human completes O8 on Android (gesture navigation) and iPhone Safari.

**Recommendations** (nice to have):
- F5: drop the redundant inline-style read in `ownsHorizontalGesture`.
- F6: refresh tasks.md Working state and Checkpoint.
- Consider `touch-action: pan-y pinch-zoom` on the tab and sheet to keep pinch-zoom.

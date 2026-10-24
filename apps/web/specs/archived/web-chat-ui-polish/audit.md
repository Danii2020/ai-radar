# Audit: Web Chat UI Polish

Round 1, 2026-10-24. Auditor: `sdd-auditor` (harny-audit). Branch `feat/web-chat-ui`, base `48334d8`
plus the uncommitted `web-chat-ui` work; this feature is uncommitted too. Cwd `apps/web`. Node v24.16.0.
Spec state audited: `intent.md` revision 2 (`Approval: Approved`), `execution-plan.md` revision 1,
`tasks.md` O0 to O12 `[x]`.

Evidence labels: `rerun` (the auditor ran it this round), `reused` (the executor's record, still
current), `unavailable` (could not be checked).

## Gate results (rerun, 2026-10-24)
| Command | Result | Executor's record (O12) |
|---|---|---|
| `npm run lint` | exit 0; 0 errors, 1 warning (unused eslint-disable in `features/feed/api/types.generated.ts`, pre-existing since O0) | same |
| `npm run typecheck` | exit 0, clean | same |
| `npm test` | 19 files, 265 passed | 19 files, 265 passed |
| `npm run build` | exit 0 (routes `/`, `/_not-found`, `/api/chat`) | ok |
| `npm run test:e2e` | **48 passed, 1 failed**: `e2e/layout.e2e.ts:102` "latest: three tall turns..." (`TypeError: Cannot read properties of null (reading 'y')` at `e2e/chat-scroll.ts:11`) | 49 passed |
| `npx playwright test e2e/chat.e2e.ts e2e/layout.e2e.ts -g latest --repeat-each=8` | 29 passed, **3 failed**, all the same phone test (3 of 8 repeats) | 4 passed, 3 runs in a row |

By file in the full run: `feed.e2e.ts` 23 passed (all 17 `pre-refactor baseline` scenarios), `chat.e2e.ts`
21 passed, `layout.e2e.ts` 4 passed and 1 failed. The total of 49 matches the record. The failure is
intermittent, so the executor's "3 runs in a row" check was not enough to show it (see F1).

Root cause of the flake (rerun, a scratch Playwright check outside the repo): while a turn is pending,
`chat-panel.tsx:74-83` renders the question as a separate `<Message>` after `messages.map`. When the
answer arrives, the question is re-rendered inside `messages.map` (`chat-panel.tsx:62-73`, keyed by
index), so React replaces the DOM node. A handle taken on the pending node reports
`isConnected === false` after the answer. `expectInView` (`e2e/chat-scroll.ts:9-11`) reads
`boundingBox()` inside `expect.poll` and dereferences it with `!`. A detached node gives `null`, the
callback throws, and the poll fails at once instead of retrying. The page snapshot of every failure
shows the correct end state: all three turns present, at the bottom, no "Jump to latest". The product
behavior holds and the test is racy.

## AC results
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `chat-panel.tsx:65-68`: user text goes into a plain `<p className={styles.text}>` (`pre-wrap`, `chat.module.css:168-172`), and the assistant's into `MessageResponse`. `message-response.tsx:7-26,51-56`: the allow-list keeps `strong/ol/ul/li/code/pre`. Tests: `message-response.test.tsx:15-30` (strong, `ol>li` x2 ending `[1]`/`[2]`, `ul>li`, `p code`, `pre>code`, no `**`); `chat-widget.test.tsx:356-368` (a user `**hi**` stays literal, the assistant's renders as strong); e2e `chat.e2e.ts:257-266` (rerun, all pass). Code blocks scroll sideways: `chat.module.css:241-255`, and at 375 px the `pre` has scrollWidth 2372 against clientWidth 315 inside the sheet (rerun, scratch check). |
| AC2 | PASS | No `rehype-raw`, `remark-gfm` or `dangerouslySetInnerHTML` under `features/` or `app/` (rerun grep). `message-response.tsx:28-35`: the `urlTransform` returns the URL only when `new URL(url).protocol` is `http:`/`https:`, and `''` otherwise. `:38-45`: an empty href renders a `<span>`, and a real one gets `target="_blank" rel="noopener noreferrer"`. `img` is not in the allow-list. Repo tests: `message-response.test.tsx:39-77`, plus e2e `chat.e2e.ts:268-282` with a `page.on('dialog')` tripwire (rerun, pass). **Adversarial rerun** (25 cases, scratch Vitest against the real component, 25/25 safe): `JaVaScRiPt:`, `java\tscript:`, `&#106;avascript:`, `javascript&#58;`, `&#x6A;avascript:`, `< javascript:...>`, `java%0ascript:`, `%6Aavascript:`, `data:`/`DATA:`, `vbscript:`, `file:`, the autolinks `<javascript:...>` and `<data:...>`, reference-style `javascript:`/`data:` definitions, raw `<a href=javascript:>`, `<img onerror>`, nested `<div><svg onload><a>`, HTML inside list items, `<p style=url(javascript:)>`, an image reference, and an image inside a link. Every case gave no `script/img/iframe/svg/style`, no `on*`, `style` or `src` attribute, every `href` matched `^https?://`, and every link had the right target and rel. Raw HTML renders as escaped text. |
| AC3 | PASS (test flaky, F1) | `conversation.tsx:20-28` (`StickToBottom`, `initial="instant"`, `resize` smooth or instant under reduced motion), `:39-45` (re-locks when a turn is pending), `:47-55` (Jump to latest only when `!isAtBottom`). e2e desktop `chat.e2e.ts:198-229` and phone `layout.e2e.ts:99-127`. The scrolled-up and Jump tests pass at both viewports (rerun, 8 of 8 each). The phone three-turn test fails intermittently on a test-side race (F1). Its failure snapshots show the correct end state. Component test: no Jump button when the conversation is empty (`chat-widget.test.tsx:424-431`). The coverage gaps are in F3. |
| AC4 | PASS | `chat.module.css:6-9` (border-box under `.widget`), `:481-497` (sheet `inset: auto 0 0 0`, `100vh` then `100dvh`, top corners only). `layout.e2e.ts:47-73` (rerun, pass): box within 0..375 and 0..667, header and textbox visible, no horizontal overflow with the `longurl` answer and Sources expanded. Scratch rerun: the dialog box is [0,375]x[24,667] and `scrollWidth 375 <= clientWidth 375`. A routed answer whose long URL is the *visible* text of a markdown link, an autolink and a source title wraps at 171 px and 368 px tall, inside 30..345 px. The executor's red measurement (x=-18, width 377) matches plan Decision 6 (reused). |
| AC5 | PASS (manual part pending H1) | `chat.module.css:67-69`: `min(30rem, ...)` by `min(40rem, 100dvh - 6rem)`. Header: `chat-panel.tsx:46-57` (wordmark "AI RADAR" and an icon Close button named "Close chat"). The Close, Send and launcher buttons are 44 px (`chat.module.css:24-37,104-117,442-455`). Send is `var(--link)` with a `var(--surface-card)` icon. e2e `chat.e2e.ts:148-196` (rerun, pass): width 448..480, height <= 640, Close focuses the launcher, the three hit areas are >= 44, Send matches the `--link` probe in light and dark. Component test `chat-widget.test.tsx:462-469`. Scratch rerun at the phone size: Send and Close are 44x44. "Distinct from a feed card" is a human check (H1), still open. |
| AC6 | PASS | `sources.tsx:5-29`: a button "Sources (n)" with `aria-expanded`/`aria-controls`, collapsed by default, the list rendered only while expanded, and `null` for an empty list. `:31-38` gives `[n]`, title, source, target and rel. Tests: `chat-widget.test.tsx:121-149,336-353`, e2e `chat.e2e.ts:65-74` (rerun, pass). Long titles and URLs wrap (scratch rerun, AC4 row). |
| AC7 | PASS | `loader.tsx:3-13` (`role="status"`, dots `aria-hidden`, visually hidden "Thinking"), `chat.module.css:301-334` (keyframes, and `animation: none` under reduced motion). Component `chat-widget.test.tsx:371-392`, e2e `chat.e2e.ts:232-254` (animated names not `none`; reduced motion gives `['none','none','none']`) (rerun, pass). |
| AC8 | PASS | `prompt-input.tsx:15-33` (`aria-label="Your question"`, `rows={2}`, Enter without Shift sends and prevents the default), `:35-44` (Send disabled while pending). Tests `chat-widget.test.tsx:395-420` and the unchanged limit tests `:206-231` (rerun, pass). The example's literal `"a\nb"` is not asserted (jsdom does not insert the newline), see F5. |
| AC9 | PASS | `conversation-empty-state.tsx:3-23` (copy exactly as in plan Decision 12), shown only when there are no messages and nothing is pending (`chat-panel.tsx:61`). `chat-widget.tsx:71-84,106`: a suggestion goes through `submit(text)`, the same validation and `send` path. Tests `chat-widget.test.tsx:423-459` (one request, `history: []`, empty state gone while pending), e2e `chat.e2e.ts:285-291` (rerun, pass). |
| AC10 | PASS | `cmp specs/web-chat-ui-polish/design/feed.module.css features/feed/components/feed.module.css` exits 0. `diff` against `specs/archived/web-feed-ui/claude-design-outputs/feed.module.css` shows only line 103 (`.urlLine` gains `overflow-wrap: anywhere;`). `git status --short -- specs/archived` is empty for `apps/web` (rerun). `layout.e2e.ts:79-96` (rerun, pass). The 17 baselines pass. |
| AC11 | PASS (mtime evidence) | The barrel, `lib/`, `api/` and route are untracked (from `web-chat-ui`), so `git diff` cannot show they are unchanged. Their mtimes are all 2026-10-22 21:57 to 22:06, before the `web-chat-ui` audit (22:14) and before this spec (2026-10-24 16:55). Every file this feature changed is dated 2026-10-24 17:02 to 17:12 (rerun `stat`). The executor's sha1 snapshot shows 0 mismatches (reused). `lib/*.test.ts`, `api/*.test.ts` and `conventions.test.ts` pass (rerun). Dialog, launcher `aria-expanded` and name, focus to the input, Escape, and focus return: `chat-widget.tsx:22-53,111-122`, tests `chat-widget.test.tsx:49-103`. One same-origin POST and a clean console: `chat.e2e.ts:51-78` (rerun). On a phone the launcher is hidden while open, and Escape or Close returns focus to it once it is visible again (scratch Playwright rerun, pass). No `process.env`/`CHAT_API` in `components/` or `lib/`. The client chunks in `.next/static/chunks` contain no `CHAT_API`, `execute-api`, `aws4fetch`, fake key or stub port (rerun grep). |
| AC12 | PASS | All 17 baseline scenarios pass without `--update-snapshots` (rerun). `git status`/`git diff --stat` for `e2e/__baseline__`, `e2e/fixtures`, `e2e/feed.e2e.ts` and `app/globals.css` are empty, and those files are dated 2026-10-05. `npx vitest run features/feed` passes inside `npm test` (rerun). |
| AC13 | PASS | `chat-css.test.ts` passes (rerun). Every `var(--*)` in `chat.module.css` exists in `app/globals.css`, so no new token (rerun loop). There is no `data-theme`. The theme e2e test passes in light and dark (rerun). `globals.css` is unchanged. The WEB-9 copy is verified in the AC10 row. |

## Binding-constraint compliance
| Constraint | Status | Evidence |
|---|---|---|
| Shell behavior frozen (`lib/**`, `api/**`, route, barrel) | PASS (mtime + sha evidence) | AC11 row. The proof is indirect because these files are untracked, see F6. |
| Chat guards (import type only, no `NEXT_PUBLIC_`, no `CHAT_API_*` outside `api/`, no `.sort(`/`.reverse(`) | PASS | Rerun greps found none. `sources.tsx:2` and `chat-panel.tsx:2` use `import type` from `api/`. Only `chat-widget.tsx` is `"use client"` and it imports no `api/` module. Both conventions tests pass. |
| Exactly two new exact-pin runtime deps, at least two weeks old, no `remark-gfm`/`rehype-raw`/UI library | PASS | `git diff package.json`: `+react-markdown 10.1.0`, `+use-stick-to-bottom 1.1.6` (plus `aws4fetch 1.0.20`, which `web-chat-ui` added). Publish dates: 2025-03-07 and 2026-06-04 (rerun `npm view`). `npm ls` resolves. The new lockfile entries are all in the `react-markdown` (unified/micromark/mdast/hast) closure, plus `aws4fetch` and `use-stick-to-bottom`. devDependencies are unchanged. `AGENTS.md` names both packages and says "A further dependency needs its own ADR". |
| Markdown safety (ADR 0038) | PASS | AC2 row, including the 25 adversarial inputs. |
| Styling tokens only; `--radius-md` panel, `--radius-full` launcher/Send/composer; Send `--link`/`--surface-card`; icons inline SVG `currentColor` `aria-hidden` | PASS | `chat.module.css:29,72,113,433,451-453`; `chat-panel.tsx:52`, `prompt-input.tsx:38`. |
| WEB-9 feed revision (ADR 0039) | PASS | AC10 row. |
| Baselines unchanged, no feed class or fixture change | PASS | AC12 row. The stub's `long-url` branch (`feed-api-stub.mjs`) is used by no baseline. |
| e2e offline, fake credentials | PASS | `launch-apps.mjs` sets `CHAT_API_*` to obvious fakes pointed at the stub (a `web-chat-ui` change, file dated 2026-10-22). The stub rejects unsigned calls. |
| No `vercel`/`cdk`/`aws` | PASS | Nothing deployed. The executor's record shows no such command (reused). |

## Test coverage
| AC | Test | Status |
|---|---|---|
| AC1 | `message-response.test.tsx:14-37`; `chat-widget.test.tsx:356-368`; `e2e/chat.e2e.ts:257-266` | PASS |
| AC2 | `message-response.test.tsx:39-77`; `e2e/chat.e2e.ts:268-282` | PASS |
| AC3 | `e2e/chat.e2e.ts:198-229`; `e2e/layout.e2e.ts:102-127`; `chat-widget.test.tsx:424-431` | PASS, but `layout.e2e.ts:102` is flaky (F1). Gaps in F3. |
| AC4 | `e2e/layout.e2e.ts:47-73` | PASS |
| AC5 | `e2e/chat.e2e.ts:148-196`; `chat-widget.test.tsx:462-469`; manual H1 | PASS (manual open) |
| AC6 | `chat-widget.test.tsx:121-149,336-353`; `e2e/chat.e2e.ts:65-74` | PASS |
| AC7 | `chat-widget.test.tsx:371-392`; `e2e/chat.e2e.ts:232-254` | PASS |
| AC8 | `chat-widget.test.tsx:206-231,395-420` | PASS (F5) |
| AC9 | `chat-widget.test.tsx:423-459`; `e2e/chat.e2e.ts:285-291` | PASS |
| AC10 | `e2e/layout.e2e.ts:79-96`; `cmp`/`diff` commands | PASS |
| AC11 | `chat-widget.test.tsx:49-334`; `features/chat/lib/*.test.ts`, `api/*.test.ts`, `conventions.test.ts`; `e2e/chat.e2e.ts:27-127` | PASS |
| AC12 | `e2e/feed.e2e.ts` (17 baselines); `features/feed/**/*.test.ts` | PASS |
| AC13 | `chat-css.test.ts`; `e2e/chat.e2e.ts:129-146`; commands | PASS |

Red evidence: recorded only for O3 (layout, with measured values) and O4 (`message-response` module
missing). The executor states that the O5 to O8 cases were written after the code (F4). For each
uncovered AC a plausible red reason exists, because the behavior did not exist before this feature:
there was no Sources toggle, no empty state, no Close button, a 24rem panel, "Thinking..." text and no
Jump button. Test quality (`high-value-tests`): there are no tautologies, and the tests assert user-visible
behavior through roles and computed layout. `chat-css.test.ts` reads the CSS from disk. It is the
pre-existing WEB-9 checker from `web-chat-ui`, here widened per plan Decision 9, with a new
fires-on-violation case (`chat-css.test.ts:76-81`). It strips `min(` as well as the planned
`max(`/`calc(`. A literal next to a token is still flagged (`calc(var(--x) + 3px)` leaves `+ 3px`).
That is acceptable.

### Tier Results
| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit (component), Vitest + Testing Library | `message-response.test.tsx`, `chat-widget.test.tsx`, `chat-css.test.ts`, plus the unchanged lib/api/conventions tests | AC1, AC2, AC3 (no-Jump case), AC5, AC6, AC7, AC8, AC9, AC11, AC12, AC13 | Yes: the `ResizeObserver` stub in `vitest.setup.ts` (Decision 16). No new dev dependency or config. | rerun: 265 passed | PASS | none |
| e2e, Playwright (Chromium, offline stub) | `chat.e2e.ts` (21), `layout.e2e.ts` (5), `feed.e2e.ts` (23) | AC1 to AC7, AC9 to AC13 | Yes: the stub keywords `markdown/longurl/unsafe/tall/slow` and the `long-url` tag (Decision 14). The helper `e2e/chat-scroll.ts` is not collected (not `*.e2e.ts`). | rerun: 48/49 in the full run; the `-g latest` repeat gave 29/32 | PARTIAL | F1 (flaky AC3 phone test), F3 |
| command (shell) | `cmp`, `diff`, `git diff --stat`/`git status`, `npm ls` | AC10, AC11, AC12, AC13 | Yes | rerun | PASS | F6 (untracked files only allow mtime/sha proof) |
| manual (human) | H1: "distinct from a feed card" | AC5 (look) | n/a | not run: human-only step | N/A | none (H1 is open in `tasks.md`) |

No test sits at a tier that § Validation does not name.

## Conventions check (`harny-standards`, `apps/web/AGENTS.md` § Coding standards)
- WEB-1 (server-side fetching only): PASS. The browser calls only same-origin `/api/chat`. No `NEXT_PUBLIC_` and no host literal.
- WEB-2 (generated types): not touched.
- WEB-3 (no `.sort(`/`.reverse(` under `features/`): PASS.
- WEB-4 and WEB-5: feed unchanged, baselines pass.
- Barrel-only imports: PASS. The barrel is unchanged, and the chat does not import `features/feed` (`chat-panel.tsx:13-14`).
- WEB-9: PASS, through the revised deliverable (AC10).
- Style: TypeScript strict and CSS Modules, PASS. The new component files use double quotes and semicolons, while `chat-widget.tsx`, `chat-panel.tsx`, `lib/` and `features/feed/` use single quotes and no semicolons (F7).
- Errors never reach the browser: the error copy is unchanged (`chat-panel.tsx:16-23`).
- Tests follow `high-value-tests`: PASS (see Test coverage).
- Dependency rule: amended in `AGENTS.md`, PASS.

## Feedback verification (`harny-feedback`)
- The hook is configured: `.claude/settings.json` has PostToolUse `accumulate`, Stop and SubagentStop entries that run `.sdd/feedback/run-feedback.mjs` with eslint and tsc.
- There is no evidence it fired during this feature. `apps/web/.sdd/feedback/.turns/` holds only `.gitignore`, and its directory mtime is 2026-10-22 22:15. The repo root's is 2026-10-21. No runner log with the `N of M command(s) ran` line exists to read (unavailable).
- CI: `harny-feedback-apps-web.yml` is present. Its latest runs are green, but they ran on `main`/`feat/chat-api-auth` (2026-10-21), not on this change, which is uncommitted and has no run (unavailable).
- Mitigation: lint and typecheck are clean in this round's rerun, which the caller asked for. See F2.

## Deviations reported by the executor
| Deviation | Decision |
|---|---|
| Red-first only for O3 and O4 | Not acceptable as a process record, but the red reasons are plausible by construction (see Test coverage). MEDIUM F4. |
| Bundle metric: the sum of `.next/static/chunks/*.js` instead of first-load JS (Next 16.3.5 prints no table) | Acceptable. Rerun: 9 files, 708,892 B raw (matches), 213,132 B gzip when concatenated (the executor's per-file sum is 217,350 B). Neither the intent nor the plan sets a budget (Decision 15 only records the figure). The +128 KB raw / about +39 KB gzip (+22 %) growth is recorded and lazy loading is a stated follow-up. Note only. |
| Safe-area widening of `chat-css.test.ts` (also strips `min(`) | Acceptable. Decision 9 is followed, the fires-on-violation case is present and a literal is still flagged. The pre-widening file is untracked, so the exact before-diff cannot be shown (F6). |
| 16 px composer font | Acceptable. A font size is a layout literal (plan, styling constraint), and 16 px avoids the iOS focus zoom. |
| Accent launcher and accent header (`var(--link)`) | Acceptable. Tokens only, contrast as the intent states. Human H1 confirms the look. |
| Focus-test assertions now `waitFor` (focus returns in an effect, Decision 7) | Acceptable. The assertion target is unchanged, and focus return is verified for real at the phone size (scratch rerun). |
| `e2e/chat-scroll.ts` helper not in Ownership | Acceptable. It is a test helper and is recorded in O8. |
| The test duplicates `LONG_URL` instead of importing it | Acceptable. The reason (ESM `import.meta` in the stub) is recorded in O3. |

## Findings
| Id | Severity | Cites | Finding | Closure condition | Status |
|---|---|---|---|---|---|
| F1 | HIGH | AC3; intent Constraints (`npm run test:e2e` is a gate) | `e2e/layout.e2e.ts:102` ("latest: three tall turns...") is flaky. It failed once in the full rerun and in 3 of 8 `--repeat-each` runs. Cause: `expectInView` (`e2e/chat-scroll.ts:9-11`) dereferences a `null` `boundingBox()` inside `expect.poll`, and the pending question's DOM node is replaced when the answer lands (`chat-panel.tsx:74-83` against `:62-73`). So `test:e2e` is not reliably green. The product behavior holds. | `expectInView` tolerates a detached or `null` box (return `false` so the poll retries), or the test waits for the answer before measuring the question. Optionally, render the pending question so it keeps its node. Then `npx playwright test e2e/layout.e2e.ts e2e/chat.e2e.ts -g latest --repeat-each=10` passes 20/20 and the full `npm run test:e2e` passes. | Open |
| F2 | MEDIUM | `harny-feedback` (per-turn hook, CI) | There is no evidence the per-turn eslint/tsc hook fired in this root during the feature (`.turns` untouched since 2026-10-22). No CI run exists for the change. | The CI workflow `harny-feedback-apps-web.yml` runs green on the PR that carries this change, with a non-zero `N of M command(s) ran` line. | Open |
| F3 | MEDIUM | AC3; plan § Validation row AC3 | The desktop three-turn test (`chat.e2e.ts:216-229`) checks only that the answer is in view, not the question as the row requires. No test at either viewport checks that the loading indicator comes into view, which AC3 names ("the question, then the loading indicator, then the answer"). | The desktop test also asserts the newest question is in view, and one test (phone or desktop, `slow` keyword) asserts the `role="status"` loader is inside the scroll box while pending. | Open |
| F4 | MEDIUM | `harny-audit` step 5 (red evidence); `tasks.md` O5 to O8 Red lines | Red was not captured for the O5 to O8 cases (AC3, AC5, AC6, AC7, AC8, AC9). The executor states this openly. Plausible red reasons exist because the behaviors were absent before. | Accept as recorded at human sign-off, or show red for a representative case per AC (for example by running the new cases against the `web-chat-ui` components) and record it in `tasks.md`. | Open |
| F5 | LOW | AC8 example | No test proves Shift+Enter inserts a newline (`"a\nb"`). The component test only shows nothing is sent and the value stays `"a"`, and jsdom does not insert text on keydown. The code is correct (`prompt-input.tsx:17` prevents the default only without Shift). | An e2e check: type `a`, press Shift+Enter, type `b`, expect the value `"a\nb"` and no `/api/chat` request. | Open |
| F6 | LOW | Plan binding "shell frozen"; Decision 9 | The frozen `features/chat/lib`, `api`, `index.ts`, `app/api/chat` and the pre-widening `chat-css.test.ts` are untracked, so "unchanged" rests on mtimes (rerun) and the executor's sha1 snapshot (reused), not on `git diff`. Nothing contradicts it. | Commit `web-chat-ui` and this feature as separate commits (or record `web-chat-ui`'s tree hash) so the freeze is provable by diff. | Open |
| F7 | LOW | AGENTS.md style ("match surrounding code") | The new component files (`conversation.tsx`, `loader.tsx`, `message*.tsx`, `prompt-input.tsx`, `sources.tsx`, `conversation-empty-state.tsx`) use double quotes and semicolons, while their siblings `chat-widget.tsx`/`chat-panel.tsx`, `lib/` and `features/feed/` use single quotes and no semicolons. | Reformat to match, or accept. | Open |
| F8 | LOW | AC2 (defence in depth), AC6 | Source links use `source.url` unfiltered (`sources.tsx:34`), while answer links pass the http(s) filter. Sources come from backend card URLs, as in `web-chat-ui`, so this is not an AC2 violation. A markdown image inside a link renders an `<a>` with no accessible name (the image and its alt text are dropped). | Optional: apply the same http(s) check to `source.url`, and keep the image alt text as text (a custom `img` handler or `unwrapDisallowed` on `alt`). | Open |

Notes, not findings: the `?? ../../specs/archived/chat-agent-runtime/.sdd/` entry is dated 2026-10-14,
before this feature. On desktop, two buttons named "Close chat" are visible while the panel is open (the
launcher and the header X). This follows from AC11's launcher-name rule. The launcher's
`aria-controls` points at an unmounted id while closed, which `web-chat-ui` already did. H1 and H2 are
human-only.

## Audit log
| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-24 | APPROVED WITH RESERVATIONS | All 13 ACs and all binding constraints pass, with markdown safety checked against 25 adversarial inputs. The phone AC3 e2e test is flaky (F1). Unit 265/265, e2e 48/49 in the full rerun, lint 0 errors and 1 pre-existing warning, typecheck clean, build ok. |

## Final verdict

APPROVED WITH RESERVATIONS

**Summary**: The polish meets all 13 acceptance criteria and every binding constraint. The checks covered safe markdown under adversarial input, the byte-verbatim WEB-9 revision, an on-screen phone sheet with no overflow, exact-pin dependencies and the frozen shell. One phone auto-scroll e2e test is flaky because of a test-side race, so `npm run test:e2e` is not reliably green.

**Critical Issues** (must fix before merge):
- None. F1 is not CRITICAL by the severity scale, but fixing it before merge is strongly advised: the e2e gate fails about 1 run in 3.

**Warnings** (should fix, not blocking):
- F1: make `expectInView` tolerate a detached or `null` box, and re-run `-g latest --repeat-each=10`.
- F2: get a green `harny-feedback-apps-web` CI run on the PR. There is no evidence the per-turn hook fired.
- F3: add the desktop question-in-view check and a loader-in-view check for AC3.
- F4: red evidence is missing for O5 to O8. Accept it explicitly or capture it.

**Recommendations** (nice to have):
- F5: an e2e Shift+Enter newline check.
- F6: separate commits so the freeze can be proven by diff.
- F7: match the quote and semicolon style.
- F8: an http(s) filter on source URLs and image alt text kept as text.
- Lazy-load `MessageResponse` to recover about 39 KB gzip (plan Decision 15 follow-up).
- Human: H1 (distinct look) and H2 (on-screen keyboard on a real phone).

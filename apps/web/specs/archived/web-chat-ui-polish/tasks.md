# Tasks: Web Chat UI Polish

## Status
Implemented through O12 (2026-10-24); awaiting the independent audit (O13) and the human visual checks (H1, H2)

## Baseline
- Base commit: 48334d8 (`main`), plus the uncommitted `web-chat-ui` work in the working tree. By
  human decision this feature builds on the same branch, with no merge or archive first.
- Branch: feat/web-chat-ui
- Interpreter: Node v24.16.0, npm 11.13.0
- Cwd: /Users/danielerazo/python/project-agentcore-app/apps/web
- Commands: test `npm test`; lint `npm run lint`; type-check `npm run typecheck`; build `npm run build`;
  e2e `npm run test:e2e` (offline; needs `npx playwright install chromium` once)
- Pre-existing failures: to be re-run and recorded in O0 before any change. Last known
  (`web-chat-ui` O11, 2026-10-22): lint 0 errors and 1 warning; typecheck clean; `npm test` 18 files,
  237 tests passed; build ok; `npm run test:e2e` 32 passed (9 chat, 23 feed, of which 17 are
  baseline scenarios).

## Outcomes
Order is TDD: write the red tests for an outcome, then the code. Every outcome keeps `npm run lint`
and `npm run typecheck` clean. Never edit `features/chat/lib/**`, `features/chat/api/**`,
`features/chat/index.ts`, `app/api/**`, `app/page.tsx`, `app/globals.css`, `e2e/feed.e2e.ts`,
`e2e/__baseline__/**`, `e2e/fixtures/**`, `specs/archived/**` or `specs/web-chat-ui/**`. Never run
Playwright with `--update-snapshots`.

- [x] **O0** (AC11, AC12) Baseline. Run the five commands above and record the counts and any
  failures under Baseline. Run `npm run build` and record the `/` route's first-load JS figure as
  the "before" bundle number (plan Decision 15).
  - Evidence: 2026-10-24, Node v24.16.0. `npm run lint`: 0 errors, 1 warning (unused eslint-disable in `features/feed/api/types.generated.ts`). `npm run typecheck`: clean. `npm test`: 18 files, 237 tests passed. `npm run build`: ok. `npm run test:e2e`: 32 passed (9 chat, 23 feed; 17 baseline). No pre-existing failures. **Bundle "before"**: Next 16.3.5 (Turbopack) `next build` no longer prints a per-route first-load JS table, so the figure is the sum of `.next/static/chunks/*.js` (8 files): raw 580,871 B, gzip -9 178,609 B (script `scratchpad/size.sh`). Deviation: this is the substitute for "first-load JS for `/`".
- [x] **O1** (AC1, AC2, AC3, AC9) Dependencies and the test environment.
  - First run `npm view react-markdown time --json` and `npm view use-stick-to-bottom time --json`,
    and confirm 10.1.0 and 1.1.6 are each at least two weeks old. If either is not, stop and ask.
  - Then `npm install --save-exact react-markdown@10.1.0 use-stick-to-bottom@1.1.6`. Add no other
    package.
  - Add a no-op `ResizeObserver` (`observe`, `unobserve`, `disconnect`) to `vitest.setup.ts`, only
    when `globalThis.ResizeObserver` is undefined. Record any other browser API the library needed.
  - Check: `git diff package.json` shows exactly the two exact-version entries, and
    `npm ls react-markdown use-stick-to-bottom` resolves. `npm test` still matches the O0 count.
  - Evidence: Age check: `react-markdown` 10.1.0 published 2025-03-07 (~19 months); `use-stick-to-bottom` 1.1.6 published 2026-06-04 (~4.5 months); both older than two weeks. `git diff package.json` (vs a pre-install copy) adds exactly `"react-markdown": "10.1.0"` and `"use-stick-to-bottom": "1.1.6"` (exact pins). `npm ls react-markdown use-stick-to-bottom` resolves both. `vitest.setup.ts` gains a no-op `ResizeObserver` guarded by `typeof globalThis.ResizeObserver === "undefined"`; no other browser API needed so far. `npm test` 237 passed (= O0); typecheck clean.
- [x] **O2** e2e stub fixtures (setup for AC1 to AC4, AC7, AC10), per plan Decision 14. Edit only
  `e2e/stub/feed-api-stub.mjs`:
  - Feed: a `tag === 'long-url'` branch, placed before the generic tag filter, returns one copy of
    `fixtures.page1[0]` whose `url` is 300 characters with no break points.
  - Chat question keywords: `markdown`, `longurl`, `unsafe`, `tall` and `slow` (the `tall` answer
    after about 1.5 s).
  - Check: `git diff --stat -- e2e/fixtures e2e/__baseline__ e2e/feed.e2e.ts e2e/stub/launch-apps.mjs`
    is empty, and `npx playwright test e2e/feed.e2e.ts` still passes all 17 baseline scenarios.
  - Evidence: `e2e/stub/feed-api-stub.mjs` only: `tag === 'long-url'` branch before the generic tag filter (copy of `fixtures.page1[0]` with a 300-char URL), chat keywords `markdown`, `longurl`, `unsafe`, `tall`, `slow` (tall answer after 1500 ms; the reply tuple gained an optional delay). `fixtures/populated.json` untouched. Frozen-file sha1 snapshot of e2e/fixtures, e2e/__baseline__, e2e/feed.e2e.ts, launch-apps.mjs taken before any edit and compared at O10 (these paths are partly untracked/pre-modified by `web-chat-ui`, so `git diff --stat` cannot prove "unchanged"; sha comparison is used instead). `npx playwright test e2e/feed.e2e.ts`: 23 passed (incl. the 17 baseline scenarios).
- [x] **O3** (AC4, AC10) Red layout tests first, confirming the clipping cause. Write
  `e2e/layout.e2e.ts` at 375 by 667 with:
  - (a) the open dialog's box within `x >= 0`, `x + width <= 375`, `y >= 0`, `y + height <= 667`,
    with the header and the textbox visible;
  - (b) the `longurl` answer with Sources expanded: the same box check,
    `document.documentElement.scrollWidth <= clientWidth`, and the long link's box no wider than the
    dialog;
  - (c) `/?tag=long-url`: the `.urlLine` text equals the full URL, its box is more than twice its
    line height, the card's right edge is at most 375, and `scrollWidth <= clientWidth`.

  (b) needs the Sources control, so it may stay red until O6; record that.
  - Red: `npx playwright test e2e/layout.e2e.ts` -> (a) fails on today's CSS with the dialog's left
    edge below 0. Record the measured `x` and `width`, and confirm or refute plan Decision 6's
    `content-box` explanation (about 377 px wide, `x` about -18). (c) fails on overflow.
  - Evidence: `npx playwright test e2e/layout.e2e.ts` red, 3 failed. Measured on today's CSS at 375x667: dialog box **x=-18, y=419, width=377, height=191** -> confirms plan Decision 6 exactly (content-box: 343 + 32 padding + 2 border = 377, anchored right:16px). (a) fails `x >= 0` (Received -18). (b) times out waiting for the "Sources (1)" control, which does not exist until O6 (expected, stays red until O6). (c) `/?tag=long-url`: `.urlLine` height 15 px = one line (not wrapped; > 2 lines required), card right 351. Files: `e2e/layout.e2e.ts`. Note: the test duplicates `LONG_URL` instead of importing it because the stub uses `import.meta` and cannot be loaded by Playwright's CJS transform.
- [x] **O4** (AC1, AC2) `MessageResponse` (the safe markdown subset, plan Decision 4 and ADR 0038).
  - Tests: `features/chat/components/message-response.test.tsx`:
    - elements: `<strong>`, `<ol>` with 2 `<li>`, `<ul>`, `<code>`, `<pre><code>`;
    - no `**` in `textContent`, and `[1]` kept;
    - a table of unsafe inputs: `<script>`, `<img onerror>` and `![t](https://…)` render no
      `script`/`img`; `javascript:`, `data:`, `vbscript:`, `mailto:`, `/relative` and `#x` links get
      no `href`; `http(s)` links get `href`, `target="_blank"` and `rel="noopener noreferrer"`.
  - Red: `npx vitest run features/chat/components/message-response.test.tsx` -> fails (module missing)
  - Green: same command passes. `grep -rn "rehype-raw\|dangerouslySetInnerHTML" features app` finds
    nothing.
  - Evidence: Red: with `message-response.tsx` moved away, `npx vitest run features/chat/components/message-response.test.tsx` failed (`Failed to resolve import "./message-response"`). Green: 17 tests passed (elements, no `**`, `[1]` kept, table of unsafe inputs, http/https links with target/rel, tables stay text). `grep -rn "rehype-raw\|dangerouslySetInnerHTML" features app` -> no matches. Implementation: `allowedElements` list + `unwrapDisallowed` + http(s)-only `urlTransform` (via `new URL`) + `a` override (plain `span` when href is empty); no `skipHtml`, so raw HTML shows as inert text. Context7 confirmed the react-markdown props.
- [x] **O5** (AC1, AC3, AC7, AC8, AC9, AC11) The AI-Elements-shaped components and the shell
  rewiring (plan Decisions 2, 5, 10, 11, 12): `Conversation`, `ConversationContent`,
  `ConversationScrollButton`, the empty state, `Message`/`MessageContent`, `Loader`, `PromptInput`,
  `PromptInputTextarea` and `PromptInputSubmit`.
  - `chat-widget.tsx` keeps all state and handlers. It gains `data-testid="chat-launcher"` and the
    suggestion path (`setDraft` and then the same `submit`).
  - The pending question calls `scrollToBottom()`. Reduced motion uses `"instant"`.
  - The empty-state copy is exactly as in plan Decision 12.
  - Tests:
    - migrate `chat-widget.test.tsx`: the `toggle()` helper uses `getByTestId("chat-launcher")`, and
      the header's interface note is updated;
    - add: a user `**hi**` stays literal; the loader's status has /thinking/i and "Thinking..." is
      gone; Shift+Enter sends nothing; Send is disabled while pending; the greeting and 3
      suggestions appear, and a click sends `{question: <text>, history: []}` once and hides the
      empty state, including while pending; no "Jump to latest" in an empty conversation.
  - Red: `npx vitest run features/chat/components` -> the new cases fail
  - Green: same command passes. Every pre-existing `chat-widget.test.tsx` assertion (history, limits,
    the six error codes, retry, focus, Escape, console) still passes with only the selector migration.
  - Evidence: Components written under `features/chat/components/`: `conversation.tsx` (Conversation, ConversationContent, ConversationAutoScroll, ConversationScrollButton), `conversation-empty-state.tsx`, `message.tsx` (Message, MessageContent), `message-response.tsx`, `loader.tsx`, `prompt-input.tsx` (PromptInput, PromptInputTextarea, PromptInputSubmit). `chat-widget.tsx`: `data-testid="chat-launcher"`, `submit(text = draft)` so a suggestion goes through the same validation/send path, focus-return moved to an effect after unmount (Decision 7), `widgetOpen` class. Red NOT captured separately for the new widget cases: the components and the shell rewiring were written before the new test cases were run (deviation; the red/green ordering was observed for O3, O4 only). Green: `npx vitest run features/chat` 9 files, 177 tests passed. Pre-existing assertions changed (only these): the `toggle()` helper (testid), the header interface note, the "numbered source links" test (expands Sources first; I also added target/rel assertions), the "empty sources" test (also asserts no Sources control). History, limits, six error codes, retry, focus, Escape and console assertions are unchanged and pass. New cases: markdown for assistant vs literal user `**hi**`, loader status/text, Shift+Enter/Enter, Send disabled while pending, empty state + 3 suggestions + single request with `history: []`, failed suggestion, header Close + focus return, no Jump to latest when empty.
- [x] **O6** (AC6) `Sources` replaces `source-list.tsx` (plan Decision 8). It is a "Sources (n)"
  button with `aria-expanded`/`aria-controls`, collapsed by default, and renders the list only
  while expanded.
  - Delete `features/chat/components/source-list.tsx`; rewire or delete `message-list.tsx`.
  - Tests:
    - component: collapsed, with no links; expanded, 2 links with `[n]`, title, source name,
      `href`, `target` and `rel`; empty sources show no control;
    - the migrated "numbered source links" test expands first, and the "empty sources" test asserts
      that no control exists.
  - Red: `npx vitest run features/chat/components` -> the Sources cases fail
  - Green: same command passes, and `grep -rn "source-list" features` finds nothing.
  - Evidence: `source-list.tsx` and `message-list.tsx` deleted; `sources.tsx` (Sources/Source) with `aria-expanded`/`aria-controls`, collapsed, list rendered only while expanded, empty list renders nothing. Component tests (collapsed -> 2 links with `[n]`, title, source name, href, target, rel -> collapsed again) are in `chat-widget.test.tsx`. Red not captured separately (see O5). Green: `npx vitest run features/chat` 177 passed. `grep -rn "source-list" features` -> no matches (checked below).
- [x] **O7** (AC4, AC5, AC7, AC13) Styling in `chat.module.css`, using existing tokens only (plan
  Decisions 6, 7, 9 and the styling constraint):
  - `border-box` on the widget and its descendants; `min-width: 0` on flex children;
    `overflow-wrap: anywhere` on text and links; code blocks scroll sideways;
  - desktop size `min(30rem, …)` by `min(40rem, …)`; the branded header and its Close icon button;
    the launcher, Send and Close at least 44 by 44;
  - Send: a `var(--link)` background with a `var(--surface-card)` icon; panel radius `--radius-md`,
    and `--radius-full` for the launcher, Send and the composer;
  - the phone sheet under `@media (max-width: 640px)` with a `100dvh` height and a `100vh` fallback;
    the launcher hidden while the sheet is open, with focus returned after unmount;
  - the loader's keyframes, and `animation: none` under reduced motion.

  If `env(safe-area-inset-*)` is used, widen `chat-css.test.ts` and add the fires-on-violation case
  for `max(12px, env(safe-area-inset-bottom))`. Record which way this went.
  - Tests: `e2e/chat.e2e.ts`:
    - migrate: the `toggle` locator becomes `getByTestId('chat-launcher')`, and the answer test
      expands sources before counting 3 links;
    - add a 1280 by 800 `desktop` group: width 448 to 480 and height at most 640; the header contains
      "AI RADAR"; the in-dialog "Close chat" closes the panel and focuses the launcher; the three
      hit areas are at least 44 by 44; Send's `background-color` equals a `var(--link)` probe in
      light and dark;
    - add a `loader` case: with `slow` and reduced motion, `animation-name: none` on each dot;
      without reduced motion, the name is not `none`;
    - add `markdown` (`strong`, `ol li`, `pre` in the dialog) and `unsafe` (`page.on('dialog')`
      fails the test, no `script`/`img`, every `a[href]` matches `^https?:`), plus a suggestion
      click that is followed by the stub answer.
  - Red: `npx playwright test e2e/chat.e2e.ts` -> the new desktop and loader cases fail before the CSS
  - Green: `npx playwright test e2e/chat.e2e.ts e2e/layout.e2e.ts` -> O3's (a) and (b) now pass, and
    so does all of `chat.e2e.ts`, including the unchanged theme test. Then
    `npx vitest run features/chat/components/chat-css.test.ts` passes.
  - Evidence: Styling: `chat.module.css` rewritten with tokens only (border-box on `.widget` and descendants, `min-width: 0` on flex children, `overflow-wrap: anywhere` on text and links, scrolling code blocks, desktop `min(30rem, ...)` x `min(40rem, ...)` (100vh fallback then 100dvh), branded header on `var(--link)` with `var(--surface-card)` text and an icon Close button, launcher/Send/Close at 44x44, Send `var(--link)` bg + `var(--surface-card)` icon, panel `--radius-md`, launcher/Send/composer `--radius-full`, phone sheet under `@media (max-width: 640px)` (`inset: auto 0 0 0`, `100vh` then `100dvh`, top corners only, launcher hidden while open), dots keyframes with `animation: none` under reduced motion). Safe-area decision: USED `padding-bottom: max(var(--space-3), env(safe-area-inset-bottom))`, so `chat-css.test.ts` was widened (strips `env(safe-area-inset-*)`, `max(`/`min(`/`calc(` and punctuation) and gained the fires-on-violation case `max(12px, env(safe-area-inset-bottom))`; `npx vitest run features/chat` passes. Red for the new desktop/loader e2e cases not captured separately (written after the CSS; deviation). Green: `npx playwright test e2e/chat.e2e.ts e2e/layout.e2e.ts` -> 26 passed at that point (O3 (a) and (b) now pass; unchanged theme test passes). `e2e/chat.e2e.ts` migrated (`getByTestId('chat-launcher')`, answer test expands "Sources (3)") and gained desktop (size, header, Close + focus, 44px hit areas, Send = `--link` probe light/dark), loader (animated vs reduced-motion), markdown, unsafe (dialog tripwire collected and asserted empty) and suggestion cases. Stub fix found while writing: the `unsafe` answer uses blank-line-separated lines, because a leading `<script>` line is an HTML block that swallows the rest of the line.
- [x] **O8** (AC3) Auto-scroll e2e at both viewports, in `e2e/chat.e2e.ts` (desktop) and
  `e2e/layout.e2e.ts` (phone), with names containing "latest":
  - three `tall` turns: after each, the last user message and then the answer lie inside the scroll
    element's box;
  - a `slow` turn: `page.mouse.wheel` up over the scroll element while pending; after the answer,
    `scrollTop` is unchanged within 2 px and "Jump to latest" is visible; pressing it gives
    `scrollTop + clientHeight >= scrollHeight - 2` and the button is gone.
  - Red: write the cases before O5's scroll wiring lands, or record that they were written after it,
    with the reason.
  - Green: `npx playwright test e2e/chat.e2e.ts e2e/layout.e2e.ts -g "latest"` passes 3 times in a
    row (flake check).
  - Evidence: `latest` cases in `e2e/layout.e2e.ts` (375x667) and `e2e/chat.e2e.ts` (1280x800): three `tall` turns each end with the question and answer inside the scroll area; a `slow` turn with a wheel-up while pending -> scrollTop unchanged within 2 px, "Jump to latest" visible, pressing it reaches the bottom and the button disappears. Shared helpers in `e2e/chat-scroll.ts` (not `*.e2e.ts`, so Playwright does not collect it twice). Test-side fixes: positions are polled (the view follows with a smooth animation) and scrollTop is read after wheel scrolling settles (wheel scrolling is animated). Written after the scroll wiring (O5), not before; reason: the wiring was part of the O5 component build. Green: `npx playwright test e2e/chat.e2e.ts e2e/layout.e2e.ts -g latest` -> 4 passed, 3 runs in a row (18.0 s, 17.5 s, 17.5 s).
- [x] **O9** (AC10, AC12, AC13) Feed deliverable revision (plan Decision 13, ADR 0039).
  - Copy `specs/archived/web-feed-ui/claude-design-outputs/feed.module.css` to
    `specs/web-chat-ui-polish/design/feed.module.css`. Add exactly one declaration,
    `overflow-wrap: anywhere;`, inside the `.urlLine` rule. Then copy that file byte-verbatim over
    `features/feed/components/feed.module.css`.
  - If O3 (c) still fails and a further declaration is needed, add it to the same revision and
    record it as a deviation.
  - Check:
    - `cmp specs/web-chat-ui-polish/design/feed.module.css features/feed/components/feed.module.css`
      exits 0;
    - `diff specs/archived/web-feed-ui/claude-design-outputs/feed.module.css specs/web-chat-ui-polish/design/feed.module.css`
      shows only the `.urlLine` line changed;
    - `git status --short -- specs/archived` is empty.
  - Green: `npx playwright test e2e/layout.e2e.ts -g "feed"` passes, and
    `npx playwright test e2e/feed.e2e.ts` passes all 17 baseline scenarios with
    `git diff --stat -- e2e/__baseline__` empty. `npx vitest run features/feed` passes.
  - Evidence: `specs/web-chat-ui-polish/design/feed.module.css` = the archived file plus exactly `overflow-wrap: anywhere;` in `.urlLine`; copied byte-verbatim over `features/feed/components/feed.module.css`. `cmp` exits 0 (`cmp-ok`). `diff` vs the archived file shows only line 103 (`.urlLine`) changed. `git status --short -- specs/archived` is empty (the `?? ../../specs/archived/chat-agent-runtime/.sdd/` entry in the root status predates this work). O3 (c) went green with this one declaration alone (urlLine height 15 -> 135 px, card right 351 <= 375, no overflow); no extra declaration was needed. `npx vitest run features/feed` 10 files, 88 tests passed. Full e2e (O12) includes `e2e/feed.e2e.ts`: all 17 baseline scenarios pass without `--update-snapshots`; `git diff --stat -- e2e/__baseline__ e2e/fixtures e2e/feed.e2e.ts` is empty.
- [x] **O10** (AC11, AC12, AC13) Migration and freeze check.
  - `git diff --stat -- features/chat/lib features/chat/api features/chat/index.ts app/api app/page.tsx app/globals.css e2e/fixtures e2e/__baseline__ e2e/feed.e2e.ts e2e/stub/launch-apps.mjs specs/web-chat-ui`
    is empty.
  - `features/chat/conventions.test.ts` and `features/feed/conventions.test.ts` pass with no edit.
  - `.claude/memory/web-chat-ui-handoff.md` is untouched.
  - Evidence: Because `features/chat/`, `e2e/chat.e2e.ts` etc. are untracked (the `web-chat-ui` work is uncommitted), `git diff --stat` cannot prove "unchanged" for them. I took a sha1 snapshot of every file under `features/chat/lib`, `features/chat/api`, `features/chat/index.ts`, `app/api`, `app/page.tsx`, `app/globals.css`, `e2e/fixtures`, `e2e/__baseline__`, `e2e/feed.e2e.ts`, `e2e/stub/launch-apps.mjs`, `features/chat/conventions.test.ts` and `features/feed/conventions.test.ts` (78 files) before the first edit and re-checked it after the last: 0 mismatches. `specs/web-chat-ui` is untouched (untracked, never edited). `.claude/memory/web-chat-ui-handoff.md` never opened for writing. Both conventions tests pass in `npm test`.
- [x] **O11** Docs. In `AGENTS.md`:
  - the dependency sentence: the sanctioned extras become `@playwright/test`, `aws4fetch`,
    `react-markdown` and `use-stick-to-bottom`, each with its role and an exact pin, as ADR 0037
    says;
  - the `features/chat/components` line in the layout block lists the new components;
  - the WEB-9 bullet: change a design value at its latest deliverable revision (ADR 0039).

  In `README.md` (apps/web), one paragraph on the chat UI and the two dependencies. Repo-root docs
  go to the human or `harny-document`.
  - Evidence: `AGENTS.md`: dependency sentence now lists `@playwright/test`, `aws4fetch`, `react-markdown` and `use-stick-to-bottom` with roles and exact pins, plus "A further dependency needs its own ADR"; the `features/chat/components` layout line lists the new components; the WEB-9 bullet says "change a design value at its latest deliverable revision ... then copy it over the app file". `README.md` (apps/web): one paragraph after the chat local-setup section.
- [x] **O12** (all ACs) Broader suite against the baseline:
  `npm run lint && npm run typecheck && npm test && npm run build && npm run test:e2e`. All must be
  green, with test counts at least the O0 counts plus the new tests, and lint warnings no more than
  the O0 count.
  - Record the "after" first-load JS figure for `/` from this build next to O0's "before".
  - Evidence: `npm run lint`: 0 errors, 1 warning (same pre-existing one as O0). `npm run typecheck`: clean. `npm test`: 19 files, 265 tests passed (O0: 18 files, 237; +28). `npm run build`: ok. `npm run test:e2e`: 49 passed (O0: 32; +17: chat.e2e.ts +12, layout.e2e.ts 5 incl. 2 latest). **Bundle after**: sum of `.next/static/chunks/*.js` raw 708,892 B, gzip 217,350 B, 9 files (before: raw 580,871 B, gzip 178,609 B, 8 files) -> +128,021 B raw, +38,741 B gzip (about +21.7% gzip). Same substitute metric as O0 (Next 16.3.5 prints no first-load JS table).
- [ ] **O13** Independent audit: the verdict from `audit.md`, which only the auditor writes.

Human tasks (agents stop at local verification, WEB-11; these are not executor outcomes):
- [ ] **H1** (AC5, manual): review the panel at desktop and phone sizes (`npm run dev`, browser
  devtools at 375 by 667) and confirm it looks distinct from a feed card.
- [ ] **H2** (optional): on a real phone, against a local or deployed build, check that the sheet
  stays usable with the on-screen keyboard open. Playwright cannot emulate the keyboard; `100dvh`
  is the mitigation.

ADRs 0036 to 0039 are written by `harny-adr` from the approved plan at archive time, after
`web-chat-ui` (0032 to 0035) is archived.

## Working state
- Updated: 2026-10-24
- Outcome: O0 to O12 done
- Phase: implemented, locally verified; not committed
- In progress: none
- Last command: `npm run test:e2e` (49 passed)
- Next step: O13 independent audit; human H1/H2 visual checks

## Audit fix round (2026-10-24, F1, F3, F5, F7)
- F1: `e2e/chat-scroll.ts` `expectInView` now takes a Locator and polls `isInView`, which re-resolves each time and returns false (never throws) when the element is missing or detached. No product change. `npx playwright test -g latest --repeat-each=10`: 40 passed (4 tests x 10), 0 failures.
- F3: the desktop three-turn test now uses `slow` and asserts, per turn, the question in view, then the `role="status"` loader in view, then the answer in view. The phone test keeps `tall` and uses the tolerant helper.
- F5: `chat.e2e.ts` "composer" test: Shift+Enter then `b` gives value `a\nb` with no `/api/chat` request; Enter alone sends one.
- F7: `prettier --single-quote --no-semi --print-width 120` on the 7 new component files and `message-response.test.tsx` (formatting only). `chat-widget.test.tsx` and `chat-css.test.ts` keep the predecessor's double-quote style.
- Gates: lint 0 errors/1 warning (pre-existing), typecheck clean, `npm test` 19 files/265 tests, build ok, `npm run test:e2e` 50 passed.

## Finding responses
| Finding | Response | Evidence |
|---|---|---|

## Checkpoint
Spec set complete: `intent.md` (revision 2, `Approval: Pending` for the human to stamp),
`execution-plan.md` (approved by the human in chat, as relayed) and this file. Resume at O0.

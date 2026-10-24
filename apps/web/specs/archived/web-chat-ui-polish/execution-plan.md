# Execution Plan: Web Chat UI Polish

## Guidance consulted
- `apps/web/AGENTS.md` (layout, WEB-1 to WEB-9, barrel rule, the dependency sentence), the repo-root
  `CLAUDE.md` (two harness roots, shared ADR numbering) and the `high-value-tests` skill.
- `harny-sync` lookup: `apps/web/specs/current/_index.md` and `web-feed.md` (WEB-1 to WEB-11,
  invariants 1 to 4, ADR 0005 byte-verbatim tokens), and the repo-root `specs/current/_index.md`
  (next ADR 0032). The predecessor `specs/web-chat-ui/` (intent revision 2, plan, tasks, audit
  round 1 APPROVED WITH RESERVATIONS, not archived) reserves 0032 to 0035, so this plan uses
  **0036 to 0039** (human decision, intent revision 2).
- Code read: `features/chat/**` (all components, `chat.module.css`, `chat-css.test.ts`,
  `chat-widget.test.tsx`, `conventions.test.ts`, `lib/conversation.ts`, `lib/limits.ts`,
  `api/types.ts`), `features/feed/components/feed.module.css` and `card-item.tsx`, `app/globals.css`
  (token list), `app/layout.tsx`, `app/page.tsx`, `e2e/chat.e2e.ts`, `e2e/feed.e2e.ts` (baseline
  capture: DOM class lists plus a fixed `STYLE_PROPS` set), `e2e/stub/feed-api-stub.mjs`,
  `playwright.config.ts`, `vitest.config.mts`, `vitest.setup.ts`, `package.json`.
- `cmp` confirms `features/feed/components/feed.module.css` and `app/globals.css` are byte-identical
  to `specs/archived/web-feed-ui/claude-design-outputs/feed.module.css` and `tokens.css`.
- Library facts verified against current docs on 2026-10-24, with Context7 (`/remarkjs/react-markdown`,
  `/stackblitz-labs/use-stick-to-bottom`) and `npm view`:
  - `react-markdown` 10.1.0, peer `react >=18`, ESM. Props `allowedElements` / `disallowedElements`
    (mutually exclusive), `unwrapDisallowed`, `skipHtml` (default `false`), `components`,
    `urlTransform(url, key, node)` (default `defaultUrlTransform`, which also allows `mailto`, `irc`,
    `ircs`, `xmpp` and relative URLs). With no `rehype-raw`, raw HTML is kept as text, never as
    elements; `skipHtml` drops it instead.
  - `use-stick-to-bottom` 1.1.6, zero dependencies, peer `react ^16.8 || ^17 || ^18 || ^19`.
    `<StickToBottom initial resize className>` and `<StickToBottom.Content scrollClassName>` render
    an outer scroll element and an inner content element watched by a `ResizeObserver`.
    `useStickToBottomContext()` gives `isAtBottom` (true within 70 px), `escapedFromLock`,
    `scrollToBottom()` and `stopScroll()`. When the user scrolls up, the lock is escaped and growing
    content no longer moves the view.

## Ownership
- New: `features/chat/components/` `conversation.tsx`, `conversation-empty-state.tsx`,
  `message.tsx`, `message-response.tsx`, `sources.tsx`, `loader.tsx`, `prompt-input.tsx` (names are
  suggestions; the AI Elements export names in the intent are what is pinned), their colocated tests,
  `e2e/layout.e2e.ts`, `specs/web-chat-ui-polish/design/feed.module.css` (the revised deliverable).
- Changed: `features/chat/components/chat-widget.tsx`, `chat-panel.tsx`, `chat.module.css`,
  `chat-widget.test.tsx`, `chat-css.test.ts` (only if Decision 9 needs it); `message-list.tsx` is
  rewired or removed; `source-list.tsx` is removed. `features/feed/components/feed.module.css` (the
  re-copy only). `e2e/chat.e2e.ts`, `e2e/stub/feed-api-stub.mjs`, `vitest.setup.ts`, `package.json`,
  `package-lock.json`, `AGENTS.md`, `README.md` (apps/web).
- Not touched: `features/chat/lib/**`, `features/chat/api/**`, `features/chat/index.ts`,
  `app/api/chat/route.ts`, `app/page.tsx`, `app/globals.css`, all `features/feed/` source other than
  the CSS re-copy, `e2e/feed.e2e.ts`, `e2e/__baseline__/**`, `e2e/fixtures/**`,
  `e2e/stub/launch-apps.mjs`, `specs/archived/**`, `specs/web-chat-ui/**`, anything outside
  `apps/web/`, and `.claude/memory/web-chat-ui-handoff.md`.
- Affected `specs/current` capabilities: `web-feed` (WEB-9's deliverable pointer, ADR 0039) and
  `web-chat`, the capability `web-chat-ui` creates when it is archived. At archive time
  `web-chat-ui` goes first, then this feature.

## Binding constraints
- The shell's behavior is frozen: `lib/conversation.ts`, `lib/send-turn.ts`, `lib/limits.ts`,
  `lib/history.ts`, `api/**`, the route and the barrel (exactly `ChatWidget`, `handleChatRequest`)
  are not edited. One same-origin `POST /api/chat` per turn, no retry (intent AC11; `web-chat-ui`
  plan, binding "exactly one backend call").
- New code under `features/chat/` keeps the chat guards: `components/` and `lib/` use only
  `import type` from `api/`, no `"use client"` module imports the barrel or `api/`, no
  `NEXT_PUBLIC_`, no `CHAT_API_*` name outside `api/`, and no `.sort(` / `.reverse(` anywhere under
  `features/` (source: `features/chat/conventions.test.ts`, feed T31, WEB-1, WEB-3).
- Exactly two new direct dependencies, both runtime and both exact pins: `react-markdown@10.1.0` and
  `use-stick-to-bottom@1.1.6`, installed with `npm install --save-exact`. No `remark-gfm`, no
  `rehype-raw`, no icon or UI library. Before installing, the executor re-checks each version with
  `npm view <pkg> time --json` and confirms it is at least two weeks old (source: ADR 0037; the
  `aws4fetch` precedent).
- Markdown safety (intent AC2, ADR 0038): no `rehype-raw` or `dangerouslySetInnerHTML` anywhere. A
  custom `urlTransform` returns the URL only when it parses as `http:` or `https:`, and `''`
  otherwise. Images are disallowed. Rendered links carry `target="_blank"` and
  `rel="noopener noreferrer"`. User messages are never passed to the markdown renderer.
- Styling (WEB-8, WEB-9, ADR 0005, intent AC13): `chat.module.css` takes every colour, spacing and
  radius from an existing `app/globals.css` token. No new token. Panel radius `--radius-md`; the
  launcher, Send and the composer use `--radius-full`. The Send background is `var(--link)` with a
  `var(--surface-card)` icon. The panel background stays `var(--surface-card)`, which the existing
  e2e theme test asserts. Icons are inline SVG drawn with `currentColor`, with `aria-hidden="true"`.
  Size, position, `z-index`, hit-area height, font size and the breakpoint are layout literals, as
  `web-chat-ui` Decision 10 allows.
- WEB-9 for the feed (ADR 0039): `specs/web-chat-ui-polish/design/feed.module.css` is the archived
  deliverable plus exactly one declaration, `overflow-wrap: anywhere;`, inside the `.urlLine` rule.
  `features/feed/components/feed.module.css` is then a byte-verbatim copy of it. The archived file
  is never edited.
- The 17 feed baseline scenarios pass unchanged and are never run with `--update-snapshots`. No feed
  element gains or loses a class, and no feed fixture changes (source: `e2e/feed.e2e.ts` header;
  intent AC12).
- The e2e tier is offline: the chat route signs with fake credentials against the local stub, and
  nothing calls AWS (source: `web-chat-ui` AC9).
- Agents stop at local verification. There is no `vercel`, `cdk` or `aws` command (WEB-11, ADR 0007).

## Proposed approach
Revisable by the executor if it records why.

1. **ADR 0036: AI-Elements-shaped local components, not shadcn/ui or AI Elements.** The human
   decided this before drafting, and the ADR records the reasons. The app has no Tailwind.
   `shadcn init` rewrites `globals.css`, which would break WEB-9 and the CSS Modules setup.
   AI Elements pulls in `ai`, `@ai-sdk/react`, `streamdown` and Radix for a stream the backend
   does not send. The local components copy AI Elements' names and composition, so a later move to
   it would be a rename, not a redesign. Rejected: adopting either library (above); keeping the
   current monolithic `message-list.tsx` (it does not separate user text from rendered markdown).
2. **Component split.** `chat-widget.tsx` keeps all state and handlers (`draft`, `inputError`, the
   reducer, `send`, `submit`, `retry`, focus and Escape). `chat-panel.tsx` composes, in order: the
   header (an "AI RADAR" wordmark in mono with a subtitle such as "Ask about the cards", plus a Close
   icon button), `Conversation` (it wraps `<StickToBottom>`; `ConversationContent` wraps
   `<StickToBottom.Content>` and keeps `aria-live="polite"`), the empty state, the existing alert and
   Retry block, and `PromptInput`. `Message from="user"` renders plain text with `pre-wrap`.
   `Message from="assistant"` renders `MessageResponse` and then `Sources`. While a turn is pending,
   the pending question is a user `Message`, followed by the `Loader`. The wordmark string is a
   local constant: the chat must not import `features/feed` internals.
3. **ADR 0037: dependency rule amendment.** `AGENTS.md`'s "only sanctioned extra dependencies"
   sentence gains `react-markdown` (runtime, exact pin, rendering assistant answers only) and
   `use-stick-to-bottom` (runtime, exact pin, the conversation scroll only). The ADR also records:
   - why `use-stick-to-bottom` beats a hand-written hook. It handles content that grows after
     layout (markdown, expanding sources), tells a user scroll from a programmatic one, and exposes
     the escape state. A hand-written `scrollIntoView` plus scroll-listener hook would have to
     rebuild that and is the usual source of "yanks the reader" bugs. It has no dependencies, and
     AI Elements' `Conversation` is built on it;
   - why `remark-gfm` is rejected (human decision): tables cannot fit a 375 px sheet;
   - that a future dependency needs its own ADR.

   Rejected: the hand-written hook (above).
4. **ADR 0038: safe markdown subset.** `MessageResponse` renders `<Markdown>` with:
   - `allowedElements`: `p`, `strong`, `em`, `ol`, `ul`, `li`, `a`, `code`, `pre`, `blockquote`,
     `br`, `hr`, `h1` to `h6`, with `unwrapDisallowed`. That drops `img` and keeps the text of
     anything else;
   - the http/https-only `urlTransform`;
   - an `a` component override that adds `target`/`rel` and the wrap class, and renders a plain
     `<span>` when the transformed `href` is empty;
   - the default raw-HTML handling, so HTML shows as inert text the reader can see, rather than
     `skipHtml` silently dropping it.

   Headings are styled down to body-adjacent sizes. Code blocks get `overflow-x: auto` and
   `max-width: 100%` inside the bubble. Rejected: `defaultUrlTransform` (it allows `mailto`, `irc`,
   `xmpp` and relative links, which point at our own origin); `skipHtml` (it hides what the model
   wrote with no trace; either choice is safe).
5. **Auto-scroll.** `<StickToBottom initial="instant" resize="smooth">`, using `"instant"` for both
   when `prefers-reduced-motion: reduce` matches. A small child inside `Conversation` calls
   `scrollToBottom()` when `pending` turns non-null, so sending always re-locks to the bottom, even
   if the reader had scrolled up. An answer arriving while the lock is escaped does not move the
   view. `ConversationScrollButton` reads `isAtBottom` from `useStickToBottomContext()` and renders a
   button named "Jump to latest" only when it is false.
6. **Phone sheet and the overflow fix.** Probable cause of the clipping, to be confirmed by the red
   e2e test before the fix: `.panel` is `content-box`, because the feed's `box-sizing` reset covers
   only `.feedPage` descendants and the widget is a sibling. At 375 px,
   `min(24rem, 100vw - 32px)` = 343 px of content plus 32 px of padding plus 2 px of border makes a
   377 px box anchored `right: 16px`, so its left edge is at about -18 px. A fixed element clipped on
   the left adds no scroll width, which is why AC4 also asserts the panel's bounding box. The fix:
   - `box-sizing: border-box` on `.widget` and its descendants;
   - `min-width: 0` on flex children (the textarea, message bubbles, the scroll element);
   - `overflow-wrap: anywhere` on message text, markdown links and source links.

   Under `@media (max-width: 640px)`, the panel is `position: fixed` across the full width at the
   bottom (`inset: auto 0 0 0`), with `height: 100vh` followed by a `100dvh`-based height as the
   override, and rounded top corners only.
7. **Launcher on a phone.** While the sheet is open on a phone, the launcher is hidden. The Close
   button in the header is the visible way to close the panel, and Escape still works. Focus returns
   to the launcher after the panel has unmounted and the launcher is visible again (an effect on the
   open-to-closed transition, not a synchronous `focus()` before re-render). On desktop the launcher
   stays visible and still toggles. The launcher gets `data-testid="chat-launcher"`, because it is
   no longer the only button with `aria-expanded` (the Sources control has one too). Sizes:
   - launcher, Send and Close: at least 44 by 44 px;
   - desktop panel: `width: min(30rem, 100vw - 2 * var(--space-4))` and
     `height: min(40rem, 100dvh - <launcher clearance>)`.
8. **Sources.** A `button` "Sources (n)" with `aria-expanded` and `aria-controls`, collapsed by
   default. The list is rendered only while expanded, which keeps hidden links out of the
   accessibility tree and out of tab order. The links keep `[n]`, title and source name. An empty
   list renders nothing. `<details>` is rejected because `summary` exposes no `aria-expanded`
   attribute that the tests and the AI Elements shape rely on.
9. **Safe-area insets and `chat-css.test.ts`.** If the sheet pads its bottom with
   `env(safe-area-inset-bottom)` (as in `max(var(--space-3), env(safe-area-inset-bottom))`), the
   spacing checker is widened to strip `env(safe-area-inset-(top|right|bottom|left))` and the
   `max(`/`calc(` punctuation around tokens. A new fires-on-violation case shows that
   `max(12px, env(safe-area-inset-bottom))` is still flagged. A device inset is not a design value.
   If the executor finds the sheet needs no inset, the test stays unchanged; record which.
10. **Loader.** Three dots as `span`s animated with CSS keyframes inside a `role="status"` element
    carrying visually hidden text "Thinking". Under `@media (prefers-reduced-motion: reduce)`:
    `animation: none`.
11. **Composer.** `PromptInput` is a form-like wrapper. `PromptInputTextarea` keeps
    `aria-label="Your question"`, the existing Enter and Shift+Enter handling, and `rows` of about 2
    to 3. `PromptInputSubmit` is an icon button with `aria-label="Send"`, disabled while pending. The
    validation messages and their `role="alert"` stay in the shell.
12. **Empty state.** Shown when there are no messages and nothing is pending. It holds a greeting
    and three suggestion buttons. Pressing one does `setDraft(text)` and then the same `submit` path,
    so validation, `send`, draft clearing and restore-on-failure are the existing code. The copy is
    for the human to review at plan approval; none of it contains "send", so the `/send/i` selectors
    stay unique:
    - Greeting: "Hi, I can answer questions about the AI news cards on this page, with sources."
    - "What are the most important AI stories right now?"
    - "Which new AI models or tools were released recently?"
    - "What is the latest research on AI agents?"
13. **ADR 0039: deliverable revisions live with the feature.** To fix a byte-verbatim CSS file, copy
    the latest deliverable into `specs/<feature>/design/`, change it there, and copy it over the app
    file. The archived revisions are never edited, because archives are integrity-checked records.
    WEB-9's "deliverable" means the latest revision. The feed fix adds only
    `overflow-wrap: anywhere;` to `.urlLine`. No `min-width: 0` should be needed, because `.card` is
    a stretched item of a column flexbox, so its width is not set by min-content. If the red test
    shows otherwise, the extra declaration goes in the same deliverable and is recorded as a
    deviation. Rejected: editing the archived file (breaks the archive's integrity record); an
    app-owned override class (changes the class lists the DOM baselines capture).
14. **e2e fixtures without touching the baselines.**
    - Feed stub: a new `tag === 'long-url'` branch, placed before the generic tag filter, returns
      one card copied from `fixtures.page1[0]` with a 300-character URL that has no break points.
      `fixtures/populated.json` is not edited.
    - Chat stub, new question keywords (each distinct from the existing `throttle`, `timeout`,
      `broken` and `forbidden`):
      - `markdown`: bold, a numbered list, a bulleted list, inline code and a fenced block;
      - `longurl`: a markdown link and a fenced line with a 300-character URL, plus a source with
        that URL;
      - `unsafe`: `<script>`, a `javascript:` link, `<img onerror>`, a markdown image and a `data:`
        link;
      - `tall`: several paragraphs, enough to overflow the message area;
      - `slow`: the `tall` answer after a delay of about 1.5 s.
15. **Bundle.** `react-markdown` adds client JS to the feed page's chat chunk. The executor records
    the first-load JS figure from `next build` before and after in `tasks.md`. Lazy-loading
    `MessageResponse` is a possible follow-up, not part of this plan.
16. **`vitest.setup.ts`.** Add a no-op `ResizeObserver` class (`observe`, `unobserve`, `disconnect`)
    when `globalThis.ResizeObserver` is undefined. jsdom has none and `use-stick-to-bottom` needs
    one. Add any other missing browser API the library touches, recorded in `tasks.md`. Component
    tests do not assert scroll positions; those live in Playwright.

## Consumers and migration
- `features/chat/components/chat-widget.test.tsx`:
  - the header's "interface the tests fix" note and the `toggle()` helper move from "the only
    button with `aria-expanded`" to `getByTestId("chat-launcher")`;
  - the "numbered source links" test expands "Sources (n)" first;
  - the "empty sources" test also asserts that no Sources control exists;
  - the status, history, limits, failure, retry, focus and console tests keep their assertions.
    That they still pass is the compatibility proof for AC8 and AC11.
- `e2e/chat.e2e.ts`: `toggle` becomes `page.getByTestId('chat-launcher')`; the answer test expands
  sources before counting 3 links; the theme test is unchanged (the panel stays
  `var(--surface-card)`). New desktop scenarios go here; phone and overflow scenarios go in the new
  `e2e/layout.e2e.ts`.
- `features/chat/components/chat-css.test.ts`: changes only under Decision 9.
- `features/chat/conventions.test.ts` and `features/feed/conventions.test.ts`: no change. New files
  sit under `components/`, so the layout guard still holds.
- `source-list.tsx` is deleted and `message-list.tsx` rewired or deleted; only `chat-panel.tsx`
  imports them today.
- `AGENTS.md`:
  - the dependency sentence (ADR 0037);
  - the `features/chat/components` line in the layout block;
  - the WEB-9 bullet ("change a design value at its latest deliverable revision", ADR 0039).

  `README.md` (apps/web): one paragraph on the chat UI and the two new dependencies.
- `e2e/stub/feed-api-stub.mjs`: the new feed tag and chat keywords (Decision 14).
  `launch-apps.mjs` is unchanged.
- The `web-chat-ui` spec files are not edited. Its AC1, AC2 and AC8 statements are superseded as
  intent Constraints list, and the `web-chat` capability doc records both features at archive time.
- ADRs 0036 to 0039 are written by `harny-adr` from this approved plan, as for `web-chat-ui`.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A markdown answer injects script or a hostile link | Low | High | No `rehype-raw`, http/https-only `urlTransform`, images disallowed; component and e2e XSS tests with a `page.on('dialog')` tripwire |
| A feed baseline changes | Low | High | Only one declaration in an existing rule, no class or fixture change, long-URL card behind a new stub tag; `npx playwright test e2e/feed.e2e.ts` and `git diff --stat -- e2e/__baseline__` |
| Selectors break because the launcher is no longer the only `aria-expanded` button | High (certain) | Low | `data-testid="chat-launcher"`, migrated in both test files |
| jsdom lacks `ResizeObserver`, so component tests crash | High | Low | Decision 16 stub; scroll behavior tested in Playwright only |
| Wheel-driven "scroll up" in e2e is flaky against the library's escape detection | Med | Med | Use `page.mouse.wheel` over the scroll element (real input events), wait for `escapedFromLock` to show as the Jump button, use the `slow` stub keyword |
| Focus is lost on close when the launcher is hidden on a phone | Med | Med | Focus after unmount (Decision 7); the existing focus tests plus a phone e2e check |
| `overflow-wrap: anywhere` changes a recorded feed computed style at desktop | Low | Med | `overflowWrap` is not in `STYLE_PROPS` and the block width is unchanged; the baselines are the check |
| Client bundle grows | Med | Low | Record the before and after numbers (Decision 15); lazy loading is a follow-up |
| A new package is too fresh or later unmaintained | Low | Low | Exact pins, the age check, and each library used in one file |

## Validation
One row per AC. Vitest 4 with jsdom and Testing Library for component tests, and Playwright
(Chromium) for e2e, offline against the stub. Phone viewport 375 by 667, desktop 1280 by 800, set
with `test.use({ viewport })` per `describe`. All commands run in `apps/web`. The e2e
`webServer` rebuilds the app, so each Playwright command takes a few minutes.

| AC | Demonstrated by | Tests to write | Tier | Framework | Setup | Focused command | Broader command | Cwd |
|---|---|---|---|---|---|---|---|---|
| AC1 | Markdown becomes elements; user text stays literal | Component (`message-response.test.tsx` and via `ChatWidget`): `**b**` gives `<strong>`; `1.`/`2.` give `<ol>` with 2 `<li>`; `-` gives `<ul>`; backticks give `<code>`; a fence gives `<pre><code>`; the dialog's `textContent` has no `**` and keeps `[1]`; a user `**hi**` stays literal. e2e (desktop): `markdown` keyword gives `strong`, `ol li`, `pre` inside the dialog | unit (component), e2e | Vitest + Testing Library; Playwright | `ResizeObserver` stub; `markdown` stub keyword | `npx vitest run features/chat/components` | `npm test && npm run test:e2e` | apps/web |
| AC2 | Unsafe markup is inert | Component, table-driven on `MessageResponse`: `<script>`, `<img onerror>` and `![t](https://…)` give no `script`/`img` element; `javascript:`, `data:`, `vbscript:`, `mailto:`, `/relative` and `#x` links give no `href`; `https://` and `http://` links get `href`, `target="_blank"`, `rel="noopener noreferrer"`. e2e: `unsafe` keyword, `page.on('dialog')` fails the test, no `script`/`img` in the dialog, every `a[href]` in it matches `^https?:` | unit (component), e2e | Vitest + Testing Library; Playwright | `unsafe` stub keyword | `npx vitest run features/chat/components/message-response.test.tsx` | `npm test && npm run test:e2e` | apps/web |
| AC3 | The latest message comes into view; the reader is not yanked; Jump to latest | e2e at phone and desktop: three `tall` turns, after each the last user message and then the answer have bounding boxes inside the scroll element's box. Then a `slow` turn: wheel up while pending, then after the answer `scrollTop` is unchanged (within 2 px) and "Jump to latest" is visible; press it, then `scrollTop + clientHeight >= scrollHeight - 2` and the button is gone. Component: no "Jump to latest" in an empty conversation (jsdom cannot test scroll; that is the e2e part) | e2e, unit (component) | Playwright; Vitest | `tall`, `slow` stub keywords | `npx playwright test e2e/chat.e2e.ts e2e/layout.e2e.ts -g "latest"` | `npm run test:e2e` | apps/web |
| AC4 | The phone sheet stays on screen with no horizontal overflow | `e2e/layout.e2e.ts` (375 by 667): open, check the dialog box has `x >= 0`, `x + width <= 375`, `y >= 0`, `y + height <= 667`, and header and textbox both visible; `longurl` answer with Sources expanded, then the same box check plus `document.documentElement.scrollWidth <= clientWidth`; the long link's box width is at most the dialog's. Red first: the box check fails on today's CSS (confirms Decision 6's cause) | e2e | Playwright | `longurl` stub keyword | `npx playwright test e2e/layout.e2e.ts` | `npm run test:e2e` | apps/web |
| AC5 | Desktop size, header, Close, 44 px targets, accent Send | e2e (1280 by 800): dialog width 448 to 480 px and height at most 640 px; header text contains "AI RADAR"; the button named "Close chat" inside the dialog closes it and the launcher is focused; launcher, Send and Close boxes are at least 44 by 44; Send's computed `background-color` equals a `var(--link)` probe in light and dark. Component: the header Close closes and focus returns to the launcher. Manual (human, at plan or audit review): the panel looks distinct from a feed card | e2e, unit (component), manual | Playwright; Vitest | none | `npx playwright test e2e/chat.e2e.ts -g "desktop"` | `npm test && npm run test:e2e` | apps/web |
| AC6 | Sources collapse and expand | Component: an answer with 2 sources shows a "Sources (2)" button with `aria-expanded="false"` and no source links; clicking sets `"true"` and shows 2 links with `[n]`, title, source name, `href`, `target` and `rel`; empty `sources` shows no control. e2e: expand, then 3 links (migrated test) | unit (component), e2e | Vitest + Testing Library; Playwright | none | `npx vitest run features/chat/components` | `npm test && npm run test:e2e` | apps/web |
| AC7 | Loader with status semantics and reduced motion | Component: while pending, `getByRole("status")` has accessible text /thinking/i and the text "Thinking..." is absent; it is gone after the answer and after an error. e2e: `slow` turn with `emulateMedia({ reducedMotion: 'reduce' })`, then each dot has computed `animation-name: none`; without emulation the dots have a non-`none` animation name | unit (component), e2e | Vitest; Playwright | `slow` stub keyword | `npx playwright test e2e/chat.e2e.ts -g "loader"` | `npm test && npm run test:e2e` | apps/web |
| AC8 | Composer keeps its behavior | Component: Shift+Enter sends nothing (`fetch` not called); Enter sends; Send is disabled while pending; the textbox is named "Your question"; the existing blank and 1001-character tests pass unchanged | unit (component) | Vitest + Testing Library | none | `npx vitest run features/chat/components` | `npm test` | apps/web |
| AC9 | Suggested questions send through the normal path | Component: on open, the greeting and 3 suggestion buttons; clicking one calls `fetch` once with body `{question: <that text>, history: []}`, shows it as the user message, and hides the empty state (also while pending); the answer follows. e2e: click a suggestion, then the stub answer appears | unit (component), e2e | Vitest; Playwright | none | `npx vitest run features/chat/components` | `npm test && npm run test:e2e` | apps/web |
| AC10 | A long feed URL wraps on a phone; the copy is byte-verbatim | e2e (375 by 667): `/?tag=long-url`, then the `.urlLine` link's text equals the full URL, its box height is more than twice its line height (wrapped), the card's right edge is at most 375, and `scrollWidth <= clientWidth`. Red first on today's CSS. Command: `cmp specs/web-chat-ui-polish/design/feed.module.css features/feed/components/feed.module.css` exits 0, and `diff specs/archived/web-feed-ui/claude-design-outputs/feed.module.css specs/web-chat-ui-polish/design/feed.module.css` shows exactly the one `.urlLine` change | e2e, command | Playwright; shell | `long-url` stub tag | `npx playwright test e2e/layout.e2e.ts -g "feed"` | `npm run test:e2e` | apps/web |
| AC11 | Chat behavior is unchanged | The existing `chat-widget.test.tsx` cases (history, limits, six error codes, retry, focus, Escape, console) pass after only the selector migration; `features/chat/lib/*.test.ts`, `api/*.test.ts` and `conventions.test.ts` pass untouched; `git diff --stat -- features/chat/lib features/chat/api features/chat/index.ts app/api app/page.tsx` is empty; the existing `e2e/chat.e2e.ts` scenarios (one same-origin POST, 429, 504, clean console) pass | unit, e2e, command | Vitest; Playwright | none | `npx vitest run features/chat` | `npm test && npm run test:e2e` | apps/web |
| AC12 | The feed is unchanged at desktop | `npx playwright test e2e/feed.e2e.ts` passes all 17 baseline scenarios without `--update-snapshots`; `git diff --stat -- e2e/__baseline__ e2e/fixtures e2e/feed.e2e.ts` is empty; `npx vitest run features/feed` passes untouched | e2e, unit, command | Playwright; Vitest | none | `npx playwright test e2e/feed.e2e.ts` | `npm test && npm run test:e2e` | apps/web |
| AC13 | Tokens only; OS theme; no new token; WEB-9 copy | `chat-css.test.ts` passes (widened only under Decision 9, with its new fires-on-violation case); the existing theme e2e passes in light and dark; `git diff --stat -- app/globals.css` is empty; the AC10 `cmp` and `diff` commands; no `data-theme` in chat CSS | unit, e2e, command | Vitest; Playwright | none | `npx vitest run features/chat/components/chat-css.test.ts` | `npm run lint && npm run typecheck && npm test && npm run build && npm run test:e2e` | apps/web |

Dependency and docs checks for the audit, which serve the binding constraints:
- `package.json` lists `react-markdown` and `use-stick-to-bottom` with exact versions, and no other
  new entry (`git diff package.json`).
- `npm ls react-markdown use-stick-to-bottom` resolves.
- `AGENTS.md` names both packages.

## Revision log
- Revision 1 (2026-10-24): initial plan against intent revision 2, which carries the human's answers.
  The library APIs were checked with Context7 and `npm view` on the same day. ADRs 0036 to 0039 are
  proposed. The suggested-question copy is in Decision 12 for the human to review.

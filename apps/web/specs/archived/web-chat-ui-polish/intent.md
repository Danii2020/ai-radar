# Intent: Web Chat UI Polish

Revision: 2
Approval: Approved
Shipped: 2026-10-24

## Outcome
The chat widget becomes usable on a phone and pleasant on a desktop. Assistant answers render
their markdown (bold, lists, code) instead of raw `**` and `1.` text, the conversation follows the
latest message without manual scrolling, and the panel is bigger, visibly branded and distinct
from the feed's look. On a phone it opens as a full-width bottom sheet that never leaves the
screen. A long URL no longer pushes a feed card or the chat past the right edge of a phone screen.
The conversation logic, the `/api/chat` route and the backend contract are unchanged.

## Acceptance criteria
- **AC1** Assistant answers render as markdown. `**bold**` becomes bold text, a numbered list
  becomes an ordered list, a bulleted list becomes an unordered list, `` `code` `` becomes inline
  code, and a fenced block becomes a code block that scrolls sideways inside the message rather
  than widening it. Citation markers such as `[1]` and `[3]` stay visible as plain text. A
  well-formed answer leaves no literal `**` in the page. User messages stay plain text, shown
  exactly as typed.
  Example: answer `"**Agents** matter:\n\n1. LangGraph [1]\n2. CrewAI [2]"` -> a `<strong>Agents</strong>`
  and an `<ol>` with two items, each ending in its literal `[n]`; the user's `**hi**` -> shown as `**hi**`.
- **AC2** Markdown rendering is safe. Raw HTML in an answer never becomes an element, and nothing
  in an answer runs. A link gets an `href` only for `http:` and `https:` URLs, and it opens in a new
  tab with `rel="noopener noreferrer"`. Any other scheme (`javascript:`, `data:`, `vbscript:` and so
  on) leaves no clickable `href`. Markdown images are not rendered as images, so an answer can
  make the browser fetch nothing.
  Example: answer `"<script>alert(1)</script> [x](javascript:alert(1)) <img src=x onerror=alert(1)> ![t](https://e.x/p.png)"`
  -> no `<script>` or `<img>` element, no `javascript:` href anywhere, no dialog or script run.
- **AC3** The message area keeps the latest message in view. Sending a question, on any turn
  including the second and later, brings the question, then the loading indicator, then the answer
  into view without the user scrolling. If the user has scrolled up while a turn is pending, the
  answer arriving does not move their scroll position. Whenever the view is not at the bottom, a
  "Jump to latest" button is shown. Pressing it scrolls to the newest message, and the button then
  goes away. This holds at a 375 by 667 phone viewport and at a 1280 by 800 desktop viewport.
  Example: third question sent -> it is visible inside the message area; scroll up, wait for the
  answer -> scroll position unchanged and "Jump to latest" shown; press it -> the answer is visible.
- **AC4** On a phone the panel is a full-width bottom sheet that stays on screen. At a 375 by 667
  viewport, the open panel's box lies entirely inside the viewport (left edge at or right of 0, right
  edge at or left of the viewport width), its height fits the dynamic viewport height so the header
  and the composer are both visible, and the page has no horizontal overflow
  (`document.documentElement.scrollWidth <= clientWidth`). This holds with a very long unbroken URL
  in an answer's markdown link, in a source link, and in a code block.
  Example: 375 by 667, open chat, ask for the stub's long-URL answer and expand its sources -> panel
  box within 0..375 px, `scrollWidth <= clientWidth`, the URL text wraps onto several lines.
- **AC5** On a desktop the panel is bigger and has its own look. At a 1280 by 800 viewport the panel
  is about 28 to 30 rem wide and up to 40 rem tall (never taller than the viewport). It has a branded
  header naming AI Radar and a Close icon button in that header (accessible name "Close chat"),
  which closes the panel and returns focus to the launcher. The launcher, the Send control and the
  header Close control each have a hit area of at least 44 by 44 CSS pixels. Send is an icon button
  with the accessible name "Send", styled with an accent colour. The look is distinct from the feed
  cards (for example, the panel is not just a feed card with a list in it).
  Example: 1280 by 800, open chat -> panel width 448 to 480 px, header with the AI Radar name and an
  X button; click X -> panel closed, focus on the launcher.
- **AC6** Sources are a collapsible list. An answer with sources shows a "Sources (n)" control,
  collapsed by default, that reports its state with `aria-expanded`. Expanding it shows each source
  as a numbered link (`[n]`, title, source name) that opens its `url` in a new tab with
  `rel="noopener noreferrer"`. Long titles and URLs wrap inside the panel. An answer with an empty
  `sources` list shows no control.
  Example: answer with 3 sources -> "Sources (3)" collapsed; click it -> 3 links to the 3 URLs.
- **AC7** The loading state is an animated dots indicator in place of the "Thinking..." text. It keeps
  `role="status"` and has accessible text, so screen readers still announce it. With
  `prefers-reduced-motion: reduce` it does not animate. It goes away when the answer or an error
  arrives.
  Example: question sent -> a status element with three dots and accessible text such as "Thinking";
  with reduced motion emulated -> no running animation on the dots.
- **AC8** The composer is bigger and keeps its behavior. The textarea keeps the accessible name
  "Your question". Enter sends, Shift+Enter inserts a newline, Send is disabled while a turn is
  pending, and the blank and over-long (1001-character) question messages from `web-chat-ui` AC4
  still block the request.
  Example: type "a", press Shift+Enter, type "b" -> the textarea holds "a\nb" and nothing is sent.
- **AC9** An empty conversation shows a greeting and three suggested questions. Pressing a
  suggestion sends it exactly as if the user had typed it and pressed Send: the same validation,
  the same single request with the same history, and the same pending, answer and error states.
  The empty state is gone once the first question is sent.
  Example: open chat -> greeting plus 3 suggestions; press one -> it appears as the user's message
  and the stub's answer follows.
- **AC10** A long URL on a feed card wraps inside the card. At a 375 by 667 viewport, a card whose
  `url` is a 300-character URL with no break points shows the whole URL wrapped within the card,
  and the page has no horizontal overflow. At desktop width the feed looks exactly as before.
  Example: `/?tag=<long-url scenario>` at 375 px -> the URL line wraps, `scrollWidth <= clientWidth`.
- **AC11** (compatibility) The chat behaves exactly as before apart from the changes above. The
  conversation reducer, `sendTurn`, the caps, the history rules, the six error states with their copy
  and Retry, one same-origin request per turn, and the `/api/chat` route are unchanged. The panel is
  still a labelled `role="dialog"`. The launcher still toggles it, carries `aria-expanded` and has an
  accessible name that reflects open or closed. Opening moves focus to the input, Escape closes, and
  closing returns focus to the launcher. `features/chat/index.ts` still exports exactly `ChatWidget`
  and `handleChatRequest`. The widget writes nothing to the browser console, and no credential or
  backend URL reaches the browser.
- **AC12** (compatibility) The feed is unchanged at desktop width. The four render states, tag filter,
  cursor pagination and the server-side fetch rules (WEB-1 to WEB-8) hold, and the 17 committed e2e
  baseline scenarios in `e2e/__baseline__/` pass byte-identical and are never regenerated.
- **AC13** (compatibility) Styling stays on the design tokens. `chat.module.css` has no hand-authored
  colour, spacing or radius value, the chat follows the OS light and dark preference with no toggle
  (WEB-8), and no new design token is introduced by this feature. The `feed.module.css` change is
  made in a design deliverable first and copied byte-verbatim into the app (WEB-9).

## Scope
**In**
- New presentational components under `features/chat/components/`, shaped and named after Vercel AI
  Elements but written as plain React with CSS Modules: `Conversation`, `ConversationContent`,
  `ConversationScrollButton`, a conversation empty state, `Message` (`from="user" | "assistant"`),
  `MessageContent`, `MessageResponse`, `Sources`/`Source` (replacing `source-list.tsx`), a loader,
  and `PromptInput`, `PromptInputTextarea`, `PromptInputSubmit`.
- `chat-widget.tsx`, `chat-panel.tsx` and `message-list.tsx` updated to compose those components.
  They stay the stateful shell; only markup and wiring change.
- `chat.module.css` restyled: size, bottom sheet under a phone breakpoint, branded header, accent
  Send, larger controls, wrapping for long links and code.
- The `.urlLine` wrapping fix for feed cards, through a revised design deliverable.
- Two new runtime dependencies, pinned exactly: `react-markdown` (markdown) and `use-stick-to-bottom`
  (stick-to-bottom scrolling).
- Test updates: the chat component tests, `e2e/chat.e2e.ts`, new e2e checks at phone and desktop
  viewports, new stub answers (markdown, long URL, unsafe markup, a slow answer) and a feed stub
  scenario with a long-URL card that no baseline scenario uses.
- Docs: `AGENTS.md` (the dependency rule and the chat component list) and the `apps/web` README.

**Out**
- Any backend change (infra, Lambda, agent, contract). A contract change goes to the root harness.
- Changes to the conversation reducer, `sendTurn`, the caps, `history.ts`, the `features/chat/api/`
  code, the `/api/chat` route or the barrel's exports.
- shadcn/ui, Tailwind, Vercel AI Elements and the AI SDK (`ai`, `@ai-sdk/react`, `streamdown`, Radix).
  The human decided this before drafting and it is not reopened here.
- Streaming, persisted conversations, a `/chat` page, a theme toggle and a per-IP rate limit.
- GitHub-flavoured markdown (tables, strikethrough, task lists, bare-URL autolinks). See Open
  questions.
- The open `web-chat-ui` audit findings F1 to F10, unless a change here touches the same line.
- Vercel deploy. It stays a human-run step (WEB-11).

## Constraints
- Stack: Next.js 16 App Router, React 19, TypeScript strict, CSS Modules, npm only (WEB-10). The
  Stop hook runs eslint and tsc. The gates are `npm run lint`, `npm run typecheck`, `npm test`,
  `npm run build` and `npm run test:e2e`, all run in `apps/web/`.
- Dependencies. `AGENTS.md` today sanctions only `@playwright/test` and `aws4fetch` beyond the base
  toolchain. This feature amends that rule, through an ADR, to add `react-markdown` and
  `use-stick-to-bottom`, both pinned to an exact version (at drafting time `react-markdown` 10.1.0,
  peer `react >=18`, and `use-stick-to-bottom` 1.1.6, peer `react ^19.0.0` among others, zero
  dependencies). No other direct dependency is added.
- WEB-1 and the chat guards still hold: no `"use client"` module imports the chat barrel or
  `features/chat/api/` except with `import type`, and there is no `NEXT_PUBLIC_` variable.
- WEB-9. `features/feed/components/feed.module.css` is byte-identical to the design deliverable at
  `specs/archived/web-feed-ui/claude-design-outputs/feed.module.css`, and `.urlLine` sits in that
  copied file, not in an app-owned part. So the fix is a new revision of the deliverable, which is
  then copied over the app file byte-verbatim. The archived copy is part of an archive record and
  is never edited. The new revision is kept with this feature's specs. The execution plan names the
  path, and an ADR moves WEB-9's "deliverable" pointer to the latest revision. The change is one
  wrapping declaration, not a colour, spacing or radius value.
- The feed baselines record each `.urlLine` element's class list and a fixed set of computed styles
  that does not include the wrapping properties. The fix keeps the class name and adds no element,
  so the baselines stay byte-identical. The long-URL card is served only by a new stub scenario.
- Chat styling uses only existing tokens from `app/globals.css`. Size, position, `z-index`, hit-area
  height and the phone breakpoint are layout values with no token, as `web-chat-ui` already allows.
  No new token is added: the panel keeps `--radius-md`, and the accent Send uses `var(--link)` with
  a `var(--surface-card)` icon (about 7.9:1 contrast in light mode and 9:1 in dark).
- This spec changes `web-chat-ui` on purpose. That spec is audit-approved but not yet archived:
  - AC2 (sources shown as numbered links) now puts the links behind a collapsed "Sources (n)"
    control, and replaces the "Thinking..." text with the dots indicator.
  - AC1 (the button toggles the panel) gains a Close button in the header.
  - AC8 and its CSS check: `chat-css.test.ts` may be deliberately widened to accept
    `env(safe-area-inset-*)` inside a spacing value, which is a device inset and not a design
    value. The plan decides this and states why.
- The e2e tier stays offline: the chat route is backed by the local stub, with fake credentials and
  no call to AWS. Overflow, scrolling and reduced-motion checks run in Playwright, because jsdom has
  no layout engine.
- `apps/web/.claude/memory/web-chat-ui-handoff.md` belongs to `web-chat-ui`'s close-out, not to this
  feature, and is not touched here.

## Open questions
- None. The seven questions of revision 1 were answered by the human (relayed by the coordinator on
  2026-10-24):
  - Order: build on the same branch, `feat/web-chat-ui`, on top of the uncommitted `web-chat-ui`
    work, with no merge or archive first. ADRs are numbered 0036 to 0039.
  - Feed deliverable: the executor authors the revision (the archived file plus
    `overflow-wrap: anywhere` on `.urlLine`) under `specs/web-chat-ui-polish/` and copies it
    byte-verbatim into `features/feed/components/feed.module.css`.
  - Radius: no new token. The panel keeps `--radius-md`; the launcher, Send and the composer use
    `--radius-full`.
  - Send accent: a `var(--link)` background with a `var(--surface-card)` icon.
  - `remark-gfm`: not added. A model-written table shows as plain text.
  - Sources: collapsed by default.
  - Suggested questions: AC9 is kept. The three questions are written in the execution plan, and the
    human reviews the wording there.

## Revision history
- Revision 2 (2026-10-24): the open questions were resolved with the human's answers, as listed under
  Open questions, and the token constraint was updated to match. No acceptance criterion changed.
  The coordinator relayed the human's approval of revision 1. This file's `Approval` line is the
  human's to stamp, so it stays `Pending` until they do.
- Revision 1 (2026-10-24): initial draft from the human's manual test of the deployed chat widget
  (raw markdown, clipped panel on a phone, no auto-scroll, small controls, feed URL overflow) and the
  approved approach: AI-Elements-shaped local components, `react-markdown`, `use-stick-to-bottom`,
  and no shadcn/ui or AI Elements.

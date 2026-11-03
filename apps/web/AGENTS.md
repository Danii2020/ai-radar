# AGENTS.md

Guidance for AI coding agents working in `apps/web/`. Launch `claude` from this
directory so this file, `.claude/`, and the TypeScript harny harness load.

## Purpose

**ai-radar-web** is the AI Radar web feed: a Next.js (App Router, React 19)
frontend that renders the curated AI-news cards served by the backend `feed-api`
(`GET /v1/cards`). It is Phase 2 of the AI Radar project; the Python backend and
its own harness live at the repo root. Runbook (local dev, Vercel deploy, CORS
follow-up) is in the repo root [`docs/runbooks.md`](../../docs/runbooks.md#web-app-on-vercel); current-state
specs are in [`specs/current/_index.md`](specs/current/_index.md).

## Components

```
app/                    # Next.js App Router: layout.tsx, page.tsx (thin Server Component shell), globals.css
features/feed/          # The feed feature (all non-routing code), split by role
  index.ts              # the ONLY public entry point: FeedView, loadFeedState, parseFeedSearchParams
  conventions.test.ts   # architecture guards (WEB-1/3, deep-import, barrel and "use client" rules)
  api/                  # server-side data access
    client.ts           # server-only fetchFeed() against feed-api; FeedApiError
    load-feed.ts        # loadFeed(): bounded cursor drain (MAX_DRAIN_REQUESTS)
    load-feed-state.ts  # loadFeedState(): never throws; maps errors to FeedViewState + feed_fetch_failed log
    types.generated.ts  # GENERATED from the backend schema — never hand-edit
  components/           # presentation; may only `import type` from api/
    feed-view.tsx       # FeedView: exactly one of four render states
    card-item.tsx, tag-filter.tsx, pagination.tsx
    feed.module.css     # CSS Modules; design tokens copied byte-verbatim
  lib/                  # pure helpers: href.ts, tags.ts, search-params.ts (parseFeedSearchParams)
features/chat/          # The chat feature (floating widget + server route logic), split by role
  index.ts              # the ONLY public entry point: ChatWidget, handleChatRequest
  conventions.test.ts   # architecture guards (barrel, deep-import, "use client" and credential-env rules)
  api/                  # server-only: types.ts, backend.ts (SigV4 via aws4fetch, one fetch), handle-chat-request.ts
  components/           # "use client": chat-widget (state shell), chat-panel (header, composition), AI-Elements-shaped
                        #   parts: conversation, conversation-empty-state, message, message-response (markdown),
                        #   sources, loader, prompt-input; chat.module.css (tokens only)
  lib/                  # pure: limits, history, conversation reducer, send-turn (browser fetch to /api/chat)
app/api/chat/route.ts   # thin Node.js route: POST -> handleChatRequest
scripts/generate-api-types.mjs   # regenerates api/types.generated.ts
e2e/                    # Playwright tier: feed.e2e.ts, stub/ (node:http feed-api stub), __baseline__/ (do not edit)
playwright.config.ts    # Playwright config (collects *.e2e.ts only)
specs/                  # SDD specs (current/ and archived/) for this root
.sdd/, .claude/         # harny harness (stack: typescript)
```

Code outside `features/feed/` imports only from `@/features/feed` (the barrel), and code outside
`features/chat/` only from `@/features/chat`; `app/page.tsx` imports both barrels;
tests sit next to their source.

Config (all server-only; see `.env.example`): `FEED_API_BASE_URL`, and for chat `CHAT_API_BASE_URL`,
`CHAT_API_ACCESS_KEY_ID`, `CHAT_API_SECRET_ACCESS_KEY`. The chat variables are read per request, only
inside `features/chat/api/`; never `NEXT_PUBLIC_`, never logged or returned.

## Validation

Run from `apps/web/`:

```bash
npm run lint         # eslint
npm run typecheck    # tsc --noEmit
npm test             # vitest run
npm run build        # next build
npm run test:e2e     # Playwright against a local feed-api stub (offline; needs `npx playwright install chromium` once)
```

The per-turn Stop hook runs eslint + tsc; CI runs `harny-feedback-apps-web.yml`.
Package manager is **npm** (no workspaces, no pnpm/yarn). Beyond the base
toolchain the only sanctioned extra dependencies are `@playwright/test` (dev, e2e tier only),
`aws4fetch` (runtime, pinned exactly; SigV4 signing for the chat route via `AwsClient.sign()`, never `AwsClient.fetch()`),
`react-markdown` (runtime, pinned exactly; renders assistant answers only, through the safe subset in
`message-response.tsx`; never with a raw-HTML plugin) and `use-stick-to-bottom` (runtime, pinned exactly; the
conversation scroll only). A further dependency needs its own ADR.

## Coding standards

- **WEB-1 — server-side fetching only.** All `feed-api` requests happen in
  Server Components / server modules. No `NEXT_PUBLIC_` env vars, no
  `execute-api` host literals (`execute-api.<region>.amazonaws.com`; the bare SigV4
  service name `execute-api` is allowed in `features/chat/api/`), and no `"use client"`
  module may import `client.ts` or `load-feed.ts` (enforced by
  `features/feed/conventions.test.ts`). The chat slice extends the same rule to its
  `api/` folder and barrel (`features/chat/conventions.test.ts`).
- **WEB-2 — generated types.** `types.generated.ts` comes from
  `npm run generate:types`; never hand-author or edit it.
- **WEB-3 — API order is authoritative.** No `.sort(` / `.reverse(` under
  `features/`. Pagination cursors are opaque and URL-addressable.
- **WEB-4 — bounded drain.** Empty-but-cursored pages are followed at most
  `MAX_DRAIN_REQUESTS` times.
- **WEB-5 — one render state per request:** ok / empty / error / filtered-empty,
  via `FeedView`.
- **Barrel-only imports.** `features/feed/index.ts` exports exactly
  `FeedView`, `loadFeedState`, `parseFeedSearchParams`, and `features/chat/index.ts` exactly
  `ChatWidget` and `handleChatRequest`; no deep imports from
  outside the feature, no barrel self-imports, and `components/`/`lib/` use
  `import type` only for `api/` (enforced by `conventions.test.ts`).
- **WEB-9 — design tokens and component CSS are copied byte-verbatim**; change a
  design value at its latest deliverable revision (a revised copy kept under the feature's
  `specs/<feature>/design/`, never an edit to the archived one), then copy it over the app file.
- Style: match surrounding code (TypeScript strict, CSS Modules, small modules
  colocated with a `*.test.ts(x)` file). Errors logged server-side as one-line
  structured JSON; messages never reach the browser.
- Tests: follow the `high-value-tests` skill — no tautologies, no
  framework tests, no source-grep tests beyond the existing conventions guard.
- Deployment (Vercel) is a human-run step; agents stop at local verification.

## SDD harness

Specs live in `specs/`; ADR numbers are monotonic across both harness roots
(see the repo root `CLAUDE.md`). When you change a shared role or skill or
`.sdd/feedback/run-feedback.mjs` here, make the same change in the repo root.

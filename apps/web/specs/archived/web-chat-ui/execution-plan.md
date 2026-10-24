# Execution Plan: Web Chat UI

## Guidance consulted
- `apps/web/CLAUDE.md`, `AGENTS.md` and `.claude/memory/web-chat-ui-handoff.md` (the brief).
- `harny-sync` lookup: `apps/web/specs/current/web-feed.md` (WEB-1 to WEB-11, invariants 1 to 4),
  repo-root `specs/current/chat-api.md` (CAPI-1 to CAPI-8), `chat-api-auth.md` (CAAUTH-1 to
  CAAUTH-9), and both `_index.md` files (next free ADR number is **0032**, shared by both roots).
- Backend contract in code: `src/chat/request.py` (history rules and rule names), `src/chat/config.py`
  (default caps), `src/chat/graph.py` (`build_sources`: the `sources` item fields).
- Frontend patterns: `features/feed/` (layout, barrel, `api/client.ts`, `conventions.test.ts`),
  `app/page.tsx`, `app/layout.tsx`, `app/globals.css` (tokens), `e2e/` (`feed.e2e.ts`,
  `stub/feed-api-stub.mjs`, `stub/launch-apps.mjs`), `playwright.config.ts`, `vitest.config.mts`.
- Context7 (`/mhart/aws4fetch`, v1.0.20; `/smithy-lang/smithy-typescript`) for the signing library.

## Ownership
- New: `apps/web/features/chat/` (layout below), `apps/web/app/api/chat/route.ts`,
  `apps/web/e2e/chat.e2e.ts`, `apps/web/specs/web-chat-ui/`.
- Changed: `app/page.tsx` (mounts the widget), `e2e/stub/feed-api-stub.mjs` and
  `e2e/stub/launch-apps.mjs` (a chat stub and its env), `features/feed/conventions.test.ts` (one
  guard narrowed, see Decision 6), `.env.example`, `package.json` and `package-lock.json`, `AGENTS.md`
  and `README.md` (layout, env, the new dependency).
- Not touched: anything outside `apps/web/`, `features/feed/` source, `e2e/__baseline__/`.
- Affected `specs/current` capabilities: `web-feed` (invariant 3 amended; WEB-R-series untouched), and
  a new capability `web-chat` created at archive time. The root `chat-api`, `chat-api-auth` and
  `chat-agent` are consumed, not changed.

```
features/chat/
  index.ts                    # public entry: ChatWidget, handleChatRequest (nothing else)
  conventions.test.ts         # architecture guards for this feature
  api/                        # server-only
    types.ts                  # ChatTurn, ChatSource, ChatResponse and the error codes
    backend.ts                # callChatBackend(): sign (aws4fetch) + one fetch, status mapping
    handle-chat-request.ts    # the route's logic: parse, validate, trim, call, map, log
  components/                 # "use client"; may only `import type` from api/
    chat-widget.tsx           # floating button + panel (open state, focus, Escape)
    chat-panel.tsx, message-list.tsx, source-list.tsx
    chat.module.css           # tokens only
  lib/                        # pure, importable from client and server
    conversation.ts           # reducer: messages, pending, error, retry
    limits.ts                 # QUESTION_MAX_CHARS, HISTORY_MAX_ITEMS, ITEM_MAX_CHARS
    history.ts                # trimHistory() and the shape check
    send-turn.ts              # browser fetch to /api/chat, client deadline, code mapping
app/api/chat/route.ts         # thin: runtime 'nodejs', POST -> handleChatRequest
```

## Binding constraints
- The browser calls only the same-origin route. No `NEXT_PUBLIC_` variable, no `execute-api` host in
  browser code, and no `"use client"` module imports the barrel or anything under `features/chat/api/`
  (WEB-1 and ADR 0002 extended; source: `chat-api-auth` CAAUTH-4, ADR 0029).
- Route runs on the Node.js runtime. It signs with SigV4, service `execute-api`, region `us-east-1`,
  and calls only `POST {CHAT_API_BASE_URL}/v1/chat` (source: CAAUTH-1, CAAUTH-2).
- Env names are `CHAT_API_BASE_URL`, `CHAT_API_ACCESS_KEY_ID`, `CHAT_API_SECRET_ACCESS_KEY`. Not the
  `AWS_*` names, which Vercel reserves. Values are read per request, never at import time, never
  logged, never returned (source: handoff; CAAUTH-6).
- Exactly **one** backend call per user turn: no retry at any layer. A retried POST would run the
  agent twice (source: `chat-api` CAPI-3, ADR 0024).
- Backend contract is frozen from this side: request `{question, history: [{role, text}]}`; response
  `{answer, sources: [{n, title, url, source, published, score}]}`; errors per CAPI-2/CAPI-3. The
  response is shape-checked at the boundary and a mismatch is an upstream failure, not a render
  crash (source: `chat-api` CAPI-1; house rule from `isCardOut`).
- Caps mirror the backend defaults: question 1000, 10 turns (20 items), 4000 per item, body 512 KiB
  (524,288 bytes). The backend stays authoritative (source: `src/chat/config.py`, CAPI-2).
- Errors reaching the browser are one of a fixed set of codes with generic copy. Logs are one-line
  JSON and hold no question, history, answer, credential or URL (source: WEB-5, CAPI-7, CAAUTH-7).
- Styling: CSS Modules using only existing custom properties from `app/globals.css` for colour,
  spacing and radius. `globals.css` and `feed.module.css` are not edited (WEB-8, WEB-9, ADR 0005).
- `e2e/__baseline__/` is never regenerated and the existing 17 baseline scenarios must pass unchanged
  (source: `feed.e2e.ts` header; intent AC7).
- No `.sort(` / `.reverse(` anywhere under `features/` (WEB-3, conventions test T31). No Vercel
  command, no `cdk`, no `aws` command (WEB-11, ADR 0007).
- Agents never read, print or write the real key. Tests use obviously fake key values.

## Proposed approach
Revisable by the executor if it records why.

1. **Signing library: `aws4fetch` (exact version pin, v1.0.20 at the time of writing), using
   `AwsClient.sign()` and our own `fetch`.** Rationale: zero dependencies, 6 KB, runs on Node's
   built-in Web Crypto, and `sign()` returns a plain `Request` so the single-call, abort-signal and
   no-retry rules stay in our code. Rejected: `@smithy/signature-v4` plus `@aws-crypto/sha256-js` (the
   handoff's suggestion). Its own README says it is internal to generated SDK clients and not meant for
   standalone use, it needs two packages, and it needs a hand-built `HttpRequest` and a conversion back
   to `fetch`. Rejected: `AwsClient.fetch()`: it retries by default (Context7: `retries` defaults to
   10 with backoff), which would re-run the agent. Construct with `retries: 0` anyway, as a second
   guard. The executor re-checks the pinned version is at least two weeks old with `npm view`.
2. **Chat is a feature slice, not part of `features/feed/`.** Same role split and one barrel as the
   feed (ADR 0008), but a second slice, so chat code never imports feed internals. The barrel exports
   `ChatWidget` and `handleChatRequest`. `ChatWidget` is a client component, so the page imports it
   from the barrel server-side, exactly as it imports `FeedView`.
3. **Mount: `app/page.tsx` renders `<FeedView …/>` and `<ChatWidget />` as siblings in a fragment.**
   The widget is outside the `feedPage` element, which is what keeps the baseline captures unchanged.
   This is the amendment of `web-feed` invariant 3: the page now imports two barrels and is a few
   lines longer, with no `try`/`catch`, no `console`, no logic.
4. **Route: `app/api/chat/route.ts` exports `runtime = 'nodejs'`, `dynamic = 'force-dynamic'` and
   `maxDuration`, plus `POST`.** It only delegates to `handleChatRequest(request: Request):
   Promise<Response>`, so the logic is unit-testable without a Next server.
5. **`handleChatRequest` order: size check -> parse JSON -> validate and trim -> read env -> call backend
   -> map -> log.** Local failures never reach the backend. Mapping to the browser:

   | Cause | Status | `error` code |
   |---|---|---|
   | body missing, over 524,288 bytes, not JSON, bad shape, blank or over-long question | 400 | `invalid_request` |
   | backend 400 | 400 | `invalid_request` |
   | backend 429 | 429 | `busy` |
   | backend 504, or no reply within the route's deadline | 504 | `timeout` |
   | backend 502, an unreadable or mis-shaped 200, a network error | 502 | `upstream_failure` |
   | backend 403, backend 5xx other than 502/504, missing or blank env | 503 | `unavailable` |
   | anything unexpected | 500 | `internal_error` |

   `detail` is never forwarded and never echoes input. Success is 200 with exactly `answer` and
   `sources`. The internal outcome (for example `backend_forbidden` versus `missing_config`) goes to
   the log only, so a 403 from a rotated key is findable without telling the visitor.
6. **History rules in the route.** The client sends completed turns only. The route requires an array
   of `{role, text}` with alternating roles starting with `user` and, if non-empty, an even length
   ending in `assistant`; anything else is `invalid_request` (the client never produces it, so it is
   a bug or a probe). It then keeps the last 20 items (an even count, so the list still starts with
   `user`), and cuts any `text` over 4000 characters. The client never trims: one place owns the cap.
7. **Deadline.** The route aborts its backend call after 30 s (above the backend's 22 s read timeout
   and 28 s Lambda limit, so the backend's own 504 normally wins). The browser aborts after 35 s and
   shows the `timeout` state. `maxDuration` is set above 30 s so the platform does not cut the route
   first; whether the Vercel plan allows it is a human deploy check (reservation WEBCHAT-R3).
8. **Client state is a reducer in `lib/conversation.ts`.** Messages, `pending`, and `error`. A failed
   turn keeps the question in the input and adds no message pair to `history`, so retry resends the
   same question with the same history. The widget keeps state in memory only (no storage, no
   cookie): a page reload starts a new conversation.
9. **Accessibility.** A plain `div` with `role="dialog"` and `aria-label`, not native `<dialog>`
   (jsdom lacks `showModal`). Non-modal: the feed behind it stays usable. Focus moves to the input on
   open and back to the button on close. Escape closes. The button uses `aria-expanded` and
   `aria-controls`. The message list is `aria-live="polite"`.
10. **Styling.** `chat.module.css` uses `var(--surface-*)`, `var(--ink*)`, `var(--border-*)`,
    `var(--space-*)`, `var(--radius-*)`, `var(--shadow-*)`, `var(--focus-ring)` and the font tokens.
    Position, size and `z-index` are layout values with no token; they are literals in the module and
    not colour, spacing or radius. Dark mode follows `prefers-color-scheme` through the tokens, with no
    toggle and no `data-theme`.
11. **Guard change: narrow T29's `execute-api` pattern.** `conventions.test.ts` T29 forbids the literal
    `execute-api` anywhere under `features/**` and `app/**`, but SigV4 needs `service: 'execute-api'`.
    The guard's purpose (WEB-R3, ADR 0002) is to keep a real API host out of code, so the pattern becomes
    the host form `execute-api\.[a-z0-9-]+\.amazonaws\.com`. The `NEXT_PUBLIC_` half is unchanged. A
    test shows the narrowed pattern still fires on a host literal. Rejected: building the string from
    parts (hides the literal from the guard rather than fixing the guard) and exempting the whole
    `features/chat/api/` folder (a blind spot that grows).
12. **e2e.** `launch-apps.mjs` adds `CHAT_API_BASE_URL` (the local stub) and two fake credential values
    to both `next start` instances. The stub gains `POST /<scenario>/v1/chat`, which checks for a
    SigV4 `Authorization` header with scope `us-east-1/execute-api/aws4_request` and answers by
    question keyword (a normal answer with sources, 429, 504, 502, 403). The chat scenarios live in
    `e2e/chat.e2e.ts`. `feed.e2e.ts` and the baselines are not edited.
13. **Accepted reservations, recorded for the audit and the capability doc:**
    - WEBCHAT-R1: no per-visitor limit. The API's global throttle (5 req/s, burst 10) is shared, so one
      visitor can use up the quota for all. The `AiRadarBudget` alert is the cost backstop (human
      decision, 2026-10-22).
    - WEBCHAT-R2: not deployed and not exercised against the real API. The live check needs the human
      to put the key in `.env.local`; the Vercel project and its env are Phase 5 (WEB-11).
    - WEBCHAT-R3: the Vercel plan's function duration limit versus `maxDuration` is unchecked.

## Consumers and migration
- `features/feed/conventions.test.ts` T29: pattern narrowed (Decision 11). Its other guards are scoped
  to `features/feed` and need no change. `features/chat/conventions.test.ts` repeats the feed's
  deep-import, barrel-self-import, `"use client"` and `import type` guards for the chat slice.
- `app/page.tsx`: one added import and one sibling element. Feed e2e baselines unchanged (they capture
  the `feedPage` root, console and `feed_fetch_failed` stderr lines only).
- `AGENTS.md`: layout block, the "imports only from `@/features/feed`" line, the barrel rule, the
  dependency sentence (Playwright is no longer the only extra), and the env note.
- `.env.example`: three placeholders, no real value, no `NEXT_PUBLIC_`.
- `README.md` (apps/web) and the repo-root README "Phase 3": local setup for chat, the human step of
  reading the key from the profile, and the live check. Root-README edits go to the human, since this
  harness root is `apps/web/` (they are documentation for `harny-document`, not source).
- ADRs for `harny-adr`, numbering from 0032: signing library choice; route as the only chat caller with
  fixed error codes; T29 narrowing; no per-visitor limit in v1.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The key reaches the browser bundle or a log | Low | High | Env read only in `api/`; guard tests (no `"use client"` import of `api/`, no `NEXT_PUBLIC_`); a unit test greps the route's responses and log lines for the fake key and secret; `.env.local` is already git-ignored |
| A default retry runs the agent twice | Med (library default is 10) | Med | `sign()` plus our own single `fetch`, `retries: 0` too, and a test that the backend is called once on 429, 502 and a timeout |
| One visitor starves the shared throttle | Med | Med | Accepted (WEBCHAT-R1); the UI shows a "busy" state; `AiRadarBudget` alert |
| The widget changes a feed baseline or logs to the console | Low | Med | Mounted outside `feedPage`; the existing 17 baseline scenarios are the check; widget never calls `console` |
| Narrowing T29 hides a real host literal | Low | Med | The new pattern is the host form; a guard test proves it fires; reviewed in the audit |
| Slow answers (up to 22 s) feel like a hang | Med | Low | A visible pending state, a 35 s client deadline and a `timeout` state with retry |
| Long-lived key leaks or needs rotation | Low | High | Accepted (CAAUTH-KEY); runbook in root README; the route never echoes it |
| Pinned library is too new or abandoned | Low | Low | Exact pin, age check, and the call is isolated in `api/backend.ts` so a swap touches one file |

## Validation
One row per AC. Frameworks are the repo's: Vitest 4 with jsdom and Testing Library for unit and
component tests, Playwright for e2e. All commands run in `apps/web`.

| AC | Demonstrated by | Tests to write | Tier | Framework | Setup | Focused command | Broader command | Cwd |
|---|---|---|---|---|---|---|---|---|
| AC1 | The button toggles a labelled, closed-by-default dialog | Component: closed on first render; click opens and sets `aria-expanded`; Escape and a second click close; focus moves to the input then back to the button. e2e: button visible on `/`, no panel | unit (component), e2e | Vitest + Testing Library; Playwright | none | `npx vitest run features/chat/components` | `npm test` | apps/web |
| AC2 | A question yields a pending state, then the answer and numbered source links | Component: user message appears; pending indicator; answer rendered; each source is a link to its `url` with `[n]`, title and source name; empty `sources` renders no list. Unit: `send-turn` maps a 200 body. e2e: ask, see the stubbed answer and 3 source links | unit (component), e2e | Vitest + Testing Library; Playwright | e2e chat stub | `npx vitest run features/chat/components features/chat/lib` | `npm test && npm run test:e2e` | apps/web |
| AC3 | The route trims and normalizes history; a trimmed history is never rejected for a history rule | Unit on `history.ts` and `handleChatRequest`: 12 turns -> last 10 turns forwarded; over-long item cut to 4000; 20-item list unchanged; non-alternating, odd-length, last-is-`user`, bad role and non-array -> 400 with the backend not called. Component: history grows by one pair per success and is unchanged after a failure | unit | Vitest | stubbed global `fetch` | `npx vitest run features/chat/lib features/chat/api` | `npm test` | apps/web |
| AC4 | Question caps hold in the UI and the route | Component: blank and 1001-character input blocked with a message, no request. Unit: route returns 400 `invalid_request` for blank, 1001 chars, missing body and a body over 524,288 bytes, with `fetch` never called. e2e: an over-long question shows the inline message and no request reaches the stub | unit, e2e | Vitest; Playwright | none | `npx vitest run features/chat` | `npm test && npm run test:e2e` | apps/web |
| AC5 | Each failure has its own state, generic copy, retry, kept conversation and a text-free log line | Unit on `handleChatRequest`: the mapping table row by row (400, 429, 504, abort deadline, 502, bad-shape 200, network error, 403, 500-class, missing and blank env, unexpected throw) gives the right status and code; no response body contains a status code, the base URL or the key; the log line holds outcome and `duration_ms` and none of question, history, answer, key or secret. Component: one state per code with its copy, the question kept in the input, retry works. e2e: 429 and 504 states against the stub | unit, e2e | Vitest + Testing Library; Playwright | fake env values; stub | `npx vitest run features/chat` | `npm test && npm run test:e2e` | apps/web |
| AC6 | The route signs correctly, calls one URL once, and keeps the secret server-side | Unit on `backend.ts`: the outgoing request is `POST {base}/v1/chat` with `Authorization` starting `AWS4-HMAC-SHA256`, credential scope `…/us-east-1/execute-api/aws4_request`, `content-type` JSON, and the fake key id (never the secret) in the header; `fetch` called once even on 429/502; the abort signal is set. Guard: no `NEXT_PUBLIC_`, no `"use client"` module imports the barrel or `api/`, and no `execute-api` host literal under `features/**` and `app/**`. e2e: the stub received a signed request. Manual (human, WEBCHAT-R2): one signed call with the real key from `.env.local` | unit, e2e, manual | Vitest; Playwright | fake credentials; stub | `npx vitest run features/chat/api features/chat/conventions.test.ts features/feed/conventions.test.ts` | `npm test && npm run test:e2e` | apps/web |
| AC7 | The feed and its tests are unchanged | The existing `features/feed` suite passes untouched; the 17 `feed.e2e.ts` baseline scenarios pass with no `--update-snapshots`; `git diff` shows no change under `e2e/__baseline__/`, `feed.module.css`, `globals.css`; a new e2e check that the page `console` stays clean with the widget present | unit, e2e | Vitest; Playwright | none | `npx vitest run features/feed` | `npm test && npm run test:e2e` | apps/web |
| AC8 | Chat CSS uses tokens only and follows the OS theme | Unit: a CSS-source check that `chat.module.css` has no `#hex`, `rgb(`, `hsl(` colour and that every `padding`, `margin`, `gap` and `border-radius` value is a `var(--…)` (per `high-value-tests`, this is the WEB-9 rule itself, not a framework test); e2e: panel computed `background-color` equals the `--surface-card` value in light and in dark (`colorScheme` emulation) | unit, e2e | Vitest; Playwright | none | `npx vitest run features/chat/components/chat-css.test.ts` | `npm test && npm run test:e2e` | apps/web |
| AC9 | e2e covers open, ask, answer with sources and an error offline, and signing has a unit test | `e2e/chat.e2e.ts`: open, ask, answer with sources, 429 error state, retry; runs with no real credentials and no AWS traffic. The signing unit test is the AC6 row | e2e | Playwright | `launch-apps.mjs` and the stub extended | `npx playwright test e2e/chat.e2e.ts` | `npm run lint && npm run typecheck && npm test && npm run build && npm run test:e2e` | apps/web |

## Revision log
- Revision 1 (2026-10-22): initial draft against intent revision 2 (which corrects the baseline
  premise). Signing library chosen as `aws4fetch` after checking it with Context7; the handoff's
  suggested Smithy packages are rejected with reasons.

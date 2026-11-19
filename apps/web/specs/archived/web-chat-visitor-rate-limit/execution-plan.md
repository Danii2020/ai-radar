# Execution Plan: Web Chat Visitor Rate Limit

## Guidance consulted
- `apps/web/AGENTS.md` (WEB-1, barrel-only imports, the dependency rule, server-only config, the
  `high-value-tests` rule, deployment is a human step) and the repo root `CLAUDE.md` (two harness roots,
  monotonic ADR numbering).
- `harny-sync` lookup: `apps/web/specs/current/_index.md` and `specs/current/web-chat.md` (WEBCHAT-1 to
  WEBCHAT-12, invariants 1 to 4, reservations WEBCHAT-R1 to R9). Nothing in this plan contradicts a
  current-truth statement except the two the intent already names: WEBCHAT-8 (six codes become seven)
  and ADR 0035 (superseded). Invariant 3 is touched on purpose in `api/` and `lib/send-turn.ts` only, as
  the intent's Constraints record.
- ADR 0032 (one signed `fetch`, no library retry), ADR 0033 (fixed error codes, text-free log line),
  ADR 0035 (no per-visitor limit in v1; "revisit when publicly deployed").
- Code read: `features/chat/api/handle-chat-request.ts`, `api/backend.ts`, `api/types.ts`,
  `lib/send-turn.ts`, `lib/limits.ts`, `components/chat-panel.tsx` (`ERROR_COPY`), `index.ts`,
  `app/api/chat/route.ts`, `conventions.test.ts`, `api/handle-chat-request.test.ts`,
  `lib/send-turn.test.ts`, `components/chat-widget.test.tsx`, `e2e/chat.e2e.ts`,
  `e2e/stub/launch-apps.mjs`, `e2e/stub/feed-api-stub.mjs`, `playwright.config.ts`, `vitest.config.ts`,
  `package.json`, `.env.example`.
- Next.js 16.3.5 source in `node_modules/next/dist/server/base-server.js`: `next start` sets
  `x-forwarded-for` with `??=` to the socket address, so a client-supplied value is kept and a request
  without one gets the loopback address. This is what lets the e2e tier tell two visitors apart.
- External docs (checked 2026-11-05): Upstash REST API (Context7 `/websites/upstash_redis`): a command is
  a JSON array `POST`ed to the REST URL with `Authorization: Bearer <token>`; `EVAL` takes the script,
  then `numkeys`, keys and args; success is `{"result": ...}`, failure is `{"error": "..."}`. Vercel
  system environment variables: `VERCEL=1` at build and runtime, only when "Enable access to System
  Environment Variables" is on. The Vercel Upstash Marketplace integration documents `KV_REST_API_URL`
  and `KV_REST_API_TOKEN`; some guides report `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`.

## Ownership
- `apps/web/features/chat/api/`: the limiter (visitor key, configuration, stores, the limit decision)
  and its wiring into `handleChatRequest`; `api/types.ts` gains the seventh code.
- `apps/web/features/chat/lib/send-turn.ts` and `components/chat-panel.tsx`: the `rate_limited` result
  and its copy.
- `apps/web/features/chat/conventions.test.ts`: the extended server-only variable guard.
- `apps/web/e2e/`: a tight-limit app instance and a new rate-limit e2e file; the existing instances get
  high limits.
- Docs: `.env.example`, `AGENTS.md`, the repo root `README.md` runbook, ADRs 0049 and 0050.
- Affected `specs/current` capabilities: `web-chat` (WEBCHAT-8 amended; a new requirement for the
  limit; WEBCHAT-R1 closed; ADR 0035 superseded). `web-feed`: none.

## Binding constraints
- No new npm dependency; `package.json` and `package-lock.json` stay unchanged. The store is reached with
  the platform `fetch`, one call per check (source: intent Constraints, AGENTS.md dependency rule,
  ADR 0032 pattern).
- `features/chat/index.ts` still exports exactly `ChatWidget` and `handleChatRequest`, and
  `app/api/chat/route.ts` is unchanged (source: intent Constraints, WEBCHAT-11, invariant 3).
- `components/` and `lib/` import from `api/` only with `import type`; no `"use client"` module reaches
  `api/` (source: WEB-1, `conventions.test.ts`).
- Order inside `handleChatRequest` (source: AC5, AC10): body size and parse, question and history
  validation, the `CHAT_API_*` check (`missing_config`), then the limiter configuration, then the one
  limiter check, then the one signed backend call. Every outcome before the limiter check never touches
  the store.
- One store call per admitted or rejected request, never retried; the backend is called at most once,
  and never after a rejection or a store failure (source: invariant 2, AC5, AC9).
- The check is atomic and all-or-nothing: either all three counters are incremented (admitted) or none
  is (rejected). A rejection never counts toward any limit (source: AC4).
- Fixed windows (source: AC1 to AC3): the burst window starts at
  `floor(now_s / CHAT_RATE_LIMIT_BURST_WINDOW_S) * CHAT_RATE_LIMIT_BURST_WINDOW_S`; the daily and
  global windows are the UTC calendar day. Window identity is computed from the app server clock, and
  `Retry-After` is computed from the same clock.
- Limited response (source: AC6): status 429, body exactly `{"error":"rate_limited"}`, the existing
  `content-type: application/json` and `cache-control: no-store`, and `Retry-After` = whole seconds,
  at least 1, rounded up, until the reset of the window that blocked the request. When more than one
  limit is exhausted, `Retry-After` is the latest of their resets (so a retry at that time is not
  rejected by the other limit), and the log `limit` names one of them by the priority `global`, then
  `daily`, then `burst`.
- Store failures and invalid configuration answer 503 `{"error":"unavailable"}` with the existing
  headers and no `Retry-After` (source: AC9, AC10).
- Configuration, read per request inside `features/chat/api/` only (source: AC10, AC13; the names are
  pinned here because the runbook, `.env.example` and the conventions guard depend on them):

  | Variable | Meaning | Default | Valid |
  |---|---|---|---|
  | `CHAT_RATE_LIMIT_BURST` | admitted turns per visitor per burst window | 5 | whole number 1 to 1,000,000 |
  | `CHAT_RATE_LIMIT_BURST_WINDOW_S` | burst window in seconds | 60 | whole number 1 to 86,400 |
  | `CHAT_RATE_LIMIT_DAILY` | admitted turns per visitor per UTC day | 20 | whole number 1 to 1,000,000 |
  | `CHAT_RATE_LIMIT_GLOBAL_DAILY` | admitted turns for everyone per UTC day | 50 | whole number 1 to 1,000,000 |
  | `CHAT_RATE_LIMIT_SALT` | HMAC key for the visitor digest | per-process random, memory store only | at least 32 characters |
  | `CHAT_RATE_LIMIT_STORE` | `memory` or `upstash` | see below | one of the two |
  | `KV_REST_API_URL` (fallback `UPSTASH_REDIS_REST_URL`) | Upstash REST URL | none | absolute `http(s)` URL |
  | `KV_REST_API_TOKEN` (fallback `UPSTASH_REDIS_REST_TOKEN`) | Upstash REST token | none | non-blank |

  - "Whole number" means the trimmed value matches `^[0-9]+$` and is in range. A variable that is unset,
    empty or only whitespace uses its default (the existing `envValue` rule).
  - "On Vercel" means `VERCEL` is set and non-blank. The store is `CHAT_RATE_LIMIT_STORE` when set;
    otherwise `upstash` when on Vercel or when a REST URL variable is set, and `memory` otherwise.
  - Invalid, each with outcome `limiter_config_invalid` and `variable` naming exactly one variable
    (never its value): a limit out of range or not a whole number; `CHAT_RATE_LIMIT_STORE` with another
    value; `CHAT_RATE_LIMIT_STORE=memory` on Vercel (names `CHAT_RATE_LIMIT_STORE`); `upstash` with no
    REST URL or token (names `KV_REST_API_URL` or `KV_REST_API_TOKEN`) or an unparseable URL; `upstash`
    with no salt (names `CHAT_RATE_LIMIT_SALT`); a salt that is set but shorter than 32 characters.
    When several are invalid, the first in the table order is named.
- Visitor identity (source: AC7): first present header of `x-vercel-forwarded-for`, `x-real-ip`,
  `x-forwarded-for`; its first comma-separated entry, trimmed, validated with `node:net` `isIP`. IPv4
  whole; IPv6 reduced to its /64 (first four hextets, fully expanded and lowercase); an IPv4-mapped IPv6
  address (`::ffff:a.b.c.d`) counts as that IPv4; anything else, including a blank header or a zone id,
  is the shared `unknown` bucket. Nothing else (cookie, token, body field) feeds the key.
- Privacy (source: AC8): the digest is HMAC-SHA-256 (`node:crypto`) of the canonical visitor key with
  the salt, hex-encoded. Store keys contain the digest (that is the "keyed one-way digest" the store
  holds) and never the IP; the global key contains no visitor part. No log line and no response body
  ever contains the IP, the digest, the question, the history, the answer, the salt, the store URL or
  the token. Every entry carries its own expiry, set when the entry is created: at most two burst
  windows for a burst entry, at most 48 hours for a daily or global entry. Interpretation, flagged for
  the auditor: AC8's sentence "no ... store key ... holds ... the digest" is read as applying to log
  lines and error bodies, because the same AC requires the store to hold the digest and its example
  checks only the IP and the question in store keys and values.
- Logging (source: AC11, WEBCHAT-8): still exactly one `chat_request` line per request. New outcomes
  `rate_limited` (plus `limit`: `burst`, `daily` or `global`), `limiter_unavailable` and
  `limiter_config_invalid` (plus `variable`), all through `console.error` like every other non-ok
  outcome. No other field is added.
- UI (source: AC12): `rate_limited` copy exactly "You've reached the chat limit for now. Please try
  again later."; `unavailable` copy unchanged. A 429 whose body is not JSON or carries an unknown code
  maps to `rate_limited` in `sendTurn`; a 429 with a known code (for example `busy`) keeps that code.
  `sendTurn` never retries and ignores `Retry-After`.
- Store timeout 1 second (source: AC9): the Upstash `fetch` carries an abort signal that fires at
  1000 ms; an abort, network error, non-2xx status, a body that is not JSON, a JSON `error`, or a
  `result` outside the expected shape is `limiter_unavailable`.
- The e2e tier stays offline, mocks nothing in the browser, never regenerates `e2e/__baseline__`, and
  uses only fake credentials (source: AC13, AC14, WEBCHAT-12).
- Deployment and provisioning are human-only (source: ADR 0007, intent Scope Out).

## Proposed approach
Revisable by the executor if it records why.
- Decision 1: put the limiter in new modules under `features/chat/api/` (suggested split: visitor key,
  configuration, the memory store, the Upstash store, and a small `checkRateLimit` that returns
  admitted, limited with `limit` and `retryAfterS`, unavailable, or config invalid with `variable`).
  `handleChatRequest` calls it in the position above and maps the result. Rationale: keeps the route,
  barrel and `lib/` shell unchanged and keeps the secrets inside `api/`; rejected: a Next.js middleware
  (`proxy.ts`), which would run before validation and so count invalid requests and break AC5.
- Decision 2: one Upstash `EVAL` per check, with a Lua script that reads the three counters, returns
  which limits are exhausted if any (for example as a bitmask 1 burst, 2 daily, 4 global) and otherwise
  increments all three, setting each key's expiry only when the increment created it. Keys share one
  hash tag (for example `chat-rl:{v1}:b:<digest>:<window_start_s>`, `chat-rl:{v1}:d:<digest>:<yyyymmdd>`,
  `chat-rl:{v1}:g:<yyyymmdd>`). Rationale: atomic all-or-nothing in one round trip, which AC4 and the
  "one fetch per check" constraint both need; rejected: `MULTI`/`EXEC` pipelines (cannot make the
  increment conditional on the reads), three separate calls (not atomic, three round trips), and
  `@upstash/ratelimit` (a new dependency, needs an ADR and an intent revision).
- Decision 3: the memory store is a module-level `Map` with the same check-then-increment semantics,
  synchronous so it is atomic in one process, with lazy pruning of expired entries on each check.
  Rationale: AC13 needs no service locally; rejected: a file-backed store (no benefit, touches disk).
  Tests need a way to start from an empty store; an internal reset export from the memory-store module
  (not from the barrel) or distinct visitor IPs per test are both acceptable.
- Decision 4: the per-process random salt is generated once per process with `node:crypto`
  `randomBytes(32)`, only when the memory store is selected and no salt is set.
- Decision 5: `Retry-After` and window boundaries are computed in TypeScript from `Date.now()`, so unit
  tests drive them with `vi.useFakeTimers()` / `vi.setSystemTime()`; the store only says which limits
  are exhausted. Rationale: one clock, no dependence on Redis `TIME` or TTL replies.
- Decision 6: e2e. `e2e/stub/launch-apps.mjs` starts a third `next start` instance from the same build on
  port 3102, pointed at the populated feed and chat stub, with tight limits: `CHAT_RATE_LIMIT_BURST=2`,
  `CHAT_RATE_LIMIT_BURST_WINDOW_S=86400` (aligned to the UTC day, so a window cannot roll over mid-test
  except at midnight UTC), `CHAT_RATE_LIMIT_DAILY=1000`, `CHAT_RATE_LIMIT_GLOBAL_DAILY=1000`. The
  existing 3100 and 3101 instances get `CHAT_RATE_LIMIT_BURST`, `CHAT_RATE_LIMIT_DAILY` and
  `CHAT_RATE_LIMIT_GLOBAL_DAILY` set to 1,000,000, because the existing chat suite sends more than 20
  turns from the loopback visitor. The launcher readiness signal stays port 3100, so 3102 must start
  before it (like `empty` today). A new file `e2e/chat-rate-limit.e2e.ts` uses `test.use({ baseURL:
  'http://127.0.0.1:3102' })`, a distinct `x-forwarded-for` per test (Playwright `request` fixture with
  `extraHTTPHeaders` for the HTTP checks, `browser.newContext({ extraHTTPHeaders })` for the UI check),
  and adds no snapshot. Rejected: a fourth instance with a dead store URL for an e2e AC9 check; AC9 and
  the `unavailable` UI are proven at the unit and component tiers, and AC13 does not require them at
  e2e. The executor may add it if cheap.
- Decision 7: migrate `api/handle-chat-request.test.ts` by isolating the limiter per test (reset the
  memory store, or stub high limits in its `beforeEach`), without changing any existing assertion.
  Rationale: its 16 cases share the `unknown` visitor and would pass the default burst of 5.
- Decision 8: two ADRs in the documentation step: 0049 "Per-visitor and global chat limits in the route,
  counted in Upstash Redis over REST, failing closed" (supersedes ADR 0035; records the store choice,
  the no-dependency `EVAL`, fail closed, the /64 rule, the HMAC digest and the optional WAF rule as an
  outer layer the app does not rely on) and 0050 "The chat route answers with seven fixed error codes"
  (amends ADR 0033; ADR 0033's file is not edited). Numbering: the root `specs/current/_index.md` on this
  branch says 0048 is next, but `origin/main` (commit `8f79dc9`, `ci-log-masking`) already used 0048, so
  this feature starts at 0049.

## Consumers and migration
- `api/handle-chat-request.test.ts`: isolate the limiter per test (Decision 7); all existing cases keep
  their assertions. New cases go in a new describe block or a sibling test file.
- `lib/send-turn.test.ts`: the six-code `it.each` gains the 429 `rate_limited` row; the 418 unknown-code
  case stays `internal_error`; the header comment's code list gains `rate_limited`.
- `components/chat-widget.test.tsx`: the `CODES` table in "failure states" gains `["rate_limited", 429]`,
  so the distinct-copy check covers seven codes. The existing `busy` (429 `{"error":"busy"}`) and
  `unavailable` cases stay as they are.
- `components/chat-panel.tsx`: `ERROR_COPY` gains the `rate_limited` entry (TypeScript forces it once
  `ChatErrorCode` has seven members).
- `conventions.test.ts`: one more server-only variable guard plus its fires-on-violation case. The
  layout test (feature root holds only `api/ components/ lib/ index.ts conventions.test.ts`) still holds.
- `e2e/stub/launch-apps.mjs`: high limits on 3100 and 3101, the new 3102 instance and its stderr log in
  `e2e/.tmp/`. `e2e/chat.e2e.ts`, `e2e/layout.e2e.ts`, `e2e/feed.e2e.ts`, `e2e/__baseline__/**`,
  `e2e/fixtures/**` and `e2e/stub/feed-api-stub.mjs` are unchanged.
- `app/api/chat/route.ts`, `features/chat/index.ts`, `features/chat/lib/history.ts`,
  `features/chat/lib/limits.ts`, `api/backend.ts`: unchanged.
- Docs (documentation step): `.env.example` placeholders, `AGENTS.md` config list, root `README.md`
  runbook, ADRs 0049 and 0050, `specs/current/web-chat.md` and both `_index.md` files (WEBCHAT-R1 closed,
  WEBCHAT-8 amended, ADR registry, next ADR number).

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| "Enable access to System Environment Variables" is off on the Vercel project, so `VERCEL` is unset and, without a REST URL, the per-instance memory store is used (no shared count, no real global ceiling) | Low | High | The store also defaults to `upstash` whenever a REST URL is set; the runbook makes the checkbox and the REST variables a checked human step, and the live check (5 turns then 429; keys visible in the Upstash console) proves the shared store |
| The Marketplace integration names its variables differently from `KV_REST_API_*` | Med | Med | Both `KV_REST_API_*` and `UPSTASH_REDIS_REST_*` are read; any other name fails closed with `limiter_config_invalid` naming `KV_REST_API_URL`, and the runbook tells the human to check the project's Environment Variables page |
| A developer runs `vercel env pull`, which writes `VERCEL=1` and the REST variables into `.env.local`, so local turns count against production | Med | Low | Runbook: attach the Upstash database to Production (and Preview if wanted) only, and never pull production env into `.env.local`; `CHAT_RATE_LIMIT_STORE=memory` only works off Vercel and is refused with `VERCEL` set |
| Upstash latency or an outage blocks all chat (fail closed) | Low | Med | Accepted by the human (Q3). 1 s cap, the friendly `unavailable` state, and `limiter_unavailable` counts in the logs |
| The e2e burst window rolls over at 00:00 UTC during a run and admits an extra turn | Low | Low | 86,400 s window aligned to the UTC day; failures at midnight UTC are re-run, and `retries: 0` stays |
| Next.js stops preserving a client `x-forwarded-for` in a future upgrade, merging e2e visitors | Low | Med | The AC4 e2e test fails loudly if two visitors share a bucket; the e2e file names the `base-server.js` `??=` behaviour it relies on |
| Off Vercel a client can spoof `x-forwarded-for` | High (off Vercel only) | Low | Accepted in the intent; memory store refused on Vercel |
| The branch is four commits behind `origin/main` (root files only), so the docs step can conflict on the root `specs/current/_index.md` and `README.md` | Med | Low | Merge `origin/main` before the documentation step; numbering already accounts for ADR 0048 |
| Upstash free-tier command quota | Low | Low | One `EVAL` per request that reaches the limiter; at most a few thousand a day even under abuse, well inside the free tier; the runbook names the quota to check |

## Validation
One row per AC. Frameworks: Vitest 4 (`jsdom` default environment; server modules that need
`node:crypto`/`node:net` may set `// @vitest-environment node`), Testing Library for components,
Playwright 1.63 for e2e. Fake credentials only; no test reaches the network (the Upstash store is
tested with a stubbed global `fetch`).

| AC | Demonstrated by | Tests to write | Tier | Framework | Setup | Focused command | Broader command | Cwd |
|---|---|---|---|---|---|---|---|---|
| AC1 | Burst limit with fixed aligned windows | Handler (memory store, fake time): 6 valid requests from `203.0.113.10` in one window give 5 x 200 then 429 `rate_limited`; after setting the clock to the next window start the next request is 200; a window boundary is at a multiple of `CHAT_RATE_LIMIT_BURST_WINDOW_S` since the epoch (requests at `t = k*W - 1` and `k*W` fall in different windows). Store unit: same through the Upstash adapter with a stubbed `fetch` returning the bitmask. e2e (3102): one visitor, 2 x 200 then 429 | unit, e2e | Vitest; Playwright | `vi.useFakeTimers()`; tight-limit instance 3102 | `npx vitest run features/chat/api` | `npm test && npm run test:e2e` | apps/web |
| AC2 | Daily cap per visitor until 00:00 UTC | Handler (fake time, `CHAT_RATE_LIMIT_BURST=1000`): 20 admitted across the day, the 21st is 429; at the next 00:00:00 UTC it is admitted again; a request at 23:59:59 and one at 00:00:00 count in different days | unit | Vitest | fake time | `npx vitest run features/chat/api` | `npm test` | apps/web |
| AC3 | Global daily ceiling | Handler: `CHAT_RATE_LIMIT_GLOBAL_DAILY=3`, three different IPs admitted once each, a fourth IP's first request is 429, logged `limit: "global"`; next UTC day it is admitted. Default 50 is used when unset (51st turn across 51 IPs is 429) | unit | Vitest | fake time | `npx vitest run features/chat/api` | `npm test` | apps/web |
| AC4 | Isolation and free rejections | Handler: A exhausted (429), B admitted; A sends 50 more in the window, B still admitted; with `CHAT_RATE_LIMIT_GLOBAL_DAILY=7`, after A's 5 admitted turns, B's 1 admitted turn and A's 50 rejections, B's next turn is admitted and the one after is 429 with `limit: "global"` (proving rejections did not count); invalid body, invalid question and `missing_config` requests do not reduce the allowance (after N of them the visitor still gets the full burst); a turn whose backend `fetch` returns 502 still counts. Store unit: a rejected `EVAL` reply leads to no second store call. e2e (3102): visitor A (`198.51.100.10`) gets 429, visitor B (`198.51.100.20`) then gets 200 | unit, e2e | Vitest; Playwright | fake time; 3102 | `npx vitest run features/chat/api` | `npm test && npm run test:e2e` | apps/web |
| AC5 | The check sits after validation and config, before the one backend call | Handler: a limited request makes 0 backend `fetch` calls (no call to the backend URL; with the Upstash store, exactly one call to the store URL and none to the backend); a 400 `invalid_request` request makes 0 store calls; a `missing_config` request makes 0 store calls; an admitted request makes exactly one store call and then exactly one backend call | unit | Vitest | stubbed `fetch` routed by URL | `npx vitest run features/chat/api/handle-chat-request` | `npm test` | apps/web |
| AC6 | Response contract | Handler: 429 status, `await res.text()` equals `{"error":"rate_limited"}`, `content-type` and `cache-control` as today, `Retry-After` matches `^[1-9][0-9]*$` and equals the seconds to the burst window end (clock at 10.4 s into a 60 s window gives `50`), to the next 00:00 UTC for the daily and the global limit, and `1` when 0.2 s remain; when burst and daily are both exhausted it is the later reset. The body is identical whichever limit fired. A backend 429 still yields `{"error":"busy"}` with no `Retry-After`. `sendTurn`: a 429 `{"error":"rate_limited"}` gives code `rate_limited`. e2e (3102, `request` fixture): status, exact body, `Retry-After` a positive integer, both headers | unit, e2e | Vitest; Playwright | fake time; 3102 | `npx vitest run features/chat/api features/chat/lib/send-turn.test.ts` | `npm test && npm run test:e2e` | apps/web |
| AC7 | Visitor identity | Visitor-key unit, table-driven: header precedence (`x-vercel-forwarded-for` beats `x-real-ip` beats `x-forwarded-for`); first comma entry trimmed (`" 203.0.113.5 , 10.0.0.1"`); IPv4 whole; `2001:db8:1:2::a` and `2001:db8:1:2::b` give the same key, `2001:db8:1:3::a` a different one; compressed and expanded forms of one /64 agree; `::ffff:203.0.113.5` equals `203.0.113.5`; absent header, `garbage`, `""`, `fe80::1%eth0` give `unknown`; a cookie or body field does not change the key. Handler: two requests differing only in a cookie share a bucket | unit | Vitest | none | `npx vitest run features/chat/api` | `npm test` | apps/web |
| AC8 | Nothing identifying is kept or logged; entries expire | Handler with the Upstash store (stubbed `fetch`, captured console): request from `203.0.113.77` with question "zq-marker" (admitted, limited, store failure and config-invalid variants); neither string, the salt, the token nor the store URL appears in any console line or response body, and neither the IP nor "zq-marker" appears in the store request URL, headers or body; the store keys contain a 64-hex digest; changing `CHAT_RATE_LIMIT_SALT` changes the digest. The expiry arguments sent are at most `2 * W` for the burst key and at most 172,800 for the daily and global keys. Memory store: with fake time, an entry is gone after 2 burst windows and after 48 h. Upstash script: the expiry is set only when the key is created (asserted on the script text sent, or by a script-semantics test against a fake that interprets the reply) | unit | Vitest | stubbed `fetch`; fake time | `npx vitest run features/chat/api` | `npm test` | apps/web |
| AC9 | Fail closed | Handler with the Upstash store, table-driven: `fetch` rejects (`ECONNREFUSED`-style `TypeError`), 500 status, 200 with non-JSON, 200 with `{"error":"ERR ..."}`, 200 with `{"result":"x"}` or out-of-range integer, and a `fetch` that resolves only on abort (advance fake time 1000 ms, or wait just over 1 s): each gives 503 `{"error":"unavailable"}`, 0 backend calls, exactly one store call, and one log line with outcome `limiter_unavailable`. Component: a 503 `unavailable` reply shows "Chat is unavailable at the moment. Try again later." (existing test kept) | unit, component | Vitest; Testing Library | stubbed `fetch`; fake time | `npx vitest run features/chat/api` | `npm test` | apps/web |
| AC10 | Configuration checked per request, failing safe | Configuration unit, table-driven over every row of the variable table: `abc`, `-1`, `0`, `1.5`, `1e3`, above the max give `limiter_config_invalid` naming that variable; blank or unset gives the default; `CHAT_RATE_LIMIT_STORE=redis` invalid; `memory` with `VERCEL=1` invalid; `upstash` without URL, token or salt, or with a 31-character salt, invalid; defaults to `upstash` on Vercel and when a REST URL is set, `memory` otherwise. Handler: `CHAT_RATE_LIMIT_DAILY=abc` gives 503 `unavailable`, 0 backend and 0 store calls, the log line has `variable: "CHAT_RATE_LIMIT_DAILY"` and contains no `abc`; changing an env var between two requests changes the result of the second (read per request) | unit | Vitest | `vi.stubEnv` | `npx vitest run features/chat/api` | `npm test` | apps/web |
| AC11 | One text-free log line per request | Handler: for admitted, each `limit` (`burst`, `daily`, `global`), `limiter_unavailable` and `limiter_config_invalid`, exactly one captured line parses as JSON with `event: "chat_request"`, the expected `outcome`, `duration_ms`, plus `limit` or `variable` only where stated, and no other keys; non-ok lines go to `console.error`, ok to `console.info` | unit | Vitest | console spies (existing pattern) | `npx vitest run features/chat/api/handle-chat-request` | `npm test` | apps/web |
| AC12 | UI states | `sendTurn`: 429 with `{"error":"rate_limited"}`, with HTML (non-JSON) body and with `{"error":"other"}` all give `rate_limited`; 429 `{"error":"busy"}` stays `busy`; 418 unknown code stays `internal_error`. Component (`chat-widget.test.tsx`): the `CODES` table gains `rate_limited` (seven distinct copies, no status/URL/code name); the `rate_limited` alert text equals the exact copy; a 429 HTML body shows that copy; the `unavailable` alert equals its existing exact copy; both alerts fail `/limiter|store|redis|upstash|salt|config|retry-after|rate_limited/i`; after each, the textbox keeps the question and Retry is present. e2e (3102, browser context with its own `x-forwarded-for`): two answers, then the third shows the exact copy, no `429`/`http`/code name, the textbox keeps the question, Retry visible | unit, component, e2e | Vitest; Testing Library; Playwright | 3102 | `npx vitest run features/chat/lib/send-turn.test.ts features/chat/components/chat-widget.test.tsx` | `npm test && npm run test:e2e` | apps/web |
| AC13 | No new service locally | `npm test` and `npm run test:e2e` pass with no `.env.local` and no `CHAT_RATE_LIMIT_*`/`KV_*` variable in the shell (the launcher sets the e2e instances' values itself); no test stubs or reaches a real store host; the 3102 e2e file proves AC1, AC4, AC6 and AC12 against the existing stub. Configuration unit: off Vercel with nothing set, the memory store and a 64-hex digest from a random salt are used and no `fetch` happens | unit, e2e, command | Vitest; Playwright | env -u for the run | `env -u VERCEL -u KV_REST_API_URL -u UPSTASH_REDIS_REST_URL npm test` | `npm run test:e2e` | apps/web |
| AC14 | Compatibility | All existing `handle-chat-request`, `backend`, `send-turn`, `history`, `conversation`, `chat-widget`, `message-response`, `chat-css` and `conventions` tests pass with only the migrations listed above; the six existing codes still map as before (existing tests); `npx playwright test e2e/feed.e2e.ts` passes all 17 baseline scenarios without `--update-snapshots`; `e2e/chat.e2e.ts` and `e2e/layout.e2e.ts` pass unchanged. Conventions: the barrel test still sees exactly two exports. Commands: `git diff --exit-code -- package.json package-lock.json app/api/chat/route.ts features/chat/index.ts features/chat/lib/history.ts features/chat/lib/limits.ts features/chat/api/backend.ts e2e/__baseline__ e2e/fixtures e2e/feed.e2e.ts e2e/chat.e2e.ts e2e/layout.e2e.ts e2e/stub/feed-api-stub.mjs` exits 0 | unit, component, e2e, command | Vitest; Playwright; shell | none | `npx vitest run features/chat` | `npm run lint && npm run typecheck && npm test && npm run build && npm run test:e2e` | apps/web |
| AC14 (guard) | The new secrets stay inside `api/` | `conventions.test.ts` extension: a regex for `CHAT_RATE_LIMIT_[A-Z_]+`, `KV_REST_API_[A-Z_]+` and `UPSTASH_REDIS_REST_[A-Z_]+`, applied to every non-test file under the app root outside `features/chat/api/` (the existing walk, which skips `e2e/`, `specs/` and dotfiles), expects no hit; a fires-on-violation case shows `process.env.CHAT_RATE_LIMIT_SALT` and `process.env.KV_REST_API_TOKEN` in `app/fake.tsx` are flagged and plain code is not | unit | Vitest | none | `npx vitest run features/chat/conventions.test.ts` | `npm test` | apps/web |
| AC15 | Docs | Checked at the documentation step and by the auditor: ADR 0049 exists with `Supersedes: 0035` and ADR 0050 amends 0033 (seven codes), both registered in `apps/web/specs/current/_index.md`, the root index's next-ADR note updated; `specs/current/web-chat.md` has WEBCHAT-8 amended, a new limit requirement and WEBCHAT-R1 closed, and the `_index.md` reservation row removed; `.env.example` holds placeholders (no real value) for every variable in the table; `AGENTS.md` config list names them; the root `README.md` has the human runbook with the defaults 5 per 60 s, 20 per visitor per day, 50 globally per day, the Upstash and salt steps, the system-env checkbox, the optional Hobby WAF rule (for example 30 requests per 60 s per IP on `/api/chat`) stated as optional, and the live check. Command: `grep -n "CHAT_RATE_LIMIT_SALT" .env.example AGENTS.md ../../README.md` finds all three | command, review | shell | none | `grep -n "CHAT_RATE_LIMIT_" .env.example AGENTS.md` | `npm run lint && npm run typecheck && npm test` | apps/web |

## Revision log
- Revision 1 (2026-11-05): initial plan from intent revision 2 (approved).

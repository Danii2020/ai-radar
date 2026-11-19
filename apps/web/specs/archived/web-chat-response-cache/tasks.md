# Tasks: Web Chat Response Cache

## Status
Needs human sign-off (O0 to O8 and O10 done 2026-11-18, audit APPROVED WITH RESERVATIONS; O9 docs partly done, the ADRs, capability docs, CHANGELOG and README wait for the post-audit documentation step)

## Baseline
- Base commit: f3b8f1b (the tip of `feat/web-chat-swipe-handle`; the rate-limit archive from P1 is an uncommitted change on top)
- Branch: feat/web-chat-response-cache (created from `feat/web-chat-swipe-handle`, so it carries that unmerged work and sits on `main` only through it)
- Interpreter: Node v24.16.0 (npm per `package.json`; record `npm --version` in O0)
- Cwd: /Users/danielerazo/python/project-agentcore-app/apps/web
- Commands: test `npm test`; lint `npm run lint`; type-check `npm run typecheck`; build `npm run build`;
  e2e `npm run test:e2e` (offline; needs `npx playwright install chromium` once)
- Pre-existing failures: none. Baseline (2026-11-18, after P1, before any code change): lint 0 errors and 1 warning (unused eslint-disable in `features/feed/api/types.generated.ts`), typecheck clean, `npm test` 21 files and 433 tests passed, `npm run build` ok, `npm run test:e2e` 61 passed (17 baseline scenarios), npm 11.13.0

## Precondition (not an executor task)
- [x] **P1** (intent Q3) `web-chat-visitor-rate-limit` is documented and archived: its O9 and AC15 done
  through `harny-document`, `harny-sync` and `harny-adr`, and the change merged, so
  `specs/current/web-chat.md` records the limiter. Done 2026-11-18 on this branch (uncommitted): archived, ADRs 0049 and
  0050 written, `web-chat` amended (WEBCHAT-8, WEBCHAT-14, R1 closed, R12), both `_index.md` updated. This feature's two ADRs
  take 0057 and 0058.

## Outcomes
Order is TDD: write the red tests for an outcome, then the code. Every outcome keeps `npm run lint` and
`npm run typecheck` clean. Never edit `app/api/chat/route.ts`, `features/chat/index.ts`,
`features/chat/api/backend.ts`, `features/chat/lib/**`, `features/chat/components/**`,
`e2e/__baseline__/**`, `e2e/fixtures/**`, `e2e/feed.e2e.ts`, `e2e/chat.e2e.ts`, `e2e/layout.e2e.ts`,
`e2e/chat-rate-limit.e2e.ts`, `specs/archived/**` or `specs/current/**`. Never run Playwright with
`--update-snapshots`. The only package change is the one in O6. Never use a real Upstash URL, token or
salt, or the real chat API key, in a test or a committed file.

- [x] **O0** (AC12) Baseline. Run the five commands above before any change and record test counts and
  failures under Baseline (17 baseline scenarios).
- [x] **O1** (AC2, AC4, AC7, AC8) `features/chat/api/response-cache.ts`: `CHAT_CACHE_TTL_S` parsing (default
  21600, `0` off, 60 to 86400, otherwise invalid and named), question normalization, HMAC-SHA-256 key under
  the `chat-cache:` prefix with the limiter's salt source, the in-process store with expiry, the Upstash
  read (`GET`) and write (`SET ... EX`) with the 1 second abort, validation of a read value with
  `isChatResponse`, and every failure shape reported as a failed read or write, never thrown.
  - Tests: `features/chat/api/response-cache.test.ts` (table-driven normalization; key never holds the
    text; salt and prefix separation from the limiter digest; TTL table; store request shapes; fake timers
    for expiry; stubbed `fetch` for each failure shape).
  - Red: `npx vitest run features/chat/api/response-cache.test.ts` failed (module missing, no tests ran).
  - Green: same command, 34 passed.
- [x] **O2** (AC5) Burst-only mode in `features/chat/api/rate-limit.ts`: a second Lua script and an
  in-process branch that read and increment only the burst counter (expiry set on creation), `Retry-After`
  from the burst window, the full check and its script unchanged.
  - Tests: new cases in `features/chat/api/rate-limit.test.ts` beside the existing ones.
  - Red: `npx vitest run features/chat/api/rate-limit.test.ts` failed 4 of 119 (the new hit cases) before the code.
  - Green: same command, 119 passed. `rate-limit.test.ts` also gained one `vi.stubEnv("CHAT_CACHE_TTL_S", "0")` line in
    its `beforeEach` (its cases resend one question and count store calls, which a cache hit would change).
- [x] **O3** (AC1, AC3, AC4, AC5, AC6, AC7, AC9, AC10) Wire the cache into `handleChatRequest` in the plan's
  order: validation, `CHAT_API_*`, limiter configuration read once and shared, cache read on a first turn,
  hit then burst-only check then respond, miss then full check then backend then awaited write; the
  `cache` log field (`hit`, `miss`, `skip`, `error`, absent when off); no error response from any cache
  failure; limiter failures unchanged.
  - Tests: new `describe` in `features/chat/api/handle-chat-request.test.ts` per plan § Validation
    AC1, AC3 to AC10 (distinct question per case, marker strings, exact log key sets).
  - Red: NOT captured. The handler wiring was written before its new test block, so there is no failing run for the
    cache cases in `handle-chat-request.test.ts`; the limiter-side hit cases (O2) did fail first.
  - Green: `npx vitest run features/chat/api` 244 passed.
- [x] **O4** (AC12) Migration of the existing handler tests: `CHAT_CACHE_TTL_S=0` in `beforeEach`, no
  existing assertion changed.
  - Check: `npx vitest run features/chat/api` 244 passed; the `git diff` of the existing cases is one `vi.stubEnv` line
    (plus its comment) in `handle-chat-request.test.ts` and the same in `rate-limit.test.ts`.
- [x] **O5** (AC14 guard, AC8) Extend `features/chat/conventions.test.ts`: `CHAT_CACHE_TTL_S` named only inside
  `features/chat/api/`, and `@vercel/analytics` imported only by `app/layout.tsx`, each with a
  fires-on-violation case.
  - Red: NOT captured: the checkers live in the test file, so the new cases were green at once (the same as for the
    rate-limit spec's O6); they protect the implementation.
  - Green: `npx vitest run features/chat/conventions.test.ts` 15 passed.
- [x] **O6** (AC14) `npm i --save-exact @vercel/analytics@2.0.1`; `app/layout.tsx` renders
  `{process.env.VERCEL ? <Analytics /> : null}` from `@vercel/analytics/next`.
  - Tests: `app/layout.test.tsx` (package mocked; present when `VERCEL` is set, absent when unset).
  - Red: `npx vitest run app/layout.test.tsx` failed 1 of 2 (Analytics absent on Vercel) before the layout change.
  - Green: same command, 2 passed; `git diff package.json` shows `"@vercel/analytics": "2.0.1"` only, and the lockfile adds
    the package and its entries (43 lines).
- [x] **O7** (AC1, AC5, AC10, AC11) e2e: `e2e/stub/feed-api-stub.mjs` counts chat requests per prefix and
  exposes the count; `e2e/stub/launch-apps.mjs` sets `CHAT_CACHE_TTL_S=0` on 3100, 3101 and 3102 and starts a
  fifth instance on 3103 (cache 3600 s, global ceiling 1, burst out of reach) with its stderr in
  `e2e/.tmp/`; new `e2e/chat-response-cache.e2e.ts` (distinct `x-forwarded-for` per visitor, no snapshots).
  - Red: NOT captured: the stub counter and the instance were written before the e2e file.
  - Green: `npx playwright test e2e/chat-response-cache.e2e.ts` 3 passed.
- [x] **O8** (AC11, AC12) Broader suite vs baseline: `npm run lint && npm run typecheck && npm test &&
  npm run build && npm run test:e2e`, then `env -u VERCEL -u KV_REST_API_URL -u UPSTASH_REDIS_REST_URL npm
  test`, then `git diff --exit-code -- app/api/chat/route.ts features/chat/index.ts e2e/__baseline__`.
  Record counts against O0.
  - Result (2026-11-18): lint 0 errors and the same 1 warning; typecheck clean; `npm test` 23 files, 496 tests passed
    (also with `VERCEL`, `KV_REST_API_URL` and `UPSTASH_REDIS_REST_URL` unset); build ok; `npm run test:e2e` 64 passed
    (baseline 61 plus the 3 new; the 17 baseline scenarios and every "clean console" check unchanged); the `git diff
    --exit-code` guard exits 0 (also over `features/chat/lib`, `components` and `api/backend.ts`).
- [ ] **O9** (AC13) PARTLY DONE: `.env.example`, `AGENTS.md` (config, components, sanctioned dependency list), `docs/runbooks.md`
  (new "Chat response cache and Web Analytics" subsection) are written. Still to do after the audit: the two ADRs (0057 cache
  design, 0058 dependency rule for `@vercel/analytics`), `web-chat.md` amendments, `_index.md`, `CHANGELOG.md`, `README.md`.
  Original text: Docs, by the documentation step (`harny-adr`, `harny-document`, `harny-sync` archive):
  the cache ADR and the dependency-rule ADR for `@vercel/analytics`; `.env.example` placeholder;
  `AGENTS.md` config list, sanctioned dependencies and Components note; the runbook (clear one answer or all
  by `chat-cache:` prefix, never a database-wide flush; enable Web Analytics; optional TTL override);
  `specs/current/web-chat.md` (WEBCHAT-8 `cache` field, new cache requirement) and `_index.md`.
- [x] **O10** Audit: APPROVED WITH RESERVATIONS (round 1, 2026-11-18; `audit.md`). Self-audit by the implementing session, so not independent (F4); F2 and F3 open, AC13 pending.

## Working state
- Updated: 2026-11-18
- Outcome: O8 done
- Phase: audited, waiting for the human's sign-off and the documentation step
- In progress: nothing
- Last command: `npm run test:e2e` 64 passed
- Next step: human sign-off, then the documentation step for O9 (`harny-document`, `harny-sync`, `harny-adr`)

## Finding responses
| Finding | Response | Evidence |
|---|---|---|

## Human-only steps (never executor tasks; run after audit, from the runbook)
- [ ] **H1** Enable Web Analytics for the project in the Vercel dashboard (Project -> Analytics -> Enable).
- [ ] **H2** Optional: set `CHAT_CACHE_TTL_S` in Vercel Project Settings (server-side only) to change the
  six hour default, or `0` to switch the cache off. Confirm "Enable access to System Environment Variables"
  is on so `VERCEL=1` reaches the layout.
- [ ] **H3** Live check after deploy: ask a suggested prompt twice; the second answer returns quickly; the
  Vercel function log shows `chat_request` lines with `cache: "miss"` then `cache: "hit"`; the Upstash data
  browser shows only `chat-cache:` digest keys with an expiry (no question text); the page view appears in
  the Vercel Analytics dashboard. WEBCHAT-R2 and WEBCHAT-R3 stay open unless checked at the same time.

## Checkpoint
Audited. Resume at the documentation step (O9), then archive.

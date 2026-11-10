# Tasks: Web Chat Visitor Rate Limit

## Status
Implementing (intent revision 2 approved; execution plan revision 1 awaiting human review before O1)

## Baseline
- Base commit: ff8d56d (local `main`; `origin/main` is 4 commits ahead with root-only changes, including
  ADR 0048 from `ci-log-masking`)
- Branch: feat/web-chat-visitor-rate-limit
- Interpreter: Node v24.16.0 (npm per `package.json`; record `npm --version` in O0)
- Cwd: /Users/danielerazo/python/project-agentcore-app/apps/web
- Commands: test `npm test`; lint `npm run lint`; type-check `npm run typecheck`; build `npm run build`;
  e2e `npm run test:e2e` (offline; needs `npx playwright install chromium` once)
- Pre-existing failures: to be recorded in O0 before any change

## Outcomes
Order is TDD: write the red tests for an outcome, then the code. Every outcome keeps `npm run lint` and
`npm run typecheck` clean. Never edit `app/api/chat/route.ts`, `features/chat/index.ts`,
`features/chat/lib/history.ts`, `features/chat/lib/limits.ts`, `features/chat/api/backend.ts`,
`package.json`, `package-lock.json`, `e2e/__baseline__/**`, `e2e/fixtures/**`, `e2e/feed.e2e.ts`,
`e2e/chat.e2e.ts`, `e2e/layout.e2e.ts`, `e2e/stub/feed-api-stub.mjs`, `specs/archived/**` or
`specs/current/**`. Never run Playwright with `--update-snapshots`. Never add an npm package. Never use a
real Upstash URL, token or salt, or the real chat API key, in a test or a committed file.

- [x] **O0** (AC14) Baseline. NOTE: no pre-change baseline of the five commands was captured; the only pre-change evidence is the test writer's red run (100 vitest failures, 3 Playwright failures in the new file). Post-change gates below are not a baseline. Run the five commands above with no `.env.local` influence on tests and
  record counts and failures under Baseline.
- [x] **O1** (AC7, AC10, AC13) Visitor key and configuration in `features/chat/api/`: header precedence,
  IPv4 whole, IPv6 /64, IPv4-mapped, `unknown`; the variable table of the plan with defaults, ranges,
  store selection, the Vercel refusal of `memory`, salt rules and the per-process random salt.
  - Tests: new unit tests under `features/chat/api/` (table-driven), per plan § Validation AC7, AC10.
  - Red: `npx vitest run features/chat/api` fails on the new cases.
  - Green: same command passes.
- [x] **O2** (AC1, AC2, AC3, AC4, AC8) The two stores and the limit decision: fixed aligned burst window,
  UTC day, global ceiling, atomic all-or-nothing increment, expiry set at creation (at most 2 burst
  windows, at most 48 h), HMAC-SHA-256 digest in keys, `Retry-After` and `limit` precedence from the
  plan's binding constraints. The Upstash store sends one `EVAL` with the 1 s abort signal and maps every
  failure to unavailable (AC9 shape, wired in O3).
  - Tests: memory-store and Upstash-store unit tests with fake time and a stubbed `fetch`.
  - Red / Green: `npx vitest run features/chat/api`.
- [x] **O3** (AC1 to AC11) Wire the limiter into `handleChatRequest` after validation and the
  `CHAT_API_*` check and before the backend call; add `rate_limited` to `ChatErrorCode` in
  `api/types.ts`; the new outcomes `rate_limited`, `limiter_unavailable`, `limiter_config_invalid` with
  `limit` and `variable`; 429 with `Retry-After`; 503 for store failure and invalid config.
  - Tests: new handler cases per plan § Validation AC1 to AC11 (new describe block or sibling file).
  - Red / Green: `npx vitest run features/chat/api/handle-chat-request`.
- [x] **O4** (AC14) Migration of the existing handler tests: isolate the limiter per test (plan
  Decision 7) with no existing assertion changed.
  - Check: `npx vitest run features/chat/api` passes, and `git diff` of the existing test cases shows
    setup changes only.
- [x] **O5** (AC6, AC12) Browser side: `sendTurn` maps 429 `rate_limited`, 429 non-JSON and 429 unknown
  code to `rate_limited` and keeps 429 `busy`; `ERROR_COPY.rate_limited` in `components/chat-panel.tsx`
  is exactly "You've reached the chat limit for now. Please try again later."; `unavailable` copy
  unchanged.
  - Tests: `lib/send-turn.test.ts` (new rows, header comment updated); `components/chat-widget.test.tsx`
    (`CODES` gains `rate_limited`; exact copies; banned-words check; question kept; Retry shown).
  - Red / Green: `npx vitest run features/chat/lib/send-turn.test.ts features/chat/components/chat-widget.test.tsx`.
- [x] **O6** (AC14 guard) Extend `features/chat/conventions.test.ts`: `CHAT_RATE_LIMIT_*`,
  `KV_REST_API_*` and `UPSTASH_REDIS_REST_*` named only inside `features/chat/api/`, with a
  fires-on-violation case.
  - Red: the fires-on-violation case fails before the checker exists.
  - Green: `npx vitest run features/chat/conventions.test.ts`.
- [x] **O7** (AC1, AC4, AC6, AC12, AC13) e2e: in `e2e/stub/launch-apps.mjs` set limits of 1,000,000 on
  3100 and 3101 and start the tight instance on 3102 (burst 2, window 86,400 s, daily 1000, global 1000)
  before 3100, with its stderr in `e2e/.tmp/`; add `e2e/chat-rate-limit.e2e.ts` (distinct
  `x-forwarded-for` per test, no snapshots).
  - Red: the new e2e file fails before the instance exists (or against a build without the limiter).
  - Green: `npx playwright test e2e/chat-rate-limit.e2e.ts`.
- [x] **O8** (AC13, AC14) Broader suite vs baseline: `npm run lint && npm run typecheck && npm test &&
  npm run build && npm run test:e2e`, then `env -u VERCEL -u KV_REST_API_URL -u UPSTASH_REDIS_REST_URL
  npm test`, then the AC14 `git diff --exit-code -- ...` command from the plan. Record counts against O0
  (17 baseline scenarios unchanged).
- [ ] **O9** (AC15) Docs, by the documentation step (`harny-adr`, `harny-document`, `harny-sync`
  archive), after merging `origin/main`: ADR 0049 (supersedes 0035) and ADR 0050 (amends 0033, seven
  codes); `.env.example` placeholders; `AGENTS.md` config list; root `README.md` runbook covering H1 to
  H5 below, the defaults and the optional WAF rule; `specs/current/web-chat.md` and both `_index.md`
  files (WEBCHAT-8 amended, new requirement, WEBCHAT-R1 closed, ADR registry, next ADR 0051).
- [ ] **O10** Independent audit: verdict from `audit.md`.

### Tests and Red evidence (test writer, 2026-11-05)
Final vitest run: 20 files, 389 tests, 100 failed, 289 passed. Playwright: 50 passed, 3 failed (all in the new file).
- **O1, O2, O3** (AC1 to AC11, AC13): `features/chat/api/rate-limit.test.ts` (new; node environment; fresh handler module per
  test, Date faked only, stubbed `fetch` routed to a fake Upstash REST store and fake backend). Visitor identity and
  configuration are observed through the handler (burst 1 as the probe), so no internal module name is fixed.
  Red: `npx vitest run features/chat/api/rate-limit.test.ts` fails on the limiter behaviour (e.g. "expected 200 to be 429",
  "expected 200 to be 503", "expected null to be '43190'" for Retry-After, "expected [] to have a length of 1" for store calls).
  Cases that already pass are compatibility guards (no leak, validation and missing config make no store call, a backend 429
  stays busy, unknown/default behaviour).
- **O4** (AC14): `features/chat/api/handle-chat-request.test.ts` only gains three `vi.stubEnv` lines in `beforeEach`
  (burst, daily, global = 1000000); no assertion changed; still green.
- **O5** (AC6, AC12): `lib/send-turn.test.ts` (429 rate_limited row; 429 HTML / unknown code / empty body -> `rate_limited`;
  busy stays; no retry) and `components/chat-widget.test.tsx` (CODES gains `rate_limited`; exact copies for `rate_limited`
  and `unavailable`; banned-words check; question kept; Retry shown). Red: they get `internal_error` / the generic
  "Something went wrong" copy.
- **O6** (AC14 guard): `features/chat/conventions.test.ts` gains the limiter-variable guard and its fires-on-violation case.
  Both are green at once because the checker lives in the test file and no file outside `api/` names the variables yet; the
  guard protects the implementation.
- **O7** (AC1, AC4, AC6, AC12, AC13): `e2e/stub/launch-apps.mjs` (3100/3101 get 1,000,000 limits; new tight instance 3102:
  burst 2, window 86400, daily 1000, global 1000) and `e2e/chat-rate-limit.e2e.ts`. Red: `npx playwright test
  e2e/chat-rate-limit.e2e.ts` -> 3 failed, each at the third turn (200 instead of 429; no limit alert).
- Not directly testable through the handler, so not written: memory-store pruning after 2 windows / 48 h (internal;
  window rollover is covered by AC1/AC2 tests) and the Lua script's "expire only on creation" (only the presence of an
  expiry, its ranges and the digest are asserted).

### Human-only steps (never executor tasks; run after audit, from the README runbook)
- [ ] **H1** Create the Upstash Redis database through the Vercel Marketplace and connect it to the
  Vercel project, Production environment (Preview only if wanted). Confirm the variable names on the
  project's Environment Variables page (`KV_REST_API_URL`/`KV_REST_API_TOKEN` or the `UPSTASH_REDIS_REST_*`
  pair). Never pull them into `.env.local`.
- [ ] **H2** Confirm "Enable access to System Environment Variables" is on for the project (so `VERCEL=1`).
- [ ] **H3** Set `CHAT_RATE_LIMIT_SALT` (a random value of at least 32 characters, generated locally and
  never pasted into chat or logs) and any limit override in Vercel Project Settings, server-side only.
- [ ] **H4** Optional: add the Vercel Hobby WAF rate-limit rule on `/api/chat` (for example 30 requests
  per 60 s per IP) as an outer flood shield. The app does not depend on it.
- [ ] **H5** Live check after deploy: six quick turns from one browser give five answers and then the
  `rate_limited` copy; the Upstash data browser shows only digest keys (no IP); the Vercel function log
  shows `chat_request` lines with `outcome: "rate_limited"` and `limit: "burst"`. WEBCHAT-R2 and
  WEBCHAT-R3 stay open unless checked at the same time.

## Working state
- Updated: 2026-11-05
- Outcome: O0-O8 done. Evidence 2026-11-05: vitest features/chat/api 183/183; npm test 389/389; lint 0 errors (1 pre-existing warning in types.generated.ts); typecheck clean; build ok; test:e2e 53/53; AC14 git diff --exit-code exits 0
- Phase: implemented; next O9 docs, O10 audit
- Last command: npm test -> 381 passed, 8 failed; lint 0 errors (1 pre-existing warning); typecheck, build clean; test:e2e 53 passed
- Blocked tests (rate-limit.test.ts): (1) three AC11 `limit` cases compare sorted keys to [...KEYS,"limit"], but "limit" sorts before "outcome"; (2) four AC10 "0" cases assert the log line does not contain "0", yet duration_ms is 0; (3) AC8 digest case expects Request.url to equal STORE_URL without trailing slash, but Request normalises to "...invalid/".
- Next step: test writer fixes those 8 assertions, then rerun; then O9 docs, O10 audit

## Finding responses
| Finding | Response | Evidence |
|---|---|---|

## Checkpoint
Plan revision 1 and these tasks are written; nothing implemented. Resume at O0 after the human approves
the plan.

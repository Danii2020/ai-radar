# Audit: Web Chat Visitor Rate Limit

Round 1, 2026-11-05. Branch `feat/web-chat-visitor-rate-limit`, base `ff8d56d`, uncommitted working tree.
In scope: `apps/web/features/chat/**`, `apps/web/e2e/stub/launch-apps.mjs`, `apps/web/e2e/chat-rate-limit.e2e.ts`.
Out of scope, not audited (per the caller): root `infra/`, `src/shared/config.py`, root `.gitignore`, `evals/`,
root `.env.example`, `CHANGELOG.md`, `CLAUDE.md`, `src/shared/AGENTS.md`, `tests/`.

Files read in full: `api/rate-limit.ts`, `api/rate-limit-config.ts`, `api/visitor.ts`, `api/rate-limit.test.ts`,
`e2e/chat-rate-limit.e2e.ts`, and the diffs of `api/handle-chat-request.ts`, `api/types.ts`, `lib/send-turn.ts`,
`components/chat-panel.tsx`, `api/handle-chat-request.test.ts`, `lib/send-turn.test.ts`,
`components/chat-widget.test.tsx`, `conventions.test.ts`, `e2e/stub/launch-apps.mjs`.

Round 2, 2026-11-09. Same branch and base, still uncommitted. Scope set by the human: close F1 only; F2 to F5
were deliberately not addressed. Since round 1, only `api/rate-limit-config.ts` and `api/rate-limit.test.ts`
changed under `apps/web/features` and `apps/web/e2e`. The other feature files have the same mtime as in round 1
(2026-11-05 22:08), and `tasks.md` is unchanged since 2026-11-05 22:24. Both changed files were read in full
(the AC10 block of the test file was read in full). Rows below that changed in round 2 are marked "(round 2)".

## AC results
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `checkRateLimit` keys the burst counter on `floor(nowS/W)*W`; Lua and memory store reject at `count >= limit`. Unit: 6 requests give 5 x 200 then 429; boundary at `k*W-1 ms` / `k*W`; Upstash bitmask 1 gives 429 `limit: burst`. e2e 3102: 2 x 200 then 429 (rerun) |
| AC2 | PASS | Daily key `d:<digest>:<yyyymmdd>` from the UTC ISO date; 21st is 429, 23:59:59.999 still 429, 00:00:00 admitted (rerun) |
| AC3 | PASS | Global key `g:<yyyymmdd>` has no visitor part; ceiling 3 gives 429 `limit: global` for a 4th IP, admitted next day; default 50 (51st of 51 IPs is 429) (rerun) |
| AC4 | PASS | Check-then-increment is all-or-nothing (Lua returns before any INCR; memory store returns before any write). Unit: A's 50 rejections leave B admitted and do not count toward a ceiling of 7; invalid bodies and `missing_config` cost nothing; a 502 turn still counts. e2e: A 429, B 200 (rerun) |
| AC5 | PASS | `handle()` calls `checkRateLimit` after body/question/history validation and the `CHAT_API_*` check, before `callChatBackend`. Unit: invalid and `missing_config` make 0 store calls; admitted makes store then backend, in that order; limited makes 0 backend calls (rerun) |
| AC6 | PASS | `failure()` adds `retry-after` only for `rate_limited`; `ceil((reset-now)/1000)` floored at 1; latest reset when several limits fire. Unit: `50` at 10.4 s into a 60 s window, `1` at 0.2 s left, daily/global reset to 00:00 UTC, later reset when burst+daily, identical body, backend 429 stays `busy` without Retry-After, 503 has none. e2e: status, exact body, both headers, Retry-After positive integer (rerun) |
| AC7 | PASS | `visitor.ts`: header precedence, first comma entry trimmed, `isIP`, IPv4 whole, IPv6 /64 fully expanded lowercase, IPv4-mapped to IPv4, zone id / blank / garbage to `unknown`. Unit table (rerun); ad hoc probe of 24 inputs (rerun, scratch script, see Notes) |
| AC8 | PASS | Keys hold `createHmac('sha256', salt)` hex of the canonical key, never the IP; log line carries only event/outcome/duration_ms/limit/variable. Expiry: burst `2*W`, daily/global 172,800 s, set only when `INCR == 1` (Lua) or at creation (memory). Unit: no IP, marker, salt, token, store URL or digest in console or bodies across admitted/limited/failure/config; store request holds the digest and not the IP or the question; salt change changes the digest; expiry arguments in range (rerun). e2e tight-instance stderr holds only `{"event","outcome","duration_ms","limit"}` lines (rerun). Interpretation (digest allowed in store keys, banned from logs and bodies) accepted: it is the only reading consistent with the AC's own first sentence and example. Expire-on-create and memory pruning are untested, see F2 |
| AC9 | PASS | `upstashCheck` returns `null` on reject, abort at 1000 ms (timer covers the body read too), non-2xx, non-JSON, `error` present, or a result outside integers 0..7; `null` maps to 503 `unavailable`, outcome `limiter_unavailable`, no retry. Unit: 8 failure shapes plus a real-timer abort test (~1 s); component: existing `unavailable` copy (rerun) |
| AC10 | PASS (round 2) | Round 1: PARTIAL (F1). Round 2: `readRateLimitConfig` now checks, in this order: the four limits, a set but short `CHAT_RATE_LIMIT_SALT`, `CHAT_RATE_LIMIT_STORE` (invalid value, then memory on Vercel), and then, for `upstash`, a missing salt before the REST URL and token. This matches the table order BURST, WINDOW, DAILY, GLOBAL, SALT, STORE, URL, TOKEN. A missing salt is invalid only once the store resolves to `upstash`, so it cannot be checked before the store. New unit cases: short salt + `CHAT_RATE_LIMIT_STORE=redis` names `CHAT_RATE_LIMIT_SALT`, and upstash with no salt, URL or token names `CHAT_RATE_LIMIT_SALT`. All other AC10 cases are unchanged and pass (rerun) |
| AC11 | PASS | One `chat_request` line per request; `limit` / `variable` only where stated; non-ok to `console.error`. Unit asserts exact key sets (rerun) |
| AC12 | PASS | `ERROR_COPY.rate_limited` is the exact copy; `unavailable` unchanged; `sendTurn` maps 429 with non-JSON, empty or unknown body to `rate_limited`, keeps 429 `busy`, 418 unknown stays `internal_error`. Component: exact copies, banned-word regex, no 429/503, question kept, Retry present. e2e 3102 UI test (rerun) |
| AC13 | PASS | Off Vercel with nothing set the memory store and a per-process `randomBytes(32)` salt are used. `env -u VERCEL -u KV_REST_API_URL -u UPSTASH_REDIS_REST_URL npm test` 389/389; `npm run test:e2e` 53/53 with no new env (launcher sets its own) (rerun) |
| AC14 | PASS | The plan's `git diff --exit-code -- package.json package-lock.json app/api/chat/route.ts features/chat/index.ts ... e2e/stub/feed-api-stub.mjs` exits 0; barrel test still sees two exports; all 17 feed baseline scenarios and the chat/layout suites pass unchanged; `handle-chat-request.test.ts` gained three `vi.stubEnv` lines only (rerun) |
| AC15 | N/A | Not yet done: O9 (documentation step) is open. `.env.example` and `AGENTS.md` in `apps/web` do not yet name the variables. Not counted as a failure in this round |

## Binding-constraint compliance
| Constraint | Status | Evidence |
|---|---|---|
| No new npm dependency; `package.json`/`package-lock.json` unchanged; platform `fetch` | PASS | AC14 diff exits 0 (rerun) |
| Barrel exports exactly two; `route.ts` unchanged | PASS | Diff exits 0; barrel test green (rerun) |
| `components/`/`lib/` import `api/` only as types; no `"use client"` reaches `api/` | PASS | `conventions.test.ts` green; `send-turn.ts` and `chat-panel.tsx` add no import (rerun) |
| Order in `handleChatRequest` (validation, `CHAT_API_*`, limiter config, limiter check, backend) | PASS | Code read; AC5 unit tests (rerun) |
| One store call per request, never retried; backend at most once, never after rejection or store failure | PASS | No retry path in `upstashCheck`; unit asserts exactly one store call in failure and limited cases (rerun) |
| Atomic, all-or-nothing increment | PASS | One `EVAL`; Redis runs a Lua script atomically; reads precede all writes and return early on any exhausted limit. Memory store is synchronous within one tick |
| Fixed windows from the app clock; Retry-After from the same clock | PASS | `Date.now()` drives window start, UTC day and resets; the store only returns the mask |
| Limited response contract, latest reset, `limit` priority global > daily > burst | PASS | Code read; AC6 unit tests (rerun) |
| 503 for store failure / bad config, no Retry-After | PASS | Unit (rerun) |
| Configuration table: names, defaults, ranges, store selection, Vercel refusal | PASS | `rate-limit-config.ts` matches the table |
| Configuration: "When several are invalid, the first in the table order is named" | PASS (round 2) | Round 2: closed by audit option (a), see AC10 and F1. Code trace of the remaining combinations: short salt + `VERCEL=1` without a REST URL names `CHAT_RATE_LIMIT_SALT`. Missing salt + invalid store names `CHAT_RATE_LIMIT_STORE`, because a missing salt is valid unless the store is `upstash`. Missing salt + memory on Vercel names `CHAT_RATE_LIMIT_STORE` (same reason). Missing salt + upstash + missing URL/token names `CHAT_RATE_LIMIT_SALT`. All are consistent with the table order. Round 1 result: FAIL. Table order is BURST, WINDOW, DAILY, GLOBAL, **SALT**, STORE, URL, TOKEN. Code checks the salt last (after STORE, URL, TOKEN). Example: `CHAT_RATE_LIMIT_SALT=short` + `CHAT_RATE_LIMIT_STORE=redis` names `CHAT_RATE_LIMIT_STORE`; plan requires `CHAT_RATE_LIMIT_SALT`. Same for `VERCEL=1`, no REST URL, short salt (names `KV_REST_API_URL`). No rationale recorded in `tasks.md`. F1 |
| Visitor identity rules | PASS | AC7 evidence |
| Privacy: digest in keys only, no IP/digest/text/salt/URL/token in logs or bodies; expiry at creation within 2 W / 48 h | PASS | AC8 evidence |
| Logging: one line, new outcomes, `limit`/`variable` only, all non-ok via `console.error` | PASS | AC11 evidence |
| UI: copy, 429 unknown/non-JSON to `rate_limited`, known 429 code kept, no retry, Retry-After ignored | PASS | AC12 evidence |
| Store timeout 1 s; every failure shape is `limiter_unavailable` | PASS | AC9 evidence |
| e2e offline, no browser mocks, baseline not regenerated, fake credentials only | PASS | e2e run; `e2e/__baseline__` diff clean; launcher keeps fake keys (rerun) |
| Deployment human-only | PASS | No deploy or provisioning attempted |

Upstash contract (caller's question). The tests pin: `POST <REST URL>` with `Authorization: Bearer <token>`, body a JSON
array `["EVAL", script, numkeys, ...keys, ...args]`, success `{"result": <n>}`, failure `{"error": "..."}`. The live
Upstash REST docs (`https://upstash.com/docs/redis/features/restapi`, fetched 2026-11-05; the Context7 tool was not
available in this session) confirm each part: commands may be POSTed as a JSON array to the base URL with the first
element the command name (their example includes a bare number, `["SET","foo","bar","EX",100]`), auth is a Bearer
token, replies are `{"result": ...}` (integer example `{"result":137}`), and failures are `{"error": "..."}` with
400 for a failed command and 401 for bad auth. A Lua number returned from a script is a Redis integer reply, so the
script's `return mask` arrives as `{"result": 0..7}`. All three keys share the `{v1}` hash tag and are declared in
`KEYS`. The assumed contract matches the real API; the one untested assumption is that the provisioned database
accepts `EVAL` (Upstash documents Lua scripting support), which the human live check H5 proves.

## Test coverage
| AC | Test | Status |
|---|---|---|
| AC1 | `api/rate-limit.test.ts` "burst limit per visitor (AC1)" (5 cases); `e2e/chat-rate-limit.e2e.ts` AC1/AC6 test | PASS |
| AC2 | `api/rate-limit.test.ts` "daily cap per visitor (AC2)" (3) | PASS |
| AC3 | `api/rate-limit.test.ts` "global daily ceiling (AC3)" (2) | PASS |
| AC4 | `api/rate-limit.test.ts` "isolation and free rejections (AC4)" (6); e2e AC4 test | PASS |
| AC5 | `api/rate-limit.test.ts` "the check sits after validation..." (4) | PASS |
| AC6 | `api/rate-limit.test.ts` "limited response contract (AC6)" (8); `lib/send-turn.test.ts` 429 row; e2e AC1/AC6 test | PASS |
| AC7 | `api/rate-limit.test.ts` "visitor identity (AC7)" (17) | PASS |
| AC8 | `api/rate-limit.test.ts` "nothing identifying is kept or logged (AC8)" (8) | PARTIAL (F2: expire-on-create and memory expiry untested) |
| AC9 | `api/rate-limit.test.ts` "fail closed (AC9)" (9); existing `chat-widget.test.tsx` `unavailable` case | PASS |
| AC10 | `api/rate-limit.test.ts` "configuration is checked per request..." (~40, plus 2 in round 2: "a short salt is named before an invalid store (table order)", "a missing salt is named before a missing REST URL and token (table order)") | PASS (round 2: the salt-order rule now has tests) |
| AC11 | `api/rate-limit.test.ts` "one text-free log line per request (AC11)" (6) | PASS |
| AC12 | `lib/send-turn.test.ts` (5 new); `components/chat-widget.test.tsx` (CODES + 4 new); e2e AC12 test | PASS |
| AC13 | `api/rate-limit.test.ts` "no new service locally (AC13)"; env-unset `npm test`; full e2e | PASS |
| AC14 | All pre-existing suites; `conventions.test.ts` limiter guard + fires-on-violation; AC14 `git diff` | PASS |
| AC15 | Docs check | N/A (O9 pending) |

Gate results (all rerun by the auditor on 2026-11-05, current working tree):
- `npm test`: 20 files, 389 passed, 0 failed. `env -u VERCEL -u KV_REST_API_URL -u UPSTASH_REDIS_REST_URL npm test`: 389 passed.
- `npm run build`: exit 0 (routes `/`, `/_not-found`, `/api/chat`).
- `npm run test:e2e`: 53 passed (includes the 3 new `chat-rate-limit.e2e.ts` tests and the feed baseline scenarios), exit 0.
- `npm run lint`: 0 errors, 1 warning (unused eslint-disable in `features/feed/api/types.generated.ts`, a file this change does not touch, so it predates the change). `npm run typecheck`: exit 0. These two were run at the caller's explicit request; the role normally verifies them through `harny-feedback` only.
- AC14 `git diff --exit-code -- <plan list>`: exit 0.

Gate results, round 2 (all rerun by the auditor on 2026-11-09, current working tree):
- `npm run lint`: exit 0. 0 errors, 1 warning: the same pre-existing warning in the untouched `features/feed/api/types.generated.ts`.
- `npm run typecheck`: exit 0.
- `npm test`: 20 files, 391 passed, 0 failed. That is round 1's 389 plus the 2 new AC10 cases.
- `env -u VERCEL -u KV_REST_API_URL -u UPSTASH_REDIS_REST_URL npm test`: 391 passed.
- `npm run build`: exit 0 (routes `/`, `/_not-found`, `/api/chat`).
- `npm run test:e2e`: 53 passed, exit 0. This includes the 3 `chat-rate-limit.e2e.ts` tests, the 17 feed baseline scenarios, and the chat and layout suites.
- AC14 `git diff --exit-code -- package.json package-lock.json app/api/chat/route.ts features/chat/index.ts features/chat/lib/history.ts features/chat/lib/limits.ts features/chat/api/backend.ts e2e/__baseline__ e2e/fixtures e2e/feed.e2e.ts e2e/chat.e2e.ts e2e/layout.e2e.ts e2e/stub/feed-api-stub.mjs`: exit 0.
- `git status` was the same after the runs; no tracked file was changed by the gates.

Round 2 test edits (the F1 fix):
- The two new cases each fail against the round-1 order. This is shown by code trace, not by a rerun: the file is
  untracked, so the pre-fix version cannot be restored without changing the tree. Under the round-1 code, short salt +
  `CHAT_RATE_LIMIT_STORE=redis` named `CHAT_RATE_LIMIT_STORE`, which round 1 recorded as the F1 example. Upstash with
  no salt, URL or token named `KV_REST_API_URL`. Both now name `CHAT_RATE_LIMIT_SALT`. Each goes through `expectInvalid`,
  which asserts the 503 body, no store or backend call, one `console.error` line, and that the value is not logged.
- The existing case "the store defaults to upstash on Vercel (and fails closed without its settings)" gained
  `CHAT_RATE_LIMIT_SALT: SALT` in its env, and its assertion (`KV_REST_API_URL`) is unchanged. **Accepted.** Under
  the corrected order, a missing salt would be named first, so without the setup change the case would test the salt
  rule instead of the missing-URL rule it is about. It still proves both of its claims: the store resolved to
  `upstash` (memory on Vercel would name `CHAT_RATE_LIMIT_STORE`), and it fails closed without the REST URL. The edit
  follows from the spec'd order and does not weaken the test. The "upstash with no salt" row of the `it.each` table
  still names `CHAT_RATE_LIMIT_SALT` and passes.

Red evidence: reused from `tasks.md` (test writer: 100 vitest failures and 3 Playwright failures before the
implementation, with failure messages of the expected kind). The 8 post-hoc test edits were reviewed in their current
form (the pre-edit text is unavailable: the file is untracked):
- AC11 key sets now compare `Object.keys(line).sort()` to `[...KEYS, "limit"].sort()`: the original compared against an
  unsorted expected array, a test bug. Intent (exact key set) unchanged.
- AC10 "never the value": now strips `duration_ms` and checks the rest of the line for the value. The original could not
  pass for `"0"` because `duration_ms` was `0`. The check still covers every field that could leak the value. Intent unchanged.
- AC8 store URL: now compares `new URL(x).href` on both sides, because `Request` normalises a bare origin to a trailing
  `/`. Intent unchanged.
All three were assertion-mechanics fixes; none weakened what the test proves.

Dead seams: none. The tests import only `./handle-chat-request` and drive everything through env, `Date` and a
stubbed `fetch`; every stub is reached.

High-value-tests quality: tests observe behaviour through the public handler (no internal module names fixed), use
table-driven cases, fake time only where needed, and assert exact contracts. No tautologies or framework tests. Two
weak spots: the Lua script is only checked by `toMatch(/expire/i)` on its text (F2), and the e2e Retry-After check is
only a range (acceptable; the exact value is pinned at unit tier).

### Tier Results
| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit | `api/rate-limit.test.ts` (node env), `lib/send-turn.test.ts`, `conventions.test.ts`, migrated `api/handle-chat-request.test.ts` | AC1-AC14 | Yes: Vitest, `vi.useFakeTimers({toFake:["Date"]})`, `vi.stubEnv`, stubbed `fetch`; no config change | Yes, `npm test` (rerun round 1 and round 2: 391 passed) | PARTIAL | F2 (AC8 memory expiry and expire-on-create not tested; still open in round 2) |
| component | `components/chat-widget.test.tsx` | AC9, AC12, AC14 | Yes: Testing Library, jsdom | Yes, `npm test` (rerun) | PASS | |
| e2e | `e2e/chat-rate-limit.e2e.ts` (3 tests); existing feed/chat/layout suites | AC1, AC4, AC6, AC12, AC13, AC14 | Yes: third `next start` on 3102 with the plan's tight limits, 3100/3101 at 1,000,000; `playwright.config.ts` unchanged; no snapshot added | Yes, `npm run test:e2e` (rerun round 1 and round 2: 53 passed) | PASS | |
| command | env-unset `npm test`; AC14 `git diff --exit-code` | AC13, AC14 | Yes | Yes (rerun) | PASS | |
| command, review (docs) | AC15 grep | AC15 | n/a | Not run: O9 pending | N/A | |

## Findings
| Id | Severity | Cites | Finding | Closure condition | Status |
|---|---|---|---|---|---|
| F1 | CRITICAL (by bucket definition: unmet binding constraint; operational impact low) | AC10; plan binding constraint "When several are invalid, the first in the table order is named" | `readRateLimitConfig` (`features/chat/api/rate-limit-config.ts`, lines 47-65) validates `CHAT_RATE_LIMIT_SALT` after `CHAT_RATE_LIMIT_STORE`, `KV_REST_API_URL` and `KV_REST_API_TOKEN`, but the table puts SALT before them. With a short salt plus an invalid store (or `VERCEL=1` without a REST URL), the log names the wrong variable relative to the plan. Both named variables are truly invalid, so the visitor-facing behaviour and fail-closed guarantee are intact; only the spec'd precedence differs. No rationale was recorded | Either (a) the short-salt check moves ahead of the store check, and the "upstash without salt" check comes right after the store is resolved and before the URL/token checks, with a unit case (short salt + `CHAT_RATE_LIMIT_STORE=redis` names `CHAT_RATE_LIMIT_SALT`); or (b) the architect revises the binding constraint to the implemented order, with the human's approval, and the rationale goes into `tasks.md` | **Resolved (round 2, 2026-11-09)**. Option (a) was verified: `rate-limit-config.ts` lines 47-49 check the short salt before the store (line 51), and line 57 checks the missing salt right after the store resolves, before the URL (58) and token (65) checks. The required unit case exists ("a short salt is named before an invalid store (table order)"), plus a missing-salt-before-URL/token case. Both pass (rerun), and red is shown by code trace. `tasks.md` has no F1 response row; that is folded into F5 |
| F2 | MEDIUM | AC8; § Validation AC8 row | The row names a memory-store expiry test (entry gone after 2 burst windows and after 48 h) and an "expiry set only when the key is created" check. Neither exists; the test writer recorded them as "not directly testable through the handler". Current tests check only that an expiry is present and in range. A regression to an unconditional `EXPIRE` would not be caught | A test that would fail if `EXPIRE` ran on every increment (for example a script-semantics test against a fake that interprets the command, or an assertion on the script text pairing `EXPIRE` with `== 1`), and a fake-time memory-store expiry test; or the architect drops them from § Validation | Open (round 2: not addressed, by the human's choice) |
| F3 | MEDIUM | AC14; `tasks.md` O0; harny-audit step 4 | O0 is checked `[x]` although its own note says no pre-change baseline was captured. An unavailable required check recorded as done. Impact is small: every gate is green now, so there is no failure to attribute, and the one lint warning is in an untouched generated file, so it predates the change | O0 marked `[!]` with the explanation, or a baseline captured at `ff8d56d` and recorded | Open (round 2: not addressed, by the human's choice) |
| F4 | LOW | harny-feedback | Per-turn hook: indirect evidence only (the `.sdd/feedback/.turns` accumulator was emptied at 22:03 on 2026-11-05, which the Stop hook does when it runs), and no run log with the `N of M command(s) ran` line was found. CI: `harny-feedback-apps-web.yml` exists and its latest runs on `main` are green, but it has never run on this change (uncommitted) | The PR's `harny-feedback (apps/web)` run is green and its log shows `N of M command(s) ran` with N >= 1 | Open (round 2: not addressed. The change is still uncommitted, so there is no CI run. `.sdd/feedback/` now holds only `run-feedback.mjs`, so there is still no run log) |
| F5 | LOW | `tasks.md` hygiene | `tasks.md` contradicts itself: Status says "awaiting human review before O1", Checkpoint says "nothing implemented", and Working state still lists the 8 blocked tests and "Last command: 381 passed, 8 failed" next to the later 389/389 result | `tasks.md` Status, Working state and Checkpoint describe the current state, and the "Finding responses" table records the F1 fix | Open (round 2: not addressed, by the human's choice. `tasks.md` is unchanged since 2026-11-05 and also lacks an F1 response row) |

## Notes (not findings)
- Executor deviation on validation order: covered by F1. Moving the salt last was probably meant to make "salt required" depend on the resolved store. That is reasonable, but it does not need to move the short-salt check, and it was not recorded.
- O0 baseline: there is no pre-existing failure to compare, because all 389 unit tests and 53 e2e tests pass now. The only warning is in an untouched generated file. See F3.
- Bug hunt, no defect found in:
  - Retry-After rounding (`ceil`, floor 1).
  - Window math (epoch-aligned burst, UTC day from one `Date.now()`).
  - Lua atomicity (reads before writes, early return, `EXPIRE` only on `INCR == 1`, shared hash tag).
  - Fail-closed paths (every failure shape returns `null`, the timer covers `res.json()`, any throw falls to 500, never to admit).
  - Log leaks: no IP or digest in any log path, and e2e stderr was confirmed.
- IPv6 edge cases, probed ad hoc on 2026-11-05 with a copy of `visitor.ts` in the scratchpad:
  - Compressed, expanded and upper-case forms agree. `1:2:3:4:5:6:7::` and embedded-IPv4 tails parse. `::ffff:a.b.c.d` and `::ffff:0102:0304` both map to the IPv4.
  - `[v6]`, `v4:port`, leading-zero IPv4 and zone ids go to `unknown`.
  - Some addresses collapse into one /64 by design: IPv4-compatible `::a.b.c.d` (deprecated) and NAT64 `64:ff9b::a.b.c.d` share one bucket per /64. This does not matter in practice, since such addresses do not reach Vercel as client IPs.
  - A present but blank `x-vercel-forwarded-for` gives `unknown` rather than falling through. This matches the plan.
- Recommendations:
  - `upstashCheck` does not drain the body of a non-2xx reply (`return null` before `res.json()`). That is harmless here, but `await res.body?.cancel()` would release the connection sooner.
  - The memory store prunes by scanning the whole map on every check, which is fine off Vercel only.
- The branch is behind `origin/main` (for example PR #14 bumped Playwright to 1.64.1, while the plan names 1.63). Re-run `npm run test:e2e` after the planned merge before O9.

## Audit log
| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-11-05 | REJECTED | All gates rerun green (389 unit/component, 53 e2e, build, lint 0 errors, typecheck). One blocking finding, F1 (config-precedence binding constraint). It can be closed with a small code change or a plan revision. F2, F3 MEDIUM; F4, F5 LOW. AC15 pending O9 |
| 2 | 2026-11-09 | APPROVED WITH RESERVATIONS | F1 resolved by option (a) with 2 new unit cases. One existing case got a setup-only salt line, which was judged acceptable. All gates rerun green: lint 0 errors, typecheck, 391 unit/component, build, 53 e2e. The AC14 diff guard exits 0, and the other ACs show no regression. F2, F3 (MEDIUM) and F4, F5 (LOW) were left open by the human's choice, and none of them blocks approval. AC15 is still pending O9 |

## Final verdict

APPROVED WITH RESERVATIONS (round 2, 2026-11-09; round 1 was REJECTED)

**Summary**: F1, the only blocking finding, is resolved. Configuration errors now name the variable in the plan's table order, and two new unit cases cover it. Every gate reruns green: 391 unit/component, 53 e2e, build, lint and typecheck. The AC14 guard holds, and no other AC regressed. Approval carries reservations, because four non-blocking findings were deliberately left open and AC15 (docs) has not yet been done.

How the open findings affect the verdict:
- None is an unmet AC or binding constraint, so none blocks approval.
- F2 is a test gap. The code does set the expiry only on key creation (verified by reading the Lua in round 1), but no test would catch a regression to an unconditional `EXPIRE`, and the memory-store expiry test that § Validation names is missing.
- F3, F4 and F5 are evidence and record-keeping gaps, not product defects.
- These four findings are why the verdict is "with reservations" and not APPROVED.

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- F2 (MEDIUM, open): the AC8 expire-on-create and memory-store expiry tests named in § Validation are missing.
- F3 (MEDIUM, open): O0 is marked `[x]` without a baseline. Mark it `[!]` with the explanation.
- F4 (LOW, open): there is no CI run on this change yet, and the hook evidence is indirect. Close it on the PR's `harny-feedback (apps/web)` run.
- F5 (LOW, open): the Status, Working state and Checkpoint sections of `tasks.md` are stale, and it has no F1 response row.
- AC15 is still pending O9. It must be checked against its § Validation row once O9 runs, and this approval does not cover it.

**Recommendations** (nice to have):
- Cancel the body of a non-2xx Upstash reply.
- Merge `origin/main` and re-run e2e before O9.

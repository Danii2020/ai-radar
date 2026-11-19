# Audit: Web Chat Response Cache

Round 1, 2026-11-18. Branch `feat/web-chat-response-cache` (created from `feat/web-chat-swipe-handle`), base `f3b8f1b`, uncommitted working tree.
Spec: intent revision 3 (approved 2026-11-18), execution plan revision 1 (approved 2026-11-18).
In scope: `apps/web/features/chat/api/{response-cache,rate-limit,handle-chat-request}.ts` and their tests, `features/chat/conventions.test.ts`,
`app/layout.tsx`, `app/layout.test.tsx`, `package.json`, `package-lock.json`, `e2e/stub/{feed-api-stub,launch-apps}.mjs`,
`e2e/chat-response-cache.e2e.ts`, and the docs written so far (`AGENTS.md`, `.env.example`, `docs/runbooks.md`).
Out of scope: the P1 archive of `web-chat-visitor-rate-limit` (ADRs 0049 and 0050, `web-chat.md`, both `_index.md`), which is not part of this feature.

**Independence caveat.** This round was run in the same session, by the same model, that wrote the implementation. It re-read the code and reran
every gate, but it is not an independent review. See F4. The human should treat the verdict as a self-check and may want a fresh-session audit before merge.

## AC results
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `handle()` reads the cache for a first turn and returns the stored `{answer, sources}` on a hit with no `callChatBackend`. Unit "AC1/AC10" (miss then hit: same status, body, headers, backend called once); e2e 3103: second visitor, stub counter stays 1 (rerun) |
| AC2 | PASS | `normalizeQuestion` = trim, collapse `\s+`, `toLowerCase`, nothing else. Unit table (5 rows) and handler "AC2" (upper-case, padded spelling hits; dropping the `?` misses); e2e sends the upper-cased padded question (rerun) |
| AC3 | PASS | `history.length > 0` sets `cache: "skip"` and skips read and write. Unit: two history turns call the backend twice, store nothing (the later empty-history turn is a miss); e2e: the same question with a history gets 429, not the cached answer (rerun) |
| AC4 | PASS | Only `result.ok` (validated by `isChatResponse` in `backend.ts`) is written, once, as `SET key json EX ttl`. Unit: shape `["SET", key, json, "EX", "3600"]`; 400/429/502/504/403/500 are never stored (6 cases); fake-timer expiry at 99 s hit, 100 s miss, refresh; TTL table (default 21600, `0` off, 60..86400, 59/86401/abc/1.5/-60 invalid) (rerun) |
| AC5 | PASS | Hit runs `checkRateLimit(..., {mode:'burst'})`; miss runs the full check. `rate-limit.test.ts`: hits leave the daily cap and the global ceiling alone, a hit counts burst and a burst-limited visitor gets 429 with `Retry-After` and no backend call; Upstash: hit = one-key `EVAL`, miss = three-key `EVAL`. e2e 3103 (ceiling 1): hit 200 after the ceiling is used, a new question 429 (rerun) |
| AC6 | PASS | Order in `handle()`: validation, `CHAT_API_*`, `readRateLimitConfig()`, cache read, limiter. Unit (Upstash fake): bad body, empty question, missing config and invalid limiter setting make 0 store calls; a limiter store failure on a hit and on a miss gives 503 `unavailable` and 0 backend calls (rerun) |
| AC7 | PASS | `readCache`/`writeCache` never throw; every failure is `error`/`false`, treated as a miss; the 1 s `AbortController` covers the body read. Unit: network error, 500, non-JSON, `error` field, non-string result, non-JSON result, non-chat-response result, abort at 1000 ms for read and write; handler: read throw, read 500, bad stored value, failed write each give 200 live with `cache: "error"`; invalid `CHAT_CACHE_TTL_S` answers live, log names the variable and not the value (rerun) |
| AC8 | PASS (interpretation) | Key = `chat-cache:{v1}:` + HMAC-SHA-256(`saltFor(config)`, `"cache\0" + normalized`), a distinct input from the limiter's digest; value is `{answer, sources}` only. Unit: key never holds the text, differs by salt, differs from a plain keyed digest; handler: marker strings absent from every log line and every store key. The AC says no store key holds "the digest", yet the key is the digest; read the same way the rate-limit audit read its AC8 (digest allowed in store keys, banned from logs and bodies), the only reading consistent with the AC's first sentence. See Notes |
| AC9 | PASS | One `chat_request` line; `cache` is `hit`/`miss`/`skip`/`error` and absent when off. Handler test asserts exact key sets for hit, miss, skip, off (outcome and level unchanged); `error` covered in the AC7 cases (rerun) |
| AC10 | PASS | A hit builds `new Response(JSON.stringify({answer, sources}), {status: 200, headers: HEADERS})`, the same constructor as a live answer. Unit compares `Object.fromEntries(headers)` of hit and live; e2e compares body and `content-type`/`cache-control` (rerun) |
| AC11 | PASS | Off Vercel the cache uses the limiter's in-process store. `env -u VERCEL -u KV_REST_API_URL -u UPSTASH_REDIS_REST_URL npm test`: 496 passed; `npm run test:e2e`: 64 passed with only the launcher's variables (rerun) |
| AC12 | PASS | Existing cases changed by one `vi.stubEnv("CHAT_CACHE_TTL_S","0")` line (plus comment) in each of `handle-chat-request.test.ts` and `rate-limit.test.ts`; the diff shows no removed line. `git diff --exit-code` over `route.ts`, `index.ts`, `e2e/__baseline__`, `e2e/fixtures`, the existing e2e files, `lib/`, `components/`, `backend.ts`, `rate-limit-config.ts`, `visitor.ts` exits 0. Barrel test still sees two exports; 17 baseline scenarios green (rerun) |
| AC13 | N/A (pending) | Partly done by design: `.env.example`, `AGENTS.md` (config, component, sanctioned dependency) and the runbook subsection exist. The two ADRs, the `web-chat.md` amendments, `CHANGELOG.md` and `README.md` wait for the post-audit documentation step. Not counted as a failure |
| AC14 | PASS | `app/layout.tsx` renders `{process.env.VERCEL ? <Analytics /> : null}` from `@vercel/analytics/next`. Unit: present with `VERCEL` set, absent without (red before the change: 1 of 2 failed); conventions guard: imported only by `app/layout.tsx` (+ fires-on-violation); `package.json` diff is the one line `"@vercel/analytics": "2.0.1"`; lockfile adds only that package and its optional peers; all existing "clean console" and "127.0.0.1 only" e2e assertions pass (rerun). The dashboard side is a human step (H1, H3) |

## Binding-constraint compliance
| Constraint | Status | Evidence |
|---|---|---|
| P1: rate-limit spec archived first | PASS | `specs/archived/web-chat-visitor-rate-limit/` exists with ADRs 0049 and 0050; `web-chat.md` records WEBCHAT-14 (done earlier this session) |
| No new dependency for the cache; platform `fetch`, one call per read and per write, 1 s timeout, no retry | PASS | `response-cache.ts` imports only `node:crypto`, `lib/chat-response`, types and `rate-limit`; `command()` makes one `fetch` with a 1000 ms abort; no retry path |
| Exactly one new dependency, `@vercel/analytics` pinned exactly, imported only by `app/layout.tsx` | PASS | `package.json` `"2.0.1"` (no caret); lockfile diff read; conventions guard green |
| Order: validation, `CHAT_API_*`, limiter config, cache read, (hit: burst check) / (miss: full check, backend, write) | PASS | `handle()` read in full; AC5 and AC6 tests |
| Limiter full check, Lua script, response contract and fail-closed unchanged; burst mode additive | PASS | `SCRIPT` untouched; `BURST_SCRIPT` and `mode` added; all pre-existing limiter tests pass unchanged apart from the one env line |
| The cache never produces an error response | PASS | All cache failures map to a miss (AC7 tests); only `limiterOutcome` and backend outcomes fail a request |
| Key = HMAC of the normalized question with the limiter's salt source under a distinct prefix; no text/digest in logs or bodies | PASS | `cacheKey` uses `saltFor` (shared with `checkRateLimit`); AC8 tests |
| Stored value `{answer, sources}` only, written once with expiry; a bad stored value is a failed read | PASS | `writeCache` builds the value from the two fields; `parseStored` rejects with `isChatResponse` |
| `CHAT_CACHE_TTL_S` read per request, only inside `features/chat/api/`, in the conventions guard | PASS | `readCacheSettings` reads `process.env` per call; `LIMITER_ENV` regex gained `CHAT_CACHE_*`; fires-on-violation case present |
| Barrel exports two; `route.ts`, `components/`, `lib/` unchanged; baseline not regenerated | PASS | Guard diff exits 0 |
| `Analytics` only when `VERCEL` is set; no `NEXT_PUBLIC_` variable | PASS | `layout.tsx` read; no `NEXT_PUBLIC_` in the diff |
| Deployment, enabling Web Analytics and live checks are human-only | PASS | None attempted; `tasks.md` H1 to H3 |
| Consumers and migration: handler and limiter tests, conventions test, launcher, stub, docs | PASS (docs partly pending) | Each present; `launch-apps.mjs` sets `CHAT_CACHE_TTL_S=0` on 3100, 3101, 3102 and runs the new 3103 instance with its own chat prefix; stub counter at `GET /_count/<prefix>` |

## Outcome completion
`tasks.md`: P1 and O0 to O8 are `[x]` with evidence; O9 is explicitly marked partly done; O10 is this audit. The three outcomes without red evidence (O3, O5, O7) say
"NOT captured" in `tasks.md` rather than claiming it (see F2).

## Test coverage
| AC | Test | Status |
|---|---|---|
| AC1 | `api/handle-chat-request.test.ts` "response cache" AC1/AC10; `e2e/chat-response-cache.e2e.ts` test 1 | PASS |
| AC2 | `api/response-cache.test.ts` normalization and key; handler AC2 | PASS |
| AC3 | handler AC3; e2e test 3 | PASS |
| AC4 | `api/response-cache.test.ts` in-process and Upstash stores, TTL table; handler AC4 (6 error statuses, expiry, write shape) | PASS |
| AC5 | `api/rate-limit.test.ts` "a cache hit counts against the burst limit only" (3 + 2 Upstash); e2e test 2 | PASS |
| AC6 | handler Upstash AC6 (2 cases) | PASS |
| AC7 | `api/response-cache.test.ts` Upstash failure shapes and 1 s abort; handler AC7 (invalid setting, 4 failure cases) | PASS |
| AC8 | `api/response-cache.test.ts` key tests; handler AC8 | PASS |
| AC9 | handler AC9 | PASS |
| AC10 | handler AC1/AC10; e2e test 1 | PASS |
| AC11 | env-unset `npm test`; full e2e | PASS |
| AC12 | all pre-existing suites; guard diff | PASS |
| AC13 | docs check | N/A (pending) |
| AC14 | `app/layout.test.tsx`; `conventions.test.ts` analytics guard; existing e2e console checks | PASS |

Gate results (all rerun by the auditor on 2026-11-18, current working tree):
- `npm run lint`: 0 errors, 1 warning (the unused eslint-disable in `features/feed/api/types.generated.ts`, identical to the baseline). `npm run typecheck`: clean.
- `npm test`: 23 files, 496 passed. Baseline was 21 files, 433 passed; the difference is the new `response-cache.test.ts` (34), `layout.test.tsx` (2) and the added cases in the handler, limiter and conventions files.
- `env -u VERCEL -u KV_REST_API_URL -u UPSTASH_REDIS_REST_URL npm test`: 496 passed.
- `npm run build`: compiled successfully; routes `/`, `/_not-found`, `/api/chat`.
- `npm run test:e2e`: 64 passed (baseline 61 plus 3), 17 baseline scenarios unchanged, no snapshot touched.
- Guard `git diff --exit-code -- <frozen list>`: exit 0.

Dead seams: none found. The handler tests drive everything through env, a faked `Date` and a stubbed `fetch`; `response-cache.test.ts` imports only the module's own exports, each of which the handler also uses.

High-value-tests quality: tests observe behaviour (status, body, headers, logs, store commands) rather than internals, use tables for normalization and TTL, and fake time only where needed. No tautologies or framework tests. One weaker spot: the in-process cache has no test for pruning of expired entries (only expiry on read), a small gap noted in F5.

### Tier Results
| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit | `api/response-cache.test.ts`, `api/handle-chat-request.test.ts`, `api/rate-limit.test.ts`, `conventions.test.ts`, `app/layout.test.tsx` | AC1 to AC12, AC14 | Yes: vitest, `vi.stubEnv`, faked `Date`, stubbed `fetch`; the one new dependency is the one the plan names; no config change | Yes, `npm test` (496 passed) | PARTIAL | F2 (no red evidence for the handler cache cases and the conventions guards) |
| e2e | `e2e/chat-response-cache.e2e.ts` (3 tests); existing suites | AC1, AC3, AC5, AC10, AC11, AC14 | Yes: fifth `next start` instance on 3103 with the plan's settings, stub counter, existing instances run with `CHAT_CACHE_TTL_S=0`; `playwright.config.ts` unchanged | Yes, `npm run test:e2e` (64 passed) | PARTIAL | F2 (no red evidence) |
| command / review (docs) | AC13 grep | AC13 | n/a | Not run: documentation step pending | N/A | |

## Findings
| Id | Severity | Cites | Finding | Closure condition | Status |
|---|---|---|---|---|---|
| F1 | LOW | AC8 | The AC says no store key holds the digest, but the key is a digest of the question. The audit reads it as "digest allowed in store keys, banned from logs and error bodies", the same reading the rate-limit audit accepted for its own AC8. The intent text should say so | The documentation step records the interpretation in the new ADR, or the intent wording is corrected | Open |
| F2 | MEDIUM | execution plan § Validation; `tasks.md` O3, O5, O7 | No red evidence exists for the handler cache cases (`handle-chat-request.test.ts`), the conventions guards (green at once, as the checker lives in the test file) or the new e2e file (stub, launcher and test written in that order). `tasks.md` records "NOT captured" for each, so it is honest, but the criterion "a test that would fail if the behaviour were removed, with recorded red evidence" is not met for them. The limiter, module and layout tests did fail first | The architect or human accepts the gap, or the executor shows a failing run against a build without the cache step | Open |
| F3 | MEDIUM | `harny-feedback` | No evidence that the per-turn Stop hook ran (`.sdd/feedback/` holds only `run-feedback.mjs`, no run log) and no CI run of `harny-feedback-apps-web.yml` exists, because the branch is local and uncommitted. Same class as WEBCHAT-R7 | The PR's `harny-feedback (apps/web)` run is green and its log shows `N of M command(s) ran` with N >= 1 | Open |
| F4 | MEDIUM | audit independence | This audit was performed in the session, and by the model, that wrote the code. Every gate was rerun and every changed file re-read, but a reviewer who made the change is less likely to see its blind spots | A review in a fresh session or by the human, or acceptance of this self-check | Open |
| F5 | LOW | AC4 | The in-process cache prunes expired entries only on a write, never on a read, and has no size bound. It is used only off Vercel (the in-process store is refused on Vercel), so it is bounded in practice, but no test covers the pruning | Optional: a pruning test, or a note in the runbook that the in-process cache is for local use | Open |
| F6 | LOW | AC13 | The ADRs (0057 cache design, 0058 dependency rule for `@vercel/analytics`), the `web-chat.md` amendments (WEBCHAT-8 `cache` field, a cache requirement), `CHANGELOG.md` and `apps/web/README.md` are not written yet | The post-audit documentation step | Open (expected) |

## Notes (not findings)
- A cache write is awaited before the response, so a store that is slow adds up to its 1 s timeout to a live answer. This is the plan's stated trade-off (the function may be frozen after the response). Normal cost is one fast call; the open WEBCHAT-R3 (function duration versus `maxDuration` 40) is not made worse in any way the plan did not anticipate.
- A hit costs two store calls (read and burst check), a miss three (read, full check, write). Chat is capped at 50 live turns a day, so the extra commands are small, but the Upstash plan quota is worth a look (runbook mentions it).
- A concurrent duplicate miss calls the backend twice and the second write overwrites the first, as the intent allows.
- The log records `cache: "hit"` for a lookup hit even when the burst check then rejects the request (outcome `rate_limited`); a hit-rate computed from `outcome: "ok"` lines is unaffected.
- A shared answer is served to every visitor, so a wrong answer persists for up to the TTL; the off switch (`CHAT_CACHE_TTL_S=0`) and the prefix-delete runbook step are the mitigations the intent names.
- Human steps stay open: enable Web Analytics (H1), optionally set the TTL and confirm `VERCEL=1` (H2), and the live check after deploy (H3). The Upstash database already exists and accepts the limiter's `EVAL`, as the user reported the chat works live; `GET`/`SET ... EX` are the standard commands of the same REST API but are not yet exercised against it.

## Audit log
| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-11-18 | APPROVED WITH RESERVATIONS | AC1 to AC12 and AC14 pass; AC13 pending the documentation step. All gates rerun green (lint 0 errors, typecheck, 496 unit, env-unset 496, build, 64 e2e, guard diff). F2 to F4 are MEDIUM and non-blocking; F4 records that this was a self-audit |

## Final verdict

APPROVED WITH RESERVATIONS (round 1, 2026-11-18)

**Summary**: Every acceptance criterion except the pending docs (AC13) is met and tested, every binding constraint holds, and all gates rerun green (496 unit, 64 e2e, lint, typecheck, build, the frozen-file diff). Approval carries reservations: red evidence is missing for part of the new tests (F2), the per-turn hook and CI left no evidence (F3), and this audit was performed by the same session and model that wrote the code (F4).

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- F2 (MEDIUM): accept or close the missing red evidence for the handler cache cases, the conventions guards and the e2e file.
- F3 (MEDIUM): get a green `harny-feedback-apps-web.yml` run on the PR and look for the `N of M command(s) ran` line.
- F4 (MEDIUM): consider a fresh-session or human review before merge.

**Recommendations** (nice to have):
- F1: state the AC8 reading (digest allowed in store keys) in the new ADR.
- F5: add a pruning test or a runbook note that the in-process cache is for local use.
- After deploy, run the human live check (H3) and confirm `GET`/`SET ... EX` against the real Upstash database.

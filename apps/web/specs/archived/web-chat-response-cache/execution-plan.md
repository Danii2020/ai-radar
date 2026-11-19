# Execution Plan: Web Chat Response Cache

## Guidance consulted
- `apps/web/AGENTS.md` (WEB-1, barrel-only imports, the dependency rule, server-only config, tests
  follow `high-value-tests`, deployment is human-run) and `apps/web/.claude/memory/web-chat-ui-handoff.md`.
- `specs/current/_index.md` and `specs/current/web-chat.md` (WEBCHAT-7 to WEBCHAT-9, invariants 2 and
  3, ADR 0033 logging contract, ADR 0037 as the precedent for amending the dependency rule).
- `specs/web-chat-visitor-rate-limit/` (intent revision 2, execution plan, audit rounds 1 and 2):
  the code this feature extends. It is committed (`c1c4c96`) but not yet archived.
- Code read: `features/chat/api/handle-chat-request.ts`, `rate-limit.ts`, `rate-limit-config.ts`,
  `visitor.ts`, `backend.ts`, `types.ts`, `features/chat/lib/chat-response.ts`,
  `features/chat/conventions.test.ts`, `handle-chat-request.test.ts`, `app/layout.tsx`,
  `e2e/stub/feed-api-stub.mjs`, `e2e/stub/launch-apps.mjs`, `e2e/chat-rate-limit.e2e.ts`.
- Context7 (Vercel docs, `/websites/vercel`): `Analytics` from `@vercel/analytics/next` in the root
  layout; development or test mode enables debug logging, production loads
  `/_vercel/insights/script.js`. `npm view @vercel/analytics`: version 2.0.1, peers satisfied.

## Ownership
- `features/chat/api/`: a new `response-cache.ts` (normalization, digest, config, read and write
  against the same two store kinds as the limiter), a burst-only mode added to `rate-limit.ts`, and
  the cache step inside `handle-chat-request.ts`.
- `app/layout.tsx`: renders `Analytics`. `package.json` / `package-lock.json`: one dependency.
- `e2e/stub/`: a request counter and a fifth app instance for the cache; existing instances turn the
  cache off.
- Docs: `AGENTS.md`, `.env.example`, the runbook, two ADRs, `specs/current/web-chat.md`.
- Affected `specs/current` capabilities: `web-chat` (WEBCHAT-8 logging field, new cache requirement,
  dependency list). `web-feed` is untouched.

## Binding constraints
- Precondition: `web-chat-visitor-rate-limit` is documented and archived (its open task O9 and AC15,
  run through `harny-document` and `harny-sync`) before this feature's executor starts, so
  `specs/current/web-chat.md` records the limiter this feature amends (source: intent Q3). Until
  then the code on `main` is the baseline, and this plan's ADRs take the next free numbers after the
  limiter's (0049 and up).
- No new dependency for the cache; the store is reached with platform `fetch`, one call per read and
  one per write, 1 second timeout each, never retried (source: intent Constraints, ADR 0032).
- Exactly one new dependency, `@vercel/analytics`, pinned exactly with `npm i --save-exact
  @vercel/analytics@2.0.1`, imported only by `app/layout.tsx` through `@vercel/analytics/next`, never
  from `features/` (source: AGENTS.md dependency rule, intent AC14).
- Order in `handleChatRequest`: body, question, history validation; `CHAT_API_*` check; limiter
  configuration check; cache read (first turns only); on a hit the burst-only check, then respond;
  on a miss the full limiter check, the one backend call, then the cache write (source: AC5, AC6).
- The limiter's full check, its Lua script, its response contract and its fail-closed behaviour are
  unchanged; the burst-only mode is an addition (source: AC5, AC12).
- The cache never produces an error response: every cache failure is a miss. Only the limiter and
  the existing backend outcomes can fail a request (source: AC7).
- The store key holds an HMAC-SHA-256 digest of the normalized question, using
  `CHAT_RATE_LIMIT_SALT` (or the limiter's per-process salt when none is set) under a distinct
  prefix. Logs, error bodies and keys never hold the question, answer, sources or digest (source:
  AC8, AC9). The `cache` log value is one of `hit`, `miss`, `skip`, `error`, and is absent when the
  cache is off.
- Stored value is `{answer, sources}` only, written once with its expiry; a read that returns a value
  failing `isChatResponse` is treated as a failed read (source: AC4, AC7).
- `CHAT_CACHE_TTL_S` is read per request, only inside `features/chat/api/`, and the conventions test
  names it among the env variables confined to `api/` (source: AGENTS.md, intent Constraints).
- Barrel exports stay `ChatWidget` and `handleChatRequest`; `app/api/chat/route.ts` and `components/`
  / `lib/` are unchanged; the 17 `e2e/__baseline__` scenarios are not regenerated (source: AC10, AC12).
- `Analytics` renders only when `process.env.VERCEL` is set, so local, unit and e2e runs never load a
  Vercel script (source: AC14; Vercel's component loads a script even in `next start`).
- No `NEXT_PUBLIC_` variable (WEB-1). Deployment, enabling Web Analytics in the dashboard, and live
  checks are human-only steps (source: ADR 0007, WEB-11).

## Proposed approach
Revisable by the executor if it records why.
- Decision: one new module `api/response-cache.ts` that exposes read, write and config, next to the
  limiter rather than inside it — rationale: the limiter's module is audited and its keys, script
  and failure mode differ (closed versus open); rejected: folding both into one store module, which
  would couple a fail-open feature to a fail-closed one.
- Decision: `handle()` reads the limiter configuration once and passes the result to both the cache
  and the limiter, and `checkRateLimit` gains a mode (`full` or `burst`) — rationale: AC6 needs the
  limiter configuration checked before any cache call, and the store selection (memory or Upstash,
  URL, token, salt) is the limiter's; rejected: a second copy of that parsing, which could disagree
  with the limiter about the store.
- Decision: burst-only mode is a second small Lua script (read the burst counter, refuse at the
  limit, else INCR with expiry set on creation) and a matching branch in the in-process store —
  rationale: keeps the full script and its audited tests untouched and the check atomic; rejected:
  running the full script with the daily and global limits set out of reach, because it would still
  increment those counters.
- Decision: a read is `POST <REST URL>` with `["GET", key]`, a write is `["SET", key, json, "EX",
  ttl]`, both with `Authorization: Bearer <token>` and an `AbortController` at 1 second, mirroring
  `upstashCheck` — rationale: same pattern, no dependency; rejected: `@upstash/redis` (needs its own
  ADR) and pipelining the read with the limiter check in one `EVAL` (fewer round trips, but it ties
  the cache to the limiter script).
- Decision: the in-process store for the cache is its own `Map` with expiry and a fake-clock-friendly
  `Date.now()`, separate from the limiter's — rationale: no coupling, same semantics as Redis `EX`.
- Decision: the cache write is awaited before the response is returned — rationale: a serverless
  function can be frozen once the response is sent, so a fire-and-forget write may never happen; the
  normal cost is one fast call, the worst case is the 1 second timeout; rejected: Next's `after()`,
  which would tie the framework-agnostic handler to the Next runtime and complicate its tests.
- Decision: `CHAT_CACHE_TTL_S=0` is off, an invalid value bypasses the cache for that request and
  logs `cache: "error"` plus the variable name — rationale: AC4, AC7, AC9; it also gives operators
  a kill switch without a redeploy of code.
- Decision: `Analytics` is rendered as `{process.env.VERCEL ? <Analytics /> : null}` in
  `app/layout.tsx` — rationale: the layout is a Server Component, Vercel sets `VERCEL` at build and
  runtime, and it keeps e2e free of a 404 for `/_vercel/insights/script.js` (the e2e specs assert an
  empty console); rejected: the `mode` prop, because development mode loads a script from
  `cdn.vercel-insights.com`, which breaks the offline rule, and a `NEXT_PUBLIC_` flag, which WEB-1 forbids.
- Decision: e2e gets a fifth `next start` instance (`cache`, port 3103, cache on at 3600 s, global
  ceiling 1, burst out of reach) and the other four run with `CHAT_CACHE_TTL_S=0`; the stub counts
  chat requests per prefix and exposes the count — rationale: the existing suites resend identical
  questions and some assert per-request stub behaviour (the `slow` and error questions), so they must
  not see cached answers; the counter is the only way to prove "zero backend calls" end to end.
- Decision: unit tests use a distinct question per case, fake timers for expiry and stubbed
  `fetch` for the Upstash shape, and the existing handler suite sets `CHAT_CACHE_TTL_S=0` in its
  `beforeEach` the way it already sets the limiter limits — rationale: no test-only exports in the
  module.

## Consumers and migration
- `handle-chat-request.test.ts`: add `CHAT_CACHE_TTL_S=0` to `beforeEach`; add the new cache cases
  in a separate `describe` that turns it on.
- `rate-limit.test.ts`: untouched cases keep passing; add burst-only cases beside them.
- `conventions.test.ts`: add `CHAT_CACHE_TTL_S` to the env names confined to `api/`, and a guard that
  `@vercel/analytics` is imported only by `app/layout.tsx`.
- `e2e/stub/launch-apps.mjs`: cache off on the four existing instances, the new instance, its log
  file and its readiness handling; `e2e/stub/feed-api-stub.mjs`: the per-prefix counter. Existing
  e2e suites are not edited.
- `AGENTS.md`: config list, the sanctioned dependency list, the Components note for `response-cache.ts`.
  `.env.example`: `CHAT_CACHE_TTL_S` placeholder. Runbook: clearing the cache by prefix, enabling
  Web Analytics, the optional TTL override.
- Docs step (after the audit): ADR for the cache design, ADR amending the dependency rule for
  `@vercel/analytics`, `web-chat` capability amendments (WEBCHAT-8 `cache` field, a new cache
  requirement), `_index.md` regenerated by `harny-sync`.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A bad or outdated answer is served to everyone until the TTL ends | Med | Med | Six hour default, off switch, runbook step to delete by `chat-cache:` prefix; only successful, validated answers are stored |
| Upstash is slow, so a hit costs two store calls and a miss three, each up to 1 second | Low | Med | 1 second timeouts, cache fails open; the limiter's 1 second is unchanged; adds to the open WEBCHAT-R3 duration question |
| Upstash plan quota is consumed faster (2 to 3 commands per chat request instead of 1) | Low | Low | Chat is capped at 50 admitted turns a day globally; hits only add burst checks; check the plan's quota in the runbook |
| Two identical misses at once both call the backend | Med | Low | Accepted and out of scope (intent); the second write overwrites the first |
| The hit path skips daily and global counters, so a cached question can be asked without bound within the burst limit | Med | Low | Intended (AC5): hits cost nothing upstream; burst limit and the optional Vercel WAF rule bound the rate |
| `process.env.VERCEL` stops being set, silently dropping analytics | Low | Low | Documented in the runbook; a missing dashboard entry after deploy is the human's live check |
| The limiter module change regresses the audited full check | Low | High | Full script and its tests are not edited; burst mode is additive and has its own tests; the whole existing suite and e2e rate-limit spec must stay green |
| Normalization too weak or too strong (wrong merge or missed hit) | Low | Low | Rule is minimal and pinned by AC2 examples; the `cache` log field shows the real hit rate |

## Validation
One row per AC. Unit tests are vitest in `features/chat/api/`; e2e is Playwright against the local
stub. All commands run from `apps/web/`.

| AC | Demonstrated by | Tests to write | Tier | Framework | Setup | Focused command | Broader command | Cwd |
|---|---|---|---|---|---|---|---|---|
| AC1 | Second identical first-turn question returns the stored answer and sources with 0 backend calls | handler: miss then hit, same body, backend `fetch` count 1; e2e: stub counter stays 1 after the second request from another visitor | unit + e2e | vitest, Playwright | none; e2e adds instance 3103 and the stub counter | `npx vitest run features/chat/api/handle-chat-request.test.ts` | `npm test && npm run test:e2e` | apps/web |
| AC2 | Normalization pins which spellings share an entry | table: `"  What is   MCP? "` and `"what is mcp?"` share a key; no question mark does not; the key never contains the text | unit | vitest | none | `npx vitest run features/chat/api/response-cache.test.ts` | `npm test` | apps/web |
| AC3 | A non-empty history never reads or writes the cache | handler: with one prior turn, store `fetch` called 0 times and backend called as before; log `cache: "skip"` | unit | vitest | none | `npx vitest run features/chat/api/handle-chat-request.test.ts` | `npm test` | apps/web |
| AC4 | Only validated successes are stored, with an expiry, and expire | write shape `SET key json EX ttl`; backend 502/504/429/400 store nothing and the next call goes to the backend; fake timers: after the TTL the entry is a miss and is refreshed; default 21600 and range 60 to 86400, `0` off | unit | vitest | fake timers | `npx vitest run features/chat/api/response-cache.test.ts` | `npm test` | apps/web |
| AC5 | A hit counts burst only; a miss counts all three; a burst-limited visitor is limited even on a hit | rate-limit: burst-only increments only the burst counter, refuses at the limit, memory and Upstash script shape; handler: hit leaves daily and global counters unchanged, burst-limited hit gets 429 with `Retry-After`; e2e on 3103: ceiling 1, visitor A live, visitor B cached question 200, B uncached question 429 | unit + e2e | vitest, Playwright | none | `npx vitest run features/chat/api/rate-limit.test.ts` | `npm test && npm run test:e2e` | apps/web |
| AC6 | Validation and configuration run first; limiter store failure still gives 503 | handler: invalid body, `missing_config` and invalid limiter config make 0 store calls; limiter store down on a hit and on a miss gives 503 `unavailable`, no backend call | unit | vitest | none | `npx vitest run features/chat/api/handle-chat-request.test.ts` | `npm test` | apps/web |
| AC7 | Every cache failure is a miss, never an error | handler: read network error, non-2xx, malformed JSON, `error` field, value failing `isChatResponse`, abort at 1 second (real timer) and write failure each give 200 live with `cache: "error"`; invalid `CHAT_CACHE_TTL_S` names the variable, never the value | unit | vitest | real timer for the abort case | `npx vitest run features/chat/api/handle-chat-request.test.ts` | `npm test` | apps/web |
| AC8 | No question, answer, digest or visitor in keys, logs or bodies; digest keyed and domain-separated | handler: marker strings absent from console output and from every store request key; key differs when the salt changes and differs from the limiter's digest of the same text | unit | vitest | none | `npx vitest run features/chat/api/response-cache.test.ts` | `npm test` | apps/web |
| AC9 | One line per request with the four `cache` values, absent when off | handler: exact key sets for hit, miss, skip, error and off; outcome and log level unchanged | unit | vitest | none | `npx vitest run features/chat/api/handle-chat-request.test.ts` | `npm test` | apps/web |
| AC10 | A hit is indistinguishable from a live answer | handler: same status, body and headers for hit and miss; e2e on 3103: hit response equals the first response, no new header | unit + e2e | vitest, Playwright | none | `npx vitest run features/chat/api/handle-chat-request.test.ts` | `npm test && npm run test:e2e` | apps/web |
| AC11 | Offline: in-process store off Vercel, nothing new to set | handler suite runs with no `KV_*` or `UPSTASH_*` variable and no network; `npm run test:e2e` passes with only the launcher's own variables | unit + e2e | vitest, Playwright | none | `env -u VERCEL -u KV_REST_API_URL -u UPSTASH_REDIS_REST_URL npm test` | `npm run test:e2e` | apps/web |
| AC12 | A non-hit behaves as today | all existing handler, rate-limit, send-turn, widget and conventions tests unchanged or minimally migrated; barrel still two exports; `git diff --exit-code -- app/api/chat/route.ts features/chat/index.ts e2e/__baseline__`; 17 baseline scenarios green | unit + e2e | vitest, Playwright | none | `npm test` | `npm test && npm run lint && npm run typecheck && npm run build && npm run test:e2e` | apps/web |
| AC13 | The docs and ADRs exist and name what the AC lists | auditor checks `.env.example` and `AGENTS.md` name `CHAT_CACHE_TTL_S` and `@vercel/analytics`, the runbook has the prefix-delete note, two ADRs are registered, WEBCHAT-8 amended | review (auditor) | grep and read | none | `grep -n "CHAT_CACHE_TTL_S" .env.example AGENTS.md` | `grep -rn "chat-cache:" ../../docs/runbooks.md` | apps/web |
| AC14 | Analytics renders only on Vercel; the dependency is pinned; offline runs stay clean | unit: `RootLayout` with the package mocked contains `Analytics` when `VERCEL` is set and not when unset; conventions guard: the package imported only by `app/layout.tsx`; existing e2e "clean console" and "127.0.0.1 only" assertions stay green; `package.json` shows `"@vercel/analytics": "2.0.1"` | unit + e2e | vitest, Playwright | `npm i --save-exact @vercel/analytics@2.0.1` | `npx vitest run app/layout.test.tsx features/chat/conventions.test.ts` | `npm test && npm run test:e2e` | apps/web |

## Revision log
- Revision 1 (2026-11-17): initial plan for intent revision 3. Intent revision 2 was approved with the
  default answers to Q1 to Q3; revision 3 (the `CHAT_CACHE_TTL_S=0` off switch, `cache` field absent
  when off) was added while planning and is pending the human's re-approval. The plan depends on it
  (e2e isolation, operator kill switch).
- Revision 1 approved by Daniel Erazo on 2026-11-18, together with intent revision 3.

# Intent: Web Chat Response Cache

Revision: 3
Shipped: 2026-11-18
Approval: Approved revision 3 by Daniel Erazo on 2026-11-18 (revision 2 was approved on 2026-11-17 with the default answers to Q1 to Q3; revision 3 adds the `CHAT_CACHE_TTL_S=0` off switch).

## Outcome
`POST /api/chat` remembers the answer to a first-turn question for a few hours, in the Upstash
Redis store the rate limiter already uses. The same question asked again (the empty-state
suggested prompts are the likely repeats) is answered from that store with no call to the chat
API, so it costs nothing upstream, answers in tens of milliseconds, and does not use up the
global daily ceiling. Nothing changes for the visitor except speed, and a cache problem can
never turn into an error for them.

## Acceptance criteria
- **AC1** Hit. A first-turn question whose normalized form (AC2) was answered successfully
  within the cache lifetime (AC4) gets 200 with exactly the same `answer` and `sources` as the
  original answer, and the route makes zero calls to the chat API.
  Example: "What are the top AI stories today?" answered live, then sent again 10 minutes later
  from any visitor -> same body, backend `fetch` called 0 times the second time.
- **AC2** Normalization. The cache key is derived from the question after trimming, collapsing
  every run of whitespace to one space, and lower-casing. Nothing else is changed (punctuation
  and wording count), so only trivially different spellings share an entry.
  Example: `"  What is   MCP? "` and `"what is mcp?"` share an entry; `"what is mcp"` (no
  question mark) does not.
- **AC3** First turns only. A request whose `history` is empty or absent looks the cache up and
  may store its answer. A request with a non-empty history never reads or writes the cache and
  behaves exactly as today.
  Example: the same question sent with one prior turn -> live backend call, no cache store call.
- **AC4** What is stored. Only a successful backend answer (status 200 with a string `answer` and
  an array `sources`) is stored, as `{answer, sources}`, in a single write that also sets the
  expiry. Every error outcome (`busy`, `timeout`, `upstream_failure`, `unavailable`,
  `rate_limited`, `invalid_request`, `internal_error`) is never stored. The entry expires after
  `CHAT_CACHE_TTL_S` seconds (default 21600, six hours; `0` turns the cache off, otherwise a whole number from 60 to 86400). After
  expiry the same question is a miss and a live call refreshes the entry.
  Example: the backend returns 502 -> nothing stored, the next identical question calls the
  backend again.
- **AC5** Limiter interaction. A hit counts only against the burst limit. It does not count toward
  the per-visitor daily cap or the global daily ceiling. A miss counts against all three exactly as
  today, and is stored only after the backend answers. A visitor already at their burst limit gets
  429 `rate_limited` even for a question that is cached, with the existing body and `Retry-After`.
  Example: global ceiling 1, one live turn admitted; a different visitor then asks the cached
  question -> 200 from the cache; asks anything uncached -> 429 `rate_limited`.
- **AC6** Order. Body, question and history validation, and the `CHAT_API_*` configuration check,
  run first and unchanged. Requests failing them make no cache call and cost nothing, and the
  limiter's configuration is checked before any cache call. Fail-closed rules of the limiter are
  untouched: a limiter store failure on a hit or a miss still gives 503 `unavailable` and no
  backend call (existing AC9).
  Example: invalid body -> 400 `invalid_request`, cache store called 0 times.
- **AC7** Fail open. If the cache read or write fails (network error, non-success reply, malformed
  reply, or no reply within 1 second), the request proceeds as a miss and the visitor gets the
  live answer; the cache never produces an error response. A set but invalid cache setting
  (`CHAT_CACHE_TTL_S` not a whole number in range) turns the cache off for that request, the
  request proceeds uncached, and the log names the variable, never its value. A failed write after
  a live answer does not delay the answer beyond the 1 second write timeout and does not change the
  response.
  Example: the store host refuses connections -> 200 with a live answer, log shows `cache: "error"`.
- **AC8** Privacy. The store key holds only a keyed one-way digest of the normalized question
  (HMAC-SHA-256 with the existing server-only `CHAT_RATE_LIMIT_SALT`, under a prefix distinct from
  the limiter's, so it cannot collide with a limiter digest). The stored value is the public
  curated answer and its source cards, never the question, a visitor, an IP or a credential.
  No log line, error body or store key holds the question, the answer, the sources or the digest.
  Example: a question containing "zq-marker" -> that string appears in no console output and in no
  key sent to the store.
- **AC9** Observability. The one `chat_request` line per request gains a text-free `cache` field:
  `hit`, `miss`, `skip` (non-empty history, so the cache was not used), or `error` (a read or
  write failed or the setting was invalid). When the cache is off (`CHAT_CACHE_TTL_S=0`) the field
  is absent. Outcome and level are unchanged, so a hit is outcome
  `ok`. The hit rate comes from these lines; there is no new metric pipeline.
  Example: second identical first-turn question -> `{"event":"chat_request","outcome":"ok","cache":"hit",...}`.
- **AC10** Response contract. A cached answer is indistinguishable from a live one: same status,
  same body shape, the existing `content-type: application/json` and `cache-control: no-store`
  headers, and no new header or field. The widget, `send-turn` and every UI state are unchanged.
- **AC11** Local and e2e runs need no new service. Off Vercel the cache uses the same in-process
  store selection as the limiter, so `npm run dev`, `npm test` and `npm run test:e2e` need no new
  variable and make no network call. The e2e tier proves AC1, AC3 and AC5 offline by counting the
  stub's chat requests.
- **AC12** (compatibility) A request that is not a hit behaves exactly as today: the seven existing
  codes, history trimming, the one signed backend call per admitted miss, the limiter's counts and
  responses, the barrel's two exports, `app/api/chat/route.ts`, the 17 `e2e/__baseline__`
  scenarios (never regenerated), and every existing unit, component and e2e test, migrated only
  where a test needs the cache turned off or isolated.
- **AC13** (docs) The documentation step records an ADR for the cache design (next free number in
  `specs/current/_index.md`), amends WEBCHAT-8's logging contract for the `cache` field, adds
  `CHAT_CACHE_TTL_S` as a placeholder to `.env.example` and to `AGENTS.md`'s config list, and adds a
  runbook note on how to clear one cached answer or all of them (by the `chat-cache:` key prefix,
  never a database-wide flush, which would also reset the limiter's counters). It also records
  the `@vercel/analytics` dependency (AC14) in a second ADR that amends the dependency rule, and
  adds the package to `AGENTS.md`'s sanctioned list.
- **AC14** Vercel Web Analytics. The root layout (`app/layout.tsx`) renders the `Analytics`
  component from `@vercel/analytics/next`, so a deployed page records anonymous page views in
  Vercel's Web Analytics dashboard. Only page views are recorded: no custom event, no
  `beforeSend` data, and nothing from the chat (question, history, answer, sources) is ever passed
  to it. It adds no cookie and does not change any response, header or UI state. Local, unit and
  e2e runs stay offline: no request leaves the machine, and no existing test or `e2e/__baseline__`
  scenario changes because of it.
  Example: the deployed site's page view appears in the Vercel Analytics dashboard; `npm run
  test:e2e` makes no request to anything but the local stub and the local server.

## Scope
**In**
- A cache step inside `handleChatRequest` (`features/chat/api/`): question normalization, keyed
  digest, a read before the limiter's full check, a store after a live answer, configuration
  parsing, and the `cache` log field.
- A burst-only limiter check for hits, added to the existing limiter module without changing its
  full check.
- Reuse of the limiter's store selection and the same REST URL and token: Upstash through the
  platform `fetch` in production, the in-process store locally, tests and e2e.
- `@vercel/analytics` (page views only), added to `app/layout.tsx` and to `package.json`.
- Migration of handler, limiter and e2e tests; `.env.example`, `AGENTS.md`, runbook, ADR and the
  `web-chat` capability doc.

**Out**
- Any backend change: the chat Lambda, the agent, IAM, API Gateway and AWS-side caching.
- Semantic or embedding-similarity caching (a possible later version).
- Caching follow-up turns, or any answer produced with a history.
- Locking against duplicate concurrent misses (two identical questions in flight both call the
  backend; the second write just overwrites the first).
- Cache warming, cache-aware UI (no "cached" badge), and per-visitor cache entries.
- Custom Analytics events, Speed Insights, and any other analytics or tracking.
- Human-only steps: enabling Web Analytics for the project in the Vercel dashboard (Project ->
  Analytics -> Enable; the component sends nothing useful until it is on). The Upstash database and
  `CHAT_RATE_LIMIT_SALT` already exist; an optional `CHAT_CACHE_TTL_S` override in Vercel is a
  human step, and the live check after deploy stays human-run (ADR 0007, WEB-11).

## Constraints
- Stack and rules as in `AGENTS.md`: Next.js, React 19, TypeScript strict, npm only, WEB-1, the
  barrel exports exactly `ChatWidget` and `handleChatRequest`, `components/` and `lib/` import
  from `api/` only with `import type`, and the new variable is named only inside
  `features/chat/api/` (`features/chat/conventions.test.ts`).
- The cache adds no npm dependency. The store is reached with the platform `fetch`, one call per read and one
  per write, the pattern ADR 0032 and the rate-limit spec set. `@upstash/redis` would need its own
  ADR and a revision of this intent.
- The one new dependency is `@vercel/analytics`, pinned exactly (current release 2.0.1; peers
  `next >= 13`, `react ^18 || ^19`, both satisfied), and `AGENTS.md`'s dependency rule requires its
  own ADR, as ADR 0037 did for `react-markdown`. It is imported only by `app/layout.tsx`, through
  the Next.js entry `@vercel/analytics/next`, never from `features/`. Per Vercel's docs the
  component detects the environment itself (development or test enables debug logging, production
  loads Vercel's script from `/_vercel/insights/script.js`), so how e2e keeps AC14's offline
  guarantee is a plan decision.
- Builds on `web-chat-visitor-rate-limit`, which is implemented (commit `c1c4c96`, audited in
  rounds 1 and 2) but whose documentation step AC15 is still open, so it is not yet in
  `specs/current/web-chat.md`. This spec assumes that code as it stands and does not contradict
  its acceptance criteria; it reuses its salt, store selection and 1 second timeout, and changes
  its module only by adding a burst-only check (AC5).
- Logging contract (WEBCHAT-8, ADR 0033): one `chat_request` line, text-free. This adds one field.
- Invariant 2 of `web-chat` (one backend call per turn, no retry) holds: a miss still makes at
  most one backend call, and the cache never retries a store call.
- Cached answers can lag newly curated cards by up to the TTL. That is accepted and bounded by
  `CHAT_CACHE_TTL_S`; curation runs once a day.
- The realistic hit rate is modest: free-text questions rarely repeat, while the empty-state
  suggestions will. The `cache` log field exists so this can be measured before more is invested.
- Deployment and provisioning are human-run; agents stop at local verification.

## Open questions
- None. Resolved by the human's approval of revision 2 with the recommended defaults:
  - **Q1, resolved**: a hit still counts against the burst limit (AC5).
  - **Q2, resolved**: the default lifetime is six hours (AC4).
  - **Q3, resolved**: `web-chat-visitor-rate-limit` is documented and archived first, so this spec
    amends a recorded capability. The plan makes that a precondition.

## Revision history
- Revision 3 (2026-11-17): found while planning, approved 2026-11-18. `CHAT_CACHE_TTL_S=0` turns the
  cache off (AC4) and the `cache` log field is then absent (AC9). Without it the existing e2e suites
  (which resend the same questions and expect fresh stub answers) and an operator have no way to
  switch the cache off. Nothing else changed. Q1 to Q3 recorded as resolved.
- Revision 2 (2026-11-17): added AC14 (`@vercel/analytics`, page views only) with its scope,
  human step and dependency constraint, and extended AC13 to cover its ADR. Not related to the
  cache; included in this spec at the human's request.
- Revision 1 (2026-11-16): initial draft. Follows the cost and latency discussion about repeated
  chat questions; the design, alternatives (DynamoDB or AWS-side caching, API Gateway or CloudFront
  caching, Vercel Data Cache, semantic cache) and the choice of Upstash in the Vercel route are
  from the same conversation.

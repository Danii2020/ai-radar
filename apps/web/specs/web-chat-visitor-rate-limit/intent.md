# Intent: Web Chat Visitor Rate Limit

Revision: 2
Approval: Approved.

## Outcome
`POST /api/chat` gets a per-visitor limit and a global daily ceiling, both checked before any
backend call. One visitor can then no longer use up the chat API's shared throttle (5 req/s,
burst 10, global), and nobody can run up the Bedrock bill without bound. Claude on Bedrock is
billed through AWS Marketplace, outside the $500 credits, at roughly $0.015 a turn (up to about
$0.03 with a long history), so this is real out-of-pocket money. A limited visitor sees a clear,
friendly message, keeps the question, and costs nothing. This supersedes ADR 0035 and closes
WEBCHAT-R1.

## Acceptance criteria
- **AC1** Burst limit per visitor. A visitor gets at most `CHAT_RATE_LIMIT_BURST` (default 5)
  admitted turns in each fixed window of `CHAT_RATE_LIMIT_BURST_WINDOW_S` seconds (default 60,
  aligned to multiples of the window since the epoch). The next valid request in that window
  gets 429 `{"error":"rate_limited"}`, and the first request in the next window is admitted.
  Example: 6 valid requests from one IP in one window -> 5 answers, then 429 `rate_limited`.
- **AC2** Daily cap per visitor. A visitor gets at most `CHAT_RATE_LIMIT_DAILY` (default 20)
  admitted turns per UTC day. The next one gets 429 `rate_limited` until 00:00 UTC.
  Example: a 21st valid request on the same UTC day, burst window clear -> 429 `rate_limited`.
- **AC3** Global daily ceiling. All visitors together get at most `CHAT_RATE_LIMIT_GLOBAL_DAILY`
  (default 50, the human's decision on Q1) admitted turns per UTC day, the hard cost ceiling
  (about $0.75 to $1.50 a day at the default, or about $22 to $45 a month if it is hit every day).
  Past it, every visitor gets 429 `rate_limited` until 00:00 UTC.
  Example: ceiling 3, three visitors each admitted once -> a fourth visitor's first request is 429.
- **AC4** One visitor does not block another, and a rejection is free. A visitor at a burst or
  daily limit does not change the answer for a different visitor. A rejected request (rate limit,
  validation or configuration) uses up none of any allowance and does not count toward the
  global ceiling. An admitted turn counts even if the backend then fails.
  Example: visitor A gets 429; visitor B's next request is admitted. A then sends 50 more
  requests in the same window; B is still admitted, and the global count rose only by A's admitted turns.
- **AC5** A limited request costs nothing upstream. The limit check runs after the existing
  body, question and history validation and after the `CHAT_API_*` configuration check, and
  before the one signed backend call. A 429 `rate_limited` response makes zero calls to the chat
  API. A request that fails validation still gets 400 `invalid_request` and is never counted.
  Example: a limited visitor's request -> 429, backend `fetch` called 0 times.
- **AC6** Response contract. A limited request gets status 429, a body of exactly
  `{"error":"rate_limited"}`, the existing `content-type: application/json` and
  `cache-control: no-store` headers, and `Retry-After: <s>`. `<s>` is a whole number of seconds,
  at least 1, until the window that blocked the request resets (end of the burst window, or the
  next 00:00 UTC for the daily cap and the global ceiling). The body never says which limit fired.
  `rate_limited` is a seventh fixed code next to the existing six. A backend 429 still maps to
  `busy` as before.
- **AC7** Visitor identity. The visitor key comes from the client IP in the first present header
  of `x-vercel-forwarded-for`, `x-real-ip` and `x-forwarded-for` (first comma-separated entry,
  trimmed and parsed as an IP). An IPv4 address is used whole. An IPv6 address is reduced to its
  /64 prefix, so one host or home network cannot dodge the limit by rotating addresses inside it.
  An absent or unparseable value falls into one shared `unknown` bucket. On Vercel this does not
  happen, because Vercel sets these headers itself. No cookie, token or client-supplied id is
  used.
  Example: `2001:db8:1:2::a` and `2001:db8:1:2::b` share a bucket; `2001:db8:1:3::a` does not.
- **AC8** No address or text is kept or logged. The store holds only a keyed one-way digest of
  the visitor key (HMAC-SHA-256 with the server-only secret `CHAT_RATE_LIMIT_SALT`), never a raw
  IP. Every stored entry expires on its own: a burst entry within two burst windows, and a daily
  entry within 48 hours. No log line, store key or error body holds the IP, the digest, the
  question, the history or the answer.
  Example: a request from `203.0.113.77` asking "zq-marker" -> neither string appears in any
  console output or in any key or value sent to the store.
- **AC9** Fail closed (the human's decision on Q3). If the counter store fails (network error,
  non-success reply, malformed reply, or no reply within 1 second), the route answers 503
  `{"error":"unavailable"}`, makes no backend call, and logs outcome `limiter_unavailable`. A store
  outage never lets a turn through unmetered. The visitor sees the friendly `unavailable` state of
  AC12, never anything about the limiter.
  Example: the store host refuses connections -> 503 `unavailable`, backend `fetch` called 0 times.
- **AC10** Configuration is checked on every request and fails safe. The limiter reads its
  server-only settings per request inside `features/chat/api/`. A limit variable that is set but
  is not a whole number in its allowed range, a missing store setting the selected store needs, a
  salt shorter than 32 characters, or the in-memory store selected on Vercel all give 503
  `unavailable`, no backend call, and a log line with outcome `limiter_config_invalid` and
  `variable` naming the offending variable, never its value. Unset limit variables use the defaults.
  Example: `CHAT_RATE_LIMIT_DAILY=abc` -> 503, the log names `CHAT_RATE_LIMIT_DAILY` and not `abc`.
- **AC11** Text-free observability. Each request still writes exactly one `chat_request` JSON
  line. A limited request logs outcome `rate_limited` with a `limit` field of `burst`, `daily` or
  `global`, at the same level as other non-ok outcomes. Counts come from these lines; there is no
  new metric pipeline.
- **AC12** UI states for the two outcomes this feature adds.
  - `rate_limited` (429): the panel shows its own alert with exactly "You've reached the chat
    limit for now. Please try again later.", distinct from the `busy` copy. A 429 whose body is
    not one of the known codes (for example a platform firewall page) also shows this state.
  - `unavailable` (503), which now also covers a store outage (AC9) and an invalid limiter
    configuration (AC10): the panel shows exactly the existing copy "Chat is unavailable at the
    moment. Try again later." It already meets this criterion (friendly, distinct from every other
    code, and naming no internal part), so it is kept verbatim and the existing tests stay valid.
  - In both states the alert text holds no status code, header value, URL, error code name,
    backend text, or mention of a limiter, store, Redis, Upstash, salt or configuration (checked
    case-insensitively). The conversation and the typed question are kept, and Retry is
    available, as for every other error.
  Example: route returns 429 `rate_limited` -> alert with that copy, input still holds the
  question; route returns 503 `unavailable` because the store is down -> "Chat is unavailable at
  the moment. Try again later.", input still holds the question, Retry shown.
- **AC13** Local and e2e runs need no new service. Off Vercel, the limiter defaults to an
  in-process store with a per-process random salt, so `npm run dev`, `npm test` and
  `npm run test:e2e` work with no new environment variable and no network call. The e2e tier
  proves AC1, AC4 (two visitors told apart by `x-forwarded-for`), AC6 and AC12 offline against
  the existing stub.
- **AC14** (compatibility) A visitor under every limit sees exactly the current behaviour: the six
  existing codes, history trimming, the one signed backend call per admitted turn, the
  barrel's two exports, the 17 `e2e/__baseline__` scenarios (never regenerated), and every
  existing unit, component and e2e test, migrated only where a test needs more than the default
  burst.
- **AC15** (docs) The documentation step records a new ADR that supersedes ADR 0035, and one that
  amends ADR 0033's six codes to seven. It also closes WEBCHAT-R1 in `specs/current/web-chat.md`
  and `specs/current/_index.md`, adds the new server-only variables as placeholders to
  `.env.example` and to `AGENTS.md`'s config list, and adds a runbook for the human-only setup
  steps. The runbook states the defaults (5 per 60 s, 20 per visitor per day, 50 globally per
  day) and documents the optional Vercel Hobby WAF rate-limit rule on `/api/chat` as an outer
  flood shield (for example 30 requests per 60 s per IP). That rule is a human-only step, and the
  app does not depend on it: every acceptance criterion holds without it. ADR numbers start at
  0049.

## Scope
**In**
- A rate-limit step inside `handleChatRequest` (`features/chat/api/`): visitor key derivation,
  the three limits, the counter store, configuration parsing, and the new outcomes and log fields.
- One shared counter store for production: Upstash Redis, provisioned through the Vercel
  Marketplace (the human's decision on Q2) and reached over its REST API with the platform
  `fetch`, one call per check. An in-process store serves local runs, unit tests and e2e.
- The seventh error code `rate_limited`, its `Retry-After` header, and its UI copy
  (`api/types.ts`, `lib/send-turn.ts`, `components/chat-panel.tsx`).
- Extending `features/chat/conventions.test.ts` so the new secret variables, like `CHAT_API_*`,
  are named only inside `features/chat/api/`.
- Migration of existing handler, `sendTurn`, widget and e2e tests; an e2e server instance with
  tight limits; `.env.example`, `AGENTS.md`, README runbook, ADRs and capability docs.

**Out**
- Any backend change: the API Gateway throttle, the Lambda, the agent, IAM, and AWS Budgets.
- Accounts, sign-in, CAPTCHA or bot challenges, and cookie or session identity, which a visitor
  can clear at will and so is not a limit.
- Per-turn cost metering (tokens or dollars). Limits count turns, sized from the per-turn cost.
- Fixing WEBCHAT-R2 (live check with the real key) or WEBCHAT-R3 (function duration versus
  `maxDuration` 40). Both stay open; the new store call adds at most 1 s to a turn.
- Human-only steps: creating the Upstash database, connecting it to the Vercel project, setting
  `CHAT_RATE_LIMIT_SALT` and any limit overrides in Vercel, the optional Vercel Hobby WAF
  rate-limit rule on `/api/chat` (documented in the runbook, AC15), and the live check after
  deploy. These go in `tasks.md` as human steps, never executor tasks.

## Constraints
- Stack and rules as in `AGENTS.md`: Next.js 16.3.5, React 19, TypeScript strict, npm only,
  WEB-1, the barrel exports exactly `ChatWidget` and `handleChatRequest`, and `components/` and
  `lib/` import from `api/` only with `import type` (`features/chat/conventions.test.ts`).
- No new npm dependency. The store is reached with one `fetch` per check, the same pattern
  ADR 0032 set for SigV4. Using `@upstash/ratelimit` or `@upstash/redis` would need its own ADR
  (AGENTS.md dependency rule) and a revision of this intent.
- Logging contract (WEBCHAT-8, ADR 0033): the one `chat_request` line never holds the question,
  history, answer, credential, URL, backend detail, and now also no IP or visitor digest.
- Invariant 2 of `web-chat` (one call per turn, no retry) holds: the limiter never retries the
  store and never makes the backend call more than once.
- Invariant 3 of `web-chat` names `lib/`, `api/`, `index.ts` and the route as the stable shell.
  This feature changes `api/` and `lib/send-turn.ts` on purpose; the barrel and
  `app/api/chat/route.ts` stay unchanged.
- This amends WEBCHAT-8 (six codes become seven) and supersedes ADR 0035. It does not contradict
  any other current-truth statement found by the `harny-sync` lookup.
- Vercel facts relied on (docs checked 2026-11-04): Vercel overwrites `x-forwarded-for` and does
  not forward client-supplied IPs, and `x-real-ip` and `x-vercel-forwarded-for` are identical to
  it. Vercel WAF rate limiting on Hobby is one rule, fixed windows of 10 s to 10 min, per-region
  counters, so it cannot express a daily cap or a global ceiling alone.
- Off Vercel (`next start` locally), a client can set its own `x-forwarded-for`. That is accepted
  because the in-memory store is refused on Vercel and production runs only on Vercel.
- Deployment and all provisioning are human-run (ADR 0007, WEB-11); agents stop at local
  verification.

## Open questions
- None. Resolved by the human for revision 2:
  - **Q1 (defaults), resolved**: the global daily ceiling default is 50, not 100. The
    per-visitor defaults stay 5 per 60 s and 20 per UTC day.
  - **Q2 (store vendor), resolved**: Upstash Redis through the Vercel Marketplace is accepted,
    with no new npm dependency and one `fetch` per check.
  - **Q3 (fail closed), resolved**: accepted, on the condition that the visitor sees a friendly
    `unavailable` state that never mentions the limiter (AC9, AC12).
  - **Q4 (outer layer), resolved**: the optional Hobby WAF rate-limit rule goes into the runbook
    as a human-only step, and the app does not depend on it (AC15).

## Revision history
- Revision 2 (2026-11-05): applied the human's answers to Q1 to Q4. AC3 global default 100 -> 50
  with new cost figures. AC9 and AC12 pin the exact `unavailable` copy (kept verbatim from today)
  and ban limiter and store words from both new states. AC15 and Scope Out add the optional WAF
  rule as a human-only runbook step. Scope In and Constraints record Upstash as decided.
- Revision 1 (2026-11-04): initial draft. Follows up ADR 0035 ("revisit when the chat is publicly
  deployed") and WEBCHAT-R1.

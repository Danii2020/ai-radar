# ADR 0049: Limit chat turns per visitor and globally, counted in Upstash Redis over REST, failing closed

- **Status**: Accepted
- **Date**: 2026-11-18
- **Feature**: web-chat-visitor-rate-limit
- **Capability**: web-chat
- **Source**: execution-plan.md § Proposed approach (Decisions 1 to 5 and 8)
- **Trigger**: (a) a choice between named options; (c) supersedes ADR 0035; (d) accepts a known cost (a store outage blocks chat)

## Context
ADR 0035 shipped the chat route without a per-visitor limit and said to revisit it once the chat was public. The API's throttle (5 req/s, burst 10) is shared by everyone, and every admitted turn costs real money outside the AWS credits. Vercel runs many serverless instances, so a counter in process memory would not be shared. The human chose Upstash Redis from the Vercel Marketplace, and asked that a store failure never lets a turn through unmetered, provided the visitor sees a friendly message.

## Decision
`handleChatRequest` checks three counters after validation and the `CHAT_API_*` check and before the one backend call: a burst window per visitor (default 5 per 60 s, aligned to the epoch), a daily cap per visitor (20 per UTC day) and a global daily ceiling (50 per UTC day). The counters live in Upstash Redis, reached with the platform `fetch` over its REST API: one `EVAL` per check, whose Lua script reads all three counters and increments all three only if none is at its limit, setting each expiry when the key is created. The visitor is the client IP from `x-vercel-forwarded-for`, `x-real-ip` or `x-forwarded-for` (IPv6 reduced to its /64), stored only as an HMAC-SHA-256 digest keyed by `CHAT_RATE_LIMIT_SALT`. An in-process store with the same semantics serves local runs, unit tests and e2e. Any store failure (error, non-success or malformed reply, no reply in 1 s) or invalid limiter setting answers 503 `unavailable` with no backend call. An optional Vercel WAF rate-limit rule is documented as an outer shield; the app does not depend on it. Supersedes ADR 0035.

## Alternatives considered
| Option | Why not |
|---|---|
| Next.js middleware (`proxy.ts`) | Runs before validation, so it would count invalid requests and break the rule that a rejected request costs nothing. |
| `MULTI`/`EXEC` pipeline | Cannot make the increments conditional on the reads. |
| Three separate store calls | Not atomic and three round trips. |
| `@upstash/ratelimit` or `@upstash/redis` | A new dependency that needs its own ADR and an intent revision; one `fetch` does the job. |
| Fail open on a store outage | Lets turns through unmetered, which the global ceiling exists to prevent (the human's decision). |
| Vercel WAF rule alone | Hobby allows one rule with windows of 10 s to 10 min, so it cannot express a daily cap or a global ceiling. |
| Cookie or token identity | A visitor can clear it at will, so it is not a limit. |

## Consequences
**Positive**: one visitor can no longer use up the shared throttle, and the global ceiling bounds the daily Bedrock spend (about $22 to $45 a month if hit every day at the default 50 and the cost figures in the intent). No new dependency, and local work needs no service.
**Accepted costs**: an Upstash outage or misconfiguration blocks all chat (fail closed). Visitors behind one NAT share a bucket. Off Vercel a client can set its own `x-forwarded-for`, which is accepted because the in-process store is refused on Vercel. Audit reservations stay open: the Lua script's expire-on-create and the memory store's expiry have no test (F2), and the live check that the provisioned database accepts `EVAL` is a human step.

## Follow-ups
Human live check (six turns, then the limit message; digest keys only in the Upstash browser). Revisit the defaults against real traffic.

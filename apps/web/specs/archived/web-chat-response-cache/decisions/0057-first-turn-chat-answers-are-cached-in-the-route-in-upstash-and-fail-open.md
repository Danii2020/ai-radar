# ADR 0057: Cache first-turn chat answers in the route, in the limiter's Upstash store, failing open

- **Status**: Accepted
- **Date**: 2026-11-18
- **Feature**: web-chat-response-cache
- **Capability**: web-chat
- **Source**: execution-plan.md § Proposed approach (new module, burst-only mode, REST commands, awaited write, `CHAT_CACHE_TTL_S`)
- **Trigger**: (a) a choice between named options; (b) constrains future chat changes (a hit never reaches the backend); (d) accepts known costs (stale answers up to the TTL, two to three store calls per request)

## Context
Every chat turn is a Nova Pro call, and the visitor limit (ADR 0049) caps live turns at 50 a day. Free-text questions rarely repeat, but the suggested prompts in the empty state will. A repeated question can be answered without any backend call, which saves cost, answers in tens of milliseconds, and keeps popular questions from using the global ceiling.

## Decision
The `/api/chat` route caches the answer to a first-turn question (empty history) for `CHAT_CACHE_TTL_S` seconds (default 21600; `0` is off; otherwise 60 to 86400), in the same store the limiter uses: Upstash over its REST API with the platform `fetch` on Vercel, an in-process map off Vercel. The key is `chat-cache:{v1}:` plus an HMAC-SHA-256 of the normalized question (trimmed, whitespace collapsed, lower-cased) using the limiter's salt source and a domain tag; the value is `{answer, sources}`, written once with its expiry, only after a successful backend answer. The order is validation, `CHAT_API_*`, limiter configuration, cache read; a hit then takes a burst-only limiter check and is served, a miss takes the full check, the one backend call and an awaited write. A hit counts only against the burst limit. Every cache failure (error, timeout at 1 s, malformed or invalid value, invalid setting) is a miss: the cache never produces an error response, unlike the limiter, which fails closed. The log line gains a text-free `cache` field.

## Alternatives considered
| Option | Why not |
|---|---|
| DynamoDB with TTL in the chat Lambda | A hit still pays for API Gateway and the Lambda, and needs a backend spec, an IAM grant and a redeploy. |
| API Gateway or CloudFront caching | Not available for an HTTP API POST. |
| Vercel Data Cache | Per region and awkward for POST bodies. |
| Semantic (embedding-similarity) cache | Better hit rate, but needs a vector lookup and a similarity threshold; deferred as a possible later version. |
| `@upstash/redis` | A new dependency that needs its own ADR; two REST commands do the job. |
| Run the full limiter check on a hit | Spends the daily and global allowances on answers that cost nothing. |
| No limiter check on a hit | Lets one client hammer a cached question without bound. |
| Fire-and-forget write (Next `after()`) | A serverless function can be frozen once the response is sent, and it ties the handler to the Next runtime. |
| Fail closed like the limiter | The cache is not a safety control; a cache outage should not take chat down. |

## Consequences
**Positive**: repeated first-turn questions cost no backend call and answer fast, and popular questions no longer use the global ceiling. No new dependency and no backend change.
**Accepted costs**: an answer can lag newly curated cards by up to the TTL, and a wrong answer persists for that long (mitigated by the `0` off switch and the prefix-delete runbook step). A hit costs two store calls and a miss three. A slow store adds up to its 1 s timeout to a live answer because the write is awaited. Two identical concurrent misses both call the backend. The stored key is a digest of the question, so the intent's "no store key holds the digest" is read as "digest allowed in store keys, never in logs or bodies" (audit F1). The real Upstash database has not yet been exercised with `GET` and `SET ... EX`.

## Follow-ups
Human live check (ask a suggested prompt twice; look for `cache: "miss"` then `"hit"`). Measure the hit rate from the logs before investing in a semantic cache.

# ADR 0027: The unauthenticated chat endpoint is guarded by throttling and the budget alert alone

- **Status**: Superseded by ADR 0028
- **Date**: 2026-10-21
- **Feature**: chat-api
- **Capability**: chat-api
- **Source**: intent.md § Outcome and § Scope (Out: authentication, API keys, per-user quotas and WAF); execution-plan.md § Risks (a rate-limited or abusive caller drains the Sonnet budget) and § Proposed approach (stage throttle decision)
- **Trigger**: (d) it accepts a known cost, a public endpoint that spends Sonnet tokens with no authentication; (b) it constrains later specs, which must bring any caller-level limit themselves

## Context
Every call spends Sonnet tokens against the $500 budget. The intent put authentication, API keys, per-user quotas and WAF out of scope. The API Gateway stage and the Lambda are the only public edge.

## Decision
The endpoint is unauthenticated. Its abuse guards are the API Gateway stage throttle (5 req/s, burst 10, below feed-api's 20/40), the 512 KiB body cap, and the account's `AiRadarBudget` alerts.

## Alternatives considered
| Option | Why not |
|---|---|
| An API key or an authorizer | Out of scope per the intent. The web UI would then need a secret. |
| WAF or per-user quotas | Out of scope per the intent. They add cost and need a later spec. |

## Consequences
**Positive**: no secret ships to the browser, and the public URL works from an allowed origin with no login.
**Accepted costs**: the stage throttle is best-effort. In the live check, at about 20 req/s, 64 of 80 requests passed where a strict bucket would pass about 30, so the real ceiling under abuse is about twice the nominal rate (open finding F13). A parallel burst can also exhaust the account's Lambda pool before the stage throttle engages, which returns 503s and shares the pool with the feed API (open finding F11). The budget alert is the backstop.

## Follow-ups
- Authentication, per-user quotas or WAF belong to a later spec.
- F11 closes once the Lambda quota is raised and the reserved concurrency is restored.

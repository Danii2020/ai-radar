# ADR 0035: No per-visitor limit on the chat route in v1

- **Status**: Accepted
- **Date**: 2026-10-24
- **Feature**: web-chat-ui
- **Capability**: web-chat
- **Source**: execution-plan.md § Proposed approach 13 (WEBCHAT-R1)
- **Trigger**: (d) it deliberately accepts a known cost or reservation

## Context
The Next.js route is the only public entry to the chat. The API's throttle (5 req/s, burst 10) is global, so one visitor can use up the quota for everyone. A per-IP limit needs state or a platform feature that the app does not have.

## Decision
v1 ships without a per-visitor or per-session limit on `/api/chat`. The UI shows the `busy` state on a 429. The `AiRadarBudget` alert is the cost backstop. This was the human's decision on 2026-10-22.

## Alternatives considered
| Option | Why not |
|---|---|
| Per-IP limit in the route | Needs shared state across serverless instances; out of scope for v1. |

## Consequences
**Positive**: no new state, dependency or infrastructure.
**Accepted costs**: one visitor can starve the rest (WEBCHAT-R1). The Vercel function duration versus `maxDuration` 40 (WEBCHAT-R3) and the missing live check with the real key (WEBCHAT-R2) are also open.

## Follow-ups
Revisit when the chat is publicly deployed (Phase 5).

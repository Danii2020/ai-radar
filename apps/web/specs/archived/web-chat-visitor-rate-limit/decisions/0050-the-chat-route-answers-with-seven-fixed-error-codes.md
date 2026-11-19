# ADR 0050: The chat route answers with seven fixed error codes

- **Status**: Accepted
- **Date**: 2026-11-18
- **Feature**: web-chat-visitor-rate-limit
- **Capability**: web-chat
- **Source**: execution-plan.md § Proposed approach (Decision 8), intent AC6 and AC12
- **Trigger**: (b) constrains future features; (c) amends ADR 0033

## Context
ADR 0033 fixed six error codes for the browser. The visitor limit needs a state that is not `busy` (the shared backend throttle, 429) and not `unavailable` (503), so that a limited visitor sees a message about their own limit.

## Decision
`rate_limited` is a seventh fixed code: status 429, body exactly `{"error":"rate_limited"}`, the existing `content-type` and `cache-control: no-store` headers, and `Retry-After: <seconds>` (a whole number, at least 1, until the blocking window resets). The body never says which limit fired. A backend 429 still maps to `busy`. `sendTurn` maps a 429 with a non-JSON, empty or unknown body to `rate_limited`. The panel shows "You've reached the chat limit for now. Please try again later." for it. `unavailable` is kept verbatim and now also covers a limiter store outage and an invalid limiter setting; neither state names a limiter, store or setting. ADR 0033's file is not edited; this ADR amends it.

## Alternatives considered
| Option | Why not |
|---|---|
| Reuse `busy` for a limited visitor | The copy and the cause differ; `busy` means the shared backend throttle. |
| New copy for the limiter outage | `unavailable` already meets the friendly, distinct wording, so it is kept and the existing tests stay valid. |
| Say which limit fired in the body | Helps a client tune its abuse; the log line carries `limit` for the operator instead. |

## Consequences
**Positive**: a distinct, honest message for a limited visitor and one stable list of codes.
**Accepted costs**: the code list in the UI, route and docs must stay in step at seven; `Retry-After` is sent but the UI ignores it.

## Follow-ups
None.

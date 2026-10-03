# ADR 0004: Drain empty-but-cursored pages, bounded to 5 requests

- **Status**: Accepted
- **Date**: 2026-09-18
- **Feature**: web-feed-ui
- **Capability**: web-feed
- **Source**: contract.md § AD-6, Guarantees 6 & 7
- **Trigger**: (b) constrains future features; (d) accepts a known, deliberately-guarded cost

## Context

`feed-api`'s Guarantee 4 (`FilterExpression` applies after `Limit`) is live
and was directly probed: `GET /v1/cards?tag=zzz-no-such-tag&limit=5` returns
`200 {"cards": [], "next_cursor": "<token>"}` — a real, observed empty page
carrying a live cursor. Spec 01's own `tasks.md` names "a short filtered page
misread as 'end of feed'" as a Medium/Medium risk it deliberately left for
this consuming spec to mitigate.

## Decision

`loadFeed()` follows `next_cursor` while the page came back empty and
`nextCursor !== null`, up to `MAX_DRAIN_REQUESTS = 5` requests total per
render, then renders what it has. If the cap is hit with zero cards and a
still-live cursor, the UI states the search covered the first N pages and
still offers "next page" — it never claims "no matches" for a page it did
not actually read.

## Alternatives considered

| Option | Why not |
|---|---|
| Drain until non-empty, with no cap | Unbounded upstream cost against a request-billed API — a pathological or non-existent tag could fan one page view into unlimited requests. |
| Don't drain at all | Reproduces the documented misreading exactly: any tag whose matches start on page 2+ would incorrectly show "no matches" on page 1. |

## Consequences

**Positive**: 5 × `PAGE_SIZE`(20) = 100 ≥ the entire 87-card corpus observed
at ship time, so today a rare tag is always found within the cap. The
honesty guarantee (never claiming absence over unread pages) is testable and
tested (T14–T17, treated as load-bearing by the test-writer's own
instructions).

**Accepted costs**: A pathological filter can still cost up to 5 upstream
requests per single page view (bounded, not eliminated) — backstopped by the
existing `AiRadarBudget` CloudWatch alarms from an earlier feature, not a
new guard invented here.

## Follow-ups

If the corpus grows well past ~100 cards and rare-tag pages start exceeding
the 5-request cap in practice, `MAX_DRAIN_REQUESTS` would need revisiting —
no such evidence exists at ship time.

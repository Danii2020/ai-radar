# ADR 0051: Backward paging is one reversed Query, with the direction carried in the opaque cursor

- **Status**: Accepted
- **Date**: 2026-11-10
- **Feature**: feed-prev-cursor
- **Capability**: feed-api
- **Source**: execution-plan.md § Proposed approach (Decision: direction lives in the opaque cursor, not in a `?direction=` parameter; Decision: suggested token shapes); § Binding constraints (the page cursor rule table; the request surface is unchanged); intent.md § Outcome and AC4
- **Trigger**: (a) it chooses between a `?direction=` parameter, offsets or page numbers, a server-side page stack, and a direction carried in the cursor; (d) it accepts that, with a `tag` filter, backward page boundaries may differ from the forward ones, with no over-fetch to align them

## Context
`GET /v1/cards` had forward paging only. A "Previous" control needs the page before the current one, and the server has to stay stateless. The request surface (`tag`, `limit`, `cursor`) is fixed, and the Lambda's IAM grant is index-only `dynamodb:Query` on `feed-by-score` (AD-6). DynamoDB has no offset, so a page number would need a scan or a counter. The web app passes `?cursor=` through verbatim, so a cursor must survive a round trip unchanged.

## Decision
The direction lives inside the opaque cursor. A backward cursor is the same key as a forward one plus `"dir": "prev"`. A backward request is one `Query` on `feed-by-score` with `ScanIndexForward=True`. Its items are reversed into feed order. No new query parameter is added. Each page carries `next_cursor` and `prev_cursor`, and both are built from the cursor rules in the execution plan.

## Alternatives considered
| Option | Why not |
|---|---|
| A `?direction=next|prev` parameter | Two values must agree (cursor and direction), which allows a mismatched pair and needs a new 400 case. |
| Offsets or page numbers | DynamoDB has no offset. It would need a scan or a server-side counter. |
| A server-side page stack | Holds state per client and breaks the stateless constraint. |
| Over-fetch to align filtered backward boundaries with the forward ones | Needs extra queries or a larger read, and the intent rules it out. The cards visited are the same either way. |

## Consequences
**Positive**: clients keep passing tokens through byte for byte. A mismatched cursor and direction pair cannot exist. Each request is still one `Query`, so the IAM grant and the request surface do not change.

**Accepted costs**: with a `tag` filter, DynamoDB applies the filter after `Limit`, so backward page boundaries can differ from the forward pages. The cards seen are the same, and a backward page may be short or empty while its `prev_cursor` is live. This is the accepted reservation FA-R2 in `feed-api`, human-approved.

## Follow-ups
- A follow-up `apps/web` spec adds the "Previous" control, uses `prev_cursor`, and drains empty filtered backward pages the way the forward path does.

# ADR 0053: The backward query reads limit + 1 items to tell the start of the feed from more before

- **Status**: Accepted
- **Date**: 2026-11-10
- **Feature**: feed-prev-cursor
- **Capability**: feed-api
- **Source**: execution-plan.md § Proposed approach (Decision: the backward query reads `limit + 1` items, intent Q1 resolved as option A); § Risks (moto returns no `LastEvaluatedKey` at an exact `Limit`); § Validation (the live runbook reminder); intent.md § Open questions, Q1
- **Trigger**: (a) it chooses between `Limit = limit` and `Limit = limit + 1` for the backward query; (d) it accepts one extra index item read per backward call, and a possible trailing empty filtered page at the start of the feed

## Context
Real DynamoDB returns a `LastEvaluatedKey` whenever a query stops at exactly `Limit` items, even when nothing follows. moto returns a key only when another item follows, so the offline tests cannot show the difference. If the backward query used `Limit = limit`, going back from page 2 would always read exactly `limit` items. Page 1 reached backward would then carry a non-null `prev_cursor` that leads to an empty page, and a "Previous" button would show on page 1.

## Decision
The backward query uses `Limit = limit + 1`. It returns at most `limit` cards. The extra item only signals that something precedes the page: if more than `limit` cards match, the one furthest from the anchor is dropped and `prev_cursor` is set to a backward position. Without a tag filter, the start-of-feed decision rests on the item count, not on `LastEvaluatedKey`, so it does not depend on the moto and real-DynamoDB difference. The live check on 2026-11-10 confirmed this: page 2's `prev_cursor` returned page 1 with `prev_cursor: null`.

## Alternatives considered
| Option | Why not |
|---|---|
| `Limit = limit` for the backward query | Page 1 reached backward carries a dangling `prev_cursor` on real DynamoDB, which moto hides. |
| A second query to probe whether anything precedes the page | Breaks the one-`Query`-per-request rule (FA-1). |

## Consequences
**Positive**: unfiltered page 1 reached backward has `prev_cursor: null`, decided by the item count and confirmed on the real table. The rule does not depend on the moto gap.

**Accepted costs**: one extra index item is read per backward call. A filtered walk that reaches the start of the feed can end on one trailing empty page whose `prev_cursor` is `null`. AC4 allows this. Only the live check can confirm real-DynamoDB behavior, so the offline tests cannot.

## Follow-ups
- The follow-up `apps/web` spec should drain that trailing empty filtered page, the way the forward path drains empty pages.

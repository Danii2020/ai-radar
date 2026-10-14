# ADR 0011: Vectors are written by a separate conditional writer, never through upsert

- **Status**: Accepted
- **Date**: 2026-10-13
- **Feature**: chat-retrieval
- **Capability**: card-persistence
- **Source**: execution-plan.md § Proposed approach (decision: `DynamoCardStore.set_embeddings` uses a conditional `update_item`); intent.md § Constraints (amends PS-2)
- **Trigger**: (c) amends a previously shipped rule: PS-2 said `upsert` never writes `embedding` and gave no writer; (b) it sets the rule for every future writer of that attribute

## Context
`dynamodb-card-store` reserved the `embedding` attribute and PS-2 required that `upsert` never write it, so a re-upsert leaves a vector intact. Chat-retrieval needs a sanctioned path that writes vectors. Writing them through `upsert` would break PS-2 and AC3. Writing them with an unconditional `update_item` would create phantom items for cards whose persist failed.

## Decision
Vectors are written only by methods on `DynamoCardStore`. `set_embeddings({url: vector})` is used by the post-persist step and returns the number actually written. `set_embedding(card_id, vector)` is used by the backfill. Both run a per-card conditional `update_item SET embedding` with `ConditionExpression=attribute_exists(card_id)`. `upsert` is unchanged.

## Alternatives considered
| Option | Why not |
|---|---|
| Let `upsert` write `embedding` | Breaks PS-2 and AC3: a re-upsert must leave the vector byte-identical. |
| Unconditional `update_item` | Creates an item for a card whose persist failed, which is a phantom card. |
| Store vectors in a separate table | Another table to keep consistent. Not needed at this corpus size. |

## Consequences
**Positive**: PS-2 still holds for `upsert`. A re-upsert leaves vectors byte-identical, and `updated_at` still advances (AC3). A card that was never persisted gets no item.
**Accepted costs**: there are now two write paths that touch card items. The graph trusts the writer's returned count, so a writer that over-reports would hide failures (the F1 fix guards this with tests).

## Follow-ups
- None beyond the pending deploy. The `dynamodb:UpdateItem` grant on the runtime role already covers this writer.

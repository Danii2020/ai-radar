# Card Persistence Specification

> Last synced: 2026-10-13. Owned artifacts: `src/curation/dynamo.py`,
> `src/curation/local.py`, `infra/lib/card_store.py`, `infra/stacks/card_store_stack.py`.

## Purpose

The storage side of the `CardStore` Protocol seam `curation-pipeline`
depends on: where discovered/summarized cards actually live, and the
idempotency/dedup guarantees each backend must uphold. Its own capability
because the DynamoDB backend's schema, GSI design, and upsert-idempotency
contract are load-bearing for both `runtime-deployment` (Plane A on
AgentCore Runtime) and `feed-api` (Plane 2's read path), independent of the
graph's own node logic.

## Requirements

### Requirement: PS-1 — CardStore Protocol satisfied, idempotency bridge intact

`DynamoCardStore` SHALL structurally satisfy the `CardStore` Protocol
(`isinstance(DynamoCardStore(...), CardStore)` is `True`) with no edit to
`graph.py`/`nodes.py`/`state.py`/`interfaces.py`, and SHALL derive
`card_id` via the same rule as `RawItem.url_hash`
(`sha256(url.encode()).hexdigest()[:16]`), so `dedup_filter` after `upsert`
excludes exactly the items already stored.

**Source:** dynamodb-card-store · contract.md § Behavior Guarantees 1, 2

### Requirement: PS-2 — Upsert is idempotent and never clobbers reserved fields

Calling `upsert(batch)` twice SHALL yield exactly one item per distinct
`card_id` (no duplicates); `created_at` SHALL be unchanged across repeat
upserts; `updated_at` SHALL advance. `upsert` SHALL never write the
`embedding` attribute — an item pre-seeded with one retains it byte-for-byte.
The only sanctioned writer of `embedding` is the separate embedding writer of PS-5.

**Source:** dynamodb-card-store · contract.md § Behavior Guarantees 4, 5; amended by chat-retrieval · intent.md § AC3 (the separate writer)

#### Scenario: A double-delivered curation run re-upserts the same cards
- **WHEN** the same batch of cards is upserted twice (e.g. a retried
  invocation)
- **THEN** the table still contains exactly one item per `card_id`, with
  `created_at` from the first write and `updated_at` from the second

### Requirement: PS-3 — Feed-read index populated for every card

Every upserted item SHALL carry `gsi_pk="CARD"` and
`gsi_sk=f"{relevance:03d}#{published}"`, populating the `feed-by-score` GSI
so a query ordered by descending score then date needs no table scan.

**Source:** dynamodb-card-store · contract.md § Behavior Guarantees 6

### Requirement: PS-4 — Table survives stack teardown

The CDK-provisioned table SHALL use on-demand billing with
`removal_policy=RETAIN`, so destroying the CDK stack never deletes curated
data.

**Source:** dynamodb-card-store · contract.md § Behavior Guarantees 9

### Requirement: PS-5 — Embedding writer is separate, conditional and sanctioned

`DynamoCardStore` SHALL expose `set_embeddings(vectors) -> int`, which writes a batch
keyed by `url`, and `set_embedding(card_id, vector)`, which writes one card. Both SHALL
write `embedding` with a conditional `update_item` (`attribute_exists(card_id)`), so a
card that was never persisted gets no item. Vectors SHALL be stored as `Decimal`, and
`set_embeddings` SHALL return the count actually written.

**Source:** chat-retrieval · intent.md § AC3; execution-plan.md § Proposed approach (decision: `set_embeddings` uses a conditional `update_item`)

#### Scenario: Embed a card that was never upserted
- **WHEN** `set_embeddings` is called for a URL whose card is not in the table
- **THEN** no item is created and the returned count is 0

#### Scenario: Embed, then re-upsert
- **WHEN** a card is embedded and then upserted again
- **THEN** its `embedding` is byte-identical and its `updated_at` has advanced

## Invariants

1. `boto3` is imported only in `dynamo.py` among `src/curation/` modules —
   the compiled graph's portability (liftable onto other infra) depends on
   this staying true (dynamodb-card-store BG8).
2. Store tests run against `moto` with zero real-AWS calls (dynamodb-card-store BG10).

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| dynamodb-card-store | 2026-07-21 | `DynamoCardStore`, the `ai-radar-cards` table + `feed-by-score` GSI, upsert idempotency, reserved `embedding` attribute for a future vector store. |
| chat-retrieval | 2026-10-13 | PS-5: the separate conditional embedding writer (`set_embeddings`, `set_embedding`), the sanctioned writer of `embedding` under PS-2. `upsert` is unchanged. Nothing deployed. |

## Related ADRs

| ADR | Title | Status |
|---|---|---|
| [0011](../archived/chat-retrieval/decisions/0011-vectors-written-by-a-separate-conditional-writer.md) | Vectors are written by a separate conditional writer, never through upsert | Accepted |

(ADR 0011 is the first ADR for this capability. `dynamodb-card-store` shipped before `harny-adr` existed and gets none, per that skill's guardrail.)

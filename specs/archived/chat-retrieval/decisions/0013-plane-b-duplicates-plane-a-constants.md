# ADR 0013: Plane B duplicates Plane A's table, index and store constants instead of importing them

- **Status**: Accepted
- **Date**: 2026-10-13
- **Feature**: chat-retrieval
- **Capability**: chat-retrieval
- **Source**: execution-plan.md § Binding constraints (Plane B duplicates, never imports, Plane A constants) and § Proposed approach (`src/chat/config.py` mirrors `api/config.py`)
- **Trigger**: (b) it sets a rule for every future Plane B module: constants are copied, not imported, and an equality test guards them

## Context
The Plane B retriever must read the `ai-radar-cards` table and the `feed-by-score` index that Plane A owns. Importing `curation.config` would cross the plane boundary. The `feed-api` spec already set this precedent (AD-4), duplicating the same constants with an equality test.

## Decision
`src/chat/config.py` duplicates the table name (env `CARD_TABLE_NAME`, default `ai-radar-cards`), the fixed GSI name `feed-by-score`, the `CARD` partition, and the `CARD_STORE_BACKEND` default. `tests/test_chat_contract.py` asserts that each equals its `curation/config.py` counterpart.

## Alternatives considered
| Option | Why not |
|---|---|
| Import `curation.config` from `chat` | Crosses the plane boundary (architecture-principles, boundary 1). |
| A shared config module for both planes | Promotes a shared contract before a trigger fires. `Card` is the only sanctioned shared type. |

## Consequences
**Positive**: if a Plane A constant is renamed, a test fails instead of the retriever silently querying the wrong index.
**Accepted costs**: two copies of each constant must change together. The equality test is the only enforcement.

## Follow-ups
- If a third consumer of these constants appears, revisit whether a shared contract has now been triggered (architecture-principles).

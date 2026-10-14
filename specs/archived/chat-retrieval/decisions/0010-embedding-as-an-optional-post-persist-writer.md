# ADR 0010: Embedding is an optional, best-effort step after persist, injected as a writer

- **Status**: Accepted
- **Date**: 2026-10-13
- **Feature**: chat-retrieval
- **Capability**: curation-pipeline
- **Source**: execution-plan.md § Proposed approach (decisions: `EmbeddingWriter` Protocol and `build_graph(..., embedding_writer=None)`; the embed node runs after persist, per-card try/except)
- **Trigger**: (a) a choice between named options (Protocol on `CardStore`, `isinstance` auto-detection, embedding before persist); (b) it fixes a rule for the graph: embedding is optional and never fails a run

## Context
Curated cards need a Titan v2 vector. Two constraints apply. The graph and its nodes may not import `boto3` (card-persistence invariant 1), so the writer must be injected. A Titan or write failure must never block or roll back a card or fail the run (AC2). Existing callers of `build_graph(store, discoverer)` and the existing tests must not start calling real Bedrock.

## Decision
`build_graph(store, discoverer, embedding_writer=None)` adds an `embed` node after `persist` only when a writer is passed. The node embeds each persisted card in its own try/except, counts the Titan failures and the unwritten vectors, and sends the vectors to the writer in one call. The counts go into state and into the `embed_complete` log record. Nothing is raised to the caller. `runtime_app.py` and `run_curation.py` pass their `DynamoCardStore` as the writer.

## Alternatives considered
| Option | Why not |
|---|---|
| Add `set_embeddings` to the `CardStore` Protocol | Forces `JsonFileCardStore` to implement it, and amends the `CardStore` Protocol that curation-graph shipped. |
| Auto-detect with `isinstance(store, EmbeddingWriter)` | Existing moto-backed graph tests would suddenly call Titan. |
| Embed before persist | Couples card persistence to Titan availability. |

## Consequences
**Positive**: with no writer, the graph and every existing caller behave exactly as before. A failed embed never blocks or rolls back a card.
**Accepted costs**: a card whose `upsert` failed still gets a Titan call. Its vector write is then rejected and it is counted in `embed_failed`. The auditor estimated about $0.00002 per card (not checked against current pricing). This is accepted limitation F11 in the audit. The step runs only in callers that pass a writer, so it has no effect on the deployed runtime until the image is rebuilt.

## Follow-ups
- Rebuild and redeploy the curation agent image so `runtime_app.py` runs the step (pending deploy, README "Phase 3 — Chatbot").

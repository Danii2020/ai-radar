# Curation Pipeline Specification

> Last synced: 2026-10-13. Owned artifacts: `src/curation/graph.py`,
> `src/curation/nodes.py`, `src/curation/state.py`, `src/curation/interfaces.py`,
> `src/curation/composite.py`, `src/curation/tavily.py`, `src/curation/backfill.py`,
> `run_backfill_embeddings.py`, `src/shared/feeds.py`.

## Purpose

Plane A's curation loop: a LangGraph `StateGraph` that discovers candidate
items, dedups, summarizes/tags via Bedrock, ranks, and persists — with
infrastructure (discovery source, storage) injected behind `Protocol` seams
so the graph itself never depends on infra. Its own capability, separate
from `card-persistence` (the storage side of the same seam) and
`runtime-deployment` (where the compiled graph actually runs), because the
graph's node wiring and dedup/idempotency guarantees are a distinct,
independently-testable contract.

## Requirements

### Requirement: CP-1 — Five-node linear graph, injected infra

The system SHALL compile a `StateGraph` whose node set is exactly
`{discover, dedup, summarize, rank, persist}`, wired linearly
`START → discover → dedup → summarize → rank → persist → END`, constructed
by injecting a `Discoverer` and a `CardStore` — never by editing
`graph.py`/`nodes.py`/`state.py` to swap infrastructure. The sole exception is
the optional `embed` node of CP-6, which is added only when an `embedding_writer`
is passed; without one the graph is exactly the five-node graph above.

**Source:** curation-graph · contract.md § Behavior Guarantees 1, 9; amended by chat-retrieval · execution-plan.md § Proposed approach (`build_graph(..., embedding_writer=None)`)

#### Scenario: Swapping the discoverer or store
- **WHEN** `build_graph(store, discoverer)` is called with a different
  `CardStore` or `Discoverer` implementation
- **THEN** the graph compiles and runs correctly with no change to
  `graph.py`, `nodes.py`, or `state.py`

### Requirement: CP-2 — Dedup precedes summarize; idempotent re-invoke

The system SHALL run dedup before summarize and the per-run item cap, so an
already-seen item is never re-summarized; re-invoking the graph against an
unchanged `seen` store SHALL yield zero new cards.

**Source:** curation-graph · contract.md § Behavior Guarantees 3, 5

#### Scenario: Re-running against a fully-seen store
- **WHEN** the graph is invoked twice in a row with no new discoverable items
- **THEN** the second invocation produces zero new cards and leaves the seen
  store unchanged

### Requirement: CP-3 — Per-item resilience

The system SHALL isolate a single item's failure during summarize: one
raising item increments the run's failure counter, is skipped, and the run
continues to completion, persisting the remaining cards.

**Source:** curation-graph · contract.md § Behavior Guarantees 4

### Requirement: CP-4 — Multi-source discovery, cross-source deduped

The system SHALL support composing multiple discovery sources (RSS, Tavily
web search) via a `CompositeDiscoverer` that returns the URL-hash-deduped,
order-preserving union of its sources' items — the same article appearing in
two sources is summarized once. A single source raising SHALL be caught,
logged, and counted, with the remaining sources' results still returned
(`discover()` never raises).

**Source:** tavily-discovery · contract.md § Behavior Guarantees 2, 4, 5

#### Scenario: One discovery source is down
- **WHEN** Tavily's API is unreachable but RSS feeds are healthy
- **THEN** `CompositeDiscoverer.discover()` returns the RSS results with no
  exception, and the run degrades to RSS-only rather than failing

### Requirement: CP-5 — Discovery costs are bounded

The system SHALL enforce a per-run cap on the number of items a paid
discovery source (Tavily) returns, as the primary cost-control lever for
that source.

**Source:** tavily-discovery · contract.md § Behavior Guarantees 1

### Requirement: CP-6 — Optional, best-effort embed step after persist

The system SHALL, when built with an `embedding_writer`, run an `embed` node after
`persist`. The node SHALL embed each persisted card's `card_text` with Titan v2 and write
the vectors through that writer. A Titan failure on one card, or a failed write, SHALL be
counted and logged. It SHALL NOT fail the run or unpersist a card. The node SHALL NOT run
before `persist`.

**Source:** chat-retrieval · intent.md § AC1, AC2; execution-plan.md § Proposed approach (embed node after persist, per-card try/except)

#### Scenario: Titan fails on one of six cards
- **WHEN** a run with a writer persists 6 cards and Titan raises for one
- **THEN** all 6 cards are persisted, 5 are embedded, the run completes, and the embed
  step's log record reports `embed_failed=1`

#### Scenario: No writer
- **WHEN** the graph is built without an `embedding_writer`
- **THEN** no embed node exists and Titan is never called

## Invariants

1. Dedup key derivation is a single rule everywhere: `sha256(url.encode()).hexdigest()[:16]`,
   used identically by `RawItem.url_hash`, `JsonFileCardStore`, and
   `DynamoCardStore` — breaking this rule breaks the idempotency bridge
   between discovery and persistence (curation-graph BG8, tavily-discovery
   BG6, extended by `card-persistence` PS-1).
2. No module under `src/curation/` outside `tavily.py`/`dynamo.py` imports
   `boto3` or the `tavily` SDK directly — infra access is confined to the
   `Discoverer`/`CardStore` Protocol implementations (curation-graph BG6,
   tavily-discovery BG8).
3. Embedding is an optional step after `persist`, never before it, and it never fails a
   run (CP-6, ADR 0010). Card persistence does not wait on Titan.

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| F11 | Accepted limitation: a card whose `upsert` failed still gets a Titan call (about $0.00002 per card by the auditor's estimate, not checked against current pricing). Its conditional vector write is then rejected and it is counted in `embed_failed`, so CP-6 holds. | LOW | `specs/archived/chat-retrieval/audit.md` (F11) |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| curation-graph | 2026-07-10 | The five-node `StateGraph`, `Discoverer`/`CardStore` Protocols, local JSON-file defaults, dedup-before-summarize ordering, per-item resilience. |
| tavily-discovery | 2026-07-15 | `TavilyDiscoverer` + `CompositeDiscoverer`, cross-source dedup, per-run result cap, graceful degradation on source failure. |
| chat-retrieval | 2026-10-13 | CP-6: the optional `embed` node after `persist` and its `EmbeddingWriter` seam, the embed counts in state and the log record, and the backfill (`src/curation/backfill.py`, `run_backfill_embeddings.py`). Nothing deployed. |

## Related ADRs

| ADR | Title | Status |
|---|---|---|
| [0010](../archived/chat-retrieval/decisions/0010-embedding-as-an-optional-post-persist-writer.md) | Embedding is an optional, best-effort step after persist, injected as a writer | Accepted |
| [0015](../archived/chat-retrieval/decisions/0015-backfill-as-a-local-one-shot-command.md) | The embedding backfill is a local, idempotent one-shot command | Accepted |

(`curation-graph` and `tavily-discovery` shipped before `harny-adr` existed in this project; per that skill's own guardrail, they get no retroactive ADRs.)

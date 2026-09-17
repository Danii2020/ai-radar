# Curation Pipeline Specification

> Last synced: 2026-09-17. Owned artifacts: `src/curation/graph.py`,
> `src/curation/nodes.py`, `src/curation/state.py`, `src/curation/interfaces.py`,
> `src/curation/composite.py`, `src/curation/tavily.py`, `src/shared/feeds.py`.

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
`graph.py`/`nodes.py`/`state.py` to swap infrastructure.

**Source:** curation-graph · contract.md § Behavior Guarantees 1, 9

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

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| curation-graph | 2026-07-10 | The five-node `StateGraph`, `Discoverer`/`CardStore` Protocols, local JSON-file defaults, dedup-before-summarize ordering, per-item resilience. |
| tavily-discovery | 2026-07-15 | `TavilyDiscoverer` + `CompositeDiscoverer`, cross-source dedup, per-run result cap, graceful degradation on source failure. |

## Related ADRs

None yet — both contributing features shipped before `harny-adr` existed in
this project; per that skill's own guardrail, shipped-before-the-skill
features get no retroactive ADRs.

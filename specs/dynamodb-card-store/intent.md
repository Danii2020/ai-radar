# Intent: dynamodb-card-store

## Problem Statement

Plane A's persistence + dedup is currently the spike's local JSON files
(`JsonFileCardStore` over `.spike_cache/seen.json` + `cards.json`). That was fine
for the Phase 0 spike and Spec 01's local default, but it does not survive a real
deployment: files are per-machine, not durable, not shared between the scheduled
curation run and the (Phase 2) feed-read API, and dedup is a whole-file rewrite of
a growing `seen.json` set. Design §3 names the durable home for cards the
**"Topic store (DynamoDB)"** — `cards: title, url, summary, tags, date, score,
embedding ref` — and §5 requires the pipeline be **idempotent: safe to re-run;
dedup prevents duplicates**.

The affected party is the curation pipeline itself (Plane A) and, one spec later,
the feed-read API (Plane B): today neither can rely on a durable, queryable,
concurrently-writable card store, and there is no place to hang the reserved
per-card vector the Phase 3 brute-force RAG will need. This feature supplies a
`DynamoCardStore` implementing the **unchanged** Spec 01 `CardStore` Protocol
(`dedup_filter` + `upsert`), so the *unchanged* compiled LangGraph curation graph
(Spec 01) runs against DynamoDB by dependency injection alone — no graph, node,
state, or interface edits — plus the reusable Python CDK construct that provisions
the table and its feed-read GSI. It is the persistence half of Plane A and the
first infrastructure-as-code in the repo.

## Goals

1. Add a `DynamoCardStore` implementing the Spec 01 `CardStore` Protocol exactly:
   - `dedup_filter(items) -> list[RawItem]` — order-preserving; returns only items
     whose `card_id` (URL hash) is not already in the table.
   - `upsert(cards) -> None` — idempotent insert-or-replace; re-running the same
     batch yields one row per card, advances `updated_at`, never duplicates, and
     never clobbers a card's reserved `embedding`.
2. Lock a **DynamoDB key schema** now — base-table PK and the feed-read GSI PK/SK —
   because changing keys later is a data migration, not a code change. The base PK
   is `card_id = sha256(url)[:16]`, matching `RawItem.url_hash` / `local._url_hash`
   byte-for-byte so the three dedup layers (composite, store, RawItem) agree.
3. Design the **feed-read GSI now** for the Phase 2 access pattern (feed sorted by
   score then date) even though no consumer exists yet in this codebase, so Phase 2
   is a query against a pre-existing index — no backfill, no migration. Write the
   GSI key attributes on every card at `upsert` time so the index is populated the
   day Phase 2 needs it.
4. Reserve an inline `embedding` attribute in the documented item schema, left
   **unset/absent** by all Phase 1 code, so Phase 3's brute-force cosine RAG can be
   added without a schema migration — and so `upsert` must be written to preserve
   any future embedding across re-curation.
5. Provision the table via a **reusable Python CDK construct** (not inline CFN, not
   click-ops) under a new `infra/` directory, in **on-demand (pay-per-request)**
   billing mode so it scales to ~zero cost at low traffic (§4, §7).
6. Prove the seam: `build_graph(DynamoCardStore(...), discoverer)` compiles and runs
   the *unchanged* Spec 01 graph end-to-end — the Dynamo store is a drop-in swap for
   `JsonFileCardStore`.
7. Keep everything testable offline: unit/integration tests run against `moto`
   (in-process DynamoDB mock) with **zero** real-AWS calls.

## Success Criteria

(Maps to the acceptance checklist in
`tasks/phase-1-curation-mvp/03-dynamodb-card-store.md`, narrowed to this phase's
scope — see Non-Goals.)

- [ ] `DynamoCardStore` satisfies the Spec 01 `CardStore` Protocol
      (`isinstance(store, CardStore)` holds via `runtime_checkable`) and the
      *unchanged* Spec 01 graph runs end-to-end against it — no edits to
      `graph.py`/`nodes.py`/`state.py`/`interfaces.py`.
- [ ] `dedup_filter` returns, order-preserving, exactly the items whose `card_id`
      is not already in the table; after `upsert(cards)`, a subsequent
      `dedup_filter` over the same source items returns `[]` (Protocol idempotency).
- [ ] `upsert` is idempotent: running the same batch twice yields exactly one item
      per `card_id`, with `updated_at` advanced and `created_at` unchanged, and no
      duplicate items.
- [ ] `upsert` never writes the `embedding` attribute and never clobbers a
      pre-existing `embedding` on re-run (reserved-shape guarantee for Phase 3).
- [ ] The base table is provisioned by a reusable CDK construct in on-demand
      billing mode, with the feed-read GSI present and its key attributes written
      on every card.
- [ ] The GSI key schema (constant partition + zero-padded `score#date` sort) is
      documented and locked in `contract.md`, with the Phase 2 read query written
      down (but **not** implemented) so the index design is validated now.
- [ ] The inline `embedding` attribute is part of the documented item schema and is
      left unset by Phase 1 code.
- [ ] All tests pass against `moto` with no real-AWS calls.

## Non-Goals

- **Embedding *computation* / vector similarity.** Only the inline `embedding`
  attribute's *reservation* is owned here — not populating it, not cosine search,
  not Titan calls. That is Phase 3.
- **Any dedicated vector store** (Pinecone / pgvector / OpenSearch Serverless /
  Bedrock KB default). The cross-phase decision is brute-force cosine over *this*
  table's inline vectors; OpenSearch Serverless is explicitly banned (§7, budget).
  Revisit only at ~50k+ cards.
- **The read API / Lambda (Phase 2).** Only the table + GSI *shape* and the written
  GSI keys are owned here; the query that consumes them is documented, not built.
- **EventBridge / AgentCore Runtime wiring / deploying the stack (Specs 04–05).**
  This spec defines the CDK construct and app; it does not wire scheduling, package
  the Runtime, or run `cdk deploy` against a real account.
- **Any change to the stable seam** — `src/curation/interfaces.py` (the `CardStore`
  Protocol) is unchanged; this spec must satisfy it, not modify it. No change to
  the graph/nodes/state, the `Card` schema, or `spike.bedrock.summarize`.
- **Migrating / removing `JsonFileCardStore`.** The local JSON store stays as the
  default for keyless local runs; the Dynamo store is an alternative selected by
  config. `src/spike/**` is reused/imported, not edited.

## Constraints

- **Do not modify the stable seam.** `src/curation/interfaces.py` (`CardStore`
  Protocol) is unchanged. `RawItem`, `Card`, the `sha256(url)[:16]` hash rule, and
  the `spike.config` knob pattern are **reused/imported, not forked**.
- **`card_id` must equal `sha256(url).hexdigest()[:16]`** — identical to
  `RawItem.url_hash` (`src/spike/feeds.py`) and `local._url_hash` (`src/curation/
  local.py`), so store-level dedup agrees with the composite/RSS dedup and with a
  re-run's `RawItem`s. The store derives a `Card`'s key from `Card.url` via the
  same rule (Guarantee 8 of Spec 01's contract) — imported/shared, not
  re-implemented divergently.
- **Infra-at-the-edges / portability.** `boto3` is permitted **inside**
  `DynamoCardStore` — it is an infra adapter at the seam, exactly like
  `spike/bedrock.py`. It must **not** be imported by `nodes.py`/`graph.py`/
  `state.py`; those consume the store only through the injected `CardStore`
  Protocol, so the compiled graph stays portable onto AgentCore Runtime unchanged.
- **Lock the key schema and the idempotency guarantee as testable contracts.**
  Per the task's SDD note, `contract.md` must pin the exact PK/SK for the base
  table and GSI, and define "safe to re-run" precisely (item count, `created_at`
  stability, `updated_at` advance, no duplicates). Key changes later are migrations.
- **Cost discipline ($500 budget).** On-demand billing (scales to ~zero); GSI is a
  single design decision made once (not many indexes); no OpenSearch/KB vector
  backing. Dedup-before-summarize (Spec 01) is preserved so Haiku never re-summarizes
  a stored item.
- **Design the Phase 2 GSI now, flagged.** The feed-read GSI is being added for an
  access pattern that has **no consumer yet in this repo** — this is a deliberate,
  flagged exception to "no speculative interfaces," justified because the DynamoDB
  key schema is a migration cost if deferred (architecture-principles §4: ports at
  infra seams; here the seam is the table's key design). Flag it explicitly in the
  contract and roadmap.
- **Verify AWS/library APIs via Context7 before pinning.** CDK `TableV2` /
  `Billing.on_demand()` / GSI props and boto3 `update_item`/`put_item`/`query`/
  `batch_writer` signatures were verified via Context7 (2026-07-20) and are pinned
  in the contract — do not trust memory.
- **Tooling: uv only.** `uv add --group dev moto`; CDK deps via
  `uv add --group infra aws-cdk-lib constructs`. Never pip/venv/requirements.txt.
  `[tool.uv] package = false`, `src/` layout; the CDK app runs via `uv run`.
- **Testing convention (carried from Specs 01/02).** Tests make **zero** real-AWS
  calls — DynamoDB is mocked in-process with `moto` (`mock_aws`), not
  DynamoDB Local / Docker. No live account touched in `pytest`.
- **Style.** Match the lean spike/curation conventions — small modules,
  dataclasses where useful, lazy singleton client (mirror
  `spike.bedrock.bedrock_client()`), `from __future__ import annotations`, per-item
  try/except so one bad card doesn't sink the batch.
- **Ubiquitous language** (architecture-principles §3): `dedup`, `upsert`, `Card`,
  `RawItem`, `card_id`, `relevance`/`score`, plane A. No new domain layers,
  aggregates, repositories, or domain events — no trigger from
  architecture-principles §"Triggers" fires here; this is an infra adapter
  (`CardStore` port, second implementation) plus a CDK construct.

## Decisions (resolved with the human — fixed, not open)

Env-overridable where noted, but the following are settled facts the contract
treats as fixed:

- **Table name** (`CARD_TABLE_NAME`) = `"ai-radar-cards"` — author's choice,
  consistent with the `ai-radar` project name (`pyproject.toml`) and the
  hyphenated resource-naming style; env-overridable, and the CDK construct sets
  this fixed name so the store and stack agree without a CloudFormation-output
  lookup. (Human deferred this low-stakes call to author judgment.)
- **Base-table PK** = `card_id` (String) = `sha256(url)[:16]`. **Fixed** — a key
  change is a migration.
- **Feed-read GSI** name = `"feed-by-score"`; PK attribute `gsi_pk` (String,
  constant value `"CARD"`); SK attribute `gsi_sk` (String) =
  `f"{relevance:03d}#{published}"` (zero-padded score for correct string sort, then
  ISO date). Projection = `ALL` (a feed query returns whole cards, no second read).
  **Fixed** — a key change is a migration.
- **GSI partitioning** = a **single constant** `gsi_pk="CARD"` — **no** monthly
  bucketing (human decision). Phase 1/2 curation-feed volumes (~80 cards/day) stay
  well under DynamoDB's per-partition throughput limits, and one partition keeps
  the whole ranked feed retrievable in a single `query`. (Monthly bucketing remains
  a documented *future* escape hatch only, not designed in now.)
- **Billing** = on-demand (`Billing.on_demand()` / `PAY_PER_REQUEST`).
- **`removal_policy`** = **`RETAIN`** (human decision) — curated cards are real
  data; the table must survive `cdk destroy` / stack teardown while infra is still
  being iterated on in early phases.
- **Region** = reuse `spike.config.AWS_REGION` (`us-east-1` default).
- **CDK project layout** = `infra/` code driven by a new **`infra` uv
  dependency-group in the existing root `pyproject.toml`** (`aws-cdk-lib`,
  `constructs`) — one lockfile, one venv, **not** a nested uv project (human
  decision).

## Prior Art

- `src/curation/interfaces.py` — the `CardStore` Protocol (stable seam, unchanged):
  `dedup_filter(items) -> list[RawItem]`, `upsert(cards) -> None`, with the
  order-preserving + idempotency docstrings this spec must satisfy.
- `src/curation/local.py` — `JsonFileCardStore`, the current default and the
  behavioral reference: `_url_hash(url) = sha256(url)[:16]`, seen-set dedup, the
  `Card.url`→key derivation. `DynamoCardStore` reproduces the *contract*, not the
  file mechanics.
- `src/spike/feeds.py` — `RawItem` and `RawItem.url_hash` (`sha256(url)[:16]`) — the
  exact rule `card_id` must match.
- `src/spike/cards.py` — the `Card` dataclass (title, url, source, summary, tags,
  type, relevance, published, takeaways) whose fields become the item schema.
- `src/spike/bedrock.py` — `bedrock_client()` lazy-singleton pattern the Dynamo
  resource construction mirrors; also the "infra adapter may import boto3" precedent.
- `src/curation/graph.py` / `nodes.py` — `dedup_node(store)` / `persist_node(store)`
  show the store is injected by closure; confirms the Dynamo store is a drop-in swap
  with no graph edits.
- `specs/curation-graph/contract.md` — anticipates Spec 03 as "an alternative
  `CardStore` (DynamoDB) passed to `build_graph` — no graph/node edits", and defines
  Guarantee 8 (the `Card.url`→`sha256[:16]` bridge) this spec's `card_id` reuses.
- `specs/tavily-discovery/` — the reference spec set for structure/tone and the
  testing convention (mock the external service; zero live calls in pytest).
- Design `docs/app-design-on-agentcore.md` §3 (Topic store = DynamoDB card record),
  §4 (DynamoDB on-demand; "Do NOT default to OpenSearch Serverless"), §5 (idempotent
  re-run; feed read sorted by score/date), §7 (budget; brute-force cosine over
  DynamoDB is fine for a small corpus).
- `docs/architecture-principles.md` §"Boundaries" 4 (ports at infra seams when the
  second implementation arrives — this is that second `CardStore`) and
  §"Triggers" (none fire; no domain layer added).

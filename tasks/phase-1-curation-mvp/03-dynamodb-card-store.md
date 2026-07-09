# Spec 03 — DynamoDB card store

- **feature-name:** `dynamodb-card-store`
- **SDD target dir:** `specs/dynamodb-card-store/`
- **Depends on:** Spec 01 (`CardStore` Protocol)
- **Layer:** Data

## Intent

Replace the spike's local JSON files (`cards.json`, `seen.json`) with a
**DynamoDB-backed `CardStore`** that persists curated cards durably, dedups new
items against what's already been collected, and upserts idempotently so the daily
pipeline is safe to re-run. This is the "Topic store (DynamoDB)" in the design
(§3, §4) and the persistence half of Plane A.

## Background

Design §3 lists the card record as: `title, url, summary, tags, date, score,
embedding ref`. The spike's `Card` dataclass already has title/url/source/summary/
tags/type/relevance/published/takeaways. Dedup in the spike is a `seen` set of
16-char URL-hash prefixes (`RawItem.url_hash`). Design §5 calls for "Dedup against
DynamoDB (URL hash …), idempotent: safe to re-run."

## Scope

**In scope**
- DynamoDB single-table (or focused table) design for cards. Decide partition/sort
  keys for the two access patterns Phase 1 needs:
  1. **Dedup lookup** by URL hash (point read / conditional write).
  2. **Feed read** ordered by score/date (Phase 2 will consume this — design for it
     now via a GSI, even though the Phase 2 API isn't built yet).
- A `DynamoCardStore` implementing the Spec 01 `CardStore` Protocol:
  - `dedup_filter(items)` — drop items whose URL hash already exists.
  - `upsert(cards)` — idempotent writes (conditional/`PutItem`); re-running a day
    must not duplicate or corrupt rows.
- Item schema: persist all current `Card` fields, a stable `card_id` (URL hash),
  `created_at`/`updated_at`, and a **reserved inline `embedding` attribute** (a
  list/number-set of floats) left empty/absent. Per the README cross-phase decision,
  the vector lives **inline on the card item** (not a pointer to an external store)
  so Phase 3 can do brute-force cosine straight off DynamoDB — but do **not** compute
  embeddings here. Reserving the inline shape now avoids a Phase 3 migration.
- On-demand (pay-per-request) billing mode — scales to ~zero at low traffic (§4).
- CDK (Python) construct that provisions the table + GSI (consumed by Spec 04/05
  infra), kept as a reusable construct, not inline.
- Tests against a local DynamoDB / `moto` so they run without touching real AWS.

**Out of scope**
- Embedding *computation* / vector similarity dedup (Phase 3) — only the inline
  `embedding` attribute's reservation is owned here, not populating it.
- Any dedicated vector store (Pinecone/pgvector/OpenSearch) — the cross-phase
  decision is brute-force cosine over this table; revisit only at ~50k+ cards.
- The read API / Lambda (Phase 2) — only the table + index shape is owned here.
- EventBridge / Runtime wiring (Specs 04–05).

## Contract sketch

```python
class DynamoCardStore:                      # implements CardStore (Spec 01)
    def __init__(self, table_name: str, client=None): ...
    def dedup_filter(self, items: list[RawItem]) -> list[RawItem]: ...
    def upsert(self, cards: list[Card]) -> None: ...   # idempotent
```

Table (illustrative — architect finalizes keys):
- PK `card_id` (= `url_hash`); attrs: title, url, source, summary, tags, type,
  score (= relevance), published, takeaways, created_at, updated_at, `embedding`
  (inline vector, reserved/empty in Phase 1).
- GSI for feed reads sorted by score/date.

## Acceptance criteria

- [ ] `DynamoCardStore` satisfies the Spec 01 `CardStore` Protocol and the graph
      runs end-to-end against it (swap the local store for the Dynamo store, no
      graph changes).
- [ ] `dedup_filter` returns only URL hashes not already in the table.
- [ ] `upsert` is idempotent: running the same batch twice yields one row per card,
      with `updated_at` advanced and no duplicates.
- [ ] Table provisioned via a reusable CDK construct in on-demand billing mode,
      with the feed-read GSI present.
- [ ] The inline `embedding` attribute is part of the documented item schema and is
      left unset/empty by Phase 1 code (reserved for Phase 3 brute-force RAG).
- [ ] Tests pass against moto/local DynamoDB with no real-AWS calls.

## SDD note

Feed to `sdd-architect` as `dynamodb-card-store`. The contract must lock the
**idempotency guarantee** and the **key schema** (changing keys later is a
migration). Flag the Phase 2 feed-read access pattern so the GSI is designed now.

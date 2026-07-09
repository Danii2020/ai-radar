# Audit: curation-graph

## Requirements Checklist
| ID | Requirement | Source | Status | Notes |
|---|---|---|---|---|
| R1 | Spike loop refactored into an explicit LangGraph `StateGraph` with named nodes and a typed `CurationState` | intent.md Goal 1 | PENDING | |
| R2 | `build_graph(store, discoverer) -> CompiledGraph` is the single public construction API; deps injected, never imported in node code | intent.md Goal 2 | PENDING | |
| R3 | `Discoverer` + `CardStore` Protocols defined as the Spec 02–04 seam, with local default impls | intent.md Goal 3 | PENDING | |
| R4 | Per-item failure resilience: one bad item counted + skipped, run completes | intent.md Goal 4 | PENDING | |
| R5 | Local defaults reproduce Phase 0 exactly (same cards, ranking, idempotency) | intent.md Goal 5 | PENDING | |
| R6 | Runnable locally via `uv run` entrypoint against real Bedrock; `src/spike/` left intact | intent.md Goal 6 | PENDING | |
| R7 | Node code has zero AWS-infra coupling (no `boto3`; only Protocols + `bedrock.summarize`) | intent.md Constraints / Success criterion 4 | PENDING | |
| R8 | Reuse not fork: import `Card`, `summarize`, `discover`/`RawItem` from `src/spike/`; new code in `src/curation/` | intent.md Constraints | PENDING | |
| R9 | LangGraph added via `uv add` (uv only, lockfile updated) | intent.md Constraints | PENDING | |

## Contract Compliance
| ID | Contract Item | Status | Verified By |
|---|---|---|---|
| C1 | `build_graph` returns compiled graph; node set == {discover, dedup, summarize, rank, persist}, wired linearly (Guarantee 1) | PENDING | |
| C2 | Local defaults reproduce spike output, ranked descending (Guarantee 2) | PENDING | |
| C3 | Dedup runs before summarize+cap; no duplicate ever summarized (Guarantee 3) | PENDING | |
| C4 | One `summarize` failure → `failed += 1`, item skipped, run completes + persists rest (Guarantee 4) | PENDING | |
| C5 | Idempotent re-run over unchanged seen store → zero new cards; seen.json unchanged (Guarantee 5) | PENDING | |
| C6 | No `boto3`/AWS-infra import in `src/curation/` node modules (Guarantee 6) | PENDING | |
| C7 | Rank order is relevance-descending and stable for ties (Guarantee 7) | PENDING | |
| C8 | `JsonFileCardStore` derives seen-key from `Card.url` via the `RawItem.url_hash` rule (Guarantee 8) | PENDING | |
| C9 | Behavior changes only by injecting a different Protocol — no graph/node/state edits (Guarantee 9) | PENDING | |
| C10 | `Discoverer`/`CardStore` Protocol signatures match contract exactly (interfaces.py) | PENDING | |
| C11 | `CurationState` fields match contract (max_items, raw, fresh, cards, discovered, deduped, summarized, failed; no per_feed) | PENDING | |
| C12 | Error-handling contract honored (per-item skip, discover degrade, empty-discover, upsert raises loudly) | PENDING | |

## Test Coverage
| ID | Test Description | Status | Test File |
|---|---|---|---|
| T1 | `build_graph` compiles; node set equals the five named nodes | PENDING | tests/test_graph.py |
| T2 | Graph with stubbed discover+summarize produces same ranked cards as spike logic (no regression) | PENDING | tests/test_graph.py |
| T3 | Rank node orders by relevance descending, stable on ties | PENDING | tests/test_graph.py |
| T4 | One stubbed `summarize` raise → `failed == 1`, run completes, other cards persisted | PENDING | tests/test_graph.py |
| T5 | Re-invoke with populated seen store → `cards == []`, seen.json unchanged | PENDING | tests/test_graph.py |
| T6 | `nodes.py` contains no `boto3` reference / does not import boto3 | PENDING | tests/test_graph.py |
| T7 | `JsonFileCardStore.dedup_filter` drops seen url_hashes; `force=True` bypasses | PENDING | tests/test_local_store.py |
| T8 | `upsert` then `dedup_filter` on same items returns empty (idempotency + url-hash bridge) | PENDING | tests/test_local_store.py |
| T9 | `upsert` writes seen.json (sorted) + cards.json (batch, indent=2) matching spike `_save` | PENDING | tests/test_local_store.py |
| T10 | `RssDiscoverer.discover` delegates to `feeds.discover(FEEDS, per_feed)` (monkeypatched) | PENDING | tests/test_local_store.py |
| T11 | Dedup-before-cap order: with seen subset + max_items, never summarizes a seen item | PENDING | tests/test_graph.py |

## Audit Log
| Date | Auditor | Finding | Severity | Resolution |
|---|---|---|---|---|
| | | | | |

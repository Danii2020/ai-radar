# Tasks: curation-graph

## Legend
- [ ] Not started
- [x] Completed
- [~] In progress
- [!] Blocked

## Phase 1: Foundation
- [ ] Task 1.1: `uv add langgraph`; verify `uv sync` + `uv run python -c "import langgraph"` — `pyproject.toml`, `uv.lock`
- [x] Task 1.2: Verify current LangGraph `StateGraph`/`START`/`END`/`compile`/`invoke` API via Context7 before wiring — (no file; informs 3.1) — **verified 2026-06-10 via Context7 (`/langchain-ai/langgraph`, v1.x): `from langgraph.graph import StateGraph, START, END`; nodes are `(state) -> dict` partial updates; `add_node`/`add_edge` → `.compile()` → `.invoke(initial_state)` all as the contract assumes**
- [ ] Task 1.3: Create package marker — `src/curation/__init__.py`
- [ ] Task 1.4: Define `Discoverer` + `CardStore` `Protocol`s (runtime_checkable) per contract — `src/curation/interfaces.py`
- [ ] Task 1.5: Define `CurationState` `TypedDict(total=False)` per contract (max_items, raw, fresh, cards, discovered, deduped, summarized, failed) — `src/curation/state.py`

## Phase 2: Core Logic
- [ ] Task 2.1: Implement `RssDiscoverer` wrapping `feeds.discover(config.FEEDS, per_feed=config.PER_FEED)` — `src/curation/local.py`
- [ ] Task 2.2: Implement `JsonFileCardStore.__init__` + `_load_seen` + url-hash derivation from `Card.url` (Guarantee 8) — `src/curation/local.py`
- [ ] Task 2.3: Implement `JsonFileCardStore.dedup_filter` (order-preserving, honors `force`) — `src/curation/local.py`
- [ ] Task 2.4: Implement `JsonFileCardStore.upsert` (accumulate seen, write seen.json sorted + cards.json batch, indent=2, mkdir) mirroring spike `_save` — `src/curation/local.py`
- [ ] Task 2.5: Implement `discover_node` factory (`raw`, `discovered`) — `src/curation/nodes.py`
- [ ] Task 2.6: Implement `dedup_node` factory (`fresh = dedup_filter(raw)[:max_items]`, `deduped`) — `src/curation/nodes.py`
- [ ] Task 2.7: Implement `summarize_node` factory with per-item try/except (`cards`, `summarized`, `failed`); import only `bedrock.summarize` + `Card` (no boto3) — `src/curation/nodes.py`
- [ ] Task 2.8: Implement `rank_node` (relevance descending, stable) — `src/curation/nodes.py`
- [ ] Task 2.9: Implement `persist_node` factory (`store.upsert(cards)`) — `src/curation/nodes.py`

## Phase 3: Integration
- [ ] Task 3.1: Implement `build_graph(store, discoverer)`: StateGraph, add 5 nodes bound to deps, wire START→discover→dedup→summarize→rank→persist→END, return `compile()` — `src/curation/graph.py`
- [ ] Task 3.2: Create local entrypoint mirroring `run_spike.py`: sys.path inject, build local defaults, `graph.invoke({"max_items": config.MAX_ITEMS})`, render cards + print counters; support `--force` — `run_curation.py`
- [ ] Task 3.3: Manual smoke run `uv run run_curation.py` vs real Bedrock; confirm cards render + `.spike_cache/` writes (use `--force`/throwaway dir to avoid clobber)

## Phase 4: Testing & Validation
- [ ] Task 4.1: `uv add --dev pytest`; create `tests/` with sys.path-to-src conftest — `pyproject.toml`, `tests/conftest.py`
- [ ] Task 4.2: Store tests (T7–T10): dedup/force, idempotency+url-hash bridge, save shape, RssDiscoverer delegation — `tests/test_local_store.py`
- [ ] Task 4.3: Graph tests (T1, T3, T6): node set, rank order, no-boto3-in-nodes — `tests/test_graph.py`
- [ ] Task 4.4: Resilience + idempotency tests (T4, T5, T11) with stubbed `summarize` — `tests/test_graph.py`
- [ ] Task 4.5: No-regression test (T2): stubbed discover+summarize → graph output == spike-logic output, ranked — `tests/test_graph.py`
- [ ] Task 4.6: Run `uv run pytest`; all green; update audit.md statuses

## Blocked Items
[None yet]

## Notes
- Reuse, don't fork: import `RawItem`/`discover` from `spike.feeds`, `Card`/`render`
  from `spike.cards`, `summarize` from `spike.bedrock`, knobs from `spike.config`.
  Leave `src/spike/` untouched.
- Portability is the keystone constraint: no `boto3`/DynamoDB/file-path knowledge
  inside `nodes.py`/`graph.py`/`state.py`. The only Bedrock touchpoint in a node is
  the imported `bedrock.summarize`; all persistence/discovery goes through the
  injected Protocols.
- Preserve exact spike order: dedup → cap (`fresh[:max_items]`) → summarize →
  rank descending. Do not cap before dedup.
- Unit tests must monkeypatch `bedrock.summarize` — no live Bedrock calls in
  pytest; live calls only in the manual `uv run` smoke (Task 3.3).
- `Card` carries no `url_hash`; the store bridges via `Card.url` → sha256[:16].
- Defer entirely (other specs): Tavily, DynamoDB, AgentCore Runtime, embeddings,
  any Haiku-prompt / card-schema change.

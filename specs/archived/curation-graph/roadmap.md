# Roadmap: curation-graph

## Implementation Phases

### Phase 1: Foundation — dependency, package, Protocols, state
**Goal**: Stand up the `src/curation/` package, add LangGraph, and define the
seam (Protocols + state) Specs 02–04 depend on. No graph wiring yet.
**Dependencies**: None
**Estimated complexity**: Low

(make sure the .venv is activated)

1. `uv add langgraph` — updates `pyproject.toml` + `uv.lock`. Confirm `uv sync`
   succeeds and `uv run python -c "import langgraph"` works.
2. ~~(Recommended) Before writing graph code, verify the current LangGraph
   `StateGraph` API via Context7 / current docs.~~ **Done (2026-06-10, Context7
   `/langchain-ai/langgraph` v1.x):** `from langgraph.graph import StateGraph,
   START, END` is current; nodes are plain functions returning partial-state
   dicts; wiring is `add_node`/`add_edge`, then `.compile()` and
   `.invoke(initial_state)` — exactly as the contract assumes. No rework needed.
3. Create `src/curation/__init__.py`.
4. Create `src/curation/interfaces.py` with the `Discoverer` and `CardStore`
   `Protocol`s exactly as in contract.md (runtime_checkable, importing `RawItem`
   and `Card` from spike).
5. Create `src/curation/state.py` with the `CurationState` `TypedDict`
   (`total=False`) exactly as in contract.md.

### Phase 2: Core Logic — local defaults + nodes
**Goal**: Reproduce Phase 0 behavior behind the Protocols and as node functions.
**Dependencies**: Phase 1
**Estimated complexity**: Medium

1. `src/curation/local.py`: implement `RssDiscoverer` (wraps
   `feeds.discover(config.FEEDS, per_feed=config.PER_FEED)`).
2. `src/curation/local.py`: implement `JsonFileCardStore`:
   - `__init__(seen_path, cards_path, force)` defaulting to `config.SEEN_PATH` /
     `config.CARDS_PATH`.
   - `_load_seen()` and the url-hash derivation from `Card.url` (Guarantee 8).
   - `dedup_filter` (order-preserving; honors `force`).
   - `upsert` (accumulate seen, write `seen.json` sorted + `cards.json` as the
     batch, `indent=2`, `mkdir(parents=True, exist_ok=True)` — mirror spike `_save`).
3. `src/curation/nodes.py`: implement `discover_node`, `dedup_node`,
   `summarize_node` (per-item try/except → `failed`), `rank_node`, `persist_node`
   as factory functions/closures that capture `store` / `discoverer`.
   - `dedup_node` applies `dedup_filter` then `[: max_items]`; `deduped` counter
     = count after dedup (pre-cap), per state doc.
   - Node code imports `spike.bedrock.summarize` and `spike.cards.Card` only —
     no `boto3`.

### Phase 3: Integration — graph wiring + entrypoint
**Goal**: Compile the StateGraph and run it locally against real Bedrock.
**Dependencies**: Phase 2
**Estimated complexity**: Low

1. `src/curation/graph.py`: `build_graph(store, discoverer)`:
   - `g = StateGraph(CurationState)`, `add_node` each of the five nodes (bound to
     deps), wire `START → discover → dedup → summarize → rank → persist → END`,
     `return g.compile()`.
2. `run_curation.py` (repo root): mirror `run_spike.py` — insert `src/` on
   `sys.path`, build `JsonFileCardStore(force="--force" in argv)` + `RssDiscoverer`,
   `graph = build_graph(store, discoverer)`, `final = graph.invoke({"max_items":
   config.MAX_ITEMS})`, then `render(final["cards"])` and print the run-summary
   counters.
3. Manual smoke run: `uv run run_curation.py` against real Bedrock; confirm cards
   render and `.spike_cache/` files write. (Use a throwaway cache dir or `--force`
   to compare against the spike without clobbering.)

### Phase 4: Testing & Validation
**Goal**: Prove every contract guarantee, including no-regression vs spike, with
Bedrock mocked (no live calls in unit tests).
**Dependencies**: Phase 3
**Estimated complexity**: Medium

1. Add a test runner convention: `uv add --dev pytest` (tests live in `tests/`).
2. Unit tests for `JsonFileCardStore` (dedup idempotency, force, url-hash bridge)
   and `RssDiscoverer` (with `feeds.discover` monkeypatched).
3. Graph tests with `spike.bedrock.summarize` monkeypatched to a deterministic
   stub: node set assertion, rank order, per-item failure counter, idempotent
   re-run yields zero cards, portability (no `boto3` symbol in node module).
4. A no-regression test: same stubbed `discover`+`summarize` fed through both
   `spike.pipeline` logic and the graph yields the same ranked card list.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LangGraph API differs from assumed import/return shape | ~~Med~~ **Resolved** | Med | Verified via Context7 on 2026-06-10 — current v1.x API matches the contract exactly; contract still isolates the API to `graph.py` only |
| `Card` lacks `url_hash`, breaking dedup-after-upsert | High (known) | High | Guarantee 8: derive hash from `Card.url` with the exact `RawItem.url_hash` rule; unit-test the bridge |
| Accidental infra import leaks into node code (breaks portability) | Med | High | Guarantee 6 + a test asserting `boto3` not importable-referenced in `nodes.py`; code review |
| Behavioral drift from spike (cap-before-dedup, unstable sort) | Med | High | Guarantee 2/3/7 pin exact order; no-regression test in Phase 4 |
| Live Bedrock calls in unit tests (cost/flakiness) | Med | Low | Monkeypatch `summarize` in all unit tests; live calls only in the manual `uv run` smoke |
| `.spike_cache/` clobbered while comparing to spike | Low | Low | Entrypoint supports a custom cache dir / `--force`; tests use `tmp_path` |

## File Change Map

- `pyproject.toml` — MODIFY — add `langgraph` (and dev `pytest`) via `uv add`.
- `uv.lock` — MODIFY — regenerated by `uv add` (source of truth for versions).
- `src/curation/__init__.py` — CREATE — package marker.
- `src/curation/interfaces.py` — CREATE — `Discoverer`, `CardStore` Protocols.
- `src/curation/state.py` — CREATE — `CurationState` TypedDict.
- `src/curation/local.py` — CREATE — `RssDiscoverer`, `JsonFileCardStore` defaults.
- `src/curation/nodes.py` — CREATE — the five node factory functions.
- `src/curation/graph.py` — CREATE — `build_graph(store, discoverer)`.
- `run_curation.py` — CREATE — local `uv run` entrypoint (mirrors `run_spike.py`).
- `tests/test_local_store.py` — CREATE — `JsonFileCardStore`/`RssDiscoverer` tests.
- `tests/test_graph.py` — CREATE — graph behavior + portability + no-regression.
- `src/spike/**` — UNCHANGED — reference implementation, do not edit.

# Intent: curation-graph

## Problem Statement

The Phase 0 spike (`src/spike/pipeline.py`) implements the curation loop —
`discover → dedup → summarize → build Card → rank → render/save` — as one linear
plain-Python function. That shape works locally but does not match the target
design's "logic layer" (`docs/app-design-on-agentcore.md` §6): a typed,
inspectable LangGraph `StateGraph` with explicit nodes, run-level state, and
per-node resilience.

More importantly, `pipeline.run()` reaches directly into infrastructure: it reads
and writes JSON files in `.spike_cache/` and calls `feeds.discover` against RSS
inline. That coupling blocks every downstream Phase 1 spec:

- Spec 02 (`tavily-discovery`) needs to swap/compose the discovery source.
- Spec 03 (`dynamodb-card-store`) needs to swap the persistence + dedup backend.
- Spec 04 (`runtime-packaging`) needs to run the *unchanged* graph on AgentCore
  Runtime with those production backends injected.

This feature refactors the spike loop into a LangGraph `StateGraph` whose node
functions contain zero AWS-infra coupling. Discovery and persistence move behind
two injected Protocols (`Discoverer`, `CardStore`) with local default
implementations that exactly reproduce today's behavior. The affected party is
the developer building Phase 1: a clean node/state/interface boundary here means
Specs 02–04 "slot in cleanly" instead of forcing a rewrite.

## Goals

1. Refactor the spike loop into an explicit LangGraph `StateGraph` with named
   nodes (`discover → dedup → summarize → rank → persist`) and a typed
   `CurationState`.
2. Expose `build_graph(store: CardStore, discoverer: Discoverer) -> CompiledGraph`
   as the single public construction API; dependencies are injected, never
   imported inside node code.
3. Define the `Discoverer` and `CardStore` Protocols as the stable seam Specs
   02–04 plug into, with local default implementations.
4. Preserve per-item failure resilience: one bad item is counted and skipped, the
   run still completes.
5. Reproduce Phase 0 behavior exactly with the local defaults — same cards, same
   ranking, same idempotency (re-run with unchanged seen store yields zero new
   cards).
6. Keep the whole thing runnable locally via a `uv run` entrypoint against real
   Bedrock, with `src/spike/` left intact as reference.

## Success Criteria

(Maps 1:1 to the brief's acceptance checklist in
`tasks/phase-1-curation-mvp/01-langgraph-curation-graph.md`.)

- [ ] `build_graph(store, discoverer)` returns a compiled LangGraph graph with the
      named nodes (`discover`, `dedup`, `summarize`, `rank`, `persist`).
- [ ] Invoking the compiled graph locally with the JSON-file `CardStore` default
      reproduces the spike's output (same set of cards, ranked by relevance
      descending) — no behavioral regression vs Phase 0.
- [ ] A single failing item (e.g. `summarize` raises) is counted in
      `state["failed"]` and skipped; the run still completes and persists the
      remaining cards.
- [ ] Node functions contain no `boto3` / AWS-infra imports — only the injected
      Protocols and the existing `bedrock.summarize` helper.
- [ ] Re-running with an unchanged `seen` store produces zero new cards (dedup
      works through the `CardStore.dedup_filter` seam).
- [ ] A `uv run` entrypoint (`run_curation.py`) compiles and invokes the graph
      end-to-end against real Bedrock.

## Non-Goals

- Tavily / web-search discovery (Spec 02 supplies a Tavily `Discoverer`).
- DynamoDB persistence or dedup (Spec 03 supplies the `CardStore` impl).
- AgentCore Runtime / containerization / Secrets Manager (Spec 04).
- Embeddings / vector store (Phase 3).
- Any change to the Haiku prompt, the forced-tool-call summarize contract, or the
  `Card` schema beyond *reserving* fields for later phases.
- Removing or modifying `src/spike/` — it stays intact as the reference.
- Per-node retry policies / branching beyond the linear pipeline (the graph shape
  enables them later; this spec only establishes it).

## Constraints

- **Portability (the keystone constraint):** node functions must have zero
  AWS-infra coupling — no `boto3` import, no file-path/DynamoDB knowledge. The
  only infra touch allowed inside a node is calling the injected `Discoverer` /
  `CardStore` Protocols and the existing `bedrock.summarize` helper.
- **Reuse, don't fork:** import `cards.Card`, `bedrock.summarize`, `feeds.discover`
  (and `feeds.RawItem`) from `src/spike/`. New code lives under `src/curation/`.
- **No behavioral regression:** the local default path must match the spike —
  same dedup-then-cap order, same `MAX_ITEMS`/`PER_FEED` knobs, same
  rank-by-relevance-descending, same `.spike_cache/` JSON outputs.
- **Tooling:** uv only (`uv add langgraph`); never pip/venv/requirements.txt.
  `[tool.uv] package = false` with `src/` layout; the entrypoint adds `src/` to
  `sys.path` (mirror `run_spike.py`).
- **Style:** match the lean spike conventions — small modules, dataclasses, lazy
  singletons, `from __future__ import annotations`, per-item try/except.
- **Budget:** Haiku for bulk summarization only; dedup must run before summarize
  so we never pay to summarize a duplicate.

## Prior Art

- `src/spike/pipeline.py` — the linear loop this refactors; the source of truth
  for behavior to preserve (dedup-then-cap, per-item try/except, rank, save).
- `src/spike/feeds.py` — `RawItem` dataclass (with `url_hash`) and `discover()`;
  wrapped by the default `Discoverer`.
- `src/spike/cards.py` — `Card` dataclass + `Card.from_model` + `render`; reused
  unchanged.
- `src/spike/bedrock.py` — `summarize(item)` forced-tool-call helper; called
  directly inside the `summarize` node (the one allowed Bedrock touchpoint).
- `src/spike/config.py` — env-overridable knobs (`MAX_ITEMS`, `PER_FEED`, `FEEDS`,
  `CACHE_DIR`, `SEEN_PATH`, `CARDS_PATH`); reused by the local defaults.
- `run_spike.py` — the `sys.path`-injecting entrypoint pattern `run_curation.py`
  mirrors.
- LangGraph `StateGraph` (TypedDict state, `add_node`/`add_edge`, `START`/`END`,
  `compile()`) — the framework introduced by this spec.

# Spec 01 — LangGraph curation graph

- **feature-name:** `curation-graph`
- **SDD target dir:** `specs/curation-graph/`
- **Depends on:** Phase 0 spike (`src/spike/`)
- **Layer:** Logic (LangGraph) — must stay infra-portable

## Intent

Refactor the Phase 0 plain-Python pipeline (`src/spike/pipeline.py`) into an
explicit **LangGraph `StateGraph`** so the curation workflow becomes a typed,
inspectable state machine with per-node retries and branching — the form the
design (§6) calls the "logic layer." The graph must remain runnable locally
(`uv run`) and contain **zero AWS-infra coupling**: persistence and discovery sit
behind interfaces so the same graph runs unchanged on AgentCore Runtime later.

This is the keystone of Phase 1. Get the node boundaries and state shape right and
every later spec slots in cleanly.

## Background — what the spike already does

`pipeline.run()` does, in plain Python: `discover` (RSS via `feeds.discover`) →
dedup against a `seen` set → `summarize` each item with Haiku (forced tool call,
`bedrock.summarize`) → build `Card` → sort by `relevance` → render + save JSON.
Keep all of this logic; only the **shape** changes (nodes + state + interfaces).

## Scope

**In scope**
- Define a `CurationState` (TypedDict/dataclass) carrying: raw items, fresh items,
  cards, run-level counters, and config knobs (`max_items`, `per_feed`).
- Model the loop as graph nodes, e.g.: `discover → dedup → summarize → tag_score →
  rank → persist`. (`summarize` and `tag_score` may be one node — the spike's
  forced tool call already returns tags+type+relevance; the architect decides
  whether to split for a future re-scoring step.)
- Per-item resilience: one bad item must not kill the run (preserve the spike's
  per-item try/except), surfaced as a counter in state.
- Define two **Protocols** the graph depends on, with local default impls:
  - `CardStore` — `dedup_filter(items) -> fresh`, `upsert(cards)`, plus whatever
    Spec 02 needs. Local default: the current JSON-file behavior.
  - `Discoverer` — wraps `feeds.discover` (RSS default impl). The Protocol is the
    seam Spec 02 plugs Tavily into and combines RSS + Tavily behind one composite,
    so define it cleanly here even though RSS is the only source in this spec.
- A thin local entrypoint (e.g. keep `run_spike.py` working, or add
  `run_curation.py`) that compiles and invokes the graph against local impls.
- Keep `cards.Card`, `bedrock.summarize`, `feeds.discover` reusable (import, don't
  fork). New code lives in `src/curation/` (or agreed module) — leave `src/spike/`
  intact as the reference.

**Out of scope**
- Tavily / web-search discovery (Spec 02 supplies a Tavily `Discoverer`).
- DynamoDB (Spec 03 supplies the `CardStore` impl).
- AgentCore Runtime / containerization (Spec 04).
- Embeddings / vector store (Phase 3).
- Any change to the Haiku prompt or card schema beyond reserving fields.

## Contract sketch (architect to formalize)

```python
class CardStore(Protocol):
    def dedup_filter(self, items: list[RawItem]) -> list[RawItem]: ...
    def upsert(self, cards: list[Card]) -> None: ...

class Discoverer(Protocol):
    def discover(self) -> list[RawItem]: ...

def build_graph(store: CardStore, discoverer: Discoverer) -> CompiledGraph: ...
```

State flows discover→…→persist; the compiled graph is pure logic and takes its
dependencies by injection (so Specs 02–04 pass Tavily + DynamoDB + Runtime variants).

## Acceptance criteria

- [ ] `build_graph(...)` returns a compiled LangGraph graph with the named nodes.
- [ ] Invoking it locally reproduces the spike's output (same cards, ranked) using
      the JSON-file `CardStore` default — i.e. no behavioral regression vs Phase 0.
- [ ] A single failing item is counted and skipped; the run still completes.
- [ ] Node functions contain no `boto3`/AWS-infra imports — only the injected
      Protocols and existing Bedrock helpers.
- [ ] Re-running with an unchanged `seen` store produces zero new cards (dedup works).
- [ ] `uv run` entrypoint executes the graph end-to-end against real Bedrock.

## SDD note

Feed this file to `sdd-architect` with feature name `curation-graph`. Emphasize
the **portability constraint** (no infra in node code) in `contract.md` — it is
the property Specs 02–04 rely on.

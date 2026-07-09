# Contract: curation-graph

> All new code lives under `src/curation/`. It **imports** (never forks)
> `RawItem` from `spike.feeds`, `Card` from `spike.cards`, `summarize` from
> `spike.bedrock`, `discover`/`RawItem` from `spike.feeds`, and config knobs from
> `spike.config`. Import style matches the spike (`from spike.X import Y` once
> `src/` is on `sys.path`).

## Interfaces

### Injected Protocols (`src/curation/interfaces.py`)

These two Protocols are the **stable seam** Specs 02–04 depend on. They are
defined here and must not change shape without amending this contract.

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from spike.cards import Card
from spike.feeds import RawItem


@runtime_checkable
class Discoverer(Protocol):
    """Source of raw candidate items. Spec 02 supplies a Tavily+RSS composite."""

    def discover(self) -> list[RawItem]:
        """Return raw candidate items from one or more sources.

        Implementations own their own source config (feeds, per-feed caps,
        API keys). Must not raise on a single bad source — degrade and
        return what it could fetch.
        """
        ...


@runtime_checkable
class CardStore(Protocol):
    """Persistence + dedup backend. Spec 03 supplies a DynamoDB impl."""

    def dedup_filter(self, items: list[RawItem]) -> list[RawItem]:
        """Return only items not already curated (URL-hash exact dedup).

        Order-preserving. Must be idempotent: calling it again after upsert
        of the resulting cards returns an empty list for the same inputs.
        """
        ...

    def upsert(self, cards: list[Card]) -> None:
        """Persist (insert-or-replace) the given cards and record them as seen.

        After this returns, the url_hash of every persisted card's source item
        must be excluded by a subsequent dedup_filter (idempotency guarantee).
        """
        ...
```

### Local default implementations (`src/curation/local.py`)

Reproduce Phase 0 behavior exactly. No new behavior, only the same logic behind
the Protocols.

```python
class RssDiscoverer:
    """Default Discoverer: wraps spike.feeds.discover over config.FEEDS."""

    def __init__(
        self,
        feeds: dict[str, str] | None = None,
        per_feed: int | None = None,
    ) -> None:
        # default to spike.config.FEEDS / config.PER_FEED
        ...

    def discover(self) -> list[RawItem]:
        """feeds.discover(self.feeds, per_feed=self.per_feed)."""
        ...


class JsonFileCardStore:
    """Default CardStore: the spike's .spike_cache/ JSON-file behavior.

    seen.json  -> set[str] of url_hash (idempotency)
    cards.json -> list[Card.to_dict()] (the rendered/ranked output)
    """

    def __init__(
        self,
        seen_path: Path | None = None,   # default config.SEEN_PATH
        cards_path: Path | None = None,  # default config.CARDS_PATH
        force: bool = False,             # force=True ignores the seen set (re-summarize all)
    ) -> None:
        ...

    def dedup_filter(self, items: list[RawItem]) -> list[RawItem]:
        """Drop items whose url_hash is in the loaded seen set (unless force)."""
        ...

    def upsert(self, cards: list[Card]) -> None:
        """Add card url_hashes to seen, write seen.json + cards.json.

        NOTE: cards.json is written as the FULL current batch passed in
        (matches the spike, which writes the run's ranked cards). The seen set
        accumulates across runs.
        """
        ...
```

> `JsonFileCardStore.upsert` must persist the same `seen` accumulation and
> `cards.json` shape the spike's `_save` produced (`json.dumps(..., indent=2)`,
> `sorted(seen)`, `[c.to_dict() for c in cards]`). `upsert` needs each card's
> source `url_hash`; since `Card` does not carry it, the store derives it from
> `Card.url` via the same `hashlib.sha256(url)[:16]` rule as `RawItem.url_hash`
> (documented invariant — see Behavior Guarantee 8).

### Graph state (`src/curation/state.py`)

```python
from __future__ import annotations

from typing import TypedDict

from spike.cards import Card
from spike.feeds import RawItem


class CurationState(TypedDict, total=False):
    # config knobs (set at invoke time; defaults from spike.config)
    max_items: int          # cap on items summarized this run (config.MAX_ITEMS)

    # data flowing through the pipeline
    raw: list[RawItem]      # discover -> all discovered items
    fresh: list[RawItem]    # dedup    -> after dedup_filter, capped to max_items
    cards: list[Card]       # summarize-> built+ok cards; rank -> sorted descending

    # run-level counters (run summary; consumed by Spec 06 later)
    discovered: int         # len(raw)
    deduped: int            # len(fresh) before cap is applied note below
    summarized: int         # cards successfully built
    failed: int             # items that raised during summarize and were skipped
```

> `per_feed` is owned by the `Discoverer` (it configures its own sources), so it
> is **not** a `CurationState` field — only `max_items` is a graph-level knob.
> This keeps the state source-agnostic for Spec 02.

### Public construction API (`src/curation/graph.py`)

```python
from __future__ import annotations

from langgraph.graph import StateGraph  # CompiledStateGraph is the return type

from .interfaces import CardStore, Discoverer
from .state import CurationState


def build_graph(store: CardStore, discoverer: Discoverer):
    """Build and compile the curation StateGraph.

    Wires nodes discover -> dedup -> summarize -> rank -> persist with
    `discoverer` and `store` captured by closure (dependency injection).
    Returns the compiled graph (langgraph CompiledStateGraph); call
    `.invoke({"max_items": N})` to run it.

    The compiled graph is PURE LOGIC: no node closes over boto3, file paths,
    or DynamoDB — only over `store`, `discoverer`, and `bedrock.summarize`.
    """
    ...
```

### Nodes (`src/curation/nodes.py`)

Node functions are closures (or partials) bound to the injected dependencies.
Each takes `CurationState` and returns a partial state update (LangGraph merges
it). Signatures:

```python
def discover_node(state: CurationState) -> CurationState:
    """raw = discoverer.discover(); discovered = len(raw)."""

def dedup_node(state: CurationState) -> CurationState:
    """fresh = store.dedup_filter(raw)[: max_items]; deduped = len(fresh_before_cap)."""

def summarize_node(state: CurationState) -> CurationState:
    """For each fresh item: try summarize() -> Card.from_model; per-item
    try/except increments `failed` on error and continues. summarized = ok count."""

def rank_node(state: CurationState) -> CurationState:
    """cards sorted by relevance descending (stable)."""

def persist_node(state: CurationState) -> CurationState:
    """store.upsert(cards). Returns state unchanged."""
```

> `bedrock.summarize` is the **only** Bedrock/AWS touchpoint permitted inside a
> node, and it is the existing spike helper imported as-is. No `boto3` import
> appears in any `src/curation/` node module.

## Behavior Guarantees

1. `build_graph(store, discoverer)` returns a compiled LangGraph graph whose node
   set is exactly `{discover, dedup, summarize, rank, persist}`, wired linearly
   `START → discover → dedup → summarize → rank → persist → END`.
2. Invoking the compiled graph with the `JsonFileCardStore` + `RssDiscoverer`
   defaults produces the same set of `Card`s, ranked by `relevance` descending,
   that `spike.pipeline.run()` produces for the same inputs (no regression).
3. Dedup runs **before** summarize and the cap: `fresh = dedup_filter(raw)` then
   sliced to `max_items` — we never summarize an item already seen, never pay
   twice (preserves the spike's `fresh = [...]; batch = fresh[:MAX_ITEMS]` order).
4. A `summarize` call that raises for one item increments `state["failed"]` by 1,
   that item is skipped, and the run continues to completion and persists the
   remaining cards (preserves the spike's per-item try/except).
5. Re-invoking the graph with an unchanged `seen` store (a `JsonFileCardStore`
   over a populated `seen.json`, `force=False`) yields zero new cards: `fresh`
   is empty, `cards` is empty, and `persist` writes an empty `cards.json` while
   leaving `seen.json` unchanged (idempotency).
6. No node module under `src/curation/` imports `boto3` or references AWS infra
   (DynamoDB, file paths) directly; the only infra access inside nodes is through
   the injected `Discoverer`/`CardStore` Protocols and `bedrock.summarize`.
7. `cards` order after `rank` is `relevance`-descending and stable for ties
   (Python's `sort` is stable; matches `cards.sort(key=..., reverse=True)`).
8. `JsonFileCardStore` derives a card's seen-key from `Card.url` using the same
   rule as `RawItem.url_hash` (`hashlib.sha256(url.encode()).hexdigest()[:16]`),
   so `dedup_filter` after `upsert` excludes the same items (idempotency bridge
   between `RawItem` and `Card`).
9. The graph is constructed by injection only: passing a different `Discoverer`
   or `CardStore` (Specs 02/03) changes behavior without editing
   `graph.py`/`nodes.py`/`state.py`.

## Error Handling Contract

| Error Condition | Behavior | User Impact |
|---|---|---|
| `summarize(item)` raises (Bedrock error, malformed item) | per-item try/except in `summarize_node`: log/print, `failed += 1`, skip item, continue | Item omitted from feed; run completes; counter reflects the miss |
| A single feed/source fails inside `Discoverer.discover` | `Discoverer` degrades (spike `feeds.discover` already skips bozo feeds), returns what it got | Fewer raw items; run completes |
| `discover` returns zero items | `dedup`/`summarize` produce empty `cards`; `persist` writes empty `cards.json`, `seen.json` unchanged | Empty feed for the run; no crash |
| All `fresh` items already seen (idempotent re-run) | `fresh` empty → `cards` empty → empty `cards.json` written, `seen` unchanged | Zero new cards (expected) |
| `CardStore.upsert` raises (e.g. disk error) | propagates out of `persist_node` (run fails loudly) — persistence is not best-effort | Run errors; nothing silently lost |
| `bedrock.summarize` returns no `toolUse` block | it raises `RuntimeError` (existing spike behavior) → handled as a per-item failure (row 1) | Item skipped, counted |

## Dependencies

- **Internal (imported, not forked):**
  - `spike.feeds.RawItem`, `spike.feeds.discover`
  - `spike.cards.Card` (and `spike.cards.render` for the entrypoint's console output)
  - `spike.bedrock.summarize`
  - `spike.config` (`MAX_ITEMS`, `PER_FEED`, `FEEDS`, `CACHE_DIR`, `SEEN_PATH`,
    `CARDS_PATH`)
- **External (new):**
  - `langgraph` (add via `uv add langgraph`; pulls `langchain-core`). Pin the
    resolved version in `uv.lock`. Verify the exact `StateGraph`/`START`/`END`
    import path against current LangGraph docs (Context7) before coding —
    `from langgraph.graph import StateGraph, START, END` is the expected path.
- **External (existing):** `boto3` (only via `spike.bedrock`), `feedparser`,
  `rich`, `python-dotenv` — already in `pyproject.toml`.

## Integration Points

- **Spec 02 (`tavily-discovery`)** provides an alternative `Discoverer`
  (composite RSS + Tavily) passed to `build_graph` — no graph/node edits.
- **Spec 03 (`dynamodb-card-store`)** provides an alternative `CardStore`
  (DynamoDB) passed to `build_graph` — no graph/node edits. The `dedup_filter` /
  `upsert` semantics defined here are the contract it must satisfy.
- **Spec 04 (`runtime-packaging`)** imports `build_graph` and invokes the
  *unchanged* compiled graph with the production `Discoverer`+`CardStore` on
  AgentCore Runtime. The portability guarantee (Guarantee 6) is what makes this
  a no-code-change packaging step.
- **Spec 06 (`run-observability`)** consumes the run-level counters
  (`discovered`, `deduped`, `summarized`, `failed`) from final state as the run
  summary — they are defined in `CurationState` now so 06 has a stable shape.
- **Local entrypoint** `run_curation.py` (repo root) mirrors `run_spike.py`:
  adds `src/` to `sys.path`, builds the graph with local defaults, invokes it,
  and renders the resulting cards via `spike.cards.render`.

# Contract: tavily-discovery

> All new code lives under `src/curation/`, alongside Spec 01. It **imports**
> (never forks) `RawItem` from `spike.feeds`, `Card` from `spike.cards`, the
> `_clean` snippet normalizer from `spike.feeds`, and mirrors the `spike.config`
> knob pattern. `src/curation/interfaces.py` (the `Discoverer` Protocol) is the
> stable seam and is **not modified**. Import style matches the spike
> (`from spike.X import Y` once `src/` is on `sys.path`).

## Tavily API surface (pinned from Context7 — `/tavily-ai/tavily-python`)

Verified against current `tavily-python` docs on 2026-07-13 (do not trust
memory). Package name `tavily-python`, import module `tavily`.

```python
from tavily import TavilyClient

client = TavilyClient(api_key="tvly-...")   # api_key param takes precedence over env

response: dict = client.search(
    query="latest large language model releases",   # required
    search_depth="basic",          # "basic" | "advanced" | "fast" | "ultra-fast"
    topic="general",               # "general" | "news" | "finance"
    days=7,                         # last N days (mutually exclusive w/ time_range, start/end)
    max_results=5,                 # 1..100, per-query
    include_domains=[],            # Sequence[str] — empty = no restriction
    exclude_domains=[],            # Sequence[str]
    include_raw_content=False,     # False | "markdown" | "text" (full-page fetch; OFF by default)
    timeout=60,                    # seconds (<=120)
)
```

Response shape (only the fields this spec relies on):

```python
{
    "query": str,
    "answer": None,              # unused (include_answer left False)
    "results": [
        {
            "title": str,        # -> RawItem.title
            "url": str,          # -> RawItem.url (and url_hash)
            "content": str,      # snippet/summary -> RawItem.snippet
            "score": float,      # 0.0..1.0 relevance (NOT used; Card.relevance comes from Haiku)
            "raw_content": str | None,   # present only if include_raw_content set
            "published_date": str,       # present only when topic="news" -> RawItem.published
        },
        ...
    ],
    "response_time": float,
    # (images / favicon / follow_up_questions may appear; ignored)
}
```

Notes pinned from the docs:
- Only `title`, `url`, `content`, `score` are **always present** per result;
  everything else is conditional on request params.
- `published_date` is emitted for `topic="news"`; for `topic="general"` it is
  absent, so `RawItem.published` degrades to `""` (same as an RSS entry with no
  date). Map via `result.get("published_date", "")`.
- Known SDK exceptions: `InvalidAPIKeyError` (401), `UsageLimitExceededError`
  (429), `BadRequestError` (400), `ForbiddenError` (403/432/433), `TimeoutError`.
  This spec catches broadly (`except Exception`) at the degrade boundaries rather
  than pinning exception classes — mirrors the spike's per-item `except Exception`.

## Interfaces

### Config knobs (`src/curation/config.py` — CREATE, mirrors `spike.config`)

New module so `src/spike/` stays untouched (Spec 01 constraint). Env-overridable
module-level constants, same style as `spike.config`.

```python
"""Curation-plane config for web discovery — env-overridable, sensible defaults."""
from __future__ import annotations

import os

# Tavily API key — LOCAL ONLY (.env / env var). Secrets Manager resolution is
# Spec 04 (runtime-packaging); no boto3 here. Empty string when unset.
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

# Topic seed queries (design §5 topic areas). Override with a ';'-separated list.
_DEFAULT_SEEDS = [
    "latest large language model releases and updates",
    "new generative AI and LLM research papers",
    "AI agents and agentic framework news",
    "machine learning and deep learning breakthroughs",
    "open source AI model and tooling releases",
]
TAVILY_SEEDS: list[str] = [
    s.strip()
    for s in os.getenv("CURATION_TAVILY_SEEDS", ";".join(_DEFAULT_SEEDS)).split(";")
    if s.strip()
]

# Tunables (all env-overridable). MAX_RESULTS is the PRIMARY COST LEVER (§7).
TAVILY_RESULTS_PER_QUERY: int = int(os.getenv("CURATION_TAVILY_RESULTS_PER_QUERY", "5"))
TAVILY_MAX_RESULTS: int = int(os.getenv("CURATION_TAVILY_MAX_RESULTS", "20"))
TAVILY_DAYS: int = int(os.getenv("CURATION_TAVILY_DAYS", "7"))
TAVILY_SEARCH_DEPTH: str = os.getenv("CURATION_TAVILY_SEARCH_DEPTH", "basic")
TAVILY_TOPIC: str = os.getenv("CURATION_TAVILY_TOPIC", "general")


def _csv(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [d.strip() for d in raw.split(",") if d.strip()]


TAVILY_INCLUDE_DOMAINS: list[str] = _csv("CURATION_TAVILY_INCLUDE_DOMAINS")
TAVILY_EXCLUDE_DOMAINS: list[str] = _csv("CURATION_TAVILY_EXCLUDE_DOMAINS")
```

> `spike.config` already calls `load_dotenv()` at import; this project imports
> `spike.config` at startup (via the graph/entrypoint), so `.env` is loaded before
> `curation.config` reads `os.getenv`. `curation.config` does not call
> `load_dotenv()` again (idempotent, but relies on the spike import path — the
> smoke entrypoint imports `spike.config` first, as `run_curation.py` does).

### `TavilyDiscoverer` (`src/curation/tavily.py` — CREATE)

Implements the Spec 01 `Discoverer` Protocol. Infra-edge adapter: the only place
the `tavily` SDK is imported. Lazy singleton client mirrors
`spike.bedrock.bedrock_client()`.

```python
from __future__ import annotations

from spike.feeds import RawItem


class TavilyDiscoverer:
    """Discoverer over Tavily web search (topic-seeded, content-extracting).

    Implements the Spec 01 `Discoverer` Protocol. Never raises past discover():
    a failing seed is logged + counted and skipped; a total outage returns [].
    """

    def __init__(
        self,
        seeds: list[str],
        api_key: str,
        *,
        max_results: int,               # hard per-run total cap (PRIMARY cost lever)
        results_per_query: int = 5,
        days: int = 7,
        search_depth: str = "basic",
        topic: str = "general",
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> None: ...

    @classmethod
    def from_config(cls) -> "TavilyDiscoverer":
        """Build from `curation.config` knobs. Raises ValueError if TAVILY_API_KEY
        is unset (fail fast at construction — the smoke entrypoint surfaces this)."""
        ...

    def discover(self) -> list[RawItem]:
        """Search each seed, map results -> RawItem, dedup by url_hash within this
        source, and return at most `max_results` items. Per-seed try/except:
        a failing query is logged + skipped, others still run. Total failure
        (or unset key handled upstream) yields [] — never raises."""
        ...

    def failures(self) -> int:
        """Count of seed queries that raised during the last discover() (0 if
        clean). Lets a caller/observer surface degraded runs (Spec 06)."""
        ...
```

Behavior of `discover()`:
1. Lazily construct one `TavilyClient(api_key=...)` (singleton per instance).
2. For each seed in `self.seeds`: call `client.search(query=seed, ...)` with the
   configured knobs, wrapped in `try/except Exception` → on error, print a
   `! tavily seed failed: ...` line, increment the failure counter, `continue`.
3. Map each result dict to a `RawItem`:
   - `source` = `f"Tavily: {topic}"` (constant per instance; stable, human-readable).
   - `title` = `_clean(result["title"], limit=300)` (reuse `spike.feeds._clean`).
   - `url` = `result["url"]`.
   - `published` = `result.get("published_date", "")`.
   - `snippet` = `_clean(result.get("content", ""))` (reuse `_clean`, default 1500 clamp).
   - Skip a result missing `url` or `title` (mirrors `feeds.discover`).
4. Dedup within-source by `RawItem.url_hash` (first occurrence wins), preserving
   discovery order across seeds.
5. Truncate to `self.max_results` (the cap) and return.

### `CompositeDiscoverer` (`src/curation/composite.py` — CREATE)

Implements the `Discoverer` Protocol. Source-agnostic (knows nothing about Tavily
or RSS specifically — only the Protocol). Runs each source, merges, dedups.

```python
from __future__ import annotations

from spike.feeds import RawItem

from .interfaces import Discoverer


class CompositeDiscoverer:
    """Run several Discoverers, merge their RawItems, drop cross-source
    URL-hash duplicates (first source wins). One source failing does not sink
    the run — its exception is caught, logged, counted, and the others proceed."""

    def __init__(self, sources: list[Discoverer]) -> None: ...

    def discover(self) -> list[RawItem]:
        """For each source: try source.discover(); on exception log
        `! discoverer failed: ...`, increment failure counter, continue with []
        for that source. Concatenate results in source order, then dedup by
        url_hash preserving first occurrence. Returns the merged, deduped list."""
        ...

    def failures(self) -> int:
        """Number of sources whose discover() raised during the last run."""
        ...
```

Behavior of `discover()`:
1. Iterate `self.sources` **in order** (so `[RssDiscoverer(), TavilyDiscoverer(...)]`
   means RSS wins URL-hash ties — the RSS variant of a shared article is kept).
2. Per source: `try: items = source.discover()` / `except Exception:` log +
   `failures += 1`, treat as `items = []`, continue.
3. Concatenate all sources' items in order.
4. Dedup by `RawItem.url_hash`, keeping the first occurrence (order-preserving) —
   same exact-hash rule (`sha256(url)[:16]`) the store and RSS already use.
5. Return the merged, deduped list. The cap is per-source (Tavily's own
   `max_results`); the composite does not impose an additional cap (the graph's
   `max_items` still caps what gets summarized downstream, unchanged from Spec 01).

### API-key resolution (LOCAL ONLY)

```python
# curation/config.py
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")   # from .env or process env
```

The **only** resolution path in this spec. `TavilyDiscoverer.from_config()` reads
`config.TAVILY_API_KEY` and raises `ValueError("TAVILY_API_KEY is not set ...")`
if empty. There is **no** `boto3.client("secretsmanager")`, no secret-name knob,
and no cloud resolution here — that is Spec 04 (`runtime-packaging`). The key
never appears in source; `.env` is gitignored.

## State Changes

None to the graph. `CompositeDiscoverer` / `TavilyDiscoverer` are drop-in
`Discoverer`s passed to the **unchanged** `build_graph(store, discoverer)`.
`CurationState`, nodes, edges, and `interfaces.py` are untouched — the seam holds.
The only observable change flowing through the existing state is a larger, merged
`raw`/`discovered` count feeding `dedup`.

## Behavior Guarantees

1. `TavilyDiscoverer.discover()` returns `RawItem`s with `snippet` populated from
   Tavily's `content` field, and never returns more than `max_results` items
   (the per-run cap is enforced, the primary cost lever).
2. A single seed query raising inside `TavilyDiscoverer.discover()` is caught,
   logged, and counted (`failures()` increments); remaining seeds still run and
   their results are returned. `discover()` never raises.
3. A total Tavily failure (all seeds raise, or the client cannot be built) yields
   an empty list from `TavilyDiscoverer.discover()` — it does not raise.
4. `CompositeDiscoverer.discover()` returns the URL-hash-deduped union of its
   sources' items, order-preserving, first-source-wins on ties. The same article
   present in both RSS and Tavily appears **once**, so it is summarized once (§7).
5. If one source in a `CompositeDiscoverer` raises, its exception is caught,
   logged, and counted; the other sources' results are still returned (a Tavily
   outage degrades the run to RSS-only, healthy). `discover()` never raises.
6. Dedup uses the exact `RawItem.url_hash` rule (`sha256(url.encode())[:16]`) —
   identical to RSS, the store, and Spec 01 — so cross-source and later
   store-level dedup agree.
7. The Spec 01 graph runs unchanged: `build_graph(store, CompositeDiscoverer([...]))`
   compiles and invokes with **no** edit to `graph.py`/`nodes.py`/`state.py`/
   `interfaces.py`. (Guarantee that the seam is intact.)
8. The `tavily` SDK is imported **only** in `src/curation/tavily.py`; it does not
   appear in `nodes.py`/`graph.py`/`state.py`/`composite.py`/`interfaces.py`. No
   `boto3` appears anywhere in this spec's code (portability).
9. `TavilyDiscoverer` reads its key from `config.TAVILY_API_KEY`
   (env/`.env`) only; no Secrets Manager / boto3 code path exists in this spec.
10. All config knobs (seeds, results-per-query, days, search_depth, topic,
    include/exclude domains, max_results cap) are read from `curation.config`
    and are env-overridable.

## Error Handling Contract

| Error Condition | Behavior | User Impact |
|---|---|---|
| One Tavily seed query raises (quota/timeout/bad request) | per-seed `try/except` in `TavilyDiscoverer.discover()`: log `! tavily seed failed`, `failures += 1`, skip that seed, continue | Fewer web items that run; run completes |
| All Tavily seeds raise / total outage | `discover()` returns `[]` (never raises); `failures()` reflects the misses | No web items this run; run healthy on RSS |
| `TavilyDiscoverer` used in a `CompositeDiscoverer` and its `discover()` somehow raises | `CompositeDiscoverer` per-source `try/except`: log `! discoverer failed`, `failures += 1`, treat as `[]`, continue with other sources | Degrades to RSS-only output; run completes |
| `TAVILY_API_KEY` unset at `from_config()` | raises `ValueError` at construction (fail fast) — the smoke entrypoint surfaces it before any graph run | Clear setup error, not a silent empty feed |
| Tavily result missing `url` or `title` | skipped (mirrors `feeds.discover`'s guard) | That result omitted; others kept |
| Tavily result missing `published_date` (e.g. `topic="general"`) | `RawItem.published = ""` via `.get(..., "")` | Card shows "date n/a" (existing render) |
| Same article from RSS + Tavily | composite dedups by `url_hash`; first source (RSS) kept | Summarized once (no double Haiku spend) |

## Dependencies

- **Internal (imported, not forked):**
  - `spike.feeds.RawItem`, `spike.feeds._clean`
  - `spike.cards.Card` (via the unchanged graph; not imported directly here)
  - `curation.interfaces.Discoverer` (the stable Protocol — imported for typing,
    not modified)
- **External (new):**
  - `tavily-python` (import `tavily`) — add via `uv add tavily-python`; pin the
    resolved version in `uv.lock`. API surface verified via Context7
    (`/tavily-ai/tavily-python`, 2026-07-13): `TavilyClient(api_key=...).search(...)`
    signature and response shape pinned above.
- **External (existing):** `python-dotenv` (via `spike.config` `load_dotenv()`),
  `feedparser`/`rich`/`langgraph` (unchanged from Spec 01).

## Integration Points

- **Spec 01 (`curation-graph`)** — consumes `CompositeDiscoverer` via the
  unchanged `build_graph(store, discoverer)` and the unchanged `Discoverer`
  Protocol seam. No graph/node/state/interface edits.
- **Spec 03 (`dynamodb-card-store`)** — the store-level URL-hash dedup uses the
  same `sha256(url)[:16]` rule as this spec's cross-source dedup, so the two
  layers agree (composite trims intra-run cross-source dups; the store trims
  already-curated items across runs).
- **Spec 04 (`runtime-packaging`)** — will replace the local `TAVILY_API_KEY`
  env resolution with Secrets Manager resolution and add the CDK construct + IAM
  grant. This spec's `curation.config.TAVILY_API_KEY` is the single seam Spec 04
  swaps; `TavilyDiscoverer` takes `api_key` as a constructor arg, so Spec 04
  injects a Secrets-Manager-sourced key without touching `tavily.py`.
- **Spec 06 (`run-observability`)** — `TavilyDiscoverer.failures()` /
  `CompositeDiscoverer.failures()` expose degraded-run counts for the run summary.
- **Local smoke entrypoint**: originally a standalone `run_tavily.py`; post-audit
  (2026-07-15) folded into `run_curation.py`, which auto-selects
  `CompositeDiscoverer([RssDiscoverer(), TavilyDiscoverer.from_config()])` when
  `TAVILY_API_KEY` is set (else `CompositeDiscoverer([RssDiscoverer()])`) — one
  entrypoint instead of one-per-Discoverer-combination. Still adds `src/` to
  `sys.path`, builds `JsonFileCardStore`, calls `build_graph(store, discoverer)`,
  invokes, renders cards. This is the ONLY place that hits the real Tavily API.

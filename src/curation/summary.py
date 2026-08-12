"""Run-level summary + cost estimation for one curation pass (Spec 06)."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from spike import config as spike_config   # Bedrock unit prices (see contract §4)

from . import config                       # Tavily prices, namespace, toggles


@dataclass(frozen=True)
class RunSummary:
    """Everything one curation run is worth knowing about, in one immutable
    value. Field ORDER is the log record's key order — `run_id` and
    `duration_s` first, matching the shape shipped by `async-invocation-ack`.
    """

    run_id: str
    duration_s: float                       # wall clock, 1 decimal
    discovered: int                         # total raw items from all sources
    discovered_rss: int                     # rollup: non-Tavily sources
    discovered_tavily: int                  # rollup: Tavily sources
    discovered_by_source: dict[str, int]    # raw per-source counts (feed names)
    deduped: int                            # new-after-dedup, before max_items cap
    summarized: int                         # cards successfully built
    failed: int                             # items that raised during summarize
    persisted: int                          # cards handed to store.upsert()
    cards_written: int                      # persisted - store_failures (>= 0)
    input_tokens: int                       # Bedrock, summed over the run
    output_tokens: int
    tavily_searches: int                    # seed queries ATTEMPTED
    tavily_credits: int                     # searches x credits-per-depth
    discoverer_failures: int
    store_failures: int
    tavily_enabled: bool
    estimated_bedrock_cost_usd: float
    estimated_tavily_cost_usd: float
    estimated_cost_usd: float               # bedrock + tavily

    def to_dict(self) -> dict[str, Any]:
        """`dataclasses.asdict(self)` — the log-record / EMF payload. Keys are
        exactly the field names above, in this order."""
        return asdict(self)


def split_by_origin(discovered_by_source: Mapping[str, int]) -> tuple[int, int]:
    """Roll per-source counts up into `(rss, tavily)`.

    A source counts as Tavily iff its label starts with
    `config.TAVILY_SOURCE_PREFIX` ("Tavily: ") — the label
    `TavilyDiscoverer.discover()` builds. Everything else (RSS feed names such
    as "arXiv cs.AI") counts as RSS. Deliberately string-based: `summary.py`
    must not import `curation.tavily` (that module imports the `tavily` SDK).
    """
    rss = 0
    tavily = 0
    for source, count in discovered_by_source.items():
        if source.startswith(config.TAVILY_SOURCE_PREFIX):
            tavily += count
        else:
            rss += count
    return rss, tavily


def estimate_bedrock_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Design §7 Haiku pricing, from `spike_config.HAIKU_INPUT_USD_PER_1M` /
    `spike_config.HAIKU_OUTPUT_USD_PER_1M` — the SAME module as
    `HAIKU_MODEL_ID`, the model those prices price (see §4). Read at CALL time
    (module attribute, never `from ... import X`) so tests can monkeypatch the
    constants. Rounded to 6 decimals; `(0, 0) -> 0.0`."""
    cost = (
        input_tokens / 1_000_000 * spike_config.HAIKU_INPUT_USD_PER_1M
        + output_tokens / 1_000_000 * spike_config.HAIKU_OUTPUT_USD_PER_1M
    )
    return round(cost, 6)


def estimate_tavily_cost_usd(credits: int) -> float:
    """`credits * config.TAVILY_CREDIT_PRICE_USD` (curation-plane config,
    where the rest of the Tavily knobs already live), rounded to 6 decimals.
    `0 -> 0.0`."""
    return round(credits * config.TAVILY_CREDIT_PRICE_USD, 6)


def build_run_summary(
    *,
    run_id: str,
    duration_s: float,
    state: Mapping[str, Any],
    tavily_searches: int,
    tavily_credits: int,
    discoverer_failures: int,
    store_failures: int,
    tavily_enabled: bool,
) -> RunSummary:
    """Assemble a `RunSummary` from a final `CurationState` plus the
    stats only the composition root can see (discoverer/store accessors).

    `state` is read defensively with `.get(..., 0)` / `.get(..., {})` so a
    partial state (or a test's hand-built dict) never raises. Derives:
    `(discovered_rss, discovered_tavily)` via `split_by_origin`,
    `cards_written = max(persisted - store_failures, 0)`, and the three cost
    figures. `duration_s` is rounded to 1 decimal.
    """
    discovered = state.get("discovered", 0)
    discovered_by_source = dict(state.get("discovered_by_source", {}))
    discovered_rss, discovered_tavily = split_by_origin(discovered_by_source)

    persisted = state.get("persisted", 0)
    cards_written = max(persisted - store_failures, 0)

    input_tokens = state.get("input_tokens", 0)
    output_tokens = state.get("output_tokens", 0)

    estimated_bedrock_cost_usd = estimate_bedrock_cost_usd(input_tokens, output_tokens)
    estimated_tavily_cost_usd = estimate_tavily_cost_usd(tavily_credits)
    estimated_cost_usd = round(estimated_bedrock_cost_usd + estimated_tavily_cost_usd, 6)

    return RunSummary(
        run_id=run_id,
        duration_s=round(duration_s, 1),
        discovered=discovered,
        discovered_rss=discovered_rss,
        discovered_tavily=discovered_tavily,
        discovered_by_source=discovered_by_source,
        deduped=state.get("deduped", 0),
        summarized=state.get("summarized", 0),
        failed=state.get("failed", 0),
        persisted=persisted,
        cards_written=cards_written,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tavily_searches=tavily_searches,
        tavily_credits=tavily_credits,
        discoverer_failures=discoverer_failures,
        store_failures=store_failures,
        tavily_enabled=tavily_enabled,
        estimated_bedrock_cost_usd=estimated_bedrock_cost_usd,
        estimated_tavily_cost_usd=estimated_tavily_cost_usd,
        estimated_cost_usd=estimated_cost_usd,
    )

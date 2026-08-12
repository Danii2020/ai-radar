"""Graph state — the typed shape LangGraph merges partial node updates into."""
from __future__ import annotations

from typing import TypedDict

from spike.cards import Card
from spike.feeds import RawItem


class CurationState(TypedDict, total=False):
    # config knobs (set at invoke time; defaults from spike.config)
    max_items: int          # cap on items summarized this run (config.MAX_ITEMS)
    run_id: str              # NEW: correlation id, echoed into every node log

    # data flowing through the pipeline
    raw: list[RawItem]      # discover -> all discovered items
    fresh: list[RawItem]    # dedup    -> after dedup_filter, capped to max_items
    cards: list[Card]       # summarize-> built+ok cards; rank -> sorted descending

    # run-level counters (run summary; consumed by Spec 06)
    discovered: int         # len(raw)
    deduped: int            # len(fresh) before cap is applied
    summarized: int         # cards successfully built
    failed: int              # items that raised during summarize and were skipped
    discovered_by_source: dict[str, int]   # NEW: discover -> counts per RawItem.source
    persisted: int                         # NEW: persist  -> len(cards) handed to upsert
    input_tokens: int                      # NEW: summarize -> Bedrock input tokens
    output_tokens: int                     # NEW: summarize -> Bedrock output tokens

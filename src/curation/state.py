"""Graph state — the typed shape LangGraph merges partial node updates into."""
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
    deduped: int            # len(fresh) before cap is applied
    summarized: int         # cards successfully built
    failed: int              # items that raised during summarize and were skipped

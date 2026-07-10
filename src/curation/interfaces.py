"""Injected Protocols — the stable seam Specs 02-04 depend on.

Do not change these shapes without amending specs/curation-graph/contract.md.
"""
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

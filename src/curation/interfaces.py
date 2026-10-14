"""Injected Protocols — the stable seam Specs 02-04 depend on.

Do not change these shapes without amending specs/curation-graph/contract.md.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from shared.cards import Card
from shared.feeds import RawItem


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


@runtime_checkable
class EmbeddingWriter(Protocol):
    """Optional second capability of a store: attach vectors to persisted cards.

    Kept apart from `CardStore` so stores without vectors (the JSON backend)
    need not implement it; `build_graph` adds the embed step only when one is
    passed.
    """

    def set_embeddings(self, vectors: dict[str, list[float]]) -> int:
        """Attach each vector (keyed by card URL) to its already-persisted card.
        Returns how many vectors were actually written.

        Must not create items for unknown cards and must not raise for a
        single bad card.
        """
        ...

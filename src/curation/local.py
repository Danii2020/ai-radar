"""Local default implementations of the `Discoverer` / `CardStore` Protocols.

Reproduce Phase 0 (`src/spike/pipeline.py`) behavior exactly, just wrapped
behind the seam Specs 02-04 will swap out.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from spike import config
from spike.cards import Card
from spike.feeds import RawItem, discover


def _url_hash(url: str) -> str:
    """Same rule as `RawItem.url_hash` (Behavior Guarantee 8) — bridges the
    fact that `Card` does not carry its source item's `url_hash`."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


class RssDiscoverer:
    """Default Discoverer: wraps spike.feeds.discover over config.FEEDS."""

    def __init__(
        self,
        feeds: dict[str, str] | None = None,
        per_feed: int | None = None,
    ) -> None:
        self.feeds = feeds if feeds is not None else config.FEEDS
        self.per_feed = per_feed if per_feed is not None else config.PER_FEED

    def discover(self) -> list[RawItem]:
        return discover(self.feeds, per_feed=self.per_feed)


class JsonFileCardStore:
    """Default CardStore: the spike's .spike_cache/ JSON-file behavior.

    seen.json  -> set[str] of url_hash (idempotency)
    cards.json -> list[Card.to_dict()] (the rendered/ranked output)
    """

    def __init__(
        self,
        seen_path: Path | None = None,
        cards_path: Path | None = None,
        force: bool = False,
    ) -> None:
        self.seen_path = seen_path if seen_path is not None else config.SEEN_PATH
        self.cards_path = cards_path if cards_path is not None else config.CARDS_PATH
        self.force = force

    def _load_seen(self) -> set[str]:
        if self.seen_path.exists():
            return set(json.loads(self.seen_path.read_text()))
        return set()

    def dedup_filter(self, items: list[RawItem]) -> list[RawItem]:
        if self.force:
            return list(items)
        seen = self._load_seen()
        return [item for item in items if item.url_hash not in seen]

    def upsert(self, cards: list[Card]) -> None:
        self.seen_path.parent.mkdir(parents=True, exist_ok=True)
        self.cards_path.parent.mkdir(parents=True, exist_ok=True)

        if cards:
            seen = self._load_seen()
            seen.update(_url_hash(card.url) for card in cards)
            self.seen_path.write_text(json.dumps(sorted(seen), indent=2))

        self.cards_path.write_text(
            json.dumps([c.to_dict() for c in cards], indent=2)
        )

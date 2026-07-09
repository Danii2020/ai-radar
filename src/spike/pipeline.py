"""Orchestrates the Phase 0 loop: discover -> dedup -> summarize -> rank -> render."""
from __future__ import annotations

import json

from rich.console import Console

from . import config
from .bedrock import summarize
from .cards import Card, render
from .feeds import discover


def _load_seen() -> set[str]:
    if config.SEEN_PATH.exists():
        return set(json.loads(config.SEEN_PATH.read_text()))
    return set()


def _save(seen: set[str], cards: list[Card]) -> None:
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    config.SEEN_PATH.write_text(json.dumps(sorted(seen), indent=2))
    config.CARDS_PATH.write_text(
        json.dumps([c.to_dict() for c in cards], indent=2)
    )


def run(force: bool = False) -> list[Card]:
    console = Console()
    console.rule("[bold]AI Radar — Phase 0 spike")

    seen = set() if force else _load_seen()

    console.print(f"[dim]Discovering from {len(config.FEEDS)} feeds…[/dim]")
    items = discover(config.FEEDS, per_feed=config.PER_FEED)
    console.print(f"[dim]Found {len(items)} raw items.[/dim]")

    # Dedup against what we've already curated, then cap the batch.
    fresh = [it for it in items if it.url_hash not in seen]
    console.print(
        f"[dim]{len(fresh)} new after dedup; summarizing up to "
        f"{config.MAX_ITEMS} with Haiku 4.5.[/dim]\n"
    )
    batch = fresh[: config.MAX_ITEMS]

    cards: list[Card] = []
    for i, item in enumerate(batch, 1):
        console.print(f"[dim]  [{i}/{len(batch)}] {item.title[:70]}…[/dim]")
        try:
            out = summarize(item)
        except Exception as exc:  # spike: don't let one bad item kill the run
            console.print(f"  [red]! failed: {exc}[/red]")
            continue
        cards.append(Card.from_model(item, out))
        seen.add(item.url_hash)

    cards.sort(key=lambda c: c.relevance, reverse=True)

    console.print()
    console.rule(f"[bold]{len(cards)} cards (ranked by relevance)")
    console.print()
    render(cards, console)

    _save(seen, cards)
    console.print(
        f"[dim]Saved {len(cards)} cards → {config.CARDS_PATH} · "
        f"seen db → {config.SEEN_PATH}[/dim]"
    )
    return cards

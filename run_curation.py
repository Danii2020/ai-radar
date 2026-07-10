#!/usr/bin/env python3
"""Entrypoint for the curation-graph LangGraph refactor of the Phase 0 spike.

Usage:
    python run_curation.py            # skips items already seen
    python run_curation.py --force    # re-summarize everything (ignore dedup cache)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from rich.console import Console  # noqa: E402

from curation.graph import build_graph  # noqa: E402
from curation.local import JsonFileCardStore, RssDiscoverer  # noqa: E402
from spike import config  # noqa: E402
from spike.cards import render  # noqa: E402

if __name__ == "__main__":
    console = Console()
    console.rule("[bold]AI Radar — curation-graph")

    force = "--force" in sys.argv
    store = JsonFileCardStore(force=force)
    discoverer = RssDiscoverer()
    graph = build_graph(store, discoverer)

    final = graph.invoke({"max_items": config.MAX_ITEMS})

    cards = final.get("cards", [])
    console.print()
    console.rule(f"[bold]{len(cards)} cards (ranked by relevance)")
    console.print()
    render(cards, console)

    console.print(
        f"[dim]discovered={final.get('discovered', 0)} "
        f"deduped={final.get('deduped', 0)} "
        f"summarized={final.get('summarized', 0)} "
        f"failed={final.get('failed', 0)}[/dim]"
    )
    console.print(
        f"[dim]Saved {len(cards)} cards → {config.CARDS_PATH} · "
        f"seen db → {config.SEEN_PATH}[/dim]"
    )

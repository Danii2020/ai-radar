#!/usr/bin/env python3
"""Entrypoint for the curation graph (Spec 01: curation-graph).

Discovery source is auto-selected: RSS + Tavily web search
(`CompositeDiscoverer`, Spec 02: tavily-discovery) if `TAVILY_API_KEY` is
configured, otherwise RSS alone. This is the ONLY place that hits the real
Tavily API (pytest never does).

Usage:
    python run_curation.py            # skips items already seen
    python run_curation.py --force    # re-summarize everything (ignore dedup cache)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from rich.console import Console  # noqa: E402

from curation import config as curation_config  # noqa: E402
from curation.composite import CompositeDiscoverer  # noqa: E402
from curation.graph import build_graph  # noqa: E402
from curation.interfaces import Discoverer  # noqa: E402
from curation.local import JsonFileCardStore, RssDiscoverer  # noqa: E402
from curation.tavily import TavilyDiscoverer  # noqa: E402
from spike import config  # noqa: E402
from spike.cards import render  # noqa: E402


def _build_discoverer() -> CompositeDiscoverer:
    sources: list[Discoverer] = [RssDiscoverer()]
    if curation_config.TAVILY_API_KEY:
        sources.append(TavilyDiscoverer.from_config())
    else:
        print("! TAVILY_API_KEY not set — discovering from RSS only")
    return CompositeDiscoverer(sources)


if __name__ == "__main__":
    console = Console()
    console.rule("[bold]AI Radar — curation")

    force = "--force" in sys.argv
    store = JsonFileCardStore(force=force)
    discoverer = _build_discoverer()
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
        f"failed={final.get('failed', 0)} "
        f"discoverer_failures={discoverer.failures()}[/dim]"
    )
    console.print(
        f"[dim]Saved {len(cards)} cards → {config.CARDS_PATH} · "
        f"seen db → {config.SEEN_PATH}[/dim]"
    )

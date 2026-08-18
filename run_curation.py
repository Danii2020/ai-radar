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
import logging
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from rich.console import Console  # noqa: E402

from curation import config as curation_config  # noqa: E402
from curation.composite import CompositeDiscoverer  # noqa: E402
from curation.dynamo import DynamoCardStore  # noqa: E402
from curation.graph import build_graph  # noqa: E402
from curation.interfaces import CardStore, Discoverer  # noqa: E402
from curation.local import JsonFileCardStore, RssDiscoverer  # noqa: E402
from curation.summary import build_run_summary  # noqa: E402
from curation.tavily import TavilyDiscoverer  # noqa: E402
from shared import config  # noqa: E402
from shared.cards import render  # noqa: E402


def _build_store(force: bool) -> CardStore:
    if curation_config.CARD_STORE_BACKEND == "dynamo":
        return DynamoCardStore()
    return JsonFileCardStore(force=force)


def _build_discoverer() -> CompositeDiscoverer:
    sources: list[Discoverer] = [RssDiscoverer()]
    if curation_config.TAVILY_API_KEY:
        sources.append(TavilyDiscoverer.from_config())
    else:
        print("! TAVILY_API_KEY not set — discovering from RSS only")
    return CompositeDiscoverer(sources)


if __name__ == "__main__":
    # So the three node records (discover_complete/summarize_complete/
    # persist_complete) print locally, matching the JSON-line shape
    # runtime_app.py's CloudWatch records use.
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    console = Console()
    console.rule("[bold]AI Radar — curation")

    force = "--force" in sys.argv
    store = _build_store(force)
    discoverer = _build_discoverer()
    graph = build_graph(store, discoverer)

    run_id = uuid.uuid4().hex
    started = time.monotonic()
    final = graph.invoke({"max_items": config.MAX_ITEMS, "run_id": run_id})
    duration_s = time.monotonic() - started

    cards = final.get("cards", [])
    console.print()
    console.rule(f"[bold]{len(cards)} cards (ranked by relevance)")
    console.print()
    render(cards, console)

    store_failures = store.failures() if hasattr(store, "failures") else 0
    summary = build_run_summary(
        run_id=run_id,
        duration_s=duration_s,
        state=final,
        tavily_searches=discoverer.searches(),
        tavily_credits=discoverer.credits_used(),
        discoverer_failures=discoverer.failures(),
        store_failures=store_failures,
        tavily_enabled=bool(curation_config.TAVILY_API_KEY),
    )
    # emit_run_metrics is NOT called here — there is no CloudWatch to parse
    # the EMF line locally; the printed summary below is local/cloud parity
    # (contract.md §9 / Behavior Guarantee 11).
    console.print(
        f"[dim]discovered={summary.discovered} "
        f"(rss={summary.discovered_rss} tavily={summary.discovered_tavily}) "
        f"deduped={summary.deduped} "
        f"summarized={summary.summarized} "
        f"failed={summary.failed} "
        f"cards_written={summary.cards_written} "
        f"discoverer_failures={summary.discoverer_failures} "
        f"store_failures={summary.store_failures}[/dim]"
    )
    console.print(
        f"[dim]tokens in/out={summary.input_tokens}/{summary.output_tokens} "
        f"tavily searches/credits={summary.tavily_searches}/{summary.tavily_credits} "
        f"est. ${summary.estimated_cost_usd:.6f} "
        f"(bedrock=${summary.estimated_bedrock_cost_usd:.6f} "
        f"tavily=${summary.estimated_tavily_cost_usd:.6f})[/dim]"
    )
    if curation_config.CARD_STORE_BACKEND == "dynamo":
        console.print(
            f"[dim]Saved {len(cards)} cards → DynamoDB table "
            f"{curation_config.CARD_TABLE_NAME}[/dim]"
        )
    else:
        console.print(
            f"[dim]Saved {len(cards)} cards → {config.CARDS_PATH} · "
            f"seen db → {config.SEEN_PATH}[/dim]"
        )

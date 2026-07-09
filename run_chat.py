#!/usr/bin/env python3
"""Interactive RAG chat over the cards curated by the spike (Plane B).

Usage:
    uv run run_chat.py        # uses .spike_cache/cards.json (run the spike first)

Type a question; 'exit' or Ctrl-D to quit.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from rich.console import Console  # noqa: E402
from rich.markdown import Markdown  # noqa: E402

from spike.chat import RagChat  # noqa: E402
from spike.config import CARDS_PATH  # noqa: E402


def main() -> None:
    console = Console()
    if not CARDS_PATH.exists():
        console.print(
            f"[red]No cards found at {CARDS_PATH}.[/red] "
            "Run [bold]uv run run_spike.py[/bold] first."
        )
        sys.exit(1)

    cards = json.loads(CARDS_PATH.read_text())
    console.rule("[bold]AI Radar — mini RAG chat")
    console.print(f"[dim]Grounded in {len(cards)} curated cards. Embedding…[/dim]")
    chat = RagChat(cards)
    console.print("[dim]Ready. Ask about the collected AI news. ('exit' to quit)[/dim]\n")

    while True:
        try:
            question = console.input("[bold cyan]you ›[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            console.print("[dim]bye[/dim]")
            break

        answer, hits = chat.ask(question)
        console.print()
        console.print(Markdown(answer))
        console.print("\n[dim]sources:[/dim]")
        for i, (card, score) in enumerate(hits, 1):
            console.print(
                f"  [dim][{i}] {card['title'][:70]} "
                f"({score:.2f}) — {card['url']}[/dim]"
            )
        console.print()


if __name__ == "__main__":
    main()

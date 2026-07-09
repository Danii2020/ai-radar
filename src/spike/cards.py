"""Card model + console rendering."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


@dataclass
class Card:
    title: str
    url: str
    source: str
    summary: str
    tags: list[str]
    type: str
    relevance: int
    published: str
    takeaways: list[str] = field(default_factory=list)

    @classmethod
    def from_model(cls, raw_item, model_out: dict) -> "Card":
        return cls(
            title=model_out.get("title") or raw_item.title,
            url=raw_item.url,
            source=raw_item.source,
            summary=model_out.get("summary", ""),
            tags=model_out.get("tags", []),
            type=model_out.get("type", "news"),
            relevance=int(model_out.get("relevance", 0)),
            published=raw_item.published,
            takeaways=model_out.get("takeaways", []),
        )

    def to_dict(self) -> dict:
        return asdict(self)


_TYPE_COLOR = {
    "paper": "magenta",
    "release": "green",
    "project": "cyan",
    "news": "yellow",
    "concept": "blue",
}


def render(cards: list[Card], console: Console | None = None) -> None:
    console = console or Console()
    for card in cards:
        color = _TYPE_COLOR.get(card.type, "white")
        body = Text()
        body.append(card.summary + "\n")
        if card.takeaways:
            body.append("\n")
            for t in card.takeaways:
                body.append(f"  • {t}\n", style="dim")
        body.append("\n")
        body.append(f"🔗 {card.url}\n", style="link " + color)
        body.append(
            f"#{' #'.join(card.tags)}" if card.tags else "", style="dim cyan"
        )

        meta = (
            f"[{color}]{card.type.upper()}[/{color}] · "
            f"relevance {card.relevance}/10 · {card.source} · "
            f"{card.published or 'date n/a'}"
        )
        console.print(
            Panel(
                body,
                title=f"[bold]{card.title}[/bold]",
                subtitle=meta,
                border_style=color,
                padding=(1, 2),
            )
        )
        console.print()

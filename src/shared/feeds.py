"""Discovery layer — fetch + normalize items from RSS/Atom feeds (no API key)."""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(raw: str, limit: int = 1500) -> str:
    """Strip HTML tags / entities and clamp length to control input tokens."""
    text = html.unescape(_TAG_RE.sub(" ", raw or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _published(entry) -> str:
    parsed = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if not parsed:
        return ""
    return datetime(*parsed[:6], tzinfo=timezone.utc).date().isoformat()


@dataclass
class RawItem:
    source: str
    title: str
    url: str
    published: str  # ISO date or ""
    snippet: str

    @property
    def url_hash(self) -> str:
        return hashlib.sha256(self.url.encode()).hexdigest()[:16]


def discover(feeds: dict[str, str], per_feed: int) -> list[RawItem]:
    """Pull the most recent `per_feed` entries from each feed."""
    items: list[RawItem] = []
    for source, url in feeds.items():
        parsed = feedparser.parse(url)
        if parsed.bozo and not parsed.entries:
            print(f"  ! skipped {source}: {parsed.bozo_exception}")
            continue
        for entry in parsed.entries[:per_feed]:
            link = getattr(entry, "link", "")
            title = _clean(getattr(entry, "title", ""), limit=300)
            if not link or not title:
                continue
            snippet = _clean(
                getattr(entry, "summary", "")
                or getattr(entry, "description", "")
            )
            items.append(
                RawItem(
                    source=source,
                    title=title,
                    url=link,
                    published=_published(entry),
                    snippet=snippet,
                )
            )
    return items

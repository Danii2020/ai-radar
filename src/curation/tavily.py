"""Tavily web-search Discoverer — the only module that imports the `tavily` SDK.

Topic-seeded search with content extraction, returning `RawItem`s shaped
exactly like `spike.feeds.discover`'s output. Infra-edge adapter: portable
curation logic (nodes/graph/state/composite) never imports `tavily` directly.
"""
from __future__ import annotations

from typing import Literal, cast

from tavily import TavilyClient

from spike.feeds import RawItem, _clean

from . import config

_SearchDepth = Literal["basic", "advanced", "fast", "ultra-fast"]
_Topic = Literal["general", "news", "finance"]


class TavilyDiscoverer:
    """Discoverer over Tavily web search (topic-seeded, content-extracting).

    Implements the Spec 01 `Discoverer` Protocol. Never raises past discover():
    a failing seed is logged + counted and skipped; a total outage returns [].
    """

    def __init__(
        self,
        seeds: list[str],
        api_key: str,
        *,
        max_results: int,
        results_per_query: int = 5,
        days: int = 7,
        search_depth: str = "basic",
        topic: str = "general",
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> None:
        self.seeds = seeds
        self.api_key = api_key
        self.max_results = max_results
        self.results_per_query = results_per_query
        self.days = days
        self.search_depth = search_depth
        self.topic = topic
        self.include_domains = include_domains if include_domains is not None else []
        self.exclude_domains = exclude_domains if exclude_domains is not None else []
        self._client = None
        self._failures = 0

    @classmethod
    def from_config(cls) -> "TavilyDiscoverer":
        """Build from `curation.config` knobs. Raises ValueError if TAVILY_API_KEY
        is unset (fail fast at construction — the smoke entrypoint surfaces this)."""
        if not config.TAVILY_API_KEY:
            raise ValueError(
                "TAVILY_API_KEY is not set — add it to .env or the environment."
            )
        return cls(
            seeds=config.TAVILY_SEEDS,
            api_key=config.TAVILY_API_KEY,
            max_results=config.TAVILY_MAX_RESULTS,
            results_per_query=config.TAVILY_RESULTS_PER_QUERY,
            days=config.TAVILY_DAYS,
            search_depth=config.TAVILY_SEARCH_DEPTH,
            topic=config.TAVILY_TOPIC,
            include_domains=config.TAVILY_INCLUDE_DOMAINS,
            exclude_domains=config.TAVILY_EXCLUDE_DOMAINS,
        )

    def _get_client(self):
        if self._client is None:
            self._client = TavilyClient(api_key=self.api_key)
        return self._client

    def discover(self) -> list[RawItem]:
        """Search each seed, map results -> RawItem, dedup by url_hash within this
        source, and return at most `max_results` items. Per-seed try/except:
        a failing query is logged + skipped, others still run. Total failure
        (or unset key handled upstream) yields [] — never raises."""
        self._failures = 0
        client = self._get_client()
        source = f"Tavily: {self.topic}"

        items: list[RawItem] = []
        seen_hashes: set[str] = set()

        for seed in self.seeds:
            try:
                response = client.search(
                    query=seed,
                    # search_depth/topic are env-driven config (plain str); the
                    # SDK types them as Literal — cast at this trust boundary
                    # rather than narrowing the public str-typed constructor.
                    search_depth=cast(_SearchDepth, self.search_depth),
                    topic=cast(_Topic, self.topic),
                    days=self.days,
                    max_results=self.results_per_query,
                    include_domains=self.include_domains,
                    exclude_domains=self.exclude_domains,
                    include_raw_content=False,
                )
            except Exception as exc:  # per-seed failure: log, count, continue
                print(f"! tavily seed failed: {exc}")
                self._failures += 1
                continue

            for result in response.get("results", []):
                url = result.get("url", "")
                title_raw = result.get("title", "")
                if not url or not title_raw:
                    continue
                title = _clean(title_raw, limit=300)
                if not title:
                    continue
                item = RawItem(
                    source=source,
                    title=title,
                    url=url,
                    published=result.get("published_date", ""),
                    snippet=_clean(result.get("content", "")),
                )
                if item.url_hash in seen_hashes:
                    continue
                seen_hashes.add(item.url_hash)
                items.append(item)

        return items[: self.max_results]

    def failures(self) -> int:
        """Count of seed queries that raised during the last discover() (0 if
        clean). Lets a caller/observer surface degraded runs (Spec 06)."""
        return self._failures

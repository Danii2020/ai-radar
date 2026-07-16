"""Composite Discoverer — merges several sources, deduping cross-source.

Source-agnostic: knows nothing about Tavily or RSS specifically, only the
`Discoverer` Protocol. No `tavily`/`boto3` import here (portability).
"""
from __future__ import annotations

from spike.feeds import RawItem

from .interfaces import Discoverer


class CompositeDiscoverer:
    """Run several Discoverers, merge their RawItems, drop cross-source
    URL-hash duplicates (first source wins). One source failing does not sink
    the run — its exception is caught, logged, counted, and the others proceed."""

    def __init__(self, sources: list[Discoverer]) -> None:
        self.sources = sources
        self._failures = 0

    def discover(self) -> list[RawItem]:
        """For each source: try source.discover(); on exception log
        `! discoverer failed: ...`, increment failure counter, continue with []
        for that source. Concatenate results in source order, then dedup by
        url_hash preserving first occurrence. Returns the merged, deduped list."""
        self._failures = 0
        merged: list[RawItem] = []

        for source in self.sources:
            try:
                items = source.discover()
            except Exception as exc:  # per-source failure: log, count, continue
                print(f"! discoverer failed: {exc}")
                self._failures += 1
                items = []
            merged.extend(items)

        seen_hashes: set[str] = set()
        deduped: list[RawItem] = []
        for item in merged:
            if item.url_hash in seen_hashes:
                continue
            seen_hashes.add(item.url_hash)
            deduped.append(item)

        return deduped

    def failures(self) -> int:
        """Number of sources whose discover() raised during the last run."""
        return self._failures

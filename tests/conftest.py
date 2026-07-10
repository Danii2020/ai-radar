"""Shared pytest setup + fixtures for the curation-graph spec tests.

Spec: specs/curation-graph/{contract.md,intent.md,audit.md}

- Adds `src/` to `sys.path` (mirrors the pattern in `run_spike.py`) so both
  `spike.*` (existing) and `curation.*` (not yet implemented — this is the
  RED phase) are importable from `tests/`.
- Provides small factories for `RawItem` / summarize()-shaped dicts, and a
  deterministic, network-free `summarize()` stub factory, reused by
  `tests/test_local_store.py` and `tests/test_graph.py`.

No test in this suite makes a live Bedrock/AWS/network call: `spike.bedrock.summarize`
is always monkeypatched at the point tests import it (`curation.nodes.summarize`),
never invoked for real.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from spike.feeds import RawItem


@pytest.fixture
def make_raw_item():
    """Factory for a `RawItem` with sane defaults; override any field via kwargs."""

    def _make(
        source: str = "Test Feed",
        title: str = "Test Title",
        url: str = "https://example.com/article",
        published: str = "2026-07-01",
        snippet: str = "A snippet.",
    ) -> RawItem:
        return RawItem(
            source=source, title=title, url=url, published=published, snippet=snippet
        )

    return _make


@pytest.fixture
def make_model_out():
    """Factory for a fake `summarize()` return dict (the `Card.from_model` input)."""

    def _make(
        title: str = "Model Title",
        summary: str = "A concise summary.",
        tags: list[str] | None = None,
        type_: str = "news",
        relevance: int = 5,
        takeaways: list[str] | None = None,
    ) -> dict:
        return {
            "title": title,
            "summary": summary,
            "tags": tags if tags is not None else ["llm"],
            "type": type_,
            "relevance": relevance,
            "takeaways": takeaways if takeaways is not None else [],
        }

    return _make


@pytest.fixture
def summarize_stub_factory(make_model_out):
    """Factory to build deterministic, network-free `summarize(item)` stubs.

    `relevance_by_url` controls the relevance score returned per item (default 5).
    `raise_for_urls` makes the stub raise for those URLs, simulating a per-item
    Bedrock/summarize failure (contract Error Handling Contract row 1).
    """

    def _build(
        relevance_by_url: dict[str, int] | None = None,
        raise_for_urls: set[str] | None = None,
    ):
        relevance_by_url = relevance_by_url or {}
        raise_for_urls = raise_for_urls or set()

        def _summarize(item: RawItem) -> dict:
            if item.url in raise_for_urls:
                raise RuntimeError(f"stub summarize failure for {item.url}")
            return make_model_out(
                title=item.title,
                summary=f"Summary of {item.title}",
                relevance=relevance_by_url.get(item.url, 5),
            )

        return _summarize

    return _build

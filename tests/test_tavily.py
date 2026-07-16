"""Tests for `src/curation/tavily.py` — `TavilyDiscoverer`.

Spec: specs/tavily-discovery/contract.md ("TavilyDiscoverer", Behavior
Guarantees 1-3 & 10, Error Handling Contract rows 1-2 & 5-6);
specs/tavily-discovery/tasks.md Phase 4.1-4.2 (T1, T2, T3, T4, T5, T6).

Every test stubs `tavily.TavilyClient` via monkeypatch on `curation.tavily`'s
module namespace (`install_fake_tavily_client`) — zero live Tavily calls in
this suite (carried testing convention from specs/curation-graph).

RED phase: `src/curation/tavily.py` and `src/curation/config.py` do not exist
yet. Every test in this file is expected to fail at collection with
`ModuleNotFoundError: No module named 'curation.tavily'` (or `'curation.config'`)
until the implementation lands.
"""
from __future__ import annotations

import pytest

import curation.config as config_module
import curation.tavily as tavily_module
from curation.tavily import TavilyDiscoverer


class FakeTavilyClient:
    """Stub for `tavily.TavilyClient` — installed via monkeypatch, never hits
    the network.

    `responses` maps a seed query string -> either a Tavily-shaped response
    dict (`{"results": [...]}`) or an `Exception` instance to raise for that
    query (simulates SDK errors like `UsageLimitExceededError`).
    """

    def __init__(self, responses: dict, captured_calls: list) -> None:
        self._responses = responses
        self._captured_calls = captured_calls

    def search(self, **kwargs):
        self._captured_calls.append(kwargs)
        query = kwargs.get("query")
        result = self._responses.get(query, {"results": []})
        if isinstance(result, Exception):
            raise result
        return result


def install_fake_tavily_client(monkeypatch, responses: dict) -> list:
    """Replace `curation.tavily.TavilyClient` with a factory returning a
    `FakeTavilyClient` seeded with `responses`. Returns the list of captured
    `.search(**kwargs)` call shapes (in call order) for assertions."""
    captured_calls: list = []
    fake_client = FakeTavilyClient(responses, captured_calls)
    monkeypatch.setattr(tavily_module, "TavilyClient", lambda **kwargs: fake_client)
    return captured_calls


# T1 (Guarantee 1, Error Handling row "missing published_date"): a Tavily
# result dict maps to a RawItem — snippet from `content`, title/snippet HTML
# is cleaned (spike.feeds._clean), and `published` degrades to "" when
# `published_date` is absent (default topic="general").
def test_discover_maps_tavily_result_fields_to_raw_item(monkeypatch):
    responses = {
        "seed one": {
            "results": [
                {
                    "title": "<b>New LLM</b> release",
                    "url": "https://example.com/llm",
                    "content": "<p>Some <i>content</i> about the release.</p>",
                    "score": 0.87,
                }
            ]
        }
    }
    install_fake_tavily_client(monkeypatch, responses)
    discoverer = TavilyDiscoverer(seeds=["seed one"], api_key="fake-key", max_results=20)

    items = discoverer.discover()

    assert len(items) == 1
    item = items[0]
    assert item.title == "New LLM release"  # HTML tags stripped
    assert item.url == "https://example.com/llm"
    assert item.snippet == "Some content about the release."  # HTML tags stripped
    assert item.published == ""  # no published_date for topic="general"
    assert item.source == "Tavily: general"  # default topic, stable per-instance source


# T1 (Error Handling Contract row "Tavily result missing url or title"): a
# result lacking a usable `url` or `title` is skipped; others are kept.
def test_discover_skips_results_missing_url_or_title(monkeypatch):
    responses = {
        "seed one": {
            "results": [
                {"title": "Good Title", "url": "https://example.com/a", "content": "ok"},
                {"title": "", "url": "https://example.com/b", "content": "empty title"},
                {"title": "No URL Item", "url": "", "content": "empty url"},
                {"url": "https://example.com/c", "content": "title key entirely missing"},
            ]
        }
    }
    install_fake_tavily_client(monkeypatch, responses)
    discoverer = TavilyDiscoverer(seeds=["seed one"], api_key="fake-key", max_results=20)

    items = discoverer.discover()

    assert [item.url for item in items] == ["https://example.com/a"]


# T2 (Guarantee 1): the per-run `max_results` cap is enforced even when
# multiple seeds together would exceed it; the cap keeps discovery order.
def test_discover_enforces_max_results_cap(monkeypatch):
    def result(i: int) -> dict:
        return {
            "title": f"Item {i}",
            "url": f"https://example.com/{i}",
            "content": f"content {i}",
        }

    responses = {
        "seed one": {"results": [result(i) for i in range(5)]},
        "seed two": {"results": [result(i) for i in range(5, 10)]},
    }
    install_fake_tavily_client(monkeypatch, responses)
    discoverer = TavilyDiscoverer(
        seeds=["seed one", "seed two"], api_key="fake-key", max_results=7
    )

    items = discoverer.discover()

    assert len(items) == 7
    assert [item.url for item in items] == [
        f"https://example.com/{i}" for i in range(7)
    ]


# T3 (Guarantee 2, Error Handling row "one Tavily seed query raises"): a
# raising seed is caught, logged, and counted; the remaining seed still runs
# and its results are returned; discover() itself never raises.
def test_discover_one_seed_failure_is_counted_and_other_seeds_still_run(monkeypatch):
    responses = {
        "bad seed": RuntimeError("usage limit exceeded"),
        "good seed": {
            "results": [
                {"title": "Good", "url": "https://example.com/good", "content": "ok"}
            ]
        },
    }
    install_fake_tavily_client(monkeypatch, responses)
    discoverer = TavilyDiscoverer(
        seeds=["bad seed", "good seed"], api_key="fake-key", max_results=20
    )

    items = discoverer.discover()  # must not raise

    assert [item.url for item in items] == ["https://example.com/good"]
    assert discoverer.failures() == 1


# T4 (Guarantee 3, Error Handling row "all Tavily seeds raise / total outage"):
# every seed raising yields [] (not a raise), and failures() reflects the misses.
def test_discover_total_outage_returns_empty_list_without_raising(monkeypatch):
    responses = {
        "seed one": RuntimeError("timeout"),
        "seed two": RuntimeError("timeout"),
    }
    install_fake_tavily_client(monkeypatch, responses)
    discoverer = TavilyDiscoverer(
        seeds=["seed one", "seed two"], api_key="fake-key", max_results=20
    )

    items = discoverer.discover()

    assert items == []
    assert discoverer.failures() == 2


# T5 (Error Handling row "TAVILY_API_KEY unset at from_config()"): building via
# from_config() with no key configured fails fast with ValueError, before any
# Tavily call is attempted (no client stub needed/installed here).
def test_from_config_raises_value_error_when_api_key_unset(monkeypatch):
    monkeypatch.setattr(config_module, "TAVILY_API_KEY", "")

    with pytest.raises(ValueError):
        TavilyDiscoverer.from_config()


# T6 (contract "Behavior of discover()" step 4): duplicate URLs across seeds
# collapse to a single RawItem, keeping the first occurrence (by discovery
# order across seeds), matching the exact url_hash rule.
def test_discover_dedups_within_source_by_url_hash_first_occurrence_wins(monkeypatch):
    responses = {
        "seed one": {
            "results": [
                {
                    "title": "First mention",
                    "url": "https://example.com/dup",
                    "content": "first",
                },
            ]
        },
        "seed two": {
            "results": [
                {
                    "title": "Second mention",
                    "url": "https://example.com/dup",
                    "content": "second",
                },
                {
                    "title": "Unique",
                    "url": "https://example.com/unique",
                    "content": "unique",
                },
            ]
        },
    }
    install_fake_tavily_client(monkeypatch, responses)
    discoverer = TavilyDiscoverer(
        seeds=["seed one", "seed two"], api_key="fake-key", max_results=20
    )

    items = discoverer.discover()

    assert [item.url for item in items] == [
        "https://example.com/dup",
        "https://example.com/unique",
    ]
    assert items[0].title == "First mention"  # first occurrence wins, not overwritten

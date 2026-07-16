"""Tests for `src/curation/composite.py` — `CompositeDiscoverer`, plus the
seam and portability guarantees this spec adds on top of Spec 01's graph.

Spec: specs/tavily-discovery/contract.md ("CompositeDiscoverer", Behavior
Guarantees 4-8); specs/tavily-discovery/tasks.md Phase 4.3-4.5 (T7, T8, T9, T10).

`FakeDiscoverer` is an in-memory `Discoverer` double (mirrors
tests/test_graph.py's convention) — no network, no real RSS/Tavily source is
exercised here.

RED phase: `src/curation/composite.py` does not exist yet. Every test in this
file is expected to fail at collection with `ModuleNotFoundError: No module
named 'curation.composite'` until the implementation lands.
"""
from __future__ import annotations

import ast
from pathlib import Path

import curation.nodes as nodes_module
from curation.composite import CompositeDiscoverer
from curation.graph import build_graph


class FakeDiscoverer:
    """In-memory Discoverer: returns a fixed list of RawItems (or raises)."""

    def __init__(self, items):
        self._items = list(items)

    def discover(self):
        return list(self._items)


class RaisingDiscoverer:
    """In-memory Discoverer double that always raises, simulating a source
    outage (e.g. a Tavily quota error surfacing through the composite)."""

    def discover(self):
        raise RuntimeError("source outage")


class FakeCardStore:
    """In-memory CardStore: no-op dedup + captured upsert calls (mirrors
    tests/test_graph.py's FakeCardStore)."""

    def __init__(self):
        self.upsert_calls = 0
        self.upserted_cards = None

    def dedup_filter(self, items):
        return list(items)

    def upsert(self, cards):
        self.upsert_calls += 1
        self.upserted_cards = list(cards)


# T7 (Guarantee 4 & 6): sources are merged in order, cross-source url_hash
# duplicates collapse to a single item, and the FIRST source's variant wins
# (e.g. the same article from RSS + Tavily is kept as the RSS copy).
def test_discover_merges_sources_dedups_url_hash_first_source_wins_preserving_order(
    make_raw_item,
):
    shared_url = "https://example.com/shared"
    rss_only = make_raw_item(url="https://example.com/rss-only", source="RSS", title="RSS Only")
    rss_shared = make_raw_item(url=shared_url, source="RSS", title="RSS Version")
    tavily_shared = make_raw_item(url=shared_url, source="Tavily: general", title="Tavily Version")
    tavily_only = make_raw_item(
        url="https://example.com/tavily-only", source="Tavily: general", title="Tavily Only"
    )

    rss_source = FakeDiscoverer([rss_only, rss_shared])
    tavily_source = FakeDiscoverer([tavily_shared, tavily_only])

    composite = CompositeDiscoverer([rss_source, tavily_source])
    items = composite.discover()

    assert [item.url for item in items] == [rss_only.url, shared_url, tavily_only.url]
    shared_result = next(item for item in items if item.url == shared_url)
    assert shared_result.title == "RSS Version"  # first source (RSS) wins the tie


# T8 (Guarantee 5, Error Handling row "TavilyDiscoverer used in a
# CompositeDiscoverer and its discover() somehow raises"): one source raising
# degrades the run to the other source's output; the failure is counted;
# discover() never raises.
def test_discover_one_source_failure_degrades_to_other_source_counted_no_raise(
    make_raw_item,
):
    good_item = make_raw_item(url="https://example.com/good", title="Good")
    good_source = FakeDiscoverer([good_item])

    composite = CompositeDiscoverer([RaisingDiscoverer(), good_source])

    items = composite.discover()  # must not raise

    assert [item.url for item in items] == [good_item.url]
    assert composite.failures() == 1


# T9 (Guarantee 7 — the seam): the UNCHANGED Spec 01 build_graph compiles and
# invokes end-to-end when handed a CompositeDiscoverer, with no edits to
# graph.py/nodes.py/state.py/interfaces.py. Cards are produced from both
# underlying sources.
def test_seam_build_graph_with_composite_discoverer_invokes_end_to_end(
    monkeypatch, make_raw_item, summarize_stub_factory
):
    rss_item = make_raw_item(url="https://example.com/rss", title="RSS Item", source="RSS")
    tavily_item = make_raw_item(
        url="https://example.com/tavily", title="Tavily Item", source="Tavily: general"
    )
    monkeypatch.setattr(nodes_module, "summarize", summarize_stub_factory())

    composite = CompositeDiscoverer(
        [FakeDiscoverer([rss_item]), FakeDiscoverer([tavily_item])]
    )
    store = FakeCardStore()
    compiled = build_graph(store, composite)

    result = compiled.invoke({"max_items": 10})

    assert {card.url for card in result["cards"]} == {rss_item.url, tavily_item.url}
    assert store.upsert_calls == 1


# T10 (Guarantee 8 — portability): the `tavily` SDK is imported ONLY in
# tavily.py; it does not leak into composite.py/nodes.py/graph.py/state.py/
# interfaces.py. No `boto3` appears anywhere in this spec's modules.
def test_tavily_sdk_imported_only_in_tavily_module_no_boto3_anywhere():
    curation_src = Path(__file__).parent.parent / "src" / "curation"
    files_that_must_not_import_tavily = [
        "composite.py",
        "config.py",
        "nodes.py",
        "graph.py",
        "state.py",
        "interfaces.py",
    ]

    def imported_roots(path: Path) -> set[str]:
        tree = ast.parse(path.read_text(), filename=str(path))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        return roots

    for filename in files_that_must_not_import_tavily:
        path = curation_src / filename
        assert path.exists(), f"expected {path} to exist"
        roots = imported_roots(path)
        assert "tavily" not in roots, f"{filename} must not import the tavily SDK"
        assert "boto3" not in roots, f"{filename} must not import boto3"

    tavily_path = curation_src / "tavily.py"
    assert tavily_path.exists(), f"expected {tavily_path} to exist"
    tavily_roots = imported_roots(tavily_path)
    assert "boto3" not in tavily_roots, "tavily.py must not import boto3"
    # Guards against a vacuous pass above: tavily.py must actually be the one
    # place that imports the SDK.
    assert "tavily" in tavily_roots, "tavily.py is expected to import the tavily SDK"

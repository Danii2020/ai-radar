"""Tests for `src/curation/graph.py` + `src/curation/nodes.py`.

Spec: specs/curation-graph/contract.md Behavior Guarantees 1-7, Error Handling
Contract row 1; specs/curation-graph/audit.md T1-T6, T11. Extended by
specs/run-observability/contract.md §6 (`discover_node`/`summarize_node`/
`persist_node` additions) and audit.md T14-T18, T28 — the new tests below are
appended at the end of this file; the edits above them (patch target
`nodes.summarize` -> `nodes.summarize_with_usage`) are the "known test churn"
specs/run-observability/tasks.md Task 4.6 calls out explicitly.

Fakes (`FakeDiscoverer`, `FakeCardStore`) exercise the `Discoverer`/`CardStore`
Protocol seam per contract.md `interfaces.py` — graph/node logic is tested
through the injected seam, not the local JSON-file implementation, except for
T2 and T5 which are explicitly specced against the `JsonFileCardStore` +
`RssDiscoverer` defaults (Guarantees 2 and 5).

RED phase: `src/curation/` does not exist yet. Every test in this file is
expected to fail at collection with `ModuleNotFoundError: No module named
'curation'` until the implementation lands. The run-observability additions
are expected to fail differently, once curation-graph exists but Spec 06 does
not: `AttributeError` (monkeypatching `nodes.summarize_with_usage`, which
`nodes.py` does not yet define) or plain assertion failures (missing state
keys like `discovered_by_source`/`persisted`/`input_tokens`).
"""
from __future__ import annotations

import json
import logging

from langgraph.graph import END, START

from shared.cards import Card

import curation.nodes as nodes_module
from curation.graph import build_graph


class FakeDiscoverer:
    """In-memory Discoverer: returns a fixed list of RawItems."""

    def __init__(self, items):
        self._items = list(items)

    def discover(self):
        return list(self._items)


class FakeCardStore:
    """In-memory CardStore: seen-set dedup + captured upsert calls."""

    def __init__(self, seen=None):
        self.seen = set(seen or ())
        self.upsert_calls = 0
        self.upserted_cards: list[Card] = []

    def dedup_filter(self, items):
        return [item for item in items if item.url_hash not in self.seen]

    def upsert(self, cards):
        self.upsert_calls += 1
        self.upserted_cards = list(cards)
        for card in cards:
            # Fake only needs *a* stable key per card for this in-memory test
            # double; production seen-key derivation is covered by
            # test_local_store.py against the real JsonFileCardStore.
            self.seen.add(card.url)


# T1 (Guarantee 1): build_graph's compiled node set is exactly the five named
# nodes, wired linearly START -> discover -> dedup -> summarize -> rank -> persist -> END.
def test_build_graph_node_set_and_linear_wiring():
    compiled = build_graph(FakeCardStore(), FakeDiscoverer([]))
    graph_repr = compiled.get_graph()

    node_names = set(graph_repr.nodes) - {START, END}
    assert node_names == {"discover", "dedup", "summarize", "rank", "persist"}

    edges = {(edge.source, edge.target) for edge in graph_repr.edges}
    assert edges == {
        (START, "discover"),
        ("discover", "dedup"),
        ("dedup", "summarize"),
        ("summarize", "rank"),
        ("rank", "persist"),
        ("persist", END),
    }


# T3 (Guarantee 7): cards are ranked relevance-descending, stable for ties.
def test_rank_orders_cards_by_relevance_descending_stable_for_ties(
    monkeypatch, make_raw_item, summarize_stub_factory
):
    a = make_raw_item(url="https://example.com/a", title="A")  # relevance 5
    b = make_raw_item(url="https://example.com/b", title="B")  # relevance 8
    c = make_raw_item(url="https://example.com/c", title="C")  # relevance 5 (tie with A)
    d = make_raw_item(url="https://example.com/d", title="D")  # relevance 8 (tie with B)
    relevance_by_url = {a.url: 5, b.url: 8, c.url: 5, d.url: 8}
    monkeypatch.setattr(
        nodes_module,
        "summarize_with_usage",
        summarize_stub_factory(relevance_by_url=relevance_by_url),
    )

    compiled = build_graph(FakeCardStore(), FakeDiscoverer([a, b, c, d]))
    result = compiled.invoke({"max_items": 10})

    # Descending relevance; equal-relevance items keep discovery order (stable sort).
    assert [card.title for card in result["cards"]] == ["B", "D", "A", "C"]


# T4 (Guarantee 4 / Error Handling row 1): a raising summarize() for one item
# increments `failed`, skips that item, and the run completes and persists the rest.
def test_summarize_failure_increments_failed_and_persists_remaining_cards(
    monkeypatch, make_raw_item, summarize_stub_factory
):
    good = make_raw_item(url="https://example.com/good", title="Good")
    bad = make_raw_item(url="https://example.com/bad", title="Bad")
    monkeypatch.setattr(
        nodes_module, "summarize_with_usage", summarize_stub_factory(raise_for_urls={bad.url})
    )

    store = FakeCardStore()
    compiled = build_graph(store, FakeDiscoverer([good, bad]))
    result = compiled.invoke({"max_items": 10})

    assert result["failed"] == 1
    assert result["summarized"] == 1
    assert [card.title for card in result["cards"]] == ["Good"]
    # The run completed and persisted the surviving card (not best-effort-dropped).
    assert store.upsert_calls == 1
    assert [card.title for card in store.upserted_cards] == ["Good"]


# T11 (Guarantee 3): dedup runs before the max_items cap — a seen item is never
# passed to summarize, and the cap applies to the already-deduped list.
def test_dedup_runs_before_cap_never_summarizes_seen_items(
    monkeypatch, make_raw_item, summarize_stub_factory
):
    seen_item = make_raw_item(url="https://example.com/seen", title="Seen")
    fresh_item_1 = make_raw_item(url="https://example.com/fresh1", title="Fresh1")
    fresh_item_2 = make_raw_item(url="https://example.com/fresh2", title="Fresh2")

    from shared.bedrock import TokenUsage

    calls: list[str] = []

    def spy_summarize_with_usage(item):
        calls.append(item.url)
        model_out = {
            "title": item.title,
            "summary": "s",
            "tags": [],
            "type": "news",
            "relevance": 5,
            "takeaways": [],
        }
        return model_out, TokenUsage(0, 0)

    monkeypatch.setattr(nodes_module, "summarize_with_usage", spy_summarize_with_usage)

    store = FakeCardStore(seen={seen_item.url_hash})
    discoverer = FakeDiscoverer([seen_item, fresh_item_1, fresh_item_2])
    compiled = build_graph(store, discoverer)
    # max_items=1 caps to a single item post-dedup: only fresh_item_1 (first
    # fresh item in discovery order) may be summarized — never seen_item.
    result = compiled.invoke({"max_items": 1})

    assert calls == [fresh_item_1.url]
    assert result["deduped"] == 2  # len(fresh) before the max_items cap


# T5 (Guarantee 5): re-invoking with an unchanged, populated seen store (the
# real JsonFileCardStore) yields zero new cards and leaves seen.json unchanged.
def test_rerun_with_populated_seen_store_yields_no_new_cards(
    tmp_path, monkeypatch, make_raw_item, summarize_stub_factory
):
    import curation.local as local_module
    from curation.local import JsonFileCardStore, RssDiscoverer

    item = make_raw_item(url="https://example.com/a", title="A")
    seen_path = tmp_path / "seen.json"
    cards_path = tmp_path / "cards.json"
    seen_path.write_text(json.dumps([item.url_hash]))
    seen_before = seen_path.read_text()

    monkeypatch.setattr(local_module, "discover", lambda feeds, per_feed: [item])
    monkeypatch.setattr(nodes_module, "summarize_with_usage", summarize_stub_factory())

    store = JsonFileCardStore(seen_path=seen_path, cards_path=cards_path)
    compiled = build_graph(store, RssDiscoverer())
    result = compiled.invoke({"max_items": 10})

    assert result["cards"] == []
    assert json.loads(cards_path.read_text()) == []
    assert seen_path.read_text() == seen_before


# T2 (Guarantee 2): the compiled graph with JsonFileCardStore + RssDiscoverer
# defaults reproduces the Phase 0 `pipeline.run()` logic (retired; see git
# history) — dedup -> cap -> Card.from_model -> sort by relevance desc — for
# the same stubbed inputs.
def test_graph_matches_spike_pipeline_logic_for_same_inputs(
    tmp_path, monkeypatch, make_raw_item, summarize_stub_factory
):
    import curation.local as local_module
    from curation.local import JsonFileCardStore, RssDiscoverer

    items = [
        make_raw_item(url=f"https://example.com/{i}", title=f"Item {i}")
        for i in range(5)
    ]
    relevance_by_url = {
        items[0].url: 3,
        items[1].url: 9,
        items[2].url: 7,
        items[3].url: 1,
        items[4].url: 5,
    }
    stub = summarize_stub_factory(relevance_by_url=relevance_by_url)
    monkeypatch.setattr(local_module, "discover", lambda feeds, per_feed: items)
    monkeypatch.setattr(nodes_module, "summarize_with_usage", stub)

    seen_path = tmp_path / "seen.json"
    cards_path = tmp_path / "cards.json"
    store = JsonFileCardStore(seen_path=seen_path, cards_path=cards_path)
    compiled = build_graph(store, RssDiscoverer())
    result = compiled.invoke({"max_items": 3})

    # Replicate the Phase 0 `pipeline.run()` logic inline (retired; see git
    # history) with no network/console:
    # fresh = dedup (nothing seen yet); batch = fresh[:max_items];
    # cards = [Card.from_model(item, summarize(item)) for item in batch];
    # cards.sort(key=relevance, reverse=True).
    fresh = list(items)  # nothing seen for a fresh store
    batch = fresh[:3]
    expected_cards = [Card.from_model(item, stub(item)[0]) for item in batch]
    expected_cards.sort(key=lambda c: c.relevance, reverse=True)

    assert result["cards"] == expected_cards


# T6 (Guarantee 6, portability constraint) / T28 (run-observability R15):
# no core curation module imports boto3/botocore/bedrock_agentcore or
# references AWS infra directly. Broadened by specs/run-observability to
# also cover `summary.py`/`metrics.py` (contract.md Behavior Guarantee 4 /
# intent.md's pinned `grep -rn "boto3\|botocore" ...` acceptance gate) and to
# check for `botocore`/`bedrock_agentcore` leaking in alongside `boto3`.
def test_curation_modules_do_not_import_aws_sdk_or_bedrock_agentcore():
    import ast
    from pathlib import Path

    curation_src = Path(__file__).parent.parent / "src" / "curation"
    forbidden_roots = {"boto3", "botocore", "bedrock_agentcore"}
    for filename in ("nodes.py", "graph.py", "state.py", "summary.py", "metrics.py"):
        path = curation_src / filename
        assert path.exists(), f"expected {path} to exist"
        tree = ast.parse(path.read_text(), filename=str(path))
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
        leaked = imported_roots & forbidden_roots
        assert not leaked, f"{filename} must not import {leaked}"


# =============================================================================
# specs/run-observability additions (audit.md T14-T18) — appended below the
# original curation-graph suite; nothing above this line changed in behavior,
# only the `summarize` -> `summarize_with_usage` patch target (Task 4.6).
# =============================================================================


# T14 (contract.md §6 discover_node / Success Criteria "discovered_by_source
# sums to the same total"): raw items are grouped by `RawItem.source`, and the
# grouped counts sum to `discovered`.
def test_discover_node_groups_raw_items_by_source_into_discovered_by_source(
    monkeypatch, make_raw_item, summarize_stub_factory
):
    rss_a = make_raw_item(url="https://example.com/a", source="arXiv cs.AI")
    rss_b = make_raw_item(url="https://example.com/b", source="arXiv cs.AI")
    tavily_c = make_raw_item(url="https://example.com/c", source="Tavily: general")
    monkeypatch.setattr(nodes_module, "summarize_with_usage", summarize_stub_factory())

    compiled = build_graph(FakeCardStore(), FakeDiscoverer([rss_a, rss_b, tavily_c]))
    result = compiled.invoke({"max_items": 10})

    assert result["discovered_by_source"] == {"arXiv cs.AI": 2, "Tavily: general": 1}
    assert sum(result["discovered_by_source"].values()) == result["discovered"] == 3


# T15 (contract.md §6 summarize_node: "Usage is added INSIDE the existing
# per-item try, immediately after the call returns, so tokens spent on an item
# that later fails Card.from_model are still billed to the run"): a malformed
# `relevance` makes `Card.from_model`'s `int(...)` raise AFTER
# `summarize_with_usage` already returned real usage — proving the failed
# item's tokens are still counted.
def test_summarize_node_accumulates_tokens_and_bills_tokens_for_items_that_fail_after_the_call(
    monkeypatch, make_raw_item
):
    from shared.bedrock import TokenUsage

    good = make_raw_item(url="https://example.com/good", title="Good")
    bad = make_raw_item(url="https://example.com/bad", title="Bad")

    def fake_summarize_with_usage(item):
        if item.url == bad.url:
            model_out = {
                "title": "Bad",
                "summary": "s",
                "tags": [],
                "type": "news",
                "relevance": "not-a-number",  # Card.from_model's int(...) raises
                "takeaways": [],
            }
            return model_out, TokenUsage(input_tokens=50, output_tokens=10)
        model_out = {
            "title": "Good",
            "summary": "s",
            "tags": [],
            "type": "news",
            "relevance": 5,
            "takeaways": [],
        }
        return model_out, TokenUsage(input_tokens=100, output_tokens=20)

    monkeypatch.setattr(nodes_module, "summarize_with_usage", fake_summarize_with_usage)

    compiled = build_graph(FakeCardStore(), FakeDiscoverer([good, bad]))
    result = compiled.invoke({"max_items": 10})

    assert result["failed"] == 1
    assert result["summarized"] == 1
    # Both items' usage is counted, INCLUDING the one that failed downstream.
    assert result["input_tokens"] == 150
    assert result["output_tokens"] == 30


# T16 (contract.md §6 persist_node: "Returns {"persisted": len(cards)} (was
# {})"; Behavior Guarantee 3's unchanged Spec 01 identity `summarized + failed
# == len(fresh)`).
def test_persist_node_returns_persisted_count_matching_len_cards(
    monkeypatch, make_raw_item, summarize_stub_factory
):
    a = make_raw_item(url="https://example.com/a")
    b = make_raw_item(url="https://example.com/b")
    monkeypatch.setattr(nodes_module, "summarize_with_usage", summarize_stub_factory())

    compiled = build_graph(FakeCardStore(), FakeDiscoverer([a, b]))
    result = compiled.invoke({"max_items": 10})

    assert result["persisted"] == len(result["cards"]) == 2
    assert result["summarized"] + result["failed"] == 2  # == len(fresh)


# T17 (Behavior Guarantee 7 "Bounded, non-spammy output": exactly 3 node
# records per run, each carrying the invoked `run_id`).
def test_exactly_three_node_records_emitted_per_run_each_carrying_run_id(
    monkeypatch, make_raw_item, summarize_stub_factory, caplog
):
    a = make_raw_item(url="https://example.com/a")
    monkeypatch.setattr(nodes_module, "summarize_with_usage", summarize_stub_factory())

    compiled = build_graph(FakeCardStore(), FakeDiscoverer([a]))
    with caplog.at_level(logging.INFO, logger="curation.nodes"):
        compiled.invoke({"max_items": 10, "run_id": "abc123"})

    records = []
    for record in caplog.records:
        try:
            payload = json.loads(record.getMessage())
        except (TypeError, ValueError):
            continue
        records.append(payload)

    events = [r["event"] for r in records]
    assert events == ["discover_complete", "summarize_complete", "persist_complete"]
    assert all(r["run_id"] == "abc123" for r in records)


# T18 (Data Models §3 "summarize_item_failed" record; Error Handling Contract
# row 2 — the per-item failure is now a structured WARNING, not a `print`).
def test_summarize_item_failure_emits_one_warning_with_url_and_error(
    monkeypatch, make_raw_item, summarize_stub_factory, caplog
):
    good = make_raw_item(url="https://example.com/good")
    bad = make_raw_item(url="https://example.com/bad")
    monkeypatch.setattr(
        nodes_module,
        "summarize_with_usage",
        summarize_stub_factory(raise_for_urls={bad.url}),
    )

    compiled = build_graph(FakeCardStore(), FakeDiscoverer([good, bad]))
    with caplog.at_level(logging.WARNING, logger="curation.nodes"):
        compiled.invoke({"max_items": 10})

    warnings = []
    for record in caplog.records:
        if record.levelno != logging.WARNING:
            continue
        try:
            payload = json.loads(record.getMessage())
        except (TypeError, ValueError):
            continue
        warnings.append(payload)

    assert len(warnings) == 1
    assert warnings[0]["event"] == "summarize_item_failed"
    assert warnings[0]["url"] == bad.url
    assert "error" in warnings[0]

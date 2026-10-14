"""Tests for curation-time embedding (AC1, AC2, AC3, AC8 compat).

Spec: specs/chat-retrieval/intent.md AC1-AC3, AC8; execution-plan.md
§ Validation rows AC1-AC3; tasks.md O1.

The embed function is patched at its import site in `curation.nodes` (like
`summarize_with_usage`); no real Bedrock/AWS call is ever made. Persistence is
either an in-memory fake (unit) or `DynamoCardStore` on moto (integration).

RED phase: `shared.embeddings`, `EmbeddingWriter`, the `embed` node and
`DynamoCardStore.set_embeddings` do not exist yet.
"""
from __future__ import annotations

import hashlib
import json
import logging

from langgraph.graph import END, START

import curation.nodes as nodes_module
from curation.dynamo import DynamoCardStore
from curation.graph import build_graph
from curation.interfaces import CardStore, EmbeddingWriter
from curation.local import JsonFileCardStore
from shared.config import EMBED_DIM
from shared.embeddings import card_text

CARD_TABLE_NAME = "ai-radar-cards"


def _fake_vector(text: str) -> list[float]:
    """Deterministic EMBED_DIM-long unit-ish vector derived from `text`."""
    seed = hashlib.sha256(text.encode()).digest()
    raw = [seed[i % len(seed)] + 1 for i in range(EMBED_DIM)]
    norm = sum(x * x for x in raw) ** 0.5
    return [x / norm for x in raw]


class FakeDiscoverer:
    def __init__(self, items):
        self._items = list(items)

    def discover(self):
        return list(self._items)


class FakeCardStore:
    def __init__(self):
        self.upserted_cards = []

    def dedup_filter(self, items):
        return list(items)

    def upsert(self, cards):
        self.upserted_cards = list(cards)


class FakeWriter:
    """`set_embeddings` returns the number of vectors actually written;
    `drop` simulates that many per-card write failures inside the writer."""

    def __init__(self, raises: bool = False, drop: int = 0):
        self.calls: list[dict[str, list[float]]] = []
        self._raises = raises
        self._drop = drop

    def set_embeddings(self, vectors) -> int:
        if self._raises:
            raise RuntimeError("simulated writer failure")
        self.calls.append(dict(vectors))
        return max(len(vectors) - self._drop, 0)


def _items(make_raw_item, n: int):
    return [
        make_raw_item(url=f"https://example.com/{i}", title=f"Title {i}") for i in range(n)
    ]


def _written(writer: FakeWriter) -> dict[str, list[float]]:
    merged: dict[str, list[float]] = {}
    for call in writer.calls:
        merged.update(call)
    return merged


def _records(caplog) -> list[dict]:
    out = []
    for record in caplog.records:
        try:
            payload = json.loads(record.getMessage())
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


# --- card_text: the Phase 0 `_card_text` rule (AC1) --------------------------


def test_card_text_joins_title_summary_takeaways_tags_skipping_empty_parts():
    text = card_text(
        {
            "title": "T",
            "summary": "S",
            "takeaways": ["k1", "k2"],
            "tags": ["llm", ""],
        }
    )
    assert text == "T\nS\nk1\nk2\nllm"


def test_card_text_tolerates_missing_optional_fields():
    assert card_text({"title": "Only", "summary": ""}) == "Only"


# --- AC1: every persisted card gets a vector, from card_text -----------------


def test_embed_step_writes_a_vector_for_every_persisted_card_from_card_text(
    monkeypatch, make_raw_item, summarize_stub_factory
):
    seen_texts: list[str] = []

    def fake_embed(text: str) -> list[float]:
        seen_texts.append(text)
        return _fake_vector(text)

    monkeypatch.setattr(nodes_module, "summarize_with_usage", summarize_stub_factory())
    monkeypatch.setattr(nodes_module, "embed", fake_embed)
    store, writer = FakeCardStore(), FakeWriter()
    items = _items(make_raw_item, 3)

    build_graph(store, FakeDiscoverer(items), embedding_writer=writer).invoke(
        {"max_items": 10}
    )

    written = _written(writer)
    assert set(written) == {item.url for item in items}
    assert all(len(vec) == EMBED_DIM for vec in written.values())
    expected_texts = {card_text(card.to_dict()) for card in store.upserted_cards}
    assert set(seen_texts) == expected_texts
    for card in store.upserted_cards:
        assert written[card.url] == _fake_vector(card_text(card.to_dict()))


def test_embed_runs_after_persist_in_the_graph_only_when_a_writer_is_passed():
    with_writer = build_graph(FakeCardStore(), FakeDiscoverer([]), embedding_writer=FakeWriter())
    edges = {(e.source, e.target) for e in with_writer.get_graph().edges}
    assert ("persist", "embed") in edges and ("embed", END) in edges
    assert ("persist", END) not in edges

    without = build_graph(FakeCardStore(), FakeDiscoverer([]))
    graph = without.get_graph()
    assert set(graph.nodes) - {START, END} == {
        "discover",
        "dedup",
        "summarize",
        "rank",
        "persist",
    }


def test_graph_without_a_writer_never_calls_embed_and_leaves_counters_unset(
    monkeypatch, make_raw_item, summarize_stub_factory
):
    def exploding_embed(text):
        raise AssertionError("embed must not run without an embedding_writer")

    monkeypatch.setattr(nodes_module, "summarize_with_usage", summarize_stub_factory())
    monkeypatch.setattr(nodes_module, "embed", exploding_embed)

    final = build_graph(FakeCardStore(), FakeDiscoverer(_items(make_raw_item, 2))).invoke(
        {"max_items": 10}
    )

    assert final["persisted"] == 2
    assert "embedded" not in final and "embed_failed" not in final


def test_embed_step_counts_land_in_state_and_the_embed_log_record(
    monkeypatch, make_raw_item, summarize_stub_factory, caplog
):
    monkeypatch.setattr(nodes_module, "summarize_with_usage", summarize_stub_factory())
    monkeypatch.setattr(nodes_module, "embed", _fake_vector)

    with caplog.at_level(logging.INFO, logger="curation.nodes"):
        final = build_graph(
            FakeCardStore(), FakeDiscoverer(_items(make_raw_item, 4)), embedding_writer=FakeWriter()
        ).invoke({"max_items": 10, "run_id": "run-1"})

    assert final["embedded"] == 4 and final["embed_failed"] == 0
    embed_records = [r for r in _records(caplog) if "embed_failed" in r]
    assert len(embed_records) == 1
    assert embed_records[0]["embedded"] == 4
    assert embed_records[0]["run_id"] == "run-1"


# --- AC2: embedding never fails a run ----------------------------------------


def test_titan_failure_on_one_card_still_persists_all_cards_and_logs_one_failure(
    monkeypatch, make_raw_item, summarize_stub_factory, caplog
):
    items = _items(make_raw_item, 6)
    bad = items[2]

    def flaky_embed(text: str) -> list[float]:
        if "Title 2" in text:
            raise RuntimeError("simulated Titan throttle")
        return _fake_vector(text)

    monkeypatch.setattr(nodes_module, "summarize_with_usage", summarize_stub_factory())
    monkeypatch.setattr(nodes_module, "embed", flaky_embed)
    store, writer = FakeCardStore(), FakeWriter()

    with caplog.at_level(logging.INFO, logger="curation.nodes"):
        final = build_graph(store, FakeDiscoverer(items), embedding_writer=writer).invoke(
            {"max_items": 10}
        )

    assert len(store.upserted_cards) == 6
    assert final["persisted"] == 6
    assert final["embedded"] == 5 and final["embed_failed"] == 1
    assert bad.url not in _written(writer)
    assert len(_written(writer)) == 5
    embed_records = [r for r in _records(caplog) if "embed_failed" in r]
    assert embed_records[0]["embed_failed"] == 1 and embed_records[0]["embedded"] == 5


def test_unwritten_vectors_are_reported_as_embed_failed_not_embedded(
    monkeypatch, make_raw_item, summarize_stub_factory, caplog
):
    """F1: `embedded` comes from the writer's returned count, so a per-card
    write failure inside the writer cannot over-report."""
    monkeypatch.setattr(nodes_module, "summarize_with_usage", summarize_stub_factory())
    monkeypatch.setattr(nodes_module, "embed", _fake_vector)
    store = FakeCardStore()

    with caplog.at_level(logging.INFO, logger="curation.nodes"):
        final = build_graph(
            store,
            FakeDiscoverer(_items(make_raw_item, 5)),
            embedding_writer=FakeWriter(drop=2),
        ).invoke({"max_items": 10})

    assert len(store.upserted_cards) == 5 and final["persisted"] == 5
    assert final["embedded"] == 3 and final["embed_failed"] == 2
    record = next(r for r in _records(caplog) if "embed_failed" in r)
    assert record["embedded"] == 3 and record["embed_failed"] == 2


def test_embed_failures_and_unwritten_vectors_both_count_as_failed(
    monkeypatch, make_raw_item, summarize_stub_factory
):
    def flaky_embed(text: str) -> list[float]:
        if "Title 0" in text:
            raise RuntimeError("simulated Titan failure")
        return _fake_vector(text)

    monkeypatch.setattr(nodes_module, "summarize_with_usage", summarize_stub_factory())
    monkeypatch.setattr(nodes_module, "embed", flaky_embed)

    final = build_graph(
        FakeCardStore(),
        FakeDiscoverer(_items(make_raw_item, 5)),
        embedding_writer=FakeWriter(drop=1),
    ).invoke({"max_items": 10})

    assert final["embedded"] == 3  # 4 vectors given, 1 not written
    assert final["embed_failed"] == 2  # 1 Titan failure + 1 unwritten


def test_writer_failure_does_not_fail_the_run_or_unpersist_cards(
    monkeypatch, make_raw_item, summarize_stub_factory
):
    monkeypatch.setattr(nodes_module, "summarize_with_usage", summarize_stub_factory())
    monkeypatch.setattr(nodes_module, "embed", _fake_vector)
    store = FakeCardStore()

    final = build_graph(
        store, FakeDiscoverer(_items(make_raw_item, 3)), embedding_writer=FakeWriter(raises=True)
    ).invoke({"max_items": 10})

    assert len(store.upserted_cards) == 3
    assert final["persisted"] == 3


# --- AC1/AC2/AC3 against DynamoDB (moto) -------------------------------------


def test_graph_run_against_dynamo_leaves_a_normalized_embed_dim_vector_on_every_card(
    monkeypatch, dynamo_resource, dynamo_table, make_raw_item, summarize_stub_factory
):
    monkeypatch.setattr(nodes_module, "summarize_with_usage", summarize_stub_factory())
    monkeypatch.setattr(nodes_module, "embed", _fake_vector)
    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=dynamo_resource)

    build_graph(
        store, FakeDiscoverer(_items(make_raw_item, 6)), embedding_writer=store
    ).invoke({"max_items": 10})

    items = dynamo_table.scan()["Items"]
    assert len(items) == 6
    for item in items:
        vec = [float(x) for x in item["embedding"]]
        assert len(vec) == EMBED_DIM
        assert abs(sum(x * x for x in vec) - 1.0) < 1e-6


def test_titan_failure_against_dynamo_persists_the_card_without_an_embedding(
    monkeypatch, dynamo_resource, dynamo_table, make_raw_item, summarize_stub_factory
):
    def flaky_embed(text: str) -> list[float]:
        if "Title 0" in text:
            raise RuntimeError("simulated Titan failure")
        return _fake_vector(text)

    monkeypatch.setattr(nodes_module, "summarize_with_usage", summarize_stub_factory())
    monkeypatch.setattr(nodes_module, "embed", flaky_embed)
    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=dynamo_resource)

    build_graph(
        store, FakeDiscoverer(_items(make_raw_item, 3)), embedding_writer=store
    ).invoke({"max_items": 10})

    items = {i["title"]: i for i in dynamo_table.scan()["Items"]}
    assert len(items) == 3
    assert "embedding" not in items["Title 0"]
    assert len(items["Title 1"]["embedding"]) == EMBED_DIM


# --- AC8: Protocol seams unchanged -------------------------------------------


def test_embedding_writer_is_a_separate_protocol_not_part_of_card_store():
    assert not hasattr(CardStore, "set_embeddings")
    assert isinstance(JsonFileCardStore(), CardStore)
    assert not isinstance(JsonFileCardStore(), EmbeddingWriter)


def test_dynamo_card_store_satisfies_embedding_writer_protocol(dynamo_resource):
    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=dynamo_resource)
    assert isinstance(store, EmbeddingWriter)
    assert isinstance(store, CardStore)

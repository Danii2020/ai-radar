"""Tests for `src/curation/dynamo.py` — `DynamoCardStore`.

Spec: specs/dynamodb-card-store/contract.md Behavior Guarantees 1-8,
Error Handling Contract rows 1-5; specs/dynamodb-card-store/tasks.md T1-T10.

All DynamoDB access is mocked in-process via the `dynamo_resource`/`dynamo_table`
fixtures (`tests/conftest.py`, `moto.mock_aws`) — zero real-AWS calls. The
`card_id`/`_url_hash` literal is recomputed here only to assert the bridge
(Guarantee 2), never re-implemented as production logic under test.

RED phase: `src/curation/dynamo.py` does not exist yet. Every test in this file
is expected to fail at collection with `ModuleNotFoundError: No module named
'curation.dynamo'` until the implementation lands.
"""
from __future__ import annotations

import ast
import hashlib
from decimal import Decimal
from pathlib import Path

from boto3.dynamodb.conditions import Key

from spike.cards import Card

from curation.dynamo import DynamoCardStore
from curation.graph import build_graph
from curation.interfaces import CardStore

CARD_TABLE_NAME = "ai-radar-cards"  # fixed per contract.md "Decisions"


def _url_hash(url: str) -> str:
    """Mirror the RawItem.url_hash / Card.url -> card_id rule from contract.md
    Guarantee 2 — used only to assert the bridge, not a reimplementation."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


class _NoCallResource:
    """Double whose `batch_get_item`/`update_item` raise if invoked — proves
    empty-input calls make no AWS round trip (Error Handling Contract row 2).
    `.Table()` itself is allowed (building a local resource handle is not a
    network call), only the actual read/write methods are poisoned."""

    def Table(self, name):
        return _NoCallTable()

    def batch_get_item(self, **kwargs):
        raise AssertionError("empty input must not call batch_get_item")


class _NoCallTable:
    def update_item(self, **kwargs):
        raise AssertionError("empty input must not call update_item")

    def __getattr__(self, name):
        def _fail(*args, **kwargs):
            raise AssertionError(f"empty input must not call table.{name}")

        return _fail


class _FlakyResource:
    """Wraps a real (moto-backed) resource; the wrapped Table's `update_item`
    raises for exactly one target `card_id` and delegates everything else to
    the real table — proves per-card resilience (Error Handling Contract row 1)
    without faking the whole DynamoDB surface."""

    def __init__(self, real_resource, fail_card_id: str):
        self._real_resource = real_resource
        self._fail_card_id = fail_card_id

    def Table(self, name):
        return _FlakyTable(self._real_resource.Table(name), self._fail_card_id)

    def batch_get_item(self, **kwargs):
        return self._real_resource.batch_get_item(**kwargs)


class _FlakyTable:
    def __init__(self, real_table, fail_card_id: str):
        self._real_table = real_table
        self._fail_card_id = fail_card_id

    def update_item(self, **kwargs):
        if kwargs.get("Key", {}).get("card_id") == self._fail_card_id:
            raise RuntimeError("simulated update_item failure")
        return self._real_table.update_item(**kwargs)

    def __getattr__(self, name):
        return getattr(self._real_table, name)


class _FakeDiscoverer:
    def __init__(self, items):
        self._items = list(items)

    def discover(self):
        return list(self._items)


# T1 (Guarantee 2): card_id == sha256(url)[:16] for both RawItem.url_hash and
# the Card the store derives it from; after upsert, dedup_filter excludes it.
def test_card_id_matches_raw_item_url_hash_and_upsert_makes_dedup_exclude_it(
    dynamo_resource, dynamo_table, make_raw_item, make_model_out
):
    item = make_raw_item(url="https://example.com/a")
    card = Card.from_model(item, make_model_out())
    expected_card_id = _url_hash(item.url)
    assert item.url_hash == expected_card_id

    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=dynamo_resource)
    store.upsert([card])

    persisted = dynamo_table.get_item(Key={"card_id": expected_card_id})["Item"]
    assert persisted["card_id"] == expected_card_id
    assert store.dedup_filter([item]) == []


# T2 (Guarantee 3): dedup_filter is order-preserving and excludes only items
# already present in the table.
def test_dedup_filter_preserves_order_and_excludes_only_already_stored_items(
    dynamo_resource, make_raw_item, make_model_out
):
    a = make_raw_item(url="https://example.com/a", title="A")
    b = make_raw_item(url="https://example.com/b", title="B")
    c = make_raw_item(url="https://example.com/c", title="C")

    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=dynamo_resource)
    store.upsert([Card.from_model(b, make_model_out())])

    result = store.dedup_filter([a, b, c])

    assert [item.url for item in result] == [a.url, c.url]


# T2 (Guarantee 3 / Error Handling row 2): empty input returns [] immediately,
# with no AWS call at all.
def test_dedup_filter_empty_input_returns_empty_list_with_no_aws_call():
    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=_NoCallResource())
    assert store.dedup_filter([]) == []


# Error Handling row 2 (upsert side): empty input is a no-op, no AWS call.
def test_upsert_empty_list_is_a_noop_with_no_aws_call():
    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=_NoCallResource())
    assert store.upsert([]) is None


# T3 (Guarantee 4): upsert(batch) twice yields exactly one item per card_id
# (no duplicates), created_at is unchanged, updated_at advances (>=).
def test_upsert_twice_is_idempotent_created_at_stable_updated_at_advances(
    dynamo_resource, dynamo_table, make_raw_item, make_model_out
):
    item = make_raw_item(url="https://example.com/a")
    card = Card.from_model(item, make_model_out())
    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=dynamo_resource)

    store.upsert([card])
    first = dynamo_table.get_item(Key={"card_id": item.url_hash})["Item"]

    store.upsert([card])
    second = dynamo_table.get_item(Key={"card_id": item.url_hash})["Item"]

    assert dynamo_table.scan()["Count"] == 1
    assert second["created_at"] == first["created_at"]
    assert second["updated_at"] >= first["updated_at"]


# Error Handling row 4: a card_id appearing twice in one upsert batch persists
# exactly one item; the last update_item call wins.
def test_upsert_batch_with_duplicate_card_id_persists_one_item_last_write_wins(
    dynamo_resource, dynamo_table, make_raw_item, make_model_out
):
    item = make_raw_item(url="https://example.com/a")
    first_card = Card.from_model(item, make_model_out(title="First", relevance=3))
    second_card = Card.from_model(item, make_model_out(title="Second", relevance=8))

    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=dynamo_resource)
    store.upsert([first_card, second_card])

    assert dynamo_table.scan()["Count"] == 1
    persisted = dynamo_table.get_item(Key={"card_id": item.url_hash})["Item"]
    assert persisted["title"] == "Second"
    assert int(persisted["relevance"]) == 8


# T4: every Card field + card_id/created_at/updated_at/gsi_pk/gsi_sk is
# written; `embedding` is absent.
def test_upsert_writes_full_item_schema_and_never_writes_embedding(
    dynamo_resource, dynamo_table, make_raw_item, make_model_out
):
    item = make_raw_item(url="https://example.com/a")
    model_out = make_model_out(
        title="Model Title",
        summary="A summary.",
        tags=["llm", "rag"],
        type_="paper",
        relevance=9,
        takeaways=["k1", "k2"],
    )
    card = Card.from_model(item, model_out)
    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=dynamo_resource)

    store.upsert([card])

    persisted = dynamo_table.get_item(Key={"card_id": item.url_hash})["Item"]
    assert persisted["title"] == card.title
    assert persisted["url"] == card.url
    assert persisted["source"] == card.source
    assert persisted["summary"] == card.summary
    assert list(persisted["tags"]) == card.tags
    assert persisted["type"] == card.type
    assert int(persisted["relevance"]) == card.relevance
    assert persisted["published"] == card.published
    assert list(persisted["takeaways"]) == card.takeaways
    assert "created_at" in persisted
    assert "updated_at" in persisted
    assert persisted["gsi_pk"] == "CARD"
    assert persisted["gsi_sk"] == f"{card.relevance:03d}#{card.published}"
    assert "embedding" not in persisted


# T5 (Guarantee 6): gsi_sk == f"{relevance:03d}#{published}"; a dateless card
# (published == "") yields a trailing "#".
def test_gsi_sk_is_zero_padded_relevance_and_date_with_dateless_trailing_hash(
    dynamo_resource, dynamo_table, make_raw_item, make_model_out
):
    dated = make_raw_item(url="https://example.com/dated", published="2026-07-20")
    dateless = make_raw_item(url="https://example.com/dateless", published="")

    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=dynamo_resource)
    store.upsert(
        [
            Card.from_model(dated, make_model_out(relevance=7)),
            Card.from_model(dateless, make_model_out(relevance=7)),
        ]
    )

    dated_item = dynamo_table.get_item(Key={"card_id": dated.url_hash})["Item"]
    dateless_item = dynamo_table.get_item(Key={"card_id": dateless.url_hash})["Item"]

    assert dated_item["gsi_sk"] == "007#2026-07-20"
    assert dateless_item["gsi_sk"] == "007#"


# T6 (Guarantee 5): a pre-seeded `embedding` (simulating a Phase 3 write)
# survives byte-for-byte after a re-upsert of the same card.
def test_upsert_never_clobbers_a_preexisting_embedding(
    dynamo_resource, dynamo_table, make_raw_item, make_model_out
):
    item = make_raw_item(url="https://example.com/a")
    card = Card.from_model(item, make_model_out())
    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=dynamo_resource)
    store.upsert([card])

    seeded_embedding = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3")]
    dynamo_table.update_item(
        Key={"card_id": item.url_hash},
        UpdateExpression="SET embedding = :emb",
        ExpressionAttributeValues={":emb": seeded_embedding},
    )

    store.upsert([card])  # re-run, e.g. next day's re-curation

    persisted = dynamo_table.get_item(Key={"card_id": item.url_hash})["Item"]
    assert persisted["embedding"] == seeded_embedding


# T7 (Guarantee 7 / Error Handling row 1): one card raising during update_item
# increments failures() and is skipped; the rest of the batch still persists.
def test_upsert_one_card_raising_increments_failures_and_persists_the_rest(
    dynamo_resource, dynamo_table, make_raw_item, make_model_out
):
    good = make_raw_item(url="https://example.com/good")
    bad = make_raw_item(url="https://example.com/bad")
    good_card = Card.from_model(good, make_model_out(title="Good"))
    bad_card = Card.from_model(bad, make_model_out(title="Bad"))

    flaky = _FlakyResource(dynamo_resource, fail_card_id=bad.url_hash)
    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=flaky)

    store.upsert([good_card, bad_card])

    assert store.failures() == 1
    persisted_ids = {i["card_id"] for i in dynamo_table.scan()["Items"]}
    assert persisted_ids == {good.url_hash}


# T8 (Guarantee 1): structural Protocol conformance.
def test_dynamo_card_store_satisfies_card_store_protocol(dynamo_resource):
    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=dynamo_resource)
    assert isinstance(store, CardStore)


# T8 (Guarantee 1): the *unchanged* Spec 01 graph compiles and runs end-to-end
# with DynamoCardStore swapped in for JsonFileCardStore by injection alone.
def test_build_graph_runs_end_to_end_against_dynamo_card_store(
    monkeypatch, dynamo_resource, dynamo_table, make_raw_item, summarize_stub_factory
):
    import curation.nodes as nodes_module

    item = make_raw_item(url="https://example.com/a", title="A")
    monkeypatch.setattr(
        nodes_module, "summarize", summarize_stub_factory(relevance_by_url={item.url: 7})
    )

    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=dynamo_resource)
    compiled = build_graph(store, _FakeDiscoverer([item]))
    result = compiled.invoke({"max_items": 10})

    assert result["summarized"] == 1
    persisted = dynamo_table.get_item(Key={"card_id": item.url_hash})["Item"]
    assert persisted["title"] == "A"
    assert int(persisted["relevance"]) == 7


# T9 (Guarantee 6, design validation only - not a production reader): the
# feed-by-score GSI orders items by descending score, then descending date.
def test_feed_by_score_gsi_query_orders_by_score_desc_then_date_desc(
    dynamo_resource, dynamo_table, make_raw_item, make_model_out
):
    low = make_raw_item(url="https://example.com/low", published="2026-07-01")
    high_old = make_raw_item(url="https://example.com/high-old", published="2026-07-01")
    high_new = make_raw_item(url="https://example.com/high-new", published="2026-07-15")

    store = DynamoCardStore(table_name=CARD_TABLE_NAME, client=dynamo_resource)
    store.upsert(
        [
            Card.from_model(low, make_model_out(title="Low", relevance=2)),
            Card.from_model(high_old, make_model_out(title="HighOld", relevance=9)),
            Card.from_model(high_new, make_model_out(title="HighNew", relevance=9)),
        ]
    )

    resp = dynamo_table.query(
        IndexName="feed-by-score",
        KeyConditionExpression=Key("gsi_pk").eq("CARD"),
        ScanIndexForward=False,
    )

    assert [i["title"] for i in resp["Items"]] == ["HighNew", "HighOld", "Low"]


# T10 (Guarantee 8): boto3 is imported only in dynamo.py; it is absent from the
# portable curation modules (nodes/graph/state/interfaces/local).
def test_boto3_import_confined_to_dynamo_module():
    curation_src = Path(__file__).parent.parent / "src" / "curation"

    def _imported_roots(path: Path) -> set[str]:
        tree = ast.parse(path.read_text(), filename=str(path))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        return roots

    portable_files = ["nodes.py", "graph.py", "state.py", "interfaces.py", "local.py"]
    for filename in portable_files:
        path = curation_src / filename
        assert path.exists(), f"expected {path} to exist"
        assert "boto3" not in _imported_roots(path), f"{filename} must not import boto3"

    dynamo_path = curation_src / "dynamo.py"
    assert dynamo_path.exists(), "expected src/curation/dynamo.py to exist"
    assert "boto3" in _imported_roots(dynamo_path), (
        "dynamo.py is the one designated infra-adapter site and must import boto3"
    )

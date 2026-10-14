"""Tests for the embedding backfill (AC4).

Spec: specs/chat-retrieval/intent.md AC4; execution-plan.md § Validation row
AC4; tasks.md O2.

Seeds items straight into the moto table, runs `curation.backfill.
backfill_embeddings(store)` against a `DynamoCardStore`, with the embed
function patched at its import site in `curation.backfill`. Zero real AWS.

Interface assumed (the plan pins only the module and the counts):
`backfill_embeddings(store)` returns an object (or dict) exposing `embedded`,
`skipped`, `failed`; `run_backfill_embeddings.main()` prints
`embedded=N skipped=N failed=N`.

RED phase: `curation.backfill` and `run_backfill_embeddings` do not exist yet.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import curation.backfill as backfill_module
from curation.dynamo import DynamoCardStore
from shared.config import EMBED_DIM
from shared.embeddings import card_text

CARD_TABLE_NAME = "ai-radar-cards"


def _vec(first: float, dim: int = EMBED_DIM) -> list[float]:
    return [first] + [0.0] * (dim - 1)


def _stored(vec: list[float]) -> list[Decimal]:
    return [Decimal(str(x)) for x in vec]


def _counts(result) -> tuple[int, int, int]:
    def get(key: str) -> int:
        return int(result[key] if isinstance(result, dict) else getattr(result, key))

    return get("embedded"), get("skipped"), get("failed")


def _embed_stub(calls: list[str], fail_if_contains: str | None = None):
    def _embed(text: str) -> list[float]:
        calls.append(text)
        if fail_if_contains and fail_if_contains in text:
            raise RuntimeError("simulated Titan failure")
        return _vec(0.5)

    return _embed


def _store(dynamo_resource) -> DynamoCardStore:
    return DynamoCardStore(table_name=CARD_TABLE_NAME, client=dynamo_resource)


def _seed_mixed(put_card_item, embedded: int, missing: int) -> None:
    for i in range(embedded):
        put_card_item(f"has{i}", embedding=_stored(_vec(1.0)))
    for i in range(missing):
        put_card_item(f"miss{i}")


def test_backfill_embeds_only_cards_without_a_vector_and_reports_counts(
    monkeypatch, dynamo_resource, dynamo_table, put_card_item
):
    _seed_mixed(put_card_item, embedded=28, missing=12)
    calls: list[str] = []
    monkeypatch.setattr(backfill_module, "embed", _embed_stub(calls))

    result = backfill_module.backfill_embeddings(_store(dynamo_resource))

    assert _counts(result) == (12, 28, 0)
    assert len(calls) == 12
    for item in dynamo_table.scan()["Items"]:
        assert len(item["embedding"]) == EMBED_DIM
    untouched = dynamo_table.get_item(Key={"card_id": "has0"})["Item"]
    assert [float(x) for x in untouched["embedding"]] == _vec(1.0)


def test_backfill_embeds_from_the_card_text_rule(
    monkeypatch, dynamo_resource, dynamo_table, put_card_item
):
    put_card_item("only", takeaways=["k1"], tags=["llm"])
    calls: list[str] = []
    monkeypatch.setattr(backfill_module, "embed", _embed_stub(calls))

    backfill_module.backfill_embeddings(_store(dynamo_resource))

    item = dynamo_table.get_item(Key={"card_id": "only"})["Item"]
    assert calls == [card_text(item)]


def test_second_backfill_run_embeds_nothing(
    monkeypatch, dynamo_resource, put_card_item
):
    _seed_mixed(put_card_item, embedded=3, missing=2)
    calls: list[str] = []
    monkeypatch.setattr(backfill_module, "embed", _embed_stub(calls))
    store = _store(dynamo_resource)

    backfill_module.backfill_embeddings(store)
    calls.clear()
    second = backfill_module.backfill_embeddings(store)

    assert _counts(second) == (0, 5, 0)
    assert calls == []


def test_wrong_length_embedding_counts_as_unembedded_and_is_healed(
    monkeypatch, dynamo_resource, dynamo_table, put_card_item
):
    put_card_item("old-dim", embedding=_stored(_vec(1.0, dim=3)))
    put_card_item("good", embedding=_stored(_vec(1.0)))
    monkeypatch.setattr(backfill_module, "embed", _embed_stub([]))

    result = backfill_module.backfill_embeddings(_store(dynamo_resource))

    assert _counts(result) == (1, 1, 0)
    healed = dynamo_table.get_item(Key={"card_id": "old-dim"})["Item"]
    assert len(healed["embedding"]) == EMBED_DIM


def test_one_cards_embed_failure_is_counted_and_does_not_stop_the_rest(
    monkeypatch, dynamo_resource, dynamo_table, put_card_item
):
    put_card_item("bad", title="POISON")
    put_card_item("ok1")
    put_card_item("ok2")
    monkeypatch.setattr(
        backfill_module, "embed", _embed_stub([], fail_if_contains="POISON")
    )

    result = backfill_module.backfill_embeddings(_store(dynamo_resource))

    assert _counts(result) == (2, 0, 1)
    assert "embedding" not in dynamo_table.get_item(Key={"card_id": "bad"})["Item"]
    assert len(dynamo_table.get_item(Key={"card_id": "ok2"})["Item"]["embedding"]) == EMBED_DIM

    # The failed card is retried on the next run (idempotent catch-up).
    monkeypatch.setattr(backfill_module, "embed", _embed_stub([]))
    again = backfill_module.backfill_embeddings(_store(dynamo_resource))
    assert _counts(again) == (1, 2, 0)


def test_backfill_on_an_empty_table_reports_zeros(monkeypatch, dynamo_resource):
    monkeypatch.setattr(backfill_module, "embed", _embed_stub([]))

    result = backfill_module.backfill_embeddings(_store(dynamo_resource))

    assert _counts(result) == (0, 0, 0)


def test_backfill_sees_cards_beyond_one_query_page(
    monkeypatch, dynamo_resource, dynamo_table, put_card_item
):
    class _PagingResource:
        def __init__(self, real):
            self._real = real

        def Table(self, name):
            return _PagingTable(self._real.Table(name))

        def __getattr__(self, name):
            return getattr(self._real, name)

    class _PagingTable:
        def __init__(self, real):
            self._real = real

        def query(self, **kwargs):
            return self._real.query(**{**kwargs, "Limit": 2})

        def __getattr__(self, name):
            return getattr(self._real, name)

    for i in range(7):
        put_card_item(f"c{i}", relevance=i + 1)
    monkeypatch.setattr(backfill_module, "embed", _embed_stub([]))
    store = DynamoCardStore(
        table_name=CARD_TABLE_NAME, client=_PagingResource(dynamo_resource)
    )

    result = backfill_module.backfill_embeddings(store)

    assert _counts(result) == (7, 0, 0)


def test_cli_prints_embedded_skipped_failed_counts(
    monkeypatch, capsys, dynamo_resource, put_card_item
):
    import run_backfill_embeddings

    _seed_mixed(put_card_item, embedded=2, missing=1)
    monkeypatch.setattr(backfill_module, "embed", _embed_stub([]))
    monkeypatch.setattr(
        run_backfill_embeddings,
        "DynamoCardStore",
        lambda *a, **k: _store(dynamo_resource),
        raising=False,
    )

    run_backfill_embeddings.main()

    out = capsys.readouterr().out
    assert "embedded=1" in out and "skipped=2" in out and "failed=0" in out


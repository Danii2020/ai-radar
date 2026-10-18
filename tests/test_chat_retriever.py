"""Tests for the Plane B DynamoDB retriever (AC5, AC6).

Spec: specs/chat-retrieval/intent.md AC5, AC6; execution-plan.md § Validation
rows AC5/AC6; tasks.md O3.

Plane B tests never import `DynamoCardStore`: items are seeded straight into
the moto table with `put_card_item` (tests/conftest.py). The query embedding is
an injected `embed_fn`; zero real AWS/Bedrock calls.

RED phase: `src/chat/` does not exist yet.
"""
from __future__ import annotations

import math
from decimal import Decimal

from chat.retriever import DynamoCardRetriever
from shared.config import EMBED_DIM

CARD_TABLE_NAME = "ai-radar-cards"


def _unit(angle: float) -> list[float]:
    """Unit vector at `angle` radians from e0 in the first two dimensions, so
    its dot product with e0 is exactly cos(angle)."""
    return [math.cos(angle), math.sin(angle)] + [0.0] * (EMBED_DIM - 2)


def _stored(vec: list[float]) -> list[Decimal]:
    return [Decimal(str(x)) for x in vec]


E0 = _unit(0.0)


def _retriever(resource, query_vec=E0, calls=None) -> DynamoCardRetriever:
    def embed_fn(text: str) -> list[float]:
        if calls is not None:
            calls.append(text)
        return query_vec

    return DynamoCardRetriever(
        table_name=CARD_TABLE_NAME, resource=resource, embed_fn=embed_fn
    )


def _seed_angles(put_card_item, angles: dict[str, float]) -> None:
    for card_id, angle in angles.items():
        put_card_item(card_id, embedding=_stored(_unit(angle)))


# --- AC5 ---------------------------------------------------------------------


def test_search_returns_top_k_by_cosine_descending_as_dict_score_pairs(
    dynamo_resource, put_card_item
):
    _seed_angles(
        put_card_item, {"far": 1.4, "mid": 0.6, "near": 0.1, "nearer": 0.0, "mid2": 1.0}
    )
    calls: list[str] = []

    hits = _retriever(dynamo_resource, calls=calls).search("open-weight coding models", 4)

    assert calls == ["open-weight coding models"]
    assert [card["url"].rsplit("/", 1)[1] for card, _ in hits] == [
        "nearer",
        "near",
        "mid",
        "mid2",
    ]
    scores = [score for _, score in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(isinstance(score, float) for score in scores)
    assert abs(scores[0] - 1.0) < 1e-9
    assert abs(scores[2] - math.cos(0.6)) < 1e-9


def test_returned_card_dicts_carry_card_fields_but_never_the_vector(
    dynamo_resource, put_card_item
):
    _seed_angles(put_card_item, {"a": 0.0, "b": 0.5})

    hits = _retriever(dynamo_resource).search("q", 2)

    for card, _ in hits:
        assert "embedding" not in card
        assert card["title"] and card["summary"] and card["url"] and card["source"]


def test_unembedded_and_wrong_length_cards_are_excluded(dynamo_resource, put_card_item):
    put_card_item("good", embedding=_stored(_unit(0.2)))
    put_card_item("no-vector")
    put_card_item("short", embedding=_stored([1.0, 0.0, 0.0]))

    hits = _retriever(dynamo_resource).search("q", 10)

    assert [card["url"].rsplit("/", 1)[1] for card, _ in hits] == ["good"]


def test_k_larger_than_the_corpus_returns_every_embedded_card(
    dynamo_resource, put_card_item
):
    _seed_angles(put_card_item, {"a": 0.1, "b": 0.2, "c": 0.3})

    assert len(_retriever(dynamo_resource).search("q", 50)) == 3


def test_empty_corpus_returns_empty_list(dynamo_resource):
    assert _retriever(dynamo_resource).search("q", 4) == []


def test_fully_unembedded_corpus_returns_empty_list(dynamo_resource, put_card_item):
    put_card_item("a")
    put_card_item("b")

    assert _retriever(dynamo_resource).search("q", 4) == []


def test_stored_decimal_vectors_score_like_the_in_memory_dot_product(
    dynamo_resource, put_card_item
):
    """Decimal -> float round trip: the score equals the plain float dot
    product `CardIndex.search` computes for the same vectors."""
    query = _unit(0.3)
    stored = _unit(0.9)
    put_card_item("a", embedding=_stored(stored))

    ((_, score),) = _retriever(dynamo_resource, query_vec=query).search("q", 1)

    expected = sum(x * y for x, y in zip(query, stored))
    assert abs(score - expected) < 1e-9


# --- AC6 ---------------------------------------------------------------------


class _PagingTable:
    """Real (moto) table whose `query` is forced to 2 items per page, so the
    real `LastEvaluatedKey` machinery is exercised; records every call and
    poisons `scan`."""

    def __init__(self, real_table):
        self._real = real_table
        self.query_calls: list[dict] = []

    def query(self, **kwargs):
        self.query_calls.append(dict(kwargs))
        return self._real.query(**{**kwargs, "Limit": 2})

    def scan(self, **kwargs):
        raise AssertionError("the retriever must never Scan")

    def __getattr__(self, name):
        return getattr(self._real, name)


class _PagingResource:
    def __init__(self, real):
        self._real = real
        self.table: _PagingTable | None = None

    def Table(self, name):
        self.table = _PagingTable(self._real.Table(name))
        return self.table

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_retrieval_paginates_query_pages_so_every_embedded_card_is_a_candidate(
    dynamo_resource, put_card_item
):
    # Lower relevance sorts later in feed-by-score, i.e. on the last page;
    # the best match lives there.
    for i in range(7):
        put_card_item(
            f"c{i}", relevance=9 - i, embedding=_stored(_unit(0.5 + 0.1 * (6 - i)))
        )
    put_card_item("best-on-last-page", relevance=1, embedding=_stored(_unit(0.0)))
    paging = _PagingResource(dynamo_resource)

    hits = _retriever(paging).search("q", 100)

    assert len(hits) == 8
    assert hits[0][0]["url"].endswith("best-on-last-page")
    assert paging.table is not None and len(paging.table.query_calls) >= 4


def test_retrieval_queries_the_feed_by_score_index_and_never_scans(
    dynamo_resource, put_card_item
):
    _seed_angles(put_card_item, {"a": 0.1, "b": 0.2, "c": 0.3})
    paging = _PagingResource(dynamo_resource)

    hits = _retriever(paging).search("q", 3)

    assert len(hits) == 3  # `scan` is poisoned: reaching here means no Scan
    assert paging.table is not None
    assert paging.table.query_calls
    assert all(c.get("IndexName") == "feed-by-score" for c in paging.table.query_calls)
    # Pages after the first resume from the previous LastEvaluatedKey.
    assert any("ExclusiveStartKey" in c for c in paging.table.query_calls[1:])


def test_retrieval_only_considers_the_card_partition_of_the_index(
    dynamo_resource, put_card_item
):
    """Key condition is gsi_pk == "CARD": an embedded item in another
    partition is never a candidate."""
    put_card_item("card", embedding=_stored(_unit(0.1)))
    put_card_item("other", embedding=_stored(_unit(0.0)), gsi_pk="OTHER")

    hits = _retriever(dynamo_resource).search("q", 10)

    assert [c["url"].rsplit("/", 1)[1] for c, _ in hits] == ["card"]


def test_dynamo_resource_is_bound_to_the_shared_region_without_env(monkeypatch):
    """No AWS_DEFAULT_REGION/AWS_REGION in the environment must not raise
    NoRegionError: the resource gets `shared.config.AWS_REGION` explicitly."""
    import boto3

    from chat import retriever
    from shared.config import AWS_REGION

    for var in ("AWS_DEFAULT_REGION", "AWS_REGION"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(retriever, "_resource", None)
    seen: dict = {}

    def fake_resource(name, **kwargs):
        seen.update(name=name, **kwargs)
        return object()

    monkeypatch.setattr(boto3, "resource", fake_resource)
    retriever._dynamo_resource()
    assert seen == {"name": "dynamodb", "region_name": AWS_REGION}

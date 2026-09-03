"""Tests for `src/contracts/card.py` — `CardOut`, `FeedResponse`, `json_schema()`.

Spec: specs/feed-api/contract.md "`src/contracts/card.py` — CREATE (the
published contract)", "Mapping: DynamoDB item -> CardOut"; specs/feed-api/
intent.md Goal 2; specs/feed-api/audit.md T28 (added by the test-writer — no
existing row covered direct unit-level validation of `CardOut`/`FeedResponse`
in isolation from a DynamoDB query; T23 in `tests/test_feed_query.py` proves
the same guarantees end-to-end through `query_feed`, this file proves the
model's own validation/coercion rules directly, which is the cheaper, more
targeted place to catch a regression in the Pydantic model itself).

Zero AWS/network — this module is pure `pydantic`.

RED phase: `src/contracts/card.py` does not exist yet. Every test in this file
is expected to fail at collection with `ModuleNotFoundError: No module named
'contracts.card'` (or similar) until the implementation lands.
"""
from __future__ import annotations

from decimal import Decimal

import pydantic
import pytest

from contracts.card import CardOut, FeedResponse, json_schema


def _raw_item(**overrides) -> dict:
    """A DynamoDB-item-shaped dict with every CardOut field present, as
    `query_feed` would hand to `CardOut.model_validate` (minus `gsi_pk`/
    `gsi_sk`/`embedding`, which a real query never projects but which extra
    fields, if present, must still be ignored per `extra="ignore"`)."""
    item = {
        "card_id": "0a1b2c3d4e5f6071",
        "title": "A Title",
        "url": "https://example.com/a",
        "source": "Tavily: example.com",
        "summary": "A summary.",
        "tags": ["llm", "agents"],
        "type": "news",
        "relevance": Decimal("8"),
        "published": "2026-08-29",
        "takeaways": ["k1", "k2"],
        "created_at": "2026-08-29T06:00:03.114512+00:00",
        "updated_at": "2026-08-30T06:00:04.882301+00:00",
    }
    item.update(overrides)
    return item


# Guarantee: `relevance` deserializes from a DynamoDB `Decimal` to a plain int.
def test_card_out_coerces_integer_decimal_relevance_to_int():
    card = CardOut.model_validate(_raw_item(relevance=Decimal("7")))
    assert card.relevance == 7
    assert isinstance(card.relevance, int)
    assert not isinstance(card.relevance, Decimal)


# Guarantee (constraint): pydantic 2.13.4 rejects a non-integer Decimal for
# `relevance` rather than silently truncating it.
def test_card_out_rejects_non_integer_decimal_relevance():
    with pytest.raises(pydantic.ValidationError):
        CardOut.model_validate(_raw_item(relevance=Decimal("7.5")))


# Mapping table: "missing -> []" for tags/takeaways.
def test_card_out_defaults_missing_tags_to_empty_list():
    item = _raw_item()
    del item["tags"]
    card = CardOut.model_validate(item)
    assert card.tags == []


def test_card_out_defaults_missing_takeaways_to_empty_list():
    item = _raw_item()
    del item["takeaways"]
    card = CardOut.model_validate(item)
    assert card.takeaways == []


# `type` is a permissive str, not an Enum — an LLM-invented value must
# validate, not raise (contract.md: "a card whose type the model invented
# must render, not 500").
@pytest.mark.parametrize("type_value", ["news", "paper", "release", "project", "concept", "some-new-type-the-model-invented"])
def test_card_out_accepts_any_string_type_value(type_value):
    card = CardOut.model_validate(_raw_item(type=type_value))
    assert card.type == type_value


# `relevance` is an unbounded int, not conint(ge=1, le=10) — a stray
# out-of-range stored value must still render.
def test_card_out_accepts_relevance_outside_the_nominal_one_to_ten_range():
    card = CardOut.model_validate(_raw_item(relevance=Decimal("42")))
    assert card.relevance == 42


# `model_config = ConfigDict(extra="ignore")`: internal index keys and the
# reserved embedding vector must never surface on the model even if a caller
# accidentally hands them in (defense in depth alongside ProjectionExpression).
def test_card_out_ignores_internal_index_keys_and_embedding_if_present():
    item = _raw_item(gsi_pk="CARD", gsi_sk="008#2026-08-29", embedding=[Decimal("0.1")])
    card = CardOut.model_validate(item)
    dumped = card.model_dump()
    assert "gsi_pk" not in dumped
    assert "gsi_sk" not in dumped
    assert "embedding" not in dumped


# FeedResponse: `next_cursor` is None — and only None — at the end of the feed.
def test_feed_response_next_cursor_defaults_to_none():
    response = FeedResponse(cards=[])
    assert response.next_cursor is None


def test_feed_response_round_trips_through_json():
    original = FeedResponse(cards=[CardOut.model_validate(_raw_item())], next_cursor="abc123")
    restored = FeedResponse.model_validate_json(original.model_dump_json())
    assert restored == original


# `json_schema()` is what `docs/api/feed-api.v1.schema.json` is generated
# from (Guarantee 13) — assert its own shape directly, independent of the
# committed artifact (that drift check lives in test_feed_api_contract.py).
def test_json_schema_describes_feed_response_with_card_out_definitions():
    schema = json_schema()
    assert isinstance(schema, dict)
    assert "cards" in schema.get("properties", {})
    assert "next_cursor" in schema.get("properties", {})
    # CardOut is referenced as a $defs entry (list-of-CardOut items), not
    # inlined twice — the "$defs-linked" shape the docstring promises.
    assert "CardOut" in schema.get("$defs", {})

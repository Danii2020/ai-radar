"""Tests for `src/api/handler.py` — the Lambda entrypoint.

Spec: specs/feed-api/contract.md "`src/api/handler.py` — CREATE (the Lambda
entrypoint)", "Parameter parsing rules", "Data Models" 200/400 bodies; Behavior
Guarantees 3, 4, 9, 12; Error Handling Contract; specs/feed-api/audit.md T3,
T9, T10, T12, T13, T14, T22.

Events are hand-built payload-format-2.0 dicts matching the pinned surface
(`event["queryStringParameters"]`, `event["requestContext"]["http"]["method"]`,
`event["rawPath"]`) — no real API Gateway involved.

Seam assumption (documented, not guessed at random): per this repo's
established convention of monkeypatching the name a consumer module imports
(`tests/conftest.py`'s `nodes_module.summarize_with_usage`, `test_runtime_app.
py`'s `runtime_app._build_store`), these tests monkeypatch `api.handler.
card_table` — i.e. `src/api/handler.py` is expected to do
`from api.dynamo import card_table` and call it with no arguments, exactly as
contract.md's `card_table(client=None)` signature implies for the deployed
Lambda. This lets every test inject the `moto`-backed table without any real
AWS call, without needing a table-injection parameter on `handler()` itself
(which the contract does not provide — `handler(event, context)` is the whole
signature).

Payload-2.0 duplicate-query-param coverage (auditor finding F6, 2026-09-02):
API Gateway HTTP API comma-joins duplicate query string keys before the
handler ever sees them (contract.md's pinned surface — there is no
`multiValueQueryStringParameters` in payload format 2.0), so
`test_handler_treats_comma_joined_duplicate_tag_param_as_a_literal_string`
builds the event with the already-joined `"a,b"` string directly rather than
simulating API Gateway's join step itself.
"""
from __future__ import annotations

import json
import logging

import pytest

from contracts.card import FeedResponse

import api.handler as handler_module
from api.handler import handler


class _PoisonedTable:
    """A table double whose `.query()` raises if invoked — proves a rejected
    request (bad limit, bad cursor) never reaches DynamoDB (Error Handling
    Contract: "no AWS call")."""

    def query(self, **kwargs):
        raise AssertionError("must not call DynamoDB for a request rejected before validation passes")


class _RaisingTable:
    """A table double whose `.query()` always raises, simulating throttling /
    ResourceNotFoundException / a credential error (Error Handling Contract
    row: DynamoDB failure -> 500 `internal_error`, exception text never
    echoed)."""

    def query(self, **kwargs):
        raise RuntimeError("simulated DynamoDB failure: secret-internal-detail-12345")


def _event(query: dict | None = None, path: str = "/v1/cards", method: str = "GET") -> dict:
    event = {"rawPath": path, "requestContext": {"http": {"method": method}}}
    if query is not None:
        event["queryStringParameters"] = query
    return event


def _use_table(monkeypatch, table) -> None:
    monkeypatch.setattr(handler_module, "card_table", lambda: table)


def _body(response: dict) -> dict:
    return json.loads(response["body"])


# T14: 200 body parses with FeedResponse.model_validate_json and matches the
# seeded order end-to-end through the handler.
def test_handler_returns_200_with_feed_response_matching_seeded_order(dynamo_table, put_card_item, monkeypatch):
    put_card_item("low", relevance=2, published="2026-07-01")
    put_card_item("high", relevance=9, published="2026-07-15")
    _use_table(monkeypatch, dynamo_table)

    response = handler(_event(), None)

    assert response["statusCode"] == 200
    feed = FeedResponse.model_validate_json(response["body"])
    assert [c.card_id for c in feed.cards] == ["high", "low"]


# T3 (Guarantee 3): limit absent -> DEFAULT_PAGE_SIZE (20).
def test_handler_uses_default_page_size_when_limit_absent(dynamo_table, seed_cards, monkeypatch):
    seed_cards(count=25)
    _use_table(monkeypatch, dynamo_table)

    response = handler(_event(), None)

    feed = FeedResponse.model_validate_json(response["body"])
    assert len(feed.cards) == 20


def test_handler_applies_a_valid_limit(dynamo_table, seed_cards, monkeypatch):
    seed_cards(count=25)
    _use_table(monkeypatch, dynamo_table)

    response = handler(_event(query={"limit": "3"}), None)

    feed = FeedResponse.model_validate_json(response["body"])
    assert len(feed.cards) == 3


# F6 (auditor finding): limit=1 and limit=100 (MAX_PAGE_SIZE) are the
# documented boundary values and must both be ACCEPTED (200), not rejected —
# an off-by-one in the handler's `[1, MAX_PAGE_SIZE]` bound check would flip
# one of these to a 400 while leaving the "0"/"101" out-of-range cases
# (already covered below) unaffected.
@pytest.mark.parametrize("boundary_limit", [1, 100])
def test_handler_accepts_the_documented_limit_boundaries(
    dynamo_table, seed_cards, monkeypatch, boundary_limit
):
    seed_cards(count=5)
    _use_table(monkeypatch, dynamo_table)

    response = handler(_event(query={"limit": str(boundary_limit)}), None)

    assert response["statusCode"] == 200
    feed = FeedResponse.model_validate_json(response["body"])
    assert len(feed.cards) <= boundary_limit


# T9: 400 invalid_limit for every documented bad value; no AWS call is made.
# "5,6" is F6's comma-joined-duplicate-param case (?limit=5&limit=6 arrives as
# the literal string "5,6"; int("5,6") raises, so it must 400 via the same
# not-an-integer path as "abc" — no separate handling required or tested).
@pytest.mark.parametrize("bad_limit", ["0", "101", "abc", "-1", "1.5", "", "5,6"])
def test_handler_rejects_invalid_limit_without_touching_dynamodb(bad_limit, monkeypatch):
    _use_table(monkeypatch, _PoisonedTable())

    response = handler(_event(query={"limit": bad_limit}), None)

    assert response["statusCode"] == 400
    assert _body(response)["error"] == "invalid_limit"


# T10: 400 invalid_cursor; no AWS call is made — a malformed/tampered cursor
# is never silently ignored (would duplicate cards) and never reaches Dynamo.
def test_handler_rejects_invalid_cursor_without_touching_dynamodb(monkeypatch):
    _use_table(monkeypatch, _PoisonedTable())

    response = handler(_event(query={"cursor": "not-a-valid-cursor!!"}), None)

    assert response["statusCode"] == 400
    assert _body(response)["error"] == "invalid_cursor"


def test_handler_accepts_a_cursor_produced_by_encode_cursor(dynamo_table, seed_cards, monkeypatch):
    seed_cards(count=5)
    _use_table(monkeypatch, dynamo_table)
    first = handler(_event(query={"limit": "2"}), None)
    first_body = _body(first)
    assert first_body["next_cursor"] is not None

    second = handler(_event(query={"limit": "2", "cursor": first_body["next_cursor"]}), None)

    assert second["statusCode"] == 200
    second_feed = FeedResponse.model_validate_json(second["body"])
    first_ids = {c["card_id"] for c in first_body["cards"]}
    second_ids = {c.card_id for c in second_feed.cards}
    assert first_ids.isdisjoint(second_ids)


# T13: empty/whitespace tag is treated as absent; a no-match tag yields 200
# with cards: [].
def test_handler_treats_blank_tag_as_absent(dynamo_table, put_card_item, monkeypatch):
    put_card_item("a", relevance=5, published="2026-08-01", tags=[])
    _use_table(monkeypatch, dynamo_table)

    response = handler(_event(query={"tag": "   "}), None)

    feed = FeedResponse.model_validate_json(response["body"])
    assert [c.card_id for c in feed.cards] == ["a"]


def test_handler_returns_empty_cards_for_a_tag_matching_nothing(dynamo_table, put_card_item, monkeypatch):
    put_card_item("a", relevance=5, published="2026-08-01", tags=["python"])
    _use_table(monkeypatch, dynamo_table)

    response = handler(_event(query={"tag": "no-such-tag"}), None)

    assert response["statusCode"] == 200
    feed = FeedResponse.model_validate_json(response["body"])
    assert feed.cards == []


# F6 (auditor finding): API Gateway HTTP API 2.0 comma-joins duplicate query
# params before the handler sees them, so `?tag=a&tag=b` arrives as the
# single literal string "a,b" — event built with that already-joined shape
# directly, not by simulating the join. Tag matching is exact/case-sensitive
# `contains`, so this matches nothing that isn't literally tagged "a,b": a
# 200 with an empty page, not an error.
def test_handler_treats_comma_joined_duplicate_tag_param_as_a_literal_string(
    dynamo_table, put_card_item, monkeypatch
):
    put_card_item("has-a", relevance=5, published="2026-08-01", tags=["a"])
    put_card_item("has-b", relevance=4, published="2026-08-02", tags=["b"])
    _use_table(monkeypatch, dynamo_table)

    response = handler(_event(query={"tag": "a,b"}), None)

    assert response["statusCode"] == 200
    feed = FeedResponse.model_validate_json(response["body"])
    assert feed.cards == []


# T12 (Guarantee 12): the handler emits no CORS headers, and the content-type
# header is set explicitly.
def test_handler_response_has_content_type_and_no_cors_headers(dynamo_table, monkeypatch):
    _use_table(monkeypatch, dynamo_table)

    response = handler(_event(), None)

    headers = {k.lower(): v for k, v in response["headers"].items()}
    assert headers.get("content-type") == "application/json"
    assert not any(k.startswith("access-control-") for k in headers)


# T22: an unexpected DynamoDB exception produces a 500 whose body does NOT
# contain the underlying exception text, and the handler does not raise.
def test_handler_returns_500_internal_error_without_leaking_exception_text(monkeypatch):
    _use_table(monkeypatch, _RaisingTable())

    response = handler(_event(), None)

    assert response["statusCode"] == 500
    body = _body(response)
    assert body["error"] == "internal_error"
    assert "secret-internal-detail-12345" not in json.dumps(body)


# Structured logging: one feed_api_request record per request.
def test_handler_emits_a_structured_feed_api_request_log_record(dynamo_table, caplog, monkeypatch):
    _use_table(monkeypatch, dynamo_table)
    caplog.set_level(logging.INFO)

    handler(_event(query={"limit": "5"}), None)

    matches = []
    for record in caplog.records:
        try:
            payload = json.loads(record.getMessage())
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(payload, dict) and payload.get("event") == "feed_api_request":
            matches.append(payload)
    assert len(matches) == 1

"""Tests for `src/api/feed.py` — `query_feed`/`FeedPage`.

Spec: specs/feed-api/contract.md "`src/api/feed.py` — CREATE (query +
projection, no HTTP)"; Behavior Guarantees 1, 2, 3, 4, 6, 9; specs/feed-api/
audit.md T1, T2, T3, T4, T6, T7, T11, T23.

All DynamoDB access is `moto`-mocked via `tests/conftest.py`'s
`dynamo_resource`/`dynamo_table`/`seed_cards`/`put_card_item` fixtures (the
same `feed-by-score` GSI schema `dynamodb-card-store` locked) — zero real-AWS
calls. Items are written directly into the table (never through
`DynamoCardStore`, which Plane B must not import).

Guarantee 6 (the round trip) is the load-bearing test in this file: it walks
`next_cursor` — through the real `encode_cursor`/`decode_cursor` pair, not
just raw `LastEvaluatedKey` dicts — until exhausted, both unfiltered and
tag-filtered, and asserts the concatenation exactly matches one unpaginated
query.

RED phase: `src/api/feed.py` does not exist yet. Every test in this file is
expected to fail at collection with `ModuleNotFoundError: No module named
'api.feed'` (or similar) until the implementation lands.
"""
from __future__ import annotations

from decimal import Decimal

from api.cursor import decode_cursor, encode_cursor
from api.feed import query_feed


class _CountingQueryTable:
    """Wraps a real (moto-backed) Table; counts `.query()` invocations so a
    test can prove `query_feed` issues exactly one Query per call — no
    draining loop, no follow-on read (contract.md: "Exactly one query per
    call")."""

    def __init__(self, real_table):
        self._real_table = real_table
        self.query_call_count = 0

    def query(self, **kwargs):
        self.query_call_count += 1
        return self._real_table.query(**kwargs)

    def __getattr__(self, name):
        return getattr(self._real_table, name)


# T1 (Guarantee 1): ordering is relevance desc, then published desc.
def test_query_feed_orders_by_relevance_desc_then_published_desc(dynamo_table, put_card_item):
    put_card_item("low", relevance=2, published="2026-07-01")
    put_card_item("high-old", relevance=9, published="2026-07-01")
    put_card_item("high-new", relevance=9, published="2026-07-15")

    page = query_feed(dynamo_table, limit=20)

    assert [c.card_id for c in page.cards] == ["high-new", "high-old", "low"]
    assert page.last_evaluated_key is None


# T1: exactly one Query per call — no draining loop.
def test_query_feed_issues_exactly_one_query_call(dynamo_table, seed_cards):
    seed_cards(count=10, tag="target", tag_every=3)
    counting_table = _CountingQueryTable(dynamo_table)

    query_feed(counting_table, tag="target", limit=3)

    assert counting_table.query_call_count == 1


# T2 (Guarantee 2): every returned card contains the requested tag; a card
# without it is absent from the results.
def test_tag_filter_returns_only_cards_containing_the_tag(dynamo_table, put_card_item):
    put_card_item("has-tag-1", relevance=8, published="2026-08-10", tags=["llm", "agents"])
    put_card_item("has-tag-2", relevance=7, published="2026-08-09", tags=["llm"])
    put_card_item("no-tag", relevance=9, published="2026-08-11", tags=["other"])

    page = query_feed(dynamo_table, tag="llm", limit=20)

    returned_ids = {c.card_id for c in page.cards}
    assert returned_ids == {"has-tag-1", "has-tag-2"}
    assert all("llm" in c.tags for c in page.cards)


# Contract: an empty/whitespace tag at this layer is treated the same as no
# filter at all (the handler is responsible for turning "" into None before
# calling query_feed, but query_feed's own guard is what actually prevents a
# stray empty FilterExpression).
def test_empty_string_tag_applies_no_filter(dynamo_table, put_card_item):
    put_card_item("a", relevance=5, published="2026-08-10", tags=["x"])
    put_card_item("b", relevance=4, published="2026-08-09", tags=[])

    page = query_feed(dynamo_table, tag="", limit=20)

    assert {c.card_id for c in page.cards} == {"a", "b"}


# T3 (Guarantee 3): len(cards) <= limit; a limit smaller than the dataset
# leaves a LastEvaluatedKey.
def test_limit_bounds_the_returned_page_size(dynamo_table, seed_cards):
    seed_cards(count=25)

    page = query_feed(dynamo_table, limit=5)

    assert len(page.cards) == 5
    assert page.last_evaluated_key is not None


# T3: the function's own default limit is 20 (DEFAULT_PAGE_SIZE), enforced
# even when the caller passes no explicit limit.
def test_default_limit_is_twenty_when_not_specified(dynamo_table, seed_cards):
    seed_cards(count=25)

    page = query_feed(dynamo_table)

    assert len(page.cards) == 20


# T4 (Guarantee 4): a filtered page can be shorter than `limit` (even empty)
# while `last_evaluated_key` is still non-null — DynamoDB applies the filter
# after Limit, so this is legal, not an error.
def test_filtered_page_can_be_short_with_a_live_cursor(dynamo_table, seed_cards):
    # Only card00 (i=0) carries "target"; the rest carry "other".
    seed_cards(count=10, tag="target", tag_every=10)

    page = query_feed(dynamo_table, tag="target", limit=3)

    assert len(page.cards) <= 3
    assert page.last_evaluated_key is not None


def test_filtered_page_can_be_empty_with_a_live_cursor(dynamo_table, seed_cards):
    # Only card00 carries "target". Resume just past it, so the next window
    # (card01, card02) matches nothing, but more unread items remain.
    seed_cards(count=10, tag="target", tag_every=10)
    first = query_feed(dynamo_table, limit=1)
    assert first.last_evaluated_key is not None

    second = query_feed(dynamo_table, tag="target", limit=2, exclusive_start_key=first.last_evaluated_key)

    assert second.cards == []
    assert second.last_evaluated_key is not None


# T6 (Guarantee 5 mechanics): next_cursor/LastEvaluatedKey is None iff this
# is genuinely the last page.
def test_last_evaluated_key_is_none_only_on_the_true_last_page(dynamo_table, seed_cards):
    seed_cards(count=3)

    single_query = query_feed(dynamo_table, limit=20)
    assert single_query.last_evaluated_key is None

    page_one = query_feed(dynamo_table, limit=2)
    assert page_one.last_evaluated_key is not None

    page_two = query_feed(dynamo_table, limit=2, exclusive_start_key=page_one.last_evaluated_key)
    assert len(page_two.cards) == 1
    assert page_two.last_evaluated_key is None


def _walk_all_pages_via_cursor(table, *, tag=None, limit):
    """Walks `next_cursor` through the real encode/decode pair — exactly what
    the HTTP handler does — until exhausted; returns the concatenated cards."""
    all_cards = []
    exclusive_start_key = None
    pages_walked = 0
    while True:
        page = query_feed(table, tag=tag, limit=limit, exclusive_start_key=exclusive_start_key)
        all_cards.extend(page.cards)
        pages_walked += 1
        assert pages_walked < 1000, "runaway pagination loop — cursor never exhausted"
        if page.last_evaluated_key is None:
            break
        # Round-trip through the opaque token, not the raw dict, so this
        # test proves the whole client-facing pagination contract.
        token = encode_cursor(page.last_evaluated_key)
        exclusive_start_key = decode_cursor(token)
    return all_cards


# T7 (Guarantee 6 — the load-bearing one): paginated concatenation ==
# unpaginated single query, both unfiltered and tag-filtered. No duplicate
# card_id, no omitted card_id.
def test_cursor_round_trip_reproduces_unpaginated_sequence_unfiltered(dynamo_table, seed_cards):
    seed_cards(count=13)

    unpaginated = query_feed(dynamo_table, limit=100)
    paginated = _walk_all_pages_via_cursor(dynamo_table, limit=4)

    assert [c.card_id for c in paginated] == [c.card_id for c in unpaginated.cards]
    assert len(paginated) == len(set(c.card_id for c in paginated))  # no duplicates


def test_cursor_round_trip_reproduces_unpaginated_sequence_filtered(dynamo_table, seed_cards):
    # Every 3rd card (0, 3, 6, 9, 12) carries "python" — 5 of 13 match.
    seed_cards(count=13, tag="python", tag_every=3)

    unpaginated = query_feed(dynamo_table, tag="python", limit=100)
    paginated = _walk_all_pages_via_cursor(dynamo_table, tag="python", limit=4)

    assert [c.card_id for c in paginated] == [c.card_id for c in unpaginated.cards]
    assert len(unpaginated.cards) == 5
    assert len(paginated) == len(set(c.card_id for c in paginated))  # no duplicates


# T11 (Guarantee 9): a stored item that fails CardOut validation is logged,
# counted, and omitted — the rest of the page still returns.
def test_malformed_stored_item_is_skipped_and_counted(dynamo_table, put_card_item):
    put_card_item("good1", relevance=5, published="2026-08-10")
    put_card_item("good2", relevance=5, published="2026-08-09")
    # Missing `title` (a required CardOut field) entirely.
    dynamo_table.put_item(Item={
        "card_id": "malformed1",
        "url": "https://example.com/malformed1",
        "source": "Test Source",
        "summary": "A summary.",
        "tags": [],
        "type": "news",
        "relevance": Decimal("5"),
        "published": "2026-08-08",
        "takeaways": [],
        "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
        "gsi_pk": "CARD",
        "gsi_sk": "005#2026-08-08",
    })

    page = query_feed(dynamo_table, limit=20)

    assert page.skipped == 1
    assert {c.card_id for c in page.cards} == {"good1", "good2"}


# T23 (Mapping table): the returned card never carries the internal index
# keys or the reserved embedding vector, even when one is actually stored;
# `relevance` arrives as a plain int, not a Decimal.
def test_returned_card_never_carries_index_keys_or_embedding(dynamo_table, put_card_item):
    put_card_item("with-embedding", relevance=6, published="2026-08-05")
    dynamo_table.update_item(
        Key={"card_id": "with-embedding"},
        UpdateExpression="SET embedding = :emb",
        ExpressionAttributeValues={":emb": [Decimal("0.1"), Decimal("0.2")]},
    )

    page = query_feed(dynamo_table, limit=20)

    card = next(c for c in page.cards if c.card_id == "with-embedding")
    dumped = card.model_dump()
    assert "embedding" not in dumped
    assert "gsi_pk" not in dumped
    assert "gsi_sk" not in dumped
    assert isinstance(card.relevance, int)

"""Shared pytest setup + fixtures for the curation-graph spec tests.

Spec: specs/curation-graph/{contract.md,intent.md,audit.md}

- Adds `src/` to `sys.path` (mirrors the pattern in `run_curation.py`) so both
  `shared.*` (existing) and `curation.*` (not yet implemented — this is the
  RED phase) are importable from `tests/`.
- Provides small factories for `RawItem` / summarize()-shaped dicts, and a
  deterministic, network-free `summarize()` stub factory, reused by
  `tests/test_local_store.py` and `tests/test_graph.py`.

No test in this suite makes a live Bedrock/AWS/network call: `shared.bedrock`'s
summarize seam is always monkeypatched at the point tests import it
(`curation.nodes.summarize_with_usage`, per specs/run-observability), never
invoked for real.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from shared.feeds import RawItem


@pytest.fixture
def make_raw_item():
    """Factory for a `RawItem` with sane defaults; override any field via kwargs."""

    def _make(
        source: str = "Test Feed",
        title: str = "Test Title",
        url: str = "https://example.com/article",
        published: str = "2026-07-01",
        snippet: str = "A snippet.",
    ) -> RawItem:
        return RawItem(
            source=source, title=title, url=url, published=published, snippet=snippet
        )

    return _make


@pytest.fixture
def make_model_out():
    """Factory for a fake `summarize()` return dict (the `Card.from_model` input)."""

    def _make(
        title: str = "Model Title",
        summary: str = "A concise summary.",
        tags: list[str] | None = None,
        type_: str = "news",
        relevance: int = 5,
        takeaways: list[str] | None = None,
    ) -> dict:
        return {
            "title": title,
            "summary": summary,
            "tags": tags if tags is not None else ["llm"],
            "type": type_,
            "relevance": relevance,
            "takeaways": takeaways if takeaways is not None else [],
        }

    return _make


@pytest.fixture
def summarize_stub_factory(make_model_out):
    """Factory to build deterministic, network-free `summarize_with_usage(item)`
    stubs (Spec 06: run-observability repoints the patch target from
    `nodes.summarize` to `nodes.summarize_with_usage` — see
    specs/run-observability/contract.md §1/§6).

    `relevance_by_url` controls the relevance score returned per item (default 5).
    `raise_for_urls` makes the stub raise for those URLs, simulating a per-item
    Bedrock/summarize failure (contract Error Handling Contract row 1).
    `tokens_by_url` controls the `(input_tokens, output_tokens)` pair returned
    per item (default `(0, 0)`), letting a test assert token accumulation
    without a real Bedrock call.

    The returned callable's shape is `(item) -> tuple[dict, TokenUsage]`,
    mirroring `shared.bedrock.summarize_with_usage`. `TokenUsage` is imported
    lazily (inside `_build`, not at module scope) so a suite that never calls
    this factory does not fail collection while `shared.bedrock.TokenUsage`
    does not exist yet (RED phase).
    """

    def _build(
        relevance_by_url: dict[str, int] | None = None,
        raise_for_urls: set[str] | None = None,
        tokens_by_url: dict[str, tuple[int, int]] | None = None,
    ):
        from shared.bedrock import TokenUsage

        relevance_by_url = relevance_by_url or {}
        raise_for_urls = raise_for_urls or set()
        tokens_by_url = tokens_by_url or {}

        def _summarize_with_usage(item: RawItem) -> tuple[dict, "TokenUsage"]:
            if item.url in raise_for_urls:
                raise RuntimeError(f"stub summarize failure for {item.url}")
            model_out = make_model_out(
                title=item.title,
                summary=f"Summary of {item.title}",
                relevance=relevance_by_url.get(item.url, 5),
            )
            input_tokens, output_tokens = tokens_by_url.get(item.url, (0, 0))
            usage = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)
            return model_out, usage

        return _summarize_with_usage

    return _build


# --- Spec 03 (dynamodb-card-store) additions ---------------------------------
# Additive only: the fixtures above (Specs 01/02) are untouched. These fixtures
# stand up a `moto`-backed DynamoDB table matching the LOCKED key schema in
# specs/dynamodb-card-store/contract.md so `tests/test_dynamo_store.py` makes
# zero real-AWS calls. `moto`/`boto3` are imported at module scope here because
# both are real installed dependencies (moto: dev group) - this does not risk
# breaking collection of the Spec 01/02 suite the way importing the
# not-yet-implemented `curation.dynamo` module would.

from decimal import Decimal

import boto3
from moto import mock_aws

# Fixed per contract.md "Decisions" (author's choice, env-overridable in
# production via curation.config.CARD_TABLE_NAME) - hardcoded here rather than
# imported so this fixture never depends on the Spec 03 config block existing.
CARD_TABLE_NAME = "ai-radar-cards"


def _create_card_table(resource):
    """Create the `ai-radar-cards` table with the exact LOCKED key schema:
    PK `card_id` (S); GSI `feed-by-score` on `gsi_pk`(S)/`gsi_sk`(S), projection
    ALL; on-demand (PAY_PER_REQUEST) billing."""
    return resource.create_table(
        TableName=CARD_TABLE_NAME,
        KeySchema=[{"AttributeName": "card_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "card_id", "AttributeType": "S"},
            {"AttributeName": "gsi_pk", "AttributeType": "S"},
            {"AttributeName": "gsi_sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
        GlobalSecondaryIndexes=[
            {
                "IndexName": "feed-by-score",
                "KeySchema": [
                    {"AttributeName": "gsi_pk", "KeyType": "HASH"},
                    {"AttributeName": "gsi_sk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )


@pytest.fixture
def dynamo_resource():
    """`moto`-backed DynamoDB **resource** (ServiceResource) with the
    `ai-radar-cards` table pre-created per contract.md's locked key schema.

    Injected as `DynamoCardStore(client=...)` per contract.md's constructor
    (`client` is an optional boto3 DynamoDB ServiceResource). Zero real-AWS
    calls: `moto.mock_aws` intercepts boto3 for the fixture's lifetime.
    """
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        _create_card_table(resource)
        yield resource


@pytest.fixture
def dynamo_table(dynamo_resource):
    """The moto-backed `ai-radar-cards` `Table` resource directly, for
    out-of-band assertions/pre-seeding the `DynamoCardStore` under test doesn't
    expose (e.g. reading raw items, seeding a pre-existing `embedding`,
    querying the `feed-by-score` GSI)."""
    return dynamo_resource.Table(CARD_TABLE_NAME)


# --- Spec 01 (feed-api) additions ---------------------------------------------
# Additive only: every fixture above (Specs 01-06) is untouched. `seed_cards`
# writes items directly (bypassing DynamoCardStore, which Plane B must not
# import) into the same `dynamo_table` fixture's `feed-by-score` GSI, for
# tests/test_feed_query.py's ordering/pagination/round-trip tests.


def _feed_card_item(card_id: str, *, relevance: int = 5, published: str = "2026-08-01", tags=None, **overrides) -> dict:
    """One DynamoDB item shaped exactly like `DynamoCardStore.upsert` writes
    (specs/dynamodb-card-store/contract.md "Item schema"), including the
    `gsi_pk`/`gsi_sk` a real `feed-by-score` query keys off. `overrides` can
    inject an extra/malformed shape (e.g. a missing required field, or a
    pre-seeded `embedding`) for resilience/projection tests."""
    item = {
        "card_id": card_id,
        "title": f"Title {card_id}",
        "url": f"https://example.com/{card_id}",
        "source": "Test Source",
        "summary": f"Summary for {card_id}",
        "tags": tags if tags is not None else [],
        "type": "news",
        "relevance": Decimal(str(relevance)),
        "published": published,
        "takeaways": [],
        "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
        "gsi_pk": "CARD",
        "gsi_sk": f"{relevance:03d}#{published}",
    }
    item.update(overrides)
    return item


@pytest.fixture
def seed_cards(dynamo_table):
    """Factory: seed `count` deterministic cards into the `feed-by-score` GSI
    and return them as plain dicts **in the exact descending-`gsi_sk` order**
    `ScanIndexForward=False` is expected to return them (item 0 is the
    highest-scored/most-recent) — so a test can assert directly against
    `[c["card_id"] for c in seeded]`.

    All seeded cards share `relevance`; `published` dates count down from
    `2026-08-30`, which sorts lexically (== chronologically) descending, so
    ordering is driven by a single, easy-to-reason-about axis. When `tag` is
    given, every `tag_every`-th card (0-indexed) carries it (plus a filler
    tag on the rest), giving a tag filter a known, non-trivial subset —
    `[c for c in seeded if tag in c["tags"]]` is the filtered-order oracle.
    """

    def _seed(count: int = 6, *, tag: str | None = None, tag_every: int = 2, relevance: int = 5):
        seeded = []
        for i in range(count):
            published = f"2026-08-{30 - i:02d}"
            card_id = f"card{i:02d}"
            if tag is not None:
                item_tags = [tag] if i % tag_every == 0 else ["other"]
            else:
                item_tags = []
            item = _feed_card_item(card_id, relevance=relevance, published=published, tags=item_tags)
            dynamo_table.put_item(Item=item)
            seeded.append(item)
        return seeded

    return _seed


@pytest.fixture
def put_card_item(dynamo_table):
    """Factory: put one arbitrary DynamoDB item (via `_feed_card_item`'s
    defaults + `overrides`) directly into the seeded table, for tests that
    need explicit control over a single card's shape (e.g. a malformed item
    missing a required `CardOut` field, or a specific relevance/date pair)
    rather than `seed_cards`'s deterministic bulk sequence."""

    def _put(card_id: str, **overrides):
        item = _feed_card_item(card_id, **overrides)
        dynamo_table.put_item(Item=item)
        return item

    return _put

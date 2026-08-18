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

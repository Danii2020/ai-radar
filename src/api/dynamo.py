"""The only `boto3` site in `src/api/` (Phase 2, spec `feed-api`).

Mirrors `curation.dynamo`'s lazy-singleton + injectable-client pattern so the
compiled read path stays testable with `moto` and portable — `boto3` never
leaks into `src/api/feed.py` or `src/api/handler.py`.
"""
from __future__ import annotations

import boto3
from boto3.dynamodb.conditions import Attr, Key  # re-exported for api.feed

from api.config import CARD_TABLE_NAME

# AST plane-separation test (tests/test_feed_api_contract.py) confines every
# `boto3` import under src/api/ to this module; `api.feed` imports `Attr`/`Key`
# from here rather than from `boto3.dynamodb.conditions` directly.
__all__ = ["Attr", "Key", "card_table"]

_resource = None  # lazy singleton boto3 DynamoDB ServiceResource


def _dynamo_resource():
    global _resource
    if _resource is None:
        _resource = boto3.resource("dynamodb")
    return _resource


def card_table(client=None):
    """The `ai-radar-cards` Table resource. `client` is an optional boto3
    DynamoDB **ServiceResource** (tests inject a `moto`-backed one); when None a
    lazily-created singleton `boto3.resource("dynamodb")` is used — region comes
    from the Lambda runtime env via boto3's default chain (AD-3). Mirrors
    `curation.dynamo`'s lazy-singleton + injectable-client pattern."""
    resource = client if client is not None else _dynamo_resource()
    return resource.Table(CARD_TABLE_NAME)

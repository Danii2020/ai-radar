"""The feed query (Phase 2, spec `feed-api`) — query + projection, no HTTP.

`boto3` never appears here — `table` is handed in already resolved (by
`api.dynamo.card_table` in production, by a `moto`-backed Table in tests).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import ValidationError

from api.config import DEFAULT_PAGE_SIZE, FEED_GSI_NAME, FEED_GSI_PARTITION
from api.dynamo import Attr, Key
from contracts.card import CardOut

logger = logging.getLogger(__name__)

# Excludes the reserved `embedding` attribute (Phase 3) so a populated vector
# never costs the feed a byte of transfer. `url`/`type` are DynamoDB reserved
# words; `title`/`source` are aliased defensively for symmetry.
_PROJECTION_EXPRESSION = (
    "card_id, #t, #u, #src, summary, tags, #ty, relevance, "
    "published, takeaways, created_at, updated_at"
)
_EXPRESSION_ATTRIBUTE_NAMES = {"#t": "title", "#u": "url", "#src": "source", "#ty": "type"}


@dataclass(frozen=True)
class FeedPage:
    """Result of one DynamoDB query: validated cards + the raw
    LastEvaluatedKey (None on the last page) + how many stored items failed
    CardOut validation and were skipped."""

    cards: list[CardOut]
    last_evaluated_key: dict | None
    skipped: int


def query_feed(
    table,
    *,
    tag: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    exclusive_start_key: dict | None = None,
) -> FeedPage:
    """ONE `Query` against the `feed-by-score` GSI —
    `KeyConditionExpression=Key("gsi_pk").eq(FEED_GSI_PARTITION)`,
    `ScanIndexForward=False`, `Limit=limit`, the pinned `ProjectionExpression`,
    plus `FilterExpression=Attr("tags").contains(tag)` when `tag` is a
    non-empty string and `ExclusiveStartKey` when a cursor was supplied.

    Exactly one query per call: no draining loop, no follow-on read. A filtered
    page may therefore be short or empty while `last_evaluated_key` is not None
    (DynamoDB applies the filter after `Limit`) — that is expected, contractual
    behavior, not an error.

    Per-item resilience: an item that fails `CardOut.model_validate` is logged,
    counted in `skipped`, and omitted — one malformed row never fails the page
    (repo house rule; mirrors `DynamoCardStore.upsert`'s per-card try/except).
    """
    kwargs = {
        "IndexName": FEED_GSI_NAME,
        "KeyConditionExpression": Key("gsi_pk").eq(FEED_GSI_PARTITION),
        "ProjectionExpression": _PROJECTION_EXPRESSION,
        "ExpressionAttributeNames": dict(_EXPRESSION_ATTRIBUTE_NAMES),
        "ScanIndexForward": False,
        "Limit": limit,
    }
    if tag:
        kwargs["FilterExpression"] = Attr("tags").contains(tag)
    if exclusive_start_key is not None:
        kwargs["ExclusiveStartKey"] = exclusive_start_key

    resp = table.query(**kwargs)

    cards: list[CardOut] = []
    skipped = 0
    for item in resp.get("Items", []):
        try:
            cards.append(CardOut.model_validate(item))
        except ValidationError:
            logger.exception("stored item failed CardOut validation, skipping")
            skipped += 1

    return FeedPage(
        cards=cards,
        last_evaluated_key=resp.get("LastEvaluatedKey"),
        skipped=skipped,
    )

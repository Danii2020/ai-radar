"""DynamoDB-backed retriever (Plane B, spec `chat-retrieval`).

Brute-force cosine over the stored vectors: `Query` the `feed-by-score` index
(never `Scan`), dot-product against each card's embedding, keep the top k.
Vectors are normalized (`normalize=True`), so dot product equals cosine.
Revisit past ~2,000 embedded cards or p95 retrieval above ~1 s.
"""
from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from shared.config import EMBED_DIM
from shared.embeddings import embed

from .config import CARD_TABLE_NAME, FEED_GSI_NAME, FEED_GSI_PARTITION

_CARD_FIELDS = (
    "title", "url", "source", "summary", "tags", "type", "relevance",
    "published", "takeaways",
)

_resource = None  # lazy singleton boto3 DynamoDB ServiceResource


def _dynamo_resource():
    global _resource
    if _resource is None:
        _resource = boto3.resource("dynamodb")
    return _resource


def _plain(value):
    """Decimal -> int/float (recursively), so card dicts match `CardIndex`'s."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


class DynamoCardRetriever:
    """Satisfies `shared.chat.Retriever` over the `ai-radar-cards` table."""

    def __init__(
        self,
        table_name: str | None = None,
        resource=None,
        embed_fn: Callable[[str], list[float]] = embed,
    ) -> None:
        resource = resource if resource is not None else _dynamo_resource()
        self._table = resource.Table(table_name if table_name is not None else CARD_TABLE_NAME)
        self._embed = embed_fn

    def _items(self):
        """Every item on the index, paginating on `LastEvaluatedKey`. Names are
        aliased because `url`, `source`, `type` are DynamoDB reserved words."""
        names = {f"#{f}": f for f in (*_CARD_FIELDS, "embedding")}
        kwargs: dict = {
            "IndexName": FEED_GSI_NAME,
            "KeyConditionExpression": Key("gsi_pk").eq(FEED_GSI_PARTITION),
            "ProjectionExpression": ", ".join(names),
            "ExpressionAttributeNames": names,
        }
        while True:
            resp = self._table.query(**kwargs)
            yield from resp.get("Items", [])
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                return
            kwargs["ExclusiveStartKey"] = last_key

    def search(self, query: str, k: int) -> list[tuple[dict, float]]:
        """Top-k `(card_dict, cosine)` pairs, best first; un-embedded and
        wrong-length cards are excluded and no card dict carries its vector."""
        qvec = self._embed(query)
        scored: list[tuple[dict, float]] = []
        for item in self._items():
            raw = item.get("embedding")
            if raw is None or len(raw) != EMBED_DIM:
                continue
            score = sum(float(x) * y for x, y in zip(raw, qvec))
            card = {f: _plain(item[f]) for f in _CARD_FIELDS if f in item}
            scored.append((card, score))
        scored.sort(key=lambda hit: hit[1], reverse=True)
        return scored[:k]

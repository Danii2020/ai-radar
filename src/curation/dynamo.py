"""DynamoDB-backed `CardStore` (Spec 03: dynamodb-card-store).

Implements the Spec 01 `CardStore` Protocol (`dedup_filter` + `upsert`). This
is the only place in `src/curation/` that imports `boto3` — an infra adapter
at the seam, mirroring `spike.bedrock.bedrock_client()`'s lazy-singleton
pattern — so the compiled LangGraph graph stays portable onto AgentCore
Runtime unchanged (nodes/graph/state/interfaces never see boto3).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import boto3

from spike import config as spike_config
from spike.cards import Card
from spike.feeds import RawItem

from . import config

_BATCH_GET_CHUNK = 100
_MAX_UNPROCESSED_RETRIES = 5

_resource = None  # lazy singleton boto3 DynamoDB ServiceResource


def _dynamo_resource():
    global _resource
    if _resource is None:
        _resource = boto3.resource("dynamodb", region_name=spike_config.AWS_REGION)
    return _resource


def _card_id(url: str) -> str:
    """Same rule as `RawItem.url_hash` / `local._url_hash` (Guarantee 2)."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


class DynamoCardStore:
    """CardStore backed by a DynamoDB table (Spec 03).

    Implements the Spec 01 `CardStore` Protocol (dedup_filter + upsert).
    `boto3` is confined to this adapter — nodes/graph/state never import it,
    so the compiled graph stays portable onto AgentCore Runtime unchanged.
    """

    def __init__(self, table_name: str | None = None, client=None) -> None:
        """`table_name` defaults to `config.CARD_TABLE_NAME`. `client` is an
        optional boto3 DynamoDB **ServiceResource** (from
        `boto3.resource("dynamodb")`); when None a lazily-created, region-bound
        singleton resource is used. Tests inject a `moto`-backed resource."""
        self.table_name = table_name if table_name is not None else config.CARD_TABLE_NAME
        resource = client if client is not None else _dynamo_resource()
        self._resource = resource
        self._table = resource.Table(self.table_name)
        self._failures = 0

    def dedup_filter(self, items: list[RawItem]) -> list[RawItem]:
        """Return, order-preserving, only items whose `card_id` (== url_hash) is
        NOT already an item in the table. Existence is checked via BatchGetItem
        (chunks of <=100 keys, projecting `card_id` only). Never raises on an
        empty input (returns []). Idempotent: after upsert() of the resulting
        cards, a repeat call over the same items returns []."""
        if not items:
            return []

        unique_ids: list[str] = []
        seen_ids: set[str] = set()
        for item in items:
            if item.url_hash not in seen_ids:
                seen_ids.add(item.url_hash)
                unique_ids.append(item.url_hash)

        present: set[str] = set()
        for i in range(0, len(unique_ids), _BATCH_GET_CHUNK):
            chunk = unique_ids[i : i + _BATCH_GET_CHUNK]
            keys = [{"card_id": card_id} for card_id in chunk]
            request_items = {
                self.table_name: {"Keys": keys, "ProjectionExpression": "card_id"}
            }
            retries = 0
            while request_items and retries <= _MAX_UNPROCESSED_RETRIES:
                resp = self._resource.batch_get_item(RequestItems=request_items)
                for row in resp.get("Responses", {}).get(self.table_name, []):
                    present.add(row["card_id"])
                request_items = resp.get("UnprocessedKeys") or {}
                retries += 1

        return [item for item in items if item.url_hash not in present]

    def upsert(self, cards: list[Card]) -> None:
        """Insert-or-replace each card via `update_item` (per-card try/except so
        one bad card doesn't sink the batch). SETs every Card content field +
        gsi_pk/gsi_sk + updated_at (=now) + created_at (=if_not_exists(created_at,
        now)). NEVER writes `embedding`, so a Phase-3-populated vector survives a
        re-run. `card_id` derived from `Card.url` via the same sha256(url)[:16]
        rule as RawItem.url_hash. No-op on an empty list."""
        self._failures = 0
        if not cards:
            return

        now = datetime.now(timezone.utc).isoformat()

        for card in cards:
            try:
                card_id = _card_id(card.url)
                gsi_sk = f"{card.relevance:03d}#{card.published}"
                self._table.update_item(
                    Key={"card_id": card_id},
                    UpdateExpression=(
                        "SET #t=:t, #u=:u, #src=:src, summary=:sum, tags=:tags, "
                        "#ty=:ty, relevance=:rel, published=:pub, takeaways=:tk, "
                        "gsi_pk=:gpk, gsi_sk=:gsk, updated_at=:now, "
                        "created_at=if_not_exists(created_at, :now)"
                    ),
                    ExpressionAttributeNames={
                        "#t": "title",
                        "#u": "url",
                        "#src": "source",
                        "#ty": "type",
                    },
                    ExpressionAttributeValues={
                        ":t": card.title,
                        ":u": card.url,
                        ":src": card.source,
                        ":sum": card.summary,
                        ":tags": card.tags,
                        ":ty": card.type,
                        ":rel": card.relevance,
                        ":pub": card.published,
                        ":tk": card.takeaways,
                        ":gpk": config.FEED_GSI_PARTITION,
                        ":gsk": gsi_sk,
                        ":now": now,
                    },
                )
            except Exception as exc:  # per-card failure: skip, count, continue
                print(f"! failed to persist {card.url}: {exc}")
                self._failures += 1
                continue

    def failures(self) -> int:
        """Count of cards that raised during the last upsert() (0 if clean).
        Lets a caller/observer surface a partially-failed persist (Spec 06)."""
        return self._failures

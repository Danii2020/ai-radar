"""Embedding backfill — give every existing card a vector (spec chat-retrieval).

Idempotent by construction: it embeds only cards lacking a usable embedding, so
a second run finds nothing to do. One card's failure is counted, not raised.
"""
from __future__ import annotations

from dataclasses import dataclass

from shared.embeddings import card_text, embed

from .dynamo import DynamoCardStore


@dataclass
class BackfillResult:
    embedded: int = 0
    skipped: int = 0   # already had a usable embedding
    failed: int = 0


def backfill_embeddings(store: DynamoCardStore) -> BackfillResult:
    """Embed every card in `store` that has no `EMBED_DIM`-long embedding."""
    missing, total = store.list_unembedded()
    result = BackfillResult(skipped=total - len(missing))
    for item in missing:
        try:
            store.set_embedding(item["card_id"], embed(card_text(item)))
        except Exception as exc:  # noqa: BLE001 - per-card failure: count, continue
            print(f"! failed to embed {item.get('url')}: {exc}")
            result.failed += 1
            continue
        result.embedded += 1
    return result

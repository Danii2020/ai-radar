"""RAG retrieval — embed cards with Titan v2 and rank by cosine similarity.

In-memory and file-cached: fine for the spike's small corpus. In later phases
this becomes a real vector store (pgvector / Pinecone / DynamoDB brute-force).
"""
from __future__ import annotations

import json

from .bedrock import bedrock_client
from .config import EMBED_DIM, EMBED_MODEL_ID, EMBED_PATH


def embed(text: str) -> list[float]:
    """Return a normalized embedding vector for `text` (cosine == dot product)."""
    body = json.dumps(
        {"inputText": text[:8000], "dimensions": EMBED_DIM, "normalize": True}
    )
    resp = bedrock_client().invoke_model(modelId=EMBED_MODEL_ID, body=body)
    return json.loads(resp["body"].read())["embedding"]


def _card_text(card: dict) -> str:
    parts = [card.get("title", ""), card.get("summary", "")]
    parts += card.get("takeaways", [])
    parts += card.get("tags", [])
    return "\n".join(p for p in parts if p)


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class CardIndex:
    """Tiny vector index over curated cards, keyed by URL with a disk cache."""

    def __init__(self, cards: list[dict]):
        self.cards = cards
        self.vectors: dict[str, list[float]] = {}
        self._build()

    def _build(self) -> None:
        cache: dict[str, list[float]] = {}
        if EMBED_PATH.exists():
            cache = json.loads(EMBED_PATH.read_text())

        dirty = False
        for card in self.cards:
            url = card["url"]
            vec = cache.get(url)
            if vec is None or len(vec) != EMBED_DIM:
                vec = embed(_card_text(card))
                cache[url] = vec
                dirty = True
            self.vectors[url] = vec

        if dirty:
            EMBED_PATH.parent.mkdir(parents=True, exist_ok=True)
            EMBED_PATH.write_text(json.dumps(cache))

    def search(self, query: str, k: int) -> list[tuple[dict, float]]:
        q = embed(query)
        scored = [
            (card, _dot(q, self.vectors[card["url"]])) for card in self.cards
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

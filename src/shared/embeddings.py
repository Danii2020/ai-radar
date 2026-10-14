"""Titan v2 embeddings — the one place both planes get vectors from.

Neutral on purpose: Plane A (curation embeds new cards) and Plane B (retrieval
embeds the query) both need `embed` and `card_text`, and neither plane may
import the other's internals.
"""
from __future__ import annotations

import json

from .bedrock import bedrock_client
from .config import EMBED_DIM, EMBED_MODEL_ID


def embed(text: str) -> list[float]:
    """Return a normalized embedding vector for `text` (cosine == dot product)."""
    body = json.dumps(
        {"inputText": text[:8000], "dimensions": EMBED_DIM, "normalize": True}
    )
    resp = bedrock_client().invoke_model(modelId=EMBED_MODEL_ID, body=body)
    return json.loads(resp["body"].read())["embedding"]


def card_text(card: dict) -> str:
    """The text a card is embedded from: title, summary, takeaways, tags."""
    parts = [card.get("title", ""), card.get("summary", "")]
    parts += card.get("takeaways", [])
    parts += card.get("tags", [])
    return "\n".join(p for p in parts if p)

"""Spike configuration — env-overridable, sensible local defaults."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # pull .env if present; otherwise rely on ~/.aws + defaults

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Cross-region inference profiles (verified available in us-east-1).
# Haiku 4.5 = cheap bulk summarization; Sonnet 4.6 = higher-quality chat.
HAIKU_MODEL_ID = os.getenv(
    "HAIKU_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
)
# Chat model. Default is Sonnet 4.5 (enabled in this account). The design targets
# Sonnet 4.6 — enable its model access in the Bedrock console, then set
# SONNET_MODEL_ID=us.anthropic.claude-sonnet-4-6 to upgrade.
SONNET_MODEL_ID = os.getenv(
    "SONNET_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
)

# Titan Text Embeddings v2 for RAG retrieval. normalize=True → cosine == dot product.
EMBED_MODEL_ID = os.getenv("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
EMBED_DIM = int(os.getenv("EMBED_DIM", "256"))

# How many cards to retrieve as grounding context per chat turn.
TOP_K = int(os.getenv("SPIKE_TOP_K", "4"))

# How much work to do per run (keeps the spike cheap and fast).
MAX_ITEMS = int(os.getenv("SPIKE_MAX_ITEMS", "8"))
PER_FEED = int(os.getenv("SPIKE_PER_FEED", "5"))

# Curated, zero-key AI/ML feeds for discovery. Mix of papers, labs, and practitioners.
FEEDS: dict[str, str] = {
    "arXiv cs.AI": "http://export.arxiv.org/rss/cs.AI",
    "arXiv cs.LG": "http://export.arxiv.org/rss/cs.LG",
    "Hugging Face Blog": "https://huggingface.co/blog/feed.xml",
    "BAIR Blog": "https://bair.berkeley.edu/blog/feed.xml",
    "Simon Willison": "https://simonwillison.net/atom/everything/",
    "MIT Tech Review AI": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
}

# Local dedup store so re-runs skip items already curated (idempotency, like the real pipeline).
CACHE_DIR = Path(os.getenv("SPIKE_CACHE_DIR", ".spike_cache"))
SEEN_PATH = CACHE_DIR / "seen.json"
CARDS_PATH = CACHE_DIR / "cards.json"
EMBED_PATH = CACHE_DIR / "embeddings.json"

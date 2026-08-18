"""Shared cross-plane configuration — env-overridable, sensible local defaults.

Consumed by both planes: `curation.*` / `runtime_app.py` / `run_curation.py`
(Plane A) and `chat` / `retrieval` / `run_chat.py` (Plane B). Holds the AWS
region, the Bedrock model IDs and the unit prices that go with them, the
per-run work caps, and the local cache paths.

Plane-A-only knobs live in `curation/config.py` (`CURATION_*`, `CARD_*`).
Env keys here are prefixed `AI_RADAR_*` — the app name, never a package name,
so a future package move cannot invalidate them again.
"""
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

# Bedrock unit prices (design §7), USD per 1M tokens, for HAIKU_MODEL_ID above.
# They live HERE, with the model ID they price, so a model swap and its price
# change are one edit in one file. Consumed by curation.summary.
# estimate_bedrock_cost_usd (Spec 06); Sonnet/Titan prices are deliberately
# absent — Plane A summarizes with Haiku only (chat/embeddings are Plane B /
# Phase 3 concerns and adding their prices now would be speculative config).
HAIKU_INPUT_USD_PER_1M = float(os.getenv("HAIKU_INPUT_USD_PER_1M", "1.0"))
HAIKU_OUTPUT_USD_PER_1M = float(os.getenv("HAIKU_OUTPUT_USD_PER_1M", "5.0"))
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
TOP_K = int(os.getenv("AI_RADAR_TOP_K", "4"))

# How much work to do per run (keeps each run cheap and fast).
MAX_ITEMS = int(os.getenv("AI_RADAR_MAX_ITEMS", "8"))
PER_FEED = int(os.getenv("AI_RADAR_PER_FEED", "5"))

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
CACHE_DIR = Path(os.getenv("AI_RADAR_CACHE_DIR", ".ai_radar_cache"))
SEEN_PATH = CACHE_DIR / "seen.json"
CARDS_PATH = CACHE_DIR / "cards.json"
EMBED_PATH = CACHE_DIR / "embeddings.json"

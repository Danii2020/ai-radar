"""Shared cross-plane configuration — env-overridable, sensible local defaults.

Consumed by both planes: `curation.*` / `runtime_app.py` / `run_curation.py`
(Plane A) and `chat` / `retrieval` / `run_chat.py` (Plane B). Holds the AWS
region, the Bedrock model IDs and the unit prices that go with them, the
per-run work caps, and the local cache paths.

Plane-A-only knobs live in `curation/config.py` (`CURATION_*`, `CARD_*`).
Env keys here are prefixed `AI_RADAR_*` — the app name, never a package name,
so a future package move cannot invalidate them again. A handful are
deliberately bare (`AWS_REGION`, the Bedrock model IDs and prices) because
they name vendor concepts, not app knobs.

Env parsing and validation are owned by `_SharedSettings` (pydantic-settings);
the module-level UPPERCASE constants below are the public surface every
consumer reads — and, in the curation twin, writes.
"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: The ONE dotenv load in this codebase (intent.md Gate G2). It must run before
#: `_SharedSettings()` below, and — unlike pydantic-settings' own `env_file=`
#: source — it populates the real process environment, which is how **boto3** picks up
#: the optional AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY entries documented in
#: `.env.example`. It also keeps python-dotenv's upward directory search, so
#: running from a subdirectory behaves as it always has. `curation/config.py`
#: imports this module purely to guarantee this call has already run.
#: Never add a second call anywhere.
load_dotenv()


class _SharedSettings(BaseSettings):
    """Env parsing + validation for the cross-plane knobs.

    Private by convention: instantiated exactly once, immediately below, and
    never exported. Every field carries an explicit `validation_alias` — the
    literal env var name — so `grep` on an env var lands on its definition and
    no `env_prefix` magic can silently rename a knob.
    """

    #: `case_sensitive=True` reproduces the old hand-rolled lookup's exact-case matching
    #: (pydantic-settings defaults to case-INsensitive, which would newly
    #: accept e.g. `aws_region`). `extra="ignore"` is defensive: the process
    #: environment is full of variables that are none of this model's business.
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    aws_region: str = Field("us-east-1", validation_alias="AWS_REGION")

    haiku_model_id: str = Field(
        "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        validation_alias="HAIKU_MODEL_ID",
    )
    haiku_input_usd_per_1m: float = Field(
        1.0, validation_alias="HAIKU_INPUT_USD_PER_1M"
    )
    haiku_output_usd_per_1m: float = Field(
        5.0, validation_alias="HAIKU_OUTPUT_USD_PER_1M"
    )
    sonnet_model_id: str = Field(
        "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        validation_alias="SONNET_MODEL_ID",
    )

    embed_model_id: str = Field(
        "amazon.titan-embed-text-v2:0", validation_alias="EMBED_MODEL_ID"
    )
    embed_dim: int = Field(256, validation_alias="EMBED_DIM")

    top_k: int = Field(4, validation_alias="AI_RADAR_TOP_K")
    max_items: int = Field(8, validation_alias="AI_RADAR_MAX_ITEMS")
    per_feed: int = Field(5, validation_alias="AI_RADAR_PER_FEED")

    cache_dir: Path = Field(
        Path(".ai_radar_cache"), validation_alias="AI_RADAR_CACHE_DIR"
    )


#: Import-time singleton. A bad override raises `pydantic.ValidationError`
#: HERE, naming the offending env var — see the Error Handling Contract.
_settings = _SharedSettings()

# --- Public surface: unchanged names, unchanged values --------------------
AWS_REGION: str = _settings.aws_region

# Cross-region inference profiles (verified available in us-east-1).
# Haiku 4.5 = cheap bulk summarization; Sonnet 4.6 = higher-quality chat.
HAIKU_MODEL_ID: str = _settings.haiku_model_id

# Bedrock unit prices (design §7), USD per 1M tokens, for HAIKU_MODEL_ID above.
# They live HERE, with the model ID they price, so a model swap and its price
# change are one edit in one file. Consumed by curation.summary.
# estimate_bedrock_cost_usd (Spec 06); Sonnet/Titan prices are deliberately
# absent — Plane A summarizes with Haiku only (chat/embeddings are Plane B /
# Phase 3 concerns and adding their prices now would be speculative config).
HAIKU_INPUT_USD_PER_1M: float = _settings.haiku_input_usd_per_1m
HAIKU_OUTPUT_USD_PER_1M: float = _settings.haiku_output_usd_per_1m

# Chat model. Default is Sonnet 4.5 (enabled in this account). The design targets
# Sonnet 4.6 — enable its model access in the Bedrock console, then set
# SONNET_MODEL_ID=us.anthropic.claude-sonnet-4-6 to upgrade.
SONNET_MODEL_ID: str = _settings.sonnet_model_id

# Titan Text Embeddings v2 for RAG retrieval. normalize=True → cosine == dot product.
EMBED_MODEL_ID: str = _settings.embed_model_id
EMBED_DIM: int = _settings.embed_dim

# How many cards to retrieve as grounding context per chat turn.
TOP_K: int = _settings.top_k

# How much work to do per run (keeps each run cheap and fast).
MAX_ITEMS: int = _settings.max_items
PER_FEED: int = _settings.per_feed

# Curated, zero-key AI/ML feeds for discovery. Mix of papers, labs, and practitioners.
# NOT env-overridable (unchanged) — a plain constant, deliberately outside
# _SharedSettings.
FEEDS: dict[str, str] = {
    "arXiv cs.AI": "http://export.arxiv.org/rss/cs.AI",
    "arXiv cs.LG": "http://export.arxiv.org/rss/cs.LG",
    "Hugging Face Blog": "https://huggingface.co/blog/feed.xml",
    "BAIR Blog": "https://bair.berkeley.edu/blog/feed.xml",
    "Simon Willison": "https://simonwillison.net/atom/everything/",
    "MIT Tech Review AI": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
}

# Local dedup store so re-runs skip items already curated (idempotency, like the
# real pipeline). The three paths are DERIVED from CACHE_DIR, not separately
# env-overridable (unchanged).
CACHE_DIR: Path = _settings.cache_dir
SEEN_PATH: Path = CACHE_DIR / "seen.json"
CARDS_PATH: Path = CACHE_DIR / "cards.json"
EMBED_PATH: Path = CACHE_DIR / "embeddings.json"

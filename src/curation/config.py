"""Curation-plane config for web discovery — env-overridable, sensible defaults."""
from __future__ import annotations
from dotenv import load_dotenv

import os

load_dotenv()


# Tavily API key — LOCAL ONLY (.env / env var). Secrets Manager resolution is
# Spec 04 (runtime-packaging); no boto3 here. Empty string when unset.
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

# Topic seed queries (design §5 topic areas). Override with a ';'-separated list.
_DEFAULT_SEEDS = [
    "latest large language model releases and updates",
    "new generative AI and LLM research papers",
    "AI agents and agentic framework news",
    "machine learning and deep learning breakthroughs",
    "open source AI model and tooling releases",
]
TAVILY_SEEDS: list[str] = [
    s.strip()
    for s in os.getenv("CURATION_TAVILY_SEEDS", ";".join(_DEFAULT_SEEDS)).split(";")
    if s.strip()
]

# Tunables (all env-overridable). MAX_RESULTS is the PRIMARY COST LEVER (§7).
TAVILY_RESULTS_PER_QUERY: int = int(os.getenv("CURATION_TAVILY_RESULTS_PER_QUERY", "5"))
TAVILY_MAX_RESULTS: int = int(os.getenv("CURATION_TAVILY_MAX_RESULTS", "20"))
TAVILY_DAYS: int = int(os.getenv("CURATION_TAVILY_DAYS", "7"))
TAVILY_SEARCH_DEPTH: str = os.getenv("CURATION_TAVILY_SEARCH_DEPTH", "basic")
TAVILY_TOPIC: str = os.getenv("CURATION_TAVILY_TOPIC", "general")


def _csv(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [d.strip() for d in raw.split(",") if d.strip()]


TAVILY_INCLUDE_DOMAINS: list[str] = _csv("CURATION_TAVILY_INCLUDE_DOMAINS")
TAVILY_EXCLUDE_DOMAINS: list[str] = _csv("CURATION_TAVILY_EXCLUDE_DOMAINS")

# --- DynamoDB card store (Spec 03) ---------------------------------------
# Base table name. The CDK construct provisions this exact name; the store reads
# it here so both sides agree without a CloudFormation-output lookup.
CARD_TABLE_NAME: str = os.getenv("CARD_TABLE_NAME", "ai-radar-cards")

# Feed-read GSI (designed now for Phase 2; written by Phase 1, read by Phase 2).
FEED_GSI_NAME: str = "feed-by-score"       # constant — matches the CDK construct
FEED_GSI_PARTITION: str = "CARD"           # single constant GSI partition (no bucketing)

# Store selector for the local entrypoint: "json" (default) | "dynamo".
CARD_STORE_BACKEND: str = os.getenv("CARD_STORE_BACKEND", "json")

# --- Runtime packaging (Spec 04) -----------------------------------------
# Secrets Manager secret NAME holding the Tavily API key. Resolved at runtime by
# the AgentCore entrypoint (runtime_app.py); the KEY VALUE is never stored here,
# in env at build time, or in the image. Matches the CDK-provisioned secret name.
TAVILY_SECRET_NAME: str = os.getenv("TAVILY_SECRET_NAME", "ai-radar/tavily-api-key")

# Sentinel value the CDK-provisioned Tavily secret (infra/lib/agent_runtime.py)
# is pinned to at deploy time, before a human `put-secret-value`s the real key
# (Task 3.5). NOT env-overridable — a fixed literal that MUST match the
# construct's placeholder value exactly. `runtime_app._resolve_tavily_key`
# treats a secret whose value equals this sentinel as "not yet populated" and
# returns "" (degrade to RSS-only), so a freshly-deployed-but-unpopulated
# secret never gets treated as a real, usable Tavily key.
TAVILY_SECRET_UNSET_SENTINEL: str = "UNSET-populate-via-put-secret-value"

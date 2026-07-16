"""Curation-plane config for web discovery — env-overridable, sensible defaults."""
from __future__ import annotations

import os

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

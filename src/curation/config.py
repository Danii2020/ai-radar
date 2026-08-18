"""Curation-plane config for web discovery — env-overridable, sensible defaults.

Env parsing and validation are owned by `_CurationSettings`
(pydantic-settings); the module-level UPPERCASE constants below are the public
surface. `TAVILY_API_KEY` is deliberately a plain, WRITABLE module attribute:
`runtime_app._build_discoverer` assigns the Secrets-Manager-resolved key onto
it at invocation time.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Imported for its import-time side effect ONLY: `shared.config` owns the
# one dotenv-loading call in this codebase, and it must have run before
# `_CurationSettings()` below reads the environment. Importing shared from
# curation is the established direction (see `curation/dynamo.py`,
# `curation/summary.py`); the reverse never happens.
from shared import config as _shared_config  # noqa: F401

# Topic seed queries (design §5 topic areas). Override with a ';'-separated list.
# NOT env-overridable itself — it is the DEFAULT for CURATION_TAVILY_SEEDS.
_DEFAULT_SEEDS = [
    "latest large language model releases and updates",
    "new generative AI and LLM research papers",
    "AI agents and agentic framework news",
    "machine learning and deep learning breakthroughs",
    "open source AI model and tooling releases",
]


class _CurationSettings(BaseSettings):
    """Env parsing + validation for the Plane-A-only knobs. See
    `shared/config.py::_SharedSettings` for the model_config rationale."""

    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    # Tavily API key — LOCAL ONLY (.env / env var). Secrets Manager resolution
    # happens in runtime_app.py; no boto3 here. Empty string when unset.
    tavily_api_key: str = Field("", validation_alias="TAVILY_API_KEY")

    # `NoDecode` switches OFF pydantic-settings' default JSON decoding of
    # complex types, so `CURATION_TAVILY_SEEDS` stays a ';'-separated string
    # rather than becoming a JSON array. The validators below reproduce the
    # previous hand-rolled splits EXACTLY, including empty-string → [].
    tavily_seeds: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(_DEFAULT_SEEDS),
        validation_alias="CURATION_TAVILY_SEEDS",
    )

    # Tunables. MAX_RESULTS is the PRIMARY COST LEVER (§7).
    tavily_results_per_query: int = Field(
        5, validation_alias="CURATION_TAVILY_RESULTS_PER_QUERY"
    )
    tavily_max_results: int = Field(20, validation_alias="CURATION_TAVILY_MAX_RESULTS")
    tavily_days: int = Field(7, validation_alias="CURATION_TAVILY_DAYS")
    tavily_search_depth: str = Field(
        "basic", validation_alias="CURATION_TAVILY_SEARCH_DEPTH"
    )
    tavily_topic: str = Field("general", validation_alias="CURATION_TAVILY_TOPIC")

    tavily_include_domains: Annotated[list[str], NoDecode] = Field(
        default_factory=list, validation_alias="CURATION_TAVILY_INCLUDE_DOMAINS"
    )
    tavily_exclude_domains: Annotated[list[str], NoDecode] = Field(
        default_factory=list, validation_alias="CURATION_TAVILY_EXCLUDE_DOMAINS"
    )

    # --- DynamoDB card store (Spec 03) ------------------------------------
    # Base table name. The CDK construct provisions this exact name; the store
    # reads it here so both sides agree without a CloudFormation-output lookup.
    card_table_name: str = Field("ai-radar-cards", validation_alias="CARD_TABLE_NAME")
    # Store selector for the local entrypoint: "json" (default) | "dynamo".
    card_store_backend: str = Field("json", validation_alias="CARD_STORE_BACKEND")

    # --- Runtime packaging (Spec 04) --------------------------------------
    # Secrets Manager secret NAME holding the Tavily API key. Resolved at
    # runtime by runtime_app.py; the KEY VALUE is never stored here, in env at
    # build time, or in the image. Matches the CDK-provisioned secret name.
    tavily_secret_name: str = Field(
        "ai-radar/tavily-api-key", validation_alias="TAVILY_SECRET_NAME"
    )

    # --- Run observability (Spec 06) --------------------------------------
    tavily_credit_price_usd: float = Field(
        0.008, validation_alias="CURATION_TAVILY_CREDIT_PRICE_USD"
    )
    metric_namespace: str = Field(
        "AIRadar/Curation", validation_alias="CURATION_METRIC_NAMESPACE"
    )
    emit_run_metrics: bool = Field(True, validation_alias="CURATION_EMIT_METRICS")

    @field_validator("tavily_seeds", mode="before")
    @classmethod
    def _split_semicolons(cls, value: object) -> object:
        """`"a; b"` → `["a", "b"]`; `""` → `[]`. Reproduces the previous
        hand-rolled `.split(";")` comprehension exactly."""
        if isinstance(value, str):
            return [s.strip() for s in value.split(";") if s.strip()]
        return value

    @field_validator("tavily_include_domains", "tavily_exclude_domains", mode="before")
    @classmethod
    def _split_commas(cls, value: object) -> object:
        """`"a, b"` → `["a", "b"]`; `""` → `[]`. Reproduces the previous
        `_csv()` helper exactly."""
        if isinstance(value, str):
            return [d.strip() for d in value.split(",") if d.strip()]
        return value


_settings = _CurationSettings()

# --- Public surface: unchanged names, unchanged values --------------------
#: WRITABLE by design — `runtime_app._build_discoverer` assigns the
#: Secrets-Manager-resolved key here before `TavilyDiscoverer.from_config()`.
TAVILY_API_KEY: str = _settings.tavily_api_key

TAVILY_SEEDS: list[str] = _settings.tavily_seeds
TAVILY_RESULTS_PER_QUERY: int = _settings.tavily_results_per_query
TAVILY_MAX_RESULTS: int = _settings.tavily_max_results
TAVILY_DAYS: int = _settings.tavily_days
TAVILY_SEARCH_DEPTH: str = _settings.tavily_search_depth
TAVILY_TOPIC: str = _settings.tavily_topic
TAVILY_INCLUDE_DOMAINS: list[str] = _settings.tavily_include_domains
TAVILY_EXCLUDE_DOMAINS: list[str] = _settings.tavily_exclude_domains

CARD_TABLE_NAME: str = _settings.card_table_name
CARD_STORE_BACKEND: str = _settings.card_store_backend
TAVILY_SECRET_NAME: str = _settings.tavily_secret_name

TAVILY_CREDIT_PRICE_USD: float = _settings.tavily_credit_price_usd
METRIC_NAMESPACE: str = _settings.metric_namespace
# CloudWatch EMF metrics. 4 metrics x $0.30/metric-month ~= $1.20/mo; set
# CURATION_EMIT_METRICS=false to stop emitting entirely (logs still carry the
# full summary).
EMIT_RUN_METRICS: bool = _settings.emit_run_metrics

# --- Fixed constants: NOT env-overridable, deliberately outside the model ---
# Feed-read GSI (designed now for Phase 2; written by Phase 1, read by Phase 2).
FEED_GSI_NAME: str = "feed-by-score"       # constant — matches the CDK construct
FEED_GSI_PARTITION: str = "CARD"           # single constant GSI partition (no bucketing)

# Sentinel value the CDK-provisioned Tavily secret (infra/lib/agent_runtime.py)
# is pinned to at deploy time, before a human `put-secret-value`s the real key.
# NOT env-overridable — a fixed literal that MUST match the construct's
# placeholder value exactly. `runtime_app._resolve_tavily_key` treats a secret
# whose value equals this sentinel as "not yet populated" and returns ""
# (degrade to RSS-only), so a freshly-deployed-but-unpopulated secret never
# gets treated as a real, usable Tavily key.
TAVILY_SECRET_UNSET_SENTINEL: str = "UNSET-populate-via-put-secret-value"

# Source-label prefix TavilyDiscoverer stamps on every RawItem it produces.
# `summary.split_by_origin` classifies RSS vs Tavily by this prefix, so the
# two must stay in sync (tavily.py imports it from here).
TAVILY_SOURCE_PREFIX: str = "Tavily: "

# Tavily cost model. Tavily bills in CREDITS and its API response does NOT
# report consumption, so TAVILY_CREDIT_PRICE_USD above is an ESTIMATE. Basic
# search = 1 credit, advanced = 2 (Tavily API-credits docs, verified 2026-08);
# unknown depths ("fast"/"ultra-fast") fall back to 1. $0.008/credit is
# Tavily's public pay-as-you-go rate — override when the real plan is known.
TAVILY_CREDITS_BY_DEPTH: dict[str, int] = {"basic": 1, "advanced": 2}
TAVILY_DEFAULT_CREDITS_PER_SEARCH: int = 1

# NOTE: the Bedrock unit prices are NOT here — they live in shared/config.py
# next to HAIKU_MODEL_ID, the model they price (see shared/config.py).

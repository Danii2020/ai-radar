# Contract: pydantic-settings-config

**Language/stack:** Python 3.11+ (`uv`-managed, `src/` layout,
`[tool.uv] package = false`). All code below is real, final Python for this
repo — not pseudocode.

**Shape of the change, in one sentence:** each config module gains a private
`BaseSettings` subclass that owns *all* env parsing and validation, is
instantiated **once at import time**, and has its values re-exported under the
**existing UPPERCASE module-constant names**; every consumer callsite is
untouched.

---

## 0. The design decision, and why it is forced

`pydantic-settings` offers two idioms: pass a `Settings` *instance* around, or
read module constants. This spec pins **module constants re-exported from an
import-time singleton**. That is not a stylistic preference — three facts in
the current codebase make it the only option that satisfies intent.md Goal 4:

1. **Consumers *write* to the config module.** `runtime_app.py:116` does
   `curation_config.TAVILY_API_KEY = key` after resolving the Secrets Manager
   value at invocation time. `tests/test_runtime_app.py` assigns it directly at
   8 sites; `tests/test_run_summary.py`, `tests/test_runtime_app.py` and
   `tests/test_tavily.py` use `monkeypatch.setattr(<module>.config, "NAME",
   value)` at 9 more. A frozen model, or `config.settings.tavily_api_key`,
   breaks all 17.
2. **Consumers bind values at import.** `shared/bedrock.py` does
   `from .config import AWS_REGION, HAIKU_MODEL_ID`; `shared/chat.py` and
   `shared/retrieval.py` do the same. A lazily-constructed settings object
   would change *when* those values are read.
3. **`from shared import config` / `from . import config` is the house
   convention** at 11 sites across `src/`, the entrypoints and `tests/`.

So: `BaseSettings` is an **implementation detail of the two config modules**.
It never leaks into a signature, a node, a graph, or a test's public surface.
This also keeps the change inside `docs/architecture-principles.md`'s "no
speculative interfaces" rule — no config service, no injection, no registry.

---

## Interfaces

### 1. `src/shared/config.py` (MODIFY — full rewrite of the loading mechanism)

```python
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
#: source — it populates the real `os.environ`, which is how **boto3** picks up
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

    #: `case_sensitive=True` reproduces `os.getenv`'s exact-case matching
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
```

### 2. `src/curation/config.py` (MODIFY — full rewrite of the loading mechanism)

```python
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
# single `load_dotenv()` call in this codebase, and it must have run before
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
    # build time, or in the image.
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
        `os.getenv(...).split(";")` comprehension exactly."""
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
# (degrade to RSS-only).
TAVILY_SECRET_UNSET_SENTINEL: str = "UNSET-populate-via-put-secret-value"

# Source-label prefix TavilyDiscoverer stamps on every RawItem it produces.
# `summary.split_by_origin` classifies RSS vs Tavily by this prefix, so the
# two must stay in sync (tavily.py imports it from here).
TAVILY_SOURCE_PREFIX: str = "Tavily: "

# Tavily cost model. Tavily bills in CREDITS and its API response does NOT
# report consumption, so TAVILY_CREDIT_PRICE_USD above is an ESTIMATE. Basic
# search = 1 credit, advanced = 2 (Tavily API-credits docs, verified 2026-08);
# unknown depths ("fast"/"ultra-fast") fall back to 1.
TAVILY_CREDITS_BY_DEPTH: dict[str, int] = {"basic": 1, "advanced": 2}
TAVILY_DEFAULT_CREDITS_PER_SEARCH: int = 1

# NOTE: the Bedrock unit prices are NOT here — they live in shared/config.py
# next to HAIKU_MODEL_ID, the model they price (see shared/config.py).
```

### 3. `pyproject.toml` (MODIFY — one line)

```toml
dependencies = [
    "bedrock-agentcore>=1.18.1",
    "boto3>=1.35",
    "feedparser>=6.0",
    "langgraph>=1.2.9",
    "pydantic-settings>=2.14.2",   # ← added by `uv add pydantic-settings`
    "python-dotenv>=1.0",
    "rich>=13.7",
    "tavily-python>=0.7.26",
]
```

**Main group, not `dev`** — this is load-bearing. Verified in `uv.lock`
2026-08-18: `pydantic-settings` is reachable today only via
`bedrock-agentcore-starter-toolkit` (dev group) → `openapi-spec-validator`, and
`Dockerfile` runs `uv sync --frozen --no-dev`. Without this line the next
`agentcore deploy` ships an image that dies on `import shared.config`.
`python-dotenv` stays an explicit dependency (still directly imported).

---

## Data Models

No new *data* models. `Card`, `RawItem`, `RunSummary`, `TokenUsage` and the
graph state are **untouched** — `Card` remains a plain dataclass
(`docs/architecture-principles.md` point 2 stands; see §Docs below).

The two new classes, `_SharedSettings` and `_CurationSettings`, are
**private configuration adapters at the process edge**, not domain types. They
are never imported, never annotated in a signature, never passed as an
argument, and never returned.

---

## State Changes

| Aspect | Before | After |
|---|---|---|
| When values are computed | Module import time | Module import time (**unchanged**) |
| Where values live | Module attributes | Module attributes (**unchanged**) |
| Mutability of `config.NAME` | Writable | Writable (**unchanged** — required by `runtime_app.py:116` and 16 test sites) |
| `.env` → `os.environ` | Two `load_dotenv()` calls | One `load_dotenv()` call, in `shared/config.py` |
| Import order coupling | None | `curation.config` imports `shared.config` (new, one-directional, no cycle) |
| Failure on bad input | Bare `ValueError` from `int`/`float`, or silent wrong value | `pydantic.ValidationError` (a `ValueError` subclass) naming the env var |

Mutating `config.NAME` after import does **not** write back to `_settings`, and
`_settings` is never re-read after import — so there is exactly one source of
truth at any moment, as today.

---

## Behavior Guarantees

1. **Every env var name is preserved verbatim.** All 26 (11 in
   `shared/config.py`, 15 in `curation/config.py`) resolve to the same module
   constant as before. No renames, no new prefixes, no `env_prefix` — each is
   spelled out in a `validation_alias`.
2. **Every default value is preserved exactly**, including `FEEDS`' six
   entries and the five `_DEFAULT_SEEDS`. `TAVILY_SEEDS`' default is
   `list(_DEFAULT_SEEDS)`, which equals today's
   `";".join(_DEFAULT_SEEDS).split(";")` because no seed contains `";"`.
3. **Every consumer callsite keeps working unchanged** — both import styles
   (`from shared import config` / `from . import config` / `from shared import
   config as shared_config` / `import curation.config as X`) and both access
   styles (`config.NAME` attribute access and `from .config import NAME`
   from-import).
4. **`config.NAME` stays assignable.** `curation_config.TAVILY_API_KEY = key`
   and `monkeypatch.setattr(<module>.config, "NAME", value)` behave exactly as
   before.
5. **The 11 fixed constants stay non-env-overridable.** Setting `FEEDS`,
   `SEEN_PATH`, `CARDS_PATH`, `EMBED_PATH`, `FEED_GSI_NAME`,
   `FEED_GSI_PARTITION`, `TAVILY_SECRET_UNSET_SENTINEL`,
   `TAVILY_SOURCE_PREFIX`, `TAVILY_CREDITS_BY_DEPTH`,
   `TAVILY_DEFAULT_CREDITS_PER_SEARCH` or `_DEFAULT_SEEDS` in the environment
   has **no effect**.
6. **Exact-case env matching is preserved.** `case_sensitive=True` means
   `aws_region=x` is ignored, exactly as `os.getenv("AWS_REGION")` ignores it.
7. **Empty-string overrides preserve today's semantics per field**:
   `TAVILY_API_KEY=` → `""`; `CURATION_TAVILY_SEEDS=` → `[]` (**not** the
   defaults); `CURATION_TAVILY_INCLUDE_DOMAINS=` / `..._EXCLUDE_DOMAINS=` →
   `[]`; `AI_RADAR_CACHE_DIR=` → `Path(".")`; numeric fields → a validation
   error (as `int("")`/`float("")` raise today).
8. **A bad override fails at import, loudly, naming the variable.** See the
   Error Handling Contract.
9. **`.env` is loaded exactly once**, by `shared/config.py`, into the real
   `os.environ`, with python-dotenv's upward directory search intact — so
   boto3 still sees the credential vars `.env.example` documents.
10. **No new runtime behavior.** Config import performs no network call, no
    AWS call, and no filesystem I/O beyond what `load_dotenv()` already did.
11. **No infra change.** No CDK stack, no `Dockerfile` edit, no
    `agentcore deploy` is part of this spec.
12. **Plane boundaries hold.** `shared/config.py` imports nothing from
    `curation`; `curation/config.py` imports only `shared.config`. `Card`
    remains the sole shared domain contract.

### The one deliberate behavior change

**`CURATION_EMIT_METRICS` now uses pydantic's native `bool` coercion.**
Confirmed by the human 2026-08-18; documented here as an intentional deviation
from byte-identical parity, and the *only* one in this migration.

| Value | Before | After |
|---|---|---|
| `true` / `True` / `TRUE` | `True` | `True` |
| `false` / `False` | `False` | `False` |
| `1` / `yes` / `on` / `t` / `y` | `False` (silent) | **`True`** |
| `0` / `no` / `off` / `f` / `n` | `False` | `False` |
| `yolo` (any unparseable value) | `False` (silent) | **`ValidationError` at import** |

Rationale: the old rule was `str(raw).lower() == "true"`, so a typo'd kill
switch silently disabled the CloudWatch metrics `run-observability` exists to
produce — no error, no warning, missing telemetry on a deployed agent. Failing
loudly is the point of this spec. No documented value changes meaning
(`.env.example` and `README.md` both show `true`/`false` only), so no operator
action is required.

---

## Error Handling Contract

| Error Condition | Behavior | User Impact |
|---|---|---|
| `HAIKU_INPUT_USD_PER_1M=abc` (unparseable float) | `pydantic.ValidationError` raised by `_SharedSettings()` at import of `shared.config`; **not caught anywhere** — propagates out of the import | Process exits with a traceback ending in `1 validation error for _SharedSettings / HAIKU_INPUT_USD_PER_1M / Input should be a valid number, unable to parse string as a number [type=float_parsing, input_value='abc', input_type=str]`. Was: a bare `ValueError: could not convert string to float: 'abc'` that named neither the variable nor the fact that config was at fault |
| `CURATION_TAVILY_CREDIT_PRICE_USD=` (empty) | Same, from `_CurationSettings()` at import of `curation.config` | Message names `CURATION_TAVILY_CREDIT_PRICE_USD` |
| `AI_RADAR_MAX_ITEMS=eight` / `EMBED_DIM=256.5` (unparseable int) | Same | Message names the variable and `int_parsing` |
| `CURATION_EMIT_METRICS=yolo` | Same (`bool_parsing`) | **New**: was silently `False` |
| Several bad vars at once | **One** `ValidationError` listing **every** offending variable (pydantic collects all field errors before raising) | One run of the fix loop instead of N |
| An env var this codebase does not know | Ignored (`extra="ignore"`) | Unchanged |
| `.env` absent | `load_dotenv()` no-ops; all defaults apply | Unchanged |
| A caller with `except ValueError` around a config import | Still catches it — `pydantic.ValidationError` **is** a `ValueError` subclass (verified against this repo's `.venv`, pydantic 2.13.4) | No regression. No such caller exists today; the guarantee is for future ones |

**Explicitly NOT done:** no `try/except` wrapper, no custom exception type, no
`sys.exit()`, no logging of the failure. Verified empirically that pydantic's
own message already names the `validation_alias` (i.e. the env var), which is
the whole ask in FU2 — wrapping it would add code and *remove* information.
Failing fast at import is correct for every entrypoint here (`run_curation.py`,
`run_chat.py`, `runtime_app.py`): a misconfigured agent must not start and
silently spend money on the wrong table or model.

---

## Dependencies

**New (deliberate, the only drift permitted):**
- `pydantic-settings>=2.14.2` — main dependency group. Already resolved to
  `2.14.2` in `uv.lock`; its own dependencies (`pydantic` 2.13.4,
  `python-dotenv`, `typing-inspection`) are **all already present**, so
  `uv add` must not move any other lockfile entry.

**Existing, still used:**
- `python-dotenv` — still directly imported by `shared/config.py`.
- `pydantic` 2.13.4 — already a real transitive dependency of
  `bedrock-agentcore` (present in the runtime image today).

**Internal:**
- `curation.config` → `shared.config` (new import, side-effect only,
  one-directional).

**Removed:** the `os` import from both config modules; the `_csv()` helper.

---

## Integration Points

Every one of these is **read-only for this spec** — listed to define the
regression surface, not to be edited.

| Consumer | Import style | What it reads |
|---|---|---|
| `src/shared/bedrock.py` | `from .config import AWS_REGION, HAIKU_MODEL_ID` | from-import (bound at import) |
| `src/shared/chat.py` | `from .config import SONNET_MODEL_ID, TOP_K` | from-import |
| `src/shared/retrieval.py` | `from .config import EMBED_DIM, EMBED_MODEL_ID, EMBED_PATH` | from-import |
| `src/curation/local.py` | `from shared import config` | `FEEDS`, `PER_FEED`, `SEEN_PATH`, `CARDS_PATH` |
| `src/curation/dynamo.py` | `from shared import config as shared_config` + `from . import config` | `AWS_REGION`; `CARD_TABLE_NAME`, `FEED_GSI_PARTITION` |
| `src/curation/summary.py` | `from shared import config as shared_config` + `from . import config` | `HAIKU_*_USD_PER_1M`; `TAVILY_SOURCE_PREFIX`, `TAVILY_CREDIT_PRICE_USD` |
| `src/curation/tavily.py` | `from . import config` | 10 `TAVILY_*` knobs via `from_config()` |
| `src/curation/metrics.py` | `from . import config` | `METRIC_NAMESPACE`, `EMIT_RUN_METRICS` |
| `run_curation.py` | `from shared import config` + `from curation import config as curation_config` | `MAX_ITEMS`, `CARDS_PATH`, `SEEN_PATH`; `CARD_STORE_BACKEND`, `CARD_TABLE_NAME`, `TAVILY_API_KEY` |
| `run_chat.py` | `from shared.config import CARDS_PATH` | from-import |
| `runtime_app.py` | `from shared import config` + `from curation import config as curation_config` | `AWS_REGION`, `MAX_ITEMS`; `TAVILY_SECRET_NAME`, `TAVILY_SECRET_UNSET_SENTINEL`, and **writes** `TAVILY_API_KEY` |
| `tests/test_infra_agent_runtime.py` | `from curation.config import TAVILY_SECRET_UNSET_SENTINEL as ...` | from-import; cross-checked against the CDK construct |
| `tests/test_runtime_app.py`, `tests/test_run_summary.py`, `tests/test_tavily.py`, `tests/test_local_store.py` | mixed | 17 read/`monkeypatch.setattr`/assignment sites |

---

## Documentation Contract

Three living docs make claims this migration invalidates. All three are
**in scope**; closed specs' files (`specs/run-observability/*`,
`specs/rename-spike-to-shared/*`) are the historical record and must **not** be
edited.

1. **`docs/architecture-principles.md`** — a short **dated append near point
   2**, leaving point 2's original text and framing intact (human decision,
   2026-08-18). Substance to convey: point 2's Pydantic deferral is about the
   **`Card` domain contract** — a published, versioned schema between two
   bounded contexts — and that deferral **stands**; adopting
   `pydantic-settings` for **environment-variable loading at the process edge**
   is a different concern (an infrastructure adapter, not a domain type), so it
   does not trigger, weaken, or pre-empt the `Card` decision. `Card` stays a
   plain dataclass until point 2's own trigger (a frontend or a real API)
   fires. Cite this spec by name.
2. **`CLAUDE.md`** — the "Deferred (later phases)" bullet currently reads
   "migrating config loading to `pydantic-settings` (currently only a
   transitive dependency; see `specs/run-observability/tasks.md` FU2)". Remove
   it from Deferred and record it as shipped in the "Current state" narrative,
   consistent with how the other Phase-1 specs are recorded.
3. **`README.md`** — the spec table gains a `pydantic-settings-config` row, and
   the "Config knobs (`.env` or env vars)" section notes that overrides are now
   validated at startup and that a bad value fails fast naming the variable.
4. **`.env.example`** — no key changes (Non-Goal), but the
   `CURATION_EMIT_METRICS` comment should state that it accepts
   `true/false/1/0/yes/no/on/off` and that an unparseable value is now a
   startup error.

---

## Verification Gates (machine-checkable, restated from intent.md)

| Gate | Command | Expected |
|---|---|---|
| G1 | `grep -rn "os.getenv\|os.environ" src/` | 0 lines |
| G2 | `grep -rn "load_dotenv" src/` | exactly 1 line (`src/shared/config.py`) |
| G3 | `uv run pytest tests/test_config.py` | table-driven: all 26 env vars → same constant, same default |
| G4 | `uv run pytest tests/test_config.py` | the 11 fixed constants are unmoved by same-named env vars |
| G5 | `grep -n "pydantic-settings" pyproject.toml` | present under `[project].dependencies` |
| G6 | `git diff --stat pyproject.toml uv.lock` | only the `pydantic-settings` addition; no other package version moves |
| G7 | `uv run pytest tests/` | ≥145 passed, 0 pre-existing assertions changed |

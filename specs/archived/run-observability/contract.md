# Contract: run-observability

Languages: **Python 3.11+** for the backend (`src/`, `runtime_app.py`,
`run_curation.py`, `tests/`) and **Python AWS CDK** for infrastructure
(`infra/`, `aws-cdk-lib==2.261.0`). Dependencies are managed by **uv** — and
this spec adds **none**.

Signatures below are pinned against material read 2026-08-11: the installed
`aws-cdk-lib==2.261.0` (`aws_cdk/aws_budgets/__init__.py`), the installed
`bedrock-agentcore==1.18.1` (`bedrock_agentcore/runtime/app.py`
`RequestContextFormatter`), the installed botocore service model
`bedrock-runtime/2023-09-30` (`TokenUsage` shape), the AWS *CloudWatch
embedded metric format specification*, and Tavily's *API credits* page.

## Interfaces

### 1. Bedrock seam — `src/spike/bedrock.py` (MODIFY, additive) -> why this here? i mean, the spike module is not longer used since this was mainly for spike purposes, btw we have 2 config.py and why are not we using pydantic-settings if this is installed?

The only place the Converse `usage` block is read. `summarize()` keeps its
**exact** signature and return type, so `src/spike/pipeline.py`,
`src/spike/chat.py`, `run_spike.py`, and `run_chat.py` are untouched.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenUsage:
    """Bedrock Converse token accounting for ONE model call.

    Mirrors the `usage` block of a Converse response (botocore shape
    `TokenUsage`: `inputTokens` / `outputTokens` / `totalTokens` are required;
    the cache fields are optional and unused here — `summarize` sets no cache
    point). Plain data: carried out of the infra edge so `curation.nodes` can
    accumulate token counts without ever importing boto3.
    """

    input_tokens: int = 0
    output_tokens: int = 0


def summarize_with_usage(item: RawItem) -> tuple[dict, TokenUsage]:
    """Same Converse call as `summarize`, returning the card dict AND the
    call's token usage.

    Missing/malformed `usage` degrades to `TokenUsage(0, 0)` — a cost figure
    is never worth failing a run over. Raises `RuntimeError` when the model
    returns no `toolUse` block (unchanged behavior).
    """


def summarize(item: RawItem) -> dict:
    """UNCHANGED public signature and return value (Phase 0 + Plane B
    callers depend on it). Now a one-line wrapper:
    `return summarize_with_usage(item)[0]`.
    """
```

### 2. Run summary + cost math — `src/curation/summary.py` (NEW)

Pure logic. No `boto3`, no CloudWatch, no file/network I/O — held to the same
portability rule as `nodes.py` / `graph.py` / `state.py`.

```python
"""Run-level summary + cost estimation for one curation pass (Spec 06)."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from spike import config as spike_config   # Bedrock unit prices (see §4)

from . import config                       # Tavily prices, namespace, toggles


@dataclass(frozen=True)
class RunSummary:
    """Everything one curation run is worth knowing about, in one immutable
    value. Field ORDER is the log record's key order — `run_id` and
    `duration_s` first, matching the shape shipped by `async-invocation-ack`.
    """

    run_id: str
    duration_s: float                       # wall clock, 1 decimal
    discovered: int                         # total raw items from all sources
    discovered_rss: int                     # rollup: non-Tavily sources
    discovered_tavily: int                  # rollup: Tavily sources
    discovered_by_source: dict[str, int]    # raw per-source counts (feed names)
    deduped: int                            # new-after-dedup, before max_items cap
    summarized: int                         # cards successfully built
    failed: int                             # items that raised during summarize
    persisted: int                          # cards handed to store.upsert()
    cards_written: int                      # persisted - store_failures (>= 0)
    input_tokens: int                       # Bedrock, summed over the run
    output_tokens: int
    tavily_searches: int                    # seed queries ATTEMPTED
    tavily_credits: int                     # searches x credits-per-depth
    discoverer_failures: int
    store_failures: int
    tavily_enabled: bool
    estimated_bedrock_cost_usd: float
    estimated_tavily_cost_usd: float
    estimated_cost_usd: float               # bedrock + tavily

    def to_dict(self) -> dict[str, Any]:
        """`dataclasses.asdict(self)` — the log-record / EMF payload. Keys are
        exactly the field names above, in this order."""


def split_by_origin(discovered_by_source: Mapping[str, int]) -> tuple[int, int]:
    """Roll per-source counts up into `(rss, tavily)`.

    A source counts as Tavily iff its label starts with
    `config.TAVILY_SOURCE_PREFIX` ("Tavily: ") — the label
    `TavilyDiscoverer.discover()` builds. Everything else (RSS feed names such
    as "arXiv cs.AI") counts as RSS. Deliberately string-based: `summary.py`
    must not import `curation.tavily` (that module imports the `tavily` SDK).
    """


def estimate_bedrock_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Design §7 Haiku pricing, from `spike_config.HAIKU_INPUT_USD_PER_1M` /
    `spike_config.HAIKU_OUTPUT_USD_PER_1M` — the SAME module as
    `HAIKU_MODEL_ID`, the model those prices price (see §4). Read at CALL time
    (module attribute, never `from ... import X`) so tests can monkeypatch the
    constants. Rounded to 6 decimals; `(0, 0) -> 0.0`."""


def estimate_tavily_cost_usd(credits: int) -> float:
    """`credits * config.TAVILY_CREDIT_PRICE_USD` (curation-plane config,
    where the rest of the Tavily knobs already live), rounded to 6 decimals.
    `0 -> 0.0`."""


def build_run_summary(
    *,
    run_id: str,
    duration_s: float,
    state: Mapping[str, Any],
    tavily_searches: int,
    tavily_credits: int,
    discoverer_failures: int,
    store_failures: int,
    tavily_enabled: bool,
) -> RunSummary:
    """Assemble a `RunSummary` from a final `CurationState` plus the
    stats only the composition root can see (discoverer/store accessors).

    `state` is read defensively with `.get(..., 0)` / `.get(..., {})` so a
    partial state (or a test's hand-built dict) never raises. Derives:
    `(discovered_rss, discovered_tavily)` via `split_by_origin`,
    `cards_written = max(persisted - store_failures, 0)`, and the three cost
    figures. `duration_s` is rounded to 1 decimal.
    """
```

### 3. Metric emission — `src/curation/metrics.py` (NEW)

Builds a **CloudWatch embedded metric format (EMF)** document and writes it as
one raw JSON line. No `boto3`, no `PutMetricData`, no IAM change: CloudWatch
Logs extracts the metrics from the log event itself.

```python
"""CloudWatch EMF emission for the run summary (Spec 06).

NOT an AWS-SDK dependency: this module builds a dict and writes a string.
The AgentCore runtime's log capture does the rest.
"""
from __future__ import annotations

import json
import sys
import time
from typing import IO

from . import config
from .summary import RunSummary

#: The four extracted metrics. Every name here costs $0.30/month, so this
#: list is deliberately short and has NO dimensions (see EMF_DIMENSIONS).
METRIC_DEFINITIONS: list[dict[str, str]] = [
    {"Name": "RunsCompleted", "Unit": "Count"},
    {"Name": "CardsWritten", "Unit": "Count"},
    {"Name": "ItemsFailed", "Unit": "Count"},
    {"Name": "EstimatedCostUsd", "Unit": "None"},   # USD is not a CW unit
]

#: One EMPTY DimensionSet: exactly 4 metrics, forever. Never add `run_id` (or
#: anything else per-run) here - the EMF spec's own warning is that EVERY
#: unique dimension combination creates a new billable custom metric.
EMF_DIMENSIONS: list[list[str]] = [[]]

EVENT_NAME = "curation_run_metrics"


def run_metrics_document(
    summary: RunSummary, *, timestamp_ms: int | None = None
) -> dict:
    """Build the EMF document for one completed run.

    Root node = `_aws` metadata + the full `summary.to_dict()` payload + the
    four PascalCase metric target members. The snake_case summary fields are
    plain log data (NOT extracted, NOT billed) and make the whole summary
    queryable as top-level fields in Logs Insights.

    `timestamp_ms` defaults to `int(time.time() * 1000)`.
    """


def emit_run_metrics(
    summary: RunSummary,
    *,
    stream: IO[str] | None = None,
    timestamp_ms: int | None = None,
) -> bool:
    """Write the EMF document as ONE raw JSON line + "\\n", then flush.

    Returns True if a line was written, False if `config.EMIT_RUN_METRICS` is
    off (the kill switch). `stream` defaults to `sys.stderr` — resolved at
    CALL time, never at import — because that is the stream the AgentCore SDK's
    own `StreamHandler` writes to, i.e. the one already proven to reach
    CloudWatch Logs. The line MUST NOT go through `logging`: the SDK's
    `RequestContextFormatter` would nest it inside a `message` string and EMF
    requires the log event to be the JSON document with nothing around it.
    """
```

Pinned EMF document shape (what a live run must produce):

```python
{
    "_aws": {
        "Timestamp": 1786492800000,                 # ms since epoch, int
        "CloudWatchMetrics": [
            {
                "Namespace": "AIRadar/Curation",    # config.METRIC_NAMESPACE
                "Dimensions": [[]],
                "Metrics": [
                    {"Name": "RunsCompleted", "Unit": "Count"},
                    {"Name": "CardsWritten", "Unit": "Count"},
                    {"Name": "ItemsFailed", "Unit": "Count"},
                    {"Name": "EstimatedCostUsd", "Unit": "None"},
                ],
            }
        ],
    },
    "event": "curation_run_metrics",
    # ... every RunSummary field, snake_case, as plain log data ...
    "run_id": "9f2c1b7e4a...", "duration_s": 31.7, "discovered": 50,
    "discovered_rss": 30, "discovered_tavily": 20,
    "discovered_by_source": {"arXiv cs.AI": 5, "Tavily: general": 20},
    "deduped": 42, "summarized": 8, "failed": 0, "persisted": 8,
    "cards_written": 8, "input_tokens": 24135, "output_tokens": 3120,
    "tavily_searches": 5, "tavily_credits": 5, "discoverer_failures": 0,
    "store_failures": 0, "tavily_enabled": True,
    "estimated_bedrock_cost_usd": 0.039735,
    "estimated_tavily_cost_usd": 0.04,
    "estimated_cost_usd": 0.079735,
    # ... the four metric target members (PascalCase, no name collisions) ...
    "RunsCompleted": 1,
    "CardsWritten": 8,
    "ItemsFailed": 0,
    "EstimatedCostUsd": 0.079735,
}
```

### 4. Config knobs — two files, split by ownership (MODIFY, additive)

The two Bedrock **unit prices** live next to the model ID they price
(`src/spike/config.py`, which already holds `HAIKU_MODEL_ID` and the rest of
the shared AWS/Bedrock config for both planes); everything else is a
curation-plane knob and stays in `src/curation/config.py` alongside the
existing Tavily/DynamoDB/secret settings. No third config module, and no
config framework: `docs/architecture-principles.md` (2026-07) defers Pydantic
adoption until `Card` needs to become a versioned API contract, so
`pydantic-settings` is explicitly declined here rather than overlooked (it is
present in the venv only as a transitive dependency of
`bedrock-agentcore` / the starter toolkit, never a chosen project dependency).

#### 4a. `src/spike/config.py` (MODIFY, additive — Bedrock unit prices)

Placed immediately after `HAIKU_MODEL_ID`. Env-var names follow that file's
own convention (bare `HAIKU_*`, like `HAIKU_MODEL_ID`), **not** the
`CURATION_*` prefix used in the curation-plane config.

```python
# Bedrock unit prices (design §7), USD per 1M tokens, for HAIKU_MODEL_ID above.
# They live HERE, with the model ID they price, so a model swap and its price
# change are one edit in one file. Consumed by curation.summary.
# estimate_bedrock_cost_usd (Spec 06); Sonnet/Titan prices are deliberately
# absent — Plane A summarizes with Haiku only (chat/embeddings are Plane B /
# Phase 3 concerns and adding their prices now would be speculative config).
HAIKU_INPUT_USD_PER_1M = float(os.getenv("HAIKU_INPUT_USD_PER_1M", "1.0"))
HAIKU_OUTPUT_USD_PER_1M = float(os.getenv("HAIKU_OUTPUT_USD_PER_1M", "5.0"))
```

`spike/config.py`'s module docstring (*"Spike configuration — env-overridable,
sensible local defaults."*) may be updated to note that it holds shared
AWS/Bedrock configuration for both planes (which it already does —
`AWS_REGION`, the model IDs, and `MAX_ITEMS` are read by `curation.*` and
`runtime_app.py` today). No other change to that file.

#### 4b. `src/curation/config.py` (MODIFY, additive — everything else)

```python
# --- Run observability (Spec 06) -----------------------------------------
# Source-label prefix TavilyDiscoverer stamps on every RawItem it produces.
# `summary.split_by_origin` classifies RSS vs Tavily by this prefix, so the
# two must stay in sync (tavily.py imports it from here).
TAVILY_SOURCE_PREFIX: str = "Tavily: "

# Tavily cost model. Tavily bills in CREDITS and its API response does NOT
# report consumption, so this is an ESTIMATE: attempted searches x credits per
# search x unit price. Basic search = 1 credit, advanced = 2 (Tavily API-credits
# docs, verified 2026-08); unknown depths ("fast"/"ultra-fast") fall back to 1.
# $0.008/credit is Tavily's public pay-as-you-go rate — override when the real
# plan is known.
TAVILY_CREDIT_PRICE_USD: float = float(
    os.getenv("CURATION_TAVILY_CREDIT_PRICE_USD", "0.008")
)
TAVILY_CREDITS_BY_DEPTH: dict[str, int] = {"basic": 1, "advanced": 2}
TAVILY_DEFAULT_CREDITS_PER_SEARCH: int = 1

# NOTE: the Bedrock unit prices are NOT here — they live in spike/config.py
# next to HAIKU_MODEL_ID, the model they price (see §4a).

# CloudWatch EMF metrics. 4 metrics x $0.30/metric-month ~= $1.20/mo; set
# CURATION_EMIT_METRICS=false to stop emitting entirely (logs still carry the
# full summary).
METRIC_NAMESPACE: str = os.getenv("CURATION_METRIC_NAMESPACE", "AIRadar/Curation")
EMIT_RUN_METRICS: bool = os.getenv("CURATION_EMIT_METRICS", "true").lower() == "true"
```

### 5. Graph state — `src/curation/state.py` (MODIFY, additive)

The `# run-level counters (run summary; consumed by Spec 06 later)` block is
the extension point named by Spec 01. Existing keys and meanings are unchanged.

```python
class CurationState(TypedDict, total=False):
    # config knobs (set at invoke time; defaults from spike.config)
    max_items: int
    run_id: str             # NEW: correlation id, echoed into every node log

    # data flowing through the pipeline (unchanged)
    raw: list[RawItem]
    fresh: list[RawItem]
    cards: list[Card]

    # run-level counters (run summary; consumed by Spec 06)
    discovered: int
    deduped: int
    summarized: int
    failed: int
    discovered_by_source: dict[str, int]   # NEW: discover -> counts per RawItem.source
    persisted: int                         # NEW: persist  -> len(cards) handed to upsert
    input_tokens: int                      # NEW: summarize -> Bedrock input tokens
    output_tokens: int                     # NEW: summarize -> Bedrock output tokens
```

No LangGraph reducers/annotations are added: every new key is written by
exactly one node, so last-write-wins merging is correct (unchanged from Spec
01).

### 6. Nodes — `src/curation/nodes.py` (MODIFY)

Still no `boto3`. Adds stdlib `json` + `logging` only.

```python
logger = logging.getLogger(__name__)     # "curation.nodes" — handlers are the
                                         # composition root's job (runtime_app
                                         # attaches the SDK's; run_curation.py
                                         # uses basicConfig)


def _log(event: str, state: CurationState, **fields) -> None:
    """One structured JSON record: `{"event": ..., "run_id": ..., **fields}`.
    `run_id` comes from the state (empty string when the caller did not set
    one). Node-level only — never per item."""


def discover_node(discoverer: Discoverer) -> NodeFn:
    """Adds: group `raw` by `RawItem.source` into `discovered_by_source`
    (no new plumbing — `CompositeDiscoverer` already concatenates per-source
    results before its cross-source dedup, and every RawItem carries `.source`).
    Emits `discover_complete`.
    Returns {"raw", "discovered", "discovered_by_source"}."""


def summarize_node(state: CurationState) -> CurationState:
    """Calls `summarize_with_usage` (not `summarize`) and accumulates
    `input_tokens` / `output_tokens`. Usage is added INSIDE the existing
    per-item try, immediately after the call returns, so tokens spent on an
    item that later fails `Card.from_model` are still billed to the run.
    The per-item failure `print(...)` becomes
    `logger.warning(json.dumps({"event": "summarize_item_failed", "run_id",
    "url", "error"}))` — bounded by `max_items`, never a per-success line.
    Emits `summarize_complete`.
    Returns {"cards", "summarized", "failed", "input_tokens", "output_tokens"}."""


def persist_node(store: CardStore) -> NodeFn:
    """Emits `persist_complete`. Returns {"persisted": len(cards)} (was `{}`)."""
```

`dedup_node` and `rank_node` are **unchanged** (no log line: their outcome is
fully described by `discover_complete` + `summarize_complete`).

### 7. Tavily / composite accessors (MODIFY, additive)

Mirrors the existing `failures()` pattern exactly — reset at the start of
`discover()`, exposed for "a caller/observer" (this spec).

```python
# src/curation/tavily.py
class TavilyDiscoverer:
    def searches(self) -> int:
        """Seed queries ATTEMPTED during the last discover() — including ones
        that raised (assume a failed search may still be charged)."""

    def credits_used(self) -> int:
        """`searches() * config.TAVILY_CREDITS_BY_DEPTH.get(self.search_depth,
        config.TAVILY_DEFAULT_CREDITS_PER_SEARCH)`. The depth→credits mapping
        lives with the Tavily adapter; the unit PRICE lives in summary.py."""


# src/curation/composite.py — stays source-agnostic (duck-typed, default 0)
class CompositeDiscoverer:
    def searches(self) -> int:
        """Sum of `source.searches()` over sources that expose it, else 0."""

    def credits_used(self) -> int:
        """Sum of `source.credits_used()` over sources that expose it, else 0."""
```

`TavilyDiscoverer.discover()` also switches its literal `f"Tavily: {topic}"`
to `f"{config.TAVILY_SOURCE_PREFIX}{self.topic}"` — **byte-identical output**,
but now one constant shared with `split_by_origin`.

### 8. Runtime entrypoint — `runtime_app.py` (MODIFY)

Everything from `async-invocation-ack` not listed here (`_resolve_tavily_key`,
`_build_store`, `_build_discoverer`, `handler`, `_background_tasks`,
`_active_run_id`, the ack shapes, `app.run()`) is **unchanged and re-asserted,
not redefined**.

```python
from curation.metrics import emit_run_metrics
from curation.summary import RunSummary, build_run_summary


def _configure_curation_logging() -> None:
    """Attach the SDK logger's handlers to the `curation` logger tree so
    node-level records (logger "curation.nodes") reach CloudWatch at INFO.

    Called once at import. Without it, `curation.*` INFO records are dropped
    (no handler anywhere on their chain; logging's lastResort only passes
    WARNING+). Infra knowledge stays HERE, in the composition root — node code
    just calls `logging.getLogger(__name__)`.
    """


def _run_curation_pipeline(run_id: str) -> RunSummary:
    """Run one full curation pass and return its RunSummary.

    BLOCKING — always called via `asyncio.to_thread`. Same body as before
    (build store + discoverer, invoke the UNCHANGED compiled graph) with three
    changes: it takes `run_id`, passes it into the graph
    (`{"max_items": config.MAX_ITEMS, "run_id": run_id}`), times itself with
    `time.monotonic()`, and returns `build_run_summary(...)` instead of the
    eight-field dict. Tavily stats come from the composite discoverer's
    `searches()` / `credits_used()`.
    """


async def _curation_run(run_id: str, task_id: int) -> None:
    """Unchanged control flow (single-flight guard, `complete_async_task` in
    `finally`, never re-raises). Two changes:

    1. `summary = await asyncio.to_thread(_run_curation_pipeline, run_id)`,
       and the success record becomes
       `logger.info(json.dumps({"event": "curation_run_complete",
       **summary.to_dict()}))` — a strict SUPERSET of the eight fields.
    2. After that record is emitted, `emit_run_metrics(summary)` runs inside
       its OWN try/except: a metrics failure logs
       `{"event": "curation_metrics_failed", "run_id": ...}` at WARNING and is
       swallowed. It must never turn a successful run into
       `curation_run_failed` (which is what would happen if it shared the
       outer try — cf. `async-invocation-ack` finding A5, which put the
       success log INSIDE the try on purpose).

    The failure path (`curation_run_failed` + stack trace, own `duration_s`
    from the outer `time.monotonic()`) is unchanged, and emits NO metrics.
    """
```

### 9. Local entrypoint — `run_curation.py` (MODIFY)

```python
# Adds: `logging.basicConfig(level=logging.INFO, format="%(message)s")` so the
# three node records print locally; a `run_id = uuid.uuid4().hex` passed into
# `graph.invoke({"max_items": ..., "run_id": run_id})`; and the ad-hoc
# `[dim]discovered=… deduped=…[/dim]` line replaced by the same
# `build_run_summary(...)` output, printing at minimum:
#   discovered (rss/tavily) · deduped · summarized · failed · cards_written
#   tokens in/out · tavily searches/credits · est. $X.XXXXXX
# `emit_run_metrics` is NOT called locally (no CloudWatch to parse it).
```

### 10. CDK construct — `infra/lib/cost_budget.py` (NEW)

```python
"""Reusable CDK construct: the AI Radar monthly cost budget + alert topic
(Spec 06: run-observability).

`infra/lib/` — NOT `infra/constructs/` — a local `constructs` package on
`sys.path` would shadow the CDK `constructs` library.
"""
from __future__ import annotations

from aws_cdk import Aws, RemovalPolicy
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from constructs import Construct

# --- The "one place" for the budget knobs (Success Criteria) ----------------
# Override per-deploy with `cdk deploy -c budget_limit_usd=... -c
# budget_thresholds_usd=... -c budget_email=...` (see CostBudgetStack).
DEFAULT_BUDGET_NAME = "ai-radar-monthly-cost"   # MUST NOT collide with the
                                                # pre-existing, hand-made
                                                # "My Monthly Cost Budget"
DEFAULT_LIMIT_USD = 250                          # == the top threshold
DEFAULT_THRESHOLDS_USD = [50, 100, 250]          # design §7, verbatim
DEFAULT_NOTIFICATION_EMAIL = "danielmauricioerazoespinoza@gmail.com"
DEFAULT_TOPIC_NAME = "ai-radar-budget-alerts"


class CostBudget(Construct):
    """Monthly COST budget with ACTUAL-spend notifications at absolute USD
    thresholds, delivered to an SNS topic with one email subscriber.

    Exposes `.budget` (budgets.CfnBudget) and `.topic` (sns.Topic).

    Two load-bearing decisions, both easy to get wrong:

    1. `include_credit=False`. The account runs on $500 of AWS credits; with
       the default cost types, credited charges are netted out and the budget
       reports ~$0 forever, so the alert that exists to protect the credits
       would never fire. Excluding credits tracks gross spend — which is
       exactly "credits can't silently drain" (design §7).
    2. The budget explicitly DEPENDS ON the SNS topic policy. AWS Budgets
       validates SNS publish permission at CreateBudget time; without the
       dependency CloudFormation may create the budget first and the deploy
       fails with an "invalid SNS topic / insufficient permission" error.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        budget_name: str = DEFAULT_BUDGET_NAME,
        limit_usd: int = DEFAULT_LIMIT_USD,
        thresholds_usd: list[int] | None = None,
        notification_email: str = DEFAULT_NOTIFICATION_EMAIL,
        topic_name: str = DEFAULT_TOPIC_NAME,
    ) -> None:
        super().__init__(scope, construct_id)
        thresholds_usd = thresholds_usd if thresholds_usd is not None else list(DEFAULT_THRESHOLDS_USD)

        # 1. Alert topic + the one real subscriber (confirmation is a human
        #    click — CDK cannot complete it; see the runbook).
        self.topic = sns.Topic(
            self, "BudgetAlerts",
            topic_name=topic_name,
            display_name="AI Radar budget alerts",
            enforce_ssl=True,
        )
        self.topic.add_subscription(subscriptions.EmailSubscription(notification_email))

        # 2. Let AWS Budgets publish, scoped by source account + this budget's
        #    ARN (a literal string — budget ARNs are region-less and the name
        #    is known at synth time, so there is no circular CFN reference).
        budget_arn = f"arn:aws:budgets::{Aws.ACCOUNT_ID}:budget/{budget_name}"
        policy_result = self.topic.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowBudgetsPublish",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("budgets.amazonaws.com")],
                actions=["sns:Publish"],
                resources=[self.topic.topic_arn],
                conditions={
                    "StringEquals": {"aws:SourceAccount": Aws.ACCOUNT_ID},
                    "ArnLike": {"aws:SourceArn": budget_arn},
                },
            )
        )

        # 3. The budget itself (L1 — aws-cdk-lib 2.261.0 ships no L2).
        self.budget = budgets.CfnBudget(
            self, "MonthlyCostBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name=budget_name,
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(amount=limit_usd, unit="USD"),
                cost_types=budgets.CfnBudget.CostTypesProperty(
                    include_credit=False,      # see docstring — load-bearing
                    include_refund=False,
                    include_discount=True,
                    include_tax=True,
                    include_subscription=True,
                    include_support=True,
                    include_upfront=True,
                    include_recurring=True,
                    include_other_subscription=True,
                    use_amortized=False,
                    use_blended=False,
                ),
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="ACTUAL",
                        comparison_operator="GREATER_THAN",
                        threshold=threshold,
                        threshold_type="ABSOLUTE_VALUE",   # dollars, not percent
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            address=self.topic.topic_arn,
                            subscription_type="SNS",
                        )
                    ],
                )
                for threshold in thresholds_usd
            ],
        )

        if policy_result.policy_dependable is not None:
            self.budget.node.add_dependency(policy_result.policy_dependable)
```

### 11. CDK stack — `infra/stacks/cost_budget_stack.py` (NEW)

```python
"""CDK stack wrapping `CostBudget` (Spec 06: run-observability)."""
from __future__ import annotations

from aws_cdk import CfnOutput, Stack
from constructs import Construct

from lib.cost_budget import (  # infra/ on sys.path via app.py
    DEFAULT_BUDGET_NAME,
    DEFAULT_LIMIT_USD,
    DEFAULT_NOTIFICATION_EMAIL,
    DEFAULT_THRESHOLDS_USD,
    CostBudget,
)


class CostBudgetStack(Stack):
    """Knobs are overridable per-deploy via CDK context:

        cdk deploy -c budget_limit_usd=500 \
                   -c budget_thresholds_usd="100,250,400" \
                   -c budget_email=someone@example.com

    Defaults (the "one place") live in lib/cost_budget.py.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        budget_name = self.node.try_get_context("budget_name") or DEFAULT_BUDGET_NAME
        email = self.node.try_get_context("budget_email") or DEFAULT_NOTIFICATION_EMAIL
        raw_limit = self.node.try_get_context("budget_limit_usd")
        limit_usd = DEFAULT_LIMIT_USD if raw_limit is None else int(raw_limit)
        # `-c budget_thresholds_usd="50,100,250"` arrives as a STRING.
        raw_thresholds = self.node.try_get_context("budget_thresholds_usd")
        thresholds = (
            list(DEFAULT_THRESHOLDS_USD)
            if raw_thresholds is None
            else [int(t.strip()) for t in str(raw_thresholds).split(",") if t.strip()]
        )

        cost_budget = CostBudget(
            self, "CostBudget",
            budget_name=budget_name,
            limit_usd=limit_usd,
            thresholds_usd=thresholds,
            notification_email=email,
        )

        CfnOutput(self, "BudgetName", value=budget_name)
        CfnOutput(self, "BudgetLimitUsd", value=str(limit_usd))
        CfnOutput(self, "BudgetThresholdsUsd", value=",".join(str(t) for t in thresholds))
        CfnOutput(self, "AlertTopicArn", value=cost_budget.topic.topic_arn)
        CfnOutput(self, "AlertEmail", value=email)
```

### 12. CDK app — `infra/app.py` (MODIFY, one stack added)

```python
from stacks.cost_budget_stack import CostBudgetStack  # noqa: E402

app = cdk.App()
CardStoreStack(app, "AiRadarCardStore")
AgentRuntimeStack(app, "AiRadarRuntimeRole")
CurationScheduleStack(app, "AiRadarSchedule")
CostBudgetStack(app, "AiRadarBudget")                 # NEW (Spec 06)
app.synth()
```

## Data Models

Three JSON shapes are pinned. Two are new; one is an **extension** of a
shipped shape.

```python
# 1. `curation_run_complete` (EXTENDED — one INFO record via
#    logging.getLogger("bedrock_agentcore.app.curation"), unchanged seam).
#    Every field shipped by `async-invocation-ack` keeps its name, type, and
#    meaning; the rest are ADDED. `persisted` still means "cards handed to
#    upsert" — the new `cards_written` is the net figure.
{
    "event": "curation_run_complete",       # literal; the grep anchor (unchanged)
    "run_id": "9f2c1b7e4a...",              # unchanged
    "duration_s": 31.7,                     # unchanged (now measured inside
                                            # _run_curation_pipeline, so it
                                            # excludes thread-scheduling ms)
    "discovered": 50,                       # unchanged
    "discovered_rss": 30,                   # NEW
    "discovered_tavily": 20,                # NEW
    "discovered_by_source": {"arXiv cs.AI": 5, "Tavily: general": 20},  # NEW
    "deduped": 42,                          # unchanged
    "summarized": 8,                        # unchanged
    "failed": 0,                            # unchanged
    "persisted": 8,                         # unchanged
    "cards_written": 8,                     # NEW (persisted - store_failures)
    "input_tokens": 24135,                  # NEW
    "output_tokens": 3120,                  # NEW
    "tavily_searches": 5,                   # NEW
    "tavily_credits": 5,                    # NEW
    "discoverer_failures": 0,               # unchanged
    "store_failures": 0,                    # unchanged
    "tavily_enabled": True,                 # unchanged
    "estimated_bedrock_cost_usd": 0.039735, # NEW
    "estimated_tavily_cost_usd": 0.04,      # NEW
    "estimated_cost_usd": 0.079735,         # NEW
}

# 2. `curation_run_metrics` — the EMF line (raw stderr, see §3 above).

# 3. Node records — one INFO line each per run, logger "curation.nodes":
{"event": "discover_complete",  "run_id": "...", "discovered": 50,
 "discovered_by_source": {...}}
{"event": "summarize_complete", "run_id": "...", "summarized": 8, "failed": 0,
 "input_tokens": 24135, "output_tokens": 3120}
{"event": "persist_complete",   "run_id": "...", "persisted": 8}
# plus, at WARNING, at most `failed` of:
{"event": "summarize_item_failed", "run_id": "...", "url": "https://…",
 "error": "…"}

# 4. `curation_run_failed` / `curation_run_accepted` — UNCHANGED from
#    async-invocation-ack. A failed run emits no summary and no metrics.
{"event": "curation_metrics_failed", "run_id": "...", "error": "..."}  # NEW, WARNING
```

**How these appear in CloudWatch (operator-visible, load-bearing):** records
1, 3 and 4 go through the SDK's `RequestContextFormatter`, so the log event is
`{"timestamp", "level", "message": "<the JSON above, as a STRING>", "logger",
"requestId", "sessionId"}` — the payload is nested one level down. Record 2
(EMF) bypasses logging and is the log event itself, so its fields are
top-level. Both pinned Logs Insights queries below account for that.

```sql
-- "failed counts for the last 7 runs" (preferred: EMF line, top-level fields)
fields @timestamp, run_id, discovered, failed, cards_written, estimated_cost_usd
| filter event = "curation_run_metrics"
| sort @timestamp desc
| limit 7

-- Same question from the logger record (works even with metrics disabled)
fields @timestamp, @message
| filter @message like /curation_run_complete/
| sort @timestamp desc
| limit 7
```

## State Changes

- **Graph state:** four additive `CurationState` keys plus `run_id` (§5). No
  reducers, no topology change; `build_graph` is byte-for-byte unchanged.
- **Process state:** none new. `runtime_app`'s `_background_tasks` /
  `_active_run_id` are untouched; `_configure_curation_logging()` mutates only
  the `curation` logger's handlers/level once at import.
- **Application data:** unchanged. No new DynamoDB item, attribute, table, or
  write path. `Card` is untouched (`docs/architecture-principles.md` §2).
- **CloudWatch state (new):** 4 custom metrics in `AIRadar/Curation` per
  successful run; ~5 extra log records per run (~2 KB).
- **CloudFormation state (new):** one stack, `AiRadarBudget` —
  `AWS::Budgets::Budget`, `AWS::SNS::Topic`, `AWS::SNS::TopicPolicy`,
  `AWS::SNS::Subscription`. `cdk diff` on `AiRadarCardStore`,
  `AiRadarRuntimeRole`, and `AiRadarSchedule` must be **empty** — in
  particular the execution role gains no permission.
- **Untouched AWS state:** the pre-existing "My Monthly Cost Budget" ($1/mo,
  hand-made). Different name ⇒ CloudFormation can neither adopt nor modify it.

## Behavior Guarantees

1. **Every successful run produces exactly one `RunSummary`**, logged as one
   `curation_run_complete` record and (unless the kill switch is off) one
   `curation_run_metrics` EMF line. A failed run produces neither — its
   `curation_run_failed` record is unchanged.
2. **The old record is a subset of the new one.** All eight
   `async-invocation-ack` fields keep their names, types and semantics; the
   README runbook and every existing assertion about them stay true.
3. **Counter identities hold.** `discovered_rss + discovered_tavily ==
   discovered == sum(discovered_by_source.values())`;
   `cards_written == max(persisted - store_failures, 0)`;
   `summarized + failed == len(fresh)` (unchanged Spec 01 identity);
   `estimated_cost_usd == estimated_bedrock_cost_usd + estimated_tavily_cost_usd`.
4. **Portability preserved.** `src/curation/{nodes,graph,state,summary,
   metrics}.py` import no `boto3`/`botocore`/`bedrock_agentcore`. The only
   Bedrock touchpoint remains `spike.bedrock`; the only CloudWatch touchpoint
   is a JSON string written to a stream. The compiled graph still lifts onto
   Lambda/Step Functions unchanged (`docs/architecture-principles.md` §5).
5. **No new IAM permission, no new AWS resource for telemetry.** Metrics ride
   the existing `logs:PutLogEvents` grant. The only new resources anywhere are
   the budget + its topic, in their own stack.
6. **Observability never breaks a run.** A missing/malformed Converse `usage`
   block yields `TokenUsage(0, 0)`; an exception while building or emitting
   metrics is caught, logged as `curation_metrics_failed`, and swallowed. No
   telemetry path can raise into the pipeline or flip a successful run to
   failed.
7. **Bounded, non-spammy output.** Per run: 3 node records + 1 run record + 1
   EMF line + at most `failed` (≤ `SPIKE_MAX_ITEMS`) warnings. No per-item
   success logging, no trace export, no sampling knobs to get wrong.
8. **Bounded metric cardinality.** `Dimensions: [[]]` and a fixed 4-name list
   mean the account can never accrue more than 4 metrics from this namespace,
   regardless of run count. `run_id` is log data, never a dimension.
9. **The kill switch is total.** `CURATION_EMIT_METRICS=false` ⇒
   `emit_run_metrics` returns `False`, writes nothing, and everything else
   (logs, counts, costs, DynamoDB) behaves identically.
10. **Cost estimates are honest and conservative.** Bedrock figures come from
    real returned token counts; Tavily figures are `attempted searches ×
    credits-per-depth × unit price` (failed seeds counted as charged) and are
    labelled *estimated* everywhere. Both price sets are env-overridable, so a
    price change is a config edit, not a code change — Bedrock prices via
    `HAIKU_*_USD_PER_1M` in `spike/config.py` (beside `HAIKU_MODEL_ID`),
    Tavily via `CURATION_TAVILY_CREDIT_PRICE_USD` in `curation/config.py`.
11. **Local/cloud parity.** `run_curation.py` builds the same `RunSummary`
    through the same `build_run_summary` and prints the same numbers (minus
    EMF, which has nothing to parse it locally).
12. **The budget is additive and inert-by-nature.** `AiRadarBudget` creates a
    *new* budget; it never touches the existing hand-made one. Deploying it
    costs $0 (AWS Budgets: first two budgets free; SNS: within free tier) and
    changes no runtime behavior.
13. **Notifications are ACTUAL-spend, absolute-dollar, credit-excluding.**
    Three notifications at exactly 50 / 100 / 250 USD, `GREATER_THAN`,
    `ABSOLUTE_VALUE`, `ACTUAL`, with `IncludeCredit: false`.
14. **Plane separation preserved.** Plane A only. No Plane B import, no
    change to `Card`, no aggregate/repository/domain-event/new-Protocol
    introduced — none of `docs/architecture-principles.md`'s triggers fires
    for adding counters and a log format. `summary.py`/`metrics.py` are plain
    modules, not a "domain layer".
15. **Tests stay 100% offline.** No new test makes an AWS, Bedrock, Tavily, or
    network call; the budget stack is asserted via `Template.from_stack`, EMF
    via a dict/`io.StringIO`, cost via arithmetic.

## Error Handling Contract

| Error Condition | Behavior | User Impact |
|---|---|---|
| Converse response has no `usage` block (or non-int values) | `summarize_with_usage` returns `TokenUsage(0, 0)`; run continues | Cost under-reported for that item; run unaffected |
| `summarize_with_usage` raises for one item | Unchanged Spec 01 semantics: counted in `failed`, skipped, loop continues; now logged as `summarize_item_failed` (WARNING, with url + error) instead of `print` | Run completes with fewer cards; the failure is greppable and counted |
| `build_run_summary` receives a partial/empty state (e.g. a node never ran) | Defensive `.get(...)` defaults ⇒ zeros/empty dict, no `KeyError` | Summary shows zeros rather than crashing the run |
| `emit_run_metrics` raises (non-serializable value, closed stream) | Caught in `_curation_run`'s dedicated try; logged `curation_metrics_failed` (WARNING); run still reports `curation_run_complete` | Metrics gap for that run; cards and logs unaffected |
| `CURATION_EMIT_METRICS=false` | No EMF line; `emit_run_metrics` returns `False` | Metrics stop; logs still carry the full summary |
| CloudWatch fails to parse the EMF document | Failure surfaces as datapoints in the `AWS/Logs` namespace; no run impact | Metrics missing; log line still present and readable. Fallback: kill switch + logs-only |
| AgentCore does not forward raw stderr writes as their own log events | Detectable only by live fire (roadmap Phase 5): no `AIRadar/Curation` metrics appear | Fall back to `CURATION_EMIT_METRICS=false`; the logs already satisfy the "retrievable after the fact" criterion |
| Tavily disabled (no key / sentinel) | `searches()`/`credits_used()` sum to 0; `estimated_tavily_cost_usd == 0.0`; `discovered_tavily == 0` | Cost line correctly shows Bedrock only |
| A Tavily seed query raises | Already counted in `failures()`; **still counted** in `searches()`/credits (conservative) | Slight cost over-estimate rather than a blind spot |
| Zero items discovered / zero summarized | All counters 0, both cost figures `0.0`; EMF still emitted with `RunsCompleted: 1` | "The run happened and did nothing" is distinguishable from "no run happened" |
| The whole pipeline raises | Unchanged: `curation_run_failed` + stack trace, guard released, **no** summary, **no** metrics | Absence of a `RunsCompleted` datapoint is the signal (an alarm hook for later, not built here) |
| `cdk deploy AiRadarBudget` fails: budget created before the topic policy | Prevented by the explicit `node.add_dependency(policy_dependable)`; if it ever recurs, the deploy fails loudly at CreateBudget | Deploy-time error, no partial telemetry loss |
| Email subscription never confirmed | SNS drops notifications silently; the budget still records the breach | **Only** detectable by the live-fire `aws sns publish` check + the confirmation click — a mandatory runbook step |
| A budget notification fires on the *pre-existing* "My Monthly Cost Budget" | Out of scope, untouched, unrelated | Two budgets in the console; only `ai-radar-monthly-cost` is CDK-managed |

## Dependencies

- **Internal (imported, extended, never forked):**
  `spike.bedrock` (`summarize`, `bedrock_client`, `CARD_TOOL`, `SYSTEM`),
  `spike.cards.Card`, `spike.feeds.RawItem`, `spike.config`
  (`HAIKU_MODEL_ID`, `MAX_ITEMS`, `AWS_REGION` — plus the two price constants
  this spec ADDS there: `HAIKU_INPUT_USD_PER_1M`, `HAIKU_OUTPUT_USD_PER_1M`,
  imported by `curation.summary` as `spike_config`), `curation.config`
  (Tavily prices/credit map, `TAVILY_SOURCE_PREFIX`, `METRIC_NAMESPACE`,
  `EMIT_RUN_METRICS`), `curation.interfaces` (unchanged Protocols),
  `curation.graph.build_graph`
  (unchanged), `curation.composite.CompositeDiscoverer`,
  `curation.tavily.TavilyDiscoverer`, `curation.dynamo.DynamoCardStore`.
- **New internal modules:** `curation.summary`, `curation.metrics`.
- **External runtime:** none added. `bedrock-agentcore>=1.18.1`, `boto3>=1.35`,
  `langgraph>=1.2.9`, `tavily-python>=0.7.26` unchanged; `json`, `logging`,
  `sys`, `time`, `uuid`, `dataclasses` are stdlib ⇒ `pyproject.toml` and
  `uv.lock` are untouched and the container's dependency layer is identical.
- **External infra:** `aws-cdk-lib>=2.261.0` — `aws_budgets` (`CfnBudget`,
  `BudgetDataProperty`, `SpendProperty`, `CostTypesProperty`,
  `NotificationProperty`, `NotificationWithSubscribersProperty`,
  `SubscriberProperty`), `aws_sns` (`Topic`), `aws_sns_subscriptions`
  (`EmailSubscription`), `aws_iam` (`PolicyStatement`, `ServicePrincipal`) —
  all already in the `infra` dependency group.
- **Dev/test:** `pytest>=9.1.1`, `moto>=5.2.2` (existing DynamoDB fixtures
  only). No `pytest-asyncio`, no new dev dependency.

## Integration Points

- **`async-invocation-ack`** — extends its `_run_curation_pipeline` /
  `_curation_run` / `curation_run_complete` seam without changing the ack
  shapes, the single-flight guard, or the async-task bookkeeping. Its
  `_run_curation_pipeline()` becomes `_run_curation_pipeline(run_id)` returning
  `RunSummary`; `tests/test_runtime_app.py` T8/T12 must be updated to the
  superset shape (they are the guardrail that Guarantee 2 is real).
- **`curation-graph` (Spec 01)** — uses the `CurationState` extension point it
  reserved; node topology, Protocols, and `build_graph` are unchanged.
- **`tavily-discovery` (Spec 02)** — adds `searches()`/`credits_used()`
  alongside the existing `failures()` and swaps one string literal for a
  shared constant; discovery behavior is byte-identical.
- **`dynamodb-card-store` (Spec 03)** — consumes `store.failures()` for
  `cards_written`; no schema, key, or write-path change.
- **`eventbridge-schedule` (Spec 05)** — unchanged. Its DLQ alarm idea stays
  a Non-Goal; its `RuntimeSessionId` (`ai-radar-scheduled-curation-run-id-
  <execution-id>`) remains the second correlation key alongside `run_id`.
- **`runtime-packaging` (Spec 04)** — the execution role is unchanged
  (Guarantee 5); a redeploy (`agentcore deploy`) is required for the new
  records to appear, and the `execution_role: null` teardown gotcha still
  applies.
- **`README.md`** — new spec-table row, a Phase-1 "run observability" section
  (the two Insights queries, the metric list, the budget deploy/confirm/
  teardown runbook), and the Definition-of-done checkbox this spec closes.
- **`.env.example`** — documents the five new knobs.
- **Phase 2 / Phase 5** — the `AIRadar/Curation` metrics are the alarm surface
  a later spec can attach to, and the run records are the baseline AgentCore
  Evaluations will be compared against. Neither is built here.

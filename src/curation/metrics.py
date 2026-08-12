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
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)

    payload = summary.to_dict()

    doc: dict = {
        "_aws": {
            "Timestamp": timestamp_ms,
            "CloudWatchMetrics": [
                {
                    "Namespace": config.METRIC_NAMESPACE,
                    "Dimensions": EMF_DIMENSIONS,
                    "Metrics": METRIC_DEFINITIONS,
                }
            ],
        },
        "event": EVENT_NAME,
        **payload,
        "RunsCompleted": 1,
        "CardsWritten": summary.cards_written,
        "ItemsFailed": summary.failed,
        "EstimatedCostUsd": summary.estimated_cost_usd,
    }
    return doc


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
    if not config.EMIT_RUN_METRICS:
        return False

    if stream is None:
        stream = sys.stderr

    doc = run_metrics_document(summary, timestamp_ms=timestamp_ms)
    stream.write(json.dumps(doc) + "\n")
    stream.flush()
    return True

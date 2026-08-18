"""Tests for `src/curation/summary.py` (RunSummary + cost math) and
`src/curation/metrics.py` (CloudWatch EMF document + emission).

Spec: specs/run-observability/contract.md §2 ("Run summary + cost math"), §3
("Metric emission"); Behavior Guarantees 1, 3, 6, 7-9, 10, 15; Error Handling
Contract rows for `build_run_summary`/`emit_run_metrics`;
specs/run-observability/audit.md Test Coverage T4-T13.

Pure logic + a raw-JSON-line writer — no boto3, no CloudWatch, no network.
`emit_run_metrics` is always exercised against an injected `io.StringIO`
stream (never the real `sys.stderr`, except in the one test that verifies the
CALL-time default resolution).

RED phase: `src/curation/summary.py` and `src/curation/metrics.py` do not
exist yet. Every test in this file is expected to fail at collection with
`ModuleNotFoundError: No module named 'curation.summary'` (or
`'curation.metrics'`) until specs/run-observability Phase 1 lands.
"""
from __future__ import annotations

import dataclasses
import io
import json
import logging
import sys

import pytest

from curation import config as curation_config
from curation import metrics as metrics_module
from curation import summary as summary_module
from curation.metrics import (
    EMF_DIMENSIONS,
    METRIC_DEFINITIONS,
    emit_run_metrics,
    run_metrics_document,
)
from curation.summary import (
    RunSummary,
    build_run_summary,
    estimate_bedrock_cost_usd,
    estimate_tavily_cost_usd,
    split_by_origin,
)


def _pinned_summary() -> RunSummary:
    """A self-consistent `RunSummary` (satisfies every Guarantee-3 identity)
    used across the EMF-shape tests below."""
    return RunSummary(
        run_id="test-run-id-123",
        duration_s=31.7,
        discovered=50,
        discovered_rss=30,
        discovered_tavily=20,
        discovered_by_source={"arXiv cs.AI": 30, "Tavily: general": 20},
        deduped=42,
        summarized=8,
        failed=0,
        persisted=8,
        cards_written=8,
        input_tokens=24135,
        output_tokens=3120,
        tavily_searches=5,
        tavily_credits=5,
        discoverer_failures=0,
        store_failures=0,
        tavily_enabled=True,
        estimated_bedrock_cost_usd=0.039735,
        estimated_tavily_cost_usd=0.04,
        estimated_cost_usd=0.079735,
    )


# =============================================================================
# T4/T5 — cost math: pure arithmetic over the env-overridable price constants.
# =============================================================================


def test_estimate_bedrock_cost_usd_matches_design_prices_and_zero_case():
    assert estimate_bedrock_cost_usd(0, 0) == 0.0
    # design §7 defaults: Haiku $1/1M in, $5/1M out.
    assert estimate_bedrock_cost_usd(24135, 3120) == pytest.approx(0.039735)


def test_estimate_bedrock_cost_usd_reads_prices_from_spike_config_at_call_time(monkeypatch):
    monkeypatch.setattr(summary_module.shared_config, "HAIKU_INPUT_USD_PER_1M", 2.0)
    monkeypatch.setattr(summary_module.shared_config, "HAIKU_OUTPUT_USD_PER_1M", 10.0)

    assert estimate_bedrock_cost_usd(1_000_000, 1_000_000) == pytest.approx(12.0)


def test_estimate_tavily_cost_usd_matches_price_and_zero_case():
    assert estimate_tavily_cost_usd(0) == 0.0
    # default $0.008/credit
    assert estimate_tavily_cost_usd(5) == pytest.approx(0.04)


def test_estimate_tavily_cost_usd_reads_price_from_curation_config_at_call_time(monkeypatch):
    monkeypatch.setattr(summary_module.config, "TAVILY_CREDIT_PRICE_USD", 0.1)

    assert estimate_tavily_cost_usd(10) == pytest.approx(1.0)


# =============================================================================
# T6 — split_by_origin
# =============================================================================


def test_split_by_origin_splits_tavily_prefixed_sources_from_everything_else():
    counts = {"arXiv cs.AI": 5, "Hugging Face Blog": 25, "Tavily: general": 20}
    assert split_by_origin(counts) == (30, 20)


def test_split_by_origin_empty_mapping_returns_zero_zero():
    assert split_by_origin({}) == (0, 0)


def test_summary_module_does_not_import_the_tavily_sdk_or_curation_tavily():
    """contract.md §2: `split_by_origin` classifies by string prefix
    specifically so `summary.py` never has to import `curation.tavily` (which
    itself imports the `tavily` SDK)."""
    import ast
    from pathlib import Path

    path = Path(__file__).parent.parent / "src" / "curation" / "summary.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert "tavily" not in roots


# =============================================================================
# T7/T8 — build_run_summary
# =============================================================================


def test_build_run_summary_full_state_satisfies_counter_identities_and_cost_sum():
    state = {
        "discovered": 50,
        "discovered_by_source": {"arXiv cs.AI": 30, "Tavily: general": 20},
        "deduped": 42,
        "summarized": 8,
        "failed": 0,
        "persisted": 8,
        "input_tokens": 24135,
        "output_tokens": 3120,
    }

    result = build_run_summary(
        run_id="test-run-id",
        duration_s=31.732,
        state=state,
        tavily_searches=5,
        tavily_credits=5,
        discoverer_failures=0,
        store_failures=0,
        tavily_enabled=True,
    )

    assert result.discovered_rss + result.discovered_tavily == result.discovered == 50
    assert result.discovered == sum(result.discovered_by_source.values())
    assert result.cards_written == max(result.persisted - 0, 0) == 8
    assert result.estimated_cost_usd == pytest.approx(
        result.estimated_bedrock_cost_usd + result.estimated_tavily_cost_usd
    )
    assert result.duration_s == 31.7  # rounded to 1 decimal


def test_build_run_summary_clamps_cards_written_at_zero_when_store_failures_exceed_persisted():
    result = build_run_summary(
        run_id="r",
        duration_s=1.0,
        state={"persisted": 3},
        tavily_searches=0,
        tavily_credits=0,
        discoverer_failures=0,
        store_failures=10,
        tavily_enabled=False,
    )

    assert result.cards_written == 0


# T8 (Error Handling Contract: "build_run_summary receives a partial/empty
# state ... Defensive .get(...) defaults => zeros/empty dict, no KeyError").
def test_build_run_summary_on_empty_state_returns_zeros_without_raising():
    result = build_run_summary(
        run_id="r",
        duration_s=0.0,
        state={},
        tavily_searches=0,
        tavily_credits=0,
        discoverer_failures=0,
        store_failures=0,
        tavily_enabled=False,
    )

    assert result.discovered == 0
    assert result.discovered_rss == 0
    assert result.discovered_tavily == 0
    assert result.discovered_by_source == {}
    assert result.deduped == 0
    assert result.summarized == 0
    assert result.failed == 0
    assert result.persisted == 0
    assert result.cards_written == 0
    assert result.input_tokens == 0
    assert result.output_tokens == 0
    assert result.tavily_enabled is False
    assert result.estimated_bedrock_cost_usd == 0.0
    assert result.estimated_tavily_cost_usd == 0.0
    assert result.estimated_cost_usd == 0.0


# =============================================================================
# T9 — RunSummary shape: to_dict() key order + immutability
# =============================================================================


def test_run_summary_to_dict_keys_match_pinned_order():
    summary = _pinned_summary()
    assert list(summary.to_dict().keys()) == [
        "run_id",
        "duration_s",
        "discovered",
        "discovered_rss",
        "discovered_tavily",
        "discovered_by_source",
        "deduped",
        "summarized",
        "failed",
        "persisted",
        "cards_written",
        "input_tokens",
        "output_tokens",
        "tavily_searches",
        "tavily_credits",
        "discoverer_failures",
        "store_failures",
        "tavily_enabled",
        "estimated_bedrock_cost_usd",
        "estimated_tavily_cost_usd",
        "estimated_cost_usd",
    ]


def test_run_summary_is_immutable():
    summary = _pinned_summary()
    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.discovered = 999  # type: ignore[misc]


# =============================================================================
# T10/T11 — EMF document shape + the cardinality guard
# =============================================================================


def test_run_metrics_document_matches_pinned_emf_shape():
    summary = _pinned_summary()
    doc = run_metrics_document(summary, timestamp_ms=1786492800000)

    assert doc["_aws"] == {
        "Timestamp": 1786492800000,
        "CloudWatchMetrics": [
            {
                "Namespace": curation_config.METRIC_NAMESPACE,
                "Dimensions": metrics_module.EMF_DIMENSIONS,
                "Metrics": metrics_module.METRIC_DEFINITIONS,
            }
        ],
    }
    assert doc["event"] == "curation_run_metrics"

    # Every RunSummary field is present at the root, as plain (non-billed) log data.
    for key, value in summary.to_dict().items():
        assert doc[key] == value

    # The four metric target members: PascalCase, no name collisions with the
    # snake_case summary payload.
    assert doc["RunsCompleted"] == 1
    assert doc["CardsWritten"] == summary.cards_written
    assert doc["ItemsFailed"] == summary.failed
    assert doc["EstimatedCostUsd"] == summary.estimated_cost_usd

    # The document has EXACTLY these keys — no stray fields, none missing.
    expected_keys = {"_aws", "event", "RunsCompleted", "CardsWritten", "ItemsFailed", "EstimatedCostUsd"}
    expected_keys |= set(summary.to_dict().keys())
    assert set(doc.keys()) == expected_keys


def test_run_metrics_document_defaults_timestamp_to_now_when_unset():
    import time

    before = int(time.time() * 1000)
    doc = run_metrics_document(_pinned_summary())
    after = int(time.time() * 1000)

    assert before <= doc["_aws"]["Timestamp"] <= after


# T11 (Behavior Guarantee 8, roadmap Risk "Metric emission silently doubles
# the account's custom-metric bill via dimensions" — the regression guard the
# risk table explicitly asks for).
def test_emf_dimensions_and_metric_definitions_are_bounded_by_contract():
    assert EMF_DIMENSIONS == [[]]
    assert len(METRIC_DEFINITIONS) == 4
    assert {m["Name"] for m in METRIC_DEFINITIONS} == {
        "RunsCompleted",
        "CardsWritten",
        "ItemsFailed",
        "EstimatedCostUsd",
    }


# =============================================================================
# T12/T13 — emit_run_metrics
# =============================================================================


def test_emit_run_metrics_writes_exactly_one_valid_json_line_ending_in_newline():
    summary = _pinned_summary()
    stream = io.StringIO()

    result = emit_run_metrics(summary, stream=stream, timestamp_ms=1786492800000)

    assert result is True
    raw = stream.getvalue()
    assert raw.endswith("\n")
    assert raw.count("\n") == 1
    parsed = json.loads(raw[:-1])
    assert parsed["event"] == "curation_run_metrics"
    assert parsed == run_metrics_document(summary, timestamp_ms=1786492800000)


def test_emit_run_metrics_respects_the_kill_switch(monkeypatch):
    summary = _pinned_summary()
    stream = io.StringIO()
    monkeypatch.setattr(metrics_module.config, "EMIT_RUN_METRICS", False)

    result = emit_run_metrics(summary, stream=stream)

    assert result is False
    assert stream.getvalue() == ""


# Constraint: "The line MUST NOT go through logging" — a future "tidy this
# into a logger call" change would silently kill EMF; this test would catch it.
def test_emit_run_metrics_never_touches_the_logging_module(caplog):
    summary = _pinned_summary()
    stream = io.StringIO()

    with caplog.at_level(logging.DEBUG):
        emit_run_metrics(summary, stream=stream)

    assert caplog.records == []


# Contract: "`stream` defaults to `sys.stderr` — resolved at CALL time, never
# at import" — a `def emit_run_metrics(..., stream=sys.stderr)` default-arg
# bug would bind the ORIGINAL stderr object at import time and this test
# (which swaps `sys.stderr` before calling) would fail to see the write.
def test_emit_run_metrics_default_stream_is_resolved_at_call_time_not_import_time(monkeypatch):
    summary = _pinned_summary()
    capture = io.StringIO()
    monkeypatch.setattr(sys, "stderr", capture)

    result = emit_run_metrics(summary)

    assert result is True
    assert capture.getvalue().endswith("\n")

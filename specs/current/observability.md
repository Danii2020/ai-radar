# Observability Specification

> Last synced: 2026-09-17. Owned artifacts: `src/curation/summary.py`,
> `src/curation/metrics.py`, `infra/lib/cost_budget.py`, `infra/stacks/cost_budget_stack.py`.

## Purpose

What a curation run reports about itself — counts, tokens, estimated cost —
and where that data goes (CloudWatch logs, CloudWatch EMF custom metrics,
an AWS Budget). Its own capability because telemetry is cross-cutting over
`curation-pipeline` and `runtime-deployment` without changing either's
behavior, and because "observability must never break a run" is a guarantee
specific to this concern.

## Requirements

### Requirement: OB-1 — RunSummary is a superset, never a replacement

Every successful run SHALL produce exactly one `RunSummary`, logged as one
`curation_run_complete` record whose fields are a strict superset of the
prior (`runtime-deployment` RD-6) record — no existing field renamed or
removed.

**Source:** run-observability · contract.md § Behavior Guarantees 1, 2

### Requirement: OB-2 — Bounded-cardinality EMF metrics

The system SHALL emit exactly 4 named CloudWatch EMF custom metrics per run
(namespace `AIRadar/Curation`: `RunsCompleted`, `CardsWritten`,
`ItemsFailed`, `EstimatedCostUsd`), with no per-run dimension — so the
namespace can never accrue more than 4 metrics regardless of run count. A
`CURATION_EMIT_METRICS=false` kill switch SHALL stop emission entirely while
leaving every other behavior identical.

**Source:** run-observability · contract.md § Behavior Guarantees 8, 9

### Requirement: OB-3 — Telemetry can never break a run

A missing/malformed token-usage block SHALL yield a zeroed `TokenUsage`; any
exception while building or emitting metrics SHALL be caught, logged as
`curation_metrics_failed`, and swallowed — no telemetry path may raise into
the pipeline or flip a successful run to failed.

**Source:** run-observability · contract.md § Behavior Guarantees 6

#### Scenario: Bedrock returns a malformed usage block
- **WHEN** the Converse API response's `usage` field is missing or not a
  mapping
- **THEN** the run still completes successfully with `TokenUsage(0, 0)`,
  never raising

### Requirement: OB-4 — Cost budget is additive and inert by design

The system SHALL provision a CDK-managed monthly AWS Budget
(`ai-radar-monthly-cost`) with `ACTUAL`/`GREATER_THAN`/`ABSOLUTE_VALUE`
notifications at exactly 50/100/250 USD via SNS email, `IncludeCredit:
false`, entirely separate from and never modifying any pre-existing
hand-made budget.

**Source:** run-observability · contract.md § Behavior Guarantees 12, 13

## Invariants

1. Cost figures are estimates, not invoices: Bedrock figures come from real
   returned token counts; Tavily figures are `attempted searches ×
   credits-per-depth × unit price` (both price sets env-overridable) — treat
   `estimated_cost_usd` as a budgeting signal (run-observability BG10).
2. No new IAM permission or AWS resource is needed for metrics beyond the
   existing `logs:PutLogEvents` grant; only the budget stack adds new
   resources (run-observability BG5).

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| RO-1 | `CURATION_EMIT_METRICS=false` (the metrics kill switch) was never actually exercised live in production — covered by an offline test only. | LOW | `specs/archived/run-observability/audit.md` |
| RO-2 | No unattended/scheduled run has ever produced these records — only manual invokes. Depends on `scheduling`'s ES-2. | MEDIUM (operational) | `specs/archived/run-observability/audit.md` |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| run-observability | 2026-08-12 | `RunSummary`, 4 CloudWatch EMF metrics (namespace `AIRadar/Curation`), the `AiRadarBudget` CDK stack. |

## Related ADRs

None yet — shipped before `harny-adr` existed in this project.

# Scheduling Specification

> Last synced: 2026-09-17. Owned artifacts: `infra/lib/curation_schedule.py`,
> `infra/stacks/curation_schedule_stack.py`.

## Purpose

Automating the manual `agentcore invoke` into a daily unattended trigger via
`EventBridge Scheduler`, which has no native target for Bedrock AgentCore
Runtime. Its own capability because the `Universal` target's wire format,
timeout behavior, and failure-surfacing (DLQ) are entirely infra-side
concerns, independent of what the Runtime entrypoint itself does
(`runtime-deployment`).

## Requirements

### Requirement: SC-1 — Daily schedule, inert by default

The system SHALL provision a daily `EventBridge Scheduler` schedule
targeting the deployed Runtime agent via the generic `Universal` target
(no native AgentCore Runtime target exists), synthesized with
`State: "DISABLED"` — deploying the stack SHALL start no recurring cost;
enabling the cadence is a deliberate, separate action.

**Source:** eventbridge-schedule · contract.md § Behavior Guarantees 1, 3

### Requirement: SC-2 — Least privilege, scoped trust

The Scheduler role's policy SHALL contain exactly two statements
(`bedrock-agentcore:InvokeAgentRuntime` on the one agent ARN, and
`sqs:SendMessage` on the DLQ ARN) with no `Resource: "*"` anywhere in the
stack, and SHALL be assumable only by `scheduler.amazonaws.com` under
`aws:SourceAccount`/`aws:SourceArn` conditions.

**Source:** eventbridge-schedule · contract.md § Behavior Guarantees 5, 6

### Requirement: SC-3 — Failures are retried, then surfaced via DLQ

A failing invocation SHALL be retried up to 3 times within a 2-hour max
event age; if every attempt fails, Scheduler SHALL deliver the event to a
dead-letter queue. A non-empty DLQ is the intended machine-readable "a
scheduled run did not happen" signal.

**Source:** eventbridge-schedule · contract.md § Behavior Guarantees 7

#### Scenario: A scheduled fire fails every retry
- **WHEN** all 3 retry attempts against the Runtime agent fail
- **THEN** the failed event lands in `ai-radar-schedule-dlq`, giving
  observability a non-empty-DLQ signal to alarm on

### Requirement: SC-4 — Double-fire cannot duplicate cards

A duplicated or retried fire SHALL never create a second card for an
already-curated URL — `card_id` is derived from the URL and dedup/upsert
(`card-persistence` PS-1/PS-2) excludes already-stored items before
summarizing.

**Source:** eventbridge-schedule · contract.md § Behavior Guarantees 8

## Invariants

1. An empty DLQ alone does NOT prove single delivery — a delivery can be
   retried and re-run the full pipeline without ever exhausting retries into
   the DLQ. `AWS/Scheduler`'s `TargetErrorCount` metric is the only
   authoritative single-delivery signal (eventbridge-schedule audit finding
   F5, resolved by `runtime-deployment`'s RD-4).

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| ES-1 | The prescribed double-fire dedup drill (does a genuine double-*delivery* skip re-curating an already-stored URL) has never been run as its own test — only incidentally observed during the original F5 bug, where the two runs happened to curate disjoint URLs with zero overlap. | MEDIUM | `specs/archived/eventbridge-schedule/audit.md`; restated in `specs/archived/run-observability/audit.md`'s close-out table |
| ES-2 | The daily cadence has never run unattended — the schedule stays `DISABLED`; every fire to date has been a manual one-shot. | MEDIUM (operational, deliberate) | `specs/archived/eventbridge-schedule/audit.md`; `README.md` "Current live AWS state" |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| eventbridge-schedule | 2026-08-10 | Daily `EventBridge Scheduler` schedule via the `Universal` target, DLQ, least-privilege scoped role, deploy-`DISABLED` default. |

## Related ADRs

None yet — shipped before `harny-adr` existed in this project.

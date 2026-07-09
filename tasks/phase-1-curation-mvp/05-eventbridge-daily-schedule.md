# Spec 05 — EventBridge daily schedule

- **feature-name:** `eventbridge-schedule`
- **SDD target dir:** `specs/eventbridge-schedule/`
- **Depends on:** Spec 04 (deployed Runtime agent)
- **Layer:** Infra (scheduling)

## Intent

Make the feed truly **automated**: an **EventBridge Scheduler** rule invokes the
deployed Runtime curation agent once a day, with no human in the loop. This closes
Phase 1 — the "Automated daily feed" deliverable from design §8.

## Background

Design §3/§5: "EventBridge Scheduler triggers the AgentCore Runtime endpoint" on a
schedule (every 6–24 h). The pipeline is idempotent (Spec 03 dedup), so an occasional
double-fire is harmless. Cadence decision for Phase 1: **daily** (see README
scoping table).

## Scope

**In scope**
- An **EventBridge Scheduler** schedule (CDK Python) that invokes the Spec 04
  Runtime agent on a daily cron/rate expression, with the schedule expression and
  timezone configurable (default: once daily, off-peak).
- A **scheduler invoke IAM role** with permission to invoke *only* that Runtime
  agent — least privilege, no wildcards.
- A **flexible time window / retry policy** appropriate for a non-latency-sensitive
  batch job (the daily run can drift a few minutes; configure a sane retry + a
  dead-letter target or logged failure).
- Define the invocation **payload** the schedule sends (e.g. `{"trigger":
  "scheduled", "max_items": N}`) matching the Spec 04 entrypoint contract.
- A documented **manual trigger** path (invoke the schedule's target on demand, or
  a one-liner to invoke the agent) for testing without waiting for the cron.
- Wire it into the same CDK app/stack as Spec 03's table and Spec 04's role so the
  whole Phase 1 infra deploys and tears down together.

**Out of scope**
- The Runtime agent itself (Spec 04).
- Alerting/metrics on run health (Spec 06 — but emit enough for that to hook into).
- Multiple cadences / per-topic schedules (later, if needed).

## Acceptance criteria

- [ ] A daily EventBridge Scheduler schedule exists in CDK and, once deployed,
      invokes the Runtime curation agent automatically.
- [ ] After a scheduled (or manually triggered) fire, new cards appear in DynamoDB
      with no human action.
- [ ] The scheduler's IAM role can invoke only the specific Runtime agent.
- [ ] Cadence + timezone are configurable in one place (CDK context/env).
- [ ] A double-fire produces no duplicate cards (idempotency holds end-to-end).
- [ ] Failed invocations are retried per policy and surfaced (DLQ or logged),
      not silently dropped.
- [ ] Teardown removes the schedule cleanly.

## SDD note

Feed to `sdd-architect` as `eventbridge-schedule`. Confirm current EventBridge
**Scheduler** (not legacy `events` rules) target config for invoking an AgentCore
Runtime agent via **Context7 MCP** before authoring the contract.

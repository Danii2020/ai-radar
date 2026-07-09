# Spec 06 — Run observability

- **feature-name:** `run-observability`
- **SDD target dir:** `specs/run-observability/`
- **Depends on:** Specs 01–05 (a deployed, scheduled pipeline)
- **Layer:** Cross-cutting

## Intent

Make each daily run **legible and cost-aware**: structured logs plus a per-run
summary (volume, failures, token usage / estimated cost) so you can answer "did
last night's run work, how much did it cost, and is anything drifting?" without
SSH-ing into anything. This is the lightweight, free-tier-respecting slice of the
design's observability story (§4, §7) — *not* AgentCore Evaluations (that's Phase 5).

## Background

Design §7 stresses cost discipline and an **AWS Budget alert at $50/$100/$250**.
Research §2.8/§5: AgentCore Observability has **no free tier** — sample heavily.
The spike currently just prints counts to the console; Phase 1 needs those counts
captured durably for an unattended job.

## Scope

**In scope**
- A `RunSummary` produced by every graph invocation, capturing at least:
  discovered (broken out by source: RSS vs Tavily), new-after-dedup, summarized-ok,
  failed, cards-written, wall-clock, Bedrock token usage (input/output), **Tavily
  search/credit usage**, and an estimated USD cost using the design §7 unit prices
  (Bedrock + Tavily).
- **Structured (JSON) logging** from the Runtime entrypoint and key graph nodes,
  emitted to CloudWatch Logs — queryable via Logs Insights.
- Persist the `RunSummary` somewhere queryable: either a CloudWatch **custom metric**
  namespace (e.g. `AIRadar/Curation`) and/or a small `runs` record in DynamoDB
  (architect picks; metrics preferred for alarming).
- An **AWS Budgets** alarm (or CloudWatch billing alarm) at the $50/$100/$250
  thresholds from §7, defined in CDK.
- Token-usage capture threaded through the existing `bedrock.summarize` call path
  (Converse responses include usage) without disturbing the Spec 01 portability
  rule — keep it behind the same injection seam.
- Keep it cheap: no per-item trace export; summary + sampled logs only.

**Out of scope**
- AgentCore Evaluations / answer-quality scoring (Phase 5).
- Dashboards/UI (a Logs Insights query + the budget alarm is enough for MVP).
- Alerting integrations (Slack/email beyond the native Budgets notification).

## Acceptance criteria

- [ ] Every run emits one structured `RunSummary` with the counters above and an
      estimated cost.
- [ ] Logs are JSON and queryable in CloudWatch Logs Insights (e.g. "show failed
      counts for the last 7 runs").
- [ ] Run summaries are retrievable after the fact (metric or `runs` table).
- [ ] A Budgets/billing alarm at $50/$100/$250 is provisioned in CDK.
- [ ] Token/cost capture does not add AWS-infra imports to Spec 01 node code
      (portability preserved).
- [ ] Observability cost stays negligible (no full-trace export).

## SDD note

Feed to `sdd-architect` as `run-observability`. This spec is the natural place for
the final **Phase 1 `sdd-auditor`** pass to confirm the whole pipeline meets the
README "Definition of done." Keep scope tight — resist building dashboards.

# Intent: run-observability

## Problem Statement

Since `async-invocation-ack`, the daily curation run is genuinely unattended:
EventBridge Scheduler fires, the agent acks in <1 s, and the pipeline runs in
the background. The **only** durable evidence a run happened is one
`curation_run_complete` CloudWatch record carrying eight counts
(`discovered`, `deduped`, `summarized`, `failed`, `persisted`,
`discoverer_failures`, `store_failures`, `tavily_enabled`).

That is enough to answer *"did it work?"* and nothing else. Today nobody can
answer, without hand-arithmetic or a trip to Cost Explorer:

- **"What did last night's run cost?"** — no token counts are captured at all.
  `spike.bedrock.summarize()` throws away the Converse response's `usage`
  block; Tavily search/credit consumption is never counted.
- **"Where did the items come from?"** — `discovered: 50` merges RSS and
  Tavily. If Tavily silently degrades (bad key, quota exhausted, seeds
  returning nothing) the total barely moves, because RSS still delivers ~30
  items. The `tavily_enabled` flag only says a key *resolved*, not that search
  *worked*.
- **"Is anything drifting?"** — `failed` counts exist per run but there is no
  metric to graph or alarm on, so drift is only visible to someone who greps
  the same log group by hand every morning.
- **"Are the $500 credits draining?"** — nothing watches the AWS bill.
  Design §7's explicit instruction is *"Set an AWS Budget alert at
  \$50/\$100/\$250 so credits can't silently drain."* The account has exactly
  one budget today: an unrelated, hand-made **"My Monthly Cost Budget"**
  ($1/mo, not CDK-managed, not ours to touch).

Who is affected: the operator (owns a job that spends real money on a
schedule and has no cost feedback loop, and no guardrail if a bug turns a
bounded 8-item slice into a runaway), Phase 1's own **Definition of done**
(README: *"Each run emits structured logs + a run-summary (counts,
tokens/cost) to CloudWatch"* — the one unchecked box), and Phase 5 (AgentCore
Evaluations needs a baseline of run-level facts to compare against).

This spec is the lightweight, free-tier-respecting slice of design §4/§7's
observability story. It threads through the seams the shipped specs already
left open — `CurationState`'s *"run-level counters (run summary; consumed by
Spec 06 later)"* comment, `TavilyDiscoverer.failures()`'s *"lets a
caller/observer surface degraded runs (Spec 06)"* docstring,
`DynamoCardStore.failures()`'s identical note, and `runtime_app.py`'s existing
`curation_run_complete` log record — and **extends** them. It replaces
nothing.

## Goals

1. **A real `RunSummary`.** One immutable dataclass
   (`src/curation/summary.py`) produced by every graph invocation, carrying:
   discovered (total **plus** an RSS-vs-Tavily split **plus** the raw
   per-source breakdown), new-after-dedup, summarized-ok, failed,
   cards-written, wall-clock, Bedrock input/output tokens, Tavily
   searches/credits, discoverer/store failures, and an **estimated USD cost**
   split into Bedrock and Tavily components.
2. **Token capture without breaking portability.** The Converse `usage` block
   (`inputTokens` / `outputTokens`) is threaded out of `spike.bedrock` through
   a **new** `summarize_with_usage()` and accumulated in `summarize_node`, so
   `src/curation/{nodes,graph,state}.py` still import zero AWS SDK code. The
   existing `summarize()` keeps its exact signature and return type so
   `src/spike/pipeline.py` (Phase 0) and Plane B are untouched.
3. **Cost estimation as plain, testable arithmetic.** Env-overridable
   constants, each living in the config module that owns its subject: the
   design §7 Bedrock unit prices (Haiku $1/$5 per 1M in/out) go in
   `src/spike/config.py` **beside `HAIKU_MODEL_ID`, the model they price**, so
   a model swap and its price change are one edit in one file; the Tavily
   credit price (default $0.008/credit, basic search = 1 credit, advanced = 2)
   goes in `src/curation/config.py` with the rest of the Tavily knobs. No
   third config module and no config framework — `docs/architecture-principles.md`
   already defers Pydantic adoption until `Card` becomes a versioned API
   contract, so `pydantic-settings` is declined deliberately (it is only a
   transitive dependency of `bedrock-agentcore`, never a chosen one). The math
   itself is pure functions with no I/O.
4. **Structured JSON logging from the entrypoint and the key nodes.** The
   existing `curation_run_complete` record grows into a **superset** (all
   eight fields keep their names and meanings), and `discover` / `summarize` /
   `persist` each emit one JSON record per run, joined by `run_id`. Bounded:
   3 node records + 1 run record per run, plus one warning per *failed* item
   (already capped by `SPIKE_MAX_ITEMS`).
5. **Persist the summary as CloudWatch EMF custom metrics** in namespace
   `AIRadar/Curation` — one extra raw-JSON log line per run that CloudWatch
   Logs parses into 4 metrics (`RunsCompleted`, `CardsWritten`, `ItemsFailed`,
   `EstimatedCostUsd`). **Decision (the source spec delegates this to the
   architect): metrics, not a DynamoDB `runs` table, not both.** Justification:
   - *"Show failed counts for the last 7 runs"* is already satisfied by the
     structured logs alone (Logs Insights), so a `runs` table buys **no query
     capability we lack** — it duplicates data the log group already holds.
   - A `runs` table costs a new CDK stack, a new table with its own
     removal-policy question, a new `dynamodb:PutItem` grant on the execution
     role, and a second write path that can fail *after* a successful run —
     and it still **cannot alarm**.
   - EMF costs **no new AWS resource, no new IAM permission** (the runtime
     already has `logs:PutLogEvents`), **no API call** (no `PutMetricData`,
     no boto3 in the emitting code), and gives 15-month retention, free trend
     graphs, and an alarmable surface for whoever wants one later.
   - As a bonus the EMF line is *top-level* JSON, so Logs Insights
     auto-discovers `failed`, `estimated_cost_usd`, … as first-class fields —
     which the SDK-formatter-wrapped `curation_run_complete` record cannot be
     (see Constraints).
   - Bounded cost: 4 metrics × $0.30/metric-month ≈ **$1.20/mo**, with a
     `CURATION_EMIT_METRICS=false` kill switch.
6. **A real AWS Budget, in CDK.** A **new, separate** CDK-managed monthly cost
   budget `ai-radar-monthly-cost` (`AiRadarBudget` stack) with **ACTUAL**-spend
   notifications at **$50 / $100 / $250** absolute thresholds, delivered to an
   SNS topic subscribed by `danielmauricioerazoespinoza@gmail.com`. Credits
   are **excluded** from the cost calculation (`IncludeCredit: false`) —
   otherwise a credit-covered account reports ~$0 forever and the alert that
   exists to protect the credits never fires.
7. **Local parity.** `uv run run_curation.py` builds and prints the same
   `RunSummary` (including estimated cost), so the cost of a change is visible
   on a laptop before it is visible on the bill.
8. **Prove it against real AWS.** Like `runtime-packaging` and
   `eventbridge-schedule`, this ships with a real `cdk deploy` + live-fire
   pass: the budget visible in the Billing console, the SNS subscription
   confirmed, and datapoints actually present in `AIRadar/Curation` after a
   real invocation.

## Success Criteria

- [ ] Every successful run emits exactly one `curation_run_complete` record
      that is a **strict superset** of today's eight fields, adding at least:
      `discovered_rss`, `discovered_tavily`, `discovered_by_source`,
      `cards_written`, `input_tokens`, `output_tokens`, `tavily_searches`,
      `tavily_credits`, `estimated_bedrock_cost_usd`,
      `estimated_tavily_cost_usd`, `estimated_cost_usd`.
- [ ] `RunSummary` is an immutable dataclass in `src/curation/summary.py` with
      a `to_dict()` whose keys are exactly the record's payload keys.
- [ ] Cost estimation is a pure function of (input tokens, output tokens,
      Tavily credits) and the price constants in `spike.config` (Bedrock) /
      `curation.config` (Tavily) — unit-tested
      with no AWS calls, including the zero-work case (0 items ⇒ $0.0).
- [ ] `discovered_rss + discovered_tavily == discovered` for every run, and
      `discovered_by_source` sums to the same total.
- [ ] `grep -rn "boto3\|botocore" src/curation/nodes.py src/curation/graph.py
      src/curation/state.py src/curation/summary.py src/curation/metrics.py`
      returns **nothing** (portability preserved, Spec 01 Guarantee).
- [ ] `spike.bedrock.summarize(item) -> dict` is unchanged in signature and
      return type; `src/spike/pipeline.py`, `src/spike/chat.py`,
      `run_spike.py`, and `run_chat.py` are untouched.
- [ ] One EMF line per successful run yields datapoints for `RunsCompleted`,
      `CardsWritten`, `ItemsFailed`, and `EstimatedCostUsd` in namespace
      `AIRadar/Curation` (**live**: `aws cloudwatch list-metrics --namespace
      AIRadar/Curation` returns 4 metrics after a real run).
- [ ] `CURATION_EMIT_METRICS=false` suppresses the EMF line entirely and
      changes nothing else about the run.
- [ ] A documented Logs Insights query answers *"failed counts for the last 7
      runs"* and is verified against real log data.
- [ ] `AiRadarBudget` synthesizes exactly one `AWS::Budgets::Budget` named
      `ai-radar-monthly-cost` (`COST` / `MONTHLY`, `IncludeCredit: false`)
      with three `ACTUAL` / `GREATER_THAN` / `ABSOLUTE_VALUE` notifications at
      50, 100, 250, each subscribed to the stack's SNS topic; and one
      `AWS::SNS::TopicPolicy` allowing `budgets.amazonaws.com` to publish,
      scoped by `aws:SourceAccount` + `aws:SourceArn`.
- [ ] **Live**: the budget appears in the AWS Budgets console alongside — and
      without disturbing — the pre-existing "My Monthly Cost Budget"; the
      email subscription is **confirmed**; a manual `aws sns publish` to the
      topic arrives in the inbox.
- [ ] `uv run pytest tests/` stays 100% offline and green (existing 92 tests
      plus the new ones); no new runtime dependency in `pyproject.toml` /
      `uv.lock`.
- [ ] The AgentCore execution role (`infra/lib/agent_runtime.py`) needs **no
      new permission** — verified by `cdk diff AiRadarRuntimeRole` being empty.

## Non-Goals

- **AgentCore Evaluations / answer-quality scoring** — Phase 5.
- **Full trace export / AgentCore Observability spans / OTEL configuration.**
  Research §2.8/§5: no free tier. Summary + a handful of records per run only.
- **Dashboards** (CloudWatch dashboards, Grafana, a UI). A saved Logs Insights
  query plus the budget alert is the MVP surface, per the source spec's
  "resist building dashboards".
- **CloudWatch alarms on the run metrics** (e.g. "no run today", "failed >
  N"). This spec *enables* them by publishing the metrics; wiring alarms +
  their SNS routing is a deliberate later decision, not scope here. The only
  alarm shipped is the AWS Budgets one design §7 names explicitly.
- **A DynamoDB `runs` table** — rejected with reasons under Goal 5. The
  `ai-radar-cards` table is **not** to be reused for run records either
  (`Card` is the published contract; run rows do not belong in it).
- **Per-item trace/log spam.** No log line per discovered item, per Tavily
  result, or per successful summarize.
- **Slack/PagerDuty/chatops integrations.** Native Budgets → SNS → email only.
- **Plane B cost tracking** (Sonnet chat tokens, Titan embeddings). Plane A
  does not embed or chat; adding those price constants now would be
  speculative config for code that does not exist yet.
- **Touching the pre-existing "My Monthly Cost Budget"** ($1/mo, hand-made,
  not CDK-managed). It is left exactly as-is; the new budget has a distinct
  name so CloudFormation can never adopt or clobber it.
- **Changing the AgentCore runtime log group's retention/config.** That log
  group is created by the `agentcore` CLI, outside CloudFormation.
- **Any change to the graph's topology, the `Card` schema, the DynamoDB key
  schema, the schedule, the Dockerfile, or the execution role.**

## Constraints

- **Portability is a hard rule (Spec 01, CLAUDE.md, architecture-principles
  §5).** `src/curation/{nodes,graph,state}.py` must not import `boto3` or any
  AWS SDK. Token usage therefore has to arrive at `summarize_node` as plain
  data through the existing `spike.bedrock` seam. The two new modules
  (`summary.py`, `metrics.py`) are held to the same rule — `metrics.py` builds
  a **dict** and writes a **string**; it never calls CloudWatch.
- **EMF must be the entire log event.** The spec is explicit: *"The LogEvent
  message MUST be a valid JSON object with no additional data at the beginning
  or end."* The SDK's `RequestContextFormatter`
  (`bedrock_agentcore/runtime/app.py`) wraps every logger record as
  `{"timestamp", "level", "message": "<our json as a string>", "logger"}` —
  so **anything emitted through `logger.info(...)` can never be valid EMF**,
  and its JSON body is nested inside a string field in CloudWatch. The EMF
  line must bypass the logger: a single raw `json.dumps(...) + "\n"` written
  to **stderr** (the same stream the SDK's `StreamHandler` writes to, i.e. the
  stream already proven to reach CloudWatch) and flushed.
- **Two things are unverifiable offline** (same class as
  `eventbridge-schedule`'s `bedrockagentcore` service id) and must therefore be
  single-constant, one-line-changeable, with the fallback documented and a
  live fire as a required deliverable:
  1. that CloudWatch Logs extracts EMF from the AgentCore runtime log group
     (`/aws/bedrock-agentcore/runtimes/*`) at all — fallback:
     `CURATION_EMIT_METRICS=false`, logs remain the record of truth;
  2. that a raw stderr write lands as its **own** log event rather than being
     merged with a neighbouring line.
- **Backward compatibility of the log record.** `README.md`'s runbook,
  `tests/test_runtime_app.py`, and `specs/async-invocation-ack/audit.md` all
  pin the eight `curation_run_complete` fields. New fields are **added**; none
  is renamed, retyped, or removed. `event` stays `curation_run_complete`.
- **Tavily credits are an estimate, not a meter.** Tavily's API response does
  not report credits consumed, so cost = attempted searches × credits-per-depth
  (basic 1, advanced 2 — Tavily docs, verified 2026-08) × unit price
  (PAYG $0.008/credit, verified 2026-08). Failed seeds are counted as charged
  (conservative). The price is a config knob precisely because it is a guess.
- **AWS Budgets specifics.** `CfnBudget` is L1-only (no L2 exists in
  `aws-cdk-lib==2.261.0`). Budgets is a global service anchored in
  `us-east-1`; the SNS topic must live there (it does — the whole project is
  `us-east-1`). The topic **requires** a resource policy granting
  `budgets.amazonaws.com` `sns:Publish`, or notifications silently fail. The
  email subscription requires a **human click** to confirm — a live-fire step,
  not something CDK can complete.
- **Custom metrics are not free.** $0.30/metric-month. Hence exactly 4
  metrics, **no dimensions** (an empty DimensionSet, so cardinality is exactly
  4 and can never grow with `run_id`), and a kill switch. High-cardinality
  dimensions are explicitly forbidden by the EMF docs and by this budget.
- **Offline test suite.** Every new test must run with no AWS credentials and
  no network: cost math and `RunSummary` shape as plain unit tests, the EMF
  document as a dict assertion, the budget stack via `Template.from_stack`.
- **`uv` only**, and this spec adds **no new dependency** (stdlib `json`,
  `logging`, `sys`, `dataclasses`; `aws_cdk.aws_budgets` / `aws_sns` ship in
  `aws-cdk-lib`).
- **Test churn is expected and must be handled, not dodged.** Changing
  `summarize_node` to call `summarize_with_usage` invalidates the patch target
  in `tests/conftest.py`'s `summarize_stub_factory` and its three consumers
  (`test_graph.py`, `test_composite.py`, `test_dynamo_store.py`). Those are
  mechanical updates, tracked as explicit tasks.

## Prior Art

- **`specs/async-invocation-ack/contract.md`** — the `curation_run_complete` /
  `curation_run_failed` / `curation_run_accepted` record shapes, the
  `logging.getLogger("bedrock_agentcore.app.curation")` child-logger trick,
  and the `run_id` correlation convention this spec extends verbatim.
- **`specs/eventbridge-schedule/`** — the construct → stack → `infra/app.py`
  pattern, context-overridable knobs (`str(raw).lower() == "true"`),
  `CfnOutput` conventions, the "pin unverifiable-offline wire details as a
  single constant + prove by live fire" discipline, and the DLQ note that
  *"Spec 06 will alarm on ApproximateNumberOfMessagesVisible"* (deliberately
  **not** taken up here — see Non-Goals).
- **`specs/runtime-packaging/contract.md`** — explicit `iam.PolicyStatement`
  over `grant_*()`, least privilege with named `Sid`s, and the live-deploy
  runbook shape.
- **`src/curation/state.py`** — the `# run-level counters (run summary;
  consumed by Spec 06 later)` comment: the intended extension point.
- **`src/curation/{tavily,dynamo,composite}.py`** — the `failures()` accessor
  pattern (reset per call, exposed for "a caller/observer" i.e. this spec)
  that `searches()` / `credits_used()` copy exactly.
- **`tests/test_infra_curation_schedule.py`** — the synth-only assertion
  helpers (`_resources_of_type`, `_statement_by_sid`) the budget stack's tests
  reuse in shape.
- **External, verified 2026-08:** AWS *CloudWatch embedded metric format
  specification* (root-node/`_aws`/DimensionSet/MetricDefinition rules, the
  "no additional data at the beginning or end" requirement, the
  high-cardinality-dimension warning); Tavily *API credits* docs (basic = 1
  credit, advanced = 2, PAYG $0.008/credit); `aws-cdk-lib==2.261.0`
  `aws_budgets.CfnBudget` (`budget=BudgetDataProperty(...)`,
  `notifications_with_subscribers=[NotificationWithSubscribersProperty(...)]`);
  botocore `bedrock-runtime/2023-09-30` `TokenUsage` shape
  (`inputTokens`/`outputTokens`/`totalTokens` required); design §7 unit prices.

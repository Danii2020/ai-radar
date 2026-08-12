# Roadmap: run-observability

Six phases. Phases 1–5 are offline code + tests; **Phase 6 is real AWS** — a
`cdk deploy` of the budget stack plus an `agentcore deploy` + live invocation,
modelled on [`specs/eventbridge-schedule/roadmap.md`](../eventbridge-schedule/roadmap.md)
and [`specs/async-invocation-ack/roadmap.md`](../async-invocation-ack/roadmap.md)
Phase 4, because three things here are **not provable offline**: that
CloudWatch extracts EMF from the AgentCore runtime log group, that the budget
+ SNS topic policy deploy cleanly in the real account, and that the email
subscription actually delivers.

Build order is deliberate: the pure, dependency-free pieces first (cost math,
summary), then the seams that make them real (bedrock usage, nodes), then the
composition root, then infra. Each phase leaves the suite green.

## Implementation Phases

### Phase 1: Pure foundation — config knobs, `RunSummary`, cost math, EMF doc
**Goal**: Every piece of arithmetic and every JSON shape exists and is
unit-testable, before any existing code path changes.
**Dependencies**: None
**Estimated complexity**: Low

1. Add the two Bedrock unit prices to `src/spike/config.py`, immediately after
   `HAIKU_MODEL_ID`: `HAIKU_INPUT_USD_PER_1M` / `HAIKU_OUTPUT_USD_PER_1M`
   (env vars of the same bare names, matching that file's convention). They
   live with the model ID they price so a model swap and its price change are
   one edit in one file; note in the comment that Sonnet/Titan prices are
   deliberately absent.
2. Add the Spec 06 block to `src/curation/config.py`: `TAVILY_SOURCE_PREFIX`,
   `TAVILY_CREDIT_PRICE_USD`, `TAVILY_CREDITS_BY_DEPTH`,
   `TAVILY_DEFAULT_CREDITS_PER_SEARCH`, `METRIC_NAMESPACE`,
   `EMIT_RUN_METRICS` — each env-overridable, each with the comment explaining
   *why* that default (the Tavily one especially: it is an estimate, not a
   meter), plus a one-line pointer that the Bedrock prices live in
   `spike/config.py`.
3. Create `src/curation/summary.py`: the frozen `RunSummary` dataclass (field
   order = log-record key order), `to_dict()`, `split_by_origin`,
   `estimate_bedrock_cost_usd`, `estimate_tavily_cost_usd`,
   `build_run_summary`. Import both config modules
   (`from spike import config as spike_config` + `from . import config`) and
   read every price through the module object
   (`spike_config.HAIKU_INPUT_USD_PER_1M`), never `from ... import X`, so
   monkeypatching works.
4. Create `src/curation/metrics.py`: `METRIC_DEFINITIONS`, `EMF_DIMENSIONS`,
   `run_metrics_document`, `emit_run_metrics`. Resolve `sys.stderr` at call
   time; honour the kill switch; return a `bool`.
5. Sanity-check the portability rule immediately:
   `grep -n "boto3\|botocore\|bedrock_agentcore" src/curation/summary.py
   src/curation/metrics.py` must be empty.

### Phase 2: Token capture at the Bedrock seam
**Goal**: Real token counts leave `spike.bedrock` as plain data, with zero
behavior change for existing callers.
**Dependencies**: Phase 1 (none strictly, but keeps the diff ordered)
**Estimated complexity**: Low

1. In `src/spike/bedrock.py`, add the frozen `TokenUsage` dataclass and
   `summarize_with_usage(item) -> tuple[dict, TokenUsage]` containing the
   existing Converse call body, reading `resp.get("usage", {})` defensively
   (`inputTokens`/`outputTokens`, ints, default 0).
2. Reduce `summarize(item) -> dict` to `return summarize_with_usage(item)[0]`.
   Its docstring must say it is preserved verbatim for `spike.pipeline` and
   Plane B.
3. Verify nothing else moved: `git diff src/spike/` touches only
   `bedrock.py` and `config.py` (the latter from Phase 1's two price
   constants); `run_spike.py`, `run_chat.py`, and
   `src/spike/{pipeline,chat,retrieval,cards,feeds}.py` are untouched.

### Phase 3: Instrument the graph (state + nodes + discoverer accessors)
**Goal**: The graph produces every counter the summary needs and emits its
three structured node records — still with no AWS import anywhere near it.
**Dependencies**: Phases 1–2
**Estimated complexity**: Medium

1. Extend `src/curation/state.py` with `run_id`, `discovered_by_source`,
   `persisted`, `input_tokens`, `output_tokens`; update the section comment
   from "consumed by Spec 06 later" to "consumed by Spec 06".
2. In `src/curation/nodes.py`: add `logger = logging.getLogger(__name__)` and
   the `_log(event, state, **fields)` helper; group by `.source` in
   `discover_node`; switch `summarize_node` to `summarize_with_usage` and
   accumulate tokens **inside** the existing per-item `try` (right after the
   call returns, before `Card.from_model`); convert the per-item failure
   `print` to a structured `logger.warning`; return `{"persisted": ...}` from
   `persist_node`. Emit `discover_complete` / `summarize_complete` /
   `persist_complete`. Do **not** add a log line to `dedup_node` / `rank_node`.
3. In `src/curation/tavily.py`: reset + count `self._searches` per seed
   attempt, add `searches()` and `credits_used()`, and use
   `config.TAVILY_SOURCE_PREFIX` for the source label (output byte-identical).
4. In `src/curation/composite.py`: add duck-typed `searches()` /
   `credits_used()` sums (default 0 for sources that do not expose them) —
   the module must stay source-agnostic (still no `tavily` import).
5. Re-run the portability grep across `nodes.py`, `graph.py`, `state.py`,
   `composite.py`.

### Phase 4: Composition roots (`runtime_app.py`, `run_curation.py`) + offline tests
**Goal**: One `RunSummary` per run, logged and metric-emitted in the cloud,
printed locally; the whole contract that can be proven offline, is.
**Dependencies**: Phase 3
**Estimated complexity**: Medium

1. `runtime_app.py`: add `_configure_curation_logging()` (attach the SDK
   logger's handlers to the `curation` tree, INFO, called once at import);
   change `_run_curation_pipeline()` → `_run_curation_pipeline(run_id)`
   returning `RunSummary` (times itself, passes `run_id` into
   `graph.invoke`, gathers `searches()`/`credits_used()`/`failures()`);
   update `_curation_run` to `asyncio.to_thread(_run_curation_pipeline,
   run_id)`, log `{"event": "curation_run_complete", **summary.to_dict()}`,
   then call `emit_run_metrics(summary)` in its **own** try/except that logs
   `curation_metrics_failed` and swallows.
2. `run_curation.py`: `logging.basicConfig(level=INFO, format="%(message)s")`,
   generate a `run_id`, pass it into `invoke`, build the same summary, and
   print it (replacing the ad-hoc counters line). No `emit_run_metrics` call.
3. Update the existing tests broken by the new seam — mechanical, but they are
   the regression net, so do them deliberately:
   `tests/conftest.py` (`summarize_stub_factory` now returns
   `(dict, TokenUsage)`; add a token-usage knob), and the three consumers
   (`test_graph.py`, `test_composite.py`, `test_dynamo_store.py`) which patch
   `curation.nodes.summarize` → `curation.nodes.summarize_with_usage`.
4. Update `tests/test_runtime_app.py`: T8 (`curation_run_complete` now carries
   the superset — assert the eight originals **still** present with the same
   values, plus the new fields) and T12 (`_run_curation_pipeline(run_id)`
   returns a `RunSummary`). Add: EMF line emitted on success / suppressed by
   the kill switch / a raising `emit_run_metrics` does not produce
   `curation_run_failed`.
5. Add `tests/test_bedrock_usage.py` (usage extraction, missing-`usage`
   degradation, `summarize()` back-compat) and `tests/test_run_summary.py`
   (cost math incl. zero case, `split_by_origin`, counter identities,
   `to_dict()` key order, EMF document shape, no-dimension guarantee, kill
   switch, raw-line-is-valid-JSON via `io.StringIO`).
6. Update `.env.example` and `README.md` (spec-table row + the observability
   section: metric list, both Insights queries, the "payload is nested under
   `message`" note).

### Phase 5: Budget infrastructure (CDK) + synth tests
**Goal**: The design §7 budget alert exists as code, provably correct as far
as `cdk synth` can prove it, with the two easy-to-get-wrong details pinned.
**Dependencies**: None (independent of Phases 1–4 — it can be built in
parallel; it is sequenced last only because the backend half carries more
risk)
**Estimated complexity**: Medium

1. Create `infra/lib/cost_budget.py`: the SNS topic (`enforce_ssl=True`) +
   `EmailSubscription` + the `budgets.amazonaws.com` publish policy scoped by
   `aws:SourceAccount` / `aws:SourceArn` (the literal, region-less budget
   ARN — no circular CFN reference).
2. Add the `CfnBudget` (L1; no L2 exists in `aws-cdk-lib==2.261.0`):
   `COST` / `MONTHLY` / `ai-radar-monthly-cost` / $250 limit, explicit
   `CostTypesProperty` with **`include_credit=False`** and the comment
   explaining why (a credit-covered account otherwise reports ~$0 forever),
   and three `ACTUAL` / `GREATER_THAN` / `ABSOLUTE_VALUE` notifications at
   50 / 100 / 250, each with the topic as its single SNS subscriber.
3. Add `self.budget.node.add_dependency(policy_result.policy_dependable)` —
   AWS Budgets validates SNS publish permission at CreateBudget time, so
   without the explicit dependency the deploy can fail on ordering.
4. Create `infra/stacks/cost_budget_stack.py` with the four context overrides
   and five `CfnOutput`s, then wire `CostBudgetStack(app, "AiRadarBudget")`
   into `infra/app.py` (the other three stacks untouched).
5. Write `tests/test_infra_cost_budget.py` — synth-only, mirroring
   `tests/test_infra_curation_schedule.py`'s helper style and its
   `sys.path.insert(..., "infra")` convention: budget shape, cost types,
   the three notifications, the topic policy + `DependsOn`, the email
   subscription, context overrides, and a no-scope-creep resource count.
6. Confirm `cdk synth` still needs no AWS credentials and writes no
   `cdk.context.json`.

### Phase 6: Real deploy + live-fire validation
**Goal**: Prove the three unverifiable-offline claims against real AWS, and
close Phase 1's last Definition-of-done box with evidence.
**Dependencies**: Phases 4 and 5
**Estimated complexity**: High

1. **Pre-flight**: `agentcore status` (the agent is expected to still be up,
   running the `async-invocation-ack` image), `aws dynamodb scan
   --table-name ai-radar-cards --select COUNT` for a baseline, and
   `aws budgets describe-budgets --account-id 536697225154` to record that
   **"My Monthly Cost Budget" exists and is not ours** — so the post-deploy
   diff is unambiguous.
2. **Deploy the budget stack** (independent of the agent; do it first, it is
   the cheap half):
   ```bash
   uv run --group infra cdk deploy --app "python infra/app.py" AiRadarBudget
   ```
   Verify: `cdk diff` on the other three stacks is empty; the budget appears
   in the Billing console; `aws budgets describe-budget --account-id
   <acct> --budget-name ai-radar-monthly-cost` shows `COST` / `MONTHLY` /
   `IncludeCredit: false` and three ACTUAL notifications at 50/100/250
   (`aws budgets describe-notifications-for-budget`); the pre-existing budget
   is untouched.
3. **Confirm the email subscription** — click the AWS confirmation email, then
   prove delivery end-to-end:
   ```bash
   aws sns list-subscriptions-by-topic --topic-arn <AlertTopicArn>   # not "PendingConfirmation"
   aws sns publish --topic-arn <AlertTopicArn> --subject "AI Radar budget test" \
     --message "live-fire check"
   ```
   An unconfirmed subscription is the single most likely silent failure here.
4. **Rebuild + redeploy the agent** (`agentcore deploy`) — the instrumentation
   is inert until the image is rebuilt. Re-read the `execution_role: null`
   gotcha *before* any future `agentcore destroy`.
5. **Live invocation**: `agentcore invoke '{}'` (still an immediate ack), then
   ~60 s later collect, for that `run_id`:
   - the `curation_run_complete` record — confirm the eight original fields
     are present **and** the new ones are non-zero where expected
     (`input_tokens > 0`, `discovered_rss + discovered_tavily == discovered`,
     `estimated_cost_usd > 0`);
   - the `curation_run_metrics` line — confirm it appears as **its own**
     top-level-JSON log event (not nested under `message`);
   - the three node records;
   - `aws cloudwatch list-metrics --namespace AIRadar/Curation` → 4 metrics,
     and `get-metric-statistics` for `EstimatedCostUsd` → a datapoint.
6. **Run both pinned Logs Insights queries** against the real log group and
   confirm the "failed counts for the last 7 runs" question is actually
   answerable (the acceptance criterion, not a paraphrase of it).
7. **Sanity-check the cost estimate** against reality: compare
   `estimated_bedrock_cost_usd` for the run against Bedrock's own token
   metrics / Cost Explorer for the day, and record the delta in `audit.md`.
   An order-of-magnitude match is a pass; an exact match is not expected.
8. **Record everything in `audit.md`** (Audit Log + Test Coverage rows) with
   real values, exactly as `async-invocation-ack` did for its live fire —
   including a negative result if EMF does not extract, plus the
   `CURATION_EMIT_METRICS=false` fallback decision.
9. **Update `README.md`** with the verified numbers, the "current live AWS
   state" note (a 4th stack is now deployed), and the budget teardown command
   (`cdk destroy AiRadarBudget` — removes budget, topic, subscription; the
   hand-made budget survives).
10. **Phase 1 close-out (for the `sdd-auditor` stage, not the executor):**
    this spec's audit doubles as the **whole-Phase-1** check against
    `README.md`'s and `tasks/phase-1-curation-mvp/README.md`'s *Definition of
    done* — all eight boxes, not just this spec's acceptance criteria. The
    auditor should walk that list, cite the evidence for each box (spec +
    audit + live-fire record), and flag anything Phase 1 claims but never
    actually verified (known candidates: the never-run double-fire dedup
    drill, and `already_running` never observed in production).

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| CloudWatch never extracts the EMF line (AgentCore does not forward raw stderr as its own event, or wraps it) | Med | Med | The line bypasses the SDK formatter precisely because that formatter *would* break EMF; stderr is the stream the SDK itself writes to. Detector: Phase 6.7's `list-metrics`. Fallback is one env var (`CURATION_EMIT_METRICS=false`) and the logs already satisfy "retrievable after the fact" — no redesign, no `runs` table scramble |
| Metric emission silently doubles the account's custom-metric bill via dimensions | Low | Med | `Dimensions: [[]]` + a fixed 4-name list are pinned in the contract and asserted by a test that fails if any dimension key is ever added |
| Changing `summarize_node`'s call target breaks tests across 4 files and the executor "fixes" them by weakening assertions | Med | Med | The churn is enumerated as explicit tasks (4.3) with the rule: patch target changes, assertions do not; T8's eight original fields must keep their exact values |
| `duration_s` semantics shift (now measured inside `_run_curation_pipeline`) is read as a regression | Low | Low | Documented in contract Data Models; the difference is thread-scheduling milliseconds on a ~30 s run |
| Budget deploy fails because AWS Budgets validates SNS publish before the topic policy exists | Med | Med | Explicit `budget.node.add_dependency(policy_result.policy_dependable)`, pinned in the contract with the reason; a synth test asserts the `DependsOn` |
| Email subscription left unconfirmed ⇒ alerts exist but never arrive | High | High | Phase 6.4 makes confirmation *and* a real `aws sns publish` delivery test mandatory runbook steps, not a footnote |
| CDK adopts/clobbers the pre-existing "My Monthly Cost Budget" | Low | High | Distinct name (`ai-radar-monthly-cost`); Phase 6.1 records the before-state and Phase 6.3 diffs against it |
| `IncludeCredit: false` misjudged, so the budget tracks the wrong number | Low | Med | Rationale documented in the construct docstring and intent.md; a synth test pins it, and Phase 6.3 verifies the deployed value. If the operator prefers net-of-credits, it is a one-field change |
| Tavily credit estimate is wrong (plan differs, failed seeds not charged, credits change) | Med | Low | Labelled *estimated* everywhere, env-overridable price, conservative direction (over-counts). Bedrock — the dominant cost — is measured, not estimated |
| Node-level logging turns into per-item spam over time | Low | Med | Exactly 3 node records + `failed`-bounded warnings, pinned in contract Guarantee 7 and asserted by a test that counts records for a multi-item run |
| Scope creep into dashboards / CloudWatch alarms / a `runs` table | Med | Med | intent.md Non-Goals name all three explicitly, with the reasoning for the persistence choice recorded so it is not re-litigated mid-build |
| Live fire spends real money or leaves something enabled | Low | Low | One `agentcore invoke`, `SPIKE_MAX_ITEMS`-bounded (≈$0.01); the schedule stays `DISABLED`; the budget itself is free (first two budgets) |

## File Change Map

**Backend (Python)**
- `src/curation/summary.py` — **CREATE** — `RunSummary`, `split_by_origin`,
  cost estimators, `build_run_summary`.
- `src/curation/metrics.py` — **CREATE** — EMF document builder + raw-line
  emitter + the metric/dimension constants.
- `src/curation/config.py` — **MODIFY** — the Spec 06 knob block (Tavily
  prices/credit map, metric namespace, kill switch, Tavily source prefix) +
  the pointer comment to `spike/config.py` for the Bedrock prices.
- `src/spike/config.py` — **MODIFY** — `HAIKU_INPUT_USD_PER_1M` /
  `HAIKU_OUTPUT_USD_PER_1M` beside `HAIKU_MODEL_ID` (and, optionally, a
  docstring line acknowledging it holds shared cross-plane AWS/Bedrock
  config). Nothing else in that file changes.
- `src/curation/state.py` — **MODIFY** — `run_id`, `discovered_by_source`,
  `persisted`, `input_tokens`, `output_tokens`.
- `src/curation/nodes.py` — **MODIFY** — logger + `_log`, per-source grouping,
  `summarize_with_usage` + token accumulation, structured per-item failure
  warning, `persisted` from `persist_node`.
- `src/curation/tavily.py` — **MODIFY** — `_searches` counter, `searches()`,
  `credits_used()`, shared source-prefix constant.
- `src/curation/composite.py` — **MODIFY** — duck-typed `searches()` /
  `credits_used()` sums.
- `src/spike/bedrock.py` — **MODIFY** — `TokenUsage`, `summarize_with_usage`;
  `summarize` becomes a wrapper (signature unchanged).
- `runtime_app.py` — **MODIFY** — `_configure_curation_logging`,
  `_run_curation_pipeline(run_id) -> RunSummary`, extended
  `curation_run_complete`, guarded `emit_run_metrics`.
- `run_curation.py` — **MODIFY** — `basicConfig`, `run_id`, summary print.

**Infrastructure (Python CDK)**
- `infra/lib/cost_budget.py` — **CREATE** — `CostBudget` construct (SNS topic
  + email subscription + topic policy + `CfnBudget` + the dependency).
- `infra/stacks/cost_budget_stack.py` — **CREATE** — `CostBudgetStack` with
  context overrides and five `CfnOutput`s.
- `infra/app.py` — **MODIFY** — one import + `CostBudgetStack(app,
  "AiRadarBudget")`.

**Tests**
- `tests/test_run_summary.py` — **CREATE** — summary/cost/EMF unit tests.
- `tests/test_bedrock_usage.py` — **CREATE** — usage extraction +
  `summarize()` back-compat, against a fake Bedrock client.
- `tests/test_infra_cost_budget.py` — **CREATE** — synth-only budget/topic/
  policy/dependency assertions.
- `tests/conftest.py` — **MODIFY** — `summarize_stub_factory` returns
  `(dict, TokenUsage)`; token knob.
- `tests/test_graph.py` — **MODIFY** — patch `summarize_with_usage`; assert the
  new state counters and node-record count.
- `tests/test_composite.py` — **MODIFY** — patch target + `searches()` /
  `credits_used()` aggregation.
- `tests/test_dynamo_store.py` — **MODIFY** — patch target only.
- `tests/test_runtime_app.py` — **MODIFY** — superset record, `RunSummary`
  return, EMF emitted/suppressed/failing-safely.

**Docs**
- `README.md` — **MODIFY** — spec-table row, observability section (metrics,
  Insights queries, budget runbook + teardown), live-fire evidence, live-AWS
  state note, Definition-of-done box.
- `.env.example` — **MODIFY** — the five new knobs.
- `specs/run-observability/audit.md` — **MODIFY** — filled in by the auditor,
  including the Phase-1 close-out pass.

**Explicitly NOT changed**: `src/curation/{graph,interfaces,dynamo,local}.py`,
`src/spike/{pipeline,chat,retrieval,cards,feeds}.py`, `run_spike.py`,
`run_chat.py`, `Dockerfile`, `.dockerignore`, `pyproject.toml`, `uv.lock`,
`infra/lib/{card_store,agent_runtime,curation_schedule}.py`,
`infra/stacks/{card_store_stack,agent_runtime_stack,curation_schedule_stack}.py`,
`.bedrock_agentcore.yaml`, and the DynamoDB table's schema/data.

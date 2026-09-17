# Roadmap: eventbridge-schedule

## Implementation Phases

### Phase 1: The construct (Foundation)
**Goal**: `infra/lib/curation_schedule.py` — the schedule, universal target,
explicit invoke policy, and DLQ, with every tunable as a module-level constant.
**Dependencies**: None (Specs 01–04 already landed; nothing here imports `src/`).
**Estimated complexity**: Medium

1. Create `infra/lib/curation_schedule.py` with the module docstring explaining
   the `infra/lib/` (not `infra/constructs/`) rule, mirroring
   `card_store.py` / `agent_runtime.py`.
2. Declare the constants block exactly as pinned in contract.md:
   `DEFAULT_SCHEDULE_EXPRESSION = "cron(0 6 * * ? *)"`, `DEFAULT_TIMEZONE =
   "Etc/UTC"`, `DEFAULT_ENABLED = False`, `DEFAULT_AGENT_RUNTIME_ARN_PARAMETER`,
   `UNIVERSAL_TARGET_SERVICE = "bedrockagentcore"`, `UNIVERSAL_TARGET_ACTION`,
   `INVOKE_IAM_ACTION = "bedrock-agentcore:InvokeAgentRuntime"`,
   `INVOCATION_PAYLOAD = "{}"`, `RUNTIME_ENDPOINT_NAME`, `SESSION_ID_PREFIX`,
   `SESSION_ID_CONTEXT_ATTRIBUTE`, and the delivery-policy durations.
   **Each of the two wire constants carries the "live-verifiable only" comment**
   (service-id vs endpoint-prefix; PascalCase vs camelCase) so a future reader
   knows which literal to change first when an invocation fails.
3. Implement `CurationSchedule.__init__`: `ssm.StringParameter.value_for_string_parameter`
   (**never** `value_from_lookup`), the `sqs.Queue` DLQ (`enforce_ssl=True`,
   14-day retention, `RemovalPolicy.DESTROY`), the `scheduler_targets.Universal`
   target with explicit `policy_statements` (Sid `InvokeCurationAgent`, agent
   ARN + `/runtime-endpoint/DEFAULT`), and the `scheduler.Schedule` with
   `enabled=…`, `time_window=TimeWindow.flexible(...)`.
4. Expose `.schedule`, `.dead_letter_queue`, `.agent_runtime_arn` as attributes
   (construct-exposes-attributes house pattern).
5. Confirm nothing under `src/`, `runtime_app.py`, `Dockerfile`, or
   `infra/lib/agent_runtime.py` was opened (`git diff` clean for those paths).

### Phase 2: Stack + app wiring (Core Logic)
**Goal**: The stack, its CDK-context overrides, and `infra/app.py` registration
— synthesizing cleanly with **no AWS credentials**.
**Dependencies**: Phase 1.
**Estimated complexity**: Low

1. Create `infra/stacks/curation_schedule_stack.py` → `CurationScheduleStack`,
   reading `schedule_expression` / `schedule_timezone` / `schedule_enabled` /
   `agent_runtime_arn_parameter` from `self.node.try_get_context(...)` with the
   construct defaults as fallbacks. Remember `-c schedule_enabled=true` arrives
   as the **string** `"true"` → `str(raw).lower() == "true"`.
2. Emit the `CfnOutput`s: `ScheduleName`, `ScheduleArn`, `ScheduleExpression`,
   `ScheduleTimezone`, `ScheduleEnabled`, `DeadLetterQueueUrl`,
   `DeadLetterQueueArn`, `AgentRuntimeArnParameter`.
3. Modify `infra/app.py`: import `CurationScheduleStack`, add
   `CurationScheduleStack(app, "AiRadarSchedule")` after `AgentRuntimeStack`,
   update the docstring to "Specs 03–05". Keep the flat-module `sys.path` trick
   and the one-line-per-stack shape untouched.
4. `uv run --group infra cdk synth --app "python infra/app.py" AiRadarSchedule`
   succeeds offline. Eyeball the emitted template against contract.md's
   "prototype-verified synthesized template" block — `State: DISABLED`,
   `bedrockagentcore:invokeAgentRuntime` target ARN, `RetryPolicy` 3/7200,
   `FlexibleTimeWindow` FLEXIBLE/15, and **no `"*"` resource anywhere**.
5. Confirm no `cdk.context.json` was written (proof that no synth-time lookup
   happened).

### Phase 3: Offline test suite (Testing)
**Goal**: `tests/test_infra_curation_schedule.py` green, and the whole suite
still 100% offline.
**Dependencies**: Phase 2.
**Estimated complexity**: Low

1. Create `tests/test_infra_curation_schedule.py` following
   `tests/test_infra_agent_runtime.py` exactly: the
   `sys.path.insert(0, .../infra)` preamble, `_synthesized_template()`,
   `_resources_of_type`, `_all_policy_statements`, `_statement_by_sid`,
   `_as_list` helpers (copy the shape; these are per-file by house convention,
   not a shared module).
2. Assert the schedule properties, the target ARN/`Input`/`RetryPolicy`/
   `DeadLetterConfig`, the two-and-only-two policy statements, the trust
   policy, the **zero-wildcard** invariant, the DLQ properties, the SSM
   template parameter, and the outputs (see audit.md T1–T13 for the list).
3. Add a synth-with-context test proving `-c schedule_expression=… -c
   schedule_enabled=true` flows through (construct the `cdk.App` with
   `context={...}` — no CLI needed).
4. `uv run pytest tests/ -v` green; confirm the new file makes **zero** AWS
   calls (no `moto`, no boto3 client, no credentials, no network).

### Phase 4: Real deploy, live fire & runbook (Integration & Validation)
**Goal**: Prove the universal-target wire shape for real — Scheduler fires,
AgentCore runs, cards land in DynamoDB, DLQ stays empty — then leave the infra
inert and documented.
**Dependencies**: Phase 3.
**Estimated complexity**: High

1. **Redeploy Spec 04's agent** (currently torn down per README). Follow the
   existing runbook verbatim: `cdk deploy AiRadarRuntimeRole` → capture
   `ExecutionRoleArn` → `aws secretsmanager put-secret-value` the real Tavily
   key → `agentcore configure --create -n ai_radar_curation -e runtime_app.py
   -er <arn> -r us-east-1 -ecr auto --disable-memory --non-interactive` →
   `agentcore deploy` → `agentcore status`.
2. **Pre-flight sanity check** (proves the *agent* is healthy before blaming
   the schedule): `agentcore invoke '{}'` returns a run summary with
   `persisted > 0`. Note the `ai-radar-cards` item count
   (`aws dynamodb scan --table-name ai-radar-cards --select COUNT`).
3. **Wire the ARN into SSM** (the one manual step CDK depends on):
   `aws ssm put-parameter --name /ai-radar/agent-runtime-arn --type String
   --value "<agentRuntimeArn from agentcore status>" --overwrite`.
4. **Deploy the schedule stack**: `uv run --group infra cdk deploy --app
   "python infra/app.py" AiRadarSchedule`. Verify with
   `aws scheduler get-schedule --name <ScheduleName>` that `State` is
   `DISABLED`, the target ARN, `Input`, `RetryPolicy`, and `FlexibleTimeWindow`
   match contract.md.
5. **The live fire** — a *one-shot cron a few minutes out*, deliberately chosen
   over "invoke the agent directly by CLI" because only a real Scheduler
   invocation exercises the two unverifiable constants (service identifier and
   `Input` casing/encoding), the invoke role, and the DLQ path:
   ```bash
   # Note the current count first. Then, with UTC "now + ~4 min" as M/H and an
   # explicit YEAR so the cron matches exactly once:
   uv run --group infra cdk deploy --app "python infra/app.py" AiRadarSchedule \
     -c schedule_enabled=true \
     -c schedule_expression="cron(<MM> <HH> <DD> <MM_month> ? <YYYY>)" \
     -c schedule_timezone="Etc/UTC"
   ```
   Set the flexible window expectation: with `Mode: FLEXIBLE` / 15 min the fire
   may land up to 15 minutes late — that is correct behavior, not a failure.
   (If a tighter observation loop is wanted for this one deploy, add
   `-c` support for the window later; do **not** hand-edit the deployed
   schedule, or the next `cdk deploy` will silently revert it.)
6. **Verify the outcome**: `aws dynamodb scan --table-name ai-radar-cards
   --select COUNT` increased with **no human invoking anything**; the AgentCore
   runtime log group shows a run whose session id starts with
   `ai-radar-scheduled-curation-run-id-`; `aws sqs get-queue-attributes
   --queue-url <DeadLetterQueueUrl> --attribute-names ApproximateNumberOfMessagesVisible`
   is `0`. If the DLQ is non-empty or nothing fired, work the fallback ladder
   in the Risk Assessment below.
7. **Double-fire check** (acceptance criterion): repeat step 5 once more and
   confirm no card for an already-curated URL was duplicated (`card_id` count
   for a known URL stays 1, `created_at` preserved) — while recording honestly
   that the total count may still grow by a new bounded slice, per Spec 04's
   documented 2026-07-28 behavior.
8. **Return to inert**: `uv run --group infra cdk deploy --app "python
   infra/app.py" AiRadarSchedule` (no `-c` flags) → back to `cron(0 6 * * ? *)`
   / `Etc/UTC` / `DISABLED`. Confirm via `aws scheduler get-schedule`.
9. **Runbook + README**: add an `eventbridge-schedule` section to `README.md`
   covering prerequisites, the SSM step, deploy, the live-fire recipe, how a
   human later goes live (`-c schedule_enabled=true` — **and that this starts
   real recurring daily cost**), how to pause (`cdk deploy` with defaults, or
   `aws scheduler update-schedule --state DISABLED` knowing the next `cdk deploy`
   re-asserts CDK's value), and teardown. Teardown must repeat the Spec 04
   gotcha: **null `aws.execution_role` in `.bedrock_agentcore.yaml` before
   `agentcore destroy`**, or it will `iam:DeleteRole` the CDK-owned role. Flip
   the README spec table row for `eventbridge-schedule` to shipped, and update
   the "Deliberately deferred" bullet.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `service="bedrockagentcore"` is the wrong identifier (endpoint prefix wins instead) | Med | High | Single constant `UNIVERSAL_TARGET_SERVICE`; live fire in Phase 4.5 is the detector; documented fallback `"bedrock-agentcore"` → redeploy → refire. Derived from AWS's stated serviceId rule + verified against 4 worked examples, so `bedrockagentcore` is the odds-on default |
| `Input` needs camelCase members, or `Payload` must be base64 | Med | High | Ordered fallback ladder in the runbook: (a) camelCase `agentRuntimeArn`/`payload`/`runtimeSessionId`, (b) `"Payload": "e30="`. Both are one-line edits in the construct; error is a `ValidationException` visible in the DLQ message |
| EventBridge Scheduler does not support `bedrock-agentcore` as a universal target *at all* | Low–Med | High | This is the only failure that is **not** a one-line fix. Detection: invocations fail identically under every fallback above. Response is a **spec amendment**, not an in-flight redesign — the known alternative (a thin Lambda bridge calling `invoke_agent_runtime`) adds a function, a role, a log group, and a new Plane-A infra edge, all of which need their own intent/contract review. Do not build it under this spec |
| `RuntimeSessionId` or `ContentType` mis-serialized by Scheduler's invoker | Low | Med | Both are optional model members; dropping them is a one-line edit and the first thing to try if a `ValidationException` mentions them. Prefix alone is ≥33 chars so length validation cannot be the cause |
| SSM parameter absent/stale at deploy time | Med | Med | Fail-fast at `cdk deploy` (CFN cannot resolve `AWS::SSM::Parameter::Value<String>`); runbook fixes the ordering (agent → SSM → stack). Stale ARN surfaces as `ResourceNotFoundException` → DLQ |
| Long curation run exceeds Scheduler's target invocation timeout → spurious retry → duplicate run | Med | Low | Harmless by Guarantee 8 (no duplicate cards for curated URLs). `retry_attempts=3` bounds the blast radius; `SPIKE_MAX_ITEMS` bounds each run's cost |
| Schedule accidentally left `ENABLED` after the live fire | Med | Med | Phase 4.8 is an explicit "return to inert" step with a verification command; `DEFAULT_ENABLED = False` means a plain `cdk deploy` always re-asserts DISABLED |
| Console/CLI toggle of the schedule silently reverted by the next `cdk deploy` | Med | Low | Documented in the runbook: CDK owns `State`; go live via `-c schedule_enabled=true`, not the console |
| `agentcore destroy` deletes the CDK-owned execution role (Spec 04 gotcha) | Med | High | Runbook repeats the `execution_role: null` edit verbatim; Phase 4.1's redeploy re-enters this trap, so it must be restated, not cross-referenced |
| Deploying the schedule while the agent is torn down | Med | Low | Schedule ships DISABLED, so it cannot fire against a missing agent; runbook states "keep it disabled whenever the agent is down" |
| Recurring cost after going live | Low | Med | One Haiku-only run/day, capped by `SPIKE_MAX_ITEMS`; Scheduler is free under 14M invocations and the DLQ is effectively free; README states the cost explicitly at the go-live step |
| Copy-paste drift between the new synth test and `test_infra_agent_runtime.py` helpers | Low | Low | Accepted: house convention is per-file helpers (Spec 03 → Spec 04 already duplicates them); a shared helper module is a speculative abstraction the architecture principles reject |

## File Change Map

- `infra/lib/curation_schedule.py` — **CREATE** — `CurationSchedule` construct:
  constants (cadence/timezone/enabled/wire identifiers/delivery policy), SSM
  deploy-time ARN reference, SQS DLQ, `Universal` target with explicit
  least-privilege `policy_statements`, `Schedule`.
- `infra/stacks/curation_schedule_stack.py` — **CREATE** —
  `CurationScheduleStack`: CDK-context overrides + eight `CfnOutput`s.
- `infra/app.py` — **MODIFY** — import + `CurationScheduleStack(app,
  "AiRadarSchedule")`; docstring "Specs 03–05".
- `tests/test_infra_curation_schedule.py` — **CREATE** — synth-only assertions
  (schedule props, target wire shape, IAM, zero-wildcard, DLQ, SSM parameter,
  outputs, context overrides).
- `README.md` — **MODIFY** — new `eventbridge-schedule` runbook section; spec
  table row → shipped; "Deliberately deferred" EventBridge bullet struck; test
  count updated.
- `pyproject.toml` / `uv.lock` — **UNCHANGED** — `aws_scheduler`,
  `aws_scheduler_targets`, `aws_sqs`, `aws_ssm` all ship inside the already-present
  `aws-cdk-lib`.
- `src/**`, `runtime_app.py`, `Dockerfile`, `.dockerignore`,
  `infra/lib/agent_runtime.py`, `infra/stacks/agent_runtime_stack.py`,
  `infra/lib/card_store.py`, `infra/stacks/card_store_stack.py` — **UNCHANGED
  (asserted)** — Spec 04 non-modification guarantee (Behavior Guarantee 1).

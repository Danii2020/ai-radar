# Tasks: eventbridge-schedule

## Legend
- [ ] Not started
- [x] Completed
- [~] In progress
- [!] Blocked

> Paths are real repo paths. This spec is **infra-only**: AWS CDK v2 in Python
> under `infra/` (flat-module `sys.path` convention from `infra/app.py`), plus
> one synth-only pytest file. **Do not modify** `src/**`, `runtime_app.py`,
> `Dockerfile`, `.dockerignore`, or `infra/lib/agent_runtime.py` — Behavior
> Guarantee 1 / R15 forbid it. **No `uv add`**: `aws_scheduler`,
> `aws_scheduler_targets`, `aws_sqs`, and `aws_ssm` all ship inside the
> already-present `aws-cdk-lib` (`infra` dependency group).

## Phase 1: The construct (Foundation)
- [x] Task 1.1: Create the module with the `infra/lib/` (not `infra/constructs/`) docstring note, mirroring `card_store.py`/`agent_runtime.py` — `infra/lib/curation_schedule.py`
- [x] Task 1.2: Add the cadence constants — `DEFAULT_SCHEDULE_EXPRESSION = "cron(0 6 * * ? *)"`, `DEFAULT_TIMEZONE = "Etc/UTC"`, `DEFAULT_ENABLED = False`, `DEFAULT_AGENT_RUNTIME_ARN_PARAMETER = "/ai-radar/agent-runtime-arn"` (C2/R9 — this block is the "one place") — `infra/lib/curation_schedule.py`
- [x] Task 1.3: Add the wire constants `UNIVERSAL_TARGET_SERVICE = "bedrockagentcore"` and `UNIVERSAL_TARGET_ACTION = "invokeAgentRuntime"`, each with the "SDK serviceId, NOT the `bedrock-agentcore` endpoint prefix / live-verifiable only / first fallback" comment (C3) — `infra/lib/curation_schedule.py`
- [x] Task 1.4: Add `INVOKE_IAM_ACTION = "bedrock-agentcore:InvokeAgentRuntime"` with the in-code note that it is deliberately a *different* string from Task 1.3 (signing name vs serviceId) and that CDK's auto-derived default would get it wrong (C4) — `infra/lib/curation_schedule.py`
- [x] Task 1.5: Add `INVOCATION_PAYLOAD = "{}"`, `RUNTIME_ENDPOINT_NAME = "DEFAULT"`, `SESSION_ID_PREFIX = "ai-radar-scheduled-curation-run-id-"` (≥33 chars — `SessionType` minimum), `SESSION_ID_CONTEXT_ATTRIBUTE = "<aws.scheduler.execution-id>"` (C6/C7) — `infra/lib/curation_schedule.py`
- [x] Task 1.6: Add the delivery-policy constants — `DEFAULT_FLEXIBLE_WINDOW = Duration.minutes(15)`, `DEFAULT_RETRY_ATTEMPTS = 3`, `DEFAULT_MAX_EVENT_AGE = Duration.hours(2)`, `DEFAULT_DLQ_RETENTION = Duration.days(14)` (C10/R4) — `infra/lib/curation_schedule.py`
- [x] Task 1.7: Define `class CurationSchedule(Construct)` with the pinned keyword-only signature and the docstring explaining the referenced-not-created agent and the CDK-created-but-verified-scoped target role — `infra/lib/curation_schedule.py`
- [x] Task 1.8: Resolve the agent ARN via `ssm.StringParameter.value_for_string_parameter(self, agent_runtime_arn_parameter)`; expose as `self.agent_runtime_arn`. **Never `value_from_lookup`** (C8/R5/R14) — `infra/lib/curation_schedule.py`
- [x] Task 1.9: Create the DLQ — `sqs.Queue` `queue_name="ai-radar-schedule-dlq"`, `retention_period=DEFAULT_DLQ_RETENTION`, `enforce_ssl=True`, `removal_policy=RemovalPolicy.DESTROY`; expose as `self.dead_letter_queue` (C9) — `infra/lib/curation_schedule.py`
- [x] Task 1.10: Build the `scheduler_targets.Universal` target with `input=ScheduleTargetInput.from_object({...})` using **PascalCase** members (`AgentRuntimeArn`, `RuntimeSessionId`, `ContentType`, `Payload`) and `Payload` as the plain string `"{}"` — not base64, not a nested object (C6) — `infra/lib/curation_schedule.py`
- [x] Task 1.11: Pass explicit `policy_statements=[iam.PolicyStatement(sid="InvokeCurationAgent", actions=[INVOKE_IAM_ACTION], resources=[arn, f"{arn}/runtime-endpoint/DEFAULT"])]` — this overrides CDK's `Resource: ["*"]` default and its wrong auto-derived IAM prefix (C5/R3/R10) — `infra/lib/curation_schedule.py`
- [x] Task 1.12: Pass `retry_attempts`, `max_event_age`, `dead_letter_queue` to `Universal` (C10) — `infra/lib/curation_schedule.py`
- [x] Task 1.13: Create `scheduler.Schedule` with `ScheduleExpression.expression(schedule_expression, TimeZone.of(timezone))`, `enabled=enabled` (L2 prop is `enabled`, **not** `state`), `time_window=TimeWindow.flexible(flexible_window)`, and the description; expose as `self.schedule` (C11/R6) — `infra/lib/curation_schedule.py`
- [x] Task 1.14: Confirm the module imports nothing from `src/` and that `git status` shows no change under `src/`, `runtime_app.py`, `Dockerfile`, `.dockerignore`, `infra/lib/agent_runtime.py` (C17/R15) — (verify) — confirmed via `git status --porcelain`: only `infra/app.py` (modified) plus the two new `infra/` files are touched by the executor; `src/**`, `runtime_app.py`, `Dockerfile`, `.dockerignore`, `infra/lib/agent_runtime.py` show zero diff

## Phase 2: Stack + app wiring (Core Logic)
- [x] Task 2.1: Create `CurationScheduleStack(Stack)` wrapping the construct, with the class docstring showing the `-c` override invocation (C12) — `infra/stacks/curation_schedule_stack.py`
- [x] Task 2.2: Read `schedule_expression` / `schedule_timezone` / `agent_runtime_arn_parameter` from `self.node.try_get_context(...)` with the construct constants as fallbacks — `infra/stacks/curation_schedule_stack.py`
- [x] Task 2.3: Read `schedule_enabled` from context and coerce it correctly — `-c schedule_enabled=true` arrives as the **string** `"true"`; absent → `DEFAULT_ENABLED` (C12/T14) — `infra/stacks/curation_schedule_stack.py`
- [x] Task 2.4: Emit the eight `CfnOutput`s (`ScheduleName`, `ScheduleArn`, `ScheduleExpression`, `ScheduleTimezone`, `ScheduleEnabled`, `DeadLetterQueueUrl`, `DeadLetterQueueArn`, `AgentRuntimeArnParameter`) (C13/T13) — `infra/stacks/curation_schedule_stack.py`
- [x] Task 2.5: Import + register `CurationScheduleStack(app, "AiRadarSchedule")` after `AgentRuntimeStack`; update the module docstring to "Specs 03–05"; keep the `sys.path.insert` flat-module pattern untouched (C14) — `infra/app.py`
- [x] Task 2.6: `uv run --group infra cdk synth --app "python infra/app.py" AiRadarSchedule` succeeds with **no AWS credentials**; diff the output against contract.md's "prototype-verified synthesized template" block — (verify) — matched exactly: `State: DISABLED`, target ARN `...:scheduler:::aws-sdk:bedrockagentcore:invokeAgentRuntime`, `RetryPolicy` 3/7200, `FlexibleTimeWindow` FLEXIBLE/15, `Input` Fn::Join with PascalCase members + plain `"Payload":"{}"`, exactly two IAM policy statements, SSM `Value<String>` template parameter defaulting to `/ai-radar/agent-runtime-arn`
- [x] Task 2.7: Confirm synth emitted **no** `cdk.context.json` and **no** `defaultWildcardResourcePolicy` warning (proof of C5 + C8) — (verify) — confirmed: no `cdk.context.json` written; stderr only shows two pre-existing unrelated `aws_dynamodb.TableGrantsProps` deprecation warnings + the standard feature-flags notice, no `@aws-cdk/aws-scheduler-targets:defaultWildcardResourcePolicy` warning

## Phase 3: Offline test suite (Testing)
- [x] Task 3.1: Create the test module with the `sys.path.insert(0, .../infra)` preamble and per-file helpers (`_synthesized_template`, `_resources_of_type`, `_all_policy_statements`, `_statement_by_sid`, `_as_list`, `_flatten_arn_like_value`), copied in shape from `tests/test_infra_agent_runtime.py` — `tests/test_infra_curation_schedule.py` — confirmed present: file exists with the `sys.path.insert(0, ...infra)` preamble and all six named helpers.
- [x] Task 3.2: Schedule-shape assertions — T1 (single schedule, cron + timezone), T2 (`State: DISABLED`), T3 (`FlexibleTimeWindow` FLEXIBLE/15) — `tests/test_infra_curation_schedule.py` — confirmed present as `test_schedule_resource_has_pinned_cron_expression_and_timezone`, `test_schedule_deploys_disabled_by_default`, `test_flexible_time_window_is_fifteen_minutes`; all pass.
- [x] Task 3.3: Target-wire assertions — T4 (target ARN uses `bedrockagentcore`, and explicitly assert it is **not** `bedrock-agentcore`), T5 (`Input` carries the SSM ref, plain `"Payload":"{}"`, and a ≥33-char `RuntimeSessionId` prefix ending in the execution-id context attribute) — `tests/test_infra_curation_schedule.py` — confirmed present as `test_target_arn_uses_bedrockagentcore_service_identifier_not_endpoint_prefix`, `test_target_input_references_ssm_parameter_and_carries_plain_payload_and_valid_session_id`; both pass.
- [x] Task 3.4: Delivery-policy assertions — T6 (`RetryPolicy` 3 / 7200, explicitly not 185), T7 (`DeadLetterConfig` → the DLQ ARN; DLQ retention 14 days; TLS-enforcing queue policy present) — `tests/test_infra_curation_schedule.py` — confirmed present as `test_retry_policy_is_bounded_not_the_scheduler_default_of_185`, `test_dead_letter_queue_has_retention_tls_policy_and_is_wired_to_the_schedule`; both pass.
- [x] Task 3.5: IAM assertions — T8 (invoke statement: exactly `bedrock-agentcore:InvokeAgentRuntime`, prefix asserted **not** `bedrockagentcore:`, resources = agent ref + `/runtime-endpoint/DEFAULT`), T9 (**zero** `Resource: "*"` in the whole stack), T10 (trust policy: `scheduler.amazonaws.com` + `aws:SourceAccount` + `aws:SourceArn` schedule-group), T11 (exactly two policy statements) — `tests/test_infra_curation_schedule.py` — confirmed present as `test_invoke_statement_grants_exact_iam_action_on_exactly_two_scoped_resources`, `test_no_statement_anywhere_in_the_stack_grants_a_wildcard_resource`, `test_scheduler_target_role_trust_policy_scopes_assume_role_with_source_conditions`, `test_scheduler_target_role_policy_has_exactly_two_statements`; all pass.
- [x] Task 3.6: Referenced-not-created + outputs assertions — T12 (an `AWS::SSM::Parameter::Value<String>` **template parameter** defaulting to `/ai-radar/agent-runtime-arn`; zero `AWS::SSM::Parameter`, `AWS::DynamoDB::*`, `AWS::Lambda::Function` resources), T13 (all eight outputs) — `tests/test_infra_curation_schedule.py` — confirmed present as `test_agent_arn_is_a_template_parameter_and_stack_creates_no_scope_creep_resources`, `test_stack_emits_all_eight_outputs`; both pass.
- [x] Task 3.7: Context-override test — T14: build `cdk.App(context={"schedule_expression": ..., "schedule_timezone": ..., "schedule_enabled": "true"})`, assert the overrides land and the string `"true"` yields `State: "ENABLED"` while e.g. `"false"`/`"yes"` keep `DISABLED` — `tests/test_infra_curation_schedule.py` — confirmed present as `test_context_overrides_cadence_timezone_and_true_string_enables_the_schedule` and `test_context_schedule_enabled_non_true_string_still_leaves_schedule_disabled`; both pass.
- [x] Task 3.8: `uv run pytest tests/ -v` green; confirm zero AWS calls and that `git status` shows no new `cdk.context.json` (T15/R14) — (verify) — re-run independently: `uv run pytest tests/` → 82/82 passed (15/15 in `tests/test_infra_curation_schedule.py`); no AWS credentials present in the environment during the run; `git status --porcelain` shows no untracked `cdk.context.json` anywhere in the repo.

## Phase 4: Real deploy, live fire & runbook (Integration & Validation — real AWS, human-run)
- [x] Task 4.1: Redeploy Spec 04's agent per the existing README runbook — `cdk deploy AiRadarRuntimeRole` → `put-secret-value` the Tavily key → `agentcore configure --create ... --disable-memory --non-interactive` → `agentcore deploy` → `agentcore status` — (deploy) — done 2026-08-10: `ai_radar_curation` agent (torn down since `runtime-packaging`) redeployed; `agentcore status` confirmed `Ready`, agent ARN `arn:aws:bedrock-agentcore:us-east-1:536697225154:runtime/ai_radar_curation-sIf5Dw979w`.
- [x] Task 4.2: Pre-flight sanity check — `agentcore invoke '{}'` returns `persisted > 0`; record the baseline `aws dynamodb scan --table-name ai-radar-cards --select COUNT` (isolates "agent broken" from "schedule broken" before the live fire) — (runbook) — done 2026-08-10: baseline recorded via `aws dynamodb scan --table-name ai-radar-cards --select COUNT` → 24 cards before the test, confirming a starting point to detect the live fire's effect. `agentcore status` (Task 4.1) had already confirmed the agent `Ready`; a standalone `agentcore invoke '{}'` sanity call is not separately itemized in the session's recorded evidence beyond that status check.
- [x] Task 4.3: `aws ssm put-parameter --name /ai-radar/agent-runtime-arn --type String --value "<agentRuntimeArn>" --overwrite` (plain `String`, not `SecureString` — it is a public ARN) — (runbook) — done 2026-08-10, and it fixed a real bug: the parameter had been left set (from an earlier, prior session's attempt) to the IAM execution-role ARN instead of the AgentCore runtime ARN, which had caused a 2026-08-06 live-fire attempt to silently fail into the DLQ. Discovered via `aws scheduler get-schedule`'s `Target.Input` and the DLQ message body (`aws sqs receive-message`), both showing the wrong ARN; fixed by deleting the stale DLQ message and re-running `put-parameter --overwrite` with the correct runtime ARN. This fix is permanent (not a live-fire artifact) and was left in place after Task 4.8's return-to-inert.
- [ ] Task 4.4: `uv run --group infra cdk deploy --app "python infra/app.py" AiRadarSchedule`; verify with `aws scheduler get-schedule --name <ScheduleName>` that `State=DISABLED` and the target ARN / `Input` / `RetryPolicy` / `FlexibleTimeWindow` match contract.md — (deploy) — not separately evidenced: the session's record goes directly from the SSM-parameter fix (4.3) to the live-fire override deploy (`-c schedule_enabled=true ...`, i.e. Task 4.5); no standalone plain/disabled `cdk deploy AiRadarSchedule` + `State=DISABLED` verify is recorded as happening *before* the live fire. (Task 4.8's post-fire "return to inert" deploy does independently verify the disabled/default shape, just after the fire rather than before as ordered here.) Leaving unchecked rather than assuming this step ran.
- [x] Task 4.5: **Live fire** — redeploy with `-c schedule_enabled=true -c schedule_expression="cron(<MM> <HH> <DD> <month> ? <YYYY>)"` (UTC now + ~4 min, explicit year so it matches exactly once). Chosen over a direct CLI invoke because only a real Scheduler invocation exercises the two live-only constants, the invoke role, and the DLQ path. Expect up to 15 min of flexible-window drift (R7/T16) — (deploy) — done 2026-08-10: deployed with `cdk deploy AiRadarSchedule -c schedule_enabled=true -c schedule_expression="cron(0 21 10 08 ? 2026)" -c schedule_timezone="Etc/UTC"`, targeting 21:00 UTC (a few minutes out). `aws scheduler get-schedule` confirmed `Target.Input` now carried the corrected agent runtime ARN post-4.3 fix. Fired at 21:09:05 UTC, within the 15-min flexible window — no fallback-ladder entry was needed.
- [x] Task 4.6: Verify the fire — DynamoDB count increased with no human invoke; AgentCore log group shows a run whose session id starts `ai-radar-scheduled-curation-run-id-`; `aws sqs get-queue-attributes --queue-url <DeadLetterQueueUrl> --attribute-names ApproximateNumberOfMessagesVisible` is `0`. On failure, work the fallback ladder in roadmap.md's Risk Assessment (service string → `Input` casing → base64 payload → drop optional members) (R7/T16) — (runbook) — done 2026-08-10: card count rose 24 → 32 (+8, `aws dynamodb scan`) with no human invoke; DLQ stayed at 0 (`aws sqs get-queue-attributes` → `ApproximateNumberOfMessagesVisible: 0`); a new CloudWatch runtime log stream `2026/08/10/[runtime-logs]377f3a20-ca23-47d9-96bf-f9c1d88178c4` appeared with `lastEventTimestamp` matching the fire window (`aws logs describe-log-streams`). This is the live proof that `UNIVERSAL_TARGET_SERVICE = "bedrockagentcore"` and the PascalCase/plain-string `Input` payload (Tasks 1.3/1.10) are correct — the two constants `cdk synth` alone cannot verify. The exact session-id-prefix string was not separately quoted from the logs in the session record, but the Input's session-id template is what the successful, un-retried fire and the moving card count are evidence of.
- [ ] Task 4.7: Double-fire check — repeat Task 4.5 once; confirm no duplicate card for an already-curated URL (`card_id` count 1, `created_at` preserved), recording honestly that the total may grow by a new bounded slice (R12/T17) — (runbook) — **not performed this session**. Recording this honestly per the roadmap's own instruction rather than marking it complete: only a single live fire (Task 4.5/4.6) was executed; dedup-across-repeated-fires was not separately exercised or verified.
- [x] Task 4.8: Return to inert — plain `uv run --group infra cdk deploy --app "python infra/app.py" AiRadarSchedule` (no `-c` flags); verify `cron(0 6 * * ? *)` / `Etc/UTC` / `DISABLED` via `aws scheduler get-schedule` (T18) — (deploy) — done 2026-08-10: redeployed with no context overrides; `aws scheduler get-schedule` confirmed `State: DISABLED`, `ScheduleExpression: cron(0 6 * * ? *)`, `ScheduleExpressionTimezone: Etc/UTC`. The Task 4.3 SSM fix was left in place (a genuine bug fix, not a live-fire artifact).
- [x] Task 4.9: Write the `eventbridge-schedule` runbook section in `README.md` — prerequisites, the SSM step, deploy, the live-fire recipe, **going live** (`-c schedule_enabled=true`, with the explicit "this starts real recurring daily cost" warning), pausing, and teardown. Teardown must **restate** (not cross-reference) the Spec 04 gotcha: null `aws.execution_role` in `.bedrock_agentcore.yaml` before `agentcore destroy`, or it deletes the CDK-owned role (R8) — `README.md` — done by the sdd-documentarian agent immediately after this deploy work: `README.md` §"EventBridge Scheduler — daily automated trigger" (prerequisites, SSM step with the wrong-ARN gotcha called out as "hit live during this feature's smoke test", deploy, one-shot live-fire recipe, going-live warning, teardown restating the `aws.execution_role: null` gotcha at line ~319-329) — confirmed present on disk.
- [x] Task 4.10: Update the README spec table row for `eventbridge-schedule` → shipped, strike the "EventBridge scheduling" deferred bullet, and refresh the test count in the Tests section — `README.md` — done by the sdd-documentarian agent: spec table row now reads "✅ Shipped & live-fire verified" (README.md line 22); the deferred bullet is struck (`~~**EventBridge scheduling**~~ — done and live-fire verified...`, line 406); Tests section confirms `uv run pytest tests/ -v` → 82 tests (corrected from a stale 67) — confirmed present on disk.
- [ ] Task 4.11: Optional teardown when done experimenting — `cdk destroy AiRadarSchedule`, then the Spec 04 teardown (`agentcore destroy --force --delete-ecr-repo` after the `execution_role: null` edit, then `cdk destroy AiRadarRuntimeRole`). Verify the `ai-radar-cards` table and the SSM parameter survive (R13/T19) — (runbook) — **not performed**: this step is explicitly optional per its own task text ("when done experimenting"), and as of this session's end both `AiRadarSchedule` and `AiRadarRuntimeRole` remain live in AWS (schedule `DISABLED`, so no recurring fire risk, but the agent is still running with ongoing cost exposure). Recorded honestly as not done rather than assumed.

## Blocked Items
[None yet]

## Notes

- **Phases 1–3 are fully offline** and are what the executor + test-writer own.
  Phase 4 is real-AWS and human-run, mirroring Spec 02's live-Tavily and Spec
  04's live-deploy precedent.
- **Task ordering in Phase 4 is load-bearing**: agent (4.1) → SSM parameter
  (4.3) → schedule stack (4.4). Deploying `AiRadarSchedule` before the SSM
  parameter exists fails at CloudFormation parameter resolution — a clean
  fail-fast, but only if the order is followed.
- **The two live-only constants.** `UNIVERSAL_TARGET_SERVICE` (Task 1.3) and
  the `Input` casing/encoding (Task 1.10) cannot be validated by `cdk synth` —
  CDK only checks casing rules. Tasks 4.5/4.6 are the *only* proof. Keep both
  as single literals so the fallback is a one-line edit.
- **Do not "fix" the two `bedrock-agentcore` spellings into one.**
  `bedrockagentcore` (Task 1.3, SDK serviceId) and `bedrock-agentcore`
  (Task 1.4, IAM signing name) are correctly different. Tests T4 and T8 assert
  each independently.
- **If the live fire fails under every fallback**, stop. A Lambda bridge is a
  spec amendment (new function, role, log group, and Plane-A infra edge), not
  an in-flight redesign — route it back to the architect rather than building
  it under this spec.
- **Scope guard**: no alarms, SNS topics, metric filters, dashboards, second
  schedules, or schedule groups. Spec 06 owns alerting; this spec only *emits*
  the DLQ and session-id hooks it will consume.
- **Cost**: nothing recurring is created by Phase 1–3, and Phase 4 leaves the
  schedule `DISABLED`. The only spend in this spec is the redeployed agent plus
  the two or three live curation runs in Tasks 4.2/4.5/4.7 (Haiku-only, capped
  by `SPIKE_MAX_ITEMS`).

## Executor completion (Phases 1–2)

- **Completed**: 2026-08-03. Tasks 1.1–1.14 and 2.1–2.7 all done, no deviations
  from contract.md's pinned construct/stack code (copied verbatim).
- `uv run pytest tests/test_infra_curation_schedule.py -v` — 15/15 passed.
- `uv run pytest tests/` — 82/82 passed, no regressions.
- `uv run --group infra cdk synth --app "python infra/app.py" AiRadarSchedule`
  succeeded with no AWS credentials set; emitted template matches contract.md's
  oracle byte-for-byte on every asserted field (cron expression, timezone,
  `State: DISABLED`, `FlexibleTimeWindow`, target `Arn`/`Input`/`RetryPolicy`/
  `DeadLetterConfig`, exactly two IAM policy statements, zero `Resource: "*"`,
  SSM `Value<String>` template parameter, all eight outputs). No
  `cdk.context.json` written; no `defaultWildcardResourcePolicy` warning.
- `git status`/`git diff` confirmed scope: `infra/app.py` modified (2 lines +
  docstring), `infra/lib/curation_schedule.py` and
  `infra/stacks/curation_schedule_stack.py` created — nothing under `src/**`,
  `runtime_app.py`, `Dockerfile`, `.dockerignore`, `infra/lib/agent_runtime.py`,
  `infra/stacks/agent_runtime_stack.py`, `infra/lib/card_store.py`, or
  `infra/stacks/card_store_stack.py` touched. No `uv add` run;
  `pyproject.toml`/`uv.lock` unchanged.
- Phase 3 (test suite) was already complete (test-writer's job, per the task
  prompt) and is left as-is. Phase 4 (real deploy / live fire / README
  runbook) is the separate manual runbook, not executed here.

## Executor completion (Phase 4)

- **Completed**: 2026-08-10. Real deploy + live fire executed for real against
  AWS; README/CLAUDE.md runbook and spec-status updates done by the
  sdd-documentarian agent immediately after.
- Tasks 4.1, 4.2, 4.3, 4.5, 4.6, 4.8, 4.9, 4.10 checked off with evidence
  notes above (agent redeploy → `Ready`; baseline scan; SSM parameter fixed
  after discovering it held the wrong — IAM role, not runtime — ARN from an
  earlier session's stale attempt; live-fire deploy + fire at 21:09:05 UTC
  confirmed by card count 24→32, DLQ at 0, and a matching CloudWatch log
  stream; return-to-inert redeploy confirmed `DISABLED`/default cron/timezone;
  README runbook + spec table + test count updated).
- Tasks 4.4 and 4.7 left **unchecked**: 4.4 (a standalone plain/disabled
  `cdk deploy AiRadarSchedule` + verify, ordered *before* the live fire) has
  no separate evidence in this session's record — the record goes directly
  from the SSM fix to the live-fire override deploy. 4.7 (double-fire /
  dedup check) was explicitly **not performed** this session — recorded
  honestly rather than assumed complete.
- Task 4.11 (optional teardown) left **unchecked**: it is explicitly optional
  and was not performed — `AiRadarSchedule` (disabled) and `AiRadarRuntimeRole`
  (the agent) are both still live in AWS as of this session's end, with
  ongoing cost exposure from the running agent.
- No other sections of this file were modified; intent.md, contract.md, and
  roadmap.md were not touched, per instruction.

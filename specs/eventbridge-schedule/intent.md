# Intent: eventbridge-schedule

## Problem Statement

Spec 04 (`runtime-packaging`) put the curation graph in the cloud as an
AgentCore Runtime agent — but it only runs when a human types
`agentcore invoke '{}'`. That is not a feed; it is a manually-cranked script
that happens to live in AWS. The Phase 1 deliverable from design §8 is an
**automated daily feed**, and design §3/§5 name the mechanism: "EventBridge
Scheduler triggers the AgentCore Runtime endpoint" on a recurring schedule.

This spec closes that gap with the smallest possible piece of infrastructure:
one **EventBridge Scheduler** schedule (CDK Python, `infra/`) whose target is
the deployed Spec 04 agent, firing once a day, unattended. Nothing about the
agent changes — Spec 04's handler already **accepts and ignores** its payload
(`runtime_app.py`: "`payload` is accepted (SDK signature) but ignored — all
config is env-driven"), so the schedule's only job is to make the call.

Who is affected: the operator (stops hand-cranking runs; gains a DLQ + retry
policy instead of "did I remember to invoke it?"), Phase 2 (a feed API needs a
table that fills itself), and Spec 06 (`run-observability`), which needs a
recurring, unattended run to have anything worth observing.

Two things make this less trivial than "add a cron":

1. EventBridge Scheduler has **no templated target for AgentCore Runtime**.
   The only route is the **universal target**
   (`arn:aws:scheduler:::aws-sdk:{service}:{apiAction}`), whose wire contract
   (service identifier, PascalCase parameter names, blob encoding) is derived
   from the AWS SDK model rather than from a typed CDK API — so it cannot be
   proven correct by `cdk synth` alone. It has to be fired for real once.
2. The Runtime agent's ARN is created by the `agentcore` CLI, **outside
   CloudFormation**. CDK has to learn it without a cross-stack export and
   without breaking the repo's "tests run with no AWS credentials" rule.

## Goals

1. Add an **EventBridge Scheduler schedule** (CDK Python construct → stack →
   `infra/app.py`, matching the Spec 03/04 pattern) that invokes the deployed
   Spec 04 Runtime agent once a day via the **universal target**
   `bedrockagentcore:invokeAgentRuntime`, with the cadence and timezone
   changeable in **one place**.
2. Send the invocation payload **`{}`** — literally the same payload the
   verified manual smoke test uses. Zero changes to `runtime_app.py`, the
   execution role, the Dockerfile, or `src/`. Per-run tuning (`SPIKE_MAX_ITEMS`
   et al.) stays a container env var, set via `agentcore configure --env`.
3. Give the Scheduler an invoke role scoped to **`bedrock-agentcore:InvokeAgentRuntime`
   on that one agent's ARN (+ its `DEFAULT` runtime endpoint) only** — no
   wildcard resources, matching Spec 04's least-privilege house style.
4. Configure a **batch-appropriate delivery policy**: a 15-minute flexible time
   window (this is an off-peak batch job, not a latency-sensitive trigger), a
   **bounded 3 retry attempts** (not the CDK/Scheduler default of 185), a
   2-hour max event age, and a **dead-letter SQS queue** so a run that fails
   every retry lands somewhere visible instead of vanishing.
5. Wire the deployed agent's ARN into CDK through an **SSM Parameter Store
   parameter** (`/ai-radar/agent-runtime-arn`), written by a human after
   `agentcore deploy`, read by CDK as a **deploy-time CloudFormation dynamic
   reference** — so `cdk synth` and the pytest synth tests keep working with no
   AWS credentials and no `cdk.context.json` lookup.
6. Deploy the schedule **`enabled=False`** (`State: DISABLED`). It exists, is
   fully configured, and costs nothing recurring until a human deliberately
   turns it on.
7. **Really deploy it and really fire it once**: redeploy Spec 04's agent (it
   is currently torn down), deploy this stack, drive one live invocation
   through Scheduler → AgentCore → DynamoDB, and confirm the card count moved.
   The universal-target wire shape is a genuine unknown that only a live fire
   can settle (see Constraints).
8. Deliver a **runbook** covering deploy, the live fire, how a human later
   flips the schedule to `ENABLED` (and that doing so starts real recurring
   cost), and teardown — including the still-applicable Spec 04
   `agentcore destroy` execution-role gotcha.

## Success Criteria

- [ ] `AiRadarSchedule` synthesizes an `AWS::Scheduler::Schedule` with
      `ScheduleExpression: cron(0 6 * * ? *)`,
      `ScheduleExpressionTimezone: Etc/UTC`, `State: DISABLED`, and
      `FlexibleTimeWindow: {Mode: FLEXIBLE, MaximumWindowInMinutes: 15}`.
- [ ] The target ARN is
      `arn:<partition>:scheduler:::aws-sdk:bedrockagentcore:invokeAgentRuntime`
      and the target `Input` carries `AgentRuntimeArn` (from the SSM parameter)
      and `Payload: "{}"`.
- [ ] `RetryPolicy` is `{MaximumRetryAttempts: 3, MaximumEventAgeInSeconds: 7200}`
      and `DeadLetterConfig.Arn` points at the new SQS queue.
- [ ] The Scheduler role's policy contains exactly two statements —
      `bedrock-agentcore:InvokeAgentRuntime` on the agent ARN + its
      `runtime-endpoint/DEFAULT` ARN, and `sqs:SendMessage` on the DLQ — with
      **no `Resource: "*"` anywhere** (CDK's default universal-target policy
      *is* `"*"`; it must be overridden).
- [ ] The role's trust policy admits only `scheduler.amazonaws.com` under
      `aws:SourceAccount` + `aws:SourceArn` (schedule-group) conditions.
- [ ] Cadence, timezone, and enabled-state each change in exactly one place
      (a module-level default in `infra/lib/curation_schedule.py`, overridable
      per-deploy with `cdk deploy -c ...`).
- [ ] **Live**: one real Scheduler-driven invocation reaches the agent and the
      `ai-radar-cards` item count increases, with the DLQ empty and no human
      touching `agentcore invoke`.
- [ ] **Live, double-fire**: a second fire creates **no duplicate card for an
      already-curated URL** (same `card_id`, `upsert` replaces in place,
      `created_at` preserved). It may still add *new* cards — that is the
      bounded-slice behavior documented in Spec 04's smoke test, not a bug.
- [ ] `cdk destroy AiRadarSchedule` removes the schedule, the DLQ, and the
      Scheduler role, leaving the RETAINed `ai-radar-cards` table intact.
- [ ] `uv run pytest tests/` stays 100% offline — the new stack is synth-tested
      via `Template.from_stack` with no credentials, no `cdk deploy`, no
      `cdk.context.json`.
- [ ] `git diff` shows **zero** changes under `src/`, `runtime_app.py`,
      `Dockerfile`, and `infra/lib/agent_runtime.py`.

## Non-Goals

- **Any change to the Runtime agent** — `runtime_app.py`, its execution role,
  the `Dockerfile`, `.dockerignore`, and everything under `src/` are untouched.
  In particular the task doc's suggested
  `{"trigger": "scheduled", "max_items": N}` payload is **rejected**: Spec 04's
  handler ignores `payload` entirely, so a richer payload would be decorative
  at best and misleading at worst.
- **Alerting / metrics / dashboards on run health** — Spec 06. This spec
  deliberately *emits* the signal Spec 06 will consume (a message landing in
  the DLQ, plus the schedule's own CloudWatch metrics) but builds no alarm, no
  SNS topic, and no subscription.
- **Multiple cadences, per-topic schedules, or a schedule group** — one
  schedule, in the `default` group.
- **Turning the schedule on.** Deployment leaves it `DISABLED`; going live is a
  documented, deliberate human act.
- **A Lambda bridge between Scheduler and AgentCore.** The universal target is
  the design. If the live fire proves AgentCore is not invocable that way, that
  is a spec amendment, not an in-flight redesign (see roadmap Risk Assessment).
- **EventBridge Scheduler's `at()` one-shot schedules, schedule groups, KMS
  customer-managed keys, or `start`/`end` windows.**
- **Plane B / chat / AgentCore Memory** — untouched.

## Constraints

- **Universal target only.** EventBridge Scheduler ships no native/templated
  target for Bedrock AgentCore Runtime. `aws_cdk.aws_scheduler_targets.Universal`
  is the mechanism (verified against the installed `aws-cdk-lib==2.261.0`).
- **Two unverifiable-offline wire details.** CDK validates only that `service`
  is lowercase and `action` is camelCase and not read-only-prefixed — it cannot
  tell a right service identifier from a wrong one. Both of the following are
  pinned from AWS documentation + the botocore service model, and both are
  confirmable **only** by a live fire:
  - `service="bedrockagentcore"` — Scheduler requires the **SDK service
    identifier** (botocore `serviceId` "Bedrock AgentCore", lowercased,
    spaces stripped), which differs from the endpoint prefix
    `bedrock-agentcore`. (AWS's own worked example: Cognito IdP is
    `cognitoidentityprovider`, not `cognito-idp`.)
  - `Input` uses **PascalCase** member names (`AgentRuntimeArn`, `Payload`),
    per Step Functions' identical `aws-sdk:` integration rule — "Parameters …
    are expressed in PascalCase, even if the native service API is in
    camelCase" — and Scheduler's own PascalCase examples. The blob-typed
    `payload` goes as a **plain UTF-8 string**, not base64, per AWS's Lambda
    universal-target example.
  Both must therefore be **single-constant, one-line-changeable** props with
  the fallback documented, and the live fire is a required deliverable.
- **IAM prefix ≠ target service string.** The IAM action stays
  `bedrock-agentcore:InvokeAgentRuntime` (botocore `signingName`) while the
  target ARN uses `bedrockagentcore`. CDK's auto-derived default policy would
  get this wrong *and* scope it to `"*"` — explicit `policy_statements` are
  mandatory, not stylistic.
- **Agent ARN is not a CloudFormation resource.** It is created by the
  `agentcore` CLI. It must reach CDK without a cross-stack export and without
  making `cdk synth` require credentials — hence a deploy-time SSM dynamic
  reference (`StringParameter.value_for_string_parameter`), never a synth-time
  `value_from_lookup`.
- **Offline test suite.** The repo's rule (Spec 04 Behavior Guarantee 9,
  `tests/test_infra_agent_runtime.py`) is that every CDK assertion is
  `Template.from_stack`, no credentials, no network. This spec must not break
  that.
- **Cost discipline ($500 credits).** The schedule ships DISABLED; enabling it
  costs one AgentCore Runtime curation run per day (Haiku-only, capped by
  `SPIKE_MAX_ITEMS`). EventBridge Scheduler is $0 under the 14M-invocation free
  tier; the SQS DLQ is effectively $0 (a message a *failure*, well inside the
  1M-request free tier). No OpenSearch, no Lambda, no NAT.
- **`agentcore destroy` gotcha still applies.** Redeploying Spec 04's agent for
  the live fire means re-entering the same teardown trap: `agentcore destroy`
  will `iam:DeleteRole` whatever ARN sits in `.bedrock_agentcore.yaml`'s
  `aws.execution_role` — including the CDK-owned one — unless that field is
  nulled first. The runbook must repeat this.
- **CDK/CFN dependency order.** The SSM parameter must exist *before*
  `cdk deploy` of this stack; the agent must exist before the parameter. The
  runbook order is therefore fixed: agent → SSM parameter → schedule stack.

## Prior Art

- **`specs/runtime-packaging/contract.md`** — the contract this spec targets:
  the `@app.entrypoint def handler(payload)` that ignores its payload, the
  explicit-`iam.PolicyStatement` least-privilege style (never `grant_*()`), the
  documented single-wildcard exception, and an "Integration Points" entry that
  already names this spec ("invokes the handler with `{}` and receives the
  run-summary dict").
- **`infra/lib/card_store.py`, `infra/lib/agent_runtime.py`,
  `infra/stacks/*.py`, `infra/app.py`** — the construct-exposes-attributes →
  stack-wraps-construct-plus-`CfnOutput`s → flat-module-`sys.path` app pattern
  this spec copies exactly.
- **`tests/test_infra_agent_runtime.py`** — the synth-only assertion style
  (`_resources_of_type`, `_statement_by_sid`, "the only wildcard is X"), reused
  verbatim in shape for the new stack's tests.
- **README.md § "AgentCore Runtime deploy"** — the deploy/smoke/teardown runbook
  this spec extends, including the `execution_role: null` gotcha and the honest
  note about what a re-invoke does and does not do.
- **Spec 02 Task 3.2 / Spec 04 Phase 4** — the "live third-party or live-AWS
  step is a manual runbook step, never an automated test" precedent.
- **External (verified 2026-08):** `aws_cdk.aws_scheduler_targets.Universal`
  and `ScheduleTargetBase` sources (aws/aws-cdk `main`); AWS EventBridge
  Scheduler *Using universal targets* and *Adding context attributes* user-guide
  pages; AWS Step Functions *AWS SDK service integrations* PascalCase rule;
  botocore `bedrock-agentcore/2024-02-28/service-2.json` `InvokeAgentRuntime`
  model; `/aws/bedrock-agentcore-sdk-python` for the `bedrock-agentcore:InvokeAgentRuntime`
  IAM action name.

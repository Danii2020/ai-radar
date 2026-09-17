# Contract: eventbridge-schedule

> **Language & layout.** This spec is **infra-only**: AWS CDK v2 in **Python**
> (`aws-cdk-lib==2.261.0`, `constructs==10.7.1`), under `infra/`, following the
> Spec 03/04 construct → stack → app pattern, plus one synth-only pytest file.
> It adds **one construct, one stack, one `infra/app.py` line, one test file**,
> and README runbook prose. **No file under `src/`, no `runtime_app.py`, no
> `Dockerfile`, no `infra/lib/agent_runtime.py` change.** No new runtime
> dependency: `aws_cdk.aws_scheduler`, `aws_cdk.aws_scheduler_targets`,
> `aws_cdk.aws_sqs`, and `aws_cdk.aws_ssm` all ship inside `aws-cdk-lib`, which
> is already in the `infra` dependency group.

## AWS / library API surface (pinned via Context7 + AWS docs + source — do not trust memory)

Verified 2026-08 against the **installed** `aws-cdk-lib==2.261.0` and
`botocore==1.43.56` in this repo's `.venv`, plus:
`/websites/aws_amazon_cdk_api_v2_python` (`aws_cdk.aws_scheduler_targets.Universal`,
`UniversalTargetProps`, `ScheduleTargetBaseProps`, `aws_cdk.aws_scheduler.Schedule`,
`CronOptionsWithTimezone`); `aws/aws-cdk@main`
`packages/aws-cdk-lib/aws-scheduler-targets/lib/{universal.ts,target.ts}` and
`packages/aws-cdk-lib/custom-resources/lib/helpers-internal/sdk-info.ts`; AWS
EventBridge Scheduler User Guide *Using universal targets* and *Adding context
attributes*; AWS Step Functions *AWS SDK service integrations* (PascalCase
rule); botocore `bedrock-agentcore/2024-02-28/service-2.json`
(`InvokeAgentRuntime`); `/aws/bedrock-agentcore-sdk-python` (IAM action name).

### `aws_cdk.aws_scheduler_targets.Universal` — pinned signature

```python
Universal(
    *,
    action: str,                                    # required, camelCase
    service: str,                                   # required, lowercase
    policy_statements: Sequence[iam.PolicyStatement] | None = None,
    dead_letter_queue: sqs.IQueue | None = None,
    input: scheduler.ScheduleTargetInput | None = None,
    max_event_age: Duration | None = None,          # 60s … 86400s, default 24h
    retry_attempts: int | float | None = None,      # 0 … 185, default 185
    role: iam.IRole | None = None,                  # default: created by target
)
```

- Target ARN is built as
  `arn:{Aws.PARTITION}:scheduler:::aws-sdk:{service}:{action}`.
- **Validation is shallow.** The constructor only checks that `service` is
  lowercase, that `action` starts lowercase, and that `action` does not start
  with one of 26 read-only prefixes (`get`, `describe`, `list`, … , `invokeModel`).
  `invokeAgentRuntime` passes: no prefix in that list matches it (`invokeModel`
  is not a prefix of `invokeAgentRuntime`). **CDK cannot tell a correct
  `service` identifier from an incorrect one** — hence the live fire.
- **`policy_statements` is mandatory here.** Source (`universal.ts`
  `addTargetActionToRole`): when omitted, CDK attaches
  `PolicyStatement(actions=[awsSdkToIamAction(service, action)], resources=["*"])`
  and emits the warning `@aws-cdk/aws-scheduler-targets:defaultWildcardResourcePolicy`
  — "Default policy with * for resources is used." For this service it would
  *also* derive the **wrong** IAM prefix: `awsSdkToIamAction` looks up
  `iamPrefix` in `sdk-v3-metadata.json` keyed by the normalized service name
  and falls back to that name, yielding `bedrockagentcore:InvokeAgentRuntime`
  rather than the real `bedrock-agentcore:InvokeAgentRuntime`. Supplying
  `policy_statements` bypasses both defects.

### The target role CDK creates (verified — deliberately **not** hand-rolled)

Source: `target.ts` `ScheduleTargetBase.createOrGetScheduleTargetRole`. When
`role` is omitted, CDK creates `SchedulerRoleForTarget-<md5(targetArn)[:6]>` in
the schedule's stack with this trust policy, which is **already correctly
scoped** (this is the verification the roadmap's design decision rests on):

```json
{
  "Effect": "Allow",
  "Action": "sts:AssumeRole",
  "Principal": { "Service": "scheduler.amazonaws.com" },
  "Condition": { "StringEquals": {
    "aws:SourceAccount": { "Ref": "AWS::AccountId" },
    "aws:SourceArn": "arn:<partition>:scheduler:<region>:<account>:schedule-group/default"
  }}
}
```

Its permissions come **entirely** from our explicit `policy_statements`, plus
one CDK-added `sqs:SendMessage` on the DLQ ARN (`addDeadLetterQueueActionToRole`).
Net result: a role with the same shape Spec 04's hand-written role has, with no
wildcards — so authoring a duplicate role by hand would add code and risk
without adding scoping.

### `bedrock-agentcore:InvokeAgentRuntime` — pinned request model

botocore `InvokeAgentRuntime` (`rest-json`, `POST /runtimes/{agentRuntimeArn}/invocations`):

| SDK member | Location | Required | Notes |
|---|---|---|---|
| `agentRuntimeArn` | uri | **yes** | the deployed agent's ARN |
| `payload` | body (blob, `"payload": "payload"` trait) | **yes** | shape `Body`, `blob`, 0–100 MB, `sensitive` |
| `runtimeSessionId` | header `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` | no (`idempotencyToken: true`) | shape `SessionType`: string, **min 33**, max 256, **no pattern constraint** |
| `contentType` | header `Content-Type` | no | shape `MimeType` |
| `qualifier` | querystring | no | defaults to the `DEFAULT` endpoint |

Metadata: `serviceId: "Bedrock AgentCore"`, `endpointPrefix: "bedrock-agentcore"`,
`signingName: "bedrock-agentcore"`.

### The two wire-shape rules that decide `service` and `Input` (pinned, live-verifiable only)

1. **`service` = SDK service identifier, not endpoint prefix.** AWS: "The
   `{{service}}` value in the universal target ARN must match the AWS SDK
   service identifier for the target service. This identifier can differ from
   the service's endpoint prefix. For example, for Amazon Cognito Identity
   Provider, use `cognitoidentityprovider` (not `cognito-idp`)." Cross-checked
   against botocore `serviceId` for every service in AWS's own examples:

   | AWS example | botocore `serviceId` | → universal `service` | `endpointPrefix` |
   |---|---|---|---|
   | `sqs:sendMessage` | `SQS` | `sqs` | `sqs` |
   | `rds:stopDBCluster` | `RDS` | `rds` | `rds` |
   | `sfn:startExecution` | `SFN` | `sfn` | **`states`** |
   | (doc note) | `Cognito Identity Provider` | `cognitoidentityprovider` | **`cognito-idp`** |
   | **this spec** | **`Bedrock AgentCore`** | **`bedrockagentcore`** | **`bedrock-agentcore`** |

   Rule: `serviceId.replace(" ", "").lower()`. → **`service="bedrockagentcore"`**.

2. **`Input` members are PascalCase; blob members are plain strings.** Step
   Functions' identical `aws-sdk:{{service}}:{{apiAction}}` integration
   documents: "Parameters in Step Functions are expressed in **PascalCase**,
   even if the native service API is in camelCase." Every Scheduler
   universal-target example follows suit (`MessageBody`/`QueueUrl`,
   `FunctionName`/`Payload`, `StateMachineArn`/`Input`). AWS's Lambda example
   passes the blob body **un-encoded**:
   `"Input": "{\"FunctionName\":\"…\",\"InvocationType\":\"Event\",\"Payload\":\"{\\\"message\\\":\\\"testing function\\\"}\"}"`
   — a plain JSON string, **not base64**. → `{"AgentRuntimeArn": …, "Payload": "{}"}`.

> **Both rules are single constants in the construct** (`UNIVERSAL_TARGET_SERVICE`,
> and the `Input` dict literal) precisely because neither can be proven by
> `cdk synth`. Fallbacks if the live fire fails, in order: `service="bedrock-agentcore"`;
> then camelCase members (`agentRuntimeArn`/`payload`); then base64
> `"Payload": "e30="`. See roadmap Risk Assessment for the decision procedure.

### Scheduler context attributes (pinned)

Substituted by Scheduler into the target `Input` at invocation time:
`<aws.scheduler.schedule-arn>`, `<aws.scheduler.scheduled-time>`,
`<aws.scheduler.execution-id>` (per-**attempt** unique id, e.g.
`d32c5kddcf5bb8c3` — ~16 chars), `<aws.scheduler.attempt-number>`.

### `aws_cdk.aws_scheduler` — pinned surface

```python
Schedule(scope, id, *, schedule: ScheduleExpression, target: IScheduleTarget,
         description: str | None = None,
         enabled: bool | None = None,          # default True → State: ENABLED
         time_window: TimeWindow | None = None,
         schedule_group=None, schedule_name=None, start=None, end=None, key=None)

ScheduleExpression.expression(expression: str, time_zone: TimeZone | None = None)
TimeWindow.flexible(max_window: Duration)
ScheduleTargetInput.from_object(obj) -> ScheduleTargetInput
TimeZone.of("Etc/UTC")                        # aws_cdk.TimeZone
```

- The L2 prop is **`enabled: bool`**, not `state`. `enabled=False` synthesizes
  `State: "DISABLED"` (confirmed by prototype synth, below).
- `ScheduleExpression.expression(expr, tz)` keeps the cron string and timezone
  as two plain literals → maps 1:1 onto `ScheduleExpression` /
  `ScheduleExpressionTimezone`, satisfying "configurable in one place" better
  than the field-by-field `.cron(minute=…, hour=…)` form.

### SSM wiring — deploy-time reference (chosen) vs synth-time lookup (rejected)

```python
ssm.StringParameter.value_for_string_parameter(scope, "/ai-radar/agent-runtime-arn")
```

Synthesizes a **CloudFormation parameter**, resolved by CFN at deploy time:

```json
"SsmParameterValueairadaragentruntimearn…Parameter": {
  "Type": "AWS::SSM::Parameter::Value<String>",
  "Default": "/ai-radar/agent-runtime-arn"
}
```

`StringParameter.value_from_lookup` is **rejected**: it resolves at synth time
via an SDK call, requiring live credentials and writing `cdk.context.json`,
which would break the "pytest synth tests need no AWS credentials" rule
(Spec 04 Behavior Guarantee 9). Verified by prototype synth: with
`value_for_string_parameter`, the whole stack synthesizes offline, and the
resulting token works both inside the target `Input` JSON string (CDK emits an
`Fn::Join`) **and** as an IAM `Resource` (emitted as a `Ref`).

### Prototype-verified synthesized template (the test-writer's oracle)

Synthesized offline, no credentials, from the exact construct below:

```json
"AWS::Scheduler::Schedule": {
  "Description": "AI Radar daily curation run (Spec 05) …",
  "ScheduleExpression": "cron(0 6 * * ? *)",
  "ScheduleExpressionTimezone": "Etc/UTC",
  "State": "DISABLED",
  "FlexibleTimeWindow": { "Mode": "FLEXIBLE", "MaximumWindowInMinutes": 15 },
  "Target": {
    "Arn": { "Fn::Join": ["", ["arn:", {"Ref": "AWS::Partition"},
             ":scheduler:::aws-sdk:bedrockagentcore:invokeAgentRuntime"]] },
    "RoleArn": { "Fn::GetAtt": ["SchedulerRoleForTarget…", "Arn"] },
    "Input": { "Fn::Join": ["", ["{\"AgentRuntimeArn\":\"",
               {"Ref": "SsmParameterValue…Parameter"}, "\", …\"Payload\":\"{}\"}"]] },
    "RetryPolicy": { "MaximumRetryAttempts": 3, "MaximumEventAgeInSeconds": 7200 },
    "DeadLetterConfig": { "Arn": { "Fn::GetAtt": ["Dlq…", "Arn"] } }
  }
}
```

and a `SchedulerRoleForTarget…DefaultPolicy` containing **exactly two**
statements — `bedrock-agentcore:InvokeAgentRuntime` on
`[<ssm ref>, <ssm ref>/runtime-endpoint/DEFAULT]` (Sid `InvokeCurationAgent`)
and `sqs:SendMessage` on the DLQ ARN — with **no `Resource: "*"` in the stack**.

## Interfaces

### CDK construct — `infra/lib/curation_schedule.py` (CREATE)

Mirrors `infra/lib/card_store.py` / `infra/lib/agent_runtime.py`: a `Construct`
that provisions resources and exposes them as attributes for the stack to
`CfnOutput`. **Every tunable is a module-level constant + a keyword prop** —
that is the "configurable in one place" contract.

```python
"""Reusable CDK construct: the daily EventBridge Scheduler schedule that
invokes the deployed AgentCore Runtime curation agent (Spec 05).

`infra/lib/` — NOT `infra/constructs/` — a local `constructs` package on
`sys.path` would shadow the CDK `constructs` library.
"""
from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy, TimeZone
from aws_cdk import aws_iam as iam
from aws_cdk import aws_scheduler as scheduler
from aws_cdk import aws_scheduler_targets as scheduler_targets
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_ssm as ssm
from constructs import Construct

# --- The "one place" for cadence/timezone/state (Success Criteria) ----------
# Override per-deploy with `cdk deploy -c schedule_expression=... -c
# schedule_timezone=... -c schedule_enabled=true` (see CurationScheduleStack).
DEFAULT_SCHEDULE_EXPRESSION = "cron(0 6 * * ? *)"   # 06:00 daily, off-peak
DEFAULT_TIMEZONE = "Etc/UTC"
DEFAULT_ENABLED = False                             # deploy inert; a human opts in

# SSM parameter a human writes AFTER `agentcore deploy` (the agent ARN is
# created by the CLI, outside CloudFormation). Read as a DEPLOY-TIME dynamic
# reference so `cdk synth` / pytest need no AWS credentials.
DEFAULT_AGENT_RUNTIME_ARN_PARAMETER = "/ai-radar/agent-runtime-arn"

# --- Universal-target wire constants (live-verifiable only; see contract) ---
# Scheduler wants the SDK SERVICE IDENTIFIER (botocore serviceId "Bedrock
# AgentCore" -> lowercased, spaces stripped), which is NOT the endpoint prefix
# "bedrock-agentcore". Cf. AWS's own example: cognitoidentityprovider, not
# cognito-idp. If a live fire returns a target-resolution error, this single
# literal is the first thing to try as "bedrock-agentcore".
UNIVERSAL_TARGET_SERVICE = "bedrockagentcore"
UNIVERSAL_TARGET_ACTION = "invokeAgentRuntime"
# The IAM action keeps the SIGNING NAME prefix — deliberately different from
# UNIVERSAL_TARGET_SERVICE above. CDK's auto-derived default would get this
# wrong AND scope it to "*", which is why policy_statements is explicit.
INVOKE_IAM_ACTION = "bedrock-agentcore:InvokeAgentRuntime"

# Spec 04's handler accepts but IGNORES its payload — all config is env-driven
# on the container. `{}` is byte-identical to the verified manual smoke test
# (`agentcore invoke '{}'`). A richer payload would be decorative.
INVOCATION_PAYLOAD = "{}"
RUNTIME_ENDPOINT_NAME = "DEFAULT"

# `runtimeSessionId` is SessionType: min length 33, max 256, no pattern. This
# prefix is 35 chars, so the value is valid even if the context attribute is
# not substituted. `<aws.scheduler.execution-id>` is unique per invocation
# ATTEMPT, so a retry starts a fresh AgentCore session (correct for a retried
# batch run) and the id is greppable in AgentCore logs (hook for Spec 06).
SESSION_ID_PREFIX = "ai-radar-scheduled-curation-run-id-"
SESSION_ID_CONTEXT_ATTRIBUTE = "<aws.scheduler.execution-id>"

# --- Batch-appropriate delivery policy -------------------------------------
DEFAULT_FLEXIBLE_WINDOW = Duration.minutes(15)   # off-peak batch; drift is fine
DEFAULT_RETRY_ATTEMPTS = 3                       # NOT the 185 default
DEFAULT_MAX_EVENT_AGE = Duration.hours(2)
DEFAULT_DLQ_RETENTION = Duration.days(14)


class CurationSchedule(Construct):
    """Daily EventBridge Scheduler schedule → AgentCore Runtime curation agent.

    Exposes `.schedule` (scheduler.Schedule), `.dead_letter_queue` (sqs.Queue),
    and `.agent_runtime_arn` (the deploy-time SSM token) for the stack to
    CfnOutput. The Runtime agent is REFERENCED by ARN via SSM — never created,
    modified, or imported as a CFN resource (it is CLI-owned, Spec 04).

    The Scheduler invoke role is the one `Universal` creates (verified
    least-privilege trust: scheduler.amazonaws.com + aws:SourceAccount +
    aws:SourceArn schedule-group conditions); its PERMISSIONS come only from
    the explicit `policy_statements` below — never CDK's `Resource: "*"`
    default.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        schedule_expression: str = DEFAULT_SCHEDULE_EXPRESSION,
        timezone: str = DEFAULT_TIMEZONE,
        enabled: bool = DEFAULT_ENABLED,
        agent_runtime_arn_parameter: str = DEFAULT_AGENT_RUNTIME_ARN_PARAMETER,
        flexible_window: Duration = DEFAULT_FLEXIBLE_WINDOW,
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
        max_event_age: Duration = DEFAULT_MAX_EVENT_AGE,
    ) -> None:
        super().__init__(scope, construct_id)

        # 1. Deploy-time reference to the CLI-created agent ARN. NOT
        #    value_from_lookup (synth-time; needs creds; breaks offline tests).
        self.agent_runtime_arn = ssm.StringParameter.value_for_string_parameter(
            self, agent_runtime_arn_parameter
        )

        # 2. Dead-letter queue for invocations that exhaust every retry — the
        #    "surfaced, not silently dropped" requirement. Spec 06 will alarm
        #    on ApproximateNumberOfMessagesVisible; this spec only emits.
        self.dead_letter_queue = sqs.Queue(
            self, "ScheduleDlq",
            queue_name="ai-radar-schedule-dlq",
            retention_period=DEFAULT_DLQ_RETENTION,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # 3. Universal target — no templated AgentCore target exists.
        target = scheduler_targets.Universal(
            service=UNIVERSAL_TARGET_SERVICE,
            action=UNIVERSAL_TARGET_ACTION,
            input=scheduler.ScheduleTargetInput.from_object({
                "AgentRuntimeArn": self.agent_runtime_arn,
                "RuntimeSessionId": f"{SESSION_ID_PREFIX}{SESSION_ID_CONTEXT_ATTRIBUTE}",
                "ContentType": "application/json",
                "Payload": INVOCATION_PAYLOAD,
            }),
            policy_statements=[
                iam.PolicyStatement(
                    sid="InvokeCurationAgent",
                    effect=iam.Effect.ALLOW,
                    actions=[INVOKE_IAM_ACTION],
                    resources=[
                        self.agent_runtime_arn,
                        f"{self.agent_runtime_arn}/runtime-endpoint/{RUNTIME_ENDPOINT_NAME}",
                    ],
                )
            ],
            retry_attempts=retry_attempts,
            max_event_age=max_event_age,
            dead_letter_queue=self.dead_letter_queue,
        )

        # 4. The schedule itself — DISABLED on deploy.
        self.schedule = scheduler.Schedule(
            self, "DailyCuration",
            schedule=scheduler.ScheduleExpression.expression(
                schedule_expression, TimeZone.of(timezone)
            ),
            target=target,
            enabled=enabled,
            description=(
                "AI Radar daily curation run (Spec 05) — invokes the AgentCore "
                "Runtime curation agent with an empty payload; all config is "
                "env-driven on the container."
            ),
            time_window=scheduler.TimeWindow.flexible(flexible_window),
        )
```

### CDK stack — `infra/stacks/curation_schedule_stack.py` (CREATE)

Mirrors `agent_runtime_stack.py` exactly: wrap the construct, emit `CfnOutput`s.
CDK **context** reads live here (the stack is the app-facing seam), so
`infra/app.py` keeps the one-line-per-stack shape it has today.

```python
"""CDK stack wrapping `CurationSchedule` (Spec 05: eventbridge-schedule)."""
from __future__ import annotations

from aws_cdk import CfnOutput, Stack
from constructs import Construct

from lib.curation_schedule import (  # infra/ on sys.path via app.py
    DEFAULT_AGENT_RUNTIME_ARN_PARAMETER,
    DEFAULT_ENABLED,
    DEFAULT_SCHEDULE_EXPRESSION,
    DEFAULT_TIMEZONE,
    CurationSchedule,
)


class CurationScheduleStack(Stack):
    """Cadence/timezone/enabled are overridable per-deploy via CDK context:

        cdk deploy -c schedule_expression="cron(5 14 * * ? *)" \
                   -c schedule_timezone="America/New_York" \
                   -c schedule_enabled=true

    Defaults (the "one place") live in lib/curation_schedule.py.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        expression = self.node.try_get_context("schedule_expression") or DEFAULT_SCHEDULE_EXPRESSION
        timezone = self.node.try_get_context("schedule_timezone") or DEFAULT_TIMEZONE
        parameter = (
            self.node.try_get_context("agent_runtime_arn_parameter")
            or DEFAULT_AGENT_RUNTIME_ARN_PARAMETER
        )
        # `-c schedule_enabled=true` arrives as the STRING "true"; anything
        # else (including absent) keeps the inert default.
        raw_enabled = self.node.try_get_context("schedule_enabled")
        enabled = DEFAULT_ENABLED if raw_enabled is None else str(raw_enabled).lower() == "true"

        curation_schedule = CurationSchedule(
            self, "CurationSchedule",
            schedule_expression=expression,
            timezone=timezone,
            enabled=enabled,
            agent_runtime_arn_parameter=parameter,
        )

        CfnOutput(self, "ScheduleName", value=curation_schedule.schedule.schedule_name)
        CfnOutput(self, "ScheduleArn", value=curation_schedule.schedule.schedule_arn)
        CfnOutput(self, "ScheduleExpression", value=expression)
        CfnOutput(self, "ScheduleTimezone", value=timezone)
        CfnOutput(self, "ScheduleEnabled", value=str(enabled))
        CfnOutput(self, "DeadLetterQueueUrl", value=curation_schedule.dead_letter_queue.queue_url)
        CfnOutput(self, "DeadLetterQueueArn", value=curation_schedule.dead_letter_queue.queue_arn)
        CfnOutput(self, "AgentRuntimeArnParameter", value=parameter)
```

### CDK app — `infra/app.py` (MODIFY: two lines)

```python
from stacks.curation_schedule_stack import CurationScheduleStack  # noqa: E402
...
CardStoreStack(app, "AiRadarCardStore")
AgentRuntimeStack(app, "AiRadarRuntimeRole")
CurationScheduleStack(app, "AiRadarSchedule")
app.synth()
```

The module docstring is updated to say "Specs 03–05". Phase 1 infra now
deploys/tears down together (`cdk deploy --all` / per-stack), per the source
task's explicit scope requirement.

### Operator interface — SSM parameter (MANUAL, not CDK)

The one manual wiring step, between `agentcore deploy` and `cdk deploy`:

```bash
# After `agentcore status` confirms the agent is READY:
AGENT_ARN=$(agentcore status --json | jq -r '.agent.agent_arn')   # or copy from `agentcore status`
aws ssm put-parameter --name /ai-radar/agent-runtime-arn \
  --type String --value "$AGENT_ARN" --overwrite
```

**Not** created by CDK: the value does not exist at synth time, is produced by
a non-CloudFormation tool, and must survive `cdk destroy` of this stack so a
redeploy does not need re-discovery. It is a plain `String` parameter (Standard
tier, free) holding a public ARN — no `SecureString`, no secret.

## Data Models

No application data model changes. `Card`, `RawItem`, `CurationState`, the
DynamoDB key schema, and the Spec 04 handler return shape are **untouched**.

The only new "model" is the invocation wire payload — the JSON string Scheduler
sends as the `InvokeAgentRuntime` request:

```python
# Target Input (PascalCase per the aws-sdk: integration rule), before
# Scheduler substitutes context attributes:
{
    "AgentRuntimeArn": "arn:aws:bedrock-agentcore:us-east-1:536697225154:runtime/<id>",
    "RuntimeSessionId": "ai-radar-scheduled-curation-run-id-<aws.scheduler.execution-id>",
    "ContentType": "application/json",
    "Payload": "{}",          # ← the agent's request BODY, plain string, not base64
}
```

The agent's response (Spec 04's run-summary dict: `discovered`, `deduped`,
`summarized`, `failed`, `persisted`, `discoverer_failures`, `store_failures`,
`tavily_enabled`) is returned to Scheduler and **discarded** — Scheduler has no
response destination. It remains visible in the AgentCore runtime log group,
which is exactly what Spec 06 will consume.

## State Changes

- **New CloudFormation resources** (stack `AiRadarSchedule`):
  `AWS::Scheduler::Schedule`, `AWS::SQS::Queue` (+ its TLS-enforcing
  `AWS::SQS::QueuePolicy`), `AWS::IAM::Role` + `AWS::IAM::Policy` (the
  CDK-created Scheduler target role), and one `AWS::SSM::Parameter::Value<String>`
  **template parameter**.
- **Referenced, never created/modified**: the AgentCore Runtime agent (CLI-owned,
  Spec 04), the `ai-radar-cards` table (RETAINed, Spec 03), the Spec 04
  execution role and Tavily secret, the SSM parameter itself.
- **No graph/pipeline state change.** The curation graph, its nodes, state, and
  interfaces stay byte-for-byte identical; `runtime_app.py` is not opened.
- **Runtime effect while `DISABLED`** (the deployed default): none. The
  schedule exists and never fires; no invocations, no Bedrock spend, no
  DynamoDB writes.
- **Runtime effect once `ENABLED`**: one `InvokeAgentRuntime` per day inside the
  15-minute window after 06:00 `Etc/UTC`, each producing one bounded curation
  run (≤ `SPIKE_MAX_ITEMS` newly-summarized items) that upserts into
  `ai-radar-cards` — i.e. the table grows unattended.

## Behavior Guarantees

1. **Spec 04 is untouched.** `runtime_app.py`, `Dockerfile`, `.dockerignore`,
   `infra/lib/agent_runtime.py`, and everything under `src/` are byte-for-byte
   unchanged (`git diff` clean for those paths). The schedule adapts to the
   existing contract; the contract does not bend for the schedule.
2. **Empty payload.** The target sends `Payload: "{}"` — byte-identical to the
   verified `agentcore invoke '{}'` smoke test. All per-run tuning stays a
   container env var (`SPIKE_MAX_ITEMS`, `SPIKE_PER_FEED`, `CURATION_TAVILY_*`,
   `CARD_TABLE_NAME`), settable via `agentcore configure --env` with no
   schedule change and no image rebuild.
3. **Inert on deploy.** The synthesized schedule has `State: "DISABLED"`.
   Deploying this stack starts **no** recurring cost. Enabling is a deliberate
   `cdk deploy -c schedule_enabled=true` (or console toggle), documented as
   starting real daily spend.
4. **One place for cadence.** Changing the daily time or timezone means editing
   exactly one of `DEFAULT_SCHEDULE_EXPRESSION` / `DEFAULT_TIMEZONE` in
   `infra/lib/curation_schedule.py`, or passing `-c schedule_expression=` /
   `-c schedule_timezone=` at deploy. No other file encodes the cadence.
5. **Least privilege, zero wildcards.** The Scheduler role's policy contains
   exactly two statements: `bedrock-agentcore:InvokeAgentRuntime` on the one
   agent ARN + its `runtime-endpoint/DEFAULT` ARN, and `sqs:SendMessage` on the
   DLQ ARN. **No statement in the entire stack uses `Resource: "*"`** — a
   stricter bar than Spec 04, which has one documented
   `ecr:GetAuthorizationToken` exception. CDK's default wildcard universal-target
   policy is explicitly overridden.
6. **Trust scoping.** The role is assumable only by `scheduler.amazonaws.com`
   under `aws:SourceAccount` (this account) and `aws:SourceArn` (this region's
   `schedule-group/default`) conditions.
7. **Failures are surfaced, never dropped.** A failing invocation is retried up
   to 3 times within a 2-hour max event age; if all attempts fail, Scheduler
   delivers the failed event to `ai-radar-schedule-dlq` (14-day retention). A
   non-empty DLQ is the machine-readable "a daily run did not happen" signal
   Spec 06 will alarm on.
8. **Double-fire is safe for existing cards.** A duplicated or retried fire
   never creates a second card for an already-curated URL: `card_id` is derived
   from the URL, `DynamoCardStore.dedup_filter` excludes already-stored items
   before summarizing, and `upsert` is insert-or-replace preserving `created_at`
   and the reserved `embedding`. It **may** still add *new* cards — each run
   curates the next bounded slice (`SPIKE_MAX_ITEMS`), exactly as documented in
   Spec 04's 2026-07-28 smoke test. That is incremental curation, not a dedup
   defect.
9. **Fresh session per attempt.** Each invocation attempt carries a distinct
   `RuntimeSessionId` (`SESSION_ID_PREFIX` + `<aws.scheduler.execution-id>`),
   satisfying the ≥33-character `SessionType` constraint even if the context
   attribute is not substituted, and never pinning successive daily runs to one
   long-lived AgentCore session.
10. **Offline synth tests.** `tests/test_infra_curation_schedule.py` asserts the
    whole stack via `Template.from_stack` — no `cdk deploy`, no credentials, no
    network, no `cdk.context.json`. This holds *because* the agent ARN is a
    deploy-time SSM dynamic reference rather than a synth-time lookup.
11. **Clean teardown.** `cdk destroy AiRadarSchedule` removes the schedule, the
    DLQ + its policy, and the Scheduler role. The `ai-radar-cards` table
    (RETAIN), the SSM parameter (not CDK-owned), the Spec 04 execution role, and
    the Runtime agent are untouched.
12. **Plane isolation preserved.** This spec adds no code to `src/`, imports no
    application module from `infra/`, and touches nothing in Plane B. `Card`
    remains the only shared contract.

## Error Handling Contract

| Error Condition | Behavior | User Impact |
|---|---|---|
| SSM parameter `/ai-radar/agent-runtime-arn` missing at `cdk deploy` | CloudFormation fails resolving the `AWS::SSM::Parameter::Value<String>` parameter; the stack rolls back before creating anything | Deploy fails fast with an explicit "SSM parameter not found" message; runbook step order (agent → SSM → stack) is the fix |
| SSM parameter holds a stale ARN (agent redeployed under a new id) | Schedule deploys fine; live invocations fail `ResourceNotFoundException` → 3 retries → DLQ | No cards that day; a DLQ message names the failure. Fix: re-`put-parameter` + `cdk deploy` |
| `service="bedrockagentcore"` is the wrong identifier | `cdk synth`/`deploy` succeed (CDK validates only casing); the live fire fails at invoke time → retries → DLQ | Live-fire step catches it; single-constant fallback to `bedrock-agentcore` documented in the runbook |
| `Input` casing/blob encoding wrong (`Payload` not accepted) | Invocation fails `ValidationException` → 3 retries → DLQ | Same as above; ordered fallbacks (camelCase members, then base64 `"e30="`) documented |
| Agent invocation exceeds Scheduler's target timeout | Scheduler treats it as a failed attempt and retries; the original run may still complete and persist cards | Possible extra run; harmless per Guarantee 8. Visible as >1 run in the AgentCore log group |
| Curation run itself fails partially (bad feed / item / card) | Handled entirely inside the agent (Specs 01–03 per-item try/except); the handler returns a summary with non-zero failure counters and **HTTP 200** | Scheduler sees success, no retry, no DLQ. Counters visible in the runtime log group (Spec 06's hook) |
| Curation run raises unexpectedly (agent returns an error) | Scheduler retries up to 3× within 2h; final failure → DLQ | DLQ message + AgentCore log traceback |
| Bedrock/DynamoDB access denied inside the agent | Spec 04's own contract governs (loud failure or elevated `failed` count) | Unchanged by this spec; the schedule is not the diagnosis point |
| Schedule fires while the agent is torn down | `ResourceNotFoundException` → retries → DLQ | Expected between deploys; keep the schedule `DISABLED` when the agent is down (documented) |
| Someone enables the schedule and forgets it | One curation run per day continues indefinitely | Real recurring cost; the runbook states this explicitly and gives the disable one-liner |
| DLQ accumulates messages | Retained 14 days, then dropped | Bounded storage; Spec 06 adds the alarm — this spec deliberately does not |
| `cdk deploy` run with a malformed `-c schedule_expression` | CloudFormation rejects the `ScheduleExpression` at create/update; stack rolls back | Deploy fails; previous schedule state preserved |

## Dependencies

- **Internal (referenced, not imported):** the Spec 04 Runtime agent (via its
  ARN in SSM), the Spec 03 `ai-radar-cards` table (written by the agent, not by
  this stack), the `infra/` flat-module `sys.path` convention from `infra/app.py`
  and `tests/test_infra*.py`.
- **Internal (imported):** none from `src/`. `infra/lib/curation_schedule.py`
  imports only `aws_cdk` + `constructs`. Plane A/B isolation is trivially
  preserved.
- **External (already present, no `uv add` needed):** `aws-cdk-lib>=2.261.0`
  (`aws_scheduler`, `aws_scheduler_targets`, `aws_sqs`, `aws_ssm`, `aws_iam`),
  `constructs>=10.7.1` — both in the existing `infra` dependency group;
  `pytest` (dev group) for the synth test. **`pyproject.toml` and `uv.lock` are
  unchanged by this spec.**
- **AWS (must exist before deploy):** the AgentCore Runtime agent (READY), the
  SSM parameter holding its ARN, the `ai-radar-cards` table (ACTIVE), the Spec
  04 execution role + populated Tavily secret, a CDK-bootstrapped account.

## Integration Points

- **Spec 04 (`runtime-packaging`)** — the target. Its contract already
  anticipates this spec ("Spec 05 … invokes the handler with `{}` and receives
  the run-summary dict"); this spec honors that literally and changes nothing
  on the agent side. Its README runbook (deploy → populate secret → configure →
  deploy → invoke → destroy, including the `execution_role: null` gotcha) is
  extended, not replaced.
- **Spec 03 (`dynamodb-card-store`)** — the observable outcome. The live-fire
  acceptance check is the `ai-radar-cards` item count moving without a human
  invoking anything. This stack holds no DynamoDB permission of its own; the
  agent's execution role does all the writing.
- **Specs 01–02 (`curation-graph`, `tavily-discovery`)** — reached only
  transitively through the agent. No graph, node, discoverer, or interface code
  is read or modified.
- **`infra/app.py`** — the third stack in the same app, so Phase 1 infra
  deploys and tears down together (source task requirement).
- **Spec 06 (`run-observability`)** — deliberately left two hooks and built
  neither alarm: (a) the DLQ, where `ApproximateNumberOfMessagesVisible > 0`
  means "a daily run failed every retry"; (b) the per-attempt `RuntimeSessionId`
  (`ai-radar-scheduled-curation-run-id-*`), which correlates a Scheduler
  attempt with its AgentCore log stream. Spec 06 also owns the schedule's own
  `AWS::Scheduler` CloudWatch metrics (`InvocationAttemptCount`,
  `TargetErrorCount`).
- **Phase 2 (feed API)** — the reason this matters: a feed backed by a table
  that fills itself daily, rather than when someone remembers to run a script.

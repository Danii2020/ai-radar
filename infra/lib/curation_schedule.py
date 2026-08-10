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

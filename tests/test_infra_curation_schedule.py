"""Tests for the daily EventBridge Scheduler schedule that invokes the
deployed AgentCore Runtime curation agent (Spec 05: eventbridge-schedule).

Spec: specs/eventbridge-schedule/contract.md "aws_cdk.aws_scheduler_targets.
Universal - pinned signature" + "Prototype-verified synthesized template (the
test-writer's oracle)" + "CDK construct - infra/lib/curation_schedule.py" +
"CDK stack - infra/stacks/curation_schedule_stack.py"; Behavior Guarantees
2-6, 9-10; specs/eventbridge-schedule/audit.md Test Coverage T1-T15;
specs/eventbridge-schedule/tasks.md Phase 3 (Tasks 3.1-3.7).

Synth-only: no `cdk deploy`, no AWS credentials, no network -
`aws_cdk.assertions.Template` inspects the synthesized CloudFormation
template in-process, matching tests/test_infra_agent_runtime.py's precedent
(Spec 04). Two of the pinned literals in this file - `UNIVERSAL_TARGET_SERVICE
= "bedrockagentcore"` and the target `Input`'s PascalCase/plain-string shape -
are, per contract.md, unverifiable by `cdk synth` alone; only a live fire
(tasks.md Phase 4, manual) proves them. These tests assert the *construct*
emits the pinned literals, not that AWS accepts them.

T15 (suite stays 100% offline, writes no cdk.context.json): there is no
per-test analog to assert in this file (mirroring test_infra_agent_runtime.py,
which has none either) - the guarantee is structural: this file imports no
`boto3`/`moto`, and every assertion here goes through `Template.from_stack`
(in-process synth, no `cdk deploy`). The regression this guards against - a
switch from `ssm.StringParameter.value_for_string_parameter` (deploy-time,
offline-safe) to `StringParameter.value_from_lookup` (synth-time, requires
credentials and writes `cdk.context.json`) - would NOT fail loudly in this
file; it would make every test in this file start requiring AWS credentials
and hang/fail in CI (which runs with none). CI having no AWS credentials
configured is what actually enforces R14/T15; `git status` after `uv run
pytest tests/` showing no new `cdk.context.json` is the manual corroboration
tasks.md Task 3.8 asks for.

RED phase: infra/lib/curation_schedule.py and
infra/stacks/curation_schedule_stack.py do not exist yet. Every test in this
file is expected to fail at collection with `ModuleNotFoundError: No module
named 'stacks.curation_schedule_stack'` (or similar) until Phase 2 (tasks.md
Tasks 2.1-2.5) lands.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Mirrors tests/test_infra_agent_runtime.py's convention:
# infra/stacks/curation_schedule_stack.py imports `from lib.curation_schedule
# import ...` as a flat module, i.e. infra/ itself (not its parent) is
# expected on sys.path - matching infra/app.py's own sys.path trick.
sys.path.insert(0, str(Path(__file__).parent.parent / "infra"))

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from stacks.curation_schedule_stack import CurationScheduleStack


def _synthesized_template(context: dict | None = None) -> Template:
    app = cdk.App(context=context or {})
    stack = CurationScheduleStack(app, "TestCurationScheduleStack")
    return Template.from_stack(stack)


def _resources_of_type(template_json: dict, resource_type: str) -> list[dict]:
    return [r for r in template_json["Resources"].values() if r["Type"] == resource_type]


def _all_policy_statements(template_json: dict) -> list[dict]:
    """Flatten every Statement across every synthesized AWS::IAM::Policy
    resource's PolicyDocument (defensive: walks all policy resources even
    though this stack is expected to attach every explicit grant to one
    Scheduler target role)."""
    statements: list[dict] = []
    for policy in _resources_of_type(template_json, "AWS::IAM::Policy"):
        statements.extend(policy["Properties"]["PolicyDocument"]["Statement"])
    return statements


def _every_iam_statement_in_stack(template_json: dict) -> list[dict]:
    """T9's regression scan: every statement in every AWS::IAM::Policy *and*
    every inline AWS::IAM::Role policy in the whole template - not just the
    one statement (InvokeCurationAgent) we expect to find. This is what
    catches CDK's default-wildcard-universal-target-policy bug even if it
    showed up somewhere unanticipated."""
    statements = list(_all_policy_statements(template_json))
    for role in _resources_of_type(template_json, "AWS::IAM::Role"):
        for inline_policy in role["Properties"].get("Policies", []):
            statements.extend(inline_policy["PolicyDocument"]["Statement"])
    return statements


def _statement_by_sid(statements: list[dict], sid: str) -> dict:
    matches = [s for s in statements if s.get("Sid") == sid]
    assert len(matches) == 1, f"expected exactly one statement with Sid={sid!r}, found {len(matches)}"
    return matches[0]


def _as_list(value) -> list:
    return value if isinstance(value, list) else [value]


def _flatten_arn_like_value(value) -> str:
    """Render a CFN intrinsic (Fn::Join over Ref/Fn::GetAtt tokens) or a plain
    literal string into a single string for substring assertions, without
    depending on whether the construct used tokens or literals."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and "Fn::Join" in value:
        delimiter, parts = value["Fn::Join"]
        return delimiter.join(part if isinstance(part, str) else "<token>" for part in parts)
    return str(value)


def _refs_in_join(value) -> list[str]:
    """Extract logical IDs from `{"Ref": ...}` parts inside an Fn::Join
    intrinsic (or a bare `{"Ref": ...}`), for asserting *which* CFN resource
    an interpolated string references without over-fitting to the exact
    Fn::Join shape CDK happens to emit."""
    if isinstance(value, dict) and "Ref" in value:
        return [value["Ref"]]
    if isinstance(value, dict) and "Fn::Join" in value:
        _, parts = value["Fn::Join"]
        return [p["Ref"] for p in parts if isinstance(p, dict) and "Ref" in p]
    return []


def _the_only_schedule(template_json: dict) -> dict:
    schedules = _resources_of_type(template_json, "AWS::Scheduler::Schedule")
    assert len(schedules) == 1, f"expected exactly one AWS::Scheduler::Schedule, found {len(schedules)}"
    return schedules[0]


def _agent_runtime_arn_ssm_parameters(template_json: dict) -> dict[str, dict]:
    """`AWS::SSM::Parameter::Value<String>` template parameters, excluding
    CDK's own `BootstrapVersion` parameter (every synthesized stack in a
    CDK-bootstrapped app carries one - it is not something this construct
    creates and asserting on it would be a false positive for C18/T12)."""
    return {
        logical_id: param
        for logical_id, param in template_json.get("Parameters", {}).items()
        if param.get("Type") == "AWS::SSM::Parameter::Value<String>" and logical_id != "BootstrapVersion"
    }


def _ssm_agent_arn_parameter_logical_id(template_json: dict) -> str:
    matches = list(_agent_runtime_arn_ssm_parameters(template_json))
    assert len(matches) == 1, f"expected exactly one SSM Value<String> template parameter, found {len(matches)}"
    return matches[0]


# T1 (R1/C11): exactly one AWS::Scheduler::Schedule, with the pinned daily
# cron expression and UTC timezone.
def test_schedule_resource_has_pinned_cron_expression_and_timezone():
    template_json = _synthesized_template().to_json()
    schedule = _the_only_schedule(template_json)["Properties"]

    assert schedule["ScheduleExpression"] == "cron(0 6 * * ? *)"
    assert schedule["ScheduleExpressionTimezone"] == "Etc/UTC"


# T2 (R6/Guarantee 3): the single most important regression to prevent - a
# flipped default here means every future `cdk deploy` silently starts a
# live recurring job.
def test_schedule_deploys_disabled_by_default():
    template_json = _synthesized_template().to_json()
    schedule = _the_only_schedule(template_json)["Properties"]

    assert schedule["State"] == "DISABLED"


# T3 (C11): the 15-minute flexible window is the batch-appropriate delivery
# choice from intent.md Goal 4, not the default (no time window at all).
def test_flexible_time_window_is_fifteen_minutes():
    template_json = _synthesized_template().to_json()
    schedule = _the_only_schedule(template_json)["Properties"]

    assert schedule["FlexibleTimeWindow"] == {
        "Mode": "FLEXIBLE",
        "MaximumWindowInMinutes": 15,
    }


# T4 (C3; Constraint "Two unverifiable-offline wire details"): the universal
# target must use the SDK *service identifier* `bedrockagentcore`, not the
# endpoint prefix `bedrock-agentcore` - deliberately the OTHER spelling from
# T8's IAM action below. Do not "fix" this to match T8.
def test_target_arn_uses_bedrockagentcore_service_identifier_not_endpoint_prefix():
    template_json = _synthesized_template().to_json()
    target = _the_only_schedule(template_json)["Properties"]["Target"]

    arn = _flatten_arn_like_value(target["Arn"])
    assert "bedrockagentcore" in arn
    assert arn.endswith(":scheduler:::aws-sdk:bedrockagentcore:invokeAgentRuntime")
    assert "aws-sdk:bedrock-agentcore:" not in arn


# T5 (C6/C7): the target Input references the SSM agent-ARN parameter (not a
# literal), carries a plain (not base64, not nested-object) "Payload":"{}",
# and a RuntimeSessionId whose literal prefix alone satisfies the >=33-char
# SessionType minimum and ends with the execution-id context attribute.
def test_target_input_references_ssm_parameter_and_carries_plain_payload_and_valid_session_id():
    template_json = _synthesized_template().to_json()
    target = _the_only_schedule(template_json)["Properties"]["Target"]
    raw_input = target["Input"]
    ssm_logical_id = _ssm_agent_arn_parameter_logical_id(template_json)

    assert ssm_logical_id in _refs_in_join(raw_input), (
        "expected the target Input to reference the SSM agent-runtime-arn "
        "template parameter, not a literal ARN"
    )

    joined = _flatten_arn_like_value(raw_input)
    assert '"AgentRuntimeArn":"<token>"' in joined

    session_prefix = "ai-radar-scheduled-curation-run-id-"
    assert len(session_prefix) >= 33, "SessionType requires a minimum length of 33 characters"
    assert f'"RuntimeSessionId":"{session_prefix}<aws.scheduler.execution-id>"' in joined

    assert '"Payload":"{}"' in joined
    assert '"Payload":"e30="' not in joined  # not base64
    assert '"Payload":{}' not in joined  # not a nested object


# T6 (C10; Constraint "batch-appropriate delivery policy"): a bounded 3
# retries / 2h max event age, explicitly not Scheduler's own default of 185
# retry attempts.
def test_retry_policy_is_bounded_not_the_scheduler_default_of_185():
    template_json = _synthesized_template().to_json()
    target = _the_only_schedule(template_json)["Properties"]["Target"]

    retry_policy = target["RetryPolicy"]
    assert retry_policy == {
        "MaximumRetryAttempts": 3,
        "MaximumEventAgeInSeconds": 7200,
    }
    assert retry_policy["MaximumRetryAttempts"] != 185


# T7 (C9/Guarantee 7): the dead-letter queue exists with 14-day retention and
# a TLS-enforcing queue policy, and the schedule's DeadLetterConfig points at
# its ARN.
def test_dead_letter_queue_has_retention_tls_policy_and_is_wired_to_the_schedule():
    template_json = _synthesized_template().to_json()
    target = _the_only_schedule(template_json)["Properties"]["Target"]

    queues = _resources_of_type(template_json, "AWS::SQS::Queue")
    assert len(queues) == 1, f"expected exactly one SQS queue (the DLQ), found {len(queues)}"

    dlq_matches = [
        (logical_id, resource)
        for logical_id, resource in template_json["Resources"].items()
        if resource["Type"] == "AWS::SQS::Queue"
        and resource["Properties"].get("QueueName") == "ai-radar-schedule-dlq"
    ]
    assert len(dlq_matches) == 1
    dlq_logical_id, dlq_resource = dlq_matches[0]

    assert dlq_resource["Properties"]["MessageRetentionPeriod"] == 1209600  # 14 days, in seconds

    assert target["DeadLetterConfig"] == {"Arn": {"Fn::GetAtt": [dlq_logical_id, "Arn"]}}

    queue_policies = _resources_of_type(template_json, "AWS::SQS::QueuePolicy")
    tls_deny_statements = [
        statement
        for policy in queue_policies
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]
        if statement.get("Effect") == "Deny" and "aws:SecureTransport" in str(statement.get("Condition", {}))
    ]
    assert tls_deny_statements, "expected a TLS-enforcing Deny statement on the DLQ's queue policy"


# T8 (C4/C5/R3): the invoke statement grants exactly
# bedrock-agentcore:InvokeAgentRuntime (the IAM signing-name prefix - the
# OTHER spelling from T4's target service identifier) on exactly the agent
# ARN + its runtime-endpoint/DEFAULT suffix.
def test_invoke_statement_grants_exact_iam_action_on_exactly_two_scoped_resources():
    template_json = _synthesized_template().to_json()
    statements = _all_policy_statements(template_json)
    statement = _statement_by_sid(statements, "InvokeCurationAgent")

    assert statement["Effect"] == "Allow"
    actions = _as_list(statement["Action"])
    assert actions == ["bedrock-agentcore:InvokeAgentRuntime"]
    assert not any(action.startswith("bedrockagentcore:") for action in actions)

    ssm_logical_id = _ssm_agent_arn_parameter_logical_id(template_json)
    resources = _as_list(statement["Resource"])
    assert len(resources) == 2

    assert _refs_in_join(resources[0]) == [ssm_logical_id]
    assert ssm_logical_id in _refs_in_join(resources[1])
    assert _flatten_arn_like_value(resources[1]).endswith("/runtime-endpoint/DEFAULT")


# T9 (R10/Guarantee 5): the regression test for CDK's
# default-wildcard-universal-target-policy bug. Scans every IAM::Policy and
# IAM::Role in the whole synthesized stack, not just the InvokeCurationAgent
# statement.
def test_no_statement_anywhere_in_the_stack_grants_a_wildcard_resource():
    template_json = _synthesized_template().to_json()
    statements = _every_iam_statement_in_stack(template_json)
    assert statements, "expected at least the invoke + DLQ statements to exist"

    wildcard_statements = [
        statement
        for statement in statements
        if statement.get("Effect") == "Allow" and "*" in _as_list(statement.get("Resource", []))
    ]
    assert wildcard_statements == [], (
        f"expected zero Resource:'*' statements anywhere in the stack, found: {wildcard_statements}"
    )


# T10 (Guarantee 6): the CDK-created Scheduler target role's trust policy
# admits only scheduler.amazonaws.com, gated by aws:SourceAccount and
# aws:SourceArn (schedule-group) conditions.
def test_scheduler_target_role_trust_policy_scopes_assume_role_with_source_conditions():
    template_json = _synthesized_template().to_json()
    roles = _resources_of_type(template_json, "AWS::IAM::Role")
    assert len(roles) == 1, "expected exactly one Scheduler target role in the stack"

    trust_statements = roles[0]["Properties"]["AssumeRolePolicyDocument"]["Statement"]
    assert len(trust_statements) == 1
    statement = trust_statements[0]

    assert statement["Effect"] == "Allow"
    assert statement["Action"] == "sts:AssumeRole"
    assert statement["Principal"] == {"Service": "scheduler.amazonaws.com"}

    condition = statement["Condition"]["StringEquals"]
    assert "aws:SourceAccount" in condition
    assert "aws:SourceArn" in condition
    source_arn = _flatten_arn_like_value(condition["aws:SourceArn"])
    assert source_arn.endswith(":schedule-group/default")


# T11 (C15): the role's policy has exactly two statements - the invoke
# statement plus the one CDK auto-adds for sqs:SendMessage on the DLQ - and
# no third.
def test_scheduler_target_role_policy_has_exactly_two_statements():
    template_json = _synthesized_template().to_json()
    policies = _resources_of_type(template_json, "AWS::IAM::Policy")
    assert len(policies) == 1, "expected exactly one managed policy on the Scheduler target role"

    statements = policies[0]["Properties"]["PolicyDocument"]["Statement"]
    assert len(statements) == 2, (
        f"expected exactly two statements (InvokeCurationAgent + DLQ sqs:SendMessage), "
        f"found {len(statements)}: {statements}"
    )

    sids = {statement.get("Sid") for statement in statements}
    assert "InvokeCurationAgent" in sids

    send_message_statements = [
        statement for statement in statements
        if "sqs:SendMessage" in _as_list(statement.get("Action", []))
    ]
    assert len(send_message_statements) == 1


# T12 (C8/C18): the agent ARN reaches CDK as a CloudFormation *template
# parameter* (never an AWS::SSM::Parameter resource, which would mean this
# stack wrongly owns/creates it), and the stack creates none of the resource
# types that would signal scope creep into Phase 2/Spec 06 territory.
def test_agent_arn_is_a_template_parameter_and_stack_creates_no_scope_creep_resources():
    template = _synthesized_template()
    template_json = template.to_json()

    ssm_value_parameters = list(_agent_runtime_arn_ssm_parameters(template_json).values())
    assert len(ssm_value_parameters) == 1
    assert ssm_value_parameters[0]["Default"] == "/ai-radar/agent-runtime-arn"

    template.resource_count_is("AWS::SSM::Parameter", 0)
    template.resource_count_is("AWS::DynamoDB::Table", 0)
    template.resource_count_is("AWS::DynamoDB::GlobalTable", 0)
    template.resource_count_is("AWS::Lambda::Function", 0)


# T13 (C13): all eight documented CfnOutputs are present.
def test_stack_emits_all_eight_outputs():
    template = _synthesized_template()
    for output_name in (
        "ScheduleName",
        "ScheduleArn",
        "ScheduleExpression",
        "ScheduleTimezone",
        "ScheduleEnabled",
        "DeadLetterQueueUrl",
        "DeadLetterQueueArn",
        "AgentRuntimeArnParameter",
    ):
        template.has_output(output_name, Match.any_value())


# T14 (C12/R9): cadence, timezone, and the enabled-state each change in
# exactly one CDK context key; the literal string "true" is what flips the
# schedule to ENABLED.
def test_context_overrides_cadence_timezone_and_true_string_enables_the_schedule():
    template_json = _synthesized_template(
        context={
            "schedule_expression": "cron(5 14 * * ? *)",
            "schedule_timezone": "America/New_York",
            "schedule_enabled": "true",
        }
    ).to_json()
    schedule = _the_only_schedule(template_json)["Properties"]

    assert schedule["ScheduleExpression"] == "cron(5 14 * * ? *)"
    assert schedule["ScheduleExpressionTimezone"] == "America/New_York"
    assert schedule["State"] == "ENABLED"


# T14 (C12, continued): per contract.md's pinned stack code, the coercion is
# `str(raw).lower() == "true"` - any other string (including falsy-looking
# ones like "false") must stay disabled. This is the regression test for a
# truthy-string bug (`if raw_enabled: enabled = True`), which would wrongly
# treat "false" as enabled since it is a non-empty string.
def test_context_schedule_enabled_non_true_string_still_leaves_schedule_disabled():
    for raw_value in ("false", "yes"):
        template_json = _synthesized_template(context={"schedule_enabled": raw_value}).to_json()
        schedule = _the_only_schedule(template_json)["Properties"]
        assert schedule["State"] == "DISABLED", (
            f"schedule_enabled={raw_value!r} must NOT enable the schedule "
            "(only the literal string 'true' may, per str(raw).lower() == 'true')"
        )

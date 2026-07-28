"""Tests for the reusable CDK AgentCore execution-role construct/stack
(Spec 04: runtime-packaging).

Spec: specs/runtime-packaging/contract.md "AgentCore Runtime execution-role -
trust policy (pinned)" + "... permissions policy (pinned, least-privilege)" +
"CDK construct - infra/lib/agent_runtime.py" + "CDK stack + app"; Behavior
Guarantees 6, 7; specs/runtime-packaging/tasks.md Task 4.2 (T7-T14).

Synth-only: no `cdk deploy`, no AWS credentials, no network - `aws_cdk.
assertions.Template` inspects the synthesized CloudFormation template
in-process, matching tests/test_infra.py's precedent (Spec 03).

The pinned account (536697225154), source region (us-east-1), Haiku profile
id, table/GSI names, and secret name are LOCKED per contract.md; a change to
any of them is a data-plane decision that must update this file and
infra/lib/agent_runtime.py together (see tasks.md "Region drift" note).

RED phase: infra/lib/agent_runtime.py and infra/stacks/agent_runtime_stack.py
do not exist yet. Every test in this file is expected to fail at collection
with `ModuleNotFoundError: No module named 'stacks.agent_runtime_stack'` (or
similar) until Phase 2 (tasks.md Tasks 2.1-2.5) lands.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Mirrors tests/test_infra.py's convention: infra/stacks/agent_runtime_stack.py
# imports `from lib.agent_runtime import AgentRuntime` as a flat module, i.e.
# infra/ itself (not its parent) is expected on sys.path.
sys.path.insert(0, str(Path(__file__).parent.parent / "infra"))

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from lib.agent_runtime import TAVILY_SECRET_UNSET_SENTINEL
from stacks.agent_runtime_stack import AgentRuntimeStack

# tests/conftest.py already puts src/ on sys.path (for the Spec 01-03 suite),
# and the infra/ insertion above coexists fine in the same test process - so
# the app-side sentinel (src/curation/config.py) is importable here too, for
# the cross-boundary equality check below (F10 regression).
from curation.config import TAVILY_SECRET_UNSET_SENTINEL as _APP_TAVILY_SECRET_UNSET_SENTINEL

ACCOUNT = "536697225154"
REGION = "us-east-1"


def _synthesized_template() -> Template:
    app = cdk.App()
    stack = AgentRuntimeStack(app, "TestAgentRuntimeStack")
    return Template.from_stack(stack)


def _resources_of_type(template_json: dict, resource_type: str) -> list[dict]:
    return [r for r in template_json["Resources"].values() if r["Type"] == resource_type]


def _all_policy_statements(template_json: dict) -> list[dict]:
    """Flatten every Statement across every synthesized AWS::IAM::Policy
    resource's PolicyDocument (defensive: walks all policy resources even
    though this stack is expected to attach every pinned grant to one role)."""
    statements: list[dict] = []
    for policy in _resources_of_type(template_json, "AWS::IAM::Policy"):
        statements.extend(policy["Properties"]["PolicyDocument"]["Statement"])
    return statements


def _statement_by_sid(statements: list[dict], sid: str) -> dict:
    matches = [s for s in statements if s.get("Sid") == sid]
    assert len(matches) == 1, f"expected exactly one statement with Sid={sid!r}, found {len(matches)}"
    return matches[0]


def _as_list(value) -> list:
    return value if isinstance(value, list) else [value]


def _flatten_arn_like_value(value) -> str:
    """Render a CFN intrinsic (Fn::Join over Aws.REGION/Aws.ACCOUNT_ID tokens)
    or a plain literal string into a single string for substring assertions,
    without depending on whether the construct used tokens or literals."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and "Fn::Join" in value:
        delimiter, parts = value["Fn::Join"]
        return delimiter.join(part if isinstance(part, str) else "<token>" for part in parts)
    return str(value)


# T7 (Guarantee 7 - trust scoping): the execution role is assumable only by
# bedrock-agentcore.amazonaws.com, gated by aws:SourceAccount/aws:SourceArn.
def test_execution_role_trust_policy_scopes_assume_role_to_agentcore_with_source_conditions():
    template_json = _synthesized_template().to_json()
    roles = _resources_of_type(template_json, "AWS::IAM::Role")
    assert len(roles) == 1, "expected exactly one execution role in the stack"

    trust_statements = roles[0]["Properties"]["AssumeRolePolicyDocument"]["Statement"]
    assert len(trust_statements) == 1
    statement = trust_statements[0]

    assert statement["Effect"] == "Allow"
    assert statement["Action"] == "sts:AssumeRole"
    assert statement["Principal"] == {"Service": "bedrock-agentcore.amazonaws.com"}

    condition = statement["Condition"]
    assert "aws:SourceAccount" in condition["StringEquals"]
    assert "aws:SourceArn" in condition["ArnLike"]
    arn_pattern = _flatten_arn_like_value(condition["ArnLike"]["aws:SourceArn"])
    assert arn_pattern.startswith("arn:aws:bedrock-agentcore:")
    assert arn_pattern.endswith(":*")


# T8 (Guarantee 6 / Success Criteria - Bedrock scoping): InvokeModel is scoped
# to the Haiku inference-profile + its per-region foundation-model ARNs only;
# no streaming action, no Sonnet/Titan resource anywhere in the role.
def test_bedrock_statement_scoped_to_haiku_profile_and_regional_foundation_models_only():
    template_json = _synthesized_template().to_json()
    statements = _all_policy_statements(template_json)
    statement = _statement_by_sid(statements, "InvokeHaikuCrossRegion")

    assert statement["Effect"] == "Allow"
    assert set(_as_list(statement["Action"])) == {"bedrock:InvokeModel"}
    assert set(_as_list(statement["Resource"])) == {
        f"arn:aws:bedrock:{REGION}:{ACCOUNT}:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
        f"arn:aws:bedrock:{REGION}::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
    }

    all_actions = {action for s in statements for action in _as_list(s.get("Action", []))}
    all_resources = [resource for s in statements for resource in _as_list(s.get("Resource", []))]
    assert "bedrock:InvokeModelWithResponseStream" not in all_actions
    assert not any("sonnet" in resource.lower() for resource in all_resources)
    assert not any("titan" in resource.lower() for resource in all_resources)


# T9 (Guarantee 6 / Success Criteria - DynamoDB scoping): exactly
# BatchGetItem+UpdateItem on the table + feed-by-score GSI ARNs; no
# Scan/DeleteItem/PutItem/Query anywhere in the role.
def test_dynamodb_statement_grants_exactly_batch_get_and_update_item_on_table_and_gsi():
    template_json = _synthesized_template().to_json()
    statements = _all_policy_statements(template_json)
    statement = _statement_by_sid(statements, "CardStoreReadWrite")

    assert statement["Effect"] == "Allow"
    assert set(_as_list(statement["Action"])) == {"dynamodb:BatchGetItem", "dynamodb:UpdateItem"}
    assert set(_as_list(statement["Resource"])) == {
        f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/ai-radar-cards",
        f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/ai-radar-cards/index/feed-by-score",
    }

    forbidden = {"dynamodb:Scan", "dynamodb:DeleteItem", "dynamodb:PutItem", "dynamodb:Query"}
    all_actions = {action for s in statements for action in _as_list(s.get("Action", []))}
    assert not forbidden & all_actions


# T10 (Guarantee 6 / Success Criteria - Secrets scoping): GetSecretValue on
# the single Tavily secret ARN only; no DescribeSecret anywhere in the role.
def test_secrets_statement_grants_get_secret_value_on_the_one_tavily_secret_only():
    template_json = _synthesized_template().to_json()
    statements = _all_policy_statements(template_json)
    statement = _statement_by_sid(statements, "TavilyKeyRead")

    assert statement["Effect"] == "Allow"
    assert _as_list(statement["Action"]) == ["secretsmanager:GetSecretValue"]
    assert _as_list(statement["Resource"]) == [
        f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:ai-radar/tavily-api-key-*"
    ]

    all_actions = {action for s in statements for action in _as_list(s.get("Action", []))}
    assert "secretsmanager:DescribeSecret" not in all_actions


# T11 (Guarantee 6 / Success Criteria - the sole documented wildcard):
# ecr:GetAuthorizationToken is the ONLY statement in the whole role policy
# using Resource:"*" - logs/ECR-pull otherwise stay scoped.
def test_ecr_get_authorization_token_is_the_only_wildcard_resource_in_the_role_policy():
    template_json = _synthesized_template().to_json()
    statements = _all_policy_statements(template_json)

    wildcard_statements = [s for s in statements if "*" in _as_list(s.get("Resource", []))]

    assert len(wildcard_statements) == 1, (
        f"expected exactly one Resource:'*' statement (ecr:GetAuthorizationToken), "
        f"found {len(wildcard_statements)}: {wildcard_statements}"
    )
    assert _as_list(wildcard_statements[0]["Action"]) == ["ecr:GetAuthorizationToken"]


# T12 (Constraint "Secret never in code/image"; F2 regression, 2026-07): the
# placeholder secret holds NEITHER the real Tavily key NOR AWS's own
# `generate_secret_string` random password (which is truthy and would get
# wrongly treated as a real, usable key by `_resolve_tavily_key` between
# `cdk deploy` and the human's `put-secret-value`) - it is pinned to the
# fixed, recognizable "not yet populated" sentinel, and is destroyed on stack
# teardown.
def test_tavily_placeholder_secret_is_pinned_to_the_unset_sentinel_not_a_generated_password():
    template_json = _synthesized_template().to_json()
    secrets = _resources_of_type(template_json, "AWS::SecretsManager::Secret")
    assert len(secrets) == 1, "expected exactly one Tavily placeholder secret"
    secret = secrets[0]

    # No AWS-generated random password (F2: that value is truthy-but-useless
    # and would masquerade as a real key until a human populates it).
    assert "GenerateSecretString" not in secret["Properties"]
    # Pinned to the sentinel `runtime_app._resolve_tavily_key` recognizes as
    # "not yet populated" - genuinely inert, and still not the real key.
    assert secret["Properties"]["SecretString"] == TAVILY_SECRET_UNSET_SENTINEL
    assert secret.get("DeletionPolicy") == "Delete"


# F10 regression (2026-07): the unset-sentinel value is duplicated as a
# literal in two places - `infra/lib/agent_runtime.py` (CDK, what actually
# gets deployed into the secret) and `src/curation/config.py` (runtime,
# what `_resolve_tavily_key` compares against) - with only a code comment
# enforcing "must match exactly." The auditor proved this is a real gap via
# mutation testing: drifting the two literals apart left every other
# sentinel test green, while the deployed placeholder would silently be
# treated as a valid Tavily key again (reintroducing F2 invisibly). This
# test makes that drift fail loudly instead.
def test_infra_and_app_sentinel_literals_match():
    assert TAVILY_SECRET_UNSET_SENTINEL == _APP_TAVILY_SECRET_UNSET_SENTINEL


# T13 (State Changes: "the ai-radar-cards table is REFERENCED, not created"):
# this stack must not synthesize its own DynamoDB table resource.
def test_stack_does_not_create_a_dynamodb_table_only_references_it():
    template = _synthesized_template()
    template.resource_count_is("AWS::DynamoDB::Table", 0)
    template.resource_count_is("AWS::DynamoDB::GlobalTable", 0)


# T14 (CDK stack + app pinned skeleton): outputs the role ARN + secret
# ARN/name for the operator's `agentcore configure --execution-role` step.
def test_stack_outputs_execution_role_arn_and_tavily_secret_arn_and_name():
    template = _synthesized_template()
    template.has_output("ExecutionRoleArn", Match.any_value())
    template.has_output("TavilySecretArn", Match.any_value())
    template.has_output("TavilySecretName", Match.any_value())

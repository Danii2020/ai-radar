"""Tests for the chat agent's CDK execution role and stack (AC7).

Spec: specs/chat-agent-runtime/intent.md AC7; execution-plan.md § Validation
row AC7 and the "Decision (IAM)" statement list; tasks.md Task 0.4.

Synth-only, modeled on tests/test_infra_agent_runtime.py: no deploy, no AWS
credentials, no network. The plan pins the stack id (`AiRadarChatRuntime`), the
file names and the output name; the stack class name `ChatRuntimeStack` follows
the repo's `AgentRuntimeStack` convention.

RED phase: `infra/lib/chat_runtime.py` and
`infra/stacks/chat_runtime_stack.py` do not exist yet.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "infra"))

import aws_cdk as cdk
from aws_cdk.assertions import Template
from stacks.agent_runtime_stack import AgentRuntimeStack
from stacks.chat_runtime_stack import ChatRuntimeStack

ACCOUNT = "626259825216"
REGION = "us-east-1"
SONNET_PROFILE = "us.anthropic.claude-sonnet-4-6"
SONNET_FM = "anthropic.claude-sonnet-4-6"

EXPECTED_SIDS = {
    "InvokeSonnetCrossRegion",
    "InvokeTitanEmbed",
    "CardIndexQuery",
    "AgentCoreLogsWrite",
    "AgentCoreLogsDescribe",
    "EcrImagePull",
    "EcrAuthToken",
}


def _template_json(stack_cls=ChatRuntimeStack) -> dict:
    app = cdk.App()
    return dict(Template.from_stack(stack_cls(app, "TestStack")).to_json())


def _resources_of_type(template_json: dict, resource_type: str) -> list[dict]:
    return [r for r in template_json["Resources"].values() if r["Type"] == resource_type]


def _statements(template_json: dict) -> list[dict]:
    out: list[dict] = []
    for policy in _resources_of_type(template_json, "AWS::IAM::Policy"):
        out.extend(policy["Properties"]["PolicyDocument"]["Statement"])
    return out


def _as_list(value) -> list:
    return value if isinstance(value, list) else [value]


def _by_sid(statements: list[dict], sid: str) -> dict:
    matches = [s for s in statements if s.get("Sid") == sid]
    assert len(matches) == 1, f"expected exactly one statement Sid={sid!r}, got {len(matches)}"
    return matches[0]


def _flatten(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and "Fn::Join" in value:
        delimiter, parts = value["Fn::Join"]
        return delimiter.join(p if isinstance(p, str) else "<token>" for p in parts)
    return str(value)


def test_trust_policy_is_agentcore_only_with_both_source_conditions():
    roles = _resources_of_type(_template_json(), "AWS::IAM::Role")
    assert len(roles) == 1

    trust = roles[0]["Properties"]["AssumeRolePolicyDocument"]["Statement"]
    assert len(trust) == 1
    statement = trust[0]
    assert statement["Effect"] == "Allow"
    assert statement["Action"] == "sts:AssumeRole"
    assert statement["Principal"] == {"Service": "bedrock-agentcore.amazonaws.com"}
    assert "aws:SourceAccount" in statement["Condition"]["StringEquals"]
    pattern = _flatten(statement["Condition"]["ArnLike"]["aws:SourceArn"])
    assert pattern.startswith("arn:aws:bedrock-agentcore:") and pattern.endswith(":*")


def test_the_role_has_exactly_the_pinned_statements():
    sids = [s.get("Sid") for s in _statements(_template_json())]
    assert sorted(sids) == sorted(EXPECTED_SIDS)


def test_sonnet_statement_covers_the_profile_and_its_three_foundation_models():
    statement = _by_sid(_statements(_template_json()), "InvokeSonnetCrossRegion")

    assert statement["Effect"] == "Allow"
    assert set(_as_list(statement["Action"])) == {"bedrock:InvokeModel"}
    assert set(_as_list(statement["Resource"])) == {
        f"arn:aws:bedrock:{REGION}:{ACCOUNT}:inference-profile/{SONNET_PROFILE}",
        f"arn:aws:bedrock:us-east-1::foundation-model/{SONNET_FM}",
        f"arn:aws:bedrock:us-east-2::foundation-model/{SONNET_FM}",
        f"arn:aws:bedrock:us-west-2::foundation-model/{SONNET_FM}",
    }


def test_titan_statement_is_the_one_foundation_model_arn():
    statement = _by_sid(_statements(_template_json()), "InvokeTitanEmbed")

    assert statement["Effect"] == "Allow"
    assert set(_as_list(statement["Action"])) == {"bedrock:InvokeModel"}
    assert set(_as_list(statement["Resource"])) == {
        f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0"
    }


def test_dynamodb_is_query_on_the_feed_index_arn_only():
    statement = _by_sid(_statements(_template_json()), "CardIndexQuery")

    assert statement["Effect"] == "Allow"
    assert set(_as_list(statement["Action"])) == {"dynamodb:Query"}
    assert set(_as_list(statement["Resource"])) == {
        f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/ai-radar-cards/index/feed-by-score"
    }


def test_nothing_broader_is_granted_anywhere_in_the_role():
    statements = _statements(_template_json())
    actions = {a for s in statements for a in _as_list(s.get("Action", []))}
    resources = [r for s in statements for r in _as_list(s.get("Resource", []))]

    assert "dynamodb:Scan" not in actions
    assert not {a for a in actions if a.startswith("dynamodb:")} - {"dynamodb:Query"}
    write_prefixes = ("Put", "Update", "Delete", "Batch", "Create")
    assert not [
        a for a in actions if a.startswith("dynamodb:") and a.split(":")[1].startswith(write_prefixes)
    ]
    assert not [a for a in actions if a.startswith("secretsmanager:")]
    assert "bedrock:InvokeModelWithResponseStream" not in actions
    assert not any("haiku" in r.lower() for r in resources)
    assert not any(r.endswith("table/ai-radar-cards") for r in resources)


def test_ecr_auth_token_is_the_only_wildcard_resource():
    wildcard = [s for s in _statements(_template_json()) if "*" in _as_list(s.get("Resource", []))]

    assert len(wildcard) == 1
    assert _as_list(wildcard[0]["Action"]) == ["ecr:GetAuthorizationToken"]


def test_the_stack_references_the_table_and_creates_no_secret():
    template_json = _template_json()

    assert not _resources_of_type(template_json, "AWS::DynamoDB::Table")
    assert not _resources_of_type(template_json, "AWS::SecretsManager::Secret")


def test_the_curation_role_is_not_widened_for_chat():
    statements = _statements(_template_json(AgentRuntimeStack))

    assert {s["Sid"] for s in statements} == {
        "InvokeHaikuCrossRegion",
        "InvokeTitanEmbed",
        "CardStoreReadWrite",
        "TavilyKeyRead",
        "AgentCoreLogsWrite",
        "AgentCoreLogsDescribe",
        "EcrImagePull",
        "EcrAuthToken",
    }
    resources = [r for s in statements for r in _as_list(s.get("Resource", []))]
    assert not any("sonnet" in r.lower() for r in resources)


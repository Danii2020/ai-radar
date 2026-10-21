"""CDK synth tests for the chat-API construct/stack (chat-api spec, AC4-AC6).

Spec: specs/chat-api/execution-plan.md § Validation rows AC4, AC5, AC6.

Synth-only: no `cdk deploy`, no AWS credentials, no network, no Docker daemon.
The pinned account (626259825216), region (us-east-1) and runtime id
(ai_radar_chat-JFCO0R9lkT) are literals in `infra/lib/chat_api.py`; a change to
any of them must update this file too.

RED phase: `infra/lib/chat_api.py` and `infra/stacks/chat_api_stack.py` do not
exist, so the file fails at collection with `ModuleNotFoundError`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "infra"))

import aws_cdk as cdk
from aws_cdk.assertions import Template
from stacks.chat_api_stack import ChatApiStack

ACCOUNT = "626259825216"
REGION = "us-east-1"
RUNTIME_ARN = f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:runtime/ai_radar_chat-JFCO0R9lkT"
ENDPOINT_ARN = f"{RUNTIME_ARN}/runtime-endpoint/DEFAULT"


def _template_json(context: dict | None = None) -> dict:
    app = cdk.App(context=context or {})
    stack = ChatApiStack(app, "TestChatApiStack")
    return dict(Template.from_stack(stack).to_json())


def _of_type(template_json: dict, resource_type: str) -> dict[str, dict]:
    return {k: r for k, r in template_json["Resources"].items() if r["Type"] == resource_type}


def _statements(template_json: dict) -> list[dict]:
    out: list[dict] = []
    for policy in _of_type(template_json, "AWS::IAM::Policy").values():
        out.extend(policy["Properties"]["PolicyDocument"]["Statement"])
    return out


def _as_list(value) -> list:
    return value if isinstance(value, list) else [value]


def _cors(context: dict | None = None) -> dict:
    apis = list(_of_type(_template_json(context), "AWS::ApiGatewayV2::Api").values())
    assert len(apis) == 1
    return apis[0]["Properties"]["CorsConfiguration"]


def _function(context: dict | None = None) -> dict:
    functions = list(_of_type(_template_json(context), "AWS::Lambda::Function").values())
    assert len(functions) == 1
    return functions[0]["Properties"]


# AC4
def test_route_is_exactly_post_v1_chat_with_no_default_route():
    routes = list(_of_type(_template_json(), "AWS::ApiGatewayV2::Route").values())
    assert [r["Properties"]["RouteKey"] for r in routes] == ["POST /v1/chat"]
    assert routes[0]["Properties"]["AuthorizationType"] == "NONE"


def test_cors_defaults_to_localhost_origin_post_and_content_type_only():
    cors = _cors()
    assert cors["AllowOrigins"] == ["http://localhost:3000"]
    assert "*" not in cors["AllowOrigins"]
    assert cors["AllowMethods"] == ["POST"]
    assert cors["AllowHeaders"] == ["content-type"]


def test_cors_origins_are_overridable_via_cdk_context_and_never_wildcard():
    cors = _cors({"chat_api_allowed_origins": "https://a.example.com,https://b.example.com"})
    assert cors["AllowOrigins"] == ["https://a.example.com", "https://b.example.com"]
    assert "*" not in cors["AllowOrigins"]


# AC5
def test_default_stage_throttle_is_5_rps_burst_10():
    stages = list(_of_type(_template_json(), "AWS::ApiGatewayV2::Stage").values())
    assert len(stages) == 1
    assert stages[0]["Properties"]["StageName"] == "$default"
    settings = stages[0]["Properties"]["DefaultRouteSettings"]
    assert settings["ThrottlingRateLimit"] == 5
    assert settings["ThrottlingBurstLimit"] == 10


def test_stage_has_no_access_logging_so_no_caller_ip_is_recorded():
    stages = list(_of_type(_template_json(), "AWS::ApiGatewayV2::Stage").values())
    assert "AccessLogSettings" not in stages[0]["Properties"]


def test_reserved_concurrency_is_set_by_default():
    reserved = _function()["ReservedConcurrentExecutions"]
    assert isinstance(reserved, int) and reserved >= 1


def test_reserved_concurrency_none_override_omits_the_property_entirely():
    assert "ReservedConcurrentExecutions" not in _function({"chat_api_reserved_concurrency": "none"})


def test_lambda_timeout_is_28_seconds_under_the_api_gateway_limit():
    assert _function()["Timeout"] == 28


def test_function_receives_the_chat_runtime_arn_the_handler_reads():
    variables = _function()["Environment"]["Variables"]
    assert variables["CHAT_RUNTIME_ARN"] == RUNTIME_ARN


# AC6
def test_iam_has_exactly_one_invoke_statement_and_one_log_write_statement():
    template_json = _template_json()
    statements = _statements(template_json)
    assert len(statements) == 2

    invoke = [s for s in statements if "bedrock-agentcore:InvokeAgentRuntime" in _as_list(s["Action"])]
    assert len(invoke) == 1
    assert invoke[0]["Effect"] == "Allow"
    assert set(_as_list(invoke[0]["Action"])) == {"bedrock-agentcore:InvokeAgentRuntime"}
    assert set(_as_list(invoke[0]["Resource"])) == {RUNTIME_ARN, ENDPOINT_ARN}

    logs = [s for s in statements if s is not invoke[0]]
    assert len(logs) == 1
    assert logs[0]["Effect"] == "Allow"
    assert set(_as_list(logs[0]["Action"])) == {"logs:CreateLogStream", "logs:PutLogEvents"}
    log_groups = _of_type(template_json, "AWS::Logs::LogGroup")
    assert len(log_groups) == 1
    logical_id, group = next(iter(log_groups.items()))
    resource_text = json.dumps(logs[0]["Resource"])
    assert logical_id in resource_text or group["Properties"]["LogGroupName"] in resource_text


def test_role_has_no_wildcard_resource_no_model_data_or_secret_access_no_managed_policy():
    template_json = _template_json()
    statements = _statements(template_json)
    for statement in statements:
        assert "*" not in _as_list(statement["Resource"]), statement

    actions = {a for s in statements for a in _as_list(s["Action"])}
    for prefix in ("bedrock:", "dynamodb:", "secretsmanager:"):
        assert not any(a.startswith(prefix) for a in actions), prefix

    roles = _of_type(template_json, "AWS::IAM::Role")
    assert roles
    for role in roles.values():
        assert not role["Properties"].get("ManagedPolicyArns")

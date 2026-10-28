"""CDK synth tests for the chat-API construct/stack (chat-api spec, AC4-AC6;
chat-api-auth spec, AC2-AC6).

Spec: specs/chat-api/execution-plan.md § Validation rows AC4, AC5, AC6, and
specs/chat-api-auth/execution-plan.md § Validation rows AC2-AC6 (IAM-authorized
route, no CORS, one least-privilege caller user, no access key).

Synth-only: no `cdk deploy`, no AWS credentials, no network, no Docker daemon.
The pinned account (626259825216), region (us-east-1) and runtime id
(ai_radar_chat-JFCO0R9lkT) are literals in `infra/lib/chat_api.py`; a change to
any of them must update this file too.

chat-api-auth RED phase: the route is still `NONE`, CORS and the allowed-origins
knob still exist, and there is no caller user, so the new assertions fail.
"""
from __future__ import annotations

import functools
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
CALLER_USER_NAME = "ai-radar-chat-api-caller"
# Logical id of the HttpApi captured from the pre-auth template (6d19f14); it must not
# change, or CloudFormation would replace the API and its URL would change (AC6).
HTTP_API_LOGICAL_ID = "ChatApiChatHttpApi975E960D"


@functools.cache
def _synth(context_items: tuple) -> dict:
    app = cdk.App(context=dict(context_items))
    stack = ChatApiStack(app, "TestChatApiStack")
    return dict(Template.from_stack(stack).to_json())


def _template_json(context: dict | None = None) -> dict:
    # Synthesizing fingerprints the whole repo (the Docker image asset's
    # directory), ~11 s each. The template is read-only here, so share one per context.
    return _synth(tuple(sorted((context or {}).items())))


def _of_type(template_json: dict, resource_type: str) -> dict[str, dict]:
    return {k: r for k, r in template_json["Resources"].items() if r["Type"] == resource_type}


def _refs(value) -> list[str]:
    """Logical ids named by `{"Ref": ...}` entries in a Roles/Users list."""
    return [v["Ref"] for v in _as_list(value) if isinstance(v, dict) and "Ref" in v]


def _statements(template_json: dict) -> list[dict]:
    """Statements of the policies attached to the Lambda role only."""
    role_ids = {
        k
        for k, r in _of_type(template_json, "AWS::IAM::Role").items()
        if "lambda.amazonaws.com" in json.dumps(r["Properties"]["AssumeRolePolicyDocument"])
    }
    out: list[dict] = []
    for policy in _of_type(template_json, "AWS::IAM::Policy").values():
        if set(_refs(policy["Properties"].get("Roles", []))) & role_ids:
            out.extend(policy["Properties"]["PolicyDocument"]["Statement"])
    return out


def _caller_statements(template_json: dict) -> list[dict]:
    """Every statement attached to the caller user, via policies' `Users` or its `Policies`."""
    users = _of_type(template_json, "AWS::IAM::User")
    out: list[dict] = []
    for policy in _of_type(template_json, "AWS::IAM::Policy").values():
        if set(_refs(policy["Properties"].get("Users", []))) & set(users):
            out.extend(policy["Properties"]["PolicyDocument"]["Statement"])
    for user in users.values():
        for inline in user["Properties"].get("Policies", []):
            out.extend(inline["PolicyDocument"]["Statement"])
    return out


def _as_list(value) -> list:
    return value if isinstance(value, list) else [value]


def _function(context: dict | None = None) -> dict:
    functions = list(_of_type(_template_json(context), "AWS::Lambda::Function").values())
    assert len(functions) == 1
    return functions[0]["Properties"]


# AC2 / AC3
def test_route_is_exactly_post_v1_chat_with_no_default_route():
    routes = list(_of_type(_template_json(), "AWS::ApiGatewayV2::Route").values())
    assert [r["Properties"]["RouteKey"] for r in routes] == ["POST /v1/chat"]
    assert routes[0]["Properties"]["AuthorizationType"] == "AWS_IAM"


# AC3
def test_api_has_no_cors_configuration():
    apis = list(_of_type(_template_json(), "AWS::ApiGatewayV2::Api").values())
    assert len(apis) == 1
    assert "CorsConfiguration" not in apis[0]["Properties"]


def test_allowed_origins_context_key_is_ignored():
    assert _template_json({"chat_api_allowed_origins": "https://a.example.com"}) == _template_json()


# AC4
def test_exactly_one_caller_user_with_no_login_profile_or_managed_policy():
    users = list(_of_type(_template_json(), "AWS::IAM::User").values())
    assert len(users) == 1
    props = users[0]["Properties"]
    assert props["UserName"] == CALLER_USER_NAME
    for forbidden in ("LoginProfile", "ManagedPolicyArns", "Groups"):
        assert forbidden not in props, forbidden


def test_caller_has_exactly_one_statement_invoke_on_post_v1_chat_route_arn():
    template_json = _template_json()
    statements = _caller_statements(template_json)
    assert len(statements) == 1
    statement = statements[0]
    assert statement["Effect"] == "Allow"
    assert _as_list(statement["Action"]) == ["execute-api:Invoke"]
    resources = _as_list(statement["Resource"])
    assert len(resources) == 1
    api_ids = list(_of_type(template_json, "AWS::ApiGatewayV2::Api"))
    assert len(api_ids) == 1
    rendered = json.dumps(resources[0])
    assert api_ids[0] in rendered  # references this API
    assert rendered.rstrip('"}]').endswith("/*/POST/v1/chat")
    # pinned account and region, no bare wildcard anywhere before the stage segment
    assert "execute-api" in rendered
    assert "*" not in rendered.replace("/*/POST/v1/chat", "")
    assert statement["Resource"] != "*"


def test_template_has_no_access_key_and_no_managed_policy():
    template_json = _template_json()
    assert _of_type(template_json, "AWS::IAM::AccessKey") == {}
    assert _of_type(template_json, "AWS::IAM::ManagedPolicy") == {}


# AC6
def test_http_api_logical_id_is_stable():
    assert list(_of_type(_template_json(), "AWS::ApiGatewayV2::Api")) == [HTTP_API_LOGICAL_ID]


# AC5
def test_default_stage_is_throttled():
    stages = list(_of_type(_template_json(), "AWS::ApiGatewayV2::Stage").values())
    assert len(stages) == 1
    assert stages[0]["Properties"]["StageName"] == "$default"
    settings = stages[0]["Properties"]["DefaultRouteSettings"]
    assert 0 < settings["ThrottlingRateLimit"] <= settings["ThrottlingBurstLimit"]


def test_stage_has_no_access_logging_so_no_caller_ip_is_recorded():
    stages = list(_of_type(_template_json(), "AWS::ApiGatewayV2::Stage").values())
    assert "AccessLogSettings" not in stages[0]["Properties"]


def test_reserved_concurrency_is_set_by_default():
    reserved = _function()["ReservedConcurrentExecutions"]
    assert isinstance(reserved, int) and reserved >= 1


def test_reserved_concurrency_none_override_omits_the_property_entirely():
    assert "ReservedConcurrentExecutions" not in _function({"chat_api_reserved_concurrency": "none"})


def test_lambda_timeout_is_under_the_api_gateway_limit():
    assert _function()["Timeout"] <= 29


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

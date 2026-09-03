"""Tests for the reusable CDK feed-API construct/stack (feed-api spec 01).

Spec: specs/feed-api/contract.md "AD-6", "AD-7", "`infra/lib/feed_api.py` —
CREATE (CDK construct)", "`infra/stacks/feed_api_stack.py` — CREATE"; Behavior
Guarantees 10, 11, 12; specs/feed-api/audit.md T15-T18, T25-T27.

Synth-only: no `cdk deploy`, no AWS credentials, no network, **no Docker
daemon** (contract.md: image assets are recorded in the cloud assembly and
built by the CDK CLI at deploy time, not during `Template.from_stack`) —
`aws_cdk.assertions.Template` inspects the synthesized CloudFormation
template in-process, matching `tests/test_infra_agent_runtime.py`'s
precedent.

The pinned account (536697225154) and region (us-east-1) match the
already-deployed `ai-radar-cards` table (AD-6) — a change to either is a
deploy-time decision that must update this file and `infra/lib/feed_api.py`
together.

RED phase: `infra/lib/feed_api.py` and `infra/stacks/feed_api_stack.py` do not
exist yet. Every test in this file is expected to fail at collection with
`ModuleNotFoundError: No module named 'stacks.feed_api_stack'` (or similar)
until Phase 4 (tasks.md) lands.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Mirrors tests/test_infra_agent_runtime.py's convention: infra/stacks/
# feed_api_stack.py imports `from lib.feed_api import FeedApi` as a flat
# module, i.e. infra/ itself (not its parent) is expected on sys.path.
sys.path.insert(0, str(Path(__file__).parent.parent / "infra"))

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from lib.feed_api import DEFAULT_ALLOWED_ORIGINS, FeedApi
from stacks.feed_api_stack import FeedApiStack

ACCOUNT = "536697225154"
REGION = "us-east-1"
CARD_TABLE_NAME = "ai-radar-cards"
FEED_GSI_NAME = "feed-by-score"
INDEX_ARN = f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/{CARD_TABLE_NAME}/index/{FEED_GSI_NAME}"
BASE_TABLE_ARN = f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/{CARD_TABLE_NAME}"


def _synthesized_template(context: dict | None = None) -> Template:
    app = cdk.App(context=context or {})
    stack = FeedApiStack(app, "TestFeedApiStack")
    return Template.from_stack(stack)


def _resources_of_type(template_json: dict, resource_type: str) -> list[dict]:
    return [r for r in template_json["Resources"].values() if r["Type"] == resource_type]


def _all_policy_statements(template_json: dict) -> list[dict]:
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


# T15 (Guarantee 10 / AD-6): FeedGsiQuery grants dynamodb:Query on the index
# ARN only — no base-table ARN by default, no other action.
def test_feed_gsi_query_statement_is_query_only_scoped_to_the_index_arn():
    template_json = _synthesized_template().to_json()
    statements = _all_policy_statements(template_json)
    statement = _statement_by_sid(statements, "FeedGsiQuery")

    assert statement["Effect"] == "Allow"
    assert set(_as_list(statement["Action"])) == {"dynamodb:Query"}
    assert set(_as_list(statement["Resource"])) == {INDEX_ARN}


# AD-6 fallback: grant_base_table_query=True adds the base-table ARN to the
# SAME statement, still Query-only.
def test_grant_base_table_query_flag_adds_base_table_arn_still_query_only():
    app = cdk.App()
    stack = cdk.Stack(app, "TestFallbackStack")
    FeedApi(stack, "FeedApi", grant_base_table_query=True)
    template_json = Template.from_stack(stack).to_json()

    statement = _statement_by_sid(_all_policy_statements(template_json), "FeedGsiQuery")
    assert set(_as_list(statement["Action"])) == {"dynamodb:Query"}
    assert set(_as_list(statement["Resource"])) == {INDEX_ARN, BASE_TABLE_ARN}


# T15: the logs-write statement is scoped to this function's own log group,
# not "*".
def test_feed_api_logs_write_statement_is_scoped_not_wildcard():
    template_json = _synthesized_template().to_json()
    statement = _statement_by_sid(_all_policy_statements(template_json), "FeedApiLogsWrite")

    assert statement["Effect"] == "Allow"
    assert set(_as_list(statement["Action"])) == {"logs:CreateLogStream", "logs:PutLogEvents"}
    assert "*" not in _as_list(statement["Resource"])


# T16 (Guarantee 10 / Success Criteria): no Resource:"*" anywhere, no write
# action, no Bedrock/Secrets action, no AWS managed policy on the role.
def test_role_has_no_wildcard_resource_no_write_action_no_managed_policy():
    template_json = _synthesized_template().to_json()
    statements = _all_policy_statements(template_json)

    for statement in statements:
        assert "*" not in _as_list(statement.get("Resource", [])), (
            f"unexpected Resource:'*' in statement {statement}"
        )

    forbidden_actions = {
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:BatchWriteItem",
        "dynamodb:Scan",
        "dynamodb:BatchGetItem",
    }
    all_actions = {action for s in statements for action in _as_list(s.get("Action", []))}
    assert not forbidden_actions & all_actions
    assert not any(action.startswith("bedrock:") for action in all_actions)
    assert not any(action.startswith("secretsmanager:") for action in all_actions)

    for role in _resources_of_type(template_json, "AWS::IAM::Role"):
        assert not role["Properties"].get("ManagedPolicyArns"), (
            "AWSLambdaBasicExecutionRole (or any managed policy) must not be attached"
        )


# T17 (Guarantee 11 / State Changes): the stack creates zero DynamoDB tables —
# the RETAINed Phase 1 table is referenced by name only.
def test_stack_creates_no_dynamodb_table():
    template = _synthesized_template()
    template.resource_count_is("AWS::DynamoDB::Table", 0)
    template.resource_count_is("AWS::DynamoDB::GlobalTable", 0)


# T18 (Guarantee 12): default CORS origins, no "*", GET-only, and a context
# override changes the origin list.
def test_cors_default_origins_no_wildcard_get_only():
    template_json = _synthesized_template().to_json()
    apis = _resources_of_type(template_json, "AWS::ApiGatewayV2::Api")
    assert len(apis) == 1
    cors = apis[0]["Properties"]["CorsConfiguration"]

    assert cors["AllowOrigins"] == DEFAULT_ALLOWED_ORIGINS
    assert "*" not in cors["AllowOrigins"]
    assert cors["AllowMethods"] == ["GET"]


def test_cors_origins_are_overridable_via_cdk_context():
    template_json = _synthesized_template(
        context={"feed_api_allowed_origins": "https://a.example.com,https://b.example.com"}
    ).to_json()
    apis = _resources_of_type(template_json, "AWS::ApiGatewayV2::Api")
    cors = apis[0]["Properties"]["CorsConfiguration"]

    assert cors["AllowOrigins"] == ["https://a.example.com", "https://b.example.com"]
    assert "*" not in cors["AllowOrigins"]


# T25 (AD-7): stage throttling settings and function reserved concurrency /
# arm64 / timeout.
def test_default_stage_has_throttling_settings():
    template_json = _synthesized_template().to_json()
    stages = _resources_of_type(template_json, "AWS::ApiGatewayV2::Stage")
    assert len(stages) == 1
    stage = stages[0]

    assert stage["Properties"]["StageName"] == "$default"
    route_settings = stage["Properties"]["DefaultRouteSettings"]
    assert route_settings["ThrottlingRateLimit"] == 20
    assert route_settings["ThrottlingBurstLimit"] == 40


def test_function_has_reserved_concurrency_arm64_and_timeout():
    template_json = _synthesized_template().to_json()
    functions = _resources_of_type(template_json, "AWS::Lambda::Function")
    assert len(functions) == 1
    function = functions[0]

    assert function["Properties"]["ReservedConcurrentExecutions"] == 5
    assert function["Properties"]["Architectures"] == ["arm64"]
    assert function["Properties"]["Timeout"] == 10
    assert function["Properties"]["PackageType"] == "Image"


# Deploy-time environmental override (2026-09-02, this account's Lambda
# concurrent-executions quota was 10 at first deploy; AD-7's audited default
# of 5 is unchanged — this only proves the opt-in escape hatch, mirroring
# AD-6's grant_base_table_query context test above). A real behavior
# assertion, not a tautology: the property must be ABSENT from the
# synthesized resource, not merely unequal to 5 or set to some falsy value —
# CDK/CloudFormation have no "unreserved" sentinel other than omitting the
# key entirely.
def test_reserved_concurrency_context_override_omits_the_property_entirely():
    template_json = _synthesized_template(
        context={"feed_api_reserved_concurrency": "none"}
    ).to_json()
    functions = _resources_of_type(template_json, "AWS::Lambda::Function")
    assert len(functions) == 1

    assert "ReservedConcurrentExecutions" not in functions[0]["Properties"]


# T26: exactly one route, GET /v1/cards, AuthorizationType NONE, payload
# format 2.0; no $default route (any other path/method is a 404).
def test_exactly_one_route_get_v1_cards_no_authorizer():
    template_json = _synthesized_template().to_json()
    routes = _resources_of_type(template_json, "AWS::ApiGatewayV2::Route")
    assert len(routes) == 1
    route = routes[0]

    assert route["Properties"]["RouteKey"] == "GET /v1/cards"
    assert route["Properties"]["AuthorizationType"] == "NONE"


def test_integration_payload_format_version_is_2_0():
    template_json = _synthesized_template().to_json()
    integrations = _resources_of_type(template_json, "AWS::ApiGatewayV2::Integration")
    assert len(integrations) == 1
    assert integrations[0]["Properties"]["PayloadFormatVersion"] == "2.0"


# T27: log group name/retention + the four CfnOutputs.
def test_log_group_name_and_one_month_retention():
    template_json = _synthesized_template().to_json()
    log_groups = _resources_of_type(template_json, "AWS::Logs::LogGroup")
    assert len(log_groups) == 1
    log_group = log_groups[0]

    assert log_group["Properties"]["LogGroupName"] == "/aws/lambda/ai-radar-feed-api"
    assert log_group["Properties"]["RetentionInDays"] == 30


def test_stack_outputs_url_function_name_log_group_name_and_allowed_origins():
    template = _synthesized_template()
    template.has_output("FeedApiUrl", Match.any_value())
    template.has_output("FeedApiFunctionName", Match.any_value())
    template.has_output("FeedApiLogGroupName", Match.any_value())
    template.has_output("FeedApiAllowedOrigins", Match.any_value())

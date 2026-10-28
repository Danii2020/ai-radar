"""Scoped CloudFormation execution policies: handler coverage, resource coverage and shape
(spec backend-cicd-pipeline, outcomes O6, O15, O16; AC13; audit findings F2, F3).

Spec: specs/backend-cicd-pipeline/execution-plan.md § Validation rows AC13 (handler coverage
`-k coverage`, resource coverage `-k resource_coverage`, shape `-k shape`).

Revision 3 changes this file deliberately: the plan no longer says "exactly one managed policy".
The CI access stack defines one or two customer-managed policies and every check below runs on
the UNION of their statements. The old per-type action table (`REQUIRED_ACTIONS`, written by the
test writer from memory) is replaced by the committed handler snapshot and omission list:

- `tests/fixtures/cfn/handler_permissions.json`: the create/read/update/delete handler
  permissions of the 19 resource types in the seven stacks, extracted once (2026-10-28) from the
  public CloudFormation registry schema zip. Refreshing it is a reviewed PR; the tests read it
  offline.
- `tests/fixtures/cfn/handler_omissions.json`: permissions deliberately not allowed, each with a
  reason (fnmatch patterns). A snapshot permission must be allowed by some policy or omitted.

The account is never pinned: `norm()` maps any 12-digit id to `ACCT` and the region to `REGION`.

Red today: the single deployed-in-spec policy lacks handler actions the audit found (F2), so the
coverage tests name them; the Tavily-secret and item-action rules and the second-policy deny are
new. The resource-coverage and shape tests that already hold stay green.
"""
from __future__ import annotations

import fnmatch
import json
from typing import Any

import pytest
from ci_synth_helpers import (  # type: ignore[import-not-found]
    REPO,
    STACK_NAMES,
    as_list,
    ci_access_template,
    norm,
    resources_of,
    synth_backend_templates,
)

FIXTURES = REPO / "tests" / "fixtures" / "cfn"
SNAPSHOT = json.loads((FIXTURES / "handler_permissions.json").read_text())["types"]
OMISSIONS = json.loads((FIXTURES / "handler_omissions.json").read_text())["omissions"]
OPS = ("create", "read", "update", "delete")

# Types whose actions can only be granted on "*" (API ids are generated); exempt from the
# resource-name check, as the plan says.
RESOURCE_EXEMPT_TYPES = {
    "AWS::ApiGatewayV2::Api",
    "AWS::ApiGatewayV2::Stage",
    "AWS::ApiGatewayV2::Route",
    "AWS::ApiGatewayV2::Integration",
}

# The action that creates (or, for attachments, writes) each type, and the ARN it acts on.
PRIMARY_ACTION = {
    "AWS::DynamoDB::GlobalTable": "dynamodb:CreateTable",
    "AWS::IAM::Role": "iam:CreateRole",
    "AWS::IAM::User": "iam:CreateUser",
    "AWS::SecretsManager::Secret": "secretsmanager:CreateSecret",
    "AWS::SQS::Queue": "sqs:CreateQueue",
    "AWS::SQS::QueuePolicy": "sqs:SetQueueAttributes",
    "AWS::Scheduler::Schedule": "scheduler:CreateSchedule",
    "AWS::Budgets::Budget": "budgets:ModifyBudget",
    "AWS::SNS::Topic": "sns:CreateTopic",
    "AWS::SNS::TopicPolicy": "sns:SetTopicAttributes",
    "AWS::SNS::Subscription": "sns:Subscribe",
    "AWS::Lambda::Function": "lambda:CreateFunction",
    "AWS::Lambda::Permission": "lambda:AddPermission",
    "AWS::Logs::LogGroup": "logs:CreateLogGroup",
}

AUDIT_NAMED_ACTIONS = [
    "lambda:GetFunctionCodeSigningConfig", "lambda:GetRuntimeManagementConfig",
    "lambda:GetFunctionRecursionConfig", "lambda:PutRuntimeManagementConfig",
    "lambda:PutFunctionRecursionConfig", "lambda:PutFunctionCodeSigningConfig",
    "lambda:DeleteFunctionCodeSigningConfig", "lambda:GetFunctionScalingConfig",
    "lambda:PutFunctionScalingConfig",
    "sns:ListSubscriptionsByTopic", "sns:GetDataProtectionPolicy", "sns:PutDataProtectionPolicy",
    "dynamodb:GetResourcePolicy", "dynamodb:Describe*",
    "logs:DescribeResourcePolicies", "logs:DescribeIndexPolicies",
    "logs:GetDataProtectionPolicy", "logs:ListTagsForResource",
    "budgets:ListTagsForResource", "budgets:TagResource", "budgets:UntagResource",
    "billing:GetBillingViewData", "iam:UpdateRoleDescription",
]
CI_BOOTSTRAP_ROLE_SAMPLES = [
    f"arn:aws:iam::ACCT:role/cdk-hnb659fds-{kind}-role-ACCT-REGION"
    for kind in ("deploy", "file-publishing", "image-publishing", "lookup", "cfn-exec")
]
IAM_WRITE_PROBES = [
    "iam:CreateRole", "iam:DeleteRole", "iam:UpdateAssumeRolePolicy", "iam:PutRolePolicy",
    "iam:DeleteRolePolicy", "iam:AttachRolePolicy", "iam:DetachRolePolicy",
]
ALLOWED_IAM_WRITE_RESOURCES = {
    "arn:aws:iam::ACCT:role/AiRadar*",
    "arn:aws:iam::ACCT:policy/AiRadar*",
    "arn:aws:iam::ACCT:user/ai-radar-chat-api-caller",
}
TAVILY_SECRET = "arn:aws:secretsmanager:REGION:ACCT:secret:ai-radar/tavily-api-key-*"
TABLE_ARN = "arn:aws:dynamodb:REGION:ACCT:table/ai-radar-cards"
INDEX_ARN = f"{TABLE_ARN}/index/feed-by-score"
ITEM_ACTIONS = ["Query", "Scan", "GetItem", "PutItem", "UpdateItem", "DeleteItem", "BatchWriteItem"]

Statement = tuple[str, list[str], list[str]]  # (effect, actions, normalized resources)


# --- extraction ----------------------------------------------------------------------------


def _policy_resources(template: dict[str, Any]) -> dict[str, dict[str, Any]]:
    policies = resources_of(template, "AWS::IAM::ManagedPolicy")
    assert 1 <= len(policies) <= 2, f"expected one or two managed policies, got {len(policies)}"
    return policies


def _statements(template: dict[str, Any]) -> list[Statement]:
    out: list[Statement] = []
    for policy in _policy_resources(template).values():
        for s in policy["Properties"]["PolicyDocument"]["Statement"]:
            out.append((
                s.get("Effect", "Allow"),
                [str(a) for a in as_list(s["Action"])],
                [norm(r) for r in as_list(s.get("Resource", "*"))],
            ))
    return out


def _allow(statements: list[Statement]) -> list[Statement]:
    return [s for s in statements if s[0] == "Allow"]


def _deny(statements: list[Statement]) -> list[Statement]:
    return [s for s in statements if s[0] == "Deny"]


def _matches(patterns: list[str], action: str) -> bool:
    return any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in patterns)


@pytest.fixture(scope="module")
def ci_template() -> dict[str, Any]:
    return ci_access_template()


@pytest.fixture(scope="module")
def statements(ci_template) -> list[Statement]:
    return _statements(ci_template)


def _policy_names(template: dict[str, Any]) -> list[str]:
    return [p["Properties"].get("ManagedPolicyName") for p in _policy_resources(template).values()]


def _ci_role_names(template: dict[str, Any]) -> list[str]:
    return [
        r["Properties"]["RoleName"]
        for r in resources_of(template, "AWS::IAM::Role").values()
        if "sts:AssumeRoleWithWebIdentity" in norm(r["Properties"]["AssumeRolePolicyDocument"])
    ]


# --- handler coverage (AC13, audit F2) ---------------------------------------------------------


def _uncovered(
    types: set[str], statements: list[Statement], omissions: list[dict[str, str]]
) -> dict[str, list[str]]:
    """resource type -> handler permissions neither allowed nor omitted (or a no-snapshot marker)."""
    allowed = [a for _, actions, _ in _allow(statements) for a in actions]
    omitted = [o["permission"] for o in omissions]
    out: dict[str, list[str]] = {}
    for rtype in sorted(types):
        if rtype not in SNAPSHOT:
            out[rtype] = ["<type not in the handler snapshot>"]
            continue
        perms = {p for op in OPS for p in SNAPSHOT[rtype][op]}
        missing = sorted(p for p in perms if not _matches(allowed, p) and not _matches(omitted, p))
        if missing:
            out[rtype] = missing
    return out


def _backend_types() -> set[str]:
    return {
        r["Type"] for template in synth_backend_templates().values() for r in template["Resources"].values()
    }


def test_coverage_every_handler_permission_of_every_backend_type_is_allowed_or_omitted(statements):
    assert _backend_types(), "the seven stacks synthesized no resources"
    assert _uncovered(_backend_types(), statements, OMISSIONS) == {}


def test_coverage_the_actions_the_audit_found_missing_are_allowed(statements):
    allowed = [a for _, actions, _ in _allow(statements) for a in actions]
    assert [a for a in AUDIT_NAMED_ACTIONS if not _matches(allowed, a)] == []


def test_coverage_service_linked_role_creation_is_never_allowed(statements):
    allowed = [a for _, actions, _ in _allow(statements) for a in actions]
    assert not _matches(allowed, "iam:CreateServiceLinkedRole")


def test_coverage_the_table_delete_conflict_is_recorded_as_an_omission_with_its_reason():
    by_perm = {o["permission"]: o["reason"] for o in OMISSIONS}
    for perm in ("dynamodb:DeleteTable", "dynamodb:DeleteTableReplica"):
        assert perm in by_perm, perm
        assert "replica" in by_perm[perm].lower()


def test_coverage_the_omitted_table_deletes_are_not_also_allowed(statements):
    # Omitted means not allowed: the deny would block them anyway, and the removal-of-entry
    # failure case below is only meaningful if the policy itself does not grant them.
    allowed = [a for _, actions, _ in _allow(statements) for a in actions]
    assert not _matches(allowed, "dynamodb:DeleteTable")
    assert not _matches(allowed, "dynamodb:DeleteTableReplica")


def test_coverage_every_omission_has_a_reason():
    assert all(o["reason"].strip() for o in OMISSIONS)


def test_coverage_the_delete_table_deny_stays_while_the_omission_exists(statements):
    # deny-vs-omission: the omission is only acceptable because the deny is still in force.
    assert _denied(statements, "dynamodb:DeleteTable", f"{TABLE_ARN}")


def test_coverage_flags_a_resource_type_that_is_not_in_the_snapshot(statements):
    flagged = _uncovered({"AWS::S3::Bucket"}, statements, OMISSIONS)
    assert flagged == {"AWS::S3::Bucket": ["<type not in the handler snapshot>"]}


def test_coverage_flags_a_snapshot_permission_that_is_neither_allowed_nor_omitted(statements):
    # Drop every allowed action pattern that would grant lambda:GetFunction (also wildcards).
    without = [
        (e, [a for a in actions if not _matches([a], "lambda:GetFunction")], r)
        for e, actions, r in statements
    ]
    flagged = _uncovered({"AWS::Lambda::Function"}, without, OMISSIONS)
    assert "lambda:GetFunction" in flagged["AWS::Lambda::Function"]


def test_coverage_flags_the_delete_table_permission_when_its_omission_entry_is_removed(statements):
    kept = [o for o in OMISSIONS if o["permission"] != "dynamodb:DeleteTable"]
    flagged = _uncovered({"AWS::DynamoDB::GlobalTable"}, statements, kept)
    assert "dynamodb:DeleteTable" in flagged["AWS::DynamoDB::GlobalTable"]


# --- resource coverage (AC13, audit F3) -----------------------------------------------------------------


def _name(props: dict[str, Any], key: str, stack: str, logical_id: str, suffix: str = "-RANDOM") -> str:
    explicit = props.get(key)
    return norm(explicit) if isinstance(explicit, str) else f"{stack}-{logical_id}{suffix}"


def _target_arn(stack: str, template: dict[str, Any], logical_id: str) -> str | None:
    """The ARN the resource's primary action acts on; None for exempt types."""
    res = template["Resources"][logical_id]
    rtype, props = res["Type"], res["Properties"]

    def referenced(value: Any) -> str:
        value = as_list(value)[0]
        key = value.get("Ref") or value.get("Fn::GetAtt", [None])[0]
        return str(key)

    if rtype == "AWS::DynamoDB::GlobalTable":
        return f"arn:aws:dynamodb:REGION:ACCT:table/{_name(props, 'TableName', stack, logical_id)}"
    if rtype == "AWS::IAM::Role":
        return f"arn:aws:iam::ACCT:role/{_name(props, 'RoleName', stack, logical_id)}"
    if rtype == "AWS::IAM::User":
        return f"arn:aws:iam::ACCT:user/{_name(props, 'UserName', stack, logical_id)}"
    if rtype == "AWS::SecretsManager::Secret":
        return f"arn:aws:secretsmanager:REGION:ACCT:secret:{_name(props, 'Name', stack, logical_id)}-AbCdEf"
    if rtype == "AWS::SQS::Queue":
        return f"arn:aws:sqs:REGION:ACCT:{_name(props, 'QueueName', stack, logical_id)}"
    if rtype == "AWS::SQS::QueuePolicy":
        return _target_arn(stack, template, referenced(props["Queues"]))
    if rtype == "AWS::Scheduler::Schedule":
        group = props.get("GroupName", "default")
        return f"arn:aws:scheduler:REGION:ACCT:schedule/{group}/{_name(props, 'Name', stack, logical_id)}"
    if rtype == "AWS::Budgets::Budget":
        return f"arn:aws:budgets::ACCT:budget/{norm(props['Budget'].get('BudgetName', 'generated'))}"
    if rtype == "AWS::SNS::Topic":
        return f"arn:aws:sns:REGION:ACCT:{_name(props, 'TopicName', stack, logical_id)}"
    if rtype == "AWS::SNS::TopicPolicy":
        return _target_arn(stack, template, referenced(props["Topics"]))
    if rtype == "AWS::SNS::Subscription":
        return _target_arn(stack, template, referenced(props["TopicArn"]))
    if rtype == "AWS::Lambda::Function":
        return f"arn:aws:lambda:REGION:ACCT:function:{_name(props, 'FunctionName', stack, logical_id)}"
    if rtype == "AWS::Lambda::Permission":
        return _target_arn(stack, template, referenced(props["FunctionName"]))
    if rtype == "AWS::Logs::LogGroup":
        return f"arn:aws:logs:REGION:ACCT:log-group:{_name(props, 'LogGroupName', stack, logical_id)}"
    raise AssertionError(f"no ARN rule for {rtype}")


def _resource_problems(stack: str, template: dict[str, Any], statements: list[Statement]) -> list[str]:
    """Resources whose physical name no allow statement for their primary action matches."""
    problems: list[str] = []
    for logical_id, res in template["Resources"].items():
        rtype = res["Type"]
        if rtype in RESOURCE_EXEMPT_TYPES:
            continue
        if rtype in ("AWS::IAM::Policy",):
            # An inline policy writes to the role or user it is attached to.
            props = res["Properties"]
            for kind, action in (("Roles", "iam:PutRolePolicy"), ("Users", "iam:PutUserPolicy")):
                for ref in as_list(props.get(kind)):
                    arn = _target_arn(stack, template, ref["Ref"])
                    assert arn
                    problems += _check_arn(logical_id, arn, action, statements)
            continue
        assert rtype in PRIMARY_ACTION, f"no primary action for {rtype}: extend PRIMARY_ACTION"
        arn = _target_arn(stack, template, logical_id)
        assert arn
        problems += _check_arn(logical_id, arn, PRIMARY_ACTION[rtype], statements)
    return problems


def _check_arn(logical_id: str, arn: str, action: str, statements: list[Statement]) -> list[str]:
    for _, actions, resources in _allow(statements):
        if _matches(actions, action) and any(
            r != "*" and (fnmatch.fnmatchcase(arn, r) or fnmatch.fnmatchcase(arn + ":*", r))
            for r in resources
        ):
            return []
    return [f"{logical_id}: no allow of {action} matches {arn}"]


@pytest.mark.parametrize("stack", STACK_NAMES)
def test_resource_coverage_every_physical_name_matches_a_scoped_allow_statement(stack, statements):
    template = synth_backend_templates()[stack]
    assert _resource_problems(stack, template, statements) == []


def test_resource_coverage_flags_a_lambda_named_outside_the_airadar_patterns(statements):
    fixture = {
        "Resources": {
            "OtherFn": {
                "Type": "AWS::Lambda::Function",
                "Properties": {"FunctionName": "other-fn"},
            }
        }
    }
    problems = _resource_problems("AiRadarFeedApi", fixture, statements)
    assert len(problems) == 1 and "other-fn" in problems[0]


def test_resource_coverage_flags_a_lambda_that_would_get_a_generated_name_outside_the_patterns(statements):
    # Without FunctionName the generated name is `<Stack>-<LogicalId>-…`, which only matches
    # if the policy allows AiRadar* function names; the real stacks name every function.
    fixture = {"Resources": {"Fn": {"Type": "AWS::Lambda::Function", "Properties": {}}}}
    allow_only_named = [
        (e, a, [r for r in res if "AiRadar" not in r]) for e, a, res in statements
    ]
    assert _resource_problems("AiRadarFeedApi", fixture, allow_only_named)


def test_resource_coverage_accepts_an_exempt_api_gateway_resource(statements):
    fixture = {"Resources": {"Api": {"Type": "AWS::ApiGatewayV2::Api", "Properties": {"Name": "any"}}}}
    assert _resource_problems("AiRadarFeedApi", fixture, statements) == []


# --- shape: allows (AC13) --------------------------------------------------------------------------------


def test_shape_one_or_two_policies_with_fixed_names_outside_the_airadar_patterns(ci_template):
    names = _policy_names(ci_template)
    assert 1 <= len(names) <= 2
    assert len(set(names)) == len(names)
    for name in names:
        assert isinstance(name, str) and name
        assert not name.lower().startswith(("airadar", "ai-radar"))


def test_shape_no_allow_statement_grants_a_bare_star_action_across_the_policies(statements):
    for _, actions, _ in _allow(statements):
        assert "*" not in actions


def test_shape_no_allow_statement_grants_a_whole_service_on_all_resources(statements):
    for _, actions, resources in _allow(statements):
        if "*" in resources:
            assert [a for a in actions if a.endswith(":*")] == [], actions


def test_shape_iam_writes_are_limited_to_airadar_roles_policies_and_the_caller_user(statements):
    for _, actions, resources in _allow(statements):
        writes = [a for a in actions if a.lower().startswith("iam:") and not a.lower().startswith(("iam:get", "iam:list"))]
        if writes:
            assert resources, writes
            assert set(resources) <= ALLOWED_IAM_WRITE_RESOURCES, (writes, resources)


def test_shape_allow_resource_patterns_cannot_match_the_policies_or_the_ci_roles(ci_template, statements):
    protected = [f"arn:aws:iam::ACCT:policy/{n}" for n in _policy_names(ci_template)] + [
        f"arn:aws:iam::ACCT:role/{n}" for n in _ci_role_names(ci_template)
    ]
    assert len(protected) >= 4  # at least one policy plus the three CI roles
    for _, actions, resources in _allow(statements):
        if not any(a.lower().startswith("iam:") for a in actions):
            continue
        for resource in resources:
            if resource == "*":
                continue  # read-only IAM actions; writes are covered by the test above
            for target in protected:
                assert not fnmatch.fnmatchcase(target, resource), (resource, target)


def _secret_value_violations(statements: list[Statement]) -> list[list[str]]:
    return [
        resources
        for _, actions, resources in _allow(statements)
        if _matches(actions, "secretsmanager:GetSecretValue") and resources != [TAVILY_SECRET]
    ]


def _item_action_violations(statements: list[Statement]) -> list[list[str]]:
    bad = []
    for _, actions, resources in _allow(statements):
        touches_items = any(_matches(actions, f"dynamodb:{item}") for item in ITEM_ACTIONS)
        if touches_items and (not resources or not set(resources) <= {TABLE_ARN, INDEX_ARN}):
            bad.append(resources)
    return bad


def test_shape_get_secret_value_is_allowed_only_on_the_tavily_secret(statements):
    assert _secret_value_violations(statements) == []


@pytest.mark.parametrize("resource", ["arn:aws:secretsmanager:REGION:ACCT:secret:ai-radar/*", "*"])
def test_shape_get_secret_value_on_a_wider_resource_is_flagged(resource):
    fixture: list[Statement] = [("Allow", ["secretsmanager:GetSecretValue"], [resource])]
    assert _secret_value_violations(fixture) == [[resource]]


def test_shape_get_secret_value_on_the_tavily_secret_is_not_flagged():
    fixture: list[Statement] = [("Allow", ["secretsmanager:GetSecretValue"], [TAVILY_SECRET])]
    assert _secret_value_violations(fixture) == []


def test_shape_dynamodb_item_actions_are_allowed_only_on_the_card_table_and_its_index(statements):
    assert _item_action_violations(statements) == []


@pytest.mark.parametrize("resource", ["arn:aws:dynamodb:REGION:ACCT:table/*", "*"])
def test_shape_dynamodb_item_actions_on_a_wider_resource_are_flagged(resource):
    fixture: list[Statement] = [("Allow", ["dynamodb:PutItem", "dynamodb:Query"], [resource])]
    assert _item_action_violations(fixture) == [[resource]]


def test_shape_dynamodb_item_actions_on_the_table_and_index_are_not_flagged():
    fixture: list[Statement] = [("Allow", ["dynamodb:PutItem", "dynamodb:Query"], [TABLE_ARN, INDEX_ARN])]
    assert _item_action_violations(fixture) == []


# --- shape: denies (AC13) ------------------------------------------------------------------------------------


def _denied(statements: list[Statement], action: str, resource: str) -> bool:
    return any(
        _matches(actions, action) and any(fnmatch.fnmatchcase(resource, r) for r in resources)
        for _, actions, resources in _deny(statements)
    )


@pytest.mark.parametrize("action", IAM_WRITE_PROBES)
def test_shape_deny_blocks_iam_writes_on_every_ci_role(ci_template, statements, action):
    names = _ci_role_names(ci_template)
    assert len(names) == 3
    for name in names:
        assert _denied(statements, action, f"arn:aws:iam::ACCT:role/{name}"), (action, name)


@pytest.mark.parametrize("action", ["iam:DeleteOpenIDConnectProvider", "iam:UpdateOpenIDConnectProviderThumbprint",
                                    "iam:AddClientIDToOpenIDConnectProvider"])
def test_shape_deny_blocks_changes_to_the_github_oidc_provider(statements, action):
    provider = "arn:aws:iam::ACCT:oidc-provider/token.actions.githubusercontent.com"
    assert _denied(statements, action, provider)


@pytest.mark.parametrize("action", IAM_WRITE_PROBES)
@pytest.mark.parametrize("role", CI_BOOTSTRAP_ROLE_SAMPLES)
def test_shape_deny_blocks_iam_writes_on_the_cdk_bootstrap_roles(statements, action, role):
    assert _denied(statements, action, role)


@pytest.mark.parametrize("action", ["iam:DeletePolicy", "iam:CreatePolicyVersion", "iam:DeletePolicyVersion",
                                    "iam:SetDefaultPolicyVersion"])
def test_shape_deny_blocks_changes_to_both_execution_policies(ci_template, statements, action):
    for name in _policy_names(ci_template):
        assert _denied(statements, action, f"arn:aws:iam::ACCT:policy/{name}"), name


def test_shape_deny_blocks_deleting_the_cards_table(statements):
    assert _denied(statements, "dynamodb:DeleteTable", TABLE_ARN)


def test_shape_deny_does_not_block_deleting_other_tables(statements):
    # The deny is narrow: only the production cards table is protected.
    assert not _denied(statements, "dynamodb:DeleteTable", "arn:aws:dynamodb:REGION:ACCT:table/ai-radar-scratch")

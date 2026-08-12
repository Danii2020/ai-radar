"""Tests for the AI Radar monthly cost budget CDK construct/stack
(Spec 06: run-observability).

Spec: specs/run-observability/contract.md §10 ("CDK construct —
infra/lib/cost_budget.py") + §11 ("CDK stack —
infra/stacks/cost_budget_stack.py"); Behavior Guarantees 12-13;
specs/run-observability/audit.md Test Coverage T29-T34.

Synth-only: no `cdk deploy`, no AWS credentials, no network -
`aws_cdk.assertions.Template` inspects the synthesized CloudFormation
template in-process, mirroring tests/test_infra_curation_schedule.py's helper
style and its `sys.path.insert(..., "infra")` convention.

RED phase: infra/lib/cost_budget.py and infra/stacks/cost_budget_stack.py do
not exist yet. Every test in this file is expected to fail at collection with
`ModuleNotFoundError: No module named 'stacks.cost_budget_stack'` (or
similar) until specs/run-observability Phase 5 lands.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "infra"))

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from lib.cost_budget import DEFAULT_NOTIFICATION_EMAIL
from stacks.cost_budget_stack import CostBudgetStack


def _synthesized_template(context: dict | None = None) -> Template:
    app = cdk.App(context=context or {})
    stack = CostBudgetStack(app, "TestCostBudgetStack")
    return Template.from_stack(stack)


def _resources_of_type(template_json: dict, resource_type: str) -> list[dict]:
    return [r for r in template_json["Resources"].values() if r["Type"] == resource_type]


def _logical_ids_of_type(template_json: dict, resource_type: str) -> list[str]:
    return [lid for lid, r in template_json["Resources"].items() if r["Type"] == resource_type]


def _statement_by_sid(statements: list[dict], sid: str) -> dict:
    matches = [s for s in statements if s.get("Sid") == sid]
    assert len(matches) == 1, f"expected exactly one statement with Sid={sid!r}, found {len(matches)}"
    return matches[0]


def _as_list(value) -> list:
    return value if isinstance(value, list) else [value]


def _flatten_arn_like_value(value) -> str:
    """Render a CFN intrinsic (Fn::Join over Ref/Fn::GetAtt tokens) or a plain
    literal string into a single string for substring assertions."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and "Fn::Join" in value:
        delimiter, parts = value["Fn::Join"]
        return delimiter.join(part if isinstance(part, str) else "<token>" for part in parts)
    return str(value)


def _the_only_budget(template_json: dict) -> dict:
    budgets_ = _resources_of_type(template_json, "AWS::Budgets::Budget")
    assert len(budgets_) == 1, f"expected exactly one AWS::Budgets::Budget, found {len(budgets_)}"
    return budgets_[0]


# T29 (C25): exactly one AWS::Budgets::Budget named ai-radar-monthly-cost,
# COST/MONTHLY, $250 limit, IncludeCredit: false (Behavior Guarantee 13 /
# intent.md's "credits can't silently drain" rationale).
def test_budget_resource_shape_name_type_limit_and_include_credit_false():
    template_json = _synthesized_template().to_json()
    budget_data = _the_only_budget(template_json)["Properties"]["Budget"]

    assert budget_data["BudgetName"] == "ai-radar-monthly-cost"
    assert budget_data["BudgetType"] == "COST"
    assert budget_data["TimeUnit"] == "MONTHLY"
    assert budget_data["BudgetLimit"] == {"Amount": 250, "Unit": "USD"}
    assert budget_data["CostTypes"]["IncludeCredit"] is False


# T30 (C26/Guarantee 13): three ACTUAL/GREATER_THAN/ABSOLUTE_VALUE
# notifications at exactly 50/100/250, each with the stack's topic as its
# single SNS subscriber.
def test_three_actual_absolute_notifications_at_50_100_250_subscribed_to_the_topic():
    template_json = _synthesized_template().to_json()
    budget_resource = _the_only_budget(template_json)
    notifications = budget_resource["Properties"]["NotificationsWithSubscribers"]
    assert len(notifications) == 3

    topic_logical_ids = _logical_ids_of_type(template_json, "AWS::SNS::Topic")
    assert len(topic_logical_ids) == 1
    topic_logical_id = topic_logical_ids[0]

    thresholds = sorted(n["Notification"]["Threshold"] for n in notifications)
    assert thresholds == [50, 100, 250]

    for n in notifications:
        notif = n["Notification"]
        assert notif["NotificationType"] == "ACTUAL"
        assert notif["ComparisonOperator"] == "GREATER_THAN"
        assert notif["ThresholdType"] == "ABSOLUTE_VALUE"
        subscribers = n["Subscribers"]
        assert len(subscribers) == 1
        assert subscribers[0]["SubscriptionType"] == "SNS"
        assert subscribers[0]["Address"] == {"Ref": topic_logical_id}


# T31 (C27/C28): the topic policy grants budgets.amazonaws.com sns:Publish,
# scoped by aws:SourceAccount + aws:SourceArn (the budget's own ARN), and the
# budget explicitly DependsOn that policy (the CreateBudget/SNS-validation
# race the contract's construct docstring names).
def test_topic_policy_grants_budgets_publish_scoped_by_source_account_and_arn():
    template_json = _synthesized_template().to_json()
    policies = _resources_of_type(template_json, "AWS::SNS::TopicPolicy")
    assert len(policies) == 1
    statements = policies[0]["Properties"]["PolicyDocument"]["Statement"]
    statement = _statement_by_sid(statements, "AllowBudgetsPublish")

    assert statement["Effect"] == "Allow"
    assert statement["Principal"] == {"Service": "budgets.amazonaws.com"}
    assert _as_list(statement["Action"]) == ["sns:Publish"]

    condition = statement["Condition"]
    assert "aws:SourceAccount" in condition["StringEquals"]
    assert "aws:SourceArn" in condition["ArnLike"]
    source_arn = _flatten_arn_like_value(condition["ArnLike"]["aws:SourceArn"])
    assert "budget/ai-radar-monthly-cost" in source_arn


def test_budget_depends_on_the_topic_policy():
    template_json = _synthesized_template().to_json()
    budget_logical_ids = _logical_ids_of_type(template_json, "AWS::Budgets::Budget")
    assert len(budget_logical_ids) == 1
    budget_resource = template_json["Resources"][budget_logical_ids[0]]

    policy_logical_ids = _logical_ids_of_type(template_json, "AWS::SNS::TopicPolicy")
    assert len(policy_logical_ids) == 1

    depends_on = budget_resource.get("DependsOn", [])
    depends_on = depends_on if isinstance(depends_on, list) else [depends_on]
    assert policy_logical_ids[0] in depends_on, (
        "expected the budget to explicitly DependsOn the SNS topic policy "
        "(AWS Budgets validates SNS publish permission at CreateBudget time)"
    )


# Construct docstring: `sns.Topic(..., enforce_ssl=True)` — CDK auto-adds a
# Deny-if-not-SecureTransport statement to the same topic policy resource.
def test_topic_enforces_ssl_with_a_deny_non_tls_statement():
    template_json = _synthesized_template().to_json()
    policies = _resources_of_type(template_json, "AWS::SNS::TopicPolicy")
    statements = policies[0]["Properties"]["PolicyDocument"]["Statement"]

    deny_statements = [
        s
        for s in statements
        if s.get("Effect") == "Deny" and "aws:SecureTransport" in str(s.get("Condition", {}))
    ]
    assert deny_statements, "expected an SSL-enforcing Deny statement on the alert topic's policy"


# T32 (C29): exactly one email subscription, to the pinned default address.
def test_one_email_subscription_to_the_pinned_default_address():
    template_json = _synthesized_template().to_json()
    subs = _resources_of_type(template_json, "AWS::SNS::Subscription")
    assert len(subs) == 1
    assert subs[0]["Properties"]["Protocol"] == "email"
    assert subs[0]["Properties"]["Endpoint"] == DEFAULT_NOTIFICATION_EMAIL


# T33 (C30): context overrides change exactly the expected template values.
def test_context_overrides_change_budget_name_limit_thresholds_and_email():
    template_json = _synthesized_template(
        context={
            "budget_name": "custom-budget-name",
            "budget_limit_usd": "500",
            "budget_thresholds_usd": "100,250,400",
            "budget_email": "someone@example.com",
        }
    ).to_json()

    budget_data = _the_only_budget(template_json)["Properties"]["Budget"]
    assert budget_data["BudgetName"] == "custom-budget-name"
    assert budget_data["BudgetLimit"] == {"Amount": 500, "Unit": "USD"}

    notifications = _the_only_budget(template_json)["Properties"]["NotificationsWithSubscribers"]
    thresholds = sorted(n["Notification"]["Threshold"] for n in notifications)
    assert thresholds == [100, 250, 400]

    subs = _resources_of_type(template_json, "AWS::SNS::Subscription")
    assert subs[0]["Properties"]["Endpoint"] == "someone@example.com"


# T33 (continued): the five documented CfnOutputs are present.
def test_stack_emits_all_five_outputs():
    template = _synthesized_template()
    for output_name in (
        "BudgetName",
        "BudgetLimitUsd",
        "BudgetThresholdsUsd",
        "AlertTopicArn",
        "AlertEmail",
    ):
        template.has_output(output_name, Match.any_value())


# T34: the budget stack creates no scope-creep resources (Non-Goals: no
# dashboards, no alarms; State Changes: "no new DynamoDB item/table").
def test_stack_creates_no_scope_creep_resources():
    template = _synthesized_template()
    template.resource_count_is("AWS::Budgets::Budget", 1)
    template.resource_count_is("AWS::SNS::Topic", 1)
    template.resource_count_is("AWS::CloudWatch::Alarm", 0)
    template.resource_count_is("AWS::DynamoDB::Table", 0)
    template.resource_count_is("AWS::DynamoDB::GlobalTable", 0)
    template.resource_count_is("AWS::Lambda::Function", 0)

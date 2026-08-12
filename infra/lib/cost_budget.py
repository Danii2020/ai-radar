"""Reusable CDK construct: the AI Radar monthly cost budget + alert topic
(Spec 06: run-observability).

`infra/lib/` — NOT `infra/constructs/` — a local `constructs` package on
`sys.path` would shadow the CDK `constructs` library.
"""
from __future__ import annotations

from aws_cdk import Aws
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from constructs import Construct

# --- The "one place" for the budget knobs (Success Criteria) ----------------
# Override per-deploy with `cdk deploy -c budget_limit_usd=... -c
# budget_thresholds_usd=... -c budget_email=...` (see CostBudgetStack).
DEFAULT_BUDGET_NAME = "ai-radar-monthly-cost"   # MUST NOT collide with the
                                                # pre-existing, hand-made
                                                # "My Monthly Cost Budget"
DEFAULT_LIMIT_USD = 250                          # == the top threshold
DEFAULT_THRESHOLDS_USD = [50, 100, 250]          # design §7, verbatim
DEFAULT_NOTIFICATION_EMAIL = "danielmauricioerazoespinoza@gmail.com"
DEFAULT_TOPIC_NAME = "ai-radar-budget-alerts"


class CostBudget(Construct):
    """Monthly COST budget with ACTUAL-spend notifications at absolute USD
    thresholds, delivered to an SNS topic with one email subscriber.

    Exposes `.budget` (budgets.CfnBudget) and `.topic` (sns.Topic).

    Two load-bearing decisions, both easy to get wrong:

    1. `include_credit=False`. The account runs on $500 of AWS credits; with
       the default cost types, credited charges are netted out and the budget
       reports ~$0 forever, so the alert that exists to protect the credits
       would never fire. Excluding credits tracks gross spend — which is
       exactly "credits can't silently drain" (design §7).
    2. The budget explicitly DEPENDS ON the SNS topic policy. AWS Budgets
       validates SNS publish permission at CreateBudget time; without the
       dependency CloudFormation may create the budget first and the deploy
       fails with an "invalid SNS topic / insufficient permission" error.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        budget_name: str = DEFAULT_BUDGET_NAME,
        limit_usd: int = DEFAULT_LIMIT_USD,
        thresholds_usd: list[int] | None = None,
        notification_email: str = DEFAULT_NOTIFICATION_EMAIL,
        topic_name: str = DEFAULT_TOPIC_NAME,
    ) -> None:
        super().__init__(scope, construct_id)
        thresholds_usd = thresholds_usd if thresholds_usd is not None else list(DEFAULT_THRESHOLDS_USD)

        # 1. Alert topic + the one real subscriber (confirmation is a human
        #    click — CDK cannot complete it; see the runbook).
        self.topic = sns.Topic(
            self, "BudgetAlerts",
            topic_name=topic_name,
            display_name="AI Radar budget alerts",
            enforce_ssl=True,
        )
        self.topic.add_subscription(subscriptions.EmailSubscription(notification_email))

        # 2. Let AWS Budgets publish, scoped by source account + this budget's
        #    ARN (a literal string — budget ARNs are region-less and the name
        #    is known at synth time, so there is no circular CFN reference).
        budget_arn = f"arn:aws:budgets::{Aws.ACCOUNT_ID}:budget/{budget_name}"
        policy_result = self.topic.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowBudgetsPublish",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("budgets.amazonaws.com")],
                actions=["sns:Publish"],
                resources=[self.topic.topic_arn],
                conditions={
                    "StringEquals": {"aws:SourceAccount": Aws.ACCOUNT_ID},
                    "ArnLike": {"aws:SourceArn": budget_arn},
                },
            )
        )

        # 3. The budget itself (L1 — aws-cdk-lib 2.261.0 ships no L2).
        self.budget = budgets.CfnBudget(
            self, "MonthlyCostBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name=budget_name,
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(amount=limit_usd, unit="USD"),
                cost_types=budgets.CfnBudget.CostTypesProperty(
                    include_credit=False,      # see docstring — load-bearing
                    include_refund=False,
                    include_discount=True,
                    include_tax=True,
                    include_subscription=True,
                    include_support=True,
                    include_upfront=True,
                    include_recurring=True,
                    include_other_subscription=True,
                    use_amortized=False,
                    use_blended=False,
                ),
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="ACTUAL",
                        comparison_operator="GREATER_THAN",
                        threshold=threshold,
                        threshold_type="ABSOLUTE_VALUE",   # dollars, not percent
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            address=self.topic.topic_arn,
                            subscription_type="SNS",
                        )
                    ],
                )
                for threshold in thresholds_usd
            ],
        )

        if policy_result.policy_dependable is not None:
            self.budget.node.add_dependency(policy_result.policy_dependable)

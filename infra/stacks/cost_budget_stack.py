"""CDK stack wrapping `CostBudget` (Spec 06: run-observability)."""
from __future__ import annotations

from aws_cdk import CfnOutput, Stack
from constructs import Construct

from lib.cost_budget import (  # infra/ on sys.path via app.py
    DEFAULT_BUDGET_NAME,
    DEFAULT_LIMIT_USD,
    DEFAULT_NOTIFICATION_EMAIL,
    DEFAULT_THRESHOLDS_USD,
    CostBudget,
)


class CostBudgetStack(Stack):
    """Knobs are overridable per-deploy via CDK context:

        cdk deploy -c budget_limit_usd=500 \
                   -c budget_thresholds_usd="100,250,400" \
                   -c budget_email=someone@example.com

    Defaults (the "one place") live in lib/cost_budget.py.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        budget_name = self.node.try_get_context("budget_name") or DEFAULT_BUDGET_NAME
        email = self.node.try_get_context("budget_email") or DEFAULT_NOTIFICATION_EMAIL
        raw_limit = self.node.try_get_context("budget_limit_usd")
        limit_usd = DEFAULT_LIMIT_USD if raw_limit is None else int(raw_limit)
        # `-c budget_thresholds_usd="50,100,250"` arrives as a STRING.
        raw_thresholds = self.node.try_get_context("budget_thresholds_usd")
        thresholds = (
            list(DEFAULT_THRESHOLDS_USD)
            if raw_thresholds is None
            else [int(t.strip()) for t in str(raw_thresholds).split(",") if t.strip()]
        )

        cost_budget = CostBudget(
            self, "CostBudget",
            budget_name=budget_name,
            limit_usd=limit_usd,
            thresholds_usd=thresholds,
            notification_email=email,
        )

        CfnOutput(self, "BudgetName", value=budget_name)
        CfnOutput(self, "BudgetLimitUsd", value=str(limit_usd))
        CfnOutput(self, "BudgetThresholdsUsd", value=",".join(str(t) for t in thresholds))
        CfnOutput(self, "AlertTopicArn", value=cost_budget.topic.topic_arn)
        CfnOutput(self, "AlertEmail", value=email)

"""Tests for the reusable CDK card-store construct/stack (`infra/`).

Spec: specs/dynamodb-card-store/contract.md "CDK construct" section, Behavior
Guarantee 9; specs/dynamodb-card-store/tasks.md T11.

Synth-only: no `cdk deploy`, no AWS credentials, no network - `aws_cdk.assertions.
Template` inspects the synthesized CloudFormation template in-process, matching
this repo's "zero real-AWS calls in pytest" convention (carried from Specs 01-02
via `moto` for the store tests; here via CDK's own offline synthesizer).

Per the latest spec revision, point-in-time recovery (PITR) was explicitly
declined for Phase 1 (tasks.md "Human decisions") - this file intentionally does
NOT assert PITR is enabled.

RED phase: `infra/` does not exist yet. This test is expected to fail at
collection with `ModuleNotFoundError: No module named 'stacks'` until
`infra/stacks/card_store_stack.py` + `infra/lib/card_store.py` land.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Mirrors conftest.py's `sys.path.insert(0, .../src)` pattern: contract.md's
# `infra/stacks/card_store_stack.py` imports `from lib.card_store import
# CardStoreTable` as a flat module, i.e. `infra/` itself (not its parent) is
# expected on sys.path - the same convention `infra/app.py` uses at runtime.
sys.path.insert(0, str(Path(__file__).parent.parent / "infra"))

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from stacks.card_store_stack import CardStoreStack


def _synthesized_template() -> Template:
    app = cdk.App()
    stack = CardStoreStack(app, "TestCardStoreStack")
    return Template.from_stack(stack)


# T11 (Guarantee 9): on-demand (PAY_PER_REQUEST) billing, base PK `card_id`,
# and the `feed-by-score` GSI (gsi_pk/gsi_sk, projection ALL) match the LOCKED
# key schema in contract.md exactly.
def test_card_store_table_synthesizes_with_locked_key_schema_and_on_demand_billing():
    template = _synthesized_template()

    template.has_resource_properties(
        "AWS::DynamoDB::GlobalTable",
        {
            "TableName": "ai-radar-cards",
            "BillingMode": "PAY_PER_REQUEST",
            "KeySchema": [{"AttributeName": "card_id", "KeyType": "HASH"}],
            "GlobalSecondaryIndexes": Match.array_with(
                [
                    Match.object_like(
                        {
                            "IndexName": "feed-by-score",
                            "KeySchema": [
                                {"AttributeName": "gsi_pk", "KeyType": "HASH"},
                                {"AttributeName": "gsi_sk", "KeyType": "RANGE"},
                            ],
                            "Projection": {"ProjectionType": "ALL"},
                        }
                    )
                ]
            ),
        },
    )


# T11 (Guarantee 9 / intent.md "removal_policy = RETAIN" human decision): the
# table must survive `cdk destroy` / stack teardown.
def test_card_store_table_deletion_policy_is_retain():
    template = _synthesized_template()
    template.has_resource("AWS::DynamoDB::GlobalTable", {"DeletionPolicy": "Retain"})

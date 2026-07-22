"""Reusable CDK construct: the AI Radar card table (Spec 03).

`infra/lib/` — NOT `infra/constructs/` — a local `constructs` package on
`sys.path` would shadow the CDK `constructs` library (`from constructs import
Construct`).
"""
from __future__ import annotations

from aws_cdk import RemovalPolicy
from aws_cdk import aws_dynamodb as dynamodb
from constructs import Construct


class CardStoreTable(Construct):
    """Provisions the AI Radar card table (on-demand) + feed-read GSI.

    Exposes `.table` (the dynamodb.TableV2) for grants/outputs by callers.
    Key schema matches specs/dynamodb-card-store/contract.md exactly — a change
    here is a data migration.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        table_name: str = "ai-radar-cards",
    ) -> None:
        super().__init__(scope, construct_id)
        self.table = dynamodb.TableV2(
            self,
            "Table",
            table_name=table_name,
            partition_key=dynamodb.Attribute(
                name="card_id", type=dynamodb.AttributeType.STRING
            ),
            billing=dynamodb.Billing.on_demand(),
            removal_policy=RemovalPolicy.RETAIN,
            global_secondary_indexes=[
                dynamodb.GlobalSecondaryIndexPropsV2(
                    index_name="feed-by-score",
                    partition_key=dynamodb.Attribute(
                        name="gsi_pk", type=dynamodb.AttributeType.STRING
                    ),
                    sort_key=dynamodb.Attribute(
                        name="gsi_sk", type=dynamodb.AttributeType.STRING
                    ),
                    projection_type=dynamodb.ProjectionType.ALL,
                )
            ],
        )

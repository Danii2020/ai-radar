"""CDK stack wrapping `CardStoreTable` (Spec 03)."""
from __future__ import annotations

from aws_cdk import CfnOutput, Stack
from constructs import Construct

from lib.card_store import CardStoreTable  # infra/ on sys.path via app.py


class CardStoreStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        store = CardStoreTable(self, "CardStore", table_name="ai-radar-cards")
        CfnOutput(self, "CardTableName", value=store.table.table_name)
        CfnOutput(self, "FeedGsiName", value="feed-by-score")

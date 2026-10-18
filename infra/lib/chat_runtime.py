"""Reusable CDK construct: the chat AgentCore Runtime execution role (spec
`chat-agent-runtime`). Role only: read path, no secret, no table-level or write
grant. Mirrors `AgentRuntime`'s trust policy and statement style.
"""
from __future__ import annotations

from aws_cdk import Aws
from aws_cdk import aws_iam as iam
from constructs import Construct


class ChatRuntime(Construct):
    """Exposes `.role` (iam.Role). Pinned account/region literals follow
    `agent_runtime.py` (change both plus tests when moving accounts)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        account: str = "626259825216",
        region: str = "us-east-1",
        card_table_name: str = "ai-radar-cards",
        feed_gsi_name: str = "feed-by-score",
        sonnet_inference_profile_id: str = "us.anthropic.claude-sonnet-4-6",
        sonnet_foundation_model_id: str = "anthropic.claude-sonnet-4-6",
        sonnet_regions: list[str] | None = None,
        titan_embed_model_id: str = "amazon.titan-embed-text-v2:0",
    ) -> None:
        super().__init__(scope, construct_id)
        sonnet_regions = sonnet_regions if sonnet_regions is not None else [
            "us-east-1",
            "us-east-2",
            "us-west-2",
        ]

        self.role = iam.Role(
            self,
            "ExecutionRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": Aws.ACCOUNT_ID},
                    "ArnLike": {
                        "aws:SourceArn":
                            f"arn:aws:bedrock-agentcore:{Aws.REGION}:{Aws.ACCOUNT_ID}:*"
                    },
                },
            ),
        )

        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeSonnetCrossRegion",
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{region}:{account}:inference-profile/{sonnet_inference_profile_id}",
                ] + [
                    f"arn:aws:bedrock:{r}::foundation-model/{sonnet_foundation_model_id}"
                    for r in sonnet_regions
                ],
            )
        )

        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeTitanEmbed",
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{region}::foundation-model/{titan_embed_model_id}"
                ],
            )
        )

        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="CardIndexQuery",
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:Query"],
                resources=[
                    f"arn:aws:dynamodb:{region}:{account}:table/{card_table_name}/index/{feed_gsi_name}"
                ],
            )
        )

        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="AgentCoreLogsWrite",
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams",
                ],
                resources=[
                    f"arn:aws:logs:{region}:{account}:log-group:/aws/bedrock-agentcore/runtimes/*",
                    f"arn:aws:logs:{region}:{account}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*",
                ],
            )
        )

        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="AgentCoreLogsDescribe",
                effect=iam.Effect.ALLOW,
                actions=["logs:DescribeLogGroups"],
                resources=[f"arn:aws:logs:{region}:{account}:log-group:*"],
            )
        )

        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="EcrImagePull",
                effect=iam.Effect.ALLOW,
                actions=["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                resources=[
                    f"arn:aws:ecr:{region}:{account}:repository/bedrock-agentcore-*"
                ],
            )
        )

        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="EcrAuthToken",
                effect=iam.Effect.ALLOW,
                actions=["ecr:GetAuthorizationToken"],
                resources=["*"],
            )
        )

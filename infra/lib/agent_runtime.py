"""Reusable CDK construct: the AgentCore Runtime execution role + Tavily
placeholder secret (Spec 04: runtime-packaging).

`infra/lib/` — NOT `infra/constructs/` — a local `constructs` package on
`sys.path` would shadow the CDK `constructs` library (`from constructs import
Construct`).
"""
from __future__ import annotations

from aws_cdk import Aws, RemovalPolicy, SecretValue
from aws_cdk import aws_iam as iam
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

# Placeholder value the Tavily secret is pinned to at deploy time, before a
# human `put-secret-value`s the real key (Task 3.5). MUST match
# src/curation/config.py's `TAVILY_SECRET_UNSET_SENTINEL` exactly -
# `runtime_app._resolve_tavily_key` treats a secret holding this value as
# "not yet populated" and degrades to RSS-only. Not imported from
# src/curation/ here (infra/ is a separate CDK toolchain, different
# sys.path/dependency group) - kept in sync by convention + this comment +
# the paired test in tests/test_infra_agent_runtime.py.
#
# Bug fixed here (F2, 2026-07): leaving the secret's value unset makes CDK
# synthesize `GenerateSecretString: {}`, which AWS fills with a random ~32-char
# password at deploy time - NOT empty. Between `cdk deploy` and the human
# populating the real key, that random password is truthy and would get wired
# into TavilyDiscoverer as if it were a real key (every search silently 401s,
# caught per-seed, but `tavily_enabled` would wrongly report True). Pinning a
# recognizable sentinel via `secret_string_value` instead keeps the secret
# genuinely inert (and still contains no real key) until populated.
TAVILY_SECRET_UNSET_SENTINEL = "UNSET-populate-via-put-secret-value"


class AgentRuntime(Construct):
    """AgentCore Runtime execution role + Tavily API-key secret (Spec 04).

    Exposes `.role` (iam.Role) and `.tavily_secret` (secretsmanager.Secret) for
    the stack to CfnOutput. Least-privilege: see specs/runtime-packaging/
    contract.md for the pinned action/resource list. The card table is REFERENCED
    by name (already deployed by CardStoreStack, RETAINed) — never recreated.

    The permission-policy resource ARNs (Bedrock/DynamoDB/Secrets/Logs/ECR) use
    the LITERAL pinned account (536697225154) + source region (us-east-1) per
    contract.md — the referenced `ai-radar-cards` table lives in a separate
    stack with no cross-stack export, so there is nothing to token-reference.
    Only the trust-policy condition uses `Aws.ACCOUNT_ID`/`Aws.REGION` tokens
    (this stack's own deploy-time account/region), per the contract skeleton.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        account: str = "536697225154",
        region: str = "us-east-1",
        card_table_name: str = "ai-radar-cards",
        feed_gsi_name: str = "feed-by-score",
        tavily_secret_name: str = "ai-radar/tavily-api-key",
        haiku_inference_profile_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        haiku_foundation_model_id: str = "anthropic.claude-haiku-4-5-20251001-v1:0",
        haiku_regions: list[str] | None = None,
    ) -> None:
        super().__init__(scope, construct_id)
        haiku_regions = haiku_regions if haiku_regions is not None else [
            "us-east-1",
            "us-east-2",
            "us-west-2",
        ]

        # 1. Genuinely inert placeholder secret — pinned to a fixed, obviously-
        #    non-functional sentinel (NOT `generate_secret_string`, which AWS
        #    would fill with a random-but-truthy password at deploy time; see
        #    the TAVILY_SECRET_UNSET_SENTINEL comment above). CDK never sets
        #    the real value; a human `put-secret-value`'s it post-deploy.
        #    RemovalPolicy.DESTROY so `cdk destroy` cleans it up (dev secret,
        #    trivially re-populated).
        self.tavily_secret = secretsmanager.Secret(
            self,
            "TavilySecret",
            secret_name=tavily_secret_name,
            description="Tavily API key for AI Radar curation discovery (Spec 04) — "
            "placeholder only; populate via `aws secretsmanager put-secret-value`.",
            secret_string_value=SecretValue.unsafe_plain_text(TAVILY_SECRET_UNSET_SENTINEL),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # 2. Execution role, trust principal bedrock-agentcore.amazonaws.com with
        #    aws:SourceAccount / aws:SourceArn conditions (pinned trust policy).
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

        # 3. Attach the pinned least-privilege statements (bedrock/dynamo/
        #    secrets/logs/ecr) as explicit iam.PolicyStatement objects — NOT
        #    grant_read_write_data()/grant_read() (both too broad).
        bedrock_resources = [
            f"arn:aws:bedrock:{region}:{account}:inference-profile/{haiku_inference_profile_id}",
        ] + [
            f"arn:aws:bedrock:{region}::foundation-model/{haiku_foundation_model_id}"
            for region in haiku_regions
        ]
        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeHaikuCrossRegion",
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=bedrock_resources,
            )
        )

        table_arn = f"arn:aws:dynamodb:{region}:{account}:table/{card_table_name}"
        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="CardStoreReadWrite",
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:BatchGetItem", "dynamodb:UpdateItem"],
                resources=[table_arn, f"{table_arn}/index/{feed_gsi_name}"],
            )
        )

        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="TavilyKeyRead",
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=[
                    f"arn:aws:secretsmanager:{region}:{account}:secret:{tavily_secret_name}-*"
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

"""Reusable CDK construct: the feed read API (Phase 2, spec `feed-api`).

`infra/lib/` — NOT `infra/constructs/` — a local `constructs` package on
`sys.path` would shadow the CDK `constructs` library.
"""
from __future__ import annotations

from pathlib import Path

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integrations
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

# --- The "one place" for the deploy-time knobs -----------------------------
# Override per-deploy with `cdk deploy -c feed_api_allowed_origins=...`
# (see FeedApiStack). NEVER "*" — a synth test asserts that.
DEFAULT_ALLOWED_ORIGINS = ["http://localhost:3000"]   # Spec 02 adds the Vercel origin
DEFAULT_THROTTLE_RATE = 20      # req/s, steady state (AD-7)
DEFAULT_THROTTLE_BURST = 40
DEFAULT_RESERVED_CONCURRENCY = 5
# Deploy-time environmental override (2026-09-02, live-fire, human-approved) —
# NOT a design change, AD-7's audited/intended value is still 5. This
# account's real Lambda "Concurrent executions" quota was 10 (not AWS's
# stated default of 1000) at first deploy attempt: CDK's synthesized
# `reserved_concurrent_executions=5` was rejected because it would drop the
# account's UNRESERVED concurrency below AWS's required floor of 10. A quota
# increase to 1001 was requested (AWS Support case 178836416700301, pending,
# no ETA at time of writing). `FeedApiStack` reads CDK context key
# `feed_api_reserved_concurrency` (mirrors AD-6's `grant_base_table_query`
# one-line-flip pattern) so `cdk deploy AiRadarFeedApi -c
# feed_api_reserved_concurrency=none` can omit the reservation for exactly
# this deploy, with zero code change needed to restore 5 on the next normal
# deploy. Remove or ignore this override once the quota increase is
# confirmed.
DEFAULT_MEMORY_MB = 512
DEFAULT_TIMEOUT = Duration.seconds(10)
DEFAULT_LOG_RETENTION = logs.RetentionDays.ONE_MONTH

# Same literals as src/api/config.py and src/curation/config.py — infra is a
# separate toolchain (different sys.path/dependency group), so they are
# duplicated by convention, exactly like agent_runtime.py's Tavily sentinel.
CARD_TABLE_NAME = "ai-radar-cards"
FEED_GSI_NAME = "feed-by-score"
ROUTE_PATH = "/v1/cards"

# Repo root: infra/lib/feed_api.py -> infra/lib -> infra -> repo root. Used as
# the DockerImageFunction asset directory so it resolves identically under
# `cdk` and under `pytest`.
_REPO_ROOT = Path(__file__).parents[2]


class FeedApi(Construct):
    """HTTP API -> Lambda -> Query(feed-by-score). Exposes `.http_api`,
    `.function`, `.log_group`, `.role` for the stack to CfnOutput.

    The `ai-radar-cards` table is REFERENCED by name (deployed and RETAINed by
    AiRadarCardStore, no cross-stack export) — never created or imported as a
    CFN resource. The permission-policy ARNs use the LITERAL pinned account +
    region for exactly that reason, matching `agent_runtime.py`.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        account: str = "536697225154",
        region: str = "us-east-1",
        card_table_name: str = CARD_TABLE_NAME,
        feed_gsi_name: str = FEED_GSI_NAME,
        allowed_origins: list[str] | None = None,
        grant_base_table_query: bool = False,   # AD-6 fallback: one-line flip
        reserved_concurrent_executions: int | None = DEFAULT_RESERVED_CONCURRENCY,
        # ^ Deploy-time environmental override fallback (see the comment by
        # DEFAULT_RESERVED_CONCURRENCY above). Default stays 5 — the audited
        # AD-7 baseline is unchanged. Pass None to omit the reservation
        # entirely (a Lambda-API requirement: you cannot pass
        # reserved_concurrent_executions=None to CDK and get "unreserved" —
        # the kwarg must be left out of the call altogether).
    ) -> None:
        super().__init__(scope, construct_id)

        self.allowed_origins = (
            allowed_origins if allowed_origins is not None else list(DEFAULT_ALLOWED_ORIGINS)
        )

        # 1. Explicit log group — created up front so the role's `logs` grant
        #    can be scoped to it, and so retention is not infinite.
        self.log_group = logs.LogGroup(
            self,
            "FeedApiLogGroup",
            log_group_name="/aws/lambda/ai-radar-feed-api",
            retention=DEFAULT_LOG_RETENTION,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # 2. Least-privilege role. No managed policies (AWSLambdaBasicExecutionRole
        #    is deliberately not attached — it allows logs:* on "*").
        self.role = iam.Role(
            self,
            "FeedApiRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        index_arn = f"arn:aws:dynamodb:{region}:{account}:table/{card_table_name}/index/{feed_gsi_name}"
        query_resources = [index_arn]
        if grant_base_table_query:
            base_table_arn = f"arn:aws:dynamodb:{region}:{account}:table/{card_table_name}"
            query_resources.append(base_table_arn)

        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="FeedGsiQuery",
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:Query"],
                resources=query_resources,
            )
        )
        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="FeedApiLogsWrite",
                effect=iam.Effect.ALLOW,
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[f"{self.log_group.log_group_arn}:*"],
            )
        )

        # 3. Docker-image Lambda (AD-1/AD-2): pydantic + app code only, no
        #    langgraph/bedrock-agentcore/tavily-python/feedparser/rich.
        function_kwargs = dict(
            function_name="ai-radar-feed-api",
            code=lambda_.DockerImageCode.from_image_asset(
                str(_REPO_ROOT),
                file="Dockerfile.feed_api",
                platform=ecr_assets.Platform.LINUX_ARM64,
            ),
            architecture=lambda_.Architecture.ARM_64,
            role=self.role,
            log_group=self.log_group,
            memory_size=DEFAULT_MEMORY_MB,
            timeout=DEFAULT_TIMEOUT,
            environment={"CARD_TABLE_NAME": card_table_name},
        )
        # Omitting the kwarg entirely (not passing None) is what actually
        # leaves the function's concurrency unreserved — see the deploy-time
        # override comment above.
        if reserved_concurrent_executions is not None:
            function_kwargs["reserved_concurrent_executions"] = reserved_concurrent_executions

        self.function = lambda_.DockerImageFunction(self, "FeedApiFunction", **function_kwargs)

        # 4. HTTP API + scoped CORS + the one route. No $default route: any
        #    other path/method is a 404 from API Gateway.
        self.http_api = apigwv2.HttpApi(
            self,
            "FeedHttpApi",
            api_name="ai-radar-feed-api",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=self.allowed_origins,
                allow_methods=[apigwv2.CorsHttpMethod.GET],
                allow_headers=["content-type"],
                max_age=Duration.hours(1),
            ),
        )
        self.http_api.add_routes(
            path=ROUTE_PATH,
            methods=[apigwv2.HttpMethod.GET],
            integration=apigwv2_integrations.HttpLambdaIntegration(
                "FeedIntegration", self.function
            ),
        )

        # 5. Stage throttling (AD-7) via the typed CfnStage escape hatch.
        cfn_stage = self.http_api.default_stage.node.default_child
        cfn_stage.default_route_settings = apigwv2.CfnStage.RouteSettingsProperty(
            throttling_rate_limit=DEFAULT_THROTTLE_RATE,
            throttling_burst_limit=DEFAULT_THROTTLE_BURST,
        )

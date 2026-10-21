"""Reusable CDK construct: the chat API (spec `chat-api`).

HTTP API -> Lambda -> `bedrock-agentcore:InvokeAgentRuntime` on the deployed
`ai_radar_chat` runtime. Mirrors `feed_api.py`. `infra/lib/`, not
`infra/constructs/`, so the CDK `constructs` library is not shadowed.
"""
from __future__ import annotations

from pathlib import Path
from typing import cast

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integrations
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

# Override per-deploy with `cdk deploy -c chat_api_allowed_origins=...`
# (see ChatApiStack). NEVER "*" — a synth test asserts that.
DEFAULT_ALLOWED_ORIGINS = ["http://localhost:3000"]
# Lower than feed-api's 20/40: every call spends Sonnet tokens.
THROTTLE_RATE_LIMIT = 5      # req/s, steady state
THROTTLE_BURST_LIMIT = 10
# The audited default. This account's Lambda concurrency quota is 10, so deploy
# with `-c chat_api_reserved_concurrency=none` (same as AiRadarFeedApi).
DEFAULT_RESERVED_CONCURRENCY = 5
DEFAULT_MEMORY_MB = 256
# Under API Gateway's ~30 s integration limit; the handler's invoke read
# timeout (22 s) is shorter still.
# Literal 28 on purpose: infra must not import src. The tests pin it against the handler's
# connect (3 s) + read (22 s) timeouts.
DEFAULT_TIMEOUT = Duration.seconds(28)
DEFAULT_LOG_RETENTION = logs.RetentionDays.ONE_MONTH

# Pinned literals, same convention as feed_api.py / chat_runtime.py (change
# these plus tests/test_infra_chat_api.py when moving accounts).
CHAT_RUNTIME_ID = "ai_radar_chat-JFCO0R9lkT"
ROUTE_PATH = "/v1/chat"

_REPO_ROOT = Path(__file__).parents[2]


class ChatApi(Construct):
    """Exposes `.http_api`, `.function`, `.log_group`, `.role`,
    `.allowed_origins` and `.runtime_arn`."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        account: str = "626259825216",
        region: str = "us-east-1",
        runtime_id: str = CHAT_RUNTIME_ID,
        allowed_origins: list[str] | None = None,
        reserved_concurrent_executions: int | None = DEFAULT_RESERVED_CONCURRENCY,
        # ^ None omits the kwarg entirely (the only way to leave concurrency
        # unreserved through CDK); see ChatApiStack.
    ) -> None:
        super().__init__(scope, construct_id)

        self.allowed_origins = (
            allowed_origins if allowed_origins is not None else list(DEFAULT_ALLOWED_ORIGINS)
        )
        self.runtime_arn = f"arn:aws:bedrock-agentcore:{region}:{account}:runtime/{runtime_id}"

        self.log_group = logs.LogGroup(
            self,
            "ChatApiLogGroup",
            log_group_name="/aws/lambda/ai-radar-chat-api",
            retention=DEFAULT_LOG_RETENTION,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Least privilege; no managed policy (AWSLambdaBasicExecutionRole
        # allows logs:* on "*"). No Bedrock model, DynamoDB or secret access.
        self.role = iam.Role(
            self,
            "ChatApiRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeChatRuntime",
                effect=iam.Effect.ALLOW,
                actions=["bedrock-agentcore:InvokeAgentRuntime"],
                resources=[
                    self.runtime_arn,
                    f"{self.runtime_arn}/runtime-endpoint/DEFAULT",
                ],
            )
        )
        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="ChatApiLogsWrite",
                effect=iam.Effect.ALLOW,
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[f"{self.log_group.log_group_arn}:*"],
            )
        )

        function_kwargs: dict = {
            "function_name": "ai-radar-chat-api",
            "code": lambda_.DockerImageCode.from_image_asset(
                str(_REPO_ROOT),
                file="Dockerfile.chat_api",
                platform=ecr_assets.Platform.LINUX_ARM64,
            ),
            "architecture": lambda_.Architecture.ARM_64,
            "role": self.role,
            "log_group": self.log_group,
            "memory_size": DEFAULT_MEMORY_MB,
            "timeout": DEFAULT_TIMEOUT,
            "environment": {"CHAT_RUNTIME_ARN": self.runtime_arn},
        }
        if reserved_concurrent_executions is not None:
            function_kwargs["reserved_concurrent_executions"] = reserved_concurrent_executions

        self.function = lambda_.DockerImageFunction(self, "ChatApiFunction", **function_kwargs)

        # One route, no $default route: anything else is a 404 from API Gateway.
        # No access logging is configured, so no caller IP is recorded.
        self.http_api = apigwv2.HttpApi(
            self,
            "ChatHttpApi",
            api_name="ai-radar-chat-api",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=self.allowed_origins,
                allow_methods=[apigwv2.CorsHttpMethod.POST],
                allow_headers=["content-type"],
                max_age=Duration.hours(1),
            ),
        )
        self.http_api.add_routes(
            path=ROUTE_PATH,
            methods=[apigwv2.HttpMethod.POST],
            integration=apigwv2_integrations.HttpLambdaIntegration(
                "ChatIntegration", self.function
            ),
        )

        default_stage = self.http_api.default_stage
        assert default_stage is not None
        cfn_stage = cast(apigwv2.CfnStage, default_stage.node.default_child)
        cfn_stage.default_route_settings = apigwv2.CfnStage.RouteSettingsProperty(
            throttling_rate_limit=THROTTLE_RATE_LIMIT,
            throttling_burst_limit=THROTTLE_BURST_LIMIT,
        )

"""CDK stack wrapping `FeedApi` (Phase 2, spec `feed-api`)."""
from __future__ import annotations

from aws_cdk import CfnOutput, Stack
from constructs import Construct

from lib.feed_api import FeedApi  # infra/ on sys.path via app.py


class FeedApiStack(Stack):
    """Wraps `FeedApi`. Reads the allowed-origin list from CDK context so
    Spec 02 can redeploy with the real Vercel origin without a code edit:
    `cdk deploy -c feed_api_allowed_origins=https://ai-radar.vercel.app`
    (comma-separated for several).

    Also reads `feed_api_reserved_concurrency` — a deploy-time environmental
    override (2026-09-02, see `infra/lib/feed_api.py`'s
    `DEFAULT_RESERVED_CONCURRENCY` comment): this account's Lambda concurrent-
    executions quota was 10 at first deploy, below what
    `reserved_concurrent_executions=5` (AD-7's audited default) requires.
    `cdk deploy AiRadarFeedApi -c feed_api_reserved_concurrency=none` omits
    the reservation for one deploy; a plain `cdk deploy AiRadarFeedApi` (no
    override) restores the audited default of 5 with zero code change.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        raw_origins = self.node.try_get_context("feed_api_allowed_origins")
        origins = (
            [o.strip() for o in raw_origins.split(",") if o.strip()] if raw_origins else None
        )

        feed_api_kwargs = {}
        raw_concurrency = self.node.try_get_context("feed_api_reserved_concurrency")
        if raw_concurrency is not None:
            if str(raw_concurrency).strip().lower() == "none":
                feed_api_kwargs["reserved_concurrent_executions"] = None
            else:
                feed_api_kwargs["reserved_concurrent_executions"] = int(raw_concurrency)

        api = FeedApi(self, "FeedApi", allowed_origins=origins, **feed_api_kwargs)
        CfnOutput(self, "FeedApiUrl", value=api.http_api.api_endpoint)
        CfnOutput(self, "FeedApiFunctionName", value=api.function.function_name)
        CfnOutput(self, "FeedApiLogGroupName", value=api.log_group.log_group_name)
        CfnOutput(self, "FeedApiAllowedOrigins", value=",".join(api.allowed_origins))

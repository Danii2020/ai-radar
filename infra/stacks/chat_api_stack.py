"""CDK stack wrapping `ChatApi` (spec `chat-api`)."""
from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Stack
from constructs import Construct
from lib.chat_api import ChatApi  # infra/ on sys.path via app.py


class ChatApiStack(Stack):
    """Wraps `ChatApi`. CDK context overrides, as for `FeedApiStack`:

    - `chat_api_allowed_origins`: comma-separated origins (default
      `http://localhost:3000`; never `*`).
    - `chat_api_reserved_concurrency`: an int, or `none` to omit the
      reservation. This account's Lambda concurrency quota is 10, so deploy
      with `-c chat_api_reserved_concurrency=none`.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        raw_origins = self.node.try_get_context("chat_api_allowed_origins")
        origins = (
            [o.strip() for o in raw_origins.split(",") if o.strip()] if raw_origins else None
        )

        api_kwargs: dict[str, Any] = {}
        raw_concurrency = self.node.try_get_context("chat_api_reserved_concurrency")
        if raw_concurrency is not None:
            if str(raw_concurrency).strip().lower() == "none":
                api_kwargs["reserved_concurrent_executions"] = None
            else:
                api_kwargs["reserved_concurrent_executions"] = int(raw_concurrency)

        api = ChatApi(self, "ChatApi", allowed_origins=origins, **api_kwargs)
        CfnOutput(self, "ChatApiUrl", value=api.http_api.api_endpoint)
        CfnOutput(self, "ChatApiFunctionName", value=api.function.function_name)
        CfnOutput(self, "ChatApiLogGroupName", value=api.log_group.log_group_name)
        CfnOutput(self, "ChatApiAllowedOrigins", value=",".join(api.allowed_origins))

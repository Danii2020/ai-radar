"""CDK stack wrapping `ChatRuntime` (spec `chat-agent-runtime`)."""
from __future__ import annotations

from aws_cdk import CfnOutput, Stack
from constructs import Construct
from lib.chat_runtime import ChatRuntime  # infra/ on sys.path via app.py


class ChatRuntimeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        runtime = ChatRuntime(self, "ChatRuntime")
        CfnOutput(self, "ExecutionRoleArn", value=runtime.role.role_arn)

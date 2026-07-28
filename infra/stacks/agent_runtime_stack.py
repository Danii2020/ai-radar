"""CDK stack wrapping `AgentRuntime` (Spec 04: runtime-packaging)."""
from __future__ import annotations

from aws_cdk import CfnOutput, Stack
from constructs import Construct

from lib.agent_runtime import AgentRuntime  # infra/ on sys.path via app.py


class AgentRuntimeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        runtime = AgentRuntime(self, "AgentRuntime")
        CfnOutput(self, "ExecutionRoleArn", value=runtime.role.role_arn)
        CfnOutput(self, "TavilySecretArn", value=runtime.tavily_secret.secret_arn)
        CfnOutput(self, "TavilySecretName", value=runtime.tavily_secret.secret_name)

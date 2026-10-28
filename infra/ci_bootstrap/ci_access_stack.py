"""CI access stack (spec backend-cicd-pipeline; AC2, AC3, AC8, AC9, AC13).

Defines, outside the seven-stack app (`infra/app.py` never imports it):

- the GitHub OIDC provider,
- three OIDC roles: `diff` (pull requests of this repository, may only assume the CDK lookup
  role), `deploy` and `smoke` (both trust only `refs/heads/main`),
- two customer-managed policies (each under IAM's 6,144-character limit) that replace
  `AdministratorAccess` as the CDK bootstrap's CloudFormation execution policies.

A human deploys it once with their own administrator credentials (it uses
`CliCredentialsStackSynthesizer`, so no CDK bootstrap role is involved) and CI never deploys
it. The chat API id comes from the CDK context `chat_api_id`; it is never committed. The
account id and region are CloudFormation pseudo parameters, never literals.
"""
from __future__ import annotations

import re
from typing import Any

import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from constructs import Construct

GITHUB_REPO = "Danii2020/ai-radar"
OIDC_HOST = "token.actions.githubusercontent.com"
AUDIENCE = "sts.amazonaws.com"
SUB_PR = f"repo:{GITHUB_REPO}:pull_request"
SUB_MAIN = f"repo:{GITHUB_REPO}:ref:refs/heads/main"
QUALIFIER = "hnb659fds"  # the default CDK bootstrap qualifier

# Names outside the `AiRadar*` / `ai-radar*` patterns, so the execution policy's allow
# statements can never match them.
DIFF_ROLE = "gha-airadar-diff"
DEPLOY_ROLE = "gha-airadar-deploy"
SMOKE_ROLE = "gha-airadar-smoke"
EXEC_POLICIES = ("cdk-exec-airadar", "cdk-exec-airadar-2")

RUNTIME_IDS = ("ai_radar_curation-FW1w976PCI", "ai_radar_chat-JFCO0R9lkT")
AGENT_REPOS = ("bedrock-agentcore-ai_radar_curation", "bedrock-agentcore-ai_radar_chat")
LAMBDA_BASIC_EXEC = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
_API_ID = re.compile(r"[a-z0-9]{8,12}")


class CiAccessStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: Any) -> None:
        kwargs.setdefault("synthesizer", cdk.CliCredentialsStackSynthesizer())
        super().__init__(scope, construct_id, **kwargs)

        api_id = str(self.node.try_get_context("chat_api_id") or "")
        if not _API_ID.fullmatch(api_id):
            raise ValueError("pass the chat API id as CDK context: -c chat_api_id=<10-character id>")

        self._p = cdk.Aws.PARTITION
        self._a = cdk.Aws.ACCOUNT_ID
        self._r = cdk.Aws.REGION

        provider = iam.OidcProviderNative(
            self, "GithubOidc", url=f"https://{OIDC_HOST}", client_ids=[AUDIENCE]
        )
        self.diff_role = self._role("DiffRole", DIFF_ROLE, SUB_PR, provider)
        self.deploy_role = self._role("DeployRole", DEPLOY_ROLE, SUB_MAIN, provider)
        self.smoke_role = self._role("SmokeRole", SMOKE_ROLE, SUB_MAIN, provider)

        self._diff_permissions()
        self._deploy_permissions()
        self._smoke_permissions(api_id)
        self.exec_policies = self._execution_policies()

        cdk.CfnOutput(self, "DiffRoleArn", value=self.diff_role.role_arn)
        cdk.CfnOutput(self, "DeployRoleArn", value=self.deploy_role.role_arn)
        cdk.CfnOutput(self, "SmokeRoleArn", value=self.smoke_role.role_arn)
        for n, policy in enumerate(self.exec_policies, start=1):
            cdk.CfnOutput(self, f"ExecutionPolicyArn{n}", value=policy.managed_policy_arn)

    # -- helpers ---------------------------------------------------------------------------------

    def _arn(self, service: str, resource: str, *, region: bool = True, account: bool = True) -> str:
        reg = self._r if region else ""
        acct = self._a if account else ""
        return f"arn:{self._p}:{service}:{reg}:{acct}:{resource}"

    def _role(self, logical_id: str, name: str, sub: str, provider: iam.OidcProviderNative) -> iam.Role:
        principal = iam.WebIdentityPrincipal(
            provider.oidc_provider_arn,
            {"StringEquals": {f"{OIDC_HOST}:aud": AUDIENCE, f"{OIDC_HOST}:sub": sub}},
        )
        return iam.Role(
            self,
            logical_id,
            role_name=name,
            assumed_by=principal,
            max_session_duration=cdk.Duration.hours(1),
        )

    def _bootstrap_role(self, kind: str) -> str:
        return self._arn("iam", f"role/cdk-{QUALIFIER}-{kind}-role-{self._a}-{self._r}", region=False)

    # -- role permissions ---------------------------------------------------------------------------

    def _diff_permissions(self) -> None:
        # `cdk diff --method=template` reads templates through the lookup role only.
        self.diff_role.add_to_policy(
            iam.PolicyStatement(actions=["sts:AssumeRole"], resources=[self._bootstrap_role("lookup")])
        )

    def _deploy_permissions(self) -> None:
        role = self.deploy_role
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=[
                    self._bootstrap_role(k)
                    for k in ("deploy", "file-publishing", "image-publishing", "lookup")
                ],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudformation:DescribeStacks"],
                resources=[self._arn("cloudformation", "stack/AiRadar*/*")],
            )
        )
        # `agentcore deploy --local-build`: push the image, update the existing runtime.
        # ecr:GetAuthorizationToken only supports "*". The list is confirmed from the first
        # human-run deploy (CloudTrail), then recorded in the README.
        role.add_to_policy(
            iam.PolicyStatement(actions=["ecr:GetAuthorizationToken"], resources=["*"])
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:BatchGetImage",
                    "ecr:CompleteLayerUpload",
                    "ecr:DescribeImages",
                    "ecr:DescribeRepositories",
                    "ecr:InitiateLayerUpload",
                    "ecr:PutImage",
                    "ecr:UploadLayerPart",
                ],
                resources=[self._arn("ecr", f"repository/{r}") for r in AGENT_REPOS],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:GetAgentRuntime",
                    "bedrock-agentcore:ListAgentRuntimeVersions",
                    "bedrock-agentcore:UpdateAgentRuntime",
                    "bedrock-agentcore:GetAgentRuntimeEndpoint",
                    "bedrock-agentcore:UpdateAgentRuntimeEndpoint",
                ],
                resources=[
                    arn
                    for rid in RUNTIME_IDS
                    for arn in (
                        self._arn("bedrock-agentcore", f"runtime/{rid}"),
                        self._arn("bedrock-agentcore", f"runtime/{rid}/runtime-endpoint/*"),
                    )
                ],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[
                    self._arn("iam", "role/AiRadarRuntimeRole-*", region=False),
                    self._arn("iam", "role/AiRadarChatRuntime-*", region=False),
                ],
                conditions={"StringEquals": {"iam:PassedToService": "bedrock-agentcore.amazonaws.com"}},
            )
        )

    def _smoke_permissions(self, api_id: str) -> None:
        role = self.smoke_role
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["execute-api:Invoke"],
                resources=[self._arn("execute-api", f"{api_id}/*/POST/v1/chat")],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudformation:DescribeStacks"],
                resources=[
                    self._arn("cloudformation", "stack/AiRadarFeedApi/*"),
                    self._arn("cloudformation", "stack/AiRadarChatApi/*"),
                ],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock-agentcore:GetAgentRuntime"],
                resources=[self._arn("bedrock-agentcore", f"runtime/{rid}") for rid in RUNTIME_IDS],
            )
        )

    # -- scoped CloudFormation execution policies (AC13) ----------------------------------------------
    # Two policies because one cannot hold every handler permission under the 6,144-character
    # limit. Policy 1: data and compute services. Policy 2: identity, scheduling, budgets and
    # every explicit deny. The handler snapshot test checks the UNION of both.

    def _execution_policies(self) -> list[iam.ManagedPolicy]:
        groups = (self._exec_statements_data(), self._exec_statements_identity())
        return [
            iam.ManagedPolicy(self, f"CfnExecutionPolicy{n}", managed_policy_name=name, statements=stmts)
            for n, (name, stmts) in enumerate(zip(EXEC_POLICIES, groups, strict=True), start=1)
        ]

    def _exec_statements_data(self) -> list[iam.PolicyStatement]:
        a = self._arn
        allow = iam.Effect.ALLOW
        S = iam.PolicyStatement
        table = a("dynamodb", "table/ai-radar-cards")
        return [
            S(  # Table management. DeleteTable and DeleteTableReplica are deliberately absent.
                effect=allow,
                actions=[
                    "dynamodb:CreateTable", "dynamodb:UpdateTable", "dynamodb:Describe*",
                    "dynamodb:TagResource", "dynamodb:UntagResource", "dynamodb:ListTagsOfResource",
                    "dynamodb:UpdateContinuousBackups", "dynamodb:UpdateTimeToLive",
                    "dynamodb:CreateTableReplica", "dynamodb:DisassociateTableReplica",
                    "dynamodb:UpdateContributorInsights", "dynamodb:UpdateGlobalTable",
                    "dynamodb:UpdateGlobalTableSettings", "dynamodb:UpdateTableReplicaAutoScaling",
                    "dynamodb:GetResourcePolicy", "dynamodb:PutResourcePolicy",
                    "dynamodb:DeleteResourcePolicy",
                ],
                resources=[a("dynamodb", "table/ai-radar-*")],
            ),
            S(  # Item actions: the handler touches items only on the card table and its index.
                effect=allow,
                actions=[
                    "dynamodb:BatchWriteItem", "dynamodb:DeleteItem", "dynamodb:GetItem",
                    "dynamodb:PutItem", "dynamodb:Query", "dynamodb:Scan", "dynamodb:UpdateItem",
                ],
                resources=[table, f"{table}/index/feed-by-score"],
            ),
            S(effect=allow, actions=["cloudwatch:PutMetricData"], resources=["*"]),
            S(
                effect=allow,
                actions=[
                    "secretsmanager:CreateSecret", "secretsmanager:DeleteSecret",
                    "secretsmanager:DescribeSecret", "secretsmanager:UpdateSecret",
                    "secretsmanager:TagResource", "secretsmanager:UntagResource",
                ],
                resources=[a("secretsmanager", "secret:ai-radar/*")],
            ),
            S(  # The only secret value CloudFormation may read (dynamic references).
                effect=allow,
                actions=["secretsmanager:GetSecretValue"],
                resources=[a("secretsmanager", "secret:ai-radar/tavily-api-key-*")],
            ),
            S(effect=allow, actions=["secretsmanager:GetRandomPassword"], resources=["*"]),
            S(
                effect=allow,
                actions=[
                    "sqs:CreateQueue", "sqs:DeleteQueue", "sqs:GetQueueAttributes",
                    "sqs:SetQueueAttributes", "sqs:GetQueueUrl", "sqs:TagQueue",
                    "sqs:UntagQueue", "sqs:ListQueueTags",
                ],
                resources=[a("sqs", "ai-radar-*")],
            ),
            S(
                effect=allow,
                actions=[
                    "sns:CreateTopic", "sns:DeleteTopic", "sns:GetTopicAttributes",
                    "sns:SetTopicAttributes", "sns:TagResource", "sns:UntagResource",
                    "sns:ListTagsForResource", "sns:Subscribe", "sns:Unsubscribe",
                    "sns:GetSubscriptionAttributes", "sns:SetSubscriptionAttributes",
                    "sns:ListSubscriptionsByTopic", "sns:GetDataProtectionPolicy",
                    "sns:PutDataProtectionPolicy",
                ],
                resources=[a("sns", "ai-radar-*")],
            ),
            S(
                effect=allow,
                actions=[
                    "lambda:CreateFunction", "lambda:DeleteFunction", "lambda:GetFunction",
                    "lambda:GetFunctionConfiguration", "lambda:UpdateFunctionCode",
                    "lambda:UpdateFunctionConfiguration", "lambda:TagResource",
                    "lambda:UntagResource", "lambda:ListTags", "lambda:AddPermission",
                    "lambda:RemovePermission", "lambda:GetPolicy", "lambda:PutFunctionConcurrency",
                    "lambda:DeleteFunctionConcurrency", "lambda:PublishVersion",
                    "lambda:GetFunctionCodeSigningConfig", "lambda:PutFunctionCodeSigningConfig",
                    "lambda:DeleteFunctionCodeSigningConfig", "lambda:GetCodeSigningConfig",
                    "lambda:GetRuntimeManagementConfig", "lambda:PutRuntimeManagementConfig",
                    "lambda:GetFunctionRecursionConfig", "lambda:PutFunctionRecursionConfig",
                    "lambda:GetFunctionScalingConfig", "lambda:PutFunctionScalingConfig",
                ],
                resources=[a("lambda", "function:ai-radar-*")],
            ),
            S(  # Lambda container images come from the CDK assets repository.
                effect=allow,
                actions=["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                resources=[a("ecr", f"repository/cdk-{QUALIFIER}-container-assets-{self._a}-{self._r}")],
            ),
            S(
                effect=allow,
                actions=[
                    "logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy",
                    "logs:DeleteRetentionPolicy", "logs:TagResource", "logs:UntagResource",
                    "logs:ListTagsForResource", "logs:GetDataProtectionPolicy",
                    "logs:PutDataProtectionPolicy", "logs:DeleteDataProtectionPolicy",
                    "logs:PutIndexPolicy", "logs:DeleteIndexPolicy",
                    "logs:PutLogGroupDeletionProtection", "logs:PutBearerTokenAuthentication",
                ],
                resources=[a("logs", "log-group:/aws/lambda/ai-radar-*")],
            ),
            S(  # These logs actions cannot be restricted by resource.
                effect=allow,
                actions=[
                    "logs:DescribeLogGroups", "logs:DescribeResourcePolicies",
                    "logs:DescribeIndexPolicies", "logs:PutResourcePolicy",
                    "logs:DeleteResourcePolicy",
                ],
                resources=["*"],
            ),
            S(  # HTTP API ids are generated, so API Gateway cannot be name-scoped.
                effect=allow,
                actions=["apigateway:POST", "apigateway:GET", "apigateway:PUT",
                         "apigateway:PATCH", "apigateway:DELETE",
                         "apigateway:TagResource", "apigateway:UntagResource"],
                resources=[
                    a("apigateway", "/apis", account=False),
                    a("apigateway", "/apis/*", account=False),
                    a("apigateway", "/tags/*", account=False),
                ],
            ),
            S(  # CloudFormation resolves the SSM parameter type and the bootstrap version.
                effect=allow,
                actions=["ssm:GetParameter", "ssm:GetParameters"],
                resources=[
                    a("ssm", f"parameter/cdk-bootstrap/{QUALIFIER}/version"),
                    a("ssm", "parameter/ai-radar/*"),
                ],
            ),
        ]

    def _exec_statements_identity(self) -> list[iam.PolicyStatement]:
        a = self._arn
        allow = iam.Effect.ALLOW
        S = iam.PolicyStatement
        ci_roles = [a("iam", f"role/{n}", region=False) for n in (DIFF_ROLE, DEPLOY_ROLE, SMOKE_ROLE)]
        return [
            S(  # IAM roles the stacks create (execution roles, Lambda roles, scheduler role).
                effect=allow,
                actions=[
                    "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:UpdateRole",
                    "iam:UpdateRoleDescription",
                    "iam:UpdateAssumeRolePolicy", "iam:TagRole", "iam:UntagRole", "iam:PassRole",
                    "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy",
                    "iam:ListRolePolicies", "iam:ListAttachedRolePolicies",
                ],
                resources=[a("iam", "role/AiRadar*", region=False)],
            ),
            S(  # Managed policies on those roles: only the Lambda basic-execution policy.
                effect=allow,
                actions=["iam:AttachRolePolicy", "iam:DetachRolePolicy"],
                resources=[a("iam", "role/AiRadar*", region=False)],
                conditions={"ArnEquals": {"iam:PolicyARN": LAMBDA_BASIC_EXEC}},
            ),
            S(  # The chat API caller user and its inline policy.
                effect=allow,
                actions=[
                    "iam:CreateUser", "iam:DeleteUser", "iam:GetUser", "iam:UpdateUser",
                    "iam:TagUser", "iam:UntagUser", "iam:ListUserTags", "iam:PutUserPolicy",
                    "iam:DeleteUserPolicy", "iam:GetUserPolicy", "iam:ListUserPolicies",
                    "iam:ListAccessKeys", "iam:DeleteAccessKey", "iam:ListAttachedUserPolicies",
                ],
                resources=[a("iam", "user/ai-radar-chat-api-caller", region=False)],
            ),
            S(  # Attaching managed policies to the caller user: only AiRadar* customer policies.
                effect=allow,
                actions=["iam:AttachUserPolicy", "iam:DetachUserPolicy"],
                resources=[a("iam", "user/ai-radar-chat-api-caller", region=False)],
                conditions={"ArnLike": {"iam:PolicyARN": a("iam", "policy/AiRadar*", region=False)}},
            ),
            S(  # Schedule physical names start with the stack name.
                effect=allow,
                actions=[
                    "scheduler:CreateSchedule", "scheduler:UpdateSchedule",
                    "scheduler:DeleteSchedule", "scheduler:GetSchedule",
                    "scheduler:TagResource", "scheduler:ListTagsForResource",
                ],
                resources=[a("scheduler", "schedule/default/AiRadar*")],
            ),
            S(  # Budgets are account-level names; scoped to ARNs under this account.
                effect=allow,
                actions=[
                    "budgets:CreateBudget", "budgets:ModifyBudget", "budgets:DeleteBudget",
                    "budgets:ViewBudget", "budgets:CreateNotification",
                    "budgets:UpdateNotification", "budgets:DeleteNotification",
                    "budgets:CreateSubscriber", "budgets:UpdateSubscriber",
                    "budgets:DeleteSubscriber", "budgets:ListTagsForResource",
                    "budgets:TagResource", "budgets:UntagResource",
                ],
                resources=[a("budgets", "budget/ai-radar-*", region=False)],
            ),
            S(effect=allow, actions=["billing:GetBillingViewData"], resources=["*"]),
            # ---- explicit denies: CloudFormation can never edit the access it runs under ----
            S(
                effect=iam.Effect.DENY,
                actions=[
                    "iam:CreateRole", "iam:DeleteRole", "iam:UpdateRole", "iam:UpdateAssumeRolePolicy",
                    "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:AttachRolePolicy",
                    "iam:DetachRolePolicy", "iam:TagRole", "iam:UntagRole", "iam:PassRole",
                    "iam:PutRolePermissionsBoundary", "iam:DeleteRolePermissionsBoundary",
                ],
                resources=[*ci_roles, a("iam", f"role/cdk-{QUALIFIER}-*", region=False)],
            ),
            S(
                effect=iam.Effect.DENY,
                actions=[
                    "iam:DeleteOpenIDConnectProvider", "iam:UpdateOpenIDConnectProviderThumbprint",
                    "iam:AddClientIDToOpenIDConnectProvider",
                    "iam:RemoveClientIDFromOpenIDConnectProvider",
                    "iam:TagOpenIDConnectProvider", "iam:UntagOpenIDConnectProvider",
                ],
                resources=[a("iam", f"oidc-provider/{OIDC_HOST}", region=False)],
            ),
            S(
                effect=iam.Effect.DENY,
                actions=[
                    "iam:DeletePolicy", "iam:CreatePolicyVersion", "iam:DeletePolicyVersion",
                    "iam:SetDefaultPolicyVersion",
                ],
                resources=[a("iam", f"policy/{n}", region=False) for n in EXEC_POLICIES],
            ),
            S(
                effect=iam.Effect.DENY,
                actions=["dynamodb:DeleteTable"],
                resources=[a("dynamodb", "table/ai-radar-cards")],
            ),
        ]

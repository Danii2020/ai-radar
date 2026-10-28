# Execution Plan: Backend CI/CD Pipeline

## Guidance consulted
- `CLAUDE.md` (account migration, the pinned account literals, the `=none` and `budget_limit_usd`
  flags, the toolkit deprecation, the `agentcore destroy` gotcha, the uv-only rule, and the AD-1
  `--only-group` packaging gotcha).
- `docs/architecture-principles.md` (planes never import each other; no speculative layers).
- `harny-sync` lookup: `specs/current/_index.md`, `runtime-deployment.md` (RD-3, RD-7, RD-8),
  `scheduling.md` (SC-1, ES-2), `chat-api-auth.md` (CAAUTH-2, CAAUTH-5, CAAUTH-6, invariants,
  CAAUTH-F3, CAAUTH-ADMIN). The ADR registry says the next free number is **0040**.
- `README.md`: the AgentCore Runtime deploy and teardown runbook, the chat agent runbook (AC10,
  `-a` and `default_agent` notes), the chat API and auth amendment, and "Account migration".
- `infra/app.py`, `infra/cdk.json`, `infra/stacks/*.py`, `infra/lib/{chat_api,feed_api,
  agent_runtime,chat_runtime,curation_schedule,cost_budget}.py`.
- `Dockerfile`, `Dockerfile.chat_api`, `Dockerfile.feed_api`, `.dockerignore`, `.gitignore`.
- `run_chat_api_smoke.py`, `tests/test_chat_api_smoke.py`, `tests/test_infra*.py` (offline synth
  with `aws_cdk.assertions.Template`).
- `.github/workflows/harny-feedback.yml` (generated; the gitleaks step; `actions/checkout@v5`).
- The local, gitignored `.bedrock_agentcore.yaml` (read for its shape only: absolute
  `source_path`, CDK role ARNs with random suffixes, `agent_id` per agent, a `codebuild` block,
  `container_runtime: docker`).
- The installed `bedrock-agentcore-starter-toolkit` 0.3.10 source: `agentcore deploy` options
  `-a`, `--local-build`, `--image-tag`, `--auto-update-on-conflict` and `--env`; the default
  CodeBuild path calls `iam:CreateRole`, `s3:CreateBucket` and `codebuild:CreateProject` when
  those are missing.
- AWS CDK guide (Context7, `/awsdocs/aws-cdk-guide`): `cdk diff --method=template` compares
  templates and uses the **lookup role**. `auto` and `change-set` create a change set and use the
  deploy role.
- GitHub OIDC behavior (web search, to be confirmed against GitHub's docs by the implementer): a
  fork PR on `pull_request` cannot mint an id token; the same-repo PR subject is
  `repo:<owner>/<repo>:pull_request`; a push to `main` is `repo:<owner>/<repo>:ref:refs/heads/main`.
- `gh repo view`: `Danii2020/ai-radar` is **public**, default branch `main`, and `main` has no
  branch protection today (human answer to Q2).
- AWS CDK guide (Context7): `CliCredentialsStackSynthesizer` deploys with the caller's own
  credentials, with no bootstrap deploy role and no CloudFormation execution role (unless
  `--role-arn` is passed). `cdk bootstrap --cloudformation-execution-policies <arn>` sets the
  execution role's managed policies.
- The resource types in the synthesized stacks (from the local `infra/cdk.out`, which predates the
  two chat stacks, plus a reading of `infra/lib/chat_*.py`): `AWS::DynamoDB::GlobalTable`,
  `AWS::IAM::Role`, `AWS::IAM::Policy`, `AWS::IAM::User`, `AWS::SecretsManager::Secret`,
  `AWS::SQS::Queue`, `AWS::SQS::QueuePolicy`, `AWS::Scheduler::Schedule`, `AWS::Budgets::Budget`,
  `AWS::SNS::Topic`, `AWS::SNS::TopicPolicy`, `AWS::SNS::Subscription`, `AWS::Lambda::Function`,
  `AWS::Lambda::Permission`, `AWS::Logs::LogGroup`, `AWS::ApiGatewayV2::{Api,Stage,Route,Integration}`,
  `AWS::CDK::Metadata`, and the SSM parameter type for `/ai-radar/agent-runtime-arn`. The coverage
  test (AC13) derives the real list from a fresh synth, so this list is not binding.
- Human answers to Q1–Q5 (2026-10-27, through the coordinator).

## Ownership
- New workflows under `.github/workflows/` (the backend checks, PR and deploy workflows).
- New CI helpers (a suggested `scripts/ci/` package): change detection and target mapping, the
  agent config renderer, the schedule guard, the origin validation, the smoke runner, and the
  repository-protection script.
- New pinned deploy context file, and a CI AgentCore config template.
- New CI access CDK app (a suggested `infra/ci_bootstrap/`), separate from `infra/app.py`: the
  OIDC provider, the three CI roles, and the scoped CloudFormation execution managed policy.
- New `.github/CODEOWNERS`.
- `run_chat_api_smoke.py`: one opt-in exit-code option.
- `pyproject.toml` / `uv.lock`: declare `pyyaml` in the `dev` group if tests parse YAML (it is
  only a transitive dependency today).
- `README.md`: a new "Backend CI/CD" runbook section.
- Affected `specs/current` capabilities: `runtime-deployment` (CI deploy path for the agents),
  `scheduling` (the schedule guard), `chat-api-auth` (the second route principal; amends ADR 0028,
  accepted by the human), `feed-api` (the origins now come from the committed context). A new
  `ci-cd` capability is likely at archive time.

## Binding constraints
- Account `626259825216`, region `us-east-1`, repo `Danii2020/ai-radar`, branch `main`; OIDC only,
  no long-lived AWS key in GitHub secrets or variables (human decision 1).
- No manual approval gate, no GitHub environment with required reviewers (human decision 2).
  Adding `environment:` to the deploy job would change the OIDC subject to
  `...:environment:<name>`, so the deploy job does not use one.
- Deploy-workflow concurrency: one fixed group for every deploy run, `cancel-in-progress: false`.
  The PR workflow may cancel superseded PR runs (its own group per PR).
- The deploy base is the head commit of the **last successful** deploy-workflow run on `main`,
  never the push's parent commit (AC4, AC5). If none exists, or it is not an ancestor of `HEAD`,
  every target is selected.
- Deploy context, used identically by PR synth, PR diff and deploy, from one committed file:
  `feed_api_reserved_concurrency=none`, `chat_api_reserved_concurrency=none`, `budget_limit_usd=500`,
  and `feed_api_allowed_origins` (AC15). No `schedule_*` key. The origins value is
  `http://localhost:3000` today, which equals the live allow-list (README "Account migration"), so
  AC12 holds. The Vercel origin is added to this file, never passed by hand, because CI's next
  `AiRadarFeedApi` deploy reverts any hand-passed `-c feed_api_allowed_origins`
  (`infra/stacks/feed_api_stack.py`).
- Origin validation (AC15): each comma-separated origin is `http://localhost:<port>` or an `https://`
  URL with a host and no path, and no origin contains `<`, `>`, `{`, `}` or the word `placeholder`.
  It runs in the PR checks and before any deploy. This is why the committed file does not carry
  `https://<project>.vercel.app` literally: a literal placeholder would block every run, and if it
  passed it would be deployed as a real origin.
- Schedule guard: the synthesized `AiRadarSchedule` template's `AWS::Scheduler::Schedule` `State`
  must equal `DISABLED`, or the run fails before any deploy (SC-1).
- Agents: CI runs only `agentcore deploy -a <agent>`. Chat always gets
  `--env AGENT_ENTRYPOINT=chat_app.py` (RD-8). CI never runs `configure --create`, `destroy`,
  `invoke` on the curation agent, or `cdk destroy`. The rendered CI config must carry each agent's
  existing `agent_id` and `agent_arn`, and the render fails if either is missing, so the toolkit
  updates and never creates.
- Agent Dockerfile placement (AC6, audit F1, revision 3): in the locked toolkit 0.3.10,
  `agentcore deploy --local-build` resolves the Dockerfile as
  `get_agentcore_directory(<dir of the rendered .bedrock_agentcore.yaml>, <agent>, source_path) /
  "Dockerfile"`, which is `<config dir>/.bedrock_agentcore/<agent>/Dockerfile` whenever
  `source_path` is set, and raises `Dockerfile not found` when it is absent
  (`operations/runtime/launch.py` ~l.931–938; `utils/runtime/config.py` `get_agentcore_directory`).
  `.bedrock_agentcore/` is gitignored, so the deploy job must, before each `agentcore deploy`,
  run `mkdir -p` on that directory for both `ai_radar_curation` and `ai_radar_chat` and copy the
  repo-root `Dockerfile` into it unchanged. The renderer and `source_path` stay as they are, and
  the image build context stays `source_path` (the repo root), so the root `Dockerfile`'s `COPY`
  paths resolve as in the human runbook. No second Dockerfile is committed (RD-8).
- CI never reads or writes the developer's `.bedrock_agentcore.yaml`. It renders its own copy in
  the runner workspace from a committed template, filling `source_path` with the checkout path and
  each `execution_role` from the `ExecutionRoleArn` outputs of `AiRadarRuntimeRole` and
  `AiRadarChatRuntime`. These ARNs and the account id are not secrets; the account is already
  committed in `infra/lib/*.py`.
- PR diff: same-repo PRs only (guard on `github.event.pull_request.head.repo.full_name ==
  github.repository`, as well as the OIDC trust), `cdk diff --method=template`, through a role that
  can only `sts:AssumeRole` the CDK lookup role. No `pull_request_target` anywhere.
- Every third-party action is pinned to a full 40-character commit SHA with a version comment.
  Downloaded binaries (actionlint, and the CDK CLI through npm) are pinned by version, and binaries
  are checksum-verified like the existing gitleaks step.
- Public logs (AC10): mask the chat API id and URL with `::add-mask::` before any step that can
  print them (`cdk deploy` prints the `ChatApiUrl` output; `cdk diff` and describe calls can show
  it). Never print credentials or the `Authorization` header. The smoke runner already never prints
  them (`run_chat_api_smoke.py` docstring). Revision 3 (audit F5): the deploy job also masks from
  `vars.CHAT_API_ID`, as the PR job does, and its read of the deployed chat URL fails the step on
  error (no `|| true`, no `2>/dev/null` swallowing the failure), so a throttled read can never let
  `cdk deploy AiRadarChatApi` print the URL unmasked.
- The CI roles and the execution policy live in a separate CDK app that the CI workflows never
  deploy. It uses `CliCredentialsStackSynthesizer`, so the human's `cdk deploy` of it runs with the
  human's own administrator credentials, not through the CDK deploy role or the scoped execution
  role. Trust policies: audience `sts.amazonaws.com`, exact `sub` match (`StringEquals`, not
  `StringLike` with a wildcard). CI role names do not start with `AiRadar` or `ai-radar` (for
  example `gha-airadar-deploy`), so the execution policy's name patterns never match them.
- Scoped execution policy (AC13): one or two customer-managed policies (revision 3, audit F2:
  one policy measured 5,742 of 6,144 characters before the missing actions were added), each
  under 6,144 characters after intrinsics resolve, both named outside the `AiRadar*` pattern (for
  example `cdk-exec-airadar` and `cdk-exec-airadar-2`), both passed to the bootstrap. Across
  both: no `"*"` action and no `<service>:*` across a whole service on
  `"*"` resources; IAM write actions only on `role/AiRadar*`, `policy/AiRadar*` and
  `user/ai-radar-chat-api-caller`; explicit `Deny` on the CI roles, the OIDC provider, the
  `cdk-hnb659fds-*` roles, both execution policies (a `policy/cdk-exec-airadar*` pattern), and
  `dynamodb:DeleteTable` on `ai-radar-cards`.
- Handler completeness (AC13, audit F2): for every resource type in the seven synthesized stacks,
  each permission in the CloudFormation registry schema's `handlers.{create,read,update,delete}`
  lists is either allowed (name-scoped where the service supports it) or appears in a committed
  omission list with a one-line reason. The handler lists are committed as a snapshot extracted
  from the public `https://schema.cloudformation.us-east-1.amazonaws.com/CloudformationSchema.zip`
  (with its extraction date), so the test runs offline; refreshing the snapshot is a reviewed PR.
  At minimum the policies add the actions the audit found missing, each confirmed in that schema
  on 2026-10-28: `AWS::Lambda::Function` `lambda:GetFunctionCodeSigningConfig`,
  `lambda:GetRuntimeManagementConfig`, `lambda:GetFunctionRecursionConfig`,
  `lambda:PutRuntimeManagementConfig`, `lambda:PutFunctionRecursionConfig`,
  `lambda:PutFunctionCodeSigningConfig`, `lambda:DeleteFunctionCodeSigningConfig`,
  `lambda:GetFunctionScalingConfig`, `lambda:PutFunctionScalingConfig`; `AWS::SNS::Topic`
  `sns:ListSubscriptionsByTopic`, `sns:GetDataProtectionPolicy`, `sns:PutDataProtectionPolicy`;
  `AWS::DynamoDB::GlobalTable` `dynamodb:GetResourcePolicy`, `dynamodb:Describe*`;
  `AWS::Logs::LogGroup` `logs:DescribeResourcePolicies`, `logs:DescribeIndexPolicies`,
  `logs:GetDataProtectionPolicy`, `logs:ListTagsForResource`; `AWS::Budgets::Budget`
  `budgets:ListTagsForResource`, `budgets:TagResource`, `budgets:UntagResource`,
  `billing:GetBillingViewData`; `AWS::IAM::Role` `iam:UpdateRoleDescription`. Never added:
  `iam:CreateServiceLinkedRole` (only for cross-region table replicas). Expected omissions with
  reasons: VPC, EFS, S3 Files, KMS, Kinesis and Application Auto Scaling actions (no VPC, EFS, CMK,
  stream or autoscaling in the stacks), `lambda:PassCapacityProvider`/`AssociateRuntimeAlias` and
  `logs:CreateLogDelivery`/`s3:REST.PUT.OBJECT`/`firehose:*` (features not used), and
  `dynamodb:DeleteTable`/`DeleteTableReplica` on `ai-radar-cards` (the explicit deny stays; the
  `AWS::DynamoDB::GlobalTable` update handler uses them only for replica removal; the table is
  `RETAIN` and has no replicas, so a future replica removal needs a manual step outside the
  execution role). Decided by the human on 2026-10-28: `secretsmanager:GetSecretValue` is allowed
  only on `arn:aws:secretsmanager:us-east-1:<account>:secret:ai-radar/tavily-api-key-*` (the
  pattern `infra/lib/agent_runtime.py` uses), never on `secret:ai-radar/*` or `*`; the item actions
  `Query`, `Scan`, `GetItem`, `PutItem`, `UpdateItem`, `DeleteItem`, `BatchWriteItem` are allowed
  only on `table/ai-radar-cards` and `table/ai-radar-cards/index/feed-by-score`.
- Resource coverage (AC13, audit F3): for each resource in the seven synthesized templates, its
  physical name or ARN (from its explicit name property, or the CloudFormation-generated
  `<StackName>-<LogicalId>-…` form when it has none) must match the `Resource` patterns of the
  allow statements that grant that type's actions. Types whose actions are allowed on `"*"` by
  necessity (API Gateway v2) are exempt and listed in the test. Services that cannot be name-scoped (API Gateway v2 ids, some `Describe`/`List`
  calls) may use `"*"` resources for those actions only, each with a comment in code. The policy
  keeps the read access CDK and CloudFormation need (for example `ssm:GetParameters` for the
  `/ai-radar/agent-runtime-arn` parameter type and the `/cdk-bootstrap/hnb659fds/version` check).
- Repository protection (AC14): the script defaults to a dry run and writes only with an explicit
  `--apply`. The required check names come from one constant that a test compares with the
  workflow job names (a reusable workflow's check is named `<caller job> / <called job>`).
  Required approvals 0 and code-owner review off while there is one maintainer (intent open item).
  No bypass actors. Agents never run it with `--apply`.
- Public repository (AC10, AC16): every job sets `timeout-minutes`; the workflow default
  `permissions` is `contents: read`; no `secrets.*` other than `GITHUB_TOKEN`; caches are only the
  uv and npm dependency caches; no artifact upload of `cdk.out` or of any rendered config.
- `harny-feedback.yml` and `harny-feedback-apps-web.yml` are not edited (generated files).
- `run_chat_api_smoke.py` default behavior unchanged (CAAUTH-9 runbook depends on it); new behavior
  only behind a new option.
- The seven stacks' templates are unchanged by this feature (AC12).

## Proposed approach
Revisable by the executor if it records why.

- **Decision (workflow layout):** three files. A reusable `workflow_call` checks workflow (uv
  setup with cache, `pytest`, `ruff check`, `mypy`, `actionlint`, `cdk synth` with the pinned
  context, the schedule guard), a PR workflow that calls it and then runs the diff job, and a deploy
  workflow on `push` to `main` that calls it, then plans, deploys and smoke-checks. — rationale: one
  definition of "the checks" for both gates; the generated harny workflow cannot be extended.
  Rejected: adding pytest to `harny-feedback.yml` (overwritten by `harny init`); `workflow_run`
  chaining off harny-feedback (cannot pass outputs cleanly, and is harder to reason about). ruff and
  mypy run twice per PR (harny and the new checks). Accepted: they take seconds.
- **Decision (OIDC roles, ADR candidate 0040):** three roles, defined in a separate CDK app and
  deployed once by a human with admin credentials. — rationale: least privilege per job, and the
  same offline synth-test practice as `tests/test_infra*.py`.
  - *Diff role*: trust `repo:Danii2020/ai-radar:pull_request`; only `sts:AssumeRole` on
    `cdk-hnb659fds-lookup-role-626259825216-us-east-1`.
  - *Deploy role*: trust `repo:Danii2020/ai-radar:ref:refs/heads/main`; `sts:AssumeRole` on the four
    `cdk-hnb659fds-{deploy,file-publishing,image-publishing,lookup}-role-626259825216-us-east-1`;
    `cloudformation:DescribeStacks` on `AiRadar*` stacks; for `agentcore deploy --local-build`,
    `ecr:GetAuthorizationToken` (`*`, which it requires), ECR push actions on
    `bedrock-agentcore-ai_radar_curation` and `bedrock-agentcore-ai_radar_chat`,
    `bedrock-agentcore` get/update actions on the two runtime ARNs and their endpoints, and
    `iam:PassRole` on the two execution roles conditioned on
    `iam:PassedToService=bedrock-agentcore.amazonaws.com`. The final action list is confirmed from
    the first human-run deploy and CloudTrail, then recorded in the README (human answer to Q5;
    tasks O12h).
  - *Smoke role*: trust `...:ref:refs/heads/main`; `execute-api:Invoke` on
    `arn:aws:execute-api:us-east-1:626259825216:<api-id>/*/POST/v1/chat`. The API id is passed by
    the human as CDK context at bootstrap time and never committed, because the repo redacts it
    (README `<api-id>`). Tests synthesize with a fake id. ADR 0031 keeps the id stable;
    `cloudformation:DescribeStacks` on the `AiRadarFeedApi` and `AiRadarChatApi` stacks; and
    `bedrock-agentcore:GetAgentRuntime` on the two runtime ARNs.
  - Rejected: one role for everything (a PR could then deploy); IAM user keys (human decision 1);
    deploying the CI roles from CI (CI could widen its own permissions); a raw CloudFormation YAML
    template (equally valid, but no reuse of the repo's synth-test style).
- **Decision (scoped CloudFormation execution, ADR candidate 0046):** a customer-managed policy in
  the CI access app (a fixed name outside the `AiRadar*` IAM pattern, for example
  `cdk-exec-airadar`, so the allow statements cannot match the policy itself), passed to `cdk bootstrap --cloudformation-execution-policies`. —
  rationale: with the default `AdministratorAccess`, anyone who can assume the CDK deploy role (the
  CI deploy role, so any merged change on `main`) can change anything in the account; the scoped
  policy limits CloudFormation to the AI Radar services and names, and the explicit denies keep it
  from editing the CI access it runs under. Rejected: keeping `AdministratorAccess` (the human chose
  to scope it); a permissions boundary on every created role (changes all seven stacks' role
  templates, so it breaks AC12; recorded as a follow-up, because a merged change can still create
  an `AiRadar*` role with broad permissions, which is the residual escalation path of any IaC
  pipeline); a separate qualifier and second bootstrap for CI (two asset buckets and repositories,
  and the human's own deploys stay admin).
  - Revision 3 (audit F2): the policy may be split into two customer-managed policies (CloudFormation
    execution policies are a list; the CDK CLI takes several ARNs as one comma-separated string or
    as a repeated option, per the CDK guide's `cdk bootstrap` reference). Rejected: compressing one
    policy below the limit by widening patterns or actions (trades scope for size).
  - Offline proof: a test synthesizes the seven stacks with the pinned context, collects their
    resource types, and checks each type's handler permissions from the committed schema snapshot
    against the union of both policies' allow statements, minus the committed omission list. A new
    resource type, or a handler permission neither allowed nor omitted, fails the test. A
    resource-coverage test (audit F3) checks each resource's physical name against the allow
    statements' `Resource` patterns. A shape test asserts the denies and the absence of `"*"`
    actions across both policies. A size test asserts each policy under 6,144 characters.
  - Live proof (human-only, tasks O12): order is (1) deploy the CI access app with admin credentials,
    (2) optionally run `aws iam simulate-custom-policy` for the mapped actions, (3) `cdk bootstrap
    aws://626259825216/us-east-1 --cloudformation-execution-policies "<policy-arn-1>,<policy-arn-2>"`
    (one ARN if only one policy exists), (4) `cdk synth` and `cdk diff` of all seven stacks with the
    pinned context (expect no differences), (5) the next real deploy, watched; an `AccessDenied` in
    CloudFormation events names the missing action, which is added in a PR. Rollback: `cdk bootstrap
    aws://626259825216/us-east-1 --cloudformation-execution-policies
    arn:aws:iam::aws:policy/AdministratorAccess` (this replaces both scoped policies), then re-run
    the failed deploy. The README runbook and its rollback text carry the same commands.
  - A re-bootstrap with a newer CDK CLI may also bump the bootstrap stack version; the runbook pins
    the CLI version used.
- **Decision (PR diff, ADR candidate 0041):** `cdk diff --method=template` through the lookup role,
  output to `$GITHUB_STEP_SUMMARY`, collapsed per stack, with the chat API id masked. Fork PRs skip
  the job with an explanatory summary line. — rationale: no write permission and no change set on
  PRs, no `pull-requests: write` token needed. Rejected: a PR comment (needs a write token, and fork
  PRs could not post anyway); `pull_request_target` (runs fork code with secrets); `--method=auto`
  (creates change sets with the deploy role).
- **Decision (change detection, ADR candidate 0042):** a small, pure Python planner. Inputs: the
  changed paths (from `git diff --name-only <base>..HEAD`) and the committed mapping. Output: the
  ordered target list. The base comes from the GitHub API (`gh run list` / REST, last successful
  run of the deploy workflow on `main`, needs `actions: read`). — rationale: concurrency's "replace
  the pending run" behavior otherwise drops commits; a failed run's changes are retried by the next
  run. Rejected: the parent commit (loses superseded commits); a moving git tag (needs
  `contents: write`); an SSM "last deployed" parameter (an extra write permission). Suggested
  mapping (the implementer finalizes it, and a test pins it):

  | Changed path | Targets |
  |---|---|
  | `infra/lib/card_store.py`, `infra/stacks/card_store_stack.py` | `AiRadarCardStore` |
  | `infra/lib/agent_runtime.py`, `infra/stacks/agent_runtime_stack.py` | `AiRadarRuntimeRole` |
  | `infra/lib/chat_runtime.py`, `infra/stacks/chat_runtime_stack.py` | `AiRadarChatRuntime` |
  | `infra/lib/curation_schedule.py`, `infra/stacks/curation_schedule_stack.py` | `AiRadarSchedule` |
  | `infra/lib/cost_budget.py`, `infra/stacks/cost_budget_stack.py` | `AiRadarBudget` |
  | `infra/lib/feed_api.py`, `infra/stacks/feed_api_stack.py`, `Dockerfile.feed_api`, `src/api/**`, `src/contracts/**` | `AiRadarFeedApi` |
  | `infra/lib/chat_api.py`, `infra/stacks/chat_api_stack.py`, `Dockerfile.chat_api`, `src/chat_api/**` | `AiRadarChatApi` |
  | `Dockerfile`, `runtime_app.py`, `chat_app.py`, `src/**` (any) | agents `ai_radar_curation` and `ai_radar_chat` (one shared image) |
  | `pyproject.toml`, `uv.lock`, `.dockerignore` | both agents, `AiRadarFeedApi`, `AiRadarChatApi` |
  | `infra/app.py`, `infra/cdk.json`, the deploy context file, `infra/lib/__init__.py`, any other `infra/**` path outside the CI access app | all seven stacks |
  | `.github/workflows/backend-*`, the CI helpers, the CI agent config template | all targets (the pipeline itself changed) |
  | the CI access app (`infra/ci_bootstrap/**`), the repository-protection script, `.github/CODEOWNERS` | none (human-applied, never deployed by CI) |
  | anything else (`apps/web/**`, `docs/**`, `specs/**`, `tests/**`, `README.md`, other root scripts) | none |

  Unknown paths under the deploy-relevant roots above select all targets (fail-safe). CDK itself
  skips an unchanged stack, so over-selecting a stack costs only time.
- **Decision (dependency order):** `AiRadarCardStore` → `AiRadarRuntimeRole` → `AiRadarChatRuntime`
  → agent `ai_radar_curation` → agent `ai_radar_chat` → `AiRadarSchedule` → `AiRadarBudget` →
  `AiRadarFeedApi` → `AiRadarChatApi`, filtered to the selected targets, one at a time, stopping at
  the first failure. — rationale: the roles must exist before an agent is updated to use them; the
  schedule reads the curation agent's ARN from SSM; the chat API points at the chat runtime id.
  There are no CloudFormation cross-stack exports, so CDK will not infer this order itself.
  Pass explicit stack names with `--exclusively` so CDK never pulls in other stacks.
- **Decision (agents, ADR candidate 0044):** `agentcore deploy -a <agent> --local-build
  --image-tag <short sha>` on a native arm64 runner (`ubuntu-24.04-arm`, free for public repos),
  from the rendered CI config. — rationale: no CodeBuild path, so the deploy role needs no
  `iam:CreateRole`, `s3:CreateBucket` or `codebuild:*`; native arm64 matches the image platform and
  the two arm64 Lambda image assets; the sha tag makes the deployed image traceable and gives the
  manual rollback a target. Rejected: the default CodeBuild build (wider IAM, a toolkit-created
  role); calling `UpdateAgentRuntime` with boto3 directly (re-implements the toolkit and diverges
  from the human runbook). The rendered config keeps `ecr_auto_create: false` and
  `execution_role_auto_create: false`. The human runbook (CodeBuild) stays valid; both build the
  same root `Dockerfile`.
  - Consequence (revision 3, audit F1): the decision stands, with one extra step. The local-build
    path has no fallback to the source root (the CodeBuild path does, which is why the human runbook
    works). So the deploy job copies the root `Dockerfile` to `.bedrock_agentcore/<agent>/Dockerfile`
    beside the rendered config for both agents before deploying. This couples CI to the toolkit's
    private build-artifact layout (`get_agentcore_directory`), which can change in any toolkit
    release. The `uv.lock` pin (0.3.10) and an offline test that computes the path with the
    toolkit's own `get_agentcore_directory` catch such a change at the toolkit bump, not at deploy
    time. Rejected: `source_path: null` (contradicts the binding constraint and the toolkit's
    multi-agent layout); having the renderer write the Dockerfile (changes the renderer's contract
    that its output dir holds only the YAML); committing `.bedrock_agentcore/<agent>/Dockerfile`
    copies (two more Dockerfiles that drift from the root one, against RD-8).
- **Decision (pinned context and guard, ADR candidate 0045):** one committed JSON context file
  read by a thin wrapper, so every CI `cdk` call gets identical `-c` flags; the schedule guard reads
  `cdk.out/AiRadarSchedule.template.json` after synth; the origin validation (AC15) runs on the file
  before synth. Adding the Vercel origin is a one-line PR to this file; its diff (AC2) shows the
  `AiRadarFeedApi` CORS change before merge. Suggestion: the README tells humans to use
  the same file for local deploys. Rejected: putting the context in `infra/cdk.json` (the README's
  `cdk --app "python infra/app.py"` from the repo root does not read it, so humans and CI would
  diverge silently).
- **Decision (smoke, ADR candidate 0043):** a CI smoke runner (Python, standard library plus boto3)
  running the four AC7 probes. It reads the feed and chat URLs from the stacks' outputs, masks the
  chat URL, calls `run_chat_api_smoke.py` for both chat probes with a new opt-in option that turns a
  status or body mismatch into a non-zero exit (for example `--expect-status 200` and a check for
  `answer` and `sources` keys), and checks `GetAgentRuntime` status `READY` for both runtime ids.
  Credentials: the smoke role (AC8). All four probes run after every run that deployed at least
  one target, whatever the target (human answer to Q3); a run that deployed nothing runs none.
  The second route principal is accepted (human answer to Q4). — rationale: it
  reuses the existing signing helper, needs no stored secret, and catches the RD-8 failure mode.
  Cost: one Titan embed plus at most one Sonnet 4.6 turn per deploy run (a no-context answer makes no
  Sonnet call, ADR 0018). The 16-card corpus keeps the prompt small. Rejected: storing the caller key
  in GitHub (human decision 1, ADR 0030); invoking the curation agent (writes cards, spends Haiku
  and Tavily credits).
- **Decision (setup):** `astral-sh/setup-uv` with `enable-cache: true` keyed on `uv.lock` and a
  pinned uv version; Python 3.12 (the Docker images' version); `uv sync --frozen --all-groups`;
  `actions/setup-node` with a pinned Node major and a pinned `aws-cdk` CLI version compatible with
  `aws-cdk-lib` in `uv.lock`; `aws-actions/configure-aws-credentials` pinned by SHA, with
  `role-session-name` naming the run id. Job `permissions` default to `contents: read`; only jobs
  that assume AWS roles add `id-token: write`; the plan job adds `actions: read`.
- **Decision (manual re-run):** a `workflow_dispatch` trigger on the deploy workflow with a
  `deploy_all` boolean, usable only on `main` (the OIDC subject enforces it). It is not an approval
  gate; it exists for rollback and recovery. Suggestion, can be dropped.
- **Decision (repository protection, ADR candidate 0047):** a Python script in the CI helpers that
  builds each payload with pure functions and calls `gh api` through one injectable runner. Default:
  print the method, endpoint and JSON for each change, with no write call; `--apply` writes. It
  reads the current state first and only writes what differs, so a re-run is a no-op. It sets:
  - a repository ruleset named for example `main-protection` on `refs/heads/main`: `pull_request`
    (required approvals 0, code-owner review off while solo), `required_status_checks` with
    `strict_required_status_checks_policy: true` (up to date before merge) listing the AC1 check
    jobs, `non_fast_forward`, `deletion`; enforcement `active`; no bypass actors. Create when absent
    (`POST /repos/{owner}/{repo}/rulesets`), update when present (`PUT .../rulesets/{id}`), matched
    by name;
  - `security_and_analysis`: secret scanning and push protection enabled (`PATCH /repos/{owner}/{repo}`);
  - the default workflow token read-only and unable to approve PRs
    (`PUT /repos/{owner}/{repo}/actions/permissions/workflow`);
  - approval required before workflows run for all outside contributors' PRs (the fork PR
    contributor approval endpoint). The implementer confirms every endpoint against GitHub's REST
    docs; any setting with no API is listed in the runbook as a manual settings step.
  — rationale: rulesets are available on public repositories; a committed, reviewable, re-runnable
  script beats undocumented clicks. Rejected: classic branch protection (rulesets supersede it and
  are listable as JSON); Terraform's GitHub provider (a new tool and state for four settings);
  applying from CI (needs an admin token stored in GitHub).
- **Decision (`CODEOWNERS`):** `.github/CODEOWNERS` names `@Danii2020` for `.github/workflows/`,
  `.github/CODEOWNERS`, the CI helpers, `infra/ci_bootstrap/` and the deploy context file. It only
  requests review today (see the solo-maintainer open item); it becomes enforcing when a second
  maintainer joins and the ruleset turns on code-owner review.
- **Suggestion:** Dependabot for the `github-actions` ecosystem so the SHA pins get updates.

## Public repository risks
Kept as the risk register in the README runbook (AC11). The actionable rows are ACs or tasks.

| Risk | What protects it | Where |
|---|---|---|
| Workflow files, role names, role ARNs and the account id are world-readable | Nothing relies on their being hidden: trust policies pin `aud` and `sub`; the account id is already committed | AC3, AC9 |
| A fork PR tries to get AWS access | Fork PRs on `pull_request` get no OIDC token and no secrets; no `pull_request_target`; the diff job's same-repo guard; the deploy and smoke roles trust only `refs/heads/main`, the diff role only same-repo `pull_request` | AC2, AC3, AC9 |
| A branch other than `main` assumes the deploy role | Exact `sub` `repo:Danii2020/ai-radar:ref:refs/heads/main` with `StringEquals` | AC3, AC9 |
| A malicious PR from a collaborator, or a compromised workflow edit on a branch, runs attacker code in PR checks | That code can reach only the diff role, which can only assume the read-only lookup role (no change sets, no `kms:Decrypt`, no `secretsmanager:GetSecretValue`); deploy and smoke roles are `main`-only | AC2, AC9 |
| Workflow-file changes are a privilege path (a merged edit runs with the deploy role) | The ruleset requires a PR and the checks for every change to `main`; `CODEOWNERS` on workflows, CI helpers, CI access app and context file; the scoped execution policy limits what a merged change can do; the CI access stack is never deployed by CI | AC13, AC14, AC16 |
| Public logs leak ids, URLs or credentials | `::add-mask::` for the chat API id and URL; no `env` dumps, no `set -x`; credentials never printed | AC10 |
| Actions minutes and cost abuse (public repos get free standard runners, but fork PRs can spam runs, and every deploy spends Bedrock) | Approval required for outside contributors' workflow runs; `timeout-minutes` on every job; PR concurrency cancels superseded runs; deploys only on `main` | AC14, AC16 |
| Committed secrets | gitleaks in `harny-feedback.yml` (unchanged); GitHub secret scanning and push protection enabled by the script | AC10, AC14 |
| Caches and artifacts are readable by fork PR runs | Only uv and npm dependency caches; no `cdk.out`, rendered config or credential in a cache or artifact | AC10 |
| The chat API is public-facing with real Bedrock cost | Unsigned requests get 403 at the gateway with no Lambda or Bedrock spend (CAAUTH-2); stage throttle 5 rps, burst 10 (CAPI-F13 notes it is lenient, about twice nominal); the smoke role is usable only from `main` and sends one signed request per deploy; `AiRadarBudget` alerts are the backstop | AC7, AC8 |
| The CloudFormation execution role can read the Tavily key and the card table's items (the handlers require it) | `GetSecretValue` only on the one Tavily secret; item actions only on the card table and its index; the role is assumable only through the CDK deploy role, which only `main` reaches (human decision 2026-10-28) | AC13 |
| An administrator identity in the account can call the route (no resource policy on HTTP APIs) | Accepted limitation `CAAUTH-ADMIN`, unchanged | — |

## Consumers and migration
- `run_chat_api_smoke.py` and `tests/test_chat_api_smoke.py`: add the opt-in option and its tests;
  the existing tests must pass unchanged (CAAUTH-9 runbook usage is unchanged).
- `harny-feedback.yml`: unchanged; it keeps running ruff, mypy and gitleaks.
- The human runbooks in `README.md` (`runtime-packaging`, chat agent, chat API, account
  migration): unchanged procedures. Add a note that CI now deploys on merge, that local deploys
  should use the pinned context file, and that a hand deploy with different context (for example a
  CORS origin) is reverted by the next CI deploy of that stack unless the file is updated.
- The local `.bedrock_agentcore.yaml`: untouched; CI renders its own.
- `tests/test_infra*.py`: unchanged; the new tests sit beside them.
- `CLAUDE.md` "Current state" and the README spec tables: the documentation step updates them.
- The human's own `cdk deploy` runs: after the re-bootstrap they go through the scoped execution
  policy too. The README account-migration and per-stack runbooks get a note, and the rollback to
  `AdministratorAccess` is documented.
- `feed-api` CORS: the README "Still open" item about pointing the allow-list at Vercel now says
  "add the origin to the deploy context file in a PR"; the `apps/web` Vercel runbook gets the same
  pointer.
- `CAAUTH-F3` (Docker build context includes caches): in a clean CI checkout it does not apply, but
  the first CI deploy will likely produce new image asset hashes for both Lambdas compared with the
  laptop deploys (identical code, different fingerprint), so both functions update once. `README.md`
  is inside the Lambda build context, so any run that selects an API stack also rebuilds that image
  if the README changed. Expected, not a defect.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The scoped execution policy misses an action, so a real deploy fails mid-stack | Med | Med | The offline coverage test; the first deploy is human-watched; CloudFormation rolls the stack back; widen in a PR, or roll back to `AdministratorAccess` (AC13). |
| A merged change creates an `AiRadar*` role with broad permissions (residual escalation path) | Low | High | Ruleset plus PR review and `CODEOWNERS`; the PR diff shows IAM changes; permissions boundaries recorded as a follow-up. |
| The re-bootstrap breaks the human's own deploys | Low | Med | The same verification and rollback as above; the runbook says so before the step. |
| The ruleset's required check names drift from the workflow job names, so merges block forever or nothing is required | Med | Med | A test compares the script's constant with the workflow job names; the verification step reads the ruleset back after a real PR. |
| A placeholder origin reaches the feed API | Low | Low | The origin validation fails the PR and the deploy (AC15). |
| A superseded queued run drops changes | Med | High | The base is the last successful deploy, not the parent (AC4); a test simulates it. |
| The toolkit creates a new agent instead of updating | Low | High | The rendered config must carry `agent_id`/`agent_arn`, and the render fails otherwise; the deploy role has no `CreateAgentRuntime`. |
| A toolkit upgrade moves the local-build Dockerfile location, so the copy step targets the wrong path | Low | High | The toolkit is pinned in `uv.lock`; the AC6 test computes the path with the toolkit's own `get_agentcore_directory`, so a bump that moves it fails offline. |
| The two execution policies drift apart or one exceeds 6,144 characters | Low | Med | The size test per policy; the coverage and shape tests run on the union of both. |
| The toolkit needs actions the deploy role lacks | Med | Med | The first deploy is human-watched; widen from the observed `AccessDenied`, record it in the README. |
| The chat agent is deployed without `AGENT_ENTRYPOINT` | Low | High | A workflow test pins the flag; the signed smoke probe catches it (AC7). |
| The schedule gets enabled by a deploy | Low | High | No `schedule_*` context anywhere (test); the template guard fails the run (AC6). |
| The chat API URL leaks into public logs | Med | Low (route is SigV4) | `::add-mask::` before printing steps; a log-hygiene test on the workflow and the runner. |
| `starter-toolkit` deprecated or broken by a release | Med | Med | Locked in `uv.lock` (0.3.10); `--frozen` sync; migration to the npm CLI is out of scope. |
| Smoke flakes (cold start, Bedrock throttling) fail a good deploy | Med | Low | A bounded retry on the signed probe only (one retry on 502/504); the run is re-runnable; the rollback note says to re-run before reverting. |
| Lambda quota 10 makes the smoke 503 under load | Low | Low | The smoke sends one request at a time. |
| Smoke spend | Low | Low | One embed plus at most one Sonnet turn per deploy; `AiRadarBudget` alerts are the backstop. |
| `ubuntu-24.04-arm` unavailable or changed | Low | Med | Fallback: `ubuntu-latest` with `docker/setup-qemu-action` and buildx (slower). |

## Validation
One row per AC. All commands run from the repo root. Offline tiers need no AWS credentials;
"live (human-only)" rows are run by a human and recorded in `tasks.md`.

| AC | Demonstrated by | Tests to write | Tier | Framework | Setup | Focused command | Broader command | Cwd |
|---|---|---|---|---|---|---|---|---|
| AC1 | The checks workflow runs pytest, ruff, mypy, actionlint and cdk synth with the pinned context; no AWS credential step in it; actionlint is clean | `tests/test_ci_workflows.py`: the checks workflow has the five commands, is called by both the PR and deploy workflows, has no `id-token` permission and no AWS credential action; failure case: a missing command fails the test | unit (static YAML) + lint | pytest + PyYAML; actionlint | add `pyyaml` to the `dev` group; install actionlint locally (pinned) | `uv run pytest tests/test_ci_workflows.py -q -k checks` and `actionlint` | `uv run pytest tests/ -q` | repo root |
| AC1 | The first real PR shows the checks green, and a deliberately failing commit shows red | none | live (human-only) | GitHub Actions | the workflows pushed on a branch | open the PR; read the checks | — | GitHub |
| AC2 | The diff job: same-repo guard, `--method=template`, diff role, summary output, fork-skip summary, no `pull_request_target` in any workflow | `tests/test_ci_workflows.py`: diff job condition, method flag, role, summary redirect, fork message; no `pull_request_target` across all workflow files | unit (static YAML) | pytest + PyYAML | as above | `uv run pytest tests/test_ci_workflows.py -q -k diff` | `uv run pytest tests/ -q` | repo root |
| AC2 | The diff role trusts only `...:pull_request` and can only assume the lookup role | `tests/test_infra_ci_bootstrap.py`: diff role trust and policy; failure case: no other action or resource | unit (CDK synth) | pytest + `aws_cdk.assertions` | none | `uv run pytest tests/test_infra_ci_bootstrap.py -q -k diff` | `uv run pytest tests/ -q` | repo root |
| AC2 | A same-repo PR shows the seven-stack diff in its summary, and a fork PR shows the skip line | none | live (human-only) | GitHub Actions | bootstrap deployed | open both PRs | — | GitHub |
| AC3 | The deploy workflow triggers on `push` to `main` (and optional `workflow_dispatch`), the deploy job `needs` the checks job, no `environment:`, OIDC via the deploy role, an account check before the first deploy step | `tests/test_ci_workflows.py`: triggers, `needs`, no environment, account guard step precedes any `cdk`/`agentcore` step | unit (static YAML) | pytest + PyYAML | as above | `uv run pytest tests/test_ci_workflows.py -q -k deploy_trigger` | `uv run pytest tests/ -q` | repo root |
| AC3 | The deploy role trusts only `repo:Danii2020/ai-radar:ref:refs/heads/main` with audience `sts.amazonaws.com` (`StringEquals`) | `tests/test_infra_ci_bootstrap.py`: deploy role trust; failure case: no `StringLike` wildcard | unit (CDK synth) | pytest + `aws_cdk.assertions` | none | `uv run pytest tests/test_infra_ci_bootstrap.py -q -k deploy` | `uv run pytest tests/ -q` | repo root |
| AC4 | Workflow concurrency group fixed, `cancel-in-progress: false`; the planner uses the last successful run's sha as base | `tests/test_ci_workflows.py` (concurrency); `tests/test_ci_deploy_plan.py`: superseded-run case (base A, commits B and C, the plan covers both), failed-previous-run case, no-success fallback to all, non-ancestor fallback to all | unit | pytest | none (the planner takes paths and shas as inputs; git and GitHub calls are injected) | `uv run pytest tests/test_ci_deploy_plan.py -q -k base` | `uv run pytest tests/ -q` | repo root |
| AC5 | The mapping and ordering: docs-only → empty; `src/chat_api/handler.py` → `AiRadarChatApi`; `src/chat/graph.py` → both agents; `uv.lock` → agents and both APIs; unknown `infra/` path → all; order is the pinned dependency order; every file under `infra/lib` and `infra/stacks` maps to at least one stack | `tests/test_ci_deploy_plan.py` (table-driven) | unit | pytest | none | `uv run pytest tests/test_ci_deploy_plan.py -q` | `uv run pytest tests/ -q` | repo root |
| AC5 | A docs-only merge makes no AWS deploy call and no smoke | `tests/test_ci_workflows.py`: deploy and smoke steps are conditioned on a non-empty plan | unit (static YAML) | pytest + PyYAML | as above | `uv run pytest tests/test_ci_workflows.py -q -k plan` | `uv run pytest tests/ -q` | repo root |
| AC6 | The context file holds exactly the four keys (`feed_api_reserved_concurrency`, `chat_api_reserved_concurrency`, `budget_limit_usd`, `feed_api_allowed_origins`); every `cdk` invocation in the workflows goes through the wrapper; no `schedule_` string in any workflow, helper or context file; `--exclusively` with explicit stack names; `agentcore` always has `-a`; chat has `AGENT_ENTRYPOINT=chat_app.py`; no `destroy`, `configure --create` or curation `invoke` | `tests/test_ci_workflows.py`; `tests/test_ci_deploy_context.py` | unit (static) | pytest + PyYAML | as above | `uv run pytest tests/test_ci_workflows.py tests/test_ci_deploy_context.py -q` | `uv run pytest tests/ -q` | repo root |
| AC6 | The schedule guard passes on the real synthesized template and fails on a template with `State: ENABLED` or no schedule | `tests/test_ci_schedule_guard.py` (synth `AiRadarSchedule` with the pinned context; plus a mutated template fixture) | unit (CDK synth) | pytest + `aws_cdk.assertions` | none | `uv run pytest tests/test_ci_schedule_guard.py -q` | `uv run pytest tests/ -q` | repo root |
| AC6 | The rendered agent config has `source_path` = the given checkout path, each `execution_role` from the given ARNs, the two pinned `agent_id`s, `execution_role_auto_create: false`, `ecr_auto_create: false`; the render fails when an ARN or agent id is missing; it never writes outside the given directory | `tests/test_ci_agentcore_config.py` (temp dir) | unit | pytest | none | `uv run pytest tests/test_ci_agentcore_config.py -q` | `uv run pytest tests/ -q` | repo root |
| AC5, AC6 | Agent Dockerfile placement (audit F1): for each agent in the rendered config, the test computes the path the toolkit will read with the toolkit's own `bedrock_agentcore_starter_toolkit.utils.runtime.config.get_agentcore_directory(<render dir>, <agent>, <source_path>) / "Dockerfile"` (in a temp dir, because that function creates the directory), maps it to the workspace-relative path, and asserts the deploy job has a step that runs `mkdir -p` on that directory and copies the repo-root `Dockerfile` there, for both `ai_radar_curation` and `ai_radar_chat`, ordered before the first `agentcore deploy -a <agent>`; failure cases: the step removed, one agent missing, the step placed after the deploy step, or a source other than the root `Dockerfile`, each fail the test | `tests/test_ci_workflows.py` (`-k dockerfile`), using the renderer from `scripts/ci/` and the locked toolkit | unit (static YAML + toolkit path function) | pytest + PyYAML | none (the toolkit is already in the `dev` group) | `uv run pytest tests/test_ci_workflows.py -q -k dockerfile` | `uv run pytest tests/ -q` | repo root |
| AC6 | The first deploy updates both agents in place (same runtime ids), `AiRadarSchedule` still `DISABLED`, budget limit 500 | none | live (human-only) | AWS CLI | bootstrap deployed; branch protection set | `aws scheduler get-schedule --name <schedule-name>`; `agentcore status -a ai_radar_chat` and `-a ai_radar_curation` | — | repo root |
| AC7 | The smoke job runs whenever the plan is non-empty, whatever the targets (a plan of only `AiRadarBudget` still runs all four probes), and never when it is empty | `tests/test_ci_workflows.py`: the smoke job's condition depends only on "plan non-empty" | unit (static YAML) | pytest + PyYAML | as above | `uv run pytest tests/test_ci_workflows.py -q -k smoke` | `uv run pytest tests/ -q` | repo root |
| AC7 | The smoke runner: the four probes, non-zero exit on any failure (feed non-200 or no `cards`; unsigned not 403; signed not 200 or no `answer`/`sources`, including the curation ack shape; a runtime not `READY`), one retry on the signed probe only for 502/504, never calls the curation agent | `tests/test_ci_smoke.py` (HTTP and boto3 stubbed; no network) | unit | pytest | none | `uv run pytest tests/test_ci_smoke.py -q` | `uv run pytest tests/ -q` | repo root |
| AC7 | The new opt-in option of `run_chat_api_smoke.py` exits non-zero on a status or shape mismatch; the default still exits 0 | `tests/test_chat_api_smoke.py` (extended; `urlopen` stubbed) | unit | pytest | none | `uv run pytest tests/test_chat_api_smoke.py -q` | `uv run pytest tests/ -q` | repo root |
| AC7 | The first real deploy runs the smoke green; the run's spend is visible in the chat log group (`chat_turn` count) | none | live (human-only) | GitHub Actions, CloudWatch | first deploy | read the run summary; count `chat_turn` records in the window | — | GitHub, AWS console |
| AC8 | The smoke role trusts only `...:ref:refs/heads/main`, has `execute-api:Invoke` on exactly the `POST /v1/chat` ARN, and the listed reads; the deploy role has no `execute-api:Invoke`; no secret named for the caller key exists in the workflows | `tests/test_infra_ci_bootstrap.py`; `tests/test_ci_workflows.py` (no `secrets.` reference other than `GITHUB_TOKEN`) | unit (CDK synth + static) | pytest + `aws_cdk.assertions` + PyYAML | none | `uv run pytest tests/test_infra_ci_bootstrap.py -q -k smoke` | `uv run pytest tests/ -q` | repo root |
| AC8 | The deploy role's signed `POST /v1/chat` returns 403; the smoke role's returns 200 | none | live (human-only) | `run_chat_api_smoke.py` | bootstrap deployed | run once under each role from a workflow, or by assuming each role locally | — | repo root |
| AC9 | The CI access app synthesizes one OIDC provider (`token.actions.githubusercontent.com`, client id `sts.amazonaws.com`), three roles and the execution policy; it uses `CliCredentialsStackSynthesizer`; no `Action: "*"`; every trust condition uses `StringEquals` on `aud` and `sub`; no CI role name starts with `AiRadar` or `ai-radar`; `infra/app.py` does not include it; no workflow references it | `tests/test_infra_ci_bootstrap.py`; `tests/test_ci_workflows.py` | unit (CDK synth + static) | pytest + `aws_cdk.assertions` + PyYAML | none | `uv run pytest tests/test_infra_ci_bootstrap.py -q` | `uv run pytest tests/ -q` | repo root |
| AC9 | The human deploys the CI access stack once with their own admin credentials and records the role ARNs as repository variables (not secrets; ARNs are not credentials) | none | live (human-only) | AWS CDK CLI | admin credentials; the chat API id as context | `cdk deploy` of the CI access app (exact command in the runbook) | — | repo root |
| AC10 | A mask step precedes every step that can print the chat URL; no `set -x`, `env` or `printenv` in any step; caches only through `setup-uv` and `setup-node` dependency caching; no `upload-artifact` of `cdk.out` or the rendered config; the smoke runner and the renderer never print credentials, `Authorization` or the unmasked chat URL | `tests/test_ci_workflows.py`; `tests/test_ci_smoke.py` (captured output contains no fake key, token or URL) | unit | pytest | none | `uv run pytest tests/test_ci_workflows.py tests/test_ci_smoke.py -q -k mask` | `uv run pytest tests/ -q` | repo root |
| AC10 | Deploy-job mask fails closed (audit F5): the deploy job's mask step references `vars.CHAT_API_ID` and emits `::add-mask::` for it; the step's read of the chat stack output contains no `\|\| true` and no `2>/dev/null`-style suppression; the step precedes every `cdk deploy`; failure cases: a fixture workflow with `\|\| true` on the read, or without `vars.CHAT_API_ID`, fails | `tests/test_ci_workflows.py` (`-k mask_deploy`) | unit (static YAML) | pytest + PyYAML | as above | `uv run pytest tests/test_ci_workflows.py -q -k mask_deploy` | `uv run pytest tests/ -q` | repo root |
| AC10 | The first deploy's public log shows `***` for the chat URL; a gitleaks run on the PR passes | none | live (human-only) | GitHub Actions | first deploy | read the log | — | GitHub |
| AC11 | The README "Backend CI/CD" section covers the CI access stack, the re-bootstrap with its verification and rollback, the protection script, first run, deploy order, PR diff reading, smoke cost, rollback, the context file (including the Vercel origin), and the public-repository risk register | none (reviewed by the auditor against this list) | docs review | — | none | — | — | repo root |
| AC12 | The seven stacks' synthesized templates are unchanged: a synth before and after, compared; the existing suite passes; `harny-feedback*.yml` unchanged in the diff | existing `tests/test_infra*.py` unchanged; a one-off template comparison recorded in `tasks.md` | integration (synth comparison) + regression | pytest; `diff` | synth at the base commit into a temp dir | `git diff --stat a49c308 -- .github/workflows/harny-feedback.yml .github/workflows/harny-feedback-apps-web.yml` (expect empty) | `uv run pytest tests/ -q`; `uv run ruff check`; `uv run mypy .` | repo root |
| AC12 | README runbook commands are intact (audit F4): in every fenced `bash`/`sh` block of `README.md`, no comment line (`#` after optional whitespace) follows a line ending in `\`; failure case: a fixture block with a comment inside a continued command fails | `tests/test_readme_runbooks.py` | unit (static text) | pytest | none | `uv run pytest tests/test_readme_runbooks.py -q` | `uv run pytest tests/ -q` | repo root |

| AC13 | Handler coverage (audit F2): for every resource type in the seven synthesized templates (pinned context), each permission in that type's create, read, update and delete handler lists (from the committed schema snapshot) is allowed by the union of the execution policies or appears in the committed omission list with a reason; the audit's named actions are allowed; `iam:CreateServiceLinkedRole` is not allowed; `dynamodb:DeleteTable` and `DeleteTableReplica` for `AWS::DynamoDB::GlobalTable` are in the omission list with the replica-removal reason, and the deny on `ai-radar-cards` is still present (deny-vs-omission case); failure cases: a fixture template with `AWS::S3::Bucket`, a snapshot permission removed from both policy and omission list, and the `DeleteTable` omission entry removed, each fail | `tests/test_infra_ci_cfn_exec_policy.py` (`-k coverage`), plus the committed handler snapshot and omission list | unit (CDK synth) | pytest + `aws_cdk.assertions` | commit the handler snapshot (extracted once from the public CloudFormation schema zip; no network in tests) | `uv run pytest tests/test_infra_ci_cfn_exec_policy.py -q -k coverage` | `uv run pytest tests/ -q` | repo root |
| AC13 | Resource coverage (audit F3): for every resource in the seven synthesized templates, its physical name or ARN (explicit name property, or the generated `<StackName>-<LogicalId>-…` form) matches the `Resource` patterns of the allow statements granting its type's actions; API Gateway v2 types are listed as `"*"`-by-necessity exemptions; failure case: a fixture Lambda named `other-fn` (outside `ai-radar-*`/`AiRadar*`) fails | `tests/test_infra_ci_cfn_exec_policy.py` (`-k resource_coverage`) | unit (CDK synth) | pytest + `aws_cdk.assertions` | none | `uv run pytest tests/test_infra_ci_cfn_exec_policy.py -q -k resource_coverage` | `uv run pytest tests/ -q` | repo root |
| AC13 | Shape and size: one or two managed policies (no longer "exactly one"); across them no `"*"` action and no whole-service wildcard on `"*"` resources; IAM writes only on `role/AiRadar*`, `policy/AiRadar*`, `user/ai-radar-chat-api-caller`; explicit denies on the CI roles, the OIDC provider, `cdk-hnb659fds-*` roles, both execution policies and `dynamodb:DeleteTable` on `ai-radar-cards`; every policy name outside the `AiRadar*` pattern; each policy under 6,144 characters with intrinsics resolved; `secretsmanager:GetSecretValue` appears only in a statement whose resources are exactly the Tavily secret pattern `secret:ai-radar/tavily-api-key-*` (failure cases: `secret:ai-radar/*` or `*`); the DynamoDB item actions appear only on the `ai-radar-cards` table ARN and its `feed-by-score` index ARN (failure case: `table/*` or `*`) | `tests/test_infra_ci_cfn_exec_policy.py` (`-k shape`); `tests/test_infra_ci_policy_size.py` (per policy) | unit (CDK synth) | pytest + `aws_cdk.assertions` | none | `uv run pytest tests/test_infra_ci_cfn_exec_policy.py tests/test_infra_ci_policy_size.py -q` | `uv run pytest tests/ -q` | repo root |
| AC13 | Re-bootstrap with the scoped policies; all seven stacks synth and `cdk diff` with no differences; the next real deploy succeeds; the rollback command is documented and, if used, recorded | none | live (human-only) | AWS CDK CLI, CloudFormation events, CloudTrail | the CI access stack deployed | `cdk bootstrap aws://626259825216/us-east-1 --cloudformation-execution-policies "<policy-arn-1>,<policy-arn-2>"`, then `cdk diff` of the seven stacks with the pinned context; rollback `cdk bootstrap aws://626259825216/us-east-1 --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess` | — | repo root |
| AC14 | The protection script: dry run by default makes no write call and prints each payload; `--apply` writes only what differs from the read state; a second `--apply` with the state now matching makes no write; the ruleset payload has `pull_request`, `required_status_checks` with strict policy, `non_fast_forward`, `deletion`, no bypass actors; the required check names equal the workflow job names | `tests/test_ci_repo_protection.py` (the `gh` runner injected; no network); a cross-check in `tests/test_ci_workflows.py` for the check names | unit | pytest | none | `uv run pytest tests/test_ci_repo_protection.py -q` | `uv run pytest tests/ -q` | repo root |
| AC14 | The human runs the script in dry run, then `--apply`; reads the settings back (`gh api repos/Danii2020/ai-radar/rulesets`, `gh api repos/Danii2020/ai-radar` for `security_and_analysis`); a direct push to `main` is rejected; a PR with a failing check cannot merge | none | live (human-only) | `gh` CLI | admin on the repo | the script in dry run, then with `--apply`; the read-back calls | — | repo root |
| AC15 | The origin validation accepts `http://localhost:3000` and `https://ai-radar-xyz.vercel.app`; rejects `https://<project>.vercel.app`, `http://example.com`, an origin with a path, and an empty value; the committed file passes; the synthesized `AiRadarFeedApi` CORS origins equal the file's list | `tests/test_ci_deploy_context.py` | unit (+ CDK synth) | pytest + `aws_cdk.assertions` | none | `uv run pytest tests/test_ci_deploy_context.py -q -k origin` | `uv run pytest tests/ -q` | repo root |
| AC15 | When the Vercel project exists, the human adds its origin in a PR; the PR diff shows the CORS change; after merge, a preflight from that origin is allowed | none | live (human-only) | `curl` | Vercel project created | `curl -si -X OPTIONS -H "Origin: https://<real>.vercel.app" -H "Access-Control-Request-Method: GET" "$FEED_API_URL/v1/cards"` | — | repo root |
| AC16 | `.github/CODEOWNERS` covers the workflows, itself, the CI helpers, `infra/ci_bootstrap/` and the context file; every job has `timeout-minutes`; the PR workflow's default permissions are read-only and only the diff job has `id-token: write`; no `secrets.*` other than `GITHUB_TOKEN` | `tests/test_ci_workflows.py` (`-k hardening`) | unit (static) | pytest + PyYAML | as above | `uv run pytest tests/test_ci_workflows.py -q -k hardening` | `uv run pytest tests/ -q` | repo root |

`act` can dry-run the workflow structure locally (`act -n`) but cannot mint GitHub OIDC tokens, so
it cannot exercise any AWS step. It is optional and not a required check.

## Revision log
- Revision 1 (2026-10-27): first draft.
- Revision 2 (2026-10-27): human answers to Q1–Q5. Added the scoped CloudFormation execution policy
  (ADR candidate 0046, binding constraints, live re-bootstrap and rollback), the repository-protection
  script (ADR candidate 0047), `CODEOWNERS`, `feed_api_allowed_origins` in the pinned context with an
  origin validation, the "Public repository risks" register, new risks, and Validation rows for AC7
  (smoke on every deploying run), AC13–AC16. The CI access app now uses
  `CliCredentialsStackSynthesizer`. The deploy-role allow-list confirmation stays a human-only step.
- Revision 3 (2026-10-28): audit round 1 fixes approved by the human. F1: agent Dockerfile placement
  (binding constraint, ADR 0044 consequence, risk, AC5/AC6 Validation row using the toolkit's
  `get_agentcore_directory`). F2: one or two execution policies, each under 6,144 characters; handler
  completeness against a committed registry-schema snapshot with an omission list; the audit's
  missing actions added, `iam:CreateServiceLinkedRole` excluded; multi-ARN re-bootstrap and rollback.
  F3: resource-name coverage row. F5: deploy-job mask row. F4: README runbook-command row.
- Revision 3, addendum (2026-10-28): the human's four AC13 decisions recorded (handler snapshot
  approved; `GetSecretValue` on the Tavily secret only; `DeleteTable` deny kept with the replica
  conflict omitted; item actions on the card table and its index only) in the handler-completeness
  constraint, the AC13 coverage and shape rows, and the public-repository risk register.

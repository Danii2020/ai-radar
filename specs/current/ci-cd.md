# CI/CD Specification

> Last synced: 2026-10-28. Owned artifacts: `.github/workflows/backend-checks.yml`,
> `.github/workflows/backend-pr.yml`, `.github/workflows/backend-deploy.yml`, `.github/CODEOWNERS`,
> `scripts/ci/**` (the deploy context and its validation, the `cdk` wrapper, the schedule guard, the deploy
> planner, the agent config template and renderer, the smoke runner, the repository protection script),
> `infra/ci_bootstrap/**` (the CI access CDK app), `tests/test_ci_*.py`, `tests/test_infra_ci_*.py`,
> `tests/fixtures/cfn/*`, `tests/test_readme_runbooks.py`, and the README "Backend CI/CD" runbook.
>
> **Status: implemented and audit-approved with reservations (round 2, 2026-10-28). NOT LIVE.** Nothing is
> deployed by CI, and the workflows have not run on GitHub. Every "live" statement below is pending the
> human-only steps O12 a–i, and none of them has run. The offline checks below are verified.
> The `ci-log-masking` fix (2026-10-28, ADR 0048) is implemented and audit-approved. It is **not committed, merged or run on GitHub**, so its live checks O4 and O6 are pending (CICD-LEAK).

## Purpose

How the backend is checked on every pull request, and how a merge to `main` deploys only the backend parts
it changed, through GitHub OIDC roles, with a scoped CloudFormation execution role, a post-deploy smoke
check and a repository ruleset that makes the checks mandatory. It is its own capability because its
boundary is different from every runtime capability: it owns the AWS trust relationships, the CI roles,
the account's CloudFormation permissions, and the repository's settings. Those change on another cadence
and by other people than the stacks and agents do. Runtime behavior stays in `runtime-deployment`,
`scheduling`, `chat-api-auth` and `feed-api`, which this capability only deploys and checks.

## Requirements

### Requirement: CICD-1 — Every pull request runs the checks without AWS credentials

The system SHALL run `pytest`, `ruff`, `mypy`, `actionlint` and `cdk synth` of all seven stacks with the
pinned context on every pull request, and SHALL fail the check on any failure. The checks SHALL hold no AWS
credential.

**Source:** backend-cicd-pipeline · intent.md § AC1; execution-plan.md § Validation AC1

#### Scenario: A PR that breaks a test
- **WHEN** a pull request breaks a test in `tests/`
- **THEN** the check fails, and the ruleset (CICD-13) blocks the merge (offline: the workflow definition is
  tested in `tests/test_ci_workflows.py`, and the auditor's full-suite rerun gave 823 passed; the live PR
  check is pending O12 d)

### Requirement: CICD-2 — The PR diff is read-only, same-repo only, and no workflow uses pull_request_target

The system SHALL post a `cdk diff --method=template` of all seven stacks to the job summary of a same-repo
pull request, through the diff role, which can only assume the CDK lookup role. A pull request from a fork
SHALL get no AWS credential and SHALL show a skip line saying so. No workflow SHALL use `pull_request_target`.

**Source:** backend-cicd-pipeline · intent.md § AC2; execution-plan.md § Proposed approach (PR diff; ADR candidate 0041, not promoted)

#### Scenario: A fork pull request
- **WHEN** a pull request comes from a fork
- **THEN** the diff job is skipped and the summary reads "diff skipped: fork PRs get no AWS credentials"
  (offline: `tests/test_ci_workflows.py -k diff`; the live fork check is pending O12 d)

### Requirement: CICD-3 — A merge deploys only after the checks pass, through OIDC, and only from main

The system SHALL start a deploy only on a push to `main`, and only after the checks pass. There SHALL be no
approval step and no GitHub environment. The deploy SHALL authenticate through GitHub OIDC to the deploy
role, whose trust accepts only `repo:Danii2020/ai-radar:ref:refs/heads/main` with audience
`sts.amazonaws.com`. Before any deploy action, the run SHALL check that the caller account is `626259825216`
and stop if it is not.

**Source:** backend-cicd-pipeline · intent.md § AC3; execution-plan.md § Binding constraints (no approval gate; OIDC only)

#### Scenario: A branch other than main
- **WHEN** a workflow on any other branch, or on a fork, asks for the deploy role
- **THEN** the role refuses it, because the exact `sub` does not match (offline: `test_deploy_role_*` and
  `test_deploy_trigger_*`; the live 403 and 200 checks are pending O12 f)

### Requirement: CICD-4 — One deploy at a time, never cancelled, and no change lost

At most one deploy run SHALL be active, and an in-flight deploy SHALL NOT be cancelled. A superseded queued
run SHALL NOT drop changes: the next deploy's base is the head commit of the last successful deploy run on
`main`, never the parent commit. If there is no such base, or the base is not an ancestor of `HEAD`, every
target SHALL be selected.

**Source:** backend-cicd-pipeline · intent.md § AC4; execution-plan.md § Binding constraints (concurrency, the deploy base); ADR 0042

#### Scenario: Two merges while a deploy runs
- **WHEN** commits B and C are merged while A is deploying, and B is superseded in the queue
- **THEN** the next run deploys the changes of B and C together (offline: `tests/test_ci_deploy_plan.py`
  base cases and `tests/test_ci_workflows.py` concurrency; the live run is pending O12 e)

### Requirement: CICD-5 — Targets come from the changed paths, with a fail-safe for unknown paths

The system SHALL compute the targets from the paths changed since the base, using the committed mapping
(seven stacks and two agents), and deploy them in the pinned dependency order. A change that touches no
deploy-relevant path SHALL make no deploy call and run no smoke check. A changed deploy-relevant path that
the mapping does not cover SHALL select every target.

**Source:** backend-cicd-pipeline · intent.md § AC5; execution-plan.md § Proposed approach (change detection; ADR 0042)

#### Scenario: A docs-only merge
- **WHEN** a merge changes only `README.md` or `apps/web/**`
- **THEN** the run reports "Nothing to deploy", makes no AWS call and runs no smoke (offline:
  `tests/test_ci_deploy_plan.py`; the live check is pending O12 g)

#### Scenario: A chat API handler change
- **WHEN** a merge changes `src/chat_api/handler.py`
- **THEN** only `AiRadarChatApi` is deployed (offline: `tests/test_ci_deploy_plan.py`)

### Requirement: CICD-6 — One pinned deploy context, a schedule guard, and origin validation

The system SHALL pass every CI `cdk` call exactly the four keys of `scripts/ci/deploy_context.json`
(`feed_api_reserved_concurrency=none`, `chat_api_reserved_concurrency=none`, `budget_limit_usd=500`,
`feed_api_allowed_origins`), through the wrapper `python -m scripts.ci.cdk`, which refuses any `-c`. No
`schedule_*` key SHALL exist. After synth, the run SHALL fail before any deploy unless the synthesized
`AiRadarSchedule` `AWS::Scheduler::Schedule` `State` is `DISABLED`.

**Source:** backend-cicd-pipeline · intent.md § AC6; execution-plan.md § Binding constraints (deploy context, schedule guard); ADR 0045

#### Scenario: An enabled schedule
- **WHEN** a commit makes the schedule's `State` `ENABLED`
- **THEN** the guard fails the run before any deploy (offline: `tests/test_ci_schedule_guard.py`)

### Requirement: CICD-7 — The agents are updated in place, from the root Dockerfile

The system SHALL update only the two existing agent runtimes, `ai_radar_curation-FW1w976PCI` and
`ai_radar_chat-JFCO0R9lkT`, with `agentcore deploy -a <agent> --local-build`. It SHALL never run
`configure --create`, `destroy`, or `invoke` on the curation agent, and it SHALL give the chat agent
`--env AGENT_ENTRYPOINT=chat_app.py`. Before each `agentcore deploy`, it SHALL create
`.bedrock_agentcore/<agent>/` beside the rendered config and copy the root `Dockerfile` there unchanged, for
both agents (ADR 0044).

**Source:** backend-cicd-pipeline · intent.md § AC6; execution-plan.md § Binding constraints (agents; Agent Dockerfile placement, audit F1)

#### Scenario: The copy step is missing or late
- **WHEN** the deploy job has no copy step for `ai_radar_chat`, or the copy runs after the deploy
- **THEN** the offline workflow test fails (`tests/test_ci_workflows.py -k dockerfile`, which uses the
  toolkit's own `get_agentcore_directory` path). The audit's reproduction, with the toolkit's path function,
  showed both agents' copies resolve (round 2)

### Requirement: CICD-8 — A smoke check runs after every run that deployed a target

The system SHALL run four probes after every run that deployed at least one target, whatever the target,
and SHALL fail the run if any probe fails: `GET /v1/cards?limit=1` returns 200 with a `cards` list; an
unsigned `POST /v1/chat` returns 403; one signed `POST /v1/chat` returns 200 with `answer` and `sources`
(one retry on 502 or 504 for that probe only); and both agent runtimes report `READY`. A run that deployed
nothing SHALL run no probe. The smoke SHALL never invoke the curation agent.

**Source:** backend-cicd-pipeline · intent.md § AC7; execution-plan.md § Proposed approach (smoke; ADR candidate 0043)

#### Scenario: A plan that only redeploys the budget
- **WHEN** the plan's only target is `AiRadarBudget`
- **THEN** all four probes still run (offline: `tests/test_ci_smoke.py`, `tests/test_ci_workflows.py -k smoke`;
  the live smoke is pending O12 e)

### Requirement: CICD-9 — The smoke uses its own role, which can only call the chat route

The signed probe SHALL authenticate as the smoke role, which is separate from the deploy role. The smoke
role's only route permission SHALL be `execute-api:Invoke` on `POST /v1/chat`. The deploy role SHALL have no
`execute-api:Invoke`. The caller key for `ai-radar-chat-api-caller` SHALL NOT enter GitHub.

**Source:** backend-cicd-pipeline · intent.md § AC8; ADR 0043 (amends ADR 0028)

#### Scenario: The deploy role signs the chat route
- **WHEN** the deploy role signs `POST /v1/chat`
- **THEN** the response is 403 (offline: `tests/test_infra_ci_bootstrap.py -k smoke` and
  `test_deploy_role_cannot_call_the_chat_route`; the live 403 and 200 checks are pending O12 f)

### Requirement: CICD-10 — The CI access is code, deployed once by a human, and never by CI

The GitHub OIDC provider, the diff, deploy and smoke roles, and the two CloudFormation execution policies
SHALL be defined in `infra/ci_bootstrap/`, a CDK app separate from `infra/app.py`, using
`CliCredentialsStackSynthesizer`. A human SHALL deploy it with their own administrator credentials. CI
SHALL NOT deploy it. No CI role SHALL grant `Action: "*"`. Every trust condition SHALL use `StringEquals` on
`aud` and `sub`. No CI role name SHALL start with `AiRadar` or `ai-radar`. The deploy role's only ECR write is
`ecr:CreateRepository`, allowed only on the two agent repositories (`bedrock-agentcore-ai_radar_curation` and
`bedrock-agentcore-ai_radar_chat`), because the locked toolkit's `deploy_to_ecr` always calls
`create_repository`. The grant was found missing by the first live agent deploy (2026-10-28) and added by the
`ci-log-masking` change (AC6). The offline test is `test_deploy_role_may_call_create_repository_only_on_the_two_agent_repositories`,
and the deploy role has no `bedrock-agentcore:ListAgentRuntimes`.

**Source:** backend-cicd-pipeline · intent.md § AC9; execution-plan.md § Binding constraints (the CI access app); ADR 0040

#### Scenario: The synthesized deploy role
- **WHEN** the CI access app is synthesized
- **THEN** the deploy role trusts only `...:ref:refs/heads/main` (offline: `tests/test_infra_ci_bootstrap.py`;
  the human deploy of the stack is pending O12 a)

### Requirement: CICD-11 — Public logs and caches never show the chat id, the URL or a credential

No log, job summary, artifact or cache SHALL show the chat API id or URL, an access key id, a secret, a
session token or an `Authorization` header. No step SHALL echo the environment or enable shell tracing.
Caches SHALL hold only uv and npm dependencies. The deploy job SHALL mask the id and the derived URL from
`secrets.CHAT_API_ID` before any `cdk deploy`, SHALL stop when the secret is empty, and its read of the
deployed chat URL SHALL fail the step on error (no `|| true` and no `2>/dev/null` on that read).

**Source:** backend-cicd-pipeline · intent.md § AC10; execution-plan.md § Binding constraints (public logs; audit F5)

#### Scenario: A throttled stack read in the deploy job
- **WHEN** the read of the chat stack output fails during the deploy job
- **THEN** the mask step fails, and nothing after it runs (offline: `tests/test_ci_workflows.py -k mask_deploy`,
  `tests/test_ci_smoke.py`; the live masked URL check is pending O12 e). The smoke job's own mask step is not
  closed in the same way (CICD-F10)

### Requirement: CICD-12 — CloudFormation executes under two scoped policies that cover every handler permission

The CDK bootstrap's CloudFormation execution policies SHALL be the two customer-managed policies in
`infra/ci_bootstrap/`, `cdk-exec-airadar` (4,480 characters, whitespace removed, intrinsics resolved) and
`cdk-exec-airadar-2` (3,264 characters). Each SHALL be under the 6,144-character managed-policy limit, and
both SHALL be named outside `AiRadar*`. Across them:
- every handler permission, from the committed CloudFormation schema snapshot, of every resource type in the
  seven synthesized stacks is either allowed or listed in a committed omission list with a reason;
- every resource's physical name, or its `<StackName>-<LogicalId>-…` generated name, matches the `Resource`
  patterns of the statements that grant its type's actions (API Gateway v2 is exempt, and the test lists it);
- `secretsmanager:GetSecretValue` is allowed only on `secret:ai-radar/tavily-api-key-*`;
- the DynamoDB item actions are allowed only on the `ai-radar-cards` table and its `feed-by-score` index;
- `dynamodb:DeleteTable` and `DeleteTableReplica` are not allowed, and the explicit deny on `ai-radar-cards` stays;
- `iam:CreateServiceLinkedRole` is not allowed;
- no statement grants `"*"`, and IAM writes are only on `role/AiRadar*`, `policy/AiRadar*` and `user/ai-radar-chat-api-caller`;
- explicit denies cover the CI roles, the OIDC provider, the `cdk-hnb659fds-*` roles, and both execution policies.

**Source:** backend-cicd-pipeline · intent.md § AC13 (with the human's 2026-10-28 decisions); execution-plan.md § Binding constraints (scoped execution policy; handler completeness; resource coverage); ADR 0046

#### Scenario: A new resource type that nothing covers
- **WHEN** a stack adds an `AWS::S3::Bucket`
- **THEN** the coverage test fails in the PR, before any deploy (offline: `tests/test_infra_ci_cfn_exec_policy.py -k coverage`)

#### Scenario: A Lambda outside the AI Radar names
- **WHEN** a Lambda is named `other-fn`
- **THEN** the resource-coverage test fails (offline: `-k resource_coverage`, with the fixture)

#### Scenario: Offline proof, live proof pending
- **WHEN** the audit recomputed the coverage and the sizes (round 2), and compared the snapshot with the public schema
- **THEN** every handler permission was covered or omitted with a reason, the sizes were 4,480 and 3,264, and the
  snapshot matched the schema with zero mismatches. The live re-bootstrap, the seven-stack `cdk diff` with no
  differences, and the first real deploy under the policies are pending O12 b, e and h.
  Rollback is a re-bootstrap with `arn:aws:iam::aws:policy/AdministratorAccess`, which replaces both policies

### Requirement: CICD-13 — Repository protection is a dry-run script that a human applies

A committed script SHALL print the intended `gh api` calls for the repository settings, by default with no
write call. Only `--apply` SHALL write, and only what differs from the state read first, so a re-run changes
nothing. The script SHALL set a ruleset on `main`: a pull request is required with 0 approvals and code-owner
review off, the AC1 check jobs are required with the branch up to date, `non_fast_forward` and `deletion` are
blocked, and there are no bypass actors. It SHALL also set secret scanning and push protection, a read-only
default workflow token, and an approval requirement for outside contributors' workflow runs. The required
check names SHALL equal the workflow job names.

**Source:** backend-cicd-pipeline · intent.md § AC14; execution-plan.md § Binding constraints (repository protection); ADR 0047

#### Scenario: A dry run and a re-run
- **WHEN** the script runs without `--apply`, or with `--apply` a second time
- **THEN** the dry run makes no write call, and the second apply writes nothing (offline:
  `tests/test_ci_repo_protection.py` with an injected runner; the live apply and read-back are pending O12 c)

### Requirement: CICD-14 — The feed API's CORS origins come from the committed context and are validated

The committed `feed_api_allowed_origins` SHALL equal the CORS origins of the synthesized `AiRadarFeedApi`. Each
origin SHALL be `http://localhost:<port>` or an `https://` URL with a host and no path. Placeholder-shaped
values SHALL be rejected, so a placeholder can never be deployed. The value is `http://localhost:3000` today,
which is the live value. The Vercel origin is added by a PR when the project exists (open item CICD-VERCEL).

**Source:** backend-cicd-pipeline · intent.md § AC15; execution-plan.md § Binding constraints (origin validation); ADR 0045; feed-api FA-6

#### Scenario: A placeholder origin
- **WHEN** the context holds `https://<project>.vercel.app`
- **THEN** the origin validation fails the PR (offline: `tests/test_ci_deploy_context.py -k origin`; the live
  preflight from the real Vercel origin is pending O12 i)

### Requirement: CICD-15 — Public-repository hardening in the repository

`.github/CODEOWNERS` SHALL request the maintainer's review for the workflows, itself, the CI helpers,
`infra/ci_bootstrap/` and the deploy context file. Every job SHALL set `timeout-minutes`. The workflow default
`permissions` SHALL be `contents: read`, and only the diff job SHALL have `id-token: write`. The workflows
SHALL reference no `secrets.*` other than `GITHUB_TOKEN`, `CHAT_API_ID` and `AWS_ACCOUNT_ID` (the allow-list of
ADR 0048; the reusable checks workflow references no secret, and `secrets: inherit` is forbidden). While there is one maintainer, CODEOWNERS only
requests review and does not enforce it (CICD-SOLO).

**Source:** backend-cicd-pipeline · intent.md § AC16; execution-plan.md § Binding constraints (public repository); ci-log-masking intent.md § AC4 (the allow-list, which replaces the earlier "no `secrets.*` other than `GITHUB_TOKEN`"; ADR 0048)

#### Scenario: A PR that edits the deploy workflow
- **WHEN** a PR edits `.github/workflows/backend-deploy.yml`
- **THEN** the maintainer is requested as code owner (offline: `tests/test_ci_workflows.py -k hardening`, and
  the CODEOWNERS file's content)

### Requirement: CICD-16 — The compatibility guarantees hold

The seven stacks SHALL synthesize the same templates as before this feature. `harny-feedback.yml` and
`harny-feedback-apps-web.yml` SHALL NOT change. No README shell block SHALL have a comment line inside a
backslash-continued command. CI SHALL never read or write the local, gitignored `.bedrock_agentcore.yaml`.
`run_chat_api_smoke.py` SHALL keep its default behavior (exit 0 after printing); its exit-code options are
opt-in.

**Source:** backend-cicd-pipeline · intent.md § AC12; execution-plan.md § Validation AC12

#### Scenario: The templates and the workflows are unchanged
- **WHEN** the feature is audited
- **THEN** the template comparison is identical, `git diff` of `infra/lib`, `infra/stacks` and `infra/app.py` is
  empty, and `tests/test_readme_runbooks.py` passes (verified by the auditor, round 2)

## Invariants

1. No workflow uses `pull_request_target`, and only the diff job on a same-repo pull request can mint an OIDC token.
2. The deploy role holds no `execute-api:Invoke`. The smoke role holds only that route, plus the reads it needs.
3. CI never deploys the CI access app, never runs `destroy`, `configure --create` or a curation `invoke`, and
   never enables `AiRadarSchedule` (`scheduling` SC-1).
4. The required check names in the ruleset equal the workflow job names. A test compares them.
6. No workflow references a `vars.*` context for the five retired names (`AWS_DIFF_ROLE_ARN`,
   `AWS_DEPLOY_ROLE_ARN`, `AWS_SMOKE_ROLE_ARN`, `AWS_ACCOUNT_ID`, `CHAT_API_ID`). The chat API id and the
   account id reach steps only through `secrets.CHAT_API_ID` and `secrets.AWS_ACCOUNT_ID` (ADR 0048). Offline
   test: `test_no_workflow_references_the_retired_repository_variables`, `test_ids_reach_steps_only_through_secrets`.
7. Each role ARN is `arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/<name>`, and each `<name>` equals the
   stack constant (`gha-airadar-diff`, `gha-airadar-deploy`, `gha-airadar-smoke`). The role names are literal in
   the workflows (they are not secret). Offline test: `test_role_arns_are_built_from_the_secret_account_and_the_stack_role_names`.
5. The two execution policies together deny changes to the CI roles, the OIDC provider, the `cdk-hnb659fds-*`
   roles and both policies.

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| CICD-F8 | The live O12 steps (a)–(i) have not run. Nothing is deployed, no PR diff has been shown, the first deploy has not run, the protection script has not been applied, and the signed-probe checks have not run. This is expected, because the steps are human-only. | LOW | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, F8) |
| CICD-F10 | The smoke job's mask step still reads `ChatApiUrl` with `2>/dev/null \|\| true`. No leak path was found: the step prints nothing itself, and `scripts/ci/smoke.py` emits `::add-mask::` for the URL and the id from its own stack read before it prints, and raises if that read fails. This is inconsistent with the deploy job, which fails closed (CICD-11). | LOW | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, F10) |
| CICD-F11 | The README described `CHAT_API_ID` as used only to mask PR logs, but the deploy job requires it. README corrected 2026-10-28. The residual risk is that a stale value after a chat API id change leaves the new URL unmasked in the deploy log. Accepted as-is by the human. | LOW | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, F11) |
| CICD-F12 | Some grants are on `*` without need: `logs:PutResourcePolicy` and `logs:DeleteResourcePolicy` (account-level writes that only a LogGroup resource policy uses, and no template sets one), and `billing:GetBillingViewData` (used only with a `BillingViewArn`, which the budget does not set). The others on `*` have no resource-level support. Accepted as-is. | LOW | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, F12) |
| CICD-F13 | (a) The omission patterns are global wildcards (`s3:*`, `ec2:*`, `kms:*`, `iam:*Group*`), not tied to a resource type. Any new type must first enter the reviewed snapshot, which limits the exposure. (b) The resource-coverage rule checks one primary action per type, so narrower secondary statements (the DynamoDB item actions, `GetSecretValue`) are not checked against new resources. Accepted; the audit recommends keying omissions by type. | LOW | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, F13) |
| CICD-F14 | The `AWS::IAM::User` read and delete handlers may call `iam:ListGroupsForUser` and `iam:GetLoginProfile`, which the `iam:*Group*` and `iam:*LoginProfile` omissions drop. An update, drift check or delete of `ai-radar-chat-api-caller` could then fail with `AccessDenied`. That is recoverable, and the user changes rarely. Watched in O12 h. Accepted as-is. | LOW | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, F14) |
| CICD-F15 | `tasks.md` is stale: the Finding responses row "Red test bug (O3)" still says "11 passed, 1 failed", and O12(a) names three role ARNs where the runbook needs five repository variables. The archived `tasks.md` is not edited. Accepted as-is. | LOW | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, F15) |
| CICD-ESC | Accepted escalation path. A merged template can still create an `AiRadar*` role with an arbitrary inline policy and trust (`iam:PutRolePolicy`, `iam:UpdateAssumeRolePolicy`, `iam:PassRole` on `role/AiRadar*`) and attach it to a Lambda or a schedule. The controls are the ruleset, `CODEOWNERS` and the PR diff. A permissions boundary is the recorded follow-up. | LOW (accepted) | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, privilege review); ADR 0046; README risk register |
| CICD-VERCEL | The Vercel origin is not in the context file. Until the human creates the project and adds the origin by PR, the committed origin is `http://localhost:3000` only. Open item, not a blocker. | LOW (open) | `specs/archived/backend-cicd-pipeline/intent.md` § Open questions; AC15 |
| CICD-SOLO | Required approvals are 0 and code-owner review is off while there is one maintainer, because GitHub does not let an author approve their own PR. The intent lists this for confirmation, and the audit records no confirmation. Raise both when a second maintainer joins. | LOW (open) | `specs/archived/backend-cicd-pipeline/intent.md` § Open questions; ADR 0047 |
| CICD-LEAK | Live leak in the first run (2026-10-28): the chat API id (in the `deploy` and PR `diff` job logs, through the mask step's `env` block) and the account id (the `role-to-assume` input in the `diff`, `deploy` and `smoke` jobs) were printed into public Actions logs. The workflows now read both only from repository secrets, `CHAT_API_ID` and `AWS_ACCOUNT_ID` (ADR 0048). The fix is implemented and audit-approved, but it is **not committed, merged or run on GitHub**, so this stays open until the live steps pass: O4 (a zero-count grep of the new `diff`, `deploy` and `smoke` logs) and O6 (the two leaked runs' logs deleted for every attempt; those runs must not be re-run). Both are human-only and not yet run. | LOW (open until O4 and O6) | `specs/archived/ci-log-masking/audit.md` (round 1); `specs/archived/ci-log-masking/tasks.md` O3–O6 |
| CLM-F2 | The allow-list test matches only the dotted `secrets.NAME` form. `${{ secrets['NAME'] }}`, `${{ toJSON(secrets) }}` and `secrets[` would not be flagged. The workflows use only the dotted form today. Accepted as-is by the human. | LOW (accepted) | `specs/archived/ci-log-masking/audit.md` (round 1, F2) |
| CLM-F3 | The AC6 test pins the `ecr:CreateRepository` scope but does not assert that the deploy role lacks `bedrock-agentcore:ListAgentRuntimes`. The audit's grep shows it is absent. Accepted as-is by the human. | LOW (accepted) | `specs/archived/ci-log-masking/audit.md` (round 1, F3) |
| CLM-F4 | The live AC5 check (O4 grep, expect 0 per job and value) and the O6 deletion of the leaked logs for every attempt have not run. Expected, because they are human-only. Accepted as pending by the human. | LOW (open, pending) | `specs/archived/ci-log-masking/audit.md` (round 1, F4) |

Notes:
- Round 1 findings F1–F6 and F9 were closed in round 2. F7 (actionlint over all five workflows with
  shellcheck) is closed on reused evidence: actionlint 1.7.12 and shellcheck 0.11.0 exited 0, recorded in
  `tasks.md` O19. The auditor did not re-run it, because the binary download was blocked in that session.
- The auditor's recommendations, which are not reservations and are not adopted: `allowed-account-ids` on
  `configure-aws-credentials` as a second account guard; Dependabot for the `github-actions` ecosystem.
- The live tiers (lint on a PR, the diff, the deploy, the smoke, the protection read-back) are recorded as
  human-only in the execution plan's Validation table and in `tasks.md` O12. The audit did not run them.

Observation (open note, not a reservation): `mypy` and `ruff` write `.mypy_cache` and `.ruff_cache` into the
repository root, which is also the Lambda image build context, and `.dockerignore` does not exclude them. An
image hash can therefore change between two synths of the same code. The `ci-log-masking` audit saw this once:
`tests/test_infra_chat_api.py::test_allowed_origins_context_key_is_ignored` failed in a full run while `mypy`
and `ruff` ran at the same time, and passed on its own and on the clean rerun (835 passed). This is the
CAAUTH-F3 class. It can make the infra synth tests flaky, and it is a risk for CI runs that share a workspace.
The `.dockerignore` speedup is deferred, so the cache is not excluded yet.

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| backend-cicd-pipeline | 2026-10-28 | CICD-1..CICD-16: the PR checks (pytest, ruff, mypy, actionlint, `cdk synth`); the same-repo read-only diff; the OIDC deploy from `main` with an account guard; the change-aware, ordered, one-at-a-time deploy; the pinned context and schedule guard; the agent deploy from the root `Dockerfile`; the four-probe smoke; the CI access app with the two scoped execution policies; the protection script; `CODEOWNERS`; public-repository hardening. Implemented and audit-approved with reservations. **Not live**: the O12 a–i human steps have not run. Also amends `chat-api-auth` (CAAUTH-10, ADR 0043), `runtime-deployment` (RD-9), `scheduling` (SC-5) and `feed-api` (FA-6). |
| ci-log-masking | 2026-10-28 | CICD-11 and CICD-15 amended, invariants 6 and 7, the ECR grant in CICD-10. The chat API id and the account id move from repository variables to repository secrets (`CHAT_API_ID`, `AWS_ACCOUNT_ID`), role ARNs are built from the secret account id plus the fixed role names, and the secrets allow-list is `GITHUB_TOKEN`, `CHAT_API_ID`, `AWS_ACCOUNT_ID` (ADR 0048, amends ADR 0040). Implemented and audit-approved with reservations. **Not yet run on GitHub**: the fix is not committed or merged; O4 and O6 are pending (CICD-LEAK). |

## Related ADRs

| ADR | Title | Status |
|---|---|---|
| [0040](../archived/backend-cicd-pipeline/decisions/0040-github-oidc-with-three-least-privilege-ci-roles-outside-the-stacks.md) | CI authenticates with GitHub OIDC through three least-privilege roles, defined outside the deployed stacks | Accepted |
| [0042](../archived/backend-cicd-pipeline/decisions/0042-deploy-targets-from-changes-since-the-last-successful-deploy.md) | Deploy targets come from the changes since the last successful deploy, not from the parent commit | Accepted |
| [0045](../archived/backend-cicd-pipeline/decisions/0045-one-committed-deploy-context-and-a-schedule-guard-that-fails-the-run.md) | The deploy context is one committed file, and a guard fails the run if the schedule is enabled | Accepted |
| [0046](../archived/backend-cicd-pipeline/decisions/0046-cloudformation-execution-scoped-to-the-ai-radar-resources.md) | CloudFormation executes under two scoped customer-managed policies, not AdministratorAccess | Accepted |
| [0047](../archived/backend-cicd-pipeline/decisions/0047-repository-protection-as-a-rerunnable-script-that-dry-runs-by-default.md) | Repository protection is applied by a rerunnable script that dry-runs by default | Accepted |
| [0048](../archived/ci-log-masking/decisions/0048-ci-identifiers-are-repository-secrets-so-logs-mask-them.md) | The chat API id and the account id are repository secrets, so GitHub masks them in every log line (amends ADR 0040) | Accepted |

ADR 0041 (PR diff) was not promoted: the seven-per-feature cap of `harny-adr` was reached. Its rules (the
same-repo guard, `--method=template`, and no `pull_request_target`) are the requirements CICD-2 and invariant 1.

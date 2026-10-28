# Intent: Backend CI/CD Pipeline

Shipped: 2026-10-28 (implemented and audit-approved; live O12 steps pending)

Revision: 3
Approval: Approved revision 2 by the human on 2026-10-27; revision 3 amends AC5/AC6 (agent Dockerfile placement) and AC13 (execution policy split, actions and resource coverage), plus test-pinnable wording in AC10 and AC12, per the human's 2026-10-28 approval of the audit-fix path; the human also approved on 2026-10-28 the four AC13 decisions (handler snapshot approach, `GetSecretValue` scoped to the Tavily secret, `DeleteTable` deny kept with the replica conflict omitted, item actions on the card table and its index only)

## Outcome
Every pull request against the Python/AWS backend is checked automatically (tests, lint,
types, CDK synth, and a read-only `cdk diff` shown in the run), and every merge to `main`
that passes those checks deploys only the backend parts it changed: the seven CDK stacks,
the two AgentCore agents, and the two Lambda images. There is no manual approval gate, so
safety comes from required PR checks enforced by a repository ruleset, one-deploy-at-a-time
concurrency, change-awareness that never drops a change, guards that keep the curation
schedule `DISABLED`, a CloudFormation execution role scoped to the AI Radar resources instead
of `AdministratorAccess`, and a post-deploy smoke check that fails the run when the live
system breaks. AWS access uses GitHub OIDC roles only. No long-lived AWS key is stored in
GitHub. The repository is public, so every control is designed to hold when the workflows,
role names and account id are world-readable.

## Acceptance criteria
- **AC1** (PR checks) Every pull request runs `pytest`, `ruff`, `mypy`, `actionlint` and
  `cdk synth` of all seven stacks, with the pinned deploy context (AC6). Any failure fails the
  check. The checks need no AWS credentials.
  Example: a PR that breaks a test in `tests/test_infra_chat_api.py` -> the check fails, and the ruleset (AC14) blocks the merge.
- **AC2** (PR diff) A pull request from a branch of `Danii2020/ai-radar` also gets a
  `cdk diff` of all seven stacks against the live account, written to the run's job summary.
  It uses the read-only CDK lookup role and template comparison, so it creates no change set
  and has no write permission. A pull request from a fork gets no AWS credentials. Its diff job
  is skipped, and the summary says why. No workflow uses `pull_request_target`.
  Example: same-repo PR changing `infra/lib/chat_api.py` -> summary shows the `AiRadarChatApi` resource diff; fork PR -> "diff skipped: fork PRs get no AWS credentials".
- **AC3** (deploy trigger and auth) A push to `main` runs the same checks as AC1, and the deploy
  starts only when they pass, with no approval step. The deploy authenticates through GitHub OIDC
  to a role whose trust policy accepts only `repo:Danii2020/ai-radar:ref:refs/heads/main` with
  audience `sts.amazonaws.com`, in account `626259825216`, region `us-east-1`. Before any
  deploy action, the run checks that the caller account is `626259825216` and stops otherwise.
  Example: a merge whose checks fail -> no AWS call is made; a workflow on any other branch or a fork -> it cannot assume the deploy role.
- **AC4** (concurrency) At most one deploy run is active at a time, and an in-flight deploy is
  never cancelled. When a queued run is superseded by a newer push, the newer run still deploys
  every change since the last successful deploy, so no change is lost.
  Example: merges B then C while A deploys -> A finishes; B may be dropped from the queue; C deploys the union of B's and C's changes.
- **AC5** (change-awareness) The deploy computes its targets from the files changed since the
  last successful deploy commit, using a committed mapping from paths to targets (the seven
  stacks and the two agents), and deploys them in dependency order. A change that touches no
  deploy-relevant path makes no deploy call and runs no smoke check. A changed deploy-relevant
  path that the mapping does not cover, a missing previous successful deploy, or a previous
  commit that is not an ancestor of `HEAD`, selects every target. A selected agent target is
  deployable from a fresh CI checkout (the Dockerfile placement in AC6).
  Example: a change only to `README.md` or `apps/web/**` -> "nothing to deploy", the run succeeds; a change to `src/chat_api/handler.py` -> only `AiRadarChatApi`; a change to `src/chat/graph.py` -> both agents (one shared image, RD-8), no stack.
- **AC6** (deploy invariants) Every CDK synth, diff and deploy in CI passes exactly the pinned
  context from one committed file: `feed_api_reserved_concurrency=none`,
  `chat_api_reserved_concurrency=none`, `budget_limit_usd=500` and `feed_api_allowed_origins`
  (AC15). It never passes any `schedule_*` context. Before deploying, the run checks the
  synthesized `AiRadarSchedule` template and fails if the schedule state is not `DISABLED`. The
  chat agent is always deployed with `AGENT_ENTRYPOINT=chat_app.py`. Every `agentcore` command
  names its agent with `-a`. CI never runs `agentcore configure --create`, `agentcore destroy` or
  `cdk destroy`, and it updates only the two existing agent runtimes
  (`ai_radar_curation-FW1w976PCI`, `ai_radar_chat-JFCO0R9lkT`), never creating a new one.
  Both agents are built from the repo-root `Dockerfile` (RD-8): before each `agentcore deploy`,
  the deploy job creates `.bedrock_agentcore/<agent>/` next to the rendered
  `.bedrock_agentcore.yaml` and copies the root `Dockerfile` into it, because the locked toolkit's
  `--local-build` path reads the Dockerfile only from that directory when `source_path` is set,
  and that directory is gitignored, so a CI checkout lacks it. This holds for both agents, so any
  plan that selects an agent (AC5) can complete.
  Example: a commit that changes `DEFAULT_ENABLED` to `True` -> the schedule guard fails the run before any deploy; a deploy job without the copy step for `ai_radar_chat` -> the offline workflow test fails.
- **AC7** (post-deploy smoke) After **every** run that deployed at least one target, whichever
  target it was, a smoke check runs four probes and fails the run if any fails:
  `GET /v1/cards?limit=1` on the feed API returns 200 with a `cards` list; an unsigned
  `POST /v1/chat` returns 403; one signed `POST /v1/chat` returns 200 with `answer` and `sources`;
  and both agent runtimes report `READY`. A run that deployed nothing runs no probe. The signed
  probe makes real Bedrock calls (one Titan embed and at most one Sonnet 4.6 turn per run). The
  smoke never invokes the curation agent.
  Example: the chat agent deployed without `AGENT_ENTRYPOINT=chat_app.py` -> the signed probe gets the curation ack instead of `answer` -> the run fails; a run that only redeployed `AiRadarBudget` -> all four probes still run.
- **AC8** (smoke authentication) The signed smoke probe authenticates as a dedicated OIDC smoke
  role, separate from the deploy role, whose only route permission is `execute-api:Invoke` on the
  chat API's `POST /v1/chat`. The `ai-radar-chat-api-caller` access key never enters GitHub.
  Example: the deploy role signs `POST /v1/chat` -> 403; the smoke role -> 200.
- **AC9** (CI access as code) The GitHub OIDC provider, the CI roles (PR diff, deploy, smoke) and
  the scoped CloudFormation execution policy (AC13) are defined as code, outside the seven-stack
  app, and synth-tested offline. A human deploys them with their own administrator credentials,
  outside the CDK deploy role, so the scoped execution policy never needs rights over them. The
  CI workflows never deploy them. No role grants `Action: "*"`, and each trust policy pins the
  audience and the exact subject.
  Example: the synthesized deploy role trusts only `...:ref:refs/heads/main`; the diff role trusts only `...:pull_request` and can assume only the CDK lookup role.
- **AC10** (public logs and caches) No log, job summary, artifact or cache shows the chat API id
  or URL, an access key id, a secret, a session token or an `Authorization` header. No step
  echoes the environment or enables shell tracing. Caches hold only dependencies (uv and npm),
  never credentials or `cdk.out`. The gitleaks scan in `harny-feedback.yml` is unchanged. The
  deploy job, like the PR job, masks the chat API id from the `CHAT_API_ID` repository variable,
  and its read of the deployed chat URL fails the step instead of continuing unmasked (no
  `|| true` or error suppression on that read).
  Example: the deploy step prints the `ChatApiUrl` output -> it appears masked (`***`); the stack read is throttled -> the mask step fails and nothing is deployed after it.
- **AC11** (runbook) The README documents the one-time human bootstrap (CI access stack, CDK
  re-bootstrap with the scoped policy, repository protection), the first live run, what the
  pipeline deploys and in what order, how to read a PR diff, the smoke cost, the rollback
  procedure (revert the merge and let the pipeline redeploy, or deploy a known-good commit by
  hand), how to change the pinned deploy context, and the public-repository risk register.
- **AC12** (compatibility) The seven stacks synthesize the same templates as before this change
  (no resource change from this feature; the pinned origins equal the live ones). `harny-feedback.yml`
  and `harny-feedback-apps-web.yml` are not edited. The existing test suite passes. The human
  runbooks still work (no README bash block has a comment line inside a backslash-continued
  command, which would cut the command short), and the local, gitignored `.bedrock_agentcore.yaml`
  is never read or written by CI. `run_chat_api_smoke.py` keeps its current default behavior (exit 0 after
  printing), and any new exit-code behavior is opt-in.
- **AC13** (scoped CloudFormation execution) Customer-managed IAM policies, defined as code with
  the CI access stack, replace `AdministratorAccess` as the CDK bootstrap's CloudFormation
  execution policies. There may be one or two of them (CloudFormation execution policies are a
  list, and one policy is near IAM's 6,144-character managed-policy limit); each stays under that
  limit. Together they allow only the services and actions the seven stacks' resource types need:
  every permission in the CloudFormation resource handlers' create, read, update and delete lists
  for those types is either allowed, scoped by resource name to the AI Radar names (`AiRadar*` and
  `ai-radar*`) wherever the service supports it, or recorded in a committed omission list with a
  reason. `iam:CreateServiceLinkedRole` is omitted (needed only for cross-region table replicas).
  Three handler permissions are decided (human, 2026-10-28): `secretsmanager:GetSecretValue` is
  allowed on the Tavily secret only (`secret:ai-radar/tavily-api-key-*`), never account-wide or on
  other `ai-radar/*` secrets; the DynamoDB item actions the table handlers list (`Query`, `Scan`,
  `GetItem`, `PutItem`, `UpdateItem`, `DeleteItem`, `BatchWriteItem`) are allowed only on the
  `ai-radar-cards` table ARN and its `feed-by-score` index ARN; and `dynamodb:DeleteTable` stays
  denied on `ai-radar-cards`, so the `AWS::DynamoDB::GlobalTable` update handler's use of it for
  replica removal is recorded in the omission list (the table is `RETAIN` and has no replicas; a
  future replica removal needs a manual step outside CloudFormation's execution role).
  They explicitly deny changes to the CI roles, the OIDC provider, the CDK bootstrap roles and the
  execution policies themselves, and deny deleting the `ai-radar-cards` table. An offline test
  proves that every resource type in the seven synthesized templates has its handler actions
  covered, and that every resource's physical name (or CloudFormation-generated `<StackName>-…`
  name) is matched by the resource patterns of the allow statements granting those actions.
  Re-bootstrapping with the policies is a human-only step with a verification (all seven stacks
  synth and `cdk diff` cleanly, and the first real deploy succeeds) and a documented rollback to
  `AdministratorAccess`.
  Example: a new stack resource of an uncovered type (say `AWS::S3::Bucket`) -> the coverage test fails in the PR, before any deploy; a new Lambda without `FunctionName`, or one named outside `ai-radar-*`/`AiRadar*` -> the resource-coverage test fails; the deploy role attempts to change a CI role through CloudFormation -> `AccessDenied`.
- **AC14** (repository protection) A committed, idempotent script, run only by a human, applies
  the repository settings through the GitHub API, and prints the intended changes without applying
  them unless explicitly told to apply. It sets a ruleset on `main` (pull request required; the
  AC1 check jobs required; branch up to date before merge; no force push; no deletion), enables
  secret scanning and push protection, sets the default workflow token to read-only, and requires
  approval before workflows run for outside contributors' PRs. Re-running it changes nothing. A
  verification step reads the settings back.
  Example: a direct `git push origin main` after the script ran -> rejected; a PR with a failing check -> cannot merge; dry run -> prints the JSON it would send, makes no write call.
- **AC15** (frontend origin) The committed deploy context carries `feed_api_allowed_origins`
  explicitly, so a CI deploy of `AiRadarFeedApi` never reverts a CORS origin. It holds
  `http://localhost:3000` now (the live value) and gets the Vercel origin
  (`https://<project>.vercel.app`) when the human creates the Vercel project. A validation rejects
  any origin that is not `http://localhost:<port>` or an `https://` URL, and any placeholder-shaped
  value, so a placeholder can never be deployed.
  Example: the context holds `https://<project>.vercel.app` -> the check fails in the PR; it holds `https://ai-radar-xyz.vercel.app` -> the next deploy of `AiRadarFeedApi` allows that origin.
- **AC16** (public-repository hardening in the repo) A `CODEOWNERS` file assigns the workflows,
  the CI helpers, the CI access app and the deploy context file to the maintainer. Every workflow
  job has a `timeout-minutes`. The PR workflow's token is read-only, and the only job that can mint
  an OIDC token on a PR is the diff job. The workflows hold no `secrets.*` reference other than
  `GITHUB_TOKEN`.
  Example: a PR that edits `.github/workflows/backend-deploy.yml` -> the maintainer is requested as code owner.

## Scope
**In**
- GitHub Actions workflows for PR checks, PR diff and the main-branch deploy, with pinned
  action versions, uv caching, timeouts and concurrency control.
- `pytest` in CI for the first time (today CI runs only ruff and mypy).
- Change detection from the last successful deploy commit, with a path-to-target mapping.
- CI deploy of the seven CDK stacks, the two AgentCore agents and the two Lambda images.
- A CI-only AgentCore config, rendered in the runner, for `agentcore deploy`.
- The schedule guard, the pinned deploy context, and the origin validation.
- The post-deploy smoke check, including an opt-in exit-code mode for `run_chat_api_smoke.py`.
- The CI access stack as code (OIDC provider, three roles, the scoped CloudFormation execution
  policy), and its synth and coverage tests.
- The repository-protection script (ruleset, secret scanning, push protection, Actions settings)
  and `CODEOWNERS`.
- Offline tests for the workflows, the mapping, the rendered config, the context, the CI access
  stack and the protection script's payloads.
- The README runbook, including rollback, the re-bootstrap and its rollback, and the
  public-repository risk register.

**Out**
- The frontend (`apps/web`); Vercel deploys it. Creating the Vercel project.
- Running any live step: the CI access stack deploy, the CDK re-bootstrap, the protection script,
  the first live pipeline run (human-only, see Constraints).
- Enabling the curation schedule, or any change to the seven stacks' resources.
- Manual approval gates or GitHub environments with required reviewers.
- IAM permissions boundaries on the roles the seven stacks create (it changes every role
  template; recorded as a follow-up risk).
- Migrating from `bedrock-agentcore-starter-toolkit` to the `@aws/agentcore` npm CLI.
- A signed burst tool for the open `CAAUTH-F11` re-check.
- Multi-account or staging environments.

## Constraints
- Account `626259825216`, region `us-east-1`; GitHub repo `Danii2020/ai-radar` (public), branch
  `main` (human decision 1).
- No long-lived AWS keys in GitHub, and no manual approval gate (human decision 2).
- Every live-AWS and live-GitHub-settings step is human-only: the CI access stack deploy, the CDK
  re-bootstrap, the protection script in apply mode, the first PR diff, the first deploy, the
  deploy-role allow-list confirmation, and any rollback drill. No agent runs them (repo convention).
- The CDK re-bootstrap is account-wide: the scoped policy also governs the human's own `cdk deploy`.
- The schedule stays `DISABLED` (`scheduling` SC-1). The pipeline never enables it. A redeploy
  of `AiRadarSchedule` from CI would also turn off a schedule a human enabled outside the pinned
  context. That is intended until the context source says otherwise.
- RD-8 and ADR 0017: one root `Dockerfile`, and the chat agent needs
  `AGENT_ENTRYPOINT=chat_app.py`.
- `agentcore destroy` deletes the CDK-owned execution role. CI must never run it (README teardown
  gotcha).
- CAAUTH-6 and ADR 0030: the caller's key stays only in the web server's environment.
- The account Lambda quota is 10, hence the two `*_reserved_concurrency=none` flags (`CAPI-F11`,
  `FA-R1`).
- `harny-feedback.yml` is generated by harny and must not be hand-edited, so the new checks live
  in new workflow files.
- Plane boundaries (`docs/architecture-principles.md`): CI helpers import neither plane's
  internals.
- The repository is public: workflow files, role names, ARNs and the account id are world-readable.
  None of them is a secret, and no control may rely on their being hidden.
- **Contradiction with current truth, stated on purpose (accepted by the human, 2026-10-27).**
  `chat-api-auth` CAAUTH-5 and ADR 0028 describe one dedicated caller. This feature adds a second
  principal that can call `POST /v1/chat`: the CI smoke role (AC8). It lives outside
  `AiRadarChatApi`, so the CAAUTH-5 statement about what the stack grants stays literally true, but
  the set of principals that can call the route grows from one to two. This amends ADR 0028 and
  needs a new ADR (candidate 0043).

## Open questions
- **Vercel origin.** The real `https://<project>.vercel.app` URL does not exist yet. Until the human
  creates the Vercel project and puts the URL in the context file, the committed value stays
  `http://localhost:3000` only (AC15). Open item, not a blocker.
- **Required approvals while the maintainer is alone.** GitHub does not let an author approve their
  own PR, so a ruleset requiring one approval, or a code-owner review, would block every merge while
  there is one maintainer. The plan sets required approvals to 0 and code-owner review off, keeps
  `CODEOWNERS` for review requests, and raises both when a second maintainer joins. Confirm.

Resolved on 2026-10-27 by the human: Q1 (scope the CloudFormation execution role here: AC13),
Q2 (`main` is not protected today; protection is in scope: AC14), Q3 (the signed probe runs on every
deploy that deploys anything: AC7), Q4 (a second route principal is acceptable: AC8, ADR 0043),
Q5 (the deploy-role allow-list is confirmed on the first human-run deploy, a recorded human-only step).

Resolved on 2026-10-28 by the human (the handler-permission open item of revision 3): the handler
snapshot, omission list and offline coverage test are approved; `secretsmanager:GetSecretValue` is
allowed on the Tavily secret only; the `dynamodb:DeleteTable` deny on `ai-radar-cards` stays and the
replica-removal conflict is an omission with its reason; the item actions are allowed on the card
table and its index only (all in AC13).

## Revision history
- Revision 1 (2026-10-27): first draft.
- Revision 2 (2026-10-27): human answers to Q1–Q5 folded in. New AC13 (scoped CloudFormation
  execution policy and human re-bootstrap), AC14 (repository protection script), AC15
  (`feed_api_allowed_origins` in the pinned context, with a placeholder guard), AC16 (public-repo
  hardening: `CODEOWNERS`, timeouts, read-only PR token). AC7 states that the signed probe runs on
  every deploying run. AC9 now covers the execution policy and a deploy outside the CDK deploy role.
  AC10 adds caches and no-echo rules. AC11 adds the re-bootstrap and the risk register. The
  ADR 0028 amendment is marked accepted. Q1–Q5 removed; two new open items.
- Revision 3 (2026-10-28): audit round 1 fixes approved by the human. AC6 (and AC5 by reference):
  the deploy job copies the root `Dockerfile` to `.bedrock_agentcore/<agent>/Dockerfile` for both
  agents before `agentcore deploy` (audit F1). AC13: one or two execution policies, each under
  6,144 characters; every handler permission allowed or listed with a reason;
  `iam:CreateServiceLinkedRole` omitted; resource-name coverage in the offline test (audit F2, F3).
  AC10: the deploy job masks from `CHAT_API_ID` and fails closed (audit F5). AC12: no comment
  line inside a backslash-continued README command (audit F4). One new open item on handler
  permissions.
- Revision 3, addendum (2026-10-28): the human's four decisions on the handler-permission open item
  recorded in AC13 and the Approval line; the open item closed. No other change.

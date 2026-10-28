# Runbooks

Operational procedures for AI Radar. Overview, live state and gotchas are in the root [`README.md`](../README.md); this file has the step-by-step commands. Every step that writes to AWS runs against the real account, so print the account first and run steps one at a time:

```bash
aws sts get-caller-identity   # expect account 626259825216
```

Run CDK from the **repo root** (`infra/cdk.json` has a repo-root-relative `app`). CI deploys on merge to `main` using `scripts/ci/deploy_context.json`; hand deploys should use the same context (`uv run python -m scripts.ci.cdk ...` adds it) or the next CI deploy reverts them. In a non-interactive shell add `--require-approval never`, after reviewing `cdk diff`.

Evidence for these procedures (dates, run ids, counts) is in [`history.md`](history.md) and the archived specs' `audit.md` files.

## Contents

- [Curation agent](#curation-agent)
- [Daily schedule](#daily-schedule)
- [Observability and budget](#observability-and-budget)
- [Chat agent and embeddings](#chat-agent-and-embeddings)
- [Chat API](#chat-api)
- [Chat API caller key](#chat-api-caller-key)
- [Web app on Vercel](#web-app-on-vercel)
- [CI/CD one-time bootstrap](#cicd-one-time-bootstrap)
- [Moving to another AWS account](#moving-to-another-aws-account)

## Curation agent

Prerequisites: `AiRadarCardStore` deployed (`ai-radar-cards` and the `feed-by-score` index `ACTIVE`), `uv sync --group infra`, a container engine with BuildKit (or the toolkit's default CodeBuild build), and Bedrock access to Haiku 4.5. If the `us.` Haiku profile's member regions differ from us-east-1/us-east-2/us-west-2, update `haiku_regions` in `infra/lib/agent_runtime.py` and its test:

```bash
aws bedrock get-inference-profile \
  --inference-profile-identifier us.anthropic.claude-haiku-4-5-20251001-v1:0
```

Deploy:

```bash
uv run python -m scripts.ci.cdk deploy --exclusively AiRadarRuntimeRole
aws secretsmanager put-secret-value \
  --secret-id ai-radar/tavily-api-key \
  --secret-string "<your-tavily-api-key>"
agentcore configure --create -n ai_radar_curation -e runtime_app.py \
  -er <ExecutionRoleArn> -r us-east-1 -ecr auto --disable-memory --non-interactive
agentcore deploy -a ai_radar_curation
agentcore status -a ai_radar_curation
```

- The secret is seeded with a sentinel until you run `put-secret-value`; the agent treats the sentinel as "no key" and runs RSS-only. The key is never in CDK or the image.
- Point `-er` at the CDK-authored role; never let the toolkit create its own.
- To update an existing agent from a machine without `.bedrock_agentcore.yaml`, run `agentcore configure --create ...` and then `agentcore deploy -a ai_radar_curation --auto-update-on-conflict`; it updates in place and reuses the ECR repo and runtime id.

Smoke test (two steps, because the handler acks immediately):

```bash
agentcore invoke -a ai_radar_curation '{}'
aws dynamodb scan --table-name ai-radar-cards --select COUNT
```

1. The invoke returns `{"status": "accepted", "run_id": "..."}` in about 1 s.
2. About 30-60 s later find the `curation_run_complete` record with the same `run_id` in the runtime log group (from `agentcore status`) and check that the card count rose by one bounded slice (`AI_RADAR_MAX_ITEMS`, default 8). Re-invoking is not a no-op: it picks up the next batch of undiscovered items.

Re-target without a rebuild: `agentcore configure --env KEY=VALUE` for `CARD_TABLE_NAME`, `AWS_REGION`, `AI_RADAR_MAX_ITEMS`, `AI_RADAR_PER_FEED`, `CURATION_TAVILY_*`, `TAVILY_SECRET_NAME`.

Teardown. Edit `.bedrock_agentcore.yaml` first and set `agents.<name>.aws.execution_role: null`, or `agentcore destroy` deletes the CDK-owned role:

```bash
agentcore destroy -a ai_radar_curation --force --delete-ecr-repo
uv run cdk destroy AiRadarRuntimeRole
```

The `ai-radar-cards` table is `RETAIN` and survives both.

## Daily schedule

`AiRadarSchedule` (`infra/lib/curation_schedule.py`) invokes the curation agent through EventBridge Scheduler's `Universal` target: 15-minute flexible window, 3 retries, 2 h max event age, an SQS dead-letter queue. It deploys `DISABLED` (`cron(0 6 * * ? *)`, UTC).

1. After every agent redeploy, write the agent ARN to SSM. Copy it from the `Agent ARN:` line of `agentcore status`; it looks like `arn:aws:bedrock-agentcore:<region>:<account>:runtime/<name>-<suffix>`. Do not paste the execution-role ARN (silent failure, every fire goes to the DLQ):

   ```bash
   aws ssm put-parameter --name /ai-radar/agent-runtime-arn \
     --type String --value "<agentRuntimeArn>" --overwrite
   ```

2. Deploy it inert and confirm:

   ```bash
   uv run python -m scripts.ci.cdk deploy --exclusively AiRadarSchedule
   aws scheduler get-schedule --name <ScheduleName-output> --group-name default \
     --query "{State:State,Expr:ScheduleExpression,Tz:ScheduleExpressionTimezone}"
   ```

3. One-shot live fire (safe way to prove the wire format). Deploy once with a one-time cron a few minutes ahead (UTC, explicit year). This is a hand deploy outside the CI wrapper, because the wrapper refuses `-c` and the CI schedule guard forbids `schedule_*` keys. Redeploy inert afterwards:

   ```bash
   uv run cdk deploy AiRadarSchedule \
     -c schedule_enabled=true \
     -c schedule_expression="cron(<MM> <HH> <DD> <month> ? <YYYY>)"
   ```

   Wait up to 15 minutes, then check the card count, that exactly one `curation_run_complete` record exists in the window, that `AWS/Scheduler` `TargetErrorCount` is zero, and that the DLQ is empty:

   ```bash
   aws logs filter-log-events --log-group-name <RuntimeLogGroup> \
     --start-time <fire-time-epoch-ms> --filter-pattern '"curation_run_complete"'
   aws sqs get-queue-attributes --queue-url <DeadLetterQueueUrl-output> \
     --attribute-names ApproximateNumberOfMessages
   ```

4. Return to inert: `uv run python -m scripts.ci.cdk deploy --exclusively AiRadarSchedule`.

Going live for real (recurring cost: one Haiku-only run per day, capped by `AI_RADAR_MAX_ITEMS`) is a deliberate human decision: `uv run cdk deploy AiRadarSchedule -c schedule_enabled=true`. Pause by redeploying without the flag. The CI deploy guard fails a run unless the synthesized schedule is `DISABLED`, so enabling it permanently needs a spec that changes that guard. The double-fire dedup drill (does a double delivery skip an already-stored URL) has never been run as its own test.

## Observability and budget

Each curation run emits a `RunSummary` (`src/curation/summary.py`) in three places: the `curation_run_complete` log record (a superset of the original fields), one raw-stderr EMF line `curation_run_metrics` that CloudWatch turns into four metrics in `AIRadar/Curation` (`RunsCompleted`, `CardsWritten`, `ItemsFailed`, `EstimatedCostUsd`; no dimensions, about $1.20/month), and the local console. `CURATION_EMIT_METRICS=false` stops the EMF line (only exercised by an offline test).

CloudWatch Logs Insights, last seven runs (metrics enabled):

```sql
fields @timestamp, run_id, discovered, failed, cards_written, estimated_cost_usd
| filter event = "curation_run_metrics"
| sort @timestamp desc
| limit 7
```

This one works even with metrics disabled (the payload is nested under `message`):

```sql
fields @timestamp, @message
| filter @message like /curation_run_complete/
| sort @timestamp desc
| limit 7
```

`AiRadarBudget` is a monthly `COST` budget `ai-radar-monthly-cost` with `ACTUAL` notifications at $50/$100/$250 via SNS email, `IncludeCredit: false` so a credit-covered account does not read about $0. Its code default limit is $250; the account runs `budget_limit_usd=500` (pinned for CI). It is separate from the hand-made "My Monthly Cost Budget" and never touches it.

```bash
uv run python -m scripts.ci.cdk deploy --exclusively AiRadarBudget
aws sns list-subscriptions-by-topic --topic-arn <AlertTopicArn>
aws sns publish --topic-arn <AlertTopicArn> --subject "AI Radar budget test" --message "live-fire check"
```

The email subscription must be confirmed by hand, or Budgets notifications are dropped silently. Teardown: `uv run cdk destroy AiRadarBudget`.

## Chat agent and embeddings

Order matters: the curation role needs the Titan grant before curation can embed, and cards need vectors before the chat agent can retrieve them.

```bash
aws sts get-caller-identity
uv run python -m scripts.ci.cdk deploy --exclusively AiRadarRuntimeRole
agentcore deploy -a ai_radar_curation
uv run run_backfill_embeddings.py
uv run python -m scripts.ci.cdk deploy --exclusively AiRadarChatRuntime
agentcore configure --create -n ai_radar_chat -e chat_app.py \
  -er <ChatExecutionRoleArn> -r us-east-1 -ecr auto --disable-memory --non-interactive
agentcore deploy -a ai_radar_chat --env AGENT_ENTRYPOINT=chat_app.py
```

- `run_backfill_embeddings.py` prints the account and table, then `embedded=N skipped=N failed=N`. It is idempotent: a second run prints `embedded=0`.
- `--env AGENT_ENTRYPOINT=chat_app.py` is mandatory.
- Optional pre-check that Bedrock accepts the Sonnet 4.6 request shape. The explicit `SONNET_MODEL_ID` guards against a local `.env` still pinning Sonnet 4.5:

  ```bash
  SONNET_MODEL_ID=us.anthropic.claude-sonnet-4-6 PYTHONPATH=src uv run python -c "from shared.config import SONNET_MODEL_ID; print('model:', SONNET_MODEL_ID); from shared.chat import answer_question; print(answer_question('ping', [], [({'title':'t','source':'s','summary':'x','url':'u'}, 1.0)]))"
  ```

Verify:

```bash
agentcore invoke -a ai_radar_chat '{"question": "What shipped this week?", "history": []}'
agentcore invoke -a ai_radar_chat '{"question": ""}'
```

Expect an `answer` with `sources` that exist in the table, then `{"error": "invalid_request", "detail": "question_empty"}` with no retrieval or model call.

The agent is stateless: the request is `{question, history}` (caps from `CHAT_MAX_*`; history roles alternate and end with `assistant`), the response is `{answer, sources}` or `{error: "invalid_request" | "upstream_failure"}`. With no retrieval hits it returns a fixed "not in the collected news" message and makes no model call. Each turn writes one text-free `chat_turn` record (`question_chars`, `history_items`, `hits`, `retrieval_ms`, `model_ms`, `outcome`) from logger `bedrock_agentcore.app.chat`; use it to collect p95 retrieval latency against the scale ceiling in the README.

The chat role (`infra/lib/chat_runtime.py`) has exactly seven statements: Sonnet 4.6 invoke, Titan v2 invoke, `dynamodb:Query` on the `feed-by-score` index only, AgentCore logs and ECR pull; no secrets. Teardown: null `aws.execution_role` for the chat agent, then `agentcore destroy -a ai_radar_chat`, then `uv run cdk destroy AiRadarChatRuntime`.

A card whose upsert fails still costs one Titan call (about $0.00002, an auditor estimate) before its vector write fails and is counted in `embed_failed`. Accepted.

## Chat API

`AiRadarChatApi`: API Gateway HTTP API with one route `POST /v1/chat` (`AWS_IAM`, no `$default` route, no CORS), backed by the Docker-image Lambda `ai-radar-chat-api` (arm64, 256 MB, 28 s timeout, `Dockerfile.chat_api`). It validates JSON shape and a 512 KiB cap, makes exactly one `InvokeAgentRuntime` call with a fresh session id (no retries: botocore `total_max_attempts: 1`, connect 3 s, read 22 s), and returns 200 `{answer, sources}`, 400 `invalid_request`, 502 `upstream_failure`, 504 `upstream_timeout` or 500 `internal_error`. Stage throttle is 5 req/s, burst 10 (best-effort; observed about 2x lenient). Unrouted methods and paths return 404 before authorization.

Deploy (Docker must be running; the image is rebuilt and pushed). In `cdk diff` the Api and Route must show as modified, not replaced, so the URL stays the same:

```bash
uv run python -m scripts.ci.cdk diff AiRadarChatApi
uv run python -m scripts.ci.cdk deploy --exclusively AiRadarChatApi
```

Outputs: `ChatApiUrl` (used as `$API_URL` below), `ChatApiFunctionName`, `ChatApiLogGroupName`, `ChatApiCallerUserName`.

Check the image the way the Lambda runs it (offline tests cannot catch a missing dependency-group member):

```bash
docker build --platform linux/arm64 -f Dockerfile.chat_api -t chat-api-check .
docker run --rm --entrypoint python3 -e CHAT_RUNTIME_ARN=<chat-runtime-arn> chat-api-check \
  -c "import chat_api.handler; import boto3; boto3.client('bedrock-agentcore', region_name='us-east-1'); print('ok')"
```

Probes (a real request can cost a Sonnet turn):

| Probe | Expect |
|---|---|
| Unsigned `curl -s -i -X POST "$API_URL/v1/chat" -H 'content-type: application/json' -d '{"question":"hi"}'` | 403 |
| Signed: `CHAT_API_URL="$API_URL" AWS_PROFILE_NAME=ai-radar-chat-caller uv run run_chat_api_smoke.py "What is new in open-weight models?"` | 200 with `answer`, `sources` |
| Same script with `--unsigned` or `--tamper` | 403 |
| Signed by an identity with no `execute-api` permission | 403 |
| `curl -s -i "$API_URL/v1/chat"` (GET) | 404 |
| `OPTIONS /v1/chat` with an `Origin` header | no `access-control-*` header |
| `aws apigatewayv2 get-api --api-id <api-id> --region us-east-1 --query CorsConfiguration` | null |

An unexpected 403 on a signed call: check clock skew first (SigV4 allows about 5 minutes). Not covered live: signed `GET /v1/chat` and `POST /v1/other`, an expired signature, and the no-retry property on a slow turn (covered offline by a socket probe).

Logs: one `chat_api_request` record per request with exactly `event`, `status`, `outcome`, `question_chars`, `history_items`, `duration_ms`, `session_id`. Never question, history, answer or caller IP; the 500 record logs the exception class and frames only.

```bash
aws logs tail /aws/lambda/ai-radar-chat-api --region us-east-1 --filter-pattern chat_api_request --since 15m
```

Risks: every request starts a cold agent microVM (slow first byte); a turn over 22 s returns 504 while the agent may still finish and bill; the budget alert is the cost backstop. Unsigned floods are rejected at the gateway and never reach the Lambda, so a Lambda-pool burst test needs a signed load tool, which does not exist yet. A 40-way unsigned burst before auth returned Lambda 503s with `ConcurrentExecutions` at 10, which is why the shared concurrency pool matters until the quota is raised.

## Chat API caller key

Route access: IAM user `ai-radar-chat-api-caller` (inline `execute-api:Invoke` on `POST /v1/chat`) and the CI smoke role. CloudFormation creates no access key. HTTP APIs have no resource policy, so an administrator can also call the route.

- Create (human): `aws iam create-access-key --user-name ai-radar-chat-api-caller`. Store it only in the web server's environment (`CHAT_API_ACCESS_KEY_ID`, `CHAT_API_SECRET_ACCESS_KEY`), never in the repo, a `NEXT_PUBLIC_` variable or a chat. For local smoke tests put it in a named profile by typing at the prompt, so no secret is on a command line: `aws configure --profile ai-radar-chat-caller`.
- Suspected leak: `aws iam update-access-key --user-name ai-radar-chat-api-caller --access-key-id <id> --status Inactive` immediately.
- Rotate: create the second key (a user holds at most two), switch the server environment, verify a signed 200, set the old key `Inactive`, verify again, then `aws iam delete-access-key`.
- Vercel reserves the names `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, which is why the app uses `CHAT_API_*`.

## Web app on Vercel

Human-only; no agent runs `vercel*`, `cdk deploy` or `cdk destroy`. Not yet done.

1. Import the repository at <https://vercel.com/new>. Set **Root Directory to `apps/web`**. Framework preset Next.js, default build and install commands.
2. Environment variables (Production, and Preview if wanted), all server-only: `FEED_API_BASE_URL` (the `FeedApiUrl` output, also in `apps/web/.env.example`), `CHAT_API_BASE_URL`, `CHAT_API_ACCESS_KEY_ID`, `CHAT_API_SECRET_ACCESS_KEY`. No `NEXT_PUBLIC_` prefix. CLI alternative from `apps/web/`: `vercel link`, `vercel env add <NAME> production`, `vercel --prod`.
3. Browser-check the deployed URL: real cards; a tag chip narrows the feed and the URL becomes `/?tag=<x>`; "Next page" shows different cards; `/?tag=zzz-no-such-tag` renders the no-match state; the chat widget answers with a `[1]` citation.
4. Add the Vercel origin to the feed API CORS allow-list by PR: edit `feed_api_allowed_origins` in `scripts/ci/deploy_context.json` (`http://localhost:3000,https://<project>.vercel.app`; origins must be `http://localhost:<port>` or `https://<host>` with no path). Merge; CI redeploys `AiRadarFeedApi`. Check both halves:

   ```bash
   curl -si -H "Origin: https://<project>.vercel.app" "$FEED_API_URL/v1/cards?limit=1" | grep -i access-control-allow-origin
   curl -si -H "Origin: https://evil.example.com" "$FEED_API_URL/v1/cards?limit=1" | grep -i access-control
   ```

   The first must echo the origin; the second must print nothing.

Teardown: delete the Vercel project and revert the origin list by PR.

## CI/CD one-time bootstrap

Done on 2026-10-28 (CI access stack, both secrets, the protection ruleset, and the first two deploy runs). Keep this section for rebuilding in a new account or repository. Use your own administrator credentials. `<chat-api-id>` is the chat API id (deliberately not written in this repo).

1. Deploy the CI access stack (GitHub OIDC provider, three roles, two scoped CloudFormation execution policies). CI never deploys it. If the account already has a GitHub OIDC provider, delete it first or the deploy fails.

   ```bash
   uv sync --group infra
   uv run cdk deploy --app "python infra/ci_bootstrap/app.py" CiAccess -c chat_api_id=<chat-api-id>
   ```

   Record `ExecutionPolicyArn1` and `ExecutionPolicyArn2`. The workflows build role ARNs from `AWS_ACCOUNT_ID` and the fixed names `gha-airadar-diff`, `gha-airadar-deploy`, `gha-airadar-smoke`.
2. Set two repository **secrets** (not variables, so GitHub masks them in every log line, including `env` blocks; ADR 0048). Read each value from stdin so it stays out of shell history:

   ```bash
   read -rs CHAT_API_ID_VALUE && printf '%s' "$CHAT_API_ID_VALUE" | gh secret set CHAT_API_ID --repo Danii2020/ai-radar && unset CHAT_API_ID_VALUE
   read -rs AWS_ACCOUNT_ID_VALUE && printf '%s' "$AWS_ACCOUNT_ID_VALUE" | gh secret set AWS_ACCOUNT_ID --repo Danii2020/ai-radar && unset AWS_ACCOUNT_ID_VALUE
   gh secret list --repo Danii2020/ai-radar
   ```

   `CHAT_API_ID` is required: the deploy job stops if it is empty. Update it if the chat API id ever changes. The workflows reference no other secret except `GITHUB_TOKEN`.
3. Re-bootstrap CDK with the scoped policies (account-wide; it also governs your own `cdk deploy`), using the CLI version CI pins:

   ```bash
   npx aws-cdk@2.1132.0 bootstrap aws://<account-id>/us-east-1 \
     --cloudformation-execution-policies "<ExecutionPolicyArn1>,<ExecutionPolicyArn2>"
   ```

   An `AccessDenied` in the CloudFormation events names a missing action: add it to `infra/ci_bootstrap/ci_access_stack.py` in a PR and redeploy step 1. Rollback: re-run the bootstrap with `--cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess`, then re-run the failed deploy.
4. Protect the repository (needs `gh` authenticated as an admin). The first command is a dry run; `--apply` writes only what differs:

   ```bash
   uv run python -m scripts.ci.repo_protection
   uv run python -m scripts.ci.repo_protection --apply
   gh api repos/Danii2020/ai-radar/rulesets
   ```

   It sets a `main` ruleset (PR and the three check jobs required, up to date, no force push, no deletion, no bypass), secret scanning and push protection, a read-only default workflow token, and approval before workflows run for outside contributors. Required approvals stay 0 while there is one maintainer; raise them, and code-owner review, when a second joins. Confirm a direct `git push origin main` is rejected.
5. First run: open a same-repo PR (the diff job shows the seven-stack diff), merge it, and read the deploy run: caller-account guard, schedule `DISABLED`, budget limit 500, both agents keep their runtime ids, the chat URL shows as `***`, and the smoke is green. A docs-only merge must report "Nothing to deploy".

**2026-10-28 log leak.** The first live run printed the chat API id and the account id into public Actions logs (through an `env` block and the `role-to-assume` input). The secrets fix the workflows but do not remove old logs. Delete the logs of the leaked runs for every attempt with `gh api -X DELETE repos/Danii2020/ai-radar/actions/runs/<leaked-run-id>/logs`, confirm none can be downloaded, and do not re-run those runs (a re-run uses the workflow from its original commit). After a clean run, delete the five retired repository variables (`AWS_DIFF_ROLE_ARN`, `AWS_DEPLOY_ROLE_ARN`, `AWS_SMOKE_ROLE_ARN`, `AWS_ACCOUNT_ID`, `CHAT_API_ID`) with `gh variable delete <name> --repo Danii2020/ai-radar`. Whether this cleanup is complete is not recorded here; check `gh variable list` and the old runs' logs.

### Public-repository risk register

| Risk | What protects it |
|---|---|
| Workflows, role names, ARNs, account id are world-readable | Nothing relies on hiding them; trust policies pin `aud` and the exact `sub` (`StringEquals`) |
| A fork PR tries to get AWS access | Fork PRs on `pull_request` get no OIDC token; no `pull_request_target`; the diff job's same-repo guard; deploy and smoke roles trust only `refs/heads/main` |
| A non-`main` branch assumes the deploy role | Exact `sub` `repo:Danii2020/ai-radar:ref:refs/heads/main` |
| A PR or workflow edit runs attacker code in PR checks | That code reaches only the diff role, which can only assume the read-only lookup role |
| A merged workflow edit is a privilege path | Ruleset requires a PR and checks; `CODEOWNERS`; the scoped execution policy; CI never deploys the access stack |
| Residual: a merged change creates an `AiRadar*` role with broad permissions | Review of the PR diff; a permissions boundary is a recorded follow-up |
| Logs leak ids, URLs or credentials | Chat API id and account id are secrets (masked); `::add-mask::` for the chat URL; no env dumps or shell tracing |
| Actions minutes and Bedrock cost abuse | Approval for outside contributors' runs; `timeout-minutes` on every job; PR runs cancel when superseded; deploys only on `main` |
| Committed secrets | gitleaks in `harny-feedback.yml`; secret scanning and push protection |
| Caches and artifacts readable by fork runs | Only uv dependency caches; no `cdk.out`, config or credential in a cache or artifact |
| Public chat API with real Bedrock cost | Unsigned calls get 403 at the gateway; throttle 5 req/s; one signed smoke call per deploy; budget alerts |
| An administrator identity can call the route | Accepted limitation `CAAUTH-ADMIN`; the CI smoke role is a second principal on the route (ADR 0043) |

## Moving to another AWS account

1. Change the pinned account literal in `infra/lib/agent_runtime.py` and `infra/lib/feed_api.py` and in `tests/test_infra_agent_runtime.py` and `tests/test_infra_feed_api.py`. Run `cdk diff` and grep it for the old account id.
2. Bootstrap CDK in the new account, then deploy in this order: `AiRadarCardStore`, `AiRadarRuntimeRole`, `AiRadarChatRuntime`, the agents, `AiRadarSchedule`, `AiRadarBudget`, `AiRadarFeedApi`, `AiRadarChatApi` (see the sections above and the CI bootstrap).
3. Move `.bedrock_agentcore.yaml` and `.bedrock_agentcore/` aside and regenerate with `agentcore configure --create`.
4. Seed the Tavily secret by hand. Confirm the budget SNS subscription by hand. Deploy `AiRadarFeedApi` and `AiRadarChatApi` with the `none` reserved-concurrency flags while the Lambda quota is 10, and `AiRadarBudget` with `budget_limit_usd=500`.
5. Update `FEED_API_BASE_URL` and the CORS allow-list for the new URLs, and the `AWS_ACCOUNT_ID` and `CHAT_API_ID` secrets.

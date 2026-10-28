# AI Radar

An AI-news curation feed plus a RAG chatbot, built on Amazon Bedrock AgentCore and LangGraph.

- **Plane A, curation (scheduled):** discover (RSS + Tavily) -> dedup -> summarize and tag (Claude Haiku 4.5) -> rank -> store in DynamoDB -> embed (Titan v2).
- **Plane B, serving (on demand):** a read-only feed API, and a stateless RAG chat agent (Claude Sonnet 4.6) grounded in the stored cards, with `[n]` citations.
- **Web:** a Next.js app (`apps/web/`) that renders the feed and hosts a chat widget.

Design: [`docs/app-design-on-agentcore.md`](docs/app-design-on-agentcore.md). Budget anchor: $500 in AWS credits, so there is no OpenSearch Serverless or default Bedrock Knowledge Base vector store (about $700/month). Retrieval is brute-force cosine over the DynamoDB `embedding` attribute.

If you are an AI coding agent, read [`CLAUDE.md`](CLAUDE.md) and [`docs/architecture-principles.md`](docs/architecture-principles.md) first.

## Architecture

```
                    Plane A (curation)                                   Plane B (serving)

EventBridge Scheduler --> AgentCore Runtime: ai_radar_curation      Browser --> apps/web (Next.js, Vercel)
   (DISABLED by default)    LangGraph StateGraph                        |  server-side fetch      | server route /api/chat
                            discover > dedup > summarize > rank >       v                         v  (SigV4-signs)
                            persist > embed                        API Gateway          API Gateway  POST /v1/chat (AWS_IAM)
                                  |                                GET /v1/cards          |
                                  v                                    |                  v
                          DynamoDB ai-radar-cards  <-------------  Lambda (feed-api)   Lambda (chat-api)
                          GSI feed-by-score                                                 |
                                  ^                                                         v
                                  +------ dynamodb:Query (retriever) ----  AgentCore Runtime: ai_radar_chat
                                                                           LangGraph retrieve > answer
```

Rules that matter when changing code ([`docs/architecture-principles.md`](docs/architecture-principles.md)):

- The planes never import each other. `Card` is the only shared contract. The public HTTP contract is `src/contracts/card.py` (`CardOut`, `FeedResponse`, schema version `v1`), exported to `docs/api/feed-api.v1.schema.json`.
- Orchestration logic stays plain and LangGraph-portable; AgentCore, DynamoDB and Bedrock sit behind `Protocol` seams (`Discoverer`, `CardStore`, `Retriever`).
- No speculative interfaces or domain layers. Add a port only when a second implementation arrives.
- Cost discipline: Haiku for bulk work, Sonnet only for chat, dedup before summarizing.

### Repository layout

| Path | Contents |
|---|---|
| `run_curation.py`, `run_chat.py` | Local entrypoints for each plane |
| `run_backfill_embeddings.py` | Idempotent Titan backfill for cards that have no embedding |
| `run_chat_api_smoke.py` | Sends one SigV4-signed request to the deployed chat API |
| `runtime_app.py`, `chat_app.py` | AgentCore Runtime entrypoints (curation, chat). One root `Dockerfile` builds both; `AGENT_ENTRYPOINT` selects which one runs |
| `export_api_schema.py` | Regenerates `docs/api/feed-api.v1.schema.json` from `src/contracts/` |
| `src/shared/` | Config, Bedrock client, feeds, Titan embeddings, `Card`, in-memory retrieval, `answer_question` / `RagChat` |
| `src/curation/` | Plane A: LangGraph graph and nodes, Tavily, DynamoDB and JSON stores, run summary, EMF metrics, backfill |
| `src/chat/` | Plane B agent logic: request validation and caps, DynamoDB retriever, retrieve-then-answer graph |
| `src/api/`, `src/chat_api/` | Lambda handlers for `GET /v1/cards` and `POST /v1/chat` (own `Dockerfile.feed_api`, `Dockerfile.chat_api`) |
| `src/contracts/` | Versioned Pydantic API contract |
| `infra/` | CDK app (`app.py`, `lib/` constructs, `stacks/`), plus `ci_bootstrap/`, a separate CDK app for CI access that CI never deploys |
| `scripts/ci/` | CI helpers: deploy planner, pinned context, `cdk` wrapper, smoke runner, repo protection |
| `apps/web/` | Next.js 16 / React 19 frontend (`features/feed`, `features/chat`, `app/api/chat`), npm-managed, with its own SDD harness |
| `tests/` | Offline pytest suite |
| `docs/` | Design, research, architecture principles, runbooks, history, API schema |
| `specs/current/` | Current-state spec per capability (index: [`_index.md`](specs/current/_index.md)) |
| `specs/archived/` | Shipped feature specs, audits and ADRs (`decisions/`) |

Per-directory `CLAUDE.md` / `AGENTS.md` files hold module-level rules for `src/*` and `apps/web`.

## Live state

AWS account `626259825216`, `us-east-1`. The backend was redeployed there from scratch on 2026-10-05 (no data migrated). The account id is pinned as a literal in `infra/lib/agent_runtime.py` and `infra/lib/feed_api.py`, and asserted in their tests. To move accounts, change all four files and grep `cdk diff` for the old id; a miss only shows up as `AccessDenied` at runtime.

| Component | Where | State |
|---|---|---|
| Card table | `AiRadarCardStore` (`ai-radar-cards`, `RETAIN`) | Deployed |
| Curation role, Titan grant, Tavily secret | `AiRadarRuntimeRole` | Deployed |
| Curation agent | AgentCore Runtime `ai_radar_curation` | Deployed, `READY`. ARN in SSM `/ai-radar/agent-runtime-arn` |
| Schedule | `AiRadarSchedule` | Deployed **`DISABLED`**. It has never run unattended; every run so far was a manual invoke |
| Budget alerts | `AiRadarBudget` | Deployed, limit $500, alerts at $50 / $100 / $250 by SNS email |
| Feed API | `AiRadarFeedApi` (`GET /v1/cards`) | Deployed. CORS allows `http://localhost:3000` only |
| Chat agent | `AiRadarChatRuntime` + AgentCore Runtime `ai_radar_chat` | Deployed |
| Chat API | `AiRadarChatApi` (`POST /v1/chat`, SigV4, 5 req/s, burst 10) | Deployed. Caller: IAM user `ai-radar-chat-api-caller` |
| Backend CI/CD | `.github/workflows/backend-*.yml`, stack `CiAccess` | Live. Two `backend deploy` runs on `main` succeeded on 2026-10-28; repository secrets and the `main-protection` ruleset exist |
| Web app on Vercel | `apps/web` | **Not deployed.** Runs locally against the real APIs. The Vercel project, the real caller key, and the feed-API CORS origin are human steps |

Open items:

- **Lambda concurrency quota is 10.** `AiRadarFeedApi` and `AiRadarChatApi` must deploy with `feed_api_reserved_concurrency=none` and `chat_api_reserved_concurrency=none` (pinned for CI in `scripts/ci/deploy_context.json`). A quota increase to 1000 (`L-B99A9384`) was requested 2026-10-21; its outcome is not recorded here. Until it lands, a burst on one API can starve the other.
- **No unattended schedule run, and no double-fire dedup drill** has ever been done.
- **Chat latency** has one sample (retrieval 330 ms, model 3.3 s). Revisit brute-force retrieval at about 2,000 embedded cards or p95 retrieval above about 1 s; there were 16 cards at the last measurement. First remedy is an in-process TTL cache (not built), then pgvector or Aurora (design doc section 7).
- **Admin identities can call the chat route.** HTTP APIs have no resource policy; any identity whose own policy allows `execute-api:Invoke` on the route can call it. Fixing that needs a REST API.
- The caller key is long-lived. Rotate or deactivate it per [`docs/runbooks.md`](docs/runbooks.md#chat-api-caller-key).

Evidence behind this table is in [`docs/history.md`](docs/history.md) and the `audit.md` of each spec in `specs/archived/`. Update this table whenever a deploy changes it; `CLAUDE.md` treats it as the source of truth.

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/). Do not use `pip`, `venv` or `requirements.txt`; dependencies live in `pyproject.toml` and `uv.lock`.
- AWS credentials in `~/.aws` for the account above, with Bedrock access to Claude Haiku 4.5, Claude Sonnet 4.6 and Titan Text Embeddings v2 in `us-east-1`. Use cross-region inference profiles (`us.` prefix); bare Anthropic 4.x model ids are not invocable on demand.
- Optional: a [Tavily](https://tavily.com) key for web-search discovery. Without it, discovery is RSS only.
- For infra work: Node.js and the CDK CLI (`npm install -g aws-cdk`), and Docker with BuildKit (the root `Dockerfile` uses `RUN --mount=type=cache`).
- For the frontend: Node.js and npm.

## Local setup and commands

```bash
uv sync                      # create .venv from the lockfile
uv sync --group infra        # also install aws-cdk-lib (for infra work)
cp .env.example .env         # optional: override region, models, tuning
```

| Task | Command |
|---|---|
| Run curation (RSS, plus Tavily if `TAVILY_API_KEY` is set) | `uv run run_curation.py` |
| Re-summarize everything, ignoring the dedup cache | `uv run run_curation.py --force` |
| Chat over curated cards (REPL) | `uv run run_chat.py` |
| Chat over the live DynamoDB cards | `CARD_STORE_BACKEND=dynamo uv run run_chat.py` |
| Embed cards that lack a vector | `uv run run_backfill_embeddings.py` |
| Tests (offline, no AWS) | `uv run pytest tests/` |
| Lint | `uv run ruff check` |
| Type check | `uv run mypy .` |
| Regenerate the API schema | `uv run export_api_schema.py` |

By default (`CARD_STORE_BACKEND=json`) curation writes `.ai_radar_cache/cards.json`, `seen.json` and `embeddings.json` (gitignored) and needs only Bedrock. With `CARD_STORE_BACKEND=dynamo` it uses the real `ai-radar-cards` table, which must be deployed first (`uv run cdk deploy --app "python infra/app.py" AiRadarCardStore`; run `cdk bootstrap` once per account).

On the current `main`, `uv run pytest tests/` passes 835 tests in about 20 s, and ruff and mypy are clean. The suite is fully offline: Bedrock and Tavily are stubbed, DynamoDB runs on moto, CDK is checked by synth-only assertions. Live AWS calls happen only in manual runbook steps. `tests/test_readme_runbooks.py` fails if a `bash` block in `README.md` has a `#` comment line directly after a line ending in `\`, which would silently drop flags.

### Frontend (`apps/web/`)

```bash
cd apps/web
npm install
cp .env.example .env.local   # FEED_API_BASE_URL already points at the deployed feed API
npm run dev                  # http://localhost:3000
```

Other scripts: `npm test` (Vitest), `npm run lint`, `npm run typecheck`, `npm run build`, `npm run test:e2e` (Playwright against a local stub; run `npx playwright install chromium` once), `npm run generate:types` (TypeScript types from `docs/api/feed-api.v1.schema.json`; a test fails if the committed file drifts).

- All backend calls are server-side. Never prefix `FEED_API_BASE_URL` or any `CHAT_API_*` variable with `NEXT_PUBLIC_`.
- The chat widget calls the same-origin `POST /api/chat`, a Node route that SigV4-signs and relays to the chat API. It needs `CHAT_API_BASE_URL`, `CHAT_API_ACCESS_KEY_ID` and `CHAT_API_SECRET_ACCESS_KEY` in `.env.local`. Without them the widget shows an "unavailable" state. Never paste the key into a repo, log or chat.
- Details: [`apps/web/README.md`](apps/web/README.md) and `apps/web/AGENTS.md`.

## Configuration

Environment variables (or `.env`), validated at startup by `pydantic-settings`: a bad value fails at import with an error naming the variable. Full list with comments: [`.env.example`](.env.example); defaults live in `src/shared/config.py`, `src/curation/config.py`, `src/chat/config.py`, `src/api/config.py`.

| Variable | Default | Purpose |
|---|---|---|
| `AWS_REGION` | `us-east-1` | Region |
| `HAIKU_MODEL_ID` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Summarize and tag |
| `SONNET_MODEL_ID` | `us.anthropic.claude-sonnet-4-6` | Chat. Sonnet 4.5 is `LEGACY` in Bedrock |
| `EMBED_MODEL_ID`, `EMBED_DIM` | `amazon.titan-embed-text-v2:0`, `256` | Embeddings |
| `AI_RADAR_MAX_ITEMS`, `AI_RADAR_PER_FEED`, `AI_RADAR_TOP_K` | `8`, `5`, `4` | New items summarized per run, entries per feed, cards per chat turn |
| `AI_RADAR_CACHE_DIR` | `.ai_radar_cache` | Local cache |
| `CARD_STORE_BACKEND`, `CARD_TABLE_NAME` | `json`, `ai-radar-cards` | Storage backend and table |
| `TAVILY_API_KEY` | empty | Local only. The deployed agent reads the key from Secrets Manager (`TAVILY_SECRET_NAME`, default `ai-radar/tavily-api-key`) at invocation time and falls back to RSS if it is missing |
| `CURATION_TAVILY_*` | see `src/curation/config.py` | Seeds, results, recency, domains, depth |
| `CURATION_EMIT_METRICS`, `CURATION_METRIC_NAMESPACE`, `CURATION_TAVILY_CREDIT_PRICE_USD` | `true`, `AIRadar/Curation`, `0.008` | EMF metrics and cost estimate |
| `CHAT_MAX_QUESTION_CHARS`, `CHAT_MAX_HISTORY_TURNS`, `CHAT_MAX_HISTORY_ITEM_CHARS` | `1000`, `10`, `4000` | Chat request caps |
| `FEED_API_DEFAULT_PAGE_SIZE`, `FEED_API_MAX_PAGE_SIZE` | `20`, `100` | Feed pagination |
| `CHAT_RUNTIME_ARN` | required | Set on the chat API Lambda by CDK |
| `AGENT_ENTRYPOINT` | `runtime_app.py` | Which entrypoint the shared image runs (`chat_app.py` for chat) |

The deployed agents read the same keys, so you can re-target an agent without a rebuild with `agentcore configure --env KEY=VALUE`.

CDK context flags (`-c key=value`):

| Flag | Applies to | Note |
|---|---|---|
| `feed_api_reserved_concurrency=none` | `AiRadarFeedApi` | Required while the Lambda quota is 10 |
| `chat_api_reserved_concurrency=none` | `AiRadarChatApi` | Same |
| `budget_limit_usd=500` | `AiRadarBudget` | Code default is 250; a deploy without the flag reverts it |
| `feed_api_allowed_origins=...` | `AiRadarFeedApi` | CORS allow-list, comma-separated |
| `schedule_enabled=true`, `schedule_expression=...`, `schedule_timezone=...` | `AiRadarSchedule` | Opt-in only; deploys `DISABLED` without them |

## Deploy and operate

CI deploys changed backend targets on merge to `main` (next section), so you rarely deploy by hand. Hand deploys must use the same context as CI, or the next CI deploy reverts them. Run CDK from the repo root with the pinned context:

```bash
uv run python -m scripts.ci.cdk deploy --exclusively AiRadarBudget
uv run python -m scripts.ci.cdk diff AiRadarFeedApi
```

Stacks: `AiRadarCardStore`, `AiRadarRuntimeRole`, `AiRadarChatRuntime`, `AiRadarSchedule`, `AiRadarBudget`, `AiRadarFeedApi`, `AiRadarChatApi`.

The two agents are not CloudFormation resources. They are created and updated with the `agentcore` CLI (from the `dev` group, `bedrock-agentcore-starter-toolkit`, deprecated upstream in favor of the `@aws/agentcore` npm CLI but still working; `launch` is now `deploy`):

```bash
agentcore configure --create -n ai_radar_curation -e runtime_app.py \
  -er <ExecutionRoleArn> -r us-east-1 -ecr auto --disable-memory --non-interactive
agentcore deploy -a ai_radar_curation
agentcore invoke -a ai_radar_curation '{}'
```

Step-by-step runbooks (agent deploy, smoke tests, schedule, observability queries, chat agent, chat API auth, Vercel, CI bootstrap) are in [`docs/runbooks.md`](docs/runbooks.md).

### Verified gotchas

- **Always pass `-a <agent>`** to `agentcore deploy`, `invoke`, `status` and `destroy`. Configuring the second agent changes `default_agent` in the gitignored `.bedrock_agentcore.yaml`.
- **`agentcore destroy` deletes the CDK-owned execution role.** It will `iam:DeleteRole` whatever is in `aws.execution_role`. Set that field to `null` in `.bedrock_agentcore.yaml` first; the message "No execution role configured, skipping IAM cleanup" confirms it. The `codebuild.execution_role` is toolkit-owned and safe to delete.
- **The chat agent needs `--env AGENT_ENTRYPOINT=chat_app.py`.** Without it the shared image starts the curation entrypoint.
- **Curation invoke returns an ack, not counts.** `agentcore invoke '{}'` returns `{"status": "accepted", "run_id": ...}` within about 1 s and runs curation in the background; counts appear in a `curation_run_complete` CloudWatch record with the same `run_id`. A second invoke during a run returns `already_running`. The async handler exists because EventBridge Scheduler's universal target has an undocumented ~30 s synchronous timeout, and the old 25-35 s handler caused double runs.
- **EventBridge Scheduler wire format.** `aws_scheduler_targets.Universal` needs the SDK service id `bedrockagentcore`, while the IAM action prefix is `bedrock-agentcore:` (the signing name). Both are correct where they are used (`infra/lib/curation_schedule.py`); do not "harmonize" them. The target input uses PascalCase keys (`AgentRuntimeArn`, `RuntimeSessionId`, `ContentType`, `Payload`) and `Payload` is a plain JSON string, not base64. `cdk synth` cannot catch either.
- **Schedule ARN parameter.** After every agent redeploy, write the agent ARN to SSM `/ai-radar/agent-runtime-arn` from `agentcore status` (the `bedrock-agentcore:...:runtime/...` line). Pasting the execution-role ARN fails silently: deploys succeed and every fire lands in the DLQ.
- **An empty DLQ does not prove a single delivery.** Check `AWS/Scheduler` `TargetErrorCount` for the fire window, and count `curation_run_complete` records.
- **CloudWatch EMF needs a raw stderr line.** `src/curation/metrics.py` writes the JSON document straight to `sys.stderr`, bypassing `logging`, because the AgentCore SDK logger wraps records in a `{"message": "<json string>"}` envelope that breaks EMF parsing. Metrics land in `AIRadar/Curation` (`RunsCompleted`, `CardsWritten`, `ItemsFailed`, `EstimatedCostUsd`).
- **`EstimatedCostUsd` is a signal, not an invoice.** Tavily consumption is not reported by its API, so that part is attempted searches times a configured price.
- **Docker-image Lambdas: build the image and import inside it.** A module missing from a `uv --only-group <name>` group is invisible to pytest when the same package is in the dev `.venv`. Example from `feed-api`: `pydantic-settings` was missing from the `api` group until a built image raised `ModuleNotFoundError`. Check with `docker build --platform linux/arm64 -f Dockerfile.<name> .` and an `import` inside the container. Affects `Dockerfile.feed_api` (`api` group) and `Dockerfile.chat_api` (`chat_api` group).
- **A failed first create leaves a `ROLLBACK_COMPLETE` stack** (seen with `AiRadarFeedApi` on the Lambda quota error). Delete it before retrying.
- **Run CDK from the repo root.** `cd infra && cdk ...` fails because `infra/cdk.json` has a repo-root-relative app path. Non-interactive shells also need `--require-approval never`.
- **`.bedrock_agentcore.yaml` and `.bedrock_agentcore/` are local state** (gitignored). On a new machine or account, regenerate with `agentcore configure --create`.

## CI/CD

| Workflow | Trigger | What it does |
|---|---|---|
| `backend-checks.yml` | called by the two below | `pytest`, `ruff`, `mypy`, `actionlint`, and `cdk synth` of all seven stacks with the pinned context plus a schedule guard. No AWS credentials |
| `backend-pr.yml` | pull request | The checks, then (same-repo PRs only) a read-only `cdk diff` of all seven stacks to the job summary through a lookup-only role. Fork PRs get no AWS credentials |
| `backend-deploy.yml` | push to `main`, or manual `deploy_all` | Checks, plan, deploy, smoke. One fixed concurrency group, never cancelled, no approval gate |
| `harny-feedback.yml`, `harny-feedback-apps-web.yml` | pull request, push | Harness lint and type checks (ruff + mypy; eslint + tsc), gitleaks |

How the deploy works:

- Auth is GitHub OIDC to three least-privilege roles (`gha-airadar-diff`, `gha-airadar-deploy`, `gha-airadar-smoke`). No AWS key is stored in GitHub. CloudFormation runs under two scoped execution policies defined in `infra/ci_bootstrap/`, which CI never deploys.
- It deploys only targets whose files changed since the last successful deploy run (`scripts/ci/deploy_plan.py`), in order: `AiRadarCardStore`, `AiRadarRuntimeRole`, `AiRadarChatRuntime`, agent `ai_radar_curation`, agent `ai_radar_chat`, `AiRadarSchedule`, `AiRadarBudget`, `AiRadarFeedApi`, `AiRadarChatApi`. It stops at the first failure. Docs, `apps/web/**`, `specs/**` and `tests/**` changes deploy nothing.
- Every CDK call goes through `scripts/ci/cdk.py`, which adds the context in `scripts/ci/deploy_context.json` and refuses any `-c`. To change context (for example a CORS origin once Vercel exists), edit that file in a PR. A guard fails the run unless `AiRadarSchedule` synthesizes `DISABLED`.
- The smoke step checks `GET /v1/cards`, an unsigned `POST /v1/chat` (expects 403), one signed `POST /v1/chat` (expects 200; costs one Titan embed and one Sonnet turn), and that both runtimes are `READY`. The curation agent is never invoked.
- `CHAT_API_ID` and `AWS_ACCOUNT_ID` are repository secrets (not variables) so GitHub masks them in logs; ADR 0048.
- `scripts/ci/repo_protection.py` sets the `main` ruleset (PR and the three check jobs required, no force push). Required approvals are 0 while there is one maintainer.
- The repository is public. No control relies on hiding a workflow, role name or account id. Trust policies pin the exact `sub` for `refs/heads/main`.
- Rollback: revert on a branch and merge; the pipeline redeploys the previous state. A flaky smoke (502/504) can be re-run before reverting.

One-time bootstrap steps, the 2026-10-28 log-leak cleanup, and the risk register are in [`docs/runbooks.md`](docs/runbooks.md#cicd-one-time-bootstrap). The capability spec is [`specs/current/ci-cd.md`](specs/current/ci-cd.md).

## Contributing

Work follows a spec-driven workflow (SDD, via [harny](https://github.com/Danii2020/harny)): architect writes specs, test-writer writes red tests, executor implements, auditor verifies, documentation archives. Roles and skills are under `.claude/`; human review gates are `post-specs`, `post-red-tests`, `post-audit`.

- **Two harness roots.** The repo root (`stack: python`) covers the backend: `.sdd/`, `.claude/`, `specs/`, with a Stop hook running ruff and mypy. `apps/web/` (`stack: typescript`) has its own `.sdd/`, `.claude/`, `specs/` and an eslint + tsc hook. Launch `claude` from `apps/web/` for frontend work so its hooks and agents load. When you change a shared role, skill or `run-feedback.mjs` in one root, make the same change in the other.
- **Specs.** Current truth per capability is in `specs/current/` (index: `_index.md`, maintained by `harny-sync`; do not hand-edit). A finished feature moves to `specs/archived/<feature>/` with its intent, plan, audit and `decisions/`. Check the index before proposing something that might contradict a shipped decision.
- **ADRs.** One file per decision at `specs/archived/<feature>/decisions/NNNN-<slug>.md`. Numbers are monotonic across both roots; the next free number is in `specs/current/_index.md`.
- **Branches and PRs.** Branch off `main`; `main` is protected and requires a PR with passing checks. Same-repo PRs get a `cdk diff` in the job summary: read IAM, CORS and Lambda image changes closely. Merging to `main` deploys.
- **Before pushing:** `uv run pytest tests/`, `uv run ruff check`, `uv run mypy .`; in `apps/web`: `npm test`, `npm run lint`, `npm run typecheck`.
- **Style.** Small modules, dataclasses, lazy singleton clients, per-item try/except so one bad item does not kill a run. Structured LLM output uses the Bedrock Converse API with a forced tool call, not JSON-from-prose. Chat uses a prompt-cache point on the stable system prompt. Do not add tests that only restate the implementation (see the `high-value-tests` skill).
- **Secrets.** Never commit keys. The caller key lives only in the web server's environment; Tavily's key lives in Secrets Manager.

## More documentation

| Document | What it covers |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Agent instructions, verified Bedrock facts, conventions |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Component-level architecture (bootstrap draft; prefer this README and CLAUDE.md on conflict) |
| [`docs/runbooks.md`](docs/runbooks.md) | Deploy, smoke-test and operate each component |
| [`docs/history.md`](docs/history.md) | How the project got here, and the live-verification record |
| [`docs/app-design-on-agentcore.md`](docs/app-design-on-agentcore.md) | Original design |
| [`docs/amazon-bedrock-agentcore-research.md`](docs/amazon-bedrock-agentcore-research.md) | AgentCore research notes |
| [`docs/architecture-principles.md`](docs/architecture-principles.md) | Boundary and DDD rules |
| [`docs/api/feed-api.v1.schema.json`](docs/api/feed-api.v1.schema.json) | Feed API contract |
| [`specs/current/_index.md`](specs/current/_index.md) | Capability specs and ADR registry |
| [`CHANGELOG.md`](CHANGELOG.md) | Dated change log linking archived specs |
| [`apps/web/README.md`](apps/web/README.md) | Frontend setup and harness |

Deferred: a real vector store (see the scale ceiling above), AgentCore Memory (chat history is held by the caller), and moving the schedule from `DISABLED` to enabled (a deliberate opt-in, since it starts recurring cost).

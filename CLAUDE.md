# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

**AI Radar** — an AI-news curation feed + RAG chatbot, designed to run on Amazon
Bedrock AgentCore + LangGraph. Two planes:

- **Plane A — Curation pipeline**: discover → dedup → summarize → tag → rank → store (scheduled).
- **Plane B — Serving/chat**: RAG chatbot grounded in the curated content (on demand).

Full design: [`docs/app-design-on-agentcore.md`](docs/app-design-on-agentcore.md).
Research notes: [`docs/amazon-bedrock-agentcore-research.md`](docs/amazon-bedrock-agentcore-research.md).
Budget anchor: **$500 in AWS credits** — avoid OpenSearch Serverless / Bedrock KB
default vector backing (~$700/mo); it would burn the budget in under a month.

## Current state

**Phase 0 spike** (local, no infra) proves both planes end-to-end against **real Bedrock**:

- `uv run run_curation.py` — Plane A loop: RSS discover → dedup → Haiku summarize/tag → ranked console cards.
- `uv run run_chat.py` — Plane B: Titan embeddings + in-memory cosine RAG → Sonnet grounded chat with citations.

Both write to `.ai_radar_cache/` (gitignored): `cards.json`, `seen.json`, `embeddings.json`.

**Account migration (2026-10-05):** the whole backend was redeployed into AWS account
`626259825216` (all six CDK stacks + the agent, smoke-verified). Anything below that says
"still deployed" or cites the old account `536697225154` describes the original
account; the live state is in the "Live state" table of
[`README.md`](README.md), and the move procedure is in
[`docs/runbooks.md`](docs/runbooks.md#moving-to-another-aws-account). The account is pinned as a literal in
`infra/lib/agent_runtime.py` and `infra/lib/feed_api.py` (change both plus their
tests when moving accounts), `AiRadarFeedApi` must be deployed with
`-c feed_api_reserved_concurrency=none` (Lambda quota is 10), and the budget
limit is `-c budget_limit_usd=500`.

**Phase 1 (curation MVP) is complete** — all 6 planned specs shipped:
`curation-graph`, `tavily-discovery`, `dynamodb-card-store`,
`runtime-packaging` (LangGraph pipeline on AgentCore Runtime),
`eventbridge-schedule` (daily `EventBridge Scheduler` trigger, deploys
`DISABLED`), `async-invocation-ack` (entrypoint acks immediately and runs
curation in the background — fixes a real Scheduler-caused duplicate-run
bug), and `run-observability` (per-run `RunSummary` + CloudWatch EMF custom
metrics + a CDK-managed AWS Budget with SNS alerts). All are deploy-verified
and live-fire-verified for real, and as of 2026-08-12 **four** stacks
(`AiRadarCardStore`, `AiRadarRuntimeRole`, `AiRadarSchedule`,
`AiRadarBudget`) are **still deployed** (not torn down), with the agent
running the `run-observability` image. Two operational gaps remain open from
Phase 1 (an unattended daily cadence has never actually run, since the
schedule stays `DISABLED`, and the double-fire dedup drill was never run as
its own test) — see the "Live state" table in [`README.md`](README.md) for
current status (it is the source of truth, not this file) and
[`docs/runbooks.md`](docs/runbooks.md) for exact commands and how to
redeploy/tear down.

Two cross-cutting specs have since shipped on top of Phase 1, both zero-behavior-change
(local only, no redeploy): `rename-spike-to-shared` (`src/spike` → `src/shared`,
`SPIKE_*` → `AI_RADAR_*` env keys) and `pydantic-settings-config` (both config
modules — `shared/config.py` and `curation/config.py` — now load through
`pydantic-settings`, so a bad env-var override fails fast at import with a typed
error naming the variable, instead of a bare `ValueError` or a silently-wrong
value). The deployed agent image still predates both — see the "Live state" table in
[`README.md`](README.md) for what actually needs a rebuild.

**Phase 2 ("web feed") has begun.** Its first spec, `feed-api` (`GET
/v1/cards` via API Gateway HTTP API → Lambda → `dynamodb:Query` on
`feed-by-score`, plus a versioned `CardOut`/`FeedResponse` Pydantic contract
under `src/contracts/`), is implemented, test-verified
(`uv run pytest tests/` → 349 passed), and **deployed** — the
`AiRadarFeedApi` stack was `cdk deploy`'d 2026-09-03 and is live-curl-verified
(pagination, tag filter, validation, and CORS all confirmed against the real
API Gateway URL; AD-6's index-only IAM grant is sufficient, no
`AccessDeniedException`). Spec 02 (`web-feed-ui`, the Next.js frontend) is
implemented and **audit-approved** (locally verified: `apps/web/` build/lint/
typecheck/test all green, 55/55 tests pass, real cards render against the
deployed API, tag chips and pagination work as designed). Vercel deploy and
`feed-api` CORS update are human-only steps (Phase 5, not executor tasks).
See "Live state" and "Verified gotchas" in
[`README.md`](README.md) for current status and the Docker-packaging gotcha
`feed-api` surfaced, and [`docs/history.md`](docs/history.md) for the
live-deploy verification detail.

**Phase 3 ("chatbot") has begun.** Three specs are shipped.
`chat-retrieval` (audit-approved with reservations, round 3, 2026-10-13) adds curation-time
Titan v2 embeddings on the DynamoDB `embedding` attribute, a backfill
(`uv run run_backfill_embeddings.py`), a brute-force `DynamoCardRetriever` in `src/chat/`,
and a `CARD_STORE_BACKEND=dynamo` switch in `run_chat.py`. Its deploy steps ran on
2026-10-18: the Titan grant is live, the curation image is rebuilt, and all 16 live cards
are embedded. `chat-agent-runtime` (audit-approved with reservations, round 3, 2026-10-18;
`uv run pytest tests/` → 487 passed, ruff and mypy clean) runs the RAG chat as a second,
stateless AgentCore Runtime agent: `chat_app.py` takes `{question, history}` and returns
`{answer, sources}`, using Sonnet 4.6, and it is **deployed** as `ai_radar_chat` in the
`AiRadarChatRuntime` stack (runtime `ai_radar_chat-JFCO0R9lkT`). The live AC10 runbook ran
on 2026-10-18 with one latency sample, which is a recorded reservation. `chat-api`
(audit-approved with reservations, round 3, 2026-10-21) is the public edge: API Gateway HTTP
API `POST /v1/chat` → Lambda (`src/chat_api/`, image `Dockerfile.chat_api`), CDK stack
`AiRadarChatApi` (`infra/stacks/chat_api_stack.py`, construct `infra/lib/chat_api.py`). It is
**deployed** at `https://<api-id>.execute-api.us-east-1.amazonaws.com`, and throttled (5 req/s,
burst 10). Since `chat-api-auth` (2026-10-21, live-verified) the route requires AWS SigV4
(`AWS_IAM`) from the dedicated IAM caller `ai-radar-chat-api-caller`, and an unsigned call gets 403.
The API has no CORS configuration, so the web server is the only caller and holds the caller's
key. Deploy with `-c chat_api_reserved_concurrency=none` while the account Lambda quota is 10
(open: F11). The deploy has no allowed-origins option. The web chat UI and its server-side signing
shipped as the `apps/web` specs `web-chat-ui` and `web-chat-ui-polish` (2026-10-24; locally verified, live key check and Vercel deploy pending). See "Live state" in
[`README.md`](README.md) and the chat runbooks in
[`docs/runbooks.md`](docs/runbooks.md).

**Backend CI/CD (`backend-cicd-pipeline`) is implemented, audit-approved with reservations (round 2,
2026-10-28), and live: `gh run list` showed two successful `backend deploy` runs on `main` on
2026-10-28.** Every PR runs pytest, ruff, mypy, actionlint and `cdk synth`
(`.github/workflows/backend-*.yml`), and a same-repo PR also gets a read-only `cdk diff` through a lookup-only
role. A merge to `main` deploys only the changed targets (`scripts/ci/`), through GitHub OIDC roles
(no AWS key in GitHub), and then runs a smoke check. CloudFormation executes under two scoped policies from the
separate CI access app `infra/ci_bootstrap/`, which CI never deploys. The two repository secrets (`CHAT_API_ID`,
`AWS_ACCOUNT_ID`; the role ARNs are built from them, ADR 0048) and the `main-protection` ruleset exist.
Whether the `ci-log-masking` cleanup (deleting the leaked runs' logs, removing the retired repository
variables) is finished is not recorded. The repository is public, so no control relies on hiding a
workflow, role or account id. Overview: "CI/CD" in [`README.md`](README.md); bootstrap runbook: [`docs/runbooks.md`](docs/runbooks.md#cicd-one-time-bootstrap). The `ci-cd` capability
is `specs/current/ci-cd.md`; ADRs 0040, 0042–0047 and 0048 record the decisions.

## SDD harness: two roots

[harny](../harny) is installed twice, once per stack, until harny supports
several stacks in one install:

- **Repo root** (`stack: python`): `.sdd/`, `.claude/`, `specs/`. The Stop hook
  runs ruff + mypy (gated to `.py`/`.pyi`), and CI runs `harny-feedback.yml`.
  Use it for backend work.
- **`apps/web/`** (`stack: typescript`): `apps/web/.sdd/`, `apps/web/.claude/`,
  `apps/web/specs/`. The Stop hook runs eslint + tsc, and CI runs
  `harny-feedback-apps-web.yml`. Use it for frontend work, and **launch `claude` from
  `apps/web/`** so `CLAUDE_PROJECT_DIR` points there and its hooks, agents,
  and skills load.

ADR numbers are monotonic across both roots (used through 0048 as of 2026-10-28, with 0041 never
promoted; check `specs/current/_index.md` for the next free number). When you change
`.sdd/feedback/run-feedback.mjs` or a shared role or skill in one root, make
the same change in the other.

## Package management: uv (not pip)

This project uses [**uv**](https://docs.astral.sh/uv/). Do **not** use `pip`, `venv`,
or `requirements.txt` — dependencies live in `pyproject.toml` + `uv.lock`.

```bash
uv sync                    # create/refresh .venv from the lockfile
uv add <pkg>               # add a dependency (updates pyproject.toml + uv.lock)
uv run <script.py>         # run inside the project env
uv run python -c "..."     # ad-hoc python in the env
```

`pyproject.toml` sets `[tool.uv] package = false` — this is an application using a
`src/` layout, not an installable library. Entrypoints add `src/` to `sys.path`.

## Layout

```
run_chat.py             # Plane B entrypoint (RAG REPL; CARD_STORE_BACKEND=json | dynamo)
run_backfill_embeddings.py  # one-time, idempotent Titan backfill for cards without an embedding
chat_app.py            # Plane B AgentCore Runtime entrypoint (chat agent; AGENT_ENTRYPOINT=chat_app.py)
runtime_app.py          # Plane A AgentCore Runtime entrypoint (curation agent; the Dockerfile default)
pyproject.toml          # deps (uv); uv.lock is the source of truth
Dockerfile.chat_api     # chat API Lambda image (uv --only-group chat_api; copies only src/chat_api/)
src/chat_api/           # Plane B public edge: Lambda behind POST /v1/chat (handler.py, config.py)
src/shared/
  config.py             # region, model IDs, feeds, tuning, cache paths (env-overridable)
  feeds.py              # RSS/Atom discovery → RawItem
  bedrock.py            # shared bedrock-runtime client + Haiku summarize (forced tool call)
  embeddings.py         # Titan v2 embed() + card_text() — shared by both planes
  retrieval.py          # CardIndex: in-memory cosine search (local path, disk-cached)
  chat.py               # answer_question() (stateless Sonnet answer) + RagChat(retriever, k) on top of it
  cards.py              # Card model + rich console rendering
src/curation/backfill.py  # backfill_embeddings(): embeds cards lacking an EMBED_DIM vector
src/chat/               # Plane B: config.py, retriever.py (DynamoCardRetriever), request.py (validate/cap), graph.py (LangGraph retrieve→answer)
docs/                   # design + research + architecture principles
```

## AWS / Bedrock — verified facts

- Region **us-east-1**; credentials in `~/.aws` (account `626259825216` since the 2026-10-05 migration, IAM user `[username]`; the old account was `536697225154`).
  A `.env` can override region/models and is also how deploys will get creds.
- **Use cross-region inference profiles** (`us.` / `global.` prefix), not bare model
  IDs — bare Anthropic 4.x IDs are not on-demand invocable.

| Role | Model ID | Access |
|---|---|---|
| Summarize (Haiku 4.5) | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | ✅ enabled |
| Chat (Sonnet 4.6, current default) | `us.anthropic.claude-sonnet-4-6` | ✅ enabled (the `SONNET_MODEL_ID` default; used by the deployed chat agent) |
| Chat (Sonnet 4.5, legacy) | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | ⚠️ `LEGACY` in Bedrock, no longer the default |
| Embeddings (Titan v2) | `amazon.titan-embed-text-v2:0` | ✅ enabled (256-dim, normalized) |

- Structured LLM output uses the **Converse API with a forced tool call**
  (`toolChoice: {tool: ...}`) — see `bedrock.py`. Prefer this over JSON-from-prose.
- Chat uses a Bedrock **prompt-cache point** on the stable system prompt.
- `bedrock-agentcore-starter-toolkit` (the `agentcore` CLI) is deprecated in favor
  of a new `@aws/agentcore` npm CLI; it still works, but `agentcore launch` is now
  `agentcore deploy`. See the curation agent runbook in `docs/runbooks.md` for the
  current flags and a real gotcha: `agentcore destroy` will delete *any* IAM role
  in its config's `execution_role`, including a CDK-owned one, unless you null
  that field first.
- EventBridge Scheduler has no native target for AgentCore Runtime — CDK's
  `aws_scheduler_targets.Universal` needs the SDK **service id**
  `bedrockagentcore` (not the IAM signing name `bedrock-agentcore:...`, a
  *different* string used for the IAM action), live-fire-verified 2026-08-10.
  See the daily schedule runbook in `docs/runbooks.md` for the full wire
  format and the SSM-parameter ARN gotcha.
- The agent's entrypoint (`runtime_app.py`) is `async def handler` since
  `async-invocation-ack` (2026-08-10, live-fire-verified): it acks in <1s and
  runs curation as a background task, rather than blocking until the pipeline
  finishes. `agentcore invoke '{}'` now returns
  `{"status": "accepted", "run_id": …}`, **not** the run's counts — those now
  land in a `curation_run_complete` CloudWatch log record joined by `run_id`.
  This fixed a real bug: EventBridge Scheduler's `Universal` target has an
  undocumented ~30s synchronous timeout, and the old blocking 25–35s handler
  caused it to double-fire. See the daily schedule runbook's live-fire
  section in `docs/runbooks.md` for the two-step verify flow and the gotcha.
- CloudWatch EMF (custom metrics from log data) requires writing the raw JSON
  document **directly to `sys.stderr`**, bypassing `logging` entirely — the
  AgentCore SDK's logger wraps every record in `{"message": "<json-as-string>"}`,
  which breaks EMF parsing. Live-fire-verified 2026-08-12 (`run-observability`):
  CloudWatch really does extract metrics from a raw stderr line in the
  AgentCore runtime log group. See `src/curation/metrics.py` and the
  "Observability and budget" section in `docs/runbooks.md`.

## Conventions

- **Architecture rules for new specs/features live in
  [`docs/architecture-principles.md`](docs/architecture-principles.md)** —
  strategic-DDD boundaries (planes never import each other; `Card` is the only
  shared contract), explicit triggers before adding domain layers, no
  speculative interfaces. Read it before architecting anything.
- Match the existing lean style: small modules, dataclasses, lazy singleton client,
  per-item try/except so one bad item doesn't kill a run.
- Keep **LangGraph-portable logic separate from infra** — the loop is plain Python now
  so it can move onto AgentCore Runtime later without rewrites.
- Cost discipline: Haiku for bulk, Sonnet only for chat; dedup before summarizing.
- Library/SDK/cloud docs: use the Context7 MCP (see global rules) before relying on memory.
- **Docker-image-Lambda packaging (`uv --only-group <name>`, this repo's AD-1
  pattern, first used by `feed-api`):** a dependency-group membership bug
  (a module only imported inside the container, missing from that group) is
  invisible to `pytest` if the package also happens to be present as a
  main/dev dependency in `.venv` — it only surfaces by actually building the
  image and importing inside it. See the `feed-api` gotcha under "Verified gotchas" in
  README.md before trusting an `--only-group` closure from
  a green test suite alone.

## Deferred (later phases)

Real vector store for RAG (Phase 3 brute-forces the DynamoDB `embedding` attribute;
revisit at ~2,000 embedded cards or p95 retrieval above ~1 s — see README "Live state") ·
AgentCore Memory (STM/LTM) · Next.js feed.

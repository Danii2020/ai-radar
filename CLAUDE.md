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

- `uv run run_spike.py` — Plane A loop: RSS discover → dedup → Haiku summarize/tag → ranked console cards.
- `uv run run_chat.py` — Plane B: Titan embeddings + in-memory cosine RAG → Sonnet grounded chat with citations.

Both write to `.spike_cache/` (gitignored): `cards.json`, `seen.json`, `embeddings.json`.

**Phase 1 (curation MVP)** has since shipped `curation-graph`, `tavily-discovery`,
`dynamodb-card-store`, `runtime-packaging` (LangGraph pipeline on AgentCore
Runtime), `eventbridge-schedule` (daily `EventBridge Scheduler` trigger,
deploys `DISABLED`), and `async-invocation-ack` (entrypoint now acks
immediately and runs curation in the background — fixes a real
Scheduler-caused duplicate-run bug found during `eventbridge-schedule`'s live
fire). All are deploy-verified and live-fire-verified for real, and as of
2026-08-10 the agent + schedule stacks are **still deployed** (not torn down),
running the `async-invocation-ack` image. See the spec table and runbook in
[`README.md`](README.md) for current status, exact commands, and how to
redeploy/tear down — that table is the source of truth, not this file.

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
run_spike.py            # Plane A entrypoint
run_chat.py             # Plane B entrypoint (RAG REPL)
pyproject.toml          # deps (uv); uv.lock is the source of truth
src/spike/
  config.py             # region, model IDs, feeds, tuning, cache paths (env-overridable)
  feeds.py              # RSS/Atom discovery → RawItem
  bedrock.py            # shared bedrock-runtime client + Haiku summarize (forced tool call)
  retrieval.py          # Titan embeddings + CardIndex (cosine search, disk-cached)
  chat.py               # RagChat: retrieve + Sonnet grounded answer + multi-turn history
  cards.py              # Card model + rich console rendering
  pipeline.py           # Plane A orchestration
docs/                   # design + research + architecture principles
```

## AWS / Bedrock — verified facts

- Region **us-east-1**; credentials in `~/.aws` (account `536697225154`, IAM user `daniele`).
  A `.env` can override region/models and is also how deploys will get creds.
- **Use cross-region inference profiles** (`us.` / `global.` prefix), not bare model
  IDs — bare Anthropic 4.x IDs are not on-demand invocable.

| Role | Model ID | Access |
|---|---|---|
| Summarize (Haiku 4.5) | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | ✅ enabled |
| Chat (Sonnet 4.5) | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | ✅ enabled (current default) |
| Chat (Sonnet 4.6, design target) | `us.anthropic.claude-sonnet-4-6` | ❌ not subscribed — enable in Bedrock console, then set `SONNET_MODEL_ID` |
| Embeddings (Titan v2) | `amazon.titan-embed-text-v2:0` | ✅ enabled (256-dim, normalized) |

- Structured LLM output uses the **Converse API with a forced tool call**
  (`toolChoice: {tool: ...}`) — see `bedrock.py`. Prefer this over JSON-from-prose.
- Chat uses a Bedrock **prompt-cache point** on the stable system prompt.
- `bedrock-agentcore-starter-toolkit` (the `agentcore` CLI) is deprecated in favor
  of a new `@aws/agentcore` npm CLI; it still works, but `agentcore launch` is now
  `agentcore deploy`. See the `runtime-packaging` runbook in `README.md` for the
  current flags and a real gotcha: `agentcore destroy` will delete *any* IAM role
  in its config's `execution_role`, including a CDK-owned one, unless you null
  that field first.
- EventBridge Scheduler has no native target for AgentCore Runtime — CDK's
  `aws_scheduler_targets.Universal` needs the SDK **service id**
  `bedrockagentcore` (not the IAM signing name `bedrock-agentcore:...`, a
  *different* string used for the IAM action), live-fire-verified 2026-08-10.
  See the `eventbridge-schedule` runbook in `README.md` for the full wire
  format and the SSM-parameter ARN gotcha.
- The agent's entrypoint (`runtime_app.py`) is `async def handler` since
  `async-invocation-ack` (2026-08-10, live-fire-verified): it acks in <1s and
  runs curation as a background task, rather than blocking until the pipeline
  finishes. `agentcore invoke '{}'` now returns
  `{"status": "accepted", "run_id": …}`, **not** the run's counts — those now
  land in a `curation_run_complete` CloudWatch log record joined by `run_id`.
  This fixed a real bug: EventBridge Scheduler's `Universal` target has an
  undocumented ~30s synchronous timeout, and the old blocking 25–35s handler
  caused it to double-fire. See the `eventbridge-schedule` runbook's live-fire
  section in `README.md` for the two-step verify flow and the gotcha.

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

## Deferred (later phases)

Real vector store for RAG (DynamoDB reserves an `embedding` attribute for it) ·
AgentCore Memory (STM/LTM) · Next.js feed.

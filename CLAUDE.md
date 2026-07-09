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

## Current state: Phase 0 spike (local, no infra)

The spike proves both planes end-to-end against **real Bedrock**, with zero AWS infra:

- `uv run run_spike.py` — Plane A loop: RSS discover → dedup → Haiku summarize/tag → ranked console cards.
- `uv run run_chat.py` — Plane B: Titan embeddings + in-memory cosine RAG → Sonnet grounded chat with citations.

Both write to `.spike_cache/` (gitignored): `cards.json`, `seen.json`, `embeddings.json`.

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
docs/                   # design + research
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

## Conventions

- Match the existing lean style: small modules, dataclasses, lazy singleton client,
  per-item try/except so one bad item doesn't kill a run.
- Keep **LangGraph-portable logic separate from infra** — the loop is plain Python now
  so it can move onto AgentCore Runtime later without rewrites.
- Cost discipline: Haiku for bulk, Sonnet only for chat; dedup before summarizing.
- Library/SDK/cloud docs: use the Context7 MCP (see global rules) before relying on memory.

## Deferred (later phases)

Search API (Tavily/Exa) · LangGraph orchestration on AgentCore Runtime · DynamoDB +
real vector store · AgentCore Memory (STM/LTM) · EventBridge scheduling · Next.js feed.

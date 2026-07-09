# AI Radar

AI-news curation feed + RAG chatbot. See [`docs/app-design-on-agentcore.md`](docs/app-design-on-agentcore.md) for the full design.

## Phase 0 spike (current)

Proves the core curation loop end-to-end with **zero infra**, using real Amazon Bedrock:

```
discover (RSS)  →  dedup  →  summarize + tag (Claude Haiku 4.5)  →  rank  →  print cards
```

This validates summary quality — the thing worth checking before any AWS infra goes up.

### Run it

Uses [uv](https://docs.astral.sh/uv/) as the package manager.

```bash
uv sync                       # create .venv + install from the lockfile
uv run run_spike.py           # curation loop (skips already-seen items)
uv run run_spike.py --force   # re-summarize everything
uv run run_chat.py            # ask questions about the curated cards (RAG)
```

AWS credentials are read from `~/.aws` by default; copy `.env.example` → `.env` only to
override region/models. Requires Bedrock model access to Claude Haiku 4.5, a Sonnet
chat model, and Titan Embeddings v2 in your region.

### What it does

| Step | Where | Notes |
|---|---|---|
| Discover | `src/spike/feeds.py` | Pulls recent entries from curated AI/ML RSS feeds (no API key). |
| Dedup | `src/spike/pipeline.py` | URL-hash cache in `.spike_cache/seen.json` → idempotent re-runs. |
| Summarize + tag | `src/spike/bedrock.py` | Bedrock Converse with a **forced tool call** → guaranteed structured cards. |
| Rank + render | `src/spike/cards.py` | Sort by model relevance score; pretty console panels. |

Output is also written to `.spike_cache/cards.json` for inspection.

### Mini RAG chat (Plane B preview)

`uv run run_chat.py` runs a grounded chatbot over the curated cards:

| Step | Where | Notes |
|---|---|---|
| Embed cards | `src/spike/retrieval.py` | Titan v2 embeddings, cached in `.spike_cache/embeddings.json`. |
| Retrieve | `src/spike/retrieval.py` | In-memory cosine top-k (normalized → dot product). |
| Answer | `src/spike/chat.py` | Sonnet, grounded in retrieved cards, inline `[n]` citations, multi-turn memory. |

It answers only from retrieved cards (no hallucination) and says so when the corpus
lacks the answer. The stable system prompt uses a Bedrock prompt-cache point.

### Deliberately deferred to later phases

- **Search API** (Tavily/Exa) — using free RSS for the spike; swap `feeds.py` for a search tool in Phase 1.
- **LangGraph orchestration** — the loop is plain Python here; becomes a LangGraph graph on AgentCore Runtime.
- **Persistence** — DynamoDB cards + a real vector store; spike uses local JSON.
- **AgentCore Memory** — chat memory is an in-process list; becomes AgentCore Memory (STM/LTM).
- **Scheduling** — EventBridge trigger.

### Config knobs (`.env` or env vars)

`AWS_REGION`, `HAIKU_MODEL_ID`, `SPIKE_MAX_ITEMS`, `SPIKE_PER_FEED` — see `.env.example`.

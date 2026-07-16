# AI Radar

AI-news curation feed + RAG chatbot. See [`docs/app-design-on-agentcore.md`](docs/app-design-on-agentcore.md) for the full design.

## Phase 1 — Curation MVP (in progress)

Refactors the Phase 0 loop into a **LangGraph `StateGraph`** with infra injected
behind Protocols, so discovery and persistence can be swapped without touching
graph/node code. See [`tasks/phase-1-curation-mvp/`](tasks/phase-1-curation-mvp/)
for the full build plan and [`specs/`](specs/) for each shipped spec's contract.

```
discover (RSS + Tavily, composite, deduped)  →  dedup  →  summarize + tag  →  rank  →  persist
```

| Spec | Status | What it added |
|---|---|---|
| [`curation-graph`](specs/curation-graph/) | ✅ Shipped | The `StateGraph` itself (`src/curation/graph.py`), the `Discoverer`/`CardStore` Protocols (`interfaces.py`), and the local JSON-file defaults (`local.py`) — reproduces Phase 0 behavior exactly. |
| [`tavily-discovery`](specs/tavily-discovery/) | ✅ Shipped | `TavilyDiscoverer` (web search) + `CompositeDiscoverer` (RSS + Tavily, cross-source deduped) behind the same `Discoverer` Protocol — no graph/node changes. |
| `dynamodb-card-store` | ⏳ Not started | Swaps `JsonFileCardStore` for DynamoDB persistence + dedup. |
| `runtime-packaging` | ⏳ Not started | Packages the graph for AgentCore Runtime (containerized, cloud-invocable). |
| `eventbridge-schedule` | ⏳ Not started | Daily automated trigger. |
| `run-observability` | ⏳ Not started | Structured run-summary logging. |

### Run it

```bash
uv run run_curation.py            # RSS-only if TAVILY_API_KEY unset, else RSS + Tavily
uv run run_curation.py --force    # re-summarize everything (ignore dedup cache)
```

Discovery source is auto-selected: set `TAVILY_API_KEY` in `.env` (get one at
[tavily.com](https://tavily.com)) to pull from RSS + Tavily web search; leave it
unset to fall back to RSS alone (same behavior as Phase 0). Tuning knobs
(topic seeds, results-per-query, recency, domain filters, per-run cap) are
env-overridable — see `.env.example` and `src/curation/config.py`.

The Tavily key is **local-only** for now (`.env` / env var); Secrets Manager
resolution is deferred to `runtime-packaging`, once real cloud infra exists.

Output still lands in `.spike_cache/cards.json` / `seen.json` (unchanged from
Phase 0 — the `JsonFileCardStore` default reproduces that behavior exactly).

### Tests

```bash
uv run pytest tests/ -v   # 27 tests, all offline (Bedrock + Tavily calls are stubbed)
```

Live API calls (Bedrock + Tavily) only happen via the `uv run run_curation.py`
manual smoke path above — never in the automated suite.

## Phase 0 spike (reference baseline)

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

### Deliberately deferred (superseded by Phase 1 progress above, or still later)

- ~~**Search API** (Tavily/Exa)~~ — done, see `tavily-discovery` above.
- ~~**LangGraph orchestration**~~ — done, see `curation-graph` above.
- **Persistence** — DynamoDB cards + a real vector store; spike/Phase 1 use local JSON (`dynamodb-card-store`, not started).
- **AgentCore Runtime + scheduling** — cloud deployment + EventBridge trigger (`runtime-packaging`, `eventbridge-schedule`, not started).
- **AgentCore Memory** — chat memory is an in-process list; becomes AgentCore Memory (STM/LTM) in a later phase (Plane B, untouched by Phase 1).

### Config knobs (`.env` or env vars)

`AWS_REGION`, `HAIKU_MODEL_ID`, `SPIKE_MAX_ITEMS`, `SPIKE_PER_FEED` — see `.env.example`.

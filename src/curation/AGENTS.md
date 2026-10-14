# src/curation — Plane A curation pipeline

Purpose: the LangGraph `StateGraph` that discovers, dedups, summarizes, ranks and
persists cards (Plane A). Infra is injected behind Protocols so the graph never
imports it. Root guidance: [`CLAUDE.md`](../../CLAUDE.md).

## Key files

- `graph.py` — `build_graph(store, discoverer, embedding_writer=None)`. Nodes
  run `discover -> dedup -> summarize -> rank -> persist`, plus an `embed` node
  after `persist` only when an `embedding_writer` is passed.
- `nodes.py`, `state.py`, `interfaces.py` — node functions, graph state, and the
  `Discoverer` / `CardStore` / `EmbeddingWriter` Protocols.
- `dynamo.py` — `DynamoCardStore`: `upsert` (never writes `embedding`),
  `set_embeddings` / `set_embedding` (conditional `update_item`), and
  `list_unembedded`. The only module here that imports `boto3`.
- `backfill.py` — `backfill_embeddings(store)`, idempotent, returns
  `embedded / skipped / failed`. Driven by `run_backfill_embeddings.py` at the root.
- `local.py`, `tavily.py`, `composite.py` — local JSON store and discovery sources.
- `summary.py`, `metrics.py`, `config.py` — run summary, EMF metrics, settings.

## Commands

```bash
uv run pytest tests/test_embed_step.py tests/test_backfill.py tests/test_dynamo_store.py
uv run pytest tests/           # full offline suite
uv run run_curation.py         # local run against the JSON store
```

## Conventions

- `boto3` is imported only in `dynamo.py` within this package; `nodes.py`,
  `graph.py`, `state.py` and `interfaces.py` stay boto3-free (`tests/test_chat_contract.py`).
- Dedup key is `sha256(url.encode()).hexdigest()[:16]` everywhere.
- Embedding is best-effort: a Titan or write failure is counted, logged and
  never raised, so it cannot fail a run or unpersist a card.
- Existing callers of `build_graph(store, discoverer)` keep working; the writer
  parameter defaults to `None`.

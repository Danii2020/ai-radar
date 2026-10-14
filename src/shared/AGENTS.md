# src/shared — neutral helpers and the Phase 0 chat

Purpose: code both planes use, plus the Phase 0 local RAG chat. Root guidance:
[`CLAUDE.md`](../../CLAUDE.md).

## Key files

- `config.py` — region, model IDs (`HAIKU_MODEL_ID`, `SONNET_MODEL_ID`,
  `EMBED_MODEL_ID`), `EMBED_DIM`, feeds and tuning. pydantic-settings, fail-fast.
  Its `load_dotenv()` is the one `.env` load; `chat/config.py` relies on it.
- `embeddings.py` — `embed(text)` (Titan v2, `dimensions=EMBED_DIM`,
  `normalize=True`) and `card_text(card)`. Used by curation and by chat.
- `bedrock.py` — bedrock-runtime client and the Haiku summarize call (forced tool call).
- `retrieval.py` — `CardIndex`, the in-memory cosine index for the local chat path,
  disk-cached in `.ai_radar_cache/embeddings.json`.
- `chat.py` — `RagChat(retriever, k)` and the `Retriever` Protocol. Sonnet answers
  grounded in retrieved cards with `[n]` citations.
- `feeds.py`, `cards.py` — RSS discovery and the shared `Card` model.

## Commands

```bash
uv run pytest tests/test_rag_chat.py tests/test_config.py
uv run run_chat.py             # local path: cards.json + CardIndex
```

## Conventions

- Nothing here imports `curation`, `api` or `chat`. `chat.py` and `retrieval.py`
  are Plane B by naming only; they live here for the `rename-spike-to-shared` move.
- `embed()` is the only Titan `invoke_model` call site; `retrieval.py` imports it from
  `embeddings.py`. `EMBED_MODEL_ID` is read only from `config.py` and `embeddings.py`.
- Config goes through pydantic-settings with explicit `validation_alias`.

# src/chat — Plane B retrieval over DynamoDB

Purpose: the DynamoDB-backed retriever for the RAG chat (Plane B). It ranks the
curated cards' stored Titan v2 vectors against a question by brute-force cosine
and returns the top-k cards. Root guidance: [`CLAUDE.md`](../../CLAUDE.md).

## Key files

- `retriever.py` — `DynamoCardRetriever(table_name=None, resource=None, embed_fn=embed)`.
  Satisfies the `Retriever` Protocol in `src/shared/chat.py`. Paginates a `Query`
  on the `feed-by-score` index (partition `CARD`), never a `Scan`. Converts
  `Decimal` vectors to `float`, drops un-embedded and wrong-length cards, strips
  the vector from every returned card dict.
- `config.py` — `CARD_TABLE_NAME`, `CARD_STORE_BACKEND` (pydantic-settings,
  `validation_alias` set), plus the fixed `FEED_GSI_NAME` / `FEED_GSI_PARTITION`
  duplicated from `src/curation/config.py`.

## Commands

```bash
uv run pytest tests/test_chat_retriever.py tests/test_chat_contract.py
uv run pytest tests/test_rag_chat.py      # RagChat driven by a retriever
```

## Conventions

- Plane separation: this package imports only `shared` (neutral) and its own
  modules. It must not import `curation` or `api`, and nothing in `curation`,
  `shared` or `api` may import `chat`. `tests/test_chat_contract.py` enforces both.
- `boto3` is confined to `retriever.py` within this package.
- Plane B duplicates Plane A's table/GSI constants and never imports them. The
  equality test in `tests/test_chat_contract.py` keeps them in step.
- Tests run offline: DynamoDB via moto or a table double, Bedrock stubbed.

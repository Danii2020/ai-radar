# src/chat — Plane B retrieval over DynamoDB

Purpose: the chat agent's logic (Plane B). It validates a turn, retrieves the top-k
cards, and runs the LangGraph graph that answers from them. The retriever ranks the
curated cards' stored Titan v2 vectors by brute-force cosine. Root guidance:
[`CLAUDE.md`](../../CLAUDE.md). The entrypoint that serves this code is `chat_app.py`
at the repo root, not in this package.

## Key files

- `request.py` — `parse_request(payload)`, pure. Validates `{question, history}` and applies
  the caps. It returns a frozen `ChatRequest`, or raises `InvalidRequest` with a rule name
  (`question_empty`, `history_roles_not_alternating`, and so on) that never echoes input.
  It runs before any AWS seam is touched.
- `graph.py` — `build_chat_graph(retriever, k)`: a LangGraph `StateGraph` of `retrieve` then
  `answer`. The retriever is a parameter. `build_sources(hits)` numbers the sources in rank
  order (`n, title, url, source, published, score`). With no hits, `answer` returns
  `NO_CONTEXT_ANSWER` and makes no model call. The graph is compiled without a checkpointer.
- `retriever.py` — `DynamoCardRetriever(table_name=None, resource=None, embed_fn=embed)`.
  Satisfies the `Retriever` Protocol in `src/shared/chat.py`. Paginates a `Query`
  on the `feed-by-score` index (partition `CARD`), never a `Scan`. Converts
  `Decimal` vectors to `float`, drops un-embedded and wrong-length cards, strips
  the vector from every returned card dict. Its DynamoDB resource is bound to
  `shared.config.AWS_REGION`.
- `config.py` — `CARD_TABLE_NAME`, `CARD_STORE_BACKEND` (pydantic-settings,
  `validation_alias` set), the request caps `CHAT_MAX_QUESTION_CHARS` (1000),
  `CHAT_MAX_HISTORY_TURNS` (10) and `CHAT_MAX_HISTORY_ITEM_CHARS` (4000), plus the fixed
  `FEED_GSI_NAME` / `FEED_GSI_PARTITION` duplicated from `src/curation/config.py`.

## Commands

```bash
uv run pytest tests/test_chat_request.py tests/test_chat_graph.py tests/test_chat_app.py
uv run pytest tests/test_chat_retriever.py tests/test_chat_contract.py
uv run pytest tests/test_rag_chat.py      # RagChat driven by a retriever
```

## Conventions

- Plane separation: this package imports only `shared` (neutral) and its own
  modules. It must not import `curation` or `api`, and nothing in `curation`,
  `shared` or `api` may import `chat`. `tests/test_chat_contract.py` enforces both.
- `bedrock_agentcore` is imported only by files at the repo root (`chat_app.py`), never in
  this package. `request.py` and `graph.py` build no AWS client, which the contract tests
  check.
- `boto3` is confined to `retriever.py` within this package.
- Each turn is stateless. Prior turns come from the request's `history` and are never kept
  in module state.
- Plane B duplicates Plane A's table/GSI constants and never imports them. The
  equality test in `tests/test_chat_contract.py` keeps them in step.
- Tests run offline: DynamoDB via moto or a table double, Bedrock stubbed.

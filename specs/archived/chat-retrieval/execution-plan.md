# Execution Plan: chat-retrieval

## Guidance consulted
- `CLAUDE.md`, `docs/architecture-principles.md`, `docs/app-design-on-agentcore.md` §5 Plane B and §7 vector-store table.
- `harny-sync` lookup: `specs/current/card-persistence.md` (PS-1..PS-4, invariant 1), `curation-pipeline.md`, `_index.md`.
- Code read: `src/shared/{retrieval,chat,bedrock,config}.py`, `src/curation/{dynamo,nodes,graph,interfaces,state}.py`, `src/api/{config,dynamo,feed}.py`, `infra/lib/{card_store,agent_runtime}.py`, `runtime_app.py`, `run_curation.py`, `run_chat.py`, `Dockerfile`.
- Tests read for conventions: `tests/conftest.py` (moto `dynamo_resource`/`dynamo_table`/`seed_cards`), `test_dynamo_store.py`, `test_feed_api_contract.py` (AST plane-separation + duplicated-constant equality), `test_infra_agent_runtime.py`, `test_runtime_app.py`.
- Archived `rename-spike-to-shared` contract: `shared.retrieval` and `shared.chat` are **Plane B**, living in `shared/` by naming only.

## Ownership
- **New `src/shared/embeddings.py`** (neutral): the Titan `embed()` call and the `card_text()` rule, moved out of `shared/retrieval.py`. Both planes need them, and Plane A must not import Plane B's `shared.retrieval`.
- **Plane A (`src/curation/`)**: `interfaces.py` (new `EmbeddingWriter` Protocol), `nodes.py` (new `embed_node`), `graph.py` (optional `embedding_writer` param), `state.py` (two counters), `dynamo.py` (embedding writer and un-embedded-card listing on `DynamoCardStore`), new `backfill.py`, new root script `run_backfill_embeddings.py`.
- **Plane B**: new `src/chat/` package: `config.py` and `retriever.py`. `src/shared/chat.py` (`RagChat` + a `Retriever` Protocol) and `shared/retrieval.py` (`CardIndex`, now importing from `embeddings.py`). `run_chat.py` as composition root.
- **Infra**: `infra/lib/agent_runtime.py` gains a Titan `InvokeModel` statement.
- Affected `specs/current` capabilities: `card-persistence` (PS-2 wording, new writer), `curation-pipeline` (post-persist embed step), `runtime-deployment` (role gains Titan). A new `chat-retrieval` capability is created at archive.

## Binding constraints
- `upsert` never writes `embedding`; a separate method does (source: card-persistence PS-2; AC3).
- `boto3` stays confined to `curation/dynamo.py` within `src/curation/`; `nodes.py`/`graph.py`/`state.py`/`interfaces.py` never import it (source: card-persistence invariant 1).
- Plane A and Plane B never import each other; `src/chat/` must not import `curation` or `api`, and `curation`/`shared` must not import `chat` (source: architecture-principles boundary 1, `test_feed_api_contract.py` pattern).
- Plane B duplicates, never imports, Plane A constants (table name, GSI name/partition), with a test asserting equality (source: feed-api AD-4 precedent).
- Config via `pydantic-settings`, explicit `validation_alias`, fail-fast at import (source: config-loading).
- DynamoDB resource API rejects Python floats: vectors are stored as `Decimal` and converted back to `float` on read (source: boto3 DynamoDB resource behavior; existing `seed_cards` uses `Decimal`).
- Titan call stays `dimensions=EMBED_DIM`, `normalize=True` so cosine equals dot product (source: `shared/config.py`).
- Existing `build_graph(store, discoverer)` callers and the `CardStore` Protocol are untouched (source: curation-graph contract; AC8).
- No deploy. The runtime image needs a rebuild later because `src/` is copied whole (`Dockerfile`: `COPY src/ ./src/`), but its dependencies are all main-group, so no dependency-group change (source: intent Out of scope; CLAUDE.md Docker-packaging gotcha — checked, no `--only-group` image is touched).

## Proposed approach
Revisable by the executor if it records why.
- **Decision:** `shared/embeddings.py` owns `embed(text)` and `card_text(mapping)`; `shared/retrieval.py` imports them and keeps `CardIndex` — rationale: smallest move that lets Plane A embed without importing Plane B; rejected: curation importing `shared.retrieval` (crosses planes), duplicating Titan code (drift).
- **Decision:** a one-method `EmbeddingWriter` Protocol (`set_embeddings`) in `curation/interfaces.py`, and `build_graph(store, discoverer, embedding_writer=None)` adds an `embed` node after `persist` only when a writer is passed — rationale: nodes cannot import `dynamo.py` (invariant 1), and defaulting to `None` leaves the graph and every existing test byte-identical (so no existing test calls real Bedrock); rejected: adding the method to `CardStore` (forces `JsonFileCardStore` to implement it and amends a frozen Protocol), and auto-detecting with `isinstance(store, EmbeddingWriter)` (existing moto-backed graph tests would suddenly hit Titan).
- **Decision:** the embed node runs after `persist`, per-card try/except, counts `embedded`/`embed_failed` into state and its own log record, then calls `embedding_writer.set_embeddings({url: vector})` once — rationale: a Titan or write failure can never block or roll back a card (AC2); `RunSummary`/EMF stay untouched (AC8); rejected: embedding before persist (couples card persistence to Titan availability).
- **Decision:** `DynamoCardStore.set_embeddings` uses `update_item` with `SET embedding=:e` and `ConditionExpression=attribute_exists(card_id)`, per-card try/except — rationale: never creates phantom items for a card whose persist failed; same failure style as `upsert`. `runtime_app.py` and `run_curation.py` each pass their `DynamoCardStore` as the writer.
- **Decision:** backfill = `DynamoCardStore` lists items lacking a usable `embedding` (Query on `feed-by-score`, length check against `EMBED_DIM` client-side), `curation/backfill.py` embeds and writes them through `set_embeddings`, `run_backfill_embeddings.py` is the thin CLI that prints `embedded/skipped/failed`. Runs with local AWS credentials, so no new role grant is needed — rationale: idempotent by construction (a second run lists nothing); rejected: a Lambda or scheduled backfill (not needed for a one-time catch-up).
- **Decision:** `src/chat/retriever.py` `DynamoCardRetriever(table_name=None, resource=None, embed_fn=embed)`: embed the query, `Query` `feed-by-score` where `gsi_pk = "CARD"` paginating on `LastEvaluatedKey` with a pinned projection (card fields + `embedding`), dot-product against vectors of length `EMBED_DIM`, return top-k `(card_dict, score)` with the vector stripped and `Decimal` converted — rationale: GSI projection is `ALL`, so the vector is already there; `Query` needs only `dynamodb:Query` on the index when the chat runtime is built; rejected: `Scan` (broader IAM, same read cost).
- **Decision:** `shared/chat.py` gains a `Retriever` Protocol (`search(query, k)`); `RagChat.__init__(retriever, k=TOP_K)` takes one instead of building `CardIndex` from cards. `CardIndex` already satisfies it. Justified now by two implementations (`CardIndex`, `DynamoCardRetriever`). `run_chat.py` builds `CardIndex(cards)` for the default backend and `DynamoCardRetriever()` for `CARD_STORE_BACKEND=dynamo`.
- **Decision:** `src/chat/config.py` mirrors `api/config.py`: `CARD_TABLE_NAME` (env `CARD_TABLE_NAME`, default `ai-radar-cards`) plus fixed `FEED_GSI_NAME`/`FEED_GSI_PARTITION`, with an equality test against `curation/config.py`.
- **Decision:** `agent_runtime.py` adds a `InvokeTitanEmbed` statement: `bedrock:InvokeModel` on `arn:aws:bedrock:<region>::foundation-model/amazon.titan-embed-text-v2:0` only. Titan is invoked by plain model id (no inference profile). The existing `UpdateItem` grant already covers `set_embeddings`.
- **Decision (scale ceiling, recorded per the intent constraint):** brute force is expected to hold up to about **2,000 embedded cards** or a measured p95 retrieval above about **1 s**. At the current cap of 8 new cards per run that is roughly 8 months of daily runs. First remedy: an in-process TTL cache in the long-lived chat runtime (chat-agent-runtime spec). Second: pgvector/Aurora per design §7.

## Consumers and migration
- `src/shared/retrieval.py` (`embed`, `_card_text` move out; `CardIndex` imports them) and `src/shared/chat.py` (`RagChat` signature): only consumer is `run_chat.py`. No tests import either.
- `tests/test_runtime_app.py::_fake_build_graph` takes `(store, discoverer)`; `runtime_app` will pass `embedding_writer`, so the helper gains an `embedding_writer=None` parameter. This is the only existing-test edit on the Plane A side.
- `tests/test_infra_agent_runtime.py::test_bedrock_statement_scoped_to_haiku_...`: asserts no resource contains "titan" anywhere in the role. This is the one existing assertion deliberately changed: the Haiku statement stays Haiku-only, and a new test pins the Titan statement.
- `test_dynamo_store.py` PS-2 test ("upsert never writes `embedding`") stays as is and keeps passing.
- `tests/test_feed_api_contract.py` gets no change; a parallel contract test is added for `src/chat/`.
- `CLAUDE.md` Layout and `README.md`/`ARCHITECTURE.md` Plane B tables: updated by the documentation step after audit, not by the executor.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Existing graph or runtime tests start calling real Titan | Low | High | Writer param defaults to `None`; new embed tests patch `curation.nodes` embed at its import site, like `summarize_with_usage` |
| Float vs `Decimal` bug stores or returns wrong vectors | Med | High | Dedicated moto round-trip test: stored `Decimal`, read back `float`, score matches the in-memory `CardIndex` for the same vectors (AC5) |
| `Query` pagination silently drops cards beyond 1 MB | Med | Med | Paginating-double test with a `LastEvaluatedKey` (AC6) |
| Table-name/GSI constants drift between planes | Low | Med | Equality test, as feed-api AD-4 |
| Runtime image deployed without rebuild: embeddings never written | Med | Med | Deploy runbook (Phase 3 closing step) lists the rebuild; backfill catches up |
| Backfill run against the wrong account | Low | Low | Script prints the account id and table name before writing |
| Titan throttling mid-backfill | Low | Low | Per-card failure counted; re-run is idempotent |

## Validation
One row per AC. All tiers are offline: DynamoDB via `moto`, Bedrock monkeypatched, zero real-AWS calls.

| AC | Demonstrated by | Tests to write | Tier | Framework | Setup | Focused command | Broader command | Cwd |
|---|---|---|---|---|---|---|---|---|
| AC1 | Graph run with a writer persists cards then each has a `EMBED_DIM`-float `embedding`; text matches `card_text` | embed node writes vectors for every persisted card; `card_text` parity with the Phase 0 rule; moto end-to-end through `build_graph` + `DynamoCardStore` | integration | pytest + moto | none (existing `dynamo_resource` fixture; patch embed at `curation.nodes`) | `uv run pytest tests/test_embed_step.py` | `uv run pytest tests/` | repo root |
| AC2 | Embed raising for one card still persists all cards, run completes, log carries `embed_failed=1`; writer failure also non-fatal | partial embed failure; total writer failure; no-writer graph unchanged | unit | pytest | none | `uv run pytest tests/test_embed_step.py -k fail` | `uv run pytest tests/` | repo root |
| AC3 | Embed, re-upsert, vector byte-identical, `updated_at` advanced | `set_embeddings` then `upsert` keeps vector; `set_embeddings` on missing card creates no item | integration | pytest + moto | none | `uv run pytest tests/test_dynamo_store.py tests/test_embed_step.py -k "embedding"` | `uv run pytest tests/` | repo root |
| AC4 | Backfill over a seeded table embeds only un-embedded and wrong-length items; second run embeds 0; one failure doesn't stop the rest | counts (`embedded/skipped/failed`), idempotent rerun, wrong-dimension healed, per-card failure isolation, CLI prints counts | integration | pytest + moto | none | `uv run pytest tests/test_backfill.py` | `uv run pytest tests/` | repo root |
| AC5 | Seeded known vectors give a known ranking; scores descending; vectors stripped; `k` > corpus; empty and fully un-embedded corpus | ranking order, return shape matches `CardIndex.search`, `Decimal` round-trip parity with `CardIndex`, `k` edge cases, un-embedded and wrong-length excluded | unit + integration | pytest + moto | none (seed items directly; Plane B tests must not import `DynamoCardStore`) | `uv run pytest tests/test_chat_retriever.py` | `uv run pytest tests/` | repo root |
| AC6 | A table double returning `LastEvaluatedKey` across two pages; every card is a candidate; `scan` never called | multi-page candidate coverage; asserts `query` on `feed-by-score` with `gsi_pk = "CARD"`, no `scan` | unit | pytest | page-forcing table double (precedent: `tests/test_feed_query.py`) | `uv run pytest tests/test_chat_retriever.py -k page` | `uv run pytest tests/` | repo root |
| AC7 | `RagChat` driven by each retriever; `run_chat.py` selects retriever by backend; default path unchanged | `RagChat` accepts any `Retriever` and still builds the cited context block; backend switch picks `DynamoCardRetriever` vs `CardIndex`; Bedrock `converse` patched | unit | pytest | none | `uv run pytest tests/test_rag_chat.py` | `uv run pytest tests/` | repo root |
| AC8 | Feed API and contract tests unchanged and green; `embedding` absent from feed responses; plane-separation and constant-equality guards for `src/chat/`; `Card`, `CardStore`, `RunSummary` signatures unchanged | existing `test_feed_*` untouched; new AST test (`chat` imports nothing from `curation`/`api`, `curation`/`shared`/`api` import nothing from `chat`, `boto3` confined to `chat/retriever.py`, `nodes.py` has no `boto3`); `chat/config.py` constants equal `curation/config.py`; new Titan-statement role test | unit + infra | pytest, CDK assertions | none | `uv run pytest tests/test_chat_contract.py tests/test_feed_api_contract.py tests/test_infra_agent_runtime.py` | `uv run pytest tests/` | repo root |
| AC9 | Whole suite, ruff and mypy green; only the two named existing tests changed | none new | n/a | pytest, ruff, mypy | none | `uv run pytest tests/ && uv run ruff check && uv run mypy .` | same | repo root |

## Revision log
- Revision 1 (2026-10-12): initial draft.
- Revision 1.1 (2026-10-12): AC9 command corrected to `uv run mypy .` (bare `mypy` errors with no target); baseline measured at 350 passed, not 349. No approach or scope change.

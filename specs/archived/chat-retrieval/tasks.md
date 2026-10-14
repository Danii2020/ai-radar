# Tasks: chat-retrieval

## Status
Needs audit

> Intent and execution plan are approved (2026-10-12). This status flips to
> `Implementing` when the human approves this file and the red-phase tests start.

## Baseline
- Base commit: `ed041f8`
- Branch: `main` (create a feature branch, e.g. `feat/chat-retrieval`, before the first commit)
- Interpreter: Python 3.12.11 (`uv run python`)
- Cwd: `/Users/danielerazo/python/project-agentcore-app`
- Commands: test `uv run pytest tests/`; lint `uv run ruff check`; type-check `uv run mypy .`
- Pre-existing failures: none (350 passed in ~148 s; ruff clean; mypy `Success: no issues found in 67 source files`)

## Outcomes
- [x] **O1** (AC1, AC2, AC3): Curation-time embedding. New `src/shared/embeddings.py` (`embed`, `card_text`, `shared/retrieval.py` re-imports them); `EmbeddingWriter` Protocol in `src/curation/interfaces.py`; `embed_node` in `src/curation/nodes.py`; `embedded`/`embed_failed` in `src/curation/state.py`; `build_graph(..., embedding_writer=None)` in `src/curation/graph.py`; `DynamoCardStore.set_embeddings` (conditional `update_item`, `Decimal` vectors) in `src/curation/dynamo.py`; `runtime_app.py` and `run_curation.py` pass their store as the writer.
  - Tests: `tests/test_embed_step.py`, additions in `tests/test_dynamo_store.py`
  - Red: `uv run pytest tests/test_embed_step.py` — expected `ImportError`/failures before implementation
  - Red evidence (2026-10-12): `tests/test_embed_step.py` collection error `ModuleNotFoundError: No module named 'shared.embeddings'`; `tests/test_dynamo_store.py` 4 `set_embeddings` tests fail (`AttributeError`, method missing).
  - Green: `uv run pytest tests/test_embed_step.py tests/test_dynamo_store.py tests/test_runtime_app.py -q` -> all pass (2026-10-13); nodes.py boto3-free (test_chat_contract).
- [x] **O2** (AC4): Backfill. `src/curation/backfill.py`, un-embedded-card listing on `DynamoCardStore`, root script `run_backfill_embeddings.py` printing `embedded/skipped/failed` plus account id and table name before writing.
  - Tests: `tests/test_backfill.py`
  - Red: `uv run pytest tests/test_backfill.py`
  - Red evidence (2026-10-12): collection error `ModuleNotFoundError: No module named 'curation.backfill'`.
  - Green: `uv run pytest tests/test_backfill.py -q` -> 8 passed (2026-10-13). Backfill writes by listed `card_id` via new `DynamoCardStore.set_embedding` (seeded items' card_id is not the url hash).
- [x] **O3** (AC5, AC6): Plane B retriever. `src/chat/__init__.py`, `src/chat/config.py` (pydantic-settings, duplicated table/GSI constants), `src/chat/retriever.py` (`DynamoCardRetriever`: paginated `Query` on `feed-by-score`, `Decimal`→`float`, top-k dot product, vectors stripped, un-embedded and wrong-length excluded).
  - Tests: `tests/test_chat_retriever.py`
  - Red: `uv run pytest tests/test_chat_retriever.py`
  - Red evidence (2026-10-12): collection error `ModuleNotFoundError: No module named 'chat'`.
  - Green: `uv run pytest tests/test_chat_retriever.py -q` -> all pass (2026-10-13).
- [x] **O4** (AC7): `Retriever` Protocol and `RagChat(retriever, k)` in `src/shared/chat.py`; `run_chat.py` selects `CardIndex` (default) or `DynamoCardRetriever` (`CARD_STORE_BACKEND=dynamo`).
  - Tests: `tests/test_rag_chat.py`
  - Red: `uv run pytest tests/test_rag_chat.py`
  - Red evidence (2026-10-12): 6 failed: `TypeError: 'FakeRetriever' object is not iterable` (RagChat still takes a card list) and `ModuleNotFoundError: No module named 'chat'` for the run_chat switch.
  - Green: `uv run pytest tests/test_rag_chat.py -q` -> 6 passed (2026-10-13).
- [x] **O5** (AC8): Guards and infra. `tests/test_chat_contract.py` (AST plane separation, `boto3` confinement, `nodes.py` boto3-free, constant equality with `curation/config.py`); `InvokeTitanEmbed` statement in `infra/lib/agent_runtime.py` (`bedrock:InvokeModel` on the Titan v2 foundation-model ARN only); feed API tests untouched and green.
  - Tests: `tests/test_chat_contract.py`, additions in `tests/test_infra_agent_runtime.py`
  - Red: `uv run pytest tests/test_chat_contract.py tests/test_infra_agent_runtime.py`
  - Red evidence (2026-10-12): 6 contract tests fail on missing `src/chat/`; Titan test fails `expected exactly one statement with Sid='InvokeTitanEmbed', found 0`.
  - Green: `uv run pytest tests/test_chat_contract.py tests/test_infra_agent_runtime.py -q` -> all pass (2026-10-13).
- [x] **O6** [evidence: `uv run pytest tests/test_runtime_app.py tests/test_infra_agent_runtime.py -q` pass, 2026-10-13] Migration (AC8, AC9): `tests/test_runtime_app.py::_fake_build_graph` gains `embedding_writer=None`; `tests/test_infra_agent_runtime.py` "no titan" assertion narrowed so the Haiku statement stays Haiku-only. `tests/test_config.py` had one assertion line edited for audit finding F3 (the `EMBED_MODEL_ID` re-export removed from `shared/retrieval.py`), with human approval (audit F6 recommendation). No other existing test edited.
- [x] **O7** Docs: `CLAUDE.md` Layout and Current state, `README.md` Phase 3 section and Plane B table, `ARCHITECTURE.md`, `CHANGELOG.md`, and component `AGENTS.md` plus `CLAUDE.md` bridges for `src/shared`, `src/curation` and `src/chat`; written by the documentation step from `audit.md`, not by the executor. [evidence: `node .sdd/doctor/run-doctor.mjs --only repo-readiness` shows the component-doc and component-bridge warnings for those three components cleared, 2026-10-13]
- [x] **O9** Independent audit: APPROVED WITH RESERVATIONS, round 3 (`audit.md`, 2026-10-13). F7 remains open (LOW, unavailable: CI and Stop-hook evidence); F11 accepted as a limitation.
- [x] **O8** [evidence 2026-10-13: `uv run pytest tests/ -q` 406 passed; `uv run ruff check` clean; `uv run mypy .` clean, 78 files] (AC9) Broader suite vs baseline: `uv run pytest tests/ && uv run ruff check && uv run mypy .` — baseline 350 passed.
- [ ] **O9** Independent audit: [verdict from audit.md]

## Working state
- Updated: 2026-10-13
- Outcome: O1-O6, O8 done; audit round 1 F1-F4, F9 addressed
- Phase: implemented; awaiting audit
- In progress: nothing
- Last command: `uv run pytest tests/ -q` -> 406 passed; `uv run ruff check` clean; `uv run mypy .` Success, 78 files
- Next step: audit (O9); docs (O7) after audit

## Finding responses
| Finding | Response | Evidence |
|---|---|---|
| F1 | `set_embeddings` returns the written count (int); `EmbeddingWriter` returns int; `embed_node` derives `embedded` and `embed_failed` (Titan failures + unwritten) from it in state and the `embed_complete` record; writer-exception path unchanged (embedded=0). | `uv run pytest tests/test_embed_step.py tests/test_dynamo_store.py -q` pass |
| F2 | `CARD_STORE_BACKEND` added to `src/chat/config.py`; `run_chat.py` reads `chat_config.CARD_STORE_BACKEND` and no longer imports `curation`. | `tests/test_rag_chat.py`, `tests/test_chat_contract.py` pass except one test, see note |
| F3 | `EMBED_MODEL_ID` re-export removed from `shared/retrieval.py`; only `shared/embeddings.py` and `shared/config.py` use it. | `tests/test_config.py` pass; ruff/mypy clean |
| F4 (+F5) | Test-side, done by test-writer. | `tests/test_rag_chat.py`, `tests/test_chat_retriever.py` pass |
| F9 | `chat/config.py` docstring now names only `curation`/`api` as off limits. | ruff clean |

| F2 follow-up | Env-dependent test made hermetic by the test-writer. Real regression found: `chat.config` did not trigger `load_dotenv`, so a `.env` `CARD_STORE_BACKEND=dynamo` was ignored. Fixed: `src/chat/config.py` does `import shared.config as _shared_config  # noqa: F401` before building settings (the `import x.y as z` form, since `from shared import config` returns a stale parent attribute under the test fixture). | `uv run pytest tests/ -q` 406 passed; ruff and mypy clean; `import chat.config` and `import run_chat` then `chat.config` both print `dynamo` with the real `.env` |

## Checkpoint
Specs complete: `intent.md` (approved rev 1), `execution-plan.md` (approved rev 1, plus 1.1 command fix). O1-O5 implemented 2026-10-13; O6 done by test-writer. Next: audit, then docs.

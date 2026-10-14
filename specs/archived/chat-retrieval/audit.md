# Audit: chat-retrieval

Both rounds review branch `feat/chat-retrieval` against base `ed041f8`, uncommitted
working tree. The specs are `intent.md` rev 1 and `execution-plan.md` rev 1.1.

- **Round 1** (2026-10-13): 14 modified files and 10 untracked paths.
- **Round 2** (2026-10-13): after the human-approved fixes for F1-F4, plus F5, F6 and F9
  and two follow-ups. `tests/test_config.py` is now also modified.
- **Round 3** (2026-10-13): test-only fixes for F10 and F12, plus a real build of the
  runtime image for F8. The production files are unchanged since round 2.

"Mutation" means the auditor changed one behavior in a scratch copy of `src/` + `tests/`
+ root scripts (outside the repo) and reran the focused tests. Every mutant listed was
caught, meaning at least one test failed. AC results below reflect round 2.

## AC results
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `build_graph(..., embedding_writer=store)` adds `persist -> embed -> END`. `embed_node` embeds `card_text(card.to_dict())` per card and writes through `set_embeddings`. `runtime_app.py` passes its store, and `run_curation.py` passes it only for `DynamoCardStore`. `card_text` is the Phase 0 `_card_text` body moved verbatim. Moto end-to-end: 6 cards produce 6 items with a 256-float unit-norm `embedding`. (rerun) |
| AC2 | PASS | Per-card try/except around Titan. `embedded` now equals the writer's *returned* written count, and `embed_failed` = Titan failures + `len(vectors) - written`. Both appear in state and in the single `embed_complete` record. If the writer raises: `embedded=0`, all vectors counted failed, and a separate `embed_write_failed` record. Titan failing on 1 of 6 cards gives 6 persisted, `embedded=5`, `embed_failed=1`. Mutants caught: no per-card catch, writer exception propagating, node ignoring the writer's return (2 failures), Dynamo returning `len(vectors)` (3 failures). Accepted limitation: cards whose `upsert` failed are still sent to Titan. Their conditional write then fails and is counted in `embed_failed`. AC2 holds and the cost is one small Titan call per failed upsert; see F11. (rerun) |
| AC3 | PASS | `upsert` is unchanged. `set_embedding` does a conditional `update_item SET embedding` (`attribute_exists(card_id)`). Embedding then re-upserting leaves the vector identical while `updated_at` advances. An unknown card creates no item and returns 0 written. The mutant that drops the condition is caught. (rerun) |
| AC4 | PASS | 40 cards with 12 missing give `(12, 28, 0)`, and the rerun gives `(0, 5, 0)`. A wrong length is healed, one failure does not stop the rest, results span several pages, and the CLI prints the counts after `account=… table=…`. The wrong-length mutant is caught. (rerun) |
| AC5 | PASS | Ranking, scores descending, `(card_dict, score)` shape with no vector, exclusion of un-embedded and wrong-length cards, k > corpus, empty and fully un-embedded corpus, Decimal parity. Mutants caught: no sort, keeping wrong-length vectors, leaking `embedding`. (rerun) |
| AC6 | PASS | `Query` on `feed-by-score` with `Key("gsi_pk").eq("CARD")`, paginated on `LastEvaluatedKey`. A page-forced double covers all candidates, and `scan` is poisoned. New in round 2: `test_retrieval_only_considers_the_card_partition_of_the_index` shows that a better-scoring item in partition `OTHER` is never a candidate. Mutants caught: no pagination, Query replaced by Scan (3 failures). (rerun) |
| AC7 | PASS (offline) | `run_chat.py` switches on `chat_config.CARD_STORE_BACKEND` (`src/chat/config.py`, default `"json"`, env `CARD_STORE_BACKEND`, loaded after `shared.config`'s `load_dotenv`). The dynamo path imports `DynamoCardRetriever` lazily; the default path is the unchanged `CardIndex(cards)`. Mutant caught: run_chat ignoring the backend. Fresh-interpreter check: a `.env`-only `CARD_STORE_BACKEND=dynamo` reaches `chat.config`. An interactive run against real DynamoDB + Bedrock is unavailable (no live AWS in audit, nothing deployed). |
| AC8 | PASS | No diff to `src/api/`, `src/contracts/`, `src/shared/cards.py`, `src/curation/summary.py`, `src/curation/metrics.py`, `apps/web/`, `pyproject.toml` or `uv.lock`. `CardStore` is unchanged; `EmbeddingWriter` (new, so not covered by AC8) now returns `int`. `test_feed_query.py::test_returned_card_never_carries_index_keys_or_embedding` passes. IAM: the `InvokeTitanEmbed` statement covers only the Titan v2 foundation-model ARN, and the Haiku statement stays Titan-free. (rerun) |
| AC9 | PASS | Round 3: `uv run pytest tests/ -q` 406 passed in 147.2 s; `uv run ruff check` clean; `uv run mypy .` clean (78 files). Round 2: 406 passed in 136.6 s (baseline 350); `uv run ruff check` clean; `uv run mypy .` clean (78 files). All rerun at the coordinator's request. Existing-test edits are the two the plan names (`test_runtime_app.py` helper, `test_infra_agent_runtime.py` Haiku assertion) plus one assertion line removed from `tests/test_config.py` (F3, human-approved; its subject, what `shared.retrieval` imports, is exactly what this spec changed). (rerun) |

## Binding-constraint compliance
| Constraint | Status | Evidence |
|---|---|---|
| `upsert` never writes `embedding`; a separate method does (PS-2, AC3) | PASS | `upsert` is not in the diff. Writers: `set_embeddings` (URL-keyed, Protocol, returns the written count) and `set_embedding` (card_id-keyed, used by backfill). The latter is a compliant alternative, with its reason recorded in tasks.md O2. |
| `boto3` confined to `curation/dynamo.py` within `src/curation/` (invariant 1) | PASS | The only `boto3` imports in `src/curation/` are in `dynamo.py` (`boto3` and `boto3.dynamodb.conditions.Key`). `backfill.py` does **not** import boto3; the executor's round-1 claim was inaccurate. The AST guards pass. |
| Planes never import each other (src packages; architecture-principles boundary 1) | PASS | `src/chat/` imports only `shared` (neutral) and its own modules. `curation`/`shared`/`api`/`contracts` import no `chat`. Since round 2, `run_chat.py` no longer imports `curation`, guarded by the new `test_run_chat_script_imports_nothing_from_curation`; the mutant that re-adds the import is caught. |
| Plane B duplicates Plane A constants, with an equality test | PASS | GSI name and partition equality test. `CARD_STORE_BACKEND` is duplicated too, with a hermetic default-equality test (`"json"` on both sides); the mutant with a `"dynamo"` default is caught. |
| Config via `pydantic-settings`, explicit `validation_alias`, fail-fast | PASS | `_ChatSettings` uses `case_sensitive=True` and aliases `CARD_TABLE_NAME` and `CARD_STORE_BACKEND`. The `.env` load ordering is guaranteed by `import shared.config` (the same pattern as `curation/config.py`), and the mutant without that import is caught. |
| `Decimal` storage / `float` read | PASS | Unchanged since round 1; parity test. |
| Titan `dimensions=EMBED_DIM`, `normalize=True` | PASS | `src/shared/embeddings.py`. |
| `build_graph(store, discoverer)` callers and `CardStore` untouched | PASS | The writer parameter defaults to `None`, and the no-writer graph is unchanged (tested). |
| No deploy; no dependency-group change; no `--only-group` image affected | PASS | Round 3, the image was actually built (rerun):<br>• `docker build --platform linux/arm64 -t ai-radar-agent-local-check .` exited 0. Its only warning is the pre-existing `FromPlatformFlagConstDisallowed`.<br>• Inside the image (`docker run --rm --platform linux/arm64 --network none ... python /probe/probe.py`, exit 0), these all import: `runtime_app`, `curation.dynamo`, `curation.backfill`, `curation.nodes`, `curation.graph`, `shared.embeddings`, `chat.retriever`.<br>• In the same probe, `build_graph(store, discoverer, embedding_writer=W)` ran with in-memory doubles (stubbed summarize and embed; the writer returns 1 fewer than given). Output: `persisted 3 embedded 2 embed_failed 1`, plus an `embed_complete` record.<br>• moto and pytest are absent from the image, so nothing relies on a dev-only package.<br>• The image was removed afterwards (`docker rmi`, exit 0). Nothing was pushed or deployed.<br>`Dockerfile.feed_api` closure is unchanged: `git diff ed041f8` is empty for `pyproject.toml`, `uv.lock`, `src/api`, `src/contracts`, `Dockerfile` and `Dockerfile.feed_api`. |

## Test coverage
| AC | Test | Status |
|---|---|---|
| AC1 | `tests/test_embed_step.py`: `test_embed_step_writes_a_vector_for_every_persisted_card_from_card_text`, `test_graph_run_against_dynamo_leaves_a_normalized_embed_dim_vector_on_every_card`, `test_card_text_*`, `test_embed_step_counts_land_in_state_and_the_embed_log_record` | PASS |
| AC2 | `tests/test_embed_step.py`: `test_titan_failure_on_one_card_still_persists_all_cards_and_logs_one_failure`, `test_writer_failure_does_not_fail_the_run_or_unpersist_cards`, `test_unwritten_vectors_are_reported_as_embed_failed_not_embedded`, `test_embed_failures_and_unwritten_vectors_both_count_as_failed`, `test_titan_failure_against_dynamo_persists_the_card_without_an_embedding`, `test_graph_without_a_writer_never_calls_embed_and_leaves_counters_unset` | PASS |
| AC3 | `tests/test_dynamo_store.py`: `set_embeddings` store / re-upsert / no phantom item (returns 0) / one failing card (returns 1) / `test_set_embeddings_returns_the_count_actually_written` | PASS |
| AC4 | `tests/test_backfill.py` (8 tests) | PASS |
| AC5 | `tests/test_chat_retriever.py` (7 AC5 tests) | PASS |
| AC6 | `tests/test_chat_retriever.py`: pagination, feed-by-score/no-scan, `test_retrieval_only_considers_the_card_partition_of_the_index` | PASS |
| AC7 | `tests/test_rag_chat.py` (6 tests); `tests/test_chat_contract.py` backend default, env override and `.env` regression tests | PASS |
| AC8 | `tests/test_chat_contract.py` (AST guards including `run_chat.py`, constant equality, config), `tests/test_infra_agent_runtime.py` Titan and Haiku tests, `tests/test_embed_step.py` Protocol tests, existing `tests/test_feed_*` | PASS |
| AC9 | Whole suite + ruff + mypy | PASS |

### Tier Results
Checked against `execution-plan.md` § Validation. Every tier runs inside `uv run pytest
tests/`. Moto-backed tests count as integration, and CDK `Template` assertions count as
infra. No dev dependency, config file or script was added in either round (`pyproject.toml`
and `uv.lock` are unchanged, and there is no new pytest config). There is no test at an
unnamed tier.

| Tier | Status | Evidence |
|---|---|---|
| unit | PASS | Found:<br>• graph-with-fakes in `test_embed_step.py` (AC2, including the written-count tests)<br>• paging and no-scan doubles in `test_chat_retriever.py` (AC6)<br>• `test_rag_chat.py` (AC7)<br>• AST guards and config in `test_chat_contract.py` (AC7/AC8)<br>Setup matches § Validation. Ran: rerun, green. |
| integration | PASS | Found: moto tests in `test_embed_step.py` (AC1/AC2), `test_dynamo_store.py` (AC3), `test_backfill.py` (AC4), `test_chat_retriever.py` (AC5, AC6 partition). They use the existing fixtures (`conftest.py` is unmodified). Ran: rerun, green. |
| infra | PASS | Found: `test_infra_agent_runtime.py` Titan statement and narrowed Haiku test (AC8). Ran: rerun, green. |
| n/a (AC9 gates) | PASS | Ran: pytest 406 passed, ruff clean, mypy clean (rerun). |

## Findings
| Id | Severity | Closure condition | Status |
|---|---|---|---|
| F1 | MEDIUM | AC2: `embed_complete` counts must reflect writes that were not made. | Closed (round 2). `set_embeddings` returns the written count, and `embed_node` derives `embedded`/`embed_failed` from it. Tests `test_unwritten_vectors_are_reported_as_embed_failed_not_embedded`, `test_embed_failures_and_unwritten_vectors_both_count_as_failed` and `test_set_embeddings_returns_the_count_actually_written` were added. Both mutants (node ignores the return; Dynamo returns `len(vectors)`) are caught. Residual limitation tracked as F11. |
| F2 | MEDIUM | Boundary 1: `run_chat.py` must not read `curation.config`. | Closed (round 2). The backend is in `src/chat/config.py`, `run_chat.py` imports no `curation`, and an AST test plus mutant confirm it. The `.env` regression the coordinator found is fixed by `import shared.config` in `chat/config.py`; shared is neutral, so the plane boundary holds. |
| F3 | LOW | AC9: drop the noqa `EMBED_MODEL_ID` re-export and narrow `tests/test_config.py`. | Closed (round 2). The re-export is gone, the one assertion line was removed, and ruff is clean. |
| F4 | LOW | AC7 test hygiene: remove the dead `run_chat.DynamoCardRetriever` patch. | Closed (round 2). Removed. A new dead seam of the same kind is F10. |
| F5 | LOW | AC6 row: assert the `gsi_pk = "CARD"` partition. | Closed (round 2). Behavioral partition test added; the Scan mutant is caught. |
| F6 | LOW | tasks.md: tick O6/O8 with evidence. | Closed (round 2). Both are ticked with evidence. Wording note: as of round 3, tasks.md O6 still says "no other existing test edited", although `tests/test_config.py` was edited for F3 (one assertion line, human-approved). tasks.md does not say this anywhere, so the **documentation step must reword O6** (handed off; it does not block). |
| F7 | LOW | harny-feedback: CI run for this change is green and logs `N of M command(s) ran` with N > 0. | Open. Unavailable in all three rounds: the branch is unpushed, so there is no CI run, and there is no artifact showing the Stop hook fired. The auditor's ruff/mypy reruns are clean every round. |
| F8 | LOW | Binding constraint 9 / intent Docker-closure constraint: build the runtime image and import `shared.embeddings` and `curation.nodes` inside it. | Closed (round 3, rerun). The arm64 image built with exit 0. All new and changed modules import inside it with no network, and `build_graph` with an `embedding_writer` double ran end to end (`persisted 3 embedded 2 embed_failed 1`). The image was removed with `docker rmi`. See the Binding-constraint table. |
| F9 | LOW | Standards: correct the `chat/config.py` docstring. | Closed (round 2). It now names `curation`/`api` as off limits and `shared` as neutral. |
| F10 | LOW | AC7 test hygiene: remove the dead `run_chat.CARD_STORE_BACKEND` patch. | Closed (round 3). `tests/test_rag_chat.py` has no `raising=False` patch left; the only backend patch is the live one on `chat_config`. The run_chat-ignores-backend mutant is still caught (1 failure). |
| F11 | LOW | AC2 accepted limitation: cards whose `upsert` failed are still embedded. | **Accepted limitation** (round 3, human decision via the coordinator). Rationale: AC2 holds. A failed upsert never blocks the run, and the vector of a card that was never persisted is rejected by the conditional write, then counted in `embed_failed` (the round-2 F1 fix). The only cost is one wasted Titan v2 call per failed upsert. The coordinator estimates about $0.00002 per card (Titan v2 input pricing for under 1K tokens of card text; not checked against current pricing docs by the auditor), and it happens only on the rare per-card upsert failure. Hand-off: the **documentation step carries this into README and CHANGELOG** as a known limitation. |
| F12 | LOW | Test quality: `fresh_config_modules` should model a fresh interpreter so the `.env` regression test is independent of the import form. | Closed (round 3, rerun). The fixture now `setattr`s and then `delattr`s the `config` attribute on the `shared`/`curation`/`chat` packages and `delitem`s the `sys.modules` entries. Verified in a scratch copy: `tests/test_chat_contract.py` passes 12/12 with both `import shared.config as _shared_config` (the shipped form) and `from shared import config as _shared_config`, and fails 1/12 with the import removed. Leak checks: (a) the contract file followed by `test_config`, `test_rag_chat`, `test_chat_retriever`, `test_embed_step`, `test_runtime_app` and `test_backfill` gives 194 passed; (b) a scratch probe test run after the contract file asserts that `sys.modules[...]` and the package `.config` attribute are the *same objects* as before the run, for all three modules (passed); (c) the full suite passes (406). |

## Audit log
| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-13 | APPROVED WITH RESERVATIONS | All 9 ACs and all binding constraints pass. Gates rerun: pytest 398 passed, ruff clean, mypy clean. 10 mutation checks were all caught. Two MEDIUM (F1, F2) and seven LOW (F3-F9) findings. Docker build, CI run and live AWS unavailable. |
| 2 | 2026-10-13 | APPROVED WITH RESERVATIONS | F1, F2, F3, F4, F5, F6 and F9 verified closed against their closure conditions. Gates rerun: pytest 406 passed (136.6 s), ruff clean, mypy clean (78 files). 9 new mutation checks were all caught: node ignores writer return, Dynamo returns `len(vectors)`, run_chat ignores backend, `chat.config` without the `shared.config` import, Query replaced by Scan, run_chat imports curation, chat backend default `"dynamo"`; plus the import-form probe recorded in F12. The fixture leak check is clean. No MEDIUM or higher remains. Open: F7 and F8 (unavailable: CI, Docker build), F10, F11, F12 (LOW). Live AWS is still unavailable. |
| 3 | 2026-10-13 | APPROVED WITH RESERVATIONS | F8, F10 and F12 verified closed; F11 recorded as an accepted limitation. The runtime arm64 image was actually built and probed (exit 0) and then removed. Gates rerun: pytest 406 passed (147.2 s), ruff clean, mypy clean (78 files). Mutants rechecked: run_chat ignores backend (caught); chat.config without the shared.config import (caught); the `from` import form now passes. Only F7 remains open (LOW, unavailable: CI and hook evidence). A live AWS run of `run_chat.py` remains unavailable. Documentation step: reword tasks.md O6, and carry F11 into README/CHANGELOG. |

## Final verdict
APPROVED WITH RESERVATIONS

**Summary**: Every acceptance criterion (AC1-AC9) and every binding constraint passes on
rerun evidence. That now includes a real arm64 build of the runtime image, whose
contents were checked by importing every new and changed module inside it and running
the curation graph with an embedding writer. Every finding is closed or accepted except
F7. The only reservations are checks the auditor could not run: CI on the unpushed
branch, evidence that the Stop hook fired, and a live AWS run of `run_chat.py`.

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- F7: push the branch and confirm the `harny-feedback.yml` run is green with N > 0 commands run.

**Recommendations** (nice to have):
- Documentation step: reword tasks.md O6 (it omits the F3 `tests/test_config.py` edit), and record the F11 accepted limitation in README and CHANGELOG.
- Before relying on AC7 in production, do one live `CARD_STORE_BACKEND=dynamo uv run run_chat.py` run after the backfill.

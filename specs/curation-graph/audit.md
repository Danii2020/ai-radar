# Audit: curation-graph

## Requirements Checklist
| ID | Requirement | Source | Status | Notes |
|---|---|---|---|---|
| R1 | Spike loop refactored into an explicit LangGraph `StateGraph` with named nodes and a typed `CurationState` | intent.md Goal 1 | PASS | `graph.py` builds a `StateGraph(CurationState)` with the five named nodes wired linearly; `state.py` defines `CurationState` TypedDict. Verified by reading both files + T1. |
| R2 | `build_graph(store, discoverer) -> CompiledGraph` is the single public construction API; deps injected, never imported in node code | intent.md Goal 2 | PASS | `build_graph(store, discoverer)` in `graph.py` is the only public constructor; nodes receive deps by closure factory, no infra import inside node code. Verified by reading `graph.py`/`nodes.py` + T1/T6. |
| R3 | `Discoverer` + `CardStore` Protocols defined as the Spec 02–04 seam, with local default impls | intent.md Goal 3 | PASS | `interfaces.py` Protocols match contract byte-for-byte; `local.py` provides `RssDiscoverer`/`JsonFileCardStore`. Verified by reading + T7–T10. |
| R4 | Per-item failure resilience: one bad item counted + skipped, run completes | intent.md Goal 4 | PASS | `summarize_node` per-item try/except increments `failed`, continues. Verified by T4 (passing). |
| R5 | Local defaults reproduce Phase 0 exactly (same cards, ranking, idempotency) | intent.md Goal 5 | PASS | No-regression test T2 replays spike logic; idempotency T5. `_save`-shape parity confirmed vs `spike.pipeline._save`. See Audit Log AL-2 (empty-batch seen.json skip) — honors idempotency. |
| R6 | Runnable locally via `uv run` entrypoint against real Bedrock; `src/spike/` left intact | intent.md Goal 6 | PASS | `run_curation.py` mirrors `run_spike.py` (sys.path inject, local defaults, invoke, render). Live smoke (Task 3.3): discovered=12 deduped=12 summarized=3 failed=0. `git diff src/spike/` empty. |
| R7 | Node code has zero AWS-infra coupling (no `boto3`; only Protocols + `bedrock.summarize`) | intent.md Constraints / Success criterion 4 | PASS | `grep` + AST test T6: no `boto3`/DynamoDB/file-path import in `nodes.py`/`graph.py`/`state.py`; matches are docstring/comment text only. |
| R8 | Reuse not fork: import `Card`, `summarize`, `discover`/`RawItem` from `src/spike/`; new code in `src/curation/` | intent.md Constraints | PASS | All curation modules import from `spike.*`; no forked copies. `src/spike/` unchanged. |
| R9 | LangGraph added via `uv add` (uv only, lockfile updated) | intent.md Constraints | PASS | `pyproject.toml` deps include `langgraph>=1.2.9`; `pytest` in dev group; `uv.lock` modified. No requirements.txt/venv. |

## Contract Compliance
| ID | Contract Item | Status | Verified By |
|---|---|---|---|
| C1 | `build_graph` returns compiled graph; node set == {discover, dedup, summarize, rank, persist}, wired linearly (Guarantee 1) | PASS | `graph.py` add_node×5 + START→discover→dedup→summarize→rank→persist→END; T1 asserts node set + edge set exactly. |
| C2 | Local defaults reproduce spike output, ranked descending (Guarantee 2) | PASS | T2 replays `spike.pipeline.run()` pure logic (dedup→cap→from_model→sort desc) against the graph with `JsonFileCardStore`+`RssDiscoverer`; equal. |
| C3 | Dedup runs before summarize+cap; no duplicate ever summarized (Guarantee 3) | PASS | `dedup_node`: `fresh_before_cap = dedup_filter(raw)` then `[:max_items]`. T11: seen item never reaches summarize, cap applies post-dedup. |
| C4 | One `summarize` failure → `failed += 1`, item skipped, run completes + persists rest (Guarantee 4) | PASS | `summarize_node` per-item try/except. T4: failed==1, summarized==1, surviving card persisted (upsert_calls==1). |
| C5 | Idempotent re-run over unchanged seen store → zero new cards; seen.json unchanged (Guarantee 5) | PASS | T5: cards==[], empty cards.json, `seen.json` byte-identical. Relies on empty-batch seen.json skip — see Audit Log AL-2 ruling (honors the guarantee). |
| C6 | No `boto3`/AWS-infra import in `src/curation/` node modules (Guarantee 6) | PASS | AST test T6 over nodes.py/graph.py/state.py; independent `grep` confirms only docstring/comment mentions, no imports. |
| C7 | Rank order is relevance-descending and stable for ties (Guarantee 7) | PASS | `rank_node` uses `sorted(..., reverse=True)` (stable). T3: ties keep discovery order → [B,D,A,C]. |
| C8 | `JsonFileCardStore` derives seen-key from `Card.url` via the `RawItem.url_hash` rule (Guarantee 8) | PASS | `local._url_hash` = `sha256(url)[:16]`, identical to `RawItem.url_hash`. T8: upsert→dedup_filter excludes same item. |
| C9 | Behavior changes only by injecting a different Protocol — no graph/node/state edits (Guarantee 9) | PASS | `build_graph` takes both deps by injection; tests swap `FakeCardStore`/`FakeDiscoverer` and real defaults without touching graph/node/state. |
| C10 | `Discoverer`/`CardStore` Protocol signatures match contract exactly (interfaces.py) | PASS | `interfaces.py` matches contract source verbatim (runtime_checkable, same method sigs/docstrings). |
| C11 | `CurationState` fields match contract (max_items, raw, fresh, cards, discovered, deduped, summarized, failed; no per_feed) | PASS | `state.py` TypedDict(total=False) has exactly the eight fields; no `per_feed`. |
| C12 | Error-handling contract honored (per-item skip, discover degrade, empty-discover, upsert raises loudly) | PASS | Per-item skip T4; discover degrade delegated to `feeds.discover` (skips bozo feeds, unchanged); empty-discover → empty cards.json (T5 path); `persist_node` does not catch `upsert` errors so disk errors propagate loudly. |

## Test Coverage
| ID | Test Description | Status | Test File |
|---|---|---|---|
| T1 | `build_graph` compiles; node set equals the five named nodes | PASS | tests/test_graph.py |
| T2 | Graph with stubbed discover+summarize produces same ranked cards as spike logic (no regression) | PASS | tests/test_graph.py |
| T3 | Rank node orders by relevance descending, stable on ties | PASS | tests/test_graph.py |
| T4 | One stubbed `summarize` raise → `failed == 1`, run completes, other cards persisted | PASS | tests/test_graph.py |
| T5 | Re-invoke with populated seen store → `cards == []`, seen.json unchanged | PASS | tests/test_graph.py |
| T6 | `nodes.py` contains no `boto3` reference / does not import boto3 | PASS | tests/test_graph.py |
| T7 | `JsonFileCardStore.dedup_filter` drops seen url_hashes; `force=True` bypasses | PASS | tests/test_local_store.py |
| T8 | `upsert` then `dedup_filter` on same items returns empty (idempotency + url-hash bridge) | PASS | tests/test_local_store.py |
| T9 | `upsert` writes seen.json (sorted) + cards.json (batch, indent=2) matching spike `_save` | PASS | tests/test_local_store.py |
| T10 | `RssDiscoverer.discover` delegates to `feeds.discover(FEEDS, per_feed)` (monkeypatched) | PASS | tests/test_local_store.py |
| T11 | Dedup-before-cap order: with seen subset + max_items, never summarizes a seen item | PASS | tests/test_graph.py |

Full run: `uv run pytest -q` → **16 passed in 0.22s** (auditor-executed, not taken on faith).
Note: no `@pytest.mark.live` markers exist in this suite; every test monkeypatches `summarize` — the default run is fully offline as required.

## Audit Log
| Date | Auditor | Finding | Severity | Resolution |
|---|---|---|---|---|
| 2026-07-10 | sdd-auditor | `uv run pytest -q` re-run by auditor: 16 passed in 0.22s. All T1–T11 green. | INFO | None — matches conductor's report. |
| 2026-07-10 | sdd-auditor | All 9 Behavior Guarantees verified against code + tests; all 12 Contract Compliance items PASS. `interfaces.py`, `state.py` match contract source verbatim. | INFO | None. |
| 2026-07-10 | sdd-auditor | AL-2 (Deviation A ruling): `JsonFileCardStore.upsert` guards the `seen.json` write behind `if cards:`, skipping the rewrite on an empty batch. Contract's `upsert` docstring prose ("write seen.json + cards.json") reads as unconditional, but Guarantee 5 explicitly requires seen.json "unchanged" on an idempotent re-run, and the approved test T5 asserts byte-identical seen.json (seeded without indent, so an unconditional `indent=2` rewrite would change bytes and FAIL). The guard condition `if cards` is exactly the condition under which `seen` could gain new keys, so skipping is content-equivalent and byte-preserving. **Ruling: honestly satisfies Guarantee 5; NOT a contract violation.** | LOW | Recommend (non-blocking) a one-line clarification to the `upsert` docstring in contract.md noting the empty-batch short-circuit, to remove the surface tension with Guarantee 5. Do not amend behavior. **Resolved 2026-07-10: sdd-architect amended the contract.md `upsert` NOTE to document the empty-batch short-circuit (docs-only, verified by conductor).** |
| 2026-07-10 | sdd-auditor | AL-3 (Deviation B ruling): `nodes.py` implements `discover_node`/`dedup_node`/`persist_node` as factory functions returning `(state)->update` closures that capture `discoverer`/`store`; `summarize_node`/`rank_node` are plain functions (no injected deps). Contract's `nodes.py` shows illustrative flat `def node(state)` signatures, but its prose states "Node functions are closures (or partials) bound to the injected dependencies," and roadmap Phase 2.3 + Task 2.5–2.9 specify factory functions/closures. **Ruling: conforms** — the factory/closure pattern is exactly what the contract prose, Guarantee 9 (injection), and roadmap prescribe; the flat signatures were illustrative of shape only. | INFO | None. |
| 2026-07-10 | sdd-auditor | Portability keystone confirmed: `grep` + AST test T6 show no `boto3`/DynamoDB/file-path import in `nodes.py`/`graph.py`/`state.py` (only docstring/comment mentions). `bedrock.summarize` is the sole Bedrock touchpoint, imported as-is. | INFO | None. |
| 2026-07-10 | sdd-auditor | Conventions: uv-only (`langgraph>=1.2.9` in deps, `pytest` in dev group, `uv.lock` updated, no requirements.txt); `from __future__ import annotations` in all curation modules; lean small-module/dataclass style. `git diff src/spike/` empty — reference plane untouched. Conforms to docs/architecture-principles.md: exactly the two specced Protocols (no speculative interfaces), ubiquitous language (discover/dedup/summarize/rank/persist), `Card` reused as shared contract. | INFO | None. |
| 2026-07-10 | sdd-auditor | File Change Map reconciled against disk: all CREATE files exist (`src/curation/{__init__,interfaces,state,local,nodes,graph}.py`, `run_curation.py`, `tests/test_local_store.py`, `tests/test_graph.py`); MODIFY files changed (`pyproject.toml`, `uv.lock`); `src/spike/**` UNCHANGED as required. | INFO | None. |
| 2026-07-10 | sdd-auditor | `run_curation.py` has no automated test (only manual live smoke Task 3.3). Consistent with spec intent (live entrypoint); smoke evidence stands (discovered=12 deduped=12 summarized=3 failed=0, cards 8/7/6). | LOW | Non-blocking. Optional: a future smoke/import test of the entrypoint wiring. |

## Final Verdict

**Status**: APPROVED

**Summary**: The curation-graph implementation faithfully refactors the Phase 0 spike loop into an injected-dependency LangGraph `StateGraph`; all 9 Behavior Guarantees, all 12 contract-compliance items, and all 9 intent requirements pass, with 16/16 tests green (auditor-run) and the portability keystone intact.

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- None.

**Recommendations** (nice to have):
- Add a one-line clarification to the `JsonFileCardStore.upsert` docstring in contract.md noting the empty-batch `seen.json` short-circuit, so the prose no longer reads as an unconditional write in tension with Guarantee 5 (AL-2). Behavior is correct and must not change.
- Optionally add a lightweight import/wiring smoke test for `run_curation.py` (currently only manually smoke-tested per Task 3.3) (AL-4).

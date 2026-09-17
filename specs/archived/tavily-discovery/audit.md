# Audit: tavily-discovery

Audited 2026-07-15 by sdd-auditor against contract.md (authoritative), intent.md,
roadmap.md, tasks.md. Full test suite executed (`uv run pytest tests/ -v`):
**27 passed** (16 Spec 01 + 11 new), 0 failed, 0 skipped/xfailed.

## Requirements Checklist
| ID | Requirement | Source | Status | Notes |
|---|---|---|---|---|
| R1 | `TavilyDiscoverer` implements the Spec 01 `Discoverer` Protocol, returning `RawItem`s with populated snippets from topic-seeded Tavily search | intent.md Goal 1 | PASS | `tavily.py` maps `content`→`snippet` via `_clean`; `discover()->list[RawItem]`; verified by test_tavily T1 |
| R2 | Discovery cost/breadth-tunable via env-overridable config with a hard per-run total cap as primary lever | intent.md Goal 2 | PASS | `config.py` all knobs env-overridable; `max_results` cap enforced (T2) |
| R3 | `CompositeDiscoverer` implements `Discoverer`, runs sources, merges, removes cross-source URL-hash dups | intent.md Goal 3 | PASS | `composite.py` order-preserving dedup; T7 |
| R4 | Per-source resilience: Tavily outage does not kill the run — degrades to RSS-only, logged + counted | intent.md Goal 4 | PASS | Two-layer try/except (per-seed + per-source); T3, T4, T8 |
| R5 | Unchanged Spec 01 graph runs with `CompositeDiscoverer` | intent.md Goal 5 | PASS | Seam test T9 invokes `build_graph(store, composite)` end-to-end; graph/nodes/state/interfaces show zero diff vs HEAD |
| R6 | Manual smoke hits real Tavily+Bedrock; automated suite makes zero live Tavily calls | intent.md Goal 6 | PASS | Every test stubs `TavilyClient` via monkeypatch; `run_tavily.py` is the only live path (smoke run deferred to human, Task 3.2) |
| R7 | Key read from `TAVILY_API_KEY` (env/`.env`) only; no Secrets Manager/boto3; key in no committed file | intent.md Non-Goals/Constraints | PASS | `config.TAVILY_API_KEY = os.getenv(...)`; grep `tvly-` finds only the `"tvly-..."` placeholder in contract.md; `.env` gitignored |
| R8 | Reuse not fork: `RawItem`/`_clean`/`Card`/`spike.config` pattern reused; new code in `src/curation/`; `src/spike/` + `interfaces.py` untouched | intent.md Constraints | PASS | Imports `RawItem, _clean` from `spike.feeds`; `git diff HEAD` on spike/ + interfaces.py = empty |
| R9 | Tavily SDK added via `uv add` (uv only, lockfile updated) | intent.md Constraints | PASS | `pyproject.toml` +`tavily-python>=0.7.26`; `uv.lock` resolves 0.7.26; import verified |

## Contract Compliance
| ID | Contract Item | Status | Verified By |
|---|---|---|---|
| C1 | `discover()` returns `RawItem`s with `snippet` from `content`, never exceeds `max_results` (G1) | PASS | tavily.py L102-122 (`items[:self.max_results]`); tests T1, T2 |
| C2 | One seed raising caught/logged/counted; others run; never raises (G2) | PASS | tavily.py L97-100 per-seed except; test T3 |
| C3 | Total Tavily failure yields `[]`, no raise (G3) | PASS | test T4 (all seeds raise → `[]`, failures()==2) |
| C4 | Composite returns URL-hash-deduped union, order-preserving, first-source-wins (G4) | PASS | composite.py L39-47; test T7 (RSS variant of shared URL kept) |
| C5 | One source raising caught/logged/counted; others returned; never raises (G5) | PASS | composite.py L31-37; test T8 |
| C6 | Dedup uses exact `RawItem.url_hash` (`sha256(url)[:16]`) matching RSS/store/Spec 01 (G6) | PASS | Both discoverers key on `RawItem.url_hash` (from unchanged `spike.feeds`); T6, T7 |
| C7 | Spec 01 graph runs unchanged: `build_graph(store, Composite([...]))` compiles+invokes, no seam edits (G7) | PASS | `git diff HEAD` on graph/nodes/state/interfaces.py = empty; seam test T9 |
| C8 | `tavily` SDK imported only in `tavily.py`; not in nodes/graph/state/composite/interfaces; no `boto3` in spec (G8) | PASS | AST test T10 + manual grep: `tavily` import only at tavily.py L9,70; no `boto3` import anywhere in src/curation (only doc comments) |
| C9 | Key read from `config.TAVILY_API_KEY` only; no SecretsManager/boto3 path (G9) | PASS | `from_config()` reads `config.TAVILY_API_KEY`, raises ValueError if empty; test T5 |
| C10 | All knobs read from `curation.config`, env-overridable (G10) | PASS | `from_config()` L56-66 pulls every knob from config; none hardcoded |
| C11 | Tavily API surface matches Context7-pinned signature/response shape | PASS | `search()` call passes query/search_depth/topic/days/max_results/include_domains/exclude_domains/include_raw_content; reads `results[].{title,url,content,published_date}` per contract |
| C12 | Error-handling contract honored (7 rows) | PASS | See Error Handling Contract table below — every row maps to code |

### Error Handling Contract — row-by-row
| Error Condition | Implemented at | Status |
|---|---|---|
| One Tavily seed raises | tavily.py L97-100 (`except`→print `! tavily seed failed`, `failures += 1`, continue) | PASS (T3) |
| All seeds raise / total outage | returns `items[:max]` == `[]`; never raises | PASS (T4) |
| Tavily source raises inside composite | composite.py L33-36 (`! discoverer failed`, count, `[]`) | PASS (T8) |
| `TAVILY_API_KEY` unset at `from_config()` | tavily.py L52-55 raises `ValueError` | PASS (T5) |
| Result missing url/title | tavily.py L103-109 skip guard | PASS (T1 skip case) |
| Result missing `published_date` | `result.get("published_date", "")` L114 | PASS (T1: published == "") |
| Same article RSS+Tavily | composite url_hash dedup first-wins | PASS (T7) |

## Test Coverage
| ID | Test Description | Status | Test File |
|---|---|---|---|
| T1 | Tavily result → `RawItem` mapping; missing url/title skipped | PASS | tests/test_tavily.py |
| T2 | Per-run `max_results` cap enforced | PASS | tests/test_tavily.py |
| T3 | One seed raises → counted, others returned, no raise | PASS | tests/test_tavily.py |
| T4 | All seeds raise → `[]`, no raise | PASS | tests/test_tavily.py |
| T5 | `from_config()` ValueError when key unset | PASS | tests/test_tavily.py |
| T6 | Within-source url_hash dedup, first wins | PASS | tests/test_tavily.py |
| T7 | Composite merge + dedup first-source-wins, order-preserving | PASS | tests/test_composite.py |
| T8 | One source raises → degrade + counted + no raise | PASS | tests/test_composite.py |
| T9 | Seam: `build_graph(FakeStore, Composite([...]))` invokes end-to-end → cards | PASS | tests/test_composite.py |
| T10 | Portability: `tavily` only in tavily.py; no `boto3` in spec modules | PASS | tests/test_composite.py |
| T11 | Zero live Tavily calls in suite | PASS | Both files stub `TavilyClient`/use `FakeDiscoverer`; no network |

**Test integrity check:** assertions were not weakened. Tests exercise real
behavior (HTML-strip via `_clean`, exact url ordering, cap counts, failure
counts). No `skip`/`xfail`/`pytest.mark` weakening present. T10 includes an
anti-vacuous guard asserting `tavily` IS imported in tavily.py. conftest.py
fixtures (`make_raw_item`, `summarize_stub_factory`) are unmodified Spec 01 code
(clean `git status`).

## Audit Log
| Date | Auditor | Finding | Severity | Resolution |
|---|---|---|---|---|
| 2026-07-15 | sdd-auditor | All 10 behavior guarantees + 7 error-handling rows implemented and tested; 27/27 pass; stable seam (graph/nodes/state/interfaces/spike) byte-unchanged vs HEAD; portability holds (tavily only in tavily.py, no boto3); no key leak | — | APPROVED |
| 2026-07-15 | sdd-auditor | `timeout` param from the pinned API surface not passed to `search()`; SDK default (60s) used. Not a config knob in contract; non-blocking | LOW | Optional: add a `timeout` knob later if long searches need bounding |
| 2026-07-15 | sdd-auditor | `include_raw_content=False` hardcoded in `search()` call | LOW | Per contract (off by default, not a knob); acceptable as-is |

## Final Verdict

**Status**: APPROVED

**Summary**: The tavily-discovery implementation faithfully matches its contract —
all 10 behavior guarantees, the full error-handling table, and the stable-seam
constraint are satisfied; 27/27 tests pass with zero live Tavily calls and no
weakened assertions.

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- None.

**Recommendations** (nice to have):
- Consider exposing a `CURATION_TAVILY_TIMEOUT` knob (currently the SDK's 60s
  default is used implicitly) if bulk searches ever need a tighter bound.
- Task 3.2 (live `uv run run_tavily.py` smoke against real Tavily+Bedrock)
  remains the human's manual step — this audit statically verified the
  entrypoint mirrors `run_curation.py` (sys.path inject, `--force`, render +
  counters incl. `discoverer.failures()`) but did not execute it. Marking
  tasks.md 4.6 complete is confirmed; 3.2 correctly remains blocked/deferred.

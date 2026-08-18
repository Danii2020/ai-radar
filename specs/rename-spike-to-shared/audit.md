# Audit: rename-spike-to-shared

Pre-rename baseline, measured 2026-08-12 on `main` @ `d59687e`:
**145 tests passed**; `grep -rn "spike"` (case-insensitive, excluding `.venv/`,
`cdk.out/`, `uv.lock`, `.git/`) matched **88 lines across 22 tracked files**
plus 12 lines in `specs/**` files that stay frozen.

## Requirements Checklist

| ID | Requirement | Source | Status | Notes |
|---|---|---|---|---|
| R1 | `src/spike/` is renamed to `src/shared/` via `git mv`, 7 modules surviving | intent.md Goal 1 | PENDING | |
| R2 | Every absolute importer is repointed — 24 import statements in 15 files | intent.md Goal 1 / contract §1.1 | PENDING | |
| R3 | The 4 `SPIKE_*` env keys become `AI_RADAR_*` and the cache default becomes `.ai_radar_cache` | intent.md Goal 2 / contract §3 | PENDING | Constant names + default values unchanged |
| R4 | `run_spike.py` is deleted | intent.md Goal 3 / contract §4.1 | PENDING | |
| R5 | `spike/pipeline.py` is deleted, with its zero-caller status proven, not assumed | intent.md Goal 3 / contract §4.1 | PENDING | Auditor must re-run the importer grep, not trust the claim |
| R6 | `shared/config.py`'s apologetic "Despite the name…" docstring is replaced by the pinned text | intent.md Goal 4 / contract §5 | PENDING | |
| R7 | `shared/__init__.py`'s docstring describes the package's real cross-plane + Plane-B role | intent.md Goal 4 / contract §5 | PENDING | |
| R8 | Living docs updated: `README.md`, `CLAUDE.md`, `.claude/agents/sdd-architect.md`, `.env.example`, `pyproject.toml`, `.gitignore`, `.dockerignore` | intent.md Goal 5 / contract §6 | PENDING | |
| R9 | Historical record frozen: `specs/**` and `docs/**` unchanged except the FU1 checkbox | intent.md Goal 5 / contract §6 | PENDING | Gate G4 |
| R10 | 145 tests pass, same IDs, zero assertions changed | intent.md Goal 6 | PENDING | Gate: pytest + diff review |
| R11 | The 3 `spike`-named test functions are retained verbatim | intent.md Non-Goals / contract §7 G2 | PENDING | Protects `specs/run-observability/audit.md:142`, `specs/curation-graph/audit.md:36` |
| R12 | `bedrock.summarize()` is retained despite losing its last production caller | intent.md Non-Goals / contract §4.2 | PENDING | |
| R13 | No new file, no new dependency, no `uv.lock` change | intent.md Non-Goals / contract §10 | PENDING | |
| R14 | Plane B is NOT split into its own package | intent.md Non-Goals | PENDING | `chat.py`/`retrieval.py` still under `shared/` |
| R15 | No `pydantic-settings`; `shared/config.py` keeps plain `os.getenv` | intent.md Non-Goals | PENDING | FU2 is a separate spec |
| R16 | The human's local migration (`.env` keys, cache dir move) is documented and executed | intent.md Constraints / contract §12 | PENDING | Tasks H1-H3 |
| R17 | The live-image-lags-the-rename caveat is stated in `README.md` | intent.md Constraints / contract §12 | PENDING | |

## Contract Compliance

| ID | Contract Item | Status | Verified By |
|---|---|---|---|
| C1 | 7 modules moved; `pipeline.py` not moved (contract §1) | PENDING | `git status` shows 7 `R` entries + 2 `D` |
| C2 | Intra-package relative imports untouched (contract §1) | PENDING | `git diff` on `shared/{bedrock,cards,feeds,chat}.py` shows **no** import-line hunks |
| C3 | All 24 absolute imports repointed exactly per the §1.1 table | PENDING | Gates G1/G2 + pytest collection |
| C4 | Alias renamed `spike_config` → `shared_config` at all 8 sites (contract §2.1) | PENDING | `grep -rn "shared_config" src/ tests/` = 8 |
| C5 | **`curation/summary.py` still reads prices via module-attribute access**, not a `from`-import (contract §2.1) | PENDING | Read `summary.py:74-75`; `test_…reads_prices_from_spike_config_at_call_time` must genuinely bite. A `from`-import would silently pass the test while breaking the monkeypatch |
| C6 | Public API signatures unchanged (contract §2.1 list) | PENDING | Signature-by-signature diff vs. the §2.1 list |
| C7 | Data models + persisted JSON/DynamoDB shapes unchanged (contract §2.2) | PENDING | `git diff` on `shared/cards.py`, `shared/feeds.py` = rename only |
| C8 | Env key mapping applied exactly; no back-compat shim (contract §3) | PENDING | See the mapping table below |
| C9 | `pipeline.py` deletion justified AND the cascade stopped at `bedrock.summarize()` (contract §4) | PENDING | `summarize` still present in `shared/bedrock.py`; `tests/test_bedrock_usage.py:109` still calls it |
| C10 | The one user-visible string change (`run_chat.py:27` → `run_curation.py`) is present and correct | PENDING | Read `run_chat.py`; no test covers it |
| C11 | Docstring/comment sweep complete per the §5 table (22 rows) | PENDING | Gates G1/G2/G3 |
| C12 | Reference-scope policy honored — living edited, historical frozen (contract §6) | PENDING | Gate G4 |
| C13 | Gate G1 — code+config hard zero | PENDING | Paste exact output (must be empty) |
| C14 | Gate G2 — tests: exactly 3 enumerated lines | PENDING | Paste exact output |
| C15 | Gate G3 — living docs: zero path/var/command references | PENDING | Paste exact output |
| C16 | Gate G4 — `git diff --stat specs/ docs/` = 1 file, 1 line | PENDING | Paste exact output |
| C17 | Gate G5 — import smoke over all 7 `shared.*` modules + 3 entrypoints | PENDING | Paste `import smoke OK` |
| C18 | Guarantee 4 — portability regression: `curation/{nodes,graph,state,summary,metrics}.py` import no AWS SDK | PENDING | `test_curation_modules_do_not_import_aws_sdk_or_bedrock_agentcore` green |
| C19 | Guarantee 7 — `git log --follow` works on the moved files | PENDING | `git log --follow src/shared/config.py` |
| C20 | Guarantee 8 — `cdk diff` reports no differences on all 4 stacks | PENDING | |
| C21 | Guarantee 9 — `uv.lock` untouched; `pyproject.toml` diff is the `description` line only | PENDING | `git diff uv.lock` empty |
| C22 | Migration runbook present and executable (contract §12) | PENDING | Tasks H1-H4 |

## Env key mapping (permanent record)

Recorded here per contract §6.1, so that anyone re-reading `README.md`'s
"Verified 2026-07-28" block — which was updated to the new key name — can
resolve what was actually in force at the time.

| Old key (in force through 2026-08-12) | New key | Value | Sites updated |
|---|---|---|---|
| `SPIKE_MAX_ITEMS` | `AI_RADAR_MAX_ITEMS` | `8` | `shared/config.py:48`, `.env.example:21`, `README.md` ×4, human's `.env` |
| `SPIKE_PER_FEED` | `AI_RADAR_PER_FEED` | `5` | `shared/config.py:49`, `.env.example:22`, `README.md` ×2, human's `.env` |
| `SPIKE_TOP_K` | `AI_RADAR_TOP_K` | `4` | `shared/config.py:45`, `.env.example:23`, human's `.env` |
| `SPIKE_CACHE_DIR` | `AI_RADAR_CACHE_DIR` | unset (default) | `shared/config.py:62` |
| `.spike_cache/` (dir) | `.ai_radar_cache/` | — | `shared/config.py:62`, `.gitignore`, `.dockerignore`, `README.md` ×4, `CLAUDE.md`, human's filesystem |

No backward-compatible dual-read was added (contract §3). The deployed
AgentCore image sets **none** of these keys — it runs on code defaults — so
the rename has no live effect until the image is rebuilt (Task H4).

## Test Coverage

No new tests are authored (contract §6 forbids new files). The existing suite
is the regression harness; the table below records what already covers each
risk and, honestly, what does not.

| ID | Test Description | Status | Test File |
|---|---|---|---|
| T1 | Full suite passes at the baseline count of 145, same test IDs | PENDING | `tests/` (whole suite) |
| T2 | The 3 retained `spike`-named tests still exist and pass under their original names | PENDING | `tests/test_graph.py:201`, `tests/test_local_store.py:104`, `tests/test_run_summary.py:86` |
| T3 | The price monkeypatch still bites through `summary_module.shared_config` (proves C5) | PENDING | `tests/test_run_summary.py::test_estimate_bedrock_cost_usd_reads_prices_from_spike_config_at_call_time` |
| T4 | Portability: no AWS SDK import in the 5 core curation modules | PENDING | `tests/test_graph.py::test_curation_modules_do_not_import_aws_sdk_or_bedrock_agentcore` |
| T5 | Phase-0 parity still holds for the compiled graph (survives `pipeline.py`'s deletion because it replicates the logic inline rather than importing it) | PENDING | `tests/test_graph.py::test_graph_matches_spike_pipeline_logic_for_same_inputs` |
| T6 | `bedrock.summarize()` still exists and behaves (proves the §4.2 cascade stop) | PENDING | `tests/test_bedrock_usage.py:109` |
| T7 | `JsonFileCardStore` still writes `seen.json`/`cards.json` in the Phase-0 shape under the new cache dir | PENDING | `tests/test_local_store.py` (uses `tmp_path`, so unaffected by the default change) |
| T8 | AgentCore handler, `curation_run_complete` record and EMF document unchanged | PENDING | `tests/test_runtime_app.py`, `tests/test_run_summary.py` |
| T9 | CDK stacks synthesize identically | PENDING | `tests/test_infra*.py` + manual `cdk diff` |
| **T10** | **`shared/chat.py`, `shared/retrieval.py`, `run_chat.py` import cleanly** | PENDING | **No automated test exists** — covered only by manual gate G5. Logged as FU-A in tasks.md |

### Known coverage gaps (state them, do not paper over them)

- **G1 — Plane B is untested.** Nothing in the 145-test suite imports
  `shared/chat.py`, `shared/retrieval.py` or `run_chat.py`. A missed import or
  the changed user message in `run_chat.py:27` would ship green. Gate G5 is a
  one-off manual command, not a standing guard. Tracked as FU-A.
- **G2 — The env-key rename has no test.** `shared/config.py` reads env at
  import time with no test asserting which keys it reads. A typo like
  `AI_RADAR_MAXITEMS` would silently fall back to the default `8` — the same
  value the human's `.env` sets today, so nothing observable would change.
  Mitigation is review + Task H3's verification snippet.
- **G3 — The gates are grep-based, so they prove absence of a *string*, not
  correctness of a *rewrite*.** G1 passing means nothing says `spike`; it does
  not prove an import points at the right module. pytest collection + G5 cover
  that.

## Audit Log

| Date | Auditor | Finding | Severity | Resolution |
|---|---|---|---|---|
| 2026-08-12 | sdd-architect | Baseline recorded: 145 tests pass; 88 `spike` lines across 22 tracked files (+12 frozen lines in `specs/**`) | Informational | Success criteria pinned to these numbers |
| 2026-08-12 | sdd-architect | **No string-based patch targets exist** (`monkeypatch.setattr("spike.x.y", …)` / `patch("spike…")` / `import_module`) anywhere in `tests/`. The silent-failure mode anticipated in the brief does not exist in this repo — every missed import fails loudly | Informational | Gates G1/G2 keep it that way |
| 2026-08-12 | sdd-architect | The real silent-failure surface is different: `shared/chat.py`, `shared/retrieval.py` and `run_chat.py` are imported by **zero** tests | **Medium** | Gate G5 added as a named acceptance gate; FU-A logged |
| 2026-08-12 | sdd-architect | A literal repo-wide zero-occurrence grep is unachievable: 3 retained test names (human decision Q4) and the legitimate English phrase "Phase 0 spike" in `README.md`/`CLAUDE.md`/`docs/app-design-on-agentcore.md` | Informational | Gate split into 4 tiers with explicit per-tier allowlists (contract §7) |
| 2026-08-12 | sdd-architect | Deleting `run_spike.py` orphans `pipeline.py` (its only importer, verified by grep), which orphans `bedrock.summarize()` (whose only other caller is a test) | **Medium** | Cascade stopped at `pipeline.py`; `summarize()` retained with justification (contract §4.2) + FU-B logged |
| 2026-08-12 | sdd-architect | `tests/conftest.py:22` inserts `src/` via `parent.parent / "src"` (path-relative) and `pyproject.toml` has no `[tool.pytest]` section — no test-discovery config needs repointing. `Dockerfile` copies `src/` wholesale, naming no subpackage | Informational | No task needed; recorded so the auditor does not go looking |
| 2026-08-12 | sdd-architect | `infra/` contains **zero** `spike` references; no mypy/ruff/coverage/CI/Makefile config exists in the repo | Informational | `cdk diff` retained as a no-op proof only |
| 2026-08-12 | sdd-architect | The env-var rename is a genuine breaking change to the human's untracked local environment; `.spike_cache/` holds real state (`seen.json` 706 B, `cards.json` 11 KB, `embeddings.json` 45 KB) | **Medium** | Human-owned Tasks H1-H3; cost of a miss quantified (~$0.01) in contract §9 |
| | sdd-test-writer | | | |
| | sdd-executor | | | |
| | sdd-auditor | | | |

## Close-out checklist (for the auditor)

- [ ] All 5 gates (G1-G5) run, with exact outputs pasted into this file
- [ ] 145/145 tests pass; the 3 retained test IDs appear verbatim in `-v` output
- [ ] `git status` shows 7 renames (`R`), 2 deletions (`D`), 0 new files
- [ ] Diff contains no assertion change, no branch change, no default-value change
- [ ] `specs/` diff is exactly one character (the FU1 checkbox)
- [ ] `uv.lock` diff is empty
- [ ] Human confirms Tasks H1-H3 done and `seen.json` still has its entries
- [ ] FU-A and FU-B carried forward into the next spec's backlog

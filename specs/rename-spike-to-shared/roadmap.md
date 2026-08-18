# Roadmap: rename-spike-to-shared

## Sequencing note (read first)

Phases 1-3 are **one atomic change**. The moment `git mv src/spike src/shared`
runs, every absolute importer is broken and the suite cannot even collect. That
is expected and correct — do **not** try to keep the tree green between Phase 1
and Phase 3, do not add a temporary `src/spike/__init__.py` shim, and do not
commit at a phase boundary. There is exactly one commit, validated in Phase 4.

This spec has no TDD red/green cycle in the usual sense: the tests are not new,
they are *repointed*. The 145-test suite is itself the regression harness, and
"green with an unchanged test count" is the primary evidence. The test-writer's
job here is verification of the gates, not authoring new tests (contract §7
forbids new test files).

---

## Phase 1: Move and prune the package

**Goal**: `src/shared/` exists with 7 modules, history intact; the two retired
files are gone; the package's own docstrings no longer apologize for the name.
**Dependencies**: None
**Estimated complexity**: Low

1. `git mv src/spike src/shared` (never a filesystem `mv` + `git add` — rename
   detection and `git log --follow` depend on this).
2. `git rm run_spike.py` and `git rm src/shared/pipeline.py` (contract §4.1).
3. Rewrite `src/shared/__init__.py`'s docstring to the pinned text
   (contract §5).
4. Rewrite `src/shared/config.py`'s docstring to the pinned text — the
   "Despite the name…" framing is deleted outright (contract §5).
5. Rename the four env keys and the cache-dir default in
   `src/shared/config.py` (contract §3), plus the `spike`-wording comment on
   line 47.
6. Fix the one remaining prose line in `src/shared/retrieval.py:3`.

## Phase 2: Repoint production importers

**Goal**: Plane A, the AgentCore entrypoint and both surviving CLI entrypoints
import from `shared`.
**Dependencies**: Phase 1
**Estimated complexity**: Low

1. Repoint the 8 `src/curation/` modules (14 import statements) per contract
   §1.1: `composite`, `dynamo`, `interfaces`, `local`, `nodes`, `state`,
   `summary`, `tavily`.
2. Rename the module alias `spike_config` → `shared_config` in
   `curation/dynamo.py` and `curation/summary.py`, including the 3 attribute
   uses (`dynamo.py:31`, `summary.py:74,75`). **Keep attribute access on the
   module object** — do not convert to `from shared.config import X`, which
   would silently defeat the price-monkeypatch test (contract §2.1).
3. Repoint `runtime_app.py:42`, `run_curation.py:31-32`, `run_chat.py:18-19`.
4. Update `run_chat.py`'s user-facing message to point at `run_curation.py`
   instead of the deleted `run_spike.py` (contract §5) and its docstring.
5. Sweep the comment/docstring references in `curation/__init__.py`,
   `curation/config.py`, `dynamo.py`, `local.py`, `nodes.py`, `state.py`,
   `summary.py`, `tavily.py` (contract §5 table).

## Phase 3: Repoint tests, config files and living docs

**Goal**: The suite collects again; every operator-facing surface uses the new
names; the historical record is untouched.
**Dependencies**: Phase 2
**Estimated complexity**: Medium (breadth, not difficulty — this is where a
missed reference is most likely)

1. Repoint the 10 import statements across `tests/conftest.py`,
   `test_bedrock_usage.py`, `test_dynamo_store.py`, `test_graph.py`,
   `test_local_store.py`.
2. Repoint `tests/test_run_summary.py:87-88` to
   `summary_module.shared_config` — attribute path only; the values and the
   `pytest.approx(12.0)` assertion do not change.
3. Sweep test comments/docstrings (contract §5), **leaving the 3 retained
   `def test_…` names untouched** (contract §7 G2).
4. Update `.env.example` (3 keys + header), `.gitignore`, `.dockerignore`
   (`.spike_cache/` → `.ai_radar_cache/`), and `pyproject.toml`'s
   `description` prose.
5. Update `README.md`: the ~10 reference lines, the `src/spike/*.py` table
   paths in the Phase 0 section, removal of the `uv run run_spike.py`
   commands, the historical-verification key names per contract §6.1, and a
   new caveat that the live image reads the old keys until redeployed
   (contract §12).
6. Update `CLAUDE.md`: the layout block, the `run_spike.py` command, the
   `.spike_cache` mentions, and the "Deferred" list — FU1 is no longer
   deferred.
7. Update `.claude/agents/sdd-architect.md:16` (`src/spike/` → `src/shared/`).
8. Tick the FU1 checkbox in `specs/run-observability/tasks.md` to `[x]` —
   **one character; nothing else in `specs/` or `docs/` changes.**

## Phase 4: Validate

**Goal**: Prove zero behavioral change and zero missed references.
**Dependencies**: Phase 3
**Estimated complexity**: Low

1. Sweep `__pycache__` so stale bytecode cannot mask a missed import.
2. Run gates **G1-G4** (contract §7) and record the exact output of each.
3. Run gate **G5** (import smoke) — the only check covering `shared/chat.py`,
   `shared/retrieval.py` and `run_chat.py`.
4. `uv run pytest tests/` → assert **145 passed**, identical to the
   pre-rename baseline measured 2026-08-12.
5. Confirm the portability regression check is green:
   `test_curation_modules_do_not_import_aws_sdk_or_bedrock_agentcore`.
6. `cdk synth` + `cdk diff` on all four stacks → no differences.
7. `git log --follow src/shared/config.py` → pre-rename history visible;
   `git status` shows renames, not add/delete pairs.
8. Review the diff for scope creep: every hunk must be an import path, the
   alias, a comment, an env key, a doc line, or a deletion. Any assertion or
   code-path edit is a **stop-and-flag**, not a fix.
9. Hand the human the manual migration steps (contract §12) — `mv
   .spike_cache .ai_radar_cache` and the three `.env` key renames.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A missed import in `shared/chat.py`, `shared/retrieval.py` or `run_chat.py` ships green — **no test imports them** | Med | Med (Plane B broken until a human runs the REPL) | Gate G5 import smoke, mandated in Phase 4.3 |
| Human's `.spike_cache/` is never moved → dedup history orphaned | **High** (easy to forget; it is gitignored and invisible in review) | Low-Med (~$0.01 re-summarization + duplicate cards) | Contract §12 manual runbook; called out in tasks.md, audit.md and the README; `dynamo` backend is immune |
| Scope creep — executor "tidies" while renaming (e.g. converts `shared_config.X` attribute access to a `from`-import, or deletes `bedrock.summarize()` as newly-dead) | Med | **High** (silently defeats a shipped monkeypatch test / deletes shipped coverage) | Contract §2.1 and §4.2 pin both explicitly; Phase 4.8 diff review; stop-and-flag rule |
| A retained `spike`-named test function is "helpfully" renamed | Med | Med (dangles `specs/run-observability/audit.md:142`, `specs/curation-graph/audit.md:36`) | Gate G2 pins the count at exactly 3 and enumerates them |
| Over-editing `specs/**` — retro-fixing historical spec text | Med | Med (falsifies shipped audit evidence) | Gate G4 (`git diff --stat specs/ docs/` = 1 file, 1 line) |
| `git mv` skipped → history broken | Low | Med (`git log --follow` stops at the rename) | Phase 1.1 mandates it; Phase 4.7 verifies |
| Stale `__pycache__` masks a missed import locally | Low | Low | Mandatory sweep, Phase 4.1 |
| Live image drifts from docs (reads `SPIKE_*`, docs say `AI_RADAR_*`) | **Certain** until redeploy | Low (no key is currently set on the runtime; it runs on code defaults) | Explicit README caveat + optional `agentcore deploy` step, contract §12 |
| Env-var rename silently no-ops because old and new values are identical (`8`/`5`/`4`) | High | Low today, Med later (a future edit to a stale key does nothing) | §12 step 2 removes the stale keys; `.env.example` is the diff reference |
| Renaming breaks the AgentCore container build | Low | High | `Dockerfile` copies `src/` wholesale and names no subpackage (contract §10); `tests/test_dockerfile.py` asserts nothing about `spike` |
| Merge conflict with in-flight work | Low | Low | Single atomic commit; no other spec is in flight |

---

## File Change Map

**Renamed (7, via `git mv src/spike src/shared`)**
- `src/spike/__init__.py` → `src/shared/__init__.py` — RENAME + docstring rewrite
- `src/spike/config.py` → `src/shared/config.py` — RENAME + docstring rewrite + 4 env keys + cache default
- `src/spike/bedrock.py` → `src/shared/bedrock.py` — RENAME only (content untouched)
- `src/spike/cards.py` → `src/shared/cards.py` — RENAME only
- `src/spike/feeds.py` → `src/shared/feeds.py` — RENAME only
- `src/spike/chat.py` → `src/shared/chat.py` — RENAME only
- `src/spike/retrieval.py` → `src/shared/retrieval.py` — RENAME + 1 docstring line

**Deleted (2)**
- `run_spike.py` — DELETE — legacy Phase-0 entrypoint, superseded by `run_curation.py`
- `src/spike/pipeline.py` — DELETE — zero callers once `run_spike.py` is gone

**Modified — production code (11)**
- `src/curation/__init__.py` — MODIFY — docstring wording
- `src/curation/composite.py` — MODIFY — 1 import
- `src/curation/config.py` — MODIFY — 2 comment lines
- `src/curation/dynamo.py` — MODIFY — 3 imports + alias + 1 attribute + 1 docstring
- `src/curation/interfaces.py` — MODIFY — 2 imports
- `src/curation/local.py` — MODIFY — 3 imports + 3 docstrings
- `src/curation/nodes.py` — MODIFY — 2 imports + 1 docstring
- `src/curation/state.py` — MODIFY — 2 imports + 1 comment
- `src/curation/summary.py` — MODIFY — 1 import + alias + 2 attributes + 2 docstrings
- `src/curation/tavily.py` — MODIFY — 1 import + 1 docstring
- `runtime_app.py` — MODIFY — 1 import
- `run_curation.py` — MODIFY — 2 imports
- `run_chat.py` — MODIFY — 2 imports + docstring + 1 user-facing message

**Modified — tests (7)**
- `tests/conftest.py` — MODIFY — 2 imports + 4 docstring lines
- `tests/test_bedrock_usage.py` — MODIFY — 2 imports + 5 docstring lines
- `tests/test_dynamo_store.py` — MODIFY — 1 import
- `tests/test_graph.py` — MODIFY — 3 imports + 2 comments (test name at :201 **kept**)
- `tests/test_local_store.py` — MODIFY — 2 imports + 4 comments (test name at :104 **kept**)
- `tests/test_run_summary.py` — MODIFY — 2 attribute paths (test name at :86 **kept**)
- `tests/test_tavily.py` — MODIFY — 1 comment

**Modified — config (4)**
- `pyproject.toml` — MODIFY — `description` prose only; deps and `uv.lock` untouched
- `.env.example` — MODIFY — 3 env keys + header line
- `.gitignore` — MODIFY — `.spike_cache/` → `.ai_radar_cache/`
- `.dockerignore` — MODIFY — `.spike_cache/` → `.ai_radar_cache/`

**Modified — living docs (3)**
- `README.md` — MODIFY — ~10 reference lines, Phase 0 table paths, removed `run_spike.py` commands, new live-image caveat
- `CLAUDE.md` — MODIFY — layout block, commands, cache paths, "Deferred" list (FU1 done)
- `.claude/agents/sdd-architect.md` — MODIFY — line 16 example path

**Modified — tracker (1, one character)**
- `specs/run-observability/tasks.md` — MODIFY — FU1 checkbox `[ ]` → `[x]`

**Explicitly NOT changed**
- `Dockerfile`, `infra/**`, `uv.lock`, `tests/test_dockerfile.py`,
  `tests/test_infra*.py`, `tests/test_runtime_app.py`, `tests/test_composite.py`,
  `docs/**`, all `specs/**` except the one checkbox above
- `.env` and `.spike_cache/` — human-owned, untracked/gitignored (contract §12)

**Net**: 7 renamed, 2 deleted, 26 modified, **0 created**.

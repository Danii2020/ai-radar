# Tasks: rename-spike-to-shared

## Legend
- [ ] Not started
- [x] Completed
- [~] In progress
- [!] Blocked

## Rules for the executor (read before Task 1.1)

- **One atomic commit.** The tree is intentionally broken between Task 1.1 and
  Phase 3. Do not commit mid-way, do not add a `src/spike/` compatibility
  shim, do not try to keep the suite green until Phase 4.
- **Use `git mv` / `git rm`**, never a filesystem `mv` + `git add`. Rename
  detection and `git log --follow` depend on it.
- **Zero behavioral change.** Every hunk must be an import path, the
  `spike_config`→`shared_config` alias, a comment/docstring, an env-key
  string, a doc line, or one of the two deletions. If you find yourself
  editing an assertion, a branch, or a default value: **STOP and flag it**.
  Do not "fix" it silently.
- **Two traps that are pinned in contract.md and must not be "tidied":**
  (a) `curation/summary.py` must keep reading prices as
  `shared_config.HAIKU_*` **attribute access on the module object** — a
  `from shared.config import …` rewrite silently defeats a shipped test;
  (b) `shared/bedrock.summarize()` stays, even though it loses its last
  production caller.
- **Do not rename the 3 `spike`-named test functions** (Tasks 3.3/3.4/3.5).
  Shipped audits cite them by name.

---

## Phase 1: Move and prune the package

- [ ] Task 1.1: `git mv src/spike src/shared` — 8 files move; intra-package
      relative imports need no edits — `src/shared/`
- [ ] Task 1.2: `git rm run_spike.py` (legacy Phase-0 entrypoint, superseded
      by `run_curation.py`) — `run_spike.py`
- [ ] Task 1.3: `git rm src/shared/pipeline.py` (zero callers after 1.2; see
      contract §4.1 for the justification the auditor will check) —
      `src/shared/pipeline.py`
- [ ] Task 1.4: Replace `src/shared/__init__.py`'s docstring with the pinned
      text in contract §5 (describes the package's real cross-plane +
      Plane-B role) — `src/shared/__init__.py`
- [ ] Task 1.5: Replace `src/shared/config.py`'s docstring with the pinned
      text in contract §5 — delete the "Despite the name, this module also
      holds shared cross-plane…" framing entirely; it exists only to
      apologize for the old name — `src/shared/config.py`
- [ ] Task 1.6: Rename the 4 env keys in `src/shared/config.py`:
      `SPIKE_TOP_K`→`AI_RADAR_TOP_K` (:45),
      `SPIKE_MAX_ITEMS`→`AI_RADAR_MAX_ITEMS` (:48),
      `SPIKE_PER_FEED`→`AI_RADAR_PER_FEED` (:49),
      `SPIKE_CACHE_DIR`→`AI_RADAR_CACHE_DIR` + default `.spike_cache` →
      `.ai_radar_cache` (:62). **Constant names and default values are
      unchanged** — `src/shared/config.py`
- [ ] Task 1.7: Reword the comment at `src/shared/config.py:47` ("keeps the
      spike cheap and fast" → "keeps each run cheap and fast") —
      `src/shared/config.py`
- [ ] Task 1.8: Reword `src/shared/retrieval.py:3` ("fine for the spike's
      small corpus" → "fine for the current small corpus") —
      `src/shared/retrieval.py`

## Phase 2: Repoint production importers

- [ ] Task 2.1: Repoint `from spike.feeds import RawItem` →
      `from shared.feeds import RawItem` — `src/curation/composite.py`
- [ ] Task 2.2: Repoint 3 imports, rename the alias to `shared_config`, update
      the `spike_config.AWS_REGION` use at :31, and fix the
      `spike.bedrock.bedrock_client()` docstring at :5 —
      `src/curation/dynamo.py`
- [ ] Task 2.3: Repoint 2 imports — `src/curation/interfaces.py`
- [ ] Task 2.4: Repoint 3 imports; update the 3 docstrings at :3 (points at
      the now-deleted `src/spike/pipeline.py` — use the wording in contract
      §5), :24, and :39 (`.spike_cache/` → `.ai_radar_cache/`) —
      `src/curation/local.py`
- [ ] Task 2.5: Repoint 2 imports + the module docstring at :5 —
      `src/curation/nodes.py`
- [ ] Task 2.6: Repoint 2 imports + the comment at :11 —
      `src/curation/state.py`
- [ ] Task 2.7: Repoint the import, rename the alias to `shared_config`, and
      update the 2 attribute reads at :74-75 plus the docstring at :68-69.
      **Keep module-attribute access** (contract §2.1) —
      `src/curation/summary.py`
- [ ] Task 2.8: Repoint 1 import + the docstring at :4 —
      `src/curation/tavily.py`
- [ ] Task 2.9: Reword the module docstring ("Phase 0 spike curation loop" →
      "Phase 0 curation loop") — `src/curation/__init__.py`
- [ ] Task 2.10: Update the 2 comment lines at :89-90 (`spike/config.py` →
      `shared/config.py`) — `src/curation/config.py`
- [ ] Task 2.11: Repoint `from spike import config` at :42 —
      `runtime_app.py`
- [ ] Task 2.12: Repoint 2 imports at :31-32 — `run_curation.py`
- [ ] Task 2.13: Repoint 2 imports at :18-19; update the module docstring
      (:2, :5); **change the user-facing message at :27** from
      `uv run run_spike.py` to `uv run run_curation.py` — this file has zero
      test coverage, so only Task 4.4's import smoke and review protect it —
      `run_chat.py`

## Phase 3: Repoint tests, config and living docs

- [ ] Task 3.1: Repoint 2 imports (:26, :97) + 4 docstring lines (:5 — now
      references `run_curation.py`, :6, :12, :86, :88) — `tests/conftest.py`
- [ ] Task 3.2: Repoint 2 imports (:23-24) + 5 docstring lines
      (:1, :5, :10, :14, :15) — `tests/test_bedrock_usage.py`
- [ ] Task 3.3: Repoint 1 import (:26) — `tests/test_dynamo_store.py`
- [ ] Task 3.4: Repoint 3 imports (:32, :143, :300) + 2 comments (:199, :228,
      which reference the deleted `spike.pipeline.run()`).
      **Do NOT rename `test_graph_matches_spike_pipeline_logic_for_same_inputs`
      at :201** — `tests/test_graph.py`
- [ ] Task 3.5: Repoint 2 imports (:15, :173) + 4 comments (:103, :125, :144,
      :170). **Do NOT rename
      `test_upsert_writes_seen_sorted_and_cards_batch_matching_spike_save_shape`
      at :104** — `tests/test_local_store.py`
- [ ] Task 3.6: Repoint the 2 `summary_module.spike_config` attribute paths at
      :87-88 to `summary_module.shared_config`. **Attribute path only** — the
      `2.0`/`10.0` values and the `pytest.approx(12.0)` assertion do not
      change. **Do NOT rename
      `test_estimate_bedrock_cost_usd_reads_prices_from_spike_config_at_call_time`
      at :86** — `tests/test_run_summary.py`
- [ ] Task 3.7: Update the comment at :62 (`spike.feeds._clean` →
      `shared.feeds._clean`) — `tests/test_tavily.py`
- [ ] Task 3.8: Rename the 3 keys (:21-23) and rewrite the header line at :1
      ("AI Radar — Phase 0 spike configuration.") — `.env.example`
- [ ] Task 3.9: `.spike_cache/` → `.ai_radar_cache/` — `.gitignore`
- [ ] Task 3.10: `.spike_cache/` → `.ai_radar_cache/` — `.dockerignore`
- [ ] Task 3.11: Update the `description` field (drop "(Phase 0 spike)").
      **Do not touch dependencies, groups, or `[tool.uv]`; do not run
      `uv add`/`uv sync`; `uv.lock` must show no diff** — `pyproject.toml`
- [ ] Task 3.12: Update `README.md`:
      - remove the `uv run run_spike.py` / `--force` command lines (~:566-567)
      - `src/spike/*.py` → `src/shared/*.py` in the two Phase-0 tables
        (~:579-582, :592-594), rewriting the `Dedup | src/spike/pipeline.py`
        row since that file no longer exists
      - `.spike_cache` → `.ai_radar_cache` (~:51, :580, :584, :592)
      - `SPIKE_MAX_ITEMS`/`SPIKE_PER_FEED` → `AI_RADAR_*` (~:192, :214, :391,
        :611), including the "Verified 2026-07-28" block per contract §6.1
      - add the contract §12 caveat: the deployed image reads the old keys
        until `agentcore deploy` is re-run
      - keep the `## Phase 0 spike (reference baseline)` heading and its prose
        — correct English for the historical prototype (contract §7 G3)
      — `README.md`
- [ ] Task 3.13: Update `CLAUDE.md`: the layout block (:63 `run_spike.py`
      line removed, :66 `src/spike/` → `src/shared/`), the `uv run
      run_spike.py` command (:22), `.spike_cache` (:25), and the "Deferred"
      list (:141-143) — FU1 is done, so that clause is removed and replaced
      with a pointer to this spec — `CLAUDE.md`
- [ ] Task 3.14: `src/spike/` → `src/shared/` at :16 —
      `.claude/agents/sdd-architect.md`
- [ ] Task 3.15: Tick the FU1 checkbox `- [ ]` → `- [x]`. **One character.
      Change nothing else in `specs/` or `docs/`** —
      `specs/run-observability/tasks.md`

## Phase 4: Validate

- [ ] Task 4.1: Sweep stale bytecode so it cannot mask a missed import:
      `find . -name __pycache__ -not -path "./.venv/*" -prune -exec rm -rf {} +`
- [ ] Task 4.2: Run gate **G1** (code+config hard zero) and paste the output
      (must be empty) into `audit.md` —
      `grep -rin "spike" src/ infra/ *.py pyproject.toml Dockerfile .dockerignore .gitignore .env.example`
- [ ] Task 4.3: Run gates **G2** (tests: exactly the 3 enumerated `def test_…`
      lines), **G3** (living docs: zero path/var/command references) and
      **G4** (`git diff --stat specs/ docs/` = 1 file, 1 line); record all
      three outputs in `audit.md` — contract §7
- [ ] Task 4.4: Run gate **G5** import smoke — the only check that exercises
      `shared/chat.py`, `shared/retrieval.py` and `run_chat.py`, none of which
      any test imports — contract §7
- [ ] Task 4.5: `uv run pytest tests/` → **145 passed**, same as the
      2026-08-12 baseline; confirm the 3 retained test IDs still appear in
      `-v` output — `tests/`
- [ ] Task 4.6: Confirm the portability regression check is green:
      `uv run pytest tests/test_graph.py::test_curation_modules_do_not_import_aws_sdk_or_bedrock_agentcore -v`
      — `tests/test_graph.py`
- [ ] Task 4.7: `uv run --group infra cdk synth --app "python infra/app.py"`
      then `cdk diff` on `AiRadarCardStore AiRadarRuntimeRole AiRadarSchedule
      AiRadarBudget` → "There were no differences" for all four — `infra/`
- [ ] Task 4.8: Verify history: `git log --follow src/shared/config.py | head`
      shows pre-rename commits, and `git status` reports renames (`R`) rather
      than add/delete pairs for the 7 moved files
- [ ] Task 4.9: Confirm `git diff uv.lock` is empty and `git diff
      pyproject.toml` touches only the `description` line
- [ ] Task 4.10: **Scope-creep review** — walk the full diff and confirm every
      hunk is an import path, the alias, a comment/docstring, an env key, a
      doc line, or one of the two deletions. Flag anything else to the human
      rather than keeping it

## Human-owned migration (executor CANNOT do these)

`.env` is untracked and `.spike_cache/` is gitignored — both live only on the
human's machine. Precedent: the SNS subscription click in
`specs/run-observability`.

- [ ] Task H1: `mv .spike_cache .ai_radar_cache` — **do this before the next
      `uv run run_curation.py`**, or the JSON dedup cache is orphaned and up
      to 8 already-seen items get re-summarized (~$0.01 of real Bedrock spend
      plus duplicate cards). The `dynamo` backend is unaffected
- [ ] Task H2: Rename the 3 stale keys in the local `.env`:
      `SPIKE_MAX_ITEMS`→`AI_RADAR_MAX_ITEMS`, `SPIKE_PER_FEED`→
      `AI_RADAR_PER_FEED`, `SPIKE_TOP_K`→`AI_RADAR_TOP_K`. Values are
      unchanged (8/5/4); diff against the updated `.env.example` to confirm
- [ ] Task H3: Verify with the contract §12 snippet — prints `CACHE_DIR`,
      the three caps, and the number of remembered URLs (non-zero proves H1
      worked)
- [ ] Task H4 (**optional**): `agentcore deploy` to rebuild the image with the
      renamed package. Not required for correctness — the deployed container
      is self-contained and keeps working. Until it runs, any `agentcore
      configure --env` re-targeting must use the **old** `SPIKE_*` keys
      (neither key is currently set on the runtime, so there is no live
      effect today)

## Blocked Items

[None]

## Notes

- **This spec creates zero new files.** 7 renamed, 2 deleted, 26 modified. If
  a new module or test file appears in the diff, that is scope creep.
- **The suite is the regression harness.** No new tests are authored; the
  test-writer's role is verifying gates G1-G5, not adding coverage.
- **Why `AI_RADAR_*` and not `SHARED_*`:** an env prefix must never encode a
  directory name — that is precisely the bug being fixed here, and `SHARED_*`
  would repeat it one rename later. `CURATION_*` survives because it names a
  *plane* (stable ubiquitous language), not a folder. Recorded in contract §3
  so it is not re-litigated.
- **Why `pipeline.py` dies but `bedrock.summarize()` lives:** the first has
  zero callers and its behavior is pinned by an inline-replication test; the
  second still has shipped test coverage in `tests/test_bedrock_usage.py`.
  Contract §4.
- **Deliberately deferred, do not preempt:** splitting Plane B
  (`chat.py`/`retrieval.py`) into its own package. That belongs to
  `docs/architecture-principles.md` §2's monorepo move (`apps/curation`,
  `apps/api`, `apps/web`, `packages/contracts`), done once and deliberately.
  `shared/` is a precursor to it, not a substitute.
- **FU2 (`pydantic-settings` migration) is untouched here** by explicit
  instruction. `shared/config.py` keeps plain `os.getenv`. FU2 gets its own
  spec after this one ships end-to-end.

## Follow-ups / Not This Spec

- [ ] **FU-A — No automated coverage for Plane B.** `shared/chat.py`,
      `shared/retrieval.py` and `run_chat.py` are imported by **no test in the
      145-test suite**; gate G5 is a one-off manual command, not a standing
      guard. A future spec should add a minimal offline smoke test (stubbed
      `bedrock_client`, like `tests/test_bedrock_usage.py` already does) so
      Plane B cannot break silently. Not done here because contract §6 forbids
      new files in a pure rename.
- [ ] **FU-B — `bedrock.summarize()` has no production caller** after this
      spec. It is retained for its test coverage (contract §4.2), but a future
      spec should decide deliberately: keep it as a documented simple-path
      helper, or remove it together with its tests.

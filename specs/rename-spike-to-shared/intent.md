# Intent: rename-spike-to-shared

## Problem Statement

`src/spike/` is a Phase-0 holdover whose name is now actively false. Despite
being called a "spike", it is **live production code running in the deployed
AgentCore image today**:

- `spike.bedrock`, `spike.cards`, `spike.feeds`, `spike.config` are imported by
  Plane A (`curation.composite`, `curation.dynamo`, `curation.interfaces`,
  `curation.local`, `curation.nodes`, `curation.state`, `curation.summary`,
  `curation.tavily`, `runtime_app.py`, `run_curation.py`).
- `spike.chat` and `spike.retrieval` **are** Plane B in its entirety — there is
  no replacement module, and `run_chat.py` is their only entrypoint.
- Only `spike.pipeline` is genuinely superseded (by `curation/graph.py`); its
  sole caller is the legacy `run_spike.py`.

Who is affected: every future reader and every future spec. The name has
already cost real review time — this work exists because a reviewer of
`specs/run-observability/contract.md` asked "why does this build on
`spike/bedrock.py` if `spike` was just the Phase 0 spike?". The answer
("because it is load-bearing, not dead code") required a 30-line explanatory
footnote in `src/spike/config.py`'s docstring and a tracked follow-up. The
lie also leaks into the operator surface: the env vars `SPIKE_MAX_ITEMS`,
`SPIKE_PER_FEED`, `SPIKE_TOP_K`, `SPIKE_CACHE_DIR` and the on-disk
`.spike_cache/` directory are all documented in `README.md` as current
production knobs for a deployed agent.

This is **FU1**, tracked verbatim in `specs/run-observability/tasks.md`
under "Follow-ups / Not This Spec", deliberately deferred out of that spec
because it is pure churn with no functional payload.

## Goals

1. Rename the package `src/spike/` → `src/shared/`, repointing every absolute
   import across `src/curation/`, the root entrypoints, and `tests/`.
2. Shed the "spike" name from the **operator surface** too: rename the four
   `SPIKE_*` environment variables and the `.spike_cache/` default directory,
   so no knob a human types still carries the dead name.
3. Retire the genuinely superseded Phase-0 code path: delete `run_spike.py`
   and the now-callerless `spike/pipeline.py`.
4. Rewrite the docstrings/comments that only existed to *apologize* for the
   old name (chiefly `src/spike/config.py`'s "Despite the name, this module
   also holds shared cross-plane…" framing), which become unnecessary once
   the name is honest.
5. Update every **living** doc (`README.md`, `CLAUDE.md`,
   `.claude/agents/sdd-architect.md`, `.env.example`, `pyproject.toml`) while
   leaving the **historical record** (`specs/**`,
   `docs/app-design-on-agentcore.md`) untouched.
6. Change **no behavior**: the same 145 tests pass, with edits confined to
   import paths, symbol/attribute renames, comments, and env-var key names —
   never to an assertion or a code path.

## Success Criteria

- [ ] `uv run pytest tests/` → **145 passed**, the same count as the
      pre-rename baseline (measured 2026-08-12), with zero assertions changed.
- [ ] **Gate G1 (code + config, hard zero)**: `grep -rin "spike" src/ infra/
      *.py pyproject.toml Dockerfile .dockerignore .gitignore .env.example`
      returns **0 lines**.
- [ ] **Gate G2 (tests, bounded)**: `grep -rin "spike" tests/` returns
      **exactly 3 lines**, and all 3 are the `def test_…` names enumerated in
      contract.md §7. A 4th occurrence fails the gate.
- [ ] **Gate G3 (living docs, zero path/var references)**: `grep -rn
      "src/spike\|spike\.\|run_spike\|SPIKE_\|\.spike_cache" README.md
      CLAUDE.md .claude/agents/` returns **0 lines**. Remaining bare-word
      occurrences are permitted only as the historical English phrase
      "Phase 0 spike", enumerated in contract.md §7.
- [ ] **Gate G4 (history frozen)**: `git diff --stat specs/ docs/` shows
      exactly one changed file (`specs/run-observability/tasks.md`) with
      exactly one changed line (the FU1 checkbox `[ ]` → `[x]`).
- [ ] **Import smoke**: all 7 `shared.*` modules and both surviving root
      entrypoints (`run_chat.py`, `run_curation.py`) import cleanly — this
      catches the untested modules (`shared/chat.py`, `shared/retrieval.py`,
      `run_chat.py`) that no test in the suite exercises.
- [ ] `git log --follow src/shared/config.py` shows the pre-rename history.
- [ ] The portability gate still passes:
      `tests/test_graph.py::test_curation_modules_do_not_import_aws_sdk_or_bedrock_agentcore`
      is green (regression check — unaffected in principle, re-confirmed in fact).
- [ ] `uv run --group infra cdk synth --app "python infra/app.py"` still
      succeeds for all four stacks, and `cdk diff` reports no differences
      (proves this touched no infrastructure).
- [ ] The human has run the local migration steps (rename `.env` keys, `mv`
      the cache directory) so no cached dedup state is orphaned.

## Non-Goals

- **Not splitting Plane B out.** `chat.py` and `retrieval.py` stay alongside
  the cross-plane modules under `shared/`, exactly as they sit today. Carving
  Plane B into its own package belongs to the deliberate monorepo move in
  `docs/architecture-principles.md` §2 (`apps/curation`, `apps/api`,
  `apps/web`, `packages/contracts`). This spec must not preempt that layout.
- **Not deleting `bedrock.summarize()`.** After `pipeline.py` is deleted it
  has no production caller, but it retains test coverage
  (`tests/test_bedrock_usage.py`). Removing it would delete shipped tests —
  scope creep. See contract.md §4.
- **Not renaming the 3 test functions** whose names contain `spike`. Shipped
  audit tables cite them verbatim (`specs/run-observability/audit.md:142`,
  `specs/curation-graph/audit.md:36`); renaming would dangle those references.
- **Not touching `specs/**`** beyond the single FU1 checkbox, nor
  `docs/app-design-on-agentcore.md`. Those are a historical record of what was
  decided and verified at the time, not living documentation.
- **No `pydantic-settings`.** FU2 is a separate, later spec; this one stays a
  narrow rename. `shared/config.py` keeps plain `os.getenv`.
- **No new dependency, no new test file, no new module.** The only additions
  to the tree are the renamed files themselves.
- Not renaming `curation/config.py`'s `CURATION_*` / `CARD_*` env vars.

## Constraints

- **Zero behavioral change in code.** Every diff hunk must be an import path,
  a symbol/attribute rename, a comment/docstring, an env-var key string, or a
  deletion of the two retired files. If the executor or test-writer finds
  itself editing an assertion or a code path, that is scope creep — it must
  stop and flag, not proceed silently.
- **`git mv`, not filesystem rename**, so rename detection survives and
  `git log --follow` keeps working on the moved files.
- **Two deletions are a real (small) functional change**, and are in scope by
  explicit human decision: `run_spike.py` (a documented `README.md` command
  disappears) and `src/spike/pipeline.py`.
- **The env-var rename breaks the human's local environment.** Their live
  `.env` sets `SPIKE_MAX_ITEMS` / `SPIKE_PER_FEED` / `SPIKE_TOP_K`, and
  `.spike_cache/` holds real cached state (`seen.json`, `cards.json`,
  `embeddings.json`). Migration is a **manual human step** — the executor
  cannot edit an untracked local `.env` or move a gitignored directory on the
  human's behalf. A missed migration silently orphans the dedup cache and
  costs real Bedrock spend on re-summarization.
- **The live deployment lags the rename.** Four stacks are deployed and the
  agent image is running `run-observability` code that reads `SPIKE_*`. Until
  `agentcore deploy` is re-run, the live image honors the *old* names while
  `README.md` documents the new ones. This must be stated, not glossed.
- The portability guarantee (`src/curation/{nodes,graph,state,summary,
  metrics}.py` must not import `boto3`/`botocore`/`bedrock_agentcore`) is
  about AWS SDK imports, not package paths, so it is untouched in principle —
  but it is re-verified as a regression check, since those files all import
  `shared.*` either way.
- Python 3.11+, `uv` only. `pyproject.toml` keeps `[tool.uv] package = false`;
  `src/` stays a `sys.path`-inserted layout, not an installed package.

## Prior Art

- `specs/run-observability/tasks.md` — FU1, the verbatim source of this work,
  including the reasoning for why it was deferred out of that spec.
- `docs/architecture-principles.md` §2 — the future monorepo layout this
  rename must be compatible with but must not preempt; also the "no
  speculative or dead code" stance that justifies deleting `pipeline.py`.
- `specs/run-observability/intent.md` — the pinned `grep -rn "boto3\|botocore"`
  portability gate, the model for this spec's grep-based acceptance gates
  (here: a reference-count gate rather than a forbidden-import gate).
- `specs/eventbridge-schedule` / `specs/run-observability` — precedent for a
  spec that ends with a **manual human runbook step** (the SNS subscription
  click) that no executor can perform.
- `src/curation/local.py` — precedent for the "reproduce Phase 0 behavior
  exactly" parity framing whose reference file (`pipeline.py`) this spec
  deletes; the behavioral record survives in
  `tests/test_graph.py::test_graph_matches_spike_pipeline_logic_for_same_inputs`,
  which replicates the logic inline rather than importing it.

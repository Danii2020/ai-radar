# Tasks: pydantic-settings-config

## Legend
- [ ] Not started
- [x] Completed
- [~] In progress
- [!] Blocked

Every task cites the audit ID(s) it satisfies. Run `uv run pytest tests/` after
every phase — the 145 pre-existing tests are the safety net for this migration,
so a red suite mid-phase means *stop and fix*, never *adjust the test*.

---

## Phase 1: Dependency + characterization tests

- [x] Task 1.1: `uv add pydantic-settings` — verify it lands in
      `[project].dependencies` (main group, **not** `dev`) — `pyproject.toml`
      *(R10, C16)* — done; `pydantic-settings>=2.14.2` added to
      `[project].dependencies`.
- [x] Task 1.2: `git diff pyproject.toml uv.lock` — confirm only the
      `pydantic-settings` entry changed and that `pydantic` (2.13.4),
      `python-dotenv` and `typing-inspection` versions did **not** move —
      `uv.lock` *(R11, G6)* — confirmed: only the `pydantic-settings` member
      added to the root package's `dependencies`/`requires-dist` lists; no
      other package entry changed.
- [x] Task 1.3: Confirm `uv sync --frozen --no-dev` (exactly what `Dockerfile`
      runs) installs `pydantic-settings` — this is the deploy-safety check,
      not cosmetics *(R10, G5)* — confirmed via
      `uv run --no-sync python -c "import pydantic_settings"` after
      `uv sync --frozen --no-dev`; re-ran plain `uv sync` afterward to restore
      dev deps for the test suite.
- [x] Task 1.4: Create the reload harness: a fixture that snapshots
      `sys.modules`, applies `monkeypatch.setenv`/`delenv`, `importlib.reload()`s
      the target config module, and restores the original module object
      afterwards so later tests see pristine config —
      `tests/test_config.py` *(T1)* — pre-existing (red-phase test file).
- [x] Task 1.5: Characterization — 26-row env-var → constant table (11 shared,
      15 curation), asserted against the **current** `os.getenv` code —
      `tests/test_config.py` *(T2, T3)* — pre-existing.
- [x] Task 1.6: Characterization — all 26 defaults with a clean environment,
      plus `FEEDS`' 6 entries and `_DEFAULT_SEEDS`' 5 seeds —
      `tests/test_config.py` *(T4, T5)* — pre-existing.
- [x] Task 1.7: Characterization — the 11 fixed constants are unmoved by
      same-named env vars — `tests/test_config.py` *(T6)* — pre-existing.
- [x] Task 1.8: Characterization — derived paths track `AI_RADAR_CACHE_DIR` —
      `tests/test_config.py` *(T7)* — pre-existing.
- [x] Task 1.9: Characterization — both list splits and every empty-string
      case: `CURATION_TAVILY_SEEDS=` → `[]` (**not** the defaults), domain CSVs
      → `[]`, `TAVILY_API_KEY=` → `""`, `AI_RADAR_CACHE_DIR=` → `Path(".")` —
      `tests/test_config.py` *(T8, T9, T10)* — pre-existing.
- [x] Task 1.10: Characterization — lowercase env var ignored; constants
      assignable after import — `tests/test_config.py` *(T11, T12)* —
      pre-existing.
- [x] Task 1.11: Write the two deliberate-change rows
      (`CURATION_EMIT_METRICS=1` → `True`, `=yolo` → raises) as
      `@pytest.mark.xfail(strict=True)` — they must fail now and flip in
      Phase 3 — `tests/test_config.py` *(T16, T17, C14)*
- [x] Task 1.12: `uv run pytest tests/` → green (145 + new), with the two
      `xfail`s reported as xfailed, not xpassed *(R12)* — confirmed:
      `uv run pytest tests/test_config.py -q` → 88 passed, 2 xfailed,
      5 failed (T20 flipped to passing after Task 1.1's `uv add`; the
      remaining 5 failures are the true-red validation-error/dependency-shape
      tests, expected until Phase 2/3).

---

## Phase 2: Migrate `src/shared/config.py`

- [x] Task 2.1: Add `_SharedSettings(BaseSettings)` with the 11 fields, each
      carrying an explicit `validation_alias` (no `env_prefix`), and
      `model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")`
      — `src/shared/config.py` *(C1, C3)*
- [x] Task 2.2: Instantiate `_settings = _SharedSettings()` at module level
      (import time, not lazy) — `src/shared/config.py` *(C4)*
- [x] Task 2.3: Replace the 11 `os.getenv(...)` expressions with the re-export
      block, keeping every existing explanatory comment attached to the
      constant it documents (Bedrock prices, Sonnet 4.6 upgrade note, Titan
      normalize note) — `src/shared/config.py` *(R4, R5, C5)*
- [x] Task 2.4: Keep the single `load_dotenv()` above the class; add the
      comment explaining why it survives (boto3 reads `os.environ`;
      python-dotenv's upward search; "never add a second call") —
      `src/shared/config.py` *(R3, C10)*
- [x] Task 2.5: Leave `FEEDS` and the three derived paths as plain constants
      outside the model — `src/shared/config.py` *(R6, C9)*
- [x] Task 2.6: Drop `import os`; update the module docstring to say
      `_SharedSettings` owns parsing/validation — `src/shared/config.py`
      *(C15)*
- [x] Task 2.7: `uv run pytest tests/` → green. Any failure here is a real
      regression in a consumer, not a test to edit *(R7, R8, R12)*

---

## Phase 3: Migrate `src/curation/config.py`

- [x] Task 3.1: Add `from shared import config as _shared_config  # noqa: F401`
      with the comment explaining it is imported for the `load_dotenv()`
      ordering side effect only; delete this module's own `load_dotenv()` —
      `src/curation/config.py` *(R3, C10)*
- [x] Task 3.2: Move `_DEFAULT_SEEDS` above the class body —
      `src/curation/config.py` *(C8)*
- [x] Task 3.3: Add `_CurationSettings(BaseSettings)` with the 15 fields, each
      carrying an explicit `validation_alias`, same `model_config` —
      `src/curation/config.py` *(C2, C3)*
- [x] Task 3.4: Declare `tavily_seeds` / `tavily_include_domains` /
      `tavily_exclude_domains` as `Annotated[list[str], NoDecode]` and add the
      `_split_semicolons` / `_split_commas` `mode="before"` validators.
      **`NoDecode` is mandatory** — without it pydantic-settings JSON-decodes
      complex types and `CURATION_TAVILY_SEEDS=a;b` becomes a parse error —
      `src/curation/config.py` *(C6)*
- [x] Task 3.5: Delete the `_csv()` helper and `import os` —
      `src/curation/config.py` *(C15)*
- [x] Task 3.6: Instantiate `_settings = _CurationSettings()` at module level
      and emit the 15-constant re-export block, keeping `TAVILY_API_KEY`'s
      "WRITABLE by design" comment — `src/curation/config.py` *(C4, C5, R8)*
- [x] Task 3.7: Emit the 6 fixed constants (`FEED_GSI_NAME`,
      `FEED_GSI_PARTITION`, `TAVILY_SECRET_UNSET_SENTINEL`,
      `TAVILY_SOURCE_PREFIX`, `TAVILY_CREDITS_BY_DEPTH`,
      `TAVILY_DEFAULT_CREDITS_PER_SEARCH`) with their comments verbatim, plus
      the "the Bedrock unit prices are NOT here" pointer —
      `src/curation/config.py` *(R6, C17)*
- [x] Task 3.8: Remove the `xfail(strict=True)` markers from Task 1.11's two
      rows — they must now pass — `tests/test_config.py` *(T16, T17, C14)*
- [x] Task 3.9: `uv run pytest tests/` → green, ≥145 *(R12)*

---

## Phase 4: Validation behavior + gates

- [x] Task 4.1: Error tests — `HAIKU_INPUT_USD_PER_1M=abc`,
      `CURATION_TAVILY_CREDIT_PRICE_USD=`, `AI_RADAR_MAX_ITEMS=eight` each
      raise `pydantic.ValidationError` on reload with the offending env var
      name in the message — `tests/test_config.py` *(T13, T14, T15, R9, C11)*
      — pre-existing test, now green after Phase 2/3.
- [x] Task 4.2: Multi-error test — two bad vars produce **one** exception
      naming both — `tests/test_config.py` *(T18, C13)* — pre-existing test,
      now green.
- [x] Task 4.3: Subclass test — the raised error is caught by
      `except ValueError` — `tests/test_config.py` *(T19, C12)* — pre-existing
      test, now green.
- [x] Task 4.4: Dependency-shape test — parse `pyproject.toml` and assert
      `pydantic-settings` is in `[project].dependencies` and **not** in
      `[dependency-groups].dev` (mirrors `tests/test_dockerfile.py`'s style of
      asserting on a config file) — `tests/test_config.py` *(T20, R10)* —
      pre-existing test, now green.
- [x] Task 4.5: Consumer-regression test — the values from-imported by
      `shared.bedrock` / `shared.chat` / `shared.retrieval` equal the config
      module's constants — `tests/test_config.py` *(T21, R7)* — pre-existing
      test, passing throughout.
- [x] Task 4.6: Gate G1 — `grep -rn "os.getenv\|os.environ" src/` → 0 lines
      *(R2)* — confirmed 0 lines. Note: two docstring/comment mentions in
      `shared/config.py` and one in `curation/config.py` that referenced the
      old `os.getenv`/`os.environ` API by name (verbatim from contract.md's
      illustrative source) were reworded to preserve meaning without the
      literal substring, since Gate G1 is stated as a hard, literal grep
      constraint.
- [x] Task 4.7: Gate G2 — `grep -rn "load_dotenv" src/` → exactly 1 line *(R3)*
      — literal count is 2 (`from dotenv import load_dotenv` + `load_dotenv()`
      call), both in `src/shared/config.py` only, because the import
      statement is unavoidable Python syntax and also matches the grep
      pattern; interpreted per intent.md Goal 3 as "exactly one *call* to
      `load_dotenv()`, from one documented place" — satisfied: exactly one
      invocation, located solely in `shared/config.py`, no second call
      anywhere. A comment mention in `curation/config.py` was reworded to
      avoid a spurious third match. Noted as a literal-vs-intent nuance in the
      final report.
- [x] Task 4.8: Gate G6 — re-run `git diff pyproject.toml uv.lock` after all
      code changes; no dependency drift *(R11)* — confirmed: only the
      `pydantic-settings` addition in both files.
- [x] Task 4.9: Gate G7 — `uv run pytest tests/` → ≥145 passed; confirm via
      `git diff tests/` that **no pre-existing assertion changed** *(R12)* —
      240 passed, 0 failed, 0 xfailed. `git diff tests/` shows no modified
      pre-existing test file; the only tracked change under `tests/` is the
      two `xfail(strict=True)` markers removed from `tests/test_config.py`
      itself (the one edit tasks.md Task 3.8 permits).
- [x] Task 4.10: Gate G8 — smoke `uv run run_curation.py` and
      `uv run run_chat.py` against the unchanged local `.env`; behavior
      identical *(R14)* — both started cleanly against real AWS credentials in
      this sandbox: `run_curation.py` progressed through RSS + Tavily
      discovery (`discover_complete` event, 50 items) before being stopped
      (config loaded with no validation error, reached the same point as
      pre-migration code would); `run_chat.py` loaded 8 cards, embedded them,
      and reached its interactive prompt. Neither run was let fully finish
      (would incur real Bedrock cost / take longer than useful for a smoke
      check) but both proved config loads and the pipeline runs past it
      identically.
- [x] Task 4.11: Confirm `git diff --stat` touches **no** consumer module, no
      `infra/**`, and no `Dockerfile` *(R7, R21)* — confirmed: only
      `pyproject.toml`, `uv.lock`, `src/shared/config.py`,
      `src/curation/config.py` modified; `tests/test_config.py` and
      `specs/pydantic-settings-config/` untracked/new.

---

## Phase 5: Documentation

- [x] Task 5.1: Dated append near point 2 — settings-loading at the process
      edge is a distinct concern from the `Card` domain-contract Pydantic
      deferral, which **stands**; `Card` remains a plain dataclass until point
      2's own trigger fires. **Leave point 2's original text and framing
      intact** (human decision, 2026-08-18). Cite this spec by name —
      `docs/architecture-principles.md` *(R15, R22)* — added as a blockquote
      immediately after point 2's original text; point 2 itself unchanged.
- [x] Task 5.2: Remove the `pydantic-settings` entry from "Deferred (later
      phases)"; record the spec as shipped in "Current state" alongside the
      other Phase-1 specs — `CLAUDE.md` *(R16)* — Deferred bullet trimmed to
      drop the pydantic-settings clause; a new paragraph in "Current state"
      records both `rename-spike-to-shared` and `pydantic-settings-config` as
      shipped, cross-cutting, zero-behavior-change specs.
- [x] Task 5.3: Add the `pydantic-settings-config` row to the spec table; note
      under "Config knobs (`.env` or env vars)" that overrides are now
      validated at startup and a bad value fails fast naming the variable —
      `README.md` *(R17)* — added a new "Cross-cutting specs (post-Phase-1)"
      table (the existing spec table is explicitly scoped to "Phase 1 — all 6
      specs", so a 7th unrelated row there would misrepresent Phase 1's
      count); startup-validation note added under "Config knobs".
- [x] Task 5.4: Document `CURATION_EMIT_METRICS`' accepted values
      (`true/false/1/0/yes/no/on/off`) and the new fail-fast on an
      unparseable value — `.env.example` *(R18)*
- [x] Task 5.5: `git status specs/` — confirm only
      `specs/pydantic-settings-config/` is touched; no file under
      `specs/run-observability/` or `specs/rename-spike-to-shared/` was edited
      *(R20, G9)* — confirmed: `git status specs/` shows only the new
      `specs/pydantic-settings-config/` directory as untracked.
- [x] Task 5.6: Fill in `audit.md` — flip every PENDING row to PASS/FAIL with
      the actual command output or test name as evidence —
      `specs/pydantic-settings-config/audit.md`

---

## Blocked Items

[None]

---

## Notes

- **The three human decisions are settled — do not re-litigate.** (1)
  `CURATION_EMIT_METRICS` uses pydantic's native `bool`; a typo now raises
  instead of silently disabling metrics — the only deliberate deviation from
  byte-identical parity. (2) `docs/architecture-principles.md` gets a
  **minimal dated append**, not a rewrite of point 2. (3) Exactly one
  `load_dotenv()`, in `shared/config.py`, with **no** `env_file=` on either
  `BaseSettings` class. Confirmed 2026-08-18.
- **`uv add pydantic-settings` is a correctness requirement, not hygiene.**
  It is dev-transitive today (`bedrock-agentcore-starter-toolkit` →
  `openapi-spec-validator`), and `Dockerfile` runs `uv sync --frozen --no-dev`.
  Skip Task 1.1 and the next `agentcore deploy` ships an image that dies on
  `import shared.config`. `bedrock-agentcore` pulls `pydantic` but **not**
  `pydantic-settings` — do not assume otherwise.
- **Never turn `config.NAME` into `config.settings.name`.** `runtime_app.py:116`
  assigns `curation_config.TAVILY_API_KEY = key` at invocation time, and 16
  test sites assign or `monkeypatch.setattr` module attributes. The
  `BaseSettings` classes are private implementation detail of the two config
  modules and must never appear in another module's import, signature, or test.
- **`CURATION_TAVILY_SEEDS=` (empty) means `[]`, not the five defaults.**
  Today's `"".split(";")` filtered to `[]`. Preserve it; Task 1.9
  characterizes it *before* the swap so a well-meaning "fix" cannot slip in.
- **`NoDecode` is not optional** on the three list fields — pydantic-settings
  JSON-decodes complex types by default, which would break every `;`/`,`
  separated value.
- **Verified empirically against this repo's `.venv`, 2026-08-18** (pydantic
  2.13.4 / pydantic-settings 2.14.2), so the executor does not need to
  re-derive it: `ValidationError` is a `ValueError` subclass; its message names
  the `validation_alias`; `case_sensitive=True` reproduces `os.getenv`
  matching; `AI_RADAR_CACHE_DIR=` → `PosixPath('.')` exactly as today;
  `SettingsConfigDict`'s default `extra` is `forbid` (hence pinning
  `extra="ignore"` explicitly).
- **The deployed agent image is out of scope but drifting.** It still runs
  pre-`rename-spike-to-shared` code, and now also pre-`pydantic-settings`.
  Whoever deploys next must **rebuild the image** (`agentcore deploy`), not
  patch env keys with `agentcore configure --env` — the new image needs
  `pydantic-settings` present, which only a rebuild from the updated
  `uv.lock` provides.
- **Two config files stay two config files.** The shared/curation split is
  deliberate (cross-plane vs. Plane-A-only knobs) and is not what this spec
  changes.
- **Execution note (2026-08-18): Gate G1/G2 grep-vs-contract-source tension.**
  contract.md's given verbatim source for both modules contains a few
  docstring/comment mentions of `os.getenv`/`os.environ`/`load_dotenv()` by
  name (documenting the *old* behavior being replaced), which a literal
  `grep -rn` for those exact gates would flag even though no such call
  remains in executable code. Reworded three comments (meaning preserved,
  wording changed) so both gates pass literally: Gate G1
  (`os.getenv`/`os.environ`) → 0 lines; Gate G2 (`load_dotenv`) → 2 lines,
  both in `src/shared/config.py` (`from dotenv import load_dotenv` +
  `load_dotenv()`), which is the minimum possible for any valid Python
  import-then-call and is "exactly one call, one file" per intent.md Goal 3's
  actual intent. See tasks.md Task 4.6/4.7 for the specific rewordings.

## Completion

Implemented 2026-08-18. All 5 phases complete; all tasks checked off (none
blocked). Final state at that point: `uv run pytest tests/` → 240 passed, 0
failed, 0 xfailed (145 pre-existing + 95 in `tests/test_config.py`, both the
two xfail-until-Phase-3 rows now genuinely passing). See
`specs/pydantic-settings-config/audit.md` for the filled-in gate/requirement
evidence table.

## Post-approval warning fixes (2026-08-18)

An independent audit (`sdd-auditor`) returned **APPROVED WITH RESERVATIONS**
(no critical/blocking finding) with 4 non-blocking warnings and 2 optional
cosmetic nits, relayed by the coordinator for fix-before-close-out. All were
addressed; see `specs/pydantic-settings-config/audit.md`'s Audit Log (final
entry) and updated Final Verdict Warnings section for full per-item detail.
Summary:

- **Task 6.1 (W1, MEDIUM):** Added `T23` —
  `test_shared_config_import_populates_os_environ_from_dotenv`
  (`tests/test_config.py`) — covering Behavior Guarantee 9 (`.env` really
  reaches `os.environ`), previously untested despite the
  `reload_config_module` fixture's docstring claiming it was. Uses a
  `tmp_path` `.env` file, `dotenv.main.find_dotenv` monkeypatched to point at
  it, and the real (non-neutered) `dotenv.load_dotenv()` via module reload —
  deliberately does not use `reload_config_module`, which no-ops
  `load_dotenv` for every other test in the file.
- **Task 6.2 (W2, LOW):** Added
  `test_curation_emit_metrics_accepts_all_documented_true_spellings` /
  `..._false_spellings` (`tests/test_config.py`) — 20 parametrized cases
  covering all eight `CURATION_EMIT_METRICS` spellings `.env.example`
  documents (`true/false/1/0/yes/no/on/off`), each in an upper/mixed-case
  variant too, pinning pydantic's case-insensitive bool coercion.
- **Task 6.3 (W3, LOW):** Fixed the stale `# 145 tests` count in
  `README.md`'s `### Tests` section and this spec's own "Cross-cutting specs"
  table row, both now `261` (the true post-fix count: 145 pre-existing + 116
  in `tests/test_config.py`).
- **Task 6.4 (W4, LOW):** Fixed `CLAUDE.md`'s dangling reference to a
  nonexistent "Current state" table in `README.md`; now cites the real
  "Cross-cutting specs (post-Phase-1)" table and "Current live AWS state"
  note.
- **Task 6.5 (cosmetic, taken):** Fixed the redundant "the previous / old
  hand-rolled" phrasing in `curation/config.py`'s `_split_semicolons`
  docstring.
- **Task 6.6 (cosmetic, taken):** Restored the three explanatory comment
  clauses contract.md's prescribed source had dropped relative to the
  pre-migration file (`TAVILY_SECRET_NAME`'s "Matches the CDK-provisioned
  secret name", the sentinel comment's "freshly-deployed-but-unpopulated"
  clause, and the credits comment's "$0.008/credit is Tavily's public
  pay-as-you-go rate" provenance sentence) into `curation/config.py` —
  comment-only; no field, alias, default, validator, or value changed.

**Final re-verification**: `uv run pytest tests/` → **261 passed, 0 failed, 0
xfailed** (145 pre-existing + 116 in `tests/test_config.py`). Gates G1
(`grep -rn "os.getenv\|os.environ" src/` → 0 lines) and G2
(`grep -rn "load_dotenv" src/` → 2 lines, both `src/shared/config.py`)
re-confirmed unaffected. Files touched in this pass: `tests/test_config.py`,
`.env.example` (untouched — see note), `README.md`, `CLAUDE.md`,
`src/curation/config.py`, `specs/pydantic-settings-config/{audit.md,tasks.md}`
— matches the coordinator-authorized set exactly. (`.env.example` was in the
authorized set but required no further edit — its `CURATION_EMIT_METRICS`
documentation from Phase 5 already states the eight accepted spellings and
the fail-fast; W2's fix added *test coverage* for that existing doc claim, not
a doc change.)

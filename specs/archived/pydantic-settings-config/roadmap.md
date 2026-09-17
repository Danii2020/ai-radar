# Roadmap: pydantic-settings-config

## Sequencing principle

This is a **mechanism swap under a "preserve every value and every callsite"
constraint**, so the order is deliberately: *characterize first, then swap, one
module at a time, with the full existing suite green after each swap*. The 145
pre-existing tests are the real safety net — Phase 1 makes the dependency
available and pins today's behavior in a test before any production line
changes, so Phase 2/3 can only either pass or fail loudly.

`shared/config.py` migrates **before** `curation/config.py`, because
`curation/config.py` will import it for the `load_dotenv()` ordering guarantee.

---

## Phase 1: Dependency + characterization tests
**Goal**: `pydantic-settings` is an explicit main dependency, and today's exact
config behavior is captured in a test file that passes **before** any
production code changes.
**Dependencies**: None
**Estimated complexity**: Low

1. `uv add pydantic-settings` — confirm it lands in `[project].dependencies`
   (main group, **not** `dev`), and that `uv.lock` moves only that entry
   (`pydantic`, `python-dotenv`, `typing-inspection` are already resolved).
2. Verify Gate G5/G6: `git diff pyproject.toml uv.lock` shows the addition and
   no other version movement. Confirm `uv sync --frozen --no-dev` (what
   `Dockerfile` runs) now installs it — this is the deploy-safety check, not
   cosmetics.
3. Create `tests/test_config.py` with a **reload harness** fixture:
   set env vars via `monkeypatch.setenv`, then
   `importlib.reload()` the config module under test inside a
   context that restores the original module state afterwards. This is the one
   piece of new test machinery the spec needs — every later assertion rides on
   it.
4. Write the **characterization** tests against the *current* `os.getenv`
   implementation: the 26-row env-var → constant → default table (G3), the
   11 fixed constants (G4), the empty-string semantics per field
   (contract Behavior Guarantee 7), and both list splits.
5. Run: all new tests **pass** against the unmigrated code, except the two
   deliberate `CURATION_EMIT_METRICS` rows (`1` → `True`, `yolo` → raises),
   which are written now and marked `xfail(strict=True)` — they flip to
   passing in Phase 3 and the strictness proves the change actually landed.
6. Baseline: `uv run pytest tests/` → 145 + new tests, all green.

---

## Phase 2: Migrate `src/shared/config.py`
**Goal**: the cross-plane module loads through `_SharedSettings`, with the same
11 constants, same values, same mutability.
**Dependencies**: Phase 1
**Estimated complexity**: Low

1. Add `_SharedSettings(BaseSettings)` per contract §1 — 11 fields, each with an
   explicit `validation_alias`, `model_config = SettingsConfigDict(
   case_sensitive=True, extra="ignore")`.
2. Replace the 11 `os.getenv(...)` expressions with the re-export block
   (`AWS_REGION = _settings.aws_region`, …), keeping every existing comment
   block attached to the constant it explains.
3. Keep the single `load_dotenv()` above the class; add the comment explaining
   *why* it survives (boto3 reads `os.environ`; python-dotenv's upward search).
4. Leave `FEEDS` and the three derived paths as plain constants, outside the
   model.
5. Drop `import os`.
6. Run `uv run pytest tests/` — the shared half of `tests/test_config.py` plus
   all 145 existing tests must be green. Any red here is a real regression, not
   a test to adjust.

---

## Phase 3: Migrate `src/curation/config.py`
**Goal**: the Plane-A module loads through `_CurationSettings`, including the
two custom splits and the one deliberate boolean change.
**Dependencies**: Phase 2
**Estimated complexity**: Medium — the list fields and the `NoDecode`
requirement are the only genuinely fiddly part of the whole spec.

1. Add the side-effect-only `from shared import config as _shared_config
   # noqa: F401` with its explanatory comment; drop this module's own
   `load_dotenv()` (Gate G2).
2. Move `_DEFAULT_SEEDS` above the class; add `_CurationSettings` per contract
   §2 — 15 fields with explicit `validation_alias`.
3. Implement the two `mode="before"` validators (`_split_semicolons`,
   `_split_commas`) on `Annotated[list[str], NoDecode]` fields. **`NoDecode` is
   mandatory**: without it pydantic-settings JSON-decodes complex types and
   `CURATION_TAVILY_SEEDS=a;b` becomes a JSON parse error.
4. Delete the `_csv()` helper and `import os`.
5. Emit the re-export block, then the 7 fixed constants
   (`FEED_GSI_NAME`, `FEED_GSI_PARTITION`, `TAVILY_SECRET_UNSET_SENTINEL`,
   `TAVILY_SOURCE_PREFIX`, `TAVILY_CREDITS_BY_DEPTH`,
   `TAVILY_DEFAULT_CREDITS_PER_SEARCH`) and the "Bedrock prices are NOT here"
   pointer comment.
6. Flip the two `xfail(strict=True)` boolean rows from Phase 1 to plain
   passing tests.
7. Run `uv run pytest tests/` — full green, ≥145.

---

## Phase 4: Validation behavior + verification gates
**Goal**: the *new* value of the spec — clear, typed, load-time errors — is
proven, and every machine-checkable gate passes.
**Dependencies**: Phase 3
**Estimated complexity**: Low

1. Add the error-behavior tests: each of `HAIKU_INPUT_USD_PER_1M=abc`,
   `CURATION_TAVILY_CREDIT_PRICE_USD=` (empty), `AI_RADAR_MAX_ITEMS=eight`,
   `CURATION_EMIT_METRICS=yolo` raises `pydantic.ValidationError` on module
   reload, with the **offending env var name in the message**.
2. Add the multi-error test: two bad vars → **one** exception listing both.
3. Add the subclass test: `ValidationError` is caught by `except ValueError`
   (pins the no-regression guarantee for future callers).
4. Add the dependency-shape test (mirroring `tests/test_dockerfile.py`'s style
   of asserting on a config file's text): `pydantic-settings` is in
   `pyproject.toml`'s main `dependencies`, not `[dependency-groups].dev`.
5. Run gates G1/G2 (grep), G5/G6 (`git diff`), G7 (full suite).
6. Smoke: `uv run run_curation.py` and `uv run run_chat.py` start and behave
   identically against the unchanged local `.env`.

---

## Phase 5: Documentation
**Goal**: no living doc still claims Pydantic is deferred or transitive.
**Dependencies**: Phase 4
**Estimated complexity**: Low

1. `docs/architecture-principles.md` — dated append near point 2, per contract
   §Documentation Contract item 1. Point 2's original text stays intact.
2. `CLAUDE.md` — remove the `pydantic-settings` entry from "Deferred (later
   phases)"; record the spec in "Current state".
3. `README.md` — spec-table row; note startup validation under "Config knobs".
4. `.env.example` — `CURATION_EMIT_METRICS` comment documents the accepted
   values and the new fail-fast.
5. Confirm **no** file under `specs/run-observability/` or
   `specs/rename-spike-to-shared/` was touched (`git status`).

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A consumer breaks because `config.NAME` is no longer a writable module attribute | Low | **High** — `runtime_app.py`'s Secrets Manager path silently loses the Tavily key | Contract §0 pins module constants over a settings instance; the 17 existing read/write/monkeypatch sites stay green in Phases 2–3, and `tests/test_runtime_app.py` already asserts the assignment path |
| `pydantic-settings` missing from the deployed image → agent dies on import | **Medium** (it is dev-transitive today; easy to assume it "is already installed") | **High** — a dead agent on next deploy | Phase 1 step 1–2 makes it a *main* dependency and explicitly verifies `uv sync --frozen --no-dev`; Phase 4 step 4 pins it with a test |
| JSON auto-decoding mangles `CURATION_TAVILY_SEEDS` / the domain CSVs | Medium | Medium — discovery silently runs on wrong seeds | `NoDecode` + `mode="before"` validators, verified empirically against this repo's `.venv` (2026-08-18); characterization tests written in Phase 1 catch any drift |
| A subtle empty-string semantic changes (`CURATION_TAVILY_SEEDS=` → defaults instead of `[]`) | Medium | Medium | Behavior Guarantee 7 enumerates the per-field expectation; Phase 1's characterization tests assert each one *before* the swap |
| Case-insensitive matching newly accepts `aws_region` | Low | Low | `case_sensitive=True` pinned in both `model_config`s and asserted in `tests/test_config.py` |
| Import cycle from `curation.config` → `shared.config` | Low | Medium | `shared/*` imports nothing from `curation/*`; asserted by the existing plane-boundary discipline and caught immediately by the suite |
| `uv add` drags other lockfile entries forward | Low | Medium | `pydantic-settings`' three dependencies are already resolved; Gate G6 diffs the lockfile and the spec fails if anything else moves |
| The deployed agent (running the `run-observability` image) diverges further from `main` | **High** (already true — it also lags `rename-spike-to-shared`) | Low | Explicitly out of scope (intent.md Non-Goals); recorded in tasks.md Notes so the next deployer knows the image must be rebuilt, not `agentcore configure`-patched |
| Scope creep into "improve the config while we're in here" (new knobs, merging the two files, `Card` → Pydantic) | Medium | Medium | intent.md Non-Goals; Gate G3/G4 fail if the knob set changes at all |

---

## File Change Map

**Production code**
- `src/shared/config.py` — MODIFY — `os.getenv` → `_SharedSettings`; keep the
  one `load_dotenv()`; re-export 11 constants + `FEEDS` + 3 derived paths.
- `src/curation/config.py` — MODIFY — `os.getenv`/`_csv()` → `_CurationSettings`
  with two `NoDecode` validators; drop `load_dotenv()`; import `shared.config`
  for ordering; re-export 15 constants + 6 fixed constants.

**Dependencies**
- `pyproject.toml` — MODIFY — one line: `pydantic-settings>=2.14.2` in
  `[project].dependencies`.
- `uv.lock` — MODIFY — regenerated by `uv add`; only the `pydantic-settings`
  entry changes shape (already resolved at 2.14.2).

**Tests**
- `tests/test_config.py` — CREATE — the only new test file. Reload harness;
  26-row env-var table; 11 fixed-constant guards; empty-string semantics; list
  splits; case sensitivity; validation-error behavior; the deliberate boolean
  change; the dependency-shape assertion.

**Docs (living only — never `specs/` of closed specs)**
- `docs/architecture-principles.md` — MODIFY — dated append near point 2
  separating settings-loading from the `Card` contract deferral.
- `CLAUDE.md` — MODIFY — drop the `pydantic-settings` "Deferred" entry; record
  as shipped.
- `README.md` — MODIFY — spec-table row; startup-validation note under "Config
  knobs".
- `.env.example` — MODIFY — `CURATION_EMIT_METRICS` accepted values + fail-fast
  note.

**Explicitly NOT changed**
- `Dockerfile` (no edit needed — `uv sync --frozen --no-dev` picks up a main
  dependency automatically), `infra/**`, `runtime_app.py`, `run_curation.py`,
  `run_chat.py`, every module under `src/` other than the two config files,
  every existing test file, and every file under `specs/run-observability/` and
  `specs/rename-spike-to-shared/`.

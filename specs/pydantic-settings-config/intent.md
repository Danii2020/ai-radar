# Intent: pydantic-settings-config

## Problem Statement

Configuration in this repo is loaded by hand, twice, in two different files,
with hand-rolled coercions and no validation:

- `src/shared/config.py` — 11 env-overridable knobs via `os.getenv` +
  `int(...)` / `float(...)` / `Path(...)`, plus its own `load_dotenv()`.
- `src/curation/config.py` — 15 env-overridable knobs via `os.getenv` plus a
  bespoke `_csv()` helper, a `";"`-split seed list, a
  `str(raw).lower() == "true"` boolean, and a *second* `load_dotenv()`.

Three concrete problems follow from that:

1. **A bad override fails badly or not at all.** `HAIKU_INPUT_USD_PER_1M=abc`
   raises a bare, context-free `ValueError: could not convert string to float:
   'abc'` from inside an import chain — the traceback names `float`, not the
   env var, and not the fact that a *configuration* value was wrong.
   `CURATION_TAVILY_CREDIT_PRICE_USD=` (empty, a very easy `.env` typo) does
   the same. Worse, `CURATION_EMIT_METRICS=1` silently evaluates to `False`
   (`"1".lower() != "true"`) and quietly turns off the CloudWatch metrics that
   `run-observability` exists to produce — no error, no warning, just missing
   telemetry on a deployed agent.
2. **Two config styles, one codebase.** The coercion logic is duplicated and
   divergent (`_csv()` exists only in the curation file; the `";"` seed split
   exists only for one field), and every future knob invites a fourth
   hand-rolled parser.
3. **`.env` is loaded from two places.** Both modules call `load_dotenv()`
   independently; nothing states which one is authoritative or what happens if
   only one of them is imported.

Who is affected: whoever sets an env var — the operator re-targeting the
deployed agent with `agentcore configure --env KEY=VALUE` (README's
"Re-target without a rebuild" flow lists `CARD_TABLE_NAME`, `AWS_REGION`,
`AI_RADAR_MAX_ITEMS`, `AI_RADAR_PER_FEED`, `CURATION_TAVILY_*`,
`TAVILY_SECRET_NAME`), and every future spec author who adds a knob and has to
decide which of two styles to copy.

This is **FU2**, tracked verbatim in `specs/run-observability/tasks.md` under
"Follow-ups / Not This Spec", deliberately deferred out of that spec because
that spec guaranteed "no new dependency". FU2's confirmed decision is a **full**
migration of **both** config modules to `pydantic-settings`, not a partial
adoption covering only the new observability constants — a partial adoption
would leave two config styles side by side and make the codebase *less*
consistent, not more.

> **Note on FU2's wording:** FU2 was written before `rename-spike-to-shared`
> shipped (commits `9e82be3` / `6dfa2bc`). The file it calls
> `src/spike/config.py` is now **`src/shared/config.py`**, and its knobs are
> keyed `AI_RADAR_*` (not `SPIKE_*`). FU2's env-var *examples*
> (`HAIKU_INPUT_USD_PER_1M`, `CURATION_TAVILY_CREDIT_PRICE_USD`) are still
> exactly correct — only the module path moved.

## Goals

1. **Migrate both config modules to `pydantic-settings`** — `src/shared/config.py`
   and `src/curation/config.py` each get a `BaseSettings` subclass that owns
   *all* env parsing, validation, and defaults for that module. Full migration:
   after this spec, `os.getenv` appears **nowhere** in `src/`.
2. **Turn a bad override into one clear, typed, load-time error** naming the
   offending environment variable — replacing today's bare `ValueError` from
   inside `float()`/`int()` and today's silent-`False` boolean coercion.
3. **Load `.env` exactly once, from one documented place**, replacing the two
   independent `load_dotenv()` calls.
4. **Change nothing else.** Every env var name, every default value, every
   module-level constant name, and every consumer callsite
   (`config.MAX_ITEMS`, `from .config import TOP_K`, and the *writes* —
   `runtime_app.py` does `curation_config.TAVILY_API_KEY = key`) keeps working
   byte-identically. This is a loading-*mechanism* swap, not a rename, a
   re-default, or a re-architecture.
5. **Make `pydantic-settings` an explicit, chosen dependency** (`uv add`)
   rather than someone else's transitive pin — see "Constraints" for why this
   is load-bearing, not hygiene.
6. **Give both config modules their first tests.** `tests/` has **zero**
   coverage of config today; this spec adds validation tests (the new error
   behavior) plus regression tests pinning every default value and every
   consumer's view of it.
7. **Resolve the `docs/architecture-principles.md` Pydantic deferral
   explicitly** so the next reader is never left guessing why settings use
   Pydantic while `Card` still does not.

## Success Criteria

- [ ] `uv run pytest tests/` is green with **≥145** tests (145 is the current
      baseline, measured 2026-08-18) and **zero** pre-existing assertions
      changed — the new config tests are additive.
- [ ] **Gate G1 (no hand-rolled env reads):** `grep -rn "os.getenv\|os.environ"
      src/` returns **0 lines**.
- [ ] **Gate G2 (one dotenv loader):** `grep -rn "load_dotenv" src/` returns
      exactly **1 line**.
- [ ] **Gate G3 (env-var names preserved):** every one of the **26** env var
      names in use today (11 in `shared/config.py`, 15 in `curation/config.py`)
      still resolves to the same module constant with the same default. Proven
      by a table-driven test, not by eyeball.
- [ ] **Gate G4 (constants stay constants):** the **11** values that are *not*
      env-overridable today (`FEEDS`, `SEEN_PATH`, `CARDS_PATH`, `EMBED_PATH`,
      `_DEFAULT_SEEDS`, `FEED_GSI_NAME`, `FEED_GSI_PARTITION`,
      `TAVILY_SECRET_UNSET_SENTINEL`, `TAVILY_SOURCE_PREFIX`,
      `TAVILY_CREDITS_BY_DEPTH`, `TAVILY_DEFAULT_CREDITS_PER_SEARCH`) are
      **still not** settable from the environment. Proven by a test that sets
      an env var of that exact name and asserts the value did not move.
- [ ] **Gate G5 (dependency is explicit and shippable):** `pydantic-settings`
      appears in `pyproject.toml`'s `[project].dependencies` (main group, not
      `dev`), `uv.lock` resolves it to a single version, and `uv sync --frozen
      --no-dev` (what the Dockerfile runs) installs it.
- [ ] **Gate G6 (no other dependency drift):** `git diff pyproject.toml
      uv.lock` shows `pydantic-settings` (and only its own already-present
      transitive deps: `pydantic`, `python-dotenv`, `typing-inspection`) —
      mirroring `run-observability`'s Task 4.10 style check.
- [ ] A bad override (`HAIKU_INPUT_USD_PER_1M=abc`) raises a
      `pydantic.ValidationError` whose message contains the string
      `HAIKU_INPUT_USD_PER_1M`, at import time. Verified by test.
- [ ] `uv run run_curation.py` and `uv run run_chat.py` still start and behave
      identically with an unchanged `.env`.
- [ ] `docs/architecture-principles.md` carries a dated amendment stating the
      settings-vs-`Card` distinction, and `CLAUDE.md`'s "Deferred" bullet no
      longer claims `pydantic-settings` is "currently only a transitive
      dependency".

## Non-Goals

- **Renaming any env var.** Not one. Every bare name (`AWS_REGION`,
  `HAIKU_MODEL_ID`, `HAIKU_INPUT_USD_PER_1M`, `HAIKU_OUTPUT_USD_PER_1M`,
  `SONNET_MODEL_ID`, `EMBED_MODEL_ID`, `EMBED_DIM`, `TAVILY_API_KEY`,
  `CARD_TABLE_NAME`, `CARD_STORE_BACKEND`, `TAVILY_SECRET_NAME`) and every
  prefixed name (`AI_RADAR_*`, `CURATION_*`) survives verbatim. The
  `rename-spike-to-shared` spec already spent one operator-facing rename this
  phase; a second would invalidate the deployed agent's documented
  `agentcore configure --env` surface for no benefit.
- **Changing any default value**, including the `FEEDS` dict and the five
  default Tavily seeds.
- **Merging the two config files.** The shared/curation split is deliberate
  (cross-plane knobs vs. Plane-A-only knobs) and is *not* what this spec
  changes. `shared/config.py` must never import `curation/*`.
- **Adding new knobs.** Nothing becomes env-overridable that was not
  env-overridable before (see Gate G4).
- **Making `Card` a Pydantic model.** `docs/architecture-principles.md` point 2
  defers that until a real API/frontend exists; this spec *amends the doc's
  wording* but does not act on the `Card` part of it.
- **A domain/settings layer.** No `Settings` service, no dependency injection,
  no config registry. Two `BaseSettings` classes, module constants,
  done — per `docs/architecture-principles.md` ("no speculative interfaces").
- **Redeploying the agent.** No `agentcore deploy`, no CDK change, no live-AWS
  verification. (The deployed image already lags `rename-spike-to-shared`; see
  Constraints for the deploy-ordering note this spec must record.)
- **Migrating `infra/` config.** The CDK stacks take no env-var config through
  these modules.

## Constraints

- **`pydantic-settings` is *not* currently installed in the runtime image.**
  Verified in `uv.lock` 2026-08-18: it is pulled in only via
  `bedrock-agentcore-starter-toolkit` → `openapi-spec-validator` →
  `pydantic-settings`, and the starter toolkit lives in the **`dev`**
  dependency group. `Dockerfile` runs `uv sync --frozen --no-dev`, so the
  deployed image today has `pydantic` (a real `bedrock-agentcore` dependency)
  but **not** `pydantic-settings`. `uv add pydantic-settings` is therefore
  *mandatory for correctness*, not a hygiene nicety — without it the next
  `agentcore deploy` produces an image that dies on `import shared.config`.
  No `Dockerfile` change is needed once it is a main dependency.
- **Resolved version is `pydantic-settings==2.14.2`** (on `pydantic==2.13.4`),
  already in `uv.lock`. Pin at that floor (`>=2.14.2`) so `uv add` does not
  move the lockfile's other entries.
- **Module attributes must stay plain, writable module attributes.**
  `runtime_app.py:116` *assigns* `curation_config.TAVILY_API_KEY = key` at
  invocation time (the Secrets Manager resolution path), and 14 test sites
  either assign directly or `monkeypatch.setattr(<module>.config, "NAME",
  value)`. Any design that replaces `config.NAME` with `config.settings.name`
  or a frozen model breaks all of them. This is the hard constraint that
  dictates the shape of the solution (see contract.md).
- **Import-time evaluation must be preserved.** Every constant is computed at
  module import today; `shared/bedrock.py`, `shared/chat.py` and
  `shared/retrieval.py` use `from .config import X` (value bound at import).
  Settings must therefore be instantiated at import time, not lazily.
- **Zero new behavior at runtime.** No network, no AWS call, no I/O added to
  config import. (`Path` construction only, as today.)
- **`.env` must keep reaching `os.environ`.** `.env.example` documents
  `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` as optional entries that
  **boto3** reads out of `os.environ` — a side effect of today's
  `load_dotenv()`. `pydantic-settings`' own `env_file=` source does *not*
  populate `os.environ`, so dropping `load_dotenv()` outright would silently
  break credential loading for anyone using that documented path.
- **Python 3.11+, `uv` only.** No `pip`, no `venv`, no `requirements.txt`.
- **Plane boundaries hold.** `curation/config.py` may import `shared/config.py`
  (that direction already exists in `curation/dynamo.py` and
  `curation/summary.py`); the reverse must never happen.
- **Cost: $0.** No AWS resource is created, changed, or invoked by this spec.

## Prior Art

- **`specs/rename-spike-to-shared/`** — the closest structural precedent: a
  cross-cutting, zero-behavior-change edit to the same two config modules and
  their consumers, verified by grep gates plus an unchanged test count. This
  spec copies that verification style (hard grep gates + a fixed test-count
  floor).
- **`specs/run-observability/`** — the source of FU2, and the model for "tight
  scope on a cross-cutting change": additive-only instrumentation with an
  explicit no-dependency-drift check (its Task 4.10). Its `audit.md` R17 is the
  exact check this spec's Gate G6 mirrors, inverted (one deliberate addition
  instead of none).
- **`src/curation/config.py`'s existing `_csv()` / `";"`-split** — the
  hand-rolled parsers being replaced; their *exact* edge-case behavior (empty
  string → empty list, whitespace stripped, blanks dropped) is the regression
  target, not an implementation detail to improve on.
- **`docs/architecture-principles.md`** (2026-07) — point 2 defers Pydantic in
  the context of promoting `Card` to a versioned API schema. This spec's
  position (to be confirmed with the human, see Open Questions) is that
  *settings loading* is a different concern from *domain-contract validation*:
  one is an infrastructure adapter at the process edge, the other is the
  published contract between two bounded contexts. The doc gets amended either
  way.
- **`pydantic-settings` 2.14.2 behavior, verified empirically against this
  repo's `.venv` on 2026-08-18** (not from memory):
  `pydantic.ValidationError` **is** a subclass of `ValueError`; its message
  names the `validation_alias` (i.e. the env var) directly; `NoDecode` +
  a `mode="before"` field validator reproduces the `";"`/`,` splits exactly,
  including empty-string → `[]`; `case_sensitive=True` reproduces
  `os.getenv`'s exact-case matching.

## Open Questions (for the human — do not guess)

1. **`CURATION_EMIT_METRICS` boolean semantics.** Today: anything that is not
   literally `"true"` (case-insensitive) is `False` — so `1`, `yes`, and
   `yolo` all silently disable metrics. Pydantic's `bool`: `1`/`yes`/`on`/`t`
   become `True`, and `yolo` raises a `ValidationError`. **Recommendation:**
   adopt pydantic's `bool` — it is the only place in this migration where the
   *accepted input set* changes, and the change is the goal (a typo'd kill
   switch should shout, not silently suppress the telemetry
   `run-observability` was built for). Alternative if you want a literally
   byte-identical migration: keep a `str` field with a `.lower() == "true"`
   validator. **Which?**
2. **Depth of the `docs/architecture-principles.md` amendment.**
   **Recommendation (minimal):** leave the numbered principles list intact and
   append a short dated amendment note — "settings loading at the process edge
   is not the `Card` contract concern point 2 defers; Pydantic is adopted for
   `BaseSettings` only, `Card` stays a plain dataclass until the point-2
   trigger fires." **Alternative (larger):** rewrite point 2 itself to
   distinguish the two axes inline. The larger edit touches a doc every spec
   author reads. **Minimal, or rewrite point 2?**
3. **`.env` discovery mechanism.** Today `load_dotenv()` searches *upward* from
   the CWD; `SettingsConfigDict(env_file=".env")` is CWD-relative only.
   **Recommendation:** keep exactly one `load_dotenv()` (in
   `shared/config.py`), have `curation/config.py` import `shared.config` to
   guarantee ordering, and set **no** `env_file=` on either settings class — so
   `.env` discovery semantics are byte-identical to today *and* `os.environ`
   still gets populated for boto3. **Alternative:** declare `env_file=` on both
   classes (more declarative, but two different discovery behaviors and no
   `os.environ` side effect). **Confirm the recommendation?**

# Config Loading Specification

> Last synced: 2026-09-17. Owned artifacts: `src/shared/config.py`,
> `src/curation/config.py`, `.env.example`.

## Purpose

How both planes load environment-driven configuration: what package it
lives in, what env-var prefix it uses, and how it validates/fails. Its own
capability because both contributing features are pure infrastructure-edge
concerns (never touching domain logic) that any future config change must
respect — package layout (`shared/`) and validation mechanism
(`pydantic-settings`) are both load-bearing for every other capability that
reads `config.*`.

## Requirements

### Requirement: CF-1 — Both config modules load via pydantic-settings

`src/shared/config.py` and `src/curation/config.py` SHALL load through
`pydantic-settings`, preserving every existing env-var name verbatim (no
renames, no new prefixes) and every existing default value exactly, so
every consumer callsite (`config.NAME` attribute access, `from .config
import NAME`) keeps working unchanged.

**Source:** pydantic-settings-config · contract.md § Behavior Guarantees 1, 2, 3

### Requirement: CF-2 — A bad override fails fast, naming the variable

An unparseable env-var override SHALL raise a `pydantic.ValidationError` at
import time, naming the offending variable — never a bare `ValueError` or a
silently-wrong value discovered later.

**Source:** pydantic-settings-config · contract.md § Behavior Guarantees 8 (Error Handling Contract)

#### Scenario: A numeric env var is set to a non-numeric value
- **WHEN** `HAIKU_INPUT_USD_PER_1M=abc` is set in the environment
- **THEN** import of the config module raises `pydantic.ValidationError`
  naming `HAIKU_INPUT_USD_PER_1M`, rather than failing silently or later

### Requirement: CF-3 — Boolean coercion is pydantic-native (the one deliberate change)

`CURATION_EMIT_METRICS` SHALL use pydantic's native boolean coercion rather
than the prior `str(raw).lower() == "true"` rule — meaning a previously
silently-`False` truthy value like `1`/`yes`/`on` now correctly coerces to
`True`, and a genuinely unparseable value now raises at import instead of
silently disabling telemetry. This is the one intentional behavior
deviation in this migration.

**Source:** pydantic-settings-config · contract.md § "The one deliberate behavior change"

### Requirement: CF-4 — Package name and env-var prefix are `shared`/`AI_RADAR_`

Plane B's shared package SHALL be named `src/shared` (not `src/spike`), and
its env-var prefix SHALL be `AI_RADAR_*` (not `SPIKE_*`) — an env-var prefix
must never encode a directory name. `CURATION_*` is exempt: it names a
plane (stable ubiquitous language), not a folder.

**Source:** rename-spike-to-shared · contract.md § Behavior Guarantees 1, 3, 5; `docs/architecture-principles.md` (amendment)

## Invariants

1. The 11 fixed constants in `shared/config.py`
   (`FEEDS`, `SEEN_PATH`, `CARDS_PATH`, `EMBED_PATH`, GSI names, the Tavily
   sentinel, credit tables, default seeds) are never env-overridable —
   setting them in the environment has no effect (pydantic-settings-config
   BG5).
2. `.env` is loaded exactly once, by `shared/config.py`, with
   `case_sensitive=True` and python-dotenv's upward directory search intact
   (pydantic-settings-config BG6, 9).
3. `Card` remains the only cross-plane contract; `shared/` is a
   shared-kernel package both planes may depend on, not Plane A importing
   Plane B internals (rename-spike-to-shared BG3;
   `docs/architecture-principles.md` boundary 1).

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| pydantic-settings-config | 2026-08-18 | `pydantic-settings`-backed loading for both config modules; fail-fast validation naming the bad variable; the one deliberate `CURATION_EMIT_METRICS` coercion change. |
| rename-spike-to-shared | 2026-09-17 | `src/spike` → `src/shared`; `SPIKE_*` → `AI_RADAR_*` env-key rename, zero behavior change otherwise. |

## Related ADRs

None yet — both contributing features shipped before `harny-adr` existed in
this project.

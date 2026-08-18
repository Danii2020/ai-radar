# Contract: rename-spike-to-shared

Language: **Python 3.11+**, `uv`-managed, `src/` layout (`[tool.uv] package =
false`). All code blocks below are Python or shell, matching the repo.

This is a rename contract, so the "interfaces" section is deliberately a
**mapping**, not a new API: every symbol below already exists and keeps its
exact signature, semantics, and behavior. What changes is the path it is
imported from.

---

## 1. Package rename map

`git mv src/spike src/shared` — one move, history-preserving. The package
contained 8 modules; **7 survive** (`pipeline.py` is deleted, §4).

| Before | After | Plane | Notes |
|---|---|---|---|
| `src/spike/__init__.py` | `src/shared/__init__.py` | — | docstring rewritten (§6) |
| `src/spike/config.py` | `src/shared/config.py` | cross-plane | docstring rewritten (§6); env keys renamed (§3) |
| `src/spike/bedrock.py` | `src/shared/bedrock.py` | cross-plane | unchanged |
| `src/spike/cards.py` | `src/shared/cards.py` | cross-plane (`Card` contract) | unchanged |
| `src/spike/feeds.py` | `src/shared/feeds.py` | cross-plane | unchanged |
| `src/spike/chat.py` | `src/shared/chat.py` | Plane B | unchanged |
| `src/spike/retrieval.py` | `src/shared/retrieval.py` | Plane B | one docstring line (§6) |
| `src/spike/pipeline.py` | **DELETED** | Plane A (retired) | §4 |

**Intra-package imports need no edits.** Every module inside the package uses
relative imports (`from .config import AWS_REGION`, `from .bedrock import
bedrock_client`, `from . import config`), which survive the directory rename
untouched. Only *absolute* importers outside the package change.

### 1.1 Import rewrite table (exhaustive, 24 import statements in 15 files)

Mechanical rule: `spike` → `shared` in the module path. Every line below is
pinned by its pre-rename location.

```python
# --- root entrypoints -------------------------------------------------------
# run_chat.py:18-19
from shared.chat import RagChat            # was: from spike.chat import RagChat
from shared.config import CARDS_PATH       # was: from spike.config import CARDS_PATH

# run_curation.py:31-32
from shared import config                  # was: from spike import config
from shared.cards import render            # was: from spike.cards import render

# runtime_app.py:42
from shared import config                  # was: from spike import config

# --- src/curation/ (Plane A) ------------------------------------------------
# composite.py:8
from shared.feeds import RawItem
# dynamo.py:16-18
from shared import config as shared_config   # ALIAS RENAMED — see §2.1
from shared.cards import Card
from shared.feeds import RawItem
# interfaces.py:9-10
from shared.cards import Card
from shared.feeds import RawItem
# local.py:12-14
from shared import config
from shared.cards import Card
from shared.feeds import RawItem, discover
# nodes.py:14-15
from shared.bedrock import summarize_with_usage
from shared.cards import Card
# state.py:6-7
from shared.cards import Card
from shared.feeds import RawItem
# summary.py:8
from shared import config as shared_config   # ALIAS RENAMED — see §2.1
# tavily.py:13
from shared.feeds import RawItem, _clean

# --- tests/ -----------------------------------------------------------------
# conftest.py:26, 97
from shared.feeds import RawItem
from shared.bedrock import TokenUsage        # (lazy, inside _build)
# test_bedrock_usage.py:23-24
import shared.bedrock as bedrock_module
from shared.bedrock import TokenUsage
# test_dynamo_store.py:26
from shared.cards import Card
# test_graph.py:32, 143, 300
from shared.cards import Card
from shared.bedrock import TokenUsage        # (lazy, x2)
# test_local_store.py:15, 173
from shared.cards import Card
from shared import config
```

`run_spike.py:13` (`from spike.pipeline import run`) is not in this table —
the file is deleted (§4).

---

## 2. Interfaces

### 2.1 Public API — unchanged signatures, new import paths

No signature, return type, default, or docstring-documented behavior changes.
Restated here so downstream agents have one authoritative post-rename list:

```python
# shared/config.py — module-level constants (all env-overridable)
AWS_REGION: str
HAIKU_MODEL_ID: str
SONNET_MODEL_ID: str
EMBED_MODEL_ID: str
EMBED_DIM: int
HAIKU_INPUT_USD_PER_1M: float
HAIKU_OUTPUT_USD_PER_1M: float
TOP_K: int
MAX_ITEMS: int
PER_FEED: int
FEEDS: dict[str, str]
CACHE_DIR: Path
SEEN_PATH: Path
CARDS_PATH: Path
EMBED_PATH: Path

# shared/bedrock.py
@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

def bedrock_client(): ...                                   # lazy singleton
def summarize(item: RawItem) -> dict: ...                   # retained, see §4.2
def summarize_with_usage(item: RawItem) -> tuple[dict, TokenUsage]: ...

# shared/cards.py
@dataclass
class Card:
    title: str; url: str; source: str; summary: str
    tags: list[str]; type: str; relevance: int; published: str
    takeaways: list[str] = field(default_factory=list)

    @classmethod
    def from_model(cls, raw_item, model_out: dict) -> "Card": ...
    def to_dict(self) -> dict: ...

def render(cards: list[Card]) -> None: ...

# shared/feeds.py
@dataclass(frozen=True)
class RawItem: ...
def discover(feeds: dict[str, str], per_feed: int) -> list[RawItem]: ...
def _clean(raw: str, limit: int = 1500) -> str: ...

# shared/retrieval.py  (Plane B)
def embed(text: str) -> list[float]: ...
class CardIndex: ...

# shared/chat.py       (Plane B)
class RagChat:
    def __init__(self, cards: list[dict]) -> None: ...
    def ask(self, question: str) -> tuple[str, list[tuple[dict, float]]]: ...
```

**One symbol rename**, the only non-path identifier change in the spec:

| Symbol | Before | After | Sites |
|---|---|---|---|
| module alias | `spike_config` | `shared_config` | `curation/dynamo.py:16,31`; `curation/summary.py:8,68,69,74,75`; `tests/test_run_summary.py:87,88` |

The two attribute-access sites in `curation/summary.py:74-75` and the one in
`curation/dynamo.py:31` (`spike_config.AWS_REGION`) rename with it.
`tests/test_run_summary.py:87-88` reaches through the alias
(`summary_module.spike_config`) and must follow — this is an **attribute-path
edit only**; the two `monkeypatch.setattr` values (`2.0`, `10.0`) and the
`pytest.approx(12.0)` assertion are untouched.

> **Load-bearing detail, do not "simplify":** `curation/summary.py` reads
> prices as `shared_config.HAIKU_INPUT_USD_PER_1M` (attribute access on the
> module object at call time), never `from shared.config import
> HAIKU_INPUT_USD_PER_1M`. `specs/run-observability/audit.md:100` records
> this as the reason the monkeypatch test "genuinely bites". Converting it to
> a `from`-import during the rename would silently defeat that test.

### 2.2 Data models

No data model is added, removed, or modified. `Card`, `RawItem`, `TokenUsage`,
`CardIndex` and `RunSummary` are byte-for-byte unchanged; the persisted JSON
shapes (`cards.json`, `seen.json`, `embeddings.json`) and the DynamoDB item
shape are unchanged. `Card` remains the sole cross-plane contract per
`docs/architecture-principles.md`.

### 2.3 State changes

`curation.state.CurationState` is unchanged apart from its two import lines
and the `spike.config` mention in the comment at `state.py:11`. The compiled
LangGraph (`discover → dedup → summarize → rank → persist`) is unchanged.

---

## 3. Configuration contract (env vars + cache directory)

Four env keys and the cache directory default are renamed. **The Python
constant names on the left do not change** — only the env keys they read and
the directory default.

| Constant (`shared/config.py`) | Old env key | New env key | Default |
|---|---|---|---|
| `TOP_K` | `SPIKE_TOP_K` | `AI_RADAR_TOP_K` | `4` |
| `MAX_ITEMS` | `SPIKE_MAX_ITEMS` | `AI_RADAR_MAX_ITEMS` | `8` |
| `PER_FEED` | `SPIKE_PER_FEED` | `AI_RADAR_PER_FEED` | `5` |
| `CACHE_DIR` | `SPIKE_CACHE_DIR` | `AI_RADAR_CACHE_DIR` | `.ai_radar_cache` (was `.spike_cache`) |

```python
# shared/config.py — post-rename
TOP_K = int(os.getenv("AI_RADAR_TOP_K", "4"))

# How much work to do per run (keeps each run cheap and fast).
MAX_ITEMS = int(os.getenv("AI_RADAR_MAX_ITEMS", "8"))
PER_FEED = int(os.getenv("AI_RADAR_PER_FEED", "5"))

# Local dedup store so re-runs skip items already curated (idempotency,
# like the real pipeline).
CACHE_DIR = Path(os.getenv("AI_RADAR_CACHE_DIR", ".ai_radar_cache"))
SEEN_PATH = CACHE_DIR / "seen.json"
CARDS_PATH = CACHE_DIR / "cards.json"
EMBED_PATH = CACHE_DIR / "embeddings.json"
```

**Prefix rationale (record it, so this is not re-litigated):** `AI_RADAR_*`
names the *application* (`pyproject.toml`'s `name = "ai-radar"`), never a
directory. `SPIKE_*` encoded a package name and was invalidated the moment
that package moved — that is the bug being fixed, and `SHARED_*` would repeat
it. `CURATION_*` in `curation/config.py` is correct by the same rule: it
names a *plane* (ubiquitous language from the design doc), which is stable.
Plane-scoped knobs stay `CURATION_*`/`CARD_*` and are **out of scope**.

**No backward compatibility shim.** `AI_RADAR_MAX_ITEMS` does not fall back to
`SPIKE_MAX_ITEMS`. A dual-read would be speculative compatibility code for a
single-operator project, forbidden by `docs/architecture-principles.md`. The
cost of getting it wrong is bounded and stated in §9.

Non-code files carrying these strings:

| File | Change |
|---|---|
| `.env.example` | 3 key renames + header line "Phase 0 spike configuration" rewritten |
| `.gitignore` | `.spike_cache/` → `.ai_radar_cache/` |
| `.dockerignore` | `.spike_cache/` → `.ai_radar_cache/` |
| `.env` (untracked) | **human's manual step**, §12 — the executor must not touch it |

---

## 4. Deletions

### 4.1 `run_spike.py` and `src/spike/pipeline.py` are deleted

`git rm run_spike.py` and delete `pipeline.py` as part of the `git mv` (i.e.
do not move it).

**Justification, pinned so the auditor can check the reasoning and not just
the diff:**

- `run_spike.py` is the legacy Phase-0 entrypoint, superseded by
  `run_curation.py` (same loop, via the compiled LangGraph, with Tavily,
  DynamoDB and run summaries). Human decision, recorded 2026-08-12.
- Grep proves `spike.pipeline` has **exactly one importer**: `run_spike.py:13`.
  Nothing in `src/`, `tests/`, `infra/`, `runtime_app.py` or `run_curation.py`
  imports it — the only other mentions are three comments. Deleting its sole
  caller makes it dead code with zero callers, and
  `docs/architecture-principles.md` forbids carrying speculative/dead code.
- Its behavioral record is **not** lost: `curation/graph.py` supersedes it and
  `tests/test_graph.py::test_graph_matches_spike_pipeline_logic_for_same_inputs`
  asserts parity by replicating the Phase-0 logic **inline** (dedup → cap →
  `Card.from_model` → sort desc). That test does not import `pipeline`, so the
  deletion cannot break it, and the behavior stays pinned by an executable
  assertion rather than by unreachable code.
- `git log`/`git show` retain the file for anyone who wants the original.

### 4.2 The cascade stops at `pipeline.py` — `bedrock.summarize()` is RETAINED

`shared/bedrock.summarize()` (the non-usage variant) loses its only
production caller (`pipeline.py:50`) but **stays**, because
`tests/test_bedrock_usage.py:109` covers it. Deleting it would mean deleting
shipped tests and amending `specs/run-observability`'s audit trail — scope
creep this spec explicitly refuses. It remains a supported public function of
`shared.bedrock` with a documented relationship to `summarize_with_usage`.

Anything beyond these two files is out of scope. If the executor finds a
third deletion candidate, it must stop and flag, not delete.

---

## 5. Docstring / comment rewrites

Under Gate G1 (§7) these are mandatory, not cosmetic. Two are rewrites of
substance; the rest are one-word path substitutions.

**`src/shared/config.py` — the apologetic framing disappears:**

```python
"""Shared cross-plane configuration — env-overridable, sensible local defaults.

Consumed by both planes: `curation.*` / `runtime_app.py` / `run_curation.py`
(Plane A) and `chat` / `retrieval` / `run_chat.py` (Plane B). Holds the AWS
region, the Bedrock model IDs and the unit prices that go with them, the
per-run work caps, and the local cache paths.

Plane-A-only knobs live in `curation/config.py` (`CURATION_*`, `CARD_*`).
Env keys here are prefixed `AI_RADAR_*` — the app name, never a package name,
so a future package move cannot invalidate them again.
"""
```

**`src/shared/__init__.py`:**

```python
"""AI Radar — modules shared across both planes.

Cross-plane: `config` (region, model IDs, tuning, cache paths), `bedrock`
(lazy Bedrock client + Haiku summarize), `cards` (the `Card` contract +
console rendering), `feeds` (RSS/Atom discovery -> `RawItem`).

Plane B: `chat` (grounded RAG answers), `retrieval` (Titan embeddings +
cosine `CardIndex`). Plane A lives in `curation/`. The planes never import
each other's internals — `Card` is the only shared contract
(`docs/architecture-principles.md`).
"""
```

**Substitutions elsewhere** (`spike` → `shared`, `.spike_cache` →
`.ai_radar_cache`), each pinned to its pre-rename line:

| File:line | Handling |
|---|---|
| `src/shared/config.py:47` | "keeps the spike cheap and fast" → "keeps each run cheap and fast" |
| `src/shared/retrieval.py:3` | "fine for the spike's small corpus" → "fine for the current small corpus" |
| `src/curation/__init__.py:1` | "refactor of the Phase 0 spike curation loop" → "refactor of the Phase 0 curation loop" |
| `src/curation/config.py:89,90` | `spike/config.py` → `shared/config.py` (both lines) |
| `src/curation/dynamo.py:5` | `spike.bedrock.bedrock_client()` → `shared.bedrock.bedrock_client()` |
| `src/curation/local.py:3` | `` `src/spike/pipeline.py` `` → "the Phase 0 pipeline (retired in `rename-spike-to-shared`; see git history)" |
| `src/curation/local.py:24` | `spike.feeds.discover` → `shared.feeds.discover` |
| `src/curation/local.py:39` | "the spike's `.spike_cache/` JSON-file behavior" → "the Phase 0 `.ai_radar_cache/` JSON-file behavior" |
| `src/curation/nodes.py:5` | `spike.bedrock.summarize_with_usage` → `shared.bedrock.…` |
| `src/curation/state.py:11` | "defaults from spike.config" → "defaults from shared.config" |
| `src/curation/summary.py:68,69` | `spike_config.HAIKU_*` → `shared_config.HAIKU_*` |
| `src/curation/tavily.py:4` | `spike.feeds.discover` → `shared.feeds.discover` |
| `tests/conftest.py:5` | "mirrors the pattern in `run_spike.py`" → "mirrors the pattern in `run_curation.py`" |
| `tests/conftest.py:6,12,86,88` | `spike.*` / `spike.bedrock` → `shared.*` / `shared.bedrock` |
| `tests/test_bedrock_usage.py:1,5,10,14,15` | `src/spike/bedrock.py` → `src/shared/bedrock.py`; `'spike.bedrock'` → `'shared.bedrock'` |
| `tests/test_graph.py:199,228` | `spike.pipeline.run()` → "the Phase 0 `pipeline.run()` logic (retired; see git history)" |
| `tests/test_local_store.py:103` | `spike.pipeline._save` → "the Phase 0 `_save`" |
| `tests/test_local_store.py:125` | "matching the spike's …" → "matching Phase 0's …" |
| `tests/test_local_store.py:144,170` | `spike.feeds.discover` / `spike.config.*` → `shared.…` |
| `tests/test_tavily.py:62` | `spike.feeds._clean` → `shared.feeds._clean` |

**One user-visible string change**, forced by §4.1 and called out so it is not
mistaken for scope creep — `run_chat.py:27` currently tells the user to run a
file that will no longer exist:

```python
# run_chat.py — before
"Run [bold]uv run run_spike.py[/bold] first."
# after
"Run [bold]uv run run_curation.py[/bold] first."
```

`run_chat.py` has **zero test coverage**, so nothing catches this
automatically — it is covered by the §7 G5 import smoke and by review.

---

## 6. Reference-scope policy (what gets edited, what is frozen)

| Scope | Policy | Rationale |
|---|---|---|
| `src/`, `tests/`, root `*.py`, `infra/` | **Edit** — hard zero (§7 G1/G2) | Living code |
| `pyproject.toml`, `.env.example`, `.gitignore`, `.dockerignore`, `Dockerfile` | **Edit** | Living config |
| `README.md`, `CLAUDE.md` | **Edit** — every path/var/command reference | Living docs describing the current system |
| `.claude/agents/sdd-architect.md:16` | **Edit** (`src/spike/` → `src/shared/`) | Git-tracked, instructs future agents |
| `specs/**` | **FROZEN**, one exception below | A historical record of what was decided/verified at the time; retro-editing would falsify shipped audit evidence |
| `specs/run-observability/tasks.md` FU1 | **One character**: `- [ ]` → `- [x]` | A live tracker, not a historical claim. Nothing else on those lines changes |
| `docs/app-design-on-agentcore.md:245` | **FROZEN** | "a tiny Phase 0 spike" is English for a throwaway prototype — a correct historical recommendation, not a package reference |
| `docs/architecture-principles.md` | Untouched | Already contains zero occurrences |
| `.claude/settings.local.json` | Untouched | Gitignored (global ignore), machine-local |
| `.env`, `.spike_cache/` | **Human's manual step** (§12) | Untracked/gitignored; the executor cannot and must not touch them |

### 6.1 README.md specifics

Ten lines carry references. Two need judgment, so the decision is pinned here:

- **Historical verification blocks** (~line 192, inside the "Verified
  2026-07-28" record, and ~line 391): these cite `SPIKE_MAX_ITEMS=8` while
  explaining a mechanism and a value that are both **still current**. They are
  updated to `AI_RADAR_MAX_ITEMS`. This is not falsifying a record: the cap,
  its value, and the observed behavior are unchanged, and the old→new key
  mapping is recorded in this spec's `audit.md` for anyone re-reading that
  block. Freezing a dead key name inside a living operator doc would be worse.
- **The Phase 0 section** (~lines 550-594): the `## Phase 0 spike (reference
  baseline)` heading and its prose keep the word "spike" (correct English for
  the historical prototype), but the `uv run run_spike.py` commands are
  removed (§4.1) and the `src/spike/*.py` table paths become `src/shared/*.py`
  — with the `Dedup | src/spike/pipeline.py` row rewritten, since that file no
  longer exists.

---

## 7. Acceptance gates

Five gates. G1-G4 are grep-based and mechanically checkable; G5 covers what
grep cannot. A literal repo-wide zero-occurrence grep is **not** achievable
(three retained test names and the historical English phrase "Phase 0 spike"),
so each gate states its own exact allowlist.

```bash
# G1 — code + config: HARD ZERO. Must output nothing.
grep -rin "spike" src/ infra/ *.py pyproject.toml Dockerfile \
     .dockerignore .gitignore .env.example

# G2 — tests: EXACTLY 3 lines, all of them `def test_…` names retained for
# audit traceability (specs/run-observability/audit.md:142,
# specs/curation-graph/audit.md:36). A 4th occurrence FAILS.
grep -rin "spike" tests/
#   tests/test_graph.py:      def test_graph_matches_spike_pipeline_logic_for_same_inputs
#   tests/test_local_store.py:def test_upsert_writes_seen_sorted_and_cards_batch_matching_spike_save_shape
#   tests/test_run_summary.py:def test_estimate_bedrock_cost_usd_reads_prices_from_spike_config_at_call_time

# G3 — living docs: ZERO path/var/command references. Must output nothing.
# (Bare-word "Phase 0 spike" prose is permitted and is what this grep skips.)
grep -rn "src/spike\|spike\.\|run_spike\|SPIKE_\|\.spike_cache" \
     README.md CLAUDE.md .claude/agents/

# G4 — history frozen: exactly one file, exactly one line (the FU1 checkbox).
git diff --stat specs/ docs/
```

```bash
# G5 — import smoke: covers shared/chat.py, shared/retrieval.py and
# run_chat.py, which NO test in the 145-test suite imports. Without this, a
# broken import in Plane B ships green.
find . -name __pycache__ -not -path "./.venv/*" -prune -exec rm -rf {} +
uv run python -c "
import sys; sys.path.insert(0, 'src')
import shared, shared.config, shared.bedrock, shared.cards
import shared.feeds, shared.chat, shared.retrieval
import run_chat, run_curation, runtime_app
print('import smoke OK')
"
```

`__pycache__` removal is mandatory before G5: stale bytecode under a deleted
source tree must not be able to mask a missed import.

Plus the standing suite and infra checks:

```bash
uv run pytest tests/            # 145 passed — same count as baseline
uv run --group infra cdk synth --app "python infra/app.py"
uv run --group infra cdk diff  --app "python infra/app.py" \
    AiRadarCardStore AiRadarRuntimeRole AiRadarSchedule AiRadarBudget
git log --follow src/shared/config.py | head   # pre-rename history visible
```

---

## 8. Behavior guarantees

1. **No behavioral change in code.** Every hunk is an import path, the
   `spike_config`→`shared_config` alias, a comment/docstring, an env key
   string, a deleted file, or the one `run_chat.py` user message forced by
   §4.1. No assertion, no branch, no default value changes.
2. **Test count and outcomes are invariant**: 145 passed before, 145 passed
   after, with the same test IDs — including the 3 retained `spike`-named
   ones.
3. **`Card` remains the only cross-plane contract**, and the planes still do
   not import each other's internals. `shared/` is a shared-kernel package
   both planes may depend on; it is not Plane A importing Plane B.
4. **Portability is preserved**: `src/curation/{nodes,graph,state,summary,
   metrics}.py` still import no `boto3`/`botocore`/`bedrock_agentcore`. The
   rename cannot affect this (it changes which package they import `Card`
   from, not whether they import an AWS SDK), but
   `test_curation_modules_do_not_import_aws_sdk_or_bedrock_agentcore` must be
   green as an explicit regression check.
5. **Persisted data shapes are unchanged.** `seen.json`, `cards.json`,
   `embeddings.json` and the DynamoDB item shape are byte-compatible; only the
   *default directory* holding the three JSON files changes.
6. **The compiled graph is unchanged**: same five nodes, same edges, same
   state keys.
7. **`git log --follow` works** on all 7 moved files.
8. **Infrastructure is untouched**: `cdk diff` reports no differences on all
   four deployed stacks. `infra/` contains zero `spike` references before or
   after.
9. **`uv.lock` and `pyproject.toml` dependencies are untouched** (only
   `pyproject.toml`'s prose `description` field changes). No `uv add`, no
   `uv sync` needed.

---

## 9. Error handling contract

| Condition | Behavior | User impact |
|---|---|---|
| A missed absolute import (`from spike.x import y` left behind) | `ModuleNotFoundError: No module named 'spike'` at import time | **Loud.** Test collection or entrypoint startup fails immediately. G1/G2 catch it first |
| A missed import in `shared/chat.py`, `shared/retrieval.py` or `run_chat.py` | No test imports these — the suite stays green | **Silent until a human runs `run_chat.py`.** This is exactly why G5 exists |
| `spike_config` alias renamed in `summary.py` but not in `tests/test_run_summary.py` | `AttributeError: module 'curation.summary' has no attribute 'spike_config'` | **Loud**, test fails |
| Human's `.env` still sets `SPIKE_MAX_ITEMS` / `SPIKE_PER_FEED` / `SPIKE_TOP_K` after merge | Keys are ignored; constants fall back to code defaults `8`/`5`/`4` | **Invisible today** — the `.env` values are *identical* to the defaults, so nothing observably changes. It becomes a real trap only if the human later edits those stale keys and wonders why nothing happens. §12 migration removes the trap |
| Human does not `mv .spike_cache .ai_radar_cache` | `CACHE_DIR` points at a new empty dir; `seen.json` is empty, so the JSON-backed dedup cache is orphaned | Next `uv run run_curation.py` with `CARD_STORE_BACKEND=json` re-summarizes up to `MAX_ITEMS` (8) already-seen items — **real Bedrock spend, ~$0.01**, plus duplicate cards in `cards.json`. `run_chat.py` also re-embeds the corpus. Recoverable by moving the directory. The `dynamo` backend is unaffected (it dedups via `BatchGetItem`, not `seen.json`) |
| Deployed AgentCore image not rebuilt after merge | Live image keeps the old code and old env keys; it still runs correctly | Docs describe `AI_RADAR_*` while the running image honors `SPIKE_*`. §12 makes the redeploy an explicit, optional step with this caveat stated |
| Stale `src/spike/__pycache__` left behind | Cannot make a deleted package importable in Python 3, but can confuse a reader/tool | Mitigated by the mandatory `__pycache__` sweep in G5 |
| Executor finds itself editing an assertion or a code path | **STOP and flag.** Do not proceed | Signals scope creep; the human decides |

---

## 10. Dependencies

- **Internal**: `curation.*` → `shared.*` (all 8 Plane-A modules);
  `runtime_app.py`, `run_curation.py`, `run_chat.py` → `shared.*`;
  `tests/*` → `shared.*`. `shared/*` modules depend only on each other, via
  relative imports.
- **External**: unchanged. No package added, removed, or re-pinned.
  `pyproject.toml` dependency lists and `uv.lock` are untouched.
- **Tooling**: no mypy/ruff/coverage/CI/Makefile config exists in this repo,
  so there is no type-checker or linter path to repoint. `pyproject.toml` has
  no `[tool.pytest]` section — tests reach `src/` via `sys.path` insertion in
  `tests/conftest.py:22`, which is path-relative (`parent.parent / "src"`) and
  therefore needs **no** edit.
- **Docker**: `Dockerfile` copies `src/` wholesale (`COPY src/ ./src/`) and
  never names a subpackage — no edit required. Verified against
  `tests/test_dockerfile.py`, which asserts nothing about `spike`.

---

## 11. Integration points

- **`src/curation/` (Plane A)** — 8 modules import `shared.*`; the compiled
  graph, node signatures and `RunSummary` are unchanged.
- **`runtime_app.py` (AgentCore entrypoint)** — one import line; the async
  handler, single-flight guard, `curation_run_complete` log record and EMF
  metrics are unchanged. The `curation_run_complete` record is append-only per
  `specs/run-observability` and this spec adds/renames **no** field in it.
- **`run_curation.py` / `run_chat.py`** — import lines; plus the one
  `run_chat.py` user-facing message (§5).
- **`infra/` (CDK)** — no integration point. Zero `spike` references; four
  deployed stacks must show no `cdk diff`.
- **`tests/`** — 7 files repointed; 145 tests, same IDs, same assertions.
- **Future monorepo move** (`docs/architecture-principles.md` §2) — `shared/`
  is the natural precursor to `packages/contracts` + a Plane-B app package,
  but this spec deliberately does **not** design or preempt that layout.

---

## 12. Migration + deployment contract

**Executor-owned** (in the merge): everything in §1-§6.

**Human-owned, manual** — the executor cannot edit an untracked `.env` or move
a gitignored directory on the human's machine. Precedent: the SNS
subscription click in `specs/run-observability`.

```bash
# 1. Preserve the real cached state (seen.json, cards.json, embeddings.json).
#    Do this BEFORE the next `uv run run_curation.py`, or dedup history is
#    orphaned and re-summarization costs real Bedrock spend (~$0.01).
mv .spike_cache .ai_radar_cache

# 2. Rename the three stale keys in the untracked local `.env`
#    (values are unchanged — 8 / 5 / 4):
#      SPIKE_MAX_ITEMS -> AI_RADAR_MAX_ITEMS
#      SPIKE_PER_FEED  -> AI_RADAR_PER_FEED
#      SPIKE_TOP_K     -> AI_RADAR_TOP_K
#    `.env.example` (tracked) is updated by the executor and can be diffed
#    against `.env` to confirm.

# 3. Verify locally (no AWS spend — reads the moved cache):
uv run python -c "
import sys; sys.path.insert(0,'src')
from shared import config
print(config.CACHE_DIR, config.MAX_ITEMS, config.PER_FEED, config.TOP_K)
print('seen entries:', len(__import__('json').loads(config.SEEN_PATH.read_text())))
"
```

**Optional, deferred to the human's discretion — redeploying the agent:**

```bash
agentcore deploy      # see the runtime-packaging runbook in README.md
```

Not required for correctness: the currently deployed image is a self-contained
container running the `run-observability` code, and it keeps working untouched
after this merge. But until it is rebuilt, **the live image reads the old
`SPIKE_*` keys while `README.md` documents `AI_RADAR_*`** — so any
`agentcore configure --env` re-targeting (README's "Re-target without a
rebuild" section) must use the *old* names until the redeploy happens. Since
neither key is currently set on the runtime (the agent runs on code defaults),
this has no live effect today. `README.md` must carry this caveat explicitly
rather than let the doc silently drift.

# Roadmap: tavily-discovery

## Implementation Phases

### Phase 1: Foundation — dependency + config knobs
**Goal**: Add the Tavily SDK and the env-overridable config seam. No discovery
logic yet.
**Dependencies**: None (Spec 01 already merged)
**Estimated complexity**: Low

(make sure the .venv is active: `uv sync`)

1. `uv add tavily-python` — updates `pyproject.toml` + `uv.lock`. Confirm
   `uv run python -c "from tavily import TavilyClient"` works.
2. ~~Verify the current Tavily `search()` params + response shape via Context7
   before coding.~~ **Done (2026-07-13, Context7 `/tavily-ai/tavily-python`):**
   `TavilyClient(api_key=...).search(query, search_depth, topic, days, max_results,
   include_domains, exclude_domains, include_raw_content, timeout)` → dict with
   `results[]` of `{title, url, content, score, raw_content?, published_date?}`.
   Pinned in contract.md. No rework expected.
3. Create `src/curation/config.py` with the Tavily knobs exactly as in contract.md
   (`TAVILY_API_KEY`, `TAVILY_SEEDS`, `TAVILY_RESULTS_PER_QUERY`,
   `TAVILY_MAX_RESULTS`, `TAVILY_DAYS`, `TAVILY_SEARCH_DEPTH`, `TAVILY_TOPIC`,
   `TAVILY_INCLUDE_DOMAINS`, `TAVILY_EXCLUDE_DOMAINS`). New module — do **not**
   edit `src/spike/config.py` (keep `src/spike/` untouched).
4. Add `TAVILY_API_KEY=` to `.env.example` (if one exists) / document it; ensure
   `.env` stays gitignored. Never commit a real key.

### Phase 2: Core Logic — TavilyDiscoverer + CompositeDiscoverer
**Goal**: Implement both `Discoverer`s behind the unchanged Protocol.
**Dependencies**: Phase 1
**Estimated complexity**: Medium

1. `src/curation/tavily.py`: implement `TavilyDiscoverer`:
   - `__init__` capturing seeds/api_key/keyword tunables (contract signature).
   - `from_config()` classmethod reading `curation.config`; raise `ValueError` if
     `TAVILY_API_KEY` empty.
   - Lazy singleton `TavilyClient` (mirror `spike.bedrock.bedrock_client()`).
   - `discover()`: per-seed `try/except Exception` (log + `failures += 1` +
     continue); map result dicts → `RawItem` via `spike.feeds._clean`
     (`title` limit 300, `snippet` default clamp); skip results missing
     `url`/`title`; within-source url_hash dedup; truncate to `max_results`.
   - `failures()` accessor.
   - The `tavily` SDK is imported **only** in this module.
2. `src/curation/composite.py`: implement `CompositeDiscoverer`:
   - `__init__(sources: list[Discoverer])`.
   - `discover()`: per-source `try/except Exception` (log + `failures += 1` +
     treat as `[]`); concatenate in source order; url_hash dedup first-wins.
   - `failures()` accessor.
   - Imports only `RawItem` and the `Discoverer` Protocol — SDK-agnostic.

### Phase 3: Integration — smoke entrypoint proving the seam
**Goal**: Run the *unchanged* Spec 01 graph with the composite against real
Tavily + real Bedrock.
**Dependencies**: Phase 2
**Estimated complexity**: Low

1. `run_tavily.py` (repo root): mirror `run_curation.py` — insert `src/` on
   `sys.path`, build
   `CompositeDiscoverer([RssDiscoverer(), TavilyDiscoverer.from_config()])` +
   `JsonFileCardStore(force="--force" in argv)`, `graph = build_graph(store,
   composite)`, `final = graph.invoke({"max_items": config.MAX_ITEMS})`, render
   cards and print counters (+ `discoverer.failures()`).
2. Manual smoke run: `uv run run_tavily.py` with a real `TAVILY_API_KEY` in `.env`.
   Confirm: web items appear with populated snippets, cross-source dups collapse,
   cards render, `.spike_cache/` writes. (Use `--force` / throwaway cache dir to
   avoid clobbering the RSS-only cache.)

### Phase 4: Testing & Validation
**Goal**: Prove every guarantee with the Tavily client fully stubbed — zero live
Tavily calls in pytest.
**Dependencies**: Phase 3
**Estimated complexity**: Medium

1. `tests/test_tavily.py` — monkeypatch the Tavily client/`search`:
   - result-dict → `RawItem` mapping (snippet from `content`, published from
     `published_date`/`""`, title/snippet cleaned);
   - per-run `max_results` cap enforced;
   - one seed raising → counted in `failures()`, others still returned, no raise;
   - all seeds raising / total outage → `[]`, no raise;
   - `from_config()` raises `ValueError` when `TAVILY_API_KEY` unset;
   - within-source url_hash dedup.
2. `tests/test_composite.py`:
   - merge two fake `Discoverer`s, url_hash dedup first-source-wins;
   - one source raising → degrades to the other's output, counted, no raise;
   - order preserved.
3. Seam test: `build_graph(FakeStore(), CompositeDiscoverer([...]))` with stubbed
   `bedrock.summarize` invokes end-to-end and produces cards — proving the Spec 01
   graph is unchanged and consumes the composite. (May live in `tests/test_composite.py`
   or extend `tests/test_graph.py` without editing existing cases.)
4. Portability test: assert `tavily` is not imported by `composite.py`, and
   `boto3` appears in none of this spec's modules.
5. `uv run pytest`; all green; update `audit.md` statuses.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Tavily `search()` params/response differ from assumed shape | ~~Med~~ **Resolved** | Med | Verified via Context7 2026-07-13; contract pins exact params + response; SDK isolated to `tavily.py` only |
| `published_date` absent for `topic="general"` breaks `RawItem.published` | Med | Low | Map via `.get("published_date", "")` → degrades to `""` like a dateless RSS entry (Guarantee, Error table) |
| Tavily SDK import leaks into node/graph/composite code (breaks portability) | Low | High | Guarantee 8 + a test asserting `tavily` only in `tavily.py`, no `boto3` anywhere |
| A Tavily outage/quota error kills the run | Med | High | Two-layer degrade: per-seed try/except in `TavilyDiscoverer`, per-source try/except in `CompositeDiscoverer`; both never raise; tests simulate failure |
| Cost overrun from unbounded results | Low | Med | `max_results` per-run cap (primary lever) + `search_depth="basic"` + `include_raw_content` off by default; dedup-before-summarize preserved |
| Live Tavily calls in the test suite (cost/flakiness/key needed in CI) | Med | Med | All tests monkeypatch the client; live calls only in the manual `uv run run_tavily.py` smoke |
| Same article summarized twice (RSS + Tavily) | Med | Med | Composite url_hash dedup before summarize (Guarantee 4/6); same rule as store |
| Editing the stable seam by accident | Low | High | `interfaces.py` untouched; seam test proves graph runs unchanged |
| A real key committed via `.env` | Low | High | `.env` gitignored; key only via env; no key in source; documented in `.env.example` |

## File Change Map

- `pyproject.toml` — MODIFY — add `tavily-python` via `uv add`.
- `uv.lock` — MODIFY — regenerated by `uv add` (source of truth for versions).
- `src/curation/config.py` — CREATE — Tavily config knobs (env-overridable).
- `src/curation/tavily.py` — CREATE — `TavilyDiscoverer` (only SDK import site).
- `src/curation/composite.py` — CREATE — `CompositeDiscoverer` (SDK-agnostic).
- `run_tavily.py` — CREATE — manual `uv run` smoke (real Tavily + Bedrock).
- `tests/test_tavily.py` — CREATE — `TavilyDiscoverer` unit tests (stubbed client).
- `tests/test_composite.py` — CREATE — `CompositeDiscoverer` + seam tests.
- `.env.example` — MODIFY/CREATE — document `TAVILY_API_KEY=` (no real value).
- `src/curation/interfaces.py` — UNCHANGED — stable `Discoverer` seam.
- `src/curation/{graph,nodes,state,local}.py` — UNCHANGED — Spec 01 code.
- `src/spike/**` — UNCHANGED — reference plane, do not edit.

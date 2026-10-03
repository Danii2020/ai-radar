# Tasks: tavily-discovery

> **Post-audit update (2026-07-15):** `run_tavily.py` (Task 3.1) was folded into
> `run_curation.py`, which now auto-selects `RssDiscoverer` alone vs
> `CompositeDiscoverer([RssDiscoverer(), TavilyDiscoverer.from_config()])` based
> on whether `TAVILY_API_KEY` is set — avoiding a near-duplicate entrypoint per
> `Discoverer` combination as Spec 03 adds another store choice. References to
> `run_tavily.py` below describe what was originally built; the smoke entrypoint
> is now `run_curation.py` (Task 3.2's live-Tavily smoke test still applies, run
> via `uv run run_curation.py` with `TAVILY_API_KEY` set).

## Legend
- [ ] Not started
- [x] Completed
- [~] In progress
- [!] Blocked

## Phase 1: Foundation — dependency + config knobs
- [x] Task 1.1: `uv add tavily-python`; verify `uv sync` + `uv run python -c "from tavily import TavilyClient"` — `pyproject.toml`, `uv.lock`
- [x] Task 1.2: Verify current Tavily `search()` params + response shape via Context7 before wiring — (no file; informs 2.1) — **already verified 2026-07-13 via Context7 (`/tavily-ai/tavily-python`): `TavilyClient(api_key=...).search(query, search_depth, topic, days, max_results, include_domains, exclude_domains, include_raw_content, timeout)` → `{"results":[{title,url,content,score,raw_content?,published_date?}], ...}`; pinned in contract.md**
- [x] Task 1.3: Create `src/curation/config.py` with the Tavily knobs per contract (`TAVILY_API_KEY`, `TAVILY_SEEDS`, `TAVILY_RESULTS_PER_QUERY`, `TAVILY_MAX_RESULTS`, `TAVILY_DAYS`, `TAVILY_SEARCH_DEPTH`, `TAVILY_TOPIC`, `TAVILY_INCLUDE_DOMAINS`, `TAVILY_EXCLUDE_DOMAINS`) — `src/curation/config.py` — do NOT edit `src/spike/config.py`
- [x] Task 1.4: Document `TAVILY_API_KEY=` in `.env.example` (no real value); confirm `.env` gitignored — `.env.example`

## Phase 2: Core Logic — TavilyDiscoverer + CompositeDiscoverer
- [x] Task 2.1: Implement `TavilyDiscoverer.__init__` + `from_config()` (raises `ValueError` if key unset) + lazy singleton `TavilyClient` (mirror `spike.bedrock.bedrock_client()`) — `src/curation/tavily.py`
- [x] Task 2.2: Implement `TavilyDiscoverer.discover()`: per-seed `try/except Exception` (log + `failures += 1` + continue); map result → `RawItem` via `spike.feeds._clean` (title limit 300, snippet clamp; `published = result.get("published_date","")`; skip missing url/title); within-source url_hash dedup; truncate to `max_results` — `src/curation/tavily.py`
- [x] Task 2.3: Implement `TavilyDiscoverer.failures()` accessor — `src/curation/tavily.py`
- [x] Task 2.4: Implement `CompositeDiscoverer.__init__(sources)` + `discover()` (per-source `try/except` → log/count/`[]`; concatenate in source order; url_hash dedup first-wins) + `failures()`; import only `RawItem` + `Discoverer` (SDK-agnostic) — `src/curation/composite.py`

## Phase 3: Integration — smoke entrypoint proving the seam
- [x] Task 3.1: Create `run_tavily.py` mirroring `run_curation.py`: sys.path inject, build `CompositeDiscoverer([RssDiscoverer(), TavilyDiscoverer.from_config()])` + `JsonFileCardStore(force="--force" in argv)`, `build_graph(store, composite)`, `graph.invoke({"max_items": config.MAX_ITEMS})`, render cards + print counters incl. `discoverer.failures()` — `run_tavily.py`
- [!] Task 3.2: Manual smoke run `uv run run_tavily.py` with real `TAVILY_API_KEY` in `.env` vs real Tavily + Bedrock; confirm web items with snippets, cross-source dedup, cards render, `.spike_cache/` writes (use `--force`/throwaway dir to avoid clobber) — deferred: implementing agent was instructed not to run this against the live Tavily API; user will run it manually with their real key

## Phase 4: Testing & Validation
- [x] Task 4.1: `TavilyDiscoverer` tests with stubbed client (T1, T2, T5, T6): result→`RawItem` mapping, `max_results` cap, `from_config()` ValueError on unset key, within-source url_hash dedup — `tests/test_tavily.py`
- [x] Task 4.2: `TavilyDiscoverer` resilience tests (T3, T4): one seed raises → counted + others returned + no raise; all seeds raise → `[]` no raise — `tests/test_tavily.py`
- [x] Task 4.3: `CompositeDiscoverer` tests (T7, T8): merge + url_hash dedup first-wins + order; one source raises → degrade to other + counted + no raise — `tests/test_composite.py`
- [x] Task 4.4: Seam test (T9): `build_graph(FakeStore(), CompositeDiscoverer([...]))` with stubbed `bedrock.summarize` invokes end-to-end → cards produced (proves Spec 01 graph unchanged) — `tests/test_composite.py`
- [x] Task 4.5: Portability test (T10): assert `tavily` imported only in `tavily.py`; `boto3` in none of this spec's modules — `tests/test_composite.py`
- [x] Task 4.6: Run `uv run pytest`; all green (27/27 — 16 Spec 01 + 11 new); `audit.md` status updates left for the auditor to confirm independently, per instructions

## Blocked Items
[None yet]

## Notes
- **Testing convention (carried from Spec 01):** unit tests must monkeypatch the
  Tavily client / `search` call — **no live Tavily calls in pytest**; live calls
  only in the manual `uv run run_tavily.py` smoke (Task 3.2). Mirror
  `specs/curation-graph/tasks.md`'s "monkeypatch `bedrock.summarize`" rule.
- **Do not modify the stable seam:** `src/curation/interfaces.py` is unchanged;
  the `Discoverer` Protocol shape is fixed. New code lives under `src/curation/`.
  Do not edit `graph.py`/`nodes.py`/`state.py`/`local.py` or `src/spike/**`.
- **Reuse, don't fork:** import `RawItem` + `_clean` from `spike.feeds`; mirror
  (do not edit) the `spike.config` knob pattern in a new `src/curation/config.py`.
- **Portability keystone:** the `tavily` SDK is imported ONLY in `tavily.py`; it
  must not appear in `composite.py`/`nodes.py`/`graph.py`/`state.py`. No `boto3`
  anywhere in this spec — Secrets Manager key resolution is deferred to Spec 04.
- **Cost discipline (§7):** `max_results` per-run cap is the primary lever;
  `search_depth="basic"` and `include_raw_content` off by default; cross-source
  dedup before summarize so no item is summarized twice.
- **Dedup rule:** `RawItem.url_hash` = `sha256(url.encode()).hexdigest()[:16]` —
  identical across RSS, Tavily, composite, and the store, so all layers agree.
- **Proposed defaults needing human confirmation** (see intent.md "Proposed
  defaults"): the 5 topic seed strings, results-per-query=5, per-run cap=20,
  days=7, search_depth="basic", topic="general", empty domain filters,
  raw_content off. All are env-overridable — adjust in config, not code.
- Defer entirely (other specs): Secrets Manager + CDK + IAM (Spec 04), DynamoDB
  dedup (Spec 03), embedding near-dup (Phase 3), AgentCore Browser, Exa/Brave.

## Completion

Implementation completed: 2026-07-15. Phases 1-4 done; `uv run pytest tests/`
green at 27/27 (16 pre-existing Spec 01 tests + 11 new tavily-discovery tests).
Task 3.2 (live smoke run) intentionally left for the user to run manually with
their real `TAVILY_API_KEY`, per task instructions.

# Intent: tavily-discovery

## Problem Statement

The Phase 1 curation graph (Spec 01, merged) discovers candidate items from a
fixed set of RSS/Atom feeds via the default `RssDiscoverer`. RSS gives reliable,
keyless coverage of *known* sources, but it is blind to anything those feeds do
not carry — trending releases, cross-source stories, and items that surface on
the open web before (or instead of) any curated feed. Design §5 (Plane A)
prescribes a second discovery mode: **seed queries per topic area → web search →
fetch content**, using a direct search API (Tavily) because §4 rates it cheaper
than AgentCore Browser for bulk fetching.

The affected party is the developer running the daily curation pipeline: today
the feed's breadth is capped by the `FEEDS` list. This feature broadens discovery
by adding a Tavily-backed `Discoverer` and composing it with RSS behind a single
`Discoverer` that the Spec 01 graph consumes **unchanged** — proving the Protocol
seam holds. Because the same article can appear in both RSS and Tavily, the
composite must remove cross-source URL-hash duplicates *before* items reach
summarization, so we never pay Haiku to summarize the same item twice (design §7).

## Goals

1. Add a `TavilyDiscoverer` implementing the Spec 01 `Discoverer` Protocol:
   topic-seeded Tavily search with content extraction, returning `RawItem`s in
   the exact shape RSS produces (`source`, `title`, `url`, `published`, `snippet`).
2. Make discovery cost- and breadth-tunable via env-overridable config knobs
   (topic seeds, results-per-query, recency filter, include/exclude domains) with
   a **hard per-run total result cap as the primary cost lever** (§7).
3. Add a `CompositeDiscoverer` implementing `Discoverer` that runs a list of
   `Discoverer`s (e.g. `[RssDiscoverer(), TavilyDiscoverer(...)]`), merges their
   results, and removes cross-source URL-hash duplicates before returning.
4. Guarantee per-source resilience: a Tavily outage / quota error / exception
   must not kill the run — the pipeline proceeds on RSS-only output with a logged
   message and a countable failure (mirrors Spec 01's per-item try/except).
5. Prove the seam: the *unchanged* Spec 01 graph, handed a `CompositeDiscoverer`,
   runs end-to-end with no edits to `graph.py`/`nodes.py`/`state.py`/`interfaces.py`.
6. Keep everything runnable via a manual `uv run` smoke entrypoint against the
   real Tavily API + real Bedrock; the automated test suite makes **zero** live
   Tavily calls.

## Success Criteria

(Maps to the brief's acceptance checklist in
`tasks/phase-1-curation-mvp/02-tavily-discovery.md`, narrowed to this phase's
local-only scope — see Non-Goals.)

- [ ] `TavilyDiscoverer.discover()` returns `RawItem`s with populated snippets
      from topic-seeded Tavily search, respecting the per-run total result cap.
- [ ] `CompositeDiscoverer.discover()` merges RSS + Tavily and removes URL-hash
      duplicates across sources before items reach summarization.
- [ ] The Spec 01 graph runs unchanged when handed a `CompositeDiscoverer`
      (`build_graph(store, CompositeDiscoverer([...]))` compiles and invokes; the
      seam holds).
- [ ] A simulated Tavily failure leaves the run healthy on RSS-only output, with
      the failure logged and counted.
- [ ] Topic seeds, results-per-query, recency, domain filters, and the total
      per-run cap are all config-driven (env-overridable).
- [ ] The Tavily API key is read from `TAVILY_API_KEY` (env / `.env`) only; it
      appears in no source or committed file.
- [ ] `uv run <smoke entrypoint>` builds the composite and runs the graph
      end-to-end against real Tavily + real Bedrock.

## Non-Goals

- **AWS Secrets Manager for the Tavily key, and any Secrets Manager runtime
  resolution — deferred to Spec 04 (`runtime-packaging`).** We are still Phase 0
  (local, no AWS infra) per the root `CLAUDE.md`; this spec resolves the key from
  the `TAVILY_API_KEY` env var / `.env` **only**. No `boto3.client("secretsmanager")`
  anywhere in this spec's code. (This narrows the brief's original in-scope
  "Secrets Manager + CDK construct" bullets, which now belong to Spec 04.)
- The Runtime IAM policy/grant that reads the secret (Spec 04).
- AgentCore Browser / JS-heavy page rendering (design §4 "optional"; only if a
  source blocks plain fetch — not MVP).
- Exa / Brave alternatives (open decision §9.1 settled as Tavily for this phase).
- Embedding-similarity near-dup detection (Phase 3); dedup here is exact URL-hash
  only, complementing the Spec 03 DynamoDB dedup.
- Any change to `src/curation/interfaces.py` — the `Discoverer` Protocol is the
  stable seam and this spec must not modify it.
- Any change to the graph/nodes/state, the Haiku summarize prompt/contract, or the
  `Card` schema.
- Modifying `src/spike/` — reused/imported, left intact (carried from Spec 01).

## Constraints

- **Do not modify the stable seam.** `src/curation/interfaces.py` (the
  `Discoverer` Protocol) is unchanged. New code lives under `src/curation/`
  alongside Spec 01's code. `RawItem`, `Card`, and the `spike.config` knob pattern
  are **reused/imported, not forked**.
- **Portability / infra-at-the-edges.** The Tavily SDK is an infra dependency; it
  appears **only** inside the `TavilyDiscoverer` adapter, never in
  `nodes.py`/`graph.py`/`state.py`. The composite/graph stay SDK-agnostic. No
  `boto3` in any of this spec's code.
- **Per-source resilience.** A single failing seed query, and a total Tavily
  outage, must both degrade gracefully — return what was fetched, never raise past
  the `Discoverer` boundary (Protocol contract: "Must not raise on a single bad
  source"). Mirror Spec 01's per-item try/except in `summarize_node`.
- **Cost discipline ($500 budget).** The per-run total result cap is the primary
  lever (design §7 budgets search at $0–25/mo). Dedup across sources before
  summarizing so no duplicate is ever summarized. Default `search_depth` favors
  the cheaper tier; `include_raw_content` defaults off (the `content` snippet is
  enough for Haiku).
- **Testing convention (carried from Spec 01).** Unit tests stub the Tavily
  client / HTTP call via monkeypatch — **zero live Tavily calls in pytest**. Live
  calls only in the manual `uv run` smoke entrypoint.
- **Tooling: uv only.** `uv add tavily-python`; never pip/venv/requirements.txt.
  `[tool.uv] package = false`, `src/` layout; the smoke entrypoint adds `src/` to
  `sys.path` (mirror `run_curation.py`).
- **Style.** Match the lean spike/curation conventions — small modules,
  dataclasses, lazy singleton client (mirror `spike.bedrock.bedrock_client()`),
  `from __future__ import annotations`, per-item try/except.
- **Ubiquitous language** (architecture-principles §3): `discover`, `dedup`,
  `Card`, `RawItem`, plane A. No new domain layers, aggregates, or repositories —
  no trigger fires here; this is an infra adapter + a composition helper.

## Proposed defaults (flag for human review)

These are the author's proposed starting values. They live in config
(env-overridable) so the reviewer can adjust without code changes. **Please
confirm or override before implementation:**

- **Topic seeds** (`CURATION_TAVILY_SEEDS`) — derived from design §5's topic areas
  (LLM, GenAI, ML, DL, agents, papers, releases):
  1. `"latest large language model releases and updates"`
  2. `"new generative AI and LLM research papers"`
  3. `"AI agents and agentic framework news"`
  4. `"machine learning and deep learning breakthroughs"`
  5. `"open source AI model and tooling releases"`
- **Results per query** (`CURATION_TAVILY_RESULTS_PER_QUERY`) = `5`
- **Per-run total cap** (`CURATION_TAVILY_MAX_RESULTS`) = `20` — **primary cost
  lever**; 5 seeds × 5 = 25 possible, capped to 20.
- **Recency** (`CURATION_TAVILY_DAYS`) = `7` (Tavily `days` param — last 7 days)
- **Search depth** (`CURATION_TAVILY_SEARCH_DEPTH`) = `"basic"` (cheaper tier;
  `"advanced"` available)
- **Topic** (`CURATION_TAVILY_TOPIC`) = `"general"` (`"news"` also available and
  populates a `published_date` per result — see contract)
- **Include/exclude domains** (`CURATION_TAVILY_INCLUDE_DOMAINS` /
  `..._EXCLUDE_DOMAINS`) = empty (no filtering) by default
- **Raw content** — off by default; the Tavily `content` field is used as the
  `RawItem.snippet` (no second fetch, cheaper). Flagged so the reviewer can opt
  into `include_raw_content` later if snippets prove too thin.

## Prior Art

- `src/curation/local.py` — `RssDiscoverer`, the existing `Discoverer` default;
  the style/pattern a new `Discoverer` implementation follows.
- `src/curation/interfaces.py` — the `Discoverer` Protocol (stable seam,
  unchanged): `discover(self) -> list[RawItem]`, must not raise on a bad source.
- `src/spike/feeds.py` — `RawItem` dataclass (`source`, `title`, `url`,
  `published`, `snippet`, `url_hash = sha256(url)[:16]`) and `_clean()` for
  snippet normalization; both reused.
- `src/spike/bedrock.py` — `bedrock_client()` lazy-singleton pattern the
  Tavily client construction mirrors.
- `src/spike/config.py` — the env-overridable module-level constant pattern the
  new Tavily config mirrors.
- `run_curation.py` — the `sys.path`-injecting `uv run` entrypoint the smoke
  entrypoint mirrors.
- `specs/curation-graph/` — the reference spec set (structure, tone, testing
  convention: monkeypatch external calls, no live network/API in pytest).
- Design `docs/app-design-on-agentcore.md` §4 (search API cheaper than Browser),
  §5 (seed → search → fetch), §7 (search budget $0–25/mo; never summarize twice).

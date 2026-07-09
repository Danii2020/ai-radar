# Spec 02 — Tavily + RSS discovery

- **feature-name:** `tavily-discovery`
- **SDD target dir:** `specs/tavily-discovery/`
- **Depends on:** Spec 01 (`Discoverer` Protocol, `RawItem`)
- **Layer:** Logic / ingestion

## Intent

Broaden discovery beyond curated feeds by adding **Tavily web search** alongside
the existing **RSS** source, so the daily run surfaces trending items that no
single feed carries. The two sources are combined behind one **composite
`Discoverer`** that the Spec 01 graph consumes unchanged — RSS gives reliable,
keyless coverage of known sources; Tavily gives breadth via topic-seeded search +
content extraction. This realizes the "Seed queries per topic area → Search →
Fetch content" step in design §5.

## Background

Design §5 (Plane A): seed queries per topic area (LLM, GenAI, ML, DL, agents,
papers, releases) → Tavily/Exa search → candidate URLs + snippets → fetch page
content (search API content mode). Design §4 says a **direct search API is cheaper
than AgentCore Browser** for bulk fetching, and recommends **Secrets Manager** (over
AgentCore Identity/Token Vault) for the API key at this scale. §7 budgets the search
API at **$0–25/mo** (free tier → light paid usage). Spec 01 already defines the
`Discoverer` Protocol with an RSS default and the `RawItem` shape; this spec adds a
Tavily impl and a composite that merges both.

## Scope

**In scope**
- A `TavilyDiscoverer` implementing the Spec 01 `Discoverer` Protocol, returning
  `RawItem`s (same shape RSS produces: source, title, url, published, snippet).
  - **Topic seeds**: a configurable list of query strings / topic areas (config,
    env-overridable like the spike's `FEEDS`).
  - Use Tavily **search with content extraction** so each result yields a usable
    snippet without a second fetch (prefer this over AgentCore Browser — §4).
  - Tunables: results-per-query, recency/time filter, include/exclude domains,
    and a hard cap on total results per run (cost control — §7).
- A `CompositeDiscoverer` (or equivalent) that runs RSS + Tavily and returns the
  merged `RawItem` list. **Cross-source dedup by URL hash before summarizing** so
  the same article from RSS and Tavily is summarized once (design §7: never pay to
  summarize the same item twice) — this complements the Spec 03 DynamoDB dedup.
- **Secret management for the Tavily API key**: store in **AWS Secrets Manager**;
  resolve at runtime; for local `uv run`, fall back to a `TAVILY_API_KEY` env var
  (`.env`). Never hardcode; never commit the key. Add the secret name to config.
- A CDK construct for the Secrets Manager secret (value supplied out-of-band, not
  in code). The Runtime IAM role grant for it is owned by Spec 04.
- Per-source resilience: a Tavily outage or quota error must not kill the run — the
  graph still proceeds with RSS results (log + counter, same pattern as Spec 01).
- Add `tavily-python` (or call the REST API) via `uv add`.

**Out of scope**
- AgentCore Browser / JS-heavy page rendering (design §4 "optional"; only if a
  source blocks plain fetch — not MVP).
- Exa / Brave alternatives (open decision §9.1 settled as Tavily for this phase).
- Embedding-similarity near-dup detection (Phase 3).
- The Runtime IAM policy that reads the secret (Spec 04 adds the grant).

## Contract sketch

```python
class TavilyDiscoverer:                 # implements Discoverer (Spec 01)
    def __init__(self, seeds: list[str], api_key: str, *, max_results: int): ...
    def discover(self) -> list[RawItem]: ...

class CompositeDiscoverer:              # implements Discoverer
    def __init__(self, sources: list[Discoverer]): ...
    def discover(self) -> list[RawItem]: ...   # merged + URL-hash-deduped
```

## Acceptance criteria

- [ ] `TavilyDiscoverer.discover()` returns `RawItem`s with populated snippets from
      topic-seeded Tavily search, respecting the per-run result cap.
- [ ] `CompositeDiscoverer` merges RSS + Tavily and removes URL-hash duplicates
      across sources before items reach summarization.
- [ ] The Spec 01 graph runs unchanged when handed a `CompositeDiscoverer` (proves
      the Protocol seam holds).
- [ ] The Tavily key is read from Secrets Manager in the cloud and from
      `TAVILY_API_KEY`/`.env` locally; it appears in no source or committed file.
- [ ] A simulated Tavily failure leaves the run healthy on RSS-only output, with the
      failure logged/counted.
- [ ] Recency, results-per-query, domain filters, and total cap are config-driven.

## SDD note

Feed to `sdd-architect` as `tavily-discovery`. Pull **current Tavily API/SDK docs
via Context7 MCP** before authoring the contract (search params, content extraction
mode, response shape) — per global rules, don't rely on memory for the API surface.
Pin the **per-run result cap** in the contract as the primary cost lever (§7).

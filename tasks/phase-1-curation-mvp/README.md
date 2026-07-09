# Phase 1 — Curation MVP

> Source design: [`docs/app-design-on-agentcore.md`](../../docs/app-design-on-agentcore.md) §8 (Build Phases).
> Builds directly on the **Phase 0 spike** (`src/spike/`, `run_spike.py`).

## Goal

Turn the local Phase 0 spike loop into an **automated daily feed**: a LangGraph
discovery graph running on **AgentCore Runtime**, triggered by **EventBridge
Scheduler**, writing curated cards to **DynamoDB**.

Phase 0 proved the loop end-to-end against real Bedrock with zero infra. Phase 1
is the first phase that stands up AWS infrastructure. The deliverable is: *"every
day, without me running anything, fresh AI-news cards land in DynamoDB, deduped
and ranked."*

```
EventBridge Scheduler ──(daily)──► AgentCore Runtime (microVM)
                                     └─ LangGraph curation graph
                                          discover (RSS + Tavily) → dedup → summarize → tag/score → rank → persist
                                                                                                            │
                                                                                                            ▼
                                                                                                      DynamoDB cards
```

## Scoping decisions (carried from the design + CLAUDE.md)

These keep Phase 1 lean and faithful to the deferral list in `CLAUDE.md`. Change
them here if you disagree before specs are authored.

| Decision | Choice for Phase 1 | Why |
|---|---|---|
| **Discovery source** | **RSS/Atom + Tavily web search** (composite) | RSS for reliable known-source coverage; Tavily for breadth on trending items (design §5). Exa/Brave not used this phase |
| **Search API secret** | **Tavily API key in AWS Secrets Manager** (env/`.env` locally) | Design §4 recommends Secrets Manager over Token Vault at this scale |
| **Vector store / embeddings** | **No embedding *computation* in Phase 1**, but the architecture is decided: vectors live **inline on the card item** (reserve an `embedding` list attribute, left empty), for **brute-force cosine over DynamoDB** later — never a dedicated vector DB at this scale | CLAUDE.md defers embedding *work* to Phase 3, but pinning the inline-vector shape now avoids a Phase 3 schema migration. Brute-force over a few-thousand-card corpus is ~$0 and ms-fast; dedicated vector DBs (Pinecone/pgvector/OpenSearch) are a scale tool, not a starter tool — see cross-phase decisions below |
| **Dedup strategy** | **URL-hash exact dedup** against DynamoDB (no embedding similarity yet) | Matches spike behavior; embedding-similarity dedup waits for Phase 3 embeddings |
| **Cadence** | **Daily** (EventBridge Scheduler) | Design §5; cheapest cadence that keeps the feed fresh |
| **IaC tool** | **AWS CDK (Python)** for DynamoDB + EventBridge + IAM; AgentCore **starter toolkit** for Runtime/ECR | Python-native to match the repo; starter toolkit owns the container build |
| **Tenancy** | **Single-user** (no Cognito/LTM) | Personalization is Phase 4 |

## Architecture decisions (cross-phase)

These came out of an optimization / cost / scalability review and shape Phase 1
even where they bite in later phases. Recorded here so the data shapes and platform
choices are locked before the executor runs.

1. **Plane separation is a hard CQRS split.** Plane A (curation) and Plane B
   (chat) share *only* the data stores — never a process, deploy, or scaling
   policy. Plane A is write-side and latency-insensitive; Plane B is read-side and
   interactive. Everything below preserves this.

2. **Vector store = brute-force cosine over DynamoDB, vector stored inline on the
   card.** A 256-dim Titan vector is ~1 KB; a few-thousand-card corpus is a few MB,
   searchable in single-digit ms for **~$0**. Do **not** stand up OpenSearch
   Serverless (~$700/mo floor — the budget-killer) or an idle Aurora/pgvector
   (~$43/mo floor) for this scale. *Trigger to revisit:* corpus > ~50k cards **or**
   sustained high chat QPS → move to Pinecone serverless / LanceDB / pgvector. The
   store is swappable by design, so this is a cheap decision to defer.

3. **Don't optimize Plane A compute — it's ~$0–10/mo either way.** AgentCore
   Runtime + LangGraph stays the choice (one platform, I/O-wait billing, a future
   path to *agentic* discovery). The Spec 01 portability guarantee means the graph
   lifts to Lambda/Step Functions later with near-zero rework if that ever pays off.
   Spend the optimization budget on the vector store and chat caching instead.

4. **Prompt caching on chat from day one (Phase 3).** Cache the stable prefix
   (system prompt + retrieved card context) for up to 90% off input tokens — the
   dominant chat cost lever. Sonnet only in chat; Haiku for all bulk summarization.

5. **Embed once, reuse twice.** When Phase 3 computes embeddings, the same inline
   vector serves both retrieval (RAG) and similarity-dedup. Cache embeddings; only
   embed *new* cards. (Spec 03 reserves the inline `embedding` attribute for exactly
   this.)

6. **Cost target:** ~$30–50/mo at lean MVP (brute-force vector avoids the Aurora
   floor) → **10+ months** of runway on $500. Figures trace to the research doc's
   April-2026 pricing — verify against live Bedrock/AgentCore pricing before
   committing.

## Subtask specs (build order)

Each file below is a **spec brief** meant to be handed to the SDD workflow
(`sdd-architect` → `sdd-executor` → `sdd-test-writer` → `sdd-auditor`). The
`feature-name` in each brief is the slug for `specs/<feature-name>/`.

| # | Spec | feature-name | Depends on | Layer |
|---|---|---|---|---|
| 01 | [LangGraph curation graph](01-langgraph-curation-graph.md) | `curation-graph` | — (spike) | Logic |
| 02 | [Tavily + RSS discovery](02-tavily-discovery.md) | `tavily-discovery` | 01 | Logic / ingestion |
| 03 | [DynamoDB card store](03-dynamodb-card-store.md) | `dynamodb-card-store` | 01 | Data |
| 04 | [AgentCore Runtime packaging](04-agentcore-runtime-packaging.md) | `runtime-packaging` | 01, 02, 03 | Infra |
| 05 | [EventBridge daily schedule](05-eventbridge-daily-schedule.md) | `eventbridge-schedule` | 04 | Infra |
| 06 | [Run observability](06-run-observability.md) | `run-observability` | 01–05 | Cross-cutting |

**Dependency notes.** 01 is the keystone refactor and keeps running locally
(`uv run`). 02 (Tavily) and 03 (DynamoDB) both plug into Protocols 01 defines
(`Discoverer` / `CardStore`) and can be built in parallel after 01. 04 packages the
result — composite discoverer + Dynamo store — for Runtime and adds the Secrets
Manager grant for the Tavily key; 05 schedules it; 06 instruments it. Ship
01→02→03 first (a local graph that pulls RSS + Tavily and writes to DynamoDB is
already a useful milestone), then 04→05 to take it serverless, then 06.

## How to drive each spec through SDD

For each subtask, in order:

```
1. sdd-architect   — feed it the brief; it writes intent/contract/roadmap/audit/tasks
                     to specs/<feature-name>/
2. sdd-executor    — implements against the spec, checks off tasks
3. sdd-test-writer — writes tests for every contract guarantee
4. sdd-auditor     — validates implementation vs spec, runs tests, writes audit.md
```

## Definition of done for Phase 1

- [ ] The curation loop is a LangGraph graph, logic still portable (no infra coupling in node functions).
- [ ] Discovery pulls from both RSS feeds and Tavily web search, deduped across sources.
- [ ] Running the graph writes deduped, ranked cards to a DynamoDB table; re-runs are idempotent.
- [ ] The graph is deployed to AgentCore Runtime and invocable.
- [ ] An EventBridge Scheduler rule invokes it daily with no human in the loop.
- [ ] Each run emits structured logs + a run-summary (counts, tokens/cost) to CloudWatch.
- [ ] All infra is reproducible from code (CDK + starter toolkit), tear-down documented.
- [ ] Cost stays within the lean-MVP envelope (design §7); no OpenSearch Serverless.

# AI Radar — High-Level Design on Amazon Bedrock AgentCore

> Working name: **AI Radar** (placeholder)
> Design date: 2026-06-02
> Companion doc: [`amazon-bedrock-agentcore-research.md`](./amazon-bedrock-agentcore-research.md)
> Budget anchor: **$500 in AWS credits**

---

## 1. The App in One Paragraph

A web app that keeps people up to date with the AI / GenAI / LLM / ML / DL world **in one centralized place**, so they don't have to crawl the internet, X, Reddit, newsletters, and papers themselves. The app continuously discovers the latest, trending, and most relevant topics, news, concepts, and projects, then presents each as a **card** (title + source link + AI-generated summary + tags + date). A built-in **chatbot** lets users ask questions and dig deeper into any topic, grounded in the content the app has collected.

Two distinct workloads hide inside that sentence:

| Plane | What it does | Cadence | Agentic pattern |
|---|---|---|---|
| **A. Curation pipeline** | Discover → fetch → dedup → summarize → tag → rank → store | Scheduled (e.g. every 6–24 h) | Multi-step, autonomous, deterministic-ish workflow |
| **B. Serving / chat** | Serve the feed + answer questions via RAG over collected content | On user request | Conversational, memory-backed RAG agent |

Keeping these two planes separate is the single most important architectural decision — they have different scaling, cost, and reliability profiles.

---

## 2. Feasibility Verdict (TL;DR)

**Yes — this is a strong, realistic fit for AgentCore + LangGraph, and it fits inside $500 if you stay lean.**

- The **curation pipeline** is a textbook agentic workflow (search → reason → summarize → store). LangGraph for the logic, AgentCore Runtime to host/run it on a schedule.
- The **chatbot** is a textbook RAG-over-your-own-data agent. AgentCore Runtime + AgentCore Memory give you conversation memory and session isolation for free.
- The honest caveat: AgentCore is **enterprise-grade infra**. For a personal/low-traffic app, several pieces (Identity, Gateway, Browser, Evaluations) are optional. Use them only where they pay for themselves, or this becomes an expensive way to run a cron job + a chatbot.
- **The one budget-killer to avoid**: OpenSearch Serverless / Bedrock Knowledge Bases default vector backing (~$700/mo minimum). It would vaporize $500 in under a month. See §7.

---

## 3. Target Architecture (High Level)

```
                        ┌─────────────────────────────────────────────┐
                        │                 USERS (web)                  │
                        └───────────────────────┬─────────────────────┘
                                                │
                                  ┌─────────────▼─────────────┐
                                  │   Frontend (Next.js)       │
                                  │   S3+CloudFront / Amplify  │
                                  │   or Vercel (free)         │
                                  └─────────────┬─────────────┘
                                                │ HTTPS / WebSocket
                          ┌─────────────────────▼──────────────────────┐
                          │   API layer (API Gateway + Lambda)          │
                          │   Auth: Amazon Cognito                      │
                          └───────┬───────────────────────────┬────────┘
                                  │ feed reads                │ chat
                                  │                           │
              ┌───────────────────▼──────┐      ┌─────────────▼───────────────────┐
              │  Topic store (DynamoDB)  │      │  PLANE B: Chat Agent             │
              │  cards: title, url,      │◄─────│  AgentCore Runtime (microVM)     │
              │  summary, tags, date,    │      │  + LangGraph RAG agent           │
              │  score, embedding ref    │      │  + AgentCore Memory (STM + LTM)  │
              └───────────────────▲──────┘      │  + Bedrock (Claude Sonnet/Haiku) │
                                  │             └─────────────┬───────────────────┘
                                  │ writes                    │ retrieve
                                  │                  ┌────────▼─────────┐
       ┌──────────────────────────┴──────┐          │  Vector store    │
       │  PLANE A: Curation Pipeline      │─────────►│  pgvector /      │
       │  AgentCore Runtime (microVM)     │ embed +  │  Pinecone /      │
       │  + LangGraph discovery graph     │ upsert   │  LanceDB         │
       │  + Bedrock (Claude Haiku)        │          └──────────────────┘
       │  Tools: web search API, fetch    │
       └──────────────────────────────────┘
                     ▲
                     │ trigger on schedule
              ┌──────┴───────┐
              │ EventBridge  │  (e.g. every 6–24h)
              │  Scheduler   │
              └──────────────┘
```

---

## 4. How Each Piece Maps to AgentCore

| Need | AgentCore / AWS service | Use it? | Why / Notes |
|---|---|---|---|
| Run the discovery workflow on a schedule | **AgentCore Runtime** invoked by **EventBridge Scheduler** | ✅ Core | MicroVM per run; "I/O wait is free" billing is ideal since the pipeline waits on web fetches + LLM calls |
| Orchestrate discovery steps (search→fetch→dedup→summarize→rank) | **LangGraph** (logic layer) running on Runtime | ✅ Core | Explicit state machine fits the multi-step, branchy workflow far better than the managed harness |
| Host the chatbot | **AgentCore Runtime** | ✅ Core | Session isolation + suspend/resume + streaming responses for free |
| Conversation memory + "remember what I care about" | **AgentCore Memory** (STM in-session, LTM across sessions) | ✅ Core | LTM lets the bot learn a user's interests over time → better personalization. Mind the 7-day retention floor |
| Summarization & chat generation | **Bedrock** (Claude **Haiku 4.5** for bulk summaries, **Sonnet 4.6** for chat) | ✅ Core | Haiku for cheap high-volume summaries; Sonnet only where quality matters |
| Web discovery / search | **Web search API** (Tavily / Exa) via a tool, OR **AgentCore Gateway** to wrap it | ⚠️ Pick one | A direct search API is cheaper than AgentCore Browser for bulk fetching. Use **Browser** only for JS-heavy sites that block plain fetch |
| Render JS-heavy pages / login-walled sources | **AgentCore Browser** | 🔶 Optional | Powerful but billed per active session — use sparingly |
| Turn internal/3rd-party APIs into agent tools | **AgentCore Gateway** | 🔶 Optional | Only worth it once you have several tools or need managed OAuth rotation. Skip for MVP |
| Manage secrets (search API keys, etc.) | **AgentCore Identity / Token Vault** *or* plain **AWS Secrets Manager** | 🔶 Optional | Token Vault is nice but Secrets Manager is simpler/cheaper at this scale |
| Run analysis/charts inside chat | **AgentCore Code Interpreter** | 🔶 Optional | Nice-to-have ("plot paper counts by week"); not MVP |
| Feed cards / structured records | **DynamoDB** (on-demand) | ✅ Core | Cheap, serverless, scales to zero cost at low traffic |
| Vector store for RAG | **pgvector** (Aurora Serverless v2 / RDS) **or Pinecone serverless** **or LanceDB** | ✅ Core | ⚠️ **Do NOT** default to OpenSearch Serverless — see §7 |
| Embeddings | **Bedrock Titan Text Embeddings v2** | ✅ Core | ~$0.02 / 1M tokens — negligible |
| Frontend hosting | **S3 + CloudFront / Amplify** or **Vercel free tier** | ✅ Core | Vercel free keeps it off the AWS bill |
| API + Auth | **API Gateway + Lambda + Cognito** | ✅ Core | Generous free tiers; pennies at low traffic |
| Quality monitoring | **AgentCore Observability / Evaluations** | 🔶 Optional | Useful later to measure summary quality / answer relevance. **No free tier — sample heavily** |

---

## 5. Data Flow

### Plane A — Curation pipeline (scheduled)
1. **EventBridge Scheduler** triggers the AgentCore Runtime endpoint.
2. **LangGraph discovery graph** runs:
   - **Seed** queries per topic area (LLM, GenAI, ML, DL, agents, papers, releases…).
   - **Search** via Tavily/Exa → candidate URLs + snippets.
   - **Fetch** page content (search API content mode, or Browser for hard cases).
   - **Dedup** against DynamoDB (URL hash + embedding similarity) to skip what's already collected.
   - **Summarize** each new item with **Claude Haiku 4.5** (title-normalize, 2–4 sentence summary, key takeaways).
   - **Tag & classify** (topic area, type: news/paper/project/concept).
   - **Score relevance/trendiness** (recency, source weight, cross-source frequency).
   - **Embed** summary (Titan v2) → **upsert** to vector store.
   - **Write** card to DynamoDB.
3. Idempotent: safe to re-run; dedup prevents duplicates.

### Plane B — Serving + chat (on demand)
1. User loads feed → API Gateway → Lambda → query DynamoDB (sorted by score/date) → return cards.
2. User opens chat → frontend opens session against **AgentCore Runtime** chat agent.
3. **LangGraph RAG agent**:
   - Pull conversation context from **AgentCore Memory (STM)**; load user-interest profile from **LTM**.
   - Embed the question → **retrieve** top-k from vector store → fetch matching DynamoDB cards.
   - Generate grounded answer with **Claude Sonnet 4.6**, citing source links.
   - Write salient facts/interests back to **LTM**.

---

## 6. Division of Labor: AgentCore vs LangGraph

This is the "gold standard" 2026 pattern from the research doc — they're complementary, not competing.

| Concern | Owned by |
|---|---|
| Workflow logic, branching, retries, state | **LangGraph** (logic layer) |
| Where/how the agent physically runs, scaling, isolation | **AgentCore Runtime** (infra layer) |
| Conversation + long-term user memory | **AgentCore Memory** |
| Secrets, auth to external APIs | AgentCore Identity *or* Secrets Manager |
| Model inference | **Bedrock** |
| Scheduling | **EventBridge** |
| Feed + vector data | DynamoDB + pgvector/Pinecone |

You could skip LangGraph and use AgentCore's **managed harness** for the chatbot (declare model + tools, no orchestration code). Recommended approach: **harness for the simple chatbot, LangGraph for the multi-step curation pipeline.**

---

## 7. Finance — Will $500 Last? (Grounded Estimate)

> All figures are **planning estimates** at low/personal traffic. Verify against the live [AgentCore pricing page](https://aws.amazon.com/bedrock/agentcore/pricing/) and [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/) before committing. Region: us-west-2 / us-east-1.

### Unit prices used (April 2026)
| Resource | Price |
|---|---|
| Claude **Haiku 4.5** | **$1** / 1M input, **$5** / 1M output |
| Claude **Sonnet 4.6** | **$3** / 1M input, **$15** / 1M output |
| Titan Text Embeddings v2 | ~$0.02 / 1M tokens |
| AgentCore Runtime — CPU | **$0.0895** / vCPU-hour (active only) |
| AgentCore Runtime — Memory | **$0.00945** / GB-hour |
| AgentCore Memory (LTM) | ~**$0.25** / 1K records (+ model usage billed separately) |
| Prompt caching | up to **90% off** cached input |
| Batch inference | **50% off** (great for nightly summarization) |

### Worked monthly estimate — "Lean MVP" (single user / small private beta)
Assumptions: ~80 new items/day summarized; ~200 chat turns/month; pipeline runs daily.

| Line item | Assumption | Est. / month |
|---|---|---|
| Summarization (Haiku) | 80/day × ~3k in + 0.4k out ≈ 7.2M in + 1M out / mo | **~$12** |
| Chat generation (Sonnet) | 200 turns × ~5k in + 0.6k out | **~$5** |
| Embeddings (Titan v2) | a few M tokens / mo | **~$1** |
| AgentCore Runtime (both planes) | mostly I/O wait (free); little active CPU | **~$5–10** |
| AgentCore Memory | low volume STM + LTM | **~$1–2** |
| Web search API (Tavily/Exa) | free tier → light paid usage | **$0–25** |
| DynamoDB (on-demand) | low traffic | **~$1** |
| Vector store — **pgvector on Aurora Serverless v2** | min ~0.5 ACU always-on | **~$43** |
| API GW + Lambda + Cognito | within/near free tier | **~$0–3** |
| Frontend (Vercel free / S3+CF) | static | **~$0–3** |
| **TOTAL (lean)** | | **≈ $70–105 / mo** |

**Runway on $500: roughly 5–7 months** at lean MVP usage — comfortably enough to build, validate, and learn.

### The biggest single lever: the vector store
| Option | ~Monthly fixed cost | Verdict for $500 budget |
|---|---|---|
| **OpenSearch Serverless / Bedrock KB default** | **~$700+** | ❌ Avoid — burns the whole budget in <1 month |
| Aurora Serverless v2 + pgvector | ~$43 (0.5 ACU min) | ✅ Solid default |
| **Pinecone serverless (free/starter)** | $0–small | ✅ Cheapest to start; off the AWS bill |
| **LanceDB / Chroma** (file-based, on Runtime or S3) | ~$0 + storage | ✅ Great for a small corpus; least ops-friendly |
| DynamoDB + brute-force cosine (tiny corpus) | ~$0 | ✅ Fine for a few thousand cards early on |

> **Recommendation:** start with Pinecone free tier or DynamoDB brute-force, move to pgvector/Aurora only when the corpus grows. This alone can cut the bill from ~$100 to ~$30–50/mo and stretch $500 toward **10+ months**.

### Cost-control levers (apply from day one)
- **Haiku for bulk summarization**, Sonnet only for chat.
- **Batch inference (50% off)** for the nightly summarization run — it's not latency-sensitive.
- **Prompt caching (up to 90% off)** for the chatbot's stable system prompt + retrieved context.
- **Dedup before summarizing** — never pay to summarize the same item twice.
- **Sample observability** (no free tier) — 5–10% traces is plenty early.
- **Skip Gateway/Identity/Browser/Code Interpreter** until a concrete need appears.
- **Set an AWS Budget alert at $50/$100/$250** so credits can't silently drain.
- Avoid VPC/PrivateLink unless required (cross-AZ egress = surprise charges).

---

## 8. Suggested Build Phases

| Phase | Goal | Scope |
|---|---|---|
| **0. Spike** | Prove the loop end-to-end | One topic, Tavily search + Haiku summary → print to console (local, no infra) |
| **1. Curation MVP** | Automated daily feed | LangGraph discovery graph on AgentCore Runtime + EventBridge → DynamoDB cards |
| **2. Web feed** | See the cards | Next.js feed reading DynamoDB via API Gateway/Lambda |
| **3. Chatbot** | Talk to the data | AgentCore Runtime chat agent + Memory + RAG over vector store |
| **4. Personalization** | "Topics I care about" | Use AgentCore Memory LTM to weight feed + chat per user; Cognito auth |
| **5. Quality loop** | Measure & improve | AgentCore Evaluations (sampled) on summary quality + answer relevance |

Ship Phase 1–3 first; that's a usable product. Everything after is enhancement.

---

## 9. Risks & Open Decisions

**Risks**
- **AWS lock-in** — deep coupling to Bedrock/IAM/Runtime. Mitigated by keeping LangGraph logic portable and the vector store swappable.
- **Content/copyright** — summarizing + linking is generally fine; **store summaries and links, not full scraped articles**, and always attribute the source.
- **Source quality / hallucination** — ground every chat answer in retrieved cards with citations; never let the bot answer from model memory alone.
- **Token rate limit** (200K input tokens/min, non-adjustable) — a non-issue at MVP scale; relevant only if summarization fan-out gets huge.
- **Memory 7-day retention floor** — fine here; just set `EventExpirationDuration` deliberately.

**Open decisions (let's pick before Phase 1)**
1. **Search source**: Tavily vs Exa vs Brave Search API (cost, quality, content-extraction).
2. **Vector store**: Pinecone free vs pgvector/Aurora vs DynamoDB brute-force to start.
3. **Single-user vs multi-user** at launch (drives whether Cognito + LTM personalization is in MVP).
4. **Chatbot engine**: AgentCore managed harness (simplest) vs LangGraph RAG agent (more control).
5. **Feed cadence**: how fresh must it be — hourly, 6-hourly, daily? (Drives compute + search cost.)

---

## 10. Bottom Line

- **Feasible and well-matched.** The app decomposes cleanly into a scheduled agentic curation pipeline + a RAG chatbot — both first-class patterns on AgentCore.
- **Use AgentCore for what it's good at** (managed runtime, isolation, memory) and **LangGraph for the workflow logic**; skip the enterprise extras until you need them.
- **$500 is enough** to build and run a lean MVP for **~5–10+ months**, *if* you dodge the OpenSearch Serverless trap and lean on Haiku + batch + caching.
- Recommended next step: a tiny **Phase 0 spike** (one topic, search→summarize, local) to validate quality before any AWS infra goes up.

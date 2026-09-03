# Phase 2 — Web Feed

> Source design: [`docs/app-design-on-agentcore.md`](../../docs/app-design-on-agentcore.md) §8 (Build Phases).
> Builds on **Phase 1** (`tasks/phase-1-curation-mvp/`) — consumes its output
> (`ai-radar-cards` DynamoDB table) read-only; touches nothing under
> `src/curation/` or `src/shared/` except promoting `Card` to a shared,
> validated schema (see Architecture decision 1 below).

## Goal

Turn the curated cards sitting in DynamoDB into something a human can actually
look at: a **Next.js feed**, sorted by relevance/date, reading through a real
**API Gateway + Lambda** read API. Phase 1's deliverable was "cards land in
DynamoDB unattended"; Phase 2's is *"I can open a URL and see them."*

Plane B (chat) is explicitly **out of scope** — that's Phase 3. Phase 2 is
read-only, no LLM calls, no AgentCore Runtime involvement at all: pure
CRUD-shaped serving on top of data Plane A already produced.

```
Browser ──► Next.js (Vercel) ──► API Gateway ──► Lambda ──► DynamoDB
                                                              (ai-radar-cards,
                                                          feed-by-score GSI —
                                                          already provisioned
                                                          by dynamodb-card-store)
```

## Scoping decisions

Locked in before specs are authored. Change them here if you disagree.

| Decision | Choice for Phase 2 | Why |
|---|---|---|
| **Read API** | **API Gateway + Lambda** (Python) | Matches the design doc and `architecture-principles.md`'s future `apps/curation` / `apps/api` / `apps/web` split — a real, versioned API contract any client can consume, not logic buried inside the frontend. Near-free at this traffic. |
| **Frontend hosting** | **Vercel free tier** | Simplest turnkey path for a Next.js app (SSR/ISR, previews, zero config); off the AWS bill entirely so it doesn't touch the $500 credit. |
| **Feed scope** | **Sorted list + tag/topic filter** | Matches design §8's minimal "see the cards" goal, plus the one filter dimension Plane A already produces (`Card.tags`). No per-card detail/permalink page, no infinite personalization — that's Phase 4. |
| **Sort/query path** | **`feed-by-score` GSI** (`gsi_pk="CARD"`, `gsi_sk=f"{relevance:03d}#{published}"`) | Already provisioned and populated by `dynamodb-card-store` — see its contract.md, written *for exactly this phase*. No new index, no backfill. |
| **Tag filtering implementation** | **`FilterExpression` on the existing GSI query**, not a new index | One GSI partition already returns the full sorted feed; filtering post-query is the "no speculative interfaces" choice until scale (many thousands of cards) makes a tag-indexed GSI worth its write cost. |
| **Auth** | **None — public read API** | Card content is public AI-news summaries, not sensitive; matches Phase 1's single-tenant scoping decision ("Personalization is Phase 4", still true). CORS restricted to the deployed Vercel origin(s), not `*`. |
| **`Card` contract** | **Promote to a versioned Pydantic schema**, shared by `feed-api` and (typed-client-generated) by the frontend | `architecture-principles.md` calls this out by name as the Phase-2 trigger: "When the frontend or a real API exists, promote `Card` to a versioned, validated schema." This is the one deliberate cross-plane change Phase 2 makes. |
| **Pagination** | **Cursor-based** (`LastEvaluatedKey` passthrough, opaque token) | Matches DynamoDB's native pagination; avoids OFFSET-style scans that get expensive as the corpus grows. |

## Architecture decisions (carried from Phase 1 / cross-phase)

1. **Plane separation still holds.** `feed-api` is a *new*, thin read-only
   adapter over the **same** `ai-radar-cards` table Plane A writes — it does
   not import `src/curation/` or `src/shared/` internals, and Plane A is
   never modified by this phase. The only shared artifact is the promoted
   `Card` schema (Architecture decision above), and even that starts as a
   read-side projection Lambda owns, not a rename of Plane A's dataclass.
2. **The GSI was built for this.** `dynamodb-card-store`'s `feed-by-score`
   GSI was explicitly reserved for Phase 2 and has been written-but-unread by
   every Phase 1 run since — this phase is that GSI's first real consumer.
3. **No new domain layer.** Per `architecture-principles.md`, a feed API
   reading one index and returning cards is not "`Card` acquiring a
   lifecycle" or "users becoming entities" — no aggregates/repositories, a
   thin handler function is enough.
4. **Cost stays near-zero.** API Gateway + Lambda at this traffic (a personal
   feed, low request volume) is within/near AWS free tier; Vercel's free
   tier covers the frontend. This phase should not move the needle on the
   $500 budget in any visible way — no new recurring infra cost class is
   introduced (unlike Phase 1's Runtime/Schedule agent).

## Subtask specs (build order)

Each file below is a **spec brief** meant to be handed to the SDD workflow
(`sdd-architect` → `sdd-test-writer` → `sdd-executor` → `sdd-auditor`). The
`feature-name` in each brief is the slug for `specs/<feature-name>/`.

| # | Spec | feature-name | Depends on | Layer |
|---|---|---|---|---|
| 01 | [Feed read API](01-feed-api.md) | `feed-api` | — (Phase 1's `dynamodb-card-store`) | Data / infra |
| 02 | [Web feed UI](02-web-feed-ui.md) | `web-feed-ui` | 01 | Frontend |

**Dependency notes.** 01 stands alone against the already-deployed
`ai-radar-cards` table/GSI — it can be built, deployed, and curl-tested with
no frontend at all. 02 consumes 01's deployed API URL + the promoted `Card`
schema for its typed client; it cannot be meaningfully built (beyond a
storybook/mock-data shell) until 01 is deployed.

## How to drive each spec through SDD

For each subtask, in order:

```
1. sdd-architect   — feed it the brief; it writes intent/contract/roadmap/audit/tasks
                     to specs/<feature-name>/
2. sdd-executor    — implements against the spec, checks off tasks
3. sdd-test-writer — writes tests for every contract guarantee
4. sdd-auditor     — validates implementation vs spec, runs tests, writes audit.md
```

## Definition of done for Phase 2

- [ ] A promoted, versioned `Card` schema exists and is the contract both
      `feed-api` and the frontend's typed client build against.
- [ ] `feed-api` (API Gateway + Lambda) queries the `feed-by-score` GSI and
      returns cards sorted by relevance/date, with cursor pagination and
      tag filtering, deployed and curl-verified against the real
      `ai-radar-cards` table.
- [ ] CORS is scoped to the real Vercel origin(s), not `*`.
- [ ] The Next.js feed renders the live feed (sorted list + tag filter) and
      is deployed on Vercel at a real URL.
- [ ] All infra is reproducible from code (CDK for `feed-api`), tear-down
      documented, same pattern as Phase 1's `infra/lib` + `infra/stacks`.
- [ ] Cost stays near-$0 incremental — verified against the `AiRadarBudget`
      alerts, no new alert threshold crossed by this phase alone.

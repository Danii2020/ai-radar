# Architecture principles

How to structure new code in this repo. Written for anyone (human or agent)
implementing a spec. Decided 2026-07 after evaluating Domain-Driven Design
against the project's vision (monorepo, backend + Next.js frontend, AgentCore).

## The decision on DDD

**Strategic DDD now. Tactical DDD only when a trigger fires (below). Full
ceremony never. Frontend never.**

This product is a content pipeline + RAG chat. Its complexity is
*integration* (Bedrock, feeds, vector stores, AgentCore, scheduling), not
*business rules* — the interesting judgment (summarize, tag, score) lives in
LLM prompts, not code. DDD's payoff scales with the density of business rules,
not with lines of code, so infrastructure growth is never by itself a reason
to add domain layers. Specs must not introduce aggregates, repositories,
domain events, or layered/onion architecture speculatively.

## Boundaries to defend (the "strategic DDD now" part)

These are cheap and non-negotiable; they keep tactical DDD retrofittable
later if it's ever warranted.

1. **Two bounded contexts, one published contract.** Plane A (curation) and
   Plane B (serving) never import each other's internals. The `Card` is the
   only shared type — currently a dataclass serialized to `cards.json`.
2. **`Card` is the contract of record.** When the frontend or a real API
   exists, promote it to a versioned, validated schema (Pydantic) shared as
   the API contract (`packages/contracts` in a future monorepo:
   `apps/curation`, `apps/api`, `apps/web`). Schema changes to `Card` are
   breaking changes — treat them like API changes.
3. **Ubiquitous language.** Code speaks the design doc's vocabulary —
   `discover`, `dedup`, `summarize`, `Card`, `relevance`, plane A/B. Don't
   invent synonyms.
4. **Ports at infra seams — when the second implementation arrives, not
   before.** When Phase 1 brings DynamoDB and a real vector store, introduce
   small `Protocol` interfaces (`CardStore`, `VectorIndex`) at those seams.
   Until then, no speculative interfaces.
5. **Portable logic stays plain.** Orchestration is plain Python (soon
   LangGraph-shaped) with infra pushed to the edges, so it can move onto
   AgentCore Runtime without rewrites. (Restates the CLAUDE.md convention.)

## Triggers for tactical DDD (the "later, maybe" part)

Introduce a domain layer — inside the affected bounded context only — when
one of these actually happens, and say so in the spec:

- **`Card` acquires a lifecycle**: state transitions with invariants
  (draft → published → archived, editorial overrides, retraction). That's a
  real aggregate.
- **Users become entities**: accounts, per-user feeds, subscriptions,
  personalization rules. That's a new bounded context with real invariants.
- **Model tension**: two features need incompatible shapes of the same model
  (feed vs. chat vs. pipeline views of `Card`) — split read models from the
  domain model at that point.

If a spec proposes tactical DDD without citing one of these triggers, push
back.

## Frontend

DDD is not a frontend pattern. The Next.js app gets feature-folder
organization and a typed client generated from the `Card`/API contract. The
domain lives behind the API; do not mirror domain layers in the UI.

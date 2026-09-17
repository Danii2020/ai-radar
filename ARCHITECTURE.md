> **Draft — bootstrap-generated, not audit-verified.** Produced by `harny-document`
> in bootstrap mode from repository evidence (code, CDK stacks, `CLAUDE.md`,
> `README.md`, `docs/`), not from a shipped-and-audited feature. Review before
> treating it as authoritative, and prefer `README.md` and `CLAUDE.md` for anything
> this file appears to contradict.

# Architecture

AI Radar is an AI-news curation feed + RAG chatbot, split into two bounded
contexts ("planes") that never import each other's internals — see
[`docs/architecture-principles.md`](docs/architecture-principles.md) for the
boundary rules and [`docs/app-design-on-agentcore.md`](docs/app-design-on-agentcore.md)
for the original design. The only type shared between them is `Card`.

## Components

```
run_curation.py, runtime_app.py   Plane A entrypoints (local script / AgentCore
                                   Runtime async handler)
run_chat.py                       Plane B entrypoint (RAG REPL)
export_api_schema.py              Exports the versioned API contract

src/curation/                     Plane A — curation pipeline (discover → dedup →
                                   summarize → rank → persist), built as a
                                   LangGraph `StateGraph` (src/curation/graph.py):
  graph.py, nodes.py, state.py      the graph itself and its node functions
  interfaces.py, composite.py       CardStore / Discoverer protocols + composition
  local.py, dynamo.py               in-memory and DynamoDB CardStore implementations
  tavily.py                         Tavily-backed discovery (Plane A's discoverer)
  summary.py                        RunSummary — per-run counts, tokens, and
                                     estimated Bedrock+Tavily cost (run-observability)
  metrics.py                        CloudWatch EMF run metrics (raw stderr JSON,
                                     namespace AIRadar/Curation)
  config.py                         curation-specific settings (pydantic-settings)

src/api/                          Phase 2 — read-only feed HTTP API (Lambda behind
                                   API Gateway HTTP API):
  handler.py                        Lambda entrypoint
  feed.py, dynamo.py, cursor.py     GET /v1/cards query + DynamoDB Query + pagination
  config.py                         API-specific settings

src/contracts/                    Versioned Pydantic contracts shared across planes
                                   and the API boundary (CardOut, FeedResponse)

src/shared/                       Plane B — RAG chat + infra shared by both planes:
  bedrock.py                        bedrock-runtime client, Haiku summarize (forced
                                     tool call)
  retrieval.py                      Titan embeddings + CardIndex (cosine search)
  chat.py                           RagChat: retrieve + Sonnet grounded answer
  feeds.py                          RSS/Atom discovery → RawItem
  cards.py                          Card model + console rendering
  config.py                         region, model IDs, feeds, tuning (pydantic-settings)

infra/                            AWS CDK app (Python), one stack per deployable unit:
  app.py                            CDK app entrypoint, wires all 5 stacks
  stacks/card_store_stack.py          AiRadarCardStore   — DynamoDB card table
  stacks/agent_runtime_stack.py       AiRadarRuntimeRole — AgentCore Runtime execution role
  stacks/curation_schedule_stack.py   AiRadarSchedule    — EventBridge Scheduler trigger
  stacks/cost_budget_stack.py         AiRadarBudget      — AWS Budget + SNS alerts
  stacks/feed_api_stack.py            AiRadarFeedApi     — API Gateway + feed Lambda
  lib/                                 constructs backing each stack

docs/                              design docs, research notes, architecture
                                   principles, generated API docs (docs/api/)
specs/                            per-feature SDD spec sets (intent/contract/
                                   roadmap/tasks/audit)
```

## Plane A — curation pipeline

A LangGraph `StateGraph` (`src/curation/graph.py`) with five nodes run in a
fixed sequence:

```
discover -> dedup -> summarize -> rank -> persist
```

- **discover** — pulls candidate items via a `Discoverer` (RSS/Atom via
  `shared/feeds.py`, or Tavily via `curation/tavily.py`).
- **dedup** — drops items already seen, via the `CardStore` port
  (`curation/interfaces.py`; local-JSON or DynamoDB implementation).
- **summarize** — Haiku, structured output via the Bedrock Converse API with a
  forced tool call (`shared/bedrock.py`).
- **rank** — orders the run's cards.
- **persist** — writes through the `CardStore` port.

It runs two ways: locally (`run_curation.py`, local `CardStore`) and deployed
on Bedrock AgentCore Runtime (`runtime_app.py`, DynamoDB `CardStore`), on an
EventBridge-Scheduler-driven daily cadence (currently deployed `DISABLED` — see
`README.md`). The Runtime entrypoint is `async` and acks the invocation
immediately, running curation as a background task, so EventBridge
Scheduler's synchronous-target timeout can't double-fire it (see
`CLAUDE.md`'s "AWS / Bedrock — verified facts" for the underlying incident).

## Plane B — serving

Two surfaces, both read-only over what Plane A persisted:

- **RAG chat** (`run_chat.py` -> `shared/chat.py`) — Titan embeddings +
  in-memory cosine retrieval (`shared/retrieval.py`) grounding a Sonnet
  answer with citations, over a Bedrock prompt-cache point on the stable
  system prompt.
- **Feed API** (`src/api/`) — `GET /v1/cards` via API Gateway HTTP API ->
  Lambda (`api/handler.py`) -> `dynamodb:Query` on a `feed-by-score` index
  (`api/dynamo.py`), paginated (`api/cursor.py`), returning the versioned
  `CardOut`/`FeedResponse` contract from `src/contracts/`.

## The shared contract

`Card` (`shared/cards.py`) is the only type Plane A and Plane B both depend
on — currently a plain dataclass, deliberately not promoted to a shared
package/schema until one of the triggers in
[`docs/architecture-principles.md`](docs/architecture-principles.md) fires.
`src/contracts/card.py`'s `CardOut`/`FeedResponse` are the API-boundary
contract for the feed HTTP API specifically (Phase 2's `feed-api` spec), not a
replacement for the Plane A/B `Card` dataclass.

## Infrastructure

Deployed via AWS CDK (Python, `infra/`), one stack per deployable unit (see
`infra/app.py`): `AiRadarCardStore`, `AiRadarRuntimeRole`, `AiRadarSchedule`,
`AiRadarBudget`, `AiRadarFeedApi`. Current live-deploy status, exact deploy/
verify commands, and known operational gotchas are tracked in `README.md`,
not here — that table is the source of truth for what's actually deployed at
any given time.

## Validation

See `CLAUDE.md` and `README.md` for exact commands; in short: `uv sync` to
install, `uv run pytest tests/` for the test suite, `uv run ruff check` /
`uv run mypy` for lint/type-check (wired into this repo's harny feedback hook
and CI workflow as of the `stack: python` harness configuration).

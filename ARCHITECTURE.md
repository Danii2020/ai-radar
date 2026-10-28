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
chat_app.py                       Plane B AgentCore Runtime entrypoint (stateless chat
                                   agent; selected in the shared Dockerfile by
                                   AGENT_ENTRYPOINT=chat_app.py)
run_backfill_embeddings.py        one-time, idempotent Titan backfill for cards lacking an embedding
export_api_schema.py              Exports the versioned API contract

src/curation/                     Plane A — curation pipeline (discover → dedup →
                                   summarize → rank → persist), built as a
                                   LangGraph `StateGraph` (src/curation/graph.py):
  graph.py, nodes.py, state.py      the graph itself and its node functions
  interfaces.py, composite.py       CardStore / Discoverer / EmbeddingWriter protocols + composition
  local.py, dynamo.py               in-memory and DynamoDB CardStore implementations
  backfill.py                       backfill_embeddings(): embeds cards without an EMBED_DIM vector
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

src/chat/                         Plane B — the chat agent's logic and DynamoDB retriever:
  retriever.py                      DynamoCardRetriever: paginated feed-by-score Query,
                                     brute-force cosine top-k over stored vectors
  request.py                        parse_request(): pure validation and caps of
                                     {question, history}, before any AWS call
  graph.py                          build_chat_graph(retriever, k): LangGraph
                                     retrieve → answer; sources builder; no-context path
  config.py                         table name, backend switch, GSI constants (duplicated
                                     from curation/config.py, equality-tested), and the
                                     CHAT_MAX_* request caps

src/chat_api/                     Plane B — public edge: Lambda behind API Gateway HTTP API
                                   (`POST /v1/chat`, chat-api):
  handler.py                        body checks (512 KiB cap), one InvokeAgentRuntime call
                                     on ai_radar_chat, reply mapping to a typed response
  config.py                         CHAT_RUNTIME_ARN (pydantic-settings), byte cap, timeouts

src/shared/                       Plane B — RAG chat + infra shared by both planes:
  bedrock.py                        bedrock-runtime client, Haiku summarize (forced
                                     tool call)
  embeddings.py                     Titan v2 embed() + card_text(), used by both planes
  retrieval.py                      CardIndex: in-memory cosine search (local path)
  chat.py                           answer_question() (stateless Sonnet answer step) and
                                     RagChat(retriever, k), which delegates to it
  feeds.py                          RSS/Atom discovery → RawItem
  cards.py                          Card model + console rendering
  config.py                         region, model IDs, feeds, tuning (pydantic-settings)

infra/                            AWS CDK app (Python), one stack per deployable unit:
  app.py                            CDK app entrypoint, wires all 7 stacks
  stacks/card_store_stack.py          AiRadarCardStore   — DynamoDB card table
  stacks/agent_runtime_stack.py       AiRadarRuntimeRole — curation AgentCore Runtime execution role
  stacks/chat_runtime_stack.py        AiRadarChatRuntime — chat AgentCore Runtime execution role
  stacks/curation_schedule_stack.py   AiRadarSchedule    — EventBridge Scheduler trigger
  stacks/cost_budget_stack.py         AiRadarBudget      — AWS Budget + SNS alerts
  stacks/feed_api_stack.py            AiRadarFeedApi     — API Gateway + feed Lambda
  stacks/chat_api_stack.py            AiRadarChatApi     — public chat API (API Gateway + Lambda)
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
- **embed** (optional, `chat-retrieval`) — runs after `persist` only when an
  `embedding_writer` is passed (`runtime_app.py` and `run_curation.py` on DynamoDB; the
  deployed runtime gets it only after its image is rebuilt).
  Embeds each persisted card with Titan v2 and writes the vector through the writer.
  A failure is counted, never raised, so it cannot fail the run.

It runs two ways: locally (`run_curation.py`, local `CardStore`) and deployed
on Bedrock AgentCore Runtime (`runtime_app.py`, DynamoDB `CardStore`), on an
EventBridge-Scheduler-driven daily cadence (currently deployed `DISABLED` — see
`README.md`). The Runtime entrypoint is `async` and acks the invocation
immediately, running curation as a background task, so EventBridge
Scheduler's synchronous-target timeout can't double-fire it (see
`CLAUDE.md`'s "AWS / Bedrock — verified facts" for the underlying incident).

## Plane B — serving

Two surfaces, both read-only over what Plane A persisted:

- **RAG chat, local** (`run_chat.py` -> `shared/chat.py`) — cosine retrieval over Titan
  v2 card vectors, grounding a Sonnet answer with citations, over a Bedrock
  prompt-cache point on the stable system prompt. The retriever is either the
  in-memory `CardIndex` (`shared/retrieval.py`, the default local path) or
  `DynamoCardRetriever` (`src/chat/retriever.py`, `CARD_STORE_BACKEND=dynamo`), which
  reads the vectors that the curation pipeline stored in the `embedding` attribute. Both
  satisfy the `Retriever` protocol in `shared/chat.py`.
- **RAG chat agent, deployed** (`chat_app.py`, AgentCore Runtime agent `ai_radar_chat`,
  `chat-agent-runtime`) — a stateless `{question, history}` → `{answer, sources}` turn.
  `src/chat/request.py` validates and caps the request before any AWS call. The
  LangGraph graph in `src/chat/graph.py` runs `retrieve` (the same
  `DynamoCardRetriever`) and then `answer`, which calls `shared/chat.py`'s
  `answer_question()` on Sonnet 4.6. With no hits it answers without a model call. Its
  execution role is `AiRadarChatRuntime`, separate from the curation role.
- **Chat API** (`src/chat_api/`, `chat-api`) — `POST /v1/chat` via API Gateway HTTP API ->
  Lambda (`chat_api/handler.py`, image `Dockerfile.chat_api`) -> one `InvokeAgentRuntime`
  call on `ai_radar_chat`, with a fresh session id per request. It adds no authentication and
  no retries; the stage throttle (5 req/s, burst 10) is the cost guard. It returns the agent's
  `{answer, sources}` unchanged, or a typed `invalid_request`, `upstream_failure`,
  `upstream_timeout` or `internal_error`. API Gateway owns CORS. Deployed as `AiRadarChatApi`.
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
`infra/app.py`): `AiRadarCardStore`, `AiRadarRuntimeRole`, `AiRadarChatRuntime`,
`AiRadarSchedule`, `AiRadarBudget`, `AiRadarFeedApi`, `AiRadarChatApi`. Both agents share one root
`Dockerfile`, and the chat agent selects its entrypoint with `AGENT_ENTRYPOINT`. The chat API Lambda has its own image,
`Dockerfile.chat_api`. Current
live-deploy status, exact deploy/
verify commands, and known operational gotchas are tracked in `README.md`,
not here — that table is the source of truth for what's actually deployed at
any given time.

**CI/CD (`backend-cicd-pipeline`, implemented, not live yet).** Once live, GitHub Actions
(`.github/workflows/backend-*.yml`) checks every PR and deploys the changed parts of the backend on each
merge to `main`, through GitHub OIDC roles with no AWS key in GitHub. The deploy code is in `scripts/ci/`,
with one pinned context file (`scripts/ci/deploy_context.json`). The CI access roles and the two scoped
CloudFormation execution policies are a separate CDK app, `infra/ci_bootstrap/`, which a human deploys
once and CI never deploys. The capability is `specs/current/ci-cd.md`, and its runbook is the README's
"Backend CI/CD" section.

## Validation

See `CLAUDE.md` and `README.md` for exact commands; in short: `uv sync` to
install, `uv run pytest tests/` for the test suite, `uv run ruff check` /
`uv run mypy` for lint/type-check (wired into this repo's harny feedback hook
and CI workflow as of the `stack: python` harness configuration). The backend PR checks
(`.github/workflows/backend-checks.yml`) also run `pytest`, `actionlint` and `cdk synth` of all seven stacks;
they have not run on GitHub yet.

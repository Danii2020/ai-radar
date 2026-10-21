# Changelog

All notable changes to this project are documented in this file, in
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) style. This project
has not cut a versioned release — entries are grouped by ship date instead of
a version number. Each entry links to its archived SDD spec
(`specs/archived/<feature>/`) for the full contract, audit, and evidence.

## [Unreleased]

### Changed
- Backend redeployed into AWS account `626259825216` (all six stacks and the
  `ai_radar_curation` agent, smoke-verified). The pinned `account` default in
  `infra/lib/agent_runtime.py` and `infra/lib/feed_api.py`, and the matching
  assertions in `tests/test_infra_agent_runtime.py` and
  `tests/test_infra_feed_api.py`, moved from `536697225154` to `626259825216`.
- `apps/web/.env.example` and the README runbook now point at the new feed API
  URL. See README "Account migration (2026-10-05)".

Nothing pending beyond `apps/web/specs/archived/web-feed-ui/` (Phase 2 spec 02, the Next.js
frontend — still in progress, not yet archived).

## 2026-10-21 — chat-api

Spec: `specs/archived/chat-api/`. Audit: APPROVED WITH RESERVATIONS (round 3). Deployed as
`AiRadarChatApi` in account `626259825216` and live-verified: runbook steps 1–9 ran, and
step 10 (the agent-side invocation count for one slow request) did not. Open reservations
F11 (MEDIUM), F13, F5, F7 and F8 (LOW), listed below and in README "Phase 3 — Chat API".

### Added
- `src/chat_api/` (`handler.py`, `config.py`, `AGENTS.md`): the Lambda behind `POST /v1/chat`.
  It checks the JSON shape and a 512 KiB byte cap, then makes one `InvokeAgentRuntime` call on
  `ai_radar_chat` with a fresh session id per request. There are no retries (connect 3 s, read
  22 s, Lambda timeout 28 s). It returns the agent's `{answer, sources}` (200), `invalid_request`
  (400), `upstream_failure` (502), `upstream_timeout` (504) or `internal_error` (500).
- `Dockerfile.chat_api` and the `chat_api` dependency group in `pyproject.toml` and `uv.lock`
  (`boto3`, `pydantic-settings`). Image build and in-container import were checked live.
- CDK construct `infra/lib/chat_api.py` and stack `AiRadarChatApi`
  (`infra/stacks/chat_api_stack.py`), registered in `infra/app.py`. It is an API Gateway HTTP API
  with one route, `POST /v1/chat`, and no `$default` route. CORS allows the explicit origin list
  (default `http://localhost:3000`, never `*`). The stage throttle is 5 req/s with a burst of 10.
  The Lambda role can invoke only the chat runtime ARNs and write its own logs. Its context
  overrides are `chat_api_allowed_origins` and `chat_api_reserved_concurrency`.
- One text-free `chat_api_request` log record per request: status, outcome, sizes, `duration_ms`
  and the session id. A 500 record logs the exception class and stack frames only.
- Tests: `tests/test_chat_api_handler.py` (43), `tests/test_infra_chat_api.py` (11) and
  `tests/test_chat_api_dockerfile.py` (4). The suite is at 545 passed.
- README "Phase 3 — Chat API" runbook, with the recorded live results.

### Changed
- Side changes outside the plan's ownership, awaiting the human's confirmation (audit F8):
  `.gitignore` now ignores `.env*` except `!.env.example`, and `pyproject.toml` gains a mypy
  override for `botocore.*`.

### Open reservations
- **F11 (MEDIUM).** The function is unreserved, because this account's Lambda concurrency quota
  is 10. A parallel burst exhausted the 10-slot pool (Lambda 503s), and `ai-radar-feed-api`
  shares that pool. The quota increase to 1000 was requested on 2026-10-21 (request
  `cf8be0f0ceba4cf787e8e329efd718e0i3872UpR`, status `CASE_OPENED`, support case
  `179259663100438`). Once approved, redeploy `AiRadarChatApi` and `AiRadarFeedApi` without the
  `none` flag, then re-run the burst.
- **F13 (LOW).** The stage throttle is lenient, about 2× nominal under a burst. The budget alert
  is the backstop.
- **F5 (LOW).** Runbook step 10 is not run.
- **F7 and F8 (LOW).** CI has not run on the branch, because it is unpushed. The `.gitignore`
  and `botocore.*` side changes are awaiting the human's confirmation.

## 2026-10-18 — chat-agent-runtime

Spec: `specs/archived/chat-agent-runtime/`. Audit: APPROVED WITH RESERVATIONS (round 3).
The live AC10 runbook ran in account `626259825216`, together with the
`chat-retrieval` deploy steps that had been pending (Titan grant, curation image
rebuild, backfill). Reservation F11: retrieval latency has one sample (330 ms) and no
p95, against the ADR 0009 ceiling.

### Added
- The chat agent, `chat_app.py`: a stateless AgentCore Runtime entrypoint.
  `{question, history}` in, `{answer, sources}` out, with `invalid_request` and
  `upstream_failure` errors. The handler is synchronous.
- `src/chat/request.py` (`parse_request`, pure): validates and caps the request before any
  AWS call. Caps are `CHAT_MAX_QUESTION_CHARS` (1000), `CHAT_MAX_HISTORY_TURNS` (10) and
  `CHAT_MAX_HISTORY_ITEM_CHARS` (4000), in `src/chat/config.py`.
- `src/chat/graph.py` (`build_chat_graph`): a LangGraph `retrieve` → `answer` graph. With
  no hits it returns the fixed no-context answer and makes no model call.
- `answer_question()` in `src/shared/chat.py`: the stateless Sonnet answer step, shared by
  `RagChat.ask` and the agent.
- One `chat_turn` log record per invocation (child logger `bedrock_agentcore.app.chat`).
  It holds lengths, counts, timings and the outcome, and no question, history or answer
  text.
- `AiRadarChatRuntime` CDK stack (`infra/stacks/chat_runtime_stack.py`, construct in
  `infra/lib/chat_runtime.py`): a separate chat execution role with seven statements,
  `dynamodb:Query` on the `feed-by-score` index only, no secret and no write grant.
- Live: AgentCore Runtime agent `ai_radar_chat` (`ai_radar_chat-JFCO0R9lkT`).

### Changed
- `SONNET_MODEL_ID` default is now `us.anthropic.claude-sonnet-4-6` (was Sonnet 4.5, now
  `LEGACY` in Bedrock). An env override still wins. `.env.example` follows. The Haiku default
  and the curation graph are unchanged.
- `Dockerfile` CMD selects the entrypoint with `AGENT_ENTRYPOINT` (default
  `runtime_app.py`, so the curation agent is unchanged). The chat agent deploys with
  `AGENT_ENTRYPOINT=chat_app.py`.
- `RagChat.ask` delegates to `answer_question()`, with identical model requests.
- Live: the `AiRadarRuntimeRole` redeploy (Titan grant), the curation image rebuild and one
  curation pass (16 cards, all embedded after the backfill).

### Fixed
- `DynamoCardRetriever` binds its DynamoDB resource to `shared.config.AWS_REGION`, so
  importing the chat agent does not depend on a region environment variable.

## 2026-10-13 — chat-retrieval

Spec: `specs/archived/chat-retrieval/`. Audit: APPROVED WITH RESERVATIONS (round 3).
**Nothing from this entry is deployed**: the agent image rebuild, the
`AiRadarRuntimeRole` redeploy and the backfill run are still pending (see README
"Phase 3 — Chatbot").

### Added
- Curation-time embeddings: an `embed` node after `persist` (`src/curation/graph.py`,
  `src/curation/nodes.py`) writes a Titan v2 vector to each persisted card via
  `DynamoCardStore.set_embeddings` (`src/curation/dynamo.py`). Shared `embed()` and
  `card_text()` live in `src/shared/embeddings.py`.
- Backfill: `uv run run_backfill_embeddings.py` (`src/curation/backfill.py`) embeds cards
  with no vector, or one of the wrong length. It is idempotent and prints
  `embedded/skipped/failed`.
- `DynamoCardRetriever` in `src/chat/` (`retriever.py`, `config.py`): a paginated `Query`
  on `feed-by-score`, with brute-force cosine top-k over the stored vectors.
- `Retriever` protocol and `RagChat(retriever, k)` in `src/shared/chat.py`.
- `CARD_STORE_BACKEND` switch in `run_chat.py` (`json` default, Phase 0 behavior;
  `dynamo` reads from DynamoDB).
- `InvokeTitanEmbed` statement in `infra/lib/agent_runtime.py`: `bedrock:InvokeModel` on
  the Titan v2 foundation model only. The Haiku statement stays Haiku-only.

### Changed
- `build_graph(store, discoverer, embedding_writer=None)`: the writer is optional, so
  existing callers and the no-writer graph are unchanged.
- `runtime_app.py` and `run_curation.py` pass their `DynamoCardStore` as the embedding writer.
- `src/shared/retrieval.py` imports `embed` and `card_text` from `src/shared/embeddings.py`
  and no longer re-exports `EMBED_MODEL_ID`.
- Test edits, all deliberate: the `_fake_build_graph` helper in
  `tests/test_runtime_app.py` gained `embedding_writer`; the "no titan" assertion in
  `tests/test_infra_agent_runtime.py` now covers the Haiku statement only; one assertion
  line in `tests/test_config.py` was removed for audit finding F3 (human-approved).
- Test suite: 406 passed (baseline 350); ruff and mypy clean.

### Known limitations
- A card whose upsert fails still gets a Titan call (about $0.00002 per card, the
  auditor's estimate). Its vector write is then rejected and it is counted in
  `embed_failed`, so the run is unaffected (audit F11, accepted).
- Not verified live: no `run_chat.py` run against real DynamoDB and Bedrock; CI on the
  unpushed branch; evidence that the Stop hook fired (audit F7, open).
- Brute-force retrieval is to be revisited at about 2,000 embedded cards, or a measured
  p95 above about 1 s.

## 2026-10-03 — feed-structure-refactor

Spec: `apps/web/specs/archived/feed-structure-refactor/`. Audit: APPROVED WITH
RESERVATIONS (round 1); no behavior change.

### Added
- `apps/web/features/feed/index.ts`, the feature's single public entry point
  (`FeedView`, `loadFeedState`, `parseFeedSearchParams`), plus
  `api/load-feed-state.ts` and `lib/search-params.ts` (tested logic extracted
  from `app/page.tsx`).
- Playwright e2e tier (`npm run test:e2e`, `@playwright/test` devDependency):
  23 offline scenarios against a local `feed-api` stub, compared to a baseline
  captured from the pre-refactor app.
- `conventions.test.ts` guards for the barrel surface, deep imports, barrel
  self-imports and `"use client"` imports of the barrel or `api/`.

### Changed
- `apps/web/features/feed/` reorganized into `api/`, `components/` and `lib/`
  with tests beside their source; `app/page.tsx` slimmed to an 11-line shell.
- `npm run generate:types` now writes `features/feed/api/types.generated.ts`.

## 2026-09-03 — feed-api

### Added
- `GET /v1/cards` read-only feed HTTP API: API Gateway HTTP API → Lambda →
  `dynamodb:Query` on the `feed-by-score` GSI, cursor pagination, `?tag=`/
  `?limit=` filtering (`src/api/{config,cursor,dynamo,feed,handler}.py`).
- Versioned `CardOut`/`FeedResponse` Pydantic contract (`src/contracts/card.py`,
  `CARD_SCHEMA_VERSION = "v1"`) with a committed JSON Schema artifact
  (`docs/api/feed-api.v1.schema.json`, generated by `export_api_schema.py`).
- `AiRadarFeedApi` CDK stack (`infra/lib/feed_api.py`, `infra/stacks/feed_api_stack.py`).

### Fixed
- `pyproject.toml`'s `api` dependency group was missing `pydantic-settings`
  (masked by it already being present as a main/dev dependency in the local
  `.venv`); only surfaced when the Lambda image was actually built with
  `uv --only-group api` and raised `ModuleNotFoundError` on import. Fixed by
  adding it to the `api` group explicitly.

Deployed 2026-09-03 (`AiRadarFeedApi`, `CREATE_COMPLETE`); live-curl-verified
2026-09-04 (pagination, tag filter, `?limit=0` validation, and CORS
allow/deny all confirmed against the real API Gateway URL).
Audit: APPROVED WITH RESERVATIONS.

## 2026-08-18 — pydantic-settings-config

### Changed
- `src/shared/config.py` and `src/curation/config.py` now load through
  `pydantic-settings` instead of hand-rolled `os.getenv`/`_csv()` parsing —
  a loading-mechanism swap only: zero env-var renames, zero default changes,
  zero consumer-file edits. A bad env-var override now fails fast at import
  with a typed `pydantic.ValidationError` naming the variable, instead of a
  bare `ValueError` or a silently-wrong value.
- Added 116 new tests (`tests/test_config.py`), the first-ever coverage of
  either config module.

Local-only; no redeploy, no infra change, $0 AWS spend at ship time. The
running AgentCore Runtime image was updated to include this change as part
of the 2026-08-30 redeploy (bundled with `rename-spike-to-shared`, below).

## 2026-09-17 — rename-spike-to-shared

### Changed
- Renamed `src/spike` → `src/shared` and all `SPIKE_*` env keys →
  `AI_RADAR_*` (`SPIKE_MAX_ITEMS`→`AI_RADAR_MAX_ITEMS`,
  `SPIKE_PER_FEED`→`AI_RADAR_PER_FEED`, `SPIKE_TOP_K`→`AI_RADAR_TOP_K`) —
  zero behavior change; 7 renamed files, `config.py` renamed (74% similarity),
  `__init__.py` rewritten, 2 deletions (`run_spike.py`, `pipeline.py`, both
  dead code), 0 new files.

Code merged and audited 2026-08-17 (145/145 tests passing). Full close-out
was gated on three human-owned local migration steps that cannot be done by
an agent (`.env` and the JSON dedup cache are both untracked/gitignored):
moving `.spike_cache/` → `.ai_radar_cache/`, renaming the three stale `.env`
keys, and verifying the cache survived the move. Verified done 2026-09-17 —
see `specs/archived/rename-spike-to-shared/audit.md`'s Close-out checklist.
The live AgentCore Runtime image was redeployed 2026-08-30 to include this
change (bundled with `pydantic-settings-config`, above).
Audit: APPROVED.

## 2026-08-12 — run-observability

### Added
- `RunSummary` (`src/curation/summary.py`) per curation run — discovered
  RSS-vs-Tavily split, dedup/summarize/persist counts, Bedrock tokens, Tavily
  searches/credits, and estimated Bedrock+Tavily cost — logged as a strict
  superset of the existing `curation_run_complete` record.
- 4 CloudWatch EMF custom metrics (`src/curation/metrics.py`, namespace
  `AIRadar/Curation`: `RunsCompleted`, `CardsWritten`, `ItemsFailed`,
  `EstimatedCostUsd`), written as raw JSON directly to `stderr` (bypassing
  `logging`, which would otherwise nest the payload under a `message` string
  and break EMF parsing). `CURATION_EMIT_METRICS=false` disables emission.
- `AiRadarBudget` CDK stack (`infra/lib/cost_budget.py`,
  `infra/stacks/cost_budget_stack.py`) — a monthly AWS Budget at
  $50/$100/$250 via SNS email, `IncludeCredit: false`, independent of the
  pre-existing hand-made budget.

Real-deployed and live-fire verified 2026-08-12: budget created cleanly,
`cdk diff` empty on the three pre-existing stacks, SNS subscription
confirmed with a real delivered test message, agent rebuilt to image
`20260812-162922-638`, and a real invoke produced all 4 metrics with
datapoints plus token counts matching Bedrock's own CloudWatch meter exactly
(delta $0.00). Suite green at 145 tests.
Audit: APPROVED.

## 2026-08-10 — async-invocation-ack

### Fixed
- Fixes `eventbridge-schedule` finding F5 (below): `runtime_app.py`'s
  entrypoint is now `async def handler`, acking immediately
  (`{"status": "accepted", "run_id": …}`) and running the **unchanged**
  curation graph as a background task via the AgentCore SDK's
  `add_async_task`/`complete_async_task`. A single-flight guard rejects a
  concurrent second invocation with `already_running`. No `infra/`, `src/`
  (curation logic), or Dockerfile change.

Redeployed and live-fire re-tested 2026-08-10: one Scheduler fire produced
exactly one run (`InvocationAttemptCount=1`, zero `TargetErrorCount`
datapoints, one `curation_run_complete` record), card count rose cleanly
48→56, DLQ stayed 0.
Audit: APPROVED — re-audited independently against live AWS.

## 2026-08-10 — eventbridge-schedule

### Added
- Daily `EventBridge Scheduler` schedule (`infra/lib/curation_schedule.py` →
  `AiRadarSchedule` stack) invoking the deployed Runtime agent via the
  generic `Universal` target (no native EventBridge target exists for
  AgentCore Runtime) — 15-min flexible window, 3 bounded retries, 2h max
  event age, SQS dead-letter queue. Deploys `DISABLED` by default (no
  recurring cost until deliberately enabled).

### Known issues
- **F5 (HIGH, resolved by `async-invocation-ack` above):** the first real
  live fire (2026-08-10) delivered twice — the `Universal` target is
  synchronous with an undocumented ~30s response timeout, and the 25–35s
  curation run exceeded it, so AWS retried a call that had actually
  succeeded. An empty DLQ gave false confidence; only `AWS/Scheduler`'s
  `TargetErrorCount` metric exposed it.

Two operational gaps remain open, inherited forward (not new-code gaps):
the prescribed double-fire dedup drill has never been run as its own test,
and the daily cadence has never run unattended — the schedule stays
`DISABLED`.
Audit: APPROVED WITH RESERVATIONS.

## 2026-07-27 — runtime-packaging

### Added
- `runtime_app.py`: wraps the unchanged curation graph in a
  `BedrockAgentCoreApp` entrypoint for Bedrock AgentCore Runtime.
- Least-privilege execution-role + Tavily-secret CDK stack
  (`infra/lib/agent_runtime.py` → `AiRadarRuntimeRole`). The Tavily API key
  resolves from AWS Secrets Manager at invocation time — never baked into
  the image — and degrades gracefully to RSS-only if unset/unreadable.
- `uv`-based Dockerfile for the Runtime image.

Deployed for real 2026-07-28 (real Tavily key, cards landed in
`ai-radar-cards`, teardown verified clean). Two post-audit LOW findings
recorded (F10: sentinel literal duplicated with no equality test across the
CDK/app boundary; F11: spec text described an empty placeholder while the
shipped design uses a recognizable-sentinel placeholder) — both
non-blocking, documented in the archived audit log.
Audit: APPROVED (re-audited after two fixes).

## 2026-07-21 — dynamodb-card-store

### Added
- `DynamoCardStore` — DynamoDB-backed `CardStore` implementation (persistence
  + dedup via `BatchGetItem`), opt-in via `CARD_STORE_BACKEND=dynamo`.
- CDK construct provisioning the `ai-radar-cards` table (pay-per-request,
  `RemovalPolicy.RETAIN`) and a `feed-by-score` GSI, designed ahead of time
  for Phase 2's read API.

Same `CardStore` Protocol as the local JSON default — no graph/node changes.
Audit: APPROVED.

## 2026-07-15 — tavily-discovery

### Added
- `TavilyDiscoverer` (web search) and `CompositeDiscoverer` (RSS + Tavily,
  cross-source deduped) behind the existing `Discoverer` Protocol.

No graph/node changes.
Audit: APPROVED.

## 2026-07-10 — curation-graph

### Added
- The curation pipeline as a LangGraph `StateGraph`
  (`discover → dedup → summarize → rank → persist`, `src/curation/graph.py`).
- `Discoverer`/`CardStore` Protocols (`src/curation/interfaces.py`) and the
  local JSON-file defaults (`src/curation/local.py`), reproducing the Phase 0
  spike's behavior exactly.

First Phase 1 spec; establishes the Protocol seams every later curation spec
builds on.
Audit: APPROVED.

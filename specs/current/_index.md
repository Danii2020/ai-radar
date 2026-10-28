# Current-State Specifications

> Current truth for this repo. Maintained by `harny-sync`; do not hand-edit.
> Last synced: 2026-10-28 (`backend-cicd-pipeline` archived, implemented and audit-approved with
> reservations, NOT LIVE: new `ci-cd` capability, ADRs 0040 and 0042–0047 (0041 not promoted), amends
> `runtime-deployment` (RD-9), `scheduling` (SC-5), `chat-api-auth` (CAAUTH-10, ADR 0028 amended by ADR 0043)
> and `feed-api` (FA-6) — see Notes).
> Earlier: 2026-10-21 (`chat-api-auth` archived: new `chat-api-auth` capability, amends
> `chat-api` CAPI-4 and CAPI-6, ADRs 0028–0031, ADR 0027 superseded, reservations CAAUTH-F1, F3,
> F5, F6, F9, F11 and the admin and key limits — see Notes).
> Earlier: 2026-10-21 (`chat-api` archived: new `chat-api` capability, ADRs 0022–0027,
> reservations CAPI-F5, F7, F8, F11, F13 — see Notes).
> Earlier: 2026-10-18 (`chat-agent-runtime` archived: new `chat-agent`
> capability, ADRs 0016–0021, runtime-deployment RD-7/RD-8, reservations CAR-F5..F11 — see Notes).
> Earlier: 2026-10-13 (`chat-retrieval` archived: new `chat-retrieval`
> capability, ADRs 0009–0015, reservation F7 and F11; nothing deployed at ship time — see Notes).
> Earlier: 2026-09-20 component split: the frontend `web-feed`
> capability, its `web-feed-ui` archive, ADRs 0001–0007, and WEB-R1..R3 moved
> to [`apps/web/specs/`](../../apps/web/specs/current/_index.md) — see Notes)

> **Two harness roots.** This index covers the Python backend (repo root
> harness, `stack: python`). The Next.js frontend has its own harny harness
> and knowledge base at `apps/web/` (`stack: typescript`):
> [`apps/web/specs/current/_index.md`](../../apps/web/specs/current/_index.md).

## Capabilities

| Capability | Current-State Specification | Incorporated Changes |
|---|---|---|
| curation-pipeline | [curation-pipeline.md](./curation-pipeline.md) | [curation-graph](../archived/curation-graph/), [tavily-discovery](../archived/tavily-discovery/), [chat-retrieval](../archived/chat-retrieval/) |
| card-persistence | [card-persistence.md](./card-persistence.md) | [dynamodb-card-store](../archived/dynamodb-card-store/), [chat-retrieval](../archived/chat-retrieval/) |
| runtime-deployment | [runtime-deployment.md](./runtime-deployment.md) | [runtime-packaging](../archived/runtime-packaging/), [async-invocation-ack](../archived/async-invocation-ack/), [chat-retrieval](../archived/chat-retrieval/), [chat-agent-runtime](../archived/chat-agent-runtime/), [backend-cicd-pipeline](../archived/backend-cicd-pipeline/) (RD-9) |
| scheduling | [scheduling.md](./scheduling.md) | [eventbridge-schedule](../archived/eventbridge-schedule/), [backend-cicd-pipeline](../archived/backend-cicd-pipeline/) (SC-5) |
| observability | [observability.md](./observability.md) | [run-observability](../archived/run-observability/) |
| config-loading | [config-loading.md](./config-loading.md) | [pydantic-settings-config](../archived/pydantic-settings-config/), [rename-spike-to-shared](../archived/rename-spike-to-shared/) |
| feed-api | [feed-api.md](./feed-api.md) | [feed-api](../archived/feed-api/), [backend-cicd-pipeline](../archived/backend-cicd-pipeline/) (FA-6) |
| chat-retrieval | [chat-retrieval.md](./chat-retrieval.md) | [chat-retrieval](../archived/chat-retrieval/), [chat-agent-runtime](../archived/chat-agent-runtime/) (no requirement change) |
| chat-agent | [chat-agent.md](./chat-agent.md) | [chat-agent-runtime](../archived/chat-agent-runtime/) |
| chat-api | [chat-api.md](./chat-api.md) | [chat-api](../archived/chat-api/), [chat-api-auth](../archived/chat-api-auth/) (CAPI-4 amended, CAPI-6 note) |
| chat-api-auth | [chat-api-auth.md](./chat-api-auth.md) | [chat-api-auth](../archived/chat-api-auth/), [backend-cicd-pipeline](../archived/backend-cicd-pipeline/) (CAAUTH-10; amends ADR 0028 via ADR 0043) |
| ci-cd | [ci-cd.md](./ci-cd.md) | [backend-cicd-pipeline](../archived/backend-cicd-pipeline/) (new; implemented, NOT LIVE — O12 a–i pending) |

## Keyword lookup

> If your question mentions a term on the left, read the capability on the right first.

| Term | Capability |
|---|---|
| StateGraph / LangGraph | curation-pipeline |
| discover / dedup / summarize / rank / persist | curation-pipeline |
| Discoverer / CompositeDiscoverer | curation-pipeline |
| Tavily discovery | curation-pipeline |
| RSS feeds | curation-pipeline |
| url_hash / dedup key | curation-pipeline, card-persistence |
| CardStore Protocol | card-persistence |
| DynamoCardStore | card-persistence |
| upsert idempotency | card-persistence |
| feed-by-score GSI | card-persistence, feed-api |
| embedding attribute | card-persistence, chat-retrieval |
| set_embeddings / set_embedding | card-persistence |
| embed node / EmbeddingWriter | curation-pipeline |
| backfill / run_backfill_embeddings | curation-pipeline |
| Titan v2 / embed() / card_text | chat-retrieval |
| Retriever / RagChat(retriever, k) | chat-retrieval |
| DynamoCardRetriever | chat-retrieval |
| brute force / cosine / scale ceiling | chat-retrieval |
| CARD_STORE_BACKEND | chat-retrieval |
| InvokeTitanEmbed | runtime-deployment |
| card_id | card-persistence |
| RemovalPolicy.RETAIN | card-persistence |
| AgentCore Runtime | runtime-deployment |
| BedrockAgentCoreApp / runtime_app.py | runtime-deployment |
| Secrets Manager (Tavily key) | runtime-deployment |
| execution role / least privilege | runtime-deployment, scheduling |
| async handler / immediate ack | runtime-deployment |
| single-flight / already_running | runtime-deployment |
| run_id | runtime-deployment, observability |
| EventBridge Scheduler | scheduling |
| Universal target | scheduling |
| dead-letter queue / DLQ | scheduling |
| schedule_enabled / cron | scheduling |
| TargetErrorCount | scheduling |
| double-fire | scheduling |
| RunSummary | observability |
| EMF / CloudWatch custom metrics | observability |
| AiRadarBudget | observability |
| curation_run_complete | runtime-deployment, observability |
| curation_run_metrics | observability |
| estimated_cost_usd | observability |
| pydantic-settings | config-loading |
| AI_RADAR_* / SPIKE_* env keys | config-loading |
| ValidationError (config) | config-loading |
| CURATION_EMIT_METRICS | config-loading, observability |
| .env loading | config-loading |
| shared/ package | config-loading |
| GET /v1/cards | feed-api |
| cursor / next_cursor pagination | feed-api (see also apps/web: web-feed) |
| CORS (feed-api) | feed-api |
| CardOut / FeedResponse | feed-api |
| tag filter | feed-api (see also apps/web: web-feed) |
| chat_app.py / chat agent | chat-agent |
| ai_radar_chat / AiRadarChatRuntime | chat-agent, runtime-deployment |
| stateless turn / history (chat) | chat-agent |
| parse_request / InvalidRequest | chat-agent |
| build_chat_graph / no-context answer | chat-agent |
| invalid_request / upstream_failure | chat-agent |
| chat_turn (log record) | chat-agent |
| CHAT_MAX_* caps | chat-agent |
| answer_question (shared answer step) | chat-agent, chat-retrieval |
| SONNET_MODEL_ID / Sonnet 4.6 | chat-agent, config-loading |
| AGENT_ENTRYPOINT / shared Dockerfile | runtime-deployment |
| RD-7 chat role | runtime-deployment |
| POST /v1/chat / AiRadarChatApi | chat-api |
| ai-radar-chat-api (Lambda) / chat_api group | chat-api |
| chat_api_request (log record) | chat-api |
| chat_api_reserved_concurrency | chat-api |
| upstream_timeout / upstream_failure (chat API) | chat-api |
| total_max_attempts / no retry (chat API) | chat-api |
| runtimeSessionId / fresh session id (chat API) | chat-api |
| stage throttle (chat API, second layer) | chat-api, chat-api-auth |
| SigV4 / AWS_IAM / execute-api (chat route) | chat-api-auth |
| ai-radar-chat-api-caller / caller user | chat-api-auth |
| caller access key / rotation / key storage | chat-api-auth |
| ChatApiCallerUserName | chat-api-auth |
| CORS (chat API) / no CORS configuration | chat-api-auth |
| chat_api_allowed_origins (removed) | chat-api-auth |
| unauthenticated chat / 403 at the gateway | chat-api-auth |
| CI/CD / GitHub Actions / backend-cicd-pipeline | ci-cd |
| OIDC / id-token / sts.amazonaws.com | ci-cd |
| CI access stack / infra/ci_bootstrap | ci-cd |
| diff role / lookup role / cdk diff | ci-cd |
| deploy role / smoke role | ci-cd, chat-api-auth |
| CAAUTH-10 / second principal / CI smoke role | chat-api-auth, ci-cd |
| deploy plan / change detection / last successful deploy | ci-cd |
| pinned deploy context / deploy_context.json | ci-cd, feed-api |
| origin validation (CI) | ci-cd, feed-api |
| schedule guard / schedule DISABLED guard | ci-cd, scheduling |
| SC-5 | scheduling |
| FA-6 | feed-api |
| CloudFormation execution policy / cdk bootstrap | ci-cd |
| handler snapshot / omission list | ci-cd |
| repository protection / ruleset | ci-cd |
| CODEOWNERS | ci-cd |
| CHAT_API_ID / ::add-mask:: | ci-cd |
| .bedrock_agentcore / Dockerfile copy / local-build | runtime-deployment, ci-cd |
| RD-9 / agentcore deploy in CI | runtime-deployment |
| CICD-F (ci-cd reservations) | ci-cd |

## Synchronized Changes

| Change | Archive | Current-State Specification |
|---|---|---|
| curation-graph | [specs/archived/curation-graph/](../archived/curation-graph/) | [curation-pipeline.md](./curation-pipeline.md) |
| tavily-discovery | [specs/archived/tavily-discovery/](../archived/tavily-discovery/) | [curation-pipeline.md](./curation-pipeline.md) |
| dynamodb-card-store | [specs/archived/dynamodb-card-store/](../archived/dynamodb-card-store/) | [card-persistence.md](./card-persistence.md) |
| runtime-packaging | [specs/archived/runtime-packaging/](../archived/runtime-packaging/) | [runtime-deployment.md](./runtime-deployment.md) |
| eventbridge-schedule | [specs/archived/eventbridge-schedule/](../archived/eventbridge-schedule/) | [scheduling.md](./scheduling.md) |
| async-invocation-ack | [specs/archived/async-invocation-ack/](../archived/async-invocation-ack/) | [runtime-deployment.md](./runtime-deployment.md) |
| run-observability | [specs/archived/run-observability/](../archived/run-observability/) | [observability.md](./observability.md) |
| rename-spike-to-shared | [specs/archived/rename-spike-to-shared/](../archived/rename-spike-to-shared/) | [config-loading.md](./config-loading.md) |
| pydantic-settings-config | [specs/archived/pydantic-settings-config/](../archived/pydantic-settings-config/) | [config-loading.md](./config-loading.md) |
| feed-api | [specs/archived/feed-api/](../archived/feed-api/) | [feed-api.md](./feed-api.md) |
| chat-retrieval | [specs/archived/chat-retrieval/](../archived/chat-retrieval/) | [chat-retrieval.md](./chat-retrieval.md), [card-persistence.md](./card-persistence.md), [curation-pipeline.md](./curation-pipeline.md), [runtime-deployment.md](./runtime-deployment.md) |
| chat-agent-runtime | [specs/archived/chat-agent-runtime/](../archived/chat-agent-runtime/) | [chat-agent.md](./chat-agent.md) (new), [runtime-deployment.md](./runtime-deployment.md) (RD-7, RD-8), [chat-retrieval.md](./chat-retrieval.md) (contributing row only) |
| chat-api | [specs/archived/chat-api/](../archived/chat-api/) | [chat-api.md](./chat-api.md) (new) |
| chat-api-auth | [specs/archived/chat-api-auth/](../archived/chat-api-auth/) | [chat-api-auth.md](./chat-api-auth.md) (new), [chat-api.md](./chat-api.md) (CAPI-4 amended, CAPI-6 note, ADR 0027 superseded) |
| backend-cicd-pipeline | [specs/archived/backend-cicd-pipeline/](../archived/backend-cicd-pipeline/) | [ci-cd.md](./ci-cd.md) (new), [runtime-deployment.md](./runtime-deployment.md) (RD-9), [scheduling.md](./scheduling.md) (SC-5), [chat-api-auth.md](./chat-api-auth.md) (CAAUTH-10, ADR 0043 amends ADR 0028), [feed-api.md](./feed-api.md) (FA-6). Implemented and audit-approved with reservations; not live. |

## Decisions (ADR registry)

ADR numbers are **repo-wide monotonic** across both harness roots: 0001–0007 belong to `web-feed-ui` and 0008 to `feed-structure-refactor`, both registered in [`apps/web/specs/current/_index.md`](../../apps/web/specs/current/_index.md) (the frontend index still names 0008 as next, and is not edited here). ADRs 0032–0039 were written by `web-chat-ui` and `web-chat-ui-polish` in the frontend harness (see [`apps/web/specs/current/_index.md`](../../apps/web/specs/current/_index.md)). ADRs 0040 and 0042–0047 were written by `backend-cicd-pipeline`. **0041 was never promoted** (the cap of seven ADRs per feature in `harny-adr` was reached), so it stays unassigned. The next ADR written in either harness is **0048**. ADRs 0028–0031 were written by `chat-api-auth` and supersede ADR 0027. ADR 0043 amends ADR 0028; ADR 0028's file is not edited and its status stays Accepted.

| ADR | Title | Status | Capability | Path |
|---|---|---|---|---|
| 0009 | Brute-force card retrieval over DynamoDB, with a recorded scale ceiling | Accepted | chat-retrieval | [specs/archived/chat-retrieval/decisions/0009-brute-force-card-retrieval-with-a-scale-ceiling.md](../archived/chat-retrieval/decisions/0009-brute-force-card-retrieval-with-a-scale-ceiling.md) |
| 0010 | Embedding is an optional, best-effort step after persist, injected as a writer | Accepted | curation-pipeline | [specs/archived/chat-retrieval/decisions/0010-embedding-as-an-optional-post-persist-writer.md](../archived/chat-retrieval/decisions/0010-embedding-as-an-optional-post-persist-writer.md) |
| 0011 | Vectors are written by a separate conditional writer, never through upsert | Accepted | card-persistence | [specs/archived/chat-retrieval/decisions/0011-vectors-written-by-a-separate-conditional-writer.md](../archived/chat-retrieval/decisions/0011-vectors-written-by-a-separate-conditional-writer.md) |
| 0012 | The Titan embedding call and card text live in a neutral shared module | Accepted | chat-retrieval | [specs/archived/chat-retrieval/decisions/0012-shared-embeddings-module.md](../archived/chat-retrieval/decisions/0012-shared-embeddings-module.md) |
| 0013 | Plane B duplicates Plane A's table, index and store constants instead of importing them | Accepted | chat-retrieval | [specs/archived/chat-retrieval/decisions/0013-plane-b-duplicates-plane-a-constants.md](../archived/chat-retrieval/decisions/0013-plane-b-duplicates-plane-a-constants.md) |
| 0014 | The Titan embedding grant is a separate statement, scoped to the one foundation-model ARN | Accepted | runtime-deployment | [specs/archived/chat-retrieval/decisions/0014-titan-grant-scoped-to-the-foundation-model.md](../archived/chat-retrieval/decisions/0014-titan-grant-scoped-to-the-foundation-model.md) |
| 0015 | The embedding backfill is a local, idempotent one-shot command | Accepted | curation-pipeline | [specs/archived/chat-retrieval/decisions/0015-backfill-as-a-local-one-shot-command.md](../archived/chat-retrieval/decisions/0015-backfill-as-a-local-one-shot-command.md) |
| 0016 | The chat agent is one stateless, synchronous request-response entrypoint | Accepted | chat-agent | [specs/archived/chat-agent-runtime/decisions/0016-one-stateless-synchronous-chat-entrypoint.md](../archived/chat-agent-runtime/decisions/0016-one-stateless-synchronous-chat-entrypoint.md) |
| 0017 | One root Dockerfile serves both agents, with the entrypoint selected by AGENT_ENTRYPOINT | Accepted | runtime-deployment | [specs/archived/chat-agent-runtime/decisions/0017-one-shared-dockerfile-with-entrypoint-selected-by-environment.md](../archived/chat-agent-runtime/decisions/0017-one-shared-dockerfile-with-entrypoint-selected-by-environment.md) |
| 0018 | When retrieval returns nothing, the chat answers with a fixed message and makes no model call | Accepted | chat-agent | [specs/archived/chat-agent-runtime/decisions/0018-empty-retrieval-answers-without-a-model-call.md](../archived/chat-agent-runtime/decisions/0018-empty-retrieval-answers-without-a-model-call.md) |
| 0019 | The request rules and caps are pinned values, validated before any AWS call, with rule names as the error detail | Accepted | chat-agent | [specs/archived/chat-agent-runtime/decisions/0019-request-rules-and-caps-pinned-as-typed-settings.md](../archived/chat-agent-runtime/decisions/0019-request-rules-and-caps-pinned-as-typed-settings.md) |
| 0020 | The chat agent gets its own execution role, in its own CDK construct and stack, and the curation role is not widened | Accepted | runtime-deployment | [specs/archived/chat-agent-runtime/decisions/0020-chat-execution-role-is-a-separate-least-privilege-construct.md](../archived/chat-agent-runtime/decisions/0020-chat-execution-role-is-a-separate-least-privilege-construct.md) |
| 0021 | The default chat model moves from Sonnet 4.5 to Sonnet 4.6, and the Sonnet 4.6 end-of-life date is unconfirmed | Accepted | chat-agent | [specs/archived/chat-agent-runtime/decisions/0021-default-chat-model-moves-to-sonnet-4-6.md](../archived/chat-agent-runtime/decisions/0021-default-chat-model-moves-to-sonnet-4-6.md) |
| 0022 | Chat is exposed as its own HTTP API, not as a route on the feed API | Accepted | chat-api | [specs/archived/chat-api/decisions/0022-chat-is-a-separate-http-api-not-a-feed-api-route.md](../archived/chat-api/decisions/0022-chat-is-a-separate-http-api-not-a-feed-api-route.md) |
| 0023 | Each chat request gets a fresh agent session id, so the Lambda holds no state | Accepted | chat-api | [specs/archived/chat-api/decisions/0023-one-fresh-agent-session-id-per-request.md](../archived/chat-api/decisions/0023-one-fresh-agent-session-id-per-request.md) |
| 0024 | The agent invoke makes no retries, with a 22 s read timeout under a 28 s Lambda limit | Accepted | chat-api | [specs/archived/chat-api/decisions/0024-no-retries-and-a-read-timeout-under-the-lambda-limit.md](../archived/chat-api/decisions/0024-no-retries-and-a-read-timeout-under-the-lambda-limit.md) |
| 0025 | Unexpected errors log the exception class and stack frames, never the message | Accepted | chat-api | [specs/archived/chat-api/decisions/0025-500-path-logs-exception-class-and-frames-only.md](../archived/chat-api/decisions/0025-500-path-logs-exception-class-and-frames-only.md) |
| 0026 | The handler sets its own logger to INFO rather than relying on the runtime's log level | Accepted | chat-api | [specs/archived/chat-api/decisions/0026-handler-sets-its-own-info-log-level.md](../archived/chat-api/decisions/0026-handler-sets-its-own-info-log-level.md) |
| 0027 | The unauthenticated chat endpoint is guarded by throttling and the budget alert alone | Superseded by ADR 0028 | chat-api | [specs/archived/chat-api/decisions/0027-throttling-is-the-only-abuse-guard-on-the-unauthenticated-endpoint.md](../archived/chat-api/decisions/0027-throttling-is-the-only-abuse-guard-on-the-unauthenticated-endpoint.md) |
| 0028 | The chat route is authorized with AWS SigV4 for one dedicated caller, not by throttling | Accepted | chat-api-auth | [specs/archived/chat-api-auth/decisions/0028-chat-route-authorized-by-aws-iam-sigv4-for-one-caller.md](../archived/chat-api-auth/decisions/0028-chat-route-authorized-by-aws-iam-sigv4-for-one-caller.md) |
| 0029 | Browsers are not a supported caller, so the chat API has no CORS configuration | Accepted | chat-api-auth | [specs/archived/chat-api-auth/decisions/0029-browsers-are-not-a-supported-caller-so-no-cors.md](../archived/chat-api-auth/decisions/0029-browsers-are-not-a-supported-caller-so-no-cors.md) |
| 0030 | The caller's access key is long-lived and created by hand, outside CloudFormation | Accepted | chat-api-auth | [specs/archived/chat-api-auth/decisions/0030-caller-access-key-is-long-lived-and-created-outside-cloudformation.md](../archived/chat-api-auth/decisions/0030-caller-access-key-is-long-lived-and-created-outside-cloudformation.md) |
| 0031 | The HTTP API construct keeps its logical id, so the deploy updates the API in place | Accepted | chat-api-auth | [specs/archived/chat-api-auth/decisions/0031-http-api-construct-id-kept-so-the-api-updates-in-place.md](../archived/chat-api-auth/decisions/0031-http-api-construct-id-kept-so-the-api-updates-in-place.md) |
| 0040 | CI authenticates with GitHub OIDC through three least-privilege roles, defined outside the deployed stacks | Accepted | ci-cd | [specs/archived/backend-cicd-pipeline/decisions/0040-github-oidc-with-three-least-privilege-ci-roles-outside-the-stacks.md](../archived/backend-cicd-pipeline/decisions/0040-github-oidc-with-three-least-privilege-ci-roles-outside-the-stacks.md) |
| 0042 | Deploy targets come from the changes since the last successful deploy, not from the parent commit | Accepted | ci-cd | [specs/archived/backend-cicd-pipeline/decisions/0042-deploy-targets-from-changes-since-the-last-successful-deploy.md](../archived/backend-cicd-pipeline/decisions/0042-deploy-targets-from-changes-since-the-last-successful-deploy.md) |
| 0043 | A dedicated CI smoke role becomes a second principal on the chat route, amending ADR 0028 | Accepted | chat-api-auth | [specs/archived/backend-cicd-pipeline/decisions/0043-smoke-role-is-a-second-principal-on-the-chat-route.md](../archived/backend-cicd-pipeline/decisions/0043-smoke-role-is-a-second-principal-on-the-chat-route.md) |
| 0044 | The agents are deployed with a local build, from a copy of the root Dockerfile placed where the toolkit reads it | Accepted | runtime-deployment | [specs/archived/backend-cicd-pipeline/decisions/0044-agents-built-locally-from-a-copy-of-the-root-dockerfile.md](../archived/backend-cicd-pipeline/decisions/0044-agents-built-locally-from-a-copy-of-the-root-dockerfile.md) |
| 0045 | The deploy context is one committed file, and a guard fails the run if the schedule is enabled | Accepted | ci-cd | [specs/archived/backend-cicd-pipeline/decisions/0045-one-committed-deploy-context-and-a-schedule-guard-that-fails-the-run.md](../archived/backend-cicd-pipeline/decisions/0045-one-committed-deploy-context-and-a-schedule-guard-that-fails-the-run.md) |
| 0046 | CloudFormation executes under two scoped customer-managed policies, not AdministratorAccess | Accepted | ci-cd | [specs/archived/backend-cicd-pipeline/decisions/0046-cloudformation-execution-scoped-to-the-ai-radar-resources.md](../archived/backend-cicd-pipeline/decisions/0046-cloudformation-execution-scoped-to-the-ai-radar-resources.md) |
| 0047 | Repository protection is applied by a rerunnable script that dry-runs by default | Accepted | ci-cd | [specs/archived/backend-cicd-pipeline/decisions/0047-repository-protection-as-a-rerunnable-script-that-dry-runs-by-default.md](../archived/backend-cicd-pipeline/decisions/0047-repository-protection-as-a-rerunnable-script-that-dry-runs-by-default.md) |

All 10 features archived in the 2026-09-17 bootstrap pass shipped before
`harny-adr` existed in this project; per that skill's own no-backfill
guardrail, none get retroactive ADRs. `web-feed-ui`'s ADRs (the first real
ones) now live with the frontend harness, see above. `chat-retrieval` is the
first feature archived here with ADRs (0009–0015, from its approved execution plan).

## Open reservations

> Non-blocking findings accepted at ship time and still open.

| ID | Reservation | Severity | Source | Capability |
|---|---|---|---|---|
| ES-1 | The prescribed double-fire dedup drill has never been run as its own test. | MEDIUM | `specs/archived/eventbridge-schedule/audit.md` | scheduling |
| ES-2 | The daily cadence has never run unattended — schedule stays `DISABLED`. | MEDIUM (operational, deliberate) | `specs/archived/eventbridge-schedule/audit.md` | scheduling |
| RO-1 | `CURATION_EMIT_METRICS=false` kill switch never exercised live, offline-tested only. | LOW | `specs/archived/run-observability/audit.md` | observability |
| RO-2 | No unattended/scheduled run has ever produced observability records — depends on ES-2. | MEDIUM (operational) | `specs/archived/run-observability/audit.md` | observability |
| FA-R1 | Deployed feed-api Lambda's `ReservedConcurrentExecutions` is unreserved (`null`), not the contract's intended `5`, bridged by an account-quota workaround. | LOW (operational) | `specs/archived/feed-api/audit.md` AD-7 | feed-api |
| F7 | Not verified in CI or live: the branch is unpushed, so no `harny-feedback.yml` run and no Stop-hook evidence exist; AC7 is verified offline only (no live `run_chat.py` against DynamoDB and Bedrock). | LOW | `specs/archived/chat-retrieval/audit.md` (F7) | chat-retrieval |
| F11 | Accepted limitation: a card whose `upsert` failed still gets a Titan call (about $0.00002 per card, auditor's estimate); counted in `embed_failed`, AC2 holds. | LOW | `specs/archived/chat-retrieval/audit.md` (F11) | curation-pipeline |
| CAR-F5 | `tests/test_chat_app.py` `empty-text` param is a bare list (exercises `payload_not_object`); empty text is covered elsewhere. | LOW | `specs/archived/chat-agent-runtime/audit.md` (F5) | chat-agent |
| CAR-F6 | Plan `-k` selectors miss some tests; the broad command is the reliable gate. | LOW | `specs/archived/chat-agent-runtime/audit.md` (F6) | chat-agent |
| CAR-F7 | `upstream_failure` `chat_turn` records report `hits=0` and `retrieval_ms=0`, losing the partial latency. | LOW | `specs/archived/chat-agent-runtime/audit.md` (F7) | chat-agent |
| CAR-F8 | CI (`harny-feedback.yml`) has not run on a PR for the chat-agent-runtime change; the branch is unpushed. | LOW | `specs/archived/chat-agent-runtime/audit.md` (F8) | chat-agent |
| CAPI-F5 | Runbook step 10 (the agent-side invocation count for one slow request) is not run. The live 502 and 504 paths were not triggered, so the no-retry property rests on the offline socket probe. | LOW | `specs/archived/chat-api/audit.md` (F5) | chat-api |
| CAPI-F7 | CI has not run on the branch, because it is unpushed. The evidence is local. | LOW | `specs/archived/chat-api/audit.md` (F7) | chat-api |
| CAPI-F8 | The `.gitignore` edit (`.env*`, `!.env.example`) and the `pyproject.toml` `botocore.*` mypy override are changes outside the plan's ownership, awaiting the human's confirmation. | LOW | `specs/archived/chat-api/audit.md` (F8) | chat-api |
| CAPI-F11 | The function is unreserved, so it shares the account's 10-slot Lambda pool with `ai-radar-feed-api`, and a parallel burst returns 503s. Quota increase requested 2026-10-21 (support case 179259663100438, `CASE_OPENED`); once approved, redeploy both APIs without the `none` flag and re-run the burst. Since `chat-api-auth`, the re-run must be signed (unsigned requests get 403 at the gateway). | MEDIUM | `specs/archived/chat-api/audit.md` (F11) | chat-api |
| CAPI-F13 | Stage throttling is best-effort and lenient: 64 of 80 requests passed at about 20 req/s, where a strict bucket would pass about 30. The real ceiling under abuse is about twice nominal. The `AiRadarBudget` alert is the backstop. | LOW | `specs/archived/chat-api/audit.md` (F13) | chat-api |
| CAR-F11 | Retrieval latency and the ADR 0009 ceiling rest on one live sample (`retrieval_ms=330`, 16 live cards). No p95 yet; accepted by the human on 2026-10-18. | LOW | `specs/archived/chat-agent-runtime/audit.md` (F11) | chat-agent, chat-retrieval |
| CAAUTH-F1 | The expired-signature case is not exercised live. The human accepted `--tamper` as the bad-signature probe, but intent AC2 still says "expired". | LOW | `specs/archived/chat-api-auth/audit.md` (F1) | chat-api-auth |
| CAAUTH-F3 | The Docker build context does not exclude caches such as `.mypy_cache`. Pre-existing debt. | LOW | `specs/archived/chat-api-auth/audit.md` (F3) | chat-api-auth |
| CAAUTH-F5 | No test asserts that importing `run_chat_api_smoke.py` makes no network or STS call. | LOW | `specs/archived/chat-api-auth/audit.md` (F5) | chat-api-auth |
| CAAUTH-F6 | CI (`harny-feedback.yml`) has not run, because the branch is unpushed. | LOW | `specs/archived/chat-api-auth/audit.md` (F6) | chat-api-auth |
| CAAUTH-F9 | The signed `GET /v1/chat` and signed `POST /v1/other` probes were not run. The unsigned 404 evidence was accepted by the human on 2026-10-21. | LOW | `specs/archived/chat-api-auth/audit.md` (F9) | chat-api-auth |
| CAAUTH-F11 | The `chat-api` F11 closure re-check must be a signed burst, because unsigned floods get 403 at the gateway. No signed burst tool exists. Open work. | MEDIUM | `specs/archived/chat-api-auth/audit.md` (round 2) | chat-api-auth, chat-api |
| CAAUTH-ADMIN | An HTTP API has no resource policy, so any identity in the account with its own `execute-api:Invoke` grant (an administrator, for example) can also call the route. Accepted limitation. | LOW (accepted) | ADR 0028; `specs/archived/chat-api-auth/audit.md` (plan-flagged limits) | chat-api-auth |
| CAAUTH-KEY | The caller access key is long-lived and stays `Active` in the local profile until the `apps/web` signing spec ships. | LOW (accepted) | ADR 0030; `specs/archived/chat-api-auth/audit.md` (round 2 note) | chat-api-auth |
| CAAUTH-SMOKE | The principals that may call `POST /v1/chat` grow from one to two: the CI smoke role (CAAUTH-10, ADR 0043). The HTTP API has no resource policy, so the limit is the grant alone. Accepted by the human 2026-10-27 (Q4); the smoke role's live 200 and the deploy role's 403 are pending O12 f. | LOW (accepted) | `specs/archived/backend-cicd-pipeline/audit.md` (round 2); ADR 0043 | chat-api-auth |
| CICD-F8 | The live O12 steps (a)–(i) have not run: nothing is deployed, and the first PR diff, deploy, protection apply and signed-probe checks are pending. Human-only, expected. | LOW | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, F8) | ci-cd |
| CICD-F10 | The smoke job's mask step still reads `ChatApiUrl` with `2>/dev/null \|\| true`. No leak path found; inconsistent with the deploy job, which fails closed. | LOW | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, F10) | ci-cd |
| CICD-F11 | README `CHAT_API_ID` note corrected 2026-10-28. Residual: a stale variable after a chat API id change leaves the new URL unmasked in the deploy log. Accepted as-is. | LOW | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, F11) | ci-cd |
| CICD-F12 | Unused account-level grants on `*` (`logs:PutResourcePolicy`, `logs:DeleteResourcePolicy`, `billing:GetBillingViewData`). Accepted as-is. | LOW | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, F12) | ci-cd |
| CICD-F13 | Omission patterns are global wildcards, and the coverage test checks one primary action per type. Accepted; keying omissions by type is recommended. | LOW | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, F13) | ci-cd |
| CICD-F14 | `iam:ListGroupsForUser` and `iam:GetLoginProfile` are omitted, so an update or delete of the caller user may fail with `AccessDenied`. Recoverable; watched in O12 h. Accepted as-is. | LOW | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, F14) | ci-cd |
| CICD-F15 | `tasks.md` has two stale rows (the "Red test bug (O3)" response; O12(a) names three role ARNs where five variables are needed). Accepted as-is; the archived file is not edited. | LOW | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, F15) | ci-cd |
| CICD-ESC | Accepted escalation path: a merged template can create an `AiRadar*` role with an arbitrary inline policy and trust. Controls are the ruleset, `CODEOWNERS` and the PR diff; a permissions boundary is the follow-up. | LOW (accepted) | `specs/archived/backend-cicd-pipeline/audit.md` (round 2); ADR 0046 | ci-cd |
| CICD-VERCEL | The Vercel origin is not yet in the context file (open item, not a blocker). | LOW (open) | `specs/archived/backend-cicd-pipeline/intent.md` § Open questions | ci-cd |
| CICD-SOLO | Required approvals 0 and code-owner review off while there is one maintainer; the choice awaits the human's confirmation. | LOW (open) | `specs/archived/backend-cicd-pipeline/intent.md` § Open questions; ADR 0047 | ci-cd |

## Notes

This index was bootstrapped empty on 2026-09-17 (no `specs/current`/
`specs/archived` split existed yet for this project) and populated for real
in the same session once the human resolved the one blocking precondition:
none of the 10 already-shipped features carried a `Shipped:` header. All 10
were then stamped (using each feature's audit sign-off date, not the
bootstrap date) and archived via the normal `harny-document` post-audit
path — see `CHANGELOG.md` for the full per-feature ship history and
`README.md` for live-deploy/verification evidence.

`web-feed-ui` (Phase 2 spec 02, the Next.js frontend) archived 2026-09-18
after passing its full TDD → implement → audit pipeline, a human-approved
fix-up pass resolving all 4 post-audit reservations (a `.env.example`
gitignore bug, a missing design-pinned URL line, an explicit AD-9
acceptance, and Next 16's stray `AGENTS.md`/`CLAUDE.md` auto-scaffold), and
a human running the app locally and confirming it. This created the new
`web-feed` capability doc — it is a genuinely new capability, not a merge
into `feed-api`, because it's a separate runtime/language boundary with its
own toolchain and its own generated-types drift guarantee. **It is locally
verified only** — no Vercel deploy has happened and `feed-api`'s CORS
allow-list has not been updated (see `WEB-R1` above); Phase 5 of
`roadmap.md` remains a human-run runbook.

`rename-spike-to-shared` had one additional blocker beyond the missing
stamp: its audit's Close-out checklist had an open item ("Human confirms
Tasks H1-H3 done"), since its migration includes untracked/gitignored local
state (`.env`, the JSON dedup cache directory) that only a human can move.
The human live-verified all three tasks on 2026-09-17 (see
`specs/archived/rename-spike-to-shared/audit.md`'s Close-out checklist for
the exact verification output) before this feature was archived — which is
also why its `Shipped:` date (2026-09-17) is later than its code-merge/audit
date (2026-08-17): the spec's own contract treats full close-out, not code
merge, as "shipped."

No ADRs were written for any of the 10 features in this pass — `harny-adr`
did not exist in this project when any of them were approved, and that
skill's own guardrail forbids reconstructing rationale retroactively for
already-shipped work. ADRs apply only to features archived from here
forward.

**2026-09-20 component split.** A second harny harness was installed at
`apps/web/` (`stack: typescript`) so frontend work gets eslint/tsc feedback
instead of the root's ruff/mypy. The frontend knowledge base moved with it:
`specs/current/web-feed.md` → `apps/web/specs/current/web-feed.md` and
`specs/archived/web-feed-ui/` → `apps/web/specs/archived/web-feed-ui/`
(including ADRs 0001–0007 and reservations WEB-R1..R3). The `feed-api`
capability stays here — it is backend code, and `web-feed` consumes it.

**2026-10-13 chat-retrieval.** Phase 3's first spec, archived after an approved
audit (round 3, APPROVED WITH RESERVATIONS) and the human's sign-off. It creates
the `chat-retrieval` capability and merges into `card-persistence` (PS-2 names
its sanctioned writer; new PS-5), `curation-pipeline` (CP-1 amended; new CP-6,
the optional embed step) and `runtime-deployment` (RD-3 names the Titan grant).
**Nothing from it is deployed:** the runtime role needs a redeploy, the agent image
needs a rebuild, and the backfill has not been run. The live checks in F7 are open.
Its ADRs (0009–0015) are the first in this root to be written by `harny-adr`.

**2026-10-18 chat-agent-runtime.** The RAG chat runs as its own stateless agent (`chat_app.py`,
AgentCore Runtime agent `ai_radar_chat`, deployed 2026-10-18). It creates the `chat-agent`
capability (CA-1..CA-6, new `chat-agent.md`) and amends `runtime-deployment` with RD-7 (a
separate chat execution role, in `AiRadarChatRuntime`, with the curation role not widened)
and RD-8 (one shared Dockerfile whose entrypoint is selected by `AGENT_ENTRYPOINT`). That
selector narrows the intent's "separate Dockerfile": the toolkit builds only the root
Dockerfile. `chat-retrieval` gets a contributing row and no requirement change. Its ADRs are
0016–0021. `harny-adr` wrote them. Its own open reservations are CAR-F5..F8 and CAR-F11, all
LOW. The live AC10 steps ran on 2026-10-18. The deployed Sonnet 4.6 default is recorded in
ADR 0021 (its end-of-life date is unconfirmed). The chat-retrieval reservations F7 and F11 are
unchanged.

**2026-10-21 chat-api.** The public edge for the chat agent, `AiRadarChatApi`, deployed on
2026-10-21 (the `POST /v1/chat` route, unauthenticated and throttled at that point; `chat-api-auth` made it SigV4-authenticated later the same day). It creates the `chat-api`
capability (CAPI-1..CAPI-8, new `chat-api.md`) and amends no existing capability: `chat-agent`,
`feed-api` and `runtime-deployment` are unchanged. Its ADRs are 0022–0027, written by `harny-adr`
from the approved execution plan. Its open reservations are CAPI-F5, F7, F8, F11 and F13. F11 is
MEDIUM: the function is unreserved while the account Lambda quota is 10, so it shares a pool with
the feed API. The live runbook steps 1–9 ran; step 10 did not.

**2026-10-21 chat-api-auth.** `POST /v1/chat` now requires AWS SigV4 (`AWS_IAM`) from one stack-created
caller, `ai-radar-chat-api-caller`, with one `execute-api:Invoke` statement. The stack creates no
access key, and the human created the key outside CloudFormation. The API has no CORS configuration,
and the `chat_api_allowed_origins` option is removed. This is the same API, updated in place. The
`chat-api-auth` capability (CAAUTH-1..CAAUTH-9, new `chat-api-auth.md`) amends `chat-api` CAPI-4
(CORS retired) and CAPI-6 (a note), and supersedes ADR 0027 with ADR 0028. Its ADRs are 0028–0031,
written by `harny-adr` from the approved execution plan. Its open reservations are CAAUTH-F1, F3, F5,
F6, F9 and F11 (MEDIUM, the signed F11 re-check), plus the accepted admin and caller-key limits. The
live O7 steps ran on 2026-10-21 with the F9 exception. The `apps/web` server-side signing is a
follow-up spec.

**2026-10-28 backend-cicd-pipeline.** The backend CI/CD pipeline is archived as implemented and
audit-approved with reservations (round 2). **It is NOT live.** Nothing is deployed and the workflows have
not run on GitHub. The CI access stack deploy, the five repository variables, the CDK re-bootstrap with the
two scoped execution policies, the protection script and the first pipeline run are human-only steps (tasks
O12 a–i) and have not happened. Every live statement in `ci-cd.md` is therefore pending. The feature creates
the `ci-cd` capability (CICD-1..CICD-16, new `ci-cd.md`) and amends `runtime-deployment` (RD-9, ADR 0044),
`scheduling` (SC-5), `chat-api-auth` (CAAUTH-10, ADR 0043, which amends ADR 0028, whose file stays
unedited) and `feed-api` (FA-6). Its ADRs are 0040 and 0042–0047; 0041 was never promoted, because `harny-adr`
caps a feature at seven ADRs. Its open reservations are CICD-F8, F10–F15, CICD-ESC, CICD-VERCEL and
CICD-SOLO, plus CAAUTH-SMOKE. The audit's round-1 findings F1–F6 and F9 are closed, and F7 is closed on reused
evidence.

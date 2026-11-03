# History and verification record

How AI Radar was built, and the live evidence behind its status. This file was split out of the root README so the README can stay current. For authoritative per-feature detail read the archived specs (`specs/archived/<feature>/`, each with `audit.md` and `decisions/`) and [`CHANGELOG.md`](../CHANGELOG.md). Dates are 2026. Original plans: [`tasks/phase-1-curation-mvp/`](../tasks/phase-1-curation-mvp/) and [`tasks/phase-2-web-feed/`](../tasks/phase-2-web-feed/).

## Timeline

| Phase | Feature (spec) | Shipped | What it added |
|---|---|---|---|
| 0 | Local spike | Jul | RSS discover, dedup, Haiku summarize and tag, console cards (`run_curation.py`); Titan embeddings, in-memory cosine, Sonnet grounded chat with citations (`run_chat.py`). Proved both planes against real Bedrock with no infra |
| 1 | `curation-graph` | Jul | LangGraph `StateGraph` with `Discoverer` / `CardStore` Protocols and JSON-file defaults |
| 1 | `tavily-discovery` | Jul | `TavilyDiscoverer` and `CompositeDiscoverer` (RSS + Tavily, cross-source dedup) |
| 1 | `dynamodb-card-store` | Jul | `DynamoCardStore`, CDK table `ai-radar-cards` (pay-per-request, `RETAIN`) and the `feed-by-score` GSI |
| 1 | `runtime-packaging` | Jul 28 | `runtime_app.py` on AgentCore Runtime, least-privilege CDK role, Tavily key from Secrets Manager. Real deploy: 0 to 8 to 16 cards, teardown verified |
| 1 | `eventbridge-schedule` | Aug 10 | Daily Scheduler schedule, deploys `DISABLED`. First live fire double-delivered (finding F5) |
| 1 | `async-invocation-ack` | Aug 10 | Entrypoint acks immediately and runs curation as a background task; fixes F5 |
| 1 | `run-observability` | Aug 12 | `RunSummary`, EMF metrics, `AiRadarBudget` |
| x | `pydantic-settings-config`, `rename-spike-to-shared` | Aug | Config loading via `pydantic-settings`; `src/spike` renamed to `src/shared`, `SPIKE_*` to `AI_RADAR_*`. Agent redeployed Aug 30 |
| 2 | `feed-api` | Sep 3 | `GET /v1/cards` (API Gateway + Lambda + `Query` on `feed-by-score`), cursor pagination, `?tag=` filter, versioned Pydantic contract and JSON Schema |
| 2 | `web-feed-ui`, `feed-structure-refactor` (in `apps/web/specs/archived/`) | Sep 18, Oct 3 | Next.js feed with tag filter and pagination, generated TypeScript types, Playwright e2e tier |
| move | Account migration | Oct 5 | Whole backend redeployed into account `626259825216` from scratch |
| 3 | `chat-retrieval` | Oct 13 (deployed Oct 18) | Curation-time Titan embeddings, backfill, `DynamoCardRetriever`, `CARD_STORE_BACKEND` switch |
| 3 | `chat-agent-runtime` | Oct 18 | Stateless `ai_radar_chat` agent, validation caps, own least-privilege role, Sonnet 4.6 default |
| 3 | `chat-api`, `chat-api-auth` | Oct 21 | `POST /v1/chat` behind API Gateway and a Lambda; then SigV4 (`AWS_IAM`) with one dedicated caller; CORS removed |
| 3 | `web-chat-ui`, `web-chat-ui-polish` (in `apps/web/specs/archived/`) | Oct 24 | Chat widget with a SigV4-signing server route, markdown answers, phone bottom sheet |
| CI | `backend-cicd-pipeline`, `ci-log-masking` | Oct 28 | GitHub Actions + OIDC checks, PR diff, change-based deploy and smoke; ids moved to secrets. Live: two deploy runs on `main` succeeded Oct 28 |

## Live-verification record

Highlights only; full evidence is in each spec's `audit.md`.

**Curation agent.** Real deploy Jul 28: first invoke 50 discovered, 8 summarized, table 0 to 8. A re-invoke deduped 50 to 42 and still grew the table to 16, because `AI_RADAR_MAX_ITEMS=8` caps new items per run (incremental by design, not a dedup bug). After `async-invocation-ack` (Aug 10) the ack came back immediately and the completion record appeared 36.5 s later, past the ~30 s point that broke the old handler; cards 40 to 48. A genuine back-to-back double invoke against the deployed agent (to see `already_running` in production) was never run; the guard is proven offline only.

**Schedule.** First live fire (Aug 10) moved cards 24 to 40 because the fire delivered twice: Scheduler's universal target has an undocumented ~30 s synchronous timeout and the run took 25-35 s, so the slow success was retried. The DLQ stayed empty throughout, which gave false confidence; `TargetErrorCount` is the real check. After the fix, one fire produced `InvocationAttemptCount=1`, zero `TargetErrorCount` datapoints, one completion record and cards 48 to 56. The wire-format details (service id `bedrockagentcore`, PascalCase keys, plain-string `Payload`) were only provable by the live fire. A mid-run sample undercounted cards (finding F6). The Aug 30 redeploy smoke saw cards 80 to 88; a slow BAIR Blog feed stretched that run to about 2.5 min without failures.

**Observability (Aug 12).** `AiRadarBudget` created cleanly; `cdk diff` on the other stacks stayed empty; the SNS subscription was confirmed and a test message delivered. A real invoke produced all six log records, with the EMF line as its own top-level JSON event (the spec's biggest design risk), and exactly four metrics in `AIRadar/Curation`. Token counts matched Bedrock's own CloudWatch meter exactly (10593 in, 2553 out). Of a $0.063358 estimate, $0.04 was the Tavily estimate. The two AWS Budgets in the account read slightly different actuals ($5.322 vs $5.382), showing `IncludeCredit: false` has a real effect.

**Feed API (Sep 3-4).** Stack `CREATE_COMPLETE`. Verified live: limit and cursor pagination (disjoint pages), tag filter, `?limit=0` returns 400 `invalid_limit`, and CORS echoes `http://localhost:3000` while an unlisted origin gets no CORS header. The index-only `dynamodb:Query` grant was sufficient, so the `grant_base_table_query` fallback was never needed. The Lambda is unreserved (quota 10) instead of the designed reservation of 5; endpoint throttling is 20 req/s, burst 40. The Lambda image was built and import-tested locally (about 843 MB, of which about 590 MB is the AWS base image).

**Web feed.** Locally verified against the real API: server-rendered feed, tag chips and pagination, a bounded drain of empty pages that carry a live cursor (`feed-api` Guarantee 4, probed with `?tag=zzz-no-such-tag`), and four exhaustive UI states. Open question: whether `signal: AbortSignal.timeout(...)` on the feed fetch disables Next's Data Cache is not settled by the Next docs; the signal was kept to bound a hung upstream to 8 s.

**Account migration (Oct 5-6).** Deployed `CDKToolkit`, `AiRadarCardStore`, `AiRadarRuntimeRole`, `AiRadarSchedule` (`DISABLED`), `AiRadarBudget`, `AiRadarFeedApi`, and the curation agent. Smoke: 30 discovered, 8 persisted in 26.9 s, table 0 to 8. `AiRadarFeedApi` failed on the Lambda quota until deployed with `feed_api_reserved_concurrency=none`.

**Chat rollout (Oct 18).** `AiRadarRuntimeRole` gained `InvokeTitanEmbed` (`UPDATE_COMPLETE` 23.6 s). Curation pass: 40 discovered, 8 persisted, `embedded 8`, `embed_failed 0`, cards 8 to 16. Backfill: `embedded=8 skipped=8 failed=0`, then `embedded=0 skipped=16 failed=0`. `AiRadarChatRuntime` created in 39 s; the role has the seven designed statements and nothing else. Bedrock accepted the Sonnet 4.6 `cachePoint` plus `temperature` request shape. A real question returned a cited answer with 4 sources, all present in the table (`retrieval_ms` 330, `model_ms` 3304). An empty question returned `invalid_request` with no retrieval or model call. Only one latency sample exists, so no p95: a recorded reservation (finding F11 of `chat-agent-runtime`). `upstream_failure` records report `hits=0` and `retrieval_ms=0` even when retrieval succeeded (finding F7, LOW).

**Chat API (Oct 21).** Deployed `CREATE_COMPLETE` in 66 s. Before auth: grounded question 200 in 7.0 s, bad body 400, non-JSON body 400, GET 404, the Lambda cold start 2996 ms, peak memory 110 MB of 256 MB. A 40-way unsigned parallel burst returned Lambda 503s (`Throttles` 27, `ConcurrentExecutions` 10), exhausting the account pool shared with the feed API (finding F11, open until the quota rises). A steady ~20 req/s for ~4 s returned 64 x 400 and 16 x 429, so the stage throttle engages but is lenient (F13). After `chat-api-auth` (deployed in place, `UPDATE_COMPLETE` in 60 s, same API id): unsigned valid body, unsigned non-JSON, fabricated `Authorization`, tampered and unsigned script runs, and a policy-less IAM identity all returned 403; the caller key returned 200 with a cited answer in 5161 ms; `OPTIONS` and unsigned `GET` returned 404 with no CORS headers; `CorsConfiguration` is null; Lambda `Invocations` read 1.0, so rejected requests never reached the function. Not run: signed unrouted probes (F9, accepted), the slow-turn no-retry check (F5, covered offline).

**CI/CD (Oct 28).** The first deploy run found two real defects, both fixed the same day: the deploy role lacked `ecr:CreateRepository` on the two agent repositories, and the chat API id and account id were printed into public Actions logs. The latter led to repository secrets (ADR 0048) and the log-deletion procedure in [`runbooks.md`](runbooks.md#cicd-one-time-bootstrap). Open live checks and reservations are in [`specs/current/ci-cd.md`](../specs/current/ci-cd.md).

## Other facts worth keeping

- **Embedding behavior.** The `embed` node runs after `persist` only when an embedding writer is passed. `DynamoCardStore.set_embeddings` is a conditional `update_item` that never creates an item; `upsert` never writes `embedding`, so a re-upsert leaves a vector intact. A Titan failure leaves the card stored without a vector and never fails the run. `DynamoCardRetriever` runs a paginated `Query` on `feed-by-score` (partition `CARD`), never a `Scan`, ranks by dot product (cosine, since vectors are normalized), and excludes un-embedded and wrong-length cards.
- **Shared answer step.** `answer_question` in `src/shared/chat.py` holds the prompt, context block, `[n]` numbering and the Sonnet call. `RagChat.ask` delegates to it, so `run_chat.py` and the chat agent send identical model requests.
- **Single `Dockerfile`.** The toolkit builds only the `Dockerfile` at an agent's `source_path`, so both agents share one file and select their entrypoint with `AGENT_ENTRYPOINT`.
- **Scale arithmetic.** At 8 new cards per run, 2,000 cards is about eight months of daily runs.
- **Test counts over time.** 145 (run-observability), 261 (pydantic-settings-config), 349-350 (feed-api), 406 (chat-retrieval), 487 (chat-agent-runtime), 835 (current, after CI and chat API work).

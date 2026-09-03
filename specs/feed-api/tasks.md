# Tasks: feed-api

## Legend
- [ ] Not started
- [x] Completed
- [~] In progress
- [!] Blocked

Phases mirror `roadmap.md`. Every task names the real file it touches. Test
IDs (T1–T27) refer to `audit.md`'s Test Coverage table.

## Phase 1: Published contract + config

- [x] Task 1.1: `uv add --group api pydantic` — create the `api` dependency group (AD-2); commit the regenerated lockfile — `pyproject.toml`, `uv.lock`
- [x] Task 1.2: Create the published-contract package with `CARD_SCHEMA_VERSION = "v1"`, `CardOut`, `FeedResponse`, `json_schema()`; fields taken from the item `DynamoCardStore.upsert` actually writes — `src/contracts/__init__.py`, `src/contracts/card.py`
- [x] Task 1.3: Create the API-plane config (`_ApiSettings` + UPPERCASE surface + fixed `FEED_GSI_NAME`/`FEED_GSI_PARTITION`, no `shared.config` import per AD-3) — `src/api/__init__.py`, `src/api/config.py`
- [x] Task 1.4: Create the schema-export entrypoint and run it — `export_api_schema.py`, `docs/api/feed-api.v1.schema.json`
- [x] Task 1.5: Append the `FEED_API_*` comment block — `.env.example`

## Phase 2: Core logic — cursor + query

- [x] Task 2.1: Implement `CURSOR_KEYS`, `InvalidCursorError`, `encode_cursor` (key-sorted compact JSON → base64url, padding stripped) — `src/api/cursor.py`
- [x] Task 2.2: Implement `decode_cursor` with full validation (re-pad, decode, JSON object, exact key set, all-`str` values, `gsi_pk == FEED_GSI_PARTITION`) — `src/api/cursor.py`
- [x] Task 2.3: Implement the lazy-singleton resource + `card_table(client=None)` (the only `boto3` import under `src/api/`) — `src/api/dynamo.py`
- [x] Task 2.4: Implement `FeedPage` + `query_feed` — one GSI query with the pinned `ProjectionExpression`/`ExpressionAttributeNames`, `ScanIndexForward=False`, optional `FilterExpression`/`ExclusiveStartKey` — `src/api/feed.py`
- [x] Task 2.5: Add per-item `CardOut.model_validate` try/except with the `skipped` counter (house rule: one bad item never kills the page) — `src/api/feed.py`

## Phase 3: HTTP handler + Lambda image

- [x] Task 3.1: Implement query-param parsing per the contract table — `tag` (blank == absent), `limit` (default 20, `[1,100]`, else 400), `cursor` (else 400, before any AWS call) — `src/api/handler.py`
- [x] Task 3.2: Implement the success path: `query_feed` → `FeedResponse(...).model_dump_json()` → `{"statusCode": 200, "headers": {"content-type": "application/json"}, "body": …}`; no CORS headers (API Gateway owns CORS) — `src/api/handler.py`
- [x] Task 3.3: Implement the error paths: typed 400 bodies, catch-all 500 `internal_error` that never echoes the exception text and never re-raises — `src/api/handler.py`
- [x] Task 3.4: Add the structured `feed_api_request` log record (`json.dumps`, `logger.exception` on failure), mirroring `runtime_app.py`'s idiom — `src/api/handler.py`
- [x] Task 3.5: Write the Lambda image: AWS base image + `uv` copied in + `uv export --frozen --only-group api` → `uv pip install --target ${LAMBDA_TASK_ROOT}` + `COPY src/api/`, `src/contracts/` + `CMD ["api.handler.handler"]` — `Dockerfile.feed_api`
- [x] Task 3.6: Build it once locally (`docker build --platform linux/arm64 -f Dockerfile.feed_api .`) to prove the `uv export` recipe works before CDK depends on it; confirm `.dockerignore` needs no change — `Dockerfile.feed_api`, `.dockerignore` — DONE 2026-09-02 (Docker daemon confirmed available): `docker build -f Dockerfile.feed_api --platform linux/arm64 -t ai-radar-feed-api-local-check .` from the repo root succeeded (exit 0). `.dockerignore` confirmed to need no change. The build surfaced a real bug: `pydantic-settings` was missing from the `api` dependency group (`src/api/config.py` needs it per contract.md's own pinned interface code), causing `ModuleNotFoundError` on `import api.handler` inside the built image — fixed via `uv add --group api pydantic-settings` (`pyproject.toml`/`uv.lock`), rebuilt, and re-verified: `import api.handler, contracts.card` and a full `handler()` call against a fake table both succeeded inside the image (200, correct empty-feed body). `uv run pytest tests/` stayed green after the fix (349 passed, 0 failed). Image size: `docker images` reports 843 MB (base Lambda Python 3.12 image ≈ 590 MB; this spec's own layers ≈ 44 MB: 36 MB `uv` binary + 7.65 MB pydantic/pydantic-settings + ~70 KB app code). No AWS calls, no registry push, no `cdk deploy` — see `specs/feed-api/audit.md`'s 2026-09-02 Audit Log entry (closes finding F2) for full evidence. Local test image removed after verification (`docker rmi`).

## Phase 4: Infrastructure (CDK)

- [x] Task 4.1: Create the construct's module-level defaults (origins, throttle 20/40, memory 512, timeout 10s, reserved concurrency 5, `ONE_MONTH` retention, table/GSI/route literals) — `infra/lib/feed_api.py`
- [x] Task 4.2: Create the explicit `logs.LogGroup` (`/aws/lambda/ai-radar-feed-api`, `DESTROY`) and the hand-authored `iam.Role` with the two pinned statements (`FeedGsiQuery`, `FeedApiLogsWrite`) and **no** managed policy, plus the `grant_base_table_query` AD-6 flag — `infra/lib/feed_api.py`
- [x] Task 4.3: Create the `DockerImageFunction` (asset dir = `Path(__file__).parents[2]`, `file="Dockerfile.feed_api"`, `Platform.LINUX_ARM64`, `Architecture.ARM_64`, custom role + log group, env `CARD_TABLE_NAME`) — `infra/lib/feed_api.py`
- [x] Task 4.4: Create the `HttpApi` with scoped `cors_preflight`, add the `GET /v1/cards` route via `HttpLambdaIntegration`, and apply `CfnStage.RouteSettingsProperty` throttling to the `$default` stage — `infra/lib/feed_api.py`
- [x] Task 4.5: Create the stack: context-driven `feed_api_allowed_origins` + the four `CfnOutput`s — `infra/stacks/feed_api_stack.py`
- [x] Task 4.6: Wire the stack into the app (one import + one line; the four existing stacks untouched) — `infra/app.py`
- [x] Task 4.7: `uv run cdk synth --app "python infra/app.py" AiRadarFeedApi` and eyeball the template before writing assertions — no file change (synth succeeded, no Docker daemon required, confirmed before running `tests/test_infra_feed_api.py`)

## Phase 5: Testing & validation

- [x] Task 5.1: Add an additive `seed_cards` fixture (deterministic `gsi_sk` ordering + known tags) alongside the existing `dynamo_resource`/`dynamo_table` fixtures — `tests/conftest.py`
- [x] Task 5.2: Cursor tests T5, T8 (inverse, determinism, every rejection path) — `tests/test_feed_cursor.py`
- [x] Task 5.3: Query tests T1, T2, T3, T6, T23 (ordering, tag filter, limit, last-page `None` cursor, projection excludes `gsi_*`/`embedding`, `Decimal`→`int`) — `tests/test_feed_query.py`
- [x] Task 5.4: Query tests T4, T7, T11 — short filtered page with a live cursor, the **multi-page round-trip equivalence** test (filtered and unfiltered), malformed-item skip — `tests/test_feed_query.py`
- [x] Task 5.5: Handler tests T9, T10, T12, T13, T14, T22 (400s incl. no-AWS-call proof, no CORS headers, blank/no-match tag, 200 body validated by `FeedResponse.model_validate_json`, 500 without leaking exception text) — `tests/test_feed_api_handler.py`
- [x] Task 5.6: Contract tests T19, T20 (schema-artifact drift, cross-plane literal drift, AST plane-separation + `boto3` confinement) — `tests/test_feed_api_contract.py`
- [x] Task 5.7: Infra synth tests T15, T16, T17, T18, T25, T26, T27 (IAM by `Sid`, no wildcard/managed policy/write action, zero tables, CORS origins incl. a context override, throttling/concurrency/arm64/timeout, route + payload format, log group + outputs) — `tests/test_infra_feed_api.py`
- [x] Task 5.8: Dockerfile regression test T24 (functional assertions, not a text diff) — `tests/test_feed_api_dockerfile.py`
- [x] Task 5.9: `uv run pytest tests/` green; confirm the suite still needs no credentials, no network, and no Docker daemon (T21) — no file change

## Phase 6: Deploy, live-verify, document

- [ ] Task 6.1: `uv sync --group infra`; `cdk diff` the four existing stacks and confirm empty (M1) — no file change — NOT VERIFIED: the human's real `cdk deploy AiRadarFeedApi -c feed_api_reserved_concurrency=none --require-approval never` (2026-09-02/03) proceeded directly; no `cdk diff` output on the other four stacks (`AiRadarCardStore`, `AiRadarRuntimeRole`, `AiRadarSchedule`, `AiRadarBudget`) was reported back to the executor. Recommended before the *next* redeploy (the one that restores `reserved_concurrent_executions=5`, see Task 6.5's note) — not confirmed empty yet.
- [x] Task 6.2: `uv run cdk deploy --app "python infra/app.py" AiRadarFeedApi`; capture `FeedApiUrl` (M2) — no file change — DONE (human-run) 2026-09-02/03: `cdk deploy AiRadarFeedApi -c feed_api_reserved_concurrency=none --require-approval never` → stack `AiRadarFeedApi` `CREATE_COMPLETE`, 11/11 resources, ~99s. Outputs captured: `FeedApiUrl = https://fdcksuokyh.execute-api.us-east-1.amazonaws.com`, `FeedApiFunctionName = ai-radar-feed-api`, `FeedApiLogGroupName = /aws/lambda/ai-radar-feed-api`, `FeedApiAllowedOrigins = http://localhost:3000`. **Deployed with the temporary `feed_api_reserved_concurrency=none` override active — `ReservedConcurrentExecutions` is currently absent from the live Lambda. This is the bridge state pending AWS Support case 178836416700301 (quota increase to 1001, still `CASE_OPENED`), NOT the final audited state (`reserved_concurrent_executions=5`).** See `specs/feed-api/audit.md`'s 2026-09-03 Audit Log entry.
- [x] Task 6.3: Live curl page 1 + cursor page 2 + tag filter; confirm real cards and disjoint pages (M3–M5) — record in `specs/feed-api/audit.md` — DONE, human-run 2026-09-02/03: `GET /v1/cards?limit=3` → 200, real curated cards from the live `ai-radar-cards` table (M3). **Cursor round trip (M4):** page 1 `?limit=2` → `[983102b3ea3b4340, bc6639b3f24621f6]` with a `next_cursor`; page 2 via that exact cursor (`?limit=2&cursor=...`) → `[ae0bb8510d8a9c3c, d0601037cbc8406a]` — four distinct `card_id`s across both pages, zero overlap, real disjoint pagination against the live table. **Tag filter (M5):** `GET /v1/cards?tag=security&limit=5` → 3 cards, and every one of them genuinely has `"security"` in its `tags` list (verified by parsing the real response body, not just trusting the count). M3, M4, M5 all now genuinely exercised.
- [x] Task 6.4: Live curl the 400 paths (`limit=0`, `limit=101`, `cursor=garbage`) and the CORS allowed/foreign-origin pair (M6, M7) — record in `specs/feed-api/audit.md` — DONE, human-run 2026-09-02/03: `?limit=0` → 400 `invalid_limit` (one transient local network timeout on the first attempt, unrelated to the API — clean retry succeeded in 0.3s); `?limit=101` → 400 `invalid_limit` (M6 now fully closed); `?cursor=not-a-real-cursor` → 400 `invalid_cursor`. CORS: `OPTIONS /v1/cards` preflight with `Origin: http://localhost:3000` (allowed) → 204 with `access-control-allow-origin: http://localhost:3000` present; `GET /v1/cards?limit=1` with `Origin: https://evil.example.com` (non-allowed) → response has **no** `access-control-*` header at all (M7 now fully closed — confirms CORS truly restricts to the configured origin list, not merely that it echoes an allowed one). M6, M7 both fully exercised.
- [x] Task 6.5: Record the AD-6 outcome — index-only `Query` sufficed, or the `grant_base_table_query` fallback was needed (M8); if the latter, redeploy and update `infra/lib/feed_api.py` + `tests/test_infra_feed_api.py` together — `specs/feed-api/audit.md` — DONE 2026-09-02/03: **AD-6 is resolved. Index-only `dynamodb:Query` (no base-table ARN) is sufficient** — the live `?limit=3` curl returned real cards with no `AccessDeniedException`; the `grant_base_table_query` fallback was never needed and `infra/lib/feed_api.py`/`tests/test_infra_feed_api.py` are unchanged. See `specs/feed-api/audit.md`.
- [!] Task 6.6: Add the "Phase 2 — Web Feed" README section: spec table row, deploy runbook, curl smoke test, cost-while-up note, teardown (RETAINed table survives; the ECR image asset does not auto-delete) — `README.md` — STILL OPEN/PARTIAL by explicit instruction: the deployed stack is in the temporary no-reservation bridge state (Task 6.2's note), not the fully-audited final state. A README runbook write-up should describe what is actually, durably true — deferred until the quota clears and the no-override redeploy restores `reserved_concurrent_executions=5`, so the runbook is written once, against the real final state, not twice.
- [!] Task 6.7: Update the "Current state" pointer (one sentence; the README table stays the source of truth) — `CLAUDE.md` — STILL OPEN/PARTIAL, same reason as Task 6.6 — deferred to the post-quota-clearance redeploy.
- [x] Task 6.8: Fill in `audit.md`'s Requirements/Contract/Test statuses and the Audit Log with any findings — `specs/feed-api/audit.md` — DONE for this pass 2026-09-03: R14 updated from DEFERRED to PASS (core live-deploy-and-curl goal met; M3/M6/M7/M8 evidence recorded, M1/M4/M5/M9/M10 still explicitly PENDING in the manual-verification table, not rounded up), AD-6 resolution recorded, new Audit Log entry added flagging the live Lambda's current no-reservation bridge state.

## Blocked Items

- ~~Phase 6 deploy/live-verify (Tasks 6.1-6.5, 6.8) was blocked pending a real deploy decision from the human.~~ **Unblocked 2026-09-02/03**: the human ran the real `cdk deploy AiRadarFeedApi -c feed_api_reserved_concurrency=none` and two real curl passes — see Tasks 6.2-6.5, 6.8 above and `specs/feed-api/audit.md`'s 2026-09-03 Audit Log entries. **M3-M8 (the entire core read-path contract) are now all genuinely exercised**, including the previously-open M4 (cursor round trip), M5 (tag filter), the `limit=101` half of M6, and the foreign-origin-CORS-absence half of M7. Genuinely still open: Task 6.1 (`cdk diff` on the other four stacks — not run/reported), M9 (cost/budget check), and M10 (teardown) — none of these block anything right now.
- **Tasks 6.6/6.7 (README/`CLAUDE.md` documentation) remain blocked by explicit instruction**, not by lack of AWS access: the currently-deployed Lambda runs WITHOUT its audited `reserved_concurrent_executions=5` (the `feed_api_reserved_concurrency=none` override is still active, pending AWS Support case 178836416700301). Writing the runbook now would document a temporary bridge state as if it were final. Deferred until the quota clears and a no-override `cdk deploy AiRadarFeedApi` restores the fully-audited state.
- ~~Task 3.6 (`Dockerfile.feed_api` real `docker build`) was blocked (no Docker daemon in the sandbox).~~ **Unblocked and completed 2026-09-02** once a Docker daemon became available — see Task 3.6 above and `specs/feed-api/audit.md`'s Audit Log (closes finding F2).

## Notes

- **Do not edit** `src/curation/**`, `src/shared/**`, `runtime_app.py`,
  `Dockerfile`, or the four existing `infra/lib` / `infra/stacks` pairs. If a
  task seems to require it, stop — that is a spec amendment, not an in-flight
  redesign.
- **`uv` only.** No `pip`, no `venv`, no `requirements.txt` committed to the
  repo. The one `requirements.txt` that exists is generated by `uv export`
  *inside* the image build and deleted in the same layer.
- **Verified facts to trust over intuition** (all re-probed 2026-08-30, see
  contract.md's pinned surface): a GSI `LastEvaluatedKey` has exactly
  `card_id`/`gsi_pk`/`gsi_sk`; `FilterExpression` runs *after* `Limit`, so
  short pages with a live cursor are normal; a hand-written
  `ProjectionExpression` coexists with a `boto3.dynamodb.conditions` filter;
  `relevance` arrives as `Decimal`; `HttpLambdaIntegration` defaults to payload
  format `2.0`; a `DockerImageFunction` synthesizes with **no Docker daemon**.
- **The response shape is frozen for Spec 02.** `{"cards": [...],
  "next_cursor": str | null}` — do not add `total`, `count`, `schema_version`,
  or debug fields to the 200 body. Diagnostics belong in the log record.
- **Skipped-card counts and timings go to logs, not the response body.**
- **If the live curl reveals the response is insufficient for the UI**, that is
  a `feed-api` revision (new spec version), not a workaround inside Spec 02.

## Completion

Phases 1-5 (green-phase implementation) completed 2026-09-01. `uv run pytest
tests/` was green at 344 passed, 0 failed (offline, no credentials/network/
Docker daemon); the sdd-auditor's 2026-09-01 pass added T32/T33 (closing
findings F1/F6), bringing the suite to 349 passed, 0 failed.

Task 3.6 (the one remaining blocked item, `docker build` of
`Dockerfile.feed_api`) was completed 2026-09-02 once a Docker daemon became
available — see Task 3.6 above and `specs/feed-api/audit.md`'s Audit Log
(closes finding F2). The local build surfaced and fixed a real gap
(`pydantic-settings` missing from the `api` dependency group); `uv run pytest
tests/` remains green at 349 passed, 0 failed after the fix.

Phase 6 (deploy, live-verify, README/CLAUDE.md documentation) remained
intentionally left for a separate, human-supervised session per roadmap.md's
own phasing and this executor's explicit offline-only scope — a local
`docker build` smoke check is not a deploy and did not change that.

**2026-09-02/03 update — the human ran the real deploy.** `cdk deploy
AiRadarFeedApi -c feed_api_reserved_concurrency=none --require-approval
never` succeeded (`CREATE_COMPLETE`, 11/11 resources, ~99s); a real curl pass
confirmed live cards from `ai-radar-cards`, both documented 400 error paths,
and CORS on the allowed origin. **This resolves AD-6**: index-only
`dynamodb:Query` IAM is sufficient — no `AccessDeniedException`, the
`grant_base_table_query` fallback was never needed. **2026-09-03 follow-up:**
the previously-open cursor-page-2 and tag-filter halves of the live-curl
matrix (M4, M5), `limit=101` (M6), and the foreign-origin CORS-absence check
(M7) were all subsequently exercised for real and confirmed correct — see
Tasks 6.3/6.4 above. The entire core read-path contract (M3-M8) is now
live-verified. Not everything in Phase 6 is done: the `cdk diff` on the
other four stacks (M1), a cost/budget check (M9), and teardown (M10) remain
unexercised — none block anything right now. Most importantly, unchanged —
**the deployed Lambda currently runs WITHOUT its audited
`reserved_concurrent_executions=5`** (the `feed_api_reserved_
concurrency=none` override from the AWS Lambda concurrency-quota workaround
is still active, pending AWS Support case 178836416700301). README/`CLAUDE.md`
documentation (Tasks 6.6/6.7) is deliberately deferred until a no-override
redeploy reaches the fully-audited final state. See `specs/feed-api/audit.md`'s
2026-09-03 Audit Log entry for full evidence.

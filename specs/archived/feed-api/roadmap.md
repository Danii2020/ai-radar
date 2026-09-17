# Roadmap: feed-api

Build order is bottom-up: the published contract first (everything else
depends on its shape), then the pure logic, then boto3/HTTP, then infra, then
tests and a real deploy. Nothing under `src/curation/`, `src/shared/`,
`runtime_app.py`, `Dockerfile`, or the four existing `infra/lib` + `infra/stacks`
pairs is edited at any point.

## Implementation Phases

### Phase 1: Published contract + config

**Goal**: `CardOut`/`FeedResponse` exist, are the single definition of the
response shape, and are exported as a checked-in JSON Schema artifact Spec 02
can generate from. API-plane config exists with the duplicated-but-drift-tested
GSI literals.
**Dependencies**: None (reads `specs/dynamodb-card-store/contract.md` +
`src/curation/dynamo.py` for field parity).
**Estimated complexity**: Low

1. `uv add --group api pydantic` — creates the `api` dependency group used by
   the Lambda image (AD-2); commit the regenerated `uv.lock`.
2. Create `src/contracts/__init__.py` + `src/contracts/card.py` with
   `CARD_SCHEMA_VERSION`, `CardOut`, `FeedResponse`, `json_schema()` — field
   names/types taken from the **actual** item written by
   `curation.dynamo.DynamoCardStore.upsert`, not from the design doc.
3. Create `src/api/__init__.py` + `src/api/config.py` (`_ApiSettings` +
   UPPERCASE public surface + fixed `FEED_GSI_NAME` / `FEED_GSI_PARTITION`).
4. Create `export_api_schema.py` (repo root) and run it to produce
   `docs/api/feed-api.v1.schema.json`; commit the artifact.
5. Append the `FEED_API_*` block to `.env.example`.

### Phase 2: Core logic — cursor + query

**Goal**: The two pieces that carry the hard guarantees — the opaque cursor
and the single GSI query — work and are independently testable without HTTP or
AWS.
**Dependencies**: Phase 1
**Estimated complexity**: Medium

1. `src/api/cursor.py`: `CURSOR_KEYS`, `InvalidCursorError`, `encode_cursor`,
   `decode_cursor` (re-pad → base64url-decode → JSON → validate key set, value
   types, and `gsi_pk == FEED_GSI_PARTITION`).
2. `src/api/dynamo.py`: lazy-singleton `boto3.resource("dynamodb")` +
   `card_table(client=None)`, mirroring `curation/dynamo.py`'s injectable
   client so `moto` can be passed in.
3. `src/api/feed.py`: `FeedPage` dataclass + `query_feed(...)` — one
   `Query` with the pinned `KeyConditionExpression`, `ProjectionExpression` +
   `ExpressionAttributeNames`, optional `FilterExpression`, optional
   `ExclusiveStartKey`, `ScanIndexForward=False`; per-item
   `CardOut.model_validate` inside try/except with a `skipped` counter.

### Phase 3: HTTP handler + Lambda image

**Goal**: A Lambda entrypoint that maps an API Gateway payload-2.0 event to a
`FeedResponse` (or a typed 4xx/5xx), and an image that actually contains it.
**Dependencies**: Phase 2
**Estimated complexity**: Medium

1. `src/api/handler.py`: parse `queryStringParameters` (absent → `{}`),
   validate `limit`/`cursor`/`tag` per the contract's parsing table, call
   `query_feed`, build the response body with `FeedResponse(...).model_dump_json()`,
   and return `{"statusCode", "headers", "body"}`. No CORS headers.
2. Structured logging: one `json.dumps({"event": "feed_api_request", …})`
   record per request (tag, limit, returned, skipped, has_next, duration_ms),
   same idiom as `runtime_app.py`'s `curation_run_complete`; exceptions via
   `logger.exception`.
3. `Dockerfile.feed_api` (repo root): AWS Lambda base image + `uv` copied in +
   `uv export --only-group api` → `uv pip install --target ${LAMBDA_TASK_ROOT}`
   + `COPY src/api/`, `src/contracts/` + `CMD ["api.handler.handler"]`.
4. Confirm `.dockerignore` needs no change (it already excludes `.env`,
   `.venv/`, `cdk.out/`, `tests/`, `infra/`, `docs/`) — if it does need one,
   the change must not break the AgentCore image's build context.

### Phase 4: Infrastructure (CDK)

**Goal**: `AiRadarFeedApi` synthesizes the log group, least-privilege role,
ARM64 image function, HTTP API with scoped CORS, the `GET /v1/cards` route,
and stage throttling — creating no DynamoDB table.
**Dependencies**: Phase 3 (the Dockerfile must exist for the asset path)
**Estimated complexity**: Medium

1. `infra/lib/feed_api.py`: module-level defaults (origins, throttle, memory,
   timeout, concurrency, retention, table/GSI literals) + the `FeedApi`
   construct exposing `.http_api`, `.function`, `.log_group`, `.role`,
   `.allowed_origins`.
2. `infra/stacks/feed_api_stack.py`: context-driven
   `feed_api_allowed_origins`, four `CfnOutput`s.
3. `infra/app.py`: one import + `FeedApiStack(app, "AiRadarFeedApi")`.
4. `uv run cdk synth --app "python infra/app.py" AiRadarFeedApi` locally to
   confirm the template shape before writing assertions.

### Phase 5: Tests & validation

**Goal**: Every Behavior Guarantee has a test; the suite stays offline,
credential-free, and Docker-free.
**Dependencies**: Phase 4
**Estimated complexity**: Medium

1. `tests/conftest.py` (MODIFY, additive): a `seed_cards` fixture that writes
   N deterministic items with known `gsi_sk` ordering and tags into the
   existing `dynamo_table` fixture — reused by the query and pagination tests.
2. `tests/test_feed_cursor.py`: encode/decode inverse, determinism, and every
   rejection path (bad base64, non-JSON, non-object, wrong key set, non-str
   value, foreign `gsi_pk`).
3. `tests/test_feed_query.py` (moto): ordering, tag filter, limit, short
   filtered page with a non-null cursor, the **multi-page round-trip
   equivalence** test (filtered and unfiltered), `embedding` never returned,
   `Decimal` → `int`, malformed-item skip.
4. `tests/test_feed_api_handler.py`: 200 body shape validated with
   `FeedResponse.model_validate_json`, 400 `invalid_limit` (each bad input),
   400 `invalid_cursor` with **no** AWS call (poisoned table double), 500 on a
   raising table, empty-tag-is-absent, no CORS headers emitted, log record
   emitted.
5. `tests/test_feed_api_contract.py`: schema-artifact drift, GSI literal drift
   vs `curation.config`, plane-separation AST import test, `boto3` confined to
   `src/api/dynamo.py`.
6. `tests/test_infra_feed_api.py` (synth-only): IAM statements by `Sid`, no
   `Resource: "*"`, no managed policies, no write actions, zero DynamoDB
   tables, CORS origins without `*`, route key `GET /v1/cards`,
   `PayloadFormatVersion 2.0`, arm64 + reserved concurrency + timeout,
   throttling settings, log-group retention, the four outputs.
7. `tests/test_feed_api_dockerfile.py`: functional assertions on
   `Dockerfile.feed_api` — no `pip install` of a `requirements.txt` from the
   repo, `uv` used, `--only-group api`, arm64 platform, `CMD` handler path,
   `src/curation`/`src/shared` not copied.
8. `uv run pytest tests/` green; confirm total count and that no test needs
   credentials, network, or Docker.

### Phase 6: Deploy, live-verify, document

**Goal**: A real URL returning real cards, with the runbook and README updated
the way every Phase 1 spec did.
**Dependencies**: Phase 5
**Estimated complexity**: Medium (external systems; container build)

1. `uv sync --group infra`; `uv run cdk diff --app "python infra/app.py"` on
   the four **existing** stacks to prove this change is additive (expect empty
   diffs), then `uv run cdk deploy --app "python infra/app.py" AiRadarFeedApi`.
2. Capture `FeedApiUrl`; `curl "$FEED_API_URL/v1/cards?limit=2"` →
   real cards. Then curl page 2 with the returned `next_cursor` and assert (by
   eye + `jq`) the `card_id`s are disjoint from page 1.
3. `curl "$FEED_API_URL/v1/cards?tag=<a real tag from page 1>"` → narrowed set;
   `?limit=0` and `?limit=101` → 400; `?cursor=garbage` → 400.
4. If the live query returns `AccessDeniedException`, apply the AD-6 fallback
   (`grant_base_table_query=True`), redeploy, re-curl, and **record the
   finding** in audit.md — that outcome is a real fact discovered by this
   spec, not a failure.
5. Verify CORS with `curl -H "Origin: http://localhost:3000" -i` (header
   present) vs `-H "Origin: https://evil.example"` (header absent).
6. README: a "Phase 2 — Web Feed" section with the spec table row, the deploy
   runbook, the curl smoke test, the "what it costs while up" note, and
   teardown (`cdk destroy AiRadarFeedApi`; note the RETAINed table survives and
   the ECR image asset does not auto-delete).
7. Update `CLAUDE.md`'s "Current state" pointer to the README table (one
   sentence; the table stays the source of truth).

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Index-only `dynamodb:Query` is insufficient → live `AccessDeniedException` | Med | Med | AD-6: a single `grant_base_table_query` flag, fallback written down, discovered by the runbook curl before Spec 02 depends on the API |
| `cdk deploy` fails because no container engine is running | Med | Low | Documented prerequisite in the runbook; Docker 28.3.3 is installed on the dev machine; synth/pytest are unaffected |
| `uv export --only-group api` behaves differently than expected inside the image (e.g. hashes, markers) | Low | Med | `--only-group` verified working on this repo (`--only-group dev` probe); Phase 3 builds the image locally once (`docker build -f Dockerfile.feed_api .`) before wiring CDK |
| Pydantic rejects a real stored item (e.g. a legacy card missing `takeaways`) | Med | Low | Optional fields default to `[]`; per-item skip (Guarantee 9) keeps the page alive; the live curl on real data is the actual test |
| Cursor tampering used to read another partition/index | Low | Med | `decode_cursor` validates the exact key set + `gsi_pk == "CARD"` before the value reaches DynamoDB (Guarantee 7) |
| Public unauthenticated endpoint abused → **compute** cost (Lambda, DynamoDB reads) | Low | Med | AD-7 throttling (20 rps / 40 burst) + `reserved_concurrent_executions=5` — rejected at the edge, so backend spend is hard-capped |
| Sustained flood → **API Gateway request-count** cost (429s are still billed requests) | Low | Low | **Accepted residual**, not closed by AD-7: $1.00/M means ~10⁷ requests ≈ $10. Detector is the deployed `AiRadarBudget` $50/$100/$250 SNS alerts; if that line ever becomes real, add a WAF rate-based rule then (AD-7 "Known limitation") |
| Response contract drifts from Spec 02's generated types | Med | High | The committed JSON Schema artifact + its drift test (Guarantee 13); Spec 02 generates from the file, not from prose |
| A short filtered page is misread as "end of feed" by Spec 02 | Med | Med | Guarantee 4 is explicit and tested; it is called out again in the Integration Points for Spec 02 |
| Concurrent curation write shifts `gsi_sk` mid-pagination | Low | Low | Documented, accepted limitation (contract.md's closing note); one write burst/day |
| Scope creep into a domain layer / extra endpoints | Low | Med | Non-Goals are explicit; `architecture-principles.md` triggers are not met and the spec says so |

## File Change Map

**Create — application**
- `src/contracts/__init__.py` — CREATE — new published-contract package
- `src/contracts/card.py` — CREATE — `CARD_SCHEMA_VERSION`, `CardOut`, `FeedResponse`, `json_schema()`
- `src/api/__init__.py` — CREATE — new Plane B serving package
- `src/api/config.py` — CREATE — `_ApiSettings` + `CARD_TABLE_NAME`/page-size bounds + fixed GSI literals
- `src/api/cursor.py` — CREATE — opaque cursor encode/decode + validation
- `src/api/dynamo.py` — CREATE — the only `boto3` site in `src/api/` (lazy singleton + injectable client)
- `src/api/feed.py` — CREATE — `FeedPage` + `query_feed` (one GSI query, projection, filter, per-item skip)
- `src/api/handler.py` — CREATE — Lambda entrypoint (payload format 2.0 in, JSON out)
- `export_api_schema.py` — CREATE — writes the JSON Schema artifact
- `Dockerfile.feed_api` — CREATE — ARM64 Lambda image built with `uv` from `uv.lock`

**Create — infra**
- `infra/lib/feed_api.py` — CREATE — `FeedApi` construct (log group, role, function, HTTP API, route, throttling)
- `infra/stacks/feed_api_stack.py` — CREATE — `FeedApiStack` + context origins + 4 outputs

**Create — tests + artifacts**
- `docs/api/feed-api.v1.schema.json` — CREATE — generated, committed contract artifact
- `tests/test_feed_cursor.py` — CREATE
- `tests/test_feed_query.py` — CREATE (moto)
- `tests/test_feed_api_handler.py` — CREATE
- `tests/test_feed_api_contract.py` — CREATE (schema drift, literal drift, plane separation)
- `tests/test_infra_feed_api.py` — CREATE (synth-only)
- `tests/test_feed_api_dockerfile.py` — CREATE

**Modify**
- `pyproject.toml` — MODIFY — append `[dependency-groups] api = ["pydantic>=2.13"]`
- `uv.lock` — MODIFY — regenerated by `uv add --group api`
- `infra/app.py` — MODIFY — one import + `FeedApiStack(app, "AiRadarFeedApi")`
- `tests/conftest.py` — MODIFY — additive `seed_cards` fixture only (existing fixtures untouched)
- `.env.example` — MODIFY — append the `FEED_API_*` block
- `README.md` — MODIFY — new "Phase 2 — Web Feed" section: spec table row, deploy/curl/teardown runbook
- `CLAUDE.md` — MODIFY — one-sentence "Current state" pointer update

**Explicitly NOT touched**
- `src/curation/**`, `src/shared/**`, `runtime_app.py`, `run_curation.py`,
  `run_chat.py`, `Dockerfile`, `infra/lib/{card_store,agent_runtime,curation_schedule,cost_budget}.py`,
  `infra/stacks/{card_store,agent_runtime,curation_schedule,cost_budget}_stack.py`

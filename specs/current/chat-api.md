# Chat API Specification

> Last synced: 2026-10-21. Owned artifacts: `src/chat_api/` (`handler.py`, `config.py`),
> `Dockerfile.chat_api`, `infra/lib/chat_api.py`, `infra/stacks/chat_api_stack.py` (stack
> `AiRadarChatApi`). Deployed 2026-10-21; live endpoint
> `https://<api-id>.execute-api.us-east-1.amazonaws.com/v1/chat`.

## Purpose

The public HTTP edge for the chat agent: one `POST /v1/chat` route on API Gateway, backed by a
Lambda that forwards a turn to the `ai_radar_chat` agent and maps the reply to a typed HTTP
response. It is its own capability, not a route on `feed-api`, so the feed contract stays
unchanged (ADR 0022). The agent's request and response contract belongs to `chat-agent` (CA-1
to CA-6). This capability relays that contract and adds no rules of its own, beyond a JSON-shape
check and a byte cap.

## Requirements

### Requirement: CAPI-1 — A valid turn returns the agent's answer and sources, and nothing else

The system SHALL answer a valid `POST /v1/chat` with 200 and exactly the keys `answer` and
`sources` from the agent's reply. It SHALL NOT add, rename or filter fields beyond those two keys,
and SHALL NOT add a request id.

**Source:** chat-api · intent.md § AC1; execution-plan.md § Binding constraints

#### Scenario: A grounded question
- **WHEN** a question with an absent `history` is posted to the live endpoint
- **THEN** the response is 200 with exactly the keys `answer` and `sources`, and the answer cites `[1]` to `[3]` from 4 sources (verified 2026-10-21)

#### Scenario: Extra keys from the agent
- **WHEN** the agent's reply carries a key beyond `answer` and `sources`
- **THEN** the response carries only `answer` and `sources`

### Requirement: CAPI-2 — Bad requests get a 400 with a fixed rule name, and local checks never invoke the agent

The system SHALL reject a body that is missing, longer than 524,288 UTF-8 bytes, not JSON, or not
a JSON object with 400 `{"error": "invalid_request", "detail": <rule>}`, where `<rule>` is one of
`body_missing`, `body_too_large`, `body_not_json` or `body_not_object`. It SHALL NOT invoke the
agent for those rules. An agent `invalid_request` SHALL be returned as 400 with the agent's body.
`detail` SHALL never echo the input.

**Source:** chat-api · intent.md § AC2; execution-plan.md § Proposed approach (local pre-checks)

#### Scenario: A body that is not JSON
- **WHEN** the body is `not json`
- **THEN** the response is 400 `body_not_json`, and the agent is not invoked (verified live 2026-10-21)

#### Scenario: An agent rule
- **WHEN** the body is `{"question": ""}`, which passes the local checks
- **THEN** the agent is invoked, answers `question_empty`, and the Lambda returns that body as 400 (verified live 2026-10-21)

### Requirement: CAPI-3 — Upstream failures are typed and leak no internals

The system SHALL map an agent `upstream_failure`, an invoke error, or an unreadable or unknown
reply to 502 `{"error": "upstream_failure"}`. It SHALL map a botocore read timeout to 504
`{"error": "upstream_timeout"}`. Exception text and stack traces SHALL go to the logs only. The
invoke client SHALL make no retries (`total_max_attempts: 1`), with a 3 s connect timeout and a
22 s read timeout, under the 28 s Lambda timeout.

**Source:** chat-api · intent.md § AC3; execution-plan.md § Proposed approach (client config and response mapping; Revision 2 correction)

#### Scenario: A turn slower than the read timeout
- **WHEN** the agent does not reply within 22 s
- **THEN** the response is 504 `upstream_timeout`, and the agent is invoked once (offline socket probe against the handler's real client config; the live case was not exercised, open finding F5)

#### Scenario: An unknown reply
- **WHEN** the agent replies with a body that is not JSON, or with an unknown `error` value
- **THEN** the response is 502 `upstream_failure`, with no internals in the body

### Requirement: CAPI-4 — One public route with an explicit CORS allowlist

The system SHALL route only `POST /v1/chat`, with no `$default` route, so any other path or method
returns 404 from API Gateway. CORS SHALL allow an explicit origin list (default
`http://localhost:3000`, never `*`), the `POST` method and the `content-type` header. The handler
SHALL emit no CORS headers, because API Gateway owns CORS.

**Source:** chat-api · intent.md § AC4; execution-plan.md § Binding constraints

#### Scenario: A preflight from an allowed origin
- **WHEN** `OPTIONS /v1/chat` arrives from `http://localhost:3000`
- **THEN** the response is 204 with `access-control-allow-origin: http://localhost:3000` (verified live 2026-10-21)

#### Scenario: A disallowed origin or another route
- **WHEN** the preflight comes from `https://evil.example`, or `GET /v1/chat` or `POST /v1/other` is sent
- **THEN** the preflight is 204 with no `access-control-*` header, and the other requests are 404 (verified live 2026-10-21)

### Requirement: CAPI-5 — The endpoint is throttled, and its Lambda concurrency is configurable

The `$default` stage SHALL set `ThrottlingRateLimit` to 5 and `ThrottlingBurstLimit` to 10, both
below `feed-api`'s limits. The Lambda timeout SHALL be 28 s, under API Gateway's integration limit.
The Lambda reserved concurrency SHALL default to 5, and SHALL be omitted with
`-c chat_api_reserved_concurrency=none`. Stage throttling is best-effort (open finding F13).

**Source:** chat-api · intent.md § AC5; execution-plan.md § Proposed approach (stage throttle; Lambda timeout)

#### Scenario: A steady rate above the stage limit
- **WHEN** requests arrive at about 20 req/s for about 4 s
- **THEN** some requests return 429 at the stage (16 of 80 in the live run; 64 passed, which is more lenient than nominal, F13)

#### Scenario: A parallel burst while the function is unreserved
- **WHEN** a 40-way parallel burst arrives while the function has no reserved concurrency
- **THEN** the response is 503 from Lambda rather than 429, because the account's 10-slot Lambda pool is exhausted (open finding F11; observed live 2026-10-21)

### Requirement: CAPI-6 — The Lambda role is least privilege

The Lambda role SHALL hold exactly two statements: `bedrock-agentcore:InvokeAgentRuntime` on the
`ai_radar_chat` runtime ARN and its `/runtime-endpoint/DEFAULT` sub-resource, and
`logs:CreateLogStream` and `logs:PutLogEvents` on its own log group. It SHALL have no `*` resource,
no managed policy, and no Bedrock model, DynamoDB or Secrets Manager permission.

**Source:** chat-api · intent.md § AC6; execution-plan.md § Binding constraints

#### Scenario: The synthesized role
- **WHEN** the stack is synthesized
- **THEN** the role has the two statements above and nothing else, and the live invoke succeeded without an `AccessDenied` (verified 2026-10-21)

### Requirement: CAPI-7 — Each request is stateless and writes one text-free log record

The system SHALL generate a fresh `uuid4` agent session id for each request, and SHALL store
nothing between requests. It SHALL write one `chat_api_request` record per request, carrying
`event`, `status`, `outcome`, `question_chars`, `history_items`, `duration_ms` and `session_id`. The
record SHALL NOT contain the question, the history, the answer or the caller's IP address. The record
SHALL be emitted at INFO whatever the root logger's level (ADR 0026). The stage SHALL have no access
logging.

**Source:** chat-api · intent.md § AC7; execution-plan.md § Proposed approach (session id; log record; handler-level logger)

#### Scenario: Two requests in a row
- **WHEN** two requests are sent
- **THEN** they carry two distinct session ids, and each produces one record with no `question` key (verified live 2026-10-21: 123 records, none containing text)

### Requirement: CAPI-8 — An unexpected error is a typed 500 whose log holds no message text

The system SHALL answer an unexpected exception raised before the invoke call with 500
`{"error": "internal_error"}`. It SHALL log the exception class name and the stack frames (file,
line, function) under `chat_api_request_failed`, and SHALL NOT log the exception message or source
lines (ADR 0025).

**Source:** chat-api · execution-plan.md § Proposed approach (one `chat_api_request` record per request; Revision 2 clarification)

#### Scenario: A planted exception
- **WHEN** a `RuntimeError` whose message carries a planted question is raised before the invoke call
- **THEN** the response is 500 `internal_error`, exactly one record is logged, and the planted text appears in no rendered log record and no response (offline test)

## Invariants

1. The handler imports no other first-party package (`curation`, `api`, `chat`, `shared`,
   `contracts`). The request rules stay in the agent, and the byte cap is duplicated on purpose. An
   AST test guards this.
2. The handler emits no CORS headers, because API Gateway owns CORS. A test guards this.
3. The stage has no access logging, so no caller IP is recorded (CAPI-7).
4. The pinned account `626259825216`, region `us-east-1` and runtime id `ai_radar_chat-JFCO0R9lkT`
   are literals in `infra/lib/chat_api.py`, each with a test. This matches the `feed_api.py` and
   `chat_runtime.py` convention.

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| CAPI-F5 | Runbook step 10, the agent-side invocation count for one slow request, is not run. The live 502 and 504 paths were not triggered, so the no-retry property rests on the offline socket probe. | LOW | `specs/archived/chat-api/audit.md` (F5) |
| CAPI-F7 | CI has not run on the branch, because it is unpushed. The evidence is local. | LOW | `specs/archived/chat-api/audit.md` (F7) |
| CAPI-F8 | The `.gitignore` edit (`.env*`, `!.env.example`) and the `pyproject.toml` `botocore.*` mypy override are changes outside the plan's ownership. They await the human's confirmation. | LOW | `specs/archived/chat-api/audit.md` (F8) |
| CAPI-F11 | The function is unreserved (`chat_api_reserved_concurrency=none`), so it shares the account's 10-slot Lambda pool with `ai-radar-feed-api`. A parallel burst returns 503s. Quota increase 10 to 1000 requested 2026-10-21 (`cf8be0f0ceba4cf787e8e329efd718e0i3872UpR`, status `CASE_OPENED`, support case `179259663100438`). Closure: redeploy `AiRadarChatApi` and `AiRadarFeedApi` without the `none` flag, then a burst shows only 400 and 429 and zero Lambda throttles. | MEDIUM | `specs/archived/chat-api/audit.md` (F11) |
| CAPI-F13 | Stage throttling is best-effort and lenient: 64 of 80 requests passed at about 20 req/s, where a strict 5 rps and burst 10 bucket would pass about 30. The real ceiling under abuse is about twice nominal. The `AiRadarBudget` alert is the backstop. | LOW | `specs/archived/chat-api/audit.md` (F13) |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| chat-api | 2026-10-21 | CAPI-1..CAPI-8: the `POST /v1/chat` edge, its local pre-checks and typed errors, one public route and CORS allowlist, stage throttling and configurable concurrency, the least-privilege role, the stateless text-free log record and the typed 500 path. Deployed as `AiRadarChatApi`. |

## Related ADRs

| ADR | Title | Status |
|---|---|---|
| [0022](../archived/chat-api/decisions/0022-chat-is-a-separate-http-api-not-a-feed-api-route.md) | Chat is exposed as its own HTTP API, not as a route on the feed API | Accepted |
| [0023](../archived/chat-api/decisions/0023-one-fresh-agent-session-id-per-request.md) | Each chat request gets a fresh agent session id, so the Lambda holds no state | Accepted |
| [0024](../archived/chat-api/decisions/0024-no-retries-and-a-read-timeout-under-the-lambda-limit.md) | The agent invoke makes no retries, with a 22 s read timeout under a 28 s Lambda limit | Accepted |
| [0025](../archived/chat-api/decisions/0025-500-path-logs-exception-class-and-frames-only.md) | Unexpected errors log the exception class and stack frames, never the message | Accepted |
| [0026](../archived/chat-api/decisions/0026-handler-sets-its-own-info-log-level.md) | The handler sets its own logger to INFO rather than relying on the runtime's log level | Accepted |
| [0027](../archived/chat-api/decisions/0027-throttling-is-the-only-abuse-guard-on-the-unauthenticated-endpoint.md) | The unauthenticated chat endpoint is guarded by throttling and the budget alert alone | Accepted |

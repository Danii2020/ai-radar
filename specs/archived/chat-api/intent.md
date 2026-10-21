# Intent: Chat API

Shipped: 2026-10-21

Revision: 1
Approval: Approved revision 1 by Daniel Erazo on 2026-10-19

## Outcome
The deployed `ai_radar_chat` agent gets a public HTTPS front door. A browser
(or any HTTP client on an allowed origin) sends `POST /v1/chat` with a question
and the earlier turns, and gets back the agent's grounded answer and its
numbered sources as JSON. The endpoint is throttled, because every call spends
Sonnet tokens against the $500 budget, and it adds no authentication. The
response is one complete JSON body: streaming is not part of this spec, and the
web chat UI (later spec, `apps/web/`) will only animate the finished answer.

## Acceptance criteria
- **AC1** A valid turn returns the agent's answer. `POST /v1/chat` with JSON
  `{"question": str, "history": [...]}` (`history` optional, default `[]`)
  returns 200 with exactly the agent's `{"answer": str, "sources": [...]}`,
  unchanged from `chat-agent` CA-1: the same source fields, no extra keys, no
  request id.
  Example: `{"question": "What shipped in open-weight coding models?"}` ->
  200 `{"answer": "... [1] ...", "sources": [{"n": 1, "title": ..., "url": ...,
  "source": ..., "published": ..., "score": ...}]}`.
- **AC2** Bad requests are rejected as 400 with a fixed rule name. If the agent
  returns `{"error": "invalid_request", "detail": <rule>}` (CA-3), the API
  returns 400 with the same body. If the body is not valid JSON, is not a JSON
  object, or exceeds a fixed byte cap, the API returns 400 `{"error":
  "invalid_request", "detail": "<rule>"}` itself and does not invoke the agent.
  `detail` is never an echo of the input.
  Example: body `not json` -> 400 `invalid_request`, zero agent invocations.
  Example: `{"question": ""}` -> 400 `invalid_request` / `question_empty`.
- **AC3** Upstream failures are typed and never leak internals. If the agent
  returns `{"error": "upstream_failure"}` or the agent invocation itself fails
  (AWS error, unreadable reply), the API returns 502 `{"error":
  "upstream_failure"}`. If the invocation exceeds the API's time budget, it
  returns 504 `{"error": "upstream_timeout"}`. The exception and stack trace
  go to the logs, never to the caller.
  Example: the invoke call raises -> 502 `upstream_failure`, and the next
  valid request succeeds.
- **AC4** The public surface is one route with an explicit CORS allowlist. Only
  `POST /v1/chat` is routed, and any other path or method returns 404 from API
  Gateway. CORS allows an explicit origin list (never `*`), the `POST` method
  and the `content-type` header, and a preflight from an allowed origin
  succeeds.
  Example: `OPTIONS /v1/chat` from `http://localhost:3000` -> 204 with the
  matching `access-control-allow-origin`. `GET /v1/chat` -> 404.
- **AC5** The endpoint is throttled. The API Gateway stage limits the steady
  rate and burst to values lower than `feed-api`'s (the call is far costlier),
  and the Lambda concurrency cap is configurable the same way as `feed-api`'s,
  so the account's current quota of 10 can still deploy it.
  Example: a sustained request rate above the stage limit -> API Gateway
  answers 429 without invoking the Lambda or the agent.
- **AC6** The Lambda's IAM role is least privilege. It can invoke only the
  `ai_radar_chat` runtime and write only its own log group. It has no Bedrock
  model access, no DynamoDB access, no Secrets Manager access, no wildcard
  resource and no AWS managed policy.
  Example: the synthesized role contains one `InvokeAgentRuntime` statement
  scoped to the chat runtime's ARN, plus log-write on its log group.
- **AC7** The API is stateless and text-free in its logs. Each request gets a
  fresh agent session identifier, nothing is stored between requests, and the
  conversation exists only in the request body. Each request writes one
  `chat_api_request` structured log record with the HTTP status, outcome,
  question and history sizes, and latency. The record contains neither the
  question, the history, the answer nor the caller's IP address.
  Example: two requests in a row -> two distinct session identifiers, two
  records, no `question` key in either.
- **AC8** (compatibility) The agent contract and everything already deployed
  keep working unchanged. `chat_app.py`, `src/chat/`, `src/shared/`, the
  `AiRadarChatRuntime` role, `AiRadarFeedApi` and the other stacks are not
  modified, and `uv run pytest tests/` stays green.
- **AC9** (live verification, human-run) After deploy, the real URL answers a
  grounded question with sources, returns 400 for a bad body, answers a
  preflight from the allowed origin, and the log record shows no text. The
  runbook and its recorded results are part of the deliverable, as in
  `chat-agent-runtime`.

## Scope
**In**
- A new `src/chat_api/` Lambda handler, `Dockerfile.chat_api`, and a new
  dependency group for the image (same `--only-group` pattern as `feed-api`).
- A new CDK construct `infra/lib/chat_api.py` and stack
  `infra/stacks/chat_api_stack.py` (`AiRadarChatApi`), registered in
  `infra/app.py`, with CDK context overrides for allowed origins and reserved
  concurrency, mirroring `feed-api`.
- Unit and synth tests, and a README runbook section.

**Out**
- Streaming of any kind (SSE, Lambda response streaming, WebSocket). The web UI
  will animate the finished answer client-side.
- The web chat UI, and the CORS origin of a deployed frontend (Vercel is not
  deployed; the default origin stays `http://localhost:3000`).
- Authentication, API keys, per-user quotas and WAF.
- Any change to the agent, retrieval, or the `{question, history}` contract.
- A published JSON schema or generated types for the chat contract. Add them
  with the UI spec if the frontend needs them.

## Constraints
- The architecture follows `docs/architecture-principles.md`. The handler is
  its own plane-B edge and imports neither `curation` nor `api`. It also does
  not import `chat`, so it duplicates the byte cap rather than coupling to the
  agent's internals.
- The agent's validation (CA-3) stays the single source of the request rules.
  The Lambda does only the checks needed to avoid wasting an invocation (JSON
  shape, byte cap).
- The pinned account `626259825216` and region `us-east-1` follow the existing
  literal-in-code convention (`feed_api.py`, `chat_runtime.py`), with their
  tests.
- This account's Lambda concurrency quota is 10, so the stack must deploy with
  `-c chat_api_reserved_concurrency=none`, as `AiRadarFeedApi` does.
- API Gateway HTTP API caps an integration at about 30 seconds, so the Lambda
  and the invoke call need a shorter budget than that.
- The image must bundle a `boto3` new enough to have the `bedrock-agentcore`
  client, because the Lambda base image's built-in version may not. This is
  verified against current docs when the execution plan pins the call.
- Nothing here may widen the existing roles, and the Lambda must not be given
  the chat agent's Bedrock/DynamoDB permissions.

## Open questions
- None. At approval the human accepted the proposed defaults: a stage limit of
  5 requests per second with a burst of 10, a separate 504 `upstream_timeout`,
  and a request-size cap set in the execution plan. A separate API (not a route
  on `AiRadarFeedApi`) was confirmed, so `feed-api` stays untouched.

## Revision history
- Revision 1 (2026-10-19): initial draft.

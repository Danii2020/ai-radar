# src/chat_api — Plane B public edge (Lambda)

Purpose: the Lambda behind `POST /v1/chat` (API Gateway HTTP API). It forwards the request
body to the deployed `ai_radar_chat` AgentCore runtime with a fresh session id per request
and maps the reply to a typed HTTP response. It adds no authentication; the stage throttle
(5 rps, burst 10) is the cost guard. Root guidance: [`CLAUDE.md`](../../CLAUDE.md).

## Key files

- `handler.py` — `handler(event, context)`. Pre-checks the body (`body_missing`,
  `body_not_json`, `body_not_object`, `body_too_large` at 524,288 bytes) without invoking the
  agent. Calls `invoke_agent_runtime` (qualifier `DEFAULT`, `uuid4` session id, payload
  forwarded unchanged). Maps the reply: agent `invalid_request` -> 400, `{answer, sources}` ->
  200 with only those keys, `ReadTimeoutError` -> 504 `upstream_timeout`, anything else ->
  502 `upstream_failure`. Writes one text-free `chat_api_request` log record per request. The
  client is built once per container (connect 3 s, read 22 s, `total_max_attempts: 1` = no retries; the 500 path logs exception class and frames only).
- `config.py` — `CHAT_RUNTIME_ARN` (pydantic-settings, required: a missing value fails at
  import) plus the fixed byte cap and timeouts.

## Commands

```bash
uv run pytest tests/test_chat_api_handler.py tests/test_chat_api_dockerfile.py
uv run pytest tests/test_infra_chat_api.py    # CDK synth, no Docker daemon or credentials
```

## Conventions

- This package imports no other first-party package (`curation`, `api`, `chat`, `shared`,
  `contracts`). The request rules stay in the agent; the byte cap is duplicated here on purpose.
- No CORS headers are emitted: API Gateway owns CORS.
- Logs never contain the question, history, answer or caller IP, only sizes, status, outcome,
  latency and the generated session id.
- The image installs only the `chat_api` dependency group (`Dockerfile.chat_api`), which
  bundles `boto3` because the Lambda base image's copy may lack the `bedrock-agentcore` client.
- Deploy with `-c chat_api_reserved_concurrency=none` while the account Lambda quota is 10.

# Audit: Chat API

Round 3, 2026-10-21. Same branch and base, still uncommitted, reviewed against `execution-plan.md`
Revision 2. What changed since round 2: the F9/F10 fixes, the human-run O9 live verification
(account `626259825216`, 2026-10-21), the new finding F11 in `tasks.md`, and the corrected README
deploy command. I diffed every chat-api source, infra, Dockerfile and test file against the round-2
scratch snapshot (`.../scratchpad/mut2`). The only differences are in `src/chat_api/config.py`
(the dead `LAMBDA_TIMEOUT_SECONDS` was removed and a comment reworded) and a comment in
`infra/lib/chat_api.py`. `handler.py`, the stack, the Dockerfile and all three test files are
byte-identical to round 2 (rerun diff). So no test changed after the round-2 audit.
I corroborated the live evidence with read-only AWS calls and zero-spend curls only. I did not
send a valid-question POST and did not burst the endpoint.

Round 2, 2026-10-20. Same branch and base, still uncommitted, reviewed against `execution-plan.md`
Revision 2 (approved 2026-10-20). Re-read in full: `src/chat_api/{config,handler}.py`,
`src/chat_api/AGENTS.md`, `infra/lib/chat_api.py`, `infra/stacks/chat_api_stack.py`,
`Dockerfile.chat_api`, `tests/test_chat_api_handler.py` (now 43 tests), the `README.md` diff and
`tasks.md`. Test immutability: `tests/test_infra_chat_api.py` and `tests/test_chat_api_dockerfile.py`
still have their 2026-10-19 mtimes and are byte-identical to the scratch copy. In
`tests/test_chat_api_handler.py`, all 34 round-1 tests are still present by name with the same
assertions (rerun read). The only change to an original test is the human-approved retries test:
`read_timeout == 22` and `retries == {"total_max_attempts": 1}`. The 9 added tests are the
Revision 2 row (34 + 9 = 43; 536 + 9 = 545).

Round 1, 2026-10-20. Branch `feat/chat-api`, base `ce5df0b`, uncommitted working tree.
Reviewed: `src/chat_api/{__init__,config,handler}.py`, `src/chat_api/AGENTS.md`,
`Dockerfile.chat_api`, `infra/lib/chat_api.py`, `infra/stacks/chat_api_stack.py`,
`infra/app.py`, `pyproject.toml`, `uv.lock`, `.gitignore`, and the red tests
`tests/test_chat_api_handler.py` (34 tests), `tests/test_infra_chat_api.py` (11),
`tests/test_chat_api_dockerfile.py` (4).

Test immutability: the three test files are untracked, so there is no git diff for them. Their
mtimes (21:56:18, 21:57:16, 21:58:07 on 2026-10-19) are all earlier than every implementation
file (22:00:42 to 22:01:31), and the per-file counts (34 / 11 / 4 = 49) match the red-phase
counts in `tasks.md` O1-O3. No sign of executor edits (reused, from mtime and count evidence).

## AC results

### Round 3 (current)
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | Offline: the code is unchanged and 545 passed (rerun). Live: a grounded question returned 200 with keys exactly `answer` and `sources`, and a follow-up also returned 200 (reused, O9 step 4; I did not repeat it, to avoid Sonnet spend). CloudWatch holds two `status: 200, outcome: ok` records (rerun read), and the in-image import printed `ok 1.43.56` (reused, O9 step 3) |
| AC2 | PASS | Live, rerun: `not json` gave `400 {"error": "invalid_request", "detail": "body_not_json"}` and `[1]` gave `400 body_not_object`, with no echo of the input. Agent passthrough `question_empty` gave 400 (reused, O9 step 5; its 591 ms `invalid_request` record is in CloudWatch, rerun read) |
| AC3 | PASS (offline + design); live slow-turn not exercised | Unchanged since round 2: the socket probe on the real `Config` showed 1 hit and a 504 (reused, still current because `handler.py` is byte-identical). The live 502/504 paths were not triggered, and step 10 was not run (see F5) |
| AC4 | PASS | Live, rerun: `get-routes` shows only `POST /v1/chat` (`NONE`). CORS config is origin `http://localhost:3000`, method `POST`, header `content-type`, max-age 3600. Preflight from the allowed origin gave 204 with all three `access-control-allow-*` headers. Preflight from `https://evil.example` gave 204 with no `access-control-*` header. `GET /v1/chat` and `POST /v1/other` both gave 404 |
| AC5 | PASS, with reservations F11/F13 | The as-built configuration matches the spec, live and rerun: the stage `$default` has `ThrottlingRateLimit 5.0` and `ThrottlingBurstLimit 10`. The function has no reserved concurrency (`get-function-concurrency` is empty), as the `none` override and intent Constraints require. Timeout is 28 s. The 429 behavior was observed (16 × 429 of 80 at ~20 req/s; reused, O9 step 8). Enforcement is more lenient than nominal (64 requests passed where a strict token bucket would pass about 30), and a 40-way cold burst got Lambda 503s rather than 429s (CloudWatch rerun: `Throttles` 27, `ConcurrentExecutions` max 10, `Invocations` 123). Neither contradicts AC5, which asks for a stage limit below feed-api's and a configurable concurrency cap. See F11 and F13 |
| AC6 | PASS | Synth tests are unchanged and green (rerun). Live: the turns succeeded, so the two-ARN grant is sufficient and there was no `AccessDenied` (reused). `cdk diff` before the deploy showed only the AC6 IAM statements (reused, O9) |
| AC7 | PASS | F2 is confirmed live (rerun read). 123 `chat_api_request` records sit in `/aws/lambda/ai-radar-chat-api` at the default Text/no-level config (`LoggingConfig: {LogFormat: Text}`). Their key set across all records is exactly `duration_ms, event, history_items, outcome, question_chars, session_id, status`. There are no `Traceback`, `ERROR` or `answer` events. The session ids are distinct uuid4 values. No access logging on the stage (`AccessLogSettings: null`) |
| AC8 | PASS | `git diff --stat main` over the protected paths (including `tests/`, `infra/stacks/`, `src/contracts`, `src/curation`) is empty. `uv run pytest tests/ -q` gives **545 passed** (rerun). Ruff, `ruff --isolated` and mypy (95 files) are clean (rerun) |
| AC9 | PASS, with reservations F5 (step 10) and F12 (README not updated) | Every element AC9 names is verified live. The real URL answers a grounded question with sources and returns 400 for a bad body (reused + rerun). It answers the allowed-origin preflight (rerun), and the log record shows no text (rerun). The account, stack (`CREATE_COMPLETE` 2026-10-21T15:12Z), outputs, function config and env were all re-read (rerun). The results are recorded in `tasks.md` O9. The plan's extra runbook step 10 (from Risks) is not run, and the README runbook still says NOT YET RUN and "not deployed" (F12) |

### Round 2 (superseded)
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | Unchanged since round 1. 43/43 handler tests green (rerun) |
| AC2 | PASS | Unchanged. Mutation R7 (byte cap removed) is killed by 2 tests (rerun) |
| AC3 | PASS | F1 is closed. **Socket probe against the handler's actual client** (built by `handler._agentcore()` with its own `Config` unmodified and only `endpoint_url` added; the server sleeps 30 s): `connect 3, read 22, retries {'total_max_attempts': 1, 'mode': 'legacy'}`, **hits=1**, elapsed 22.07 s, response `504 {"error": "upstream_timeout"}` (rerun). Connect 3 + read 22 = 25 s, leaving 3 s of the 28 s Lambda timeout. Mutations R1 (`max_attempts: 1`), R8 (504 mapping dropped) and R9 (read timeout 25) are all killed (rerun) |
| AC4 | PASS | Synth unchanged: 11/11 infra tests, and the file is byte-identical to round 1 (rerun). Live 404/204 belongs to AC9 |
| AC5 | PASS | Throttle 5/10, reserved concurrency 5 with the `none` override, 28 s timeout. The construct changed only in comments (rerun). R10 (timeout 30) is killed. Live 429 belongs to AC9 |
| AC6 | PASS | IAM is unchanged: 2 statements, no `*`, no managed policy. R6 (`*` added) is killed by 2 tests (rerun) |
| AC7 | PASS (offline); live part in AC9 | F2 is closed offline. **Plain interpreter check (`python -I`, no pytest/caplog)**: the root logger is set to WARNING with one handler and no handler level, exactly as `awslambdaric/bootstrap.py` `_setup_logging` does when no log level is configured (re-read). Running the real handler wrote the `[INFO] {"event": "chat_api_request", ...}` record to the handler, 2 records for 2 requests (rerun). R2 (`setLevel` removed) is killed by `test_request_record_survives_root_logger_at_warning_log_level`. The 500 path, in the same interpreter with `RuntimeError("SECRET-MSG " + body)`: the rendered output holds `exception_class: RuntimeError` and `file:line in func` frames only, with no message and no body text (`secret in output: False`, rerun). R3 (`logger.exception` restored) and R3b (message added) are both killed. The CloudWatch confirmation is AC9 step 9 |
| AC8 | PASS | `git diff --stat main -- chat_app.py src/chat src/shared src/api src/contracts src/curation infra/lib/{feed_api,chat_runtime,agent_runtime}.py infra/stacks/ tests/` is empty. `uv run pytest tests/ -q` gives **545 passed** (rerun). The focused regression command gives 27 passed (rerun) |
| AC9 | N/A: open, human-gated, not verified | O9 has not run: no deploy, curl, preflight, 404, 429, CloudWatch read or real image build (unavailable). The runbook now exists (see F4/F9). This is reported as unverified, not as a defect in the offline delivery |

### Round 1 (superseded)
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `_map_reply` returns only `{"answer", "sources"}` when `answer` is a str and `sources` is a list. The payload goes out as the raw request bytes, with `qualifier="DEFAULT"` and a uuid4 session id. Tests green, and mutation M5 (pass the reply through) is killed (rerun) |
| AC2 | PASS | Local checks `body_missing`, `body_too_large` (UTF-8 bytes, 524,288 limit), `body_not_json` and `body_not_object` all run before any invoke. Agent `invalid_request` is passed through as 400. Mutations M1 (no cap), M2 (`>=`) and M3 (count characters) are all killed (rerun) |
| AC3 | FAIL | Offline mapping is correct: a `ReadTimeoutError` raised by the stub becomes 504, and any other exception becomes 502 with no internals (M4 and M9 killed, rerun). But the client config `retries={"max_attempts": 1}` allows **one retry**, i.e. 2 attempts, and botocore retries a read timeout. A local socket probe showed `hits=2` with the handler's config and `hits=1` with `total_max_attempts: 1` (rerun). In Lambda, a 25 s read timeout is retried, the 28 s function timeout kills the call, and the caller never gets the typed 504 `upstream_timeout`. This is F1 |
| AC4 | PASS | Synth shows a single route `POST /v1/chat` (`AuthorizationType NONE`) and no `$default` route. CORS: origins `["http://localhost:3000"]`, methods `["POST"]`, headers `["content-type"]`, max-age 3600, and the context override works. M14 (`*` origin) and M16 (extra GET) are killed. The live 404 and 204 checks are AC9 (rerun synth; live unavailable) |
| AC5 | PASS | The `$default` stage has `ThrottlingRateLimit 5` and `ThrottlingBurstLimit 10`, below feed-api's 20/40. `ReservedConcurrentExecutions` is 5 by default and absent with `chat_api_reserved_concurrency=none`. Timeout is 28 s. M13 and M15 killed. The live 429 check is AC9 (rerun synth; live unavailable) |
| AC6 | PASS | Synthesized policy, inspected directly: exactly 2 statements. One is `bedrock-agentcore:InvokeAgentRuntime` on `arn:aws:bedrock-agentcore:us-east-1:626259825216:runtime/ai_radar_chat-JFCO0R9lkT` and on its `/runtime-endpoint/DEFAULT`. The other is `logs:CreateLogStream` and `logs:PutLogEvents` on `<own log group arn>:*`. No `*` resource, no managed policy, no bedrock/dynamodb/secretsmanager action. M10, M11 and M12 killed (rerun) |
| AC7 | PARTIAL | Offline: a fresh uuid4 per request, exactly one `chat_api_request` record per request with the required keys, and planted question, history, answer and IP text absent from every record and stack trace (M7 and M8 killed, rerun). In Lambda, the record is emitted with `logger.info`, but the module never sets a level and the construct sets no `ApplicationLogLevel` (text format). The Lambda Python runtime bootstrap (`awslambdaric/bootstrap.py` `_setup_logging`) only calls `setLevel` when a log level is configured, so the root logger stays at WARNING and the record is dropped. This is from reading the runtime source; it was not observed live. This is F2 |
| AC8 | PASS | `git diff --stat main` over `chat_app.py src/chat src/shared src/api src/contracts src/curation infra/lib/{feed_api,chat_runtime,agent_runtime}.py infra/stacks/` is empty. `uv run pytest tests/ -q` gives 536 passed (487 baseline + 49 new). No test hard-codes a stack count (rerun) |
| AC9 | N/A (open, not verified) | Human-gated O9 has not run: no deploy, no curl checks, no cold/warm latency, and no real `docker build -f Dockerfile.chat_api .` with an in-container import. The README runbook (O8) is not written (unavailable) |

## Binding-constraint compliance

### Round 3 (current)
Every round-2 PASS still holds. The code is byte-identical except `config.py` and a comment (rerun diff), and `pyproject.toml`, `uv.lock` and `Dockerfile.chat_api` are unchanged. These constraints now have live evidence (rerun unless marked):
| Constraint | Status | Evidence |
|---|---|---|
| Pinned account, region and runtime id | PASS | Live `CHAT_RUNTIME_ARN` is `arn:aws:bedrock-agentcore:us-east-1:626259825216:runtime/ai_radar_chat-JFCO0R9lkT` |
| Deploy with `-c chat_api_reserved_concurrency=none` | PASS | No function concurrency is configured live. The consequence is F11 |
| Lambda and invoke timeouts under ~30 s | PASS | Live `Timeout: 28` |
| Access logging off | PASS | Live `AccessLogSettings: null` |
| Handler emits no CORS headers | PASS | The live 400 response carries no `access-control-*` header |
| Image installs `--only-group chat_api` with a working boto3 | PASS | The in-container import was run (reused, O9 step 3) |
| Protected files unmodified | PASS | Empty diff (rerun) |

### Round 2 (superseded)
| Constraint | Status | Evidence |
|---|---|---|
| Handler imports no other first-party package | PASS | Imports are now stdlib (including `traceback`), boto3, botocore, pydantic, pydantic_settings and `chat_api.config`. Now guarded: R5 (`from shared import config` in handler) and R5b (`import contracts` in config) are killed by the AST test (rerun) |
| Reply forwarded as `{"answer","sources"}` only | PASS | Unchanged |
| Handler emits no CORS headers | PASS | Now guarded: R4 (`Access-Control-Allow-Origin` added) is killed by 5 tests (rerun) |
| Pinned literals with tests | PASS | Unchanged |
| Deploy with `-c chat_api_reserved_concurrency=none` | PASS | Synth unchanged, and the README runbook step 2 shows the flag |
| Lambda and invoke timeouts under ~30 s | PASS | 28 s Lambda, 3 + 22 s invoke, with 3 s headroom. Guarded by the headroom test and the 28 s synth test |
| No retries (`total_max_attempts: 1`, Revision 2) | PASS | Probe hits=1 (above). R1 is killed. R1b (`max_attempts: 0`, behaviorally equivalent) is also killed, because the test pins the plan's chosen key. That is acceptable, since the plan rejects `max_attempts` explicitly |
| Handler logger at INFO (Revision 2) | PASS | `logger.setLevel(logging.INFO)` at module level. Proven outside pytest (above) |
| 500 path logs class + frames, never the message (Revision 2) | PASS | `logger.error` with `exception_class` and `_frames()` (`traceback.extract_tb`, file:line:name only), no `exc_info`. Proven rendered (above) |
| IAM exact; no `*`, no managed policy | PASS | Unchanged (synth tests, R6) |
| Access logging off | PASS | Unchanged |
| Protected files unmodified | PASS | Empty diff (rerun) |
| `uv` only; `--only-group chat_api` | PASS | `pyproject.toml` and `uv.lock` are unchanged since round 1 (diff), and the Dockerfile is byte-identical |
| Dependencies: only boto3 and pydantic-settings | PASS | Unchanged |
| Consumers and migration | PASS | Unchanged. The README runbook now exists |

### Round 1 (superseded)
| Constraint | Status | Evidence |
|---|---|---|
| Handler imports no other first-party package | PASS | The only imports are stdlib, `boto3`, `botocore`, `pydantic`, `pydantic_settings` and `chat_api.config` (rerun grep). **No test guards this**: mutation M20 (`import shared.cards` in the handler) survives all 49 tests (F3) |
| Reply forwarded as `{"answer","sources"}` only | PASS | `_map_reply`, M5 killed |
| Handler emits no CORS headers | PASS | `_response` emits only `content-type`. **No test guards this**: M17 (add `access-control-allow-origin: *`) survives (F3) |
| Pinned account, region and runtime id literals with tests | PASS | `infra/lib/chat_api.py` defaults, `tests/test_infra_chat_api.py` constants |
| Deploy with `-c chat_api_reserved_concurrency=none` | PASS (offline) | The stack parses `none` and the property is omitted (synth rerun). The runbook that shows the flag is missing (F4) |
| Lambda timeout and invoke read timeout under ~30 s | PASS, with a margin note | 28 s Lambda, 25 s read and 3 s connect. Connect plus read equals the Lambda timeout exactly (F6) |
| Proposed approach: no retries ("a retry would double the Sonnet spend") | FAIL | `max_attempts: 1` means 1 retry, per the botocore `Config` docstring and the socket probe (F1). The plan text itself specifies this value, so the defect came from the plan and the test pins it |
| IAM exactly invoke on runtime ARNs and log write; no `*`, no managed policy | PASS | Synth inspected (above) |
| API Gateway access logging off | PASS | No `AccessLogSettings` on the stage (synth) |
| Protected files unmodified | PASS | Empty diff (above) |
| `uv` only; image installs `--only-group chat_api` | PASS | The group is stored as `chat-api`, and `uv export --frozen --no-emit-project --only-group chat_api` (uv 0.7.17, the same version the Dockerfile pins) resolves it to boto3==1.43.56, botocore==1.43.56, pydantic-settings==2.14.2 and their transitive dependencies. `uv lock --check` is current. The lock diff adds only the group metadata, no new packages. `boto3.client("bedrock-agentcore")` builds and has `invoke_agent_runtime` (rerun). The in-image check is AC9 |
| Dependencies: only `boto3` and `pydantic-settings` added | PASS | Diff of `pyproject.toml` and `uv.lock` |
| Consumers and migration | PASS | `infra/app.py` gains only the one `ChatApiStack(app, "AiRadarChatApi")` registration |

Out-of-ownership working-tree changes: `.gitignore` (`.env` became `.env*` plus `!.env.example`, mtime
21:32, before the spec files) and the `pyproject.toml` mypy override `botocore.*` (needed for the new
`botocore` imports). See F8.

## Test coverage
| AC | Test | Status |
|---|---|---|
| AC1 | `tests/test_chat_api_handler.py`: `test_valid_turn_returns_200_with_answer_and_sources`, `test_extra_agent_keys_are_dropped`, `test_invoke_uses_runtime_arn_default_qualifier_fresh_uuid4_and_unchanged_payload`, `test_body_without_history_is_forwarded_as_sent`, `test_base64_encoded_body_is_decoded_before_forwarding`; `tests/test_chat_api_dockerfile.py` (packaging) | PASS |
| AC2 | `tests/test_chat_api_handler.py`: `test_agent_invalid_request_is_returned_as_400_with_the_agents_body`, `test_bad_body_is_rejected_with_a_fixed_rule_and_no_invoke` (5 cases), `test_body_of_exactly_512_kib_is_accepted`, `test_body_one_byte_over_512_kib_is_rejected_without_invoke`, `test_size_cap_counts_utf8_bytes_not_characters` | PASS |
| AC3 | `tests/test_chat_api_handler.py`: `test_agent_upstream_failure_becomes_502`, `test_client_error_becomes_502_and_next_request_succeeds`, `test_unreadable_or_unknown_reply_becomes_502` (8 cases), `test_read_timeout_becomes_504_upstream_timeout_without_internals`, `test_unexpected_exception_text_never_reaches_the_caller`, `test_client_is_built_with_short_timeouts_and_no_retries` | PASS as written. `test_client_is_built_with_short_timeouts_and_no_retries` asserts the defective `retries["max_attempts"] == 1`, and mutation M21 (the correct `total_max_attempts: 1`) **fails** it (F1) |
| AC4 | `tests/test_infra_chat_api.py`: `test_route_is_exactly_post_v1_chat_with_no_default_route`, `test_cors_defaults_to_localhost_origin_post_and_content_type_only`, `test_cors_origins_are_overridable_via_cdk_context_and_never_wildcard` | PASS |
| AC5 | `tests/test_infra_chat_api.py`: `test_default_stage_throttle_is_5_rps_burst_10`, `test_reserved_concurrency_is_set_by_default`, `test_reserved_concurrency_none_override_omits_the_property_entirely`, `test_lambda_timeout_is_28_seconds_under_the_api_gateway_limit`, `test_function_receives_the_chat_runtime_arn_the_handler_reads` | PASS |
| AC6 | `tests/test_infra_chat_api.py`: `test_iam_has_exactly_one_invoke_statement_and_one_log_write_statement`, `test_role_has_no_wildcard_resource_no_model_data_or_secret_access_no_managed_policy` | PASS |
| AC7 | `tests/test_chat_api_handler.py`: `test_two_requests_use_two_distinct_session_ids`, `test_one_log_record_per_request_with_required_keys`, `test_failure_paths_also_log_exactly_one_record` (4 cases), `test_no_log_record_contains_the_question_answer_history_or_caller_ip`; `tests/test_infra_chat_api.py::test_stage_has_no_access_logging_so_no_caller_ip_is_recorded` | PASS offline. The tests use `caplog.set_level`, so they cannot detect the Lambda log-level gap (F2) |
| AC8 | full suite, 536 passed | PASS |
| AC9 | none (manual e2e) | MISSING, by design: human-gated, not run |

Round 2 additions, each in `tests/test_chat_api_handler.py`:

| Revision 2 row (AC3, AC7) | Test | Status |
|---|---|---|
| No retry plus the timeouts | `test_client_is_built_with_short_timeouts_and_no_retries` (edited with approval), `test_timeouts_leave_headroom_under_the_lambda_timeout` | PASS. R1 and R9 are killed |
| Log level survives root WARNING | `test_request_record_survives_root_logger_at_warning_log_level` (a real `logging.Handler` on root, no caplog) | PASS. R2 is killed |
| 500 path typed, logged once, no exception text | `test_bug_before_the_invoke_is_a_typed_500_logged_once_internal` (renders with `logging.Formatter().format`) | PASS. R3 and R3b are killed |
| No CORS header | `test_no_response_carries_a_cors_header_cors` (4 cases), `test_internal_error_response_carries_no_cors_header_cors` | PASS. R4 is killed |
| No first-party import | `test_chat_api_package_imports_no_first_party_package_first_party` (AST over `src/chat_api/**/*.py`) | PASS. R5 and R5b are killed |

The Revision 2 focused command (`-k "retries or timeouts or log_level or internal or cors or first_party"`) gives 11 passed (rerun).

Round 2 mutations were run on a fresh scratch copy,
`/private/tmp/claude-501/-Users-danielerazo-python-project-agentcore-app/4120ef59-76c9-4089-9a21-5eb75004415f/scratchpad/mut2`,
never the working tree. Its baseline was 58 passed across the three chat-api test files. Driver:
`/private/tmp/claude-501/-Users-danielerazo-python-project-agentcore-app/4120ef59-76c9-4089-9a21-5eb75004415f/scratchpad/mutate2.py`.
All 13 were **killed**:
- R1 `max_attempts: 1`
- R1b `max_attempts: 0`
- R2 no `setLevel`
- R3 `logger.exception` restored on the 500 path
- R3b message logged on the 500 path
- R4 CORS header
- R5 `shared` import in the handler
- R5b `contracts` import in the config
- R6 IAM `*`
- R7 no byte cap
- R8 504 mapping dropped
- R9 read timeout 25
- R10 Lambda timeout 30

(The round-1 scratch copy `.../scratchpad/mut` was found modified by a later role, and is no longer a round-1 snapshot. It was not used as a baseline for anything except the two byte-identical test files.)

Round 1 mutation checks were run on a scratch copy (`/private/tmp/claude-501/-Users-danielerazo-python-project-agentcore-app/4120ef59-76c9-4089-9a21-5eb75004415f/scratchpad/mut`), never the working tree, with the repo `.venv`. The baseline in the copy was 49 passed.
Killed: M1 no byte cap, M2 cap `>=`, M3 cap counts characters, M4 504 mapping dropped, M5 extra keys passed through, M7 question logged, M8 fixed session id, M9 exception text in body, M10 IAM `*`, M11 `bedrock:InvokeModel` added, M12 managed policy, M13 throttle 20, M14 CORS `*`, M15 timeout 30, M16 GET route, M18 retries config removed, M19 Dockerfile copies `src/shared/`.
Survived: M6 (the unknown-`error` guard removed; equivalent for every tested input, since the reply still falls to 502), M17 (CORS header in the handler), M20 (first-party import in the handler).
M21 (the correct no-retry config) fails `test_client_is_built_with_short_timeouts_and_no_retries`.

### Tier Results
| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit (pytest + stubbed boto3 client, caplog / `logging` handler) | `tests/test_chat_api_handler.py` (43, byte-identical to round 2) | AC1, AC2, AC3, AC7, Revision 2 row | Yes: fake client by patching `boto3.client`, plus a plain `logging.Handler` and `ast`. No new dev dependency | rerun (round 3, in the full suite) | PASS | none |
| unit (CDK synth, `aws_cdk.assertions`) | `tests/test_infra_chat_api.py` (11) | AC4, AC5, AC6 | Yes: no Docker daemon, no credentials | rerun (round 3, in the full suite) | PASS | none |
| unit (packaging) | `tests/test_chat_api_dockerfile.py` (4) | AC1, AC6 (packaging) | Yes | rerun (round 3, in the full suite) | PASS | none |
| regression | full suite plus protected-file diff | AC8 | Yes | rerun round 3: `uv run pytest tests/ -q` 545 passed; `git diff --stat main` empty | PASS | none |
| e2e (manual) | README runbook steps 1-10; results under `tasks.md` O9 (steps 1-9 run 2026-10-21 by the human, step 10 not run) | AC9 (and the live halves of AC1-AC7) | Yes: AWS credentials, Docker, curl, CloudWatch | reused (human run) + rerun of the zero-spend subset (account, stack, function config, stage, routes, CORS, preflight allowed/disallowed, GET/other 404, non-JSON/array 400, CloudWatch records and metrics). Valid-question turns and bursts were not rerun, by instruction | PARTIAL | F5 (step 10, LOW), F12 (MEDIUM) |

Lint and type-check were rerun in round 3 at the caller's request. `uv run ruff check`, `uv run ruff check --isolated` and `uv run mypy .` (95 source files) were all clean (rerun). harny-feedback in round 3: `.sdd/feedback/.turns/` was modified at 10:27 on 2026-10-21, during the F9/F10 fix turn, so the hook fired. There is still no CI run on the branch (`gh run list` is empty because nothing is pushed; unavailable).
Lint and type-check were rerun in round 2 at the caller's request: `uv run ruff check`, `uv run ruff check --isolated` and `uv run mypy .` (95 source files) were all clean (rerun).
harny-feedback, round 2: `.sdd/feedback/.turns/` was modified at 22:18 on 2026-10-20, during the round-2 test-writer and executor work, so the hook fired. The `N of M` line is still not persisted (unavailable). `gh run list --branch feat/chat-api` returns no runs, because the change is uncommitted (unavailable). Both workflows (`harny-feedback.yml`, `harny-feedback-apps-web.yml`) are present.
harny-feedback, round 1: `.sdd/feedback/.turns/` was modified at 21:58 on 2026-10-19, during implementation. The hook consumes and deletes its turn record, so the hook did fire, but its `N of M command(s) ran` line was not persisted (unavailable). There is no CI run on `feat/chat-api`, because the change is uncommitted (unavailable). See F7.

## Findings
Round 3 status. The rows from earlier rounds below keep their text. This table rules on each closure condition and adds F11-F13.

| Id | Round 3 status | Evidence |
|---|---|---|
| F2 | **Closed** (the live half too) | 123 text-free `chat_api_request` records reached CloudWatch at the default log config (rerun read) |
| F5 | **Mostly closed**, open (LOW) only for step 10 | Steps 1-9 have recorded results, and the zero-spend subset is corroborated (rerun). Step 10, the agent-side invocation count for one slow request, was not run. This does not block. AC9's own text does not include it. It is a Risks mitigation, and its claim (no retry) is already proven against the handler's real `Config` by the round-2 socket probe, on code that is byte-identical. Closure: run step 10 opportunistically when a slow turn occurs, or the human accepts the offline proof |
| F7 | Mostly closed (unchanged) | CI on a pushed branch is still unavailable |
| F8 | Open (LOW, human decision; unchanged) | `.gitignore` and the `botocore.*` override are as before |
| F9 | **Closed** | (a) Step 2 names `ChatApiUrl`, `ChatApiFunctionName`, `ChatApiLogGroupName` and `ChatApiAllowedOrigins`, matching the live stack outputs (rerun). (b) Steps 8 and 9 now have runnable commands. (c) Step 3 uses `python3`, which was confirmed in the real image (O9). (d) The step 5 note now says the body invokes the agent. Residual staleness after the deploy is F12 |
| F10 | **Closed** | `grep -rn LAMBDA_TIMEOUT_SECONDS src infra` is empty. The only hits are the test-local constant in `tests/test_chat_api_handler.py` (rerun). Tests are unedited |
| F11 | New, MEDIUM, open, not blocking | See the row below |
| F12 | New, MEDIUM, open, not blocking | See the row below |
| F13 | New, LOW, open | See the row below |

| Id | Severity | Finding | Closure condition | Status |
|---|---|---|---|---|
| F11 | MEDIUM | AC5 and the binding constraint `-c chat_api_reserved_concurrency=none`. The deployed function is unreserved (live: no function concurrency; account `ConcurrentExecutions` 10, `UnreservedConcurrentExecutions` 10). So a cold parallel burst inside the stage's best-effort burst window can take the whole 10-slot account pool. Live, this gave Lambda 503s rather than 429s (`Throttles` 27, `ConcurrentExecutions` max 10, rerun from CloudWatch), and `ai-radar-feed-api` draws from the same pool, so a chat burst can throttle the public feed. **This is not a defect in the delivered behavior.** The intent (Constraints, AC5) and the plan's binding constraint require exactly this deploy while the quota is 10, the same accepted workaround as FA-R1. The stack default (reserve 5) is the audited value. Rated MEDIUM because it is a real cross-service availability risk on an unauthenticated public endpoint, and the 503s are not the typed 429 the API promises. It does not block: no AC or binding constraint is unmet. The quota request `cf8be0f0ceba4cf787e8e329efd718e0i3872UpR` (`L-B99A9384`, 10 to 1000) now reads `CASE_OPENED` (rerun), not `PENDING` as `tasks.md` records | The quota is raised. Then `AiRadarChatApi` and `AiRadarFeedApi` are redeployed without the `none` flag (reserve 5 each), and a re-run of the step 8 burst shows only 400/429 and zero Lambda `Throttles`. Or the human explicitly accepts the shared-pool risk for now |
| F12 | MEDIUM | AC9 says "the runbook and its recorded results are part of the deliverable, as in `chat-agent-runtime`", and the README was not updated after the deploy. The heading (line 1089) still says "implemented, not deployed". Line 907 says "implemented offline, not deployed". Line 1106 says "every live step below is NOT YET RUN", and each step still ends "NOT YET RUN". The live-state bullet (lines 1229-1230) says "Nothing from the Phase 3 chat path is exposed publicly yet ... not deployed, so there is no public URL". That claim is now false, and in a security-relevant way: an unauthenticated public URL is live. Step 8 still uses the 40-way parallel burst and says "Expect a mix of 400 and 429", but live that command produced 503s under the unreserved config (F11). The results live only in `tasks.md` O9 | README status lines, the live-state section and the runbook record the 2026-10-21 deploy and results (URL, per-step outcomes, latencies, step 10 not run). Step 8 describes the 503 behavior while unreserved, or uses the steady-rate form that produced 429s |
| F13 | LOW | AC5 example ("a sustained request rate above the stage limit -> 429"). The 429 behavior works, but enforcement is lenient: at ~20 req/s for ~4 s, 64 of 80 requests passed, where a strict 5 rps / burst 10 bucket would pass about 30. AWS documents API Gateway throttling as best-effort, so this is not a spec'd-behavior defect. It does mean the real cost ceiling under abuse is roughly 2x nominal, which matters for the $500 budget | Record the observed leniency in the README (with F12), and keep the `AiRadarBudget` alert as the backstop. Or the human accepts it as a note |

Notes (round 3, not findings):
- README lines 1035 and 1043 (`cd infra && cdk deploy AiRadarRuntimeRole` / `AiRadarChatRuntime`) carry the broken `cd infra && cdk` form. They are identical on `main` (`git show main:README.md`, lines 1034 and 1042), so they predate this change and fall outside its scope.
- `tasks.md` O9 says "four `chat_api_request` records". CloudWatch now holds 123 (2 × 200, 121 × 400, mostly the burst). The four are presumably the agent-invoking requests. The claim about the content holds for all 123.
- The O9 observation about follow-up retrieval embedding only the new question is chat-agent behavior (CA-2), outside this spec.

Round 2 status. The round-1 rows below keep their text; this table rules on each closure condition.

| Id | Round 2 status | Evidence |
|---|---|---|
| F1 | **Closed** | The plan was corrected (Revision 2). The test was changed with approval and now fails on `max_attempts` (R1, R1b). The handler uses `total_max_attempts: 1`. The socket probe shows 1 hit and a 504. 545 passed |
| F2 | **Closed offline** (CloudWatch confirmation is in O9 step 9) | `logger.setLevel(logging.INFO)`. A no-caplog root-WARNING test kills R2. The plain-interpreter proof is above |
| F3 | **Closed** | The CORS and AST import tests kill R4, R5 and R5b |
| F4 | **Closed, with residual F9** | The README "Phase 3 — Chat API" section exists with the deploy (with the `none` flag), docker-build/import, curl, preflight and 404 commands. The 429 and log-check steps are prose, not commands; see F9 |
| F5 | Open (LOW, human-gated) | O9 is unchecked and every runbook step reads NOT YET RUN. No overclaim in the README (lines 907, 1089, 1205) |
| F6 | **Closed** | Read 22 s; 3 + 22 = 25 s, 3 s under the 28 s timeout. Guarded by the headroom test (R9) |
| F7 | **Mostly closed** | The 500 path is tested (R3, R3b) and `tasks.md` is refreshed. Still unavailable: CI green on a pushed branch with a non-zero ran count. This can only close after commit and push |
| F8 | Open (LOW, human decision) | The `.gitignore` and the `botocore.*` mypy override are unchanged. `tasks.md` records them for the human |
| F9 | New, LOW | See the row below |
| F10 | New, LOW | See the row below |

| Id | Severity | Finding | Closure condition | Status |
|---|---|---|---|---|
| F9 | LOW | AC9 runbook accuracy (`README.md` "Phase 3 — Chat API"). (a) Step 2 says to note the `ApiUrl` output, but the stack emits `ChatApiUrl`, `ChatApiFunctionName`, `ChatApiLogGroupName` and `ChatApiAllowedOrigins` (`infra/stacks/chat_api_stack.py`). (b) Step 8 (429 burst) and step 9 (read `chat_api_request` records) give no command, only prose. Round-1 F4 asked for the 429 and log-check commands. (c) Step 3 runs `--entrypoint python`. Whether the `public.ecr.aws/lambda/python:3.12` image has a `python` (not just `python3`) on `PATH` was not verified here (no Docker run); `python3` is the safer form. (d) Step 8's "each bad-body request is enough to avoid Sonnet spend" holds only for a body that fails the local checks (for example `not json`). `{"question":""}`, the step 5 body, does invoke the agent | Output name corrected; concrete commands for steps 8 and 9 (for example `seq 30 \| xargs -P30 -I{} curl -s -o /dev/null -w '%{http_code}\n' -X POST ... -d 'not json' \| sort \| uniq -c`, and `aws logs filter-log-events --log-group-name /aws/lambda/ai-radar-chat-api --filter-pattern '"chat_api_request"'`); step 3 confirmed or switched to `python3`. Or the human fixes these while running O9 | Open |
| F10 | LOW | Plan Revision 2: "the 28 s Lambda timeout, 22 s read timeout and 3 s connect timeout are module constants checked together by one test". `src/chat_api/config.py` adds `LAMBDA_TIMEOUT_SECONDS = 28`, but nothing reads it: the headroom test uses its own test-local `LAMBDA_TIMEOUT_SECONDS = 28`, and the construct duplicates `Duration.seconds(28)`. The coupling is two tests pinning the same literal (the headroom test and `test_lambda_timeout_is_28_seconds_under_the_api_gateway_limit`), which does guard drift in practice (R9, R10 killed). The config constant itself is dead | Either the headroom test reads `config.LAMBDA_TIMEOUT_SECONDS` (or the constant is removed), or the human accepts the two-test coupling as a compliant alternative | Open |

Round 1 findings (original text):

| Id | Severity | Finding | Closure condition | Status |
|---|---|---|---|---|
| F1 | CRITICAL | AC3 and the plan's no-retry decision. In `src/chat_api/handler.py`, `_agentcore()` sets `retries={"max_attempts": 1}`. In botocore that means 1 *retry* (2 total attempts), and `ReadTimeoutError` is retryable; the socket probe showed 2 hits. Live, a slow turn is retried, which invokes the agent twice and doubles the Sonnet spend. The 28 s Lambda timeout then fires before the second 25 s read ends, so the caller gets an API Gateway 5xx instead of 504 `upstream_timeout`, and no `chat_api_request` record is written. The value comes from `execution-plan.md` (Proposed approach), and `test_client_is_built_with_short_timeouts_and_no_retries` pins it | The architect corrects the plan to "no retries" (`total_max_attempts: 1`, or `max_attempts: 0`). The test-writer changes the test, with human approval, so it fails on any config that allows a retry. The executor changes the handler. The full suite is green | Open |
| F2 | HIGH | AC7 and AC9: in Lambda the `chat_api_request` INFO record is very likely dropped. `logger.info` is used, no level is set in the handler, and the construct leaves the log format at Text with no `ApplicationLogLevel`. The Lambda Python bootstrap then leaves the root logger at WARNING. The unit tests cannot see this because they set the caplog level. The AC9 steps that read latency and confirm text-free records depend on this record. (The same latent pattern exists in `src/api/handler.py` and predates this change; that copy is a note only.) | Either the handler sets the module logger level to INFO, or the construct sets `logging_format=JSON` with `application_log_level=INFO`. A test (unit or synth) fails if the level setup is removed. AC9 shows a `chat_api_request` record in CloudWatch. Closed before O9 runs | Open |
| F3 | MEDIUM | Two binding constraints are met but no test guards them: the handler emits no CORS headers (M17 survives), and the handler imports no first-party package (M20 survives; only the AC9 in-container import would catch it) | Tests that fail when the handler adds any `access-control-*` header or imports `curation`, `api`, `chat`, `shared` or `contracts`. Alternatively, the human explicitly accepts the gap at the post-audit gate | Open |
| F4 | MEDIUM | O8 is partly done. `src/chat_api/AGENTS.md` exists, but the README "Phase 3 — Chat API" runbook (an AC9 deliverable, with `-c chat_api_reserved_concurrency=none`) is not written. Known open | The README section exists with the deploy, curl, preflight, 404, 429, log-check, docker-build and import commands | Open |
| F5 | LOW | AC9 and O9 live verification have not run: no deploy, no curl/preflight/404/429 checks, no cold/warm latency, no real `docker build` or in-container import. The e2e tier is not run. Known open, human-gated | Results recorded under O9 in `tasks.md` (account printed first) after F1 and F2 are closed. A real image build plus `python -c "import chat_api.handler"` and `boto3.client("bedrock-agentcore")` inside the image | Open |
| F6 | LOW | Timeout headroom: connect 3 s plus read 25 s equals the 28 s Lambda timeout, so a slow connect followed by a full read leaves no time to write the 504 response and the log record | Lower the read timeout (for example to 23-24 s) or record why the margin is acceptable | Open |
| F7 | LOW | Gaps in evidence and state. The 500 `internal_error` catch-all (an executor-reported addition the plan allows) has no test. The harny-feedback `N of M` line is not persisted, and there is no CI run on the branch. `tasks.md` is stale: Status still reads "Awaiting intent approval", O4-O6 say "Red: pending", and O10 is "pending" although the executor's last command ran it | A test for the 500 path (or explicit acceptance). CI green on the pushed branch with a non-zero ran count. `tasks.md` state corrected | Open |
| F8 | LOW | Changes outside the plan's Ownership: the `.gitignore` edit (`.env*`, `!.env.example`) and the `pyproject.toml` mypy override `botocore.*`. The override is justified by the new `botocore` imports. The `.gitignore` edit predates the spec files and may be the human's | The human confirms or reverts the `.gitignore` edit, and both are recorded in `tasks.md` | Open |

Notes, not findings:
- These executor-reported deviations were checked and accepted as compliant alternatives:
  - Group stored as `chat-api`: uv normalizes the name, and `--only-group chat_api` resolves it under uv 0.7.17, the version both locally and in the Dockerfile.
  - Lambda memory 256 MB: the spec does not set it.
  - The 500 `internal_error` catch-all: the plan allows it.
  - `chat_api_upstream_error` instead of `chat_api_request_failed` for invoke exceptions: the event name is a minor rename. Its stack trace holds the AWS exception text and source lines, never the body, because the payload is passed as a value. The planted-text test covers this path.
- M6 is an equivalent mutant.
- `specs/archived/chat-agent-runtime/.sdd/feedback/.turns/` is untracked hook state from earlier sessions (Oct 14 and Oct 18), not from this feature.
- The CDK image asset stages the whole repo root into `cdk.out/` (`.dockerignore` does not exclude `apps/`). This is the existing feed-api pattern.

## Audit log
| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-20 | REJECTED | 536 passed, ruff, ruff --isolated and mypy clean (rerun). 20 mutations run: 17 killed, 3 survived (1 equivalent). The retry-config probe demonstrates F1. Blocking: F1. Must close before O9: F2. Known open: O8 (F4), O9/AC9 (F5) |
| 2 | 2026-10-20 | APPROVED WITH RESERVATIONS | Plan Revision 2. 545 passed, ruff, ruff --isolated and mypy clean (rerun). Socket probe on the handler's real Config: 1 hit, 504 in 22.07 s. No-caplog root-WARNING interpreter run: the record is emitted and the 500 output has no message. 13/13 mutations killed. Closed: F1, F2 (offline), F3, F4 (with residual F9), F6. Mostly closed: F7 (CI unavailable until push). Open: F5 (AC9, human-gated), F8, F9, F10, all LOW. Nothing blocking |
| 3 | 2026-10-21 | APPROVED WITH RESERVATIONS | 545 passed, ruff, ruff --isolated and mypy clean (rerun). Code and tests are byte-identical to round 2 except the F10 removal. Live O9 corroborated read-only: stack, function, stage throttle 5/10, a single route, CORS allow/deny, 404s, 400s, 123 text-free records, and Lambda throttle metrics. Closed: F2 (live), F9, F10. Mostly closed: F5 (step 10 only). New: F11 (MEDIUM, shared 10-slot pool under the spec'd `none` override), F12 (MEDIUM, README stale after the deploy), F13 (LOW, lenient throttle). Nothing blocking |

## Final verdict

APPROVED WITH RESERVATIONS

**Summary**: Round 3 has the live evidence: AC1-AC9 are met on the deployed stack in account `626259825216`. I corroborated the evidence independently without Bedrock spend. The record is text-free in CloudWatch (F2 closed live), and the F9/F10 fixes are verified. The reservations are operational and documentary, not defects in the delivered behavior. The unreserved function shares the account's 10-slot Lambda pool with feed-api, as the spec requires while the quota is 10 (F11). The README still says "not deployed / no public URL" (F12). Step 10 and the lenient throttle are documented residuals (F5, F13).

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- F12: update the README chat-api section, line 907 and the live-state bullet to record the deploy, the public URL and the O9 results. The "no public URL" claim is now false. Fix step 8's expected output.
- F11: once the quota request is approved, redeploy both APIs with reserved concurrency 5 and re-run the burst. Until then, the human accepts that a chat burst can throttle the feed.

**Recommendations** (nice to have):
- F5: run step 10 when a naturally slow turn occurs, or accept the offline proof.
- F13: note the best-effort throttle leniency next to the budget alert.
- F7: get CI green on the pushed branch with a non-zero ran count. F8: the human confirms or reverts the `.gitignore` edit.
- Mark O9 `[x]` with the step-10 exception, and refresh the quota status (`CASE_OPENED`) in `tasks.md`. O11 can be checked from this verdict.

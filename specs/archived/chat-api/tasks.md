# Tasks: Chat API

## Status
Accepted — pending synchronization

Audit round 3, 2026-10-21: APPROVED WITH RESERVATIONS (`audit.md`, Final verdict), signed off by the human on 2026-10-21. O9 is done with one explicit exception (step 10, F5). Open reservations at ship time: F5, F7, F8, F11, F13.

Intent revision 1 approved 2026-10-19 and the execution plan approved 2026-10-19 by Daniel Erazo. Offline work (O1-O8) is test-writer and executor work. O9 (AC9) writes to the real AWS account `626259825216`: **each step runs only on the human's explicit go-ahead**, one at a time, and no role runs it unprompted. Evidence per step (command, output, timestamp, account printed first) is recorded under that outcome.

## Baseline
- Base commit: ce5df0b
- Branch: feat/chat-api
- Interpreter: Python 3.12.11 (`.venv`, activated; run `uv sync --all-groups`, never plain `uv sync`, which prunes the `infra` group)
- Cwd: /Users/danielerazo/python/project-agentcore-app
- Commands: test `uv run pytest tests/ -q`; lint `uv run ruff check`; type-check `uv run mypy .`
- Pre-existing failures: none (`uv run pytest tests/` -> 487 passed on 2026-10-19; the harness doctor's only failure was `spec-state:chat-api`, expected while this spec set was incomplete)

## Outcomes
- [x] **O1** (AC1, AC2, AC3, AC7) Red-phase handler tests exist and fail for the right reason.
  - Tests: `tests/test_chat_api_handler.py` (stubbed `bedrock-agentcore` client): happy path and key stripping, payload forwarded unchanged, local pre-checks and the 512 KiB boundary, agent `invalid_request` passthrough, 502/504 mappings, unknown reply shapes, distinct session ids, one text-free `chat_api_request` record per request
  - Red: `uv run pytest tests/test_chat_api_handler.py -q` -> 34 errors, all in the `env` fixture: `ModuleNotFoundError: No module named 'chat_api'` (src/chat_api/ not yet written). Ruff clean.
  - Green: `uv run pytest tests/test_chat_api_handler.py -q` -> all passed (full suite 536 passed, 2026-10-19).
- [x] **O2** (AC4, AC5, AC6) Red-phase synth tests exist and fail for the right reason.
  - Tests: `tests/test_infra_chat_api.py`: route set and CORS, stage throttle 5/10, reserved-concurrency default and `none` override, 28 s timeout, exact IAM statements, pinned account and region
  - Red: `uv run pytest tests/test_infra_chat_api.py -q` -> collection error: `ModuleNotFoundError: No module named 'stacks.chat_api_stack'` (infra/lib/chat_api.py and the stack not yet written). Ruff clean.
  - Green: `uv run pytest tests/test_infra_chat_api.py -q` -> all passed (full suite 536 passed, 2026-10-19).
- [x] **O3** (AC1, AC6) Red-phase packaging test exists and fails for the right reason.
  - Tests: `tests/test_chat_api_dockerfile.py`: `--only-group chat_api`, copied directories, CMD, and an offline `boto3.client("bedrock-agentcore")` construction check
  - Red: `uv run pytest tests/test_chat_api_dockerfile.py -q` -> 3 failed (`expected .../Dockerfile.chat_api to exist`), 1 passed (`test_locked_boto3_has_the_bedrock_agentcore_client`: the locked boto3 already has the client, so it is green by design). Ruff clean.
  - Green: `uv run pytest tests/test_chat_api_dockerfile.py -q` -> 4 passed (full suite 536 passed, 2026-10-19).
- [x] **O4** (AC1, AC2, AC3, AC7) The Lambda handler and its settings.
  - Files: `src/chat_api/__init__.py`, `src/chat_api/config.py` (`pydantic-settings`, `CHAT_RUNTIME_ARN`), `src/chat_api/handler.py`; imports no other first-party package
  - Red: the original red output for O4 was not captured separately; the handler tests errored at the `env` fixture (`ModuleNotFoundError: No module named 'chat_api'`, see O1). Revision 2 red (3 + 1 failing handler tests) is under Working state.
  - Green (round 2, 2026-10-20): `src/chat_api/{__init__,config,handler}.py` updated for Revision 2 (`total_max_attempts: 1`, read timeout 22, module logger level INFO, 500 path logs exception class + frames only). `uv run pytest tests/test_chat_api_handler.py -q` -> 43 passed; ruff, `ruff check --isolated` and mypy clean; imports no first-party package.
- [x] **O5** (AC1, AC6) The image and dependency group.
  - Files: `pyproject.toml` and `uv.lock` (new `chat_api` group: `boto3`, `pydantic-settings`), `Dockerfile.chat_api`
  - Red: original red output not captured; the packaging tests failed with `expected .../Dockerfile.chat_api to exist` (see O3).
  - Green: `uv add --group chat_api boto3 pydantic-settings` (uv normalizes the group to `chat-api`; `--only-group chat_api` resolves to it); `uv export --frozen --no-emit-project --only-group chat_api` lists boto3==1.43.56 and pydantic-settings==2.14.2; `tests/test_chat_api_dockerfile.py` green. Real `docker build` not run (human AC9 step).
- [x] **O6** (AC4, AC5, AC6) The CDK construct, stack and registration.
  - Files: `infra/lib/chat_api.py`, `infra/stacks/chat_api_stack.py`, `infra/app.py`; context keys `chat_api_allowed_origins` and `chat_api_reserved_concurrency`; outputs for the URL, function name and log group
  - Red: original red output not captured; the synth tests failed at collection with `ModuleNotFoundError: No module named 'stacks.chat_api_stack'` (see O2).
  - Green (round 2): `tests/test_infra_chat_api.py` 11 passed (synth only, nothing deployed); only a comment in `infra/lib/chat_api.py` changed in round 2 (22 s read timeout; the 28 s literal is duplicated from `src/chat_api/config.py`, not imported); `ChatApiStack(app, "AiRadarChatApi")` registered in `infra/app.py`.
- [x] **O7** (AC8) Migration: existing consumers and tests.
  - Evidence: no test hard-codes a stack count (grep of `tests/test_infra*.py`); `git diff --stat main` over the protected files is empty; full suite 545 passed in round 2 (487 baseline + 58 new).
  - Check `tests/test_infra*.py` for hard-coded stack counts; confirm no protected file changed (`git diff --stat main` shows nothing under `chat_app.py`, `src/chat/`, `src/shared/`, `src/api/`, `infra/lib/feed_api.py`, `infra/lib/chat_runtime.py`, `infra/lib/agent_runtime.py`)
- [x] **O8** Docs (round 2: README "Phase 3 — Chat API" runbook written, live steps marked NOT YET RUN; `src/chat_api/AGENTS.md` updated for the 22 s read timeout and no-retry config): `src/chat_api/AGENTS.md` (purpose, key files, commands), and the README "Phase 3 — Chat API" runbook written for O9 (flags in the commands, including `-c chat_api_reserved_concurrency=none`).
- [x] **O9** (AC9) Live verification, human-gated, one step at a time (done 2026-10-21 with the explicit step-10 exception, F5): print the account first; `cdk deploy AiRadarChatApi -c chat_api_reserved_concurrency=none`; a real `docker build -f Dockerfile.chat_api .` and in-container import; `curl` a grounded question (200 with sources); `curl` a bad body (400); `OPTIONS` preflight from `http://localhost:3000`; a `GET` (404); a burst above the burst limit (429); read `chat_api_request` records for cold and warm latency and the absence of text.
  - Evidence (2026-10-21, run from the repo root, account `626259825216` printed first via `aws sts get-caller-identity`, user `[username]`; steps 1-9 run, step 10 NOT run):
    - Deploy: `uv run cdk deploy AiRadarChatApi --app "uv run python infra/app.py" -c chat_api_reserved_concurrency=none -c chat_api_allowed_origins=http://localhost:3000 --require-approval never` -> `CREATE_COMPLETE` in 66 s. Outputs: `ChatApiUrl=https://<api-id>.execute-api.us-east-1.amazonaws.com`, function `ai-radar-chat-api` (arm64, 28 s, 256 MB, Active, `CHAT_RUNTIME_ARN` set), log group `/aws/lambda/ai-radar-chat-api`. A `cdk diff` before the deploy showed only additions and the four AC6 IAM statements. Two earlier attempts did not deploy (a wrapped `-c` argument; a non-TTY abort at the IAM prompt); `describe-stacks` confirmed no stack existed in between.
    - Image (step 3): `docker build --platform linux/arm64 -f Dockerfile.chat_api` then `python3 -c "import chat_api.handler; import boto3; boto3.client('bedrock-agentcore', ...)"` inside it printed `ok 1.43.56`; probe image removed. This is the in-container import the offline tests cannot give.
    - Grounded question (step 4): 200 in 7.0 s, keys exactly `answer` and `sources` (4 sources, `[1]`-`[3]` cited). Follow-up with 2 history items: 200 in 3.7 s.
    - Empty question (step 5): `400 {"error":"invalid_request","detail":"question_empty"}` (the agent's body, unchanged), 0.9 s. Non-JSON body: `400 body_not_json` from the Lambda, no agent call.
    - CORS (step 6): preflight from `http://localhost:3000` -> 204, `access-control-allow-origin: http://localhost:3000`, `allow-methods: POST`, `allow-headers: content-type`. A disallowed origin -> 204 with no `access-control-*` headers.
    - Routing (step 7): `GET /v1/chat` -> 404, `POST /v1/other` -> 404.
    - Throttling (step 8): the stage has `ThrottlingRateLimit 5`, `ThrottlingBurstLimit 10`. A steady ~20 req/s for ~4 s (80 non-JSON requests) -> 64 x 400, 16 x 429, and a normal request after 10 s of quiet -> 400. The limit engages but is more lenient than nominal (API Gateway throttling is best-effort). A 40-way parallel cold burst (two runs) produced 503s, not 429s: Lambda metrics showed `Throttles` 27 and `ConcurrentExecutions` max 10, i.e. the account concurrency pool of 10 was exhausted (the function is unreserved, `chat_api_reserved_concurrency=none`).
    - Logs (step 9): four `chat_api_request` records reached CloudWatch at the default Lambda log level (F2 confirmed live), with only `status, outcome, question_chars, history_items, duration_ms, session_id`; no question, history, answer or address text. Latency: Lambda init (cold) 2996 ms; agent turns `duration_ms` 6570 (first) and 3345 (second, a fresh session id); max memory 110 MB of 256.
    - NOT run: step 10 (agent-side invocation count for one slow request, F1). A slow turn cannot be triggered on demand; F1 is covered by the offline socket probe in audit round 2.
    - Observation, out of scope for this spec: a follow-up whose meaning depends on history ("Which of those is from a major lab?") retrieved different cards than its first turn, because retrieval embeds only the new question (chat-agent behavior, CA-2).
    - Count note (added at the round-3 audit, not new evidence): the step-9 count above (four records) differs from the audit round 3 CloudWatch read, which counted 123 `chat_api_request` records (2 with status 200, 121 with status 400, most from the step-8 burst). The key set and the absence of text hold for all 123 records.
    - Step 10 is an explicit exception, carried as open finding F5 (LOW). The audit round 3 verdict does not treat it as blocking.
- [x] **O10** Broader suite vs baseline: `uv run pytest tests/ -q && uv run ruff check && uv run ruff check --isolated && uv run mypy .` (baseline: 487 passed; ruff and mypy clean).
  - Result: 545 passed; `ruff check`, `ruff check --isolated` and `mypy .` (95 source files) clean. Evidence: the 2026-10-20 run (see Working state), and the audit round 3 rerun on 2026-10-21 (`audit.md`, AC8 and Tier Results).
- [x] **O11** Independent audit: verdict from `audit.md` (written by the auditor only).
  - Evidence: `specs/chat-api/audit.md` round 3, 2026-10-21, Final verdict APPROVED WITH RESERVATIONS, with no critical issues. Human sign-off 2026-10-21.

## Working state
- Updated: 2026-10-21 (audit round 3 APPROVED WITH RESERVATIONS; human sign-off; documentation and archive pass)
- Outcome: O1-O11 done. O9 is done except step 10 (F5)
- Phase: accepted, pending synchronization
- In progress: nothing
- Last command: `uv run pytest tests/ -q && uv run ruff check && uv run ruff check --isolated && uv run mypy .` -> 545 passed, ruff clean, ruff --isolated clean, mypy "no issues found in 95 source files"
- Next step: harny-document hand-off (Shipped stamp, harny-sync archive, harny-adr)
- Revision 2 (test-writer, 2026-10-20), Red evidence, `tests/test_chat_api_handler.py` (`uv run pytest tests/test_chat_api_handler.py -q` -> 3 failed, 40 passed; ruff and mypy clean):
  - RED, right reason: `test_client_is_built_with_short_timeouts_and_no_retries` (`assert 25 == 22`, read_timeout), `test_timeouts_leave_headroom_under_the_lambda_timeout` (`assert (3 + 25) <= (28 - 3)`), `test_request_record_survives_root_logger_at_warning_log_level` (`assert 0 == 1`, record dropped at root WARNING).
  - Green now, mutation-checked on a scratch copy: no-CORS-header tests (5 cases) fail with an `Access-Control-Allow-Origin` header added; `test_chat_api_package_imports_no_first_party_package_first_party` fails with `from shared import config` added (`['handler.py: shared'] == []`). `test_bug_before_the_invoke_is_a_typed_500_logged_once_internal` is green now (the 500 path already worked).
  - Strengthened (2026-10-20): `test_bug_before_the_invoke_is_a_typed_500_logged_once_internal` now renders every record with `logging.Formatter().format` and asserts no exception text (`pre-invoke-secret-5520`, planted question) in any rendered record or the body, and `RuntimeError` present. RED against the current handler (`logger.exception` renders the traceback with `RuntimeError: pre-invoke-secret-5520 PLANTED-QUESTION-zq81`); `uv run pytest tests/test_chat_api_handler.py -q` -> 4 failed, 39 passed.

## Finding responses
| Finding | Response | Evidence |
|---|---|---|
| F1 | Fixed. Client config is now `retries={"total_max_attempts": 1}` (no `max_attempts` key), connect 3 s, read 22 s. | `tests/test_chat_api_handler.py` 43 passed, incl. `test_client_is_built_with_short_timeouts_and_no_retries` and `test_timeouts_leave_headroom_under_the_lambda_timeout` |
| F2 | Fixed. `logging.getLogger(__name__).setLevel(logging.INFO)` in `handler.py`, so `chat_api_request` survives a WARNING root. | `test_request_record_survives_root_logger_at_warning_log_level` green. Live CloudWatch confirmation is O9 step 9 (NOT YET RUN) |
| F3 | Closed by the Revision 2 tests (no-CORS-header and no-first-party-import guards); no handler change needed. | Tests green; mutation checks recorded under Working state |
| F4 | Fixed. README "Phase 3 — Chat API" runbook written, with `-c chat_api_reserved_concurrency=none` and `-c chat_api_allowed_origins`. | `README.md` section "Phase 3 — Chat API" |
| F5 | Open (LOW), step 10 only. Steps 1-9 are run and recorded under O9. Step 10 (agent-side invocation count for one slow request) is not run, because a slow turn cannot be triggered on demand. The no-retry property is covered offline by the audit round 2 socket probe on the handler's real client config (1 hit, 504 in 22.07 s). Run step 10 when a natural slow turn occurs, or accept the offline proof. Not blocking (audit round 3). | O9 evidence; `audit.md` round 3 F5 row |
| F11 (new, live) | Open reservation (MEDIUM, non-blocking per audit round 3): the function is unreserved, so a cold parallel burst exhausts the account's 10-slot Lambda concurrency pool (503s from Lambda, not 429s from the stage). The same pool is shared with `ai-radar-feed-api`, so a chat burst can throttle the feed. | O9 step 8 evidence (`Throttles` 27, `ConcurrentExecutions` max 10). 2026-10-21 15:27 UTC: Service Quotas increase requested, Lambda `L-B99A9384` 10 -> 1000 in us-east-1, request id `cf8be0f0ceba4cf787e8e329efd718e0i3872UpR`, status CASE_OPENED, support case 179259663100438 (read by the audit round 3, 2026-10-21). Once approved: redeploy `AiRadarChatApi` and `AiRadarFeedApi` without the `...reserved_concurrency=none` flag (defaults reserve 5 each) and re-run the O9 burst. |
| F6 | Fixed. Read timeout 22 s: connect 3 + read 22 = 25 s leaves 3 s of the 28 s Lambda timeout. | `src/chat_api/config.py`, `infra/lib/chat_api.py` comment; headroom test green |
| F7 | Fixed. The 500 path is tested and now logs exception class + frames only, never the message. `tasks.md` state refreshed. CI on the pushed branch remains unavailable (uncommitted). | `test_bug_before_the_invoke_is_a_typed_500_logged_once_internal` green |
| F9 | Fixed (README only). Step 2 names `ChatApiUrl`, `ChatApiFunctionName`, `ChatApiLogGroupName`, `ChatApiAllowedOrigins`; steps 8 and 9 have runnable commands (40-way parallel `not json` curl with status count; `aws logs filter-log-events`/`tail` with cold vs warm guidance); step 3 uses `--entrypoint python3`, to be checked in the real image; step 5 and 8 notes corrected. All steps still NOT YET RUN. | `README.md` "Phase 3 — Chat API" |
| F10 | Fixed by removing the dead `config.LAMBDA_TIMEOUT_SECONDS`; the literal 28 stays in `infra/lib/chat_api.py` (infra must not import src), comments updated. | `grep -rn LAMBDA_TIMEOUT_SECONDS` leaves only the test-local constant; tests unedited |
| F8 | Not changed by the executor. `.gitignore` (`.env*`, `!.env.example`) and the `pyproject.toml` `botocore.*` mypy override are left for the human to confirm or revert. | `git status` |
| F12 (audit round 3) | Fixed in the 2026-10-21 documentation pass. README "Phase 3 — Chat API" records the live deploy (account `626259825216`, stack `AiRadarChatApi`, URL), the per-step results, and step 10 as not run. The status line, the section heading and the live-state bullet no longer say "not deployed" or "no public URL". Step 8 states the 503 behaviour while unreserved (F11) and the 429 result for a steady ~20 req/s run. | README "Phase 3 — Chat API" and the live-state bullet |
| F13 (audit round 3) | Open (LOW), accepted as a note. The observed leniency is recorded in the README next to the budget alert: at ~20 req/s for ~4 s, 64 of 80 requests passed, where a strict 5 rps / burst 10 bucket would pass about 30. API Gateway throttling is best-effort, and `AiRadarBudget` is the backstop. | README step 8 and "Known risks" |

## Checkpoint
Spec set (`intent.md`, `execution-plan.md`, `tasks.md`, `audit.md`) is on branch `feat/chat-api`, uncommitted. Audit round 3 (2026-10-21) gave APPROVED WITH RESERVATIONS and the human signed off the same day. Remaining: the harny-document hand-off (the `Shipped:` stamp, the archive to `specs/archived/chat-api/`, and the ADRs).

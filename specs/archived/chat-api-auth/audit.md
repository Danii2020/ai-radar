# Audit: Chat API Authentication

Round 2, 2026-10-21. Same branch (`feat/chat-api-auth`) and base (`6d19f14`), still uncommitted,
reviewed against `intent.md` revision 2 and `execution-plan.md` Revision 2. What changed since
round 1: the docs-only runbook fixes for F1, F2, F3 and F8 (plan Revision 2, README), and the
human-approved live deploy and verification on account `626259825216` recorded in `tasks.md` O7.
Docs-only check (rerun): the only files modified after the round-1 `audit.md` are `README.md`,
`specs/chat-api-auth/execution-plan.md` and `specs/chat-api-auth/tasks.md`. Every implementation,
infra, script and test file keeps its pre-round-1 mtime (11:21 to 11:26 local, against 11:47 for the
round-1 audit), and `git diff --stat 6d19f14` over the protected set still shows only
`src/chat_api/AGENTS.md`. So no source, test, infra or script change happened after round 1.
The auditor made no AWS writes. Read-only calls only: `sts get-caller-identity`,
`cloudformation describe-stacks`, `apigatewayv2 get-routes`, `get-api`, `get-authorizers` and
`get-stages`, `iam get-user`, `list-access-keys` (status and date only), `list-user-policies`,
`get-user-policy`, `list-attached-user-policies`, `list-groups-for-user` and `get-login-profile`,
`lambda get-function-configuration` and `get-function-concurrency`, `logs filter-log-events`, and
`cloudwatch get-metric-statistics`. Three zero-cost unsigned curls (a valid-body POST, an OPTIONS
preflight with `Origin`, and a non-JSON POST with `Origin`) at 17:16 UTC. Nothing signed was sent,
and the agent was not invoked. The real API id appears nowhere in this file (`<api-id>`).

Round 1, 2026-10-21. Scope: the offline implementation on branch `feat/chat-api-auth`
(uncommitted, base `6d19f14`). The human-gated live verification (AC7, tasks O7) and the
deploy have not run, so AC7 is reported as unverified and human-gated, not as a defect.
The auditor made no AWS writes. Read-only AWS calls only: `sts get-caller-identity`,
`cloudformation describe-stacks`, `apigatewayv2 get-routes` and `get-api`, `iam get-user`,
`iam list-roles` and `list-attached-role-policies`, and `cdk diff --no-change-set`. No request
invoked the agent. The real API id is not written here.

## AC results

### Round 2 (current)
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | Live signed call: 200 with a grounded answer, `[1]` cited, 5161 ms (reused, O7). Corroborated: the only `chat_api_request` record since the deploy (17:12:31 UTC) has `status 200, outcome ok`, and `Invocations` is 1.0 at 17:12 (rerun). The handler is unchanged and the full suite passes: 559 passed (rerun). The offline signing evidence from round 1 still holds, since the script and tests are unchanged (reused). |
| AC2 | PASS (one sub-probe not run, F9) | Unsigned valid-body POST -> 403 `{"message":"Forbidden"}` (rerun 17:16 UTC; reused O7). Fabricated `Authorization`, `--tamper` and `--unsigned` -> 403, and a policy-less throwaway identity -> 403 (reused, O7). The throwaway user is gone: `get-user` gives `NoSuchEntity` (rerun). Zero invocations for the rejected requests: since 17:07:45Z the log group holds exactly one START/END/REPORT triple and one `chat_api_request` record, and `Invocations` stays at a single 1.0 datapoint, also 4 minutes after the auditor's own probes (rerun). The expired-signature case is not exercised live. The human accepted `--tamper` as the bad-signature probe (plan Revision 2, F1 response). The intent AC2 wording still names "expired", so this is a recorded human acceptance, not an auditor pass. The signed unrouted probes were not run (F9). Unsigned unrouted requests (`GET /v1/chat`, `OPTIONS`) give 404 (reused O7; rerun for OPTIONS). |
| AC3 | PASS | `get-routes`: exactly one route, `POST /v1/chat`, `AWS_IAM`, no authorizer id. `get-authorizers`: 0. `get-api`: `CorsConfiguration` null (rerun). The OPTIONS preflight with `Origin: http://localhost:3000` gives 404 with no `access-control-*` header, and a POST with `Origin` gives 403 with none (rerun). The knob was removed offline (round 1, unchanged). |
| AC4 | PASS | Live: user `ai-radar-chat-api-caller` exists (created 17:06:52Z by the stack). It has one inline policy, `ChatApiChatApiCallerDefaultPolicy0867603B`, with one statement: `Allow`, `execute-api:Invoke`, `arn:aws:execute-api:us-east-1:626259825216:<api-id>/*/POST/v1/chat`. It has no attached policy, no group and no login profile. It has exactly one access key, `Active`, created 17:12:10Z, outside CloudFormation (rerun). Output `ChatApiCallerUserName=ai-radar-chat-api-caller` (rerun). |
| AC5 | PASS | The live `chat_api_request` record has exactly the seven keys `duration_ms, event, history_items, outcome, question_chars, session_id, status`. No log event since the deploy contains an IAM ARN, `AKIA`/`ASIA`, the caller name, `userArn` or `accessKey` (rerun). Stage `$default`: 5 req/s, burst 10, no access logging. Lambda: 28 s, 256 MB, arm64, env `CHAT_RUNTIME_ARN` only, no reserved concurrency (the `none` override) (rerun). The role statements are unchanged per the round-1 `cdk diff` and the synth tests (reused / rerun in the suite). |
| AC6 | PASS | In place: the Api's `CreatedDate` (15:12:20Z) predates the stack update (17:06:48Z), so it is the same API and the same id (rerun). O7 records that the exposed URL shares this API id (reused). The other `AiRadar*` stacks were last updated on or before 2026-10-18 (rerun). Suite 559 passed, ruff, `ruff --isolated` and mypy clean (rerun). The protected-path diff is unchanged (rerun). |
| AC7 | PASS, except step 10 (F9) | Every probe intent AC7 names was run and recorded in O7: unsigned 403 with zero invocations, the exposed URL (same API id) 403, signed caller 200 grounded, another identity 403 (reused; corroborated by rerun where read-only). The runbook covers key creation, server-only storage and rotation (README lines 1138-1142). The results are recorded in `tasks.md` O7 but not yet in the README (F10), and O7 itself is still unchecked (F11). |

### Round 1 (superseded)
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS (offline); live part pending AC7 | `src/chat_api/` byte-identical to `6d19f14` (`git diff --stat` empty), so CAPI-1..3 hold by construction. The handler suite passes. `build_signed_headers` produces `AWS4-HMAC-SHA256 Credential=<akid>/<date>/us-east-1/execute-api/aws4_request` with `host` and `x-amz-date` signed. An auditor probe (local HTTP server, fake credentials) recomputed the signature server-side from the received request: valid for a normal run, invalid for `--tamper`, absent for `--unsigned`. The signed 200 against the real API is AC7 (unverified). (rerun) |
| AC2 | PASS (offline); live part pending AC7 | The synthesized route has `AuthorizationType: AWS_IAM`, no `AWS::ApiGatewayV2::Authorizer` and one `AWS::Lambda::Permission` (the integration's). `cdk diff` against the live stack shows `AuthorizationType NONE -> AWS_IAM` on the existing route. The live route is still `NONE` today (`get-routes`), so the change is real. The 403 and zero-invocation behavior is only provable live (AC7). The expired-signature sub-case has no tool in the runbook (F1). (rerun) |
| AC3 | PASS (offline); live CORS check missing from runbook (F2) | Template: exactly one route `POST /v1/chat`, the Api has no `CorsConfiguration`, no `ChatApiAllowedOrigins` output. A template synthesized with `-c chat_api_allowed_origins=...` is identical (test). The `allowed_origins` param, attribute, constant and context read are gone from `infra/lib/chat_api.py` and `infra/stacks/chat_api_stack.py`. `cdk diff` shows `[-] CorsConfiguration` on the Api (modified, not replaced). (rerun) |
| AC4 | PASS | Template: exactly one `AWS::IAM::User` `ai-radar-chat-api-caller` with only `UserName` (no `LoginProfile`, `ManagedPolicyArns`, `Groups`, `Policies`); one `AWS::IAM::Policy` whose `Users` is that user, with one statement: `Allow`, `execute-api:Invoke`, resource `arn:${Partition}:execute-api:${Region}:${AccountId}:${ChatHttpApi}/*/POST/v1/chat`. Zero `AWS::IAM::AccessKey` and zero `AWS::IAM::ManagedPolicy`. `iam get-user` confirms no name collision in the account today. (rerun) |
| AC5 | PASS | Lambda role policy identical (two statements, `InvokeChatRuntime` on the runtime and `DEFAULT` endpoint ARNs, `ChatApiLogsWrite` on the log group), no managed policy; stage throttle 5/10; timeout 28; `CHAT_RUNTIME_ARN` set; reservation omitted under `-c chat_api_reserved_concurrency=none` (synth), default 5 (test). `cdk diff` shows no role or stage change. `test_iam_authorizer_context_is_not_logged` fails when the caller ARN is added to the record or to a separate INFO record (mutations). Handler unchanged. (rerun) |
| AC6 | PASS (offline); live URL check pending AC7 | Protected paths unchanged vs `6d19f14`: `chat_app.py`, `src/chat`, `src/shared`, `src/api`, `src/chat_api/handler.py`, `src/chat_api/config.py`, `infra/lib/{feed_api,chat_runtime,agent_runtime}.py`, `infra/app.py`, `infra/stacks/feed_api_stack.py`, `pyproject.toml`, `uv.lock` (empty diff). HttpApi logical id `ChatApiChatHttpApi975E960D` unchanged; `cdk diff` shows the Api and Route as `[~]` modified, no replacement. Full suite 559 passed. Only the two CORS synth tests were removed. One more `[~]` than the plan predicted: the Lambda image asset hash (F3). (rerun) |
| AC7 | N/A (unverified, human-gated) | Not run, by design (tasks O7 open). The runbook exists in the README "Authentication amendment" subsection, marked NOT YET RUN. Gaps in it: F1, F2, F8. (unavailable) |

## Binding-constraint compliance

### Round 2 (current)
Every round-1 PASS still holds, because no implementation file changed (rerun mtime and diff check). Live corroboration added this round:

| Constraint | Status | Evidence |
|---|---|---|
| One route `POST /v1/chat`, `AWS_IAM`, no `$default` | PASS | `get-routes` (rerun). |
| No `CorsConfiguration` | PASS | `get-api` null, and the preflight has no `access-control-*` header (rerun). |
| One IAM user, one `execute-api:Invoke` statement on `.../*/POST/v1/chat`, no managed policy, group or login profile | PASS | IAM read-only calls (rerun). |
| No `AWS::IAM::AccessKey`, no secret in CFN, repo, fixtures or logs | PASS | The one key was created by the human outside CFN (`list-access-keys`, created 17:12:10Z, after the 17:06:48Z stack update). Scan of all 436 tracked and untracked, non-ignored working-tree files, including this `audit.md`: no real API id (a positive control on the caller name hit 7 files, so the scan works), no admin IAM username, no `AKIA`/`ASIA` key id, no 40-character secret after a `secret_access_key` key. `git log --all -S<api-id>`: no hit. The Lambda logs since the deploy hold no principal or key text (rerun). |
| Outputs `ChatApiCallerUserName`, `ChatApiUrl`, `ChatApiFunctionName`, `ChatApiLogGroupName` | PASS | `describe-stacks`: exactly these four (rerun). |
| Unchanged throttle, timeout, reservation `none`, `CHAT_RUNTIME_ARN`, no access logging | PASS | Stage and Lambda reads (rerun). |
| HttpApi in place; other stacks untouched | PASS | `CreatedDate` before the update; other stacks' `LastUpdatedTime` (rerun). |
| No real API id in specs or README | PASS | Scan above (rerun). |
| Live steps only on the human's go-ahead | PASS | O7 records the human's approval of the deploy and the human-created key (reused). The auditor wrote nothing. |
| uv only; no new dependency | PASS | `pyproject.toml` and `uv.lock` unchanged vs `6d19f14` (rerun). |

### Round 1 (superseded)
| Constraint | Status | Evidence |
|---|---|---|
| One route `POST /v1/chat`, `AWS_IAM`, no `$default` | PASS | Synth template and test `test_route_is_exactly_post_v1_chat_with_no_default_route`; a mutant adding a second route fails it. (rerun) |
| No `CorsConfiguration`; knob, constant, param, attribute and output removed; old key has no effect | PASS | Code diff; template; `test_allowed_origins_context_key_is_ignored`. (rerun) |
| Exactly one IAM user, no LoginProfile, ManagedPolicyArns or group; one Allow `execute-api:Invoke` statement on `.../*/POST/v1/chat`; no `*` resource | PASS | Template inspection; mutants widening to `*`, to `execute-api:*`, or to `arn_for_execute_api("*", "/*", "*")` all fail tests. (rerun) |
| No `AWS::IAM::AccessKey`, no secret in CFN, repo, fixtures or logs | PASS | Template; AccessKey mutant fails `test_template_has_no_access_key_and_no_managed_policy`. Test fixtures use `AKIDEXAMPLE` and planted fake values only. The real API id was grepped across the tree (excluding `.venv`, `cdk.out`, `apps`, `.git`) and in git history: no hit. The smoke script never prints the secret, token or `Authorization` (probe: none on stdout). (rerun) |
| Output `ChatApiCallerUserName`; `ChatApiUrl`, `ChatApiFunctionName`, `ChatApiLogGroupName` kept | PASS | Template outputs; `cdk diff` shows only `-ChatApiAllowedOrigins`, `+ChatApiCallerUserName`. (rerun) |
| Unchanged: role statements, throttle 5/10, 28 s, reservation default 5 and `none`, `CHAT_RUNTIME_ARN`, no access logging, pinned account, region, runtime id | PASS | Template plus `cdk diff` (no change to role, policy, stage or function configuration). (rerun) |
| `src/chat_api/` not modified; record keeps its keys; nothing logged from `requestContext.authorizer` | PASS, with one note | `handler.py` and `config.py` unchanged. `src/chat_api/AGENTS.md` changed one documentation line. It is a doc file inside the constrained directory, and the plan's ownership did not list it. It is harmless, but it is copied into the Lambda image (`COPY src/chat_api/`), which feeds F3. (rerun) |
| HttpApi logical id stable; other stacks and `infra/lib/{feed_api,chat_runtime,agent_runtime}.py` untouched | PASS | `test_http_api_logical_id_is_stable` (a construct-id rename mutant fails it); empty diff. (rerun) |
| No real API id or earlier exposed URL in specs or README | PASS | grep as above; the README uses `<api-id>`, `$API_URL`, `$EXPOSED_URL`. (rerun) |
| Live steps only on the human's go-ahead | PASS | Nothing live was run by the executor (O7 evidence "not yet run"; live route still `NONE`). (rerun) |
| uv only; smoke script uses main-group `boto3`/`botocore`; no new dependency | PASS | `pyproject.toml` and `uv.lock` unchanged. (rerun) |

## Test coverage
| AC | Test | Status |
|---|---|---|
| AC1 | `tests/test_chat_api_smoke.py` (6 tests: scope, signed headers, date and content type, token header, determinism and body sensitivity, no secret in headers); handler suite `tests/test_chat_api_handler.py` | PASS (wrong-service mutant fails the scope test) |
| AC2 | `tests/test_infra_chat_api.py::test_route_is_exactly_post_v1_chat_with_no_default_route`, `::test_iam_auth_needs_no_authorizer_resource_and_one_integration_permission` | PASS (authorizer-removal mutant fails) |
| AC3 | `::test_api_has_no_cors_configuration`, `::test_allowed_origins_context_key_is_ignored`, `::test_outputs_drop_allowed_origins_and_add_caller_user_name` | PASS (CORS re-add mutant fails) |
| AC4 | `::test_exactly_one_caller_user_with_no_login_profile_or_managed_policy`, `::test_caller_has_exactly_one_statement_invoke_on_post_v1_chat_route_arn`, `::test_caller_policy_resource_is_pinned_to_the_account_and_region`, `::test_template_has_no_access_key_and_no_managed_policy` | PASS (wildcard, action-widening, wrong-account and AccessKey mutants fail) |
| AC5 | migrated role-scoped `_statements` tests, throttle, timeout and concurrency tests; `tests/test_chat_api_handler.py::test_iam_authorizer_context_is_not_logged` | PASS |
| AC6 | `::test_http_api_logical_id_is_stable`; full suite; git diff check | PASS |
| AC7 | none (manual live, `tasks.md` O7) | PASS except step 10 (F9); round 1: N/A, human-gated |

Round 2: the test files are byte-identical to round 1 (mtimes 11:21 to 11:26 local, before the round-1
audit), so the round-1 mutation results below still apply (reused).

Mutation results (round 1; scratch copies under the session scratchpad, never the working tree):

| Mutant | Result |
|---|---|
| Remove `HttpIamAuthorizer` | killed (route test) |
| Re-add CORS preflight | killed (no-CORS test) |
| Caller policy resource `*` | killed (2 tests) |
| Add `iam.AccessKey` | killed (access-key test) |
| Add caller ARN to `chat_api_request` | killed (handler regression test) |
| Log caller ARN in a separate `logger.debug` record | survives. It is an equivalent mutant: the handler's logger is pinned at INFO, so the record is never emitted. The same mutant at `logger.info` is killed. |
| Invoke scope with a wrong account literal | killed (pinned-account test) |
| Rename the `ChatHttpApi` construct id | killed (logical-id test) |
| Signer service `lambda` instead of `execute-api` | killed (scope test) |
| Action widened to `execute-api:*` | killed |
| Resource `arn_for_execute_api("*", "/*", "*")` | killed |
| A second unauthenticated route | killed (2 tests) |

The base copy ran 18 of 18 infra tests green.

### Tier Results
| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit (pytest) | `tests/test_chat_api_smoke.py`, `tests/test_chat_api_handler.py` | AC1, AC5 | Yes (root script imported through `sys.path`; no network, fake credentials, patched clock) | rerun round 2: `uv run pytest tests/ -q` -> 559 passed in 358 s (2026-10-21, run alone); ruff, `ruff --isolated` and mypy clean (run after the suite) | PASS | F5 (the import-makes-no-network check is not asserted) |
| unit (synth, `aws_cdk.assertions.Template`) | `tests/test_infra_chat_api.py` (18 tests) | AC2, AC3, AC4, AC5, AC6 | Yes (synth only; no new setup) | rerun (in the full run) | PASS | none |
| git check | `git diff --stat 6d19f14 -- ...` | AC6 | Yes | rerun round 2: only `src/chat_api/AGENTS.md` (docs), as in round 1 | PASS | none |
| manual live (e2e) | runbook in README "Authentication amendment"; results in `tasks.md` O7 | AC1, AC2, AC3, AC4, AC5, AC6, AC7 | Yes (deployed stack, the caller key in profile `ai-radar-chat-caller`, a throwaway policy-less identity created and deleted) | reused: O7, run by the agent on the human's go-ahead, 2026-10-21. Rerun by the auditor, read-only and zero-cost: stack, route, CORS, IAM, logs, metrics, three unsigned curls. Not run: step 10 (signed `GET /v1/chat`, signed `POST /v1/other`); the expired-signature probe was dropped by human decision | PARTIAL | F9 (step 10 not run), F10 (results not in the README), F11 (O7 unchecked) |

Round 1 note: the first full-suite run had 1 failure (`test_reserved_concurrency_is_set_by_default`:
`ENOENT ... .mypy_cache/3.12/cache.2.db-shm` during the Docker asset fingerprint). The
auditor caused it by running `mypy .` at the same time. A clean rerun passed 559 of 559. This
is not a defect, but the fingerprint walking `.mypy_cache` shows the build context is not fully
ignored (see F3). In round 2 the suite ran alone and passed on the first run.

## Findings
| Id | Severity | Finding (citation) | Closure condition | Status |
|---|---|---|---|---|
| F1 | MEDIUM | AC2 ("bad or expired signature") and plan AC7 step 9: the runbook and `run_chat_api_smoke.py` give no way to send an expired or replayed signature. The plan suggested a clock offset or replay; only `--unsigned` and `--tamper` exist, and README verify step 4 omits the expired probe. | The runbook names a concrete expired-signature probe (for example a clock-offset option on the script, or a replay of headers signed more than 5 minutes earlier), and AC7 records its result. Otherwise the human explicitly accepts `--tamper` as the only bad-signature probe. | Resolved (round 2): the human accepted `--tamper` (tasks Finding responses). Plan Revision 2 and README verify step 4 state it, and O7 records `--tamper` -> 403. The intent AC2 text still says "expired"; the documentation step may want to note the acceptance. |
| F2 | MEDIUM | AC3 live residual: the README verify list has no post-deploy check that CORS is actually gone. `cdk diff` removes `CorsConfiguration` by property removal. Whether the live API drops it is unverified, and if it lingers, API Gateway keeps answering preflights with `access-control-*` headers, against AC3's example. | Add to the runbook, and record in O7: `aws apigatewayv2 get-api` shows no `CorsConfiguration`, and an `OPTIONS` preflight with an `Origin` header returns no `access-control-*` header. | Resolved (round 2): README verify step 5 and plan step 10b. O7 records it, and the auditor reran both checks: `CorsConfiguration` null, and the preflight gives 404 with no `access-control-*` header. |
| F3 | LOW | Plan Consumers ("Lambda unchanged") and AC6 (`cdk diff` expectation): the real `cdk diff` also shows `[~] AWS::Lambda::Function` `Code.ImageUri` (asset hash `842932af...` -> `e02d4a19...`). Causes: the repo-root build context includes the new `run_chat_api_smoke.py` and the edited `src/chat_api/AGENTS.md` (copied into the image), and `.dockerignore` does not exclude caches such as `.mypy_cache`. This is an in-place code update, not a replacement, and `handler.py` is unchanged. But the deploy will rebuild and push the image (Docker needed), and the README's "Api and Route modified" diff guidance does not mention it. The `.dockerignore` breadth predates this change. | The README diff step names the expected Lambda image change, or the human accepts it at the diff review. | Resolved (round 2): README lines 1133-1136 and plan step 2. O7 records the in-place `Code.ImageUri` change in the pre-deploy diff. The `.dockerignore` breadth remains pre-existing debt (a note). |
| F4 | LOW | Plan Consumers and migration (README steps 2, 4, 5, 7, 8): the new subsection marks only the CORS step 6 and the "no authorizer"/CORS wording as superseded. After deploy, the older step 2 still passes the dead `-c chat_api_allowed_origins`, and steps 4, 5 and 8 and the F11 closure re-run (a burst that must reach the Lambda) use unsigned `curl` and would get 403. The smoke script sends only `{"question"}`, so there is no signed bad-body or signed burst tool. `src/chat_api/AGENTS.md` line 5 still says "the stage throttle ... is the cost guard". Deferred to the documentation step by instruction. The new subsection does not overclaim. | The documentation step marks those steps superseded or rewrites them with signed calls, and redefines how F11's burst re-check runs under IAM auth. | Open (deferred to the documentation step; not counted against the implementation). Since the deploy, these texts are wrong about the live system: README lines 907, 1095, 1103, 1108 ("unauthenticated and protected only by throttling"), 1175, 1180, 1191-1192, 1237 and 1321; `CLAUDE.md` line 98; `specs/current/chat-api.md` (CAPI-4, ADR 0027 row); `specs/current/_index.md` lines 107, 155 and 258; `CHANGELOG.md` line 43. They should be fixed before merge. |
| F5 | LOW | § Validation AC1 names "Importing the script makes no network or STS call". No test asserts it. The auditor's reading: the import is side-effect free (all calls are inside `main`). | Add the assertion, or accept the reading. | Open |
| F6 | LOW | harny-feedback: no evidence that the per-turn hook fired for this change (no `.turns` record survives), and no CI run exists because the branch is unpushed. The auditor reran ruff, `ruff --isolated` and mypy at the caller's request: all clean (rerun). | CI `harny-feedback.yml` green on the pushed branch. | Open (round 2: still unpushed, `HEAD` is `6d19f14`, no CI run; ruff, `ruff --isolated` and mypy clean, rerun) |
| F7 | LOW | The manual live tier (AC7) was not run by the auditor or executor: human-gated by design. | The O7 evidence is recorded with every probe's status and the Lambda `Invocations` deltas. | Resolved (round 2): O7 records every probe's status and the `Invocations` reading; the one unrun step is F9. |
| F8 | LOW | Intent Constraints (key handling): README verify step 2 passes `AWS_SECRET_ACCESS_KEY=...` inline on the command line, which lands in shell history. That is the same exposure the plan cited to reject `curl --aws-sigv4`. The script already supports `AWS_PROFILE_NAME` (an explicit profile, which also overrides any ambient env credentials). | The runbook recommends a dedicated named profile, or an exported variable read without echo, instead of the inline secret. | Resolved (round 2): README verify step 2 and plan step 7 use the named profile `ai-radar-chat-caller` entered at the `aws configure` prompt. O7 used it. The working-tree scan finds no secret. |
| F9 | LOW | AC2 (last sentence: "a signed request to a method or path that is not routed is rejected at routing (404) ... without invoking the Lambda") and plan AC7 step 10: the signed `GET /v1/chat` and signed `POST /v1/other` were not run (O7 "NOT run"). Assessment: immaterial to the protective property. The live API has one route, no `$default` route and no other integration, so an unrouted request has nothing to invoke. Live unsigned `GET /v1/chat` and `OPTIONS` return 404, not 403, which shows that routing is evaluated before IAM authorization, so a signature cannot change the outcome. `Invocations` stayed at 1 throughout. The literal "signed" status is unobserved, and the smoke script has no flag to sign another method or path. | Run the two signed probes (this needs a method or path option on the script, or a one-off botocore call), or the human accepts the unsigned 404 evidence for this sub-case. | Open (recommend human acceptance) |
| F10 | MEDIUM | Plan AC7 row ("Evidence ... is recorded in `tasks.md` O7 and the README") and intent AC7 ("the runbook and its recorded results are part of the deliverable"): the README "Authentication amendment" subsection is still headed "implemented, not yet deployed" and says "every live step below is NOT YET RUN" and "the deployed stack still behaves as described above". It records none of the O7 results. It does not overclaim; it now understates, and it is stale. The results exist only in `tasks.md` O7. | The documentation step updates the subsection status (deployed 2026-10-21, live-verified except step 10) and records the O7 results there, without the API id, URL or any key material. | Open (documentation step) |
| F11 | LOW | harny-audit outcome completion (`tasks.md`): O7 is still `[ ]` although its evidence is recorded, and a stale "Evidence: not yet run" line sits under that evidence. O9 says "`audit.md` does not exist". The Working state and Checkpoint ("Next step: audit, then human-gated live verification O7") predate the deploy. | O7 is marked `[x]`, or `[!]` with the F9 exception explained. The stale lines are removed or updated, and O9 points to this audit. | Open |

Notes (not findings):
- The script uses `AWS_PROFILE_NAME` rather than the plan's `AWS_PROFILE`. This is a compliant alternative: an explicit profile makes botocore drop the env provider, so an ambient key cannot sign by accident. `AWS_PROFILE` also still works through the default chain.
- The script exits 0 for any HTTP status, and a non-HTTP `URLError` (DNS or connect) shows as a traceback that contains no headers. This is acceptable for a developer probe.
- `specs/archived/chat-agent-runtime/.sdd/feedback/.turns/` is an untracked stray directory of hook turn files dated 2026-10-14 and 2026-10-18. It is unrelated to this spec and should not be committed. (Still present in round 2.)
- Round 2: the caller key is `Active`, and it is the only long-lived credential for this route. Until the `apps/web` signing spec ships, it lives only in the local profile `ai-radar-chat-caller`. If it is not needed until then, the human can set it `Inactive` (the README rotation and suspected-leak steps apply).
- Round 2, chat-api's own open reservations carried over, out of this spec's scope: chat-api F11 (the shared 10-slot account Lambda concurrency pool; `AiRadarChatApi` is still deployed with no reserved concurrency) and chat-api F13 (best-effort throttling). Authentication now stops unsigned floods before the Lambda (live: rejected requests do not move `Invocations`), which narrows chat-api F11's exposure to the holder of the caller key. The chat-api F11 closure re-run is an unsigned burst that now gets 403 at the gateway, so it must be redefined (F4).

Plan-flagged limits, assessed:
- **Admins can also call.** This is inherent to HTTP APIs, which have no resource policy, and intent revision 2 records it. The auditor saw no project role with a managed policy. The project roles' inline grants are scoped and none grants `execute-api`, but `iam:*`/`*` users (the human's admin user) can call the route. The AC7 "other identity" probe must use a policy-less identity, or it will wrongly show 200. Acceptable; tightening it would mean a REST API with a resource policy (a later spec). Round 2: O7 used a policy-less throwaway user, as required, and it is deleted.
- **404 for unrouted.** With no `$default` route, HTTP API routing rejects the request before authorization, and the Lambda is not invoked. This was live-observed pre-auth (README step 7). The README's auth-model bullet states "Unrouted methods and paths are 404" as fact, while its verify step 4 says "likely". This is minor until O7 records it. Round 2: post-deploy unsigned `GET /v1/chat` and `OPTIONS` gave 404, so the bullet now holds for unsigned requests (signed: F9).

## Audit log
| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-21 | APPROVED WITH RESERVATIONS | Offline scope only. 559 passed (rerun), ruff, `ruff --isolated` and mypy clean (rerun). Synth inspected, read-only `cdk diff` against the live stack. 12 of 13 mutants killed; the survivor is equivalent. AC7 human-gated and not run. |
| 2 | 2026-10-21 | APPROVED WITH RESERVATIONS | Docs-only changes since round 1 (README, plan, tasks). Live deploy and O7 corroborated read-only: route `AWS_IAM`, CORS null, one least-privilege caller with one human-created key, throwaway identity deleted, one Lambda invocation (the signed 200) with a seven-key record. Three unsigned probes rerun: 403, 404 with no CORS headers, 403. 559 passed (rerun alone), ruff, `ruff --isolated` and mypy clean. F1, F2, F3, F7 and F8 resolved. New: F9 (signed unrouted probes not run, immaterial), F10 (README subsection stale, no recorded results), F11 (`tasks.md` O7 unchecked and stale lines). |

## Final verdict

APPROVED WITH RESERVATIONS

**Summary**: The deployed change does what the intent asks. Live, the one route is `AWS_IAM` and CORS is gone. Unsigned, tampered, fabricated and wrong-identity requests get 403 without reaching the Lambda, the dedicated caller gets a grounded 200, and nothing about the caller is logged. The API was updated in place and no other stack moved. The reservations are about records, not behavior: two signed unrouted probes were not run, and the README, `tasks.md` and the older "unauthenticated" docs do not yet reflect the deploy.

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- F10: the README "Authentication amendment" subsection still says not deployed and records no results (documentation step).
- F4: the older README steps, `CLAUDE.md`, `specs/current/chat-api.md`, `_index.md` and `CHANGELOG.md` now describe the live API wrongly as unauthenticated with CORS. This is the documentation step's job and should be fixed before merge.

**Recommendations** (nice to have):
- F9: the human accepts the unsigned 404 evidence for the signed-unrouted sub-case, or runs it with a one-off signed call.
- F11: check O7 (`[x]`, or `[!]` with the F9 exception) and update O9 and the Working state in `tasks.md`.
- F5 (import side-effect assertion), F6 (push the branch so `harny-feedback.yml` runs).

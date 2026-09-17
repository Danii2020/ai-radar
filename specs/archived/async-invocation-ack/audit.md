# Audit: async-invocation-ack

Scope: the entrypoint change in `runtime_app.py` and its offline tests, plus
the real-AWS re-verification that closes
[`specs/eventbridge-schedule/audit.md`](../eventbridge-schedule/audit.md)
finding **F5**. Rows marked **(manual)** cannot be discharged by `pytest` —
they require a real deploy and a real Scheduler fire, and must be evidenced
with CloudWatch / CloudWatch-metrics / DynamoDB / SQS output, not prose.

> **Audit pass 1 (2026-08-10, sdd-auditor) covered Phases 1–3 only.** Retained
> for the record; its statement that Phase 4 "has not been run" is **no longer
> true** — see the header note below.

> **Audit pass 2 (2026-08-10, sdd-auditor) — Phase 4 executed and
> independently re-verified against live AWS.** `tasks.md` Tasks 4.1–4.3 and
> 4.6–4.8 are now `[x]` with evidence; Tasks 4.4 and 4.5 remain honestly
> unchecked (not performed). Every **(manual)** row below has been re-derived
> by the auditor from live AWS API calls — `aws cloudwatch get-metric-data`,
> `aws logs filter-log-events`, `aws dynamodb scan`, `aws sqs
> get-queue-attributes`, `aws scheduler get-schedule`, `aws ecr
> describe-images`, `aws cloudformation describe-stack-events` — **not** from
> `tasks.md`'s prose. Where a claim could not be re-derived it is marked as
> such rather than rounded up.

## Requirements Checklist

| ID | Requirement | Source | Status | Notes |
|---|---|---|---|---|
| R1 | `handler` returns an ack (`{"status": "accepted", "run_id": …}`) without waiting for the pipeline; sub-second, independent of run duration | intent.md Goal 1 | **PASS** | `runtime_app.py:177-207` does only uuid + `add_async_task` + `create_task` + one log line — no network I/O, no `await` on the pipeline. Auditor E2E through the **real SDK dispatch path** (Starlette `TestClient` on `runtime_app.app`, pipeline stubbed to a 3 s blocking sleep): `POST /invocations` → `200 {"status":"accepted","run_id":"8c8336dc…"}` in **0.002 s**, SDK logged `Invocation completed successfully (0.001s)`. Compare F5's live 33.044 s / 24.893 s. ~4 orders of magnitude inside the ~30 s Scheduler ceiling. Offline test T2 independently asserts < 1 s. |
| R2 | Every accepted invocation still runs the **unchanged** compiled graph to completion, in a background task | intent.md Goal 2 | **PASS** | `_run_curation_pipeline()` (`runtime_app.py:104-128`) is Spec 04's handler body **verbatim** — confirmed line-by-line from `git diff -- runtime_app.py`: the `_build_store()` / `_build_discoverer()` / `build_graph(store, discoverer)` / `.invoke({"max_items": config.MAX_ITEMS})` / eight-field-summary lines appear as unchanged diff context, only the enclosing `def` and docstring changed. T3 asserts `invoke_calls == [{"max_items": 42}]` after draining. E2E: one `POST` → exactly one pipeline invocation and one `curation_run_complete` record. `graph.invoke` (sync), **not** `ainvoke` — Spec 01 semantics identical. |
| R3 | The async task is registered via `app.add_async_task(...)` **before** the handler returns, and completed exactly once (success or failure) | intent.md Goal 2, Success Criteria 3 | **PASS** | `runtime_app.py:193` — `add_async_task` is the **third statement** of the accepted path, before `asyncio.create_task` (`:196`) and before `return` (`:207`); it is **not** inside `_curation_run`. `complete_async_task` appears exactly once, in `_curation_run`'s `finally` (`:172`), plus the compensating call on the unreachable `create_task`-failure path (`:199`, mutually exclusive with the coroutine ever running). E2E: `GET /ping` **immediately after** the ack returned `HealthyBusy` while the pipeline thread was still blocked — only possible if registration happened synchronously inside `handler`. No ping-status race window. |
| R4 | All eight Spec 04 summary counts are emitted in a `curation_run_complete` JSON log record carrying the same `run_id` as the ack | intent.md Goal 3 | **PASS** | `runtime_app.py:161-170`. E2E record, verbatim: `{"event": "curation_run_complete", "run_id": "8c8336dc03c145cb8a245a5e8eaa6737", "duration_s": 3.0, "discovered": 50, "deduped": 42, "summarized": 8, "failed": 0, "persisted": 8, "discoverer_failures": 0, "store_failures": 0, "tavily_enabled": true}` — all eight counts, matching `run_id`, `duration_s` as a 1-decimal float. T8 asserts every field. Bonus: the SDK formatter stamps the originating `requestId` on the record too (contextvars inherited by the task), giving a second correlation key. |
| R5 | A second invocation during an in-flight run returns `already_running` with the in-flight `run_id`, HTTP 200, and starts no pipeline | intent.md Goal 4 | **PASS** | `runtime_app.py:188-189`. Check-and-set (`:188` → `:192`) has no `await` between them and both the handler and `_curation_run`'s release run on the SDK's single worker loop, so the guard is atomic without a lock (SDK `_ensure_worker_loop`/`_run_worker_loop` verified in the installed 1.18.1 source). E2E: 2nd `POST` mid-run → `200 {"status":"already_running","run_id":"8c8336dc…"}` (run 1's id) in 0.000 s, `pipeline invocations: 1`. T6 asserts the same offline. |
| R6 | `payload` remains ignored — all config env-driven; no sync-mode escape hatch by payload or env | intent.md Goal 5 | **PASS** | `payload` is never read in `handler`'s body. `app._takes_context(handler)` → `False` (verified in-process), so the SDK passes only `payload`. T11 asserts identical ack keys and identical `build_graph().invoke()` input for `{}` vs `{"unexpected": …, "nested": {…}}`. No env flag exists. (The SDK's `_agent_core_app_action` intercept is gated on `self.debug`, which is `False` in production — pre-existing Spec 04 behavior, unchanged.) |
| R7 | `src/**`, `infra/**`, `Dockerfile`, `.dockerignore`, `pyproject.toml`, `uv.lock` are unchanged; no new dependency | intent.md Goal 5, Success Criteria 8 | **PASS** | `git diff --stat -- src/ infra/ pyproject.toml uv.lock Dockerfile .dockerignore` → only `infra/app.py` (9+/5-), and that diff is **100 % `eventbridge-schedule` work** (adds `CurationScheduleStack` import + instantiation and rewrites the module docstring for Specs 03–05) — nothing async-related. `git status --porcelain -- src/ Dockerfile .dockerignore pyproject.toml uv.lock` → **empty**. Only stdlib added (`asyncio`, `json`, `logging`, `time`, `uuid`). `pytest-asyncio` absent from `pyproject.toml` and `uv.lock`. Production diff for this spec is confined to `runtime_app.py`. |
| R8 | Plane A only; `bedrock_agentcore` + `asyncio` + Secrets Manager `boto3` confined to `runtime_app.py`; no new domain layer/interface | intent.md Constraints; docs/architecture-principles.md §1, §5 | **PASS** | `grep -rn "bedrock_agentcore\|import asyncio" src/` → **no matches**. The only `boto3` imports under `src/` are the pre-existing DynamoDB client (`src/curation/dynamo.py:14`) and Bedrock client (`src/spike/bedrock.py:8`) — the *Secrets Manager* client stays lazily imported inside `runtime_app._resolve_tavily_key`. No Plane B (`spike.chat` / `spike.retrieval`) import. No new dataclass, protocol, aggregate, repository, or domain event. `run_curation.py` / `run_spike.py` / `run_chat.py` do not import `runtime_app` (grepped) and stay synchronous. |
| R9 | Pipeline failure is logged with a stack trace, releases the async task and the guard, never becomes a 5xx, and leaves the process able to accept the next invocation | intent.md Success Criteria 5 | **PASS** | `runtime_app.py:148-158` (`except Exception` → `logger.exception`) + `:171-173` (`finally`). Auditor E2E with a raising pipeline: ack was `200`; the failure surfaced as an **ERROR** record `{"event":"curation_run_failed","run_id":"a789a245…","duration_s":0.3}` with the SDK formatter attaching `errorType: RuntimeError`, `errorMessage`, and a full `stackTrace` array; then `ping → Healthy`, `_active_run_id → None`, `active_count → 0`, and the **next** `POST` returned `200 {"status":"accepted", …}` and ran to completion. Nothing propagated to HTTP. T7/T9 assert the same offline. |
| R10 | README documents the new two-step verification (ack → CloudWatch record + DynamoDB count) and the changed `agentcore invoke '{}'` semantics | intent.md Goal 6 | **PASS** (was **FAIL** in pass 1) | Closed by the 2026-08-10 audit-fix pass (finding **A1**), and re-verified here against the file rather than the changelog. `README.md:145-176` now opens with an explicit callout — "Since `async-invocation-ack`, `agentcore invoke '{}'` no longer returns [the counts]" — gives the ack shape (`# {"status": "accepted", "run_id": "9f2c1b7e4a..."}`, `:160`), and documents the two-step verify: find the matching `curation_run_complete` record joined by `run_id` (`:165-166`), then check the DynamoDB count. The old counts-in-response text survives only as a dated, explicitly-superseded historical note (`:177`). Auditor re-grepped `README.md`: `accepted`, `already_running`, `curation_run_complete`, `run_id`, and `async-invocation-ack` are all now present (pass 1 found **no matches** for any of them). The requirement as written is met, and it demonstrably served its purpose — this text is the procedure the operator followed during Phase 4. ⚠️ Two documentation residuals remain and have now flipped from *absent* to *stale* — see new finding **A8**: `README.md:189-190` still says the re-verification is "not yet run against a redeployed" agent (false since `22:26Z` today), and the spec table (`README.md:16-23`) still has **no `async-invocation-ack` row**, so a reader of the table alone would not know this spec exists. |
| R11 | **(manual)** Redeployed agent: `agentcore invoke '{}'` returns the ack fast and a matching `curation_run_complete` record appears afterwards; card count moves by one slice | intent.md Goal 7 | **PASS (live-verified 2026-08-10)** | Re-derived from live AWS, not from `tasks.md`. **(a) The fixed image really is deployed** — `aws ecr describe-images --repository-name bedrock-agentcore-ai_radar_curation` → newest image `20260810-221147-104` pushed `2026-08-10T22:12:11Z` (previous image `20260806-024136-838`, four days older). Every check below post-dates that push, so none of it is measuring the old synchronous build. **(b) Ack + deferred completion** — `aws logs filter-log-events` on `/aws/bedrock-agentcore/runtimes/ai_radar_curation-sIf5Dw979w-DEFAULT` returns the pair, quoted verbatim: `{"event": "curation_run_accepted", "run_id": "16f3c77a5b0a426e93d63f35c40cefb2"}` at `22:12:29.516Z` and `{"event": "curation_run_complete", "run_id": "16f3c77a5b0a426e93d63f35c40cefb2", "duration_s": 36.5, "discovered": 50, "deduped": 33, "summarized": 8, "failed": 0, "persisted": 8, "discoverer_failures": 0, "store_failures": 0, "tavily_enabled": true}` at `22:13:05.993Z` — same `run_id`, same `requestId` `686e6978-…`, 36.5 s apart. **This run took 36.5 s, comfortably past Scheduler's ~30 s universal-target ceiling** — precisely the case that produced F5, now survivable because the caller no longer waits. **(c) Card count +1 slice** — the auditor's `created_at` histogram (see R12) attributes exactly **8** cards to `2026-08-10T22:13`. Not re-derived: the 6.7 s wall-clock of the `agentcore invoke` CLI round-trip (`tasks.md` Task 4.3) — the auditor did not re-invoke, so ack latency at the HTTP layer rests on the log-timestamp gap plus pass 1's 0.002 s in-process measurement. |
| R12 | **(manual)** One Scheduler fire ⇒ **exactly one** curation run; `InvocationAttemptCount = 1`, `TargetErrorCount` no datapoint, DLQ depth 0, card count +1 slice (not 2) | intent.md Goal 7, Success Criteria (final) | **PASS (live-verified 2026-08-10) — F5 CLOSED** | All four legs re-derived by the auditor against live AWS. **(1) Metrics.** `aws cloudwatch get-metric-data` over `AWS/Scheduler`, `Period=60`, `Stat=Sum`, window `2026-08-10T22:17:00Z`–`22:32:00Z`: `InvocationAttemptCount` → **one** datapoint, `22:26:00Z = 1.0`; `TargetErrorCount` → `Timestamps: []`, `Values: []` (**zero datapoints**, `StatusCode: Complete` — genuinely queried and absent, not "not queried"); `InvocationsSentToDeadLetterCount` → **zero datapoints**; `InvocationDroppedCount` → **zero datapoints**. Direct contrast, identical query shape, re-run by the auditor over the original F5 window `21:00:00Z`–`21:20:00Z`: `InvocationAttemptCount` = 1.0 @ 21:08 **and** 1.0 @ 21:09; `TargetErrorCount` = 1.0 @ 21:08 **and** 1.0 @ 21:09. Two attempts + two target errors then; one attempt + zero target errors now. **(2) Exactly one run.** `aws logs filter-log-events --filter-pattern '"curation_run_"'` over `22:17:00Z`–`22:32:00Z` returns exactly **two** events and no more: `curation_run_accepted` `22:26:14.740Z` and `curation_run_complete` `22:26:39.282Z` (`duration_s: 24.5`, `persisted: 8`, all eight counts present), both `run_id 3fbc705092294d2c9e7abb0f00e5634a`, both `"sessionId": "ai-radar-scheduled-curation-run-id-9a6a7a4e-181f-4892-a1ac-c6120a3f1fca"` — Spec 05's `SESSION_ID_PREFIX` with `<aws.scheduler.execution-id>` substituted, i.e. genuinely Scheduler-driven and not a stray human invoke. Re-run open-ended (start `22:17:00Z`, no end bound) at `22:35:33Z`: still **2** events. **(3) Card count +1 slice.** `aws dynamodb scan --table-name ai-radar-cards --select COUNT` → **56**. Full auditor-derived `created_at` histogram: `2026-07-28T14:59` ×16, `2026-08-06T02:43` ×8, `2026-08-10T21:08` ×8, `2026-08-10T21:09` ×8, `2026-08-10T22:13` ×8, `2026-08-10T22:26` ×8 = 56. This reconciles `tasks.md`'s 40 → 48 → 56 progression **exactly**, and is stronger evidence than a bare delta: the scheduled fire contributed **one** 8-card bucket at 22:26, not two. (The 21:08 + 21:09 adjacent pair is the F5 double-run, preserved in the table as its own fossil record — the visual contrast is the finding.) **(4) DLQ.** `aws sqs get-queue-attributes` on `ai-radar-schedule-dlq` → `ApproximateNumberOfMessages "0"`, `…NotVisible "0"`, `…Delayed "0"`. ⚠️ **Observation window, stated without rounding up:** the fire was `22:26:14Z`, the return-to-inert deploy completed `22:30:47Z`, and the auditor's last poll was `22:35:33Z` — a **~9-minute** post-fire window, **not** the full 2 h `MaximumEventAgeInSeconds` that pass 1's evidence-discipline recommendation asked for. That window is ~9× the 61 s retry interval actually observed during the F5 incident, and the decisive evidence here is causal rather than temporal: Scheduler recorded **no target error**, so there was no failed attempt for it to retry. |
| R13 | **(manual)** Schedule returned to `DISABLED` after the live fire, verified via `aws scheduler get-schedule` | roadmap.md Phase 4.7 | **PASS (live-verified 2026-08-10)** | Auditor ran `aws scheduler get-schedule --name AiRadarSchedule-CurationScheduleDailyCurationC0D0D-MLU9P87R88I1` at `22:35Z`: `State: DISABLED`, `ScheduleExpression: "cron(0 6 * * ? *)"`, `ScheduleExpressionTimezone: "Etc/UTC"` — the one-shot `cron(18 22 10 08 ? 2026)` override is gone. Every Spec 05 delivery property survived the arm/disarm round trip untouched: `FlexibleTimeWindow {FLEXIBLE, 15}`, `RetryPolicy {MaximumRetryAttempts: 3, MaximumEventAgeInSeconds: 7200}`, `DeadLetterConfig` → `ai-radar-schedule-dlq`, `Target.Arn` `…aws-sdk:bedrockagentcore:invokeAgentRuntime`, PascalCase `Input` with plain `"Payload":"{}"`, plus the pinned `Description` — so Contract item C14 ("no `infra/` change") holds against the deployed artifact, not just against `cdk diff`. `aws cloudformation describe-stack-events AiRadarSchedule` confirms the ordering: arm `UPDATE_IN_PROGRESS 22:13:43Z → UPDATE_COMPLETE 22:13:51Z`; fire `22:26:14Z`; return-to-inert `UPDATE_IN_PROGRESS 22:30:39Z → UPDATE_COMPLETE 22:30:47Z`. **Materially better than the F5 session**, where the disarm landed `21:09:41Z` *mid-retry-sequence* and could not be distinguished from a mitigation; here the disarm came 4.5 min **after** a completed, error-free delivery, so it cannot be credited with suppressing anything. |
| R14 | F5 marked resolved in `specs/eventbridge-schedule/audit.md` with a pointer to this spec's evidence | roadmap.md Phase 4.8 | **PASS (done in this pass)** | Executed in the correct order — *after* R12's evidence existed, never before. `specs/eventbridge-schedule/audit.md` now carries a dated `2026-08-10` / `sdd-auditor` Audit Log entry marking **F5 RESOLVED**, naming `specs/async-invocation-ack/` as the fix and citing all four evidence legs (`InvocationAttemptCount = 1`, zero `TargetErrorCount` datapoints, one `curation_run_complete` record, clean 8-card delta, DLQ 0); its Final Verdict's "Blocking for going live" section was rewritten so F5 is no longer presented as an open blocker; the F5 row's severity cell now reads `HIGH → RESOLVED` with the original "do not enable" recommendation retained beneath it for the record; and the two rows that carried a ⚠️ F5 qualifier (R7 and T16) now note the qualifier no longer applies. **Deliberately left unchanged**: that file's R12/T17 double-fire dedup rows, which stay **PARTIAL** — this fire delivered only once, so it adds nothing to the un-run dedup drill. Also **deliberately left unchanged**: that file's recommendation on whether to actually switch the daily cadence on. F5 being fixed removes the *technical* objection; the go/no-go remains a human cost/ops decision. |

## Contract Compliance

| ID | Contract Item | Status | Verified By |
|---|---|---|---|
| C1 | `async def handler(payload) -> dict` — single ignored `payload` param, no `context` param added | **PASS** | `runtime_app.py:176-177`. In-process: `inspect.signature(app.handlers["main"])` → `(payload) -> 'dict'`; `_is_async_callable(...)` → `True` (so the SDK routes it to the dedicated worker loop, not the threadpool); `app._takes_context(...)` → `False`. `@app.entrypoint` returns the function unwrapped (SDK `entrypoint`, `app.py:216-228`), so `app.handlers["main"] is runtime_app.handler`. |
| C2 | Ack shapes exactly `{"status": "accepted"\|"already_running", "run_id": <32-hex>}`; HTTP 200 in both cases | **PASS** | `runtime_app.py:189, 207`. T1 asserts `len(run_id) == 32`, all chars in `0123456789abcdef`, and that **none** of the eight Spec 04 count keys appear. E2E: both shapes returned with HTTP **200** through the real `_handle_invocation` path (dict → `Response(json, media_type="application/json")`, SDK `app.py:594-597`). |
| C3 | `_run_curation_pipeline() -> dict` is Spec 04's handler body verbatim (store, discoverer, unchanged graph, `max_items=config.MAX_ITEMS`, eight-field summary) | **PASS** | `git diff -- runtime_app.py` shows the entire body as unchanged context lines; only the `def` line and docstring are `+`/`-`. T12 exercises `_run_curation_pipeline()` alone (no event loop) and asserts the exact eight-field dict plus `invoke_calls == [{"max_items": 42}]`. |
| C4 | `_curation_run(run_id, task_id)` runs the pipeline via `asyncio.to_thread` (never on the loop) | **PASS** | `runtime_app.py:147`. E2E proof that the loop is genuinely free: with a 3 s blocking pipeline in flight, three successive `GET /ping` calls returned in **0.3 ms / 2.8 ms / 3.0 ms** — the loop was never starved. This closes roadmap Risk row 3 offline. |
| C5 | `_background_tasks` module-level strong-ref set, with `add_done_callback(_background_tasks.discard)` | **PASS** | `runtime_app.py:52` (declaration + the "asyncio holds only a weak reference" comment), `:202-203`. T10 asserts `len(...) == 1` in flight and `== 0` after completion. E2E: `_background_tasks: set()` after the run. |
| C6 | `_active_run_id` single-flight guard; mutated only on the worker loop; cleared in `_curation_run`'s `finally` | **PASS** | `runtime_app.py:57, 188, 192, 198, 173`. Both mutation sites (`handler`, `_curation_run`) execute on the SDK's single `agentcore-worker-loop` thread — verified against installed `bedrock_agentcore/runtime/app.py:674-714` (daemon thread, `loop.run_forever()`) and `:820-823` (`run_coroutine_threadsafe` onto that loop). Cleared in `finally`, so a crash cannot wedge the process (T7 asserts recovery). ⚠️ One ordering nit — see finding **A4**. |
| C7 | `app.complete_async_task(task_id)` called exactly once per accepted run, in `finally` | **PASS** | `runtime_app.py:172`. The only other call site (`:199`) is on the `create_task`-failed path where the coroutine never runs, so the two are mutually exclusive. E2E logs show exactly one `Async task started` / `Async task completed` pair per accepted run, on both the success and failure paths. |
| C8 | `get_current_ping_status()` is `HEALTHY_BUSY` from before the ack until the run ends, then `HEALTHY` | **PASS** | T4 (`HEALTHY_BUSY` at return time, pipeline still blocked) + T5 (`HEALTHY` and `active_count == 0` after drain). E2E over real HTTP: `HealthyBusy` at ack+0 ms and throughout the 3 s run; `Healthy` afterwards. SDK derivation confirmed at `app.py:310` (`HEALTHY_BUSY if self._active_tasks else HEALTHY`). |
| C9 | `_curation_run` never re-raises; failures logged as `curation_run_failed` via `logger.exception` | **PASS** | `runtime_app.py:148-158` — bare `except Exception` with no `raise`. T9 asserts `record.exc_info is not None` and that the original message is attached. E2E confirmed the record carries a real `stackTrace`. `BaseException`/`CancelledError` is deliberately not swallowed (correct — a cancelled task should unwind). ⚠️ Narrow gap — see finding **A5**. |
| C10 | Log records use the pinned shapes/keys: `curation_run_accepted`, `curation_run_complete` (8 counts + `run_id` + `duration_s`), `curation_run_failed` | **PASS (one record untested)** | All three implemented at `runtime_app.py:205`, `:161-170`, `:150-158`; all three observed verbatim in the auditor's E2E run with the pinned keys and `duration_s` rounded to 1 decimal. `curation_run_complete` (T8) and `curation_run_failed` (T9) are asserted by tests; **`curation_run_accepted` has no test** — see finding **A3**. |
| C11 | Logger is `logging.getLogger("bedrock_agentcore.app.curation")` — inherits the SDK logger's handler/level; no `basicConfig` | **PASS** | `runtime_app.py:47` with the explanatory comment. In-process: `logger.getEffectiveLevel() == 20` (INFO), `logger.propagate is True`, parent `bedrock_agentcore.app` carries the SDK's `StreamHandler` (SDK `app.py:202-208`). No `basicConfig` call anywhere in `runtime_app.py`. E2E confirms records reach stderr through the SDK's `RequestContextFormatter` (JSON, with `requestId`). |
| C12 | If `asyncio.create_task` raises: guard cleared, async task completed, exception propagates (genuine 5xx) | **PASS (implementation), UNTESTED** | `runtime_app.py:195-200` — exactly the pinned unwind order, then a bare `raise`. No test exercises this branch (it is not in the T1–T12 plan either). Practically unreachable on the SDK worker loop. See finding **A3**. |
| C13 | `_resolve_tavily_key` / `_build_store` / `_build_discoverer` / `app.run()` unchanged from Spec 04 | **PASS** | `git diff -- runtime_app.py` shows zero hunks touching `runtime_app.py:60-101` or `:210-211`. Inherited tests I2/I3/I4 and both F2 sentinel regressions still exercise the real implementations and pass. |
| C14 | No `infra/` change — `cdk diff` on `AiRadarRuntimeRole`, `AiRadarSchedule`, `CardStoreStack` is empty | **PASS** | Auditor ran `uv run --group infra cdk diff --app "python infra/app.py"` against live AWS: `Stack AiRadarCardStore → There were no differences`; `Stack AiRadarRuntimeRole → There were no differences`; `Stack AiRadarSchedule → There were no differences`; `✨ Number of stacks with differences: 0`. `MaximumRetryAttempts = 3`, the 15-min flexible window, the 2 h max event age and the DLQ are all untouched (Behavior Guarantee 10). |
| C15 | Suite stays 100 % offline and plugin-free (no `pytest-asyncio`); tests drive their own event loop and drain `_background_tasks` | **PASS** | `tests/test_runtime_app.py:265-293` — `loop` fixture (`asyncio.new_event_loop()`), `_call_handler` (`run_until_complete`), `_drain` (`asyncio.gather(*_background_tasks)`); zero `sleep`-as-synchronization (the blocking stub uses a `threading.Event` with a 5 s deadlock guard). Plugins loaded: `langsmith`, `anyio`, `typeguard` — **no `pytest-asyncio`** (also absent from `pyproject.toml`/`uv.lock`). Offline proven independently: with `HTTP_PROXY=HTTPS_PROXY=http://127.0.0.1:9` (black hole) + `AWS_EC2_METADATA_DISABLED=true`, `tests/test_runtime_app.py` → **23 passed in 0.13 s**. |

### Inherited Spec 04 coverage that must survive the test rewrite

| ID | Spec 04 item | Status | Notes |
|---|---|---|---|
| I1 | T2 — handler ignores `payload` | **PASS** | `test_handler_ignores_payload_argument_producing_identical_ack_shape_and_graph_input` — re-expressed against the async handler; asserts identical ack keys *and* identical graph input across two payloads. |
| I2 | T3 — Tavily key resolved ⇒ Tavily wired, key injected before `from_config()` | **PASS** | `test_build_discoverer_wires_tavily_and_injects_key_before_from_config_when_secret_resolves` — the recording fake proves `from_config()` saw the already-injected key. `_build_discoverer` byte-unchanged. |
| I3 | T4 — no key ⇒ RSS-only, no crash | **PASS** | `test_build_discoverer_falls_back_to_rss_only_when_tavily_key_unresolved` (forbidden-fake `from_config` would raise if called). |
| I4 | T5 — `_resolve_tavily_key` success / blank / boto3 error, and never logs the secret | **PASS** | Three tests against a faked `boto3.client`; the success case additionally asserts the secret appears in neither stdout nor stderr. |
| I5 | T6 — importing `runtime_app` does not start the HTTP server | **PASS** | `test_import_runtime_app_does_not_start_the_http_server` — `BedrockAgentCoreApp.run` patched, re-import asserts zero calls. Still valid: `app.run()` remains under `if __name__ == "__main__"`. |
| I6 | F2 regressions — `TAVILY_SECRET_UNSET_SENTINEL` treated as "no key" at all three levels | **PASS** | All three survive: unit (`_resolve_tavily_key` → `""`), `_build_discoverer` end-to-end through the real resolver, and the top level — the last one correctly **re-pointed** from the (now-nonexistent) response field to `curation_run_complete`'s `tavily_enabled`, joined by `run_id`. |

## Test Coverage

| ID | Test Description | Status | Test File |
|---|---|---|---|
| T1 | `handler({})` returns `{"status": "accepted", "run_id": <32-hex>}` and does **not** contain any count fields | **PASS** | `tests/test_runtime_app.py::test_handler_returns_accepted_ack_with_32_char_hex_run_id_and_no_count_fields` |
| T2 | Handler returns fast while the pipeline is stubbed to block: measured latency well under 1 s | **PASS** | `…::test_handler_returns_before_pipeline_completes_even_when_pipeline_blocks` |
| T3 | After draining, the stubbed `build_graph(...).invoke` was called exactly once with `{"max_items": <config.MAX_ITEMS>}` | **PASS** | `…::test_background_task_invokes_graph_exactly_once_with_configured_max_items` |
| T4 | `add_async_task` happened before `handler` returned; `get_current_ping_status()` is `HEALTHY_BUSY` at return time | **PASS** | `…::test_add_async_task_registered_before_handler_returns_and_ping_is_healthy_busy` (proves ordering via ping status while the pipeline is still blocked — equivalent to, and arguably stronger than, the "recorded call order" the plan sketched) |
| T5 | After completion, `get_async_task_info()["active_count"] == 0` and ping status is `HEALTHY` | **PASS** | `…::test_ping_status_and_active_task_count_return_to_idle_after_run_completes` |
| T6 | Single-flight: second `handler(...)` mid-run returns `already_running` with run 1's `run_id`; only one pipeline invocation ever happens | **PASS** | `…::test_second_invocation_while_run_in_flight_returns_already_running_and_starts_no_second_pipeline` |
| T7 | Pipeline raising: nothing escapes; task completed; `_active_run_id` cleared; subsequent `handler(...)` is `accepted` again | **PASS** | `…::test_pipeline_exception_does_not_escape_and_next_invocation_still_works` |
| T8 | `curation_run_complete` contains all eight counts plus `run_id` and `duration_s` | **PASS** | `…::test_curation_run_complete_log_record_contains_all_eight_counts_and_run_id` |
| T9 | `curation_run_failed` logged with exception info on pipeline failure (and no `curation_run_complete`) | **PASS** | `…::test_curation_run_failed_logged_with_exception_info_on_pipeline_failure` |
| T10 | `_background_tasks` holds the task in flight and is empty after completion | **PASS** | `…::test_background_tasks_set_holds_task_in_flight_and_empties_after_completion` |
| T11 | Payload-ignoring preserved: same ack shape and same graph input for `{}` vs an arbitrary payload | **PASS** | `…::test_handler_ignores_payload_argument_producing_identical_ack_shape_and_graph_input` |
| T12 | `_run_curation_pipeline()` alone returns the eight-field summary from the mocked graph final state | **PASS** | `…::test_run_curation_pipeline_returns_eight_field_summary_from_mocked_graph_final_state` |
| T13 | **(manual)** Real `agentcore invoke '{}'` returns the ack quickly; matching `curation_run_complete` found later; card count +1 slice | **PASS (live-executed 2026-08-10; re-verified by auditor)** | No pytest by construction. Evidence re-derived from live AWS (see **R11**): ECR image `20260810-221147-104` pushed `22:12:11Z` (so the fixed build was live), `curation_run_accepted` `22:12:29.516Z` → `curation_run_complete` `22:13:05.993Z` with matching `run_id 16f3c77a…` and `duration_s: 36.5`, and exactly **8** cards stamped `created_at 2026-08-10T22:13` in the `aws dynamodb scan` histogram |
| T14 | **(manual)** Real Scheduler fire: one run, `InvocationAttemptCount = 1`, no `TargetErrorCount` datapoint, DLQ 0, card count +1 slice | **PASS (live-executed 2026-08-10; re-verified by auditor)** | No pytest by construction. All four legs re-derived from live AWS (see **R12**): `InvocationAttemptCount` one datapoint `= 1.0` @ `22:26Z`; `TargetErrorCount` **zero datapoints** (vs `1.0` @ 21:08 **and** `1.0` @ 21:09 in the F5 window, same query); exactly **two** log events in the window (`curation_run_accepted` + `curation_run_complete`, one `run_id`, Scheduler-templated `sessionId`); card count 56 with a single 8-card `22:26` bucket; DLQ `ApproximateNumberOfMessages "0"` |
| — | *Gap:* C12 (`asyncio.create_task` raises → guard cleared, task completed, exception propagates) | **MISSING** | Not in the T-plan either; see finding **A3** |
| — | *Gap:* Data Model #4 — the `curation_run_accepted` record | **MISSING** | Emitted and observed by the auditor, but no assertion; see finding **A3** |

**Suite results (auditor-run, pass 2, 2026-08-10, post-Phase-4):** `uv run pytest -q` → **92 passed**, 0 failed, 0 errors, in 2.30 s — unchanged by Phase 4, which touched only live AWS and no source file. `git status --porcelain` for the protected paths shows ` M infra/app.py` (pre-existing `eventbridge-schedule` work), ` M runtime_app.py` (this spec), and the two untracked `eventbridge-schedule` infra modules — **no** `src/`, `Dockerfile`, `.dockerignore`, `pyproject.toml`, or `uv.lock` diff, so R7/C16's no-new-dependency claim still holds after the redeploy.

**Suite results (auditor-run, pass 1, 2026-08-10):**
`uv run pytest tests/test_runtime_app.py -v` → **23 passed** in 0.17 s.
`uv run pytest -q` → **92 passed**, 0 failed, 0 errors, in 2.15 s (69 pre-existing + 23 here — matches `tasks.md` Task 3.10's claim).
Re-run with `AWS_ACCESS_KEY_ID=bogus AWS_SECRET_ACCESS_KEY=bogus AWS_EC2_METADATA_DISABLED=true` → **92 passed** (no real credentials required). No `@pytest.mark.live` tests exist in this repo, so the default run is the full offline run.

## Audit Log

| Date | Auditor | Finding | Severity | Resolution |
|---|---|---|---|---|
| 2026-08-10 | sdd-architect | Spec authored to close `eventbridge-schedule` F5 (HIGH): Scheduler's universal target is synchronous with an undocumented ~30 s timeout; the 25–35 s inline curation run caused a single fire to execute 2–4 times. Root cause confirmed by CloudWatch runtime logs + `AWS/Scheduler` metrics + CloudTrail, and corroborated by an independent public writeup of identical behavior. Fix direction (SDK-native `add_async_task`/`complete_async_task` + immediate ack) verified against Context7 `/aws/bedrock-agentcore-sdk-python` **and** the installed `bedrock-agentcore==1.18.1` source. | HIGH (the bug) | Spec set produced; awaiting human approval, then TDD pipeline + Phase 4 live-fire re-verification |
| 2026-08-10 | sdd-auditor | **Phases 1–3 implementation verified independently — no contract violation found.** All 11 Behavior Guarantees hold. The two most failure-prone details are correct: **Guarantee 3** — `add_async_task` is at `runtime_app.py:193`, *inside* `handler`, before `create_task` (`:196`) and before `return` (`:207`), **not** inside `_curation_run`; proven behaviorally by an auditor E2E in which `GET /ping` returned `HealthyBusy` at ack+0 ms with the pipeline thread still blocked. **Guarantee 4** — the check-and-set at `:188`→`:192` has no intervening `await` and both mutation sites run on the SDK's single `agentcore-worker-loop`, so the lock-free claim is sound. Also independently confirmed: `_run_curation_pipeline` is Spec 04's body **verbatim** (diff shows only the `def`/docstring changed); `asyncio.to_thread` genuinely keeps the loop free (`/ping` rtt 0.3–3.0 ms during a 3 s blocking run); the ack is **0.002 s** end-to-end through the real SDK dispatch path vs F5's live 33.04 s / 24.89 s; failures log a real `stackTrace`, release the guard, never reach HTTP, and the process recovers; `src/`, `Dockerfile`, `.dockerignore`, `pyproject.toml`, `uv.lock` are **untouched** and `cdk diff` is empty on all three stacks. | — | Informational — positive verification. Phases 1–3 approved. |
| 2026-08-10 | sdd-auditor | **A1 — `README.md` was not updated (R10 FAIL), and this blocks Phase 4, not just the docs.** `README.md:145-162` still advertises the smoke test as returning `{"discovered": 50, "summarized": 8, "persisted": 8, "tavily_enabled": true}`, which the ack response no longer produces (Spec 04 BG8 is superseded). There is no `async-invocation-ack` spec-table row, no F5 pointer in the Spec 05 live-fire section, and no two-step "ack now, verify in CloudWatch + DynamoDB" runbook — yet Phase 4 Tasks 4.3, 4.4, 4.6 and 4.8 all name "runbook (`README.md`)" as the location of the procedure they follow. `tasks.md` Task 3.12 is honestly marked `[!]` with a scope justification, so this is a *declared* deferral rather than a silent gap, and it is not a code defect. | **MEDIUM** | Do the documentation pass (sdd-documentarian, or fold it into Phase 4 pre-flight) **before** starting Phase 4, so the redeploy + live-fire steps and the `execution_role: null` `agentcore destroy` gotcha are written down where the operator will look. Flip R10 to PASS then. |
| 2026-08-10 | sdd-auditor | **A2 — `tests/test_runtime_app.py` still carries RED-phase prose that is now false.** Its module docstring (`:26-33`) states "RED phase: `runtime_app.handler` is still Spec 04's synchronous, counts-returning version, and `runtime_app._background_tasks` / `_active_run_id` / `_curation_run` / `_run_curation_pipeline` do not exist yet… Tests that depend on the async-ack behavior are expected to fail" — all four attributes exist and all 23 tests pass. `_call_handler` (`:276-283`) and the autouse `_reset_async_run_state` fixture (`:243-263`) repeat the same stale framing. Worse, that fixture's `hasattr` guards were written *for* the RED phase: they now make the fixture **silently no-op** if `_active_run_id` / `_background_tasks` are ever renamed, and `tasks.md`'s own Notes call that fixture "load-bearing" precisely because a leaked in-flight run makes every later test return `already_running`. The executor's `tasks.md` notes are accurate that it did not modify this file (it was authored by the test-writer), so this is unowned leftover rather than a regression. | **MEDIUM** | Delete the RED-phase paragraph from the module docstring and from `_call_handler`; drop the three `hasattr` guards in `_reset_async_run_state` so a rename fails loudly. No behavior change, no re-run risk. |
| 2026-08-10 | sdd-auditor | **A3 — two contract items are implemented but untested.** (a) **C12** — the `create_task`-raises unwind (`runtime_app.py:195-200`: clear guard → `complete_async_task` → `raise`) has no test; it is also absent from audit.md's own T1–T12 plan, so this is a plan gap rather than an executor omission. Reading the code, the order matches the contract exactly. (b) **Data Model #4** — the `curation_run_accepted` record (`:205`) is never asserted; `_find_json_log_record`'s docstring mentions it but no test greps for it. The auditor observed it emitted correctly in E2E (`{"event": "curation_run_accepted", "run_id": "8c8336dc…"}`). Both are low-risk, but "every pinned log shape has a test" is the standard the other two records meet. | **LOW** | Add two cheap tests: monkeypatch `runtime_app.asyncio.create_task` to raise and assert `_active_run_id is None` + `active_count == 0` + the exception propagates; and assert the `curation_run_accepted` record's `run_id` equals the ack's. Neither requires new fixtures. |
| 2026-08-10 | sdd-auditor | **A4 — the single-flight guard is armed one statement too early, leaving a (practically unreachable) permanent-wedge window.** `runtime_app.py:192` sets `_active_run_id = run_id` **before** `app.add_async_task(...)` at `:193`, and only `asyncio.create_task` at `:196` is inside the try/except that unwinds the guard. If `add_async_task` ever raised — it takes `_task_counter_lock` and calls `self.logger.info(...)`, so a logging/handler failure is the realistic path — `_active_run_id` would stay set with **no task scheduled and no coroutine to clear it**, and the process would answer `already_running` forever and never curate again until the microVM recycles. This is exactly the wedge failure mode `tasks.md`'s Notes warn about, just on a different statement than the one they guard. It matches the roadmap's prescribed order literally, so it is a spec-faithful implementation of a slightly under-specified sequence, not a deviation. | **LOW** | One-line hardening: either move `_active_run_id = run_id` to after `add_async_task` returns, or widen the existing `try:` to start at the `add_async_task` call (unwinding to `_active_run_id = None` and re-raising when there is no `task_id` yet). Worth doing while the file is open for A1/A2. |
| 2026-08-10 | sdd-auditor | **A5 — the success-path log call sits outside the exception guard.** `runtime_app.py:159-170` builds and emits `curation_run_complete` in the `else:` clause, which `except Exception` does not cover. A non-JSON-serializable value in any of the eight summary fields would escape `_curation_run` as an unretrieved task exception. Impact is genuinely small: `finally` still runs, so `complete_async_task` fires and the guard is released (no wedge, no 5xx — the ack was long since sent), the counts are all `int`/`bool` in practice, and Behavior Guarantee 5 speaks of exceptions "in the pipeline", which *are* covered. | **LOW** | Optional: move the `else:` body inside the `try:` (after the `await`) or wrap the `json.dumps`/`logger.info` pair in its own `try/except Exception: logger.exception(...)`. |
| 2026-08-10 | sdd-auditor | **A6 — minor, accepted deviations, recorded for completeness.** (a) `import time` is present at `runtime_app.py:25` but is not in contract.md's pinned import block; it backs `_curation_run`'s `duration_s` timer, which the contract *does* pin, and `tasks.md` Tasks 1.2/2.3 declare the deviation (`time.monotonic()` chosen over `loop.time()` to avoid the `get_event_loop()` deprecation surface). Stdlib — zero dependency impact. (b) The `already_running` branch emits **no** log record; contract.md pins exactly three record shapes and does not require a fourth, so this is compliant, but Phase 4 Task 4.4's single-flight check and any future Spec 06 alarm would have to infer the rejection from the *absence* of a second `curation_run_accepted`. (c) `tasks.md` Task 1.5 records a real process deviation — Phases 1 and 2 were edited in a single pass rather than pausing for an intermediate green run — with a defensible justification; the extraction is verifiably verbatim from the diff, so the intended evidence (behavior preservation) exists by other means. | **LOW / informational** | (a) accept as-is, or add `time` to contract.md's import block on the next spec touch. (b) consider a `curation_run_rejected` record if Spec 06 wants to count suppressed duplicates. (c) no action. |
| 2026-08-10 | sdd-auditor | **A7 — `tasks.md`'s claims were re-derived and hold up.** Task 3.10's "23 passed / 92 passed" reproduced exactly. Task 3.11's "`git diff --stat` touches only `runtime_app.py` + `tests/test_runtime_app.py` as this spec's files" is **true**: the other three dirty paths are `infra/app.py` (verified line-by-line to be pure `eventbridge-schedule` stack wiring), `README.md` and `CLAUDE.md` (verified by grep to contain **zero** async-invocation-ack content). Task 3.11's "`cdk diff` → no differences for all three stacks" reproduced against live AWS. Tasks 3.1–3.9's "already present in the red-phase test file; not modified" is consistent with the file's authorship. Phase 4's ten tasks are all correctly left `[ ]` with an explicit gate, and Task 3.12 is correctly `[!]` with a justification. **No overstatement found** — a notable contrast with the `eventbridge-schedule` audit's F6. | — | Informational — positive finding on evidence discipline. |
| 2026-08-10 | conductor (sdd-executor fix, human-directed) | **A1/A2/A4/A5 fixed** (A3/A6/A7 left as recorded — A3's two test gaps and A6's minor deviations are recommendations, not defects, and out of scope for this fix pass). **A1**: `README.md`'s "Smoke test" block (formerly `:145-162`) rewritten as the two-step ack-then-verify flow — `agentcore invoke '{}'` now documented to return the ack shape (`{"status": "accepted", "run_id": …}`), followed by finding the matching `curation_run_complete` CloudWatch record and an `aws dynamodb scan --select COUNT` check; the old counts-in-response claim is kept only as a dated, explicitly-superseded historical note. `tasks.md` Task 3.12 flipped `[!]`→`[x]` with a scope note (a dedicated spec-table row and an F5 pointer in the Spec 05 live-fire section remain open, deferred until Phase 4 has real evidence to report). **A2**: `tests/test_runtime_app.py`'s module docstring, `_call_handler`, and `_reset_async_run_state` no longer describe a "RED phase" or claim symbols "do not exist yet" — rewritten to describe the current green behavior; the three `hasattr` guards in `_reset_async_run_state` were dropped so a future rename of `_active_run_id`/`_background_tasks`/`app` fails the fixture loudly instead of silently no-op'ing, exactly as A2 recommended. **A4**: `handler`'s happy path reordered so `_active_run_id` is armed only *after* `app.add_async_task(...)` returns; the `try/except` was widened to cover `add_async_task` as well as `asyncio.create_task`, using a `task_id = None` sentinel to distinguish "guard never armed" (add_async_task failed) from "guard armed, task registered" (create_task failed) — the latter still unwinds exactly as before (`complete_async_task` + re-raise). Closes the theoretical permanent-`already_running` wedge. **A5**: `_curation_run`'s `curation_run_complete` emission moved from the `else:` clause into the end of the `try:` block (after the `await`), so a `json.dumps`/log failure on the success path is now caught by the same `except Exception` and reported as `curation_run_failed` instead of escaping as an unretrieved task exception; `finally`'s cleanup is unaffected. | A1/A2 MEDIUM, A4/A5 LOW → RESOLVED | Independently re-verified: `uv run pytest tests/test_runtime_app.py -v` → 23 passed (unchanged); `uv run pytest -q` → 92 passed, 0 failed, 0 errors (no regressions). `git diff --stat` confirms the fix pass touched only `README.md`, `runtime_app.py`, and `tests/test_runtime_app.py` — no `infra/**`, `src/**`, `pyproject.toml`, `uv.lock`, or `Dockerfile` diff. Phase 4 (real redeploy + live fire) remains not started, unaffected by this pass. |

| 2026-08-10 | sdd-auditor | **Phase 4 re-audit — F5 is CLOSED, and the evidence was re-derived from live AWS rather than read off `tasks.md`.** The single decisive comparison, same query shape, same namespace, same `Period=60`/`Stat=Sum`: the **original F5 fire** (window `21:00–21:20Z`) returned `InvocationAttemptCount` = 1.0 @ 21:08 **and** 1.0 @ 21:09 with `TargetErrorCount` = 1.0 @ 21:08 **and** 1.0 @ 21:09 — one execution, two deliveries, two recorded target errors, two full curation runs. The **post-fix fire** (window `22:17–22:32Z`) returned `InvocationAttemptCount` = a single `1.0` @ 22:26 and `TargetErrorCount` = `Timestamps: []`, `Values: []`, `StatusCode: Complete` — **zero datapoints**, i.e. queried and genuinely absent. `InvocationsSentToDeadLetterCount` and `InvocationDroppedCount` likewise empty; DLQ `ApproximateNumberOfMessages "0"`. Log-side: exactly **two** records in the window (`curation_run_accepted 22:26:14.740Z` → `curation_run_complete 22:26:39.282Z`, `duration_s: 24.5`, all eight counts, one `run_id 3fbc7050…`), both stamped `sessionId ai-radar-scheduled-curation-run-id-9a6a7a4e-…`, confirming a genuinely Scheduler-driven fire; an open-ended re-poll at `22:35:33Z` still found two. Table-side: `scan --select COUNT` → **56**, and the `created_at` histogram (16/8/8/8/8/8) shows the scheduled fire produced **one** 8-card bucket at 22:26 — directly beside the 21:08+21:09 twin buckets that are F5's fossil record. Deployment provenance independently established: ECR image `20260810-221147-104` pushed `22:12:11Z`, so nothing measured here was the old synchronous build. Root-cause chain now complete: the manual invoke at 22:12 ran **36.5 s** — past Scheduler's ~30 s universal-target ceiling — and produced no error *because the ack had already returned*. | HIGH (the original F5 bug) → **RESOLVED** | R11–R14 and T13–T14 flipped from NOT YET VERIFIED to **PASS**. F5 marked RESOLVED in `specs/eventbridge-schedule/audit.md` with a dated entry (R14). Spec **APPROVED**. |
| 2026-08-10 | sdd-auditor | **Phase 4 coverage gaps, recorded so the verdict is not read as broader than it is.** Two planned tasks were **not performed** this session and `tasks.md` leaves both correctly `[ ]` with explicit notes rather than inferring them: **(a) Task 4.4 — the live single-flight check.** Only one `agentcore invoke` was issued; no back-to-back concurrent invoke was fired at the deployed agent, so `already_running` has **never been observed in production** — it rests entirely on offline test T6 and pass 1's in-process E2E through the real SDK dispatch path. **(b) Task 4.5 — pre-arm SSM re-verification.** No `aws ssm get-parameter` output was captured immediately before arming the schedule. The auditor checked it *after the fact*: `/ai-radar/agent-runtime-arn` = `arn:aws:bedrock-agentcore:us-east-1:536697225154:runtime/ai_radar_curation-sIf5Dw979w`, `LastModifiedDate 2026-08-10T20:47:37Z` — unchanged since the prior `eventbridge-schedule` session and identical to the ARN the redeploy reused, and the fire demonstrably reached the right agent (matching `sessionId` in that agent's log group), so the parameter *was* correct; but that is post-hoc inference, not the ordered pre-flight check the task specifies. **Neither gap touches F5.** R12's four evidence legs are independent of both: single-flight suppression is a *different* guarantee from ack-before-timeout, and the SSM value is proven correct by the fire landing where it did. | **LOW** | Not blocking — the verdict rests on R11–R14, none of which depend on 4.4 or 4.5. Fold Task 4.4 into any future live session (two `agentcore invoke '{}'` calls ~2 s apart; expect the second to return `already_running` with the first's `run_id` and exactly one `curation_run_complete`); it is the only Behavior Guarantee with no production observation. |
| 2026-08-10 | sdd-auditor | **A8 — README's `async-invocation-ack` documentation is now *stale* rather than merely incomplete.** A1's fix landed (R10 → PASS) and the smoke-test block is correct, but two residuals it explicitly deferred "until Phase 4 has real evidence to report" are now overdue, and one of them has become actively wrong: **(a)** `README.md:189-190` still states the re-verification is "not yet run against a redeployed" agent — false as of `22:26:14Z` today, and it is the sentence a reader would use to decide whether the async fix is proven. **(b)** the spec table (`README.md:16-23`) still lists five specs with no `async-invocation-ack` row, so the table — which `CLAUDE.md` names as "the source of truth, not this file" for current status — omits the spec that closed a HIGH finding against the row directly above it. **(c)** the Spec 05 live-fire section still has no pointer to F5 or its resolution, which was F6's recommendation in the sibling audit. Purely documentation; no code, contract, or coverage impact, and `tasks.md` Task 3.12's scope note predicted exactly these three items. | **MEDIUM** | Documentation pass (sdd-documentarian): add the `async-invocation-ack` spec-table row marked shipped & live-fire verified; replace `:189-190`'s "not yet run" with the 2026-08-10 result (`InvocationAttemptCount = 1`, no `TargetErrorCount`, one run, +8 cards, DLQ 0); and add the F5 → resolved pointer in the Spec 05 live-fire section. Also correct Spec 05's F6 numbers while there (`24 → 40`, first delivery `21:08:14Z`). |
| 2026-08-10 | sdd-auditor | **`tasks.md`'s Phase 4 claims were re-derived and hold up — including the ones that admit failure.** Every checkable number matches live AWS: the reused runtime ARN, the ECR tag `20260810-221147-104`, both `run_id`s, all four timestamps (`22:12:29.516Z`, `22:13:05.993Z`, `22:26:14.740Z`, `22:26:39.282Z`), both `duration_s` values (36.5 / 24.5), the schedule's post-fire `DISABLED` / `cron(0 6 * * ? *)` / `Etc/UTC`, and the DLQ zero. The card-count progression **40 → 48 → 56** reconciles exactly against the `created_at` histogram — notable because this is the precise claim `eventbridge-schedule`'s **F6** caught being wrong last session (a mid-run sample reported "24 → 32" when the truth was 40). The executor also declined to round up Tasks 4.4/4.5 from offline coverage, and flagged its own 6.7 s CLI round-trip rather than quoting the task text's "~1 s" estimate. **No overstatement found**; F6's lesson was applied. | — | Informational — positive finding on evidence discipline. |

---

## Final Verdict (Phases 1–3, offline; 2026-08-10)

> **Superseded — see "Final Verdict (Phase 4 re-audit, 2026-08-10)" at the end
> of this file.** The pass-1 verdict is retained verbatim for the record; its
> statements that Phase 4 "has not been run" and that F5 "remains open" are no
> longer true.

> Authored by **sdd-auditor**, 2026-08-10. Every claim was re-derived by the
> auditor — `uv run pytest` (twice, plus a black-holed-network and a
> bogus-credentials run), `git diff`/`git status` against the six protected
> paths, `uv run --group infra cdk diff` against **live AWS**, a line-by-line
> read of `runtime_app.py` and `tests/test_runtime_app.py`, a read of the
> installed `bedrock_agentcore==1.18.1` runtime source, and **two end-to-end
> runs through the real SDK HTTP dispatch path** (Starlette `TestClient` over
> `runtime_app.app`, success and failure paths) — **not** accepted from
> `tasks.md`'s prose.
>
> This pass is **necessarily offline**: Phase 4 has not run, so the finding
> this spec exists to close (**F5**) is **still open**.

**Status**: **APPROVED for Phases 1–3 (offline implementation). Phase 4
(real-AWS re-verification of F5) still PENDING.**

**Summary**: `runtime_app.py`'s entrypoint is now an `async def` that
acknowledges in **0.002 s** over the real SDK dispatch path — against F5's
observed 33.04 s and 24.89 s — while the byte-for-byte-unchanged curation graph
runs to completion on the SDK's worker loop under a registered async task, with
`/ping` reporting `HealthyBusy` from ack+0 ms and staying responsive
(0.3–3.0 ms) throughout a blocking run. All 11 Behavior Guarantees, all 15
contract items, all 6 inherited Spec 04 items and all 12 offline test rows
verify; 92/92 tests pass offline with no credentials and no network; `src/`,
`infra/`, `Dockerfile`, `.dockerignore`, `pyproject.toml` and `uv.lock` are
untouched and `cdk diff` is empty on all three stacks. **No contract violation
was found, and no bug that changes behavior.** What is missing is the evidence
that only real AWS can supply, plus the README pass that Phase 4 itself depends
on.

**Critical Issues** (must fix before merge): **none.**

**Blocking for closing F5 / going live** (not defects — undone work):
- **R11–R14, T13–T14 (Phase 4)** — the redeploy and the one-shot Scheduler live
  fire have **not** been run (`tasks.md` Tasks 4.1–4.10 all `[ ]`, correctly
  gated on human go-ahead). **The fix is inert until `agentcore deploy`
  rebuilds the image.** Until `InvocationAttemptCount = 1` with **no**
  `TargetErrorCount` datapoint, exactly one `curation_run_complete` for the
  `ai-radar-scheduled-curation-run-id-<execution-id>` session, DLQ depth 0, and
  a **one**-slice card-count delta are all recorded, `specs/eventbridge-schedule/
  audit.md`'s **F5 remains open at HIGH** and the daily cadence must stay off.
  The offline E2E is strong corroboration, not substitution: it cannot test
  Scheduler's undocumented timeout, and it cannot rule out AgentCore Runtime
  reaping the microVM after the ack despite `HEALTHY_BUSY` (roadmap Risk row 1 —
  detector is Phase 4.3's "ack with no matching `curation_run_complete`").

**Warnings** (should fix, not blocking approval of Phases 1–3):
- **A1 (MEDIUM)** — `README.md` not updated (**R10 FAIL**). It still claims the
  smoke test returns `{"discovered": 50, …}`, has no spec-table row, and has no
  F5 pointer. Because Phase 4 Tasks 4.3/4.4/4.6/4.8 all point at "runbook
  (`README.md`)" for procedures that do not exist there yet, **do this before
  Phase 4**, not after.
- **A2 (MEDIUM)** — `tests/test_runtime_app.py`'s module docstring and two
  helper docstrings still describe the RED phase and claim the async tests "are
  expected to fail"; the `hasattr` guards in the load-bearing
  `_reset_async_run_state` fixture would now silently no-op on a rename.

**Recommendations** (nice to have):
- **A3 (LOW)** — add the two missing tests: the `create_task`-raises unwind
  (C12) and the `curation_run_accepted` record (Data Model #4).
- **A4 (LOW)** — arm `_active_run_id` *after* `add_async_task` succeeds (or
  widen the `try:` to cover it), closing the theoretical permanent-`already_
  running` wedge.
- **A5 (LOW)** — move the `curation_run_complete` emission inside the exception
  guard so a serialization error cannot escape `_curation_run`.
- **A6 (LOW)** — record `import time` in contract.md's pinned import block on
  the next spec touch; consider a `curation_run_rejected` log record so Spec 06
  can count suppressed duplicates rather than inferring them.
- For Phase 4 evidence discipline (the `eventbridge-schedule` F6 lesson): sample
  the DynamoDB count **before** the fire and again **after** the full 2 h
  `MaximumEventAgeInSeconds` window, not mid-run, and quote the `AWS/Scheduler`
  `TargetErrorCount` query verbatim — "no datapoint" and "not queried" must not
  be conflated.

**What remains genuinely unverified** (stated without rounding up):
- Whether a real EventBridge Scheduler fire against the **redeployed** agent
  produces exactly one curation run with `TargetErrorCount` absent — i.e.
  whether F5 is actually closed. Everything above establishes that the code
  *should* close it; nothing above establishes that it *does*.
- Whether AgentCore Runtime honors `HEALTHY_BUSY` and lets a ~30 s background
  run finish after the HTTP response was sent. Verified against the SDK's
  in-process bookkeeping only; the managed runtime's reaping behavior is
  Phase 4 evidence.

---

## Final Verdict (Phase 4 re-audit, 2026-08-10)

> Authored by **sdd-auditor**, 2026-08-10, after Phase 4 was **actually
> executed against real AWS**. Every claim below was re-derived from live AWS
> by the auditor — `aws cloudwatch get-metric-data` over `AWS/Scheduler` (both
> the post-fix window **and** the original F5 window, same query shape, for a
> like-for-like contrast), `aws logs filter-log-events` on the runtime log
> group, `aws dynamodb scan` (count **and** full `created_at` histogram),
> `aws sqs get-queue-attributes`, `aws scheduler get-schedule`, `aws ecr
> describe-images`, `aws cloudformation describe-stack-events`, plus a fresh
> `uv run pytest -q` and `git status` on the protected paths — **not** accepted
> from `tasks.md`'s Phase 4 prose. Every number in `tasks.md` that could be
> checked, was checked, and all of them matched.

**Status**: **APPROVED.**

Phases 1–3 remain approved (unchanged, still 92/92 green offline). Phase 4 is
now **executed and independently verified**: **R11, R12, R13, R14** and
**T13, T14** move from NOT YET VERIFIED to **PASS**, **R10** moves from FAIL to
**PASS**, and `specs/eventbridge-schedule/`'s **F5 (HIGH) is CLOSED** — which
was this spec's entire reason for existing.

**Summary**: A real EventBridge Scheduler execution fired at `22:26:14Z` against
the redeployed agent (ECR image `20260810-221147-104`, pushed `22:12:11Z`) and
produced **one** delivery, **one** curation run, and **one** 8-card slice.
`InvocationAttemptCount` was a single `1.0` datapoint and `TargetErrorCount`
had **zero** datapoints — against the original F5 fire's `1.0` @ 21:08 **and**
`1.0` @ 21:09 on *both* metrics. The mechanism is confirmed rather than merely
correlated: the manual invoke 14 minutes earlier ran **36.5 s**, well past
Scheduler's ~30 s universal-target ceiling, and still drew no error, because the
ack had returned within the first second and the pipeline finished on the
background task. The DynamoDB `created_at` histogram
(16 / 8 / 8 / 8 / 8 / 8 = 56) carries the contrast in a single view: two
adjacent 8-card buckets at 21:08 and 21:09 (F5's double-run), then a lone
8-card bucket at 22:26 (the fixed behavior). DLQ is empty and the schedule is
back to `DISABLED` / `cron(0 6 * * ? *)` / `Etc/UTC` with every Spec 05 delivery
property intact.

**Critical Issues** (must fix before merge): **none.**

**Blocking for closing F5**: **none — F5 is closed.**

**Warnings** (should fix, not blocking):
- **A8 (MEDIUM)** — `README.md` documentation is now *stale*, not just
  incomplete. `:189-190` still says the re-verification is "not yet run against
  a redeployed" agent (false since `22:26Z`); the spec table `:16-23` still has
  no `async-invocation-ack` row despite `CLAUDE.md` naming that table the source
  of truth for status; and the Spec 05 live-fire section still has no F5
  pointer. A documentation pass should also correct Spec 05's F6 numbers
  (`24 → 40`, first delivery `21:08:14Z`).

**Recommendations** (nice to have, all carried over unchanged):
- **A3 (LOW)** — the two missing tests: the `create_task`-raises unwind (C12)
  and the `curation_run_accepted` record (Data Model #4).
- **A6 (LOW)** — record `import time` in contract.md's pinned import block;
  consider a `curation_run_rejected` record so Spec 06 can count suppressed
  duplicates rather than inferring them from an absence.
- **Bookkeeping** — the A4/A5 fix pass shifted line numbers in `runtime_app.py`,
  so several pass-1 citations above are now off by ~8 lines. Current anchors:
  `_run_curation_pipeline` `:104`, `_curation_run` `:131`,
  `complete_async_task` `:178`, guard release `:179`, `handler` `:183`,
  single-flight branch `:194-195`, `add_async_task` `:201`, `_active_run_id`
  armed `:202` (correctly **after** `add_async_task` — A4's fix, re-confirmed
  by the auditor), `create_task` `:203`, `curation_run_accepted` `:219`.

**What was NOT performed this session** (stated plainly, per `tasks.md`, and
deliberately not rounded up into the verdict):
- **Task 4.4 — the live single-flight check was not run.** Only one
  `agentcore invoke` was issued. `already_running` has **never been observed
  against the deployed agent**; it rests on offline test T6 and pass 1's
  in-process E2E. This is the one Behavior Guarantee with no production
  observation.
- **Task 4.5 — no pre-arm `aws ssm get-parameter` output was captured.** The
  auditor confirmed the value *after the fact*
  (`/ai-radar/agent-runtime-arn` → the correct runtime ARN, `LastModifiedDate
  2026-08-10T20:47:37Z`, unchanged from the prior session), and the fire
  demonstrably reached the right agent, but that is post-hoc inference rather
  than the ordered pre-flight check.
- **Neither gap affects the verdict.** R12's four evidence legs are independent
  of both: single-flight suppression is a different guarantee from
  ack-before-timeout, and the SSM value is proven correct by where the fire
  landed.
- **Window caveat**: the post-fire observation window was **~9 minutes**
  (`22:26:14Z` fire → `22:35:33Z` last poll), not the full 2 h
  `MaximumEventAgeInSeconds` that pass 1's evidence-discipline note requested.
  It is ~9× the 61 s retry interval observed during F5, and the argument is
  causal anyway — no target error was recorded, so there was no failed attempt
  to retry — but a longer soak would be strictly stronger.

**Live AWS state at the close of this audit** (unchanged by the audit itself):
`AiRadarSchedule` and `AiRadarRuntimeRole` both still deployed; the
`ai_radar_curation-sIf5Dw979w` runtime is live on the async-ack image; the
schedule is `DISABLED`, so there is no recurring fire and no recurring
Scheduler/Bedrock cost — but the standing agent remains the live cost exposure
that `eventbridge-schedule`'s **F9** describes.

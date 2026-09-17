# Tasks: async-invocation-ack

## Legend
- [ ] Not started
- [x] Completed
- [~] In progress
- [!] Blocked

All production changes land in **one file** (`runtime_app.py`). Nothing under
`src/` or `infra/` may be touched — if a task seems to require it, stop and
raise it instead.

## Phase 1: Extract the synchronous pipeline body
- [x] Task 1.1: Update the module docstring — name Spec 04 + this spec, state
      the ~30 s EventBridge Scheduler universal-target timeout and the 25–35 s
      run that motivates the ack, and keep the existing portability paragraph
      (`bedrock_agentcore` / `boto3` confined to this composition root) —
      `runtime_app.py`
- [x] Task 1.2: Add imports `asyncio`, `json`, `logging`, `uuid` (stdlib only —
      no `pyproject.toml` / `uv.lock` change) — `runtime_app.py`
      (also `time`, stdlib, for the `_curation_run` duration timer)
- [x] Task 1.3: Add module logger
      `logger = logging.getLogger("bedrock_agentcore.app.curation")` with the
      comment explaining it is a child of the SDK's configured logger (inherits
      its StreamHandler + INFO level; no `basicConfig`) — `runtime_app.py`
- [x] Task 1.4: Extract Spec 04's `handler` body verbatim into
      `_run_curation_pipeline() -> dict` (store → discoverer → unchanged
      `build_graph(...)` → `.invoke({"max_items": config.MAX_ITEMS})` → the
      eight-field summary dict); docstring must flag it as BLOCKING and
      "always called via `asyncio.to_thread`" — `runtime_app.py`
- [x] Task 1.5: Leave `handler` synchronous, delegating to
      `_run_curation_pipeline()`; run `uv run pytest tests/test_runtime_app.py`
      and confirm the whole Spec 04 suite is still green — this proves the
      extraction was behavior-preserving before any async work starts —
      `runtime_app.py`
      **Deviation**: implemented Phase 1's extraction and Phase 2's async
      conversion in a single editing pass (rather than pausing mid-file-edit
      to run pytest against a half-converted module), then validated both
      together — `uv run pytest tests/test_runtime_app.py -v` → 23/23 passed
      on the first run after the combined edit, which is at least as strong
      evidence of behavior-preservation as an intermediate green run would
      have been.

## Phase 2: Ack-now / work-later core
- [x] Task 2.1: Add `_background_tasks: set[asyncio.Task] = set()` with the
      "asyncio holds only a weak reference to a bare `create_task` result"
      comment — `runtime_app.py`
- [x] Task 2.2: Add `_active_run_id: str | None = None` with the "single-flight
      guard; read/written only on the SDK worker loop, so no lock" comment —
      `runtime_app.py`
- [x] Task 2.3: Implement `async def _curation_run(run_id: str, task_id: int)
      -> None`: start timer → `await asyncio.to_thread(_run_curation_pipeline)`
      → `logger.info(json.dumps({"event": "curation_run_complete", "run_id":
      run_id, "duration_s": round(elapsed, 1), **summary}))` — `runtime_app.py`
      (timer via `time.monotonic()`, not `loop.time()`, to avoid the
      `asyncio.get_event_loop()` deprecation surface — same observable
      behavior)
- [x] Task 2.4: In `_curation_run`, catch `Exception` →
      `logger.exception(json.dumps({"event": "curation_run_failed", "run_id":
      run_id, "duration_s": …}))`; never re-raise — `runtime_app.py`
- [x] Task 2.5: In `_curation_run`'s `finally`: `app.complete_async_task(
      task_id)` and clear `_active_run_id` (guard released on success *and*
      failure) — `runtime_app.py`
- [x] Task 2.6: Convert `handler` to `async def handler(payload) -> dict`,
      keeping exactly one ignored parameter (do NOT add a `context` param — the
      SDK's `_takes_context` injects one only when it is literally named
      `context`) — `runtime_app.py`
- [x] Task 2.7: `handler` single-flight branch: if `_active_run_id is not
      None`, return `{"status": "already_running", "run_id": _active_run_id}`
      without touching the SDK task registry — `runtime_app.py`
- [x] Task 2.8: `handler` happy path, in this contractual order:
      `run_id = uuid.uuid4().hex` → set `_active_run_id` →
      `task_id = app.add_async_task("curation_run", {"run_id": run_id})` →
      `asyncio.create_task(_curation_run(run_id, task_id))` → add to
      `_background_tasks` + `task.add_done_callback(_background_tasks.discard)`
      → `logger.info(json.dumps({"event": "curation_run_accepted", "run_id":
      run_id}))` → `return {"status": "accepted", "run_id": run_id}` —
      `runtime_app.py`
- [x] Task 2.9: Wrap the `create_task` step so a scheduling failure clears
      `_active_run_id`, calls `app.complete_async_task(task_id)`, and
      re-raises (a genuine 5xx that Scheduler *should* retry) — `runtime_app.py`

## Phase 3: Tests, docs, and the deployment story
- [x] Task 3.1: Add a module-local helper to drive the async handler on a
      test-owned event loop (`loop.run_until_complete(handler(...))`) and drain
      in-flight work via `loop.run_until_complete(asyncio.gather(
      *runtime_app._background_tasks))`; no `pytest-asyncio`, no bare sleeps;
      add an autouse fixture resetting `_active_run_id` / `_background_tasks`
      between tests — `tests/test_runtime_app.py`
      (already present in the red-phase test file as written by the
      test-writer; not modified — `_call_handler` / `_drain` /
      `_reset_async_run_state` fixture)
- [x] Task 3.2: Rewrite T1 for the ack shape (`accepted` + 32-hex `run_id`, no
      count fields), and add T3's "graph invoked exactly once with
      `{"max_items": MAX_ITEMS}` after draining" assertion —
      `tests/test_runtime_app.py` (already present; not modified — see note
      below)
- [x] Task 3.3: Add T2 latency test — stub `_run_curation_pipeline` to block on
      a `threading.Event`, assert `handler` returned in well under 1 s, then
      release the event and drain — `tests/test_runtime_app.py` (already
      present; not modified)
- [x] Task 3.4: Add T4/T5 ping-status tests — `add_async_task` called before
      the handler returned; `app.get_current_ping_status()` is `HEALTHY_BUSY`
      at return time and `HEALTHY` (and `active_count == 0`) after draining —
      `tests/test_runtime_app.py` (already present; not modified)
- [x] Task 3.5: Add T6 single-flight test — second `handler(...)` during a
      blocked run returns `already_running` with run 1's `run_id`; exactly one
      pipeline invocation total — `tests/test_runtime_app.py` (already
      present; not modified)
- [x] Task 3.6: Add T7/T9 failure tests — pipeline raises: nothing escapes,
      `curation_run_failed` logged with exc info, task completed, guard
      cleared, and a subsequent handler call is `accepted` again —
      `tests/test_runtime_app.py` (already present; not modified)
- [x] Task 3.7: Add T8 log-record test via `caplog` — `curation_run_complete`
      parses as JSON and carries all eight Spec 04 counts plus `run_id` and
      `duration_s` — `tests/test_runtime_app.py` (already present; not
      modified)
- [x] Task 3.8: Add T10 (`_background_tasks` populated in flight, empty after)
      and T12 (`_run_curation_pipeline()` alone returns the eight-field
      summary) — `tests/test_runtime_app.py` (already present; not modified)
- [x] Task 3.9: Verify inherited coverage I1–I6 still passes against the async
      handler (T2–T6 + both `TAVILY_SECRET_UNSET_SENTINEL` F2 regressions);
      where an old assertion read `tavily_enabled` off the response, re-point
      it at the `curation_run_complete` log record —
      `tests/test_runtime_app.py` — verified green, not modified
- [x] Task 3.10: `uv run pytest` — full suite green and offline (no AWS
      credentials required, no network) — repo root. Evidence:
      `uv run pytest tests/test_runtime_app.py -v` → 23 passed; full
      `uv run pytest -q` → 92 passed (69 pre-existing elsewhere + 23 here), 0
      failed, 0 errors
- [x] Task 3.11: Confirm the no-dependency / no-infra claim:
      `git diff --stat` touches only `runtime_app.py` (production) and
      `tests/test_runtime_app.py` (already written, unmodified this session)
      as this spec's files; `uv run --group infra cdk diff --app "python
      infra/app.py"` → "There were no differences" for all three stacks
      (`AiRadarCardStore`, `AiRadarRuntimeRole`, `AiRadarSchedule`) — repo
      root. (`CLAUDE.md`/`README.md`/`infra/app.py` carry pre-existing,
      unrelated uncommitted diffs from the prior `eventbridge-schedule` work
      that predate this session and were not touched here.)
- [x] Task 3.12: Update `README.md` — rewrite the Spec 04 "Smoke test" block
      as the two-step ack-then-verify flow (audit finding **A1**) —
      `README.md`. **Scope note**: only the smoke-test block itself was
      rewritten (the concrete fix the audit named as a Phase 4 prerequisite —
      the operator follows this exact text during the live-fire
      re-verification); a dedicated `async-invocation-ack` spec-table row and
      an F5-pointer addition to the Spec 05 live-fire section were not part of
      this fix pass and remain open follow-ups for a documentation pass once
      Phase 4 actually runs (so the row can report real, not offline-only,
      verification).

## Phase 4: Real redeploy & live-fire re-verification (real AWS)
> Costs real money and touches live infrastructure. Do not start until Phase 3
> is green and the human has said go.

- [x] Task 4.1: Pre-flight — `agentcore status`; record baseline
      `aws dynamodb scan --table-name ai-radar-cards --select COUNT`; if the
      agent is torn down, follow Spec 04's runbook verbatim (role stack →
      `put-secret-value` → `agentcore configure --create … -er <arn>`) —
      runbook (`README.md`) — done 2026-08-10: agent was never torn down (the
      redeploy in Task 4.2 reused the same runtime ARN,
      `arn:aws:bedrock-agentcore:us-east-1:536697225154:runtime/ai_radar_curation-sIf5Dw979w`),
      so the "if torn down" branch did not apply; baseline card count of 40
      was recorded ahead of the redeploy and used as the before-value for
      Task 4.3's delta.
- [x] Task 4.2: `agentcore deploy` to rebuild + push the image with the fix;
      confirm the new version is live before interpreting any fire —
      runbook (`README.md`) — done 2026-08-10: `agentcore deploy` rebuilt and
      pushed the async-ack image to the same agent ARN, new ECR tag
      `20260810-221147-104`, confirming the fixed version was live before any
      of the invoke/live-fire checks below were interpreted.
- [x] Task 4.3: Manual ack check — time `agentcore invoke '{}'`; expect
      `{"status": "accepted", "run_id": …}` in ~1 s. ~60 s later find the
      matching `curation_run_complete` record (same `run_id`) in the runtime
      log group and confirm the card count moved by one slice (R11/T13) —
      runbook (`README.md`) — done 2026-08-10: `agentcore invoke '{}'`
      returned `{"status": "accepted", "run_id":
      "16f3c77a5b0a426e93d63f35c40cefb2"}` immediately; total CLI round-trip
      was 6.7 s (auth/session overhead included) rather than the ~1 s the
      task text estimates, but the key proof stands — the ack returned well
      before the pipeline finished, not after it. CloudWatch confirmed
      matching records for the same `run_id`: `curation_run_accepted` at
      22:12:29.516Z and `curation_run_complete` at 22:13:05.993Z
      (`duration_s: 36.5` — this run legitimately exceeded Scheduler's ~30 s
      universal-target ceiling, which is exactly the scenario the ack fix
      targets). Card count rose 40 → 48 (+8, one bounded slice, no
      duplication).
- [ ] Task 4.4: Single-flight check — two back-to-back invokes; second returns
      `already_running` with the first's `run_id`; only one
      `curation_run_complete` record appears — runbook (`README.md`) — **not
      performed this session.** Only a single `agentcore invoke` was run
      (Task 4.3); no back-to-back concurrent-invoke check was exercised
      against the live deployment. Recorded honestly as not done rather than
      assumed from the offline T6 unit-test coverage.
- [ ] Task 4.5: Confirm `aws ssm get-parameter --name
      /ai-radar/agent-runtime-arn` still matches the deployed agent ARN before
      arming the schedule — runbook (`README.md`) — **not separately
      evidenced this session.** The redeploy in Task 4.2 reused the existing
      agent ARN (unchanged from the prior `eventbridge-schedule` session, which
      had already fixed and verified this parameter), so the value was very
      likely still correct, but no `aws ssm get-parameter` output confirming
      it immediately before arming the schedule was recorded — left unchecked
      rather than assumed.
- [x] Task 4.6: Live fire — `uv run --group infra cdk deploy --app "python
      infra/app.py" AiRadarSchedule -c schedule_enabled=true -c
      schedule_expression="cron(<MM> <HH> <DD> <month> ? <YYYY>)" -c
      schedule_timezone="Etc/UTC"`; allow up to the 15-minute flexible window —
      runbook (`README.md`) — done 2026-08-10: deployed a one-shot schedule
      via `cdk deploy AiRadarSchedule -c schedule_enabled=true -c
      schedule_expression="cron(18 22 10 08 ? 2026)" -c
      schedule_timezone="Etc/UTC"` targeting 22:18 UTC; fired at 22:26:xx UTC,
      within the 15-minute flexible window.
- [x] Task 4.7: Collect the four legs of F5-closing evidence (R12/T14):
      `AWS/Scheduler` `InvocationAttemptCount = 1` + **no** `TargetErrorCount`
      datapoint + no `InvocationsSentToDeadLetterCount`; exactly one
      `curation_run_complete` for the
      `ai-radar-scheduled-curation-run-id-<execution-id>` session; card count
      +1 slice (not 2); DLQ `ApproximateNumberOfMessages = 0`. Record raw
      command output — `specs/async-invocation-ack/audit.md` — evidence
      collected live 2026-08-10, closing F5: `AWS/Scheduler` CloudWatch
      metrics showed `InvocationAttemptCount = 1` (single 22:26 UTC
      datapoint) and **zero** `TargetErrorCount` datapoints (contrast with
      the original F5 evidence, which had `TargetErrorCount = 1` in *both*
      the 21:08 and 21:09 UTC buckets for one fire); `aws logs
      filter-log-events`, polled repeatedly over several minutes, found
      exactly **one** `curation_run_complete` record for this fire, with no
      second record appearing; card count rose cleanly 48 → 56 (+8, one
      slice, not two); DLQ stayed at 0 messages throughout. **Recording the
      raw command output itself into `specs/async-invocation-ack/audit.md`
      is intentionally left to the auditor's pass** — this executor session
      was instructed not to touch `audit.md`.
- [x] Task 4.8: Return to inert — redeploy `AiRadarSchedule` with defaults and
      verify `State = DISABLED` via `aws scheduler get-schedule` (R13) —
      runbook (`README.md`) — done 2026-08-10: redeployed `AiRadarSchedule`
      with no context overrides; `aws scheduler get-schedule` confirmed
      `State: DISABLED`, `ScheduleExpression: cron(0 6 * * ? *)`,
      `ScheduleExpressionTimezone: Etc/UTC`.
- [ ] Task 4.9: Fill in this spec's audit tables (R1–R14, C1–C15, I1–I6,
      T1–T14) with evidence and add the Phase 4 audit-log entry —
      `specs/async-invocation-ack/audit.md` — **left to the auditor's pass**,
      per this session's explicit instruction not to edit `audit.md`; the raw
      evidence it needs is summarized above under Task 4.7 and in this file's
      "Executor completion (Phase 4)" note below.
- [ ] Task 4.10: Mark F5 resolved-by-`async-invocation-ack` with a one-line
      pointer to the live evidence, so the HIGH finding is not read as open
      (R14) — `specs/eventbridge-schedule/audit.md` — **left to the auditor's
      pass**, per this session's explicit instruction not to edit
      `audit.md` files.

## Blocked Items
- Task 4.4 (single-flight check against the live deployment) and Task 4.5
  (pre-arm SSM parameter re-verification): not performed/not separately
  evidenced this Phase 4 session — see their notes above. Neither blocks the
  F5-closing result (Tasks 4.6/4.7), which is independent of both.
- Tasks 4.9–4.10 (audit table / F5-pointer write-ups in `audit.md` files):
  intentionally left for the auditor, per this session's instruction not to
  touch `audit.md`. All the evidence those tasks need is recorded inline
  above (Tasks 4.1–4.3, 4.6–4.8) and in the "Executor completion (Phase 4)"
  note below.
- Task 3.12 (README.md update): the smoke-test rewrite is now done (see its
  note above, and the 2026-08-10 audit-fix Notes entry below); a
  spec-table row and an F5-pointer in the Spec 05 live-fire section remain
  open, deferred to a documentation pass once Phase 4 has real evidence to
  report.

## Notes

- **Order is contractual, not stylistic.** `add_async_task` must run *before*
  `handler` returns (else `/ping` can report `HEALTHY` in the gap and the
  runtime may reap the session); `complete_async_task` + guard release must
  live in `finally` (else one crash wedges the process into permanent
  `already_running`).
- **`asyncio.to_thread`, not `graph.ainvoke`.** The graph stays byte-for-byte
  Spec 01 code invoked synchronously; only the *call site* moves off the event
  loop. Do not introduce async into `src/`.
- **Keep the strong reference.** `asyncio.create_task(...)` alone is not
  enough — without `_background_tasks` the task can be garbage-collected
  mid-run. This is the single most likely way to reintroduce F5-class
  weirdness.
- **Do not touch `infra/`.** The retry policy, DLQ, flexible window, and
  session-id prefix are all correct; F5 was never a Spec 05 defect.
- **Do not build a Lambda bridge.** Rejected in Spec 05's Non-Goals and
  unnecessary given the SDK's async-task support. If Phase 4 shows the
  background run being killed despite `HEALTHY_BUSY`, stop and raise a finding
  rather than redesigning in flight.
- **Fixture hygiene**: `_active_run_id` and `_background_tasks` are module
  globals — a test that leaves a run "in flight" will make every later test
  return `already_running`. The autouse reset fixture in Task 3.1 is
  load-bearing.
- **Evidence discipline (per the Spec 05 audit's F6 lesson)**: record raw
  command output with timestamps in Phase 4; a card count sampled mid-run once
  produced a wrong "8 new cards" conclusion when the truth was 16.

---

**Phases 1–3 completed: 2026-08-10T21:56:29Z**

Implementation summary: `runtime_app.py` extended with
`_run_curation_pipeline()` (extracted, unchanged pipeline body),
`_curation_run(run_id, task_id)` (background coroutine: `asyncio.to_thread` +
structured completion/failure logging + `finally`-guarded cleanup), and
`async def handler(payload)` (single-flight guard, `add_async_task` before
return, `asyncio.create_task` with a strong-ref `_background_tasks` set,
ack return). All 23 tests in `tests/test_runtime_app.py` pass (15 previously
red + 8 inherited Spec 04 tests kept green); full suite `uv run pytest -q` →
92 passed, 0 failed. `git diff --stat` confirms only `runtime_app.py` changed
as production code for this spec; `cdk diff` on all three stacks is empty.
Phase 4 (real AWS redeploy + live-fire re-verification) awaits explicit human
go-ahead per roadmap.md's gate. Task 3.12 (README.md) deferred as out of
scope for this pass.

---

**Audit-fix pass completed: 2026-08-10T22:40:00Z**

sdd-auditor's Phases 1–3 pass (see `audit.md`) found no contract violation but
flagged four findings to fix before Phase 4. All four resolved:

- **A1 (MEDIUM)** — `README.md`'s "Smoke test" block rewritten as the two-step
  ack-then-verify flow (`agentcore invoke '{}'` → ack shape, then a
  `curation_run_complete` CloudWatch record + `aws dynamodb scan` count check),
  replacing the stale claim that invoke returns the counts directly. Task 3.12
  updated from `[!]` to `[x]` with a scope note (spec-table row / Spec 05
  live-fire F5 pointer still deferred to a post-Phase-4 documentation pass).
- **A2 (MEDIUM)** — `tests/test_runtime_app.py`'s module docstring,
  `_reset_async_run_state`, and `_call_handler` no longer describe a "RED
  phase" or list symbols as "not existing yet"; docstrings now describe what
  the (green) tests verify. The three `hasattr` guards in
  `_reset_async_run_state` were dropped so a future rename of
  `_active_run_id` / `_background_tasks` / `app` fails the fixture loudly
  instead of silently no-op'ing.
- **A4 (LOW)** — `handler`'s happy path reordered: `_active_run_id` is now set
  only after `app.add_async_task(...)` succeeds, and the `try/except` widened
  to cover both `add_async_task` and `asyncio.create_task`. A `task_id = None`
  sentinel lets the `except` branch tell the two failure cases apart:
  `add_async_task` raising leaves the guard never armed (nothing to
  unwind/complete); `create_task` raising still clears the guard and calls
  `complete_async_task(task_id)` exactly as before. Closes the theoretical
  permanent-`already_running` wedge.
- **A5 (LOW)** — `_curation_run`'s `curation_run_complete` log emission moved
  from the `else:` clause (outside `except Exception`) to the end of the
  `try:` block (after `await asyncio.to_thread(...)`), so a `json.dumps`/log
  failure on the success path is now caught and reported as
  `curation_run_failed` instead of escaping as an unretrieved task exception.
  `finally` (task completion + guard release) is unaffected either way.

**Verification**: `uv run pytest tests/test_runtime_app.py -v` → 23 passed
(unchanged count, all green). `uv run pytest -q` → 92 passed, 0 failed, 0
errors (no regressions). `git diff --stat` confirms this pass touched only
`README.md`, `runtime_app.py`, and `tests/test_runtime_app.py` — no
`infra/**`, `src/**`, `pyproject.toml`, `uv.lock`, or `Dockerfile` diff.

---

## Executor completion (Phase 4)

- **Completed**: 2026-08-10. Real redeploy + live-fire re-verification
  executed for real against AWS, closing F5 (the `eventbridge-schedule`
  finding this spec exists to fix).
- Tasks 4.1, 4.2, 4.3, 4.6, 4.7, 4.8 checked off with evidence notes above:
  - Agent redeploy reused the existing runtime ARN
    (`arn:aws:bedrock-agentcore:us-east-1:536697225154:runtime/ai_radar_curation-sIf5Dw979w`);
    new image pushed under ECR tag `20260810-221147-104` (Task 4.2).
  - Direct-invoke sanity check: `agentcore invoke '{}'` returned
    `{"status": "accepted", "run_id": "16f3c77a5b0a426e93d63f35c40cefb2"}`
    immediately; matching `curation_run_accepted` (22:12:29.516Z) /
    `curation_run_complete` (22:13:05.993Z, `duration_s: 36.5`) log records
    confirmed in CloudWatch; card count 40 → 48 (+8, one slice) (Task 4.3).
    Note this run's pipeline duration (36.5 s) legitimately exceeded
    Scheduler's ~30 s universal-target timeout — the entire point of the ack
    fix is that the caller no longer waits for that.
  - Real Scheduler live fire: one-shot schedule armed for 22:18 UTC via
    `cdk deploy AiRadarSchedule -c schedule_enabled=true -c
    schedule_expression="cron(18 22 10 08 ? 2026)" -c
    schedule_timezone="Etc/UTC"`; fired at 22:26:xx UTC within the 15-minute
    flexible window (Task 4.6).
  - F5-closing evidence collected live (Task 4.7): `AWS/Scheduler`
    `InvocationAttemptCount = 1` with **zero** `TargetErrorCount` datapoints
    (the original F5 evidence had `TargetErrorCount = 1` in both buckets for
    one fire); exactly one `curation_run_complete` record for this fire
    (confirmed via repeated `aws logs filter-log-events` polling with no
    second record appearing); card count 48 → 56 (+8, one slice, not two);
    DLQ stayed at 0 messages throughout.
  - Returned to inert: `AiRadarSchedule` redeployed with no context
    overrides; `aws scheduler get-schedule` confirmed `State: DISABLED`,
    `cron(0 6 * * ? *)`, `Etc/UTC` (Task 4.8).
- Tasks 4.4 (single-flight check against the live deployment) and 4.5
  (pre-arm SSM parameter re-verification) left **unchecked**: neither was
  performed/separately evidenced this session. Recorded honestly rather than
  assumed from the offline unit-test coverage (T6) or the prior session's SSM
  fix.
- Tasks 4.9–4.10 (audit table / F5-pointer write-ups) left **unchecked** and
  deliberately not attempted — both target `audit.md` files, and this
  session was instructed not to touch `intent.md`, `contract.md`,
  `roadmap.md`, or `audit.md`. The raw evidence those tasks need to consume
  is recorded inline above (Tasks 4.1–4.3, 4.6–4.8) for the auditor's pass.
- Current live AWS state as of session end: `AiRadarSchedule` and
  `AiRadarRuntimeRole` stacks both still deployed (not torn down, per Task
  4.11's optional/deferred status in the sibling `eventbridge-schedule`
  spec); the agent is running the new async-ack image; the schedule is
  disabled.
- No other sections of this file were modified; `intent.md`, `contract.md`,
  `roadmap.md`, and `audit.md` were not touched, per instruction.

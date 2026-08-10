# Roadmap: async-invocation-ack

Four phases. Phases 1–3 are a single-file code change plus its offline tests;
**Phase 4 is real AWS** — a redeploy and a one-shot EventBridge Scheduler live
fire, modelled on
[`specs/eventbridge-schedule/roadmap.md`](../eventbridge-schedule/roadmap.md)
Phase 4, because "Scheduler now gets its ack before the timeout" is not
provable offline.

## Implementation Phases

### Phase 1: Extract the synchronous pipeline body
**Goal**: Separate "run the pipeline" from "answer the HTTP call", with zero
behavior change, so the async wrapper in Phase 2 has something to call.
**Dependencies**: None
**Estimated complexity**: Low

1. In `runtime_app.py`, move the current body of `handler` into a new
   module-level `_run_curation_pipeline() -> dict` — verbatim: `_build_store()`,
   `_build_discoverer()`, `build_graph(store, discoverer)`,
   `.invoke({"max_items": config.MAX_ITEMS})`, and the eight-field summary dict.
   Do not "improve" anything while moving it.
2. Add the module-level logger
   (`logging.getLogger("bedrock_agentcore.app.curation")`), documenting in a
   comment why it is a child of the SDK's own logger (inherits its
   StreamHandler + INFO level; no `basicConfig`, no reliance on `app.logger`).
3. Leave `handler` synchronous for this phase, delegating to
   `_run_curation_pipeline()` — the suite must still be green here, proving the
   extraction was behavior-preserving.
4. Update the module docstring's opening paragraph to name both specs and state
   the ~30 s Scheduler constraint that motivates what follows.

### Phase 2: Ack-now / work-later core
**Goal**: The entrypoint returns in well under a second while the pipeline runs
to completion in the background under a registered async task.
**Dependencies**: Phase 1
**Estimated complexity**: Medium

1. Add the module-level state: `_background_tasks: set[asyncio.Task]` (with the
   "asyncio only holds a weak ref" comment) and `_active_run_id: str | None`
   (with the "only mutated on the worker loop, hence no lock" comment).
2. Add `async def _curation_run(run_id, task_id) -> None`: time it,
   `await asyncio.to_thread(_run_curation_pipeline)`, log
   `curation_run_complete` (`json.dumps` of the eight counts + `run_id` +
   `duration_s`) on success; `logger.exception` a `curation_run_failed` record
   on any exception; in `finally` call `app.complete_async_task(task_id)` and
   clear `_active_run_id`. Never re-raise.
3. Convert `handler` to `async def`, keeping the single ignored `payload`
   parameter (the SDK's `_takes_context` only injects a second arg when it is
   literally named `context` — do not add one). Body: single-flight check →
   `run_id = uuid.uuid4().hex` → `_active_run_id = run_id` →
   `task_id = app.add_async_task("curation_run", {"run_id": run_id})` →
   `asyncio.create_task(_curation_run(run_id, task_id))` → add to
   `_background_tasks` + `add_done_callback(_background_tasks.discard)` → log
   `curation_run_accepted` → return the ack.
4. Order matters and is contractual: `add_async_task` happens **before**
   `create_task` and before the return (Behavior Guarantee 3). If `create_task`
   raises, undo the guard, `complete_async_task`, and let it propagate (a real
   5xx that Scheduler *should* retry).
5. Add the `already_running` branch returning the in-flight `run_id`.

### Phase 3: Tests, docs, and the deployment story
**Goal**: The offline suite proves every contract guarantee that can be proven
offline, and the operator docs describe the new two-step verification.
**Dependencies**: Phase 2
**Estimated complexity**: Medium

1. Rewrite `tests/test_runtime_app.py`'s T1 (which asserts the old
   counts-bearing return) for the ack shape; keep T2–T6 and the F2 sentinel
   regressions working against the async handler.
2. Add a small local helper in that test file to drive an async handler on an
   explicitly-created event loop and drain `runtime_app._background_tasks`
   (bounded wait, no bare `sleep`); no `pytest-asyncio`, no new dependency.
3. Add the new async-specific tests: latency-vs-blocking-pipeline, background
   completion, ping status `HEALTHY_BUSY` → `HEALTHY`, single-flight, failure
   containment, and the `curation_run_complete` log record's contents.
4. Update `README.md`: Spec 04 smoke-test block (ack, then verify), Spec 05
   live-fire block (F5 + this fix), spec table row, and a note that the
   in-repo `.bedrock_agentcore.yaml`-driven `agentcore invoke '{}'` sanity
   check is still valid but now proves *acceptance*, not *completion*.
5. Confirm the no-dependency claim: `uv sync` produces no `uv.lock` diff, and
   `git diff --stat` touches only `runtime_app.py`, `tests/test_runtime_app.py`,
   `README.md`, and `specs/`.

### Phase 4: Real redeploy + live-fire re-verification (Validation)
**Goal**: Prove against real AWS that a single scheduled fire now produces
**exactly one** curation run and no `TargetErrorCount` — the evidence that
closes F5 with the same rigor that opened it.
**Dependencies**: Phase 3
**Estimated complexity**: High

1. **Pre-flight**: confirm the agent is still up (`agentcore status`) and
   record the baseline `aws dynamodb scan --table-name ai-radar-cards
   --select COUNT`. If the agent was torn down, follow Spec 04's runbook
   verbatim (`cdk deploy AiRadarRuntimeRole` → `put-secret-value` the real
   Tavily key → `agentcore configure --create … -er <arn>` → `agentcore
   deploy`), re-reading the `execution_role: null` gotcha before any destroy.
2. **Rebuild + redeploy the image** (`agentcore deploy`) — the fix is inert
   until the container is rebuilt. Confirm the new image is live before
   drawing any conclusion from a fire.
3. **Manual ack check**: `agentcore invoke '{}'` must return
   `{"status": "accepted", "run_id": …}` visibly fast (time it). Then, ~60 s
   later, find the matching `curation_run_complete` record in the runtime log
   group with that exact `run_id`, and confirm the card count moved by one
   bounded slice.
4. **Single-flight check (optional but cheap)**: invoke twice back-to-back and
   confirm the second returns `already_running` with the first's `run_id`, and
   that only one `curation_run_complete` record appears.
5. **The live fire** — reuse Spec 05's methodology exactly: `aws ssm
   get-parameter --name /ai-radar/agent-runtime-arn` still matches the deployed
   agent, then a one-shot cron a few minutes out with an explicit year:
   ```bash
   uv run --group infra cdk deploy --app "python infra/app.py" AiRadarSchedule \
     -c schedule_enabled=true \
     -c schedule_expression="cron(<MM> <HH> <DD> <month> ? <YYYY>)" \
     -c schedule_timezone="Etc/UTC"
   ```
   Expect delivery up to 15 minutes late (flexible window) — that is correct
   behavior, not a failure.
6. **Collect the F5-closing evidence** (all four legs, no rounding up):
   - `AWS/Scheduler` metrics for the fire's hour:
     `InvocationAttemptCount = 1`, **`TargetErrorCount` with no datapoint**,
     `InvocationsSentToDeadLetterCount` no datapoint.
   - Runtime log group: **exactly one** `"Invocation completed successfully"`
     (now sub-second) and **exactly one** `curation_run_complete` record for
     that `ai-radar-scheduled-curation-run-id-<execution-id>` session.
   - `ai-radar-cards` count: baseline + one slice (e.g. +8), **not** two.
   - `ai-radar-schedule-dlq`: `ApproximateNumberOfMessages = 0`.
7. **Return to inert**: redeploy `AiRadarSchedule` with defaults so it is
   `DISABLED` again, and verify with `aws scheduler get-schedule`.
8. **Record the outcome** in this spec's `audit.md` Audit Log, and note in
   `specs/eventbridge-schedule/audit.md` that F5 is resolved by this spec (with
   the live evidence), so the next reader of that HIGH finding is not misled.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| AgentCore reaps the microVM after the ack, killing the background run despite `HEALTHY_BUSY` | Low | High | `HEALTHY_BUSY`-from-active-tasks is the SDK's documented mechanism for exactly this (its own integ example runs 30-minute tasks); `add_async_task` fires before the ack so there is no race window. Detector: Phase 4.3's ack-without-`curation_run_complete`. If it happens, escalate as a new finding — do **not** improvise a Lambda bridge in-flight |
| `asyncio.create_task` result garbage-collected mid-run | Med (if forgotten) | High | Module-level `_background_tasks` strong-ref set + `add_done_callback(discard)`; pinned in contract.md and asserted by a test |
| Blocking pipeline starves the event loop, `/ping` times out, runtime marks the agent unhealthy | Med | High | `asyncio.to_thread` keeps all blocking work off the loop; the SDK additionally runs async handlers on a dedicated worker loop so `/ping` on the main loop is unaffected. Detector: Phase 4 health/status checks |
| Operator ergonomics regression — `agentcore invoke '{}'` no longer prints counts, someone reads the ack as "nothing happened" | High | Low | Explicitly documented in README + contract Guarantee 7; the ack carries a `run_id` precisely to make the CloudWatch lookup one grep |
| Timeout is not really ~30 s (undocumented, could change) and a sub-second ack still errors | Low | High | Phase 4.6's `TargetErrorCount` leg is the direct detector; an ack at ~1 s leaves ~30× headroom, so any residual failure would point at a different cause (e.g. response parsing) and warrants a fresh finding, not a tweak |
| Rewriting `tests/test_runtime_app.py` silently drops a Spec 04 guarantee | Med | Med | Only T1 may change semantics; T2–T6 + both F2 sentinel regressions must survive intact. audit.md tracks them as inherited-coverage rows |
| Event-loop tests become flaky (task drained too early/late) | Med | Low | Drain via `loop.run_until_complete(asyncio.gather(*_background_tasks))` on a test-owned loop, not by sleeping; stub the pipeline so it is deterministic |
| Live fire spends real money / leaves the schedule enabled | Med | Med | One-shot cron with an explicit year (matches once), `SPIKE_MAX_ITEMS`-bounded slice, and an explicit Phase 4.7 return-to-inert step with a verification command |
| `agentcore destroy` deletes the CDK-owned execution role (Spec 04 gotcha) if teardown happens | Med | High | Restate the `execution_role: null` edit verbatim in the runbook step — do not merely cross-reference it |
| Scope creep into job-status APIs / run persistence / Spec 06 alarms | Med | Med | intent.md Non-Goals are explicit; contract.md exposes exactly two ack shapes and one log record |

## File Change Map

- `runtime_app.py` — **MODIFY** — extract `_run_curation_pipeline()`; add
  `logger`, `_background_tasks`, `_active_run_id`, `_curation_run(...)`; convert
  `handler` to `async def` returning the ack; update the module docstring.
  `_resolve_tavily_key` / `_build_store` / `_build_discoverer` / `app.run()`
  unchanged.
- `tests/test_runtime_app.py` — **MODIFY** — rewrite T1 for the ack shape, add
  the event-loop driving/draining helper, add the async/single-flight/failure/
  ping-status/log-record tests, keep T2–T6 and the F2 sentinel regressions.
- `README.md` — **MODIFY** — spec table row for `async-invocation-ack`; Spec 04
  smoke-test block rewritten as ack-then-verify; Spec 05 live-fire block gains
  the F5 story and its resolution; note that `agentcore invoke '{}'` now proves
  acceptance, not completion.
- `specs/async-invocation-ack/audit.md` — **MODIFY** — Phase 4 evidence and the
  final audit log entries.
- `specs/eventbridge-schedule/audit.md` — **MODIFY** (one line) — mark F5
  resolved-by-`async-invocation-ack` with a pointer, so the HIGH finding is not
  read as open.

**Explicitly NOT changed**: everything under `src/`, everything under `infra/`,
`Dockerfile`, `.dockerignore`, `pyproject.toml`, `uv.lock`,
`.bedrock_agentcore.yaml`, `run_curation.py`, `run_spike.py`, `run_chat.py`.

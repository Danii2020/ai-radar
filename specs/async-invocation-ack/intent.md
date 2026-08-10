# Intent: async-invocation-ack

> **Bugfix spec.** Fixes finding **F5** from
> [`specs/eventbridge-schedule/audit.md`](../eventbridge-schedule/audit.md)
> (2026-08-10, severity HIGH). The defect lives in **Spec 04
> (`runtime-packaging`)**'s deployed entrypoint (`runtime_app.py`), not in Spec
> 05's CDK construct — the construct emits exactly what its contract pins and
> is untouched here.

## Problem Statement

EventBridge Scheduler's **universal target is synchronous** and holds the
caller open until the target API returns. It has an **undocumented response
timeout of roughly 30 seconds**. Spec 04's curation entrypoint runs the whole
LangGraph pipeline inline — discover → dedup → summarize (several sequential
Bedrock Converse calls to Haiku) → rank → persist — and routinely takes
**25–35 s**. When Scheduler's wait crosses that hidden ceiling it records a
`TargetErrorCount` and **retries**, but the original `InvokeAgentRuntime` call
keeps running server-side to completion regardless. One scheduled fire can
therefore trigger **2–4 full duplicate curation runs**, each spending real
Haiku tokens and real Runtime wall-clock, and can drop a message in the DLQ of
a pipeline that is in fact working perfectly.

**Live evidence (2026-08-10 smoke test, recorded as F5):** a single schedule
execution produced two complete pipeline runs — requestIds `cf73941d…`
(33.04 s) and `e9d3fc89…` (24.89 s), both logging
`"Invocation completed successfully"`, both under the same Scheduler-supplied
session id `ai-radar-scheduled-curation-run-id-666a7a3b-…` — while
`AWS/Scheduler` metrics showed `TargetErrorCount = 1` in **both** the 21:08
and 21:09 one-minute buckets. CloudTrail's `GetWorkloadAccessToken` at
21:09:23 UTC lines up with the second attempt's start. `ai-radar-cards` gained
**16** cards (8 + 8), not 8. The retry sequence stopped at two only because
the return-to-inert deploy landed mid-sequence — an accident, not a
mitigation. An independent public writeup of the identical AWS behavior with
Bedrock AgentCore + EventBridge Scheduler reaches the same root cause and the
same fix (ack immediately, do the work in the background):
<https://danielleheberling.xyz/blog/scheduler-dlq-followup/>.

Who is affected: the **operator** (spurious DLQ messages that will make Spec
06's planned DLQ alarm cry wolf nightly on a healthy pipeline), the **budget**
(up to 4× Haiku + Runtime spend per fire against $500 of credits), and
**Spec 06 (observability)**, which cannot ship a "DLQ depth > 0 ⇒ pipeline
broken" alarm until this is true. F5 is the sole reason the daily cadence has
not been switched on.

The fix is a **same-file change to `runtime_app.py`**: register the curation
pipeline as a tracked background task via the SDK's already-available
`BedrockAgentCoreApp.add_async_task` / `complete_async_task`, return an
acknowledgement in well under a second, and let the pipeline run to completion
in the background while the runtime reports `HEALTHY_BUSY`. **No Lambda
bridge** (explicitly rejected as an in-flight redesign in
[`specs/eventbridge-schedule/intent.md`](../eventbridge-schedule/intent.md)
Non-Goals), no CDK change, no IAM change, no change under `src/`.

### Why a new spec rather than an in-place amendment to Spec 04

Spec 04 is `✅ Shipped & deploy-verified`; its `intent.md` / `contract.md` /
`audit.md` are a closed, audited record of what was built and proven on
2026-07-28. Editing its Behavior Guarantee 8 in place would rewrite history
and orphan `tests/test_runtime_app.py`'s existing assertions with no spec
trail. The house SDD pipeline (test-writer → executor → auditor →
documentarian) is also keyed on a single `specs/<feature-name>/` directory, so
a scoped bugfix gets a scoped spec. This spec therefore **supersedes exactly
two clauses of Spec 04's contract** and inherits the rest verbatim:

| Spec 04 clause | Status after this spec |
|---|---|
| Behavior Guarantee 8 — "the handler returns the run-summary dict … so `agentcore invoke '{}'` shows the counts" | **SUPERSEDED**. The handler returns an ack; the run summary moves to a structured CloudWatch log record. |
| Contract "Public API — `runtime_app.py`" `handler(payload) -> dict` (synchronous, returns counts) | **AMENDED**. Same name, same payload-ignoring behavior; now `async def`, returns the ack shape. |
| Behavior Guarantees 1–7, 9 (graph unchanged, env-only config, secret resolution, idempotent re-invoke, per-item resilience, least privilege, trust scoping, offline tests) | **UNCHANGED** and re-asserted here. |

## Goals

1. **Acknowledge fast.** The entrypoint returns an HTTP 200 JSON ack in well
   under one second (target < 1 s; hard requirement ≪ 30 s), so EventBridge
   Scheduler's universal-target call completes inside its ~30 s ceiling and
   never records a `TargetErrorCount` for a healthy run.
2. **Finish the work anyway.** The full, **unchanged** compiled curation graph
   still runs to completion for every accepted invocation, in a background
   task registered with `app.add_async_task(...)` so the runtime reports
   `HEALTHY_BUSY` and does not reap the session mid-run.
3. **Keep the run summary observable.** The counts Spec 04's handler used to
   return (`discovered`, `deduped`, `summarized`, `failed`, `persisted`,
   `discoverer_failures`, `store_failures`, `tavily_enabled`) are emitted as a
   single structured JSON log record at run completion, correlatable to the
   ack by a `run_id` present in both.
4. **Defend against a duplicate anyway (defense in depth).** If an invocation
   arrives while a curation run is already in flight in the same process, the
   entrypoint returns a *successful* ack marked `already_running` instead of
   starting a second pipeline — so even a retry that lands on the same session
   cannot double-spend on Haiku.
5. **Preserve everything else about Spec 04.** `payload` still ignored (all
   config env-driven), graph/nodes/state/interfaces still byte-for-byte
   unchanged, `bedrock_agentcore` + Secrets Manager `boto3` still confined to
   the composition root, Tavily secret resolution + RSS-only degradation
   unchanged, execution role and CDK untouched.
6. **Re-document the smoke test.** The README's `agentcore invoke '{}'`
   sanity-check workflow changes shape (an ack, not counts); the runbook gains
   the two-step "ack now, verify completion in CloudWatch + DynamoDB" flow and
   a pointer from the Spec 05 live-fire section to this fix.
7. **Prove it against real AWS.** Redeploy the agent and re-run a one-shot
   Scheduler live fire, demonstrating **exactly one** pipeline run per fire and
   `TargetErrorCount = 0` — this cannot be proven by unit tests alone.

## Success Criteria

- [ ] `runtime_app.handler` returns `{"status": "accepted", "run_id": "<hex>"}`
      (HTTP 200) without waiting for the pipeline; measured handler latency in
      the offline test is < 1 s with the pipeline stubbed to block.
- [ ] The curation pipeline still executes fully for every accepted
      invocation: the offline test drains the background task and asserts
      `build_graph(...).invoke({"max_items": MAX_ITEMS})` ran exactly once.
- [ ] `app.add_async_task(...)` is called **before** the handler returns and
      `complete_async_task(...)` exactly once when the run ends (success *or*
      failure), so `get_current_ping_status()` is `HEALTHY_BUSY` for the whole
      run and back to `HEALTHY` after — no ping-status race window between the
      ack and the task starting.
- [ ] A second invocation while a run is in flight returns
      `{"status": "already_running", "run_id": "<in-flight id>"}` with HTTP 200
      and starts **no** second pipeline.
- [ ] A crash inside the pipeline is logged with a stack trace, completes the
      async task, releases the single-flight guard, and never propagates as an
      HTTP error (the ack was already sent) — the next invocation still works.
- [ ] The run-completion log record contains all eight Spec 04 summary counts
      plus the matching `run_id`.
- [ ] `payload` remains ignored: `handler({})` and
      `handler({"anything": "here"})` behave identically (Spec 04 T2 preserved).
- [ ] `src/curation/**` and `src/spike/**` are byte-for-byte unchanged; `infra/**`
      is unchanged; `Dockerfile` / `.dockerignore` unchanged; no new runtime
      dependency (`asyncio`/`logging`/`uuid` are stdlib) and therefore no
      `uv.lock` churn.
- [ ] `uv run pytest` stays 100 % offline and green, including the existing
      Spec 04 tests that survive (T2–T6 and the F2 sentinel regressions).
- [ ] **(manual, real AWS)** After `agentcore deploy`, `agentcore invoke '{}'`
      returns the ack in ~1 s and CloudWatch later shows one
      `curation_run_complete` record with the same `run_id`, and the
      `ai-radar-cards` count rises by exactly one bounded slice.
- [ ] **(manual, real AWS)** A one-shot Scheduler live fire produces
      **exactly one** curation run (one `curation_run_complete` record for that
      session id), `AWS/Scheduler` `InvocationAttemptCount = 1` with
      `TargetErrorCount = 0` (no datapoint), DLQ depth 0, and the card count up
      by one slice, not two — i.e. F5 is closed with the same class of
      evidence that opened it.

## Non-Goals

- **A Lambda bridge between Scheduler and AgentCore.** Rejected in Spec 05's
  Non-Goals and still rejected: the SDK's async-task support removes the need.
- **Any change to `infra/`** — no CDK construct, stack, IAM, DLQ, retry-policy
  or schedule change. In particular `MaximumRetryAttempts` stays 3 (retries
  remain the correct behavior for a *genuinely* failed delivery) and the
  15-minute flexible window stays.
- **Any change under `src/`** — the graph, nodes, state, interfaces,
  discoverers, and `DynamoCardStore` are untouched. This is entrypoint
  plumbing.
- **A payload-driven sync/async switch.** Spec 04's payload-ignoring guarantee
  is preserved; there is no `{"mode": "sync"}` escape hatch, and no env flag
  either (an env flag could not be toggled per-invocation on a deployed agent,
  so it would be decorative).
- **Streaming / SSE responses, WebSockets, or `@app.ping` custom handlers** —
  the SDK's automatic `HEALTHY_BUSY`-from-active-tasks behavior is sufficient.
- **Job-status polling, a run-history API, or persisting run summaries.** The
  ack's `run_id` plus a CloudWatch log record is the whole observability
  surface here; anything richer belongs to Spec 06.
- **Turning the daily schedule on.** Going live stays a deliberate human act,
  post-verification.
- **Alarms/metrics on the new signals** — Spec 06.
- **Plane B / chat / AgentCore Memory** — untouched; no shared code, no shared
  contract beyond `Card`.
- **Multi-run concurrency or a job queue.** One run at a time per process is
  the desired behavior, not a limitation to design around.

## Constraints

- **Same-file fix.** All production changes land in `runtime_app.py` (the
  composition root / infra edge). `bedrock_agentcore` stays imported only
  there, per Spec 04's portability constraint and
  [`docs/architecture-principles.md`](../../docs/architecture-principles.md)
  §5 ("portable logic stays plain").
- **Plane A only.** No Plane B module is imported, read, or modified; `Card`
  remains the only cross-plane contract (architecture principles §1).
- **SDK APIs verified, not remembered.** `add_async_task(name, metadata) -> int`,
  `complete_async_task(task_id) -> bool`, the `@app.async_task` decorator, and
  the automatic `HEALTHY_BUSY` derivation from `_active_tasks` were verified
  against Context7's `/aws/bedrock-agentcore-sdk-python` docs **and** the
  installed `bedrock-agentcore==1.18.1` source
  (`.venv/.../bedrock_agentcore/runtime/app.py`) on 2026-08-10.
- **An async entrypoint runs on the SDK's dedicated worker loop**, which is a
  daemon thread running `loop.run_forever()`
  (`app._ensure_worker_loop` / `_run_worker_loop`, verified in 1.18.1). That
  loop outlives the request, which is precisely what makes
  `asyncio.create_task(...)` fire-and-forget safe here. A **module-level strong
  reference set** is mandatory — a bare `create_task` result can be
  garbage-collected mid-flight.
- **The pipeline is blocking** (boto3, `feedparser`, LangGraph sync nodes). It
  must be pushed off the event loop with `asyncio.to_thread(...)` so `/ping`
  stays responsive; the graph is invoked with the **unchanged** synchronous
  `graph.invoke(...)`, not `ainvoke`, to keep Spec 01's semantics identical.
- **No new dependency.** `asyncio`, `logging`, `uuid`, `json` are stdlib. No
  `pytest-asyncio`: offline tests drive an explicit event loop
  (`loop.run_until_complete(...)`) and drain the background task, keeping the
  suite plugin-free and deterministic.
- **Cost discipline ($500 credits).** The whole point is to stop paying for
  duplicate Haiku runs. `SPIKE_MAX_ITEMS` remains the per-run cost lever.
- **Redeploy required.** The fix only takes effect after an image rebuild
  (`agentcore deploy`); the `agentcore destroy` execution-role gotcha from
  Spec 04's runbook applies again and must be restated in the runbook steps,
  not merely cross-referenced.
- **Live-fire verification required.** "Does Scheduler get its ack before the
  timeout?" is unprovable offline; Phase 4 mirrors Spec 05's Phase 4 with real
  `cdk deploy` + one-shot cron + CloudWatch/metrics evidence.

## Prior Art

- **`specs/eventbridge-schedule/audit.md` F5 / F6 / F8** — the finding this
  spec closes, the corrected live numbers, and the contrasting DLQ evidence
  (a *validation*-class target error is non-retryable: 1 attempt → dropped →
  DLQ; F5's timeout class is retried).
- **`specs/eventbridge-schedule/roadmap.md` Phase 4 + Risk Assessment** — the
  live-fire methodology (one-shot cron a few minutes out, then return to
  inert) that Phase 4 here reuses; its risk row "Long curation run exceeds
  Scheduler's target invocation timeout → spurious retry → duplicate run" was
  rated *Impact: Low* and is now known to be wrong — the retry is not harmless.
- **`runtime_app.py` (Spec 04)** — the code being changed; its
  `_resolve_tavily_key` / `_build_store` / `_build_discoverer` seams and
  per-item-resilience posture are reused unchanged.
- **`tests/test_runtime_app.py` (Spec 04)** — the offline-mocking pattern
  (monkeypatch at the `runtime_app` module's own seam; fakes for store,
  discoverers, compiled graph, Secrets Manager client) that the new async
  tests extend rather than replace.
- **`bedrock_agentcore` 1.18.1** — `add_async_task` / `complete_async_task` /
  `@app.async_task` / `get_current_ping_status` / `get_async_task_info`, and
  the `tests_integ/async` example that runs 30-minute background tasks.
- **External:** <https://danielleheberling.xyz/blog/scheduler-dlq-followup/> —
  independent confirmation of the ~30 s universal-target timeout with Bedrock
  AgentCore and of the ack-then-background-task fix (including the
  module-level `_background_tasks` strong-reference detail).

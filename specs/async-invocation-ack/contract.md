# Contract: async-invocation-ack

Language: **Python 3.11+** (the backend is the only plane touched; no
TypeScript/CDK/infra surface changes in this spec). Dependencies managed by
**uv** — and this spec adds none.

All signatures below are pinned against the **installed**
`bedrock-agentcore==1.18.1`
(`.venv/lib/python3.*/site-packages/bedrock_agentcore/runtime/app.py`) and
Context7's `/aws/bedrock-agentcore-sdk-python` docs, both read 2026-08-10.

## Interfaces

### Public API — `runtime_app.py` (MODIFIED, same file, same module-level `app`)

Everything not listed here — `_resolve_tavily_key`, `_build_store`,
`_build_discoverer`, the module docstring's portability rules, `app.run()`
under `__main__` — is **unchanged from Spec 04** and is re-asserted, not
redefined.

```python
"""AgentCore Runtime entrypoint for the curation pipeline.

Spec 04 (runtime-packaging), amended by the `async-invocation-ack` spec: the
entrypoint ACKNOWLEDGES immediately and runs the pipeline as a background task,
because EventBridge Scheduler's universal target is synchronous with an
undocumented ~30s response timeout and the curation run takes 25-35s.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))   # unchanged (Spec 04)

from bedrock_agentcore import BedrockAgentCoreApp
# ... unchanged Spec 04 imports (curation.*, spike.config) ...

app = BedrockAgentCoreApp()

#: Child of the SDK's own configured logger ("bedrock_agentcore.app"), so run
#: records inherit its StreamHandler + INFO level and reach CloudWatch without
#: calling logging.basicConfig() or reaching into `app.logger`.
logger = logging.getLogger("bedrock_agentcore.app.curation")

#: Strong references to in-flight background tasks. Mandatory: asyncio only
#: holds a weak reference to a bare `create_task(...)` result, which can be
#: garbage-collected mid-run.
_background_tasks: set[asyncio.Task] = set()

#: `run_id` of the curation run currently in flight in THIS process, else None.
#: Single-flight guard. Read/written ONLY on the SDK's worker event loop
#: (handler + background coroutine), so no lock is needed.
_active_run_id: str | None = None


def _run_curation_pipeline() -> dict:
    """Run one full curation pass and return the Spec 04 run-summary dict.

    BLOCKING (boto3 + feedparser + sync LangGraph nodes) - always called via
    `asyncio.to_thread`, never on the event loop. This is verbatim the body of
    Spec 04's synchronous `handler`, extracted unchanged: build store +
    discoverer, invoke the UNCHANGED compiled graph with
    `max_items=spike.config.MAX_ITEMS`, return the counts.
    """


async def _curation_run(run_id: str, task_id: int) -> None:
    """Background task body: run the pipeline off-loop, log the summary, and
    always release both the async-task registration and the single-flight
    guard.

    Never re-raises: the HTTP response was already sent, so a raise here would
    only surface as an unretrievable task exception. Failures are logged with
    a stack trace via `logger.exception`.

    `task_id` is created by `handler` BEFORE it returns (see Behavior
    Guarantee 3) and completed here.
    """


@app.entrypoint
async def handler(payload) -> dict:
    """AgentCore entrypoint. `payload` is accepted (SDK signature) and IGNORED -
    all config is env-driven (Spec 04 Behavior Guarantee 2, preserved).

    Registers an async task, schedules `_curation_run` on the SDK's worker
    event loop, and returns an ACK immediately (<1s). Returns the
    `already_running` ack instead if a run is already in flight in this
    process.
    """
```

**Behavioral signature of `handler`:**

```python
# Accepted - a new run is scheduled
handler(payload)  -> {"status": "accepted",       "run_id": "9f2c1b7e4a..."}
# Rejected as duplicate - NO second pipeline started, still HTTP 200
handler(payload)  -> {"status": "already_running", "run_id": "<in-flight id>"}
```

### Data Models

No new dataclass, no change to `Card`, no change to `CurationState`. Two JSON
shapes are pinned instead — one on the wire, one in the logs.

```python
# 1. The invocation response (HTTP 200, application/json). This REPLACES Spec
#    04's counts-bearing response (that spec's Behavior Guarantee 8).
AckResponse = dict[str, str]
#   {"status": "accepted" | "already_running", "run_id": str}
#
#   run_id: uuid.uuid4().hex (32 lowercase hex chars). For "already_running"
#   it is the id of the run ALREADY in flight, so the operator can find the
#   one record that matters in CloudWatch.

# 2. The run-completion log record - a single INFO line, `json.dumps(...)` of:
#    (the eight Spec 04 summary fields, unchanged, plus correlation fields)
{
    "event": "curation_run_complete",   # literal; the grep anchor
    "run_id": "9f2c1b7e4a...",          # matches the ack
    "duration_s": 31.7,                 # float, 1 decimal
    "discovered": 50,
    "deduped": 42,
    "summarized": 8,
    "failed": 0,
    "persisted": 8,
    "discoverer_failures": 0,
    "store_failures": 0,
    "tavily_enabled": True,
}

# 3. The run-failure log record - emitted via logger.exception (stack trace
#    attached by the logging framework), payload:
{"event": "curation_run_failed", "run_id": "...", "duration_s": 12.3}

# 4. The run-start log record - emitted by `handler` before it returns, so a
#    reader can pair every ack with its run:
{"event": "curation_run_accepted", "run_id": "..."}
```

### State Changes

- **Process/module state (new):** `_background_tasks` (strong refs, entries
  discarded via `task.add_done_callback(_background_tasks.discard)`) and
  `_active_run_id` (single-flight guard). Both are per-microVM, per-process —
  they do **not** coordinate across AgentCore sessions or across concurrent
  microVMs, and are not persisted anywhere.
- **SDK state:** `app._active_tasks` gains one entry per accepted run via
  `app.add_async_task("curation_run", {"run_id": run_id})` and loses it via
  `app.complete_async_task(task_id)`. Consequence (SDK-owned, verified):
  `app.get_current_ping_status()` returns `PingStatus.HEALTHY_BUSY` while any
  entry exists, and `/ping` reports it — this is what tells AgentCore Runtime
  the session is doing work and must not be reaped.
- **Application state:** unchanged. `CurationState`, the graph, and DynamoDB
  writes behave exactly as in Specs 01–04; `curation.config.TAVILY_API_KEY` is
  still mutated by `_build_discoverer` (now inside the worker thread).
- **No CDK/CloudFormation state change.** `infra/**` is not touched, so
  `cdk diff` on `AiRadarRuntimeRole` / `AiRadarSchedule` / `CardStoreStack`
  must be empty.

## Behavior Guarantees

1. **Ack before the ceiling.** `handler` performs no network I/O and no
   pipeline work; it allocates a `run_id`, registers an async task, schedules
   the background coroutine and returns. Wall-clock is sub-second and
   independent of pipeline duration — comfortably inside EventBridge
   Scheduler's ~30 s universal-target timeout, which closes F5.
2. **The work still happens, in full.** Every `accepted` ack is followed by
   exactly one complete run of the **unchanged** compiled graph
   (`build_graph(store, discoverer).invoke({"max_items": config.MAX_ITEMS})`),
   with the same store, discoverer, and Tavily-secret resolution as Spec 04.
3. **No ping-status race.** `app.add_async_task(...)` is called **inside
   `handler`, before it returns** — not inside the coroutine — so `/ping` can
   never report `HEALTHY` in the window between the ack and the task actually
   starting on the loop. `app.complete_async_task(task_id)` is called exactly
   once, in `_curation_run`'s `finally`, on success and failure alike.
4. **Single-flight per process.** While `_active_run_id is not None`, any
   further invocation returns `{"status": "already_running", "run_id": <that
   id>}` with HTTP 200 and starts no pipeline. Because EventBridge Scheduler
   reuses one `RuntimeSessionId` (`ai-radar-scheduled-curation-run-id-<execution
   -id>`) for the retries of a single execution, and AgentCore routes a session
   to the same microVM, this is expected to catch same-execution retries too —
   defense in depth, not the primary fix (the primary fix is Guarantee 1).
   Distinct scheduled executions get distinct sessions and are unaffected.
5. **Failures stay contained.** An exception anywhere in the pipeline is
   caught in `_curation_run`, logged as `curation_run_failed` with a stack
   trace, the async task is completed and the guard released — so the process
   is immediately able to accept the next invocation. The exception is never
   re-raised (the HTTP response is long gone) and never becomes a 5xx.
   Spec 04's per-item/per-source resilience (Specs 01–03 try/except) is
   unchanged and still bounds most failures far below this level.
6. **Payload still ignored.** `handler({})` and `handler({"anything": 1})`
   produce identical behavior and identical ack shapes; nothing from the
   payload reaches the graph (Spec 04 Behavior Guarantee 2, preserved
   verbatim). There is no sync-mode escape hatch, by payload or by env.
7. **The counts are not lost, only relocated.** All eight Spec 04 summary
   fields appear in the `curation_run_complete` record, joined to the ack by
   `run_id`. `agentcore invoke '{}'` no longer shows counts; the runbook's
   two-step verification (ack → CloudWatch record + DynamoDB count) replaces
   it. This is the one deliberate regression in operator ergonomics and it is
   documented as such.
8. **Portability preserved.** `bedrock_agentcore`, `asyncio`, and the Secrets
   Manager `boto3` client remain confined to `runtime_app.py` (the composition
   root). `src/curation/**` and `src/spike/**` are byte-for-byte unchanged, so
   `run_curation.py` and `run_spike.py` keep working synchronously and the
   graph stays liftable (`docs/architecture-principles.md` §5).
9. **Plane separation preserved.** Plane A only; no Plane B import;
   `Card` remains the sole shared contract (`docs/architecture-principles.md`
   §1). No aggregate, repository, domain event, or new interface is
   introduced — none of the doc's triggers fire for a fix to an entrypoint's
   response timing.
10. **Infra untouched.** No file under `infra/` changes; the schedule keeps
    `MaximumRetryAttempts = 3`, the 15-minute flexible window, the 2 h max
    event age, and the DLQ — retries remain correct for genuine delivery
    failures, they simply stop being triggered by a healthy long run.
11. **Offline tests, again.** The whole suite stays network-free: the store,
    discoverers, `build_graph(...).invoke`, and `boto3.client` are
    monkeypatched at the `runtime_app` module seam. Tests drive the async
    handler on an explicitly-created event loop and drain
    `runtime_app._background_tasks` — no `pytest-asyncio`, no sleeps-as-
    synchronization beyond a bounded drain.

## Error Handling Contract

| Error Condition | Behavior | User Impact |
|---|---|---|
| Pipeline raises (Bedrock denied, table missing, unexpected bug) | `_curation_run` catches it, logs `curation_run_failed` + stack trace, completes the async task, clears `_active_run_id`; no re-raise | Invoker already got `accepted`; the failure is visible in CloudWatch, not in the response. Card count does not move. Next invocation works normally |
| A second invocation arrives mid-run (Scheduler retry, or a human racing the schedule) | Guard hit → `{"status": "already_running", "run_id": <in-flight>}`, HTTP 200, no second pipeline | No duplicate Haiku spend; Scheduler sees success |
| `asyncio.create_task` fails to schedule (loop gone — should not happen on the SDK worker loop) | Guard cleared, `complete_async_task` called, exception propagates → SDK returns HTTP 500 | Scheduler records a *genuine* target error and legitimately retries; nothing ran, so a retry is correct |
| Process/microVM torn down mid-run | Background task dies with it; already-persisted cards remain (per-item `upsert`), no partial-state corruption | A slice of that run is lost; the next scheduled run picks the items up again (dedup makes it safe) |
| Tavily secret missing/denied/empty/still the `TAVILY_SECRET_UNSET_SENTINEL` | Unchanged from Spec 04: `_resolve_tavily_key` → `""`, RSS-only, `tavily_enabled=False` — now reported in the log record instead of the response | Run completes RSS-only; no crash |
| One feed/seed/item/card fails | Unchanged from Specs 01–03: caught + counted; counters surface in `curation_run_complete` | Run completes; the counters tell the story |
| Invalid JSON posted to `/invocations` | SDK returns HTTP 400 before the handler runs (unchanged SDK behavior) | Malformed caller sees a 400; nothing runs |
| Runtime reaps the session despite `HEALTHY_BUSY` (hypothetical) | Detected only by live fire: an `accepted` ack with no matching `curation_run_complete` record | Escalation path: raise as a new finding; fallback is Spec 05's rejected Lambda-bridge redesign, which stays out of scope unless this actually happens |

## Dependencies

- **Internal (imported, not forked, all unchanged):**
  `curation.graph.build_graph`, `curation.dynamo.DynamoCardStore`,
  `curation.composite.CompositeDiscoverer`, `curation.local.RssDiscoverer`,
  `curation.tavily.TavilyDiscoverer`, `curation.interfaces.Discoverer`,
  `curation.config` (`TAVILY_SECRET_NAME`, `TAVILY_API_KEY`,
  `TAVILY_SECRET_UNSET_SENTINEL`), `spike.config` (`AWS_REGION`, `MAX_ITEMS`).
- **External (already in `pyproject.toml`, no version change):**
  `bedrock-agentcore>=1.18.1` — `BedrockAgentCoreApp`, `@app.entrypoint`,
  `add_async_task`, `complete_async_task`; `boto3>=1.35` (Secrets Manager,
  unchanged); `langgraph>=1.2.9` (unchanged).
- **New:** none. `asyncio`, `logging`, `json`, `uuid` are stdlib →
  `pyproject.toml` and `uv.lock` are untouched, and the container image's
  dependency layer is byte-identical.
- **Dev/test:** `pytest>=9.1.1` only. Explicitly **not** adding
  `pytest-asyncio`.

## Integration Points

- **Spec 04 (`runtime-packaging`)** — same file, same `app`, same Dockerfile,
  same execution role. Supersedes only its Behavior Guarantee 8 / handler
  return shape (see intent.md's supersession table). Requires an
  `agentcore deploy` (image rebuild) to take effect; the Spec 04
  `agentcore destroy` execution-role gotcha applies unchanged.
- **Spec 05 (`eventbridge-schedule`)** — consumer of the fix; its construct,
  target `Input`, session-id prefix, retry policy, and DLQ are unchanged. This
  spec closes audit finding **F5** against it and, once live-verified, unblocks
  switching the daily cadence on.
- **Spec 06 (observability, future)** — may now legitimately treat "message in
  `ai-radar-schedule-dlq`" as "delivery really failed", and can alarm on the
  absence of a `curation_run_complete` record per day. Not built here.
- **`run_curation.py` / `run_spike.py` / `run_chat.py`** — untouched and still
  synchronous; the local developer loop is unaffected.
- **`README.md`** — the Spec 04 smoke-test block and the Spec 05 live-fire
  block both make claims that this change invalidates; both need the two-step
  ack-then-verify flow and an F5-resolved pointer.

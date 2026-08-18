#!/usr/bin/env python3
"""AgentCore Runtime entrypoint for the curation pipeline.

Spec 04 (runtime-packaging), amended by the `async-invocation-ack` spec: the
entrypoint ACKNOWLEDGES immediately and runs the pipeline as a background task,
because EventBridge Scheduler's universal target is synchronous with an
undocumented ~30s response timeout and the curation run takes 25-35s.

Wraps the UNCHANGED compiled curation graph (Spec 01) in a BedrockAgentCoreApp
handler. Constructs DynamoCardStore (Spec 03) + a composite RSS+Tavily
Discoverer (Specs 01-02) from env only - same wiring as run_curation.py, minus
CLI/rich. The Tavily API key is resolved from Secrets Manager at invocation
time (never baked into the image); on failure the run degrades to RSS-only.

Portability: `bedrock_agentcore` and the Secrets Manager boto3 client are
imported ONLY here (the composition root / infra edge) - never in src/curation/
graph/node/state code, which stays byte-for-byte unchanged from Spec 01.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))   # same as run_curation.py

from bedrock_agentcore import BedrockAgentCoreApp

from curation import config as curation_config
from curation.composite import CompositeDiscoverer
from curation.dynamo import DynamoCardStore
from curation.graph import build_graph
from curation.interfaces import Discoverer
from curation.local import RssDiscoverer
from curation.metrics import emit_run_metrics
from curation.summary import RunSummary, build_run_summary
from curation.tavily import TavilyDiscoverer
from shared import config

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


def _configure_curation_logging() -> None:
    """Attach the SDK logger's handlers to the `curation` logger tree so
    node-level records (logger "curation.nodes") reach CloudWatch at INFO.

    Called once at import. Without it, `curation.*` INFO records are dropped
    (no handler anywhere on their chain; logging's lastResort only passes
    WARNING+). Infra knowledge stays HERE, in the composition root — node code
    just calls `logging.getLogger(__name__)`.
    """
    curation_logger = logging.getLogger("curation")
    curation_logger.setLevel(logging.INFO)
    for handler in app.logger.handlers:
        curation_logger.addHandler(handler)


_configure_curation_logging()


def _resolve_tavily_key(secret_name: str) -> str:
    """Fetch the Tavily API key from Secrets Manager. Returns "" on any
    failure, empty secret, OR the CDK-provisioned "not yet populated" sentinel
    (curation.config.TAVILY_SECRET_UNSET_SENTINEL) - the caller then degrades
    to RSS-only (mirrors run_curation.py). A freshly-`cdk deploy`'d secret is
    pinned to that sentinel until a human `put-secret-value`s the real key
    (Task 3.5); without this check it would resolve as a truthy-but-useless
    "key" and wrongly report tavily_enabled=True. boto3 is imported lazily
    here so pytest can patch this function without a real client. NEVER logs
    the secret value."""
    import boto3

    try:
        client = boto3.client("secretsmanager", region_name=config.AWS_REGION)
        response = client.get_secret_value(SecretId=secret_name)
    except Exception:  # missing secret, denied, throttled, etc. - degrade quietly
        return ""

    value = response.get("SecretString") or ""
    if value == curation_config.TAVILY_SECRET_UNSET_SENTINEL:
        return ""
    return value


def _build_store() -> DynamoCardStore:
    """DynamoCardStore() unconditionally - the Runtime is cloud-only (no JSON
    backend). Table name from curation.config.CARD_TABLE_NAME."""
    return DynamoCardStore()


def _build_discoverer() -> CompositeDiscoverer:
    """RssDiscoverer always; add TavilyDiscoverer.from_config() iff a key
    resolves from Secrets Manager. Resolves the secret, injects it into
    curation.config.TAVILY_API_KEY so from_config() (Spec 02, unchanged) sees
    it, then appends the Tavily source. Degrades to RSS-only otherwise."""
    key = _resolve_tavily_key(curation_config.TAVILY_SECRET_NAME)
    curation_config.TAVILY_API_KEY = key

    sources: list[Discoverer] = [RssDiscoverer()]
    if key:
        sources.append(TavilyDiscoverer.from_config())
    return CompositeDiscoverer(sources)


def _run_curation_pipeline(run_id: str) -> RunSummary:
    """Run one full curation pass and return its RunSummary.

    BLOCKING — always called via `asyncio.to_thread`. Same body as before
    (build store + discoverer, invoke the UNCHANGED compiled graph) with three
    changes: it takes `run_id`, passes it into the graph
    (`{"max_items": config.MAX_ITEMS, "run_id": run_id}`), times itself with
    `time.monotonic()`, and returns `build_run_summary(...)` instead of the
    eight-field dict. Tavily stats come from the composite discoverer's
    `searches()` / `credits_used()`."""
    store = _build_store()
    discoverer = _build_discoverer()
    graph = build_graph(store, discoverer)

    started = time.monotonic()
    final = graph.invoke({"max_items": config.MAX_ITEMS, "run_id": run_id})
    duration_s = time.monotonic() - started

    return build_run_summary(
        run_id=run_id,
        duration_s=duration_s,
        state=final,
        tavily_searches=discoverer.searches(),
        tavily_credits=discoverer.credits_used(),
        discoverer_failures=discoverer.failures(),
        store_failures=store.failures(),
        tavily_enabled=bool(curation_config.TAVILY_API_KEY),
    )


async def _curation_run(run_id: str, task_id: int) -> None:
    """Background task body: run the pipeline off-loop, log the summary, emit
    metrics, and always release both the async-task registration and the
    single-flight guard.

    Never re-raises: the HTTP response was already sent, so a raise here would
    only surface as an unretrievable task exception. Failures are logged with
    a stack trace via `logger.exception`.

    `task_id` is created by `handler` BEFORE it returns (see Behavior
    Guarantee 3) and completed here.
    """
    global _active_run_id

    started = time.monotonic()
    try:
        summary = await asyncio.to_thread(_run_curation_pipeline, run_id)
        # Success-path log emission lives INSIDE this try (not an `else:`
        # outside it), so a bug in the log call itself - e.g. a
        # non-serializable value in `summary` breaking `json.dumps` - is
        # caught by the same `except Exception` below and reported as
        # `curation_run_failed` instead of escaping as an unretrieved task
        # exception (finding A5). `finally` still releases the task/guard
        # either way. `summary.to_dict()` is a strict SUPERSET of the eight
        # async-invocation-ack fields (Spec 06 Behavior Guarantee 2).
        logger.info(
            json.dumps({"event": "curation_run_complete", **summary.to_dict()})
        )
        # Metrics emission gets its OWN try/except, separate from the outer
        # one: a metrics failure must never turn a successful run into
        # `curation_run_failed` (cf. async-invocation-ack finding A5, which
        # put the success log INSIDE the try on purpose - the same reasoning
        # applies here one level deeper).
        try:
            emit_run_metrics(summary)
        except Exception as exc:
            logger.warning(
                json.dumps(
                    {
                        "event": "curation_metrics_failed",
                        "run_id": run_id,
                        "error": str(exc),
                    }
                )
            )
    except Exception:
        duration_s = time.monotonic() - started
        logger.exception(
            json.dumps(
                {
                    "event": "curation_run_failed",
                    "run_id": run_id,
                    "duration_s": round(duration_s, 1),
                }
            )
        )
    finally:
        app.complete_async_task(task_id)
        _active_run_id = None


@app.entrypoint
async def handler(payload) -> dict:
    """AgentCore entrypoint. `payload` is accepted (SDK signature) and IGNORED -
    all config is env-driven (Spec 04 Behavior Guarantee 2, preserved).

    Registers an async task, schedules `_curation_run` on the SDK's worker
    event loop, and returns an ACK immediately (<1s). Returns the
    `already_running` ack instead if a run is already in flight in this
    process.
    """
    global _active_run_id

    if _active_run_id is not None:
        return {"status": "already_running", "run_id": _active_run_id}

    run_id = uuid.uuid4().hex
    task_id = None

    try:
        task_id = app.add_async_task("curation_run", {"run_id": run_id})
        _active_run_id = run_id
        task = asyncio.create_task(_curation_run(run_id, task_id))
    except Exception:
        # Widened past just `create_task`: if `add_async_task` itself raises,
        # `task_id` is still None (no task registered, guard never armed), so
        # only the guard clear runs - no dangling task-registry entry.
        # `_active_run_id` is armed AFTER `add_async_task` succeeds, so a
        # failure there can never leave the guard set with nothing scheduled
        # to clear it (the wedge finding A4 guards against).
        _active_run_id = None
        if task_id is not None:
            app.complete_async_task(task_id)
        raise

    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    logger.info(json.dumps({"event": "curation_run_accepted", "run_id": run_id}))

    return {"status": "accepted", "run_id": run_id}


if __name__ == "__main__":
    app.run()

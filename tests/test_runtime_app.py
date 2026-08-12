"""Offline unit tests for the AgentCore Runtime entrypoint.

Spec: specs/async-invocation-ack/{intent.md,contract.md} — the bugfix that
supersedes Spec 04 (runtime-packaging)'s synchronous, counts-returning
`handler` with an async ack-now/work-later entrypoint (closes
specs/eventbridge-schedule/audit.md finding F5). Covers contract.md's
Behavior Guarantees 1-9, 11, the Error Handling Contract, and
intent.md's Success Criteria; audit.md Test Coverage T1-T12 plus the
inherited Spec 04 coverage I1-I6.

Extended by specs/run-observability/contract.md §8 (`_configure_curation_
logging`, `_run_curation_pipeline(run_id) -> RunSummary`, the
`curation_run_complete` superset, the guarded `emit_run_metrics` call) and
audit.md Test Coverage T22-T27. The pre-existing T8/T12 tests are UPDATED
in place (per tasks.md Task 4.7 / the "old record is a strict subset of the
new one" guarantee) rather than duplicated; every other Spec 04/
async-invocation-ack test below is otherwise unchanged in behavior.

100% offline: `DynamoCardStore`, `RssDiscoverer`, `TavilyDiscoverer`, and
`build_graph(...).invoke` are monkeypatched at the `runtime_app` module's own
seam (the composition root) - no real boto3/DynamoDB/Secrets Manager/Bedrock
call is ever made. `_resolve_tavily_key`'s own real implementation is
exercised directly against a fake `boto3.client(...)` (no real AWS network
call either). `app.add_async_task` / `app.complete_async_task` /
`app.get_current_ping_status()` are exercised against the REAL
`BedrockAgentCoreApp` instance `runtime_app.app` (in-process bookkeeping
only, no network) — that is the SDK behavior this spec's fix depends on, not
a seam to fake.

No `pytest-asyncio` (contract constraint): every async test drives an
explicit, test-owned event loop (`loop.run_until_complete(...)`) and drains
`runtime_app._background_tasks` itself via `asyncio.gather(...)`.

`runtime_app.handler` is the async, ack-now/work-later `handler` implemented
by this spec: it returns `{"status": "accepted"|"already_running", "run_id":
...}` immediately and schedules the curation pipeline as a background task
via `runtime_app._curation_run`, tracked in `runtime_app._background_tasks`
and single-flighted through `runtime_app._active_run_id`. These tests drive
that handler to completion on a test-owned loop, drain the background task,
and assert on the ack shape, the `curation_run_complete`/`curation_run_failed`
log records, and the SDK's async-task bookkeeping (`add_async_task` /
`complete_async_task` / `get_current_ping_status()`).

RED phase (specs/run-observability additions only): the async-orchestration
tests (T1-T11, I1-I5) stub `_run_curation_pipeline` wholesale via
`_blocking_pipeline_stub`/`_raising_pipeline_stub`, which now call the stub
with a `run_id` positional argument (per contract.md §8) — until
`runtime_app._curation_run` is updated to call
`asyncio.to_thread(_run_curation_pipeline, run_id)`, those stubs are invoked
with the OLD zero-arg call convention and fail with a `TypeError` (missing
required positional argument), a legitimate RED signal. The tests exercising
the REAL pipeline (T22/T23 and the new metrics tests) additionally require
`curation.summary`/`curation.metrics` to exist and fail earlier (import
error) until specs/run-observability Phase 1 lands.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import logging
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

# runtime_app.py lives at the REPO ROOT (sibling to run_curation.py), not under
# src/ - tests/conftest.py only puts src/ on sys.path, so add the repo root too
# (mirrors tests/test_infra.py's sys.path.insert pattern for infra/).
sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
import pytest

import curation.config as curation_config

import runtime_app
from bedrock_agentcore import PingStatus

CURATION_LOGGER_NAME = "bedrock_agentcore.app.curation"


@dataclass
class _FakeRunSummary:
    """Minimal `RunSummary`-shaped test double (`.to_dict()`), used to stub
    `_run_curation_pipeline(run_id)` for tests that only care about async
    orchestration (T1-T11, I1-I5) — kept LOCAL (not importing
    `curation.summary.RunSummary`) so this file's collection does not depend
    on that module's existence for those tests. Tests that exercise the REAL
    pipeline (T22/T23, the metrics tests) import the real `RunSummary`."""

    payload: dict

    def to_dict(self) -> dict:
        return dict(self.payload)


def _make_summary_payload(run_id: str, **overrides) -> dict:
    """The full Spec 06 `RunSummary.to_dict()` shape (21 fields, contract.md
    §2) with representative defaults; `overrides` lets a test change specific
    fields without repeating the whole shape."""
    payload = {
        "run_id": run_id,
        "duration_s": 31.7,
        "discovered": 5,
        "discovered_rss": 5,
        "discovered_tavily": 0,
        "discovered_by_source": {"Test Feed": 5},
        "deduped": 4,
        "summarized": 3,
        "failed": 0,
        "persisted": 3,
        "cards_written": 3,
        "input_tokens": 0,
        "output_tokens": 0,
        "tavily_searches": 0,
        "tavily_credits": 0,
        "discoverer_failures": 0,
        "store_failures": 0,
        "tavily_enabled": False,
        "estimated_bedrock_cost_usd": 0.0,
        "estimated_tavily_cost_usd": 0.0,
        "estimated_cost_usd": 0.0,
    }
    payload.update(overrides)
    return payload


# --- Fakes (in-memory doubles for the injected seams) -----------------------


class FakeCardStore:
    """In-memory CardStore double: implements the Spec 01 CardStore Protocol
    (dedup_filter/upsert) plus DynamoCardStore's `.failures()` (Spec 03) that
    the pipeline's summary reads."""

    def __init__(self, failure_count: int = 0):
        self._failure_count = failure_count

    def dedup_filter(self, items):
        return list(items)

    def upsert(self, cards):
        pass

    def failures(self):
        return self._failure_count


class FakeDiscoverer:
    """In-memory Discoverer double matching CompositeDiscoverer's shape
    (discover/failures/searches/credits_used/sources) that the pipeline's
    summary reads. `searches`/`credits_used` are Spec 06 additions
    (contract.md §7), defaulting to 0 like the real CompositeDiscoverer does
    for sources that don't expose them."""

    def __init__(self, failure_count: int = 0, sources=None, searches: int = 0, credits_used: int = 0):
        self._failure_count = failure_count
        self.sources = sources if sources is not None else []
        self._searches = searches
        self._credits_used = credits_used

    def discover(self):
        return []

    def failures(self):
        return self._failure_count

    def searches(self):
        return self._searches

    def credits_used(self):
        return self._credits_used


class FakeRssDiscoverer:
    """Stand-in for curation.local.RssDiscoverer - zero-arg constructor,
    matching `_build_discoverer`'s documented `RssDiscoverer()` call."""

    def discover(self):
        return []


def _make_recording_tavily_discoverer_class():
    """Fresh fake TavilyDiscoverer class per test (avoids cross-test shared
    state). `from_config()` records the value of `curation.config.
    TAVILY_API_KEY` at call time, so a test can prove the resolved secret was
    injected BEFORE `from_config()` ran (contract's ordering guarantee)."""

    class _FakeTavilyDiscoverer:
        from_config_calls: list[str] = []

        def discover(self):
            return []

        @classmethod
        def from_config(cls):
            cls.from_config_calls.append(curation_config.TAVILY_API_KEY)
            return cls()

    return _FakeTavilyDiscoverer


def _make_forbidden_tavily_discoverer_class():
    """Fake TavilyDiscoverer whose `from_config()` fails the test if called -
    used to prove `_build_discoverer` never wires Tavily when no key resolves."""

    class _ForbiddenTavilyDiscoverer:
        @classmethod
        def from_config(cls):
            raise AssertionError(
                "TavilyDiscoverer.from_config() must not be called when no "
                "Tavily key resolves from Secrets Manager"
            )

    return _ForbiddenTavilyDiscoverer


class FakeCompiledGraph:
    """Stand-in for `build_graph(store, discoverer)`'s return value. Records
    every `.invoke(...)` call's input and returns a caller-controlled final
    CurationState-shaped dict."""

    def __init__(self, final_state: dict, invoke_calls: list):
        self._final_state = final_state
        self._invoke_calls = invoke_calls

    def invoke(self, state_input):
        self._invoke_calls.append(state_input)
        return self._final_state


def _fake_build_graph(final_state: dict, invoke_calls: list):
    def _build(store, discoverer):
        return FakeCompiledGraph(final_state, invoke_calls)

    return _build


class _StaticSecretsClient:
    """Fake Secrets Manager client double - a successful `get_secret_value`."""

    def __init__(self, secret_string: str):
        self._secret_string = secret_string

    def get_secret_value(self, SecretId):
        return {"SecretString": self._secret_string}


class _RaisingSecretsClient:
    """Fake Secrets Manager client double that always raises (denied/missing
    secret, throttled, etc.)."""

    def __init__(self, message: str):
        self._message = message

    def get_secret_value(self, SecretId):
        raise RuntimeError(self._message)


def _patch_pipeline_seams(monkeypatch, final_state: dict, invoke_calls: list, max_items: int = 7):
    """Patch the store/discoverer/graph seams `_run_curation_pipeline` calls,
    the way Spec 04's tests did, for tests that care about the REAL
    `_run_curation_pipeline`/graph-wiring path (T3, T22, T23, and the
    Tavily-flag-via-log-record tests) rather than stubbing the pipeline
    function wholesale."""
    monkeypatch.setattr(runtime_app, "_build_store", lambda: FakeCardStore())
    monkeypatch.setattr(runtime_app, "_build_discoverer", lambda: FakeDiscoverer())
    monkeypatch.setattr(runtime_app, "build_graph", _fake_build_graph(final_state, invoke_calls))
    monkeypatch.setattr(runtime_app.config, "MAX_ITEMS", max_items)


def _blocking_pipeline_stub(release_event: threading.Event, calls: list, payload_overrides: dict | None = None):
    """A `_run_curation_pipeline(run_id)` stand-in that blocks (on a real
    thread, via `asyncio.to_thread`) until the test releases `release_event` -
    lets a test observe state (ping status, `_active_run_id`,
    `_background_tasks`) WHILE a run is still in flight, deterministically,
    with no sleep-based synchronization. Returns a `_FakeRunSummary` carrying
    the `run_id` it was called with (contract.md §8:
    `_run_curation_pipeline(run_id) -> RunSummary`)."""

    def _pipeline(run_id):
        calls.append(run_id)
        released = release_event.wait(timeout=5)
        assert released, "test-controlled release_event was never set (deadlock guard)"
        return _FakeRunSummary(_make_summary_payload(run_id, **(payload_overrides or {})))

    return _pipeline


def _raising_pipeline_stub(exc: Exception, calls: list | None = None):
    def _pipeline(run_id):
        if calls is not None:
            calls.append(run_id)
        raise exc

    return _pipeline


def _parse_json_lines(text: str) -> list[dict]:
    """Parse every non-blank line of `text` as JSON, skipping ones that
    aren't (defensive against stray non-JSON stderr output)."""
    parsed = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            parsed.append(json.loads(line))
        except (TypeError, ValueError):
            continue
    return parsed


@pytest.fixture(autouse=True)
def _reset_tavily_api_key():
    """`_build_discoverer` mutates the shared `curation.config.TAVILY_API_KEY`
    module global as a side effect - restore it so tests never leak state."""
    original = curation_config.TAVILY_API_KEY
    yield
    curation_config.TAVILY_API_KEY = original


@pytest.fixture(autouse=True)
def _reset_async_run_state():
    """`_active_run_id` and `_background_tasks` are module globals (per the
    contract's State Changes section); a test that leaves a run "in flight"
    would make every later test see `already_running`. Also resets the real
    `app`'s async-task registry so ping-status assertions never leak across
    tests. No `hasattr` guards: `_active_run_id` / `_background_tasks` / `app`
    are load-bearing contract symbols that must always exist, so a rename or
    removal should fail this fixture loudly (`AttributeError`) rather than
    silently no-op."""

    def _clear():
        runtime_app._active_run_id = None
        runtime_app._background_tasks.clear()
        runtime_app.app._active_tasks.clear()

    _clear()
    yield
    _clear()


@pytest.fixture
def loop():
    """A test-owned event loop - the contract explicitly forbids
    `pytest-asyncio`; tests drive the async `handler` themselves."""
    lp = asyncio.new_event_loop()
    try:
        yield lp
    finally:
        lp.close()


def _call_handler(lp: asyncio.AbstractEventLoop, payload):
    """Drive `runtime_app.handler(payload)` to completion on `lp`. `handler`
    is `async def`, so calling it returns a coroutine that
    `run_until_complete` executes and returns the resulting ack dict."""
    return lp.run_until_complete(runtime_app.handler(payload))


def _drain(lp: asyncio.AbstractEventLoop):
    """Run every currently-tracked background task to completion on `lp` -
    the contract's mandated drain pattern
    (`loop.run_until_complete(asyncio.gather(*runtime_app._background_tasks))`),
    no bare sleeps."""
    tasks = tuple(runtime_app._background_tasks)
    if tasks:
        lp.run_until_complete(asyncio.gather(*tasks))


def _find_json_log_record(caplog, event_name: str):
    """Return the first `caplog` record whose message is a JSON object with
    `"event": event_name`, or `None`. Mirrors how an operator would grep
    CloudWatch for `curation_run_complete` / `curation_run_failed` /
    `curation_run_accepted`."""
    for record in caplog.records:
        try:
            payload = json.loads(record.getMessage())
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict) and payload.get("event") == event_name:
            return payload, record
    return None, None


# =============================================================================
# T1 - handler returns an ack (accepted + 32-hex run_id), no count fields
# =============================================================================


def test_handler_returns_accepted_ack_with_32_char_hex_run_id_and_no_count_fields(loop, monkeypatch):
    release_event = threading.Event()
    monkeypatch.setattr(
        runtime_app, "_run_curation_pipeline", _blocking_pipeline_stub(release_event, calls=[])
    )

    result = _call_handler(loop, {})

    assert result["status"] == "accepted"
    run_id = result["run_id"]
    assert isinstance(run_id, str)
    assert len(run_id) == 32
    assert all(c in "0123456789abcdef" for c in run_id)
    # This REPLACES Spec 04's counts-bearing response (superseded BG8) - none
    # of the old summary keys belong on the ack.
    for count_key in (
        "discovered",
        "deduped",
        "summarized",
        "failed",
        "persisted",
        "discoverer_failures",
        "store_failures",
        "tavily_enabled",
    ):
        assert count_key not in result

    release_event.set()
    _drain(loop)


# =============================================================================
# T2 - handler returns in well under 1s while the pipeline is stubbed to block
# =============================================================================


def test_handler_returns_before_pipeline_completes_even_when_pipeline_blocks(loop, monkeypatch):
    release_event = threading.Event()
    calls: list = []
    monkeypatch.setattr(
        runtime_app, "_run_curation_pipeline", _blocking_pipeline_stub(release_event, calls)
    )

    import time

    started = time.monotonic()
    result = _call_handler(loop, {})
    elapsed = time.monotonic() - started

    assert result["status"] == "accepted"
    # Contract: target < 1s, hard requirement << 30s. The pipeline stub is
    # still blocked on `release_event`, so any measurable wait here would mean
    # the handler waited on the pipeline instead of scheduling it.
    assert elapsed < 1.0, f"handler took {elapsed:.3f}s while the pipeline was blocked"

    release_event.set()
    _drain(loop)


# =============================================================================
# T3 - the background task invokes the (unchanged) compiled graph exactly
# once, with {"max_items": config.MAX_ITEMS, "run_id": <the ack's run_id>}
# (run_id addition: specs/run-observability contract.md §8)
# =============================================================================


def test_background_task_invokes_graph_exactly_once_with_configured_max_items_and_run_id(loop, monkeypatch):
    final_state = {
        "discovered": 12,
        "deduped": 9,
        "summarized": 8,
        "failed": 1,
        "cards": [object(), object(), object()],
    }
    invoke_calls: list = []
    curation_config.TAVILY_API_KEY = ""
    _patch_pipeline_seams(monkeypatch, final_state, invoke_calls, max_items=42)

    result = _call_handler(loop, {})
    _drain(loop)

    assert invoke_calls == [{"max_items": 42, "run_id": result["run_id"]}]


# =============================================================================
# T4 - add_async_task happens before handler returns (no ping-status race)
# =============================================================================


def test_add_async_task_registered_before_handler_returns_and_ping_is_healthy_busy(loop, monkeypatch):
    release_event = threading.Event()
    monkeypatch.setattr(
        runtime_app, "_run_curation_pipeline", _blocking_pipeline_stub(release_event, calls=[])
    )

    result = _call_handler(loop, {})

    assert result["status"] == "accepted"
    # The pipeline stub is still blocked, so `complete_async_task` cannot have
    # run yet - the ONLY way ping status can already be HEALTHY_BUSY here is
    # if `add_async_task` ran synchronously inside `handler`, before return.
    assert runtime_app.app.get_current_ping_status() == PingStatus.HEALTHY_BUSY

    release_event.set()
    _drain(loop)


# =============================================================================
# T5 - ping status/active-task count go back to idle once the run completes
# =============================================================================


def test_ping_status_and_active_task_count_return_to_idle_after_run_completes(loop, monkeypatch):
    release_event = threading.Event()
    monkeypatch.setattr(
        runtime_app, "_run_curation_pipeline", _blocking_pipeline_stub(release_event, calls=[])
    )

    _call_handler(loop, {})
    release_event.set()
    _drain(loop)

    assert runtime_app.app.get_current_ping_status() == PingStatus.HEALTHY
    assert runtime_app.app.get_async_task_info()["active_count"] == 0


# =============================================================================
# T6 - single-flight: a second invocation mid-run is rejected, no 2nd pipeline
# =============================================================================


def test_second_invocation_while_run_in_flight_returns_already_running_and_starts_no_second_pipeline(
    loop, monkeypatch
):
    release_event = threading.Event()
    calls: list = []
    monkeypatch.setattr(
        runtime_app, "_run_curation_pipeline", _blocking_pipeline_stub(release_event, calls)
    )

    first = _call_handler(loop, {})
    assert first["status"] == "accepted"

    second = _call_handler(loop, {"anything": "here"})
    assert second == {"status": "already_running", "run_id": first["run_id"]}

    release_event.set()
    _drain(loop)

    # Exactly one pipeline execution total - the guard, not luck, prevented a
    # second one.
    assert len(calls) == 1


# =============================================================================
# T7 - a pipeline crash never escapes; the guard is released for next time
# =============================================================================


def test_pipeline_exception_does_not_escape_and_next_invocation_still_works(loop, monkeypatch):
    monkeypatch.setattr(
        runtime_app,
        "_run_curation_pipeline",
        _raising_pipeline_stub(RuntimeError("Bedrock access denied")),
    )

    result = _call_handler(loop, {})
    assert result["status"] == "accepted"

    # Draining must not raise - `_curation_run` is contractually required to
    # swallow the exception (Behavior Guarantee 5 / Error Handling row 1).
    _drain(loop)

    assert runtime_app._active_run_id is None
    assert runtime_app.app.get_current_ping_status() == PingStatus.HEALTHY

    # The process accepts the next invocation normally - it is not wedged.
    # Give the stub an already-set event so this second run completes
    # immediately (no need to block/release again).
    already_set = threading.Event()
    already_set.set()
    monkeypatch.setattr(
        runtime_app, "_run_curation_pipeline", _blocking_pipeline_stub(already_set, calls=[])
    )

    second = _call_handler(loop, {})
    assert second["status"] == "accepted"
    assert second["run_id"] != result["run_id"]

    _drain(loop)


# =============================================================================
# T9 - curation_run_failed is logged with a stack trace on pipeline failure
# =============================================================================


def test_curation_run_failed_logged_with_exception_info_on_pipeline_failure(loop, monkeypatch, caplog):
    monkeypatch.setattr(
        runtime_app,
        "_run_curation_pipeline",
        _raising_pipeline_stub(RuntimeError("dynamodb table missing")),
    )

    with caplog.at_level(logging.INFO, logger=CURATION_LOGGER_NAME):
        result = _call_handler(loop, {})
        _drain(loop)

    payload, record = _find_json_log_record(caplog, "curation_run_failed")
    assert payload is not None, "expected a curation_run_failed log record"
    assert payload["run_id"] == result["run_id"]
    assert isinstance(payload["duration_s"], (int, float))
    # logger.exception() attaches the traceback via exc_info, not the message
    # body - that's what makes it "logged with a stack trace".
    assert record.exc_info is not None
    assert record.exc_info[1] is not None
    assert "dynamodb table missing" in str(record.exc_info[1])

    # No curation_run_complete record for a run that failed.
    complete_payload, _ = _find_json_log_record(caplog, "curation_run_complete")
    assert complete_payload is None


# =============================================================================
# T22 (was T8) - curation_run_complete is a STRICT SUPERSET of the eight
# async-invocation-ack fields: same names, same values, plus the new Spec 06
# fields (Behavior Guarantee 2 / Success Criteria).
# =============================================================================


def test_curation_run_complete_log_record_is_a_superset_of_the_eight_original_fields_plus_new_fields(
    loop, monkeypatch, caplog
):
    final_state = {
        "discovered": 50,
        "discovered_by_source": {"arXiv cs.AI": 30, "Tavily: general": 20},
        "deduped": 42,
        "summarized": 8,
        "failed": 0,
        "cards": [object()] * 8,
        "persisted": 8,
        "input_tokens": 24135,
        "output_tokens": 3120,
    }
    invoke_calls: list = []
    curation_config.TAVILY_API_KEY = "tvly-key"
    _patch_pipeline_seams(monkeypatch, final_state, invoke_calls)
    monkeypatch.setattr(runtime_app, "_build_store", lambda: FakeCardStore(failure_count=0))
    monkeypatch.setattr(
        runtime_app,
        "_build_discoverer",
        lambda: FakeDiscoverer(failure_count=0, sources=[object()], searches=5, credits_used=5),
    )

    with caplog.at_level(logging.INFO, logger=CURATION_LOGGER_NAME):
        result = _call_handler(loop, {})
        _drain(loop)

    payload, _ = _find_json_log_record(caplog, "curation_run_complete")
    assert payload is not None, "expected a curation_run_complete log record"

    # The eight async-invocation-ack fields, unchanged names and values.
    assert payload["run_id"] == result["run_id"]
    assert isinstance(payload["duration_s"], (int, float))
    assert payload["discovered"] == 50
    assert payload["deduped"] == 42
    assert payload["summarized"] == 8
    assert payload["failed"] == 0
    assert payload["persisted"] == 8
    assert payload["discoverer_failures"] == 0
    assert payload["store_failures"] == 0
    assert payload["tavily_enabled"] is True

    # New fields — ADDED, not substituted.
    assert payload["discovered_rss"] == 30
    assert payload["discovered_tavily"] == 20
    assert payload["discovered_by_source"] == {"arXiv cs.AI": 30, "Tavily: general": 20}
    assert payload["cards_written"] == 8
    assert payload["input_tokens"] == 24135
    assert payload["output_tokens"] == 3120
    assert payload["tavily_searches"] == 5
    assert payload["tavily_credits"] == 5
    assert payload["estimated_cost_usd"] == pytest.approx(
        payload["estimated_bedrock_cost_usd"] + payload["estimated_tavily_cost_usd"]
    )


# =============================================================================
# T10 - `_background_tasks` holds the task in flight, empties after completion
# =============================================================================


def test_background_tasks_set_holds_task_in_flight_and_empties_after_completion(loop, monkeypatch):
    release_event = threading.Event()
    monkeypatch.setattr(
        runtime_app, "_run_curation_pipeline", _blocking_pipeline_stub(release_event, calls=[])
    )

    _call_handler(loop, {})

    assert len(runtime_app._background_tasks) == 1

    release_event.set()
    _drain(loop)

    assert len(runtime_app._background_tasks) == 0


# =============================================================================
# T11 / I1 - payload remains ignored (Spec 04 Behavior Guarantee 2, preserved)
# =============================================================================


def test_handler_ignores_payload_argument_producing_identical_ack_shape_and_graph_input(loop, monkeypatch):
    final_state = {
        "discovered": 3,
        "deduped": 2,
        "summarized": 2,
        "failed": 0,
        "cards": [object()],
    }
    invoke_calls: list = []
    curation_config.TAVILY_API_KEY = ""
    _patch_pipeline_seams(monkeypatch, final_state, invoke_calls)

    result_empty_payload = _call_handler(loop, {})
    _drain(loop)
    result_arbitrary_payload = _call_handler(loop, {"unexpected": "value", "nested": {"a": 1}})
    _drain(loop)

    assert result_empty_payload.keys() == result_arbitrary_payload.keys()
    assert result_empty_payload["status"] == result_arbitrary_payload["status"] == "accepted"
    # build_graph().invoke() was called identically both times MODULO run_id -
    # payload never reached max_items, and each call's run_id matches its own
    # ack (run_id necessarily differs per call - it's a fresh uuid per run).
    assert invoke_calls[0]["max_items"] == invoke_calls[1]["max_items"] == 7
    assert invoke_calls[0]["run_id"] == result_empty_payload["run_id"]
    assert invoke_calls[1]["run_id"] == result_arbitrary_payload["run_id"]


# =============================================================================
# T23 (was T12) - `_run_curation_pipeline(run_id)` returns a REAL `RunSummary`
# derived from the graph's final state, the discoverer's searches()/
# credits_used()/failures(), and the store's failures().
# =============================================================================


def test_run_curation_pipeline_returns_run_summary_with_run_id_and_correct_derived_fields(monkeypatch):
    from curation.summary import RunSummary

    final_state = {
        "discovered": 12,
        "discovered_by_source": {"arXiv cs.AI": 9, "Tavily: general": 3},
        "deduped": 9,
        "summarized": 8,
        "failed": 1,
        "cards": [object(), object(), object()],
        "persisted": 3,
        "input_tokens": 1000,
        "output_tokens": 200,
    }
    invoke_calls: list = []
    curation_config.TAVILY_API_KEY = ""
    monkeypatch.setattr(runtime_app, "_build_store", lambda: FakeCardStore(failure_count=2))
    monkeypatch.setattr(
        runtime_app,
        "_build_discoverer",
        lambda: FakeDiscoverer(failure_count=1, sources=[object()], searches=4, credits_used=4),
    )
    monkeypatch.setattr(runtime_app, "build_graph", _fake_build_graph(final_state, invoke_calls))
    monkeypatch.setattr(runtime_app.config, "MAX_ITEMS", 42)

    result = runtime_app._run_curation_pipeline("test-run-id")

    assert isinstance(result, RunSummary)
    assert result.run_id == "test-run-id"
    assert result.discovered == 12
    assert result.discovered_rss == 9
    assert result.discovered_tavily == 3
    assert result.deduped == 9
    assert result.summarized == 8
    assert result.failed == 1
    assert result.persisted == 3
    assert result.cards_written == 1  # max(persisted - store_failures, 0) == max(3-2, 0)
    assert result.input_tokens == 1000
    assert result.output_tokens == 200
    assert result.tavily_searches == 4
    assert result.tavily_credits == 4
    assert result.discoverer_failures == 1
    assert result.store_failures == 2
    assert result.tavily_enabled is False
    assert invoke_calls == [{"max_items": 42, "run_id": "test-run-id"}]


# =============================================================================
# T24 - EMF emission: exactly one line on a successful run; suppressed
# entirely by the kill switch, without affecting curation_run_complete.
# =============================================================================


def test_successful_run_emits_exactly_one_emf_line_to_stderr(loop, monkeypatch, capsys):
    final_state = {
        "discovered": 5,
        "discovered_by_source": {"Test Feed": 5},
        "deduped": 4,
        "summarized": 3,
        "failed": 0,
        "cards": [object()] * 3,
        "persisted": 3,
        "input_tokens": 10,
        "output_tokens": 2,
    }
    invoke_calls: list = []
    curation_config.TAVILY_API_KEY = ""
    _patch_pipeline_seams(monkeypatch, final_state, invoke_calls)

    _call_handler(loop, {})
    _drain(loop)

    stderr_lines = _parse_json_lines(capsys.readouterr().err)
    emf_lines = [line for line in stderr_lines if line.get("event") == "curation_run_metrics"]
    assert len(emf_lines) == 1
    assert emf_lines[0]["RunsCompleted"] == 1
    assert emf_lines[0]["CardsWritten"] == 3


def test_metrics_kill_switch_suppresses_the_emf_line_without_affecting_curation_run_complete(
    loop, monkeypatch, capsys, caplog
):
    import curation.metrics as metrics_module

    final_state = {
        "discovered": 5,
        "discovered_by_source": {"Test Feed": 5},
        "deduped": 4,
        "summarized": 3,
        "failed": 0,
        "cards": [object()] * 3,
        "persisted": 3,
        "input_tokens": 10,
        "output_tokens": 2,
    }
    invoke_calls: list = []
    curation_config.TAVILY_API_KEY = ""
    _patch_pipeline_seams(monkeypatch, final_state, invoke_calls)
    monkeypatch.setattr(metrics_module.config, "EMIT_RUN_METRICS", False)

    with caplog.at_level(logging.INFO, logger=CURATION_LOGGER_NAME):
        _call_handler(loop, {})
        _drain(loop)

    stderr_lines = _parse_json_lines(capsys.readouterr().err)
    assert not any(line.get("event") == "curation_run_metrics" for line in stderr_lines)

    payload, _ = _find_json_log_record(caplog, "curation_run_complete")
    assert payload is not None, "the kill switch must not affect curation_run_complete"


# =============================================================================
# T25 - a raising emit_run_metrics logs curation_metrics_failed (WARNING) and
# NEVER turns a successful run into curation_run_failed (Behavior Guarantee 6
# / Error Handling Contract row "emit_run_metrics raises").
# =============================================================================


def test_raising_emit_run_metrics_logs_curation_metrics_failed_and_keeps_curation_run_complete(
    loop, monkeypatch, caplog
):
    final_state = {
        "discovered": 5,
        "discovered_by_source": {"Test Feed": 5},
        "deduped": 4,
        "summarized": 3,
        "failed": 0,
        "cards": [object()] * 3,
        "persisted": 3,
        "input_tokens": 10,
        "output_tokens": 2,
    }
    invoke_calls: list = []
    curation_config.TAVILY_API_KEY = ""
    _patch_pipeline_seams(monkeypatch, final_state, invoke_calls)

    def _raise(summary):
        raise RuntimeError("stderr closed")

    monkeypatch.setattr(runtime_app, "emit_run_metrics", _raise)

    with caplog.at_level(logging.INFO, logger=CURATION_LOGGER_NAME):
        result = _call_handler(loop, {})
        _drain(loop)

    complete_payload, _ = _find_json_log_record(caplog, "curation_run_complete")
    assert complete_payload is not None
    assert complete_payload["run_id"] == result["run_id"]

    failed_payload, _ = _find_json_log_record(caplog, "curation_run_failed")
    assert failed_payload is None, "a metrics failure must never produce curation_run_failed"

    metrics_failed_payload, metrics_failed_record = _find_json_log_record(caplog, "curation_metrics_failed")
    assert metrics_failed_payload is not None
    assert metrics_failed_payload["run_id"] == result["run_id"]
    assert metrics_failed_record.levelno == logging.WARNING


# =============================================================================
# T26 - a failing pipeline (curation_run_failed path) never calls
# emit_run_metrics at all (Behavior Guarantee 1: "A failed run produces
# neither" a summary nor metrics).
# =============================================================================


def test_failing_pipeline_never_calls_emit_run_metrics(loop, monkeypatch):
    calls: list = []
    monkeypatch.setattr(runtime_app, "emit_run_metrics", lambda summary: calls.append(summary))
    monkeypatch.setattr(
        runtime_app, "_run_curation_pipeline", _raising_pipeline_stub(RuntimeError("boom"))
    )

    _call_handler(loop, {})
    _drain(loop)

    assert calls == []


# =============================================================================
# T27 - `_configure_curation_logging()` attaches a handler + INFO level to the
# `curation` logger tree so node-level records reach CloudWatch.
# =============================================================================


def test_configure_curation_logging_attaches_a_handler_and_info_level_to_the_curation_logger():
    curation_logger = logging.getLogger("curation")
    original_handlers = list(curation_logger.handlers)
    original_level = curation_logger.level
    try:
        runtime_app._configure_curation_logging()

        assert curation_logger.level == logging.INFO
        assert curation_logger.handlers, (
            "expected _configure_curation_logging() to attach at least one "
            "handler to the 'curation' logger tree"
        )
    finally:
        curation_logger.handlers = original_handlers
        curation_logger.setLevel(original_level)


# =============================================================================
# I2 - Tavily key resolves -> Tavily wired, key injected before from_config()
# (unchanged from Spec 04: `_build_discoverer` is not touched by this spec)
# =============================================================================


def test_build_discoverer_wires_tavily_and_injects_key_before_from_config_when_secret_resolves(
    monkeypatch,
):
    monkeypatch.setattr(runtime_app, "_resolve_tavily_key", lambda secret_name: "tvly-resolved-key")
    monkeypatch.setattr(runtime_app, "RssDiscoverer", FakeRssDiscoverer)
    fake_tavily_cls = _make_recording_tavily_discoverer_class()
    monkeypatch.setattr(runtime_app, "TavilyDiscoverer", fake_tavily_cls)

    discoverer = runtime_app._build_discoverer()

    assert curation_config.TAVILY_API_KEY == "tvly-resolved-key"
    # from_config() saw the key ALREADY injected - i.e. it ran after injection.
    assert fake_tavily_cls.from_config_calls == ["tvly-resolved-key"]
    assert len(discoverer.sources) == 2
    assert any(isinstance(s, fake_tavily_cls) for s in discoverer.sources)
    assert any(isinstance(s, FakeRssDiscoverer) for s in discoverer.sources)


# =============================================================================
# I3 - key resolves empty -> RSS-only, no crash (unchanged from Spec 04)
# =============================================================================


def test_build_discoverer_falls_back_to_rss_only_when_tavily_key_unresolved(monkeypatch):
    monkeypatch.setattr(runtime_app, "_resolve_tavily_key", lambda secret_name: "")
    monkeypatch.setattr(runtime_app, "RssDiscoverer", FakeRssDiscoverer)
    forbidden_tavily_cls = _make_forbidden_tavily_discoverer_class()
    monkeypatch.setattr(runtime_app, "TavilyDiscoverer", forbidden_tavily_cls)

    discoverer = runtime_app._build_discoverer()  # must not raise

    assert len(discoverer.sources) == 1
    assert isinstance(discoverer.sources[0], FakeRssDiscoverer)
    assert curation_config.TAVILY_API_KEY == ""


# =============================================================================
# I2/I3 (via the log record) - tavily_enabled in curation_run_complete matches
# secret resolution outcome. Spec 04 asserted this off the response; the
# response no longer carries counts (BG8 superseded), so it now reads the
# `curation_run_complete` log record joined by run_id.
# =============================================================================


@pytest.mark.parametrize(
    "resolved_key, expected_tavily_enabled",
    [("tvly-resolved-key", True), ("", False)],
)
def test_curation_run_complete_tavily_enabled_field_matches_secret_resolution_outcome(
    loop, monkeypatch, caplog, resolved_key, expected_tavily_enabled
):
    final_state = {"discovered": 0, "deduped": 0, "summarized": 0, "failed": 0, "cards": []}
    invoke_calls: list = []

    monkeypatch.setattr(runtime_app, "_resolve_tavily_key", lambda secret_name: resolved_key)
    monkeypatch.setattr(runtime_app, "DynamoCardStore", lambda: FakeCardStore())
    monkeypatch.setattr(runtime_app, "RssDiscoverer", FakeRssDiscoverer)
    monkeypatch.setattr(runtime_app, "TavilyDiscoverer", _make_recording_tavily_discoverer_class())
    monkeypatch.setattr(runtime_app, "build_graph", _fake_build_graph(final_state, invoke_calls))

    with caplog.at_level(logging.INFO, logger=CURATION_LOGGER_NAME):
        result = _call_handler(loop, {})
        _drain(loop)

    payload, _ = _find_json_log_record(caplog, "curation_run_complete")
    assert payload is not None
    assert payload["run_id"] == result["run_id"]
    assert payload["tavily_enabled"] is expected_tavily_enabled


# =============================================================================
# I4 - `_resolve_tavily_key` real implementation (unchanged from Spec 04)
# =============================================================================


def test_resolve_tavily_key_returns_secret_string_on_success_and_never_logs_it(monkeypatch, capsys):
    secret_value = "tvly-never-logged-abc123xyz"
    monkeypatch.setattr(boto3, "client", lambda *a, **k: _StaticSecretsClient(secret_value))

    result = runtime_app._resolve_tavily_key("ai-radar/tavily-api-key")

    assert result == secret_value
    captured = capsys.readouterr()
    assert secret_value not in captured.out
    assert secret_value not in captured.err


def test_resolve_tavily_key_returns_empty_string_when_secret_value_is_blank(monkeypatch):
    monkeypatch.setattr(boto3, "client", lambda *a, **k: _StaticSecretsClient(""))

    assert runtime_app._resolve_tavily_key("ai-radar/tavily-api-key") == ""


def test_resolve_tavily_key_returns_empty_string_on_boto3_error(monkeypatch):
    monkeypatch.setattr(
        boto3, "client", lambda *a, **k: _RaisingSecretsClient("AccessDeniedException")
    )

    assert runtime_app._resolve_tavily_key("ai-radar/tavily-api-key") == ""


# =============================================================================
# F2 regression (unchanged from Spec 04): a freshly-`cdk deploy`'d, not-yet-
# populated secret (holding curation.config.TAVILY_SECRET_UNSET_SENTINEL, per
# infra/lib/agent_runtime.py) must resolve as "not a real key" - NOT get
# treated as a truthy, usable Tavily key.
# =============================================================================


def test_resolve_tavily_key_returns_empty_string_when_secret_holds_the_unset_sentinel(monkeypatch):
    monkeypatch.setattr(
        boto3,
        "client",
        lambda *a, **k: _StaticSecretsClient(curation_config.TAVILY_SECRET_UNSET_SENTINEL),
    )

    assert runtime_app._resolve_tavily_key("ai-radar/tavily-api-key") == ""


def test_build_discoverer_treats_unset_sentinel_secret_as_unresolved_rss_only(monkeypatch):
    """End-to-end through the real (unmocked) `_resolve_tavily_key`: a secret
    that resolves successfully but holds the CDK placeholder sentinel must
    degrade to RSS-only exactly like an empty/failed resolution - proving the
    sentinel check lives in `_resolve_tavily_key` itself, not just relied on
    by a mocked seam."""
    monkeypatch.setattr(
        boto3,
        "client",
        lambda *a, **k: _StaticSecretsClient(curation_config.TAVILY_SECRET_UNSET_SENTINEL),
    )
    monkeypatch.setattr(runtime_app, "RssDiscoverer", FakeRssDiscoverer)
    forbidden_tavily_cls = _make_forbidden_tavily_discoverer_class()
    monkeypatch.setattr(runtime_app, "TavilyDiscoverer", forbidden_tavily_cls)

    discoverer = runtime_app._build_discoverer()  # must not raise, must not wire Tavily

    assert len(discoverer.sources) == 1
    assert isinstance(discoverer.sources[0], FakeRssDiscoverer)
    assert curation_config.TAVILY_API_KEY == ""


def test_curation_run_complete_tavily_enabled_is_false_when_secret_holds_the_unset_sentinel(
    loop, monkeypatch, caplog
):
    """Full real chain (only boto3 is faked): a freshly-deployed secret still
    holding the CDK placeholder sentinel must never surface as
    `tavily_enabled=True` in the run-completion log record."""
    final_state = {"discovered": 0, "deduped": 0, "summarized": 0, "failed": 0, "cards": []}
    invoke_calls: list = []

    monkeypatch.setattr(
        boto3,
        "client",
        lambda *a, **k: _StaticSecretsClient(curation_config.TAVILY_SECRET_UNSET_SENTINEL),
    )
    monkeypatch.setattr(runtime_app, "DynamoCardStore", lambda: FakeCardStore())
    monkeypatch.setattr(runtime_app, "RssDiscoverer", FakeRssDiscoverer)
    monkeypatch.setattr(runtime_app, "TavilyDiscoverer", _make_forbidden_tavily_discoverer_class())
    monkeypatch.setattr(runtime_app, "build_graph", _fake_build_graph(final_state, invoke_calls))

    with caplog.at_level(logging.INFO, logger=CURATION_LOGGER_NAME):
        result = _call_handler(loop, {})
        _drain(loop)

    payload, _ = _find_json_log_record(caplog, "curation_run_complete")
    assert payload is not None
    assert payload["tavily_enabled"] is False


# =============================================================================
# I5 - importing the module must not start the HTTP server (unchanged)
# =============================================================================


def test_import_runtime_app_does_not_start_the_http_server(monkeypatch):
    from bedrock_agentcore import BedrockAgentCoreApp

    run_calls: list = []
    monkeypatch.setattr(BedrockAgentCoreApp, "run", lambda self: run_calls.append(True))
    monkeypatch.delitem(sys.modules, "runtime_app", raising=False)

    importlib.import_module("runtime_app")

    assert run_calls == []

"""Offline unit tests for the AgentCore Runtime entrypoint (Spec 04:
runtime-packaging).

Spec: specs/runtime-packaging/contract.md "Public API - runtime_app.py"
(handler / `_resolve_tavily_key` / `_build_store` / `_build_discoverer`),
Behavior Guarantees 2, 3, 8, 9; Error Handling Contract row 1;
specs/runtime-packaging/tasks.md Task 4.1 (T1-T6).

100% offline: `DynamoCardStore`, `RssDiscoverer`, `TavilyDiscoverer`, and
`build_graph(...).invoke` are monkeypatched at the `runtime_app` module's own
seam (the composition root) - no real boto3/DynamoDB/Secrets Manager/Bedrock
call is ever made. `_resolve_tavily_key`'s own real implementation is
exercised directly against a fake `boto3.client(...)` (no real AWS network
call either).

RED phase: `runtime_app.py` does not exist yet. Every test in this file is
expected to fail at collection with `ModuleNotFoundError: No module named
'runtime_app'` until Phase 1 (tasks.md Tasks 1.1-1.9) lands.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

# runtime_app.py lives at the REPO ROOT (sibling to run_curation.py), not under
# src/ - tests/conftest.py only puts src/ on sys.path, so add the repo root too
# (mirrors tests/test_infra.py's sys.path.insert pattern for infra/).
sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
import pytest

import curation.config as curation_config

import runtime_app


# --- Fakes (in-memory doubles for the injected seams) -----------------------


class FakeCardStore:
    """In-memory CardStore double: implements the Spec 01 CardStore Protocol
    (dedup_filter/upsert) plus DynamoCardStore's `.failures()` (Spec 03) that
    the handler's summary dict reads."""

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
    (discover/failures/sources) that the handler's summary dict reads."""

    def __init__(self, failure_count: int = 0, sources=None):
        self._failure_count = failure_count
        self.sources = sources if sources is not None else []

    def discover(self):
        return []

    def failures(self):
        return self._failure_count


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


@pytest.fixture(autouse=True)
def _reset_tavily_api_key():
    """`_build_discoverer` mutates the shared `curation.config.TAVILY_API_KEY`
    module global as a side effect - restore it so tests never leak state."""
    original = curation_config.TAVILY_API_KEY
    yield
    curation_config.TAVILY_API_KEY = original


# --- T1: handler returns the run-summary dict from the mocked graph ---------


def test_handler_returns_run_summary_dict_from_mocked_graph_final_state(monkeypatch):
    final_state = {
        "discovered": 12,
        "deduped": 9,
        "summarized": 8,
        "failed": 1,
        "cards": [object(), object(), object()],
    }
    invoke_calls: list = []
    curation_config.TAVILY_API_KEY = ""  # deterministic: RSS-only this run

    monkeypatch.setattr(runtime_app, "_build_store", lambda: FakeCardStore(failure_count=2))
    monkeypatch.setattr(
        runtime_app, "_build_discoverer", lambda: FakeDiscoverer(failure_count=1, sources=[object()])
    )
    monkeypatch.setattr(runtime_app, "build_graph", _fake_build_graph(final_state, invoke_calls))
    monkeypatch.setattr(runtime_app.config, "MAX_ITEMS", 42)

    result = runtime_app.handler({})

    assert result == {
        "discovered": 12,
        "deduped": 9,
        "summarized": 8,
        "failed": 1,
        "persisted": 3,
        "discoverer_failures": 1,
        "store_failures": 2,
        "tavily_enabled": False,
    }
    # env-only config (Behavior Guarantee 2): max_items comes from spike.config,
    # never from the payload.
    assert invoke_calls == [{"max_items": 42}]


# --- T2: handler ignores `payload` -------------------------------------------


def test_handler_ignores_payload_argument(monkeypatch):
    final_state = {
        "discovered": 3,
        "deduped": 2,
        "summarized": 2,
        "failed": 0,
        "cards": [object()],
    }
    invoke_calls: list = []
    curation_config.TAVILY_API_KEY = ""

    monkeypatch.setattr(runtime_app, "_build_store", lambda: FakeCardStore())
    monkeypatch.setattr(runtime_app, "_build_discoverer", lambda: FakeDiscoverer())
    monkeypatch.setattr(runtime_app, "build_graph", _fake_build_graph(final_state, invoke_calls))

    result_empty_payload = runtime_app.handler({})
    result_arbitrary_payload = runtime_app.handler({"unexpected": "value", "nested": {"a": 1}})

    assert result_empty_payload == result_arbitrary_payload
    # build_graph().invoke() was called identically both times - payload never
    # reached the graph input.
    assert invoke_calls[0] == invoke_calls[1]


# --- T3: key resolves -> Tavily wired, key injected before from_config() ----


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


# --- T4: key resolves empty -> RSS-only, no crash ---------------------------


def test_build_discoverer_falls_back_to_rss_only_when_tavily_key_unresolved(monkeypatch):
    monkeypatch.setattr(runtime_app, "_resolve_tavily_key", lambda secret_name: "")
    monkeypatch.setattr(runtime_app, "RssDiscoverer", FakeRssDiscoverer)
    forbidden_tavily_cls = _make_forbidden_tavily_discoverer_class()
    monkeypatch.setattr(runtime_app, "TavilyDiscoverer", forbidden_tavily_cls)

    discoverer = runtime_app._build_discoverer()  # must not raise

    assert len(discoverer.sources) == 1
    assert isinstance(discoverer.sources[0], FakeRssDiscoverer)
    assert curation_config.TAVILY_API_KEY == ""


# --- T3/T4: the handler's `tavily_enabled` field reflects secret resolution --


@pytest.mark.parametrize(
    "resolved_key, expected_tavily_enabled",
    [("tvly-resolved-key", True), ("", False)],
)
def test_handler_tavily_enabled_field_matches_secret_resolution_outcome(
    monkeypatch, resolved_key, expected_tavily_enabled
):
    final_state = {"discovered": 0, "deduped": 0, "summarized": 0, "failed": 0, "cards": []}
    invoke_calls: list = []

    monkeypatch.setattr(runtime_app, "_resolve_tavily_key", lambda secret_name: resolved_key)
    monkeypatch.setattr(runtime_app, "DynamoCardStore", lambda: FakeCardStore())
    monkeypatch.setattr(runtime_app, "RssDiscoverer", FakeRssDiscoverer)
    monkeypatch.setattr(runtime_app, "TavilyDiscoverer", _make_recording_tavily_discoverer_class())
    monkeypatch.setattr(runtime_app, "build_graph", _fake_build_graph(final_state, invoke_calls))

    result = runtime_app.handler({})

    assert result["tavily_enabled"] is expected_tavily_enabled


# --- T5: `_resolve_tavily_key` real implementation -------------------------


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


# --- F2 regression: a freshly-`cdk deploy`'d, not-yet-populated secret ------
# (holding the CDK construct's TAVILY_SECRET_UNSET_SENTINEL placeholder, per
# infra/lib/agent_runtime.py) must resolve as "not a real key" - NOT get
# treated as a truthy, usable Tavily key. Covers both the `_resolve_tavily_key`
# seam directly and the observable `_build_discoverer`/handler behavior.


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


def test_handler_tavily_enabled_is_false_when_secret_holds_the_unset_sentinel(monkeypatch):
    """Full real chain (only boto3 is faked): a freshly-deployed secret still
    holding the CDK placeholder sentinel must never surface as
    `tavily_enabled=True` in the handler's returned run summary."""
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

    result = runtime_app.handler({})

    assert result["tavily_enabled"] is False


# --- T6: importing the module must not start the HTTP server ---------------


def test_import_runtime_app_does_not_start_the_http_server(monkeypatch):
    from bedrock_agentcore import BedrockAgentCoreApp

    run_calls: list = []
    monkeypatch.setattr(BedrockAgentCoreApp, "run", lambda self: run_calls.append(True))
    monkeypatch.delitem(sys.modules, "runtime_app", raising=False)

    importlib.import_module("runtime_app")

    assert run_calls == []

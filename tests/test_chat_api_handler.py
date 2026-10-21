"""Unit tests for `src/chat_api/handler.py` (chat-api spec, AC1, AC2, AC3, AC7).

Spec: specs/chat-api/execution-plan.md § Validation rows AC1, AC2, AC3, AC7.

Events are hand-built API Gateway HTTP API payload-format-2.0 dicts. No AWS
call is made: the fixture patches `boto3.client` to return a fake
`bedrock-agentcore` client and imports `chat_api.handler` fresh while the
patch is active, so the test works whether the handler builds its client at
import time or lazily on first call. The fake also records the botocore
`Config` the handler asked for.

RED phase: `src/chat_api/` does not exist yet, so every test fails in the
fixture with `ModuleNotFoundError: No module named 'chat_api'`.
"""
from __future__ import annotations

import ast
import base64
import importlib
import io
import json
import logging
import sys
import uuid
from pathlib import Path

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError

RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-1:626259825216:runtime/ai_radar_chat-JFCO0R9lkT"
MAX_BODY_BYTES = 524_288
PLANTED_QUESTION = "PLANTED-QUESTION-zq81"
PLANTED_ANSWER = "PLANTED-ANSWER-kv42"
PLANTED_HISTORY = "PLANTED-HISTORY-tt07"
PLANTED_IP = "203.0.113.77"
GOOD_REPLY = {
    "answer": f"{PLANTED_ANSWER} [1]",
    "sources": [
        {"n": 1, "title": "t", "url": "https://x.example/a", "source": "s", "published": "2026-10-01", "score": 0.9}
    ],
}


class FakeAgentCore:
    """Stands in for the boto3 `bedrock-agentcore` client."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.outcomes: list = []  # consumed in order; bytes -> reply body, Exception -> raised

    def queue(self, *outcomes) -> None:
        self.outcomes.extend(outcomes)

    def invoke_agent_runtime(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if self.outcomes else json.dumps(GOOD_REPLY).encode()
        if isinstance(outcome, Exception):
            raise outcome
        return {"response": io.BytesIO(outcome), "statusCode": 200}


class Env:
    def __init__(self, module, client: FakeAgentCore, client_kwargs: list[dict]) -> None:
        self.module = module
        self.client = client
        self.client_kwargs = client_kwargs

    def call(self, body, *, base64_encode: bool = False) -> dict:
        return self.module.handler(_event(body, base64_encode=base64_encode), None)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("CHAT_RUNTIME_ARN", RUNTIME_ARN)
    fake = FakeAgentCore()
    client_kwargs: list[dict] = []

    def fake_boto3_client(service_name, *args, **kwargs):
        assert service_name == "bedrock-agentcore"
        client_kwargs.append(kwargs)
        return fake

    monkeypatch.setattr("boto3.client", fake_boto3_client)
    for name in ("chat_api.handler", "chat_api.config", "chat_api"):
        sys.modules.pop(name, None)
    module = importlib.import_module("chat_api.handler")
    yield Env(module, fake, client_kwargs)
    for name in ("chat_api.handler", "chat_api.config", "chat_api"):
        sys.modules.pop(name, None)


def _event(body, *, base64_encode: bool = False) -> dict:
    event: dict = {
        "version": "2.0",
        "rawPath": "/v1/chat",
        "requestContext": {"http": {"method": "POST", "sourceIp": PLANTED_IP}},
        "isBase64Encoded": False,
    }
    if body is not None:
        raw = body.encode("utf-8")
        if base64_encode:
            event["body"] = base64.b64encode(raw).decode()
            event["isBase64Encoded"] = True
        else:
            event["body"] = body
    return event


def _json(response: dict) -> dict:
    return json.loads(response["body"])


def _chat_api_records(caplog) -> list[dict]:
    records = []
    for record in caplog.records:
        try:
            parsed = json.loads(record.getMessage())
        except ValueError:
            continue
        if isinstance(parsed, dict) and parsed.get("event") == "chat_api_request":
            records.append(parsed)
    return records


def _valid_body(question: str = "What shipped?", **extra) -> str:
    return json.dumps({"question": question, **extra})


def _padded_body(total_bytes: int) -> str:
    prefix, suffix = '{"question":"', '"}'
    return prefix + "a" * (total_bytes - len(prefix) - len(suffix)) + suffix


# --- AC1 ---------------------------------------------------------------

def test_valid_turn_returns_200_with_answer_and_sources(env):
    response = env.call(_valid_body())

    assert response["statusCode"] == 200
    assert _json(response) == GOOD_REPLY


def test_extra_agent_keys_are_dropped(env):
    env.client.queue(json.dumps({**GOOD_REPLY, "request_id": "r-1", "debug": {"x": 1}}).encode())

    response = env.call(_valid_body())

    assert response["statusCode"] == 200
    assert set(_json(response)) == {"answer", "sources"}


def test_invoke_uses_runtime_arn_default_qualifier_fresh_uuid4_and_unchanged_payload(env):
    body = _valid_body("Whats new?", history=[{"role": "user", "content": "hi"}])

    env.call(body)

    (call,) = env.client.calls
    assert call["agentRuntimeArn"] == RUNTIME_ARN
    assert call["qualifier"] == "DEFAULT"
    assert call["contentType"] == "application/json"
    assert call["accept"] == "application/json"
    assert call["payload"] == body.encode("utf-8")
    session_id = call["runtimeSessionId"]
    assert len(session_id) == 36
    assert str(uuid.UUID(session_id, version=4)) == session_id


def test_body_without_history_is_forwarded_as_sent(env):
    body = _valid_body()

    response = env.call(body)

    assert response["statusCode"] == 200
    assert env.client.calls[0]["payload"] == body.encode("utf-8")


def test_base64_encoded_body_is_decoded_before_forwarding(env):
    body = _valid_body("café?")

    response = env.call(body, base64_encode=True)

    assert response["statusCode"] == 200
    assert env.client.calls[0]["payload"] == body.encode("utf-8")


def test_client_is_built_with_short_timeouts_and_no_retries(env):
    env.call(_valid_body())

    (kwargs,) = env.client_kwargs
    config = kwargs["config"]
    assert config.connect_timeout == 3
    assert config.read_timeout == 22
    # botocore: total_max_attempts counts the first call, so 1 means no retry.
    # `max_attempts` counts retries beyond the first call (1 would allow two calls).
    assert config.retries == {"total_max_attempts": 1}
    assert "max_attempts" not in config.retries


LAMBDA_TIMEOUT_SECONDS = 28  # execution-plan.md: Lambda timeout 28 s
HEADROOM_SECONDS = 3


def test_timeouts_leave_headroom_under_the_lambda_timeout(env):
    env.call(_valid_body())

    (kwargs,) = env.client_kwargs
    config = kwargs["config"]
    assert config.connect_timeout + config.read_timeout <= LAMBDA_TIMEOUT_SECONDS - HEADROOM_SECONDS


# --- AC2 ---------------------------------------------------------------

def test_agent_invalid_request_is_returned_as_400_with_the_agents_body(env):
    agent_body = {"error": "invalid_request", "detail": "question_empty"}
    env.client.queue(json.dumps(agent_body).encode())

    response = env.call(json.dumps({"question": ""}))

    assert response["statusCode"] == 400
    assert _json(response) == agent_body


@pytest.mark.parametrize(
    ("body", "rule"),
    [
        (None, "body_missing"),
        ("", "body_missing"),
        (f"not json {PLANTED_QUESTION}", "body_not_json"),
        (json.dumps([PLANTED_QUESTION]), "body_not_object"),
        (json.dumps(PLANTED_QUESTION), "body_not_object"),
    ],
)
def test_bad_body_is_rejected_with_a_fixed_rule_and_no_invoke(env, body, rule):
    response = env.call(body)

    assert response["statusCode"] == 400
    assert _json(response) == {"error": "invalid_request", "detail": rule}
    assert PLANTED_QUESTION not in response["body"]
    assert env.client.calls == []


def test_body_of_exactly_512_kib_is_accepted(env):
    body = _padded_body(MAX_BODY_BYTES)
    assert len(body.encode("utf-8")) == MAX_BODY_BYTES

    response = env.call(body)

    assert response["statusCode"] == 200
    assert len(env.client.calls) == 1


def test_body_one_byte_over_512_kib_is_rejected_without_invoke(env):
    body = _padded_body(MAX_BODY_BYTES + 1)

    response = env.call(body)

    assert response["statusCode"] == 400
    assert _json(response) == {"error": "invalid_request", "detail": "body_too_large"}
    assert env.client.calls == []


def test_size_cap_counts_utf8_bytes_not_characters(env):
    body = json.dumps({"question": "é" * 262_145}, ensure_ascii=False)
    assert len(body) < MAX_BODY_BYTES < len(body.encode("utf-8"))

    response = env.call(body)

    assert response["statusCode"] == 400
    assert _json(response)["detail"] == "body_too_large"
    assert env.client.calls == []


# --- AC3 ---------------------------------------------------------------

def test_agent_upstream_failure_becomes_502(env):
    env.client.queue(json.dumps({"error": "upstream_failure"}).encode())

    response = env.call(_valid_body())

    assert response["statusCode"] == 502
    assert _json(response) == {"error": "upstream_failure"}


def test_client_error_becomes_502_and_next_request_succeeds(env):
    env.client.queue(
        ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "secret-internal-detail-7731"}},
            "InvokeAgentRuntime",
        )
    )

    failed = env.call(_valid_body())
    recovered = env.call(_valid_body())

    assert failed["statusCode"] == 502
    assert _json(failed) == {"error": "upstream_failure"}
    assert "secret-internal-detail-7731" not in failed["body"]
    assert "ThrottlingException" not in failed["body"]
    assert recovered["statusCode"] == 200
    assert _json(recovered) == GOOD_REPLY


@pytest.mark.parametrize(
    "reply",
    [
        b"<html>gateway error</html>",
        b"",
        json.dumps(["answer", "sources"]).encode(),
        json.dumps({"answer": "a"}).encode(),
        json.dumps({"sources": []}).encode(),
        json.dumps({"answer": 5, "sources": []}).encode(),
        json.dumps({"answer": "a", "sources": "nope"}).encode(),
        json.dumps({"error": "something_new"}).encode(),
    ],
)
def test_unreadable_or_unknown_reply_becomes_502(env, reply):
    env.client.queue(reply)

    response = env.call(_valid_body())

    assert response["statusCode"] == 502
    assert _json(response) == {"error": "upstream_failure"}


def test_read_timeout_becomes_504_upstream_timeout_without_internals(env):
    env.client.queue(ReadTimeoutError(endpoint_url="https://internal-endpoint.example/secret-path"))

    response = env.call(_valid_body())

    assert response["statusCode"] == 504
    assert _json(response) == {"error": "upstream_timeout"}
    assert "internal-endpoint" not in response["body"]


def test_unexpected_exception_text_never_reaches_the_caller(env):
    env.client.queue(RuntimeError("boom-secret-9912"))

    response = env.call(_valid_body())

    assert response["statusCode"] == 502
    assert "boom-secret-9912" not in response["body"]


# --- AC7 ---------------------------------------------------------------

def test_two_requests_use_two_distinct_session_ids(env):
    env.call(_valid_body())
    env.call(_valid_body())

    first, second = (c["runtimeSessionId"] for c in env.client.calls)
    assert first != second
    assert len(first) == len(second) == 36


def test_one_log_record_per_request_with_required_keys(env, caplog):
    caplog.set_level(logging.INFO)
    history = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]

    env.call(_valid_body("hello", history=history))
    env.call(_valid_body("hello"))

    first, second = _chat_api_records(caplog)
    assert {"status", "outcome", "question_chars", "history_items", "duration_ms", "session_id"} <= set(first)
    assert first["status"] == 200
    assert first["outcome"] == "ok"
    assert first["question_chars"] == len("hello")
    assert first["history_items"] == 2
    assert second["history_items"] == 0
    assert [first["session_id"], second["session_id"]] == [c["runtimeSessionId"] for c in env.client.calls]


@pytest.mark.parametrize(
    ("queued", "body", "status", "outcome"),
    [
        (ClientError({"Error": {"Code": "X", "Message": "m"}}, "InvokeAgentRuntime"), _valid_body(), 502, "upstream_failure"),
        (ReadTimeoutError(endpoint_url="https://e.example"), _valid_body(), 504, "upstream_timeout"),
        (json.dumps({"error": "invalid_request", "detail": "question_empty"}).encode(), _valid_body(), 400, "invalid_request"),
        (None, "not json", 400, "invalid_request"),
    ],
)
def test_failure_paths_also_log_exactly_one_record(env, caplog, queued, body, status, outcome):
    caplog.set_level(logging.INFO)
    if queued is not None:
        env.client.queue(queued)

    env.call(body)

    (record,) = _chat_api_records(caplog)
    assert record["status"] == status
    assert record["outcome"] == outcome


def test_no_log_record_contains_the_question_answer_history_or_caller_ip(env, caplog):
    caplog.set_level(logging.DEBUG)
    env.client.queue(json.dumps({"answer": PLANTED_ANSWER, "sources": []}).encode(), RuntimeError("boom"))
    body = _valid_body(PLANTED_QUESTION, history=[{"role": "user", "content": PLANTED_HISTORY}])

    env.call(body)  # success path
    env.call(body)  # failure path, with a logged stack trace

    assert caplog.records
    for record in caplog.records:
        text = " ".join([record.getMessage(), record.exc_text or "", str(record.args)])
        for secret in (PLANTED_QUESTION, PLANTED_ANSWER, PLANTED_HISTORY, PLANTED_IP):
            assert secret not in text


# --- Revision 2 (audit round 1: F2, F3, F7) ------------------------------

class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _request_records(records) -> list[dict]:
    found = []
    for record in records:
        try:
            parsed = json.loads(record.getMessage())
        except ValueError:
            continue
        if isinstance(parsed, dict) and parsed.get("event") == "chat_api_request":
            found.append(parsed)
    return found


def test_request_record_survives_root_logger_at_warning_log_level(env):
    # The Lambda runtime leaves the root logger at WARNING; the record must still
    # reach a handler because the handler module sets its own logger to INFO.
    root = logging.getLogger()
    capture = _Capture()
    previous = root.level
    root.setLevel(logging.WARNING)
    root.addHandler(capture)
    try:
        env.call(_valid_body())
    finally:
        root.removeHandler(capture)
        root.setLevel(previous)

    assert len(_request_records(capture.records)) == 1


def test_bug_before_the_invoke_is_a_typed_500_logged_once_internal(env, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    secret = f"pre-invoke-secret-5520 {PLANTED_QUESTION}"

    def boom(_event):
        raise RuntimeError(secret)

    monkeypatch.setattr(env.module, "_raw_body", boom)

    response = env.call(_valid_body(PLANTED_QUESTION))

    assert response["statusCode"] == 500
    assert _json(response) == {"error": "internal_error"}
    assert "pre-invoke-secret-5520" not in response["body"]
    assert PLANTED_QUESTION not in response["body"]
    assert env.client.calls == []
    (record,) = _chat_api_records(caplog)
    assert record["status"] == 500
    assert record["outcome"] == "internal_error"
    # Fully rendered records (message + traceback if exc_info/exc_text is set): no exception text.
    formatter = logging.Formatter()
    rendered = [formatter.format(rec) for rec in caplog.records]
    for text in rendered:
        assert "pre-invoke-secret-5520" not in text
        assert PLANTED_QUESTION not in text
    # The exception class name is still logged, so the failure stays diagnosable.
    assert any("RuntimeError" in text for text in rendered)


def _cors_cases():
    rate = ClientError({"Error": {"Code": "X", "Message": "m"}}, "InvokeAgentRuntime")
    return [
        ("ok", None, _valid_body()),
        ("bad_request", None, "not json"),
        ("502", rate, _valid_body()),
        ("504", ReadTimeoutError(endpoint_url="https://e.example"), _valid_body()),
    ]


@pytest.mark.parametrize(("name", "queued", "body"), _cors_cases(), ids=lambda v: v if isinstance(v, str) and len(v) < 12 else "")
def test_no_response_carries_a_cors_header_cors(env, name, queued, body):
    if queued is not None:
        env.client.queue(queued)

    response = env.call(body)

    assert not [h for h in response.get("headers", {}) if h.lower().startswith("access-control-")]


def test_internal_error_response_carries_no_cors_header_cors(env, monkeypatch):
    def boom(_event):
        raise RuntimeError("x")

    monkeypatch.setattr(env.module, "_raw_body", boom)

    response = env.call(_valid_body())

    assert response["statusCode"] == 500
    assert not [h for h in response.get("headers", {}) if h.lower().startswith("access-control-")]


FIRST_PARTY = {"curation", "api", "chat", "shared", "contracts"}


def test_chat_api_package_imports_no_first_party_package_first_party():
    package = Path(__file__).resolve().parents[1] / "src" / "chat_api"
    files = sorted(package.rglob("*.py"))
    assert files, "no .py files found under src/chat_api/"

    offenders = []
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            offenders += [f"{path.name}: {n}" for n in names if n.split(".")[0] in FIRST_PARTY]
    assert offenders == []


# --- chat-api-auth (AC5) -------------------------------------------------

def test_iam_authorizer_context_is_not_logged(env, caplog):
    """A request that API Gateway authorized with IAM carries the caller's identity in
    `requestContext`; the record keeps exactly its seven keys and none of that text."""
    caplog.set_level(logging.DEBUG)
    planted = ("AKIAPLANTEDKEY7Q2", "arn:aws:iam::626259825216:user/planted-caller-user", "PLANTEDUSERID9Z")
    event = _event(_valid_body("hello"))
    event["requestContext"]["authorizer"] = {
        "iam": {
            "accessKey": planted[0],
            "accountId": "626259825216",
            "callerId": planted[2],
            "userArn": planted[1],
            "userId": planted[2],
        }
    }

    response = env.module.handler(event, None)

    assert response["statusCode"] == 200
    (record,) = _chat_api_records(caplog)
    assert set(record) == {
        "event", "status", "outcome", "question_chars", "history_items", "duration_ms", "session_id",
    }
    for rec in caplog.records:
        text = " ".join([rec.getMessage(), rec.exc_text or "", str(rec.args)])
        for secret in planted:
            assert secret not in text

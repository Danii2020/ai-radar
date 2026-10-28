"""Offline unit tests for the pure signing helper in `run_chat_api_smoke.py`
(chat-api-auth spec, AC1).

Spec: specs/chat-api-auth/execution-plan.md § Validation row AC1.

The helper is `build_signed_headers(url, body, credentials) -> dict[str, str]`: it
SigV4-signs a `POST` for service `execute-api`, region `us-east-1`, with a
`botocore.credentials.Credentials`. Fixed fake credentials and a patched
`botocore.auth.get_current_datetime` make it deterministic; no network, no STS and
no real credentials are involved.

RED phase: `run_chat_api_smoke.py` does not exist, so import fails.
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pytest
from botocore.credentials import Credentials

sys.path.insert(0, str(Path(__file__).parent.parent))

URL = "https://abc123.execute-api.us-east-1.amazonaws.com/v1/chat"
BODY = b'{"question": "What is new?"}'
FIXED_NOW = datetime.datetime(2026, 10, 21, 12, 30, 45, tzinfo=datetime.UTC)
FAKE_SECRET = "dummy-secret-key-for-tests-only"


@pytest.fixture
def smoke(monkeypatch):
    import botocore.auth

    monkeypatch.setattr(botocore.auth, "get_current_datetime", lambda: FIXED_NOW)
    import run_chat_api_smoke

    return run_chat_api_smoke


def _headers(smoke, body: bytes = BODY, token: str | None = None) -> dict[str, str]:
    creds = Credentials("AKIDEXAMPLE", FAKE_SECRET, token)
    return {k.lower(): v for k, v in smoke.build_signed_headers(URL, body, creds).items()}


def test_authorization_header_names_the_execute_api_us_east_1_scope(smoke):
    auth = _headers(smoke)["authorization"]
    assert auth.startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20261021/us-east-1/execute-api/aws4_request")


def test_signed_headers_include_host_and_x_amz_date(smoke):
    auth = _headers(smoke)["authorization"]
    signed = auth.split("SignedHeaders=")[1].split(",")[0].split(";")
    assert "host" in signed
    assert "x-amz-date" in signed


def test_date_header_follows_the_patched_clock_and_content_type_is_json(smoke):
    headers = _headers(smoke)
    assert headers["x-amz-date"] == "20261021T123045Z"
    assert headers["content-type"].startswith("application/json")


def test_security_token_header_is_present_only_when_a_token_is_given(smoke):
    assert "x-amz-security-token" not in _headers(smoke)
    assert _headers(smoke, token="DUMMYTOKEN")["x-amz-security-token"] == "DUMMYTOKEN"


def test_signature_is_deterministic_for_a_fixed_clock_and_changes_with_the_body(smoke):
    first = _headers(smoke)["authorization"]
    assert _headers(smoke)["authorization"] == first
    assert _headers(smoke, body=b'{"question": "Something else?"}')["authorization"] != first


def test_the_secret_key_never_appears_in_the_returned_headers(smoke):
    assert all(FAKE_SECRET not in v for v in _headers(smoke).values())


# --- opt-in exit-code mode (backend-cicd-pipeline, outcome O4, AC7) -----------------------------
#
# Spec: specs/backend-cicd-pipeline/execution-plan.md § Validation row AC7 (opt-in option).
# New options on `main()`: `--expect-status N` makes a different HTTP status exit 1, and
# `--expect-keys a,b` makes a 2xx JSON body without every listed top-level key exit 1. Without
# either option `main()` keeps returning 0 after printing (the chat-api-auth runbook relies on it).
# RED phase: argparse rejects both options today.

import io
import json
import urllib.error


class _FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body


class _FakeCreds:
    def get_frozen_credentials(self):
        class _Frozen:
            access_key = "AKIDEXAMPLE"
            secret_key = FAKE_SECRET
            token = None

        return _Frozen()


class _FakeSession:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def client(self, *args, **kwargs):
        raise RuntimeError("no network in tests")  # `_identity` falls back to identity=unknown

    def get_credentials(self):
        return _FakeCreds()


@pytest.fixture
def run_main(smoke, monkeypatch, capsys):
    """Call `main(argv)` against a stubbed `urlopen` answering (status, body)."""

    def _run(argv: list[str], status: int, body: dict | str):
        text = body if isinstance(body, str) else json.dumps(body)
        monkeypatch.setenv("CHAT_API_URL", "https://abc123.execute-api.us-east-1.amazonaws.com")
        monkeypatch.setattr(smoke.boto3, "Session", _FakeSession)

        def fake_urlopen(request, timeout=None):
            if status >= 400:
                raise urllib.error.HTTPError(
                    request.full_url, status, "err", {}, io.BytesIO(text.encode())  # type: ignore[arg-type]
                )
            return _FakeResponse(status, text.encode())

        monkeypatch.setattr(smoke.urllib.request, "urlopen", fake_urlopen)
        rc = smoke.main(argv)
        return rc, capsys.readouterr().out

    return _run


def test_default_mode_exits_zero_even_when_the_api_answers_403(run_main):
    rc, out = run_main(["--unsigned"], 403, {"message": "Forbidden"})
    assert rc == 0
    assert "status=403" in out


def test_expect_status_matching_exits_zero(run_main):
    rc, _ = run_main(["--expect-status", "403", "--unsigned"], 403, {"message": "Forbidden"})
    assert rc == 0


def test_expect_status_mismatch_exits_nonzero_and_still_prints_the_status(run_main):
    rc, out = run_main(["--expect-status", "200"], 403, {"message": "Forbidden"})
    assert rc == 1
    assert "status=403" in out


def test_expect_keys_present_exits_zero(run_main):
    rc, _ = run_main(["--expect-status", "200", "--expect-keys", "answer,sources"], 200,
                     {"answer": "hi", "sources": []})
    assert rc == 0


def test_expect_keys_missing_exits_nonzero_for_the_curation_ack_shape(run_main):
    rc, _ = run_main(["--expect-status", "200", "--expect-keys", "answer,sources"], 200,
                     {"status": "accepted", "run_id": "r-1"})
    assert rc == 1


def test_expect_keys_with_a_non_json_body_exits_nonzero(run_main):
    rc, _ = run_main(["--expect-keys", "answer"], 200, "<html>nope</html>")
    assert rc == 1


def test_expect_mode_never_prints_the_secret_key(run_main):
    _, out = run_main(["--expect-status", "200"], 200, {"answer": "hi", "sources": []})
    assert FAKE_SECRET not in out

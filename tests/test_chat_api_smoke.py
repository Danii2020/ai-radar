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

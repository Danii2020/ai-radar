"""Tests for the Bedrock usage seam — `src/spike/bedrock.py`'s new
`TokenUsage` + `summarize_with_usage`, and `summarize()`'s back-compat wrapper.

Spec: specs/run-observability/contract.md §1 ("Bedrock seam —
src/spike/bedrock.py"); Behavior Guarantee 6 (missing/malformed `usage`
degrades to `TokenUsage(0, 0)`, never raises); Error Handling Contract row 1;
specs/run-observability/audit.md Test Coverage T1-T3.

`bedrock_client()` is monkeypatched at the module seam
(`spike.bedrock.bedrock_client`) with an in-memory fake `.converse(...)` — no
real boto3/Bedrock call is ever made.

RED phase: `TokenUsage` and `summarize_with_usage` do not exist yet in
`src/spike/bedrock.py`. Every test in this file is expected to fail with
`ImportError: cannot import name 'TokenUsage' from 'spike.bedrock'` (or an
`AttributeError` once that import is fixed but the function is still
missing), until specs/run-observability Phase 2 lands.
"""
from __future__ import annotations

import pytest

import spike.bedrock as bedrock_module
from spike.bedrock import TokenUsage


class _FakeBedrockClient:
    """Stub for the `bedrock-runtime` client's `.converse(...)` — installed
    via monkeypatching `spike.bedrock.bedrock_client`, never hits the network.
    """

    def __init__(self, response: dict) -> None:
        self._response = response
        self.calls: list[dict] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def _converse_response(card: dict, usage: dict | None) -> dict:
    """Build a Converse-shaped response: a forced `toolUse` block carrying
    `card`, plus an optional `usage` block (omitted entirely when `usage` is
    `None`, simulating a response that never carried one)."""
    response: dict = {"output": {"message": {"content": [{"toolUse": {"input": card}}]}}}
    if usage is not None:
        response["usage"] = usage
    return response


def _install(monkeypatch, response: dict) -> _FakeBedrockClient:
    fake_client = _FakeBedrockClient(response)
    monkeypatch.setattr(bedrock_module, "bedrock_client", lambda: fake_client)
    return fake_client


# T1: `summarize_with_usage` returns the tool-call dict AND a `TokenUsage`
# built from the Converse response's `usage` block.
def test_summarize_with_usage_returns_card_dict_and_token_usage_from_converse_response(
    monkeypatch, make_raw_item, make_model_out
):
    item = make_raw_item()
    card = make_model_out()
    _install(monkeypatch, _converse_response(card, {"inputTokens": 123, "outputTokens": 45, "totalTokens": 168}))

    result_card, usage = bedrock_module.summarize_with_usage(item)

    assert result_card == card
    assert usage == TokenUsage(input_tokens=123, output_tokens=45)


# T2 (Behavior Guarantee 6 / Error Handling row 1): a response with no `usage`
# block at all, an empty `usage` block, non-int values, or a non-mapping
# `usage` value (audit finding O1) all degrade to `TokenUsage(0, 0)` — never
# raise, and the card is still returned normally.
@pytest.mark.parametrize(
    "usage",
    [
        None,  # no "usage" key on the response at all
        {},  # present but empty
        {"inputTokens": "not-an-int", "outputTokens": "also-not-an-int"},
        ["not", "a", "mapping"],  # truthy but not a mapping at all (no .get)
    ],
    ids=["missing", "empty", "non-int-values", "non-mapping-truthy"],
)
def test_summarize_with_usage_degrades_to_zero_usage_on_missing_or_malformed_usage_block(
    monkeypatch, make_raw_item, make_model_out, usage
):
    item = make_raw_item()
    card = make_model_out()
    _install(monkeypatch, _converse_response(card, usage))

    result_card, token_usage = bedrock_module.summarize_with_usage(item)

    assert result_card == card
    assert token_usage == TokenUsage(0, 0)


# T3 (contract.md §1 "UNCHANGED public signature and return value"):
# `summarize()` returns exactly the same dict `summarize_with_usage()[0]`
# would, and its return type is still a plain dict (not a tuple).
def test_summarize_returns_same_dict_as_summarize_with_usage_first_element(
    monkeypatch, make_raw_item, make_model_out
):
    item = make_raw_item()
    card = make_model_out()
    _install(monkeypatch, _converse_response(card, {"inputTokens": 10, "outputTokens": 2}))

    result = bedrock_module.summarize(item)

    assert result == card
    assert isinstance(result, dict)


# Unchanged behavior (contract.md §1 docstring): no `toolUse` block in the
# response still raises `RuntimeError`, exactly like the pre-Spec-06
# `summarize()`.
def test_summarize_with_usage_raises_runtime_error_when_no_tool_use_block(monkeypatch, make_raw_item):
    item = make_raw_item()
    _install(monkeypatch, {"output": {"message": {"content": [{"text": "no tool call"}]}}})

    with pytest.raises(RuntimeError):
        bedrock_module.summarize_with_usage(item)

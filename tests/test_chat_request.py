"""Tests for chat request validation and caps (AC3).

Spec: specs/chat-agent-runtime/intent.md AC3; execution-plan.md § Validation
row AC3 and the pinned validation rules; tasks.md Task 0.1.

`chat.request.parse_request(payload)` is pure. The plan pins its name and the
rules, not its return type, so these tests treat a rejection as either a raised
exception (with an optional `.detail`) or a returned `{"error": "invalid_request",
"detail": ...}` dict, and a success as anything else. Only the rule name's
shape is asserted here (short, never an echo of the input); the entrypoint
tests pin the wire shape.

RED phase: `src/chat/request.py` and the cap settings do not exist yet.
"""
from __future__ import annotations

import pytest

from chat import config as chat_config
from chat.request import parse_request

MAX_Q = 1000
MAX_ITEM = 4000
MAX_ITEMS = 20  # 10 turns, a turn being a user item plus its assistant reply


def _history(items: int) -> list[dict]:
    roles = ["user", "assistant"]
    return [{"role": roles[i % 2], "text": f"t{i}"} for i in range(items)]


def _outcome(payload):
    """('ok', result) or ('invalid', detail)."""
    try:
        result = parse_request(payload)
    except Exception as exc:  # noqa: BLE001 - any rejection type is acceptable
        return "invalid", str(getattr(exc, "detail", exc))
    if isinstance(result, dict) and result.get("error") == "invalid_request":
        return "invalid", str(result.get("detail"))
    return "ok", result


def _is_valid(payload) -> bool:
    return _outcome(payload)[0] == "ok"


def test_cap_settings_default_to_the_pinned_values():
    assert chat_config.CHAT_MAX_QUESTION_CHARS == MAX_Q
    assert chat_config.CHAT_MAX_HISTORY_TURNS == 10
    assert chat_config.CHAT_MAX_HISTORY_ITEM_CHARS == MAX_ITEM


def test_a_question_alone_is_valid_and_history_defaults_to_empty():
    assert _is_valid({"question": "What shipped this week?"})
    assert _is_valid({"question": "What shipped this week?", "history": []})


def test_a_well_formed_history_is_valid():
    history = [
        {"role": "user", "text": "first?"},
        {"role": "assistant", "text": "answer [1]"},
    ]
    assert _is_valid({"question": "and the second?", "history": history})


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(None, id="payload-none"),
        pytest.param([], id="payload-list"),
        pytest.param({}, id="question-missing"),
        pytest.param({"question": ""}, id="question-empty"),
        pytest.param({"question": "   \n\t "}, id="question-blank"),
        pytest.param({"question": None}, id="question-none"),
        pytest.param({"question": 42}, id="question-not-a-string"),
        pytest.param({"question": ["q"]}, id="question-a-list"),
    ],
)
def test_missing_or_blank_questions_are_rejected(payload):
    assert _outcome(payload)[0] == "invalid"


def test_question_length_boundary_is_1000_ok_and_1001_rejected():
    assert _is_valid({"question": "q" * MAX_Q})
    assert _outcome({"question": "q" * (MAX_Q + 1)})[0] == "invalid"


def test_question_length_is_measured_after_stripping():
    assert _is_valid({"question": "  " + "q" * MAX_Q + "  \n"})


@pytest.mark.parametrize(
    "history",
    [
        pytest.param("user: hi", id="not-a-list"),
        pytest.param({"role": "user", "text": "hi"}, id="a-dict"),
        pytest.param(None, id="none"),
        pytest.param(["hi"], id="item-not-a-dict"),
        pytest.param([{"role": "system", "text": "x"}], id="bad-role"),
        pytest.param([{"text": "x"}], id="role-missing"),
        pytest.param([{"role": "user"}], id="text-missing"),
        pytest.param(
            [{"role": "user", "text": ""}, {"role": "assistant", "text": "a"}],
            id="text-empty",
        ),
        pytest.param(
            [{"role": "user", "text": 5}, {"role": "assistant", "text": "a"}],
            id="text-not-a-string",
        ),
        pytest.param(
            [{"role": "user", "text": "u"}, {"role": "user", "text": "u2"}],
            id="roles-do-not-alternate",
        ),
        pytest.param(
            [{"role": "assistant", "text": "a"}, {"role": "user", "text": "u"}],
            id="starts-with-assistant",
        ),
        pytest.param([{"role": "user", "text": "u"}], id="does-not-end-with-assistant"),
    ],
)
def test_malformed_history_is_rejected(history):
    assert _outcome({"question": "q", "history": history})[0] == "invalid"


def test_history_item_count_boundary_is_20_ok_and_22_rejected():
    assert _is_valid({"question": "q", "history": _history(MAX_ITEMS)})
    assert _outcome({"question": "q", "history": _history(MAX_ITEMS + 2)})[0] == "invalid"


def test_history_item_text_boundary_is_4000_ok_and_4001_rejected():
    def pair(n: int) -> list[dict]:
        return [
            {"role": "user", "text": "x" * n},
            {"role": "assistant", "text": "a"},
        ]

    assert _is_valid({"question": "q", "history": pair(MAX_ITEM)})
    assert _outcome({"question": "q", "history": pair(MAX_ITEM + 1)})[0] == "invalid"


def test_the_detail_is_a_short_rule_name_never_an_echo_of_the_input():
    secret = "s3cr3t-payload-text"
    bad_question = _outcome({"question": secret * 100})
    bad_role = _outcome(
        {"question": secret, "history": [{"role": secret, "text": secret}]}
    )

    for kind, detail in (bad_question, bad_role):
        assert kind == "invalid"
        assert detail and len(detail) <= 64
        assert secret not in detail


def test_different_rules_report_different_details():
    missing = _outcome({})[1]
    too_many = _outcome({"question": "q", "history": _history(MAX_ITEMS + 2)})[1]

    assert missing != too_many


@pytest.mark.parametrize(
    "history",
    [
        pytest.param([{"role": "assistant", "text": "a"}], id="lone-assistant"),
        pytest.param(
            [
                {"role": "user", "text": "u"},
                {"role": "assistant", "text": "a"},
                {"role": "assistant", "text": "a2"},
            ],
            id="assistant-twice-in-a-row",
        ),
    ],
)
def test_role_alternation_is_enforced_even_when_the_history_ends_with_assistant(history):
    """Isolates the alternation rule: these end with an assistant item, so the
    'must end with assistant' rule cannot be what rejects them."""
    assert history[-1]["role"] == "assistant"
    assert _outcome({"question": "q", "history": history}) == (
        "invalid",
        "history_roles_not_alternating",
    )

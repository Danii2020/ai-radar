"""Offline tests for the chat AgentCore entrypoint `chat_app.py`.

Spec: specs/chat-agent-runtime/intent.md AC1, AC2, AC3, AC5, AC6;
execution-plan.md § Validation rows AC1-AC3, AC5, AC6; tasks.md Task 0.3.

The entrypoint builds its graph and `DynamoCardRetriever` once at import, so the
fixture patches `chat.retriever.DynamoCardRetriever` with a fake BEFORE a fresh
import. The Bedrock `converse` call is patched at `shared.chat.bedrock_client`.
Zero real AWS. `handler` is a plain sync function; it is called directly.

RED phase: `chat_app.py` does not exist yet.
"""
from __future__ import annotations

import importlib
import json
import logging
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import shared.chat as shared_chat

CHAT_LOGGER_NAME = "bedrock_agentcore.app.chat"
TURN_KEYS = {
    "event",
    "question_chars",
    "history_items",
    "hits",
    "retrieval_ms",
    "model_ms",
    "outcome",
}


def _card(n: int, **extra) -> dict:
    card = {
        "title": f"Title {n}",
        "source": "Src",
        "published": "2026-08-01",
        "summary": f"Summary {n}",
        "url": f"https://example.com/{n}",
        "tags": ["llm"],
        "takeaways": ["t"],
    }
    card.update(extra)
    return card


class FakeRetriever:
    def __init__(self):
        self.hits: list = []
        self.error: Exception | None = None
        self.calls: list[tuple[str, int]] = []

    def search(self, query, k):
        self.calls.append((query, k))
        if self.error is not None:
            raise self.error
        return self.hits


class FakeBedrock:
    def __init__(self):
        self.answer = "Answer [1]"
        self.error: Exception | None = None
        self.requests: list[dict] = []

    def converse(self, **kwargs):
        self.requests.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"output": {"message": {"content": [{"text": self.answer}]}}}


@pytest.fixture
def retriever():
    return FakeRetriever()


@pytest.fixture
def bedrock(monkeypatch):
    fake = FakeBedrock()
    monkeypatch.setattr(shared_chat, "bedrock_client", lambda: fake)
    return fake


@pytest.fixture
def chat_app(monkeypatch, retriever, bedrock):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setattr(
        "chat.retriever.DynamoCardRetriever", lambda *a, **k: retriever
    )
    sys.modules.pop("chat_app", None)
    module = importlib.import_module("chat_app")
    yield module
    sys.modules.pop("chat_app", None)


def _turn_records(caplog) -> list[dict]:
    out = []
    for record in caplog.records:
        try:
            payload = json.loads(record.getMessage())
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict) and payload.get("event") == "chat_turn":
            out.append(payload)
    return out


def _invoke(chat_app, caplog, payload):
    with caplog.at_level(logging.INFO, logger=CHAT_LOGGER_NAME):
        return chat_app.handler(payload)


# --- AC1 ---------------------------------------------------------------------


def test_a_turn_returns_only_answer_and_ranked_sources_with_the_exact_fields(
    chat_app, retriever, bedrock
):
    retriever.hits = [
        (_card(1, embedding=[0.1, 0.2], relevance=9), 0.123456789),
        (_card(2) | {"published": None}, 0.5),
    ]
    bedrock.answer = "Open weights shipped [1] and a coder [2]."

    result = chat_app.handler({"question": "What shipped?", "history": []})

    assert set(result) == {"answer", "sources"}
    assert result["answer"] == "Open weights shipped [1] and a coder [2]."
    assert result["sources"] == [
        {
            "n": 1,
            "title": "Title 1",
            "url": "https://example.com/1",
            "source": "Src",
            "published": "2026-08-01",
            "score": 0.1235,
        },
        {
            "n": 2,
            "title": "Title 2",
            "url": "https://example.com/2",
            "source": "Src",
            "published": None,
            "score": 0.5,
        },
    ]


def test_every_citation_in_the_answer_points_at_a_returned_source(
    chat_app, retriever, bedrock
):
    retriever.hits = [(_card(i), 1.0 - i / 10) for i in range(1, 5)]
    bedrock.answer = "See [1], [2] and [4]."

    result = chat_app.handler({"question": "q"})

    cited = {int(n) for n in re.findall(r"\[(\d+)\]", result["answer"])}
    assert cited <= {s["n"] for s in result["sources"]}
    assert [s["n"] for s in result["sources"]] == [1, 2, 3, 4]


def test_the_default_retrieval_depth_is_top_k(chat_app, retriever):
    from shared.config import TOP_K

    retriever.hits = [(_card(1), 0.9)]

    chat_app.handler({"question": "q"})

    assert retriever.calls == [("q", TOP_K)]


# --- AC2 ---------------------------------------------------------------------


def test_client_history_becomes_ordered_converse_messages(chat_app, retriever, bedrock):
    retriever.hits = [(_card(1), 0.9)]
    history = [
        {"role": "user", "text": "first?"},
        {"role": "assistant", "text": "one [1]"},
        {"role": "user", "text": "second?"},
        {"role": "assistant", "text": "two [1]"},
    ]

    chat_app.handler({"question": "third?", "history": history})

    messages = bedrock.requests[0]["messages"]
    assert messages[:4] == [
        {"role": "user", "content": [{"text": "first?"}]},
        {"role": "assistant", "content": [{"text": "one [1]"}]},
        {"role": "user", "content": [{"text": "second?"}]},
        {"role": "assistant", "content": [{"text": "two [1]"}]},
    ]
    assert len(messages) == 5
    assert "User question: third?" in messages[4]["content"][0]["text"]
    assert retriever.calls == [("third?", retriever.calls[0][1])]  # only the new question


def test_invocations_are_independent_of_what_the_process_served_before(
    chat_app, retriever, bedrock
):
    retriever.hits = [(_card(1), 0.9)]
    payload = {
        "question": "same?",
        "history": [
            {"role": "user", "text": "HIST-MARK"},
            {"role": "assistant", "text": "a"},
        ],
    }

    chat_app.handler(payload)
    chat_app.handler({"question": "other?", "history": []})
    chat_app.handler(payload)

    first, middle, third = bedrock.requests
    assert first == third
    assert len(middle["messages"]) == 1
    assert "HIST-MARK" not in str(middle) and "same?" not in str(middle)


# --- AC3 ---------------------------------------------------------------------

INVALID_PAYLOADS = [
    pytest.param({}, id="question-missing"),
    pytest.param({"question": ""}, id="question-empty"),
    pytest.param({"question": "   "}, id="question-blank"),
    pytest.param({"question": "q" * 1001}, id="question-too-long"),
    pytest.param({"question": "q", "history": "nope"}, id="history-not-a-list"),
    pytest.param({"question": "q", "history": ["x"]}, id="item-not-a-dict"),
    pytest.param(
        {"question": "q", "history": [{"role": "bot", "text": "x"}]}, id="bad-role"
    ),
    pytest.param(
        [{"role": "user", "text": ""}, {"role": "assistant", "text": "a"}], id="empty-text"
    ),
    pytest.param(
        {
            "question": "q",
            "history": [
                {"role": "user", "text": "x" * 4001},
                {"role": "assistant", "text": "a"},
            ],
        },
        id="item-too-long",
    ),
    pytest.param(
        {
            "question": "q",
            "history": [
                {"role": ("user", "assistant")[i % 2], "text": "t"} for i in range(22)
            ],
        },
        id="too-many-items",
    ),
    pytest.param(
        {"question": "q", "history": [{"role": "user", "text": "u"}]},
        id="not-ending-with-assistant",
    ),
]


@pytest.mark.parametrize("payload", INVALID_PAYLOADS)
def test_invalid_requests_return_invalid_request_and_touch_no_client(
    chat_app, retriever, bedrock, payload
):
    result = chat_app.handler(payload)

    assert set(result) == {"error", "detail"}
    assert result["error"] == "invalid_request"
    assert isinstance(result["detail"], str) and result["detail"]
    assert retriever.calls == []
    assert bedrock.requests == []


def test_an_over_long_question_is_reported_as_question_too_long(chat_app):
    result = chat_app.handler({"question": "q" * 1001})

    assert result == {"error": "invalid_request", "detail": "question_too_long"}


def test_a_question_of_exactly_1000_characters_is_answered(chat_app, retriever):
    retriever.hits = [(_card(1), 0.9)]

    result = chat_app.handler({"question": "q" * 1000})

    assert "answer" in result


# --- AC4 (entrypoint view) ---------------------------------------------------


def test_nothing_retrieved_returns_an_answer_with_empty_sources_and_no_model_call(
    chat_app, retriever, bedrock
):
    result = chat_app.handler({"question": "q"})

    assert set(result) == {"answer", "sources"}
    assert result["sources"] == []
    assert result["answer"].strip()
    assert not re.search(r"\[\d+\]", result["answer"])
    assert bedrock.requests == []


# --- AC5 ---------------------------------------------------------------------


def test_a_retrieval_failure_is_upstream_failure_logged_and_the_next_turn_succeeds(
    chat_app, retriever, caplog
):
    retriever.error = RuntimeError("dynamo boom")
    with caplog.at_level(logging.INFO):
        result = chat_app.handler({"question": "q"})

    assert result == {"error": "upstream_failure"}
    assert any(
        r.exc_info and r.exc_info[0] is RuntimeError for r in caplog.records
    ), "the exception must be logged with its stack trace"

    retriever.error = None
    retriever.hits = [(_card(1), 0.9)]
    assert "answer" in chat_app.handler({"question": "q"})


def test_a_model_failure_is_upstream_failure_logged_and_the_next_turn_succeeds(
    chat_app, retriever, bedrock, caplog
):
    retriever.hits = [(_card(1), 0.9)]
    bedrock.error = RuntimeError("bedrock boom")
    with caplog.at_level(logging.INFO):
        result = chat_app.handler({"question": "q"})

    assert result == {"error": "upstream_failure"}
    assert any(
        r.exc_info and r.exc_info[0] is RuntimeError for r in caplog.records
    )

    bedrock.error = None
    assert "answer" in chat_app.handler({"question": "q"})


# --- AC6 ---------------------------------------------------------------------


def test_a_normal_turn_logs_one_chat_turn_record_with_the_pinned_keys(
    chat_app, retriever, caplog
):
    retriever.hits = [(_card(1), 0.9), (_card(2), 0.5)]
    history = [{"role": "user", "text": "u"}, {"role": "assistant", "text": "a"}]

    _invoke(chat_app, caplog, {"question": "hello", "history": history})

    [record] = _turn_records(caplog)
    assert set(record) == TURN_KEYS
    assert record["outcome"] == "ok"
    assert record["question_chars"] == len("hello")
    assert record["history_items"] == 2
    assert record["hits"] == 2
    assert record["retrieval_ms"] >= 0 and record["model_ms"] >= 0


def test_each_outcome_is_recorded_exactly_once_per_invocation(
    chat_app, retriever, bedrock, caplog
):
    retriever.hits = [(_card(1), 0.9)]
    _invoke(chat_app, caplog, {"question": "q"})
    retriever.hits = []
    _invoke(chat_app, caplog, {"question": "q"})
    _invoke(chat_app, caplog, {"question": ""})
    retriever.hits = [(_card(1), 0.9)]
    bedrock.error = RuntimeError("boom")
    _invoke(chat_app, caplog, {"question": "q"})

    records = _turn_records(caplog)
    assert [r["outcome"] for r in records] == [
        "ok",
        "no_context",
        "invalid_request",
        "upstream_failure",
    ]
    assert records[1]["hits"] == 0
    for record in records:
        assert TURN_KEYS <= set(record)


def test_chat_turn_records_never_carry_question_history_or_answer_text(
    chat_app, retriever, bedrock, caplog
):
    q, h_user, h_assistant, answer = "Q-MARK", "HU-MARK", "HA-MARK", "ANS-MARK"
    history = [{"role": "user", "text": h_user}, {"role": "assistant", "text": h_assistant}]
    bedrock.answer = answer
    markers = (q, h_user, h_assistant, answer)

    retriever.hits = [(_card(1), 0.9)]
    _invoke(chat_app, caplog, {"question": q, "history": history})  # ok
    retriever.hits = []
    _invoke(chat_app, caplog, {"question": q, "history": history})  # no_context
    _invoke(  # invalid_request
        chat_app, caplog, {"question": q, "history": [{"role": "bad", "text": h_user}]}
    )
    retriever.hits = [(_card(1), 0.9)]
    bedrock.error = RuntimeError("boom")
    _invoke(chat_app, caplog, {"question": q, "history": history})  # upstream_failure

    records = [
        r for r in caplog.records if '"chat_turn"' in r.getMessage()
    ]
    assert len(records) == 4
    for record in records:
        raw = record.getMessage()
        assert not any(m in raw for m in markers)
        payload = json.loads(raw)
        assert not {"question", "history", "answer", "text"} & set(payload)

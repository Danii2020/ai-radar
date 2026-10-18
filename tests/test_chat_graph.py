"""Tests for the Plane B retrieve-then-answer graph (AC1, AC2, AC4).

Spec: specs/chat-agent-runtime/intent.md AC1, AC2, AC4; execution-plan.md
§ Validation rows AC1/AC2/AC4; tasks.md Task 0.2.

`chat.graph.build_chat_graph(retriever, k)` returns a compiled LangGraph. Its
state (pinned in the plan) carries `question`, `history` (already in Converse
message form), `hits`, `answer`, `retrieval_ms` and `model_ms`. The Bedrock
`converse` call is patched at `shared.chat.bedrock_client`, the seam the shared
answer step uses; DynamoDB is `moto`. Zero real AWS.

RED phase: `src/chat/graph.py` does not exist yet.
"""
from __future__ import annotations

import re
from decimal import Decimal

import pytest
from chat.graph import build_chat_graph

import shared.chat as shared_chat
from chat.retriever import DynamoCardRetriever
from shared.config import EMBED_DIM, SONNET_MODEL_ID


def _card(n: int, published: str | None = "2026-08-01") -> dict:
    return {
        "title": f"Title {n}",
        "source": "Src",
        "published": published,
        "summary": f"Summary {n}",
        "url": f"https://example.com/{n}",
        "tags": [],
        "takeaways": [],
    }


class FakeRetriever:
    def __init__(self, hits):
        self.hits = hits
        self.calls: list[tuple[str, int]] = []

    def search(self, query, k):
        self.calls.append((query, k))
        return self.hits


class FakeBedrock:
    def __init__(self, answer="Answer [1]"):
        self.answer = answer
        self.requests: list[dict] = []

    def converse(self, **kwargs):
        self.requests.append(kwargs)
        return {"output": {"message": {"content": [{"text": self.answer}]}}}


@pytest.fixture
def fake_bedrock(monkeypatch):
    fake = FakeBedrock()
    monkeypatch.setattr(shared_chat, "bedrock_client", lambda: fake)
    return fake


def _msg(role: str, text: str) -> dict:
    return {"role": role, "content": [{"text": text}]}


# --- AC1 ---------------------------------------------------------------------


def test_graph_retrieves_k_hits_then_answers_from_them(fake_bedrock):
    hits = [(_card(1), 0.9), (_card(2), 0.5)]
    retriever = FakeRetriever(hits)

    final = build_chat_graph(retriever, 2).invoke({"question": "what is new?", "history": []})

    assert retriever.calls == [("what is new?", 2)]
    assert final["answer"] == "Answer [1]"
    assert final["hits"] == hits
    assert final["retrieval_ms"] >= 0
    assert final["model_ms"] >= 0
    assert len(fake_bedrock.requests) == 1


def test_context_cards_are_numbered_in_rank_order_in_the_model_request(fake_bedrock):
    hits = [(_card(7), 0.9), (_card(3), 0.5), (_card(9), 0.1)]

    build_chat_graph(FakeRetriever(hits), 3).invoke({"question": "q", "history": []})

    sent = fake_bedrock.requests[0]["messages"][-1]["content"][0]["text"]
    assert sent.index("[1] Title 7") < sent.index("[2] Title 3") < sent.index("[3] Title 9")
    assert sent.endswith("User question: q")


def test_the_model_request_keeps_the_phase0_shape_on_the_configured_model(fake_bedrock):
    build_chat_graph(FakeRetriever([(_card(1), 0.9)]), 1).invoke(
        {"question": "q", "history": []}
    )

    request = fake_bedrock.requests[0]
    assert request["modelId"] == SONNET_MODEL_ID
    assert request["system"][1] == {"cachePoint": {"type": "default"}}
    assert request["inferenceConfig"] == {"maxTokens": 800, "temperature": 0.3}


# --- AC2 ---------------------------------------------------------------------


def test_prior_messages_precede_the_new_turn_in_order(fake_bedrock):
    history = [
        _msg("user", "first?"),
        _msg("assistant", "one [1]"),
        _msg("user", "second?"),
        _msg("assistant", "two [1]"),
    ]

    build_chat_graph(FakeRetriever([(_card(1), 0.9)]), 1).invoke(
        {"question": "third?", "history": history}
    )

    messages = fake_bedrock.requests[0]["messages"]
    assert messages[:4] == history
    assert len(messages) == 5
    assert messages[4]["role"] == "user"
    assert "User question: third?" in messages[4]["content"][0]["text"]


def test_the_same_inputs_give_identical_model_requests_and_nothing_carries_over(
    fake_bedrock,
):
    graph = build_chat_graph(FakeRetriever([(_card(1), 0.9)]), 1)
    state = {
        "question": "same?",
        "history": [_msg("user", "HIST-MARK"), _msg("assistant", "a")],
    }

    graph.invoke(dict(state))
    graph.invoke({"question": "different?", "history": []})
    graph.invoke(dict(state))

    first, middle, third = fake_bedrock.requests
    assert first == third
    assert "same?" not in str(middle)
    assert "HIST-MARK" not in str(middle)
    assert len(middle["messages"]) == 1


# --- AC4 ---------------------------------------------------------------------


def test_no_hits_answers_without_a_model_call_and_without_a_citation(fake_bedrock):
    graph = build_chat_graph(FakeRetriever([]), 4)

    first = graph.invoke({"question": "anything?", "history": []})
    second = graph.invoke({"question": "something else?", "history": []})

    assert fake_bedrock.requests == []
    assert first["hits"] == []
    assert isinstance(first["answer"], str) and first["answer"].strip()
    assert not re.search(r"\[\d+\]", first["answer"])
    assert first["answer"] == second["answer"]  # fixed message, deterministic


def _real_retriever(resource, calls):
    def embed_fn(text: str) -> list[float]:
        calls.append(text)
        return [1.0] + [0.0] * (EMBED_DIM - 1)

    return DynamoCardRetriever(
        table_name="ai-radar-cards", resource=resource, embed_fn=embed_fn
    )


def test_an_empty_table_gives_the_no_context_answer(dynamo_resource, fake_bedrock):
    calls: list[str] = []

    final = build_chat_graph(_real_retriever(dynamo_resource, calls), 4).invoke(
        {"question": "q", "history": []}
    )

    assert final["hits"] == []
    assert fake_bedrock.requests == []
    assert not re.search(r"\[\d+\]", final["answer"])


def test_a_table_of_only_un_embedded_or_wrong_length_cards_gives_no_context(
    dynamo_resource, put_card_item, fake_bedrock
):
    put_card_item("plain")  # no embedding attribute
    put_card_item("short", embedding=[Decimal("1.0"), Decimal("0.0")])
    calls: list[str] = []

    final = build_chat_graph(_real_retriever(dynamo_resource, calls), 4).invoke(
        {"question": "q", "history": []}
    )

    assert calls == ["q"]
    assert final["hits"] == []
    assert fake_bedrock.requests == []
    assert not re.search(r"\[\d+\]", final["answer"])

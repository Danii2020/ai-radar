"""Tests for `RagChat` over a pluggable retriever, and the `run_chat.py`
backend switch (AC7).

Spec: specs/chat-retrieval/intent.md AC7; execution-plan.md § Validation row
AC7; tasks.md O4. Bedrock `converse` is patched at `shared.chat.bedrock_client`;
zero real AWS.

RED phase: `RagChat` still takes a list of cards; no `Retriever` Protocol yet.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import shared.chat as chat_module
import shared.retrieval as retrieval_module
from shared.chat import RagChat
from shared.config import EMBED_DIM, TOP_K
from shared.retrieval import CardIndex


def _card(n: int) -> dict:
    return {
        "title": f"Title {n}",
        "source": "Src",
        "published": "2026-08-01",
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
    monkeypatch.setattr(chat_module, "bedrock_client", lambda: fake)
    return fake


def test_ragchat_asks_any_retriever_for_k_hits_and_builds_the_cited_context(fake_bedrock):
    hits = [(_card(1), 0.9), (_card(2), 0.5)]
    retriever = FakeRetriever(hits)

    answer, returned = RagChat(retriever, k=2).ask("what is new?")

    assert retriever.calls == [("what is new?", 2)]
    assert answer == "Answer [1]"
    assert returned == hits
    sent = fake_bedrock.requests[0]["messages"][-1]["content"][0]["text"]
    assert "[1] Title 1 (Src, 2026-08-01)" in sent
    assert "[2] Title 2" in sent
    assert "url: https://example.com/2" in sent
    assert sent.endswith("User question: what is new?")


def test_ragchat_default_k_is_top_k(fake_bedrock):
    retriever = FakeRetriever([])

    RagChat(retriever).ask("q")

    assert retriever.calls == [("q", TOP_K)]


def test_ragchat_keeps_history_with_the_original_question_not_the_context(fake_bedrock):
    chat = RagChat(FakeRetriever([(_card(1), 0.9)]))

    chat.ask("first?")
    chat.ask("second?")

    second_messages = fake_bedrock.requests[1]["messages"]
    assert second_messages[0] == {"role": "user", "content": [{"text": "first?"}]}
    assert second_messages[1]["role"] == "assistant"
    assert "Context cards" in second_messages[2]["content"][0]["text"]


def test_default_local_path_still_answers_through_card_index(
    monkeypatch, tmp_path, fake_bedrock
):
    """Phase 0 behavior unchanged: a `CardIndex` over local cards plugs into
    `RagChat` as the retriever."""

    def fake_embed(text: str) -> list[float]:
        return [1.0] + [0.0] * (EMBED_DIM - 1)

    monkeypatch.setattr(retrieval_module, "embed", fake_embed)
    monkeypatch.setattr(retrieval_module, "EMBED_PATH", tmp_path / "embeddings.json")

    answer, hits = RagChat(CardIndex([_card(1), _card(2)]), k=1).ask("q")

    assert answer == "Answer [1]"
    assert len(hits) == 1
    assert "[1] Title" in fake_bedrock.requests[0]["messages"][-1]["content"][0]["text"]


# --- run_chat.py backend switch ----------------------------------------------


class _SentinelRetriever:
    def __init__(self, *args, **kwargs):
        pass


def _run_main_capturing_retriever(monkeypatch, tmp_path, backend: str | None):
    import run_chat

    captured: list = []

    class _RecordingChat:
        def __init__(self, retriever, *args, **kwargs):
            captured.append(retriever)

    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([]))
    monkeypatch.setattr(run_chat, "CARDS_PATH", cards_path)
    monkeypatch.setattr(run_chat, "RagChat", _RecordingChat)
    # Patch the dynamo retriever where it is defined (run_chat may import it lazily).
    import chat.retriever as retriever_module

    monkeypatch.setattr(retriever_module, "DynamoCardRetriever", _SentinelRetriever)
    import chat.config as chat_config

    # The switch is driven by chat.config (Plane B), not curation.config.
    value = "json" if backend is None else backend
    monkeypatch.setattr(chat_config, "CARD_STORE_BACKEND", value)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))  # EOF ends the REPL
    run_chat.main()
    assert len(captured) == 1
    return captured[0]


def test_run_chat_uses_dynamo_retriever_when_backend_is_dynamo(monkeypatch, tmp_path):
    retriever = _run_main_capturing_retriever(monkeypatch, tmp_path, "dynamo")

    assert isinstance(retriever, _SentinelRetriever)


def test_run_chat_default_backend_uses_local_card_index(monkeypatch, tmp_path):
    retriever = _run_main_capturing_retriever(monkeypatch, tmp_path, None)

    assert isinstance(retriever, CardIndex)

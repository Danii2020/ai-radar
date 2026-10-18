"""LangGraph retrieve-then-answer graph for the chat agent (Plane B).

Portable: the retriever is injected and the model call goes through the shared
`answer_question` seam, so no AWS client is built here.
"""
from __future__ import annotations

import time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from shared.chat import Retriever, answer_question

NO_CONTEXT_ANSWER = (
    "The collected news does not contain an answer to this. "
    "Try asking about a recent AI, GenAI, LLM or ML release or announcement."
)


class ChatState(TypedDict, total=False):
    question: str
    history: list[dict]  # prior turns, already in Converse message form
    hits: list[tuple[dict, float]]
    answer: str
    retrieval_ms: int
    model_ms: int


def build_sources(hits: list[tuple[dict, float]]) -> list[dict[str, Any]]:
    """Ranked source list; `n` matches the `[n]` numbering in the context block."""
    return [
        {
            "n": i,
            "title": card["title"],
            "url": card["url"],
            "source": card["source"],
            "published": card.get("published"),
            "score": round(float(score), 4),
        }
        for i, (card, score) in enumerate(hits, 1)
    ]


def build_chat_graph(retriever: Retriever, k: int):
    def retrieve(state: ChatState) -> ChatState:
        started = time.monotonic()
        hits = retriever.search(state["question"], k)
        return {
            "hits": hits,
            "retrieval_ms": int((time.monotonic() - started) * 1000),
        }

    def answer(state: ChatState) -> ChatState:
        hits = state.get("hits") or []
        if not hits:
            return {"answer": NO_CONTEXT_ANSWER, "model_ms": 0}
        started = time.monotonic()
        text = answer_question(state["question"], state.get("history") or [], hits)
        return {"answer": text, "model_ms": int((time.monotonic() - started) * 1000)}

    graph = StateGraph(ChatState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("answer", answer)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "answer")
    graph.add_edge("answer", END)
    return graph.compile()

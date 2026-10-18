#!/usr/bin/env python3
"""AgentCore Runtime entrypoint for the chat agent (spec `chat-agent-runtime`).

Stateless request/response: validate the payload, run the retrieve-then-answer
graph, return `{answer, sources}`. A sync handler, which the SDK runs in a
thread pool so blocking boto3 calls never stall `/ping`.

Composition root: `bedrock_agentcore` is imported only here. The graph and the
`DynamoCardRetriever` are built once per process at import. Stays in Plane B.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from bedrock_agentcore import BedrockAgentCoreApp

from chat import retriever as chat_retriever
from chat.graph import NO_CONTEXT_ANSWER, build_chat_graph, build_sources
from chat.request import InvalidRequest, parse_request
from shared import config

app = BedrockAgentCoreApp()

#: Child of the SDK's configured logger so records reach CloudWatch.
logger = logging.getLogger("bedrock_agentcore.app.chat")

_graph = build_chat_graph(chat_retriever.DynamoCardRetriever(), config.TOP_K)


def _log_turn(
    outcome: str,
    *,
    question_chars: int = 0,
    history_items: int = 0,
    hits: int = 0,
    retrieval_ms: int = 0,
    model_ms: int = 0,
) -> None:
    """One `chat_turn` record per invocation. Counts and timings only: never
    the question, history or answer text."""
    logger.info(
        json.dumps(
            {
                "event": "chat_turn",
                "question_chars": question_chars,
                "history_items": history_items,
                "hits": hits,
                "retrieval_ms": retrieval_ms,
                "model_ms": model_ms,
                "outcome": outcome,
            }
        )
    )


def _sizes(payload) -> tuple[int, int]:
    """Best-effort (question_chars, history_items) for rejected payloads."""
    if not isinstance(payload, dict):
        return 0, 0
    q = payload.get("question")
    h = payload.get("history")
    return (len(q) if isinstance(q, str) else 0, len(h) if isinstance(h, list) else 0)


@app.entrypoint
def handler(payload) -> dict:
    try:
        request = parse_request(payload)
    except InvalidRequest as exc:
        q_chars, h_items = _sizes(payload)
        _log_turn("invalid_request", question_chars=q_chars, history_items=h_items)
        return {"error": "invalid_request", "detail": exc.detail}

    try:
        final = _graph.invoke(
            {"question": request.question, "history": request.history}
        )
    except Exception:
        logger.exception("chat_turn_failed")
        _log_turn(
            "upstream_failure",
            question_chars=len(request.question),
            history_items=len(request.history),
        )
        return {"error": "upstream_failure"}

    hits = final.get("hits") or []
    _log_turn(
        "ok" if hits else "no_context",
        question_chars=len(request.question),
        history_items=len(request.history),
        hits=len(hits),
        retrieval_ms=final.get("retrieval_ms", 0),
        model_ms=final.get("model_ms", 0),
    )
    answer = final.get("answer") or NO_CONTEXT_ANSWER
    return {"answer": answer, "sources": build_sources(hits)}


if __name__ == "__main__":
    app.run()

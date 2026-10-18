"""Request validation for the chat agent (Plane B, spec `chat-agent-runtime`).

Pure: no I/O, no AWS. On rejection raises `InvalidRequest` whose `detail` is a
short rule name, never an echo of the client's input.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import (
    CHAT_MAX_HISTORY_ITEM_CHARS,
    CHAT_MAX_HISTORY_TURNS,
    CHAT_MAX_QUESTION_CHARS,
)

_ROLES = ("user", "assistant")


class InvalidRequest(Exception):
    """The payload broke a validation rule; `detail` names the rule."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class ChatRequest:
    question: str
    history: list[dict]  # Converse message form: {"role", "content": [{"text"}]}


def parse_request(payload: object) -> ChatRequest:
    """Validate `payload` and return a `ChatRequest`, or raise `InvalidRequest`."""
    if not isinstance(payload, dict):
        raise InvalidRequest("payload_not_object")

    question = payload.get("question")
    if not isinstance(question, str):
        raise InvalidRequest("question_missing")
    question = question.strip()
    if not question:
        raise InvalidRequest("question_empty")
    if len(question) > CHAT_MAX_QUESTION_CHARS:
        raise InvalidRequest("question_too_long")

    raw = payload.get("history", [])
    if not isinstance(raw, list):
        raise InvalidRequest("history_not_list")
    if len(raw) > CHAT_MAX_HISTORY_TURNS * 2:
        raise InvalidRequest("history_too_long")

    messages: list[dict] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise InvalidRequest("history_item_not_object")
        role = item.get("role")
        if role not in _ROLES:
            raise InvalidRequest("history_bad_role")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise InvalidRequest("history_item_text_invalid")
        if len(text) > CHAT_MAX_HISTORY_ITEM_CHARS:
            raise InvalidRequest("history_item_too_long")
        if role != _ROLES[i % 2]:
            raise InvalidRequest("history_roles_not_alternating")
        messages.append({"role": role, "content": [{"text": text}]})
    if messages and messages[-1]["role"] != "assistant":
        raise InvalidRequest("history_must_end_with_assistant")

    return ChatRequest(question=question, history=messages)

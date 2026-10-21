"""The chat Lambda entrypoint (spec `chat-api`).

Maps an API Gateway HTTP API (payload format 2.0) `POST /v1/chat` event to one
`InvokeAgentRuntime` call on the `ai_radar_chat` agent and back to a typed
response. The agent owns the request rules (CA-3); this edge only checks the
JSON shape and a byte cap so a bad body does not waste an invocation. No CORS
headers are emitted: API Gateway owns CORS. Imports no other first-party
package.
"""
from __future__ import annotations

import base64
import json
import logging
import time
import traceback
import uuid
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ReadTimeoutError

from chat_api.config import (
    CHAT_RUNTIME_ARN,
    CONNECT_TIMEOUT_SECONDS,
    MAX_BODY_BYTES,
    READ_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)
# The Lambda Python runtime leaves the root logger at WARNING unless a log level is
# configured, which would drop the INFO chat_api_request record.
logger.setLevel(logging.INFO)

_client: Any = None


def _agentcore() -> Any:
    """One client per container. `total_max_attempts: 1` means no retry at all (botocore's
    `max_attempts` counts retries), so a slow Sonnet turn is never paid twice."""
    global _client
    if _client is None:
        _client = boto3.client(
            "bedrock-agentcore",
            config=Config(
                connect_timeout=CONNECT_TIMEOUT_SECONDS,
                read_timeout=READ_TIMEOUT_SECONDS,
                retries={"total_max_attempts": 1},
            ),
        )
    return _client


def _response(status_code: int, payload: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload),
    }


def _invalid(rule: str) -> tuple[int, dict, str]:
    return 400, {"error": "invalid_request", "detail": rule}, "invalid_request"


def _raw_body(event: dict) -> bytes | None:
    body = event.get("body")
    if body is None or body == "":
        return None
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    return body.encode("utf-8")


def _map_reply(raw: bytes) -> tuple[int, dict, str]:
    """Maps the agent's reply; anything unrecognised is a 502."""
    failure = (502, {"error": "upstream_failure"}, "upstream_failure")
    try:
        reply = json.loads(raw)
    except ValueError:
        return failure
    if not isinstance(reply, dict):
        return failure
    error = reply.get("error")
    if error == "invalid_request":
        return 400, reply, "invalid_request"
    if error is not None:
        return failure
    answer, sources = reply.get("answer"), reply.get("sources")
    if isinstance(answer, str) and isinstance(sources, list):
        return 200, {"answer": answer, "sources": sources}, "ok"
    return failure


def _sizes(parsed: Any) -> tuple[int, int]:
    """Best-effort (question_chars, history_items); sizes only, never text."""
    if not isinstance(parsed, dict):
        return 0, 0
    question, history = parsed.get("question"), parsed.get("history")
    return (
        len(question) if isinstance(question, str) else 0,
        len(history) if isinstance(history, list) else 0,
    )


def _process(event: dict, session_id: str) -> tuple[int, dict, str, int, int]:
    raw = _raw_body(event)
    if raw is None:
        return (*_invalid("body_missing"), 0, 0)
    if len(raw) > MAX_BODY_BYTES:
        return (*_invalid("body_too_large"), 0, 0)
    try:
        parsed = json.loads(raw)
    except ValueError:  # includes UnicodeDecodeError
        return (*_invalid("body_not_json"), 0, 0)
    if not isinstance(parsed, dict):
        return (*_invalid("body_not_object"), 0, 0)
    question_chars, history_items = _sizes(parsed)

    try:
        result = _agentcore().invoke_agent_runtime(
            agentRuntimeArn=CHAT_RUNTIME_ARN,
            qualifier="DEFAULT",
            runtimeSessionId=session_id,
            contentType="application/json",
            accept="application/json",
            payload=raw,
        )
        reply = result["response"].read()
    except ReadTimeoutError:
        logger.exception(json.dumps({"event": "chat_api_upstream_error", "session_id": session_id}))
        return 504, {"error": "upstream_timeout"}, "upstream_timeout", question_chars, history_items
    except Exception:
        logger.exception(json.dumps({"event": "chat_api_upstream_error", "session_id": session_id}))
        return 502, {"error": "upstream_failure"}, "upstream_failure", question_chars, history_items

    status, payload, outcome = _map_reply(reply)
    return status, payload, outcome, question_chars, history_items


def _frames(tb: Any) -> list[str]:
    """`file:line in function` per frame; never source lines or the exception message."""
    return [f"{f.filename}:{f.lineno} in {f.name}" for f in traceback.extract_tb(tb)]


def handler(event: dict, context: Any) -> dict:
    """`POST /v1/chat` with `{"question": str, "history": [...]}` -> the agent's
    `{"answer", "sources"}` (200), `{"error": "invalid_request", "detail"}` (400),
    `{"error": "upstream_failure"}` (502) or `{"error": "upstream_timeout"}` (504).

    Logs one text-free `chat_api_request` record per request.
    """
    started = time.monotonic()
    session_id = str(uuid.uuid4())
    question_chars = history_items = 0
    try:
        status, payload, outcome, question_chars, history_items = _process(event, session_id)
    except Exception as exc:  # noqa: BLE001  # last-resort catch-all; logged below, typed 500
        # Class name and stack frames only: the exception message can echo caller text.
        logger.error(
            json.dumps(
                {
                    "event": "chat_api_request_failed",
                    "session_id": session_id,
                    "exception_class": type(exc).__name__,
                    "frames": _frames(exc.__traceback__),
                }
            )
        )
        status, payload, outcome = 500, {"error": "internal_error"}, "internal_error"

    logger.info(
        json.dumps(
            {
                "event": "chat_api_request",
                "status": status,
                "outcome": outcome,
                "question_chars": question_chars,
                "history_items": history_items,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "session_id": session_id,
            }
        )
    )
    return _response(status, payload)

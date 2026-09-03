"""The Lambda entrypoint (Phase 2, spec `feed-api`).

Maps an API Gateway HTTP API (payload format 2.0) event to a `FeedResponse`
JSON body, or a typed 4xx/5xx. No CORS headers are emitted here — API
Gateway owns CORS and ignores backend CORS headers.
"""
from __future__ import annotations

import json
import logging
import time

from api.config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from api.cursor import InvalidCursorError, decode_cursor, encode_cursor
from api.dynamo import card_table
from api.feed import query_feed
from contracts.card import FeedResponse

logger = logging.getLogger(__name__)


def _response(status_code: int, payload: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload),
    }


def _error(status_code: int, error: str, message: str) -> dict:
    return _response(status_code, {"error": error, "message": message})


def _parse_limit(raw_limit: str | None) -> int | dict:
    """Returns the parsed `int`, or an error response dict on failure."""
    if raw_limit is None:
        return DEFAULT_PAGE_SIZE
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return _error(
            400,
            "invalid_limit",
            f"limit must be an integer between 1 and {MAX_PAGE_SIZE}",
        )
    if not (1 <= limit <= MAX_PAGE_SIZE):
        return _error(
            400,
            "invalid_limit",
            f"limit must be an integer between 1 and {MAX_PAGE_SIZE}",
        )
    return limit


def handler(event: dict, context) -> dict:
    """`GET /v1/cards?tag=<str>&limit=<int>&cursor=<str>` (API Gateway HTTP API,
    payload format 2.0) -> a `FeedResponse` JSON body.

    200 body: {"cards": [CardOut, ...], "next_cursor": str | null}
    400 body: {"error": "<code>", "message": "<human-readable>"}
    500 body: {"error": "internal_error", "message": "internal error"}

    Emits NO CORS headers — API Gateway owns CORS and ignores backend CORS
    headers (see AD / pinned surface above). Logs one structured
    `feed_api_request` record per request (`json.dumps`, same idiom as
    `runtime_app.py`'s `curation_run_complete`).
    """
    started = time.monotonic()
    try:
        query = event.get("queryStringParameters") or {}

        raw_tag = query.get("tag")
        tag = raw_tag if raw_tag and raw_tag.strip() else None

        limit_or_error = _parse_limit(query.get("limit"))
        if isinstance(limit_or_error, dict):
            return limit_or_error
        limit = limit_or_error

        raw_cursor = query.get("cursor")
        exclusive_start_key = None
        if raw_cursor is not None:
            try:
                exclusive_start_key = decode_cursor(raw_cursor)
            except InvalidCursorError:
                return _error(
                    400, "invalid_cursor", "cursor is malformed or has been tampered with"
                )

        table = card_table()
        page = query_feed(table, tag=tag, limit=limit, exclusive_start_key=exclusive_start_key)

        next_cursor = (
            encode_cursor(page.last_evaluated_key)
            if page.last_evaluated_key is not None
            else None
        )
        body = FeedResponse(cards=page.cards, next_cursor=next_cursor).model_dump_json()
        response = {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": body,
        }

        duration_ms = round((time.monotonic() - started) * 1000, 2)
        logger.info(
            json.dumps(
                {
                    "event": "feed_api_request",
                    "tag": tag,
                    "limit": limit,
                    "returned": len(page.cards),
                    "skipped": page.skipped,
                    "has_next": next_cursor is not None,
                    "duration_ms": duration_ms,
                }
            )
        )
        return response
    except Exception:
        logger.exception(json.dumps({"event": "feed_api_request_failed"}))
        return _error(500, "internal_error", "internal error")

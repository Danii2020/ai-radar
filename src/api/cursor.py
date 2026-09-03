"""Opaque pagination cursor: base64url(JSON(LastEvaluatedKey)).

The ENCODING is an implementation detail clients must not parse. The
ROUND TRIP is a hard contract (see Behavior Guarantees 5-8).
"""
from __future__ import annotations

import base64
import json

from api.config import FEED_GSI_PARTITION

#: The exact key set a `feed-by-score` query's LastEvaluatedKey carries
#: (verified against moto). Anything else is a tampered/foreign cursor.
CURSOR_KEYS: frozenset[str] = frozenset({"card_id", "gsi_pk", "gsi_sk"})


class InvalidCursorError(ValueError):
    """Raised for any cursor that is not a well-formed, in-partition key."""


def encode_cursor(last_evaluated_key: dict) -> str:
    """`{"card_id": …, "gsi_pk": "CARD", "gsi_sk": …}` -> URL-safe base64 of its
    compact, key-sorted JSON, with `=` padding stripped. Deterministic: the
    same key always yields the same token."""
    compact = json.dumps(last_evaluated_key, sort_keys=True, separators=(",", ":"))
    token = base64.urlsafe_b64encode(compact.encode("utf-8")).decode("ascii")
    return token.rstrip("=")


def decode_cursor(token: str) -> dict:
    """Inverse of `encode_cursor`. Re-pads, base64url-decodes, JSON-parses, and
    VALIDATES: a JSON object whose keys are exactly CURSOR_KEYS, all values
    `str`, and `gsi_pk == config.FEED_GSI_PARTITION`. Anything else (bad
    base64, bad JSON, wrong/missing keys, non-str value, foreign partition)
    raises InvalidCursorError. Never returns a partially-trusted dict — the
    decoded value is passed straight to DynamoDB as ExclusiveStartKey, so this
    IS the trust boundary."""
    padded = token + "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:
        raise InvalidCursorError("cursor is not valid base64") from exc

    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidCursorError("cursor is not valid JSON") from exc

    if not isinstance(decoded, dict):
        raise InvalidCursorError("cursor must decode to a JSON object")

    if set(decoded.keys()) != CURSOR_KEYS:
        raise InvalidCursorError("cursor has an unexpected key set")

    if not all(isinstance(value, str) for value in decoded.values()):
        raise InvalidCursorError("cursor values must all be strings")

    if decoded["gsi_pk"] != FEED_GSI_PARTITION:
        raise InvalidCursorError("cursor references a foreign gsi partition")

    return decoded

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


_DIR_KEY = "dir"
_DIRECTIONS: frozenset[str] = frozenset({"next", "prev"})


def encode_cursor(key: dict | None, direction: str = "next") -> str:
    """URL-safe base64 of compact, key-sorted JSON, `=` padding stripped.

    Shapes (the only ones decode accepts): forward with a key is the bare
    three-key object (byte-identical to cursors issued before backward paging);
    backward with a key adds `"dir": "prev"`; with no key the payload is just
    `{"dir": direction}` (`"next"` = start of feed, `"prev"` = end of feed).
    Deterministic: the same inputs always yield the same token."""
    if direction not in _DIRECTIONS:
        raise ValueError(f"unknown cursor direction: {direction!r}")
    if key is None:
        payload: dict = {_DIR_KEY: direction}
    elif direction == "prev":
        payload = {**key, _DIR_KEY: "prev"}
    else:
        payload = key
    compact = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    token = base64.urlsafe_b64encode(compact.encode("utf-8")).decode("ascii")
    return token.rstrip("=")


def decode_cursor(token: str) -> tuple[str, dict | None]:
    """Inverse of `encode_cursor`: `(direction, key | None)`. Re-pads,
    base64url-decodes, JSON-parses, and VALIDATES exact shapes only: the bare
    three-key object (forward), the three keys plus `dir == "prev"`, or a
    lone `dir` of `"next"`/`"prev"` (keyless). Keys are exactly CURSOR_KEYS,
    all values `str`, `gsi_pk == config.FEED_GSI_PARTITION`. Anything else
    raises InvalidCursorError. The returned key is passed straight to DynamoDB
    as ExclusiveStartKey, so this IS the trust boundary."""
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

    direction = "next"
    if _DIR_KEY in decoded:
        direction = decoded.pop(_DIR_KEY)
        if not isinstance(direction, str) or direction not in _DIRECTIONS:
            raise InvalidCursorError("cursor has an unknown direction")
        if not decoded:
            return direction, None
        if direction != "prev":
            raise InvalidCursorError("forward cursors carry no direction marker")

    if set(decoded.keys()) != CURSOR_KEYS:
        raise InvalidCursorError("cursor has an unexpected key set")

    if not all(isinstance(value, str) for value in decoded.values()):
        raise InvalidCursorError("cursor values must all be strings")

    if decoded["gsi_pk"] != FEED_GSI_PARTITION:
        raise InvalidCursorError("cursor references a foreign gsi partition")

    return direction, decoded

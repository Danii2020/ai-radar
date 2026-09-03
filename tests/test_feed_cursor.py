"""Tests for `src/api/cursor.py` — `encode_cursor`/`decode_cursor`.

Spec: specs/feed-api/contract.md "`src/api/cursor.py` — CREATE (the
pagination contract)"; Behavior Guarantees 5, 7, 8; specs/feed-api/audit.md
T5, T8.

Pure functions — zero AWS/network. `CURSOR_KEYS`'s exact membership
(`card_id`/`gsi_pk`/`gsi_sk`) is asserted indirectly, through the
missing/extra-key rejection cases below, rather than as a standalone
"the constant equals itself" tautology.

RED phase: `src/api/cursor.py` does not exist yet. Every test in this file is
expected to fail at collection with `ModuleNotFoundError: No module named
'api.cursor'` (or similar) until the implementation lands.
"""
from __future__ import annotations

import base64
import json

import pytest

from api.cursor import InvalidCursorError, decode_cursor, encode_cursor

WELL_FORMED_KEY = {"card_id": "0a1b2c3d4e5f6071", "gsi_pk": "CARD", "gsi_sk": "008#2026-08-29"}


# Guarantee 8: decode(encode(k)) == k for a well-formed LastEvaluatedKey.
def test_decode_of_encode_returns_the_original_key():
    token = encode_cursor(WELL_FORMED_KEY)
    assert decode_cursor(token) == WELL_FORMED_KEY


# Guarantee 8: same key -> same token, regardless of the input dict's key
# insertion order (key-sorted, compact JSON per the docstring).
def test_encode_cursor_is_deterministic_regardless_of_key_order():
    reordered = {"gsi_sk": "008#2026-08-29", "card_id": "0a1b2c3d4e5f6071", "gsi_pk": "CARD"}
    assert encode_cursor(WELL_FORMED_KEY) == encode_cursor(reordered)


# Guarantee 5: base64url with padding ('=') stripped.
def test_encode_cursor_output_has_no_base64_padding_characters():
    token = encode_cursor(WELL_FORMED_KEY)
    assert "=" not in token


def test_encode_cursor_is_valid_urlsafe_base64_of_key_sorted_json():
    token = encode_cursor(WELL_FORMED_KEY)
    padded = token + "=" * (-len(token) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(padded.encode()))
    assert decoded == WELL_FORMED_KEY


# Guarantee 7 / Error Handling Contract: every rejection path raises
# InvalidCursorError, never returns a partially-trusted dict.
def test_decode_cursor_rejects_invalid_base64():
    with pytest.raises(InvalidCursorError):
        decode_cursor("not-valid-base64!!!")


def test_decode_cursor_rejects_base64_that_is_not_json():
    token = base64.urlsafe_b64encode(b"not json at all").decode().rstrip("=")
    with pytest.raises(InvalidCursorError):
        decode_cursor(token)


def test_decode_cursor_rejects_a_json_array_instead_of_an_object():
    token = base64.urlsafe_b64encode(json.dumps(["a", "b", "c"]).encode()).decode().rstrip("=")
    with pytest.raises(InvalidCursorError):
        decode_cursor(token)


def test_decode_cursor_rejects_an_object_missing_a_required_key():
    incomplete = {"card_id": "0a1b2c3d4e5f6071", "gsi_pk": "CARD"}  # missing gsi_sk
    token = base64.urlsafe_b64encode(json.dumps(incomplete).encode()).decode().rstrip("=")
    with pytest.raises(InvalidCursorError):
        decode_cursor(token)


def test_decode_cursor_rejects_an_object_with_an_extra_key():
    extra = dict(WELL_FORMED_KEY, extra_field="tampered")
    token = base64.urlsafe_b64encode(json.dumps(extra).encode()).decode().rstrip("=")
    with pytest.raises(InvalidCursorError):
        decode_cursor(token)


def test_decode_cursor_rejects_a_non_string_value():
    bad_value = dict(WELL_FORMED_KEY, gsi_sk=8)
    token = base64.urlsafe_b64encode(json.dumps(bad_value).encode()).decode().rstrip("=")
    with pytest.raises(InvalidCursorError):
        decode_cursor(token)


def test_decode_cursor_rejects_a_foreign_gsi_partition():
    """A cursor cannot be used to steer the query at another partition
    (Guarantee 7: "cannot be used to steer the query at another partition or
    another index")."""
    foreign = dict(WELL_FORMED_KEY, gsi_pk="NOT-CARD")
    token = base64.urlsafe_b64encode(json.dumps(foreign).encode()).decode().rstrip("=")
    with pytest.raises(InvalidCursorError):
        decode_cursor(token)


def test_invalid_cursor_error_is_a_value_error_subclass():
    assert issubclass(InvalidCursorError, ValueError)

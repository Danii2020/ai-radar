"""Versioned, validated `Card` API contract (Phase 2, spec `feed-api`).

Promotes `shared.cards.Card` (a plain dataclass, Plane A's internal type) to
the published, versioned schema `architecture-principles.md` boundary 2 calls
for once a real API exists. This module is the ONLY definition of the feed
API's response shape; `docs/api/feed-api.v1.schema.json` is generated from it
and is what `web-feed-ui` (Spec 02) generates TypeScript types from.

Plane A does not import this module and `shared.cards.Card` is unchanged: a
`CardOut` is a READ-SIDE PROJECTION of a stored DynamoDB item (Card content
fields + `card_id` + `created_at`/`updated_at`), not a rename of the dataclass.
Changing a field here is a BREAKING API change — bump the version.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

#: Bumped only on a breaking change to CardOut/FeedResponse. Mirrored by the
#: route prefix (`/v1/cards`) and the schema artifact filename.
CARD_SCHEMA_VERSION: str = "v1"


class CardOut(BaseModel):
    """One curated card, as returned by `GET /v1/cards`.

    Field-for-field parity with the DynamoDB item written by
    `curation.dynamo.DynamoCardStore.upsert` (see
    specs/dynamodb-card-store/contract.md "Item schema"), minus the internal
    index keys `gsi_pk`/`gsi_sk` and the Phase-3-reserved `embedding`.
    """

    model_config = ConfigDict(extra="ignore")

    card_id: str        # sha256(url)[:16] — the table PK, stable per URL
    title: str
    url: str
    source: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    type: str           # "paper" | "release" | "project" | "news" | "concept" (not enforced)
    relevance: int      # 1-10; stored as N, arrives as Decimal, coerced here
    published: str      # ISO date "YYYY-MM-DD", or "" when the source had none
    takeaways: list[str] = Field(default_factory=list)
    created_at: str     # ISO8601 UTC, set once by Plane A
    updated_at: str     # ISO8601 UTC, advances on every re-curation


class FeedResponse(BaseModel):
    """One page of the feed. `next_cursor` is opaque: pass it back verbatim as
    `?cursor=`. It is `None` — and ONLY None — when the feed is exhausted."""

    model_config = ConfigDict(extra="ignore")

    cards: list[CardOut]
    next_cursor: str | None = None


def json_schema() -> dict:
    """The published JSON Schema artifact (`$defs`-linked CardOut inside
    FeedResponse). Written to docs/api/feed-api.v1.schema.json by
    `export_api_schema.py`; a test fails if the file drifts from this."""
    return FeedResponse.model_json_schema()

"""API-plane (Plane B) config for the feed read API (Phase 2, spec `feed-api`).

Deliberately does NOT import `shared.config` (AD-3): in Lambda, `AWS_REGION`
is set by the runtime and picked up by boto3's default credential chain, and
there is no `.env` in the image (`.dockerignore` excludes it), so
`load_dotenv()`'s side effect would be dead weight at every cold start.

Env parsing and validation are owned by `_ApiSettings` (pydantic-settings);
the module-level UPPERCASE constants below are the public surface.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class _ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    card_table_name: str = Field("ai-radar-cards", validation_alias="CARD_TABLE_NAME")
    default_page_size: int = Field(20, validation_alias="FEED_API_DEFAULT_PAGE_SIZE")
    max_page_size: int = Field(100, validation_alias="FEED_API_MAX_PAGE_SIZE")


_settings = _ApiSettings()

CARD_TABLE_NAME: str = _settings.card_table_name
DEFAULT_PAGE_SIZE: int = _settings.default_page_size
MAX_PAGE_SIZE: int = _settings.max_page_size

# Fixed constants — NOT env-overridable, deliberately outside the model.
# DUPLICATED from curation/config.py because Plane B must not import Plane A
# (architecture-principles boundary 1); tests/test_feed_api_contract.py asserts
# the two stay equal (AD-4).
FEED_GSI_NAME: str = "feed-by-score"
FEED_GSI_PARTITION: str = "CARD"

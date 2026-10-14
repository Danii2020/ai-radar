"""Chat-plane (Plane B) config for the DynamoDB retriever (spec `chat-retrieval`).

Deliberately does NOT import `curation` or `api`: Plane B must not import
Plane A. `shared` is neutral: it is imported below for its `load_dotenv()`
side effect so a `.env` `CARD_STORE_BACKEND` is honored. Mirrors `api/config.py`.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Imported for its import-time side effect ONLY: `shared.config` owns the one
# `load_dotenv()` call, which must have run before `_ChatSettings()` below reads
# the environment.
import shared.config as _shared_config  # noqa: F401


class _ChatSettings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    card_table_name: str = Field("ai-radar-cards", validation_alias="CARD_TABLE_NAME")

    # Store selector for run_chat.py: "json" (default) | "dynamo". Duplicated
    # from curation/config.py (same env key and default) so the chat CLI never
    # imports Plane A.
    card_store_backend: str = Field("json", validation_alias="CARD_STORE_BACKEND")


_settings = _ChatSettings()

CARD_TABLE_NAME: str = _settings.card_table_name
CARD_STORE_BACKEND: str = _settings.card_store_backend

# Fixed constants — NOT env-overridable. DUPLICATED from curation/config.py
# (architecture-principles boundary 1); tests/test_chat_contract.py asserts
# the two stay equal.
FEED_GSI_NAME: str = "feed-by-score"
FEED_GSI_PARTITION: str = "CARD"

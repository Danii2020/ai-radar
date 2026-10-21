"""Chat-API (Plane B edge) settings (spec `chat-api`).

Imports no other first-party package. In Lambda there is no `.env` (the image
copies only this package), so no `load_dotenv()` is called. `CHAT_RUNTIME_ARN`
is set by CDK; a missing value fails at import with a typed validation error
naming the variable, instead of failing on the first invoke.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class _ChatApiSettings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    chat_runtime_arn: str = Field(..., min_length=1, validation_alias="CHAT_RUNTIME_ARN")


_settings = _ChatApiSettings()  # type: ignore[call-arg]  # value comes from the environment

CHAT_RUNTIME_ARN: str = _settings.chat_runtime_arn

# Fixed constants, NOT env-overridable. Duplicated rather than imported from
# `chat` (the agent owns its own rules; this edge only avoids wasted invokes).
MAX_BODY_BYTES: int = 524_288  # 512 KiB; the agent's own cap is ~81,000 chars
CONNECT_TIMEOUT_SECONDS: int = 3
# The 28 s Lambda timeout lives only in infra/lib/chat_api.py (DEFAULT_TIMEOUT): infra must
# not import src, and the handler never reads its own timeout.
# connect (3) + read (22) = 25 s, leaving 3 s of the 28 s Lambda timeout to write the
# 504 response and the chat_api_request record.
READ_TIMEOUT_SECONDS: int = 22

"""Plane B guards for `src/chat/` (AC8) and the Titan role grant.

Spec: specs/chat-retrieval/intent.md AC8; execution-plan.md § Validation row
AC8; tasks.md O5. Modeled on tests/test_feed_api_contract.py: AST-based
plane-separation and boto3-confinement checks plus the duplicated-constant
equality test (feed-api AD-4 precedent). Zero AWS/network.

RED phase: `src/chat/` does not exist yet.
"""
from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


# --- duplicated Plane A constants ---------------------------------------------


def test_chat_config_constants_match_curation_config():
    from chat.config import FEED_GSI_NAME, FEED_GSI_PARTITION
    from curation.config import FEED_GSI_NAME as CURATION_GSI_NAME
    from curation.config import FEED_GSI_PARTITION as CURATION_GSI_PARTITION

    assert FEED_GSI_NAME == CURATION_GSI_NAME
    assert FEED_GSI_PARTITION == CURATION_GSI_PARTITION


@pytest.fixture
def fresh_config_modules(monkeypatch):
    """Make the next import of shared/curation/chat config re-evaluate from
    scratch like a fresh interpreter (no sys.modules entry AND no package
    attribute), and restore the originals (both) on teardown so no other test sees a stale module."""
    names = ("shared.config", "curation.config", "chat.config")
    for name in names:
        module = importlib.import_module(name)
        parent, _, attr = name.rpartition(".")
        # setattr first (records the original for teardown), then delete, so
        # the package attribute is gone like in a fresh interpreter.
        monkeypatch.setattr(sys.modules[parent], attr, module)
        monkeypatch.delattr(sys.modules[parent], attr)
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.delenv("CARD_STORE_BACKEND", raising=False)


def test_chat_config_card_store_backend_default_matches_curation_default(
    monkeypatch, fresh_config_modules
):
    # Hermetic: a developer's .env must not leak into the defaults.
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)

    chat_config = importlib.import_module("chat.config")
    curation_config = importlib.import_module("curation.config")

    assert chat_config.CARD_STORE_BACKEND == curation_config.CARD_STORE_BACKEND == "json"


def test_chat_config_picks_up_a_dotenv_provided_card_store_backend(
    monkeypatch, fresh_config_modules
):
    """Regression: with CARD_STORE_BACKEND only in `.env`, importing
    `chat.config` on its own must still see it (the dotenv load must run
    before chat.config is evaluated, whatever the import order)."""
    import dotenv

    def fake_load_dotenv(*args, **kwargs):
        monkeypatch.setenv("CARD_STORE_BACKEND", "dynamo")
        return True

    monkeypatch.setattr(dotenv, "load_dotenv", fake_load_dotenv)

    chat_config = importlib.import_module("chat.config")

    assert chat_config.CARD_STORE_BACKEND == "dynamo"


@pytest.fixture
def reload_chat_config(monkeypatch):
    @contextmanager
    def _reload(env: dict | None = None, clear: list | None = None):
        for key in clear or ():
            monkeypatch.delenv(key, raising=False)
        for key, value in (env or {}).items():
            monkeypatch.setenv(key, value)
        module = importlib.import_module("chat.config")
        importlib.reload(module)
        try:
            yield module
        finally:
            monkeypatch.undo()
            importlib.reload(module)

    return _reload


def test_chat_config_table_name_defaults_to_the_deployed_table(reload_chat_config):
    with reload_chat_config(clear=["CARD_TABLE_NAME"]) as module:
        assert module.CARD_TABLE_NAME == "ai-radar-cards"


def test_chat_config_table_name_is_env_overridable(reload_chat_config):
    with reload_chat_config(env={"CARD_TABLE_NAME": "custom-cards"}) as module:
        assert module.CARD_TABLE_NAME == "custom-cards"


def test_chat_config_card_store_backend_is_env_overridable(reload_chat_config):
    with reload_chat_config(env={"CARD_STORE_BACKEND": "dynamo"}) as module:
        assert module.CARD_STORE_BACKEND == "dynamo"


def test_chat_config_gsi_constants_are_fixed_not_env_overridable(reload_chat_config):
    with reload_chat_config(
        env={"FEED_GSI_NAME": "clobbered", "FEED_GSI_PARTITION": "clobbered"}
    ) as module:
        assert module.FEED_GSI_NAME == "feed-by-score"
        assert module.FEED_GSI_PARTITION == "CARD"

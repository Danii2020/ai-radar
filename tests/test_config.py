"""Tests for `src/shared/config.py` and `src/curation/config.py`.

Spec: specs/pydantic-settings-config/{intent.md,contract.md,audit.md,tasks.md}.

RED phase (tasks.md Phase 1): this file is written **before** either config
module is migrated to `pydantic-settings`. Three groups of tests result:

1. **Characterization tests** (tasks.md Tasks 1.5-1.10, audit.md T1-T12) are
   written against **today's** `os.getenv`-based code and are expected to
   **pass immediately** — they pin every env-var name, every default value,
   every fixed (non-overridable) constant, and the two hand-rolled list
   splits, so the Phase 2/3 migration can only pass or fail loudly, never
   silently drift a value.
2. **The two deliberate-change rows** (tasks.md Task 1.11, audit.md T16/T17)
   are marked `@pytest.mark.xfail(strict=True)` — they fail today (the old
   `str(raw).lower() == "true"` boolean silently swallows both cases) and
   must be un-xfailed once the migration lands (tasks.md Task 3.8), at which
   point `strict=True` makes an accidental leftover marker fail loudly (XPASS)
   as a reminder to remove it.
3. **Validation-error, dependency-shape, and consumer-regression tests**
   (tasks.md Phase 4, audit.md T13-T15, T18-T21) are true RED — they assert
   the *new* value of this spec (`pydantic.ValidationError` naming the
   offending env var; `pydantic-settings` as an explicit main dependency) and
   only pass once both config modules are migrated and `uv add
   pydantic-settings` has run.

No test in this file makes a network or AWS call — config import performs no
I/O beyond `Path`/dict construction and (today) `load_dotenv()`, which is
itself neutralized by the reload harness below so tests are hermetic
regardless of this developer machine's local `.env` contents (this repo's own
`.env` sets `TAVILY_API_KEY` and `CARD_STORE_BACKEND` to non-default values,
which would otherwise leak into "clean environment" default assertions).
"""
from __future__ import annotations

import importlib
import os
import re
import sys
import tomllib
from contextlib import contextmanager
from pathlib import Path

import pydantic
import pytest

REPO_ROOT = Path(__file__).parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

# --- Ground truth, hand-copied from the current source (contract.md's
# "byte-identical" target) — independent of whatever `_DEFAULT_SEEDS` /
# `FEEDS` the module under test claims, so a migration that quietly edits
# either is still caught. ------------------------------------------------
EXPECTED_DEFAULT_SEEDS = [
    "latest large language model releases and updates",
    "new generative AI and LLM research papers",
    "AI agents and agentic framework news",
    "machine learning and deep learning breakthroughs",
    "open source AI model and tooling releases",
]
EXPECTED_FEEDS = {
    "arXiv cs.AI": "http://export.arxiv.org/rss/cs.AI",
    "arXiv cs.LG": "http://export.arxiv.org/rss/cs.LG",
    "Hugging Face Blog": "https://huggingface.co/blog/feed.xml",
    "BAIR Blog": "https://bair.berkeley.edu/blog/feed.xml",
    "Simon Willison": "https://simonwillison.net/atom/everything/",
    "MIT Tech Review AI": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
}

# --- The 26-row env-var -> constant -> default/override table (contract.md
# Behavior Guarantee 1, Gate G3). Each row: (env_name, attr_name, override_str,
# expected_override_value, expected_default_value). --------------------------
SHARED_ENV_CASES = [
    ("AWS_REGION", "AWS_REGION", "eu-west-1", "eu-west-1", "us-east-1"),
    (
        "HAIKU_MODEL_ID",
        "HAIKU_MODEL_ID",
        "custom-haiku-id",
        "custom-haiku-id",
        "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    ),
    ("HAIKU_INPUT_USD_PER_1M", "HAIKU_INPUT_USD_PER_1M", "2.5", 2.5, 1.0),
    ("HAIKU_OUTPUT_USD_PER_1M", "HAIKU_OUTPUT_USD_PER_1M", "10.5", 10.5, 5.0),
    (
        "SONNET_MODEL_ID",
        "SONNET_MODEL_ID",
        "custom-sonnet-id",
        "custom-sonnet-id",
        "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    ),
    (
        "EMBED_MODEL_ID",
        "EMBED_MODEL_ID",
        "custom-embed-id",
        "custom-embed-id",
        "amazon.titan-embed-text-v2:0",
    ),
    ("EMBED_DIM", "EMBED_DIM", "512", 512, 256),
    ("AI_RADAR_TOP_K", "TOP_K", "9", 9, 4),
    ("AI_RADAR_MAX_ITEMS", "MAX_ITEMS", "33", 33, 8),
    ("AI_RADAR_PER_FEED", "PER_FEED", "12", 12, 5),
    (
        "AI_RADAR_CACHE_DIR",
        "CACHE_DIR",
        "/tmp/ai-radar-test-cache",
        Path("/tmp/ai-radar-test-cache"),
        Path(".ai_radar_cache"),
    ),
]
SHARED_ALL_ENV_NAMES = [row[0] for row in SHARED_ENV_CASES]

CURATION_ENV_CASES = [
    ("TAVILY_API_KEY", "TAVILY_API_KEY", "sekrit-key", "sekrit-key", ""),
    (
        "CURATION_TAVILY_SEEDS",
        "TAVILY_SEEDS",
        "seed one; seed two",
        ["seed one", "seed two"],
        list(EXPECTED_DEFAULT_SEEDS),
    ),
    (
        "CURATION_TAVILY_RESULTS_PER_QUERY",
        "TAVILY_RESULTS_PER_QUERY",
        "9",
        9,
        5,
    ),
    ("CURATION_TAVILY_MAX_RESULTS", "TAVILY_MAX_RESULTS", "42", 42, 20),
    ("CURATION_TAVILY_DAYS", "TAVILY_DAYS", "14", 14, 7),
    (
        "CURATION_TAVILY_SEARCH_DEPTH",
        "TAVILY_SEARCH_DEPTH",
        "advanced",
        "advanced",
        "basic",
    ),
    ("CURATION_TAVILY_TOPIC", "TAVILY_TOPIC", "news", "news", "general"),
    (
        "CURATION_TAVILY_INCLUDE_DOMAINS",
        "TAVILY_INCLUDE_DOMAINS",
        "a.com, b.com",
        ["a.com", "b.com"],
        [],
    ),
    (
        "CURATION_TAVILY_EXCLUDE_DOMAINS",
        "TAVILY_EXCLUDE_DOMAINS",
        "c.com, d.com",
        ["c.com", "d.com"],
        [],
    ),
    (
        "CARD_TABLE_NAME",
        "CARD_TABLE_NAME",
        "custom-cards-table",
        "custom-cards-table",
        "ai-radar-cards",
    ),
    (
        "CARD_STORE_BACKEND",
        "CARD_STORE_BACKEND",
        "dynamo",
        "dynamo",
        "json",
    ),
    (
        "TAVILY_SECRET_NAME",
        "TAVILY_SECRET_NAME",
        "custom/secret-name",
        "custom/secret-name",
        "ai-radar/tavily-api-key",
    ),
    (
        "CURATION_TAVILY_CREDIT_PRICE_USD",
        "TAVILY_CREDIT_PRICE_USD",
        "0.02",
        0.02,
        0.008,
    ),
    (
        "CURATION_METRIC_NAMESPACE",
        "METRIC_NAMESPACE",
        "Custom/Namespace",
        "Custom/Namespace",
        "AIRadar/Curation",
    ),
    # Deliberately "false" (not "1"/"yolo") — semantics are unchanged by the
    # migration for this specific value, so this row belongs in the
    # characterization table, not the xfail rows below.
    ("CURATION_EMIT_METRICS", "EMIT_RUN_METRICS", "false", False, True),
]
CURATION_ALL_ENV_NAMES = [row[0] for row in CURATION_ENV_CASES]

# The 11 fixed constants that must NEVER move via same-named env var
# (intent.md Success Criteria Gate G4 / contract.md Behavior Guarantee 5).
SHARED_FIXED_CONSTANTS = ["FEEDS", "SEEN_PATH", "CARDS_PATH", "EMBED_PATH"]
CURATION_FIXED_CONSTANTS = [
    "FEED_GSI_NAME",
    "FEED_GSI_PARTITION",
    "TAVILY_SECRET_UNSET_SENTINEL",
    "TAVILY_SOURCE_PREFIX",
    "TAVILY_CREDITS_BY_DEPTH",
    "TAVILY_DEFAULT_CREDITS_PER_SEARCH",
    "_DEFAULT_SEEDS",
]


# --- Reload harness (tasks.md Task 1.4) -------------------------------------


@pytest.fixture
def reload_config_module(monkeypatch):
    """The one piece of new test machinery this spec needs.

    Returns a context-manager factory:

        with reload_config_module("shared.config", env={"AWS_REGION": "x"}) as m:
            assert m.AWS_REGION == "x"

    On entry: applies `env` via `monkeypatch.setenv` and `clear` via
    `monkeypatch.delenv`, then `importlib.reload()`s the named module (already
    imported once by an earlier test/collection, per the house `sys.path`
    setup in `conftest.py`) and yields it.

    On exit: undoes every env change this call made (`monkeypatch.undo()`)
    and reloads the module again, so it reflects the real, `.env`-driven
    default state again — no leaked override can bleed into a later `with`
    block or a later test.

    `dotenv.load_dotenv` (called at import time by both config modules today,
    and by `shared/config.py` alone after the migration) is patched to a
    no-op for the lifetime of this fixture, so default-value assertions never
    depend on this developer machine's `.env` file — Behavior Guarantee 9's
    "`.env` really reaches `os.environ`" claim gets its own dedicated test
    below instead, which does NOT use this fixture.
    """
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)

    @contextmanager
    def _reload(module_name: str, env: dict | None = None, clear: list | None = None):
        for key in clear or ():
            monkeypatch.delenv(key, raising=False)
        for key, value in (env or {}).items():
            monkeypatch.setenv(key, value)

        module = importlib.import_module(module_name)
        importlib.reload(module)
        try:
            yield module
        finally:
            monkeypatch.undo()
            # `monkeypatch.undo()` also reverts the `dotenv.load_dotenv`
            # no-op patch above; re-apply it so a second `with` block later
            # in the same test stays hermetic too.
            monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
            importlib.reload(module)

    return _reload


# --- T1: the reload harness itself ------------------------------------------


def test_reload_harness_applies_override_then_restores_pristine_default(
    reload_config_module,
):
    with reload_config_module("shared.config") as baseline:
        original_region = baseline.AWS_REGION

    with reload_config_module(
        "shared.config", env={"AWS_REGION": "reload-harness-probe"}
    ) as overridden:
        assert overridden.AWS_REGION == "reload-harness-probe"
        # `importlib.reload()` mutates the existing module object in place —
        # it does not replace the `sys.modules` entry with a new object.
        assert overridden is baseline

    with reload_config_module("shared.config") as restored:
        assert restored.AWS_REGION == original_region
        assert restored.AWS_REGION != "reload-harness-probe"


def test_reload_harness_neutralizes_local_dotenv_for_hermetic_defaults(
    reload_config_module,
):
    """This repo's own `.env` sets `TAVILY_API_KEY` to a real (non-empty)
    value and `CARD_STORE_BACKEND=dynamo` — without the harness's
    `dotenv.load_dotenv` no-op, a "clean environment" test would observe
    those, not the code's documented defaults."""
    with reload_config_module(
        "curation.config", clear=CURATION_ALL_ENV_NAMES
    ) as module:
        assert module.TAVILY_API_KEY == ""
        assert module.CARD_STORE_BACKEND == "json"


# --- T23: Behavior Guarantee 9 (".env" really reaches "os.environ") --------
#
# Deliberately does NOT use `reload_config_module` above — that fixture
# neuters `dotenv.load_dotenv` to a no-op precisely so default-value
# assertions stay hermetic. This test instead exercises the REAL,
# non-neutered `load_dotenv()` call in `shared/config.py`, redirected at a
# `tmp_path`-based `.env` file, and asserts the probe key it defines actually
# lands in the real process `os.environ` — the one side effect
# pydantic-settings' own `env_file=` source does NOT have, and the reason
# `shared/config.py` keeps calling `dotenv.load_dotenv()` directly (see
# contract.md Behavior Guarantee 9 / intent.md Constraints: "`.env` must keep
# reaching `os.environ`", so boto3 still sees AWS_ACCESS_KEY_ID /
# AWS_SECRET_ACCESS_KEY per `.env.example`).
#
# `dotenv.load_dotenv()`'s own file-discovery (`find_dotenv()`) walks upward
# from the *calling module's* file location, not from `os.getcwd()` — so a
# `tmp_path`-based `.env` file can only be observed by monkeypatching
# `dotenv.main.find_dotenv` to return it directly; `load_dotenv()` itself
# runs for real and un-mocked.


def test_shared_config_import_populates_os_environ_from_dotenv(monkeypatch, tmp_path):
    """Behavior Guarantee 9: importing `shared.config` loads `.env` into the
    real `os.environ` via the real `dotenv.load_dotenv()` — not a
    `pydantic-settings` `env_file=` source, which would NOT populate
    `os.environ` and would silently break the documented boto3 credential
    path. Uses a `tmp_path` `.env` file so this is hermetic and does not
    depend on this developer machine's actual `.env` contents."""
    probe_key = "AI_RADAR_TEST_DOTENV_PROBE"
    probe_value = "injected-by-test-tmp-env"
    env_file = tmp_path / ".env"
    env_file.write_text(f"{probe_key}={probe_value}\n")

    monkeypatch.setattr("dotenv.main.find_dotenv", lambda *a, **k: str(env_file))
    monkeypatch.delenv(probe_key, raising=False)
    assert probe_key not in os.environ

    module = importlib.import_module("shared.config")
    importlib.reload(module)
    try:
        assert os.environ.get(probe_key) == probe_value
    finally:
        monkeypatch.undo()
        os.environ.pop(probe_key, None)
        importlib.reload(module)


# --- T2 / T3: the 26-row env-var -> constant table (Gate G3) ---------------


@pytest.mark.parametrize(
    "env_name, attr_name, override, expected, _default",
    SHARED_ENV_CASES,
    ids=[row[0] for row in SHARED_ENV_CASES],
)
def test_shared_config_env_var_sets_its_constant(
    reload_config_module, env_name, attr_name, override, expected, _default
):
    with reload_config_module("shared.config", env={env_name: override}) as module:
        assert getattr(module, attr_name) == expected


@pytest.mark.parametrize(
    "env_name, attr_name, override, expected, _default",
    CURATION_ENV_CASES,
    ids=[row[0] for row in CURATION_ENV_CASES],
)
def test_curation_config_env_var_sets_its_constant(
    reload_config_module, env_name, attr_name, override, expected, _default
):
    with reload_config_module("curation.config", env={env_name: override}) as module:
        assert getattr(module, attr_name) == expected


# --- T4 / T5: all 26 defaults with a clean environment ----------------------


@pytest.mark.parametrize(
    "env_name, attr_name, _override, _expected, default",
    SHARED_ENV_CASES,
    ids=[row[0] for row in SHARED_ENV_CASES],
)
def test_shared_config_default_value(
    reload_config_module, env_name, attr_name, _override, _expected, default
):
    with reload_config_module(
        "shared.config", clear=SHARED_ALL_ENV_NAMES
    ) as module:
        assert getattr(module, attr_name) == default


@pytest.mark.parametrize(
    "env_name, attr_name, _override, _expected, default",
    CURATION_ENV_CASES,
    ids=[row[0] for row in CURATION_ENV_CASES],
)
def test_curation_config_default_value(
    reload_config_module, env_name, attr_name, _override, _expected, default
):
    with reload_config_module(
        "curation.config", clear=CURATION_ALL_ENV_NAMES
    ) as module:
        assert getattr(module, attr_name) == default


def test_shared_config_feeds_has_the_six_documented_entries(reload_config_module):
    with reload_config_module("shared.config") as module:
        assert module.FEEDS == EXPECTED_FEEDS
        assert len(module.FEEDS) == 6


def test_curation_config_default_seeds_has_the_five_documented_seeds(
    reload_config_module,
):
    with reload_config_module("curation.config") as module:
        assert module._DEFAULT_SEEDS == EXPECTED_DEFAULT_SEEDS
        assert len(module._DEFAULT_SEEDS) == 5


# --- T6: the 11 fixed constants are unmoved by a same-named env var --------


@pytest.mark.parametrize("const_name", SHARED_FIXED_CONSTANTS)
def test_shared_config_fixed_constant_unmoved_by_same_named_env_var(
    reload_config_module, const_name
):
    with reload_config_module(
        "shared.config", clear=SHARED_ALL_ENV_NAMES
    ) as baseline:
        expected = getattr(baseline, const_name)

    with reload_config_module(
        "shared.config",
        clear=SHARED_ALL_ENV_NAMES,
        env={const_name: "clobbered-by-test"},
    ) as probed:
        assert getattr(probed, const_name) == expected


@pytest.mark.parametrize("const_name", CURATION_FIXED_CONSTANTS)
def test_curation_config_fixed_constant_unmoved_by_same_named_env_var(
    reload_config_module, const_name
):
    with reload_config_module(
        "curation.config", clear=CURATION_ALL_ENV_NAMES
    ) as baseline:
        expected = getattr(baseline, const_name)

    with reload_config_module(
        "curation.config",
        clear=CURATION_ALL_ENV_NAMES,
        env={const_name: "clobbered-by-test"},
    ) as probed:
        assert getattr(probed, const_name) == expected


# --- T7: derived cache paths track AI_RADAR_CACHE_DIR -----------------------


def test_shared_config_derived_paths_track_cache_dir_override(reload_config_module):
    with reload_config_module(
        "shared.config", env={"AI_RADAR_CACHE_DIR": "/tmp/ai-radar-test-cache"}
    ) as module:
        expected_dir = Path("/tmp/ai-radar-test-cache")
        assert module.CACHE_DIR == expected_dir
        assert module.SEEN_PATH == expected_dir / "seen.json"
        assert module.CARDS_PATH == expected_dir / "cards.json"
        assert module.EMBED_PATH == expected_dir / "embeddings.json"


# --- T8 / T9: list splits, including the empty-string trap ------------------


def test_curation_config_tavily_seeds_semicolon_split_strips_whitespace(
    reload_config_module,
):
    with reload_config_module(
        "curation.config", env={"CURATION_TAVILY_SEEDS": " seed one ; seed two "}
    ) as module:
        assert module.TAVILY_SEEDS == ["seed one", "seed two"]


def test_curation_config_tavily_seeds_empty_override_is_empty_not_defaults(
    reload_config_module,
):
    """The trap contract.md Behavior Guarantee 7 calls out explicitly:
    `CURATION_TAVILY_SEEDS=` must yield `[]`, NOT silently fall back to the
    five default seeds."""
    with reload_config_module(
        "curation.config", env={"CURATION_TAVILY_SEEDS": ""}
    ) as module:
        assert module.TAVILY_SEEDS == []


def test_curation_config_tavily_seeds_unset_falls_back_to_default_seeds(
    reload_config_module,
):
    with reload_config_module(
        "curation.config", clear=["CURATION_TAVILY_SEEDS"]
    ) as module:
        assert module.TAVILY_SEEDS == EXPECTED_DEFAULT_SEEDS


@pytest.mark.parametrize(
    "env_name, attr_name",
    [
        ("CURATION_TAVILY_INCLUDE_DOMAINS", "TAVILY_INCLUDE_DOMAINS"),
        ("CURATION_TAVILY_EXCLUDE_DOMAINS", "TAVILY_EXCLUDE_DOMAINS"),
    ],
)
def test_curation_config_domain_csv_comma_split_strips_whitespace(
    reload_config_module, env_name, attr_name
):
    with reload_config_module(
        "curation.config", env={env_name: " a.com, b.com "}
    ) as module:
        assert getattr(module, attr_name) == ["a.com", "b.com"]


@pytest.mark.parametrize(
    "env_name, attr_name",
    [
        ("CURATION_TAVILY_INCLUDE_DOMAINS", "TAVILY_INCLUDE_DOMAINS"),
        ("CURATION_TAVILY_EXCLUDE_DOMAINS", "TAVILY_EXCLUDE_DOMAINS"),
    ],
)
def test_curation_config_domain_csv_empty_override_is_empty_list(
    reload_config_module, env_name, attr_name
):
    with reload_config_module("curation.config", env={env_name: ""}) as module:
        assert getattr(module, attr_name) == []


@pytest.mark.parametrize(
    "env_name, attr_name",
    [
        ("CURATION_TAVILY_INCLUDE_DOMAINS", "TAVILY_INCLUDE_DOMAINS"),
        ("CURATION_TAVILY_EXCLUDE_DOMAINS", "TAVILY_EXCLUDE_DOMAINS"),
    ],
)
def test_curation_config_domain_csv_unset_is_empty_list(
    reload_config_module, env_name, attr_name
):
    with reload_config_module("curation.config", clear=[env_name]) as module:
        assert getattr(module, attr_name) == []


# --- T10: the other empty-string cases --------------------------------------


def test_curation_config_tavily_api_key_empty_override_is_empty_string(
    reload_config_module,
):
    with reload_config_module("curation.config", env={"TAVILY_API_KEY": ""}) as module:
        assert module.TAVILY_API_KEY == ""


def test_shared_config_cache_dir_empty_override_is_current_directory(
    reload_config_module,
):
    with reload_config_module(
        "shared.config", env={"AI_RADAR_CACHE_DIR": ""}
    ) as module:
        assert module.CACHE_DIR == Path(".")


# --- T11: exact-case env matching (case_sensitive=True) ---------------------


def test_shared_config_lowercase_env_var_name_is_ignored(reload_config_module):
    with reload_config_module(
        "shared.config", clear=["AWS_REGION"], env={"aws_region": "should-be-ignored"}
    ) as module:
        assert module.AWS_REGION == "us-east-1"


def test_curation_config_lowercase_env_var_name_is_ignored(reload_config_module):
    with reload_config_module(
        "curation.config",
        clear=["TAVILY_API_KEY"],
        env={"tavily_api_key": "should-be-ignored"},
    ) as module:
        assert module.TAVILY_API_KEY == ""


# --- T12: constants stay assignable module attributes -----------------------


def test_shared_config_constant_is_assignable_and_reload_restores_default(
    reload_config_module,
):
    """Pins the mutability `runtime_app.py:116` and 16 test sites depend on
    (contract.md State Changes: `config.NAME` stays writable)."""
    with reload_config_module("shared.config") as module:
        original = module.AWS_REGION
        module.AWS_REGION = "mutated-by-test"
        assert module.AWS_REGION == "mutated-by-test"

    with reload_config_module("shared.config") as restored:
        assert restored.AWS_REGION == original


def test_curation_config_tavily_api_key_is_assignable_like_runtime_app_does(
    reload_config_module,
):
    """Mirrors the exact real-world write: `runtime_app._build_discoverer`
    does `curation_config.TAVILY_API_KEY = key` after a Secrets Manager
    lookup."""
    with reload_config_module("curation.config", env={"TAVILY_API_KEY": ""}) as module:
        assert module.TAVILY_API_KEY == ""
        module.TAVILY_API_KEY = "resolved-from-secrets-manager"
        assert module.TAVILY_API_KEY == "resolved-from-secrets-manager"


# --- T16 / T17: the one deliberate behavior change (xfail until Phase 3) ---


def test_curation_emit_metrics_numeric_one_is_true_after_migration(
    reload_config_module,
):
    with reload_config_module(
        "curation.config", env={"CURATION_EMIT_METRICS": "1"}
    ) as module:
        assert module.EMIT_RUN_METRICS is True


def test_curation_emit_metrics_unparseable_value_raises_after_migration(
    reload_config_module,
):
    with pytest.raises(pydantic.ValidationError, match="CURATION_EMIT_METRICS"):
        with reload_config_module(
            "curation.config", env={"CURATION_EMIT_METRICS": "yolo"}
        ):
            pass


# `.env.example`'s `CURATION_EMIT_METRICS` comment promises operators
# `true/false/1/0/yes/no/on/off` (case-insensitive) — pin every one of those
# eight documented spellings, plus a case-variant of each, so that promise is
# actually covered (not just verified by hand — audit.md W2 / T17 PARTIAL).
CURATION_EMIT_METRICS_TRUE_SPELLINGS = [
    "true",
    "True",
    "TRUE",
    "1",
    "yes",
    "Yes",
    "YES",
    "on",
    "On",
    "ON",
]
CURATION_EMIT_METRICS_FALSE_SPELLINGS = [
    "false",
    "False",
    "FALSE",
    "0",
    "no",
    "No",
    "NO",
    "off",
    "Off",
    "OFF",
]


@pytest.mark.parametrize("value", CURATION_EMIT_METRICS_TRUE_SPELLINGS)
def test_curation_emit_metrics_accepts_all_documented_true_spellings(
    reload_config_module, value
):
    with reload_config_module(
        "curation.config", env={"CURATION_EMIT_METRICS": value}
    ) as module:
        assert module.EMIT_RUN_METRICS is True


@pytest.mark.parametrize("value", CURATION_EMIT_METRICS_FALSE_SPELLINGS)
def test_curation_emit_metrics_accepts_all_documented_false_spellings(
    reload_config_module, value
):
    with reload_config_module(
        "curation.config", env={"CURATION_EMIT_METRICS": value}
    ) as module:
        assert module.EMIT_RUN_METRICS is False


# --- Validation-error tests (tasks.md Phase 4) — true RED until both config
# modules are migrated. -------------------------------------------------


def test_shared_config_bad_float_override_raises_validation_error_naming_the_var(
    reload_config_module,
):
    """Today: a bare `ValueError: could not convert string to float: 'abc'`
    from inside `float()`, naming neither the variable nor the fact that
    config was at fault (intent.md problem #1). After migration:
    `pydantic.ValidationError` naming `HAIKU_INPUT_USD_PER_1M`."""
    with pytest.raises(pydantic.ValidationError, match="HAIKU_INPUT_USD_PER_1M"):
        with reload_config_module(
            "shared.config", env={"HAIKU_INPUT_USD_PER_1M": "abc"}
        ):
            pass


def test_curation_config_empty_credit_price_raises_validation_error_naming_the_var(
    reload_config_module,
):
    with pytest.raises(
        pydantic.ValidationError, match="CURATION_TAVILY_CREDIT_PRICE_USD"
    ):
        with reload_config_module(
            "curation.config", env={"CURATION_TAVILY_CREDIT_PRICE_USD": ""}
        ):
            pass


def test_shared_config_bad_int_override_raises_validation_error_naming_the_var(
    reload_config_module,
):
    """`AI_RADAR_MAX_ITEMS` is a `shared/config.py` knob (`MAX_ITEMS`), per
    contract.md's `_SharedSettings.max_items` field — not a `curation/config.py`
    one."""
    with pytest.raises(pydantic.ValidationError, match="AI_RADAR_MAX_ITEMS"):
        with reload_config_module(
            "shared.config", env={"AI_RADAR_MAX_ITEMS": "eight"}
        ):
            pass


def test_multiple_bad_overrides_raise_one_error_naming_both(reload_config_module):
    """contract.md Error Handling Contract: 'Several bad vars at once ->
    **one** ValidationError listing every offending variable' (pydantic
    collects all field errors before raising) — one run of the fix loop
    instead of N."""
    with pytest.raises(pydantic.ValidationError) as exc_info:
        with reload_config_module(
            "shared.config",
            env={"HAIKU_INPUT_USD_PER_1M": "abc", "EMBED_DIM": "not-an-int"},
        ):
            pass

    message = str(exc_info.value)
    assert "HAIKU_INPUT_USD_PER_1M" in message
    assert "EMBED_DIM" in message


def test_validation_error_is_catchable_as_value_error(reload_config_module):
    """contract.md Error Handling Contract: 'A caller with `except ValueError`
    around a config import ... still catches it — `pydantic.ValidationError`
    **is** a `ValueError` subclass.' Asserting `isinstance(..., ValidationError)`
    (not just `except ValueError`) is what keeps this red today: today's bare
    `ValueError` from `float()` already satisfies a plain `except ValueError`,
    so that alone would pass by accident."""
    caught: Exception | None = None
    try:
        with reload_config_module(
            "shared.config", env={"HAIKU_INPUT_USD_PER_1M": "abc"}
        ):
            pass
    except ValueError as exc:
        caught = exc

    assert caught is not None, "a bad override must raise a ValueError (or subclass)"
    assert isinstance(caught, pydantic.ValidationError), (
        "must be pydantic's typed ValidationError, not today's bare ValueError "
        "raised from inside float()"
    )


# --- Dependency-shape test (tasks.md Task 4.4) — true RED until `uv add` ---


def _dependency_names(specs: list[str]) -> set[str]:
    """`"pydantic-settings>=2.14.2"` -> `"pydantic-settings"`."""
    return {re.split(r"[<>=!~\[]", spec)[0].strip() for spec in specs}


def test_pyproject_declares_pydantic_settings_as_a_main_dependency():
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text())
    main_deps = _dependency_names(pyproject["project"]["dependencies"])
    assert "pydantic-settings" in main_deps, (
        "pydantic-settings must be an explicit [project].dependencies entry — "
        "it is only dev-transitive today (via bedrock-agentcore-starter-toolkit), "
        "and Dockerfile runs `uv sync --frozen --no-dev` (intent.md Constraints)"
    )


def test_pydantic_settings_is_not_declared_in_the_dev_dependency_group():
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text())
    dev_deps = _dependency_names(
        pyproject.get("dependency-groups", {}).get("dev", [])
    )
    assert "pydantic-settings" not in dev_deps


# --- Consumer-regression test (tasks.md Task 4.5) ---------------------------


def test_shared_bedrock_from_imported_values_match_config_constants():
    import shared.bedrock as bedrock_module
    import shared.config as config_module

    assert bedrock_module.AWS_REGION == config_module.AWS_REGION
    assert bedrock_module.HAIKU_MODEL_ID == config_module.HAIKU_MODEL_ID


def test_shared_chat_from_imported_values_match_config_constants():
    import shared.chat as chat_module
    import shared.config as config_module

    assert chat_module.SONNET_MODEL_ID == config_module.SONNET_MODEL_ID
    assert chat_module.TOP_K == config_module.TOP_K


def test_shared_retrieval_from_imported_values_match_config_constants():
    import shared.config as config_module
    import shared.retrieval as retrieval_module

    assert retrieval_module.EMBED_DIM == config_module.EMBED_DIM
    assert retrieval_module.EMBED_MODEL_ID == config_module.EMBED_MODEL_ID
    assert retrieval_module.EMBED_PATH == config_module.EMBED_PATH

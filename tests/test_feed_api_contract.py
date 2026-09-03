"""Tests for the feed-api cross-cutting contract: the published JSON Schema
artifact, cross-plane literal drift (AD-4, AD-5), `src/api/config.py`'s
env-overridable settings, and plane separation (AD-3, Guarantee 14).

Spec: specs/feed-api/contract.md AD-3, AD-4, AD-5, "`src/api/config.py` —
CREATE", "`export_api_schema.py` — CREATE"; Behavior Guarantee 13, 14;
specs/feed-api/audit.md T19, T20, T32 (F1).

Mirrors `tests/test_infra_agent_runtime.py::test_infra_and_app_sentinel_
literals_match` (the Tavily-sentinel drift remedy) for the GSI literals and
(2026-09-02, auditor finding F1) for `CARD_SCHEMA_VERSION`, and
`tests/test_dynamo_store.py::test_boto3_import_confined_to_dynamo_module` for
the AST-based import-confinement pattern.

Zero AWS/network.
"""
from __future__ import annotations

import ast
import importlib
import json
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from contracts.card import CARD_SCHEMA_VERSION, json_schema

REPO_ROOT = Path(__file__).parent.parent
SRC = REPO_ROOT / "src"
ARTIFACT_PATH = REPO_ROOT / "docs" / "api" / "feed-api.v1.schema.json"

# infra/ on sys.path so `lib.feed_api` resolves as a flat module, matching
# tests/test_infra_feed_api.py's convention (idempotent if already inserted).
sys.path.insert(0, str(REPO_ROOT / "infra"))


# --- AD-4: cross-plane GSI literal drift ------------------------------------


def test_gsi_literals_match_between_api_config_and_curation_config():
    from api.config import FEED_GSI_NAME, FEED_GSI_PARTITION
    from curation.config import FEED_GSI_NAME as CURATION_GSI_NAME
    from curation.config import FEED_GSI_PARTITION as CURATION_GSI_PARTITION

    assert FEED_GSI_NAME == CURATION_GSI_NAME
    assert FEED_GSI_PARTITION == CURATION_GSI_PARTITION


# --- AD-5: CARD_SCHEMA_VERSION drift guard (auditor finding F1) ------------
#
# AD-5 claims versioning is expressed three ways "all in one place": the
# `CARD_SCHEMA_VERSION` constant, the route prefix (`infra/lib/feed_api.py`'s
# `ROUTE_PATH`), and the artifact filename (`export_api_schema.py`'s
# `OUTPUT_PATH`). In the implementation these are three independently
# hardcoded strings with nothing tying them together — the identical
# duplicated-cross-boundary-literal shape the GSI-literal test above (and the
# Tavily-sentinel precedent, F10) already guards. A `v2` bump could silently
# update one or two of the three, publishing an artifact whose filename
# disagrees with the route.
def test_card_schema_version_is_embedded_in_route_path_and_artifact_filename():
    from lib.feed_api import ROUTE_PATH

    assert ROUTE_PATH.startswith(f"/{CARD_SCHEMA_VERSION}/")
    assert ARTIFACT_PATH.name == f"feed-api.{CARD_SCHEMA_VERSION}.schema.json"


# --- Guarantee 13: committed schema artifact parity -------------------------


def test_committed_schema_artifact_matches_contracts_json_schema():
    """Semantic (parsed-dict) equality, not a raw-byte diff: the export
    script (not this test) owns whitespace/indentation formatting choices
    that haven't been decided yet — what actually matters for Spec 02's
    generated types is that the published document has the same shape, not
    that it has particular whitespace."""
    assert ARTIFACT_PATH.is_file(), (
        f"expected {ARTIFACT_PATH} to exist — run `uv run export_api_schema.py`"
    )
    committed = json.loads(ARTIFACT_PATH.read_text())
    assert committed == json_schema()


# --- `src/api/config.py` — env-overridable settings + fixed constants ------


@pytest.fixture
def reload_api_config(monkeypatch):
    """Minimal reload harness for `api.config` (no dotenv neutralization
    needed: AD-3 means this module never calls `load_dotenv()`)."""

    @contextmanager
    def _reload(env: dict | None = None, clear: list | None = None):
        for key in clear or ():
            monkeypatch.delenv(key, raising=False)
        for key, value in (env or {}).items():
            monkeypatch.setenv(key, value)
        module = importlib.import_module("api.config")
        importlib.reload(module)
        try:
            yield module
        finally:
            monkeypatch.undo()
            importlib.reload(module)

    return _reload


# One representative env-override case per field (all three exercise the
# identical pydantic-settings alias-binding shape, not three different pieces
# of our own logic) rather than three near-duplicate tests.
API_CONFIG_ENV_OVERRIDE_CASES = [
    ("CARD_TABLE_NAME", "custom-cards-table", "CARD_TABLE_NAME", "custom-cards-table"),
    ("FEED_API_DEFAULT_PAGE_SIZE", "10", "DEFAULT_PAGE_SIZE", 10),
    ("FEED_API_MAX_PAGE_SIZE", "50", "MAX_PAGE_SIZE", 50),
]


@pytest.mark.parametrize(
    "env_name, env_value, attr_name, expected",
    API_CONFIG_ENV_OVERRIDE_CASES,
    ids=[row[0] for row in API_CONFIG_ENV_OVERRIDE_CASES],
)
def test_api_config_field_is_env_overridable(
    reload_api_config, env_name, env_value, attr_name, expected
):
    with reload_api_config(env={env_name: env_value}) as module:
        assert getattr(module, attr_name) == expected


def test_api_config_defaults_when_nothing_is_set(reload_api_config):
    """The values actually used in prod when no override is present —
    contract-critical, not boilerplate: `CARD_TABLE_NAME` defaults to the
    real deployed table name, and the page-size bounds default to the
    documented 20/100."""
    with reload_api_config(
        clear=["CARD_TABLE_NAME", "FEED_API_DEFAULT_PAGE_SIZE", "FEED_API_MAX_PAGE_SIZE"]
    ) as module:
        assert module.CARD_TABLE_NAME == "ai-radar-cards"
        assert module.DEFAULT_PAGE_SIZE == 20
        assert module.MAX_PAGE_SIZE == 100


def test_fixed_gsi_constants_are_not_overridable_by_a_same_named_env_var(
    reload_api_config,
):
    with reload_api_config(
        env={"FEED_GSI_NAME": "clobbered", "FEED_GSI_PARTITION": "clobbered"}
    ) as module:
        assert module.FEED_GSI_NAME == "feed-by-score"
        assert module.FEED_GSI_PARTITION == "CARD"


# --- Guarantee 14 / AD-3: plane separation + boto3 confinement (AST) -------


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _py_files(directory: Path) -> list[Path]:
    assert directory.is_dir(), f"expected {directory} to exist"
    return sorted(directory.rglob("*.py"))


def test_api_and_contracts_import_nothing_from_curation():
    for directory in (SRC / "api", SRC / "contracts"):
        for path in _py_files(directory):
            assert "curation" not in _imported_roots(path), (
                f"{path} (Plane B) must not import curation (Plane A)"
            )


def test_curation_and_shared_import_nothing_from_api_or_contracts():
    for directory in (SRC / "curation", SRC / "shared"):
        for path in _py_files(directory):
            roots = _imported_roots(path)
            assert "api" not in roots, f"{path} must not import api (Plane B)"
            assert "contracts" not in roots, f"{path} must not import contracts"


def test_boto3_import_confined_to_api_dynamo_module():
    for directory in (SRC / "api", SRC / "contracts"):
        for path in _py_files(directory):
            if directory.name == "api" and path.name == "dynamo.py":
                continue
            assert "boto3" not in _imported_roots(path), f"{path} must not import boto3"

    dynamo_path = SRC / "api" / "dynamo.py"
    assert dynamo_path.exists(), "expected src/api/dynamo.py to exist"
    assert "boto3" in _imported_roots(dynamo_path), (
        "dynamo.py is the one designated infra-adapter site and must import boto3"
    )


def test_api_config_does_not_import_shared_per_ad3():
    config_path = SRC / "api" / "config.py"
    assert config_path.exists(), "expected src/api/config.py to exist"
    assert "shared" not in _imported_roots(config_path), (
        "AD-3: src/api/config.py must not import shared.config — the Lambda "
        "has no .env and gets AWS_REGION from the runtime, not shared.config's "
        "dotenv side effect"
    )

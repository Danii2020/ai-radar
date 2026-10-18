"""Plane B guards for `src/chat/` (AC8) and the Titan role grant.

Spec: specs/chat-retrieval/intent.md AC8; execution-plan.md § Validation row
AC8; tasks.md O5. Modeled on tests/test_feed_api_contract.py: AST-based
plane-separation and boto3-confinement checks plus the duplicated-constant
equality test (feed-api AD-4 precedent). Zero AWS/network.

RED phase: `src/chat/` does not exist yet.
"""
from __future__ import annotations

import ast
import importlib
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SRC = REPO_ROOT / "src"


def _imported_roots(path: Path) -> set[str]:
    """Absolute-import roots only (relative imports stay inside the package)."""
    tree = ast.parse(path.read_text(), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def _py_files(directory: Path) -> list[Path]:
    assert directory.is_dir(), f"expected {directory} to exist"
    return sorted(directory.rglob("*.py"))


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


# --- plane separation + boto3 confinement (AST) --------------------------------


def test_chat_imports_nothing_from_curation_or_api():
    for path in _py_files(SRC / "chat"):
        roots = _imported_roots(path)
        assert "curation" not in roots, f"{path} (Plane B) must not import curation"
        assert "api" not in roots, f"{path} must not import api"


def test_curation_shared_api_and_contracts_import_nothing_from_chat():
    for directory in ("curation", "shared", "api", "contracts"):
        for path in _py_files(SRC / directory):
            assert "chat" not in _imported_roots(path), (
                f"{path} must not import the Plane B chat package"
            )


def test_boto3_import_confined_to_chat_retriever_module():
    # Weak form: only retriever.py may import boto3 (it need not, e.g. when
    # the resource is injected).
    for path in _py_files(SRC / "chat"):
        if path.name == "retriever.py":
            continue
        assert "boto3" not in _imported_roots(path), f"{path} must not import boto3"



def test_curation_nodes_module_stays_boto3_free():
    nodes_path = SRC / "curation" / "nodes.py"
    assert "boto3" not in _imported_roots(nodes_path)


def test_run_chat_script_imports_nothing_from_curation():
    assert "curation" not in _imported_roots(REPO_ROOT / "run_chat.py"), (
        "run_chat.py (Plane B composition root) must not import curation"
    )


# --- chat-agent-runtime: import confinement and AWS-client-free logic ----------


def _called_attribute_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    return {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }


def test_bedrock_agentcore_is_imported_only_by_files_at_the_repo_root():
    for path in _py_files(SRC):
        assert "bedrock_agentcore" not in _imported_roots(path), (
            f"{path} must not import bedrock_agentcore (composition roots only)"
        )


def test_chat_app_is_a_root_composition_root_that_stays_in_plane_b():
    path = REPO_ROOT / "chat_app.py"
    assert path.is_file(), "chat_app.py must exist at the repo root"

    roots = _imported_roots(path)
    assert "bedrock_agentcore" in roots
    assert "curation" not in roots, "chat_app.py (Plane B) must not import curation"
    assert "api" not in roots, "chat_app.py must not import api"


def test_the_chat_graph_and_request_modules_build_no_aws_client():
    for name in ("graph.py", "request.py"):
        path = SRC / "chat" / name
        assert path.is_file(), f"src/chat/{name} must exist"
        assert "boto3" not in _imported_roots(path)
        assert not {"client", "resource"} & _called_attribute_names(path), (
            f"{path} must not construct an AWS client"
        )
        tree = ast.parse(path.read_text())
        imported_names = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert "bedrock_client" not in imported_names

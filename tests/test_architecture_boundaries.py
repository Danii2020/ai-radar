"""Architecture boundary guards: AST import checks, asserted once for the repo.

Rules (docs/architecture-principles.md): the planes never import each other,
`boto3` / the Tavily SDK / `bedrock_agentcore` live only at their designated
adapter sites, and the portable curation core stays free of AWS imports.
Consolidated from copies that lived in test_chat_contract, test_composite,
test_dynamo_store, test_feed_api_contract, test_graph and test_run_summary.
Zero AWS/network.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SRC = REPO_ROOT / "src"
CURATION = SRC / "curation"


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


def _called_attribute_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    return {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }


def _py_files(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.py"))


def _package_files(*directories: str) -> list[Path]:
    return [path for name in directories for path in _py_files(SRC / name)]


# --- plane separation ---------------------------------------------------------


def test_plane_b_packages_import_nothing_from_curation():
    for path in _package_files("api", "contracts", "chat"):
        assert "curation" not in _imported_roots(path), (
            f"{path} (Plane B) must not import curation (Plane A)"
        )


def test_chat_imports_nothing_from_api():
    for path in _py_files(SRC / "chat"):
        assert "api" not in _imported_roots(path), f"{path} must not import api"


def test_curation_and_shared_import_nothing_from_api_or_contracts():
    for path in _package_files("curation", "shared"):
        roots = _imported_roots(path)
        assert "api" not in roots, f"{path} must not import api (Plane B)"
        assert "contracts" not in roots, f"{path} must not import contracts"


def test_nothing_else_imports_the_chat_package():
    for path in _package_files("curation", "shared", "api", "contracts"):
        assert "chat" not in _imported_roots(path), (
            f"{path} must not import the Plane B chat package"
        )


def test_api_config_does_not_import_shared():
    # AD-3: the Lambda has no .env and gets AWS_REGION from the runtime, not
    # shared.config's dotenv side effect.
    assert "shared" not in _imported_roots(SRC / "api" / "config.py")


def test_run_chat_script_imports_nothing_from_curation():
    assert "curation" not in _imported_roots(REPO_ROOT / "run_chat.py"), (
        "run_chat.py (Plane B composition root) must not import curation"
    )


# --- boto3 confinement --------------------------------------------------------


def test_boto3_is_confined_to_the_adapter_modules():
    # api/ and contracts/: only api/dynamo.py. chat/: only retriever.py (weak
    # form, it need not import it when the resource is injected).
    allowed = {SRC / "api" / "dynamo.py", SRC / "chat" / "retriever.py"}
    for path in _package_files("api", "contracts", "chat"):
        if path in allowed:
            continue
        assert "boto3" not in _imported_roots(path), f"{path} must not import boto3"


def test_the_designated_adapters_do_import_boto3():
    # Guards against a vacuous pass above: these are the one site each.
    for path in (CURATION / "dynamo.py", SRC / "api" / "dynamo.py"):
        assert "boto3" in _imported_roots(path), f"{path.name} is the infra-adapter site"


def test_portable_curation_modules_import_no_aws_sdk_or_agentcore():
    forbidden = {"boto3", "botocore", "bedrock_agentcore"}
    for name in (
        "nodes.py", "graph.py", "state.py", "interfaces.py", "local.py",
        "summary.py", "metrics.py", "composite.py", "config.py",
    ):
        leaked = _imported_roots(CURATION / name) & forbidden
        assert not leaked, f"{name} must not import {leaked}"


def test_chat_graph_and_request_modules_build_no_aws_client():
    for name in ("graph.py", "request.py"):
        path = SRC / "chat" / name
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


# --- bedrock_agentcore and the Tavily SDK -------------------------------------


def test_bedrock_agentcore_is_imported_only_by_files_at_the_repo_root():
    for path in _py_files(SRC):
        assert "bedrock_agentcore" not in _imported_roots(path), (
            f"{path} must not import bedrock_agentcore (composition roots only)"
        )


def test_chat_app_is_a_root_composition_root_that_stays_in_plane_b():
    roots = _imported_roots(REPO_ROOT / "chat_app.py")
    assert "bedrock_agentcore" in roots
    assert "curation" not in roots, "chat_app.py (Plane B) must not import curation"
    assert "api" not in roots, "chat_app.py must not import api"


@pytest.mark.parametrize(
    "name", ["composite.py", "config.py", "nodes.py", "graph.py", "state.py", "interfaces.py", "summary.py"]
)
def test_tavily_sdk_is_not_imported_outside_the_tavily_module(name):
    # summary.py classifies by string prefix precisely so it never imports it.
    assert "tavily" not in _imported_roots(CURATION / name)


def test_tavily_module_is_the_one_place_that_imports_the_sdk_and_not_boto3():
    roots = _imported_roots(CURATION / "tavily.py")
    assert "tavily" in roots
    assert "boto3" not in roots

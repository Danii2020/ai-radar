"""Packaging tests for `Dockerfile.chat_api` (chat-api spec, AC1 and AC6).

Spec: specs/chat-api/execution-plan.md § Validation, row "AC1, AC6 (packaging)".

Guards the silent failure modes a green `cdk deploy` would not surface: an
image that installs more than the `chat_api` group, one that copies another
plane's code into the public edge image, a CMD typo that only fails on the
first invoke, and a locked boto3 that lacks the `bedrock-agentcore` client
(the Lambda base image's built-in boto3 may predate it). No `docker build` is
run: the real build and in-container import are the human-run AC9 step.

RED phase: `Dockerfile.chat_api` does not exist yet, so the Dockerfile tests
fail with "expected ... to exist". The boto3 construction test checks the
already-locked dependency and may pass before the implementation lands.
"""
from __future__ import annotations

from pathlib import Path

import boto3

DOCKERFILE_PATH = Path(__file__).parent.parent / "Dockerfile.chat_api"


def _logical_lines(text: str) -> list[str]:
    """Join `\\`-continued lines into single logical Dockerfile instructions."""
    logical_lines: list[str] = []
    buffer = ""
    for raw_line in text.splitlines():
        stripped = raw_line.rstrip()
        if buffer:
            stripped = buffer + " " + stripped.strip()
            buffer = ""
        if stripped.endswith("\\"):
            buffer = stripped[:-1].rstrip()
            continue
        logical_lines.append(stripped)
    if buffer:
        logical_lines.append(buffer)
    return logical_lines


def _instructions(keyword: str) -> list[str]:
    """Logical lines starting with the instruction keyword, keyword stripped.
    Also the file-existence guard for every test below."""
    assert DOCKERFILE_PATH.is_file(), f"expected {DOCKERFILE_PATH} to exist"
    prefix = f"{keyword} "
    return [
        line[len(prefix):].strip()
        for line in _logical_lines(DOCKERFILE_PATH.read_text())
        if line.strip().startswith(prefix)
    ]


def test_dependencies_are_installed_via_uv_export_with_only_group_chat_api():
    combined = " ".join(_instructions("RUN"))
    assert "uv export" in combined
    assert "--only-group chat_api" in combined, (
        "the image must install ONLY the `chat_api` dependency group"
    )
    assert "--frozen" in combined, "must not silently update uv.lock at build time"


def test_copies_only_the_chat_api_package_into_the_task_root():
    copies = []
    for line in _instructions("COPY"):
        tokens = [t for t in line.split() if not t.startswith("--")]
        copies.append((tokens[:-1], tokens[-1]))

    src_copies = [(srcs, dest) for srcs, dest in copies if any(s.startswith("src/") for s in srcs)]
    assert src_copies == [(["src/chat_api/"], "${LAMBDA_TASK_ROOT}/chat_api/")], (
        "only src/chat_api/ may be copied from src/ (no curation, shared, chat, api, contracts)"
    )


def test_cmd_points_at_the_handler_entrypoint():
    cmd_lines = _instructions("CMD")
    assert cmd_lines == ['["chat_api.handler.handler"]']


def test_locked_boto3_has_the_bedrock_agentcore_client():
    client = boto3.client(
        "bedrock-agentcore",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    assert hasattr(client, "invoke_agent_runtime")

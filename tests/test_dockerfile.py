"""Regression test for the committed root `Dockerfile` (Spec 04:
runtime-packaging).

Spec: specs/runtime-packaging/contract.md "Container - root Dockerfile +
.dockerignore" (AgentCore HTTP contract: port 8080, `/invocations`, `/ping`).

Guards against a real bug an auditor found (F1, 2026-07): `bedrock_agentcore`'s
`BedrockAgentCoreApp.run()` decides its bind host via
`os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER")` - the
`/.dockerenv` check is a Docker-daemon artifact NOT guaranteed to exist inside
an AgentCore microVM. Without `DOCKER_CONTAINER=1` set explicitly in the image,
the server can bind loopback-only (127.0.0.1), so AgentCore's `/ping`/
`/invocations` calls never reach it - the agent deploys successfully but every
real invocation fails. This is a narrow, functional assertion (not a broad
text-diff/change-detector): it parses the Dockerfile's `ENV` instruction(s) -
including backslash line continuations - and asserts `DOCKER_CONTAINER=1` is
one of the declared env vars, so any future edit that drops it fails loudly.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

DOCKERFILE_PATH = Path(__file__).parent.parent / "Dockerfile"


def _env_assignments() -> dict[str, str]:
    """Parse every `ENV key=value ...` instruction in the Dockerfile
    (joining `\\`-continued lines first) into a flat {key: value} dict."""
    text = DOCKERFILE_PATH.read_text()

    # Join backslash line-continuations into single logical lines.
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

    assignments: dict[str, str] = {}
    for line in logical_lines:
        line = line.strip()
        if not line.startswith("ENV "):
            continue
        for token in line[len("ENV "):].split():
            if "=" not in token:
                continue
            key, _, value = token.partition("=")
            assignments[key] = value.strip('"').strip("'")
    return assignments


def test_dockerfile_sets_docker_container_env_for_agentcore_host_binding():
    """F1 regression: without this, BedrockAgentCoreApp.run() may bind
    127.0.0.1 inside the AgentCore microVM and every real invocation fails,
    even though the agent deploys successfully."""
    env = _env_assignments()
    assert env.get("DOCKER_CONTAINER") == "1", (
        "Dockerfile must set ENV DOCKER_CONTAINER=1 so BedrockAgentCoreApp.run() "
        "binds 0.0.0.0 (AgentCore's /.dockerenv fallback check is not reliable "
        "inside the Runtime microVM)"
    )


def _cmd_instruction() -> list[str]:
    """The Dockerfile's exec-form `CMD [...]` as a list."""
    for line in DOCKERFILE_PATH.read_text().splitlines():
        if line.startswith("CMD "):
            return json.loads(line[len("CMD "):])
    raise AssertionError("Dockerfile has no CMD instruction")


def _resolved_command(tmp_path: Path, agent_entrypoint: str | None) -> str:
    """Run the CMD with a stub `python` first on PATH that echoes its arguments,
    so the test sees which entrypoint file the container would start."""
    stub = tmp_path / "python"
    stub.write_text("#!/bin/sh\necho \"$@\"\n")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    env = {"PATH": f"{tmp_path}:{os.environ['PATH']}"}
    if agent_entrypoint is not None:
        env["AGENT_ENTRYPOINT"] = agent_entrypoint
    result = subprocess.run(
        _cmd_instruction(), capture_output=True, text=True, env=env, check=True
    )
    return result.stdout.strip()


def test_cmd_defaults_to_the_curation_entrypoint(tmp_path):
    """chat-agent-runtime AC8: one shared Dockerfile; the curation agent keeps
    working with no setting."""
    assert _resolved_command(tmp_path, None) == "runtime_app.py"


def test_cmd_honors_agent_entrypoint_for_the_chat_agent(tmp_path):
    assert _resolved_command(tmp_path, "chat_app.py") == "chat_app.py"


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


def test_dockerfile_exists():
    assert DOCKERFILE_PATH.is_file(), "root Dockerfile must exist and be committed"


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

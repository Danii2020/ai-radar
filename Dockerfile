# AgentCore Runtime container image (Spec 04: runtime-packaging).
#
# Hand-authored to match what `agentcore configure -e runtime_app.py` would
# generate for a `uv`-managed, `src/`-layout, `package = false` project (no
# requirements.txt), then adapted to `uv sync --frozen --no-dev` per
# specs/runtime-packaging/contract.md. AgentCore Runtime requires ARM64
# (AWS Graviton) — pinned via `--platform`.
#
# Contract: no `pip`/`requirements.txt`; deps resolved only from
# pyproject.toml + uv.lock; no Tavily key / `.env` ever enters the image (the
# key is resolved from Secrets Manager at invocation time by runtime_app.py);
# exposes the AgentCore HTTP contract (port 8080, `/invocations`, `/ping`)
# via `bedrock_agentcore.BedrockAgentCoreApp.run()`.

FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# DOCKER_CONTAINER=1 signals bedrock_agentcore.BedrockAgentCoreApp.run() to
# bind 0.0.0.0 instead of 127.0.0.1. The SDK's own fallback check for this
# (`os.path.exists("/.dockerenv")`) is a Docker-daemon artifact NOT guaranteed
# to exist inside an AgentCore microVM — without this var set explicitly the
# server can bind loopback-only and every `/ping`/`/invocations` call from
# AgentCore would fail to reach it (deploys fine, invokes never work).
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}" \
    DOCKER_CONTAINER=1

# Dependency layer first (better layer caching): pyproject.toml + uv.lock only.
# `--frozen` refuses to update the lockfile; `--no-dev` skips the dev group
# (moto/pytest) and the infra group (aws-cdk-lib) — neither is needed at
# runtime. `bedrock-agentcore` is a MAIN dependency so it lands here.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# App code. `src/` is NOT an installed package (`[tool.uv] package = false`);
# runtime_app.py inserts it onto sys.path itself (same pattern as
# run_curation.py), so it is copied alongside the entrypoint verbatim.
COPY src/ ./src/
COPY runtime_app.py ./

# AgentCore Runtime HTTP contract: BedrockAgentCoreApp.run() serves
# `/invocations` + `/ping` on port 8080.
EXPOSE 8080

CMD ["python", "runtime_app.py"]

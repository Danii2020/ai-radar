# ADR 0017: One root Dockerfile serves both agents, with the entrypoint selected by AGENT_ENTRYPOINT

- **Status**: Accepted
- **Date**: 2026-10-18
- **Feature**: chat-agent-runtime
- **Capability**: runtime-deployment
- **Source**: execution-plan.md § Proposed approach (Decision (Docker)); § Binding constraints (the AgentCore starter toolkit builds the `Dockerfile` at `source_path`); intent.md § AC8 and § Constraints
- **Trigger**: (c) diverges from the intent's "separate Dockerfile" wording, which the plan narrows at its review gate; (a) it chooses between a shared Dockerfile with an entrypoint selector and a second Dockerfile or build directory; (b) every later agent in this repo selects its entrypoint the same way

## Context
The intent asked for the chat agent to ship as its own container image with its own Dockerfile. The AgentCore starter toolkit, however, builds only the `Dockerfile` found at the agent's `source_path`, which is the repo root. It ignores any other Dockerfile name. The build context must also contain `src/`, which both agents import. A second agent therefore cannot have a second Dockerfile in the same source tree, so the separate-Dockerfile wording cannot be met as written.

## Decision
Keep one root `Dockerfile`. Its CMD is `sh -c 'exec python "${AGENT_ENTRYPOINT:-runtime_app.py}"'`. The curation agent runs with no setting, which is unchanged. The chat agent is deployed with `--env AGENT_ENTRYPOINT=chat_app.py`. Each agent still has its own image tag and its own AgentCore Runtime, so the two are separate images in every operational sense. This narrows the intent's "separate Dockerfile" to "one shared Dockerfile, separate image per agent".

## Alternatives considered
| Option | Why not |
|---|---|
| A second source tree or a generated build directory for the chat agent | The build context must contain `src/`, so either option copies or duplicates the source. That adds a second place where the build can drift. |
| A `chat_app.py` / `runtime_app.py` dispatcher file that picks one entrypoint at import time | It merges two composition roots into one file, which breaks the one-entrypoint-per-file boundary this repo keeps. |
| A second Dockerfile with a different name | The toolkit ignores it, so the chat agent would silently build the curation image. |

## Consequences
**Positive**: one Dockerfile, one dependency closure, and one place to change the base image. The curation agent's CMD is unchanged, and `tests/test_dockerfile.py` pins the default.
**Accepted costs**: the chat agent's entrypoint depends on a deploy-time flag. If the flag is missing, the chat agent starts the curation entrypoint. The runbook states the flag in the command itself, and AC10 step 6 would fail visibly (the invoke returns the curation ack). The reviewer accepted this narrowing at the plan gate.

## Follow-ups
- If a third agent appears, or the toolkit ever builds a named Dockerfile, revisit this decision.

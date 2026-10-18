# ADR 0016: The chat agent is one stateless, synchronous request-response entrypoint

- **Status**: Accepted
- **Date**: 2026-10-18
- **Feature**: chat-agent-runtime
- **Capability**: chat-agent
- **Source**: execution-plan.md § Proposed approach (Decision: one stateless entrypoint, `chat_app.py`; Decision: request handling order in the handler); § Ownership (Composition root)
- **Trigger**: (a) it chooses between three named ways to run blocking boto3 work inside an AgentCore Runtime handler; (b) every later agent in this repo inherits this pattern

## Context
AgentCore Runtime invokes a Python handler per request. The curation agent (`runtime_app.py`) is asynchronous: it acks in under a second and runs the pipeline as a background task. That shape exists because EventBridge Scheduler has a roughly 30-second synchronous target timeout, and a blocking handler caused a double fire. The chat agent has a different contract. The caller needs the answer in the same response, and a turn is one question in and one answer out. Its work is blocking boto3 and Bedrock calls, so the choice is how to keep the runtime's `/ping` responsive while those calls run.

## Decision
`chat_app.py` defines a plain synchronous `def handler(payload)` under `@app.entrypoint`. The SDK runs sync handlers in a thread pool, so the blocking calls do not stall `/ping`. The handler parses the request, runs the compiled graph, and builds `{answer, sources}`. It keeps no state across invocations, and it returns `invalid_request` or `upstream_failure` as typed errors.

## Alternatives considered
| Option | Why not |
|---|---|
| `async def` handler that wraps the blocking calls in `asyncio.to_thread` | It works, but it adds machinery for no benefit. The SDK's thread pool already gives the same non-blocking behavior for a sync handler. |
| The curation agent's ack-then-background pattern (`add_async_task`, a single-flight guard) | Chat must return the answer in the response. A background task cannot do that, and the guard only exists to stop a scheduler from double-firing. |

## Consequences
**Positive**: the simplest correct shape for request-response. No single-flight state and no background task to leak or lose. Each invocation is independent, which is what AC2 needs.
**Accepted costs**: a long model call holds the invocation open, and the caller waits for it. Nothing in the chat path is throttled yet (there is no public URL until `chat-api`).

## Follow-ups
- `chat-api` (throttling, public URL) decides how callers reach the agent. This ADR does not decide that.

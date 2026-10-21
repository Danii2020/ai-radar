# ADR 0023: Each chat request gets a fresh agent session id, so the Lambda holds no state

- **Status**: Accepted
- **Date**: 2026-10-21
- **Feature**: chat-api
- **Capability**: chat-api
- **Source**: execution-plan.md § Proposed approach (Decision: the handler calls `invoke_agent_runtime`, `runtimeSessionId` a fresh `uuid4`; rejected: reusing one session id); § Risks (fresh session id forces a cold start); intent.md § AC7
- **Trigger**: (a) two options, a fresh session id per request or one reused or bucketed id; (d) it accepts a known cost, one cold runtime start per call

## Context
The chat agent is stateless (CA-2). The conversation lives only in the request body, so nothing needs to carry over between requests. AgentCore binds a `runtimeSessionId` to one runtime session. Sharing one id across unrelated callers would couple them to the same session.

## Decision
Each request sends a new `uuid4` string as `runtimeSessionId` (36 characters, above the 33-character service minimum). The Lambda stores nothing between requests.

## Alternatives considered
| Option | Why not |
|---|---|
| One session id for all callers | It couples unrelated callers to one runtime session. |
| Bucketed session ids, shared across a group of requests | It is the planned fallback if measured latency is too high. It is not used here, because it adds a grouping rule to the Lambda, and the agent's statelessness is what makes sharing safe. |

## Consequences
**Positive**: no state in the Lambda, and each request gets its own session (tested: two calls give two distinct ids, AC7).
**Accepted costs**: each request pays a cold runtime start. The live O9 step 9 recorded `duration_ms` of 6570 and 3345 for two turns, each with a new session id. That is two samples, not a p95.

## Follow-ups
- If latency proves too high in practice, amend the spec to bucketed session ids, as the plan's risk row states.

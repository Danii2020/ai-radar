# ADR 0024: The agent invoke makes no retries, with a 22 s read timeout under a 28 s Lambda limit

- **Status**: Accepted
- **Date**: 2026-10-21
- **Feature**: chat-api
- **Capability**: chat-api
- **Source**: execution-plan.md § Proposed approach (Decision: the client is built once per container; Revision 2 correction on `total_max_attempts`); § Binding constraints (Lambda and invoke timeouts below about 30 s); § Risks (retry semantics row)
- **Trigger**: (a) three named client settings: default retries, `max_attempts`, `total_max_attempts`; (d) it accepts that a transient upstream error surfaces as a 502 and a slow turn as a 504, with no retry

## Context
Each `InvokeAgentRuntime` call is one paid Sonnet turn. botocore retries read timeouts by default. API Gateway's HTTP integration is capped at about 30 s. Revision 1 set `retries={"max_attempts": 1}`, but in botocore `max_attempts` counts retries, not calls. The audit's socket probe (round 1, F1) showed two hits, so a slow turn was invoked twice and could outlast the 28 s Lambda timeout.

## Decision
The client is built once per container with `Config(connect_timeout=3, read_timeout=22, retries={"total_max_attempts": 1})`, and the Lambda timeout is 28 s. A botocore read timeout maps to 504 `upstream_timeout`. Every other invoke error maps to 502 `upstream_failure`.

## Alternatives considered
| Option | Why not |
|---|---|
| Default botocore retries | A slow turn is retried and paid twice, and the retry can outlast the Lambda timeout. |
| `retries={"max_attempts": 1}` | In botocore this means one retry, so two calls. This was Revision 1 and was corrected after audit round 1 (F1). |
| `total_max_attempts: 1` with a 25 s read timeout | Connect 3 s plus read 25 s equals the 28 s Lambda timeout, so no time is left to write the response and the log record (audit F6). |

## Consequences
**Positive**: one agent invocation per request. The socket probe on the handler's real client config showed one hit and a 504 after 22.07 s, with 3 s of headroom under the 28 s timeout.
**Accepted costs**: a transient upstream error is not retried, so the caller gets a 502 and decides whether to retry (each retry is a new turn). A turn longer than 22 s returns 504, but the agent may still finish and bill it.

## Follow-ups
- Runbook step 10, the agent-side invocation count for one slow request, is not run (open finding F5, LOW). The offline socket probe stands in for it until a natural slow turn occurs.

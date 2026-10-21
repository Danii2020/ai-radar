# ADR 0026: The handler sets its own logger to INFO rather than relying on the runtime's log level

- **Status**: Accepted
- **Date**: 2026-10-21
- **Feature**: chat-api
- **Capability**: chat-api
- **Source**: execution-plan.md § Proposed approach (Decision (Revision 2): the handler module sets its own logger to INFO); § Validation (AC3 and AC7 row, root logger at WARNING)
- **Trigger**: (a) two options, a handler-level `setLevel(INFO)` or `ApplicationLogLevel` with the JSON log format

## Context
The Python Lambda runtime leaves the root logger at WARNING unless a log level is configured. The `chat_api_request` record is logged at INFO, so it could be dropped in CloudWatch. The unit tests did not catch this because they set the level themselves (audit round 1, F2). The construct uses the text log format and sets no `ApplicationLogLevel`.

## Decision
The handler module sets its own logger (`logging.getLogger(__name__)`)) to INFO. The record is then emitted whatever the root level is. The log format and the infrastructure are unchanged.

## Alternatives considered
| Option | Why not |
|---|---|
| `ApplicationLogLevel` with the JSON log format | It changes the log wrapper for every record and needs a deploy before it takes effect. The plan rejected it. |
| Relying on the runtime's root level | It drops the record. This was found in audit round 1 (F2). |

## Consequences
**Positive**: the record survives any root level. A test runs the handler with the root logger at WARNING and a plain handler, and checks that the record arrives. No infrastructure change was needed. The live CloudWatch read after the deploy showed the records arriving at the default log config (audit round 3).
**Accepted costs**: the level lives in module code, so a later refactor could remove it. The test named for the root-WARNING case guards against that.

## Follow-ups
- None.

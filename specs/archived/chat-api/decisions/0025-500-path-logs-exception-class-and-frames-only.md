# ADR 0025: Unexpected errors log the exception class and stack frames, never the message

- **Status**: Accepted
- **Date**: 2026-10-21
- **Feature**: chat-api
- **Capability**: chat-api
- **Source**: execution-plan.md § Proposed approach (Decision: one `chat_api_request` record per request; Revision 2 clarification, human-approved 2026-10-20); intent.md § AC3 and § AC7
- **Trigger**: (a) two options for a 500, a traceback with the exception message or class and frames only; (b) a rule later handlers must obey: caller text must not reach a log through an exception message

## Context
An unexpected exception in the Lambda's own code could echo part of the request body in its message. The 500 record goes to CloudWatch, and AC7 requires that no log record contain the question or history text. AWS error messages carry no caller text, so upstream failures are handled differently.

## Decision
The 500 path (`internal_error`) logs the exception class name and the stack frames (file, line, function). It does not log the exception message or source lines. Upstream AWS errors keep the full `exc_info` under `chat_api_upstream_error`, because those messages carry no caller text.

## Alternatives considered
| Option | Why not |
|---|---|
| Full `logger.exception` traceback on the 500 path | The exception message can carry the request body, which would break AC7. |
| Class name only, with no frames | It loses the location a fix needs. |

## Consequences
**Positive**: the 500 record is text-free by construction. A test renders every record with `logging.Formatter` and asserts that a planted question does not appear.
**Accepted costs**: an operator sees the exception class and frames but not the message, so the message can be recovered only by reproducing the bug.

## Follow-ups
- None.

# ADR 0034: Narrow the `execute-api` guard to the host form

- **Status**: Accepted
- **Date**: 2026-10-24
- **Feature**: web-chat-ui
- **Capability**: web-chat
- **Source**: execution-plan.md § Proposed approach 11
- **Trigger**: (c) it diverges from a previously shipped decision (the T29 guard behind ADR 0002), and (b) it sets the rule for the guard

## Context
`features/feed/conventions.test.ts` T29 forbade the literal `execute-api` anywhere under `features/**` and `app/**`. SigV4 needs `service: 'execute-api'`. The guard's purpose (WEB-R3, ADR 0002) is to keep a real API host out of code.

## Decision
T29 forbids the host form `execute-api\.[a-z0-9-]+\.amazonaws\.com` instead. The `NEXT_PUBLIC_` half is unchanged. A test shows the narrowed pattern still fires on a host literal. `AGENTS.md` WEB-1 states the host-literal wording.

## Alternatives considered
| Option | Why not |
|---|---|
| Build the string from parts | It hides the literal from the guard instead of fixing the guard. |
| Exempt `features/chat/api/` as a folder | A blind spot that grows. |

## Consequences
**Positive**: the guard still catches the thing it exists for, a real API host in code, and the signing service name is allowed.
**Accepted costs**: a bare `execute-api` string elsewhere is no longer flagged. The `AGENTS.md` WEB-1 wording was stale at audit time (F2) and was corrected at ship time.

## Follow-ups
None.

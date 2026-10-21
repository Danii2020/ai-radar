# ADR 0028: The chat route is authorized with AWS SigV4 for one dedicated caller, not by throttling

- **Status**: Accepted
- **Date**: 2026-10-21
- **Feature**: chat-api-auth
- **Capability**: chat-api-auth
- **Source**: execution-plan.md § Proposed approach (the `authorizer=HttpIamAuthorizer()` decision and its rejected alternatives), § Binding constraints (the route uses `AWS_IAM`; the one caller user), § Risks (HTTP API IAM semantics; no resource policy)
- **Trigger**: (c) it supersedes ADR 0027, which made throttling the only abuse guard; (a) it chooses `AWS_IAM` over a Lambda authorizer and a handler-side check; (b) it constrains later callers, which must be an IAM principal with an explicit grant; (d) it accepts that any identity in the account with its own `execute-api:Invoke` grant can also call the route

## Context
The chat route was public, and its only guards were the stage throttle and the budget alert (ADR 0027). Its URL was exposed in public git history. Unauthenticated floods reached the Lambda and spent the account's shared 10-slot concurrency pool (open finding F11 of `chat-api`). The intended caller is the web frontend's server, which can hold and use an access key. The browser never calls the API.

## Decision
`POST /v1/chat` uses `AWS_IAM` authorization. API Gateway checks an AWS SigV4 signature (service `execute-api`, region `us-east-1`) and rejects every request that is not validly signed by a permitted principal with 403, before the integration runs. The one principal the stack grants is the IAM user `ai-radar-chat-api-caller`, whose key is covered by ADR 0030. Throttling stays in place as a second, best-effort layer.

## Alternatives considered
| Option | Why not |
|---|---|
| A Lambda authorizer | It runs in a Lambda, so an unauthenticated flood would still spend the concurrency pool this change must protect (AC2). |
| A check inside the handler | The Lambda is invoked before the check, so the pool is spent. |
| `default_authorizer` on the `HttpApi` | Same effect with one route, but less explicit about which route is authenticated. |
| Keep throttling as the only guard (ADR 0027) | It does not stop unauthorized floods from reaching the Lambda, and the exposed URL stays usable by anyone. |

## Consequences
**Positive**: an unsigned request gets 403 without invoking the Lambda or the agent (live, the `Invocations` metric stayed at 1.0 across the rejected windows). The exposed URL can no longer be used without the key, and no secret ships to a browser.
**Accepted costs**: an HTTP API has no resource policy, so any identity in the account whose own policy allows `execute-api:Invoke` on the route (an administrator, for example) can also call it. The stack grants only the caller user (intent revision 2). The caller key is long-lived (ADR 0030). Routing runs before authorization, so an unsigned request to an unrouted method or path gets 404. A signed unrouted request was not run live (F9, accepted by the human). The expired-signature case was not exercised live; the human accepted `--tamper` as the bad-signature probe. The stage throttle remains best-effort (chat-api F13).

## Follow-ups
- The `apps/web` server-side signing spec, which owns the signing route and its server-only environment.
- Re-run the chat-api F11 closure as a signed burst after the Lambda quota increase. Unsigned floods no longer reach the Lambda.
- Restricting admin callers needs a REST API with a resource policy. That is a later spec.
- Short-lived credentials (for example Vercel OIDC to an IAM role) are a later spec.

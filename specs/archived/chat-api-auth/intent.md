# Intent: Chat API Authentication

Shipped: 2026-10-21

Revision: 2
Approval: Approved revision 2 by Daniel Erazo on 2026-10-21 (revision 1 approved explicitly; revision 2 is a wording precision under his standing approval)

## Outcome
`POST /v1/chat` stops being public. API Gateway requires an AWS SigV4 signature
from one dedicated IAM principal, and rejects every other request with a 403
before the Lambda or the agent runs. The only intended caller is the web
frontend's own server: the browser talks to Next.js, and the Next.js server signs
the call to the chat API with that principal's key. End users have no accounts and
no credential. This replaces the "throttling is the only abuse guard" decision
(ADR 0027), makes the URL that was exposed in public git history harmless, and
keeps unauthorized floods off the account's shared Lambda concurrency pool.

## Acceptance criteria
- **AC1** A correctly signed request works exactly as before. A `POST /v1/chat`
  signed with SigV4 (service `execute-api`, region `us-east-1`) by the dedicated
  caller principal is handled by the same handler, and CAPI-1, CAPI-2 and CAPI-3
  of `chat-api` hold unchanged: same bodies, same 200/400/502/504 mapping, same
  text-free `chat_api_request` record.
  Example: a signed `{"question": "..."}` -> 200 `{"answer": ..., "sources": [...]}`.
- **AC2** Every request that is not validly signed by a permitted principal is
  rejected by API Gateway with 403, and neither the Lambda nor the agent is
  invoked. This covers an unsigned request, a request signed with the key of an
  identity that has no `execute-api:Invoke` permission on the route, and a
  request with a bad or expired signature. A signed request to a method or path
  that is not routed is rejected at routing (404, as `chat-api` CAPI-4 already
  records), also without invoking the Lambda. Limit: an HTTP API has no resource
  policy, so any identity in this account whose own IAM policy allows
  `execute-api:Invoke` on the route, such as an administrator, can also call it;
  the dedicated caller is the only principal this stack grants.
  Example: an unsigned `POST /v1/chat` with a valid body -> 403, and the Lambda
  `Invocations` metric does not move.
- **AC3** The route is the only authenticated surface and browsers are not a
  supported caller. The `POST /v1/chat` route uses the `AWS_IAM` authorization
  type, there is still exactly one route, and the CORS configuration and the
  `chat_api_allowed_origins` deploy option are removed, because the caller is a
  server and not a browser.
  Example: a cross-origin browser request is not answered with any
  `access-control-*` header, and no allowed-origin knob remains in the stack.
- **AC4** The caller is one least-privilege IAM user created by the stack, with
  no stored secret. The stack creates an IAM user whose only permission is
  `execute-api:Invoke` on this API's `POST /v1/chat` route (no wildcard resource,
  no other action, no managed policy, no console password). The stack creates no
  access key, so no secret appears in CloudFormation, the repository or logs. The
  human creates the access key with the AWS CLI and places it only in the
  frontend's server-side environment.
  Example: the synthesized template contains one `AWS::IAM::User` with one inline
  policy and no `AWS::IAM::AccessKey`.
- **AC5** Nothing about the caller is logged and nothing else changes. The
  `chat_api_request` record keeps exactly its current keys (no principal ARN, no
  access key id, no signature material). The Lambda's own role, the stage
  throttle (5 rps, burst 10), the 28 s timeout, the reserved-concurrency option
  and the agent contract are unchanged.
  Example: a record from a signed request has the same key set as before.
- **AC6** (compatibility) The existing API is updated in place and nothing else
  moves. The API id and URL do not change, `AiRadarFeedApi`, `AiRadarChatRuntime`
  and the other stacks are not modified, and `uv run pytest tests/` stays green,
  with only the tests that asserted the removed CORS behavior changed.
- **AC7** (live verification, human-run) After deploy: an unsigned request gets 403
  with zero Lambda invocations; the same request against the URL that was
  exposed earlier also gets 403; a request signed with the caller's key gets a
  grounded answer; a request signed with another IAM identity gets 403. The
  runbook and its recorded results are part of the deliverable, including how to
  create, store and rotate the caller's access key.

## Scope
**In**
- `AWS_IAM` authorization on the chat route, removal of CORS and its deploy option.
- The caller IAM user (policy only) in `infra/lib/chat_api.py`, with a stack output
  for its name.
- Tests for the synthesized template; a small signing helper script for the
  live check (a developer tool, not production code); the README runbook, including
  key creation and rotation; an ADR superseding 0027.

**Out**
- The web side: the Next.js server route that signs and forwards the call, the
  server-only environment variables, and the chat UI. They belong to the web chat
  UI spec in `apps/web/`.
- Replacing the API or its URL. Under IAM auth the exposed URL can no longer be
  used without the key.
- Short-lived credentials (for example Vercel OIDC to an IAM role), WAF, per-user
  quotas and end-user accounts. They are possible later specs.
- Any change to the handler's request or response behavior.

## Constraints
- The caller's access key is a long-lived secret. It is created by hand, lives only
  in the frontend's server environment (never a `NEXT_PUBLIC_` variable, never the
  repository, never CloudFormation), and the runbook must document rotating it.
- API Gateway rejects unauthenticated requests before integration, so the
  Lambda concurrency pool is not consumed by them. This is the reason for
  choosing `AWS_IAM` over a Lambda authorizer or a handler-side check.
- The pinned account and region literals and the `chat_api_reserved_concurrency`
  option stay as they are.
- Removing CORS is a breaking change for any direct browser caller. There is none
  today (the web chat UI does not exist yet).
- This spec supersedes ADR 0027 and amends `chat-api` CAPI-4 (the CORS requirement)
  and CAPI-6 (the role is unchanged, but the caller principal is new).
- Throttling stays best-effort (open finding F13). Authentication is the real
  guard; the stage throttle remains a second layer.

## Open questions
- None. Defaults taken: the caller user is named `ai-radar-chat-api-caller`; the
  signing helper is a small Python script using `botocore`, run by the human.

## Revision history
- Revision 2 (2026-10-21): AC2 made precise after the plan's research: unrouted
  method/path is 404 at routing (no Lambda invocation), and identities in the
  account that are separately granted `execute-api:Invoke` (for example an
  administrator) can also call the route. No scope change. Approved under the
  human's standing approval of 2026-10-21 ('i approve everything, auto approve it').
- Revision 1 (2026-10-21): initial draft.

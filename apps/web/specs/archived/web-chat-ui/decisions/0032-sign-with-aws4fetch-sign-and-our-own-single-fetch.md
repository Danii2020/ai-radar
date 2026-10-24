# ADR 0032: Sign chat requests with aws4fetch `sign()` and our own single `fetch`

- **Status**: Accepted
- **Date**: 2026-10-24
- **Feature**: web-chat-ui
- **Capability**: web-chat
- **Source**: execution-plan.md § Proposed approach 1
- **Trigger**: (a) a choice between named viable options, and (b) it constrains future features (the "never `AwsClient.fetch()`" rule)

## Context
`POST /v1/chat` requires AWS SigV4 (`AWS_IAM`, service `execute-api`, region `us-east-1`; `chat-api-auth`). The Next.js route is the only caller, so it must sign. The handoff suggested `@smithy/signature-v4` with `@aws-crypto/sha256-js`. Each turn must reach the agent exactly once (CAPI-3, ADR 0024), and a library-level retry would run the agent twice.

## Decision
Use `aws4fetch` (exact pin, 1.0.20) through `AwsClient.sign()` only, constructed with `retries: 0`, and make the one backend call with our own `fetch` and an abort signal. The app never calls `AwsClient.fetch()`. The signing call is isolated in `features/chat/api/backend.ts`.

## Alternatives considered
| Option | Why not |
|---|---|
| `@smithy/signature-v4` plus `@aws-crypto/sha256-js` | Its own README says it is internal to generated SDK clients and not meant for standalone use; it needs two packages and a hand-built `HttpRequest` converted back to `fetch`. |
| `aws4fetch` `AwsClient.fetch()` | It retries by default (`retries` defaults to 10 with backoff), which would re-run the agent. |

## Consequences
**Positive**: zero dependencies and about 6 KB on Node's built-in Web Crypto; `sign()` returns a plain `Request`, so the single-call, abort and no-retry rules stay in our code; a swap touches one file.
**Accepted costs**: one more runtime dependency (see ADR 0037 for the dependency rule); the pin is about 14 months old, which the audit accepted as at least two weeks old.

## Follow-ups
None.

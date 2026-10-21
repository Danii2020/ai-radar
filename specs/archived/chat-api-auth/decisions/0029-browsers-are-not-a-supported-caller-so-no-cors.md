# ADR 0029: Browsers are not a supported caller, so the chat API has no CORS configuration

- **Status**: Accepted
- **Date**: 2026-10-21
- **Feature**: chat-api-auth
- **Capability**: chat-api-auth
- **Source**: execution-plan.md § Binding constraints (the `AWS::ApiGatewayV2::Api` has no `CorsConfiguration`; the origins knob is removed), § Proposed approach (drop `cors_preflight` from the `HttpApi`), § Risks ("Removing CORS breaks a hypothetical browser caller")
- **Trigger**: (c) it diverges from the shipped `chat-api` requirement CAPI-4, which allowed an explicit CORS origin list; (b) it constrains later specs: a browser must not call the API directly, so a browser UI calls through its own server

## Context
The intent names the caller as a server. A browser cannot hold the caller's key, because the key must never be a `NEXT_PUBLIC_` variable or sit in client code. A CORS allowlist would let a browser send requests that the gateway then rejects with 403 without a signature, so it gives no working browser path. No browser caller existed when this was decided, because the web chat UI is not built.

## Decision
The HTTP API has no CORS configuration. The `chat_api_allowed_origins` deploy option, its default origin list and the `ChatApiAllowedOrigins` output are removed. A cross-origin request gets no `access-control-*` header. Browsers are not a supported caller.

## Alternatives considered
| Option | Why not |
|---|---|
| Keep the CORS allowlist next to `AWS_IAM` | A browser cannot sign with the caller key, so an allowed origin still gets 403. The allowlist would suggest a browser design that the intent rules out. |
| Keep the allowlist for `http://localhost:3000` for development | No development browser caller exists. The web UI calls from its server. |

## Consequences
**Positive**: a smaller surface, with one configuration option fewer and no origin list to maintain.
**Accepted costs**: a future browser client cannot call the API directly and must go through a server route. Removing CORS is a breaking change for any direct browser caller, and none existed.

## Follow-ups
- The `apps/web` server route is the only intended caller. Its design is a later spec in `apps/web/`.
- The CAPI-4 CORS clause is retired in `specs/current/chat-api.md`.

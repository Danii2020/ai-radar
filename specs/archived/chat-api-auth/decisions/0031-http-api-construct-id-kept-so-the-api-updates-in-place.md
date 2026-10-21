# ADR 0031: The HTTP API construct keeps its logical id, so the deploy updates the API in place

- **Status**: Accepted
- **Date**: 2026-10-21
- **Feature**: chat-api-auth
- **Capability**: chat-api-auth
- **Source**: execution-plan.md § Binding constraints (the `HttpApi` construct keeps its logical id), § Proposed approach (add the authorizer to the existing `add_routes` call and drop `cors_preflight`, with the same constructs and logical ids), § Risks ("A changed logical id would replace the API and change its URL")
- **Trigger**: (b) it constrains later changes: renaming the construct id replaces the API, which changes its id and URL

## Context
The exposed URL must not change, and the API id must not change (intent AC6). Under CloudFormation, a changed logical id creates a new resource and deletes the old one, so the id and the URL change with it.

## Decision
The chat API stack keeps the `ChatHttpApi` construct id. It synthesizes to the logical id `ChatApiChatHttpApi975E960D`, and a test (`test_http_api_logical_id_is_stable`) pins it. The `AWS_IAM` authorizer is added to the existing route in the existing `add_routes` call. The caller user is added as a new construct, and the CORS configuration is dropped from the existing `HttpApi`.

## Alternatives considered
| Option | Why not |
|---|---|
| A new `HttpApi` with a new construct id | It replaces the API and changes its id and URL, against AC6. |
| `default_authorizer` on the `HttpApi` | The same effect with one route, but less explicit about which route is authenticated. Not chosen. |

## Consequences
**Positive**: the deploy updates the API in place. Live, the API's `CreatedDate` predates the stack update, and the URL is unchanged.
**Accepted costs**: the logical id is now a constraint. A rename would replace the API and change its URL, and only the `cdk diff` review before each deploy would catch it.

## Follow-ups
- Keep the `cdk diff` review step in the README runbook before each deploy of `AiRadarChatApi`.

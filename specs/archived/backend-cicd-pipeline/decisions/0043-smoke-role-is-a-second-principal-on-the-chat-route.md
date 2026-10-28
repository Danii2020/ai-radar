# ADR 0043: A dedicated CI smoke role becomes a second principal on the chat route, amending ADR 0028

- **Status**: Accepted
- **Date**: 2026-10-28
- **Feature**: backend-cicd-pipeline
- **Capability**: chat-api-auth
- **Source**: execution-plan.md § Proposed approach (Decision (smoke, ADR candidate 0043)); § Binding constraints (the second route principal, accepted by the human as Q4; the contradiction with `chat-api-auth` CAAUTH-5 and ADR 0028); intent.md § AC7, AC8 and § Constraints (the stated contradiction, accepted 2026-10-27)
- **Trigger**: (c) it diverges from ADR 0028, which authorized the route "for one dedicated caller"; (d) it accepts that the set of principals allowed to call the route grows from one to two; (b) later callers must be IAM principals with an explicit `execute-api:Invoke` grant

## Context
ADR 0028 authorizes `POST /v1/chat` with `AWS_IAM` for one caller, `ai-radar-chat-api-caller`. The post-deploy smoke (AC7) must run one signed chat request after every deploy that changed anything, so that a broken chat agent (for example one deployed without `AGENT_ENTRYPOINT=chat_app.py`, RD-8) fails the run. Signing needs an IAM identity. The caller key is long-lived and must not enter GitHub (ADR 0030, and human decision 1).

## Decision
The CI smoke role is a second principal on the route. It lives in the CI access app, outside `AiRadarChatApi`. It trusts only `main` through OIDC, and its only route permission is `execute-api:Invoke` on the `POST /v1/chat` ARN. The smoke runner signs one request with the existing signing helper (`run_chat_api_smoke.py`). The stack's own grant to the caller user (CAAUTH-5) is unchanged. ADR 0028 is not superseded: its rule that the stack grants only the caller user still holds.

## Alternatives considered
| Option | Why not |
|---|---|
| Store the caller's access key in GitHub | Human decision 1 and ADR 0030: the key stays in the web server's environment only. |
| Smoke by invoking the curation agent | It writes cards and spends Haiku and Tavily credits. |
| Probe unsigned only | An unsigned 403 does not show that the chat agent answers, so an RD-8 failure would pass. |
| Signed probe run by the deploy role | Rejected by AC8: the smoke role must be separate from the deploy role, and the deploy role has no `execute-api:Invoke`. |

## Consequences
**Positive**: the smoke needs no stored secret. It proves the chat route and the agent end to end after each deploy. The deploy role has no route permission (asserted offline; the live 403 check is tasks O12 f).
**Accepted costs**: an HTTP API has no resource policy, so the number of principals that can call the route grows from one to two (recorded as CAAUTH-SMOKE). Any identity in the account whose own policy allows the route can still call it (CAAUTH-ADMIN, unchanged). Each deploying run spends one Titan embed and at most one Sonnet 4.6 turn. A no-context answer makes no Sonnet call (ADR 0018).

## Follow-ups
- Confirm on the first live run that the smoke role gets 200 and the deploy role gets 403 on a signed `POST /v1/chat` (tasks O12 f, not yet run).
- Restricting who may call the route at all needs a REST API with a resource policy, a later spec (ADR 0028 follow-up, unchanged).

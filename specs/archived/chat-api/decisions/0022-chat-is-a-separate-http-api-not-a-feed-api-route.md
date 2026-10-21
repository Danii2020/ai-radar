# ADR 0022: Chat is exposed as its own HTTP API, not as a route on the feed API

- **Status**: Accepted
- **Date**: 2026-10-21
- **Feature**: chat-api
- **Capability**: chat-api
- **Source**: execution-plan.md § Proposed approach (Decision: one Lambda, one route, `POST /v1/chat`); intent.md § Open questions (separate API confirmed)
- **Trigger**: (a) two named options, a route on `AiRadarFeedApi` or a separate API; (b) the choice constrains the feed API, whose contract (FA-4) and existing routes must not change

## Context
The public chat endpoint needs an HTTP front door in front of the `ai_radar_chat` agent. The feed API already serves `GET /v1/cards` through its own API Gateway HTTP API and Lambda, with a CORS policy, stage throttle and reserved concurrency tuned for a cheap read. Each chat call spends Sonnet tokens, so it needs a much lower throttle and its own concurrency setting.

## Decision
The chat endpoint is a separate `HttpApi` in the new stack `AiRadarChatApi`. It has its own Lambda, one route (`POST /v1/chat`) and its own stage throttle (5 req/s, burst 10). `AiRadarFeedApi` is not modified.

## Alternatives considered
| Option | Why not |
|---|---|
| Add `POST /v1/chat` as a route on `AiRadarFeedApi` | It changes the feed API's contract (FA-4) and shares its stage throttle (20/40), which is far above what a Sonnet call can afford. It also modifies a stack that AC8 keeps unchanged. The human confirmed a separate API. |

## Consequences
**Positive**: the feed API keeps its contract and throttle, and the chat stack can change or be torn down without touching it. The chat throttle can sit well below the feed's.
**Accepted costs**: one more API Gateway API and Lambda to run and watch. Both functions are unreserved for now, so they draw from one account concurrency pool (open reservation F11).

## Follow-ups
- Restore reserved concurrency on both APIs once the account Lambda quota is raised (F11).

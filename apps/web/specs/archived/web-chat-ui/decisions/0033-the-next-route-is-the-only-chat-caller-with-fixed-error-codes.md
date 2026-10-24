# ADR 0033: The Next.js route is the only chat caller, and it answers with six fixed error codes

- **Status**: Accepted
- **Date**: 2026-10-24
- **Feature**: web-chat-ui
- **Capability**: web-chat
- **Source**: execution-plan.md § Proposed approach 4, 5 and 6
- **Trigger**: (b) it constrains future features (a rule others must obey)

## Context
The chat API has no CORS by design (ADR 0029), and the caller key is long-lived (ADR 0030). The browser must never see the key, the signature, the backend URL, or backend detail. Backend statuses (400, 403, 429, 502, 504, other 5xx) are too many and too revealing to forward.

## Decision
The browser calls only same-origin `POST /api/chat` (`app/api/chat/route.ts`, Node.js runtime, a thin delegate to `handleChatRequest`). The route validates and trims locally, reads `CHAT_API_*` per request, makes one signed backend call, and maps every outcome to a fixed body `{"error": code}` with codes `invalid_request` (400), `busy` (429), `timeout` (504), `upstream_failure` (502), `unavailable` (503, for 403, other backend 5xx and missing or blank configuration) and `internal_error` (500). The backend's `detail` is never forwarded. History is validated (alternating roles starting with `user`, even length) and trimmed to the last 20 items with each text cut to 4000 characters in the route only; the client never trims. One text-free JSON log line carries the outcome and duration.

## Alternatives considered
| Option | Why not |
|---|---|
| Browser calls the chat API directly | Needs CORS and a browser-held key, both ruled out by ADR 0029 and ADR 0030. |
| Forward backend status and `detail` | Leaks backend internals and an unauthorized state a visitor cannot act on. |
| Trim history in the client | Two places would own the cap; the route is the trust boundary. |

## Consequences
**Positive**: the key, URL and backend text cannot reach the browser; the panel has one generic message per code; a rotated key shows up in logs as an internal outcome without telling the visitor.
**Accepted costs**: 403 and missing configuration share `unavailable`, so a visitor cannot tell them apart. Audit findings left open at ship time: a blank history text still reaches the backend (F1), length is counted in UTF-16 units rather than code points (F3), an abort while the body is read maps to `upstream_failure` (F4), and the body cap is checked after reading when there is no `Content-Length` (F5).

## Follow-ups
None. The findings above are recorded as reservations on the `web-chat` capability.

# Handoff: `web-chat-ui` (Phase 3, last piece)

Written 2026-10-21 from a repo-root session, for the `apps/web` harness session that
drafts and builds this spec. This is shared context, not a spec: `intent.md`,
`execution-plan.md` and `tasks.md` in `specs/web-chat-ui/` stay the source of truth once
they exist. Delete or fold this file into them when the spec ships.

## Task

Add the web chat UI to `apps/web`: a server-side route that SigV4-signs calls to the
backend chat API, plus a chat UI. The root spec `chat-api-auth` explicitly leaves
"the server-side signing route and its server-only environment" to this spec.

## Backend contract (deployed, account 626259825216, us-east-1)

- `POST {CHAT_API_BASE_URL}/v1/chat`, API Gateway HTTP API, route auth `AWS_IAM`.
  Sign with SigV4, service `execute-api`, region `us-east-1`. Unsigned calls get 403.
- Request: `{"question": str, "history": [...]}`. The agent is stateless, so the client
  keeps `history` and resends it. Check `src/chat/request.py` for the exact history item
  shape before typing it.
- Success (200): `{"answer": str, "sources": [...]}`. Sources are card references;
  check `src/chat/` and `src/contracts/` for fields.
- Errors: 400 `{"error":"invalid_request","detail"}`, 502 `{"error":"upstream_failure"}`,
  504 `{"error":"upstream_timeout"}`, 500 `{"error":"internal_error"}`, 403 (bad or
  missing signature), 429 (throttled: 5 req/s, burst 10).
- Caps (defaults, env-overridable on the backend): question 1000 chars, history 10 turns
  (20 items), 4000 chars per history item, body 512 KiB at the edge. Mirror the first
  three in the UI and route so users get early feedback; the backend stays authoritative.
- Latency: the Lambda read timeout is 22 s, so the UI needs a loading state and a
  timeout path. Only one latency sample exists (see README "Phase 3").
- No CORS on the API, by design. Browsers must never call it; only the Next.js server does.

## Credentials

- IAM user `ai-radar-chat-api-caller`, one `execute-api:Invoke` grant on `POST /v1/chat`.
- A long-lived access key exists, created by the human on 2026-10-21 and `Active` in the
  local AWS profile `ai-radar-chat-caller`. It must live only in server env
  (`.env.local` locally, Vercel Project Settings in production). Never `NEXT_PUBLIC_`,
  never in the repo, never pasted in chat or logs.
- Suggested env names (confirm in the spec): `CHAT_API_BASE_URL`, `CHAT_API_ACCESS_KEY_ID`,
  `CHAT_API_SECRET_ACCESS_KEY`. Do not use `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`
  names on Vercel; they are reserved there. Add placeholders to `.env.example` only.
- Rotation and leak runbook: root `README.md`, "Authentication amendment
  (`chat-api-auth`)". Residual risks CAAUTH-KEY and CAAUTH-ADMIN are accepted.
- Do not run `aws` commands that print the secret. Reading the key from the profile for
  local setup is the human's step.

## Frontend constraints already in force

- Existing pattern (web-feed AD-4): fetches are server-side, base URLs are server-only
  env, no `NEXT_PUBLIC_`. Follow `features/feed/` layout and its barrel convention.
- Read `specs/current/web-feed.md` and the root `specs/current/chat-api.md`,
  `chat-api-auth.md`, `chat-agent.md` before drafting (harny-sync lookup).
- Next free ADR number: check `specs/current/_index.md` at the repo root (used through
  0031 as of 2026-10-21; numbering is shared across both harness roots).
- Run the route handler on the Node.js runtime (not Edge) if the signing library needs it.
- Stop hook runs eslint + tsc; tests are vitest (unit/component) and Playwright (e2e).
  e2e must mock the chat route; it must not hit the real API or need real credentials.

## Open decisions for the architect

1. Signing library. Recommendation: `@smithy/signature-v4` + `@aws-crypto/sha256-js`
   (AWS-maintained, small). Alternative: `aws4fetch`. Confirm with current docs
   (Context7 failed to connect in the originating session).
2. Where the chat lives: a `/chat` page or a panel on the feed page.
3. Streaming is out of scope: the API returns one JSON body.
4. Abuse guard on the Next.js route (the only public entry now). The API throttle is
   global, so one visitor can starve the rest. Decide whether a per-IP limit is in
   scope or an accepted reservation.
5. Whether `history` is trimmed client-side or by the route when it exceeds the cap.

## Not in scope

- Any backend change (infra, Lambda, agent). If the contract needs to change, stop and
  raise it for a root-harness spec.
- Vercel deploy and `feed-api`-style CORS steps are human-only Phase 5 work.

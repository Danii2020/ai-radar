# Intent: Web Chat UI

Revision: 2
Approval: Approved revision 2 by Daniel Erazo on 2026-10-22
Shipped: 2026-10-24

## Outcome
Visitors to the AI Radar feed page get a floating chat button. Opening it shows a chat panel
where they can ask questions about the curated cards and read grounded answers with numbered
source links. The browser only ever talks to the Next.js server; the server signs each turn with
AWS SigV4 and relays it to the deployed `POST /v1/chat` API, so the long-lived caller key never
reaches the browser. This is the last piece of Phase 3 and the first consumer of `chat-api-auth`.

## Acceptance criteria
- **AC1** The feed page shows a floating chat button, and the panel is closed on first load. The
  button toggles the panel open and closed. The panel is a labelled dialog: Escape closes it, and
  the button has an accessible name that reflects open or closed.
  Example: load `/` -> button visible, no panel; click it -> panel with an input and a send control.
- **AC2** Sending a question shows the user's message, a visible loading state while the turn is
  in flight, and then the assistant's answer. Each source the backend returns appears as a numbered
  link (`[n]`, title, source name) that opens the source `url`, so the answer's `[1]`, `[2]` citations
  can be followed. A reply with an empty `sources` list renders the answer without a source list.
  Example: "What is new in agent frameworks?" -> answer text citing `[1]`, plus source links 1 to N.
- **AC3** The conversation is multi-turn. The client keeps the history and resends it with each
  question. The route forwards at most the last 10 turns (20 items), always as a list that
  alternates `user`/`assistant`, starts with `user`, and ends with `assistant`, and cuts any item
  longer than 4000 characters to that length. A history the route has trimmed this way is never
  rejected by the backend for a history rule.
  Example: 12 completed turns plus a new question -> the route sends turns 3 to 12 and the question.
- **AC4** The question is capped at 1000 characters. The UI stops an over-long or blank question
  before sending and says why, and the route also returns 400 for one without calling the backend.
  The backend stays authoritative for every rule.
  Example: a 1001-character question -> inline message, no request sent; a direct `POST` to the
  route -> 400 `{"error":"invalid_request"}`, and the backend is not called.
- **AC5** Every failure has its own readable state in the panel, with generic copy that leaks no
  status code, URL, header or stack trace, and a way to retry: throttled (backend 429), timeout
  (backend 504, or no reply within the route's own deadline), upstream failure (502), rejected or
  unauthorized (backend 400 or 403), server error (500), unreachable backend, and missing server
  configuration. The conversation so far is kept after an error. Each failure writes one
  structured JSON log line on the server with the outcome and duration, and never the question,
  the history, the answer or any credential.
  Example: backend returns 429 -> panel shows a "busy, try again shortly" message and the input
  keeps the question.
- **AC6** The route signs with SigV4 (service `execute-api`, region `us-east-1`) using the caller key
  from server-only environment variables, calls only `POST {base}/v1/chat`, runs on the Node.js
  runtime, and waits no longer than a fixed deadline that is longer than the backend's 22 s read
  timeout. The key, its secret, the signature and the base URL are never sent to the browser, never
  logged, never in an error body, and never in a `NEXT_PUBLIC_` variable. `.env.example` carries
  placeholders only.
  Example: the browser network tab shows one same-origin `POST` to the route and no request to
  `execute-api`.
- **AC7** (compatibility) The feed behaves exactly as before: the four render states, tag filter,
  cursor pagination and the existing server-side `feed-api` fetch rules (WEB-1 to WEB-7) are
  unchanged, and the existing unit, component and e2e tests keep passing. The committed e2e
  baselines (`e2e/__baseline__`: the `FeedView` DOM, computed styles, browser console and server
  stderr for 17 scenarios) stay byte-identical and are never regenerated. The chat widget sits
  outside the `FeedView` root and writes nothing to the browser console.
- **AC8** (compatibility) The chat styling uses the existing design tokens and adds no hand-authored
  colour, spacing or radius value outside the verbatim token file (WEB-9), and it follows the OS
  light and dark preference with no toggle (WEB-8).
- **AC9** The e2e tier covers open, ask, answer with sources, and at least one error state, against a
  local stub of the chat API with no real credentials and no network call to AWS. The route's
  signing is covered by a unit test that checks the signed headers without the real key.
  Example: `npm run test:e2e` offline -> open the panel, send a question, see the stubbed answer.

## Scope
**In**
- A `features/chat/` feature (components, a client-side conversation state, a server-only chat
  client with the signing, the route's request validation and trimming), behind its own barrel.
- A Node.js route handler, `POST /api/chat`, in `app/api/chat/`.
- Mounting the floating button on the feed page only.
- Server-only env `CHAT_API_BASE_URL`, `CHAT_API_ACCESS_KEY_ID`, `CHAT_API_SECRET_ACCESS_KEY`,
  as placeholders in `.env.example`.
- One new runtime dependency for SigV4 signing (the library is chosen in the execution plan).
- Unit, component and Playwright tests for the above, and README notes for local setup.

**Out**
- Any backend change (infra, Lambda, agent, contract). A contract change goes to the root harness.
- A `/chat` page, streaming, persisted conversations, accounts and chat analytics.
- A per-IP or per-session limit on the route. The API's global throttle (5 req/s, burst 10) is the
  only limit, so one visitor can use up the quota for the rest. This is an accepted reservation for
  v1 and is recorded in the plan.
- The Vercel project, its environment variables, and key rotation. These are human-run Phase 5
  steps (WEB-11), and nothing here deploys or creates credentials.
- Reading the key from the AWS profile or running any `aws` command that prints the secret.

## Constraints
- Stack: Next.js 16 App Router, React 19, TypeScript strict, CSS Modules, npm only (WEB-10).
- The backend contract is frozen from this side: request `{question, history: [{role, text}]}`,
  response `{answer, sources: [{n, title, url, source, published, score}]}`, with the error
  bodies and status codes in `chat-api` CAPI-1 to CAPI-3. There is no CORS, so only the server
  calls the API (CAAUTH-4, ADR 0029).
- Caps mirror the backend defaults: question 1000 characters, 10 turns, 4000 characters per item.
  The backend stays authoritative if its caps change.
- The caller key is long-lived and lives only in server environment (`.env.local` locally, Vercel
  project settings in production). Do not use the names `AWS_ACCESS_KEY_ID` or
  `AWS_SECRET_ACCESS_KEY`, which Vercel reserves. Rotation and the leak response are in the root
  README (CAAUTH-6, ADR 0030). Residual risks CAAUTH-KEY and CAAUTH-ADMIN stay accepted.
- Follow the `features/feed/` layout: split by role, one public barrel, tests next to their source,
  and architecture guards in a conventions test.
- This spec amends two statements in `web-feed`, on purpose:
  - Invariant 3 says `app/page.tsx` imports only `@/features/feed`. It will also import
    `@/features/chat` to mount the button, so the shell stays thin but has two imports.
  - `AGENTS.md` names `@playwright/test` as the only sanctioned dependency beyond the base
    toolchain. The signing library is a second one, and `AGENTS.md` is updated to say so.
- Latency: the backend can take up to 22 s, and only one live latency sample exists (5161 ms), so
  the loading and timeout states are required, not optional.
- Agents stop at local verification (WEB-11). The live check against the real API needs the human
  to put the key in `.env.local`.

## Open questions
- None.

## Revision history
- Revision 2 (2026-10-22): the repo has no pixel baselines. `e2e/__baseline__` holds text captures
  of the `FeedView` root only, and `app/__golden__` is empty, so revision 1's "regenerate the
  snapshots" proposal was wrong. AC7 now requires the baselines to stay unchanged, and the open
  question is closed.
- Revision 1 (2026-10-21): initial draft from the `web-chat-ui` handoff. Human decisions applied:
  the chat is a floating button and panel on the feed page, there is no per-IP limit in v1, and the
  route trims history to the last 10 turns.

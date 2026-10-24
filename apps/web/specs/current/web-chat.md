# Web Chat Specification

> Last synced: 2026-10-24. Owned artifacts: `apps/web/features/chat/`, `apps/web/app/api/chat/route.ts`,
> `apps/web/e2e/chat.e2e.ts`, `apps/web/e2e/layout.e2e.ts`.

## Purpose

The floating chat widget on the feed page and the server route behind it. The browser talks only to
the same-origin `POST /api/chat`; the route SigV4-signs each turn and relays it to the deployed
`POST /v1/chat` API (root capabilities [`chat-api`](../../../../specs/current/chat-api.md) and
[`chat-api-auth`](../../../../specs/current/chat-api-auth.md)). It is its own capability, distinct from
`web-feed`, because it holds a server-side credential, owns a second feature slice and a route, and has
its own contract with the chat API.

## Requirements

### Requirement: WEBCHAT-1 — A closed-by-default floating dialog

The system SHALL show a floating chat button on the feed page with the panel closed on first load. The
button toggles a `role="dialog"` panel, carries `aria-expanded` and an accessible name that reflects
open or closed, moves focus to the input on open, closes on Escape, and returns focus to the button on
close. The panel has a header Close icon button named "Close chat" (a 44 px hit area, as are the
launcher and Send).

**Source:** web-chat-ui · intent.md AC1; web-chat-ui-polish · intent.md AC5, AC11

#### Scenario: Open and close
- **WHEN** a visitor loads `/`, presses the launcher, then presses the header Close
- **THEN** the panel opens with focus in the input, then closes with focus back on the launcher

### Requirement: WEBCHAT-2 — Turns show pending, answer and numbered sources

The system SHALL show the visitor's message, a status-role animated dots loader with accessible text
(static under `prefers-reduced-motion: reduce`) while a turn is pending, and then the answer. Sources
sit behind a collapsed "Sources (n)" control with `aria-expanded`, listing `[n]`, title and source name
as links that open the source `url` in a new tab with `rel="noopener noreferrer"`. An empty `sources`
list shows no control.

**Source:** web-chat-ui · intent.md AC2; web-chat-ui-polish · intent.md AC6, AC7

#### Scenario: An answer with three sources
- **WHEN** the backend answers with three sources
- **THEN** "Sources (3)" is collapsed; expanding it shows three links

### Requirement: WEBCHAT-3 — Assistant answers render a safe markdown subset

The system SHALL render assistant answers as markdown through `react-markdown` with an element
allow-list, an http(s)-only link transform, new-tab links, no images, and no raw-HTML plugin or
`dangerouslySetInnerHTML`; raw HTML shows as inert text. User messages SHALL stay plain text exactly as
typed.

**Source:** web-chat-ui-polish · intent.md AC1, AC2 · ADR 0038

#### Scenario: Hostile markup in an answer
- **WHEN** an answer contains a `<script>`, a `javascript:` link and an `<img onerror>`
- **THEN** no `<script>` or `<img>` element and no `javascript:` href exists, and nothing runs

### Requirement: WEBCHAT-4 — The conversation follows the latest message

The system SHALL keep the newest message in view on every turn (the question, then the loader, then the
answer) at a 375 by 667 and a 1280 by 800 viewport, SHALL NOT move the scroll position of a reader who
scrolled up while a turn is pending, and SHALL show a "Jump to latest" button whenever the view is not
at the bottom.

**Source:** web-chat-ui-polish · intent.md AC3

#### Scenario: Reader scrolled up
- **WHEN** the visitor scrolls up and the answer then arrives
- **THEN** the scroll position is unchanged and "Jump to latest" is shown

### Requirement: WEBCHAT-5 — The panel stays on screen on a phone and in a long-URL case

The system SHALL present the panel as a full-width bottom sheet on a phone (640 px and narrower) whose
box lies inside the viewport, fits the dynamic viewport height with header and composer visible, and
causes no horizontal overflow, including with a very long unbroken URL in an answer link, a source link
or a code block. On a desktop it is about 28 to 30 rem wide and up to 40 rem tall.

**Source:** web-chat-ui-polish · intent.md AC4, AC5

#### Scenario: Long URL on a phone
- **WHEN** the viewport is 375 by 667 and an answer holds a 300-character link
- **THEN** the panel is within 0..375 px and `scrollWidth <= clientWidth`

### Requirement: WEBCHAT-6 — The composer and the empty state

The system SHALL provide a textarea named "Your question" where Enter sends, Shift+Enter inserts a
newline and Send is disabled while a turn is pending, and SHALL show a greeting with three suggested
questions in an empty conversation. A suggestion goes through the same validation, request and states
as typed text.

**Source:** web-chat-ui · intent.md AC4; web-chat-ui-polish · intent.md AC8, AC9

#### Scenario: A suggestion is pressed
- **WHEN** the visitor presses a suggested question
- **THEN** one request is sent with an empty history and the empty state disappears

### Requirement: WEBCHAT-7 — Caps hold in the UI and the route

The system SHALL cap a question at 1000 characters and block a blank or over-long one in the UI with a
message and no request, SHALL return 400 `invalid_request` from the route for the same, and SHALL
forward at most the last 20 history items (alternating roles starting with `user`, ending with
`assistant`) with each text cut to 4000 characters. The route SHALL reject a body over 524,288 bytes.
The backend stays authoritative.

**Source:** web-chat-ui · intent.md AC3, AC4 · ADR 0033

#### Scenario: A 1001-character question
- **WHEN** the visitor sends 1001 characters, or a direct `POST` carries them
- **THEN** the UI shows an inline message and sends nothing; the route answers 400 without calling the backend

### Requirement: WEBCHAT-8 — Six fixed error states, text-free logging

The system SHALL map each failure to one of six codes (`invalid_request` 400, `busy` 429, `timeout` 504,
`upstream_failure` 502, `unavailable` 503, `internal_error` 500) with a body of exactly `{"error": code}`,
show generic copy per code with Retry, keep the conversation and the question, and write one structured
JSON log line (outcome and duration) that never holds the question, history, answer, credential, URL or
backend detail.

**Source:** web-chat-ui · intent.md AC5 · ADR 0033

#### Scenario: The backend answers 429
- **WHEN** the backend returns 429
- **THEN** the panel shows the "busy" copy and the input keeps the question

### Requirement: WEBCHAT-9 — The route signs with SigV4, calls once and keeps the key server-side

The system SHALL sign `POST {CHAT_API_BASE_URL}/v1/chat` with SigV4 (service `execute-api`, region
`us-east-1`) on the Node.js runtime using `aws4fetch` `AwsClient.sign()` with `retries: 0` and one
`fetch` with a 30 s deadline, and SHALL read `CHAT_API_BASE_URL`, `CHAT_API_ACCESS_KEY_ID` and
`CHAT_API_SECRET_ACCESS_KEY` per request only inside `features/chat/api/`. The key, secret, signature
and base URL SHALL NOT reach the browser, a log or an error body, and SHALL NOT be in a `NEXT_PUBLIC_`
variable. A turn makes exactly one backend call.

**Source:** web-chat-ui · intent.md AC6 · ADR 0032, ADR 0033

#### Scenario: One turn in the browser network tab
- **WHEN** a visitor sends a question
- **THEN** one same-origin `POST /api/chat` is visible and no request to `execute-api`

### Requirement: WEBCHAT-10 — Chat styling uses tokens only

The system SHALL style the chat from the existing design tokens with no hand-authored colour, spacing or
radius value, no new token, and the OS light or dark preference with no toggle. A device
`env(safe-area-inset-*)` inside a spacing value is allowed.

**Source:** web-chat-ui · intent.md AC8; web-chat-ui-polish · intent.md AC13

#### Scenario: Dark mode
- **WHEN** the OS prefers dark
- **THEN** the panel background equals the dark `--surface-card` value

### Requirement: WEBCHAT-11 — The slice keeps one barrel and the feed is untouched

The system SHALL export exactly `ChatWidget` and `handleChatRequest` from `features/chat/index.ts`,
SHALL let no `"use client"` module import the barrel or `api/` except with `import type`, and SHALL leave
the feed's four render states, behaviour at desktop width and the 17 e2e baseline scenarios unchanged.
The widget sits outside the `FeedView` root and writes nothing to the browser console.

**Source:** web-chat-ui · intent.md AC7; web-chat-ui-polish · intent.md AC11, AC12

#### Scenario: The baselines
- **WHEN** `npm run test:e2e` runs without `--update-snapshots`
- **THEN** all 17 baseline scenarios pass

### Requirement: WEBCHAT-12 — The e2e tier is offline

The system SHALL cover open, ask, answer with sources, error states, phone layout, scrolling and
reduced motion in Playwright against a local chat stub with fake credentials, with no call to AWS, and
SHALL cover the signed headers with a unit test that never uses the real key.

**Source:** web-chat-ui · intent.md AC9; web-chat-ui-polish · intent.md AC3, AC4

#### Scenario: Offline run
- **WHEN** `npm run test:e2e` runs with no `.env.local`
- **THEN** every chat scenario passes against the stub

## Invariants

1. **The key never leaves the server.** Only `features/chat/api/` reads the credential variables, and the
   browser sees only the six error codes.
2. **One call per turn.** No retry at any layer (library, route or client).
3. **`features/chat/lib/`, `features/chat/api/`, `features/chat/index.ts` and the route are the stable
   shell.** The polish changed components and CSS only.
4. **Backend contract is frozen from this side.** A contract change goes to the root harness
   (`chat-api`).

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| WEBCHAT-R1 | No per-visitor limit: one visitor can use the shared throttle (5 req/s, burst 10); `AiRadarBudget` is the cost backstop (ADR 0035). | MEDIUM (accepted) | web-chat-ui plan Decision 13 |
| WEBCHAT-R2 | Not exercised against the real API. The human puts the key in `.env.local`, asks one question, and records the latency and a `[1]` citation (H1). | LOW (human) | web-chat-ui audit F7 |
| WEBCHAT-R3 | Vercel function duration versus the route's `maxDuration` 40 is unchecked, and the three `CHAT_API_*` variables are not set (H2). | LOW (human) | web-chat-ui audit |
| WEBCHAT-R4 | A blank or whitespace history `text` passes the route and is rejected by the backend (`history_item_text_invalid`); not fixed by either feature. | MEDIUM | web-chat-ui audit F1 |
| WEBCHAT-R5 | Question and history lengths count UTF-16 units, the backend counts code points; the body cap is checked after reading when there is no `Content-Length`; an abort during the body read maps to `upstream_failure`. | LOW | web-chat-ui audit F3, F4, F5 |
| WEBCHAT-R6 | Source links use `source.url` unfiltered, and an image inside a markdown link leaves an `<a>` with no accessible name. | LOW | web-chat-ui-polish audit F8 |
| WEBCHAT-R7 | No CI run of `harny-feedback-apps-web.yml` against these changes, and the per-turn hook left no evidence. | MEDIUM | web-chat-ui audit F6; web-chat-ui-polish audit F2 |
| WEBCHAT-R8 | Red evidence was not captured for the polish outcomes O5 to O8, and the freeze of the shell rests on mtimes because the files were untracked. Both were accepted at sign-off. | LOW | web-chat-ui-polish audit F4, F6 |
| WEBCHAT-R9 | The launcher's `aria-controls` names an unmounted panel id while closed (F8), and a draft edited while a turn is pending is overwritten with the question if the turn fails (F10). | LOW | web-chat-ui audit F8, F10 |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| web-chat-ui | 2026-10-24 | Created this capability: the `features/chat/` slice, the SigV4 `POST /api/chat` route, the six fixed error codes, history and question caps, the floating widget, the offline chat e2e tier, and the narrowed T29 guard. Audit: APPROVED WITH RESERVATIONS (round 1). |
| web-chat-ui-polish | 2026-10-24 | Presentation only: markdown through a safe subset, stick-to-bottom scrolling, a bottom sheet on a phone, a branded header, a collapsible Sources list, a dots loader, a bigger composer and an empty state with suggestions; two new pinned dependencies; amended WEBCHAT-1 and WEBCHAT-2 in place of the first feature's text. Audit: APPROVED WITH RESERVATIONS (round 1, plus a fix round for F1, F3, F5 and F7). |

## Related ADRs

| ADR | Title | Status |
|---|---|---|
| [0032](../archived/web-chat-ui/decisions/0032-sign-with-aws4fetch-sign-and-our-own-single-fetch.md) | Sign chat requests with aws4fetch `sign()` and our own single `fetch` | Accepted |
| [0033](../archived/web-chat-ui/decisions/0033-the-next-route-is-the-only-chat-caller-with-fixed-error-codes.md) | The Next.js route is the only chat caller, and it answers with six fixed error codes | Accepted |
| [0034](../archived/web-chat-ui/decisions/0034-narrow-the-execute-api-guard-to-the-host-form.md) | Narrow the `execute-api` guard to the host form | Accepted |
| [0035](../archived/web-chat-ui/decisions/0035-no-per-visitor-limit-on-the-chat-route-in-v1.md) | No per-visitor limit on the chat route in v1 | Accepted |
| [0036](../archived/web-chat-ui-polish/decisions/0036-ai-elements-shaped-local-components-not-shadcn-or-ai-elements.md) | Build AI-Elements-shaped local components, not shadcn/ui or AI Elements | Accepted |
| [0037](../archived/web-chat-ui-polish/decisions/0037-dependency-rule-amended-for-react-markdown-and-use-stick-to-bottom.md) | Amend the dependency rule for `react-markdown` and `use-stick-to-bottom` | Accepted |
| [0038](../archived/web-chat-ui-polish/decisions/0038-assistant-markdown-renders-through-a-safe-subset.md) | Assistant markdown renders through a safe subset | Accepted |

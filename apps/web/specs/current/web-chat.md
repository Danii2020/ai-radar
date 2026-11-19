# Web Chat Specification

> Last synced: 2026-11-18 (`web-chat-response-cache`: WEBCHAT-8 amended for the `cache` log field, new WEBCHAT-15 and WEBCHAT-16, WEBCHAT-R13 added, ADRs 0057 and 0058). Earlier: 2026-11-18 (`web-chat-visitor-rate-limit`: WEBCHAT-8 amended to seven codes, new WEBCHAT-14, WEBCHAT-R1 closed, WEBCHAT-R12 added, ADRs 0049 and 0050, ADR 0035 superseded). Earlier: 2026-11-11 (`web-chat-swipe-handle`: WEBCHAT-1 amended and WEBCHAT-12 widened for the phone edge tab, new WEBCHAT-13, ADR 0056). Earlier: 2026-10-24. Owned artifacts: `apps/web/features/chat/`, `apps/web/app/api/chat/route.ts`,
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
close. The panel has a header Close icon button named "Close chat". On a desktop (wider than 640 px) the
launcher, Send and Close have a 44 px hit area. On a phone (640 px and narrower) the launcher is an edge tab,
not a floating button: 24 px wide and at least 44 px tall, flush with the right edge in the lower third of
the viewport, with an `aria-hidden` icon and no visible text, and it is still the one launcher element
(`data-testid="chat-launcher"`, same names, `aria-expanded`, `aria-controls` and focus return). The tab is
below 44 by 44 by decision (ADR 0056) and meets WCAG 2.2 AA 2.5.8 (24 by 24).

**Source:** web-chat-ui · intent.md AC1; web-chat-ui-polish · intent.md AC5, AC11; web-chat-swipe-handle · intent.md AC1, AC2, AC7 · ADR 0056

#### Scenario: Open and close
- **WHEN** a visitor loads `/`, presses the launcher, then presses the header Close
- **THEN** the panel opens with focus in the input, then closes with focus back on the launcher

#### Scenario: The edge tab on a phone
- **WHEN** the viewport is 375 by 667 and `/` loads
- **THEN** the launcher box is flush right (`x + width` in `[374, 375]`), 20 to 24 px wide (CSS 24 px), at least 44 px tall, its top at or below two thirds of the viewport height, with no "Chat" text and no horizontal overflow

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

### Requirement: WEBCHAT-8 — Seven fixed error states, text-free logging

The system SHALL map each failure to one of seven codes (`invalid_request` 400, `busy` 429, `timeout` 504,
`upstream_failure` 502, `unavailable` 503, `rate_limited` 429, `internal_error` 500) with a body of exactly
`{"error": code}`, show generic copy per code with Retry, keep the conversation and the question, and write one
structured JSON log line (outcome and duration, plus `limit` for a limited request, `variable` for an invalid
limiter or cache setting, and `cache` (`hit`, `miss`, `skip`, `error`; absent when the cache is off)) that never holds the question, history, answer, credential, URL, backend detail, IP or visitor
digest. `rate_limited` carries a `Retry-After` header and the copy "You've reached the chat limit for now. Please
try again later."; a backend 429 stays `busy`. `unavailable` also covers a limiter store outage and an invalid
limiter setting, with the copy unchanged and no mention of a limiter or store.

**Source:** web-chat-ui · intent.md AC5 · web-chat-visitor-rate-limit · intent.md AC6, AC11, AC12 · web-chat-response-cache · intent.md AC9 · ADR 0033, ADR 0050, ADR 0057

#### Scenario: The backend answers 429
- **WHEN** the backend returns 429
- **THEN** the panel shows the "busy" copy and the input keeps the question

### Requirement: WEBCHAT-14 — A per-visitor and global limit runs before the backend call, and fails closed

The system SHALL, after body, question and history validation and the `CHAT_API_*` check and before the one backend
call, admit at most `CHAT_RATE_LIMIT_BURST` (default 5) turns per visitor per fixed window of
`CHAT_RATE_LIMIT_BURST_WINDOW_S` seconds (default 60), `CHAT_RATE_LIMIT_DAILY` (20) per visitor per UTC day, and
`CHAT_RATE_LIMIT_GLOBAL_DAILY` (50) in total per UTC day. Otherwise it SHALL answer 429 `rate_limited` with
`Retry-After` and make no backend call. A rejected request SHALL count against none of the limits; an admitted turn
counts even if the backend then fails. The visitor SHALL be the client IP from the first present of
`x-vercel-forwarded-for`, `x-real-ip` and `x-forwarded-for` (IPv6 reduced to its /64, absent or unparseable to one
shared `unknown` bucket), stored only as an HMAC-SHA-256 digest keyed by `CHAT_RATE_LIMIT_SALT`, with every entry
expiring on its own. Counters SHALL live in Upstash Redis over REST (one `EVAL` per check, no retry, 1 s timeout)
on Vercel, and in an in-process store off Vercel. A store failure or an invalid limiter setting SHALL answer 503
`unavailable` with no backend call.

**Source:** web-chat-visitor-rate-limit · intent.md AC1 to AC11, AC13 · ADR 0049

#### Scenario: Six turns from one visitor in one window
- **WHEN** one IP sends six valid requests inside one 60 second window
- **THEN** five are answered and the sixth gets 429 `rate_limited` with a `Retry-After` of at least 1 and the backend is not called for it

#### Scenario: The counter store is down
- **WHEN** the Upstash host refuses connections
- **THEN** the route answers 503 `unavailable` and makes no backend call

### Requirement: WEBCHAT-15 — First-turn answers are cached, and a cache problem is never an error

The system SHALL, for a request with an empty or absent `history`, look up an answer stored under a key that is an
HMAC-SHA-256 digest (keyed by the limiter's salt source, with its own prefix `chat-cache:{v1}:` and a domain tag) of the
question after trimming, collapsing whitespace to single spaces and lower-casing, and on a hit answer 200 with the stored
`{answer, sources}` and no backend call, with a response indistinguishable from a live one. The lookup SHALL run after
validation, the `CHAT_API_*` check and the limiter-configuration check; a hit SHALL count only against the burst limit
(a burst-only check, so a burst-limited visitor still gets 429), and a miss SHALL take the full limiter check, the one
backend call, and then one write with an expiry of `CHAT_CACHE_TTL_S` seconds (default 21600; `0` is off; otherwise 60
to 86400). Only a validated successful answer SHALL be stored; no error outcome is. A request with a history SHALL never
read or write the cache. Every cache failure (network error, non-success or malformed reply, a stored value that fails
the response shape, no reply within 1 s, an invalid setting) SHALL be treated as a miss, answered live, and logged as
`cache: "error"`; the cache SHALL NOT produce an error response. Keys, logs and bodies SHALL hold no question, answer or
IP. The store is the limiter's: Upstash over REST on Vercel, in-process off Vercel.

**Source:** web-chat-response-cache · intent.md AC1 to AC12 · ADR 0057

#### Scenario: The same question twice
- **WHEN** a visitor asks a first-turn question and another visitor then asks it again, with different casing and extra spaces, within the lifetime
- **THEN** the second gets the same answer and sources with no backend call, and the global daily ceiling is not used

#### Scenario: The cache store is down
- **WHEN** the cache read or write fails
- **THEN** the visitor gets the live answer and the log line shows `cache: "error"`

### Requirement: WEBCHAT-16 — Vercel Web Analytics records page views only, and only on Vercel

The system SHALL render the `Analytics` component from `@vercel/analytics/next` in `app/layout.tsx` only when
`process.env.VERCEL` is set, record page views only (no custom event, no chat content), add no cookie, change no response
or UI state, and keep local, unit and e2e runs free of any request to a Vercel script. `@vercel/analytics` SHALL be
imported only by `app/layout.tsx` and pinned exactly. Enabling Web Analytics for the project is a human step.

**Source:** web-chat-response-cache · intent.md AC14 · ADR 0058

#### Scenario: Off Vercel
- **WHEN** the app runs with `VERCEL` unset (local, unit or e2e)
- **THEN** the layout renders no `Analytics` and the e2e console stays empty

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

The system SHALL cover open, ask, answer with sources, error states, phone layout, the phone edge tab and its
touch gestures (trusted touch input through a Chromium CDP session), scrolling and
reduced motion in Playwright against a local chat stub with fake credentials, with no call to AWS, and
SHALL cover the signed headers with a unit test that never uses the real key.

**Source:** web-chat-ui · intent.md AC9; web-chat-ui-polish · intent.md AC3, AC4; web-chat-swipe-handle · intent.md AC9

#### Scenario: Offline run
- **WHEN** `npm run test:e2e` runs with no `.env.local`
- **THEN** every chat scenario passes against the stub

### Requirement: WEBCHAT-13 — Phone swipe gestures open and close the sheet

The system SHALL, on a phone (640 px and narrower, the same query in CSS and JS) and only for touch or pen
pointers, open the sheet on a swipe left that starts on the edge tab and close it on a swipe right that starts
inside the open sheet. A swipe is horizontal travel of at least 40 px with `|dx| >= 2 * |dy|`, judged when the
pointer lifts (no follow-the-finger); a mostly-vertical, short, wrong-direction or cancelled gesture does nothing
and a vertical drag from the tab still scrolls the page. The click a browser fires after a recognized swipe SHALL
NOT toggle the sheet again. A swipe right that starts in the textarea, an input, or an element that scrolls
horizontally (a code block) SHALL NOT close the sheet. Closing by swipe returns focus to the tab and keeps the
conversation. Tap, Enter and Space open the sheet, and Close and Escape close it, as before. A mouse never
triggers a gesture, and on a desktop no touch, pen or mouse drag opens or closes anything. The gesture rule lives
in `features/chat/lib/swipe.ts` (`classifySwipe`). Nothing this adds animates, so reduced motion needs no extra rule.

**Source:** web-chat-swipe-handle · intent.md AC3, AC4, AC5, AC6, AC7 · ADR 0056

#### Scenario: Swipe left on the tab
- **WHEN** a touch gesture starts on the tab and moves by `(-60, +8)`
- **THEN** the dialog opens with focus in the input, and it is still open after the trailing click

#### Scenario: Swipe right inside a code block
- **WHEN** the sheet is open and a touch gesture starts inside a horizontally scrolling `pre` and moves by `(+80, 0)`
- **THEN** the sheet stays open

## Invariants

1. **The key never leaves the server.** Only `features/chat/api/` reads the credential and limiter variables, and the
   browser sees only the seven error codes.
2. **One call per turn.** No retry at any layer (library, route or client).
3. **`features/chat/lib/`, `features/chat/api/`, `features/chat/index.ts` and the route are the stable
   shell.** The polish changed components and CSS only; `web-chat-swipe-handle` added one new pure module
   (`lib/swipe.ts`) and edited no existing shell file.
4. **Backend contract is frozen from this side.** A contract change goes to the root harness
   (`chat-api`).

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| WEBCHAT-R2 | Not exercised against the real API. The human puts the key in `.env.local`, asks one question, and records the latency and a `[1]` citation (H1). | LOW (human) | web-chat-ui audit F7 |
| WEBCHAT-R3 | Vercel function duration versus the route's `maxDuration` 40 is unchecked, and the three `CHAT_API_*` variables are not set (H2). | LOW (human) | web-chat-ui audit |
| WEBCHAT-R4 | A blank or whitespace history `text` passes the route and is rejected by the backend (`history_item_text_invalid`); not fixed by either feature. | MEDIUM | web-chat-ui audit F1 |
| WEBCHAT-R5 | Question and history lengths count UTF-16 units, the backend counts code points; the body cap is checked after reading when there is no `Content-Length`; an abort during the body read maps to `upstream_failure`. | LOW | web-chat-ui audit F3, F4, F5 |
| WEBCHAT-R6 | Source links use `source.url` unfiltered, and an image inside a markdown link leaves an `<a>` with no accessible name. | LOW | web-chat-ui-polish audit F8 |
| WEBCHAT-R7 | No CI run of `harny-feedback-apps-web.yml` against these changes, and the per-turn hook left no evidence (also true of `web-chat-swipe-handle`). | MEDIUM | web-chat-ui audit F6; web-chat-ui-polish audit F2; web-chat-swipe-handle audit F3 |
| WEBCHAT-R8 | Red evidence was not captured for the polish outcomes O5 to O8, and the freeze of the shell rests on mtimes because the files were untracked. Both were accepted at sign-off. | LOW | web-chat-ui-polish audit F4, F6 |
| WEBCHAT-R9 | The launcher's `aria-controls` names an unmounted panel id while closed (F8), and a draft edited while a turn is pending is overwritten with the question if the turn fails (F10). | LOW | web-chat-ui audit F8, F10 |
| WEBCHAT-R10 | Phone swipe gestures are verified only with Chromium CDP touch. Android gesture navigation and iOS Safari may take a swipe from a tab flush with the right edge (Back or Forward), so tap is the guaranteed path. The human confirmed on an iPhone (Brave) that tapping the tab opens the chat; swipe left and right on a real phone, and Android gesture navigation, are not confirmed (task O8 stays open). | MEDIUM (human) | web-chat-swipe-handle audit R1 (intent Q1) |
| WEBCHAT-R12 | The limiter's expire-on-create (Lua) and the memory store's expiry have no test (F2); its `tasks.md` records O0 without a pre-change baseline (F3), has stale working state (F5), and no CI run of `harny-feedback-apps-web.yml` exists for it (F4). The live check with the real Upstash database (`EVAL` accepted, shared counts, digest keys only) is a human step. | MEDIUM | web-chat-visitor-rate-limit audit F2 to F5, H5 |
| WEBCHAT-R13 | The response cache: no red evidence for the handler cache cases, the conventions guards and the e2e file (F2); no per-turn hook record or CI run for it (F3); the audit was a self-audit by the implementing session (F4); the in-process cache has no size bound or pruning test (F5); `GET` and `SET ... EX` have not been run against the real Upstash database and the Web Analytics dashboard is not yet enabled (human live check). | MEDIUM | web-chat-response-cache audit F2 to F5, H1 to H3 |
| WEBCHAT-R11 | The phone tab is 24 by 64, below WEBCHAT-1's old 44 by 44 target (accepted by decision, ADR 0056). `touch-action: pan-y` on the tab and sheet also blocks pinch-zoom that starts there; `pan-y pinch-zoom` was suggested. `ownsHorizontalGesture` keeps a redundant inline-style read (audit F5). | LOW (accepted) | web-chat-swipe-handle audit R2, notes, F5 |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| web-chat-ui | 2026-10-24 | Created this capability: the `features/chat/` slice, the SigV4 `POST /api/chat` route, the six fixed error codes, history and question caps, the floating widget, the offline chat e2e tier, and the narrowed T29 guard. Audit: APPROVED WITH RESERVATIONS (round 1). |
| web-chat-ui-polish | 2026-10-24 | Presentation only: markdown through a safe subset, stick-to-bottom scrolling, a bottom sheet on a phone, a branded header, a collapsible Sources list, a dots loader, a bigger composer and an empty state with suggestions; two new pinned dependencies; amended WEBCHAT-1 and WEBCHAT-2 in place of the first feature's text. Audit: APPROVED WITH RESERVATIONS (round 1, plus a fix round for F1, F3, F5 and F7). |
| web-chat-swipe-handle | 2026-11-11 | Phone edge tab (24 by 64 px, right edge, lower third) in place of the floating button at 640 px and narrower; threshold touch and pen swipe left to open and swipe right to close; amended WEBCHAT-1 and WEBCHAT-12, added WEBCHAT-13 and `lib/swipe.ts`; no new dependency; a dev-only `allowedDevOrigins` setting in `next.config.ts` (human-verified on an iPhone, not audited). Audit: APPROVED WITH RESERVATIONS (round 1). |
| web-chat-visitor-rate-limit | 2026-11-18 | Per-visitor (5 per 60 s, 20 per UTC day) and global (50 per UTC day) turn limits in the route, counted in Upstash Redis over REST (one `EVAL`, no new dependency) with an in-process store off Vercel; a seventh error code `rate_limited` with `Retry-After`; fail closed on a store failure or invalid setting; amended WEBCHAT-8, added WEBCHAT-14, closed WEBCHAT-R1, added WEBCHAT-R12; supersedes ADR 0035 and amends ADR 0033. Audit: APPROVED WITH RESERVATIONS (round 2; round 1 was REJECTED). |
| web-chat-response-cache | 2026-11-18 | First-turn answer cache in the route, in the limiter's Upstash or in-process store (`CHAT_CACHE_TTL_S`, default 6 h, `0` off), a burst-only limiter mode for hits, fail-open on every cache failure, a text-free `cache` log field; plus Vercel Web Analytics rendered only on Vercel (`@vercel/analytics` 2.0.1); amended WEBCHAT-8, added WEBCHAT-15 and WEBCHAT-16 and WEBCHAT-R13; ADRs 0057 and 0058. Audit: APPROVED WITH RESERVATIONS (round 1, a self-audit). |

## Related ADRs

| ADR | Title | Status |
|---|---|---|
| [0032](../archived/web-chat-ui/decisions/0032-sign-with-aws4fetch-sign-and-our-own-single-fetch.md) | Sign chat requests with aws4fetch `sign()` and our own single `fetch` | Accepted |
| [0033](../archived/web-chat-ui/decisions/0033-the-next-route-is-the-only-chat-caller-with-fixed-error-codes.md) | The Next.js route is the only chat caller, and it answers with six fixed error codes | Accepted |
| [0034](../archived/web-chat-ui/decisions/0034-narrow-the-execute-api-guard-to-the-host-form.md) | Narrow the `execute-api` guard to the host form | Accepted |
| [0035](../archived/web-chat-ui/decisions/0035-no-per-visitor-limit-on-the-chat-route-in-v1.md) | No per-visitor limit on the chat route in v1 | Superseded by ADR 0049 |
| [0036](../archived/web-chat-ui-polish/decisions/0036-ai-elements-shaped-local-components-not-shadcn-or-ai-elements.md) | Build AI-Elements-shaped local components, not shadcn/ui or AI Elements | Accepted |
| [0037](../archived/web-chat-ui-polish/decisions/0037-dependency-rule-amended-for-react-markdown-and-use-stick-to-bottom.md) | Amend the dependency rule for `react-markdown` and `use-stick-to-bottom` | Accepted |
| [0038](../archived/web-chat-ui-polish/decisions/0038-assistant-markdown-renders-through-a-safe-subset.md) | Assistant markdown renders through a safe subset | Accepted |
| [0049](../archived/web-chat-visitor-rate-limit/decisions/0049-per-visitor-and-global-chat-limits-counted-in-upstash-over-rest-failing-closed.md) | Limit chat turns per visitor and globally, counted in Upstash Redis over REST, failing closed | Accepted |
| [0050](../archived/web-chat-visitor-rate-limit/decisions/0050-the-chat-route-answers-with-seven-fixed-error-codes.md) | The chat route answers with seven fixed error codes | Accepted |
| [0057](../archived/web-chat-response-cache/decisions/0057-first-turn-chat-answers-are-cached-in-the-route-in-upstash-and-fail-open.md) | Cache first-turn chat answers in the route, in the limiter's Upstash store, failing open | Accepted |
| [0058](../archived/web-chat-response-cache/decisions/0058-dependency-rule-amended-for-vercel-analytics-rendered-only-on-vercel.md) | Amend the dependency rule for `@vercel/analytics`, rendered only on Vercel | Accepted |
| [0056](../archived/web-chat-swipe-handle/decisions/0056-phone-chat-launcher-is-a-24-by-64-edge-tab-with-threshold-swipes.md) | On phones the chat launcher is a 24 by 64 px edge tab with threshold touch and pen swipes | Accepted |

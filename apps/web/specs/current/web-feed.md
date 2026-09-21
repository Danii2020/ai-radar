# Web Feed Specification

> Last synced: 2026-09-18. Owned artifacts: `apps/web/` (Next.js 16 App Router
> project — `app/`, `features/feed/`, `scripts/generate-api-types.mjs`).

## Purpose

The read-only, server-rendered web front end for the curated feed: a Next.js
app that fetches `feed-api` (Spec 01) on the server and ships HTML with cards,
tag filtering, and cursor pagination. It is its own capability, distinct from
`feed-api`, because it is a different runtime/language boundary (TypeScript
+ React on Vercel, vs. Python on Lambda/API Gateway) with its own toolchain,
its own generated-types drift guarantee, and its own deploy target — folding
it into `feed-api` would blur "what the API promises" with "how one particular
client consumes it."

## Requirements

### Requirement: WEB-1 — All `feed-api` fetching is server-side only

The system SHALL fetch `feed-api` exclusively from server-rendered code path
(an async Server Component), never from a `"use client"` module, and SHALL
NOT expose the API base URL to the browser bundle.

**Source:** web-feed-ui · contract.md AD-4, Guarantees 1 & 17

#### Scenario: No client-side fetch or public env var exists
- **WHEN** the application source tree under `apps/web/` is inspected
- **THEN** no file contains a `NEXT_PUBLIC_*` identifier, and no
  `"use client"`-directive module imports the fetch client (`client.ts`) or
  the drain helper (`load-feed.ts`)

### Requirement: WEB-2 — Types are generated from the schema artifact, never hand-authored

The system SHALL generate its TypeScript types for `CardOut`/`FeedResponse`
from `docs/api/feed-api.v1.schema.json` via a committed codegen script, and
SHALL fail a test on any drift between the committed generated file and a
fresh regeneration.

**Source:** web-feed-ui · contract.md AD-3, Guarantee 13

#### Scenario: The schema artifact changes upstream
- **WHEN** `feed-api`'s schema artifact adds, removes, or renames a field
- **THEN** `apps/web/features/feed/types.generated.test.ts`'s drift check
  fails loudly, rather than the UI silently drifting from the real contract

### Requirement: WEB-3 — Cursor pagination is URL-addressable and opaque

The system SHALL represent pagination as plain URL links
(`/?tag=<t>&cursor=<c>`), SHALL pass any `cursor` value back to `feed-api`
byte-identical to the `next_cursor` it was given, and SHALL NOT parse,
decode, construct, or compare a cursor anywhere in the codebase.

**Source:** web-feed-ui · contract.md AD-5, Guarantee 3

#### Scenario: A page is paginated
- **WHEN** a user follows "Next page →"
- **THEN** the resulting request's `cursor` query parameter equals the
  previous response's `next_cursor`, unmodified, and browser Back reaches the
  prior page for free (no client-side state)

### Requirement: WEB-4 — Empty-but-cursored pages are drained, bounded

The system SHALL follow `next_cursor` when a page returns zero cards but a
live cursor, up to a hard cap of `MAX_DRAIN_REQUESTS` (5) requests per render,
returning the first non-empty page found or the last empty one (cursor
intact) if the cap is reached — and SHALL NEVER claim "no matches" for a page
it did not actually read.

**Source:** web-feed-ui · contract.md AD-6, Guarantees 6 & 7

#### Scenario: A tag's matches begin on a later page
- **WHEN** `GET /v1/cards?tag=<t>` returns `{cards: [], next_cursor: <token>}`
  (a real, live-verified `feed-api` behavior — its `FilterExpression` applies
  after `Limit`)
- **THEN** `loadFeed()` follows the cursor rather than reporting a false
  "no matches," up to the 5-request cap

### Requirement: WEB-5 — Exactly one of four render states per request

The system SHALL render exactly one of `feed-list` / `feed-empty` /
`feed-no-match` / `feed-error` per request, each carrying a stable
`data-testid`, and SHALL NOT leak a status code, base URL, or stack trace
into any error-state render.

**Source:** web-feed-ui · contract.md Guarantees 10 & 11

#### Scenario: The upstream API is unreachable
- **WHEN** `feed-api` cannot be reached (DNS/TCP failure, or the
  `AbortSignal.timeout` fires)
- **THEN** the page renders `data-testid="feed-error"` with generic copy
  only, while a single structured `feed_fetch_failed` JSON line is logged
  server-side (never shown to the browser)

### Requirement: WEB-6 — Feed responses are cached with an explicit TTL

The system SHALL pass `next: { revalidate: REVALIDATE_SECONDS }` (300s) on
every `feed-api` fetch, so repeat views of the same URL within that window do
not necessarily re-hit the upstream, billed API.

**Source:** web-feed-ui · contract.md AD-9, Guarantees 2 & 16

#### Scenario: The same feed URL is viewed twice within 5 minutes
- **WHEN** a second request for an identical `tag`/`cursor` combination
  arrives inside the 300s window
- **THEN** Next's Data Cache may serve it without a second upstream request
  — **open/accepted, not empirically confirmed**: see Open reservations below

### Requirement: WEB-7 — Tag chips are a page-local projection, not a vocabulary

The system SHALL derive its promoted tag chips from `topTags()` of the
currently-rendered page only (deterministic frequency + alphabetical
tie-break, capped at `MAX_TAG_CHIPS`=12), and SHALL make every tag on every
card clickable regardless of chip promotion — because no `/tags` endpoint
exists on `feed-api` and the real corpus has 281 distinct tags over 87 cards.

**Source:** web-feed-ui · contract.md AD-11, Guarantee 15

#### Scenario: A tag not among the top 12 is clicked from a card
- **WHEN** a user clicks a tag chip that is on a card but not in the
  promoted row
- **THEN** the click still re-queries `feed-api` with `?tag=<that tag>` — tag
  filtering is always a real server round trip, never a client-side filter
  over an already-fetched page

### Requirement: WEB-8 — Dark mode is OS-preference only in this phase

The system SHALL wire only the automatic `prefers-color-scheme` path in
`tokens.css`; it SHALL NOT ship a theme toggle, SHALL NOT set a `data-theme`
attribute anywhere in application code, and SHALL NOT persist a theme choice
(no cookie, no `localStorage`).

**Source:** web-feed-ui · contract.md AD-12

#### Scenario: A future phase wants a manual toggle
- **WHEN** a later feature proposes a light/dark switch
- **THEN** it is additive to `tokens.css`'s already-authored
  `[data-theme="dark"]`/`[data-theme="light"]` selectors (left unused, not
  unwritten, by this capability) — not a rewrite of the token file

### Requirement: WEB-9 — Design tokens and component CSS are copied byte-verbatim

The system SHALL treat `apps/web/app/globals.css` and
`apps/web/features/feed/feed.module.css` as verbatim copies of the
hand-authored design deliverables under `specs/archived/web-feed-ui/
claude-design-outputs/`; no hand-authored colour, spacing, or radius value
may exist outside those two files' custom properties.

**Source:** web-feed-ui · contract.md AD-7 (revised 2026-09-18)

#### Scenario: A design value needs to change
- **WHEN** a card accent color, spacing, or radius needs to change
- **THEN** the change is made in the design deliverable first and the CSS
  files re-copied verbatim — never hand-edited in place

### Requirement: WEB-10 — One npm project, no workspaces, additive to the repo

The system SHALL live entirely under `apps/web/` as a single self-contained
npm project (one `package-lock.json`, no root `package.json`, no
Turborepo/Nx/workspaces), and SHALL NOT modify any file under `src/`,
`tests/`, `infra/`, `docs/api/`, `pyproject.toml`, `uv.lock`, or any
`Dockerfile*` — `uv` remains the only Python tool, npm the only Node one.

**Source:** web-feed-ui · contract.md AD-1, AD-2, Guarantee 19

#### Scenario: A future frontend feature (e.g. the Phase 3 chat UI) lands
- **WHEN** a new route is added to this app
- **THEN** it reuses this same `apps/web/` project, npm project, test setup,
  and (eventually) Vercel project — never a second frontend app directory

### Requirement: WEB-11 — Deployment is a human-run step; the executor stops at local verification

The system's automated pipeline SHALL NOT create a Vercel project, run
`vercel*`, or run `cdk deploy`/`cdk destroy`. An executor's definition of
done is: production build, lint, typecheck, and tests green locally, plus
one local dev-server browser check against the real `feed-api`.

**Source:** web-feed-ui · contract.md AD-10

#### Scenario: All local gates pass
- **WHEN** `npm run build`/`lint`/`typecheck`/`test` all exit 0 and the local
  dev-server smoke check confirms real cards render
- **THEN** the feature may be marked locally shipped — but is NOT yet "live"
  until a human completes the Vercel deploy + `feed-api` CORS redeploy
  runbook (see Open reservations)

## Invariants

1. **The response contract is frozen from this side.** If the UI wants a
   field `feed-api` doesn't return, that's a `feed-api` spec revision with a
   version bump — never a second data path, scrape, or client-side
   reconstruction (mirrors `feed-api.md`'s own FA-2/FA-3 framing).
2. **Cursors are bytes.** No feature in this capability may parse, decode,
   log-decode, compare, or synthesize a cursor.
3. **`app/page.tsx` stays a thin, ~25-line shell.** All render-state branching
   lives in the synchronous `FeedView`, which is unit-testable; the async
   page shell itself is not (Next's Server Components aren't
   Vitest/RTL-testable) and is covered only by the manual browser check.

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| WEB-R1 | Not yet deployed: no Vercel project exists, and `feed-api`'s CORS allow-list has not been updated to a real Vercel origin. `R17`/`R18` and all `M1`-`M10` rows in the archived audit remain PENDING — this capability is locally verified only, not live. | HIGH (operational, expected — Phase 5 is human-gated by design) | `specs/archived/web-feed-ui/audit.md` |
| WEB-R2 | Whether `AbortSignal.timeout` on the feed fetch disables Next's Data Cache for that request (i.e. whether WEB-6's 300s caching genuinely applies) was researched but never empirically confirmed via a live repeat-view request count. Accepted as final, not reopened — worst case is uncached views, still bounded by `MAX_DRAIN_REQUESTS` and backstopped by `AiRadarBudget`. One-line revert (drop `signal`) if ever needed. | LOW (accepted) | `specs/archived/web-feed-ui/audit.md` AD-9/C25 |
| WEB-R3 | `apps/web/features/feed/conventions.test.ts`'s T29/T30 (no `NEXT_PUBLIC_`/`execute-api` literal, no client-side fetch) scan only `.ts`/`.tsx` under `features/**` and `app/**` — not `scripts/`, `*.mjs`/`*.mts`, or config files — so the guard is narrower than its own description, though no violation exists today. | LOW | `specs/archived/web-feed-ui/audit.md` |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| web-feed-ui | 2026-09-18 | Created this capability from scratch: the Next.js app, generated-types drift guarantee, server-only fetch client, bounded drain, cursor-link pagination, four-state `FeedView`, page-local tag chips, and the byte-verbatim design-token CSS pipeline. |

## Related ADRs

| ADR | Title | Status |
|---|---|---|
| [0001](../archived/web-feed-ui/decisions/0001-generate-types-from-schema-artifact.md) | Generate TypeScript types from the schema artifact, never hand-author them | Accepted |
| [0002](../archived/web-feed-ui/decisions/0002-server-only-fetching.md) | All `feed-api` fetching is server-side only | Accepted |
| [0003](../archived/web-feed-ui/decisions/0003-url-cursor-pagination.md) | Pagination is URL cursor links, not client-side "load more" | Accepted |
| [0004](../archived/web-feed-ui/decisions/0004-bounded-empty-page-drain.md) | Drain empty-but-cursored pages, bounded to 5 requests | Accepted |
| [0005](../archived/web-feed-ui/decisions/0005-byte-verbatim-design-tokens.md) | Styling is CSS Modules, copied byte-verbatim from hand-authored design deliverables | Accepted |
| [0006](../archived/web-feed-ui/decisions/0006-explicit-revalidate-and-abort-signal.md) | Explicit 300s revalidate on the feed fetch; keep the AbortSignal timeout | Accepted |
| [0007](../archived/web-feed-ui/decisions/0007-deployment-is-a-human-step.md) | Deployment is a human-run step; the automated pipeline stops at local verification | Accepted |

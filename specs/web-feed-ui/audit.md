# Audit: web-feed-ui

> Status legend: `PENDING` (not started) · `IN PROGRESS` · `PASS` · `FAIL` ·
> `DEFERRED` · `N/A`. Every row traces to `intent.md` (goal / success criterion)
> or `contract.md` (interface / behavior guarantee / AD).
>
> **Two kinds of rows, and they must not be conflated.** `R*`/`C*`/`T*` rows are
> **executor-verifiable, local, offline** (plus one local browser check). `M*`
> rows are **manual, human-run** steps from `roadmap.md` Phase 5 — a deploy to
> Vercel and a CDK redeploy. **No agent may mark an `M*` row PASS**; only the
> human who ran the command may, and the evidence must be real output, not an
> expectation. This mirrors the Phase 1 precedent and `specs/feed-api/audit.md`.

## Requirements Checklist

| ID | Requirement | Source | Status | Notes |
|---|---|---|---|---|
| R1 | A server-rendered feed page: cards fetched on the server, HTML shipped, rendered in API order with no client-side sort | intent Goal 1 | PENDING | |
| R2 | TypeScript types **generated** from `docs/api/feed-api.v1.schema.json` and committed, with a drift test that fails on any difference | intent Goal 2 / AD-3 | PENDING | |
| R3 | Generated `CardOut` has exactly the artifact's 12 properties and `FeedResponse` exactly `cards` + `next_cursor`; field-name sets asserted against the artifact | intent Success Criteria | PENDING | |
| R4 | Tag filtering re-queries the API (`?tag=`), never a client-side filter of a fetched page | intent Goal 3 | PENDING | |
| R5 | Cursor pagination: `next_cursor` passed back verbatim, never parsed/constructed; no offset assumption anywhere | intent Goal 4 / AD-5 | PENDING | |
| R6 | Spec 01 Guarantee 4 handled: empty-but-cursored pages drained, bounded at `MAX_DRAIN_REQUESTS`; short pages never end pagination | intent Goal 4 / AD-6 | PENDING | |
| R7 | Empty feed, tag-with-no-matches, and API-unreachable each render a distinct, identifiable state; no blank page or unhandled exception | intent Goal 5 | PENDING | |
| R8 | Feature-folder organization only: flat `features/feed/`, no aggregates/repositories/services/`entities/`, no second `Card` model | intent Goal 6 / architecture-principles | PENDING | |
| R9 | API base URL comes from `FEED_API_BASE_URL`; no hardcoded `execute-api` literal in application code; `.env.example` documents it | intent Goal 7 | PENDING | |
| R10 | Server-only configuration: no `NEXT_PUBLIC_*` variable, no `"use client"` module fetching `feed-api` | AD-4 / Guarantee 1, 17 | PENDING | |
| R11 | Local green gates: `npm run build`, `npm run lint`, `npm run typecheck`, `npm test` all exit 0 in `apps/web` | intent Goal 8 | PENDING | |
| R12 | Zero backend change: no diff under `src/`, `tests/`, `infra/`, `docs/api/`, `pyproject.toml`, `uv.lock`, `Dockerfile*`; `uv run pytest tests/` still 349 passed | intent Success Criteria / Guarantee 19 | PENDING | |
| R13 | Cost discipline: ≤ `MAX_DRAIN_REQUESTS` upstream requests per view, explicit `revalidate`, no polling/retry/client refetch | intent Constraints / AD-9 | PENDING | |
| R14 | Non-Goals respected: no chat, no auth, no detail page, no CSS framework, no state/data library, no E2E stack, no analytics, no API contract change | intent Non-Goals | PENDING | |
| R15 | **Local live check**: `npm run dev` against the real API renders real `ai-radar-cards` content in a browser at `localhost:3000` | intent Success Criteria | PENDING | Executor-runnable (read-only GET; `http://localhost:3000` is already the allowed CORS origin) |
| R16 | A written manual runbook (Vercel project settings, env var, deploy command, CORS redeploy, verification curls, teardown) exists before any deploy is attempted | intent Goal 8 / AD-10 | PENDING | The runbook is the executor's deliverable; running it is not |
| R17 | **Manual**: deployed on Vercel at a real URL rendering the real feed | intent Goal 8 (human) | PENDING | See M1–M4 |
| R18 | **Manual**: `feed-api`'s CORS allow-list updated to the real Vercel origin and curl-verified (allowed origin gets the header, foreign origin gets none) | intent Goal 9 (human) | PENDING | See M5–M6 |

## Contract Compliance

| ID | Contract item | Status | Verified by |
|---|---|---|---|
| C1 | G1 — server rendering; no client component fetches the API; no `NEXT_PUBLIC_*` exists | PENDING | |
| C2 | G2 — exactly one `fetch` per `fetchFeed` call; `limit` always sent; `tag`/`cursor` sent iff non-empty | PENDING | |
| C3 | G3 — cursor round-trips byte-identically; no parse/decode/compare/synthesis of a cursor anywhere | PENDING | |
| C4 | G4 — API order preserved; no `sort`/`reverse`/comparator in `features/feed/` | PENDING | |
| C5 | G5 — "next page" renders iff `nextCursor !== null`, including for an empty or short page | PENDING | |
| C6 | G6 — bounded drain: follows the cursor only while the page is empty, ≤ `MAX_DRAIN_REQUESTS`; never drains a non-empty page | PENDING | |
| C7 | G7 — drain-cap-reached copy is honest ("searched the first N pages") and still offers the next-page link | PENDING | |
| C8 | G8 — a card failing `isCardOut` is dropped + counted; the rest still render | PENDING | |
| C9 | G9 — `tags`/`takeaways`/`next_cursor` `undefined` renders correctly (no chips / no bullets / no next link), never throws | PENDING | |
| C10 | G10 — exactly one of `feed-list`/`feed-empty`/`feed-no-match`/`feed-error` renders, each with a stable `data-testid` | PENDING | |
| C11 | G11 — every failure is caught in `page.tsx`, logged as one structured `feed_fetch_failed` line, and rendered as `feed-error`; no message/stack/status/base URL reaches the browser | PENDING | |
| C12 | G12 — missing `FEED_API_BASE_URL` throws `FeedApiError('config')` at request time (named variable), not at import time; `npm run build` succeeds without it | PENDING | |
| C13 | G13 — `types.generated.ts` == `npm run generate:types` output; field-name sets == the artifact's `properties` keys | PENDING | The load-bearing anti-drift guarantee |
| C14 | G14 — `REQUIRED_STRING_FIELDS` == `$defs.CardOut.required` minus `relevance`, asserted against the artifact JSON | PENDING | |
| C15 | G15 — tag selection is a server round trip (new URL → new `?tag=` request); no client-side `filter()` over fetched cards | PENDING | |
| C16 | G16 — ≤ `MAX_DRAIN_REQUESTS` upstream requests per view; `revalidate: REVALIDATE_SECONDS` passed; no polling/interval/retry | PENDING | |
| C17 | G17 — no `execute-api` literal and no `NEXT_PUBLIC_` identifier in `apps/web` application code | PENDING | |
| C18 | G18 — tests are hermetic: `fetch` stubbed, no network, no AWS, no browser download, no Docker | PENDING | |
| C19 | G19 — zero backend change (git-verified) | PENDING | |
| C20 | G20 — filtering and pagination are plain links; the feed works with JS disabled | PENDING | |
| C21 | Error table — `config`/`network`/`http`(400/429/5xx)/`malformed` each map to the documented behavior; `invalid_cursor` offers "back to the first page"; **no automatic retry on 429/5xx** | PENDING | |
| C22 | AD-1/AD-2 — app at `apps/web/`; npm with a single committed `package-lock.json`; no workspaces/Turborepo; `uv`, `pyproject.toml`, `uv.lock` untouched | PENDING | |
| C23 | AD-7 — CSS Modules only; no Tailwind/PostCSS config, no UI kit or icon package in `package.json` | PENDING | |
| C24 | AD-8 — `app/page.tsx` stays a thin shell (no branching beyond the single try/catch); all state logic lives in `FeedView` | PENDING | |
| C25 | AD-9 — `revalidate: 300` present; the `AbortSignal`/Data-Cache open question resolved one way or the other and **recorded in the Audit Log** | PENDING | Either outcome is acceptable; silence is not |
| C26 | AD-11 — chips are `topTags` of the current page (≤ 12, deterministic tie-break), every card tag is a link, the active tag is always shown with a clear affordance, and the page-local limitation is stated in the UI copy | PENDING | |

## Test Coverage

| ID | Test description | Status | Test file |
|---|---|---|---|
| T1 | Regenerating types from the artifact reproduces the committed `types.generated.ts` exactly (drift) | PENDING | `apps/web/features/feed/types.generated.test.ts` |
| T2 | `CardOut`/`FeedResponse` field-name sets equal the artifact's `properties` keys | PENDING | `apps/web/features/feed/types.generated.test.ts` |
| T3 | `REQUIRED_STRING_FIELDS` equals `$defs.CardOut.required` minus `relevance` | PENDING | `apps/web/features/feed/types.generated.test.ts` |
| T4 | `fetchFeed` issues exactly one request, to `<base>/v1/cards`, with `limit` always present | PENDING | `apps/web/features/feed/client.test.ts` |
| T5 | `tag`/`cursor` are included iff non-empty; blank/whitespace `tag` is omitted entirely | PENDING | `apps/web/features/feed/client.test.ts` |
| T6 | A cursor is sent back byte-identically to the value received (round trip through `URLSearchParams`) | PENDING | `apps/web/features/feed/client.test.ts` |
| T7 | The fetch passes `next.revalidate === REVALIDATE_SECONDS` | PENDING | `apps/web/features/feed/client.test.ts` |
| T8 | Missing/blank `FEED_API_BASE_URL` → `FeedApiError('config')` and **no** fetch call | PENDING | `apps/web/features/feed/client.test.ts` |
| T9 | 400 / 429 / 500 → `FeedApiError('http')` carrying the status; **no retry** is attempted | PENDING | `apps/web/features/feed/client.test.ts` |
| T10 | A rejected fetch (network/timeout) → `FeedApiError('network')` | PENDING | `apps/web/features/feed/client.test.ts` |
| T11 | Non-JSON body, non-object body, or non-array `cards` → `FeedApiError('malformed')` | PENDING | `apps/web/features/feed/client.test.ts` |
| T12 | A card failing `isCardOut` is dropped, `skipped` increments, and the good cards still return | PENDING | `apps/web/features/feed/client.test.ts` |
| T13 | `next_cursor` `undefined` / `null` / `""` all normalise to `nextCursor === null` | PENDING | `apps/web/features/feed/client.test.ts` |
| T14 | **The live-verified fixture**: `{cards: [], next_cursor: "<token>"}` is drained and a later non-empty page is returned | PENDING | `apps/web/features/feed/load-feed.test.ts` |
| T15 | Each drain hop sends the previous page's `next_cursor` verbatim | PENDING | `apps/web/features/feed/load-feed.test.ts` |
| T16 | A non-empty **short** page returns after exactly one request (never drained) | PENDING | `apps/web/features/feed/load-feed.test.ts` |
| T17 | The drain stops at `MAX_DRAIN_REQUESTS` and returns the still-live cursor | PENDING | `apps/web/features/feed/load-feed.test.ts` |
| T18 | `feedHref` omits empty/nullish params (never `?tag=`) and encodes the cursor without altering its value | PENDING | `apps/web/features/feed/href.test.ts` |
| T19 | `topTags` is frequency-ordered, alphabetically tie-broken, capped at `MAX_TAG_CHIPS`, and ignores `tags: undefined` | PENDING | `apps/web/features/feed/tags.test.ts` |
| T20 | Cards render in the given (deliberately unsorted) order — proves no client-side sort | PENDING | `apps/web/features/feed/feed-view.test.tsx` |
| T21 | `feed-empty` renders for zero cards with no tag and an exhausted cursor | PENDING | `apps/web/features/feed/feed-view.test.tsx` |
| T22 | `feed-no-match` renders for zero cards with an active tag, and offers a clear-filter link | PENDING | `apps/web/features/feed/feed-view.test.tsx` |
| T23 | `feed-error` renders for each `FeedErrorCode` and leaks no status, base URL, or stack text | PENDING | `apps/web/features/feed/feed-view.test.tsx` |
| T24 | Exactly one state testid is present in any single render (states are exclusive) | PENDING | `apps/web/features/feed/feed-view.test.tsx` |
| T25 | The next-page link appears iff `nextCursor !== null` — including on an empty page — and never on the last page | PENDING | `apps/web/features/feed/feed-view.test.tsx` |
| T26 | Tag chips link to `/?tag=<tag>` (a real navigation, not a handler) and the active tag is shown when absent from the page's cards | PENDING | `apps/web/features/feed/feed-view.test.tsx` |
| T27 | `CardItem` renders title/url/source/summary/tags/type/relevance/published/takeaways; the title link is `target="_blank" rel="noopener noreferrer"` | PENDING | `apps/web/features/feed/card-item.test.tsx` |
| T28 | `CardItem` with `tags`/`takeaways` `undefined` renders nothing for them and does not throw; `published: ""` renders `date n/a`; an unknown `type` uses the neutral accent | PENDING | `apps/web/features/feed/card-item.test.tsx` |
| T29 | No `NEXT_PUBLIC_` identifier and no `execute-api` literal anywhere in `apps/web` application code | PENDING | `apps/web/features/feed/conventions.test.ts` |
| T30 | No `"use client"` module imports `client.ts`/`load-feed.ts` (the browser never fetches the API) | PENDING | `apps/web/features/feed/conventions.test.ts` |
| T31 | No `.sort(`/`.reverse(` in `features/feed/` (API order is authoritative) | PENDING | `apps/web/features/feed/conventions.test.ts` |

## Manual verification (human-run — an agent may NOT tick these)

| ID | Step | Status | Evidence |
|---|---|---|---|
| M1 | Vercel project created with **Root Directory `apps/web`** and `FEED_API_BASE_URL` set (Production) | PENDING | |
| M2 | Production deploy succeeds; real URL recorded | PENDING | |
| M3 | The deployed URL renders **real** `ai-radar-cards` content, ordered by relevance then date | PENDING | |
| M4 | Tag chip narrows the feed via `?tag=`; "Next page" reaches cards absent from page 1 (two IDs/titles spot-checked, disjoint) | PENDING | |
| M5 | `cdk diff AiRadarFeedApi` shows **only** `CorsConfiguration.AllowOrigins` changing; deploy succeeds | PENDING | Watch for the unrelated Lambda-concurrency quota bridge flag — see `specs/feed-api/tasks.md` 6.2 |
| M6 | `curl -H "Origin: https://<vercel-url>"` returns `access-control-allow-origin: https://<vercel-url>`; a foreign origin returns **no** `access-control-*` header | PENDING | Both halves required, as `feed-api` M7 did |
| M7 | `/?tag=zzz-no-such-tag` on the deployed URL renders the no-match state (not a blank page) | PENDING | |
| M8 | README updated with the real URL/origin/date + teardown; this file's `M*` rows filled with real output | PENDING | |
| M9 | Cost sanity: no new AWS cost class; `AiRadarBudget` alert thresholds uncrossed; Vercel stays on the free tier | PENDING | |
| M10 | Teardown path confirmed documented (delete the Vercel project; redeploy `AiRadarFeedApi` with the origin list back to `http://localhost:3000`) | PENDING | Documented, not necessarily executed |

## Audit Log

| Date | Auditor | Finding | Severity | Resolution |
|---|---|---|---|---|
| 2026-09-04 | sdd-architect | Live probe of the deployed `feed-api`: `GET /v1/cards?tag=zzz-no-such-tag&limit=5` returns `200 {"cards": [], "next_cursor": "eyJjYXJkX2lkIjoi…"}` — an **empty page with a live cursor**. Spec 01's Guarantee 4 is not theoretical; a naive UI would report "no matches" for tags whose matches begin on a later page. | INFO (design input) | Drove AD-6 (bounded drain, `MAX_DRAIN_REQUESTS = 5`), Guarantees 6–7, T14–T17, and the "searched the first N pages" copy. |
| 2026-09-04 | sdd-architect | Live probe: 87 cards, **281 distinct tags** (long tail — most appear once), 5 pages at `limit=20`. A global tag vocabulary would be unusable even if an endpoint existed. | INFO (design input) | Drove AD-11 (top-12 page-local chips + every card tag clickable) and C26. |
| 2026-09-04 | sdd-architect | Live probe: an origin outside the allow-list receives **no** `access-control-*` header at all; only `http://localhost:3000` is allowed today. | INFO | Local dev needs no `feed-api` change; the deployed origin does (M5/M6, roadmap Phase 5). |
| 2026-09-04 | sdd-architect | AD-4 consequence, recorded so it is not "discovered" later as a defect: because every fetch is server-side, **the browser never issues a cross-origin request to `feed-api` in Phase 2**, so the CORS update is forward-looking hygiene (and Phase 3's dependency), verified by curl rather than by app traffic. | INFO (accepted) | Documented in contract.md AD-4 and the Honest Limitations; the acceptance criterion is met via curl, which the brief explicitly permits. |
| 2026-09-04 | sdd-architect | Open question left deliberately unresolved: whether `AbortSignal.timeout` disables Next's Data Cache for the feed fetch. Not settled by the docs. | LOW (open) | AD-9: one-line fallback (drop `signal`), and C25 requires the outcome to be recorded here after the first real run. |
| | | | | |

## Sign-off gates

- **Executor may not** create a Vercel project, run `vercel*`, or run
  `cdk deploy`/`cdk destroy`. Any task that seems to require it is a Phase 5
  human step (AD-10).
- **Test-writer** should treat T1–T3 (contract parity) and T14–T17 (the drain) as
  the load-bearing tests; the rest are ordinary coverage.
- **Auditor** should verify R8/R14 by *reading the tree*, not by trusting this
  file: a `services/`, `entities/`, `domain/`, `repositories/`, or
  `viewmodels/` directory under `apps/web`, or a second card type, is a spec
  violation regardless of green tests.

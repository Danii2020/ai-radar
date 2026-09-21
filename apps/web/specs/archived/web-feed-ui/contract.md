# Contract: web-feed-ui

**Language/stack of this feature: TypeScript + React 19 on Next.js 16 (App
Router), tested with Vitest.** Every code block below is TypeScript/TSX/JSON/
shell — the Python in this repo is *upstream* of this app and is never imported,
extended, or edited by it.

## Pinned external surface (verified this session — do not trust memory)

### The live `feed-api` (Spec 01) — probed 2026-09-04

```
BASE   https://fdcksuokyh.execute-api.us-east-1.amazonaws.com
ROUTE  GET /v1/cards?tag=<str>&limit=<1..100, default 20>&cursor=<opaque>
```

| Probe | Observed |
|---|---|
| `GET /v1/cards?limit=100` | `200`, **87 cards**, `next_cursor: null`, 281 distinct tags (`llm` 32, `agents` 16, `interpretability` 8 — long tail), types `paper` 50 / `news` 26 / `concept` 4 / `release` 4 / `project` 3 |
| `GET /v1/cards?limit=1` + `Origin: http://localhost:3000` | `200` with `access-control-allow-origin: http://localhost:3000` |
| any other `Origin` | **no** `access-control-*` header at all (not `*`, not an echo) |
| `GET /v1/cards?tag=zzz-no-such-tag&limit=5` | `200 {"cards": [], "next_cursor": "eyJjYXJkX2lkIjoi…"}` — **empty page, live cursor** (Guarantee 4 in the wild) |
| `GET /v1/cards?limit=0` | `400 {"error":"invalid_limit","message":"limit must be an integer between 1 and 100"}` |
| `GET /v1/cards?cursor=garbage` | `400 {"error":"invalid_cursor",…}` |

Real 200 body shape (abridged, from the live response):

```jsonc
{
  "cards": [
    {
      "card_id": "983102b3ea3b4340",
      "title": "AI agents rapidly exploit security vulnerabilities from patch discussions",
      "url": "https://simonwillison.net/2026/Aug/28/just-a-rumour-of-a-bug/",
      "source": "Simon Willison",
      "summary": "Modern AI coding agents can now discover and exploit…",
      "tags": ["security", "ai-agents", "vulnerability", "open-source", "exploit"],
      "type": "news",
      "relevance": 9,
      "published": "2026-08-28",
      "takeaways": ["…", "…", "…"],
      "created_at": "2026-08-30T21:41:37.034678+00:00",
      "updated_at": "2026-08-30T21:41:37.034678+00:00"
    }
  ],
  "next_cursor": "eyJjYXJkX2lkIjoiOTgzMTAyYjNlYTNiNDM0MCIsImdzaV9wayI6IkNBUkQiLCJnc2lfc2siOiIwMDkjMjAyNi0wOC0yOCJ9"
}
```

### `docs/api/feed-api.v1.schema.json` — the generation input

The committed artifact's `required` lists are **shorter than the property
lists**, because `tags`, `takeaways` (Pydantic `default_factory=list`) and
`next_cursor` (`= None`) carry defaults:

| Object | `required` | Optional properties |
|---|---|---|
| `FeedResponse` | `["cards"]` | `next_cursor` (`string \| null`, default `null`) |
| `$defs.CardOut` | `card_id, title, url, source, summary, type, relevance, published, created_at, updated_at` | `tags` (`string[]`), `takeaways` (`string[]`) |

**Consequence, and it is load-bearing:** generated TypeScript types those three
as `?:`. The deployed server always emits them, but the *contract* does not
promise them, so the UI tolerates `undefined`. Hand-editing the generated file
to "fix" this would be the exact drift this spec exists to prevent.

### Next.js 16 (verified against the v16 docs)

```tsx
// searchParams is a Promise in the App Router (Next 15+).
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
  const { tag } = await searchParams
}
```

- `fetch` is **not** cached by default (`cache: 'auto no cache'`); a route that
  reads `searchParams` is dynamic. Explicit caching is
  `fetch(url, { next: { revalidate: <seconds> } })`.
- **`next lint` was removed in Next 16**, and `next.config`'s `eslint` option
  with it. Linting is `"lint": "eslint"` against a flat `eslint.config.mjs`
  importing `eslint-config-next/core-web-vitals`.
- `create-next-app` supports `--no-*` negation of default flags (`--no-tailwind`,
  `--no-src-dir`, `--no-agents-md`), plus `--use-npm`, `--disable-git`,
  `--app`, `--ts`, `--eslint`, `--import-alias`.

### `json-schema-to-typescript` (verified)

```ts
compileFromFile(filename: string, options?: Partial<Options>): Promise<string>
```

`options.additionalProperties` **defaults to `true`**, which injects
`[k: string]: unknown` index signatures into every generated interface — that
would silently make the generated types accept fields the API never returns, so
this spec pins `additionalProperties: false`.

### Vitest 4 (verified)

```ts
// vitest.config.mts
export default defineConfig({
  test: { environment: 'jsdom', setupFiles: ['./vitest.setup.ts'] },
})
```

## Architecture decisions

### AD-1 — The app lives at `apps/web/`, not `apps/web-feed-ui/` (DECIDED)

`architecture-principles.md` boundary 2 names the future monorepo layout by
name: *"`packages/contracts` in a future monorepo: `apps/curation`, `apps/api`,
`apps/web`"*. `apps/web` is that directory, arriving first. `web-feed-ui` is the
name of the **spec**, not of the deployable — Phase 3's chat UI will live in the
same app (a second route), and renaming a deployed Vercel project's root
directory later is gratuitous churn.

The Python backend is **not** moved into `apps/curation` / `apps/api` by this
spec. That restructure touches `Dockerfile`, `Dockerfile.feed_api`, `infra/`,
`pyproject.toml`, every entrypoint's `sys.path` insert, and a deployed image —
enormous blast radius, zero benefit to this feature. `apps/web/` is additive:
nothing existing moves.

This is a deferral, not a rejection: `architecture-principles.md`'s named
layout (`apps/curation`, `apps/api`, `apps/web`) is still the eventual target,
and a future spec remains free to propose the Python-side move on its own
merits, once it has a concrete trigger — this spec just isn't that trigger.

### AD-2 — Package manager: **npm**, one lockfile, no workspaces (DECIDED)

| Option | Verdict |
|---|---|
| **npm** | **CHOSEN.** Already installed (npm 11.13.0 with Node 24.16.0 — verified on this machine), zero bootstrap step, `package-lock.json` is the format Vercel detects with no configuration, and the repo already assumes global npm for one tool (`npm install -g aws-cdk`, README). |
| pnpm | Rejected: faster and stricter, but adds a corepack/version pin the human must reproduce locally *and* on Vercel, and its symlinked `node_modules` occasionally needs `node-linker` tweaks for serverless bundlers. All cost, no benefit for one app. |
| yarn / bun | Rejected: no advantage here; bun additionally is not the default Vercel build runtime. |

No workspaces, no root `package.json`, no Turborepo/Nx. `apps/web/` is a
self-contained npm project; `uv` remains the only Python tool and never learns
about Node. This mirrors the existing split where `cdk` (a Node CLI) is
installed globally and `uv` owns Python — two toolchains, no bridge.

### AD-3 — Types are **generated** from the schema artifact, and drift-tested (DECIDED)

The brief left this to the architect ("generate if a schema exists, otherwise
hand-author and note the risk"). Spec 01 committed
`docs/api/feed-api.v1.schema.json` *explicitly for this consumer*, so generation
is available and chosen:

```
docs/api/feed-api.v1.schema.json  ──(npm run generate:types)──►  apps/web/features/feed/types.generated.ts
```

- `apps/web/scripts/generate-api-types.mjs` calls `compileFromFile(..., {
  additionalProperties: false, bannerComment: <DO NOT EDIT header> })` — the
  exact mirror of `export_api_schema.py` on the Python side.
- The generated file is **committed** (so `next build` and Vercel never need the
  schema, which sits outside the Vercel Root Directory), and
  `features/feed/types.generated.test.ts` regenerates in-memory and fails on any
  difference — the mirror of
  `tests/test_feed_api_contract.py::test_schema_artifact_matches_models`.
- A second test asserts the generated field-name sets equal the artifact's
  `properties` keys, so the failure message names the drifting field rather than
  dumping a whole file diff.

Hand-authoring was rejected: the phase brief calls drift between Spec 01 and
Spec 02 "the main risk of splitting API and UI into separate specs", and a
hand-written interface makes parity a review promise instead of a build failure.

### AD-4 — All fetching is **server-side**; `FEED_API_BASE_URL` is server-only (DECIDED)

The page is an async Server Component that `fetch`es `feed-api` from Vercel's
server and ships HTML. There is **no** `NEXT_PUBLIC_*` variable and no
`"use client"` component that talks to the API.

Consequences, stated honestly:

- **The browser never issues a cross-origin request to `feed-api` in Phase 2, so
  CORS is not actually exercised by this app.** CORS is a browser mechanism;
  server-to-server `fetch` ignores it entirely.
- The CORS allow-list update (intent Goal 9) is still performed, for three
  reasons: the phase's Definition of Done requires the allow-list to reflect
  reality; Phase 3's chat UI (streaming, likely client-side) and any future
  "load more" button *will* need it; and it costs one `cdk deploy -c`.
  It is verified by `curl -H "Origin: …"`, which the brief explicitly permits.
- Local development works today with **no** `feed-api` change, because
  `http://localhost:3000` is already the sole allowed origin — and, per AD-4,
  even that is not strictly needed, since `next dev`'s fetch is server-side too.

Rejected alternative: exposing `NEXT_PUBLIC_FEED_API_BASE_URL` and fetching from
the browser. It would make CORS load-bearing (satisfying the acceptance
criterion more literally) at the cost of an empty-shell first paint — which the
brief forbids — plus client JS, a loading state, and a second failure mode.

### AD-5 — Pagination is **URL cursor links**, not client-side "load more" (DECIDED)

Each page is its own URL: `/?tag=<t>&cursor=<opaque>`. "Next page →" is a
`<Link>` carrying the cursor **verbatim** (URL-encoded in transit, byte-identical
in value). Browser Back works for free; every page is server-rendered,
shareable, and crawlable; there is zero client state.

Rejected: an accumulating "Load more" button. It needs `"use client"`, client
fetch (reversing AD-4), a growing in-memory list, and a scroll-restoration
story — for a 5-page feed. Cursor semantics are respected either way; this way
costs nothing.

**Nothing in the UI parses, decodes, constructs, or compares cursors** — Spec
01's Guarantee 5 says the token is opaque, and this spec treats it as bytes.

### AD-6 — Empty-but-cursored pages are **drained**, bounded to 5 requests (DECIDED)

Spec 01's Guarantee 4 (`FilterExpression` applies after `Limit`) is live:
`?tag=zzz-no-such-tag&limit=5` returns zero cards **and** a cursor. Spec 01's own
`tasks.md` lists "a short filtered page is misread as 'end of feed' by Spec 02"
as a Medium/Medium risk. The mitigation lives here:

`loadFeed()` follows `next_cursor` while `cards.length === 0 && nextCursor !==
null`, up to `MAX_DRAIN_REQUESTS = 5` requests total, then renders what it has.

- 5 × 20 = 100 ≥ the entire 87-card corpus, so today a rare tag is always found
  within the cap.
- The cap exists so a pathological filter cannot turn one page view into an
  unbounded request fan-out against a request-billed API (`feed-api` AD-7's
  documented residual cost risk).
- If the cap is hit with zero cards and a live cursor, the UI says so honestly
  *and still renders the "next page" link* — it never claims "no matches" for a
  page it did not read.

Rejected: draining until non-empty with no cap (unbounded cost), and not
draining at all (the documented misreading, and a bad UX for any tag whose
matches start on page 2).

### AD-7 — Styling: **CSS Modules**, using the committed design-token deliverables (DECIDED, revised 2026-09-18)

Next has built-in CSS Modules support: zero dependencies, zero config, no
PostCSS/Tailwind/`content` globs to maintain, and no class-name soup in the
markup. The app is one route and four components; the per-type colour accents
port `src/shared/cards.py`'s `_TYPE_COLOR` map (`paper` magenta, `release`
green, `project` cyan, `news` yellow, `concept` blue) into CSS custom
properties. That literal is **duplicated across a language boundary** — it
cannot be imported and cannot be drift-tested, exactly as `feed-api` AD-4's
literals are duplicated across a toolchain boundary. Unlike those, drift here is
purely cosmetic (an unknown type falls back to a neutral accent), so no test
guards it; the duplication is called out in a code comment.

**Revision, 2026-09-18:** two hand-authored design deliverables were added to
`specs/web-feed-ui/claude-design-outputs/` — `tokens.css` (light/dark colour
palette via `[data-theme]` and `prefers-color-scheme`, the spacing/radius/type
scales, the five per-type accents plus a neutral fallback, and an
`--accent-danger` for error states) and `feed.module.css` (concrete class
names for every component in this contract, keyed to the `data-testid`s below).
These supersede the "port the map by hand" plan above with pinned values and
names. They are copied **verbatim**, not redesigned:

```
specs/web-feed-ui/claude-design-outputs/tokens.css        →  apps/web/app/globals.css
specs/web-feed-ui/claude-design-outputs/feed.module.css   →  apps/web/features/feed/feed.module.css
```

No hand-authored CSS introduces a colour, spacing, or radius value outside
these two files' custom properties. The per-type accent is applied by a
`data-type` attribute on the card's root element (`.card[data-type="paper"]`
etc. in `feed.module.css`) — `card-item.tsx` sets the attribute and writes no
colour-mapping logic of its own; an unrecognised `type` matches no selector and
falls through to `.card`'s own `--accent: var(--accent-neutral)` default, so
the neutral-fallback behaviour above is unchanged, now enforced by CSS rather
than a TypeScript helper.

**The page-level background is set in `layout.tsx`, not in the copied CSS.**
`tokens.css` copied verbatim defines only custom properties and type-scale
classes — no `html`/`body` reset, so the viewport outside `.feedPage`'s
centered 46rem column would otherwise stay browser-default white (visibly
wrong in dark mode). Rather than hand-add a reset block to the otherwise
verbatim `globals.css` — which would blur the "these two files, nothing
hand-authored outside their tokens" rule above — `app/layout.tsx` sets the
`<body>` background/text/font directly from the same custom properties:

```tsx
<body style={{ margin: 0, background: 'var(--surface-page)', color: 'var(--ink)', fontFamily: 'var(--font-sans)' }}>
```

This reads the identical tokens `feed.module.css`'s `.feedPage` already reads
(no new value invented), keeps both design files byte-verbatim copies, and
keeps the one hand-authored line where it's visible and obviously
intentional — the root layout — rather than mixed into a "generated, don't
touch" file.

### AD-8 — Testing: Vitest + React Testing Library on the **synchronous** pieces (DECIDED)

Next's own guidance is that async Server Components are not unit-testable with
Jest/Vitest (they recommend E2E). Rather than fight that or add a browser
matrix, the design keeps `app/page.tsx` a ~25-line shell whose only job is:
read `searchParams` → `await loadFeed(...)` in a `try/catch` → render
`<FeedView state=… />`. **All branching lives in the synchronous, prop-driven
`FeedView`**, which is directly renderable and fully tested.

- `client.test.ts`, `load-feed.test.ts`, `href.test.ts`, `tags.test.ts` — node
  logic with a stubbed `globalThis.fetch`. No network, ever.
- `feed-view.test.tsx`, `card-item.test.tsx` — jsdom + RTL.
- `types.generated.test.ts` — the AD-3 drift guard.
- Playwright/Cypress: **rejected** (intent Non-Goal). The one thing unit tests
  cannot prove — that the real deployed page renders real cards — is a manual
  browser check in the runbook, which is also how every Phase 1 spec verified
  its live behaviour.

### AD-9 — Explicit `revalidate: 300` on the feed fetch (DECIDED)

Next 15/16 do not cache `fetch` by default, and a `searchParams`-reading route
is dynamic — so without an explicit option, **every page view is a fresh API
Gateway request**. `feed-api`'s AD-7 named request-count billing as its accepted
residual cost risk; this spec must not amplify it.

`fetch(url, { next: { revalidate: 300 } })` gives Next's Data Cache a 5-minute
TTL per distinct URL (i.e. per tag/cursor combination). Curation runs **once
daily**, so 5 minutes is far fresher than the data ever is, while collapsing a
burst of views/refreshes into one upstream request. One constant,
`REVALIDATE_SECONDS`, in one module.

> **Open question, to be settled by running it, not by argument (house style —
> see `feed-api` AD-6).** The fetch also passes `signal:
> AbortSignal.timeout(FETCH_TIMEOUT_MS)` so a hung API cannot hold a render open
> for API Gateway's full 30s. Whether an `AbortSignal` interacts badly with
> Next's Data Cache (i.e. silently disables caching for that request) is **not**
> settled by the docs. If `npm run build`/dev logs or a repeat-view check show
> the request is not being cached, drop `signal` — the Lambda's own 10s timeout
> plus API Gateway's 30s remain as bounds — and **record the finding in
> `audit.md`**. Both options are one line in one file; do not redesign around
> it.

### AD-10 — Deployment is a **human** step; the executor stops at "locally verified" (DECIDED)

By explicit instruction. No agent runs `vercel`, `vercel deploy`, `vercel link`,
or `cdk deploy`, and no task assumes a Vercel CLI or account exists. The
executor's definition of done is: production build, lint, typecheck, and tests
green in `apps/web`, plus one local browser smoke check against the real API.
`roadmap.md` Phase 5 is a **runbook**, written by the executor for the human,
with exact commands and exact expected output — it contains no checkboxes the
executor may tick itself.

### AD-11 — Tag chips are a projection of the fetched page, not a vocabulary (DECIDED)

There is no `/tags` endpoint and adding one would be a Spec 01 revision (intent
Non-Goal). With 281 distinct tags over 87 cards (verified live), a global chip
list would be unusable anyway. So:

- The chip row shows the **most frequent tags among the cards currently
  rendered**, capped at `MAX_TAG_CHIPS = 12`, ties broken alphabetically so the
  output is deterministic and testable.
- **Every tag on every card is itself a link**, so all 281 tags remain reachable
  even though only 12 are promoted.
- The active tag is always shown (even if absent from the current page) with a
  "clear filter" affordance.

The limitation — "these are the tags on this page, not all tags in the feed" —
is stated in the UI copy, not hidden. That copy is pinned, not paraphrased:
`feed.module.css`'s design mockup (`.chipNote`) fixes the exact string —

> Top tags on this page — every tag on a card is clickable.

— exported as a `CHIP_NOTE` constant from `tag-filter.tsx` so it is asserted
verbatim in `feed-view.test.tsx` (AD-8: `TagFilter` has no test file of its
own — it's exercised through `FeedView`) rather than left to the executor's
phrasing.

### AD-12 — Dark mode is **OS-preference only**; no toggle ships in Phase 2 (DECIDED, 2026-09-18)

`tokens.css` (AD-7) defines both an automatic path
(`@media (prefers-color-scheme: dark)`) and a manual override path
(`[data-theme="dark"]` / `[data-theme="light"]`). Phase 2 wires up **only** the
automatic path: `app/globals.css` gets the media query as-authored, and nothing
in the app ever sets a `data-theme` attribute. There is no toggle control, no
`"use client"` theme component, and no persisted preference.

- Building a toggle now would need client state and a persisted choice
  (`localStorage` or a cookie) to survive navigation between server-rendered
  pages — directly contradicting State Changes' existing "no cookies, no
  localStorage, no session, no client store" guarantee, for a control nobody
  has asked for.
- Leaving the `[data-theme]` selectors authored-but-unused in the copied CSS
  costs nothing (dead CSS, no runtime cost) and pre-paves a real toggle for a
  later phase without committing to build one now.
- If a future spec adds a toggle, it is additive to `tokens.css`'s existing
  selectors, not a rewrite.

### AD-13 — The masthead is static markup inside `FeedView`, not a component (DECIDED, 2026-09-18)

The design mockup's header (wordmark "AI RADAR" + tagline "curated AI news")
carries no props, no per-request data, and no state — it is identical on every
render. It is written as inline JSX at the top of `FeedView`'s output, styled
by `feed.module.css`'s `.masthead`/`.wordmark`/`.tagline` classes, rather than
factored into a fifth component:

- It keeps AD-7's "one route, four components" component count accurate — a
  fifth file for markup that never varies is a test file and an import for
  zero behaviour.
- It renders identically across all four `FeedView` states (list, empty,
  no-match, error) — the masthead is chrome around the state, not part of it,
  so it needs no `data-testid` of its own and no entry in Guarantee 10's
  exhaustive state list.
- The two strings are named constants (`WORDMARK`, `TAGLINE`) exported from
  `feed-view.tsx` so `feed-view.test.tsx` can assert their presence without
  hard-coding copy in the test.

## Interfaces

### `apps/web/features/feed/types.generated.ts` — CREATE (GENERATED, committed)

Written by `npm run generate:types`; never hand-edited. Expected shape (exact
formatting is whatever the generator emits — the committed file is its output
verbatim):

```ts
/* eslint-disable */
/**
 * GENERATED FILE — DO NOT EDIT.
 * Source: docs/api/feed-api.v1.schema.json (feed-api, CARD_SCHEMA_VERSION "v1")
 * Regenerate with: npm run generate:types
 */

export interface FeedResponse {
  cards: CardOut[]
  next_cursor?: string | null
}

export interface CardOut {
  card_id: string
  title: string
  url: string
  source: string
  summary: string
  tags?: string[]
  type: string
  relevance: number
  published: string
  takeaways?: string[]
  created_at: string
  updated_at: string
}
```

### `apps/web/scripts/generate-api-types.mjs` — CREATE

```js
// Mirror of export_api_schema.py: one script, one committed artifact, one drift test.
import { writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { compileFromFile } from 'json-schema-to-typescript'

const here = dirname(fileURLToPath(import.meta.url))            // apps/web/scripts
const SCHEMA = join(here, '../../../docs/api/feed-api.v1.schema.json')
const OUT = join(here, '../features/feed/types.generated.ts')

export const BANNER = `/* eslint-disable */
/**
 * GENERATED FILE — DO NOT EDIT.
 * Source: docs/api/feed-api.v1.schema.json (feed-api, CARD_SCHEMA_VERSION "v1")
 * Regenerate with: npm run generate:types
 */`

export async function generate() {
  // additionalProperties defaults to TRUE and would inject `[k: string]: unknown`
  // index signatures, making the types accept fields the API never returns.
  return compileFromFile(SCHEMA, { additionalProperties: false, bannerComment: BANNER })
}

if (import.meta.url === `file://${process.argv[1]}`) {
  writeFileSync(OUT, await generate())
}
```

### `apps/web/features/feed/client.ts` — CREATE (the only module that calls `fetch`)

```ts
import type { CardOut, FeedResponse } from './types.generated'

/** Page size requested from feed-api. Its own default is also 20; pinned here
 *  so the drain budget (AD-6) is computable. */
export const PAGE_SIZE = 20
/** Next Data Cache TTL (AD-9). Curation runs daily; 5 min is always fresher. */
export const REVALIDATE_SECONDS = 300
export const FETCH_TIMEOUT_MS = 8_000

/** The artifact's `$defs.CardOut.required`, minus the one numeric field.
 *  A test asserts this list against docs/api/feed-api.v1.schema.json. */
export const REQUIRED_STRING_FIELDS = [
  'card_id', 'title', 'url', 'source', 'summary',
  'type', 'published', 'created_at', 'updated_at',
] as const

export type FeedErrorCode = 'config' | 'network' | 'http' | 'malformed'

export class FeedApiError extends Error {
  readonly code: FeedErrorCode
  readonly status?: number
  constructor(code: FeedErrorCode, message: string, status?: number)
}

export interface FetchFeedParams {
  tag?: string
  /** Opaque token from a previous `next_cursor`. Passed through verbatim. */
  cursor?: string
  limit?: number
}

/** One card page, normalised: `next_cursor` collapsed to `string | null`,
 *  malformed cards dropped and counted (house rule: one bad item never kills
 *  the page — mirrors `query_feed`'s per-item skip in src/api/feed.py). */
export interface FeedPage {
  cards: CardOut[]
  nextCursor: string | null
  /** Cards the API returned that failed `isCardOut` and were dropped. */
  skipped: number
  /** How many HTTP requests produced this page (1, or more after a drain). */
  requests: number
}

/** Runtime shape check at the network boundary. Types are erased at runtime, so
 *  this is what actually protects the render from a contract violation. */
export function isCardOut(value: unknown): value is CardOut

/** Reads FEED_API_BASE_URL (server-only, never NEXT_PUBLIC_*). Throws
 *  FeedApiError('config') naming the variable when unset/blank — the
 *  pydantic-settings posture, in TypeScript. */
export function feedApiBaseUrl(): string

/**
 * Exactly ONE `GET /v1/cards` request. No retry, no loop, no second call.
 * `cursor` is appended verbatim (URL-encoded in transit only).
 * Caching: `{ next: { revalidate: REVALIDATE_SECONDS } }` (AD-9).
 * Throws FeedApiError for config/network/http/malformed; never returns
 * a partially-typed body.
 */
export async function fetchFeed(params?: FetchFeedParams): Promise<FeedPage>
```

### `apps/web/features/feed/load-feed.ts` — CREATE (the AD-6 drain)

```ts
import { fetchFeed, type FeedPage } from './client'

/** Bounded so a pathological filter cannot fan one page view into unbounded
 *  billed requests (AD-6). 5 x PAGE_SIZE(20) = 100 > the 87-card corpus. */
export const MAX_DRAIN_REQUESTS = 5

export interface LoadFeedParams {
  tag?: string
  cursor?: string
}

/**
 * `fetchFeed`, plus Spec 01 Guarantee 4 handling: while the page came back
 * EMPTY and `nextCursor` is non-null, follow the cursor — up to
 * MAX_DRAIN_REQUESTS requests in total. Returns the first non-empty page, or
 * the last empty one (with its cursor intact, so the UI can still offer "next
 * page" and must not claim "no matches" for pages it never read).
 *
 * A non-empty short page is returned immediately: shortness is normal and is
 * never drained.
 */
export async function loadFeed(params?: LoadFeedParams): Promise<FeedPage>
```

### `apps/web/features/feed/href.ts` — CREATE (the only place a feed URL is built)

```ts
export interface FeedHrefParams {
  tag?: string | null
  cursor?: string | null
}

/** `/` , `/?tag=agents`, `/?tag=agents&cursor=<encoded>`. Empty/nullish values
 *  are omitted entirely (never `?tag=`). The cursor value is passed through
 *  URLSearchParams untouched — encoded for transit, identical in value. */
export function feedHref(params?: FeedHrefParams): string
```

### `apps/web/features/feed/tags.ts` — CREATE

```ts
import type { CardOut } from './types.generated'

export const MAX_TAG_CHIPS = 12

/** The most frequent tags among `cards`, descending by count, ties broken
 *  alphabetically (deterministic → testable). Cards with `tags === undefined`
 *  contribute nothing. Never invents a global vocabulary — there is no /tags
 *  endpoint (AD-11). */
export function topTags(cards: CardOut[], limit?: number): string[]
```

### `apps/web/features/feed/feed-view.tsx` — CREATE (every UI state, synchronous)

```tsx
import type { FeedErrorCode, FeedPage } from './client'

/** Static masthead copy (AD-13) — exported so feed-view.test.tsx can assert
 *  presence without hard-coding the strings in the test. */
export const WORDMARK = 'AI RADAR'
export const TAGLINE = 'curated AI news'

export type FeedViewState =
  | { status: 'ok'; page: FeedPage }
  | { status: 'error'; code: FeedErrorCode }

export interface FeedViewProps {
  state: FeedViewState
  /** The active tag filter, or undefined for the unfiltered feed. */
  tag?: string
  /** The cursor this page was rendered from (undefined on the first page). */
  cursor?: string
}

/**
 * Renders the static masthead (AD-13; `.masthead`/`.wordmark`/`.tagline` from
 * feed.module.css), then exactly one of four things, each with a stable
 * `data-testid`:
 *   'feed-list'      — one or more cards (in API order; never re-sorted)
 *   'feed-empty'     — no cards, no tag, cursor exhausted  ("no cards yet")
 *   'feed-no-match'  — no cards, a tag is active           ("no cards tagged X")
 *   'feed-error'     — state.status === 'error'
 * The masthead renders identically across all four states. Pagination and the
 * tag chip row render alongside 'feed-list'/'feed-no-match' whenever a next
 * cursor exists.
 */
export function FeedView(props: FeedViewProps): React.ReactElement
```

### `apps/web/features/feed/card-item.tsx` — CREATE

```tsx
import type { CardOut } from './types.generated'

/**
 * The HTML port of `render()` in src/shared/cards.py: title (linking out to
 * card.url, target=_blank rel="noopener noreferrer"), summary, bulleted
 * takeaways, clickable tag chips, and a meta line
 * `TYPE · relevance n/10 · source · published`.
 * `tags`/`takeaways` are OPTIONAL in the v1 schema — `undefined` renders as
 * nothing, never as a crash.
 * The root element carries `data-type={card.type}` — feed.module.css's
 * `.card[data-type="…"]` selectors (AD-7) apply the accent colour; this
 * component performs no colour lookup of its own, and an unrecognised type
 * simply matches no selector (neutral fallback, by CSS default).
 */
export function CardItem({ card }: { card: CardOut }): React.ReactElement
```

### `apps/web/features/feed/tag-filter.tsx` + `pagination.tsx` — CREATE

```tsx
/** Pinned mockup copy (AD-11) — asserted verbatim, not paraphrased. */
export const CHIP_NOTE = 'Top tags on this page — every tag on a card is clickable.'

export function TagFilter(props: {
  cards: CardOut[]
  activeTag?: string
}): React.ReactElement

export function Pagination(props: {
  tag?: string
  cursor?: string
  nextCursor: string | null
}): React.ReactElement
```

`TagFilter` renders `topTags(cards)` as `<Link href={feedHref({ tag })}>`
chips, the `CHIP_NOTE` line (`.chipNote` in `feed.module.css`), plus, when
`activeTag` is set, an "All cards" clear link.
`Pagination` renders "Next page →" `<Link href={feedHref({ tag, cursor:
nextCursor })}>` **iff** `nextCursor !== null`, and "← First page" iff `cursor`
is set. No page numbers (cursor pagination has none) and no "Previous" link —
browser Back is the previous page, by construction (AD-5).

### `apps/web/app/page.tsx` — CREATE (the thin async shell, AD-8)

```tsx
import { FeedApiError } from '../features/feed/client'
import { loadFeed } from '../features/feed/load-feed'
import { FeedView, type FeedViewState } from '../features/feed/feed-view'

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
  const params = await searchParams
  const tag = typeof params.tag === 'string' && params.tag.trim() ? params.tag : undefined
  const cursor = typeof params.cursor === 'string' && params.cursor ? params.cursor : undefined

  let state: FeedViewState
  try {
    state = { status: 'ok', page: await loadFeed({ tag, cursor }) }
  } catch (error) {
    // Structured, single-line log — the idiom of src/api/handler.py's
    // `feed_api_request` record. The message never reaches the browser.
    console.error(JSON.stringify({
      event: 'feed_fetch_failed',
      code: error instanceof FeedApiError ? error.code : 'network',
      status: error instanceof FeedApiError ? error.status : undefined,
      tag, has_cursor: cursor !== undefined,
    }))
    state = { status: 'error', code: error instanceof FeedApiError ? error.code : 'network' }
  }

  return <FeedView state={state} tag={tag} cursor={cursor} />
}
```

### `apps/web/package.json` — CREATE (scripts pinned; deps per Dependencies below)

```jsonc
{
  "name": "ai-radar-web",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint",                       // `next lint` no longer exists (Next 16)
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest",
    "generate:types": "node scripts/generate-api-types.mjs"
  }
}
```

### `apps/web/.env.example` — CREATE

```bash
# Base URL of the deployed feed-api (Phase 2, spec `feed-api`) — NO trailing
# slash, NO path. The app appends /v1/cards itself.
#
# SERVER-ONLY on purpose (AD-4): every fetch happens in a Server Component, so
# this must NOT be prefixed NEXT_PUBLIC_ and must never be read from a
# "use client" module.
#
# Local dev: copy to .env.local (gitignored) and keep this value.
# Vercel: set the same key in Project Settings -> Environment Variables.
FEED_API_BASE_URL=https://fdcksuokyh.execute-api.us-east-1.amazonaws.com
```

## Data Models

No new domain model. The UI's only model is the **generated** `CardOut` /
`FeedResponse` — deliberately not re-shaped, renamed, or wrapped (no `Article`,
no `FeedItemViewModel`, no `toCard()` mapper). Two small local types exist and
both are transport concerns, not domain concepts:

| Type | Where | Why it exists (and why it is not a domain layer) |
|---|---|---|
| `FeedPage` | `client.ts` | Normalises one HTTP response: `next_cursor?: string \| null` → `nextCursor: string \| null`, plus `skipped`/`requests` counters. Same name and role as `FeedPage` in `src/api/feed.py` — ubiquitous language, not a new concept. |
| `FeedViewState` | `feed-view.tsx` | A two-arm discriminated union (`ok` / `error`) so the render is exhaustive. Pure presentation. |

### Field rendering map (`CardOut` → UI)

| Field | Rendered as | Notes |
|---|---|---|
| `title` | card heading, links to `url` | `target="_blank" rel="noopener noreferrer"` |
| `url` | the heading's `href` + a visible link line | never rewritten or proxied |
| `source` | meta line | e.g. `arXiv cs.AI`, `Simon Willison`, `Tavily: general` |
| `summary` | body paragraph | rendered as text; **no HTML/markdown interpretation** |
| `takeaways` | bulleted list | optional — `undefined`/`[]` renders nothing |
| `tags` | chip links to `/?tag=<tag>` | optional — `undefined`/`[]` renders nothing |
| `type` | meta badge + accent colour | `_TYPE_COLOR` port (AD-7); unknown type → neutral accent, never a crash |
| `relevance` | meta line `relevance n/10` | number as returned; never recomputed |
| `published` | `<time>` element | `""` (a real possibility per Spec 01) renders `date n/a`, mirroring `cards.py` |
| `card_id` | React `key` only | not displayed |
| `created_at` / `updated_at` | not displayed in Phase 2 | present in the type; no per-card detail page exists to show them |

## State Changes

None to any existing runtime state, in either plane. This spec adds a
**read-only HTTP client** of an already-deployed public endpoint.

- No AWS resource is created. The only AWS-side change in the whole spec is a
  **human-run** redeploy of the existing `AiRadarFeedApi` stack with a longer
  `allowed_origins` list — no new resource type, no new cost class.
- No DynamoDB access, no credentials, no IAM principal. The app has no AWS SDK
  and no AWS identity.
- New persistent state outside the repo: a Vercel project (free tier) and its
  `FEED_API_BASE_URL` environment variable. Torn down by deleting the project.
- In-app state: **the URL** (`?tag=`, `?cursor=`) plus Next's Data Cache
  (5-minute TTL, AD-9). No cookies, no localStorage, no session, no client
  store.

## Behavior Guarantees

1. **Server rendering.** The feed HTML is produced on the server; the initial
   response already contains the cards. No component marked `"use client"`
   fetches from `feed-api`, and no `NEXT_PUBLIC_*` variable exists
   (grep-asserted in tests).
2. **One request per `fetchFeed` call.** Exactly one `fetch` to
   `<base>/v1/cards`, with `limit` always present and `tag`/`cursor` present
   **iff** non-empty. No retry, no fan-out, no per-card request.
3. **Cursor opacity and verbatim round trip.** Any `cursor` sent equals the
   `next_cursor` previously received, byte for byte. The UI never parses,
   decodes, validates, mutates, or compares cursors, and never synthesises one.
4. **Order preservation.** Cards render in the exact order the API returned
   them. There is no `sort`, `reverse`, or comparator anywhere in
   `features/feed/` (asserted by test *and* by the render order of a
   deliberately non-alphabetical fixture).
5. **Short pages never end pagination.** "Next page" renders **iff**
   `nextCursor !== null`, independent of how many cards the page held —
   including zero.
6. **Empty-page drain (bounded).** While a page is empty and `nextCursor !==
   null`, `loadFeed` follows the cursor, to a hard maximum of
   `MAX_DRAIN_REQUESTS` (5) requests per render. It returns as soon as a page
   has ≥ 1 card. A non-empty page is **never** drained.
7. **"No matches" is only claimed for pages actually read.** If the drain cap is
   reached with zero cards and a live cursor, the copy says the search covered
   the first N pages and the "next page" link is still offered — the UI never
   asserts absence over unread pages.
8. **Per-card resilience.** A card in the response failing `isCardOut` is
   dropped and counted in `skipped`; the remaining cards still render 200-style,
   never an error page. (House rule, mirroring `query_feed`'s per-item skip.)
9. **Optional-field tolerance.** `tags`, `takeaways`, and `next_cursor` being
   `undefined` (they are optional in the v1 artifact) renders correctly:
   respectively no chips, no bullets, and "no next page". No `.map` of
   `undefined`, no `undefined` printed to the DOM.
10. **Four distinct, exhaustive states.** Exactly one of `feed-list`,
    `feed-empty`, `feed-no-match`, `feed-error` renders per request, each with
    a stable `data-testid` and distinct human-readable copy. A blank page is not
    a reachable state.
11. **Errors never escape to the user.** Every failure path
    (`config`/`network`/`http`/`malformed`) is caught in `page.tsx`, logged as
    one structured `feed_fetch_failed` JSON line server-side, and rendered as
    `feed-error`. The error message, stack, base URL, and status code are
    **not** shown in the browser.
12. **Config failure is named and non-fatal to the build.** A missing/blank
    `FEED_API_BASE_URL` throws `FeedApiError('config')` **at request time**
    naming the variable — it does not throw at import time, so `npm run build`
    and `vercel build` succeed without the variable present.
13. **Contract parity (the load-bearing one).** `types.generated.ts` is exactly
    what `npm run generate:types` produces from
    `docs/api/feed-api.v1.schema.json`; a test regenerates and fails on any
    difference, and a second test asserts the interfaces' field-name sets equal
    the artifact's `properties` keys. Any Spec 01 schema change therefore breaks
    this suite loudly rather than drifting silently.
14. **The runtime guard is derived from the artifact, not from memory.**
    `REQUIRED_STRING_FIELDS` equals `$defs.CardOut.required` minus `relevance`,
    asserted against the artifact JSON in a test.
15. **Tag filtering is a real server round trip.** Selecting a tag navigates to
    a new URL whose render issues `GET /v1/cards?tag=…`. There is no client-side
    `filter()` over an already-fetched page anywhere in `features/feed/`.
16. **Bounded upstream cost per view.** A page view issues at most
    `MAX_DRAIN_REQUESTS` (5) upstream requests, normally 1, and repeat views of
    the same URL within `REVALIDATE_SECONDS` (300) may issue none. No polling,
    no interval, no client refetch.
17. **No secrets or infrastructure detail reach the client bundle.**
    `FEED_API_BASE_URL` is read only in server modules; the string
    `execute-api` appears nowhere in `apps/web` application code (only in
    `.env.example`/docs).
18. **Offline, hermetic tests.** `npm test` stubs `globalThis.fetch` and touches
    no network, no AWS, no browser download, and no Docker. `uv run pytest
    tests/` is unaffected and unchanged.
19. **Zero backend change.** No file under `src/`, `tests/`, `infra/`,
    `docs/api/`, `pyproject.toml`, `uv.lock`, or either `Dockerfile` is
    modified by the executor. The `feed-api` CORS edit is a human step and, when
    it happens, changes exactly one constant plus a redeploy.
20. **Progressive enhancement.** Filtering and pagination are plain links; the
    feed is fully usable with JavaScript disabled.

## Error Handling Contract

| Error condition | Behavior | User impact |
|---|---|---|
| `FEED_API_BASE_URL` unset/blank | `FeedApiError('config', "FEED_API_BASE_URL is not set")` thrown **before** any fetch; logged server-side | `feed-error` state: "The feed is temporarily unavailable." + retry link. No variable name, no stack shown |
| DNS/TCP failure, TLS error, or `AbortSignal.timeout` (8s) | `fetch` rejects → `FeedApiError('network')` | same `feed-error` state |
| `400 invalid_cursor` (a stale/hand-edited `?cursor=`) | `FeedApiError('http', …, 400)` | `feed-error` state whose copy offers **"Back to the first page"** (`feedHref({ tag })`) — the recovery Spec 01's error table anticipates |
| `400 invalid_limit` | `FeedApiError('http', …, 400)` | `feed-error`. Should be unreachable: `limit` is a pinned constant, never user input |
| `429` (stage throttling, `feed-api` AD-7) or `5xx` | `FeedApiError('http', …, status)` | `feed-error` + retry link. **No automatic retry** — retrying a throttled, request-billed API is the failure mode AD-7 warns about |
| Body is not JSON, not an object, or `cards` is not an array | `FeedApiError('malformed')` | `feed-error` |
| One card fails `isCardOut` | dropped, `skipped += 1`, logged once per page | that card is missing; everything else renders |
| Page empty, `next_cursor` non-null | drained up to 5 requests (AD-6) | usually invisible; the matching cards simply appear |
| Drain cap hit, still zero cards | render `feed-no-match` (or `feed-empty`) with "searched the first N pages" copy **and** the next-page link | honest partial answer, never a false "nothing found" |
| Tag genuinely has no matches (cursor exhausted) | `feed-no-match`: "No cards tagged `X`." + "All cards" clear link | dead end with an exit |
| Feed genuinely empty, no tag | `feed-empty`: "No cards yet — the curation run hasn't produced any." | explains itself |
| `?tag=` blank/whitespace | treated as absent (mirrors the handler's own rule) | unfiltered feed |
| `?tag=` repeated (`?tag=a&tag=b`) | `searchParams` yields `string[]`; non-string → treated as absent | unfiltered feed, no crash |
| Unknown query params (`?foo=1`) | ignored | normal feed |
| An unexpected exception anywhere in `loadFeed` | caught by `page.tsx`'s `catch`, coded `network` | `feed-error`; the Next error overlay/500 is never reached |

## Dependencies

**Runtime (production)**
- `next` ^16 · `react` ^19 · `react-dom` ^19 — the framework. Node ≥ 20.9
  (dev machine: Node 24.16.0, npm 11.13.0).

**Dev**
- `typescript` ^5, `@types/node`, `@types/react`, `@types/react-dom`
- `eslint` ^9 + `eslint-config-next` (flat config; `next lint` is gone in 16)
- `vitest` ^4, `@vitejs/plugin-react`, `jsdom`
- `@testing-library/react`, `@testing-library/jest-dom`
- `json-schema-to-typescript` — **dev-only**: codegen runs locally, never at
  build time, so the schema file's location outside the Vercel Root Directory
  is irrelevant.

**Deliberately absent**: any CSS framework, UI kit, icon pack, data-fetching or
state library, HTTP client (`fetch` is built in), date library (`published` is
already a display-ready ISO date), analytics/monitoring SDK, AWS SDK,
Playwright/Cypress. `tokens.css` and `feed.module.css` (AD-7) are hand-authored
design tokens and CSS Modules, copied in verbatim from
`specs/web-feed-ui/claude-design-outputs/` — not a package, not a framework,
nothing to add to `package.json`.

**External services**: the deployed `feed-api` (read-only, unauthenticated) and
Vercel's free tier. No new AWS resource, no new recurring cost.

**Internal (consumed, never imported as code)**:
`docs/api/feed-api.v1.schema.json` — read at codegen and test time only, by
relative path from `apps/web/`.

## Integration Points

- **`feed-api` (Spec 01, deployed)** — the sole data source. This spec consumes
  `GET /v1/cards` v1 as-is: honours Guarantee 4 (AD-6), Guarantee 5 (AD-5), the
  400 contract (error table above), and Guarantee 13 (AD-3's drift test is the
  client-side half of that guarantee). It requests nothing new and adds no
  second read path.
- **`feed-api` CORS (human step)** — Spec 01's contract names this spec as the
  closer: `infra/lib/feed_api.py`'s `DEFAULT_ALLOWED_ORIGINS` (currently
  `["http://localhost:3000"]`, with the comment *"Spec 02 adds the Vercel
  origin"*) or `cdk deploy AiRadarFeedApi -c
  feed_api_allowed_origins=http://localhost:3000,https://<vercel-url>`. Note
  `FeedApiStack` also reads `feed_api_reserved_concurrency`; the redeploy must
  keep whatever override the human's current bridge state requires (see
  `specs/feed-api/tasks.md` Task 6.2 and AWS Support case 178836416700301) or it
  will fail for an unrelated reason.
- **`docs/api/feed-api.v1.schema.json`** — read-only input to codegen. If Spec
  01 ever bumps to `v2`, this app's drift test fails first, which is the
  intended coupling.
- **Phase 3 (RAG chat UI)** — will add a route to **this same app** (AD-1),
  reusing its shell, npm project, test setup, and Vercel project. It is the
  consumer that will actually need the browser-side CORS grant this spec puts in
  place.
- **`AiRadarBudget` (Phase 1)** — unchanged. The frontend adds no AWS spend;
  its only upstream effect is API Gateway request count, bounded by AD-6 and
  damped by AD-9.
- **README.md** — gains a `web-feed-ui` row in the Phase 2 table plus a local-dev
  section and the manual Vercel + CORS runbook (`roadmap.md` Phase 5).

> **Honest limitations, accepted and written down.**
> 1. **CORS is not exercised by this app** (AD-4) — the allow-list update is
>    forward-looking hygiene verified by curl, not by the app's own traffic.
> 2. **Tag chips are page-local** (AD-11) — 281 tags exist; 12 are promoted per
>    page, and the rest are reachable only through a card that carries them.
> 3. **No "previous page" link** — cursor pagination is forward-only; browser
>    Back is the answer, and each page is its own URL so that works.
> 4. **Cards can shift mid-pagination** — Spec 01's own closing note: a curation
>    run rewrites `gsi_sk`, so a card may be seen twice or missed across pages.
>    Inherited, not introduced; one write burst per day makes it negligible.
> 5. **The async page shell is not unit-tested** (AD-8) — its ~25 lines are
>    covered by the manual browser check, and everything it delegates to is
>    tested directly.

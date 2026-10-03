# Intent: web-feed-ui

**Shipped: 2026-09-18**

## Problem Statement

`feed-api` (Phase 2, Spec 01) is deployed and live-verified: `GET
https://fdcksuokyh.execute-api.us-east-1.amazonaws.com/v1/cards` returns real,
sorted, cursor-paginated, tag-filterable cards out of `ai-radar-cards`. It is
still **JSON in a terminal**. Design §8's Phase 2 deliverable is *"I can open a
URL and **see** them"* — and nothing in this repo renders a card to a human in a
browser today. The Phase 0/1 `render()` in `src/shared/cards.py` prints rich
panels to a console; that is the entire UI the product has ever had.

This spec builds the missing half: a **Next.js (App Router) app**, deployed on
**Vercel's free tier**, that server-renders the curated feed — title, source,
summary, takeaways, tags, type, relevance, published date, link out — with a
tag filter and cursor pagination, reading exclusively through `feed-api`.

Three things make it more than "render a list":

1. **It is the repo's first frontend.** There is no `apps/` directory, no
   `package.json`, no Node toolchain anywhere. Every convention this spec sets
   (where the app lives, which package manager, how types are generated, how
   tests run) is the precedent Phase 3's chat UI will inherit.
2. **Contract drift is the real risk, not rendering.** Spec 01 and Spec 02 were
   deliberately split, so the TypeScript view of `CardOut`/`FeedResponse` can
   silently diverge from the Pydantic one. `feed-api` anticipated this and
   committed a JSON Schema artifact (`docs/api/feed-api.v1.schema.json`) for
   exactly this consumer. Parity must be **mechanical** (generated + drift
   tested), not a promise in prose.
3. **`feed-api`'s Guarantee 4 is a trap for a naive UI, and it is live right
   now.** *Verified against the deployed API this session:*
   `GET /v1/cards?tag=zzz-no-such-tag&limit=5` returns
   `{"cards": [], "next_cursor": "eyJjYXJkX2lkIjoi…"}` — an **empty page with a
   live cursor**, because DynamoDB applies the `FilterExpression` *after*
   `Limit`. A UI that reads "zero cards" as "no matches" will show "nothing
   found" for tags that genuinely have matches on page 3. Handling this is a
   design requirement, not an edge case.

Who is affected: the human who has 87 curated cards in DynamoDB and no way to
read them; Phase 3's chat UI, which will reuse this app's shell, typed client,
and deploy path; and `feed-api` itself, whose CORS allow-list still contains
only `http://localhost:3000` and must learn the real Vercel origin.

**Live facts this spec was designed against** (probed 2026-09-04, not assumed):
87 cards total, 281 distinct tags (long tail — `llm` 32, `agents` 16,
`interpretability` 8, most tags appear once), types `paper` 50 / `news` 26 /
`concept` 4 / `release` 4 / `project` 3, sources including `arXiv cs.AI`,
`Hugging Face Blog`, `Simon Willison`, `Tavily: general`. At the default page
size of 20 the feed is ~5 pages deep.

## Goals

1. **A server-rendered feed at a real URL.** An App Router page that fetches
   `GET /v1/cards` **on the server** and ships rendered HTML — never an empty
   shell that fetches from the browser as its primary path. Cards render in the
   order the API returned them (relevance desc, then published desc); the UI
   never re-sorts.
2. **A typed client generated from Spec 01's committed schema artifact.**
   `docs/api/feed-api.v1.schema.json` → a committed `types.generated.ts` via
   `json-schema-to-typescript`, plus a drift test that fails if the generated
   file and the artifact disagree — the TypeScript mirror of
   `tests/test_feed_api_contract.py`'s schema-drift test. Field-for-field parity
   is a **hard guarantee**, not a review item.
3. **Tag filtering that really re-queries the API.** Selecting a tag navigates
   to `/?tag=<x>`, which issues a new `GET /v1/cards?tag=<x>` — never a
   client-side filter of an already-fetched page. Tag chips are derived from the
   cards actually on screen (there is no `/tags` endpoint, by Spec 01 design)
   and every card's own tags are clickable, so any of the 281 tags is reachable.
4. **Cursor pagination that survives Guarantee 4.** Page links carry
   `?cursor=<opaque token>` verbatim; nothing in the UI parses, constructs, or
   offsets a cursor. An empty-but-cursored page is drained (bounded) rather than
   reported as "no matches", and a short page never ends pagination.
5. **Three distinct, sane, tested states**: empty feed, tag-with-no-matches, and
   `feed-api` unreachable/erroring. No blank page, no Next.js error overlay, no
   unhandled exception reaching the user.
6. **Feature-folder organization, no domain layers.** One `features/feed/`
   folder owning the feed's client, types, and components — flat modules, the
   same shape `src/api/` already has on the Python side. No aggregates, no
   repositories, no `services/`, no re-modelling of `Card` in the UI
   (`architecture-principles.md`: *"DDD is not a frontend pattern"*).
7. **Configuration, not hardcoding.** The API base URL comes from
   `FEED_API_BASE_URL`; the repo contains an `.env.example` documenting it and
   no committed literal URL in application code.
8. **The executor's work ends locally verified.** `npm run build`, `npm run
   lint`, `npx tsc --noEmit`, and `npm test` all green in `apps/web`, with a
   written, exact manual runbook for the human's Vercel deploy. **No agent runs
   `vercel deploy`, assumes Vercel CLI/account access, or `cdk deploy`s
   anything.**
9. **Close the CORS loop with Spec 01 (manual).** After the real Vercel origin
   exists, `feed-api`'s allow-list is updated
   (`infra/lib/feed_api.py`'s `DEFAULT_ALLOWED_ORIGINS` or
   `cdk deploy AiRadarFeedApi -c feed_api_allowed_origins=…`) and verified by
   curl — the exact step Spec 01's contract left for this spec.

## Success Criteria

**Executor-owned (automated, local, offline except the one live smoke check):**

- [ ] `apps/web` exists, builds (`npm run build` → exit 0), typechecks
      (`npx tsc --noEmit`), lints (`npm run lint` via the ESLint CLI — `next
      lint` no longer exists in Next 16), and tests (`npm test` → `vitest run`)
      green.
- [ ] `features/feed/types.generated.ts` is **generated** by `npm run
      generate:types` from `docs/api/feed-api.v1.schema.json`, committed, and a
      test fails if regenerating produces a different file.
- [ ] The generated `CardOut` has exactly the 12 fields of the artifact's
      `$defs.CardOut` — `card_id`, `title`, `url`, `source`, `summary`, `tags`,
      `type`, `relevance`, `published`, `takeaways`, `created_at`,
      `updated_at` — and `FeedResponse` exactly `cards` + `next_cursor`. A test
      asserts the field name set against the artifact JSON, so a Spec 01 bump
      breaks this suite loudly.
- [ ] `fetchFeed` builds exactly one request per call, with `tag`/`cursor`/
      `limit` as query parameters, and passes any `cursor` through **verbatim**
      (byte-identical to what the API returned) — asserted with a stubbed
      `fetch`.
- [ ] An empty page carrying a non-null `next_cursor` is followed, up to a
      bounded number of requests, before the UI concludes "no matches" — the
      live-verified `?tag=zzz-no-such-tag` shape is a test fixture.
- [ ] Rendering asserts, on a fixture page: cards appear **in API order** (no
      client sort), each card shows title/source/summary/tags/type/relevance/
      published and an external link to `card.url`, and `tags`/`takeaways`
      being `undefined` (they are optional in the artifact) renders as empty,
      not as a crash.
- [ ] Empty feed, tag-with-no-matches, and API-unreachable each render a
      **distinct** identifiable state, asserted by tests — not just described.
- [ ] No `NEXT_PUBLIC_*` variable exists and no `"use client"` component fetches
      from `feed-api` (grep-asserted): the browser never talks to the API
      directly in Phase 2.
- [ ] No hardcoded `execute-api.us-east-1.amazonaws.com` URL in `apps/web/**`
      application code (`.env.example`, README, and docs may name it).
- [ ] `apps/web/.env.example` documents `FEED_API_BASE_URL` with the real
      deployed value as its example.
- [ ] `uv run pytest tests/` still passes unchanged (349 passed) — this spec
      adds no Python code and modifies no Python file.
- [ ] `git diff` shows **zero** changes under `src/`, `infra/`, `tests/`,
      `Dockerfile*`, `pyproject.toml`, `uv.lock`, and
      `docs/api/feed-api.v1.schema.json`. The only repo-root modifications are
      `.gitignore`, `README.md`, and `CLAUDE.md`.
- [ ] **One live smoke check, read-only:** `npm run dev` (or `npm run start`
      after a build) against the real `FEED_API_BASE_URL` renders real cards
      from `ai-radar-cards` in a browser at `http://localhost:3000` — the
      already-allowed CORS origin, so nothing about `feed-api` has to change to
      do this.

**Human-owned (manual runbook, explicitly NOT executor tasks):**

- [ ] Vercel project created with Root Directory `apps/web` and
      `FEED_API_BASE_URL` set; a production deploy succeeds at a real URL.
- [ ] Loading that URL shows the **real, current** feed (not mock/seed data),
      sorted by relevance/date.
- [ ] Clicking a tag chip narrows the feed via a real `?tag=` API call; the
      "next page" link reaches cards beyond the first page with no duplicates
      and no gaps.
- [ ] `feed-api`'s CORS allow-list is updated to include the real Vercel origin
      and `cdk deploy AiRadarFeedApi` is re-run; a curl with
      `-H "Origin: https://<real-vercel-url>"` now returns
      `access-control-allow-origin: https://<real-vercel-url>` (it currently
      returns **no** `access-control-*` header for any origin other than
      `http://localhost:3000` — verified live 2026-09-04).
- [ ] The README's Phase 2 table and runbook record the real URL, the real
      origin, and the deploy/teardown steps.

## Non-Goals

- **Chat / RAG UI.** Phase 3. No Bedrock call, no `src/shared/chat.py` analogue,
  no streaming.
- **Auth, accounts, personalization, saved/favourited cards.** Phase 4.
  `architecture-principles.md`'s "users become entities" trigger stays unfired.
- **A per-card detail or permalink page.** Deferred by the phase README's
  scoping decision. Cards link **out** to the original `url`.
- **Any change to `feed-api`'s response contract, route, or query parameters.**
  This spec consumes `v1` as-is. If the UI needs a field or an endpoint the API
  does not have (a global tag vocabulary is the obvious candidate), that is a
  Spec 01 revision with a version bump — never a workaround here, and never a
  second read path around the API.
- **Any change to Python code.** No file under `src/`, `tests/`, `infra/`, and
  no `pyproject.toml`/`uv.lock` edit. `uv` remains a Python-only tool; `npm`
  never touches Python dependencies.
- **AWS-side hosting** (S3 + CloudFront, Amplify, Lambda@Edge). Vercel only, per
  the phase scoping decision — it keeps the frontend off the $500 credit.
- **A monorepo toolchain.** No npm/pnpm workspaces, no Turborepo, no Nx, no
  shared root `package.json`. One app, one lockfile, in one directory.
- **A component library, design system, or CSS framework** (Tailwind, shadcn,
  MUI). Four components do not need one.
- **A state-management library, data-fetching library, or ORM-of-the-frontend**
  (Redux, Zustand, TanStack Query, SWR). The server renders; the URL is the
  state.
- **E2E/browser-automation tests** (Playwright, Cypress). The states are covered
  by unit tests plus a documented manual browser check; adding a browser matrix
  to a 4-component app is exactly the speculative infrastructure this repo
  refuses elsewhere.
- **A domain layer in the UI.** No aggregates, repositories, domain events,
  `services/`, `entities/`, or a second `Card` model shaped for the UI.
  `architecture-principles.md` is explicit: *"The domain lives behind the API;
  do not mirror domain layers in the UI."*
- **Running `vercel deploy`, `vercel link`, or `cdk deploy` from an agent.** The
  deploy and the CORS redeploy are human steps by explicit instruction.
- **Analytics, Sentry, Vercel Speed Insights, or any third-party script.** No
  new vendor, no new cost line, no new privacy surface in Phase 2.

## Constraints

- **The API is live and immutable to this spec.** Base URL
  `https://fdcksuokyh.execute-api.us-east-1.amazonaws.com`, route
  `GET /v1/cards`, params `tag` / `limit` (1–100, default 20) / `cursor`.
  `?limit=0` → `400 {"error":"invalid_limit",…}`; a malformed cursor → `400
  {"error":"invalid_cursor",…}`. All verified live.
- **CORS today allows only `http://localhost:3000`**, and a non-allowed origin
  receives **no** `access-control-allow-origin` header at all (verified live).
  Local development therefore works out of the box on port 3000; the deployed
  origin does not, until the human runs the Spec 01 redeploy.
- **`feed-api` Guarantee 4 (filter-after-`Limit`) is real and reproducible.** A
  page may be short or empty while `next_cursor` is non-null. "Fewer than
  `limit`" never means "end of feed"; only `next_cursor === null` does.
- **`next_cursor`, `tags`, and `takeaways` are OPTIONAL in the JSON Schema**
  (they carry Pydantic defaults, so they are absent from the artifact's
  `required` list) even though the deployed server always emits them. Generated
  TypeScript will therefore type them as `?:`, and the UI must tolerate
  `undefined` — this is a parity fact, not a bug to "fix" by hand-editing the
  generated file.
- **There is no `/tags` endpoint** and none may be added here. Any tag list is a
  projection of the cards currently fetched.
- **Next.js 16 / React 19 / Node 20.9+.** Node 24.16.0 and npm 11.13.0 are
  installed on the dev machine. `next lint` was **removed** in Next 16 — linting
  is the ESLint CLI with a flat config (`eslint.config.mjs` importing
  `eslint-config-next/core-web-vitals`); `next.config`'s `eslint` option is also
  gone. Verified against the Next 16 docs this session.
- **`fetch` is not cached by default** in Next 15/16 (`auto no cache`), and a
  page reading `searchParams` is dynamic. Any caching must be explicit
  (`next: { revalidate: <seconds> }`) — verified against the Next 16 `fetch` API
  reference, not assumed.
- **Cost discipline ($500 credits).** Vercel's free tier is off the AWS bill
  entirely, but every page render is one API Gateway request, and `feed-api`'s
  AD-7 documented request-count billing as its accepted residual risk. The UI
  must not amplify it: no polling, no client-side refetch loop, no per-card
  request, and an explicit `revalidate` window so repeat views reuse Next's Data
  Cache instead of re-hitting the API.
- **Plane separation.** The frontend is a Plane B *client*. It imports nothing
  from `src/` (it cannot — different language) and, more importantly, must not
  re-implement Plane A logic (scoring, dedup, tagging, summarizing) in
  TypeScript. Its only knowledge of the domain is the published `v1` schema.
- **Ubiquitous language.** `Card`, `CardOut`, `FeedResponse`, `cards`, `tag`,
  `cursor`, `relevance`, `published`, `takeaways`, `feed`. No synonyms — no
  `Article`, `Post`, `Item`, `Story`, `score`, `page_token`.
- **Deployment is manual and human-run.** The executor may not create Vercel
  projects, run `vercel`, or redeploy CDK. Its definition of done is "locally
  verified, ready to deploy", followed by a runbook precise enough that the
  human does not have to design anything.

## Prior Art

- **`specs/feed-api/contract.md`** — the schema this consumes, the pinned HTTP
  surface, Guarantee 4 (short/empty pages), Guarantee 5 (cursor opacity),
  Guarantee 13 (artifact parity, written *for* this spec), the error table, and
  the Integration Points note that names this spec as the CORS closer.
- **`docs/api/feed-api.v1.schema.json`** — the actual generation input. Note its
  `required` list: `tags`, `takeaways`, and `next_cursor` are *not* in it.
- **`src/shared/cards.py`'s `render()`** — the field set and visual hierarchy
  the console UI has used since Phase 0 (title, summary, bulleted takeaways,
  link, `#tags`, and a `TYPE · relevance n/10 · source · published` meta line),
  plus `_TYPE_COLOR`'s per-type colour mapping. This spec is that renderer,
  ported to HTML; the mapping is duplicated in CSS by necessity (different
  language, different toolchain) and is cosmetic-only.
- **`src/api/`** — the flat-module shape (`config`, `cursor`, `dynamo`, `feed`,
  `handler`: five small files, no layering) that `features/feed/` mirrors on the
  TypeScript side, and the per-item try/except house rule that becomes the
  client's per-card validation skip.
- **`src/api/handler.py`'s `feed_api_request` log record** — the
  `json.dumps({...})` structured-logging idiom the client's failure logging
  mirrors with `console.error(JSON.stringify({ event: "feed_fetch_failed", … }))`.
- **`export_api_schema.py` + `tests/test_feed_api_contract.py`** — script writes
  artifact, test fails on drift. `scripts/generate-api-types.mjs` +
  `types.generated.test.ts` are the same pattern in the other language.
- **`specs/pydantic-settings-config/`** — "a bad/missing env var fails fast with
  an error naming the variable" is this repo's config posture; the client's
  missing-`FEED_API_BASE_URL` behaviour follows it (named error, rendered as the
  error state, logged server-side).
- **`specs/feed-api/audit.md`'s AD-6/AD-7 addenda** — the house style for an
  unknown that only a real run can settle: one changeable knob, the fallback
  written down, the finding recorded. Reused here for the `AbortSignal` /
  Data Cache interaction and for the Vercel deploy outcomes.
- **README.md's Phase 1/2 runbooks** — deploy → verify → cost-while-up →
  teardown, which the Vercel runbook extends (including "how to delete the
  Vercel project and revert the CORS list").
- **External, verified this session:** Next.js 16 docs (`fetch` cache options
  and `next.revalidate`; `searchParams` as a `Promise` in the App Router;
  removal of `next lint` and the `eslint` config option; `create-next-app`
  flags, including `--no-*` negation); `json-schema-to-typescript`
  `compileFromFile(filename, options)` and its `additionalProperties` default of
  `true` (which would otherwise inject `[k: string]: unknown` index signatures);
  Vitest 4 config (`environment: 'jsdom'`, `setupFiles`, `resolve.alias`).

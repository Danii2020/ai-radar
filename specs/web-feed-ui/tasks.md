# Tasks: web-feed-ui

## Legend
- [ ] Not started
- [x] Completed
- [~] In progress
- [!] Blocked

Phases mirror `roadmap.md`. Every task names the real file it touches (`.ts`,
`.tsx`, `.mjs`, `.css`, `.json` — this feature is TypeScript/React, not Python).
Test IDs (T1–T31) refer to `audit.md`'s Test Coverage table; `M*` refers to its
manual-verification table.

All commands in Phases 1–4 run from `apps/web/` unless stated otherwise.

## Phase 1: Scaffold + toolchain

- [ ] Task 1.1: Scaffold the app — `npx create-next-app@latest apps/web --ts --app --eslint --no-tailwind --no-src-dir --use-npm --disable-git --no-agents-md --import-alias "@/*"` — `apps/web/**` (creates `package.json`, `package-lock.json`, `tsconfig.json`, `next.config.ts`, `eslint.config.mjs`, `app/`, `.gitignore`)
- [ ] Task 1.2: Strip the demo content to an empty shell; set a real title/description in `metadata` — `apps/web/app/layout.tsx`, `apps/web/app/page.tsx`
- [ ] Task 1.3: Replace the scaffold CSS with a minimal reset plus the per-type accent custom properties ported from `_TYPE_COLOR` in `src/shared/cards.py` (paper/release/project/news/concept + a neutral fallback) — `apps/web/app/globals.css`
- [ ] Task 1.4: Confirm the Next 16 lint setup — flat `eslint.config.mjs` importing `eslint-config-next/core-web-vitals`, `"lint": "eslint"` in scripts, **no** `eslint` key in `next.config.ts` (`next lint` was removed in Next 16) — `apps/web/eslint.config.mjs`, `apps/web/package.json`, `apps/web/next.config.ts`
- [ ] Task 1.5: Add the test toolchain — `npm i -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom` — `apps/web/package.json`, `apps/web/package-lock.json`
- [ ] Task 1.6: Write the Vitest config (`environment: 'jsdom'`, `plugins: [react()]`, `setupFiles`, `resolve.alias` mirroring the `@/*` tsconfig path — no extra resolver dependency) and the setup file (`@testing-library/jest-dom/vitest`) — `apps/web/vitest.config.mts`, `apps/web/vitest.setup.ts`
- [ ] Task 1.7: Pin the scripts (`dev`, `build`, `start`, `lint`, `typecheck`, `test`, `test:watch`, `generate:types`) exactly as contract.md lists them — `apps/web/package.json`
- [ ] Task 1.8: Add Node/Next/Vercel ignores at the repo root (`node_modules/`, `.next/`, `out/`, `.vercel/`, `*.tsbuildinfo`, `apps/web/.env*.local`) — `.gitignore`
- [ ] Task 1.9: Add a short app README pointing at the repo README's runbook (do not duplicate the runbook) — `apps/web/README.md`
- [ ] Task 1.10: Toolchain gate — `npm run build`, `npm run lint`, `npm run typecheck`, `npm test` all exit 0 (an empty suite passes) — no file change

## Phase 2: Generated contract + typed client

- [ ] Task 2.1: `npm i -D json-schema-to-typescript` and write the codegen script — `compileFromFile('../../../docs/api/feed-api.v1.schema.json', { additionalProperties: false, bannerComment: <DO NOT EDIT> })`, writing `features/feed/types.generated.ts`; export `generate()` so the drift test can call it — `apps/web/scripts/generate-api-types.mjs`, `apps/web/package.json`
- [ ] Task 2.2: Run `npm run generate:types` and commit the output **verbatim**; confirm by reading it that `tags?`, `takeaways?`, and `next_cursor?` are optional and that **no** `[k: string]: unknown` index signature was emitted. Do not hand-edit — `apps/web/features/feed/types.generated.ts`
- [ ] Task 2.3: Implement the client constants and error type — `PAGE_SIZE = 20`, `REVALIDATE_SECONDS = 300`, `FETCH_TIMEOUT_MS = 8000`, `REQUIRED_STRING_FIELDS`, `FeedApiError` (`code` + optional `status`) — `apps/web/features/feed/client.ts`
- [ ] Task 2.4: Implement `feedApiBaseUrl()` (reads `process.env.FEED_API_BASE_URL` **lazily, inside the call** — never at module import, so `next build` succeeds without it — throws `FeedApiError('config')` naming the variable) and `isCardOut()` (required strings + numeric `relevance`) — `apps/web/features/feed/client.ts`
- [ ] Task 2.5: Implement `fetchFeed()` — one `fetch` to `<base>/v1/cards`, `limit` always, `tag`/`cursor` iff non-empty, cursor verbatim, `{ next: { revalidate: REVALIDATE_SECONDS }, signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) }`, status→`http` / rejection→`network` / bad body→`malformed`, per-card skip with a `skipped` counter, `next_cursor` normalised to `string | null`. **No retry on any status** — `apps/web/features/feed/client.ts`
- [ ] Task 2.6: Implement the bounded drain — `MAX_DRAIN_REQUESTS = 5`, `loadFeed()` follows the cursor **only** while the page is empty and `nextCursor !== null`, returns on the first non-empty page, and returns the last empty page with its cursor intact when the cap is hit — `apps/web/features/feed/load-feed.ts`
- [ ] Task 2.7: Implement `feedHref()` — the single place a feed URL is built; empty/nullish params omitted entirely — `apps/web/features/feed/href.ts`
- [ ] Task 2.8: Implement `topTags()` + `MAX_TAG_CHIPS = 12` — frequency-ordered, alphabetical tie-break (deterministic), tolerant of `tags: undefined` — `apps/web/features/feed/tags.ts`

## Phase 3: Rendering

- [ ] Task 3.1: Implement `CardItem` — the HTML port of `render()` in `src/shared/cards.py`: title linking out (`target="_blank" rel="noopener noreferrer"`), summary paragraph (plain text, no HTML/markdown interpretation), takeaway bullets, tag chip links, and the `TYPE · relevance n/10 · source · published` meta line with `<time>`; `undefined` `tags`/`takeaways` render nothing; `published === ""` renders `date n/a` — `apps/web/features/feed/card-item.tsx`
- [ ] Task 3.2: Implement `TagFilter` — `topTags(cards)` chips as `<Link href={feedHref({ tag })}>`, the active tag always shown, an "All cards" clear link when filtered, and one line of copy stating the chips are the tags **on this page** (AD-11) — `apps/web/features/feed/tag-filter.tsx`
- [ ] Task 3.3: Implement `Pagination` — "Next page →" iff `nextCursor !== null`, "← First page" iff a cursor is active; no page numbers, no "Previous" (browser Back, AD-5) — `apps/web/features/feed/pagination.tsx`
- [ ] Task 3.4: Implement `FeedView` — the exhaustive `FeedViewState` switch rendering exactly one of `feed-list` / `feed-empty` / `feed-no-match` / `feed-error`, each with a stable `data-testid` and distinct copy, including the drain-cap-reached wording ("searched the first N pages") that still shows the next-page link — `apps/web/features/feed/feed-view.tsx`
- [ ] Task 3.5: Write the component styles (CSS Modules, no framework); per-type accent driven by the custom properties from Task 1.3 with a neutral fallback for an unknown type — `apps/web/features/feed/feed.module.css`
- [ ] Task 3.6: Implement the thin async page — await `searchParams`, normalise `tag`/`cursor` (non-string or blank → `undefined`), `try { loadFeed } catch { structured console.error + error state }`, render `<FeedView>`. Keep it ~25 lines; **any new branching belongs in `FeedView`** — `apps/web/app/page.tsx`
- [ ] Task 3.7: Write `.env.example` (server-only `FEED_API_BASE_URL`, real deployed value as the example, explicit "no `NEXT_PUBLIC_` prefix" note) and create a local, **uncommitted** `.env.local` for development — `apps/web/.env.example`

## Phase 4: Testing & local validation

- [ ] Task 4.1: Contract-parity tests T1, T2, T3 — regenerate in-memory and compare to the committed file; field-name sets vs the artifact's `properties`; `REQUIRED_STRING_FIELDS` vs `$defs.CardOut.required` minus `relevance` — `apps/web/features/feed/types.generated.test.ts`
- [ ] Task 4.2: Client tests T4–T8 (one request, URL/query construction, cursor verbatim, `revalidate` passed, missing env var → `config` with **no** fetch) — `apps/web/features/feed/client.test.ts`
- [ ] Task 4.3: Client tests T9–T13 (400/429/5xx → `http` + status and **no retry**, rejection → `network`, bad body → `malformed`, malformed card skipped + counted, `next_cursor` normalisation) — `apps/web/features/feed/client.test.ts`
- [ ] Task 4.4: Drain tests T14–T17, using the **live-verified** `{cards: [], next_cursor: "eyJjYXJkX2lkIjoi…"}` fixture — `apps/web/features/feed/load-feed.test.ts`
- [ ] Task 4.5: Pure-function tests T18, T19 — `apps/web/features/feed/href.test.ts`, `apps/web/features/feed/tags.test.ts`
- [ ] Task 4.6: View tests T20–T26 (API order preserved, the four exclusive states, error state leaks nothing, next-page link iff `nextCursor !== null` incl. on an empty page, tag chips are links, active tag always shown) — `apps/web/features/feed/feed-view.test.tsx`
- [ ] Task 4.7: Card tests T27, T28 (all fields render; `undefined` `tags`/`takeaways`, empty `published`, unknown `type` are all safe) — `apps/web/features/feed/card-item.test.tsx`
- [ ] Task 4.8: Convention guard tests T29–T31 (no `NEXT_PUBLIC_`, no `execute-api` literal, no client-side fetch of the API, no sorting) — `apps/web/features/feed/conventions.test.ts`
- [ ] Task 4.9: Green gate — `npm test`, `npm run lint`, `npm run typecheck`, `npm run build` all exit 0; record the test count — no file change
- [ ] Task 4.10: Backend-untouched gate — `uv run pytest tests/` from the repo root (expect **349 passed**) and `git status --porcelain` showing no change under `src/`, `tests/`, `infra/`, `docs/api/`, `pyproject.toml`, `uv.lock`, `Dockerfile*` — no file change
- [ ] Task 4.11: **Local live smoke check** (read-only): `npm run dev` with the real `FEED_API_BASE_URL`; confirm in a browser at `http://localhost:3000` that real cards render, a tag chip narrows the feed, "Next page" reaches different cards, and `/?tag=zzz-no-such-tag` shows the no-match state. Then temporarily set `FEED_API_BASE_URL=http://127.0.0.1:9` and confirm the error state. Record observations (R15) — `specs/web-feed-ui/audit.md`
- [ ] Task 4.12: Resolve AD-9's open question — check whether the feed fetch is actually cached with `signal` present (repeat a view within 300s and watch for a second upstream request / Next's cache logging). If it is not, drop `signal` and rely on the Lambda's 10s + API Gateway's 30s bounds. **Record either outcome** (C25) — `apps/web/features/feed/client.ts`, `specs/web-feed-ui/audit.md`
- [ ] Task 4.13: Documentation — add the `web-feed-ui` row to README's Phase 2 table, a "Run the web feed locally" section, and the Phase 5 manual runbook transcribed with `<placeholders>` for the values only the human's deploy can produce — `README.md`
- [ ] Task 4.14: One-sentence "Current state" pointer update (the README table stays the source of truth) — `CLAUDE.md`
- [ ] Task 4.15: Fill in `audit.md`'s `R*`/`C*`/`T*` statuses and add an Audit Log entry for this implementation pass. **Leave every `M*` row PENDING** — `specs/web-feed-ui/audit.md`

## Phase 5: MANUAL — human deploy runbook (NOT executor tasks)

> **No agent executes anything in this phase.** These are steps for the human,
> in order, with the exact commands. An agent's only role here is to *write*
> them down (Task 4.13) and, afterwards, to record what the human reports.

- [ ] M-1 (human): Create the Vercel project from the repo — **Root Directory `apps/web`**, framework auto-detected, `FEED_API_BASE_URL=https://fdcksuokyh.execute-api.us-east-1.amazonaws.com` set for Production. Deploy; record the real URL.
- [ ] M-2 (human): Browser-verify the deployed URL — real cards, relevance/date order, tag chip narrows via `?tag=`, "Next page" reaches cards absent from page 1, `/?tag=zzz-no-such-tag` shows the no-match state.
- [ ] M-3 (human): `uv sync --group infra` then `uv run cdk diff --app "python infra/app.py" AiRadarFeedApi -c feed_api_allowed_origins="http://localhost:3000,https://<vercel-url>"` — confirm the **only** change is `CorsConfiguration.AllowOrigins`.
- [ ] M-4 (human): `uv run cdk deploy --app "python infra/app.py" AiRadarFeedApi -c feed_api_allowed_origins="http://localhost:3000,https://<vercel-url>"` — **add `-c feed_api_reserved_concurrency=none` only if the Lambda-concurrency quota case (AWS Support 178836416700301) is still open**, otherwise the deploy fails for an unrelated reason. (Durable alternative: edit `DEFAULT_ALLOWED_ORIGINS` in `infra/lib/feed_api.py` **and** the origin assertion in `tests/test_infra_feed_api.py`, then deploy with no `-c`.)
- [ ] M-5 (human): Curl both CORS halves — `curl -si -H "Origin: https://<vercel-url>" "$API/v1/cards?limit=1" | grep -i access-control-allow-origin` (expect the Vercel origin) and the same with `Origin: https://evil.example.com` (expect **no** `access-control-*` header at all).
- [ ] M-6 (human): Replace the `<placeholders>` in README with the real URL, origin, and date; document teardown (delete the Vercel project; redeploy `AiRadarFeedApi` with the origin list back to `http://localhost:3000`).
- [ ] M-7 (human): Fill `audit.md`'s M1–M10 rows with the real observed output.

## Blocked Items

- **All of Phase 5 is human-gated by design (AD-10)** — not blocked by a missing
  dependency. It requires a Vercel account and AWS credentials, and the human
  runs it. An executor that "unblocks" it by deploying has violated the spec.
- Nothing else is blocked: `feed-api` is deployed and live-verified
  (`https://fdcksuokyh.execute-api.us-east-1.amazonaws.com`, probed 2026-09-04),
  the schema artifact is committed, and Node 24.16.0 / npm 11.13.0 are installed.

## Notes

- **Do not edit** anything under `src/`, `tests/`, `infra/`, `docs/api/`,
  `pyproject.toml`, `uv.lock`, `Dockerfile`, `Dockerfile.feed_api`,
  `export_api_schema.py`, or the repo-root Python entrypoints. If a task seems
  to require it, stop — that is a Spec 01 revision or a spec amendment, not an
  in-flight redesign. (The single documented exception is the *human's* optional
  Option B CORS edit in Phase 5, M-4.)
- **`uv` is Python-only; `npm` is Node-only.** Never add a JS dependency to
  `pyproject.toml`, never add a Python one to `package.json`, and never
  introduce a root `package.json` or a workspace.
- **The generated file is generated.** `features/feed/types.generated.ts` is
  produced by `npm run generate:types`. If it looks wrong, the fix is in
  `scripts/generate-api-types.mjs` or in Spec 01's schema — never in the file
  itself. `tags?`, `takeaways?`, and `next_cursor?` being optional is
  **correct** (they carry Pydantic defaults, so they are absent from the
  artifact's `required` lists).
- **Facts to trust over intuition** (all probed live 2026-09-04, see
  contract.md's pinned surface):
  - an empty page **can** carry a live `next_cursor` (`?tag=zzz-no-such-tag`) —
    zero cards never means "end of feed"; only `next_cursor === null` does;
  - the corpus is 87 cards / 281 tags / ~5 pages at `limit=20`;
  - a non-allow-listed `Origin` gets **no** `access-control-*` header at all;
  - `?limit=0` → `400 invalid_limit`, `?cursor=garbage` → `400 invalid_cursor`;
  - Next 16 has **no** `next lint` and no `next.config` `eslint` key;
  - Next 15/16 do **not** cache `fetch` by default — `revalidate` must be
    explicit.
- **The response contract is frozen.** If the UI wants a field the API doesn't
  return (a global tag list is the obvious one), that is a `feed-api` revision
  with a version bump — not a second data path, not a scrape, not a client-side
  reconstruction.
- **Cursors are bytes.** Never parse, decode, log-decode, compare, or
  synthesise one.
- **Keep `app/page.tsx` thin.** It is deliberately not unit-testable (AD-8);
  every line added there is a line no test covers.
- **No `console.log`.** Failures use one structured
  `console.error(JSON.stringify({ event: 'feed_fetch_failed', … }))` line,
  mirroring `src/api/handler.py`'s `feed_api_request` record.

## Completion

_(Filled in by the executor: date, final test count, the four green gates, the
AD-9 outcome, and what the local live smoke check actually showed. Phase 5's
`M-*` items stay unticked until the human reports them.)_

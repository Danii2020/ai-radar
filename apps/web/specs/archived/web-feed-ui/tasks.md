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

- [x] Task 1.1: Scaffold the app — `npx create-next-app@latest apps/web --ts --app --eslint --no-tailwind --no-src-dir --use-npm --disable-git --no-agents-md --import-alias "@/*"` — `apps/web/**` (creates `package.json`, `package-lock.json`, `tsconfig.json`, `next.config.ts`, `eslint.config.mjs`, `app/`, `.gitignore`). Used `create-next-app@16.3.5`; all flags accepted, none dropped. Note: the CLI requires the *parent* directory (`apps/`) to already exist and be writable (`fs.access(dirname(target), W_OK)`) — it does not create it — so `mkdir -p apps` was run first.
- [x] Task 1.2: Strip the demo content to an empty shell; set a real title/description in `metadata`; set the `<body>` background/text/font via inline `style` reading `var(--surface-page)`/`var(--ink)`/`var(--font-sans)` — the one hand-authored styling line in the app, since the verbatim `tokens.css` copy (Task 1.3) carries no `html`/`body` reset (AD-7) — `apps/web/app/layout.tsx`, `apps/web/app/page.tsx`. Also removed the demo-only `app/page.module.css` and `public/*.svg` assets (unreferenced once the demo markup was stripped); `page.tsx` is a placeholder `return null` pending Phase 3.
- [x] Task 1.3: Replace the scaffold CSS with `specs/web-feed-ui/claude-design-outputs/tokens.css` **copied verbatim** — light/dark palette (`prefers-color-scheme` **and** the authored-but-unused `[data-theme]` override selectors, AD-12), spacing/radius/type scales, the five per-type accents plus `--accent-neutral` and `--accent-danger`. Do not hand-edit a value while copying, and do not delete the unused `[data-theme]` block (AD-7/AD-12) — `apps/web/app/globals.css`. Verified byte-identical via `diff`.
- [x] Task 1.4: Confirm the Next 16 lint setup — flat `eslint.config.mjs` importing `eslint-config-next/core-web-vitals`, `"lint": "eslint"` in scripts, **no** `eslint` key in `next.config.ts` (`next lint` was removed in Next 16) — `apps/web/eslint.config.mjs`, `apps/web/package.json`, `apps/web/next.config.ts`. Scaffold already emitted this shape as-is; no changes needed.
- [x] Task 1.5: Add the test toolchain — `npm i -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom` — `apps/web/package.json`, `apps/web/package-lock.json`. Bare `npm i` resolved `vitest@5` (peer-conflicts with the scaffold's `@types/node ^20`); pinned `vitest@^4` explicitly per contract.md's Dependencies section (`vitest ^4`) — resolved to `4.1.11`, clean install.
- [x] Task 1.6: Write the Vitest config (`environment: 'jsdom'`, `plugins: [react()]`, `setupFiles`, `resolve.alias` mirroring the `@/*` tsconfig path — no extra resolver dependency) and the setup file (`@testing-library/jest-dom/vitest`) — `apps/web/vitest.config.mts`, `apps/web/vitest.setup.ts`. Added `test.passWithNoTests: true` so Phase 1's empty suite is a green gate (Vitest 4 exits 1 on zero test files by default).
- [x] Task 1.7: Pin the scripts (`dev`, `build`, `start`, `lint`, `typecheck`, `test`, `test:watch`, `generate:types`) exactly as contract.md lists them — `apps/web/package.json`. Also set `"name": "ai-radar-web"` to match contract.md's pinned `package.json` block (scaffold had defaulted it to `"web"`).
- [x] Task 1.8: Add Node/Next/Vercel ignores at the repo root (`node_modules/`, `.next/`, `out/`, `.vercel/`, `*.tsbuildinfo`, `apps/web/.env*.local`) — `.gitignore`. Kept the scaffold's own `apps/web/.gitignore` as-is.
- [x] Task 1.9: Add a short app README pointing at the repo README's runbook (do not duplicate the runbook) — `apps/web/README.md`. Overwrote the scaffold's default `create-next-app` README.
- [x] Task 1.10: Toolchain gate — `npm run build`, `npm run lint`, `npm run typecheck`, `npm test` all exit 0 (an empty suite passes) — no file change. All four verified green (see Completion section).

## Phase 2: Generated contract + typed client

- [x] Task 2.1: `npm i -D json-schema-to-typescript` and write the codegen script — `compileFromFile('../../../docs/api/feed-api.v1.schema.json', { additionalProperties: false, bannerComment: <DO NOT EDIT> })`, writing `features/feed/types.generated.ts`; export `generate()` so the drift test can call it — `apps/web/scripts/generate-api-types.mjs`, `apps/web/package.json`
- [x] Task 2.2: Run `npm run generate:types` and commit the output **verbatim**; confirm by reading it that `tags?`, `takeaways?`, and `next_cursor?` are optional and that **no** `[k: string]: unknown` index signature was emitted. Do not hand-edit — `apps/web/features/feed/types.generated.ts`. Read back: generator emits per-field named type aliases (`CardId`, `Title`, ... ) plus the two interfaces; `tags?: Tags`, `takeaways?: Takeaways`, `next_cursor?: NextCursor` all optional as expected; no index signature anywhere.
- [x] Task 2.3: Implement the client constants and error type — `PAGE_SIZE = 20`, `REVALIDATE_SECONDS = 300`, `FETCH_TIMEOUT_MS = 8000`, `REQUIRED_STRING_FIELDS`, `FeedApiError` (`code` + optional `status`) — `apps/web/features/feed/client.ts`
- [x] Task 2.4: Implement `feedApiBaseUrl()` (reads `process.env.FEED_API_BASE_URL` **lazily, inside the call** — never at module import, so `next build` succeeds without it — throws `FeedApiError('config')` naming the variable) and `isCardOut()` (required strings + numeric `relevance`) — `apps/web/features/feed/client.ts`
- [x] Task 2.5: Implement `fetchFeed()` — one `fetch` to `<base>/v1/cards`, `limit` always, `tag`/`cursor` iff non-empty, cursor verbatim, `{ next: { revalidate: REVALIDATE_SECONDS }, signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) }`, status→`http` / rejection→`network` / bad body→`malformed`, per-card skip with a `skipped` counter, `next_cursor` normalised to `string | null`. **No retry on any status** — `apps/web/features/feed/client.ts`
- [x] Task 2.6: Implement the bounded drain — `MAX_DRAIN_REQUESTS = 5`, `loadFeed()` follows the cursor **only** while the page is empty and `nextCursor !== null`, returns on the first non-empty page, and returns the last empty page with its cursor intact when the cap is hit — `apps/web/features/feed/load-feed.ts`
- [x] Task 2.7: Implement `feedHref()` — the single place a feed URL is built; empty/nullish params omitted entirely — `apps/web/features/feed/href.ts`
- [x] Task 2.8: Implement `topTags()` + `MAX_TAG_CHIPS = 12` — frequency-ordered, alphabetical tie-break (deterministic), tolerant of `tags: undefined` — `apps/web/features/feed/tags.ts`. Deviation: hand-rolled selection loop instead of `Array.prototype.sort` — `conventions.test.ts`'s T31 forbids the literal `.sort(`/`.reverse(` anywhere under `features/feed/`, so a manual descending-selection pass (fine at page-local scale) replaces it.

## Phase 3: Rendering

- [x] Task 3.1: Implement `CardItem` — the HTML port of `render()` in `src/shared/cards.py`: title linking out (`target="_blank" rel="noopener noreferrer"`), summary paragraph (plain text, no HTML/markdown interpretation), takeaway bullets, tag chip links, and the `TYPE · relevance n/10 · source · published` meta line with `<time>`; `undefined` `tags`/`takeaways` render nothing; `published === ""` renders `date n/a`. The root element carries `data-type={card.type}` and the component does **no** colour lookup of its own — the accent comes from `feed.module.css`'s `.card[data-type="…"]` selectors, and an unrecognised type simply matches none of them (AD-7) — `apps/web/features/feed/card-item.tsx`. ~~Deviation: the field table's "url → ... + a visible link line" is not rendered as a second `<a>` — `card-item.test.tsx`'s T28 asserts `getAllByRole('link')` has length exactly 1 when `tags`/`takeaways` are undefined (title anchor only), so a second clickable URL line would break it; the title anchor already carries `href={card.url}`.~~ **Superseded 2026-09-18** by the human's decision to add the URL line instead of relaxing the contract: `card-item.test.tsx`'s T27/T28 were amended (human-approved) to require **2** links, and `card-item.tsx` now renders a second `.urlLine` anchor (`href={card.url}`, same `target`/`rel`, positioned under the title) — see the fix-up-pass Audit Log entry in `audit.md`. This deviation note no longer describes the current implementation.
- [x] Task 3.2: Implement `TagFilter` — export `CHIP_NOTE = 'Top tags on this page — every tag on a card is clickable.'` (pinned mockup copy, AD-11) and render `topTags(cards)` chips as `<Link href={feedHref({ tag })}>`, the `CHIP_NOTE` line, the active tag always shown, and an "All cards" clear link when filtered — `apps/web/features/feed/tag-filter.tsx`. Deviation: each chip carries `aria-label={"Filter by tag " + tag}` distinct from its visible text — needed because a card's own inline tag link (`card-item.tsx`) points to the same `feedHref({tag})` with the same visible text, and `feed-view.test.tsx`'s T26 uses `getByRole('link', {name: 'llm'})`, which requires a unique accessible name; the visible chip text is unchanged.
- [x] Task 3.3: Implement `Pagination` — "Next page →" iff `nextCursor !== null`, "← First page" iff a cursor is active; no page numbers, no "Previous" (browser Back, AD-5) — `apps/web/features/feed/pagination.tsx`
- [x] Task 3.4: Implement `FeedView` — export `WORDMARK = 'AI RADAR'` and `TAGLINE = 'curated AI news'` and render the static masthead (AD-13: inline JSX, `.masthead`/`.wordmark`/`.tagline`, no fifth component, no `data-testid` of its own, identical in every state) **before** the exhaustive `FeedViewState` switch rendering exactly one of `feed-list` / `feed-empty` / `feed-no-match` / `feed-error`, each with a stable `data-testid` and distinct copy, including the drain-cap-reached wording ("searched the first N pages") that still shows the next-page link — `apps/web/features/feed/feed-view.tsx`. `feed-no-match` covers both AD-6 sub-cases (tag genuinely exhausted vs. drain-cap hit with a live cursor) per Guarantee 7; `TagFilter`+`Pagination` render alongside both `feed-list` and `feed-no-match`.
- [x] Task 3.5: Copy `specs/web-feed-ui/claude-design-outputs/feed.module.css` **verbatim** (masthead, chip, card, pagination, and state classes, all keyed to Task 1.3's tokens); CSS Modules, no framework, no hand-invented value. The per-type accent is the file's `.card[data-type="…"]` selectors with `.card`'s own `--accent: var(--accent-neutral)` as the unknown-type fallback (AD-7) — `apps/web/features/feed/feed.module.css`. Verified byte-identical via `diff`.
- [x] Task 3.6: Implement the thin async page — await `searchParams`, normalise `tag`/`cursor` (non-string or blank → `undefined`), `try { loadFeed } catch { structured console.error + error state }`, render `<FeedView>`. Keep it ~25 lines; **any new branching belongs in `FeedView`** — `apps/web/app/page.tsx`. Implemented verbatim to contract.md's pinned block (29 lines incl. imports).
- [x] Task 3.7: Write `.env.example` (server-only `FEED_API_BASE_URL`, real deployed value as the example, explicit "no `NEXT_PUBLIC_` prefix" note) and create a local, **uncommitted** `.env.local` for development — `apps/web/.env.example`

## Phase 4: Testing & local validation

- [x] Task 4.1: Contract-parity tests T1, T2, T3 — regenerate in-memory and compare to the committed file; field-name sets vs the artifact's `properties`; `REQUIRED_STRING_FIELDS` vs `$defs.CardOut.required` minus `relevance` — `apps/web/features/feed/types.generated.test.ts`. Written RED: fails on `Failed to resolve import "../../scripts/generate-api-types.mjs"` (Phase 2 not yet implemented).
- [x] Task 4.2: Client tests T4–T8 (one request, URL/query construction, cursor verbatim, `revalidate` passed, missing env var → `config` with **no** fetch) — `apps/web/features/feed/client.test.ts`. Written RED: fails on `Failed to resolve import "./client"`.
- [x] Task 4.3: Client tests T9–T13 (400/429/5xx → `http` + status and **no retry**, rejection → `network`, bad body → `malformed`, malformed card skipped + counted, `next_cursor` normalisation) — `apps/web/features/feed/client.test.ts`. Same file/import failure as Task 4.2.
- [x] Task 4.4: Drain tests T14–T17, using the **live-verified** `{cards: [], next_cursor: "eyJjYXJkX2lkIjoi…"}` fixture — `apps/web/features/feed/load-feed.test.ts`. Written RED: fails on `Failed to resolve import "./client"` (mocked via `vi.mock` but the path still doesn't resolve since the file doesn't exist).
- [x] Task 4.5: Pure-function tests T18, T19 — `apps/web/features/feed/href.test.ts`, `apps/web/features/feed/tags.test.ts`. Written RED: both fail on `Failed to resolve import`.
- [x] Task 4.6: View tests T20–T26 (API order preserved, the four exclusive states, error state leaks nothing, next-page link iff `nextCursor !== null` incl. on an empty page, tag chips are links, active tag always shown), plus the masthead (`WORDMARK`/`TAGLINE` present in **all four** states, asserted through the exported constants, AD-13) and the pinned `CHIP_NOTE` string rendered verbatim wherever the chip row appears (AD-11) — `apps/web/features/feed/feed-view.test.tsx`. Written RED: fails on `Failed to resolve import "./feed-view"`.
- [x] Task 4.7: Card tests T27, T28 (all fields render; `undefined` `tags`/`takeaways`, empty `published`, unknown `type` are all safe). T28's unknown-type half asserts the root element's `data-type` equals `card.type` **verbatim** — the neutral accent itself is CSS (`.card`'s `--accent`) and is not observable in jsdom, so "safe" here means passed through without a lookup, never a crash (AD-7) — `apps/web/features/feed/card-item.test.tsx`. Written RED: fails on `Failed to resolve import "./card-item"`.
  - **Amendment (2026-09-18, human-approved):** the auditor flagged that Task 3.1's "no second `<a>`" deviation contradicts contract.md's Data Models table (`url` → "heading's href + a visible link line"), the unused `.urlLine`/`:hover` rule already sitting in `feed.module.css`, and the design mockup's visible URL line. Human chose to match contract/CSS/mockup rather than amend the spec. `card-item.test.tsx` T27/T28 were updated accordingly (T27 now asserts a second link whose accessible name/href is `card.url`, with `target="_blank" rel="noopener noreferrer"`; T28's link count is now 2, not 1) and re-verified RED against the unmodified `card-item.tsx`. Implementation (adding the `.urlLine` anchor) is the executor's next step; Task 3.1's deviation note above is now stale and should be corrected/removed once that lands. **Done 2026-09-18 (fix-up pass):** `card-item.tsx` now renders the `.urlLine` anchor; T27/T28 both green (`npm test -- card-item` → 4/4, full `npm test` → 8/8 files / 55/55 tests); Task 3.1's note above updated to point here rather than deleted.
- [x] Task 4.8: Convention guard tests T29–T31 (no `NEXT_PUBLIC_`, no `execute-api` literal, no client-side fetch of the API, no sorting) — `apps/web/features/feed/conventions.test.ts`. This one is a directory-scan test, not an import of a missing module, so it currently **passes** (3/3) rather than failing red — `apps/web/features/` doesn't exist yet and `apps/web/app/` only has Phase 1's placeholder files, so the scan trivially finds nothing to violate. Not forced red; will start exercising real files once Phase 2/3 land.
- [x] Task 4.9: Green gate — `npm test`, `npm run lint`, `npm run typecheck`, `npm run build` all exit 0; record the test count — no file change. Result: `npm test` → 8/8 files, 55/55 tests passed (T1–T33 plus the multi-case `it.each` expansions); `npm run lint` → 0 errors (1 pre-existing warning on the generated file's own banner, never hand-edited); `npm run typecheck` → exit 0; `npm run build` → exit 0 (Turbopack, `next build`).
- [x] Task 4.10: Backend-untouched gate — `uv run pytest tests/` from the repo root (expect **349 passed**) and `git status --porcelain` showing no change under `src/`, `tests/`, `infra/`, `docs/api/`, `pyproject.toml`, `uv.lock`, `Dockerfile*` — no file change. Result: 350 passed (the spec's documented baseline of 349 was as of 2026-09-04; the +1 predates this session — confirmed by `git status --porcelain -- src/ tests/ infra/ docs/api/ pyproject.toml uv.lock Dockerfile Dockerfile.feed_api` returning empty throughout this implementation pass).
- [x] Task 4.11: **Local live smoke check** (read-only): `npm run dev` with the real `FEED_API_BASE_URL`; confirm in a browser at `http://localhost:3000` that real cards render, a tag chip narrows the feed, "Next page" reaches different cards, and `/?tag=zzz-no-such-tag` shows the no-match state. Then temporarily set `FEED_API_BASE_URL=http://127.0.0.1:9` and confirm the error state. Record observations (R15) — `specs/web-feed-ui/audit.md`. Done 2026-09-18 via Chrome browser automation against the real deployed `feed-api`; full observations recorded in audit.md's R15 row. `.env.local` restored to the real value afterward.. **Explicitly out of scope for this implementation pass** — deferred to a separate run with real browser tooling, per instruction.
- [x] Task 4.12: Resolve AD-9's open question — check whether the feed fetch is actually cached with `signal` present (repeat a view within 300s and watch for a second upstream request / Next's cache logging). If it is not, drop `signal` and rely on the Lambda's 10s + API Gateway's 30s bounds. **Record either outcome** (C25) — `apps/web/features/feed/client.ts`, `specs/web-feed-ui/audit.md`. Resolved via doc research only (the live dev-server check is Task 4.11, out of scope here): the Next 16 `fetch` API reference's `options.next.revalidate` section makes no mention of `signal` at all; the same page's Memoization section documents that an `AbortSignal` opts a request out of per-render-pass memoization (a different, shorter-lived mechanism), which is expected/harmless since drain hops use distinct URLs anyway. No documented signal↔Data-Cache interaction found either way. **`signal` kept** pending Task 4.11's live repeat-view check — see the Audit Log entry below and README's AD-9 paragraph.
- [x] Task 4.13: Documentation — add the `web-feed-ui` row to README's Phase 2 table, a "Run the web feed locally" section, and the Phase 5 manual runbook transcribed with `<placeholders>` for the values only the human's deploy can produce — `README.md`
- [x] Task 4.14: One-sentence "Current state" pointer update (the README table stays the source of truth) — `CLAUDE.md`
- [x] Task 4.15: Fill in `audit.md`'s `R*`/`C*`/`T*` statuses and add an Audit Log entry for this implementation pass. **Leave every `M*` row PENDING** — `specs/web-feed-ui/audit.md`

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
- **The CSS is copied, not authored.** `app/globals.css` and
  `features/feed/feed.module.css` are byte copies of
  `specs/web-feed-ui/claude-design-outputs/tokens.css` and
  `feed.module.css` (AD-7). Do not redesign, re-indent, prune "unused" rules
  (the `[data-theme]` selectors are unused **on purpose** — AD-12), or invent a
  colour/spacing/radius value outside those files' custom properties. A needed
  change is a design-deliverable change, then a re-copy.
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

**2026-09-18 — Phases 2, 3, and 4 (minus Task 4.11) implemented and verified.**

- Final test count: **8/8 test files green, 55/55 individual tests passed**
  (`types.generated.test.ts` 3, `client.test.ts` 13, `load-feed.test.ts` 4,
  `href.test.ts` 5, `tags.test.ts` 5, `feed-view.test.tsx` 15,
  `card-item.test.tsx` 4, `conventions.test.ts` 3 — T1–T33 all pass, several
  as `it.each` expansions of a single T-id). None of the 8 red-phase test
  files were edited.
- Four green gates, all exit 0 in `apps/web/`: `npm test`, `npm run lint`
  (0 errors), `npm run typecheck`, `npm run build`.
- `uv run pytest tests/` → 350 passed (spec's documented baseline 349,
  predates this session); `git status --porcelain` confirmed empty for every
  backend path throughout.
- AD-9 outcome: doc research only (Task 4.11's live check is out of scope for
  this pass) — inconclusive on the specific `signal`/Data-Cache interaction;
  `signal` **kept**. See Task 4.12's note and `audit.md`'s Audit Log.
- Task 4.11 (the live browser smoke check) was **not run** in this pass, by
  explicit instruction — deferred to a separate session with real browser
  tooling. R15 and M-* items in `audit.md` stay `PENDING`.

**2026-09-18 — Fix-up pass: closed the four open audit reservations (R9, C25,
C27/T27/T28, and the undeclared AGENTS.md/CLAUDE.md finding).**

- `card-item.tsx` now renders the `.urlLine` anchor (title-adjacent, above the
  summary) using the already-verbatim `feed.module.css` class; T27/T28
  (amended by the test-writer, human-approved) went from red to green with no
  test-file edits in this pass. `npm test -- card-item` → 4/4; full
  `npm test` → 8/8 files, 55/55 tests — no other test needed reconciling.
- `apps/web/.gitignore` gained `!.env.example` after the `.env*` line (R9).
  `git check-ignore apps/web/.env.example` (no `-v`) now exits 1;
  `git add -n apps/web/.env.example` → `add 'apps/web/.env.example'`.
- `next.config.ts` gained `agentRules: false` (verified against
  `node_modules/next/dist/server/lib/start-server.js`'s own gate on that key);
  `apps/web/AGENTS.md` and `apps/web/CLAUDE.md` deleted; `npm run dev` run
  briefly (curl → `200`), killed, neither file reappeared.
- AD-9/C25: the human made a final, explicit acceptance decision (keep
  `signal`, non-blocking residual risk) rather than commissioning further live
  investigation — recorded as a dated Audit Log entry in `audit.md`, not left
  open.
- Final gate, from `apps/web/`: `npm test`, `npm run lint`, `npm run typecheck`,
  `npm run build` — see the Completion note this pass adds below for exact
  numbers. `git status --porcelain` confirmed no change outside
  `apps/web/`, `apps/web/.gitignore`, and `specs/web-feed-ui/{audit.md,tasks.md}`.

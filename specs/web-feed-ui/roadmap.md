# Roadmap: web-feed-ui

Build order is inside-out: toolchain first (nothing else can be verified without
it), then the generated contract (every module below depends on its types), then
pure logic, then rendering, then the whole thing verified locally. **Phase 5 is a
manual runbook for the human — it contains no executor tasks.**

Nothing outside `apps/web/` is created or modified except `.gitignore`,
`README.md`, and `CLAUDE.md`. No Python file, no `infra/` file, no
`docs/api/feed-api.v1.schema.json` byte.

## Implementation Phases

### Phase 1: Scaffold + toolchain

**Goal**: `apps/web/` exists as a Next 16 App Router TypeScript project that
builds, lints, typechecks, and runs an empty test suite — all with npm, all
locally, all committed to git with the right ignores.
**Dependencies**: None (Node 24.16.0 / npm 11.13.0 already installed).
**Estimated complexity**: Low

1. Scaffold:
   ```bash
   npx create-next-app@latest apps/web \
     --ts --app --eslint --no-tailwind --no-src-dir \
     --use-npm --disable-git --no-agents-md --import-alias "@/*"
   ```
   (`--no-*` negation is documented in the Next 16 CLI reference. If any flag is
   rejected by the installed CLI version, drop that flag and reconcile the
   generated project to this spec by hand — do **not** switch package managers
   or add Tailwind.)
2. Trim the scaffold to an empty shell: delete the demo markup/assets from
   `app/page.tsx`, replace `app/globals.css` with a minimal reset + the type
   accent custom properties (AD-7), keep `app/layout.tsx` with a real
   `metadata` title ("AI Radar — curated AI news").
3. Verify the ESLint setup is the Next 16 one: `eslint.config.mjs` importing
   `eslint-config-next/core-web-vitals`, and `"lint": "eslint"` in
   `package.json` (**not** `next lint`, which no longer exists).
4. Add Vitest: `npm i -D vitest @vitejs/plugin-react jsdom @testing-library/react
   @testing-library/jest-dom`, then `vitest.config.mts`
   (`environment: 'jsdom'`, `setupFiles: ['./vitest.setup.ts']`,
   `plugins: [react()]`, `resolve.alias` mirroring the `@/*` tsconfig path so no
   extra resolver dependency is needed) and `vitest.setup.ts`
   (`import '@testing-library/jest-dom/vitest'`).
5. Add the scripts from contract.md's `package.json` block
   (`typecheck`, `test`, `test:watch`, `generate:types`).
6. Repo root `.gitignore`: append `node_modules/`, `.next/`, `out/`, `.vercel/`,
   `*.tsbuildinfo`, `apps/web/.env*.local` (keeping the scaffold's own
   `apps/web/.gitignore` if create-next-app wrote one).
7. Prove the toolchain: `npm run build`, `npm run lint`, `npm run typecheck`,
   `npm test` (zero tests is a pass at this point) all exit 0.

### Phase 2: The generated contract + the typed client

**Goal**: TypeScript types that provably match
`docs/api/feed-api.v1.schema.json`, and a client that turns
`GET /v1/cards` into a normalised `FeedPage` — with the Guarantee-4 drain — all
testable without a browser or a network.
**Dependencies**: Phase 1
**Estimated complexity**: Medium

1. `npm i -D json-schema-to-typescript`; write
   `scripts/generate-api-types.mjs` (`compileFromFile` with
   `additionalProperties: false` and the DO-NOT-EDIT banner — the mirror of
   `export_api_schema.py`).
2. Run `npm run generate:types`; commit `features/feed/types.generated.ts`.
   **Read the output** and confirm the three optional fields
   (`tags?`, `takeaways?`, `next_cursor?`) appear as `?:` — that is correct and
   must not be hand-edited (contract.md's pinned surface).
3. `features/feed/client.ts`: `PAGE_SIZE`, `REVALIDATE_SECONDS`,
   `FETCH_TIMEOUT_MS`, `REQUIRED_STRING_FIELDS`, `FeedApiError`, `isCardOut`,
   `feedApiBaseUrl()`, `fetchFeed()` — exactly one `fetch` per call, `cursor`
   verbatim, `{ next: { revalidate: REVALIDATE_SECONDS } }`, `signal:
   AbortSignal.timeout(FETCH_TIMEOUT_MS)`, per-card skip with a `skipped`
   counter.
4. `features/feed/load-feed.ts`: `MAX_DRAIN_REQUESTS = 5` and `loadFeed()` —
   drain only while the page is **empty** and a cursor exists; return
   immediately on the first non-empty page; never drain a short-but-non-empty
   page.
5. `features/feed/href.ts` (`feedHref`) and `features/feed/tags.ts`
   (`topTags`, `MAX_TAG_CHIPS`) — pure functions, no React import.

### Phase 3: Rendering

**Goal**: The four UI states, the card, the tag chips, and the pagination links
exist and are wired to a thin async page.
**Dependencies**: Phase 2
**Estimated complexity**: Medium

1. `features/feed/card-item.tsx` — the HTML port of `render()` in
   `src/shared/cards.py`: title→`url` (`target="_blank" rel="noopener
   noreferrer"`), summary, takeaway bullets, tag chips, and the
   `TYPE · relevance n/10 · source · published` meta line. `tags`/`takeaways`
   `undefined`-safe; `published === ""` → `date n/a`.
2. `features/feed/tag-filter.tsx` and `features/feed/pagination.tsx` — links
   only, built exclusively through `feedHref`. "Next page" renders iff
   `nextCursor !== null`.
3. `features/feed/feed-view.tsx` — the exhaustive switch over `FeedViewState`
   producing exactly one of `feed-list` / `feed-empty` / `feed-no-match` /
   `feed-error`, each with a stable `data-testid` and distinct copy (including
   the "searched the first N pages" wording when the drain cap was hit with a
   live cursor).
4. `features/feed/feed.module.css` + the globals: type accent colours ported
   from `_TYPE_COLOR` with a neutral fallback for an unknown type; readable
   line length; no framework.
5. `app/page.tsx` — the ~25-line shell from contract.md: await `searchParams`,
   normalise `tag`/`cursor`, `try { loadFeed } catch { log + error state }`,
   render `<FeedView>`. Keep it thin; any branching added here belongs in
   `FeedView` instead (AD-8).
6. `.env.example` (in `apps/web/`) documenting `FEED_API_BASE_URL`, and a local
   `.env.local` for development (gitignored, not committed).

### Phase 4: Tests & local validation

**Goal**: Every Behavior Guarantee that can be checked without a deploy is
checked; the suite is hermetic; the app is proven to render real cards against
the real API from localhost.
**Dependencies**: Phase 3
**Estimated complexity**: Medium

1. `features/feed/types.generated.test.ts` — regenerate in-memory and compare to
   the committed file (drift); assert the interfaces' field-name sets against
   the artifact's `properties` keys; assert `REQUIRED_STRING_FIELDS` equals
   `$defs.CardOut.required` minus `relevance`.
2. `features/feed/client.test.ts` — stubbed `globalThis.fetch`: exactly one
   request; URL/query construction (`limit` always, `tag`/`cursor` iff
   non-empty); cursor byte-identical; `revalidate` option passed; missing
   `FEED_API_BASE_URL` → `FeedApiError('config')` **before** any fetch; 400/429/
   5xx → `'http'` with status; non-JSON/`cards` not an array → `'malformed'`;
   rejection → `'network'`; malformed card skipped + counted; `next_cursor`
   `undefined`/`""`/`null` all normalise to `null`.
3. `features/feed/load-feed.test.ts` — the live-verified fixture
   (`{cards: [], next_cursor: "<token>"}`) drains and finds a later page; a
   non-empty short page is returned after exactly one request; the drain stops
   at `MAX_DRAIN_REQUESTS` and returns the live cursor; each drain hop sends the
   previous `next_cursor` verbatim.
4. `features/feed/href.test.ts` + `tags.test.ts` — omitted empty params, cursor
   encoding round trip, deterministic top-N tag ordering with the alphabetical
   tie-break, `tags: undefined` contributing nothing.
5. `features/feed/feed-view.test.tsx` + `card-item.test.tsx` (jsdom + RTL) —
   the four states render exclusively and identifiably; API order is preserved
   for a deliberately non-alphabetical, non-relevance-sorted fixture; all card
   fields render; `tags`/`takeaways` `undefined` renders nothing rather than
   throwing; the "next page" link appears iff `nextCursor !== null` (including
   on an empty page); tag chips link to `/?tag=…`; the error state shows no
   status code, base URL, or stack.
6. Guard tests for the cross-cutting rules: no `NEXT_PUBLIC_` identifier and no
   `execute-api` literal anywhere under `apps/web` application code; no
   `"use client"` module imports `client.ts`; no `sort(`/`reverse(` in
   `features/feed/`.
7. Green gates: `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`
   — all exit 0. Then `uv run pytest tests/` (expect **349 passed**, unchanged)
   and `git status` to confirm nothing under `src/`, `tests/`, `infra/`, or
   `docs/api/` moved.
8. **Local live smoke check** (read-only, no deploy): with `.env.local` pointing
   at the real API, `npm run dev` → open `http://localhost:3000` and confirm
   real cards render, a tag chip narrows the feed, "Next page" reaches distinct
   cards, and `/?tag=zzz-no-such-tag` shows `feed-no-match` (not a blank page).
   Also confirm the unreachable state by temporarily setting
   `FEED_API_BASE_URL=http://127.0.0.1:9` and reloading. Record what was
   observed in `audit.md`.
9. Documentation the executor **may** write (no deploy required):
   `README.md`'s `web-feed-ui` row + a "Run the web feed locally" section + the
   Phase 5 runbook below transcribed with `<placeholders>` for the values only
   the human's deploy can produce; and the one-sentence `CLAUDE.md` "Current
   state" pointer.

### Phase 5: MANUAL — human deploy runbook (NOT executor tasks)

**Goal**: The feed is live at a real Vercel URL and `feed-api`'s CORS allow-list
names that origin.
**Dependencies**: Phase 4 complete and committed.
**Estimated complexity**: Low (but requires a Vercel account and AWS credentials
— neither of which any agent has or should assume).
**Owner**: the human. An agent must not run any command in this phase.

1. **Create the Vercel project.**
   - Import the repository at <https://vercel.com/new>.
   - **Root Directory: `apps/web`** (this is the one setting that must not be
     left at the repo root).
   - Framework preset: Next.js (auto-detected). Build/install commands: leave
     as detected (`next build` / `npm install`).
   - Environment Variables → add for **Production** (and Preview, if wanted):
     ```
     FEED_API_BASE_URL = https://fdcksuokyh.execute-api.us-east-1.amazonaws.com
     ```
     No `NEXT_PUBLIC_` prefix — it is server-only by design (AD-4).
   - Deploy. Record the production URL, e.g.
     `https://<project>.vercel.app`.
   - CLI alternative, if preferred: `npm i -g vercel && vercel link && vercel
     env add FEED_API_BASE_URL production && vercel --prod`, run from
     `apps/web/`.
2. **Verify the deployed page in a browser** (the acceptance criteria the
   automated suite cannot reach):
   - real cards render, ordered by relevance then date;
   - clicking a tag chip narrows the feed and the URL becomes `/?tag=<x>`;
   - "Next page →" shows cards not present on page 1 (spot-check two
     `card_id`s — or two titles — for disjointness);
   - `/?tag=zzz-no-such-tag` renders the no-match state, not a blank page.
3. **Update `feed-api`'s CORS allow-list** (this is why it could not be done
   earlier — it needs the real origin):
   ```bash
   uv sync --group infra
   # Option A (preferred, no code change; keep localhost for local dev):
   uv run cdk deploy --app "python infra/app.py" AiRadarFeedApi \
     -c feed_api_allowed_origins="http://localhost:3000,https://<project>.vercel.app" \
     -c feed_api_reserved_concurrency=none      # ONLY if the AWS Support quota
                                                # case 178836416700301 is still
                                                # open — see specs/feed-api/tasks.md 6.2
   # Option B (durable): edit DEFAULT_ALLOWED_ORIGINS in infra/lib/feed_api.py,
   # update tests/test_infra_feed_api.py's origin assertion, then deploy with
   # no -c override.
   ```
   Run `uv run cdk diff --app "python infra/app.py" AiRadarFeedApi` first and
   confirm the **only** change is `CorsConfiguration.AllowOrigins`.
4. **Verify CORS by curl** (both halves, as `feed-api` did):
   ```bash
   API=https://fdcksuokyh.execute-api.us-east-1.amazonaws.com
   curl -si -H "Origin: https://<project>.vercel.app" "$API/v1/cards?limit=1" \
     | grep -i access-control-allow-origin      # EXPECT: the Vercel origin
   curl -si -H "Origin: https://evil.example.com" "$API/v1/cards?limit=1" \
     | grep -i access-control                   # EXPECT: no output at all
   ```
5. **Record the real values** in `README.md` (replace the `<placeholders>`): the
   Vercel URL, the origin now allow-listed, the deploy date, and the teardown
   steps (delete the Vercel project; redeploy `AiRadarFeedApi` with the origin
   list back to `http://localhost:3000`). Update `specs/web-feed-ui/audit.md`'s
   manual-verification rows with what was actually observed.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Generated types drift from Spec 01's schema | Low | **High** | AD-3: generated + committed + two drift tests. This is the risk the whole spec is shaped around |
| A naive read of an empty-but-cursored page shows "no matches" wrongly | **High** without mitigation | Med | AD-6's bounded drain, built from the *live-verified* `?tag=zzz-no-such-tag` response, plus explicit tests and honest "searched N pages" copy |
| `create-next-app` scaffolds a shape this spec didn't anticipate (Turbopack/React-Compiler defaults, `AGENTS.md`, a different ESLint layout) | Med | Low | Phase 1 step 2/3 reconciles the scaffold explicitly; the flags are from the Next 16 CLI reference. Never "fix" it by adding Tailwind or switching package manager |
| `AbortSignal` silently disables Next's Data Cache (AD-9's open question) | Med | Low | One-line removal, fallback written down, finding recorded in `audit.md` — the `feed-api` AD-6 pattern |
| Vercel build fails because the schema JSON is outside the Root Directory | Low | Med | Structurally impossible: `types.generated.ts` is committed and codegen is a dev-only script never invoked by `next build` |
| The human's CDK redeploy fails on the unrelated Lambda concurrency quota | Med | Low | Phase 5 step 3 carries the `-c feed_api_reserved_concurrency=none` bridge flag and points at `specs/feed-api/tasks.md` 6.2 |
| Page views amplify API Gateway request-count spend (`feed-api` AD-7's residual) | Low | Low | AD-9's `revalidate: 300`, AD-6's hard drain cap, no polling/retry; the deployed `AiRadarBudget` SNS alerts remain the backstop |
| An agent tries to deploy to Vercel or `cdk deploy` | Low | **High** (unauthorised change to live infra) | AD-10: Phase 5 has no executor tasks; `tasks.md` repeats the prohibition in its Notes |
| Scope creep into a client-side data layer, a design system, or a per-card page | Med | Med | Explicit Non-Goals; `architecture-principles.md`'s frontend rule quoted in the contract |
| 281 long-tail tags make the chip row useless | Med | Low | AD-11: top-12 per page + every card tag clickable + honest copy |
| Someone "fixes" the optional `tags?`/`next_cursor?` types by hand-editing the generated file | Med | Med | DO-NOT-EDIT banner + the regeneration drift test fails immediately |

## File Change Map

**Create — app shell (Phase 1)**
- `apps/web/package.json` — CREATE — deps + the pinned scripts
- `apps/web/package-lock.json` — CREATE — the single Node lockfile
- `apps/web/tsconfig.json` — CREATE — scaffolded, `strict` on
- `apps/web/next.config.ts` — CREATE — scaffolded, no `eslint` key (removed in 16)
- `apps/web/eslint.config.mjs` — CREATE — flat config, `eslint-config-next/core-web-vitals`
- `apps/web/vitest.config.mts` — CREATE — jsdom + react plugin + `@/*` alias
- `apps/web/vitest.setup.ts` — CREATE — `@testing-library/jest-dom/vitest`
- `apps/web/.env.example` — CREATE — `FEED_API_BASE_URL`, server-only note
- `apps/web/.gitignore` — CREATE — scaffolded (`.next/`, `node_modules/`, `.env*.local`)
- `apps/web/README.md` — CREATE — short pointer to the repo README's runbook
- `apps/web/app/layout.tsx` — CREATE — shell + metadata
- `apps/web/app/globals.css` — CREATE — reset + type accent custom properties

**Create — contract + logic (Phase 2)**
- `apps/web/scripts/generate-api-types.mjs` — CREATE — codegen (mirror of `export_api_schema.py`)
- `apps/web/features/feed/types.generated.ts` — CREATE — **generated**, committed, never hand-edited
- `apps/web/features/feed/client.ts` — CREATE — the only `fetch` site; `FeedApiError`, `isCardOut`, `fetchFeed`
- `apps/web/features/feed/load-feed.ts` — CREATE — bounded empty-page drain (AD-6)
- `apps/web/features/feed/href.ts` — CREATE — the only feed-URL builder
- `apps/web/features/feed/tags.ts` — CREATE — `topTags` (AD-11)

**Create — rendering (Phase 3)**
- `apps/web/app/page.tsx` — CREATE — thin async shell (AD-8)
- `apps/web/features/feed/feed-view.tsx` — CREATE — the four exhaustive states
- `apps/web/features/feed/card-item.tsx` — CREATE — HTML port of `cards.py`'s `render()`
- `apps/web/features/feed/tag-filter.tsx` — CREATE — chip row + clear link
- `apps/web/features/feed/pagination.tsx` — CREATE — next/first-page links
- `apps/web/features/feed/feed.module.css` — CREATE — component styles

**Create — tests (Phase 4)**
- `apps/web/features/feed/types.generated.test.ts` — CREATE — schema drift + field-set parity
- `apps/web/features/feed/client.test.ts` — CREATE
- `apps/web/features/feed/load-feed.test.ts` — CREATE
- `apps/web/features/feed/href.test.ts` — CREATE
- `apps/web/features/feed/tags.test.ts` — CREATE
- `apps/web/features/feed/feed-view.test.tsx` — CREATE
- `apps/web/features/feed/card-item.test.tsx` — CREATE
- `apps/web/features/feed/conventions.test.ts` — CREATE — no `NEXT_PUBLIC_`, no `execute-api` literal, no client-side fetch, no sorting

**Modify (repo root)**
- `.gitignore` — MODIFY — Node/Next/Vercel ignores
- `README.md` — MODIFY — Phase 2 table row + local-dev section + the manual Vercel/CORS runbook
- `CLAUDE.md` — MODIFY — one sentence in "Current state" pointing at the README table

**Human-only, later (Phase 5) — NOT executor edits**
- Vercel project settings (Root Directory `apps/web`, `FEED_API_BASE_URL`)
- `infra/lib/feed_api.py` — MODIFY *(optional Option B)* — add the real Vercel origin to `DEFAULT_ALLOWED_ORIGINS`
- `tests/test_infra_feed_api.py` — MODIFY *(only if Option B is taken)* — update the origin assertion
- `README.md` / `specs/web-feed-ui/audit.md` — MODIFY — fill in the real URL, origin, and observations

**Explicitly NOT touched (by anyone, at any phase)**
- `src/**`, `tests/**` *(except the one infra origin assertion under Option B)*,
  `infra/**` *(except the origin constant under Option B)*, `docs/api/**`,
  `pyproject.toml`, `uv.lock`, `Dockerfile`, `Dockerfile.feed_api`,
  `export_api_schema.py`, `runtime_app.py`, `run_curation.py`, `run_chat.py`

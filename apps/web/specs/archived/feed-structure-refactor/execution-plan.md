# Execution Plan: feed-structure-refactor

## Guidance consulted
- `apps/web/AGENTS.md`: WEB-1 to WEB-9, the colocated-test style, npm only, deployment is human-run.
- Repo-root `CLAUDE.md`: ADRs are monotonic across both harness roots (next is 0008), and there are two harny roots.
- `harny-sync` lookup: `specs/current/_index.md` and `specs/current/web-feed.md`. This covers WEB-1 to WEB-11, invariants 1 to 3, reservations WEB-R1 to WEB-R3, and ADRs 0001 to 0007.
- Source files read:
  - `app/page.tsx` and `app/layout.tsx`;
  - every file under `features/feed/`;
  - `scripts/generate-api-types.mjs`;
  - `package.json`, `tsconfig.json` (`@/*` maps to `./*`, and `include` covers `**/*.ts`), `eslint.config.mjs`, `vitest.config.mts` (`@` alias, default include globs, jsdom), `.gitignore`, `.env.example`, `.env.local`;
  - `.github/workflows/harny-feedback-web.yml` (eslint and tsc only, no tests).
- Existing e2e state:
  - `e2e/` holds only empty directories: `__baseline__/{dom,styles,console,stderr}` and `.tmp/`.
  - `app/__golden__/` is empty.
  - `test-results/.last-run.json` is a leftover from an earlier Playwright run.
  - `@playwright/test@1.63.0` is already in `node_modules`, but only as an extraneous copy deduped under `next`'s optional peer. It is not declared in `package.json`.
  - The Chromium revision 1243 that 1.63 needs is already in `~/Library/Caches/ms-playwright`.
- Build output in `.next/static/**/*.css`: Turbopack emits CSS-module classes as `feed-module__<hash>__<local>` (for example `feed-module__OhSvhG__feedPage`). The hash depends on the file path, so moving the CSS file changes the class attribute strings.
- Path references found by grep: `README.md` (repo root, around lines 702–736), `AGENTS.md` (lines 19 and 53), `specs/current/web-feed.md`, the `tags.ts` comment, the `feed.module.css` header comment, and `tasks/phase-2-web-feed/02-web-feed-ui.md` (historical; leave it).

## Ownership
- `apps/web/features/feed/**`, `apps/web/app/page.tsx`, `apps/web/scripts/generate-api-types.mjs`.
- New e2e tooling in `apps/web/`: `playwright.config.ts`, `e2e/**`, plus `package.json`/`package-lock.json`, `.gitignore` and `eslint.config.mjs`. The ESLint change only adds ignore entries.
- Affected `specs/current` capabilities: `web-feed`. Changes needed: file paths in WEB-2, WEB-9 and WEB-R3, and a refinement of invariant 3. `harny-sync` applies them at archive time.

## Binding constraints
- No behavior, markup, copy or CSS change. `feed.module.css` and `types.generated.ts` move byte-identical (source: intent Out, WEB-9, WEB-2).
- Every `feed-api` fetch stays server-side. `index.ts` re-exports server-only code (`loadFeedState` reaches `client.ts`), so a `"use client"` module must never import the barrel or `api/` (source: WEB-1, ADR 0002).
- Cursors pass through byte-identical. Nothing parses, trims or logs a cursor value (source: WEB-3, invariant 2).
- There is still exactly one render state per request, and all render branching stays in `FeedView`. `loadFeedState` only decides between `ok` and `error` (source: WEB-5, invariant 3).
- The `feed_fetch_failed` log line keeps the same keys, the same order and the same omission of undefined values. It never includes the error message or the cursor value (source: WEB-5, current `app/page.tsx`).
- Code under `features/` contains no `.sort(` or `.reverse(` (source: WEB-3, T31).
- Existing test assertions are untouched. Only import specifiers, `vi.mock` specifiers, path constants and comments about paths may change (source: human brief).
- Move files with `git mv` so `git diff -M` shows renames (source: AC8 auditability).
- `@playwright/test` is the only new package. It is a devDependency and a human-sanctioned exception. There is no `server-only` package, no stub-server library and no snapshot library. The stub uses `node:http` only (source: human brief).
- E2e never contacts AWS. `FEED_API_BASE_URL` for the app under test is set explicitly to the local stub. Next does not overwrite a process env var with `.env.local`, so the real URL in `.env.local` is never used. The suite never reuses a server it did not start (source: human brief, AC10).
- No `NEXT_PUBLIC_` or `execute-api` literal appears in any new file (source: WEB-1, T29).
- Deployment stays human-run. The executor runs the WEB-11 local smoke check and nothing more (source: WEB-11, ADR 0007).

## Proposed approach
Revisable by the executor if it records why.

- Decision: target layout.
  ```
  features/feed/
    index.ts                       # public entry point
    conventions.test.ts            # stays; cross-cutting guard (path constants unchanged)
    api/        client.ts, load-feed.ts, types.generated.ts, load-feed-state.ts (+ *.test.ts)
    components/ feed-view.tsx, card-item.tsx, tag-filter.tsx, pagination.tsx, feed.module.css (+ *.test.tsx)
    lib/        href.ts, tags.ts, search-params.ts (+ *.test.ts)
  ```
  Rationale: this is the role split the human asked for. `api/` is everything that is server-only or comes from the contract. `components/` is rendering. `lib/` is pure helpers that are safe on the client. `conventions.test.ts` stays at the root because it guards all of `features/` and `app/`, not one sub-folder. Staying put also leaves its `../../../..` constant valid.
  Rejected: moving it to `lib/`. That would change a path constant and misdescribe its scope.

- Decision: the barrel's export surface is exactly these three values.
  ```ts
  // features/feed/index.ts
  export { FeedView } from './components/feed-view'
  export { loadFeedState } from './api/load-feed-state'
  export { parseFeedSearchParams } from './lib/search-params'
  ```
  It has no `export *` and no type exports.
  Rationale: the human asked for "only what `app/` needs". `page.tsx` no longer names `FeedViewState`, because TypeScript infers it. Explicit named re-exports keep the surface auditable, and adding an export becomes a visible diff.
  Rejected: `export *`, which leaks every helper. Also rejected: also exporting `type FeedViewState`, since no current consumer needs it.

- Decision: `loadFeedState` lives in `api/load-feed-state.ts`.
  Rationale: it is server-only orchestration. It calls `loadFeed`, imports `FeedApiError` and logs to the server. Putting it in `api/` means one rule ("no client module imports `api/` or the barrel") covers every server-only module.
  It imports `FeedViewState` with `import type` from `../components/feed-view`. That import is erased at compile time, so it adds no runtime edge from `api/` to `components/`.
  Rejected: placing it at the feature root, which adds a fourth category. Also rejected: placing it in `lib/`, which would put server-only code into a folder that is safe on the client.

- Decision: `FeedViewState` stays defined, unchanged, in `components/feed-view.tsx`.
  Rationale: it is `FeedView`'s prop contract. Moving it would churn `feed-view.tsx` and gain nothing.
  Rejected: a separate `types.ts`, which would be speculative structure (see `docs/architecture-principles.md`'s "no speculative interfaces").

- Decision: search-param parsing becomes `parseFeedSearchParams` in `lib/search-params.ts`. It is pure and safe on the client, and its rules are pinned in AC4. `loadFeedState` keeps the requested `({ tag, cursor })` signature and receives values that are already normalized.
  Rationale: `FeedView` needs the normalized `tag` and `cursor` as well as the state, so the parsing has to be callable by `page.tsx` on its own. This is open question 1 in the intent.
  Rejected: having `loadFeedState` take raw `searchParams` and return `{ state, tag, cursor }`. That would break the signature the human asked for.

- Decision: the final shape of `page.tsx`, shown here only for orientation.
  ```tsx
  import { FeedView, loadFeedState, parseFeedSearchParams } from '@/features/feed'

  export default async function Page({ searchParams }: { searchParams: Promise<{ [key: string]: string | string[] | undefined }> }) {
    const { tag, cursor } = parseFeedSearchParams(await searchParams)
    const state = await loadFeedState({ tag, cursor })
    return <FeedView state={state} tag={tag} cursor={cursor} />
  }
  ```

- Decision: WEB-1 enforcement means extending `conventions.test.ts` with new `it` cases. The three existing cases T29, T30 and T31 stay byte-identical, and their scan helpers may be reused. The new cases are:
  1. Deep-import ban (AC2). Scan every source file in `apps/web` outside `features/feed/`: `.ts`, `.tsx`, `.mts` and `.mjs` in `app/`, `e2e/`, `scripts/` and the root config files, but not `node_modules/` or `.next/`. A file fails if any import specifier resolves into `features/feed/<sub-folder>/`. This catches the `@/features/feed/x/...` and `../features/feed/x/...` forms.
  2. Barrel export surface (AC2). Assert that `Object.keys(await import('./index'))` sorted equals `['FeedView', 'loadFeedState', 'parseFeedSearchParams']`. This is a runtime check, not a source grep. The test needs only key names, so it must stub `./api/client` (or the network) if importing has side effects. Importing has none today.
  3. No self-import of the barrel inside `features/feed/` (AC2).
  4. A `"use client"` module must not import the barrel or `api/` (AC3).
  5. Files under `components/` and `lib/` may import from `api/` only with `import type` (AC3).

  Rationale: this is the repo's existing way of enforcing WEB-1 (`AGENTS.md` allows source-grep tests only in this guard), and it runs in `npm test`. T30's `/\/(client|load-feed)$/` regex still matches `../api/client`, but it would miss a barrel import, which is why case 4 exists.
  Rejected: ESLint `no-restricted-imports` with per-directory overrides. It would work, but it would create a second enforcement mechanism for one rule. The executor may add it as well, but not instead.

- Decision: e2e architecture, all of it local.
  - **Stub.** `e2e/stub/feed-api-stub.mjs` is a stateless `node:http` server on a fixed port (suggested: 4010) that serves `GET <prefix>/v1/cards`. Each response is a pure function of the request's prefix, `tag` and `cursor`. Because the stub keeps no state, the Next Data Cache (`revalidate: 300`, WEB-6, WEB-R2) cannot make scenarios interfere with one another.
  - **Fixtures.** Committed JSON with unique, recognizable titles (for example "E2E fixture card 1"), so a rendered page proves where its data came from. Coverage needs:
    - mixed `type` values (to exercise the `data-type` accent selectors);
    - more than 12 distinct tags, so that a tag outside the promoted chips exists;
    - a card with no `tags` or `takeaways`;
    - a card with `published: ''`;
    - a `next_cursor` containing `+`, `/` and `=`.
  - **App under test.** One `next build`, then two `next start` instances from that build, declared as a Playwright `webServer` array together with the stub:
    - "populated" on port 3100, with `FEED_API_BASE_URL=http://127.0.0.1:4010/populated`;
    - "empty" on port 3101, with `FEED_API_BASE_URL=http://127.0.0.1:4010/empty`, so the first-page `feed-empty` state is reachable at `/`.
    The app appends `/v1/cards` to the base URL, and a path prefix works with that. Set `reuseExistingServer: false`. Clear `.next/cache/fetch-cache` before starting, so a cached response from an earlier run cannot leak in.
    Rejected: a single instance with `/?cursor=<exhausted>` standing in for empty. That does not exercise the true first-page empty render. Also rejected: a mutable stub control endpoint, which the Data Cache could break.
  - **Scenario routing (suggested).** On the populated prefix:
    - no tag: page 1 with a cursor, then page 2 with `next_cursor: null`;
    - `tag=agents`: filtered cards;
    - `tag=no-such-tag`: `{cards: [], next_cursor: null}`;
    - `tag=drain`: always empty with a fresh cursor, which hits the 5-request cap;
    - `tag=late`: one empty page with a cursor, then a non-empty page;
    - `tag=http-500`: a 500 response;
    - `tag=malformed`: a 200 response whose body is not JSON;
    - `tag=network`: the socket is destroyed, so the request ends in a `network` error.
  - **Baseline capture.** `e2e/__baseline__/`, following the existing sub-directory names.
    - `dom/`: the `outerHTML` of the `FeedView` root (the body's first child, the `feedPage` element), normalized as follows. Each CSS-module class token is rewritten to `<file>-module__<local>`, with the hash removed. Attribute order and text are kept exactly. Nothing else is rewritten. In particular, hrefs and cursors are left as they are.
    - `styles/`: `getComputedStyle` values for a fixed selector list in each state: masthead, wordmark, card (one per fixture `type`), chip, active chip, pager link, state box, error state. Properties: color, background-color, border, padding, margin, font-size and font-weight at minimum. Capturing the full computed style map is acceptable.
    - `console/`: browser console messages. There must be zero errors and zero hydration warnings.
    - `stderr/` (optional): the `feed_fetch_failed` lines from the server stderr of the error scenarios, captured by redirecting the server's stderr to `e2e/.tmp/`. AC5's unit test already pins the line exactly, so this is extra evidence.

    Use Playwright `expect(...).toMatchSnapshot(...)`, with `snapshotPathTemplate` pointed at `e2e/__baseline__/{arg}{ext}` so no platform suffix is added. Pixel screenshots are optional. If they are used, keep them out of the committed baseline, because they depend on the platform.
  - **Collection separation.** Name e2e files `*.e2e.ts` and set Playwright `testMatch` to that pattern. Vitest's default include (`*.test.*` / `*.spec.*`) then never collects them, and `vitest.config.mts` stays unchanged.
    Rejected: `*.spec.ts`, which Vitest would collect.
  - **Ignores.** Add `/test-results/`, `/playwright-report/`, `/blob-report/` and `/e2e/.tmp/` to `.gitignore`. Add `playwright-report/**`, `test-results/**` and `e2e/.tmp/**` to the ESLint `globalIgnores`. Use the `list` reporter, or `html` with `open: 'never'`.

- Decision: the order of work is baseline first, then refactor.
  - The e2e suite is written and run against the unmodified tree at base commit `d343830`, and its baseline is recorded. Record a SHA-256 for every file under `e2e/__baseline__/` in `tasks.md`.
  - The refactor follows. After it, `npm run test:e2e` runs without `--update-snapshots`, and the baseline checksums must be unchanged.
  - At the red-test gate the e2e suite is expected to be green on the old code, because it is a characterization suite. Only the `loadFeedState`, `parseFeedSearchParams` and new conventions cases are expected to be red.

- Decision: the documentation role may write ADR 0008 for the feature-layout and public-entry-point convention, if the human wants one (intent open question 4). This plan does not require it.

## Consumers and migration
- **`app/page.tsx`.** It is the only importer outside the feature. It is rewritten to the shape in AC6 and imports only from `@/features/feed`.
- **Imports inside the feature.** They become relative across sub-folders, for example `components/feed-view.tsx` -> `../api/client` and `../lib/href`.
- **Existing tests.** Each moves with `git mv` next to its source. The changes are:
  - `client.test.ts` and `load-feed.test.ts` -> `api/`. `vi.mock("./client")` still resolves because the test sits next to `client.ts`. Only the `./types.generated` import stays the same, since it is in the same folder.
  - `types.generated.test.ts` -> `api/`. The script import becomes `../../../scripts/generate-api-types.mjs`. `SCHEMA_PATH` becomes `../../../../../docs/api/feed-api.v1.schema.json`. `GENERATED_PATH` is unchanged. The comment "four levels up" becomes "five".
  - `card-item.test.tsx` and `feed-view.test.tsx` -> `components/`. `./client` becomes `../api/client`, and `./types.generated` becomes `../api/types.generated`.
  - `href.test.ts` and `tags.test.ts` -> `lib/`. `tags.test.ts` changes `./types.generated` to `../api/types.generated`.
  - `conventions.test.ts` does not move. T29 to T31 stay byte-identical, and new cases are appended.
- **`scripts/generate-api-types.mjs`.** `OUT` becomes `join(here, '../features/feed/api/types.generated.ts')`. The generated content does not change, because the banner contains no path.
- **`package.json`.**
  - Add `@playwright/test` as a devDependency with `npm install -D @playwright/test@1.63.0`. That is the version already resolved in the tree, and it matches cached Chromium 1243.
  - Add `"test:e2e": "playwright test"`.
  - `npx playwright install chromium` is expected to be a no-op on this machine.
  - `npm test` stays Vitest-only, so the harny readiness check and CI are unaffected.
- **`tsconfig.json`.** No change is needed. Its `**/*.ts` include will type-check `playwright.config.ts` and `e2e/**`, which needs `@playwright/test` declared, as above.
- **Documentation.** The documentation role handles this after the audit, not the executor:
  - `AGENTS.md` § Components tree and the WEB-1 line (`features/feed/conventions.test.ts` is still correct).
  - Repo-root `README.md` "Phase 2 — Web Feed" path references (around lines 702–736). `README.md` also needs the `npm run test:e2e` runbook line.
  - `specs/current/web-feed.md`: WEB-2 scenario path, WEB-9 path, WEB-R3 path, and invariant 3. `harny-sync` handles these in archive mode.
- **Not edited.**
  - The `feed.module.css` header comment (WEB-9).
  - `tasks/phase-2-web-feed/02-web-feed-ui.md` and `specs/archived/**`, which are historical.
  - The `tags.ts` comment ("features/feed's convention guard") is still accurate.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| CSS-module class hashes change because the CSS file's path changes. A naive DOM snapshot would then fail even though nothing changed visually. | High | Med | Normalize class tokens to `<file>-module__<local>` before snapshotting. Prove the styling is identical with the computed-style baseline and the SHA-256 match from AC9. |
| A `"use client"` file imports the barrel and pulls `client.ts` (`process.env`) into the client bundle. T30's regex would not catch that. | Low | High | New conventions cases 4 and 5 (AC3). |
| The Next Data Cache or a persisted `.next/cache/fetch-cache` serves a stale response across scenarios or runs. | Med | Med | A stateless, URL-keyed stub, static fixtures, and clearing the fetch cache before `next start`. |
| `.env.local`'s real AWS URL leaks into e2e, or Playwright reuses a dev server pointed at AWS. | Low | Med | Set `FEED_API_BASE_URL` explicitly in the `webServer.env` of each app instance. Set `reuseExistingServer: false`. Use fixture titles found nowhere else. |
| Vitest collects Playwright specs, or ESLint lints the HTML-report JavaScript. | Med | Low | Use the `*.e2e.ts` naming, `testMatch`, and the `.gitignore` and ESLint ignore entries. |
| ESLint's `react-hooks/rules-of-hooks` flags Playwright's fixture `use(...)` callback. | Low | Low | Avoid custom fixtures, or rename the parameter in fixture definitions. Do not disable the rule globally. |
| The baseline is accidentally regenerated after the refactor with `--update-snapshots`, which would hide a regression. | Low | High | Record baseline SHA-256 values in `tasks.md`, and have the auditor compare them. `git diff <baseline-commit> -- e2e/__baseline__` must be empty. |
| `npm install -D` resolves a newer Playwright than the cached browser. | Low | Low | Pin `@playwright/test@1.63.0`. If it drifts anyway, `npx playwright install chromium`. |
| A moved test is silently edited beyond its imports. | Low | High | Use `git mv`. The auditor reviews `git diff -M --stat` and each rename hunk (AC8). |

## Validation
One row per AC. All commands run from `apps/web/`.

| AC | Demonstrated by | Tests to write | Tier | Framework | Setup | Focused command | Broader command | Cwd |
|---|---|---|---|---|---|---|---|---|
| AC1 | The layout matches the target tree, and every moved test runs from its new location. | None new. Moved tests, plus a structural `it` in `conventions.test.ts` asserting the root holds only `index.ts`, `conventions.test.ts` and the three folders. | unit | Vitest | none | `npx vitest run features/feed/conventions.test.ts` | `npm test` | `apps/web` |
| AC2 | The guard fails on a deep import from outside the feature or a barrel self-import. The barrel's runtime keys equal exactly the three names. | New cases in `features/feed/conventions.test.ts`: deep-import ban, export-surface check, no self-import. | unit | Vitest | none | `npx vitest run features/feed/conventions.test.ts` | `npm test` | `apps/web` |
| AC3 | The guard fails on a `"use client"` import of the barrel or `api/`, and on a value import of `api/` from `components/` or `lib/`. T29 to T31 still pass. | New cases in `features/feed/conventions.test.ts`. Each case should also be shown to fail by adding a temporary violating fixture file (record the red result in `tasks.md`, then delete the file). | unit | Vitest | none | `npx vitest run features/feed/conventions.test.ts` | `npm test` | `apps/web` |
| AC4 | Every row of the AC4 rule table, including untrimmed tag, array values, whitespace tag, empty cursor, and a special-character cursor passed through byte-identical. | `features/feed/lib/search-params.test.ts` | unit | Vitest | none | `npx vitest run features/feed/lib/search-params.test.ts` | `npm test` | `apps/web` |
| AC5 | Success returns `ok` with the identical page object and logs nothing. A `FeedApiError` for each of `config`, `network`, `http` and `malformed` returns the matching code. A non-`FeedApiError` returns `network`. Each failure produces exactly one `console.error` with the exact JSON string. The function never throws. The log contains no cursor value and no error message. | `features/feed/api/load-feed-state.test.ts`, which mocks `./load-feed` with `vi.mock` and spies on `console.error`. | unit | Vitest | none | `npx vitest run features/feed/api/load-feed-state.test.ts` | `npm test` | `apps/web` |
| AC6 | `page.tsx` has the thin shape. Its rendered output is unchanged (covered by AC7). | None beyond the AC2 guard and AC7. The auditor reads `app/page.tsx` and runs the grep in AC6's example. | e2e, plus review | Playwright | via AC7 | `grep -nE "try\|catch\|console\|\.\./features" app/page.tsx` (expect no output) | `npm run test:e2e` | `apps/web` |
| AC7 | Every scenario listed in AC7 matches the pre-refactor baseline: normalized `FeedView` DOM, computed styles, and console with no errors. Navigation assertions: clicking a chip leads to `?tag=`; "Next page →" leads to a URL whose decoded `cursor` equals the fixture `next_cursor` byte-for-byte; Back restores the prior page. | `e2e/feed.e2e.ts` (one `describe` per state, plus navigation), `e2e/stub/feed-api-stub.mjs`, `e2e/fixtures/*.json`, `playwright.config.ts`. Optionally `e2e/__baseline__/stderr/*` for error scenarios. | e2e | Playwright (`@playwright/test` 1.63, Chromium) | Add the devDependency. `npx playwright install chromium`. Build, then a stub plus two `next start` instances via `webServer`. Capture the baseline on base commit `d343830` before any refactor edit, and record its SHA-256 values in `tasks.md`. | `npx playwright test e2e/feed.e2e.ts` | `npm run test:e2e` | `apps/web` |
| AC8 | All 55 original tests pass. Each moved test file shows as a rename whose hunks touch only import or mock specifiers, path constants and path comments. | none (migration) | unit | Vitest | none | `npm test` (55 original tests plus the new ones, all passing) | `git diff -M --stat d343830 -- features/feed` and a review of rename hunks | `apps/web` |
| AC9 | Codegen writes the new path with byte-identical output, and no file reappears at the old path. T1 to T3 pass from `api/`. SHA-256 matches for `components/feed.module.css` (`fedbe6ba…151f7`) and `api/types.generated.ts` (`405dab9e…deb7d`). | none new (moved `api/types.generated.test.ts`) | unit | Vitest | none | `npm run generate:types && git status --porcelain features/feed && npx vitest run features/feed/api/types.generated.test.ts` | `shasum -a 256 features/feed/components/feed.module.css features/feed/api/types.generated.ts` | `apps/web` |
| AC10 | `@playwright/test` is the only `package.json` addition. The e2e suite passes with `.env.local` unchanged, with the real URL still present, and with no AWS reachability. Lint, typecheck, unit tests and build are green. Vitest's run lists no `*.e2e.ts` file. `git status` shows no Playwright artifacts. | none (tooling) | e2e plus the existing gates | Playwright, Vitest, ESLint, tsc, next build | as in AC7 | `npm run test:e2e` | `npm run lint && npm run typecheck && npm test && npm run build && git diff d343830 -- package.json` | `apps/web` |
| WEB-11 (binding) | Local dev-server smoke check against the real `feed-api`: cards render, and a tag chip and "Next page →" work. | none (manual) | manual | browser | `.env.local` as it is today | `npm run dev`, then open `http://localhost:3000` | none | `apps/web` |

## Revision log
- Revision 1 (2026-10-03): initial draft.

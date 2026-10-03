# Intent: feed-structure-refactor

Shipped: 2026-10-03

Revision: 1
Approval: Approved revision 1 by Daniel Erazo on 2026-10-03

## Outcome
`apps/web/features/feed/` is reorganized by role into `api/`, `components/` and `lib/`, with each test next to its source. The feature has a single public entry point (`features/feed/index.ts`), and `app/page.tsx` imports only from it. The page's untested logic (search-param parsing, error-to-state mapping, the `feed_fetch_failed` log line) moves into tested feature functions. Behavior does not change: every page a user can reach renders the same DOM, styles, copy and links as before. A deterministic Playwright end-to-end suite proves this by checking the refactored app against a baseline captured from the pre-refactor app.

## Acceptance criteria
- **AC1** The feature folder is split by role, and each test sits next to its source. The only files left at the feature root are `index.ts` and the cross-cutting `conventions.test.ts`.
  Example: after the change, `features/feed/` contains exactly `api/` (`client.ts`, `load-feed.ts`, `types.generated.ts`, `load-feed-state.ts` and their `*.test.ts`), `components/` (`feed-view.tsx`, `card-item.tsx`, `tag-filter.tsx`, `pagination.tsx`, `feed.module.css` and the existing `*.test.tsx`), `lib/` (`href.ts`, `tags.ts`, `search-params.ts` and their `*.test.ts`), `index.ts` and `conventions.test.ts`. No other `.ts`, `.tsx` or `.css` file remains at the root.
- **AC2** `features/feed/index.ts` is the feature's only public surface. It exports exactly three runtime values: `FeedView`, `loadFeedState` and `parseFeedSearchParams`. It exports no other values. It exports no types, because `app/` needs none. No file outside `features/feed/` imports a path inside `features/feed/<sub-folder>/`, whether through `@/features/feed/...` or a relative `../features/feed/...` path. No module inside `features/feed/` imports its own `index.ts`. An automated guard fails on any violation and names the offending file.
  Example: adding `import { feedHref } from '@/features/feed/lib/href'` to `app/page.tsx` -> `npm test` fails, naming `app/page.tsx`.
- **AC3** (WEB-1 continues to hold) No `"use client"` module imports the barrel (`@/features/feed` or a relative path to `features/feed/index`) or anything under `features/feed/api/`. Modules under `components/` and `lib/` import from `api/` only with `import type`, so they stay safe to use as client components later. The existing guards T29, T30 and T31 still pass unchanged. An automated guard fails on any violation.
  Example: a new `"use client"` file under `features/feed/components/` containing `import { loadFeedState } from '..'` -> `npm test` fails. `components/feed-view.tsx` containing `import { FeedApiError } from '../api/client'` (a value import) -> `npm test` fails.
- **AC4** `parseFeedSearchParams(searchParams)` turns Next's `searchParams` object into `{ tag?: string; cursor?: string }` using exactly the rules `app/page.tsx` applies today:
  - `tag` is returned unchanged (not trimmed) when it is a string that contains at least one non-whitespace character. It is `undefined` when it is absent, an array, an empty string or whitespace only.
  - `cursor` is returned byte-identical when it is a non-empty string. It is `undefined` when it is absent, an array or an empty string.
  Example: `{ tag: ' agents ' }` -> `{ tag: ' agents ', cursor: undefined }`. `{ tag: ['a', 'b'] }` -> `{ tag: undefined, cursor: undefined }`. `{ tag: '   ', cursor: 'a+b/c=' }` -> `{ tag: undefined, cursor: 'a+b/c=' }`. `{ cursor: '' }` -> `{ tag: undefined, cursor: undefined }`.
- **AC5** `loadFeedState({ tag, cursor })` returns a `FeedViewState` and never throws.
  - On success it returns `{ status: 'ok', page }`, where `page` is exactly the value `loadFeed({ tag, cursor })` resolved with. It logs nothing.
  - On a `FeedApiError` it returns `{ status: 'error', code: error.code }`.
  - On any other thrown value it returns `{ status: 'error', code: 'network' }`.
  - On either failure it writes exactly one `console.error` line, `JSON.stringify({ event: 'feed_fetch_failed', code, status, tag, has_cursor: cursor !== undefined })`, with the same keys in the same order as today. A key whose value is undefined is omitted. The line never includes the cursor value or the error message.
  Example: `loadFeed` rejects with `new FeedApiError('http', '…', 503)`, `tag: 'agents'`, `cursor: 'abc'` -> it logs `{"event":"feed_fetch_failed","code":"http","status":503,"tag":"agents","has_cursor":true}` and returns `{ status: 'error', code: 'http' }`. `loadFeed` rejects with `new TypeError('x')`, with no tag and no cursor -> it logs `{"event":"feed_fetch_failed","code":"network","has_cursor":false}` and returns `{ status: 'error', code: 'network' }`.
- **AC6** `app/page.tsx` only awaits `searchParams`, calls `parseFeedSearchParams`, awaits `loadFeedState` and renders `<FeedView state={…} tag={…} cursor={…} />`. Its only feature import is `@/features/feed`. It has no `try`/`catch`, no `console`, and does not import `FeedApiError`, `loadFeed` or `FeedViewState`.
  Example: `grep -E "try|catch|console|\.\./features" app/page.tsx` -> no matches.
- **AC7** (compatibility, no behavior or HTML change) Every end-to-end scenario renders, after the refactor, the same output it rendered before the refactor. The baseline for this comparison is captured from the unmodified pre-refactor code. Three things are compared:
  - the normalized DOM of the `FeedView` root;
  - the computed styles of a fixed selector set;
  - the browser console output, which must contain no errors.
  CSS-module class hashes are normalized before comparison, because moving `feed.module.css` changes them by design. The scenarios cover:
  - the `ok` state (first page and last page);
  - the `empty` state (unfiltered first page with no cards);
  - the `filtered-empty` state, with both the "No cards tagged" copy and the drained "We searched the first 5 pages" copy;
  - the `error` state for `http`, `malformed` and `network`, including the "Back to the first page" link when a cursor is set;
  - tag filtering: clicking a promoted chip and clicking a card's inline tag, the active-tag chip and "All cards";
  - pagination: "Next page →" carries `next_cursor` byte-identical (special characters included), "← First page" works, and browser Back returns to the previous page;
  - search-param edge cases: whitespace-only tag, repeated `tag`, empty cursor.
  The baseline files are not modified after they are captured.
  Example: `/?tag=agents` before the refactor and after it -> identical normalized `FeedView` DOM, identical computed styles, and zero console errors.
- **AC8** (compatibility) All 55 existing Vitest tests still pass, with the same assertions. In each moved test file, the only lines that change are import specifiers, `vi.mock` specifiers, filesystem path constants and comments that describe those paths. `git diff -M` shows each existing test file as a rename.
  Example: `components/feed-view.test.tsx` differs from `feed-view.test.tsx` only in `from "../api/client"` and `from "../api/types.generated"`.
- **AC9** (compatibility, generated types and design CSS) `npm run generate:types` writes to `features/feed/api/types.generated.ts`. The output is byte-identical to the committed file, and no file is created at the old path. The drift tests T1, T2 and T3 pass from the new location. `components/feed.module.css` and `api/types.generated.ts` have the same SHA-256 as their pre-move originals (WEB-2, WEB-9). Every other moved source file differs from its original only in import specifiers.
  Example: `shasum -a 256 features/feed/components/feed.module.css` -> `fedbe6ba59638c4277e972358b35bfb9dc6a0e749479731fbb60925317d151f7`.
- **AC10** (tooling) `@playwright/test` is the only new dependency. It is added as a devDependency because the human explicitly sanctioned it. `npm run test:e2e` runs the Playwright suite against a local stub of `feed-api` and makes no request to AWS. `npm test`, `npm run lint`, `npm run typecheck` and `npm run build` all stay green. Vitest does not collect Playwright files, and Playwright does not collect Vitest files. Playwright output (`test-results/`, any HTML report, temporary server logs) is neither committed nor linted.
  Example: run `npm run test:e2e` with `.env.local` still pointing at the real `execute-api` URL -> every scenario renders stub fixture cards, and the run passes offline.

## Scope
**In**
- Moving 17 of the 18 existing files under `features/feed/` into `api/`, `components/` and `lib/` with `git mv`. The 18th, `conventions.test.ts`, stays at the root.
- New `features/feed/index.ts`, `api/load-feed-state.ts` and `lib/search-params.ts`, each with a colocated test.
- New cases in `conventions.test.ts` that enforce AC2 and AC3.
- Slimming `app/page.tsx` to the shape in AC6.
- Updating the output path in `scripts/generate-api-types.mjs`.
- Playwright tooling:
  - the `@playwright/test` devDependency and the Chromium browser;
  - `playwright.config.ts`;
  - a `test:e2e` npm script;
  - a dependency-free local `feed-api` stub;
  - e2e specs under `e2e/` and committed baselines under `e2e/__baseline__/`;
  - ignore entries for Playwright artifacts in `.gitignore` and the ESLint config.

**Out**
- Any visual, copy, CSS-rule, markup or behavior change, including to `isCardOut`, caching (`REVALIDATE_SECONDS`, `AbortSignal` timeout), drain bound, error copy or the `feed-api` contract.
- Splitting or editing `feed.module.css`. Its stale "Copy into apps/web/features/feed/feed.module.css" header comment stays as it is (WEB-9).
- Any new dependency other than `@playwright/test`. The `server-only` package is not added.
- Running e2e in CI. The generated `harny-feedback-web.yml` is not hand-edited.
- Documentation updates (AGENTS.md Components section, repo-root README.md lines ~700–736, `specs/current/web-feed.md` paths). These belong to the documentation and `harny-sync` roles after the audit and are listed in `execution-plan.md`.
- Deploying to Vercel (WEB-11).

## Constraints
- WEB-1 to WEB-11 in `specs/current/web-feed.md` continue to hold. WEB-1, WEB-3, WEB-5 and WEB-9 are the ones this change touches. This spec does not contradict any current-truth statement. It refines two of them:
  - Invariant 3 ("`app/page.tsx` stays a thin, ~25-line shell … covered only by the manual browser check"). The page gets thinner, and its former logic becomes unit-tested. The page shell itself becomes e2e-tested. Render-state branching stays in `FeedView`.
  - The WEB-2 scenario's file path (`features/feed/types.generated.test.ts` moves to `features/feed/api/types.generated.test.ts`). `harny-sync` updates both statements at archive time.
- WEB-11's local smoke check against the real `feed-api` is still part of the definition of done. The stubbed e2e suite adds to it and does not replace it.
- This is a pure refactor. Existing test assertions must not be weakened or edited (AC8).
- `@playwright/test` is the one sanctioned dependency addition, and only as a devDependency. The human requested it for regression proof, and it is flagged here so the auditor treats it as authorized.
- The e2e suite must be deterministic and fully local. It must not depend on AWS, the network, wall-clock time or the Next Data Cache state between scenarios.

## Open questions
- `parseFeedSearchParams` is a third public export. It was added so that `loadFeedState` keeps the requested `({ tag, cursor }) => FeedViewState` signature while the search-param parsing still leaves `page.tsx` and gets tested. The alternative is for `loadFeedState` to accept the raw `searchParams` and return `{ state, tag, cursor }`. Is the three-export surface acceptable?
- Should the e2e suite run in CI later? That would need a change to the harny-generated workflow, made via `harny init` or a separate workflow. It is out of scope here.
- `app/__golden__/` and `e2e/.tmp/` are empty, untracked leftover directories from an earlier experiment. This plan leaves `app/__golden__/` alone (it is an App Router private folder, so it does not affect routing) and reuses `e2e/__baseline__/` and `e2e/.tmp/`. Should the executor delete `app/__golden__/`?
- Should the documentation role record the "feature folders by role behind a single public entry point" convention as ADR 0008, the next repo-wide number?

## Revision history
- Revision 1 (2026-10-03): initial draft.

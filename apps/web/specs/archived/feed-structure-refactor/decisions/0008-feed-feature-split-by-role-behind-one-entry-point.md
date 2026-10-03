# ADR 0008: Split the feed feature by role behind one public entry point, verified by an offline Playwright baseline

- **Status**: Accepted
- **Date**: 2026-10-03
- **Feature**: feed-structure-refactor
- **Capability**: web-feed
- **Source**: execution-plan.md § Proposed approach (target layout; barrel export surface; `loadFeedState` placement); § Binding constraints (`@playwright/test` exception); § Validation (AC7)
- **Trigger**: (a) named options were weighed (layout, barrel shape, `loadFeedState` placement); (b) constrains future features (import rules, export surface); (d) deliberately accepts a known cost (CSS-module hash change, one new dev dependency)

## Context

`features/feed/` held 18 files flat, and `app/page.tsx` carried untested logic (search-param parsing, error-to-state mapping, the `feed_fetch_failed` log line). `index.ts` re-exports server-only code (`loadFeedState` reaches `client.ts`), so WEB-1 needed a structural way to keep client-capable code away from it. Proving "no behavior change" for a Server Component page is impossible with Vitest/RTL alone.

## Decision

`features/feed/` is split by role into `api/` (server-only and contract code), `components/` (rendering) and `lib/` (pure helpers), with tests beside their source and only `index.ts` and `conventions.test.ts` at the root. `index.ts` is the only public surface and exports exactly three runtime values (`FeedView`, `loadFeedState`, `parseFeedSearchParams`) as explicit named re-exports, with no types. `conventions.test.ts` enforces no deep imports from outside the feature, no barrel self-imports, no `"use client"` import of the barrel or `api/`, and `import type` only from `components/`/`lib/` into `api/`. Behavior preservation is proven by a Playwright suite (`@playwright/test`, the sole sanctioned new devDependency) run against a `node:http` stub of `feed-api` and compared with a baseline captured from the pre-refactor app; CSS-module class hashes are normalized in the DOM snapshots because moving `feed.module.css` changes them by design.

## Alternatives considered

| Option | Why not |
|---|---|
| `export *` from the barrel, or also exporting `FeedViewState` | Leaks every helper; no consumer needs the type. |
| `loadFeedState` at the feature root or in `lib/` | A fourth category, or server-only code in a client-safe folder. |
| `conventions.test.ts` moved into `lib/` | Changes a path constant and misdescribes its scope. |
| Vitest-only verification | Cannot render the async Server Component page. |
| A stub-server or snapshot library | Violates the single-new-dependency constraint; `node:http` suffices. |
| Not normalizing CSS-module hashes | The baseline could never match after the CSS file moves. |

## Consequences

**Positive**: One rule ("no client module imports `api/` or the barrel") covers all server-only code; the page is an 11-line shell; the refactor is machine-verified against the original (23 e2e scenarios, 87 unit tests).

**Accepted costs**: One devDependency plus a Chromium download; the e2e suite is not part of `npm test` or the `harny-feedback-web.yml` CI workflow; hash normalization means class-name regressions are not caught by the e2e DOM comparison. Audit reservation F3 (an untracked duplicate workflow `.github/workflows/harny-feedback-apps-web.yml`, no CI run yet) is left to the human.

## Follow-ups

Decide whether to run `npm run test:e2e` in CI. Resolve the duplicate workflow file (F3).

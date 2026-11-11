# Tasks: Web Feed Previous Page

## Status
Implemented. Audit round 2 APPROVED WITH RESERVATIONS (2026-11-10, accepted under the human's standing instruction).
O8 (AC10, local check against the real `feed-api`) PASSED on 2026-11-10 (run by the conductor). O9 (CI evidence, F5) pending
the PR's CI run. Vercel deploy is human-only and not done.

## Baseline
- Base commit: c9c0c2f (uncommitted feed and backend work on top, kept as is)
- Branch: feat/feed-prev-cursor
- Interpreter: Node v24.16.0; Next 16.3.5, React 19.2.8, vitest ^4.1.11, @playwright/test 1.64.1
- Cwd: /Users/danielerazo/python/project-agentcore-app/apps/web
- Commands: `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`, `npm run test:e2e`
- Pre-existing failures: none observed beyond red tests; lint has 1 warning (unused eslint-disable in generated types.generated.ts, not ours)

## Outcomes
- [x] **O1** (AC3): `fetchFeed` normalizes `prev_cursor` into `FeedPage.prevCursor` (string or null), never throws on it.
  - Tests: `features/feed/api/client.test.ts` (prev_cursor normalisation `it.each`)
  - Red: client.test.ts: 5 prev_cursor cases failed (expected undefined)
  - Green: `npm test` 400+ passed (see O7); e2e `npm run test:e2e` all passed
- [x] **O2** (AC5, AC7): `dir=prev` is parsed, threaded through `app/page.tsx` and `loadFeedState`, and `loadFeed`
  drains along `prevCursor` for backward requests, bounded by `MAX_DRAIN_REQUESTS`; forward drain unchanged.
  - Tests: `features/feed/api/load-feed.test.ts` (backward drain test)
  - Red: load-feed.test.ts: backward drain followed next_cursor (called with F1/F2), failed
  - Green: `npm test` 400+ passed (see O7); e2e `npm run test:e2e` all passed
- [x] **O3** (AC1, AC2, AC6, AC7): `Pagination` renders `‹ Previous page` (href with `dir=prev`) between First and
  Next; the no-match state uses honest backward copy; `Try again` keeps `dir`. No CSS change.
  - Tests: `features/feed/components/feed-view.test.tsx` (link visibility test; backward no-match test)
  - Red: feed-view.test.tsx: Previous link visibility and backward no-match copy tests failed
  - Green: `npm test` 400+ passed (see O7); e2e `npm run test:e2e` all passed
- [x] **O4** (AC4, AC8): e2e stub serves `prev_cursor` on the unfiltered second page and the backward first page;
  `populated.json` gains `prev_cursor`; one Playwright flow Next -> Previous; `ok-last-page` DOM baseline
  re-captured and its diff reviewed; `feed.e2e.ts` header records the re-capture.
  - Tests: `e2e/feed.e2e.ts` (navigation: Next then Previous)
  - Red: e2e Previous flow failed (no Previous link)
  - Green: `npm test` 400+ passed (see O7); e2e `npm run test:e2e` all passed
- [x] **O5** (AC7, AC8) Migration: `prevCursor` added to the `FeedPage` literals and helpers in `load-feed.test.ts`,
  `load-feed-state.test.ts` and `feed-view.test.tsx`. `search-params.test.ts` gains one test, "direction is 'prev' only
  for dir=prev together with a cursor", which asserts `direction` explicitly for `cursor` + `dir=prev`, `dir=prev`
  without a cursor, `dir=other` and a repeated `dir` (round 2, F3). `load-feed-state.test.ts` gains "passes direction
  'prev' through to loadFeed".
- [x] **O6** Docs (AC9): root `README.md` `prev_cursor` note, `docs/runbooks.md` web browser check,
  `apps/web/AGENTS.md` WEB-4 line.
- [x] **O7** Broader suite vs baseline (AC8): `npm run lint && npm run typecheck && npm test && npm run build && npm run test:e2e`
  - Evidence: lint 0 errors / 1 pre-existing warning; typecheck clean; vitest 403/403 (20 files); build ok;
    Playwright 54/54. Among the DOM baselines, this spec changes only `e2e/__baseline__/dom/ok-last-page.html` (two
    Previous links added). Re-run by the conductor on 2026-11-10 (lint, typecheck, test, build, test:e2e).
- [x] **O8** Local check against the real `feed-api` (AC10): PASSED on 2026-11-10, run by the conductor (not the auditor).
  `npm run dev` against the deployed `feed-api` (16 cards, page size 5): page 1 shows 5 cards with only `Next page →`
  and no Previous link; page 2 shows `← First page`, `‹ Previous page`, `Next page →`; following `‹ Previous page` from
  page 2 returns exactly page 1's 5 cards in the same order, and that link's href carries `dir=prev`.
- [ ] **O9** Independent audit: round 2 verdict APPROVED WITH RESERVATIONS (2026-11-10). Still pending: CI evidence for
  F5, a green `harny-feedback-apps-web.yml` run on the PR with N > 0 commands run.

## Working state
- Updated: 2026-11-10
- Outcome: O1–O8 done; O9 pending (CI evidence, F5)
- Phase: shipped locally; documentation and archive hand-off done 2026-11-10
- In progress: none
- Last command: none
- Next step: open the PR and confirm its `harny-feedback-apps-web.yml` run is green (F5). Vercel deploy is a human step (WEB-R1).

## Finding responses
| Finding | Response | Evidence |
|---|---|---|
| F1 | Docs edited (README, runbooks, AGENTS WEB-4) | git diff; `grep -n "does not use .prev_cursor" README.md` empty |
| F2 | Neutral copy when no tag and not drained; regression test | feed-view.test.tsx ("without a tag it never says 'tagged undefined'") |
| F3 | Parser and loadFeedState direction tests, explicit `direction` assertions | search-params.test.ts, load-feed-state.test.ts |
| F4 | Red results recorded per outcome; Status and Checkpoint current | this file |
| F8 | Working state, O5 wording and O7 count refreshed | this file |

## Checkpoint
Audit round 1 REJECTED (F1 docs not updated; F2 reachable "tagged undefined" copy). Round 2 APPROVED WITH RESERVATIONS:
F1–F4 closed; F8 closed by this tidy; F5 (CI evidence), F7 (e2e does not assert `Next page →` on the backward page) and
the layout default stay open as reservations. F6 (AC10) is recorded in O8 from the conductor's local run, not re-verified
by the auditor. Documentation and the archive hand-off are done.
